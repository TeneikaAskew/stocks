#!/usr/bin/env pwsh
# Script to rebuild Docker containers with updated configuration

Write-Host "Rebuilding Docker containers..." -ForegroundColor Green

# Stop existing containers
Write-Host "Stopping existing containers..." -ForegroundColor Yellow
docker compose down

# Rebuild containers
Write-Host "Building containers with updated configuration..." -ForegroundColor Yellow
docker compose build --no-cache

# Start containers
Write-Host "Starting containers..." -ForegroundColor Yellow
docker compose up -d

Write-Host "Containers rebuilt successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To access Claude Code container, run:" -ForegroundColor Cyan
Write-Host "docker exec -it stocks-claude-code-image /bin/bash" -ForegroundColor White