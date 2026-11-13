---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-001, REQ-DATA-003]
issues: [1190]
canvases: []
done_when:
  - "tests/gcp/test_intraday_as_traded.py passes: the AlphaVantage TIME_SERIES_INTRADAY request built by fetch_alphavantage_intraday.fetch_month, by fetch_market_data.fetch_minute_bars called without an adjusted argument, and by backfill_ticker.av_intraday_month each carries adjusted=false"
  - "tests/gcp/test_intraday_as_traded.py::test_every_intraday_writer_requests_as_traded passes: every TIME_SERIES_INTRADAY request under gcp/ that feeds market_data_intraday sets adjusted to false, found by AST, so a new writer without it fails"
  - "tests/audits/test_audit_intraday_session_gaps.py passes: for every tracked ticker a session in the scan window with zero regular-hours 1-min bars is reported MISSING, one under 90% of that ticker's own trailing 20-session median is reported THIN, either makes --strict exit 1, a ticker whose normal session is sparse is not flagged, a half day is judged against its own length, and the scan issues one bounded query per ticker"
  - "tests/gcp/test_intraday_verify_basis.py passes: --verify-basis exits 1 and prints one BASIS-FAIL line per ticker-month in which two or more consecutive sessions have a 1-min regular-hours high and low off the daily table's by more than 3 bp, exits 0 when none is, and reports a session with no daily row as UNMEASURED rather than passing it"
  - "tests/gcp/test_export_intraday_bars.py passes: after a nightly fetch the current and the previous Eastern month of SPY, QQQ and IWM are written to intraday-bars/v1/1min/<TICKER>/<YYYY-MM>.parquet (zstd; columns ts, open, high, low, close, volume, data_source; ts UTC ascending) with one query per ticker-month, an existing file is overwritten, manifest.json records each month's rows, first and last ts, sha256, exported_at and basis factor range, a failed upload raises, --export-bars-from writes every month from the one given, and read_bars returns exactly the rows exported"
  - "tests/meta/test_workflows_no_continue_on_error.py passes: no step or job in .github/workflows sets continue-on-error to true"
  - "make test passes on the PR head with tests/gcp/test_evaluate_ew_strikes.py, tests/gcp/test_intraday_replace_months.py, tests/gcp/test_intraday_writers_utc.py and tests/audits/test_audit_data_freshness.py unchanged"
  - "The PR body gives EXPLAIN (ANALYZE, BUFFERS) from production for the gap-scan query and the basis query (rows read, execution time), and the table of rows per ticker and month that the refill and the as-traded rewrite would write"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, and 12-PR-ISSUE-TRACEABILITY lists it"
status: draft
supersedes: null
---

# market_data_intraday: as-traded prices, no silent gaps, and a durable copy

## Problem

Two defects in the 1-min bars, found on 2026-11-13. Both were silent.

### 1. Sessions are missing and nothing said so

