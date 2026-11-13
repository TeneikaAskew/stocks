---
feat_id: FEAT-REPLAY-001
req_ids: [REQ-DATA-001, REQ-REPLAY-001]
issues: []
canvases: []
site_source_notes: [CHARTS-02, CHARTS-03, CHARTS-08, JOURNAL-04]
done_when:
  - "tests/gcp/test_discord_interactions.py::test_replay_says_the_table_has_no_bars_and_starts_nothing passes: with gcp.database.query_to_dataframe_strict stubbed to return zero rows, handle_replay('AMD', '2026-04-24', ...) returns a message that names market_data_intraday, AMD and 2026-04-24, for refresh False and for refresh True, and execute_cloud_run_job is called zero times; the one query it ran names market_data_intraday and interval = '1min' and is bound to ticker AMD and the window 2026-04-17 00:00 UTC to 2026-04-24 00:00 UTC; it ran before _brief_row_exists"
  - "tests/gcp/test_discord_interactions.py::test_replay_reports_a_database_error_and_starts_nothing passes: when the probe query raises sqlalchemy OperationalError, and when is_cloud_sql_configured() is False, handle_replay returns a message that says the table could not be read, holds no driver text, and execute_cloud_run_job is called zero times (on main the first case dispatches backfill-ticker and the second dispatches the brief and the insight)"
  - "tests/gcp/test_discord_interactions.py::test_replay_with_bars_runs_the_probe_once_then_dispatches passes for a weekday, for a Sunday and for today: the probe runs exactly once with the 7-day window before that date, then premarket-brief and insight-pipeline are dispatched with the env they get today; with both stored rows present and refresh False the two render-existing jobs are dispatched instead; no reply mentions a backfill"
  - "tests/scripts/test_backfill_and_replay.py::test_main_refuses_dates_the_table_does_not_hold and ::test_no_backfill_step_remains pass: main() for --dates 2026-04-24,2026-04-27 with a stubbed connection that holds bars only before 2026-04-27 exits non-zero with a message naming AMD, 2026-04-24 and market_data_intraday, and _execute_job is called zero times; the module defines no trigger_backfill_ticker and no _month_groups, and argparse rejects --skip-backfill, --history-days, --include-news and --news-window-days"
  - "tests/api/test_platform_api.py::TestMarketDataAPI::test_market_data_404_names_the_table_and_never_reads_the_bucket passes: with _CLOUD_SQL True and the bars query returning zero rows, GET /api/market/data/IWM/20260220 answers 404 with detail exactly 'No 1-min bars for IWM on 20260220 in market_data_intraday.', and a recorder in place of every api.gcs_reader function saw zero calls (on main the bucket is probed three times, the yearly daily parquet included)"
  - "tests/api/test_platform_api.py::TestMarketDataAPI::test_market_data_database_failure_is_503_not_a_bucket_read passes: with gcp.database.query_to_dataframe_strict raising a driver OperationalError the route answers 503 with detail exactly 'Could not read 1-min bars for IWM on 20260220: the database is unavailable.', no driver text, zero bucket calls; with the query raising KeyError the route answers 500 (on main both cases answer 404 or serve a bucket file with 200)"
  - "tests/api/test_platform_api.py::TestMarketDataAPI::test_market_data_local_dev_reads_the_bucket_only_without_cloud_sql passes: with _CLOUD_SQL False a minute parquet in the stubbed bucket gives 200, a missing one gives 404, and the path data/{ticker}/{ticker}_{year}.parquet is never probed in either case"
  - "tests/api/test_platform_api.py::TestReferenceAPI passes with three new cases: for a date two days ago the answer is 200 with source 'cloud_sql' from exactly one query (market_data_daily, LIMIT 5) whose rows also give week, an httpx.Client recorder saw zero calls, and api.main has no _fetch_av_daily_reference, AV_API_KEY or AV_BASE; zero rows gives 404 with detail exactly 'No daily bar for IWM before 20200316 in market_data_daily.' and zero bucket calls; a driver OperationalError gives 503 with detail exactly 'Could not read reference levels for IWM before 20200316: the database is unavailable.' (on main: two queries, a bucket listing, and 404 for the outage)"
  - "tests/lib/test_replay_labeled_trades.py::test_replay_trades_outage_is_503 and tests/lib/test_style_walk_forward.py::test_mine_and_validate_outage_is_503 pass: a driver OperationalError from the journal query (through gcp.database.query_to_dataframe_strict) or from _replay_bar_loader gives 503 with the detail of Design section 6, and no user_style_results or playbook_cards_staging write (on main the journal outage reads as 404 'no matching trades found' or as 'need >= 10 closed trades, have 0', and the bar outage is an unhandled 500); the existing cases for a date with no bars still pass unchanged"
  - "tests/api/test_route_coverage.py passes with /api/market/data/{T}/{D} and /api/market/reference/{T}/{D} pinned at 503 (404 on main, lines 403 and 404) and POST /api/style/mine-and-validate pinned at 503 (200 on main, line 274)"
  - "python scripts/export_openapi.py --check and tests/api/test_openapi_snapshot.py pass after platform/api/openapi.json is regenerated, and tests/api/test_openapi_snapshot.py::test_replay_routes_document_their_error_responses passes: the snapshot lists 404 and 503 with schema ErrorDetail on the two GET routes and 503 with schema ErrorDetail on the two POST routes (on main each of the four lists only 200 and 422)"
  - "tests/meta/test_production_writers.py::test_replay_paths_reach_no_vendor_or_bucket_bar_fetch passes: for every file and entry function in REPLAY_PATH, the functions reachable inside that file hold no AlphaVantage TIME_SERIES request, no call to a function that holds one anywhere in gcp/, lib/, scripts/ or platform/api, no api.gcs_reader use outside the two local-dev functions, and no 'backfill-ticker' string (on main it fails at gcp/discord_interactions/main.py:464, scripts/backfill_and_replay.py:180 and platform/api/main.py:242, :1116, :1170, :1703, :1704); ::test_local_dev_bucket_reads_sit_behind_the_cloud_sql_check passes"
  - "tests/meta/test_production_writers.py::test_every_replay_entry_point_is_registered passes, and ::test_the_replay_guard_catches_the_obvious_rewrites shows the two guards reject, each on a small source snippet: a fifth Discord handler that dispatches a job, an unregistered job name, a new file that reads an env var or flag matching REPLAY, AS_OF, --as-of, BACKTEST_ or VALIDATE_, a new platform/api caller of _load_date_data, a TIME_SERIES_DAILY dict in a helper an entry point calls, a gcs_reader call outside the local-dev functions, and a local-dev call that is not under 'if not _CLOUD_SQL'"
  - "EXPLAIN (ANALYZE, BUFFERS) of the probe query, run read-only through scripts/db_query_cr.sh for SPY with the latest session as D and for a ticker with no rows, is pasted on the PR with both execution ids: each plan is an index scan that reads at most 10 rows; a plan that reads more blocks the merge"
  - "make test passes on the PR head; the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes"
  - "02-FEATURE-CATALOG FEAT-REPLAY-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the four (FEAT-REPLAY-001, component) rows are in the implementation-source notes of 03-SITE-TRACEABILITY.md with docs/review-evidence/site-source-snapshot.json regenerated, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# Replays on Discord and the API read bars from the table or say they cannot

