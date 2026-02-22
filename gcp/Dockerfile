FROM python:3.11-slim

WORKDIR /app

# System dependencies required by psycopg2 and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library, GCP modules, and scripts
COPY lib/ lib/
COPY gcp/ gcp/
COPY scripts/ scripts/
COPY alert_config.json .

# Default entrypoint (overridden at deploy time via --command)
CMD ["python", "-m", "gcp.premarket_brief"]
