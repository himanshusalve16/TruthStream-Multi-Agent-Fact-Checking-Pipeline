# TruthStream — Railway & Render Deployment Guide

This guide details how to deploy TruthStream's multi-service architecture to cloud application platforms like **Railway** or **Render**, using Vercel for static frontend hosting.

---

## Service Deployment Matrix

The monorepo contains services that should be deployed as follows:

| Service | Build Target | Recommended Platform | Port |
|---|---|---|---|
| **Frontend** | Static build (`/frontend`) | [Vercel](https://vercel.com) / Render Static | N/A |
| **Gateway** | Dockerfile (`/backend`) | [Render](https://render.com) | `8080` (Render assigns) |
| **AI Service** | Dockerfile (`/ai-service`) | Render | `8000` (Render assigns) |
| **Eureka Server** | Dockerfile (`/eureka-server`) | Render | `8761` (Render assigns) |
| **PostgreSQL** | Managed Database | Render / Railway | Requires `vector`, `uuid-ossp`, `pgcrypto` |
| **Redis** | Managed Cache | Render / Railway | Pub/Sub + queue |

> [!IMPORTANT]
> **Deploy order**: Eureka Server → AI Service → Gateway → Frontend
> Each service depends on the ones before it being reachable.

---

## 1. Database & Redis Setup

Regardless of the platform, your Postgres instance must support the `pgvector` extension.

1. Provision a PostgreSQL 16 database.
2. Connect using a database tool (e.g., `psql` or `pgAdmin`) and run the initialization commands:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
3. Provision a Redis 7 instance. The Spring Boot backend uses it to subscribe to real-time events, and FastAPI uses it to queue tasks.

---

## 2. Deploying the AI Service (Python FastAPI)

Deploy the `ai-service` folder as a Docker service.

### Environment Variables for FastAPI

| Variable | Value | Description |
|---|---|---|
| `DB_HOST` | your postgres host | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `truthstream` | Database name |
| `DB_USER` | your db user | Database username |
| `DB_PASSWORD` | your db password | Database password |
| `REDIS_HOST` | your redis host | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `GEMINI_API_KEY_1` | your gemini key | Primary Gemini API key |
| `GEMINI_API_KEY_2..4` | optional | Additional keys for rotation |
| `SERPAPI_KEY` | your serpapi key | Optional — falls back to DuckDuckGo |
| `INTERNAL_API_SECRET` | random hex string | Shared secret matching gateway |
| `EUREKA_SERVER_URL` | `https://truthstream-eureka.onrender.com/eureka/` | Online Eureka registry URL |
| `INSTANCE_HOST` | `ai-service-w29p.onrender.com` | **Your** Render AI service hostname (no https://) |
| `INSTANCE_PORT` | `10000` | Render internal port (check Render dashboard) |

> [!IMPORTANT]
> Set `INSTANCE_HOST` to the hostname shown in your Render AI service's **Settings → Public URL**,
> removing the `https://` prefix. This is what Eureka registers and what the gateway discovers.

*FastAPI listens on the port Render assigns (usually `10000`). This is set via `$PORT`.*

---

## 3. Deploying the Gateway (Spring Boot)

Deploy the `backend` folder as a Docker service. Flyway migrations run automatically
on startup to initialize the application tables (`users`, `articles`, `jobs`, `claims`,
`sources`, `verdicts`, `bias_results`, `audit_log`).

### Environment Variables for Spring Boot

| Variable | Value | Description |
|---|---|---|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://host:port/db` | JDBC Postgres connection string |
| `SPRING_DATASOURCE_USERNAME` | your db user | DB username |
| `SPRING_DATASOURCE_PASSWORD` | your db password | DB password |
| `SPRING_DATA_REDIS_HOST` | your redis host | Redis host |
| `SPRING_DATA_REDIS_PORT` | `6379` | Redis port |
| `FASTAPI_BASE_URL` | `https://ai-service-w29p.onrender.com` | **Static fallback** URL if Eureka unavailable |
| `INTERNAL_API_SECRET` | random hex string | Shared secret matching ai-service |
| `JWT_SECRET` | 64-char hex string | JWT signing secret |
| `JWT_EXPIRY_MS` | `3600000` | JWT token validity (ms) |
| `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` | `https://truthstream-eureka.onrender.com/eureka/` | Online Eureka registry URL |
| `EUREKA_CLIENT_ENABLED` | `true` | Enable Eureka client registration |

*Spring Boot exposes port `8080` (Render assigns the actual port via `$PORT`).*

---

## 4. Deploying the Frontend (React Vite)

Deploy the `frontend` folder to **Vercel** or **Render Static Sites**.

### Configuration Steps
1. Create a new project, select the repository, and set the **Root Directory** to `frontend`.
2. Set the build parameters:
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. Configure the environment variable:
   - `VITE_API_BASE_URL`: Set this to the public URL of your Spring Boot backend (e.g., `https://truthstream-backend.up.railway.app`).

### CORS Configuration
Ensure the backend accepts requests from your frontend domains. The CORS origins are defined in `WebConfig.java` in the backend. If your frontend runs on a custom Vercel domain, add it to the CORS configuration:

```java
.allowedOriginPatterns("http://localhost:3000", "https://*.vercel.app", "https://your-app.com")
```

---

## 5. Deploying the Eureka Server (NEW)

Deploy the `eureka-server` folder as a new Docker web service on Render.

### Render Settings

| Setting | Value |
|---|---|
| **Name** | `truthstream-eureka` |
| **Root Directory** | `eureka-server` |
| **Runtime** | Docker |
| **Health Check Path** | `/actuator/health` |

### Environment Variables

Render injects `$PORT` automatically — no manual configuration needed.

Optionally set:

| Variable | Value | Description |
|---|---|---|
| `PORT` | *(auto-injected by Render)* | Render sets this automatically |

### After Deployment

The Eureka dashboard is accessible at:
```
https://truthstream-eureka.onrender.com
```

Expected dashboard content:
- `TRUTHSTREAM-GATEWAY` — UP (Spring Boot gateway)
- `TRUTHSTREAM-AI-SERVICE` — UP (FastAPI AI service)

> [!NOTE]
> On Render free tier, services sleep after ~15 minutes of inactivity. The dashboard
> may show 0 registered instances if all services are sleeping. This is expected.
> The fallback URL (`FASTAPI_BASE_URL`) ensures routing still works.

---

## 6. Verifying the Deployment

Run a smoke test to confirm that services are communicating correctly:
1. Register a new user account through the frontend UI.
2. Submit a short text snippet (e.g., "The unemployment rate dropped to 3.4% in 2024"). This runs standard analysis and verifies the database, Redis queue, and Gemini API connections.
3. Verify that SSE events display in the UI and that the final confidence gauge and verdict render on completion.

---

## 6. Render Free Tier Keepalive & Cold-Start Mitigation

When deployed to Render's free tier, containers automatically sleep after 15 minutes of inactivity. This results in startup cold starts of 15–30+ seconds. To mitigate this without adding heavy pipeline load or hitting resource quotas, TruthStream implements a dual-layer keepalive and state-aware health architecture.

### Internal Self-Keepalive Loop
FastAPI spawns an internal background task (`keepalive_loop`) at startup. Every 5 minutes, it sends a lightweight HTTP ping to its local `/health` endpoint. 
> [!NOTE]
> Since Render suspends container processes entirely during sleep, this internal task cannot wake up a fully sleeping container. It serves to keep connections warm and prevent sleep *while* the application is currently active.

### Safe External Waking
To wake up the container or keep it warm externally, configure uptime monitors (e.g., UptimeRobot or cron-job.org) to ping the `/health` endpoint.
* **Probing Endpoint**: Hitting `GET /health` returns a tiny JSON `{"status": "ok"}` within 10–50ms.
* **No Overflow Failures**: This endpoint bypasses database queries, Gemini client initialization, and worker queues, preventing verbose logger traces or SSE stream creation. This guarantees that cron-job.org/UptimeRobot will **never** fail with a `"Failed (output too large)"` or timeout error.

### Frontend Passive Health Check Monitoring
To maximize perceived performance, the frontend does not block user input or perform aggressive readiness loops on page load:
1. When the page loads, the frontend is fully interactive immediately. Users can paste text or URLs and submit them without waiting.
2. In the background, the frontend queries `/api/health` passively every 30 seconds.
3. The UI displays the service status in a subtle, compact badge at the top-right of the form:
   * **`AI Service Online`** (state: `online`)
   * **`Warming Up`** (state: `warming_up`)
   * **`AI Capacity Limited`** (state: `capacity_limited`)
4. If a job is submitted while the service status is `warming_up` (cold-start), the submit button shows `"Waking AI Service..."` only *after* submission begins, preserving perceived speed.

---

## Related Guides
- [README.md](README.md) — Local development and quick start.
- [API-KEYS-AND-DEPLOYMENT.md](API-KEYS-AND-DEPLOYMENT.md) — Search configuration and API keys.
- [Working.md](Working.md) — End-to-end architecture and internals.
