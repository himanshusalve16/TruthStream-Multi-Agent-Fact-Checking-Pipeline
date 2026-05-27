# TruthStream — Microservices and Eureka Service Discovery

This document describes the online microservice architecture of TruthStream, including how
services are split, how they register with the Eureka registry, how the gateway discovers
the AI service dynamically, and how the system remains resilient on Render free tier.

---

## 1. Production Architecture Overview

```
   User Browser
        │ HTTPS
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SERVICE 1: GATEWAY & ORCHESTRATOR (Spring Boot)                            │
│  https://backend-nccx.onrender.com                                          │
│                                                                             │
│  • Exposes /api/jobs — REST + SSE endpoints                                 │
│  • Creates job records in PostgreSQL                                        │
│  • Routes job IDs to Redis queues (LPUSH)                                   │
│  • Subscribes to Redis Pub/Sub to relay SSE to browser                      │
│  • Discovers AI service URL via Eureka → FASTAPI_BASE_URL fallback          │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │ LPUSH job_id (Redis Queue)
                             ▼
                    ┌──────────────┐
                    │  Redis Queue │
                    └──────┬───────┘
                           │ BRPOP job_id
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SERVICE 2: AI EXECUTION SERVICE (FastAPI)                                  │
│  https://ai-service-w29p.onrender.com                                       │
│                                                                             │
│  • Consumes job IDs from Redis queues                                       │
│  • Runs multi-agent NLP pipeline (claims → search → judge → verdict)        │
│  • Manages Gemini quota, key rotation, cooldown, semaphores                 │
│  • Publishes progress events to Redis Pub/Sub                               │
└─────────────────────────────────────────────────────────────────────────────┘
          ↑ Redis Pub/Sub events
          └──────────────────────────── back to Gateway → SSE → Browser

                     ┌────────────────────────────────────────────┐
                     │  SERVICE 3: EUREKA REGISTRY (Spring Boot)  │
                     │  https://truthstream-eureka.onrender.com   │
                     │                                            │
                     │  • Dashboard shows live service topology   │
                     │  • Gateway registers as: TRUTHSTREAM-GATEWAY│
                     │  • AI service registers as:                │
                     │      TRUTHSTREAM-AI-SERVICE                │
                     └────────────────────────────────────────────┘
                              ↑ heartbeat        ↑ heartbeat
                          (Gateway)           (AI Service)
```

---

## 2. Service Identities in Eureka

| Service | Eureka App Name | Renders At |
|---|---|---|
| Spring Boot Gateway | `TRUTHSTREAM-GATEWAY` | `https://backend.onrender.com` |
| FastAPI AI Service | `TRUTHSTREAM-AI-SERVICE` | `https://ai-service.onrender.com` |
| Eureka Registry | N/A (is the server) | `https://truthstream-eureka.onrender.com` |

---

## 3. Eureka Dashboard

### Accessing the Dashboard

After all services are deployed:

```
https://truthstream-eureka.onrender.com
```

The dashboard shows:
- **Instances currently registered with Eureka** — both services should appear
- **Status**: UP / DOWN / OUT_OF_SERVICE
- **Last heartbeat** timestamp
- **Instance hostname** and port
- **Metadata**: service-type, version

> [!NOTE]
> On Render free tier, services sleep after ~15 minutes of inactivity. If a service
> is sleeping, it will not appear in the dashboard until it wakes up and re-registers.
> This is expected behavior — the fallback routing ensures the system still works.

---

## 4. How Services Register

### Gateway (Spring Boot)

The gateway uses Spring Cloud Netflix Eureka Client. Registration happens automatically
at startup via `@EnableDiscoveryClient` on the main application class.

Configuration in `application.yml`:
```yaml
spring:
  application:
    name: truthstream-gateway  # Eureka app name

eureka:
  client:
    enabled: ${EUREKA_CLIENT_ENABLED:true}
    service-url:
      defaultZone: ${EUREKA_CLIENT_SERVICEURL_DEFAULTZONE:http://eureka-server:8761/eureka/}
    registry-fetch-interval-seconds: 15
  instance:
    hostname: ${RENDER_EXTERNAL_HOSTNAME:${spring.application.name}}
    prefer-ip-address: false
    lease-renewal-interval-in-seconds: 30   # heartbeat every 30s
    lease-expiration-duration-in-seconds: 90 # evict after 90s without heartbeat
```

### AI Service (FastAPI)

The AI service uses `py-eureka-client`. Registration happens inside the FastAPI lifespan
startup, **after** all workers are ready (so the service is actually healthy when it registers):

```python
import py_eureka_client.eureka_client as eureka_client

await eureka_client.init_async(
    eureka_server=settings.eureka_server_url,   # EUREKA_SERVER_URL env var
    app_name="truthstream-ai-service",
    instance_port=settings.instance_port,       # INSTANCE_PORT (default 8000)
    instance_host=settings.instance_host,       # INSTANCE_HOST (Render hostname)
    renewal_interval_in_secs=30,
    duration_in_secs=90,
)
```

