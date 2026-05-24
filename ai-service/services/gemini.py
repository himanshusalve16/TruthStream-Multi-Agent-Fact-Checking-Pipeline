"""Gemini service client manager and error handling/fallback logic."""
import asyncio
import logging
from typing import Callable, Any
import httpx
from google import genai
from google.genai import errors
from config import settings

logger = logging.getLogger(__name__)


class GeminiClientManager:
    def __init__(self):
        self._keys = []
        self._current_index = 0
        self._clients = {}
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
        logger.info("GeminiClientManager initialized with %d keys", len(self._keys))

    def get_client(self) -> genai.Client:
        if not self._keys:
            # Will default to settings.gemini_api_key_1 or throw
            return genai.Client(api_key=settings.gemini_api_key_1)

        key = self._keys[self._current_index]
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

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
    Executes a Gemini API call with proper retry logic and key fallback.

    Retry Policy:
    - Max 1 retry for transient errors (5xx, timeouts, network errors) on the current key.
    - 2.0 second delay before retry.
    - DO NOT retry the current key for 429 (quota), 403 (permission), 401, or 400.

    Fallback Policy:
    - If a key fails (due to 429, 403, 401, 5xx after retry, or transient error after retry),
      rotate to the next available key and restart the request.
    - If all keys in the pool have been tried and failed, raise a final clean error.
    - Permanent 404 Model Not Found error is raised immediately without rotating keys.
    """
    total_keys = gemini_manager.get_total_keys()
    keys_tried = 0

    # Ensure we try at least once if total_keys is 0
    max_tries = max(1, total_keys)

    while keys_tried < max_tries:
        client = gemini_manager.get_client()
        masked_key = gemini_manager.get_current_key_masked()
        logger.info(
            "Attempting Gemini call with key slot %d (%s) (tried %d/%d keys)",
            gemini_manager._current_index,
            masked_key,
            keys_tried,
            total_keys,
        )

        try:
            # Try call
            return await call_fn(client)
        except Exception as e:
            err_str = str(e).lower()
            code = getattr(e, "code", None)
            
            # Extract code from APIError if applicable
            if isinstance(e, errors.APIError) and getattr(e, "code", None):
                code = e.code

            # A. Invalid model (404 Not Found)
            if code == 404 or "is not found" in err_str or "not supported" in err_str:
                logger.error("Invalid Gemini model: %s. Stopping fallback rotation.", settings.gemini_model)
                raise RuntimeError(f"Invalid Gemini model configuration: {settings.gemini_model}. Please use a supported model like gemini-2.5-flash-lite.") from e

            # B. Quota exceeded (429)
            elif code == 429 or "quota" in err_str or "resource_exhausted" in err_str:
                logger.warning("Quota exceeded for key slot %d (%s).", gemini_manager._current_index, masked_key)
                
            # C. Invalid API Key (400 or 403 permission)
            elif code in (400, 401, 403) and ("api key not valid" in err_str or "api_key_invalid" in err_str or "permission" in err_str):
                logger.warning("API key in slot %d (%s) is invalid or unauthorized.", gemini_manager._current_index, masked_key)

            # D. Network Timeout or E. Provider Outage (Transient)
            elif is_transient_error(e):
                logger.warning("Transient error/timeout on key slot %d (%s): %s. Retrying once...", gemini_manager._current_index, masked_key, str(e))
                await asyncio.sleep(2.0)
                try:
                    return await call_fn(client)
                except Exception as retry_err:
                    logger.warning("Retry failed on key slot %d (%s). Proceeding to rotate.", gemini_manager._current_index, masked_key)
                    e = retry_err
            
            # Other permanent errors
            elif code == 400:
                logger.error("Permanent 400 Bad Request error on key slot %d (%s). Raising immediately.", gemini_manager._current_index, masked_key)
                raise e
                
            else:
                logger.warning("Unexpected error on key slot %d (%s): %s", gemini_manager._current_index, masked_key, str(e))

            # Rotate key and try next one if we have fallback keys
            if total_keys > 1:
                gemini_manager.rotate_key()
                keys_tried += 1
            else:
                # No other keys to try
                break

    # If all keys failed, raise a clean exception
    logger.error("All %d Gemini API keys in the pool have failed.", total_keys)
    raise RuntimeError("AI provider quota temporarily exceeded or all keys failed. Please try again later.")

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
