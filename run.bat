@echo off
echo Building and starting Docker containers...

echo Stopping existing containers...
docker-compose down

echo Building Docker images...
docker-compose build

echo Starting containers...
docker-compose up -d

timeout /t 5 /nobreak > nul

echo.
echo Container status:
docker-compose ps

echo.
echo Jupyter Notebook is available at: http://localhost:8888
echo Claude Code container is running. Access it with: docker exec -it stocks-claude-code bash
echo.
echo To stop containers, run: docker-compose down
pause