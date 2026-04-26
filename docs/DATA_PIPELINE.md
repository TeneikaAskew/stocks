# Data Pipeline — per-table plan for freshness & reliability

**Last updated:** 2026-04-14 (post-incident, after the April 10 env var regression caused `market_data_daily` to drift)

This doc is the single source of truth for:
- What every Cloud SQL table exists for
- Where each table's data feeds into the platform (UI, scripts, ML models)
- Whether we actually need to persist it or can fetch live
- The scheduled job(s) that populate it, and how we verify freshness

Use it alongside [audit_data_freshness.py](../scripts/audit_data_freshness.py) and [`/api/health/freshness`](../platform/api/routers/health.py) to diagnose any gap.

---

## Guiding principles

1. **AlphaVantage is the only provider.** No Yahoo Finance anywhere in production. Legacy Yahoo rows are archived to `archive_yahoo_*` tables and ignored.
2. **Fresh > complete.** The platform prefers a fresh read over a cached one when the staleness cost is < the API cost. Live quotes bypass Cloud SQL entirely.
3. **Persist only what has training value.** If a consumer only reads "current state" we prefer live API calls. We persist when we need historical snapshots for backtesting, Greeks recomputation, or model training (future).
4. **Fail loud.** Every fetcher fails with a non-zero exit code when prerequisites are missing (env vars, upstream API down). No more silent `exit(0)` while skipping all writes.
5. **One table, one owner.** Each table has exactly one canonical writer. Redundant backup workflows are allowed but must be upsert-idempotent.

---

## Table-by-table plan

### 1. `market_data_daily` ✅ canonical

**Purpose** — Daily OHLCV + 50+ technical indicators (RSI, EMA9/20, SMA200, MACD, Bollinger Bands, ATR, RVOL, Strat candle classification, FTFC score, consecutive up/down) for IWM, SPY, QQQ, SPX.

**Feeds into**
- [DashboardPage.tsx](../platform/src/routes/DashboardPage.tsx) — `/api/dashboard/brief/{ticker}` → the 4 KPI cards at the top, the Daily Bias card, the RSI value, and the "vs 5d avg" subtitles
- [premarket_brief.py](../gcp/premarket_brief.py) — Discord morning brief
- [lib/data_loader.py](../lib/data_loader.py) — backtest dataloaders
- `/api/market/reference/{ticker}/{date}` — prev-day lookups + week range computation

**Alternatives considered** — AlphaVantage `TIME_SERIES_DAILY` is always fresh, but we need the historical series (~11 years back) for backtests and indicator context (250-bar lookback for SMA200). **Persisting is the right call.**

**ML value** — High. Any future swing/daily model trains from this table. Indicator columns are pre-computed so we don't recompute them every training run.

**Canonical writer** — [`gcp/fetchers/fetch_market_data.py`](../gcp/fetchers/fetch_market_data.py) invoked by Cloud Run job `fetch-market-data`
**Schedule** — Cloud Scheduler `fetch-market-data-daily` at **17:00 ET Mon–Fri** (`0 17 * * 1-5 America/New_York`)
**Writes** — Daily row per ticker to `market_data_daily` **AND** full 1-min session to `market_data_intraday` (shared writer)
**Freshness budget** — max 30h after market close (`expected_lag_hours: 30` in audit)

**Reliability improvements from the April 14 incident**
- ✅ Fail-fast guard added: script now exits non-zero when `ALPHA_VANTAGE_API_KEY` or Cloud SQL env vars are missing. See [docs/incidents/2026-04-14-market-data-daily-gap.md](incidents/2026-04-14-market-data-daily-gap.md).
- 🟡 **TODO**: add a Cloud Monitoring alert on `fetch-market-data` execution failures (email or Discord webhook)
- 🟡 **TODO**: add a watchdog GitHub Actions workflow that runs at 23:30 UTC daily — queries `SELECT MAX(date) FROM market_data_daily WHERE ticker='IWM'` and, if the result is < today, re-invokes the Cloud Run job. The fail-fast guard + watchdog means the next incident takes hours to detect instead of days.

