# Track A — Foundation: Watchlist & Data Pipeline Health

**Eval window:** 2026-05-04 → 2026-05-07 (4 trading days)
**Date written:** 2026-05-08
**Branch:** `claude/trading-audit-plan-Ou627`
**Verdict:** **BROKEN** — daily ETF data pipeline is silently frozen on 2026-04-27; SPX intraday partition is empty; ~76% of `signal_alerts` over the eval window lack exits. Foundation cannot be trusted by Tracks B/C/D/E without remediation.

---

## TL;DR — what's actually broken

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | `fetch-market-data` Cloud Run Job has hardcoded `--date=2026-04-27`. It re-fetches April 27's data every night. | **P0** | `gcloud run jobs describe` output |
| 2 | SPY/IWM/QQQ have **zero** real daily rows for 2026-04-28 through 2026-05-07 (8 trading days). Only NULL placeholder rows from 2026-05-08. | **P0** | `market_data_daily` queries |
| 3 | `premarket_analysis` rows for 5/4–5/7 contain **identical** RSI/strat/FTFC values across all 4 days. Brief is reading 4/27 data and emitting the same call every morning. | **P0** | `premarket_analysis` queries (see below) |
| 4 | SPX intraday partition (`market_data_intraday_spx`) is **completely empty** — 0 rows ever inserted. Dec 2025 SPX gap is therefore not "open"; the partition was never populated. | **P0** | `MIN/MAX(ts), COUNT(*)` returned NULL/NULL/0 |
| 5 | 76% of `signal_alerts` rows over the entire 50-day history have NULL `exit_ts`. Same-day (5/7) exits ARE backfilled (360/386), but 5/1–5/6 exits never get written. | **P0** | `signal_alerts` queries |
| 6 | `ticker_calibration` is stale: latest entry is 2026-05-04 with 60-day lookback. Was supposed to refresh quarterly per scheduler `calibrate-thresholds-quarterly`. | **P2** | `ticker_calibration` queries |
| 7 | All major fetcher GitHub Actions workflows (`analyze-market-data`, `daily-insight-reports`, `freshness-watchdog`, `validate-market-data`, etc.) are `disabled_manually`. Pipeline migrated to Cloud Run Jobs/Schedulers. | INFO | GitHub `actions/workflows` API |

---

## 1. Watchlist state — HEALTHY

**Query:** `SELECT user_id, ticker, in_brief, in_insight, signals, removed_at FROM watchlists`

| Metric | Count |
|---|---|
| Total active rows | 18 |
| `signals=true` | 3 (SPY, IWM, QQQ) |
| `in_brief=true` | 5 (IWM, MSFT, QQQ, SPY, ZS — including 1 soft-deleted) |
| `in_insight=true` | 5 |
| Soft-deleted (`removed_at IS NOT NULL`) | 2 (MSFT, ZS) |

**Findings:**
- SPY/IWM/QQQ correctly carry all three surface flags (`in_brief=true`, `in_insight=true`, `signals=true`). Track E's per-ticker work has the right ticker set.
- 13 rows are inactive on every surface (`signals=false, in_brief=false, in_insight=false`) — mostly seeded peer/discord-replay names (AVGO, AMD, ANET, ARM, ASTX, etc.). Not actively consumed but not soft-deleted either.
- 2 soft-deleted rows (MSFT, ZS) still appear in the table. CLAUDE.md flags this as a cleanup item, not a correctness issue.
- **Backlog item**: hard-delete the 2 soft-deleted rows; review the 13 dormant peer rows and either flip a flag on or hard-delete.

---

## 2. Daily data freshness — BROKEN (root cause: frozen scheduler arg)

**Query:** `SELECT ticker, date FROM market_data_daily WHERE ticker IN ('SPY','IWM','QQQ') AND date >= '2026-04-01'`

```
SPY/IWM/QQQ have rows ONLY for these dates between 2026-04-01 and 2026-05-08:
  2026-04-01, 04-02, 04-06, 04-07, 04-08, 04-09, 04-10, 04-13, 04-24, 04-27, 05-08

Missing trading days:
  2026-04-14, 04-15, 04-16, 04-17, 04-20, 04-21, 04-22, 04-23  (8 days)
  2026-04-28, 04-29, 04-30, 05-01, 05-04, 05-05, 05-06, 05-07  (8 days)

Last row with non-NULL close: 2026-04-27
2026-05-08 row exists but close, rsi_14, atr_14, vwap, volume are ALL NULL (placeholder).
```

