import asyncio
import logging
import time
import redis.asyncio as aioredis
from google.genai import types
import json

from config import settings
from db import queries
from models.schemas import BiasResult, JudgeResult
from agents.bias_scorer import score_bias
from services.gemini import execute_gemini_call, gemini_manager
from services.redis_publisher import publish_status, publish_event, publish_done

logger = logging.getLogger("truthstream.ai.recovery")

async def auto_summarize(text: str) -> str:
    """Summarize a long article using Gemini to make it concise (under 500 words)."""
    user_prompt = (
        "Summarize the following long article to a concise summary focusing on its core factual assertions, "
        "statistics, and checkable claims. Keep the summary under 500 words.\n\n"
        f"<article_text>\n{text[:60000]}\n</article_text>"
    )
    
    async def call_summarizer(client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a professional fact-checker assistant. Summarize the text as requested.",
                temperature=0.2,
            )
        )
    try:
        response = await execute_gemini_call(call_summarizer)
        return response.text
    except Exception as e:
        logger.error("Auto-summarization failed: %s. Using simple text truncation instead.", e)
        words = text.split()
        return " ".join(words[:500])


async def run_best_effort_verdict(article_text: str, bias_result: BiasResult, explanation: str = "") -> JudgeResult:
    """Generate a best-effort overall verdict when claim extraction is unavailable or skipped."""
    user_prompt = (
        "Analyze the following article text and produce a best-effort overall verdict, confidence, and summary "
        "explaining why individual claims could not be fact-checked (e.g. parsing failed, or text was too complex/unstructured).\n"
        f"Failure context: {explanation}\n\n"
        f"Article content:\n{article_text[:15000]}"
    )
    
    async def call_best_effort(client):
        return await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a professional fact-checking editor. Return a best-effort overall verdict as JSON "
                    "using this schema: {\"overall_verdict\": \"MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE\", "
                    "\"overall_confidence\": float (0.0-1.0), \"overall_summary\": \"string\"}"
                ),
                temperature=0.2,
                response_mime_type="application/json",
            )
        )
    try:
        response = await execute_gemini_call(call_best_effort)
        data = json.loads(response.text)
        return JudgeResult(
            overall_verdict=data.get("overall_verdict", "UNVERIFIABLE"),
            overall_confidence=float(data.get("overall_confidence", 0.5)),
            overall_summary=data.get("overall_summary", "Best-effort verdict generated directly from article text."),
            claim_verdicts=[]
        )
    except Exception as e:
        logger.error("Best-effort verdict generation failed: %s", e)
        return JudgeResult(
            overall_verdict="UNVERIFIABLE",
            overall_confidence=0.1,
            overall_summary="Could not analyze the article content to produce a verdict.",
            claim_verdicts=[]
        )


async def run_recovery_pipeline_flow(
    job_id: str, redis: aioredis.Redis, pool, raw_text: str, cleaned: str, wc: int,
    url_hash: str | None, input_url: str | None, user_id: str,
    start_time: float, fetch_time: float, model_call_time: float, explanation: str
) -> None:
    # We defer logging import to avoid circular dependency, but we can import log_lifecycle_async dynamically
    from orchestration.pipeline_router import log_lifecycle_async

    # State transition: generating_verdict
    await publish_status(redis, job_id, "generating_verdict", "Executing best-effort recovery analysis...")
    await log_lifecycle_async(pool, job_id, "EXTRACTION_STARTED", start_time=start_time, user_id=user_id, details={"path": "recovery", "reason": explanation})

    # Insert article if it doesn't exist
    article_id = await queries.insert_article(
        pool,
        url=input_url,
        url_hash=url_hash,
        raw_text=raw_text[:50000],
        cleaned_text=cleaned,
        truncated=True,
        word_count=wc,
    )
    await queries.update_job_article(pool, job_id, article_id)

    # Score bias (timeout: 10s)
    bias_result = None
    if not gemini_manager.is_degraded():
        try:
            bias_start = time.perf_counter()
            bias_result = await asyncio.wait_for(score_bias(cleaned, input_url), timeout=10.0)
            model_call_time += (time.perf_counter() - bias_start)
        except Exception as e:
            logger.error("Bias scoring failed in recovery: %s", e)
            
    if not bias_result:
        bias_result = BiasResult(
            bias_score=50, bias_direction="neutral", framing_flags=[], loaded_terms=[], summary="Bias analysis unavailable due to AI capacity limit."
        )

    # Insert bias
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

    # Run best effort verdict (timeout: 10s)
    judge_result = None
    if not gemini_manager.is_degraded():
        try:
            judge_start = time.perf_counter()
            judge_result = await asyncio.wait_for(run_best_effort_verdict(cleaned, bias_result, explanation), timeout=10.0)
            model_call_time += (time.perf_counter() - judge_start)
        except Exception as e:
            logger.error("Best effort verdict failed in recovery: %s", e)

    if not judge_result:
        judge_result = JudgeResult(
            overall_verdict="UNVERIFIABLE",
            overall_confidence=0.0,
            overall_summary=f"AI Capacity Limited. Verification is unavailable at this time. (Reason: {explanation})",
            claim_verdicts=[]
        )

    await queries.insert_verdict(
        pool, job_id, None,
        judge_result.overall_verdict, judge_result.overall_confidence,
        judge_result.overall_summary + f" (Recovery mode active: {explanation})", True
    )

    await queries.update_job_status(pool, job_id, "PARTIAL")
    status_msg = "Analysis completed with recovery fallback."
    if gemini_manager.is_degraded():
        status_msg = "⚠️ Provider Cooling Down: AI Capacity Limited. Retry Available Soon."
    await publish_status(redis, job_id, "partial_completed", status_msg)

    await publish_event(redis, job_id, "verdict", {
        "overall_verdict": judge_result.overall_verdict,
        "overall_confidence": judge_result.overall_confidence,
        "overall_summary": judge_result.overall_summary + f" (Recovery mode active: {explanation})",
        "claim_verdicts": [],
    })
    await log_lifecycle_async(pool, job_id, "JOB_COMPLETED", start_time=start_time, user_id=user_id, details={
        "path": "recovery",
        "verdict": judge_result.overall_verdict
    })
    await publish_done(redis, job_id)

    # Log diagnostics
    total_time = time.perf_counter() - start_time
    proc_time = total_time - fetch_time
    logger.info(
        "\n[DIAGNOSTICS] Job %s (RECOVERY) Performance Metrics:\n"
        "- Fetch Time: %.3fs\n"
        "- Model Call Time: %.3fs\n"
        "- Processing Time: %.3fs\n"
        "- Total Job Time: %.3fs\n",
        job_id, fetch_time, model_call_time, proc_time, total_time
    )
