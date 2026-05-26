import asyncio
import logging
import time
import redis.asyncio as aioredis
from typing import Dict

from db import queries
from models.schemas import ClaimSchema, ClaimSourcesResult, BiasResult
from agents.extractor import extract_claims
from agents.source_finder import find_sources
from agents.bias_scorer import score_bias
from agents.judge import run_judge
from utils.verdict_calc import compute_fallback_verdict
from services.embeddings import embed_batch
from services.redis_publisher import publish_status, publish_event, publish_done
from orchestration.pipelines.recovery import run_recovery_pipeline_flow

logger = logging.getLogger("truthstream.ai.deep")

async def run_deep_path_pipeline_flow(
    job_id: str, redis: aioredis.Redis, pool, raw_text: str, cleaned: str, wc: int,
    url_hash: str | None, input_url: str | None, user_id: str,
    start_time: float, fetch_time: float, model_call_time: float, http_client
) -> None:
    from orchestration.pipeline_router import log_lifecycle_async

    # State transition: parsing_claims
    await publish_status(redis, job_id, "parsing_claims", "Extracting claims (Deep Path)...")
    await log_lifecycle_async(pool, job_id, "EXTRACTION_STARTED", start_time=start_time, user_id=user_id, details={"path": "deep"})

    # Insert article
    article_id = await queries.insert_article(
        pool,
        url=input_url,
        url_hash=url_hash,
        raw_text=raw_text[:50000],
        cleaned_text=cleaned,
        truncated=False,
        word_count=wc,
    )
    await queries.update_job_article(pool, job_id, article_id)

    # Extract claims
    claims = []
    extraction_notes = "Deep path extraction."
    try:
        extract_start = time.perf_counter()
        # 12s Timeout for Claim Extraction
        extraction_result = await asyncio.wait_for(extract_claims(cleaned, input_url), timeout=12.0)
        model_call_time += (time.perf_counter() - extract_start)
        claims = extraction_result.claims
        extraction_notes = extraction_result.extraction_notes
        
        # Cap claims to 5 for deep path
        if len(claims) > 5:
            logger.info("Capping claims from %d to 5 for Deep Path.", len(claims))
            claims = claims[:5]
    except Exception as e:
        logger.warning("Claim extraction failed in Deep Path: %s. Falling back to Recovery Path.", e)
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, f"Claim extraction failed in Deep Path: {e}"
        )
        return

    if not claims:
        logger.warning("No claims found in Deep Path. Falling back to Recovery Path.")
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, "No claims extracted from text in Deep Path."
        )
        return

    # Embed and deduplicate
    unique_claims = []
    seen_texts = set()
    for c in claims:
        txt_norm = c.text.strip().lower()
        if txt_norm not in seen_texts:
            seen_texts.add(txt_norm)
            unique_claims.append(c)
    claims = unique_claims

    embeddings = await embed_batch([c.text for c in claims])
    
    async def process_single_claim(claim: ClaimSchema, emb: list[float]) -> ClaimSchema:
        if emb:
            similar = await queries.find_similar_claim(pool, emb)
            if similar:
                claim.claim_id = str(similar["id"])
                return claim

        claim_id = await queries.insert_claim(
            pool, job_id, article_id,
            claim.text, claim.context_quote,
            claim.claim_type, claim.checkability,
            emb or None,
        )
        claim.claim_id = claim_id
        return claim

    tasks = []
    for i, claim in enumerate(claims):
        emb = embeddings[i] if i < len(embeddings) else []
        tasks.append(process_single_claim(claim, emb))

    inserted_claims = list(await asyncio.gather(*tasks))

    # Publish claims extracted event
    await publish_event(redis, job_id, "claims_extracted", {
        "claims": [
            {
                "claim_id": c.claim_id,
                "text": c.text,
                "claim_type": c.claim_type,
                "checkability": c.checkability,
            }
            for c in inserted_claims
        ],
        "extraction_notes": extraction_notes,
    })

    # State transition: verifying_sources
    await publish_status(redis, job_id, "verifying_sources", "Crawling sources & analyzing bias (Deep Path)...")
    await log_lifecycle_async(pool, job_id, "REASONING_STARTED", start_time=start_time, user_id=user_id)

    # Sourcing & Bias analysis in parallel
    source_results_raw = []
    bias_result = None
    try:
        source_tasks = [find_sources(claim, redis, max_sources=6, http_client=http_client, scrape_full_text=True) for claim in inserted_claims]

        bias_task = score_bias(cleaned, input_url)

        sourcing_start = time.perf_counter()
        # 25s Timeout for sourcing + bias stages in parallel
        results = await asyncio.wait_for(
            asyncio.gather(
                asyncio.gather(*source_tasks, return_exceptions=True),
                bias_task,
                return_exceptions=True,
            ),
            timeout=25.0
        )
        sourcing_duration = time.perf_counter() - sourcing_start
        model_call_time += sourcing_duration
        source_results_raw, bias_result = results
    except asyncio.TimeoutError:
        logger.warning("Sourcing/Bias timed out in Deep Path. Falling back to Recovery Path.")
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, "Sourcing or bias analysis timed out (25s budget)."
        )
        return

    # Handle bias failure
    if isinstance(bias_result, Exception) or bias_result is None:
        logger.error("Bias scoring failed: %s", bias_result)
        bias_result = BiasResult(
            bias_score=50, bias_direction="neutral",
            framing_flags=[], loaded_terms=[],
            summary="Bias analysis unavailable."
        )

    # Insert bias result
    await queries.insert_bias_result(
        pool, job_id, article_id,
        bias_result.bias_score, bias_result.bias_direction,
        [f.model_dump() for f in bias_result.framing_flags],
        bias_result.loaded_terms, bias_result.summary,
    )
    await publish_event(redis, job_id, "bias_scored", {
        "bias_score": bias_result.bias_score,
        "bias_direction": bias_result.bias_direction,
        "framing_flags": [f.model_dump() for f in bias_result.framing_flags],
        "loaded_terms": bias_result.loaded_terms,
        "summary": bias_result.summary,
    })

    # Process source results
    sources_by_claim: Dict[str, ClaimSourcesResult] = {}
    for source_result in (source_results_raw if isinstance(source_results_raw, list) else []):
        if isinstance(source_result, Exception) or source_result is None:
            logger.warning("Source finding failed for a claim: %s", source_result)
            continue
        cid = source_result.claim_id
        sources_by_claim[cid] = source_result

        # Insert sources into DB
        for s in source_result.sources:
            sid = await queries.insert_source(
                pool, cid, s.url, s.title, s.domain,
                s.snippet, s.full_text, s.stance,
                s.quality_score or 0.0, s.fetch_status or "unknown"
            )
            s.source_id = sid

        await publish_event(redis, job_id, "claim_sourced", {
            "claim_id": cid,
            "sources": [
                {
                    "source_id": s.source_id,
                    "url": s.url,
                    "title": s.title,
                    "domain": s.domain,
                    "snippet": s.snippet,
                    "stance": s.stance,
                    "quality_score": s.quality_score,
                    "fetch_status": s.fetch_status,
                }
                for s in source_result.sources
            ],
        })

    # State transition: reasoning / generating_verdict
    await publish_status(redis, job_id, "reasoning", "Synthesizing final verdict (Deep Path)...")
    await log_lifecycle_async(pool, job_id, "VERDICT_STARTED", start_time=start_time, user_id=user_id)

    # Judge Agent
    try:
        judge_start = time.perf_counter()
        # 12s Timeout for Judge Agent
        judge_result = await asyncio.wait_for(
            run_judge(inserted_claims, sources_by_claim, bias_result, cleaned),
            timeout=12.0
        )
        model_call_time += (time.perf_counter() - judge_start)
    except Exception as e:
        logger.warning("Judge agent failed or timed out in Deep Path: %s. Using fallback.", e)
        judge_result = compute_fallback_verdict(inserted_claims, sources_by_claim, bias_result)

    await publish_status(redis, job_id, "generating_verdict", "Saving final verdicts...")

    # Insert verdicts
    for cv in judge_result.claim_verdicts:
        await queries.insert_verdict(
            pool, job_id, cv.claim_id,
            cv.verdict, cv.confidence, cv.reasoning, False
        )

    await queries.insert_verdict(
        pool, job_id, None,
        judge_result.overall_verdict, judge_result.overall_confidence,
        judge_result.overall_summary, True
    )

    await publish_event(redis, job_id, "verdict", {
        "overall_verdict": judge_result.overall_verdict,
        "overall_confidence": judge_result.overall_confidence,
        "overall_summary": judge_result.overall_summary,
        "claim_verdicts": [cv.model_dump() for cv in judge_result.claim_verdicts],
    })

    await queries.update_job_status(pool, job_id, "COMPLETE")
    await publish_status(redis, job_id, "completed", "Job successfully completed.")
    await log_lifecycle_async(pool, job_id, "JOB_COMPLETED", start_time=start_time, user_id=user_id, details={
        "path": "deep",
        "verdict": judge_result.overall_verdict
    })
    await publish_done(redis, job_id)

    # Log diagnostics
    total_time = time.perf_counter() - start_time
    proc_time = total_time - fetch_time
    logger.info(
        "\n[DIAGNOSTICS] Job %s (DEEP) Performance Metrics:\n"
        "- Fetch Time: %.3fs\n"
        "- Model Call Time: %.3fs\n"
        "- Processing Time: %.3fs\n"
        "- Total Job Time: %.3fs\n",
        job_id, fetch_time, model_call_time, proc_time, total_time
    )
