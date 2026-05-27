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

## System Architecture

TruthStream is designed as a split-microservice architecture registered with Eureka Service Discovery (Phase 2):

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
        │ LPUSH Job ID                 │ HTTP / Eureka             │ Pub/Sub
        ▼                              ▼                           │
 ┌──────────────┐             ┌─────────────────┐                  │
 │ Redis Queue  │             │  Eureka Server  │                  │
 └──────────────┘             │   (Port 8761)   │                  │
        ▲                     └─────────────────┘                  │
        │ BRPOP Job ID                 ▲                           │
        │                              │ Register / Discovery      │
 ┌──────┴──────────────────────────────┴───────────────────────────┴──────┐
 │ 2. AI Execution Service (FastAPI - Port 8000)                          │
 └──────┬──────────────────────────────┬───────────────────────────┬──────┘
        │                              │                           │
        ▼                              ▼                           ▼
 ┌──────────────┐             ┌────────────┐              ┌──────────────┐
 │ Gemini API   │             │ Redis Pub  │              │ PostgreSQL   │
 └──────────────┘             └────────────┘              └──────────────┘
```

### Technology Stack
- **Frontend**: React 19, Vite 8, TailwindCSS v4, TypeScript, D3.js
- **Gateway & Orchestration Service**: Spring Boot 3.2, Spring MVC Async Emitters, Lettuce Redis
- **AI Execution Service**: Python 3.12, FastAPI, asyncpg, Google GenAI SDK (Gemini 2.5 Flash & text-embedding-004), py-eureka-client
- **Service Registry**: Netflix Eureka Server (Spring Cloud / Port 8761)
- **Database**: PostgreSQL 16 + pgvector
- **Broker / Cache**: Redis 7 (Queues & Pub/Sub messaging)

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
| **Eureka Dashboard** | [http://localhost:8761](http://localhost:8761) | Service discovery registry console (Phase 2) |
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

- **Postgres Port Conflicts**: If you have a local PostgreSQL instance running on port 5432, the database container will fail to start. Update `DB_PORT=5433` in `.env` and restart.
- **Gemini Key Issues**: If you see quota limits or key validation failures, you can configure multiple API keys (`GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, etc.) in `.env` to enable rotation. If all keys fail, the system falls back to **Sandbox Mock Fallback Mode** to generate simulated responses.
- **Stuck Jobs**: If containers exit unexpectedly, jobs may be left in `PROCESSING` states. The system watchdog automatically sweeps and fails these jobs on the next startup. To wipe the database completely, run `.\stop.ps1 -Clean`.

---

## License
Distributed under the MIT License. See [LICENSE](LICENSE) for details.
