"""Internal router — receives jobs dispatched from Spring Boot."""
import logging
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
        await queries.insert_audit_log(pool, body.job_id, body.user_id, "QUEUE_ENQUEUED", {"elapsed_seconds": 0.0})
        logger.info("[LIFECYCLE] [JOB_ID: %s] [ACTION: QUEUE_ENQUEUED]", body.job_id)

        await request.app.state.redis.lpush("job_queue", body.job_id)
        logger.info("Job %s queued from Spring Boot", body.job_id)
        return {"job_id": body.job_id, "queued": True}
    except Exception as e:
        logger.error("Failed to queue job %s: %s", body.job_id, e)
        raise HTTPException(status_code=500, detail="Failed to queue job")
