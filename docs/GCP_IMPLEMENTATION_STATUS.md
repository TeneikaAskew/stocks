# GCP Implementation Status Tracker

**Project**: adept-mountain-474619-d4
**Region**: us-east1
**Service Account**: trading-runner@adept-mountain-474619-d4.iam.gserviceaccount.com
**Last Updated**: 2026-04-13 (session 10)

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
  - [x] All indexes created (7 indexes)
    - [x] `idx_etf_options_ticker_source_date (ticker, data_source, snapshot_date DESC)` — covering index for Options Flow reader (created 2026-04-12)
- **Note:** `gcp/schema.sql` patched — removed `id BIGSERIAL PRIMARY KEY` from `market_data_intraday`; PK is now `(ticker, interval, ts)` (required for PostgreSQL LIST partitioning).

### Secret Manager
- [x] `cloud-sql-connection-name` = `adept-mountain-474619-d4:us-east1:trading-db` ✅
- [x] `db-trading-user` = `trading_user` ✅
- [x] `db-trading-pass` = (generated, stored) ✅
- [x] `gcs-trading-bucket` = `adept-mountain-474619-d4-trading-data` ✅
- [x] `av-api-key` = (from .env `ALPHA_VANTAGE_API_KEY`) ✅
- [x] `discord-webhook` = (set) ✅ 2026-02-22

---

## Phase 2: Code Implementation

### Core Library Changes
- [x] `lib/data_loader.py` — Added Cloud SQL backend
  - [x] `_cloud_sql_active()` helper
  - [x] `_query_cloud_sql()` helper
  - [x] `load_intraday()` — Priority 0: Cloud SQL
  - [x] `_load_intraday_from_sql()` — Parameterized query
  - [x] `load_daily()` — Cloud SQL path added
  - [x] `_load_daily_from_sql()` — Maps SQL cols to canonical names (expanded: 30+ indicator columns)
  - [x] `load_options()` — New: queries etf/earnings options tables; added `data_source=` filter param
  - [x] `load_trades()` — New: queries trades table
  - [x] Zero breaking changes (env-var-gated, Parquet fallback preserved)

- [x] `lib/config.py` — Added `AlphaVantageConfig` dataclass (rpm=150, delay/batch properties)

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

- [x] `gcp/schema.sql` — PostgreSQL 15 schema (9 tables: + `journal_entries`, `etf_options_snapshots` gains `data_source` + `mark` columns)

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
- [x] `gcp/fetchers/fetch_av_historical_options.py` — New: AV HISTORICAL_OPTIONS daily → Cloud SQL + GCS
  - [x] Fetches EOD options chains with real Greeks (delta, gamma, theta, vega)
  - [x] Respects centralized AV rate limit (150 RPM)
  - [x] Upserts to `etf_options_snapshots` with `data_source='alphavantage'`
  - [x] Tickers: SPY, IWM, QQQ, SPX (SPX confirmed working 2026-04-12)
  - [x] `--start-date` / `--end-date` for range backfills
  - [x] `--skip-existing` flag (auto-enabled in range mode) — checks Cloud SQL before calling AV
  - [x] Deployed as Cloud Run Job `fetch-av-options-backfill` (12h timeout) for multi-year backfills

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

### Raw Parquet Backup to GCS ✅ 2026-02-23
- [x] All local parquets synced → `gs://adept-mountain-474619-d4-trading-data/raw/data/` ✅
  - 7.61 GiB total, ~1,580 options files + intraday monthly parquets + daily summaries
  - SPY/IWM/QQQ intraday, ETF options (IWM/QQQ/SPX/SPY), earnings options, trade logs
- [x] `data/` removed from git tracking (`f287259b`) — GCS is now source of truth
  - `.gitignore` updated; local copies preserved but untracked
  - Retrieval: `gsutil -m cp -r gs://adept-mountain-474619-d4-trading-data/raw/data/ data/`

