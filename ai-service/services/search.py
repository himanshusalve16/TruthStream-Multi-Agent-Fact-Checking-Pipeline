"""
Web search: SerpAPI (primary) → DuckDuckGo (free fallback) → Bing (last resort).

Key improvements over previous version:
- build_claim_query() removed site-operator restrictions that killed DDG recall.
- build_fallback_query() provides a broader 2nd-pass query when the primary fails.
- search_web_with_fallback() chains primary → fallback → Bing automatically.
- DDG parser tries multiple selectors and logs result counts for diagnostics.
- Bing search added as a no-API-key third engine.
"""
import logging
import re
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
BING_SEARCH_URL = "https://www.bing.com/search"
BOT_USER_AGENT = "Mozilla/5.0 (compatible; TruthStream-Bot/1.0; +https://truthstream.app/bot)"

# Stop-words for query trimming
_STOP = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "for", "of", "with", "by", "that", "this",
    "it", "as", "from", "has", "have", "had", "be", "been", "being",
    "which", "who", "whose", "when", "where", "how", "its", "their",
}


# ─────────────────────────────────────────────────────────────────────────────
# Query builders
# ─────────────────────────────────────────────────────────────────────────────

def build_claim_query(claim_text: str, claim_type: Optional[str] = None) -> str:
    """
    Build the PRIMARY search query for a claim.

    Old behaviour (removed):
      - site:gov OR site:edu restrictions → killed DDG recall for non-US topics
      - appending 'fact check' → returned fact-check index pages, not evidence
      - using raw 200-char claim verbatim → DDG returned nothing

    New behaviour:
      - Extract the most informative 10 content words (no stop-words)
      - Surround with double-quotes for phrase-search when short enough
      - Add a gentle type-specific suffix that broadens rather than narrows
    """
    # Remove existing quotes and collapse whitespace
    base = re.sub(r'["""\']+', '', claim_text.strip())
    base = re.sub(r'\s+', ' ', base)

    # Extract content words (drop stop-words, keep capitalized words first)
    words = base.split()
    content_words = [w for w in words if w.lower() not in _STOP and len(w) > 2]
    # Prefer capitalized (likely named entities) first
    capitalized = [w for w in content_words if w[0].isupper()]
    lowercase = [w for w in content_words if not w[0].isupper()]
    ranked = (capitalized + lowercase)[:12]

    if not ranked:
        # Pure fallback: use first 80 chars
        query_core = base[:80]
    elif len(ranked) <= 6:
        # Short enough to phrase-quote
        query_core = " ".join(ranked)
    else:
        # Use first 10 words without quotes (better recall)
        query_core = " ".join(ranked[:10])

    # Soft type suffix — broadens rather than narrows
    if claim_type == "statistic":
        suffix = "data report"
    elif claim_type == "event":
        suffix = "news"
    elif claim_type == "attribution":
        suffix = "statement"
    else:
        suffix = ""

    query = f"{query_core} {suffix}".strip()
    logger.debug("[SEARCH] Primary query: %s", query)
    return query


def build_fallback_query(claim_text: str) -> str:
    """
    Build a BROADER fallback query when the primary returns < 3 results.
    Uses only the first 5 capitalized words (named entities + key nouns).
    """
    base = re.sub(r'["""\']+', '', claim_text.strip())
    words = base.split()
    # Grab first 5 words that start with uppercase — they're usually the core topic
    entities = [w.strip(".,;:()[]") for w in words if w and w[0].isupper()][:5]
    if len(entities) >= 2:
        query = " ".join(entities)
    else:
        # Fall back to first 60 chars of claim, no operators
        query = re.sub(r'\s+', ' ', base)[:60]
    logger.debug("[SEARCH] Fallback query: %s", query)
    return query


