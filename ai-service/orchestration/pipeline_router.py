import asyncio
import logging
import time
import datetime
import redis.asyncio as aioredis

from db import queries
from services.redis_publisher import (
    publish_status, publish_event, publish_error, publish_done
)
from services.scraper import fetch_article_url
from utils.text import clean_text, md5_hash, word_count, classify_article_complexity

# Defer imports of pipelines to avoid circular references if any, but since they are acyclic we can import them directly
from orchestration.pipelines.fast import run_fast_path_pipeline_flow
from orchestration.pipelines.standard import run_standard_path_pipeline_flow
from orchestration.pipelines.deep import run_deep_path_pipeline_flow
from orchestration.pipelines.recovery import run_recovery_pipeline_flow

logger = logging.getLogger("truthstream.ai.router")

async def log_lifecycle_async(pool, job_id: str, action: str, start_time: float = None, details: dict = None, user_id: str = None) -> None:
    """Consistently emits stdout diagnostics and writes execution logs into postgres."""
    elapsed = 0.0
    if start_time is not None:
        elapsed = time.perf_counter() - start_time
    
    details_str = f" | DETAILS: {details}" if details else ""
    logger.info("[LIFECYCLE] [JOB_ID: %s] [ACTION: %s] [ELAPSED: %.3fs]%s", job_id, action, elapsed, details_str)
    
    try:
        await queries.insert_audit_log(pool, job_id, user_id, action, details)
    except Exception as e:
        logger.error("Failed to write lifecycle audit log to DB for job %s: %s", job_id, e)


async def _fail_job(pool, redis: aioredis.Redis, job_id: str, message: str) -> None:
    try:
        await queries.update_job_status_error(pool, job_id, "FAILED", message)
    except Exception:
        pass
    await publish_error(redis, job_id, message)
    await publish_done(redis, job_id)