### Cloud SQL Ingestion
- [x] `market_data_intraday` — SPY 2,300,839 rows (2015-01-02 → 2026-02-21) ✅ exact parquet match
- [x] `market_data_intraday` — IWM 1,858,427 rows (2015-01-02 → 2026-02-21) ✅ exact parquet match
- [x] `market_data_intraday` — QQQ 2,135,654 rows (2015-01-02 → 2026-02-21) ✅ exact parquet match
- [x] `market_data_daily` — 19,785 rows (SPY/IWM/QQQ ~6,600 each + SPX 81) ✅
  - Backfilled daily indicators from 250-day daily series via `compute_and_upsert_daily_indicators()`
  - Indicator columns: `sma_200, ema_20, macd, macd_signal, macd_histogram, bb_upper, bb_lower, bb_width, bb_pct, price_vs_ema20`
- [x] `etf_options_snapshots` — IWM 1,346,868 rows ✅ exact match
- [x] `etf_options_snapshots` — QQQ 2,840,359 rows ✅ exact match
- [~] `etf_options_snapshots` — ^SPX ~5.2M rows (Yahoo, data_source=NULL) — to be deleted after AV backfill completes
- [x] `etf_options_snapshots` — SPY AV: 2015-01-02 → 2026-04-09 (internal gap 2021-10 → 2023-04, filling via Cloud Run Job)
- [~] `etf_options_snapshots` — SPX AV: backfill in progress (Cloud Run Job, 10yr range 2016 → 2026)
- [~] `etf_options_snapshots` — Yahoo rows (~23M, data_source IS NULL) — orphaned, no consumers, pending deletion
- [ ] `earnings_options_snapshots` — not yet migrated
- [ ] `trades` — not yet migrated

### Verification ✅ 2026-02-23
- [x] Row counts match Parquet sources (IWM/QQQ/SPY intraday exact; IWM/QQQ options exact)
- [x] Zero NULLs on required fields (ticker, ts, open, high, low, close, volume)
- [x] PRIMARY KEY / UNIQUE constraints prevent any duplicates
- [x] Date ranges verified (intraday: 2015–2026; options: Oct–Dec 2025)
- [ ] Indicator values spot-checked against TradingView/AV
- [ ] Backtest produces same results with Cloud SQL vs Parquet

---

## Phase 4: Deployment

### Docker Image
- [x] `./gcp/deploy.sh build` — First successful Cloud Build ✅ 2026-02-23
  - Build ID: `1cfaf281-8465-485c-9a68-c14da0130157` (2m 20s, 86 files / 1.3 MB)
  - Digest: `sha256:0a01010aefc4e1ff7c6dfd10410402fae9fa9b1e8ee67cba665d6cebb76c5021`
- [x] Image available in Artifact Registry ✅
  - `us-east1-docker.pkg.dev/adept-mountain-474619-d4/trading/trading-system:latest`
- **Note:** `gcp/deploy.sh build` updated to use a minimal temp build context (86 files / ~1.3 MB) instead of the full repo (4 GB). Copies only `lib/`, `gcp/`, `scripts/`, `alert_config.json`, `requirements-gcp.txt`.

### Cloud Run Jobs (8 jobs) ✅ 2026-02-23 (updated 2026-04-12)
- [x] `fetch-market-data` — deployed
- [x] `fetch-etf-options` — deployed
- [x] `fetch-earnings-options` — deployed
- [x] `fetch-alphavantage-intraday` — deployed
- [x] `premarket-brief` — deployed; now writes to `premarket_analysis` (32 cols) + queries `economic_events`
- [x] `signal-monitor` — deployed; now writes to `signal_alerts` + `trades` via TradeLogger
- [x] `weekend-review` — deployed
- [x] `fetch-economic-events` — **new** (2026-04-12): FRED releases → `economic_events` table
- **Note:** `signal-monitor` converted from Cloud Run Service → Job (no HTTP server needed for polling loop)

