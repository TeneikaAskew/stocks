---
feat_id: FEAT-REPLAY-001
spec: docs/superpowers/specs/2026-11-13-feat-replay-001-replay-bars-from-the-table.md
branch: fix/feat-replay-001-replay-bars-from-the-table
pr: 1891
status: ready
---

# Replays on Discord and the API read bars from the table or say they cannot: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [17].

**Goal:** `/replay`, `scripts/backfill_and_replay.py` and the four API replay routes read bars only from the Cloud SQL tables, start no fetch, and say plainly when the table lacks the ticker or the day or cannot be read; a guard test keeps it that way.

**Architecture:** Two single-row probes gate `/replay` and the script. The API loader reads `market_data_intraday` through the raising query helper and branches three ways on two startup flags (table, local-dev bucket, 503). The reference route becomes one `market_data_daily` query. Outages go through `api.http_errors.unavailable`, so an outage is 503 and a defect stays 500. `tests/meta/test_production_writers.py` gains an `ast` guard over 24 registered replay files.

**Tech Stack:** Python, FastAPI, SQLAlchemy with pg8000, psycopg2 (the script), pytest, `ast`.

**Spec:** docs/superpowers/specs/2026-11-13-feat-replay-001-replay-bars-from-the-table.md

## Global Constraints

- Base: `origin/main` once it holds the approved spec (commits 7df792b4 and 80a7cd0d). The code of every file this plan touches is that of 8712afb6; the spec's line numbers are for that code. Branch `fix/feat-replay-001-replay-bars-from-the-table`. Commit this plan file first, alone: `docs(plan): FEAT-REPLAY-001 implementation plan`.
- No replay fetches. No new AlphaVantage request, no job start added, no bucket read when Cloud SQL is configured. No change to `gcp/deploy.sh`, `gcp/backfill_ticker.py`, `lib/data_loader.py`, `GET /api/market/dates`, `/api/live/*`, or solyra. No trading cost anywhere. Tickers in scope for checks: SPY, QQQ, IWM.
- Exact strings, copied from the spec. `{T}` is the upper-case ticker, `{D}` an ISO date, `{date}` the path value as sent.
  - R1 `No replay for {T} on {D}: market_data_intraday has no 1-min bars for {T} in the 7 days before {D}. Nothing was fetched and no job was started.`
  - R2 `No replay for {T} on {D}: market_data_daily has no daily bar for {T} before {D}. Nothing was fetched and no job was started.`
  - R3 `Could not read {table} for {T}: the database did not answer. No job was started. Try again in a minute.`
  - A1 `No 1-min bars for {T} on {date} in market_data_intraday.` (404)
  - A2 `Invalid date {date}: expected YYYYMMDD or YYYYMM.` (404)
  - A3 `Could not read 1-min bars for {T} on {date}: the database is unavailable.` (503)
  - A4 `No 1-min parquet for {T} on {date} in the bucket (local dev).` (404, local dev only)
  - A5 `No daily bar for {T} before {date} in market_data_daily.` (404)
  - A6 `Invalid date {date}: expected YYYYMMDD or YYYY-MM-DD.` (404)
  - A7 `Could not read reference levels for {T} before {date}: the database is unavailable.` (503)
  - A8 `Could not read 1-min bars for {T}: the database is unavailable.` (503, the two POST routes)
  - A9 `Could not read journal trades for {T}: the database is unavailable.` (503, the two POST routes)
- Exact SQL, copied from the spec.
  - Q1 `SELECT 1 FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :lo AND ts < :hi LIMIT 1`
  - Q2 `SELECT 1 FROM market_data_daily WHERE ticker = :t AND date < :d LIMIT 1`
  - Q3 `SELECT date, open, high, low, close, rsi_14 FROM market_data_daily WHERE ticker = :ticker AND date < :dt ORDER BY date DESC LIMIT 5`
- A 503 for a failed read is raised only by `api.http_errors.unavailable(detail, exc)` inside the `except`. Never write `raise HTTPException(status_code=503)` inside an `except Exception` block: `tests/meta/test_http_status_classification.py` counts those and `main.py` must stay at 6.
- All four handlers stay plain `def` (CLAUDE.md 3.10).
- Time (CLAUDE.md 3.9): the probe window is raw UTC on purpose (the table holds two conventions). No other new time conversion. Do not reword `datetime.now()` in `get_reference_levels` or `date.today()` in `parse_date_arg`: the timezone ratchet keys on them.
- **The render step.** A task that changes a file under `gcp/`, `lib/`, `scripts/` or `platform/api` ends with it, because `tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate` fails as soon as a cited line moves:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), then stage whichever of the three docs changed in the same commit as the code. Nothing else in those docs is edited.
- **The guard check.** From Task 3 on, a task that cleans a registered file runs this and expects no line for its file:
  `python3 -c "from tests.meta import test_production_writers as g; s=g._replay_sources(); h=g.vendor_holders(s); [print(o) for r,e in g.REPLAY_PATH.items() for o in g.replay_reach_offenders(r, s[r], e, h, g.REPLAY_EXEMPT)]"`
- Commits: run `python3 scripts/gate/spec_gate.py --commit` first. Conventional message, imperative, 72 characters or fewer. No AI attribution of any kind: no co-author line, no "generated by", no emoji.
- Tests go in the files named, one folder per area. Whole suite: `make test`. One failure exists on `main` too in the planning sandbox and is not this plan's: `tests/api/test_movement_statement_router.py::test_endpoint_nan_close_does_not_500_and_carries_no_nan`, when run with the rest of `tests/api` (alone, its module is skipped). Its cause was not looked into.
- A claim in a doc or on the PR about what the code does comes from output that was run (CLAUDE.md 3.11.1).

## Review Focus

Inputs the spec implies and no done_when test pins. Each has a test in the task that owns the code.

- A path date made of digits that is not a calendar date (`20260230`) or of non-ASCII digits (full-width `20260220`): 404 A2 before any read. `str.isdigit()` accepts the second. Task 7.
- The dashed reference date (`2020-03-16`), which the handler accepts today: still 200, bound as `2020-03-16`. Half-dashed forms (`2026-0220`) and a month (`202602`) are 404 A6. Task 8.
- A December month request (`202612`): the window is `2026-12-01 02:00Z` to `2027-01-01 02:00Z`, and an empty month is 404 A1 with `202612` in it. Task 7.
- `end_time` before the first bar: the 404 keeps its own text, `No data for {T} on {date} at or before end_time=...`. Solyra tells the 404s apart by prefix. Task 7.
- `/replay` with a ticker typed as ` amd `: both probes bind `AMD` and the reply names `AMD`. Task 4.
- The script with repeated or unsorted `--dates`: each distinct date is probed once and reported once, in date order. Task 5.
- The guard on a dispatch or a bar-loader call at module level or inside a nested function: module level is flagged; a nested function counts as its outermost function. Task 3.

## File map

| File | Change | Task |
|---|---|---|
| `lib/eastern_time.py` | add `replay_probe_window` | 2 |
| `tests/meta/test_production_writers.py` | the replay guard | 3, 11 |
| `gcp/discord_interactions/main.py` | two probes, `handle_replay` gate, backfill removed | 4 |
| `scripts/backfill_and_replay.py` | `missing_replay_dates`, backfill step removed | 5 |
| `platform/api/main.py` | flags, loader, market data route, reference route | 6, 7, 8, 10 |
| `platform/api/routers/backtest.py` | strict journal read, 503 for an outage | 9, 10 |
| `platform/api/schemas.py`, `platform/api/openapi.json` | `ErrorDetail`, declared 404 and 503 | 8, 9, 10 |
| `tests/gcp/test_discord_interactions.py`, `tests/scripts/test_backfill_and_replay.py`, `tests/lib/test_eastern_time.py` | tests | 2, 4, 5 |
| `tests/api/test_platform_api.py`, `test_intraday_loader_conventions.py`, `test_route_coverage.py`, `test_api_handler_dispatch.py`, `test_openapi_snapshot.py` | tests | 6 to 10 |
| `tests/lib/test_replay_labeled_trades.py`, `tests/lib/test_style_walk_forward.py` | tests | 9 |
| `tests/fixtures/timezone_boundary_baseline.json` | one entry renamed | 8 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 4 to 10, 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 13 |

