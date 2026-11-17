---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-CAP-002, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004]
issues: []
canvases: []
site_source_notes: [DASHBOARD-04]
done_when:
  - "tests/lib/test_bar_prints.py passes for the rule on bars written out in the test, each case with its expected rows written in the test and not computed by the code under test: lib.bar_prints.isolated_prints(bars) returns a frame with the columns ts, side, print_kind, observed, reference, bound, scale and excess_bp, one row per flagged (bar, side), and a boolean array of the bars it judged; a low wick 60 bp under the lowest open or close of the bar and of the two bars on each side, with every bar's range 0.05 and every open and close at 100, is flagged with print_kind 'wick', reference, bound (reference minus max(6 x scale, 0.0050 x reference)) and excess_bp as written in the test; a bar whose open is that low and whose close is back at 100 is flagged with print_kind 'open'; the mirror with the close is 'close'; a one-price bar at the low is 'open_and_close'; five consecutive bars whose lows are 60 bp under while every open and close stays at 100 are all five flagged; a level shift, where the bar and every bar after it open and close 60 bp lower, gives no flag; a wick 49 bp under gives no flag; a wick exactly at the bound gives no flag; a wick 60 bp under in a window whose median range is 0.15 (6 x 0.15 = 0.90 above 0.60) gives no flag; the first two and the last two bars of the input are not judged; a NaN open, high, low or close raises ValueError naming its ts; ts not strictly increasing raises ValueError; an empty input returns an empty frame; RULE_VERSION is 'isolated-print-v1' and PARAMS is {'neighbours': 2, 'scale_bars': 61, 'scale_multiple': 6.0, 'floor_bp': 50.0}, so a value changed without a new version fails (on main the module does not exist)"
  - "tests/lib/test_bar_prints.py passes against the premarket spike geometry through one shared measurement: lib.bar_prints.print_geometry(bars) returns, for every input bar in input order, ts, reference_high, excess_high, reference_low and excess_low in price units with no threshold applied, and judged, with NaN references and excesses where a bar is not judged; isolated_prints takes its judged array and every flag's reference from print_geometry, so over the bars of item 1 each flag's reference equals print_geometry's for its ts and side and its excess_bp equals that side's excess divided by the reference times 10,000; and over 300 bars written in the test whose opens and closes all lie strictly inside their own high and low, print_geometry's excess_high and excess_low of each judged bar equal, bar by bar and exactly, the high-side and low-side values lib.level_calibration.wick_excesses returns for that bar (with every value finite it returns the 300 high-side values and then the 300 low-side ones, in bar order: lib/level_calibration.py:310-325 on main a34bbd40, read), so the two rules measure a wick the same way where both apply (on main lib.bar_prints does not exist)"
  - "tests/lib/test_bar_prints.py passes on the ten known sessions, over fixtures in tests/fixtures/bar_prints/ exported read-only through scripts/db_query_cr.sh, each one Eastern day of one ticker plus the 40 stored bars before and after it, with tests/fixtures/bar_prints/sources.json naming for each file the db-query execution id, the SQL, the row count and the file's sha256: the regular-hours flags of each session are exactly SPY 2017-11-28 one (15:16 low), SPY 2018-02-06 22 (all low, 15:13 the first and 15:42 the last), SPY 2018-02-20 one (09:31 low), SPY 2018-04-05 one (11:37 low), SPY 2023-05-25 16 (all low, 15:29 among them), QQQ 2018-02-06 five (15:30, 15:32, 15:39, 15:40 and 15:41 low), QQQ 2021-12-14 one (11:16 low), QQQ 2023-05-25 four (14:15, 14:16, 14:49 and 15:53 low), IWM 2018-02-06 three (15:22, 15:35 and 15:37 low) and IWM 2023-05-25 ten (all high, 13:22 among them), 64 in all, the times written out in the test (on main the function does not exist; these are the prototype's figures, run 2026-11-15 over the bucket copy)"
  - "tests/lib/test_bar_prints.py passes on the clean sample, over fixtures exported the same way: no regular-hours flag for SPY, QQQ or IWM on 2019-06-17, 2020-03-12, 2022-09-13 or 2024-08-05, and no flag at any hour for any of the three on 2019-06-17 (prototype, run 2026-11-15: the same; extended-hours flags on the other three dates are allowed and are not asserted)"
  - "tests/gcp/test_intraday_bar_flags.py passes on half days, over fixtures exported the same way: every bar of SPY 2025-07-03, SPY 2025-12-24, IWM 2018-12-24 and IWM 2025-11-28 from 13:00 to 20:00 ET is labelled session_part 'extended' through lib.eastern_time.session_schedule; none of the four has a regular-hours flag; the flags from 13:00 to 16:00 ET are exactly SPY 2025-07-03 13:01, 13:06, 13:58 and 13:59 (low, 'wick'), SPY 2025-12-24 14:21 (low, 'close', observed 670.292), none on IWM 2018-12-24 (whose after-close low 125.11 sits among bars that open and close from 125.11 to 125.46), and IWM 2025-11-28 13:17 (low, 'close') and 14:50 (low, 'open', observed 233.4998) (on main nothing labels or flags a bar)"
  - "tests/gcp/test_intraday_bar_flags.py passes for the pass, over fixtures written out in the test with their expected rows: flag_months(tickers, months, commit=...) issues per ticker-month one strict read of market_data_intraday bounded by lib.eastern_time.intraday_month_window widened by 7 days on each side, with interval = '1min' in the SQL text and ts, open, high, low, close, volume and inserted_at selected; it writes flags only for bars inside the month window; over a fixture of two consecutive months the union of the two months' flags equals isolated_prints over the two months read whole; a month holding a row that is not proven by lib.eastern_time.proven_true_utc raises UnprovenRows (gcp.bar_recompute.require_proven) and writes nothing for that month; with commit=False it issues no write; with commit=True it issues exactly one write statement per ticker-month; a read raising ConnectionError('connection refused') and one raising KeyError('high') each propagate, with the months already written left written and nothing written for the failing month; one log line per month starting 'bar flags month:' with ticker, month, bars judged and the four counts; each coverage row it writes holds read_start and read_end, the widened window it read, and session_sha256, one sha256 per Eastern date of the rows read; when a date that both the read and the earlier coverage row's session_sha256 hold has a different sha256, or a date the earlier row holds is missing from the read, the line 'BARS-CHANGED' names the ticker, the month, those dates and the earlier checked_at, and with commit=True the flags the write inserted and deleted; a session appended since the earlier pass, with every earlier date unchanged, logs no 'BARS-CHANGED' (on main the module does not exist)"
  - "tests/integration/test_intraday_bar_flags_writes.py passes in the integration-tests CI job on real Postgres: the one write statement of a ticker-month inserts the new flags with detected_at and checked_at set to the pass's time, updates a flag that is still flagged with its new observed, reference, bound, scale, excess_bp, checked_at and run_id and keeps its detected_at, deletes the flags of that ticker, month window and rule_version that are no longer flagged, leaves flags of another rule_version, another ticker and the neighbouring months untouched, and upserts the coverage row, all in that one statement; running the same pass twice over unchanged bars leaves every row as the first run left it except checked_at and run_id; a month with no flag still writes its coverage row with the four counts 0 and bars_judged above 0; and over four consecutive months of one ticker whose flags and coverage flag_months wrote, beside a second ticker's, gcp.database.replace_rows_in_window over market_data_intraday with the third month's window and clear_span_tables=DERIVED_SPAN_TABLES deletes, in the swap's own transaction, the flags and coverage rows of the second, third and fourth months, whose read windows overlap the swapped window, and nothing of the first month or of the second ticker, so that before any rebuild a read of the coverage for the four months finds the first month's row only; a swap whose verify raises leaves all four months' flags and coverage as they were; and flag_months over the second to fourth months afterwards writes their coverage rows again (on main neither table exists)"
  - "tests/gcp/test_intraday_bar_flags.py passes for when the pass runs: fetch_alphavantage_intraday.main() runs flag_months for SPY, QQQ and IWM over export_intraday_bars.nightly_months(market_today()) with commit=True after its fetch loop and before the bars export, only for the nightly arguments (--symbol=ALL --force, no dates, no symbols file, one task) with the database configured; INTRADAY_BAR_FLAGS=off skips it with one log line naming the variable and the export still runs; a run without --force, with --start-date or with --symbols-file flags nothing; a pass raising ConnectionError logs a line starting 'bar flags failed (outage)', one raising KeyError a line starting 'bar flags failed (defect)', the export still runs and main exits 1; the pass reads only after process_symbol has returned for every ticker: over a stored session holding values B, as the 23:00 writer leaves them, a coverage row whose session_sha256 is that of values A, and a stubbed fetch that upserts A again, the pass reads A and logs no 'BARS-CHANGED', while a stubbed fetch that upserts A' logs 'BARS-CHANGED' naming that session; after a pass that succeeds main logs one line starting 'bar flags:' with the months, the flags written and the seconds; --flag-bars-from YYYY-MM judges every month from the one given to the current Eastern month for the three tickers or the one --symbol names, fetches nothing, writes only with --commit, refuses any other ticker, more than one Cloud Run task, the database not configured and a month after the current one, each with exit 1 before any query, and together with --replace-months, --verify-months, --verify-basis or --export-bars-from is a usage error (on main none of this exists)"
  - "tests/gcp/test_intraday_replace_months.py passes with DERIVED_TS_TABLES in gcp/fetchers/fetch_alphavantage_intraday.py holding the fifteen tables it holds on main, a new tuple DERIVED_SPAN_TABLES holding intraday_bar_flags and intraday_bar_flag_coverage passed as clear_span_tables to both swaps of replace_month, the window's and the tail's, the assertions at :875 and :1634 unchanged, added assertions that both swaps receive DERIVED_SPAN_TABLES, and a clear_span_tables name that fails the identifier check refused before the transaction opens, as :881-891 tests for clear_tables (line numbers on main a34bbd40); a committed replace of one month then prints 'REBUILD intraday_bar_flags' and 'REBUILD intraday_bar_flag_coverage' lines where it cleared rows; tests/gcp/test_intraday_replace_levels_tables.py, which pins the clear_tables handed to the swap at fifteen names, passes unmodified (on main neither the keyword nor the tuple exists)"
  - "tests/gcp/test_export_intraday_bars.py passes for the flag counts: each month entry the export writes gains the key flags, read with one strict query per ticker over the run's months from intraday_bar_flag_coverage for lib.bar_prints.RULE_VERSION, holding rule_version, checked_at, bars_judged and the counts regular_high, regular_low, extended_high and extended_low; a month with no coverage row records flags as {'state': 'not_judged'} and never a count of 0; the query raising ConnectionError makes the export raise with the manifest unchanged; the manifest version stays 1 and read_bars returns the key as stored; fake_query answers SQL that names intraday_bar_flag_coverage from a frame the test gives, empty by default; the existing assertions of the file change only at :648 (the expected entry gains the key), :821 (test_io_shape's nightly makes 12 calls, not 9: (6, 3, 12)), :838-839 (the calls gain one coverage read per ticker, after its daily read) and :1617-1618 (the end-to-end run's reads gain the coverage read, after its daily read); added assertions in test_io_shape pin the coverage reads: the nightly's three, one per ticker in the order SPY, QQQ, IWM, each right after that ticker's daily read, each naming intraday_bar_flag_coverage with the ticker, the rule version and the run's first and last month as parameters and a 120 s timeout, and the history's one; the stand-in readers at :874-881, :1583-1585 and :1782-1787, which answer every SQL that does not name market_data_daily with bars, gain an answer for SQL that names intraday_bar_flag_coverage, an empty frame, the second recording it as 'coverage' (line numbers on main a34bbd40, read; the file is the same on 1bce9d9c) (on main entries have no flags key)"
  - "tests/gcp/test_intraday_bar_flags_schema.py passes: gcp/schema.sql creates intraday_bar_flags and intraday_bar_flag_coverage with the columns, CHECK constraints and primary keys of Design 2, idempotently (IF NOT EXISTS), and the CREATE TABLE of market_data_intraday and its partitions and index are byte for byte as on main (on main neither table exists)"
  - "make test passes on the PR head with tests/meta/test_production_writers.py, tests/meta/test_timezone_boundaries.py, tests/fixtures/timezone_boundary_baseline.json, tests/gcp/test_av_intraday_universe.py and tests/gcp/test_intraday_writers_utc.py unmodified, and lib/eastern_time.py, lib/indicators.py, lib/level_calibration.py, gcp/bar_recompute.py, gcp/fetchers/fetch_market_data.py, gcp/deploy.sh and platform/api not in the PR's diff"
  - "The PR body gives: run read-only through scripts/db_query_cr.sh and pasted with its execution id, EXPLAIN (ANALYZE, BUFFERS) of the pass's read for SPY 2023-05 with its margins, written with literals, showing an index scan whose rows equal the rows returned; the shipped isolated_prints run over the bucket copy of the three tickers (gs://<GCS_BUCKET>/intraday-bars/v1/1min/, read through read_bars), giving per ticker the flag rows by session part and side beside this spec's prototype figures, with every difference named bar by bar; and, measured locally with the database stubbed, the seconds, the statement count and the peak resident memory of flag_months over one ticker's 143 synthetic months of 31,711 rows each, 287 statements (one coverage read, 143 reads and 143 writes) and the memory under 512 MB (on main nothing exists; for this spec the read was measured at 27,717 rows from an index scan, 671 buffers, 242 ms, db-query-nbpxc, and the prototype took under 5 s a ticker over the whole history)"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold the (FEAT-DATA-001, DASHBOARD-04) row beginning with the current source hash, with this change's prose first and then 'Earlier:' and the earlier note's prose unchanged, docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: superseded