## Problem

The owner's rule, 2026-11-13: every replay reads 1-minute bars only from the store the nightly pull fills, the Cloud SQL table `market_data_intraday` (interval `1min`). No replay fetches bars from AlphaVantage or anywhere else. When the table does not have the ticker or the day, the replay says so. Read at `main` 8712afb6:

- Discord `/replay` starts a vendor fetch. `handle_replay` (`gcp/discord_interactions/main.py:389`) asks `ticker_has_daily_data` (`:322-338`), which reads `market_data_daily`, and when that finds nothing it runs the `backfill-ticker` job and waits up to 540 s (`:454-472`). That job pulls 1-min bars from AlphaVantage and writes them to the table (`gcp/backfill_ticker.py:134-161`, `:633-656`).
- A database error starts the same fetch. `ticker_has_daily_data` calls `query_to_dataframe`, which returns an empty frame on any error (`gcp/database.py:218-241`), so an outage reads as "no data". Run on 2026-11-13 with `get_engine` raising: it returned False. With Cloud SQL not configured it returns True (`:329-330`) and the brief and the insight are dispatched unchecked.
- `/replay` never looks at `market_data_intraday`. No line of the Discord module names the table.
- `scripts/backfill_and_replay.py` runs `backfill-ticker` before every replay unless `--skip-backfill` is passed (`:167-192`, `:322-330`).
- `_load_date_data` (`platform/api/main.py:1623-1724`) feeds `GET /api/market/data/{ticker}/{date}` (`:933`), `POST /api/backtest/replay-trades` and the per-trade bars of `POST /api/style/mine-and-validate` (`platform/api/routers/backtest.py:477-483`, `:586`, `:751`). It reads the table through the swallowing `query_to_dataframe` (`:1642`, `:1661`), then falls to bucket parquet on zero rows or on an error (`:1698-1722`), last of all a yearly file of daily bars (`:1719-1722`). Run on 2026-11-13 through the real route:
  - database down, a minute parquet in the bucket: 200 with the bucket's bars.
  - zero rows in the table, only the yearly file in the bucket: 200 with `count` 1, one daily bar drawn as a 1-min candle.
