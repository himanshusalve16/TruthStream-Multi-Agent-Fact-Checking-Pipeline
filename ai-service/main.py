"""
TruthStream AI Service — main FastAPI application.
Orchestrates the multi-agent fact-checking pipeline.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict

import redis.asyncio as aioredis
from fastapi import FastAPI

from config import settings
from db.connection import init_db_pool, close_db_pool
import time
from db import queries
from routers import internal
from models.schemas import (
    JobDispatch, ClaimSchema, ClaimSourcesResult, BiasResult, JudgeResult
)
from agents.extractor import extract_claims
from agents.source_finder import find_sources
from agents.bias_scorer import score_bias
from agents.judge import run_judge
from utils.verdict_calc import compute_fallback_verdict
from services.redis_publisher import (
    publish_status, publish_event, publish_error, publish_done
)
from services.scraper import fetch_article_url
from utils.text import clean_text, truncate_text, word_count, md5_hash, classify_article_complexity
from services.embeddings import embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("truthstream.ai")

NUM_WORKERS = 3

# ──────────────────────────────────────────────────────────────
# Startup helpers with retry
# ──────────────────────────────────────────────────────────────

_DB_MAX_RETRIES = 10
_DB_RETRY_DELAY = 3.0   # seconds between attempts

_REDIS_MAX_RETRIES = 8
_REDIS_RETRY_DELAY = 2.0


async def _connect_db_with_retry(database_url: str):
    """
    Attempt to create the asyncpg pool, retrying on failure.

    Root cause this solves: Docker Compose's 'service_healthy' condition for
    the db service only guarantees that pg_isready returned OK — meaning
    Postgres is accepting connections. It does NOT guarantee that:
      - Our specific database exists yet
      - The Flyway migration (run by backend) has completed
      - A transient network hiccup isn't occurring

    Without retry, a single connection failure crashes the process.
    """
    last_error = None
    delay = 2.0
    for attempt in range(1, _DB_MAX_RETRIES + 1):
        try:
            pool = await init_db_pool(database_url)
            logger.info("Database pool connected successfully on attempt %d", attempt)
            return pool
        except Exception as exc:
            last_error = exc
            if attempt < _DB_MAX_RETRIES:
                logger.warning(
                    "DB connection attempt %d/%d failed. Retrying in %.1fs... Error: %s",
                    attempt, _DB_MAX_RETRIES, delay, exc
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 10.0)  # Exponential backoff up to 10s
            else:
                logger.error("DB connection failed permanently after %d attempts", _DB_MAX_RETRIES)
    
    logger.critical("Fatal: Could not connect to database after %d attempts. Failing gracefully to avoid infinite crash-loops.", _DB_MAX_RETRIES)
    raise SystemExit(1)


async def _connect_redis_with_retry(redis_url: str) -> aioredis.Redis:
    """
    Attempt to connect to Redis, retrying on failure.

    Root cause: even with redis healthcheck passing, the first ping from
    our code can race against Redis being ready to serve on the internal
    Docker bridge network.
    """
    last_error = None
    delay = 1.0
    for attempt in range(1, _REDIS_MAX_RETRIES + 1):
        try:
            client = aioredis.from_url(redis_url, decode_responses=False)
            await client.ping()
            logger.info("Redis connected successfully on attempt %d", attempt)
            return client
        except Exception as exc:
            last_error = exc
            if attempt < _REDIS_MAX_RETRIES:
                logger.warning(
                    "Redis connection attempt %d/%d failed. Retrying in %.1fs... Error: %s",
                    attempt, _REDIS_MAX_RETRIES, delay, exc
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, 5.0)
            else:
                logger.error("Redis connection failed permanently after %d attempts", _REDIS_MAX_RETRIES)
    
    logger.critical("Fatal: Could not connect to Redis after %d attempts. Failing gracefully.", _REDIS_MAX_RETRIES)
    raise SystemExit(1)


# ──────────────────────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────────────────────

async def cleanup_stuck_jobs(pool) -> None:
    """Startup watchdog: Clean up any jobs stuck in PENDING or PROCESSING status."""
    try:
        async with pool.acquire() as conn:
            count = await conn.execute(
                """
                UPDATE jobs
                SET status = 'FAILED',
                    error_message = 'Job terminated due to system restart.',
                    updated_at = NOW()
                WHERE status IN ('PENDING', 'PROCESSING')
                """
            )
            logger.info("Startup watchdog: swept and marked stuck jobs as FAILED: %s", count)
    except Exception as e:
        logger.error("Startup watchdog: failed to clean up stuck jobs: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    logger.info("Initializing database pool...")
    env_mode = "Docker" if settings.db_host == "db" else "Local"
    logger.info("Resolved DB Host: %s (Mode: %s)", settings.db_host, env_mode)
    logger.info("DB Port: %s", settings.db_port)
    logger.info("Connecting to PostgreSQL at %s:%s", settings.db_host, settings.db_port)
    app.state.db_pool = await _connect_db_with_retry(settings.database_url)

    # Clean up stuck jobs from previous session
    await cleanup_stuck_jobs(app.state.db_pool)

    logger.info("Connecting to Redis...")
    app.state.redis = await _connect_redis_with_retry(settings.redis_url)

    logger.info("Validating AI Provider Configuration...")
    from services.gemini import validate_gemini_model_sync
    await asyncio.to_thread(validate_gemini_model_sync)

    logger.info("Starting %d job workers...", NUM_WORKERS)
    app.state.workers = [
        asyncio.create_task(job_worker(app), name=f"worker-{i}")
        for i in range(NUM_WORKERS)
    ]

    logger.info("AI service ready.")
    yield

    # ── Shutdown ─────────────────────────────────────────────
    logger.info("Shutting down workers...")
    for w in app.state.workers:
        w.cancel()
    await asyncio.gather(*app.state.workers, return_exceptions=True)

    await close_db_pool(app.state.db_pool)
    await app.state.redis.aclose()
    logger.info("AI service stopped.")


app = FastAPI(
    title="TruthStream AI Service",
    version="1.0.0",
    description="Multi-agent fact-checking pipeline",
    lifespan=lifespan,
)

app.include_router(internal.router, prefix="/internal")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service"}


# ──────────────────────────────────────────────────────────────
# Worker loop
# ──────────────────────────────────────────────────────────────

async def job_worker(app: FastAPI):
    """BRPOP from job_queue and process each job_id."""
    redis = app.state.redis
    pool = app.state.db_pool
    logger.info("Worker started")

    while True:
        try:
            result = await redis.brpop("job_queue", timeout=2)
            if result:
                _, job_id_bytes = result
                job_id = job_id_bytes.decode()
                logger.info("Worker picked up job: %s", job_id)
                await publish_status(redis, job_id, "accepted", "Job accepted by worker thread...")
                await publish_status(redis, job_id, "spawning_agents", "Spawning fact-checking agents...")
                await process_job(job_id, redis, pool)
        except asyncio.CancelledError:
            logger.info("Worker cancelled")
            break
        except Exception as e:
            logger.error("Worker error: %s", e)
            await asyncio.sleep(1)


# ──────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────

async def auto_summarize(text: str) -> str:
    """Summarize a long article using Gemini to make it concise (under 500 words)."""
    user_prompt = (
        "Summarize the following long article to a concise summary focusing on its core factual assertions, "
        "statistics, and checkable claims. Keep the summary under 500 words.\n\n"
        f"<article_text>\n{text[:60000]}\n</article_text>"
    )
    from google.genai import types
    
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


async def run_best_effort_verdict(article_text: str, bias_result: BiasResult) -> JudgeResult:
    """Generate a best-effort overall verdict when claim extraction is unavailable or skipped."""
    user_prompt = (
        "Analyze the following article text and produce a best-effort overall verdict, confidence, and summary "
        "explaining why individual claims could not be fact-checked (e.g. parsing failed, or text was too complex/unstructured).\n\n"
        f"Article content:\n{article_text[:15000]}"
    )
    from google.genai import types
    from models.schemas import JudgeResult
    
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
        import json
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

UNIFIED_FAST_PATH_SYSTEM_PROMPT = """You are an elite, rapid fact-checker and media bias analyst.
Analyze the provided short article/text. You must perform claim extraction, bias analysis, and veracity judgment all in one single pass.

