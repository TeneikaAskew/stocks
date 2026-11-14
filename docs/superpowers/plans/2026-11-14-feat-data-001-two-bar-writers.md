---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-13-feat-data-001-two-bar-writers.md
branch: fix/feat-data-001-two-bar-writers
pr: null
status: ready
---

# Two writer modules for the 1-minute bar table: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [11].

**Goal:** Only `gcp/fetchers/fetch_alphavantage_intraday.py` and `gcp/fetchers/fetch_market_data.py` write 1-minute bars to `market_data_intraday`: the `backfill-ticker` job stops fetching and writing them and reads its premarket bars strictly, `gcp/migrate_to_gcp.py` loses its intraday loader, and guard tests pin the two modules and what may start them.

**Architecture:** Two removals and one strictness change in production code, then a guard. `gcp/backfill_ticker.py` loses `av_intraday_month` and step 2 of `run`, and its premarket bar read moves out of its `try` onto `gcp.database.query_to_dataframe_strict`, so an outage ends the run and an empty premarket is a logged fact. `gcp/migrate_to_gcp.py` loses `migrate_market_data_intraday` and its selector, so argparse refuses it. `tests/meta/test_production_writers.py` gains an `ast` scan for writes of the table and five checks built on it (two writer modules, their entry points, the one variable-table deleter, no dispatcher of the job).

**Tech Stack:** Python, pandas, `requests`, SQLAlchemy with pg8000 through `gcp.database`, argparse, pytest (`monkeypatch`, `caplog`, `subprocess`), `ast`, `re`.

**Spec:** docs/superpowers/specs/2026-11-13-feat-data-001-two-bar-writers.md

## Global Constraints

