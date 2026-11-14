---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-14-feat-data-001-watched-ticker-ingest-v3.md
branch: feature/feat-data-001-watched-ticker-ingest-v3
pr: null
status: ready
---

# Watched-ticker ingest job implementation plan (v3: the deploy wiring ships under FEAT-DEPLOY-001)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** A nightly Cloud Run Job, `fetch-watched-tickers`, fetches daily bars, indicators and ticker info once per distinct ticker that web users watch, reading the owner-free set from the stocks tables `watched_tickers` and `user_watchlists` through the strict reader, with every failure counted and nothing fabricated.

**Architecture:** One new module `gcp/fetchers/fetch_watched_tickers.py` orchestrates the existing helpers: the job resolves the session, reads the set with one Cloud SQL query through `gcp.database.query_to_dataframe_strict` (tickers only, no owner column), drops default-list tickers, caps at 50, plans its own pulls from stored coverage (`_pick_watched_outputsize`), calls `fetch_market_data._run_backfill` once per `(outputsize, data_source)` group and sums the row counts it returns, computes indicators only where the session bar exists, refreshes `ticker_info`, verifies every ticker itself through the strict reader, and records one `job_runs` row. Two small changes outside the module: `_run_backfill` gains `outputsize` and `data_source` keywords and returns its upserted row count, and `_backfill_targets`' all-history union gains a `HAVING` clause. The freshness watchdog gains a heartbeat check inside its calendar guard.

**Tech Stack:** Python 3, pandas, SQLAlchemy over pg8000 (`gcp/database.py`), Cloud Run Jobs and Cloud Scheduler through `gcp/deploy.sh`, pytest under `tests/gcp/` and `tests/audits/`.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-data-001-watched-ticker-ingest-v3.md` (approved; supersedes the v2 spec, whose plan this replaces: the v2 branch's commits move to this branch unchanged, since the gate refused the v2 branch's Task 9 deploy change under FEAT-DATA-001).

**Cross-repo order:** the tables of `docs/superpowers/specs/2026-11-14-feat-insight-001-user-watchlist-api.md` must be on main (its PR merged, its `apply-schema-on-change` build green) before this PR is marked ready, because CI's Integration Tests job applies `gcp/schema.sql` from this branch and `tests/integration/test_watched_set_sql.py` needs the two tables; the FEAT-DEPLOY-001 companion (`docs/superpowers/specs/2026-11-14-feat-deploy-001-watched-tickers-deploy.md`) merges after this PR, and only then does Task 13 run the arm. Nothing depends on the lock stages or on solyra.

## Global Constraints

- The job never reads `watchlists` (whole word) or `watchlist_history` and never selects an owner, uid or email column; its one set query, `WATCHED_SET_SQL`, selects `w.ticker` and `COUNT(*) OVER () AS eligible_total` from `watched_tickers`, names `user_watchlists` only inside its `EXISTS` predicate, and excludes `:exclude` (the static `fetch_market_data.TICKERS`) before its `LIMIT :limit` (§ Steps item 1, done_when[5]).
- A failed set read is a failed run with zero Alpha Vantage calls, never an empty universe; an empty list is a legitimate zero (REQ-DATA-001).
- `job_runs.status` values are the schema's `'success'` and `'error'` (`gcp/schema.sql:5177`, the convention the watchdog reads); the spec's words "status ok" and "status failed" map to those two values, the only mapping this plan makes.
- Constants, verbatim from the spec: `WATCHED_TICKERS_MAX=50`, `AV_BACKFILL_SLEEP_SECS=1.0`, `--max-retries 0`, `--task-timeout 2400`, `--memory 512Mi`, `--cpu 1`, scheduler `watched-tickers-nightly` at `45 23 * * 1-5` America/New_York, `data_source` stamp `av_watched_backfill`, depth threshold `BACKFILL_DEPTH_THRESHOLD_BARS` (1,500), indicator minimum 15 bars, `ticker_info` age 30 days, watchdog window two sessions.
- No change to `compute_and_upsert_daily_indicators`, `_pick_backfill_outputsize` or `get_ticker_info`; `_verify_post_fetch_rows` is not called by this job (§ Non-goals).
- Every database read in the job goes through `gcp.database.query_to_dataframe_strict`; a failed read fails the run (CLAUDE.md Rule 3.7).
- No em or en dashes in code, logs or docs.

## Review Focus

1. A set row whose ticker is lower-case or padded (the table's CHECK constraint forbids it, but the module upper-cases and trims anyway before dedup) never reaches the pulls unnormalized; a null ticker in the frame fails the set read. Pinned in Task 3.
2. `WATCHED_TICKERS_MAX` set to `0` or a non-integer in the environment: `0` means nothing is kept and the run records `items_total=0` with note `max=0`; a non-integer is a configuration failure that still records one `job_runs` error row and makes zero vendor calls, because `main()` parses the configuration inside the outcome-recording boundary. Pinned in Tasks 3 and 8.
3. More eligible tickers than the ceiling: the query's window count makes the overflow exact (`overflow = eligible_total - len(rows)`), the static tickers are excluded in SQL before the `LIMIT` so they never consume it, and the note carries `overflow=<n>` for the watchdog; the real-SQL test seeds static tickers among the earliest rows to prove the order of the two clauses. Pinned in Task 3.
4. A coverage row whose `max_date` is after the session date (a stray future-dated bar): treated as current (`None`), never a negative staleness that picks `full`. Pinned in Task 5.
5. `record_job_run` itself failing (it swallows and returns False, `gcp/database.py:1091`): the job logs `job_runs write failed` at ERROR and still exits with the run's own code, so a telemetry failure never masks a data outcome. Pinned in Task 8.

---

### Task 1: `_run_backfill` learns `outputsize` and `data_source`

Spec: § Steps item 3, § Non-goals. Advances done_when[1].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:971-1060` (`_run_backfill`; the plan at `:990-991`, the constant at `:1041`)
- Create: `tests/gcp/test_fetch_watched_tickers.py` (this task adds its first tests; later tasks extend the file)

