# TruthStream — Railway & Render Deployment Guide

This guide details how to deploy TruthStream's multi-service architecture to cloud application platforms like **Railway** or **Render**, using Vercel for static frontend hosting.

---

## Service Deployment Matrix

The monorepo contains services that should be deployed as follows:

| Service | Build Target | Recommended Platform | Configurations |
|---|---|---|---|
| **Frontend** | Static build (`/frontend`) | [Vercel](https://vercel.com) | Point to the Backend public URL |
| **Backend** | Dockerfile (`/backend`) | [Railway](https://railway.app) / [Render](https://render.com) | Expose Spring Boot port (`8080`) |
| **AI Service** | Dockerfile (`/ai-service`) | Railway / Render | Private or Web Service on Port `8000` |
| **PostgreSQL** | Managed Database | Railway / Render | Require extensions (`vector`, `uuid-ossp`, `pgcrypto`) |
| **Redis** | Managed Cache | Railway / Render | Used for workers and pub/sub relay |

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
| `DATABASE_URL` | `postgresql://user:pass@host:port/db` | Standard Postgres connection URI |
| `REDIS_URL` | `redis://host:port` | Redis connection URI |
| `GEMINI_API_KEY` | `your-gemini-key` | Google GenAI API key. Supports `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, etc., for key rotation |
| `INTERNAL_API_SECRET` | `your-shared-secret` | Shared secret key with Spring Boot |
| `SERPAPI_KEY` | `your-serpapi-key` | Optional. If omitted, searches default to DuckDuckGo scraping |

*FastAPI exposes port `8000` for internal requests.*

---

## 3. Deploying the Backend (Spring Boot Gateway)

Deploy the `backend` folder as a Docker service. Flyway migrations will run automatically on startup to initialize the application tables (`users`, `articles`, `jobs`, `claims`, `sources`, `verdicts`, `bias_results`, `audit_log`).

### Environment Variables for Spring Boot

| Variable | Value | Description |
|---|---|---|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://host:port/db` | JDBC Postgres connection string |
| `SPRING_DATASOURCE_USERNAME` | `your-db-user` | DB username |
| `SPRING_DATASOURCE_PASSWORD` | `your-db-password` | DB password |
| `SPRING_DATA_REDIS_HOST` | `your-redis-host` | Redis host |
| `SPRING_DATA_REDIS_PORT` | `6379` | Redis port |
| `FASTAPI_BASE_URL` | `https://your-ai-service-url` | Public or internal URL of the FastAPI container |
| `INTERNAL_API_SECRET` | `your-shared-secret` | Shared secret matching the FastAPI configuration |

*Spring Boot exposes port `8080` for API requests.*

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

## 5. Verifying the Deployment

Run a smoke test to confirm that services are communicating correctly:
1. Register a new user account through the frontend UI.
2. Submit a short text snippet (e.g., "The unemployment rate dropped to 3.4% in 2024"). This runs standard analysis and verifies the database, Redis queue, and Gemini API connections.
3. Verify that SSE events display in the UI and that the final confidence gauge and verdict render on completion.

---

## Related Guides
- [README.md](README.md) — Local development and quick start.
- [API-KEYS-AND-DEPLOYMENT.md](API-KEYS-AND-DEPLOYMENT.md) — Search configuration and API keys.
- [Working.md](Working.md) — End-to-end architecture and internals.
