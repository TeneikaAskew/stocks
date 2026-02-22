# GCP Implementation Status Tracker

**Project**: adept-mountain-474619-d4
**Region**: us-east1
**Service Account**: trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com
**Last Updated**: 2026-02-22

---

## Phase 1: Infrastructure Setup

### GCP Project & APIs
- [x] GCP project selected: `adept-mountain-474619-d4`
- [x] `gcloud` CLI installed and authenticated
- [x] `setup_cloud_sql.sh` script written (`gcp/setup_cloud_sql.sh`)
- [x] Enable required GCP APIs ✅ 2026-02-22
  - [x] `sqladmin.googleapis.com` — Cloud SQL Admin
  - [x] `run.googleapis.com` — Cloud Run
  - [x] `cloudscheduler.googleapis.com` — Cloud Scheduler
  - [x] `secretmanager.googleapis.com` — Secret Manager
  - [x] `artifactregistry.googleapis.com` — Artifact Registry
  - [x] `cloudbuild.googleapis.com` — Cloud Build
  - [x] `storage.googleapis.com` — Cloud Storage
  - [x] `iam.googleapis.com` — Identity & Access Management
  - [x] `iamcredentials.googleapis.com` — IAM Service Account Credentials
  - [x] `logging.googleapis.com` — Cloud Logging
  - [x] `monitoring.googleapis.com` — Cloud Monitoring

### Service Account & IAM
- [x] Service account name defined: `trading-runner`
- [x] Service account created with required roles ✅ 2026-02-22
  - [x] `roles/cloudsql.client`
  - [x] `roles/storage.objectAdmin`
  - [x] `roles/secretmanager.secretAccessor`
  - [x] `roles/run.invoker`

### Artifact Registry
- [x] Repository created: `trading` in `us-east1` ✅ 2026-02-22
  - Image path: `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system`

### Cloud Storage
- [x] Bucket created: `adept-mountain-474619-d4-trading-data` ✅ 2026-02-22
- [x] Lifecycle policy: delete `raw/` objects after 730 days

### Cloud SQL
- [x] PostgreSQL 15 instance created: `trading-db` (db-g1-small, 20GB) ✅ 2026-02-22
  - Public IP: `34.24.66.12` | Region: `us-east1-c` | Status: RUNNABLE
- [x] Database `trading` created
- [x] User `trading_user` created
- [x] Password stored in Secret Manager as `db-trading-pass`
- [x] Schema applied (`gcp/schema.sql`) ✅ 2026-02-22
  - [x] `market_data_daily` table (+ auto-update trigger)
  - [x] `market_data_intraday` table (partitioned by ticker, PK fixed for pg15)
    - [x] Partition: `market_data_intraday_spy`
    - [x] Partition: `market_data_intraday_iwm`
    - [x] Partition: `market_data_intraday_qqq`
    - [x] Partition: `market_data_intraday_spx`
    - [x] Partition: `market_data_intraday_other`
  - [x] `etf_options_snapshots` table
  - [x] `earnings_options_snapshots` table
  - [x] `signal_alerts` table
  - [x] `trades` table
  - [x] `premarket_analysis` table
  - [x] `economic_events` table
  - [x] All indexes created (6 indexes)
- **Note:** `gcp/schema.sql` patched — removed `id BIGSERIAL PRIMARY KEY` from `market_data_intraday`; PK is now `(ticker, interval, ts)` (required for PostgreSQL LIST partitioning).

### Secret Manager
- [x] `cloud-sql-connection-name` = `adept-mountain-474619-d4:us-east1:trading-db` ✅
- [x] `db-trading-user` = `trading_user` ✅
- [x] `db-trading-pass` = (generated, stored) ✅
- [x] `gcs-trading-bucket` = `adept-mountain-474619-d4-trading-data` ✅
- [x] `av-api-key` = (from .env `ALPHA_VANTAGE_API_KEY`) ✅
- [x] `discord-webhook` = **PLACEHOLDER** ⚠️ — update with real URL:
  ```bash
  echo -n 'https://discord.com/api/webhooks/YOUR_ID/TOKEN' | \
    gcloud secrets versions add discord-webhook --data-file=-
  ```

