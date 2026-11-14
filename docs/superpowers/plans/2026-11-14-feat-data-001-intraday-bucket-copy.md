---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-13-feat-data-001-intraday-bucket-copy.md
branch: feature/feat-data-001-intraday-bucket-copy
pr: null
status: ready
---

# market_data_intraday: the bucket copy of the 1-min bars and the recompute readers that place rows by proof: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [7].

**Goal:** The nightly fetch job writes the SPY, QQQ and IWM 1-min bars to the trading-data bucket as one Parquet file per ticker-month with a manifest that says how whole and on what basis each month is, an analysis session reads them back with `read_bars`, and the three readers the runbook's recompute runs place a proven row at its stored instant.

**Architecture:** A new read-only module, `gcp/fetchers/export_intraday_bars.py`, reads one ticker-month at a time through `gcp.database.query_to_dataframe_strict`, places each row with `lib.eastern_time.place_stored_rows`, uploads the month's file and then writes that month's manifest entry under a GCS generation precondition. `fetch_alphavantage_intraday.main()` calls it after its fetch loop for the nightly's argument shape, and `--export-bars-from` writes the history. `_load_1m_bars`, `load_intraday_bars` and `read_minutes` select `inserted_at` and call `place_stored_rows` in place of `stored_intraday_to_eastern`. Nothing in the tree reads the copy: the table stays the only source for every job, replay and route.

**Tech Stack:** Python, pandas, pyarrow (Parquet, zstd), google-cloud-storage, SQLAlchemy with pg8000 through `gcp.database`, argparse, pytest.

**Spec:** docs/superpowers/specs/2026-11-13-feat-data-001-intraday-bucket-copy.md

## Global Constraints

