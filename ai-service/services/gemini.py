"""Gemini service client manager and error handling/quota governance."""
import asyncio
import logging
import os
import time
from typing import Callable, Any
from contextvars import ContextVar
import httpx
from google import genai
from google.genai import errors
from config import settings

logger = logging.getLogger(__name__)

# ContextVar to hold the job ID and the job call counter for request budgeting
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
job_call_counter: ContextVar[int | None] = ContextVar("job_call_counter", default=None)

# Global tracking of active Gemini API calls
active_gemini_calls = 0

class GeminiClientManager:
    def __init__(self):
        self._keys = []
        self._current_index = 0
        self._clients = {}
        self._cooldowns = {}  # key -> timestamp when cooldown expires
        self._circuit_breaker_until = 0.0
        self.reload_keys()

    def reload_keys(self):
        # Gather keys
        raw_keys = [
            getattr(settings, "gemini_api_key_1", None),
            getattr(settings, "gemini_api_key_2", None),
            getattr(settings, "gemini_api_key_3", None),
            getattr(settings, "gemini_api_key_4", None),
        ]
        seen = set()
        self._keys = []
        for k in raw_keys:
            if k and isinstance(k, str) and k.strip() and "replace-me" not in k:
                k_clean = k.strip()
                if k_clean not in seen:
                    seen.add(k_clean)
                    self._keys.append(k_clean)

        # Fallback to default if list is empty
        if not self._keys and getattr(settings, "gemini_api_key_1", None):
            self._keys = [settings.gemini_api_key_1]

        self._current_index = 0
        self._cooldowns = {}
        self._circuit_breaker_until = 0.0
        logger.info("GeminiClientManager initialized with %d keys", len(self._keys))

    def is_degraded(self) -> bool:
        """Returns True if the global circuit breaker is active or all keys are in cooldown."""
        now = time.time()
        if now < self._circuit_breaker_until:
            return True
        if not self._keys:
            return True
        
        # Check if all keys are currently in cooldown
        all_in_cooldown = True
        for key in self._keys:
            cooldown_until = self._cooldowns.get(key, 0.0)
            if now >= cooldown_until:
                all_in_cooldown = False
                break
        
        if all_in_cooldown:
            self._circuit_breaker_until = now + 60.0
            logger.error(
                "[INSTRUMENTATION] QUOTA_COOLDOWN_ACTIVATED | All %d Gemini keys are in cooldown. Circuit breaker activated for 60s.",
                len(self._keys)
            )
            return True
            
        return False

    def mark_cooldown(self, key: str):
        """Put a key into cooldown for 60 seconds."""
        self._cooldowns[key] = time.time() + 60.0
        try:
            slot_idx = self._keys.index(key)
        except ValueError:
            slot_idx = -1
        logger.warning(
            "[INSTRUMENTATION] KEY_COOLDOWN_ACTIVATED | Key slot %d put in cooldown for 60s.",
            slot_idx
        )

    def get_client(self) -> genai.Client:
        if not self._keys:
            raise RuntimeError("No Gemini API keys configured.")

        # Check circuit breaker / cooldowns
        if self.is_degraded():
            raise RuntimeError("AI service capacity is currently degraded. Circuit breaker active.")

        now = time.time()
        total_keys = len(self._keys)
        for i in range(total_keys):
            idx = (self._current_index + i) % total_keys
            key = self._keys[idx]
            cooldown_until = self._cooldowns.get(key, 0.0)
            if now >= cooldown_until:
                # Key is available! Set current index to this slot.
                self._current_index = idx
                if key not in self._clients:
                    self._clients[key] = genai.Client(api_key=key)
                return self._clients[key]

        # Fallback safeguard
        raise RuntimeError("AI capacity limited. All Gemini keys are in cooldown. Circuit breaker active.")

    def rotate_key(self):
        if not self._keys or len(self._keys) <= 1:
            return
        old_index = self._current_index
        self._current_index = (self._current_index + 1) % len(self._keys)
        logger.warning(
            "Rotating Gemini API key from slot %d to slot %d (Total keys: %d)",
            old_index,
            self._current_index,
            len(self._keys),
        )

    def get_current_key_masked(self) -> str:
        if not self._keys:
            return "None"
        key = self._keys[self._current_index]
        if len(key) <= 8:
            return "***"
        return f"{key[:4]}...{key[-4:]}"

    def get_total_keys(self) -> int:
        return len(self._keys)


# Singleton instance
gemini_manager = GeminiClientManager()


# Global semaphore lazy-getter
_GLOBAL_GEMINI_SEMAPHORE = None