### Cloud Scheduler Triggers (23 triggers) ✅ 2026-02-23 (updated 2026-04-12)
- [x] `premarket-brief-daily` — `30 8 * * 1-5` ET
- [x] `signal-monitor-daily` — `25 9 * * 1-5` ET (new — was missing)
- [x] `weekend-review-weekly` — `0 9 * * 6` ET
- [x] `fetch-market-data-daily` — `0 17 * * 1-5` ET
- [x] `etf-options-0930` through `etf-options-1605` — 9 triggers
- [x] `earnings-opts-0900` through `earnings-opts-1630` — 6 triggers
- [x] `av-intraday-monthly` — `0 21 1 * *` ET
- [x] `economic-events-daily` — `0 7 * * 1-5` ET (**new** 2026-04-12)
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

## Platform: Unified Trading Dashboard (`platform/`)

A production-grade React/TypeScript web app that replaces 4 separate vanilla JS apps (chart-viewer, options-heatseeker, website, success-report-site) with a single unified platform backed by the GCP data stack.

### Stack
| Layer | Technology |
|-------|-----------|
| Frontend | Vite 7 + React 19 + TypeScript + Tailwind CSS 4 |
| State | Zustand (client) + TanStack Query v5 (server cache) |
| Charts | TradingView Lightweight Charts (candles) + Recharts (metrics) + D3.js (options heatmap) |
| Backend | FastAPI — thin wrapper over `lib/` modules + Cloud SQL |
| AI | Vertex AI Gemini 2.0 Flash (streaming, 4 modes) |
| Data | Cloud SQL PostgreSQL 15 (primary) + GCS parquets (fallback) |

### Routes (10 pages)
| Route | Page | Status |
|-------|------|--------|
| `/` | Dashboard — backtest KPIs, recent signals, playbook summary | ✅ Live |
| `/live` | Live Market — Alpha Vantage quotes, EMA/RSI/StochRSI/ATR, signal detection, sound alerts | ✅ Live |
| `/charts` | Chart Viewer — TradingView candlesticks, trade marking, multi-TF (1/5/15/30/60) | ✅ Live |
| `/options` | Options Flow — D3.js GEX/VEX heatmap, king nodes, gatekeepers, midpoints, date navigation | ✅ Live |
| `/playbook` | Playbook — 12 decision cards per ticker, interactive condition checklists | ✅ Live |
| `/backtest` | Backtester — equity curve (Recharts), trade table (TanStack Table), summary metrics | ✅ Live |
| `/reports` | Reports — markdown report browser (6 phases) with sidebar navigation | ✅ Live |
| `/signals` | Signal Explorer — 330K+ signals, filter by direction/score/date | ✅ Live |
| `/journal` | Trade Journal — Cloud SQL-backed (local JSON fallback) | ✅ Live |
| `/insights` | AI Insights — Vertex AI Gemini streaming chat, 4 modes (Chat/Market/Strategy/Trade Review) | ✅ Live |

### FastAPI Backend (`platform/api/`)
8 routers: `live`, `options`, `playbook`, `backtest`, `signals`, `insights`, `journal`

Key data flows:
- **Chart data**: Cloud SQL `market_data_intraday` (3,115 dates, 2015–2026) with local parquet fallback
- **Reference levels**: Cloud SQL `market_data_daily` for previous day OHLC support/resistance
- **Live quotes**: Alpha Vantage GLOBAL_QUOTE (15s polling, 150 RPM plan)
- **Options flow**: Alpha Vantage HISTORICAL_OPTIONS proxy (replaces Cloudflare Worker)
- **Journal**: Cloud SQL `journal_entries` table (CRUD) with local JSON fallback
- **Backtest results**: reads `data/backtest_results/backtest_{TICKER}_*.csv`
- **Signals**: reads `data/signals/historical_{TICKER}_*_signals.parquet`
- **AI chat**: Vertex AI Gemini 2.0 Flash via `google.genai` SDK, SSE streaming

