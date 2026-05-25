"""
TruthStream AI Service — main FastAPI application.
Orchestrates the multi-agent fact-checking pipeline.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import asyncio
import logging
import time
import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx

from config import settings
from db.connection import init_db_pool, close_db_pool
from routers import internal
from orchestration import cleanup_stuck_jobs, job_worker, stalled_jobs_watchdog, cancellation_listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("truthstream.ai")

NUM_FAST_WORKERS = 3
NUM_SLOW_WORKERS = 2

# ──────────────────────────────────────────────────────────────
# Startup helpers with retry
# ──────────────────────────────────────────────────────────────

_DB_MAX_RETRIES = 10
_DB_RETRY_DELAY = 3.0   # seconds between attempts

_REDIS_MAX_RETRIES = 8
_REDIS_RETRY_DELAY = 2.0


async def _connect_db_with_retry(database_url: str):
    """
    Attempt to create the asyncpg pool, retrying on failure.
    Without retry, a single connection failure crashes the process.
    """
    delay = 2.0
    for attempt in range(1, _DB_MAX_RETRIES + 1):
        try:
            pool = await init_db_pool(database_url)
            logger.info("Database pool connected successfully on attempt %d", attempt)
            return pool
        except Exception as exc:
            if attempt < _DB_MAX_RETRIES:
                logger.warning(
                    "DB connection attempt %d/%d failed. Retrying in %.1fs... Error: %s",
                    attempt, _DB_MAX_RETRIES, delay, exc
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 10.0)  # Exponential backoff up to 10s
            else:
                logger.error("DB connection failed permanently after %d attempts", _DB_MAX_RETRIES)
    
    logger.critical("Fatal: Could not connect to database after %d attempts. Failing gracefully to avoid infinite crash-loops.", _DB_MAX_RETRIES)
    raise SystemExit(1)


async def _connect_redis_with_retry(redis_url: str) -> aioredis.Redis:
    """
    Attempt to connect to Redis, retrying on failure.
    """
    delay = 1.0
    for attempt in range(1, _REDIS_MAX_RETRIES + 1):
        try:
            client = aioredis.from_url(redis_url, decode_responses=False)
            await client.ping()
            logger.info("Redis connected successfully on attempt %d", attempt)
            return client
        except Exception as exc:
            if attempt < _REDIS_MAX_RETRIES:
                logger.warning(
                    "Redis connection attempt %d/%d failed. Retrying in %.1fs... Error: %s",
                    attempt, _REDIS_MAX_RETRIES, delay, exc
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 5.0)
            else:
                logger.error("Redis connection failed permanently after %d attempts", _REDIS_MAX_RETRIES)
    
    logger.critical("Fatal: Could not connect to Redis after %d attempts. Failing gracefully.", _REDIS_MAX_RETRIES)
    raise SystemExit(1)


async def keepalive_loop(app: FastAPI):
    """
    Lightweight internal keepalive loop.
    Pings the local /health endpoint every 5 minutes using the shared HTTP pool
    to maintain warm runtime state, keep connections alive, and reduce pseudo-cold-starts.
    """
    await asyncio.sleep(10.0)  # Wait for startup to fully complete
    
    port = os.environ.get("PORT", "8000")
    url = f"http://127.0.0.1:{port}/health"
    client = app.state.http_client

    logger.info("[KEEPALIVE] Internal keepalive background loop started.")
    
    while True:
        try:
            response = await client.get(url, timeout=5.0)
            logger.debug("[KEEPALIVE] Keepalive ping status: %s", response.status_code)
        except asyncio.CancelledError:
            logger.info("[KEEPALIVE] Internal keepalive loop cancelled.")
            break
        except Exception as e:
            logger.warning("[KEEPALIVE] Internal keepalive ping failed: %s", e)
            
        try:
            await asyncio.sleep(300.0)  # Ping every 5 minutes
        except asyncio.CancelledError:
            logger.info("[KEEPALIVE] Internal keepalive loop cancelled.")
            break


# ──────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for the FastAPI app."""
    # ── Startup ──────────────────────────────────────────────
    start_time = time.perf_counter()
    app.state.is_ready = False
    app.state.boot_stage = "waking"
    logger.info("[INSTRUMENTATION] SERVICE_BOOT_START")
    logger.info("[STARTUP] FastAPI application boot initialized.")
    
    logger.info("[STARTUP] Initializing database pool connection...")
    app.state.db_pool = await _connect_db_with_retry(settings.database_url)
    logger.info("[INSTRUMENTATION] DB_POOL_READY")

    # Clean up stuck jobs from previous session
    logger.info("[STARTUP] Initializing startup watchdog cleanup for stuck jobs...")
    await cleanup_stuck_jobs(app.state.db_pool)

    logger.info("[STARTUP] Connecting to Redis database...")
    app.state.redis = await _connect_redis_with_retry(settings.redis_url)
    logger.info("[INSTRUMENTATION] REDIS_CONNECTED")

    logger.info("[STARTUP] Prewarming HTTP Client Session...")
    app.state.http_client = httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "TruthStream-Bot/1.0 (+https://truthstream.app/bot)"},
        follow_redirects=True,
        max_redirects=3,
    )
    logger.info("[INSTRUMENTATION] HTTP_POOL_READY")

    logger.info("[STARTUP] Initializing and validating Gemini AI client configuration...")
    app.state.boot_stage = "initializing"
    from services.gemini import validate_gemini_model_sync, gemini_manager
    await asyncio.to_thread(validate_gemini_model_sync)
    logger.info("[STARTUP] Gemini AI client validated.")
    
    # Phase 2: Prewarm Gemini clients to eliminate cold-start latency
    logger.info("[INSTRUMENTATION] GEMINI_PREWARM_START")
    logger.info("[STARTUP] Prewarming Gemini API clients (%d keys)...", gemini_manager.get_total_keys())
    for key_index in range(gemini_manager.get_total_keys()):
        try:
            client = gemini_manager.get_client()
            # Verify client is responsive by fetching model metadata asynchronously
            await client.aio.models.get(model=settings.gemini_model)
            logger.info("[STARTUP] Gemini client %d/%d warmed and ready (Key: %s)",
                key_index + 1, gemini_manager.get_total_keys(), gemini_manager.get_current_key_masked())
            # Rotate to next key
            gemini_manager.rotate_key()
        except Exception as e:
            logger.warning("[STARTUP] Failed to prewarm Gemini client %d: %s. Continuing next...",
                key_index + 1, e)
    
    # Rotate back to first key for actual use
    gemini_manager._current_index = 0
    logger.info("[INSTRUMENTATION] GEMINI_PREWARM_DONE")

    logger.info("[STARTUP] Preloading and caching prompt templates & agents...")
    import agents.bias_scorer
    import agents.extractor
    import agents.judge
    import agents.source_finder
    import orchestration.pipelines.fast
    import orchestration.pipelines.deep
    logger.info("[STARTUP] Prompt templates and agents preloaded.")

    logger.info("[STARTUP] Starting background stalled jobs watchdog...")
    app.state.watchdog_task = asyncio.create_task(stalled_jobs_watchdog(app))

    logger.info("[STARTUP] Starting Redis cancellation listener...")
    app.state.cancel_listener_task = asyncio.create_task(cancellation_listener(app))

    logger.info("[STARTUP] Starting %d fast and %d slow async queue workers...", NUM_FAST_WORKERS, NUM_SLOW_WORKERS)
    app.state.boot_stage = "waiting_workers"
    app.state.workers = []
    for i in range(NUM_FAST_WORKERS):
        app.state.workers.append(
            asyncio.create_task(job_worker(app, "job_queue_fast"), name=f"fast-worker-{i}")
        )
    for i in range(NUM_SLOW_WORKERS):
        app.state.workers.append(
            asyncio.create_task(job_worker(app, "job_queue_slow"), name=f"slow-worker-{i}")
        )
    logger.info("[INSTRUMENTATION] WORKER_POOL_READY")
    logger.info("[INSTRUMENTATION] QUEUE_CONSUMER_READY")

    # Start keepalive loop
    app.state.keepalive_task = asyncio.create_task(keepalive_loop(app))

    app.state.is_ready = True
    app.state.boot_stage = "ready"
    startup_duration = time.perf_counter() - start_time
    logger.info("[INSTRUMENTATION] SERVICE_READY | Startup Duration: %.3fs", startup_duration)
    yield

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("Shutting down workers...")
    for w in app.state.workers:
        w.cancel()
    await asyncio.gather(*app.state.workers, return_exceptions=True)

    logger.info("Shutting down watchdog task...")
    app.state.watchdog_task.cancel()
    await asyncio.gather(app.state.watchdog_task, return_exceptions=True)

    logger.info("Shutting down cancellation listener...")
    app.state.cancel_listener_task.cancel()
    await asyncio.gather(app.state.cancel_listener_task, return_exceptions=True)

    logger.info("Shutting down keepalive task...")
    app.state.keepalive_task.cancel()
    await asyncio.gather(app.state.keepalive_task, return_exceptions=True)

    await app.state.http_client.aclose()
    await close_db_pool(app.state.db_pool)
    await app.state.redis.aclose()
    logger.info("AI service stopped.")


