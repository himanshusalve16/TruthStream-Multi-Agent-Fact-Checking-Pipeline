# TruthStream — Multi-Agent Fact-Checking Pipeline

TruthStream is a production-grade, low-latency concurrent processing pipeline for automated fact-checking. Submit any article URL or text passage to extract discrete factual claims, verify them against active web sources, score media framing and language bias, and receive a synthesized jury verdict — streamed live to your browser.

---

## The Problem & Solution

### The Problem
Traditional news consumption and information verification are slow, manually intensive, and prone to subjective reviewer bias. Verifying a single news article requires:
1. Identifying discrete, checkable factual claims.
2. Formulating search queries and evaluating search results.
3. Scraping source pages while bypassing ads/boilerplate.
4. Synthesizing split and conflicting source stances.
5. Grading political framing bias and emotionally charged language.

Doing this manually takes minutes or hours per article.

### The Solution
TruthStream automates this entire process using a cooperative **multi-agent system** powered by Google Gemini and PostgreSQL. By dividing tasks among specialized AI agents and coordinating them via an asynchronous, health-monitored task queue, TruthStream can fact-check an article and stream live feedback in under 10 seconds.

---

## Key Features

- **Asynchronous Pipeline Ingestion**: Web scraping and CPU-bound parsing are offloaded to separate thread executors, protecting the event loop and ensuring low latency.
- **Dual-Queue Segregation**: Submissions are dynamically routed based on length. Short passages (under 600 words) go to the Fast-Track queue (`job_queue_fast`) for single-pass analysis. Large articles or URLs go to the Standard/Slow queue (`job_queue_slow`) for parallel web verification.
- **Scraper Bypass Mode**: To minimize web request overhead, the Standard path bypasses full-text page scraping, extracting stances directly from search result snippets ranked using a local token overlap reranker. Deep checks retrieve full page content.
- **pgvector Semantic Deduplication**: Extracted claims are vectorized into 768-dimensional embeddings (`text-embedding-004`) and matched against PostgreSQL records. If a claim has been verified in the past 24 hours, the previous verdict is reused, skipping execution.
- **Cooperative Task Cancellation**: Users can interrupt running tasks from the frontend. A Redis Pub/Sub channel publishes cancellation triggers, allowing FastAPI workers to catch `asyncio.CancelledError` and terminate threads cleanly.
- **D3.js Gauges & Timelines**: The frontend includes responsive neon glassmorphic dashboards, live progress tracking, and interactive D3.js timelines visualizing claim confidence and source consensus.

---

## How It Works (End-to-End Pipeline)

TruthStream fact-checks submissions via a real-time, event-driven pipeline:
1. **Ingestion**: A user submits an article URL or raw text. The Spring Boot backend gateway writes a `PENDING` job record to PostgreSQL and returns a `202 Accepted` response with the `job_id` to the frontend.
2. **SSE Stream Initialization**: The React frontend establishes a Server-Sent Events (SSE) connection to `/api/jobs/{id}/stream`. The backend subscribes to a Redis Pub/Sub channel (`job:{id}:events`) to forward updates to the client in real-time.
3. **Semantic Cache Lookup**: The gateway hashes the URL using MD5. If the URL was successfully processed within the last 24 hours, the gateway clones the cached claims and verdicts instantly, avoiding unnecessary processing and AI quota usage.
4. **Complexity Routing**: The gateway sends the job request to FastAPI (`/internal/jobs`). FastAPI inspects the input:
   - **Fast Path**: Short text passages (under 600 words) bypass background queuing and run a single-pass Gemini model call to extract claims, score bias, and judge veracity in one turn.
   - **Standard/Deep Path**: Long text passages or URLs are queued in Redis (`job_queue_slow`) for asynchronous background processing.
