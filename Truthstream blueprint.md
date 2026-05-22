# TruthStream — Complete Implementation Blueprint

---

## 1. Product Summary

TruthStream is a multi-agent fact-checking pipeline that accepts a URL or raw article text, automatically extracts discrete factual claims, searches the web for corroborating and contradicting evidence, scores the article for bias and framing, and produces a judge-synthesized verdict with per-claim confidence scores — all streamed live to the user's browser via Server-Sent Events. It is designed to run as a portfolio-grade full-stack system with a React + D3 frontend, a Spring Boot API gateway, a Python FastAPI agent service, PostgreSQL + pgvector for persistence and semantic search, and Redis for job queuing and rate limiting.

---

## 2. Full System Architecture

### Services

#### 2.1 React Frontend (`/frontend`)
Serves the user interface. Accepts URL or text input, opens an SSE connection to the Spring Boot API on job submission, and progressively renders claims, sources, bias scores, and the final verdict as events arrive. Uses D3 for the confidence gauge and verdict timeline.

**Why it exists:** Decoupled UI layer. SSE consumption is handled natively in the browser with `EventSource`.

#### 2.2 Spring Boot API Gateway (`/backend`)
The single entry point for all client requests. Handles:
- JWT authentication (issue + validate tokens)
- REST endpoints for job submission, status, and result retrieval
- SSE endpoint that subscribes to a Redis pub/sub channel and forwards events to the browser
- Dispatches job metadata to Redis and delegates actual processing to FastAPI via internal HTTP

**Why it exists:** Acts as the secure, typed orchestration layer. Java/Spring is well-suited to connection management, auth middleware, and SSE lifecycle. It keeps the Python service free of auth concerns.

#### 2.3 Python FastAPI Agent Service (`/ai-service`)
The intelligence layer. On receiving a job from Spring Boot:
1. Extracts claims (LLM call)
2. For each claim: searches sources, scrapes, ranks
3. Scores bias on the full article
4. Runs the judge agent
5. Publishes incremental SSE events to Redis pub/sub as each step completes

**Why it exists:** Python has the best ecosystem for LLM orchestration (LangChain or raw OpenAI SDK), web scraping (httpx + BeautifulSoup), and vector ops (pgvector via psycopg2/asyncpg).

#### 2.4 PostgreSQL + pgvector (`/db`)
Primary persistence. Stores users, jobs, articles, claims, sources, verdicts, and an append-only audit log. The `pgvector` extension stores claim embeddings for deduplication and lookup of prior similar verdicts.

**Why it exists:** Relational integrity for job/claim/verdict relationships. pgvector eliminates the need for a separate vector database.

#### 2.5 Redis
Three roles:
- **Job queue**: FastAPI workers poll a Redis list (`BRPOP`) for job IDs dispatched by Spring Boot.
- **Pub/Sub**: FastAPI publishes SSE events to a channel (`job:{job_id}:events`); Spring Boot subscribes and forwards to the browser.
- **Rate limiting + caching**: Per-user request counts (sliding window); cached scrape results for recently seen URLs.

**Why it exists:** Low-latency inter-service messaging without the overhead of a full message broker. Redis pub/sub is sufficient for this throughput.

### Communication Map

```
Browser
  │  HTTP POST /api/jobs          (submit)
  │  GET  /api/jobs/{id}/stream   (SSE)
  ▼
Spring Boot (port 8080)
  │  JWT validation on all routes
  │  POST http://fastapi:8000/internal/jobs   (dispatch job)
  │  Redis SUBSCRIBE job:{id}:events          (SSE relay)
  ▼
FastAPI (port 8000)           Redis
  │  BRPOP job_queue           ◄──── Spring Boot LPUSH
  │  PUBLISH job:{id}:events   ────► Spring Boot SUBSCRIBE
  │
  ├─► OpenAI API (LLM calls)
  ├─► SerpAPI / Brave Search API (source discovery)
  ├─► httpx (web scraping)
  └─► PostgreSQL (reads/writes via asyncpg)
```

---

## 3. Detailed Data Flow

### 3.1 Happy Path: URL Submission to Final Verdict

```
1. User submits URL via frontend POST /api/jobs
2. Spring Boot:
   a. Validates JWT
   b. Creates job row in PostgreSQL (status=PENDING)
   c. Returns {job_id} to browser immediately (202 Accepted)
   d. Browser opens EventSource /api/jobs/{job_id}/stream
   e. Spring Boot subscribes Redis channel job:{job_id}:events
   f. Spring Boot POSTs to FastAPI /internal/jobs with {job_id, url, user_id}

3. FastAPI receives job:
   a. Creates article row (or fetches cached)
   b. Fetches URL content (httpx, 10s timeout)
   c. Strips HTML → plain text (BeautifulSoup)
   d. Updates job status=PROCESSING
   e. PUBLISH event: {type:"status", data:{stage:"extracting_claims"}}

4. Claim Extractor Agent:
   a. Sends article text to LLM with extraction prompt
   b. Receives JSON array of claims
   c. For each claim: compute embedding (OpenAI text-embedding-3-small)
   d. Check pgvector for near-duplicate claims (cosine distance < 0.1)
   e. Insert new claim rows; reuse prior verdicts for duplicates
   f. PUBLISH event: {type:"claims_extracted", data:{claims:[...]}}

5. For each claim (parallel, max 5 concurrent):
   Source Finder Agent:
   a. Query SerpAPI with claim text
   b. Fetch top 5 result pages (httpx, 8s timeout each)
   c. Score source quality (domain authority heuristics)
   d. Insert source rows
   e. PUBLISH event: {type:"claim_sourced", data:{claim_id, sources:[...]}}

6. Bias Scorer Agent (runs on full article, parallel with step 5):
   a. Sends article to LLM with bias prompt
   b. Returns bias_score (0–100), framing_flags[], loaded_terms[]
   c. Updates article row
   d. PUBLISH event: {type:"bias_scored", data:{...}}

7. Judge Agent:
   a. Receives all claims + sources + bias score
   b. For each claim: produces verdict (SUPPORTED/REFUTED/UNVERIFIABLE), confidence (0.0–1.0)
   c. Produces overall article verdict
   d. Inserts verdict rows + audit log entries
   e. Updates job status=COMPLETE
   f. PUBLISH event: {type:"verdict", data:{...}}
   g. PUBLISH event: {type:"done"}

8. Spring Boot:
   a. Receives "done" event on Redis channel
   b. Forwards final SSE event to browser
   c. Closes SSE connection
```

