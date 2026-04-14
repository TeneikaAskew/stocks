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
    local av_key
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    [ -n "$av_key" ] && env="${env},AV_API_KEY=${av_key},ALPHA_VANTAGE_API_KEY=${av_key}"
    local fred_key
    fred_key="$(_secret fred-api-key 2>/dev/null || true)"
    [ -n "$fred_key" ] && env="${env},FRED_API_KEY=${fred_key}"
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

deploy_fetch_economic_events() {
    echo "Deploying fetch-economic-events job..."
    local fred_key fred_env
    fred_key="$(gcloud secrets versions access latest --secret=fred-api-key 2>/dev/null || true)"
    fred_env="$(_env_string)${fred_key:+,FRED_API_KEY=${fred_key}}"

    gcloud run jobs create fetch-economic-events \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_economic_events,--source,fred" \
        --set-env-vars "${fred_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-economic-events \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_economic_events,--source,fred" \
        --set-env-vars "${fred_env}" \
        --quiet
}

deploy_fetch_earnings_calendar() {
    echo "Deploying fetch-earnings-calendar job..."
    local ew_user ew_pass ew_env
    ew_user="$(_secret ew-user 2>/dev/null || true)"
    ew_pass="$(_secret ew-pass 2>/dev/null || true)"
    ew_env="$(_env_string)${ew_user:+,EW_USER=${ew_user}}${ew_pass:+,EW_PASS=${ew_pass}}"

    gcloud run jobs create fetch-earnings-calendar \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 300 \
        --service-account "${SA_EMAIL}" \
        --command "python,scripts/fetch_earnings_calendar.py,--source,all,--days,30" \
        --set-env-vars "${ew_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-earnings-calendar \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,scripts/fetch_earnings_calendar.py,--source,all,--days,30" \
        --set-env-vars "${ew_env}" \
        --quiet
}

deploy_fetchers() {
    deploy_fetch_market_data
    deploy_fetch_etf_options
    deploy_fetch_earnings_options
    deploy_fetch_alphavantage
    deploy_fetch_economic_events
    deploy_fetch_earnings_calendar
}

# ── One-shot maintenance jobs ─────────────────────────────────────────────────
# These do not run on a schedule. Create once with deploy_*, then execute
# manually via `gcloud run jobs execute <name> --region us-east1` whenever
# needed. All three are idempotent.

# Apply gcp/schema.sql — adds new tables / columns / indexes. Safe to re-run;
# every statement is IF NOT EXISTS / OR REPLACE.
deploy_apply_schema_migrations() {
    echo "Deploying apply-schema-migrations job..."
    gcloud run jobs create apply-schema-migrations \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 0 --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.apply_schema" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update apply-schema-migrations \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.apply_schema" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# Pull FRED DGS3MO + SP500 → daily_rates + market_data_daily(SPX). Used by
# lib.options_greeks for risk-free rate and SPX spot price lookups.
# Backfill mode pulls full history from 2015 (~3000 daily rows, <60s).
# Default mode is the 14-day incremental window — wire to a daily scheduler
# at ~00:30 UTC after FRED's nightly publication.
deploy_fetch_fred_rates() {
    echo "Deploying fetch-fred-rates job..."
    gcloud run jobs create fetch-fred-rates \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_fred_rates" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-fred-rates \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_fred_rates" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# One-shot SPX Greeks backfill. Walks every historical SPX snapshot_date in
# etf_options_snapshots and writes computed Greeks into the *_computed
# sidecar columns. AV columns are NEVER touched. 12h timeout (typical run
# 3-5h on db-g1-small for ~22.5M rows). Idempotent: skips dates whose
# gamma_computed is already finite, unless --force is passed at execute time.
deploy_compute_spx_greeks_backfill() {
    echo "Deploying compute-spx-greeks-backfill job..."
    gcloud run jobs create compute-spx-greeks-backfill \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 0 --task-timeout 43200 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,scripts.maintenance.compute_spx_greeks" \
        --args "--ticker,SPX" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update compute-spx-greeks-backfill \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,scripts.maintenance.compute_spx_greeks" \
        --args "--ticker,SPX" \
        --set-env-vars "$(_env_string)" \
        --quiet
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

    # Pre-market brief — 8:30 AM ET weekdays (today's earnings)
    _schedule "premarket-brief-daily"    "30 8 * * 1-5"   "premarket-brief"
    # Pre-market brief — 9:00 AM ET Sundays (week-ahead earnings digest)
    _schedule "premarket-brief-sunday"   "0 9 * * 0"      "premarket-brief"
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

    # Economic events — 7 AM ET weekdays (before pre-market brief)
    _schedule "economic-events-daily"  "0 7 * * 1-5"  "fetch-economic-events"

    # Earnings calendar (UW + EW) — 7:15 AM ET weekdays
    _schedule "earnings-calendar-daily"  "15 7 * * 1-5"  "fetch-earnings-calendar"

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
    apply-schema) build_image && deploy_apply_schema_migrations ;;
    fred-rates)   build_image && deploy_fetch_fred_rates ;;
    spx-greeks)   build_image && deploy_compute_spx_greeks_backfill ;;
    spx-greeks-pipeline)
        # Convenience: build once + deploy the three jobs that compose the
        # SPX Greeks roll-out. Does NOT execute any of them.
        build_image
        deploy_apply_schema_migrations
        deploy_fetch_fred_rates
        deploy_compute_spx_greeks_backfill
        echo ""
        echo "Pipeline jobs deployed. Execute in order:"
        echo "  gcloud run jobs execute apply-schema-migrations --region ${REGION} --wait"
        echo "  gcloud run jobs execute fetch-fred-rates --region ${REGION} --wait \\"
        echo "      --args=--backfill"
        echo "  gcloud run jobs execute compute-spx-greeks-backfill --region ${REGION} --wait"
        ;;
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
        echo "  setup               Provision Cloud SQL, GCS bucket, service account"
        echo "  migrate             Migrate local Parquet data → GCS + Cloud SQL"
        echo "  build               Build and push Docker image"
        echo "  premarket           Deploy pre-market brief job"
        echo "  monitor             Deploy real-time signal monitor service"
        echo "  weekend             Deploy weekend review job"
        echo "  fetchers            Deploy all data-fetching Cloud Run jobs"
        echo "  schedulers          Create/update all Cloud Scheduler triggers"
        echo "  apply-schema        Deploy schema-migration one-shot job"
        echo "  fred-rates          Deploy FRED rates fetcher job"
        echo "  spx-greeks          Deploy SPX Greeks backfill job"
        echo "  spx-greeks-pipeline Build + deploy schema/FRED/Greeks jobs (no execute)"
        echo "  all                 Build + deploy everything (jobs + schedulers)"
        ;;
esac