- Base: `origin/main` at 20d9c47b or later (PR #1920, the checks this spec builds on, and PR #1891 are on it). The spec's code references are to c698b24e. `git diff --stat c698b24e 20d9c47b` over every file the spec cites changes only `lib/eastern_time.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `docs/product/03-SITE-TRACEABILITY.md`, `tests/meta/` and the timezone baseline (run 2026-11-14); this plan's line numbers are those of 20d9c47b. Branch `feature/feat-data-001-intraday-bucket-copy`. Commit this plan file first, alone: `docs(plan): FEAT-DATA-001 implementation plan for the intraday bucket copy`. The site-note producer of Task 13 refuses a branch with no committed plan.
- Scope: SPY, QQQ and IWM for the export. No trading cost anywhere. No production write, no deploy and no runbook step from this PR: every step of the spec's runbook is the owner's, each on the owner's own yes (Close-out below). The only production access is Task 1, read-only.
- Not in the PR's diff: `gcp/deploy.sh`, `platform/api`, `CLAUDE.md`, `.github/`, `lib/eastern_time.py`, `scripts/audit_data_freshness.py`, `tests/fixtures/timezone_boundary_baseline.json`, `tests/fixtures/intraday_checks.py`, and these tests: `tests/lib/test_intraday_session_readings.py`, `tests/gcp/test_intraday_verify_basis.py`, `test_intraday_as_traded.py`, `test_intraday_replace_months.py`, `test_intraday_writers_utc.py`, `test_av_intraday_universe.py`, `tests/meta/test_production_writers.py`, `test_timezone_boundaries.py`, `tests/agents/test_on_demand_level_calibration.py`.
- **The copy is never a source for the tree (CLAUDE.md 3.7.1).** No job, replay, backtest or route reads the bucket copy, and nothing falls back to it. The one reader is `read_bars`, called by hand in an analysis session. It has no database path (Task 5 proves it cannot import one) and returns `months`, the manifest entries, beside the bars, so what the caller prints carries the file, its hash, `exported_at`, `last_ts` and the basis state. Task 5's tree test keeps every other file from importing the module or naming the prefix.
- **The export module only reads the table.** `gcp/fetchers/export_intraday_bars.py` spells no write statement and no write-helper call on `market_data_intraday`, docstrings and log strings included (never the word "copy", "update" or "insert into" directly before the table name), and holds no string constant that names a writer module (`gcp.fetchers.fetch_...`) or a writer job (`fetch-alphavantage-intraday`, `fetch-market-data`, `intraday-bulk-backfill`). The two-bar-writers guard, when it lands, scans for exactly these. Its top-level imports are the standard library and pandas; `gcp.database`, `lib.eastern_time`, `lib.infra_errors`, pyarrow, the GCS client and the fetch module are imported inside functions.
- Reads: each new read is `gcp.database.query_to_dataframe_strict(sql, params, timeout_s=120)`, imported inside the function, with `interval = '1min'` in the SQL text. No `try` around a read. Exact SQL, copied from the spec:
  - B1 `SELECT ts, open, high, low, close, volume, data_source, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`
  - B2 `SELECT date, high, low, data_source FROM market_data_daily WHERE ticker = :t AND date >= :first AND date <= :last`
  - `MINUTES_SQL` after Task 10: `SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday WHERE ticker = :ticker AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`
- Exact names and strings, copied from the spec: prefix `intraday-bars/v1/1min`; objects `intraday-bars/v1/1min/{T}/{YYYY-MM}.parquet` and `intraday-bars/v1/1min/{T}/manifest.json`; columns `ts, open, high, low, close, volume, data_source`; manifest `{"version": 1, "ticker": T, "months": {"YYYY-MM": {...}}}`; states `as_traded`, `inferred`, `adjusted`, `partial`, `unmeasured`; reasons `no_daily_row`, `daily_from_intraday`, `daily_source_unknown`, `daily_not_positive`, `no_rth_high_low`, `incomplete`, `odd`; variable `INTRADAY_BARS_EXPORT` (`off`, any letter case); flag `--export-bars-from YYYY-MM`; log lines that start `bars export:`, `bars export failed (outage)` and `bars export failed (defect)`.
- Names on `main` that the spec did not have (use these): `place_stored_rows` returns `(instants, keep, proven)`; `session_minute_readings` returns `list[SessionReading]`; `session_basis_verdicts` returns `list[dict]` with keys `session, status, exact, verdict, reason, f_high, f_low, factor` and verdicts spelled `AS-TRADED`, `INFERRED`, `ADJUSTED`, `ODD`, `UNMEASURED`, `INCOMPLETE`; it takes the schedule already cut, so the caller drops sessions whose `market_close` is after now, as `run_verify_basis` does (`gcp/fetchers/fetch_alphavantage_intraday.py:1071-1074`); `BASIS_TICKERS` (`:975`), `_BASIS_DAILY_SQL` (`:982-986`) and `_month_last_day` (`:991`) exist there.
- Choices this plan makes where the spec leaves one open (each is reported to the owner with the plan):
  - The manifest is read once per ticker and each write carries the generation the previous write returned, which gives the spec's counts: 3 reads and 6 writes a night.
  - `factor_min` and `factor_max` range over the sessions counted `as_traded`, `inferred` or `adjusted`; an ODD session is under `not_measured` and outside the range.
  - A month with no row gets its entry through the same code: `file`, `sha256`, `first_ts`, `last_ts` null, every closed session `missing`, state `unmeasured`. An object an earlier export left for it stays in the bucket and is not read.
  - `file` in an entry is the full object name; `read_bars` opens its last path part under `root/TICKER/`. `first_ts`, `last_ts` and `exported_at` are ISO 8601 UTC strings.
  - The Parquet schema is explicit: `ts` `timestamp[us, tz=UTC]`, prices `float64`, `volume` `int64` nullable, `data_source` `string`. `read_bars` returns `volume` as pandas `Int64`.
  - A reader's empty read returns as on `main`, before the `inserted_at` column is touched. `tests/agents/test_on_demand_level_calibration.py:59-60` answers the minutes read with an empty frame that has no such column and passes unmodified (run against a prototype, 2026-11-14).
  - `GCS_BUCKET` unset on a nightly: the export raises `RuntimeError`, which `main()` logs as a defect and exits 1.
  - `--export-bars-from`: a value that is not `YYYY-MM` or is after the current Eastern month, and the flag together with `--symbols-file`, `--start-date` or `--end-date`, are usage errors (exit 2); `CLOUD_RUN_TASK_COUNT` above 1 exits 1 before any query, so N tasks never export the same months at once.
  - `TRUE_DAILY_SOURCES` is not imported by the export: the reason `session_basis_verdicts` returns already carries it.
- Time (CLAUDE.md 3.9): a zone changes only through `lib/eastern_time.py`. `tests/meta/test_timezone_boundaries.py` fails on a new `.tz_localize(None)`, `.replace(tzinfo=None)`, `to_datetime(..., utc=True)`, `date.today()` or `datetime.now()` with no zone, or `DATE(col)` / `ts::date` in SQL text. The export's months come from `market_today()`. Do not reword `date.today()` at `fetch_alphavantage_intraday.py:1179`: the baseline keys on it.
- Capacity (CLAUDE.md Rule 0), the spec's numbers, each tied to a test or a measurement:
  - Volume: nightly, 6 reads of about 20,000 rows of eight columns and 6 files of about 0.6 MB; one-time, at most 143 files and about 85 MB a ticker.
  - Velocity: nightly, 6 bars queries, 3 daily queries, 6 uploads, 3 manifest reads, 6 manifest writes; one-time, 143 bars queries, 1 daily query, 143 uploads, 1 manifest read, 143 manifest writes a ticker. Task 4's I/O-shape test pins both shapes.
  - Wall-clock: nightly estimated under 30 s; one-time estimated about 7 min a ticker; both against the fetch job's 3,600 s task timeout (`gcp/deploy.sh:2218`), the second about 8 times under it. Task 11 measures both locally.
  - Cost: about $0.0007 a nightly run, about 2 cents a month over 26 runs; about 3 cents for the one-time export; under 1 cent a month of storage. No new job, no new schedule.
  - Memory is bounded to one ticker-month (Task 4's test); a rerun converges (Task 4); each ticker-month logs one progress line (Task 4).
- **The render step.** A task that changes a file under `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers (run against a prototype of Tasks 8 to 10: three tests of `tests/scripts/test_check_generated_docs.py` fail until it is run):
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed), then stage whichever of the three docs changed in the same commit as the code. Nothing else in those docs is edited.
- Lessons of #1920 and #1891, binding here:
  1. A generated inventory block is never merged by hand. After any merge of `main`, take either side of a conflict in the three docs, run the render step, and run `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass) before the next commit.
  2. The site snapshot stops verifying whenever `main` moves. The note rows and the snapshot are the last commits before the push, and all four site-note steps of Task 13 are redone after any merge of `main`.
  3. The PR is opened as a draft and stays a draft until the close-out commits are pushed and every done_when line in its body is ticked with evidence. Marking it ready starts the first of only two review rounds.
  4. Every new test has a red-then-green record: its failing output before the code, its passing output after, and the output of one named variant of the code that makes it fail again (each task names its variant; revert the variant before the commit). The three outputs go in the PR body under `Red then green`.
  5. Two tests on `main` depend on test order and are not this work's: `tests/api/test_movement_statement_router.py::test_endpoint_nan_close_does_not_500_and_carries_no_nan` when `tests/api` runs alone, and the fresh-clone tests after `tests/scripts/test_docs_audit.py`. Run the whole suite in its normal order with `make test`, never a hand-picked order of folders.
- Other lanes (2026-11-14). None blocks this plan; the order below avoids a collision.
  - Two-bar-writers (`2026-11-13-feat-data-001-two-bar-writers.md`, approved; its plan is being written on `fix/feat-data-001-two-bar-writers`): edits `gcp/backfill_ticker.py`, `gcp/migrate_to_gcp.py` and `tests/meta/test_production_writers.py`, none of which this plan edits, and declares DASHBOARD-04. If it merges first, merge `main`, run `python3 -m pytest tests/meta/test_production_writers.py -q` on this branch (its writer guard then reads the export module), and extend its DASHBOARD-04 row in Task 13. If this merges first, that lane extends this plan's row.
  - Strict bar reader (`2026-11-13-feat-data-001-strict-bar-loader.md`, approved, no plan on `main`): puts `interval = '1min'` into the `WHERE` text of the `load_intraday_bars` f-string (`gcp/historical_signals.py:314-323`), where Task 9 adds `inserted_at` to the select list, and declares ADMIN-06, CHARTS-06, DASHBOARD-05 and SIGNALS-01. Task 9 does not add the predicate. Whichever lands second keeps the first's edit and extends the four rows.
  - Watched-ticker ingest v3 and its FEAT-DEPLOY-001 wiring: no code file in common. They move the three inventory docs, `03-SITE-TRACEABILITY.md` and the snapshot, so lessons 1 and 2 apply after each of their merges.
  - `scripts/db_query_cr.sh` timeout fit (`2026-11-13-feat-deploy-001-db-query-timeout-fit.md`, approved): once it lands the script refuses a `--timeout` the `db-query` job's 600 s task timeout (`gcp/deploy.sh:2491`) cannot reach. Task 1 already stays under it.
  - Proposed order: two-bar-writers, then this PR, then the strict bar reader. The writers' guard then meets the export module on this branch, before the merge.
- Commits: run `python3 scripts/gate/spec_gate.py --commit` first. Conventional message, imperative, 72 characters or fewer. No AI attribution of any kind: no co-author line, no "generated by", no session link, no emoji.
- Tests go in the files named, one folder per area, never at the `tests/` root. A claim in a doc or on the PR about what the code does comes from output that was run (CLAUDE.md 3.11.1).

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | the month file: placed rows, the two strict queries, failures that leave the manifest as it was | 2, 4 |
| [1] | the manifest: entry, states, create, precondition, write order | 3, 4 |
| [2] | when the export runs: the nightly shape, the log lines, `--export-bars-from` | 6, 7 |
| [3] | `read_bars` and its import isolation | 5 |
| [4] | the three readers by proof, their twins, the stubs | 8, 9, 10 |
| [5] | `make test`, the files left unmodified | 12 |
| [6] | PR-body measurements | 1 (production), 11 (local), posted in 13 |
| [7] | product record, ten site notes, snapshot, inventory, audit, gate | 13 |

## Review Focus

Inputs the spec implies and no done_when test pins. Each has a test in the task that owns the code.

- A month that an earlier export wrote and that holds no row now: its entry says `rows` 0 and `file` null, and `read_bars` returns no row for it though the old object is still beside the manifest. Task 5.
- The manifest write fails after the first-ever upload of a month, so there is no older entry: `read_bars` raises `KeyError` for that month, and `FileNotFoundError` when no manifest exists at all. done_when names only the `ValueError` case, which needs an older entry. Task 5.
- The job is started as `python -m gcp.fetchers.fetch_alphavantage_intraday`, so the export's own import of the fetch module loads it a second time under its package name: an end-to-end run through `runpy` writes one file and exits 0. Task 7.
- `--export-bars-from` with a value that is not a month (`2026-13`, `2026-1`, `202601`), a month after the current Eastern month, `--symbol spy` (accepted as SPY), `--symbol SPY,QQQ` (refused: the spec names one ticker or ALL), and more than one Cloud Run task. Task 7.
- A reader whose bars carry no `inserted_at` inside the calibration job: `calibrate_level_params.run` logs the ticker, lists it in `failed`, writes no row for it and the run exits non-zero (`gcp/calibrate_level_params.py:394-399`), so a defect is never thresholds from misplaced bars. Task 10.
- `_load_1m_bars` and `load_intraday_bars` keep the dtype of `main` on the instants they return (`datetime64[ns, UTC]`) and return no `inserted_at` column, on an empty read as well; the tables downstream are keyed on that index. Tasks 8 and 9.

## File map

| File | Change | Task |
|---|---|---|
| `gcp/fetchers/export_intraday_bars.py` | new: the bucket object, `build_month`, `export_month`, the manifest protocol, `export_window`, `read_bars` | 2, 3, 4, 5 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `main()` exports after the fetch loop; `run_export_bars_from`, `--export-bars-from` | 6, 7 |
| `gcp/research/strat_engine/strat_data_builder.py` | `_load_1m_bars` (`:178-210`) | 8 |
| `gcp/historical_signals.py` | `load_intraday_bars` (`:281-334`) | 9 |
| `gcp/calibrate_level_params.py` | `MINUTES_SQL` (`:83-86`), `read_minutes` (`:250-269`) | 10 |
| `tests/fixtures/intraday_bars_bucket.py` | new: `MemoryBucket` | 2, 4 |
| `tests/gcp/test_export_intraday_bars.py` | new | 2 to 7 |
| `tests/gcp/test_recompute_readers_by_proof.py` | new | 8, 9, 10 |
| `tests/gcp/test_strat_data_builder_gamma.py`, `tests/scripts/test_run_historical_signals_strategy.py`, `tests/gcp/test_calibrate_level_params.py` | the reader stubs gain `inserted_at`; no assertion changes | 8, 9, 10 |
| `tests/gcp/measure_export_intraday_bars.py` | new: the three local measurements | 11 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 2 to 10, 12 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 13 |

## Task 1: Measure the bars query and take the premise count in production

Spec: Capacity; Design H ("The premise, over every ticker"); Close-out ("Before the merge"). Advances done_when[6] (production half). Needs: nothing. Read-only, no `--commit`. Run it before any code: a plan that reads more rows than it returns means Design E is wrong, and a premise count that returns a row means the PR does not merge.

- [ ] Run the plan of B1 for SPY 2025-05, with literals where the code binds:

```bash
env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "EXPLAIN (ANALYZE, BUFFERS) SELECT ts, open, high, low, close, volume, data_source, inserted_at FROM market_data_intraday WHERE ticker = 'SPY' AND interval = '1min' AND ts >= TIMESTAMPTZ '2025-05-01 02:00:00+00' AND ts < TIMESTAMPTZ '2025-06-01 02:00:00+00' ORDER BY ts"
```

- [ ] Pass means: every scan node's actual `rows=` equals the rows the statement returns, with no `Rows Removed by Filter` above 0 and no `Seq Scan`, on one partition, `market_data_intraday_spy`. On a fail, stop and report to the owner; do not start Task 2.
- [ ] Run the premise count, the spec's statement word for word, over every ticker:

```bash
env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh --timeout 420 -q "SELECT ticker, count(*) AS label_rows, min(ts) AS first_ts, max(ts) AS last_ts FROM market_data_intraday WHERE interval = '1min' AND inserted_at >= TIMESTAMPTZ '2026-09-28 00:00+00' AND ts < TIMESTAMPTZ '2026-09-28 00:00+00' AND (ts AT TIME ZONE 'UTC')::time >= TIME '04:00' AND ts < ((ts AT TIME ZONE 'UTC')::date + TIME '04:00') AT TIME ZONE 'America/New_York' GROUP BY ticker ORDER BY ticker"
```

  The spec says `--timeout 600`; the `db-query` job's task timeout is 600 s (`gcp/deploy.sh:2491`), so a 600 s statement cannot report. 420 s leaves the 180 s the script itself allows for the rest of the run (`scripts/db_query_cr.sh:64`). If the statement is cancelled at 420 s, run it once per partition instead, one dispatch each, with `FROM market_data_intraday_spy`, `_qqq`, `_iwm`, `_spx` and `_other` in place of the parent: the five results together are the count.
- [ ] Pass means: no row. A row is a label written since 2026-09-28: stop, post the rows on the PR for the owner, and the PR does not merge (spec, Close-out).
- [ ] Save the plan, its execution time, the count's result and every execution id the script prints. They go on the PR in Task 13.

## Task 2: The bucket object and the month file

Spec: Design E ("Where", "A month", "What the export reads", "The instant written for each row", "Format", "The bucket"). Advances done_when[0]. Needs: nothing.

**Files:** Create `gcp/fetchers/export_intraday_bars.py`, `tests/fixtures/intraday_bars_bucket.py`, `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:** Consumes `lib.eastern_time.intraday_month_window`, `place_stored_rows`; the builders of `tests/fixtures/intraday_checks.py` (`session_bars`, `stored`, `OLD`, `NEW`). Produces, all new, in the export module:
- `PREFIX = "intraday-bars/v1/1min"`, `EXPORT_TICKERS = ("SPY", "QQQ", "IWM")`, `COLUMNS = ("ts", "open", "high", "low", "close", "volume", "data_source")`, `BARS_SQL` (B1), `DAILY_SQL` (B2).
- `object_name(ticker: str, year: int, month: int) -> str` and `manifest_name(ticker: str) -> str`.
- `class GenerationMismatch(Exception)`.
- The bucket protocol, two methods: `read(name: str) -> tuple[bytes, int] | None` (the bytes and the generation; `None` only when the object is absent; any other failure raises) and `write(name: str, data: bytes, if_generation_match: int | None = None) -> int` (the new generation; raises `GenerationMismatch` when the precondition fails).
- `class GcsBucket` with `__init__(self, bucket: str)` and those two methods: `read` catches `google.api_core.exceptions.NotFound` and nothing else; `write` uses `upload_from_string(data, if_generation_match=...)` and turns `PreconditionFailed` into `GenerationMismatch`.
- `bucket_from_env() -> GcsBucket`: `GCS_BUCKET` with a leading `gs://` dropped; unset or empty raises `RuntimeError` whose message names `GCS_BUCKET`.
- `build_month(rows: pd.DataFrame, daily: pd.DataFrame, ticker: str, year: int, month: int, now_utc: datetime) -> tuple[bytes | None, dict]`: pure. The Parquet bytes (`None` when `rows` is empty) and the manifest entry. This task builds the bytes and the entry keys `file`, `rows`, `stored_rows`, `dropped_rows`, `inferred_rows`, `first_ts`, `last_ts`, `sha256`, `exported_at`; Task 3 adds `sessions` and `basis`.
- `export_month(bucket, ticker: str, year: int, month: int, daily: pd.DataFrame, now_utc: datetime) -> dict`: one B1 read over `intraday_month_window(year, month)`, `build_month`, one `bucket.write(object_name(...), data)` when there are bytes, returns the entry. It does not touch the manifest.

Produces, in `tests/fixtures/intraday_bars_bucket.py`: `class MemoryBucket` with the same two methods and GCS's rule (a generation counter per object; `if_generation_match=0` succeeds only when the object is absent; a mismatch raises `GenerationMismatch`), the lists `reads` and `writes` of object names in call order, a dict `objects`, and two hooks: `fail_write: Callable[[str], Exception | None]` and `before_write: Callable[[str], None]` (called before the precondition is checked, so a test can let "another run" write first).

What the file holds, which the signature does not determine. `instants, keep, proven = place_stored_rows(rows["ts"], rows["volume"], rows["inserted_at"])`, once over the whole month. The file is the kept rows with `ts` replaced by their instant, sorted by `ts`, the seven columns in `COLUMNS` order, written with an explicit pyarrow schema (Global Constraints) and `compression="zstd"`. `rows` is the count kept, `dropped_rows` the count not kept, `inferred_rows` the count kept and not proven, `sha256` the hex digest of the bytes.

- [ ] Write in `tests/gcp/test_export_intraday_bars.py`, with `NOW = datetime(2026, 11, 13, 15, tzinfo=timezone.utc)`, a helper `month_rows(year, month, how="true", shared="true", inserted=OLD, **kw)` that concatenates `stored(session_bars(d, **kw), how, shared=shared, inserted=inserted)` for each session `d` of the month and adds `open` (the midpoint), `close` (the midpoint) and `data_source` `"alphavantage"`, a helper `expected_table(year, month, **kw)` that builds the same bars at `eastern_index_to_utc(bar)` without calling `place_stored_rows`, a helper `read_file(data: bytes) -> pd.DataFrame` over `pyarrow.parquet.read_table`, and a helper `fake_query(bars, daily)` that patches `gcp.database.query_to_dataframe_strict` with a recording fake (SQL holding `market_data_daily` answers `daily[params["t"]]`; other SQL answers `bars[(params["t"], params["start"].year, params["start"].month)]`; an `Exception` in place of a frame is raised) and returns the list of calls:
  - `test_month_file_holds_each_bar_on_its_own_minute`, parametrized over `("true", "true")`, `("label", "true")` for SPY 2025-05 (21 sessions of 961 bars): the file's rows equal `expected_table(2025, 5)` exactly (20,181 rows, the seven columns in order, `ts` ascending with dtype `timestamp[us, tz=UTC]` in the file's schema), `rows == stored_rows == 20181`, `dropped_rows == 0`, `inferred_rows == 20181`; with `inserted=NEW`, `inferred_rows == 0`.
  - `test_a_month_stored_both_ways_with_different_prices`: the true copy as above, plus for each session the label copy built with `day_high=610.0, day_low=600.0`, less the label rows whose `ts` the true copy holds (the table's key allows one row per `ts`): 1,201 stored rows a session. The file equals `expected_table(2025, 5)`, its highest `high` is 600.0, and per session `rows == 961`, `dropped_rows == 240`; over the month `rows + dropped_rows == stored_rows == 25221` (run through `place_stored_rows` on `main`, 2026-11-14: 961 kept and 240 dropped for one such session).
  - `test_a_flat_session_stored_both_ways_is_written_as_placed`: one session, `stored(session_bars("2025-05-01", spike=False), "both", shared="label")`, `OLD`: the file's `ts` and values equal what `place_stored_rows` returns for the same frame (the test calls it), `rows == 961`, `inferred_rows == 961` (the named limit: nothing but `inferred_rows` flags it).
  - `test_the_last_bar_of_a_month_is_in_that_months_file`: SPY 2025-06 and 2025-07 stored as true UTC; the row at `2025-07-01 00:00 UTC` (the 20:00 ET bar of 2025-06-30) is handed to the fake for the June window. `export_month` for June writes a file whose last `ts` is `2025-07-01 00:00:00+00:00`; the July file's first `ts` is `2025-07-01 08:00:00+00:00`; the two B1 calls are bounded by `intraday_month_window(2025, 6)` and `(2025, 7)`.
  - `test_export_month_reads_one_strict_query_and_overwrites`: one call; its SQL equals B1 once whitespace is collapsed and holds `interval = '1min'`; `params == {"t": "SPY", "start": datetime(2025, 5, 1, 2, tzinfo=timezone.utc), "end": datetime(2025, 6, 1, 2, tzinfo=timezone.utc)}`; `timeout_s == 120`. A second `export_month` after one row's `close` changed writes the same object name again (`bucket.writes` holds it twice) and the stored bytes are the new ones.
  - `test_null_price_and_volume_stay_null`: one row with `open` NaN and one with `volume` NA: both are null in the file (`read_table(...).column("open").null_count == 1`, the same for `volume`), and the `volume` field's type is `int64`.
  - `test_object_names`: `object_name("SPY", 2025, 5) == "intraday-bars/v1/1min/SPY/2025-05.parquet"`, `manifest_name("SPY") == "intraday-bars/v1/1min/SPY/manifest.json"`, `EXPORT_TICKERS == fai.BASIS_TICKERS`, and `" ".join(DAILY_SQL.split()) == " ".join(fai._BASIS_DAILY_SQL.split())`.
  - `test_bucket_from_env`: `GCS_BUCKET=gs://b` and `GCS_BUCKET=b` both give a bucket named `b` (with `google.cloud.storage.Client` patched); unset raises `RuntimeError` matching `GCS_BUCKET`.
  - `test_gcs_bucket_absent_is_an_answer_and_any_other_failure_raises`: with a fake client whose blob raises `NotFound` on download, `read` returns `None`; raising `Forbidden`, `read` raises it; `write(..., if_generation_match=0)` passes `if_generation_match=0` to `upload_from_string`, and a `PreconditionFailed` from it surfaces as `GenerationMismatch`.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect FAIL: no module `gcp.fetchers.export_intraday_bars`).
