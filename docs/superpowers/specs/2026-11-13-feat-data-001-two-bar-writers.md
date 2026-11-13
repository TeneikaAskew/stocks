---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-DATA-001]
issues: []
canvases: []
site_source_notes: [CHARTS-01, DASHBOARD-04, JOURNAL-01, LIVE-08]
done_when:
  - "tests/gcp/test_backfill_ticker.py::test_run_fetches_and_writes_no_one_minute_bars passes: with requests.get captured, gcp.database.upsert_dataframe recorded, BACKFILL_ADD_TO_WATCHLIST set to false and add_to_watchlist replaced by a stub that fails when called, run() for BACKFILL_TICKER amd, one BACKFILL_DATES date and BACKFILL_INCLUDE_NEWS false sends exactly one request, whose function is TIME_SERIES_DAILY_ADJUSTED; with BACKFILL_INCLUDE_NEWS true it sends exactly two, TIME_SERIES_DAILY_ADJUSTED then NEWS_SENTIMENT; in both runs no request names TIME_SERIES_INTRADAY, no recorded upsert names market_data_intraday, market_data_daily is upserted with the daily rows, exactly one INFO record reads '1-min bars are not fetched by this job; premarket context reads market_data_intraday', compute_indicators_for_full_range is called once and compute_indicators_for_dates once with the date and its prior weekday, and run() returns 0; gcp.backfill_ticker has no attribute av_intraday_month (on main c698b24e the same run sends TIME_SERIES_DAILY_ADJUSTED and TIME_SERIES_INTRADAY and upserts market_data_daily and market_data_intraday; the variable and the stub are set because the watchlist step opens a database connection, and so that the test holds under either default of the variable)"
  - "tests/gcp/test_backfill_ticker.py::test_premarket_absent_bars_says_so passes: with gcp.database.query_to_dataframe_strict answering the premarket read with zero rows, compute_indicators_for_dates('SPY', [2026-11-06]) upserts exactly one market_data_daily row for that date, the row holds no key that starts with pre_ and no gap_pct, and exactly one WARNING record holds market_data_intraday, SPY and 2026-11-06 (on main the row is the same and no log record names the table)"
  - "tests/gcp/test_backfill_ticker.py::test_premarket_read_failure_fails_the_run passes for two failures of the premarket read through gcp.database.query_to_dataframe_strict: ConnectionError('connection refused') (an outage to lib.infra_errors.is_infrastructure_error) and KeyError('close') (a defect). With target dates 2026-11-04, 2026-11-05 and 2026-11-06 and the read failing for 2026-11-05, compute_indicators_for_dates raises that same exception, exactly one row is upserted (2026-11-04, with its pre_ keys), no row is upserted for 2026-11-05 or 2026-11-06 and no bar read is made for 2026-11-06. With the same failure under run() for BACKFILL_DATES 2026-11-05,2026-11-06 and BACKFILL_ADD_TO_WATCHLIST true, run() raises that exception instead of returning and the add_to_watchlist stub is called zero times. ::test_premarket_compute_defect_is_still_a_warning passes: with bars returned and lib.indicators.calculate_premarket_context raising KeyError('close') the row is upserted without a pre_ key and one WARNING record starts with 'pre-market compute failed' (on main the outage is swallowed inside gcp.database.query_to_dataframe, every date's row is upserted without a pre_ key and nothing is raised; the compute case is the same on main and pins that it did not change)"
  - "tests/gcp/test_migrate_to_gcp_dispatch.py::test_no_intraday_loader_remains passes: gcp.migrate_to_gcp has no attribute migrate_market_data_intraday, _normalize_ohlcv or COLUMN_MAP; market_data_intraday is not a key of TABLE_FUNCS, and its seven keys map to the functions named upload_raw_parquets (gcs_raw), migrate_market_data_daily_av (market_data_daily_av), backfill_daily_indicators (daily_indicators), migrate_etf_options (etf_options_snapshots), migrate_av_options (av_options), migrate_earnings_options (earnings_options_snapshots) and migrate_trades (trades); the text of gcp/migrate_to_gcp.py does not hold market_data_intraday and the writer scan of Design 4 finds no match in it; main() for --table trades, with TABLE_FUNCS['trades'] replaced by a recorder, calls it once with the data directory and dry_run False; and python gcp/migrate_to_gcp.py --table market_data_intraday in a subprocess exits 2 with argparse's invalid choice message on stderr. The test asserts nothing about what a call without --table runs or returns (on main the attribute exists, the selector is accepted and the scan matches lines 249 and 252)"
  - "tests/meta/test_production_writers.py::test_only_the_two_fetchers_write_one_minute_bars passes with SANCTIONED_INTRADAY_WRITERS equal to gcp/fetchers/fetch_alphavantage_intraday.py and gcp/fetchers/fetch_market_data.py (on main it fails naming gcp/backfill_ticker.py, the call at line 652, and gcp/migrate_to_gcp.py, lines 249 and 252), and ::test_sanctioned_intraday_writers_still_write passes: each of the two files exists and holds at least one match of the same scan (on main lines 318 and 639 of the first and line 573 of the second)"
  - "tests/meta/test_production_writers.py::test_the_intraday_writer_scan_catches_the_obvious_rewrites passes: the scan matches each of these 20 snippets: upsert_dataframe with a nested pd.DataFrame(...) argument, bulk_insert_dataframe, bulk_copy_upsert, bulk_copy_update, replace_rows_in_window and to_sql, each with the table name as an argument; INSERT INTO, COPY, DELETE FROM, UPDATE, TRUNCATE TABLE and MERGE INTO on market_data_intraday; a lower-case insert into public.market_data_intraday_spy; a TRUNCATE of market_data_intraday_other; an INSERT INTO a double-quoted market_data_intraday; a DELETE FROM split across two adjacent string literals; a DELETE FROM market_data_intraday_qqq inside a WITH; an upsert_dataframe call whose table name sits more than 300 characters after the opening parenthesis; an upsert_dataframe call that passes the table as a keyword argument; and an f-string DELETE FROM market_data_intraday whose only field is in its WHERE; and it matches none of these 8: a SELECT from the table, a SELECT from it that ends FOR UPDATE, an upsert into market_data_daily, a DELETE FROM archive_yahoo_market_data_intraday, an INSERT INTO market_data_intraday_flow_15m, a log line that names the table, a docstring that holds DELETE FROM market_data_intraday, and a comment that holds UPDATE market_data_intraday"
  - "tests/meta/test_production_writers.py::test_only_named_entry_points_reach_the_intraday_writers passes: (a) for each sanctioned file the test computes the functions that reach a write of the scan through calls inside the file (on main they are main, process_symbol, replace_month and run_replace_months in gcp/fetchers/fetch_alphavantage_intraday.py and main, process_ticker and write_intraday_to_sql in gcp/fetchers/fetch_market_data.py), and no other .py file under gcp/, lib/, scripts/ or platform/ imports one of them from its module or names one through an imported alias of the module; (b) the only file outside the two whose string constants outside docstrings name either module, by dotted name or by path, is scripts/backfill_watchlist_data.py; (c) the only files outside the two whose string constants outside docstrings hold the job name fetch-market-data, fetch-alphavantage-intraday or intraday-bulk-backfill are platform/api/routers/admin.py, scripts/audit_data_freshness.py and scripts/maintenance/refresh_architecture_drawio.py; each of those four files still holds what it is listed for; (d) in gcp/deploy.sh with comment lines dropped, the functions whose job command runs either module are exactly deploy_fetch_market_data, deploy_fetch_alphavantage and deploy_intraday_bulk_backfill, and the _schedule and _schedule_with_args lines that target their three jobs are exactly fetch-market-data-daily, av-intraday-monthly and av-intraday-nightly; and the checks of (a) to (c) reject the 9 snippets and accept the 4 snippets of Design 4 (the test passes on main c698b24e: it is a guard on a new path, and the snippets show it can fail)"
  - "tests/meta/test_production_writers.py::test_the_yahoo_archive_is_the_one_named_deleter passes: the files under gcp/, lib/, scripts/ and platform/ that hold both an f-string whose literal text puts INSERT INTO, MERGE INTO, DELETE FROM, UPDATE, TRUNCATE or COPY directly before a field and the name of the table or of one of its partitions as a whole string constant are exactly gcp/database.py and scripts/archive_yahoo_data.py; scripts.archive_yahoo_data.TABLES has exactly the keys earnings_options_snapshots, etf_options_snapshots, market_data_daily and market_data_intraday; the quoted values of YAHOO_PREDICATE are exactly yfinance, yahoo and yahooquery; and delete_chunk for market_data_intraday on a recording connection executes one statement, a DELETE FROM market_data_intraday that holds YAHOO_PREDICATE (the test passes on main: it pins a deleter the writer scan cannot see)"
  - "tests/meta/test_production_writers.py::test_no_code_dispatches_backfill_ticker passes: no string constant outside a docstring, in any .py file under gcp/, lib/, scripts/ or platform/ other than gcp/backfill_ticker.py, contains backfill-ticker (on main c698b24e it fails at gcp/discord_interactions/main.py:464 and :470 and at scripts/backfill_and_replay.py:178, :180, :306 and :330; it passes once the implementation of FEAT-REPLAY-001 is on main, which is the precondition of this plan)"
  - "tests/gcp/test_intraday_as_traded.py passes with test_backfill_ticker_month_fetch_requests_as_traded and the backfill_ticker import removed, the required file set of test_every_intraday_request_in_the_repo_asks_for_as_traded at six files (no gcp/backfill_ticker.py), len(sites) >= 7, and a new assertion that gcp/backfill_ticker.py is not among the files that hold a TIME_SERIES_INTRADAY request (on main the scan finds 8 requests in 7 files and that assertion fails at gcp/backfill_ticker.py:138); tests/gcp/test_intraday_writers_utc.py passes with test_backfill_ticker_writes_utc_instants removed and its other seven tests unmodified"
  - "make test passes on the PR head; the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py, the multiwriter block of docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md lists market_data_intraday with 2 writers, gcp/fetchers/fetch_alphavantage_intraday.py and gcp/fetchers/fetch_market_data.py (4 on main), and tests/scripts/test_check_generated_docs.py passes"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the four (FEAT-DATA-001, component) rows of Design 7 are in the implementation-source notes of 03-SITE-TRACEABILITY.md with docs/review-evidence/site-source-snapshot.json regenerated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# Two writer modules for the 1-minute bar table

