#!/bin/bash
# Deploy GCP pipeline components.
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project adept-mountain-474619-d4
#   Run setup first: ./gcp/deploy.sh setup
#
# Usage:
#   ./gcp/deploy.sh setup      # provision Cloud SQL, GCS bucket, service account
#   ./gcp/deploy.sh migrate    # migrate local Parquet data → GCS + Cloud SQL
#   ./gcp/deploy.sh build      # build & push Docker image only
#   ./gcp/deploy.sh premarket  # deploy pre-market brief job
#   ./gcp/deploy.sh monitor    # deploy signal monitor service
#   ./gcp/deploy.sh weekend    # deploy weekend review job
#   ./gcp/deploy.sh fetchers   # deploy all data-fetching Cloud Run jobs
#   ./gcp/deploy.sh schedulers # create/update all Cloud Scheduler triggers
#   ./gcp/deploy.sh all        # build + deploy everything + schedulers

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-east1}"
IMAGE="us-east1-docker.pkg.dev/${PROJECT_ID}/trading/trading-system"
SA_EMAIL="trading-runner@${PROJECT_ID}.iam.gserviceaccount.com"

# Read a value from Secret Manager
_secret() { gcloud secrets versions access latest --secret="$1" --quiet 2>/dev/null || echo ''; }

echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"

# ── Setup ─────────────────────────────────────────────────────────────────────
setup() {
    echo "Running infrastructure setup..."
    chmod +x gcp/setup_cloud_sql.sh
    ./gcp/setup_cloud_sql.sh
}

# ── Migration ─────────────────────────────────────────────────────────────────
migrate() {
    echo "Running data migration..."
    GCS_BUCKET="${PROJECT_ID}-trading-data" \
    CLOUD_SQL_CONNECTION_NAME="$(_secret cloud-sql-connection-name)" \
    DB_USER="$(_secret db-trading-user)" \
    DB_PASS="$(_secret db-trading-pass)" \
    DB_NAME="trading" \
    python gcp/migrate_to_gcp.py "$@"
}

# ── Image build ───────────────────────────────────────────────────────────────
build_image() {
    echo "Building Docker image..."
    # Use a minimal build context — only the files gcp/Dockerfile actually COPYs.
    # This avoids sending the 4GB data/ directory to Cloud Build.
    local tmpdir
    tmpdir=$(mktemp -d)
    cp requirements-gcp.txt    "$tmpdir/"
    cp alert_config.json       "$tmpdir/"
    cp gcp/Dockerfile          "$tmpdir/Dockerfile"
    cp -r lib/                 "$tmpdir/lib/"
    cp -r gcp/                 "$tmpdir/gcp/"
    cp -r scripts/             "$tmpdir/scripts/"
    gcloud builds submit --tag "${IMAGE}" "$tmpdir"
    rm -rf "$tmpdir"
}

# ── Shared env vars injected into every Cloud Run job ─────────────────────────
_env_string() {
    local env
    env="CLOUD_SQL_CONNECTION_NAME=$(_secret cloud-sql-connection-name)"
    env="${env},DB_USER=$(_secret db-trading-user)"
    env="${env},DB_PASS=$(_secret db-trading-pass)"
    env="${env},DB_NAME=trading"
    env="${env},GCS_BUCKET=${PROJECT_ID}-trading-data"
    local webhook
    webhook="$(_secret discord-webhook 2>/dev/null || true)"
    [ -n "$webhook" ] && env="${env},DISCORD_WEBHOOK_URL=${webhook}"
    echo "$env"
}