- `GET /api/market/reference/{ticker}/{date}` (`:1089-1232`) calls AlphaVantage `TIME_SERIES_DAILY` for any date under 30 days old (`:228-266`, `:1114-1127`), then the daily table through the swallowing helper (`:1130-1164`), then a bucket listing (`:1166-1222`). Run the same day: a recent date called AlphaVantage once; an old date with the database down answered 404 `Date 20200316 not found for SPY`.
- `replay-trades` and `mine-and-validate` read the journal through the swallowing helper too (`backtest.py:486-490`), so an outage reads as "no matching trades found" (`:553`) or "need >= 10 closed trades, have 0" (`:732-736`). The docstring promises a loud failure (`:516-518`).
- `GET /api/market/dates/{ticker}` is already right: 503 on a database error, the bucket only when Cloud SQL is not configured (`platform/api/main.py:854-930`; `tests/api/test_platform_api.py:723`, `:759`).
- These tests pin the wrong behaviour: `tests/gcp/test_discord_interactions.py:429`, `:447`, `:481`; `tests/scripts/test_backfill_and_replay.py:61-117`; `tests/api/test_platform_api.py:846`, `:980`; `tests/api/test_route_coverage.py:403-404`.

## Non-goals

- `backfill-ticker` itself, the loader `lib.data_loader.DataLoader` and every job that reads through it (`/backtest`, the style history, the end-of-day resolver, the research jobs). That is a second spec under FEAT-DATA-001, drafted and not yet on `main`.
- No bucket copy of the bars is designed or read.
- No change to which tickers the nightly pulls, to `/validate` or `/replay-signals` (the first already reads only the table and prints `NO INTRADAY DATA` when it is empty, `scripts/validation/validate_brief_accuracy.py:166-205`, `:457-458`; the second re-posts stored `signal_alerts`, `gcp/signal_replay.py:108-124`), or to what the brief and the insight compute.
- No change to `gcp/deploy.sh`. It is owned by FEAT-DEPLOY-001, so the `discord` target keeps deploying `backfill-ticker` (`:5429`) and its comment (`:5426`) goes stale until a FEAT-DEPLOY-001 change.
- No change to `stale_days` on the reference answer, to `GET /api/market/dates`, or to the live routes under `/api/live`.
- No solyra change. The frontend work is a later solyra spec (Close-out).
- No trading cost appears anywhere.

## Approaches considered