- Base: `origin/main` at 20d9c47b or later. Branch `fix/feat-data-001-two-bar-writers`. Commit this plan file first, alone: `docs(plan): FEAT-DATA-001 implementation plan for the two bar writers`. The site-note producer of Task 9 refuses a branch with no committed plan.
- The spec's line numbers are for c698b24e. This plan cites 20d9c47b, read on 2026-11-14. What moved: every cited line of `gcp/backfill_ticker.py` below its module docstring sits 3 lines further down (the job's write is `:659`, not `:652`), and its watchlist default (`:618`) is already `"false"` (#1910); the fetchers' writes are `fetch_alphavantage_intraday.py:327` and `:644` and `fetch_market_data.py:574`; `tests/meta/test_production_writers.py` holds 79 cases, not 15, and already holds the replay guard; `tests/gcp/test_backfill_ticker.py` holds 23 cases, not 18. `gcp/migrate_to_gcp.py`, `gcp/deploy.sh`, `gcp/database.py`, `scripts/archive_yahoo_data.py`, `scripts/backfill_watchlist_data.py`, `platform/api/routers/admin.py`, `tests/gcp/test_intraday_as_traded.py` and `tests/gcp/test_intraday_writers_utc.py` are unchanged since c698b24e (`git diff --stat c698b24e 20d9c47b`), so the spec's lines hold for them.
- Order: the spec's precondition holds. FEAT-REPLAY-001's implementation is on `main` (#1891, d08b0fa4); on 20d9c47b the only string constant outside a docstring that holds `backfill-ticker` under `gcp/`, `lib/`, `scripts/` or `platform/` is the job's own logger name, `gcp/backfill_ticker.py:72` (planning scan, 2026-11-14).
- Not in the PR's diff: `CLAUDE.md`, `gcp/deploy.sh`, anything under `.github/`, `gcp/fetchers/`, `lib/`, `platform/` (so `platform/api/openapi.json`), `scripts/`, `gcp/database.py`, `gcp/schema.sql`, `tests/fixtures/timezone_boundary_baseline.json`, and these tests: `tests/gcp/test_migrate_trades_tz_guard.py`, `tests/gcp/test_deploy_reachability.py`, `tests/gcp/test_discord_interactions.py`, `tests/scripts/test_backfill_and_replay.py`, `tests/meta/test_timezone_boundaries.py`. What the spec needs in `gcp/deploy.sh` is an owner step (Close-out 5), not a task.
- No stored bar is written, deleted or moved. No new AlphaVantage request, job, schedule, table or query text. The watchlist step of `run` (`gcp/backfill_ticker.py:694-700`) and its default (`:618`) are not changed. No trading cost anywhere.
- Exact strings, copied from the spec. `{T}` is the upper-case ticker, `{date}` is `YYYY-MM-DD`.
  - L1, INFO, once per `run`: `1-min bars are not fetched by this job; premarket context reads market_data_intraday`
  - L2, WARNING, once per date with zero premarket rows: `no 1-min bars in market_data_intraday for {T} premarket {date}; pre_* not written`
  - The premarket SQL keeps its text byte for byte (`gcp/backfill_ticker.py:502-506`) and its three parameters; no `timeout_s`.
- Rule 3.7: the new read has no `try` around it and no fallback value. Nothing this plan adds returns an empty container on failure. The two daily reads that stay on the swallowing helper (`:374`, `:442`) get the `AUDIT-2026-05-13` comment and no other edit.
- Rule 3.9: no new time conversion. `eastern_bounds_utc` is called exactly as today.
- **Red then green, on the PR.** Every new test has a record: a test that is red before its change records that run (command, failing line); a test that passes on the unmodified tree or as soon as its function exists (the scan's snippet test, the two-writer tests, the entry-point test, the Yahoo test, the dispatch test, the compute-defect pin, the print-filter test) records the variant or the run on `main`'s code that its task names, applied in a scratch edit, seen to fail, and reverted. A variant is never committed.
- **The render step.** A task that changes a file under `gcp/` ends with it, because the generated inventory cites line numbers into both files (`docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md` cites 10 lines of `gcp/backfill_ticker.py` and 12 of `gcp/migrate_to_gcp.py`):
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed; the render takes about a minute), then stage whichever of the three docs changed in the same commit as the code. The blocks between `<!-- inventory:*:start/end -->` markers are never edited or merged by hand: after any merge of `main`, run the render again and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q`, and commit what the render wrote.
- **The site snapshot is last.** It stops verifying whenever `main` moves or a watched file changes. The site notes and the snapshot are the last two commits before the final push, and all four site-note steps of Task 9 are redone after any merge of `main`.
- **Draft until closed.** The PR is opened as a draft and stays a draft until the close commits of Task 9 are pushed and every done_when line in the body is ticked with its evidence. Marking it ready starts the first of two review rounds; there is no third.
- **Whole suite in its normal order.** Two tests on `main` depend on order and are not this plan's: `tests/api/test_movement_statement_router.py::test_endpoint_nan_close_does_not_500_and_carries_no_nan` (fails when `tests/api` runs alone) and the fresh-clone tests that follow `test_docs_audit.py`. Judge the suite by `make test`, not by a folder run.
- Commits: run `python3 scripts/gate/spec_gate.py --commit` first. Conventional message, imperative, 72 characters or fewer. No AI attribution of any kind: no co-author line, no "generated by", no emoji. Never rebase or force-push after the first push; bring the branch up to date by merging `origin/main`.
- Tests go in the files named, one folder per area, never at the `tests/` root.
- A claim in a doc or on the PR about what the code does comes from output that was run (CLAUDE.md 3.11.1).
- Other lanes (read at 20d9c47b; if one has merged, merge `origin/main` before the task named and rerun that task's expected-values step):
  - FEAT-DATA-001 bucket copy (`specs/2026-11-13-feat-data-001-intraday-bucket-copy.md`, approved, plan in progress on `feature/feat-data-001-intraday-bucket-copy`): it also declares `(FEAT-DATA-001, DASHBOARD-04)`, adds `gcp/fetchers/export_intraday_bars.py` and edits `fetch_alphavantage_intraday.main`, a function of the writer closure. Before Task 6 and Task 9. A row it left is extended, not replaced (Task 9).
  - FEAT-DATA-001 strict bar loader (`specs/2026-11-13-feat-data-001-strict-bar-loader.md`, approved, no plan): adds two tests to `tests/meta/test_production_writers.py` and changes `REPLAY_PATH` and `REPLAY_EXEMPT`. This plan appends one section at the end of that file and edits no existing line, so the two merge as text. Its prototype counted one `DELETE` at `gcp/migrate_to_gcp.py:249`, which Task 4 removes; that count is that lane's to restate.
  - FEAT-DATA-001 watched-ticker ingest v3 and FEAT-DEPLOY-001's wiring for it (both plans `ready`, `pr: null`): v3 edits `_run_backfill` and `_backfill_targets` of `gcp/fetchers/fetch_market_data.py` (neither is in the writer closure), adds `gcp/fetchers/fetch_watched_tickers.py`, edits `scripts/audit_data_freshness.py` (already listed in Task 6) and rewrites the `(FEAT-DATA-001, SHARED-07)` note, which is not one of this plan's four. The wiring adds `deploy_fetch_watched_tickers` and `watched-tickers-nightly` to `gcp/deploy.sh`; its command runs neither writer module. Before Task 6 and Task 9. If Task 6's test then names a new file, report it to the owner; do not add it to a list on your own call.
  - FEAT-INSIGHT-001 write routes 410 r2 (plan `ready`, `pr: null`): declares `(FEAT-INSIGHT-001, JOURNAL-01)`, a different row of the same notes table, and regenerates the same snapshot file. Before Task 9.
  - FEAT-OPTION-001 options mutation retirement (draft, no plan; its tests `test_parser_grammar_unchanged` and `test_supported_paths_still_dispatch` do not exist on `main`): if it is implemented first, Task 4 also edits those two tests to seven selectors and takes the selector out of its help text (spec, Risks).
- Choices this plan makes where the spec leaves one open (each is reported to the owner with the plan):
  - The writer closure is asserted by a floor (it holds `main` and at least three names per file), not by equality with the seven names of done_when[6]: the spec says it is computed, not listed by hand. The seven are recorded on the PR as the run's output.
  - Check (d) reads every `gcp/deploy.sh` line whose first word starts with `_schedule`, not only `_schedule` and `_schedule_with_args`, so `_schedule_verified` and `_schedule_with_args_verified` cannot carry a fourth scheduler past it. Today the result is the same three.
  - `_sent_params` in `tests/gcp/test_intraday_as_traded.py` loses its `try`/`except RuntimeError` (`:50-53`): the job's fetch was the only caller that raised on a vendor note (run 2026-11-14: `fetch_month`, `fetch_minute_bars` and `fetch_minute_data` return), and its comment names the removed caller. The spec does not list this edit.
  - Review Focus adds five tests the spec's counts do not include: `tests/gcp/test_backfill_ticker.py` goes from 23 cases to 29, `tests/meta/test_production_writers.py` from 79 to 88.

## What stops in production, and when

- At the merge: nothing. No file under `platform/` changes and nothing under `platform/` or `lib/` imports either changed module, so the API the merge deploys behaves as before; a Cloud Run Job keeps the image its `deploy_*` function last gave it (`gcp/deploy.sh:1296-1311`; read from the file, not from GCP).
- From the owner's deploy of the jobs image (`./gcp/deploy.sh discord`, `gcp/deploy.sh:5429`, or `all`, `:5472`), a `backfill-ticker` execution:
  - sends no `TIME_SERIES_INTRADAY` request (today one per month touched, 1 or 2) and upserts no row into `market_data_intraday` (today about 20,000 per month touched, stamped `alphavantage`). Evidence, planning run of 2026-11-14 on 20d9c47b with `requests.get` captured: `run()` for AMD and 2026-04-24 sent `TIME_SERIES_DAILY_ADJUSTED` and `TIME_SERIES_INTRADAY` and upserted `market_data_daily` and `market_data_intraday`. Task 2's test is that run.
  - writes `pre_*` and `gap_pct` only for a date whose premarket bars the table already holds, and logs L2 for each date it does not;
  - ends non-zero when the premarket bar read fails, where today it upserts the row without premarket fields and exits 0.
- Who relied on the bars the job wrote:
  - Discord `/replay` and `scripts/backfill_and_replay.py`, until #1891. Neither dispatches the job now, and no shell or workflow file names it outside `gcp/deploy.sh` and the test copy of it (`tests/fixtures/retry_split/deploy.sh`); `gcp/deploy.sh` gives it no scheduler.
  - The job's own premarket step, for a ticker the nightly does not pull: its `pre_*` fields stay empty until an operator brings the bars with a fetcher command (spec, Design 4 table).
  - An operator who ran the job by hand to make a ticker chartable. Not checked: when and by whom the job last ran. The committed snapshot `tests/fixtures/live_gcp_snapshot_2026-09-07.json` records its latest execution then as `backfill-ticker-z8s7h` on 2026-05-04; that is a fixture, not a live read.
- `gcp/migrate_to_gcp.py` is not deployed; it runs from an operator's checkout. From a checkout of this change, `./gcp/deploy.sh migrate` with no selector no longer deletes and reloads the 1-min rows of SPY, IWM, QQQ and SPX from local parquet, and `--table market_data_intraday` exits 2 with argparse's `invalid choice` after the three secret reads.
- What the owner runs or checks at deploy is in Close-out 2 and 3.

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | `run` fetches and writes no 1-min bars | 2 |
| [1] | an absent premarket is said | 3 |
| [2] | a failed premarket read fails the run; the compute `except` is unchanged | 3 |
| [3] | no intraday loader in the migrate script | 4 |
| [4] | only the two fetchers write; both still write | 5 |
| [5] | the scan's 20 and 8 snippets | 1 |
| [6] | the entry points | 6 |
| [7] | the Yahoo archive is the one named deleter | 7 |
| [8] | nothing dispatches `backfill-ticker` | 7 |
| [9] | the as-traded guard and the UTC writers test | 2 |
| [10] | `make test`, the inventory at 2 writers, the generated-docs test | 8 (render in 2, 3, 4) |
| [11] | product record, site notes, snapshot, audit, gate | 9 |

## Review Focus

Inputs the spec implies and no done_when test pins. Each has a test in the task that owns the code.

- Several target dates with no bars, and a lower-case ticker: one L2 per date, each naming the ticker in upper case, and every date's row is still upserted. Task 3.
- Premarket bars that all fail the print filter (`bar_count` 0, `gcp/backfill_ticker.py:539`): the row is upserted without `pre_` keys and no L2 is logged, because the table did hold bars. Task 3.
- A write helper called with a partition name or a `public.` prefix (`bulk_insert_dataframe(df, "market_data_intraday_other")`, `upsert_dataframe(df, "public.market_data_intraday", ...)`), and source text that does not parse: the first two are writes; the third raises `SyntaxError` instead of being skipped. Task 1.
- A writer function reached by a relative import inside `gcp/fetchers/` (`from .fetch_market_data import process_ticker`) or by `importlib.import_module("gcp.fetchers.fetch_market_data")`: both are rejected; the same relative import in a file under `scripts/` is not, because it names `scripts/fetch_market_data.py`, another module. Task 6.
- The job's name inside an f-string (`f"jobs/backfill-ticker:run?project={p}"`): flagged, since its literal parts are string constants; the name in a docstring or a comment is not. Task 7.

## File map

| File | Change | Task |
|---|---|---|
| `tests/meta/test_production_writers.py` | one appended section: the scan, the lists, nine tests | 1, 5, 6, 7 |
| `gcp/backfill_ticker.py` | `av_intraday_month` and step 2 removed, L1; strict premarket read, L2; two `AUDIT` comments; docstrings | 2, 3 |
| `tests/gcp/test_backfill_ticker.py` | `stubbed_run`, `_backfill_premarket_row`, `_premarket_reads` (new), six tests | 2, 3 |
| `tests/gcp/test_intraday_as_traded.py`, `tests/gcp/test_intraday_writers_utc.py` | one test and one import fewer each | 2 |
| `gcp/migrate_to_gcp.py` | the intraday loader, its selector, its helper, its map and its import removed | 4 |
| `tests/gcp/test_migrate_to_gcp_dispatch.py` | new, one test | 4 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 2, 3, 4, 8 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 9 |

## Task 1: The writer scan and its rewrite test

Spec: Design 4 ("The writer scan"; test 3). Advances done_when[5]. Needs: nothing. Green on the unmodified tree.

**Files:** Modify `tests/meta/test_production_writers.py` (append after `:1325`; no existing line changes).

**Interfaces:** Consumes, from the same file, unedited: `SCAN_ROOTS` (`:31`), `_py_files` (`:68`), `_rel` (`:76`), `_FUNC` (`:449`), `_replay_tree` (`:464`), `_docstring_nodes` (`:507`), `_call_name` (`:553`). Produces, all new, at module level:
- `INTRADAY_TABLE = "market_data_intraday"`, `INTRADAY_PARTITION_SUFFIXES = ("_spy", "_iwm", "_qqq", "_spx", "_other")` (`gcp/schema.sql:156-165`).
- `SANCTIONED_INTRADAY_WRITERS = {"gcp/fetchers/fetch_alphavantage_intraday.py", "gcp/fetchers/fetch_market_data.py"}`
- `INTRADAY_WRITE_HELPERS = ("upsert_dataframe", "bulk_insert_dataframe", "bulk_copy_upsert", "bulk_copy_update", "replace_rows_in_window", "to_sql")`
- `intraday_write_sites(src: str) -> list[tuple[int, str]]`: sorted `(line, what)`. `what` is `"sql"` for a statement (line of the string's first line) or the helper's name (line of the call). Raises `SyntaxError` on text that does not parse.

The rules, which the signature does not determine:
- Strings read: each string constant that is neither a docstring nor a part of an f-string, and each f-string as the join of its literal parts. `_sql_strings` (`:167`) is not reused: it takes a path and keeps docstrings.
- A statement is a verb, whitespace, then the name. Verbs: `INSERT INTO`, `MERGE INTO`, `COPY`, `DELETE FROM`, `UPDATE`, `TRUNCATE` with an optional `TABLE`. The name: an optional `public.`, then the table or the table with one partition suffix, with optional double quotes around either name, not followed by a word character. Case-insensitive.
- A call is a write when `_call_name` is in `INTRADAY_WRITE_HELPERS` and a string constant equal to the table or a partition, with an optional `public.`, sits anywhere inside a positional or keyword argument.
- Not copied from `_ROW_WRITE` (`:40`): the 300-character raw-text window and the name `upsert_rows`.

- [ ] Write `_INTRADAY_MUST_CATCH` and `_INTRADAY_MUST_IGNORE` and `test_the_intraday_writer_scan_catches_the_obvious_rewrites`: `len` is 20 and 8; `[s for s in _INTRADAY_MUST_CATCH if not intraday_write_sites(s)] == []`; `[s for s in _INTRADAY_MUST_IGNORE if intraday_write_sites(s)] == []`; in the long-argument snippet the table name starts more than 300 characters after the opening parenthesis.

```python
_INTRADAY_MUST_CATCH = [
    'upsert_dataframe(pd.DataFrame(rows), "market_data_intraday", ["ticker", "interval", "ts"])',
    "bulk_insert_dataframe(df, 'market_data_intraday', chunksize=5000)",
    'bulk_copy_upsert(df, "market_data_intraday", ["ticker", "interval", "ts"])',
    'bulk_copy_update(df, "market_data_intraday", ["ticker", "interval", "ts"], ["close"])',
    "replace_rows_in_window(df, 'market_data_intraday', {'ticker': s, 'interval': '1min'}, 'ts', a, b)",
    'df.to_sql("market_data_intraday", engine, if_exists="append")',
    'execute_sql("INSERT INTO market_data_intraday (ticker) VALUES (:t)")',
    'cur.execute("COPY market_data_intraday FROM STDIN")',
    'execute_sql("DELETE FROM market_data_intraday WHERE ticker = :t")',
    'execute_sql("UPDATE market_data_intraday SET volume = 0 WHERE ticker = :t")',
    'execute_sql("TRUNCATE TABLE market_data_intraday")',
    'execute_sql("MERGE INTO market_data_intraday m USING staged s ON m.ts = s.ts WHEN NOT MATCHED THEN INSERT VALUES (s.ts)")',
    'execute_sql("insert into public.market_data_intraday_spy (ticker) values (:t)")',
    'execute_sql("TRUNCATE market_data_intraday_other")',
    "execute_sql('INSERT INTO \"market_data_intraday\" (ticker) VALUES (:t)')",
    'execute_sql("DELETE FROM " "market_data_intraday WHERE ticker = :t")',
    'execute_sql("WITH gone AS (DELETE FROM market_data_intraday_qqq WHERE ts < :c RETURNING 1) SELECT count(*) FROM gone")',
    "upsert_dataframe(pd.DataFrame([" + ", ".join(["{'ticker': 'SPY'}"] * 30) + "]), 'market_data_intraday', ['ticker', 'interval', 'ts'])",
    'upsert_dataframe(df, conflict_cols=["ticker", "interval", "ts"], table="market_data_intraday")',
    """execute_sql(f"DELETE FROM market_data_intraday WHERE ticker = '{t}'")""",
]
_INTRADAY_MUST_IGNORE = [
    'query_to_dataframe("SELECT ts FROM market_data_intraday WHERE ticker = :t")',
    'query_to_dataframe("SELECT ts FROM market_data_intraday WHERE ticker = :t FOR UPDATE")',
    'upsert_dataframe(df, "market_data_daily", ["ticker", "date"])',
    'execute_sql("DELETE FROM archive_yahoo_market_data_intraday WHERE ticker = :t")',
    'execute_sql("INSERT INTO market_data_intraday_flow_15m (ticker) VALUES (:t)")',
    'log.info("wrote %d rows to market_data_intraday", n)',
    'def f():\n    """DELETE FROM market_data_intraday is never run here."""\n    return 1',
    "x = 1  # UPDATE market_data_intraday by hand",
]
```

- [ ] Write `test_the_intraday_writer_scan_reads_partitions_and_refuses_unparseable_text` (Review Focus): `intraday_write_sites('bulk_insert_dataframe(df, "market_data_intraday_other")')` and `intraday_write_sites('upsert_dataframe(df, "public.market_data_intraday", ["ticker", "interval", "ts"])')` are not empty; `intraday_write_sites("def (:")` raises `SyntaxError`.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q -k intraday_writer_scan` (expect FAIL: `intraday_write_sites` is not defined).
- [ ] Implement the constants and `intraday_write_sites`.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q` (expect 81 passed: the 79 on `main` and these two).
- [ ] Variant for the record: drop `MERGE INTO` from the verbs; expect the first test to fail naming the `MERGE INTO` snippet; revert.
- [ ] Run the scan over the untouched tree:
  `python3 -c "from tests.meta import test_production_writers as g; [print(g._rel(p), s) for p in g._py_files(g.SCAN_ROOTS) for s in g.intraday_write_sites(p.read_text(errors='ignore'))]"`
  Expect exactly six lines: `gcp/backfill_ticker.py (659, 'upsert_dataframe')`; `gcp/fetchers/fetch_alphavantage_intraday.py (327, 'upsert_dataframe')` and `(644, 'replace_rows_in_window')`; `gcp/fetchers/fetch_market_data.py (574, 'upsert_dataframe')`; `gcp/migrate_to_gcp.py (249, 'sql')` and `(252, 'bulk_insert_dataframe')`. Any other line means a rule above is implemented differently; fix the function, not the expectation. Keep the output for the PR.
- [ ] Commit: `test(data): add the 1-min bar writer scan and its rewrite test`

## Task 2: `backfill-ticker` fetches and writes no 1-min bars

Spec: Design 1; Design 5; Design 6 (rows `stubbed_run`, as-traded and UTC). Advances done_when[0], [9]. Needs: nothing. The two guard files change in this task because both import or patch `av_intraday_month`.

**Files:** Modify `gcp/backfill_ticker.py` (`:1-49`, `:68`, `:137-164`, `:572-594`, `:640-663`), `tests/gcp/test_backfill_ticker.py` (`stubbed_run`, `:218-240`), `tests/gcp/test_intraday_as_traded.py` (`:21`, `:50-53`, `:81-83`, `:142-145`), `tests/gcp/test_intraday_writers_utc.py` (`:14`, `:66-94`).

**Interfaces:** `run() -> int` keeps its signature. `gcp.backfill_ticker` no longer has `av_intraday_month`.

- [ ] Write `test_run_fetches_and_writes_no_one_minute_bars(monkeypatch, caplog)` in `tests/gcp/test_backfill_ticker.py`. Env: `BACKFILL_TICKER=amd`, `ALPHA_VANTAGE_API_KEY=k`, `BACKFILL_DATES=2026-04-24`, `BACKFILL_ADD_TO_WATCHLIST=false`. Two runs, `BACKFILL_INCLUDE_NEWS` `false` then `true`, with `caplog.clear()` between. For each run:
  - `patch.object(mod.requests, "get", side_effect=fake_get)`, where `fake_get(url, params=None, **kw)` appends `params["function"]` to `seen` and answers by function: `TIME_SERIES_DAILY_ADJUSTED` with a `Time Series (Daily)` of 2026-04-23 and 2026-04-24 (keys `1. open` to `6. volume`, with `5. adjusted close`), `NEWS_SENTIMENT` with `{"feed": []}`, and `TIME_SERIES_INTRADAY` with one bar under `Time Series (1min)` at `2026-04-24 09:30:00`, so the old code runs to its end and the failure is the assertion, not a vendor error.
  - `patch("gcp.database.upsert_dataframe", ...)` recording `(table, frame)`; `add_to_watchlist` replaced by a function that raises `AssertionError`; `compute_indicators_for_full_range` and `compute_indicators_for_dates` replaced by `MagicMock`s; log captured with `caplog.at_level(logging.INFO, logger="backfill-ticker")`.
  - Assert: `mod.run() == 0`; `seen == ["TIME_SERIES_DAILY_ADJUSTED"]` for news `false` and `["TIME_SERIES_DAILY_ADJUSTED", "NEWS_SENTIMENT"]` for `true`; `"TIME_SERIES_INTRADAY" not in seen`; the recorded tables are `["market_data_daily"]`, whose frame has `date` `[date(2026, 4, 23), date(2026, 4, 24)]`, `ticker` `AMD` and `data_source` `alphavantage` on both rows; exactly one INFO record whose message equals L1; `compute_indicators_for_full_range` called once with `"AMD"`; `compute_indicators_for_dates` called once with `("AMD", [date(2026, 4, 23), date(2026, 4, 24)])`.
  - After both runs: `not hasattr(mod, "av_intraday_month")`.
- [ ] Run: `python3 -m pytest tests/gcp/test_backfill_ticker.py -q -k no_one_minute_bars` (expect FAIL at the request list: `["TIME_SERIES_DAILY_ADJUSTED", "TIME_SERIES_INTRADAY"]`, with `market_data_intraday` among the upserts). This is the record for [0].
- [ ] Implement in `gcp/backfill_ticker.py`:
  - Delete `av_intraday_month` (`:137-164`) and step 2 of `run` (`:640-663`). Where step 2 was, `log.info(L1)`. Drop `eastern_index_to_utc` from the import at `:68`; `eastern_bounds_utc` stays. `requests` and `AV_BASE` stay.
  - Module docstring: its first sentence (`:2`) is unchanged (`docs/product/infrastructure/05-a-ARCHITECTURE.md:917` quotes it). Lines `:4-5` say the job is run by hand by an operator and that nothing in the repo dispatches it. Item 2 (`:13-15`) goes and the rest are renumbered. The premarket item says the context is computed from the 1-min bars `market_data_intraday` already holds for the date, that a date with none gets no `pre_*` fields and a warning, and that this job fetches and writes no 1-min bars. Lines `:21-23` and `:37-45` (the watchlist default) are not touched.
  - `run` docstring (`:572-594`): four steps, no intraday step; the per-date step names the table as the source of its bars. Renumber the step comments in the body to match.
- [ ] Change `stubbed_run` (`tests/gcp/test_backfill_ticker.py:235`): drop the `av_intraday_month` patch line. Nothing else in the fixture changes.
- [ ] Change `tests/gcp/test_intraday_as_traded.py`: delete the import at `:21` and `test_backfill_ticker_month_fetch_requests_as_traded` (`:81-83`); in `_sent_params` call `call()` directly, without the `try`/`except RuntimeError` (`:50-53`); in `test_every_intraday_request_in_the_repo_asks_for_as_traded` the required set is the six files without `gcp/backfill_ticker.py`, the count is `len(sites) >= 7`, and a new line asserts `"gcp/backfill_ticker.py" not in files` with the sites in the message.
- [ ] Change `tests/gcp/test_intraday_writers_utc.py`: delete the `W3` comment and `test_backfill_ticker_writes_utc_instants` (`:66-94`) and the then unused `from datetime import date` (`:14`). The other seven tests are not touched.
- [ ] Run: `python3 -m pytest tests/gcp/test_backfill_ticker.py tests/gcp/test_intraday_as_traded.py tests/gcp/test_intraday_writers_utc.py tests/meta/test_production_writers.py tests/scripts/test_backfill_and_replay.py tests/gcp/test_discord_interactions.py -q` (expect all pass; the three files hold 24, 13 and 7 cases).
- [ ] Record for [9]: with the code change stashed and the new `not in files` line in place, `test_every_intraday_request_in_the_repo_asks_for_as_traded` fails naming `gcp/backfill_ticker.py:141`.
- [ ] The Task 1 scan command: no line for `gcp/backfill_ticker.py`. The render step.
- [ ] Commit: `fix(data): stop backfill-ticker fetching and writing 1-min bars`

## Task 3: The premarket bar read is strict

Spec: Design 2; Design 6 (row `_backfill_premarket_row`); Non-goals (the two daily reads, the compute `except`). Advances done_when[1], [2]. Needs: Task 2.

**Files:** Modify `gcp/backfill_ticker.py` (`compute_indicators_for_dates`; lines as on 20d9c47b, before Task 2 shortens the file: `:374`, `:442`, `:498-561`), `tests/gcp/test_backfill_ticker.py` (`_backfill_premarket_row`, `:357-401`; new helper and tests after it).

**Interfaces:** `compute_indicators_for_dates(ticker: str, target_dates: list[date]) -> None` keeps its signature and now raises what the bar read raises. Produces in the test file:
- `_premarket_reads(monkeypatch, bar_answer) -> types.SimpleNamespace` (new) with `written: list[tuple[str, pd.DataFrame]]` (table, frame, in call order), `bar_reads: list[date]` (the bar reads asked of the strict reader, by the date of `params["start"]`) and `swallowed_bar_reads: list[date]` (the same reads asked of the old reader).
  - `bar_answer(day: date, bars: Callable[[date], pd.DataFrame]) -> pd.DataFrame` returns a frame or raises. `bars(day)` is 30 one-minute bars from 08:00 Eastern of that day as aware UTC `ts`, with `open` 100.6, `high` 100.65, `low` 100.55, `close` 100.62, `volume` 1000.
  - It sets `gcp.database.query_to_dataframe` to answer a `market_data_daily` read from 60 business days ending 2026-11-06 (built as `_backfill_premarket_row` builds its frame, every day's high and low 0.5 either side of its close), cut at `params["fd"]`, newest first, and to answer a `market_data_intraday` read through `bar_answer` while recording it in `swallowed_bar_reads`. It sets `query_to_dataframe_strict` to a `(sql, params=None, timeout_s=None)` that records and answers the bar read, then calls `install_level_params(monkeypatch, ["SPY", "AMD"])`, which wraps the reader already in place (`tests/lib/level_params_fixtures.py:165-181`). It sets `upsert_dataframe` to record.

- [ ] Change `_backfill_premarket_row`: the bar frame is answered by `gcp.database.query_to_dataframe_strict`, set before `install_level_params`; `query_to_dataframe` answers the daily read only. Its two tests are not edited.
- [ ] Write, with `d4`, `d5`, `d6` the dates 2026-11-04 to 2026-11-06 and log captured on `"backfill-ticker"`:
  - `test_premarket_absent_bars_says_so`: every bar read answers `pd.DataFrame()`; `compute_indicators_for_dates("SPY", [d6])`. One upsert, to `market_data_daily`, one row, `date == d6`; no key of the row starts with `pre_` and `gap_pct` is not a key; the WARNING records that hold `market_data_intraday` are exactly one, equal to L2 for `SPY` and `2026-11-06`; `bar_reads == [d6]` and `swallowed_bar_reads == []`.
  - `test_premarket_read_failure_fails_the_run`, in a loop over `ConnectionError("connection refused")` and `KeyError("close")`, after asserting `lib.infra_errors.is_infrastructure_error` is true for the first and false for the second:
    - `bar_answer` raises the exception for `d5` and returns `bars(day)` otherwise. `compute_indicators_for_dates("SPY", [d4, d5, d6])` raises, and `excinfo.value is` that exception. `written` is one entry, the `market_data_daily` row of `d4`, whose columns include `pre_high`, `pre_low`, `pre_vwap` and `pre_volume`; `bar_reads == [d4, d5]`; `swallowed_bar_reads == []`.
    - Under `run()`: env `BACKFILL_TICKER=amd`, `ALPHA_VANTAGE_API_KEY=k`, `BACKFILL_DATES=2026-11-05,2026-11-06`, `BACKFILL_INCLUDE_NEWS=false`, `BACKFILL_ADD_TO_WATCHLIST=true`; `av_daily_full` patched to a two-row frame, `compute_indicators_for_full_range` patched, `add_to_watchlist` a `MagicMock`. `run()` raises the same object; the stub's `call_count` is 0; after the first entry of `written` (step 1's daily rows) there is exactly one more, the row of `d4`.
  - `test_premarket_compute_defect_is_still_a_warning`: bars for `d6`, `lib.indicators.calculate_premarket_context` patched to raise `KeyError("close")`. No exception; one row for `d6` with no `pre_` key; exactly one WARNING record, and it starts `pre-market compute failed`.
  - `test_premarket_absent_bars_warns_once_per_date_in_upper_case` (Review Focus): `compute_indicators_for_dates("spy", [d5, d6])` with no bars upserts two rows and logs L2 for `SPY` and `2026-11-05`, then for `SPY` and `2026-11-06`, and no third.
  - `test_bars_that_all_fail_the_print_filter_log_no_absent_warning` (Review Focus): bars for `d6`, `calculate_premarket_context` patched to return `{"bar_count": 0}`. One row without a `pre_` key; no record holds `no 1-min bars`.
- [ ] Run: `python3 -m pytest tests/gcp/test_backfill_ticker.py -q -k "premarket or print_filter"`. Expect three new tests to FAIL: `test_premarket_absent_bars_says_so` and the once-per-date test find no record naming the table (`assert [] == [...]`), and `test_premarket_read_failure_fails_the_run` reports `DID NOT RAISE ConnectionError`. The compute-defect pin and the print-filter test pass, as the spec says of `main`. All five results were seen on 20d9c47b in the planning run of 2026-11-14. The two existing `_backfill_premarket_row` tests should fail as well, since the old code never asks the strict reader for bars; that was reasoned, not run. This is the record for [1] and [2].
- [ ] Implement in `compute_indicators_for_dates`: move the `eastern_bounds_utc` call and the bar read out of the `try`, with the read on `query_to_dataframe_strict`, the same SQL text and the same three parameters, no `timeout_s`. After it, `if ibars.empty:` logs L2 with `ticker.upper()` and `fd.isoformat()`. The `try` now opens at `if not ibars.empty:`; its `except` and its message do not change. No `try` around the read.
- [ ] Above each daily read (`:374`, `:442`) add one comment, in the form `gcp/migrate_to_gcp.py:257` uses: `# AUDIT-2026-05-13: silent fallback — query_to_dataframe returns an empty frame on an outage, which reads here as "insufficient daily history"`.
- [ ] Run: `python3 -m pytest tests/gcp/test_backfill_ticker.py tests/meta/test_timezone_boundaries.py -q` (expect all pass; 29 cases in the first; the timezone baseline does not change).
- [ ] Variants for the two tests that pass before the change: make the compute `except` re-raise and expect `test_premarket_compute_defect_is_still_a_warning` to fail with `KeyError`; log L2 without the `if ibars.empty:` test and expect `test_bars_that_all_fail_the_print_filter_log_no_absent_warning` to fail. Revert both.
- [ ] The render step.
- [ ] Commit: `fix(data): fail the backfill run when the premarket bar read fails`

## Task 4: `gcp/migrate_to_gcp.py` has no intraday loader

Spec: Design 3; Design 6 (row `test_migrate_to_gcp_dispatch.py`). Advances done_when[3]. Needs: Task 1.

**Files:** Modify `gcp/migrate_to_gcp.py` (`:48`, `:96-101`, `:109-115`, `:195-262`, `:773`, `:819`). Create `tests/gcp/test_migrate_to_gcp_dispatch.py`.

**Interfaces:** Consumes `intraday_write_sites` (Task 1), imported as `from tests.meta import test_production_writers as guard`. `TABLE_FUNCS` keeps seven keys.

- [ ] Write `test_no_intraday_loader_remains(monkeypatch, tmp_path)`, with `import gcp.migrate_to_gcp as m` and `REPO = Path(__file__).resolve().parents[2]`:
  - `m` has none of `migrate_market_data_intraday`, `_normalize_ohlcv`, `COLUMN_MAP`.
  - `{k: f.__name__ for k, f in m.TABLE_FUNCS.items()}` equals `{"gcs_raw": "upload_raw_parquets", "market_data_daily_av": "migrate_market_data_daily_av", "daily_indicators": "backfill_daily_indicators", "etf_options_snapshots": "migrate_etf_options", "av_options": "migrate_av_options", "earnings_options_snapshots": "migrate_earnings_options", "trades": "migrate_trades"}`.
  - The text of `gcp/migrate_to_gcp.py` does not hold `market_data_intraday`, and `guard.intraday_write_sites(text) == []`.
  - With `monkeypatch.setitem(m.TABLE_FUNCS, "trades", recorder)` and `sys.argv` set to `["migrate_to_gcp.py", "--table", "trades", "--data-dir", str(tmp_path)]`, `m.main()` calls the recorder once with `(tmp_path, False)`.
  - `subprocess.run([sys.executable, "gcp/migrate_to_gcp.py", "--table", "market_data_intraday"], cwd=REPO, capture_output=True, text=True, timeout=120)` returns code 2 and its stderr holds `invalid choice: 'market_data_intraday'`.
  - Nothing is asserted about a call without `--table`.
- [ ] Run: `python3 -m pytest tests/gcp/test_migrate_to_gcp_dispatch.py -q` (expect FAIL at the first assertion: the module has `migrate_market_data_intraday`). This is the record for [3].
- [ ] Implement: delete the section comment and `migrate_market_data_intraday` (`:195-262`), its `TABLE_FUNCS` entry (`:773`), its call in the default path (`:819`), `_normalize_ohlcv` (`:109-115`), `COLUMN_MAP` (`:96-101`) and the `eastern_index_to_utc` import (`:48`). The section comment at `:94` and the indicator import below it stay. The docstring of `_trade_times_to_utc` (`:691-705`) is history of #764 and is not edited.
- [ ] Run: `python3 -m pytest tests/gcp/test_migrate_to_gcp_dispatch.py tests/gcp/test_migrate_trades_tz_guard.py tests/meta/test_production_writers.py tests/meta/test_timezone_boundaries.py -q` (expect all pass).
- [ ] The Task 1 scan command: four lines, all in the two fetchers. The render step.
- [ ] Commit: `fix(data): drop the intraday loader from the parquet migration`

## Task 5: Only the two fetchers write the table

Spec: Design 4 ("The two modules"; tests 1 and 2). Advances done_when[4]. Needs: Tasks 1, 2, 4.

**Files:** Modify `tests/meta/test_production_writers.py` (the section of Task 1).

**Interfaces:** Consumes `intraday_write_sites`, `SANCTIONED_INTRADAY_WRITERS`.

- [ ] Write:
  - `test_only_the_two_fetchers_write_one_minute_bars`: over `_py_files(SCAN_ROOTS)`, the files outside `SANCTIONED_INTRADAY_WRITERS` with at least one site are none; the failure message gives each file with its sites.
  - `test_sanctioned_intraday_writers_still_write`: each file of the set exists and `intraday_write_sites` of its text is not empty.
- [ ] Record for [4], on `main`'s code: `python3 -c "import subprocess; from tests.meta import test_production_writers as g; [print(f, g.intraday_write_sites(subprocess.run(['git', 'show', 'origin/main:' + f], capture_output=True, text=True, check=True).stdout)) for f in ('gcp/backfill_ticker.py', 'gcp/migrate_to_gcp.py')]"` (expect `[(659, 'upsert_dataframe')]` and `[(249, 'sql'), (252, 'bulk_insert_dataframe')]` while `origin/main` is 20d9c47b).
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q` (expect 83 passed).
- [ ] Variant for the second test's record: add `"gcp/backfill_ticker.py"` to the set; expect it to fail naming that file; revert.
- [ ] Commit: `test(data): hold the 1-min bar table to its two writer modules`

## Task 6: What may start the two writers

Spec: Design 4 ("What starts them"; test 4). Advances done_when[6]. Needs: Task 1. A guard on a new path: it passes on the unmodified tree.

**Files:** Modify `tests/meta/test_production_writers.py` (the same section).

**Interfaces:** Consumes `intraday_write_sites`. Produces, all new:
- `INTRADAY_WRITER_MODULES = {"gcp/fetchers/fetch_alphavantage_intraday.py": "gcp.fetchers.fetch_alphavantage_intraday", "gcp/fetchers/fetch_market_data.py": "gcp.fetchers.fetch_market_data"}`
- `INTRADAY_WRITER_JOBS = ("fetch-market-data", "fetch-alphavantage-intraday", "intraday-bulk-backfill")`
- `INTRADAY_WRITER_MODULE_STARTERS = {"scripts/backfill_watchlist_data.py"}`
- `INTRADAY_WRITER_JOB_NAME_FILES = {"platform/api/routers/admin.py", "scripts/audit_data_freshness.py", "scripts/maintenance/refresh_architecture_drawio.py"}`
- `INTRADAY_WRITER_DEPLOY_FUNCTIONS = {"deploy_fetch_market_data", "deploy_fetch_alphavantage", "deploy_intraday_bulk_backfill"}`, `INTRADAY_WRITER_SCHEDULERS = {"fetch-market-data-daily", "av-intraday-monthly", "av-intraday-nightly"}`
- `intraday_writer_closure(src: str) -> set[str]`: the top-level functions of the file that hold a site of `intraday_write_sites` at any depth, plus those that call one of them by bare name, repeated until nothing is added.
- `writer_import_offenders(rel: str, src: str, closures: dict[str, set[str]]) -> list[str]`, check (a); `closures` is keyed by dotted module name; each entry is `"{line}: {what}"`. An offender is `from <module> import <closure name>` or `import *`, with a relative import resolved against `rel`'s package, or an attribute access `<alias>.<closure name>` where the alias was bound by `from gcp.fetchers import <leaf> [as x]`, `import <module> as x`, or is the dotted name itself after `import <module>`.
- `writer_module_strings(src: str) -> list[int]`, check (b): lines of string constants outside docstrings (the literal parts of an f-string included) that hold a module's dotted name or its path.
- `writer_job_strings(src: str) -> list[int]`, check (c): the same for a job name as a whole name, neither preceded nor followed by a word character or a hyphen.
- `deploy_writer_entry_points(text: str) -> tuple[set[str], set[str], set[str]]`, check (d), on the text with lines whose first character after indentation is `#` dropped: the shell functions (`name() {` at column 0, to the next one) whose body holds either module's dotted name; the job names those functions pass to `gcloud run jobs create`; and the first quoted argument of every line whose first word starts with `_schedule` and that has one of `INTRADAY_WRITER_JOBS` as a quoted argument.

- [ ] Write `test_only_named_entry_points_reach_the_intraday_writers`:
  - Closures are computed from the two files; each holds `main` and at least three names.
  - (a) no other file under `SCAN_ROOTS` has an import offender.
  - (b) the files outside the two with a module string are exactly `INTRADAY_WRITER_MODULE_STARTERS`. (c) the files outside the two with a job string are exactly `INTRADAY_WRITER_JOB_NAME_FILES`. Equality holds both ways, so a listed file that stopped naming one fails too.
  - (d) `deploy_writer_entry_points` of `gcp/deploy.sh` is `(INTRADAY_WRITER_DEPLOY_FUNCTIONS, set(INTRADAY_WRITER_JOBS), INTRADAY_WRITER_SCHEDULERS)`.
  - With the same closures, checked as the file `gcp/new_job.py`, each of `_ENTRY_MUST_REJECT` has at least one offender among (a), (b) and (c), and none of `_ENTRY_MUST_ACCEPT` has any; `len` is 9 and 4.

```python
_ENTRY_MUST_REJECT = [
    "from gcp.fetchers.fetch_market_data import write_intraday_to_sql",
    'from gcp.fetchers import fetch_alphavantage_intraday as fai\ndef f():\n    return fai.replace_month("SPY", 2026, 10, "k", True)',
    "import gcp.fetchers.fetch_market_data\ndef f():\n    gcp.fetchers.fetch_market_data.main()",
    "from gcp.fetchers.fetch_market_data import process_ticker",
    "from gcp.fetchers.fetch_alphavantage_intraday import *",
    'subprocess.run([sys.executable, "-m", "gcp.fetchers.fetch_market_data", "--tickers", t])',
    'subprocess.run(["python", "gcp/fetchers/fetch_alphavantage_intraday.py", "--symbol", t])',
    'execute_cloud_run_job("fetch-market-data", {})',
    'url = f"https://run.googleapis.com/v2/projects/{p}/locations/{r}/jobs/intraday-bulk-backfill:run"',
]
_ENTRY_MUST_ACCEPT = [
    "from gcp.fetchers.fetch_market_data import _run_backfill, fetch_minute_data",
    'from gcp.fetchers import fetch_market_data as fmd\nTICKERS = fmd.TICKERS\nrows = fmd.fetch_minute_data("SPY", "2026-11-13", "k")',
    'names = ["fetch-market-data-daily", "av-intraday-nightly", "av-intraday-monthly"]',
    '"""Runs after gcp.fetchers.fetch_market_data and the fetch-market-data job."""\nx = 1',
]
```

- [ ] Write `test_the_entry_point_checks_read_relative_imports_and_importlib` (Review Focus): `from .fetch_market_data import process_ticker` is an offender of (a) as `gcp/fetchers/new_fetcher.py` and is not one as `scripts/new_script.py`; `importlib.import_module("gcp.fetchers.fetch_market_data").main()` has a line in `writer_module_strings`.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q -k entry_point` (expect FAIL: names not defined).
- [ ] Implement the constants and the five functions.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q` (expect 85 passed).
- [ ] Print what the checks read on the tree and keep it for the PR. Expect, on 20d9c47b: closures `main`, `process_symbol`, `replace_month`, `run_replace_months` and `main`, `process_ticker`, `write_intraday_to_sql`; no import offender; (b) `scripts/backfill_watchlist_data.py:265`; (c) `platform/api/routers/admin.py:1262`, `scripts/audit_data_freshness.py:889` and `:999`, `scripts/maintenance/refresh_architecture_drawio.py:70`; (d) the functions at `gcp/deploy.sh:2146`, `:2211` and `:3738` and the schedulers at `:4622`, `:4723` and `:4741`. A file or line beyond these after a merge of `main` is another lane's entry point: report it to the owner.
- [ ] Variant for the record: empty `INTRADAY_WRITER_MODULE_STARTERS`; expect the test to fail naming `scripts/backfill_watchlist_data.py`; revert.
- [ ] Commit: `test(data): list what may start the two 1-min bar writers`

## Task 7: The named deleter and the dispatch scan

Spec: Design 4 ("The one known deleter the scan cannot see"; tests 5 and 6). Advances done_when[7], [8]. Needs: Task 1. Both pass on the unmodified tree.

**Files:** Modify `tests/meta/test_production_writers.py` (the same section).

**Interfaces:** Consumes `BACKFILL_JOB` (`:446`), `_docstring_nodes`, `_replay_tree`. Produces, new:
- `VARIABLE_TABLE_WRITERS = {"gcp/database.py", "scripts/archive_yahoo_data.py"}`
- `holds_variable_table_write(src: str) -> bool`: true when the text holds both an f-string in which a literal part ends, trailing whitespace aside, with `INSERT INTO`, `MERGE INTO`, `DELETE FROM`, `UPDATE`, `TRUNCATE` (optional `TABLE`) or `COPY` and the next part is a field, and a string constant outside docstrings equal to the table or one of its partitions.
- `backfill_dispatch_lines(src: str) -> list[int]`: lines of string constants outside docstrings that contain `BACKFILL_JOB`.

- [ ] Write `test_the_yahoo_archive_is_the_one_named_deleter`:
  - the files under `SCAN_ROOTS` for which `holds_variable_table_write` is true are exactly `VARIABLE_TABLE_WRITERS`;
  - with `import scripts.archive_yahoo_data as a`: `set(a.TABLES) == {"earnings_options_snapshots", "etf_options_snapshots", "market_data_daily", "market_data_intraday"}`; `sorted(re.findall(r"'([^']*)'", a.YAHOO_PREDICATE)) == ["yahoo", "yahooquery", "yfinance"]`;
  - `a.delete_chunk(conn, "market_data_intraday", a.TABLES["market_data_intraday"], 500_000)` on a connection that records `str(stmt)` in `execute` (returning an object with `rowcount` 0) and does nothing in `commit`: one statement; with its whitespace collapsed it starts `DELETE FROM market_data_intraday WHERE`; it holds `a.YAHOO_PREDICATE`.
- [ ] Write `test_no_code_dispatches_backfill_ticker`: over `_py_files(SCAN_ROOTS)`, the files other than `gcp/backfill_ticker.py` with a dispatch line are none (the message gives file and lines); `backfill_dispatch_lines` of `gcp/backfill_ticker.py` is not empty (its logger name), so an empty walk cannot pass.
- [ ] Write `test_the_dispatch_scan_reads_f_strings_and_skips_docstrings` (Review Focus): `backfill_dispatch_lines` is not empty for `_execute_job('backfill-ticker', {})` and for `url = f"jobs/backfill-ticker:run?project={p}"`, and is empty for a module whose only mentions are its docstring and a comment.
- [ ] Run: `python3 -m pytest tests/meta/test_production_writers.py -q` (expect FAIL: names not defined). Implement. Run again (expect 88 passed).
- [ ] Record for [8], on the spec's base: run `backfill_dispatch_lines` over `git show c698b24e:gcp/discord_interactions/main.py` and `git show c698b24e:scripts/backfill_and_replay.py` (expect `[464, 470]` and `[178, 180, 306, 330]`).
- [ ] Variant for [7]'s record: empty `VARIABLE_TABLE_WRITERS`; expect the test to fail naming both files; revert.
- [ ] Commit: `test(data): pin the one variable-table deleter and the unused job`

## Task 8: Whole suite, the generated inventory, the files left alone

Spec: Done when (the suite and the inventory). Advances done_when[10]. Needs: Tasks 1 to 7.

- [ ] Run: `make test` (expect no failure that `origin/main` does not have; see Global Constraints for the two order-dependent tests). For orientation only, not a `make test` result: a planning run of 2026-11-14 over a scratch copy without `.git`, with the two removals and the strict read applied roughly and no test edited, gave 9,716 passed, and its 41 failures and errors were the 12 cases Tasks 2 and 3 edit (9 in `test_backfill_ticker.py`, 2 in the as-traded file, 1 in the UTC file) and 29 that failed on `not a git repository`.
- [ ] Run the render step once more on the final code and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass). `git status` shows no change to the three docs; if it does, commit: `docs(infra): re-render the inventory for the two bar writers`.
- [ ] Check the block: `grep -n 'market_data_intraday. | [0-9] | .gcp' docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md` prints one line, the multiwriter row ``| `market_data_intraday` | 2 | `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py` |`` (4 files on `main`, `:945`). The `backfill-ticker` row of the blast table no longer lists the table, and the graph has no `J_backfill_ticker ==> T_market_data_intraday` edge. A planning render of 2026-11-14 over a scratch copy with the two removals gave exactly this row.
- [ ] Run: `git diff --stat origin/main -- CLAUDE.md gcp/deploy.sh .github gcp/fetchers gcp/database.py gcp/schema.sql lib platform scripts tests/fixtures/timezone_boundary_baseline.json tests/gcp/test_migrate_trades_tz_guard.py tests/gcp/test_deploy_reachability.py tests/gcp/test_discord_interactions.py tests/scripts/test_backfill_and_replay.py tests/meta/test_timezone_boundaries.py` (expect empty).

## Task 9: Product record, site notes and the gate

Spec: Design 7; Capacity; Done when (the product records); product-delivery Phase 4 and Phase 5. Closes done_when[11]. Needs: Tasks 1 to 8. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/`, `tests/` or `platform/api` may change without redoing all four of them.

- [ ] Push with `git push -u origin fix/feat-data-001-two-bar-writers` and open a **draft** PR. Title: `FEAT-DATA-001: two writer modules for the 1-minute bar table`. Body, on the repository's template: the spec path and this plan's path; the 12 done_when items, each as a `- [ ]` line that starts with the item's text; the Capacity section from the spec's Capacity table, which counts and does not measure: Volume (0 rows to `market_data_intraday` per `backfill-ticker` run, was about 20,000 per month touched; about 800 daily rows and up to 8 indicator rows per run, as before), Velocity (1 daily AlphaVantage call and 0 or 1 news call per run, was 1 or 2 monthly 1-min calls more; about 40 Cloud SQL round trips per run), Wall-clock (20 to 80 s of round trips at 0.5 to 2 s each plus the vendor's answer time, against the 600 s task timeout, `gcp/deploy.sh:1299`; not measured), Cost (no new job, schedule or table; the job has no schedule; one or two vendor calls fewer per run); the section "What stops in production, and when" of this plan; the red-then-green records of Tasks 1 to 7; the choices listed in Global Constraints. Say that no route, response or page changes, so there is no deployed-site Playwright step (spec, Close-out 1).
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record only (`:513`; not the table row at `:35`): in the Status cell (`:520`) append, before the closing ` |`: `; market_data_intraday has two writer modules, the nightly history fetch and the daily fetcher: backfill-ticker no longer fetches or writes 1-min bars and fails its run when the premarket bar read fails, gcp/migrate_to_gcp.py has no intraday loader, and a guard test pins the two modules and their entry points ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed; no stored bar is written, deleted or moved by it)`. Last reviewed (`:524`) becomes the date of the PR's head commit; the gate compares the two exactly, so set it again if a later commit lands on another day.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-DATA-001` (`:320`): append to its `**PR lineage:**` line (`:346`) ` · [#N](https://github.com/TeneikaAskew/stocks/pull/N) *remediation: two writer modules for market_data_intraday, spec [#1884](https://github.com/TeneikaAskew/stocks/pull/1884)*`. No earlier entry is removed. Commit both docs and the plan: `docs(product): record the two bar writers under FEAT-DATA-001`.
- [ ] Site notes, step 1 (preflight). With every code and test commit in place and a clean tree, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`. It prints a JSON verdict and installs nothing yet (status `unverified`, exit 1). Copy its `source_identity_sha256`.
- [ ] Site notes, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes` (`:1297`), add four rows `| FEAT-DATA-001 | <component> | source_identity_sha256=<that hash>; <text> |` and change no other byte. Sort order among the FEAT-DATA-001 rows (`:1303-1306`): ADMIN-02, **CHARTS-01**, DASHBOARD-01, **DASHBOARD-04**, **JOURNAL-01**, LIVE-03, **LIVE-08**, SHARED-07. Each text is the component's opening clause followed, after one space, by the shared sentences, both copied from the block below with their backticks:

  ```text
  CHARTS-01     The 1-min bars behind `GET /api/market/dates/{ticker}`
  DASHBOARD-04  The 1-min bars behind `GET /api/market/data/{ticker}/{date}`
  JOURNAL-01    The 1-min bars behind `GET /api/market/dates/{ticker}`, as the Journal header reads it,
  LIVE-08       The 1-min bars behind `GET /api/market/data/{ticker}/{date}` in review mode

  shared        are in `market_data_intraday`, which only `gcp/fetchers/fetch_alphavantage_intraday.py` and `gcp/fetchers/fetch_market_data.py` now write: the `backfill-ticker` job (`gcp/backfill_ticker.py`) no longer fetches or upserts 1-min bars, and `gcp/migrate_to_gcp.py` has no intraday loader (`--table market_data_intraday` is refused by argparse, exit 2). No route, response or reader of this component changed and no stored bar was written, deleted or moved. Tests: `tests/meta/test_production_writers.py` (`test_only_the_two_fetchers_write_one_minute_bars`, `test_only_named_entry_points_reach_the_intraday_writers`), `tests/gcp/test_backfill_ticker.py`, `tests/gcp/test_migrate_to_gcp_dispatch.py`. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.
  ```

  If `main` already holds a `(FEAT-DATA-001, DASHBOARD-04)` row (the bucket copy), extend it instead: the new hash, this change's text, then ` Earlier: ` and that row's earlier prose unchanged. Tell the owner.
  Commit: `docs(site): note the two bar writers under four components`.
