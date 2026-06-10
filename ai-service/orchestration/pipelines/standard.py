import asyncio
import logging
import time
import redis.asyncio as aioredis
from typing import Dict, List

from db import queries
from models.schemas import ClaimSchema, ClaimSourcesResult, BiasResult
from agents.extractor import extract_claims
from agents.source_finder import find_sources
from agents.article_source_pool import build_article_source_pool
from agents.compressed_judge import run_compressed_judge
from utils.verdict_calc import compute_fallback_verdict
from services.embeddings import embed_batch
from services.redis_publisher import publish_status, publish_event, publish_done
from orchestration.pipelines.recovery import run_recovery_pipeline_flow
from utils.priority import compute_claim_significance, calculate_source_overlap, fetch_cached_claim_results
from utils.pipeline_constants import (
    MAX_CLAIMS, MAX_CLAIMS_MODERATE,
    SOURCE_QUERIES_STANDARD, MAX_SOURCES_PER_CLAIM_STANDARD,
    SOURCE_POOL_TIMEOUT_STANDARD,
)

logger = logging.getLogger("truthstream.ai.standard")

async def run_standard_path_pipeline_flow(
    job_id: str, redis: aioredis.Redis, pool, raw_text: str, cleaned: str, wc: int,
    url_hash: str | None, input_url: str | None, user_id: str,
    start_time: float, fetch_time: float, model_call_time: float, http_client
) -> None:
    from orchestration.pipeline_router import log_lifecycle_async

    # State transition: parsing_claims
    await publish_status(redis, job_id, "parsing_claims", "Extracting and prioritizing claims (Standard Path)...")
    await log_lifecycle_async(pool, job_id, "EXTRACTION_STARTED", start_time=start_time, user_id=user_id, details={"path": "standard"})

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

    # Check provider availability & quota pressure
    from services.gemini import gemini_manager
    pressure = gemini_manager.get_quota_pressure_level()
    logger.info("[INSTRUMENTATION] PIPELINE_ROUTING | Quota pressure level: %s", pressure)

    if pressure == "critical":
        logger.warning("[INSTRUMENTATION] LIGHTWEIGHT_MODE_ACTIVATED | Critical pressure: skipping LLM. Recovery mode.")
        await publish_status(redis, job_id, "routing", "⚠️ System under high load: Running retrieval-only mode...")
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, "AI capacity limited. Provider is down."
        )
        return

    claim_limit = MAX_CLAIMS_MODERATE if pressure == "moderate" else MAX_CLAIMS
    if pressure == "moderate":
        logger.warning("[INSTRUMENTATION] LIGHTWEIGHT_MODE_ACTIVATED | Moderate pressure: limiting claims to %d.", MAX_CLAIMS_MODERATE)
        await publish_status(redis, job_id, "routing", f"⚠️ Quota pressure detected: Running lightweight verification (Max {MAX_CLAIMS_MODERATE} claims)...")

    # Extract candidate claims
    candidate_claims = []
    extraction_notes = "Standard path extraction."
    try:
        extract_start = time.perf_counter()
        # 10s Timeout for Claim Extraction
        extraction_result = await asyncio.wait_for(extract_claims(cleaned, input_url), timeout=10.0)
        model_call_time += (time.perf_counter() - extract_start)
        candidate_claims = extraction_result.claims
        extraction_notes = extraction_result.extraction_notes
    except Exception as e:
        logger.warning("Claim extraction failed in Standard Path: %s. Falling back to Recovery Path.", e)
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, f"Claim extraction failed: {e}"
        )
        return

    if not candidate_claims:
        logger.warning("No claims found in Standard Path. Falling back to Recovery Path.")
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, "No claims extracted from text."
        )
        return

    # Build article-level source pool (2 SerpAPI calls total instead of N_claims × 2)
    await publish_status(redis, job_id, "verifying_sources", "Retrieving evidence sources (Standard Path)...")

    pool_results: Dict[str, ClaimSourcesResult] = {}
    try:
        pool_results = await asyncio.wait_for(
            build_article_source_pool(
                article_text=cleaned,
                article_url=input_url,
                claims=candidate_claims,
                redis=redis,
                http_client=http_client,
                max_queries=SOURCE_QUERIES_STANDARD,
                max_pool_size=10,
                max_sources_per_claim=MAX_SOURCES_PER_CLAIM_STANDARD,
            ),
            timeout=SOURCE_POOL_TIMEOUT_STANDARD,
        )
    except Exception as e:
        logger.warning("[STANDARD] Article source pool failed: %s — continuing without sources", e)
        pool_results = {
            (c.claim_id or ""): ClaimSourcesResult(claim_id=c.claim_id or "", sources=[])
            for c in candidate_claims
        }

    # Compatibility shim: also compute per-claim overlap scores using pool results
    source_results = [
        pool_results.get(c.claim_id or "", ClaimSourcesResult(claim_id=c.claim_id or "", sources=[]))
        for c in candidate_claims
    ]

    # Score and Prioritize Claims
    scored_claims = []
    sources_by_claim: Dict[str, ClaimSourcesResult] = {}
    
    for i, claim in enumerate(candidate_claims):
        s_res = source_results[i]
        if isinstance(s_res, Exception) or s_res is None:
            s_res = ClaimSourcesResult(claim_id=claim.claim_id or "", sources=[])
        
        # Calculate scores
        sig_score = compute_claim_significance(claim.text, claim.checkability, claim.claim_type)
        overlap_score = calculate_source_overlap(claim.text, [s.model_dump() for s in s_res.sources]) * 5.0
        total_priority = sig_score + overlap_score
        
        logger.info(
            "[INSTRUMENTATION] CLAIM_SIGNIFICANCE_SCORING | Claim: %s | Significance: %.2f | Overlap: %.2f | Priority: %.2f",
            claim.text[:50], sig_score, overlap_score, total_priority
        )
        scored_claims.append((total_priority, claim, s_res))

    # Sort and select Top claims
    scored_claims.sort(key=lambda x: x[0], reverse=True)
    top_claims_info = scored_claims[:claim_limit]
    top_claims = [x[1] for x in top_claims_info]
    
    # Store top claims sources in the sources_by_claim mapping
    for _, claim, s_res in top_claims_info:
        sources_by_claim[claim.claim_id or ""] = s_res

    discarded_count = len(candidate_claims) - len(top_claims)
    logger.info("[INSTRUMENTATION] TOP_5_CLAIMS_SELECTED | Selected: %d | Discarded: %d", len(top_claims), discarded_count)

    # Semantic Cache Check
    embeddings = await embed_batch([c.text for c in top_claims])
    inserted_claims = []
    cached_verdicts_by_claim = {}
    cache_hits = 0

    for i, claim in enumerate(top_claims):
        emb = embeddings[i] if i < len(embeddings) else []
        similar_id = None
        cached_verdict = None
        cached_sources = []
        
        if emb:
            similar = await queries.find_similar_claim(pool, emb)
            if similar:
                similar_id = str(similar["id"])
                cached_sources, cached_verdict = await fetch_cached_claim_results(pool, similar_id)

        if similar_id and cached_verdict:
            # Semantic cache hit!
            claim.claim_id = similar_id
            logger.info("[INSTRUMENTATION] CACHE_REUSED | Claim: %s | Reused Claim ID: %s", claim.text[:50], similar_id)
            cache_hits += 1
            
            cached_verdicts_by_claim[similar_id] = {
                "verdict": cached_verdict["verdict"],
                "confidence": float(cached_verdict["confidence"]),
                "reasoning": cached_verdict["reasoning"]
            }
            
            # Map cached sources
            from models.schemas import SourceSchema
            reused_sources = []
            for s in cached_sources:
                reused_sources.append(SourceSchema(
                    url=s["url"],
                    title=s["title"],
                    domain=s["domain"],
                    snippet=s["snippet"],
                    full_text=s["full_text"],
                    stance=s["stance"],
                    quality_score=float(s["quality_score"]) if s["quality_score"] is not None else 0.0,
                    fetch_status=s["fetch_status"]
                ))
            sources_by_claim[similar_id] = ClaimSourcesResult(claim_id=similar_id, sources=reused_sources)
            inserted_claims.append(claim)
        else:
            # Cache miss: insert new claim
            claim_id = await queries.insert_claim(
                pool, job_id, article_id,
                claim.text, claim.context_quote,
                claim.claim_type, claim.checkability,
                emb or None,
            )
            claim.claim_id = claim_id
            inserted_claims.append(claim)

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
        "extraction_notes": f"{extraction_notes} ({cache_hits} claims resolved via cache)",
    })

    # State transition: verifying_sources
    await publish_status(redis, job_id, "verifying_sources", "Analyzing bias and claim evidence (Standard Path)...")
    await log_lifecycle_async(pool, job_id, "REASONING_STARTED", start_time=start_time, user_id=user_id)

    # Identify cache-miss claims that need Gemini analysis
    cache_miss_claims = [c for c in inserted_claims if c.claim_id not in cached_verdicts_by_claim]

    bias_result = None
    judge_result = None
    stances_by_claim = {}

    if cache_miss_claims:
        logger.info("[INSTRUMENTATION] PIPELINE_COMPRESSED | Run compressed judgment for %d cache-miss claims.", len(cache_miss_claims))
        compressed_start = time.perf_counter()
        bias_result, judge_result, stances_by_claim = await run_compressed_judge(
            cache_miss_claims, sources_by_claim, cleaned, input_url
        )
        model_call_time += (time.perf_counter() - compressed_start)
    else:
        logger.info("[INSTRUMENTATION] PIPELINE_COMPRESSED | All claims resolved via cache. Skipping Gemini judgment.")
        bias_result = BiasResult(
            bias_score=10, bias_direction="neutral",
            framing_flags=[], loaded_terms=[],
            summary="All claims resolved via semantic cache. Minimal bias assumed."
        )
        judge_result = compute_fallback_verdict(inserted_claims, sources_by_claim, bias_result)
        stances_by_claim = {}

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

    # Save sources and stances into database, publish events
    for c in inserted_claims:
        cid = c.claim_id or ""
        c_sources = sources_by_claim.get(cid)
        if not c_sources:
            continue
            
        # Update source stances if cache miss
        if cid not in cached_verdicts_by_claim:
            c_stances = stances_by_claim.get(cid, [])
            for idx, s in enumerate(c_sources.sources):
                if idx < len(c_stances):
                    s.stance = c_stances[idx]

        # Save sources in DB
        for s in c_sources.sources:
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
                for s in c_sources.sources
            ],
        })

    # State transition: reasoning / generating_verdict
    await publish_status(redis, job_id, "generating_verdict", "Saving final verdicts...")

    # Save claim verdicts to DB and gather for the verdict event
    claim_verdicts_payload = []
    
    # 1. New verdicts from compressed judge
    for cv in judge_result.claim_verdicts:
        await queries.insert_verdict(
            pool, job_id, cv.claim_id,
            cv.verdict, cv.confidence, cv.reasoning, False
        )
        claim_verdicts_payload.append(cv.model_dump())
        
    # 2. Cached verdicts
    for cid, cached in cached_verdicts_by_claim.items():
        await queries.insert_verdict(
            pool, job_id, cid,
            cached["verdict"], cached["confidence"],
            cached["reasoning"] + " (Resolved via Semantic Cache)", False
        )
        claim_verdicts_payload.append({
            "claim_id": cid,
            "verdict": cached["verdict"],
            "confidence": cached["confidence"],
            "reasoning": cached["reasoning"] + " (Resolved via Semantic Cache)",
            "key_source_indices": []
        })

    # Save overall verdict
    await queries.insert_verdict(
        pool, job_id, None,
        judge_result.overall_verdict, judge_result.overall_confidence,
        judge_result.overall_summary, True
    )

    await publish_event(redis, job_id, "verdict", {
        "overall_verdict": judge_result.overall_verdict,
        "overall_confidence": judge_result.overall_confidence,
        "overall_summary": judge_result.overall_summary,
        "claim_verdicts": claim_verdicts_payload,
    })

    await queries.update_job_status(pool, job_id, "COMPLETE")
    await publish_status(redis, job_id, "completed", "Job successfully completed.")
    await log_lifecycle_async(pool, job_id, "JOB_COMPLETED", start_time=start_time, user_id=user_id, details={
        "path": "standard",
        "verdict": judge_result.overall_verdict
    })
    await publish_done(redis, job_id)

    # Log diagnostics
    total_time = time.perf_counter() - start_time
    proc_time = total_time - fetch_time
    logger.info(
        "\n[DIAGNOSTICS] Job %s (STANDARD) Performance Metrics:\n"
        "- Fetch Time: %.3fs\n"
        "- Model Call Time: %.3fs\n"
        "- Processing Time: %.3fs\n"
        "- Total Job Time: %.3fs\n",
        job_id, fetch_time, model_call_time, proc_time, total_time
    )
