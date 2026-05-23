<#
.SYNOPSIS
  TruthStream - Stop all Docker Compose services.

.PARAMETER Clean
  Also remove Docker volumes (destroys database data).

.PARAMETER Prune
  Remove dangling Docker images after stopping.

.EXAMPLE
  .\stop.ps1

.EXAMPLE
  .\stop.ps1 -Clean

.EXAMPLE
  .\stop.ps1 -Prune
#>

param(
    [switch]$Clean,
    [switch]$Prune
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " TruthStream - Stopping services"
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------
# Clean confirmation
# ------------------------------------------------------------

if ($Clean) {

    Write-Host "WARNING: -Clean will DELETE Docker volumes and database data." -ForegroundColor Red

    $confirm = Read-Host "Type 'yes' to continue"

    if ($confirm -ne "yes") {

        Write-Host "Clean operation cancelled." -ForegroundColor Yellow
        $Clean = $false
    }
}

# ------------------------------------------------------------
# Stop services
# ------------------------------------------------------------

if ($Clean) {

    Write-Host ""
    Write-Host "Stopping containers and removing volumes..." -ForegroundColor Yellow

    docker compose down -v --remove-orphans

    Write-Host ""
    Write-Host "All containers, networks, and volumes removed." -ForegroundColor Green
}
else {

    Write-Host ""
    Write-Host "Stopping containers (data preserved)..." -ForegroundColor Yellow

    docker compose down --remove-orphans

    Write-Host ""
    Write-Host "All services stopped successfully." -ForegroundColor Green
}

# ------------------------------------------------------------
# Optional prune
# ------------------------------------------------------------

if ($Prune) {

    Write-Host ""
    Write-Host "Removing dangling Docker images..." -ForegroundColor Yellow

    docker image prune -f

    Write-Host ""
    Write-Host "Dangling images removed." -ForegroundColor Green
}

# ------------------------------------------------------------
# Final help
# ------------------------------------------------------------

Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Cyan
Write-Host "  Start normally: .\start.ps1"
Write-Host "  Start detached: .\start.ps1 -Detach"
Write-Host "  Full reset:     .\start.ps1 -Reset"
Write-Host ""