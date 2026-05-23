# TruthStream — API Keys, Free AI Options, Docker & AWS Deployment

This guide covers how to obtain API keys, free/low-cost alternatives to OpenAI, and how to deploy the full stack with **Docker** or on **AWS**.

---

## 1. Fix your `.env` file

At the project root, copy the template if you have not already:

```powershell
Copy-Item .env.example .env
```

Each key must use `KEY=value` format (no spaces around `=`). Example:

```env
GEMINI_API_KEY=sk-your-key-here
SERPAPI_KEY=replace-me
```

**Search:** If `SERPAPI_KEY` is unset or `replace-me`, TruthStream uses **DuckDuckGo** automatically (free, no API key). You can remove any old `BRAVE_API_KEY` line from `.env` — it is no longer used.

Generate secrets locally (PowerShell):

```powershell
# INTERNAL_API_SECRET (32 hex chars)
$bytes = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[System.BitConverter]::ToString($bytes) -replace '-', ''
```

Never commit `.env` to git.

---

## 2. Gemini API key (current default for TruthStream)

TruthStream’s AI service uses the **Google GenAI Python SDK** with:

- **Chat:** `gemini-2.5-flash` (claim extraction, bias, judge, source stance)
- **Embeddings:** `text-embedding-004` (claim deduplication via pgvector)

### How to get a Gemini key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Sign in with your Google account.
3. Click **Create API key** and copy it once.
4. Set usage limits if needed in your Google Cloud Console.

Put the key in `.env`:

```env
GEMINI_API_KEY=sk-...
```

### Typical cost (rough)

- Google Gemini 2.5 Flash has a very generous free tier (up to 1500 requests/day).
- For most developers and portfolio demos, usage will remain **100% free**.

---

## 3. Alternatives to Gemini

TruthStream is wired to **Google Gemini’s API by default**. Other providers work only if you modify the code in the `ai-service/agents` and `ai-service/services` to use their respective SDKs (such as OpenAI, Anthropic, or Ollama).

If you wish to switch back to OpenAI, you will need to:
1. Re-install the `openai` python package.
2. Update the agents to use `AsyncOpenAI`.
3. Re-adjust the database schema `VECTOR` dimension from 768 to 1536 since OpenAI's embeddings are larger.

---

## 4. Web search (SerpAPI optional + DuckDuckGo free default)

TruthStream finds corroborating sources with this order:

1. **SerpAPI** — if `SERPAPI_KEY` is set to a real key (~100 free searches/month).
2. **DuckDuckGo** — if SerpAPI is missing, exhausted, or returns no results (**no API key**, no billing).

### Option A — DuckDuckGo only (recommended if Brave/SerpAPI are not available)

Leave SerpAPI unset or as placeholder:

```env
SERPAPI_KEY=replace-me
```

No other search key is required. DuckDuckGo uses the same `httpx` + BeautifulSoup stack already in `requirements.txt` (no extra package).

### Option B — SerpAPI (better result quality when you have quota)