app = FastAPI(
    title="TruthStream AI Service",
    version="1.0.0",
    description="Multi-agent fact-checking pipeline",
    lifespan=lifespan,
)

app.include_router(internal.router, prefix="/internal")

# Phase 5: Include observability router for metrics and health
from routers import observability
app.include_router(observability.router, prefix="/observability")


@app.get("/health")
async def health():
    """Ultra-lightweight health endpoint returning plain tiny JSON, no logging or processing."""
    return {"status": "ok"}


@app.get("/ready")
async def ready(request: Request):
    """
    Lightweight readiness check verifying Redis, Postgres DB pool,
    and completed startup initialization (including Gemini prewarming).
    """
    # 1. Check if application boot finished
    if not getattr(request.app.state, "is_ready", False):
        stage = getattr(request.app.state, "boot_stage", "waking")
        detail_map = {
            "waking": "Waking AI Service",
            "initializing": "Initializing Runtime",
            "waiting_workers": "Waiting for Warm Workers"
        }
        return JSONResponse(
            status_code=503,
            content={"status": "waking", "details": detail_map.get(stage, "Waking AI Service")}
        )

    # 2. Check Redis connection
    try:
        await asyncio.wait_for(request.app.state.redis.ping(), timeout=1.5)
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "details": f"Redis connection down: {str(e)}"}
        )

    # 3. Check Database pool
    try:
        async with request.app.state.db_pool.acquire(timeout=1.5) as conn:
            await conn.execute("SELECT 1")
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "details": f"Database pool down: {str(e)}"}
        )

    # 4. Check worker health
    workers_ok = True
    if not hasattr(request.app.state, "workers") or not request.app.state.workers:
        workers_ok = False
    else:
        for w in request.app.state.workers:
            if w.done() and w.exception() is not None:
                workers_ok = False
                break

    if not workers_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "details": "Queue workers crashed"}
        )

    return {"status": "ready"}

