#!/bin/bash
# Phase 2 deployment runbook — Cloud Shell
#
# Idempotent end-to-end deploy of every Phase 2 catalyst fetcher.  Re-running
# is safe: secrets use create-or-update, schema migrations are ALTER TABLE
# IF NOT EXISTS, Cloud Run jobs use create-or-update, schedulers use
# create-or-skip-if-exists.
#
# Run from a Cloud Shell session that has cloned the repo and checked out
# claude/fix-gcp-errors-Gueox (or whatever branch the Phase 2 commits are on).
#
# Usage:
#   cd ~/stocks
#   git checkout claude/fix-gcp-errors-Gueox && git pull
#   bash scripts/cloud_shell/phase2_deploy.sh
#
# To run individual sections, copy the block you want into the shell.

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────
# CONFIG — edit if your project / region / contact email differ
# ─────────────────────────────────────────────────────────────────────────

PROJECT_ID="${PROJECT_ID:-adept-mountain-474619-d4}"
REGION="${REGION:-us-east1}"
SEC_USER_AGENT="${SEC_USER_AGENT:-TeneikaAskew Trading teneika@atransformation.tech}"

echo "═══════════════════════════════════════════════════════════════════════"
echo " Phase 2 deploy"
echo "   Project        : $PROJECT_ID"
echo "   Region         : $REGION"
echo "   SEC User-Agent : $SEC_USER_AGENT"
echo "═══════════════════════════════════════════════════════════════════════"
echo

gcloud config set project "$PROJECT_ID" --quiet

# ─────────────────────────────────────────────────────────────────────────
# 1. SEC EDGAR User-Agent secret
#    SEC requires a descriptive User-Agent header with org + contact email.
#    This is NOT an API key — there is no key.  It's identification only.
# ─────────────────────────────────────────────────────────────────────────

echo "▶ [1/6] Storing SEC User-Agent in Secret Manager..."

if gcloud secrets describe sec-user-agent --quiet >/dev/null 2>&1; then
    echo -n "$SEC_USER_AGENT" | \
        gcloud secrets versions add sec-user-agent --data-file=- --quiet
    echo "  ✓ Updated existing sec-user-agent secret"
else
    echo -n "$SEC_USER_AGENT" | \
        gcloud secrets create sec-user-agent \
            --data-file=- --replication-policy=automatic --quiet
    echo "  ✓ Created sec-user-agent secret"
fi

# Allow the trading-runner service account to read it.
SA_EMAIL="trading-runner@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud secrets add-iam-policy-binding sec-user-agent \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet >/dev/null
echo "  ✓ Granted secretAccessor to ${SA_EMAIL}"
echo

# ─────────────────────────────────────────────────────────────────────────
# 2. Apply schema migrations (idempotent)
#    Adds: news_sentiment columns (topics[], overall_sentiment_*) +
#          earnings_history, sec_filings, insider_transactions,
#          top_movers_daily tables.
#    All ALTER/CREATE statements use IF NOT EXISTS so this is safe to re-run.
# ─────────────────────────────────────────────────────────────────────────

echo "▶ [2/6] Applying schema migrations..."

DB_USER=$(gcloud secrets versions access latest --secret=db-trading-user)
DB_PASS=$(gcloud secrets versions access latest --secret=db-trading-pass)
CONNECTION_NAME=$(gcloud secrets versions access latest --secret=cloud-sql-connection-name)
DB_NAME="trading"

if ! command -v cloud-sql-proxy &>/dev/null; then
    echo "  Downloading cloud-sql-proxy..."
    curl -sLo /tmp/cloud-sql-proxy \
        https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.linux.amd64
    chmod +x /tmp/cloud-sql-proxy
    PROXY_BIN=/tmp/cloud-sql-proxy
else
    PROXY_BIN=$(command -v cloud-sql-proxy)
fi

# Find an unused local port to avoid conflicts with anything else.
PROXY_PORT=15432
$PROXY_BIN --port $PROXY_PORT "$CONNECTION_NAME" >/tmp/cloud-sql-proxy.log 2>&1 &
PROXY_PID=$!
trap 'kill $PROXY_PID 2>/dev/null || true' EXIT

# Wait for the proxy to be ready
for i in {1..15}; do
    if PGPASSWORD="$DB_PASS" psql -h 127.0.0.1 -p $PROXY_PORT -U "$DB_USER" \
            -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

PGPASSWORD="$DB_PASS" psql \
    -h 127.0.0.1 -p $PROXY_PORT \
    -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f gcp/schema.sql

kill $PROXY_PID 2>/dev/null || true
trap - EXIT
echo "  ✓ Schema applied (new tables + new news_sentiment columns)"
echo

# ─────────────────────────────────────────────────────────────────────────
# 3. Build the Docker image with the new fetcher code
# ─────────────────────────────────────────────────────────────────────────

echo "▶ [3/6] Building Docker image..."
./gcp/deploy.sh build
echo

# ─────────────────────────────────────────────────────────────────────────
# 4. Deploy all Cloud Run jobs (creates new ones, updates existing)
# ─────────────────────────────────────────────────────────────────────────

echo "▶ [4/6] Deploying Cloud Run jobs..."
./gcp/deploy.sh fetchers
echo

# ─────────────────────────────────────────────────────────────────────────
# 5. Deploy / update Cloud Scheduler triggers
# ─────────────────────────────────────────────────────────────────────────

echo "▶ [5/6] Deploying Cloud Scheduler triggers..."
./gcp/deploy.sh schedulers
echo

# ─────────────────────────────────────────────────────────────────────────
# 6. Verify
# ─────────────────────────────────────────────────────────────────────────

echo "▶ [6/6] Verifying deployments..."
echo
echo "── New / updated Cloud Run jobs ──"
gcloud run jobs list --region "$REGION" --format="table(metadata.name,spec.template.spec.template.spec.taskCount,metadata.creationTimestamp)" \
    --filter="metadata.name~'^fetch-(news-sentiment|earnings-history|sec-filings|insider-transactions|top-movers|market-data)'"

echo
echo "── New schedulers ──"
gcloud scheduler jobs list --location "$REGION" \
    --filter="name~'(news-topics|earnings-history|sec-filings|insider-transactions|top-movers)'" \
    --format="table(name.basename(),schedule,state)"

echo
echo "═══════════════════════════════════════════════════════════════════════"
echo " ✓ Phase 2 deploy complete."
echo
echo " Next step: smoke-test each new fetcher with"
echo "     bash scripts/cloud_shell/phase2_smoke_test.sh"
echo "═══════════════════════════════════════════════════════════════════════"