- [ ] Implement the names above.
- [ ] Run the file again (expect all pass), then `python3 -m pytest tests/meta/test_timezone_boundaries.py tests/meta/test_production_writers.py -q` (expect all pass).
- [ ] Variant: write `rows["ts"]` in place of the placed instants. `test_month_file_holds_each_bar_on_its_own_minute[label-true]` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `feat(data): write a month of 1-min bars as a Parquet file`

## Task 3: The manifest entry

Spec: Design E ("Manifest", the reasons, the state order). Advances done_when[1] (the entry). Needs: Task 2.

**Files:** Modify `gcp/fetchers/export_intraday_bars.py` (`build_month`), `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:** Consumes `lib.eastern_time.session_schedule`, and `session_basis_verdicts` from the fetch module, imported inside `build_month`. Produces: the two remaining keys of the entry.
- `sessions`: `{"expected", "ok", "thin", "missing", "undetermined"}`. The schedule is `session_schedule(first day, last day)` of the month, less every session whose `market_close` is after `now_utc`; `expected` is its length and the other four count the records' `status`.
- `basis`: `{"state", "factor_min", "factor_max", "as_traded", "inferred", "adjusted", "odd", "not_measured"}`. The four counts are of the verdicts `AS-TRADED`, `INFERRED`, `ADJUSTED` and `ODD`. `not_measured` maps the session's ISO date to: the record's `reason` for `UNMEASURED`, `"incomplete"` for `INCOMPLETE`, `"odd"` for `ODD`. `state` is the first that applies of `adjusted` (an ADJUSTED session), `inferred` (an INFERRED session), `unmeasured` (no session counted as traded, inferred or adjusted), `as_traded` (`not_measured` is empty), `partial`.

- [ ] Write, with `daily_rows(year, month, src="alphavantage_daily", skip=(), stamp=None)` giving one row of 600.0 and 590.0 per session (`skip` leaves dates out, `stamp` maps a date to another `data_source`) and `entry(rows, daily, y=2025, m=5, now=NOW)` returning `build_month(rows, daily, "SPY", y, m, now)[1]`:
  - `test_entry_keys_and_counts`: SPY 2025-05, `NEW`, as traded: the entry's keys are exactly the eleven of the spec; `rows + dropped_rows == stored_rows`; `file == "intraday-bars/v1/1min/SPY/2025-05.parquet"`; `sha256 == hashlib.sha256(data).hexdigest()`; `first_ts == "2025-05-01T08:00:00+00:00"`; `last_ts == "2025-05-31T00:00:00+00:00"`; `exported_at == NOW.isoformat()`; `sessions == {"expected": 21, "ok": 21, "thin": 0, "missing": 0, "undetermined": 0}`; `basis == {"state": "as_traded", "factor_min": 1.0, "factor_max": 1.0, "as_traded": 21, "inferred": 0, "adjusted": 0, "odd": 0, "not_measured": {}}`.
  - `test_one_unproven_row_makes_the_month_inferred`: the same month with the `inserted_at` of the 2025-05-16 10:00 ET bar set to `OLD`: `state == "inferred"`, `as_traded == 20`, `inferred == 1`, `inferred_rows == 1`.
  - `test_not_measured_reasons_and_partial`: `NEW`, as traded except 2025-05-12 holding only 09:30 to 13:29 and 2025-05-13 with `f_low=0.99`; the daily frame lacks 2025-05-14 and stamps 2025-05-15 `alphavantage_1min` and 2025-05-19 `yahoo`: `not_measured == {"2025-05-12": "incomplete", "2025-05-13": "odd", "2025-05-14": "no_daily_row", "2025-05-15": "daily_from_intraday", "2025-05-19": "daily_source_unknown"}`, `state == "partial"`, `as_traded == 16`, `odd == 1`, `sessions["thin"] == 1`. Each of these months, taken alone, is never `as_traded`: one parametrized case per reason, with `daily_not_positive` (a daily low of 0.0) and `no_rth_high_low` (every `high` NaN on one session) added.
  - `test_adjusted_wins_and_carries_the_range`: one session at `f_high=f_low=0.99430`, one row elsewhere `OLD`: `state == "adjusted"`, `adjusted == 1`, `factor_min == 0.9943`, `factor_max == 1.0`.
  - `test_unmeasured_has_null_factors`: every daily row stamped `alphavantage_1min`: `state == "unmeasured"`, `factor_min is None`, `factor_max is None`, 21 dates under `not_measured`.
  - `test_a_month_with_no_row`: an empty frame with B1's eight columns: the bytes are `None`; `rows == stored_rows == dropped_rows == inferred_rows == 0`; `file`, `sha256`, `first_ts`, `last_ts` are `None`; `sessions == {"expected": 21, "ok": 0, "thin": 0, "missing": 21, "undetermined": 0}`; `state == "unmeasured"`.
  - `test_the_newest_session_has_no_daily_row_yet`: SPY 2026-11 with whole as-traded sessions to 2026-11-12, daily rows to 2026-11-11, `now` `datetime(2026, 11, 13, 2, tzinfo=timezone.utc)` (21:00 ET on 2026-11-12): `sessions["expected"] == 9`, `not_measured == {"2026-11-12": "no_daily_row"}`, `state == "partial"`, `inferred_rows == 0`.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect the new tests FAIL with `KeyError: 'sessions'`).
- [ ] Implement.
- [ ] Run the file again (expect all pass).
- [ ] Variant: test `as_traded` before `inferred` in the state order. `test_one_unproven_row_makes_the_month_inferred` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `feat(data): say how whole and on what basis an exported month is`

## Task 4: The manifest protocol and `export_window`

Spec: Design E ("Writes", "What a failure between two writes leaves", "What a run logs"); What bad input gets (export rows); Capacity. Advances done_when[0] (failures), done_when[1] (create, precondition, order). Needs: Tasks 2 and 3.

**Files:** Modify `gcp/fetchers/export_intraday_bars.py`, `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:** Produces, new:
- `MANIFEST_VERSION = 1`, `MANIFEST_RETRIES = 5`.
- `read_manifest(bucket, ticker: str) -> tuple[dict, int]`: the document and its generation; an absent object gives `({"version": 1, "ticker": ticker, "months": {}}, 0)`; bytes that are not JSON, a `version` that is not 1 or a `ticker` that is not this one raise `ValueError`; any other read failure propagates.
- `write_month_entry(bucket, ticker: str, month_key: str, entry: dict, doc: dict, generation: int) -> tuple[dict, int]`: puts the entry into `doc`, writes with `if_generation_match=generation`; on `GenerationMismatch` calls `read_manifest` again, puts the entry into that copy and retries, at most `MANIFEST_RETRIES` times after the first attempt, then lets `GenerationMismatch` out. Returns the document and generation now stored.
- `months_between(first: tuple[int, int], last: tuple[int, int]) -> list[tuple[int, int]]` (both ends included; empty when `first` is after `last`) and `nightly_months(today: date) -> list[tuple[int, int]]` (the month before `today`'s and `today`'s).
- `export_window(tickers: Sequence[str], months: Sequence[tuple[int, int]], *, bucket=None, now_utc: datetime | None = None) -> dict`: returns `{"months": int, "rows": int, "seconds": float}`. `bucket` defaults to `bucket_from_env()`, `now_utc` to `lib.eastern_time.utc_now()`.