**Interfaces:**
- Produces: `def _run_backfill(tickers: list | None = None, *, outputsize: str | None = None, data_source: str = 'av_daily_backfill') -> int`, returning the number of rows passed to `upsert_dataframe` in that call (an upsert's row count includes conflict updates, which a stored-row count cannot see); the early exits return 0. With `outputsize` given and `tickers` non-empty, every explicit ticker is planned at that size (no `_pick_backfill_outputsize` call); `data_source` is the value written at the line that today assigns `'av_daily_backfill'`. Without the keywords the behaviour is unchanged apart from the return value.

- [ ] **Step 1: Write failing tests** `test_run_backfill_forced_outputsize_pulls_every_ticker_at_that_size` (patch `_av_get_full_daily_series` to record `(ticker, outputsize)`, `upsert_dataframe` to record frames, `is_cloud_sql_configured` True, env `ALPHA_VANTAGE_API_KEY`; call `_run_backfill(['AAA','BBB'], outputsize='compact', data_source='av_watched_backfill')`; assert two calls with `'compact'` and every written frame's `data_source` column equals `'av_watched_backfill'`), `test_run_backfill_without_keywords_keeps_full_and_default_source` (call `_run_backfill(['AAA'])`; assert `'full'` and `'av_daily_backfill'`), `test_run_backfill_returns_the_rows_it_upserted` (frames of 5 and 7 bars: the call returns 12), and `test_run_backfill_returns_zero_when_no_ticker_returns_data` (`(no data returned)` for every ticker: the call returns 0).
- [ ] **Step 2: Run** `pytest tests/gcp/test_fetch_watched_tickers.py -k run_backfill -v`; expected FAIL (`unexpected keyword argument 'outputsize'`).
- [ ] **Step 3: Implement** the two keywords in `_run_backfill`.
- [ ] **Step 4: Run** the two tests plus `pytest tests/gcp/test_fetch_market_data_backfill_sleep.py tests/gcp/test_backfill_targets_orphans.py -q`; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): _run_backfill takes a forced outputsize and a data_source`

### Task 2: The all-history union counts only real bars from other writers

Spec: § Leaving the set. Advances done_when[4].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:814-833` (`_backfill_targets`, the `BACKFILL_ALL_HISTORY` branch)
- Create: `tests/gcp/test_fetch_market_data_backfill_targets.py` (shared with the lock stage A plan, which adds its own tests to the same file; create it if absent)

**Interfaces:**
- Produces: the `market_data_daily` arm of the union becomes `SELECT ticker FROM market_data_daily GROUP BY ticker HAVING bool_or(close IS NOT NULL AND data_source IS DISTINCT FROM 'av_watched_backfill')`; the `earnings_history` arm is unchanged.

- [ ] **Step 1: Write failing tests** with the `_captured_sql(monkeypatch, backfill_all=True)` pattern of `tests/gcp/test_backfill_targets_orphans.py` to assert the SQL text carries the `HAVING` clause, and a behavioural test with a fake `query_to_dataframe` that evaluates the arm in SQLite over fixtures (watched-only ticker; watched-only plus an indicator-only row with null close and null source; a mixed-source ticker; a null-sourced ticker with a close; an `earnings_history` ticker): only the first two are absent from the targets. The orphan-preservation regression (done_when[4]'s last clause) is written in Task 5 once `plan_pulls` exists.
- [ ] **Step 2: Run** `pytest tests/gcp/test_fetch_market_data_backfill_targets.py -v`; expected FAIL.
- [ ] **Step 3: Implement** the clause.
- [ ] **Step 4: Run** the file and `tests/gcp/test_backfill_targets_orphans.py`; expected PASS.
- [ ] **Step 5: Commit** `fix(fetchers): all-history backfill union ignores watched-only and indicator-only rows`

### Task 3: Config, the set read with its exact overflow, and the second-guard dedup

Spec: § Entry point and schedule, § Steps items 1 and 2. Advances done_when[0].

**Files:**
- Create: `gcp/fetchers/fetch_watched_tickers.py`
- Create: `tests/integration/test_watched_set_sql.py`
- Modify: `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Produces:
  ```python
  JOB_NAME = 'fetch-watched-tickers'
  WATCHED_DATA_SOURCE = 'av_watched_backfill'
  WATCHED_SET_SQL = ("SELECT w.ticker, COUNT(*) OVER () AS eligible_total FROM watched_tickers w "
                     "WHERE EXISTS (SELECT 1 FROM user_watchlists u WHERE u.ticker = w.ticker AND u.removed_at IS NULL) "
                     "AND w.ticker <> ALL(:exclude) "
                     "ORDER BY w.created_at LIMIT :limit")
  class SetReadError(RuntimeError): ...
  @dataclass(frozen=True)
  class Config:
      max_tickers: int = 50
      @classmethod
      def from_env(cls, env: Mapping[str, str]) -> 'Config'   # WATCHED_TICKERS_MAX; raises ValueError when it is not an int
  Query = Callable[..., 'pd.DataFrame']                        # the strict reader's shape: query(sql, params, timeout_s=...)
  @dataclass(frozen=True)
  class WatchedSet:
      tickers: list[str]        # upper-cased and trimmed, frame order (created_at)
      eligible_total: int       # the window count carried by every row; 0 for an empty frame
      overflow: int             # eligible_total - len(frame rows), exact however many the LIMIT cut
  def read_watched_set(query: Query, exclude: Sequence[str], max_tickers: int) -> WatchedSet   # params {'limit': max_tickers, 'exclude': list(exclude)}; SetReadError when the read raises, when a ticker is null or not a string, or when eligible_total is missing or not an integer
  def dedup(tickers: list[str], exclude: Iterable[str]) -> list[str]   # order-preserving unique, drops exclude as a second guard behind the query
  ```

- [ ] **Step 1: Write failing tests**: `Config.from_env({})` gives `max_tickers=50`; `WATCHED_TICKERS_MAX='x'` raises `ValueError`; `read_watched_set` calls the query with `WATCHED_SET_SQL`, `{'limit': max_tickers, 'exclude': list(fetch_market_data.TICKERS)}` and `timeout_s=_SET_QUERY_TIMEOUT_S`; a frame of 50 rows whose `eligible_total` is 60 gives 50 tickers in frame order and `overflow=10`, one of 50 rows with `eligible_total` 51 gives `overflow=1`, an empty frame gives no tickers and `overflow=0`; a raising query becomes `SetReadError`, as do a null ticker, a non-string ticker and a missing or non-integer `eligible_total`; `dedup(['aapl ', 'AAPL', 'SPY'], fetch_market_data.TICKERS)` is `['AAPL']` (the second guard behind the query's own exclusion); a source scan asserts the module's SQL names `user_watchlists` only inside an `EXISTS` predicate, selects no owner, uid or email column, and places `<> ALL(:exclude)` before `LIMIT`; and `tests/integration/test_watched_set_sql.py` (skipped without `DB_HOST`, run by CI's Integration Tests job against ephemeral Postgres with `gcp/schema.sql` applied) seeds `SPY` and `IWM` as the two earliest `watched_tickers` rows with active memberships, 60 eligible tickers after them and one ticker whose only membership is removed, then runs `WATCHED_SET_SQL` with `limit=50` and `exclude=list(fetch_market_data.TICKERS)`: 50 rows, none static, not the removed one, every `eligible_total` 60, in `created_at` order (the mixed static and non-static regression test of done_when[0]); with 51 eligible tickers it returns 50 rows whose `eligible_total` is 51.
- [ ] **Step 2: Run** `pytest tests/gcp/test_fetch_watched_tickers.py -k "set_read or dedup or config or scan" -v`; expected FAIL. `python3 -m pytest tests/integration/test_watched_set_sql.py -q` is skipped here without Postgres; CI's Integration Tests job is its proof.
- [ ] **Step 3: Implement** the module with these functions only.
- [ ] **Step 4: Run** the tests; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): watched-ticker set read from Cloud SQL with its exact overflow`

### Task 4: Session check

Spec: § Steps item 0. Advances done_when[3].

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Produces: `def resolve_session(today: date) -> date | None` returning `today` when `lib.eastern_time.is_session(today)` else `None`; `run()` (Task 8) records `status='success', note='non_session', items_total=0` and returns 0 on `None` before any HTTP or vendor call.

- [ ] **Step 1: Write failing tests**: `resolve_session(date(2026, 11, 26))` (Thanksgiving) is `None`; `date(2026, 11, 14)` (Saturday) is `None`; `date(2026, 11, 13)` returns the date. The run-level assertions (no set query, no upsert, no indicator row) are written in Task 8 against `run()`.
- [ ] **Step 2: Run**; expected FAIL. **Step 3: Implement.** **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): watched-ticker job skips non-sessions`

### Task 5: Coverage, the job's own outputsize decision, and the plan of pulls

Spec: § Steps item 3, § Leaving the set (ownership stamp). Advances done_when[1] and done_when[4].

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `tests/gcp/test_fetch_watched_tickers.py`, `tests/gcp/test_fetch_market_data_backfill_targets.py`

**Interfaces:**
- Consumes: `fetch_market_data._pick_backfill_outputsize(bar_count, max_date, today_et)`, `BACKFILL_DEPTH_THRESHOLD_BARS`, `gcp.database.query_to_dataframe_strict`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Coverage: ticker: str; bar_count: int; max_date: date | None; bootstrapped: bool
  COVERAGE_SQL = "SELECT ticker, COUNT(*) AS bar_count, MAX(date) AS max_date, bool_or(data_source = 'av_watched_backfill') AS bootstrapped FROM market_data_daily WHERE ticker = ANY(:kept) GROUP BY ticker"
  def read_coverage(kept: list[str]) -> dict[str, Coverage]      # strict; absent ticker -> Coverage(t, 0, None, False)
  def _pick_watched_outputsize(bar_count: int, max_date: date | None, bootstrapped: bool, today: date) -> str | None
  def stamp_for(cov: Coverage) -> str                               # WATCHED_DATA_SOURCE if bar_count == 0 or bootstrapped else 'av_daily_backfill'
  def plan_pulls(coverages: dict[str, Coverage], today: date) -> dict[tuple[str, str], list[str]]   # {(outputsize, data_source): tickers}, no None groups
  ```
  `_pick_watched_outputsize`: `'full'` when `bar_count == 0`; `None` when `max_date is not None and max_date >= today`; `_pick_backfill_outputsize(max(bar_count, BACKFILL_DEPTH_THRESHOLD_BARS), max_date, today)` when `bootstrapped`; otherwise `_pick_backfill_outputsize(bar_count, max_date, today)`.

- [ ] **Step 1: Write failing tests** (real `_pick_backfill_outputsize`, no mock of it): no rows → `('full', 'av_watched_backfill')`; current ticker → not in the plan; bootstrapped 300 bars current → not in the plan; bootstrapped 300 bars two sessions behind → `('compact', 'av_watched_backfill')`; bootstrapped 1,800 bars 100 days behind → `'full'`; existing orphan 300 bars from another writer one session behind → `('full', 'av_daily_backfill')`; a `max_date` after `today` → not in the plan; `read_coverage` builds the strict query with `:kept` and fills absent tickers with `(0, None, False)`; a raising strict reader propagates. In `tests/gcp/test_fetch_market_data_backfill_targets.py` add the orphan-preservation regression: write 300 `av_daily_backfill` bars for `ORPH` (no `earnings_history` row), run `plan_pulls` plus Task 1's `_run_backfill` with the group's `data_source`, then evaluate the union arm: `ORPH` is still a target.
- [ ] **Step 2: Run**; expected FAIL. **Step 3: Implement.** **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): watched-ticker pulls planned from stored coverage with an ownership stamp`

### Task 6: Indicators where the session bar exists, then ticker info

Spec: § Steps items 4 and 5. Advances done_when[1].

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Consumes: `fetch_market_data.compute_and_upsert_daily_indicators(ticker, fetch_date, *, level_params)`, `fetch_market_data.read_level_params_for_run(tickers, fetch_date)`, `lib.ticker_info.get_ticker_info(ticker, max_age_days=30)`.
- Produces:
  ```python
  SESSION_BAR_SQL = "SELECT ticker FROM market_data_daily WHERE date = :fetch_date AND ticker = ANY(:kept) AND close IS NOT NULL"
  def tickers_with_session_bar(kept: list[str], fetch_date: date) -> list[str]        # strict
  def compute_indicators(tickers: list[str], fetch_date: date) -> None                 # read_level_params_for_run once, then compute_and_upsert_daily_indicators per ticker, in order
  def refresh_ticker_info(tickers: list[str]) -> None                                   # get_ticker_info(t, max_age_days=30) per ticker; an exception is logged per ticker and does not stop the loop (the verification in Task 7 counts it)
  ```

- [ ] **Step 1: Write failing tests**: a ticker whose fetch returned nothing has no session bar → `compute_and_upsert_daily_indicators` is not called for it (the regression of done_when[1]); the others are called with `fetch_date` and their `level_params`; `get_ticker_info` is called with `max_age_days=30` for every kept ticker and a raising call does not stop the others.
- [ ] **Step 2: Run**; expected FAIL. **Step 3: Implement.** **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): watched-ticker indicators only where the session bar exists; ticker info once per 30 days`

