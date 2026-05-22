"""Web search using SerpAPI (primary) and Brave Search (fallback)."""
import logging
from typing import List, Optional
import httpx

from config import settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


async def search_web(query: str, max_results: int = 10) -> List[dict]:
    """
    Search using SerpAPI first, fall back to Brave if quota exceeded or error.
    Returns a list of result dicts: {url, title, snippet, rank}.
    """
    results = await _search_serpapi(query, max_results)
    if not results:
        logger.info("SerpAPI returned no results, falling back to Brave Search")
        results = await _search_brave(query, max_results)
    return results


async def _search_serpapi(query: str, max_results: int) -> List[dict]:
    if not settings.serpapi_key or settings.serpapi_key == "replace-me":
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(SERPAPI_URL, params={
                "q": query,
                "api_key": settings.serpapi_key,
                "num": max_results,
                "hl": "en",
                "gl": "us",
            })
            if response.status_code == 429:
                logger.warning("SerpAPI quota exceeded")
                return []
            response.raise_for_status()
            data = response.json()
            organic = data.get("organic_results", [])
            return [
                {
                    "url": r.get("link", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "rank": i + 1,
                }
                for i, r in enumerate(organic[:max_results])
                if r.get("link")
            ]
    except Exception as e:
        logger.error("SerpAPI search failed: %s", e)
        return []


async def _search_brave(query: str, max_results: int) -> List[dict]:
    if not settings.brave_api_key or settings.brave_api_key == "replace-me":
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                BRAVE_URL,
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": settings.brave_api_key,
                },
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("web", {}).get("results", [])
            return [
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("description", ""),
                    "rank": i + 1,
                }
                for i, r in enumerate(results[:max_results])
                if r.get("url")
            ]
    except Exception as e:
        logger.error("Brave Search failed: %s", e)
        return []


def build_claim_query(claim_text: str, claim_type: Optional[str] = None) -> str:
    """Build an optimized search query for a claim."""
    base = claim_text.strip()
    if len(base) > 200:
        base = base[:200]

    if claim_type == "statistic":
        return f'"{base}" site:gov OR site:edu OR reuters.com OR apnews.com'
    elif claim_type == "event":
        return f'"{base}" fact check'
    elif claim_type == "attribution":
        return f'"{base}" statement'
    else:
        return base