## Task 1: Measure the two probes in production

Spec: Capacity; Design 2. Advances done_when[15]. Needs: nothing. Run it before any code: a plan that reads more than 10 rows blocks the merge, and then the probe design is wrong.

- [ ] Run, read-only (no `--commit`). D is the latest NYSE session; the literals below are for D = 2026-11-13. On a later day replace `2026-11-13` by that session and `2026-11-06` by D minus 7 days, in all four statements.

```bash
env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "EXPLAIN (ANALYZE, BUFFERS) SELECT 1 FROM market_data_intraday WHERE ticker = 'SPY' AND interval = '1min' AND ts >= TIMESTAMPTZ '2026-11-06 00:00:00+00' AND ts < TIMESTAMPTZ '2026-11-13 00:00:00+00' LIMIT 1; EXPLAIN (ANALYZE, BUFFERS) SELECT 1 FROM market_data_daily WHERE ticker = 'SPY' AND date < DATE '2026-11-13' LIMIT 1; EXPLAIN (ANALYZE, BUFFERS) SELECT 1 FROM market_data_intraday WHERE ticker = 'ZZZZ' AND interval = '1min' AND ts >= TIMESTAMPTZ '2026-11-06 00:00:00+00' AND ts < TIMESTAMPTZ '2026-11-13 00:00:00+00' LIMIT 1; EXPLAIN (ANALYZE, BUFFERS) SELECT 1 FROM market_data_daily WHERE ticker = 'ZZZZ' AND date < DATE '2026-11-13' LIMIT 1"
```

- [ ] Pass means, for each of the four plans: a `Limit` over an `Index Scan` or `Index Only Scan` on one relation (for the 1-min probe one partition, `market_data_intraday_spy` or `market_data_intraday_other`; for the daily probe `market_data_daily`), and `rows=` in the `actual` part of every scan node is 10 or fewer. A `Seq Scan`, or any scan node with actual rows above 10, fails. The two `ZZZZ` plans show actual rows 0; if `ZZZZ` has rows, use another ticker with none.
- [ ] Save the four plans, the execution time of each, and the execution id the script prints. They go on the PR in Task 13. On a fail, stop and report to the owner; do not start Task 2.

## Task 2: The probe window

Spec: Design 1 (the rule), Design 2 (second bullet). Advances done_when[0], [3], [4]. Needs: nothing.

**Files:** Modify `lib/eastern_time.py` (the "reading market_data_intraday across the convention migration" section, after `stored_intraday_to_eastern`). Test `tests/lib/test_eastern_time.py`.

**Interfaces:** Produces `replay_probe_window(d: date) -> tuple[datetime, datetime]`: `(lo, hi)`, both timezone-aware UTC, `hi` = `d` at 00:00 UTC, `lo` = `hi` minus 7 days.

- [ ] Write `test_replay_probe_window_is_the_seven_utc_days_before_the_date`:
  - `replay_probe_window(date(2026, 4, 24)) == (datetime(2026, 4, 17, tzinfo=timezone.utc), datetime(2026, 4, 24, tzinfo=timezone.utc))`
  - `replay_probe_window(date(2026, 1, 3))[0] == datetime(2025, 12, 27, tzinfo=timezone.utc)`
  - for `date(2026, 3, 10)` (spans the clock change): `hi - lo == timedelta(days=7)` and both offsets are zero
  - a `datetime(2026, 4, 24, 15, 30)` and a `pd.Timestamp("2026-04-24 15:30")` give the same pair as `date(2026, 4, 24)`
- [ ] Run: `python3 -m pytest tests/lib/test_eastern_time.py -q -k replay_probe_window` (expect FAIL: cannot import `replay_probe_window`).
- [ ] Implement it. Build `hi` from `d.year, d.month, d.day` with the module's `UTC`.
- [ ] Run: `python3 -m pytest tests/lib/test_eastern_time.py tests/meta/test_timezone_boundaries.py -q` (expect all pass).
- [ ] The render step.
- [ ] Commit: `fix(replay): add the 7-day probe window for a replay date`

## Task 3: The guard's functions, the registration test and the rewrite test

Spec: Design 8. Advances done_when[14]; builds what [12] and [13] need. Needs: nothing. Green on `main`'s code.

**Files:** Modify `tests/meta/test_production_writers.py` (append; the existing tests are not edited).

**Interfaces:** Produces, at module level:
- `REPLAY_PATH: dict[str, tuple[str, ...]]`: the 24 files of Design 8 with their entry functions; `("*",)` for a whole file.
- `REPLAY_EXEMPT: dict[tuple[str, str], str]`: one key, `("platform/api/routers/backtest.py", "_style_history_bar_loader")`; the value says why (the walk-forward history read through `lib.data_loader.DataLoader`, until the second spec).
- `DISCORD_JOBS: dict[str, str]`: `premarket-brief` to `gcp/premarket_brief.py`, `insight-pipeline` to `gcp/insight_pipeline_job.py`, `insight-discord-push` to `gcp/insight_discord_push.py`, `signal-replay` to `gcp/signal_replay.py`, `validate-brief` to `gcp/validate_brief_job.py`, `backtest` to `gcp/backtest_job.py`.
- `LOCAL_DEV_FUNCS = ("_bars_from_gcs_local_dev", "_reference_from_gcs_local_dev")`, `BAR_LOADERS = ("_load_date_data", "_replay_bar_loader", "_style_history_bar_loader")`, `REPLAY_FLAG = re.compile(r"REPLAY|AS_OF|--as-of|--replay|BACKTEST_|VALIDATE_(?:TICKER|DATE)|PLAYBOOK_RESOLVE_DATE")`.
- `_replay_sources() -> dict[str, str]`: repo-relative path to text for every `*.py` under `gcp/`, `lib/`, `scripts/`, `platform/api`, skipping `_archive`, `archive`, `node_modules`, `__pycache__`.
- `vendor_holders(sources: dict[str, str]) -> set[str]`
- `replay_reach_offenders(rel: str, src: str, entries: tuple[str, ...], holders: set[str], exempt: dict) -> list[str]`, each `"{rel}:{line} in {function}: {reason}"`
- `local_dev_offenders(rel: str, src: str) -> list[str]`
- `registration_offenders(sources: dict[str, str], replay_path: dict, discord_jobs: dict) -> list[str]`

All four take source text, so the rewrite test can feed snippets. Parse with `ast`, `SyntaxWarning` ignored. Rules:

- A vendor request is an `ast.Dict` with the constant key `"function"` and a string constant value starting `TIME_SERIES_`, or any string constant containing `function=TIME_SERIES_`.
- `vendor_holders`: the name of every function (nested functions and methods too) whose own body holds a vendor request. Only those names. A function that calls a holder is not added.
- Reach: for `("*",)` the scope is the whole module. Otherwise start from the entry names; a function defined in the file is reached when its name appears as an `ast.Name` or as an `ast.Attribute` attribute inside a reached function; repeat until nothing is added. A named entry the file does not define is an offender.
- `replay_reach_offenders` flags, inside what is reached: (a) a vendor request; (b) a call whose bare name or attribute name is in `holders`; (c) `gcs_reader.<anything>` (an attribute on the name `gcs_reader`) unless it is lexically inside a function in `LOCAL_DEV_FUNCS`; (d) a string constant containing `backfill-ticker` that is not a docstring (a docstring is the first statement of a module, class or function); (e) when `rel` starts with `platform/api/`: the name `DataLoader` or `data_loader`, or an attribute named `DataLoader`, unless lexically inside a function that `exempt` names for that file. Report each line and reason once.
- `local_dev_offenders`: every call of a `LOCAL_DEV_FUNCS` name must be inside the body, not the `else`, of an `if` or `elif` whose test is exactly the name `_CLOUD_SQL_UNCONFIGURED`.
- `registration_offenders` flags: (1) in `gcp/discord_interactions/main.py`, a call of `execute_cloud_run_job` whose outermost enclosing function is not a `REPLAY_PATH` entry of that file (module level is flagged), whose first argument is not a string literal, or whose literal is not a `DISCORD_JOBS` key; a `DISCORD_JOBS` module that is not a `REPLAY_PATH` key; (2) a file not in `REPLAY_PATH` in which a string literal read through `os.environ.get`, `os.getenv` or `os.environ[...]`, or passed to `.add_argument(...)`, matches `REPLAY_FLAG`; (3) under `platform/api`, a call of a `BAR_LOADERS` name, or of `enqueue_insight_task` with the keyword `as_of_iso`, whose outermost enclosing function is not in the reach of that file's registered entries.

