---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-DATA-003]
issues: [1190]
canvases: []
done_when:
  - "tests/audits/test_audit_intraday_session_gaps.py passes: for SPY, QQQ and IWM a session in the scan window with zero regular-hours 1-min bars is reported MISSING, one under 90% of that session's expected minutes is reported THIN, a half day is judged against its own length, either makes --strict exit 1, five thin sessions in a row are all reported, the same sessions stored as true UTC, as legacy Eastern-labelled rows and as both at once give the same counts, and the scan issues one bounded query per ticker"
  - "tests/gcp/test_intraday_verify_basis.py passes: --verify-basis exits 1 and prints one BASIS-FAIL line per ticker-month in which two or more consecutive sessions have a 1-min regular-hours high and low off the daily table's by more than 3 bp, exits 0 when none is, reports a session with no daily row as UNMEASURED rather than passing it, exits 3 when nothing fails but a session is UNMEASURED, and gives the same result for a month stored as true UTC, as legacy Eastern-labelled rows and as both at once"
  - "tests/gcp/test_export_intraday_bars.py passes: after a nightly fetch the current and the previous Eastern month of SPY, QQQ and IWM are written to intraday-bars/v1/1min/<TICKER>/<YYYY-MM>.parquet (zstd; columns ts, open, high, low, close, volume, data_source; ts UTC ascending) with one query per ticker-month, an existing file is overwritten, manifest.json records each month's rows, first and last ts, sha256, exported_at, basis state and factor range, a month with no daily row is written with basis unmeasured and null factors (never 1.0), a failed upload raises, --export-bars-from writes every month from the one given, read_bars returns exactly the rows exported, and read_bars raises when a requested month's file is absent and when a month's file has been replaced by a different valid Parquet file"
  - "tests/meta/test_workflows_no_continue_on_error.py passes: no step or job in .github/workflows sets continue-on-error to true"
  - "make test passes on the PR head with tests/gcp/test_evaluate_ew_strikes.py, tests/gcp/test_intraday_replace_months.py, tests/gcp/test_intraday_writers_utc.py and tests/audits/test_audit_data_freshness.py unchanged"
  - "The PR body gives EXPLAIN (ANALYZE, BUFFERS) from production for the gap-scan query and the basis query (rows read, execution time), and the table of rows per ticker and month, for SPY, QQQ and IWM, that the refill, the thin-month refetch and the as-traded rewrite would write"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, and 12-PR-ISSUE-TRACEABILITY lists it"
status: draft
supersedes: null
---

# market_data_intraday: no silent gaps, a basis check, and a durable copy

## Scope

- The request change (every AlphaVantage 1-min request on `adjusted=false`) is its own spec, `docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md`, split out so it can ship first. This spec is everything else: the gap alarm, the basis check, the workflow test, the bucket copy, and the close-out that refills and rewrites stored bars. Its close-out starts only once that change is deployed.
- The refill, the thin-month refetch, the as-traded rewrite, the gap alarm and the bucket copy cover SPY, QQQ and IWM only. Other tickers are out of scope; the owner is removing them from the watchlist.
- No trading cost is applied or stored anywhere in this change. Bars, the bucket copy and both checks carry prices as traded and nothing else.

## Problem

Two defects in the 1-min bars, found on 2026-11-13. Both were silent.

### 1. Sessions are missing and nothing said so