async def reuse_completed_job(pool, new_job_id: str, old_job_id: str, article_id: str, user_id: str, redis) -> bool:
    """Clones the old job's completed results (bias, claims, sources, verdicts) to the new job and publishes events."""
    import json
    logger.info("Cloning cached complete job %s to new job %s", old_job_id, new_job_id)
    try:
        async with pool.acquire() as conn:
            # 1. Clone bias result
            bias_row = await conn.fetchrow(
                "SELECT * FROM bias_results WHERE job_id = $1::uuid", old_job_id
            )
            if bias_row:
                await queries.insert_bias_result(
                    pool, new_job_id, article_id,
                    bias_row["bias_score"], bias_row["bias_direction"],
                    bias_row["framing_flags"] if isinstance(bias_row["framing_flags"], list) else json.loads(bias_row["framing_flags"]),
                    bias_row["loaded_terms"], bias_row["summary"]
                )
                await publish_event(redis, new_job_id, "bias_scored", {
                    "bias_score": bias_row["bias_score"],
                    "bias_direction": bias_row["bias_direction"],
                    "framing_flags": bias_row["framing_flags"] if isinstance(bias_row["framing_flags"], list) else json.loads(bias_row["framing_flags"]),
                    "loaded_terms": bias_row["loaded_terms"],
                    "summary": bias_row["summary"]
                })

            # 2. Clone claims
            claims_rows = await conn.fetch(
                "SELECT * FROM claims WHERE job_id = $1::uuid", old_job_id
            )
            temp_to_real_id = {}
            claims_data = []
            for c in claims_rows:
                old_claim_id = str(c["id"])
                new_claim_id = await queries.insert_claim(
                    pool, new_job_id, article_id,
                    c["text"], c["context_quote"],
                    c["claim_type"], c["checkability"],
                    c["embedding"]
                )
                temp_to_real_id[old_claim_id] = new_claim_id
                claims_data.append({
                    "claim_id": new_claim_id,
                    "text": c["text"],
                    "claim_type": c["claim_type"],
                    "checkability": c["checkability"]
                })

            if claims_data:
                await publish_event(redis, new_job_id, "claims_extracted", {
                    "claims": claims_data,
                    "extraction_notes": "Reused from cached fact-check result."
                })

                # 3. For each claim, clone sources & verdicts
                for old_claim_id, new_claim_id in temp_to_real_id.items():
                    sources_rows = await conn.fetch(
                        "SELECT * FROM sources WHERE claim_id = $1::uuid", old_claim_id
                    )
                    new_sources = []
                    for s in sources_rows:
                        sid = await queries.insert_source(
                            pool, new_claim_id, s["url"], s["title"], s["domain"],
                            s["snippet"], s["full_text"], s["stance"],
                            float(s["quality_score"]) if s["quality_score"] is not None else 0.0,
                            s["fetch_status"]
                        )
                        new_sources.append({
                            "source_id": sid,
                            "url": s["url"],
                            "title": s["title"],
                            "domain": s["domain"],
                            "snippet": s["snippet"],
                            "stance": s["stance"],
                            "quality_score": float(s["quality_score"]) if s["quality_score"] is not None else 0.0,
                            "fetch_status": s["fetch_status"]
                        })

                    await publish_event(redis, new_job_id, "claim_sourced", {
                        "claim_id": new_claim_id,
                        "sources": new_sources
                    })

                    # Copy claim verdicts
                    verdict_row = await conn.fetchrow(
                        "SELECT * FROM verdicts WHERE job_id = $1::uuid AND claim_id = $2::uuid",
                        old_job_id, old_claim_id
                    )
                    if verdict_row:
                        await queries.insert_verdict(
                            pool, new_job_id, new_claim_id,
                            verdict_row["verdict"], float(verdict_row["confidence"]),
                            verdict_row["reasoning"], False
                        )

            # 4. Clone overall verdict
            overall_verdict_row = await conn.fetchrow(
                "SELECT * FROM verdicts WHERE job_id = $1::uuid AND is_overall = TRUE",
                old_job_id
            )
            if overall_verdict_row:
                await queries.insert_verdict(
                    pool, new_job_id, None,
                    overall_verdict_row["verdict"], float(overall_verdict_row["confidence"]),
                    overall_verdict_row["reasoning"], True
                )
                
                # Fetch new claim verdicts for verdict SSE event
                claim_verdicts_rows = await conn.fetch(
                    "SELECT * FROM verdicts WHERE job_id = $1::uuid AND is_overall = FALSE",
                    new_job_id
                )
                claim_verdicts = [{
                    "claim_id": str(cv["claim_id"]),
                    "verdict": cv["verdict"],
                    "confidence": float(cv["confidence"]),
                    "reasoning": cv["reasoning"]
                } for cv in claim_verdicts_rows]

                await publish_event(redis, new_job_id, "verdict", {
                    "overall_verdict": overall_verdict_row["verdict"],
                    "overall_confidence": float(overall_verdict_row["confidence"]),
                    "overall_summary": overall_verdict_row["reasoning"],
                    "claim_verdicts": claim_verdicts
                })

        await queries.update_job_status(pool, new_job_id, "COMPLETE")
        await queries.insert_audit_log(pool, new_job_id, user_id, "JOB_COMPLETED_CACHE_REUSED", {
            "old_job_id": old_job_id,
            "article_id": article_id
        })
        await publish_done(redis, new_job_id)
        return True
    except Exception as e:
        logger.exception("Failed to clone completed job %s: %s", old_job_id, e)
        return False


async def route_and_execute_pipeline(job_id: str, redis: aioredis.Redis, pool, http_client) -> None:
    from services.gemini import job_id_var, job_call_counter
    job_id_token = job_id_var.set(job_id)
    job_call_token = job_call_counter.set(0)
    try:
        await _route_and_execute_pipeline_impl(job_id, redis, pool, http_client)
    finally:
        job_id_var.reset(job_id_token)
        job_call_counter.reset(job_call_token)


