# Build for the trading platform API.
#
# This image serves /api only. The frontend moved to its own repository
# (github.com/TeneikaAskew/solyra), so there is no longer a Node stage
# building a Vite bundle, and nothing copies a dist/ in.
#
# api/main.py mounts the SPA only when platform/dist exists, so it simply
# does not mount here — no code change was needed to drop the frontend, and
# dropping a dist/ back in would light it up again.

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
        numpy>=1.26.0 \
        scikit-learn>=1.4.0 \
        lightgbm>=4.3.0

# Source — keep the layout main.py expects: <root>/lib, <root>/gcp, <root>/scripts, <root>/platform
COPY lib/ /app/lib/
COPY gcp/ /app/gcp/
# scripts/ is needed at runtime: health.py imports scripts/audit_data_freshness.py
# for /api/health/freshness (powers the Dashboard DataPipelineStatus widget).
COPY scripts/ /app/scripts/
COPY platform/api/ /app/platform/api/

EXPOSE 8080
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --app-dir /app/platform"]