---

## Phase 2: Code Implementation

### Core Library Changes
- [x] `lib/data_loader.py` — Added Cloud SQL backend
  - [x] `_cloud_sql_active()` helper
  - [x] `_query_cloud_sql()` helper
  - [x] `load_intraday()` — Priority 0: Cloud SQL
  - [x] `_load_intraday_from_sql()` — Parameterized query
  - [x] `load_daily()` — Cloud SQL path added
  - [x] `_load_daily_from_sql()` — Maps SQL cols to canonical names
  - [x] `load_options()` — New: queries etf/earnings options tables
  - [x] `load_trades()` — New: queries trades table
  - [x] Zero breaking changes (env-var-gated, Parquet fallback preserved)

- [x] `gcp/trade_logger.py` — Added Cloud SQL write path
  - [x] `log_trade()` — Upserts to Cloud SQL + Parquet fallback
  - [x] `get_daily_trades()` — Cloud SQL first, Parquet fallback
  - [x] `get_weekly_trades()` — Cloud SQL date range query
  - [x] `get_all_trades()` — Full query with fallback

### GCP Modules
- [x] `gcp/database.py` — Cloud SQL connection pool utilities
  - [x] `is_cloud_sql_configured()`
  - [x] `get_engine()` — SQLAlchemy singleton
  - [x] `upsert_dataframe()` — ON CONFLICT DO UPDATE
  - [x] `bulk_insert_dataframe()` — Fast bulk inserts
  - [x] `query_to_dataframe()` — SELECT → DataFrame
  - [x] `execute_sql()` — Non-SELECT statements

- [x] `gcp/gcs_utils.py` — GCS helpers
  - [x] `upload_dataframe_as_parquet()`
  - [x] `parquet_exists_in_gcs()`
  - [x] `download_csv_from_gcs()`
  - [x] `download_parquet_from_gcs()`
  - [x] `list_blobs()`

- [x] `gcp/schema.sql` — PostgreSQL 15 schema (8 tables)

- [x] `gcp/migrate_to_gcp.py` — Parquet → GCS + Cloud SQL migration
  - [x] `upload_raw_parquets()` — All Parquet → GCS raw/
  - [x] `migrate_market_data_daily()` — Daily OHLCV + indicators
  - [x] `migrate_market_data_intraday()` — 1-min bars (chunked)
  - [x] `migrate_etf_options()` — ETF options snapshots
  - [x] `migrate_earnings_options()` — Earnings options
  - [x] `migrate_trades()` — Trade log

### Cloud Run Fetchers
- [x] `gcp/fetchers/__init__.py`
- [x] `gcp/fetchers/fetch_market_data.py` — Replaces `fetch-market-data.yml`
  - [x] yfinance 1-min → daily OHLCV + indicators
  - [x] Writes to `market_data_daily`, `market_data_intraday`, GCS
- [x] `gcp/fetchers/fetch_etf_options.py` — Replaces `fetch_etf_options.yml`
  - [x] yahooquery options chain + Greeks
  - [x] Market session classification
  - [x] Writes to `etf_options_snapshots`, GCS
- [x] `gcp/fetchers/fetch_earnings_options.py` — Replaces `fetch-earnings-options.yml`
  - [x] Active tickers from GCS strategy CSVs
  - [x] Batch processing (10 tickers/batch)
  - [x] Writes to `earnings_options_snapshots`, GCS
- [x] `gcp/fetchers/fetch_alphavantage_intraday.py` — Replaces `fetch-alphavantage-intraday-monthly.yml`
  - [x] 5-key rotation, 13s rate limiting
  - [x] GCS skip-existing check
  - [x] Writes to `market_data_intraday`, GCS