### Cloud SQL Integration ✅ 2026-02-23
- **Reads**: `market_data_daily`, `market_data_intraday`, `etf_options_snapshots` — via `lib/data_loader.py` + direct queries in `main.py`
- **Chart endpoints**: `/api/market/dates`, `/api/market/data`, `/api/market/reference` — Cloud SQL primary, local parquet fallback
- **Journal CRUD**: `journal_entries` table — GET/POST/DELETE with local JSON fallback
- Health endpoint (`/api/health`) reports `cloud_sql: true/false`

### Journal Cloud SQL Migration ✅ 2026-02-23
- [x] `journal_entries` table added to `gcp/schema.sql` (UUID PK, ticker, direction, timestamps, prices, return_pct, notes)
- [x] `platform/api/routers/journal.py` — full CRUD (GET/POST/DELETE) against Cloud SQL with local JSON fallback
- [x] `platform/src/routes/JournalPage.tsx` — TanStack Query hooks (Cloud SQL primary, localStorage as optimistic cache)
- [x] Data source indicator in UI: green "Cloud SQL" or amber "Local storage"

### Dev Server Access (GitHub Codespace) ✅ 2026-02-23
- [x] `platform/vite.config.ts` — `host: true` (listens on `0.0.0.0`)
- [x] `platform/api/main.py` — `allow_origin_regex=r"https://.*\.app\.github\.dev"` in CORS middleware
- [x] `.devcontainer/devcontainer.json` — `forwardPorts: [5173, 8000]` with labels

### Production Static File Serving ✅ 2026-02-23
- [x] `platform/api/main.py` — `/assets` StaticFiles mount + SPA catch-all `@app.get("/{full_path:path}")` at end of file
- Production workflow: `npm run build` → `uvicorn api.main:app --host 0.0.0.0 --port 8000` (single port)

### How to Start (Development)
```bash
# Terminal 1 — FastAPI backend
cd /workspaces/stocks/platform
set -a && source ../.env && set +a
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Vite frontend
cd /workspaces/stocks/platform
npm run dev
# → http://localhost:5173  (or Codespace URL on port 5173)
```

### GCP Dependencies Required
```
CLOUD_SQL_CONNECTION_NAME=adept-mountain-474619-d4:us-east1:trading-db
DB_USER=trading_user
DB_PASS=<from Secret Manager: db-trading-pass>
DB_NAME=trading
AV_API_KEY=<from Secret Manager: av-api-key>
GOOGLE_APPLICATION_CREDENTIALS=.gcp-key.json   # for Vertex AI
```

---

## Cost Estimates (Monthly)

> Based on current data: 7.61 GiB GCS, ~14M Cloud SQL rows, 22 Cloud Scheduler triggers, 7 Cloud Run Jobs

| Service | Resource | Est. Cost/mo |
|---------|----------|-------------|
| **Cloud SQL** | db-g1-small instance (us-east1, 24/7) | ~$10–12 |
| **Cloud SQL** | 20 GB SSD storage | ~$3.40 |
| **Cloud SQL** | Automated backups (~5 GB) | ~$0.40 |
| **Cloud Storage** | 7.6 GB standard storage | ~$0.15 |
| **Cloud Storage** | Operations (reads/writes) | ~$0.05 |
| **Cloud Run Jobs** | Execution time (all 7 jobs) | ~$1.50 |
| **Cloud Scheduler** | 22 triggers (3 free) | ~$1.90 |
| **Secret Manager** | Access operations | ~$0.02 |
| **Artifact Registry** | Docker image storage | ~$0.10 |
| **Total estimate** | | **~$17–20/mo** |

**Notes:**
- Cloud SQL dominates cost (~75%). Upgrade to `db-n1-standard-1` if query performance degrades.
- If Cloud Run jobs are disabled (GitHub Actions cutover not done), subtract ~$1.50.
- GCS cost stays low (<$0.25) even as data grows — parquets compress well.
- Scale: at $0.02/GB, even 100 GB of GCS backups = $2/month.

---

## Test Results

