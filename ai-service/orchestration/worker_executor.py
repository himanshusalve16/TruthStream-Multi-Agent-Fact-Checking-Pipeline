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

MAX_FAST_CONCURRENT_JOBS = 15
MAX_SLOW_CONCURRENT_JOBS = 4
fast_concurrency_semaphore = asyncio.Semaphore(MAX_FAST_CONCURRENT_JOBS)
slow_concurrency_semaphore = asyncio.Semaphore(MAX_SLOW_CONCURRENT_JOBS)

# Registry to track active pipeline execution tasks for cancellation
active_tasks = {}


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
                    
                    # Publish cancellation event to interrupt active worker threads across node cluster
                    try:
                        await redis.publish("job:cancel:events", job_id)
                    except Exception as pe:
                        logger.error("Failed to publish cancel event for job %s: %s", job_id, pe)
                        
                    await _fail_job(
                        pool, redis, job_id, 
                        f"Job processing stalled in {status} stage (45s timeout exceeded). Pipeline aborted."
                    )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in stalled jobs watchdog: %s", e)


async def cancellation_listener(app: FastAPI):
    """Redis Pub/Sub listener to coordinate task cancellation across scaled execution nodes."""
    redis = app.state.redis
    pubsub = redis.pubsub()
    await pubsub.subscribe("job:cancel:events")
    logger.info("Cancellation Pub/Sub listener active on job:cancel:events")
    try:
        async for message in pubsub.listen():
            if message and message["type"] == "message":
                job_id = message["data"].decode()
                task = active_tasks.get(job_id)
                if task:
                    logger.warning("Cancellation Listener: Cancelling hung task for job %s", job_id)
                    task.cancel()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Error in cancellation listener loop: %s", e)
    finally:
        await pubsub.unsubscribe("job:cancel:events")


async def heartbeat_reporter(job_id: str, redis: aioredis.Redis, stop_event: asyncio.Event):
    """Periodically refreshes a job's Redis heartbeat key during active pipeline execution."""
    while not stop_event.is_set():
        try:
            # 5-second TTL heartbeat
            await redis.setex(f"job:{job_id}:heartbeat", 5, "1")
        except Exception as e:
            logger.warning("Failed to write heartbeat for job %s: %s", job_id, e)
        await asyncio.sleep(2.0)


async def process_job(job_id: str, redis: aioredis.Redis, pool, http_client) -> None:
    """Safe wrapper to run the pipeline, catch all exceptions, and prevent silent stalls."""
    try:
        await route_and_execute_pipeline(job_id, redis, pool, http_client)
    except Exception as e:
        logger.exception("Unhandled exception in pipeline execution for job %s: %s", job_id, e)
        await _fail_job(pool, redis, job_id, f"Internal pipeline execution error: {e}")


async def run_job_with_semaphore(job_id: str, redis: aioredis.Redis, pool, http_client, worker_name: str, queue_name: str):
    sem = fast_concurrency_semaphore if queue_name == "job_queue_fast" else slow_concurrency_semaphore
    async with sem:
        await publish_status(redis, job_id, "spawning_agents", "Spawning fact-checking agents...")
        await log_lifecycle_async(pool, job_id, "TASK_DISPATCHED", details={"worker": worker_name})
        
        # Track task in cancellation registry
        active_tasks[job_id] = asyncio.current_task()
        
        # Spawn heartbeat reporter task
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(heartbeat_reporter(job_id, redis, stop_event))
        
        try:
            await process_job(job_id, redis, pool, http_client)
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            active_tasks.pop(job_id, None)
            try:
                await redis.delete(f"job:{job_id}:heartbeat")
            except Exception:
                pass


async def job_worker(app: FastAPI, queue_name: str = "job_queue_fast"):
    """BRPOP from the specified Redis queue and process each job_id asynchronously."""
    redis = app.state.redis
    pool = app.state.db_pool
    http_client = app.state.http_client
    logger.info("Worker started for queue: %s", queue_name)

    while True:
        try:
            result = await redis.brpop(queue_name, timeout=2)
            if result:
                _, job_id_bytes = result
                job_id = job_id_bytes.decode()
                logger.info("Worker (%s) picked up job: %s", queue_name, job_id)
                
                worker_name = asyncio.current_task().get_name()
                await log_lifecycle_async(pool, job_id, "JOB_ACCEPTED", details={"worker": worker_name})
                await log_lifecycle_async(pool, job_id, "WORKER_ASSIGNED", details={"worker": worker_name})
                
                await publish_status(redis, job_id, "accepted", "Job accepted by worker thread...")
                
                # Dispatch the task asynchronously
                asyncio.create_task(run_job_with_semaphore(job_id, redis, pool, http_client, worker_name, queue_name))
        except asyncio.CancelledError:
            logger.info("Worker (%s) cancelled", queue_name)
            break
        except Exception as e:
            logger.error("Worker (%s) error: %s", queue_name, e)
            await asyncio.sleep(1)
