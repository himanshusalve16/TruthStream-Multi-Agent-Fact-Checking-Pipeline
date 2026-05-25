import asyncio
import logging
import time
import redis.asyncio as aioredis
from fastapi import FastAPI

from config import settings
from db import queries
from services.redis_publisher import publish_status
from orchestration.pipeline_router import route_and_execute_pipeline, log_lifecycle_async, _fail_job

logger = logging.getLogger("truthstream.ai.worker")

MAX_CONCURRENT_JOBS = 5
concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


async def cleanup_stuck_jobs(pool) -> None:
    """Startup watchdog: Clean up any jobs stuck in PENDING or PROCESSING status from previous runs."""
    try:
        async with pool.acquire() as conn:
            count = await conn.execute(
                """
                UPDATE jobs
                SET status = 'FAILED',
                    error_message = 'Job terminated due to system restart.',
                    updated_at = NOW()
                WHERE status IN ('PENDING', 'PROCESSING')
                """
            )
            logger.info("Startup watchdog: swept and marked stuck jobs as FAILED: %s", count)
    except Exception as e:
        logger.error("Startup watchdog: failed to clean up stuck jobs: %s", e)


async def stalled_jobs_watchdog(app: FastAPI):
    """Background watchdog to detect and resolve stalled jobs."""
    pool = app.state.db_pool
    redis = app.state.redis
    logger.info("Stalled jobs watchdog started")
    while True:
        try:
            await asyncio.sleep(15)
            async with pool.acquire() as conn:
                # Find jobs stuck in PENDING or PROCESSING for more than 45 seconds
                stuck_rows = await conn.fetch(
                    """
                    SELECT id, status, created_at, updated_at 
                    FROM jobs 
                    WHERE status IN ('PENDING', 'PROCESSING') 
                      AND (NOW() - COALESCE(updated_at, created_at)) > INTERVAL '45 seconds'
                    """
                )
                for row in stuck_rows:
                    job_id = str(row["id"])
                    status = row["status"]
                    logger.warning("[WATCHDOG] Job %s has been stuck in %s for too long. Forcing cleanup.", job_id, status)
                    await _fail_job(
                        pool, redis, job_id, 
                        f"Job processing stalled in {status} stage (45s timeout exceeded). Pipeline aborted."
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in stalled jobs watchdog: %s", e)


async def process_job(job_id: str, redis: aioredis.Redis, pool, http_client) -> None:
    """Safe wrapper to run the pipeline, catch all exceptions, and prevent silent stalls."""
    try:
        await route_and_execute_pipeline(job_id, redis, pool, http_client)
    except Exception as e:
        logger.exception("Unhandled exception in pipeline execution for job %s: %s", job_id, e)
        await _fail_job(pool, redis, job_id, f"Internal pipeline execution error: {e}")


async def run_job_with_semaphore(job_id: str, redis: aioredis.Redis, pool, http_client, worker_name: str):
    async with concurrency_semaphore:
        await log_lifecycle_async(pool, job_id, "TASK_DISPATCHED", details={"worker": worker_name})
        await process_job(job_id, redis, pool, http_client)


async def job_worker(app: FastAPI):
    """BRPOP from job_queue and process each job_id asynchronously."""
    redis = app.state.redis
    pool = app.state.db_pool
    http_client = app.state.http_client
    logger.info("Worker started")

    while True:
        try:
            result = await redis.brpop("job_queue", timeout=2)
            if result:
                _, job_id_bytes = result
                job_id = job_id_bytes.decode()
                logger.info("Worker picked up job: %s", job_id)
                
                worker_name = asyncio.current_task().get_name()
                await log_lifecycle_async(pool, job_id, "JOB_ACCEPTED", details={"worker": worker_name})
                await log_lifecycle_async(pool, job_id, "WORKER_ASSIGNED", details={"worker": worker_name})
                
                await publish_status(redis, job_id, "accepted", "Job accepted by worker thread...")
                await publish_status(redis, job_id, "spawning_agents", "Spawning fact-checking agents...")
                
                # Dispatch the task asynchronously
                asyncio.create_task(run_job_with_semaphore(job_id, redis, pool, http_client, worker_name))
        except asyncio.CancelledError:
            logger.info("Worker cancelled")
            break
        except Exception as e:
            logger.error("Worker error: %s", e)
            await asyncio.sleep(1)