- SPY and QQQ have no 1-min bars for 31 sessions, 2025-11-17 to 2025-12-31. IWM has none for 9, 2025-11-17 to 2025-11-28. ASTX has none for 4 (one in 2026-04, three in 2026-05).
- SPY has 24 thin sessions between 2025-04-16 and 2025-06-13 (as few as 31 of 390 regular-hours bars) and QQQ has 4 in early January 2025.
- Cause: every SPY, QQQ and IWM bar from 2024-12 to 2026-01 was written in one manual load on 2026-02-23 (`inserted_at` 02:40 to 03:05 UTC, no Cloud Run execution or workflow run). What it loaded had been fetched in mid-November 2025: November ends at 11-14 for all three, and SPY and QQQ December was never fetched.
- Nothing revisits old months. `av-intraday-nightly` refetches the previous month to today. The monthly GitHub workflow ran once (2025-12-01) and reported success with `continue-on-error` on every fetch step; its output was never stored.
- The freshness watchdog has a gap scan for this table, but only for IWM, SPY and QQQ and only over the last 5 days (`scripts/audit_data_freshness.py`, `gap_scan_days: 5`). A gap already older than that when the watchdog started is never seen.
- AlphaVantage serves the SPY, QQQ and IWM sessions today (fetched read-only with the job's key on 2026-11-13). ASTX was not checked.

### 2. Stored prices are on many bases

- AlphaVantage's TIME_SERIES_INTRADAY returns split- and dividend-adjusted prices unless the request says `adjusted=false`, adjusted as of the call.
- `fetch_alphavantage_intraday.fetch_month` does not set the parameter, `fetch_market_data.fetch_minute_bars` defaults it to true, and `backfill_ticker.av_intraday_month` sets it to true. All three write `market_data_intraday`.
- So every bar sits at the basis of its last fetch. Measured against AlphaVantage's `adjusted=false` series, bar by bar with identical volumes: SPY 2025-04 and 2025-05 are stored at 0.99430 of the traded price, SPY 2025-06 steps to 0.99725 at the June ex-dividend date, QQQ 2025-01 is at 0.99629, and SPY, QQQ and IWM 2025-11 are at exactly 1.00000.
- The nightly makes new stretches. It refetches the previous month with `--force`, so a month is rewritten at a new basis when an ex-dividend date falls in that window. SPY is stored about 0.25% low for 2026-02-02 to 03-19 (0.99724), 2026-05-01 to 06-17 (0.99746) and 2026-08-03 to 09-17 (0.99753). SPY 2026-08-31 15:59 ET is 765.053 in the table and traded at 766.95.
- The same holds across the table. Each session's 1-min regular-hours high and low were compared with the daily table's, which is as traded (SPY 2025-05-15 open 585.56 and close 590.46 equal the as-traded 1-min bars). On the 16 tickers that carry stored signals, from 2025-01:

| Ticker | Months with adjusted sessions | Sessions | Rows in those months | Lowest factor |
|---|---|---|---|---|
| SPY | 15 | 253 | 304,302 | 0.99132 |
| QQQ | 15 | 277 | 314,655 | 0.99629 |
| IWM | 16 | 276 | 317,038 | 0.99221 |
| MU | 18 | 349 | 349,139 | 0.98424 |
| TXN | 17 | 334 | 219,735 | 0.95729 |
| MRVL | 16 | 317 | 290,037 | 0.99565 |
| CSCO | 16 | 312 | 216,318 | 0.96417 |
| QCOM | 16 | 295 | 259,694 | 0.97183 |
| AVGO | 15 | 304 | 294,544 | 0.98896 |
| TSM | 15 | 300 | 291,238 | 0.98422 |
| MCK | 10 | 63 | 78,307 | 0.99496 |
| NVDA | 4 | 76 | 81,600 | 0.99989 |
| ASTX | 3 | 22 | 52,359 | 0.86449 |
| AMD | 2 | 37 | 40,291 | 0.96952 |

  That is 178 ticker-months and 3,109,257 rows. ANET and ARM have none.
- Not every mismatch is a dividend. NVDA 2026-06-09 to 09-25 sits at 1.035 to 1.048, MU 2026-06-08 to 06-25 at 1.015, and ASTX and AMD have factors far from 1. Those were measured, not explained: the cause was not checked.
- Readers compare these bars with as-traded numbers: the brief's levels come from the daily table, and live quotes and strikes are as traded (`platform/api/routers/live.py` and `evaluate_ew_strikes.py` already ask for `adjusted=false`, #1151).
- A refill of the missing sessions on today's code would write November and December 2025 about 1.07% low for SPY and overwrite the as-traded rows of 2025-11-03 to 11-14.

### 3. An analysis has to re-export the bars every time

- A session that cannot reach Cloud SQL (Claude Code on the web: port 443 only) reads bars through the `db-query` job, 50,000 rows a statement. On 2026-11-13 the export of the signal tickers' bars took about 55 minutes of job runs, and the copy lives only in that session's container.
- The bucket's old `raw/<ticker>/intraday/` parquets stop at 2026-05 and are deleted after 730 days by a lifecycle rule.

## Non-goals

- No production write in this change. The refill, the as-traded rewrite and the recomputes are separate runs that wait for the owner's yes on their exact scope (Close-out below).
- No change to the daily table, to `adjusted_close`, or to how any reader uses intraday prices.
- No change to which months the nightly fetches.
- The live trigger check in `signal_monitor.fetch_latest_bar` keeps its request: it reads today's last 100 bars, which no dividend has adjusted yet, and stores none.
- The unexplained factors (NVDA, MU, ASTX, AMD) are listed by the new check, not diagnosed here.
- The bucket copy is for analysis sessions. No job and no API path reads it, and it is never a fallback for Cloud SQL (CLAUDE.md 3.7.1). It holds SPY, QQQ and IWM only.

## Approaches considered

1. As-traded everywhere, with an alarm and a check (chosen). It matches the daily table, live quotes and strikes; a refetch can never move a stored bar again; and each of the two silent failures gets a check that fails loudly.
2. Adjusted everywhere: every bar would have to be rewritten after every ex-dividend date, for every ticker, forever, and stored bars would stop matching live and daily prices.
3. Store both: a second set of price columns doubles the table for no reader that exists.
4. Fix the writers only: the missing sessions were found by accident a year later. Without the alarm the next gap is found the same way.

## Design

### A. Writers request as-traded prices

- `fetch_alphavantage_intraday.fetch_month` adds `'adjusted': 'false'`. That one function serves the nightly, the bulk backfill and `replace_month`.
- `fetch_market_data.fetch_minute_bars` and `fetch_minute_data` change the default of `adjusted` to False. `write_intraday_to_sql` and `fetch_premarket_refresh` then get as-traded bars; the EW strikes caller already passes False.
- `backfill_ticker.av_intraday_month` sends `"adjusted": "false"`.
- `tests/gcp/test_intraday_as_traded.py` captures each function's request with a stubbed `requests.get`, and walks every `gcp/**/*.py` with `ast` for a dict holding `'function': 'TIME_SERIES_INTRADAY'`. Each must carry `adjusted` as the literal `'false'`, or an expression on a parameter whose default is False. Two requests that never feed the table are listed with their reason: `signal_monitor.fetch_latest_bar` and `fetch_cross_asset` (VIX, its own table).
- Scope: every ticker. The three functions are the only writers of the table for every symbol, so the fix is not specific to SPY, QQQ and IWM.

### B. Gap alarm

Extend the gap scan the freshness watchdog already runs (`scripts/audit_data_freshness.py`, Cloud Run job `freshness-watchdog`, `--strict`, hourly on weekdays and nightly).

- **Tickers**: every tracked ticker, read at run time from the function the nightly fetcher uses for `--symbol ALL` (`fetch_alphavantage_intraday.resolve_all_symbols`), instead of the fixed IWM, SPY, QQQ.
- **Sessions**: NYSE sessions from `lib.eastern_time.session_schedule`, from the ticker's first stored session, never a weekend or holiday.
- **MISSING**: a session with zero regular-hours 1-min bars.
- **THIN**: a session whose regular-hours bar count is under 90% of that ticker's own median over its previous 20 sessions, with a half day judged against its own length. A fixed 350-bar floor is wrong for sparse names: MCK is under 90% of the full minute count on 333 of 468 sessions without any gap. The ticker's own median flags SPY's 2025 thin sessions (31 to 338 bars against a median of 390) and does not flag MCK.
- **Windows**: the hourly and nightly runs scan the last 5 sessions, as now. A new `--intraday-gap-since YYYY-MM-DD` scans from that date; it is for the close-out and for any bulk operation, and is not scheduled.
- **Failure**: a MISSING or THIN session is a failed row, so `--strict` exits 1 and the failure notifier files the job failure. The report names each ticker and session.
- **Cost**: one query per ticker, grouped by Eastern date over `ts >= :since` on the primary key `(ticker, interval, ts)`. The scheduled scan reads about 5 sessions of bars per ticker. Measured on production for the on-demand scan, SPY since 2025-01-01: an index-only scan on the SPY partition's primary key read 436,191 rows and returned 438 dates in 1,150 ms (db-query-fvhrq). The PR records the same for the final query.

### C. Basis check

`fetch_alphavantage_intraday --verify-basis PATH`, beside the existing `--verify-months`: read-only, no vendor call.

- Input: the file of `TICKER,YYYY-MM` lines that `gcp/queries/list_intraday_ticker_months.sql` already produces from the table, so the list is every ticker-month stored, not a hand list.
- Per ticker-month: for each session, the 1-min regular-hours high and low over `market_data_daily`'s high and low. A month fails when two or more consecutive sessions are off by more than 3 bp. One odd session is not a basis (a single bad print); it is listed as a note.
- Output: `BASIS-FAIL TICKER YYYY-MM first..last factor` lines and exit 1, or exit 0. A session with no daily row is `UNMEASURED`, never a pass.
- The method reproduces every factor measured against AlphaVantage above.

### D. Monthly workflow

- `.github/workflows/fetch-alphavantage-intraday-monthly.yml` no longer exists on `main`, and no workflow on `main` sets `continue-on-error: true` (checked at 61bbd17e). `.github/workflows/README.md` states the rule.
- Nothing enforces it. `tests/meta/test_workflows_no_continue_on_error.py` reads every file under `.github/workflows` and fails on a step or job that sets it to true. It changes no workflow.

### E. Durable copy of the bars in the bucket

A nightly write of the SPY, QQQ and IWM 1-min bars from Cloud SQL to GCS, so an analysis session downloads files instead of re-exporting.

- **Where**: `gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/<TICKER>/<YYYY-MM>.parquet`, one file per ticker per Eastern month, plus `intraday-bars/v1/1min/<TICKER>/manifest.json`. The `intraday-bars/` prefix has no lifecycle rule (the bucket's two rules delete `sql-dumps/` after 30 days and `raw/` after 730).
- **Format**: Parquet, zstd. Columns `ts` (timestamp, UTC, the bar's true instant as `gcp.historical_signals.load_intraday_bars` returns it, so the two stored timestamp conventions are already resolved), `open`, `high`, `low`, `close` (float64), `volume` (int64), `data_source` (string). One row per bar, ascending `ts`.
- **Manifest**: per month `rows`, `first_ts`, `last_ts`, `sha256`, `exported_at`, and `factor_min` and `factor_max` from the basis check (1.0 means as traded). A month that is still on an adjusted basis says so; a reader never has to assume.
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
  `read_bars` raises if a requested month has no file or its hash differs, and returns the manifest's factor range beside the frame. It needs `pandas` and `pyarrow` only.

### Capacity

- Writers: no change. The same AlphaVantage calls, rows and writes per run.
- Gap alarm, scheduled: one query per tracked ticker, about 5 sessions of bars read each.
- Gap alarm on demand, and the basis check: bounded by the date or the list the caller gives; about 1.2 s per ticker for 23 months, measured above.
- Durable copy, nightly: 3 tickers x 2 months = 6 queries of about 20,000 rows on the primary key, 6 uploads of about 0.6 MB (the size of the old monthly parquets) and 3 manifests; under 30 seconds added to a job with a 3,600-second task timeout.
- Durable copy, one time: IWM and QQQ from 2015-01 and SPY from 2022-02, about 340 ticker-months, 340 queries and uploads, about 200 MB; a single execution inside the same timeout. One query and one upload per month, so a crash leaves the months already written.
- Storage: about 0.2 GB at standard rates, under one cent a month.
- No new job and no new schedule.

## Close-out (after the merge, each step on the owner's yes)

These need the deployed fix and production writes, so they are not pre-merge boxes. Each has the check that proves it.

1. **Deploy** the fetchers image and the freshness watchdog. The nightly bucket write starts with this deploy, so the owner's yes to the deploy is the yes to those writes.
2. **Refill the missing sessions** with the plain fetch (`--start-date`, `--end-date`, `--force`), which upserts.
   - SPY and QQQ 2025-11 and 2025-12, IWM 2025-11. Rows per ticker and month are in the PR body.
   - Check: `audit_data_freshness.py --intraday-gap-since 2025-01-01` reports zero MISSING sessions for SPY, QQQ and IWM.
3. **Rewrite the adjusted months as traded**, not only the missing days.
   - List: every ticker-month `--verify-basis` fails, for every ticker in the table (178 ticker-months and 3.1 million rows on the 16 measured tickers).
   - Mechanism: `--replace-months --commit`, one transaction per ticker-month, which deletes the month and inserts the as-traded refetch. A plain upsert is not enough: it rewrites the rows it fetches and leaves any legacy Eastern-labelled row in place, still adjusted.
   - Gate: CLAUDE.md 3.9 holds `--replace-months --commit` until #1190 lands, because two result tables have no recompute path. This rewrite is the same run as that migration: one refetch per ticker-month fixes its timestamps and its basis. It does not start before #1190 allows it.
   - Check: `--verify-basis` over a list regenerated from the table exits 0, and `--verify-months` exits 0.
4. **Recompute what reads these bars**, over the ranges the replace prints.
   - Derived timestamp tables (`intraday_flow_15m`, `intraday_gex_15m`, `realtime_gex_15m`, `strat_features_*`): their builders, per REBUILD line.
   - `premarket_analysis` outcomes: the playbook resolver, per replaced session.
   - `historical_signals`: full regeneration per ticker.
   - Premarket fields of `market_data_daily` (`pre_high`, `pre_low`, `pre_vwap`, `gap_pct`) and `signal_alerts` exits: no path today (#1190).
   - Levels and ATR: prior-day, week, month, quarter and year levels and ATR(14) and ATR(5) are computed from the daily table, which is already as traded, so they do not change. Premarket high and low (PMK_H, PMK_L) come from the premarket fields above. `ticker_level_params` premarket-filter thresholds are calibrated from 1-min premarket bars (`gcp/calibrate_level_params.py`) and are recalibrated after the rewrite.
   - Check: each of the replace's RECOMPUTE lines is answered with the command run or the issue that tracks the missing path.

5. **Write the history to the bucket** once, after step 2: `--export-bars-from=2015-01`.
   - Until step 3 runs, the adjusted months are exported as they are, and each manifest entry carries its factor. After step 3 the rewritten months are exported again.
   - Check: every ticker-month the table holds for SPY, QQQ and IWM has a file whose row count and `sha256` match its manifest entry, and after step 3 every `factor_min` and `factor_max` is 1.0.

The thin months (SPY 2025-04 to 06, QQQ 2025-01) are adjusted, so they are in step 3's list and are refetched whole there.

## Risks

- A reader that relied on adjusted intraday prices. None found: readers compare intraday bars with live, daily and strike prices. Covered by the unchanged suites.
- Until step 3 runs, the table keeps its mixed months. The nightly re-bases the previous month as it refetches it, so new mixing stops on the first night after the deploy.
- The alarm fires on tickers with real one-off outages. That is its job; the report names the session so it can be refetched or acknowledged.
- A session reads a stale bucket copy. The manifest's `last_ts` and `exported_at` say how fresh each month is, and a failed nightly write fails the job.
- A threshold relative to the ticker's own median cannot see a ticker that has always been thin. The basis check and the first full scan at close-out are what catch stored history.