async def _route_and_execute_pipeline_impl(job_id: str, redis: aioredis.Redis, pool, http_client) -> None:
    """Internal fact-checking pipeline logic with stage timeouts, complexity routing, and caching."""
    start_time = time.perf_counter()
    model_call_time = 0.0
    fetch_time = 0.0

    # Fetch job from DB with retry to handle transaction race conditions
    job = None
    db_fetch_start = time.perf_counter()
    for attempt in range(5):
        try:
            job = await queries.get_job(pool, job_id)
            if job:
                break
        except Exception as e:
            logger.warning("Job %s DB fetch attempt %d/5 failed: %s", job_id, attempt + 1, e)
        if not job and attempt < 4:
            logger.warning("Job %s not found in DB (attempt %d/5). Retrying in 0.5s...", job_id, attempt + 1)
            await asyncio.sleep(0.5)
    
    db_fetch_duration = time.perf_counter() - db_fetch_start
    logger.info("[INSTRUMENTATION] Job %s DB_FETCH_COMPLETED | Duration: %.3fs", job_id, db_fetch_duration)
    await log_lifecycle_async(pool, job_id, "DB_FETCH_COMPLETED", 
        details={"duration_ms": round(db_fetch_duration * 1000), "attempts": attempt + 1})

    if not job:
        logger.error("Job %s not found in DB after 5 attempts", job_id)
        await _fail_job(pool, redis, job_id, "Job metadata not found in database.")
        return

    user_id = str(job["user_id"])
    input_url = job["input_url"]
    input_text = job["input_text"]

    # Calculate queue time: difference between created_at and now
    queue_time = 0.0
    if job.get("created_at"):
        now = datetime.datetime.now(datetime.timezone.utc)
        created_at = job["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        queue_time = (now - created_at).total_seconds()

    await log_lifecycle_async(pool, job_id, "PIPELINE_STARTED", start_time=start_time, user_id=user_id, details={
        "input_type": "url" if input_url else "text",
        "queue_time": queue_time
    })
    await queries.update_job_status(pool, job_id, "PROCESSING")
    await publish_status(redis, job_id, "fetching", "Fetching article content...")
    await log_lifecycle_async(pool, job_id, "PARSER_STARTED", start_time=start_time, user_id=user_id)

    url_hash = md5_hash(input_url) if input_url else None
    cached_article = None

    # Check for caching/reuse: duplicate URL fact-checked previously
    if url_hash:
        cache_check_start = time.perf_counter()
        cached_article = await queries.find_article_by_url_hash(pool, url_hash)
        cache_check_duration = time.perf_counter() - cache_check_start
        logger.info("[INSTRUMENTATION] Job %s CACHE_CHECK_COMPLETED | Duration: %.3fs | Found: %s", 
            job_id, cache_check_duration, cached_article is not None)
        await log_lifecycle_async(pool, job_id, "CACHE_CHECK_COMPLETED",
            details={"duration_ms": round(cache_check_duration * 1000), "hit": cached_article is not None})
        
        if cached_article:
            async with pool.acquire() as conn:
                completed_job_row = await conn.fetchrow(
                    "SELECT id FROM jobs WHERE article_id = $1::uuid AND status = 'COMPLETE' ORDER BY created_at DESC LIMIT 1",
                    cached_article["id"]
                )
                if completed_job_row:
                    old_job_id = str(completed_job_row["id"])
                    article_id = str(cached_article["id"])
                    await queries.update_job_article(pool, job_id, article_id)
                    cloned = await reuse_completed_job(pool, job_id, old_job_id, article_id, user_id, redis)
                    if cloned:
                        total_time = time.perf_counter() - start_time
                        logger.info(
                            "\n[DIAGNOSTICS] Job %s (CACHE-REUSED) Performance Metrics:\n"
                            "- Queue Time: %.3fs\n"
                            "- Fetch Time: 0.000s\n"
                            "- Model Call Time: 0.000s\n"
                            "- Processing Time: %.3fs\n"
                            "- Total Job Time: %.3fs\n"
                            "- Routing Path: Cache-Reused\n",
                            job_id, queue_time, total_time, total_time
                        )
                        return

    # ── Step 1: Fetch article ──
    raw_text = ""
    cleaned = ""
    if input_url:
        if cached_article:
            raw_text = cached_article["raw_text"]
            cleaned = cached_article["cleaned_text"]
            logger.info("Reusing cached article text for URL: %s", input_url)
        else:
            try:
                fetch_start = time.perf_counter()
                # 8s Timeout for URL fetching
                raw_text, _ = await asyncio.wait_for(fetch_article_url(input_url, http_client), timeout=8.0)
                fetch_time = time.perf_counter() - fetch_start
                logger.info("[INSTRUMENTATION] Job %s URL_FETCH_COMPLETED | Duration: %.3fs", job_id, fetch_time)
                await log_lifecycle_async(pool, job_id, "URL_FETCH_COMPLETED",
                    details={"duration_ms": round(fetch_time * 1000)})
            except asyncio.TimeoutError:
                logger.error("[INSTRUMENTATION] Job %s URL_FETCH_TIMEOUT | Duration: 8.000s", job_id)
                await _fail_job(pool, redis, job_id, "Article fetch timed out (8s limit).")
                return
            except Exception as e:
                logger.error("[INSTRUMENTATION] Job %s URL_FETCH_FAILED | Error: %s", job_id, e)
                await _fail_job(pool, redis, job_id, f"Could not fetch article: {e}")
                return
    else:
        raw_text = input_text or ""

    if not cleaned:
        if len(raw_text.strip()) < 100:
            await _fail_job(pool, redis, job_id, "Article content too short or inaccessible.")
            return
        await publish_status(redis, job_id, "extracting", "Parsing and cleaning text content...")
        
        # Phase 4: Make text cleaning async to avoid event loop blocking
        text_clean_start = time.perf_counter()
        cleaned = await asyncio.to_thread(clean_text, raw_text)
        text_clean_duration = time.perf_counter() - text_clean_start
        if text_clean_duration > 0.1:
            logger.warning("[INSTRUMENTATION] Job %s TEXT_CLEAN_SLOW | Duration: %.3fs (potential event loop blocking)", 
                job_id, text_clean_duration)
        else:
            logger.info("[INSTRUMENTATION] Job %s TEXT_CLEAN_COMPLETED | Duration: %.3fs", job_id, text_clean_duration)
        await log_lifecycle_async(pool, job_id, "TEXT_CLEAN_COMPLETED",
            details={"duration_ms": round(text_clean_duration * 1000)})
    
    # State transition: routing
    await publish_status(redis, job_id, "routing", "Classifying article complexity...")
    
    # INSTRUMENTATION: Measure complexity classification (also async)
    complexity_start = time.perf_counter()
    wc = word_count(cleaned)
    complexity = await asyncio.to_thread(classify_article_complexity, cleaned)
    complexity_duration = time.perf_counter() - complexity_start
    logger.info("[INSTRUMENTATION] Job %s COMPLEXITY_CLASSIFIED | Duration: %.3fs | Complexity: %s | Words: %d",
        job_id, complexity_duration, complexity, wc)
    await log_lifecycle_async(pool, job_id, "COMPLEXITY_CLASSIFIED",
        details={"duration_ms": round(complexity_duration * 1000), "complexity": complexity, "word_count": wc})

    # Explicit queueing budget check: if queue_time > 15s, downgrade to Fast-Path lightweight processing
    if queue_time > 15.0 and complexity in ("standard", "deep"):
        logger.warning("Job %s queue time (%.3fs) exceeded budget (15.0s). Forcing Fast-Path mode.", job_id, queue_time)
        await publish_status(redis, job_id, "routing", "⚠️ System load high: Downgrading to fast-track mode...")
        complexity = "fast"
        words = cleaned.split()
        if len(words) > 600:
            cleaned = " ".join(words[:600])
            wc = word_count(cleaned)
            logger.info("Force-truncated text to 600 words for Fast-Path processing.")

    logger.info("Job %s text length: %d words, Complexity: %s", job_id, wc, complexity)

    # ── ROUTING PATH ──
    logger.info("[INSTRUMENTATION] Job %s PIPELINE_ROUTING | Complexity: %s | Words: %d | Path: %s",
        job_id, complexity, wc, "fast" if complexity == "fast" else "standard" if complexity == "standard" else "deep" if complexity == "deep" else "recovery")
    await log_lifecycle_async(pool, job_id, "PIPELINE_SELECTED",
        details={"complexity": complexity, "word_count": wc})
    
    # ── Degraded mode routing check ──
    from services.gemini import gemini_manager
    if gemini_manager.is_degraded():
        logger.warning("[INSTRUMENTATION] DEGRADED_MODE_BYPASS | Job: %s | AI capacity degraded, routing straight to recovery path.", job_id)
        await publish_status(redis, job_id, "routing", "⚠️ AI Capacity Limited: Routing to recovery mode...")
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, "AI service capacity is currently degraded. Circuit breaker active."
        )
        return

    if complexity == "fast":
        await publish_status(redis, job_id, "processing", "Running fast-track analysis...")
        await run_fast_path_pipeline_flow(job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id, start_time, fetch_time, model_call_time)
    elif complexity == "standard":
        await publish_status(redis, job_id, "processing", "Running standard analysis...")
        await run_standard_path_pipeline_flow(job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id, start_time, fetch_time, model_call_time, http_client)
    elif complexity == "deep":
        await publish_status(redis, job_id, "processing", "Running deep analysis...")
        await run_deep_path_pipeline_flow(job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id, start_time, fetch_time, model_call_time, http_client)
    else:
        # recovery or noisy/broken
        await publish_status(redis, job_id, "processing", "Running recovery analysis...")
        await run_recovery_pipeline_flow(
            job_id, redis, pool, raw_text, cleaned, wc, url_hash, input_url, user_id,
            start_time, fetch_time, model_call_time, "Manual recovery route triggered."
        )
