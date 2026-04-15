# Changelog

## Session 12 (2026-04-15)

### GCP Cloud Run Job Failure Notifier (Discord + GitHub Issue)
- **Commit(s)**: feat(gcp): add Cloud Run job failure notifier
- **Files**: `gcp/failure_notifier.py` (new), `gcp/deploy.sh`, `tests/test_failure_notifier.py` (new), `docs/GCP_IMPLEMENTATION_STATUS.md`
- **What Changed**: New Cloud Run Service `failure-notifier` built on Python stdlib `http.server` (no new deps in `requirements-gcp.txt`). Receives Pub/Sub push envelopes containing Cloud Logging entries for failed Cloud Run Jobs, extracts job name / execution ID / error text / timestamp, and fans out to two destinations: (1) a Discord webhook embed with a clickable "View logs" link to the Cloud Console execution page, and (2) a GitHub issue labelled `gcp-job-failure,<job_name>,automated`. Repeat failures append a comment to the existing open issue instead of opening a new one (dedup pattern adapted from `scripts/handle_workflow_failure.py`). `gcp/deploy.sh` gains `setup_notifier_secrets` (stores `github-pat` + `github-repo` in Secret Manager) and `deploy_notifier` (builds the service, creates the Pub/Sub topic `gcp-job-failures`, creates the push subscription with OIDC auth using the existing `trading-runner` SA, creates the Cloud Logging sink `gcp-job-failures-sink` with filter `resource.type="cloud_run_job" AND severity>=ERROR AND resource.labels.job_name!="failure-notifier"`, and grants the sink writer `pubsub.publisher`). A self-loop guard in `handle_notification` also ignores entries whose `job_name == "failure-notifier"` as a second line of defense. Wired into `all` and the help text. Unit tests cover envelope parsing, Cloud Logging field extraction, Discord payload truncation, GitHub dedup (existing issue → comment; no match → create), graceful skip on missing env vars, self-loop suppression, and end-to-end happy path — 11 passing in 0.2s.
- **Why**: GCP Cloud Run Jobs (9 fetchers + 3 analysis jobs) run on Cloud Scheduler crons with no alerting. The two-week silent breakage of `fetch-market-data` documented in Session 10 was the motivating incident — nobody noticed `market_data_daily` was frozen at 2026-04-05. The existing `.github/workflows/handle-workflow-failure.yml` only covers GitHub Actions, not GCP jobs. A per-job try/except wrapper would require touching 9+ scripts and still miss crashes like OOM / task-timeout / image-pull failures, whereas a Cloud Logging sink catches every failure mode uniformly with zero changes to the job scripts.
- **Benefit**: Any Cloud Run Job failure (crash, non-zero exit, OOM, task-timeout) now posts to Discord within ~60 seconds and creates or updates a tracked GitHub issue — the same two channels the user already monitors. Repeat failures are collapsed into a single issue so the tracker doesn't get flooded. Uses only existing secrets (`discord-webhook`) plus two new ones (`github-pat`, `github-repo`) and runs on `min-instances=0` so steady-state cost is near zero.

## Session 10 (2026-04-13)

### Daily Bias Card: Live Quote Overlay + Trading-Day Staleness
- **Files**: `platform/api/routers/dashboard.py`, `platform/src/routes/DashboardPage.tsx`
- **What Changed**: The `/api/dashboard/brief/{ticker}` endpoint now overlays the live AlphaVantage quote on top of the Cloud SQL daily snapshot whenever `_is_market_open()` (shared with `live.py`) returns True. Pulls last 250 daily closes from Cloud SQL, appends a synthetic today-bar built from the live price, and recomputes RSI14 / EMA9 / EMA20 / SMA200 via `lib.indicators` so every number on the bias card reflects the live tape. Returns a new `live: { price, session, updated_at, source }` block so the frontend can label it. The DashboardPage re-polls the brief every 15s when the market is open (was 5min) and renders a green LIVE pill + "Live regular — $XYZ.XX" subtitle in place of "Based on YYYY-MM-DD daily close". The `stale_days` calculation switched from calendar days to trading days via a new `_trading_days_between()` helper that uses the same `MARKET_HOLIDAYS_2026` set as `live.py`, so Thursday→Monday reads as "1d stale" (only Friday missing) instead of "4d stale".
- **Why**: User screenshot showed "4d stale" on Daily Bias card with data frozen at 2026-04-09. Even after backfilling Cloud SQL, the card still wouldn't reflect today's tape during market hours, and the calendar-day staleness counter was misleading on Mondays.
- **Benefit**: Bias card stays current with live price action and indicators during market hours; staleness pill no longer cries wolf over weekends + holidays.

