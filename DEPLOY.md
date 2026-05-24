# TruthStream Deployment Guide

> For **Docker Compose** (local/VPS), **AWS** (EC2 / ECS), and how to obtain **Gemini / SerpAPI** API keys (DuckDuckGo search needs no key), see **[docs/API-KEYS-AND-DEPLOYMENT.md](docs/API-KEYS-AND-DEPLOYMENT.md)**.

## Overview

| Service | Platform | Notes |
|---------|----------|-------|
| Frontend | [Vercel](https://vercel.com) / [Render](https://render.com) | Root: `frontend/` |
| Backend | [Railway](https://railway.app) / Render | `backend/Dockerfile` |
| AI Service | Railway / Render | `ai-service/Dockerfile` |
| PostgreSQL | Railway / Render | Enable pgvector: run `infra/postgres/init.sql` once |
| Redis | Railway / Render | |

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
| `GEMINI_API_KEY` | your key |
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
| `INTERNAL_API_SECRET` | same as AI service |

3. Generate domain for HTTPS.

## 4. Render Deployment (Alternative to Railway)

### 4.1 Render — Database & Redis
1. Create a **PostgreSQL** database on Render. Once provisioned, connect via external tool (e.g., pgAdmin or psql) and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
2. Create a **Redis** instance on Render.

### 4.2 Render — AI Service (Private or Web Service)
1. Create a **Web Service** (or Private Service if backend is in same region).
2. Connect GitHub repo, set **Root Directory** to `ai-service`.
3. Set Environment to **Docker**.
4. Environment Variables:
   - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (use internal PostgreSQL credentials from Render)
   - `REDIS_HOST`, `REDIS_PORT` (use internal Redis credentials from Render)
   - `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, etc.
   - `INTERNAL_API_SECRET`: random 32+ char string

### 4.3 Render — Backend (Web Service)
1. Create a **Web Service**, set **Root Directory** to `backend`.
2. Set Environment to **Docker**.
3. Environment Variables:
   - `SPRING_DATASOURCE_URL`: `jdbc:postgresql://<RENDER_INTERNAL_DB_HOST>:<PORT>/<DB_NAME>`
   - `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD`
   - `SPRING_DATA_REDIS_HOST`, `SPRING_DATA_REDIS_PORT`
   - `FASTAPI_BASE_URL`: AI service internal URL (if Private Service) or public URL
   - `INTERNAL_API_SECRET`: same as AI service
   - `JWT_SECRET`: 64-hex char string

### 4.4 Render — Frontend (Static Site)
1. Create a **Static Site**, set **Root Directory** to `frontend`.
2. Build Command: `npm run build`
3. Publish Directory: `dist`
4. Environment Variables:
   - `VITE_API_BASE_URL`: The public URL of your Render Backend service.

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