- SPY and QQQ have no 1-min bars for 31 sessions, 2025-11-17 to 2025-12-31. IWM has none for 9, 2025-11-17 to 2025-11-28.
- Thin sessions (under 90% of the session's regular-hours minutes), over the stored history as exported on 2026-11-13 (SPY from 2022-02-24, QQQ and IWM from 2015-01-02):

| Ticker | Month | Thin sessions | Fewest and most bars |
|---|---|---|---|
| SPY | 2024-03 | 12 | 25 to 336 |
| SPY | 2024-04 | 12 | 34 to 312 |
| SPY | 2024-05 | 1 | 341 |
| SPY | 2025-04 | 6 | 49 to 240 |
| SPY | 2025-05 | 12 | 31 to 338 |
| SPY | 2025-06 | 6 | 42 to 283 |
| QQQ | 2021-04 | 1 | 338 |
| QQQ | 2024-11 | 9 | 18 to 340 |
| QQQ | 2024-12 | 9 | 13 to 233 |
| QQQ | 2025-01 | 4 | 86 to 317 |
| IWM | 2021-04 | 1 | 338 |

  SPY 49, QQQ 23, IWM 1. SPY bars before 2022-02-24 were not in that export, so they were not checked.
- Cause of the missing sessions: every SPY, QQQ and IWM bar from 2024-12 to 2026-01 was written in one manual load on 2026-02-23 (`inserted_at` 02:40 to 03:05 UTC, no Cloud Run execution or workflow run). What it loaded had been fetched in mid-November 2025: November ends at 11-14 for all three, and SPY and QQQ December was never fetched. The cause of the thin sessions was not traced.
- Nothing revisits old months. `av-intraday-nightly` refetches the previous month to today. The monthly GitHub workflow ran once (2025-12-01) and reported success with `continue-on-error` on every fetch step; its output was never stored.
- The freshness watchdog has a gap scan for this table over the last 5 days (`scripts/audit_data_freshness.py`, `gap_scan_days: 5`). It asks only whether a day has any row; the 350-row floor is applied to the latest day alone and counts extended-hours bars. So a thin session in the window passes, and a gap already older than 5 days when the watchdog started is never seen.
- AlphaVantage serves the missing SPY, QQQ and IWM sessions today (fetched read-only with the job's key on 2026-11-13).

### 2. Stored prices are on many bases

- AlphaVantage's TIME_SERIES_INTRADAY returns split- and dividend-adjusted prices unless the request says `adjusted=false`, adjusted as of the call.
- Eight requests in the repo name that endpoint. Seven ask for adjusted prices, and three of the seven write `market_data_intraday` (the sibling spec lists each by file and line).
- So every stored bar sits at the basis of its last fetch. Measured against AlphaVantage's `adjusted=false` series, bar by bar with identical volumes: SPY 2025-04 and 2025-05 are stored at 0.99430 of the traded price, SPY 2025-06 steps to 0.99725 at the June ex-dividend date, QQQ 2025-01 is at 0.99629, and SPY, QQQ and IWM 2025-11 are at exactly 1.00000.
- The nightly makes new stretches. It refetches the previous month with `--force`, so a month is rewritten at a new basis when an ex-dividend date falls in that window. SPY is stored about 0.25% low for 2026-02-02 to 03-19 (0.99724), 2026-05-01 to 06-17 (0.99746) and 2026-08-03 to 09-17 (0.99753). SPY 2026-08-31 15:59 ET is 765.053 in the table and traded at 766.95.
- Each session's 1-min regular-hours high and low were compared with the daily table's, which is as traded (SPY 2025-05-15 open 585.56 and close 590.46 equal the as-traded 1-min bars). Months that hold sessions on an adjusted basis:

| Ticker | From 2025-01: months | Rows in them | Lowest factor | Whole exported history: months | Rows in them |
|---|---|---|---|---|---|
| SPY | 15 | 304,302 | 0.99132 | 50 | 923,571 |
| QQQ | 15 | 314,655 | 0.99629 | 119 | 1,983,926 |
| IWM | 16 | 317,038 | 0.99221 | 120 | 1,737,874 |
| Total | 46 | 935,995 | | 289 | 4,645,371 |

- IWM and QQQ 2015-01 to 2016-04 (334 sessions each) have no daily row, so their basis could not be measured.
- The 13 other tickers that carry stored signals hold 132 more such ticker-months (2,173,262 rows) from 2025-01. They are out of scope and stay as they are.
- Readers compare these bars with as-traded numbers: the brief's levels come from the daily table, and live quotes and strikes are as traded (`platform/api/routers/live.py:403` and `evaluate_ew_strikes.py` already ask for `adjusted=false`, #1151).
- A refill of the missing sessions on today's code would write November and December 2025 about 1.07% low for SPY and overwrite the as-traded rows of 2025-11-03 to 11-14.

### 3. An analysis has to re-export the bars every time

- A session that cannot reach Cloud SQL (Claude Code on the web: port 443 only) reads bars through the `db-query` job, 50,000 rows a statement. On 2026-11-13 the export of the signal tickers' bars took about 55 minutes of job runs, and the copy lives only in that session's container.
- The bucket's old `raw/<ticker>/intraday/` parquets stop at 2026-05 and are deleted after 730 days by a lifecycle rule.

## Non-goals

- No production write in this change. The refill, the thin-month refetch, the as-traded rewrite and the recomputes are separate runs that wait for the owner's yes on their exact scope (Close-out below).
- No ticker other than SPY, QQQ and IWM is refilled, refetched, rewritten, scanned for gaps or copied to the bucket. Their stored months keep their mixed bases.
- No change to the watchlist, and no change to which tickers or months the nightly fetches. What it fetches is recorded under "The watchlist" below.
- No change to the daily table, to `adjusted_close`, or to how any reader uses intraday prices.
- The bucket copy is for analysis sessions. No job and no API path reads it, and it is never a fallback for Cloud SQL (CLAUDE.md 3.7.1).

## Approaches considered

1. As-traded everywhere, with an alarm and a check (chosen). It matches the daily table, live quotes and strikes; a refetch can never move a stored bar again; and each of the two silent failures gets a check that fails loudly.
2. Adjusted everywhere: every bar would have to be rewritten after every ex-dividend date, forever, and stored bars would stop matching live and daily prices.
3. Store both: a second set of price columns doubles the table for no reader that exists.
4. Fix the writers only: the missing sessions were found by accident a year later. Without the alarm the next gap is found the same way.

## Design

### A. Requests

In the sibling spec named under Scope. Nothing here changes a request.

### B. Gap alarm

Extend the gap scan the freshness watchdog already runs (`scripts/audit_data_freshness.py`, Cloud Run job `freshness-watchdog`, `--strict`, hourly on weekdays and nightly).

- **Tickers**: SPY, QQQ and IWM, the list the scan already uses.
- **Sessions**: NYSE sessions from `lib.eastern_time.session_schedule`, never a weekend or holiday.
- **MISSING**: a session with zero regular-hours 1-min bars.
- **THIN**: a session whose regular-hours bar count is under 90% of that session's expected minutes from the calendar (390, or a half day's own length). SPY, QQQ and IWM have a bar in nearly every regular-hours minute (outside the months listed in the Problem, one session in each of QQQ's and IWM's twelve stored years falls under 90%), so the calendar is the baseline and no earlier session is read. A threshold relative to the ticker's own trailing 20-session median was measured on the stored bars and rejected: a run of thin sessions drags the median down, and it passed 6 of SPY's 49 thin sessions (2025-05-13, 05-21, 05-30 and 06-04 among them) and 2 of QQQ's 23.
- **Timestamps**: the table still holds two conventions, true UTC and legacy Eastern clock labelled UTC (CLAUDE.md 3.9). The scan reads `ts` and `volume` and resolves them with `lib.eastern_time.stored_intraday_to_eastern`, the rule the Charts API and `_held_session_dates` use: each row is read in its own convention, and a minute stored under both is counted once. Regular hours are selected only after that. No date is taken from `ts` in SQL.
- **Windows**: the hourly and nightly runs scan the last 5 sessions, as now. A new `--intraday-gap-since YYYY-MM-DD` scans from that date; it is for the close-out and for any bulk operation, and is not scheduled.
- **Failure**: a MISSING or THIN session is a failed row, so `--strict` exits 1 and the failure notifier files the job failure. The report names each ticker and session.
- **Cost**: one query per ticker, `ts >= :since` on the primary key `(ticker, interval, ts)`, returning `ts` and `volume`. Measured on production (db-query-q6wbd): SPY since 2026-11-05, an index scan, 5,827 rows in 5.7 ms; SPY since 2025-01-01, a bitmap heap scan, 436,190 rows in 4,444 ms with a cold cache. The PR records the same for the final query.

### C. Basis check

`fetch_alphavantage_intraday --verify-basis PATH`, beside the existing `--verify-months`: read-only, no vendor call.

- Input: a file of `TICKER,YYYY-MM` lines, as `gcp/queries/list_intraday_ticker_months.sql` produces from the table. For the close-out it is that list's SPY, QQQ and IWM lines.
- Per ticker-month: rows are resolved with `stored_intraday_to_eastern` as in B, then for each session the 1-min regular-hours high and low are set over `market_data_daily`'s high and low. A month fails when two or more consecutive sessions are off by more than 3 bp. One odd session is not a basis (a single bad print); it is listed as a note.
- Output: `BASIS-FAIL TICKER YYYY-MM first..last factor` lines and exit 1. A session with no daily row is printed as `UNMEASURED TICKER YYYY-MM first..last`, never a pass: with no failure and at least one such line the exit is 3. Exit 0 means every session was measured and none failed.
- The method reproduces every factor measured against AlphaVantage above.

### D. Monthly workflow

- `.github/workflows/fetch-alphavantage-intraday-monthly.yml` no longer exists on `main`, and no workflow on `main` sets `continue-on-error: true`. `.github/workflows/README.md` states the rule.
- Nothing enforces it. `tests/meta/test_workflows_no_continue_on_error.py` reads every file under `.github/workflows` and fails on a step or job that sets it to true. It changes no workflow.

### E. Durable copy of the bars in the bucket

A nightly write of the SPY, QQQ and IWM 1-min bars from Cloud SQL to GCS, so an analysis session downloads files instead of re-exporting.

- **Where**: `gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/<TICKER>/<YYYY-MM>.parquet`, one file per ticker per Eastern month, plus `intraday-bars/v1/1min/<TICKER>/manifest.json`. The `intraday-bars/` prefix has no lifecycle rule (the bucket's two rules delete `sql-dumps/` after 30 days and `raw/` after 730).
- **Format**: Parquet, zstd. Columns `ts` (timestamp, UTC, the bar's true instant as `gcp.historical_signals.load_intraday_bars` returns it, so the two stored timestamp conventions are already resolved), `open`, `high`, `low`, `close` (float64), `volume` (int64), `data_source` (string). One row per bar, ascending `ts`.
- **Manifest**: per month `rows`, `first_ts`, `last_ts`, `sha256`, `exported_at`, and the basis from the basis check: `basis` is `measured` with `factor_min` and `factor_max` over the sessions that have a daily row (1.0 means as traded), or `unmeasured` with both factors null when no session of the month has one. IWM and QQQ 2015-01 to 2016-04 are unmeasured today and stay so, because the daily table is not changed here. A month that is still on an adjusted basis says so, an unmeasured month says so, and a reader never has to assume.
- **Nightly**: at the end of `av-intraday-nightly` (`fetch_alphavantage_intraday --symbol=ALL`), after its writes. It rewrites the current month and the previous month, because those are the two months that run refetches. A file is replaced whole. A failed query or upload raises, so the job fails and the notifier files it; the bars are already in Cloud SQL by then.
- **One-time history**: `--export-bars-from YYYY-MM` writes every month from the one given and fetches nothing (`gcloud run jobs execute fetch-alphavantage-intraday --args="--export-bars-from=2015-01"`). It is run once after the refill, and the rewritten months are exported again after the as-traded rewrite.
- **Module**: `gcp/fetchers/export_intraday_bars.py`: `export_month`, `export_window`, `read_bars`. No change to `gcp/deploy.sh`: the scheduler's arguments stay `--symbol=ALL --force`, and the export is on for that run unless `INTRADAY_BARS_EXPORT=off`.
- **How a session reads it**:
  ```bash
  env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage cp -r \
    gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/SPY ./bars/
  ```
  ```python
  from gcp.fetchers.export_intraday_bars import read_bars
  bars = read_bars("./bars", "SPY", "2025-01", "2026-11")   # checks each file against the manifest's sha256
  ```
  `read_bars` raises if a requested month has no file or its hash differs from the manifest's, and returns each month's basis state and factor range beside the frame. It does not refuse an unmeasured month and never reports one as 1.0. It needs `pandas` and `pyarrow` only. Both refusals are tested: a month's file removed, and a month's file swapped for another valid Parquet file.

### The watchlist (read from production on 2026-11-13; nothing here changes it)

- `av-intraday-nightly --symbol=ALL` fetches `MarketConfig.tickers` (IWM, SPY, QQQ), the insight `DEFAULT_TICKERS` (SPY, IWM, QQQ) and the active rows of `watchlists` where `user_id = 'default'` (`gcp/calibrate_level_params.py:96-100`, `brief_insight_watchlist_tickers`).
- `watchlists` holds only `user_id = 'default'` rows. 16 are active: SPY, QQQ, IWM, AVGO, NVDA, ASTX, MU, ANET, CSCO, TXN, MRVL, AMD, ARM, TSM, QCOM and MCK.
- The web app does not edit those rows. Its watchlist endpoints key on the signed-in user (`platform/api/routers/insights.py:57`, `_watchlist_owner`), and no row with such a key exists. The Discord `/watchlist` command and the CLI edit `default`.
- So removing a ticker in the web app does not change what the nightly fetches. The nightly fetches only SPY, QQQ and IWM once the 13 other rows of `default` are removed or marked removed. Until then it fetches all 16, as traded once this change is deployed.

### Capacity

- Requests: no change in number. The same AlphaVantage calls, rows and writes per run.
- Gap alarm, scheduled: 3 queries, about 5 sessions of bars each (5,827 rows in 5.7 ms measured for SPY).
- Gap alarm on demand, and the basis check: bounded by the date or the list the caller gives; 4.4 s for SPY's 436,190 rows since 2025-01-01, measured cold.
- Durable copy, nightly: 3 tickers x 2 months = 6 queries of about 20,000 rows on the primary key, 6 uploads of about 0.6 MB (the size of the old monthly parquets) and 3 manifests; under 30 seconds added to a job with a 3,600-second task timeout.
- Durable copy, one time: IWM and QQQ from 2015-01 and SPY from its first stored month, about 340 ticker-months, 340 queries and uploads, about 200 MB; a single execution inside the same timeout. One query and one upload per month, so a crash leaves the months already written.
- Storage: about 0.2 GB at standard rates, under one cent a month.
- No new job and no new schedule.

## Close-out (after the merge, each step on the owner's yes)

These need the deployed fix and production writes, so they are not pre-merge boxes. Each has the check that proves it. Every step is for SPY, QQQ and IWM only.

1. **Deploy** this spec's code: the fetchers image and the freshness watchdog. The request change of the sibling spec must already be deployed. The nightly bucket write starts with this deploy, so the owner's yes to the deploy is the yes to those writes.
2. **Refill the missing sessions and refetch the thin months of 2025**, with the plain fetch (`--start-date`, `--end-date`, `--force`), which upserts.
   - Refill: SPY and QQQ 2025-11 and 2025-12, IWM 2025-11. 66,923 new rows; the 28,501 rows already stored for 2025-11-03 to 11-14 are rewritten with identical values.
   - Thin months, a separate yes: SPY 2025-04, 2025-05 and 2025-06, QQQ 2025-01. AlphaVantage returns 20,172, 20,160, 19,195 and 19,188 rows for them; 16,917, 14,133, 16,222 and 17,320 are stored. The refetch also puts these four months on the as-traded basis.
   - Why an upsert is enough here: these months hold no legacy Eastern-labelled row (checked on production on 2026-11-13), so every stored row is rewritten by the row AlphaVantage returns for the same minute.
   - Why this does not wait for #1190: nothing that has no recompute path exists in these windows. Read from production on 2026-11-13 (db-query-q9m9t): `signal_alerts`, `premarket_analysis` and `historical_signals` hold no row for these tickers in either window, and no `market_data_daily` row there has a premarket field. `intraday_flow_15m` and `intraday_gex_15m` hold nothing in the refill window, and 3,233 rows each for SPY 2025-04 to 06 and 1,160 each for QQQ 2025-01.
   - The thin months of 2024 (SPY 2024-03 to 05, QQQ 2024-11 and 12) and the single thin session of 2021-04 were not checked for legacy rows and their AlphaVantage counts were not fetched. They are on an adjusted basis, so they are in step 3's list.
   - Check: `audit_data_freshness.py --intraday-gap-since 2025-01-01` reports no MISSING session for SPY, QQQ and IWM and no THIN session in a month that was refetched; `--verify-basis` passes the months written; and each month's stored row count equals the count AlphaVantage returned.
3. **Rewrite the adjusted months as traded**, not only the missing days.
   - List: every SPY, QQQ and IWM ticker-month that `--verify-basis` fails or cannot measure. Today that is 289 failing ticker-months (4,645,371 rows), 46 of them from 2025-01 (935,995 rows), less the four months step 2 rewrites, plus IWM and QQQ 2015-01 to 2016-04, which have no daily row to measure against. The PR body lists them by ticker and month, and the owner's yes names the range.
   - Mechanism: `--replace-months --commit`, one transaction per ticker-month, which deletes the month and inserts the as-traded refetch. A plain upsert is not enough in general: it rewrites the rows it fetches and leaves any legacy Eastern-labelled row in place, still adjusted.
   - Gate: CLAUDE.md 3.9 holds `--replace-months --commit` until #1190 lands, because two result tables have no recompute path. This rewrite is the same run as that migration: one refetch per ticker-month fixes its timestamps and its basis. It does not start before #1190 allows it.
   - Check: `--verify-basis` over the three tickers' list regenerated from the table prints no BASIS-FAIL line, its UNMEASURED lines are exactly the months that have no daily row (IWM and QQQ 2015-01 to 2016-04 today, so it exits 3, not 1), and `--verify-months` exits 0.
4. **Recompute what reads these bars**, over every session written in steps 2 and 3: the refilled sessions, the refetched thin months and the replaced months. The plain fetch of step 2 prints no REBUILD or REPLACED line, so its windows are named here and are part of the scope, not left to the replace's output.
   - `strat_features_*`: a full-history rebuild, `strat_data_builder --rebuild --start-date=2016-01-01` on the `strat-engine` job, never a rebuild from a window's start. A rebuild loads no bar before its start date (`_process_ticker`: `bar_load_start = start_date`), so RSI, MACD and EMA-200 would be recomputed without warmup and stored values overwritten with NULL and then differently seeded ones. `gcp/deploy.sh` documents that this run needs the job's memory raised to 32Gi and set back afterwards; that job change is part of the owner's yes. The job's task timeout is 5,400 s and the duration of a full rebuild was not measured for this spec: the run plan takes it from the job's last full rebuild before starting, and splits the run with `--tickers` and `--tf-only` if it does not fit.
   - `realtime_gex_15m`: `build-realtime-gex --backfill --restart`, which recomputes from 2026-05-23, the table's first day. Step 2's windows are all before it.
   - `intraday_flow_15m` and `intraday_gex_15m`: no deployed job writes them (the job list of 2026-11-13 has none; `docs/audits/2026-08-27-claude-codebase-review/09-dormant-surfaces.md` records them as last written on 2026-06-05). Their modules take no date window: `--backfill` resumes after the last bucket and skips an old hole (`build_intraday_flow._resume_since`), and `--backfill --restart` recomputes the whole history. So there is no path to run here. The replace of step 3 deletes their rows for a replaced month; the plain refetch of step 2 leaves the 3,233 and 1,160 rows of the thin months computed from the old bars. The close-out records them as stale, or the owner asks for a manual `--backfill --restart`.
   - `premarket_analysis` outcomes: the playbook resolver, per session and ticker (`PLAYBOOK_RESOLVE_DATE`, `PLAYBOOK_RESOLVE_FORCE`). Its own sweep looks back 14 days only.
   - `historical_signals`: full regeneration per ticker.
   - Premarket fields of `market_data_daily` (`pre_high`, `pre_low`, `pre_vwap`, `gap_pct`) and `signal_alerts` exits: no path today (#1190). Step 2's windows hold neither.
   - Levels and ATR: prior-day, week, month, quarter and year levels and ATR(14) and ATR(5) are computed from the daily table, which is already as traded, so they do not change. Premarket high and low (PMK_H, PMK_L) come from the premarket fields above. `ticker_level_params` premarket-filter thresholds are calibrated from 1-min premarket bars (`gcp/calibrate_level_params.py`) and are recalibrated after the rewrite.
   - Check: the `strat-engine` rebuild's log shows it loaded bars from 2016-01-01 and finished, and in every window of the union no `strat_features_*` row past its timeframe's first 200 bars of history has a NULL `ema_200`; the `build-realtime-gex` run is recorded where a window reaches 2026-05-23; `intraday_flow_15m` and `intraday_gex_15m` are recorded as rebuilt by hand or as stale, per window; and each of the replace's RECOMPUTE lines is answered with the command run or the issue that tracks the missing path.
5. **Write the history to the bucket** once, after step 2: `--export-bars-from=2015-01`.
   - Until step 3 runs, the adjusted months are exported as they are, and each manifest entry carries its factor. After step 3 the rewritten months are exported again.
   - Check: every ticker-month the table holds for SPY, QQQ and IWM has a file whose row count and `sha256` match its manifest entry, and after step 3 every month is either `measured` with `factor_min` and `factor_max` of 1.0 or `unmeasured`, with the unmeasured months listed and equal to the basis check's.

## Open before this spec is marked ready

Found by an independent read of the draft on 2026-11-13. Each is verified against the code and none is resolved in this text yet.

1. **Thin sessions across the two timestamp conventions.** `stored_intraday_to_eastern` decides a date's convention from its rows, and a thin legacy session can read as true UTC, or a thin session stored both ways can count as complete (240 real bars read as 390 in a local run of the function). The "same counts for all three fixtures" items for the gap scan and the basis check cannot hold for thin sessions as written. Dates from 2026-09-28 are true UTC by construction, so the scheduled 5-session scan is safe; `--intraday-gap-since`, `--verify-basis` and the export of older months are exposed.
2. **Step 3's list and its check disagree.** The list is every month the basis check fails; the check also requires `--verify-months` to pass, which fails any month holding a legacy row whatever its basis. And `--replace-months` re-inserts only the sessions a month already holds, so it repairs a thin session and never a missing one.
3. **Thin sessions and the basis check.** A thin session's 1-min high and low differ from the daily table's whatever the basis, so thinness and basis are mixed in BASIS-FAIL and in the manifest factor. The manifest's 1.0 has no stated tolerance.
4. **Export contract.** One query per ticker-month cannot also read the daily table for the factor; the nightly export runs at 21:00 ET, before the daily row of that session exists at 23:00 ET, so the newest session is unmeasured every night; no item ties a file's content to the table (the two-convention case, the Eastern month boundary, a failed query, `INTRADAY_BARS_EXPORT=off`).
5. **The gap scan also feeds the API.** `audit_all()` backs `GET /api/health/freshness` and the admin data-sources view, so new MISSING and THIN rows change responses the site shows and add queries to the API service. That needs an API test and a capacity line.
6. **A second scheduler runs the same job.** `av-intraday-monthly` (`0 21 1 * *`) runs `fetch-alphavantage-intraday` with the same default symbol, so two exports can write the same files on a 1st. `tests/gcp/test_av_intraday_universe.py` runs `main()` with `--symbol=ALL --force` and no database, so the export's wiring has to say what it does there.
7. **`--intraday-gap-since`** has no `done_when` item, no memory number against the watchdog's 512Mi, and must use a strict query: the existing scan's reader returns an empty frame on a database error, which would read as every session MISSING.
8. **Smaller:** `ticker_level_params` recalibration has no check; the workflow test is stricter than the two documents that describe the rule; SPY's stored history before 2022-02-24 was not exported, so SPY's month and row totals may be undercounts.

## Risks

- A reader that relied on adjusted intraday prices. None found: readers compare intraday bars with live, daily and strike prices. Covered by the unchanged suites.
- Until step 3 runs, the table keeps its mixed months. The nightly re-bases the previous month as it refetches it, so new mixing stops on the first night after the deploy.
- The alarm fires on real one-off outages. That is its job; the report names the session so it can be refetched or acknowledged.
- A session reads a stale bucket copy. The manifest's `last_ts` and `exported_at` say how fresh each month is, and a failed nightly write fails the job.
- A ticker added to the scan later that does not trade every minute would be reported THIN every day. The scan's list is three tickers by design; widening it means changing the THIN rule first.
