# How TruthStream Works

This document provides a deep dive into the inner workings of TruthStream. It explains how each component in the technology stack interacts, how data flows through the system, and how the AI agents collaborate to generate a fact-checking verdict.

---

## 1. The Technology Stack

TruthStream is a distributed, multi-service application running in Docker containers. Here is how each piece contributes to the system:

- **Frontend (React 19 + Vite + TailwindCSS):** 
  Provides a responsive, real-time user interface. It connects to the backend via REST for job submission and uses Server-Sent Events (SSE) to listen for live streaming updates. D3.js is used to render interactive data visualizations, such as the confidence gauge and the verdict timeline.
- **API Gateway (Spring Boot 3.2):** 
  Acts as the primary entry point for all incoming requests. It is responsible for orchestrating the workflow. When a job is submitted, Spring Boot writes it to the database, places a message on the Redis queue, and opens an SSE connection back to the client.
- **AI Service (Python 3.12 + FastAPI):** 
  The intelligence engine of the application. It runs multiple AI agents using the Google GenAI SDK (`gemini-2.5-flash`). This service pulls jobs from the Redis queue, executes web scraping, fetches external data, runs LLM models, and pushes live updates back into Redis.
- **Database (PostgreSQL 16 + pgvector):** 
  Stores all structured data (users, jobs, extracted claims, source references, verdicts). The `pgvector` extension allows the system to store mathematical embeddings of text claims, enabling semantic similarity search for deduplication (i.e., avoiding re-checking the exact same claim multiple times).
- **Message Broker (Redis 7):** 
  Serves two main purposes: 
  1. A **Job Queue** allowing Spring Boot to asynchronously pass work to the Python AI service.
  2. A **Pub/Sub (Publish/Subscribe)** channel for broadcasting real-time progression events (e.g., "claim extracted", "bias scored") from Python back to the Spring Boot SSE relay, which then forwards them to the browser.
- **Search APIs (SerpAPI / DuckDuckGo):** 
  Used by the AI service to query the live internet for evidence to corroborate or refute factual claims.

---

## 2. End-to-End Processing Workflow

When a user submits a URL or block of text, the system orchestrates a high-performance concurrent processing sequence to arrive at a final verdict.

### Step 1: Ingestion & Dual-Queue Routing
1. The user submits a request via the React frontend to the Spring Boot API (`POST /api/jobs`).
2. Spring Boot creates a new `job` record in the PostgreSQL database with a status of `PENDING`.
3. Spring Boot responds immediately to the frontend with an HTTP 202 (Accepted) and the newly generated `job_id`.
4. The React frontend immediately opens a persistent Server-Sent Events (SSE) connection to `GET /api/jobs/{id}/stream` to listen for progress.
5. Spring Boot determines if the job qualifies for the **Fast-Track** queue (e.g. plain-text passage under 600 words) or the **Standard/Deep** queue. It drops the `job_id` into the corresponding Redis list: `job_queue_fast` or `job_queue_slow`.

### Step 2: Non-Blocking Content Scraping & Cleaning
1. A FastAPI worker thread from the designated worker pool (Fast queue pool: 15 concurrent slots, Slow queue pool: 4 concurrent slots) picks up the `job_id`.
2. If the user provided a URL, the service initiates an HTTP fetch:
   - **Async DNS Resolution**: The blocking hostname lookups are offloaded to an asynchronous threadpool executor (`run_in_executor`) to prevent event-loop latency cascades.
   - **Non-Blocking HTML Clean**: Once the raw HTML is downloaded, BeautifulSoup text cleaning is offloaded to a thread executor to ensure CPU-bound DOM parsing does not starve the async event loop.
3. The job status is updated to `PROCESSING`, and a status event is published to Redis.

### Step 3: Production-Grade Agentic Pipeline Execution

The system coordinates four specialized agents working under a structured Directed Acyclic Graph (DAG) pipeline with latency budgets:

#### A. Claim Extractor Agent
- **Task:** Parses raw text to isolate discrete, checkable factual claims.
- **Action:** Runs a structured, single-turn LLM extraction prompt returning a JSON schema.
- **Vectorization & Deduplication:** Generates 768-dimensional claim embeddings using Gemini's `text-embedding-004` and queries PostgreSQL using the `pgvector` extension. If a matching claim was verified recently, the previous results are reused immediately.
- **Update:** Publishes a `claims_extracted` event. The React frontend receives this and shows individualClaim cards.

#### B. Bias Analyst Agent (Runs concurrently)
- **Task:** Scores loaded language, framing bias, and emotional manipulation.
- **Action:** Evaluates the full article in a single concurrent task.
- **Update:** Pushes a `bias_scored` event to render the D3 bias gauge.

#### C. Source Finder Agent (Crawler Bypass / Snippet Rerank)
- **Task:** Discovers and validates corroborating or refuting source evidence.
- **Scraper Bypass (Standard & Fast paths)**: The agent bypasses full-text HTTP crawling of search result URLs. It formulate search queries, fetches SERP/DuckDuckGo results, and ranks result snippets using a local **lexical overlap snippet reranker**. This avoids slow network calls, reducing latency by up to 90%.
- **Deep Path Scraping**: If the deep-check path is selected, the agent crawls and cleans the top 3 source pages in parallel (bounded by semaphore).
- **Stance Classification**: A structured prompt classifies the stance of each snippet/full-text reference (SUPPORTS, REFUTES, NEUTRAL, UNCLEAR).
- **Update:** Pushes a `claim_sourced` event.

#### D. Judge Agent (Single-Pass jury Synthesis)
- **Task:** Synthesizes consensus, source quality, and bias data to produce overall and per-claim verdicts.
- **Action:** Restructured to execute in a single structured prompt. It evaluates the consensus matrix and mathematically computes confidence scores:
  
  $$C_{\text{final}} = \left( w_a \cdot A + w_q \cdot Q + w_f \cdot F \right) \cdot G \cdot (1 - P_b) \cdot (1 - P_c)$$
  
- **Update:** Publishes the final `verdict` event.

### Step 4: Cooperative Cancellation & Watchdog Recovery
- **Active Heartbeats**: Active pipeline tasks report progress every 2.0s to Redis (`job:{job_id}:heartbeat`).
- **Cooperative Cancellation**: If a user clicks **Cancel** on the React frontend, it triggers `POST /api/jobs/{id}/cancel` on the gateway. The gateway:
  1. Sets status to `FAILED` in PostgreSQL.
  2. Pushes an SSE `error` event to disconnect client.
  3. Publishes the job ID to Redis channel `job:cancel:events`.
  4. Active FastAPI workers listen to the pub/sub and raise an `asyncio.CancelledError` inside the active task registry to safely abort execution.
- **Execution Watchdog**: A background watchdog task monitors heartbeats. If a task exceeds its 45-second budget or stalls, it is automatically cancelled and marked as failed.

### Step 5: Completion & Delivery
1. The AI service updates the job status to `COMPLETE` in PostgreSQL.
2. It publishes a final `done` event.
3. Spring Boot receives `done` from Redis, relays it to the browser, and closes the EventSource.
4. The frontend renders the final verdict banner, interactive D3 timeline, and detailed claim list.

---

## 3. Data Integrity & Auditing

TruthStream is designed with data integrity in mind. Every major transition (Job Created, Claim Extracted, Source Found, Verdict Issued) is recorded in an append-only `audit_log` table in PostgreSQL. 

Because the backend operates highly asynchronously, Redis Pub/Sub provides the critical link ensuring the user is never left wondering what the system is doing, translating complex, multi-agent AI processes into a seamless, live-updating user interface.
