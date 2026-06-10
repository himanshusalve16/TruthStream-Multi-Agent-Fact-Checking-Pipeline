import asyncio
import logging
import time
import json
import redis.asyncio as aioredis
from google.genai import types

from config import settings
from db import queries
from services.gemini import execute_gemini_call
from services.redis_publisher import publish_status, publish_event, publish_done
from orchestration.pipelines.recovery import run_recovery_pipeline_flow
from models.schemas import ClaimSchema, ClaimSourcesResult
from utils.pipeline_constants import (
    MAX_CLAIMS_FAST,
    SOURCE_QUERIES_FAST, MAX_SOURCES_PER_CLAIM_FAST,
    SOURCE_POOL_TIMEOUT_FAST,
)

logger = logging.getLogger("truthstream.ai.fast")

UNIFIED_FAST_PATH_SYSTEM_PROMPT = """You are an elite, rapid fact-checker and media bias analyst.
Analyze the provided short article/text. You must perform claim extraction, bias analysis, and veracity judgment all in one single pass.

Task 1: Factual Claim Extraction
- Extract up to 2 discrete checkable factual claims (statistics, events, attribution, definition).
- Prioritize the highest-value, most verifiable claims. Ignore low-value or opinion claims.
- For each claim, rate checkability: "high", "medium", or "low".

Task 2: Media Bias Analysis
- Score overall bias from 0 (neutral) to 100 (heavily biased).
- Identify direction: left_leaning, right_leaning, pro_establishment, anti_establishment, or neutral.
- List loaded terms used.
- Detail framing flags (type, description, examples, severity).

Task 3: Veracity Judgment
- Synthesize the claims and your overall analysis to provide:
  - An overall verdict: MOSTLY_TRUE, MIXTURE, MOSTLY_FALSE, or UNVERIFIABLE.
  - Overall confidence: float (0.0-1.0).
  - Overall summary: 2-3 sentences.
  - For each extracted claim, provide a verdict (SUPPORTED, REFUTED, CONTESTED, UNVERIFIABLE), confidence, and reasoning.

Output JSON only using this exact schema:
{
  "bias": {
    "bias_score": integer (0-100),
    "bias_direction": "left_leaning|right_leaning|pro_establishment|anti_establishment|neutral",
    "framing_flags": [
      {"type": "string", "description": "string", "examples": ["string"], "severity": "low|medium|high"}
    ],
    "loaded_terms": ["string"],
    "summary": "string"
  },
  "claims": [
    {
      "temp_id": "string (e.g. c1, c2)",
      "text": "string",
      "context_quote": "string",
      "claim_type": "statistic|event|attribution|definition",
      "checkability": "high|medium|low"
    }
  ],
  "verdict": {
    "overall_verdict": "MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE",
    "overall_confidence": float (0.0-1.0),
    "overall_summary": "string",
    "claim_verdicts": [
      {
        "temp_id": "string matching claim temp_id",
        "verdict": "SUPPORTED|REFUTED|CONTESTED|UNVERIFIABLE",
        "confidence": float (0.0-1.0),
        "reasoning": "string"
      }
    ]
  }
}
"""

async def run_fast_path_pipeline(cleaned_text: str, url: str | None) -> dict:
    """Run a single-pass unified LLM call for short/simple articles."""
    user_content = (
        f"Article URL: {url or 'N/A'}\n\n"
        f"Article Text:\n{cleaned_text}\n\n"
        "Analyze this article and return the unified JSON."
    )
    
    async def call_fast_path(client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=UNIFIED_FAST_PATH_SYSTEM_PROMPT,
                temperature=0.1,
                response_mime_type="application/json",
            )
        )
        
    response = await execute_gemini_call(call_fast_path)
    return json.loads(response.text)