**Root cause:** `fetch-market-data` Cloud Run Job is configured with `--date=2026-04-27` baked in:

```bash
$ gcloud run jobs describe fetch-market-data --region=us-east1 \
    --format="value(spec.template.spec.template.spec.containers[0].args)"
--date=2026-04-27
```

The scheduler `fetch-market-data-daily` (cron `0 23 * * 1-5`) fires nightly at 23:00 UTC, calls the job, and the job re-fetches the same April 27 data every time. From the execution log, the job has run successfully 11 times since 2026-04-29 — every run completed `True`, but every run targeted April 27.

**Why other tickers show rows for May 4–7 anyway:** they don't. The `data_source` breakdown on May 4–7 rows is:
```
data_source       rows
NULL              731    ← placeholder rows, no real OHLCV
fred              8
alphavantage      6      ← only the May 8 SPY/IWM/QQQ NULL placeholders
```

Spot-check on AAPL confirmed: `inserted_at` for AAPL 2026-04-28 through 2026-05-01 rows is `2026-05-01 22:01:39` with `data_source=NULL` — these are placeholder rows created by an unrelated upsert (probably the earnings calendar fetcher inserting `(ticker, date)` keys without payload). They have no close, no indicators.

**Impact:** Every downstream consumer of `market_data_daily` for SPY/IWM/QQQ has been reading 2026-04-27 data since 2026-04-28. This includes the brief, the insight pipeline, signal_monitor's `total_score` denominators, and anything that joins on prior-close.

