import asyncpg
import logging

logger = logging.getLogger(__name__)


async def init_db_pool(database_url: str) -> asyncpg.Pool:
    """Create an asyncpg connection pool."""
    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,  # required for pgvector compatibility
    )
    logger.info("Database pool initialized")
    return pool


async def close_db_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
    logger.info("Database pool closed")
