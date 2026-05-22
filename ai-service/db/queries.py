"""
All SQL queries for the FastAPI service.
Uses asyncpg parameterized queries throughout.
"""
from typing import Optional, List
import asyncpg
import json


# ─────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────

async def get_job(pool: asyncpg.Pool, job_id: str) -> Optional[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM jobs WHERE id = $1", job_id
        )


async def update_job_status(pool: asyncpg.Pool, job_id: str, status: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status = $1, updated_at = NOW() WHERE id = $2",
            status, job_id
        )


async def update_job_status_error(
        pool: asyncpg.Pool, job_id: str, status: str, error_message: str
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE jobs SET status = $1, error_message = $2, updated_at = NOW()
               WHERE id = $3""",
            status, error_message, job_id
        )


async def update_job_article(pool: asyncpg.Pool, job_id: str, article_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET article_id = $1, updated_at = NOW() WHERE id = $2",
            article_id, job_id
        )


# ─────────────────────────────────────────
# Articles
# ─────────────────────────────────────────

async def find_article_by_url_hash(pool: asyncpg.Pool, url_hash: str) -> Optional[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM articles WHERE url_hash = $1", url_hash
        )


async def insert_article(
        pool: asyncpg.Pool,
        url: Optional[str],
        url_hash: Optional[str],
        raw_text: str,
        cleaned_text: str,
        truncated: bool,
        word_count: int,
) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO articles (url, url_hash, raw_text, cleaned_text, truncated, word_count)
               VALUES ($1, $2, $3, $4, $5, $6)
               ON CONFLICT (url_hash) DO UPDATE
                 SET cleaned_text = EXCLUDED.cleaned_text
               RETURNING id""",
            url, url_hash, raw_text, cleaned_text, truncated, word_count
        )
        return str(row["id"])


# ─────────────────────────────────────────
# Claims
# ─────────────────────────────────────────

async def find_similar_claim(pool: asyncpg.Pool, embedding: List[float]) -> Optional[asyncpg.Record]:
    """Find a near-duplicate claim using cosine similarity (pgvector)."""
    async with pool.acquire() as conn:
        # Register pgvector codec
        await conn.execute("SET LOCAL ivfflat.probes = 10")
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        return await conn.fetchrow(
            """SELECT id, text, 1 - (embedding <=> $1::vector) AS similarity
               FROM claims
               WHERE 1 - (embedding <=> $1::vector) > 0.9
               LIMIT 1""",
            embedding_str
        )


async def insert_claim(
        pool: asyncpg.Pool,
        job_id: str,
        article_id: str,
        text: str,
        context_quote: Optional[str],
        claim_type: Optional[str],
        checkability: Optional[str],
        embedding: Optional[List[float]],
) -> str:
    async with pool.acquire() as conn:
        embedding_str = None
        if embedding:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        row = await conn.fetchrow(
            """INSERT INTO claims (job_id, article_id, text, context_quote, claim_type, checkability, embedding)
               VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
               RETURNING id""",
            job_id, article_id, text, context_quote, claim_type, checkability, embedding_str
        )
        return str(row["id"])


# ─────────────────────────────────────────
# Sources
# ─────────────────────────────────────────

async def insert_source(
        pool: asyncpg.Pool,
        claim_id: str,
        url: str,
        title: Optional[str],
        domain: Optional[str],
        snippet: Optional[str],
        full_text: Optional[str],
        stance: Optional[str],
        quality_score: float,
        fetch_status: str,
) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO sources (claim_id, url, title, domain, snippet, full_text,
                                    stance, quality_score, fetch_status)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               RETURNING id""",
            claim_id, url, title, domain, snippet, full_text,
            stance, quality_score, fetch_status
        )
        return str(row["id"])


# ─────────────────────────────────────────
# Verdicts
# ─────────────────────────────────────────

async def insert_verdict(
        pool: asyncpg.Pool,
        job_id: str,
        claim_id: Optional[str],
        verdict: str,
        confidence: float,
        reasoning: str,
        is_overall: bool,
) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO verdicts (job_id, claim_id, verdict, confidence, reasoning, is_overall)
               VALUES ($1,$2,$3,$4,$5,$6)
               RETURNING id""",
            job_id, claim_id, verdict, confidence, reasoning, is_overall
        )
        return str(row["id"])


# ─────────────────────────────────────────
# Bias Results
# ─────────────────────────────────────────

async def insert_bias_result(
        pool: asyncpg.Pool,
        job_id: str,
        article_id: str,
        bias_score: int,
        bias_direction: str,
        framing_flags: list,
        loaded_terms: list,
        summary: str,
) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO bias_results (job_id, article_id, bias_score, bias_direction,
                                         framing_flags, loaded_terms, summary)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               RETURNING id""",
            job_id, article_id, bias_score, bias_direction,
            json.dumps([f if isinstance(f, dict) else f.model_dump() for f in framing_flags]),
            loaded_terms, summary
        )
        return str(row["id"])


# ─────────────────────────────────────────
# Audit Log
# ─────────────────────────────────────────

async def insert_audit_log(
        pool: asyncpg.Pool,
        job_id: Optional[str],
        user_id: Optional[str],
        event_type: str,
        payload: dict,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO audit_log (job_id, user_id, event_type, payload)
               VALUES ($1, $2, $3, $4)""",
            job_id, user_id, event_type, json.dumps(payload)
        )
