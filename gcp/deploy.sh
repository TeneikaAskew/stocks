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
        --set-env-vars "${av_env}" \
        --quiet

    gcloud run jobs update fetch-news-sentiment \
        --region "${REGION}" \
        --update-env-vars "^@^NEWS_TICKERS=SPY,IWM,QQQ" \
        --quiet
}

deploy_fetch_news_sentiment_topics() {
    echo "Deploying fetch-news-sentiment-topics (topic mode) job..."
    local av_key av_env
    av_key="$(_secret av-api-key 2>/dev/null || true)"
    av_env="$(_env_string)${av_key:+,AV_API_KEY=${av_key}}"

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
    deploy_fetch_etf_options
    deploy_fetch_alphavantage
    deploy_fetch_economic_events
    deploy_fetch_earnings_calendar
    deploy_fetch_earnings_history
    deploy_fetch_sec_filings
    deploy_fetch_insider_transactions
    deploy_fetch_top_movers
    deploy_fetch_news_sentiment
    deploy_fetch_news_sentiment_topics
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

    # AlphaVantage monthly intraday — 1st of each month 9 PM ET
    _schedule "av-intraday-monthly"  "0 21 1 * *"  "fetch-alphavantage-intraday"

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

    # News sentiment — 3x per trading day (pre-market, midday, post-close)
    # Ticker mode: always-on watchlist (SPY/IWM/QQQ).
    _schedule "news-sentiment-0800"  "0 8 * * 1-5"   "fetch-news-sentiment"
    _schedule "news-sentiment-1200"  "0 12 * * 1-5"  "fetch-news-sentiment"
    _schedule "news-sentiment-1600"  "0 16 * * 1-5"  "fetch-news-sentiment"

    # Topic mode: catalyst stream across all tickers AV tracks. Offset
    # by 5 min from the ticker schedules so AV quota usage is staggered.
    _schedule "news-topics-0805"     "5 8 * * 1-5"   "fetch-news-sentiment-topics"
    _schedule "news-topics-1205"     "5 12 * * 1-5"  "fetch-news-sentiment-topics"
    _schedule "news-topics-1605"     "5 16 * * 1-5"  "fetch-news-sentiment-topics"

    # AI Insights daily report — 8:45 AM ET weekdays, after premarket-brief
    # (which seeds the strat + daily indicators the pipeline consumes).
    _schedule "insight-pipeline-daily"   "45 8 * * 1-5"  "insight-pipeline"

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
    insights)    build_image && setup_insight_tasks_queue && deploy_insight_pipeline && deploy_auto_refresh_top_n ;;
    schedulers)  deploy_schedulers ;;
    backfill)    shift; backfill_watchlist "$@" ;;
    all)
        build_image
        deploy_premarket
        deploy_monitor
        deploy_weekend
        deploy_fetchers
        setup_insight_tasks_queue
        deploy_insight_pipeline
        deploy_auto_refresh_top_n
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
        echo "  all        Build + deploy everything (jobs + schedulers + backfill)"
        ;;
esac
