---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-DATA-001, REQ-DATA-003, REQ-FRESH-001]
issues: [1190]
canvases: []
site_source_notes: [ADMIN-02, SHARED-07]
done_when:
  - "tests/lib/test_intraday_session_readings.py passes: lib.eastern_time.session_minute_readings(ts, inserted_at, schedule) reads no calendar and returns, per session of the schedule frame it is handed (the frame lib.eastern_time.session_schedule gives), the expected minutes, three counts of distinct regular-hours minutes (true_utc, eastern_label, both), exact and status, where a row is proven when its UTC date is TRUE_UTC_FROM or later or its inserted_at is TRUE_UTC_INSERTED_FROM (2026-09-28 00:00 UTC) or later, and status is OK, THIN or MISSING only when the three counts fall in the same class and UNDETERMINED otherwise; with rows that are not proven on 2025-05-01, 240 minutes from 09:30 ET give 240/150/0 stored as true UTC, 0/240/0 stored as Eastern labels and 240/390/240 stored both ways, all UNDETERMINED; the same true-UTC rows inserted on 2026-11-20 give THIN 240/240/240 with exact true; 04:00 to 13:29 ET stored as true UTC gives 240/390/240 UNDETERMINED; 04:00 to 20:00 ET gives OK 390/390/390 stored each of the three ways; the same session on 2025-01-15 stored as labels gives 331/390/331 UNDETERMINED; no row gives MISSING with exact true; on proven rows 351 of 390 is OK and 350 is THIN, and on the half day 2025-11-28 189 of 210 is OK and 188 is THIN; intraday_month_window(2025, 12) is 2025-12-01 02:00 UTC to 2026-01-01 02:00 UTC and fetch_alphavantage_intraday.month_replace_window returns the same pair (on main c698b24e neither new function exists, and stored_intraday_to_eastern counts 240, 0 and 390 regular-hours minutes for the first three shapes and 390 for the 04:00 to 13:29 ET shape, run 2026-11-13)"
  - "tests/lib/test_intraday_session_readings.py::test_place_stored_rows passes: lib.eastern_time.place_stored_rows(ts, volume, inserted_at) returns each row's UTC instant, a keep flag and a proven flag; a proven row keeps its stored instant whatever the other rows of its date look like; a row that is not proven gets the instant stored_intraday_to_eastern gives it; where two rows land on one minute the proven row is kept, and between two rows that are not proven the one stored_intraday_to_eastern keeps; for one complete 04:00 to 20:00 ET session on 2025-05-01 with a volume spike at 09:30, stored as true UTC, as labels, and both ways with either copy kept on a shared key, the kept regular-hours rows are the session's 390 minutes and carry the session's own high and low; and the same session with flat volume, stored both ways with the label copy on the shared keys and no row proven, comes back with 390 kept regular-hours rows that sit on minutes other than the bars' own, every one flagged not proven, which is the named limit of Design F (on main the function does not exist; the resolver alone gives those 390 minutes and that high and low in the four spiked storages and 390 wrong minutes in the flat one, run 2026-11-13)"
  - "tests/audits/test_audit_intraday_session_gaps.py passes for the scheduled scan: with the clock at 2026-11-13 15:00 UTC audit_all reads the sessions 2026-11-05, 11-06, 11-09, 11-10 and 11-11 for SPY, QQQ and IWM with exactly one query per ticker through gcp.database.query_to_dataframe_strict with timeout_s 120, whose SQL holds interval = '1min', bounds ts from 2026-11-05 02:00 UTC to before 2026-11-12 02:00 UTC, selects ts and inserted_at and takes no date from ts; the scan fetches the schedule with _calendar(session_schedule, ...) and hands it to session_minute_readings, which is not called through _calendar; a session with no regular-hours bar adds one row with table market_data_intraday [sessions], status stale, expected_latest the session, row_count_recent 0 and detail 'MISSING: 0 of 390 regular-hours minutes', a session with 240 adds one with detail 'THIN: 240 of 390 regular-hours minutes', a session with 351 adds none, five thin sessions give five rows, and --strict exits 1 on any such row; a reader raising ConnectionError('connection refused') and a reader raising KeyError('inserted_at') each propagate out of audit_all; a KeyError raised inside session_minute_readings propagates out of audit_all as a KeyError and adds no nyse_calendar row; a calendar error from session_schedule gives the one nyse_calendar row and --strict exits 2; and audit_all adds no market_data_intraday [gap] row (on main the scan asks only whether a UTC day has a row, through the swallowing reader: 30 bars a day add no row, and a failed read comes back as an empty frame and adds a [gap] row per ticker with 0 of the five days present; _calendar turns a KeyError of the function it wraps into the calendar failure, run 2026-11-13)"
  - "tests/audits/test_audit_intraday_session_gaps.py passes for what a scheduled run prints: main() with --strict over stubbed readers that hold 240 regular-hours minutes for SPY on 2026-11-09 prints a report with one line that holds market_data_intraday [sessions], SPY and stale, a line that holds 'detail: THIN: 240 of 390 regular-hours minutes', a details line that holds expected_latest 2026-11-09 and row_count_recent 240, and an Overall line that reads STALE, and exits 1; with every session whole the report holds no line with [sessions], its Overall line is printed, and nothing the run prints or logs holds 'check=intraday_session_gaps'; with the scan's read raising ConnectionError the run logs 'check=intraday_session_gaps FAILED after' and prints no report (on main, main() sets the root logger to WARNING, so a passing _timed check logs nothing and a failing one logs that line, run 2026-11-13)"
  - "tests/audits/test_audit_intraday_session_gaps.py passes for --intraday-gap-since: it runs this scan alone (audit_all is not called); per ticker it issues one strict first-row probe and then one strict query per month window, from the later of the given date and the UTC date of the first stored row, none spanning more than one month window, every SQL text holding interval = '1min'; it prints one line 'SESSION-GAP TICKER YYYY-MM-DD STATUS true_utc=N eastern_label=N both=N expected=N exact=yes|no' per MISSING, THIN or UNDETERMINED session, one line 'MONTH TICKER,YYYY-MM rows=N unproven_rows=N' per month window that holds a row, one line 'NO-ROWS TICKER' for a ticker with no stored row, and a last line that starts 'intraday-gap-since summary:' and holds seconds=N; sessions before the first stored row print nothing; without --strict it exits 0 whenever the summary line is printed, whatever it listed; with --strict it exits 1 when a SESSION-GAP or NO-ROWS line is printed and 0 when none is; a calendar error exits 2 with and without --strict and prints no summary line; --intraday-gap-tickers narrows the run to the named ones of SPY, QQQ and IWM; any other ticker, an unparseable date, a date after the last settled session and --json are usage errors that exit 2 before any query; ConnectionError('connection refused') and KeyError('inserted_at') from a reader, and a KeyError raised inside session_minute_readings, each propagate and the summary line is not printed (on main the flag does not exist)"
  - "tests/api/test_health_freshness_session_gaps.py passes: with audit_all running for real at a clock fixed on 2026-11-13 15:00 UTC, over stubbed readers that hold no SPY bar for 2026-11-09, GET /api/health/freshness answers 200 with a tables row whose table is market_data_intraday [sessions], ticker SPY, status stale, expected_latest 2026-11-09 and a detail that starts with MISSING, and overall_status stale; GET /api/admin/data-sources answers 200 with market_data_intraday at status stale and 'market_data_intraday [sessions] (SPY): stale' in its message; with the scan's read raising ConnectionError('connection refused') both routes answer 503; with it raising KeyError('inserted_at'), and with it raising a sqlalchemy OperationalError that wraps a pg8000 DatabaseError of SQLSTATE 57014, both answer 500; python scripts/export_openapi.py --check passes and platform/api/openapi.json is not in the PR's diff (on main neither response can hold such a row; lib.infra_errors.is_infrastructure_error calls the first exception an outage and the other two defects, run 2026-11-13)"
  - "tests/gcp/test_intraday_verify_basis.py passes for the measure: fetch_alphavantage_intraday.session_basis_verdicts(rows, daily, schedule) measures a session only when session_minute_readings calls it OK and market_data_daily holds for it a row whose data_source is one of TRUE_DAILY_SOURCES (alphavantage_daily, av_daily_backfill, av_watched_backfill) with a positive high and low; f_high is the highest 1-min regular-hours high over the daily high and f_low the lowest low over the daily low, each rounded to 5 decimals and compared in units of 0.00001; both from 0.99970 to 1.00030 inclusive is AS-TRADED when the session is exact and INFERRED when it is not, both below 0.99970 or both above 1.00030 is ADJUSTED, anything else is ODD; with daily high 600.00 and low 590.00 from alphavantage_daily, both extremes at 0.99430 give ADJUSTED with session factor 0.99430, at 0.99969 ADJUSTED, at 0.99970 and at 1.00030 AS-TRADED, at 1.00031 ADJUSTED, a low 1 percent under with the high equal gives ODD, and a high at 0.99900 with a low at 1.00100 gives ODD; a complete proven session whose bars sit at 0.99430 of the traded price and whose daily row was built from those bars (data_source alphavantage_1min, high and low equal to the bars' own) is UNMEASURED with reason daily_from_intraday and is not AS-TRADED; a daily row with a NULL data_source, and one stamped yahoo, give daily_source_unknown; no daily row gives no_daily_row; a NULL or non-positive daily high or low gives daily_not_positive; regular-hours rows with no non-null high or low give no_rth_high_low; a row stamped av_watched_backfill is measured (on main no basis check exists; fetch_market_data.build_daily_row stamps alphavantage_1min when the daily endpoint gave nothing, and such a row reads 1.00000 against its own bars stored at 0.99430, run 2026-11-13)"
  - "tests/gcp/test_intraday_verify_basis.py passes for --verify-basis: for each listed ticker-month it issues one strict bars query bounded by the month window with interval = '1min' in the SQL text, and one strict market_data_daily query per ticker that selects date, high, low and data_source; it prints 'BASIS-FAIL TICKER YYYY-MM sessions=N first..last factor=MIN..MAX inferred=N' for a month holding an ADJUSTED session (one line for a month on two bases, showing factor=0.99430..0.99725, and one line for each of two months whose only ADJUSTED sessions are the last of one and the first of the next), EMPTY for a listed month with no rows, UNMEASURED with a count per reason for sessions with no measurable daily row or no regular-hours high and low, 'INCOMPLETE TICKER YYYY-MM sessions=N first..last inexact=N' for MISSING, THIN and UNDETERMINED sessions, INFERRED for sessions measured as traded from a row that is not proven, one 'ODD TICKER YYYY-MM-DD high=F low=F exact=yes|no' line per ODD session, and a last line that starts 'verify-basis summary:'; it exits 1 when a BASIS-FAIL or EMPTY line is printed or the list has no lines; otherwise 3 when an INFERRED line, an INCOMPLETE line with inexact above 0 or an ODD line with exact=no is printed; otherwise 0; a month whose rows are all proven and that holds as-traded sessions, one session with no daily row, one whose daily row is stamped alphavantage_1min, one THIN session and one ODD session prints UNMEASURED, INCOMPLETE and ODD lines and exits 0; the same month with one as-traded session resting on a row that is not proven prints INFERRED and exits 3; a month of unproven as-traded sessions of which twelve are thin and lack the minutes holding the daily high and low prints INCOMPLETE and no BASIS-FAIL line and exits 3; a complete May 2025 month stored as true UTC, as labels and both ways prints the same lines in the three storages (INFERRED when as traded, BASIS-FAIL with the same factor when adjusted); a line naming a ticker other than SPY, QQQ and IWM exits 1 before any query; --verify-basis together with --verify-months or --replace-months is a usage error; ConnectionError('connection refused') and KeyError('high') from a reader each propagate and no summary line is printed (on main the flag does not exist)"
  - "tests/gcp/test_intraday_replace_levels_tables.py passes: replace_month hands replace_rows_in_window the six strat_features_levels tables (1m, 5m, 15m, 30m, 60m, 4h) as tables to clear, beside the nine it hands over on main, and tests/gcp/test_intraday_replace_months.py passes unmodified (on main DERIVED_TS_TABLES holds nine names and none of the six)"
  - "tests/meta/test_workflows_no_continue_on_error.py passes: no mapping at any depth of any .yml, .yaml, .yml.disabled or .yaml.disabled file under .github/workflows carries continue-on-error with a value other than the boolean false, and the test's own cases show it rejects true on a step, true on a job, the string true, yes, a GitHub expression, a value that arrives through a YAML merge key and a file that does not parse, and accepts false, an absent key, the words in a comment and the words inside a run script; .github/workflows/README.md holds exactly one line that contains continue-on-error, that line contains 'on any step or job' and the test's path, and the file no longer contains 'on a fetch or validation step' (on main no test reads the key, the 12 workflow files hold it nowhere, and the README forbids it on a fetch or validation step only)"
  - "make test passes on the PR head with tests/gcp/test_evaluate_ew_strikes.py, tests/gcp/test_intraday_as_traded.py, tests/gcp/test_intraday_replace_months.py, tests/gcp/test_intraday_writers_utc.py, tests/gcp/test_av_intraday_universe.py, tests/audits/test_audit_data_freshness.py, tests/api/test_route_coverage.py, tests/api/test_admin_users_datasources.py, tests/api/test_platform_api.py, tests/meta/test_production_writers.py and tests/meta/test_timezone_boundaries.py unmodified, tests/fixtures/timezone_boundary_baseline.json unmodified, and gcp/deploy.sh, platform/api, CLAUDE.md and gcp/fetchers/export_intraday_bars.py not in the PR's diff"
  - "The PR body gives, each run read-only through scripts/db_query_cr.sh and pasted with its execution id: EXPLAIN (ANALYZE, BUFFERS) for the scheduled scan's query for SPY, for the month-window bars query of the on-demand scan and of the basis check for SPY 2025-05, for the first-row probe for SPY and for the basis check's market_data_daily query for SPY, each showing rows read on its scan node equal to the rows it returns and the probe reading at most 10 rows; the regular-hours bar count of each of the five settled sessions on the day of the run for SPY, QQQ and IWM; and the number of market_data_daily rows per ticker and data_source for SPY, QQQ and IWM, NULL counted as its own value, with the first and last date of each. It also gives, measured locally, the peak resident memory of --intraday-gap-since over one ticker's 143 synthetic months of 50,000 rows each, under 256 MB (the prototype of 2026-11-13 peaked at 117 MB; on main the earlier form of the scheduled query read 5,827 rows in 5.7 ms, db-query-q6wbd; how many daily rows of the three tickers carry each data_source is not known)"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md gain the (FEAT-DATA-001, ADMIN-02) row and the existing (FEAT-DATA-001, SHARED-07) row is extended (the new source hash and this change's prose first, then 'Earlier:' and the earlier note's prose from 'Purchased account ceiling' to its end, unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes (on main the notes table holds FEAT-DATA-001 rows for DASHBOARD-01, LIVE-03 and SHARED-07 and none for ADMIN-02)"
status: draft
supersedes: null
---

# market_data_intraday checks: a session gap alarm, a basis check, a workflow test, and the levels tables in the replace's clear list

## Scope

- This spec is the checks: how a stored session is read (Design F), the gap alarm and the on-demand scan with the API response (Design B), the basis check (Design C), the workflow test (Design D), and the six levels tables in the replace's clear list (Design G).
- It was one spec with the bucket copy and the close-out runbook. Those are now `docs/superpowers/specs/2026-11-13-feat-data-001-intraday-bucket-copy.md` (file B), in the same PR. The single spec counted 16 tasks, and a plan over about 15 means the spec is too big (`.claude/skills/product-delivery/references/plan-template.md:39`).
- This file has no bucket and writes no production data. File B's plan opens after this file's implementation is on `main`.
- The design letters are those of the single spec, kept so the review threads still point at them. A (requests) is done in the sibling spec below. E (the bucket copy) is file B.
- The request change is done and is not specified here. `docs/superpowers/specs/2026-11-13-feat-data-001-intraday-as-traded.md` (#1865) is implemented by #1874 (`main` 8712afb6) and was deployed on 2026-11-13 (the deploy evidence is on #1874; not re-read for this revision): every `TIME_SERIES_INTRADAY` request sends `adjusted=false`, and `tests/gcp/test_intraday_as_traded.py` (14 cases) holds it.
- The scan and the basis check cover SPY, QQQ and IWM only.
- No trading cost is applied or stored anywhere in this change. Both checks read prices as traded and nothing else.
- Code references are to `main` c698b24e.

## Problem

Found on 2026-11-13. Both defects were silent.

Where a number below has no execution id beside it, it was reported by the analysis session of 2026-11-13 and was not checked for this revision. File B's runbook regenerates every list with the deployed checks before any write (its step 2).

### 1. Sessions went missing and nothing said so

- SPY and QQQ had no 1-min bars for 31 sessions, 2025-11-17 to 2025-12-31. IWM had none for 9, 2025-11-17 to 2025-11-28.
- Cause: every SPY, QQQ and IWM bar from 2024-12 to 2026-01 was written in one manual load on 2026-02-23 (`inserted_at` 02:40 to 03:05 UTC, no Cloud Run execution or workflow run). What it loaded had been fetched in mid-November 2025.
- These sessions were refilled on 2026-11-13 with the owner's yes, after the request change was deployed (executions `fetch-alphavantage-intraday-dbjxf` for SPY and `-7gdpw` for QQQ, 2025-11-01 to 2025-12-31, and `-4l6pj` for IWM, 2025-11-01 to 2025-11-30). 66,923 new rows. The check afterwards (db-query-4m2s4) found no missing session in those months and the refilled sessions at factor 1.0.
- Thin sessions (under 90% of the session's regular-hours minutes) are still stored. Over the history as exported on 2026-11-13 (SPY from 2022-02-24, QQQ and IWM from 2015-01-02):

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

  SPY 49, QQQ 23, IWM 1. SPY bars before 2022-02-24 were not in that export: every SPY total in this spec is a lower bound. The cause of the thin sessions was not traced.
- Where the table comes from: the list of thin sessions the analysis session kept from its local export (73 rows). The table was recounted from that list for this revision and matches. The export was many `db-query` runs, so the table has no one execution id.
- How that count placed each stored row was not recorded. If it used `lib.eastern_time.stored_intraday_to_eastern`, some counts are off (Design F). The deployed checks regenerate the list before any write (file B, step 2).
- Nothing revisits old months.
  - `av-intraday-nightly` (`0 21 * * 1-6`, `gcp/deploy.sh:4741`, `--symbol=ALL --force`) refetches the previous month to today.
  - `av-intraday-monthly` (`0 21 1 * *`, `gcp/deploy.sh:4723`) runs the same job with no arguments. Without `--force`, `process_symbol` skips a ticker that holds 100,000 rows since 2024 (`gcp/fetchers/fetch_alphavantage_intraday.py:273`), which is all three.
  - The monthly GitHub workflow ran once (2025-12-01) and reported success with `continue-on-error` on every fetch step. Its output was never stored. The file is gone from `main`.
- The freshness watchdog's scan of this table cannot see either case (`scripts/audit_data_freshness.py`, `gap_scan_days: 5`, `:133`). Run on `main` on 2026-11-13 with stubbed readers:
  - It asks only whether a day has any row, and takes the day with `DATE(ts)` in UTC (`scripts/audit_data_freshness.py:785`). Five days of 30 bars each add no row.
  - It reads through `query_to_dataframe`, which returns an empty frame on a database error (`gcp/database.py:218-241`). A failed read then adds a `[gap]` row for each ticker with 0 of the five days present: an outage reads as a gap.
  - The 350-row floor applies to the latest day alone and counts extended-hours bars.
  - A gap older than five sessions when the watchdog started is never seen.

### 2. Stored prices are on many bases

- Until 2026-11-13 the 1-min requests returned split- and dividend-adjusted prices, adjusted as of the call. So every stored bar sits at the basis of its last fetch.
- Measured against AlphaVantage's `adjusted=false` series, bar by bar with identical volumes: SPY 2025-04 and 2025-05 are stored at 0.99430 of the traded price, SPY 2025-06 steps to 0.99725 at the June ex-dividend date, QQQ 2025-01 is at 0.99629, and SPY, QQQ and IWM 2025-11 are at exactly 1.00000.
- The nightly made new stretches each time an ex-dividend date fell in the month it refetched. SPY is stored about 0.25% low for 2026-02-02 to 03-19 (0.99724), 2026-05-01 to 06-17 (0.99746) and 2026-08-03 to 09-17 (0.99753). SPY 2026-08-31 15:59 ET is 765.053 in the table and traded at 766.95.
- New mixing has stopped: the request change is deployed, and 2026-09-28 to 2026-11-12 read at factor 1.0 on all 34 sessions (db-query-tvjtp).
- Months that hold sessions on an adjusted basis, counted on 2026-11-13 before the refill by comparing each session's 1-min regular-hours high and low with the daily table's. The count used the first draft's rule (two or more consecutive sessions with high and low both off by more than 3 bp). The refill added no adjusted month.

| Ticker | From 2025-01: months | Rows in them | Lowest factor | Whole exported history: months | Rows in them |
|---|---|---|---|---|---|
| SPY (whole history from 2022-02-24 only) | 15 | 304,302 | 0.99132 | at least 50 | at least 923,571 |
| QQQ | 15 | 314,655 | 0.99629 | 119 | 1,983,926 |
| IWM | 16 | 317,038 | 0.99221 | 120 | 1,737,874 |
| Total | 46 | 935,995 | | at least 289 | at least 4,645,371 |

- IWM 2025-12 was not part of the refill and is still adjusted: 11 sessions near 0.9966.
- IWM and QQQ 2015-01 to 2016-04 (334 sessions each) have no daily row, so their basis could not be measured.
- That count took every daily row as traded. Not every daily row is: when the daily endpoint gives nothing, the nightly builds the daily row from the session's own 1-min bars and stamps it `alphavantage_1min` (`gcp/fetchers/fetch_market_data.py:282-291`). Such a session measures 1.0 against its own bars whatever their basis (run 2026-11-13: bars at 0.99430 read 1.00000). How many daily rows of the three tickers carry that stamp is not known (Design C; a `done_when` measurement).
- Readers compare these bars with as-traded numbers: the brief's levels come from the daily table, and live quotes and strikes are as traded (`platform/api/routers/live.py:403`).

## Non-goals

- No production write, and no deploy other than the staging deploy of the API that every merge to `main` starts. Every other production step is in Close-out and waits for the owner's own yes. The only production access before the merge is the read-only measurements of `done_when`, through `scripts/db_query_cr.sh`.
- No bucket copy of the bars, no manifest, no export flag: file B. No stored bar is refetched or rewritten here: file B's runbook.
- No ticker other than SPY, QQQ and IWM is scanned or checked.
- No change to a request, to the watchlist, or to which tickers or months any job fetches.
- No new writer of `market_data_intraday`. The draft spec `2026-11-13-feat-data-001-two-bar-writers.md` holds the writers to `gcp/fetchers/fetch_alphavantage_intraday.py` and `gcp/fetchers/fetch_market_data.py`. Nothing here adds a third. The functions added to the first of those files only read (Other specs this one meets).
- No change to `stored_intraday_to_eastern` or to any reader that uses it (the Charts API, `_held_session_dates`, `verify_month`, `load_intraday_bars`, the level calibration). Design F adds functions beside it. File B changes three of those readers, the ones its runbook's recompute runs (its Design H): the strat feature loader, `load_intraday_bars` and the level calibration's reader. This file's implementation changes none.
- No change to `gcp/deploy.sh`, to a schedule, or to any job's memory, timeout or retries. That file belongs to FEAT-DEPLOY-001 and the gate refuses it here.
- No change to `platform/api`. The two routes that serve the freshness report carry the new rows as they carry every other row.
- No change to the daily table or to `adjusted_close`. The basis check reads `data_source` and does not rewrite it.
- No change to the audit's logging level (`scripts/audit_data_freshness.py:1572`).
- No edit of `CLAUDE.md`. Its wording change is a FEAT-CICD-001 step (Close-out, step 5).

## Approaches considered

1. An alarm on sessions and a basis check, with a rewrite to as-traded in file B's runbook (chosen). Each of the two silent failures gets a check that fails loudly, and a refetch can never move a stored bar again.
2. Adjusted everywhere: every bar would have to be rewritten after every ex-dividend date, and stored bars would stop matching live and daily prices.
3. Store both bases: a second set of price columns doubles the table for no reader that exists.
4. Fix the writers only: the missing sessions were found by accident a year later.

For reading dates stored before 2026-09-28 (Design F):

1. Three readings, proof by insert time, and UNDETERMINED where the readings disagree (chosen). It never counts a session as whole on an inference, and it is exact for every row written since the writers were fixed.
2. Keep `stored_intraday_to_eastern` for the counts: measured wrong on thin sessions (Design F).
3. Pick each date's convention from the daily table's high and low: a thin session lacks the minutes holding the extremes under either reading, so the pick fails exactly where it is needed.

For which daily rows the basis check trusts (Design C):

1. Only rows stamped by a writer that reads the daily endpoint (chosen). A daily row built from the 1-min bars cannot test those bars.
2. Trust every daily row: the first draft's rule, and the hole the review found.
3. Compare a daily row's values with the bars to guess its source: an as-traded session also matches its own bars, so the guess cannot tell the two apart.

## Design

### B. Gap alarm

A session scan beside the checks the freshness watchdog runs (`scripts/audit_data_freshness.py`, Cloud Run job `freshness-watchdog`, `--strict`, 11 hourly runs on a weekday and one nightly, `gcp/deploy.sh:4462-4463`).

- **Tickers**: SPY, QQQ and IWM, the list of the table's `CHECKS` entry.
- **Sessions**: NYSE sessions from `lib.eastern_time.session_schedule`, never a weekend or holiday.
  - The scan reads the schedule once, with `_calendar(session_schedule, first, last)`, and hands the frame to `session_minute_readings` (Design F). Only the calendar call is wrapped.
  - Why: `_calendar` turns any exception of the function it wraps into the calendar failure (`scripts/audit_data_freshness.py:414-419`). If the readings read the calendar themselves and were wrapped, a defect in them would show as the `nyse_calendar` row with exit 2 (run on `main` on 2026-11-13: a `KeyError('inserted_at')` raised inside a wrapped function came out as `CalendarUnavailable`).
  - So a calendar failure is the one `nyse_calendar` row and `--strict` exit 2, as for every other session check, and a `KeyError` inside the readings propagates as a defect.
- **MISSING**: a session with zero regular-hours 1-min bars.
- **THIN**: a session whose count of regular-hours minutes is under 90% of that session's own length from the calendar (390, or 210 on a half day such as 2025-11-28). The comparison is in whole numbers: THIN when 10 x count is under 9 x expected, so 351 of 390 is whole and 350 is thin.
  - SPY, QQQ and IWM have a bar in nearly every regular-hours minute, so the calendar is the baseline and no earlier session is read.
  - A threshold relative to the ticker's trailing 20-session median was measured on the stored bars and rejected: a run of thin sessions drags the median down, and it passed 6 of SPY's 49 thin sessions and 2 of QQQ's 23.
- **UNDETERMINED**: a session stored before 2026-09-28 whose count depends on which timestamp convention its rows are in (Design F). It is reported like the other two. The scheduled scan cannot produce it: its window holds only UTC dates from `TRUE_UTC_FROM` on, where every row is a true instant by construction.
- **Counts** come from `session_minute_readings`. The scan reads `ts` and `inserted_at` and nothing else. No date is taken from `ts` in SQL, and the resolver is not used.

**Scheduled scan**

- The last 5 settled sessions, the same five the old scan used: `_recent_trading_days` with the check's `settle_hour_et` 21 and `settle_lag_days` 1. At 2026-11-13 15:00 UTC they are 2026-11-05, 11-06, 11-09, 11-10 and 11-11 (run 2026-11-13). The check's settle values are not changed.
- It runs inside `_session_dependent_checks`, in the loop over `CHECKS`, for an entry that carries `session_gap_days`, under `_timed("intraday_session_gaps", ...)`. So it is part of `audit_all()`, and a test that empties `CHECKS` runs no scan (`tests/audits/test_audit_data_freshness_column_nullity.py:270`).
- One query per ticker through `query_to_dataframe_strict` with `_CHECK_QUERY_TIMEOUT_S` (120 s):
  `SELECT ts, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end`.
  - `start` is 02:00 UTC on the oldest session's date and `end` is 02:00 UTC on the day after the newest. A session's rows lie in that window under either convention (labels 04:00 to 20:00 on its date; true instants from 08:00 or 09:00 UTC on its date to 00:00 or 01:00 UTC on the next).
- One `FreshnessRow` per failing ticker and session:
  - `table` `market_data_intraday [sessions]`, `ticker`, `status` `stale`, `expected_latest` the session date, `last_row_at` and `lag_hours` null, `expected_max_hours` the check's 30, `row_count_recent` the lowest of the three counts, `writer_job` `fetch-alphavantage-intraday`;
  - `detail` one of `MISSING: 0 of 390 regular-hours minutes`, `THIN: 240 of 390 regular-hours minutes`, `UNDETERMINED: 240 as true UTC, 390 as Eastern labels, 240 as both, of 390`.
  - A session that is whole adds no row.
- A stale row makes `--strict` exit 1, and the failure notifier files the job failure.

**What a scheduled run prints** (how the audit reports every check today: its rows, through `format_terminal`)

- For a failing session, run on `main` on 2026-11-13 with a hand-built row:
  - the row's line, holding `market_data_intraday [sessions]`, the ticker and `stale`;
  - a line holding `writer-job: fetch-alphavantage-intraday`;
  - a line holding `detail: THIN: 240 of 390 regular-hours minutes`;
  - a `details:` line holding `expected_latest` (the session) and `row_count_recent`;
  - and the report's last line, `Overall: STALE`.
- For a run in which every session is whole: nothing of its own. The scan reports failures only, as the gap scan, value sanity and column nullity do (`scripts/audit_data_freshness.py:1436`, `:1495`). The report's `Overall:` line shows that `audit_all()` returned, and a scan that raises ends the run with a traceback and no report.
- `_timed` logs `check=intraday_session_gaps ok in N s` at INFO. `main()` sets the root logger to WARNING (`scripts/audit_data_freshness.py:1572`), so that line is not printed on a passing run (run 2026-11-13: nothing logged). Its `check=intraday_session_gaps FAILED after N s` line is logged at ERROR and is printed. The logging level is not changed for one check.
- So no close-out step reads a `check=` line of a passing run. What the close-out reads instead is in Close-out, step 2.

**The old day-presence scan leaves this table.** The table's `CHECKS` entry drops `gap_scan_days` and gains `session_gap_days: 5`.

- Every hole the old scan could flag (no row on the UTC date) is MISSING in the new one, so keeping both would report one hole twice.
- The old one reads this table by `DATE(ts)` through the swallowing reader.
- `_query_gap_scan` itself is untouched and still runs for every other table. `tests/audits/test_audit_data_freshness.py` builds its own check dicts and stays as it is (50 passed on `main`, run 2026-11-13).
- The `min_rows_per_day` floor on the latest day stays.

**On-demand scan**: `--intraday-gap-since YYYY-MM-DD`, for file B's runbook, for any bulk operation, and for anyone who needs the sessions missing from a window of history. It is not scheduled.

- It runs this scan alone. `audit_all()` is not called: the other checks take 8 to 14 minutes in the job (`gcp/deploy.sh:2536-2537`) and are not what the run was asked for.
- `--intraday-gap-tickers SPY,QQQ` narrows it to some of the three. The default is all three.
- Per ticker:
  - One strict probe: `SELECT min(ts) AS first_ts FROM market_data_intraday WHERE ticker = :t AND interval = '1min'`.
  - Sessions run from the later of the given date and the UTC date of `first_ts`, to the last settled session. Sessions before the first stored row are history that was never stored, not gaps.
  - One strict query per month window, the scheduled scan's SQL with the window's bounds. One month is in memory at a time.
- The month window is `lib.eastern_time.intraday_month_window(year, month)`: `[M-01 02:00Z, (M+1)-01 02:00Z)`, which holds month M in both conventions. It is the arithmetic of `month_replace_window` (`gcp/fetchers/fetch_alphavantage_intraday.py:443-447`), moved so both modules use one definition; `month_replace_window` returns it.
- Output, printed with `print`, not logged, so it does not depend on the logging level:
  - `SESSION-GAP TICKER YYYY-MM-DD STATUS true_utc=N eastern_label=N both=N expected=N exact=yes|no`, one per failing session.
  - `MONTH TICKER,YYYY-MM rows=N unproven_rows=N`, one per month window that holds a row. These lines are the list of stored months, and the ones with `unproven_rows` above 0 are the core of file B's rewrite list.
  - `NO-ROWS TICKER` for a ticker with no stored row.
  - A last line, `intraday-gap-since summary: ...`, with per ticker the first stored date and the number of sessions scanned and of each status, and `seconds=N`, the scan's own wall-clock. A run that ends without it crashed.
- Exit codes. The job has `--max-retries 0` (`gcp/deploy.sh:2535`), so a non-zero exit is not run again.

| Exit | When |
|---|---|
| 0 | the scan finished and printed its summary line: without `--strict`, whatever it listed; with `--strict`, only when it printed no SESSION-GAP and no NO-ROWS line |
| 1 | with `--strict`: a SESSION-GAP or NO-ROWS line was printed. Also a reader error, which raises: a traceback and no summary line |
| 2 | a usage error, before any query (an unparseable date, a date after the last settled session, a ticker outside the three, `--json` with this flag); Cloud SQL not configured (`scripts/audit_data_freshness.py:1577-1583`); a calendar failure, with or without `--strict`, with no summary line |

- A run that only needs the list leaves `--strict` out and exits 0. File B's runbook runs it that way at every step.
- Listing run: `gcloud run jobs execute freshness-watchdog --region us-east1 --args="--intraday-gap-since=2015-01-01,--intraday-gap-tickers=SPY" --wait`. The gate form adds `--strict` to the arguments.

**Where else the scan shows**

- `audit_all()` also backs `GET /api/health/freshness` (`platform/api/routers/health.py:133`) and, through the same cached report, the admin data-sources view (`platform/api/routers/admin.py:1392-1402`).
- The freshness response gains the rows above in `tables`, and `overall_status` is `stale` while one exists. `FreshnessRow` in `platform/api/schemas.py:1530` already has every field, so the OpenAPI document does not change.
- The admin view folds `market_data_intraday [sessions]` into the `market_data_intraday` dataset: the dataset reads `stale` and its message carries `market_data_intraday [sessions] (SPY): stale` (run on `main` with a hand-built row, 2026-11-13). The message names the ticker; the session is in the freshness response.
- `tests/api/test_health_freshness_session_gaps.py` is the API test of the changed response.

### C. Basis check

`fetch_alphavantage_intraday --verify-basis PATH`, beside `--verify-months`: read-only, no vendor call. It is a separate run from `--replace-months` and `--verify-months`; two of them together is a usage error.

- **Input**: a file of `TICKER,YYYY-MM` lines, read by `_read_replace_list`. A file with no lines exits 1, as `--verify-months` does. A line naming a ticker other than SPY, QQQ and IWM exits 1 before any query.
  - In the job the path is a `gs://` object. `_read_text` reads a local file or `gs://bucket/object` (`gcp/fetchers/fetch_alphavantage_intraday.py:652-661`), and the image holds no list. The form is `--verify-basis=gs://adept-mountain-474619-d4-trading-data/intraday-lists/<name>.csv`.
- **Reads**, both strict with a 120 s statement timeout:
  - bars, one per listed ticker-month: `SELECT ts, high, low, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end`, over the month window;
  - daily, one per ticker over the span of its listed months: `SELECT date, high, low, data_source FROM market_data_daily WHERE ticker = :t AND date >= :first AND date <= :last`. `date` is the session's own date; nothing is converted.
- **Sessions of a listed month**: the calendar's sessions of that month whose close has passed when the check runs. The runner fetches the schedule and hands it on, as the scan does.
- **Which sessions are measured**: only a session that `session_minute_readings` calls OK (whole under every reading) and that has a measurable daily row (next bullet). A thin, missing or undetermined session is never measured, so thinness cannot read as a basis.
- **Which daily rows are measurable**: a row whose `data_source` is in `TRUE_DAILY_SOURCES` and whose high and low are positive. The stamps every writer of `market_data_daily` gives, read at c698b24e:

| `data_source` | Written by | Where its high and low come from | Measured |
|---|---|---|---|
| `alphavantage_daily` | `build_daily_row` when the daily endpoint answered (`gcp/fetchers/fetch_market_data.py:279-281`); `gcp/migrate_to_gcp.py:664`; `scripts/backfill_watchlist_data.py:233` | `TIME_SERIES_DAILY_ADJUSTED`, the `2. high` and `3. low` fields, which are as traded | yes |
| `av_daily_backfill` | `_run_backfill` (`gcp/fetchers/fetch_market_data.py:1049`) | the same endpoint and fields (`:920`, `:941-942`) | yes |
| `av_watched_backfill` | the watched-ticker ingest job, through `_run_backfill` (`2026-11-13-feat-data-001-watched-ticker-ingest.md`, approved on `main`; its code is not on `main` at c698b24e) | the same endpoint | yes. The job drops default-list tickers, so no SPY, QQQ or IWM row is expected to carry it |
| `alphavantage_1min` | `build_daily_row` when the daily endpoint gave nothing (`gcp/fetchers/fetch_market_data.py:282-291`) | the session's own 1-min bars | no: `daily_from_intraday` |
| `yahoo` | the `^VIX` fetch (`gcp/fetchers/fetch_market_data.py:664`) | Yahoo; `^VIX` only | no: `daily_source_unknown` |
| NULL | `scripts/deep_backfill_ticker.py` (it writes no stamp, `:74-102`); rows `_run_backfill` wrote before it stamped (the comment at `gcp/fetchers/fetch_market_data.py:1041-1048`); rows the indicator and premarket writers create with no price (`:546`, `gcp/fetchers/fetch_premarket_refresh.py:354`) | not known from the row | no: `daily_source_unknown` |

  - The stamp is the last stamping writer's. `upsert_dataframe` overwrites on conflict only the columns its frame carries (`gcp/database.py:483-484`, `:513-516`), so a writer with no stamp leaves the one there.
  - Any value not in `TRUE_DAILY_SOURCES`, one not listed above included, is `daily_source_unknown`. A new daily writer is measured only once its stamp is added there.
  - The error is on the safe side: a daily-endpoint row with no stamp is not measured, and a row built from the bars is never measured.
  - How many rows of the three tickers carry each value is not known. The PR body counts them (`done_when`), so the share of sessions the check can measure is known before the merge.
- **Which rows**: `lib.eastern_time.place_stored_rows` (Design F) gives each row its instant; regular hours, from the session's open to its close, are selected after that.
- **The measure**: `f_high` is the highest 1-min regular-hours high over the daily high, `f_low` the lowest low over the daily low, each rounded to 5 decimals and compared in units of 0.00001. The session's factor is their mean, rounded to 5 decimals.
  - AS-TRADED: both from 0.99970 to 1.00030 inclusive.
  - ADJUSTED: both below 0.99970, or both above 1.00030.
  - ODD: anything else.
  - Why the same side: a session that lacks minutes can only have a lower high and a higher low than the daily bar, so missing data moves the two ratios apart; an adjustment moves both the same way. In a hermetic run of 2026-11-13, of 200 synthetic as-traded sessions that each lack the 150 minutes around the high and the 150 around the low, the first draft's rule (both off by more than 3 bp, either side) called 143 off and this rule called none ADJUSTED. A bad print moves one ratio: ODD.
- **A verdict that passes comes from proven rows only.** An AS-TRADED session that is not exact (a row that is not proven counts toward it under either reading, Design F) is INFERRED: reported, and never a pass. An ADJUSTED session fails whether or not its rows are proven; the line counts the inferred ones.
- **A month fails when it holds one ADJUSTED session.** The first draft asked for two consecutive off sessions. That passed a stretch of two that straddles a month end, one in each month (run 2026-11-13), and a nightly refetch can leave a stretch of one.
- **Where it lives**: `session_basis_verdicts(rows, daily, schedule)` and `TRUE_DAILY_SOURCES` in `gcp/fetchers/fetch_alphavantage_intraday.py`. The function takes the month window's rows, the daily frame and the schedule, and returns one record per session: `session`, `status`, `exact`, `verdict`, `reason`, `f_high`, `f_low`, `factor`. It reads nothing itself. The runner prints from it, and file B's export fills its manifest from it.
- **Output**, one line per ticker-month and kind:
  - `BASIS-FAIL TICKER YYYY-MM sessions=N first..last factor=MIN..MAX inferred=N`: N ADJUSTED sessions, the first and last of them, the lowest and highest session factor, and how many are not exact. A month on two bases shows both ends (SPY 2025-06: `factor=0.99430..0.99725`).
  - `EMPTY TICKER YYYY-MM`: a listed month with no rows. It is data that went missing after the list was made.
  - `UNMEASURED TICKER YYYY-MM sessions=N first..last no_daily_row=N daily_from_intraday=N daily_source_unknown=N daily_not_positive=N no_rth_high_low=N`.
  - `INCOMPLETE TICKER YYYY-MM sessions=N first..last inexact=N`: sessions that are MISSING, THIN or UNDETERMINED, and how many of them are not exact. They are the gap scan's findings, not basis failures.
  - `INFERRED TICKER YYYY-MM sessions=N first..last`.
  - `ODD TICKER YYYY-MM-DD high=F low=F exact=yes|no`, one per session.
  - A last line, `verify-basis summary: ...`, with the count of each kind. A run that ends without it crashed.
- **Exit codes.** The job has `--max-retries 1` (`gcp/deploy.sh:2217`), so Cloud Run runs a task that exits non-zero once more before the execution fails (its documented retry; not checked by a run for this spec).

| Exit | When |
|---|---|
| 0 | the run finished; no BASIS-FAIL and no EMPTY line; and no line rests on a row that is not proven |
| 1 | a BASIS-FAIL or EMPTY line was printed; the list has no lines; a line names another ticker (before any query). Also a reader error, which raises: a traceback and no summary line |
| 2 | a usage error: two of the list modes together |
| 3 | none of the above, and at least one line rests on a row that is not proven: an INFERRED line, an INCOMPLETE line with `inexact` above 0, or an ODD line with `exact=no` |

  - What exit 0 says: every measured session is AS-TRADED from proven rows, and every session that was not measured is exact and is listed. It does not say every session was measured. The UNMEASURED, INCOMPLETE and ODD lines and the summary's counts say which were not.
  - Why UNMEASURED never changes the exit: no step can measure a session that has no daily-endpoint row.
  - Why an exact INCOMPLETE or ODD line does not: with proven rows a thin or missing session is a fact the gap scan reports and fails on, and an ODD session is a print that disagrees on one side. No rerun of this check changes either. Before file B's rewrite the same lines rest on rows that are not proven and exit 3.
  - This is what lets file B's runbook end at exit 0 (its step 6). A prototype of the rule was run on 15 hand cases on 2026-11-13.
- **The three-way fixture** (a whole month stored as true UTC, as labels, and both ways) uses sessions with extended hours and an opening volume spike, as stored sessions have. Where both conventions meet on one key the table holds one row, so the fixture does too.
- The 289 months in the Problem were counted with the first draft's rule and with every daily row trusted. This check can list more (one adjusted session now fails its month), names some INCOMPLETE or INFERRED instead, and leaves some UNMEASURED. File B's runbook regenerates the list.

### D. Workflow test

- No file under `.github/workflows` carries `continue-on-error`: the 9 enabled and 3 disabled workflow files were parsed on 2026-11-13 and none holds the key at any depth or in its text. There is no `.github/actions` directory.
- Nothing enforces it. `tests/meta/test_workflows_no_continue_on_error.py` parses every `.yml`, `.yaml`, `.yml.disabled` and `.yaml.disabled` file under `.github/workflows` with `yaml.safe_load` and fails on a `continue-on-error` key, at any depth, whose value is anything but the boolean `false`.
  - `true`, `yes`, the string `'true'` and a GitHub expression all fail: an expression can evaluate to true.
  - A value that arrives through a YAML merge key fails, since the loaded document holds it.
  - A file that does not parse fails: it cannot be vouched for.
  - Disabled files are scanned because renaming one enables it.
  - The words in a comment or inside a `run` script do not fail.
  - A prototype run on 2026-11-13 gave these answers on eleven cases and found nothing in the 12 files.
- What it does not see: a duplicated key (YAML keeps the last; GitHub refuses the file), and anything outside `.github/workflows`.
- It changes no workflow and reads the two gate workflows without touching them. The gate does not count the test or the README as process files (`is_process_file` is false for both, run 2026-11-13), so this PR may carry them.
- **Which rule it enforces** (decision 3): none, anywhere, other than an explicit `false`. The written rule was narrower: CLAUDE.md 3.7 and `.github/workflows/README.md:38` forbid it on a fetch or validation step, and CLAUDE.md's workflow item 3 allows it on non-critical steps. A test cannot tell a fetch step from a non-critical one. A workflow that needs the key later changes this test in the same PR, with the reason.
- The PR rewords the README line to: ``- No `continue-on-error` on any step or job, other than an explicit `false` (CLAUDE.md Rule 3.7; `tests/meta/test_workflows_no_continue_on_error.py`).`` CLAUDE.md is reworded in a separate step (Close-out, step 5), because the gate gives that file to FEAT-CICD-001.

### F. Reading a session stored before 2026-09-28 (used by B and C, and by file B's export and recompute readers)

The table holds two timestamp conventions, true UTC and legacy Eastern clock labelled UTC (CLAUDE.md 3.9). Which rows each rule covers:

| Rows | Convention | How it is known |
|---|---|---|
| stored on a UTC date from `TRUE_UTC_FROM` (2026-09-28) on | true UTC | by construction: every writer has converted with `eastern_index_to_utc` since #1185 |
| stored on an earlier date, inserted on or after 2026-09-28 00:00 UTC | true UTC | proven by `inserted_at` (below) |
| stored on an earlier date, inserted before that | either | not known; never counted on an inference |

For the third kind `stored_intraday_to_eastern` infers the convention from the date's rows, and a thin session defeats the inference. Run on `main` c698b24e on 2026-11-13, flat-volume one-minute rows on 2025-05-01, regular-hours minutes the resolver counts:

| Rows | Stored as true UTC | Stored as labels | Stored both ways |
|---|---|---|---|
| 240 minutes from 09:30 ET (the truth is 240) | 240 | 0 | 390 |
| 04:00 to 13:29 ET, a day cut at 13:30 (the truth is 240) | 390 | 240 | 390 |

So a count taken through the resolver can call a thin session whole, or a present one missing.

**What is added to `lib/eastern_time.py`** (the resolver is not changed):

- `TRUE_UTC_INSERTED_FROM`, 2026-09-28 00:00 UTC, the midnight that opens `TRUE_UTC_FROM`.
- A row is **proven** true UTC when its UTC date is `TRUE_UTC_FROM` or later, or its `inserted_at` is `TRUE_UTC_INSERTED_FROM` or later.
  - The premise is the one `TRUE_UTC_FROM` already rests on. At c698b24e all four writers convert (`gcp/fetchers/fetch_alphavantage_intraday.py:311` and `:596`, `gcp/fetchers/fetch_market_data.py:559`, `gcp/backfill_ticker.py:643`, `gcp/migrate_to_gcp.py:232`), and `gcp.database` refuses a naive `ts` for this table.
  - `inserted_at` defaults to `NOW()` on insert (`gcp/schema.sql:150`), and an upsert does not change it: `upsert_dataframe` updates only the frame's columns, and no writer's frame carries it. So a row a later run rewrote in place stays unproven, which errs on the safe side. `replace_month` deletes and inserts, so every row it writes is proven.
- `session_minute_readings(ts, inserted_at, schedule)` returns, for each session of the schedule it is handed, the expected minutes and three counts of distinct regular-hours minutes. Regular hours run from the session's open to its close as the schedule gives them.
  - `schedule` is the frame `session_schedule(start, end)` returns: one row per session with `market_open` and `market_close` (`lib/eastern_time.py:581-592`). The function reads no calendar. The caller fetches the schedule, so a calendar failure and a defect in the readings stay two different errors (Design B).
  - `true_utc`: every row read as a true instant.
  - `eastern_label`: proven rows as true instants; every other row read as an Eastern clock time stamped UTC.
  - `both`: proven rows, plus the minutes the other rows cover under both readings.
  - Each count is classed MISSING (0), THIN (under 90% of expected) or OK. `status` is that class when the three agree and UNDETERMINED when they do not. `exact` is true when no unproven row counts under either reading.
- `place_stored_rows(ts, volume, inserted_at)`, for the basis check, file B's export and file B's three recompute readers (its Design H), which need each row's instant and not only a count. A proven row is read at its stored instant. Any other row is placed by `stored_intraday_to_eastern`, run over all the window's rows so the rule sees each date entire, which is where every reader sees it. When two rows land on one minute, a proven row is kept over an unproven one, then the resolver's own order applies.
- `intraday_month_window(year, month)` (Design B).

**What it gives**, from a hermetic run of a prototype on 2026-11-13 (rows not proven unless stated; counts are true UTC / Eastern label / both):

| Rows on 2025-05-01 unless stated | Stored | Counts | Status |
|---|---|---|---|
| 240 minutes from 09:30 ET | true UTC | 240 / 150 / 0 of 390 | UNDETERMINED |
| the same | labels | 0 / 240 / 0 | UNDETERMINED |
| the same | both ways | 240 / 390 / 240 | UNDETERMINED |
| the same | true UTC, inserted 2026-11-20 | 240 / 240 / 240 | THIN, exact |
| 04:00 to 13:29 ET (day cut at 13:30) | true UTC | 240 / 390 / 240 | UNDETERMINED |
| the same | labels | 0 / 240 / 0 | UNDETERMINED |
| the same | both ways | 240 / 390 / 240 | UNDETERMINED |
| 04:00 to 20:00 ET, whole | true UTC, labels, or both | 390 / 390 / 390 | OK |
| 09:30 to 15:59 ET only, whole | true UTC | 390 / 150 / 150 | UNDETERMINED |
| 04:00 to 09:29 ET only | labels | 0 / 0 / 0 | MISSING, exact |
| no row | | 0 / 0 / 0 | MISSING, exact |
| 04:00 to 20:00 ET on 2025-01-15, whole | true UTC | 390 / 390 / 390 | OK |
| the same | labels | 331 / 390 / 331 | UNDETERMINED |
| 04:00 to 20:00 ET on 2025-11-05, whole (a winter session like those the refill rewrote in place) | true UTC | 390 / 390 / 390 | OK |
| 240 minutes from 09:30 ET on 2026-10-01 | true UTC | 240 / 240 / 240 | THIN, exact |

**What is claimed, and what is not**

- From 2026-09-28 on, and for every row inserted from then on, the count is exact. This covers the scheduled alarm, every session a replace writes, and every session a refill adds.
- Before that, for unproven rows: a session is OK only when it is whole under every reading, MISSING only when no reading finds a bar, and THIN only when every reading is thin. Anything else is UNDETERMINED: reported, failed, and never given one count.
- A whole legacy-labelled winter session is UNDETERMINED (331 / 390 / 331). Its timestamps are those of a day cut at 15:00 ET and stored both ways.
- Two shapes of unproven rows still read OK when something is wrong. Both need a session stored under both conventions, and file B's rewrite removes both: after a replace every row is proven.
  - **Covered gap.** The missing regular-hours minutes are covered by the other copy's extended-hours rows (regular hours cut at 13:30 ET with full premarket and after-hours, stored both ways: 390 / 390 / 390; the resolver also reads 390). No rule on timestamps separates it from a whole session.
  - **Misplaced whole session.** The session is whole, its volume is flat, and the label copy sits on the keys the two conventions share. The readings say OK, 390 / 390 / 390, and they are right about the count. But `place_stored_rows` puts every unproven row where the resolver puts it, and the resolver puts all 390 regular-hours rows on the wrong minute: the regular hours it returns hold the bars of 13:30 to 19:59 ET (run 2026-11-13: 390 of 390 wrong, and neither the high nor the low is the session's). With an opening volume spike, as stored sessions have, all 390 are right in the same run.
    - What each consumer then does: the gap scan says OK. The basis check measures the wrong rows and prints ODD, ADJUSTED or INFERRED, none of which passes. File B's export writes those rows and flags them only through `inferred_rows`.
- A session whose minutes alternate between conventions can read THIN when it is whole (even minutes as true UTC and odd ones as labels: 270 / 270 / 150). No writer produces that: each writes a whole fetch in one convention. The error is on the reporting side.
- How many stored sessions come out UNDETERMINED was not measured. File B's runbook counts them before any write (its step 2).

### G. Derived tables of a replaced month

- `strat_features_levels_{1m,5m,15m,30m,60m,4h}` are computed from the intraday feature tables, not from the daily table: `strat_enrich_levels.backfill_one` reads `ts, open, high, low, close, volume` from `strat_features_{tf}` (`gcp/research/strat_engine/strat_enrich_levels.py:160-162`), and `_compute_enrichments` derives the opening ranges (`:86`), the prior day, week, month, quarter and year levels (`:91`) and the order blocks with their ATR(14) (`:109-110`) from those bars.
- They are keyed by `(ticker, ts)` like the tables `replace_month` clears, and are not among them (`DERIVED_TS_TABLES`, `gcp/fetchers/fetch_alphavantage_intraday.py:472-476`). A replace that moves keys would leave their rows at keys no feature row has.
- The six tables join `DERIVED_TS_TABLES`. A replaced month's level rows are then deleted in the replace's transaction and listed in its `REBUILD` lines, as the feature rows are. All six exist in production (`tests/fixtures/live_gcp_snapshot_2026-11-09.json`), and the replace skips a table that does not.
- `tests/gcp/test_intraday_replace_months.py` checks the tables handed over as a superset (`:805`) and stays as it is (351 passed on `main`, run 2026-11-13).
- This file changes the list and nothing else. No replace runs from it. Their rebuild and its check are in file B's runbook (its step 7), which runs on readers that place rows by proof (file B, Design H).

### What bad input gets

An outage and a defect do not get the same answer. `lib.infra_errors.is_infrastructure_error` is the classifier; on 2026-11-13 it called `ConnectionError('connection refused')` an outage, and `KeyError('inserted_at')` and a statement timeout (SQLSTATE 57014, wrapped by SQLAlchemy) defects.

| Read | Input | On `main` today | After |
|---|---|---|---|
| scheduled scan | database unreachable (`ConnectionError`) | empty frame; three `[gap]` rows, each with 0 of the five days present | raises out of `audit_all()`: the watchdog job fails and is filed; both routes answer 503 |
| scheduled scan | a defect in the read (`KeyError('inserted_at')`) or a statement timeout | same as above | raises: the job fails; both routes answer 500 |
| scheduled scan | a defect inside `session_minute_readings` | the function does not exist | raises as itself; no `nyse_calendar` row |
| scheduled scan | the query runs and returns no row | `[gap]` row | five MISSING rows for the ticker, which is true |
| scheduled scan | 30 regular-hours bars in a session | no row | one THIN row |
| scheduled scan | calendar failure | `nyse_calendar` row, exit 2 | the same |
| `--intraday-gap-since` | reader error, either kind | the flag does not exist | raises, non-zero exit, no summary line |
| `--intraday-gap-since` | a ticker with no stored row | | `NO-ROWS` line; exit 1 with `--strict`, 0 without |
| `--intraday-gap-since` | calendar failure | | exit 2 with or without `--strict`, no summary line |
| `--verify-basis` | reader error, either kind | the flag does not exist | raises, non-zero exit, no summary line |
| `--verify-basis` | no daily row; a daily row built from the 1-min bars; a daily row with no known stamp; a daily high or low NULL or not positive | | UNMEASURED with the reason counted; never AS-TRADED; the exit does not change |
| `--verify-basis` | a listed month with no rows; an empty list | | EMPTY, exit 1; exit 1 |

- The scan does not follow `_query_column_nullity`, which turns a failed strict read into an `unknown` row (`scripts/audit_data_freshness.py:1046-1073`). An `unknown` row leaves `--strict` at exit 0, so a failed scan would pass.
- Each case in the table has a test named in `done_when`, with the exception it raises.

### Other specs this one meets

- **File B** (`2026-11-13-feat-data-001-intraday-bucket-copy.md`) uses from this file: `intraday_month_window`, `place_stored_rows` (in its export, and in the three recompute readers of its Design H) and `session_minute_readings` in `lib/eastern_time.py`; `session_basis_verdicts` and `TRUE_DAILY_SOURCES` in `gcp/fetchers/fetch_alphavantage_intraday.py`; and, in its runbook only, `--intraday-gap-since`, `--verify-basis` and the six tables in `DERIVED_TS_TABLES`. Its plan opens after this file's implementation is on `main`.
- **The draft strict-bar-loader spec** (`2026-11-13-feat-data-001-strict-bar-loader.md`) names this spec as the place where a session missing inside a backtest window is surfaced. That is `--intraday-gap-since`: run from the window's first date, it prints one `SESSION-GAP` line per failing session, with the ticker and the date, up to the last settled session; the lines dated inside the window are the window's holes. The scheduled alarm covers the last five settled sessions the same way.
  - It does this for SPY, QQQ and IWM only. A backtest of another ticker gets no such list from this spec.
- **The draft two-bar-writers spec** (`2026-11-13-feat-data-001-two-bar-writers.md`). Its guard scans for writes and deletes of `market_data_intraday`.
  - This file adds `session_basis_verdicts` and the `--verify-basis` runner to a sanctioned writer file. Both only read, and neither calls a function that reaches a write, so that guard's writer closure does not grow.
  - The six names added to `DERIVED_TS_TABLES` are not the bars table.
  - `scripts/audit_data_freshness.py` gains the string `fetch-alphavantage-intraday` as a row's `writer_job`. That guard already lists the file among those that name a writer job.
  - No file added here spells a write statement or a write helper call on the table, a docstring included.
- **FEAT-REPLAY-001** (`2026-11-13-feat-replay-001-replay-bars-from-the-table.md`, approved). Replays read bars only from the table. Nothing here reads bars from anywhere else, and the new flag names (`--intraday-gap-since`, `--intraday-gap-tickers`, `--verify-basis`) match none of the patterns of its registration guard.
- Every new read of the table names `interval = '1min'` in its SQL text, not as a bound parameter, so the interval guard of the draft strict-bar-loader spec passes whichever lands first.
- The watched-ticker ingest spec (approved, on `main`) adds a `job_runs` heartbeat check to `scripts/audit_data_freshness.py` and writes daily bars only, stamped `av_watched_backfill` (Design C). It shares the file with Design B and no function or `CHECKS` entry.
- New code changes zone only through `lib/eastern_time.py`. `tests/meta/test_timezone_boundaries.py` and its baseline stay as they are.

### Site traceability

`site_source_notes` cannot be widened by the implementation PR, so it is declared by a rule: one element per changed route or changed table reader the site shows, per page, the first Chain row on that page of `docs/product/03-SITE-TRACEABILITY.md` that names it. Bare line numbers in this section are that document's.

| Changed route or reader | Page | Chain rows that name it | Declared |
|---|---|---|---|
| `GET /api/health/freshness`: `tables` gains `market_data_intraday [sessions]` rows and loses this table's `[gap]` rows | 00 Shared | SHARED-07 (`:125`), the only one | SHARED-07 |
| `GET /api/admin/data-sources`: the `market_data_intraday` dataset's status and message follow those rows | 14 Admin | ADMIN-02 (`:1119`) first; then ADMIN-11 (`:1128`), ADMIN-12 (`:1129`), ADMIN-13 (`:1130`) | ADMIN-02 |
| the audit's reader of `market_data_intraday` (`scripts/audit_data_freshness.py`) | reaches the site only through the two routes above | the same rows | the same two |

Considered and not declared:

- The Charts API's reader (`stored_intraday_to_eastern`): not changed.
- Readers of `strat_features_levels_*` (DASHBOARD-21, ADMIN-08): not changed. `DERIVED_TS_TABLES` is a delete list that only `--replace-months` uses.
- `POST /api/admin/data-sources/{source_id}/refresh` (ADMIN-06): not changed.
- `lib/eastern_time.py`: three functions and one constant are added; no existing function's result changes.
- The basis check: no route reads it.

So `site_source_notes: [ADMIN-02, SHARED-07]`.

- The implementation PR writes the `(FEAT-DATA-001, ADMIN-02)` row, which does not exist.
- It extends the `(FEAT-DATA-001, SHARED-07)` row that an earlier change left (`:1305`). The note protocol asks only that each declared own row is added or changed and that its cell begins with the current source hash (`scripts/maintenance/doc_source_snapshot.py:157-164`). It does not keep the old prose, so a rewrite would erase the earlier change's note. The row is extended the way three rows of that table already are: the new hash and this change's prose first, then `Earlier:` and the earlier note's prose, unchanged.
- It regenerates `docs/review-evidence/site-source-snapshot.json`.
- What the site shows of this change: the Admin page's Data tab (ADMIN-02), through `GET /api/admin/data-sources`. No solyra page calls `GET /api/health/freshness`: the document's own note says so (`:137`), and solyra `main` 13dfa44 has no caller under `src/` (searched 2026-11-13). SHARED-07 is declared because its Chain row names the changed route, not because a page shows it.
- The deployed-site runs are close-out steps the owner posts on the PR (AGENTS.md, Browser proof).

### Capacity

Volume, velocity and wall-clock per run, and the task timeout each must fit four times over.

| Run | Volume | Velocity | Wall-clock | Timeout and headroom |
|---|---|---|---|---|
| scheduled scan, in the watchdog | 3 reads of about 5,800 rows of two timestamps, about 0.3 MB | 3 queries a run; 12 runs on a weekday | 5.7 ms a query measured on the earlier form (SPY, 5,827 rows, db-query-q6wbd); at most 6 s at 2 s a round trip | job runs 8 to 14 min today; 14 min 6 s is 4.2 times under 3,600 s |
| scheduled scan, in the API | the same | at most once per 5 minutes per instance (`_CACHE_TTL` 300, single flight) and 5 instances: at most 15 queries per 5 minutes | adds at most 6 s to an audit | how long the audit takes inside the API was not measured (#1224 records a probe that timed out at 30 s) |
| on-demand scan, one ticker | at most 143 month reads of 20,000 to 25,000 rows, up to twice that where a month is stored both ways | 1 probe and at most 143 queries | 607 ms a month read (measured for SPY, 25,174 rows, `run_verify_months`): about 1.5 min; 4.8 min at 2 s a query | 12 times under the watchdog's 3,600 s at the worst figure |
| basis check, one ticker's list | the same reads with three more columns | at most 143 queries and 1 daily query | about 1.5 min by the same figure; the daily query was not measured. Twice that when Cloud Run reruns a task that exited non-zero | fetch job, 2Gi, 3,600 s a task: over 12 times |

- Memory. The on-demand scan and the basis check hold one ticker-month at a time. A prototype of the scan over 143 synthetic months of 50,000 rows peaked at 117 MB resident, 113 MB of it imports (local run, 2026-11-13). The watchdog has 512Mi. The implementation's own figure is a `done_when` item. A read of a whole range in one frame would not fit: the resolver alone peaked at 207 MB for 437,000 rows in one frame (local run, 2026-11-13).
- Where a duration comes from after the deploy. The scheduled scan's own seconds are not printed on a passing run (Design B). The numbers that are printed: the on-demand scan's `seconds=N` on its summary line, and each execution's start and completion time from `gcloud run jobs executions list`, which gives the whole watchdog run before and after the deploy.
- Production plans for the final queries are a `done_when` item, read-only through `scripts/db_query_cr.sh`.
- Cost, at Cloud Run's job rates of about $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read for this spec):
  - scheduled scan: about $0.0001 a run, about 3 cents a month over about 270 runs;
  - on-demand scan or basis check: under 1 cent a run.
- No new job and no new schedule. Requests to AlphaVantage do not change in number.

## Implementation plan: size

11 tasks. The single spec had 16; file B holds the other part.

1. `lib/eastern_time.py`: the proof rule, `session_minute_readings` with the schedule passed in, `intraday_month_window`.
2. `lib/eastern_time.py`: `place_stored_rows`.
3. Audit: the scheduled scan, the `CHECKS` key, the rows, the printed report.
4. Audit: `--intraday-gap-since`.
5. The API test of the freshness and admin responses.
6. Basis check: `session_basis_verdicts` and the daily source rule.
7. Basis check: the runner, the lines, the exit codes.
8. Workflow test and the README line.
9. `DERIVED_TS_TABLES` and its test.
10. Site note rows, the snapshot, the generated inventories, the catalog record, PR traceability.
11. PR-body measurements.

No `done_when` item of this file needs file B's code, and none of file B's is repeated here. Each file carries its own delivery items: the unmodified suites, the PR-body measurements, and the product records.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. No step here writes production data. The one object a step puts in the bucket is the month list a read-only check reads (step 2).

### Before the merge

- **Site evidence, the before run.** It is the owner's run of a solyra cloud spec against the deployed site, posted on the PR.
  - The page: the Admin page's Data tab (ADMIN-02). Nothing else on the site shows this change (Site traceability).
  - The cloud spec does not exist. solyra `main` 13dfa44 holds three: `tests/catalysts/earnings-history.cloud.spec.ts`, `tests/playbook/orb-parity.cloud.spec.ts` and `tests/signals/score-explanation.cloud.spec.ts`. A fourth, `tests/charts/replay-bars-table.cloud.spec.ts`, is specified for the replay routes (solyra PR 336, a draft). None opens the Admin page.
  - The one for this change would be `tests/admin/data-sources-session-gaps.cloud.spec.ts`. It is a solyra change under a solyra spec of its own, merged before this implementation PR merges. It is not specified here.
  - Until it exists this run cannot be made, and the PR says so. The API test in the PR (`tests/api/test_health_freshness_session_gaps.py`) is the proof the PR itself carries.

### After the merge (every step waits for the owner's own yes)

1. **Deploy**: `./gcp/deploy.sh freshness-watchdog` and `./gcp/deploy.sh fetchers`.
   - The first puts the scan and `--intraday-gap-since` on the watchdog. The second puts `--verify-basis` and the longer clear list on the fetch job's image; that target rebuilds the image and redeploys every fetcher job as `gcp/deploy.sh` declares it (`deploy_fetchers`, `gcp/deploy.sh:3207`). Neither is a change to that file, and neither starts a write.
   - The API needs no step: the merge starts its staging deploy, so the two routes carry the scan from the merge on. Merging is the owner's yes to that. The scan only reads.
2. **Read-only verification** of what was deployed.
   - The watchdog's next scheduled run. Its output holds the report with its `Overall:` line and no traceback, so `audit_all()` returned with the scan in it. Each `market_data_intraday [sessions]` row it prints is recorded with its `detail:` line and put to the owner. The PR body's five-session counts say which rows to expect.
   - One listing run of the scan on the deployed image, from the oldest of the five settled sessions: `--args="--intraday-gap-since=YYYY-MM-DD"`. It exits 0. Its summary line gives, per ticker, the sessions scanned, which equal the calendar's sessions from that date to the last settled one, and `seconds=N`. This is the positive proof that the deployed scan runs: a scheduled run in which every session is whole prints nothing of its own. If the watchdog's failure issue is open, this run waits: an execution that exits 0 lets the notifier's hourly reconcile close that issue (`gcp/failure_notifier.py:743-810`; run with stubs on 2026-11-13).
   - One run of the basis check over a list of one proven month, `SPY,2026-10`, uploaded as `gs://adept-mountain-474619-d4-trading-data/intraday-lists/verify-basis-a.csv`: `--args="--verify-basis=gs://adept-mountain-474619-d4-trading-data/intraday-lists/verify-basis-a.csv"`. Its summary line is printed. Exit 0 is expected: every row of that month is on a date from `TRUE_UTC_FROM` on, and its sessions read at factor 1.0 on 2026-11-13 (db-query-tvjtp). An exit of 1 is a finding: it is recorded with its BASIS-FAIL lines and put to the owner. Cloud Run runs the task once more first (`--max-retries 1`), and the failure notifier files the failed execution as a `gcp-job-failure` issue. The same reconcile closes that issue once the job's latest execution succeeded; the operator comments on it with this step and the execution id.
   - The watchdog's run time before and after: the start and completion times of its last executions from `gcloud run jobs executions list --job=freshness-watchdog --region=us-east1`. The capacity table expects at most 6 s more.
3. **Site evidence, the after run**: the owner's second run of the same cloud spec, once staging has deployed the merge. It waits for that spec to exist, as the before run does.
4. **The site document**: the SHARED-07 and ADMIN-02 cells of `docs/product/03-SITE-TRACEABILITY.md` are brought to the deployed state on a `docs/` branch afterwards.
5. **Reword CLAUDE.md's workflow item 3** (decision 3), as its own change.
   - The gate calls `CLAUDE.md` a process file (`is_process_file`, `scripts/gate/spec_gate.py:1122-1127`) and gives process files to FEAT-CICD-001 (`:4816-4819`), so a FEAT-DATA-001 PR that edits it is refused. It is not documentation to the gate either (`AGENT_FILES`, `:1359`), so a `docs/` or `chore/` branch cannot carry it.
   - It goes on a `feature/feat-cicd-001-<slug>` or `fix/feat-cicd-001-<slug>` branch with its own approved FEAT-CICD-001 spec and ready plan.
   - The change: item 3 ("Implement Continue-on-Error Strategically", `CLAUDE.md:1810-1813`) says instead that no step or job sets `continue-on-error` to anything but `false`, that `tests/meta/test_workflows_no_continue_on_error.py` holds it, and that a step allowed to fail records the failure in a step output that a later step fails on. Rule 3.7's two lines (`CLAUDE.md:583`, `CLAUDE.md:647`) drop "in fetcher workflows" and "on a fetch / validation step".
   - Until it merges, item 3 permits what the test refuses. The test wins in CI.

File B's runbook starts after steps 1 and 2.

## Decisions the owner can overrule

Decided, and written into the text above:

1. **Two specs in one PR.** This file holds the checks. File B holds the bucket copy and the production runbook. One plan each.
2. **`site_source_notes: [ADMIN-02, SHARED-07]`**, derived by the rule in "Site traceability".
3. **The workflow test bans every `continue-on-error`** other than an explicit `false`. This PR rewords `.github/workflows/README.md`. CLAUDE.md's item 3 is reworded on a FEAT-CICD-001 branch (Close-out, step 5), because the gate refuses that file here.
4. **The basis check measures a session only against a daily row from the daily endpoint** (`TRUE_DAILY_SOURCES`). Any other row is UNMEASURED with its reason.
5. **The schedule is passed into `session_minute_readings`**, fetched with `_calendar(session_schedule, ...)`.
6. **The audit's logging level stays.** The close-out reads the printed report and the on-demand scan's summary line.
7. **File B's runbook can end at exit 0.** The exit rules of Design B and Design C are written for that.

Design calls made in this text:

8. A session whose count depends on the timestamp convention is reported UNDETERMINED and fails. Before the rewrite this is noisy on purpose.
9. An AS-TRADED verdict from rows that are not proven is INFERRED and does not pass.
10. A month fails the basis check on one ADJUSTED session, not two in a row.
11. The old day-presence scan is dropped for `market_data_intraday` only.
12. `inserted_at` is used as proof that a row is a true instant.
13. A failed read in the scheduled scan fails the whole audit: 503 or 500 on the two routes, and a failed watchdog run.
14. `req_ids` holds REQ-CAP-001 and REQ-FRESH-001 beside the two the first draft had.
15. `--verify-basis` exits 3 only when a line rests on a row that is not proven. An exact INCOMPLETE or ODD line is printed and counted and leaves the exit alone. The review's example had INCOMPLETE always change the exit; with sessions the vendor serves thin or not at all, that rule could never reach exit 0.
16. A daily row with no stamp, or with a stamp not in `TRUE_DAILY_SOURCES`, is not measured, even though some such rows came from the daily endpoint.
17. The on-demand scan exits 2 on a calendar failure with or without `--strict`: a run that scanned nothing must not exit 0.

## Risks

- The alarm fires on a real one-off outage. That is its job; the row names the session so it can be refetched or recorded. The PR body shows the last five sessions' counts before the deploy (`done_when`), so the first run's answer is known.
- The freshness response and the admin Data tab turn `stale` when the alarm fires, and answer 503 or 500 when the scan's query fails. The API test pins all three.
- Before file B's rewrite, the on-demand scan and the basis check print UNDETERMINED, INCOMPLETE and INFERRED for sessions that may be whole (every legacy-labelled winter session, for one). How much there is is not measured until file B's step 2.
- Two shapes of unproven rows read OK when something is wrong: the covered gap and the misplaced whole session (Design F). Each can only exist in a month that holds unproven rows, and file B's rewrite covers every such month.
- The proof by insert time rests on no writer having stored a label since 2026-09-28. File B's runbook tests it on production before any write depends on it (its step 2). The scheduled alarm does not depend on it: its window holds only dates from `TRUE_UTC_FROM` on. A hand-run write that bypassed the repo's helpers would not show in that test if it held regular-hours rows only.
- The basis check may measure little. A session is measured only against a daily row stamped by a daily-endpoint writer, and how many daily rows of the three tickers carry such a stamp is not known. The PR-body count answers it before the merge. If many are unstamped, the check prints them UNMEASURED; re-pulling those daily rows is a change to the daily table and is not in this spec.
- Exit 0 from `--verify-basis` does not mean every session was measured. The lines and the summary's counts say which were not, and the run that reads them is file B's step 6.
- A session is first read by the scheduled scan about a day after the nightly that fetched it: the scan keeps the check's settle values (pinned by `tests/audits/test_audit_data_freshness.py:638-639`), and at 2026-11-13 15:00 UTC it stops at 2026-11-11. Changing the settle values is not in this spec.
- A ticker added to the scan later that does not trade every minute would be reported THIN every day. The scan's list is three tickers by design; widening it means changing the THIN rule first.
- A scheduled run in which every session is whole prints nothing for the scan, so a scan that silently stopped running would look the same. The API test and the suite hold the wiring, and the close-out's listing run proves the deployed image once. Nothing proves it each night.
