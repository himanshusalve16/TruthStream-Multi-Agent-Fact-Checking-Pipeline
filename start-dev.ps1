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