1. The table or an explicit answer, on every replay surface, held by a guard (chosen). It is the owner's rule, it matches what `/api/market/dates` already does, and a status code is enough for the frontend to tell "not in the table" from "database down".
2. Keep the fallbacks and label them with a `source` field. Rejected: CLAUDE.md 3.7.1, no frontend code reads the field, and the yearly file serves daily bars as minute bars.
3. Keep the on-demand backfill but route it through the nightly fetcher. Rejected by the rule: a replay does not fetch.

## Design

### 1. What "the table has bars for a replay of D" means

What each job a replay starts actually reads:

| Surface | Job | Reads for date D | Reads `market_data_intraday` |
|---|---|---|---|
| `/replay` | `premarket-brief`, `BRIEF_AS_OF=D` | daily rows dated before D (`gcp/premarket_brief.py:991-1008`, `:1357-1362`) and D's premarket snapshot on the daily row (`:1354`) | no |
| `/replay` | `insight-pipeline`, `INSIGHT_AS_OF` | `market_data_daily` (`lib/agents/summarizers.py:229`, `:609`) | no |
| `/replay`, cached | the two render-existing jobs | stored `premarket_analysis` and `insight_reports` rows | no |
| `/replay-signals` | `signal-replay` | stored `signal_alerts` | no |
| `/validate` | `validate-brief` | D's own session bars | yes, D |
| `/backtest` | `backtest` | the window asked | yes, the window (second spec) |
| `REPLAY_DATE` | `signal-monitor` replay | D's own bars (`scripts/replay_signal_monitor.py:101-127`) | yes, D; Discord does not start it |

- So `/replay` reads no 1-min bar. The brief and the insight replay the morning of D, from data before D. The check on the table is a coverage gate: is this ticker, around this day, something the nightly pull holds.
- Rule: the table has bars for a `/replay` of D when it holds at least one `1min` row for the ticker with `ts` in `[D - 7 days 00:00 UTC, D 00:00 UTC)`.
- Why before D and not D itself: D's own bars are not an input; today's bars only land at 21:00 ET (`gcp/deploy.sh:4741`), and a Sunday date is a valid weekly brief (`gcp/premarket_brief.py:1296`) with no bars of its own. A D-itself rule would refuse both.
- Why raw UTC bounds: the table holds two timestamp conventions (CLAUDE.md 3.9). `D 00:00 UTC` is before any bar of D and after the regular session of D-1 in both.
- Why 7 days: it spans any weekend plus holidays.

### 2. Discord `/replay`

- New `replay_bars_in_table(ticker: str, d: date) -> bool` in `gcp/discord_interactions/main.py`. One query through `gcp.database.query_to_dataframe_strict` with `timeout_s=10`:
  `SELECT 1 FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :lo AND ts < :hi LIMIT 1`.
  It raises when `is_cloud_sql_configured()` is False and lets a query error propagate.
- The window comes from `lib.eastern_time.replay_probe_window(d) -> (lo, hi)`, new, beside the helpers that read the table across the two conventions (`lib/eastern_time.py:187`).
- `handle_replay` calls it first, after the date parses and before the cached path:
  - False: reply `No replay for {T} on {D}: market_data_intraday has no 1-min bars for {T} in the 7 days before {D}. Nothing was fetched and no job was started.` Dispatch nothing.
  - raises: log the exception, reply `Could not read market_data_intraday for {T}: the database did not answer. No job was started. Try again in a minute.` Dispatch nothing.
  - True: the cached path (`:422-450`) and the recompute path (`:474-513`) run as today.
- Removed: `ticker_has_daily_data`, `execute_cloud_run_job_blocking` (its only caller is the backfill, `:464`), the backfill block and `backfill_msg`.
- A ticker with 1-min bars and no daily rows gets the brief's own `NO DATA` status (`gcp/premarket_brief.py:992-994`), as today.

### 3. `scripts/backfill_and_replay.py`

