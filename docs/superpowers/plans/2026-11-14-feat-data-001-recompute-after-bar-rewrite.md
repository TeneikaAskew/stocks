---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-14-feat-data-001-recompute-after-bar-rewrite.md
branch: feature/feat-data-001-recompute-after-bar-rewrite
pr: null
status: ready
---

# Recompute paths for signal_alerts exits and the daily premarket fields: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [9].

**Goal:** The two result tables that had no recompute path get one each: `--re-resolve` on the end-of-day resolver rewrites resolver-written exits of `signal_alerts` and `trades`, and `--recompute-premarket` on the daily fetcher rewrites the premarket columns of `market_data_daily`, each with a dry run, a committed run behind `--commit`, a ledger row per overwrite and a `--revert-run`.

**Architecture:** One new module, `gcp/bar_recompute.py`, holds what both tools share: run identity, the proof check on bars, the write decision, the report, the per-group transaction (compare-and-set, then the ledger) and the revert. The resolver gains a bounded force mode that feeds each closed alert through the same `resolve_one` the scheduled path runs, and `resolve_one` now ends its walk at the session close. The fetcher's inline premarket block becomes `premarket_snapshot`, called by the nightly and by a bars-only mode.

**Tech Stack:** Python, pandas, SQLAlchemy `text()` with pg8000 through `gcp.database`, argparse, `google-cloud-storage`, pytest (`monkeypatch`, `caplog`), Postgres 15 in CI for `tests/integration/`.