- [ ] Site notes, step 3. Run the same `produce` command again; it now writes the sidecar. Commit: `docs(site): regenerate the source snapshot`. These two commits are the last before the push.
- [ ] Site notes, step 4. Run `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched file later: merge `origin/main`, run the render step and `tests/scripts/test_check_generated_docs.py`, then repeat steps 1 to 4 with the new hash in all four rows.
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > /tmp/audit-branch.txt`; then `git worktree add --detach /tmp/audit-main origin/main`, run the same command there into `/tmp/audit-main.txt`, and `git worktree remove /tmp/audit-main`. Compare the `[P1]`, `[P2]` and `[P3]` finding lines: the branch reports none that `main` does not. A new finding is fixed or reported, not waived. Exit code 2 means the run itself failed, not that the docs are clean.
- [ ] Run on the final head: `make test` (done_when[10] names the PR head; expect no failure that `origin/main` does not have), `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass) and `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0). Push.
- [ ] Tick each done_when box in the PR body with its evidence beside it (test name, command output, file), then mark the PR ready for review. Review cap: two rounds.

## Close-out (not tasks; owner's steps)

Copied from the spec's Close-out, in its order, with the lines as they are on 20d9c47b. None of it is done by the implementer of this plan, none of it is a done_when box, and every production step waits for the owner's yes.

