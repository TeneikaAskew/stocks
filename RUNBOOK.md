# Disaster Recovery Runbook

**Audience:** the one person operating this system, under pressure, at 3 AM. Practical not exhaustive.
**Last updated 2026-06-23** from `gcp/deploy.sh`, `platform/deploy.sh`, [ARCHITECTURE.md](ARCHITECTURE.md), and [DATA_DEPENDENCIES.md](DATA_DEPENDENCIES.md). Counts below were re-derived from `gcp/deploy.sh` + `gcp/schema.sql` at update time.

**Current scale (2026-06-23):** ~62 Cloud Run Jobs, ~77 Cloud Scheduler crons, 57 Cloud SQL tables, 3 Cloud Run Services (`trading-platform`, `discord-interactions`, `failure-notifier`) + an optional public `trading-platform-staging` service. The platform service is deployed by `platform/deploy.sh` (the GitHub-Actions deploy workflows were deleted); all jobs/schedulers by `gcp/deploy.sh`. Ad-hoc SQL goes through `scripts/db_query_cr.sh` (the `db-query.yml` GHA workflow was deleted — see §6).

---

## 1. RTO and RPO

These are derived from the actual backup config — `gcloud sql instances describe trading-db` reports `backupConfiguration: enabled=true, retainedBackups=7, startTime=03:00 UTC, transactionLogRetentionDays=7`. The bucket has no versioning. Read this section as **real numbers, not aspirational**.

| Layer | RTO (time-to-recover) | RPO (data loss tolerated) | Notes |
|---|---|---|---|
| **Cloud SQL `trading-db`** | 30-60 min | **~5 min** | PITR enabled (7d transaction log retention). Without PITR, RPO would be 24h (one daily backup). |
| **GCS `adept-mountain-474619-d4-trading-data`** | ∞ for missing data | ∞ | **No versioning, no backup.** Loss is permanent unless the file can be re-fetched from an external API (AlphaVantage daily/intraday only, no historical re-issue). |
| **Cloud Run Jobs (~62 jobs) + Schedulers (~77 crons)** | 60-90 min | n/a (stateless) | All recreatable from `gcp/deploy.sh all` + the targeted subcommands (the `all` bundle no longer deploys every job — research-image jobs like `strat-engine`, `magnitude-inference`, the `build-options-*` / `build-realtime-gex` jobs, and `db-query` / `freshness-watchdog` / `audit-*` are deployed via their own targets). Schedulers from `deploy.sh schedulers`. |
| **Cloud Run Services (3: trading-platform, discord-interactions, failure-notifier)** | 30 min | n/a | `discord-interactions` + `failure-notifier` via `gcp/deploy.sh`; **`trading-platform` via `platform/deploy.sh`** (behind IAP). Optional public `trading-platform-staging` also via `platform/deploy.sh` (`STAGING_SERVICE=1`). |
| **Secret Manager (~25 secrets)** | 1-4 hours **per secret you can't recover** | 100% loss for unrecoverable secrets | No automated backup. API keys must be re-issued from each provider (AV, FRED, Anthropic, Discord, GitHub PAT, Benzinga, etc.). DB passwords are internal — re-rotate via Cloud SQL. Newer secrets: `discord-webhook-signals`, `discord-webhook-earnings`, `gh-stocks-repo-pat`, the Firebase web-app config (`FIREBASE_API_KEY`/`FIREBASE_AUTH_DOMAIN`/`FIREBASE_APP_ID` — public identifiers, passed at deploy time, not stored as secrets), and `trading-db-pass` (the password the platform service reads; jobs read `db-trading-pass`). |
| **Whole-project rebuild** | 4-8 hours | Whatever Cloud SQL backup you can restore (≤ 7 days old) | Rebuild sequence in §4 below. |

**Bottom line:** the only piece with a real DR posture is Cloud SQL. Everything else is "redeploy from git + Secret Manager." If you lose **both** Cloud SQL **and** Secret Manager simultaneously, you're rebuilding from external API key reissuance — that's the long pole.

---

## 2. Failure scenarios

### 2.1 Cloud SQL instance down or corrupted