### 3.2 Job Lifecycle States

```
PENDING → PROCESSING → COMPLETE
                     → FAILED
                     → PARTIAL (some claims failed, verdict still produced)
```

### 3.3 Retries and Failures

| Failure Point | Strategy |
|---|---|
| URL fetch fails (timeout/4xx/5xx) | Retry 3× with exponential backoff (2s, 4s, 8s). On final failure: `status=FAILED`, publish `{type:"error", message:"Could not fetch article"}` |
| LLM API timeout | Retry 2× with 5s delay. If extraction fails: `status=FAILED`. If a single claim's judge fails: mark claim as UNVERIFIABLE, continue. |
| SerpAPI quota exceeded | Fall back to Brave Search API. If both fail: mark source list as empty, claim verdict = UNVERIFIABLE. |
| Scrape returns empty body | Skip that source; do not halt pipeline. |
| Duplicate URL (same user, <24h) | Return cached job_id immediately from Spring Boot without re-processing. |
| Article >15,000 tokens | Truncate to first 15,000 tokens; add metadata flag `truncated=true`; note in verdict summary. |

---

## 4. Agent Architecture

### 4.1 Claim Extractor Agent

**Responsibility:** Parse raw article text and produce a structured list of discrete, checkable factual claims. Filter out opinions, predictions, and rhetorical statements.

**Input:**
```json
{
  "article_text": "string (up to 15000 tokens)",
  "article_url": "string | null"
}
```

**Output:**
```json
{
  "claims": [
    {
      "claim_id": "uuid",
      "text": "The unemployment rate fell to 3.4% in January 2024.",
      "context_quote": "...sentence surrounding the claim in the article...",
      "claim_type": "statistic|event|attribution|definition",
      "checkability": "high|medium|low"
    }
  ],
  "extraction_notes": "string"
}
```

**Prompt strategy:** One-shot extraction with JSON mode. System prompt defines what constitutes a checkable claim. User prompt passes article. Temperature = 0.

**Coordination:** Runs first, sequentially. All downstream agents depend on its output.

---

### 4.2 Source Finder Agent

**Responsibility:** For each claim, find web sources that are relevant, assess whether they support or contradict the claim, and return structured evidence.

**Input:**
```json
{
  "claim": {
    "claim_id": "uuid",
    "text": "string"
  },
  "max_sources": 5
}
```

**Output:**
```json
{
  "claim_id": "uuid",
  "sources": [
    {
      "source_id": "uuid",
      "url": "string",
      "title": "string",
      "domain": "string",
      "snippet": "string (200 chars max)",
      "stance": "SUPPORTS|REFUTES|NEUTRAL|UNCLEAR",
      "quality_score": 0.82,
      "fetch_status": "success|timeout|blocked|empty"
    }
  ]
}
```

**Prompt strategy:** After search + scrape, pass claim + each source snippet to LLM in a single batched prompt asking for stance classification per source. Temperature = 0.

**Tool calls used:** SerpAPI search → httpx scrape → LLM stance classification.

---

### 4.3 Bias Scorer Agent

**Responsibility:** Analyze the full article text for loaded language, framing bias, emotional manipulation, and one-sided sourcing patterns.

**Input:**
```json
{
  "article_text": "string",
  "article_url": "string | null"
}
```

**Output:**
```json
{
  "bias_score": 42,
  "bias_direction": "left_leaning|right_leaning|pro_establishment|anti_establishment|neutral",
  "framing_flags": [
    {"type": "loaded_language", "examples": ["radical", "extremist"], "severity": "medium"},
    {"type": "omission_bias", "description": "No counterarguments presented", "severity": "high"}
  ],
  "loaded_terms": ["string"],
  "summary": "string (2–3 sentence plain English summary of bias findings)"
}
```

**Prompt strategy:** Single LLM call with detailed rubric in system prompt. No tool calls needed. Temperature = 0.2 for slight variation in framing detection.

**Coordination:** Runs in parallel with Source Finder Agent. Its output feeds the Judge Agent.

---

### 4.4 Judge Agent

**Responsibility:** Synthesize all claim verdicts, source stances, and bias scores into a final per-claim verdict and overall article verdict.

**Input:**
```json
{
  "article_text": "string",
  "claims": [...],
  "sources_by_claim": {"claim_id": [...]},
  "bias_result": {...}
}
```

**Output:**
```json
{
  "overall_verdict": "MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE",
  "overall_confidence": 0.74,
  "overall_summary": "string (3–5 sentence plain English summary)",
  "claim_verdicts": [
    {
      "claim_id": "uuid",
      "verdict": "SUPPORTED|REFUTED|UNVERIFIABLE|CONTESTED",
      "confidence": 0.88,
      "reasoning": "string (1–2 sentences)",
      "key_sources": ["source_id1", "source_id2"]
    }
  ]
}
```

**Prompt strategy:** Chain-of-thought prompt. The system prompt instructs the model to reason about evidence quality, source count, source consensus, and bias context before outputting JSON. Temperature = 0. JSON mode enforced.

**How it synthesizes:**
1. Count sources per claim by stance (SUPPORTS vs REFUTES).
2. Weight sources by `quality_score`.
3. Apply bias penalty: if `bias_score > 70`, reduce overall_confidence by up to 0.15.
4. If claim has zero sources: verdict = UNVERIFIABLE, confidence = 0.1.
5. If sources conflict (SUPPORTS and REFUTES both present): verdict = CONTESTED.

---

### 4.5 Agent Coordination

```
Extractor (sequential)
     │
     ├──► Source Finder × N claims (parallel, asyncio.gather, max 5 concurrent)
     ├──► Bias Scorer (parallel with Source Finder)
     │
     └── (both complete) ──► Judge Agent (sequential, has all data)
```

Implemented in FastAPI using `asyncio.gather` for parallelism. No LangChain agent loop needed — this is a DAG, not a ReAct loop. Use plain Python async orchestration.

---

## 5. Database Design

### 5.1 Tables

#### `users`
```sql
CREATE TABLE users (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email        TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active    BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX idx_users_email ON users(email);
```

#### `articles`
```sql
CREATE TABLE articles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url          TEXT,
  url_hash     TEXT GENERATED ALWAYS AS (md5(url)) STORED,
  raw_text     TEXT NOT NULL,
  cleaned_text TEXT,
  truncated    BOOLEAN NOT NULL DEFAULT false,
  word_count   INTEGER,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX idx_articles_url_hash ON articles(url_hash);
```