**SPX note** — SPX is stuck at 2025-12-17 (pre-existing 4-month gap). SPX is an index with no intraday on AV; the script tries `TIME_SERIES_INTRADAY` for SPX every day and fails, but `TIME_SERIES_DAILY` should still work. Separate investigation needed in the fetcher logic.

---

### 2. `market_data_intraday` ✅ canonical

**Purpose** — 1-min OHLCV bars for IWM, SPY, QQQ (SPX has no intraday from AV). Partitioned by ticker. ~11 years of history, ~1.88M rows per ticker.

**Feeds into**
- [ChartsPage.tsx](../platform/src/routes/ChartsPage.tsx) — `/api/market/data/{ticker}/{date}?timeframe=N` — the candlestick + volume chart. Timeframes 5/15/30/60 are aggregated server-side from 1-min bars via `_aggregate_timeframe()` in [main.py](../platform/api/main.py).
- [DashboardPage.tsx](../platform/src/routes/DashboardPage.tsx) — same endpoint for the PriceAreaChart (hourly bars for the last 2 trading days)
- [LiveMarketPage.tsx](../platform/src/routes/LiveMarketPage.tsx) — review mode (pre-market backfill)
- [signal_monitor.py](../gcp/signal_monitor.py) — rolling 100-bar window for real-time condition evaluation
- [lib/data_loader.py](../lib/data_loader.py) — backtest dataloaders

**Alternatives considered** — AV `TIME_SERIES_INTRADAY` is live for today's bars, but backtests need multi-year intraday history. We **cannot** drop this table.

**ML value** — High. Intraday strategy backtests, market microstructure models, volatility forecasting all need persisted 1-min bars.

**Canonical writer** — Same Cloud Run job as `market_data_daily` (`gcp/fetchers/fetch_market_data.py` writes both tables in a single run)
**Schedule** — Same daily run at 17:00 ET (the fetcher fetches a full day of 1-min bars and upserts them)
**Writes** — ~390-1200 rows per ticker per day (pre + regular + after hours)
**Freshness budget** — 30h max (same as daily)

**Validated today** — The existing script already writes 1-min bars daily. The earlier plan's "Phase B" (add a separate daily backfill) was redundant and was skipped. Confirmed via `SELECT ticker, DATE(ts), COUNT(*) FROM market_data_intraday WHERE DATE(ts) >= '2026-04-01' GROUP BY ...` — every trading day Apr 6–13 has 900-1200 bars.

**Reliability improvements** — Same as `market_data_daily` (shared writer):
- ✅ Fail-fast guard (applies to both tables)
- 🟡 **TODO**: watchdog workflow also queries `MAX(ts)` on intraday to catch daily partial-write failures

---

### 3. `etf_options_snapshots` ⚠️ two writers (intraday + EOD) — consolidation needed