def get_gemini_semaphore() -> asyncio.Semaphore:
    global _GLOBAL_GEMINI_SEMAPHORE
    if _GLOBAL_GEMINI_SEMAPHORE is None:
        limit = int(os.environ.get("GEMINI_CONCURRENCY_LIMIT", "2"))
        _GLOBAL_GEMINI_SEMAPHORE = asyncio.Semaphore(limit)
    return _GLOBAL_GEMINI_SEMAPHORE


def is_transient_error(e: Exception) -> bool:
    """
    Check if an exception is a transient error that should be retried.
    Transient errors:
    - timeouts (asyncio.TimeoutError, httpx.TimeoutException)
    - network errors (httpx.NetworkError)
    - HTTP 5xx errors (ServerError)
    """
    if isinstance(e, (asyncio.TimeoutError, httpx.TimeoutException, httpx.NetworkError)):
        return True

    if isinstance(e, errors.ServerError):
        return True

    if isinstance(e, errors.APIError):
        # 5xx status codes
        if e.code and 500 <= e.code < 600:
            return True
        # Common transient status codes
        if e.code in (408, 502, 503, 504):
            return True

    # Check string representation for common network failures
    err_str = str(e).lower()
    if "timeout" in err_str or "connection" in err_str or "dns error" in err_str:
        return True

    return False


