FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared library and GCP modules
COPY lib/ lib/
COPY gcp/ gcp/
COPY alert_config.json .

# Default entrypoint (overridden at deploy time)
CMD ["python", "-m", "gcp.premarket_brief"]