## Problem

The owner's rule, 2026-11-13: every replay reads 1-minute bars only from the store the nightly pull fills, the Cloud SQL table `market_data_intraday` (interval `1min`). No replay fetches bars from AlphaVantage or anywhere else. Scope is SPY, QQQ and IWM. So the table must have a known, short list of what writes it and of what starts those writers. Read at `main` c698b24e, with the runs of 2026-11-13 kept in the scratch folders named under Design 4:

- Four files hold a write to the table by its name. A scan of `gcp/`, `lib/`, `scripts/` and `platform/` (Design 4) finds six writes:
  - `gcp/fetchers/fetch_alphavantage_intraday.py:318` and `:639`: the nightly pull, the bulk backfill and `replace_month`.
  - `gcp/fetchers/fetch_market_data.py:573`: `write_intraday_to_sql`, the daily fetcher.
  - `gcp/backfill_ticker.py:652`: the `backfill-ticker` job.
  - `gcp/migrate_to_gcp.py:249` and `:252`: a delete and a bulk insert.
- A fifth file can delete rows through a table name held in a variable: `scripts/archive_yahoo_data.py` (`:57-79`, `:153`). It is run by hand. Design 4 says what it deletes.
- `backfill-ticker` pulls whole months of 1-min bars from AlphaVantage on its own (`av_intraday_month`, `gcp/backfill_ticker.py:134-161`) and upserts them (`run`, step 2, `:633-656`). Run on 2026-11-13 with `requests.get` captured: `run()` sent `TIME_SERIES_DAILY_ADJUSTED` and `TIME_SERIES_INTRADAY`, and upserted `market_data_daily` and `market_data_intraday`.
- `gcp/migrate_to_gcp.py:197-262` deletes every 1-min row of a ticker (`:248-251`) and bulk-inserts a local parquet (`:252`). The two steps are not one transaction, and a failure between them is logged and the migration goes on (`:256-261`). It runs in the default path (`:819`). Run the same day with every handler stubbed: `main()` with no `--table` called `upload_raw_parquets`, `migrate_market_data_intraday`, `migrate_etf_options`, `migrate_earnings_options`, `migrate_trades`. `./gcp/deploy.sh migrate` runs that script with its own arguments (`gcp/deploy.sh:69-77`, `:5362`).
- The job's premarket step cannot tell an outage from an empty premarket. It reads the table through `query_to_dataframe` (`gcp/backfill_ticker.py:498-505`), which returns an empty frame on any error (`gcp/database.py:218-241`), inside a `try` whose `except` only logs (`:496`, `:557-558`). Run the same day:
  - zero premarket rows: the day's row is upserted with no `pre_` key, and no log line names the table;
  - the read raising `ConnectionError`: the same row is upserted, nothing is raised, and the only trace is `Cloud SQL query failed: connection refused` from `gcp.database`.
