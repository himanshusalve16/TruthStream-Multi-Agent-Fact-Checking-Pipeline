"""Web search: SerpAPI (primary, optional) and DuckDuckGo HTML (free fallback, no API key)."""
import logging
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
BOT_USER_AGENT = "TruthStream-Bot/1.0 (+https://truthstream.app/bot)"


async def search_web(query: str, max_results: int = 10, redis=None) -> List[dict]:
    """
    Search using SerpAPI when configured, otherwise DuckDuckGo.
    If SerpAPI fails or returns nothing, fall back to DuckDuckGo (no API key).
    Uses Redis to cache results by query hash.
    Returns: [{url, title, snippet, rank}, ...]
    """
    if redis:
        import hashlib
        import json
        query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()
        cache_key = f"search:{query_hash}"
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.info("Search cache hit for query: %s", query)
                return json.loads(cached.decode())
        except Exception as e:
            logger.warning("Failed to read search cache: %s", e)

    results: List[dict] = []
    if _serpapi_configured():
        results = await _search_serpapi(query, max_results)
    if not results:
        if _serpapi_configured():
            logger.info("SerpAPI returned no results, falling back to DuckDuckGo")
        else:
            logger.info("SerpAPI not configured, using DuckDuckGo search")
        results = await _search_duckduckgo(query, max_results)

    if redis and results:
        try:
            import json
            # Cache search results for 2 hours (7200 seconds)
            await redis.setex(cache_key, 7200, json.dumps(results))
        except Exception as e:
            logger.warning("Failed to write search cache: %s", e)

    return results


def _serpapi_configured() -> bool:
    key = settings.serpapi_key
    return bool(key and key not in ("replace-me", ""))


async def _search_serpapi(query: str, max_results: int) -> List[dict]:
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


def _normalize_ddg_url(href: str) -> str:
    """DuckDuckGo HTML results often use redirect URLs."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path == "/l/":
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else href
    return href


async def _search_duckduckgo(query: str, max_results: int) -> List[dict]:
    """
    Free web search via DuckDuckGo HTML endpoint — no API key required.
    Uses httpx + BeautifulSoup (same stack as the article scraper).
    """
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.post(
                DDG_HTML_URL,
                data={"q": query, "b": ""},
                headers={
                    "User-Agent": BOT_USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            if response.status_code != 200:
                logger.warning("DuckDuckGo HTTP %s", response.status_code)
                return []

            soup = BeautifulSoup(response.text, "lxml")
            results: List[dict] = []

            for block in soup.select("div.result"):
                if len(results) >= max_results:
                    break
                link_el = block.select_one("a.result__a")
                snippet_el = block.select_one("a.result__snippet, div.result__snippet")
                if not link_el:
                    continue
                url = _normalize_ddg_url(link_el.get("href", ""))
                if not url.startswith("http"):
                    continue
                results.append({
                    "url": url,
                    "title": link_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    "rank": len(results) + 1,
                })

            return results
    except Exception as e:
        logger.error("DuckDuckGo search failed: %s", e)
        return []


def build_claim_query(claim_text: str, claim_type: Optional[str] = None) -> str:
    """Build an optimized search query for a claim."""
    base = claim_text.strip()
    # Remove any existing double quotes to avoid syntax issues in search engines
    base = base.replace('"', '')
    if len(base) > 200:
        base = base[:200]

    if claim_type == "statistic":
        return f'{base} site:gov OR site:edu OR reuters.com OR apnews.com'
    elif claim_type == "event":
        return f'{base} fact check'
    elif claim_type == "attribution":
        return f'{base} statement'
    else:
        return base
