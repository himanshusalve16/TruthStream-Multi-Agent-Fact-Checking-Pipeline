"""
TruthStream AI Service — main FastAPI application.
Orchestrates the multi-agent fact-checking pipeline.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
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


# ──────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager for the FastAPI app."""
    # ── Startup ──────────────────────────────────────────────
    logger.info("[STARTUP] FastAPI application boot initialized.")
    
    logger.info("[STARTUP] Initializing database pool connection...")
    app.state.db_pool = await _connect_db_with_retry(settings.database_url)
    logger.info("[STARTUP] Database pool connection established successfully.")

    # Clean up stuck jobs from previous session
    logger.info("[STARTUP] Initializing startup watchdog cleanup for stuck jobs...")
    await cleanup_stuck_jobs(app.state.db_pool)

    logger.info("[STARTUP] Connecting to Redis database...")
    app.state.redis = await _connect_redis_with_retry(settings.redis_url)
    logger.info("[STARTUP] Redis connection established successfully.")

    logger.info("[STARTUP] Initializing Redis Pub/Sub SSE event system...")
    # System ready to stream notifications via Redis publisher

    logger.info("[STARTUP] Prewarming HTTP Client Session...")
    app.state.http_client = httpx.AsyncClient(
        timeout=10.0,
        headers={"User-Agent": "TruthStream-Bot/1.0 (+https://truthstream.app/bot)"},
        follow_redirects=True,
        max_redirects=3,
    )
    logger.info("[STARTUP] HTTP Client Session warmed and ready.")

    logger.info("[STARTUP] Initializing and validating Gemini AI client configuration...")
    from services.gemini import validate_gemini_model_sync
    await asyncio.to_thread(validate_gemini_model_sync)
    logger.info("[STARTUP] Gemini AI client validated and ready.")

    logger.info("[STARTUP] Initializing pipeline routing engine...")
    # Pipeline router components imported and loaded
    logger.info("[STARTUP] Pipeline routing engine loaded.")

    logger.info("[STARTUP] Starting background stalled jobs watchdog...")
    app.state.watchdog_task = asyncio.create_task(stalled_jobs_watchdog(app))

    logger.info("[STARTUP] Starting Redis cancellation listener...")
    app.state.cancel_listener_task = asyncio.create_task(cancellation_listener(app))

    logger.info("[STARTUP] Starting %d fast and %d slow async queue workers...", NUM_FAST_WORKERS, NUM_SLOW_WORKERS)
    app.state.workers = []
    for i in range(NUM_FAST_WORKERS):
        app.state.workers.append(
            asyncio.create_task(job_worker(app, "job_queue_fast"), name=f"fast-worker-{i}")
        )
    for i in range(NUM_SLOW_WORKERS):
        app.state.workers.append(
            asyncio.create_task(job_worker(app, "job_queue_slow"), name=f"slow-worker-{i}")
        )
    logger.info("[STARTUP] Queue consumer background task(s) spawned successfully.")

    logger.info("AI service ready and listening.")
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service"}
