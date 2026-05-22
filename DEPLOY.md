# TruthStream Deployment Guide

> For **Docker Compose** (local/VPS), **AWS** (EC2 / ECS), and how to obtain **OpenAI / SerpAPI** API keys (DuckDuckGo search needs no key), see **[docs/API-KEYS-AND-DEPLOYMENT.md](docs/API-KEYS-AND-DEPLOYMENT.md)**.

## Overview

| Service | Platform | Notes |
|---------|----------|-------|
| Frontend | [Vercel](https://vercel.com) | Root: `frontend/` |
| Backend | [Railway](https://railway.app) | `backend/Dockerfile` |
| AI Service | Railway | `ai-service/Dockerfile` |
| PostgreSQL | Railway plugin | Enable pgvector: run `infra/postgres/init.sql` once |
| Redis | Railway plugin | |

## 1. Railway — Database & Redis

1. Create a new Railway project.
2. Add **PostgreSQL** and **Redis** from the template marketplace.
3. Connect to Postgres and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

4. Flyway migrations run automatically when the backend starts.

## 2. Railway — AI Service

1. New service → Deploy from GitHub repo → set root directory to `ai-service`.
2. Set environment variables:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (or jdbc-style converted to postgresql://) |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` |
| `OPENAI_API_KEY` | your key |
| `SERPAPI_KEY` | optional — omit for free DuckDuckGo search |
| `INTERNAL_API_SECRET` | random 32+ char string |

3. Note the public URL (e.g. `https://truthstream-ai.up.railway.app`).

## 3. Railway — Backend

1. New service → root `backend`.
2. Environment variables:

| Variable | Value |
|----------|-------|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://HOST:PORT/railway` |
| `SPRING_DATASOURCE_USERNAME` | from Postgres |
| `SPRING_DATASOURCE_PASSWORD` | from Postgres |
| `SPRING_DATA_REDIS_HOST` | from Redis |
| `SPRING_DATA_REDIS_PORT` | `6379` |
| `FASTAPI_BASE_URL` | AI service internal/public URL |
| `JWT_SECRET` | 64+ char random hex |
| `INTERNAL_API_SECRET` | same as AI service |
| `JWT_EXPIRY_MS` | `3600000` |

3. Generate domain for HTTPS.

## 4. Vercel — Frontend

1. Import repo, set **Root Directory** to `frontend`.
2. Build: `npm run build` · Output: `dist`
3. Environment:

| Variable | Value |
|----------|-------|
| `VITE_API_BASE_URL` | Railway backend URL (e.g. `https://truthstream-api.up.railway.app`) |

4. Update `frontend/vercel.json` rewrite destination to your backend URL, **or** rely on `VITE_API_BASE_URL` only (preferred — API calls go directly to backend; configure CORS on backend for your `*.vercel.app` origin).

5. In `backend` `WebConfig`, add your Vercel production URL to `allowedOriginPatterns`.

## 5. CORS

Ensure `WebConfig.java` includes:

```java
.allowedOriginPatterns("http://localhost:3000", "https://*.vercel.app", "https://your-app.vercel.app")
```

## 6. Smoke test

1. Register on production frontend.
2. Submit a short text article (avoids scrape failures during first test).
3. Confirm SSE events and final verdict render.

## Local full-stack Docker

```powershell
. .\load-env.ps1
docker compose up --build
```

Frontend: http://localhost:3000
