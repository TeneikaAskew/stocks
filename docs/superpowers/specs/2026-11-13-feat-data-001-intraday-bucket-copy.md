---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-DATA-001, REQ-DATA-003]
issues: [1190]
canvases: []
site_source_notes: [DASHBOARD-04]
done_when:
  - "tests/gcp/test_export_intraday_bars.py passes for the file: export_month writes intraday-bars/v1/1min/TICKER/YYYY-MM.parquet (zstd; columns ts, open, high, low, close, volume, data_source; ts UTC ascending) whose rows equal an expected table written out in the test and not computed by the code under test, for a month stored as true UTC, a month stored as labels, a month stored both ways with different prices in the two copies, and a month end where the 20:00 ET bar of the last day is stored on the 1st in UTC (it is in the earlier month's file and not in the later one's); the run reads market_data_intraday with one strict query per ticker-month bounded by lib.eastern_time.intraday_month_window with interval = '1min' in the SQL text, and market_data_daily with one strict query per ticker that selects date, high, low and data_source; each row's instant is the one lib.eastern_time.place_stored_rows returns; an existing file is overwritten; a NULL price stays null; a whole session stored both ways with flat volume and the label copy on the shared keys is written as place_stored_rows returns it, with every such row counted in inferred_rows; a query raising ConnectionError('connection refused'), a query raising KeyError('high'), an upload raising ConnectionError and an upload raising PermissionError each propagate and leave the stored manifest byte for byte as it was (on main the module does not exist)"
  - "tests/gcp/test_export_intraday_bars.py passes for the manifest: manifest.json records per month the file, rows, stored_rows, dropped_rows, inferred_rows, first and last ts, sha256, exported_at, the session counts (expected, ok, thin, missing, undetermined) from session_minute_readings, and the basis from fetch_alphavantage_intraday.session_basis_verdicts (state as_traded, inferred, adjusted, partial or unmeasured, the factor range, the counts as_traded, inferred, adjusted and odd, and each session that is not counted as as_traded, inferred or adjusted under not_measured with one of the reasons no_daily_row, daily_from_intraday, daily_source_unknown, daily_not_positive, no_rth_high_low, incomplete and odd); rows plus dropped_rows equals stored_rows; a month whose sessions all measure as traded and of which one rests on a row that is not proven has state inferred and never as_traded; a month with a session whose daily row is stamped alphavantage_1min records that session as daily_from_intraday and is never as_traded; a session with no daily row is recorded as no_daily_row and its month is never as_traded; a month with no row gets an entry with rows 0 and no file; on a bucket that holds no manifest the first export creates it with if_generation_match=0, version 1 and its one month; when another run creates the manifest between this run's read and its write, the precondition fails and the retry keeps the other run's entry and adds this one; an entry another run wrote between this run's read and write of an existing manifest is kept; a manifest read that fails for any reason other than the object being absent raises and nothing is written; the manifest is written after each month's file, so when the second month's upload of a two-month run raises, read_bars still returns the first month and the second month's file and entry are as they were; when the manifest write raises after a month's upload, read_bars raises ValueError for that month; and a manifest that does not parse or whose version is not 1 raises and is not replaced (on main the module does not exist; with one manifest write per ticker a failed second upload left the first month failing its hash, prototype run 2026-11-13)"
  - "tests/gcp/test_export_intraday_bars.py passes for when the export runs: fetch_alphavantage_intraday.main exports the current and the previous Eastern month of SPY, QQQ and IWM after its fetch loop only for the nightly arguments (--symbol=ALL --force, no dates, no symbols file, one task) with the database configured and INTRADAY_BARS_EXPORT not off; with the clock at 2026-10-31 21:00 ET (2026-11-01 01:00 UTC) those months are 2026-09 and 2026-10; a run without --force, a run with --start-date and a run with --symbols-file export nothing; INTRADAY_BARS_EXPORT=off exports nothing and logs one line naming the variable; with the database not configured main exports nothing and issues no query, so tests/gcp/test_av_intraday_universe.py passes unmodified; with the database configured and GCS_BUCKET unset the export raises; after an export that succeeds main logs one line that starts 'bars export:' and holds the months written, the rows written and the seconds it took; an export that raises ConnectionError makes main log a line starting 'bars export failed (outage)' and one that raises KeyError a line starting 'bars export failed (defect)', each after the fetch summary, and exit 1; --export-bars-from YYYY-MM writes every month from the one given to the current Eastern month for the three tickers or the one of them named by --symbol, fetches nothing, refuses any other ticker with exit 1 before any query, and exits 1 when the database or GCS_BUCKET is not configured; and --export-bars-from together with --replace-months, --verify-months or --verify-basis is a usage error (on main none of this exists)"
  - "tests/gcp/test_export_intraday_bars.py passes for read_bars: it returns the pair (bars, months), bars holding exactly the exported rows of the requested months (the seven columns, ts as UTC datetimes ascending) and months the requested months' manifest entries in order; it raises FileNotFoundError when the manifest or a requested month's file is absent, KeyError when a requested month has no manifest entry, and ValueError naming the month when a month's file was replaced by a different valid Parquet file, when the manifest's version is not 1 and when first_month is after last_month; it returns a month the manifest records with rows 0 without raising; it returns a month whose state is inferred, adjusted, partial or unmeasured without raising; and it runs in a subprocess in which gcp.database, lib, sqlalchemy, google, requests and pandas_market_calendars cannot be imported (on main the function does not exist)"
  - "make test passes on the PR head with tests/lib/test_intraday_session_readings.py, tests/gcp/test_intraday_verify_basis.py, tests/gcp/test_intraday_as_traded.py, tests/gcp/test_intraday_replace_months.py, tests/gcp/test_intraday_writers_utc.py, tests/gcp/test_av_intraday_universe.py, tests/meta/test_production_writers.py and tests/meta/test_timezone_boundaries.py unmodified, tests/fixtures/timezone_boundary_baseline.json unmodified, and gcp/deploy.sh, platform/api, CLAUDE.md, lib/eastern_time.py and scripts/audit_data_freshness.py not in the PR's diff"
  - "The PR body gives, run read-only through scripts/db_query_cr.sh and pasted with its execution id, EXPLAIN (ANALYZE, BUFFERS) for the export's month-window bars query for SPY 2025-05, showing rows read on its scan node equal to the rows it returns. It also gives, measured locally with an in-memory bucket, the seconds and the peak resident memory of the nightly export over 6 synthetic ticker-months of 25,000 rows each, and of --export-bars-from over one ticker's 143 synthetic months of 50,000 rows each, the second under 512 MB (on main the module does not exist, and neither figure was measured for this spec)"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md gain the (FEAT-DATA-001, DASHBOARD-04) row, docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes (on main the notes table holds no FEAT-DATA-001 row for DASHBOARD-04)"
status: draft
supersedes: null
---

# market_data_intraday: a durable copy of the 1-min bars in the bucket, and the runbook that makes the stored bars whole and as traded

## Scope

- This spec is the bucket copy of the SPY, QQQ and IWM 1-min bars (Design E) and the production runbook that refetches the thin months, rewrites the stored bars as traded, recomputes what reads them and writes the history to the bucket (Close-out).
- It is the second of two specs in one PR. The first, `docs/superpowers/specs/2026-11-13-feat-data-001-intraday-gaps-basis-copy.md` (file A), holds the checks: the session readings, the gap alarm, the basis check, the workflow test and the levels tables in the replace's clear list. The two were one spec of 16 tasks, over the line of about 15 (`.claude/skills/product-delivery/references/plan-template.md:39`).
- **Its plan opens after file A's implementation is on `main`.** What it uses from file A, and nothing else of it:

