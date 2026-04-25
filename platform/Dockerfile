# Multi-stage build for the unified trading platform.
# Stage 1: build Vite/React frontend → platform/dist
# Stage 2: run FastAPI which serves both /api and the SPA from dist

FROM node:20-slim AS frontend
WORKDIR /build/platform
COPY platform/package.json platform/package-lock.json ./
RUN npm ci
COPY platform/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps — platform API has its own slimmer requirements.txt
COPY platform/api/requirements.txt /tmp/api-reqs.txt
RUN pip install --no-cache-dir -r /tmp/api-reqs.txt \
    && pip install --no-cache-dir \
        google-cloud-storage>=2.14.0 \
        psycopg2-binary>=2.9.9 \
        cloud-sql-python-connector[pg8000]>=1.10.0 \
        sqlalchemy>=2.0.25 \
        python-dotenv>=1.0.0 \
        cachetools>=5.3.0 \
        tenacity>=8.2.0 \
        requests>=2.31.0 \
        numpy>=1.26.0

# Source — keep the layout main.py expects: <root>/lib, <root>/gcp, <root>/platform
COPY lib/ /app/lib/
COPY gcp/ /app/gcp/
COPY platform/api/ /app/platform/api/
COPY --from=frontend /build/platform/dist /app/platform/dist

EXPOSE 8080
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --app-dir /app/platform"]
