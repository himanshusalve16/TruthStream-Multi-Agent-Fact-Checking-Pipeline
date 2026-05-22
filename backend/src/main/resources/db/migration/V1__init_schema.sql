-- TruthStream Database Schema
-- Managed by Flyway. Do not manually alter these tables.

-- ============================================================
-- Users
-- ============================================================
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active     BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================
-- Articles
-- ============================================================
CREATE TABLE articles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url          TEXT,
  url_hash     TEXT,
  raw_text     TEXT NOT NULL,
  cleaned_text TEXT,
  truncated    BOOLEAN NOT NULL DEFAULT FALSE,
  word_count   INTEGER,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_articles_url_hash ON articles(url_hash) WHERE url_hash IS NOT NULL;

-- ============================================================
-- Jobs
-- ============================================================
CREATE TABLE jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  article_id    UUID REFERENCES articles(id),
  status        TEXT NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING','PROCESSING','COMPLETE','FAILED','PARTIAL')),
  input_url     TEXT,
  input_text    TEXT,
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status  ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);

-- ============================================================
-- Claims
-- ============================================================
CREATE TABLE claims (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  article_id    UUID NOT NULL REFERENCES articles(id),
  text          TEXT NOT NULL,
  context_quote TEXT,
  claim_type    TEXT,
  checkability  TEXT,
  embedding     VECTOR(1536),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claims_job_id ON claims(job_id);
CREATE INDEX idx_claims_embedding ON claims
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- Sources
-- ============================================================
CREATE TABLE sources (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id      UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  url           TEXT NOT NULL,
  title         TEXT,
  domain        TEXT,
  snippet       TEXT,
  full_text     TEXT,
  stance        TEXT CHECK (stance IN ('SUPPORTS','REFUTES','NEUTRAL','UNCLEAR')),
  quality_score NUMERIC(4,3),
  fetch_status  TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sources_claim_id ON sources(claim_id);

-- ============================================================
-- Verdicts
-- ============================================================
CREATE TABLE verdicts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  claim_id    UUID REFERENCES claims(id),
  verdict     TEXT NOT NULL,
  confidence  NUMERIC(4,3),
  reasoning   TEXT,
  is_overall  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_verdicts_job_id ON verdicts(job_id);
CREATE INDEX idx_verdicts_claim_id ON verdicts(claim_id);

-- ============================================================
-- Bias Results
-- ============================================================
CREATE TABLE bias_results (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id         UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  article_id     UUID NOT NULL REFERENCES articles(id),
  bias_score     INTEGER,
  bias_direction TEXT,
  framing_flags  JSONB,
  loaded_terms   TEXT[],
  summary        TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_bias_results_job_id ON bias_results(job_id);

-- ============================================================
-- Audit Log
-- ============================================================
CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  job_id      UUID REFERENCES jobs(id),
  user_id     UUID REFERENCES users(id),
  event_type  TEXT NOT NULL,
  payload     JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_log_job_id     ON audit_log(job_id);
CREATE INDEX idx_audit_log_user_id    ON audit_log(user_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
