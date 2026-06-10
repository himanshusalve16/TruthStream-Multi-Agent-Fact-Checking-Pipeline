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
| **PostgreSQL** | Managed Database | Render / Railway | Requires `vector`, `uuid-ossp`, `pgcrypto` |
| **Redis** | Managed Cache | Render / Railway | Pub/Sub + queue |

> [!IMPORTANT]
> **Deploy order**: PostgreSQL + Redis → AI Service → Gateway → Frontend
> Build and deploy the database and cache instances first so the AI service and Gateway can establish connection pools at startup.

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
| `FASTAPI_BASE_URL` | `https://ai-service-w29p.onrender.com` | The direct URL of the deployed FastAPI AI Service (used for service-to-service communication) |
| `INTERNAL_API_SECRET` | random hex string | Shared secret matching ai-service |
| `JWT_SECRET` | 64-char hex string | JWT signing secret |
| `JWT_EXPIRY_MS` | `3600000` | JWT token validity (ms) |

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

## Related Guides
- [README.md](README.md) — Local development and quick start.
- [API-KEYS-AND-DEPLOYMENT.md](API-KEYS-AND-DEPLOYMENT.md) — Search configuration and API keys.
- [Working.md](Working.md) — End-to-end system internals & engineering handbook.