- Step 1 goes: `trigger_backfill_ticker`, `_month_groups`, `DAILY_HISTORY_DAYS` and the flags `--skip-backfill`, `--history-days`, `--include-news`, `--news-window-days`. argparse then rejects them, which is the loud answer.
- New `missing_replay_dates(conn, ticker, dates) -> list[date]`: the same probe per date on the script's own connection (`db_connect`, `:108`), with `replay_probe_window`. `main` opens the connection first, exits non-zero naming the ticker, the missing dates and the table, and starts no job when the list is not empty. A query error propagates.
- `--skip-replay` stays and means "report only". The file keeps its name; the docstring says what it now does.

### 4. `_load_date_data` and `GET /api/market/data/{ticker}/{date}`

- New `_bars_query(sql, params)` in `platform/api/main.py`, a deferred call to `gcp.database.query_to_dataframe_strict`, like `_dates_query` (`:623-632`).
- `_load_date_data(ticker_lower, date)`:
  - `_CLOUD_SQL` False: `return _bars_from_gcs_local_dev(ticker_lower, date)`. That new function holds today's minute-file and month-file reads (`:1709-1717`) and raises `FileNotFoundError` when neither exists. The yearly probe (`:1719-1722`) is deleted.
  - `_CLOUD_SQL` True: the same two SELECTs (`:1642-1678`) through `_bars_query`, the same conversion and Eastern cut (`:1681-1694`). The `try/except` around them (`:1633`, `:1695-1696`) goes, so an error propagates. Zero rows after the cut, or a date that is not 6 or 8 digits, raises `FileNotFoundError("No 1-min bars for {T} on {date} in market_data_intraday.")`.
- `get_market_data` keeps `FileNotFoundError -> 404` (`:952-953`) and adds `except Exception as exc: unavailable("Could not read 1-min bars for {T} on {date}: the database is unavailable.", exc)` (`platform/api/http_errors.py`: 503 for an outage, the exception re-raised as a 500 for a defect). Its two later empty-frame 404s (`:956`, `:1002`) use the same not-in-the-table text. The `end_time` 404 (`:1018`) keeps its own text.

### 5. `GET /api/market/reference/{ticker}/{date}`

- `_CLOUD_SQL` False: `return _reference_from_gcs_local_dev(ticker, date)`, today's bucket branch (`:1166-1232`) moved into one function, unchanged.
- `_CLOUD_SQL` True: one query through new `_daily_reference_query` (strict):
  `SELECT date, open, high, low, close, rsi_14 FROM market_data_daily WHERE ticker = :ticker AND date < :dt ORDER BY date DESC LIMIT 5`.
  - The first row is the reference day. `week` is built from the same rows with today's rule: null under two rows (`:1066-1067`). This is the same data the two queries of today return (`:1057-1065`, `:1132-1140`).
  - Zero rows: 404 `No daily bar for {T} before {date} in market_data_daily.`
  - An error: `unavailable("Could not read reference levels for {T} before {date}: the database is unavailable.", exc)`.
  - `source` is always `cloud_sql`. `stale_days` keeps today's rule (`:1146-1155`).
- Deleted: `_fetch_av_daily_reference`, `AV_API_KEY`, `AV_BASE` (`:222-266`; nothing else in the module uses them), `_fetch_week_range` (`:1047-1086`) and the `httpx` import (`:14`; its only use is `:240`).

### 6. `POST /api/backtest/replay-trades` and `POST /api/style/mine-and-validate`

- `_replay_journal_query` (`backtest.py:486-490`) forwards to `gcp.database.query_to_dataframe_strict`.
- Both handlers wrap the journal read and the bar loop: an exception other than `FileNotFoundError` goes to `unavailable("Could not read 1-min bars for {T}: the database is unavailable.", exc)` for the bar loop and `unavailable("Could not read journal trades for {T}: the database is unavailable.", exc)` for the journal read.
- A date with no bars stays as it is: `FileNotFoundError` is caught (`:586-589`, `:751-754`) and that date's trades come back `unavailable` (`lib/backtest.py:986`, `:941-946`).

### 7. Response contract the frontend receives

