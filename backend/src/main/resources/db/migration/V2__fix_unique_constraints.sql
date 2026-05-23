-- Fix for PostgreSQL ON CONFLICT error
-- The articles table originally had a partial unique index:
-- CREATE UNIQUE INDEX idx_articles_url_hash ON articles(url_hash) WHERE url_hash IS NOT NULL;
-- However, PostgreSQL's ON CONFLICT (url_hash) requires either a full UNIQUE constraint
-- or the exact WHERE clause in the ON CONFLICT statement.
-- Standard UNIQUE constraints in Postgres already allow multiple NULLs, so this constraint is safe.

ALTER TABLE articles ADD CONSTRAINT uq_articles_url_hash UNIQUE (url_hash);

-- Optionally drop the old partial index since the constraint implicitly creates a new unique index
DROP INDEX IF EXISTS idx_articles_url_hash;