### Infrastructure Scripts
- [x] `gcp/setup_cloud_sql.sh` — One-shot provisioning
- [x] `gcp/deploy.sh` — Complete rewrite with all commands
  - [x] `setup` command
  - [x] `migrate` command
  - [x] `build` command
  - [x] `fetchers` command
  - [x] `schedulers` command (21 cron triggers)

### Container
- [x] `gcp/Dockerfile` — Updated with psycopg2 deps + scripts/

### Dependencies
- [x] `requirements.txt` — Added GCP packages
  - [x] `cloud-sql-python-connector[pg8000]>=1.7.0`
  - [x] `google-cloud-storage>=2.14.0`
  - [x] `SQLAlchemy>=2.0.0`
  - [x] `psycopg2-binary>=2.9.9`
  - [x] `pandas-market-calendars>=4.3.1`

### Documentation
- [x] `docs/GCP_IMPLEMENTATION_GUIDE.md` — Full architecture guide (14 sections)
- [x] `docs/GCP_IMPLEMENTATION_STATUS.md` — This file

### Claude Automation
- [x] `.claude/commands/gcp-deploy.md` — `/gcp-deploy` slash command

---

## Phase 3: Data Migration

### Raw Parquet Backup to GCS
- [ ] SPY daily parquets → `gs://BUCKET/raw/spy/`
- [ ] IWM daily parquets → `gs://BUCKET/raw/iwm/`
- [ ] QQQ daily parquets → `gs://BUCKET/raw/qqq/`
- [ ] SPX daily parquets → `gs://BUCKET/raw/spx/`
- [ ] SPY intraday parquets → `gs://BUCKET/raw/spy/intraday/`
- [ ] IWM intraday parquets → `gs://BUCKET/raw/iwm/intraday/`
- [ ] QQQ intraday parquets → `gs://BUCKET/raw/qqq/intraday/`
- [ ] ETF options parquets → `gs://BUCKET/raw/options/etfs/`
- [ ] Earnings options parquets → `gs://BUCKET/raw/options/earnings/`
- [ ] Trade logs → `gs://BUCKET/raw/trades/`

### Cloud SQL Ingestion
- [ ] `market_data_daily` — SPY, IWM, QQQ, SPX historical
- [ ] `market_data_intraday` — SPY 1-min (~16GB compressed)
- [ ] `market_data_intraday` — IWM 1-min
- [ ] `market_data_intraday` — QQQ 1-min
- [ ] `etf_options_snapshots` — Historical options snapshots
- [ ] `earnings_options_snapshots` — Historical earnings options
- [ ] `trades` — Trade log history

### Verification
- [ ] Row counts match between Parquet and Cloud SQL
- [ ] Date ranges complete (no gaps)
- [ ] Indicator values match (`RSI_14`, `EMA9`, etc.)
- [ ] Backtest produces same results with Cloud SQL vs Parquet

---

## Phase 4: Deployment

### Docker Image
- [ ] `./gcp/deploy.sh build` — First successful Cloud Build
- [ ] Image available in Artifact Registry

### Cloud Run Jobs (10 jobs)
- [ ] `fetch-market-data` — Daily at 5:00 PM ET
- [ ] `fetch-etf-options` — 9× daily during market hours
- [ ] `fetch-earnings-options` — 6× daily
- [ ] `fetch-av-intraday` — 1st of each month
- [ ] `premarket-brief` — Weekdays 8:30 AM ET
- [ ] `signal-monitor` — Weekdays 9:30 AM ET
- [ ] `weekend-review` — Saturdays 10:00 AM ET
- [ ] `migrate` — On-demand (one-time migration)
- [ ] `analyze-market-data` — Weekdays 6:00 PM ET
- [ ] `run-pipeline` — Weekdays 6:30 PM ET

