<#
.SYNOPSIS
  TruthStream - Start the full stack with Docker Compose.

.DESCRIPTION
  Runs pre-flight checks, then starts all services with Docker Compose.

.PARAMETER NoBuild
  Skip rebuilding images.

.PARAMETER Detach
  Run containers in background mode.

.PARAMETER Reset
  Remove Docker volumes before startup (destroys DB data).

.EXAMPLE
  .\start.ps1

.EXAMPLE
  .\start.ps1 -Detach

.EXAMPLE
  .\start.ps1 -NoBuild -Detach

.EXAMPLE
  .\start.ps1 -Reset
#>

param(
    [switch]$NoBuild,
    [switch]$Detach,
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Banner
# ------------------------------------------------------------

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " TruthStream - AI Fact-Checking Platform" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------
# Pre-flight checks
# ------------------------------------------------------------

Write-Host "[1/4] Running pre-flight checks..." -ForegroundColor Yellow

# Docker check
try {
    $null = docker info 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw
    }

    Write-Host "  [OK] Docker is running" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Docker is not running." -ForegroundColor Red
    Write-Host "  Start Docker Desktop and try again." -ForegroundColor Yellow
    exit 1
}

# Docker Compose check
try {
    $null = docker compose version 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw
    }

    Write-Host "  [OK] Docker Compose available" -ForegroundColor Green
}
catch {
    Write-Host "  [ERROR] Docker Compose not available." -ForegroundColor Red
    exit 1
}

# .env check
if (-not (Test-Path ".env")) {

    Write-Host "  [ERROR] .env file not found." -ForegroundColor Red
    Write-Host "  Run:" -ForegroundColor Yellow
    Write-Host "    Copy-Item .env.example .env" -ForegroundColor White
    exit 1
}

Write-Host "  [OK] .env file found" -ForegroundColor Green

# OpenAI key warning
$envContent = Get-Content ".env" -Raw

if ($envContent -match "OPENAI_API_KEY=(?:replace-me|sk-replace-me)") {

    Write-Host ""
    Write-Host "WARNING: OPENAI_API_KEY is still placeholder." -ForegroundColor Yellow
    Write-Host "AI features may fail." -ForegroundColor Yellow
    Write-Host ""
}

# ------------------------------------------------------------
# Optional reset
# ------------------------------------------------------------

if ($Reset) {

    Write-Host ""
    Write-Host "[RESET MODE]" -ForegroundColor Red
    Write-Host "This will DELETE Docker volumes and database data." -ForegroundColor Red

    $confirm = Read-Host "Type 'yes' to continue"

    if ($confirm -ne "yes") {

        Write-Host "Reset cancelled." -ForegroundColor Yellow
        exit 0
    }

    Write-Host ""
    Write-Host "Removing containers and volumes..." -ForegroundColor Yellow

    docker compose down -v --remove-orphans

    Write-Host "Reset complete." -ForegroundColor Green
}

# ------------------------------------------------------------
# Build and start
# ------------------------------------------------------------

Write-Host ""
Write-Host "[2/4] Starting services..." -ForegroundColor Yellow
Write-Host "Startup order: db + redis -> ai-service -> backend -> frontend" -ForegroundColor DarkGray
Write-Host ""

$composeArgs = @("compose", "up")

if (-not $NoBuild) {
    $composeArgs += "--build"
}

if ($Detach) {
    $composeArgs += "-d"
}

& docker @composeArgs

# ------------------------------------------------------------
# Detached mode info
# ------------------------------------------------------------

if ($Detach) {

    Write-Host ""
    Write-Host "[3/4] Waiting for services..." -ForegroundColor Yellow

    Start-Sleep -Seconds 10

    Write-Host ""
    Write-Host "[4/4] Service status" -ForegroundColor Yellow
    docker compose ps

    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host " ACCESS POINTS" -ForegroundColor Cyan
    Write-Host "===================================================" -ForegroundColor Cyan

    Write-Host ""
    Write-Host "Frontend:" -ForegroundColor Green
    Write-Host "  http://localhost:3000"

    Write-Host ""
    Write-Host "Backend API:" -ForegroundColor Green
    Write-Host "  http://localhost:8080"

    Write-Host ""
    Write-Host "Backend Health:" -ForegroundColor Green
    Write-Host "  http://localhost:8080/actuator/health"

    Write-Host ""
    Write-Host "FastAPI Docs:" -ForegroundColor Green
    Write-Host "  http://localhost:8000/docs"

    Write-Host ""
    Write-Host "FastAPI Health:" -ForegroundColor Green
    Write-Host "  http://localhost:8000/health"

    Write-Host ""
    Write-Host "Useful commands:" -ForegroundColor Cyan
    Write-Host "  docker compose logs -f"
    Write-Host "  docker compose logs -f backend"
    Write-Host "  docker compose logs -f ai-service"
    Write-Host "  .\stop.ps1"

    Write-Host ""
}