Task 1: Factual Claim Extraction
- Extract up to 3 discrete checkable factual claims (statistics, events, attribution, definition).
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
    from google.genai import types
    import json
    
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

async def process_job(job_id: str, redis: aioredis.Redis, pool) -> None:
    """Full fact-checking pipeline for a single job with global 120s watchdog."""
    logger.info("Processing job: %s", job_id)
    try:
        # Global 120-second watchdog
        await asyncio.wait_for(_process_job_inner(job_id, redis, pool), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("Job %s timed out globally (120s limit exceeded)", job_id)
        await _fail_job(pool, redis, job_id, "Job processing exceeded maximum allowed time (120s limit).")
    except Exception as e:
        logger.exception("Unhandled error processing job %s: %s", job_id, e)
        await _fail_job(pool, redis, job_id, f"Internal pipeline error: {str(e)[:200]}")


async def _process_job_inner(job_id: str, redis: aioredis.Redis, pool) -> None:
    """Internal fact-checking pipeline logic with stage timeouts, complexity routing, and caching."""
    start_time = time.perf_counter()
    model_call_time = 0.0
    fetch_time = 0.0

    # Fetch job from DB
    job = await queries.get_job(pool, job_id)
    if not job:
        logger.error("Job %s not found in DB", job_id)
        return

    user_id = str(job["user_id"])
    input_url = job["input_url"]
    input_text = job["input_text"]

    # Calculate queue time: difference between created_at and now
    queue_time = 0.0
    if job.get("created_at"):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        created_at = job["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=datetime.timezone.utc)
        queue_time = (now - created_at).total_seconds()

    await queries.insert_audit_log(pool, job_id, user_id, "JOB_STARTED", {
        "input_type": "url" if input_url else "text",
        "queue_time": queue_time
    })
    await queries.update_job_status(pool, job_id, "PROCESSING")
    await publish_status(redis, job_id, "fetching_article", "Fetching article content...")

    url_hash = md5_hash(input_url) if input_url else None
    cached_article = None

    # Check for caching/reuse: duplicate URL fact-checked previously
    if url_hash:
        cached_article = await queries.find_article_by_url_hash(pool, url_hash)
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
                raw_text, _ = await asyncio.wait_for(fetch_article_url(input_url), timeout=8.0)
                fetch_time = time.perf_counter() - fetch_start
            except asyncio.TimeoutError:
                await _fail_job(pool, redis, job_id, "Article fetch timed out (8s limit).")
                return
            except Exception as e:
                await _fail_job(pool, redis, job_id, f"Could not fetch article: {e}")
                return
    else:
        raw_text = input_text or ""

    if not cleaned:
        if len(raw_text.strip()) < 100:
            await _fail_job(pool, redis, job_id, "Article content too short or inaccessible.")
            return
        await publish_status(redis, job_id, "extracting_content", "Parsing and cleaning text content...")
        cleaned = clean_text(raw_text)
    
    wc = word_count(cleaned)
    complexity = classify_article_complexity(cleaned)

    # Explicit queueing budget check: if queue_time > 15s, downgrade to Fast-Path lightweight processing
    if queue_time > 15.0:
        logger.warning("Job %s queue time (%.3fs) exceeded budget (15.0s). Forcing Fast-Path mode.", job_id, queue_time)
        await publish_status(redis, job_id, "spawning_agents", "⚠️ System load high: Switching to lightweight fast-track verification mode...")
        complexity = "short/simple"
        words = cleaned.split()
        if len(words) > 600:
            cleaned = " ".join(words[:600])
            wc = word_count(cleaned)
            logger.info("Force-truncated text to 600 words for Fast-Path processing.")

    logger.info("Job %s text length: %d words, Complexity: %s", job_id, wc, complexity)

    if complexity == "broken/noisy":
        await _fail_job(pool, redis, job_id, "Article content is too short, noisy, or empty.")
        return

    # ── ROUTING PATH ──
    
    # ── Path A: Fast-Path for Short Articles ──
    if complexity == "short/simple":
        await publish_status(redis, job_id, "extracting_claims", "Executing Fast-Path direct analysis...")
        
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
            logger.warning("Fast-path pipeline failed or timed out: %s. Falling back to standard pipeline.", e)
            complexity = "medium"

        if complexity == "short/simple":
            await publish_status(redis, job_id, "finalizing", "Saving fast-path results...")
            
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
            
            # Save claims
            temp_to_real_id = {}
            claims_list = []
            for c in fast_result.get("claims", []):
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
                
            await publish_event(redis, job_id, "claims_extracted", {
                "claims": claims_list,
                "extraction_notes": "Fast-path single-stage claim extraction."
            })
            
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
            await queries.insert_audit_log(pool, job_id, user_id, "JOB_COMPLETED_FAST_PATH", {
                "overall_verdict": overall_verdict,
                "overall_confidence": overall_confidence
            })
            await publish_done(redis, job_id)
            
            # Print performance metrics
            end_time = time.perf_counter()
            total_time = end_time - start_time
            proc_time = total_time - fetch_time
            logger.info(
                "\n[DIAGNOSTICS] Job %s (FAST-PATH) Performance Metrics:\n"
                "- Queue Time: %.3fs\n"
                "- Fetch Time: %.3fs\n"
                "- Model Call Time: %.3fs\n"
                "- Processing Time: %.3fs\n"
                "- Total Job Time: %.3fs\n"
                "- Routing Path: Fast-Path\n",
                job_id, queue_time, fetch_time, model_call_time, proc_time, total_time
            )
            return

    # ── Path B: Standard/Medium/Long Pipeline ──
    is_fallback_active = False
    original_cleaned = cleaned

    if complexity == "long/complex":
        logger.info("Job %s exceeds 1800 words or is long/complex. Auto-summarizing...", job_id)
        await publish_status(redis, job_id, "extracting_claims", "⚠️ Fallback: Auto-summarizing large article to cap latency...")
        try:
            summarize_start = time.perf_counter()
            # 10s Timeout for summarization stage
            summary = await asyncio.wait_for(auto_summarize(cleaned), timeout=10.0)
            model_call_time += (time.perf_counter() - summarize_start)
            cleaned = summary
            is_fallback_active = True
            logger.info("Job %s: Auto-summarization complete. Summary word count: %d", job_id, word_count(cleaned))
        except Exception as e:
            logger.warning("Job %s: Auto-summarization failed/timed out: %s. Truncating to 500 words instead.", job_id, e)
            words = cleaned.split()
            cleaned = " ".join(words[:500])

    cleaned, truncated = truncate_text(cleaned)

    # Insert article
    article_id = await queries.insert_article(
        pool,
        url=input_url,
        url_hash=url_hash,
        raw_text=raw_text[:50000],
        cleaned_text=cleaned,
        truncated=truncated or is_fallback_active,
        word_count=word_count(cleaned),
    )
    await queries.update_job_article(pool, job_id, article_id)

    await publish_status(redis, job_id, "extracting_claims", "Analyzing article for claims...")

    # Extract claims
    claims = []
    extraction_notes = "Standard extraction."
    try:
        extract_start = time.perf_counter()
        # 10s Timeout for Claim Extraction
        extraction_result = await asyncio.wait_for(extract_claims(cleaned, input_url), timeout=10.0)
        model_call_time += (time.perf_counter() - extract_start)
        claims = extraction_result.claims
        extraction_notes = extraction_result.extraction_notes
        
        # Limit the number of claims based on complexity to speed up downstream stages
        max_claims = 3 if complexity == "medium" else 4
        if len(claims) > max_claims:
            logger.info("Limiting extracted claims from %d to %d (Complexity: %s)", len(claims), max_claims, complexity)
            claims = claims[:max_claims]
    except Exception as e:
        logger.warning("Job %s: Claim extraction failed or timed out (%s). Falling back to Tier 3 overall verdict.", job_id, e)
        await publish_status(redis, job_id, "judging", "⚠️ Fallback: Claim extraction failed. Generating best-effort verdict...")

    # If claim extraction yielded no claims or failed, run Tier 3 Best-Effort Overall Verdict
    if not claims:
        logger.info("Job %s: No claims found or extraction failed. Running best-effort verdict.", job_id)
        try:
            bias_start = time.perf_counter()
            # 10s Timeout for bias scoring
            bias_result = await asyncio.wait_for(score_bias(cleaned, input_url), timeout=10.0)
            model_call_time += (time.perf_counter() - bias_start)
        except Exception as e:
            logger.error("Job %s: Bias scoring failed/timed out during best-effort path: %s", job_id, e)
            bias_result = BiasResult(
                bias_score=50, bias_direction="neutral", framing_flags=[], loaded_terms=[], summary="Bias analysis unavailable."
            )

        # Save bias
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

        # Run best-effort overall verdict
        try:
            judge_start = time.perf_counter()
            # 10s Timeout for best-effort verdict
            judge_result = await asyncio.wait_for(run_best_effort_verdict(cleaned, bias_result), timeout=10.0)
            model_call_time += (time.perf_counter() - judge_start)
        except Exception as e:
            logger.error("Job %s: Best-effort verdict timed out or failed: %s", job_id, e)
            from models.schemas import JudgeResult
            judge_result = JudgeResult(
                overall_verdict="UNVERIFIABLE",
                overall_confidence=0.1,
                overall_summary="Verification skipped due to article complexity or processing timeout.",
                claim_verdicts=[]
            )

        await publish_status(redis, job_id, "finalizing", "Saving best-effort verdict...")

        await queries.insert_verdict(
            pool, job_id, None,
            judge_result.overall_verdict, judge_result.overall_confidence,
            judge_result.overall_summary + (" (Best-effort verdict generated directly; claim parsing was unavailable.)"), True
        )

        await queries.update_job_status(pool, job_id, "PARTIAL")
        await queries.insert_audit_log(pool, job_id, user_id, "JOB_COMPLETED_PARTIAL", {
            "overall_verdict": judge_result.overall_verdict,
            "overall_confidence": judge_result.overall_confidence,
            "reason": "Claim extraction failed or returned no claims."
        })

        await publish_event(redis, job_id, "verdict", {
            "overall_verdict": judge_result.overall_verdict,
            "overall_confidence": judge_result.overall_confidence,
            "overall_summary": judge_result.overall_summary + " (Best-effort verdict; claim parsing was unavailable.)",
            "claim_verdicts": [],
        })
        await publish_done(redis, job_id)
        
        # Log diagnostics
        end_time = time.perf_counter()
        total_time = end_time - start_time
        proc_time = total_time - fetch_time
        logger.info(
            "\n[DIAGNOSTICS] Job %s (PARTIAL/BEST-EFFORT) Performance Metrics:\n"
            "- Queue Time: %.3fs\n"
            "- Fetch Time: %.3fs\n"
            "- Model Call Time: %.3fs\n"
            "- Processing Time: %.3fs\n"
            "- Total Job Time: %.3fs\n"
            "- Routing Path: Best-Effort Verdict\n",
            job_id, queue_time, fetch_time, model_call_time, proc_time, total_time
        )
        return

    # ── Embed claims + deduplicate + insert ──
    unique_claims = []
    seen_texts = set()
    for c in claims:
        txt_norm = c.text.strip().lower()
        if txt_norm not in seen_texts:
            seen_texts.add(txt_norm)
            unique_claims.append(c)
    claims = unique_claims

    embeddings = await embed_text_batch([c.text for c in claims])
    
    async def process_single_claim(claim: ClaimSchema, emb: list[float]) -> ClaimSchema:
        if emb:
            similar = await queries.find_similar_claim(pool, emb)
            if similar:
                logger.info("Near-duplicate claim found (id=%s), skipping insert", similar["id"])
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

    await publish_status(redis, job_id, "sourcing_claims", "Finding sources for each claim...")

    # Sourcing & Bias analysis in parallel
    source_results_raw = []
    bias_result = None
    try:
        source_tasks = [find_sources(claim, redis) for claim in inserted_claims]
        bias_task = score_bias(cleaned, input_url)

        sourcing_start = time.perf_counter()
        # 15s Timeout for sourcing + bias stages in parallel (reduced from 45s)
        results = await asyncio.wait_for(
            asyncio.gather(
                asyncio.gather(*source_tasks, return_exceptions=True),
                bias_task,
                return_exceptions=True,
            ),
            timeout=15.0
        )
        sourcing_duration = time.perf_counter() - sourcing_start
        model_call_time += sourcing_duration # include search/bias LLM latency
        source_results_raw, bias_result = results
    except asyncio.TimeoutError:
        logger.warning("Job %s: Sourcing/Bias analysis timed out (15s limit exceeded). Proceeding with Tier 3 best-effort fallback.", job_id)
        await publish_status(redis, job_id, "judging", "⚠️ Fallback: Sourcing timed out. Generating best-effort verdict...")
        
        # Default bias result
        bias_result = BiasResult(
            bias_score=50, bias_direction="neutral", framing_flags=[], loaded_terms=[], summary="Bias analysis timed out."
        )
        await queries.insert_bias_result(
            pool, job_id, article_id,
            bias_result.bias_score, bias_result.bias_direction,
            [], [], bias_result.summary,
        )

        try:
            judge_start = time.perf_counter()
            judge_result = await asyncio.wait_for(run_best_effort_verdict(cleaned, bias_result), timeout=10.0)
            model_call_time += (time.perf_counter() - judge_start)
        except Exception as e:
            logger.error("Job %s: Fallback verdict failed: %s", job_id, e)
            from models.schemas import JudgeResult
            judge_result = JudgeResult(
                overall_verdict="UNVERIFIABLE",
                overall_confidence=0.1,
                overall_summary="Verification timed out during source gathering.",
                claim_verdicts=[]
            )

        await publish_status(redis, job_id, "finalizing", "Saving best-effort verdict...")

        await queries.insert_verdict(
            pool, job_id, None,
            judge_result.overall_verdict, judge_result.overall_confidence,
            "Sourcing timed out. " + judge_result.overall_summary, True
        )

        await queries.update_job_status(pool, job_id, "PARTIAL")
        await publish_event(redis, job_id, "verdict", {
            "overall_verdict": judge_result.overall_verdict,
            "overall_confidence": judge_result.overall_confidence,
            "overall_summary": "Sourcing timed out. " + judge_result.overall_summary,
            "claim_verdicts": [],
        })
        await publish_done(redis, job_id)
        
        # Log diagnostics
        end_time = time.perf_counter()
        total_time = end_time - start_time
        proc_time = total_time - fetch_time
        logger.info(
            "\n[DIAGNOSTICS] Job %s (PARTIAL/TIMEOUT) Performance Metrics:\n"
            "- Queue Time: %.3fs\n"
            "- Fetch Time: %.3fs\n"
            "- Model Call Time: %.3fs\n"
            "- Processing Time: %.3fs\n"
            "- Total Job Time: %.3fs\n"
            "- Routing Path: Sourcing Timeout Fallback\n",
            job_id, queue_time, fetch_time, model_call_time, proc_time, total_time
        )
        return

    # Handle bias failure if it returned exception
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
        source_ids = []
        for s in source_result.sources:
            sid = await queries.insert_source(
                pool, cid, s.url, s.title, s.domain,
                s.snippet, s.full_text, s.stance,
                s.quality_score or 0.0, s.fetch_status or "unknown"
            )
            s.source_id = sid
            source_ids.append(sid)

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

    await publish_status(redis, job_id, "judging", "Synthesizing final verdict...")

    # Judge Agent
    try:
        judge_start = time.perf_counter()
        # 10s Timeout for Judge Agent
        judge_result = await asyncio.wait_for(
            run_judge(inserted_claims, sources_by_claim, bias_result, cleaned),
            timeout=10.0
        )
        model_call_time += (time.perf_counter() - judge_start)
    except Exception as e:
        logger.warning("Job %s: Judge agent failed or timed out (%s). Using computed fallback.", job_id, e)
        await publish_status(redis, job_id, "judging", "⚠️ Fallback: Judge failed. Computing evidence-based verdict...")
        judge_result = compute_fallback_verdict(inserted_claims, sources_by_claim, bias_result)

    await publish_status(redis, job_id, "finalizing", "Saving final verdicts...")

    # Insert verdicts
    for cv in judge_result.claim_verdicts:
        await queries.insert_verdict(
            pool, job_id, cv.claim_id,
            cv.verdict, cv.confidence, cv.reasoning, False
        )

    # Insert overall verdict
    await queries.insert_verdict(
        pool, job_id, None,
        judge_result.overall_verdict, judge_result.overall_confidence,
        judge_result.overall_summary, True
    )

    # Publish verdict event
    await publish_event(redis, job_id, "verdict", {
        "overall_verdict": judge_result.overall_verdict,
        "overall_confidence": judge_result.overall_confidence,
        "overall_summary": judge_result.overall_summary,
        "claim_verdicts": [cv.model_dump() for cv in judge_result.claim_verdicts],
    })

    # Mark complete
    await queries.update_job_status(pool, job_id, "COMPLETE")

    # Audit log
    await queries.insert_audit_log(pool, job_id, user_id, "JOB_COMPLETED", {
        "overall_verdict": judge_result.overall_verdict,
        "overall_confidence": judge_result.overall_confidence,
    })

    await publish_done(redis, job_id)
    
    # Log diagnostics
    end_time = time.perf_counter()
    total_time = end_time - start_time
    proc_time = total_time - fetch_time
    logger.info(
        "\n[DIAGNOSTICS] Job %s (STANDARD-%s) Performance Metrics:\n"
        "- Queue Time: %.3fs\n"
        "- Fetch Time: %.3fs\n"
        "- Model Call Time: %.3fs\n"
        "- Processing Time: %.3fs\n"
        "- Total Job Time: %.3fs\n"
        "- Routing Path: Standard (%s)\n",
        job_id, complexity.upper(), queue_time, fetch_time, model_call_time, proc_time, total_time, complexity
    )


async def _fail_job(pool, redis, job_id: str, message: str) -> None:
    try:
        await queries.update_job_status_error(pool, job_id, "FAILED", message)
    except Exception:
        pass
    await publish_error(redis, job_id, message)
    await publish_done(redis, job_id)
    logger.error("Job %s failed: %s", job_id, message)


async def embed_text_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts; returns empty lists on failure."""
    from services.embeddings import embed_batch
    try:
        return await embed_batch(texts)
    except Exception as e:
        logger.error("Batch embedding failed: %s", e)
        return [[] for _ in texts]