| From file A | Where | Used here by |
|---|---|---|
| `intraday_month_window(year, month)` | `lib/eastern_time.py` | the export's month bounds |
| `place_stored_rows(ts, volume, inserted_at)` | `lib/eastern_time.py` | the instant written for each row |
| `session_minute_readings(ts, inserted_at, schedule)` | `lib/eastern_time.py` | the manifest's session counts |
| `session_basis_verdicts(rows, daily, schedule)` and `TRUE_DAILY_SOURCES` | `gcp/fetchers/fetch_alphavantage_intraday.py` | the manifest's basis |
| `--intraday-gap-since`, `--verify-basis`, the six levels tables in `DERIVED_TS_TABLES` | the watchdog and the fetch job | the runbook only, not the code |

- The order:
  1. File A's implementation merges, is deployed and is verified read-only (file A, Close-out, steps 1 and 2).
  2. This file's plan opens, and its implementation merges.
  3. The runbook runs, in the order its steps are numbered. Step 1 deploys this file's code. Steps 2, 3, 5, 6 and 7 use only file A's flags and code that is on `main` today. Steps 4 and 8, the two writes of the history to the bucket, are the ones that need this file's code.
- The code and every runbook step cover SPY, QQQ and IWM only.
- No trading cost is applied or stored anywhere in this change. Bars and the bucket copy carry prices as traded and nothing else.
- Code references are to `main` c698b24e. The design letter E is the one the single spec used, kept so the review threads still point at it.

## Problem

Where a number below has no execution id beside it, it was reported by the analysis session of 2026-11-13 and was not checked for this revision. Step 2 of the runbook regenerates every list with the deployed checks before any write.

### 1. An analysis has to re-export the bars every time

- A session that cannot reach Cloud SQL (Claude Code on the web: port 443 only) reads bars through the `db-query` job, 50,000 rows a statement. On 2026-11-13 the export of the signal tickers' bars took about 55 minutes of job runs, and the copy lives only in that session's container.
- The bucket's old `raw/<ticker>/intraday/` parquets stop at 2026-05 and are deleted after 730 days by a lifecycle rule (`gcp/deploy.sh:3337-3358`).

### 2. The stored bars are not whole, not on one basis and not in one convention

The evidence and its tables are in file A's Problem. In short:

- **Thin sessions**: 73 stored sessions hold under 90% of their regular-hours minutes (SPY 49, QQQ 23, IWM 1), in 11 ticker-months from 2021-04 to 2025-06. The missing sessions of November and December 2025 were refilled on 2026-11-13 (below).
- **Many bases**: until 2026-11-13 every 1-min request returned adjusted prices, so each stored bar sits at the basis of its last fetch. At least 289 ticker-months hold sessions on an adjusted basis, with at least 4,645,371 rows in them. SPY before 2022-02-24 was not in that count.
- **Two timestamp conventions**: true UTC, and legacy Eastern clock labelled UTC (CLAUDE.md 3.9). A row inserted before 2026-09-28 on an earlier date is not proven to be either (file A, Design F).
- File A's checks find all three and change no stored bar. Making the bars right is a production rewrite, and it needs both files deployed: file A's flags to list and verify, and this file's export to put the result in the bucket. So the runbook is here.

## Non-goals

- No production write from the implementation PR, and no deploy other than the staging deploy of the API that every merge to `main` starts. Every production step is in Close-out and waits for the owner's own yes. The only production access before the merge is the read-only measurement of `done_when`, through `scripts/db_query_cr.sh`.
- No ticker other than SPY, QQQ and IWM is refetched, rewritten or copied to the bucket.
- No change to a request, to the watchlist, or to which tickers or months any job fetches. The `default` watchlist was reduced to SPY, QQQ and IWM on 2026-11-13 (as reported to this revision; not re-read for it), so `--symbol=ALL` resolves to those three (`gcp/calibrate_level_params.py:96-100`).
- No new writer of `market_data_intraday`. The export module only reads it. The draft spec `2026-11-13-feat-data-001-two-bar-writers.md` holds the writers to `gcp/fetchers/fetch_alphavantage_intraday.py` and `gcp/fetchers/fetch_market_data.py`; nothing here adds a third, and every write of the runbook goes through the first of those (Other specs this one meets).
- The bucket copy is a durable copy for analysis sessions. It is not a replay source. FEAT-REPLAY-001 (`2026-11-13-feat-replay-001-replay-bars-from-the-table.md`, approved) and the draft `2026-11-13-feat-data-001-strict-bar-loader.md` hold replays and backtests to `market_data_intraday`; both say no bucket copy of the bars is designed or read there. No job, replay, backtest or API path reads this copy, and it is never a fallback for Cloud SQL (CLAUDE.md 3.7.1).
- No change to `lib/eastern_time.py`, to `scripts/audit_data_freshness.py`, or to either check of file A. This file calls them.
- No change to `gcp/deploy.sh`, to a schedule, or to any job's memory, timeout or retries. That file belongs to FEAT-DEPLOY-001 and the gate refuses it here. No new job and no new scheduler. The one temporary memory raise is a runbook step (step 7).
- No change to `platform/api`, and nothing the site shows.
- No change to the daily table, to `adjusted_close`, or to how any reader uses intraday prices. Re-pulling a daily row is not a step of the runbook.

## Approaches considered

For the copy:

1. A nightly write from the fetch job, one Parquet file per ticker and month with a manifest beside it (chosen). An analysis session downloads files and reads the manifest to know how whole and on what basis each month is.
2. Keep exporting through `db-query`: about 55 minutes each time, and the copy dies with the session.
3. Go on with the `raw/<ticker>/intraday/` parquets: they stop at 2026-05, a lifecycle rule deletes them after 730 days, and nothing beside them says what a month holds.
4. A job and a scheduler of its own: both are `gcp/deploy.sh` changes, which belong to FEAT-DEPLOY-001, and one more schedule to keep in step with the nightly fetch.

For the rewrite (runbook, step 5):

1. Rewrite every month that holds a row not proven true UTC (chosen). After it the final checks rest on no inference, and the two shapes that read OK when something is wrong cannot remain (file A, Design F).
2. Rewrite only the months a check fails: months that pass on unproven rows stay, and so do those two shapes.
3. Relabel timestamps in SQL: it cannot restore the bars that were overwritten where the two conventions met (CLAUDE.md 3.9), and it fixes no basis.

## Design

### E. Durable copy of the bars in the bucket

A nightly write of the SPY, QQQ and IWM 1-min bars from Cloud SQL to GCS, so an analysis session downloads files instead of re-exporting.