1. **What does not apply.** `platform/api/openapi.json` does not change, so solyra needs no contract sync, and no page changes, so there is no deployed-site Playwright run.
2. **Deploy** from `main`: the jobs image for `backfill-ticker` (`./gcp/deploy.sh discord`, `gcp/deploy.sh:5429`, or the full deploy). Before it, read-only, so the owner knows who still uses the job: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs executions list --job=backfill-ticker --region=us-east1 --limit=10`. The planning session had no production access; the last execution it can name is the fixture's, 2026-05-04.
3. **Verify by running the job once**, results on the PR. The run calls AlphaVantage once and re-upserts up to 800 daily rows for the ticker (`gcp/backfill_ticker.py:633` before this change), so it waits for the owner's yes and the ticker the owner names, one that already holds daily rows. With `BACKFILL_ADD_TO_WATCHLIST=false`, `BACKFILL_INCLUDE_NEWS=false` and one date at least two calendar months back, started outside 21:00 to 23:30 ET:
   - the execution's log holds L1, no `AV intraday-month` line and no `intraday bars` line; for the date and its prior weekday it holds either the `pre-market` line or L2 (a date whose bars all fail the print filter logs neither); it ends `backfill complete` and the execution exits 0;
   - secondary, read-only through `scripts/db_query_cr.sh`, before and after: `SELECT count(*) FROM market_data_intraday WHERE ticker = '<TICKER>' AND interval = '1min' AND ts >= '<month start>' AND ts < '<next month start>'` for the month of the date and the month of the day four days before it. Equal counts where the month was already held prove nothing; the count never stands in for the log.
4. **Docs**, on a `docs/` branch: the Data cells of the twenty rows of Design 7 (`docs/product/03-SITE-TRACEABILITY.md:334`, `:345`, `:430`, `:506-511`, `:513-517`, `:1041`, `:1042`, `:1044`, `:1051`, `:1053`, `:1054`); `docs/product/06-DATA-ARCHITECTURE.md:26`; `docs/product/infrastructure/05-i-GCP_IMPLEMENTATION_GUIDE.md:1234` and `:1609`, and, not in the spec's list, `:1195` and `:1600`, which describe the same loader; `05-j-GCP_IMPLEMENTATION_STATUS.md:125`.
5. **A FEAT-DEPLOY-001 change**, not this PR: the comment above `deploy_backfill_ticker` (`gcp/deploy.sh:1283-1293`), the comment at `:5426`, and, not in the spec's list, the help line at `:5550`, which says the Discord service runs the job; and the re-cut of the 2026-10-16 spec to seven selectors before it is planned.

Not in the spec's list, from product-delivery Phase 5 step 7: after the merge, on a `docs/` branch, set this plan's `status: done`.
