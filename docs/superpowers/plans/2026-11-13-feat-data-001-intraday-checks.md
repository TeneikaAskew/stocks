---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-13-feat-data-001-intraday-gaps-basis-copy.md
branch: feature/feat-data-001-intraday-checks
pr: null
status: ready
---

# market_data_intraday checks (session gap alarm, basis check, workflow test, levels tables in the clear list): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances. done_when items are numbered from 0 in the spec's order, [0] to [12].

**Goal:** The freshness watchdog reports a 1-min session of SPY, QQQ or IWM that is missing or thin, an on-demand scan lists such sessions over history, a read-only basis check says which stored months are not as traded, a test keeps `continue-on-error` out of every workflow, and a replaced month clears its six levels tables.

**Architecture:** Three pure functions in `lib/eastern_time.py` read a stored session without trusting an inferred timestamp convention: a row counts as a true instant only when it is proven by its date or its insert time, and a session whose count depends on the convention is UNDETERMINED. `scripts/audit_data_freshness.py` calls them from a scan inside `audit_all()` and from `--intraday-gap-since`; `gcp/fetchers/fetch_alphavantage_intraday.py` calls them from `--verify-basis`. Every read goes through `gcp.database.query_to_dataframe_strict`, so a failed read raises and is never an empty result.

**Tech Stack:** Python, pandas, numpy, the NYSE calendar through `lib/eastern_time.py` only, SQLAlchemy with pg8000 through `gcp.database`, argparse, PyYAML, pytest, FastAPI `TestClient`.

**Spec:** docs/superpowers/specs/2026-11-13-feat-data-001-intraday-gaps-basis-copy.md

## Global Constraints

- Base: `origin/main` at 39ce5d57 or later. The spec's code references are to c698b24e; `git diff c698b24e 39ce5d57` is empty for `lib/eastern_time.py`, `scripts/audit_data_freshness.py`, `gcp/fetchers/`, `gcp/database.py`, `platform/api`, `gcp/deploy.sh`, `.github` and `tests/audits` (run 2026-11-14), so its line numbers hold for the code this plan touches. Branch `feature/feat-data-001-intraday-checks`. Commit this plan file first, alone: `docs(plan): FEAT-DATA-001 implementation plan for the intraday checks`. The site-note producer of Task 12 refuses a branch with no committed plan.
- Other lanes. PR #1891 (FEAT-REPLAY-001) adds `replay_probe_window` to `lib/eastern_time.py` right after `stored_intraday_to_eastern`, re-renders the three generated inventory docs, and edits `docs/product/02`, `12` and (in its close task) `03` and the snapshot. If it has merged, rebase on `main` before Task 2; if it merges later, rebase before Task 12. The watched-ticker ingest (spec `2026-11-14-feat-data-001-watched-ticker-ingest-v2.md`) will add a heartbeat check to `scripts/audit_data_freshness.py` and also declares SHARED-07; if its implementation is on `main`, rebase before Task 4 and read Task 12's note step against the row as it then is.
- Scope: SPY, QQQ and IWM only. Read-only: no write to any table, no new writer of `market_data_intraday`, no vendor call, no trading cost. No file this plan adds, and no code it adds to an existing file, spells a write statement or a write-helper call on `market_data_intraday`, docstrings included.
- Not in the PR's diff: `gcp/deploy.sh`, `platform/api` (so `platform/api/openapi.json`), `CLAUDE.md`, `.github/pull_request_template.md`, any workflow file, `tests/fixtures/timezone_boundary_baseline.json`, and these tests: `tests/gcp/test_evaluate_ew_strikes.py`, `test_intraday_as_traded.py`, `test_intraday_replace_months.py`, `test_intraday_writers_utc.py`, `test_av_intraday_universe.py`, `tests/audits/test_audit_data_freshness.py`, `tests/api/test_route_coverage.py`, `test_admin_users_datasources.py`, `test_platform_api.py`, `tests/meta/test_production_writers.py`, `test_timezone_boundaries.py`.
- Not changed: `stored_intraday_to_eastern` and every reader that uses it (`_held_session_dates`, `verify_month`, the Charts API), `_query_gap_scan`, the audit's logging level (`scripts/audit_data_freshness.py:1572`), the `settle_hour_et` 21 and `settle_lag_days` 1 of the `market_data_intraday` check, any schedule or job setting.
- Reads: every new read is `gcp.database.query_to_dataframe_strict(sql, params, timeout_s=120)` and holds `interval = '1min'` in the SQL text, not as a parameter. No `try` around a read or around `session_minute_readings`. Exact SQL, copied from the spec:
  - Q1 `SELECT ts, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end`
  - Q2 `SELECT min(ts) AS first_ts FROM market_data_intraday WHERE ticker = :t AND interval = '1min'`
  - Q3 `SELECT ts, high, low, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end`
  - Q4 `SELECT date, high, low, data_source FROM market_data_daily WHERE ticker = :t AND date >= :first AND date <= :last`
- Rules, copied from the spec:
  - Proven: a row's UTC date is `TRUE_UTC_FROM` (2026-09-28) or later, or its `inserted_at` is `TRUE_UTC_INSERTED_FROM` (2026-09-28 00:00 UTC) or later.
  - Regular hours: from the session's `market_open` to before its `market_close`, as the schedule frame gives them. Expected minutes: 390, or 210 on a half day.
  - A count is MISSING at 0, THIN when `10 * count < 9 * expected` (351 of 390 is whole, 350 is thin; 189 of 210 is whole, 188 is thin), else OK. A session's status is that class when its three counts agree and UNDETERMINED otherwise.
  - Basis: `f_high` and `f_low` rounded to 5 decimals and compared in units of 0.00001. Both from 0.99970 to 1.00030 inclusive: AS-TRADED when the session is exact, INFERRED when it is not. Both below 0.99970 or both above 1.00030: ADJUSTED. Anything else: ODD. The session factor is the mean of the two, rounded to 5 decimals.
  - `TRUE_DAILY_SOURCES = ("alphavantage_daily", "av_daily_backfill", "av_watched_backfill")`.
- Exact strings, copied from the spec. `{T}` is the ticker, dates are ISO, factors have 5 decimals.
  - Row: table `market_data_intraday [sessions]`, status `stale`, `writer_job` `fetch-alphavantage-intraday`.
  - D1 `MISSING: 0 of {expected} regular-hours minutes`
  - D2 `THIN: {count} of {expected} regular-hours minutes`
  - D3 `UNDETERMINED: {true_utc} as true UTC, {eastern_label} as Eastern labels, {both} as both, of {expected}`
  - G1 `SESSION-GAP {T} {date} {STATUS} true_utc={N} eastern_label={N} both={N} expected={N} exact={yes|no}`
  - G2 `MONTH {T},{YYYY-MM} rows={N} unproven_rows={N}`
  - G3 `NO-ROWS {T}`
  - G4 a last line that starts `intraday-gap-since summary:` and holds `seconds={N}`
  - B1 `BASIS-FAIL {T} {YYYY-MM} sessions={N} {first}..{last} factor={MIN}..{MAX} inferred={N}`
  - B2 `EMPTY {T} {YYYY-MM}`
  - B3 `UNMEASURED {T} {YYYY-MM} sessions={N} {first}..{last} no_daily_row={N} daily_from_intraday={N} daily_source_unknown={N} daily_not_positive={N} no_rth_high_low={N}`
  - B4 `INCOMPLETE {T} {YYYY-MM} sessions={N} {first}..{last} inexact={N}`
  - B5 `INFERRED {T} {YYYY-MM} sessions={N} {first}..{last}`
  - B6 `ODD {T} {date} high={F} low={F} exact={yes|no}`
  - B7 a last line that starts `verify-basis summary:`
  - README line: ``- No `continue-on-error` on any step or job, other than an explicit `false` (CLAUDE.md Rule 3.7; `tests/meta/test_workflows_no_continue_on_error.py`).``
- Choices this plan makes where the spec leaves one open (each is reported to the owner with the plan):
  - `session_minute_readings` returns `list[SessionReading]`, a `NamedTuple`; `place_stored_rows` returns `(instants, keep, proven)`.
  - The proof rule is one public function, `proven_true_utc`, because G2 needs a per-row count outside the two reading functions. The spec counts three new functions; this is a fourth.
  - D2 names the lowest of the three counts, the same number `row_count_recent` carries.
  - The part of G4 after its prefix is `{T} first={date|none} sessions={N} ok={N} missing={N} thin={N} undetermined={N}` per ticker, joined by `; `, then `; seconds={N.N}`. The part of B7 after its prefix is `months={N} as_traded={N} inferred={N} adjusted={N} odd={N} unmeasured={N} incomplete={N} empty={N}` (sessions per kind; months and empty months counted as months).
  - G1 to G4 and B1 to B7 are written with `print`. `--verify-basis` ignores Cloud Run task striping and `--limit`: the list is at most 3 tickers by 143 months.
- Time (CLAUDE.md 3.9): a zone changes only through `lib/eastern_time.py`. `tests/meta/test_timezone_boundaries.py` scans `lib/`, `gcp/` and `scripts/` and fails on a new `.tz_localize(None)`, `.replace(tzinfo=None)`, `to_datetime(..., utc=True)`, `datetime.now()` with no zone, or `DATE(col)` / `ts::date` in SQL text. Where the new code in `lib/eastern_time.py` must drop a zone to read a raw clock label, the line carries `# tz-ok: <reason>`, as `:251` and `:253` do. Do not reword `date.today()` in `fetch_alphavantage_intraday.main` or the three `.replace(tzinfo=None)` expressions the baseline lists for the audit.
- **The render step.** A task that changes a file under `gcp/`, `lib/` or `scripts/` ends with it, because the generated inventory cites line numbers (39 citations into `scripts/audit_data_freshness.py`, 5 into `fetch_alphavantage_intraday.py`):
  `python3 -m scripts.maintenance.doc_inventory --snapshot tests/fixtures/live_gcp_snapshot_2026-09-07.json --restore docs/product/infrastructure/05-a-ARCHITECTURE.md docs/product/infrastructure/05-c-DATA_DEPENDENCIES.md docs/product/infrastructure/05-e-API.md`
  then `python3 -m pytest tests/scripts/test_check_generated_docs.py::test_committed_docs_pass_every_gate -q` (expect 1 passed; each takes about 35 s), then stage whichever of the three docs changed in the same commit as the code. Nothing else in those docs is edited.