# ── Pre-market brief (Cloud Run Job) ─────────────────────────────────────────
deploy_premarket() {
    echo "Deploying pre-market brief job..."
    gcloud run jobs create premarket-brief \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.premarket_brief" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update premarket-brief \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.premarket_brief" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Signal monitor (Cloud Run Job — runs during market hours, exits at close) ─
deploy_monitor() {
    echo "Deploying signal monitor job..."
    gcloud run jobs create signal-monitor \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 0 \
        --task-timeout 28800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.signal_monitor" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update signal-monitor \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.signal_monitor" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Weekend review (Cloud Run Job) ───────────────────────────────────────────
deploy_weekend() {
    echo "Deploying weekend review job..."
    gcloud run jobs create weekend-review \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.weekend_review" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update weekend-review \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.weekend_review" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Data-fetching jobs ────────────────────────────────────────────────────────
deploy_fetch_market_data() {
    echo "Deploying fetch-market-data job..."
    gcloud run jobs create fetch-market-data \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 2 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_market_data" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-market-data \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_market_data" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_fetch_etf_options() {
    echo "Deploying fetch-etf-options job..."
    gcloud run jobs create fetch-etf-options \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_etf_options" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-etf-options \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_etf_options" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_fetch_earnings_options() {
    echo "Deploying fetch-earnings-options job..."
    gcloud run jobs create fetch-earnings-options \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_earnings_options" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-earnings-options \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_earnings_options" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_fetch_alphavantage() {
    echo "Deploying fetch-alphavantage-intraday job..."
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,ALPHA_VANTAGE_API_KEY=${av_key}}"

    gcloud run jobs create fetch-alphavantage-intraday \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 1 \
        --task-timeout 3600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_alphavantage_intraday" \
        --set-env-vars "${av_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-alphavantage-intraday \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_alphavantage_intraday" \
        --set-env-vars "${av_env}" \
        --quiet
}

deploy_fetchers() {
    deploy_fetch_market_data
    deploy_fetch_etf_options
    deploy_fetch_earnings_options
    deploy_fetch_alphavantage
}

# ── Cloud Scheduler triggers ──────────────────────────────────────────────────
_job_uri() {
    echo "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${1}:run"
}

_schedule() {
    local NAME=$1 CRON=$2 JOB=$3
    gcloud scheduler jobs create http "${NAME}" \
        --location "${REGION}" \
        --schedule "${CRON}" \
        --time-zone "America/New_York" \
        --uri "$(_job_uri "${JOB}")" \
        --http-method POST \
        --oauth-service-account-email "${SA_EMAIL}" \
        --quiet 2>/dev/null || echo "  ${NAME}: already exists"
}

deploy_schedulers() {
    echo "Creating Cloud Scheduler triggers..."

    # Pre-market brief — 8:30 AM ET weekdays
    _schedule "premarket-brief-daily"    "30 8 * * 1-5"   "premarket-brief"
    # Signal monitor — 9:25 AM ET weekdays (starts before open, exits at close)
    _schedule "signal-monitor-daily"     "25 9 * * 1-5"   "signal-monitor"
    # Weekend review — Saturday 9 AM ET
    _schedule "weekend-review-weekly"    "0 9 * * 6"      "weekend-review"
    # Market data — 5 PM ET weekdays
    _schedule "fetch-market-data-daily"  "0 17 * * 1-5"   "fetch-market-data"

    # ETF options — 9 snapshots per trading day
    _schedule "etf-options-0930"  "30 9 * * 1-5"   "fetch-etf-options"
    _schedule "etf-options-0935"  "35 9 * * 1-5"   "fetch-etf-options"
    _schedule "etf-options-0940"  "40 9 * * 1-5"   "fetch-etf-options"
    _schedule "etf-options-1000"  "0 10 * * 1-5"   "fetch-etf-options"
    _schedule "etf-options-1130"  "30 11 * * 1-5"  "fetch-etf-options"
    _schedule "etf-options-1300"  "0 13 * * 1-5"   "fetch-etf-options"
    _schedule "etf-options-1430"  "30 14 * * 1-5"  "fetch-etf-options"
    _schedule "etf-options-1530"  "30 15 * * 1-5"  "fetch-etf-options"
    _schedule "etf-options-1605"  "5 16 * * 1-5"   "fetch-etf-options"

    # Earnings options — 6 snapshots per trading day
    _schedule "earnings-opts-0900"  "0 9 * * 1-5"    "fetch-earnings-options"
    _schedule "earnings-opts-0935"  "35 9 * * 1-5"   "fetch-earnings-options"
    _schedule "earnings-opts-1000"  "0 10 * * 1-5"   "fetch-earnings-options"
    _schedule "earnings-opts-1200"  "0 12 * * 1-5"   "fetch-earnings-options"
    _schedule "earnings-opts-1550"  "50 15 * * 1-5"  "fetch-earnings-options"
    _schedule "earnings-opts-1630"  "30 16 * * 1-5"  "fetch-earnings-options"

    # AlphaVantage monthly intraday — 1st of each month 9 PM ET
    _schedule "av-intraday-monthly"  "0 21 1 * *"  "fetch-alphavantage-intraday"

    echo "All schedulers configured."
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "${1:-help}" in
    setup)       setup ;;
    migrate)     shift; migrate "$@" ;;
    build)       build_image ;;
    premarket)   build_image && deploy_premarket ;;
    monitor)     build_image && deploy_monitor ;;
    weekend)     build_image && deploy_weekend ;;
    fetchers)    build_image && deploy_fetchers ;;
    schedulers)  deploy_schedulers ;;
    all)
        build_image
        deploy_premarket
        deploy_monitor
        deploy_weekend
        deploy_fetchers
        deploy_schedulers
        echo "All components deployed."
        ;;
    help|*)
        echo "Usage: $0 <command>"
        echo ""
        echo "  setup      Provision Cloud SQL, GCS bucket, service account"
        echo "  migrate    Migrate local Parquet data → GCS + Cloud SQL"
        echo "  build      Build and push Docker image"
        echo "  premarket  Deploy pre-market brief job"
        echo "  monitor    Deploy real-time signal monitor service"
        echo "  weekend    Deploy weekend review job"
        echo "  fetchers   Deploy all data-fetching Cloud Run jobs"
        echo "  schedulers Create/update all Cloud Scheduler triggers"
        echo "  all        Build + deploy everything (jobs + schedulers)"
        ;;
esac