| Suite | Status | Tests | Date |
|-------|--------|-------|------|
| Unit/Integration (`make test`) | ⚠️ 1 pre-existing failure | 222/223 | 2026-04-13 |
| Platform API (`tests/test_platform_api.py`) | ⚠️ 1 pre-existing failure | 30/31 | 2026-04-13 |
| E2E Playwright (`make test-e2e`) | Not run | 28 | — |
| Scripts CLI (`make test-scripts`) | ✅ PASS | 18/18 | 2026-02-22 |

Pre-existing failures (unrelated to dashboard work):
- `test_data_loader.py::TestLoadIntraday::test_returns_empty_when_no_data` — premise
  invalid now that Cloud SQL has real IWM data.
- `test_platform_api.py::TestHealth::test_health_returns_ok` — checks for removed
  `data_dir_exists` field in `/api/health` response.

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
- 2026-02-22: Full 2015–2026 dataset re-run (all 7 phases + timeframe sweep); 1m+30m confirmed primary signal (Sharpe 11.05 IWM)
- 2026-02-22: Backfilled 10yr historical options data (IWM 2016–2026, SPY 2018–2025, QQQ 2022 partial)
- 2026-02-22: options_pnl_translation.py and walk_forward_tf_combos.py — time-of-day breakdown and low-sample flags
- 2026-02-22: Extended SPY options coverage through 2026-02-20 (added 2022-11 → 2026-02 batch)
- 2026-02-23: Recover trading_analysis.py, trade_analysis_pipeline.py, iwm_trading_alerts.py + trade_tracker CSVs
- 2026-02-23: gcp/database.py bulk_insert rewritten with SQLAlchemy Core to fix pg8000 65535-param limit; chunksize 10000→5000 in migrate_to_gcp.py
- 2026-02-23: BACKTEST_RESULTS.md expanded to include SPY and QQQ parameter table + filter rejection rates
- 2026-02-22: deploy.sh build context reduced ~4 GB → ~1.3 MB; market_data_intraday schema uses composite PK
- 2026-02-22: walk_forward_tf_combos.py — rolling-window OOS validation of top TF combos with volatility regime split
- 2026-02-22: options_pnl_translation.py — Greeks-approximation 0DTE P&L estimator using daily options chains
- 2026-02-22: phase6_playbook_combined.md — appendix with multi-TF filtered win rates (1m+30m 56–59%, 5m+15m ~62%)
- 2026-02-23: trade_analysis_pipeline.py — fix market-hours filter (allow 4:00 PM exits), add Trade_Profitable fallback for 6-month comparison; IWM report updated with 6-month window analysis
- 2026-02-23: GCS sync completed — 7.61 GiB backed up to gs://adept-mountain-474619-d4-trading-data/raw/data/
- 2026-02-23: data/ removed from git tracking (f287259b); GCS is now source of truth; .gitignore updated
- 2026-02-23: Cloud SQL intraday migration complete — SPY 2.3M, IWM 1.86M, QQQ 2.14M rows (exact parquet match)
- 2026-02-23: ETF options migration complete for IWM (1.35M) and QQQ (2.84M); SPX/SPY in progress (~14M total target)
- 2026-02-23: Data quality verified — PK/UNIQUE constraints prevent dupes; zero NULLs on required fields
- 2026-02-23: .env + .gcp-key.json created for persistent credentials (both gitignored); secrets also in Secret Manager
- 2026-02-23: AlphaVantageConfig centralized in lib/config.py (rpm=150); AV scripts + data_loader use config instead of hardcoded values
- 2026-02-23: gcp/database.py query_to_dataframe uses sqlalchemy.text() for correct named-param handling across DBAPIs
- 2026-02-23: data_loader load_daily expanded to 30+ indicator columns; load_options gains data_source= filter
- 2026-02-23: gcp/schema.sql — etf_options_snapshots gains data_source VARCHAR(30) + mark DOUBLE PRECISION columns
- 2026-02-23: gcp/migrate_to_gcp.py — added av_options migration key; daily_indicators backfill support
- 2026-02-23: gcp/fetchers/fetch_market_data.py — compute_and_upsert_daily_indicators() from 250-day daily series
- 2026-02-23: gcp/fetchers/fetch_av_historical_options.py — new fetcher for AV HISTORICAL_OPTIONS → Cloud SQL + GCS
- 2026-02-23: market_data_daily backfilled to 19,785 rows (SPY/IWM/QQQ ~6,600 each)
- 2026-02-23: trade_analysis_pipeline.py — fix RTH filter (entry cutoff 3:55 PM, exit 3:58 PM, same-day check)
- 2026-02-23: scripts/find_swing_trades.py — new swing trade scanner (afternoon entry, next-day exit, --options-pnl flag)
- 2026-02-23: options_pnl_translation.py — find_swing_option + estimate_swing_options_pnl for overnight swing trades
- 2026-02-23: Swing scanner gains winner vs loser indicator profiling (predictive/non-predictive factor tables)
- 2026-02-23: platform/ — unified React/TypeScript trading dashboard (10 routes, FastAPI backend, Vertex AI Gemini chat, D3.js options heatmap, TradingView candlesticks, TanStack Table signals/trades); replaces 4 separate vanilla JS apps
- 2026-02-23: fix(config) — remove hardcoded AV API keys from scripts; centralize key management in AlphaVantageConfig.get_api_keys() (env-only)
- 2026-02-23: feat(gcp) — AV options migration gains checkpoint-resume (skips existing dates) and streaming row-group reads (constant memory)
- 2026-02-23: chore(deps) — add requirements.lock/requirements-gcp.lock; Makefile gains `lock` target; Dockerfile prefers lock file
- 2026-02-23: fix(platform) — SPA catch-all route moved to end of main.py to avoid shadowing /api/* routes; Codespace CORS regex added; BacktestPage/DashboardPage TS fixes
- 2026-02-23: feat(platform) — chart data endpoints upgraded to Cloud SQL primary (3,115 dates from 2015–2026); reference levels from market_data_daily; local parquet fallback preserved
- 2026-02-23: feat(platform) — journal_entries Cloud SQL CRUD (GET/POST/DELETE) with local JSON fallback; TanStack Query + useMutation hooks
- 2026-02-23: chore(devcontainer) — forwardPorts [5173, 8000] with labels for Codespace auto-forwarding
- 2026-03-01: feat(platform) — add markdown rendering (marked) for ReportsPage tables and InsightsPage chat bubbles; prose-report CSS styles
- 2026-03-01: chore(workflows) — remove yfinance/yahooquery from GitHub Actions pip installs (analyze-market-data, fetch-earnings-options, update-economic-events-calendar)
- 2026-04-10: fix(platform) — header market-session badge + ticker price now driven by live /api/live/status and /api/live/quote via shared useLiveStatus/useLiveQuote hooks; dead marketStore deleted (badge was permanently stuck on "Market Closed")
- 2026-04-10: feat(platform) — PlaybookPage auto-evaluates each card's condition strings against a live MarketSnapshot (RSI/VWAP/EMA/StochRSI/RVOL/ORB/prev-day levels/minutes-since-open) via new lib/playbookEvaluator.ts regex mapper; cards light up in direction color (green CALL / red PUT), counter reads metCount/total with "N subjective" suffix for unevaluable conditions, progress bar and border intensify as live market satisfies the setup
- 2026-04-12: feat(gcp) — Cloud Run jobs now write to ALL Cloud SQL tables: premarket_brief → premarket_analysis (32 cols with key levels, vol regime, MACD cross); signal_monitor → signal_alerts + trades; new fetch_economic_events fetcher → economic_events (FRED API + JSON); premarket brief rewritten as rich 3-embed Discord message (overview, ticker analysis, economic calendar); options dates endpoint uses widening-range scan with 12h TTL cache; schema.sql gains 14 new columns on premarket_analysis; deploy.sh gains fetch-economic-events job + economic-events-daily scheduler trigger
- 2026-04-12: fix(platform) — Options Flow page rewritten from broken live-AV proxy to Cloud SQL reader backed by `etf_options_snapshots WHERE data_source='alphavantage'`. Endpoints: `/api/options/dates/{ticker}` (widening-range scan, 12h TTL cache) and `/api/options/{ticker}/{date}` (full chain, 12h TTL cache). Frontend now surfaces real API error messages, shows "Source: AlphaVantage EOD · Cloud SQL" footer. Added SPX to VALID_TICKERS after confirming AV supports SPX (9,166 contracts/day) + SPXW (19,026). Covering index `idx_etf_options_ticker_source_date(ticker, data_source, snapshot_date DESC)` created.
- 2026-04-12: fix(workflows) — fetch-alphavantage-options-daily.yml was calling `scripts/fetch_alphavantage_options.py` (local parquets → git commit) instead of `gcp.fetchers.fetch_av_historical_options` (Cloud SQL writer). Fixed: now calls the Cloud SQL writer with `--start-date`/`--end-date` support. Documents 7 required GitHub repo secrets. Old script bannered as local-only.
- 2026-04-12: feat(fetchers) — `gcp/fetchers/fetch_av_historical_options.py` gains `--start-date`/`--end-date` for range backfills, `--skip-existing` flag (auto-enabled in range mode) that checks Cloud SQL before calling AV, SPX added to TICKERS. Deployed as Cloud Run Job `fetch-av-options-backfill` with 12h timeout for 10-year backfill.
- 2026-04-12: data(backfill) — 10-year AV options backfill (2016-04-10 → 2026-04-11) for SPY/IWM/QQQ/SPX launched as Cloud Run Job. SPY has near-complete coverage 2015 → 2026 (internal gap 2021-10 → 2023-04). IWM through 2024-09, QQQ through 2024-05, SPX starting from 2016-04. Job resumes automatically via `--skip-existing`.
- 2026-04-12: docs — INFRASTRUCTURE_NOTES.md created: documents deferred Cloud SQL tier upgrade (db-g1-small → db-custom-2-4096), reasoning, re-evaluation triggers, short-term mitigations (covering index, 12h TTL cache, widening-range scan)
- 2026-04-12: feat(gcp) — new `earnings_calendar` Cloud SQL table (42 cols) with dual-source persistence from Unusual Whales + Earnings Whispers; fetch_earnings_calendar.py gains EW cookie-based auth (mirrors GAS 04_Code.js login flow), 9 strategy endpoints, Cloud SQL upsert; deploy.sh gains fetch-earnings-calendar Cloud Run Job + earnings-calendar-daily scheduler trigger; GAS tracking columns (strike_hit, day0-5_check, hit_rsi, ohlc_volume, etc.) present as NULLable for future backfill
- 2026-04-12: feat(fetchers) — fetch_earnings_options.py resolves tickers from earnings_calendar SQL table (7-day lookahead) instead of GCS/local CSVs; CSVs kept as fallback
- 2026-04-12: feat(scripts) — add AlphaVantage EARNINGS_CALENDAR as 3rd source in fetch_earnings_calendar.py; AV is date-of-truth, overrides EW/UW dates via ticker lookup; normalize_earnings_time() unifies 1/2/3/premarket/postmarket to {premarket, intraday, postmarket, unknown}; Cloud SQL now holds 9,510 rows across 3 sources (8,783 AV, 490 EW, 237 UW) with 557 overlapping (ticker, date) pairs
- 2026-04-13: feat(gcp) — add `archive_yahoo_*` tables (schema.sql) + `scripts/archive_yahoo_data.py` for chunked Yahoo→archive→delete with resume-safe dedup. Intraday Yahoo cleanup complete (51,471 rows archived, 0 in prod). Recovered 73K AV rows lost to a ctid-partition bug (script now uses PK-based batching). `fetch_alphavantage_intraday.py` switched from `bulk_insert_dataframe` → `upsert_dataframe` so re-runs are safe. `etf_options_snapshots` Yahoo cleanup (~24M rows) pending the running `fetch-av-options-backfill` Cloud Run Job completion.
- 2026-04-13: feat(fetchers) — `fetch_economic_events.py` adds ForexFactory source (https://nfs.faireconomy.media/ff_calendar_thisweek.json) for release times + forecast/previous values. FRED fallback for coverage; FOMC Press Release metadata blacklisted. Brief filters to Mon–Fri only, prefers rows with times when available.
- 2026-04-13: feat(premarket) — earnings embed tier sort (AV+UW+EW first, then AV+UW, then AV+EW, then long tail). Tier 1-3 get 🟢🔵🟡 badges. Day headers show "N confirmed / M total". Truncation shows hidden confirmed count ("+111 more (2 confirmed)"). Weekly mode (Sunday brief) groups economic events by day in the calendar embed description. Labels renamed F/P → Exp=/Prev= for clarity.
- 2026-04-13: fix(platform) — Daily Bias card on Dashboard now overlays live AlphaVantage quote on top of the Cloud SQL daily snapshot when market is open (recomputes RSI14 / EMA9 / EMA20 / SMA200 with synthetic today bar appended). Frontend polls the brief endpoint every 15s during regular hours and shows a green LIVE pill + "Live regular — $XYZ.XX" subtitle. Stale-days calc converted from calendar days to trading days via shared `_is_market_open` holiday set so Thu→Mon reads "1d stale" not "4d stale".
- 2026-04-13: fix(gcp) — `gcp/deploy.sh` `_env_string()` now injects `AV_API_KEY` + `ALPHA_VANTAGE_API_KEY` (both names) and `FRED_API_KEY` from Secret Manager into every Cloud Run job. Closes a footgun where a fresh `deploy.sh fetchers` push would create jobs missing the AV key. Existing jobs already had the keys set out-of-band.
- 2026-04-13: ops — rebuilt `trading-system` container image (digest `78035eb7…` → `10200d2c…`) with the post-AlphaVantage-migration fetch_market_data.py code path. Old image had a yfinance fallback that wrote pandas float `1.0` into INTEGER columns (`consecutive_up`, `consecutive_down`), causing silent daily failures since 2026-04-06. Backfilled IWM/SPY/QQQ rows for 2026-04-06..04-10 via 5 manual `gcloud run jobs execute` calls (Cloud SQL now current through Friday 04-10).
- 2026-04-13: chore(workflows) — `.github/workflows/fetch-market-data.yml` renamed to `.disabled`. `fetch-market-data` Cloud Run Job is now sole source of truth for `market_data_daily`.

---

## Notes

- All Cloud SQL access is **environment-variable-gated** via `CLOUD_SQL_CONNECTION_NAME`. Setting this env var enables Cloud SQL; omitting it falls back to local Parquet (zero breaking changes for local dev).
- Migration script supports `--dry-run` to preview without writing.
- Initial migration of ~16GB intraday data may take 30–60 minutes; run in screen/tmux.
- All credentials stored in Secret Manager. Also present as `.env` + `.gcp-key.json` in project root (both gitignored) for local dev convenience.
- `data/` is not in git — use `gsutil -m cp -r gs://adept-mountain-474619-d4-trading-data/raw/data/ data/` to restore locally.
- **Daily OHLCV data**: `market_data_daily` backfilled to 19,785 rows (SPY/IWM/QQQ ~6,600 each, 2000–2026). Indicators computed from 250-day daily series via `compute_and_upsert_daily_indicators()`.
- **Options data sources**: All fetchers use AlphaVantage (`data_source='alphavantage'`). Historical Yahoo intraday data (`data_source=NULL`) remains in Cloud SQL; API handles timezone conversion for legacy rows. Filter with `data_source=` param in `load_options()`.