supersedes: null
---

# market_data_intraday: flag the vendor's misprints in the 1-minute bars of SPY, QQQ and IWM, and never change the bars

## Scope

- The stored 1-minute bars of SPY, QQQ and IWM hold prints that sit far outside the minute they are stamped in. The bars are as the vendor (AlphaVantage) returns them, as traded, and the committed replace of 2026-11-15 kept them.
- This spec adds a flag for such a print: a pure rule in `lib/`, two new tables, a nightly pass inside the 21:00 ET fetch job, a history run, and counts in the bucket manifest.
- It never changes, deletes or replaces a bar, and it writes no value in place of one (CLAUDE.md 3.7).
- It changes no consumer. Features, levels, signals, calibration, the end-of-day resolver and the brief keep reading the bars as stored, misprints included. A second spec decides how each consumer honours the flags.
- One spec, one PR, under FEAT-DATA-001, for SPY, QQQ and IWM only.
- Code references are to `main` 1bce9d9c (2026-11-15). Every production number has its execution beside it. Every database read was made without `--commit`. "Prototype" means a scratch script run in the delivery session on 2026-11-15 over the bucket copy of the bars; it is not committed, and the shipped function must reproduce its figures (`done_when` item 13).

## Capability

- The catalog row is FEAT-DATA-001 (`docs/product/02-FEATURE-CATALOG.md:35`): Data platform, Ingestion, storage, freshness; backend fetcher jobs; status Production but needs remediation; P0; phase 1. Its record (`:513-535`) lists `gcp/fetchers/`, `gcp/schema.sql` and `lib/data_loader.py` under Code.
- The flags describe the stored bars and are written by the job that writes them, so the change is FEAT-DATA-001's. The consumers belong to other capabilities (FEAT-STRAT-001, FEAT-SIGNAL-001, FEAT-REPLAY-001), which is one reason they are a second spec (decision 11).
- Requirements: REQ-DATA-001 (no silent fallback: a bar is never replaced and an unjudged month never reads as clean), REQ-DATA-002 (as-of: a flag depends on later bars, Design 10), REQ-DATA-003 (a derived record carries its rule, configuration and code version), REQ-DATA-004 (regular and extended hours from the one calendar), REQ-CAP-001 and REQ-CAP-002 (capacity, batching, idempotence).
- No canvas is listed: no route and no job is added. Whether the backend architecture canvas depicts the fetch job was not checked.

## Decisions for the owner

**Decided by the owner on 2026-11-15:** flag the bar; never replace or delete it; never fabricate a value.

The rest are written into the text below as recommended. Striking one changes only the sections named.

