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

# Phase 3: Replace global semaphore with per-worker concurrency control
class WorkerPool:
    """Manages a pool of workers with per-worker job distribution and concurrency control."""
    
    def __init__(self, worker_id: str, max_concurrent_jobs: int = 5):
        self.worker_id = worker_id
        self.max_concurrent_jobs = max_concurrent_jobs
        self.active_jobs = {}  # job_id -> task
        self.waiting_queue = []  # job_ids waiting for capacity
        self.lock = asyncio.Lock()
    
    async def acquire_slot(self, job_id: str) -> tuple[int, int]:
        """
        Acquire a slot for a job. Returns (queue_position, total_waiting).
        If no slots available, job waits in queue.
        """
        async with self.lock:
            if len(self.active_jobs) < self.max_concurrent_jobs:
                # Slot available immediately
                self.active_jobs[job_id] = None
                return 0, len(self.waiting_queue)
            else:
                # Add to waiting queue
                position = len(self.waiting_queue)
                self.waiting_queue.append(job_id)
                return position, len(self.waiting_queue)
    
    async def wait_for_slot(self, job_id: str) -> None:
        """Wait until a slot becomes available for this job."""
        async with self.lock:
            if job_id in self.active_jobs:
                # Already has a slot
                return
            if job_id not in self.waiting_queue:
                self.waiting_queue.append(job_id)
        
        # Wait for slot (check every 100ms)
        while True:
            await asyncio.sleep(0.1)
            async with self.lock:
                if job_id in self.active_jobs:
                    return
    
    async def release_slot(self, job_id: str) -> None:
        """Release a job's slot and promote the next waiting job."""
        async with self.lock:
            self.active_jobs.pop(job_id, None)
            
            # Promote waiting job if available
            if self.waiting_queue:
                next_job_id = self.waiting_queue.pop(0)
                self.active_jobs[next_job_id] = None
    
    def get_status(self) -> dict:
        """Return current worker status."""
        return {
            "worker_id": self.worker_id,
            "active_jobs": len(self.active_jobs),
            "max_concurrent": self.max_concurrent_jobs,
            "waiting_jobs": len(self.waiting_queue),
            "utilization_percent": int((len(self.active_jobs) / self.max_concurrent_jobs) * 100)
        }


# Global worker pools for fast and slow paths
fast_worker_pool = WorkerPool("fast-pool", max_concurrent_jobs=5)  # 3 workers × 5 jobs = 15 concurrent max
slow_worker_pool = WorkerPool("slow-pool", max_concurrent_jobs=2)  # 2 workers × 2 jobs = 4 concurrent max

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
    """Phase 3: Use per-worker pool instead of global semaphore."""
    worker_pool = fast_worker_pool if queue_name == "job_queue_fast" else slow_worker_pool
    
    # Try to acquire a slot immediately
    queue_pos, total_waiting = await worker_pool.acquire_slot(job_id)
    
    if queue_pos > 0:
        # Job is waiting in queue
        logger.info("[INSTRUMENTATION] Job %s WORKER_QUEUE_POSITION | Position: %d/%d | Worker: %s",
            job_id, queue_pos + 1, queue_pos + total_waiting + 1, worker_name)
        await publish_status(redis, job_id, "waiting", f"Position {queue_pos + 1} in worker queue (estimated wait: {(queue_pos + 1) * 30}s)")
        await log_lifecycle_async(pool, job_id, "WORKER_QUEUE_POSITION",
            details={"position": queue_pos + 1, "total_waiting": total_waiting + 1})
        
        # Wait for slot to become available
        slot_wait_start = time.perf_counter()
        await worker_pool.wait_for_slot(job_id)
        slot_wait_duration = time.perf_counter() - slot_wait_start
        logger.info("[INSTRUMENTATION] Job %s WORKER_SLOT_ACQUIRED | Wait duration: %.3fs | Worker: %s",
            job_id, slot_wait_duration, worker_name)
        await log_lifecycle_async(pool, job_id, "WORKER_SLOT_ACQUIRED",
            details={"wait_duration_ms": round(slot_wait_duration * 1000)})
    else:
        # Slot was available immediately
        logger.info("[INSTRUMENTATION] Job %s WORKER_SLOT_ACQUIRED | Immediate (no wait) | Worker: %s",
            job_id, worker_name)
    
    try:
        # Now we have a slot, initialize and execute
        await publish_status(redis, job_id, "initializing", "Initializing pipeline infrastructure...")
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
    finally:
        # Release slot so next waiting job can proceed
        await worker_pool.release_slot(job_id)
        logger.info("[INSTRUMENTATION] Job %s WORKER_SLOT_RELEASED | Worker: %s | Pool status: %s",
            job_id, worker_name, worker_pool.get_status())


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
