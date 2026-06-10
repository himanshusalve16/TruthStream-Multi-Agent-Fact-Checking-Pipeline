"""Source Finder Agent — searches, scrapes, and classifies source stance per claim."""
import asyncio
import json
import logging
from typing import List

from google import genai
from google.genai import types
from models.schemas import ClaimSchema, ClaimSourcesResult, SourceSchema
from services.gemini import execute_gemini_call
from config import settings
from services.search import search_web_with_fallback, build_claim_query, build_fallback_query, build_article_queries
from services.scraper import scrape_url
from utils.text import extract_domain
from utils.quality import score_source, is_paywalled

logger = logging.getLogger(__name__)

STANCE_SYSTEM_PROMPT = """You are evaluating whether web sources support or contradict a specific factual claim.

For each source snippet below, classify the stance as:
- "SUPPORTS": the source provides evidence that the claim is true
- "REFUTES": the source provides evidence that the claim is false
- "NEUTRAL": the source discusses the topic but takes no stance
- "UNCLEAR": the snippet is insufficient to determine stance

Output JSON only:
{
  "stances": [
    {"source_index": 0, "stance": "SUPPORTS|REFUTES|NEUTRAL|UNCLEAR", "reason": "one sentence"}
  ]
}"""

MAX_SOURCES = 6
MAX_CONCURRENT_SCRAPES = 5


def rank_snippets_by_overlap(claim_text: str, search_results: List[dict]) -> List[dict]:
    """Rank search results based on word token overlap with the claim text."""
    import re
    claim_words = set(re.findall(r'\w+', claim_text.lower()))
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    claim_words = claim_words - stop_words

    if not claim_words:
        return search_results

    scored_results = []
    for r in search_results:
        snippet_text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        snippet_words = set(re.findall(r'\w+', snippet_text))
        overlap = len(claim_words.intersection(snippet_words))
        score = overlap / len(claim_words) if len(claim_words) > 0 else 0
        scored_results.append((score, r))

    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_results]


