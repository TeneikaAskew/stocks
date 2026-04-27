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
#   ./gcp/deploy.sh insights   # deploy insight-pipeline job + Cloud Tasks queue
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

# ── AI Insights pipeline (Cloud Run Job) ─────────────────────────────────────
# The same image runs scheduled daily batches and on-demand runs enqueued via
# Cloud Tasks from the platform API. The refresh endpoint passes the run_id
# and ticker as env-var overrides on the job execution.
deploy_insight_pipeline() {
    echo "Deploying insight-pipeline job..."
    local admin_token admin_env
    admin_token="$(_secret admin-token 2>/dev/null || true)"
    admin_env="$(_env_string)${admin_token:+,ADMIN_TOKEN=${admin_token}}"

    gcloud run jobs create insight-pipeline \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.insight_pipeline_job" \
        --set-env-vars "${admin_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update insight-pipeline \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.insight_pipeline_job" \
        --set-env-vars "${admin_env}" \
        --quiet
}

# ── AI Insights Discord push (Cloud Run Job) ────────────────────────────────
# Reads today's insight_reports rows and posts them to Discord as a
# multi-embed message. Cloud Scheduler triggers this at 9:15 AM ET
# weekdays — ~30 min after the 8:45 insight-pipeline cron finishes.
deploy_insight_discord_push() {
    echo "Deploying insight-discord-push job..."

    gcloud run jobs create insight-discord-push \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 120 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.insight_discord_push" \
        --args "" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update insight-discord-push \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 120 \
        --command "python,-m,gcp.insight_discord_push" \
        --args "" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Historical signals — watchlist iterator (Cloud Run Job) ─────────────────
# Runs the trading_analysis voter against every active ticker in the
# Cloud SQL watchlists table and upserts results to historical_signals.
# Idempotent (ON CONFLICT DO NOTHING) so re-running on already-covered
# date ranges is a no-op. Caps at --max-tickers=25 unless overridden.
deploy_historical_signals_watchlist() {
    echo "Deploying historical-signals-watchlist job..."

    gcloud run jobs create historical-signals-watchlist \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,scripts.run_historical_signals" \
        --args "--from-watchlist" \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update historical-signals-watchlist \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,scripts.run_historical_signals" \
        --args "--from-watchlist" \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Auto-refresh top-N (Cloud Run Job) ───────────────────────────────────────
# Pre-warms the AI insight cache for the highest-scoring ranker tickers.
# Calls lib.agents.ranker.rank_tickers, picks top N, enqueues a Cloud
# Tasks message per ticker that triggers the existing insight-pipeline
# job in on-demand mode. Cost is bounded by INSIGHT_AUTO_REFRESH_TOP_N
# (default 3 → ~$0.30-1.50/day at typical model costs).
deploy_auto_refresh_top_n() {
    echo "Deploying auto-refresh-top-n job..."
    local env
    env="$(_env_string),INSIGHT_AUTO_REFRESH_TOP_N=3"

    gcloud run jobs create auto-refresh-top-n \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.auto_refresh_top_n" \
        --set-env-vars "${env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update auto-refresh-top-n \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 600 \
        --command "python,-m,gcp.auto_refresh_top_n" \
        --set-env-vars "${env}" \
        --quiet
}

# ── Cloud Tasks queue for on-demand pipeline runs ────────────────────────────
# The refresh endpoint enqueues a task that triggers this Cloud Run job with
# INSIGHT_RUN_ID / INSIGHT_TICKER env overrides. Queue creation is idempotent.
setup_insight_tasks_queue() {
    echo "Ensuring Cloud Tasks queue insight-pipeline-queue exists..."
    gcloud tasks queues create insight-pipeline-queue \
        --location "${REGION}" \
        --max-attempts 2 \
        --max-concurrent-dispatches 5 \
        --quiet 2>/dev/null || echo "  insight-pipeline-queue: already exists"
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
    local benzinga_key
    benzinga_key="$(_secret benzinga-api-key 2>/dev/null || true)"
    [ -n "$benzinga_key" ] && env="${env},BENZINGA_API_KEY=${benzinga_key}"
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
    # 1800s timeout: with EARNINGS_WINDOW_DAYS=7 we may pull bars for
    # ~100 tickers; at 150 RPM that's ~80s of AV calls plus per-ticker
    # indicator computation. 30 min leaves comfortable headroom.
    local env
    env="$(_env_string),EARNINGS_WINDOW_DAYS=7"

    gcloud run jobs create fetch-market-data \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 2 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_market_data" \
        --set-env-vars "${env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-market-data \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_market_data" \
        --set-env-vars "${env}" \
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

# Pull FRED DGS3MO into daily_rates for BSM Greeks risk-free rate lookup.
# Backfill mode pulls full history from 2015 (~3000 daily rows, <60s).
# Default mode is the 14-day incremental window — wire to a daily scheduler
# at ~00:30 UTC after FRED's nightly publication.
deploy_fetch_fred_rates() {
    echo "Deploying fetch-fred-rates job..."
    local fred_key fred_env
    fred_key="$(_secret fred-api-key 2>/dev/null || true)"
    fred_env="$(_env_string)${fred_key:+,FRED_API_KEY=${fred_key}}"

    gcloud run jobs create fetch-fred-rates \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_fred_rates" \
        --set-env-vars "${fred_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-fred-rates \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_fred_rates" \
        --set-env-vars "${fred_env}" \
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

# News sentiment is split into two Cloud Run jobs sharing the same image:
# `fetch-news-sentiment` queries by ticker (always-on watchlist), while
# `fetch-news-sentiment-topics` queries by AV catalyst topic to capture
# single-name catalysts outside the watchlist. Selection is driven by
# env vars (NEWS_TICKERS / NEWS_TOPICS) so the --command stays identical
# across both jobs.
#
# The list-valued env vars are set via a follow-up --update-env-vars
# call using gcloud's "^@^" delimiter syntax, because the default
# comma delimiter would split SPY,IWM,QQQ into three separate vars.
deploy_fetch_insider_transactions() {
    echo "Deploying fetch-insider-transactions job..."
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,AV_API_KEY=${av_key}}"

    gcloud run jobs create fetch-insider-transactions \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_insider_transactions" \
        --set-env-vars "${av_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-insider-transactions \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_insider_transactions" \
        --set-env-vars "${av_env}" \
        --quiet
}

deploy_fetch_top_movers() {
    echo "Deploying fetch-top-movers job..."
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,AV_API_KEY=${av_key}}"

    gcloud run jobs create fetch-top-movers \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_top_movers" \
        --set-env-vars "${av_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-top-movers \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_top_movers" \
        --set-env-vars "${av_env}" \
        --quiet
}

deploy_fetch_sec_filings() {
    echo "Deploying fetch-sec-filings job..."
    # SEC requires a descriptive User-Agent identifying the organization
    # and a contact email. Pulled from Secret Manager so individual
    # operators can set their own without touching the deploy script.
    local sec_ua env
    sec_ua="$(_secret sec-user-agent 2>/dev/null || true)"
    env="$(_env_string)${sec_ua:+,SEC_USER_AGENT=${sec_ua}}"

    gcloud run jobs create fetch-sec-filings \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_sec_filings" \
        --set-env-vars "${env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-sec-filings \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_sec_filings" \
        --set-env-vars "${env}" \
        --quiet
}

deploy_fetch_earnings_history() {
    echo "Deploying fetch-earnings-history job..."
    # 1800s timeout: pulls ~100-300 tickers (anyone reporting in next 90d).
    # AV rate limit at 150 RPM means ~2-3 minutes of API time at peak.
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,AV_API_KEY=${av_key}}"

    gcloud run jobs create fetch-earnings-history \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_earnings_history" \
        --set-env-vars "${av_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-earnings-history \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_earnings_history" \
        --set-env-vars "${av_env}" \
        --quiet
}

deploy_fetch_news_sentiment() {
    echo "Deploying fetch-news-sentiment (ticker mode) job..."
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,AV_API_KEY=${av_key}}"

    # Tickers come from alert_config.json `watchlist` at runtime via
    # gcp/fetchers/_watchlist.load_watchlist(). No hardcoded NEWS_TICKERS
    # env var — change the watchlist by editing alert_config.json + redeploy
    # the image. --args="" defensively strips any leftover positional CLI
    # args from prior manual gcloud edits that would break argparse.
    gcloud run jobs create fetch-news-sentiment \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --set-env-vars "${av_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        --set-env-vars "${av_env}" \
        --remove-env-vars "NEWS_TICKERS" \
        --quiet
}

deploy_fetch_news_sentiment_topics() {
    echo "Deploying fetch-news-sentiment-topics (topic mode) job..."
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,AV_API_KEY=${av_key}}"

    # NEWS_TOPICS env var (set below) is the source of truth; --args=""
    # defensively strips any leftover CLI args from prior manual edits.
    gcloud run jobs create fetch-news-sentiment-topics \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --set-env-vars "${av_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment-topics \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        --set-env-vars "${av_env}" \
        --quiet

    # 5 catalyst-rich topics — AV's hard cap per call.
    gcloud run jobs update fetch-news-sentiment-topics \
        --region "${REGION}" \
        --update-env-vars "^@^NEWS_TOPICS=mergers_and_acquisitions,technology,financial_markets,earnings,life_sciences" \
        --quiet
}

deploy_fetchers() {
    deploy_fetch_market_data
    deploy_fetch_alphavantage
    deploy_fetch_fred_rates
    deploy_fetch_economic_events
    deploy_fetch_earnings_calendar
    deploy_fetch_earnings_history
    deploy_fetch_sec_filings
    deploy_fetch_insider_transactions
    deploy_fetch_top_movers
    deploy_fetch_news_sentiment
    deploy_fetch_news_sentiment_topics
}

# ── One-shot maintenance jobs ─────────────────────────────────────────────────
# Apply gcp/schema.sql — adds new tables / columns / indexes. Safe to re-run;
# every statement is IF NOT EXISTS / OR REPLACE. Run via:
#   gcloud run jobs execute apply-schema-migrations --region us-east1 --wait
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


# ── Failure notifier (Cloud Run Service) ─────────────────────────────────────
# Receives Cloud Logging entries about failed Cloud Run Jobs via Pub/Sub push
# and fans out to (1) Discord webhook and (2) GitHub issue create/update.
# See gcp/failure_notifier.py for details.

NOTIFIER_SERVICE="failure-notifier"
NOTIFIER_TOPIC="gcp-job-failures"
NOTIFIER_SUB="gcp-job-failures-push"
NOTIFIER_SINK="gcp-job-failures-sink"

setup_notifier_secrets() {
    echo "Setting up failure notifier secrets..."
    echo ""
    echo "This stores a GitHub PAT (with 'issues: write' on the target repo)"
    echo "and the target repo slug in Secret Manager. Both are injected into"
    echo "the failure-notifier Cloud Run service at deploy time."
    echo ""

    # ── GitHub PAT ────────────────────────────────────────────────────────
    if ! gcloud secrets describe github-pat --quiet >/dev/null 2>&1; then
        # Auto-detect: GCP secret → env var → interactive prompt
        local pat=""
        # 1) Pull from existing GCP Secret Manager secret (shared PAT)
        if [ -z "$pat" ]; then
            pat="$(gcloud secrets versions access latest \
                --secret=gh-stocks-repo-pat \
                --project=28960574877 --quiet 2>/dev/null || true)"
            [ -n "$pat" ] && echo "  PAT sourced from GCP secret gh-stocks-repo-pat"
        fi
        # 2) STOCKS_REPO_PAT env var
        if [ -z "$pat" ]; then
            pat="${STOCKS_REPO_PAT:-}"
            [ -n "$pat" ] && echo "  PAT sourced from STOCKS_REPO_PAT env var"
        fi
        # 3) Interactive fallback
        if [ -z "$pat" ]; then
            echo "Enter a GitHub PAT with 'issues: write' (input hidden):"
            read -rs pat
            echo ""
        fi
        if [ -z "$pat" ]; then
            echo "  ERROR: no PAT found. Ensure gh-stocks-repo-pat exists in GCP project 28960574877,"
            echo "         or set STOCKS_REPO_PAT env var."
            return 1
        fi
        printf '%s' "$pat" | gcloud secrets create github-pat \
            --replication-policy=automatic --data-file=- --quiet
        echo "  github-pat created"
    else
        echo "  github-pat already exists. Use 'gcloud secrets versions add' to rotate."
    fi

    # ── GitHub repo slug ──────────────────────────────────────────────────
    if ! gcloud secrets describe github-repo --quiet >/dev/null 2>&1; then
        # Auto-detect from git remote origin
        local repo="${GH_REPO:-}"
        if [ -z "$repo" ]; then
            local remote_url
            remote_url="$(git remote get-url origin 2>/dev/null || true)"
            # Extract owner/repo from HTTPS or SSH URLs
            repo="$(echo "$remote_url" | sed -E 's#.*(github\.com[:/])##; s/\.git$//')"
        fi
        if [ -z "$repo" ]; then
            echo "Enter the GitHub repo slug (e.g. 'TeneikaAskew/stocks'):"
            read -r repo
        fi
        if [ -z "$repo" ]; then
            echo "  ERROR: no repo slug provided."
            return 1
        fi
        echo "  Using repo: ${repo}"
        printf '%s' "$repo" | gcloud secrets create github-repo \
            --replication-policy=automatic --data-file=- --quiet
        echo "  github-repo created"
    else
        echo "  github-repo already exists."
    fi
}

deploy_notifier() {
    echo "Deploying failure-notifier Cloud Run service..."

    # Verify secrets exist (but don't read them into shell variables)
    if ! gcloud secrets describe github-pat --quiet >/dev/null 2>&1 \
       || ! gcloud secrets describe github-repo --quiet >/dev/null 2>&1; then
        echo "  github-pat / github-repo missing. Run: $0 setup-notifier-secrets"
        return 1
    fi

    # Grant the service account access to read the notifier secrets
    for secret in github-pat github-repo; do
        gcloud secrets add-iam-policy-binding "${secret}" \
            --member="serviceAccount:${SA_EMAIL}" \
            --role="roles/secretmanager.secretAccessor" --quiet 2>/dev/null || true
    done

    local env_string
    env_string="$(_env_string)"
    env_string="${env_string},GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION}"

    # 1) Deploy the Cloud Run service (overrides Dockerfile CMD with stdlib server)
    # Secrets are mounted from Secret Manager at runtime via --set-secrets so
    # they never appear in revision metadata (visible to anyone with run.services.get).
    gcloud run deploy "${NOTIFIER_SERVICE}" \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3 \
        --service-account "${SA_EMAIL}" \
        --command "python" --args "-m,gcp.failure_notifier" \
        --set-env-vars "${env_string}" \
        --set-secrets="GITHUB_PAT=github-pat:latest,GITHUB_REPO=github-repo:latest" \
        --no-allow-unauthenticated \
        --quiet

    local service_url
    service_url="$(gcloud run services describe "${NOTIFIER_SERVICE}" \
        --region "${REGION}" --format='value(status.url)')"
    echo "  Service URL: ${service_url}"

    # 2) Create Pub/Sub topic (idempotent)
    gcloud pubsub topics create "${NOTIFIER_TOPIC}" --quiet 2>/dev/null \
        || echo "  topic ${NOTIFIER_TOPIC}: already exists"

    # 3) Grant the Pub/Sub service account permission to invoke the Run service
    local project_number pubsub_sa
    project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
    pubsub_sa="service-${project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"

    gcloud run services add-iam-policy-binding "${NOTIFIER_SERVICE}" \
        --region "${REGION}" \
        --member="serviceAccount:${pubsub_sa}" \
        --role="roles/run.invoker" --quiet

    # 4a) Create dead-letter topic so permanently failing messages don't retry forever
    local dlq_topic="${NOTIFIER_TOPIC}-dlq"
    gcloud pubsub topics create "${dlq_topic}" --quiet 2>/dev/null \
        || echo "  topic ${dlq_topic}: already exists"

    # 4b) Create Pub/Sub push subscription with OIDC auth (idempotent)
    gcloud pubsub subscriptions create "${NOTIFIER_SUB}" \
        --topic="${NOTIFIER_TOPIC}" \
        --push-endpoint="${service_url}" \
        --push-auth-service-account="${SA_EMAIL}" \
        --ack-deadline=60 \
        --dead-letter-topic="projects/${PROJECT_ID}/topics/${dlq_topic}" \
        --max-delivery-attempts=5 \
        --quiet 2>/dev/null \
        || gcloud pubsub subscriptions update "${NOTIFIER_SUB}" \
            --push-endpoint="${service_url}" \
            --push-auth-service-account="${SA_EMAIL}" \
            --dead-letter-topic="projects/${PROJECT_ID}/topics/${dlq_topic}" \
            --max-delivery-attempts=5 \
            --quiet

    # Grant Pub/Sub SA permission to publish to dead-letter topic and ack from subscription
    gcloud pubsub topics add-iam-policy-binding "${dlq_topic}" \
        --member="serviceAccount:${pubsub_sa}" \
        --role="roles/pubsub.publisher" --quiet
    gcloud pubsub subscriptions add-iam-policy-binding "${NOTIFIER_SUB}" \
        --member="serviceAccount:${pubsub_sa}" \
        --role="roles/pubsub.subscriber" --quiet

    # 5) Create Cloud Logging sink → Pub/Sub
    # Filter catches Cloud Run Job execution failures but excludes the notifier
    # itself to prevent infinite loops.
    local sink_filter
    sink_filter='resource.type="cloud_run_job"
AND severity>=ERROR
AND resource.labels.job_name!="'"${NOTIFIER_SERVICE}"'"'

    gcloud logging sinks create "${NOTIFIER_SINK}" \
        "pubsub.googleapis.com/projects/${PROJECT_ID}/topics/${NOTIFIER_TOPIC}" \
        --log-filter="${sink_filter}" \
        --quiet 2>/dev/null \
        || gcloud logging sinks update "${NOTIFIER_SINK}" \
            "pubsub.googleapis.com/projects/${PROJECT_ID}/topics/${NOTIFIER_TOPIC}" \
            --log-filter="${sink_filter}" --quiet

    # 6) Grant sink writer permission to publish to the topic
    local sink_writer
    sink_writer="$(gcloud logging sinks describe "${NOTIFIER_SINK}" \
        --format='value(writerIdentity)')"
    gcloud pubsub topics add-iam-policy-binding "${NOTIFIER_TOPIC}" \
        --member="${sink_writer}" \
        --role="roles/pubsub.publisher" --quiet

    echo "failure-notifier deployed and wired to Cloud Logging."
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

    # ETF options intraday (9x/day) was REMOVED — see commit message.
    # Daily EOD snapshots come from fetch-av-options-backfill (with real Greeks)
    # and the Options UI queries AV live for "current chain" via the existing
    # OptionsFlowPage fallback. See docs/DATA_PIPELINE.md.

    # AlphaVantage monthly intraday — 1st of each month 9 PM ET
    _schedule "av-intraday-monthly"  "0 21 1 * *"  "fetch-alphavantage-intraday"

    # FRED rates — 6:30 AM ET daily (after FRED's nightly publication ~04:30 UTC)
    _schedule "fred-rates-daily"  "30 6 * * *"  "fetch-fred-rates"

    # Economic events — 7 AM ET weekdays (before pre-market brief)
    _schedule "economic-events-daily"  "0 7 * * 1-5"  "fetch-economic-events"

    # Earnings calendar (UW + EW) — 7:15 AM ET weekdays
    _schedule "earnings-calendar-daily"  "15 7 * * 1-5"  "fetch-earnings-calendar"

    # Earnings history (AV EARNINGS, per-ticker quarterly EPS) — Sunday 6 AM ET.
    # Weekly cadence is enough since past quarters never change.
    _schedule "earnings-history-weekly"  "0 6 * * 0"  "fetch-earnings-history"

    # SEC EDGAR filings — every 30min during market hours, hourly otherwise.
    # 8-Ks (material events) hit at any time; M&A and earnings preannouncements
    # are the highest-impact catalysts and appear only here at zero cost.
    _schedule "sec-filings-0930"  "30 9 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1000"  "0 10 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1030"  "30 10 * * 1-5"  "fetch-sec-filings"
    _schedule "sec-filings-1100"  "0 11 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1130"  "30 11 * * 1-5"  "fetch-sec-filings"
    _schedule "sec-filings-1200"  "0 12 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1230"  "30 12 * * 1-5"  "fetch-sec-filings"
    _schedule "sec-filings-1300"  "0 13 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1330"  "30 13 * * 1-5"  "fetch-sec-filings"
    _schedule "sec-filings-1400"  "0 14 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1430"  "30 14 * * 1-5"  "fetch-sec-filings"
    _schedule "sec-filings-1500"  "0 15 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1530"  "30 15 * * 1-5"  "fetch-sec-filings"
    _schedule "sec-filings-1600"  "0 16 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1700"  "0 17 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-2000"  "0 20 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-0700"  "0 7 * * 1-5"    "fetch-sec-filings"

    # Insider transactions — daily at 7 AM ET. AV refreshes Form 4 data
    # overnight from EDGAR; daily cadence catches everything new.
    _schedule "insider-transactions-daily"  "0 7 * * 1-5"  "fetch-insider-transactions"

    # Top movers — daily at 4:15 PM ET, after the close so AV's snapshot
    # reflects the full session.
    _schedule "top-movers-daily"  "15 16 * * 1-5"  "fetch-top-movers"

    # News sentiment — HOURLY during the trading day so catalysts can't
    # age out of AV's 50-article window before we capture them. The
    # Apr-7-2026 Broadcom-Google deal hit at 13:46 ET; with the prior
    # 3x schedule (08:00/12:00/16:00) it would have been captured at
    # the 16:00 run only — risking the article aging out under heavy
    # syndication. Hourly cadence keeps AV calls well under the 150
    # RPM plan: 10 runs/day × 5 watchlist tickers = 50 calls/day.
    # Ticker mode reads alert_config.json["watchlist"] when no
    # --tickers arg is passed (see fetch_news_sentiment.main()).
    for h in 08 09 10 11 12 13 14 15 16 17; do
        _schedule "news-sentiment-${h}00"  "0 ${h} * * 1-5"  "fetch-news-sentiment"
    done

    # Topic mode: catalyst stream across all tickers AV tracks. Same
    # hourly cadence, offset 5 min so AV calls stagger.
    for h in 08 09 10 11 12 13 14 15 16 17; do
        _schedule "news-topics-${h}05"  "5 ${h} * * 1-5"  "fetch-news-sentiment-topics"
    done

    # AI Insights daily report — 8:45 AM ET weekdays, after premarket-brief
    # (which seeds the strat + daily indicators the pipeline consumes).
    _schedule "insight-pipeline-daily"   "45 8 * * 1-5"  "insight-pipeline"

    # AI Insights Discord push — 9:15 AM ET weekdays. Reads today's rows
    # from insight_reports and POSTs a multi-embed digest to Discord.
    # Decoupled from the pipeline so delivery can be retried independently
    # if Discord drops.
    _schedule "insight-discord-push-daily"  "15 9 * * 1-5"  "insight-discord-push"

    # Historical signals — watchlist iterator — 1 AM ET weekdays. Runs
    # well after the 5 PM market-data fetcher has settled new intraday
    # bars, picking up any tickers added to the watchlist that day.
    _schedule "historical-signals-watchlist-daily"  "0 1 * * 2-6"  "historical-signals-watchlist"

    # Auto-refresh top-N — 8:10 AM ET weekdays.
    # Runs after news fetchers (8:00, 8:05) so catalyst data is fresh,
    # and before premarket-brief at 8:30 so the warmed reports are
    # ready by the time the user opens the platform.
    _schedule "auto-refresh-top-n"       "10 8 * * 1-5"  "auto-refresh-top-n"

    echo "All schedulers configured."
}

# ── Watchlist backfill ────────────────────────────────────────────────────────
# Idempotent: only fetches what's missing per ticker. Safe to run after
# any edit to alert_config.json["watchlist"]; safe to run nightly. Runs
# locally (not in Cloud Run) because the script is small enough that a
# Cloud Run job is overhead.
backfill_watchlist() {
    echo "Backfilling watchlist data (idempotent)..."
    local args=("$@")
    if [ ! -f .env ]; then
        echo "WARN: no .env at repo root — fetchers may fail without AV_API_KEY" >&2
    else
        # shellcheck disable=SC1091
        set -a; . ./.env; set +a
        export ALPHA_VANTAGE_API_KEY="${AV_API_KEY:-${ALPHA_VANTAGE_API_KEY:-}}"
    fi
    if [ -f .gcp-key.json ]; then
        export GOOGLE_APPLICATION_CREDENTIALS="$PWD/.gcp-key.json"
    fi
    python3 -m scripts.backfill_watchlist_data "${args[@]}"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "${1:-help}" in
    setup)       setup ;;
    migrate)     shift; migrate "$@" ;;
    build)       build_image ;;
    premarket)   build_image && deploy_premarket ;;
    monitor)     build_image && deploy_monitor ;;
    weekend)     build_image && deploy_weekend ;;
    fetchers)    build_image && deploy_fetchers && backfill_watchlist ;;
    insights)    build_image && setup_insight_tasks_queue && deploy_insight_pipeline && deploy_insight_discord_push && deploy_historical_signals_watchlist && deploy_auto_refresh_top_n ;;
    schedulers)  deploy_schedulers ;;
    backfill)    shift; backfill_watchlist "$@" ;;
    apply-schema) build_image && deploy_apply_schema_migrations ;;
    fred-rates)   build_image && deploy_fetch_fred_rates ;;
    spx-greeks)   build_image && deploy_compute_spx_greeks_backfill ;;
    setup-notifier-secrets) setup_notifier_secrets ;;
    notifier)    build_image && deploy_notifier ;;
    all)
        build_image
        deploy_premarket
        deploy_monitor
        deploy_weekend
        deploy_fetchers
        setup_insight_tasks_queue
        deploy_insight_pipeline
        deploy_insight_discord_push
        deploy_historical_signals_watchlist
        deploy_auto_refresh_top_n
        deploy_notifier
        deploy_schedulers
        backfill_watchlist
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
        echo "  insights   Deploy AI insight pipeline job + Cloud Tasks queue"
        echo "  schedulers Create/update all Cloud Scheduler triggers"
        echo "  backfill   Idempotently backfill data for every watchlist ticker."
        echo "             Pass --tickers AVGO,NVDA to override. Runs automatically"
        echo "             after \`fetchers\` and \`all\`."
        echo "  apply-schema Deploy one-shot job that re-applies gcp/schema.sql"
        echo "             (idempotent — every statement is IF NOT EXISTS / OR REPLACE)"
        echo "  fred-rates Deploy fetch-fred-rates job (DGS3MO daily into daily_rates)"
        echo "  spx-greeks Deploy one-shot SPX Greeks backfill job (12h timeout)"
        echo "             python -m scripts.maintenance.compute_spx_greeks --ticker SPX"
        echo "  setup-notifier-secrets  One-time: store GitHub PAT + repo in Secret Manager"
        echo "  notifier   Deploy failure-notifier Cloud Run service + log sink"
        echo "  all        Build + deploy everything (jobs + schedulers + backfill)"
        ;;
esac
