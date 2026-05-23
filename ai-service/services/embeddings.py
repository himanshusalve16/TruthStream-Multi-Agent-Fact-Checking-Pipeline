"""Gemini embedding service."""
import logging
from typing import List

from google import genai
from config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def embed_text(text: str) -> List[float]:
    """Compute Gemini text-embedding-004 embedding for a string."""
    client = get_gemini_client()
    try:
        response = await client.aio.models.embed_content(
            model="text-embedding-004",
            contents=text[:8000],  # embedding model has token limit
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return []


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts. Falls back to empty lists on error."""
    client = get_gemini_client()
    try:
        response = await client.aio.models.embed_content(
            model="text-embedding-004",
            contents=[t[:8000] for t in texts],
        )
        return [item.values for item in response.embeddings]
    except Exception as e:
        logger.error("Batch embedding failed: %s", e)
        return [[] for _ in texts]