### Task 7: Per-ticker verification

Spec: § Steps item 6. Advances done_when[2].

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Produces:
  ```python
  VERIFY_BARS_SQL = "SELECT m.ticker, m.close, m.atr_14, c.bar_count FROM market_data_daily m JOIN (SELECT ticker, COUNT(*) AS bar_count FROM market_data_daily WHERE ticker = ANY(:kept) GROUP BY ticker) c USING (ticker) WHERE m.date = :fetch_date AND m.ticker = ANY(:kept)"
  VERIFY_INFO_SQL = "SELECT ticker, updated_at FROM ticker_info WHERE ticker = ANY(:kept)"
  INDICATOR_MIN_BARS = 15
  TICKER_INFO_MAX_AGE = timedelta(days=30)
  @dataclass(frozen=True)
  class Verdict: failed: dict[str, str]; too_short: list[str]     # failed: ticker -> 'bars' | 'indicators' | 'ticker_info'
  def verify_tickers(kept: list[str], fetch_date: date, now: datetime) -> Verdict    # both reads strict; a raising read propagates
  ```
  Rules: no row or null `close` → `'bars'`; null `atr_14` with `bar_count >= 15` → `'indicators'`; `bar_count < 15` with a close → `too_short`; `ticker_info` row missing or `updated_at < now - 30 days` → `'ticker_info'` (a ticker can carry one reason only, in the order bars, indicators, ticker_info).

