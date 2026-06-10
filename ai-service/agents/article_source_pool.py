"""
Article-Level Source Pool

Instead of calling find_sources() independently for each claim (N_claims × 1-2 SerpAPI
calls = 5-10 calls/article), this module builds a SINGLE shared pool of sources for the
whole article using 2-3 targeted queries, then distributes them to each claim by
lexical-overlap matching.

SerpAPI Budget:
  fast path   → max_queries=1   (1 SerpAPI call total)
  standard    → max_queries=2   (2 SerpAPI calls total, fallback to 3 if 1st returns <3)
  deep path   → max_queries=3   (3 SerpAPI calls total)

vs old per-claim approach: 5 claims × 2 = 10 calls/article.
"""
import asyncio
import logging
import re
from typing import Dict, List, Optional

from models.schemas import ClaimSchema, ClaimSourcesResult, SourceSchema
from services.search import (
    build_article_queries,
    build_claim_query,
    build_fallback_query,
    search_web,
)
from utils.text import extract_domain
from utils.quality import score_source, is_paywalled

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Domain credibility tiers (for quick pre-ranking without scraping)
# ─────────────────────────────────────────────────────────────────────────────
_TIER1_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
    "theguardian.com", "nytimes.com", "washingtonpost.com",
    "bloomberg.com", "ft.com", "economist.com",
    "who.int", "cdc.gov", "nih.gov", "nasa.gov",
    "sciencemag.org", "nature.com", "thelancet.com",
}
_TIER2_DOMAINS = {
    "thehindu.com", "ndtv.com", "indiatimes.com", "hindustantimes.com",
    "aljazeera.com", "france24.com", "dw.com",
    "politifact.com", "snopes.com", "factcheck.org",
    "statista.com", "worldbank.org", "imf.org", "un.org",
    "cnbc.com", "forbes.com", "businessinsider.com",
}


def _domain_tier_boost(domain: str) -> float:
    """Return a 0.0-0.3 boost for high-credibility domains."""
    if domain in _TIER1_DOMAINS:
        return 0.3
    if domain in _TIER2_DOMAINS:
        return 0.15
    return 0.0


def _lexical_overlap(text_a: str, text_b: str) -> float:
    """Compute word-level Jaccard-like overlap between two texts (stop-words removed)."""
    _stop = {"the", "a", "an", "and", "or", "is", "are", "was", "were",
             "in", "on", "at", "to", "for", "of", "with", "by", "that", "this"}
    wa = set(re.findall(r'\w+', text_a.lower())) - _stop
    wb = set(re.findall(r'\w+', text_b.lower())) - _stop
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa)


def _score_and_assign_sources(
    all_results: List[dict],
    claims: List[ClaimSchema],
    max_sources_per_claim: int = 5,
) -> Dict[str, List[dict]]:
    """
    Score all pooled search results globally, then assign the most relevant
    ones to each claim using lexical overlap.

    Returns: {claim_id → [source_dict, ...]}
    """
    # Global quality scoring (domain tier + dedup)
    seen_urls: set = set()
    seen_domains: set = set()
    scored_pool: List[tuple] = []

    for r in all_results:
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        domain = extract_domain(url) or url
        # Allow max 2 per domain in global pool (looser than per-claim dedup)
        domain_count = sum(1 for _, item in scored_pool if item.get("domain") == domain)
        if domain_count >= 2:
            continue

        base_quality = score_source(
            domain=domain,
            url=url,
            snippet=r.get("snippet", ""),
            fetch_status="success",
            search_rank=r.get("rank", 99),
            full_text=None,
        )
        tier_boost = _domain_tier_boost(domain)
        total_quality = base_quality + tier_boost

        scored_pool.append((total_quality, {**r, "domain": domain, "quality_score": total_quality}))

    scored_pool.sort(key=lambda x: x[0], reverse=True)
    pool = [item for _, item in scored_pool]

    logger.info("[POOL] Global pool: %d unique sources from %d raw results", len(pool), len(all_results))

    # Assign to each claim
    assignment: Dict[str, List[dict]] = {}
    for claim in claims:
        cid = claim.claim_id or ""
        claim_ref = claim.text

        # Score each pool item by overlap with this claim
        claim_scored = []
        for item in pool:
            candidate_text = (item.get("title", "") + " " + item.get("snippet", ""))
            overlap = _lexical_overlap(claim_ref, candidate_text)
            # Combined score: quality × 0.5 + overlap × 0.5
            combined = item.get("quality_score", 0.0) * 0.5 + overlap * 0.5
            claim_scored.append((combined, item))

        claim_scored.sort(key=lambda x: x[0], reverse=True)
        assignment[cid] = [item for _, item in claim_scored[:max_sources_per_claim]]

        logger.info(
            "[POOL] Claim '%s...' → assigned %d sources",
            claim_ref[:60], len(assignment[cid])
        )

    return assignment