async def run_fast_path_pipeline_flow(
    job_id: str, redis: aioredis.Redis, pool, raw_text: str, cleaned: str, wc: int,
    url_hash: str | None, input_url: str | None, user_id: str,
    start_time: float, fetch_time: float, model_call_time: float, http_client=None
) -> None:
    from orchestration.pipeline_router import log_lifecycle_async

    # State transition: parsing_claims
    await publish_status(redis, job_id, "parsing_claims", "Executing Fast-Path direct single-pass analysis...")
    await log_lifecycle_async(pool, job_id, "EXTRACTION_STARTED", start_time=start_time, user_id=user_id, details={"path": "fast"})

    # Insert article record
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

    try:
        fast_start = time.perf_counter()
        # 15s budget for unified LLM call
        fast_result = await asyncio.wait_for(run_fast_path_pipeline(cleaned, input_url), timeout=15.0)
        model_call_time += (time.perf_counter() - fast_start)
    except Exception as e:
        logger.warning("Fast-path pipeline failed or timed out: %s. Falling back to Recovery Path.", e)
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, f"Fast-path failed or timed out: {e}"
        )
        return

    # Save bias, claims, verdicts...
    await publish_status(redis, job_id, "generating_verdict", "Saving fast-path results...")
    
    # Save bias
    bias_data = fast_result.get("bias", {})
    bias_score = max(0, min(100, int(bias_data.get("bias_score", 50))))
    bias_direction = bias_data.get("bias_direction", "neutral")
    framing_flags = bias_data.get("framing_flags", [])
    loaded_terms = bias_data.get("loaded_terms", [])
    bias_summary = bias_data.get("summary", "")
    
    await queries.insert_bias_result(
        pool, job_id, article_id,
        bias_score, bias_direction,
        framing_flags, loaded_terms, bias_summary
    )
    await publish_event(redis, job_id, "bias_scored", {
        "bias_score": bias_score,
        "bias_direction": bias_direction,
        "framing_flags": framing_flags,
        "loaded_terms": loaded_terms,
        "summary": bias_summary
    })
    
    # Save claims (capped at MAX_CLAIMS_FAST to enforce global limit)
    temp_to_real_id: dict[str, str] = {}
    claims_list = []
    inserted_claim_data: list[tuple[str, str, str | None]] = []  # (claim_id, text, claim_type)

    raw_claims = fast_result.get("claims", [])
    if len(raw_claims) > MAX_CLAIMS_FAST:
        logger.info("[FAST] Capping claims %d → %d (MAX_CLAIMS_FAST)", len(raw_claims), MAX_CLAIMS_FAST)
        raw_claims = raw_claims[:MAX_CLAIMS_FAST]

    for c in raw_claims:
        temp_id = c.get("temp_id", "c1")
        text = c.get("text", "")
        context_quote = c.get("context_quote", "")
        claim_type = c.get("claim_type", "event")
        checkability = c.get("checkability", "medium")
        
        claim_id = await queries.insert_claim(
            pool, job_id, article_id,
            text, context_quote, claim_type, checkability, None
        )
        temp_to_real_id[temp_id] = claim_id
        claims_list.append({
            "claim_id": claim_id,
            "text": text,
            "claim_type": claim_type,
            "checkability": checkability
        })
        inserted_claim_data.append((claim_id, text, claim_type))
        
    await publish_event(redis, job_id, "claims_extracted", {
        "claims": claims_list,
        "extraction_notes": "Fast-path single-stage claim extraction."
    })

    # ── Lightweight article-level source pool (1 SerpAPI call total) ─────────
    # Runs after claims are inserted. Bounded to 8s total. Snippet-only.
    # Distributes pool sources to claims by lexical overlap — no per-claim searches.
    if inserted_claim_data and http_client is not None:
        await publish_status(redis, job_id, "verifying_sources", "Retrieving verification sources...")
        # Build ClaimSchema objects for pool builder
        pool_claims = [
            ClaimSchema(claim_id=cid, text=ctext, claim_type=ctype, checkability="medium")
            for cid, ctext, ctype in inserted_claim_data
        ]
        pool_sources: dict[str, ClaimSourcesResult] = {}
        try:
            from agents.article_source_pool import build_article_source_pool
            pool_sources = await asyncio.wait_for(
                build_article_source_pool(
                    article_text=cleaned,
                    article_url=input_url,
                    claims=pool_claims,
                    redis=redis,
                    http_client=http_client,
                    max_queries=SOURCE_QUERIES_FAST,
                    max_pool_size=6,
                    max_sources_per_claim=MAX_SOURCES_PER_CLAIM_FAST,
                ),
                timeout=SOURCE_POOL_TIMEOUT_FAST,
            )
        except asyncio.TimeoutError:
            logger.warning("[FAST-PATH] Source pool timeout — skipping sources.")
        except Exception as e:
            logger.warning("[FAST-PATH] Source pool failed: %s — skipping sources.", e)

        for cid, s_result in pool_sources.items():
            if not s_result.sources:
                continue
            saved_sources = []
            for s in s_result.sources:
                sid = await queries.insert_source(
                    pool, cid, s.url, s.title, s.domain,
                    s.snippet, s.full_text, s.stance,
                    s.quality_score or 0.0, s.fetch_status or "success"
                )
                s.source_id = sid
                saved_sources.append({
                    "source_id": sid,
                    "url": s.url,
                    "title": s.title,
                    "domain": s.domain,
                    "snippet": s.snippet,
                    "stance": s.stance,
                    "quality_score": s.quality_score,
                    "fetch_status": s.fetch_status,
                })
            await publish_event(redis, job_id, "claim_sourced", {
                "claim_id": cid,
                "sources": saved_sources,
            })
            logger.info(
                "[FAST-PATH] Sources saved | Claim: %s | Count: %d",
                cid[:8], len(saved_sources)
            )
    elif not http_client:
        logger.warning("[FAST-PATH] http_client not available — skipping source retrieval.")
    # ── End source collection ─────────────────────────────────────────────────

    # Save verdicts
    verdict_data = fast_result.get("verdict", {})
    overall_verdict = verdict_data.get("overall_verdict", "UNVERIFIABLE")
    overall_confidence = float(verdict_data.get("overall_confidence", 0.5))
    overall_summary = verdict_data.get("overall_summary", "")
    
    mapped_claim_verdicts = []
    for cv in verdict_data.get("claim_verdicts", []):
        temp_id = cv.get("temp_id")
        real_cid = temp_to_real_id.get(temp_id)
        if real_cid:
            verdict = cv.get("verdict", "UNVERIFIABLE")
            confidence = float(cv.get("confidence", 0.5))
            reasoning = cv.get("reasoning", "")
            await queries.insert_verdict(
                pool, job_id, real_cid,
                verdict, confidence, reasoning, False
            )
            mapped_claim_verdicts.append({
                "claim_id": real_cid,
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": reasoning
            })
            
    await queries.insert_verdict(
        pool, job_id, None,
        overall_verdict, overall_confidence, overall_summary, True
    )
    
    await publish_event(redis, job_id, "verdict", {
        "overall_verdict": overall_verdict,
        "overall_confidence": overall_confidence,
        "overall_summary": overall_summary,
        "claim_verdicts": mapped_claim_verdicts,
    })
    
    await queries.update_job_status(pool, job_id, "COMPLETE")
    await publish_status(redis, job_id, "completed", "Job successfully analyzed.")
    await log_lifecycle_async(pool, job_id, "JOB_COMPLETED", start_time=start_time, user_id=user_id, details={
        "path": "fast",
        "verdict": overall_verdict
    })
    await publish_done(redis, job_id)
    
    # Print diagnostics
    total_time = time.perf_counter() - start_time
    proc_time = total_time - fetch_time
    logger.info(
        "\n[DIAGNOSTICS] Job %s (FAST-PATH) Performance Metrics:\n"
        "- Fetch Time: %.3fs\n"
        "- Model Call Time: %.3fs\n"
        "- Processing Time: %.3fs\n"
        "- Total Job Time: %.3fs\n",
        job_id, fetch_time, model_call_time, proc_time, total_time
    )