Deregistration happens cleanly on shutdown:
```python
eureka_client.stop()
```

---

## 5. How URL Discovery Works (Gateway → AI Service)

The `FastApiClient` in the Spring Boot gateway resolves the AI service URL on
**every request** using this priority order:

```
1. Try Eureka:
   discoveryClient.getInstances("TRUTHSTREAM-AI-SERVICE")
   → if list is non-empty → use instances[0].getUri()

2. Fallback (if Eureka unavailable or returns empty list):
   → use FASTAPI_BASE_URL env var
```

This is implemented in `FastApiClient.resolveBaseUrl()`:
```java
private String resolveBaseUrl() {
    try {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("TRUTHSTREAM-AI-SERVICE");
        if (instances != null && !instances.isEmpty()) {
            return instances.get(0).getUri().toString();
        }
    } catch (Exception e) {
        log.warn("Eureka lookup failed: {}. Using static fallback.", e.getMessage());
    }
    return fallbackBaseUrl;  // FASTAPI_BASE_URL
}
```

> [!IMPORTANT]
> The service lookup uses **uppercase** `"TRUTHSTREAM-AI-SERVICE"`. Eureka stores all
> app names in uppercase regardless of how the client registers. Using lowercase would
> return empty results on some Spring Cloud builds.

---

## 6. Render Free-Tier Resilience

Render free-tier services sleep after ~15 minutes of inactivity. This affects Eureka
registration. The architecture handles this as follows:

### Self-Preservation Disabled on Eureka Server

Standard Eureka self-preservation retains "ghost" instances when heartbeat rates drop
(designed for large-cluster network partitions). On Render, services sleep simultaneously,
so self-preservation would accumulate stale entries. It is **disabled**:

```yaml
# eureka-server/src/main/resources/application.yml
eureka:
  server:
    enable-self-preservation: false
    eviction-interval-timer-in-ms: 15000  # check for expired leases every 15s
```

### Heartbeat Tuning

Both services use 30s heartbeat / 90s expiry:
- **30s heartbeat**: standard Eureka default
- **90s expiry**: 3× the heartbeat interval (recommended ratio)
- **Result**: a sleeping service is evicted within 90s of its last heartbeat

### Gateway Fallback

When a service is evicted from Eureka (or Eureka itself is sleeping), the gateway
automatically falls back to `FASTAPI_BASE_URL`. There is **no user-visible impact**
beyond slightly higher latency during the fallback URL lookup.

### Wake-Up Flow

When a sleeping service wakes up:
1. Service boots → completes startup (DB, Redis, workers, Gemini warmup)
2. Registers with Eureka (at the end of the lifespan startup)
3. Eureka dashboard shows the instance as UP within 1–2 heartbeat cycles (~30–60s)

---

## 7. Render Deployment — Four Services

### Service 1: truthstream-eureka (NEW)

| Setting | Value |
|---|---|
| **Name** | `truthstream-eureka` |
| **Root Directory** | `eureka-server` |
| **Build Command** | *(Docker)* — handled by Dockerfile |
| **Start Command** | *(Docker)* — handled by Dockerfile |
| **Port** | Render injects `$PORT` automatically |

**Environment Variables:**

| Variable | Value |
|---|---|
| `PORT` | *(auto-injected by Render)* |

**Health Check Path:** `/actuator/health`

After deploy, visit: `https://truthstream-eureka.onrender.com`

---

### Service 2: truthstream-gateway (Spring Boot)

**Environment Variables to ADD:**

| Variable | Value |
|---|---|
| `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` | `https://truthstream-eureka.onrender.com/eureka/` |
| `EUREKA_CLIENT_ENABLED` | `true` |

