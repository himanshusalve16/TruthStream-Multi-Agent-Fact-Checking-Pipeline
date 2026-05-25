import pytest
import json
from services.gemini import execute_gemini_call, MockResponse, MockEmbeddingResponse
from google.genai import errors

@pytest.mark.anyio
async def test_execute_gemini_call_fallback_quota_exceeded():
    # Define a mock call function that mimics call_bias_scorer and always fails
    async def call_bias_scorer(client):
        raise errors.APIError(message="Quota exceeded", code=429)

    # Execute the call, it should fallback to mock scorer response
    res = await execute_gemini_call(call_bias_scorer)
    
    assert isinstance(res, MockResponse)
    data = json.loads(res.text)
    assert data["bias_score"] == 35
    assert data["bias_direction"] == "neutral"

@pytest.mark.anyio
async def test_execute_gemini_call_fallback_generic_error():
    # Define a mock call function that mimics call_extractor and always fails
    async def call_extractor(client):
        raise ValueError("Generic API key failure")

    res = await execute_gemini_call(call_extractor)
    assert isinstance(res, MockResponse)
    data = json.loads(res.text)
    assert len(data["claims"]) == 2
    assert data["claims"][0]["claim_type"] == "event"

@pytest.mark.anyio
async def test_execute_gemini_call_fallback_embedding():
    # Define a mock call function that mimics call_embed and always fails
    async def call_embed(client):
        raise ValueError("Embedding generation error")

    res = await execute_gemini_call(call_embed)
    assert isinstance(res, MockEmbeddingResponse)
    assert len(res.embeddings) == 1
    assert len(res.embeddings[0].values) == 768