The order inside `export_window`, which the tests pin. Per ticker: one B2 read over the first day of the earliest month to the last day of the latest; then `read_manifest`; then per month, in order: `export_month`, then `write_month_entry`, then one INFO line `bars month: {T} {YYYY-MM} rows={N} stored={N} dropped={N} inferred={N} state={S} ({i}/{n})`. The prefix is not `bars export:`: done_when[2] wants exactly one line with that start, the summary `main()` logs. The month's frame is not referenced after its entry is built. Nothing is caught.

- [ ] Write, with `bucket = MemoryBucket()` and a helper `run(tickers, months, bars, daily, bucket, now=NOW)` that installs `fake_query` and calls `export_window`:
  - `test_first_export_creates_the_manifest`: on an empty bucket, SPY 2025-05: the manifest write carried `if_generation_match=0`; the stored document is `{"version": 1, "ticker": "SPY", "months": {"2025-05": <entry>}}`.
  - `test_a_manifest_another_run_created_in_between_is_kept`: `before_write` puts a manifest holding a `2024-01` entry the first time the manifest name is written: the stored document holds both `2024-01` and `2025-05`, and `bucket.writes` shows two attempts on the manifest.
  - `test_an_entry_another_run_wrote_in_between_is_kept`: the bucket starts with a manifest holding `2025-04`; `before_write` adds `2025-03` once: the stored document holds `2025-03`, `2025-04` and `2025-05`.
  - `test_six_mismatches_raise`: `before_write` rewrites the manifest every time: `GenerationMismatch` after exactly 6 attempts.
  - `test_a_failed_manifest_read_writes_nothing`: `bucket.read` raising `PermissionError` for the manifest name: `export_window` raises it and `bucket.writes == []`.
  - `test_a_bad_manifest_is_never_replaced`, parametrized over `b"{"`, `b'{"version": 2, "ticker": "SPY", "months": {}}'`: `ValueError`, and the object's bytes are unchanged.
  - `test_second_month_upload_failure_leaves_the_first_month_whole`: the bucket holds an earlier export of 2025-05 and 2025-06; a rerun over both with new rows, `fail_write` raising `ConnectionError` on the June object: `ConnectionError` propagates; the May object's sha256 equals its manifest entry's; the June object and the June entry are byte for byte what they were.
  - `test_failures_leave_the_manifest_as_it_was`, parametrized: the bars query raising `ConnectionError("connection refused")`; the daily query raising `KeyError("high")`; an upload raising `ConnectionError`; an upload raising `PermissionError`. Each propagates as itself and the manifest object's bytes equal those before the run.
  - `test_manifest_write_failure_after_an_upload`: `fail_write` raising `ConnectionError` on the manifest name: the month's object is the new file and its entry still describes the old one (the two sha256 differ).
  - `test_io_shape` (Rule 0): the nightly shape, `EXPORT_TICKERS` over `[(2026, 9), (2026, 10)]` on an empty bucket: exactly 6 B1 calls and 3 B2 calls, every one with `timeout_s == 120`; `bucket.reads` holds each manifest name once (3); `bucket.writes` holds 6 month objects and 6 manifest writes, each month's object before its manifest write. The history shape, SPY over `months_between((2025, 1), (2025, 12))`: 12 B1 calls, 1 B2 call whose `params` are `{"t": "SPY", "first": date(2025, 1, 1), "last": date(2025, 12, 31)}`, 1 manifest read, 12 and 12 writes. The return value's `months` is 6 and 12 and `rows` the sum of the entries' `rows`.
  - `test_one_month_in_memory_at_a_time` (Rule 0): the fake keeps a `weakref` to each B1 frame it returns and, on each later B1 call, runs `gc.collect()` and asserts every earlier frame's reference is dead.
  - `test_a_rerun_converges` (Rule 0): two runs over the same rows, the second with a later `now`: each object's bytes are equal across the runs, each entry is equal apart from `exported_at`, and the manifest holds the same month keys once.
  - `test_each_month_logs_its_progress` (Rule 0, `caplog` at INFO): six lines start `bars month: `, the first holds `SPY 2026-09` and `(1/6)`, the last `(6/6)`, and no line starts `bars export:`.
  - `test_months_between_and_nightly_months`: `months_between((2025, 11), (2026, 2)) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]`; `months_between((2026, 2), (2026, 1)) == []`; `nightly_months(date(2026, 10, 31)) == [(2026, 9), (2026, 10)]`; `nightly_months(date(2026, 1, 5)) == [(2025, 12), (2026, 1)]`.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect the new tests FAIL: the module has no `export_window`).
- [ ] Implement.
- [ ] Run the file again (expect all pass).
- [ ] Variant: write the manifest once per ticker, after its last month. `test_second_month_upload_failure_leaves_the_first_month_whole` and `test_io_shape` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `feat(data): write each month's manifest entry under a precondition`