- [ ] Write `test_the_replay_guard_catches_the_obvious_rewrites`, parametrized over snippets. Each row is a small source string checked as the named file; "flag" means at least one offender, "clean" means none.

| Snippet | Checked by | Expect |
|---|---|---|
| Discord module: the four handlers dispatch the six jobs by literal name | registration | clean |
| the same plus `def handle_earnings(): execute_cloud_run_job("backtest", {})` | registration | flag |
| the same with `"validate-brief"` replaced by `"backfill-ticker"` | registration | flag |
| the same with a job name passed as a variable | registration | flag |
| the same plus a module-level `execute_cloud_run_job("backtest", {})` | registration | flag |
| `handle_replay` dispatching from a nested function | registration | clean |
| new file `gcp/new_job.py`, one row each: `os.environ.get("MY_REPLAY_DAY")`, `os.getenv("NEWJOB_AS_OF")`, `add_argument("--as-of")`, `add_argument("--replay-date")`, `os.environ["BACKTEST_WINDOW"]`, `os.environ.get("VALIDATE_TICKER")`, `os.environ.get("VALIDATE_DATE")`, `os.environ.get("PLAYBOOK_RESOLVE_DATE")` | registration | flag (8 rows) |
| `gcp/new_job.py` reading `DB_USER` | registration | clean |
| `platform/api/main.py` with `def export_csv(t, d): return X(t, d)`, one row for each of the three `BAR_LOADERS` as `X` | registration | flag (3 rows) |
| `platform/api/main.py` where `_reference_from_gcs_local_dev`, called by `get_reference_levels`, calls `_load_date_data` | registration | clean |
| `platform/api/routers/insights.py` with a second function passing `as_of_iso=` to `enqueue_insight_task` | registration | flag |
| the same where the second function calls `enqueue_insight_task` without `as_of_iso` | registration | clean |
| `get_reference_levels` calls `_latest`, which holds `{"function": "TIME_SERIES_DAILY"}` | reach | flag |
| `get_reference_levels` builds `f"...?function=TIME_SERIES_DAILY&symbol={t}"` | reach | flag |
| `handle_replay` calls `f.fetch_month(t, d)`, holders = `{"fetch_month"}` | reach | flag |
| a `TIME_SERIES_INTRADAY` dict in a function no entry reaches | reach | clean |
| `_load_date_data` calls `gcs_reader.blob_exists` | reach | flag |
| `gcs_reader.download_parquet` inside `_bars_from_gcs_local_dev` | reach | clean |
| `mine_and_validate` reaches `_style_history_bar_loader` and `_other`, both calling `DataLoader()` | reach | flag |
| `get_market_data` uses the module-level `data_loader` | reach | flag |
| only `_style_history_bar_loader` holds `DataLoader()` | reach | clean |
| the same with `exempt={}` | reach | flag, and the offender names `_style_history_bar_loader` |
| `gcp/backtest_job.py` (whole file) calling `DataLoader()` | reach | clean |
| `scripts/backfill_and_replay.py` with `_execute_job('backfill-ticker', {})` | reach | flag |
| `handle_replay` logging `"run backfill-ticker by hand for %s"` | reach | flag |
| `backfill-ticker` only in a module docstring, a function docstring and a comment | reach | clean |
| an entry tuple naming a function the file does not define | reach | flag |
| `if not _CLOUD_SQL: return _bars_from_gcs_local_dev(t, d)` | local-dev | flag |
| `_reference_from_gcs_local_dev(t, d)` under no branch | local-dev | flag |
| the call in the `else` of `if _CLOUD_SQL_UNCONFIGURED:` | local-dev | flag |
| `if _CLOUD_SQL_UNCONFIGURED or FORCE:` | local-dev | flag |
| `if _CLOUD_SQL: ... elif _CLOUD_SQL_UNCONFIGURED: return _bars_from_gcs_local_dev(t, d)` | local-dev | clean |