5. **Background Verification**: A FastAPI worker pulls the job from the Redis queue:
   - **Claim Extraction**: The `Extractor` agent parses the text and extracts up to 5 discrete factual claims.
   - **Semantic Deduplication**: Extracted claims are vectorized (using `text-embedding-004`) and matched against PostgreSQL using cosine similarity. If a claim was verified in the past 24 hours, the verdict is reused.
   - **Source Discovery**: The `Source Finder` agent generates optimized queries. It queries SerpAPI (falling back to DuckDuckGo HTML scraping if unconfigured or quota-exceeded).
     - **Standard Path (Snippet-Bypass)**: Stances are evaluated directly from search engine snippets and domain authority to maximize speed.
     - **Deep Path**: Top 3 source URLs are crawled in parallel using thread executors and cleaned via BeautifulSoup, and stances are evaluated on the full text.
   - **Bias Scoring**: In parallel, the `Bias Scorer` agent analyzes framing, loaded terms, and political bias.
   - **Verdict Synthesis**: The `Judge` agent evaluates the consensus matrix across claims and sources to produce the overall verdict.
6. **Streaming & Completion**: As each step executes, the worker publishes events to Redis. The gateway relays these events to the client. Once the verdict is saved, the job is marked `COMPLETE` and the stream is closed.

---

## Adaptive Multi-Pipeline Routing

To ensure fast response times and low token consumption, the system dynamically routes articles:
- **Fast Path**: Triggered for short raw text blocks (< 600 words). Bypasses web search entirely, executing a single-pass Gemini call. Complete in **3.5s – 5.0s**.
- **Standard Path**: Triggered for standard URLs and medium articles. Uses web search but evaluates evidence strictly using search snippets and domain authority (crawler-bypass). Complete in **6.8s – 11.7s**.
- **Deep Path**: Triggered for complex articles, highly contested claims, or when direct page analysis is required. Performs full-page web scraping in parallel for the top 3 results. Complete in **12.3s – 26.7s**.
- **Recovery Path**: Triggered if any step fails or if all Gemini API keys hit rate limits. Uses a summary-based, best-effort evaluation fallback to ensure the system never hangs.

---

## Pipeline Limits & Capping

TruthStream is designed to be highly optimized and resource-bounded:
- **Claim Caps**: A maximum of **5 claims** are processed per article (capped at **2 claims** on the Fast Path and **3 claims** under high quota pressure) to prevent pipeline bloat and API timeout issues.
- **Source Budgets**: To prevent SerpAPI quota exhaustion, the system limits search queries per article: **1 query** for Fast/Recovery paths, **2 queries** for Standard, and **3 queries** for Deep.
- **Source Capping**: The pipeline maps at most **2 external sources** per claim, stopping search early once at least 1 high-quality supporting or refuting source is verified.

---

## System Architecture

TruthStream is designed as a decoupled, multi-service architecture:

```
                        ┌──────────────────────────────┐
                        │         User Browser         │
                        └──────────────┬───────────────┘
                           HTTP POST   │   GET SSE
                           /api/jobs   │   /jobs/{id}/stream
                                       ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. Gateway & Orchestration Service (Spring Boot - Port 8080)           │
 └──────┬──────────────────────────────┬───────────────────────────▲──────┘
        │                              │                           │
        │ LPUSH Job ID                 │ HTTP POST                 │ Pub/Sub
        ▼                              │ /internal/jobs            │
 ┌──────────────┐                      ▼                           │
 │ Redis Queue  ├──────────────┐┌──────────────┐                   │
 └──────────────┘              ││ AI Service   │                   │
                               ││ (FastAPI     │                   │
                               ▼│  Port 8000)  │                   │
 ┌──────────────────────────────┼──────┬───────┼───────────────────┴──────┐
 │ Async Queue Workers          │      │       │                          │
 └──────────────────────────────┘      ▼       ▼                          ▼
                                ┌──────────┐┌──────────┐           ┌──────────┐
                                │Gemini API││SerpAPI/DD│           │PostgreSQL│
                                └──────────┘└──────────┘           └──────────┘
```

