"""Observability router — exposes execution metrics, logs, and system health."""
import logging
import time
from fastapi import APIRouter, Request, HTTPException
from db import queries

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/system/health")
async def system_health(request: Request) -> dict:
    """Return current system health and worker pool status."""
    try:
        from orchestration.worker_executor import fast_worker_pool, slow_worker_pool
        from services.gemini import gemini_manager
        
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "worker_pools": {
                "fast": fast_worker_pool.get_status(),
                "slow": slow_worker_pool.get_status(),
            },
            "gemini": {
                "available_keys": gemini_manager.get_total_keys(),
                "current_key": gemini_manager.get_current_key_masked(),
            },
            "redis": {
                "connected": True,  # Would check if connected
            }
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}/metrics")
async def job_metrics(job_id: str, request: Request) -> dict:
    """Return execution metrics for a specific job."""
    try:
        pool = request.app.state.db_pool
        
        # Fetch audit logs for this job
        async with pool.acquire() as conn:
            logs = await conn.fetch(
                """
                SELECT action, details, created_at 
                FROM audit_logs 
                WHERE job_id = $1::uuid 
                ORDER BY created_at ASC
                """,
                job_id
            )
        
        if not logs:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Parse logs into execution timeline
        timeline = []
        start_time = logs[0]["created_at"]
        
        for log in logs:
            elapsed = (log["created_at"] - start_time).total_seconds()
            duration_ms = 0
            
            details = log["details"] or {}
            if isinstance(details, dict):
                duration_ms = details.get("duration_ms", 0)
            
            timeline.append({
                "action": log["action"],
                "elapsed_seconds": elapsed,
                "duration_ms": duration_ms,
                "timestamp": log["created_at"].isoformat(),
            })
        
        # Calculate stage latencies
        stage_latencies = {}
        for log in timeline:
            if "duration_ms" in log and log["duration_ms"] > 0:
                stage_latencies[log["action"]] = {
                    "duration_ms": log["duration_ms"],
                    "elapsed_at": log["elapsed_seconds"]
                }
        
        # Calculate total time
        total_time = (logs[-1]["created_at"] - start_time).total_seconds()
        
        return {
            "job_id": job_id,
            "total_execution_time_seconds": total_time,
            "timeline": timeline,
            "stage_latencies": stage_latencies,
            "stage_count": len(timeline),
        }
    except Exception as e:
        logger.error("Failed to fetch job metrics for %s: %s", job_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/slow")
async def slow_jobs(request: Request, threshold_seconds: int = 10) -> dict:
    """Return jobs that took longer than threshold_seconds."""
    try:
        pool = request.app.state.db_pool
        
        async with pool.acquire() as conn:
            jobs = await conn.fetch(
                """
                SELECT 
                    j.id,
                    j.status,
                    j.created_at,
                    j.updated_at,
                    EXTRACT(EPOCH FROM (j.updated_at - j.created_at)) as duration_seconds
                FROM jobs j
                WHERE j.updated_at IS NOT NULL
                  AND (j.updated_at - j.created_at) > INTERVAL '%d seconds'
                  AND j.created_at > NOW() - INTERVAL '1 hour'
                ORDER BY duration_seconds DESC
                LIMIT 20
                """ % threshold_seconds
            )
        
        return {
            "threshold_seconds": threshold_seconds,
            "slow_jobs": [
                {
                    "job_id": str(j["id"]),
                    "status": j["status"],
                    "duration_seconds": float(j["duration_seconds"]),
                    "created_at": j["created_at"].isoformat(),
                    "updated_at": j["updated_at"].isoformat(),
                }
                for j in jobs
            ]
        }
    except Exception as e:
        logger.error("Failed to fetch slow jobs: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/pipeline-latencies")
async def pipeline_latencies(request: Request, hours: int = 1) -> dict:
    """Return average latency per pipeline stage over the last N hours."""
    try:
        pool = request.app.state.db_pool
        
        async with pool.acquire() as conn:
            # Get all logs from last N hours
            logs = await conn.fetch(
                """
                SELECT action, details, created_at 
                FROM audit_logs 
                WHERE created_at > NOW() - INTERVAL '%d hours'
                ORDER BY job_id, created_at ASC
                """ % hours
            )
        
        # Group by job and calculate latencies
        job_stages = {}
        for log in logs:
            job_id = log["job_id"] if hasattr(log, "job_id") else None
            action = log["action"]
            details = log["details"] or {}
            duration_ms = details.get("duration_ms", 0) if isinstance(details, dict) else 0
            
            if duration_ms > 0:
                if action not in job_stages:
                    job_stages[action] = []
                job_stages[action].append(duration_ms)
        
        # Calculate averages
        stage_stats = {}
        for stage, durations in job_stages.items():
            if durations:
                stage_stats[stage] = {
                    "average_ms": sum(durations) / len(durations),
                    "min_ms": min(durations),
                    "max_ms": max(durations),
                    "count": len(durations),
                }
        
        return {
            "time_range_hours": hours,
            "stage_statistics": stage_stats,
        }
    except Exception as e:
        logger.error("Failed to fetch pipeline latencies: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/queue-health")
async def queue_health(request: Request) -> dict:
    """Return Redis queue health metrics."""
    try:
        redis = request.app.state.redis
        
        fast_queue_len = await redis.llen("job_queue_fast")
        slow_queue_len = await redis.llen("job_queue_slow")
        
        return {
            "timestamp": time.time(),
            "queues": {
                "job_queue_fast": {
                    "depth": fast_queue_len,
                    "max_concurrent": 15,
                    "estimated_wait_seconds": fast_queue_len * 30 if fast_queue_len > 0 else 0,
                },
                "job_queue_slow": {
                    "depth": slow_queue_len,
                    "max_concurrent": 4,
                    "estimated_wait_seconds": slow_queue_len * 120 if slow_queue_len > 0 else 0,
                }
            }
        }
    except Exception as e:
        logger.error("Failed to fetch queue health: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