### Cloud Run Job: Stale Image + Daily Failures Diagnosed and Fixed
- **Files**: `gcp/deploy.sh` (`_env_string()`), Cloud Run job image rebuild, manual backfill executions
- **What Changed**: The `fetch-market-data` Cloud Run Job had been failing silently on most weekdays since 2026-04-06 (4 of 6 most recent runs `Completed=False`). Root cause: the deployed container image was built before the AlphaVantage migration and still contained a yfinance fallback that wrote pandas float `1.0` into the `INTEGER` columns `consecutive_up` / `consecutive_down` (PostgreSQL `invalid input syntax for type integer: "1.0"`). The successful days were ones where the pandas series happened to be int-typed (no NaNs). Rebuilt the image with `bash gcp/deploy.sh build` (digest `78035eb7…` → `10200d2c…`), updated the job to pull the new image, and manually ran `gcloud run jobs execute fetch-market-data --args=--date,YYYY-MM-DD` for 04-06, 04-07, 04-08, 04-09, 04-10 — all 5 succeeded with `✓ daily OHLCV upserted (source: alphavantage_daily)` for IWM/SPY/QQQ. Cloud SQL `market_data_daily` is now current through Friday 04-10. Also patched `_env_string()` in `deploy.sh` to inject `AV_API_KEY` + `ALPHA_VANTAGE_API_KEY` (both names — code paths read different ones) and `FRED_API_KEY` from Secret Manager. Re-ran `--update-env-vars` against all 7 other Cloud Run Jobs (premarket-brief, signal-monitor, fetch-etf-options, etc.) to apply the merged env, though inspection showed they already had both keys set out-of-band.
- **Why**: Two-week silent breakage. No alerting on Cloud Run job failures means nobody noticed `market_data_daily` had been frozen at 2026-04-05.
- **Benefit**: Cloud SQL is current. Future `deploy.sh fetchers` runs will create jobs with both AV env var names by default, eliminating the "fetcher reads ALPHA_VANTAGE_API_KEY but only AV_API_KEY is set" footgun. SPX intraday remains broken on a separate longstanding issue (no AV time series for SPX index), out of scope here.

### Disable Parallel GH Actions Workflow for Market Data
- **Files**: `.github/workflows/fetch-market-data.yml` → `.disabled`, `docs/GCP_IMPLEMENTATION_GUIDE.md` §15
- **What Changed**: Renamed `fetch-market-data.yml` to `.disabled` per project convention (already used for `fetch-economic-events-calendar.yml.disabled`). Updated GUIDE §15 cutover table to mark this workflow ✅ disabled. The Cloud Run Job is now the sole writer to `market_data_daily`.
- **Why**: User directive: "nothing should be reliant on gh workflows or actions, everything should be a cloud sql run job or workflow." The GH workflow only wrote to local parquet files (never Cloud SQL) so it was a confusing dead path that someone might assume was the source of truth.
- **Benefit**: One canonical fetcher path. Easier to debug and monitor. 12 other data-fetching workflows still exist in `.github/workflows/` and need the same treatment in a follow-up audit.

## Session 9 (2026-04-13)

### Yahoo Archive Tables + Cleanup Script
- **Files**: `gcp/schema.sql`, `scripts/archive_yahoo_data.py` (new), `docs/GCP_IMPLEMENTATION_GUIDE.md`
- **What Changed**: Added four `archive_yahoo_*` tables (daily, intraday, etf_options, earnings_options) created via `CREATE TABLE ... (LIKE src INCLUDING ALL)`. New orchestration script `scripts/archive_yahoo_data.py` does chunked copy (prod → archive) + chunked DELETE from prod using primary-key batching (NOT ctid — critical on partitioned tables). Script has dry-run, per-table `--confirm` gates, resume-safe dedup via NOT EXISTS, and backfill pre-flight check that aborts on `etf_options_snapshots` if the running `fetch-av-options-backfill` Cloud Run Job has active executions.
- **Why**: Yahoo data was supposed to be deleted after the AlphaVantage migration but ~24M rows still lived in `etf_options_snapshots` + 51K in `market_data_intraday`. User wanted them archived (not destroyed) then removed from prod.
- **Benefit**: Production tables become AV-only for deterministic queries; legacy Yahoo data preserved for forensics; script is resumable and safe to re-run.