Every error body is `{"detail": "<string>"}`. solyra already reads `detail` as a string (`src/hooks/useMarketData.ts:42-43`, `src/hooks/useJournalChartTrades.ts:591`, `:764`), so the status code carries the meaning and `detail` is for display.

| Endpoint | Not in the table | Database unavailable |
|---|---|---|
| `GET /api/market/data/{ticker}/{date}` | 404, `No 1-min bars for {T} on {date} in market_data_intraday.` | 503, `Could not read 1-min bars for {T} on {date}: the database is unavailable.` |
| `GET /api/market/reference/{ticker}/{date}` | 404, `No daily bar for {T} before {date} in market_data_daily.` | 503, `Could not read reference levels for {T} before {date}: the database is unavailable.` |
| `POST /api/backtest/replay-trades` | 200; each trade on that date is `{"id": ..., "status": "unavailable", "reason": "no bars for date"}` (unchanged) | 503, `Could not read 1-min bars for {T}: the database is unavailable.` or `Could not read journal trades for {T}: the database is unavailable.` |
| `POST /api/style/mine-and-validate` | 200; dates with no bars are left out of the mining, and if no profile clears: `{"status": "unavailable", "reason": "no condition profile cleared the mining threshold for either direction"}` (unchanged) | 503, same two texts |

- `{T}` is the ticker in upper case; `{date}` is the path value as sent.
- The walk-forward history read of `mine-and-validate` is the second spec; its not-in-the-table answer is also a 200 with `status` `unavailable`.
- A defect (not an outage) stays a 500.
- `platform/api/schemas.py` gains `class ErrorDetail(ApiModel): detail: str`. The four routes declare `responses={404: {"model": ErrorDetail}, 503: {"model": ErrorDetail}}` (the two POST routes 503 only). `platform/api/openapi.json` is regenerated with `python scripts/export_openapi.py`.

### 8. The guard (`tests/meta/test_production_writers.py`, extended)

- `REPLAY_PATH`, a dict of file to entry functions (`"*"` is the whole file):
  - `gcp/discord_interactions/main.py`: `handle_replay`, `handle_replay_signals`, `handle_validate`, `handle_backtest`.
  - `platform/api/main.py`: `get_market_data`, `get_reference_levels`, `_load_date_data`. `platform/api/routers/backtest.py`: `replay_trades`, `mine_and_validate`.
  - `gcp/signal_monitor.py`: `update_window`, `calculate_indicators`, `evaluate_ticker`, `_evaluate_strategies_for_bar`, `fire_alert`, `refresh_level_map` (what the replay harness drives; the live poll `fetch_latest_bar` is outside).
  - Whole files: `scripts/backfill_and_replay.py`, `scripts/replay_signal_monitor.py`, `gcp/signal_replay.py`, `gcp/validate_brief_job.py`, `scripts/validation/validate_brief_accuracy.py`, `gcp/backtest_job.py`, `scripts/run_backtest.py`, `gcp/premarket_brief.py`, `gcp/insight_pipeline_job.py`, `gcp/insight_discord_push.py`, `gcp/earnings_reactions_brief.py`, `gcp/indicator_correlation_job.py`, `gcp/regime_combo_job.py`, `gcp/research/strat_engine/strat_pred_serve.py`, `scripts/analysis/per_ticker_calibration.py`, `scripts/analysis/phase6_playbook.py`, `scripts/calibrate_thresholds.py`, `lib/exec_backtest/cli.py`.
- The reach test, by `ast`: from each entry function, follow calls and names to functions defined in the same file. In what is reached, none of:
  - a dict literal whose `function` value starts with `TIME_SERIES_`, or a string holding `function=TIME_SERIES_`;
  - a call to any function, anywhere in `gcp/`, `lib/`, `scripts/` or `platform/api`, whose body holds such a request (18 today), or to a same-file caller of one;
  - `gcs_reader.<anything>`, except inside `_bars_from_gcs_local_dev` and `_reference_from_gcs_local_dev`;
  - the string `backfill-ticker`.