1. Sign up: [https://serpapi.com](https://serpapi.com)
2. Copy key: [https://serpapi.com/manage-api-key](https://serpapi.com/manage-api-key)
3. Set in `.env`:

```env
SERPAPI_KEY=your_serpapi_key_here
```

DuckDuckGo still runs automatically if SerpAPI fails or hits its monthly limit.

Docs: [https://serpapi.com/search-api](https://serpapi.com/search-api)

---

## 5. Deploy with Docker (full stack)

TruthStream includes `docker-compose.yml` for all five services: **db**, **redis**, **ai-service**, **backend**, **frontend**.

### Prerequisites

- Docker Desktop (Windows/Mac) or Docker Engine + Compose v2 (Linux)
- Filled `.env` at repo root (see sections 1–5)

### Steps

```powershell
cd D:\Truthstream

# Load variables into the shell (Windows)
. .\load-env.ps1

# Build and start everything (first run: 5–10 minutes)
docker compose up --build -d

# Check status — db and redis should be "healthy"
docker compose ps

# View logs
docker compose logs -f backend
docker compose logs -f ai-service
```

### Access URLs (default)

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8080 |
| Backend health | http://localhost:8080/actuator/health |
| FastAPI docs | http://localhost:8000/docs |

### Production-oriented Docker notes

1. **Do not expose Postgres/Redis** to the public internet — remove host port mappings or bind to `127.0.0.1` only.
2. Use **strong** `DB_PASSWORD`, `JWT_SECRET`, `INTERNAL_API_SECRET`.
3. Put **HTTPS** in front (nginx, Caddy, or a cloud load balancer).
4. For frontend API calls in production, set build arg when building frontend:

   ```powershell
   docker compose build frontend --build-arg VITE_API_BASE_URL=https://api.yourdomain.com
   ```

5. **Persist data:** `pgdata` volume keeps PostgreSQL data across restarts.
6. **Stop / reset:**

   ```powershell
   docker compose stop          # stop containers
   docker compose down          # stop and remove containers
   docker compose down -v       # also delete database volume (fresh DB)
   ```

### Dev vs Docker

| Mode | When to use |
|------|-------------|
| `docker compose up db redis -d` only + local `mvnw` / `uvicorn` / `npm run dev` | Daily coding (hot reload) |
| `docker compose up --build` | Integration test, demo, single-server deploy |

---

## 7. Deploy on AWS

There is no single “AWS button” for this monorepo. Common patterns:

```mermaid
flowchart LR
  Users[Users] --> CF[CloudFront optional]
  CF --> ALB[Application Load Balancer]
  ALB --> FE[Frontend ECS or S3]
  ALB --> BE[Spring Boot ECS]
  BE --> AI[FastAPI ECS]
  BE --> Redis[ElastiCache Redis]
  AI --> Redis
  BE --> RDS[(RDS PostgreSQL + pgvector)]
  AI --> RDS
```

### Option A — Single EC2 + Docker Compose (simplest)

Best for portfolio / low traffic.

1. **Launch EC2** (Ubuntu 22.04, `t3.medium` or larger; 4 GB+ RAM recommended).
2. **Security group:** allow `22` (SSH), `80`/`443` (HTTP/S) from your IP or `0.0.0.0/0` for public demo.
3. Install Docker on the instance:

   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
   sudo usermod -aG docker ubuntu
   ```

4. Clone the repo, copy `.env` (use **scp** or Secrets Manager — never commit secrets).
5. Run `docker compose up --build -d`.
6. Point a domain to the EC2 public IP; use **nginx** on the host or **Caddy** for HTTPS (Let’s Encrypt).

**Pros:** Fast, matches local Docker. **Cons:** You manage the VM, backups, and scaling.

### Option B — AWS ECS Fargate (recommended for “real” AWS)

Run each container as its own service.

| Component | AWS service |
|-----------|-------------|
| Spring Boot | ECS Fargate service + ALB target group |
| FastAPI | ECS Fargate service (internal) |
| React static | **S3 + CloudFront** (build `frontend/dist`, upload) |
| PostgreSQL | **RDS PostgreSQL 16** — enable extension `vector` via migration / parameter group |
| Redis | **ElastiCache Redis** |

High-level steps:

1. **ECR:** Create repositories `truthstream-backend`, `truthstream-ai`, push images from `backend/Dockerfile` and `ai-service/Dockerfile`.
2. **RDS:** Create Postgres DB; run Flyway via backend on startup; run `infra/postgres/init.sql` logic (`CREATE EXTENSION vector`) once.
3. **ElastiCache:** Redis cluster; set `SPRING_DATA_REDIS_HOST` and `REDIS_URL` in task env.
4. **ECS task definitions:** Map env vars from **AWS Secrets Manager** (`GEMINI_API_KEY`, etc.).
5. **ALB:** Listener 443 → backend target group `:8080`; path rules optional for `/api`.
6. **CloudFront:** Origin = S3 bucket (frontend); behavior: `/api/*` → ALB (or call API subdomain directly with CORS).

**Internal networking:** Backend calls AI at `http://ai-service.local:8000` via ECS service discovery or private ALB.

### Option C — EKS (Kubernetes)

Same containers as ECS, more operational overhead. Only worth it if you already run Kubernetes.

### AWS environment variable mapping

| `.env` (local) | AWS |
|----------------|-----|
| `SPRING_DATASOURCE_URL` | RDS JDBC URL |
| `DATABASE_URL` (ai-service) | `postgresql://user:pass@rds-host:5432/truthstream` |
| `REDIS_URL` | `redis://elasticache-host:6379` |
| `GEMINI_API_KEY` | Secrets Manager |
| `FASTAPI_BASE_URL` | Internal AI service URL |

### pgvector on RDS

After RDS is up, connect once and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

Flyway migrations in the backend create application tables.

### Cost tip (AWS)

For a demo, **one EC2 + Docker Compose** is often **$15–40/month**. Full ECS + RDS + ElastiCache is typically **$80–200+/month** depending on instance sizes.

---

## 8. Quick reference — all keys in `.env`

| Variable | Required? | Purpose | Get it from |
|----------|-----------|---------|-------------|
| `GEMINI_API_KEY` | Yes (for full AI) | LLM + embeddings | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) |
| `SERPAPI_KEY` | No (optional) | Better search when set; else DuckDuckGo | [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) |
| `INTERNAL_API_SECRET` | Yes | Backend → AI internal calls | Generate locally (see §1) |
| `DB_PASSWORD` | Yes | PostgreSQL | You choose |

---

## 9. Verify keys work

```powershell
# Infrastructure only
docker compose up db redis -d

# AI health (after ai-service is up)
Invoke-WebRequest http://localhost:8000/health

# Backend health
Invoke-WebRequest http://localhost:8080/actuator/health
```

Submit a **short pasted text** job (not a URL) first — it avoids scrape failures while you validate Gemini + DB + Redis.

---

## Related docs

- [README.md](../README.md) — local dev quick start  
- [DEPLOY.md](../DEPLOY.md) — Railway + Vercel  
- [Truthstream blueprint.md](../Truthstream%20blueprint.md) — architecture  