- Commits: run `python3 scripts/gate/spec_gate.py --commit` first. Conventional message, imperative, 72 characters or fewer. No AI attribution of any kind: no co-author line, no "generated by", no emoji.
- Tests go in the files named, one folder per area, never at the `tests/` root. Whole suite: `make test`.
- A claim in a doc or on the PR about what the code does comes from output that was run (CLAUDE.md 3.11.1).

## done_when map

| done_when | What | Task |
|---|---|---|
| [0] | proof rule, `session_minute_readings`, `intraday_month_window` | 2 |
| [1] | `place_stored_rows` | 3 |
| [2] | the scheduled scan | 4 |
| [3] | what a scheduled run prints | 4 |
| [4] | `--intraday-gap-since` | 5 |
| [5] | the API test of the two routes | 6 |
| [6] | `session_basis_verdicts` | 7 |
| [7] | `--verify-basis` | 8 |
| [8] | six levels tables in the clear list | 9 |
| [9] | workflow test and README line | 10 |
| [10] | `make test`, files left unmodified | 11 |
| [11] | PR-body measurements | 1 (production), 5 (memory), posted in 12 |
| [12] | product record, site notes, snapshot, inventory, audit, gate | 12 |

## Review Focus

Inputs the spec implies and no done_when test pins. Each has a test in the task that owns the code.

- `market_data_daily.date` read back as a `pd.Timestamp` or `datetime` and not a `date` (pandas does this for a DATE column; the audit met it, `scripts/audit_data_freshness.py:824-834`): the session still finds its daily row and is never `no_daily_row`. Task 7.
- `--verify-basis` over the current month: a session whose close has not passed is not read at all, so it is neither INCOMPLETE nor counted. Task 8.
- A half day among the scheduled scan's five sessions (2026-11-27): 188 minutes read `THIN: 188 of 210 regular-hours minutes` and 189 add no row; and a reading that is UNDETERMINED gets D3 with the lowest count in `row_count_recent`. Task 4.
- `--intraday-gap-since` on a weekend or holiday (2026-10-31): the scan starts at the next session and is not a usage error. `--intraday-gap-tickers " spy, qqq "` runs SPY and QQQ. `--intraday-gap-tickers` without `--intraday-gap-since` is a usage error. Task 5.
- `inserted_at` that is NULL (NaT) or naive, and two rows inside one minute: NaT is never proof, a naive value is read as UTC as `ts` is, and two rows in one minute count as one minute. Task 2.
- `continue-on-error: no` or `off`: PyYAML reads both as the boolean false, so the spec's rule accepts them. The test pins that, so the gap is visible instead of assumed. Task 10.

## File map

| File | Change | Task |
|---|---|---|
| `lib/eastern_time.py` | `TRUE_UTC_INSERTED_FROM`, `proven_true_utc`, `SessionReading`, `session_minute_readings`, `intraday_month_window`, `place_stored_rows` | 2, 3 |
| `gcp/fetchers/fetch_alphavantage_intraday.py` | `month_replace_window` returns `intraday_month_window`; `TRUE_DAILY_SOURCES`, `session_basis_verdicts`; `run_verify_basis`, `--verify-basis`; six names in `DERIVED_TS_TABLES` | 2, 7, 8, 9 |
| `scripts/audit_data_freshness.py` | `session_gap_days` in `CHECKS`, the scan and its row, `run_intraday_gap_since`, two flags | 4, 5 |
| `tests/fixtures/intraday_checks.py` | new: row builders and the audit reader stubs | 2, 3, 4 |
| `tests/lib/test_intraday_session_readings.py` | new | 2, 3 |
| `tests/audits/test_audit_intraday_session_gaps.py` | new | 4, 5 |
| `tests/api/test_health_freshness_session_gaps.py` | new | 6 |
| `tests/gcp/test_intraday_verify_basis.py` | new | 7, 8 |
| `tests/gcp/test_intraday_replace_levels_tables.py` | new | 9 |
| `tests/meta/test_workflows_no_continue_on_error.py`, `.github/workflows/README.md` | new test; line 38 reworded | 10 |
| `docs/product/infrastructure/05-a`, `05-c`, `05-e` | inventory blocks, by the render step | 2 to 9, 11 |
| `docs/product/02`, `03`, `12`, `docs/review-evidence/site-source-snapshot.json` | close | 12 |

## Task 1: Measure the five queries in production

Spec: Capacity; Done when (the PR-body measurements). Advances done_when[11] (production half). Needs: nothing. Run it before any code: the SQL is fixed by the spec, and a query plan that reads more rows than it returns means the design is wrong. Read-only, no `--commit`.

- [ ] Find the five settled sessions of the day: `python3 -c "from datetime import datetime, UTC; from scripts.audit_data_freshness import _recent_trading_days as r; print(r(datetime.now(UTC).replace(tzinfo=None), 5, settle_hour_et=21, settle_lag_days=1))"`. The literals below are for 2026-11-05 to 2026-11-11 (the list at 2026-11-13 15:00 UTC). On another day replace `2026-11-05` by the oldest of the five and `2026-11-12` by the day after the newest, in the first and the sixth statement.
- [ ] Run:

```bash
env -u CLOUDSDK_AUTH_ACCESS_TOKEN ./scripts/db_query_cr.sh -q "EXPLAIN (ANALYZE, BUFFERS) SELECT ts, inserted_at FROM market_data_intraday WHERE ticker = 'SPY' AND interval = '1min' AND ts >= TIMESTAMPTZ '2026-11-05 02:00:00+00' AND ts < TIMESTAMPTZ '2026-11-12 02:00:00+00'; EXPLAIN (ANALYZE, BUFFERS) SELECT ts, inserted_at FROM market_data_intraday WHERE ticker = 'SPY' AND interval = '1min' AND ts >= TIMESTAMPTZ '2025-05-01 02:00:00+00' AND ts < TIMESTAMPTZ '2025-06-01 02:00:00+00'; EXPLAIN (ANALYZE, BUFFERS) SELECT ts, high, low, volume, inserted_at FROM market_data_intraday WHERE ticker = 'SPY' AND interval = '1min' AND ts >= TIMESTAMPTZ '2025-05-01 02:00:00+00' AND ts < TIMESTAMPTZ '2025-06-01 02:00:00+00'; EXPLAIN (ANALYZE, BUFFERS) SELECT min(ts) AS first_ts FROM market_data_intraday WHERE ticker = 'SPY' AND interval = '1min'; EXPLAIN (ANALYZE, BUFFERS) SELECT date, high, low, data_source FROM market_data_daily WHERE ticker = 'SPY' AND date >= DATE '2025-05-01' AND date <= DATE '2025-05-31'; SELECT ticker, (ts AT TIME ZONE 'America/New_York')::date AS session, count(DISTINCT date_trunc('minute', ts)) AS rth_minutes FROM market_data_intraday WHERE ticker IN ('SPY','QQQ','IWM') AND interval = '1min' AND ts >= TIMESTAMPTZ '2026-11-05 02:00:00+00' AND ts < TIMESTAMPTZ '2026-11-12 02:00:00+00' AND (ts AT TIME ZONE 'America/New_York')::time >= TIME '09:30' AND (ts AT TIME ZONE 'America/New_York')::time < TIME '16:00' GROUP BY 1, 2 ORDER BY 1, 2; SELECT ticker, data_source, count(*) AS n, min(date) AS first_date, max(date) AS last_date FROM market_data_daily WHERE ticker IN ('SPY','QQQ','IWM') GROUP BY ticker, data_source ORDER BY ticker, data_source"
```

- [ ] Pass means: in each of the first, second, third and fifth plans, every scan node's actual `rows=` equals the rows the statement returns, with no `Rows Removed by Filter` above 0 and no `Seq Scan`; the bar plans touch one partition, `market_data_intraday_spy`. The fourth plan (the probe) reads at most 10 rows on every scan node. On a fail, stop and report to the owner; do not start Task 2.
- [ ] The sixth statement gives the regular-hours minute count of each of the five sessions per ticker (15 rows when none is missing; 390 expected, or 210 on a half day, where the count to 16:00 also holds post-close bars). Its dates are all from `TRUE_UTC_FROM` on, where every row is a true instant, so the named-zone conversion is right. The seventh gives the daily rows per ticker and `data_source`, NULL as its own row. Note which sessions are under 351: those are the rows the first deployed run will print.
- [ ] Save the five plans, each execution time, both result sets and the execution id the script prints. They go on the PR in Task 12.

## Task 2: The proof rule, the session readings and the month window

Spec: Design F ("What is added", "What it gives"); Design B (the month window). Advances done_when[0]. Needs: nothing. If #1891 is on `main`, rebase first.

**Files:** Modify `lib/eastern_time.py` (the section "reading market_data_intraday across the convention migration": the constant after `TRUE_UTC_FROM` at `:196`, the functions after `stored_intraday_to_eastern`, which ends at `:328`). Modify `gcp/fetchers/fetch_alphavantage_intraday.py` (`:26`, `:430-447`). Create `tests/fixtures/intraday_checks.py`, `tests/lib/test_intraday_session_readings.py`.

**Interfaces:** Produces, all new, in `lib/eastern_time.py`:
- `TRUE_UTC_INSERTED_FROM: datetime`, aware UTC, built from `TRUE_UTC_FROM`.
- `proven_true_utc(ts, inserted_at) -> numpy.ndarray`: one bool per row. `ts` and `inserted_at` are read as `stored_intraday_to_eastern` reads `ts` (`:249-252`): a naive value is UTC. A NaT `inserted_at` is not proof.
- `class SessionReading(NamedTuple)`: `session: date`, `expected: int`, `true_utc: int`, `eastern_label: int`, `both: int`, `exact: bool`, `status: str` (`"OK"`, `"THIN"`, `"MISSING"` or `"UNDETERMINED"`).
- `session_minute_readings(ts, inserted_at, schedule) -> list[SessionReading]`: one per row of `schedule`, in its order. `schedule` is the frame `session_schedule` returns (index the session date, `market_open` and `market_close` aware UTC). It reads no calendar.
- `intraday_month_window(year: int, month: int) -> tuple[datetime, datetime]`: `[M-01 02:00 UTC, (M+1)-01 02:00 UTC)`, aware UTC.

