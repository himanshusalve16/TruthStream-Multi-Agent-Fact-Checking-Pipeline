# TruthStream — Windows Setup & Implementation Roadmap

---

## Windows Setup Strategy

Every command in this document is written for **PowerShell 7** on Windows. Do not use Command Prompt (cmd.exe) — it is missing modern features you will need. Do not use the old Windows PowerShell 5 that ships with Windows. Install PowerShell 7 in Phase 1.

The setup follows a strict dependency-first order:
1. Install tools globally on your machine (once)
2. Configure PowerShell for development
3. Create the monorepo folder skeleton
4. Stand up infrastructure (Postgres + pgvector + Redis) via Docker Compose
5. Bootstrap each service with its minimal working state
6. Wire them together and verify each connection point
7. Confirm the whole system talks end-to-end before writing a single feature

**Monorepo:** Use a single repo (`truthstream\`). One repo = one `docker-compose.yml`, one `.env`, one `git clone`. Do not split into multiple repos.

**Your terminal for everything:** Windows Terminal + PowerShell 7. Install both in Phase 1.

---

## Phase 0 — Windows Prerequisites (Before Anything Else)

### 0.1 Check Your Windows Version

Open the old PowerShell (press `Win + R`, type `powershell`, press Enter):

```powershell
winver
```

You need **Windows 10 version 2004 or later**, or **Windows 11**. If you see a build number below 19041, update Windows before continuing.

### 0.2 Enable Developer Mode

Start Menu → Settings → Privacy & Security → For Developers → Turn on **Developer Mode**.

This allows symlinks and longer file paths, which Maven and Node.js need.

### 0.3 Enable Long Path Support

Run old PowerShell **as Administrator** (right-click → Run as administrator):

```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Restart your computer after this step.

---

## Phase 1 — Tool Installation

Install in this exact order. Use **winget** (built into Windows 10/11) for everything. Open old PowerShell as Administrator for installs.

### 1.1 Install Windows Terminal

```powershell
winget install --id Microsoft.WindowsTerminal -e --accept-source-agreements --accept-package-agreements
```

After install, open Windows Terminal from the Start Menu. **Use Windows Terminal for all remaining steps in this guide.**

### 1.2 Install PowerShell 7

Inside Windows Terminal:

```powershell
winget install --id Microsoft.PowerShell -e --accept-source-agreements --accept-package-agreements
```

After install, close Windows Terminal completely. Reopen it. In the title bar dropdown (the `˅` arrow), select **PowerShell** — make sure it says "PowerShell 7.x.x" in the prompt, not "Windows PowerShell".

Set PowerShell 7 as the default in Windows Terminal:
- Click the `˅` dropdown → Settings → Startup → Default profile → select **PowerShell** (the one with the black icon, not the blue one)

**Verify you are in PowerShell 7:**
```powershell
$PSVersionTable.PSVersion
# Major must be 7
```

### 1.3 Set PowerShell Execution Policy

PowerShell blocks scripts by default. Fix this now — you need it for virtual environment activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# Type Y and press Enter when prompted
```

### 1.4 Install Git

```powershell
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
```

Close and reopen Windows Terminal (this refreshes the PATH).

```powershell
git --version
# Expected: git version 2.x.x
```

Configure Git:
```powershell
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
git config --global core.autocrlf false
```

> `core.autocrlf false` is critical. Without it, Git converts line endings to Windows CRLF, which breaks shell scripts inside Docker containers.

### 1.5 Install Java 21

```powershell
winget install --id Microsoft.OpenJDK.21 -e --accept-source-agreements --accept-package-agreements
```

Close and reopen Windows Terminal.

```powershell
java -version
# Expected: openjdk version "21.x.x"
```

If `java` is not found after reopening, set `JAVA_HOME` manually:
```powershell
# Find where Java was installed
Get-ChildItem "C:\Program Files\Microsoft" | Where-Object { $_.Name -like "*jdk*21*" }

# Set JAVA_HOME permanently for your user (replace the path with what you found above)
[System.Environment]::SetEnvironmentVariable("JAVA_HOME", "C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot", "User")
[System.Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\Microsoft\jdk-21.0.x.x-hotspot\bin", "User")
```

Close and reopen Windows Terminal, then run `java -version` again.

### 1.6 Install Maven

```powershell
winget install --id Apache.Maven -e --accept-source-agreements --accept-package-agreements
```

Close and reopen Windows Terminal.

```powershell
mvn -version
# Expected: Apache Maven 3.x.x
```

If not found, Maven needs to be on PATH. Download manually as a fallback:
1. Go to https://maven.apache.org/download.cgi
2. Download the Binary zip archive (`apache-maven-3.x.x-bin.zip`)
3. Extract to `C:\tools\maven\`
4. Add to PATH permanently:
```powershell
[System.Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\tools\maven\bin", "User")
```

### 1.7 Install Node.js 20 LTS

```powershell
winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
```

Close and reopen Windows Terminal.

```powershell
node -v   # Expected: v20.x.x
npm -v    # Expected: 10.x.x
```

### 1.8 Install Python 3.11

```powershell
winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements
```

Close and reopen Windows Terminal.

```powershell
python --version
# Expected: Python 3.11.x
```

> **Important:** The winget Python installer adds Python to PATH automatically. If `python` is not found, open the Start Menu, search "Manage app execution aliases", and turn OFF the "python.exe" and "python3.exe" aliases that Windows sets by default — these override the real Python install.

### 1.9 Install Docker Desktop

Docker requires WSL2 (Windows Subsystem for Linux) as its backend. This is built into Windows 10/11 — you do not need to install a separate Linux distro.

**Step 1:** Enable WSL2. Run PowerShell **as Administrator**:
```powershell
wsl --install --no-distribution
```

Restart your computer when prompted.

**Step 2:** After restart, download Docker Desktop:
Go to https://www.docker.com/products/docker-desktop/ → Download for Windows

Run the installer. During installation:
- Check "Use WSL 2 instead of Hyper-V" (should be pre-checked)
- Check "Add shortcut to desktop"

**Step 3:** Launch Docker Desktop from the Start Menu. Wait for the whale icon in the taskbar notification area to stop animating (this means Docker is ready — takes 60–90 seconds the first time).

**Step 4:** Verify in Windows Terminal:
```powershell
docker --version
# Expected: Docker version 25.x.x

docker compose version
# Expected: Docker Compose version v2.x.x

docker run hello-world
# Expected: "Hello from Docker!" message
```

> If `docker` is not found, add Docker to PATH: Settings → Docker Desktop → Resources → WSL Integration, or add `C:\Program Files\Docker\Docker\resources\bin` to your user PATH.

### 1.10 Install Postman

```powershell
winget install --id Postman.Postman -e --accept-source-agreements --accept-package-agreements
```

Or download from https://www.postman.com/downloads/. No CLI setup needed yet.

### 1.11 Install IDEs

```powershell
# IntelliJ IDEA Community (for Spring Boot)
winget install --id JetBrains.IntelliJIDEA.Community -e --accept-source-agreements --accept-package-agreements

# VS Code (for FastAPI + React)
winget install --id Microsoft.VisualStudioCode -e --accept-source-agreements --accept-package-agreements
```

After VS Code opens, install these extensions (press `Ctrl+Shift+X` and search each name):
- `ms-python.python` — Python
- `vscjava.vscode-java-pack` — Extension Pack for Java
- `dsznajder.es7-react-js-snippets` — ES7+ React snippets
- `ms-azuretools.vscode-docker` — Docker
- `humao.rest-client` — REST Client (for SSE testing without Postman)

### 1.12 Verify All Tools

Run this block to confirm everything is installed:

```powershell
Write-Host "=== TruthStream Tool Check ===" -ForegroundColor Cyan
Write-Host "Git:    $(git --version)"
Write-Host "Java:   $(java -version 2>&1 | Select-Object -First 1)"
Write-Host "Maven:  $(mvn -version 2>&1 | Select-Object -First 1)"
Write-Host "Node:   $(node -v)"
Write-Host "npm:    $(npm -v)"
Write-Host "Python: $(python --version)"
Write-Host "Docker: $(docker --version)"
Write-Host "Compose:$(docker compose version)"
```

All lines must print a version number. Fix any missing tool before continuing.

---

## Phase 2 — PowerShell Helper Script for .env Loading

On macOS/Linux, `.env` files are loaded with `export $(grep ...)`. PowerShell does not support this syntax. You will use a helper script instead.

Create this file once. You will use it every time you start a service locally.

In `C:\Users\YourName\Documents\` (or wherever you keep scripts), but we will put it inside the project. You will create it in Phase 3 after the project folder exists.

---

## Phase 3 — Create the Monorepo

Open Windows Terminal (PowerShell 7). Navigate to where you keep your projects (e.g., `C:\Users\YourName\Projects\`):

```powershell
# Navigate to your projects folder — change this path to match yours
cd C:\Users\$env:USERNAME\Documents
# OR if you have a Projects folder:
# cd C:\Users\$env:USERNAME\Projects

# Create the monorepo
mkdir truthstream
cd truthstream
git init

# Create all directories
mkdir frontend, backend, ai-service, infra
mkdir infra\postgres

# Create files — New-Item is the PowerShell equivalent of touch
New-Item .gitignore -ItemType File
New-Item .env.example -ItemType File
New-Item .env -ItemType File
New-Item docker-compose.yml -ItemType File

# Write .gitignore
@"
node_modules/
.env
*.class
__pycache__/
.venv/
target/
.DS_Store
*.pyc
.idea/
.vscode/settings.json
"@ | Set-Content .gitignore

# Create the load-env helper script (Windows replacement for export $(...))
New-Item load-env.ps1 -ItemType File
```

Write the `load-env.ps1` helper script. This is your most important Windows-specific tool:

```powershell
# Paste this content into load-env.ps1
@'
# load-env.ps1
# Usage: . .\load-env.ps1
# The dot-space prefix (. .\) is required to load vars into current session
param([string]$EnvFile = ".env")

if (-not (Test-Path $EnvFile)) {
    Write-Error "No .env file found at $EnvFile"
    return
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    # Skip comments and empty lines
    if ($line -match "^\s*#" -or $line -eq "") { return }
    # Parse KEY=VALUE
    if ($line -match "^([^=]+)=(.*)$") {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        Write-Host "  Loaded: $key" -ForegroundColor DarkGray
    }
}
Write-Host "Environment loaded from $EnvFile" -ForegroundColor Green
'@ | Set-Content load-env.ps1
```

**How to use `load-env.ps1`:** The `. .\` (dot space dot-backslash) prefix is mandatory. Without the leading dot, environment variables only exist in a child process and disappear immediately.

```powershell
# Correct usage — notice the ". " at the start
. .\load-env.ps1

# If your .env is one level up (e.g., from inside the backend folder):
. ..\load-env.ps1 -EnvFile ..\.env
```

Initial commit:
```powershell
git add .gitignore .env.example load-env.ps1
git commit -m "chore: initial monorepo scaffold"
```

---

## Phase 4 — Folder Structure

This is the complete target structure. You will build it incrementally:

```
truthstream\
├── .env                          ← Real secrets — never committed
├── .env.example                  ← Template — committed
├── .gitignore
├── docker-compose.yml
├── load-env.ps1                  ← Windows env loader helper
│
├── infra\
│   └── postgres\
│       └── init.sql
│
├── frontend\                     ← React (Vite + TypeScript)
│   ├── public\
│   ├── src\
│   │   ├── api\
│   │   │   └── client.ts
│   │   ├── components\
│   │   │   ├── ClaimCard.tsx
│   │   │   ├── ClaimList.tsx
│   │   │   ├── SourceCard.tsx
│   │   │   ├── BiasPanel.tsx
│   │   │   ├── ConfidenceGauge.tsx
│   │   │   ├── VerdictBanner.tsx
│   │   │   ├── VerdictTimeline.tsx
│   │   │   ├── InputForm.tsx
│   │   │   ├── LoadingState.tsx
│   │   │   └── ErrorBanner.tsx
│   │   ├── context\
│   │   │   └── JobContext.tsx
│   │   ├── hooks\
│   │   │   └── useJobStream.ts
│   │   ├── pages\
│   │   │   ├── LandingPage.tsx
│   │   │   ├── JobPage.tsx
│   │   │   ├── HistoryPage.tsx
│   │   │   ├── LoginPage.tsx
│   │   │   └── RegisterPage.tsx
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── backend\                      ← Spring Boot (Maven)
│   ├── src\main\java\com\truthstream\
│   │   ├── TruthStreamApplication.java
│   │   ├── config\
│   │   ├── controller\
│   │   ├── service\
│   │   ├── repository\
│   │   ├── model\
│   │   ├── dto\
│   │   └── security\
│   ├── src\main\resources\
│   │   ├── application.yml
│   │   └── db\migration\
│   │       └── V1__init_schema.sql
│   └── pom.xml
│
└── ai-service\                   ← Python FastAPI
    ├── main.py
    ├── config.py
    ├── requirements.txt
    ├── Dockerfile
    ├── routers\
    ├── agents\
    ├── services\
    ├── db\
    ├── models\
    ├── utils\
    └── tests\
```

---

## Phase 5 — Environment Variables

### 5.1 `.env.example` (commit this file)

```powershell
# Paste this into .env.example
@"
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=truthstream
DB_USER=postgres
DB_PASSWORD=changeme

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Spring Boot
SPRING_PORT=8080

# FastAPI
FASTAPI_PORT=8000
FASTAPI_BASE_URL=http://localhost:8000

# AI / External APIs
GEMINI_API_KEY=sk-replace-me
SERPAPI_KEY=replace-me
BRAVE_API_KEY=replace-me

# Internal auth (Spring Boot calls FastAPI with this header)
INTERNAL_API_SECRET=replace-with-random-32-char-string
"@ | Set-Content .env.example
```

### 5.2 `.env` (never commit — fill in real values)

Copy the example to `.env`:
```powershell
Copy-Item .env.example .env
```

**Generate the internal API secret:**
```powershell
$bytes = New-Object byte[] 16
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = [System.BitConverter]::ToString($bytes) -replace '-', ''
Write-Host "INTERNAL_API_SECRET=$secret"
```

Open `.env` in VS Code and fill in the values:
```powershell
code .env
```

Fill in:
- `INTERNAL_API_SECRET` — paste the 32-char hex you generated
- `DB_PASSWORD` — any strong password (e.g., `TruthStream2024!`)
- `GEMINI_API_KEY` — from https://aistudio.google.com/app/apikey
- `SERPAPI_KEY` — from https://serpapi.com (100 free searches/month)
- `BRAVE_API_KEY` — from https://api.search.brave.com (2000 free queries/month)

---

## Phase 6 — Docker Compose Setup

### 6.1 `docker-compose.yml`

Open `docker-compose.yml` in VS Code (`code docker-compose.yml`) and paste:

```yaml
version: "3.9"

services:
  db:
    image: pgvector/pgvector:pg16
    container_name: truthstream-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    ports:
      - "${DB_PORT}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7.2-alpine
    container_name: truthstream-redis
    restart: unless-stopped
    ports:
      - "${REDIS_PORT}:6379"
    command: redis-server --save "" --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  ai-service:
    build:
      context: ./ai-service
      dockerfile: Dockerfile
    container_name: truthstream-ai
    restart: unless-stopped
    ports:
      - "${FASTAPI_PORT}:8000"
    environment:
      DATABASE_URL: postgresql://${DB_USER}:${DB_PASSWORD}@db:${DB_PORT}/${DB_NAME}
      REDIS_URL: redis://redis:6379
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      SERPAPI_KEY: ${SERPAPI_KEY}
      BRAVE_API_KEY: ${BRAVE_API_KEY}
      INTERNAL_API_SECRET: ${INTERNAL_API_SECRET}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: truthstream-backend
    restart: unless-stopped
    ports:
      - "${SPRING_PORT}:8080"
    environment:
      SPRING_DATASOURCE_URL: jdbc:postgresql://db:5432/${DB_NAME}
      SPRING_DATASOURCE_USERNAME: ${DB_USER}
      SPRING_DATASOURCE_PASSWORD: ${DB_PASSWORD}
      SPRING_DATA_REDIS_HOST: redis
      SPRING_DATA_REDIS_PORT: 6379
      FASTAPI_BASE_URL: http://ai-service:8000
      INTERNAL_API_SECRET: ${INTERNAL_API_SECRET}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      ai-service:
        condition: service_started

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: truthstream-frontend
    restart: unless-stopped
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  pgdata:
```

> **Development workflow:** During daily coding, run ONLY `db` and `redis` in Docker. Run backend, ai-service, and frontend natively with hot-reload. Full Docker Compose is for integration testing only.

---

## Phase 7 — Database Initialization

### 7.1 `infra\postgres\init.sql`

```powershell
code infra\postgres\init.sql
```

Paste this content:

```sql
-- Enable required PostgreSQL extensions
-- This file runs automatically on first container start
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Verify extensions loaded
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    RAISE EXCEPTION 'pgvector extension failed to load';
  END IF;
END $$;
```

### 7.2 Start the Database

```powershell
# From the truthstream\ root directory
# Load .env variables first
. .\load-env.ps1

# Start only db and redis
docker compose up db redis -d

# Watch for healthy status — wait about 15 seconds
docker compose ps
```

Both services should show `healthy` in the STATUS column. If they show `starting`, wait 10 more seconds and run `docker compose ps` again.

### 7.3 Verify the Database

```powershell
docker exec -it truthstream-db psql -U postgres -d truthstream
```

Inside the psql prompt:
```sql
-- List extensions
\dx

-- Expected output includes:
-- vector    | ...
-- uuid-ossp | ...
-- pgcrypto  | ...

\q
```

### 7.4 Flyway Migration File

The full schema is managed by Flyway inside Spring Boot. Create the migration file:

```powershell
# Create the migration directory and file
mkdir -p backend\src\main\resources\db\migration
code backend\src\main\resources\db\migration\V1__init_schema.sql
```

Paste this content into the file:

```sql
CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE articles (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url          TEXT,
  url_hash     TEXT,
  raw_text     TEXT NOT NULL,
  cleaned_text TEXT,
  truncated    BOOLEAN NOT NULL DEFAULT FALSE,
  word_count   INTEGER,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_articles_url_hash ON articles(url_hash) WHERE url_hash IS NOT NULL;

CREATE TABLE jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  article_id    UUID REFERENCES articles(id),
  status        TEXT NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING','PROCESSING','COMPLETE','FAILED','PARTIAL')),
  input_url     TEXT,
  input_text    TEXT,
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status  ON jobs(status);

CREATE TABLE claims (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  article_id    UUID NOT NULL REFERENCES articles(id),
  text          TEXT NOT NULL,
  context_quote TEXT,
  claim_type    TEXT,
  checkability  TEXT,
  embedding     VECTOR(768),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claims_job_id ON claims(job_id);
CREATE INDEX idx_claims_embedding ON claims
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE sources (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id      UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  url           TEXT NOT NULL,
  title         TEXT,
  domain        TEXT,
  snippet       TEXT,
  full_text     TEXT,
  stance        TEXT CHECK (stance IN ('SUPPORTS','REFUTES','NEUTRAL','UNCLEAR')),
  quality_score NUMERIC(4,3),
  fetch_status  TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sources_claim_id ON sources(claim_id);

CREATE TABLE verdicts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id      UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  claim_id    UUID REFERENCES claims(id),
  verdict     TEXT NOT NULL,
  confidence  NUMERIC(4,3),
  reasoning   TEXT,
  is_overall  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_verdicts_job_id ON verdicts(job_id);

CREATE TABLE bias_results (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id         UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  article_id     UUID NOT NULL REFERENCES articles(id),
  bias_score     INTEGER,
  bias_direction TEXT,
  framing_flags  JSONB,
  loaded_terms   TEXT[],
  summary        TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_log (
  id          BIGSERIAL PRIMARY KEY,
  job_id      UUID REFERENCES jobs(id),
  user_id     UUID REFERENCES users(id),
  event_type  TEXT NOT NULL,
  payload     JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_log_job_id     ON audit_log(job_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
```

---

## Phase 8 — Spring Boot Bootstrap

### 8.1 Generate the Project

1. Open https://start.spring.io in your browser
2. Configure:

| Field | Value |
|---|---|
| Project | Maven |
| Language | Java |
| Spring Boot | 3.2.x (latest 3.2) |
| Group | com.truthstream |
| Artifact | backend |
| Name | backend |
| Packaging | Jar |
| Java | 21 |

3. Click **ADD DEPENDENCIES** and add:
   - Spring Web
   - Spring Security
   - Spring Data JPA
   - Spring Data Redis (Access+Driver)
   - Flyway Migration
   - PostgreSQL Driver
   - Lombok
   - Validation
   - Spring Boot Actuator

4. Click **GENERATE** — downloads `backend.zip`
5. Extract the zip. Copy its contents into `truthstream\backend\` (replace the empty folder).

### 8.2 Add JWT Dependencies to `pom.xml`

Open `backend\pom.xml` in VS Code. Find the `<dependencies>` block and add these entries before the closing `</dependencies>` tag:

```xml
<!-- JWT -->
<dependency>
  <groupId>io.jsonwebtoken</groupId>
  <artifactId>jjwt-api</artifactId>
  <version>0.12.3</version>
</dependency>
<dependency>
  <groupId>io.jsonwebtoken</groupId>
  <artifactId>jjwt-impl</artifactId>
  <version>0.12.3</version>
  <scope>runtime</scope>
</dependency>
<dependency>
  <groupId>io.jsonwebtoken</groupId>
  <artifactId>jjwt-jackson</artifactId>
  <version>0.12.3</version>
  <scope>runtime</scope>
</dependency>

<!-- WebClient for calling FastAPI -->
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

### 8.3 `application.yml`

Delete `backend\src\main\resources\application.properties`. Create `application.yml` in the same folder:

```powershell
Remove-Item backend\src\main\resources\application.properties
code backend\src\main\resources\application.yml
```

Paste:

```yaml
spring:
  application:
    name: truthstream-backend

  datasource:
    url: ${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/truthstream}
    username: ${SPRING_DATASOURCE_USERNAME:postgres}
    password: ${SPRING_DATASOURCE_PASSWORD:changeme}
    driver-class-name: org.postgresql.Driver

  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: false
    properties:
      hibernate:
        dialect: org.hibernate.dialect.PostgreSQLDialect

  flyway:
    enabled: true
    locations: classpath:db/migration
    baseline-on-migrate: true

  data:
    redis:
      host: ${SPRING_DATA_REDIS_HOST:localhost}
      port: ${SPRING_DATA_REDIS_PORT:6379}

  mvc:
    async:
      request-timeout: 300000

server:
  port: ${SPRING_PORT:8080}

app:
  jwt:
    secret: ${JWT_SECRET}
    expiry-ms: ${JWT_EXPIRY_MS:3600000}
  fastapi:
    base-url: ${FASTAPI_BASE_URL:http://localhost:8000}
  internal:
    api-secret: ${INTERNAL_API_SECRET}

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: always

logging:
  level:
    com.truthstream: DEBUG
    org.springframework.security: INFO
```

### 8.4 Spring Boot Dockerfile

Create `backend\Dockerfile`:

```powershell
code backend\Dockerfile
```

```dockerfile
FROM eclipse-temurin:21-jdk-alpine AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
RUN ./mvnw package -DskipTests --no-transfer-progress

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
```

### 8.5 Run Spring Boot Locally on Windows

```powershell
# Open a NEW terminal tab (Ctrl+Shift+T in Windows Terminal)
# Navigate to project root
cd C:\Users\$env:USERNAME\Documents\truthstream

# Load environment variables
. .\load-env.ps1

# Move into backend folder
cd backend

# Run Spring Boot using the Windows Maven wrapper (mvnw.cmd — NOT ./mvnw)
.\mvnw.cmd spring-boot:run
```

> **Windows-specific:** On macOS/Linux the command is `./mvnw`. On Windows it is `.\mvnw.cmd`. The `.cmd` extension is required. If you see "Permission denied" errors, you are accidentally using the wrong wrapper.

Expected output in the last lines:
```
Started TruthStreamApplication in 3.x seconds (process running for 4.x)
```

Verify Spring Boot is running:
```powershell
# Open another terminal tab
Invoke-WebRequest -Uri http://localhost:8080/actuator/health | Select-Object -ExpandProperty Content
# Expected: {"status":"UP",...}
```

---

## Phase 9 — FastAPI Bootstrap

### 9.1 Create Virtual Environment

```powershell
# Open a new terminal tab
cd C:\Users\$env:USERNAME\Documents\truthstream\ai-service

# Create virtual environment
python -m venv .venv

# Activate it (Windows uses Scripts\Activate.ps1, NOT bin/activate)
.\.venv\Scripts\Activate.ps1

# Your prompt should now show (.venv) at the start
# Expected: (.venv) PS C:\...\ai-service>
```

If you see a red error about execution policy:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
# Then try activating again
.\.venv\Scripts\Activate.ps1
```

### 9.2 `requirements.txt`

```powershell
code requirements.txt
```

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.1
pydantic-settings==2.2.1
asyncpg==0.29.0
redis[asyncio]==5.0.4
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.2.1
openai==1.30.1
pgvector==0.3.2
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
respx==0.21.1
```

Install:
```powershell
# Make sure .venv is still activated (you see (.venv) in the prompt)
pip install -r requirements.txt
```

This will take 1–2 minutes. You will see progress bars for each package.

### 9.3 `config.py`

```powershell
code config.py
```

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    openai_api_key: str
    serpapi_key: str
    brave_api_key: str
    internal_api_secret: str

    class Config:
        env_file = "../.env"
        env_file_encoding = "utf-8"

settings = Settings()
```

### 9.4 Create Package `__init__.py` Files

Python requires `__init__.py` files to treat folders as packages:

```powershell
# From ai-service\
mkdir routers, agents, services, db, models, utils, tests
mkdir tests\fixtures, tests\mocks

# Create __init__.py in each package folder
"" | Set-Content routers\__init__.py
"" | Set-Content agents\__init__.py
"" | Set-Content services\__init__.py
"" | Set-Content db\__init__.py
"" | Set-Content models\__init__.py
"" | Set-Content utils\__init__.py
"" | Set-Content tests\__init__.py
```

### 9.5 `db\connection.py`

```powershell
code db\connection.py
```

```python
import asyncpg

async def init_db_pool(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn=database_url,
        min_size=2,
        max_size=10,
        command_timeout=30
    )

async def close_db_pool(pool: asyncpg.Pool):
    await pool.close()
```

### 9.6 `routers\internal.py`

```powershell
code routers\internal.py
```

```python
from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel
from config import settings

router = APIRouter()

class JobDispatch(BaseModel):
    job_id: str
    user_id: str
    input_type: str
    url: str | None = None
    text: str | None = None

@router.post("/jobs", status_code=202)
async def dispatch_job(
    body: JobDispatch,
    request: Request,
    x_internal_secret: str = Header(alias="X-Internal-Secret")
):
    if x_internal_secret != settings.internal_api_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    await request.app.state.redis.lpush("job_queue", body.job_id)
    return {"job_id": body.job_id, "queued": True}
```

### 9.7 `main.py`

```powershell
code main.py
```

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from routers import internal
from db.connection import init_db_pool, close_db_pool
import redis.asyncio as redis_async
from config import settings
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await init_db_pool(settings.database_url)
    app.state.redis = redis_async.from_url(settings.redis_url)
    workers = [asyncio.create_task(job_worker(app)) for _ in range(3)]
    yield
    for w in workers:
        w.cancel()
    await close_db_pool(app.state.db_pool)
    await app.state.redis.aclose()

app = FastAPI(title="TruthStream AI Service", lifespan=lifespan)
app.include_router(internal.router, prefix="/internal")

async def job_worker(app: FastAPI):
    while True:
        try:
            result = await app.state.redis.brpop("job_queue", timeout=1)
            if result:
                _, job_id = result
                print(f"Worker picked up job: {job_id.decode()}")
        except Exception as e:
            print(f"Worker error: {e}")
            await asyncio.sleep(1)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service"}
```

### 9.8 FastAPI Dockerfile

```powershell
code Dockerfile
```

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.9 Run FastAPI Locally on Windows

```powershell
# New terminal tab
cd C:\Users\$env:USERNAME\Documents\truthstream\ai-service

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Load environment variables (note: going up one level to find .env)
. ..\load-env.ps1 -EnvFile ..\.env

# Start FastAPI with hot-reload
uvicorn main:app --reload --port 8000
```

Expected output:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Open your browser at http://localhost:8000/docs — you should see the Swagger UI with the `/internal/jobs` endpoint and `/health` endpoint.

---

## Phase 10 — React Frontend Bootstrap

### 10.1 Create Vite React Project

```powershell
# New terminal tab
cd C:\Users\$env:USERNAME\Documents\truthstream

# Create the React project inside the frontend folder
# This will replace the empty frontend\ folder
npm create vite@latest frontend -- --template react-ts
# When asked "Current directory is not empty. Remove existing files..." → press Y

cd frontend
npm install
```

### 10.2 Install Dependencies

```powershell
npm install axios react-router-dom d3
npm install -D @types/d3 @types/react-router-dom vitest @testing-library/react @testing-library/jest-dom jsdom
```

### 10.3 `vite.config.ts`

Open `frontend\vite.config.ts` and replace its contents:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      }
    }
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
  }
})
```

### 10.4 `src\api\client.ts`

```powershell
mkdir src\api
code src\api\client.ts
```

```typescript
import axios from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default client
```

### 10.5 `src\test-setup.ts`

```powershell
code src\test-setup.ts
```

```typescript
import '@testing-library/jest-dom'
```

### 10.6 Add test script to `package.json`

Open `frontend\package.json` and add `"test": "vitest"` to the scripts section:

```json
"scripts": {
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "test": "vitest"
},
```

### 10.7 Frontend Dockerfile

```powershell
code Dockerfile
```

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 10.8 `nginx.conf`

```powershell
code nginx.conf
```

```nginx
server {
  listen 80;
  root /usr/share/nginx/html;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api {
    proxy_pass http://backend:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }
}
```

### 10.9 Run Frontend Locally

```powershell
# New terminal tab
cd C:\Users\$env:USERNAME\Documents\truthstream\frontend
npm run dev
```

Expected output:
```
  VITE v5.x.x  ready in xxx ms
  ➜  Local:   http://localhost:3000/
  ➜  Network: use --host to expose
```

Open http://localhost:3000 in your browser. You should see the default Vite + React page.

---

## Phase 11 — Redis Verification

After `docker compose up redis -d` from the truthstream root:

```powershell
# Connect to Redis CLI inside the container
docker exec -it truthstream-redis redis-cli

# Inside Redis CLI:
PING
# Expected: PONG

SET test_key "hello"
GET test_key
# Expected: "hello"

DEL test_key
exit
```

Test pub/sub — open two terminal tabs:

**Tab A:**
```powershell
docker exec -it truthstream-redis redis-cli
SUBSCRIBE job:test123:events
# Waiting for messages...
```

**Tab B:**
```powershell
docker exec -it truthstream-redis redis-cli
PUBLISH job:test123:events "{\"type\":\"status\",\"data\":\"test\"}"
```

Tab A should receive: `1) "message"` / `2) "job:test123:events"` / `3) {"type":"status","data":"test"}`

Exit both (`Ctrl+C` then `exit`).

---

## Phase 12 — pgvector Verification

```powershell
docker exec -it truthstream-db psql -U postgres -d truthstream
```

Inside psql:
```sql
-- Confirm pgvector loaded
SELECT typname FROM pg_type WHERE typname = 'vector';
-- Expected: vector

-- Test vector math
CREATE TEMP TABLE vec_test (id serial, embedding vector(3));
INSERT INTO vec_test (embedding) VALUES ('[1,2,3]'), ('[4,5,6]'), ('[1,2,4]');
SELECT id, embedding, embedding <=> '[1,2,3]' AS distance
FROM vec_test
ORDER BY distance;
-- Expected: 3 rows ordered by cosine distance, row with [1,2,3] first (distance 0)

DROP TABLE vec_test;
\q
```

---

## Phase 13 — Postman Setup

### 13.1 Create Collection and Environment

1. Open Postman → **New Collection** → Name: `TruthStream`
2. Click **Environments** (left sidebar) → **+** → Name: `TruthStream Local`
3. Add variables:

| Variable | Initial Value | Current Value |
|---|---|---|
| `base_url` | `http://localhost:8080` | `http://localhost:8080` |
| `access_token` | (empty) | (empty) |
| `job_id` | (empty) | (empty) |

4. Click **Save**, then select `TruthStream Local` from the environment dropdown (top right of Postman).

### 13.2 Add Requests

**POST Register** (add to TruthStream collection):
- Method: POST
- URL: `{{base_url}}/api/auth/register`
- Body → raw → JSON:
  ```json
  {"email": "test@example.com", "password": "Test1234!"}
  ```

**POST Login:**
- Method: POST
- URL: `{{base_url}}/api/auth/login`
- Body → raw → JSON:
  ```json
  {"email": "test@example.com", "password": "Test1234!"}
  ```
- Tests tab — paste this script (auto-saves token after login):
  ```javascript
  const json = pm.response.json();
  if (json.access_token) {
      pm.environment.set("access_token", json.access_token);
      console.log("Token saved to environment");
  }
  ```

**POST Submit Job:**
- Method: POST
- URL: `{{base_url}}/api/jobs`
- Authorization → Bearer Token → Token: `{{access_token}}`
- Body → raw → JSON:
  ```json
  {"input_type": "url", "url": "https://apnews.com/article/test"}
  ```
- Tests tab:
  ```javascript
  const json = pm.response.json();
  if (json.job_id) {
      pm.environment.set("job_id", json.job_id);
  }
  ```

**GET Job Status:**
- Method: GET
- URL: `{{base_url}}/api/jobs/{{job_id}}`
- Authorization → Bearer Token → `{{access_token}}`

**GET Actuator Health:**
- Method: GET
- URL: `{{base_url}}/actuator/health`

**GET FastAPI Health:**
- Method: GET
- URL: `http://localhost:8000/health`

> **SSE streams in Postman:** Postman does not render SSE streams well. For SSE testing, use the **REST Client** VS Code extension. Create a file `test.http` and add:
> ```
> GET http://localhost:8080/api/jobs/YOUR_JOB_ID/stream
> Authorization: Bearer YOUR_TOKEN
> Accept: text/event-stream
> ```
> Click "Send Request" above the line — it streams events live in the VS Code output panel.

---

## Phase 14 — Running Everything Locally on Windows

### Development Mode (4 Terminal Tabs)

Open Windows Terminal. Create 4 tabs with `Ctrl+Shift+T`.

**Tab 1 — Infrastructure:**
```powershell
cd C:\Users\$env:USERNAME\Documents\truthstream
. .\load-env.ps1
docker compose up db redis -d
docker compose ps
# Wait until both show "healthy"
```

**Tab 2 — FastAPI:**
```powershell
cd C:\Users\$env:USERNAME\Documents\truthstream\ai-service
.\.venv\Scripts\Activate.ps1
. ..\load-env.ps1 -EnvFile ..\.env
uvicorn main:app --reload --port 8000
```

**Tab 3 — Spring Boot:**
```powershell
cd C:\Users\$env:USERNAME\Documents\truthstream\backend
. ..\load-env.ps1 -EnvFile ..\.env

# Set environment variables that Spring Boot reads
$env:SPRING_DATASOURCE_URL = "jdbc:postgresql://localhost:5432/truthstream"
$env:SPRING_DATASOURCE_USERNAME = $env:DB_USER
$env:SPRING_DATASOURCE_PASSWORD = $env:DB_PASSWORD

# Run with Windows Maven wrapper
.\mvnw.cmd spring-boot:run
```

**Tab 4 — React:**
```powershell
cd C:\Users\$env:USERNAME\Documents\truthstream\frontend
npm run dev
```

**Access points:**
- Frontend: http://localhost:3000
- Spring Boot: http://localhost:8080
- Spring Boot health: http://localhost:8080/actuator/health
- FastAPI docs (Swagger): http://localhost:8000/docs
- FastAPI health: http://localhost:8000/health

### Full Docker Mode (Integration Testing Only)

```powershell
cd C:\Users\$env:USERNAME\Documents\truthstream
. .\load-env.ps1
docker compose up --build
# First build takes 4–6 minutes on Windows due to layer caching
```

---

## Phase 15 — Verification Checklist

Run through every item. All must pass before writing feature code.

### Infrastructure
- [ ] `docker compose ps` shows `truthstream-db` and `truthstream-redis` with status `healthy`
- [ ] `docker exec -it truthstream-db psql -U postgres -d truthstream -c "\dx"` shows `vector`, `uuid-ossp`, `pgcrypto`
- [ ] `docker exec -it truthstream-redis redis-cli PING` returns `PONG`

### FastAPI
- [ ] `http://localhost:8000/health` returns `{"status":"ok","service":"ai-service"}`
- [ ] `http://localhost:8000/docs` loads Swagger UI
- [ ] POST to `http://localhost:8000/internal/jobs` with correct `X-Internal-Secret` header returns 202
- [ ] POST with wrong `X-Internal-Secret` returns 403

### Spring Boot
- [ ] `http://localhost:8080/actuator/health` returns `{"status":"UP",...}`
- [ ] Flyway ran: `docker exec -it truthstream-db psql -U postgres -d truthstream -c "\dt"` lists all tables (`users`, `jobs`, `claims`, etc.)
- [ ] POST `http://localhost:8080/api/auth/register` with email/password creates a user row in DB
- [ ] POST `http://localhost:8080/api/auth/login` returns `{"access_token":"..."}`
- [ ] POST `http://localhost:8080/api/jobs` without token returns 401
- [ ] POST `http://localhost:8080/api/jobs` with valid Bearer token returns 202

### Frontend
- [ ] `http://localhost:3000` loads in browser with no red errors in DevTools console
- [ ] Navigating to `http://localhost:3000/login` works
- [ ] `npm run test` in `frontend\` folder passes
- [ ] DevTools → Network tab shows requests to `/api/*` hitting Spring Boot at port 8080 (Vite proxy working)

### End-to-End Connection Test
- [ ] Use Postman: login → get `access_token` → submit job → get `job_id`
- [ ] Open browser DevTools → Network tab → filter by "stream"
- [ ] Navigate to `http://localhost:3000/jobs/{job_id}` — SSE connection appears in Network tab
- [ ] Spring Boot console log shows Redis subscription for that job_id
- [ ] FastAPI console log shows job_id picked up from `job_queue`
- [ ] Redis pub/sub test: manually publish a test event in Redis and see it appear in the browser SSE stream

---

## Phase 16 — Build Order (What to Build First)

### Build First — Weeks 1–2 (The Wire)

Build the end-to-end pipe with fake/stub data before any LLM work:

1. Spring Boot JWT auth (`/api/auth/register`, `/api/auth/login`)
2. `POST /api/jobs` — creates DB row, dispatches to FastAPI, returns 202
3. FastAPI worker receives job_id from Redis queue
4. FastAPI publishes a stub event to Redis pub/sub after 2 seconds: `{"type":"status","data":"processing"}`
5. Spring Boot SSE endpoint subscribes to Redis and forwards to browser
6. Frontend: input form + SSE connection + log events to console
7. Verify full wire: submit job in browser → see stub event in browser console

Do not call a single LLM API until this stub wire works end to end.

### Build Second — Weeks 3–4 (Intelligence)

8. FastAPI: URL fetch + HTML clean (httpx + BeautifulSoup)
9. Claim Extractor Agent (first real OpenAI call)
10. Source Finder Agent (SerpAPI + scrape + stance prompt)
11. Bias Scorer Agent
12. Judge Agent + confidence calculation
13. DB writes for claims, sources, verdicts
14. Frontend: ClaimList, SourceCard, BiasPanel, VerdictBanner, ConfidenceGauge (D3)

### Build Third — Week 5 (Reliability)

15. Retry logic for LLM + scraper (exponential backoff)
16. Duplicate URL detection (url_hash check)
17. Rate limiting in Spring Boot (Redis counter)
18. SSRF protection in FastAPI (block private IPs)
19. pgvector claim deduplication
20. Article truncation at 15,000 tokens

### Week 6 — Polish + Deploy

21. Unit tests for FastAPI agents (pytest + mocked OpenAI)
22. Unit tests for Spring Boot services (JUnit + Mockito)
23. Full Docker Compose test
24. Deploy backend + ai-service + DB + Redis to Railway
25. Deploy frontend to Vercel
26. README with architecture diagram

### Postpone to Post-v1
- JWT refresh tokens
- History page filtering/search
- Admin dashboard
- Public shareable job links
- Playwright E2E tests

### Do Not Add
- Celery or RQ (asyncio workers are sufficient)
- LangChain (plain OpenAI SDK is cleaner for this DAG)
- Kubernetes
- WebSockets (SSE is simpler and sufficient)
- Separate vector database (pgvector covers it)
- User roles beyond basic auth

---

## Windows-Specific Mistakes to Avoid

| Mistake | Fix |
|---|---|
| Using `./mvnw` instead of `.\mvnw.cmd` | On Windows the wrapper is a `.cmd` file. Always `.\mvnw.cmd`. |
| Forgetting `. .\load-env.ps1` (the leading dot-space) | Without the dot, env vars die immediately. The `. ` prefix is mandatory. |
| Using `.venv/bin/activate` | On Windows it's `.\.venv\Scripts\Activate.ps1` |
| Running PowerShell scripts with execution policy blocked | Run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once |
| Using port 5432 if you have a local Postgres install | Change `DB_PORT=5433` in `.env` to avoid conflict |
| Typing `docker-compose` (v1) | Use `docker compose` (v2, no hyphen) |
| Committing `.env` | It is in `.gitignore` — double check with `git status` before every commit |
| `ddl-auto: create` in JPA | Use `validate`. Flyway owns the schema. `create` drops all data on restart. |
| Using `localhost` in Docker container URLs | Inside Docker, use the service name: `http://backend:8080`, not `http://localhost:8080` |
| Forgetting `--reload` when starting Uvicorn | Without it, every Python code change needs a manual Ctrl+C and restart |
| Opening `cmd.exe` by accident | Always use Windows Terminal → PowerShell 7. Check `$PSVersionTable.PSVersion.Major` = 7 |
| Using forward slashes in PowerShell paths when backslash is needed | PowerShell accepts both `\` and `/` — but use `\` when in doubt to avoid confusion |
| Not restarting Windows Terminal after installing tools | PATH changes only take effect in new terminal sessions |
| CRLF line endings in `.sh` files inside Docker | `git config --global core.autocrlf false` prevents this. Set it once in Phase 1. |

---

## Appendix A — Shortcut: `start-dev.ps1`

Create this file at the truthstream root to start all services with one script:

```powershell
code start-dev.ps1
```

```powershell
# start-dev.ps1
# Run from truthstream\ root: .\start-dev.ps1

Write-Host "Starting TruthStream development environment..." -ForegroundColor Cyan

# Load environment
. .\load-env.ps1

# Start infrastructure
Write-Host "`n[1/4] Starting Docker infrastructure..." -ForegroundColor Yellow
docker compose up db redis -d

# Wait for healthy
Write-Host "Waiting for DB and Redis to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
docker compose ps

Write-Host "`n[2/4] Open a new terminal tab and run:" -ForegroundColor Green
Write-Host "  cd ai-service" -ForegroundColor White
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  . ..\load-env.ps1 -EnvFile ..\.env" -ForegroundColor White
Write-Host "  uvicorn main:app --reload --port 8000" -ForegroundColor White

Write-Host "`n[3/4] Open another terminal tab and run:" -ForegroundColor Green
Write-Host "  cd backend" -ForegroundColor White
Write-Host "  . ..\load-env.ps1 -EnvFile ..\.env" -ForegroundColor White
Write-Host "  `$env:SPRING_DATASOURCE_URL = 'jdbc:postgresql://localhost:5432/truthstream'" -ForegroundColor White
Write-Host "  `$env:SPRING_DATASOURCE_USERNAME = `$env:DB_USER" -ForegroundColor White
Write-Host "  `$env:SPRING_DATASOURCE_PASSWORD = `$env:DB_PASSWORD" -ForegroundColor White
Write-Host "  .\mvnw.cmd spring-boot:run" -ForegroundColor White

Write-Host "`n[4/4] Open another terminal tab and run:" -ForegroundColor Green
Write-Host "  cd frontend" -ForegroundColor White
Write-Host "  npm run dev" -ForegroundColor White

Write-Host "`nAccess points when all services are running:" -ForegroundColor Cyan
Write-Host "  Frontend:       http://localhost:3000"
Write-Host "  Spring Boot:    http://localhost:8080"
Write-Host "  Actuator:       http://localhost:8080/actuator/health"
Write-Host "  FastAPI Swagger:http://localhost:8000/docs"
```

Run it:
```powershell
.\start-dev.ps1
```

---

## Appendix B — Stopping Everything

```powershell
# Stop Docker containers (keeps data)
docker compose stop

# Stop Docker containers AND delete data volumes (fresh start)
docker compose down -v

# Kill all local dev servers
# Just press Ctrl+C in each terminal tab
```

---

*TruthStream Windows Setup Roadmap v1.0*