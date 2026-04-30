FROM python:3.11-slim

WORKDIR /app

# System dependencies required by psycopg2 and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (production-only subset)
# Use lock file for reproducibility; fall back to unpinned if lock doesn't exist
COPY requirements-gcp.txt requirements-gcp.lock* ./
RUN if [ -f requirements-gcp.lock ]; then \
        pip install --no-cache-dir -r requirements-gcp.lock; \
    else \
        pip install --no-cache-dir -r requirements-gcp.txt; \
    fi

# Copy shared library, GCP modules, and scripts
COPY lib/ lib/
COPY gcp/ gcp/
COPY scripts/ scripts/
# Root-level modules imported by scripts/run_historical_signals.py
# (sys.path.insert(0, parent.parent) makes /app importable as a
# package root). Without trading_analysis.py at /app/, the historical-
# signals-watchlist Cloud Run Job fails with ModuleNotFoundError.
COPY trading_analysis.py .
COPY alert_config.json .

# Default entrypoint (overridden at deploy time via --command)
CMD ["python", "-m", "gcp.premarket_brief"]
