# PowerShell script to build and run Docker containers on Windows
# If this script doesn't run, try: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

Write-Host "Building and starting Docker containers..." -ForegroundColor Green

# Stop and remove existing containers
Write-Host "Stopping existing containers..." -ForegroundColor Yellow
docker-compose down

# Build and start containers
Write-Host "Building Docker images..." -ForegroundColor Yellow
docker-compose build

Write-Host "Starting containers..." -ForegroundColor Yellow
docker-compose up -d

# Wait for services to be ready
Start-Sleep -Seconds 5

# Display status
Write-Host "`nContainer status:" -ForegroundColor Green
docker-compose ps

Write-Host "`nJupyter Notebook is available at: http://localhost:8889" -ForegroundColor Cyan
Write-Host "Claude Code container is running. Access it with: docker exec -it stocks-claude-code bash" -ForegroundColor Cyan

Write-Host "`nTo stop containers, run: docker-compose down" -ForegroundColor Yellow