## Task 5: `read_bars`, and nothing else reads the copy

Spec: Design E ("How a session reads it"); Non-goals (the copy is not a replay source). Advances done_when[3]. Needs: Task 4.

**Files:** Modify `gcp/fetchers/export_intraday_bars.py`, `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:** Produces `read_bars(root, ticker: str, first_month: str, last_month: str) -> tuple[pd.DataFrame, list[dict]]`. `root` is a local directory that holds `TICKER/manifest.json` and the month files beside it (what `gcloud storage cp -r .../intraday-bars/v1/1min/SPY ./bars/` leaves). `bars` has the seven columns, `ts` as UTC datetimes ascending, a fresh integer index, `volume` as `Int64`. `months` has one dict per requested month in order: the manifest entry plus `"month"`.

Raises, in this order of checks: `ValueError` when `first_month` is after `last_month`; `FileNotFoundError` when the manifest is absent; `ValueError` when its `version` is not 1; `KeyError` naming the month when a requested month has no entry; for an entry whose `file` is not null, `FileNotFoundError` when the file is absent and `ValueError` naming the month when the file's sha256 is not the entry's. An entry with `file` null adds no rows and opens nothing.

- [ ] Write, with a helper `to_disk(bucket, tmp_path)` that writes every object of a `MemoryBucket` under `tmp_path` with the `PREFIX` part of its name removed:
  - `test_read_bars_returns_the_exported_rows_and_entries`: after an export of SPY 2025-05 and 2025-06, `read_bars(tmp_path, "SPY", "2025-05", "2025-06")` returns `bars` equal to the two files' rows in order (the seven columns, `ts` tz-aware UTC and increasing, index `0..n-1`) and `months` whose `"month"` values are `["2025-05", "2025-06"]`, each equal to its manifest entry plus that key; `read_bars(..., "2025-06", "2025-06")` returns June only.
  - `test_read_bars_errors`, parametrized: no manifest: `FileNotFoundError`; a month's file deleted: `FileNotFoundError`; a month with no entry: `KeyError`; a month's file replaced by another valid Parquet file: `ValueError` whose message holds `2025-05`; manifest `version` 2: `ValueError`; `first_month` `2025-06` with `last_month` `2025-05`: `ValueError`.
  - `test_read_bars_does_not_refuse_a_month_for_its_state`, parametrized over months built to be `inferred`, `adjusted`, `partial` and `unmeasured` (Task 3's inputs): each is returned, and `months[0]["basis"]["state"]` is that state.
  - `test_a_month_with_rows_0_returns_no_row`: an exported empty month: no rows, `months[0]["rows"] == 0`, no raise. And the Review Focus case: the same month with an older object left beside the manifest and the entry now saying `file` null: still no rows.
  - `test_after_a_failed_run_read_bars_tells_the_months_apart`: on Task 4's second-upload failure, `read_bars` for May returns its rows; on Task 4's manifest-write failure with an older entry, `read_bars` raises `ValueError` naming the month; with no older entry (the month's first export), `KeyError` (Review Focus).
  - `test_read_bars_needs_only_pandas_and_pyarrow`: a subprocess (`sys.executable -c`) installs a `sys.meta_path` finder that raises `ImportError` for `gcp.database`, `lib`, `sqlalchemy`, `google`, `requests` and `pandas_market_calendars` and any submodule of them, imports `gcp.fetchers.export_intraday_bars`, calls `read_bars` on the directory written above and prints the row count; the test asserts exit 0 and the count.
  - `test_nothing_in_the_tree_reads_the_copy` (CLAUDE.md 3.7.1): over every `.py` file under `gcp/`, `lib/`, `scripts/` and `platform/`, by `ast`: the only file that imports `export_intraday_bars` (an `import`, a `from ... import`, or a string constant holding the module's name) is `gcp/fetchers/fetch_alphavantage_intraday.py`; no file but the export module holds the name `read_bars` or a string constant that contains `intraday-bars/`; and the fetch module does not hold the name `read_bars`. The same check, run on snippets, rejects `from gcp.fetchers.export_intraday_bars import read_bars`, `importlib.import_module("gcp.fetchers.export_intraday_bars")` and `f"gs://{b}/intraday-bars/v1/1min/{t}"`, and accepts a docstring that names the module. A comment in the test says what it cannot see: a module name built at run time.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect the new tests FAIL: the module has no `read_bars`; the tree test passes before Task 6 and is red-checked by its snippets).
- [ ] Implement `read_bars`. pyarrow is imported inside it.
- [ ] Run the file again (expect all pass).
- [ ] Variant: skip the sha256 comparison. `test_read_bars_errors` (the replaced file) must fail. Revert. Second variant: add `from lib.eastern_time import utc_now` at the module's top. `test_read_bars_needs_only_pandas_and_pyarrow` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `feat(data): read exported bars back and refuse a file by its hash`

## Task 6: The nightly run exports after its fetch

Spec: Design E ("Which runs export", "Which months", "What a run logs", "A failed export"). Advances done_when[2] (the nightly half). Needs: Task 4.

**Files:** Modify `gcp/fetchers/fetch_alphavantage_intraday.py` (the `lib.eastern_time` import, `:26-35`; `main`, `:1212-1276`), `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:** Consumes `export_window`, `nightly_months`, `EXPORT_TICKERS`, `lib.eastern_time.market_today`, `lib.infra_errors.is_infrastructure_error`. Produces, new, in the fetch module:
- `_run_bars_export(tickers: Sequence[str], months: Sequence[tuple[int, int]]) -> bool`: calls `export_window`; on success logs `bars export: {N} months, {N} rows, {N.N} s` and returns True; on any `Exception` logs, with `exc_info=True`, `bars export failed (outage): {exc}` when `is_infrastructure_error(exc)` and `bars export failed (defect): {exc}` otherwise, and returns False. This is the one `except` the plan adds; it never returns success for a failure.

Where it goes in `main()`. The decision is taken after the run summary and the dead-ticker block (`:1254-1271`) and before the systemic exit (`:1272`), so the export also runs when a ticker failed. It runs when all hold: `args.symbol == 'ALL'` and no `args.symbols_file`; `args.force`; neither `args.start_date` nor `args.end_date`; `task_cnt == 1`; `is_cloud_sql_configured()`; `INTRADAY_BARS_EXPORT` is not `off` in any letter case. When only the variable stops it, one INFO line names `INTRADAY_BARS_EXPORT`. When only the database stops it, one INFO line says so and no query is issued. The months are `nightly_months(market_today())`. `main()` exits 1 when a ticker failed or `_run_bars_export` returned False.

- [ ] Write, with a helper `nightly(monkeypatch, argv, *, configured=True, export=None, process=None, env=None)` that patches `fai.get_api_keys` to `["k"]`, `fai.resolve_all_symbols` to `["SPY", "QQQ", "IWM"]`, `fai.process_symbol` (default: returns `fai.OUTCOME_OK`), `fai.is_cloud_sql_configured`, `fai.market_today` to `date(2026, 10, 31)`, `export_intraday_bars.export_window` with a recorder (default: returns `{"months": 6, "rows": 123456, "seconds": 4.2}`; an `Exception` given as `export` is raised), deletes `CLOUD_RUN_TASK_COUNT` and `INTRADAY_BARS_EXPORT` unless `env` sets them, sets `sys.argv`, runs `fai.main()` and returns `(exit code, the recorder's calls)`:
  - `test_the_nightly_arguments_export_two_eastern_months`: argv `--symbol=ALL --force`: one call, `tickers == ("SPY", "QQQ", "IWM")`, `months == [(2026, 9), (2026, 10)]`, exit 0. And the clock the spec names: `datetime(2026, 11, 1, 1, tzinfo=timezone.utc).astimezone(ET).date() == date(2026, 10, 31)`, while `nightly_months(date(2026, 11, 1)) == [(2026, 10), (2026, 11)]`, the months a UTC date would have given.
  - `test_other_argument_shapes_export_nothing`, parametrized: `--symbol=ALL` (no `--force`); `--symbol=ALL --force --start-date 2026-10-01`; `--symbol=ALL --force --end-date 2026-10-31`; `--symbols-file <a file holding SPY> --force`; `--symbol SPY --force`; `--symbol=ALL --force` with `CLOUD_RUN_TASK_COUNT=4`: zero calls.
  - `test_the_variable_turns_it_off` (`caplog`), parametrized over `off`, `OFF`, `Off`: zero calls and exactly one record whose message holds `INTRADAY_BARS_EXPORT`.
  - `test_database_not_configured_exports_nothing_and_asks_nothing`: `configured=False`, with `gcp.database.query_to_dataframe_strict` patched to raise `AssertionError`: zero calls, exit 0.
  - `test_gcs_bucket_unset_is_a_failed_export`: with the real `export_window`, `GCS_BUCKET` unset and `gcp.database.query_to_dataframe_strict` patched to raise `AssertionError`: exit 1 and a record that starts `bars export failed (defect)` and holds `GCS_BUCKET`.
  - `test_success_logs_one_line` (`caplog`): one record starts `bars export:` and holds `6 months`, `123456 rows` and `4.2 s`.
  - `test_a_failed_export_logs_its_kind_after_the_fetch_summary_and_exits_1`, parametrized: `ConnectionError("connection refused")` gives a record that starts `bars export failed (outage)`; `KeyError("high")` one that starts `bars export failed (defect)`; in both the record comes after the one that starts `Run summary:`, and the exit is 1.
  - `test_the_export_runs_when_a_ticker_failed`: `process` raising for QQQ: one export call, exit 1.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect the new tests FAIL: `fai` has no `market_today`).
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py tests/gcp/test_av_intraday_universe.py tests/gcp/test_intraday_as_traded.py tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_verify_basis.py tests/meta -q` (expect all pass; `test_av_intraday_universe.py` holds 4 tests and none changes: its `main()` runs with the database not configured).
- [ ] Variant: take the months from `date.today()`. `tests/meta/test_timezone_boundaries.py` must fail on a new `host-today` hit in `main`. Revert. Second variant: drop the `task_cnt == 1` condition. `test_other_argument_shapes_export_nothing` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `feat(data): export the bars after the nightly fetch`

## Task 7: `--export-bars-from`

Spec: Design E ("One-time history"). Advances done_when[2] (the history half). Needs: Task 6.

**Files:** Modify `gcp/fetchers/fetch_alphavantage_intraday.py` (`main`, `:1123-1176`; one new function above it), `tests/gcp/test_export_intraday_bars.py`.

**Interfaces:** Produces (new) `run_export_bars_from(first: tuple[int, int], symbol: str) -> int`, the exit code. In order: more than one Cloud Run task returns 1 with a logged error; `symbol`, stripped and upper-cased, is `ALL` (the three tickers) or one of `EXPORT_TICKERS`, else 1 with a logged error; the database not configured returns 1; `GCS_BUCKET` unset or empty returns 1; all four before any query. Then `months_between(first, the month of market_today())` and `_run_bars_export`; 0 when it returned True, else 1. It fetches nothing and needs no API key.

In `main()`: add `--export-bars-from` (metavar `YYYY-MM`; help says it writes every month from the one given to the current Eastern month for SPY, QQQ and IWM or the one named by `--symbol`, fetches nothing, and gives `--args="--export-bars-from=2015-01,--symbol=SPY"`). Add it to `list_modes` (`:1165-1168`), so two of the four are the existing `parser.error`. With `parser.error`: a value `re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", ...)` refuses; a month after the current Eastern month; the flag with `--symbols-file`, `--start-date` or `--end-date`. Dispatch beside the other three, before `get_api_keys()` (`:1184`).

