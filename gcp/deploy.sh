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
        ${DB_SECRET_FLAG} \
        --set-env-vars "${admin_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update insight-pipeline \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.insight_pipeline_job" \
        ${DB_SECRET_FLAG} \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update insight-discord-push \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 120 \
        --command "python,-m,gcp.insight_discord_push" \
        --args "" \
        ${DB_SECRET_FLAG} \
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

    # NOTE: `--args="--from-watchlist"` MUST use the `=` form (no space).
    # When the arg value starts with `-`, gcloud's argparse interprets a
    # space-separated form (`--args "--from-watchlist"`) as a new flag
    # named `--from-watchlist` and errors with "argument --args: expected
    # one argument". See CLAUDE.md rule 5.4 ("Cloud Run Job sizing
    # checklist"). Pre-fix this aborted ./gcp/deploy.sh insights and
    # ./gcp/deploy.sh all mid-way through the deploy bundle.
    gcloud run jobs create historical-signals-watchlist \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,scripts.run_historical_signals" \
        --args="--from-watchlist" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update historical-signals-watchlist \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,scripts.run_historical_signals" \
        --args="--from-watchlist" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Signal-quality report (Cloud Run Job) ───────────────────────────────────
# Phase 0.5 spec items #3-#4. Persists per-signal classifications +
# returns + ATR-normalized MFE into signal_metrics. Runs in two modes
# under the same image:
#   --mode=rolling     hourly during market hours (10–16 ET, scheduler)
#   --mode=historical  once nightly (Tue–Sat 01:00 ET, scheduler) to
#                      promote rolling 'pending' rows to 'final'
# 1 GiB / 10-min timeout per the spec; the script chunks per-ticker
# intraday queries so memory stays well under the cap even on the
# month-long historical backfill window.
deploy_signal_quality_report() {
    echo "Deploying signal-quality-report job..."

    # NB: --args="--mode=rolling" (with =) is required because the
    # arg value itself starts with `-`. With the space form
    # `--args "--mode=rolling"`, gcloud parses `--mode=rolling` as a
    # new flag and bails with "argument --args: expected one
    # argument". Same applies to anywhere args begin with `-`.
    #
    # task-timeout: 3600s (1 h). Original spec said 600s, calibrated
    # for rolling mode (~50 signals/4h, finishes in <2 min). But the
    # SAME job is invoked with --mode=historical for monthly backfills
    # (~1000+ signals, ~15-20 min) — those hit the 600s wall. Bumping
    # to 3600 gives both modes headroom; rolling still bills for ~2
    # min (Cloud Run charges actual runtime, not the configured cap).
    #
    # max-retries 0: the script exits clean on success and non-zero
    # only on legitimate failure (DB outage, bug). Cloud Run can't
    # distinguish "transient" from "permanent" failure, so any retry
    # double-sends failure emails for free. The hourly scheduler tick
    # provides natural retry cadence — if the 14:00 ET run hits a DB
    # blip, the 15:00 ET run picks up where it left off (rolling
    # mode is incremental).
    gcloud run jobs create signal-quality-report \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 0 \
        --task-timeout 3600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,scripts.signal_quality_report" \
        --args="--mode=rolling" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update signal-quality-report \
        --image "${IMAGE}" --region "${REGION}" \
        --max-retries 0 \
        --task-timeout 3600 \
        --command "python,-m,scripts.signal_quality_report" \
        --args="--mode=rolling" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Signal-quality alarm (Cloud Run Job) ───────────────────────────────────
# Phase 0.5 spec item #6. Compares trailing-7d clean-rate vs prior-7d
# clean-rate; alarms when delta < -3pp. Posts to the SIGNAL_QA_WEBHOOK_URL
# Discord channel and exits non-zero so the failure-notifier sink picks
# it up and creates a GitHub issue. ~10s runtime, 256 MiB is plenty.
deploy_signal_quality_alarm() {
    echo "Deploying signal-quality-alarm job..."

    # --max-retries 0: the alarm script INTENTIONALLY exits 1 on a
    # detected regression so the failure-notifier sink picks it up.
    # Cloud Run can't distinguish that from a crash, so any positive
    # retries double-post the Discord alarm. We accept that a real
    # crash (DB outage etc.) won't auto-retry — the next day's run
    # picks up the regression anyway.
    #
    # Memory: 512Mi is Cloud Run's gen2-with-CPU-always-allocated
    # minimum. Tried 256Mi originally — gcloud rejects with "Total
    # memory < 512 Mi is not supported with gen2 execution environment
    # with cpu always allocated (unthrottled)". The actual workload
    # (one DB query + small Discord POST) runs comfortably in <100Mi.
    gcloud run jobs create signal-quality-alarm \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 0 \
        --task-timeout 120 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.signal_quality_alarm" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update signal-quality-alarm \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 120 \
        --command "python,-m,gcp.signal_quality_alarm" \
        ${DB_SECRET_FLAG} \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "${env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update auto-refresh-top-n \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 600 \
        --command "python,-m,gcp.auto_refresh_top_n" \
        ${DB_SECRET_FLAG} \
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

# Sensitive values are passed via Cloud Run --set-secrets so they never
# traverse bash CLI args and aren't visible to anyone with `roles/run.viewer`
# via `gcloud run jobs describe`. Each mapping is `ENV_NAME=secret-id:version`.
#
# Originally only DB_PASS was secret-bound — the variable name reflects that
# narrower history. Track D audit § 8.12 / G.P0.9 expanded the set to cover
# the four additional API keys that were previously baked as literal env
# values via _env_string. See:
#   docs/audit/2026-05-08/track-D.md § 8.12
#   docs/audit/2026-05-08/track-G.md G.P0.9
#
# Mechanism: --set-secrets resolves Secret Manager versions at container
# start time, sidestepping the shell-quoting/MSYS-path-conversion mess that
# bit DB_PASS on 2026-04-30. AV is mapped to two env names (AV_API_KEY +
# ALPHA_VANTAGE_API_KEY) because callers are split across the legacy and
# canonical names; both resolve to the same Secret Manager secret.
#
# Required vs optional secrets:
#   * DB_PASS, av-api-key, discord-webhook-insights are created by
#     setup_cloud_sql.sh — assumed present; deploy fails fast if missing.
#   * fred-api-key, benzinga-api-key are optional add-ons — deploys
#     gracefully skip them when not provisioned, preserving the
#     pre-PR-318 behaviour from `_env_string`'s `[ -n "$key" ] && ...`
#     conditional. Codex P1 review on PR #318 caught the regression
#     where requiring all 5 broke fresh deploys missing the optionals.
_build_secret_flag() {
    local pairs="DB_PASS=db-trading-pass:latest"
    pairs="${pairs},AV_API_KEY=av-api-key:latest"
    pairs="${pairs},ALPHA_VANTAGE_API_KEY=av-api-key:latest"
    pairs="${pairs},DISCORD_WEBHOOK_URL=discord-webhook-insights:latest"
    if gcloud secrets describe fred-api-key --project="${PROJECT_ID}" >/dev/null 2>&1; then
        pairs="${pairs},FRED_API_KEY=fred-api-key:latest"
    else
        echo "  (skipping FRED_API_KEY — secret 'fred-api-key' not in project)" >&2
    fi
    if gcloud secrets describe benzinga-api-key --project="${PROJECT_ID}" >/dev/null 2>&1; then
        pairs="${pairs},BENZINGA_API_KEY=benzinga-api-key:latest"
    else
        echo "  (skipping BENZINGA_API_KEY — secret 'benzinga-api-key' not in project)" >&2
    fi
    echo "--set-secrets=${pairs}"
}
DB_SECRET_FLAG="$(_build_secret_flag)"

# ── Shared env vars injected into every Cloud Run job ─────────────────────────
# Only non-secret values land here. The 4 API keys + DB_PASS go through
# DB_SECRET_FLAG above. CLOUD_SQL_CONNECTION_NAME and DB_USER are stored
# in Secret Manager for centralized rotation but aren't sensitive (the
# connection name is project-region-instance, the username is the role
# label "trading-app"); leaving them in env-vars keeps deploy-script
# simplicity without leaking real credentials.
_env_string() {
    local env
    env="CLOUD_SQL_CONNECTION_NAME=$(_secret cloud-sql-connection-name)"
    env="${env},DB_USER=$(_secret db-trading-user)"
    env="${env},DB_NAME=trading"
    env="${env},GCS_BUCKET=${PROJECT_ID}-trading-data"
    echo "$env"
}

# ── Discord interactions endpoint (Cloud Run SERVICE, not a Job) ────────────
# HTTP service that receives slash-command webhooks from Discord, verifies
# Ed25519 signatures, and dispatches Cloud Run Job executions for /replay,
# /validate, /backtest, /watchlist (latter three stubbed in Slice 1).
#
# Setup prerequisites (one-time, before deploy):
#   1. Use your EXISTING Discord app (the one whose webhook posts the
#      morning briefs). No need to create a new app — the webhook URL
#      and the application identity are independent properties of the
#      same app and can coexist.
#   2. Grab three values from Dev Portal → Your App:
#        General Information  →  Application ID
#        General Information  →  Public Key
#        Bot                  →  Reset Token  (one-time copy; the
#                                webhook flow doesn't need this so
#                                you may have never generated it)
#   3. Store each in GCP Secret Manager (paste value, then Ctrl+D):
#        gcloud secrets create discord-app-id --data-file=-
#        gcloud secrets create discord-public-key --data-file=-
#        gcloud secrets create discord-bot-token --data-file=-
#   4. Grant the trading-runner SA `roles/run.developer` so it can
#      dispatch other Cloud Run Jobs:
#        gcloud projects add-iam-policy-binding ${PROJECT_ID} \
#            --member=serviceAccount:${SA_EMAIL} \
#            --role=roles/run.developer
#   5. Bot must be in the guild with `applications.commands` + `bot`
#      OAuth scopes. If your existing bot is already in the guild
#      (because it posts the morning brief), slash commands work
#      once registered — no re-invite needed.
#   6. After this script runs, set the service URL as the "Interactions
#      Endpoint URL" in Discord Dev Portal → General Information.
#   7. Run scripts/discord/register_commands.py to register the commands.
deploy_discord_interactions() {
    echo "Deploying discord-interactions SERVICE..."

    # Discord-specific secrets only — the service queries Cloud SQL via
    # the same connector path as the rest of the platform.
    local discord_app_id discord_public_key discord_bot_token
    discord_app_id="$(_secret discord-app-id 2>/dev/null || true)"
    discord_public_key="$(_secret discord-public-key 2>/dev/null || true)"
    discord_bot_token="$(_secret discord-bot-token 2>/dev/null || true)"
    if [ -z "${discord_app_id}" ] || [ -z "${discord_public_key}" ] \
       || [ -z "${discord_bot_token}" ]; then
        echo "ERROR: Discord secrets missing. Create discord-app-id, " \
             "discord-public-key, discord-bot-token in Secret Manager first." >&2
        return 1
    fi

    local env
    env="$(_env_string)"
    env="${env},DISCORD_APP_ID=${discord_app_id}"
    env="${env},DISCORD_PUBLIC_KEY=${discord_public_key}"
    env="${env},DISCORD_BOT_TOKEN=${discord_bot_token}"
    env="${env},GCP_PROJECT=${PROJECT_ID},GCP_REGION=${REGION}"

    # Cloud Run service deploy. min-instances=0 keeps cost ~$0 when idle;
    # cold start fits in Discord's 3-sec ack window (1-2 sec on this
    # image). max-instances=5 caps autocomplete-burst cost.
    gcloud run deploy discord-interactions \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 \
        --min-instances 0 --max-instances 5 \
        --timeout 600 \
        --port 8080 \
        --allow-unauthenticated \
        --service-account "${SA_EMAIL}" \
        --command "uvicorn" \
        --args "gcp.discord_interactions.main:app,--host,0.0.0.0,--port,8080" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${env}" \
        --quiet

    echo
    echo "Service URL:"
    gcloud run services describe discord-interactions \
        --region "${REGION}" --format="value(status.url)"
    echo
    echo "Next steps:"
    echo "  1. Copy the URL above + '/discord/interactions' into the"
    echo "     'Interactions Endpoint URL' field in Discord Dev Portal."
    echo "  2. Run: python -m scripts.discord.register_commands"
}


# ── Per-ticker backfill (Cloud Run Job) ──────────────────────────────────────
# One-shot backfill of a single ticker — daily history + intraday + news +
# indicators + pre-market context + watchlist insert. Triggered by the
# Discord /replay command when the user requests a ticker that isn't yet
# in market_data_daily. Idempotent (ON CONFLICT) so re-runs are cheap.
deploy_backfill_ticker() {
    echo "Deploying backfill-ticker job..."
    gcloud run jobs create backfill-ticker \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.backfill_ticker" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update backfill-ticker \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 600 \
        --command "python,-m,gcp.backfill_ticker" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}


# ── Brief/insight accuracy validator (Cloud Run Job) ─────────────────────────
# Wraps scripts/validation/validate_brief_accuracy.py. Triggered by the
# Discord /validate command. Posts results back to the channel via
# DISCORD_WEBHOOK_URL so the 15-min Discord followup TTL doesn't bound
# the job runtime.
deploy_validate_brief() {
    echo "Deploying validate-brief job..."
    gcloud run jobs create validate-brief \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --task-timeout 300 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.validate_brief_job" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update validate-brief \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 300 \
        --command "python,-m,gcp.validate_brief_job" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}


# ── Strategy backtest (Cloud Run Job) ────────────────────────────────────────
# Wraps scripts/run_backtest.py. Triggered by the Discord /backtest
# command. Defaults to a 5y window with --use-strat (per plan §12 user
# decision). Memory bumped to 2Gi because backtests over multi-year
# windows aggregate large daily series in memory before signal sim.
deploy_backtest() {
    echo "Deploying backtest job..."
    gcloud run jobs create backtest \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 1 \
        --task-timeout 900 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.backtest_job" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update backtest \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 900 \
        --command "python,-m,gcp.backtest_job" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}


# ── Pre-market brief (Cloud Run Job) ─────────────────────────────────────────
deploy_premarket() {
    echo "Deploying pre-market brief job..."
    gcloud run jobs create premarket-brief \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.premarket_brief" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update premarket-brief \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.premarket_brief" \
        ${DB_SECRET_FLAG} \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update signal-monitor \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.signal_monitor" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Signal-monitor EOD resolver (Cloud Run Job — runs after close) ──────────
# Per Track D audit § 2 / G.P0.10: closes positions still open at 16:00 ET
# (the in-process exit-watcher in signal-monitor only resolves while the
# Job is alive; anything still-open at close lands here). Replays the same
# exit logic against historical intraday bars and records target_hit /
# time_stop / rsi_extreme / eod_close.
#
# Capacity calc (CLAUDE.md §0):
#   Volume:    ~1,209 alerts × 250KB intraday window ≈ 300 MB peak
#   Velocity:  1 SQL query per (ticker, day) — backfill ~10 (ticker, day)
#              pairs ≈ 10 round-trips × 1.5s pg8000 = 15s + per-row math
#   Wall:      ~5 min for one-shot backfill, ~30s daily steady-state
#   timeout:   3600s = 1hr (≥ 4× wall-clock headroom)
#   memory:    1Gi (peak 300 MB × 2 safety factor + Python overhead)
#   retries:   0 (idempotent via is_open=FALSE; transient retries don't help)
deploy_signal_monitor_eod_resolver() {
    echo "Deploying signal-monitor-eod-resolver job..."
    gcloud run jobs create signal-monitor-eod-resolver \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 0 \
        --task-timeout 3600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.signal_monitor_eod_resolver" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update signal-monitor-eod-resolver \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.signal_monitor_eod_resolver" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# ── Premarket playbook resolver (Cloud Run Job) ──────────────────────────────
# EOD resolver for premarket_analysis brief-playbook outcomes (2026-05-11).
# Walks each (analysis_date, ticker) row's RTH 1-min bars and records
# trigger_hit_ts / target_hit_ts / stop_hit_ts / reversal / MAE / MFE /
# EOD pnl. Self-heals when structured input columns are NULL via
# derive_level_map_from_daily — see gcp/premarket_playbook_resolver.py.
#
# Capacity (CLAUDE.md §0):
#   Volume:    ~3 tier-1 ETFs/day × 1 row × ~3 KB intraday window = tiny
#   Velocity:  3 SQL reads + 3 writes per run = 6 round-trips
#   Wall:      ~30s daily steady-state, ~5 min for one-shot backfill
#   timeout:   3600s = 1hr (≥ 4× wall-clock headroom for backfill mode)
#   memory:    1Gi (peak 50 MB × overhead margin)
#   retries:   0 (idempotent via outcome_resolved_at; transient retries don't help)
deploy_premarket_playbook_resolver() {
    echo "Deploying premarket-playbook-resolver job..."
    gcloud run jobs create premarket-playbook-resolver \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 0 \
        --task-timeout 3600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.premarket_playbook_resolver" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update premarket-playbook-resolver \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.premarket_playbook_resolver" \
        ${DB_SECRET_FLAG} \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update weekend-review \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.weekend_review" \
        ${DB_SECRET_FLAG} \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "${env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-market-data \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_market_data" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${env}" \
        --quiet
}

deploy_fetch_alphavantage() {
    echo "Deploying fetch-alphavantage-intraday job..."
    # ALPHA_VANTAGE_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per
    # G.P0.9; no per-deploy resolution needed.
    gcloud run jobs create fetch-alphavantage-intraday \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 2Gi --cpu 1 --max-retries 1 \
        --task-timeout 3600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_alphavantage_intraday" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-alphavantage-intraday \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_alphavantage_intraday" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# AV HISTORICAL_OPTIONS audit-and-fill job (etf_options_snapshots writer).
# Replaces the disabled .github/workflows/fetch-alphavantage-options-daily.yml.
#
# Spec design:
# - --from-latest tells the fetcher to compute start-date = MAX(snapshot_date
#   in etf_options_snapshots) + 1 day across the requested tickers. end-date
#   defaults to today. This makes the job self-resuming: every Cloud Scheduler
#   invocation catches up from wherever the last successful run left off, no
#   spec edits or args overrides needed as time advances. Initial runs against
#   an empty table fall through to start=today (caller can override with an
#   explicit --start-date for a wide historical backfill).
# - Range mode auto-enables --skip-existing in the fetcher, so re-runs only
#   fetch (ticker, date) pairs missing from etf_options_snapshots — cheap
#   incremental cost after the first full backfill.
# - Secrets (DB_PASS, AV_API_KEY) are mounted via --set-secrets rather than
#   inlined through _env_string. Inlined keys land as plaintext in the Job
#   spec where anyone with run.viewer can read them via gcloud run jobs
#   describe; secret refs require secretmanager.secretAccessor at runtime.
#   This is the pattern the other deploy_fetch_* functions should migrate to.
# - max-retries 0 because Cloud Run can't distinguish transient from
#   permanent failures, and the job is idempotent (ON CONFLICT DO UPDATE)
#   so a re-dispatch after failure converges without duplicate emails.
# - 12h task-timeout sized for the worst case of an empty-SQL initial run
#   (~10 years × 4 tickers ≈ 10K AV calls @ 150 RPM ≈ 70 min). Steady-state
#   monthly runs finish in under a minute (~22 trading days × 4 tickers).
#
# Scheduler binding: av-options-monthly cron at 0 5 1 * * (5:00 UTC on the
# 1st of every month) — see deploy_schedulers().
deploy_av_options_backfill() {
    echo "Deploying fetch-av-options-backfill job..."

    local non_secret_env
    non_secret_env="CLOUD_SQL_CONNECTION_NAME=$(_secret cloud-sql-connection-name)"
    non_secret_env="${non_secret_env},DB_USER=$(_secret db-trading-user)"
    non_secret_env="${non_secret_env},DB_NAME=trading"
    non_secret_env="${non_secret_env},GCS_BUCKET=${PROJECT_ID}-trading-data"

    local secrets_flag
    secrets_flag="--set-secrets=DB_PASS=db-trading-pass:latest"
    secrets_flag="${secrets_flag},AV_API_KEY=av-api-key:latest"
    secrets_flag="${secrets_flag},ALPHA_VANTAGE_API_KEY=av-api-key:latest"

    # Both branches pass the full set of runtime flags so an existing
    # out-of-band job converges to the captured spec on every deploy.
    # gcloud run jobs update leaves omitted flags untouched, so without
    # mirroring memory/cpu/retries/timeout/SA on the update branch a
    # hand-tweaked job would never reconverge from `deploy.sh fetchers`.
    local common_flags=(
        --image "${IMAGE}" --region "${REGION}"
        --memory 2Gi --cpu 1 --max-retries 0
        --task-timeout 43200
        --service-account "${SA_EMAIL}"
        --command "python,-m,gcp.fetchers.fetch_av_historical_options"
        --args "--tickers,SPY IWM QQQ SPX,--from-latest"
        ${secrets_flag}
        --set-env-vars "${non_secret_env}"
        --quiet
    )

    gcloud run jobs create fetch-av-options-backfill "${common_flags[@]}" 2>/dev/null || \
    gcloud run jobs update fetch-av-options-backfill "${common_flags[@]}"
}

# Pull FRED DGS3MO into daily_rates for BSM Greeks risk-free rate lookup.
# Backfill mode pulls full history from 2015 (~3000 daily rows, <60s).
# Default mode is the 14-day incremental window — wire to a daily scheduler
# at ~00:30 UTC after FRED's nightly publication.
deploy_fetch_fred_rates() {
    echo "Deploying fetch-fred-rates job..."
    # FRED_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    gcloud run jobs create fetch-fred-rates \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_fred_rates" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-fred-rates \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_fred_rates" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_fetch_economic_events() {
    # `--source all` invokes both ForexFactory (release times +
    # forecast/previous values direct from source) AND FRED (US
    # agency releases via the canonical-time lookup in
    # gcp/fetchers/fetch_economic_events.py:FRED_RELEASE_TIMES_ET).
    # The previous `--source fred` form silently dropped FF — every
    # event ended up TBD because FRED's API doesn't expose times.
    echo "Deploying fetch-economic-events job..."
    # FRED_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    gcloud run jobs create fetch-economic-events \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_economic_events,--source,all" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-economic-events \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_economic_events,--source,all" \
        --args="" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ew_env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-earnings-calendar \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,scripts/fetch_earnings_calendar.py,--source,all,--days,30" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${ew_env}" \
        --quiet
}

# Pre-market refresh — runs at 8:30 AM ET (15 min before the brief)
# to populate today's gap_pct / pre_high / pre_low for earnings reporters
# and watchlist tickers. Without this, the morning brief sees NULL gap
# data because the 11pm fetcher runs after-the-fact.
#
# Universe: ~50 tickers (today's earnings reporters with options flow
# + yesterday's AMC + watchlist). One AV TIME_SERIES_INTRADAY call per
# ticker, well under the AV premium tier's 1200/day budget.
deploy_fetch_premarket_refresh() {
    echo "Deploying fetch-premarket-refresh job..."
    gcloud run jobs create fetch-premarket-refresh \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 300 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_premarket_refresh" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-premarket-refresh \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_premarket_refresh" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# EW strike verdict evaluator — runs at 16:30 ET (30 min after close)
# to score every Earnings Whispers strike pick from today's session
# against the day's intraday bars. Populates ew_strike_verdict +
# ew_strike_move_pct + ew_minutes_to_hit + ew_minutes_in_zone +
# ew_day_change_pct on earnings_calendar so tomorrow's brief can render
# the verdict in the 🔮 Whispers section ("EW LC $30 HIT +18.7%, in 0m,
# held 390m, day +4.1%"). Idempotent — already-scored rows skip unless
# --force is passed.
deploy_evaluate_ew_strikes() {
    echo "Deploying evaluate-ew-strikes job..."
    gcloud run jobs create evaluate-ew-strikes \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.evaluate_ew_strikes" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update evaluate-ew-strikes \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.evaluate_ew_strikes" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
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
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    gcloud run jobs create fetch-insider-transactions \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_insider_transactions" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-insider-transactions \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_insider_transactions" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_fetch_top_movers() {
    echo "Deploying fetch-top-movers job..."
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    gcloud run jobs create fetch-top-movers \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_top_movers" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-top-movers \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_top_movers" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "${env}" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-sec-filings \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.fetch_sec_filings" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "${env}" \
        --quiet
}

deploy_fetch_earnings_history() {
    echo "Deploying fetch-earnings-history job..."
    # 7200s timeout: 45 tickers × ~50s/ticker (AV API + DB upsert, full-mode
    # tickers can pull 1k+ bars) ≈ 2250s wall-clock — 1800s was 0.8× the
    # estimate (issue #269 — task hit the 1800s cap at ticker [37/45] on
    # 2026-05-04). 7200 = 3.2× the wall-clock per CLAUDE.md §0 rule 5
    # ("≥ 4× the wall-clock estimate"; this is close but free since
    # Cloud Run charges runtime not cap).
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    gcloud run jobs create fetch-earnings-history \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --task-timeout 7200 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_earnings_history" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-earnings-history \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 7200 \
        --command "python,-m,gcp.fetchers.fetch_earnings_history" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_compute_earnings_reactions() {
    echo "Deploying compute-earnings-reactions job..."
    # Phase 1.6 populator: joins earnings_history × market_data_daily
    # (× earnings_calendar for timing fallback) to fill the
    # earnings_reactions table the brief reads. Pure DB join, no
    # external API calls — 1Gi/1CPU is plenty for ~300 tickers.
    # 1800s timeout: ~1s per ticker × 320 tickers = ~5 min typical.
    gcloud run jobs create compute-earnings-reactions \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 \
        --task-timeout 1800 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.compute_earnings_reactions" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update compute-earnings-reactions \
        --image "${IMAGE}" --region "${REGION}" \
        --task-timeout 1800 \
        --command "python,-m,gcp.fetchers.compute_earnings_reactions" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

deploy_fetch_news_sentiment() {
    echo "Deploying fetch-news-sentiment (ticker mode) job..."
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --remove-env-vars "NEWS_TICKERS" \
        --quiet
}

deploy_fetch_news_sentiment_topics() {
    echo "Deploying fetch-news-sentiment-topics (topic mode) job..."
    # AV_API_KEY ships via DB_SECRET_FLAG (--set-secrets) per G.P0.9.
    # NEWS_TOPICS env var (set below) is the source of truth; --args=""
    # defensively strips any leftover CLI args from prior manual edits.
    gcloud run jobs create fetch-news-sentiment-topics \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --max-retries 1 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update fetch-news-sentiment-topics \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.fetchers.fetch_news_sentiment" \
        --args "" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
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
    deploy_av_options_backfill
    deploy_fetch_fred_rates
    deploy_fetch_economic_events
    deploy_fetch_earnings_calendar
    deploy_fetch_earnings_history
    deploy_compute_earnings_reactions
    deploy_fetch_premarket_refresh
    deploy_evaluate_ew_strikes
    deploy_fetch_sec_filings
    deploy_fetch_insider_transactions
    deploy_fetch_top_movers
    deploy_fetch_news_sentiment
    deploy_fetch_news_sentiment_topics
}

# ── Backup / disaster-recovery jobs ───────────────────────────────────────────
# Weekly Cloud SQL → GCS logical backup. Replaces the GCS parquet backup
# pattern (which only covered 2 of ~30 tables) with a full pg_dump that
# captures every table on every run.
#
# Runs as a Cloud Run Job invoked by Cloud Scheduler weekly (Sunday 04:00 UTC,
# wired in deploy_schedulers). Calls the Cloud SQL Admin API to trigger an
# offload-mode SQL export — Cloud SQL itself writes the gzipped dump to GCS,
# the calling SA only triggers + polls the operation. Combined with PITR
# (enabled via `gcloud sql instances patch trading-db --enable-point-in-time-recovery`)
# this gives ~daily snapshots + 7-day point-in-time recovery + weekly
# cross-machinery dump in a different storage tier.
#
# Output path: gs://${PROJECT_ID}-trading-data/sql-dumps/trading-YYYYMMDD-HHMMSS.sql.gz
#
# IAM prerequisites — one-time, run via:
#   ./gcp/deploy.sh setup-pg-dump-iam
# 1. trading-runner SA needs roles/cloudsql.editor on the project (to invoke
#    the export API).
# 2. The Cloud SQL service identity
#    (service-${PROJECT_NUMBER}@gcp-sa-cloud-sql.iam.gserviceaccount.com)
#    needs roles/storage.objectAdmin on the destination bucket — Cloud SQL
#    itself writes the file, NOT the calling SA.
deploy_weekly_pg_dump() {
    echo "Deploying cloud-sql-weekly-export job..."

    local non_secret_env
    non_secret_env="GCP_PROJECT=${PROJECT_ID}"
    non_secret_env="${non_secret_env},CLOUD_SQL_INSTANCE=trading-db"
    non_secret_env="${non_secret_env},DB_NAME=trading"
    non_secret_env="${non_secret_env},SQL_DUMP_BUCKET=${PROJECT_ID}-trading-data"
    non_secret_env="${non_secret_env},SQL_DUMP_PREFIX=sql-dumps"

    local common_flags=(
        --image "${IMAGE}" --region "${REGION}"
        --memory 512Mi --cpu 1 --max-retries 0
        --task-timeout 3600
        --service-account "${SA_EMAIL}"
        --command "python,-m,gcp.sql_export_to_gcs"
        --set-env-vars "${non_secret_env}"
        --quiet
    )

    gcloud run jobs create cloud-sql-weekly-export "${common_flags[@]}" 2>/dev/null || \
    gcloud run jobs update cloud-sql-weekly-export "${common_flags[@]}"
}

# One-time IAM setup for the weekly pg_dump path. Idempotent — re-running
# will report "already exists" but won't break.
setup_pg_dump_iam() {
    echo "=== Configuring IAM for cloud-sql-weekly-export ==="

    # Resolve the project number to construct the Cloud SQL service identity.
    local project_number
    project_number="$(gcloud projects describe "${PROJECT_ID}" \
        --format='value(projectNumber)')"
    local cloud_sql_sa="service-${project_number}@gcp-sa-cloud-sql.iam.gserviceaccount.com"
    local bucket="${PROJECT_ID}-trading-data"

    echo
    echo "1) Granting roles/cloudsql.editor to trading-runner SA on project..."
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role=roles/cloudsql.editor \
        --condition=None \
        --quiet 2>&1 | tail -3

    echo
    echo "2) Granting roles/storage.objectAdmin to Cloud SQL service identity"
    echo "   (${cloud_sql_sa}) on bucket gs://${bucket}/..."
    # The Cloud SQL service identity needs to be created first for IAM bindings
    # to stick. gcloud beta services identity create handles that idempotently.
    gcloud beta services identity create \
        --service=sqladmin.googleapis.com \
        --project="${PROJECT_ID}" 2>&1 | tail -3 || true

    gcloud storage buckets add-iam-policy-binding "gs://${bucket}" \
        --member="serviceAccount:${cloud_sql_sa}" \
        --role=roles/storage.objectAdmin \
        --quiet 2>&1 | tail -3

    echo
    echo "3) Updating GCS lifecycle rules (sql-dumps/ → 30d, raw/ → 730d)"
    # gcloud storage buckets update --lifecycle-file REPLACES the whole
    # bucket lifecycle config, so we must include every rule we want to
    # keep. The raw/ → 730d rule was originally set in setup_cloud_sql.sh
    # for parquet retention; mirroring it here preserves that policy
    # alongside the new sql-dumps/ → 30d rule. If gcp/setup_cloud_sql.sh
    # ever changes its rule definition, update this block to match.
    cat >/tmp/sql_dumps_lifecycle.json <<EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 30,
        "matchesPrefix": ["sql-dumps/"]
      }
    },
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 730,
        "matchesPrefix": ["raw/"]
      }
    }
  ]
}
EOF
    gcloud storage buckets update "gs://${bucket}" \
        --lifecycle-file=/tmp/sql_dumps_lifecycle.json \
        --quiet 2>&1 | tail -3
    rm -f /tmp/sql_dumps_lifecycle.json

    echo
    echo "✓ IAM + lifecycle configured. Test with:"
    echo "  gcloud run jobs execute cloud-sql-weekly-export --region ${REGION} --wait"
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update apply-schema-migrations \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,gcp.apply_schema" \
        ${DB_SECRET_FLAG} \
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
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update compute-spx-greeks-backfill \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,scripts.maintenance.compute_spx_greeks" \
        --args "--ticker,SPX" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet
}

# NOTE: Replay mode for the signal monitor is now built into the
# existing signal-monitor Cloud Run Job — no separate replay-signal-monitor
# job is needed. The job's main() in gcp/signal_monitor.py supports a
# --mode=replay flag that dispatches to scripts/replay_signal_monitor.py
# (the canonical hermetic harness). Replay activates automatically when
# REPLAY_DATE or REPLAY_TICKER env vars are set at execute time:
#
#   gcloud run jobs execute signal-monitor --region us-east1 \
#     --update-env-vars=REPLAY_DATE=2026-05-07,REPLAY_TICKER=SPY --wait
#
# The replay path mocks Discord webhook + DB writes (hermetic), so it's
# safe to run on the production job spec. Output is JSON-formatted alert
# fires in Cloud Logging textPayload. No rows written to signal_alerts;
# no Discord webhooks fired.
#
# Use cases:
#   1. Validate a fresh signal-monitor deploy against held-out data
#      BEFORE waiting for market open (Phase 0.5 spec item #8 —
#      live-vs-offline parity test).
#   2. Hermetic regression check after refactors that touch the
#      signal-fire path (e.g. the 2026-05-09 Track B end-to-end
#      validation).
#   3. What-if: tune assign_timeframe thresholds and replay to see how
#      the timeframe distribution shifts.


# ── Phase 0.6 — quarterly per-ticker threshold calibration ───────────────────
# Replaces the universal-across-tickers THRESHOLDS dict with per-ticker
# calibrated values from rolling 60-day bar history. See
# docs/plans/SIGNAL_QUALITY_TEST_PLAN.md §3.6 / Phase 0.6.
#
# Cadence: quarterly (1st of Jan / Apr / Jul / Oct) — see deploy_schedulers().
# Manual run any time: `gcloud run jobs execute calibrate-thresholds`.
deploy_calibrate_thresholds() {
    echo "Deploying calibrate-thresholds job..."
    gcloud run jobs create calibrate-thresholds \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 1Gi --cpu 1 --max-retries 1 --task-timeout 600 \
        --service-account "${SA_EMAIL}" \
        --command "python,-m,scripts.calibrate_thresholds" \
        ${DB_SECRET_FLAG} \
        --set-env-vars "$(_env_string)" \
        --quiet 2>/dev/null || \
    gcloud run jobs update calibrate-thresholds \
        --image "${IMAGE}" --region "${REGION}" \
        --command "python,-m,scripts.calibrate_thresholds" \
        ${DB_SECRET_FLAG} \
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

    # The failure-notifier posts to a DEDICATED Discord channel for GCP job
    # failures (secret `discord-webhook-gcp`), not `discord-webhook-insights`
    # that the rest of the platform uses for briefs/alerts. We also fold in the
    # GitHub PAT/repo secrets so a single --set-secrets flag carries every
    # secret-mounted env var (a second --set-secrets on the same gcloud invoke
    # replaces the first entirely, which previously masked the shared secrets).
    local notifier_secrets="${DB_SECRET_FLAG#--set-secrets=}"
    notifier_secrets="${notifier_secrets/discord-webhook-insights:latest/discord-webhook-gcp:latest}"
    notifier_secrets="${notifier_secrets},GITHUB_PAT=github-pat:latest,GITHUB_REPO=github-repo:latest"

    # 1) Deploy the Cloud Run service (overrides Dockerfile CMD with stdlib server)
    # Secrets are mounted from Secret Manager at runtime via --set-secrets so
    # they never appear in revision metadata (visible to anyone with run.services.get).
    gcloud run deploy "${NOTIFIER_SERVICE}" \
        --image "${IMAGE}" --region "${REGION}" \
        --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3 \
        --service-account "${SA_EMAIL}" \
        --command "python" --args "-m,gcp.failure_notifier" \
        --set-env-vars "${env_string}" \
        --set-secrets="${notifier_secrets}" \
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
    # Filter catches Cloud Run Job execution failures but excludes:
    #   1. the notifier itself (prevents infinite loops)
    #   2. Cloud Audit Logs (`cloudaudit.googleapis.com`) — every
    #      `gcloud run jobs update` triggers an ERROR-severity audit log
    #      because gcloud tries Jobs.CreateJob first (ALREADY_EXISTS at
    #      ERROR severity) and falls back to UpdateJob. Without the
    #      `logName:"run.googleapis.com"` clause, every deploy fired one
    #      false-positive notification per job. Real execution failures
    #      land on `run.googleapis.com/varlog/system` (task-failed
    #      records) and `run.googleapis.com/stderr` (container stack
    #      traces), both of which still match.
    local sink_filter
    sink_filter='resource.type="cloud_run_job"
AND severity>=ERROR
AND resource.labels.job_name!="'"${NOTIFIER_SERVICE}"'"
AND logName:"run.googleapis.com"'

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

# Variant of _schedule that injects BRIEF_TRIGGERED_BY=cloud-scheduler:<name>
# as a containerOverride env var on the Cloud Run Jobs ":run" body. Used by
# the premarket-brief schedulers so _resolve_run_kind_and_update classifies
# the run as 'scheduled' (not 'manual_replay') in premarket_analysis_history.
# Plain Cloud Scheduler triggers don't propagate any context to the Job; the
# job's persisted env is whatever was last set by a manual `gcloud run jobs
# execute --update-env-vars=...`, which silently corrupts the run-kind label.
_schedule_brief() {
    local NAME=$1 CRON=$2 JOB=$3
    local BODY='{"overrides":{"containerOverrides":[{"env":[{"name":"BRIEF_TRIGGERED_BY","value":"cloud-scheduler:'"${NAME}"'"}]}]}}'
    gcloud scheduler jobs create http "${NAME}" \
        --location "${REGION}" \
        --schedule "${CRON}" \
        --time-zone "America/New_York" \
        --uri "$(_job_uri "${JOB}")" \
        --http-method POST \
        --headers "Content-Type=application/json" \
        --message-body "${BODY}" \
        --oauth-service-account-email "${SA_EMAIL}" \
        --quiet 2>/dev/null || echo "  ${NAME}: already exists"
}

# Variant of _schedule that injects INSIGHT_TRIGGERED_BY=cloud-scheduler:<name>
# as a containerOverride env var on the insight-pipeline ":run" body. Mirrors
# _schedule_brief — without it, _resolve_update_mode_and_kind in
# gcp/insight_pipeline_job.py classifies every cron run as 'manual_replay' in
# insight_reports_history (issue #313 — audit 2026-05-09 found run_kind never
# saw 'scheduled' for 23 days).
_schedule_insight() {
    local NAME=$1 CRON=$2 JOB=$3
    local BODY='{"overrides":{"containerOverrides":[{"env":[{"name":"INSIGHT_TRIGGERED_BY","value":"cloud-scheduler:'"${NAME}"'"}]}]}}'
    # Idempotent: update if exists, create otherwise. Codex review on PR
    # #352 caught that create-only swallows ALREADY_EXISTS, so a re-deploy
    # against an existing scheduler keeps the OLD body and the new
    # INSIGHT_TRIGGERED_BY override never reaches production.
    if gcloud scheduler jobs describe "${NAME}" --location "${REGION}" --quiet 2>/dev/null >/dev/null; then
        gcloud scheduler jobs update http "${NAME}" \
            --location "${REGION}" \
            --schedule "${CRON}" \
            --time-zone "America/New_York" \
            --uri "$(_job_uri "${JOB}")" \
            --http-method POST \
            --update-headers "Content-Type=application/json" \
            --message-body "${BODY}" \
            --oauth-service-account-email "${SA_EMAIL}" \
            --quiet \
        && echo "  ${NAME}: updated"
    else
        gcloud scheduler jobs create http "${NAME}" \
            --location "${REGION}" \
            --schedule "${CRON}" \
            --time-zone "America/New_York" \
            --uri "$(_job_uri "${JOB}")" \
            --http-method POST \
            --headers "Content-Type=application/json" \
            --message-body "${BODY}" \
            --oauth-service-account-email "${SA_EMAIL}" \
            --quiet \
        && echo "  ${NAME}: created"
    fi
}

# Variant of _schedule that overrides the container command-line args via the
# Cloud Run Jobs ":run" body. Used to point a single signal-monitor job image
# at orb-snapshot or other one-shot modes.
_schedule_with_args() {
    local NAME=$1 CRON=$2 JOB=$3
    shift 3
    # Build JSON args array: ["--mode=orb-snapshot","--window=15m"]
    local ARGS_JSON='['
    local first=1
    for a in "$@"; do
        [ ${first} -eq 1 ] || ARGS_JSON+=','
        ARGS_JSON+='"'"${a}"'"'
        first=0
    done
    ARGS_JSON+=']'

    local BODY='{"overrides":{"containerOverrides":[{"args":'"${ARGS_JSON}"'}]}}'

    gcloud scheduler jobs create http "${NAME}" \
        --location "${REGION}" \
        --schedule "${CRON}" \
        --time-zone "America/New_York" \
        --uri "$(_job_uri "${JOB}")" \
        --http-method POST \
        --headers "Content-Type=application/json" \
        --message-body "${BODY}" \
        --oauth-service-account-email "${SA_EMAIL}" \
        --quiet 2>/dev/null || echo "  ${NAME}: already exists"
}

deploy_schedulers() {
    echo "Creating Cloud Scheduler triggers..."

    # Pre-market brief — 8:30 AM ET weekdays (today's earnings).
    # _schedule_brief (not _schedule) so BRIEF_TRIGGERED_BY=cloud-scheduler:<name>
    # is passed as a containerOverride env var on every trigger; without it the
    # brief misclassifies scheduled runs as manual_replay in history.
    _schedule_brief "premarket-brief-daily"    "30 8 * * 1-5"   "premarket-brief"
    # Pre-market brief — 9:00 AM ET Sundays (week-ahead earnings digest)
    _schedule_brief "premarket-brief-sunday"   "0 9 * * 0"      "premarket-brief"
    # Signal monitor — 9:25 AM ET weekdays (starts before open, exits at close)
    _schedule "signal-monitor-daily"     "25 9 * * 1-5"   "signal-monitor"
    # Signal monitor EOD resolver — 4:30 PM ET weekdays (30 min after close
    # so any late-arriving intraday bars are queryable). Sweeps any alerts
    # still is_open=TRUE or with exit_ts NULL and resolves them via the
    # gcp.signal_monitor_eod_resolver replay path. Per Track D G.P0.10.
    _schedule "signal-monitor-eod-resolver-daily" "30 16 * * 1-5"  "signal-monitor-eod-resolver"
    # Premarket brief-playbook outcome resolver — 4:30 PM ET weekdays.
    # Walks each (analysis_date, ticker) row's RTH 1-min bars and records
    # trigger_hit_ts / target_hit_ts / stop_hit_ts / reversal / MAE / MFE /
    # EOD pnl. Same wall-clock slot as the alerts resolver above
    # (different job, different table — no contention).
    _schedule "premarket-playbook-resolver-daily" "30 16 * * 1-5"  "premarket-playbook-resolver"
    # ORB scheduled snapshots — 9:45 ET (15-min ORB) and 10:00 ET (30-min ORB).
    # Uses the same signal-monitor job image with --mode=orb-snapshot.
    _schedule_with_args "orb-15m-alert"  "45 9 * * 1-5"  "signal-monitor" \
        "--mode=orb-snapshot" "--window=15m"
    _schedule_with_args "orb-30m-alert"  "0 10 * * 1-5"  "signal-monitor" \
        "--mode=orb-snapshot" "--window=30m"
    # Weekend review — Saturday 9 AM ET
    _schedule "weekend-review-weekly"    "0 9 * * 6"      "weekend-review"
    # Cloud SQL → GCS backup — Sunday 04:00 UTC (≈ 23:00 ET Saturday).
    # Off-hours so the optional offload export doesn't compete with any
    # weekend backfill jobs. Output: gs://${PROJECT_ID}-trading-data/
    # sql-dumps/trading-YYYYMMDD-HHMMSS.sql.gz. Lifecycle rule (set in
    # setup_pg_dump_iam) deletes dumps older than 30 days, leaving the
    # last ~4 weekly snapshots.
    _schedule "cloud-sql-weekly-export-sunday" "0 4 * * 0" "cloud-sql-weekly-export"
    # Market data — 11 PM ET weekdays. Was 5 PM ET originally but moved
    # 6 hours later because AV's TIME_SERIES_INTRADAY publishes the
    # closing-day's 1-min bars with a several-hour lag. The 5 PM cron
    # consistently saw "no bars for <ticker> on <today>" and required
    # a manual --date=YYYY-MM-DD backfill the following morning. 11 PM
    # ET (= 03:00 UTC next day) puts the fetch ~7 hours after the
    # 16:00 ET close, well beyond AV's typical ingestion window.
    _schedule "fetch-market-data-daily"  "0 23 * * 1-5"   "fetch-market-data"

    # AV HISTORICAL_OPTIONS — 1st of each month at 5:00 UTC (1 AM ET).
    # The job spec uses --from-latest, so each invocation queries
    # MAX(snapshot_date) from etf_options_snapshots and backfills from
    # there to today. On a healthy cadence this picks up ~22 trading
    # days × 4 tickers ≈ 88 AV calls (~35 sec at 150 RPM) once a month.
    # If the user wants daily freshness (rather than the once-a-month
    # roll-up), change to "0 5 * * *" — same args work because
    # --from-latest is self-resuming.
    _schedule "av-options-monthly"  "0 5 1 * *"  "fetch-av-options-backfill"
    # Live options queries beyond the last refresh continue to flow
    # through the OptionsFlowPage AV-fallback path; the SQL table is
    # the source of truth for historical analysis.

    # AlphaVantage monthly intraday — 1st of each month 9 PM ET
    _schedule "av-intraday-monthly"  "0 21 1 * *"  "fetch-alphavantage-intraday"

    # AlphaVantage nightly intraday — 9 PM ET Tue–Sat (after each weekday's
    # session settles). Tue 9 PM picks up Mon's bars, Sat 9 PM picks up Fri's.
    # Passes --force so the GCS parquet-exists short-circuit doesn't skip
    # the still-incomplete current month; the DB upsert is idempotent on
    # (ticker,interval,ts) so re-fetching is safe. The default date range
    # ("first of previous month → today") means each night re-fetches last
    # month too — that's ~26s of redundant AV calls per night, well below
    # the 150 RPM premium budget. Closes the month-end-to-1st-of-next-month
    # gap that left the table stale for fresh signal-quality analysis.
    _schedule_with_args "av-intraday-nightly"  "0 21 * * 2-6"  "fetch-alphavantage-intraday" \
        "--symbol=ALL" "--force"

    # FRED rates — 6:30 AM ET daily (after FRED's nightly publication ~04:30 UTC)
    _schedule "fred-rates-daily"  "30 6 * * *"  "fetch-fred-rates"

    # Economic events — 7 AM ET weekdays (before pre-market brief)
    _schedule "economic-events-daily"  "0 7 * * 1-5"  "fetch-economic-events"

    # Earnings calendar (UW + EW) — 7:15 AM ET weekdays
    _schedule "earnings-calendar-daily"  "15 7 * * 1-5"  "fetch-earnings-calendar"

    # Earnings history (AV EARNINGS, per-ticker quarterly EPS) — Sunday 6 AM ET.
    # Weekly cadence is enough since past quarters never change.
    _schedule "earnings-history-weekly"  "0 6 * * 0"  "fetch-earnings-history"

    # Compute earnings reactions — daily at 11 PM ET (after market
    # close + EW strike eval at 11 PM, so the latest market_data_daily
    # bars are settled). Daily cadence (not weekly) so:
    #   1. Tomorrow's BMO reporters always have fresh sustain stats
    #      from today's close
    #   2. Yesterday's AMC reporters get their D+1 reaction row populated
    #      the same evening, so the next-morning brief's conditional
    #      lean has fresh history including today's quarter
    #   3. New tickers in earnings_history (added by Sunday weekly
    #      fetch) get reaction rows within ≤1 day, not 7
    #
    # Cost: pure DB join, no external API. ~5 min for the full ~320
    # ticker universe. Recomputes idempotently — same row content,
    # only updated_at advances.
    _schedule "compute-earnings-reactions-daily"  "0 23 * * 1-5"  "compute-earnings-reactions"

    # Pre-market refresh — 8:20 AM ET, 10 min before the morning brief.
    # premarket-brief-daily (the Discord push) fires at 8:30 AM ET, so
    # this MUST run earlier or the brief reads NULL gap_pct for every
    # ticker. ~30s typical runtime for 50 tickers at 4 parallel workers.
    # Populates today's gap_pct / pre_high / pre_low / pre_vwap into
    # market_data_daily; the 11pm fetcher fills in regular-session OHLC.
    _schedule "premarket-refresh-daily"  "20 8 * * 1-5"  "fetch-premarket-refresh"

    # EW strike verdict evaluator — 11:00 PM ET. Earlier 5pm slot was
    # tried and produced unreliable bars (AV intraday hadn't fully
    # settled — borderline KEPT/ASSIGNED verdicts flipped on re-runs).
    # 11pm gives the full session 7 hours to settle and aligns with
    # fetch-market-data-daily so AV is already warmed up.
    _schedule "evaluate-ew-strikes-daily" "0 23 * * 1-5"  "evaluate-ew-strikes"

    # Phase 0.6 — per-ticker threshold calibration. Quarterly cadence
    # (1st of Jan / Apr / Jul / Oct at 02:00 ET). ATR / RVOL / RSI
    # distributions are slow-moving aggregates over a 60-day window;
    # weekly recalibration would be mostly noise. Manual override
    # always available: `gcloud run jobs execute calibrate-thresholds`.
    _schedule "calibrate-thresholds-quarterly" "0 2 1 1,4,7,10 *" "calibrate-thresholds"

    # Phase 0.5 — signal-quality report.
    # Hourly during market hours: --mode=rolling, incremental update of
    # signal_metrics as 60m/90m/120m/240m windows close out. Cron is
    # 14-20 UTC (10:00-16:00 ET in DST or 09:00-15:00 ET in standard
    # time; scheduler timezone is America/New_York so cron is read in
    # local time — 10-16 ET). 7 invocations per trading day.
    _schedule "signal-quality-report-hourly" \
        "0 10-16 * * 1-5" "signal-quality-report"

    # Nightly: --mode=historical promotes rolling 'pending' rows to
    # 'final'. Tue-Sat 01:00 ET so it runs AFTER historical-signals-
    # watchlist (which Cloud Scheduler doesn't have a strict ordering
    # for, but in practice the watchlist iterator finishes by 22:00 ET).
    # --lookback-days=2 covers any signal whose 240m (=4h) window
    # closed in the last day; 2 days is paranoid headroom against DST
    # edges and weekend gaps.
    _schedule_with_args "signal-quality-report-nightly" \
        "0 1 * * 2-6" "signal-quality-report" \
        "--mode=historical" "--lookback-days=2"

    # Phase 0.5 spec item #6 — clean-rate regression alarm.
    # Daily 02:00 ET, after the nightly historical run promotes rolling
    # rows to 'final'. Compares trailing-7d to prior-7d clean-rate;
    # alarms when delta < -3pp. Posts to SIGNAL_QA_WEBHOOK_URL and
    # exits non-zero on regression so the existing failure-notifier
    # creates a GitHub issue.
    _schedule "signal-quality-alarm-daily" \
        "0 2 * * 2-6" "signal-quality-alarm"

    # SEC EDGAR filings — 4 strategic slots that cover every consumer.
    # The brief (8:30) and insight pipeline (8:45) read from sec_filings
    # once each morning, so 0700 is the only feed that matters for the
    # morning workflow. The other three give the Catalysts page intra-day
    # freshness for users browsing during market hours plus a post-close
    # sweep for after-hours 8-Ks.
    #
    # History: this used to be 17 schedules every 30 min — see PR
    # cleanup that retired the redundant slots. The deletion loop below
    # is idempotent; once the obsolete jobs are gone, it's a no-op.
    _schedule "sec-filings-0700"  "0 7 * * 1-5"    "fetch-sec-filings"
    _schedule "sec-filings-1000"  "0 10 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1300"  "0 13 * * 1-5"   "fetch-sec-filings"
    _schedule "sec-filings-1700"  "0 17 * * 1-5"   "fetch-sec-filings"

    # One-shot cleanup of the 13 retired sec-filings schedules. Idempotent:
    # `gcloud scheduler jobs delete` returns non-zero when the job is
    # already gone, which we swallow with `|| true`. Safe to leave in
    # forever; consider removing this loop once a deploy or two has
    # confirmed all targets are gone in your environment.
    for OBSOLETE in \
        sec-filings-0930 sec-filings-1030 sec-filings-1100 \
        sec-filings-1130 sec-filings-1200 sec-filings-1230 \
        sec-filings-1330 sec-filings-1400 sec-filings-1430 \
        sec-filings-1500 sec-filings-1530 sec-filings-1600 \
        sec-filings-2000 ; do
        gcloud scheduler jobs delete "${OBSOLETE}" \
            --location "${REGION}" --quiet 2>/dev/null \
            && echo "  retired ${OBSOLETE}" \
            || true
    done

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
    # Use _schedule_insight (not _schedule) so INSIGHT_TRIGGERED_BY=
    # cloud-scheduler:insight-pipeline-daily is injected on every run.
    # Without that env var the job's _resolve_update_mode_and_kind
    # classifies the run as 'manual_replay' rather than 'scheduled' —
    # validated against insight_reports_history 2026-04-15..05-08 where
    # 0/470 rows had run_kind='scheduled' (issue #313).
    _schedule_insight "insight-pipeline-daily"   "45 8 * * 1-5"  "insight-pipeline"

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
    eod-resolver) build_image && deploy_signal_monitor_eod_resolver ;;
    playbook-resolver) build_image && deploy_premarket_playbook_resolver ;;
    weekend)     build_image && deploy_weekend ;;
    fetchers)    build_image && deploy_fetchers && backfill_watchlist ;;
    insights)    build_image && setup_insight_tasks_queue && deploy_insight_pipeline && deploy_insight_discord_push && deploy_historical_signals_watchlist && deploy_auto_refresh_top_n ;;
    schedulers)  deploy_schedulers ;;
    backfill)    shift; backfill_watchlist "$@" ;;
    apply-schema) build_image && deploy_apply_schema_migrations ;;
    pg-dump)      build_image && deploy_weekly_pg_dump ;;
    setup-pg-dump-iam) setup_pg_dump_iam ;;
    fred-rates)   build_image && deploy_fetch_fred_rates ;;
    spx-greeks)   build_image && deploy_compute_spx_greeks_backfill ;;
    calibrate)    build_image && deploy_calibrate_thresholds ;;
    signal-quality) build_image && deploy_signal_quality_report && deploy_signal_quality_alarm ;;
    setup-notifier-secrets) setup_notifier_secrets ;;
    notifier)    build_image && deploy_notifier ;;
    discord)     build_image && deploy_discord_interactions ;;
    all)
        build_image
        deploy_premarket
        deploy_monitor
        deploy_signal_monitor_eod_resolver
        deploy_premarket_playbook_resolver
        deploy_weekend
        deploy_fetchers
        setup_insight_tasks_queue
        deploy_insight_pipeline
        deploy_insight_discord_push
        deploy_historical_signals_watchlist
        deploy_auto_refresh_top_n
        deploy_signal_quality_report
        deploy_signal_quality_alarm
        deploy_weekly_pg_dump
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
        echo "  pg-dump    Deploy cloud-sql-weekly-export Cloud Run Job (full Postgres"
        echo "             dump → gs://\${PROJECT_ID}-trading-data/sql-dumps/). Wired"
        echo "             to Sunday 04:00 UTC scheduler in deploy_schedulers."
        echo "  setup-pg-dump-iam  One-time IAM grants for pg-dump: trading-runner gets"
        echo "             cloudsql.editor, Cloud SQL service identity gets storage"
        echo "             objectAdmin on the dump bucket, lifecycle rule sets 30d"
        echo "             retention on the sql-dumps/ prefix."
        echo "  fred-rates Deploy fetch-fred-rates job (DGS3MO daily into daily_rates)"
        echo "  spx-greeks Deploy one-shot SPX Greeks backfill job (12h timeout)"
        echo "             python -m scripts.maintenance.compute_spx_greeks --ticker SPX"
        echo ""
        echo "  Note: replay mode for the signal-monitor is built into the"
        echo "  existing signal-monitor job (gcp/signal_monitor.py main"
        echo "  --mode=replay). Override at execute time:"
        echo "    gcloud run jobs execute signal-monitor --wait \\"
        echo "      --update-env-vars=REPLAY_DATE=YYYY-MM-DD,REPLAY_TICKER=SPY"
        echo "  setup-notifier-secrets  One-time: store GitHub PAT + repo in Secret Manager"
        echo "  notifier   Deploy failure-notifier Cloud Run service + log sink"
        echo "  discord    Deploy discord-interactions Cloud Run service (slash commands)"
        echo "             Prereqs: discord-app-id, discord-public-key, discord-bot-token"
        echo "             secrets in Secret Manager. After deploy, set the service URL"
        echo "             as Discord's Interactions Endpoint URL and run"
        echo "             scripts/discord/register_commands.py."
        echo "  signal-quality"
        echo "             Deploy signal-quality-report (Phase 0.5 measurement)"
        echo "             + signal-quality-alarm (regression detector) jobs."
        echo "  all        Build + deploy everything (jobs + schedulers + backfill)"
        ;;
esac