**Backlog (P0):**
1. Remove `--date=2026-04-27` from the Cloud Run Job spec — the job should default to `today` per `fetch_market_data.py:814` (`fetch_date = args.date or datetime.now(_ET).date().strftime('%Y-%m-%d')`).
2. Backfill SPY/IWM/QQQ daily rows for 2026-04-28 through 2026-05-07 (8 days) using `gcp/backfill_ticker.py` or a manual job invocation with `--date=YYYY-MM-DD --tickers="SPY IWM QQQ"`.
3. Re-run the prior gap (2026-04-14 → 2026-04-23, 8 days). This second gap predates this audit but is in the same table.
4. Add a freshness-watchdog assertion: `MAX(date) FROM market_data_daily WHERE ticker IN ('SPY','IWM','QQQ') AND close IS NOT NULL` should be ≥ today − 1 trading day, else page.
5. Hard-delete the 731 NULL-payload placeholder rows for May 4–7 once real data lands (they're worse than nothing — they hide the gap from daily-row-count checks).

---

## 3. Daily indicators — BROKEN (consequence of #2)

**Query:** `SELECT ticker, MAX(date) FROM market_data_daily WHERE rsi_14 IS NOT NULL GROUP BY ticker`

| Ticker | Last date with `rsi_14 IS NOT NULL` |
|---|---|
| SPY | 2026-04-27 |
| IWM | 2026-04-27 |
| QQQ | 2026-04-27 |

Since `compute_and_upsert_daily_indicators()` runs *after* the OHLCV upsert in `process_ticker()` (`fetch_market_data.py:467`), it never gets a chance to compute fresh values. All 50+ indicator columns (rsi_14, atr_14, vwap, ma_20, ema_9, etc.) are stuck on April 27 values for the ETFs.

---

## 4. Premarket brief is using stale daily inputs — WORKING WITH BAD INPUTS

**Query:** `SELECT analysis_date, ticker, signal_status, strat_candle, ftfc_score, rsi, change_pct FROM premarket_analysis WHERE analysis_date BETWEEN '2026-05-04' AND '2026-05-07' AND ticker IN ('SPY','IWM','QQQ')`

| analysis_date | ticker | signal_status | strat_candle | ftfc_score | rsi | change_pct |
|---|---|---|---|---|---|---|
| 2026-05-04 | IWM | PUT setup (3/5) | 2U | 1.0 | 72.778 | 0.177 |
| 2026-05-05 | IWM | PUT setup (3/5) | 2U | 1.0 | 72.778 | 0.177 |
| 2026-05-06 | IWM | PUT setup (3/5) | 2U | 1.0 | 72.778 | 0.177 |
| 2026-05-07 | IWM | PUT setup (3/5) | 2U | 1.0 | 72.778 | 0.177 |
| 2026-05-04 | QQQ | PUT setup (3/5) | 1 | 0.0 | 76.878 | 0.053 |
| 2026-05-05 | QQQ | PUT setup (3/5) | 1 | 0.0 | 76.878 | 0.053 |
| 2026-05-06 | QQQ | PUT setup (3/5) | 1 | 0.0 | 76.878 | 0.053 |
| 2026-05-07 | QQQ | PUT setup (3/5) | 1 | 0.0 | 76.878 | 0.053 |
| 2026-05-04 | SPY | PUT setup (4/5) | 2U | 1.0 | 73.774 | 0.172 |
| 2026-05-05 | SPY | PUT setup (4/5) | 2U | 1.0 | 73.774 | 0.172 |
| 2026-05-06 | SPY | PUT setup (4/5) | 2U | 1.0 | 73.774 | 0.172 |
| 2026-05-07 | SPY | PUT setup (4/5) | 2U | 1.0 | 73.774 | 0.172 |

Every value (RSI, candle, FTFC, change%) is byte-identical across all 4 days for each ticker — the brief is computing identical analyses because its inputs (`market_data_daily` rows) haven't changed since April 27.

The `premarket-brief` Cloud Run Job ran successfully every morning (8:30 AM EDT, 12:30 UTC), but **all 12 outputs are stale-data echoes**. Track B will need to flag every brief from 5/4–5/7 as untrustworthy.

**Backlog (P0):** the brief should either (a) refuse to run when its inputs are >1 trading day stale, or (b) emit a banner ("WARNING: daily indicators last refreshed 2026-04-27") so a human catches it. CLAUDE.md production-grade rule #4 ("Resilient to bad data — log a warning and skip") was violated here — the brief silently shipped 4 wrong calls.

---

## 5. Insight pipeline ran — VERDICT FROM TRACK A: WORKING (but probably also stale-input)

**Query:** `SELECT ticker, status, started_at, finished_at, error FROM insight_runs WHERE created_at >= '2026-05-04'`

```
2026-05-04: IWM done, QQQ done, SPY done    (12:45–12:46 UTC)
2026-05-05: IWM done, QQQ done, SPY done
2026-05-06: IWM done, QQQ done, SPY done
2026-05-07: IWM done, QQQ done, SPY done
2026-05-08: IWM done, QQQ done, SPY done    (today, also ran)
```

15 runs total, all `status=done`, no errors. **Track C** owns the deeper question of whether the insights themselves are correct — but the same stale-daily-data problem from §4 is almost certainly contaminating insight outputs as well, since the agent context summarizers in `lib/agents/summarizers.py` read from `market_data_daily`.

(Note: my initial query missed the May 7 row because `as_of` is a `timestamp with time zone` and `BETWEEN '2026-05-04' AND '2026-05-07'` resolves the upper bound to `2026-05-07 00:00:00`, which excludes the 12:45 row. The insight run table confirmed all 5 days fired.)

---

## 6. Intraday data coverage — MOSTLY HEALTHY (one gap on IWM)

**Query:** `SELECT DATE(ts AT TIME ZONE 'America/New_York') AS session, COUNT(*) bars FROM market_data_intraday_<ticker> WHERE ts BETWEEN '2026-05-04' AND '2026-05-08' GROUP BY session`

| Ticker | 2026-05-04 | 2026-05-05 | 2026-05-06 | 2026-05-07 | Expected (extended hours, 04:00–20:00) |
|---|---|---|---|---|---|
| SPY | 961 | 961 | 961 | 961 | ~961 ✅ |
| QQQ | 960 | 960 | 960 | 960 | ~961 ✅ |
| IWM | **884** | 904 | 910 | 902 | ~961 — under-coverage especially 5/4 |
| SPX | 0 | 0 | 0 | 0 | n/a (partition empty — see §7) |

- IWM 2026-05-04 has 884 bars vs SPY/QQQ 961: ~77 bars missing. That's ~77 minutes of gaps. May 4 was a Monday — could be early-session AV outage on IWM only. Worth investigating but lower-priority than #2.
- All `data_source = 'alphavantage'`, no Yahoo fallback rows.
- Bar range is 04:00 ET to ~19:59 ET (full extended-hours session, not just RTH 9:30–16:00). Note that signal_monitor only consumes RTH bars, so the partial coverage outside RTH doesn't directly affect signals.

**Backlog (P2):** Investigate IWM 5/4 missing 77 minutes — check `fetch-alphavantage-intraday` logs for that timestamp range.

---

## 7. SPX intraday — COMPLETELY EMPTY

```sql
SELECT MIN(ts), MAX(ts), COUNT(*) FROM market_data_intraday_spx;
-- Result: NULL, NULL, 0
SELECT MIN(ts), MAX(ts), COUNT(*) FROM market_data_intraday WHERE ticker='SPX';
-- Result: NULL, NULL, 0
```

The `market_data_intraday_spx` partition has never received a row. The "Dec 2025 SPX gap" referenced in the audit plan is actually a complete absence — not a gap that closed.

The daily SPX rows (15 days in 2026-04-27 through 2026-05-07) come from `data_source='fred'` (8 rows of FRED rate-style daily data) + recent unsourced rows. Daily SPX is partial, intraday SPX is nonexistent.

**Backlog (P1):** Decide whether SPX intraday is needed. If yes, configure an Alpha Vantage / IEX / IBKR feed for `^GSPC` or equivalent and add it to `fetch-alphavantage-intraday`. If no, remove SPX from the intraday-consumers' tickers list (signal_monitor doesn't currently surface SPX signals, so this is mostly a documentation cleanup).

