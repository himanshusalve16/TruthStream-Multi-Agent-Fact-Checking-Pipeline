# TruthStream

TruthStream extracts factual claims from news articles, finds corroborating and contradicting web sources, scores article bias, and produces a judge-synthesized verdict — all streamed live to the browser via Server-Sent Events.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, Vite, D3, TypeScript |
| API Gateway | Spring Boot 3, JWT, SSE relay |
| AI Service | Python FastAPI, OpenAI GPT-4o, 4 agents |
| Database | PostgreSQL 16 + pgvector |
| Queue / Pub-Sub | Redis |

## Architecture

```
Browser → Spring Boot (8080) → FastAPI (8000)
              ↓                      ↓
           Redis pub/sub         PostgreSQL
              ↑
         SSE stream to browser
```

**Pipeline:** URL/text → fetch & clean → extract claims → [find sources ∥ score bias] → judge → stream verdict via SSE

## Project structure

```
truthstream/
├── frontend/          React UI
├── backend/           Spring Boot API + auth + SSE
├── ai-service/        FastAPI agents + workers
├── infra/postgres/    DB extension init
├── docker-compose.yml
├── load-env.ps1       Windows .env loader
└── start-dev.ps1      Dev startup helper
```

## Prerequisites

- Docker Desktop (Postgres + Redis)
- Java 21, Maven (or `backend/mvnw.cmd`)
- Node.js 20+
- Python 3.11+
- API keys: `OPENAI_API_KEY` (required for AI); `SERPAPI_KEY` optional — search falls back to free DuckDuckGo (see `.env.example`)

## Quick start (Windows)

```powershell
# 1. Copy and fill secrets
Copy-Item .env.example .env
# Edit .env with your API keys and JWT_SECRET

# 2. Start infrastructure
. .\load-env.ps1
docker compose up db redis -d

# 3. AI service (new terminal)
cd ai-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
. ..\load-env.ps1 -EnvFile ..\.env
uvicorn main:app --reload --port 8000

# 4. Backend (new terminal)
cd backend
. ..\load-env.ps1 -EnvFile ..\.env
$env:SPRING_DATASOURCE_URL = "jdbc:postgresql://localhost:5432/truthstream"
$env:SPRING_DATASOURCE_USERNAME = $env:DB_USER
$env:SPRING_DATASOURCE_PASSWORD = $env:DB_PASSWORD
.\mvnw.cmd spring-boot:run

# 5. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 — register, sign in, submit a URL, and watch live results at `/jobs/:id`.

Or run `.\start-dev.ps1` for infrastructure + printed commands for the other services.

## API overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Get JWT |
| POST | `/api/jobs` | Submit URL or text (202) |
| GET | `/api/jobs/{id}/stream` | SSE events (`?token=` for EventSource) |
| GET | `/api/jobs/{id}/verdict` | Full verdict when complete |
| GET | `/api/jobs` | Paginated job history |

## Full Docker

```powershell
. .\load-env.ps1
docker compose up --build
```

Frontend: http://localhost:3000 · Backend: http://localhost:8080 · FastAPI docs: http://localhost:8000/docs

## Documentation

- `Truthstream blueprint.md` — full system design, agents, prompts, milestones
- `Truthstream windows setup roadmap.md` — Windows tooling and verification checklist
- [`docs/API-KEYS-AND-DEPLOYMENT.md`](docs/API-KEYS-AND-DEPLOYMENT.md) — **API keys**, free OpenAI alternatives, **Docker** & **AWS** deploy
- `DEPLOY.md` — Railway + Vercel deployment steps

## Tests

```powershell
cd frontend && npm run test
cd backend && .\mvnw.cmd test
cd ai-service && python -m pytest tests/ -q
```

CI runs all three on push via `.github/workflows/ci.yml`.

## License

Portfolio / educational use.