Produces, in `tests/fixtures/intraday_checks.py` (imported as `from tests.fixtures.intraday_checks import ...`, as `tests/fixtures/earnings_calendar_sources.py` is). It imports only what `lib/eastern_time.py` has on `main` (`eastern_index_to_utc`, `session_schedule`), so Task 6 can run it there:
- `OLD = pd.Timestamp("2026-02-23 02:40", tz="UTC")` (not proof), `NEW = pd.Timestamp("2026-11-20 12:00", tz="UTC")` (proof).
- `et_minutes(day: str, start: str, end: str) -> pd.DatetimeIndex`: naive Eastern, one per minute, both ends included.
- `store(naive_et: pd.DatetimeIndex, how: str) -> pd.DatetimeIndex`: the stored `ts`, aware UTC. `"true"` converts with `eastern_index_to_utc`; `"label"` stamps the same clock as UTC; `"both"` is the union of the two.

How the three counts are taken (the tests fix the numbers; this fixes the meaning). Minutes are distinct whole-minute offsets from the session's open, inside `[0, expected)`. P is the offsets of proven rows read at their stored instant. Ut is the offsets of the other rows read at their stored instant. Ul is the offsets of the other rows whose stored clock, read as a naive Eastern wall time, falls in the session's regular hours; compare it with `utc_to_eastern_naive` of the open and close, naive against naive, so no wall time is localized and a clock-change hour cannot raise. `true_utc = |P ∪ Ut|`, `eastern_label = |P ∪ Ul|`, `both = |P ∪ (Ut ∩ Ul)|`. `exact` is true when Ut and Ul are both empty.

- [ ] Write in `tests/lib/test_intraday_session_readings.py`, with a local `read(ts, day, inserted=OLD)` that returns `session_minute_readings(ts, pd.Series([inserted] * len(ts)), session_schedule(day, day))[0]`:
  - `test_session_minute_readings_table`, parametrized. Each row is (day, first minute, last minute, storage, inserted) and the reading `true_utc / eastern_label / both of expected, status, exact`:

| Rows | Stored | Inserted | Reading |
|---|---|---|---|
| 2025-05-01 09:30 to 13:29 | true | OLD | 240 / 150 / 0 of 390, UNDETERMINED, not exact |
| the same | label | OLD | 0 / 240 / 0, UNDETERMINED |
| the same | both | OLD | 240 / 390 / 240, UNDETERMINED |
| the same | true | NEW | 240 / 240 / 240, THIN, exact |
| 2025-05-01 04:00 to 13:29 | true | OLD | 240 / 390 / 240, UNDETERMINED |
| 2025-05-01 04:00 to 20:00 | true, label, both (three rows) | OLD | 390 / 390 / 390, OK, not exact |
| 2025-01-15 04:00 to 20:00 | label | OLD | 331 / 390 / 331, UNDETERMINED |
| 2025-05-01, no row | | | 0 / 0 / 0, MISSING, exact |
| 2026-10-01, 351 minutes from 09:30 | true | OLD | 351 / 351 / 351, OK, exact |
| 2026-10-01, 350 minutes from 09:30 | true | OLD | 350 / 350 / 350, THIN, exact |
| 2025-11-28, 189 minutes from 09:30 | true | NEW | 189 / 189 / 189 of 210, OK, exact |
| 2025-11-28, 188 minutes from 09:30 | true | NEW | 188 / 188 / 188 of 210, THIN, exact |

  - `test_session_minute_readings_reads_no_calendar`: with `lib.eastern_time._sessions_covering` patched to raise `AssertionError`, a hand-built one-row frame (index `pd.Timestamp("2025-05-01")`, `market_open` `2025-05-01 13:30+00:00`, `market_close` `2025-05-01 20:00+00:00`) and the 240 true rows still give 240 / 150 / 0. A two-row schedule returns two readings in the schedule's order.
  - `test_proven_rule`: `TRUE_UTC_INSERTED_FROM == datetime(2026, 9, 28, tzinfo=timezone.utc)`. `proven_true_utc` over four rows, (`ts`, `inserted_at`): (2025-05-01 13:30 UTC, NaT) False; (2025-05-01 13:31 UTC, 2026-09-28 00:00:00 UTC) True; (2026-09-28 00:00 UTC, OLD) True; (2026-09-27 23:59 UTC, 2026-09-27 23:59:59 UTC) False. A naive `ts` of 2025-05-01 13:30 with a naive `inserted_at` of 2026-11-20 12:00 is True.
  - `test_two_rows_in_one_minute_count_once`: rows at 2025-05-01 13:30:00 and 13:30:30 UTC, OLD, read `true_utc == 1`.
  - `test_intraday_month_window`: `intraday_month_window(2025, 12) == (datetime(2025, 12, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 1, 2, tzinfo=timezone.utc))`; `fetch_alphavantage_intraday.month_replace_window(2025, 12)` is the same pair, and so is `(2026, 3)` against `intraday_month_window(2026, 3)`.
- [ ] Run: `python3 -m pytest tests/lib/test_intraday_session_readings.py -q` (expect FAIL: cannot import `session_minute_readings`).
- [ ] Implement the constant and the four functions in `lib/eastern_time.py`. Move the comment that explains the 02:00 boundary (`fetch_alphavantage_intraday.py:430-439`) above `intraday_month_window`. In the fetcher, `month_replace_window` keeps its name, signature and docstring and returns `intraday_month_window(year, month)`; delete `_WINDOW_HOUR_UTC` (its only users are `:445` and `:447`), leave one comment line that points at `lib.eastern_time.intraday_month_window`, and drop `timezone` from the `datetime` import if nothing else in the file uses it.
- [ ] Run: `python3 -m pytest tests/lib/test_intraday_session_readings.py tests/lib/test_eastern_time.py tests/gcp/test_intraday_replace_months.py tests/meta/test_timezone_boundaries.py -q` (expect all pass; at 39ce5d57 `test_eastern_time.py` holds 27 tests and `test_intraday_replace_months.py` 351, and none of them changes).
- [ ] The render step.
- [ ] Commit: `feat(data): read a stored 1-min session without trusting its framing`

## Task 3: `place_stored_rows`

Spec: Design F (`place_stored_rows`; the misplaced whole session). Advances done_when[1]. Needs: Task 2.

**Files:** Modify `lib/eastern_time.py` (after `session_minute_readings`), `tests/fixtures/intraday_checks.py`, `tests/lib/test_intraday_session_readings.py`.

**Interfaces:** Consumes `proven_true_utc`, `stored_intraday_to_eastern`, `utc_to_eastern_naive`, `eastern_index_to_utc`. Produces:
- `place_stored_rows(ts, volume, inserted_at) -> tuple[pd.DatetimeIndex, numpy.ndarray, numpy.ndarray]` (new): `(instants, keep, proven)`, one entry per input row, in input order. `instants` is aware UTC.
- In the fixture module: `session_bars(day: str, *, start: str = "04:00", end: str = "20:00", spike: bool = True, day_high: float = 600.0, day_low: float = 590.0, f_high: float = 1.0, f_low: float = 1.0) -> pd.DataFrame` with columns `bar` (naive Eastern minute), `high`, `low`, `volume`. Every bar's high and low are the midpoint of `day_high` and `day_low`, except the 10:17 bar, whose high is `day_high * f_high`, and the 11:42 bar, whose low is `day_low * f_low`. Volume is 1000, and 20000 from 09:30 to 09:59 when `spike`.
- `stored(frame: pd.DataFrame, how: str = "true", *, shared: str = "true", inserted=OLD) -> pd.DataFrame`: adds `ts` (through `store`) and `inserted_at`. For `"both"` the frame holds one row per `ts`, and where the two conventions meet on a key the `shared` copy's values are kept (`"true"` or `"label"`).

The rule, which the signature does not determine. Run `stored_intraday_to_eastern(ts, volume)` once over all the rows. A proven row's instant is its stored `ts`. A row that is not proven gets the resolver's placement: its stored `ts` where the resolver converted it, and `eastern_index_to_utc` of the resolver's wall time where the resolver read it as a label (do not convert a resolver-converted row back: its wall time can be an ambiguous hour). Then keep one row per instant: sort by instant, then proven before not proven, then rows the resolver kept before rows it dropped, stable; the first of each instant is kept.

- [ ] Write `test_place_stored_rows`, parametrized by case, all on 2025-05-01. `rth` is `keep` and the instant in `[2025-05-01 13:30 UTC, 2025-05-01 20:00 UTC)`:
  - proven keeps its stored instant: `stored(session_bars(day), "label", inserted=NEW)` (961 rows the resolver reads as labels): `instants` equal the stored `ts`, `keep` and `proven` are all True.
  - not proven follows the resolver: the same rows with OLD: `utc_to_eastern_naive(instants)` equals the resolver's index, `keep` equals the resolver's mask, `proven` is all False.
  - two rows on one minute, neither proven: the same OLD rows plus one row at 2025-05-01 20:30 UTC, volume 1000, OLD. The label row at 16:30 UTC and the added row both land on 20:30 UTC; exactly one row is dropped and it is the added one, as the resolver alone drops it.
  - two rows on one minute, one proven: the same with the added row inserted NEW. Exactly one row is dropped and it is the label row at 16:30 UTC.
  - four storages with the spike: `stored(session_bars(day), how, shared=s)`, OLD, for `how` `"true"`, for `"label"`, and for `"both"` with `shared` `"true"` and with `"label"`: `rth` selects 390 rows, each on its own bar's minute (`utc_to_eastern_naive(instants[rth])` equals `bar`), whose highest high is 600.0 and lowest low is 590.0.
  - the named limit: `stored(session_bars(day, spike=False), "both", shared="label")`, OLD: `rth` selects 390 rows, none on its own bar's minute, none proven, and neither 600.0 nor 590.0 is among their highs and lows.