- [ ] **Step 1: Write failing tests**: four tickers; one with no session row (`bars`), one with a null `atr_14` and 300 bars (`indicators`), one with a stale `ticker_info` row (`ticker_info`), one healthy; `too_short` for a ticker with 10 bars and a close; `verify_tickers` never calls `fetch_market_data._verify_post_fetch_rows` (patch it to raise).
- [ ] **Step 2: Run**; expected FAIL. **Step 3: Implement.** **Step 4: Run**; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): watched-ticker per-ticker verification of bars, indicators and ticker info`

### Task 8: `run()` and `main()`

Spec: § Steps items 0 to 7, § Entry point. Advances done_when[0], [1], [2], [3], [5].

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Consumes: Tasks 3 to 7, `gcp.database.record_job_run`, `fetch_market_data._run_backfill` (Task 1).
- Produces:
  ```python
  def run(cfg: Config, *, today: date, now: datetime, query: Query = query_to_dataframe_strict) -> int
  def main() -> int    # logging.basicConfig as backfill_daily_indicators.main does; started = datetime.now(timezone.utc) first; then Config.from_env(os.environ) inside try: a ValueError records record_job_run(JOB_NAME, started, 'error', items_total=0, note=f'config: {exc}') and returns 2 with zero vendor calls; otherwise run(cfg, today=market_today(), now=started); sys.exit(main()) under __main__
  ```
  Configuration parsing sits inside the outcome-recording boundary on purpose: done_when[0] requires a non-integer ceiling to record a `job_runs` row and exit non-zero, and `Config.from_env` raising before `run()` would leave no row.
  `run` order: session check (non-session → `record_job_run(JOB_NAME, started, 'success', items_total=0, note='non_session')`, return 0); set read through `read_watched_set(query, fetch_market_data.TICKERS, cfg.max_tickers)` (failure → `record_job_run(..., 'error', note=f'set_read: {exc}')`, return 2, zero vendor calls); `dedup` as the second guard (note `overflow=<n>` from the set read when above zero); `read_coverage`, `plan_pulls`, one `_run_backfill(group, outputsize=..., data_source=...)` per group; `tickers_with_session_bar`, `compute_indicators`; `refresh_ticker_info`; `verify_tickers`; `record_job_run(JOB_NAME, started, 'error' if kept and len(failed) == len(kept) else 'success', items_total=len(kept), items_processed=len(kept) - len(failed), items_failed=len(failed), rows_written=<the sum of the per-group _run_backfill returns>, note=<overflow, too_short=[...], failed=ticker:reason,...>)` (the terminal status compares counts; `failed` is the dict of Task 7); return 1 when every kept ticker failed, else 0. Per-ticker progress logs `ticker=%s step=%s processed=%d/%d`. A `record_job_run` that returns False logs `job_runs write failed` at ERROR and does not change the exit code.

- [ ] **Step 1: Write failing tests**: a raising set query → `record_job_run(..., 'error', ...)` once, no `_av_get_full_daily_series` call, return 2; an empty frame → `'success'`, `items_total=0`, return 0; a frame of fifty rows with `eligible_total` 60 and `max_tickers=50` → fifty processed, note contains `overflow=10`; one ticker's Alpha Vantage call raising → counted in `items_failed`, others proceed, the recorded status is `'success'`, return 0; every ticker failing → the recorded status is `'error'` and the return is 1; a two-group run (a `'full'` group whose `_run_backfill` returns 12 and a `'compact'` group returning 3) → `rows_written=15`; Thanksgiving and a Saturday → no set query, no upsert, no indicator call, one `'success'` row with `non_session`; the mixed-set verification case of done_when[2] end to end (`items_failed=3`, the three names and reasons in the note); `record_job_run` called exactly once per run with `job_name='fetch-watched-tickers'`; `main()` with `WATCHED_TICKERS_MAX='x'` records exactly one `'error'` row whose note starts with `config:`, makes no vendor call and returns 2 (patch `os.environ`, `record_job_run` and `_av_get_full_daily_series`); a `record_job_run` returning False leaves the exit code unchanged and logs at ERROR; `tests/gcp/test_watchlist_readers_default_owner.py` (lock stage A) and `tests/gcp/test_user_watchlist_isolation.py` (the API spec) stay green once they exist.
- [ ] **Step 2: Run** `pytest tests/gcp/test_fetch_watched_tickers.py -v`; expected FAIL on the new tests.
- [ ] **Step 3: Implement** `run` and `main`.
- [ ] **Step 4: Run** the file and `pytest tests/gcp -q -x`; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): fetch-watched-tickers job entry point`

