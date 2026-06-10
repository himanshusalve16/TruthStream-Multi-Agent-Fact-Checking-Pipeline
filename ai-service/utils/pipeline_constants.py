"""
Shared pipeline constants for TruthStream.

Single source of truth for claim caps, source budgets, and timeouts
across all pipeline types (fast, standard, deep, recovery).
"""

# ── Claim processing limits ────────────────────────────────────────────────
MAX_CLAIMS = 5          # Hard cap: never process more than 5 claims per article
MAX_CLAIMS_FAST = 2    # Fast path: short articles, cap at 2 claims
MAX_CLAIMS_MODERATE = 3  # When under quota pressure: cap at 3 regardless of path

# ── Source collection budgets ──────────────────────────────────────────────
# Max SerpAPI queries per article per pipeline (not per claim)
SOURCE_QUERIES_FAST = 1       # 1 article-level query, distribute across claims
SOURCE_QUERIES_STANDARD = 2   # 2 article-level queries
SOURCE_QUERIES_DEEP = 3       # 3 article-level queries (better coverage)
SOURCE_QUERIES_RECOVERY = 1   # 1 query: best effort

# Max sources per claim after pool distribution
MAX_SOURCES_PER_CLAIM_FAST = 2
MAX_SOURCES_PER_CLAIM_STANDARD = 2
MAX_SOURCES_PER_CLAIM_DEEP = 2

# ── Timeouts (seconds) ─────────────────────────────────────────────────────
EXTRACTION_TIMEOUT_FAST = 15.0
EXTRACTION_TIMEOUT_STANDARD = 10.0
EXTRACTION_TIMEOUT_DEEP = 12.0
SOURCE_POOL_TIMEOUT_FAST = 8.0
SOURCE_POOL_TIMEOUT_STANDARD = 12.0
SOURCE_POOL_TIMEOUT_DEEP = 15.0

# ── Source quality thresholds ──────────────────────────────────────────────
MIN_SNIPPET_CHARS = 30   # Minimum snippet length to count as a real source
STOP_EARLY_THRESHOLD = 1  # Stop source search per claim once this many good sources found
