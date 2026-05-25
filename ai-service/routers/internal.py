"""Internal router — receives jobs dispatched from Spring Boot."""
import logging
import time
from fastapi import APIRouter, Request, HTTPException, Header
from config import settings
from models.schemas import JobDispatch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs", status_code=202)
async def dispatch_job(
        body: JobDispatch,
        request: Request,
        x_internal_secret: str = Header(alias="X-Internal-Secret"),
) -> dict:
    """Validate the internal secret, then push the job_id to the Redis queue."""
    if x_internal_secret != settings.internal_api_secret:
        logger.warning("Invalid X-Internal-Secret header from %s", request.client.host)
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        from db import queries
        pool = request.app.state.db_pool
        
        # Log queue enqueue
        enqueue_start = time.perf_counter()
        await queries.insert_audit_log(pool, body.job_id, body.user_id, "QUEUE_ENQUEUED", {"elapsed_seconds": 0.0})
        logger.info("[INSTRUMENTATION] Job %s QUEUE_ENQUEUED | From Spring Boot: %s", body.job_id, request.client.host)

        # Determine target queue based on input type and length
        is_fast_path = False
        if body.input_type == "text" and body.text:
            word_count = len(body.text.split())
            is_fast_path = word_count < 600
            logger.info("[INSTRUMENTATION] Job %s QUEUE_DECISION | Type: text | Words: %d | Path: %s",
                body.job_id, word_count, "fast" if is_fast_path else "slow")
        else:
            logger.info("[INSTRUMENTATION] Job %s QUEUE_DECISION | Type: %s | Path: slow",
                body.job_id, body.input_type)

        target_queue = "job_queue_fast" if is_fast_path else "job_queue_slow"

        await request.app.state.redis.lpush(target_queue, body.job_id)
        enqueue_duration = time.perf_counter() - enqueue_start
        logger.info("[INSTRUMENTATION] Job %s QUEUED | Queue: %s | Enqueue duration: %.3fs",
            body.job_id, target_queue, enqueue_duration)
        
        return {"job_id": body.job_id, "queued": True}
    except Exception as e:
        logger.error("Failed to queue job %s: %s", body.job_id, e)
        raise HTTPException(status_code=500, detail="Failed to queue job")