### Task 9: Deploy function, dispatch arm and scheduler (ships under FEAT-DEPLOY-001)

Spec: § Entry point and schedule, done_when[6]. No commit on this branch.

The spec gate assigns every `gcp/deploy.sh` change to FEAT-DEPLOY-001, so `deploy_fetch_watched_tickers()`, the `watched-tickers` arm, the `watched-tickers-nightly` schedule and their reachability test are the companion spec's `docs/superpowers/specs/2026-11-14-feat-deploy-001-watched-tickers-deploy.md` and its own plan and PR, merged after this PR. done_when[6] is satisfied here by the absence of any `gcp/deploy.sh` change on this branch and by `tests/gcp/test_deploy_reachability.py` staying green.

- [ ] **Step 1: Verify** `git diff origin/main..HEAD --stat -- gcp/deploy.sh` is empty and `python3 -m pytest tests/gcp/test_deploy_reachability.py -q` passes.

### Task 10: Watchdog heartbeat check

Spec: § Freshness. Advances done_when[7].

**Files:**
- Modify: `scripts/audit_data_freshness.py` (new `_query_watched_tickers_heartbeat(now_utc: datetime) -> list[FreshnessRow]` after `_query_job_duration_regression` at `:1303`; called through `_timed` from `_session_dependent_late_checks` at `:1489`, after `enrichment_coverage`, NOT after `job_duration_regression` in `audit_all`: the check is session-dependent, so a calendar failure reaches `audit_all`'s existing `CalendarUnavailable` handler)
- Modify: `tests/audits/test_audit_freshness_job_observability.py`, `tests/audits/test_audit_data_freshness.py`

**Interfaces:**
- Produces: `_query_watched_tickers_heartbeat`: skips with a logged warning and `[]` when `gcp.database.table_exists('job_runs')` is False (as the duration check does); otherwise reads, through `query_to_dataframe_strict(sql, {}, timeout_s=_CHECK_QUERY_TIMEOUT_S)`, the latest `job_runs` row for `job_name = 'fetch-watched-tickers'` and the latest `status = 'success'` row; emits exactly one `FreshnessRow(table='job_runs.fetch-watched-tickers heartbeat', ticker=None, status='skipped', writer_job='fetch-watched-tickers', detail=<the activation condition: the job's first job_runs row>)` and no finding while `job_runs` holds no row at all for the job (the check activates with the first row, written by the close-out's manual execution, so a `freshness-watchdog` redeployed by `deploy.sh all` before the job and its schedule exist does not page; § Freshness, Activation); once any row exists, emits `FreshnessRow(table='job_runs.fetch-watched-tickers heartbeat', ticker=None, status='stale', writer_job='fetch-watched-tickers', detail=...)` when there is no success row or its `started_at` date (Eastern) is before `previous_session(previous_session(today_et))` (two sessions, `lib.eastern_time`; both session steps go through `_calendar(previous_session, ...)`, so a calendar failure yields the explicit `nyse_calendar` row); emits `status='warn'` rows `job_runs.fetch-watched-tickers overflow` when the latest row's note contains `overflow=` and `job_runs.fetch-watched-tickers failures` when its `items_failed > 0`, each with the note in `detail`.

- [ ] **Step 1: Write failing tests** with the file's `_patch_strict(monkeypatch, df)` helper: no row at all → exactly one skipped row whose detail names the activation condition, and the report's overall status unaffected; rows exist but none a success → one stale row; latest success three sessions ago → stale; latest success yesterday → no row; a success row whose note has `overflow=10` → one warn row; `items_failed=2` → one warn row; `table_exists` False → `[]`; the heartbeat runs through `_timed` in `_session_dependent_late_checks` (patch it and assert it is called after `enrichment_coverage`). In `tests/audits/test_audit_data_freshness.py`, a variant of `test_calendar_failure_is_unknown_and_strict_exits_2` with `table_exists` True and a strict reader returning one success row: the report still carries the `nyse_calendar` row and the session-independent rows, and no exception escapes `audit_all`.
- [ ] **Step 2: Run** `pytest tests/audits/test_audit_freshness_job_observability.py -v`; expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/audits -q`; expected PASS.
- [ ] **Step 5: Commit** `feat(audit): heartbeat check for fetch-watched-tickers`

### Task 11: Fix wave after the whole-branch review

Spec: § Steps items 2 and 7, § Config, § Leaving the set, § Freshness (Activation). Advances done_when[0], [1], [4], [5], [7]. One implementer, one scoped re-review; nothing here changes what the job fetches or writes beyond the items listed.

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `gcp/fetchers/fetch_market_data.py`, `scripts/audit_data_freshness.py`
- Modify: `tests/gcp/test_fetch_watched_tickers.py`, `tests/gcp/test_fetch_market_data_backfill_targets.py`, `tests/audits/test_audit_freshness_job_observability.py`, `tests/audits/test_audit_data_freshness.py`

**Items (each with its covering test, written failing first where it names a defect):**
- [ ] The source scan of done_when[5] covers the whole module text with comments stripped: `watchlist_history`, `owner_uid`, `owner_email`, `user_id` and `email` never appear (word boundaries), `user_watchlists` appears exactly once and only inside the EXISTS predicate of `WATCHED_SET_SQL`, and the only column selected from `watched_tickers` is `ticker`.
- [ ] `read_coverage` reads `bootstrapped` as `pd.notna(v) and bool(v)`: a NULL `bool_or` (every stored row with a NULL `data_source`) is not bootstrapped, so `stamp_for` keeps `av_daily_backfill` for a legacy orphan and the ticker stays in the all-history union (§ Leaving the set). Tests for None and NaN.
- [ ] A phase-error `job_runs` row carries `rows_written` so far and `overflow=<n>` in its note when the set read overflowed (§ Steps item 2; Task 8 ruling). Test: an indicators-phase failure after bars were written.
- [ ] `compute_indicators` is removed (dead since Task 8 split it into `tickers_with_session_bar` and `upsert_indicators`); its test moves onto `upsert_indicators`.
- [ ] The three extra `SetReadError` guards of Task 3 each get a direct test.
- [ ] `_run_backfill` raises `ValueError` when `outputsize` or a non-default `data_source` arrives with `tickers` None or empty, so `_run_backfill([], data_source='av_watched_backfill')` can never stamp the whole earnings universe. Tests for both.
- [ ] `Config.from_env` rejects `WATCHED_TICKERS_MAX` below 1 with a `ValueError` naming the variable; `main()`'s existing configuration path records the `error` row with note `config: ...` and returns 2 with zero vendor calls and no set read (done_when[0]). Tests for 0, a negative value and 1.
- [ ] `test_verify_never_calls_post_fetch_rows_check` asserts inside a `run()` test that patches `fetch_market_data._verify_post_fetch_rows` (the standalone version passed vacuously).
- [ ] The heartbeat warn test's fixture uses the job's real note format (`failed=AAA:bars`); the calendar-failure variant asserts that a session-independent row survives; the two-group `run()` test asserts the exit code and the recorded status.
- [ ] Task 10's activation: `_query_watched_tickers_heartbeat` emits one `skipped` row and no finding while `job_runs` holds no row at all for the job, with tests for the pre-activation state and for an absent heartbeat after activation (rows exist, none a success).
- [ ] **Run** `ruff check --select F` on the changed files and `pytest tests/gcp/test_fetch_watched_tickers.py tests/gcp/test_fetch_market_data_backfill_targets.py tests/audits -q`; expected PASS, output pristine.
- [ ] **Commit** in themed commits; the controller re-runs Task 12 (row and snapshot) on the resulting head.

### Task 12: Implementation-source note and source snapshot

Spec: done_when[8] (the FEAT-CICD-001 documentation identity protocol, `.claude/skills/product-delivery/SKILL.md`, "Committed-source documentation identity"). Advances done_when[8].

**Files:**
- Modify: `docs/product/03-SITE-TRACEABILITY.md` (the existing FEAT-DATA-001 SHARED-07 row of the `## Implementation-source notes` table, updated in place: its hash replaced, its sentence kept, the new sentences appended; no other byte)
- Modify: `docs/review-evidence/site-source-snapshot.json` (regenerated)

- [ ] **Step 1: Preflight**: `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json` on the branch head; it refuses with `no declared source-bound note updates` and reports the head's source identity; copy that hash.
- [ ] **Step 2: Write the row** as the existing row's text with `source_identity_sha256=<hash>; <the row's existing sentence>; fetch-watched-tickers (gcp/fetchers/fetch_watched_tickers.py) fetches daily bars, indicators and ticker info once per distinct watched ticker from an owner-free Cloud SQL set query, and scripts/audit_data_freshness.py carries its heartbeat check; tests: tests/gcp/test_fetch_watched_tickers.py, tests/integration/test_watched_set_sql.py, tests/gcp/test_deploy_reachability.py, tests/audits/test_audit_freshness_job_observability.py. |` and commit `docs(site): SHARED-07 implementation-source note for the watched-ticker ingest`.
- [ ] **Step 3: Produce** the snapshot with the Step 1 command (it now installs the record) and commit `docs(evidence): site source snapshot for the watched-ticker ingest`.
- [ ] **Step 4: Verify**: `python3 scripts/maintenance/doc_source_snapshot.py verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000` exits 0 with `status identity-matched`, and `python3 scripts/maintenance/docs_audit.py` on the branch reports nothing `origin/main` does not.

### Task 13: Close

Spec: § Done when. Closes done_when[9].

- [ ] Update the FEAT-DATA-001 record in `docs/product/02-FEATURE-CATALOG.md` (line 513: Status, Last reviewed) and add this PR to the FEAT-DATA-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md` (line 346).
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new.
- [ ] `make test` green; `python3 scripts/gate/spec_gate.py --pr origin/main` ok.
- [ ] PR body: the Capacity numbers of § Capacity (Volume, Velocity, Wall-clock, cost), every done_when line ticked with its evidence; the post-merge close-out comments (Task 14) follow the merge.

### Task 14: Post-merge close-out: deploy, manual execution, scheduler, first scheduled run

Spec: § Post-merge close-out (steps 1 to 5). Production steps after the merge, under the owner's authorization of 2026-11-14, each recorded as a PR comment; none is an acceptance item.

- [ ] **Step 1:** confirm the user-watchlist API PR is merged and its `apply-schema-on-change` build is green (the `watched_tickers` and `user_watchlists` tables exist: that PR's own post-merge close-out comment shows the `information_schema` query), and that the FEAT-DEPLOY-001 companion's implementation PR is merged (its `deploy_fetch_watched_tickers`, arm and schedule are on main).
- [ ] **Step 2:** `./gcp/deploy.sh watched-tickers` builds main once and deploys `fetch-watched-tickers` (no scheduler) and redeploys `fetch-market-data`, `fetch-earnings-history` and `freshness-watchdog` from that image; for each of the four, `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs describe <job> --region us-east1 --format='value(spec.template.spec.template.spec.containers[0].image)'` names the new build's image (close-out step 2).
- [ ] **Step 3:** one manual run: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs execute fetch-watched-tickers --region us-east1 --wait`; then `./scripts/db_query_cr.sh -q "SELECT job_name, status, items_total, items_processed, items_failed, rows_written, note FROM job_runs WHERE job_name = 'fetch-watched-tickers' ORDER BY started_at DESC LIMIT 1"`; an empty active set is a valid first run (`success`, `items_total` 0); paste the row and the execution id in a PR comment (close-out step 3).
- [ ] **Step 4:** only then `./gcp/deploy.sh schedulers` so `watched-tickers-nightly` is created.
- [ ] **Step 5:** after the first scheduled run, the two read-only queries of close-out step 5 through `scripts/db_query_cr.sh`, pasted with their execution ids in a PR comment.