async def execute_gemini_call(call_fn: Callable[[genai.Client], Any]) -> Any:
    """
    Executes a Gemini API call with proper retry logic, key rotation, cooldown, 
    circuit-breaker, and request budgeting under a global concurrency semaphore.
    """
    global active_gemini_calls
    job_id = job_id_var.get() or "unknown"
    
    # 1. Budgeting Check
    current_calls = job_call_counter.get()
    if current_calls is not None:
        max_calls = int(os.environ.get("GEMINI_MAX_CALLS_PER_JOB", "12"))
        if current_calls >= max_calls:
            logger.error("[INSTRUMENTATION] JOB_BUDGET_EXCEEDED | Job: %s | Calls: %d / %d", job_id, current_calls, max_calls)
            raise RuntimeError(f"AI request budget exceeded for job {job_id}. Maximum of {max_calls} Gemini calls allowed.")
        job_call_counter.set(current_calls + 1)
        
    # 2. Circuit Breaker Check
    if gemini_manager.is_degraded():
        raise RuntimeError("AI service capacity is currently degraded. Circuit breaker active.")

    # 3. Global Concurrency Control via Semaphore
    sem = get_gemini_semaphore()
    logger.info("[INSTRUMENTATION] GLOBAL_SEMAPHORE_WAIT | Job: %s | Active Calls: %d", job_id, active_gemini_calls)
    
    start_wait = time.perf_counter()
    async with sem:
        wait_time = time.perf_counter() - start_wait
        logger.info("[INSTRUMENTATION] GLOBAL_SEMAPHORE_ACQUIRED | Job: %s | Wait Time: %.3fs", job_id, wait_time)
        
        active_gemini_calls += 1
        try:
            total_keys = gemini_manager.get_total_keys()
            keys_tried = 0
            max_tries = max(1, total_keys)

            while keys_tried < max_tries:
                # Check circuit breaker inside loop as well
                if gemini_manager.is_degraded():
                    raise RuntimeError("AI service capacity is currently degraded. Circuit breaker active.")

                try:
                    client = gemini_manager.get_client()
                except RuntimeError as re:
                    logger.error("[INSTRUMENTATION] CIRCUIT_BREAKER_TRIGGERED | %s", str(re))
                    raise re

                masked_key = gemini_manager.get_current_key_masked()
                slot_index = gemini_manager._current_index
                
                logger.info(
                    "[INSTRUMENTATION] GEMINI_CALL_START | Job: %s | Model: %s | Key Slot: %d (%s) (tried %d/%d keys)",
                    job_id,
                    settings.gemini_model,
                    slot_index,
                    masked_key,
                    keys_tried,
                    total_keys,
                )

                call_start = time.perf_counter()
                try:
                    # Execute the actual call
                    result = await call_fn(client)
                    call_duration = time.perf_counter() - call_start
                    logger.info(
                        "[INSTRUMENTATION] GEMINI_CALL_SUCCESS | Job: %s | Key Slot: %d | Duration: %.3fs",
                        job_id,
                        slot_index,
                        call_duration,
                    )
                    return result
                except Exception as e:
                    call_duration = time.perf_counter() - call_start
                    err_str = str(e).lower()
                    code = getattr(e, "code", None)
                    
                    if isinstance(e, errors.APIError) and getattr(e, "code", None):
                        code = e.code

                    logger.warning(
                        "[INSTRUMENTATION] GEMINI_CALL_FAILURE | Job: %s | Key Slot: %d | Duration: %.3fs | Error: %s",
                        job_id,
                        slot_index,
                        call_duration,
                        str(e),
                    )

                    # A. Invalid model (404 Not Found) - stop immediately
                    if code == 404 or "is not found" in err_str or "not supported" in err_str:
                        logger.error("Invalid Gemini model: %s. Stopping fallback rotation.", settings.gemini_model)
                        raise RuntimeError(f"Invalid Gemini model configuration: {settings.gemini_model}. Please use a supported model like gemini-2.5-flash-lite.") from e

                    # B. Quota exceeded (429) or C. Invalid key/unauthorized (400/401/403 credentials)
                    is_quota = code == 429 or "quota" in err_str or "resource_exhausted" in err_str
                    is_auth_error = code in (400, 401, 403) and ("api key not valid" in err_str or "api_key_invalid" in err_str or "permission" in err_str)
                    
                    if is_quota or is_auth_error:
                        if is_quota:
                            logger.warning("[INSTRUMENTATION] QUOTA_COOLDOWN_ACTIVATED | Key Slot: %d | Key put in 60s cooldown.", slot_index)
                        else:
                            logger.warning("[INSTRUMENTATION] INVALID_KEY_COOLDOWN | Key Slot: %d | Bad key put in 60s cooldown.", slot_index)
                        
                        # Mark this key as cooling down
                        gemini_manager.mark_cooldown(gemini_manager._keys[slot_index])
                        
                        # Rotate immediately
                        gemini_manager.rotate_key()
                        keys_tried += 1
                        continue

                    # D. Transient errors - retry exactly once on current key
                    elif is_transient_error(e):
                        logger.warning("[INSTRUMENTATION] TRANSIENT_RETRY_START | Job: %s | Key Slot: %d. Retrying in 2.0s...", job_id, slot_index)
                        await asyncio.sleep(2.0)
                        
                        call_retry_start = time.perf_counter()
                        try:
                            result = await call_fn(client)
                            logger.info(
                                "[INSTRUMENTATION] GEMINI_CALL_SUCCESS (AFTER RETRY) | Job: %s | Key Slot: %d | Duration: %.3fs",
                                job_id,
                                slot_index,
                                time.perf_counter() - call_retry_start,
                            )
                            return result
                        except Exception as retry_err:
                            logger.warning(
                                "[INSTRUMENTATION] GEMINI_CALL_FAILURE (AFTER RETRY) | Job: %s | Key Slot: %d | Error: %s",
                                job_id,
                                slot_index,
                                str(retry_err),
                            )
                            # Put key in cooldown and rotate
                            gemini_manager.mark_cooldown(gemini_manager._keys[slot_index])
                            gemini_manager.rotate_key()
                            keys_tried += 1
                            e = retry_err
                            continue
                    
                    # Permanent client-side error (like 400 Bad Request) - do not rotate, raise immediately
                    elif code == 400:
                        logger.error("Permanent 400 Bad Request on key slot %d. Raising immediately.", slot_index)
                        raise e
                        
                    else:
                        # Other unexpected errors: put in cooldown and rotate
                        gemini_manager.mark_cooldown(gemini_manager._keys[slot_index])
                        gemini_manager.rotate_key()
                        keys_tried += 1
                        continue

            # If all keys failed
            logger.error("[INSTRUMENTATION] ALL_KEYS_EXHAUSTED | Job: %s", job_id)
            raise RuntimeError("AI provider quota temporarily exceeded or all keys failed. Please try again later.")
        finally:
            active_gemini_calls -= 1


def validate_gemini_model_sync():
    """Validates the configured Gemini model using the primary API key."""
    client = gemini_manager.get_client()
    try:
        logger.info("Validating Gemini model on startup: %s", settings.gemini_model)
        client.models.get(model=settings.gemini_model)
        logger.info("Gemini model validated successfully: %s", settings.gemini_model)
    except Exception as e:
        err_str = str(e).lower()
        code = getattr(e, "code", None)
        if isinstance(e, errors.APIError) and getattr(e, "code", None):
            code = e.code

        if code == 404 or "is not found" in err_str or "not supported" in err_str:
            logger.error("Startup validation failed: Invalid Gemini model configured: %s.", settings.gemini_model)
            logger.error("Supported alternatives: gemini-2.5-flash-lite, gemini-2.5-flash")
            raise RuntimeError(f"Invalid Gemini model configuration: {settings.gemini_model}. Please use a supported model like gemini-2.5-flash-lite.") from e
        elif code in (400, 401, 403) and ("api key not valid" in err_str or "api_key_invalid" in err_str):
            logger.warning("Primary API key is invalid, skipping strict model validation on startup.")
        else:
            logger.warning("Could not cleanly validate model %s on startup, but proceeding. Error: %s", settings.gemini_model, e)