**Spec:** docs/superpowers/specs/2026-11-14-feat-data-001-recompute-after-bar-rewrite.md (approved 2026-11-14, PR #1938)

## Global Constraints

- **Precondition.** The spec is `status: approved` on `origin/main` (PR #1938 merged). Until then the gate refuses every commit on this branch. Base: `origin/main` at 58d96807 or later. Commit this plan file first, alone: `docs(plan): FEAT-DATA-001 implementation plan for the recompute paths`.
- **Citations.** The spec cites 20d9c47b. This plan cites 58d96807, read on 2026-11-14.
  - Unchanged since 20d9c47b (`git diff --stat 20d9c47b 58d96807`), so the spec's lines hold: `gcp/signal_monitor_eod_resolver.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/database.py`, `gcp/schema.sql`, `gcp/deploy.sh`, `lib/eastern_time.py`, `lib/strat_levels.py`, `tests/gcp/test_signal_monitor_eod_resolver.py`, `tests/gcp/test_intraday_replace_months.py`.
  - Moved: the second copy of the premarket block in `gcp/backfill_ticker.py` is at `:495-545`, not `:505-560` (#1936). `tests/meta/test_production_writers.py` is 2,554 lines and 90 cases; the lines the spec cites (`:33-53`, `:439-440`) hold, and a new section (`:1328-2554`, #1936) reads this plan's code (see Guards).
  - No function the spec names changed shape.
- **Scope, copied from the spec.** SPY, QQQ and IWM only; any other ticker is refused before a query. No job, schedule or deploy change. No Discord message from either tool. `find_open_alerts` and its SQL text, `persist`, `_load_day`, `_control_query_ok` and `run()` are not edited.
- **Flags, copied.**
  - `python -m gcp.signal_monitor_eod_resolver --re-resolve --from YYYY-MM-DD --to YYYY-MM-DD [--tickers "SPY QQQ"] [--commit] [--report-dir PATH]`
  - `python -m gcp.fetchers.fetch_market_data --recompute-premarket --from YYYY-MM-DD --to YYYY-MM-DD [--tickers "SPY QQQ"] [--commit] [--report-dir PATH]`
  - `--revert-run RUN_ID [--commit] [--report-dir PATH]` on either entry point, for its own target.
  - `--tickers` is one space-separated value. Its default (unset on the resolver, `ALL` on the fetcher) means SPY, QQQ and IWM.
- **Names, copied.** Targets `signal-alert-exits` and `daily-premarket`. Ledger actions `recompute` and `revert`. Report: `gs://<GCS_BUCKET>/bar-recompute/v1/<target>/<run_id>/rows.csv` and `summary.json`; with `--report-dir PATH` the same two files under `PATH/bar-recompute/v1/<target>/<run_id>/`. `run_id` is `CLOUD_RUN_EXECUTION`, else `local-<UTC timestamp>`. Group log line: `RECOMPUTE-EXITS SPY 2026-05-01 candidates=120 changed=37 unchanged=83 refused=0` (the fetcher's reads `RECOMPUTE-PREMARKET SPY 2026-05 ...`).
- **Statuses.** Refused or left, exit 1: `unproven_rows`, `no_bars`, `bars_incomplete`, `daily_incomplete`, `changed_underneath`, `trade_diverged` (copied). Exit 0: `already_current` (copied), `trade_missing` (copied), and this plan's names for a row with nothing to report: `recomputed`, `reverted`, `would_revert`.
- **Exit codes, copied.** 0: finished and refused no row. 1: finished and at least one row was refused or left, or it failed. 2: refused before any query or write, with the reason on one line.
- **The write rule, copied.** `changed` is exact: any compared column differs, NULL-safe, no tolerance. Compared columns: for exits the four exit fields of the alert and of the trade; for premarket the ten value columns. Not compared: the marker column and `pre_fetched_at`. A row is written when its compared values differ from the stored ones, or when they are equal and its marker is NULL. Equal with a marker set is `already_current` and is not written. The compare-and-set `WHERE` and the ledger still cover every overwritten column, `pre_fetched_at` and the marker included.
- **Rule 3.7.** Every read the two tools make goes through `gcp.database.query_to_dataframe_strict` with no `timeout_s` and no `try` around it. Nothing added returns an empty container or a default on failure. The nightly's own swallowing reads are not changed; the two that move get a comment starting `# AUDIT-2026-05-13: silent fallback` that says why each is reachable.
- **Rule 0.** One statement per table per group. No `executemany`, no `MetaData.reflect`, no per-row statement. Budgets (Task 12 asserts them):

  | Run | schema check | ledger read | selection | daily reads | bar reads | parameter reads | writes | 27 or 24 groups |
  |---|---|---|---|---|---|---|---|---|
  | exits, committed | 1 | 1 | 1 | 0 | 1 a group | 0 | 3 a written group | 111, under 120 |
  | premarket, committed | 1 | 1 | 1 | 1 a ticker | 1 a group | 1 a distinct session date | 2 a written group | 228 with 150 dates, under 240 |

  A dry run makes no ledger read and no write.
- **Guards the new code must pass, unmodified.** Each was run against a skeleton of the strings below in planning.
  - `tests/meta/test_timezone_boundaries.py` and its baseline. It records hits by scope and expression, so three things in `gcp/signal_monitor_eod_resolver.py` must stay byte for byte: the module docstring (`:2-52`; one added line fails the test with a new `sql-utc-date` hit, run 2026-11-14), the expression `close_et.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)` inside `_eod_close_resolution` (`:366`), and `alert_ts.tz_localize(None)` inside `resolve_one` (`:299`). New code uses `.tz_convert(None)`, `lib.eastern_time.market_today()`, `utc_now()`, `localize_assuming_utc`, `eastern_bounds_utc` and `session_close`; it never calls `.tz_localize(None)`, `.replace(tzinfo=None)`, a zone-less `now()` or `today()`, `ZoneInfo("America/New_York")`, and no SQL it adds holds `CURRENT_DATE`, `DATE(col)` or `ts::date`.
  - `tests/meta/test_production_writers.py`. No file beyond the ones that guard already lists may hold the string `gcp.fetchers.fetch_market_data`, `gcp/fetchers/fetch_market_data.py`, or a job name (`fetch-market-data`, `fetch-alphavantage-intraday`, `intraday-bulk-backfill`) in a string constant outside a docstring. So `gcp/bar_recompute.py` and the resolver name neither. `gcp/bar_recompute.py` builds `UPDATE {table}` at run time, so it must hold no string constant equal to `market_data_intraday` or a partition name. `gcp/fetchers/fetch_market_data.py` holds that constant, so it must hold no statement with a write verb before run-time text. Every SQL string with `FROM signal_alerts` or `UPDATE signal_alerts` holds `run_kind`. No new code inserts into or upserts `signal_alerts` or `trades`. No new flag or environment name matches `REPLAY|AS_OF|--as-of|--replay|BACKTEST_|VALIDATE_(?:TICKER|DATE)|PLAYBOOK_RESOLVE_DATE`.
  - The strict-bar-loader lane (approved, no plan): in the resolver, new code calls no method or module function of `lib/data_loader.py`, holds no vendor request, and names the interval in its bar query.
  - `tests/meta/test_import_coverage.py`: `gcp/bar_recompute.py` imports with no side effect; `google.cloud` is imported inside the function that uploads.
- **Not in the PR's diff, copied.** `gcp/deploy.sh`, `gcp/signal_monitor.py`, `gcp/backfill_ticker.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `lib/eastern_time.py`, `lib/data_loader.py`, anything under `platform/api`, `CLAUDE.md`, `tests/meta/test_production_writers.py`, `tests/meta/test_timezone_boundaries.py`, `tests/fixtures/timezone_boundary_baseline.json`, `tests/gcp/test_intraday_writers_utc.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/gcp/test_premarket_filter_params.py`, `tests/gcp/test_premarket_filter_callers.py`, `tests/gcp/test_atr5_column.py`, `tests/integration/conftest.py`.
- **No production write and no deploy from this plan.** No schema apply, no committed recompute. Production is read only once, in Task 13, through `scripts/db_query_cr.sh` without `--commit`. The owner's steps are listed under Close-out.
- **Red then green, on the PR.** Each new test has a record: its failing run before the change (command, failing line), or, for a test that passes as soon as its function exists, the variant its task names, applied in a scratch edit, seen to fail and reverted. A variant is never committed.
- **Expected values are fixed here.** Where a task gives an expected number, it was run in planning. If the code disagrees, fix the code or stop and report; do not edit the expectation.
- **Integration tests locally.** `tests/integration/` needs a Postgres. This kind of container holds Postgres 16: `pg_ctlcluster 16 main start`, create a login role and a database as the `postgres` user, `psql -f gcp/schema.sql` into it (without `ON_ERROR_STOP` three pgvector statements fail locally; CI's image has the extension), then export `DB_HOST=localhost DB_PORT=5432 DB_USER=... DB_PASS=... DB_NAME=...`. Run 2026-11-14: `tests/integration/test_run_kind_constraints.py` and `test_schema_query_contract.py` gave 17 passed that way. The proof for done_when[3] and [5] is the CI job `integration-tests` (`.github/workflows/backtest-pipeline.yml:90-163`, Postgres 15). Drop the database and stop the cluster afterwards.
- **The render step.** A task that changes a file under `gcp/` ends with it:
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), then stage whichever of the three docs changed in the same commit. The blocks between `<!-- inventory:*:start/end -->` markers are never edited or merged by hand; after any merge of `main`, render again and commit what the render wrote.
- **The site snapshot is last.** It stops verifying whenever `main` moves or a watched file changes. The site notes and the snapshot are the last two commits before the final push, and all four site-note steps of Task 14 are redone after any merge of `main`.
- **Draft until closed.** The PR is opened as a draft and stays a draft until the close commits of Task 14 and the final body are pushed. Marking it ready starts the first of two review rounds; there is no third.
- **Whole suite in its normal order.** Judge by `make test`, not by a folder run.
- **Commits.** Run `python3 scripts/gate/spec_gate.py --commit` first. Conventional message, imperative, 72 characters or fewer. No AI attribution of any kind. Never rebase or force-push after the first push; bring the branch up to date by merging `origin/main`.
- **Other lanes** (read at 58d96807; if one has merged, merge `origin/main` before the task named).
  - Strict bar loader (approved, no plan): edits `_load_day` (`:175`), `_control_query_ok` (`:235`) and `run()` (`:543-572`) of the resolver and adds the file to `REPLAY_PATH`. This plan edits `resolve_one`, `_eod_close_resolution` and `main()`, and adds methods. Either order. Before Task 4.
  - Bucket copy (approved, plan in progress): edits `fetch_alphavantage_intraday.main` and declares `(FEAT-DATA-001, DASHBOARD-04)`. This plan changes two dictionary entries, one comment and one log line there. Before Task 11 and Task 14.
  - Time sweep stage 1 (approved with this spec in #1938, no plan): the spec's text names neither entry point; `gcp/fetchers/fetch_alphavantage_intraday.py` is on its list. Before Task 11.
  - Watched-ticker ingest v3 (plan `ready`, `pr: null`): edits `_run_backfill` and `_backfill_targets` of `gcp/fetchers/fetch_market_data.py`, and consumes `compute_and_upsert_daily_indicators(ticker, fetch_date, *, level_params)` and `read_level_params_for_run`, whose signatures this plan keeps. Before Task 8.
  - FEAT-INSIGHT-001 write routes 410 r2 (plan `ready`, `pr: null`) declares a `JOURNAL-01` row under its own capability, a different row of the same notes table, and regenerates the same snapshot file. Before Task 14.
- **Choices this plan makes** (each is reported to the owner with the plan; 1, 2 and 3 answer defects of the spec's text and are for the owner to confirm).
  1. `bar_recompute_ledger.action` is `VARCHAR(16)`. The spec's DDL says `VARCHAR(8)` and its own value `recompute` is nine characters. Run 2026-11-14 on Postgres 16: the insert fails with `value too long for type character varying(8)`.
  2. Three lines of `tests/gcp/test_intraday_replace_months.py` change, `:876`, `:877` and `:879`. done_when[6] says two, but `:877` asserts `"#1190" in adv["signal_alerts exits"]`, which the same item forbids. Run 2026-11-14 with only `:876` and `:879` changed: `:877` fails.
  3. `_eod_close_resolution` keeps its baselined expression and changes only how `close_et` is built (Task 4). The direct form removes a baseline entry, and done_when[7] says the baseline is unmodified. Run 2026-11-14: the direct form fails `tests/meta/test_timezone_boundaries.py` with `Baselined sites no longer occur`.
  4. `resolve_one(alert, bars=None)`: the force mode hands its frame in. The scheduled call is unchanged.
  5. The schema check runs for a dry run too. A missing ledger or marker column is exit 2 in every mode, because the selection reads the marker.
  6. The alert selection left-joins the live `trades` row, so the trade's stored exit is read in the same query. A trade is its alert's mirror when exit time, price and reason are equal, NULL-safe (the three the spec measured). `return_pct` is compared and written but is not part of the mirror test.
  7. The premarket selection requires a close (done_when[4], Design 1). `daily_incomplete` is a session for which the daily read holds fewer than two rows up to that date, or whose last row is not that date (Design 5 says "a selected row with no close", which the selection never returns).
  8. Ledger `old_values` and `new_values` are keyed by table name for both targets: `{"signal_alerts": {...}, "trades": {...} or null}` and `{"market_data_daily": {...}}`.
  9. A flag of one of the two modes given without the mode (`--from`, `--to`, `--tickers` on the resolver, `--commit`, `--report-dir`), a malformed date, and a comma inside `--tickers` are exit 2. `--report-dir` wins over `GCS_BUCKET`.
  10. A candidate alert with a NULL `time_stop_minutes` raises, naming the alert, like the three inputs the spec lists. The scheduled path's `or 30` default is not used to rewrite a stored exit.
  11. A dry `--revert-run` reads only the ledger and reports `would_revert`; it cannot say `changed_underneath`. A run id with no ledger row for the target is exit 1, one line, no write.
  12. The premarket read is one statement a (ticker, month) with one `VALUES` window a session joined to the bars. Run 2026-11-14 on synthetic rows: a nested loop with an index scan of 330 rows a loop, the shape the spec measured; one range over the month read 3,210 rows for 1,320 wanted.
  13. The pre-merge `EXPLAIN` of the alert selection replaces the two marker columns with `NULL::text`, because production does not hold them until the owner's schema apply.
  14. `premarket_snapshot` takes `prior` from a new strict helper, `prior_session_inputs`, used by the nightly too, so the two cannot drift.
  15. Review Focus adds tests the spec's counts do not include.

## What changes in production, and when

- At the merge: nothing. No file under `platform/` changes; a job keeps its image until its `deploy_*` function runs.
- From the owner's `./gcp/deploy.sh eod-resolver`: the scheduled 16:30 ET resolver ends its walk at the session close. An alert fired in the last minutes resolves to `eod_close` where it would have been a `time_stop` after the close, and a same-day run that finds only premarket bars leaves the alert open. A session whose stored bars stop more than five minutes before the close leaves its open alerts unresolved and the job exits 1 for it.
- From the owner's `./gcp/deploy.sh market-data`: the nightly and the 08:20 refresh run the image that holds `premarket_snapshot`. The nightly's row is what it is today (Task 8 pins it with the existing tests, unmodified).
- From the owner's `./gcp/deploy.sh fetchers`: a committed replace prints the two commands in its `RECOMPUTE` lines.
- Neither tool runs unless the owner starts it. Each committed run is under one cent (spec, Capacity).

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | selection, flags and refusals of `--re-resolve` | 5 (schema refusal: 1, 3) |
| [1] | the proof-requiring day read and the dry run | 6 (2 for the shared parts) |
| [2] | the walk ends at the session close | 4 |
| [3] | committed exits and revert on real Postgres | 7 (1, 3) |
| [4] | `premarket_snapshot`, the premarket selection, reads and dry run | 8, 9 |
| [5] | committed premarket and revert on real Postgres | 10 (1, 3) |
| [6] | the replace's RECOMPUTE lines | 11 |
| [7] | `make test`, the files left alone, the OpenAPI check | 13 |
| [8] | the PR-body measurements | 12 (local), 13 (production, read-only) |
| [9] | product record, site notes, snapshot, inventory, audit, gate | 14 (render in every `gcp/` task) |

Where the five points corrected on 2026-11-14 are tested:

| Point | Test | Task |
|---|---|---|
| 1. The write decision compares value columns only | `test_a_fresh_read_time_never_makes_a_write` (unit); `test_a_second_run_at_a_later_instant_writes_nothing` (Postgres) | 2; 10 |
| 2. The per-run check counts markers equal to the run's id; coverage is separate | `test_markers_per_run_and_coverage_are_two_checks`, once a target | 7; 10 |
| 3. The trade follows its alert | `test_the_trade_follows_its_alert` (`write_group`); `test_an_alert_changed_underneath_leaves_its_trade` (through `main`) | 3; 7 |
| 4. `eod_close` is stamped with the close and priced from the last bar before it | the five cases of Task 4; `test_the_stored_exit_is_the_deciding_bars_close` | 4; 7 |
| 5. A retry reads its own ledger rows before its first save | `test_report_rows_come_from_the_ledger_for_keys_it_holds` (unit); `test_a_retry_under_the_same_run_id_reports_from_the_ledger` (Postgres) | 3; 10 |

## Review Focus

Inputs the spec implies and no done_when test pins. Each has a test in the task that owns the code.

- A column that is NULL on one row and set on another comes back from pandas as `float64` with `NaN`, and an integer column comes back as a float. 147 of each ticker's 149 premarket rows hold such NULLs. Expected: the row is written. Run 2026-11-14: sending the `NaN` fails with `invalid input syntax for type bigint: "nan"`, sending `7654321.0` fails the same way, and `NULL IS NOT DISTINCT FROM 'NaN'` is false, so a float column would report every such row `changed_underneath`. Tasks 2 and 3.
- `resolve_one` returns a naive UTC `exit_ts`; the stored one is an aware instant. Expected: an exit equal to the stored one reports `changed` false, and the value bound to the statement is aware UTC. Task 6.
- A candidate alert whose `time_stop_minutes` is NULL, read back as `NaN` beside other rows' integers. Expected: the run raises naming the ticker and the alert, not `cannot convert float NaN to integer` from inside the walk. Task 6.
- `--tickers "spy qqq"`, `--tickers SPY,QQQ`, `--from 2026-5-1x`. Expected: the first covers SPY and QQQ; the other two are exit 2 before any query, with no traceback. Tasks 2, 5 and 9.
- `--revert-run` with an id that has no ledger row for this entry point's target (a typo, or an exits run id given to the fetcher). Expected: exit 1, one line naming the id and the target, no transaction. Tasks 7 and 10.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/schema.sql` | the ledger table and three marker columns, appended | 1 |
| `gcp/bar_recompute.py` | new: identity, proof, values, decision, report, write, ledger, revert | 2, 3 |
| `gcp/gcs_utils.py` | `upload_text_to_gcs` and `_storage_client`, appended | 2 |
| `gcp/signal_monitor_eod_resolver.py` | `resolve_one`, `_eod_close_resolution`, `main`; new methods | 4, 5, 6, 7 |
| `gcp/fetchers/fetch_market_data.py` | `premarket_snapshot`, `prior_session_inputs`; flags; the bars-only mode; `sys.exit(main())` | 8, 9, 10 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | two entries, one comment, one log line | 11 |
| `tests/gcp/test_bar_recompute_schema.py`, `tests/gcp/test_bar_recompute.py`, `tests/gcp/test_recompute_exits.py`, `tests/gcp/test_recompute_premarket.py` | new | 1, 2, 3, 5, 6, 8, 9, 11 |
| `tests/gcp/test_signal_monitor_eod_resolver.py` | two fixture moves (11 lines), the five cases of done_when[2], a sixth for the boundary, one helper | 4 |
| `tests/gcp/test_intraday_replace_months.py` | `:876`, `:877`, `:879` | 11 |
| `tests/integration/test_bar_recompute_writes.py` | new | 3, 7, 10, 12 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 1 to 11 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 14 |

## Task 1: The ledger table and the marker columns

Spec: Design 2 ("The ledger"); decision 5. Advances done_when[3], [5] (their tables) and [0] (the names the absent-schema refusal reads). Needs: nothing.

**Files:** Modify `gcp/schema.sql` (append after `:5480`). Create `tests/gcp/test_bar_recompute_schema.py`.

**Interfaces:** Produces the table `bar_recompute_ledger` and the columns `signal_alerts.exit_recompute_run`, `trades.exit_recompute_run`, `market_data_daily.pre_recompute_run`, all `TEXT`, all nullable. The DDL is the spec's block (Design 2), copied, with one change: `action VARCHAR(16)` (choice 1). No index beyond the `UNIQUE (run_id, target, ticker, row_key)`, whose leading column serves the read by run.

- [ ] Write, reading `gcp/schema.sql` as text:
  - `test_the_ledger_and_the_markers_are_declared`: the text holds `CREATE TABLE IF NOT EXISTS bar_recompute_ledger`, each of the twelve column names of the spec's block inside that statement, `UNIQUE (run_id, target, ticker, row_key)`, and the three `ADD COLUMN IF NOT EXISTS` lines.
  - `test_the_action_and_target_columns_hold_their_values`: the `N` of `action VARCHAR(N)` is at least `len("recompute")` and the `N` of `target VARCHAR(N)` at least `len("signal-alert-exits")`.
  - `test_the_block_is_four_statements_for_the_applier`: `gcp.apply_schema.split_statements` of the appended block gives four statements.
- [ ] Run: `python3 -m pytest tests/gcp/test_bar_recompute_schema.py -q` (expect FAIL: the table is not declared). Record for [3] and [5].
- [ ] Append the block, under a comment that names FEAT-DATA-001, this spec and what a NULL marker means.
- [ ] Run again (expect 3 passed), then `python3 -m pytest tests/gcp/test_apply_schema.py tests/gcp/test_apply_schema_trigger.py -q` (expect 114 passed).
- [ ] Variant for the record: `action VARCHAR(8)`; expect the second test to fail; revert.
- [ ] The render step. Commit: `feat(data): add the bar recompute ledger and marker columns`

## Task 2: `gcp/bar_recompute.py`: identity, proof, values, decision, report

Spec: Design 2 ("Run identity", "Proof before placement", "The dry run", "Exit codes"), Design 7. Advances done_when[1], [4]. Needs: nothing.

**Files:** Create `gcp/bar_recompute.py`, `tests/gcp/test_bar_recompute.py`. Modify `gcp/gcs_utils.py` (append).

**Interfaces:** Produces, in `gcp/bar_recompute.py`:
- `ALLOWED_TICKERS = ("SPY", "QQQ", "IWM")`, `TARGET_EXITS = "signal-alert-exits"`, `TARGET_PREMARKET = "daily-premarket"`, `REFUSED_STATUSES` (the six), `BUILD_INFO_PATH` (`gcp/build_info.json` beside the module).
- `class Refusal(Exception)`: `str(e)` is the one-line reason. An entry point logs it and returns 2.
- `class UnprovenRows(Exception)` with `.unproven: int` and `.rows: int`.
- `run_id() -> str`; `code_version() -> dict` with keys `git_commit`, `git_dirty`, `built_at`, all `None` when the file is absent.
- `parse_window(tickers: str | None, first: str | None, last: str | None, today: date) -> tuple[list[str], date, date]`. `None` or `ALL` for tickers means the three. Raises `Refusal`.
- `require_proven(ts, inserted_at) -> None`: raises `UnprovenRows` unless every row is proven by `lib.eastern_time.proven_true_utc`. Nothing is inferred; `stored_intraday_to_eastern` is not called.
- `bars_basis(bars: pd.DataFrame) -> dict` with `rows`, `first_ts`, `last_ts`, `inserted_min`, `inserted_max`, `sha256`. The digest is over one line a row in `ts` order, joined by `\n`, UTF-8: `<ts as %Y-%m-%dT%H:%M:%S.%f>+00:00|<repr(open)>|<repr(high)>|<repr(low)>|<repr(close)>|<volume as int, empty when NULL>`.
- `db_value(value, sqltype: str)`: what is bound to a statement. `None`, `NaN`, `NaT` and `pd.NA` give `None`; `bigint` and `integer` give `int`; `timestamptz` gives an aware UTC `datetime` (a naive one is read as UTC through `localize_assuming_utc`); `jsonb` gives JSON text (a `str` passes through, a `dict` is dumped with sorted keys).
- `json_value(value)`: what the ledger and the CSV hold. A float stays a JSON number (`json.dumps` writes the shortest text that reads back to the same float; `allow_nan=False`), a time is `%Y-%m-%dT%H:%M:%S.%f+00:00`, a date is ISO.
- `same(a, b) -> bool`: exact and NULL-safe; two times compare as instants; two JSON values compare after `json.loads`.
- `decide(old: dict, new: dict, marker, compared: tuple[str, ...]) -> tuple[bool, bool]`: `(changed, write)` by the write rule.
- `@dataclass ReportRow`: `ticker`, `session_date`, `row_key`, `old: dict`, `new: dict | None`, `changed: bool | None`, `status: str`, `bars_rows: int | None`, `bars_sha256: str | None`, `written: bool = False`.
- `rows_csv(rows, columns: tuple[str, ...]) -> str`: header `ticker,session_date,row_key,old_<c>...,new_<c>...,changed,status,bars_rows,bars_sha256,written`, written with the `csv` module.
- `save_report(target: str, run_id: str, csv_text: str, summary: dict, report_dir: str | None) -> str`: raises `Refusal` with neither a directory nor `GCS_BUCKET`; an upload that fails raises.
- `exit_code(rows) -> int`: 1 when any status is in `REFUSED_STATUSES`, else 0.

In `gcp/gcs_utils.py`: `_storage_client()` and `upload_text_to_gcs(bucket: str, blob_path: str, text: str, content_type: str) -> str` (the `gs://` URL). No `try`: unlike its three siblings in the file, it raises.

- [ ] Write `tests/gcp/test_bar_recompute.py`:
  - `test_run_id_is_the_execution_or_a_local_stamp`: with `CLOUD_RUN_EXECUTION=fetch-market-data-abc12` it is that; unset, it matches `^local-\d{8}T\d{6}Z$`.
  - `test_code_version_reads_the_image_stamp`: with `BUILD_INFO_PATH` pointed at a file holding `{"git_commit": "abc", "git_dirty": false, "built_at": "2026-11-14T00:00:00Z"}` it returns those three; pointed at a missing file, three `None`.
  - `test_parse_window`: `(None, "2026-10-01", "2026-10-06", date(2026, 11, 14))` gives `(["SPY", "QQQ", "IWM"], date(2026, 10, 1), date(2026, 10, 6))`; `"ALL"` the same; `"spy qqq"` gives `["SPY", "QQQ"]` (Review Focus). `Refusal` for `"AMD"`, `"SPY,QQQ"`, a missing `first`, a missing `last`, `first` after `last`, `last` equal to `today`, `last` after `today`, and `first="2026-5-1x"` (Review Focus).
  - `test_require_proven`: rows on 2026-09-24 inserted 2026-11-14 pass; one of them inserted 2026-09-24 raises `UnprovenRows` with `unproven == 1`; a row on 2026-10-06 with an insert time of 2026-05-01 passes (proven by its date).
  - `test_bars_basis`: two literal rows; `sha256` equals `hashlib.sha256` of the two lines written out in the test; `rows == 2`.
  - `test_values_bound_to_a_statement` (Review Focus): `db_value(float("nan"), "double precision") is None`; `db_value(pd.NaT, "timestamptz") is None`; `db_value(np.float64(7654321.0), "bigint") == 7654321` and is an `int`; `db_value(datetime(2026, 10, 6, 20, 0), "timestamptz")` is aware and equals 20:00 UTC; `db_value({"b": 1, "a": 2}, "jsonb") == '{"a": 2, "b": 1}'`; `db_value('{"x": 1.0}', "jsonb") == '{"x": 1.0}'`.
  - `test_a_fresh_read_time_never_makes_a_write` (corrected point 1): with `compared` the ten value columns, `old` and `new` equal on all ten and different on `pre_fetched_at`: marker `"run-1"` gives `(False, False)`; marker `None` gives `(False, True)`; `new["pre_high"]` different gives `(True, True)`; `old` 0.30000000000000004 against `new` 0.3 gives `(True, True)`; `None` against `None` is equal and `None` against `0.0` is not.
  - `test_save_report`: with `report_dir=tmp_path` the two files exist under `bar-recompute/v1/daily-premarket/run-1/` and `summary.json` loads; with `GCS_BUCKET=b` and no directory, `upload_text_to_gcs` (patched) is called for `bar-recompute/v1/daily-premarket/run-1/rows.csv` and `.../summary.json`; when it raises `ConnectionError`, that object propagates; with neither, `Refusal`.
  - `test_upload_text_raises`: `_storage_client` patched to a client whose upload raises `ConnectionError`; the same object propagates.
  - `test_rows_csv`: the header is as above for two columns; a `None` is an empty cell, a float is its `repr`, a time is the ledger's text form, and a refused row has empty `new_` cells and an empty `changed`.
  - `test_exit_code`: `[recomputed, already_current, trade_missing]` gives 0; adding one `no_bars` gives 1.
- [ ] Run: `python3 -m pytest tests/gcp/test_bar_recompute.py -q` (expect FAIL: no module).
- [ ] Implement. `run_id` takes its stamp from `lib.eastern_time.utc_now()`.
- [ ] Run again (expect all pass), then `python3 -m pytest tests/meta/test_timezone_boundaries.py tests/meta/test_import_coverage.py -q` (expect all pass).
- [ ] Variants for the record: make `decide` compare `pre_fetched_at` and expect `test_a_fresh_read_time_never_makes_a_write` to fail on its first assertion; wrap the upload in `try` returning `""` and expect `test_upload_text_raises` to fail. Revert both.
- [ ] The render step. Commit: `feat(data): add the shared bar recompute module`

## Task 3: `gcp/bar_recompute.py`: the group write, the ledger, the revert

Spec: Design 2 ("The committed run", "The ledger", "The revert"), Design 1 (the trade follows its alert). Advances done_when[3], [5]. Needs: Tasks 1, 2.

**Files:** Modify `gcp/bar_recompute.py`, `tests/gcp/test_bar_recompute.py`. Create `tests/integration/test_bar_recompute_writes.py`.

**Interfaces:** Produces:
- `@dataclass(frozen=True) TableSpec`: `table`, `alias`, `keys: dict[str, str]`, `columns: dict[str, str]` (every overwritten column but the marker, name to SQL type), `marker`, `fixed: str = ""`. Every identifier must match `^[a-z_][a-z0-9_]*$`, else `ValueError`.
- `ALERT_EXITS`: `signal_alerts`, alias `a`, keys `ticker varchar`, `alert_ts timestamptz`; columns `exit_ts timestamptz`, `exit_reason varchar`, `exit_price double precision`, `exit_return_pct double precision`; marker `exit_recompute_run`; fixed `a.run_kind = 'live' AND a.is_open IS FALSE`.
- `TRADE_EXITS`: `trades`, alias `t`, keys `ticker varchar`, `entry_time timestamptz`; columns `exit_time timestamptz`, `exit_price double precision`, `exit_reason varchar`, `return_pct double precision`; marker `exit_recompute_run`; fixed `t.run_kind = 'live'`.
- `DAILY_PREMARKET`: `market_data_daily`, alias `d`, keys `ticker varchar`, `date date`; columns `pre_high`, `pre_low`, `pre_vwap`, `gap_pct`, `pre_range_atr` (`double precision`), `pre_volume bigint`, `pre_fetched_at timestamptz`, `pre_excluded_stale_prints integer`, `pre_excluded_spikes integer`, `pre_filter_status varchar`, `pre_filter_params jsonb`; marker `pre_recompute_run`.
- `PREMARKET_COMPARED`: the ten columns of `DAILY_PREMARKET` without `pre_fetched_at`.
- `@dataclass TableWrite`: `spec`, `key: dict`, `old: dict` (every column and the marker, as read), `new: dict` (every column).
- `@dataclass WriteUnit`: `ticker`, `session_date`, `row_key`, `primary: TableWrite`, `follower: TableWrite | None`, `changed: bool`, `basis: dict`.
- `schema_missing() -> list[str]`: one strict query on `information_schema.columns`; the names missing among `bar_recompute_ledger` and the three marker columns.
- `compare_and_set_sql(spec: TableSpec, n: int) -> str`.
- `write_group(engine, *, target: str, action: str, run_id: str, units: list[WriteUnit]) -> dict[str, tuple[bool, bool | None]]`: `row_key` to (primary written, follower written, `None` when the unit has no follower). One `engine.begin()`.
- `ledger_of_run(run_id: str, target: str) -> list[dict]`: one strict read, ordered by `id`; each dict holds `ticker`, `session_date`, `row_key`, `action`, `old_values`, `new_values`, `changed`.
- `revert_units(ledger_rows: list[dict], target: str) -> list[WriteUnit]`: old is that run's `new_values` with that run's id as the marker, new is its `old_values`; a follower that is null in the ledger is not reverted.
- `finish_run(*, target, run_id, commit: bool, action: str, rows: list[ReportRow], groups: list[tuple[str, list[WriteUnit]]], summary: dict, csv_columns: tuple[str, ...], report_dir: str | None) -> int`: the exit code.

What the signatures do not determine:
- The statement, one a table a group, every `v.` reference cast to the column's type (run 2026-11-14: without the casts Postgres answers `operator does not exist: date = text`):

  ```sql
  UPDATE <table> AS <alias>
     SET <col> = v.new_<col>::<type>, ..., <marker> = :run_id
    FROM (VALUES (:r0_<key>, ..., :r0_old_<col>, ..., :r0_old_marker, :r0_new_<col>, ...), (...)) AS v(<key>, ..., old_<col>, ..., old_marker, new_<col>, ...)
   WHERE <alias>.<key> = v.<key>::<type> AND ...
     AND <alias>.<col> IS NOT DISTINCT FROM v.old_<col>::<type> AND ...
     AND <alias>.<marker> IS NOT DISTINCT FROM v.old_marker::text
     AND <fixed>
  RETURNING <alias>.<key>, ...
  ```
- `write_group` in order: the statement for the primaries; then, only for the units the first statement returned and that have a follower, the statement for the followers; then one multi-row `INSERT INTO bar_recompute_ledger`, one row a returned primary, with `CAST(:x AS JSONB)` for the three JSON columns. In a ledger row the follower's object is null when the unit had none or the second statement did not return it. No statement runs for an empty list; a group in which the first statement returns nothing runs one statement.
- `finish_run` in order: with `commit`, read `ledger_of_run` once; for each key the ledger holds, replace the report row with one built from the ledger (its `old_values`, `new_values`, `changed`, status `recomputed` or `reverted`, `written` true) and drop its unit. Save the report. With `commit`, write each group through `write_group` and fill each row: a returned primary is `written` true; a primary that was not returned is `changed_underneath`; a returned primary whose follower was not returned is `trade_diverged`. Save the report again. Return `exit_code`. A dry run calls neither `ledger_of_run` nor `get_engine`. An exception from a group propagates; the groups before it stay committed.

- [ ] Write in `tests/gcp/test_bar_recompute.py`:
  - `test_the_statement_casts_and_compares_every_column`: `compare_and_set_sql(ALERT_EXITS, 2)` starts `UPDATE signal_alerts AS a`, holds `a.run_kind = 'live'`, holds `IS NOT DISTINCT FROM v.old_<c>::` for each of the four columns and `v.old_marker::text`, holds two value tuples, and ends `RETURNING a.ticker, a.alert_ts`; `TableSpec("x; DROP", ...)` raises `ValueError`.
  - `test_schema_missing_names_what_is_absent`: with the strict reader patched to answer every row but `trades.exit_recompute_run`, the result is `["trades.exit_recompute_run"]`; a reader raising `ConnectionError` propagates.
  - `test_report_rows_come_from_the_ledger_for_keys_it_holds` (corrected point 5): `finish_run(commit=True, ...)` with `ledger_of_run` patched to hold key K, `write_group` patched to record, and a fresh row for K whose status is `already_current`: the saved CSV's row for K has the ledger's old and new values, `written` true and a status that is not `already_current`; K's unit is not passed to `write_group`; `ledger_of_run` was called once and before the first `save_report`. With `commit=False`, `ledger_of_run` and `get_engine` raise if called and are not.
  - `test_a_failed_report_stops_before_any_write`: with `save_report` raising `ConnectionError`, `finish_run(commit=True, ...)` raises that object and `write_group` is not called.
  - `test_revert_units_swap_old_and_new`: from one ledger row, the unit's `old` is the row's `new_values` with the run's id as marker and its `new` is the `old_values`; a null `trades` object gives `follower is None`.
- [ ] Write `tests/integration/test_bar_recompute_writes.py` with a fixture `recompute_db(db_engine)` that truncates `signal_alerts`, `trades`, `market_data_daily`, `market_data_intraday`, `bar_recompute_ledger` and `ticker_level_params`, and a helper `row(table, where) -> dict` returning every column. Tests, on `write_group` directly:
  - `test_the_schema_is_ready`: `schema_missing() == []`.
  - `test_the_trade_follows_its_alert` (corrected point 3): three live alerts with mirror trades (one `alert_ts` with microseconds, one exit price `0.1 + 0.2`); units built from a read; then `UPDATE signal_alerts SET exit_price = 999.0` on the third. Result: the first two are `(True, True)`, the third `(False, False)`; the third's alert and trade rows are equal in every column to what they were after the other writer's change; the ledger holds two rows and none for the third.
  - `test_a_trade_changed_underneath_leaves_only_the_trade`: the same with the change on the third trade: `(True, False)`, its alert is written, its ledger row holds `"trades": null` in both objects.
  - `test_nulls_and_integers_are_written` (Review Focus): two daily rows, one with `pre_volume`, `pre_range_atr` and `pre_excluded_spikes` NULL and one with them set, read back through `query_to_dataframe_strict`; both are written, and a new value of `None` is stored as NULL.
  - `test_the_ledger_refuses_a_second_row_for_a_key`: units rebuilt from a fresh read and written again under the same run id raise on the ledger's unique key, and the transaction leaves both tables as they were.
  - `test_one_statement_a_table_and_no_executemany`: with a `before_cursor_execute` listener, a group of 40 units with followers is three statements and none has `executemany` true.
- [ ] Run both files (expect FAIL: names not defined). Record for [3] and [5].
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/gcp/test_bar_recompute.py -q` and, against the local Postgres, `python3 -m pytest tests/integration/test_bar_recompute_writes.py -q` (expect all pass).
- [ ] Variant for the record (corrected point 3): pass every unit's follower to the second statement instead of the returned ones; expect `test_the_trade_follows_its_alert` to fail on the third trade's row. Planning run of 2026-11-14 on Postgres 16 with this statement: keyed from `RETURNING`, the third trade stayed; keyed independently, it was rewritten beside the other writer's alert. Revert.
- [ ] `python3 -m pytest tests/meta/test_production_writers.py -q` (expect 90 passed). The render step. Commit: `feat(data): write recompute groups by compare-and-set with a ledger`

## Task 4: The walk ends at the session close

Spec: Design 4; decisions 2 and 12. Advances done_when[2]. Needs: nothing. Applies to the scheduled path too.

**Files:** Modify `gcp/signal_monitor_eod_resolver.py` (`:66`, `:78`, `:290-376`), `tests/gcp/test_signal_monitor_eod_resolver.py` (`:167-178`, `:197-206`, new cases at the end).

**Interfaces:** `resolve_one(self, alert: pd.Series, bars: pd.DataFrame | None = None) -> Optional[dict]` (choice 4): with `bars` given it does not call `_load_day`. `_eod_close_resolution(...) -> Optional[dict]`. Produces `EOD_CLOSE_REACH = timedelta(minutes=5)`.

What the signatures do not determine:
- In `resolve_one`, after the empty-frame return (so a day with no bars never asks the calendar): `close_utc = pd.Timestamp(session_close(alert_date)).tz_convert(None)`; the walk is over the bars at or after the alert and before `close_utc`; both calls of `_eod_close_resolution` pass the bars before `close_utc`. Line `:299` is not touched.
- In `_eod_close_resolution`: `close_et = session_close(alert_date).astimezone(_ET)`, then line `:366` unchanged (choice 3). It returns `None` when the frame it is given is empty or its last index is before `close_utc_naive - EOD_CLOSE_REACH`. The price is the close of that frame's last bar. `_SESSION_CLOSE_ET` (`:78`) goes; nothing else reads it.
- The module docstring is not edited (Guards).

- [ ] Add a helper `_session_frame(resolver, day, first_et, last_et, closes=None)` to the test file: one bar a minute from `first_et` to `last_et` Eastern, naive UTC index, close `100.00` on even minutes and `100.02` on odd ones (the RSI settles near 50 after the first bars, and every case fires hours after them), `closes` overriding by `"HH:MM"` Eastern, and the RSI column computed as `_load_day` computes it. Each new case runs `resolve_one` under `patch.object(EODResolver, "_load_day", return_value=frame)` and stubs no loader method.
- [ ] Write five cases (values from the planning run of 2026-11-14 on this fixture; beside each, what `main` returns today):
  - `test_a_late_call_resolves_to_eod_close`: bars 09:30 to 19:59 on 2026-10-06, CALL at 19:50:00 UTC, entry 100.0, target 110.0, stop 30. `exit_reason == "eod_close"`, `exit_ts == datetime(2026, 10, 6, 20, 0)`, `exit_price == 100.02`. Today: `time_stop` at 20:20 UTC.
  - `test_a_target_only_after_hours_is_not_an_exit`: the same with `closes={"19:59": 111.0}` and stop 600. `eod_close` at 20:00 UTC, 100.02. Today: `target_hit` at 23:59 UTC.
  - `test_premarket_bars_alone_do_not_resolve`: bars 04:00 to 07:37, PUT at 13:50:09 UTC. `None`. Today: `eod_close` at the 07:37 close.
  - `test_bars_that_stop_early_do_not_resolve`: bars 09:30 to 15:40, CALL at 19:30:07 UTC, target 110.0, stop 600. `None`. Today: `eod_close`.
  - `test_a_half_day_ends_at_one`: bars 09:30 to 16:30 on 2026-11-27, `closes={"13:10": 111.0}`, CALL at 17:50:07 UTC, stop 600. `eod_close`, `exit_ts == datetime(2026, 11, 27, 18, 0)`, 100.02. Today: `target_hit` at 18:10 UTC.
- [ ] Write a sixth, `test_the_five_minute_rule_at_its_boundary`, CALL at 19:30:07 UTC, target 110.0, stop 600: bars to 15:55 resolve to `eod_close` with the 15:55 close, 100.02; bars to 15:54 return `None`; and with `closes={"15:35": 110.5}` on bars that stop at 15:40 the result is `target_hit` at 19:35 UTC (a stored bar is real).
- [ ] Run: `python3 -m pytest tests/gcp/test_signal_monitor_eod_resolver.py -q` (expect the six new tests to FAIL, the first five as listed, and 30 passed). Record for [2].
- [ ] Move two fixtures, assertions unchanged: in `test_resolve_one_eod_close_fallback` the five bars become 19:55 to 19:59 UTC and `alert_ts` 19:55:00; in `test_resolve_one_eod_close_when_alert_after_last_bar` the four bars become 19:55 to 19:58 UTC and `alert_ts` 19:59:00. Eleven lines. Both pass before and after the change (run 2026-11-14).
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/gcp/test_signal_monitor_eod_resolver.py tests/meta/test_timezone_boundaries.py -q` (expect 36 and 6 passed). Planning run of the same edit: with the fixtures unmoved, exactly those two of the 30 fail.
- [ ] The render step. Commit: `fix(data): end the resolver's walk at the session close`

## Task 5: `--re-resolve`: flags, refusals, selection

Spec: Design 3 (selection, refused before any query), Design 7. Advances done_when[0]. Needs: Tasks 2, 3.

**Files:** Modify `gcp/signal_monitor_eod_resolver.py` (`main`, `:591-620`; one new method and one constant on the class). Create `tests/gcp/test_recompute_exits.py`.

**Interfaces:** Produces:
- `EODResolver.find_resolved_alerts(self, tickers: list[str], first: date, last: date) -> pd.DataFrame`: one `query_to_dataframe_strict` call with `RESOLVED_ALERTS_SQL` and `{"tickers": tickers, "first": first, "last": last}`.
- `main()` flags: `--re-resolve`, `--from` (`dest="first"`), `--to` (`dest="last"`), `--tickers`, `--commit`, `--revert-run RUN_ID`, `--report-dir PATH`. With neither `--re-resolve` nor `--revert-run`, and none of the other new flags, `main()` is the scheduled path, line for line.
- The text, which the tests pin:

  ```sql
  SELECT a.ticker, a.alert_ts, a.alert_date, a.direction, a.price_at_signal, a.target_price,
         a.time_stop_minutes, a.exit_ts, a.exit_reason, a.exit_price, a.exit_return_pct,
         a.exit_recompute_run,
         t.entry_time IS NOT NULL AS trade_found, t.exit_time AS trade_exit_time,
         t.exit_price AS trade_exit_price, t.exit_reason AS trade_exit_reason,
         t.return_pct AS trade_return_pct, t.exit_recompute_run AS trade_exit_recompute_run
    FROM signal_alerts a
    LEFT JOIN trades t
      ON t.ticker = a.ticker AND t.entry_time = a.alert_ts AND t.run_kind = 'live'
   WHERE a.run_kind = 'live' AND a.is_open IS FALSE AND a.exit_ts IS NOT NULL
     AND a.exit_ts = date_trunc('minute', a.exit_ts)
     AND a.ticker = ANY(:tickers) AND a.alert_date >= :first AND a.alert_date <= :last
   ORDER BY a.alert_date, a.ticker, a.alert_ts
  ```

Order of refusals in `main()`, each exit 2 with one logged line: a mode flag without its mode, or `--re-resolve` with `--since`, `--backfill` or `--revert-run`, or `--revert-run` with `--from`, `--to` or `--tickers`; `parse_window(..., today=market_today())`; either `exit.call_exit_mode` or `exit.put_exit_mode` not `target_stop`; no `--report-dir` and no `GCS_BUCKET`; then the first query, `schema_missing()`, non-empty.

- [ ] Write, with `gcp.database.query_to_dataframe_strict` and `gcp.database.get_engine` patched to raise `AssertionError` unless a test says otherwise:
  - `test_selection_is_one_strict_query`: `find_resolved_alerts(["SPY", "QQQ"], date(2026, 5, 1), date(2026, 5, 8))` calls the strict reader once; the text, whitespace collapsed, holds `a.run_kind = 'live'`, `a.is_open IS FALSE`, `a.exit_ts IS NOT NULL`, `a.exit_ts = date_trunc('minute', a.exit_ts)`, `a.ticker = ANY(:tickers)`, `a.alert_date >= :first AND a.alert_date <= :last` and `t.run_kind = 'live'`; the parameters are those three; the frame returned is the reader's.
  - `test_default_tickers_are_the_three`: `main()` with `--re-resolve --from 2026-10-01 --to 2026-10-06 --report-dir <tmp>` reaches the selection with `["SPY", "QQQ", "IWM"]`.
  - `test_refused_before_any_query`, parametrised, each returning 2 with no reader call: `--tickers "SPY AMD"`; `--tickers SPY,QQQ` (Review Focus); no `--from`; no `--to`; `--from` after `--to`; `--to` equal to today's Eastern date and after it (with `market_today` patched where the resolver reads it); `--from 2026-5-1x` (Review Focus); `--re-resolve --since 2026-05-01`; `--re-resolve --backfill`; `--re-resolve --revert-run x`; `--commit` alone; `--from 2026-10-01` alone; `call_exit_mode` set to `fixed_horizon` on the loaded configuration, then `put_exit_mode`; no `--report-dir` with `GCS_BUCKET` unset.
  - `test_a_missing_ledger_or_marker_is_exit_two`: with `schema_missing` answering `["bar_recompute_ledger"]`, `main()` with and without `--commit` returns 2, and `get_engine` and the selection are not reached.
  - `test_the_scheduled_path_is_untouched`: `main()` with no flag and with `--since 2026-04-01` calls `EODResolver.run` with the same `since` as today; with the swallowing reader patched to record, `find_open_alerts(since="2026-04-01")` sends, whitespace collapsed, exactly the text of `:139-151` on 58d96807, written out in the test as a literal.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_exits.py -q` (expect FAIL: argparse does not know `--re-resolve` and raises `SystemExit` where the tests want a returned 2, and there is no `find_resolved_alerts`). Record for [0].
- [ ] Implement. `main()` keeps `-> int` and its `sys.exit(main())`.
- [ ] Run again, then `python3 -m pytest tests/gcp/test_signal_monitor_eod_resolver.py tests/meta -q` (expect all pass).
- [ ] The render step. Commit: `feat(data): select resolver-written exits for a bounded re-resolve`

## Task 6: `--re-resolve`: the proof-requiring day read and the dry run

Spec: Design 3 (bars, the rule, a NULL input), Design 2 (the dry run). Advances done_when[1]. Needs: Tasks 4, 5.

**Files:** Modify `gcp/signal_monitor_eod_resolver.py`, `tests/gcp/test_recompute_exits.py`.

**Interfaces:** Produces on `EODResolver`:
- `DAY_BARS_SQL`: `SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`, with `start` and `end` the Eastern day `[D 00:00, D+1 00:00)` from `eastern_bounds_utc`.
- `read_day_bars(self, ticker: str, day: date) -> pd.DataFrame`: one strict read.
- `day_frame(self, raw: pd.DataFrame) -> pd.DataFrame`: columns `Open`, `High`, `Low`, `Close`, `Volume` and the RSI column over the whole day, index naive UTC through `.tz_convert("UTC").tz_convert(None)`, named `Time`. A naive `ts` is not localized; it raises.
- `re_resolve(self, tickers, first, last, *, commit: bool, run_id: str, report_dir: str | None) -> int`.
- `EXIT_CSV_COLUMNS = ("exit_ts", "exit_reason", "exit_price", "exit_return_pct")`.

What the signatures do not determine, a (ticker, date) group at a time, one group's bars in memory:
- No row: every alert of the group is `no_bars`. `require_proven` raising: every alert is `unproven_rows`. Neither has a new value.
- Each alert: a NULL `price_at_signal`, `target_price`, `direction` or `time_stop_minutes` (choice 10) raises `ValueError` naming the ticker and `alert_ts`. Then `self.resolve_one(alert, bars=frame)` and no other exit logic. `None` is `bars_incomplete`. The new `exit_ts` becomes aware UTC through `localize_assuming_utc`.
- The unit: the primary is the alert on `ALERT_EXITS`; the follower is the trade on `TRADE_EXITS` when `trade_found` and the trade is its alert's mirror (choice 6), with the alert's four new values; `trade_found` false gives status `trade_missing`; a trade that is not the mirror gives `trade_diverged` and no follower. `decide` runs over the alert's four and, with a follower, the trade's four, against the alert's marker. A unit that `decide` does not write, and that is not `trade_diverged`, is `already_current`.
- The basis: `bars_basis`, `code_version()`, and `call_exit_mode`, `put_exit_mode`, `rsi_period`, `call_rsi_exit`, `put_rsi_exit`.
- The summary: arguments, run id, code version, that configuration, counts by status per ticker and date, and per ticker and over all the wins (`exit_return_pct > 0`) and the mean return before and after, over the selected rows, a row with no new value counting its stored one both times.
- The group log line of Global Constraints, then `finish_run`. `_post_digest` is not called.

- [ ] Write the fixture in the test, with its expected rows as literals. Bars: one a minute from 04:00 to 19:59 Eastern, close `round(base + 0.02, 2)` on odd minutes and `base` on even, open, high and low equal to the close, volume 1000.
  - SPY 2026-10-06, base 100.0, inserted 2026-10-07: proven by date. 960 rows, sha256 `3d0abb76f18fbe6f4401b4755e9d06a23a2813bf21473f3fde530285e1042f60`.
  - SPY 2026-09-24, base 101.0, inserted 2026-11-14: proven by insert time. 960 rows, sha256 `3cb85aabdeeeef0d9fa28cc67439231f9d2e0f02edf58432bb22dcc7fa24d344`.
  - QQQ 2026-10-06: no rows. QQQ 2026-09-24: the same bars with one row inserted 2026-09-24.

  | Alert | Stored exit | Expected new (run 2026-11-14) | changed, status |
  |---|---|---|---|
  | SPY, 2026-10-06 19:50:00.250000 UTC, CALL, entry 100.0, target 110.0, stop 30 | `time_stop`, 20:20 UTC, 100.0, 0.0 | `eod_close`, 20:00:00 UTC, 100.02, 0.01999999999999602 | true, `recomputed` |
  | SPY, 2026-10-06 14:00:07.500000 UTC, PUT, entry 100.0, target 90.0, stop 30 | `time_stop`, 14:31 UTC, 100.02, -0.01999999999999602 | the same four | false, `recomputed` |
  | SPY, 2026-09-24 15:00:01.000001 UTC, CALL, entry 101.0, target 101.02, stop 30 | `target_hit`, 15:03 UTC, 101.5, 0.495 | `target_hit`, 15:01:00 UTC, 101.02, 0.01980198019801586 | true, `recomputed` |
  | QQQ, 2026-10-06, any | any | none | none, `no_bars` |
  | QQQ, 2026-09-24, two alerts | any | none | none, `unproven_rows`, both |
- [ ] Write:
  - `test_the_dry_run_report_equals_the_expected_table`: `main()` with `--re-resolve --from 2026-09-24 --to 2026-10-06 --tickers "SPY QQQ" --report-dir <tmp>`, the strict reader answering by SQL text, `get_engine` returning an engine whose `begin` raises, `requests.post` raising. Returns 1 (rows were refused). `rows.csv` under `bar-recompute/v1/signal-alert-exits/<run id>/` parses to exactly the table (ticker, session date, `alert_ts` as the row key, four old, four new, changed, status, `bars_rows`, `bars_sha256`, `written` false); `summary.json` holds the counts by status and, for SPY, wins 1 before and 2 after. The log holds `RECOMPUTE-EXITS SPY 2026-10-06 candidates=2 changed=1 unchanged=1 refused=0`. The bar reads are one per (ticker, date), four in all, each text holding `interval = '1min'` and `inserted_at` and bounded by that Eastern day. With QQQ left out of `--tickers` the run returns 0.
  - `test_the_force_frame_equals_the_scheduled_frame`: with `CLOUD_SQL_CONNECTION_NAME` set and one fake at `gcp.database.query_to_dataframe_strict` that answers both the loader's text and `DAY_BARS_SQL` from the SPY 2026-10-06 rows, `pd.testing.assert_frame_equal(resolver._load_day("SPY", date(2026, 10, 6)), resolver.day_frame(resolver.read_day_bars("SPY", date(2026, 10, 6))))`. Planning run of 2026-11-14: equal in index and values, 960 rows by 6 columns; only the index name differed, which `day_frame` sets.
  - `test_each_alert_goes_through_resolve_one`: with `EODResolver.resolve_one` wrapped to record, it is called once per alert of the two proven groups, each time with `bars` given, and `resolver.loader` replaced by `object()` is never used.
  - `test_an_unchanged_exit_is_not_a_change` (Review Focus): the second row above has `changed` false, and the unit's `new["exit_ts"]` is aware.
  - `test_a_null_input_raises_naming_the_alert` (Review Focus), over `price_at_signal`, `target_price`, `direction`, `time_stop_minutes`, the last as `NaN` in a frame whose other rows hold integers: `ValueError` whose text holds the ticker and the `alert_ts`.
  - `test_bars_that_stop_early_are_bars_incomplete`: SPY 2026-10-06 bars cut at 15:40 and an alert with no trigger: status `bars_incomplete`, no new value, exit 1.
  - `test_read_failures_propagate`: `ConnectionError("connection refused")` from the selection, then from a bar read, and `KeyError("close")` from a bar read, each leave `main()` as the same object.
  - `test_an_empty_selection_is_exit_zero`: no candidate gives a report with no row, no bar read, exit 0.
- [ ] Run (expect FAIL: no `re_resolve`). Record for [1].
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_exits.py tests/gcp/test_signal_monitor_eod_resolver.py tests/meta -q` (expect all pass).
- [ ] The render step. Commit: `feat(data): re-resolve closed alerts from proven bars as a dry run`

## Task 7: `--re-resolve --commit` and `--revert-run` for exits

Spec: Design 2 (the committed run, the revert), Design 1, Close-out 8 (the two checks). Advances done_when[3]. Needs: Tasks 3, 6.

**Files:** Modify `gcp/signal_monitor_eod_resolver.py`, `tests/integration/test_bar_recompute_writes.py`, `tests/gcp/test_recompute_exits.py`.

**Interfaces:** Produces `EODResolver.revert_run(self, revert_of: str, *, commit: bool, run_id: str, report_dir: str | None) -> int`: `ledger_of_run(revert_of, TARGET_EXITS)`, `revert_units`, groups by (ticker, session date), `finish_run(action="revert")`. No ledger row: one logged line naming the id and the target, return 1, no transaction (choice 11).

- [ ] Write in the integration file, driving `main()` with `--report-dir <tmp>` and `CLOUD_RUN_EXECUTION` set per run. Seed helpers insert alerts, mirror trades and one-minute bars (inserted now, so proven). "Equal in every column" compares the whole row from `row()`.
  - `test_a_committed_run_overwrites_only_the_exit_fields`: after `--commit`, each selected alert holds the new `exit_ts`, `exit_reason`, `exit_price`, `exit_return_pct` and `exit_recompute_run`; its trade the new `exit_time`, `exit_price`, `exit_reason`, `return_pct` and `exit_recompute_run`; every other column of both, `is_open` included, is equal. Rows with `run_kind` `replay` and `backfill`, an open alert, and a closed alert whose `exit_ts` holds microseconds are equal in every column.
  - `test_a_diverged_trade_is_left_and_its_alert_written`: a trade whose stored exit price differs from its alert's: the trade is equal in every column, the report says `trade_diverged`, the alert is written, exit 1.
  - `test_an_alert_with_no_trade_is_written`: the alert is written, reported `trade_missing`, its ledger row holds `"trades": null`, and the run's exit code is 0.
  - `test_an_alert_changed_underneath_leaves_its_trade` (corrected point 3): `bar_recompute.save_report` wrapped so that its first call first runs `UPDATE signal_alerts SET exit_price = 999.0` on one alert. That alert is as the other writer left it and reported `changed_underneath`; its trade, whose stored exit still equals the alert's old exit, is equal in every column; no ledger row exists for it; exit 1.
  - `test_each_written_alert_has_one_ledger_row`: one row a written alert with the old values, the new values, `changed`, and a basis holding the bars' row count, sha256, first and last `ts`, the insert-time range, `git_commit` and the five configuration values.
  - `test_groups_commit_one_at_a_time`: `write_group` wrapped to raise on its second call: the first group's alerts, trades and ledger rows are committed, the second's are not, and the exception leaves `main()`.
  - `test_a_second_run_writes_nothing`: a second committed run under a new id writes no row, inserts no ledger row, reports every alert `already_current`, exit 0.
  - `test_markers_per_run_and_coverage_are_two_checks` (corrected point 2): run A over a sub-window with `--commit`, then run B over the whole window with `--commit`, one group of B refused as `no_bars`. Per run: `count(*) WHERE exit_recompute_run = '<B>'` on `signal_alerts`, and on `trades`, equal B's report rows with `written` true, and are fewer than the selected rows. Coverage: the selected alerts with a NULL marker are exactly B's report rows with a refused or left status. A's rows keep A's id.
  - `test_the_stored_exit_is_the_deciding_bars_close` (corrected point 4): for each written alert, by reason: for `target_hit`, `time_stop` and `rsi_extreme` the stored price equals the close of the stored bar at the stored exit minute; for `eod_close` no bar is stored at the exit minute, the exit minute is `session_close` of the date, and the price equals the close of the last bar before it. The fixture holds at least one `eod_close`.
  - `test_revert_restores_the_old_values`: `--revert-run <A> --commit` restores the four exit fields of each alert and trade exactly (a price of `0.1 + 0.2` included), sets `exit_recompute_run` to the revert's id, writes one ledger row a restored alert with action `revert`, and leaves a row a later write changed, reported `changed_underneath`. Without `--commit` it writes nothing and reports `would_revert`.
- [ ] Write in `tests/gcp/test_recompute_exits.py`: `test_revert_of_an_unknown_run_is_exit_one` (Review Focus): `ledger_of_run` answering `[]`: returns 1, one ERROR line holding the id and `signal-alert-exits`, `get_engine` not called.
- [ ] Run (expect FAIL). Record for [3], with the note that on `main` the trades update is guarded by `exit_time IS NULL` (`:424`).
- [ ] Implement: `re_resolve` passes `commit` to `finish_run`; `main()` routes `--revert-run`. `persist` is not changed.
- [ ] Run both files and `python3 -m pytest tests/meta -q` (expect all pass).
- [ ] Variant for the record (corrected point 4): in the test's check, read the bar at the exit minute for every reason; expect it to fail on the `eod_close` row with no bar found. Revert.
- [ ] The render step. Commit: `feat(data): commit and revert re-resolved exits through the ledger`

## Task 8: `premarket_snapshot`, called by the nightly

Spec: Design 5 ("One function for the computation"). Advances done_when[4]. Needs: nothing.

**Files:** Modify `gcp/fetchers/fetch_market_data.py` (`:445-545`). Create `tests/gcp/test_recompute_premarket.py`.

**Interfaces:** Produces, in the same file:
- `PREMARKET_COLUMNS`: the eleven names, in the order `pre_high`, `pre_low`, `pre_vwap`, `pre_volume`, `gap_pct`, `pre_range_atr`, `pre_fetched_at`, `pre_excluded_stale_prints`, `pre_excluded_spikes`, `pre_filter_status`, `pre_filter_params`.
- `prior_session_inputs(df: pd.DataFrame, enriched: pd.DataFrame) -> dict` with `close`, `open`, `atr_14`, `atr_5` from the second-to-last row (`Close`, `Open`, `ATR14`, `ATR5`); a NULL or `NaN` is `None`; fewer than two rows gives four `None`. No `try`.
- `premarket_snapshot(ticker: str, session_date, bars: pd.DataFrame, prior: dict, level_params, read_at: datetime) -> dict | None`: the eleven values with `None` where the computation gives none, or `None` when `bars` is empty or holds no bar in the window. `bars` holds `ts` (aware UTC), `open`, `high`, `low`, `close`, `volume`. `level_params` `None` gives status `level_params_unavailable`, as the block does today. No query, no clock, no `try`.

`compute_and_upsert_daily_indicators` keeps its signature, its two reads on `query_to_dataframe`, its `try` and its warning, and its write rule: the six price columns are set only when not `None` (`:518-524`), the five provenance columns always. Its two log lines stay, the first counting `len(intraday)`. The two reads get the `AUDIT-2026-05-13` comment.

- [ ] Write:
  - `test_the_snapshot_is_the_one_place`: 330 bars from 04:00 to 09:29 Eastern on 2026-10-06 (`open` 100.0, `high` 100.5, `low` 99.5, `close` 100.0, `volume` 1000), `prior = {"close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}`, the SPY parameters of `tests.lib.level_params_fixtures.legacy_db(("SPY", "QQQ"))` loaded for that date, `read_at` a fixed instant. Expected (run 2026-11-14 through the library functions the block calls): `pre_high` 100.5, `pre_low` 99.5, `pre_vwap` 100.0, `pre_volume` 330000, `gap_pct` 1.0101, `pre_range_atr` 0.5, `pre_fetched_at` the instant, both counts 0, status `ok`, and `pre_filter_params` equal to `premarket_filter_inputs(params, {"atr_14": 2.0, "atr_5": 2.0})["params"]`. With parameters from `legacy_db(..., effective_from=date(2026, 10, 1))` loaded for 2026-09-24: status `params_unavailable`, `pre_range_atr` `None`, both counts `None`, the first five values as above. With an empty frame: `None`. With `calculate_premarket_context` patched to raise `KeyError("close")`: it propagates.
  - `test_prior_session_inputs`: 40 business days ending 2026-10-06 with `Open` 99.0, `High` 100.0, `Low` 98.0, `Close` 99.0 give `{"close": 99.0, "open": 99.0, "atr_14": 2.0, "atr_5": 2.0}` after `add_all_indicators`; a NULL close on the prior row gives `close` `None`; one row gives four `None`; a frame with no `Close` column raises `KeyError`.
  - `test_the_nightly_calls_the_snapshot`: with `fmd.premarket_snapshot` wrapped to record, `compute_and_upsert_daily_indicators("SPY", "2026-10-06", level_params=params)` over patched `query_to_dataframe` and `upsert_dataframe` calls it once, and the upserted row holds its values.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_premarket.py -q` (expect FAIL: no `premarket_snapshot`). Record for [4].
- [ ] Implement the extraction.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_premarket.py tests/gcp/test_premarket_filter_params.py tests/gcp/test_premarket_filter_callers.py tests/gcp/test_atr5_column.py -q` (expect the new tests and the 40 existing cases to pass, the three files unmodified), then `python3 -m pytest tests/meta -q`.
- [ ] The render step. Commit: `refactor(data): compute the premarket snapshot in one function`

## Task 9: `--recompute-premarket`: flags, selection, the three reads, the dry run

Spec: Design 5; decisions 8 and 9. Advances done_when[4]. Needs: Tasks 2, 3, 8.

**Files:** Modify `gcp/fetchers/fetch_market_data.py` (`build_parser`, `:1141-1188`; `main`, `:1191-1196`; the last line), `tests/gcp/test_recompute_premarket.py`.

**Interfaces:** Produces:
- Flags in `build_parser`: `--recompute-premarket`, `--from` (`dest="first"`), `--to` (`dest="last"`), `--commit`, `--revert-run RUN_ID`, `--report-dir PATH`.
- `main()` branches on the two modes before anything else it does and returns the mode's exit code; the last line of the file becomes `sys.exit(main())` (`main()` returns `None` in every existing mode).
- `recompute_premarket(tickers: list[str], first: date, last: date, *, commit: bool, run_id: str, report_dir: str | None) -> int`.
- Three texts:

  ```sql
  -- PREMARKET_ROWS_SQL: one strict query
  SELECT ticker, date, close, pre_high, pre_low, pre_vwap, pre_volume, gap_pct, pre_range_atr,
         pre_fetched_at, pre_excluded_stale_prints, pre_excluded_spikes, pre_filter_status,
         pre_filter_params::text AS pre_filter_params, pre_recompute_run
    FROM market_data_daily
   WHERE ticker = ANY(:tickers) AND date >= :first AND date <= :last AND close IS NOT NULL
     AND (pre_high IS NOT NULL OR pre_low IS NOT NULL OR pre_vwap IS NOT NULL OR gap_pct IS NOT NULL)
   ORDER BY ticker, date
  -- DAILY_BARS_SQL: one strict query a ticker, :lo is 400 calendar days before the window's first date
  SELECT date, open AS "Open", high AS "High", low AS "Low", close AS "Close", volume AS "Volume"
    FROM market_data_daily WHERE ticker = :ticker AND date >= :lo AND date <= :hi ORDER BY date
  -- the bars: one strict query a (ticker, month), one window a selected session (choice 12)
  SELECT b.ts, b.open, b.high, b.low, b.close, b.volume, b.inserted_at
    FROM (VALUES (:s0, :e0), (:s1, :e1), ...) AS w(start_ts, end_ts)
    JOIN market_data_intraday b
      ON b.ticker = :t AND b.interval = '1min'
     AND b.ts >= w.start_ts::timestamptz AND b.ts < w.end_ts::timestamptz
   ORDER BY b.ts
  ```

What the signatures do not determine:
- `pre_filter_params` is read as the database's own text and bound back as that text. Run 2026-11-14: a stored number with more digits than a float holds does not match `json.dumps` of the parsed value.
- A (ticker, month) at a time. `read_at = utc_now()` once, after the month's bars return (`utc_now` imported by name from `lib.eastern_time`, so a test can move the clock). Each session: its window from `eastern_bounds_utc(d, time(4), time(9, 30))`; no row is `no_bars`; `require_proven` raising is `unproven_rows`; the daily frame is the last 250 rows up to the date, with `add_all_indicators` run on it as the nightly runs it (choice 7 for `daily_incomplete`); `prior_session_inputs`; the parameters from `read_level_params_for_run(tickers, d)`, read once a distinct session date for the run's tickers and kept for the run; `premarket_snapshot`; `None` is `no_bars`.
- A failed parameter read is not caught: `LevelParamsUnavailable` leaves `main()`, with the reader's error as its `__cause__`. The mode never writes `level_params_unavailable`.
- The unit: `DAILY_PREMARKET`, no follower; `decide` over `PREMARKET_COMPARED` against `pre_recompute_run`. The basis: `bars_basis`, `code_version()`, the filter status and parameters, and the prior close, open and ATRs.
- The report's columns are `PREMARKET_COLUMNS`; the group log line is `RECOMPUTE-PREMARKET <ticker> <YYYY-MM> candidates=.. changed=.. unchanged=.. refused=..`; then `finish_run`.
- The mode reads no `ALPHA_VANTAGE_API_KEY` and makes no HTTP request.

- [ ] Write, with the reads answered by SQL text, level parameters through `install_level_params(monkeypatch, ("SPY", "QQQ"), db=legacy_db(("SPY", "QQQ"), effective_from=date(2026, 10, 1)))`, installed after the fake reader, which it wraps, `requests.get` raising and `get_engine` returning an engine whose `begin` raises. Fixture: the bars and daily rows of Task 8 for SPY on 2026-10-06 (parameters `ok`) and on 2026-09-24 (bars inserted 2026-11-14, parameters effective from 2026-10-01); QQQ 2026-10-06 with no bars; QQQ 2026-09-24 with one row inserted 2026-09-24. Each selected row's stored values are literals in the test.
  - `test_the_dry_run_report_equals_the_expected_table`: `main()` with `--recompute-premarket --from 2026-09-24 --to 2026-10-06 --tickers "SPY QQQ" --report-dir <tmp>` returns 1. `rows.csv` under `bar-recompute/v1/daily-premarket/<run id>/` equals a table written out in the test: for SPY 2026-10-06 and 2026-09-24 the old and the new value of each of the eleven columns (Task 8's numbers; the 2026-09-24 row goes from a NULL status to `params_unavailable`, with NULL counts and a NULL `pre_range_atr`), `changed` true, status `recomputed`; QQQ 2026-10-06 `no_bars` and QQQ 2026-09-24 `unproven_rows`, neither with a new value. `summary.json` holds the counts, and the log holds `RECOMPUTE-PREMARKET SPY 2026-10 candidates=1 changed=1 unchanged=0 refused=0`.
  - `test_reads_are_one_a_ticker_and_one_a_month`: the selection once, with `tickers`, `first`, `last`, its text holding `ticker = ANY(:tickers)`, `close IS NOT NULL` and the four `IS NOT NULL` alternatives; the daily read once a ticker; the bar read once a (ticker, month), its text holding `interval = '1min'`, `inserted_at` and one window a selected session; the parameters once a distinct session date.
  - `test_the_mode_touches_no_vendor`: `fmd.os.environ` replaced by a recording mapping never sees `ALPHA_VANTAGE_API_KEY`; `process_ticker`, `fetch_and_upsert_vix` and `_run_backfill` raise if called and are not.
  - `test_refused_before_any_query`, parametrised, each 2 with no read: `--tickers "SPY AMD"`; `--tickers SPY,QQQ`; a missing bound; `--to` on or after `market_today()`; `--from 2026-5-1x`; `--recompute-premarket --date 2026-10-06`; `--recompute-premarket --backfill`; `--commit` alone; no `--report-dir` with `GCS_BUCKET` unset. And `--tickers ALL` covers the three.
  - `test_a_session_with_no_prior_daily_row_is_daily_incomplete`: the daily read answering one row for SPY: status `daily_incomplete`, no new value, exit 1.
  - `test_a_missing_ledger_or_marker_is_exit_two`: as Task 5's, with and without `--commit`.
  - `test_read_failures_propagate`: `ConnectionError` and `KeyError("close")` from the selection, a daily read and a bar read each leave `main()` as the same object; a parameter read that fails leaves it as `LevelParamsUnavailable` whose `__cause__` is the object.
- [ ] Run (expect FAIL: argparse rejects the flag). Record for [4].
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_premarket.py tests/gcp/test_premarket_filter_params.py tests/gcp/test_premarket_filter_callers.py tests/gcp/test_atr5_column.py tests/meta -q` (expect all pass).
- [ ] The render step. Commit: `feat(data): recompute premarket fields from stored bars as a dry run`

## Task 10: `--recompute-premarket --commit` and `--revert-run` for premarket

Spec: Design 2 (the committed run, steps 1 to 6), Design 5 (`pre_fetched_at`, write). Advances done_when[5]. Needs: Tasks 3, 9.

**Files:** Modify `gcp/fetchers/fetch_market_data.py`, `tests/integration/test_bar_recompute_writes.py`, `tests/gcp/test_recompute_premarket.py`.

**Interfaces:** Produces `revert_premarket_run(revert_of: str, *, commit: bool, run_id: str, report_dir: str | None) -> int`, as Task 7's on `TARGET_PREMARKET`, groups by (ticker, month).

- [ ] Write in the integration file, driving `fmd.main()`. Seeds: daily rows for SPY and QQQ over two months with premarket values, 40 business days of daily history before them, premarket bars for each session, and `ticker_level_params` rows that make the later month `ok`. The schema's own policy seed is in force (run 2026-11-14 on a database with the schema applied: a ticker with no parameter row loads as `params_unavailable`).
  - `test_a_committed_run_overwrites_the_twelve_columns`: each selected row holds the eleven new values and `pre_recompute_run`; a new value of `None` is stored as NULL over a stored number; every other column but `updated_at` is equal. A row of AMD, a row with no premarket value and a row dated `market_today()` are equal in every column.
  - `test_a_row_changed_underneath_is_left`: `save_report` wrapped as in Task 7 with `UPDATE market_data_daily SET pre_high = 1.0` on one row: `changed_underneath`, left, no ledger row, exit 1.
  - `test_each_written_row_has_one_ledger_row`: old values, new values, `changed`, basis.
  - `test_a_retry_under_the_same_run_id_reports_from_the_ledger` (corrected point 5): `write_group` wrapped to raise on its second call; the run raises. Run again with the same `CLOUD_RUN_EXECUTION` and no wrapper. One ledger row a written row and no more. In the second run's `rows.csv` the first group's rows carry the ledger's old values (the values stored before the first attempt) and new values, `written` true, and a status that is not `already_current`.
  - `test_a_second_run_at_a_later_instant_writes_nothing` (corrected point 1): after a committed run, record `pre_fetched_at`, `pre_recompute_run` and `updated_at` of every row; run again under a new id with `fmd.utc_now` patched an hour later. No ledger row is added; the three recorded values are equal on every row; every row is `already_current`; exit 0.
  - `test_markers_per_run_and_coverage_are_two_checks` (corrected point 2): as Task 7's, on `pre_recompute_run`.
  - `test_revert_restores_the_eleven_columns`: `--revert-run <id> --commit` restores each of the eleven exactly, `pre_fetched_at` and a NULL included, and sets the marker to the revert's id.
- [ ] Write in `tests/gcp/test_recompute_premarket.py`: `test_revert_of_an_unknown_run_is_exit_one` (Review Focus), with an exits run id whose ledger rows have target `signal-alert-exits`: returns 1, no transaction.
- [ ] Run (expect FAIL). Record for [5], with the note that on `main` no code writes a NULL over a stored premarket value (`:518-524`).
- [ ] Implement.
- [ ] Run both files and `python3 -m pytest tests/meta -q` (expect all pass).
- [ ] Variants for the record: let `finish_run` skip the ledger read and expect the retry test to fail on a first-group row reading `already_current`; add `pre_fetched_at` to `PREMARKET_COMPARED` and expect the later-instant test to fail on an added ledger row. Revert both.
- [ ] The render step. Commit: `feat(data): commit and revert recomputed premarket fields`

## Task 11: The replace's RECOMPUTE lines

Spec: Design 6. Advances done_when[6]. Needs: Tasks 5, 9 (the flags exist).

**Files:** Modify `gcp/fetchers/fetch_alphavantage_intraday.py` (`:483-490`, `:500-503`, `:755-757`), `tests/gcp/test_intraday_replace_months.py` (`:876`, `:877`, `:879`), `tests/gcp/test_recompute_exits.py`.

- [ ] Change the three assertions (choice 2) and no other line of the file: `:876` asserts `"python -m gcp.signal_monitor_eod_resolver --re-resolve" in adv["signal_alerts exits"]` with `"--from"` and `"--to"`; `:877` asserts neither `"NO PATH YET"` nor `"#1190"` is in that entry; `:879` asserts `"python -m gcp.fetchers.fetch_market_data --recompute-premarket" in premarket`, with `"--from"`, `"--to"`, and neither `"NO PATH YET"`, `"#1190"` nor `"backfill_daily_indicators"`.
- [ ] Write in `tests/gcp/test_recompute_exits.py`: `test_a_committed_replace_names_both_commands`, set up as `tests/gcp/test_intraday_replace_months.py:854-866` is (a one-line list, `replace_month` patched to an ok result, `commit=True`): `caplog.text` holds a `RECOMPUTE signal_alerts exits:` line with `--re-resolve` and a `RECOMPUTE market_data_daily` line with `--recompute-premarket`, and holds neither `NO PATH YET` nor `until #1190 lands`.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_replace_months.py tests/gcp/test_recompute_exits.py -q -k "recompute_advice or committed_replace"` (expect FAIL on `:876`). Record for [6].
- [ ] Implement: the two entries become `python -m gcp.signal_monitor_eod_resolver --re-resolve --from <first session> --to <last session>` and `python -m gcp.fetchers.fetch_market_data --recompute-premarket --from <first session> --to <last session>`, each followed by `, dry run first, then with --commit`. The warning at `:755-757` goes. The comment at `:483-490` says every table has a path and where each is. The `historical_signals` entry is not changed.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_replace_months.py tests/meta/test_production_writers.py -q` (expect 351 and 90 passed), and `git diff origin/main --stat -- tests/gcp/test_intraday_replace_months.py` (expect 3 insertions, 3 deletions).
- [ ] The render step. Commit: `fix(data): name the two recompute commands in the replace's advice`

## Task 12: The statement budgets, measured on the integration Postgres

Spec: Design 11 (Capacity); done_when[8], the local half. Advances done_when[8]. Needs: Tasks 7, 10.

**Files:** Modify `tests/integration/test_bar_recompute_writes.py`.

- [ ] Write two tests that count statements with a `before_cursor_execute` listener on `db_engine`, attached after the seed and removed after `main()` returns, and print the count and the seconds:
  - `test_exits_statement_budget`: 900 synthetic alerts with mirror trades on 27 (ticker, date) groups (9 NYSE sessions, 3 tickers), each group's session bars inserted with one `generate_series` statement. A committed `--re-resolve` runs under 120 statements (planned: 111), none with `executemany` true.
  - `test_premarket_statement_budget`: 450 synthetic daily rows on 24 (ticker, month) groups (150 sessions over 8 months, 3 tickers), their premarket bars and 300 days of daily history inserted the same way. A committed `--recompute-premarket` runs under 240 statements (planned: 228), none with `executemany` true.
- [ ] Run against the local Postgres with `-s` and keep the four numbers for the PR body. A count over the limit is a defect in the code, not in the limit.
- [ ] Commit: `test(data): hold both recompute tools to their statement budgets`

## Task 13: Whole suite, the files left alone, the production measurements, the draft PR

Spec: Done when [7], [8]; Close-out ("Before the merge"). Advances done_when[7], [8]. Needs: Tasks 1 to 12.

- [ ] Run: `make test` (expect no failure that `origin/main` does not have) and `python scripts/export_openapi.py --check` (expect it to pass).
- [ ] Run the render step once more and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass). If `git status` shows a change to the three docs, commit: `docs(infra): re-render the inventory for the recompute paths`.
- [ ] Run: `git diff --stat origin/main -- gcp/deploy.sh gcp/signal_monitor.py gcp/backfill_ticker.py gcp/fetchers/fetch_premarket_refresh.py lib/eastern_time.py lib/data_loader.py platform/api CLAUDE.md tests/meta/test_production_writers.py tests/meta/test_timezone_boundaries.py tests/fixtures/timezone_boundary_baseline.json tests/gcp/test_intraday_writers_utc.py tests/gcp/test_premarket_playbook_resolver.py tests/gcp/test_premarket_filter_params.py tests/gcp/test_premarket_filter_callers.py tests/gcp/test_atr5_column.py tests/integration/conftest.py` (expect empty).
- [ ] Production, read only, each through `env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "..."`, never `--commit`, with the execution id kept beside each result:
  - `EXPLAIN (ANALYZE, BUFFERS)` of `DAY_BARS_SQL` with literals for QQQ and the Eastern day 2026-05-01.
  - `EXPLAIN (ANALYZE, BUFFERS)` of the premarket bars statement with literals for SPY and one window for each session of 2026-10. The index scan must show rows read equal to rows returned, a loop a window. If it does not, stop and report (choice 12).
  - `EXPLAIN (ANALYZE, BUFFERS)` of `RESOLVED_ALERTS_SQL` with literals for the three tickers from 2026-05-01 to yesterday, the two marker columns written as `NULL::text` (choice 13; say so on the PR).
  - The candidates per ticker of both tools on that day: `count(*)` by ticker of the alert selection's `WHERE`, and of the premarket selection's `WHERE` from 2026-04-14. On 2026-11-14 the spec read 835 and 447.
  - The candidate alerts with a NULL `price_at_signal`, `target_price` or `direction`, and, for choice 10, with a NULL `time_stop_minutes`. A count above zero is reported to the owner before the PR is marked ready: the tool raises on such a row.
- [ ] Push with `git push -u origin feature/feat-data-001-recompute-after-bar-rewrite` and open a **draft** PR. Title: `FEAT-DATA-001: recompute paths for signal_alerts exits and the daily premarket fields`. Body, on the repository's template:
  - the spec path and this plan's path;
  - the ten done_when items, each as a `- [ ]` line that starts with the item's text;
  - Capacity from the spec's Design 11 table, with Task 12's four numbers and the three plans above: Volume (835 alerts on 27 day reads of at most about 1,200 rows; 447 daily rows on 24 month reads of at most about 7,600 bars; one group in memory at a time; 835 and 447 ledger rows of about 1 KB), Velocity (exits: 30 round trips dry, about 165 committed; premarket: about 180 dry, about 280 committed; one statement a table a group), Wall-clock (exits 85 to 330 s committed against 3,600 s; premarket 140 to 560 s committed against 5,400 s; at Rule 0's 0.5 to 2 s a round trip, not measured on production), Cost (under one cent a committed run; no job, no schedule; the ledger and the reports under 2 MB);
  - the section "What changes in production, and when";
  - the red-then-green records of Tasks 1 to 11 and the choices of Global Constraints, the first three marked for the owner;
  - that no route, response or page changes, so there is no deployed-site run (spec, Design 10), and `Canvas refresh pending: none`.
- [ ] Set `pr:` in this plan to the PR's number.

## Task 14: Product record, site notes and the gate

Spec: Design 10; Done when [9]; product-delivery Phase 5. Closes done_when[9]. Needs: Tasks 1 to 13. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/`, `tests/` or `platform/api` may change without redoing all four of them.

- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record only (`:513`): in the Status cell (`:520`) append, before the closing ` |`: `; signal_alerts exits and the market_data_daily premarket fields have recompute paths, a bounded re-resolve mode of the end-of-day resolver and a bars-only mode of the daily fetcher, each with a dry run, a ledger row per overwrite and a revert, and the resolver's walk ends at the session close ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed; no stored row is rewritten by the PR)`. Last reviewed (`:524`) becomes the date of the PR's head commit; set it again if a later commit lands on another day.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-DATA-001` (`:320`): append to its `**PR lineage:**` line (`:346`) ` · [#N](https://github.com/TeneikaAskew/stocks/pull/N) *remediation: recompute paths for bar-derived results (#1190), spec [#1931](https://github.com/TeneikaAskew/stocks/pull/1931)*`. No earlier entry is removed. Commit both docs and the plan: `docs(product): record the recompute paths under FEAT-DATA-001`.
- [ ] Site notes, step 1 (preflight). With every code and test commit in place and a clean tree, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`. It prints a verdict and installs nothing yet. Copy its `source_identity_sha256`.
- [ ] Site notes, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes` (`:1297`), write nine `(FEAT-DATA-001, component)` rows and change no other byte. Order among the FEAT-DATA-001 rows: ADMIN-02, **ADMIN-06**, **CHARTS-01**, **DASHBOARD-01**, DASHBOARD-04, **INSIGHTS-01**, **JOURNAL-01**, **JOURNAL-02**, LIVE-03, **LIVE-04**, LIVE-08, **PLAYBOOK-05**, SHARED-07, **SIGNALS-02**. Six are new rows: `| FEAT-DATA-001 | <component> | source_identity_sha256=<that hash>; <text> |`. Three exist on 58d96807 (CHARTS-01 `:1304`, DASHBOARD-01 `:1305`, JOURNAL-01 `:1307`) and are extended: the new hash, this change's text, then ` Earlier: ` and the row's earlier prose unchanged, its old hash dropped. A row another lane added since is extended the same way; tell the owner. The texts, with their backticks:

  ```text
  fetcher rows (ADMIN-06, CHARTS-01, DASHBOARD-01, INSIGHTS-01, JOURNAL-01, LIVE-04, PLAYBOOK-05)
    The `fetch-market-data` job named in this component's Data cell computes the premarket columns of `market_data_daily` in one function, `premarket_snapshot` in `gcp/fetchers/fetch_market_data.py`; the nightly's row is unchanged. A bars-only mode, `--recompute-premarket`, can rewrite a past session's premarket columns for SPY, QQQ and IWM from stored 1-minute bars that are proven true UTC, with a dry run, a `bar_recompute_ledger` row per overwrite and `--revert-run`. No route or response of this component changed and the PR rewrote no stored row. Tests: `tests/gcp/test_recompute_premarket.py`, `tests/gcp/test_bar_recompute.py`, `tests/integration/test_bar_recompute_writes.py`. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.

  resolver rows (JOURNAL-02, SIGNALS-02)
    The `signal-monitor-eod-resolver` job named in this component's Data cell ends its walk at the session close: `eod_close` is stamped with the close, priced from the last bar before it, and written only when the stored bars reach the last five minutes. A force mode, `--re-resolve`, can rewrite a resolver-written exit of `signal_alerts` and its `trades` row for SPY, QQQ and IWM from proven bars, with a dry run, a `bar_recompute_ledger` row per overwrite and `--revert-run`. No route or response of this component changed and the PR rewrote no stored row. Tests: `tests/gcp/test_signal_monitor_eod_resolver.py`, `tests/gcp/test_recompute_exits.py`, `tests/integration/test_bar_recompute_writes.py`. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.
  ```

  Commit: `docs(site): note the recompute paths under nine components`.
- [ ] Site notes, step 3. Run the same `produce` command again; it now writes the sidecar. Commit: `docs(site): regenerate the source snapshot`. These two commits are the last before the push.
- [ ] Site notes, step 4. Run `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched file later: merge `origin/main`, run the render step and `tests/scripts/test_check_generated_docs.py`, then repeat steps 1 to 4 with the new hash in all nine rows.
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > /tmp/audit-branch.txt`; then `git worktree add --detach /tmp/audit-main origin/main`, run the same command there into `/tmp/audit-main.txt`, and `git worktree remove /tmp/audit-main`. Compare the `[P1]`, `[P2]` and `[P3]` lines: the branch reports none that `main` does not. A new finding is fixed or reported, not waived. Exit code 2 means the run itself failed.
- [ ] Run on the final head: `make test`, `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` and `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0). Push.
- [ ] Tick each done_when box in the PR body with its evidence beside it (test name, command output, execution id), [6] with the note of choice 2, then mark the PR ready for review. Review cap: two rounds.

## Close-out (not tasks; owner's steps)

Copied from the spec's Close-out, in its order. None of it is done by the implementer of this plan, none of it is a done_when box, and each step, read-only ones included, waits for the owner's own yes. The record is kept as comments on the implementation PR and on #1190.

1. **Apply the schema**: `./gcp/deploy.sh apply-schema`. Check: `information_schema` shows `bar_recompute_ledger` and the three marker columns; the ledger is empty and no marker is set.
2. **Deploy the two jobs**: `./gcp/deploy.sh eod-resolver` and `./gcp/deploy.sh market-data`, from `main` at or after the merge. Check: each job's image is the build's digest; the next scheduled run of each exits 0; the next nightly row for SPY has the eleven premarket columns set as on the night before.
3. **Rehearsal, dry**, over the sessions proven today: `gcloud run jobs execute signal-monitor-eod-resolver --region us-east1 --args="--re-resolve,--from=2026-09-28,--to=<yesterday>" --wait` and `gcloud run jobs execute fetch-market-data --region us-east1 --args="--recompute-premarket,--from=2026-09-28,--to=<yesterday>" --wait`. Check: both exit 0; both reports are in the bucket; the exits report holds the candidates a read-only count gives (10 on 2026-11-14) and none is `unproven_rows`; the premarket report holds one row a ticker and session (105 on 2026-11-14, plus later sessions); the ledger is empty. The owner reads both reports. The six `eod_close` rows of 2026-09-30 and 2026-10-01 are expected to change.
4. **Rehearsal, committed**: the same two commands with `,--commit`. Check: the ledger holds one row a report row marked written; the rows whose marker equals the run's id are exactly those rows, counted a table with `WHERE exit_recompute_run = '<run id>'` (and `pre_recompute_run` for the daily table); each rewritten exit equals its ledger `new_values`; a second dry run reports every row `already_current`. Then `--revert-run` of the exits run as a dry run only.
5. **The gate.** With steps 1 to 4 recorded, both tables have a path that has run on production; the record on #1190 names the two execution ids of step 4. `./gcp/deploy.sh fetchers` then puts the new RECOMPUTE lines into the replace job. If the runbook's step 1 already ran, this is a second deploy of the fetchers.
6. **CLAUDE.md 3.9** still says not to run `--replace-months --commit` until #1190 lands. Bringing it up to date is a FEAT-CICD-001 change on its own branch.
7. **The runbook's steps 5 and 6** (bucket-copy spec): the replace, then the scan that shows `unproven_rows=0` for every month.
8. **In the runbook's step 7, the full recompute**, after its `ticker_level_params` item. Dry run of both tools over everything (exits from 2026-05-01, premarket from 2026-04-14, to yesterday); the owner reads the reports and says yes to each tool separately; then the committed run of each, with two checks kept apart:
   - Per run: the ledger's rows for the run equal the report's written rows, and the count of rows whose marker equals the run's id, a table, equals the written rows of that table in the report.
   - Coverage: every selected row has a marker that is not NULL or is in the report with a refused or left status; the count of selected rows with a NULL marker equals the count of those report rows.
   - Then, for three alerts from the report, one an `eod_close` if it holds any: the stored price equals the close of the bar that decided it. For `target_hit`, `time_stop` and `rsi_extreme` that is the stored bar at the exit minute; for `eod_close` it is the last stored bar before the session close. A second dry run reports everything `already_current`.
   - A row that is `no_bars` or `bars_incomplete` is recorded by name and stays as it is; the owner decides about it. The run then exits 1, which is expected for that case.
   - The record lists the consumers of the spec's Design 9 with the before and after from the summary, and answers the replace's two RECOMPUTE lines with the two execution ids.
9. **Undo**, if the owner asks: `--revert-run <run id> --commit` on the same job. Check: the ledger holds the revert's rows and the rows hold their old values.

**After the runbook**: the nine site notes and this plan's status are brought to the deployed state on a `docs/` branch (the plan's `status: done` may follow the merge itself, product-delivery Phase 5 step 7). Not in the spec's list: the hand-written data documents (`docs/product/06-DATA-ARCHITECTURE.md` and the ERD and dictionary under `docs/product/infrastructure/`) do not know the ledger table; that is the same `docs/` branch.