- **Where**: `gs://<GCS_BUCKET>/intraday-bars/v1/1min/<TICKER>/<YYYY-MM>.parquet`, one file per ticker per month, plus `intraday-bars/v1/1min/<TICKER>/manifest.json`. `GCS_BUCKET` is the job's variable (`adept-mountain-474619-d4-trading-data`, set by `_env_string`, `gcp/deploy.sh:1127`); a leading `gs://` is dropped. The `intraday-bars/` prefix has no lifecycle rule (the bucket's two rules delete `sql-dumps/` after 30 days and `raw/` after 730, `gcp/deploy.sh:3337-3358`). The job's service account, `trading-runner@`, holds Storage Object Admin on the bucket (CLAUDE.md, Database access; not re-read from IAM for this spec).
- **A month** is `lib.eastern_time.intraday_month_window(year, month)`: `[M-01 02:00Z, (M+1)-01 02:00Z)`. For bars between 04:00 and 20:00 ET that is the Eastern month: the 20:00 ET bar of a month's last day, stored at 00:00 or 01:00 UTC on the 1st, is in that month's file (run on four months, 2026-11-13).
- **What the export reads**, both through `query_to_dataframe_strict` with a 120 s statement timeout:
  - bars, one query per ticker-month: `SELECT ts, open, high, low, close, volume, data_source, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`. It does not call `gcp.historical_signals.load_intraday_bars`, which returns no `data_source` and is not bounded to a month (`gcp/historical_signals.py:281-334`).
  - daily, one query per ticker for the run's months: `SELECT date, high, low, data_source FROM market_data_daily WHERE ticker = :t AND date >= :first AND date <= :last`, the basis check's query.
- **The instant written for each row**: `place_stored_rows`. When two stored rows land on one minute one is written and the other is counted in `dropped_rows`.
  - A proven row is written at its stored instant. A row that is not proven is written where the resolver puts it, and is counted in `inferred_rows`.
  - The named limit of file A's Design F applies: a whole session stored under both conventions with flat volume and the label copy on the shared keys is written with all 390 regular-hours rows on the wrong minute. Nothing in the file marks those rows. The month's `inferred_rows` is above 0, which is the only flag. The rewrite removes the shape.
