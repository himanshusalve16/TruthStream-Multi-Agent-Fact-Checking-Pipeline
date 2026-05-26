import pytest
import requests
from services.gemini import execute_gemini_call, gemini_manager, job_id_var, job_call_counter, provider_registry
from google.genai import errors

@pytest.mark.anyio
async def test_execute_gemini_call_quota_exhaustion_raises_runtime_error():
    # Setup key and call counter
    job_id_var.set("test-job-123")
    job_call_counter.set(0)
    
    # Create requests.Response mock with RetryInfo details
    response = requests.Response()
    response.status_code = 429
    response._content = b'{"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED", "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "24s"}]}}'
    
    # Define a mock call function that always fails with a quota error
    async def call_always_fails(client):
        raise errors.APIError(code=429, response=response)

    # All API keys should fail and mark cooldown, eventually raising RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        await execute_gemini_call(call_always_fails)
    
    assert "AI provider quota temporarily exceeded or all keys failed" in str(exc_info.value)
    assert not provider_registry.check_availability()  # The circuit breaker must be activated

    # Reset circuit breaker
    provider_registry.cooldown_until = 0.0
    provider_registry.available = True
    gemini_manager._cooldowns = {}


@pytest.mark.anyio
async def test_execute_gemini_call_budgeting_cap():
    job_id_var.set("test-job-456")
    job_call_counter.set(15)  # Max budget reached

    async def call_valid(client):
        return "success"

    # Execution should fail immediately due to budget cap
    with pytest.raises(RuntimeError) as exc_info:
        await execute_gemini_call(call_valid)

    assert "AI request budget exceeded" in str(exc_info.value)