---

## 8. Signal-alerts exit-tracking — BROKEN (76% missing exits)

**Query:** `SELECT alert_date, COUNT(*) AS rows, COUNT(*) FILTER (WHERE exit_ts IS NOT NULL) AS exited FROM signal_alerts WHERE alert_date >= '2026-04-15' GROUP BY alert_date`

| alert_date | total alerts | exited | exited_pct |
|---|---|---|---|
| 2026-05-01 | 355 | 0 | **0%** |
| 2026-05-04 | 79 | 0 | **0%** |
| 2026-05-05 | 155 | 0 | **0%** |
| 2026-05-06 | 162 | 0 | **0%** |
| 2026-05-07 | 386 | 360 | 93% |
| 2026-05-08 (partial) | (live) | (live) | n/a |

History-wide: 1,569 alerts since 2026-03-19, of which only **360 (23%) have a populated `exit_ts`**. Per-ticker:

| Ticker | rows | exited | exit% |
|---|---|---|---|
| SPY | 553 | 131 | 23.7% |
| QQQ | 536 | 131 | 24.4% |
| IWM | 488 | 98 | 20.1% |

**Hypothesis (must be confirmed by Track D):** `signal_monitor.py` only resolves exits for alerts created in the *same session* it's running. When the monitor stops at 4 PM, alerts opened that day get exit-resolved before shutdown — but if any alert is still open when the next session starts (or if the resolver is a separate end-of-day step that's been failing silently), it never gets backfilled. The May 7 row breaks the pattern (93% exited), suggesting the resolver started running consistently *that day* but isn't going back over older signals.

**Impact on Track E:** the per-ticker calibration script must **recompute exits from intraday bars** rather than rely on `exit_ts`/`exit_return_pct` columns — otherwise win-rate stats will be computed on only 23% of the data and biased toward recent (May 7) signals.

**Backlog (P0):**
- Add a daily end-of-day Cloud Run Job (`signal-monitor-eod-resolver` or similar) that scans `signal_alerts WHERE is_open IS TRUE OR exit_ts IS NULL` for the prior trading day, replays the global exit logic against `market_data_intraday`, and writes back `exit_ts`, `exit_reason`, `exit_price`, `exit_return_pct`, `is_open=false`.
- One-time backfill over the 1,209 alerts (1,569 − 360) currently lacking exits.

---

## 9. Cloud Run Jobs — RUNNING, but invocation args worth auditing

| Job | Last 5 runs | Status | Note |
|---|---|---|---|
| `fetch-market-data` | daily 4/29–5/8 | All `Completed True` | **Args frozen on `--date=2026-04-27`** (the actual bug from §2) |
| `fetch-alphavantage-intraday` | 5/2, 5/8 only | OK on 5/8, 5/2 | 4/2 and 3/2 were `Completed False`. Cron is monthly (`0 21 * * 2-6` is wrong for monthly — let me re-check). |
| `fetch-fred-rates` | daily | All True | Healthy |
| `premarket-brief` | daily | All True | Inputs broken (§4), output infected |
| `insight-pipeline` | daily | All True | Inputs likely also stale (§5) |
| `signal-monitor` | every 15min | Mostly True | One in-flight at write time; otherwise green |