### Intraday Yahoo Cleanup + Data Recovery
- **Files**: `scripts/archive_yahoo_data.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`
- **What Changed**: Ran archive+delete on `market_data_intraday`. First attempt had a ctid partition bug: the DELETE CTE batched by ctid, which is partition-local on PostgreSQL LIST-partitioned tables, so ctids collided across SPY/IWM/QQQ/SPX partitions and deleted 73,498 AV rows along with the 51,471 Yahoo rows. Fixed the script to use primary-key columns instead. Recovered the lost AV rows via `python -m gcp.fetchers.fetch_alphavantage_intraday --symbol ALL --start-date 2026-02-01 --end-date 2026-04-09 --force`. Switched the fetcher from `bulk_insert_dataframe` → `upsert_dataframe` so re-runs are idempotent.
- **Why**: Post-incident: wanted to recover the data AND prevent recurrence.
- **Benefit**: `market_data_intraday` now has 0 Yahoo rows and full AV coverage Feb 22 – Apr 11 2026. Fetcher is upsert-safe going forward.

### ForexFactory as Economic Events Source
- **Files**: `gcp/fetchers/fetch_economic_events.py`
- **What Changed**: Added `fetch_forexfactory_events()` using the free FairEconomyMedia JSON mirror (`https://nfs.faireconomy.media/ff_calendar_thisweek.json`). Provides release TIME + forecast/previous values that FRED's `/releases/dates` endpoint doesn't offer. `main()` fetches FF first, then FRED as backup, deduped by `(event_date, event_name)` keeping FF (it has times). CLI gains `--source forexfactory|ff` and `--min-impact` / `--countries` flags. Added `FOMC Press Release` to the FRED name blacklist (it's a metadata category that appears every weekday, pollutes the calendar).
- **Why**: FRED only provides release dates, not times — users couldn't tell if CPI dropped at 8:30am or 4pm. FF is the de facto trader standard.
- **Benefit**: Economic Calendar embed in the premarket brief now shows real release times (`🔴 08:30 Core PPI m/m Exp=0.5% Prev=0.5%`).

### Premarket Brief: Earnings Tier Sort + Weekly Mode
- **Files**: `gcp/premarket_brief.py`
- **What Changed**: Earnings embed now tier-sorts tickers by source coverage:
  - 🟢 Tier 1 = AV + UW + EW (all three — top confirmed + strategy)
  - 🔵 Tier 2 = AV + UW (top market-movers per UW, no strategy)
  - 🟡 Tier 3 = AV + EW (strategy pick without UW validation)
  - Tier 4-6 = long tail
  Within each tier, display row prefers EW > AV > UW (EW carries strategy/strike/score). Day headers show "N confirmed / M total" instead of just "total". Truncation shows hidden confirmed count: "+111 more (2 confirmed)". Added weekly mode to `_build_calendar_embed()` — on Sundays, the Economic Calendar embed shows the week ahead grouped by day. F/P labels renamed to Exp=/Prev= for clarity. `load_economic_events()` filters weekends (DOW NOT IN 0,6) and drops TBD rows when a timed row exists for the same date.
- **Why**: Alphabetical sort buried the most-actionable tickers (BLK, JPM, NFLX, etc.) under OTC junk. Users needed confirmed names to appear first.
- **Benefit**: The top 10 tickers per day are now the ones that matter (AV+UW+EW confirmed), with clear visual tier badges. Sunday brief gives the full week of earnings + economic events in one message.

## Session 8 (2026-04-12)

### Cloud Run Jobs → All Cloud SQL Tables
- **Commits**: `c16d6e1c`, `e413f53c`, `1b66a43c`
- **Files**: `gcp/premarket_brief.py`, `gcp/signal_monitor.py`, `gcp/schema.sql`, `gcp/deploy.sh`, `gcp/fetchers/fetch_economic_events.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `INFRASTRUCTURE_NOTES.md`
- **What Changed**: Premarket brief rewritten as 3-embed Discord message (overview + ticker analysis + economic calendar) with 32-column Cloud SQL persist. Signal monitor now writes to `signal_alerts` and `trades`. New `fetch_economic_events` Cloud Run job (FRED API → `economic_events` table). Schema gains 14 new columns on `premarket_analysis`.
- **Why**: 5 of 9 Cloud SQL tables were empty — no Cloud Run job was writing to them.
- **Benefit**: All tables now have data pipelines; premarket brief delivers actionable market context.

### Earnings Calendar: Dual-Source (UW + EW) → Cloud SQL
- **Commits**: `1b66a43c`
- **Files**: `scripts/fetch_earnings_calendar.py`, `gcp/schema.sql`, `gcp/deploy.sh`, `.env.example`
- **What Changed**: New `earnings_calendar` table (42 cols) with Unusual Whales calendar + Earnings Whispers strategy picks. EW auth mirrors GAS login flow (cookie/CSRF). GAS tracking columns (strike_hit, day0-5, hit_rsi, etc.) included as NULLable for future backfill.
- **Why**: Earnings data was scattered across JSON files and Google Sheets CSVs with no Cloud SQL persistence.
- **Benefit**: Single source of truth for earnings calendar + strategy picks; enables SQL-based ticker resolution for options fetcher.

### AlphaVantage Earnings as Date-of-Truth (3rd source)
- **Files**: `scripts/fetch_earnings_calendar.py`, `docs/GCP_IMPLEMENTATION_GUIDE.md`
- **What Changed**: Added `fetch_alphavantage_earnings()` that pulls AV `EARNINGS_CALENDAR` (CSV). AV is fetched FIRST and builds a `{ticker: (date, time)}` override map that's applied to UW and EW records before dedup. Added `normalize_earnings_time()` helper that unifies EW's numeric codes (1/2/3) with UW/AV's string vocabulary → `{premarket, intraday, postmarket, unknown}`. Cloud SQL `earnings_calendar` now holds 9,510 rows across 3 sources with 557 ticker/date pairs that overlap across sources (vs 0 before).
- **Why**: EW and UW frequently disagreed on earnings dates (up to 7 days apart) for the same ticker. AV pulls from SEC filings and is authoritative. Without a truth source, dedup on `(ticker, date)` couldn't match rows across sources.
- **Benefit**: Single, consistent earnings calendar. EW keeps strategy picks, UW keeps fundamentals, AV provides coverage + date truth. Downstream consumers (options fetcher, premarket brief) see one unified schedule.

### Earnings Options Fetcher: SQL-Based Ticker Resolution
- **Files**: `gcp/fetchers/fetch_earnings_options.py`, `docs/GCP_IMPLEMENTATION_GUIDE.md`
- **What Changed**: Options fetcher now reads tickers from `earnings_calendar` SQL table (7-day lookahead) instead of GCS/local strategy CSVs. CSVs kept as fallback.
- **Why**: CSV-based ticker loading was broken in Cloud Run (CSVs not synced to GCS), resulting in 0 rows in `earnings_options_snapshots`.
- **Benefit**: Options fetcher automatically picks up tickers from the daily earnings calendar fetch, closing the pipeline gap.

### Options Flow Page Fix
- **Commits**: `828d1f9c`
- **Files**: `platform/api/routers/options.py`
- **What Changed**: Options dates endpoint uses widening-range scan (60d→1y→3y→10y→unbounded) with 12h TTL cache. SPX added to valid tickers.
- **Why**: Cold queries on 40M-row `etf_options_snapshots` timed out on db-g1-small.
- **Benefit**: Options Flow page loads reliably without DB tier upgrade.
# Changelog: 2026-04-14 to 2026-04-20

## Session 1 (2026-04-14)

### Dashboard KPI vs-Week Deltas + Freshness Widget
- **Commits**: `86a9ed2 feat(platform): add pipeline freshness widget and KPI vs-week deltas`
- **Files**: `platform/api/main.py`, `platform/api/routers/health.py` (new), `platform/src/routes/DashboardPage.tsx`, `platform/src/components/dashboard/DataPipelineStatus.tsx` (new), `platform/src/components/shared/MetricCard.tsx`
- **What Changed**: The two "close" KPI cards on the Dashboard no longer show a dead "Regular market close" subtitle. They now show each close's percent delta vs the prior 5-session average close (`+0.42% vs prev 5d avg`), with direction markers on `MetricCard`. The RSI card appends `· +X.X% vs 5d avg` to its zone label using a new `avg_rsi_14` field on the reference endpoint's `week` block. `_fetch_week_range()` also returns `prev_session_close` / `prev_session_date` so the 2-day change KPI no longer depends on Cloud SQL having today's row in sync with AV. A new `DataPipelineStatus` widget at the top of the Dashboard hits `/api/health/freshness` and collapses to a single line when everything is green. `main.py` grew a HEAD / handler and a uvicorn log filter to drop the Codespaces tunnel probe spam.
- **Why**: User screenshot flagged the duplicated "Regular market close" subtitles as wasted surface area. The 2-day change was also broken on days where Cloud SQL lagged AV. The freshness widget closes the silent-outage gap.
- **Benefit**: KPI subtitles now carry information; Dashboard surfaces data pipeline health at a glance.

### SPX Greeks Pipeline (Schema + Fetchers + API + Tests)
- **Commits**: `aa056e9 feat(platform): surface computed Greeks for SPX in options chain`, `b8d86e7 feat(gcp): add SPX Greeks sidecar columns and FRED rates pipeline`, `4c8c833 feat(scripts): add freshness audit, SPX backfill, and Greeks maintenance`, `8583668 feat(workflows): add freshness watchdog and Greeks unit tests`
- **Files**: `gcp/schema.sql`, `gcp/fetchers/fetch_fred_rates.py` (new), `gcp/apply_schema.py` (new), `gcp/deploy.sh`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/fetchers/fetch_market_data.py`, `lib/data_loader.py`, `platform/api/routers/options.py`, `scripts/backfill_spx_from_options.py` (new), `scripts/maintenance/compute_spx_greeks.py` (new), `tests/test_options_greeks.py` (new), `platform/src/stores/tickerStore.ts`, `platform/src/types/index.ts`
- **What Changed**: AV doesn't publish Greeks for cash-settled indexes, so SPX rows arrived with NULL delta/gamma/etc. Added `*_computed` sidecar columns (`delta_computed`, `gamma_computed`, ...) to `etf_options_snapshots` so BSM-computed values live alongside source-provided ones without clobbering provenance. New `daily_rates` table sourced from FRED (DGS3MO risk-free + SP500 dividend yield) feeds the BSM calc. `scripts/backfill_spx_from_options.py` derives SPX daily OHLC from `etf_options_snapshots` via put-call parity — SPX has no AV daily series, so this was the only way to populate `market_data_daily` for SPX. `scripts/maintenance/compute_spx_greeks.py` backfills historical SPX rows with computed Greeks. The options router picks `*_computed` columns for `COMPUTED_GREEKS_TICKERS` and emits them under the canonical `delta`/`gamma`/... keys plus a `greeks_source` provenance field — frontend stays uniform. SPX added to the platform ticker list. Unit tests pin known-good BSM values and put-call parity so sign errors fail CI.
- **Why**: SPX options were unusable because the frontend expected non-null Greeks. Cash-settled index options need local computation with an accurate risk-free rate and dividend yield, which required the FRED pipeline.
- **Benefit**: SPX options chain page renders Greeks; provenance is explicit via `greeks_source`; BSM math is test-pinned.

### Freshness Watchdog + April Gap Incident
- **Commits**: `8583668 feat(workflows): add freshness watchdog and Greeks unit tests`, `b8d86e7` (signal_monitor fail-fast is part of the gcp commit), `0f96850 docs: document data pipeline, codespaces auth, and April gap incident`
- **Files**: `.github/workflows/freshness-watchdog.yml` (new), `scripts/audit_data_freshness.py` (new), `gcp/signal_monitor.py`, `docs/DATA_PIPELINE.md` (new), `docs/incidents/2026-04-14-market-data-daily-gap.md` (new), `docs/claude-code-codespaces-auth.md` (new)
- **What Changed**: `market_data_daily` sat stale for 3 days in early April because nothing was actively checking. The new watchdog runs `audit_data_freshness.py --strict` hourly during active hours and once post-close; any stale table fails the workflow and the existing `handle-workflow-failure` reusable workflow opens a labeled issue with the audit JSON embedded. `signal_monitor.main()` now fails fast on missing `ALPHA_VANTAGE_API_KEY` / Cloud SQL config so Cloud Run surfaces the error instead of looping silently. Incident report captures root cause + fixes. `DATA_PIPELINE.md` documents the canonical fetcher → Cloud SQL → API chain.
- **Why**: Silent Cloud Run failures were the core defect. Fail-fast + hourly audit is the minimum viable detection loop.
- **Benefit**: Next data gap is caught within ~1 hour instead of on user complaint.

### Deploy-Safety Agents + 100-Point Audit Scorecard
- **Commits**: `08a0f81 chore(agents): add reliability, security, and trading review agents`, `dfad892 docs(audit-review): expand to 100-point scorecard across 7 categories`
- **Files**: `.claude/agents/pre-deploy-check.md` (new), `.claude/agents/security-scan.md` (new), `.claude/agents/impact-analyzer.md` (new), `.claude/agents/infra-drift-detector.md` (new), `.claude/agents/test-coverage-analyzer.md` (new), `.claude/agents/trading-logic-reviewer.md` (new), `.claude/agents/debug-local.md` (new), `.claude/agents/workflow-debugger.md`, `.claude/commands/gcp-deploy.md`, `.claude/commands/audit-review.md`
- **What Changed**: Ported a set of AWS-oriented review/debug/deploy agents onto this GCP stack, skipping duplicates. Seven new agents: `pre-deploy-check` (single gate — stale `platform/dist/`, `.env`, Cloud SQL reachability, GCS creds, workflow YAML, schema drift), `security-scan` (secrets/SQLi/SELECT * with GovCloud/PII stripped), `impact-analyzer` (blast radius across lib → routers → React → workflows), `infra-drift-detector` (live Cloud SQL schema vs `gcp/schema.sql` for all 9 tables + Cloud Run config vs `gcp/deploy.sh` + GCS structure + workflow crons), `test-coverage-analyzer` (maps `git diff` to `make test` / `make test-e2e` / `make test-scripts`), `trading-logic-reviewer` (12-check financial correctness: look-ahead, survivorship, data snooping, P&L accounting, risk mgmt, Black-Scholes, Sharpe annualization), `debug-local` (non-workflow runtime errors + NO-SHORTCUTS 5-step protocol + postmortem writer). `workflow-debugger` gained the same NO-SHORTCUTS discipline + postmortem section. `/gcp-deploy` gained Step 0 (invoke `pre-deploy-check`, block on exit 2) and Step 7 (post-deploy Cloud Run health check, new-revision verification via `<script src="/assets/index-*.js">` compare, 2-min error-log tail, rollback command printer). `/audit-review` restructured to delegate to `security-scan` / `data-pipeline-validator` / `test-coverage-analyzer` / `pre-deploy-check` / `infra-drift-detector` and produce a 100-point scorecard across Security (15), Performance (15), Monitoring (15), Data Integrity (15), Docs (10), Testing (20), Deploy Readiness (10), with `AUDIT_BLOCK=true` exit signal for CI.
- **Why**: On 2026-04-14 a `make dev` session showed a stale React UI on port 8000 because FastAPI serves `platform/dist/` via StaticFiles and `npm run build` hadn't been rerun. The `pre-deploy-check` agent's first rule — compare newest mtime in `platform/src/**` to `platform/dist/index.html` — turns that foot-gun into a hard block. The other agents close adjacent gaps (schema drift, missing tests, look-ahead bias in trading logic, silent secrets) that no existing agent covered.
- **Benefit**: Deploys and local prod-mode runs now fail loudly instead of silently serving stale bundles. Financial logic gets a checklist the size of the actual failure modes (look-ahead, survivorship, Black-Scholes units). `/audit-review` scores are comparable across runs and delegate to specialized agents rather than inlining every check. No duplicates were added — existing `code-reviewer`, `workflow-debugger` (now enhanced), `playwright-tester`, `python-code-tester`, `js-code-tester`, `data-pipeline-validator`, `pine-script-reviewer`, `/commit`, `/debug-workflow`, `/validate-data` are all untouched.
