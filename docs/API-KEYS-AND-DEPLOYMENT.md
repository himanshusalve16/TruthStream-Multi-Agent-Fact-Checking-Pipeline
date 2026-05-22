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
OPENAI_API_KEY=sk-your-key-here
SERPAPI_KEY=replace-me
```

**Search:** If `SERPAPI_KEY` is unset or `replace-me`, TruthStream uses **DuckDuckGo** automatically (free, no API key). You can remove any old `BRAVE_API_KEY` line from `.env` — it is no longer used.

Generate secrets locally (PowerShell):

```powershell
# JWT_SECRET (64 hex chars)
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[System.BitConverter]::ToString($bytes) -replace '-', ''

# INTERNAL_API_SECRET (32 hex chars)
$bytes = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[System.BitConverter]::ToString($bytes) -replace '-', ''
```

Never commit `.env` to git.

---

## 2. OpenAI API key (current default for TruthStream)

TruthStream’s AI service uses the **OpenAI Python SDK** with:

- **Chat:** `gpt-4o` (claim extraction, bias, judge, source stance)
- **Embeddings:** `text-embedding-3-small` (claim deduplication via pgvector)

### How to get an OpenAI key

1. Go to [https://platform.openai.com](https://platform.openai.com).
2. Sign up or log in.
3. Open **API keys**: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).
4. Click **Create new secret key** → copy it once (starts with `sk-`).
5. Add billing: **Settings → Billing** — new accounts often receive a small free credit; after that usage is pay-as-you-go.
6. Set usage limits: **Settings → Limits** to avoid surprise bills.

Put the key in `.env`:

```env
OPENAI_API_KEY=sk-...
```

### Typical cost (rough)

- One article check (several LLM calls + embeddings): often **$0.05–$0.30** depending on article length and claim count.
- Monitor usage at [https://platform.openai.com/usage](https://platform.openai.com/usage).

---

## 3. Free & cheaper alternatives to OpenAI

TruthStream is wired to **OpenAI’s API and models by default**. Other providers work only if they expose an **OpenAI-compatible** HTTP API (chat + ideally embeddings), or you change `ai-service` code.

| Provider | Free tier? | Chat (like GPT-4o) | Embeddings | OpenAI-compatible? | Notes |
|----------|------------|--------------------|------------|--------------------|--------|
| **OpenAI** | Small trial credit | Yes (`gpt-4o`) | Yes | Native | What the repo uses today |
| **Groq** | Yes (rate limits) | Yes (Llama, etc.) | No | Yes (chat only) | Fast inference; you’d still need embeddings elsewhere |
| **OpenRouter** | Some free models | Yes | Varies | Yes | One API key, many models; [openrouter.ai](https://openrouter.ai) |
| **Google AI Studio (Gemini)** | Generous free tier | Yes | Yes (separate models) | Via adapter / code change | [aistudio.google.com](https://aistudio.google.com) |
| **Ollama (local)** | Free (your hardware) | Yes (local LLMs) | Limited | Yes (`http://localhost:11434/v1`) | Best for **dev/offline**; not for production scale |
| **Together AI** | Trial credits | Yes | Some | Partial | [together.ai](https://www.together.ai) |
| **Mistral** | Limited free | Yes | Yes | Own SDK | Code changes required |

### Practical recommendation

| Goal | Recommendation |
|------|----------------|
| **Easiest path (matches this repo)** | Use **OpenAI** with a spending limit |
| **Minimize cost in dev** | **Ollama** locally for chat + skip/disable SerpAPI (claims still run; sources may be empty) |
| **No code changes, cheaper chat** | **OpenRouter** with `OPENAI_BASE_URL` + model name env vars (requires a small code change in `embeddings.py` / agents — see below) |
| **Fully free cloud (more work)** | **Gemini** via Google AI Studio — replace OpenAI client calls in agents |

### Optional: OpenAI-compatible endpoint (Groq / Ollama / OpenRouter)

You can point the existing `AsyncOpenAI` client at another base URL (Groq, Ollama, OpenRouter):

```python
# Example only — not enabled by default in this repo
AsyncOpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url="https://api.groq.com/openai/v1",  # Groq
)
```

You must also set model names to ones that provider supports (e.g. `llama-3.3-70b-versatile` on Groq, not `gpt-4o`). Embeddings still need OpenAI or another embedding API unless you disable pgvector deduplication.

### Get keys for common alternatives

| Service | Sign up | API key location |
|---------|---------|------------------|
| **Groq** | [https://console.groq.com](https://console.groq.com) | API Keys section |
| **OpenRouter** | [https://openrouter.ai/keys](https://openrouter.ai/keys) | Create key |
| **Google Gemini** | [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Create API key |
| **Ollama** | [https://ollama.com](https://ollama.com) | No cloud key; run `ollama serve` locally |

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
4. **ECS task definitions:** Map env vars from **AWS Secrets Manager** (`OPENAI_API_KEY`, `JWT_SECRET`, etc.).
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
| `OPENAI_API_KEY` | Secrets Manager |
| `JWT_SECRET` | Secrets Manager |
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
| `OPENAI_API_KEY` | Yes (for full AI) | LLM + embeddings | [platform.openai.com](https://platform.openai.com/api-keys) |
| `SERPAPI_KEY` | No (optional) | Better search when set; else DuckDuckGo | [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) |
| `JWT_SECRET` | Yes | User auth tokens | Generate locally (see §1) |
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

Submit a **short pasted text** job (not a URL) first — it avoids scrape failures while you validate OpenAI + DB + Redis.

---

## Related docs

- [README.md](../README.md) — local dev quick start  
- [DEPLOY.md](../DEPLOY.md) — Railway + Vercel  
- [Truthstream blueprint.md](../Truthstream%20blueprint.md) — architecture  