- [ ] Write, with a helper `history(monkeypatch, argv, *, configured=True, bucket="b", export=None)` built as Task 6's, with `fai.get_api_keys` patched to fail the test when called and `GCS_BUCKET` set or deleted:
  - `test_export_bars_from_writes_every_month_to_the_current_one`: `--export-bars-from 2026-08` (`market_today` 2026-10-31): one call, the three tickers, `months == [(2026, 8), (2026, 9), (2026, 10)]`, exit 0, `process_symbol` never called. With `--symbol SPY`: `tickers == ("SPY",)`. With `--symbol spy`: the same (Review Focus).
  - `test_another_ticker_exits_1_before_any_query`, parametrized over `AMD` and `SPY,QQQ`: exit 1, zero calls, with `gcp.database.query_to_dataframe_strict` patched to raise `AssertionError`.
  - `test_not_configured_exits_1`, parametrized over the database not configured and `GCS_BUCKET` deleted: exit 1, zero calls.
  - `test_more_than_one_task_exits_1` (Review Focus): `CLOUD_RUN_TASK_COUNT=4`: exit 1, zero calls.
  - `test_export_bars_from_usage_errors`, parametrized: with `--replace-months x`, `--verify-months x`, `--verify-basis x`, `--symbols-file f`, `--start-date 2026-10-01`, `--end-date 2026-10-31`; the values `2026-13`, `2026-1`, `202601` and `2026-11` (after the current Eastern month): `SystemExit` with code 2, zero calls.
  - `test_a_failed_history_export_exits_1`: `export` raising `ConnectionError`: exit 1 and a record that starts `bars export failed (outage)`.
  - `test_the_module_run_as_main_exports_end_to_end` (Review Focus): a subprocess runs a script that patches `gcp.database.is_cloud_sql_configured` to True and `gcp.database.query_to_dataframe_strict` to answer B1 with one stored session of 2026-10-01 and B2 with its daily row, replaces `gcp.fetchers.export_intraday_bars.bucket_from_env` with a function returning one `MemoryBucket`, sets `GCS_BUCKET=b` and `sys.argv` to `--export-bars-from=2026-10 --symbol=SPY`, patches `lib.eastern_time.market_today` to `date(2026, 10, 31)`, calls `runpy.run_module("gcp.fetchers.fetch_alphavantage_intraday", run_name="__main__")` and prints the bucket's object names: exit 0, and the names are the October object and the manifest.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py -q` (expect the new tests FAIL: `main()` exits 2 on an unrecognized argument).
- [ ] Implement.
- [ ] Run: `python3 -m pytest tests/gcp/test_export_intraday_bars.py tests/gcp/test_intraday_verify_basis.py tests/gcp/test_intraday_replace_months.py tests/meta -q` (expect all pass).
- [ ] Variant: dispatch after `get_api_keys()`. `test_export_bars_from_writes_every_month_to_the_current_one` must fail (the patched `get_api_keys` fails it). Revert.
- [ ] The render step.
- [ ] Commit: `feat(data): write the bar history to the bucket on demand`

## Task 8: `_load_1m_bars` places rows by proof

Spec: Design H ("What changes", "What a reader then returns"). Advances done_when[4]. Needs: nothing (independent of Tasks 2 to 7).

**Files:** Modify `gcp/research/strat_engine/strat_data_builder.py` (the import at `:62-64`, `_load_1m_bars` at `:178-210`), `tests/gcp/test_strat_data_builder_gamma.py` (the stub rows at `:153-155`). Create `tests/gcp/test_recompute_readers_by_proof.py`.

**Interfaces:** Consumes `lib.eastern_time.place_stored_rows`, `utc_to_eastern_naive`. `_load_1m_bars(engine, ticker: str, start_date: str) -> pd.DataFrame` keeps its signature and its return: index `ts`, aware UTC, `datetime64[ns, UTC]`, sorted; columns `open, high, low, close, volume` and no other.

Produces, in the new test file, the accepted-thin fixture every reader test uses: `PROVEN = pd.Timestamp("2026-11-20 03:00", tz="UTC")`, `UNPROVEN = pd.Timestamp("2026-02-23 03:00", tz="UTC")`, and `thin_monday(inserted) -> pd.DataFrame`: SPY rows for 2025-05-05 from 04:00 to 13:29 ET stored as true UTC (570 rows, `ts` 08:00 to 17:29 UTC), `volume` 1000, `open` 1000 plus the bar's own Eastern minute of the day, `high` 0.5 above the open, `low` 0.5 below it, `close` 0.25 above it, `inserted_at` as given. And `expected_minutes(first: str, last: str) -> pd.DataFrame`: the bars for those Eastern minutes with the same values, written from the minute alone, never through the code under test.

The two edits, as the spec gives them: the SELECT (`:190`) gains `inserted_at`; the placement (`:203-208`) becomes `place_stored_rows(df["ts"], df["volume"], df["inserted_at"])`, the Eastern clock for the regular-hours cut is `utc_to_eastern_naive` of the kept instants, the index is those instants, and `inserted_at` is dropped with `ts`. The empty-read return (`:201-202`) stays before the placement, so an empty read never touches the column, and drops `inserted_at` when the frame has it, so it gives the five columns either way.

- [ ] Write:
  - `test_strat_builder_load_1m_bars`: `sdb.pd.read_sql` patched to capture the SQL and return `thin_monday(PROVEN)` rows at or after `params["start_ts"]`: `_load_1m_bars(_Engine(), "SPY", "2025-05-05")` returns exactly 240 rows, index equal to the instants of `expected_minutes("09:30", "13:29")` (2025-05-05 13:30 UTC to 17:29 UTC), each row's `open, high, low, close, volume` equal to that minute's; `list(out.columns) == ["open", "high", "low", "close", "volume"]`; `str(out.index.dtype) == "datetime64[ns, UTC]"`; and the captured SQL holds `inserted_at`.
  - `test_strat_builder_load_1m_bars_unproven_twin`: `thin_monday(UNPROVEN)`: 390 rows from 09:30 to 15:59 ET, and the 09:30 row's `open` is 1330.0, the bar of 05:30 ET. This is what `main` returns for both fixtures today (run 2026-11-14 on 20d9c47b).
  - `test_strat_builder_load_1m_bars_needs_inserted_at`: the same rows without the column: `KeyError`.
  - `test_strat_builder_empty_read_returns_as_before` (Review Focus), parametrized over an empty frame with the six columns of `main`'s SELECT and one that also has `inserted_at`: each returns an empty frame whose columns are the five, and does not raise.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_readers_by_proof.py -q` (expect `test_strat_builder_load_1m_bars` FAIL with 390 rows where 240 are expected, and the `KeyError` test FAIL; the twin passes on `main`).