- [ ] Write `test_every_replay_entry_point_is_registered`: `registration_offenders(_replay_sources(), REPLAY_PATH, DISCORD_JOBS) == []`; every `REPLAY_PATH` key is a file in the repo and every named entry is defined in it; the flag scan finds at least 16 files and `vendor_holders` at least 15 names, so an empty walk cannot pass; `set(DISCORD_JOBS)` is the six names above.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q` (expect FAIL: names not defined).
- [ ] Implement the constants and the four functions.
- [ ] Run again (expect all pass; the 15 existing tests still pass).
- [ ] Run the guard check on the untouched code. Expect exactly these places and no other file: `gcp/discord_interactions/main.py:464` and `:470`; `scripts/backfill_and_replay.py:178`, `:180`, `:306`, `:330`; `platform/api/main.py:242`, `:1116`, `:1170`, `:1703`, `:1704` (two reasons on `:1704`). With `{}` in place of `g.REPLAY_EXEMPT`, one more: `platform/api/routers/backtest.py:636`. Any other line means a rule above is implemented differently; fix the function, not the list.
- [ ] Commit: `test(replay): add the replay path guard and its registration test`

## Task 4: Discord `/replay` reads the two tables and starts no backfill

Spec: Design 2; Design 9 rows 1 and 2. Advances done_when[0], [1], [2], [3]. Needs: Task 2, Task 3.

**Files:** Modify `gcp/discord_interactions/main.py` (`:275-338`, `:389-513`). Test `tests/gcp/test_discord_interactions.py`.

**Interfaces:** Consumes `lib.eastern_time.replay_probe_window`. Produces `replay_bars_in_table(ticker: str, d: date) -> bool` and `replay_daily_in_table(ticker: str, d: date) -> bool`.

- [ ] Add a test helper `_run_replay(answers, date_arg="2026-04-24", refresh=False, configured=True, brief_row=False, insight_row=False) -> (msg, events, dispatched)`. It patches `gcp.database.query_to_dataframe_strict` with a fake `(sql, params=None, timeout_s=None)` that appends `(table, sql, params, timeout_s)` to `events` (the table is read from the SQL text) and returns or raises `answers[table]`; `gcp.database.is_cloud_sql_configured` to return `configured`; `_brief_row_exists` to append `("brief_row",)` and return `brief_row`; `_insight_row_exists`, `_log_cache_hit`, `edit_deferred_reply`; and `execute_cloud_run_job` to append `(name, env)` to `dispatched` and return True. It calls `handle_replay("AMD", date_arg, "appid", "tok", refresh=refresh)`. Existing tests patch `gcp.database` the same way (`:222`, `:691`), because this module imports it inside functions.
- [ ] Write the four tests of done_when, with a one-row frame as "found" and an empty frame as "not found":
  - `test_replay_says_the_table_has_no_bars_and_starts_nothing`, for `refresh` False and True: `msg` equals R1 for AMD and 2026-04-24; `dispatched == []`; `events` is one entry for `market_data_intraday`; its SQL holds `market_data_intraday`, `interval = '1min'` and `LIMIT 1`; its params equal `{"t": "AMD", "lo": datetime(2026, 4, 17, tzinfo=timezone.utc), "hi": datetime(2026, 4, 24, tzinfo=timezone.utc)}`; `timeout_s == 10`. No `brief_row` event and no daily event.
  - `test_replay_says_the_daily_table_has_no_bar_and_starts_nothing`, for `refresh` False and True: `msg` equals R2; `dispatched == []`; events are `market_data_intraday` then `market_data_daily` and nothing else; the second SQL holds `market_data_daily`, `date < :d` and `LIMIT 1`; its params equal `{"t": "AMD", "d": date(2026, 4, 24)}`; `timeout_s == 10`.
  - `test_replay_reports_a_database_error_and_starts_nothing`, three cases with `boom = sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception("connection refused by 10.1.2.3"))`: the 1-min probe raises (R3 with `market_data_intraday`); the daily probe raises after a found 1-min row (R3 with `market_data_daily`); `configured=False` (R3 with `market_data_intraday`, and `events == []`). In each: `msg` equals R3 exactly, holds neither `connection refused` nor `SELECT`, and `dispatched == []`.
  - `test_replay_with_bars_runs_each_probe_once_then_dispatches`, for `date_arg` in `"2026-04-24"` (a weekday), `"2026-04-26"` (a Sunday) and `"today"`, with `d = parse_date_arg(date_arg)`: events are exactly `market_data_intraday`, `market_data_daily`, `brief_row`; the first params are the 7-day window before `d`, the second `{"t": "AMD", "d": d}`; dispatched names are `["premarket-brief", "insight-pipeline"]`; the brief env equals `{"BRIEF_AS_OF": d.isoformat(), "BRIEF_TICKERS": "AMD", "BRIEF_UPDATE": "true", "BRIEF_POST_TO_DISCORD": "true", "BRIEF_TRIGGERED_BY": "discord:replay"}`; the insight env keys are `INSIGHT_AS_OF`, `INSIGHT_TICKERS`, `INSIGHT_UPDATE`, `INSIGHT_TRIGGERED_BY`; `"backfill" not in msg.lower()`. Then with `brief_row=True, insight_row=True`: the same three events, dispatched names `["premarket-brief", "insight-discord-push"]`, the brief env equals `{"BRIEF_POST_EXISTING_TICKER": "AMD", "BRIEF_POST_EXISTING_DATE": d.isoformat(), "BRIEF_TRIGGERED_BY": "discord:replay"}`, no "backfill" in the reply.
- [ ] Write `test_replay_probes_bind_the_normalised_ticker`: `handle_replay(" amd ", "2026-04-24", ...)` with the 1-min probe answering empty binds `t == "AMD"`, the reply starts `No replay for AMD on 2026-04-24: `, nothing is dispatched.
- [ ] Change the existing tests (Design 9): delete `test_replay_skips_backfill_when_ticker_has_data` (`:429`), `test_replay_dispatches_backfill_when_ticker_missing` (`:447`), `test_replay_returns_error_when_backfill_fails` (`:481`). In the five that patch `ticker_has_daily_data` (`:353`, `:391`, `:414`, `:910`, `:943`) patch `replay_bars_in_table` and `replay_daily_in_table` to return True instead. In the two that relied on the unconfigured True (`:323`, `:868`) add the same two patches.
- [ ] Run: `python3 -m pytest tests/gcp/test_discord_interactions.py -q` (expect FAIL: the module has no `replay_bars_in_table`).
- [ ] Implement:
  - `replay_bars_in_table`: import `is_cloud_sql_configured` and `query_to_dataframe_strict` from `gcp.database` inside the function; raise `RuntimeError` when not configured; run Q1 with `{"t": ticker.upper(), "lo": lo, "hi": hi}` from `replay_probe_window(d)` and `timeout_s=10`; return `not df.empty`. No `try`.
  - `replay_daily_in_table`: the same shape with Q2 and `{"t": ticker.upper(), "d": d}`.
  - `handle_replay`: after `ticker_u` is set and before the cached path, run the 1-min probe, then the daily probe. A False gives R1 or R2 and returns. An exception is logged with `logger.exception` and gives R3 with that probe's table. The daily probe does not run after a False or a raise from the first. The cached path and the recompute path are otherwise unchanged, minus `backfill_msg`.
  - Delete `ticker_has_daily_data`, `execute_cloud_run_job_blocking`, the backfill block (`:454-472`) and every `{backfill_msg}`. Reword the `handle_replay` docstring: no "auto-backfill".
- [ ] Run: `python3 -m pytest tests/gcp/test_discord_interactions.py -q` (expect 61 passed).
- [ ] The guard check (expect no line for `gcp/discord_interactions/main.py`), then `python3 -m pytest tests/meta -q` (expect all pass), then the render step.
- [ ] Commit: `fix(replay): gate /replay on the two tables and drop the backfill`

## Task 5: `scripts/backfill_and_replay.py` refuses dates the tables lack

Spec: Design 3; Design 9 row 3. Advances done_when[4]. Needs: Task 2, Task 3.

**Files:** Modify `scripts/backfill_and_replay.py`. Test `tests/scripts/test_backfill_and_replay.py`.

**Interfaces:** Consumes `replay_probe_window`. Produces `missing_replay_dates(conn, ticker: str, dates: list[date]) -> list[tuple[date, str]]`: for each distinct date in date order, Q1 on the script's own psycopg2 connection (`%s` placeholders, parameters `(ticker, lo, hi)`), and only if that finds a row, Q2 with `(ticker, d)`. An entry is the date and the table that lacks it, at most one per date. It uses `with conn.cursor() as cur`, `cur.execute`, `cur.fetchone()`, and catches nothing.

- [ ] Add a stub `_Conn(answer)` to the test file: `cursor()` returns a context manager with `execute(sql, params)` and `fetchone()`; `answer(sql, params)` returns a row tuple or None; it records `queries` and `closed`.
- [ ] Change the existing tests (Design 9 and spec issue 3): delete the five at `:61`, `:71`, `:80`, `:87`, `:104`. In `_run_main` (`:135`) `db_connect` returns `_Conn(lambda sql, params: (1,))` and the `pytest.fail("the comparison report must not run on a failed replay")` moves to `report_comparison`. Drop `"--skip-backfill"` from `:158` and `:173`. Reword the module docstring: the script no longer dispatches the job.
- [ ] Write `test_main_refuses_dates_the_tables_do_not_hold`, running `main()` with `--ticker amd --dates 2026-04-24,2026-04-27`, `_execute_job` recording, `report_comparison` failing:
  - connection A answers every daily probe with a row and the 1-min probe with a row only when `lo <= datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc) < hi`: `SystemExit` with a non-zero code whose text holds `AMD`, `2026-04-24` and `market_data_intraday` and not `2026-04-27`; zero `_execute_job` calls; the connection is closed; the two 1-min windows probed are 2026-04-17 to 2026-04-24 and 2026-04-20 to 2026-04-27, at 00:00 UTC.
  - connection B answers every 1-min probe with a row and the daily probe with a row only when its bound date is after `date(2026, 4, 24)`: the text holds `AMD`, `2026-04-24` and `market_data_daily` and not `2026-04-27`; zero `_execute_job` calls.
- [ ] Write `test_no_backfill_step_remains`: the module defines no `trigger_backfill_ticker` and no `_month_groups`, and its source holds no `DAILY_HISTORY_DAYS`; `main()` with each of `--skip-backfill`, `--history-days 800`, `--include-news`, `--news-window-days 7` exits with code 2 and `unrecognized arguments` on stderr, before `db_connect` is called.
- [ ] Write `test_missing_replay_dates_probes_each_distinct_date_once_in_order`: with every probe answering None, `[d27, d24, d24]` returns `[(d24, "market_data_intraday"), (d27, "market_data_intraday")]` from two queries.
- [ ] Run: `python3 -m pytest tests/scripts/test_backfill_and_replay.py -q` (expect FAIL).
- [ ] Implement. `main` opens the connection first and holds it in one `try/finally` that closes it. It calls `missing_replay_dates`; when the list is not empty it exits with `No replay for {T}: ` plus, per entry and joined by `; `, the R1 clause `market_data_intraday has no 1-min bars for {T} in the 7 days before {D}` or the R2 clause `market_data_daily has no daily bar for {T} before {D}`, plus `. Nothing was fetched and no job was started.` The probes run with `--skip-replay` too. Then the replay loop and `report_comparison` on the same connection. Remove `trigger_backfill_ticker`, `_month_groups`, `DAILY_HISTORY_DAYS`, the four flags, and every string that holds `backfill-ticker` outside the docstring. The module docstring says what the script does now. `--skip-replay` help: `Report only; do not trigger insight-pipeline runs`.
- [ ] Run again (expect 11 passed). The guard check (expect no line for `scripts/backfill_and_replay.py`). The render step.
- [ ] Commit: `fix(replay): refuse replay dates the tables lack in the script`

## Task 6: Two startup flags in the API

Spec: Design 4, first bullet. Advances done_when[7] (`test_cloud_sql_flags_tell_unconfigured_from_a_failed_import`). Needs: nothing.

**Files:** Modify `platform/api/main.py:62-68`. Test `tests/api/test_platform_api.py` (`TestMarketDataAPI`).

**Interfaces:** Produces `_cloud_sql_flags() -> tuple[bool, bool]` (configured, unconfigured) and the module flags `_CLOUD_SQL`, `_CLOUD_SQL_UNCONFIGURED`.

- [ ] Write `TestMarketDataAPI::test_cloud_sql_flags_tell_unconfigured_from_a_failed_import(self, monkeypatch, caplog)`: with `gcp.database.is_cloud_sql_configured` patched to True, `_cloud_sql_flags() == (True, False)`; patched to False, `(False, True)`; with `monkeypatch.setitem(sys.modules, "gcp.database", None)`, `(False, False)` and an ERROR record with `exc_info` on the `api.main` logger.
- [ ] Run: `python3 -m pytest tests/api/test_platform_api.py -q -k cloud_sql_flags` (expect FAIL: no `_cloud_sql_flags`).
- [ ] Implement. The function imports `is_cloud_sql_configured` from `gcp.database` inside its body; on any exception it calls `logger.exception(...)` and returns `(False, False)`; otherwise `(configured, not configured)`. Module level: `_CLOUD_SQL, _CLOUD_SQL_UNCONFIGURED = _cloud_sql_flags()`. Keep a separate guarded `from gcp.database import query_to_dataframe` until Task 8 removes its last user.
- [ ] Run: `python3 -m pytest tests/api -q` (expect no failure that `origin/main` does not have). The render step.
- [ ] Commit: `fix(api): tell an unconfigured database from a failed import`

## Task 7: The bar loader and `GET /api/market/data/{ticker}/{date}`

Spec: Design 4; Design 7 (market data rows); Design 9 rows 4, 5 and 7. Advances done_when[5], [6], [7] (market data half), [10] (row `:403`). Needs: Task 3, Task 6.

**Files:** Modify `platform/api/main.py` (`get_market_data` `:933-1044`, `_load_date_data` `:1623-1724`). Test `tests/api/test_platform_api.py`, `tests/api/test_intraday_loader_conventions.py`, `tests/api/test_route_coverage.py`, `tests/api/test_api_handler_dispatch.py`.

**Interfaces:** Consumes the two flags. Produces:
- `_parse_bar_date(date: str) -> tuple[str, datetime]`: `("day", that day)` for 8 ASCII digits that form a calendar date, `("month", its first day)` for 6 ASCII digits with a month of 01 to 12; otherwise `ValueError` whose message is A2.
- `_bars_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame`: a deferred call to `gcp.database.query_to_dataframe_strict`, like `_dates_query` (`:623`).
- `_bars_from_gcs_local_dev(ticker_lower: str, date: str) -> pd.DataFrame`
- `_load_date_data(ticker_lower: str, date: str) -> pd.DataFrame` (same signature; new behaviour below).

- [ ] Add module-level test helpers above `TestMarketDataAPI` (Task 8 uses them too): `_flags(monkeypatch, configured, unconfigured)` sets the two flags on `api.main`; `_strict_recorder(monkeypatch, result)` patches `gcp.database.query_to_dataframe_strict` with a fake `(sql, params=None, timeout_s=None)` that records `(sql, params)` and returns a copy of `result` or raises it; `_bucket_recorder(monkeypatch, blobs=None)` replaces every public function of `api.gcs_reader` (`list_matching_blobs`, `list_matching_blobs_strict`, `blob_exists`, `download_csv`, `download_parquet`, `download_text`, `get_latest_csv`, `get_latest_parquet`) with one that records `(function, first argument)` and answers from `blobs` (blob path to frame; a path not in it does not exist); `_loud(client)` is `TestClient(client.app, raise_server_exceptions=False)`; `_statement_timeout()` is `sqlalchemy.exc.OperationalError("SELECT 1", {}, pg8000.exceptions.DatabaseError({"C": "57014"}))`.
- [ ] Write in `TestMarketDataAPI`:
  - `test_market_data_404_names_the_table_and_never_reads_the_bucket`: flags (True, False), zero rows: `GET /api/market/data/IWM/20260220` is 404 with body `{"detail": A1}` for IWM and 20260220; one query; zero bucket calls.
  - `test_market_data_malformed_date_is_404_before_any_read`, parametrized over `20261345`, `abcdefgh`, `202613`, `2026-02-20`, `20260230`, and the eight full-width digits of 20260220 (in the test: `"\uff12\uff10\uff12\uff16\uff10\uff12\uff12\uff10"`): 404 with body `{"detail": A2}` holding the value as sent; zero queries; zero bucket calls.
  - `test_market_data_database_failure_is_503_and_a_defect_is_500`: `ConnectionError("connection refused")` gives 503 with body `{"detail": A3}` and no `connection refused` in the text; `KeyError("close")` and `_statement_timeout()` each give 500 through `_loud(client)`; zero bucket calls in all three.
  - `test_local_dev_reads_the_bucket_only_when_cloud_sql_is_unconfigured` (market data half; Task 8 adds the reference half): flags (False, True) and the strict recorder set to raise if called. With `data/iwm/minute/iwm_minute_20260220.parquet` in the bucket (30 bars, naive Eastern index) the route is 200 with `count` 30; `/20260219` is 404 with body `{"detail": A4}`; no call ever names `data/iwm/iwm_2026.parquet`. With flags (False, False) and the same bucket, `/20260220` is 503 with body `{"detail": A3}`, zero bucket calls, zero queries.
  - `test_market_data_month_request_binds_the_month_window_and_names_the_month`: `/202612` with zero rows is 404 A1 with `202612`; the query params are `{"ticker": "IWM", "start": datetime(2026, 12, 1, 2, tzinfo=timezone.utc), "end": datetime(2027, 1, 1, 2, tzinfo=timezone.utc)}`.
  - `test_market_data_end_time_before_the_first_bar_keeps_its_own_404_text`: 30 bars from 09:30, `?end_time=04:00`: 404 with detail `No data for IWM on 20260220 at or before end_time=04:00`.
- [ ] Change the existing tests (Design 9 and spec issue 1): `_patch_intraday` (`:658`) patches `_bars_query`; `tests/api/test_intraday_loader_conventions.py:120`, `:213`, `:286` patch `_bars_query`; delete `test_market_data_404_when_no_rows` (`:846`); in `tests/api/test_route_coverage.py:403` the row becomes `Req("GET", f"/api/market/data/{T}/{D.replace('-', '')}", 503)`; add `"_bars_query"` to `BLOCKING_CALLS` in `tests/api/test_api_handler_dispatch.py`.
- [ ] Run: `python3 -m pytest tests/api/test_platform_api.py tests/api/test_intraday_loader_conventions.py tests/api/test_route_coverage.py -q` (expect FAIL: no `_bars_query`).
- [ ] Implement:
  - `_parse_bar_date`: match with `re.fullmatch(r"[0-9]{8}", date)` and `r"[0-9]{6}"`; build the value with `datetime(int(...), int(...), int(...))`, not `strptime`.
  - `_load_date_data`: a malformed date raises `FileNotFoundError` with the helper's message. Then, in this order: `if _CLOUD_SQL:` the same two SELECTs as today through `_bars_query`, with today's windows (`[D 00:00Z, D+1 02:00Z)` for a day, `[M-01 02:00Z, next month-01 02:00Z)` for a month), today's conversion through `_intraday_index_to_eastern` and today's Eastern cut; no `try` around them; zero rows after the cut raises `FileNotFoundError(A1)`. `if _CLOUD_SQL_UNCONFIGURED: return _bars_from_gcs_local_dev(ticker_lower, date)`. Otherwise `raise HTTPException(status_code=503, detail=A3)`.
  - `_bars_from_gcs_local_dev`: today's minute-file read, then the month-file read (`:1709-1717`), each through today's `blob_exists` and `download_parquet`; `FileNotFoundError(A4)` when neither exists. The yearly read (`:1719-1722`) is deleted.
  - `get_market_data`: call `_parse_bar_date` first and answer 404 with the message on `ValueError`. Keep `except FileNotFoundError` as 404 with `str(e)`. Add `except Exception as exc: unavailable(A3, exc)`. The two later empty-frame 404s (`:956`, `:1002`) use A1. The `end_time` 404 (`:1018`) and the 400 keep their text.
- [ ] Run the three files again (expect all pass), then `python3 -m pytest tests/api tests/meta -q` (expect no failure that `origin/main` does not have).
- [ ] The guard check: `platform/api/main.py:1703` and `:1704` are gone; the reference lines remain until Task 8. `python scripts/export_openapi.py --check` (expect up to date; if the handler docstring was reworded, run it without `--check` and stage `platform/api/openapi.json`). The render step.
- [ ] Commit: `fix(api): read chart bars from the table or answer 404 or 503`

## Task 8: `GET /api/market/reference/{ticker}/{date}` is one table query

Spec: Design 5; Design 7 (reference rows); Design 9 rows 6 and 7. Advances done_when[8], [7] (reference half), [10] (row `:404`). Needs: Task 6, Task 7.

**Files:** Modify `platform/api/main.py` (`:14`, `:221-266`, `:1047-1232`), `platform/api/schemas.py:376-379` (comments only), `tests/fixtures/timezone_boundary_baseline.json`. Test `tests/api/test_platform_api.py`, `tests/api/test_route_coverage.py`, `tests/api/test_api_handler_dispatch.py`.

**Interfaces:** Consumes the flags, `_load_date_data`, the Task 7 test helpers. Produces:
- `_parse_reference_date(date: str) -> str`: `YYYY-MM-DD` for 8 ASCII digits or for `NNNN-NN-NN` that form a calendar date; otherwise `ValueError` whose message is A6.
- `_daily_reference_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame`: deferred strict, like `_bars_query`.
- `_week_from_daily_rows(df: pd.DataFrame) -> Optional[dict]`: the body of today's `_fetch_week_range` after its query (`:1066-1083`): None under two rows, else `high`, `low`, `avg_close`, `avg_rsi_14`, `start_date`, `end_date`, `sessions`.
- `_reference_from_gcs_local_dev(ticker: str, date: str) -> dict`: today's bucket branch (`:1166-1232`) with `"week": None`.

- [ ] Write in `TestReferenceAPI`, flags (True, False) unless said, rows built newest first with `date, open, high, low, close, rsi_14`:
  - (a) `test_reference_reads_one_query_and_calls_no_vendor`: for a date two days ago and five rows: 200; `source == "cloud_sql"`; `date` is the newest row's; `week` equals the high, low, mean close, mean `rsi_14`, first and last date and `sessions` 5 of those rows; exactly one query, whose SQL holds `market_data_daily` and `LIMIT 5` and whose params are `{"ticker": "IWM", "dt": <ISO date>}`; `httpx.Client` replaced by a recorder saw zero calls; `api.main` has none of `_fetch_av_daily_reference`, `_fetch_week_range`, `AV_API_KEY`, `AV_BASE`.
  - (b) `test_reference_404_names_the_daily_table`: zero rows, `/20200316`: 404 with body `{"detail": A5}`; zero bucket calls.
  - (c, d) `test_reference_database_failure_is_503_and_a_defect_is_500`: `ConnectionError("connection refused")` gives 503 with body `{"detail": A7}` and no `connection refused`; `KeyError("close")` gives 500 through `_loud(client)`.
  - (e) `test_reference_malformed_date_is_404_before_any_read`, parametrized over `20261345`, `garbage`, `2026-13-45`, `2026-0220`, `202602`: 404 with body `{"detail": A6}`; zero queries; zero bucket calls.
  - (f) `test_reference_stale_days_rule`, parametrized over (request age in days, gap to the newest row, expected): `(0, 5, 5)`, `(0, 3, 0)`, `(40, 5, 0)`, the request dated `datetime.now().date()` minus the age, one row: `stale_days` equals expected and `week` is null.
  - `test_reference_accepts_the_dashed_date`: `/2020-03-16` is 200 and the bound `dt` is `2020-03-16`.
- [ ] Extend `test_local_dev_reads_the_bucket_only_when_cloud_sql_is_unconfigured` (Task 7): flags (False, True), minute parquets for 20200313 and 20200316 (60 regular-session bars each): `GET /api/market/reference/IWM/20200316` is 200 with `date == "20200313"`, `week` null, no `source` key, zero queries. Flags (False, False): `/api/market/reference/IWM/20260220` is 503 with body `{"detail": A7}`, zero bucket calls.
- [ ] Change the existing tests (Design 9): delete `test_reference_recent_uses_alphavantage` (`:980`); in `:1004`, `:1032` and `_patch_all_backends` (`:2155-2167`) patch `_daily_reference_query` with one frame that carries `rsi_14` and is returned on every call; fix the comments at `:969-978` and line 7 of the module docstring (no AlphaVantage routing). In `tests/api/test_route_coverage.py`: row `:404` is pinned at 503; drop `("api.main", "AV_API_KEY")` from the loop at `:675` and fix the comment above it (three modules). Add `"_daily_reference_query"` to `BLOCKING_CALLS`.
- [ ] Run: `python3 -m pytest tests/api/test_platform_api.py tests/api/test_route_coverage.py -q` (expect FAIL).
- [ ] Implement `get_reference_levels`: parse first, 404 with the message on `ValueError`. `if _CLOUD_SQL:` run Q3 through `_daily_reference_query` with `{"ticker": ticker_upper, "dt": date_str}` inside `try`, `except Exception as exc: unavailable(A7, exc)`; zero rows is 404 A5; the first row is the reference day; `source` is `cloud_sql`; `week` is `_week_from_daily_rows(df)`; `stale_days` keeps today's rule (`:1107-1110`, `:1146-1155`), written with `datetime.now().date()` inside this handler. `if _CLOUD_SQL_UNCONFIGURED: return _reference_from_gcs_local_dev(ticker, date)`. Otherwise `raise HTTPException(status_code=503, detail=A7)`. Rewrite the handler docstring to say this; it is the OpenAPI description.
- [ ] Delete `_fetch_av_daily_reference`, `AV_API_KEY`, `AV_BASE`, `_fetch_week_range`, `import httpx`, and the guarded `query_to_dataframe` import Task 6 kept (no line of the module names it now). Keep `MAX_CLOUD_SQL_STALENESS_DAYS`; its comment loses "we prefer AV". Fix the two comments on `ReferenceResponse` in `platform/api/schemas.py`.
- [ ] Run: `python -m tests.meta.test_timezone_boundaries --write-baseline`, then `git diff tests/fixtures/timezone_boundary_baseline.json`. Expect one entry renamed, `get_reference_levels::df.index.tz_localize(None)` to `_reference_from_gcs_local_dev::df.index.tz_localize(None)` (the sorted list may reorder). Any other change means an expression was reworded; undo that rewording, not the baseline.
- [ ] Run: `python scripts/export_openapi.py`, then `python3 -m pytest tests/api tests/meta -q` (expect no failure that `origin/main` does not have).
- [ ] The guard check (expect no line for `platform/api/main.py`). The render step.
- [ ] Commit: `fix(api): answer reference levels from one daily-table query`

## Task 9: The two POST routes answer 503 for an outage

Spec: Design 6; Design 7 (POST rows); Design 9 row 7. Advances done_when[9], [10] (row `:274`). Needs: Task 3, Task 7.

**Files:** Modify `platform/api/routers/backtest.py` (`:90-96`, `:472-490`, `:512-593`, `:690-756`). Test `tests/lib/test_replay_labeled_trades.py`, `tests/lib/test_style_walk_forward.py`, `tests/api/test_route_coverage.py`.

**Interfaces:** `_replay_journal_query(sql, params)` keeps its signature and forwards to `gcp.database.query_to_dataframe_strict`, imported inside the function.

- [ ] Write, each with `_HAS_CLOUD_SQL` True, `gcp.database.query_to_dataframe_strict` patched for the journal read, `_replay_bar_loader` patched for the bars, and `_style_exec` recording:
  - `tests/lib/test_replay_labeled_trades.py::test_replay_trades_outage_is_503` (body `{"ticker": "IWM", "trade_ids": ["row-1"]}`): the journal read raising `ConnectionError("connection refused")` gives 503 with body `{"detail": A9}` for IWM; the journal read answered with `_journal_rows_df()` and the bar loader raising the same error gives 503 with body `{"detail": A8}`; no `connection refused` in either; `_style_exec` never called.
  - `::test_replay_trades_defect_is_500`: the same two cases with `KeyError("close")` through a client built with `raise_server_exceptions=False`: 500 both times; `_style_exec` never called.
  - `tests/lib/test_style_walk_forward.py::test_mine_and_validate_outage_is_503` and `::test_mine_and_validate_defect_is_500` (body `{"ticker": "IWM"}`): the same four assertions; the answered journal read is `pd.DataFrame(_closed_rows(10))`, so the bar loop is reached.
- [ ] `tests/api/test_route_coverage.py:274`: `POST /api/style/mine-and-validate` is pinned at 503.
- [ ] Run: `python3 -m pytest tests/lib/test_replay_labeled_trades.py tests/lib/test_style_walk_forward.py -q` (expect the four new tests FAIL: the journal outage reads as 404 or as a 200 "have 0").
- [ ] Implement. In both handlers wrap the journal read: `except Exception as exc: unavailable(A9, exc)`. In both bar loops keep `except FileNotFoundError` as it is and add after it `except Exception as exc: unavailable(A8, exc)`. Import `unavailable` from `api.http_errors`. Remove `query_to_dataframe` from the module's import and from its fallback assignment. `_style_history_bar_loader` and the lines around `:778` are not touched. Update the `replay_trades` docstring (an outage is a 503, a defect a 500) and the comment at `:467` and the `_replay_bar_loader` docstring at `:478-481` (no bucket fallback).
- [ ] Run the two files again (expect all pass, the existing cases unchanged), then `python3 -m pytest tests/api/test_route_coverage.py tests/meta -q` (expect all pass).
- [ ] `python scripts/export_openapi.py`. The guard check (expect no output at all now). The render step.
- [ ] Commit: `fix(api): answer 503 when the scorecard or style read fails`

## Task 10: The error contract in OpenAPI

Spec: Design 7, last bullet. Advances done_when[11]. Needs: Tasks 7, 8, 9.

**Files:** Modify `platform/api/schemas.py`, the two route decorators in `platform/api/main.py`, the two in `platform/api/routers/backtest.py`, `platform/api/openapi.json`. Test `tests/api/test_openapi_snapshot.py`.

**Interfaces:** Produces `class ErrorDetail(ApiModel)` with one field, `detail: str`.

- [ ] Write `test_replay_routes_document_their_error_responses`, reading the committed snapshot: for `GET /api/market/data/{ticker}/{date}` and `GET /api/market/reference/{ticker}/{date}`, responses `404` and `503` each have `content["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorDetail"}`; for `POST /api/backtest/replay-trades` and `POST /api/style/mine-and-validate`, `503` has that schema and `404` is not listed; `components.schemas.ErrorDetail` has `required == ["detail"]` and `properties.detail.type == "string"`.
- [ ] Run: `python3 -m pytest tests/api/test_openapi_snapshot.py -q` (expect the new test FAIL: each route lists only 200 and 422).
- [ ] Add `ErrorDetail`. Add `responses={404: {"model": ErrorDetail}, 503: {"model": ErrorDetail}}` to the two GET decorators and `responses={503: {"model": ErrorDetail}}` to the two POST decorators. No other code is added to the document.
- [ ] Run: `python scripts/export_openapi.py`, then `python scripts/export_openapi.py --check` and `python3 -m pytest tests/api/test_openapi_snapshot.py -q` (expect 4 passed). `git diff --stat platform/api/openapi.json` shows only those four paths and the new schema.
- [ ] The render step.
- [ ] Commit: `fix(api): declare the 404 and 503 bodies of the replay routes`

## Task 11: The guard's three tree tests

Spec: Design 8 (reach test, local-dev test, `REPLAY_EXEMPT`). Advances done_when[12], [13]. Needs: Tasks 3 to 9.

**Files:** Modify `tests/meta/test_production_writers.py`.

**Interfaces:** Consumes Task 3's constants and functions.

- [ ] Write:
  - `test_replay_paths_reach_no_vendor_or_bucket_bar_fetch`: for every `REPLAY_PATH` item, `replay_reach_offenders(rel, src, entries, vendor_holders(sources), REPLAY_EXEMPT) == []`; the failure message lists every offender.
  - `test_local_dev_bucket_reads_sit_behind_the_unconfigured_check`: `local_dev_offenders` is empty for every file under `platform/api`, and each of the two local-dev functions is called at least once, so the test cannot pass on a tree that lacks them.
  - `test_the_only_replay_exemption_is_the_style_history_loader`: `list(REPLAY_EXEMPT) == [("platform/api/routers/backtest.py", "_style_history_bar_loader")]`; that function is defined; it is in the reach of `("mine_and_validate",)` and not in the reach of any other registered entry of the file; its body holds a call of `DataLoader`; the reach offenders of that file with `exempt={}` are not empty and every one names `_style_history_bar_loader`.
- [ ] Prove the reach test is red on `main`'s code: run `replay_reach_offenders` over the `origin/main` blobs (`git show origin/main:<rel>` for each `REPLAY_PATH` file, holders from the `origin/main` blobs of the four roots). Expect the eleven places of Task 3. Keep the output for the PR.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q` (expect all pass on the branch).
- [ ] Commit: `test(replay): hold the replay paths to the table with a reach test`