`av-intraday-nightly` scheduler is `0 21 * * 2-6` = nightly at 21:00 UTC. But the execution history only shows runs on 5/2 and 5/8 — not 5/4–5/7. **That's another active fetcher gap to investigate.** This is suspicious — either the scheduler isn't actually firing the job, or the job is failing silently before completing. Worth a separate investigation.

**Backlog (P1):** Audit `av-intraday-nightly` scheduler: it should have triggered on Mon-Fri (Tue–Sat in UTC). Last 7 days only show 2 runs.

---

## 10. GitHub Actions workflow inventory

```
disabled_manually  Analyze Market Data
disabled_manually  Daily AI Insight Reports
disabled_manually  Download Google Sheets Data
disabled_manually  Earnings Options Analytics
disabled_manually  Fetch Monthly Alpha Vantage Intraday Data
disabled_manually  Fetch Daily Alpha Vantage Options Data
disabled_manually  Fetch News Sentiment
disabled_manually  Freshness Watchdog
disabled_manually  Test Failure Handler
disabled_manually  Validate Market Data
active             Backtest Pipeline
active             DB Query
active             Handle Workflow Failure
active             Monthly architecture doc refresh
```

The pipeline has migrated from GitHub Actions to Cloud Run Jobs/Schedulers (per CLAUDE.md). Most `disabled_manually` workflows are vestigial. The `Freshness Watchdog` workflow being disabled is notable — that was the system that *should* have caught the §2 frozen-date bug. **If a freshness watchdog had been running daily, it would have alerted on 2026-04-28 when SPY's last close was still 2026-04-27.**

**Backlog (P1):** Re-enable `Freshness Watchdog` (or migrate it to a Cloud Run Job equivalent). It was the missing immune-system response that let this 11-day data-freeze go undetected.

---

## Foundation Verdict

**BROKEN.** Tracks B/C/D/E should be aware:

1. **Daily indicators for SPY/IWM/QQQ are frozen on 2026-04-27.** Any analysis that joins to `market_data_daily` for those tickers reflects April 27, not May 4–7. Brief outputs for 5/4–5/7 are demonstrably stale (§4 — identical RSI/strat/FTFC across 4 days).
2. **Intraday is OK** for SPY/QQQ (961 bars/day), mostly OK for IWM (~95% coverage), and **completely empty** for SPX. Track D and Track E can use SPY/QQQ/IWM intraday with confidence; SPX is unusable.
3. **Signal-alert exits are only ~23% populated** historically. Track D's hit-rate analysis must recompute exits from intraday bars; Track E's per-ticker win-rate stats will need the same.
4. **The watchlist itself is fine** (SPY/IWM/QQQ correctly flagged for all surfaces).
5. **Brief and insight-pipeline pipelines ran every day** (8:30 AM and 8:45 AM) — but they ran on stale inputs.

---

## Prioritized backlog (Track A)

| Priority | Item | Effort |
|---|---|---|
| **P0-1** | Remove `--date=2026-04-27` arg from `fetch-market-data` Cloud Run Job spec | 5 min (gcloud command) |
| **P0-2** | Backfill SPY/IWM/QQQ daily for 2026-04-28 → 2026-05-07 (and the 4-14 → 4-23 prior gap) | 30 min |
| **P0-3** | Add freshness-guard to `premarket_brief.py`: refuse to run / banner-warn when daily inputs >1 day stale | 1 hr |
| **P0-4** | Build/deploy `signal-monitor-eod-resolver` Cloud Run Job to backfill missing exits | 2 hr |
| **P0-5** | One-time backfill of the 1,209 historical alerts lacking exits | 1 hr |
| **P1-1** | Re-enable `Freshness Watchdog` (or migrate to Cloud Run) | 30 min |
| **P1-2** | Investigate `av-intraday-nightly` scheduler — why only 2 runs in last 7 days | 30 min |
| **P1-3** | Fill or formally retire SPX intraday partition | 1 hr |
| **P2-1** | Investigate IWM 2026-05-04 missing 77 intraday minutes | 30 min |
| **P2-2** | Hard-delete 2 soft-deleted watchlist rows (MSFT, ZS) | 5 min |
| **P2-3** | Review 13 dormant peer rows in watchlists (flip flag or delete) | 15 min |
| **P2-4** | Drop NULL-payload placeholder rows from `market_data_daily` once real data lands | 15 min |

**Track A complete.** Track E (next) will treat intraday SPY/QQQ/IWM as the source of truth for per-ticker calibration and will recompute its own exits rather than trust the broken `signal_alerts.exit_*` columns.