- [ ] Implement. Drop `stored_intraday_to_eastern` from the import at `:62-64` if nothing else in the file uses it; `eastern_index_to_utc` stays (`:393`).
- [ ] In `tests/gcp/test_strat_data_builder_gamma.py`, add `"inserted_at": pd.Timestamp("2026-02-23 03:00", tz="UTC")` to the `rows` frame at `:153-155`. No assertion changes.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_readers_by_proof.py tests/gcp/test_strat_data_builder_gamma.py tests/meta/test_timezone_boundaries.py -q` (expect all pass).
- [ ] Variant: keep the new SELECT and call `stored_intraday_to_eastern` as `main` does. `test_strat_builder_load_1m_bars` must fail with 390 rows. Revert.
- [ ] The render step.
- [ ] Commit: `fix(data): place proven 1-min rows where stored in the feature loader`

## Task 9: `load_intraday_bars` places rows by proof

Spec: Design H. Advances done_when[4]. Needs: Task 8 (the fixture).

**Files:** Modify `gcp/historical_signals.py` (the import at `:24`, `load_intraday_bars` at `:281-334`), `tests/scripts/test_run_historical_signals_strategy.py` (the two `read_sql` stubs, `:308` and `:348-363`), `tests/gcp/test_recompute_readers_by_proof.py`.

**Interfaces:** `load_intraday_bars(ticker: str, start: datetime, end: Optional[datetime] = None) -> pd.DataFrame` keeps its signature and its six columns, `Time, Open, High, Low, Last, Volume`; `Time` is the placed instant, `datetime64[ns, UTC]`.

The two edits: the select list of the f-string (`:314-323`) gains `inserted_at` after `volume AS "Volume"`; the placement (`:328-330`) becomes `place_stored_rows(df['Time'], df['Volume'], df['inserted_at'])`, `Time` is the kept instants, and `inserted_at` is dropped. The `WHERE` text, the bound parameters and the window cut (`:331-334`) are not touched. The empty-read return (`:326-327`) stays before the placement and drops `inserted_at` when the frame has it. Do not add an `interval` predicate here: it is the strict bar reader's edit.

- [ ] Write, with `hs.get_engine` patched to `lambda: object()` and `hs.pd.read_sql` patched to capture the SQL and return the fixture under the names the SELECT gives (`Time, Open, High, Low, Last, Volume, inserted_at`):
  - `test_historical_signals_load_intraday_bars`: `thin_monday(PROVEN)`: `load_intraday_bars("SPY", datetime(2025, 5, 5), datetime(2025, 5, 6, 8))` returns `list(bars.columns) == ["Time", "Open", "High", "Low", "Last", "Volume"]` and exactly 570 rows whose `Time` runs from 2025-05-05 08:00 UTC to 17:29 UTC, 240 of them from 13:30 UTC (09:30 ET) on and none after 17:29 UTC, each with the values of `expected_minutes("04:00", "13:29")` for its own minute; the captured SQL holds `inserted_at`.
  - `test_historical_signals_load_intraday_bars_unproven_twin`: `thin_monday(UNPROVEN)`: 570 rows whose `Time` runs from 12:00 UTC to 21:29 UTC (what `main` returns today, run 2026-11-14).
  - `test_historical_signals_load_intraday_bars_needs_inserted_at`: without the column: `KeyError`.
  - `test_historical_signals_empty_read_returns_as_before` (Review Focus), parametrized over an empty frame with and without `inserted_at`: each returns an empty frame with no `inserted_at` column, and does not raise.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_readers_by_proof.py -q` (expect the first and third FAIL: `Time` starts at 12:00 UTC, and no `KeyError`).
- [ ] Implement. Drop the names the file no longer uses from the import at `:24`; `utc_to_eastern_naive` stays (`:308`).
- [ ] In `tests/scripts/test_run_historical_signals_strategy.py`, give the two frames that stand for the read an `inserted_at` of `pd.Timestamp("2026-02-23 03:00", tz="UTC")` with `.assign(...)`: the lambda at `:308` and `rows` in `test_load_intraday_bars_fetches_a_window_in_both_conventions` (`:348-363`). Do not add it inside `_av_session` (`:294-301`): the tests at `:320` and after use that frame as the reader's output. No assertion changes.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_readers_by_proof.py tests/scripts/test_run_historical_signals_strategy.py tests/scripts/test_signal_quality_report.py tests/meta/test_timezone_boundaries.py -q` (expect all pass).
- [ ] Variant: as Task 8's, in this function. `test_historical_signals_load_intraday_bars` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `fix(data): place proven 1-min rows where stored in the signals loader`

## Task 10: `read_minutes` and `MINUTES_SQL` place rows by proof

Spec: Design H. Advances done_when[4]. Needs: Task 8 (the fixture).

**Files:** Modify `gcp/calibrate_level_params.py` (`MINUTES_SQL` at `:83-86`, `read_minutes` at `:250-269`), `tests/gcp/test_calibrate_level_params.py` (`_minutes`, `:57-72`), `tests/gcp/test_recompute_readers_by_proof.py`.

**Interfaces:** `read_minutes(query: QueryFn, ticker: str, start, before) -> pd.DataFrame` keeps its signature and its six columns, `timestamp, open, high, low, close, volume`; `timestamp` is `utc_to_eastern_naive` of the placed instant. `MINUTES_SQL` is the string of Global Constraints.

The two edits: `MINUTES_SQL` gains `inserted_at`; the placement (`:264-266`) becomes `place_stored_rows(df['ts'], df['volume'], df['inserted_at'])` with `timestamp` from `utc_to_eastern_naive`. The widened bounds (`:257-258`), the `None` check, the empty-read return (`:262-263`) and the date cut (`:267-269`) are not touched.

- [ ] Write, with `query` a function that asserts `sql == job.MINUTES_SQL` and returns the fixture:
  - `test_calibration_read_minutes`: `thin_monday(PROVEN)`: `read_minutes(query, "SPY", date(2025, 5, 5), date(2025, 5, 6))` returns 570 rows whose `timestamp` runs from 2025-05-05 04:00 to 13:29, 240 of them from 09:30 on, each with the values of `expected_minutes("04:00", "13:29")` for its own minute; `"inserted_at" in job.MINUTES_SQL` and `"interval = '1min'" in job.MINUTES_SQL`; `list(out.columns)` is the six.
  - `test_calibration_read_minutes_unproven_twin`: `thin_monday(UNPROVEN)`: 570 rows from 08:00 to 17:29 (what `main` returns today, run 2026-11-14).
  - `test_calibration_read_minutes_needs_inserted_at`: without the column: `KeyError`.
  - `test_a_run_whose_bars_lack_inserted_at_fails_the_ticker` (Review Focus): with the `FakeDb` of `tests/gcp/test_calibrate_level_params.py` answering `MINUTES_SQL` without the column, `job.run(["SPY"], ...)` returns a result whose `failed == ["SPY"]` and `rows_written == 0`.
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_readers_by_proof.py -q` (expect the first and third FAIL).
- [ ] Implement.
- [ ] In `tests/gcp/test_calibrate_level_params.py`, add `"inserted_at": pd.Timestamp("2026-02-23 03:00", tz="UTC")` to the frame `_minutes` builds (`:70-71`). No assertion changes. Against a prototype of this task eight tests of that file failed until the column was there, and `tests/agents/test_on_demand_level_calibration.py` passed unmodified (run 2026-11-14).
- [ ] Run: `python3 -m pytest tests/gcp/test_recompute_readers_by_proof.py tests/gcp/test_calibrate_level_params.py tests/agents/test_on_demand_level_calibration.py tests/meta/test_timezone_boundaries.py -q` (expect all pass).
- [ ] Variant: as Task 8's, in this function. `test_calibration_read_minutes` must fail. Revert.
- [ ] The render step.
- [ ] Commit: `fix(data): place proven 1-min rows where stored in the calibration read`

## Task 11: The three local measurements

Spec: Capacity (memory); Done when (the PR-body measurements). Advances done_when[6] (local half). Needs: Tasks 4 and 8.

**Files:** Create `tests/gcp/measure_export_intraday_bars.py` (not collected by pytest: its name does not start with `test_`; `tests/scripts/measure_inventory_render.py` is the precedent).

**Interfaces:** `python3 -m tests.gcp.measure_export_intraday_bars {nightly|history|loader}`: each mode runs in its own process, builds synthetic rows, patches `gcp.database.query_to_dataframe_strict` (or `strat_data_builder.pd.read_sql`), uses a `MemoryBucket`, and prints one line `mode={m} seconds={N.N} peak_rss_mb={N}` from `time.perf_counter()` and `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss`. It exits 1 when its bound is passed.
- `nightly`: `export_window` over 6 synthetic ticker-months of 25,000 rows each. No bound; the figures are reported.
- `history`: `export_window` over one ticker's 143 synthetic months (2015-01 to 2026-11) of 50,000 rows each. Bound: peak under 512 MB.
- `loader`: `strat_data_builder._load_1m_bars` over 3,000,000 synthetic proven rows in one frame. Bound: peak under 2,048 MB.

- [ ] Write the module. Synthetic rows are true UTC minutes from 04:00 ET, `inserted_at` 2026-11-20, a daily row per session.
- [ ] Run each mode once: `python3 -m tests.gcp.measure_export_intraday_bars nightly`, `... history`, `... loader` (expect exit 0 from each). On a bound passed, stop and report: the design holds one month at a time, so a breach is a defect in Task 4, not a number to raise.
- [ ] Save the three lines for the PR body. For the record beside them: the spec's prototype of the loader took 7.4 s and 1,158 MB against 6.1 s and 1,081 MB for the loader of `main`.
- [ ] Commit: `test(data): measure the bar export and the feature loader locally`

## Task 12: Whole suite, the files left alone, the generated inventory

Spec: Done when (the suites and files left unmodified). Advances done_when[5]. Needs: Tasks 2 to 11.

- [ ] Run: `make test`, in its normal order (expect no failure that `origin/main` does not have; Global Constraints, lesson 5).
- [ ] Run the render step once more on the final code and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass). `git status` shows no change to the three docs; if it does, commit: `docs(infra): re-render the inventory for the bar export`.
- [ ] Run: `git diff --stat origin/main -- gcp/deploy.sh platform/api CLAUDE.md .github lib/eastern_time.py scripts/audit_data_freshness.py tests/fixtures/timezone_boundary_baseline.json tests/fixtures/intraday_checks.py tests/lib/test_intraday_session_readings.py tests/gcp/test_intraday_verify_basis.py tests/gcp/test_intraday_as_traded.py tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_writers_utc.py tests/gcp/test_av_intraday_universe.py tests/meta/test_production_writers.py tests/meta/test_timezone_boundaries.py tests/agents/test_on_demand_level_calibration.py` (expect empty).
- [ ] Run: `git diff origin/main -- tests/gcp/test_strat_data_builder_gamma.py tests/scripts/test_run_historical_signals_strategy.py tests/gcp/test_calibrate_level_params.py | grep '^[-+].*assert'` (expect no line: no assertion of those three files changed).

## Task 13: Product record, site notes and the gate

Spec: Site traceability; Done when (the PR-body measurements, the product records); product-delivery Phase 4 and Phase 5. Closes done_when[6] (posted) and [7]. Needs: Tasks 1 to 12. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` may change without redoing all four of them: the source hash covers those paths.

