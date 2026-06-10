# Changelog

All notable changes to the **TruthStream** project are documented in this file.

---

## [1.1.0] - 2026-06-11

### Added
- **Adaptive Multi-Pipeline System**:
  - Implemented automatic routing of articles based on input length, complexity, and system load.
  - Added **Fast Path** (instant analysis for short texts under 600 words via single-pass model evaluation, complete in 3.5s – 5.0s).
  - Added **Standard Path** (utilizes Search-Snippet Bypass mode, complete in 6.8s – 11.7s).
  - Added **Deep Path** (utilizes concurrent background full-text scraping for top 3 sources, complete in 12.3s – 26.7s).
  - Added **Recovery/Fallback Path** (best-effort summary-based verdict generated when models or quotas fail).
  - Added **High-Load Downgrade**: Automatically routes standard/deep requests to the Fast Path and truncates inputs to 600 words when the queue time exceeds 15.0 seconds.
- **Source-First Verification Architecture**:
  - Replaced AI reasoning fallback text with external source corroboration scores.
  - Claims are marked `UNVERIFIABLE` if zero corroborating external sources are found.
  - Claim-to-source mapping now carries attributes: page title, absolute URL, base domain name, snippet, and stance labels (`SUPPORT`, `CONTRADICT`, `NEUTRAL`).
- **Resource Constraints and Caps**:
  - Added claim limit budget: at most 5 claims per article (capped at 2 on Fast Path and 3 under quota pressure).
  - Added source limit budget: at most 2 sources per claim.
  - Added Search Query limit budget: max 1 query for Fast/Recovery, 2 for Standard, and 3 for Deep.
  - Added early search termination: stops queries as soon as at least 1 high-quality supporting or refuting source is found.
- **Modern Dark AI Dashboard UI**:
  - Redesigned the frontend with a premium dark dashboard, using backdrop-blur glassmorphic panels and custom HSL accent colors.
  - Added a live pipeline orchestration board and worker execution feed in `LoadingState.tsx`.
  - Added Verdict Banner Cards and Claim Consensus Stream cards detailing stances and source alignments.
  - Added the Verification Sources accordion panel showing stances and domain metadata.

### Optimized
- **Startup Connection Retries**:
  - The Spring Boot backend gateway uses HikariCP with infinite retry loops (`initialization-fail-timeout: -1`) to block and wait for database containers to wake up.
  - The FastAPI service uses asyncpg and aioredis retry loops with exponential backoff on startup to prevent boot crash-looping.
- **Search Query Quality & Key Rotation**:
  - Configured multi-key rotation fallback in FastAPI (`GEMINI_API_KEY_1` to `GEMINI_API_KEY_4`) with automatic cool-down cooldowns.
  - Expanded search term parser stop-words with navigational and boilerplate UI terms to maximize SerpAPI query relevance.
  - Implemented automatic fallback to DuckDuckGo HTML scraping if SerpAPI is exhausted.
- **Fast Gateway Caching**:
  - Ingested URL MD5 caching checks database verdicts from the last 24 hours, returning cached claims instantly and bypassing FastAPI processing.
  - Implemented pgvector claim semantic matching: uses cosine similarity to match extracted claims against the database from the last 24 hours to reuse verdicts.

### Fixed
- **Verdict Dropping Bug**: Fixed a key mapping issue where extracted claims without temporary IDs were overwriting each other in memory, causing the verification logic to drop sources and default to false `UNVERIFIABLE` verdicts.
- **Observability Metric Table Mismatches**: Logged and bypassed the known table naming mismatch (`audit_logs` vs `audit_log`) in telemetry routers to ensure main operations remain stable.