## Task 12: Whole suite and the generated inventory

Spec: done_when[16]. Advances done_when[16]. Needs: Tasks 2 to 11.

- [ ] Run: `make test` (expect no failure that `origin/main` does not have; see Global Constraints for the one known sandbox failure).
- [ ] Run the render step once more on the final code and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass). `git status` shows no change to the three docs; if it does, commit: `docs(infra): re-render the inventory for the replay bar routes`.
- [ ] Run: `git diff --stat origin/main -- gcp/deploy.sh gcp/backfill_ticker.py lib/data_loader.py` (expect empty).

## Task 13: Product record, site notes and the gate

Spec: Design 10; done_when[17]; product-delivery Phase 4 and Phase 5. Closes done_when[15] (posted) and [17]. Needs: Tasks 1 to 12. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/`, `tests/` or `platform/api` may change without redoing all four of them: the source hash covers those paths.

- [ ] Push with `git push -u origin fix/feat-replay-001-replay-bars-from-the-table` and open a draft PR. Title: `FEAT-REPLAY-001: replays read bars from the table or say they cannot`. Body: the spec path and this plan's path; the 18 done_when items, each as a `- [ ]` line that starts with the item's text; a Capacity section: Volume 0 rows written, each probe returns at most 1 row and the reference query at most 5; Velocity 2 probes per `/replay` and per script date, 1 SELECT per market data request, 1 per reference request (was 2 SELECTs, or 1 AlphaVantage call and 1 SELECT); Wall-clock the four execution times of Task 1, each probe bounded at 10 s; Cost no new job, schedule or write, 0 USD per run, fewer AlphaVantage calls and no `backfill-ticker` minutes. Paste Task 1's four plans with the execution id, and Task 11's red-on-main output.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-REPLAY-001` record only (not the table row at line 28): Status becomes `**Invalidated**; replays on Discord and the API read 1-min bars only from market_data_intraday or say they cannot ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed)`. Last reviewed becomes the date of the PR's head commit; the gate compares the two exactly, so set it again if a later commit lands on another day.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-REPLAY-001`: append `[#N](https://github.com/TeneikaAskew/stocks/pull/N) *remediation*` to its `**PR lineage:**` line, after the separator the line already uses between entries. No earlier entry is removed. Commit both docs and the plan: `docs(product): record the replay bar change under FEAT-REPLAY-001`.
- [ ] Site notes, step 1 (preflight). With every code and test commit in place and a clean tree, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`. It prints a JSON verdict and installs nothing yet (status `unverified`, exit 1). Copy its `source_identity_sha256`.
- [ ] Site notes, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes`, add nine rows `| FEAT-REPLAY-001 | <component> | source_identity_sha256=<that hash>; <text> |` in the table's sort order (after `FEAT-PLAYBOOK-001 | PLAYBOOK-09`, before `FEAT-SIGNAL-001 | CHARTS-06`), components in this order: CHARTS-02, CHARTS-03, CHARTS-08, DASHBOARD-03, DASHBOARD-04, JOURNAL-02, JOURNAL-04, LIVE-08, PLAYBOOK-05. Change no other byte. Each text is the sentence for its route, then the closing sentence:
  - market data (CHARTS-02, DASHBOARD-04, JOURNAL-02, LIVE-08): `GET /api/market/data/{ticker}/{date}` in `platform/api/main.py` (`get_market_data`, `_load_date_data`) reads 1-min bars only from `market_data_intraday` through the raising query helper: a day or month the table lacks is a 404 that starts `No 1-min bars for `, a malformed date a 404 that starts `Invalid date `, a database outage a 503 that starts `Could not read `, a defect a 500; the bucket parquet is read only when Cloud SQL is not configured and the yearly daily file is never read. Tests: `tests/api/test_platform_api.py::TestMarketDataAPI`, `tests/api/test_route_coverage.py`, `tests/meta/test_production_writers.py`.
  - reference (CHARTS-03, DASHBOARD-03, PLAYBOOK-05, LIVE-08): `GET /api/market/reference/{ticker}/{date}` (`get_reference_levels`) answers from one `market_data_daily` query, the newest row before the date with `week` from the same five rows, and no longer calls AlphaVantage: no row is a 404 that starts `No daily bar for `, an outage a 503 that starts `Could not read `, `source` is always `cloud_sql`, and `stale_days` keeps its rule. Tests: `tests/api/test_platform_api.py::TestReferenceAPI`, `tests/api/test_route_coverage.py`.
  - CHARTS-08: `POST /api/backtest/replay-trades` in `platform/api/routers/backtest.py` reads the journal through the raising query helper and answers 503 (`Could not read journal trades for ` or `Could not read 1-min bars for `) for a database outage and 500 for a defect; a date with no bars still comes back `unavailable` in a 200. Tests: `tests/lib/test_replay_labeled_trades.py`, `tests/api/test_route_coverage.py`.
  - JOURNAL-04: the same sentence for `POST /api/style/mine-and-validate` with `tests/lib/test_style_walk_forward.py`, plus: the walk-forward history read through `lib.data_loader.DataLoader` is unchanged and is the one exemption `tests/meta/test_production_writers.py` pins.
  - LIVE-08 carries both the market data and the reference sentence.
  - closing sentence, every row: `Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.`
  Commit: `docs(site): note the replay bar routes under nine components`.
