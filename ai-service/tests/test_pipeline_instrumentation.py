import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from orchestration.pipeline_router import route_and_execute_pipeline, log_lifecycle_async
from services.gemini import provider_registry

@pytest.mark.asyncio
async def test_ready_endpoint_no_unbound_local(monkeypatch):
    """Verify that the ready endpoint does not fail with UnboundLocalError when provider is degraded."""
    from main import ready
    
    # Mock provider availability
    monkeypatch.setattr(provider_registry, "available", False)
    monkeypatch.setattr(provider_registry, "cooldown_until", 9999999999.0)
    
    # Mock request and app state
    mock_app_state = MagicMock()
    mock_app_state.is_ready = True
    
    # Setup mock redis ping
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_app_state.redis = mock_redis
    
    # Setup mock db pool
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_db_pool = AsyncMock()
    mock_db_pool.acquire = MagicMock()
    mock_db_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_db_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_app_state.db_pool = mock_db_pool
    
    # Setup mock workers
    mock_worker = MagicMock()
    mock_worker.done = MagicMock(return_value=False)
    mock_app_state.workers = [mock_worker]
    
    mock_request = MagicMock()
    mock_request.app.state = mock_app_state
    
    # Call the endpoint
    response = await ready(mock_request)
    
    # Verify we got a 503 degraded status and not an UnboundLocalError
    assert response.status_code == 503
    data = json.loads(response.body.decode())
    assert data["status"] == "degraded"
    assert "AI Capacity Limited" in data["details"]

@pytest.mark.asyncio
async def test_route_and_execute_pipeline_no_unbound_local(monkeypatch):
    """Verify that the pipeline router does not fail with UnboundLocalError when provider is degraded."""
    # Mock provider registry to be degraded
    monkeypatch.setattr(provider_registry, "available", False)
    monkeypatch.setattr(provider_registry, "cooldown_until", 9999999999.0)
    
    mock_redis = AsyncMock()
    
    # Setup mock db pool supporting async context manager for pool.acquire()
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    
    mock_client = AsyncMock()
    
    # Mock get_job query to return a fake text-based job
    fake_job = {
        "user_id": "00000000-0000-0000-0000-000000000000",
        "input_url": None,
        "input_text": "This is a sample factual claim to check. It contains more than enough words to classify and is long enough to bypass the length checks in the pipeline router.",
        "created_at": None
    }
    
    # Mock functions that pipeline_router uses
    with patch("orchestration.pipeline_router.queries.get_job", new_callable=AsyncMock, return_value=fake_job) as mock_get_job, \
         patch("orchestration.pipeline_router.queries.update_job_status", new_callable=AsyncMock) as mock_update_status, \
         patch("orchestration.pipeline_router.queries.insert_audit_log", new_callable=AsyncMock) as mock_audit, \
         patch("orchestration.pipeline_router.publish_status", new_callable=AsyncMock) as mock_pub_status, \
         patch("orchestration.pipeline_router.classify_article_complexity", return_value="standard"), \
         patch("orchestration.pipeline_router.run_recovery_pipeline_flow", new_callable=AsyncMock) as mock_recovery:
        
        # This shouldn't raise any UnboundLocalError
        await route_and_execute_pipeline("test-job-id", mock_redis, mock_pool, mock_client)
        
        mock_get_job.assert_awaited()
        mock_recovery.assert_awaited()

@pytest.mark.asyncio
async def test_log_lifecycle_async():
    """Verify log_lifecycle_async executes and inserts into audit logs correctly."""
    mock_pool = MagicMock()
    
    with patch("orchestration.pipeline_router.queries.insert_audit_log", new_callable=AsyncMock) as mock_insert:
        await log_lifecycle_async(mock_pool, "test-job-id", "TEST_ACTION", details={"x": 1})
        mock_insert.assert_awaited_once_with(mock_pool, "test-job-id", None, "TEST_ACTION", {"x": 1})


@pytest.mark.asyncio
async def test_health_endpoint(monkeypatch):
    """Verify that the health endpoint returns degraded if provider availability check fails."""
    from main import health
    import time
    
    # Test healthy/online status
    monkeypatch.setattr(provider_registry, "available", True)
    monkeypatch.setattr(provider_registry, "cooldown_until", 0.0)
    res_healthy = await health()
    assert res_healthy == {"status": "ok"}
    
    # Test degraded status
    monkeypatch.setattr(provider_registry, "available", False)
    monkeypatch.setattr(provider_registry, "cooldown_until", time.time() + 1000)
    res_degraded = await health()
    assert res_degraded == {"status": "degraded"}