- The local-dev test: every call of those two functions sits inside `if not _CLOUD_SQL:`. The API tests of `done_when` prove the same at run time.
- The registration test fails when any of these is not in `REPLAY_PATH` (or, for a job name, in `DISCORD_JOBS`, which maps each of the six job names to its registered module):
  - a function in the Discord module that calls `execute_cloud_run_job`;
  - a job name passed to it;
  - a file under `gcp/`, `scripts/`, `platform/api` or `lib/` that reads an env var or declares a flag matching `REPLAY`, `AS_OF`, `--as-of`, `--replay`, `BACKTEST_` or `VALIDATE_TICKER|DATE` (16 files today, all listed above);
  - a function under `platform/api` that calls `_load_date_data`, `_replay_bar_loader` or `_style_history_bar_loader`.
- A prototype of the reach test was run on `main`: it flags exactly the seven lines named in `done_when` and nothing in the other 19 files.
- What it does not see: a fetch reached through another file by a name it cannot resolve, a request built without a dict literal, the parquet and daily-bar fallbacks inside `DataLoader` (the second spec adds them), and a job started by hand.

### 9. Existing tests that change

| Test | Change | Why |
|---|---|---|
| `tests/gcp/test_discord_interactions.py:429`, `:447`, `:481` | deleted | they pin the backfill dispatch |
| same file, 7 tests that patch `ticker_has_daily_data` or rely on its unconfigured `True` (`:323`, `:353`, `:391`, `:414`, `:868`, `:910`, `:943`) | patch `replay_bars_in_table` instead | the old function is gone |
| `tests/scripts/test_backfill_and_replay.py:61`, `:71`, `:80`, `:87`, `:104` | deleted; `:148` and `:163` drop `--skip-backfill` (`:158`, `:173`) and stub the probe | they pin the dispatch |
| `tests/api/test_platform_api.py` `_patch_intraday` (`:658`) and `tests/api/test_intraday_loader_conventions.py:120`, `:213`, `:286` | patch `_bars_query` | the loader no longer calls `query_to_dataframe` |
| `tests/api/test_platform_api.py:846` | replaced by the 404 test of `done_when` | it stubs the bucket fall-through |
| `tests/api/test_platform_api.py:980`, `:1004`, `:1032`, `:2155-2167` | `:980` replaced; the others feed one LIMIT 5 frame through `_daily_reference_query` | one query, no AlphaVantage |
| `tests/api/test_route_coverage.py:274`, `:403`, `:404`, `:675` | 503; the `api.main` `AV_API_KEY` entry goes | outage is no longer a 404 or a 200 |

### 10. Site traceability

The change reaches the site through the market data, reference, scorecard and style routes. The implementation PR adds the `(FEAT-REPLAY-001, CHARTS-02)`, `(..., CHARTS-03)`, `(..., CHARTS-08)` and `(..., JOURNAL-04)` rows to the implementation-source notes of `docs/product/03-SITE-TRACEABILITY.md` and regenerates `docs/review-evidence/site-source-snapshot.json`.

### Capacity

Queries per request or per command. None grows.

| Surface | Today | After |
|---|---|---|
| `/replay` | 1 probe on `market_data_daily`, up to 2 stored-row probes, and for an unknown ticker a blocking job of up to 540 s with 3 to 4 AlphaVantage calls | 1 probe on `market_data_intraday` (LIMIT 1 on `idx_market_data_intraday_lookup`, `gcp/schema.sql:167-168`), the same stored-row probes, no job |
| `scripts/backfill_and_replay.py` | 1 `backfill-ticker` execution per month of dates | 1 probe per date |
| `GET /api/market/data` | 1 SELECT, then up to 3 bucket reads on a miss or an error | the same 1 SELECT |
| `GET /api/market/reference` | recent date: 1 AlphaVantage call (8 s timeout) and 1 SELECT; older date: 2 SELECTs; then a bucket listing on a miss | 1 SELECT of at most 5 rows |
| `replay-trades`, `mine-and-validate` | 1 journal SELECT, 1 bars SELECT per distinct entry date, bucket reads on a miss | the same SELECTs |