- [ ] Run: `python3 -m pytest tests/lib/test_intraday_session_readings.py -q -k place_stored_rows` (expect FAIL: cannot import `place_stored_rows`).
- [ ] Implement `place_stored_rows`.
- [ ] Run: `python3 -m pytest tests/lib/test_intraday_session_readings.py tests/lib/test_eastern_time.py tests/meta/test_timezone_boundaries.py -q` (expect all pass).
- [ ] The render step.
- [ ] Commit: `feat(data): place stored 1-min rows by proof before inference`

## Task 4: The scheduled session scan

Spec: Design B ("Scheduled scan", "What a scheduled run prints", "The old day-presence scan leaves this table"); What bad input gets (scheduled scan rows). Advances done_when[2], [3]. Needs: Task 2. If the watched-ticker ingest is on `main`, rebase first.

**Files:** Modify `scripts/audit_data_freshness.py` (imports `:34-43`; the `market_data_intraday` entry of `CHECKS`, `:124-143`; `_session_dependent_checks`, `:1467-1486`). Modify `tests/fixtures/intraday_checks.py`. Create `tests/audits/test_audit_intraday_session_gaps.py`.

**Interfaces:** Consumes `session_minute_readings`, `SessionReading`, and from the audit `_recent_trading_days` (`:744`), `_calendar` (`:414`), `session_schedule`, `_timed` (`:1379`), `_CHECK_QUERY_TIMEOUT_S` (120.0, `:60`), `FreshnessRow`. Produces, all new, in the audit:
- `_session_gap_row(check: dict, ticker: str, reading: SessionReading) -> FreshnessRow`: `table` `f"{check['name']} [sessions]"`, `status` `stale`, `expected_latest` the session's ISO date, `last_row_at` and `lag_hours` None, `expected_max_hours` `check["expected_lag_hours"]`, `row_count_recent` the lowest of the three counts, `writer_job` `fetch-alphavantage-intraday`, `detail` D1, D2 or D3.
- `_query_intraday_session_gaps(check: dict, now_utc: datetime) -> list[FreshnessRow]`: failing sessions only.
- In the fixture module: `rth_frame(counts: dict[str, int], inserted=None) -> pd.DataFrame` with columns `ts` and `inserted_at`: for each ISO session date, that many one-minute rows from 09:30 Eastern stored as true UTC; `inserted_at` is `ts` plus one day unless given; an empty dict gives an empty frame that still has both columns. `install_audit_readers(monkeypatch, mod, scan) -> list[dict]`: `mod` is the audit module object (it has two import names, `scripts.audit_data_freshness` here and `audit_data_freshness` in the API). It patches `mod.query_to_dataframe` with a healthy answer for each of the three shapes the swallowing reader is asked (SQL holding `GROUP BY`: one row per ticker in `params["tickers"]` and per calendar day from `params["start_bound"]` to `params["end_bound"]`, columns `ticker`, `d`, `c`; SQL holding `AS bad`: `[{"bad": 0}]`; otherwise `[{"last_row_at": datetime(2026, 11, 13, 14, 0), "row_count_recent": 100000}]`), patches `gcp.database.query_to_dataframe_strict` with a fake `(sql, params=None, timeout_s=None)` that appends `{"sql", "params", "timeout_s"}` to the returned list and answers SQL holding `inserted_at` from `scan` (`scan(params["t"])`, or raises `scan` when it is an exception) and SQL holding `non_null` with ten of ten for IWM, SPY and QQQ, and raises `AssertionError` on anything else, patches `gcp.database.table_exists` to return False, and sets `mod._ENRICHMENT_WINDOW_ET` to `(0, 0)`. With every session whole, `audit_all(datetime(2026, 11, 13, 15, 0))` over these stubs has `overall_status == "ok"` (run on a prototype of this scan, 2026-11-14).

- [ ] Write in `tests/audits/test_audit_intraday_session_gaps.py`, with `mod = scripts.audit_data_freshness`, `NOW = datetime(2026, 11, 13, 15, 0)`, `FIVE = ("2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11")`, `whole = {d: 390 for d in FIVE}`, a helper `_audit(monkeypatch, scan, now=NOW)` that installs the readers and returns `(mod.audit_all(now), calls)`, and a helper `_main(monkeypatch, argv, scan)` that installs the readers, sets `mod.is_cloud_sql_configured` to return True, wraps `mod.audit_all` so `main()` runs it at `NOW` (`real = mod.audit_all`, patched with `lambda: real(NOW)`), sets `sys.argv`, calls `mod.main()` and returns the exit code (0 when it returns):
  - `test_scan_reads_five_settled_sessions_with_one_strict_query_per_ticker`: every ticker whole. The calls whose SQL holds `inserted_at` are three, for IWM, SPY and QQQ; each SQL equals Q1 once whitespace is collapsed, holds `interval = '1min'`, and holds neither `DATE(` nor `::date`; each `params` equals `{"t": <ticker>, "start": datetime(2026, 11, 5, 2, tzinfo=timezone.utc), "end": datetime(2026, 11, 12, 2, tzinfo=timezone.utc)}`; each `timeout_s == 120`. No row's table holds `[sessions]` and none holds `market_data_intraday [gap]`. The `market_data_intraday` entry of `mod.CHECKS` has `session_gap_days == 5` and no `gap_scan_days`, and still has `settle_hour_et == 21`, `settle_lag_days == 1` and `min_rows_per_day == 350`.
  - `test_missing_thin_and_whole_sessions`: SPY with 2026-11-09 absent gives one row: table `market_data_intraday [sessions]`, ticker SPY, status `stale`, `expected_latest` `2026-11-09`, `row_count_recent` 0, `detail` `MISSING: 0 of 390 regular-hours minutes`, `writer_job` `fetch-alphavantage-intraday`, `expected_max_hours` 30. With 240 on that session: one row, `detail` `THIN: 240 of 390 regular-hours minutes`, `row_count_recent` 240. With 30: one row, `THIN: 30 of 390 regular-hours minutes`. With 351: none. With all five at 240: five rows for SPY. A reader that returns the empty frame for SPY: five MISSING rows.
  - `test_reader_errors_propagate_out_of_audit_all`: `scan=ConnectionError("connection refused")` raises `ConnectionError`; `scan=KeyError("inserted_at")` raises `KeyError`.
  - `test_a_defect_in_the_readings_is_not_a_calendar_failure`: with `mod.session_minute_readings` patched to raise `KeyError("inserted_at")`, `audit_all(NOW)` raises `KeyError` (it does not return a report with a `nyse_calendar` row).
  - `test_a_calendar_error_from_the_schedule_is_the_one_calendar_row`: with `mod.session_schedule` patched to raise `RuntimeError("boom")`, `audit_all(NOW)` returns a report with exactly one row whose table is `nyse_calendar`; `main()` with `--strict` exits 2.
  - `test_strict_run_prints_the_thin_session` (`capsys`): `_main` with argv `["audit_data_freshness.py", "--strict"]` and SPY at 240 on 2026-11-09: exit code 1; stdout has exactly one line that holds `market_data_intraday [sessions]`, and it holds `SPY` and `stale`; a line that holds `writer-job: fetch-alphavantage-intraday`; a line that holds `detail: THIN: 240 of 390 regular-hours minutes`; a line that holds `details:`, `"expected_latest": "2026-11-09"` and `"row_count_recent": 240`; a line that holds `Overall:` and `STALE`.
  - `test_whole_run_prints_nothing_of_its_own` (`capsys`, `caplog`): call `caplog.set_level(logging.WARNING)` first. `main()` calls `logging.basicConfig(level=logging.WARNING)`, which does nothing under pytest because the root logger already has pytest's handlers; setting the level here stands for it and keeps the test independent of what an earlier test left on the root logger. Every session whole: no stdout line holds `[sessions]`; a line holds `Overall:`; `check=intraday_session_gaps` is in neither stdout, stderr nor `caplog.text`; no `SystemExit` with a non-zero code.
  - `test_failed_read_logs_the_check_and_prints_no_report` (`capsys`, `caplog`): `scan=ConnectionError("connection refused")`: `main()` raises `ConnectionError`, `caplog.text` holds `check=intraday_session_gaps FAILED after`, and stdout holds no `Overall:`.
  - `test_half_day_and_undetermined_details` (Review Focus): at `datetime(2026, 12, 1, 15, 0)` the five sessions are 2026-11-20, 11-23, 11-24, 11-25 and 11-27; with the first four at 390 and 2026-11-27 at 188 the one row reads `THIN: 188 of 210 regular-hours minutes`, and at 189 there is none. `_session_gap_row(check, "SPY", SessionReading(date(2025, 5, 1), 390, 240, 390, 240, False, "UNDETERMINED"))` has `detail` `UNDETERMINED: 240 as true UTC, 390 as Eastern labels, 240 as both, of 390` and `row_count_recent` 240.
