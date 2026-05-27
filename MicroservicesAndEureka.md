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
   discoveryClient.getInstances("truthstream-ai-service")
   → if list is non-empty → use instances[0].getUri()

2. Fallback (if Eureka unavailable or returns empty list):
   → use FASTAPI_BASE_URL env var
```

This is implemented in `FastApiClient.resolveBaseUrl()`:
```java
private String resolveBaseUrl() {
    try {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("truthstream-ai-service");
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
> The fallback URL (`FASTAPI_BASE_URL`) is **always set** in production. This guarantees
> the system works even when the Eureka service is sleeping or not yet deployed.

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

### Services not showing in Eureka dashboard

1. Check Eureka server logs: `docker compose logs eureka-server`
2. Verify the service has booted: `docker compose logs ai-service | grep EUREKA`
3. Wait 30–90s after boot — registration + first heartbeat cycle takes time
4. Check network: all services must be on the same Docker network (`internal`)

### Gateway not discovering AI service via Eureka

1. Look for the log line: `AI service URL resolved via Eureka: ...`
2. If you see: `Eureka returned no instances` → AI service hasn't registered yet
3. The fallback URL is always used in this case — check `FASTAPI_BASE_URL`

### Render: service shows as DOWN in dashboard

1. Ensure `INSTANCE_HOST` is the correct Render external hostname (not localhost)
2. Ensure `INSTANCE_PORT` matches Render's internal port (usually `10000`)
3. Check that the Eureka server is awake and not sleeping

### Connection timeout on free tier

Render free services can take 30–60s to wake up. The gateway fallback routing ensures
job dispatch still works while services wake. The Eureka dashboard may show the instance
as DOWN or absent until the heartbeat resumes.

---

## 10. Shared Infrastructure (Unchanged)

- **Redis Queues**: `job_queue_fast`, `job_queue_slow` — Gateway LPUSH, AI Service BRPOP
- **Redis Pub/Sub**: `job:{id}:events` — AI Service publishes, Gateway subscribes → SSE
- **Redis Cancellation**: `job:cancel:events` — Gateway publishes, AI Service subscribes
- **PostgreSQL**: Shared database for job state, claims, verdicts, embeddings
