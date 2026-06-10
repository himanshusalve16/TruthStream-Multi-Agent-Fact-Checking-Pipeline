"""
Web search: SerpAPI (primary) → DuckDuckGo (free fallback) → Bing (last resort).

Optimization additions:
- SerpAPI quota tracker: Redis daily counter + 429 exhaustion flag
  → saves calls by skipping SerpAPI when quota is blown
- build_article_queries(): generates 2-3 diverse, non-overlapping queries
  from article metadata (title phrase + entity + claim) instead of per-claim verbatim text
- max_results reduced from 15 → 8 (SerpAPI charges per search, not per result)
- search_web_with_fallback() unchanged but budget-aware via query_budget param
"""
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
BING_SEARCH_URL = "https://www.bing.com/search"
BOT_USER_AGENT = "Mozilla/5.0 (compatible; TruthStream-Bot/1.0; +https://truthstream.app/bot)"

# Redis keys for quota tracking
_QUOTA_DATE_KEY_PREFIX = "serpapi:calls:"   # + YYYY-MM-DD
_QUOTA_EXHAUSTED_KEY = "serpapi:quota_exhausted"
_QUOTA_EXHAUSTED_TTL = 3600                 # 1 hour before retrying after 429

# Stop-words for query trimming
_STOP = {
    # Grammar / Function words
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "in", "on", "at", "to", "for", "of", "with", "by", "that", "this",
    "it", "as", "from", "has", "have", "had", "be", "been", "being",
    "which", "who", "whose", "when", "where", "how", "its", "their",
    "said", "says", "will", "would", "could", "should", "may", "might",
    "also", "about", "after", "before", "during", "while", "since",
    # UI Junk / Scraper noise
    "home", "opinion", "wednesday", "monday", "tuesday", "thursday", 
    "friday", "saturday", "sunday", "menu", "login", "subscribe", 
    "navigation", "search", "advertisement", "newsletter", "sign",
    "today", "yesterday", "tomorrow", "news", "article",
}


# ─────────────────────────────────────────────────────────────────────────────
# SerpAPI Quota Tracker
# ─────────────────────────────────────────────────────────────────────────────

async def _record_serpapi_call(redis) -> int:
    """Increment daily SerpAPI call counter in Redis. Returns today's count."""
    if not redis:
        return 0
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"{_QUOTA_DATE_KEY_PREFIX}{today}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 90000)  # 25 hours TTL
        logger.info("[SEARCH] SerpAPI calls today: %d", count)
        return count
    except Exception as e:
        logger.warning("[SEARCH] Quota counter error: %s", e)
        return 0


async def _mark_serpapi_exhausted(redis) -> None:
    """Set a temporary Redis flag blocking SerpAPI for _QUOTA_EXHAUSTED_TTL seconds."""
    if not redis:
        return
    try:
        await redis.setex(_QUOTA_EXHAUSTED_KEY, _QUOTA_EXHAUSTED_TTL, "1")
        logger.warning("[SEARCH] SerpAPI quota exhausted — blocked for %ds", _QUOTA_EXHAUSTED_TTL)
    except Exception:
        pass


async def _is_serpapi_exhausted(redis) -> bool:
    """Return True if the quota-exhausted flag is set in Redis."""
    if not redis:
        return False
    try:
        val = await redis.get(_QUOTA_EXHAUSTED_KEY)
        return val is not None
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Query builders
# ─────────────────────────────────────────────────────────────────────────────

def _extract_content_words(text: str, max_words: int = 10) -> List[str]:
    """
    Extract the most informative content words from a text fragment.
    Capitalized words (likely named entities) are prioritized.
    """
    base = re.sub(r'["""\']+', '', text.strip())
    base = re.sub(r'\s+', ' ', base)
    words = base.split()
    content = [w.strip(".,;:()[]") for w in words
               if w.lower() not in _STOP and len(w) > 2 and w.strip(".,;:()[]")]
    capitalized = [w for w in content if w and w[0].isupper()]
    lowercase = [w for w in content if w and not w[0].isupper()]
    return (capitalized + lowercase)[:max_words]


def build_claim_query(claim_text: str, claim_type: Optional[str] = None) -> str:
    """
    Build the PRIMARY search query for a claim.
    Uses content-word extraction with capitalized-entity prioritization.
    Soft type suffix broadens rather than narrows recall.
    """
    ranked = _extract_content_words(claim_text, max_words=10)

    if not ranked:
        query_core = re.sub(r'\s+', ' ', claim_text.strip())[:80]
    elif len(ranked) <= 6:
        query_core = " ".join(ranked)
    else:
        query_core = " ".join(ranked[:10])

    suffix_map = {
        "statistic": "data report",
        "event": "news",
        "attribution": "statement",
    }
    suffix = suffix_map.get(claim_type or "", "")
    query = f"{query_core} {suffix}".strip()
    logger.debug("[SEARCH] Primary query: %s", query)
    return query