- The probe's latency is not measured here. It is a `done_when` measurement. CLAUDE.md 3.9 records 10.8 ms for the `MAX(ts)` probe on the same index.
- No new job, schedule or write. Cost change: fewer AlphaVantage calls and fewer job minutes.

## Close-out (after the merge, on the owner's yes)

1. **Deploy** from `main`: the `discord-interactions` service and the API.
2. **Verify** on staging, results on the PR: `/replay` for a ticker the table does not hold replies with the not-in-the-table text and Cloud Run shows no `backfill-ticker` execution; `GET /api/market/data/SPY/{a session}` is 200 and `/api/market/data/SPY/20100104` is 404 with the new text; `GET /api/market/reference/SPY/{today}` is 200 with `source` `cloud_sql`.
3. **solyra spec**, separate: `npm run contract:sync`; show 404 as "not in the table" and 503 as "unavailable" on `useMarketData`, `useReferenceLevels`, `useReviewQuote`, `useHistoricalDay`, `useReplayTrades` and `useMineMyStyle`; limit the `ReplayControl` calendar to the dates `GET /api/market/dates` lists (today it blocks only weekends and holidays, `src/components/shared/ReplayControl.tsx:115-118`); mocks and fixtures for both states; a `*.cloud.spec.ts` the owner runs against the deployed site.
4. **Docs**, on a `docs/` branch: `docs/product/infrastructure/05-a-ARCHITECTURE.md:788` still says `/replay` dispatches `backfill-ticker`; `gcp/deploy.sh:5426` says the same and waits for a FEAT-DEPLOY-001 change.

## Risks

- A ticker with no bars on Discord. `/replay` for a ticker outside the nightly's set used to work after one to two minutes of backfill. It now answers at once that the table has no bars. The way in is `/watchlist add`: both nightly pulls read the watchlist (`gcp/fetchers/fetch_alphavantage_intraday.py:45-52`, `gcp/fetchers/fetch_market_data.py:1220-1221`), from the first of the previous month onward. Older dates stay refused. The reply does not promise a date.
- Tickers other than SPY, QQQ and IWM. On-demand onboarding through `/replay` ends for all of them. Charts, the scorecard and style mining already depended on the table for them; they lose only the bucket fall-through.
- Local development without Cloud SQL. The API keeps its bucket branch when Cloud SQL is not configured, so a laptop with bucket access still draws charts; the yearly daily file is gone there too. `/replay` and `scripts/backfill_and_replay.py` need a database and say so. `done_when` covers both API modes.
- Reference levels lose the vendor's fresher answer. If the nightly daily fetch misses a day, the route returns the latest stored day, with `stale_days` set when the request is under 30 days old and that day is over 3 calendar days back; after a long weekend that flag can be set for a correct row. Nothing in solyra renders `stale_days` today.
- The 7-day rule passes a date whose own day the table lacks (a gap day, or today before 21:00 ET). That is intended for `/replay`; `/validate` reads D itself and reports `NO INTRADAY DATA`.
- An outage now answers 503 where it answered 404 or 200. The frontend shows its error state until the solyra follow-up words it. `tests/api/test_route_coverage.py` pins the new codes.
- The reach test follows names inside one file. A fetch moved behind a new helper in another file is caught only when the helper itself holds the request or the registration test sees the new entry point. The limits are listed in Design 8.
- This spec narrows one sentence of the approved `docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md` (`:467`: `_load_date_data` "SQL AND local/GCS fallbacks use the atomic guard/evidence contract"). With Cloud SQL configured there is no fallback left to guard. It does not supersede that spec: the gate allows `supersedes` only within one FEAT, that spec belongs to FEAT-DATA-001, no plan on `main` names it, and the two test files its `done_when` names for the replay routes (`tests/api/test_av_price_replay_routes.py`, `tests/scripts/test_av_price_replay_entrypoints.py`) do not exist.
