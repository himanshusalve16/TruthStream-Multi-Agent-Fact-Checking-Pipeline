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
from db import queries
from routers import internal
from models.schemas import (
    JobDispatch, ClaimSchema, ClaimSourcesResult, BiasResult
)
from agents.extractor import extract_claims
from agents.source_finder import find_sources
from agents.bias_scorer import score_bias
from agents.judge import run_judge
from services.redis_publisher import (
    publish_status, publish_event, publish_error, publish_done
)
from services.scraper import fetch_article_url
from utils.text import clean_text, truncate_text, word_count, md5_hash
from services.embeddings import embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("truthstream.ai")

NUM_WORKERS = 3


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database pool...")
    app.state.db_pool = await init_db_pool(settings.database_url)

    logger.info("Connecting to Redis...")
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=False)
    await app.state.redis.ping()

    logger.info("Starting %d job workers...", NUM_WORKERS)
    app.state.workers = [
        asyncio.create_task(job_worker(app), name=f"worker-{i}")
        for i in range(NUM_WORKERS)
    ]

    logger.info("AI service ready.")
    yield

    # Shutdown
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
                asyncio.create_task(process_job(job_id, redis, pool))
        except asyncio.CancelledError:
            logger.info("Worker cancelled")
            break
        except Exception as e:
            logger.error("Worker error: %s", e)
            await asyncio.sleep(1)


# ──────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────

async def process_job(job_id: str, redis: aioredis.Redis, pool) -> None:
    """Full fact-checking pipeline for a single job."""
    logger.info("Processing job: %s", job_id)

    try:
        # Fetch job from DB
        job = await queries.get_job(pool, job_id)
        if not job:
            logger.error("Job %s not found in DB", job_id)
            return

        user_id = str(job["user_id"])
        input_url = job["input_url"]
        input_text = job["input_text"]

        await queries.update_job_status(pool, job_id, "PROCESSING")
        await publish_status(redis, job_id, "fetching_article", "Fetching article content...")

        # ── Step 1: Fetch article ──
        if input_url:
            try:
                raw_text, _ = await fetch_article_url(input_url)
            except Exception as e:
                await _fail_job(pool, redis, job_id, f"Could not fetch article: {e}")
                return
        else:
            raw_text = input_text or ""

        if len(raw_text.strip()) < 100:
            await _fail_job(pool, redis, job_id, "Article content too short or inaccessible.")
            return

        cleaned = clean_text(raw_text)
        cleaned, truncated = truncate_text(cleaned)
        wc = word_count(cleaned)
        url_hash = md5_hash(input_url) if input_url else None

        # ── Step 2: Insert article ──
        article_id = await queries.insert_article(
            pool,
            url=input_url,
            url_hash=url_hash,
            raw_text=raw_text[:50000],
            cleaned_text=cleaned,
            truncated=truncated,
            word_count=wc,
        )
        await queries.update_job_article(pool, job_id, article_id)

        await publish_status(redis, job_id, "extracting_claims", "Analyzing article for claims...")

        # ── Step 3: Extract claims ──
        try:
            extraction_result = await extract_claims(cleaned, input_url)
        except Exception as e:
            await _fail_job(pool, redis, job_id, f"Claim extraction failed: {e}")
            return

        claims = extraction_result.claims
        if not claims:
            await publish_event(redis, job_id, "no_claims", {
                "message": "No verifiable factual claims found in this article.",
                "notes": extraction_result.extraction_notes,
            })
            await queries.update_job_status(pool, job_id, "PARTIAL")
            await publish_done(redis, job_id)
            return

        # ── Step 4: Embed claims + deduplicate + insert ──
        embeddings = await embed_text_batch([c.text for c in claims])
        inserted_claims: list[ClaimSchema] = []

        for i, claim in enumerate(claims):
            emb = embeddings[i] if i < len(embeddings) else []
            # Deduplication check
            if emb:
                similar = await queries.find_similar_claim(pool, emb)
                if similar:
                    logger.info("Near-duplicate claim found (id=%s), skipping insert", similar["id"])
                    claim.claim_id = str(similar["id"])
                    inserted_claims.append(claim)
                    continue

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
            "extraction_notes": extraction_result.extraction_notes,
        })

        await publish_status(redis, job_id, "sourcing_claims", "Finding sources for each claim...")

        # ── Step 5: Source Finder + Bias Scorer (parallel) ──
        source_tasks = [find_sources(claim, redis) for claim in inserted_claims]
        bias_task = score_bias(cleaned, input_url)

        results = await asyncio.gather(
            asyncio.gather(*source_tasks, return_exceptions=True),
            bias_task,
            return_exceptions=True,
        )

        source_results_raw, bias_result = results

        # Handle bias failure
        if isinstance(bias_result, Exception):
            logger.error("Bias scoring failed: %s", bias_result)
            from models.schemas import BiasResult as BR
            bias_result = BR(
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
            if isinstance(source_result, Exception):
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

        # ── Step 6: Judge Agent ──
        judge_result = await run_judge(inserted_claims, sources_by_claim, bias_result, cleaned)

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
        logger.info("Job %s completed: %s (%.2f)", job_id,
                    judge_result.overall_verdict, judge_result.overall_confidence)

    except Exception as e:
        logger.exception("Unhandled error processing job %s: %s", job_id, e)
        await _fail_job(pool, redis, job_id, f"Internal pipeline error: {str(e)[:200]}")


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
