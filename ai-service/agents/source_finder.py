"""Source Finder Agent — searches, scrapes, and classifies source stance per claim."""
import asyncio
import json
import logging
from typing import List

from models.schemas import ClaimSchema, ClaimSourcesResult, SourceSchema
from services.embeddings import get_openai_client
from services.search import search_web, build_claim_query
from services.scraper import scrape_url
from utils.text import extract_domain
from utils.quality import score_source, is_paywalled

logger = logging.getLogger(__name__)

STANCE_SYSTEM_PROMPT = """You are evaluating whether web sources support or contradict a specific factual claim.

Claim: "{claim_text}"

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

MAX_SOURCES = 5
MAX_CONCURRENT_SCRAPES = 5


async def find_sources(
        claim: ClaimSchema,
        redis=None,
) -> ClaimSourcesResult:
    """
    For a single claim: search → scrape → classify stance.
    Returns ClaimSourcesResult.
    """
    query = build_claim_query(claim.text, claim.claim_type)
    results = await search_web(query, max_results=10)

    # Filter to top MAX_SOURCES by quality before scraping
    top_results = results[:MAX_SOURCES * 2]  # scrape extra to compensate for failures

    # Scrape in parallel
    sem = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)

    async def scrape_one(result: dict, rank: int) -> dict:
        async with sem:
            url = result["url"]
            domain = extract_domain(url) or url
            full_text, fetch_status = await scrape_url(url, redis=redis)
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
    selected = valid[:MAX_SOURCES]

    if not selected:
        return ClaimSourcesResult(claim_id=claim.claim_id or "", sources=[])

    # Classify stances via LLM
    stances = await _classify_stances(claim.text, selected)

    sources = []
    for i, s in enumerate(selected):
        stance = stances[i] if i < len(stances) else "UNCLEAR"
        paywalled = is_paywalled(s.get("snippet", ""), s.get("full_text", ""))
        sources.append(SourceSchema(
            url=s["url"],
            title=s.get("title"),
            domain=s.get("domain"),
            snippet=(s.get("snippet") or "")[:500],
            full_text=(s.get("full_text") or "")[:2000] if not paywalled else None,
            stance=stance,
            quality_score=s.get("quality_score", 0.0),
            fetch_status="blocked" if paywalled else s.get("fetch_status", "success"),
        ))

    return ClaimSourcesResult(claim_id=claim.claim_id or "", sources=sources)


async def _classify_stances(claim_text: str, sources: List[dict]) -> List[str]:
    """Ask GPT-4o to classify stance of each source relative to the claim."""
    client = get_openai_client()
    sources_json = json.dumps([
        {"source_index": i, "title": s.get("title", ""), "snippet": s.get("snippet", "")[:500]}
        for i, s in enumerate(sources)
    ])
    system = STANCE_SYSTEM_PROMPT.format(claim_text=claim_text[:300])
    user = f"Sources:\n{sources_json}"

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            timeout=20.0,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        stances_data = data.get("stances", [])
        stances = ["UNCLEAR"] * len(sources)
        for item in stances_data:
            idx = item.get("source_index", -1)
            if 0 <= idx < len(stances):
                stances[idx] = item.get("stance", "UNCLEAR")
        return stances
    except Exception as e:
        logger.error("Stance classification failed: %s", e)
        return ["UNCLEAR"] * len(sources)
