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

When a user submits a URL or block of text, the system orchestrates a complex sequence of events to arrive at a final verdict. 

### Step 1: Ingestion & Queuing
1. The user submits a request via the React frontend to the Spring Boot API (`POST /api/jobs`).
2. Spring Boot creates a new `job` record in the PostgreSQL database with a status of `PENDING`.
3. Spring Boot responds immediately to the frontend with an HTTP 202 (Accepted) and the newly generated `job_id`.
4. The React frontend immediately opens a persistent Server-Sent Events (SSE) connection to `GET /api/jobs/{id}/stream`.
5. Spring Boot drops the `job_id` into a Redis List (acting as a queue) to notify the Python FastAPI workers that a new job is waiting.

### Step 2: Content Scraping & Cleaning
1. A FastAPI worker, constantly polling Redis, picks up the new job.
2. If the user provided a URL, the service uses the Python `httpx` library and `BeautifulSoup` to download the webpage and strip away HTML tags, navigation, and ads, leaving only the raw article text.
3. The job status is updated to `PROCESSING`, and a status event is published to Redis.

### Step 3: Agentic Pipeline Execution

The system then utilizes four specialized LLM agents working in a directed acyclic graph (DAG) pipeline.

#### A. Claim Extractor Agent
- **Task:** Parses the raw article text to identify discrete, checkable factual claims. It filters out subjective opinions, predictions, and rhetoric.
- **Action:** Sends the article text to Google Gemini with a prompt instructing it to return a structured JSON array of claims.
- **Vectorization:** Once claims are extracted, the service generates a 768-dimensional mathematical embedding for each claim using Gemini's `text-embedding-004` model.
- **Deduplication:** The service queries PostgreSQL (`pgvector`) to find if any visually distinct but semantically identical claims have already been checked recently. If so, it reuses the prior evidence to save time and API costs.
- **Update:** Pushes a `claims_extracted` event via Redis. The React frontend receives this and renders loading spinners for each individual claim.

#### B. Bias Scorer Agent (Runs concurrently)
- **Task:** Analyzes the full article for framing, loaded language, and emotional manipulation.
- **Action:** Sends the full article to Gemini to generate a bias score (0-100) and identify directional leanings (e.g., pro-establishment).
- **Update:** Pushes a `bias_scored` event via Redis. The frontend displays the bias gauge.

#### C. Source Finder Agent (Runs concurrently per claim)
- **Task:** Finds real-world evidence for or against each extracted claim.
- **Action:** 
  1. Formulates a search query based on the claim.
  2. Uses SerpAPI or DuckDuckGo to find relevant web pages.
  3. Scrapes the top search results.
  4. Passes the claim and the scraped text snippets to Gemini, asking the model to determine the `stance` of the source (Does it SUPPORT, REFUTE, or is it NEUTRAL?).
- **Update:** As each claim is sourced, it pushes a `claim_sourced` event via Redis.

#### D. Judge Agent (Final synthesis)
- **Task:** Synthesizes the findings of all previous agents to produce a final verdict.
- **Action:** 
  1. Waits for all claims to be sourced and the bias score to be calculated.
  2. Analyzes the weight, quality, and consensus of the sources for each claim to determine a per-claim verdict (SUPPORTED, REFUTED, CONTESTED, UNVERIFIABLE) and confidence score.
  3. Looks at the aggregate of all claims and the article's bias to generate an **overall article verdict** and summary.
- **Update:** Pushes the final `verdict` event.

### Step 4: Completion & Delivery
1. The AI service marks the job status as `COMPLETE` in PostgreSQL.
2. It publishes a final `done` event to Redis.
3. Spring Boot receives the `done` event, forwards it to the React frontend, and gracefully closes the SSE connection.
4. The frontend renders the final D3 confidence timeline and overall summary.

---

## 3. Data Integrity & Auditing

TruthStream is designed with data integrity in mind. Every major transition (Job Created, Claim Extracted, Source Found, Verdict Issued) is recorded in an append-only `audit_log` table in PostgreSQL. 

Because the backend operates highly asynchronously, Redis Pub/Sub provides the critical link ensuring the user is never left wondering what the system is doing, translating complex, multi-agent AI processes into a seamless, live-updating user interface.
