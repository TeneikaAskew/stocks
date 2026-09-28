#!/bin/bash
# Provision all GCP infrastructure for the trading system.
#
# Run once from an authenticated shell:
#   chmod +x gcp/setup_cloud_sql.sh
#   ./gcp/setup_cloud_sql.sh
#
# Prerequisites:
#   gcloud auth login && gcloud config set project adept-mountain-474619-d4

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
REGION="${REGION:-us-east1}"
INSTANCE_NAME="${INSTANCE_NAME:-trading-db}"
DB_NAME="${DB_NAME:-trading}"
DB_USER="${DB_USER:-trading_user}"
BUCKET="${BUCKET:-${PROJECT_ID}-trading-data}"
REGISTRY="${REGISTRY:-trading}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-trading-runner}"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GCP Trading System Setup"
echo "  Project : $PROJECT_ID"
echo "  Region  : $REGION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

gcloud config set project "$PROJECT_ID"

# ── 1. Enable required APIs ──────────────────────────────────────────────────
echo ""
echo "▶ Enabling APIs..."
gcloud services enable \
    sqladmin.googleapis.com \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    storage.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    --quiet

echo "  ✓ APIs enabled"

# ── 2. Service account ────────────────────────────────────────────────────────
echo ""
echo "▶ Creating service account: $SERVICE_ACCOUNT..."
gcloud iam service-accounts create "$SERVICE_ACCOUNT" \
    --display-name="Trading System Runner" \
    --quiet 2>/dev/null || echo "  (already exists)"

# Grant roles
for ROLE in \
    roles/cloudsql.client \
    roles/storage.objectAdmin \
    roles/run.invoker \
    roles/secretmanager.secretAccessor; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$ROLE" \
        --quiet >/dev/null
done
echo "  ✓ Service account ready: $SA_EMAIL"

# ── 3. Artifact Registry ──────────────────────────────────────────────────────
echo ""
echo "▶ Creating Artifact Registry: $REGISTRY..."
gcloud artifacts repositories create "$REGISTRY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Trading system Docker images" \
    --quiet 2>/dev/null || echo "  (already exists)"
echo "  ✓ Registry: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REGISTRY}"

# ── 4. GCS Bucket ─────────────────────────────────────────────────────────────
echo ""
echo "▶ Creating GCS bucket: gs://$BUCKET..."
gcloud storage buckets create "gs://$BUCKET" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --quiet 2>/dev/null || echo "  (already exists)"

# Lifecycle: delete raw Parquet backups after 2 years
cat > /tmp/lifecycle.json <<'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 730, "matchesPrefix": ["raw/"]}
    }
  ]
}
EOF
gcloud storage buckets update "gs://$BUCKET" \
    --lifecycle-file=/tmp/lifecycle.json --quiet
echo "  ✓ Bucket: gs://$BUCKET"

# ── 5. Cloud SQL instance ──────────────────────────────────────────────────────
echo ""
echo "▶ Creating Cloud SQL instance: $INSTANCE_NAME (PostgreSQL 15)..."
echo "  This takes 3-5 minutes..."

gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=POSTGRES_15 \
    --tier=db-g1-small \
    --region="$REGION" \
    --storage-auto-increase \
    --storage-size=20 \
    --backup-start-time=03:00 \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=4 \
    --deletion-protection \
    --quiet 2>/dev/null || echo "  (already exists)"

echo "  ✓ Instance created"

# ── 6. Database + user ────────────────────────────────────────────────────────
echo ""
echo "▶ Creating database and user..."

gcloud sql databases create "$DB_NAME" \
    --instance="$INSTANCE_NAME" \
    --quiet 2>/dev/null || echo "  (database already exists)"

# Generate a strong password and store in Secret Manager
DB_PASS=$(openssl rand -base64 24)

gcloud secrets create db-trading-pass \
    --replication-policy=automatic \
    --quiet 2>/dev/null || true

echo -n "$DB_PASS" | gcloud secrets versions add db-trading-pass --data-file=-

gcloud sql users create "$DB_USER" \
    --instance="$INSTANCE_NAME" \
    --password="$DB_PASS" \
    --quiet 2>/dev/null || \
gcloud sql users set-password "$DB_USER" \
    --instance="$INSTANCE_NAME" \
    --password="$DB_PASS" \
    --quiet

echo "  ✓ Database '$DB_NAME' and user '$DB_USER' ready"
echo "  ✓ Password stored in Secret Manager: db-trading-pass"