- [ ] If Task 1 ran on an earlier day, run its premise count again, so the count on the PR is the day's. A row stops the PR.
- [ ] Push with `git push -u origin feature/feat-data-001-intraday-bucket-copy` and open a **draft** PR. Title: `FEAT-DATA-001: bucket copy of the 1-min bars and recompute readers that place rows by proof`. Body: the spec path and this plan's path; the 8 done_when items, each as a `- [ ]` line that starts with the item's text; a `Red then green` section (lesson 4); a Capacity section with one line per label, each value starting with its figure: `Volume:` 6 reads of about 20,000 rows and 6 files of about 0.6 MB a night, at most 143 files and about 85 MB a ticker for the history, 0 table rows written; `Velocity:` 6 bars queries, 3 daily queries, 6 uploads, 3 manifest reads and 6 manifest writes a night, 143, 1, 143, 1 and 143 a ticker for the history, 0 queries added to the three readers; `Wall-clock:` the seconds of Task 11's `nightly` and `history` lines against the fetch job's 3,600 s task timeout, and Task 1's execution time for one month read; `Cost:` about $0.0007 a nightly run, about 2 cents a month over 26 runs, about 3 cents for the one-time export, under 1 cent a month of storage, no new job or schedule. Paste Task 1's plan and the premise count's result with their execution ids, and Task 11's three lines. Say that no deployed-site run is planned (the spec's Site traceability: no route and no response changes), and that the spec's runbook is the owner's and starts after the merge.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record only (`:513`; not the table row at `:35`): in the Status cell (`:520`) append, before the closing ` |`: `; a bucket copy of the SPY, QQQ and IWM 1-min bars written by the nightly fetch job (one Parquet file per ticker-month and a manifest, read by no job, replay or route) and three recompute readers that place a proven row at its stored instant ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed; no stored bar is rewritten by it)`. Last reviewed (`:524`) becomes the date of the PR's head commit; the gate compares the two exactly, so set it again if a later commit lands on another day.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-DATA-001` (`:320`): append to its `**PR lineage:**` line (`:346`) ` · [#N](https://github.com/TeneikaAskew/stocks/pull/N) *remediation: bucket copy of the 1-min bars and proof-aware recompute readers, spec [#1868](https://github.com/TeneikaAskew/stocks/pull/1868)*`. No earlier entry is removed. Commit both docs and the plan: `docs(product): record the bar export under FEAT-DATA-001`.
- [ ] Site notes, step 1 (preflight). With every code and test commit in place and a clean tree, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`. It prints a JSON verdict and installs nothing yet (status `unverified`, exit 1). Copy its `source_identity_sha256`.
- [ ] Site notes, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes` (`:1297`), leave one `| FEAT-DATA-001 | <component> | source_identity_sha256=<that hash>; <text> |` row for each of the ten declared components and change no other byte. In the table's sort order the FEAT-DATA-001 rows then read ADMIN-02, ADMIN-06, ADMIN-07, CHARTS-06, DASHBOARD-01, DASHBOARD-04, DASHBOARD-05, DASHBOARD-08, DASHBOARD-21, INSIGHTS-01, LIVE-03, SHARED-07, SIGNALS-01. Nine are new; ADMIN-02 (`:1303`) exists since #1920 and is extended: the new hash, this change's text, then ` Earlier: ` and the row's prose from `` `GET /api/admin/data-sources` regroups `` to its end, unchanged. If another FEAT-DATA-001 change has left one of the other nine on `main` by then (DASHBOARD-04 from the two-bar-writers lane; ADMIN-06, CHARTS-06, DASHBOARD-05, SIGNALS-01 from the strict bar reader), extend that row the same way. Each text is its sentence, then the closing sentence:
  - DASHBOARD-04: the `fetch-alphavantage-intraday` job (`gcp/fetchers/fetch_alphavantage_intraday.py`, `main`) now also writes the SPY, QQQ and IWM 1-min bars of the current and the previous Eastern month to the bucket after its nightly fetch (`gcp/fetchers/export_intraday_bars.py`: one Parquet file per ticker-month and a manifest under `intraday-bars/v1/1min/`); `GET /api/market/data/{ticker}/{date}`, its reader and the bars it reads are unchanged, and no route reads the bucket copy. Tests: `tests/gcp/test_export_intraday_bars.py`.
  - DASHBOARD-21 and ADMIN-02: the `strat-engine` job's bar loader (`gcp/research/strat_engine/strat_data_builder.py`, `_load_1m_bars`) selects `inserted_at` and places a row proven a true UTC instant at its stored instant (`lib.eastern_time.place_stored_rows`); a row that is not proven is placed as before. Tests: `tests/gcp/test_recompute_readers_by_proof.py`.
  - DASHBOARD-05, CHARTS-06, SIGNALS-01 and ADMIN-06: the same sentence for the `historical-signals-watchlist` job and `gcp/historical_signals.py`, `load_intraday_bars`.
  - DASHBOARD-08, INSIGHTS-01 and ADMIN-07: the same sentence for the on-demand level calibration inside an insight run (the `insight-pipeline` job and `POST /api/insights/report/{ticker}/refresh`) and `gcp/calibrate_level_params.py`, `read_minutes`.
  - closing sentence, every row: `No route and no response shape changes. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.`
  Commit: `docs(site): note the bar export and the proof-aware readers`.
- [ ] Site notes, step 3. Run the same `produce` command again; it now writes the sidecar. Commit: `docs(site): regenerate the source snapshot`.
- [ ] Site notes, step 4. Run `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched file later, bring the branch up to date, re-render (lesson 1) and repeat steps 1 to 4 with the new hash in all ten rows (lesson 2).
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > /tmp/audit-branch.txt`; then `git worktree add --detach /tmp/audit-main origin/main`, run the same command there into `/tmp/audit-main.txt`, and `git worktree remove /tmp/audit-main`. Compare the `[P1]`, `[P2]` and `[P3]` finding lines: the branch reports none that `main` does not. A new finding is fixed or reported, not waived. Exit code 2 means the run itself failed, not that the docs are clean.
- [ ] Run: `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass) and `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Push the close-out commits. Tick each done_when box in the PR body with its evidence beside it (test name, execution id, file). Only then mark the PR ready for review (lesson 3). Review cap: two rounds.

## Close-out (not tasks; owner's steps)

From the spec's Close-out. None of it is done by the implementer of this plan, none of it is a done_when box, and every step, read-only ones included, starts on the owner's own yes for that step.

- **Before the merge:** nothing but the read-only measurements of Task 1. The premise count must hold no row.
- **After the merge:** the spec's runbook, steps 1 to 8, in its order and with its checks: deploy the fetchers; regenerate the lists read-only; refetch the thin months; first history write to the bucket; rewrite every month that holds a row not proven; scan, fill and confirm; recompute what reads the bars; second history write. Step 5 stays behind #1190 (CLAUDE.md 3.9).
- **After the runbook:** the ten notes and this plan's status are brought to the deployed state on a `docs/` branch. From product-delivery Phase 5 step 7: after the merge, on a `docs/` branch, set this plan's `status: done`.

### For the owner: what the 2026-11-14 rewrite appears to have covered

The spec's runbook was written before the owner had the whole SPY, QQQ and IWM history rewritten as traded by plain upsert (2015-01 to 2026-11). This plan decides nothing about what the runbook skips. Each row names the read-only check that would confirm it; none was run for this plan.

| Runbook step | Appears covered? | Read-only check |
|---|---|---|
| 1 deploy | no: this code is not merged | none |
| 2 regenerate the lists | no, and it is the check for the rows below | the step itself: the three-ticker premise count, `--intraday-gap-since=2015-01-01`, `--verify-basis`, `--verify-months` |
| 3 refetch the thin months of 2025 | yes in effect: the same plain fetch ran over those months | the scan's SESSION-GAP lines for SPY 2025-04 to 06 and QQQ 2025-01; each month's stored row count against the count the 2026-11-14 run logged (`YYYY-MM: N bars`, `fetch_alphavantage_intraday.py:322`); `--verify-basis` over the four months prints no BASIS-FAIL and no EMPTY |
| 4 first history write | no. Its stated use, a copy with the adjusted months named while the rewrite waits, is smaller now | `--verify-basis` over every MONTH line: how many months still print BASIS-FAIL |
| 5 rewrite every month with a row not proven | the basis, yes in effect. Not the proof: a row an upsert rewrites in place keeps its old `inserted_at`. Not the misplaced rows: an upsert cannot remove the legacy labels of 2026-04 to 2026-09. Not the derived tables: an upsert clears none of the 15 `DERIVED_TS_TABLES` | `unproven_rows=` on the scan's MONTH lines; the premise count without its `inserted_at` predicate, for the three tickers, grouped by month (the label-only rows still stored); the VERIFY-FAIL lines of `--verify-months` |
| 6 scan, fill, confirm | partly: the sessions still thin are candidates for the accepted record. The pass condition (`unproven_rows=0` on every MONTH line, `--verify-basis` exit 0) cannot be met by an upsert | the two runs of the pass condition, as the spec words them |
| 7 recompute | no: every table computed from the bars holds values from the old bars, now over the whole history and not only the windows the spec names | the spec's step-7 query for one rewritten session: `matched` below `bars` shows `strat_features_1m` is stale |
| 8 second history write | no | none |

### For the owner: what this needs outside FEAT-DATA-001

- `gcp/deploy.sh` (FEAT-DEPLOY-001): nothing for this PR to work. The spec calls for no new job and no new scheduler; the export rides the nightly's argument shape, and `GCS_BUCKET` is already in the job's environment (`gcp/deploy.sh:1127`). The watched-ticker lane needed a separate FEAT-DEPLOY-001 wiring spec because it added a job; that split does not apply here. One item is reported for that capability, as the spec asks: the two stale comment lines that say `--memory 8Gi` (`gcp/deploy.sh:1706`, `:1728`) where the job is declared at 16Gi.
- `CLAUDE.md` (FEAT-CICD-001 branch): section 3.9 still names `stored_intraday_to_eastern` as the way to read across the migration, and 3.7.1 says the bucket holds ingestion staging only. Both want a sentence once this merges; neither is edited here.
- `.github/`: nothing.