- Nothing lists who may write the table or what may start a writer. `tests/meta/test_production_writers.py` guards `signal_alerts`, `trades` and three provenance tables (`:35-47`, `:237-259`), not this one.
- Two tests pin what has to go: `tests/gcp/test_intraday_as_traded.py:81-83` and `:142-145` (the job's request, 8 requests in 7 files), and `tests/gcp/test_intraday_writers_utc.py:66-94` (the job's write).
- Two callers still dispatch the job and expect it to bring bars: Discord `/replay` (`gcp/discord_interactions/main.py:464`) and `scripts/backfill_and_replay.py:180`. The spec `docs/superpowers/specs/2026-11-13-feat-replay-001-replay-bars-from-the-table.md` (FEAT-REPLAY-001, PR #1882) removes both dispatches. That spec is on `main` at f43447fb as a draft, with its approval in a one-line PR. Its implementation is not on `main`.

## Non-goals

- The reader side. A strict 1-min read on `lib.data_loader.DataLoader`, the replay and backtest call sites that switch to it, the interval filter on seven bar reads and their guards are the other half: `docs/superpowers/specs/2026-11-13-feat-data-001-strict-bar-loader.md`. Neither half needs the other's code: this one edits `gcp/backfill_ticker.py`, `gcp/migrate_to_gcp.py` and tests, that one edits `lib/data_loader.py`, the entry points and tests. Both add tests to `tests/meta/test_production_writers.py`; the additions share no name and no helper beyond what that file has on `main`.
- The Discord and API replay surfaces. They are FEAT-REPLAY-001's spec.
- The job is not deleted. It still writes daily history, news, indicators, strat fields, premarket context for dates the table holds, and the watchlist row.
- No change to the two fetchers, to which tickers the nightly pulls, to any entry point of Design 4, or to `gcp/deploy.sh` (owned by FEAT-DEPLOY-001). The job stays deployed (`gcp/deploy.sh:1294-1311`, the `discord` target at `:5429`), and the `migrate` target stays (`:69-77`).
- An operator's explicit backfill is not a replay and stays allowed. The owner's rule is that a replay starts no pull. It does not say an operator may not run a fetcher. Design 4 names each such command.
- The job's two daily-bar reads stay on the swallowing helper (`gcp/backfill_ticker.py:371`, `:439`). An outage there still reads as `insufficient daily history` and skips the date (`:379-384`, `:447-450`). They read `market_data_daily`, not bars. The implementation marks both with the `AUDIT-2026-05-13` comment.
- The `except` around the premarket compute stays (`:557-558`). Design 2 lists what it still catches.
- The watchlist step (`:687-693`) is not changed. The approved `docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock-a.md` changes its default at `:611` and the two watchlist tests of `tests/gcp/test_backfill_ticker.py` (`:240-251`). The two changes touch different lines and merge in either order. The tests of this spec set `BACKFILL_ADD_TO_WATCHLIST` themselves (false in `done_when` item 1, true in item 3), so they hold under either default.
- `scripts/archive_yahoo_data.py` is not changed. Design 4 says what it deletes, when it runs, and which test pins it.
- No stored bar is written, deleted or moved by this change. Bars the job wrote in the past stay.
- No new way to bring bars for a ticker outside the nightly's set. After this spec and FEAT-REPLAY-001, nothing in the repo dispatches the job; it is run by hand, and it brings no 1-min bars (the owner's decision, 2026-11-13).
- The approved `docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md` and the approved `docs/superpowers/specs/2026-10-16-feat-deploy-001-av-options-legacy-dispatch-retirement.md` are narrowed, not superseded (Risks).
- No trading cost appears anywhere.

## Approaches considered

1. Remove the fetch and the write from the job and the loader from the migrate script, then hold the list at two modules with tests (chosen). The table is then written by the two fetchers only, and what starts them is a named list (Design 4).
2. Keep the job's bars but route them through the nightly fetcher's `fetch_month` and `replace_month`. Rejected by the owner's decision of 2026-11-13: a replay starts no pull, and this job is the pull a replay started (Discord `/replay` and `scripts/backfill_and_replay.py`, until FEAT-REPLAY-001's implementation). An operator who wants bars for a ticker runs one of the fetchers' own commands (Design 4), so the job needs no second copy of that path.
3. List `gcp/migrate_to_gcp.py` as a third sanctioned writer. Rejected by the owner: one command could still replace a ticker's bars with a laptop file, in two steps that are not atomic.

## Design

### 1. `backfill-ticker` stops fetching and writing 1-min bars

- Removed from `gcp/backfill_ticker.py`: `av_intraday_month` (`:134-161`), step 2 of `run` (`:633-656`), and the import of `eastern_index_to_utc` (`:65`), whose only use is `:643`. `eastern_bounds_utc` stays (`:497`).
- Where step 2 was, `run` logs one INFO line: `1-min bars are not fetched by this job; premarket context reads market_data_intraday`. Close-out 3 reads it in the execution log.
- The module docstring (`:13-15`) and the docstring of `run` (`:574-576`) lose the intraday step and say where the premarket step gets its bars. The first lines of the module docstring (`:4-5`) stop saying Discord `/replay` triggers the job.
- What `run` still does, in order: daily history from AlphaVantage into `market_data_daily` (`:619-631`), news when asked (`:658-668`), indicators over the full range (`:674`), strat fields and premarket context per target date (`:679-685`), the watchlist row (`:687-693`).
- The job keeps its `requests` import and `AV_BASE` for the daily and news calls.

### 2. The premarket read becomes strict

In `compute_indicators_for_dates` (`gcp/backfill_ticker.py:495-558`):