# ─────────────────────────────────────────────────────────────────────────────
# Primary search orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def search_web(
    query: str,
    max_results: int = 10,
    redis=None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[dict]:
    """
    Search using SerpAPI when configured, otherwise DuckDuckGo.
    Falls back to Bing if both return nothing.
    Uses Redis to cache results by query hash.
    Returns: [{url, title, snippet, rank}, ...]
    """
    import hashlib, json

    query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
    cache_key = f"search:{query_hash}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.debug("[SEARCH] Cache hit for: %s", query[:60])
                return json.loads(cached.decode())
        except Exception as e:
            logger.warning("[SEARCH] Cache read error: %s", e)

    results: List[dict] = []

    # 1. SerpAPI (if configured)
    if _serpapi_configured():
        results = await _search_serpapi(query, max_results, http_client)
        if results:
            logger.info("[SEARCH] SerpAPI returned %d results for: %s", len(results), query[:60])

    # 2. DuckDuckGo fallback
    if not results:
        if _serpapi_configured():
            logger.info("[SEARCH] SerpAPI returned 0 results → trying DuckDuckGo: %s", query[:60])
        else:
            logger.info("[SEARCH] SerpAPI not configured → using DuckDuckGo: %s", query[:60])
        results = await _search_duckduckgo(query, max_results, http_client)
        if results:
            logger.info("[SEARCH] DuckDuckGo returned %d results for: %s", len(results), query[:60])

    # 3. Bing last-resort fallback
    if not results:
        logger.info("[SEARCH] DuckDuckGo returned 0 → trying Bing: %s", query[:60])
        results = await _search_bing(query, max_results, http_client)
        if results:
            logger.info("[SEARCH] Bing returned %d results for: %s", len(results), query[:60])
        else:
            logger.warning("[SEARCH] All engines returned 0 results for: %s", query[:60])

    if redis and results:
        try:
            await redis.setex(cache_key, 7200, json.dumps(results))
        except Exception as e:
            logger.warning("[SEARCH] Cache write error: %s", e)

    return results


async def search_web_with_fallback(
    primary_query: str,
    fallback_query: str,
    max_results: int = 10,
    redis=None,
    http_client: Optional[httpx.AsyncClient] = None,
    min_primary_results: int = 3,
) -> tuple[List[dict], str]:
    """
    Try primary query first. If fewer than min_primary_results are returned,
    try the fallback query and merge any additional unique URLs.

    Returns: (results_list, query_used_str)
    """
    results = await search_web(primary_query, max_results, redis, http_client)
    query_used = primary_query

    if len(results) < min_primary_results:
        logger.info(
            "[SEARCH] Primary query returned %d results (< %d threshold) → trying fallback: %s",
            len(results), min_primary_results, fallback_query[:60]
        )
        fallback_results = await search_web(fallback_query, max_results, redis, http_client)
        if fallback_results:
            # Merge: add fallback results whose URLs aren't already present
            seen_urls = {r["url"] for r in results}
            for r in fallback_results:
                if r["url"] not in seen_urls:
                    results.append(r)
                    seen_urls.add(r["url"])
            query_used = f"{primary_query} + fallback: {fallback_query}"
            logger.info(
                "[SEARCH] After fallback merge: %d total results", len(results)
            )

    return results, query_used


# ─────────────────────────────────────────────────────────────────────────────
# Search engine implementations
# ─────────────────────────────────────────────────────────────────────────────

def _serpapi_configured() -> bool:
    key = settings.serpapi_key
    return bool(key and key not in ("replace-me", ""))


async def _search_serpapi(
    query: str, max_results: int, http_client: Optional[httpx.AsyncClient] = None
) -> List[dict]:
    try:
        params = {
            "q": query,
            "api_key": settings.serpapi_key,
            "num": max_results,
            "hl": "en",
            "gl": "us",
        }
        if http_client is not None:
            response = await http_client.get(SERPAPI_URL, params=params, timeout=15.0)
        else:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(SERPAPI_URL, params=params)

        if response.status_code == 429:
            logger.warning("[SEARCH] SerpAPI quota exceeded")
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
        logger.error("[SEARCH] SerpAPI failed: %s", e)
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