### Cloud Scheduler Triggers (21 triggers)
- [ ] All 21 schedulers created and enabled
- [ ] Test manual trigger on each job

### Monitoring
- [ ] Cloud Logging configured
- [ ] Error alerting set up (Slack/email)
- [ ] Dashboard created in Cloud Monitoring

---

## Phase 5: GitHub Actions Cutover

### Workflows to Disable (after Cloud Run is verified)
- [ ] `.github/workflows/fetch-market-data.yml` — ➡ Cloud Run `fetch-market-data`
- [ ] `.github/workflows/fetch_etf_options.yml` — ➡ Cloud Run `fetch-etf-options`
- [ ] `.github/workflows/fetch-earnings-options.yml` — ➡ Cloud Run `fetch-earnings-options`
- [ ] `.github/workflows/fetch-alphavantage-intraday-monthly.yml` — ➡ Cloud Run `fetch-av-intraday`
- [ ] `.github/workflows/analyze-market-data.yml` — ➡ Cloud Run `analyze-market-data`
- [ ] `.github/workflows/run-pipeline.yml` — ➡ Cloud Run `run-pipeline`

### Workflows to Keep in GitHub Actions
- [ ] `.github/workflows/handle-workflow-failure.yml` — Keep (CI/CD support)
- [ ] `.github/workflows/backtest-pipeline.yml` — Keep (code-driven)
- [ ] `.github/workflows/validate-market-data.yml` — Keep (CI checks)
- [ ] `.github/workflows/download-google-sheets.yml` — Keep (Sheets-dependent)

### Cutover Steps
- [ ] Run Cloud Run jobs in parallel with GitHub Actions for 1 week
- [ ] Validate data parity (row counts, value spot-checks)
- [ ] Disable GitHub Actions workflows one by one
- [ ] Update README with new architecture

---

## Test Results

| Suite | Status | Tests | Date |
|-------|--------|-------|------|
| Unit/Integration (`make test`) | ✅ PASS | 339/339 | 2026-02-22 |
| E2E Playwright (`make test-e2e`) | Not run | 28 | — |
| Scripts CLI (`make test-scripts`) | ✅ PASS | 18/18 | 2026-02-22 |

---

## Change Log

- 2026-02-22: Pre-migration cleanup — add .gcloudignore + .dockerignore, create requirements-gcp.txt (prod-only), update gcp/Dockerfile, delete orphaned root files
- 2026-02-22: Fix indicator warmup periods — StochRSI→SMA, MACD/EMA/SMA min_periods=period, BB ddof=0 (matches TradingView/AV spec)
- 2026-02-22: DataLoader gains Cloud SQL priority-0 for load_intraday/load_daily; new load_options/load_trades methods
- 2026-02-22: TradeLogger upgraded to Cloud SQL dual-write with Parquet fallback; reads prefer Cloud SQL
- 2026-02-22: deploy.sh expanded with fetchers/schedulers/setup/migrate/build commands; SA env injection
- 2026-02-22: Dockerfile adds libpq-dev/gcc system deps; copies scripts/ into image
- 2026-02-22: enrich_with_indicators gains skip_levels flag (~1.5GB memory savings on large datasets)
- 2026-02-22: requirements.txt adds playwright, GCP cloud packages; Makefile adds test-e2e/test-scripts targets
- 2026-02-22: Phase reports regenerated with corrected indicator values; BACKTEST_RESULTS.md narrowed to IWM

---

## Notes

- All Cloud SQL access is **environment-variable-gated** via `CLOUD_SQL_CONNECTION_NAME`. Setting this env var enables Cloud SQL; omitting it falls back to local Parquet (zero breaking changes for local dev).
- Migration script supports `--dry-run` to preview without writing.
- Initial migration of ~16GB intraday data may take 30–60 minutes; run in screen/tmux.
- All credentials stored in Secret Manager — never in env files committed to git.
