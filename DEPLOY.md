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
| `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` | `https://truthstream-eureka.onrender.com/eureka/` | Eureka registry URL — **must include `/eureka/` suffix** |
| `EUREKA_CLIENT_ENABLED` | `true` | Enable Eureka client registration |
| `RENDER_EXTERNAL_HOSTNAME` | `backend-nccx.onrender.com` | *(auto-injected by Render)* Instance hostname for Eureka |

> [!CAUTION]
> `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` **must end with `/eureka/`** (including the trailing slash).
> Using `https://truthstream-eureka.onrender.com` (without `/eureka/`) causes Spring Boot
> to send registration to `/apps/TRUTHSTREAM-GATEWAY` instead of `/eureka/apps/TRUTHSTREAM-GATEWAY`,
> which returns **HTTP 404** and the log line `registration status: 404`.

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

## 7. Eureka Registration Troubleshooting

### `registration status: 404`

This is the most common Eureka registration failure. It means the Eureka server
**is reachable** but the registration endpoint path is wrong.

**Root cause**: `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` is missing the `/eureka/` suffix.

Spring Boot constructs the registration URL as:
```
{defaultZone}apps/{APP_NAME}
```

| defaultZone value | Registration URL sent | Result |
|---|---|---|
| `https://...onrender.com/eureka/` ✅ | `https://...onrender.com/eureka/apps/TRUTHSTREAM-GATEWAY` | **200 OK** |
| `https://...onrender.com/` ❌ | `https://...onrender.com/apps/TRUTHSTREAM-GATEWAY` | **404** |
| `https://...onrender.com` ❌ | `https://...onrender.comapps/TRUTHSTREAM-GATEWAY` | **connection error** |

**Fix**: Ensure the env var is set to exactly:
```
EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=https://truthstream-eureka.onrender.com/eureka/
```
(with `/eureka/` path segment and trailing slash)

---

### Gateway appears in logs but not in dashboard

1. Check `RENDER_EXTERNAL_HOSTNAME` is set on the gateway service — Render injects this automatically, verify it appears in the service's environment.
2. Check `eureka.instance.hostname` in logs: look for `Registering application TRUTHSTREAM-GATEWAY with eureka with status UP`.
3. The dashboard auto-refreshes every 30s. Wait at least 60s after startup.

---

### `HTTPS vs HTTP` redirect causing registration failure

Render services redirect HTTP to HTTPS. The Spring Boot Eureka client does **not**
follow HTTP → HTTPS redirects during registration. Always use `https://` in
`EUREKA_CLIENT_SERVICEURL_DEFAULTZONE`.

---

### Expected successful registration log lines

When registration succeeds, look for these in the gateway logs:
```
Registering application TRUTHSTREAM-GATEWAY with eureka with status UP
Sending heartbeat to eureka for app: TRUTHSTREAM-GATEWAY
Got http response code 200 for request...
```

When discovery works, look for:
```
AI service URL resolved via Eureka: https://ai-service-w29p.onrender.com
```

When fallback is active:
```
Eureka returned no instances for TRUTHSTREAM-AI-SERVICE. Using static fallback URL.
```

---

## Related Guides
- [README.md](README.md) — Local development and quick start.
- [MicroservicesAndEureka.md](MicroservicesAndEureka.md) — Eureka architecture and online dashboard.
- [API-KEYS-AND-DEPLOYMENT.md](API-KEYS-AND-DEPLOYMENT.md) — Search configuration and API keys.
- [Working.md](Working.md) — End-to-end architecture and internals.