def build_fallback_query(claim_text: str) -> str:
    """
    Broader fallback: first 5 capitalized words (named entities).
    Falls back to first 60 chars of claim if <2 entities found.
    """
    base = re.sub(r'["""\']+', '', claim_text.strip())
    words = base.split()
    entities = [w.strip(".,;:()[]") for w in words if w and w[0].isupper()][:5]
    if len(entities) >= 2:
        query = " ".join(entities)
    else:
        query = re.sub(r'\s+', ' ', base)[:60]
    logger.debug("[SEARCH] Fallback query: %s", query)
    return query


def build_article_queries(
    article_text: str,
    article_url: Optional[str] = None,
    claims: Optional[list] = None,
    max_queries: int = 3,
) -> List[str]:
    """
    Generate 2-3 diverse, non-overlapping article-level search queries.

    Strategy (in priority order):
      Q1: Headline/title phrase — first sentence content words (≤8 words)
      Q2: Best claim's key entities + type suffix
      Q3: Date + org + topic keyword (event/statistic claims only)

    Deduplication: if Q2 shares >60% word overlap with Q1, it is skipped.
    This produces queries that cover different facets of the article with minimal redundancy.

    Returns a list of 1-3 query strings.
    """
    queries: List[str] = []
    used_word_sets: List[set] = []

    def _word_set(q: str) -> set:
        return set(re.findall(r'\w+', q.lower())) - _STOP

    def _too_similar(candidate: str) -> bool:
        """Return True if candidate overlaps >60% with any existing query."""
        cw = _word_set(candidate)
        if not cw:
            return True
        for existing_ws in used_word_sets:
            if not existing_ws:
                continue
            overlap = len(cw & existing_ws) / len(cw)
            if overlap > 0.60:
                return True
        return False

    def _add(q: str) -> bool:
        q = q.strip()
        if not q or len(q) < 5:
            return False
        if _too_similar(q):
            logger.debug("[SEARCH] Article query skipped (too similar): %s", q)
            return False
        queries.append(q)
        used_word_sets.append(_word_set(q))
        logger.debug("[SEARCH] Article query added: %s", q)
        return True

    # ── Q1: Headline / first sentence ────────────────────────────────────────
    first_sentences = re.split(r'[.!?\n]', article_text.strip())
    headline_candidate = ""
    for sent in first_sentences[:3]:
        sent = sent.strip()
        if len(sent.split()) >= 4:
            headline_candidate = sent
            break

    if headline_candidate:
        words = _extract_content_words(headline_candidate, max_words=8)
        if words:
            _add(" ".join(words))

    if len(queries) >= max_queries:
        return queries

    # ── Q2: Most checkable claim's key entities ──────────────────────────────
    if claims:
        # Pick the claim with highest checkability (high > medium > low)
        priority = {"high": 3, "medium": 2, "low": 1}
        best_claim = max(
            claims,
            key=lambda c: priority.get(getattr(c, "checkability", "") or "", 0),
            default=None,
        )
        if best_claim:
            q2_words = _extract_content_words(best_claim.text, max_words=8)
            ctype = getattr(best_claim, "claim_type", None)
            suffix = {"statistic": "data", "event": "news", "attribution": "statement"}.get(ctype or "", "")
            q2 = (" ".join(q2_words) + " " + suffix).strip()
            _add(q2)

    if len(queries) >= max_queries:
        return queries

    # ── Q3: Date + org + topic (for event/statistic claims) ──────────────────
    if claims:
        # Find a claim with a year and an entity
        year_pat = re.compile(r'\b(20\d\d|19\d\d)\b')
        for c in claims:
            text = c.text
            year_match = year_pat.search(text)
            if year_match:
                year = year_match.group(1)
                entities = [w.strip(".,;:()[]") for w in text.split()
                            if w and w[0].isupper() and w.lower() not in _STOP][:3]
                if entities:
                    q3 = f"{' '.join(entities)} {year}"
                    if _add(q3):
                        break

    # Last resort Q3: URL domain + article words
    if len(queries) < 2 and article_url:
        domain = re.sub(r'^https?://(www\.)?', '', article_url).split('/')[0]
        domain_words = domain.replace('.', ' ').replace('-', ' ')
        if len(queries) > 0:
            # Combine domain hint with Q1 topic words
            q3 = f"{domain_words} {queries[0][:40]}".strip()
            _add(q3)

    logger.info("[SEARCH] Generated %d article-level queries: %s", len(queries), queries)
    return queries[:max_queries]


