"""Redis pub/sub publisher helpers."""
import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


async def publish_event(redis: aioredis.Redis, job_id: str, event_type: str, data: Any) -> None:
    """Publish a structured SSE event to a job's Redis channel."""
    channel = f"job:{job_id}:events"
    payload = json.dumps({"type": event_type, "data": data})
    try:
        await redis.publish(channel, payload)
        logger.debug("Published event type=%s to channel=%s", event_type, channel)
    except Exception as e:
        logger.error("Failed to publish event to %s: %s", channel, e)


async def publish_status(redis: aioredis.Redis, job_id: str, stage: str, message: str = "") -> None:
    await publish_event(redis, job_id, "status", {"stage": stage, "message": message})


async def publish_error(redis: aioredis.Redis, job_id: str, message: str) -> None:
    await publish_event(redis, job_id, "error", {"message": message})


async def publish_done(redis: aioredis.Redis, job_id: str) -> None:
    await publish_event(redis, job_id, "done", {})