async def _search_duckduckgo(
    query: str, max_results: int, http_client: Optional[httpx.AsyncClient] = None
) -> List[dict]:
    """
    Free web search via DuckDuckGo HTML endpoint.
    Tries POST first; falls back to GET if DDG blocks the bot POST.
    Tries multiple CSS selectors to handle layout changes.
    """
    headers = {
        "User-Agent": BOT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    html_text = None

    # Attempt 1: POST (standard)
    try:
        if http_client is not None:
            resp = await http_client.post(
                DDG_HTML_URL,
                data={"q": query, "b": ""},
                headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=8.0,
            )
        else:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.post(
                    DDG_HTML_URL,
                    data={"q": query, "b": ""},
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                )
        if resp.status_code == 200:
            html_text = resp.text
        else:
            logger.warning("[SEARCH] DDG POST returned HTTP %d", resp.status_code)
    except Exception as e:
        logger.warning("[SEARCH] DDG POST failed: %s", e)

    # Attempt 2: GET fallback if POST failed or was blocked
    if not html_text:
        try:
            get_url = f"https://duckduckgo.com/html/?q={httpx.QueryParams({'q': query})}"
            if http_client is not None:
                resp = await http_client.get(get_url, headers=headers, timeout=8.0)
            else:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                    resp = await client.get(get_url, headers=headers)
            if resp.status_code == 200:
                html_text = resp.text
                logger.info("[SEARCH] DDG GET fallback succeeded")
            else:
                logger.warning("[SEARCH] DDG GET also returned HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("[SEARCH] DDG GET fallback failed: %s", e)

    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "lxml")
    results: List[dict] = []

    # Try multiple selector patterns — DDG changes layout periodically
    selector_pairs = [
        ("div.result", "a.result__a", "a.result__snippet, div.result__snippet"),
        ("div.results_links", "a.result__a", "a.result__snippet"),
        ("div.web-result", "a.result__url", "div.result__snippet"),
        ("li.results_links_deep", "h2 a", "div.result__snippet"),
    ]

    for block_sel, link_sel, snippet_sel in selector_pairs:
        blocks = soup.select(block_sel)
        if not blocks:
            continue
        for block in blocks:
            if len(results) >= max_results:
                break
            link_el = block.select_one(link_sel)
            snippet_el = block.select_one(snippet_sel)
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
        if results:
            logger.debug("[SEARCH] DDG selector '%s' matched %d results", block_sel, len(results))
            break  # Stop trying more selectors once one works

    if not results:
        logger.warning("[SEARCH] DDG: all selectors returned 0 results (layout may have changed)")

    return results


async def _search_bing(
    query: str, max_results: int, http_client: Optional[httpx.AsyncClient] = None
) -> List[dict]:
    """
    Bing web search via HTML scraping — no API key required.
    Used only as a last-resort fallback when both SerpAPI and DDG return nothing.
    """
    headers = {
        "User-Agent": BOT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        params = {"q": query, "count": str(max_results), "setlang": "en"}
        if http_client is not None:
            resp = await http_client.get(BING_SEARCH_URL, params=params, headers=headers, timeout=8.0)
        else:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(BING_SEARCH_URL, params=params, headers=headers)

        if resp.status_code != 200:
            logger.warning("[SEARCH] Bing returned HTTP %d", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results: List[dict] = []

        for item in soup.select("li.b_algo"):
            if len(results) >= max_results:
                break
            link_el = item.select_one("h2 a")
            snippet_el = item.select_one("div.b_caption p, p.b_algoSlug, div.b_snippet")
            if not link_el:
                continue
            url = link_el.get("href", "")
            if not url.startswith("http"):
                continue
            results.append({
                "url": url,
                "title": link_el.get_text(strip=True),
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                "rank": len(results) + 1,
            })

        logger.debug("[SEARCH] Bing returned %d results for: %s", len(results), query[:60])
        return results

    except Exception as e:
        logger.error("[SEARCH] Bing search failed: %s", e)
        return []