- `eastern_bounds_utc` (`:497`) and the bar read (`:498-505`) move out of the `try`. The read goes through `gcp.database.query_to_dataframe_strict`, with the same SQL text and the same three parameters. No `timeout_s` is passed, as today.
- Zero rows: one `log.warning`, `no 1-min bars in market_data_intraday for {T} premarket {date}; pre_* not written`, with the ticker in upper case and the date as `YYYY-MM-DD`. The row is then upserted without any `pre_` key, as today (`:506`, `:560-561`; `upsert_dataframe` builds its update list from the frame's own columns, `gcp/database.py:483-484`).
- Any exception from the read propagates. The date's row is not upserted and the run ends non-zero. The job runs with `--max-retries 0` (`gcp/deploy.sh:1298`).
- A failed read ends the date loop. The loop runs the target dates in sorted order (`:438`), so this is what a failed read on one date leaves, by the code and by the prototype of Design 4:
  - written and kept: the daily history of step 1, the news, the full-range indicators, and the rows of the target dates before the failing one;
  - not written: the failing date's row, the rows of every later target date, and the watchlist row (`:687-693` is not reached);
  - no read is made for a later date.
  - This is the intended behaviour (CLAUDE.md 3.7: an outage fails the run, it is not skipped). A database that failed one read is not asked for the next. Every write of the job is an upsert on its key (`:629-630`, `:413-416`, `:560-561`, `:666-667`), so a second run of the same command converges on the same rows.
- An outage and a defect: a job has no status code, so both end the run non-zero with the exception as raised (`ConnectionError('connection refused')` stays a `ConnectionError`, `KeyError('close')` stays a `KeyError`). Neither is turned into "no bars". The test covers both.
- What moving the two calls out of the `try` changes for other inputs. Today the `except` at `:557-558` catches nothing from the read, because the swallowing helper never raises (`gcp/database.py:234-241`). From `eastern_bounds_utc` it could only catch an error on a value that is not a date, and `fd` always comes from `_parse_dates` (`:83-96`) as a `date`. So no input that was a warning becomes a failure, except a failed read, which is the intended change.
- What the `except` still catches, unchanged: errors from `premarket_filter_inputs`, from `calculate_premarket_context` and from the conversions at `:536-554`. The level-parameter read already uses the strict helper, and `load_level_params` turns its failure into `LevelParamsUnavailable` (`lib/strat_levels.py:1280-1283`), which the job handles at `:524-528` by writing the snapshot unfiltered with `pre_filter_status` `level_params_unavailable`. This spec does not change that.
- Cloud SQL not configured: the strict helper raises from `get_engine`. That is not a new state for the job: step 1's upsert needs the database first.
- For a ticker the nightly has never pulled, the job leaves daily bars, indicators and news, and no premarket fields. The log line says so for each date.

### 3. `gcp/migrate_to_gcp.py`

- Removed: `migrate_market_data_intraday` and its section comment (`:195-262`), its `TABLE_FUNCS` entry (`:773`), its call in the default path (`:819`), the helper `_normalize_ohlcv` (`:109-115`, used only at `:222`), the dict `COLUMN_MAP` (`:96-101`, used only at `:114`, inside that helper) and the import of `eastern_index_to_utc` (`:48`, used only at `:232`). The section comment at `:94` stays: the indicator column import below it (`:103-106`) is still used (`:177`).
- After the removal the file does not hold the text `market_data_intraday`. The test of `done_when` item 4 holds it there.
- `--table` takes its choices from `sorted(TABLE_FUNCS.keys())` (`:795`), so `--table market_data_intraday` is then rejected by argparse with exit 2 and `invalid choice`, before any handler runs. That is the loud answer. Run on 2026-11-13 with the key removed in memory: `SystemExit(2)`, and the message lists the other seven.
- Seven selectors stay, each with the function it has today: `gcs_raw`, `market_data_daily_av`, `daily_indicators`, `etf_options_snapshots`, `av_options`, `earnings_options_snapshots`, `trades`.
- A call without `--table` no longer loads bars. This spec's test asserts nothing else about that call: FEAT-OPTION-001's draft changes what it runs and returns (Risks).
- The file stays in `SANCTIONED_ROW_WRITERS` and `SANCTIONED_PROVENANCE_WRITERS` (`tests/meta/test_production_writers.py:45`, `:246`): `migrate_trades` still writes `trades`.

### 4. Who may write the table (`tests/meta/test_production_writers.py`, extended)

The rule is two writer modules, and a named list of what starts them.

**The two modules.** `SANCTIONED_INTRADAY_WRITERS = {"gcp/fetchers/fetch_alphavantage_intraday.py", "gcp/fetchers/fetch_market_data.py"}`. Both stamp what they write with `data_source` `alphavantage` (`fetch_alphavantage_intraday.py:168`, `fetch_market_data.py:564`).

**What starts them.** Read from the code on 2026-11-13, not from GCP:

| Module | Entry point | Who starts it | What it writes |
|---|---|---|---|
| `fetch_alphavantage_intraday` | scheduler `av-intraday-nightly`, 21:00 ET Monday to Saturday (`gcp/deploy.sh:4741-4742`), job `fetch-alphavantage-intraday` with `--symbol=ALL --force` | Cloud Scheduler | the brief tickers, the insight defaults and the watchlist (`fetch_alphavantage_intraday.py:45-52`), from the first of the previous month to today (`:888-890`) |
| `fetch_alphavantage_intraday` | scheduler `av-intraday-monthly`, 21:00 ET on the 1st (`gcp/deploy.sh:4723`), the same job with its default arguments | Cloud Scheduler | the same set and range |
| `fetch_alphavantage_intraday` | job `intraday-bulk-backfill` (`gcp/deploy.sh:3738-3771`), no scheduler | an operator | the earnings universe file from 2024-01-01 |
| `fetch_alphavantage_intraday` | the `fetch-alphavantage-intraday` job run with `--symbol`, `--start-date`, `--end-date`, or `--replace-months PATH --commit` (`fetch_alphavantage_intraday.py:881-882`, `replace_month`, `:564`) | an operator | the named tickers and months; `--replace-months` deletes and re-inserts a ticker-month in one transaction |
| `fetch_market_data` | scheduler `fetch-market-data-daily`, 23:00 ET Monday to Friday (`gcp/deploy.sh:4622`), job `fetch-market-data` | Cloud Scheduler | that day's bars for its list, the watchlist and the earnings tickers of the next 7 days (`fetch_market_data.py:1214-1241`) |
| `fetch_market_data` | `POST /api/admin/data-sources/market_data_daily/refresh` (`platform/api/routers/admin.py:1262`, `:1524-1525`), which runs the `fetch-market-data` job as deployed | an admin, from the Admin page, at most once a minute | the same as the scheduled run |
| `fetch_market_data` | `scripts/backfill_watchlist_data.py` (`backfill_intraday`, `:255-273`), which runs the module with `--tickers T --date D` for the last 5 weekdays of a watchlist ticker that holds no 1-min row in the last 7 days (`:115-120`), or of every one with `--force` | an operator: `./gcp/deploy.sh backfill` (`gcp/deploy.sh:5399`, `:5094-5108`), the last step of `./gcp/deploy.sh all` (`:5489`), or the script by hand | those tickers and dates |
| `fetch_market_data` | the `fetch-market-data` job run with `--tickers` and `--date` (`--allow-stale-date` for a date more than 5 days back, `fetch_market_data.py:1063-1091`, `:1182`) | an operator | the named tickers on that date |

- The daily fetcher's `--backfill` mode writes daily bars only (`fetch_market_data.py:1193-1194`, `_run_backfill`, `:973`). `fetch-earnings-history` reaches that mode (`gcp/fetchers/fetch_earnings_history.py:558`), so it is not in the table.
- None of the eight is a replay, and no replay starts one. FEAT-REPLAY-001's guard holds that for the Discord and API paths and the loader half for the rest. An operator's explicit backfill is the supported way to bring bars the nightly did not (Non-goals).

**The writer scan.** It reads each file under the test file's own `SCAN_ROOTS` through `_py_files` (`:26`, `:63-68`) as a syntax tree. A file that does not parse fails the test. It looks for a write that creates, replaces or deletes rows of the table or of one of its five partitions (`gcp/schema.sql:140-165`: `_spy`, `_iwm`, `_qqq`, `_spx`, `_other`), with an optional `public.` prefix and optional double quotes around either name, case-insensitive:

- in every string constant that is not a docstring (Python joins adjacent literals into one constant; an f-string is read as its literal parts): `INSERT INTO`, `MERGE INTO`, `COPY`, `DELETE FROM`, `UPDATE` and `TRUNCATE` on the table;
- a call of `upsert_dataframe`, `bulk_insert_dataframe`, `bulk_copy_upsert`, `bulk_copy_update` or `replace_rows_in_window` (the five write helpers of `gcp/database.py`: `:417`, `:871`, `:680`, `:806`, `:536`) or of `to_sql`, with the table name as a string constant anywhere in its arguments, positional or keyword, at any distance.

The existing `_ROW_WRITE` (`:35-40`) reads raw text within 300 characters and also names `upsert_rows`, a helper no file under the scan roots defines. This scan does not copy either.

**Six tests.**

1. `test_only_the_two_fetchers_write_one_minute_bars`: no file outside the set holds a match.
2. `test_sanctioned_intraday_writers_still_write`: each file in the set exists and holds a match, so the set cannot keep a file that stopped writing.
3. `test_the_intraday_writer_scan_catches_the_obvious_rewrites`: the 20 must-catch and 8 must-ignore snippets of `done_when` item 6.
4. `test_only_named_entry_points_reach_the_intraday_writers`: the table above, as far as source text can hold it.
   - (a) For each of the two files, the writer closure is computed, not listed by hand: the top-level functions that hold a match, and those that call one of them by name inside the file. No other file imports a closure name from the module (`from module import name` or `*`) or names one through an alias the file imported for the module (`alias.name`).
   - (b) `INTRADAY_WRITER_MODULE_STARTERS = {"scripts/backfill_watchlist_data.py"}`: the only file outside the two whose non-docstring string constants name either module, as `gcp.fetchers.fetch_...` or as its path.
   - (c) `INTRADAY_WRITER_JOB_NAME_FILES`: the only files outside the two whose non-docstring string constants hold `fetch-market-data`, `fetch-alphavantage-intraday` or `intraday-bulk-backfill` as a whole name. Three today: `platform/api/routers/admin.py` (`:1262`, the Admin refresh), `scripts/audit_data_freshness.py` (`:893`, a label the freshness audit prints) and `scripts/maintenance/refresh_architecture_drawio.py` (`:70`, a diagram label). Only the first dispatches.
   - Each file listed in (b) and (c) must still hold what it is listed for.
   - (d) `gcp/deploy.sh`, comment lines dropped: the functions whose job command runs either module are exactly `deploy_fetch_market_data`, `deploy_fetch_alphavantage` and `deploy_intraday_bulk_backfill`, and the `_schedule` and `_schedule_with_args` lines that target their jobs are exactly the three schedulers of the table. The test reads that file. It does not edit it.
   - Must-reject snippets, 9: a writer function imported by a third file; `replace_month` through a module alias; the module imported whole and its `main` called; `process_ticker` imported; a star import; the fetcher run as a subprocess with `-m`; the fetcher run by its path; a writer job dispatched by name; a writer job's path in an f-string.
   - Must-accept snippets, 4: an import of a helper that reaches no write (`_run_backfill`, `fetch_minute_data`); a module alias used for a name outside the closure; a string that holds a scheduler's name and not the job's; a docstring that names the module.
5. `test_the_yahoo_archive_is_the_one_named_deleter`: the next paragraph.
6. `test_no_code_dispatches_backfill_ticker` holds the order with FEAT-REPLAY-001 (Risks): no string constant outside a docstring, in a `.py` file under the same roots other than `gcp/backfill_ticker.py`, contains `backfill-ticker`. A later spec that adds a dispatcher lists it in this test.

A later spec that adds an entry point lists it in test 4 and in the table above.

**The one known deleter the scan cannot see.** `scripts/archive_yahoo_data.py`, read whole on 2026-11-13:

- It holds the table's name in a config dict of four tables (`TABLES`, `:57-79`) and builds its SQL from the dict (`:126`, `:153`).
- What it selects: rows whose `data_source` is NULL or one of `yfinance`, `yahoo`, `yahooquery` (`YAHOO_PREDICATE`, `:51-53`). Neither writer module stamps such a row, and neither did the two writers this spec removes (`gcp/backfill_ticker.py:650`, `gcp/migrate_to_gcp.py:237`). Whether the table holds any such row today is not checked.
- What it does: it copies the selected rows to `archive_yahoo_market_data_intraday` (`archive_chunk`, `:116-138`). With `--delete` it then deletes the selected rows from the table in chunks (`delete_chunk`, `:141-163`, called at `:245`). It creates no row in the table.
- When it runs: by hand only, with `--confirm market_data_intraday` or `--confirm all` (`:306-313`). No job, scheduler, workflow or script calls it. The only other mention in the repo is a comment at `gcp/schema.sql:555`.
- Test 5 pins it. It lists the files that hold both a write statement whose table is an f-string field and the table's name as a whole string constant: `gcp/database.py` (the write helpers; the name at `:392` is the key of the UTC check) and this script, and nothing else. It also pins the script's four table names, the three Yahoo source names and the statement `delete_chunk` executes for the table.
- FEAT-OPTION-001's draft makes this script refuse deletes on the two options tables and keeps the four keys and the deletes on the two market-data tables (its Design, `:124-134`). Test 5 holds in either order.

**Prototypes.** Each scan of this section was prototyped and run on this branch on 2026-11-13, whose code is that of `main` c698b24e. What each flags there is stated beside it above.

- The revised writer scan flags exactly `gcp/backfill_ticker.py:652` (the table name is on `:653`), `gcp/migrate_to_gcp.py:249` and `:252`, and finds the three writes of the two sanctioned files (`:318`, `:639`, `:573`). All 20 must-catch snippets match and none of the 8 must-ignore snippets does.
- The entry-point checks find no violation on `main` with the lists above, reject all 9 snippets and accept all 4. The closures are the seven functions `done_when` item 7 names. In `gcp/deploy.sh` they find the three functions and the three schedulers.
- `checks_revise.py` applies Design 1 and 2 to a copy of the job held in memory; the repo file is not touched. With three target dates and the read failing on the second: one row is upserted, the exception is raised as it was, and no read is made for the third. Under `run()` the watchlist stub is not called. With zero rows: one warning, one row, no `pre_` key.
- The variable-table check finds `gcp/database.py` and `scripts/archive_yahoo_data.py` and no third file.
- The dispatch scan flags six constants in two files: `gcp/discord_interactions/main.py:464` and `:470`, `scripts/backfill_and_replay.py:178`, `:180`, `:306` and `:330`. Those are the lines FEAT-REPLAY-001's guard names for the same two files.
- The review's eleven bypass cases: four are now caught by the scan (a quoted identifier, adjacent literals, `MERGE INTO`, a table name past 300 characters), three by test 4 (a writer function called from a third file, `replace_month` from a third file, the fetcher as a subprocess), one was caught before (a DELETE inside a WITH), and three are listed below as not seen (a reflected table, a DROP of a partition, a DETACH of a partition).

**What the tests do not see.**

- A table name held in a variable and passed in from another file, or a partition name built in an f-string field. Test 5 sees only a file that holds both the statement and the name.
- A reflected table: `sa.Table("market_data_intraday", ...)` and an insert built from it. No file under the scan roots holds one; the write helpers reflect by a variable.
- DDL: a `DROP TABLE` of a partition, `ALTER TABLE ... DETACH PARTITION`, and `gcp/schema.sql`, which today only creates the table, its five partitions and its index (`:140-168`). No `.py`, `.sql` or `.sh` file under the scan roots drops, alters or detaches it. `gcp/db_maintenance.py` can VACUUM, ANALYZE or REINDEX the table (`:53-56`); that changes no row.
- SQL an operator runs by hand, through `scripts/db_query_cr.sh --commit` or a `.sql` file. A search of the 70 tracked `.sql`, `.sh`, `.yml`, `.yaml` and `.disabled` files outside `archive/` and `docs/research/` found no INSERT, MERGE, COPY, DELETE, UPDATE, TRUNCATE, DROP or ALTER on the table.
- A new write helper that is not in the list.
- A writer function reached without an import the test can read: a module name built from parts, `getattr`, or a module object passed as a value.
- A job run by hand or from the console, and a scheduler made outside `gcp/deploy.sh`.
- Anything outside `gcp/`, `lib/`, `scripts/` and `platform/`.
- What the dispatch scan does not see: shell and workflow files (`gcp/deploy.sh:5429` still deploys the job), a job name built from parts, and a run started by hand.

The run-time tests of `run` (Design 1 and 2) and of the migrate script (Design 3) cover those two files directly, whatever a scan misses.

### 5. The as-traded guard and the UTC writers test

- `tests/gcp/test_intraday_as_traded.py`:
  - `test_backfill_ticker_month_fetch_requests_as_traded` (`:81-83`) and the `backfill_ticker` import (`:21`) go.
  - In `test_every_intraday_request_in_the_repo_asks_for_as_traded` the required set drops `gcp/backfill_ticker.py` and holds six files (`:142-144`), the count becomes `len(sites) >= 7` (`:145`), and a new line asserts `gcp/backfill_ticker.py` is not in the files found. The prototype's count on this branch: 8 requests in 7 files today, one of them `gcp/backfill_ticker.py:138`.
  - The file goes from 14 test cases to 13.
- `tests/gcp/test_intraday_writers_utc.py`: `test_backfill_ticker_writes_utc_instants` (`:66-94`) proved the job wrote UTC instants. It goes; the no-write test of Design 1 replaces it. The file goes from 8 test cases to 7.

### 6. Existing tests that change

| Test | Change | Why |
|---|---|---|
| `tests/gcp/test_backfill_ticker.py` `stubbed_run` (`:216-237`) | drop the `av_intraday_month` patch (`:232`) | the function is gone |
| `tests/gcp/test_backfill_ticker.py` `_backfill_premarket_row` (`:337-381`) | answer the bar read on `gcp.database.query_to_dataframe_strict`, set before `install_level_params`, which passes every other strict query to the reader already in place (`tests/lib/level_params_fixtures.py:174-181`); the daily read stays on `query_to_dataframe` | the read is strict |
| `tests/gcp/test_backfill_ticker.py` | four new tests (`done_when` items 1 to 3); 18 cases today, 22 after | new behaviour |
| `tests/gcp/test_intraday_as_traded.py`, `tests/gcp/test_intraday_writers_utc.py` | Design 5 | one request and one writer fewer |
| `tests/gcp/test_migrate_to_gcp_dispatch.py` | new file, one test | the migrate script had no test of its selectors |
| `tests/meta/test_production_writers.py` | six new tests (Design 4); its 15 cases today are unmodified, 21 after | the allowlist |
| `tests/gcp/test_migrate_trades_tz_guard.py`, `tests/gcp/test_deploy_reachability.py`, `tests/gcp/test_discord_interactions.py`, `tests/scripts/test_backfill_and_replay.py` | unmodified | they stub the job or read `gcp/deploy.sh`, which does not change |
| `tests/meta/test_timezone_boundaries.py` | unmodified, no baseline change | the baseline entries of the two files sit in functions this spec keeps (`_parse_dates`, `main`, `_normalize_av_options`, `_normalize_options_df`) |

The four existing files this spec's tests live in were run on this branch on 2026-11-13, twice: 55 passed (15, 14, 8 and 18).

### 7. Site traceability

No route, response or reader the site calls changes. What changes is the writer list of a table four pages show. `site_source_notes` cannot be widened by the implementation PR (`.claude/skills/product-delivery/references/spec-template.md:47`), so it is declared by a rule: one element per page, the first Chain row on that page of `docs/product/03-SITE-TRACEABILITY.md` whose Data cell names `backfill-ticker` or `gcp/migrate_to_gcp.py` as a writer of `market_data_intraday`.

| Page | First such row | Later rows on the page with the same writer list |
|---|---|---|
| Dashboard | DASHBOARD-04 (`:334`) | DASHBOARD-15 |
| Live Market | LIVE-08 (`:430`) | none |
| Charts | CHARTS-01 (`:506`) | CHARTS-02 to CHARTS-06, CHARTS-08 to CHARTS-12 |
| Journal | JOURNAL-01 (`:1041`) | JOURNAL-02, JOURNAL-04, JOURNAL-11, JOURNAL-13, JOURNAL-14 |

- That is four elements, sorted and unique: CHARTS-01, DASHBOARD-04, JOURNAL-01, LIVE-08. Twenty rows carry the writer list; the sixteen later ones are covered by the first row of their page, and their cells are corrected in Close-out 4.
- No other page has a row that names either writer for this table (scans `site_rows.py` and `site_rows2.py` in the scratch folders, re-run for this revision).
- Rows that name `backfill-ticker` or `gcp/migrate_to_gcp.py` as a writer of another table are not declared. Both stay writers of `market_data_daily` (14 rows name them for it), the job stays a writer of `news_sentiment`, and this spec does not change what the script writes to `trades` or to the options tables.
- DASHBOARD-01 is such a row. Its Data cell names the two as writers of `market_data_daily` (`:331`), not of this table, so the rule does not select it. The 2026-10-16 FEAT-DEPLOY-001 spec declares DASHBOARD-01 for its own change to `./gcp/deploy.sh migrate` (Risks). That is its declaration, not this one's.
- The implementation PR adds the four `(FEAT-DATA-001, component)` rows to the implementation-source notes and regenerates `docs/review-evidence/site-source-snapshot.json`. The table holds three FEAT-DATA-001 rows today (DASHBOARD-01, LIVE-03, SHARED-07; `:1303-1305`); none is one of these four.

### Capacity

Per `backfill-ticker` run, counted from the code, with the default seven dates. A round trip through pg8000 and the connector is taken at 0.5 to 2 s (CLAUDE.md rule 0). Nothing here was measured.

| | Today | After |
|---|---|---|
| AlphaVantage calls | 1 daily, 1 or 2 monthly 1-min (120 s timeout each, `:143`), 0 or 1 news | 1 daily, 0 or 1 news |
| Rows written to `market_data_intraday` | about 20,000 per month touched (960 minutes a day, about 21 sessions), in chunks of 2,000 | 0 |
| Cloud SQL round trips | about 40, plus about 10 upsert chunks per month of bars | about 40: 1 daily upsert, 5 for the full-range indicators (`:371`, `:409-419`), up to 4 per target date for up to 8 dates (daily read, bar read, level parameters, upsert), 1 news, 1 watchlist |
| Wall-clock estimate | not measured | 20 to 80 s of round trips plus the vendor's answer time; the task timeout is 600 s (`gcp/deploy.sh:1299`) |

- Volume: about 800 daily rows and up to 8 indicator rows per run, as today.
- No query text changes and no query is added, so no plan is measured before the merge.
- No new job, schedule or table. Cost: one or two fewer vendor calls and fewer writes per run; the job has no schedule, so runs per day is 0 unless an operator starts one.
- `gcp/migrate_to_gcp.py` is a manual CLI; it loses one delete and one bulk insert per ticker.
- The new tests read source files and run no query. The subprocess of `done_when` item 4 imports the script and exits in argparse.

## Close-out (after the merge, on the owner's yes)

1. **What does not apply.** `platform/api/openapi.json` does not change (no file under `platform/` is touched), so solyra needs no contract sync. No route, response or page changes, so there is no deployed-site Playwright step: at the merge the site shows what it showed.
2. **Deploy** from `main`: the jobs image for `backfill-ticker` (`./gcp/deploy.sh discord`, `gcp/deploy.sh:5429`, or the full deploy).
3. **Verify by running the job once**, results on the PR. The run calls AlphaVantage once and writes to production: it re-upserts up to 800 daily rows for the ticker and stamps them `data_source` `alphavantage` (`gcp/backfill_ticker.py:626`). So it waits for the owner's yes and for the ticker the owner names. It must be a ticker that already holds daily rows, so the run adds no ticker to `market_data_daily`; a new ticker there joins the earnings chain's nightly refresh (`gcp/fetchers/fetch_market_data.py:818-826`). `scripts/backfill_and_replay.py:22-31` names AMD, CARS, MCK and NVDA as tickers an earlier backfill path wrote; whether they hold rows today is not checked. With `BACKFILL_ADD_TO_WATCHLIST=false`, `BACKFILL_INCLUDE_NEWS=false` and one date:
   - the date is at least two calendar months back, and the run starts outside 21:00 to 23:30 ET. The nightly rewrites the previous and the current month at 21:00 ET, the daily fetcher writes its run date at 23:00 ET, and an operator's watchlist backfill writes the last days. None of them writes a month that old;
   - the check is the execution's own log. It holds the line `1-min bars are not fetched by this job; premarket context reads market_data_intraday`, which only the new code logs. It holds no `AV intraday-month` line and no `intraday bars` line; the old code logs the first once per month touched (`gcp/backfill_ticker.py:136`), before any write. For the date and for its prior weekday it shows which case held: the `pre-market` line when bars were found, the new `no 1-min bars in market_data_intraday` line when none were. A date whose bars all fail the print filter logs neither (`:536`). It ends with `backfill complete`, and the execution exits 0;
   - secondary, read-only through `scripts/db_query_cr.sh`, before and after the run: `SELECT count(*) FROM market_data_intraday WHERE ticker = '<TICKER>' AND interval = '1min' AND ts >= '<month start>' AND ts < '<next month start>'`, with the literals written in because `scripts/db_query_cr.sh` takes no bind values, for the two months the old code would have fetched, the month of the date and the month of the day four days before it (`:634-638`). What it can show: a count that is 0 before and 0 after means the run inserted no bar where the old code would have inserted the month the vendor holds; a count that rose means something wrote the month. What it cannot show: when the month was already there, equal counts do not tell the old code from the new, because the old code upserted the same keys and an upsert does not touch `inserted_at` (`gcp/database.py:483-484`). So the count never stands in for the log.
4. **Docs**, on a `docs/` branch:
   - the Data cells of the twenty rows of Design 7, which list `backfill-ticker` (Discord `/replay`) and `gcp/migrate_to_gcp.py` as unscheduled writers of the table. The implementation PR may not edit those cells;
   - `docs/product/06-DATA-ARCHITECTURE.md:26`, whose Producer cell for the table names `gcp/backfill_ticker.py`. The gate lets a feature PR change, under `docs/product/`, only its own catalog and traceability records, the model registry and the generated blocks of `05-a`, `05-c` and `05-e` (`scripts/gate/spec_gate.py:4344-4349`), so this file waits for the `docs/` branch;
   - `docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md:1234` and `:1609` (the `--table market_data_intraday` command) and `05-j-GCP_IMPLEMENTATION_STATUS.md:125`.
5. **A FEAT-DEPLOY-001 change**, not this PR and not the `docs/` branch, because `gcp/deploy.sh` is that capability's file:
   - the comment above `deploy_backfill_ticker` (`gcp/deploy.sh:1283-1293`), which says the job writes intraday bars and that Discord `/replay` triggers it;
   - the comment at `gcp/deploy.sh:5426` (`/replay -> backfill-ticker`), which FEAT-REPLAY-001's Close-out names too;
   - the re-cut of the 2026-10-16 spec with seven selectors, before it is planned (Risks). `migrate()` itself needs no edit: it passes its arguments through.

## Risks

- Order. This plan opens after the implementation of FEAT-REPLAY-001 is on `main` (the owner's order: that spec, then this one, then the loader half). No code is shared. The reason is behaviour: until then `/replay` and `scripts/backfill_and_replay.py` dispatch this job and expect bars and premarket fields from it, and with this change alone a replayed brief for a new ticker would run on daily rows with no premarket snapshot and say nothing. `test_no_code_dispatches_backfill_ticker` fails until both dispatches are gone, so this PR cannot go green in the wrong order.
- Tickers other than SPY, QQQ and IWM. The job no longer makes a ticker replayable. Bars arrive only through the two fetcher modules, by the eight entry points of Design 4. For a ticker the nightly does not pull, the operator's paths are the watchlist backfill for the last days and the monthly fetcher run by hand for older months. The owner accepted this on 2026-11-13.
- The Admin refresh of `market_data_daily` is one of the eight. It runs the daily fetcher's job as deployed, which also writes that day's 1-min bars. It is an admin's explicit run of the scheduled job, not a replay, and this spec does not change it. Whether it is used, and how often, is not checked.
- Bars the job wrote in the past stay in the table and are not marked. `data_source` is `alphavantage` for every writer, so nothing tells them apart.
- Premarket fields for a backfilled ticker stay empty until the table has its bars. The log line says so per date and `test_premarket_absent_bars_says_so` pins it.
- An outage is louder, and it stops the run where it happens. A failed bar read now ends the run non-zero where it wrote a row without premarket fields. The rows of the dates before it stay, the failing date and the later dates get no row, and the watchlist row is not written (Design 2). A second run of the same command converges, because every write is an upsert. `--max-retries 0` means one failure, not two. `test_premarket_read_failure_fails_the_run` pins each of these.
- Two swallows stay in the job: the daily reads (`:371`, `:439`) and the compute `except` (`:557-558`). An outage that hits the daily read first is still logged as `insufficient daily history`. Both are named in Non-goals and marked in the code; `test_premarket_compute_defect_is_still_a_warning` pins the second so it cannot widen unnoticed.
- `docs/superpowers/specs/2026-11-11-feat-option-001-options-mutation-retirement.md` is a draft on `main` with no plan. It touches the same script three ways.
  - Selectors. Its `done_when` names eight `--table` selectors, `market_data_intraday` among them, and a dispatch test for that selector (`:9`), and its Design keeps all eight keys (`:98`). After this spec there are seven. That draft has to say seven before it is approved. If it is implemented first, this PR edits its two tests (`test_parser_grammar_unchanged`, `test_supported_paths_still_dispatch`) and takes the selector out of the help text it adds.
  - The call without `--table`. It deletes the no-table SQL branch and makes that call return 2 unless `--skip-sql` is passed, a call with only `--data-dir` included (`:8`, `:99-102`). This spec's `done_when` item 4 asserts nothing about that call, so both sets of tests hold in either merge order. What item 4 asserts, the absent selector, the argparse refusal, the seven function names and the `--table trades` dispatch, is true before and after that draft.
  - Both specs remove the call at `gcp/migrate_to_gcp.py:819`; that overlap is a text merge.
- `docs/superpowers/specs/2026-11-13-feat-data-001-watched-ticker-ingest.md` (approved, plan `ready`, not implemented) does not conflict. Its job writes daily bars and `ticker_info` only (`:95-96`), so the new file `gcp/fetchers/fetch_watched_tickers.py` is not a writer of this table and the allowlist does not list it. If it ever wrote bars, `test_only_the_two_fetchers_write_one_minute_bars` would fail naming it. If it imports a function of the daily fetcher's writer closure, runs that module, or names its job in a string, test 4 of Design 4 fails naming it, and that PR lists the new entry point. It edits `gcp/fetchers/fetch_market_data.py` (`_run_backfill`, `_backfill_targets`), which this spec does not touch and which reach no bar write.
- `./gcp/deploy.sh migrate`. Today `./gcp/deploy.sh migrate --table market_data_intraday` reads three secrets (`cloud-sql-connection-name`, `db-trading-user`, `db-trading-pass`, `gcp/deploy.sh:69-76`) and runs the loader. After this change the same command prints the project and region lines and `Running data migration...`, reads the same three secrets, then `python gcp/migrate_to_gcp.py` exits 2 with argparse's `invalid choice` and the script exits 2 (`set -euo pipefail`, `:23`). Run on 2026-11-13 with a stub `gcloud` and a selector argparse does not know: exit 2, three secret reads, that message. That is loud. `./gcp/deploy.sh migrate` with no selector no longer loads bars and prints no line about it. Two guides still show the selector until Close-out 4.
- This spec narrows the approved `docs/superpowers/specs/2026-10-16-feat-deploy-001-av-options-legacy-dispatch-retirement.md` (FEAT-DEPLOY-001, no plan on `main`). It fixes a shell grammar for `./gcp/deploy.sh migrate` with eight selectors, `market_data_intraday` among them and among its four supported non-options SQL selectors (`:39`), a matrix row and a test matrix over each current selector (`:55`, `:79`) and a capacity line of eight (`:87`), and it says a selector change must update that contract through a compatible spec (`:39`). Here the selector ends: seven selectors after this change, three supported non-options SQL selectors (`market_data_daily_av`, `daily_indicators`, `trades`), and `market_data_intraday` gone from the supported list and from its matrix. `supersedes` stays null: the gate allows it only within one FEAT (`check_supersedes`, `scripts/gate/spec_gate.py`), that spec is FEAT-DEPLOY-001's, and no plan on `main` names it. That spec is re-cut before it is planned (Close-out 5). Its DASHBOARD-01 declaration is not affected (Design 7).
- The scans read source text. Their limits are in Design 4. The run-time tests of `run` and of the migrate script do not depend on them.
- Test 4 of Design 4 reads `gcp/deploy.sh`. A FEAT-DEPLOY-001 change that adds a job or a scheduler for a writer module fails it until the entry point is listed. That is the point of the list.
- This spec narrows one sentence of the approved `docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md` (`:459`: it lists the `gcp/backfill_ticker.py` minute publication and the `gcp/migrate_to_gcp.py` minute upload among the writers to move to a journal). Here those two writers end. `supersedes` stays null (the owner's decision): superseding would retire all 602 lines of that spec for one sentence, no plan on `main` names it, and the test file its `done_when` names for these writers (`tests/gcp/test_av_legacy_writer_retirement.py`) does not exist. If that spec is ever planned, it is re-cut first.
- Not checked: production data (whether the table holds a row with a NULL or Yahoo `data_source`, and which tickers hold daily rows), the live jobs, schedulers and their arguments (read from `gcp/deploy.sh`, not from GCP), the wall-clock of a run, GitHub issues (`issues` is empty because no network call was allowed), the text FEAT-OPTION-001's draft will have when it is approved, and the canvases (`canvases` is empty; the artifacts were not opened).
