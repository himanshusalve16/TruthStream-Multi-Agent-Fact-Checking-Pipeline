# TruthStream

AI-powered multi-agent fact-checking. Submit any article URL or text, and get live-streamed claim extraction, source verification, bias analysis, and a synthesized verdict.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, Vite 8, TailwindCSS v4, TypeScript |
| API Gateway | Spring Boot 3.2, SSE relay |
| AI Service | Python 3.12, FastAPI, Gemini 2.5 Flash, 4 agents |
| Database | PostgreSQL 16 + pgvector |
| Queue / Pub-Sub | Redis 7 |
| Containerization | Docker Compose |

## Architecture

```
Browser
  │
  ▼
nginx (port 3000)  ──/api proxy──►  Spring Boot (port 8080)
                                          │              │
                                       Redis         FastAPI (port 8000)
                                          │              │
                                    SSE stream ◄── PostgreSQL + pgvector
```

**Pipeline:** URL/text → fetch & clean → extract claims → [find sources ∥ score bias] → judge → stream verdict via SSE

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose v2)
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

> No local Python, Java, or Node.js required — everything runs in Docker.

### 1. Clone and configure

```powershell
git clone https://github.com/your-username/truthstream.git
cd truthstream

# Create your environment file from the template
Copy-Item .env.example .env
```

Open `.env` and fill in:
- `GEMINI_API_KEY` — **required** for the AI pipeline
- `INTERNAL_API_SECRET` — generate with: `python -c "import secrets; print(secrets.token_hex(16))"`
- `DB_PASSWORD` — choose any password
- `SERPAPI_KEY` — optional; falls back to DuckDuckGo if not set

### 2. Start everything

```powershell
docker compose up --build
```

Or use the helper script (adds pre-flight checks):
```powershell
.\start.ps1
```

Wait ~60 seconds for all services to become healthy. You'll see:
```
truthstream-backend  | Started TruthstreamBackendApplication in 12.3 seconds
truthstream-ai       | AI service ready.
truthstream-frontend | /docker-entrypoint.sh: Configuration complete
```

### 3. Open the app

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:3000 |
| Backend health | http://localhost:8080/actuator/health |
| FastAPI docs | http://localhost:8000/docs |

Register, sign in, and submit any news article URL.

### Stop

```powershell
docker compose down           # stop, keep database
.\stop.ps1                    # same, with status output
.\stop.ps1 -Clean             # stop + destroy database volumes (fresh start)
```

---

## Port Conflicts

If any port is already in use, change the corresponding `*_PORT` in `.env`:

```env
DB_PORT=5433        # was 5432
REDIS_PORT=6380     # was 6379
SPRING_PORT=8081    # was 8080
FASTAPI_PORT=8001   # was 8000
FRONTEND_PORT=3001  # was 3000
```

Then restart: `docker compose up --build`

---

## Project Structure

```
truthstream/
├── frontend/               React + Vite + TailwindCSS
│   ├── src/
│   ├── Dockerfile          Node 20 build → nginx serve
│   ├── nginx.conf          API proxy + SSE headers
│   └── .dockerignore
├── backend/                Spring Boot 3 — SSE relay
│   ├── src/
│   ├── Dockerfile          JDK 21 build → JRE runtime
│   └── .dockerignore
├── ai-service/             FastAPI — 4 AI agents
│   ├── agents/             extractor, source_finder, bias_scorer, judge
│   ├── db/                 asyncpg queries
│   ├── services/           scraper, embeddings, redis_publisher
│   ├── Dockerfile          Python 3.12 multi-stage
│   └── .dockerignore
├── infra/postgres/
│   └── init.sql            pgvector extension setup
├── docker-compose.yml      Full orchestration
├── .env.example            Safe template — commit this
├── .env                    Real secrets — in .gitignore
├── start.ps1               Windows startup script
└── stop.ps1                Windows teardown script
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/jobs` | Submit URL or text |
| `GET` | `/api/jobs` | Paginated job history |
| `GET` | `/api/jobs/{id}/stream` | SSE live stream |
| `GET` | `/api/jobs/{id}/verdict` | Full verdict |
| `GET` | `/api/jobs/{id}/sources` | Sources by claim |

---

## Startup Order & Health Checks

Docker Compose enforces this startup sequence:

```
db (pg_isready healthy)
redis (PING healthy)
    └─► ai-service (/health returns 200)
            └─► backend (actuator/health returns UP)
                    └─► frontend (nginx starts)
```

Each service has a `healthcheck` and uses `depends_on: condition: service_healthy`. Spring Boot and FastAPI both implement retry logic for transient DB/Redis connection failures during startup.

---

## Development (local, without Docker)

If you want to run services locally for hot-reload development:

```powershell
# 1. Start infrastructure only
docker compose up db redis -d

# 2. AI service (new terminal)
cd ai-service
python -m venv .venv && .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/truthstream"
$env:REDIS_URL = "redis://localhost:6379"
$env:GEMINI_API_KEY = "sk-your-key"
$env:INTERNAL_API_SECRET = "your-secret"
uvicorn main:app --reload --port 8000

# 3. Backend (new terminal)
cd backend
$env:SPRING_DATASOURCE_URL = "jdbc:postgresql://localhost:5432/truthstream"
$env:SPRING_DATASOURCE_USERNAME = "postgres"
$env:SPRING_DATASOURCE_PASSWORD = "postgres"
$env:SPRING_DATA_REDIS_HOST = "localhost"
$env:SPRING_DATA_REDIS_PORT = "6379"
$env:FASTAPI_BASE_URL = "http://localhost:8000"
$env:INTERNAL_API_SECRET = "your-secret"
.\mvnw.cmd spring-boot:run

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev       # http://localhost:3000, proxies /api → localhost:8080
```

---

## Tests

```powershell
cd frontend   && npm run test
cd backend    && .\mvnw.cmd test
cd ai-service && python -m pytest tests/ -q
```

---

## Troubleshooting

**Port 5432 already in use**
→ A local PostgreSQL is running. Either stop it, or change `DB_PORT=5433` in `.env`.

**"replace-me" API key errors**
→ Edit `.env` and set a real `GEMINI_API_KEY`.

**ai-service keeps restarting**
→ It retries DB connection up to 10 times. Check `docker compose logs ai-service` for the exact error.

**Fresh start (wipe database)**
```powershell
.\stop.ps1 -Clean
.\start.ps1
```

**Rebuild without cache**
```powershell
docker compose build --no-cache
docker compose up
```

---

## License

Portfolio / educational use.