#### `jobs`
```sql
CREATE TABLE jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id),
  article_id   UUID REFERENCES articles(id),
  status       TEXT NOT NULL CHECK (status IN ('PENDING','PROCESSING','COMPLETE','FAILED','PARTIAL')),
  input_url    TEXT,
  input_text   TEXT,
  error_message TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
```

#### `claims`
```sql
CREATE TABLE claims (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          UUID NOT NULL REFERENCES jobs(id),
  article_id      UUID NOT NULL REFERENCES articles(id),
  text            TEXT NOT NULL,
  context_quote   TEXT,
  claim_type      TEXT,
  checkability    TEXT,
  embedding       VECTOR(1536),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_claims_job_id ON claims(job_id);
CREATE INDEX idx_claims_embedding ON claims USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

#### `sources`
```sql
CREATE TABLE sources (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id       UUID NOT NULL REFERENCES claims(id),
  url            TEXT NOT NULL,
  title          TEXT,
  domain         TEXT,
  snippet        TEXT,
  full_text      TEXT,
  stance         TEXT CHECK (stance IN ('SUPPORTS','REFUTES','NEUTRAL','UNCLEAR')),
  quality_score  NUMERIC(4,3),
  fetch_status   TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sources_claim_id ON sources(claim_id);
```

#### `verdicts`
```sql
CREATE TABLE verdicts (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id              UUID NOT NULL REFERENCES jobs(id),
  claim_id            UUID REFERENCES claims(id),  -- NULL = overall verdict
  verdict             TEXT NOT NULL,
  confidence          NUMERIC(4,3),
  reasoning           TEXT,
  is_overall          BOOLEAN NOT NULL DEFAULT false,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_verdicts_job_id ON verdicts(job_id);
```

#### `bias_results`
```sql
CREATE TABLE bias_results (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          UUID NOT NULL REFERENCES jobs(id),
  article_id      UUID NOT NULL REFERENCES articles(id),
  bias_score      INTEGER,
  bias_direction  TEXT,
  framing_flags   JSONB,
  loaded_terms    TEXT[],
  summary         TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### `audit_log`
```sql
CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  job_id      UUID REFERENCES jobs(id),
  user_id     UUID REFERENCES users(id),
  event_type  TEXT NOT NULL,
  payload     JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_log_job_id ON audit_log(job_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
```

### 5.2 pgvector Usage

- **Claim deduplication:** Before inserting a new claim, query:
  ```sql
  SELECT id, text, 1 - (embedding <=> $1) AS similarity
  FROM claims
  WHERE 1 - (embedding <=> $1) > 0.9
  LIMIT 1;
  ```
  If a near-duplicate exists and has a completed verdict, reuse it — skip re-processing for that claim.

- **Similar prior verdicts:** Surface prior verdicts for claims that are semantically similar to a new submission, enabling the UI to show "We've seen this claim before."

### 5.3 Audit Trail Design

Every significant state transition writes a row to `audit_log`:
- `JOB_CREATED`, `JOB_STARTED`, `JOB_COMPLETED`, `JOB_FAILED`
- `CLAIM_EXTRACTED` (one row per claim)
- `VERDICT_ISSUED` (one row per verdict)
- `BIAS_SCORED`

The `payload` JSONB column stores a snapshot of relevant data at that moment. This is append-only — no updates, no deletes. This provides a complete history for debugging, reprocessing, and compliance.

---

## 6. REST API Design

### Auth Endpoints

#### `POST /api/auth/register`
```json
// Request
{"email": "user@example.com", "password": "Str0ngPass!"}

// Response 201
{"user_id": "uuid", "email": "user@example.com"}
```

#### `POST /api/auth/login`
```json
// Request
{"email": "user@example.com", "password": "Str0ngPass!"}

// Response 200
{"access_token": "jwt_string", "token_type": "Bearer", "expires_in": 3600}
```

---

### Job Endpoints

#### `POST /api/jobs`
Requires `Authorization: Bearer <token>`
```json
// Request (URL mode)
{"input_type": "url", "url": "https://example.com/article"}

// Request (text mode)
{"input_type": "text", "text": "Article body here..."}

// Response 202
{"job_id": "uuid", "status": "PENDING", "created_at": "2024-01-15T10:00:00Z"}
```

#### `GET /api/jobs/{job_id}`
```json
// Response 200
{
  "job_id": "uuid",
  "status": "COMPLETE",
  "created_at": "...",
  "updated_at": "...",
  "article": {"id": "uuid", "url": "...", "truncated": false},
  "claims_count": 7,
  "verdict": "MOSTLY_TRUE",
  "overall_confidence": 0.74
}
```

#### `GET /api/jobs` (paginated history)
```json
// Response 200
{
  "jobs": [...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

### Verdict Endpoints

#### `GET /api/jobs/{job_id}/verdict`
```json
// Response 200
{
  "job_id": "uuid",
  "overall_verdict": "MOSTLY_TRUE",
  "overall_confidence": 0.74,
  "overall_summary": "string",
  "bias": {
    "bias_score": 42,
    "bias_direction": "neutral",
    "framing_flags": [...],
    "loaded_terms": [...]
  },
  "claim_verdicts": [
    {
      "claim_id": "uuid",
      "text": "string",
      "verdict": "SUPPORTED",
      "confidence": 0.88,
      "reasoning": "string",
      "sources": [...]
    }
  ]
}
```

---

### Source Endpoints

#### `GET /api/jobs/{job_id}/sources`
```json
// Response 200
{
  "sources_by_claim": {
    "claim_id_1": [
      {"source_id": "uuid", "url": "...", "title": "...", "stance": "SUPPORTS", "quality_score": 0.82}
    ]
  }
}
```

---

### SSE Endpoint

#### `GET /api/jobs/{job_id}/stream`
Headers: `Accept: text/event-stream`, `Authorization: Bearer <token>`

**Event sequence:**
```
event: status
data: {"stage": "extracting_claims", "message": "Analyzing article..."}

event: claims_extracted
data: {"claims": [{"claim_id": "uuid", "text": "...", "claim_type": "statistic"}]}

event: claim_sourced
data: {"claim_id": "uuid", "sources": [...]}

event: bias_scored
data: {"bias_score": 42, "bias_direction": "neutral", "summary": "..."}

event: verdict
data: {"overall_verdict": "MOSTLY_TRUE", "overall_confidence": 0.74, "claim_verdicts": [...]}

event: done
data: {}
```

---

## 7. Frontend Plan

### 7.1 Screens / Routes

| Route | Component | Purpose |
|---|---|---|
| `/` | `LandingPage` | Input form (URL or text), recent checks |
| `/jobs/:id` | `JobPage` | Live streaming results view |
| `/history` | `HistoryPage` | Past jobs list |
| `/login` | `LoginPage` | Auth |
| `/register` | `RegisterPage` | Auth |

---

### 7.2 Components

#### `InputForm`
- Tab toggle: URL input / Paste text
- Submit button triggers `POST /api/jobs`, then navigates to `/jobs/:id`

#### `JobPage` (primary UI)
Houses all streaming sub-components. Opens `EventSource` on mount.

#### `ClaimList`
Renders as claims arrive via `claims_extracted` event. Each `ClaimCard` shows:
- Claim text
- Type badge (statistic / event / attribution)
- Status spinner until verdict arrives

#### `ClaimCard`
Updates live when `claim_sourced` and `verdict` events arrive. Shows:
- Verdict badge (SUPPORTED / REFUTED / CONTESTED / UNVERIFIABLE)
- Confidence bar (CSS width transition)
- Source accordion (collapsed by default)

#### `SourceCard`
- Domain name, title, snippet
- Stance indicator (green check / red X / yellow dash)
- Quality score badge
- Link to original

#### `BiasPanel`
Appears when `bias_scored` event fires. Shows:
- Bias score (0–100) rendered as a D3 gauge
- Direction label
- Loaded terms as highlighted chips
- Framing flags list

#### `ConfidenceGauge` (D3)
A semi-circular arc gauge, 0–100%, color-coded:
- 0–33%: red
- 34–66%: amber
- 67–100%: green
Animates from 0 to final value when verdict event fires.

#### `VerdictBanner`
Prominently shows overall verdict label and summary. Animates in on `verdict` event.

#### `VerdictTimeline` (D3)
Horizontal timeline showing claims left-to-right with colored nodes (verdict color). On hover, shows claim text + confidence tooltip. Built with D3 force layout on the x-axis.

#### `LoadingState`
Per-stage progress indicator. Stages: Fetching → Extracting → Sourcing → Scoring → Judging. Updates on each `status` event.

#### `ErrorBanner`
Appears on `error` event or `status=FAILED` poll. Shows message and a retry button.

---

### 7.3 State Management
Use React Context + `useReducer` for job state. No Redux needed at this scale. The `JobContext` holds claims, sources, bias, and verdict state. All SSE event handlers dispatch into the reducer.

---

## 8. Backend Implementation Plan

### 8.1 Spring Boot Package Structure

```
com.truthstream
├── config
│   ├── SecurityConfig.java        # JWT filter chain
│   ├── RedisConfig.java           # RedisTemplate, MessageListenerContainer
│   └── WebConfig.java             # CORS
├── controller
│   ├── AuthController.java
│   ├── JobController.java         # REST + SSE endpoint
│   └── VerdictController.java
├── service
│   ├── AuthService.java
│   ├── JobService.java            # creates job, calls FastAPI, manages status
│   ├── SseService.java            # manages SseEmitter map, Redis subscription
│   └── FastApiClient.java         # WebClient to FastAPI /internal/jobs
├── repository
│   ├── UserRepository.java
│   ├── JobRepository.java
│   └── VerdictRepository.java
├── model
│   ├── User.java
│   ├── Job.java
│   └── Verdict.java
├── dto
│   ├── JobRequest.java
│   ├── JobResponse.java
│   └── SseEvent.java
├── security
│   ├── JwtUtil.java
│   └── JwtAuthFilter.java
└── TruthStreamApplication.java
```

### 8.2 FastAPI Module Structure

```
ai-service/
├── main.py                   # FastAPI app, routers
├── routers/
│   └── internal.py           # POST /internal/jobs
├── agents/
│   ├── extractor.py          # Claim Extractor Agent
│   ├── source_finder.py      # Source Finder Agent
│   ├── bias_scorer.py        # Bias Scorer Agent
│   └── judge.py              # Judge Agent
├── services/
│   ├── scraper.py            # httpx + BeautifulSoup
│   ├── search.py             # SerpAPI / Brave wrapper
│   ├── embeddings.py         # OpenAI embedding calls
│   └── redis_publisher.py    # Redis pub/sub publish helpers
├── db/
│   ├── connection.py         # asyncpg pool
│   └── queries.py            # all SQL queries
├── models/
│   └── schemas.py            # Pydantic models
├── utils/
│   ├── text.py               # cleaning, truncation
│   └── quality.py            # source quality scoring
└── config.py                 # env vars via pydantic-settings
```

### 8.3 Redis Queue Strategy

Spring Boot (on job creation):
```java
redisTemplate.opsForList().leftPush("job_queue", jobId.toString());
```

FastAPI (worker loop):
```python
async def worker():
    while True:
        _, job_id = await redis.brpop("job_queue")
        asyncio.create_task(process_job(job_id))
```

Start 3 worker tasks on FastAPI startup (`@asynccontextmanager` lifespan). Max 3 concurrent jobs.

### 8.4 SSE Implementation in Spring Boot

Use `SseEmitter` with a `Map<UUID, SseEmitter>` held in `SseService`. On Redis message received (via `MessageListener`), look up the emitter by job_id and call `emitter.send(...)`. Set emitter timeout to 5 minutes. On `done` event, call `emitter.complete()` and remove from map.

```java
@GetMapping(value = "/api/jobs/{jobId}/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter stream(@PathVariable UUID jobId, Authentication auth) {
    SseEmitter emitter = new SseEmitter(300_000L);
    sseService.register(jobId, emitter);
    return emitter;
}
```

### 8.5 Background Processing Flow

```
FastAPI receives POST /internal/jobs
  → validate job exists in DB
  → LPUSH job_id to job_queue
  → return 202 immediately

Worker picks up job_id:
  → fetch article
  → asyncio.gather(
       run_source_finder_for_all_claims(),
       run_bias_scorer()
     )
  → run_judge()
  → update job status in DB
  → publish "done" event
```

---

## 9. AI/LLM Prompt Engineering

**Model:** `gpt-4o` for all agents. Use JSON mode (`response_format: {type: "json_object"}`). Temperature = 0 for extractor, source stance, and judge. Temperature = 0.2 for bias scorer.

---

### 9.1 Claim Extractor System Prompt

```
You are a professional fact-checker. Your task is to extract discrete, verifiable factual claims from the provided article.

Rules:
- Extract ONLY checkable factual claims: statistics, named events, attributed statements, specific dates/numbers.
- Do NOT extract: opinions, predictions, rhetorical questions, vague assertions.
- Each claim must be self-contained and understandable without the surrounding article.
- Maximum 10 claims per article. Prioritize the most specific and checkable ones.
- Label each claim with a type: "statistic", "event", "attribution", or "definition".
- Rate checkability as "high" (specific, verifiable), "medium" (partially verifiable), or "low" (hard to verify).

Output JSON only. Use this schema:
{
  "claims": [
    {
      "text": "string",
      "context_quote": "string",
      "claim_type": "statistic|event|attribution|definition",
      "checkability": "high|medium|low"
    }
  ],
  "extraction_notes": "string"
}
```

**User prompt:**
```
Article URL: {url_or_none}

Article text:
{article_text}

Extract all verifiable factual claims.
```

---

### 9.2 Source Stance Classification Prompt

```
You are evaluating whether a web source supports or contradicts a specific factual claim.

Claim: "{claim_text}"

For each source snippet below, classify the stance as:
- "SUPPORTS": the source provides evidence that the claim is true
- "REFUTES": the source provides evidence that the claim is false
- "NEUTRAL": the source discusses the topic but takes no stance
- "UNCLEAR": the snippet is insufficient to determine stance

Output JSON only:
{
  "stances": [
    {"source_index": 0, "stance": "SUPPORTS|REFUTES|NEUTRAL|UNCLEAR", "reason": "one sentence"}
  ]
}

Sources:
{sources_json}
```

---

### 9.3 Bias Scorer System Prompt

```
You are a media bias analyst. Analyze the provided article for bias signals.

Evaluate:
1. Loaded language: emotionally charged words used to influence rather than inform.
2. Framing bias: selective emphasis, misleading headlines, omission of counterarguments.
3. Attribution patterns: are sources one-sided? Are opposing voices quoted fairly?
4. Overall tone: neutral/clinical vs. persuasive/emotional.

Score bias from 0 (completely neutral) to 100 (heavily biased).
Identify the likely direction: left_leaning, right_leaning, pro_establishment, anti_establishment, or neutral.

Output JSON only:
{
  "bias_score": integer (0-100),
  "bias_direction": "left_leaning|right_leaning|pro_establishment|anti_establishment|neutral",
  "framing_flags": [
    {"type": "string", "description": "string", "examples": ["string"], "severity": "low|medium|high"}
  ],
  "loaded_terms": ["string"],
  "summary": "string (2-3 sentences)"
}
```

---

### 9.4 Judge System Prompt

```
You are a senior fact-checking editor. Your job is to synthesize evidence and produce final verdicts.

For each claim, you are given:
- The claim text
- A list of sources with stance (SUPPORTS/REFUTES/NEUTRAL/UNCLEAR) and quality_score (0.0-1.0)
- A bias report on the original article

Rules for claim verdicts:
- SUPPORTED: majority of quality sources (quality_score > 0.6) support, none strongly refute.
- REFUTED: majority of quality sources refute.
- CONTESTED: sources split between support and refutation.
- UNVERIFIABLE: no usable sources, or all sources are low quality.

Rules for overall verdict:
- MOSTLY_TRUE: >70% of checkable claims are SUPPORTED.
- MIXTURE: mixed results, no clear majority.
- MOSTLY_FALSE: >70% of checkable claims are REFUTED.
- UNVERIFIABLE: insufficient evidence to reach a verdict.

Apply a confidence penalty of up to 0.15 if article bias_score > 70.

Think step by step before producing JSON. Use a "reasoning" field for each claim verdict.

Output JSON only using this schema:
{
  "overall_verdict": "MOSTLY_TRUE|MIXTURE|MOSTLY_FALSE|UNVERIFIABLE",
  "overall_confidence": float (0.0-1.0),
  "overall_summary": "string (3-5 sentences)",
  "claim_verdicts": [
    {
      "claim_id": "string",
      "verdict": "SUPPORTED|REFUTED|CONTESTED|UNVERIFIABLE",
      "confidence": float (0.0-1.0),
      "reasoning": "string",
      "key_source_indices": [integer]
    }
  ]
}
```

---

### 9.5 Sample Agent JSON Outputs

**Extractor:**
```json
{
  "claims": [
    {
      "text": "The U.S. unemployment rate fell to 3.4% in January 2024.",
      "context_quote": "...as the economy added 353,000 jobs, pushing unemployment to 3.4%...",
      "claim_type": "statistic",
      "checkability": "high"
    }
  ],
  "extraction_notes": "1 high-checkability statistic found."
}
```

**Judge:**
```json
{
  "overall_verdict": "MOSTLY_TRUE",
  "overall_confidence": 0.81,
  "overall_summary": "The article's primary statistical claims are supported by BLS data...",
  "claim_verdicts": [
    {
      "claim_id": "abc-123",
      "verdict": "SUPPORTED",
      "confidence": 0.91,
      "reasoning": "BLS January 2024 report confirms 3.4% unemployment rate.",
      "key_source_indices": [0, 2]
    }
  ]
}
```

---

## 10. Source Retrieval Strategy

### 10.1 Search
Use **SerpAPI** (primary) and **Brave Search API** (fallback). Query construction:
- For statistics: `"{number} {context}" site:gov OR site:edu OR reuters.com OR apnews.com`
- For events: `"{event name}" "{date_if_known}" fact check`
- For attributions: `"{person}" "{quoted phrase}" statement`

Max 10 results per query. Filter to top 5 by domain quality before scraping.

### 10.2 Scraping
Use `httpx` async client with:
- `timeout=8` seconds
- `headers={"User-Agent": "TruthStream-Bot/1.0 (+https://yoursite.com/bot)"}` — be transparent
- Follow up to 3 redirects
- Strip with BeautifulSoup: extract `<article>`, `<main>`, or `<body>` text. Remove nav, footer, ads.
- Truncate to 2,000 chars per source (sufficient for stance classification).

Cache scraped content in Redis with key `scrape:{md5(url)}`, TTL = 6 hours.

### 10.3 Source Quality Scoring

Score each source 0.0–1.0:

| Signal | Weight |
|---|---|
| Domain in trusted list (reuters.com, apnews.com, bbc.com, .gov, .edu, nature.com, pubmed.ncbi.nlm.nih.gov) | +0.4 |
| HTTPS | +0.1 |
| Domain in known low-quality list (blogs, tabloids, known partisan sites) | -0.5 |
| Snippet length > 100 chars (sufficient content) | +0.1 |
| Fetch succeeded | +0.1 |
| No paywall signal in content (`"Subscribe to read"`, `"Sign in"`) | +0.1 |
| Result rank ≤ 3 (higher search rank) | +0.1 |

Maintain these lists in `utils/quality.py` as Python sets. Start with 30–40 domains.

### 10.4 Paywalled/Inaccessible Pages
- If scraped content contains paywall keywords: set `fetch_status="blocked"`, set `quality_score -= 0.3`.
- Do not use the snippet for stance classification.
- Fall back to using the search result snippet only (lower confidence).

---

## 11. Claim Verification Strategy

### 11.1 Splitting Claims
The Extractor caps at 10 claims. For articles with many potential claims, instruct the model to prioritize: (1) statistics, (2) attributed statements from named individuals, (3) factual events with dates. Opinions are explicitly excluded.

### 11.2 Assessing Evidence Strength
Weight each source's stance by its `quality_score`:
```python
support_weight = sum(s.quality_score for s in sources if s.stance == "SUPPORTS")
refute_weight  = sum(s.quality_score for s in sources if s.stance == "REFUTES")
total_weight   = sum(s.quality_score for s in sources if s.stance in ("SUPPORTS","REFUTES"))

if total_weight == 0:
    raw_confidence = 0.1
else:
    raw_confidence = max(support_weight, refute_weight) / total_weight
```

Then scale: if `support_weight > refute_weight`, verdict leans SUPPORTED; opposite → REFUTED.

### 11.3 Conflicting Evidence
If both support and refute weights are within 20% of each other → verdict = CONTESTED, confidence = 0.5. The reasoning field must note the disagreement.

### 11.4 Final Confidence Calculation
```python
final_confidence = raw_confidence
if bias_score > 70:
    final_confidence -= 0.1
if source_count == 1:
    final_confidence -= 0.1
final_confidence = max(0.05, min(1.0, final_confidence))
```

---

## 12. Bias Scoring Strategy

### 12.1 Signals Used
1. **Loaded language:** Emotionally charged adjectives and nouns. Maintain a seed list of ~50 terms (e.g., "radical", "regime", "freedom-loving", "elite", "thugs"). Supplement with LLM identification.
2. **Framing:** Does the article present only one side? Are counterarguments straw-manned or absent?
3. **Attribution patterns:** Are all quoted sources from one ideological direction?
4. **Headline vs. body alignment:** Does the headline overstate the body's evidence? (Pass both to LLM.)
5. **Emotional density:** Ratio of emotional adjectives to total word count (computed in Python before LLM call, passed as a signal in the prompt).

### 12.2 Avoiding False Positives
- Score 0–100, not a binary "biased/unbiased."
- Require multiple signals to score above 60. A single loaded term does not make an article biased.
- The LLM must provide `framing_flags` with specific examples, not vague assertions.
- In the judge prompt, a bias_score below 50 does not penalize confidence.
- Surface bias findings to the user as informational, not as a verdict modifier unless score > 70.

---

## 13. Error Handling and Edge Cases

| Case | Handling |
|---|---|
| **Article > 15,000 tokens** | Truncate to first 15,000 tokens. Set `article.truncated=true`. Add note in verdict summary. |
| **No claims found** | Set `extraction_notes` to explain why. Mark job as PARTIAL. Publish `{type:"no_claims", message:"No verifiable factual claims found in this article."}`. Return bias score only. |
| **Source fetch fails for all sources** | All claims → UNVERIFIABLE. Overall verdict → UNVERIFIABLE, confidence = 0.1. Publish warning event. |
| **LLM timeout (>30s)** | Retry 2× with 5s delay. If extraction fails entirely → job FAILED. If only judge times out → PARTIAL with raw source data returned. |
| **Duplicate URL (same user, <24h)** | Spring Boot checks `articles.url_hash` + `jobs` table for a COMPLETE job by the same user for the same URL within 24h. If found: return existing `job_id` in POST /api/jobs response immediately. |
| **Conflicting evidence** | Verdict = CONTESTED. Expose both supporting and refuting sources in the UI with clear labels. |
| **Low confidence overall** | If `overall_confidence < 0.4`, add a disclaimer to the verdict summary: "Insufficient evidence to reach a high-confidence verdict." Do not hide the result. |
| **Empty article body** | If cleaned_text < 100 chars after stripping, return 400 from FastAPI with `error="Article content too short or inaccessible."` |
| **Prompt injection in article text** | Sanitize: strip all text after `"Ignore previous instructions"` patterns before passing to LLM. Use a regex blocklist of injection markers. |

---

## 14. Security and Abuse Prevention

### 14.1 JWT Auth
- Tokens signed with HS256, secret in environment variable.
- Expiry: 1 hour. No refresh tokens for v1 (add later).
- Spring Security filter validates token on every request except `/api/auth/*`.

### 14.2 Rate Limiting
- Redis sliding window counter: key = `ratelimit:{user_id}`, max 10 job submissions per hour.
- In Spring Boot `JobController`, before dispatching: check counter; if exceeded, return 429.
- Also rate-limit by IP for unauthenticated endpoints (register/login): max 20 attempts/hour per IP.

### 14.3 SSRF Protection
Before fetching any URL in FastAPI:
- Parse URL with `urllib.parse`.
- Block private IP ranges: `10.x.x.x`, `172.16.x.x–172.31.x.x`, `192.168.x.x`, `127.x.x.x`, `169.254.x.x`.
- Block non-http(s) schemes.
- Resolve hostname to IP and re-check against private ranges (DNS rebinding protection).
- Use a dedicated outbound-only network namespace in Docker for the scraper.

### 14.4 Scraping Safety
- Set `User-Agent` to identify as a bot.
- Respect `robots.txt` — use `urllib.robotparser` before scraping.
- Timeout all requests.
- Never follow redirects to private IPs (re-check after each redirect).

### 14.5 Prompt Injection
- Wrap article text in explicit XML delimiters in the prompt: `<article_text>{text}</article_text>`.
- Pre-scan for injection patterns with regex before the LLM call.
- Use system-level JSON mode — the model is constrained to output JSON, reducing free-form injection risk.

### 14.6 Input Sanitization
- Spring Boot: validate Content-Type, max request body 1MB.
- URL input: validate with `java.net.URL`, ensure scheme is http or https.
- Text input: strip HTML tags server-side before sending to FastAPI.
- FastAPI: validate all inputs via Pydantic models with explicit field length limits.

---

## 15. Testing Strategy

### 15.1 Unit Tests

**Spring Boot (JUnit 5 + Mockito):**
- `JwtUtilTest`: token generation, validation, expiry.
- `JobServiceTest`: duplicate URL detection, rate limit logic.
- `SseServiceTest`: emitter registration, Redis message dispatch.

**FastAPI (pytest + pytest-asyncio):**
- `test_extractor.py`: mock OpenAI response, assert claim JSON schema.
- `test_bias_scorer.py`: mock OpenAI response, assert score range.
- `test_judge.py`: test confidence calculation logic with synthetic source data.
- `test_quality.py`: domain scoring function unit tests.
- `test_scraper.py`: mock httpx, test paywall detection.

### 15.2 Integration Tests

- `test_job_flow.py`: spin up FastAPI + PostgreSQL (via Docker Compose), submit a job, assert DB rows created for article, claims, sources, verdicts.
- Use `testcontainers-python` for ephemeral Postgres.
- Mock OpenAI and SerpAPI with `respx` (httpx mock library).

### 15.3 Agent Tests

- Pre-record 5 real article fixtures with known ground-truth claims and verdicts.
- Run the full pipeline against them; assert overall_verdict matches ground truth.
- Store fixtures in `ai-service/tests/fixtures/`.

### 15.4 API Tests (Spring Boot)

- Use `MockMvc` for controller layer tests.
- `JobControllerTest`: test 202 on valid submission, 429 on rate limit, 401 on missing token.
- `SseControllerTest`: test that SSE endpoint returns correct `Content-Type`.

### 15.5 Frontend Tests

- **Vitest + React Testing Library:**
  - `ClaimCard.test.tsx`: renders correctly with each verdict type.
  - `JobPage.test.tsx`: mock EventSource, simulate SSE events, assert UI updates.
  - `ConfidenceGauge.test.tsx`: D3 renders arc element.
- **No E2E tests in v1** (Playwright can be added post-MVP).

### 15.6 Mock Data Strategy

- `ai-service/tests/mocks/openai_responses.py`: pre-recorded LLM response JSONs for each agent.
- `ai-service/tests/mocks/serpapi_responses.py`: pre-recorded search results.
- `ai-service/tests/mocks/scraped_pages.py`: truncated HTML of real news pages.
- Use environment variable `TEST_MODE=true` to activate mocks globally.

---

## 16. Deployment Plan

### 16.1 Docker Compose (Local Dev)

```yaml
# docker-compose.yml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    environment:
      - VITE_API_BASE_URL=http://localhost:8080

  backend:
    build: ./backend
    ports: ["8080:8080"]
    environment:
      - SPRING_DATASOURCE_URL=jdbc:postgresql://db:5432/truthstream
      - SPRING_DATA_REDIS_HOST=redis
      - FASTAPI_BASE_URL=http://ai-service:8000
      - JWT_SECRET=${JWT_SECRET}
    depends_on: [db, redis]

  ai-service:
    build: ./ai-service
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@db:5432/truthstream
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - SERPAPI_KEY=${SERPAPI_KEY}
      - BRAVE_API_KEY=${BRAVE_API_KEY}
    depends_on: [db, redis]

  db:
    image: pgvector/pgvector:pg16
    environment:
      - POSTGRES_DB=truthstream
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

volumes:
  pgdata:
```

### 16.2 Environment Variables

```env
# .env (never commit)
JWT_SECRET=your-256-bit-secret
DB_PASSWORD=strongpassword
OPENAI_API_KEY=sk-...
SERPAPI_KEY=...
BRAVE_API_KEY=...
```

### 16.3 Local Development

1. `docker-compose up db redis` (start dependencies only)
2. Spring Boot: run via `./mvnw spring-boot:run` with `.env` sourced.
3. FastAPI: `uvicorn main:app --reload --port 8000` in a virtualenv.
4. Frontend: `npm run dev`.

This avoids rebuilding Docker images on every code change.

### 16.4 Production Deployment

Target: **Railway** or **Render** (easiest for a portfolio project, free tier available).

- Deploy each service as a separate service in Railway.
- Use Railway's managed PostgreSQL (add pgvector extension via SQL migration on first deploy).
- Use Railway's managed Redis.
- Set all environment variables in the Railway dashboard.
- Frontend: deploy to **Vercel** (set `VITE_API_BASE_URL` to Railway backend URL).

Do not use Kubernetes or ECS for v1. It is not necessary and would take weeks to configure.

### 16.5 CI/CD

Use **GitHub Actions**:

```yaml
# .github/workflows/ci.yml
on: [push]
jobs:
  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd backend && ./mvnw test

  test-ai-service:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd ai-service && pip install -r requirements.txt && pytest

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npm ci && npm run test
```

On merge to `main`, Railway auto-deploys from the connected GitHub repo.

---

## 17. Milestone Plan

### Week 1 — Foundation
- Set up monorepo: `/frontend`, `/backend`, `/ai-service`
- Docker Compose with Postgres + Redis running
- Spring Boot: auth endpoints (register, login, JWT)
- FastAPI: basic health endpoint, DB connection, Redis connection
- DB migrations with Flyway (Spring Boot) for all tables
- Frontend: login/register screens, basic routing

### Week 2 — Core Pipeline (No LLM yet)
- FastAPI: URL fetching, HTML cleaning, article storage
- Claim Extractor Agent (LLM call, JSON parsing, DB insert)
- Spring Boot: `POST /api/jobs` endpoint, job creation, dispatch to FastAPI
- Redis pub/sub: FastAPI publishes events, Spring Boot subscribes
- SSE endpoint in Spring Boot
- Frontend: input form submits job, opens SSE, logs raw events to console

### Week 3 — Source Finder + Bias Scorer
- SerpAPI integration + httpx scraper
- Source quality scoring
- Source Finder Agent (stance classification)
- Bias Scorer Agent
- DB inserts for sources + bias results
- SSE events: `claim_sourced`, `bias_scored`
- Frontend: ClaimList renders with spinner states; BiasPanel renders

### Week 4 — Judge Agent + Full Verdict
- Judge Agent implementation
- Confidence calculation
- Verdict DB inserts + audit log
- SSE `verdict` + `done` events
- Frontend: ConfidenceGauge (D3), VerdictBanner, VerdictTimeline (D3), SourceCards
- Error states and loading states in UI

### Week 5 — Reliability + Edge Cases
- Retry logic for LLM + scraper
- Rate limiting in Spring Boot
- SSRF protection in FastAPI
- Duplicate URL detection
- pgvector deduplication for claims
- Paywall detection
- Article truncation

### Week 6 — Polish + Deployment
- Unit and integration tests (target 70% coverage on FastAPI agents)
- Frontend Vitest tests
- Docker Compose finalized and tested end-to-end
- Deploy to Railway + Vercel
- README with architecture diagram
- Record a 2-minute demo video

**Postpone to post-v1:**
- Refresh tokens
- User-facing history with filtering/search
- Playwright E2E tests
- Admin dashboard
- Sharing/public job links

---

## 18. Final Folder Structure

```
truthstream/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ClaimCard.tsx
│   │   │   ├── ClaimList.tsx
│   │   │   ├── SourceCard.tsx
│   │   │   ├── BiasPanel.tsx
│   │   │   ├── ConfidenceGauge.tsx
│   │   │   ├── VerdictBanner.tsx
│   │   │   ├── VerdictTimeline.tsx
│   │   │   ├── InputForm.tsx
│   │   │   ├── LoadingState.tsx
│   │   │   └── ErrorBanner.tsx
│   │   ├── pages/
│   │   │   ├── LandingPage.tsx
│   │   │   ├── JobPage.tsx
│   │   │   ├── HistoryPage.tsx
│   │   │   ├── LoginPage.tsx
│   │   │   └── RegisterPage.tsx
│   │   ├── context/
│   │   │   └── JobContext.tsx
│   │   ├── hooks/
│   │   │   └── useJobStream.ts
│   │   ├── api/
│   │   │   └── client.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── backend/
│   ├── src/main/java/com/truthstream/
│   │   ├── config/
│   │   ├── controller/
│   │   ├── service/
│   │   ├── repository/
│   │   ├── model/
│   │   ├── dto/
│   │   └── security/
│   ├── src/main/resources/
│   │   ├── application.yml
│   │   └── db/migration/          # Flyway SQL migrations
│   ├── src/test/
│   └── pom.xml
│
└── ai-service/
    ├── main.py
    ├── routers/
    │   └── internal.py
    ├── agents/
    │   ├── extractor.py
    │   ├── source_finder.py
    │   ├── bias_scorer.py
    │   └── judge.py
    ├── services/
    │   ├── scraper.py
    │   ├── search.py
    │   ├── embeddings.py
    │   └── redis_publisher.py
    ├── db/
    │   ├── connection.py
    │   └── queries.py
    ├── models/
    │   └── schemas.py
    ├── utils/
    │   ├── text.py
    │   └── quality.py
    ├── tests/
    │   ├── fixtures/
    │   ├── mocks/
    │   └── test_*.py
    ├── config.py
    ├── requirements.txt
    └── Dockerfile
```

---

## 19. Suggested Tech Choices — Honest Assessment

### Things you have right
- **FastAPI for agents:** Correct. Python async + OpenAI SDK is the natural fit.
- **Spring Boot as gateway:** Reasonable for the portfolio signal. SSE + JWT + Redis integration is well-supported.
- **PostgreSQL + pgvector:** Correct. Removes the need for a separate vector DB.
- **Redis for pub/sub + queue:** Correct. Sufficient for this scale.

### Things to reconsider

**Celery/RQ:** Do not use either. Your job volume is low (tens of jobs/hour at most). `asyncio.gather` inside FastAPI with a `BRPOP` worker loop is simpler, has no broker dependency beyond Redis, and is easier to debug. Celery adds significant complexity for zero benefit here.

**LangChain:** Do not use it for v1. Your pipeline is a fixed DAG, not a dynamic agent loop. LangChain's abstraction layers will slow you down, make debugging harder, and add dependency weight. Use the OpenAI Python SDK directly. You can add LangChain later if you need more complex agent behaviors.

**D3:** Keep it, but limit its scope to the two components that genuinely need it: the `ConfidenceGauge` (arc gauge) and the `VerdictTimeline` (claim nodes). All other UI should be plain React + CSS. D3 + React can be painful if overused.

**Spring Boot:** If you find Java overhead too slow for iteration, you could replace it with a Node.js Express or Fastify gateway. Spring Boot is the right choice if you want the portfolio signal of a polyglot system. Keep it.

---

## 20. Deliverables Summary

### All Agent Prompts
See Section 9 for: Claim Extractor system prompt, Source Stance Classification prompt, Bias Scorer system prompt, and Judge system prompt.

### Sample JSON Outputs
See Section 9.5 for extractor and judge output examples. Bias scorer output:
```json
{
  "bias_score": 61,
  "bias_direction": "anti_establishment",
  "framing_flags": [
    {"type": "loaded_language", "description": "Repeated use of 'regime'", "examples": ["regime", "puppet"], "severity": "medium"},
    {"type": "omission_bias", "description": "No expert counterarguments cited", "severity": "high"}
  ],
  "loaded_terms": ["regime", "puppet", "orchestrated"],
  "summary": "The article uses emotionally charged language and presents only one perspective, with no expert countervoices. Bias is moderate-to-high."
}
```

### Sample API Payloads
See Section 6 for full request/response examples for all endpoints.

### Architecture Summary (README)

```
TruthStream extracts factual claims from news articles, finds corroborating
and contradicting web sources, scores article bias, and produces a
judge-synthesized verdict — all streamed live to the browser.

Stack:
- Frontend:   React + D3 (Vite), deployed on Vercel
- API Gateway: Spring Boot (Java), JWT auth, SSE relay
- AI Service: Python FastAPI, 4 LLM agents (OpenAI gpt-4o)
- Database:   PostgreSQL 16 + pgvector (claims deduplication)
- Queue/Cache: Redis (job queue, pub/sub, rate limiting)
- Search:     SerpAPI + Brave Search API
- Deployment: Railway (backend/DB/Redis) + Vercel (frontend)

Pipeline: URL → fetch → clean → extract claims → [find sources ∥ score bias]
→ judge → stream verdict via SSE
```

---

*Blueprint version 1.0 — TruthStream*