> [!CAUTION]
> The URL **must include `/eureka/`** with a trailing slash.
> `https://truthstream-eureka.onrender.com` (without the suffix) causes
> `registration status: 404`. See [Troubleshooting](#9-troubleshooting-eureka-registration).

> [!NOTE]
> `RENDER_EXTERNAL_HOSTNAME` is auto-injected by Render into the gateway service.
> It is used as the instance hostname registered in Eureka. You do not need to set it manually.

All other env vars remain unchanged.

---

### Service 3: truthstream-ai-service (FastAPI)

**Environment Variables to ADD:**

| Variable | Value |
|---|---|
| `EUREKA_SERVER_URL` | `https://truthstream-eureka.onrender.com/eureka/` |
| `INSTANCE_HOST` | `ai-service-w29p.onrender.com` *(your actual Render hostname)* |
| `INSTANCE_PORT` | `10000` *(Render internal port — check your Render service config)* |

> [!IMPORTANT]
> Set `INSTANCE_HOST` to the **actual Render external hostname** of your AI service,
> not the example value above. Find it in your Render service → Settings → Public URL.
> Remove `https://` — use the hostname only (e.g., `ai-service-w29p.onrender.com`).

---

### Service 4: truthstream-frontend

No Eureka-related changes. Frontend is unchanged.

---

## 8. Local Development (Docker Compose)

```bash
docker compose up --build
```

Eureka dashboard: `http://localhost:8761`

The compose file automatically:
- Starts `eureka-server` container
- Sets `EUREKA_SERVER_URL=http://eureka-server:8761/eureka/` on `ai-service`
- Sets `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=http://eureka-server:8761/eureka/` on `backend`
- Uses `service_started` condition (not `service_healthy`) so services don't wait
  for Eureka's 30s healthcheck window before booting

---

## 9. Troubleshooting Eureka Registration

### `registration status: 404` — Root Cause

This log line means the Eureka server **is reachable** but the registration
endpoint path is wrong. The most common cause is a missing or malformed
`/eureka/` suffix in the `defaultZone` URL.

Spring Boot constructs the registration URL by concatenating:
```
{defaultZone}apps/{APP_NAME}
```

| `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` value | Registration URL sent to Eureka | HTTP Result |
|---|---|---|
| `https://...onrender.com/eureka/` ✅ | `.../eureka/apps/TRUTHSTREAM-GATEWAY` | **200 OK** |
| `https://...onrender.com/` ❌ | `.../apps/TRUTHSTREAM-GATEWAY` | **404 Not Found** |
| `https://...onrender.com` ❌ | `...onrender.comapps/...` (malformed) | **Connection Error** |
| `http://...onrender.com/eureka/` ❌ | Render redirects HTTP→HTTPS; client doesn't follow | **Connection Error** |

**The correct value:**
```
EUREKA_CLIENT_SERVICEURL_DEFAULTZONE=https://truthstream-eureka.onrender.com/eureka/
```

---

### Gateway appears in logs but missing from dashboard

1. Check that `RENDER_EXTERNAL_HOSTNAME` is visible in Render environment — Render injects it automatically; verify it in Service → Environment.
2. Look in gateway logs for: `Registering application TRUTHSTREAM-GATEWAY with eureka with status UP`
3. The Eureka dashboard auto-refreshes every 30s. Wait 60s after gateway startup.
4. If still missing: the instance may be registered with a non-routable hostname. Check `eureka.instance.hostname` in logs.

---

### HTTP vs HTTPS redirect failure

Render enforces HTTPS. If you set `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` with `http://`,
Render's CDN redirects to `https://` — but the Netflix Eureka HTTP client **does not follow
redirects**. Registration silently fails. Always use `https://` for Render URLs.

---

### AI service registers but gateway can't discover it

The gateway queries Eureka for service ID `TRUTHSTREAM-AI-SERVICE` (uppercase).
If py-eureka-client registers the AI service under a different app name, discovery
will return empty. Check that `app_name="truthstream-ai-service"` is set in `main.py`
— Eureka uppercases it automatically to `TRUTHSTREAM-AI-SERVICE`.

---

### Free-tier wake-up delay

After Render wakes a sleeping service, it takes 30–60s for:
1. The service to fully boot (DB pool, Redis, Gemini warmup, worker start)
2. The Eureka registration call to succeed
3. The gateway to pick up the new instance via registry refresh (15s interval)

During this window, the gateway uses the static `FASTAPI_BASE_URL` fallback automatically.

---

### Expected log lines — successful state

**Eureka Server (truthstream-eureka):**
```
Registered instance TRUTHSTREAM-AI-SERVICE/ai-service-w29p.onrender.com with status UP
Registered instance TRUTHSTREAM-GATEWAY/backend-nccx.onrender.com with status UP
```

**Gateway (truthstream-gateway):**
```
Registering application TRUTHSTREAM-GATEWAY with eureka with status UP
Sending heartbeat to eureka for app: TRUTHSTREAM-GATEWAY
Got http response code 200 for request on url
AI service URL resolved via Eureka: https://ai-service-w29p.onrender.com
```

**AI Service (truthstream-ai-service):**
```
[EUREKA] Registered as truthstream-ai-service on https://truthstream-eureka.onrender.com/eureka/ (host=ai-service-w29p.onrender.com, port=10000)
```

**When fallback is active (Eureka sleeping):**
```
Eureka returned no instances for TRUTHSTREAM-AI-SERVICE. Using static fallback URL.
```
This is expected and non-fatal — jobs still dispatch via `FASTAPI_BASE_URL`.

---

## 10. Shared Infrastructure (Unchanged)

- **Redis Queues**: `job_queue_fast`, `job_queue_slow` — Gateway LPUSH, AI Service BRPOP
- **Redis Pub/Sub**: `job:{id}:events` — AI Service publishes, Gateway subscribes → SSE
- **Redis Cancellation**: `job:cancel:events` — Gateway publishes, AI Service subscribes
- **PostgreSQL**: Shared database for job state, claims, verdicts, embeddings