async def build_article_source_pool(
    article_text: str,
    article_url: Optional[str],
    claims: List[ClaimSchema],
    redis=None,
    http_client=None,
    max_queries: int = 2,
    max_pool_size: int = 10,
    max_sources_per_claim: int = 5,
) -> Dict[str, ClaimSourcesResult]:
    """
    Build a shared source pool for an entire article in max_queries SerpAPI calls,
    then distribute sources to each claim by relevance.

    Args:
        article_text:         cleaned article text (used for query generation)
        article_url:          original article URL (used for URL-based cache + query hints)
        claims:               list of ClaimSchema objects (must have claim_id set)
        redis:                Redis connection for search caching + quota tracking
        http_client:          shared httpx.AsyncClient
        max_queries:          hard cap on number of search queries (SerpAPI budget)
        max_pool_size:        max unique sources in the global pool
        max_sources_per_claim: max sources assigned to each individual claim

    Returns:
        {claim_id: ClaimSourcesResult} for all claims
    """
    if not claims:
        return {}

    logger.info(
        "[POOL] Building article source pool | Claims: %d | Max queries: %d | URL: %s",
        len(claims), max_queries, article_url or "text-input"
    )

    # ── Step 1: Generate diverse article-level queries ────────────────────────
    queries = build_article_queries(
        article_text=article_text,
        article_url=article_url,
        claims=claims,
        max_queries=max_queries,
    )

    if not queries:
        # Absolute fallback: use the first claim's query
        queries = [build_claim_query(claims[0].text, claims[0].claim_type)]
        logger.warning("[POOL] No article queries generated — using claim fallback: %s", queries[0])

    logger.info("[POOL] Running %d search queries (budget=%d): %s", len(queries), max_queries, queries)

    # ── Step 2: Run queries in parallel (budget-bounded) ─────────────────────
    query_tasks = [
        search_web(q, max_results=8, redis=redis, http_client=http_client)
        for q in queries[:max_queries]
    ]
    query_results = await asyncio.gather(*query_tasks, return_exceptions=True)

    # Flatten all results
    all_results: List[dict] = []
    for i, res in enumerate(query_results):
        if isinstance(res, Exception):
            logger.warning("[POOL] Query %d failed: %s", i + 1, res)
            continue
        logger.info("[POOL] Query %d returned %d results", i + 1, len(res))
        all_results.extend(res)

    # ── Step 3: If pool is too thin, try one fallback claim-specific query ────
    if len(all_results) < 3 and len(queries) < max_queries + 1:
        # Pick the most checkable claim for targeted fallback
        priority = {"high": 3, "medium": 2, "low": 1}
        best_claim = max(
            claims,
            key=lambda c: priority.get(getattr(c, "checkability", "") or "", 0),
            default=claims[0],
        )
        fallback_q = build_fallback_query(best_claim.text)
        logger.info(
            "[POOL] Pool thin (%d results) → targeted fallback: %s", len(all_results), fallback_q
        )
        try:
            fb_results = await search_web(fallback_q, max_results=8, redis=redis, http_client=http_client)
            all_results.extend(fb_results)
            logger.info("[POOL] Fallback added %d results → total: %d", len(fb_results), len(all_results))
        except Exception as e:
            logger.warning("[POOL] Fallback query failed: %s", e)

    if not all_results:
        logger.warning("[POOL] All queries returned 0 results — returning empty sources for all claims")
        return {
            (c.claim_id or ""): ClaimSourcesResult(claim_id=c.claim_id or "", sources=[])
            for c in claims
        }

    # ── Step 4: Score globally and assign to claims ───────────────────────────
    assignment = _score_and_assign_sources(
        all_results[:max_pool_size * 3],  # cap raw pool before scoring
        claims,
        max_sources_per_claim=max_sources_per_claim,
    )

    # ── Step 5: Per-claim source enforcement ──────────────────────────────────
    # If any claim has 0 sources after pool distribution, run ONE targeted search
    # for that claim specifically (stop-early: 1 good source is enough).
    # This ensures no claim is silently left without a source status.
    claims_needing_fallback = [
        c for c in claims
        if not assignment.get(c.claim_id or "", [])
    ]
    if claims_needing_fallback:
        logger.info(
            "[POOL] %d claim(s) have 0 sources after pool — running targeted single-claim search",
            len(claims_needing_fallback),
        )
        for claim in claims_needing_fallback:
            cid = claim.claim_id or ""
            try:
                targeted_q = build_fallback_query(claim.text)
                targeted_results = await search_web(
                    targeted_q, max_results=5, redis=redis, http_client=http_client
                )
                if targeted_results:
                    # Add top result to pool for this claim
                    best = targeted_results[0]
                    domain = extract_domain(best.get("url", "")) or best.get("url", "")
                    assignment[cid] = [{
                        **best,
                        "domain": domain,
                        "quality_score": _domain_tier_boost(domain) + 0.4,
                    }]
                    logger.info(
                        "[POOL] Targeted fallback for claim '%s...' → found 1 source: %s",
                        claim.text[:50], best.get("url", "")[:60],
                    )
                else:
                    logger.warning(
                        "[POOL] No source found for claim '%s...' — will be marked unverifiable",
                        claim.text[:60],
                    )
            except Exception as e:
                logger.warning("[POOL] Targeted fallback for claim '%s...' failed: %s", claim.text[:40], e)

    # ── Step 6: Convert to ClaimSourcesResult objects ─────────────────────────
    result: Dict[str, ClaimSourcesResult] = {}
    zero_source_claims: List[str] = []

    for claim in claims:
        cid = claim.claim_id or ""
        assigned = assignment.get(cid, [])
        sources = []
        for s in assigned:
            sources.append(SourceSchema(
                url=s["url"],
                title=s.get("title"),
                domain=s.get("domain"),
                snippet=(s.get("snippet") or "")[:500],
                full_text=None,
                stance="UNCLEAR",  # Will be updated by compressed_judge
                quality_score=s.get("quality_score", 0.0),
                fetch_status="success",
            ))
        result[cid] = ClaimSourcesResult(claim_id=cid, sources=sources)

        # Diagnostic: flag claims with no sources so they surface in logs
        if not sources:
            zero_source_claims.append(claim.text[:60])

    total_sources = sum(len(v.sources) for v in result.values())

    # ── Step 7: Diagnostics ───────────────────────────────────────────────────
    logger.info(
        "[POOL] Done | Queries used: %d | Total sources: %d | Claims: %d | Zero-source claims: %d",
        len(queries), total_sources, len(claims), len(zero_source_claims)
    )
    for claim in claims:
        cid = claim.claim_id or ""
        src_count = len(result[cid].sources)
        if src_count == 0:
            logger.warning(
                "[POOL] SOURCE_MISSING | Claim: '%s...' | No external source found — verdict based on internal reasoning",
                claim.text[:70]
            )
        else:
            logger.info(
                "[POOL] SOURCE_OK | Claim: '%s...' | Sources: %d",
                claim.text[:70], src_count
            )

    return result