- [ ] Site notes, step 3. Run the same `produce` command again; it now writes the sidecar. Commit: `docs(site): regenerate the source snapshot`.
- [ ] Site notes, step 4. Run `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched file later, bring the branch up to date and repeat steps 1 to 4 with the new hash in all nine rows (#1874 had to: commits 5d89d23d and e0ba3613).
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > /tmp/audit-branch.txt`; then `git worktree add --detach /tmp/audit-main origin/main`, run the same command there into `/tmp/audit-main.txt`, and `git worktree remove /tmp/audit-main`. Compare the `[P1]`, `[P2]` and `[P3]` finding lines: the branch reports none that `main` does not. A new finding is fixed or reported, not waived. The audit reads issue state through `gh`; exit code 2 means the run itself failed, not that the docs are clean.
- [ ] Run: `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Tick each done_when box in the PR body with its evidence beside it (test name, execution id, file), then mark the PR ready for review. Review cap: two rounds.

## Close-out (not tasks; owner's steps)

Copied from the spec's Close-out, in its order. Step 1 is before the merge; the rest follow it, each on the owner's yes. None of it is done by the implementer of this plan. Solyra was re-read at `main` 13dfa44 on 2026-11-13; where a step and that re-read disagree, the re-read is right: three `*.cloud.spec.ts` files exist and none is under `tests/charts/`; Charts has no ticker picker, so the run picks SPY on the Dashboard first; the Dashboard asks for reference levels as of the brief's daily date and falls back to today; earlier contract syncs are solyra PRs 317, 323 and 327, and PR 323 ran the sync against a stocks PR branch through `STOCKS_OPENAPI_REF`; `useReferenceLevels` now throws on a non-OK response, so only `PlaybookPage.tsx:79` still returns null; the Dashboard and Playbook lines moved to `DashboardPage.tsx:398-407` and `PlaybookPage.tsx:73-84`. Every solyra line is re-read at solyra `main` before it is acted on.

1. **Before the merge: the deployed-site run.** A `*.cloud.spec.ts` under solyra `tests/charts/`, under a solyra spec and plan of its own, approved and merged before this PR merges. It opens Charts for SPY on a session the table holds and on 2010-01-04, and the Dashboard and Playbook reference levels for today; asserts each response's status and `detail` or `source`; saves a screenshot of each state. The owner signs in with `npm run e2e:cloud:auth`, runs `npm run e2e:cloud`, and posts the before states on this PR. The 503 state is not in that spec; its proof is the API tests here and solyra's hermetic suite in step 5.
2. **Contract sync in solyra, the day of the merge.** One small solyra PR that runs `npm run contract:sync`, on a `fix/<feat-id>-<slug>` branch under a solyra spec and plan approved before this PR merges. It can be prepared from this branch through `STOCKS_OPENAPI_REF` and merges right after this PR. Until it merges, every solyra PR is red on `npm run contract:check`.
3. **Deploy** from `main`: the `discord-interactions` service and the API.
4. **Verify** on staging, results on the PR: `/replay` for a ticker the table does not hold replies with R1 and Cloud Run shows no `backfill-ticker` execution; `GET /api/market/data/SPY/{a session}` is 200, `/api/market/data/SPY/20100104` is 404 with A1, `GET /api/market/reference/SPY/{today}` is 200 with `source` `cloud_sql` (the requests carry the owner's Firebase ID token); the owner re-runs the step 1 spec and posts the after states.
5. **Solyra UI spec**, separate and later: show a 404 that starts `No 1-min bars for ` or `No daily bar for ` as "not in the table" and a 503 as "unavailable", by the Design 7 prefixes and not by the status alone; on `useReplayTrades` and `useMineMyStyle` only the 503 is new; change the Playbook reference read that returns null on a non-OK response; limit the `ReplayControl` calendar to the dates `GET /api/market/dates` lists; mocks and fixtures for both states in the hermetic suite.
6. **Docs**, on a `docs/` branch: `docs/product/infrastructure/05-a-ARCHITECTURE.md:788` (and `:583`, spec issue 5); the stale Chain, Data and Hosting cells of `docs/product/03-SITE-TRACEABILITY.md` the spec lists; `gcp/deploy.sh:5426` waits for a FEAT-DEPLOY-001 change.

Not in the spec's list, from product-delivery Phase 5 step 7: after the merge, on a `docs/` branch, set this plan's `status: done`.
