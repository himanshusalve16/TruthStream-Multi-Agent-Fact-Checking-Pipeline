"""Gemini embedding service."""
import logging
from typing import List

from google import genai
from services.gemini import gemini_manager, execute_gemini_call

logger = logging.getLogger(__name__)


def get_gemini_client() -> genai.Client:
    """Returns the currently active Gemini client from the manager."""
    return gemini_manager.get_client()


async def embed_text(text: str) -> List[float]:
    """Compute Gemini text-embedding-004 embedding for a string with fallback."""
    async def call_embed(client: genai.Client):
        return await client.aio.models.embed_content(
            model="text-embedding-004",
            contents=text[:8000],  # embedding model has token limit
        )

    try:
        response = await execute_gemini_call(call_embed)
        return response.embeddings[0].values
    except Exception as e:
        logger.error("Embedding failed: %s", e)
        return []


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts. Falls back to empty lists on error."""
    async def call_embed(client: genai.Client):
        return await client.aio.models.embed_content(
            model="text-embedding-004",
            contents=[t[:8000] for t in texts],
        )

    try:
        response = await execute_gemini_call(call_embed)
        return [item.values for item in response.embeddings]
    except Exception as e:
        logger.error("Batch embedding failed: %s", e)
        return [[] for _ in texts]