1. **The rule** (Design 1). Recommended: `lib.bar_prints.isolated_prints`. A bar's high (low) is flagged when it lies beyond every open and close of the two bars on each side, and beyond the bar's own open and close where those are not the extreme itself, by more than both 6 times the local scale and 50 bp. The local scale is the median 1-minute range of the 61 bars centred on the bar. Alternatives, all measured in Problem 4:
   - the wick must pass the neighbours' highs and lows instead of their opens and closes: it flags 2 of the 22 outlying bars of SPY 2018-02-06, and with two neighbours a side it misses QQQ 2018-02-06 entirely;
   - the bar's own open and close always count, as in the premarket spike filter: it misses a misprint that is the minute's first or last trade (SPY 2025-12-24 14:21, IWM 2025-11-28 14:50);
   - the session's range against the vendor's daily bar: the daily bar is not an independent source and has its own errors (Problem 2).
2. **The parameters: 6 times the scale, 50 bp, 61 bars, two neighbours a side, as module constants with a rule version** (Design 1). Recommended. They flag all ten known sessions. The weakest, QQQ 2021-12-14 11:16, clears the multiple at 7.29 and the floor at 64.5 bp. A multiple of 8 misses it, and so does a floor of 75 bp. Constants rather than a policy row: these are not calibrated per ticker, a changed value must re-judge the whole history under a new version rather than start on a date, and a constant changes only through a reviewed PR that states the new counts. Alternative: a row of `level_param_policy`.
3. **The same rule in regular and extended hours** (Design 1). Recommended. Each flag records which part of the session it is in, from `lib.eastern_time.session_schedule`. Extended hours hold 15,996 of the prototype's 16,441 flag rows (Problem 4). Alternatives: regular hours only; or a higher floor after hours, which no measurement here supports.
4. **Storage: two new tables, `intraday_bar_flags` and `intraday_bar_flag_coverage`; `market_data_intraday` unchanged** (Design 2). Recommended. Alternative: a column on `market_data_intraday`. That table has exactly two sanctioned writer modules, pinned by `tests/meta/test_production_writers.py:1383-1386`; a flag column would need a third writer of the bars table or a change to both writers' upserts, and one column cannot hold two sides or two rule versions. The coverage table is what lets a missing flag mean "judged, not flagged" rather than "never judged" (CLAUDE.md 3.7).
5. **The nightly pass runs inside the 21:00 ET fetch job, after the fetch and before the bucket export, over the previous and the current Eastern month** (Design 4). Recommended. That job rewrites exactly those two months every night, so the pass judges what was just written, needs no schedule of its own to keep in step (CLAUDE.md 3.9), and the export that follows can count its flags. Alternative: a separate job on its own schedule after 21:00.
6. **The 23:00 ET daily fetcher's rewrite of the same session is not judged. The next nightly refetches the session before its pass runs, and the pass judges what the refetch left** (Design 5). Recommended. `BARS-CHANGED` names a session whose bars, after that refetch, differ from those the last pass judged: a vendor revision, or a row or value the refetch did not overwrite. It cannot see a 23:00 value the refetch overwrote, and it says nothing about appended sessions. Alternatives: the daily fetcher re-judges too. That job runs with `--max-retries 2` over about 800 tickers (`gcp/deploy.sh:2157-2160`, read), so a failed flag pass there would refetch everything twice. Or the nightly reads the two months before its fetch and compares them with what the last pass judged: that sees the 23:00 values, for 6 more reads of up to 31,711 rows a night, and it changes no flag, since the refetch replaces those values before the pass reads.
7. **The history run is `--flag-bars-from YYYY-MM` on the fetch job, a dry run unless `--commit`, one execution per ticker** (Design 6). Recommended.
8. **A replace clears, in its own transaction, the flags and coverage of every month whose read it rewrites: the replaced month and the month on each side. The rebuild is the history command, run afterwards, over the same months** (Design 7). Recommended. Re-judging inside the replace is not: its executions ran 53 to 58 minutes a ticker against a 3,600 s timeout (PR #1943 comment 6884444352, read).
9. **The bucket manifest counts the flags per month, read from the tables; a month never judged is recorded as `not_judged`, never as 0** (Design 8). Recommended.
10. **SPY, QQQ and IWM only.** Recommended: they are the tickers whose every stored bar is a proven instant (`freshness-watchdog-dq7hh`, read from PR #1943 comment 6888913445) and the ones the bucket copy holds.
11. **No consumer honours the flags in this spec. A second spec, written after this one is approved, decides it for each consumer** (Design 10). Recommended, as one FEAT-DATA-001 spec on the recompute spec's precedent (one spec for a cleanup that crosses capabilities). Alternative: one spec per consumer's capability.

## Problem

### 1. What was found on 2026-11-15

- A read-only scan compared each session's regular-hours 1-minute extremes with the vendor's daily bar (`alphavantage_daily`, 2016-05 on, about 2,500 sessions a ticker) at a 30 bp tolerance (db-query-dxhqh, 206.8 s, run). 27 sessions matched.
  - 17 are half days. The scan used a fixed 09:30 to 16:00 ET window, which took in prints after the 13:00 ET close. The manifest's basis check uses the exchange schedule and does not do this.
  - 10 are misprints in regular hours: SPY 2017-11-28, 2018-02-06, 2018-02-20, 2018-04-05 and 2023-05-25; QQQ 2018-02-06, 2021-12-14 and 2023-05-25; IWM 2018-02-06 and 2023-05-25.
- The worst is SPY 2023-05-25 15:29 ET: open 415.36, close 415.29, low 393.84. The 15:28 low is 415.03 and the 15:30 low 415.11 (PR #1943 comment 6896723478, and run again on the bucket copy for this spec).
- PR #1943 comment 6891791378 said two dates hit all three tickers within a minute. Its correction, 6896723478, says that is wrong for 2023-05-25 (IWM 13:22, SPY 15:29, QQQ 15:53) and that on 2018-02-06 the outlying bars cluster in one afternoon window.
- In those sessions the flagged bar's open and close and the bars either side sit at the normal price, and only the wick is out. The correction states the limit: the evidence says the prints do not represent where the market traded; it does not prove they never printed. No second source with trade-condition flags is connected.

### 2. The daily bar cannot decide

- The vendor's daily table is not independent of its 1-minute feed and has its own errors. SPY 2022-10-17: daily low 357.281, while no 1-minute bar of the day, at any hour, traded below 358.88 (db-query-v2kqd, run).
- The closing print can sit in the daily bar and in no regular-hours bar. SPY 2025-04-09: daily high 548.62; highest regular-hours 1-minute high 546.33 (db-query-v2kqd, run). In the bucket copy, 548.62 is the high of the 16:00 bar (volume 17,576,624), and the same price recurs as the high or the open of 14 later bars up to 20:00 ET (prototype, run).
- The daily extremes differ from the 1-minute bars on more sessions than the misprints: the daily high above every regular-hours high by more than 30 bp on SPY 22, QQQ 10 and IWM 8 sessions, and the daily low below every regular-hours low on SPY 34, QQQ 18 and IWM 13 (db-query-hbb74, run).
- So the daily range may corroborate a flag, and it must not decide one.

### 3. What the manifest's ODD count is

- The bucket export already counts sessions whose regular-hours range disagrees with the daily bar by more than 3 bp in a way no adjustment explains: verdict ODD (`session_basis_verdicts`, `gcp/fetchers/fetch_alphavantage_intraday.py:1189-1279`, read). The manifests of 2026-11-15 06:50Z count SPY 134, QQQ 56 and IWM 52 such sessions (read).
- All ten known sessions are ODD. But ODD is not a misprint count. Set beside the sessions in which the recommended rule flags a regular-hours bar (prototype, run):

| Ticker | ODD sessions | Sessions with a regular-hours flag | Both | ODD, no flag | Flag, not ODD |
|---|---|---|---|---|---|
| SPY | 134 | 78 | 7 | 127 | 71 |
| QQQ | 56 | 83 | 5 | 51 | 78 |
| IWM | 52 | 58 | 5 | 47 | 53 |

- A misprint that stays inside the day's range moves neither ratio, and a closing print or a daily-table error makes a session ODD with no misprint in it.

### 4. What a rule over the bar's neighbourhood finds

Run on 2026-11-15 by the prototype over the bucket copy of all three tickers: 6,879,159 bars, 2015-01-02 to 2026-11-13 (143 months each), read through `gcp.fetchers.export_intraday_bars.read_bars` with every file's sha256 checked. The table holds the same rows: SPY 2,507,878, QQQ 2,342,615, IWM 2,028,666, the same first and last `ts`, and no row inserted after the export (db-query-nbpxc, run). A value rewritten in place since the export would not show in that count, since an upsert keeps `inserted_at`. Neither scheduled writer of these bars runs between Saturday 21:00 ET and Monday 21:00 ET outside the 1st of a month (`gcp/deploy.sh:4622`, `:4723`, `:4741`, read); whether anything else rewrote a value was not checked.

Flag rows of the recommended rule (decisions 1 to 3):

| Ticker | All | Regular hours (high / low) | Extended hours (high / low) | Sessions with a regular-hours flag | Sessions with any flag |
|---|---|---|---|---|---|
| SPY | 6,546 | 178 (79 / 99) | 6,368 (2,359 / 4,009) | 78 | 1,426 |
| QQQ | 6,834 | 126 (55 / 71) | 6,708 (2,583 / 4,125) | 83 | 1,496 |
| IWM | 3,061 | 141 (98 / 43) | 2,920 (1,325 / 1,595) | 58 | 1,155 |

- 16,441 rows, 0.24% of the bars. By the price at the extreme: SPY 5,781 wicks, 389 opens, 313 closes, 63 bars of one price; QQQ 5,915, 448, 410, 61; IWM 2,000, 527, 342, 192.
- **All ten known sessions are flagged**, with 64 regular-hours flags among them (`done_when` item 3 lists them).
- **Misprints come in clusters and repeat.** SPY 2018-02-06 holds 22 flagged bars from 15:13 to 15:42, most of them consecutive. On SPY 2023-05-25 the low 411.032 recurs in 26 bars from 09:43 to 16:39, below the vendor's own daily low of 412.41. QQQ 331.606 recurs 3 times that day; IWM's high 175.412 recurs 8 times. On SPY 2025-04-23, 41 bars from 11:32 to 15:54 carry highs of 541.58 to 545.13 while their own opens and closes sit from 534.74 to 538.86; the day's highest regular-hours high, 545.43, was at 10:00.
- **The extremes rule under-flags clusters.** With the neighbours' highs and lows as the reference instead of their opens and closes, one neighbour a side flags 2 of SPY 2018-02-06's 22 bars (15:13 and 15:42, the two ends of the cluster) and 2 of QQQ 2023-05-25's 4 (14:49 and 15:53; it misses the consecutive pair 14:15 and 14:16). Two neighbours a side flag no bar of QQQ 2018-02-06: 9 of the 10 sessions.
- **A misprint can be the minute's first or last trade.** SPY 2025-12-24 14:21: open 690.1118, close 670.292 equal to the low, the bars around it at 690. IWM 2025-11-28 14:50: open 233.4998 equal to the low, close 248.63. A rule that always counts the bar's own open and close measures no wick there. 2,745 of the 16,441 flag rows are of this kind (SPY 765, QQQ 919, IWM 1,061), 4 of them in regular hours (QQQ 2015-12-01 13:58 open, volume 1,507,035; QQQ 2015-12-03 14:30 close, volume 1,015,904; QQQ 2016-04-14 09:30 open 110.00; SPY 2025-05-19 11:55 open).
- **Extended hours hold 97% of the rows**, mostly from 08:00 to 08:59 and from 16:00 to 17:59 ET (SPY 1,483 and 4,185; QQQ 2,388 and 3,476; IWM 1,195 and 1,295), and they grow from 2023 (SPY 557 in 2023, 981 in 2024, 2,082 in 2025, 1,541 to 2026-11-13). What they are was not checked. Some are large: QQQ's close print of 2015-12-03 14:30 carried 1,015,904 shares at 114.4411 among bodies at 112.1, which is how a late-reported block at an earlier price would look. The SPY 2025-04-09 closing price reprinted after hours (Problem 2) is flagged twice, at 17:49 and 18:30.
- **Regular-hours flags by year** (SPY / QQQ / IWM): 2015 3 / 11 / 2, 2016 7 / 2 / 1, 2017 1 / 2 / 1, 2018 27 / 7 / 6, 2019 2 / 0 / 1, 2020 4 / 3 / 10, 2021 0 / 1 / 7, 2022 4 / 1 / 0, 2023 29 / 8 / 14, 2024 10 / 23 / 14, 2025 82 / 59 / 82, 2026 9 / 9 / 3.
- **Violent sessions give no regular-hours flag**: 2020-03-12, 2022-09-13 and 2024-08-05, for all three tickers. 2019-06-17 has no flag at any hour for any of the three. The scale tracks the session: on SPY 2018-02-06 it is 0.62 around 15:30, against 0.065 on SPY 2017-11-28.
- **Half days**: no regular-hours flag on any of the 17. After the 13:00 close the rule flags what stands apart from its neighbours and not what the market traded together. SPY 2025-07-03 has 581.808 and 582.522 lows at 13:58 and 13:59 among bodies at 624.9: both flagged. IWM 2018-12-24's after-close low 125.11 sits among bars that open and close from 125.11 to 125.46: not flagged.
- **Sensitivity to the scale window**: run on the rule before its open and close refinement (which adds 4 regular-hours rows), a scale over 31 or 121 bars instead of 61 still flags all ten known sessions, and the regular-hours flagged bars move by at most 30: SPY 177, 147 and 176; QQQ 123, 122 and 130; IWM 141, 132 and 165, at 61, 31 and 121 bars.

### 5. What nothing here can say

Whether any flagged print traded. The flag says that a print does not represent the minute it is stamped in, measured against the bars around it. It does not say the print is false. Some flagged prints are plainly real trades at another price, such as the closing price reprinted after hours.

## Non-goals

- No bar is changed, deleted, replaced or interpolated. `market_data_intraday`, its writers and its readers are not edited, except the fetch job's `main()`, which calls the pass, its `replace_month`, which hands the new tuple `DERIVED_SPAN_TABLES` to its two swaps, and `gcp.database.replace_rows_in_window`, which gains the keyword `clear_span_tables` (Design 7). `DERIVED_TS_TABLES` keeps its fifteen names.
- No consumer reads the flags. No feature, level, signal, calibration, exit, brief, chart or route changes. That is decision 11's second spec.
- No change to the premarket print filter (`lib/indicators.py:661-713`, FEAT-STRAT-001) or to its calibration. It keeps filtering the premarket fields as it does.
- No ticker other than SPY, QQQ and IWM. The pass refuses any other before a query.
- No production write from the implementation PR. Every production step is in Close-out and waits for the owner's own yes.
- No change to `gcp/deploy.sh`, to a schedule, or to a job's memory, timeout or retries. The pass runs inside the existing job, inside its existing limits (Capacity).
- No second data source, and no attempt to say whether a print traded.
- No change to `gcp/fetchers/fetch_market_data.py` (decision 6).
- No edit of `CLAUDE.md`, of the approved bucket-copy spec or of the recompute spec.

## Approaches considered

For the rule:

1. The neighbourhood of opens and closes, with the bar's own open and close left out where they are the extreme, and a scale from the local median range (chosen). It catches wicks, clusters of wicks with normal bodies, and bad first and last prints; Problem 4 has the counts.
2. The neighbours' highs and lows as the reference: misses most of a cluster (Problem 4).
3. The premarket filter's geometry as it stands, with the bar's own body always in the reference (`lib/indicators.py:702-707`): misses bad opens and closes. Its scale is the prior session's ATR times a calibrated quantile, a daily scale, so it cannot follow the minute. The chosen rule keeps that filter's geometry where both apply, and `done_when` item 2 tests that they agree there.
4. The session's range against the daily bar: decides by a source that is not independent and that has its own errors (Problem 2).
5. A repeated identical price as its own signal (SPY 411.032 in 26 bars): it would catch prints within 50 bp of the market, but it needs its own rule and evidence. Not here.
6. A second vendor with trade-condition codes: none is connected.

For storage:

1. Two new tables, flags and coverage (chosen).
2. A column or two on `market_data_intraday` (decision 4 says why not).
3. Flags in the bucket only: the bucket is never a source for the tree (CLAUDE.md 3.7.1, `gcp/fetchers/export_intraday_bars.py:11-14`, read), so a consumer could not read them.

For the nightly pass:

1. Inside the 21:00 ET fetch job, after its fetch (chosen, decision 5).
2. A separate job on its own schedule: a second schedule to keep after the fetch, the drift CLAUDE.md 3.9 describes.
3. Inside each consumer: every consumer would judge for itself, and they would disagree.

## Design

### 1. The rule: `lib/bar_prints.py`, `isolated_prints`

A new module, because the rule is the one contract the nightly pass, the history run and the tests share, and neither the fetch module (a writer of bars) nor `lib/indicators.py` (indicators and the premarket filter) is its home. Pure: pandas and numpy only, no I/O, no clock.

```python
RULE_VERSION = "isolated-print-v1"
PARAMS = {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0, "floor_bp": 50.0}

def print_geometry(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per input bar, in input order: ts, reference_high, excess_high,
    reference_low, excess_low (price units, no threshold) and judged.
    NaN references and excesses where a bar is not judged."""

def isolated_prints(bars: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """bars: one ticker's stored 1-minute bars, ts ascending, with open, high, low, close.
    Returns (flags, judged)."""
```

`print_geometry` is the one place the wick is measured. `isolated_prints` calls it, then applies the scale and the threshold: its judged array is `print_geometry`'s, each flag's reference is `print_geometry`'s for that bar and side, and its `excess_bp` is that side's excess over the reference. The agreement test reads `print_geometry` directly, for every judged bar, flagged or not (`done_when` item 2).

For each bar `i` with open `o`, high `h`, low `l`, close `c`:

- **Reference, low side**: the lowest of the open and close of the bars `i-2`, `i-1`, `i+1` and `i+2`, together with whichever of the bar's own `o` and `c` is above `l`. **High side**: the highest of the same four bars' opens and closes, together with whichever of `o` and `c` is below `h`. The bar's own open or close is left out only when it is the extreme itself. Then a misprint that is the minute's first or last trade is measured against the trade after it or before it, while a level that the bar and the two after it all hold is protected.
- **Scale**: the median of `high - low` over the 61 stored bars centred on `i` (30 on each side; fewer at the two ends of the input).
- **Threshold**: `max(6 x scale, 0.0050 x reference)`. **Bound**: reference minus the threshold (low), plus it (high).
- **Flagged** when `l < bound` (low) or `h > bound` (high), strictly. Both sides can be flagged on one bar (SPY 152, QQQ 120 and IWM 18 bars in the prototype).
- **print_kind**: `open_and_close` when both `o` and `c` equal the extreme, `open` or `close` when one does, `wick` otherwise.
- **Excess**, in price units, `print_geometry`'s `excess_low` and `excess_high`: `reference - l` (low), `h - reference` (high). **excess_bp**: the excess over the reference, times 10,000.
- **Judged**: a bar with two stored bars on each side in the input. The pass reads margins (Design 3), so the bars left unjudged are the first two of the history and the last two before the live edge, which the next night judges.
- **Bad input**: an empty frame returns no flag. `ts` not strictly increasing, or a NaN in `open`, `high`, `low` or `close`, raises `ValueError` naming the `ts`. None of the three tickers holds a NaN price today (prototype, run). A NaN is a vendor gap; the rule does not guess around it.
- Columns of `flags`: `ts`, `side` (`high` or `low`), `print_kind`, `observed` (the stored high or low), `reference`, `bound`, `scale`, `excess_bp`.
- The parameters are module constants. Any change is a new `RULE_VERSION`, and a test pins the version to `PARAMS` (`done_when` item 1). Each coverage row stores `PARAMS` (Design 2).
- The session part is not part of the rule. The pass adds it (Design 3).

What it agrees with: on a bar whose open and close are both strictly inside its high and low, `print_geometry`'s `excess_high` is `h - max(body top, the two bars each side's highest body top)`, which is `min(h - body top, h - the two bars each side's highest body top)`, what `lib.level_calibration.wick_excesses` measures for the premarket spike filter (`lib/level_calibration.py:310-325` on main a34bbd40, read); the low side mirrors it. `wick_excesses` returns every finite excess, flagged or not, while `isolated_prints` returns rows only for flagged sides, so the test compares `print_geometry` with `wick_excesses` bar by bar over the judged bars (`done_when` item 2). The two rules differ in the scale and in the bar whose open or close is the extreme.

### 2. Storage (`gcp/schema.sql`, applied by the owner, Close-out step 1)

```sql
CREATE TABLE IF NOT EXISTS intraday_bar_flags (
    ticker        VARCHAR(10)      NOT NULL,
    interval      VARCHAR(5)       NOT NULL DEFAULT '1min',
    ts            TIMESTAMPTZ      NOT NULL,   -- the bar's key in market_data_intraday
    side          VARCHAR(4)       NOT NULL CHECK (side IN ('high', 'low')),
    rule_version  VARCHAR(32)      NOT NULL,
    print_kind    VARCHAR(14)      NOT NULL
        CHECK (print_kind IN ('wick', 'open', 'close', 'open_and_close')),
    session_part  VARCHAR(8)       NOT NULL CHECK (session_part IN ('regular', 'extended')),
    observed      DOUBLE PRECISION NOT NULL,   -- the stored high or low
    reference     DOUBLE PRECISION NOT NULL,
    bound         DOUBLE PRECISION NOT NULL,
    scale         DOUBLE PRECISION NOT NULL,
    excess_bp     DOUBLE PRECISION NOT NULL,
    read_start    TIMESTAMPTZ      NOT NULL,   -- the window the pass read for the month
    read_end      TIMESTAMPTZ      NOT NULL,   -- (Design 3, step 1); a replace overlapping it clears the row
    detected_at   TIMESTAMPTZ      NOT NULL,   -- the first pass that flagged it
    checked_at    TIMESTAMPTZ      NOT NULL,   -- the last pass that flagged it
    run_id        TEXT             NOT NULL,
    CHECK (read_start < read_end),
    PRIMARY KEY (ticker, interval, ts, side, rule_version)
);

CREATE TABLE IF NOT EXISTS intraday_bar_flag_coverage (
    ticker              VARCHAR(10)  NOT NULL,
    interval            VARCHAR(5)   NOT NULL DEFAULT '1min',
    -- The month window's first instant (lib.eastern_time.intraday_month_window).
    ts                  TIMESTAMPTZ  NOT NULL,
    rule_version        VARCHAR(32)  NOT NULL,
    month               DATE         NOT NULL,   -- the first of the Eastern month
    read_start          TIMESTAMPTZ  NOT NULL,   -- the window the pass read, margins included;
    read_end            TIMESTAMPTZ  NOT NULL,   -- a replace overlapping it clears the row (Design 7)
    params              JSONB        NOT NULL,
    bars_in_month       INTEGER      NOT NULL,
    bars_judged         INTEGER      NOT NULL,
    first_judged_ts     TIMESTAMPTZ,
    last_judged_ts      TIMESTAMPTZ,
    flags_regular_high  INTEGER      NOT NULL,
    flags_regular_low   INTEGER      NOT NULL,
    flags_extended_high INTEGER      NOT NULL,
    flags_extended_low  INTEGER      NOT NULL,
    bars_basis          JSONB        NOT NULL,   -- gcp.bar_recompute.bars_basis of the rows read
    session_sha256      JSONB        NOT NULL,   -- Eastern date -> sha256 of that date's rows read
    code_version        JSONB        NOT NULL,   -- gcp.bar_recompute.code_version()
    run_id              TEXT         NOT NULL,
    checked_at          TIMESTAMPTZ  NOT NULL,
    CHECK ((bars_judged = 0) = (first_judged_ts IS NULL)),
    CHECK (read_start < read_end),
    PRIMARY KEY (ticker, interval, ts, rule_version)
);
```

- **What a reader can tell.** A coverage row for (ticker, month, rule version) says the month was judged at `checked_at` over the bars its `bars_basis` hashes. A bar of that month inside `first_judged_ts` to `last_judged_ts` with no flag row was judged and not flagged. No coverage row means not judged: never "clean".
- `bars_basis` is `gcp.bar_recompute.bars_basis` over every row the pass read for the month, margins included, since the flags rest on all of them (`gcp/bar_recompute.py:202-230`, read: rows, first and last `ts`, earliest and latest `inserted_at`, and a sha256 over `ts`, open, high, low, close and volume).
- `session_sha256` maps each Eastern date of the rows read (`lib.eastern_time.market_date`) to the `sha256` of `gcp.bar_recompute.bars_basis` over that date's rows, about 32 dates a month. It is what lets the next pass tell a session whose bars changed from one appended since (Design 3, step 4). Every pass of a month reads the same window, so a date that a margin's edge cuts is compared with the same cut. The two digests took 0.21 s each over a synthetic month of 31,711 rows (run locally, 2026-11-16).
- `read_start` and `read_end`, on both tables, are the window the pass read for the month: `[month start - 7 days, month end + 7 days)`. Every flag and the coverage row of a month rest on bars inside it, so a replace that rewrites any bar inside it clears them (Design 7).
- `run_id` is `gcp.bar_recompute.run_id()`: `CLOUD_RUN_EXECUTION` in a job, else `local-<UTC>` (`:85-94`, read). `code_version` is `gcp.bar_recompute.code_version()` (`:97-112`, read).
- No row of `market_data_intraday` is read by a foreign key and none is written. `market_data_intraday`'s `CREATE TABLE`, partitions and index are unchanged (`gcp/schema.sql:140-168`).
- Neither table name contains `market_data_intraday`, so the two-writer guard's name pattern does not see them (`tests/meta/test_production_writers.py:1590-1600`, read). The new module writes no bar, so the guard's list does not change.

### 3. The pass: `gcp/fetchers/intraday_bar_flags.py`, `flag_months`

A new module beside `export_intraday_bars.py`, which is read-only by design (`:7-8`, read) and so is not the home of a writer.

```python
FLAG_TICKERS = ("SPY", "QQQ", "IWM")
def flag_months(tickers, months, *, commit: bool, now_utc=None) -> dict:
    """Judge each (ticker, month); with commit, write its flags and coverage.
    Returns {'months', 'flags', 'changed', 'seconds'}."""
```

Per ticker-month, in month order:

1. **Read**, one strict query through `gcp.database.query_to_dataframe_strict`:
   `SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`,
   with `[start, end)` the month window of `lib.eastern_time.intraday_month_window` widened by 7 days on each side.
   - 7 days: the longest gap between two stored bars of the three tickers is 3 days 12 hours, and every 7-day margin before or after a month start holds at least 1,714 bars (prototype, run). So every bar of the month has its two neighbours and its 30 scale bars on each side, except at the live edge and at the first bar of the history.
   - The read's plan is an index scan of the ticker's partition key whose rows equal the rows returned: SPY 2023-05 with its margins, 27,717 rows, 671 buffers read, 242 ms (db-query-nbpxc, run, selecting the same columns less `volume`).
2. **Proof**: `gcp.bar_recompute.require_proven(ts, inserted_at)`. A month holding a row that is not a proven instant raises `UnprovenRows`, and nothing is written for it. Every stored row of the three tickers is proven today (`freshness-watchdog-dq7hh`), so this cannot fire unless a writer regresses.
3. **Judge**: `isolated_prints` over the whole read. Keep the flags whose `ts` lies in the month window. Label each `regular` when `ts` lies in `[market_open, market_close)` of its Eastern date's session from `lib.eastern_time.session_schedule`, else `extended`; half days and holidays come from the calendar (REQ-DATA-004).
4. **Compare**: against the coverage rows of the rule version, read once per ticker before its first month with one strict query over the run's months. When a date that both the read and the coverage row's `session_sha256` hold has a different sha256, or a date the coverage row holds is missing from the read, log `BARS-CHANGED <ticker> <month> sessions=<dates> since=<checked_at>`; with `commit`, the line also gives the flags the write inserted and deleted, from the statement's own result (step 5), so no flag is read back. A date only the read holds was appended since the last pass and is not a change. The comparison sees what the last pass judged against what this pass reads, both after a nightly's refetch: it does not see a value another writer wrote in between and the refetch overwrote (Design 5).
5. **Write**, with `commit` only: one statement, so the month is replaced atomically and a run that stops leaves each month either as it was or wholly rewritten:
   - a data-modifying CTE that deletes the flags of (ticker, interval, rule version) inside the month window whose (`ts`, `side`) is not in the new set;
   - an `INSERT ... ON CONFLICT (ticker, interval, ts, side, rule_version) DO UPDATE` of the new set, which keeps `detected_at` and sets every other column, `read_start` and `read_end` included;
   - an `INSERT ... ON CONFLICT DO UPDATE` of the coverage row;
   - and it returns the counts of flags deleted, inserted and updated.
   A month with no flag runs the same statement with an empty set: stale flags go and the coverage row says 0.
6. **Log** one line: `bar flags month: SPY 2026-10 judged=20412 regular_high=0 regular_low=1 extended_high=7 extended_low=12 (3/6)`.

- One ticker-month in memory at a time: at most 31,711 rows (prototype, run).
- Nothing is caught. A failed read or write raises with its own exception, and the months already written stay written: the pass is idempotent, so a rerun converges.
- A ticker outside `FLAG_TICKERS` raises `ValueError` before any query.
- New code changes zone only through `lib/eastern_time.py` (`tests/meta/test_timezone_boundaries.py` unmodified).

### 4. The nightly pass (decision 5)

In `fetch_alphavantage_intraday.main()`, inside the block that already gates the export on the nightly's own arguments (`--symbol=ALL --force`, no dates, no symbols file, one task; `gcp/fetchers/fetch_alphavantage_intraday.py:1685-1708`, read):

- after the fetch loop, `flag_months(FLAG_TICKERS, nightly_months(market_today()), commit=True)`, then the export as today. `process_symbol` refetches every month of its range and upserts every bar the vendor returns, unconditionally (`gcp/fetchers/fetch_alphavantage_intraday.py:265`, `:299-334` on main a34bbd40, read), so the pass reads every bar the vendor returned that night as the vendor returned it, whatever another writer had written at its key (Design 5);
- `INTRADAY_BAR_FLAGS=off` skips the pass with one log line, as `INTRADAY_BARS_EXPORT=off` skips the export;
- a pass that raises is logged as `bar flags failed (outage)` or `(defect)` by `lib.infra_errors.is_infrastructure_error`, as the export's failure is; the export still runs, and `main()` exits 1. A failed execution files or comments on the job's failure issue, as any failed run of the job does;
- after a pass that succeeds, one line: `bar flags: 6 months, 41 flags, 2 changed, 9.8 s`.

A ticker that failed to fetch is still judged: its stored bars are what they are. The job's `--max-retries 1` (`gcp/deploy.sh:2217`, read) reruns the whole execution on exit 1; the pass is idempotent, so a retry converges.

### 5. The 23:00 ET daily fetcher (decision 6)

- `fetch-market-data` runs at 23:00 ET Monday to Friday (`gcp/deploy.sh:4622`, read) and upserts the session's 1-minute bars of its tickers, the three included, through `write_intraday_to_sql` (`gcp/fetchers/fetch_market_data.py:618-642`, read).
- If those values differ from what the 21:00 nightly wrote, the session's flags describe the 21:00 values until the next nightly pass, at most 22 hours later on a weekday (Saturday's nightly covers Friday).
- An upsert keeps a row's `inserted_at`, so nothing in the bars table shows such a rewrite.
- The next nightly does not judge the 23:00 values either. Its fetch loop refetches both months and upserts every bar the vendor returns before the pass runs (Design 4), so a 23:00 value at a key the vendor still returns is overwritten unread, and the pass judges the vendor's values again. `BARS-CHANGED` therefore does not count the 23:00 rewrites: a session the 23:00 writer changed from A to B and the refetch set back to A reads as unchanged. What it does name is a session whose bars, after the refetch, differ from those the last pass judged: a value the vendor revised between two nights, or a row or value the refetch did not overwrite. A session appended since the last pass is not counted (Design 3, step 4). `done_when` item 15 tests this ordering.
- Whether the 23:00 writes ever differ from the 21:00 ones was not measured. Measuring it needs a read of the two months before the nightly's fetch, 6 more reads a night (decision 6). This spec does not add it: it would change no flag, since the refetch replaces those values before the pass reads.
- Under the alternative (the daily fetcher re-judges too), a failed flag pass there makes the 23:00 job exit 1, and its two retries refetch every ticker (`gcp/deploy.sh:2159`, read).

### 6. The history run (decision 7)

```
python -m gcp.fetchers.fetch_alphavantage_intraday --flag-bars-from 2015-01 --symbol SPY [--commit]
```

- It mirrors `--export-bars-from` (`:1467-1511`, read). It judges every month from the one given to the current Eastern month, for the three tickers (`--symbol ALL`) or the one named. It fetches nothing and needs no API key.
- Without `--commit` it writes nothing and logs the per-month lines and a summary.
- It refuses, with exit 1 before any query: more than one Cloud Run task, a ticker outside the three, the database not configured, and a month after the current one. It cannot be combined with `--replace-months`, `--verify-months`, `--verify-basis` or `--export-bars-from`.
- One execution per ticker (Capacity).

### 7. A replace clears the flags (decision 8)

- `replace_rows_in_window` clears each of its `clear_tables` by `ts` inside the swapped window only (`gcp/database.py:696-705` on main a34bbd40, read: `ts >= :w_start AND ts < :w_end`). That is not enough for the flags. A flag of May's last bars rests on June's first bars, as neighbours and as scale bars, and May's coverage row rests on June's first 7 days through its margin. A `ts` clear of June would leave May's flags and May's coverage row in place, and May would read as judged over bars it no longer holds. The same holds for June's first bars after a replace of May.
- So `replace_rows_in_window` gains one keyword, `clear_span_tables`: tables derived from the swapped table whose rows record, in `read_start` and `read_end`, the span of source rows they were computed from. In the swap's own transaction, after the `clear_tables` deletes, it deletes their rows of the key's `clear_key` columns whose `[read_start, read_end)` overlaps the swapped window, and counts them in `cleared` with the others. A name that fails the identifier check is refused before the transaction opens, as for `clear_tables`; a table that does not exist is skipped, as for `clear_tables`.
- A new tuple `DERIVED_SPAN_TABLES = ("intraday_bar_flags", "intraday_bar_flag_coverage")` beside `DERIVED_TS_TABLES` (`gcp/fetchers/fetch_alphavantage_intraday.py:484-491`, read) is handed as `clear_span_tables` to both swaps of `replace_month`, the window's and the tail's (`:898-905` and `:923-928` on main a34bbd40, read). `DERIVED_TS_TABLES` keeps its fifteen names: `tests/gcp/test_intraday_replace_levels_tables.py` pins the `clear_tables` a swap receives at fifteen (read), and a `ts` clear of the flags would add nothing to the span clear.
- A month's read reaches 7 days into the month on each side, so a replace of month M clears the flags and coverage of M-1, M and M+1, and of no other month; a tail swap past M's window end clears M and M+1. The integration test checks that state before any rebuild (`done_when` item 14).
- So after a replace those months read "not judged", never as judged over bars they no longer hold. The run prints `REBUILD intraday_bar_flags rows_cleared=N` and the same for coverage (`:1064-1068`, read).
- Cost: two more `DELETE` statements in each swap's transaction, each over one ticker's rows (at most 6,834 flags and 143 coverage rows a ticker, by the prototype's counts), reached through the primary key's leading column. No index is added. Not measured.
- The rebuild is `--flag-bars-from` over the replaced months and one month on each side, the months the replace cleared. It runs after the replace, not inside it (decision 8).

### 8. The counts in the bucket manifest (decision 9)

- In `export_window` (`gcp/fetchers/export_intraday_bars.py:477-567`, read), one more strict read per ticker over the run's months, right after that ticker's daily read and with the same 120 s timeout: the coverage rows of `RULE_VERSION`. A nightly then makes 12 queries instead of 9 (`done_when` item 17). Each month entry gains:
  `"flags": {"rule_version": "isolated-print-v1", "checked_at": "...", "bars_judged": 20412, "regular_high": 0, "regular_low": 1, "extended_high": 7, "extended_low": 12}`,
  or `"flags": {"state": "not_judged"}` when the month has no coverage row. Never a 0 for a month that was not judged.
- The counts come from the coverage row, which the pass wrote in the same statement as the flags it counts.
- The manifest stays version 1. `read_bars` returns entries as stored, so a reader that does not know the key is unaffected (`:577-647`, read). Months not re-exported since the change keep no `flags` key until `--export-bars-from` writes them again (Close-out step 6).
- `lib.bar_prints` is imported inside `export_window`. The module's top-level imports stay the standard library and pandas, so `read_bars` still runs where `lib` cannot be imported (`gcp/fetchers/export_intraday_bars.py:16-18`, read).
- The bucket stays a copy for analysis. No job reads the counts from it (CLAUDE.md 3.7.1).

### 9. What bad input gets

| Input | Result |
|---|---|
| a ticker outside SPY, QQQ, IWM | `ValueError` before any query; `--flag-bars-from` exits 1 |
| a NaN price in a bar | `ValueError` naming the `ts`; nothing written for the month; the nightly exits 1 |
| `ts` not strictly increasing | `ValueError`; same |
| a row that is not a proven instant | `UnprovenRows`; same |
| a failed read or write, outage or defect | raises; earlier months stay written; the nightly logs it as an outage or a defect and exits 1 |
| a month with no bar | coverage row with `bars_in_month` 0 and `bars_judged` 0; no flag |
| the live edge | its last two bars are not judged until bars exist after them |
| a session's bars, after the nightly's refetch, differ from those the last pass judged | `BARS-CHANGED` names it; the month is judged again and replaced |
| a 23:00 value the nightly's refetch overwrote | not seen: the pass judges the refetched values (Design 5) |
| a second pass over unchanged bars | the same rows; only `checked_at` and `run_id` move |
| a replace of the month | flags and coverage of the month and of the month on each side cleared in the swap's transaction; `REBUILD` lines |
| a month never judged, in the manifest | `{"state": "not_judged"}` |

### 10. Consumers: what the second spec must decide

Nothing reads the flags after this spec. The consumers of the three tickers' 1-minute bars, named from the code by the bucket-copy and recompute specs, keep the prints:

- the strat feature and level builders (`strat_data_builder._load_1m_bars`, `strat_features_*`, `strat_features_levels_*`);
- historical signals (`historical_signals.load_intraday_bars`) and their metrics;
- level calibration (`calibrate_level_params.read_minutes`, `lib/level_calibration.py`);
- the end-of-day resolver and its `--re-resolve` (`gcp/signal_monitor_eod_resolver.py`);
- the premarket fields and their recompute (`gcp/fetchers/fetch_market_data.py`, which already runs the premarket print filter), the playbook resolver and the brief;
- the 15-minute flow and GEX builders;
- the chart route `GET /api/market/data/{ticker}/{date}`.

What the second spec has to settle:

- **Look-ahead (REQ-DATA-002).** A bar's flag rests on up to 30 later bars and is written after the session. A live consumer cannot have it, and a replay as of a time must not use a flag that rests on later bars. The coverage row's `checked_at` and the flag's `detected_at` are its as-of.
- **Which version and which hours.** Consumers name the rule version they honour, and whether they honour extended-hours flags, which include real trades at another price, such as the closing price reprinted after hours.
- **What honouring means for each consumer.** Drop the extreme for a high or low aggregate, or drop the bar; never a made-up value (the owner's decision).
- **Recompute.** What already built from the prints is rebuilt, and through which path.

### 11. Other specs this one meets

- **The bucket-copy spec** (`2026-11-13-feat-data-001-intraday-bucket-copy.md`, approved, implemented in #1943). Not edited. Its manifest entries gain one key (Design 8), and its runbook's replace now clears two more tables, for the months on each side too (Design 7).
- **The recompute spec** (`2026-11-14-feat-data-001-recompute-after-bar-rewrite.md`, approved, #1959). Not edited. This spec reuses four helpers of `gcp/bar_recompute.py` unchanged: `run_id`, `code_version`, `require_proven` and `bars_basis`.
- **The replace-months r2 spec** (#1953, implemented in #1955). Its swaps gain a second kind of derived clear, by read span (Design 7); `DERIVED_TS_TABLES` and the replace's rules are unchanged.
- **The two-bar-writers change** (#1936). The writer list of `market_data_intraday` is unchanged: the new module writes only its own two tables.
- **FEAT-STRAT-001's premarket print filter.** Not changed. Its spike geometry is the rule's where both apply (Design 1).

### 12. Site traceability

`site_source_notes` cannot be widened by the implementation PR, so it is declared now, by the bucket-copy spec's rule 2: the first Chain row of `docs/product/03-SITE-TRACEABILITY.md` that names the changed producer.

- The changed producer is the `fetch-alphavantage-intraday` job: its `main()` gains the pass and its replace two more cleared tables (Design 7). The first Chain row that names it is DASHBOARD-04 (`:334`), whose Data cell names `market_data_intraday` and both of its writers (read).
- The table, the `lib/` module and the tests add no route, no response shape and no reader the site shows, so rule 1 of that spec gives nothing.
- So `site_source_notes: [DASHBOARD-04]`. A FEAT-DATA-001 row for DASHBOARD-04 exists (`:1311`, read); the implementation PR extends it the way the earlier specs did: the new source hash and this change's prose first, then `Earlier:` and the earlier prose unchanged.
- The note says that the job now judges the bars it wrote and writes flags to two new tables, and that the route, its reader and the bars are unchanged.
- Nothing changes on the site, so the implementation PR has no deployed-site run to show (AGENTS.md, Review guidelines). Its evidence is the tests and the PR-body measurements; after the merge, Close-out's checks.

### 13. Capacity

| Run | Volume | Velocity | Wall-clock | Limits |
|---|---|---|---|---|
| nightly, three tickers, two months | 6 reads of at most 31,711 rows of seven columns (about 2 MB each), one in memory at a time; a few dozen flags | 1 coverage read per ticker (3), 6 bar reads, 6 write statements: 15 round trips | 8 to 30 s at 0.5 to 2 s a round trip, plus about 0.5 s of compute a month, most of it the two digests (Design 2) | `fetch-alphavantage-intraday`, 3,600 s, 2Gi, 1 retry (`gcp/deploy.sh:2215-2218`, read) |
| history, one ticker, 143 months | 143 reads, about 2,950,000 to 3,650,000 rows in all (about 1.45 times the 2,028,666 to 2,507,878 stored, for the margins; prototype, run); 3,061 to 6,834 flags; 143 coverage rows | 1 coverage read, 143 bar reads, 143 writes: 287 round trips | 145 to 575 s by Rule 0, plus about 70 s of compute (143 months at about 0.5 s); the export's 143 month reads, without margins, plus a Parquet write and an upload each, took 229.4 to 280.6 s a ticker (PR #1943 comment 6891791378, read) | the same job; 4 times 650 s is 2,600 s, under 3,600 s |
| history, dry run | the same reads | 144 round trips | 72 to 290 s, plus about 70 s of compute | the same |

- Memory: one ticker-month at a time, at most 31,711 rows; the rule's arrays are a few MB. The prototype ran each ticker's whole history (2.0 to 2.5 million bars) in one frame in 2 to 5 s (run).
- No per-bar or per-flag statement: one read and one write a ticker-month (REQ-CAP-002). A write per flag would be 16,441 round trips, up to 9 hours.
- Storage: about 16,500 flag rows of about 170 bytes, 2.8 MB, and 429 coverage rows of about 3 KB, most of it the 32 or so dates of `session_sha256`, 1.3 MB (estimates, not measured).
- Cost, at about $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read): a history execution of at most 650 s at 1 vCPU and 2 GiB is about 1.4 cents, under 5 cents for the three. The nightly adds under 35 s a run, 26 runs a month: about 2 cents a month. Nothing new is scheduled.

## Implementation plan: size

12 tasks, one branch, one PR.

1. Schema: the two tables, and their schema test.
2. `lib/bar_prints.py`: the rule and its tests on hand-written bars, the agreement test with `wick_excesses`.
3. The fixtures: export the 26 ticker-sessions (10 known, 12 clean, 4 half days) read-only with `scripts/db_query_cr.sh`, and write `sources.json`.
4. Tests of the rule on the known sessions and the clean sample.
5. `gcp/fetchers/intraday_bar_flags.py`: the read, the proof, the judging, the session part and the log lines.
6. The write statement, the comparison and `BARS-CHANGED`.
7. The integration test on real Postgres, the replace's clear included.
8. `main()`: the nightly pass and its switch.
9. `--flag-bars-from`, its refusals and its dry run.
10. `clear_span_tables` in `replace_rows_in_window`, `DERIVED_SPAN_TABLES` in `replace_month`, and the replace tests.
11. The manifest's `flags` and the export tests.
12. The PR-body measurements, the site note, the snapshot, the generated inventories, the catalog record and PR traceability.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes, read-only ones included. The record is kept as comments on the implementation PR.

**Before the merge**: the measurements of `done_when` item 13, nothing else.

**After the merge**

1. **Apply the schema**: `./gcp/deploy.sh apply-schema`.
   - Check, read-only: `information_schema.columns` lists both tables with the columns of Design 2; both are empty.
2. **Deploy the fetchers**: `./gcp/deploy.sh fetchers`, from a checkout of `main` at or after the merge. The schema goes first: the export reads the coverage table.
   - Check: `fetch-alphavantage-intraday`'s image is the build's digest.
3. **History, dry run**, one execution per ticker:
   `gcloud run jobs execute fetch-alphavantage-intraday --region us-east1 --args="--flag-bars-from=2015-01,--symbol=SPY" --wait`
   - Check: exit 0; 143 `bar flags month:` lines; the summary's counts equal the PR body's figures for the shipped function, plus whatever the sessions since 2026-11-13 add.
4. **History, committed**: the same three commands with `,--commit`.
   - Check, read-only: per ticker, 143 coverage rows for `isolated-print-v1`, `bars_in_month` equal to the stored rows of each month window; the flag rows by `session_part` and `side` equal the run's summary; the named bars of `done_when` item 3 are flagged in the table; a second dry run reports no `BARS-CHANGED`.
5. **The first nightly after the deploy.**
   - Check: the log holds `bar flags: 6 months`; the coverage rows of the previous and current month have `checked_at` from that run; the three manifests' entries for those two months hold `flags`.
6. **Refresh the manifests**, if the owner wants every month's counts in the bucket: `--export-bars-from=2015-01`, one execution per ticker, as on 2026-11-15.
7. **After any later replace**: `--flag-bars-from` over the replaced months and one month on each side, dry run, then committed, with the step 4 checks for those months.

**After the close-out**: the DASHBOARD-04 note and the plan's status are brought to the deployed state on a `docs/` branch, and the second spec (decision 11) is written.

## Risks

- **A real print is flagged.** A one-minute move whose close sits at its extreme and whose next two bars open and close more than 50 bp and 6 local ranges away would be flagged. No session read by hand looked like that, and not every flagged session was read: 219 ticker-sessions hold the 445 regular-hours rows. The flag says "unrepresentative of its minute", never "false"; the second spec decides what that costs each consumer.
- **A misprint is not flagged.** A print within 50 bp of its neighbourhood: some of SPY's 26 prints at 411.032 on 2023-05-25 fall inside the threshold while the market traded near them. A run of three or more consecutive bars whose opens and closes are also misprinted. A misprint in a fast minute, where 6 local ranges is wide.
- **The parameters rest on ten labelled sessions.** The weakest clears the multiple by 1.29 local ranges and the floor by 14.5 bp. Another set needs a new rule version and a full history run, and both versions stay in the table until one is deleted by hand.
- **Look-ahead.** A flag rests on later bars (Design 10). No consumer reads it in this spec, so none can leak the future through it yet.
- **A flag can outlive the bar it describes for up to a night** after the 23:00 rewrite (decision 6). How often is not measured, and `BARS-CHANGED` cannot count it: the next refetch overwrites the 23:00 values before the pass reads (Design 5).
- **After a replace, the month and its neighbours read "not judged"** until the history command runs. A consumer of the second spec has to handle that state.
- **The extended-hours flags are many**, 15,996 over the history and growing since 2023, and they include real trades at another price. A consumer that honours every flag after hours drops those prints too.
- **The nightly can now fail for a reason that is not the fetch.** A NaN price, an unproven row or the flag tables missing ends the execution with exit 1 and a failure issue, and the job retries once. The bars are written before the pass runs, so the fetch is not undone.
- **The manifest's older months carry no counts** until `--export-bars-from` writes them again.

## What was not verified

- That any flagged print did or did not trade: not checked; no second source is connected.
- What the extended-hours prints are (late reports, the closing price reprinted, odd lots): not checked.
- The shipped function: not written. Every count here is the prototype's, over the bucket copy, whose rows equal the table's in count and in first and last `ts` (db-query-nbpxc); values rewritten in place since the export were not looked for.
- Whether the 23:00 ET daily fetcher ever writes a value that differs from the 21:00 nightly's: not measured, and the pass cannot see it (Design 5).
- The wall-clock of the pass and of the history run on production: not measured. The figures are Rule 0's and the export's measured times.
- That `./gcp/deploy.sh apply-schema` creates both tables in one run: not run.
- Every one of the 219 ticker-sessions with a regular-hours flag: not read by hand. Those read were the ten known sessions, SPY 2018-02-06 and 2023-05-25 bar by bar, the list of SPY's regular-hours flags of 2025 and 2026 with three of them bar by bar, the four regular-hours open and close prints, three half days bar by bar, SPY 2025-04-09 after the close, and six extended-hours flags drawn at random.
- Tickers other than SPY, QQQ and IWM: not looked at.
- Whether the backend architecture canvas depicts the fetch job: not opened.