def deduplicate_and_filter_sources(results: List[dict], max_needed: int) -> List[dict]:
    """
    Enforces source domain diversity (max 1 per domain) and filters syndicated
    mirror content using Jaccard word-level similarity.
    """
    import re
    seen_domains = set()
    unique_results = []

    def get_word_set(text: str) -> set:
        words = re.findall(r'\w+', text.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        return set(w for w in words if len(w) > 3 and w not in stop_words)

    for i, r in enumerate(results):
        url = r.get("url", "")
        domain = extract_domain(url) or url

        # 1. Domain diversity: limit to 1 result per domain
        if domain in seen_domains:
            continue

        # 2. Content similarity check to avoid syndication and mirror copies (Jaccard > 0.65)
        r_text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        r_words = get_word_set(r_text)

        is_duplicate = False
        for ur in unique_results:
            ur_text = (ur.get("title", "") + " " + ur.get("snippet", "")).lower()
            ur_words = get_word_set(ur_text)
            if r_words and ur_words:
                intersection = r_words.intersection(ur_words)
                union = r_words.union(ur_words)
                jaccard = len(intersection) / len(union) if union else 0.0
                if jaccard > 0.65:
                    is_duplicate = True
                    break

        if is_duplicate:
            continue

        seen_domains.add(domain)
        # Ensure rank field is set for later quality scoring
        if "rank" not in r:
            r["rank"] = i + 1
        unique_results.append(r)

        if len(unique_results) >= max_needed:
            break

    removed_count = len(results) - len(unique_results)
    if removed_count > 0:
        logger.info(
            "[SOURCE] Dedup removed %d duplicates | remaining: %d",
            removed_count, len(unique_results)
        )

    return unique_results


async def find_sources(
        claim: ClaimSchema,
        redis=None,
        max_sources: int = 5,
        http_client=None,
        scrape_full_text: bool = False,
        classify_stance: bool = True,
        query_budget: int = 2,
) -> ClaimSourcesResult:
    """
    For a single claim: search → (optional scrape) → classify stance.

    query_budget controls how many search API calls are made:
      1 = primary query only (fast path, minimal SerpAPI cost)
      2 = primary + fallback if primary returns < 3 (default, balanced)

    Note: prefer build_article_source_pool() for multi-claim articles
    to share the search budget across all claims.
    """
    claim_id = claim.claim_id or ""
    claim_short = claim.text[:80]

    primary_query = build_claim_query(claim.text, claim.claim_type)
    fallback_query = build_fallback_query(claim.text)

    logger.info(
        "[SOURCE] Starting source lookup | Claim: %s... | Type: %s",
        claim_short, claim.claim_type
    )
    logger.info("[SOURCE] Primary query: %s", primary_query)
    logger.info("[SOURCE] Fallback query: %s", fallback_query)

    # Fetch up to 8 results (reduced from 15 to conserve SerpAPI quota)
    results, query_used = await search_web_with_fallback(
        primary_query=primary_query,
        fallback_query=fallback_query,
        max_results=8,
        redis=redis,
        http_client=http_client,
        min_primary_results=3,
        query_budget=query_budget,
    )

    logger.info(
        "[SOURCE] Search complete | Results: %d | Query used: %s",
        len(results), query_used[:80]
    )

    if not results:
        logger.warning(
            "[SOURCE] All search engines returned 0 results | Claim: %s...", claim_short
        )
        return ClaimSourcesResult(claim_id=claim_id, sources=[])

    # Rerank snippets by lexical overlap with claim
    results = rank_snippets_by_overlap(claim.text, results)

    # Apply domain diversity and syndication filters
    top_results = deduplicate_and_filter_sources(results, max_needed=max_sources + 3)

    logger.info(
        "[SOURCE] After dedup | Candidates: %d | Claim: %s...", len(top_results), claim_short
    )

    if not scrape_full_text:
        # Standard/Fast Path: snippet-only, no HTTP fetches
        selected = []
        for i, r in enumerate(top_results[:max_sources]):
            url = r["url"]
            domain = extract_domain(url) or url
            quality = score_source(
                domain=domain,
                url=url,
                snippet=r.get("snippet", ""),
                fetch_status="success",
                search_rank=r.get("rank", i + 1),
                full_text=None,
            )
            selected.append({
                **r,
                "domain": domain,
                "full_text": None,
                "fetch_status": "success",
                "quality_score": quality,
            })
    else:
        # Deep Path: scrape full text in parallel
        sem = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)

        async def scrape_one(result: dict, rank: int) -> dict:
            async with sem:
                url = result["url"]
                domain = extract_domain(url) or url
                full_text, fetch_status = await scrape_url(url, redis=redis, http_client=http_client)
                quality = score_source(
                    domain=domain,
                    url=url,
                    snippet=result.get("snippet", ""),
                    fetch_status=fetch_status,
                    search_rank=rank,
                    full_text=full_text,
                )
                return {
                    **result,
                    "domain": domain,
                    "full_text": full_text,
                    "fetch_status": fetch_status,
                    "quality_score": quality,
                    "rank": rank,
                }

        scraped = await asyncio.gather(
            *[scrape_one(r, r["rank"]) for r in top_results],
            return_exceptions=True,
        )

        # Filter successful scrapes and sort by quality
        valid = [
            s for s in scraped
            if isinstance(s, dict) and s.get("fetch_status") not in ("ssrf_blocked", "error")
        ]
        valid.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        selected = valid[:max_sources]

    if not selected:
        logger.warning(
            "[SOURCE] 0 sources passed dedup/quality filter | Claim: %s...", claim_short
        )
        return ClaimSourcesResult(claim_id=claim_id, sources=[])

    logger.info(
        "[SOURCE] Selected %d sources for stance classification | Claim: %s...",
        len(selected), claim_short
    )

    # Classify stances via LLM if requested, else default to UNCLEAR
    if classify_stance:
        stances = await _classify_stances(claim.text, selected)
    else:
        stances = ["UNCLEAR"] * len(selected)

    sources = []
    for i, s in enumerate(selected):
        stance = stances[i] if i < len(stances) else "UNCLEAR"
        paywalled = is_paywalled(s.get("snippet", ""), s.get("full_text", "")) if s.get("full_text") else False
        sources.append(SourceSchema(
            url=s["url"],
            title=s.get("title"),
            domain=s.get("domain"),
            snippet=(s.get("snippet") or "")[:500],
            full_text=(s.get("full_text") or "")[:2000] if not paywalled and s.get("full_text") else None,
            stance=stance,
            quality_score=s.get("quality_score", 0.0),
            fetch_status="blocked" if paywalled else s.get("fetch_status", "success"),
        ))

    logger.info(
        "[SOURCE] Done | Claim: %s... | Sources: %d | Stances: %s",
        claim_short, len(sources), [s.stance for s in sources]
    )

    return ClaimSourcesResult(claim_id=claim_id, sources=sources)


async def _classify_stances(claim_text: str, sources: List[dict]) -> List[str]:
    """Ask Gemini to classify stance of each source relative to the claim."""
    sources_json = json.dumps([
        {"source_index": i, "title": s.get("title", ""), "snippet": s.get("snippet", "")[:500]}
        for i, s in enumerate(sources)
    ])
    user_content = f"Claim: {claim_text[:300]}\n\nSources:\n{sources_json}"

    async def call_stance(client: genai.Client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=STANCE_SYSTEM_PROMPT,
                temperature=0,
                response_mime_type="application/json",
            )
        )

    try:
        response = await execute_gemini_call(call_stance)
        raw = response.text
        data = json.loads(raw)
        stances_data = data.get("stances", [])
        stances = ["UNCLEAR"] * len(sources)
        for item in stances_data:
            idx = item.get("source_index", -1)
            if 0 <= idx < len(stances):
                stances[idx] = item.get("stance", "UNCLEAR")
        return stances
    except Exception as e:
        logger.error("[SOURCE] Stance classification failed: %s", e)
        return ["UNCLEAR"] * len(sources)