# ─────────────────────────────────────────────────────────────────────────────
# Primary search orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def search_web(
    query: str,
    max_results: int = 8,
    redis=None,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[dict]:
    """
    Search: SerpAPI → DuckDuckGo → Bing.
    Uses Redis to cache by query hash (2h TTL).
    Tracks SerpAPI usage and respects quota-exhausted flag.
    Returns: [{url, title, snippet, rank}, ...]
    """
    query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
    cache_key = f"search:{query_hash}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                logger.info("[SEARCH] Cache hit for: %s", query[:60])
                return json.loads(cached.decode())
        except Exception as e:
            logger.warning("[SEARCH] Cache read error: %s", e)

    results: List[dict] = []

    # 1. SerpAPI (if configured and not quota-exhausted)
    if _serpapi_configured():
        if await _is_serpapi_exhausted(redis):
            logger.info("[SEARCH] SerpAPI quota flag set → skipping to DDG: %s", query[:60])
        else:
            results = await _search_serpapi(query, max_results, http_client, redis)
            if results:
                logger.info("[SEARCH] SerpAPI returned %d results for: %s", len(results), query[:60])

    # 2. DuckDuckGo fallback
    if not results:
        if _serpapi_configured():
            logger.info("[SEARCH] SerpAPI 0 results → trying DDG: %s", query[:60])
        else:
            logger.info("[SEARCH] SerpAPI not configured → using DDG: %s", query[:60])
        results = await _search_duckduckgo(query, max_results, http_client)
        if results:
            logger.info("[SEARCH] DDG returned %d results for: %s", len(results), query[:60])

    # 3. Bing last-resort fallback
    if not results:
        logger.info("[SEARCH] DDG 0 results → trying Bing: %s", query[:60])
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
    max_results: int = 8,
    redis=None,
    http_client: Optional[httpx.AsyncClient] = None,
    min_primary_results: int = 3,
    query_budget: int = 2,
) -> Tuple[List[dict], str]:
    """
    Try primary query; if < min_primary_results, try fallback and merge.
    Respects query_budget: budget=1 → primary only; budget>=2 → primary+fallback.
    Returns: (results_list, description_of_queries_used)
    """
    results = await search_web(primary_query, max_results, redis, http_client)
    query_used = primary_query

    if query_budget >= 2 and len(results) < min_primary_results:
        logger.info(
            "[SEARCH] Primary returned %d (< %d) → fallback (budget=%d): %s",
            len(results), min_primary_results, query_budget, fallback_query[:60]
        )
        fallback_results = await search_web(fallback_query, max_results, redis, http_client)
        if fallback_results:
            seen_urls = {r["url"] for r in results}
            for r in fallback_results:
                if r["url"] not in seen_urls:
                    results.append(r)
                    seen_urls.add(r["url"])
            query_used = f"{primary_query} + fallback:{fallback_query}"
            logger.info("[SEARCH] After fallback merge: %d total results", len(results))

    return results, query_used


# ─────────────────────────────────────────────────────────────────────────────
# Search engine implementations
# ─────────────────────────────────────────────────────────────────────────────

def _serpapi_configured() -> bool:
    key = settings.serpapi_key
    return bool(key and key not in ("replace-me", ""))


async def _search_serpapi(
    query: str,
    max_results: int,
    http_client: Optional[httpx.AsyncClient] = None,
    redis=None,
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
            response = await http_client.get(SERPAPI_URL, params=params, timeout=12.0)
        else:
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(SERPAPI_URL, params=params)

        if response.status_code == 429:
            logger.warning("[SEARCH] SerpAPI 429 — quota exhausted")
            await _mark_serpapi_exhausted(redis)
            return []

        response.raise_for_status()
        await _record_serpapi_call(redis)

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
    query: str,
    max_results: int,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[dict]:
    """
    DuckDuckGo HTML search. POST first, GET fallback.
    Tries multiple CSS selectors to handle layout changes.
    """
    headers = {
        "User-Agent": BOT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    html_text = None

    # Attempt 1: POST (standard DDG endpoint)
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

    # Attempt 2: GET fallback
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
                logger.warning("[SEARCH] DDG GET returned HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("[SEARCH] DDG GET failed: %s", e)

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
            logger.debug("[SEARCH] DDG selector '%s' → %d results", block_sel, len(results))
            break

    if not results:
        logger.warning("[SEARCH] DDG: all selectors returned 0 results")

    return results


async def _search_bing(
    query: str,
    max_results: int,
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[dict]:
    """
    Bing HTML search — no API key. Last resort when SerpAPI+DDG fail.
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

        logger.debug("[SEARCH] Bing → %d results for: %s", len(results), query[:60])
        return results

    except Exception as e:
        logger.error("[SEARCH] Bing failed: %s", e)
        return []