- [ ] Run: `python3 -m pytest tests/audits/test_audit_intraday_session_gaps.py -q` (expect FAIL: the module has no `_session_gap_row`, and `CHECKS` has no `session_gap_days`).
- [ ] Implement:
  - `CHECKS`: in the `market_data_intraday` entry replace `"gap_scan_days": 5,` by `"session_gap_days": 5,` with a comment that the session scan replaces the day-presence scan for this table (every hole it could flag is MISSING here, and it read by `DATE(ts)` through the swallowing reader). Nothing else in the entry changes.
  - Import `SessionReading` and `session_minute_readings` in the `lib.eastern_time` import.
  - `_query_intraday_session_gaps`: `days = _recent_trading_days(now_utc, check["session_gap_days"], settle_hour_et=check.get("settle_hour_et", 16), settle_lag_days=check.get("settle_lag_days", 0))`; `schedule = _calendar(session_schedule, days[-1], days[0])`, the only calendar call it wraps; `start` is 02:00 UTC on `days[-1]` and `end` is 02:00 UTC on the day after `days[0]`, both aware (`datetime(y, m, d, 2, tzinfo=UTC)`, with a comment that the hour is `intraday_month_window`'s); for each ticker of `check["tickers"]`, one Q1 read through `query_to_dataframe_strict` imported inside the function from `gcp.database` (as `_query_column_nullity` does, `:998`) with `timeout_s=_CHECK_QUERY_TIMEOUT_S`, then `session_minute_readings(df["ts"], df["inserted_at"], schedule)` called directly, then `_session_gap_row` for each reading whose status is not `OK`. No `try`.
  - `_session_dependent_checks`: after the `_query_gap_scan` line (`:1486`), inside the loop: `if check.get("session_gap_days"): report.rows.extend(_timed("intraday_session_gaps", _query_intraday_session_gaps, check, now))`.
- [ ] Run: `python3 -m pytest tests/audits tests/api/test_route_coverage.py tests/meta -q` (expect all pass; `tests/audits/test_audit_data_freshness.py` holds 50 tests at 39ce5d57 and none changes. The two freshness rows of `test_route_coverage.py` are pinned at 503 today and are expected to stay there: its harness raises `_BackendDown`, a `ConnectionError`, at the scan's read, and `is_infrastructure_error` calls a `ConnectionError` an outage. If either row turns 500, the scan is raising something else: fix the scan, not the row).
- [ ] The render step.
- [ ] Commit: `feat(data): alarm on a missing or thin 1-min session`

## Task 5: `--intraday-gap-since`

Spec: Design B ("On-demand scan", its exit table); What bad input gets (`--intraday-gap-since` rows); Capacity (memory). Advances done_when[4], and done_when[11] (memory half). Needs: Task 4.

**Files:** Modify `scripts/audit_data_freshness.py` (`main`, `:1563-1597`; one new function above it). Modify `tests/audits/test_audit_intraday_session_gaps.py`.

**Interfaces:** Consumes `proven_true_utc`, `intraday_month_window`, `session_minute_readings`, `as_utc_instant`, `most_recent_trading_day`, `_calendar`, `CalendarUnavailable`. Produces (new) `run_intraday_gap_since(since: date, tickers: tuple[str, ...], strict: bool, now_utc: Optional[datetime] = None) -> int`: the exit code. `now_utc` is naive UTC, the frame `most_recent_trading_day` takes; its default is built with `datetime.now(UTC).replace(tzinfo=None)` on a line that carries `# tz-ok:`.

What it does, in order. The check is the `CHECKS` entry that carries `session_gap_days`. `last` is `most_recent_trading_day(now, settle_hour_et=..., settle_lag_days=...)` with the entry's values. `since` after `last` returns 2 with a message on stderr, before any query. Per ticker: Q2; a null `first_ts` prints G3 and goes to the next ticker; otherwise `start` is the later of `since` and the UTC date of `first_ts` (through `as_utc_instant`, which refuses a naive value). For each month from `start`'s to `last`'s: one Q1 read over `intraday_month_window(y, m)`; G2 when the frame has a row, with `unproven_rows` the count of rows `proven_true_utc` calls False; `schedule = _calendar(session_schedule, lo, hi)` for the part of the month inside `[start, last]`; `session_minute_readings`, called directly; G1 for each reading that is not `OK`. One month's frame is alive at a time. After the last ticker, G4. A `CalendarUnavailable` anywhere returns 2 with a message on stderr and no G4. Nothing else is caught. Return 1 when `strict` and a G1 or G3 line was printed, else 0.

- [ ] Write, with a helper `_gap_since(monkeypatch, argv, *, first_ts, months, now=NOW)` that patches `mod.audit_all` to raise `AssertionError("audit_all must not run")`, `mod.is_cloud_sql_configured` to True, `mod.run_intraday_gap_since` with a wrapper that passes `now_utc=now` to the real one, and `gcp.database.query_to_dataframe_strict` with a recording fake (SQL holding `min(ts)` answers `pd.DataFrame({"first_ts": [first_ts.get(params["t"])]})`; any other SQL answers `months.get((params["t"], params["start"].year, params["start"].month), rth_frame({}))`), sets `sys.argv`, calls `mod.main()` and returns `(exit code, calls)`; an `Exception` given in place of a frame or of `first_ts` is raised by the fake:
  - `test_gap_since_reads_month_by_month_and_prints_the_lines` (`capsys`): argv `--intraday-gap-since 2026-09-21 --intraday-gap-tickers SPY`; `first_ts` SPY 2022-02-24 09:00 UTC. September holds 04:00 to 20:00 as true UTC, OLD, for 2026-09-21, 09-23, 09-24 and 09-25 (961 rows each, built with `store(et_minutes(d, "04:00", "20:00"), "true")`), 240 minutes from 09:30, OLD, for 09-22, and 390 from 09:30 for 09-28, 09-29 and 09-30; October holds 390 for each session except 240 on 2026-10-05; November holds 390 for 11-02 to 11-06, 11-10 and 11-11 and nothing for 11-09. Exit 0. Four calls: the probe (SQL equals Q2, `params == {"t": "SPY"}`, `timeout_s == 120`), then three reads whose `(start, end)` are `intraday_month_window(2026, 9)`, `(2026, 10)` and `(2026, 11)`; every SQL holds `interval = '1min'`. stdout, in order:
    `MONTH SPY,2026-09 rows=5254 unproven_rows=4084`
    `SESSION-GAP SPY 2026-09-22 UNDETERMINED true_utc=240 eastern_label=150 both=0 expected=390 exact=no`
    `MONTH SPY,2026-10 rows=8430 unproven_rows=0`
    `SESSION-GAP SPY 2026-10-05 THIN true_utc=240 eastern_label=240 both=240 expected=390 exact=yes`
    `MONTH SPY,2026-11 rows=2730 unproven_rows=0`
    `SESSION-GAP SPY 2026-11-09 MISSING true_utc=0 eastern_label=0 both=0 expected=390 exact=yes`
    then a last line that starts `intraday-gap-since summary:` and holds `SPY first=2022-02-24 sessions=38 ok=35 missing=1 thin=1 undetermined=1` and `seconds=`.
    The same run with `--strict` exits 1. With every session whole and `--strict` it exits 0 and prints no `SESSION-GAP` line.
  - `test_sessions_before_the_first_stored_row_print_nothing`: `first_ts` 2026-10-05 13:30 UTC with `--intraday-gap-since 2026-09-21`: two month reads (October, November), no line dated before 2026-10-05, no `MONTH SPY,2026-09`.
  - `test_a_ticker_with_no_stored_row`: `first_ts` None for QQQ, argv `--intraday-gap-tickers QQQ`: one call (the probe), stdout holds `NO-ROWS QQQ` and the summary line; exit 0 without `--strict`, 1 with.
  - `test_default_is_the_three_tickers`: no `--intraday-gap-tickers`: three probes, for the tickers of the `CHECKS` entry.
  - `test_usage_errors_exit_2_before_any_query`, parametrized: `--intraday-gap-since 2026-11-05 --intraday-gap-tickers AMD`; `--intraday-gap-since 2026-13-01`; `--intraday-gap-since 2026-11-12` (after the last settled session, 2026-11-11); `--intraday-gap-since 2026-11-05 --json`; `--intraday-gap-tickers SPY` with no `--intraday-gap-since`: exit 2, zero calls, no summary line. And with `mod.is_cloud_sql_configured` returning False, `--intraday-gap-since 2026-11-05` exits 2 with zero calls, as the audit does today (`:1577-1583`).
  - `test_a_calendar_error_exits_2_with_and_without_strict`: `mod.session_schedule` patched to raise `RuntimeError("boom")`: exit 2 both ways, no line that starts `intraday-gap-since summary:`.
  - `test_reader_and_reading_errors_propagate`: the probe raising `ConnectionError("connection refused")`, a month read raising `KeyError("inserted_at")`, and `mod.session_minute_readings` patched to raise `KeyError("inserted_at")` each leave `main()` as that exception, with no summary line on stdout.
  - `test_since_on_a_closed_day_and_ticker_spelling` (Review Focus): `--intraday-gap-since 2026-10-31 --intraday-gap-tickers " spy, qqq "` with every November session to 2026-11-11 whole for both: exit 0; six calls, a probe and two month reads (October, November) for SPY and for QQQ and none for IWM; the summary holds `SPY first=2022-02-24 sessions=8 ok=8 missing=0 thin=0 undetermined=0` (the eight sessions from 2026-11-02 to 2026-11-11) and the same for QQQ.
- [ ] Run: `python3 -m pytest tests/audits/test_audit_intraday_session_gaps.py -q` (expect the new tests FAIL: `main()` exits 2 on an unrecognized argument, and the module has no `run_intraday_gap_since`).
- [ ] Implement. In `main()`: add `--intraday-gap-since` (metavar `YYYY-MM-DD`) and `--intraday-gap-tickers`; right after `parse_args`, with `parser.error` (exit 2): `--intraday-gap-tickers` without `--intraday-gap-since`; `--json` with `--intraday-gap-since`; a date `date.fromisoformat` refuses; a ticker, after `strip().upper()`, that is not one of the entry's tickers. Keep the logging lines and the not-configured exit (`:1572-1583`) where they are. Then, when the flag is given, `sys.exit(run_intraday_gap_since(since, tickers, args.strict))` before `audit_all()` is reached. Extend the module docstring's Usage block with the two forms the spec gives (the listing run and the gate form with `--strict`).
- [ ] Run: `python3 -m pytest tests/audits tests/meta -q` (expect all pass).
- [ ] Measure memory, locally, and keep the figure for the PR. In one fresh `python3` process: patch `gcp.database.query_to_dataframe_strict` so the probe answers 2015-01-01 09:00 UTC and each month read answers 50,000 rows with `ts` evenly spaced inside the window it was asked for and `inserted_at` OLD; patch `is_cloud_sql_configured` to True and `run_intraday_gap_since` to pass `now_utc=datetime(2026, 11, 13, 15, 0)`; run `main()` with `--intraday-gap-since 2015-01-01 --intraday-gap-tickers SPY`; print `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024` (MB on Linux) and the number of month reads. Expect 143 month reads and a peak under 256. A peak at or over 256 means more than one month is alive at a time: fix the loop, not the number.
- [ ] The render step.
- [ ] Commit: `feat(data): list missing and thin 1-min sessions on demand`

## Task 6: The API test of the two routes

Spec: Design B ("Where else the scan shows"); What bad input gets (scheduled scan rows); Site traceability. Advances done_when[5]. Needs: Task 4. No file under `platform/api` changes.

**Files:** Create `tests/api/test_health_freshness_session_gaps.py`.

**Interfaces:** Consumes `rth_frame`, `install_audit_readers`. The module sets up `sys.path` and imports `from routers import admin as admin_module` and `from routers import health as health_module` as `tests/api/test_admin_users_datasources.py:41-56` does, so `admin.py`'s `from .health import freshness_report_dict` and this test share one cache. The audit module is `import audit_data_freshness as audit_mod`, the name `health.py:132` imports.

- [ ] Write, with a fixture that builds `FastAPI()` with `health_module.router` and `admin_module.router`, sets `ADMIN_EMAIL` and `api.auth.AUTH_MODE = "iap"` (as `_as_admin` does there, `:62-65`), wraps `audit_mod.audit_all` so the routes run it for real at `datetime(2026, 11, 13, 15, 0)`, and sets `health_module._cache = None` before each request; the client is `TestClient(app, raise_server_exceptions=False)` and the admin request carries the header `x-goog-authenticated-user-email: accounts.google.com:<ADMIN_EMAIL>`:
  - `test_a_missing_session_shows_on_both_routes`: readers whole except no SPY bar for 2026-11-09. `GET /api/health/freshness` is 200; exactly one element of `tables` has table `market_data_intraday [sessions]`, and it has ticker `SPY`, status `stale`, `expected_latest` `2026-11-09` and a `detail` that starts `MISSING`; `overall_status` is `stale`. `GET /api/admin/data-sources` is 200; the source with id `market_data_intraday` has status `stale` and `market_data_intraday [sessions] (SPY): stale` in its `message`.
  - `test_an_outage_is_503_and_a_defect_is_500`, parametrized over the scan's read raising `ConnectionError("connection refused")` (503 on both routes), `KeyError("inserted_at")` (500 on both) and `sqlalchemy.exc.OperationalError("SELECT 1", {}, pg8000.exceptions.DatabaseError({"C": "57014"}))` (500 on both).
- [ ] Run: `python3 -m pytest tests/api/test_health_freshness_session_gaps.py -q` (expect 4 passed: the code is Task 4's).
- [ ] Prove it is red without the scan: `git worktree add --detach /tmp/red-main origin/main`, copy this test file and `tests/fixtures/intraday_checks.py` into it, run the same command there (expect 4 failed: no `[sessions]` row, and 200 where 503 and 500 are asserted, because `main`'s scan reads through the swallowing reader), then `git worktree remove --force /tmp/red-main`. Keep the output for the PR.
- [ ] Run: `python scripts/export_openapi.py --check` (expect `platform/api/openapi.json is up to date`) and `git diff --stat origin/main -- platform/api` (expect empty).
- [ ] Commit: `test(data): pin the session rows on the freshness and admin routes`

## Task 7: `session_basis_verdicts`

Spec: Design C ("Which sessions are measured", "Which daily rows are measurable", "The measure", "Where it lives"). Advances done_when[6]. Needs: Tasks 2 and 3.

**Files:** Modify `gcp/fetchers/fetch_alphavantage_intraday.py` (the `lib.eastern_time` import at `:26`; new code after `run_verify_months`, which ends at `:842`). Create `tests/gcp/test_intraday_verify_basis.py`.

**Interfaces:** Consumes `session_minute_readings`, `place_stored_rows`, and the fixture module's `session_bars`, `stored`, `OLD`, `NEW`. Produces, new:
- `TRUE_DAILY_SOURCES: tuple[str, ...]` (Global Constraints).
- `session_basis_verdicts(rows: pd.DataFrame, daily: pd.DataFrame, schedule: pd.DataFrame) -> list[dict]`: one dict per row of `schedule`, in its order, with keys `session` (date), `status`, `exact`, `verdict`, `reason`, `f_high`, `f_low`, `factor`. `rows` has `ts`, `high`, `low`, `volume`, `inserted_at`; `daily` has `date`, `high`, `low`, `data_source`. It reads nothing itself.
  - `verdict` is one of `AS-TRADED`, `INFERRED`, `ADJUSTED`, `ODD`, `UNMEASURED`, `INCOMPLETE`. `status` and `exact` are the reading's.
  - A session whose status is not `OK` is `INCOMPLETE`; `reason` and the three numbers are None.
  - Otherwise the first reason that applies makes it `UNMEASURED`, in this order: `no_daily_row`; `daily_from_intraday` (the stamp is `alphavantage_1min`); `daily_source_unknown` (any other stamp not in `TRUE_DAILY_SOURCES`, NULL included); `daily_not_positive` (high or low NULL, zero or negative); `no_rth_high_low` (no non-null high, or no non-null low, among the kept regular-hours rows). The kept regular-hours rows are those `place_stored_rows(rows["ts"], rows["volume"], rows["inserted_at"])` keeps with an instant in `[market_open, market_close)`.
  - A measured session carries `f_high`, `f_low` and `factor` and one of the four measured verdicts.

- [ ] Write, with `day = "2025-05-01"`, `schedule = session_schedule(day, day)`, a local `daily(day, src="alphavantage_daily", high=600.0, low=590.0)` that returns a one-row frame with a `date` value, and `one(**kw)` that returns `session_basis_verdicts(stored(session_bars(day, **kw), inserted=NEW), daily(day), schedule)[0]`:
  - `test_the_measure`, parametrized over (`f_high`, `f_low`, verdict, factor): (0.99430, 0.99430, ADJUSTED, 0.99430); (0.99969, 0.99969, ADJUSTED, 0.99969); (0.99970, 0.99970, AS-TRADED, 0.99970); (1.00030, 1.00030, AS-TRADED, 1.00030); (1.00031, 1.00031, ADJUSTED, 1.00031); (1.0, 0.99, ODD, 0.99500); (0.99900, 1.00100, ODD, 1.00000). Each record has `status == "OK"`, `exact is True`, and `f_high` and `f_low` equal to the two inputs.
  - `test_a_daily_row_built_from_the_bars_is_not_a_measure`: bars at 0.99430 on both sides, proven, with a daily row stamped `alphavantage_1min` whose high and low are the bars' own regular-hours extremes: `verdict == "UNMEASURED"`, `reason == "daily_from_intraday"`, `f_high is None`.
  - `test_unmeasured_reasons`, parametrized: `data_source` None and `"yahoo"` give `daily_source_unknown`; an empty daily frame gives `no_daily_row`; a daily high of None, a low of 0.0 and a high of -1.0 each give `daily_not_positive`; bars whose `high` and `low` are all NaN give `no_rth_high_low`.
  - `test_av_watched_backfill_is_measured`: that stamp with as-traded bars is `AS-TRADED`.
  - `test_an_as_traded_session_on_rows_that_are_not_proven_is_inferred`: the as-traded bars with `inserted=OLD` give `INFERRED` and `exact is False`.
  - `test_a_session_that_is_not_ok_is_not_measured`: `session_bars(day, start="09:30", end="13:29")`, NEW, gives `verdict == "INCOMPLETE"`, `status == "THIN"`, `f_high is None`, whatever the daily row says.
  - `test_daily_date_as_a_timestamp_still_matches` (Review Focus): the daily frame's `date` as `pd.Timestamp("2025-05-01")` and as `datetime(2025, 5, 1)` gives `AS-TRADED`, not `no_daily_row`.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_verify_basis.py -q` (expect FAIL: the module has no `session_basis_verdicts`).
- [ ] Implement `TRUE_DAILY_SOURCES` and `session_basis_verdicts`. Compare in whole units: `round(f * 100000)` against 99970 and 100030.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_verify_basis.py tests/gcp/test_intraday_replace_months.py tests/meta -q` (expect all pass).
- [ ] The render step.
- [ ] Commit: `feat(data): measure a session's basis against a true daily row`

## Task 8: `--verify-basis`

Spec: Design C (Input, Reads, "Sessions of a listed month", Output, the exit table, the three-way fixture); What bad input gets (`--verify-basis` rows). Advances done_when[7]. Needs: Task 7.

**Files:** Modify `gcp/fetchers/fetch_alphavantage_intraday.py` (new runner after `session_basis_verdicts`; `main`, `:865-884`). Modify `tests/gcp/test_intraday_verify_basis.py`.

**Interfaces:** Consumes `_read_replace_list` (`:664`), `intraday_month_window`, `session_schedule`, `utc_now`, `session_basis_verdicts`, `query_to_dataframe_strict` (the module-level import at `:32`, which the tests patch as `fai.query_to_dataframe_strict`, as `tests/gcp/test_intraday_replace_months.py:674` does). Produces (new) `run_verify_basis(path: str, now_utc: Optional[datetime] = None) -> int`; `now_utc` is aware UTC and defaults to `utc_now()`.

What it does, in order. Read the list; no lines returns 1 with a logged error, as `run_verify_months` does (`:808-815`). A line whose ticker is not SPY, QQQ or IWM returns 1 with a logged error, before any query. Per ticker, in list order: one Q4 read over the first day of its earliest listed month to the last day of its latest. Per listed ticker-month: one Q3 read over `intraday_month_window(y, m)`. An empty frame prints B2 and nothing else for that month. Otherwise the schedule is `session_schedule(first day, last day)` of the month, less every session whose `market_close` is after `now_utc`; `session_basis_verdicts`; then the month's lines in the order B1, B3, B4, B5, B6, each printed only when it counts at least one session. After the last month, B7. Return 1 when a B1 or B2 line was printed; otherwise 3 when a B5 line, a B4 line with `inexact` above 0 or a B6 line with `exact=no` was printed; otherwise 0. No `try` around either read.

- [ ] Write, with `_run(monkeypatch, tmp_path, list_text, bars, daily, now=datetime(2026, 11, 13, 15, tzinfo=timezone.utc))` that writes the list to `tmp_path / "l.csv"`, patches `fai.query_to_dataframe_strict` with a recording fake (SQL holding `market_data_daily` answers `daily[params["t"]]`; other SQL answers `bars.get((params["t"], params["start"].year, params["start"].month))` or an empty frame with Q3's five columns; an exception in place of a frame is raised) and returns `(fai.run_verify_basis(str(path), now), calls)`; and `month(y, m, per_day, how="true", shared="true")` that concatenates `stored(session_bars(d, **kw), how, shared=shared, inserted=ins)` for each session `d` of the month, with `(kw, ins) = per_day(d)`, and builds the daily frame with one `alphavantage_daily` row of 600.0 and 590.0 per session:
  - `test_reads_one_bars_query_per_month_and_one_daily_query_per_ticker`: list `SPY,2025-04` and `SPY,2025-05`: three calls; the daily SQL equals Q4 once whitespace is collapsed, with `params == {"t": "SPY", "first": date(2025, 4, 1), "last": date(2025, 5, 31)}`; the two bar SQLs equal Q3, hold `interval = '1min'`, and are bounded by `intraday_month_window(2025, 4)` and `(2025, 5)`; every `timeout_s == 120`.
  - `test_a_month_on_two_bases_is_one_line`: SPY 2025-06, OLD, both sides at 0.99430 on the sessions before 2025-06-20 and at 0.99725 from 2025-06-20 on: stdout holds `BASIS-FAIL SPY 2025-06 sessions=20 2025-06-02..2025-06-30 factor=0.99430..0.99725 inferred=20`; exit 1.
  - `test_one_adjusted_session_fails_its_month`: SPY 2025-04 and 2025-05, NEW, as traded except 2025-04-30 and 2025-05-01 at 0.99430: stdout holds `BASIS-FAIL SPY 2025-04 sessions=1 2025-04-30..2025-04-30 factor=0.99430..0.99430 inferred=0` and `BASIS-FAIL SPY 2025-05 sessions=1 2025-05-01..2025-05-01 factor=0.99430..0.99430 inferred=0`; exit 1.
  - `test_a_proven_month_with_unmeasured_incomplete_and_odd_sessions_exits_0`: SPY 2025-05, NEW, as traded except 2025-05-12 holding only 09:30 to 13:29 and 2025-05-13 with `f_low=0.99`; the daily frame lacks 2025-05-14 and stamps 2025-05-15 `alphavantage_1min`. stdout holds `UNMEASURED SPY 2025-05 sessions=2 2025-05-14..2025-05-15 no_daily_row=1 daily_from_intraday=1 daily_source_unknown=0 daily_not_positive=0 no_rth_high_low=0`, `INCOMPLETE SPY 2025-05 sessions=1 2025-05-12..2025-05-12 inexact=0` and `ODD SPY 2025-05-13 high=1.00000 low=0.99000 exact=yes`, no line that starts `BASIS-FAIL` or `INFERRED`, and a last line that starts `verify-basis summary:`; exit 0.
  - `test_one_row_that_is_not_proven_makes_it_inferred_and_exit_3`: the same month with the `inserted_at` of the 2025-05-16 10:00 bar set to OLD: the three lines above and `INFERRED SPY 2025-05 sessions=1 2025-05-16..2025-05-16`; exit 3.
  - `test_thin_sessions_that_are_not_proven_are_incomplete_not_a_basis`: SPY 2025-05, OLD, as traded, the first twelve sessions holding only 12:00 to 15:59: stdout holds `INCOMPLETE SPY 2025-05 sessions=12 2025-05-01..2025-05-16 inexact=12` and `INFERRED SPY 2025-05 sessions=9 2025-05-19..2025-05-30`, no `BASIS-FAIL`; exit 3.
  - `test_the_three_storages_print_the_same_lines`, parametrized over `("true", "true")`, `("label", "true")`, `("both", "true")`, `("both", "label")`: SPY 2025-05, OLD, whole sessions with the spike. As traded: `INFERRED SPY 2025-05 sessions=21 2025-05-01..2025-05-30`, exit 3. At 0.99430: `BASIS-FAIL SPY 2025-05 sessions=21 2025-05-01..2025-05-30 factor=0.99430..0.99430 inferred=21`, exit 1.
  - `test_an_empty_month_and_an_empty_list`: a listed month with no rows prints `EMPTY SPY 2025-05` and exits 1; a list with no lines (`""`, `"ticker,month\n"`, `"# only a comment\n"`) returns 1 with zero calls and no summary line.
  - `test_another_ticker_exits_1_before_any_query`: list `SPY,2025-05` and `AMD,2025-05`: 1, zero calls.
  - `test_reader_errors_propagate`: the bars read raising `ConnectionError("connection refused")`, and the daily read raising `KeyError("high")`, each leave `run_verify_basis` as that exception with no line that starts `verify-basis summary:`.
  - `test_verify_basis_with_another_list_mode_is_a_usage_error`: `main()` with `--verify-basis x --verify-months y`, and with `--verify-basis x --replace-months y`, raises `SystemExit` with code 2 and `fai.query_to_dataframe_strict` is not called.
  - `test_sessions_whose_close_has_not_passed_are_not_read` (Review Focus): SPY 2026-11, whole as-traded sessions with the spike for each session to 2026-11-12 and no row after it (the rows are proven by their date), with a daily row for every session of the month, at `now` 2026-11-13 15:00 UTC, when the session of 2026-11-13 is open: stdout is the summary line alone, with no `INCOMPLETE` and no `BASIS-FAIL` line; exit 0.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_verify_basis.py -q` (expect the new tests FAIL: the module has no `run_verify_basis`).
- [ ] Implement `run_verify_basis`. In `main()`: add `--verify-basis` (metavar `PATH`; help says read-only, no vendor call, and gives the `gs://` form the spec names); extend the check at `:879` so any two of `--replace-months`, `--verify-months` and `--verify-basis` are a `parser.error`; then `sys.exit(run_verify_basis(args.verify_basis))` beside the two existing dispatches. Leave `date.today()` at `:887` as it is.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_verify_basis.py tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_as_traded.py tests/meta -q` (expect all pass).
- [ ] The render step.
- [ ] Commit: `feat(data): check which stored 1-min months are as traded`

## Task 9: The six levels tables in the clear list

Spec: Design G. Advances done_when[8]. Needs: nothing.

**Files:** Modify `gcp/fetchers/fetch_alphavantage_intraday.py:465-476`. Create `tests/gcp/test_intraday_replace_levels_tables.py`.

**Interfaces:** `DERIVED_TS_TABLES` gains `strat_features_levels_1m`, `_5m`, `_15m`, `_30m`, `_60m`, `_4h` after the nine names it holds.

- [ ] Write `test_replace_month_clears_the_six_levels_tables`, patching `fai.fetch_month`, `fai._held_session_dates`, `fai._held_digest` and `fai.replace_rows_in_window` as `tests/gcp/test_intraday_replace_months.py:794-809` does: `replace_month("SPY", 2026, 9, "k", commit=True)` hands over `clear_tables` whose set equals the nine names on `main` (`intraday_flow_15m`, `intraday_gex_15m`, `realtime_gex_15m`, `strat_features_1m`, `_5m`, `_15m`, `_30m`, `_60m`, `_4h`) and the six, 15 names with no duplicate.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_replace_levels_tables.py -q` (expect FAIL: nine names).
- [ ] Add the six names and extend the comment above the tuple: the levels tables are computed from the feature tables (`strat_enrich_levels.backfill_one`), keyed by `(ticker, ts)`, and rebuilt by that module.
- [ ] Run: `python3 -m pytest tests/gcp/test_intraday_replace_levels_tables.py tests/gcp/test_intraday_replace_months.py -q` (expect 1 and 351 passed).
- [ ] The render step.
- [ ] Commit: `feat(data): clear a replaced month's levels tables`

## Task 10: The workflow test and the README line

Spec: Design D. Advances done_when[9]. Needs: nothing.

**Files:** Create `tests/meta/test_workflows_no_continue_on_error.py`. Modify `.github/workflows/README.md:38`.

**Interfaces:** Produces, in the test module: `continue_on_error_offenders(text: str) -> list[str]`: `yaml.safe_load` the text; a `yaml.YAMLError` is one offender that says the file does not parse; otherwise walk every mapping and sequence, and each mapping key equal to the string `continue-on-error` whose value `is not False` is an offender naming the path to it and the value. `_workflow_files() -> list[Path]`: every file under `.github/workflows`, at any depth, whose name ends `.yml`, `.yaml`, `.yml.disabled` or `.yaml.disabled`.

- [ ] Write:
  - `test_the_check_rejects_and_accepts`, parametrized over snippets. Rejected (at least one offender): `continue-on-error: true` on a step; on a job; the string `'true'`; `yes`; `${{ matrix.experimental }}`; a step that takes the key through a merge key (`<<: *defaults`, with the anchor holding `continue-on-error: true`); text that does not parse. Accepted (no offender): `continue-on-error: false`; no key; the words in a `#` comment; the words inside a `run: |` script.
  - `test_yaml_1_1_false_spellings_are_read_as_false` (Review Focus): `continue-on-error: no` and `off` give no offender, with a comment that PyYAML reads them as the boolean and that the rule is the spec's.
  - `test_no_workflow_sets_continue_on_error`: `_workflow_files()` holds `spec-gate.yml` and `registry-check.yml`, so an empty walk cannot pass; for every file, `continue_on_error_offenders(text) == []`, and the failure message names each file and offender.
  - `test_the_readme_states_the_rule`: exactly one line of `.github/workflows/README.md` contains `continue-on-error`; that line contains `on any step or job` and `tests/meta/test_workflows_no_continue_on_error.py`; the file does not contain `on a fetch or validation step`.
- [ ] Run: `python3 -m pytest tests/meta/test_workflows_no_continue_on_error.py -q` (expect only `test_the_readme_states_the_rule` FAIL: the 12 workflow files hold the key nowhere).
- [ ] Replace `.github/workflows/README.md:38` by the README line of Global Constraints. No other line of that file and no workflow file changes.
- [ ] Run the file again (expect all pass).
- [ ] Commit: `test(ci): keep continue-on-error out of every workflow`

## Task 11: Whole suite, the files left alone, the generated inventory

Spec: Done when (the suites and files left unmodified). Advances done_when[10]. Needs: Tasks 2 to 10.

- [ ] Run: `make test` (expect no failure that `origin/main` does not have).
- [ ] Run the render step once more on the final code and `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass). `git status` shows no change to the three docs; if it does, commit: `docs(infra): re-render the inventory for the intraday checks`.
- [ ] Run: `git diff --stat origin/main -- gcp/deploy.sh platform/api CLAUDE.md gcp/fetchers/export_intraday_bars.py .github/pull_request_template.md tests/fixtures/timezone_boundary_baseline.json tests/gcp/test_evaluate_ew_strikes.py tests/gcp/test_intraday_as_traded.py tests/gcp/test_intraday_replace_months.py tests/gcp/test_intraday_writers_utc.py tests/gcp/test_av_intraday_universe.py tests/audits/test_audit_data_freshness.py tests/api/test_route_coverage.py tests/api/test_admin_users_datasources.py tests/api/test_platform_api.py tests/meta/test_production_writers.py tests/meta/test_timezone_boundaries.py` (expect empty). `gcp/fetchers/export_intraday_bars.py` does not exist on `main`; it is file B's.
- [ ] Run: `git diff --name-only origin/main -- .github` (expect `.github/workflows/README.md` alone).

## Task 12: Product record, site notes and the gate

Spec: Site traceability; Done when (the PR-body measurements, the product records); product-delivery Phase 4 and Phase 5. Closes done_when[11] (posted) and [12]. Needs: Tasks 1 to 11. Once the site-note steps start, no file under `gcp/`, `lib/`, `scripts/` or `tests/` may change without redoing all four of them: the source hash covers those paths.

- [ ] If Task 1 ran on an earlier day, run its sixth statement again for the day's five sessions, so the counts on the PR are the day's.
- [ ] Push with `git push -u origin feature/feat-data-001-intraday-checks` and open a draft PR. Title: `FEAT-DATA-001: session gap alarm, basis check and workflow test for market_data_intraday`. Body: the spec path and this plan's path; the 13 done_when items, each as a `- [ ]` line that starts with the item's text; a Capacity section from the spec's Capacity table: Volume (scheduled scan: 3 reads of about 5,800 rows of two timestamps; on-demand scan and basis check: at most 143 month reads of 20,000 to 50,000 rows per ticker, one month in memory at a time; 0 rows written), Velocity (3 queries a watchdog run, 12 runs on a weekday; in the API at most once per 5 minutes per instance; 1 probe and at most 143 queries per ticker on demand, plus 1 daily query for the basis check), Wall-clock (the execution times of Task 1; 607 ms a month read as `run_verify_months` records; the watchdog's 3,600 s and the fetch job's 3,600 s task timeouts), Cost (no new job or schedule; about 3 cents a month for the scheduled scan and under 1 cent per on-demand run, at the spec's list prices). Paste Task 1's five plans and two result sets with the execution id, Task 5's peak memory and month-read count, and Task 6's red-on-main output. Say that the deployed-site before run waits for a solyra cloud spec that does not exist yet (the spec's Close-out), and that `tests/api/test_health_freshness_session_gaps.py` is the proof this PR carries.
- [ ] Set `pr:` in this plan to the PR's number.
- [ ] `docs/product/02-FEATURE-CATALOG.md`, the `### FEAT-DATA-001` record only (`:513`; not the table row at `:35`): in the Status cell (`:520`) append, before the closing ` |`: `; a session gap alarm on the freshness watchdog, an on-demand session scan and a read-only basis check for market_data_intraday (SPY, QQQ, IWM), a test that keeps continue-on-error out of every workflow, and the six levels tables in the replace's clear list ([#N](https://github.com/TeneikaAskew/stocks/pull/N); implementation under review, not deployed; no stored bar is rewritten by it)`. Last reviewed (`:524`) becomes the date of the PR's head commit; the gate compares the two exactly, so set it again if a later commit lands on another day.
- [ ] `docs/product/12-PR-ISSUE-TRACEABILITY.md`, section `### FEAT-DATA-001` (`:320`): append to its `**PR lineage:**` line (`:346`) ` · [#N](https://github.com/TeneikaAskew/stocks/pull/N) *remediation: session gap alarm and basis check for market_data_intraday, spec [#1868](https://github.com/TeneikaAskew/stocks/pull/1868)*`. No earlier entry is removed. Commit both docs and the plan: `docs(product): record the intraday checks under FEAT-DATA-001`.
- [ ] Site notes, step 1 (preflight). With every code and test commit in place and a clean tree, run `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`. It prints a JSON verdict and installs nothing yet (status `unverified`, exit 1). Copy its `source_identity_sha256`.
- [ ] Site notes, step 2. In `docs/product/03-SITE-TRACEABILITY.md`, table `## Implementation-source notes` (`:1297`), change two rows and no other byte:
  - Add `| FEAT-DATA-001 | ADMIN-02 | source_identity_sha256=<that hash>; <text> |` in the table's sort order, after `FEAT-CICD-001 | SHARED-01` and before `FEAT-DATA-001 | DASHBOARD-01`. Text: `GET /api/admin/data-sources` regroups the freshness audit (`scripts/audit_data_freshness.py`, `audit_all`), which now reads the last five settled sessions of `market_data_intraday` for SPY, QQQ and IWM minute by minute (`_query_intraday_session_gaps`, `lib.eastern_time.session_minute_readings`): a session with no regular-hours bar, or with under 90% of its minutes, adds a stale `market_data_intraday [sessions]` row, so the `market_data_intraday` dataset reads `stale` with `market_data_intraday [sessions] (SPY): stale` in its message; this table's day-presence `[gap]` row is gone; a failed read of the scan answers 503 for an outage and 500 for a defect. Tests: `tests/api/test_health_freshness_session_gaps.py`, `tests/audits/test_audit_intraday_session_gaps.py`. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.
  - Extend the `FEAT-DATA-001 | SHARED-07` row (`:1305`): the new hash, then this change's prose, then ` Earlier: ` and the earlier note's prose from `Purchased account ceiling` to its end, unchanged. This change's prose: `GET /api/health/freshness` (`audit_all`) gains `market_data_intraday [sessions]` rows, one per ticker and session that is MISSING or THIN among the last five settled sessions of SPY, QQQ and IWM, each with `expected_latest` the session and a `detail` that starts `MISSING: ` or `THIN: `, and `overall_status` is `stale` while one exists; this table's `[gap]` rows are gone; the scan reads through the raising query helper, so an outage is a 503 and a defect a 500. `--intraday-gap-since` on the same script lists failing sessions over history and is served by no route. Tests: `tests/api/test_health_freshness_session_gaps.py`, `tests/audits/test_audit_intraday_session_gaps.py`, `tests/lib/test_intraday_session_readings.py`. Source and local tests only; current-head review, hosted CI and deployed verification remain separate, rollout pending.
  - If another FEAT-DATA-001 change has rewritten the SHARED-07 row on `main` since 39ce5d57, keep that row's whole prose after `Earlier:` and tell the owner: done_when[12] names the prose as it was at c698b24e.
  Commit: `docs(site): note the intraday session scan under two components`.
- [ ] Site notes, step 3. Run the same `produce` command again; it now writes the sidecar. Commit: `docs(site): regenerate the source snapshot`.
- [ ] Site notes, step 4. Run `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` (expect exit 0 and `implementation-source identity matched`). If `origin/main` moved, or review changes a watched file later, bring the branch up to date and repeat steps 1 to 4 with the new hash in both rows.
- [ ] Docs audit, branch against `main`: `python3 scripts/maintenance/docs_audit.py > /tmp/audit-branch.txt`; then `git worktree add --detach /tmp/audit-main origin/main`, run the same command there into `/tmp/audit-main.txt`, and `git worktree remove /tmp/audit-main`. Compare the `[P1]`, `[P2]` and `[P3]` finding lines: the branch reports none that `main` does not. A new finding is fixed or reported, not waived. Exit code 2 means the run itself failed, not that the docs are clean.
- [ ] Run: `python3 -m pytest tests/scripts/test_check_generated_docs.py -q` (expect all pass) and `python3 scripts/gate/spec_gate.py --pr origin/main` (expect exit 0).
- [ ] Tick each done_when box in the PR body with its evidence beside it (test name, execution id, file), then mark the PR ready for review. Review cap: two rounds.

## Close-out (not tasks; owner's steps)

Copied from the spec's Close-out, in its order. None of it is done by the implementer of this plan, none of it is a done_when box, and no step writes production data.

1. **Before the merge: the deployed-site before run.** The owner's run of a solyra cloud spec against the Admin page's Data tab (ADMIN-02). That spec, `tests/admin/data-sources-session-gaps.cloud.spec.ts`, does not exist; it is a solyra change under a solyra spec of its own, merged before this PR merges. Until it exists the run cannot be made, and the PR says so.
2. **Deploy**, on the owner's yes: `./gcp/deploy.sh freshness-watchdog` and `./gcp/deploy.sh fetchers`. Neither changes that file. The API needs no step: the merge starts its staging deploy.
3. **Read-only verification** of what was deployed, results on the PR: the watchdog's next scheduled run (its report ends with an `Overall:` line and no traceback; each `market_data_intraday [sessions]` row is recorded with its `detail:` line); one listing run, `--args="--intraday-gap-since=YYYY-MM-DD"` from the oldest of the five settled sessions, which exits 0 and whose summary line gives the sessions scanned and `seconds=N` (it waits while the watchdog's failure issue is open); one basis run over `SPY,2026-10` uploaded as `gs://adept-mountain-474619-d4-trading-data/intraday-lists/verify-basis-a.csv`, exit 0 expected, an exit of 1 put to the owner with its BASIS-FAIL lines; the watchdog's run time before and after from `gcloud run jobs executions list --job=freshness-watchdog --region=us-east1`.
4. **Site evidence, the after run**: the owner's second run of the same cloud spec, once staging has deployed the merge.
5. **The site document**: the SHARED-07 and ADMIN-02 cells of `docs/product/03-SITE-TRACEABILITY.md` brought to the deployed state on a `docs/` branch.
6. **Reword CLAUDE.md's workflow item 3 and Rule 3.7's two lines**, as a FEAT-CICD-001 change with its own approved spec and ready plan. Until it merges, item 3 permits what Task 10's test refuses; the test wins in CI.

File B's plan (`2026-11-13-feat-data-001-intraday-bucket-copy.md`) opens after this implementation is on `main`, and its runbook starts after steps 2 and 3.

Not in the spec's list, from product-delivery Phase 5 step 7: after the merge, on a `docs/` branch, set this plan's `status: done`.