**Detection signal**
- Brief at 8:30 ET errors with `pg8000.exceptions.DatabaseError` in [premarket-brief logs](https://console.cloud.google.com/run/jobs/executions/details/us-east1/premarket-brief)
- FastAPI dashboard shows 500s on `/api/dashboard/brief/{ticker}`
- failure-notifier creates a GitHub issue (the log sink fires on `severity>=ERROR` from any Cloud Run Job)

**Immediate response (5 min)**
```bash
# Confirm instance state
gcloud sql instances describe trading-db --project=adept-mountain-474619-d4 \
  --format='value(state,settings.activationPolicy)'

# If state != RUNNABLE — investigate via Cloud Console → SQL → trading-db → Operations
# If RUNNABLE but unreachable — check Cloud SQL Auth Proxy connectivity from a Cloud Run Job
```

**Recovery — minor corruption (PITR within 7 days)**
```bash
# Pick the timestamp BEFORE the corruption (UTC, ISO-8601)
gcloud sql instances clone trading-db trading-db-recovered \
  --point-in-time=2026-05-02T05:00:00Z \
  --project=adept-mountain-474619-d4

# Validate the clone
gcloud sql instances describe trading-db-recovered

# Cut over: rename or update CLOUD_SQL_CONNECTION_NAME secret to point at the clone
gcloud secrets versions add cloud-sql-connection-name --data-file=- <<<"adept-mountain-474619-d4:us-east1:trading-db-recovered"

# Redeploy ALL jobs/services so they pick up the new secret value (env var is set at deploy time)
./gcp/deploy.sh all
```

**Recovery — full instance loss (restore from latest daily backup)**
```bash
# List backups (kept 7)
gcloud sql backups list --instance=trading-db --project=adept-mountain-474619-d4

# Restore (creates a new instance from the backup)
gcloud sql backups restore <BACKUP_ID> \
  --restore-instance=trading-db-restored \
  --backup-instance=trading-db \
  --project=adept-mountain-474619-d4

# Same cut-over flow as above
```

**Verification**
```bash
# Confirm row counts on the 5 critical tables haven't dropped
gcloud sql connect trading-db-recovered --user=trading_user --quiet <<EOF
SELECT 'market_data_daily' AS t, COUNT(*) FROM market_data_daily UNION ALL
SELECT 'market_data_intraday', COUNT(*) FROM market_data_intraday UNION ALL
SELECT 'earnings_calendar', COUNT(*) FROM earnings_calendar UNION ALL
SELECT 'insight_reports', COUNT(*) FROM insight_reports UNION ALL
SELECT 'historical_signals', COUNT(*) FROM historical_signals;
EOF

# Trigger a brief manually and confirm it posts to Discord
gcloud run jobs execute premarket-brief --region=us-east1 --wait
```

---

### 2.2 GCS bucket data loss

**Detection signal**
- `gs://adept-mountain-474619-d4-trading-data` returns 404 / empty listing
- Jobs that write parquet snapshots (`fetch_market_data`, `migrate_to_gcp`) emit warnings about missing prefixes

**Immediate response (10 min) — DON'T panic**
GCS is the **secondary** store. The canonical store is Cloud SQL. If the bucket is gone but Cloud SQL is intact, **the platform still functions** — only the historical parquet snapshots and Cloud Build sources are lost.

```bash
# Confirm bucket state
gcloud storage buckets describe gs://adept-mountain-474619-d4-trading-data 2>&1
gcloud storage ls gs://adept-mountain-474619-d4-trading-data | head

# Check if it's a permission issue vs. actual loss
gcloud storage buckets get-iam-policy gs://adept-mountain-474619-d4-trading-data
```

**Recovery**
> ⚠️ **There is no backup.** Versioning is OFF (verified `versioning_enabled=<empty>` from `gcloud storage buckets describe`). The 730-day lifecycle rule on `raw/` deletes content rather than archives it. **Whatever's gone is gone.**

If actual loss:
```bash
# Recreate the bucket
gcloud storage buckets create gs://adept-mountain-474619-d4-trading-data \
  --location=us-east1 --uniform-bucket-level-access

# Re-grant SA access
gcloud storage buckets add-iam-policy-binding gs://adept-mountain-474619-d4-trading-data \
  --member="serviceAccount:trading-system@adept-mountain-474619-d4.iam.gserviceaccount.com" \
  --role=roles/storage.objectAdmin

# Re-run migrate to repopulate from local parquet (if you still have a local copy)
./gcp/deploy.sh migrate
```

**Verification**
```bash
# Subsequent fetcher run should write parquet again
gcloud run jobs execute fetch-market-data --region=us-east1 --wait
gcloud storage ls gs://adept-mountain-474619-d4-trading-data/parquet/ | head
```

**Risk recommendation:** enable bucket versioning (`gcloud storage buckets update gs://... --versioning`) — adds ~$0.005/GB/month for a few cents/month and gives you 30-day soft-delete of accidentally-overwritten objects. See §5.

---

### 2.3 AlphaVantage API outage or rate limit

**Detection signal**
- `fetch_market_data` / `fetch_alphavantage_intraday` / `fetch_news_sentiment` exit with HTTP 429 or empty CSV body
- Per [DATA_DEPENDENCIES.md §6](DATA_DEPENDENCIES.md#6-blast-radius-per-cloud-run-job), `fetch-market-data` failure cascades to ~10 downstream consumers

**Immediate response (no automated mitigation)**
- Check status: AlphaVantage doesn't publish a public status page. Test directly:
  ```bash
  AV_KEY=$(gcloud secrets versions access latest --secret=av-api-key)
  curl -s "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey=$AV_KEY" | head -c 200
  ```
- A response containing `"Information"` or `"Note"` keys = rate-limited (free tier = 25/day, paid tier ~500/min)
- A response containing the actual quote = AV is up; problem is upstream

**Recovery — rate limit hit**
- **Wait.** Rate limit window resets within minutes (premium) or 24 hours (free).
- **Don't retry in a tight loop.** The fetchers all use `_safe_int` / `_safe_num` paths and don't retry on rate-limit; a tight retry loop is more likely to extend the rate-limit window than escape it.
- Consider stopping any active backfill jobs that are burning quota:
  ```bash
  gcloud run jobs executions list --job=fetch-market-data --limit=5 --filter='status.conditions.type=Completed AND status.conditions.status=Unknown'
  # Cancel any RUNNING execution that's burning quota
  gcloud run jobs executions delete <execution-name> --region=us-east1
  ```

**Recovery — AV outage**
- The pipeline degrades gracefully: `compute_earnings_reactions` and `evaluate_ew_strikes` read existing rows; the brief reads the most recent `market_data_daily` row even if today's didn't land.
- The `freshness-watchdog` Cloud Run Job (CR-native since 2026-05-30; the old `freshness-watchdog.yml` GHA workflow was retired) runs hourly 09:00-19:00 ET + nightly 19:30 ET and exits non-zero on any stale table, which the `failure-notifier` log sink turns into a Discord alert + GitHub issue.

**Verification**
```bash
# After AV recovers, manually re-trigger the failed scheduled jobs:
gcloud run jobs execute fetch-market-data --region=us-east1 --wait
# Then verify the row landed:
gcloud sql connect trading-db --user=trading_user --quiet <<<"SELECT MAX(date) FROM market_data_daily WHERE ticker='IWM';"
```

---

### 2.4 Discord webhook failure

**Detection signal**
- The 8:30 ET brief generates successfully (table is populated, `Persisted N rows...` in logs) but the post to Discord doesn't appear
- The `send_to_discord` function in [`gcp/premarket_brief.py`](gcp/premarket_brief.py) raises `requests.HTTPError` on the webhook POST
- failure-notifier may or may not catch it depending on whether the error becomes a non-zero exit

**Immediate response (5 min)**
- Test the webhook directly:
  ```bash
  WEBHOOK=$(gcloud secrets versions access latest --secret=discord-webhook-insights)
  curl -sS -X POST -H "Content-Type: application/json" \
    -d '{"content":"runbook test"}' "$WEBHOOK"
  ```
- If 401 / 404 — the webhook URL was deleted or rotated in Discord. Need a new one.
- If 429 — Discord rate-limited the channel; back off, retry in 5-10 min.

**Recovery**
1. Discord → Server Settings → Integrations → Webhooks → recreate the webhook
2. Update Secret Manager:
   ```bash
   echo -n "<new-webhook-url>" | gcloud secrets versions add discord-webhook-insights --data-file=-
   ```
3. Redeploy any job that bakes the webhook URL into env vars at deploy time. Per `gcp/deploy.sh`, the brief / monitor / insight-discord-push jobs all use `_env_string()` which captures the **current** secret value at deploy time:
   ```bash
   ./gcp/deploy.sh premarket
   ./gcp/deploy.sh monitor
   ./gcp/deploy.sh insights
   ```
4. ⚠️ **The discord-interactions Cloud Run Service uses `--set-secrets` (live secret reference)** so it does NOT need redeployment. Verify the difference per service before touching things.

**Verification**
```bash
# Trigger a brief and watch for Discord delivery
gcloud run jobs execute premarket-brief --region=us-east1 --wait
# Then confirm the embed landed in the Discord channel
```

---

### 2.5 Cloud Run Job stuck in failure loop

**Detection signal**
- failure-notifier opens repeated GitHub issues for the same job (label `gcp-job-failure`)
- `gcloud run jobs executions list --job=<NAME>` shows consecutive `Failed` executions
- Cloud Scheduler still fires (it's an HTTP trigger; it doesn't know the job's exit status)

**Immediate response (10 min)**
```bash
# Identify the failing job
gcloud run jobs executions list --region=us-east1 --filter='status.conditions.status=False' --limit=10 \
  --format='table(metadata.labels.run\.googleapis\.com/job,metadata.name,status.completionTime,status.conditions.message)'

# Pull the last failed execution's logs
gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=<NAME> AND severity>=ERROR' \
  --limit=20 --format='value(timestamp,textPayload)'
```

**Recovery — stop the bleeding (silence the cron loop while you fix it)**
```bash
# Pause the scheduler so it stops re-triggering
gcloud scheduler jobs pause <NAME>-daily --location=us-east1

# Fix the underlying issue — usually one of:
#   a) Code regression — git log + revert / forward-fix
#   b) Missing secret / env var — gcloud secrets list + check deploy.sh
#   c) Schema drift — gcloud sql connect + verify column shape
#   d) Image is stale — rebuild with `./gcp/deploy.sh build`

# Manually run the job to verify the fix
gcloud run jobs execute <NAME> --region=us-east1 --wait

# Resume the scheduler
gcloud scheduler jobs resume <NAME>-daily --location=us-east1
```

**Verification**
- Next scheduled execution must complete with `status.conditions.status=True`. Wait one cron cycle (typically <24h) before declaring it fixed.

---

### 2.6 Secret Manager secret rotated or deleted

**Detection signal**
- All Cloud Run Jobs deployed with `--set-secrets DB_PASS=db-trading-pass:latest` start failing with `password authentication failed for user "trading_user"`
- Or jobs deployed with `--set-env-vars` (a snapshot at deploy time) keep working until the next redeploy then fail

**Immediate response (5 min)**
```bash
# Confirm secret existence + version state
gcloud secrets list --filter='name~db-trading-pass'
gcloud secrets versions list db-trading-pass

# If the secret exists but the job's pinned version is destroyed:
gcloud secrets versions list db-trading-pass --filter='state=DESTROYED'
```

**Recovery — rotation forced (need new secret value)**
1. Rotate at the source (e.g., reset the Cloud SQL `trading_user` password):
   ```bash
   NEW_PASS=$(openssl rand -base64 32)
   gcloud sql users set-password trading_user --instance=trading-db --password="$NEW_PASS"
   echo -n "$NEW_PASS" | gcloud secrets versions add db-trading-pass --data-file=-
   ```
2. **All `--set-secrets`-deployed jobs auto-pick up `:latest`** — no redeploy needed for Cloud SQL pass since PR #170 standardized this.
3. **Jobs deployed with `--set-env-vars` (legacy)** — redeploy to bake the new value:
   ```bash
   ./gcp/deploy.sh all
   ```

**Recovery — secret deleted**
- If a secret is deleted (not rotated), `--set-secrets` references will start failing on the next job execution.
- Recreate from a known-good source (your password manager, the original vendor's credential portal, or `openssl rand` for self-issued):
  ```bash
  echo -n "<value>" | gcloud secrets create <name> --data-file=- --replication-policy=automatic
  ```
- For external API keys (AV, FRED, Anthropic, Discord, GitHub PAT) — these are **non-recoverable from GCP**. You must regenerate from the provider's portal.

**Verification**
```bash
gcloud run jobs execute premarket-brief --region=us-east1 --wait
gcloud logging read 'labels."run.googleapis.com/execution_name"=<exec-id> AND severity>=ERROR' --limit=5
```

---

### 2.7 Cloud Build push failure during deploy

**Detection signal**
- `./gcp/deploy.sh build` exits non-zero
- `gcloud builds list --limit=5` shows `STATUS: FAILURE` or `TIMEOUT`

**Immediate response (10 min)**
```bash
# Get the failed build's log URL
gcloud builds list --limit=3 --format='value(id,status,createTime,logUrl)'

# Pull the last 100 lines of the failed log
gcloud builds log <BUILD_ID> | tail -100
```

Common causes (in observed frequency):
1. **Docker image registry quota / permissions** — verify `roles/artifactregistry.writer` on the build service account
2. **Dockerfile pip-install failure** — package version conflict; check `requirements-gcp.txt` against published wheels
3. **Cloud Build timeout (default 60 min)** — large image rebuilds; bump `--timeout=20m` or trim base image
4. **Source bucket permission drift** — `adept-mountain-474619-d4_cloudbuild` bucket lost an IAM grant

**Recovery**
```bash
# Cancel hung builds first
gcloud builds cancel <BUILD_ID>

# Re-attempt with verbose output
./gcp/deploy.sh build 2>&1 | tee /tmp/build.log

# If pip-conflict — pin/unpin the offending package and retry
```

**Verification**
- Successful build emits `latest: digest: sha256:...` and `STATUS: SUCCESS` in the manifest line
- The next `gcloud run jobs execute <ANY_JOB>` should pull the new image (`:latest` is auto-resolved at execution start)

---

### 2.8 Full project loss (worst case: everything in GCP is gone)

**Detection signal**
- The project `adept-mountain-474619-d4` returns 404 / "not found" on `gcloud projects describe`
- Or: every resource you query returns "not found" — you're effectively rebuilding

**Immediate response (15 min)**
- Verify it's actual loss vs. an auth issue:
  ```bash
  gcloud auth list
  gcloud config list
  gcloud projects describe adept-mountain-474619-d4
  ```
- If real loss — read §4 (Rebuild from scratch). The flow takes 4-8 hours assuming external API keys can be re-issued.

**Critical: the GitHub repo is the source of truth.** Everything in `gcp/`, `lib/`, `scripts/`, `platform/` is recoverable. The `gcp/schema.sql` recreates every Cloud SQL table (idempotent). The Discord webhook URLs are rotatable. The Cloud SQL **data** is the only piece you can't rebuild — see §4 step 11 for the data-recovery options.

---

## 3. Backup posture audit

| Resource | Backup mechanism | Verified restorable? | Status |
|---|---|---|---|
| **Cloud SQL `trading-db`** | Daily automated backups @ 03:00 UTC, 7-backup retention; transaction log retention 7d enables PITR | ❌ Never tested | ⚠️ **Backups exist but no rehearsed restore.** Worth a one-time `gcloud sql backups restore` to a `-test` instance to validate. |
| **GCS `adept-mountain-474619-d4-trading-data`** | None — versioning OFF; 730-day delete lifecycle on `raw/` | n/a | 🔴 **No backup.** Risk-low (Cloud SQL is canonical), but if a fetcher ever writes corrupted parquet on top of good parquet, the good copy is gone. **Recommend: enable versioning.** |
| **GCS `adept-mountain-474619-d4_cloudbuild`** | Auto-managed by Cloud Build (24h source retention) | n/a | 🟢 OK — the source tarballs aren't worth backing up; Cloud Build auto-prunes anyway. |
| **Secret Manager (~25 secrets)** | None at the Secret Manager level | n/a | ⚠️ **No automated backup.** Internal secrets (DB pass, admin token) can be re-generated. External secrets (AV, FRED, Anthropic, Discord webhooks [insights/signals/earnings/gcp], GitHub PAT [`gh-stocks-repo-pat`], EW user/pass, Benzinga, sec-user-agent, Firebase web config) **must be re-issued from each provider** — this is the long pole on whole-project rebuild. **Recommend: print or 1Password-archive the values you can't easily re-issue.** |
| **Container images (Artifact Registry)** | None — no retention policy on `trading/trading-system` | n/a | 🟢 OK — `./gcp/deploy.sh build` rebuilds from current source in ~3 min. Old images aren't load-bearing for DR. |
| **Cloud Run Jobs (~62) / Services (3 + staging)** | Config in `gcp/deploy.sh` (jobs + `discord-interactions` + `failure-notifier`) and `platform/deploy.sh` (`trading-platform` + staging) (git) | ✅ Implicitly tested every time we deploy | 🟢 OK — `deploy.sh all` + the per-target subcommands recreate the jobs; `platform/deploy.sh` recreates the platform service. |
| **Cloud Scheduler (~77 crons)** | Config in `gcp/deploy.sh::deploy_schedulers` (git) | ✅ Implicitly tested | 🟢 OK — `deploy.sh schedulers` recreates from scratch. The ~77 includes two hourly loops (`news-sentiment-{08..17}00` ×10 and `news-topics-{08..17}05` ×10). |
| **Pub/Sub (`gcp-job-failures` + DLQ)** | Topics auto-recreated by `deploy.sh` (no message retention beyond default 7d) | n/a | 🟢 OK — topics are config; messages are ephemeral. |
| **Log sink (`gcp-job-failures-sink`)** | Created by `setup_notifier_secrets` in deploy.sh | ✅ | 🟢 OK |
| **Code (this repo)** | GitHub | ✅ Tested with every clone | 🟢 OK |

**Backup gaps ranked by risk:**

1. 🔴 **Secret Manager external API keys** — single source of truth is GCP; if that's gone, you're calling AV/FRED/Anthropic support to re-issue.
2. 🔴 **GCS bucket versioning OFF** — a bad parquet write silently overwrites a good one, no recovery.
3. ⚠️ **Cloud SQL backup never restore-tested** — backups exist but there's no evidence the restore path works. Should validate annually.

---

## 4. Rebuild from scratch

Numbered sequence to recreate the entire project from a clean slate, given (a) the GitHub repo, (b) the external API keys you can re-issue, (c) a Google account with billing.

```bash
# === Step 1: Create the GCP project ===
gcloud projects create adept-mountain-474619-d4 --name="Trading System"
gcloud config set project adept-mountain-474619-d4
gcloud beta billing projects link adept-mountain-474619-d4 \
    --billing-account=<YOUR_BILLING_ACCOUNT_ID>

# === Step 2: Enable APIs ===
gcloud services enable sqladmin.googleapis.com run.googleapis.com \
    cloudbuild.googleapis.com cloudscheduler.googleapis.com \
    secretmanager.googleapis.com artifactregistry.googleapis.com \
    storage.googleapis.com cloudtasks.googleapis.com pubsub.googleapis.com \
    logging.googleapis.com iam.googleapis.com aiplatform.googleapis.com

# === Step 3: Create service account ===
gcloud iam service-accounts create trading-system \
    --display-name="Trading System Runner"
SA_EMAIL=trading-system@adept-mountain-474619-d4.iam.gserviceaccount.com
for ROLE in roles/cloudsql.client roles/storage.objectAdmin \
            roles/secretmanager.secretAccessor roles/run.invoker \
            roles/cloudtasks.enqueuer roles/aiplatform.user; do
    gcloud projects add-iam-policy-binding adept-mountain-474619-d4 \
        --member="serviceAccount:${SA_EMAIL}" --role="${ROLE}"
done

# === Step 4: Provision Cloud SQL ===
./gcp/setup_cloud_sql.sh   # called by deploy.sh setup
# This creates: trading-db (POSTGRES_15, db-g1-small, us-east1-c),
# database 'trading', user 'trading_user' with auto-generated pass,
# stores DB_PASS in Secret Manager.
./gcp/deploy.sh setup

# === Step 5: Apply schema ===
./gcp/deploy.sh apply-schema   # idempotent — every CREATE is IF NOT EXISTS

# === Step 6: Create the trading-data bucket ===
gcloud storage buckets create gs://adept-mountain-474619-d4-trading-data \
    --location=us-east1 --uniform-bucket-level-access

# === Step 7: Re-issue + store external API secrets ===
# This is the LONG POLE. For each, get the value from the provider's portal:
#   - av-api-key (alphavantage.co)
#   - fred-api-key (research.stlouisfed.org)
#   - ew-user / ew-pass (earningswhispers.com)
#   - benzinga-api-key (benzinga.com)
#   - sec-user-agent (your email — required by SEC)
#   - github-pat / gh-stocks-repo-pat (github.com/settings/tokens)
#   - discord-webhook-insights (main briefs/insights channel; the default fallback)
#   - discord-webhook-signals (signals channel: signal_monitor entries/exits/ORB,
#                              EOD resolver, signal-quality jobs; falls back to insights)
#   - discord-webhook-earnings (earnings channel: earnings embeds; falls back to insights)
#   - discord-webhook-gcp (dedicated GCP-errors channel used by failure-notifier)
#   - discord-bot-token / discord-public-key / discord-app-id (Discord Developer Portal)
#   - admin-token (generate fresh: openssl rand -base64 32)
# For each, store via:
echo -n "<value>" | gcloud secrets create <name> --data-file=- --replication-policy=automatic

# === Step 8: Build the image ===
./gcp/deploy.sh build

# === Step 9: Deploy everything in the `all` bundle ===
./gcp/deploy.sh all
# `all` builds the main image then deploys the core daily pipeline:
# premarket-brief, earnings-reactions-brief, signal-monitor,
# signal-monitor-eod-resolver, premarket-playbook-resolver, weekend-review,
# the fetchers, the insight stack (pipeline + discord-push + historical-signals
# + auto-refresh-top-n), signal-quality-report/alarm, signal-replay,
# indicator-correlation, cloud-sql-weekly-export, failure-notifier, and ALL
# schedulers + the watchlist backfill.

# === Step 10: Deploy the jobs NOT in `all` ===
# The research-image + GHA-migration jobs have their own targets. Build the
# research image once, then deploy each:
./gcp/deploy.sh build-research          # research image (lightgbm/sklearn/scipy/shap)
./gcp/deploy.sh strat-engine            # strat directionality engine (replaces P7b)
./gcp/deploy.sh magnitude-inference     # daily magnitude predictions (builds research image)
./gcp/deploy.sh build-options-greeks    # etf_options_daily_greeks (gamma-levels)
./gcp/deploy.sh build-options-daily-features  # options_daily_features
./gcp/deploy.sh build-realtime-gex      # realtime_gex_15m
./gcp/deploy.sh options-retention       # etf-options-retention (30-day REALTIME prune)
./gcp/deploy.sh refresh-earnings-views  # earnings mat-views
./gcp/deploy.sh db-query                # CR-native ad-hoc SQL job (backs db_query_cr.sh)
./gcp/deploy.sh freshness-watchdog      # CR-native freshness watchdog
./gcp/deploy.sh audit-infra-drift       # daily infra-drift detector
./gcp/deploy.sh audit-walkforward       # weekly walk-forward audit
./gcp/deploy.sh audit-brief-bias        # weekly brief-bias audit
./gcp/deploy.sh regime-combo            # regime combo miner (research image)
# fetch-av-options-realtime is deployed by `./gcp/deploy.sh fetchers`.
# NOTE: gamma-levels-daily scheduler targets a `p2-build-gamma-levels` job —
# verify that job exists before relying on the 22:30 ET gamma refresh.

# === Step 10b: Deploy the platform service (NOT in gcp/deploy.sh) ===
./gcp/deploy.sh discord    # discord-interactions Cloud Run Service (slash commands)
                           # Then point Discord's Interactions Endpoint URL at the new
                           # service URL and run scripts/discord/register_commands.py
# The trading-platform Cloud Run service is deployed separately (behind IAP):
export DB_USER=postgres DB_NAME=trading
./platform/deploy.sh                          # prod (trading-platform, IAP, AUTH_MODE=iap)
# Optional public staging service (no IAP, Firebase login gates the API):
#   FIREBASE_API_KEY=… FIREBASE_AUTH_DOMAIN=… FIREBASE_APP_ID=… \
#     STAGING_SERVICE=1 ./platform/deploy.sh
# See §7 (Auth + platform deploy) for the AUTH_MODE / Firebase details.

# === Step 11: Restore data (if Cloud SQL backup is recoverable) ===
# If you had a Cloud SQL export (sqldump) in another project / off-cloud:
gcloud sql import sql trading-db gs://<recovery-bucket>/trading-db.sql \
    --database=trading --user=postgres
# Otherwise: cold-start the data layer by triggering each fetcher manually:
for JOB in fetch-market-data fetch-fred-rates fetch-economic-events \
           fetch-earnings-calendar fetch-earnings-history fetch-sec-filings \
           fetch-insider-transactions fetch-top-movers fetch-news-sentiment; do
    gcloud run jobs execute $JOB --region=us-east1 --wait
done
# Note: AlphaVantage history goes back ~10 years for daily, ~2 years for intraday.
# Older data is unrecoverable from the API.

# === Step 12: Verify ===
gcloud run jobs execute premarket-brief --region=us-east1 --wait
# Confirm Discord delivery + dashboard at the service URL.
```

**Realistic timing:** Steps 1-10 ~2 hours of `gcloud` time. Step 7 (secret re-issuance) is the variable — could be 1 hour if your password manager has them all, could be a full day if you have to email AV support. Step 11 cold-start data backfill takes ~2-4 hours of API quota burn.

---

## 5. Monitoring gaps

Things that could fail silently today because nothing watches them. Ranked by silent-failure cost.

1. **🔴 Insight pipeline showing $0.00 Vertex AI / Gemini cost over 90 days.** Per [COST_ANALYSIS.md §4B](COST_ANALYSIS.md), the active Gemini model (`gemini-3.1-flash-lite` as of 2026-05-11) has paid pricing per token (no zero-cost tier). $0 means either (a) no rounding above sub-cent, or (b) the pipeline isn't actually invoking Gemini. **No alarm watches "is insight-pipeline producing output."** A failure here is invisible from billing and from Discord (the brief still posts; only the insight digest goes silent).
   - **Fix:** add a `signal-quality-alarm`-style daily check that queries `SELECT COUNT(*) FROM insight_reports WHERE as_of >= CURRENT_DATE - INTERVAL '1 day'` and posts to Discord if 0.

2. **🔴 `ticker_calibration` written but never read.** Per [DATA_DEPENDENCIES.md §5](DATA_DEPENDENCIES.md), `scripts/calibrate_thresholds.py` writes the table; `lib/strategies/config.py` documents reading it but still hardcodes thresholds. **Calibration could be silently broken for months** and nobody would notice because nothing reads the output.
   - **Fix:** either wire `lib/strategies/config.py` to query the table, or stop running the calibrate job.

3. **⚠️ Cloud SQL backup restore is never tested.** Backups run nightly; no evidence the restore path actually works. Cloud SQL has been known to silently produce backups that fail to restore due to extension version mismatches.
   - **Fix:** annual `gcloud sql backups restore` to a `-test` instance, then `DROP` it. ~30 min of operator time.

4. **⚠️ GCS bucket has no versioning.** A bad parquet write silently corrupts a good one, no recovery.
   - **Fix:** `gcloud storage buckets update gs://... --versioning` — pennies/month.

5. **⚠️ External secrets have no documented inventory or backup.** If Secret Manager is wiped, you don't know which secrets you needed to re-issue. The list in §3 above is the only inventory; it lives in this runbook.
   - **Fix:** export to 1Password (or any password manager that's not GCP) on rotation.

6. **⚠️ Cloud Scheduler re-fires HTTP triggers regardless of job exit status.** If `fetch-market-data` fails 5 days in a row, Cloud Scheduler doesn't know; it just keeps firing. The failure-notifier catches the per-execution ERROR but doesn't escalate consecutive failures.
   - **Fix:** the `signal-quality-alarm` pattern (compare yesterday vs. today, exit non-zero on regression) could be templated for any data-freshness check.

7. **⚠️ `fetch-earnings-options` Cloud Run Job confirmed missing** (per [DATA_DEPENDENCIES.md §5](DATA_DEPENDENCIES.md) and the recently-merged drift PR). Nothing watches whether `earnings_options_snapshots` is fresh because the writer doesn't exist.
   - **Fix:** decide — rebuild the fetcher or drop the table.

8. **⚠️ The `premarket_analysis_history` and `insight_reports_history` tables are write-only.** They exist for "compliance / replay" but no consumer reads them. If they accumulate forever (no retention policy), the small Postgres instance will eventually run out of disk.
   - **Fix:** add a quarterly cleanup job that deletes rows older than 90 days, OR move them to a partitioned table with auto-drop, OR if no replay use case ever materializes, drop the tables.

---

## 6. Database access (the only supported path)

Direct Postgres (5432) and Auth-Proxy (3307) connections are blocked from the
Claude-Code-on-web sandbox (egress is 443-only). The supported ad-hoc SQL path
is the **`db-query` Cloud Run Job**, driven by `scripts/db_query_cr.sh`:

```bash
./scripts/db_query_cr.sh -q "SELECT count(*) FROM signal_alerts WHERE alert_date = current_date"
./scripts/db_query_cr.sh -f gcp/queries/check_daily_rates_nulls.sql        # file = ONE statement
./scripts/db_query_cr.sh -q "UPDATE x SET y=1 WHERE z=2" --commit          # writes need --commit
```

The dispatch travels over 443 (Cloud Run control plane); the SQL runs inside GCP
with full Cloud SQL access; results land in
`gs://${PROJECT_ID}-trading-data/query-results/${EXEC_NAME}/` and the dispatcher
prints `summary.md`. Default is **rollback** — a write without `--commit` is a
deliberate no-op. The old `.github/workflows/db-query.yml` GHA workflow was
**deleted 2026-05-30**; do not look for it. Redeploy the job with
`./gcp/deploy.sh db-query` if it's missing.

---

## 7. Auth + platform deploy

The platform service is now access-controlled (the doc previously said "no
auth"). `platform/api/auth.py` implements an `AUTH_MODE` middleware with three
modes:

| `AUTH_MODE` | Where used | Identity source |
|---|---|---|
| `iap` | **prod today** (`trading-platform`) | IAP `X-Goog-Authenticated-User-Email` header |
| `firebase` | public staging (`trading-platform-staging`) | Firebase ID token (`Authorization: Bearer`) verified per gated `/api/*` request |
| `open` | local dev | no-op |

- Pre-auth (always reachable) prefixes: `/api/health`, `/api/me`, `/api/config/firebase`.
- Invalid token → 401; disallowed account → 403 (fail-closed).
- Allow policy: open self-signup (`AUTH_OPEN_SIGNUP=1`, the default) or an
  allow-list (`AUTH_OPEN_SIGNUP=0` + `AUTH_ALLOWED_EMAILS=a@x.com,b@y.com`).

**Deploy commands** (`platform/deploy.sh`, run from repo root with `DB_USER` /
`DB_NAME` exported):

```bash
# Prod — trading-platform, behind IAP, AUTH_MODE=iap (default)
./platform/deploy.sh

# Prod service, new revision tagged `staging`, NO traffic (shares prod IAP)
STAGING=1 ./platform/deploy.sh
#   promote later: gcloud run services update-traffic trading-platform \
#       --region us-east1 --to-tags=staging=100

# SEPARATE public staging service — no IAP, Firebase login gates the API
FIREBASE_API_KEY=… FIREBASE_AUTH_DOMAIN=… FIREBASE_APP_ID=… \
  STAGING_SERVICE=1 ./platform/deploy.sh
```

The staging service (`trading-platform-staging`) is `--allow-unauthenticated`
(so the login page loads) but `AUTH_MODE=firebase` re-protects every gated
`/api/*` call. The Firebase web-app config (`FIREBASE_API_KEY` /
`FIREBASE_AUTH_DOMAIN` / `FIREBASE_APP_ID`) is REQUIRED for a firebase deploy —
these are public identifiers (access is enforced server-side by token
verification), passed via env at deploy time, not stored as Secret Manager
secrets. Service account: `trading-platform-svc@`. Image:
`gcr.io/${PROJECT_ID}/trading-platform`. Resource: 2Gi / 1 CPU, min-instances 0,
max 5, 300s timeout.

**Status (2026-06-23):** Firebase is live on the staging service; **prod is
still on IAP** — GCIP `authorizedDomains` lacks the prod domain and prod
`AUTH_MODE` has not been flipped to `firebase` (intentional until the frontend
login + domain are wired). Per-user journal scoping is shipped
(`journal_entries.user_email`); the insights Watchlist tab is **not** per-user
yet (shared `watchlists.user_id='default'`).

---

## 8. Feature flags (env-var, read at call-time)

Three flags are read from Cloud Run env at request/run time. Flip them by
updating the env var on the relevant service/job — no code change:

| Flag | Default | Effect | Flip on |
|---|---|---|---|
| `MOVEMENT_STATEMENT_ENABLED` | OFF | Exposes `/api/movement-statement` + the Dashboard "Movement Read" card (else 404 / hidden) | platform service |
| `STRUCTURE_CONTINUATION_MODEL_ENABLED` | OFF | Enables the structure-continuation model behind the movement statement | platform service (+ any job computing it) |
| `RECOMMEND_LONG_ONLY` | `true` | Morning brief recommends LONG STRADDLE/CALL/PUT/SKIP instead of iron condors | set in `gcp/deploy.sh::_env_string` (every job) |

```bash
# Enable the movement-statement surface on the platform service:
gcloud run services update trading-platform --region us-east1 \
  --update-env-vars MOVEMENT_STATEMENT_ENABLED=true,STRUCTURE_CONTINUATION_MODEL_ENABLED=true

# Revert to iron-condor brief recommendations (default is long-only):
gcloud run jobs update premarket-brief --region us-east1 \
  --update-env-vars RECOMMEND_LONG_ONLY=false
```

`RECOMMEND_LONG_ONLY` is baked by `_env_string()` into every job at deploy time;
to change it persistently, edit `gcp/deploy.sh` and redeploy rather than
patching one job. Movement-statement cells are limited to IWM/SPY/QQQ on 5m/15m
(never 30m).

---

## Final operator checklist (laminate this)

When something breaks at 3 AM, the order is:
1. **Check failure-notifier GitHub issues** — they have the run URL and last 50 lines of error logs
2. **Identify the table that's stale** — `SELECT MAX(<date_col>) FROM <table>` for the table the broken brief / page reads
3. **Walk the blast radius** — [DATA_DEPENDENCIES.md §6](DATA_DEPENDENCIES.md) tells you what else is affected
4. **Pause schedulers if a job is in failure loop** — `gcloud scheduler jobs pause <NAME>`
5. **Fix the root cause** — code regression / secret rotation / schema drift
6. **Manually run the job** — `gcloud run jobs execute <NAME> --wait` before resuming the cron
7. **Resume schedulers** — `gcloud scheduler jobs resume <NAME>`
8. **Open a postmortem** — `docs/incidents/<date>-<title>.md` with what broke, what you did, and what to monitor next time
