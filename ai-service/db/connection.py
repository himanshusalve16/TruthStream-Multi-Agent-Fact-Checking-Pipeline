import asyncpg
import logging

logger = logging.getLogger(__name__)


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register custom codecs for each new connection in the pool."""
    # Register pgvector type so asyncpg can encode/decode vector columns
    await conn.execute("SELECT 1")  # ensure connection is alive
    try:
        await conn.set_type_codec(
            "vector",
            encoder=lambda v: v,
            decoder=lambda v: v,
            schema="pg_catalog",
            format="text",
        )
    except Exception:
        # vector type may not exist if extension not loaded yet — fail loudly at query time
        pass


async def init_db_pool(database_url: str) -> asyncpg.Pool:
    """Create an asyncpg connection pool."""
    pool = await asyncpg.create_pool(
        dsn=database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,  # required for pgvector compatibility
        init=_init_connection,
    )
    logger.info("Database pool initialized")
    return pool


async def close_db_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
    logger.info("Database pool closed")