**Purpose** — Options chains (calls + puts, all strikes, all expirations) for SPY, IWM, QQQ, SPX. Includes bid/ask/mark/last, volume/OI, IV, and Greeks (from AV for most; computed via Black-Scholes for SPX/SPXW/NDX where AV doesn't provide them).

**Feeds into**
- [OptionsFlowPage.tsx](../platform/src/routes/OptionsFlowPage.tsx) — `/api/options/dates/{ticker}` + `/api/options/{ticker}/{date}` — full chain display, Greeks, GEX/VEX heatmap
- [lib/options_greeks.py](../lib/options_greeks.py) — reads historical rows, recomputes BSM Greeks for SPX family, writes `*_computed` columns
- [scripts/maintenance/compute_spx_greeks.py](../scripts/maintenance/compute_spx_greeks.py) — batch Greeks recomputation
- Potential future consumer: ML models for options flow analysis

**Alternatives considered** — Your question was whether we can **drop the snapshot history now that AV has daily options** and just fetch live. The answer is **no, we still need the table**:
1. **Backtests** need historical chains to simulate strategy entries/exits across days/weeks
2. **Greeks recomputation** requires the original `underlying_price` and `implied_volatility` from the snapshot moment — we can't recover that from live data
3. **IV evolution studies** (for future ML training) need the full time-series of IV per strike/expiration
4. **Intraday snapshots** (multiple per day) capture how chains evolve with underlying price — essential for gamma scalping / 0DTE strategies

**What was dropped (2026-04-26)** — the intraday 9x/day `fetch-etf-options` Cloud Run job. Daily EOD snapshots from `fetch-av-options-backfill` are sufficient for the vast majority of use cases, and AV is queried live for "current chain" via the existing OptionsFlowPage fallback. See "Deprecated path" below.

**ML value** — High. This is one of the most valuable tables for future options strategy models because options history is hard to buy and AV gives it for free.

**Current writer — single canonical path**

- Script: [`gcp/fetchers/fetch_av_historical_options.py`](../gcp/fetchers/fetch_av_historical_options.py)
- Cloud Run job: `fetch-av-options-backfill`
- Source: AlphaVantage `HISTORICAL_OPTIONS` endpoint
- Schedule: GitHub Actions `fetch-alphavantage-options-daily.yml` at `0 1 * * 1-5` (01:00 UTC = 21:00 ET)
- Writes: one snapshot per ticker per trading day with `data_source='alphavantage'`
- **~40k contracts per day across all 4 tickers**

**Freshness budget** — 30h from EOD run

**Deprecated path (removed 2026-04-26)** — the intraday 9x/day `fetch-etf-options` Cloud Run job (yahooquery) was deleted along with `gcp/fetchers/fetch_etf_options.py`, `scripts/fetch_etf_options_intraday.py`, and `.github/workflows/fetch_etf_options.yml`. The Strat signals on the underlying's OHLC bars across timeframes, so per-option intraday chain snapshots don't add signal — and AV `HISTORICAL_OPTIONS` returns one per-day snapshot per call, not intraday bars, so the 9x/day approach couldn't answer intraday-high/dwell questions anyway. The Options UI queries AV directly for "current chain" when the user wants "right now" data; daily EOD snapshots cover backtest needs.

---

### 4. `earnings_options_snapshots` ✅ canonical (6x/day)

**Purpose** — Options chains for tickers announcing earnings in the next 7 days. Captures IV ramp + post-earnings IV crush. Multiple snapshots per day so we can compare 9:30 AM vs 3:55 PM IV.

**Feeds into**
- [earnings_options_analytics/](../earnings_options_analytics/) — strategy analyzer, win rate, profit factor per strategy (Long Calls, Bull Spreads, Iron Condors, etc.)
- Future: an Earnings page in the platform (per the previous plan) — 4 quarterly EPS cards + grouped bar chart + strategy picks table

**Alternatives considered** — Same as `etf_options_snapshots`. IV crush studies need historical chains; we can't regenerate IV from price alone.

**ML value** — High. Earnings-specific options strategies (long straddle, iron condor, calendar spreads) all benefit from historical IV + outcomes data for training.

**Canonical writer** — [`gcp/fetchers/fetch_earnings_options.py`](../gcp/fetchers/fetch_earnings_options.py)
**Cloud Run job** — `fetch-earnings-options`
**Schedule** — Cloud Scheduler 6x/day during market hours (`0900, 0935, 1000, 1200, 1550, 1630 America/New_York` weekdays)
**Source** — Originally yahooquery with AV fallback. **User preference: AV only.** Need to verify this.
**Writes** — Variable: depends on how many tickers have earnings in the 7-day window (typically 20-50 tickers × 100-500 contracts = 2-25k rows per snapshot, × 6 snapshots = 12k-150k rows/day)
**Freshness budget** — 24h

**Reliability improvements**
1. 🟡 **TODO**: audit the fetcher source — replace any remaining yahooquery calls with AV equivalents
2. 🟡 **TODO**: verify the ticker resolution from `earnings_calendar` (see next table) is pulling the right 7-day window
3. 🟡 **TODO**: confirm the `data_source` column reflects `'alphavantage'` for all new writes

---

### 5. `earnings_calendar` ✅ weekly is fine

**Purpose** — Upcoming and recent earnings announcements. One row per (ticker, earnings_date, data_source) combo — same ticker+date may have 3 rows (AV, UW, EW) capturing different attributes (date of truth from AV, expected move from UW, strategy pick from EW).

**Feeds into**
- [`fetch_earnings_options.py`](../gcp/fetchers/fetch_earnings_options.py) — resolves the 7-day ticker universe
- [`premarket_brief.py`](../gcp/premarket_brief.py) — morning Discord brief ("5 tickers have earnings this week")
- Future: Earnings page ticker dropdown (P1 = EW+AV+UW, P2 = AV+UW)

**Alternatives considered** — Earnings dates are published weeks in advance and rarely change mid-week. Weekly refresh is the right cadence. **Do not promote to daily** — it would waste API calls without adding value.

**ML value** — Medium. Future models might use "days until earnings" as a feature; the calendar enables that.

**Canonical writer** — [`scripts/fetch_earnings_calendar.py`](../scripts/fetch_earnings_calendar.py)
**Schedule** — GitHub Actions `update_economic_events_calendar.yml` at `0 11 * * 0` (Sundays 11:00 UTC = 6 AM EST)
**Sources** — AV `EARNINGS_CALENDAR` endpoint (date of truth) + Unusual Whales CSV (expected moves) + Earnings Whispers CSV (strategy picks, requires login)
**Writes** — ~50-200 rows/week depending on earnings season
**Freshness budget** — 192h (8 days — allows one missed weekly run)

**Reliability improvements**
1. ✅ **Weekly cadence is correct** — per user direction. Do NOT move to daily.
2. 🟡 **TODO**: verify the Sunday job actually runs (the audit shows `fetched_at` of 2026-04-12 which is... Sunday, so yes, it ran)

---

### 6. `earnings_history` 🆕 does not exist yet

**Purpose (planned)** — Last ~20 quarters of reported vs estimated EPS per ticker, for the Earnings Surprise Tracker visual.

**Status** — Not in schema. Designed in the previous earnings page plan as a new table. Lazy-fetched from AV `EARNINGS` endpoint on first request per ticker, cached in Cloud SQL for 24h.

**Canonical writer (planned)** — [`scripts/fetch_earnings_history.py`](../scripts/fetch_earnings_history.py) (not built yet)
**Trigger** — Lazy via the `/api/earnings/{ticker}/history` endpoint when a user first picks that ticker on the Earnings page
**ML value** — Medium. Historical EPS surprise is a classic quant factor.
**Freshness budget** — 90 days (earnings don't change; only add new ones after each announcement)

**Reliability improvements**
1. 🟡 **TODO**: build it (part of the earnings page implementation)

---

### 7. `economic_events` ⚠️ consider dropping the table entirely

**Purpose** — FOMC meetings, CPI releases, NFP, etc. Forward-looking calendar for news-avoidance.

**Feeds into**
- [`premarket_brief.py`](../gcp/premarket_brief.py) — "this week's macro events" in the Discord brief

**Alternatives considered** — Every consumer only reads **future** events. No ML model trains on historical macro releases (the outcomes are not in the table — only scheduled events). **This is the one table in the whole pipeline that could genuinely be replaced with a live fetch.**

**ML value** — Low. Scheduled events without outcomes aren't useful for training. Historical "actual vs forecast" from FRED would be more valuable and is a different data source.

**Canonical writer** — [`scripts/fetch_economic_calendar.py`](../scripts/fetch_economic_calendar.py) + [`gcp/fetchers/fetch_economic_events.py`](../gcp/fetchers/fetch_economic_events.py)
**Schedule** — Weekly, bundled into `update_economic_events_calendar.yml`
**Freshness budget** — 192h

**Proposed changes**
1. 🟡 **Option A (recommended)**: Keep the weekly refresh as-is. It's low-volume and the cost is ~1 API call per week. Not worth the refactor.
2. 🟡 **Option B**: Drop the table entirely and fetch live from FRED or Trading Economics when the premarket brief generator runs. Saves ~200 rows/week of storage. Minor benefit.
3. **Decision**: stay with Option A. Don't touch it.

---

### 8. `premarket_analysis` ✅ canonical

**Purpose** — Pre-market snapshot computed at 5 PM ET (after market close, for the NEXT day's open). Captures RSI, EMA positions, Strat classification, FTFC score, signal status. One row per (ticker, analysis_date).

**Feeds into**
- [DashboardPage.tsx](../platform/src/routes/DashboardPage.tsx) — `/api/dashboard/brief/{ticker}` (the brief endpoint surfaces premarket_analysis rows)
- [premarket_brief.py](../gcp/premarket_brief.py) — Discord brief generator (both writer and reader)

**Alternatives considered** — Computed from `market_data_daily` so we COULD recompute on demand. But the analysis is deterministic given the inputs, and caching saves CPU on every Dashboard load. **Keep persisted.**

**ML value** — Low-medium. The fields are all derived from market_data_daily so a model would just read the source directly.

**Canonical writer** — [`gcp/premarket_brief.py`](../gcp/premarket_brief.py)
**Cloud Run job** — `premarket-brief`
**Schedule** — Cloud Scheduler at 08:30 ET Mon–Fri (before market open)
**Freshness budget** — 30h

**Reliability improvements**
1. 🟡 **TODO**: confirm the `premarket-brief` Cloud Run job has the required env vars (avoid a repeat of the April 10 regression). Same fail-fast guard should apply.
2. 🟡 **TODO**: verify the Cloud Scheduler `premarket-brief-daily` is enabled and firing

---

### 9. `signal_alerts` 🔴 currently empty — env var regression

**Purpose** — Automated intraday signal firings (CALL/PUT, score ≥ threshold, conditions met). Generated by `signal_monitor` polling every 60s during market hours.

**Feeds into**
- Internal only (no frontend route displays it directly)
- Historical signal quality analysis (retrospective)
- Potential future Signals page

**Alternatives considered** — Signals are generated in real-time and must be persisted. No live alternative.

**ML value** — High if we keep populating it — historical signal firings + their outcomes (which trades fired them, whether those trades won) are the raw material for signal-quality ML models.

**Canonical writer** — [`gcp/signal_monitor.py`](../gcp/signal_monitor.py)
**Cloud Run job** — `signal-monitor`
**Schedule** — Cloud Scheduler `signal-monitor-daily` at 09:25 ET Mon–Fri. Polls for ~6.5 hours during market hours.
**Freshness budget** — 30h

**Current status** — Table has **zero rows** ever. Same April 10 env var regression affected this Cloud Run job — the 2.5-hour polling loop on April 13 13:25-16:00 UTC logged "No AV API key — cannot fetch" every minute and exited without writing anything. The env vars are now set correctly, so the next scheduled run (April 14 13:25 UTC) should populate it.

**Reliability improvements**
1. ✅ Same fail-fast guard as `fetch_market_data.py` should be added to `signal_monitor.py` — if `ALPHA_VANTAGE_API_KEY` is missing, exit non-zero immediately instead of polling for 2.5 hours with no data
2. 🟡 **TODO**: verify the April 14 13:25 UTC run populates the table with at least 1 row
3. 🟡 **TODO**: add the watchdog audit to flag this if it stays empty past tomorrow

---

### 10. `trades` ✅ canonical (when signal_monitor works)

**Purpose** — Automated trade log: entry/exit times, prices, P&L %, strategy combo, FTFC direction. Written by the signal monitor when a signal fires AND meets entry criteria.

**Feeds into**
- [BacktesterPage.tsx](../platform/src/routes/BacktesterPage.tsx) — reads via `/api/backtest/*` which currently points to GCS parquets, not Cloud SQL. There's a dual-write pattern where trade results land in both.
- Future: automated trade tracking dashboard

**Alternatives considered** — Trade records are authoritative; must persist.

**ML value** — Very high. Trade outcomes are the supervised labels for any trading strategy ML model.

**Canonical writer** — [`gcp/trade_logger.py`](../gcp/trade_logger.py) (invoked by `signal_monitor.py`)
**Schedule** — Continuous during market hours (tied to signal_monitor lifecycle)
**Freshness budget** — Depends on market activity; can be 0 rows on a quiet day

**Reliability improvements**
1. Same as `signal_alerts` — the April 10 env var regression also killed trade writes since `trade_logger` is invoked by `signal_monitor`. Fix cascades.
2. 🟡 **TODO**: verify trades table gets populated once signal_monitor resumes normal operation

---

### 11. `journal_entries` ✅ canonical, user-authored

**Purpose** — Manual trade journal (user-authored). Separate from `trades` (automated) and `signal_alerts` (monitor). Used for notes, reflection, performance review.

**Feeds into**
- [JournalPage.tsx](../platform/src/routes/JournalPage.tsx) — `/api/journal/trades/{ticker}` (GET/POST/DELETE via `journal.py` router)
- Local JSON fallback at `data/journal/{ticker}_journal.json` when Cloud SQL is unreachable

**Alternatives considered** — User data, no external source. Must persist.
**ML value** — Low (subjective free-text notes).
**Canonical writer** — User via the Journal page UI
**Freshness budget** — N/A (user-driven)
**Reliability improvements** — None needed; works correctly.

---

### 12. `daily_rates` 🔴 table doesn't exist

**Purpose (planned)** — Risk-free rate (3-month US Treasury, `DGS3MO`) + S&P 500 dividend yield, from FRED. Used by the Black-Scholes Greeks computer for options where AV doesn't supply Greeks (SPX, SPXW, NDX, RUT, XSP).

**Feeds into**
- [`lib/options_greeks.py`](../lib/options_greeks.py) — reads rate as of a specific date when recomputing historical BSM Greeks
- [`gcp/fetchers/fetch_fred_rates.py`](../gcp/fetchers/fetch_fred_rates.py) — the intended writer
- [`scripts/audit_data_freshness.py`](../scripts/audit_data_freshness.py) — detects the missing table

**Current status** — The fetcher script exists but the **table has never been created in `gcp/schema.sql`**. All Greeks recomputation currently falls back to a hardcoded risk-free rate (probably 5% or whatever the default is in `options_greeks.py`), which is slightly inaccurate but not catastrophic.

**Canonical writer (planned)** — [`gcp/fetchers/fetch_fred_rates.py`](../gcp/fetchers/fetch_fred_rates.py)
**Cloud Run job (not yet created)** — `fetch-fred-rates`
**Proposed schedule** — Daily at 18:00 ET (after FRED publishes daily rates, which happens around 4 PM ET)
**Freshness budget** — 72h (FRED has a 1-2 day publishing lag)

**Proposed changes**
1. 🔴 **Add the `daily_rates` table definition** to [gcp/schema.sql](../gcp/schema.sql):
   ```sql
   CREATE TABLE IF NOT EXISTS daily_rates (
     date             DATE PRIMARY KEY,
     dgs3mo           DOUBLE PRECISION,   -- 3-month Treasury yield (%)
     sp500_div_yield  DOUBLE PRECISION,   -- S&P 500 dividend yield (%)
     fetched_at       TIMESTAMPTZ DEFAULT NOW(),
     data_source      VARCHAR(30) DEFAULT 'fred'
   );
   ```
2. 🔴 **Run the migration** against the production Cloud SQL database: `psql ... -f gcp/schema.sql` (the `CREATE TABLE IF NOT EXISTS` is idempotent)
3. 🟡 **Backfill** via `python scripts/fetch_fred_rates.py --backfill` (one-time)
4. 🟡 **Create a Cloud Run job** `fetch-fred-rates` + Cloud Scheduler entry at 18:00 ET daily
5. 🟡 **Update `options_greeks.py`** to actually read from the new table instead of the hardcoded fallback

---

## Summary — what's healthy vs what needs work

| Table | Canonical writer | Schedule | Status today |
|---|---|---|---|
| `market_data_daily` | fetch-market-data Cloud Run | 17:00 ET Mon-Fri | ✅ OK (April 14 run will confirm) |
| `market_data_intraday` | (same writer) | (same schedule) | ✅ OK |
| `etf_options_snapshots` | fetch-av-options-backfill | 01:00 UTC Mon-Fri | ⚠️ Needs verify — ensure automation actually runs daily |
| `earnings_options_snapshots` | fetch-earnings-options Cloud Run | 6x/day during market hours | ⚠️ Warn — last row April 12, need April 13 |
| `earnings_calendar` | update_economic_events_calendar GH workflow | Weekly Sundays 6 AM EST | ✅ OK |
| `earnings_history` | (not built) | (lazy on first UI request) | 🆕 Not yet built |
| `economic_events` | update_economic_events_calendar GH workflow | Weekly Sundays 6 AM EST | ✅ OK — keep as-is, don't drop |
| `premarket_analysis` | premarket-brief Cloud Run | 08:30 ET Mon-Fri | ✅ OK (needs env var fail-fast too) |
| `signal_alerts` | signal-monitor Cloud Run | 09:25-16:00 ET Mon-Fri | 🔴 Empty — April 10 regression, self-heal tomorrow |
| `trades` | trade-logger (via signal-monitor) | (same lifecycle) | 🔴 Same root cause as signal_alerts |
| `journal_entries` | User via UI | On-demand | ✅ OK |
| `daily_rates` | fetch-fred-rates Cloud Run (not built) | Daily 18:00 ET (planned) | 🔴 **Table doesn't exist** |

---

## Action items — prioritized

### P0 — Fix today or tomorrow
- [x] Backfill `market_data_daily` April 13 (done)
- [x] Add fail-fast guard to `fetch_market_data.py` (done)
- [x] Backfill `etf_options_snapshots` April 13 for all 4 tickers (done)
- [ ] Add fail-fast guard to `signal_monitor.py` — same pattern as market data
- [ ] Confirm April 14 17:00 ET scheduled run of `fetch-market-data` populates today's row
- [ ] Confirm April 14 09:25 ET scheduled run of `signal-monitor` populates `signal_alerts` with at least 1 row

### P1 — This week
- [ ] Add the `daily_rates` table to schema + migrate + backfill via FRED + create Cloud Run job
- [ ] Create a Cloud Monitoring alert policy on Cloud Run job execution failures for: `fetch-market-data`, `fetch-earnings-options`, `signal-monitor`, `premarket-brief`, `fetch-av-options-backfill`. Alert to Discord webhook.
- [x] **Done 2026-04-26**: removed `fetch-etf-options` (the 9x/day intraday Cloud Run job with the `ticker='ALL'` bug) along with the fetcher + workflow files. Daily EOD via `fetch-av-options-backfill` is the canonical writer.
- [ ] Investigate the SPX 4-month gap in `market_data_daily` (separate incident)
- [ ] Verify `fetch_earnings_options.py` uses AV, not yahooquery, for ticker resolution

### P2 — Watchdog layer
- [ ] Build `.github/workflows/freshness-watchdog.yml` that runs every hour and invokes `python scripts/audit_data_freshness.py --strict`. On failure, the existing `handle-workflow-failure.yml` reusable workflow auto-creates a GitHub issue with the full table status.
- [ ] Add a "trigger fetcher from audit" feature — when the audit finds a stale table, it could emit a structured JSON with the missing dates, and a follow-up workflow invokes the appropriate Cloud Run job with `--date` args. Fully automated recovery for env-var-style regressions.

### P3 — Nice to have
- [ ] Build `earnings_history` table + AV `EARNINGS` fetcher (part of earnings page work)
- [ ] Document the Cloud Run job env var contract in a shared deployment script so any recreation of a job automatically includes all required secrets (avoid repeating April 10)

---

## How to run the audit

```bash
# CLI — pretty table
set -a && source .env && set +a
python3 scripts/audit_data_freshness.py

# JSON for CI / scripting
python3 scripts/audit_data_freshness.py --json

# Strict mode — exit 1 if anything is stale (for watchdog workflows)
python3 scripts/audit_data_freshness.py --strict

# From the UI: the DataPipelineStatus widget at the top of the Dashboard
# hits /api/health/freshness and auto-refreshes every 5 minutes.

# Force a fresh API read (bypass 5-min TTL cache):
make stop && make dev
```

See also [docs/incidents/2026-04-14-market-data-daily-gap.md](incidents/2026-04-14-market-data-daily-gap.md) for the post-mortem that motivated this plan.

---

## Active monitoring

Reactive freshness (dashboard widget) is not enough — the April 10 regression sat silent for 3 days. Active monitoring layers:

### 1. `freshness-watchdog.yml` GitHub workflow
Runs `python scripts/audit_data_freshness.py --strict` hourly during active hours plus once nightly. Any `stale` table fails the workflow, which the existing `handle-workflow-failure.yml` reusable workflow turns into a labeled GitHub issue (`workflow-failure,freshness,automated`). Duplicate runs comment on the existing open issue instead of spamming.

Expanded audit checks (as of 2026-04-14):
- **Lag from most recent trading close** (original check)
- **Row-count floor per day** (`min_rows_per_day`) — catches "fetcher ran but wrote 0 rows"
- **Gap scan over last 5 trading days** — catches mid-window holes even when yesterday is fresh
- **Value sanity** — `high >= low`, non-negative volume, SPX close within 1000–20000, non-positive options strike rejection

### 2. Cloud Monitoring alert policies (recommended)
Cover the 5 critical Cloud Run jobs (`fetch-market-data`, `fetch-av-options-backfill`, `signal-monitor`, `premarket-brief`, `fetch-earnings-options`). One policy per job on job execution failure:

```bash
gcloud alpha monitoring policies create \
  --project=adept-mountain-474619-d4 \
  --display-name="Cloud Run Job Failed: fetch-market-data" \
  --condition-display-name="Failed task attempts > 0" \
  --condition-filter='metric.type="run.googleapis.com/job/completed_task_attempt_count" AND resource.labels.job_name="fetch-market-data" AND metric.labels.result="failed"' \
  --condition-threshold-value=0 \
  --condition-threshold-comparison=COMPARISON_GT \
  --condition-threshold-duration=60s
```

Skipped-execution (scheduler didn't fire) is caught by the freshness watchdog instead — it's simpler to check "did the data land" than to derive "did the scheduler fire" from GCP metrics.

### 3. SPX parity ordering constraint
`gcp/fetchers/fetch_market_data.py::process_spx_via_parity` derives SPX daily close via put-call parity from `etf_options_snapshots`. The options backfill job (`fetch-av-options-backfill`, ~01:00 UTC) **must** run before the daily fetcher (`fetch-market-data-daily`, 17:00 ET / 21:00 UTC) for the same calendar day. Current ordering gives a 20+ hour buffer.

If the options backfill is ever moved later, update the daily fetcher schedule to run after it, or SPX will be 1 day behind the ETFs.

### 4. Paused buggy intraday options schedulers (2026-04-14)
The 9 `etf-options-*` intraday Cloud Scheduler triggers (9:30/9:35/9:40/10:00/11:30/13:00/14:30/15:30/16:05 ET) were paused on 2026-04-14. They had been silently broken since 2026-04-10 14:00 UTC (the same env-var regression incident) and wrote `data_source=NULL` rows which duplicated the reliable AV EOD backfill (`fetch-av-options-backfill`, 01:00 UTC). Re-enable only if real intraday options data is needed beyond the live AV API path.
