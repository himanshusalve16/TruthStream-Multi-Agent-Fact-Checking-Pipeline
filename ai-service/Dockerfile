# ─────────────────────────────────────────────────────────────────────────────
# TruthStream AI Service — Dockerfile
# Python 3.12-slim, non-root, layer-cached dependency install
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency install ───────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app

# System packages needed to build lxml + asyncpg C extensions
# libpq-dev  → asyncpg native connection
# gcc        → C extension compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file first so pip install is a cached layer.
# Rebuilding only when requirements.txt changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system libraries only (no gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -m -u 1000 -s /bin/sh appuser

# Copy installed Python packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy application source (note: .dockerignore excludes .venv, __pycache__, tests)
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Single worker: the app uses asyncio internally for concurrency.
# Using multiple uvicorn workers would require shared state (Redis job queue
# is fine, but in-process app.state would not be shared).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info"]