### Technology Stack
- **Frontend**: React 19, Vite 8, TailwindCSS v4, TypeScript, D3.js (Confidence Gauge & Verdict Timeline)
- **Gateway & Orchestration Service**: Spring Boot 3.2, Spring MVC Async Emitters, Lettuce Redis Client
- **AI Execution Service**: Python 3.12, FastAPI, asyncpg, Google GenAI SDK (Gemini 2.5 Flash / Gemini 2.5 Flash Lite & text-embedding-004)
- **Database**: PostgreSQL 16 + pgvector
- **Broker / Cache / Queue**: Redis 7 (Dual queue routing, search cache & Pub/Sub messaging)
- **Source Retrieval**: SerpAPI (with DuckDuckGo HTML scraping fallback)
- **Hosting / Deployment**: Vercel (Frontend), Render (Spring Boot backend, FastAPI AI service, PostgreSQL, Redis)


---

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose v2)
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

### 1. Clone the Repository & Configure Environment
```powershell
git clone https://github.com/himanshusalve16/TruthStream-Multi-Agent-Fact-Checking-Pipeline.git
cd TruthStream

# Copy the environment file template
Copy-Item .env.example .env
```

Open `.env` in a text editor and fill in the required keys:
- `GEMINI_API_KEY` — **Required** for AI pipeline operations. Supports key rotation (you can add `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, etc.).
- `INTERNAL_API_SECRET` — Used to secure Spring Boot-to-FastAPI calls. Generate a secret using:
  ```powershell
  $bytes = New-Object byte[] 16
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  [System.BitConverter]::ToString($bytes) -replace '-', ''
  ```
- `DB_PASSWORD` — Choose a secure password for the Postgres container.
- `SERPAPI_KEY` — Optional. If not set, TruthStream falls back to DuckDuckGo HTML scraping (no API key required).

### 2. Start the Stack
You can start the full stack in Docker using the helper script (which runs pre-flight checks):
```powershell
.\start.ps1
```
Or directly via Docker Compose:
```powershell
docker compose up --build -d
```
Wait around 45–60 seconds for all services to become healthy. Check container health with:
```powershell
docker compose ps
```

### 3. Access URLs

| Service | Access URL | Purpose |
|---|---|---|
| **Frontend UI** | [http://localhost:3000](http://localhost:3000) | Main user interface |
| **Spring Boot Actuator** | [http://localhost:8080/actuator/health](http://localhost:8080/actuator/health) | Gateway health status |
| **FastAPI Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | AI service documentation & testing |
| **FastAPI Health** | [http://localhost:8000/health](http://localhost:8000/health) | Ultra-lightweight keepalive probe |
| **FastAPI Readiness** | [http://localhost:8000/ready](http://localhost:8000/ready) | Multi-stage boot state verification |
| **AI System Health** | [http://localhost:8000/observability/system/health](http://localhost:8000/observability/system/health) | Telemetry metrics & queue depths |

### 4. Stop the Stack
```powershell
# Stop all containers while preserving data
.\stop.ps1

# Stop all containers and delete database volumes (Fresh Start)
.\stop.ps1 -Clean
```

---

## Local Development (Without Docker)

To run the services locally with hot-reloading:

### 1. Spin up Postgres and Redis in Docker
```powershell
docker compose up db redis -d
```

### 2. Run the AI Service (Python)
```powershell
cd ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Load environment variables
. ..\load-env.ps1 -EnvFile ..\.env

# Run FastAPI with reload
uvicorn main:app --reload --port 8000
```

### 3. Run the Backend (Spring Boot)
```powershell
cd backend
. ..\load-env.ps1 -EnvFile ..\.env

# Adjust environment database URLs to target localhost
$env:SPRING_DATASOURCE_URL = "jdbc:postgresql://localhost:5432/truthstream"
$env:SPRING_DATA_REDIS_HOST = "localhost"

.\mvnw.cmd spring-boot:run
```

### 4. Run the Frontend (React)
```powershell
cd frontend
npm install
npm run dev
# Vite starts development server on http://localhost:3000
```

---

## API Reference

The gateway exposes the following endpoints (Spring Security is configured to allow access without authentication for development convenience):

| Method | Endpoint | Description | Payload / Response |
|---|---|---|---|
| `POST` | `/api/jobs` | Submits a URL or text block to fact-check | `{"input_type": "url", "url": "..."}` $\to$ Returns `{"job_id": "...", "status": "PENDING"}` |
| `GET` | `/api/jobs/{id}/stream` | SSE stream for real-time progress updates | Relays events: `status`, `claims_extracted`, `claim_sourced`, `bias_scored`, `verdict`, `done` |
| `GET` | `/api/jobs/{id}` | Fetches job metadata and processing status | Returns job status (`COMPLETE`, `PROCESSING`, `FAILED`) |
| `POST` | `/api/jobs/{id}/cancel` | Aborts an active processing job | Returns updated job metadata with status `FAILED` |
| `GET` | `/api/jobs/{id}/verdict` | Returns the completed fact-checking verdict | Returns overall rating, summary, bias data, and claim verdicts |
| `GET` | `/api/jobs` | Paginated job history for the current user | Query parameters: `page`, `size` |

---

## Diagnostics & Telemetry

The AI service includes dedicated observability and status routes:
- `/health`: Ultra-lightweight health probe returning a tiny `{"status": "ok"}` JSON within 10–50ms. Zero execution overhead, safe for external cron/uptime monitors.
- `/ready`: Multi-stage readiness probe verifying Redis connectivity, Postgres database pools, worker thread status, and Gemini key prewarming.
- `/observability/system/health`: Checks database connection, Redis connectivity, Gemini API key health, and queue worker utilization.
- `/observability/metrics/queue-health`: Returns current message depths for `job_queue_fast` and `job_queue_slow`.
- `/observability/jobs/{job_id}/metrics`: Measures execution times and latencies for each pipeline stage by parsing database logs.

> [!NOTE]
> **Database Table Mismatch**: The observability router queries the `audit_logs` table. However, the database schema table is named `audit_log` (singular). Endpoints that parse execution logs will throw a database error. This is a known database naming inconsistency.

---

## Troubleshooting

### Queueing Issues & Processing Lag
- **Jobs taking too long in PENDING**: This indicates that the Redis queue workers are either stopped or overwhelmed. Check the number of active workers using `GET /observability/system/health`. Ensure that the queue sizes in Redis are low.
- **Articles stuck in PROCESSING**: If a background worker crashes, a job may be left in `PROCESSING` indefinitely. The `stalled_jobs_watchdog` runs every 15 seconds and marks any job active for over 45 seconds as `FAILED`. On application startup, the FastAPI lifecycle watchdog also automatically resets any stale pending/processing jobs to `FAILED` status.

### Source Verification & Verdict Mismatches
- **Verdicts showing UNVERIFIABLE**: This is the expected, evidence-based default when the system cannot find corroborating web evidence. Verdicts are source-first, meaning we do not fall back to AI-only reasoning. If a claim has 0 verified sources attached to it, the judge will render it `UNVERIFIABLE`.
- **Missing Sources / Source verification returns 0 results**: Ensure `SERPAPI_KEY` is configured and has remaining quota. If SerpAPI fails or runs out of credits, the pipeline automatically falls back to DuckDuckGo HTML scraping. However, if DuckDuckGo rate limits the scraper, source counts may drop.
- **SerpAPI Quota Exhausted**: Check your SerpAPI usage dashboard. You can rotate search API keys in the `.env` configuration to maintain search reliability.

### API Keys & Gateway Route Mismatches
- **Gemini Key Issues (Quota Limits)**: If a Gemini key hits a `429` (Quota Exceeded) or `403` error, the AI service rotates to the next configured key (`GEMINI_API_KEY_1` through `GEMINI_API_KEY_4`). If all keys fail, the system falls back to the **Sandbox Mock Fallback Mode** to return simulated structures rather than throwing errors.
- **Backend Route Mismatches / Gateway 503**: If the gateway logs show `503 Service Unavailable` when dispatching jobs, verify that the `FASTAPI_BASE_URL` is set to the correct URL of the running FastAPI container/service (e.g. `http://ai-service:8000` in Docker or `https://ai-service.onrender.com` in production).
- **Render Deployment Failures**: Make sure all database migration scripts in `/backend/src/main/resources/db/migration/` are valid and the target database is active. Render free tier databases may sleep, causing initial connection timeouts. The Spring Boot backend uses HikariCP connection retries to wait for the database to wake up.