# ── 7. Run schema migrations ──────────────────────────────────────────────────
echo ""
echo "▶ Applying schema (gcp/schema.sql)..."

CONNECTION_NAME=$(gcloud sql instances describe "$INSTANCE_NAME" \
    --format='value(connectionName)')

# Use Cloud SQL Auth Proxy for schema application
if ! command -v cloud-sql-proxy &>/dev/null; then
    echo "  Downloading cloud-sql-proxy..."
    curl -sLo /tmp/cloud-sql-proxy \
        https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.linux.amd64
    chmod +x /tmp/cloud-sql-proxy
    PROXY_BIN=/tmp/cloud-sql-proxy
else
    PROXY_BIN=cloud-sql-proxy
fi

# Start proxy in background
$PROXY_BIN --port 5432 "$CONNECTION_NAME" &
PROXY_PID=$!
sleep 5

# Applied through gcp/apply_schema.py, NOT `psql -f`. The
# `-- ATOMIC-BEGIN` / `-- ATOMIC-END` markers in gcp/schema.sql are the
# applier's contract: it runs each marked group in ONE transaction, while
# psql treats the markers as ordinary comments and commits every statement
# on its own. The watchlist_history group creates its table, installs the
# trigger that captures membership transitions, and seeds from current
# state -- under psql the lock is released with its own DO statement, so a
# remove/re-add landing in that triggerless window is seeded as continuous
# membership and the log is wrong from birth, unrepairably.
#
# This script provisions a NEW instance, but every step is re-runnable
# ("already exists"), so it CAN be pointed at the live one. An earlier
# version of this comment argued the grouping did not matter here because
# the run rotates the database password first. That argument is wrong, and
# measured wrong: `ALTER USER ... PASSWORD` does not terminate
# already-authenticated sessions or their connection pools -- a session
# opened before the rotation keeps working -- so concurrent writers are
# still live in the window (Codex P2 on `f94ce61`).
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt

DB_HOST=127.0.0.1 DB_PORT=5432 \
DB_USER="$DB_USER" DB_PASS="$DB_PASS" DB_NAME="$DB_NAME" \
python3 -m gcp.apply_schema \
    --revision="$(git rev-parse HEAD)" \
    --revision-time="$(git log -1 --format=%ct HEAD)" \
    --revision-ancestors="$(git rev-list --max-count=100 HEAD | tr '\n' ' ')"

kill $PROXY_PID 2>/dev/null || true
echo "  ✓ Schema applied"

# ── 8. Store secrets for Cloud Run ───────────────────────────────────────────
echo ""
echo "▶ Storing connection config in Secret Manager..."

echo -n "${CONNECTION_NAME}" | \
    gcloud secrets create cloud-sql-connection-name \
    --data-file=- --replication-policy=automatic --quiet 2>/dev/null || \
echo -n "${CONNECTION_NAME}" | \
    gcloud secrets versions add cloud-sql-connection-name --data-file=-

echo -n "${DB_USER}" | \
    gcloud secrets create db-trading-user \
    --data-file=- --replication-policy=automatic --quiet 2>/dev/null || \
echo -n "${DB_USER}" | \
    gcloud secrets versions add db-trading-user --data-file=-

echo -n "${BUCKET}" | \
    gcloud secrets create gcs-trading-bucket \
    --data-file=- --replication-policy=automatic --quiet 2>/dev/null || \
echo -n "${BUCKET}" | \
    gcloud secrets versions add gcs-trading-bucket --data-file=-

echo "  ✓ Secrets stored"

# ── 9. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo ""
echo "  Cloud SQL instance : $INSTANCE_NAME"
echo "  Connection name    : $CONNECTION_NAME"
echo "  Database           : $DB_NAME"
echo "  DB user            : $DB_USER"
echo "  GCS bucket         : gs://$BUCKET"
echo "  Service account    : $SA_EMAIL"
echo ""
echo "  Next steps:"
echo "    1. Set DISCORD_WEBHOOK_URL secret:"
echo "       echo -n 'https://discord.com/...' | gcloud secrets create discord-webhook-insights --data-file=-"
echo "    2. Set ALPHA_VANTAGE_API_KEY secret:"
echo "       echo -n 'YOUR_KEY' | gcloud secrets create av-api-key --data-file=-"
echo "    3. Migrate existing data:"
echo "       ./gcp/deploy.sh migrate"
echo "    4. Deploy all Cloud Run jobs:"
echo "       ./gcp/deploy.sh all"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
