"""OpenAI embedding service."""
import logging
from typing import List

from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def embed_text(text: str) -> List[float]:
    """Compute OpenAI text-embedding-3-small embedding for a string."""
    client = get_openai_client()
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=text[:8000],  # embedding model has token limit
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return []


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts. Falls back to empty lists on error."""
    client = get_openai_client()
    try:
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=[t[:8000] for t in texts],
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error("Batch embedding failed: %s", e)
        return [[] for _ in texts]