- **Format**: Parquet, zstd. Columns `ts` (timestamp, UTC), `open`, `high`, `low`, `close` (float64), `volume` (int64, nullable), `data_source` (string). One row per bar, ascending `ts`. A NULL in the table stays null in the file; nothing is filled in.
- **Manifest**, one JSON object per ticker, `{"version": 1, "ticker": "SPY", "months": {"2025-05": {...}}}`. Each month entry holds:
  - `file` (the object name, or null when the month has no row), `rows`, `first_ts`, `last_ts`, `sha256` (of the file's bytes), `exported_at`;
  - `stored_rows` (rows the query returned), `dropped_rows`, and `inferred_rows` (rows written that are not proven, so their instant rests on the resolver). `rows + dropped_rows` equals `stored_rows`. A month with `inferred_rows` 0 is exact.
  - `sessions`, from `session_minute_readings`: `expected` (the calendar's sessions of the month whose close has passed), `ok`, `thin`, `missing`, `undetermined`.
  - `basis`, from `session_basis_verdicts`: `state`, `factor_min`, `factor_max`, the counts `as_traded`, `inferred`, `adjusted` and `odd`, and `not_measured`, a map from session date to reason for every session that is not counted as `as_traded`, `inferred` or `adjusted`. The count `as_traded` is of sessions AS-TRADED from proven rows.
    - The reasons: `no_daily_row`, `daily_from_intraday`, `daily_source_unknown`, `daily_not_positive` (a daily high or low that is NULL or not positive), `no_rth_high_low` (no non-null regular-hours high or low), `incomplete` (MISSING, THIN or UNDETERMINED), `odd`.
    - The state takes the first of these that applies:
      - `adjusted`: at least one ADJUSTED session.
      - `inferred`: at least one INFERRED session, which is an as-traded verdict that rests on a row that is not proven.
      - `unmeasured`: no session is counted as `as_traded`, `inferred` or `adjusted`. Both factors are null.
      - `as_traded`: every expected session is AS-TRADED from proven rows.
      - `partial`: at least one session is AS-TRADED from proven rows and at least one is under `not_measured`.
    - So the manifest never says more than the basis check does: a month reads `as_traded` only where `--verify-basis` would print no line for it at all.
  - The state is named, so no reader compares a factor with 1.0.
  - The nightly export runs at 21:00 ET and the daily fetch at 23:00 ET (`fetch-market-data-daily`, `0 23 * * 1-5`, `gcp/deploy.sh:4622`). So the newest session has no daily row when it is exported: the current month lists that session under `not_measured` as `no_daily_row` every weeknight, and the next export measures it.
- **The bucket** is reached through one small object, so the tests pass an in-memory one:
  - `read(name)` returns the bytes and the object's GCS generation, or says the object is absent. Absent is an answer; any other failure raises. A helper that turned a failed read into "absent" would make the next write start a fresh manifest over a real one (CLAUDE.md 3.7.1), so the two are never the same value.
  - `write(name, data, if_generation_match=None)` returns the new generation.
- **Writes**, one month at a time: the month's file is uploaded whole, then the manifest is written with that month's entry. The nightly does this for each of its two months of each ticker; `--export-bars-from` does it for each month in turn.
  - **The manifest does not exist yet** (the first nightly after the deploy, and the first month of a ticker): the run starts from `{"version": 1, "ticker": T, "months": {}}` and writes it with `if_generation_match=0`, which GCS accepts only when the object does not exist (its documented precondition; not checked against the bucket for this spec, and the in-memory bucket of the tests follows the same rule). If another run created it in between, the write fails its precondition and the run goes on as below. A prototype run on 2026-11-13 created the manifest at generation 1 on the first run and kept both entries after a lost race.
  - **The manifest exists**: it is read with its generation and written with `if_generation_match` set to that generation. On a mismatch the run reads it again, puts its own month entry into the fresh copy and retries, up to 5 times, then raises. An entry another run wrote for another month is never lost.
  - A manifest that does not parse, or whose `version` is not 1, raises. It is never replaced by a fresh one.
  - A failed query or upload raises before the manifest is touched for that month.
- **What a failure between two writes leaves**, and what a reader does:
  - The second month's upload fails: the first month's file and entry were both written and match. The second month's file and entry are as they were. With one manifest write per ticker, as the reviewed text had it, the first month's new file would not match its recorded hash until the next run (prototype run 2026-11-13).
  - A month's upload succeeds and its manifest write fails: that one month's file is new and its entry describes the old file. `read_bars` raises `ValueError` naming the month. The run fails. The next nightly rewrites the current and the previous month; an older month is healed by running `--export-bars-from` again.
  - A reader who copies the folder between a month's two writes sees the same mismatch for that month. The rule for a reader: on `ValueError` for a month, copy the ticker's folder again; if it still raises, that month is unreadable until the next export of it, and the reader works without it. `read_bars` never returns rows of a file that does not match its entry.
- **Which runs export**, decided in `main()` after the fetch loop:
  - All of: `--symbol` is ALL and no `--symbols-file`; `--force`; neither `--start-date` nor `--end-date`; one task (`CLOUD_RUN_TASK_COUNT` unset or 1); the database configured; `INTRADAY_BARS_EXPORT` not `off`.
  - `av-intraday-nightly` (`--symbol=ALL --force`, `gcp/deploy.sh:4741`): exports. A manual run with the same arguments also does.
  - `av-intraday-monthly` (no arguments, `gcp/deploy.sh:4723`): does not, so the two schedulers cannot both export at 21:00 ET on a 1st.
  - Manual dated runs and `intraday-bulk-backfill` (a symbols file, a start date, four tasks): do not. After such a run the months it wrote are exported with `--export-bars-from`.
  - `INTRADAY_BARS_EXPORT=off` (any letter case): no export; one log line names the variable.
  - Database not configured: no export and no query; one log line. The fetch writes nothing in that case either. `tests/gcp/test_av_intraday_universe.py` calls `main()` this way, its watchlist stub refuses any other strict query, and it passes unmodified (4 passed on `main`, run 2026-11-13).
  - Database configured and `GCS_BUCKET` unset: the export raises. It does not guess a bucket.
  - The trigger is the nightly's argument shape because an explicit flag on the scheduler would be a `gcp/deploy.sh` change.
- **Which months**: the current Eastern month and the one before it, from `lib.eastern_time.market_today()`. `main()` takes its fetch range from `date.today()` in a UTC container, which at 21:00 ET is already the next day. The fetch range is not changed here. At 2026-10-31 21:00 ET the fetch range is 2026-10 and 2026-11 and the export writes 2026-09 and 2026-10 (run 2026-11-13). On every evening the export's two months include each month that run wrote rows to.
- **What a run logs**. The module logs at INFO (`lib/logging_config.py:18`), so these lines are printed.
  - After an export that succeeds: `bars export: N months, N rows, N.N s`. The runbook reads the seconds from this line.
  - After one that fails: `bars export failed (outage): ...` when `lib.infra_errors.is_infrastructure_error` says so and `bars export failed (defect): ...` otherwise, after the fetch summary, and `main()` exits 1.
- **A failed export**. The bars are already in Cloud SQL. The job has `--max-retries 1` (`gcp/deploy.sh:2217`; the live job read 1 on 2026-11-09, `tests/fixtures/live_gcp_snapshot_2026-11-09.json`), so Cloud Run runs the task once more: the fetch repeats (an upsert of the same months) and the export repeats. If it fails again the execution fails and the notifier files it. The export also runs when the fetch had a failed ticker; the exit is 1 if either failed.
- **One-time history**: `--export-bars-from YYYY-MM` writes every month from the one given to the current Eastern month and fetches nothing. It is a separate run from `--replace-months`, `--verify-months` and `--verify-basis`; two of them together is a usage error.
  - `--symbol=ALL` (the default) covers the three tickers; `--symbol SPY` covers one; any other ticker exits 1 before any query.
  - It exits 1 when the database or `GCS_BUCKET` is not configured: an explicit export must not end quietly.
  - The manifest is written after each month, as in the nightly, so a run that stops keeps what it wrote and a rerun converges.
  - Run per ticker: `gcloud run jobs execute fetch-alphavantage-intraday --region us-east1 --args="--export-bars-from=2015-01,--symbol=SPY" --wait`.
- **Module**: `gcp/fetchers/export_intraday_bars.py`: `export_month`, `export_window`, `read_bars`. Its top-level imports are the standard library and pandas. `gcp.database`, `lib.eastern_time`, `lib.infra_errors`, the GCS client and the fetch module are imported inside the export functions.
- **How a session reads it**:
  ```bash
  env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage cp -r \
    gs://adept-mountain-474619-d4-trading-data/intraday-bars/v1/1min/SPY ./bars/
  ```
  ```python
  from gcp.fetchers.export_intraday_bars import read_bars
  bars, months = read_bars("./bars", "SPY", "2025-01", "2026-11")
  ```
  - `read_bars(root, ticker, first_month, last_month)` returns one pair. `bars` is a DataFrame of the seven columns, `ts` as UTC datetimes ascending, a fresh integer index. `months` is a list with one dict per requested month in order: the manifest entry plus `"month"`.
  - It raises `FileNotFoundError` when the manifest or a month's file is absent, `KeyError` when a requested month has no manifest entry, and `ValueError` when a file's sha256 differs from the manifest's (naming the month), the manifest's `version` is not 1, or `first_month` is after `last_month`. A month recorded with `rows` 0 adds no rows and does not raise.
  - It does not refuse a month whose state is `inferred`, `adjusted`, `partial` or `unmeasured`, or one with `inferred_rows` above 0 or sessions thin, missing or undetermined: the caller reads those from `months`.
  - It needs `pandas` and `pyarrow` only. The test runs it in a subprocess where `gcp.database`, `lib`, `sqlalchemy`, `google`, `requests` and `pandas_market_calendars` cannot be imported.

### What bad input gets

An outage and a defect do not get the same answer. `lib.infra_errors.is_infrastructure_error` is the classifier; on 2026-11-13 it called `ConnectionError('connection refused')` an outage and `KeyError('inserted_at')` a defect.

| Read or write | Input | On `main` today | After |
|---|---|---|---|
| export | failed query or upload, either kind | the module does not exist | raises; the manifest is untouched for that month; `main()` logs outage or defect and exits 1 |
| export | NULL price or volume | | null in the file |
| export | no manifest in the bucket | | created with `if_generation_match=0` |
| export | the manifest read fails, other than the object being absent | | raises; nothing is written |
| export | manifest that does not parse, or version not 1 | | raises; not replaced |
| export | another run wrote the manifest in between | | read again, own entry put in, retried up to 5 times |
| export | a session whose daily row was built from the 1-min bars, or has no known stamp | | under `not_measured`; the month is never `as_traded` |
| `read_bars` | file absent, entry absent, hash differs | | `FileNotFoundError`, `KeyError`, `ValueError` naming the month |

Each case has a test named in `done_when`, with the exception it raises.

### Other specs this one meets

- **File A** (`2026-11-13-feat-data-001-intraday-gaps-basis-copy.md`): the table under Scope lists every function and flag of it that this file uses. This file changes none of them.
- **FEAT-REPLAY-001** (`2026-11-13-feat-replay-001-replay-bars-from-the-table.md`, approved): replays read bars only from the table. The bucket copy is a durable copy and never a replay source (Non-goals). The module's flag and variable names (`--export-bars-from`, `INTRADAY_BARS_EXPORT`) match none of the patterns of that spec's registration guard.
- **The draft two-bar-writers spec** (`2026-11-13-feat-data-001-two-bar-writers.md`): who may write the table.
  - The export module only reads. It spells no write statement and no write helper call on the table, a docstring included, and holds no string constant that names a writer module or a writer job.
  - It imports `session_basis_verdicts` and `TRUE_DAILY_SOURCES` from a sanctioned writer file. Neither reaches a write, so neither is in that guard's writer closure, and its test accepts such an import.
  - `main()` of `gcp/fetchers/fetch_alphavantage_intraday.py` calls the export after its fetch loop. `main()` is already one of that file's named entry points.
  - Every write of the runbook is one that spec names for an operator: the `fetch-alphavantage-intraday` job run with `--symbol`, `--start-date` and `--end-date` (steps 3 and 6), and with `--replace-months PATH --commit` (step 5). No step writes the table any other way.
- **The draft strict-bar-loader spec**: every new read of the table names `interval = '1min'` in its SQL text, not as a bound parameter, so its interval guard passes whichever lands first.
- New code changes zone only through `lib/eastern_time.py`. `tests/meta/test_timezone_boundaries.py` and its baseline stay as they are.

### Site traceability

`site_source_notes` cannot be widened by the implementation PR, so it is declared by a rule.

- File A's rule is one element per changed route or changed table reader the site shows. Here that rule gives nothing: no route changes, no response changes, and no route reads the export module or `read_bars`.
- An empty declaration is not enough, though. `docs/product/03-SITE-TRACEABILITY.md` watches `gcp`, `lib`, `scripts` and `tests` (`docs/DOC_REGISTRY.md:196`), and this file's code is under `gcp` and `tests`. When watched code changes, the docs audit accepts the document only with a snapshot record that verifies (`scripts/maintenance/docs_audit.py:7289-7309`), and a record needs at least one declared own note that was added or changed (`scripts/maintenance/doc_source_snapshot.py:157-161`: with no declared component it raises `no declared source-bound note updates`). Without one the branch audit reports a finding that `main` does not, and the delivery item of `done_when` fails.
- So one element is declared, by a second rule, used only because the first gives nothing: the first Chain row of the document that names the changed producer.
  - The changed producer is the `fetch-alphavantage-intraday` job: its `main()` gains the export.
  - The first Chain row that names that job is DASHBOARD-04 (`docs/product/03-SITE-TRACEABILITY.md:334`), whose bars come from it.

| Changed producer | First Chain row that names it | Declared |
|---|---|---|
| the `fetch-alphavantage-intraday` job (`gcp/fetchers/fetch_alphavantage_intraday.py` `main()`, and the new `gcp/fetchers/export_intraday_bars.py` it calls) | DASHBOARD-04 (`docs/product/03-SITE-TRACEABILITY.md:334`) | DASHBOARD-04 |

So `site_source_notes: [DASHBOARD-04]`.

- The implementation PR writes the `(FEAT-DATA-001, DASHBOARD-04)` row, which does not exist (the table holds FEAT-DATA-001 rows for DASHBOARD-01, LIVE-03 and SHARED-07), and regenerates `docs/review-evidence/site-source-snapshot.json`.
- The note says what the source now does and that DASHBOARD-04's route, its reader and the bars it reads are unchanged. It claims nothing about the site.
- Nothing on the site shows this change, so there is no deployed-site run (AGENTS.md, Browser proof, is for a change a user can see).

### Capacity

Volume, velocity and wall-clock per run, and the task timeout each must fit four times over.

| Run | Volume | Velocity | Wall-clock | Timeout and headroom |
|---|---|---|---|---|
| nightly export | 6 reads of about 20,000 rows of eight columns; 6 files of about 0.6 MB | 6 bars queries, 3 daily queries, 6 uploads, 3 manifest reads and 6 manifest writes | estimated under 30 s; not measured | fetch job, 3,600 s; the first night's `bars export:` line gives the real figure (runbook, step 1) |
| one-time export, one ticker | at most 143 files, about 85 MB | 143 bars queries, 1 daily query, 143 uploads, 1 manifest read and 143 manifest writes when no other run writes it | estimated 3 s a month: about 7 min; not measured | 8 times under 3,600 s |

- Memory. The export holds one ticker-month at a time. Its peak was not measured for this spec; the fetch job has 2Gi, and the implementation's own figure is a `done_when` item (a local run with an in-memory bucket).
- The production plan of the export's bars query is a `done_when` item, read-only through `scripts/db_query_cr.sh`. The daily query is file A's and is measured there.
- Cost, at Cloud Run's job rates of about $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read for this spec):
  - nightly export: about $0.0007 a run, about 2 cents a month over 26 runs;
  - one-time export: about 3 cents in all;
  - storage: about 0.2 GB, under 1 cent a month.
- No new job and no new schedule. Requests to AlphaVantage do not change in number, outside the runbook's refetches.

## Implementation plan: size

8 tasks. The single spec had 16; file A holds the other part.

1. Export: `export_month`, the two queries, the placed rows, the file.
2. Export: the manifest entry (rows, sessions, basis and its states).
3. Export: the bucket object, the first-run create, the generation precondition, the write order.
4. Export: the wiring in `main()` and the log lines.
5. Export: `--export-bars-from`.
6. Export: `read_bars` and the import-isolation test.
7. Site note row, the snapshot, the generated inventories, the catalog record, PR traceability.
8. PR-body measurements.

No `done_when` item of this file repeats one of file A's. Each file carries its own delivery items: the unmodified suites, the PR-body measurements, and the product records. The runbook below is not a plan: it has no code.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box.

### Before the merge

Nothing. This file changes no route and no response, so there is no deployed-site run, and no production step comes before the merge.

### After the merge: the production runbook (every step waits for the owner's own yes)

Each step is for SPY, QQQ and IWM only, starts only on the owner's own yes for that step, read-only ones included, and names the check that proves it. It starts after file A's close-out steps 1 and 2.

**Already done on 2026-11-13, with the owner's yes** (recorded here, not repeated):

- The request change was deployed (sibling spec `2026-11-13-feat-data-001-intraday-as-traded.md`; the deploy evidence is on #1874, not re-read for this revision).
- The missing sessions of November and December 2025 were refilled: SPY and QQQ 2025-11 and 2025-12, IWM 2025-11 (executions `fetch-alphavantage-intraday-dbjxf`, `-7gdpw` and `-4l6pj`). 66,923 new rows; the rows already stored for 2025-11-03 to 11-14 were rewritten in place. No missing session in those months afterwards, and refilled sessions at factor 1.0 (db-query-4m2s4).
- Not recorded: whether anything was recomputed after that refill. Its windows are part of step 7.

**How the runbook is run and recorded**

- **The record.** Each step's execution ids, the lines this text names, and the owner's yes are posted as comments on this file's implementation PR.
- **Lists are `gs://` objects.** `--verify-basis`, `--verify-months` and `--replace-months` read their list with `_read_text` (`gcp/fetchers/fetch_alphavantage_intraday.py:652-661`): a local path or `gs://bucket/object`. The job's image holds no list, so in the job the argument is always a `gs://` object.
  - A list is `TICKER,YYYY-MM` lines, cut from the second field of the scan's MONTH lines.
  - Upload: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud storage cp ./spy-months.csv gs://adept-mountain-474619-d4-trading-data/intraday-lists/spy-months.csv`.
  - Use: `gcloud run jobs execute fetch-alphavantage-intraday --region us-east1 --args="--verify-basis=gs://adept-mountain-474619-d4-trading-data/intraday-lists/spy-months.csv" --wait`. The same form serves `--verify-months=` and `--replace-months=`; a committed replace adds `,--commit`.
  - The `intraday-lists/` prefix has no lifecycle rule (`gcp/deploy.sh:3337-3358`).
- **Scans are listing runs.** Every `--intraday-gap-since` run of the runbook leaves `--strict` out, so it exits 0 when it finishes whatever it lists (file A, Design B). The step reads the lines.
- **Some runs are expected to exit non-zero.** The step says so where it happens. What follows from a non-zero exit:
  - The fetch job has `--max-retries 1` (`gcp/deploy.sh:2217`), so Cloud Run runs the task once more. A read-only check prints its lines twice and takes twice the time. Cloud Run's retry of a failed task is its documented behaviour; it was not checked by a run for this spec.
  - When the second attempt also exits non-zero the execution fails, and the failure notifier posts its Discord message and files, or comments on, the job's `gcp-job-failure` issue (`gcp/failure_notifier.py:1-17`).
  - How that issue is closed: the notifier's hourly reconcile closes a job's open failure issue once that job's latest execution succeeded (`gcp/failure_notifier.py:743-810`; run with stubbed GitHub and Cloud Run on 2026-11-13). For the fetch job that is the next runbook run that exits 0, or the 21:00 ET nightly at the latest. When the issue is filed the operator comments on it with the runbook step and the execution id, so it reads as expected. If it is still open a day later it is closed by hand with that comment.
  - The same reconcile does not know a runbook run from a scheduled one. Before each run, on either job, the operator reads the job's open failure issue, and does not start a run while one is open that the runbook did not cause: a run that exits 0 would let the reconcile close it.
  - The watchdog job has `--max-retries 0` (`gcp/deploy.sh:2535`). The runbook's scans exit 0, so nothing is filed for them.

| Step | Run | Expected exit | Why |
|---|---|---|---|
| 2 | `--intraday-gap-since`, no `--strict` | 0 | a listing run |
| 2 | `--verify-basis` over every stored month | 1 | the adjusted months print BASIS-FAIL |
| 2 | `--verify-months` over every stored month | 1 | the legacy-labelled months print VERIFY-FAIL |
| 3 | plain fetch of the four thin months | 0 | |
| 3 | `--verify-basis` over those four months | 3, or 0 | rows an upsert rewrote in place are not proven, so their sessions print INFERRED |
| 4, 8 | `--export-bars-from` | 0 | |
| 5 | `--replace-months`, dry run | 0, or 1 | 1 when a month's refetch is incomplete |
| 5 | `--replace-months --commit` | 0, or 1 | 1 while any month prints RETRY |
| 6 | `--intraday-gap-since`, no `--strict` | 0 | |
| 6 | `--verify-basis` | 0 | the pass condition |
| 6 | `--verify-months`, for the record | 0, or 1 | 1 when a proven thin session misreads (step 6) |

**The steps**

1. **Deploy** this file's code: `./gcp/deploy.sh fetchers`, which rebuilds the image and redeploys every fetcher job as `gcp/deploy.sh` declares it (`deploy_fetchers`, `gcp/deploy.sh:3207`). The nightly bucket write starts with this deploy, so the owner's yes to the deploy is the yes to those writes.
   - The API needs no step and does not change.
   - Check, after the first weekday `av-intraday-nightly` on the new image: the job has `GCS_BUCKET` set; six files and three manifests exist, the manifests created by that run; each current-month entry lists that evening's session under `not_measured` as `no_daily_row`, and each entry's state is recorded; and the `bars export:` line gives the seconds the export took.
2. **Regenerate the lists with the deployed checks**, read-only, before any write.
   - Premise of file A's Design F: one read-only query counts SPY, QQQ and IWM rows with `inserted_at` on or after 2026-09-28 00:00 UTC, `ts` before it, and a UTC clock time from 04:00 up to that date's true-UTC start (08:00 under EDT, 09:00 under EST). Such a row could only be a label. The count must be 0. Its run time is not measured (`inserted_at` has no index); it goes through `scripts/db_query_cr.sh` with `--timeout 600`.
   - `--intraday-gap-since=2015-01-01`, one execution per ticker. Then `--verify-basis` and `--verify-months` over each ticker's MONTH lines. Both are expected to exit 1 here (table above).
   - Their output replaces the tables in file A's Problem: the THIN and UNDETERMINED sessions with their counts, the months each check fails, the months that hold a row not proven, the sessions UNMEASURED with their reasons, and SPY's months before 2022-02-24, which were never checked. The owner's yes to steps 3 and 5 names scopes from this output.
   - Sessions UNMEASURED as `daily_from_intraday` or `daily_source_unknown` are recorded by count and range. Their basis cannot be checked against the daily table. Re-pulling those daily rows from the daily endpoint would make them measurable; it is a change to the daily table, it is not a step of this runbook, and it is put to the owner with the counts.
3. **Refetch the thin months of 2025** with the plain fetch (`--start-date`, `--end-date`, `--force`), which upserts: SPY 2025-04, 2025-05 and 2025-06, and QQQ 2025-01.
   - AlphaVantage was reported to return 20,172, 20,160, 19,195 and 19,188 rows for them, against 16,917, 14,133, 16,222 and 17,320 stored. No execution id or saved response for those counts is on record: not checked. The fetch's own log gives the counts when it runs (`YYYY-MM: N bars`, `gcp/fetchers/fetch_alphavantage_intraday.py:313`), and the first check below uses those.
   - The refetch also puts these four months on the as-traded basis.
   - Why an upsert is enough here: these months were reported to hold no legacy Eastern-labelled row, so every stored row is rewritten by the row AlphaVantage returns for the same minute. That report has no execution id on record: not checked. The step does not rest on it. The first check below fails for a month that holds a row the fetch did not write, and such a month goes to step 5's list.
   - Why this does not wait for #1190: nothing without a recompute path exists in these windows. Read from production on 2026-11-13 (db-query-q9m9t): `signal_alerts`, `premarket_analysis` and `historical_signals` hold no row for these tickers there, and no `market_data_daily` row there has a premarket field. `intraday_flow_15m` and `intraday_gex_15m` hold 3,233 rows each for SPY 2025-04 to 06 and 1,160 each for QQQ 2025-01.
   - Check, in three parts. Rows an upsert rewrites in place keep their old `inserted_at`, so the tools alone may call a rewritten session UNDETERMINED or INFERRED; the first part is what settles the reading.
     - Each month's stored row count over its month window equals the count the fetch logged for it. The fetch's keys are then the month's keys, so every stored row was written by this run: true UTC, and as traded.
     - With that established, one read-only query over the months written (the form of db-query-tvjtp, with a count added) shows for every session at least 90% of its regular-hours minutes and a 1-min regular-hours high and low within 3 bp of the daily table's.
     - `--verify-basis` over the months written prints no BASIS-FAIL and no EMPTY line. It is expected to exit 3 with INFERRED lines (table above).
4. **Write the history to the bucket, first time**: `--export-bars-from=2015-01`, one execution per ticker.
   - The adjusted months are exported as they are: each entry says `adjusted` with its factor range, or `inferred`, and `inferred_rows` says how many instants rest on the resolver.
   - Check: every MONTH line of step 2's scan, regenerated after step 3, has a manifest entry and a file whose row count and `sha256` match it.
5. **Rewrite as traded every month that holds a row not proven true UTC** (decision 1), not only the months a check fails.
   - List: every MONTH line of the scan, regenerated after step 3, with `unproven_rows` above 0, and any other month for which a check prints a failing line (BASIS-FAIL, VERIFY-FAIL, or a THIN or UNDETERMINED session). A legacy-labelled row is never proven, so every month that holds one is in it. It holds the four months of step 3, IWM 2025-12, the months the refill left with rows rewritten in place (2025-11), and the months that pass every check today.
   - Size: at most 421 ticker-months (three tickers times the 141 months from 2015-01 to 2026-09, less SPY and QQQ 2025-12, which the refill wrote whole; SPY's first stored month is not known, so it is counted from 2015-01). The row count is not measured; at least 4,645,371 rows sit in the months counted as adjusted. The scan's MONTH lines give both numbers, and the owner's yes names them.
   - Mechanism: `--replace-months --commit`, one transaction per ticker-month, which deletes the month and inserts the as-traded refetch. A plain upsert is not enough in general: it leaves any legacy Eastern-labelled row in place.
   - With file A deployed, the replace also clears the month's rows in the six `strat_features_levels_*` tables (file A, Design G). Step 7 rebuilds them.
   - What the replace does not do: it re-inserts only the sessions the month already holds (`replace_month`, `gcp/fetchers/fetch_alphavantage_intraday.py:618`) and skips a month that holds none (`REPLACE_NOTHING_HELD`). So it repairs a thin session the vendor serves whole and never adds a missing one. Step 6 covers that.
   - Sizing, before the committed run: a dry run (no `--commit`) over the whole list shows every month's refetch is complete. Then one month is replaced with `--commit` and its seconds are read from the log. No committed replace has run yet, so its wall-clock is not measured. The rest runs as list chunks sized so each execution stays under a quarter of the job's 3,600 s.
   - A run that exits 1 is run once more by Cloud Run over the same list (read from `run_replace_months`, `gcp/fetchers/fetch_alphavantage_intraday.py:677-760`; not run). On a committed run the months that already reached `replaced` are then replaced again from a new refetch, which writes the same sessions and spends the vendor calls twice. Small chunks keep that cheap.
   - Every listed month must reach `replaced`. A `RETRY` line is run again. A month refused twice as `incomplete_refetch` is recorded with the counts the run printed; the runbook stays open on it and the owner decides.
   - Gate: CLAUDE.md 3.9 holds `--replace-months --commit` until #1190 lands, because two result tables have no recompute path. This rewrite is the same run as that migration: one refetch per ticker-month fixes its timestamps and its basis. It does not start before #1190 allows it.
   - What the site shows meanwhile: a replaced month has no feature and no level rows until step 7 rebuilds them. The movement statement and the strat-engine admin view read those tables (DASHBOARD-21, ADMIN-08). The owner's yes covers that window.
   - Check: every listed month printed `replaced`.
6. **Scan again, fill what the replace could not, and confirm.**
   - `--intraday-gap-since` from the ticker's first stored date, one execution per ticker. Every row of a replaced month is proven, so each line is exact.
   - Each MISSING session it lists is filled with the plain fetch of its month, as in step 3. The month is already as traded and true UTC, so the upsert adds the session's rows and rewrites the others with the same values. Then the scan runs again.
   - **Sessions the vendor does not serve whole.** Two kinds can remain, and each is recorded by name for the owner to accept:
     - vendor-thin: a THIN session, `exact=yes`, in a month that reached `replaced` in step 5, or whose stored row count equals the count a plain fetch logged for it. Its rows are what the vendor returned.
     - vendor-missing: a MISSING session, `exact=yes`, that is still MISSING after this step's plain fetch of its month, whose log gives the month's bar count. The vendor returned no regular-hours bar for that date.
     - The record holds one line for each, written by the operator from the scan's line and the fetch's log: `ACCEPTED-GAP TICKER YYYY-MM-DD THIN N of M` or `ACCEPTED-GAP TICKER YYYY-MM-DD MISSING`, with the execution id that shows it. This is where the thin months of 2024 and 2021-04-12 are settled: repaired, or accepted.
     - The owner accepts the list by name. A session the owner does not accept keeps the runbook open.
   - **The pass condition.** For each of SPY, QQQ and IWM, two runs both exit 0 and their lines read as follows:
     1. `--intraday-gap-since` from the ticker's first stored date, without `--strict`: the summary line is printed; every MONTH line has `unproven_rows=0`; no SESSION-GAP line is UNDETERMINED or has `exact=no`; and the SESSION-GAP lines are exactly the sessions of the accepted record.
     2. `--verify-basis` over that scan's MONTH lines: exit 0, which means no BASIS-FAIL, no EMPTY, no INFERRED, and no line that rests on a row that is not proven. Its INCOMPLETE lines count, month by month, the sessions of the accepted record and no other. Its UNMEASURED lines, with their reasons, and each ODD line are copied into the record.
   - That is the whole condition. The convention criterion is `unproven_rows=0` on every MONTH line: every stored row is then proven true UTC.
   - A BASIS-FAIL line that remains after the rewrite is as-traded bars that disagree with a daily-endpoint row on both sides. No step of this runbook changes it. It keeps the condition unmet and is put to the owner with its line.
   - **`--verify-months` is not part of it.** It runs proven rows through the resolver, so a correct true-UTC month can fail. Run on 2026-11-13 through the real `verify_month`: a month of true-UTC rows in which one Monday session is stored 04:00 to 13:29 ET with flat volume returns `legacy` with `label_rows=570`; with an opening volume spike, or on a Tuesday whose UTC date also holds Monday's 20:00 ET bar, it returns `clean`. It is run once over the same list for the record. A VERIFY-FAIL month whose MONTH line has `unproven_rows=0` is accepted and listed. Its exit is then 1, which is expected (table above).
7. **Recompute what reads these bars**, over every session written by the 2026-11-13 refill and by steps 3, 5 and 6. The plain fetch prints no REBUILD or REPLACED line, so its windows are named here.
   - `strat_features_*`: a full-history rebuild, `strat_data_builder --rebuild --start-date=2016-01-01` on the `strat-engine` job, never a rebuild from a window's start. A rebuild loads no bar before its start date (`gcp/research/strat_engine/strat_data_builder.py:695`), so RSI, MACD and EMA-200 would be recomputed without warmup.
     - Memory: the run needs the job raised to 32Gi and set back afterwards (`gcp/deploy.sh:1696-1706`, and again at `:1724-1728`). That job change is part of the owner's yes.
     - It is set back to 16Gi, not 8Gi. The job is declared at 16Gi (`gcp/deploy.sh:1733` and `:1743`; the comment at `:1693-1696` says 16Gi matches the live job, raised from 8Gi after the daily run outgrew it), and it ran at 16Gi in both live snapshots (`tests/fixtures/live_gcp_snapshot_2026-09-07.json` and `tests/fixtures/live_gcp_snapshot_2026-11-09.json`, `"memory": "16Gi"`). The last line of the two command blocks in that file's comments still says `--memory 8Gi` (`gcp/deploy.sh:1706`, `gcp/deploy.sh:1728`). That line is stale and is not followed: 8Gi would halve the daily run's memory.
     - The run plan reads the job's live memory first and sets it back to what it read. If that is not 16Gi the difference is put to the owner.
     - The stale comment is in `gcp/deploy.sh`, which this spec does not edit. It is reported for FEAT-DEPLOY-001.
     - The job's task timeout is 5,400 s and the duration of a full rebuild was not measured: the run plan takes it from the job's last full rebuild before starting, and splits the run with `--tickers` and `--tf-only` if it does not fit four times.
   - `strat_features_levels_*` (file A, Design G), after the feature rebuild: `strat_enrich_levels --mode=backfill-all` on the `strat-engine` job, the run `strat-enrich-daily` makes at 02:00 ET Tuesday to Saturday (`gcp/deploy.sh:4537`). Its exit code proves nothing: `backfill-all` logs a failed ticker and timeframe and goes on (`gcp/research/strat_engine/strat_enrich_levels.py:241-248`). `computed_at` is not changed by its upsert (`:187`), so it cannot show a recompute either.
   - `realtime_gex_15m`: `build-realtime-gex --backfill --restart`, which recomputes from 2026-05-23, the table's first day.
   - `intraday_flow_15m` and `intraday_gex_15m`: no deployed job writes them (`docs/audits/2026-08-27-claude-codebase-review/09-dormant-surfaces.md` records them as last written on 2026-06-05). `--backfill` resumes after the last bucket and skips an old hole (`build_intraday_flow._resume_since`); `--backfill --restart` recomputes the whole history. The replace deletes their rows for a replaced month. The record lists them as stale, or the owner asks for a manual `--backfill --restart`.
   - `premarket_analysis` outcomes: the playbook resolver, per session and ticker (`PLAYBOOK_RESOLVE_DATE`, `PLAYBOOK_RESOLVE_FORCE`).
   - `historical_signals`: full regeneration per ticker.
   - Premarket fields of `market_data_daily` and `signal_alerts` exits: no path today (#1190).
   - Levels and ATR of the brief and the planner come from the daily table, which the rewrite does not touch, so they do not change. This is not true of the `strat_features_levels_*` tables.
   - `ticker_level_params`: its premarket thresholds are calibrated from 1-min premarket bars (`gcp/calibrate_level_params.py:250`). On 2026-11-09 production held no such table (`tests/fixtures/live_gcp_snapshot_2026-11-09.json`), and the module is not in `gcp/deploy.sh`. The runbook reads whether the table now holds rows for the three tickers. If none, that is recorded. If some, the calibration is rerun over every `effective_from` they span (`--history FIRST LAST --tickers SPY,QQQ,IWM`).
   - Check:
     - `strat_features_*`: the rebuild's log shows it loaded bars from 2016-01-01 and finished, and in every window of the union no row past its timeframe's first 200 bars has a NULL `ema_200`.
     - `strat_features_levels_*`: the run's log has an `upserted N rows` line for each of the 18 ticker and timeframe pairs and no `failed` line; each N equals the count of `strat_features_{tf}` rows with a non-NULL `strat_candle` for that ticker; and for the three tickers no level row lacks a feature row at its key and no such feature row lacks a level row (two counts per timeframe, both 0).
     - `ticker_level_params`: no row for the three tickers has a `calibrated_at` earlier than the end of step 6, or the record that the table holds none.
     - The `build-realtime-gex` run is recorded where a window reaches 2026-05-23; `intraday_flow_15m` and `intraday_gex_15m` are recorded as rebuilt by hand or as stale, per window; and each of the replace's RECOMPUTE lines is answered with the command run or the issue that tracks the missing path.
8. **Write the history to the bucket, second time**: `--export-bars-from=2015-01`, one execution per ticker, after step 6 has passed.
   - Check: every MONTH line of step 6's scan has a manifest entry, and a file whose row count and `sha256` match it; `inferred_rows` is 0 in every entry; no entry is `adjusted` or `inferred`; and every entry is `as_traded`, or is `partial` or `unmeasured` with nothing under `not_measured` but the sessions the record already holds: those with no measurable daily row (the UNMEASURED lines of step 6), the accepted vendor-thin and vendor-missing sessions, and the recorded ODD ones.

**After the runbook**: the DASHBOARD-04 note of `docs/product/03-SITE-TRACEABILITY.md` and the plan's status are brought to the deployed state on a `docs/` branch.

## Decisions the owner can overrule

Decided, and written into the text above:

1. **The rewrite covers every SPY, QQQ and IWM month that holds a row not proven true UTC** (step 5), not only the months a check fails. After it the final checks rest on no inference.
2. **Two specs in one PR.** File A holds the checks; this file the bucket copy and the runbook. This file's plan opens after file A's implementation is on `main`.
3. **A session the vendor does not serve whole is recorded by name and accepted by the owner** (step 6), vendor-missing the same way as vendor-thin.
4. **After the rewrite the convention criterion is `unproven_rows=0`.** A VERIFY-FAIL month whose rows are all proven is accepted and listed.
5. **The manifest is created with `if_generation_match=0`** when it does not exist.
6. **The runbook's end state is reached with exit 0**: the two runs of step 6's pass condition.

Design calls made in this text:

7. The export is triggered by the nightly's argument shape, so `gcp/deploy.sh` stays untouched.
8. `site_source_notes: [DASHBOARD-04]`. The rule that fits file A gives nothing here, and the docs audit needs one declared note for any change under `gcp` or `tests`.
9. The manifest is written after each month's file, in the nightly too. It costs three more manifest writes a night and keeps a failed upload from leaving another month unreadable.
10. The manifest has an `inferred` state and an `inferred` count, so a month never reads `as_traded` on rows that are not proven.
11. The history goes to the bucket twice: before the rewrite, with the adjusted months named as such (step 4), and after it (step 8). The first copy is useful while the rewrite waits for #1190.
12. A `--replace-months` or check run that is expected to exit non-zero is left to file its issue, which the operator annotates. No flag is added to silence it.
13. Re-pulling daily rows that did not come from the daily endpoint is left out of the runbook and put to the owner with step 2's counts.
14. `req_ids` holds REQ-CAP-001, REQ-DATA-001 and REQ-DATA-003. REQ-FRESH-001 goes with file A's alarm.

## Risks

- Until step 5 runs, the table keeps its mixed months and the bucket copy carries them, named `adjusted` or `inferred` in the manifest.
- A session reads a stale bucket copy. The manifest's `last_ts` and `exported_at` say how fresh each month is, and a failed nightly write fails the job.
- A month can be unreadable for a day: its file was uploaded and its manifest write failed, or a reader copied the folder between the two writes. `read_bars` refuses it by hash and names it; the next export of that month heals it. For a month older than the nightly's two, that is a rerun of `--export-bars-from`.
- Two exports of one month at once can leave a manifest entry that describes the other run's file. `read_bars` refuses it by hash and the next export heals it.
- A whole session stored both ways with flat volume and the label copy on the shared keys is exported on the wrong minutes, flagged only by `inferred_rows` (file A, Design F). It can only exist in a month that holds unproven rows, and step 5 rewrites every such month. Until then a reader of a month with `inferred_rows` above 0 is reading resolver placement.
- A replaced month has no feature or level rows until step 7. The owner's yes to step 5 covers it.
- Expected non-zero exits file real issues and post to Discord. The operator annotates each one. A reader of the issue list who has not seen the annotation may take it for an outage.
- The reconcile that closes failure issues cannot tell a runbook run from a nightly: a run that exits 0 can close the issue of a real failure. The operator checks the job's open issue before each run.
- After the runbook, a full-history scan with `--strict` still exits 1 on the accepted sessions. The accepted record is the list to compare it with. No accepted-sessions input to the scan is specified here.
- Some sessions' basis is never checked: those with no daily row (IWM and QQQ 2015-01 to 2016-04 today) and those whose daily row did not come from the daily endpoint. Step 5 writes them from an `adjusted=false` refetch like every other session, so their bars are as traded by construction; only the cross-check against the daily table is missing. Step 2 counts them.
- The proof by insert time rests on no writer having stored a label since 2026-09-28. Step 2's first query tests it on production before anything depends on it. A hand-run write that bypassed the repo's helpers would not show there if it held regular-hours rows only.
- A reader that relied on adjusted intraday prices. None found: readers compare intraday bars with live, daily and strike prices.
- The runbook's order depends on #1190 for step 5. If #1190 is late, steps 1 to 4 still give the durable copy, with its adjusted months named.
