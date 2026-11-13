---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-13-feat-data-001-watched-ticker-ingest.md
branch: feature/feat-data-001-watched-ticker-ingest
pr: null
status: ready
---

# Watched-ticker ingest job implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Every task cites a spec section and the done_when item it advances (done_when[0] is the first item).

**Goal:** A nightly Cloud Run Job, `fetch-watched-tickers`, fetches daily bars, indicators and ticker info once per distinct ticker that solyra users watch, reading the owner-free set from solyra's `watched-tickers` function, with every failure counted and nothing fabricated.

**Architecture:** One new module `gcp/fetchers/fetch_watched_tickers.py` orchestrates the existing helpers: the job resolves the session, reads the set over HTTPS with a shared secret, drops default-list tickers, caps at 50, plans its own pulls from stored coverage (`_pick_watched_outputsize`), calls `fetch_market_data._run_backfill` once per `(outputsize, data_source)` group, computes indicators only where the session bar exists, refreshes `ticker_info`, verifies every ticker itself through the strict reader, and records one `job_runs` row. Two small changes outside the module: `_run_backfill` gains `outputsize` and `data_source` keywords, and `_backfill_targets`' all-history union gains a `HAVING` clause. The freshness watchdog gains a heartbeat check.

**Tech Stack:** Python 3, pandas, SQLAlchemy over pg8000 (`gcp/database.py`), `urllib.request` for the one HTTPS GET, Cloud Run Jobs and Cloud Scheduler through `gcp/deploy.sh`, pytest under `tests/gcp/` and `tests/audits/`.

**Spec:** `docs/superpowers/specs/2026-11-13-feat-data-001-watched-ticker-ingest.md` (approved through #1875).

**Cross-repo order:** the solyra `watched-tickers` function and the shared secret are deployed first (solyra spec v2, plan solyra#334); this job's code can merge before that, but its first execution (Task 11) and the scheduler (Task 11, after one manual run) wait for the function. Nothing here depends on the stocks lock stages.

## Global Constraints

- The job never reads `watchlists` or `watchlist_history` and never sees an owner, uid or email; it reads only the `tickers` list of the solyra reply (§ Steps item 1, done_when[5]).
- A failed set read is a failed run with zero Alpha Vantage calls, never an empty universe; an empty list is a legitimate zero (REQ-DATA-001).
- `job_runs.status` values are the schema's `'success'` and `'error'` (`gcp/schema.sql:5177`, the convention the watchdog reads); the spec's words "status ok" and "status failed" map to those two values, the only mapping this plan makes.
- Constants, verbatim from the spec: `WATCHED_TICKERS_MAX=50`, `AV_BACKFILL_SLEEP_SECS=1.0`, `--max-retries 0`, `--task-timeout 2400`, `--memory 512Mi`, `--cpu 1`, scheduler `watched-tickers-nightly` at `45 23 * * 1-5` America/New_York, `data_source` stamp `av_watched_backfill`, depth threshold `BACKFILL_DEPTH_THRESHOLD_BARS` (1,500), indicator minimum 15 bars, `ticker_info` age 30 days, watchdog window two sessions.
- No change to `compute_and_upsert_daily_indicators`, `_pick_backfill_outputsize` or `get_ticker_info`; `_verify_post_fetch_rows` is not called by this job (§ Non-goals).
- Every database read in the job goes through `gcp.database.query_to_dataframe_strict`; a failed read fails the run (CLAUDE.md Rule 3.7).
- No em or en dashes in code, logs or docs.

## Review Focus

1. A solyra reply whose `tickers` contains a lower-case or padded symbol, or a non-string: upper-cased and trimmed before dedup, a non-string entry fails the set read (a malformed body), never a `KeyError` inside the pulls. Pinned in Task 3.
2. `WATCHED_TICKERS_MAX` set to `0` or a non-integer in the environment: `0` means nothing is kept and the run records `items_total=0` with note `max=0`; a non-integer fails the run before any vendor call. Pinned in Task 3.
3. The set read returns 200 with `truncated: true`: the job processes what it got and writes `truncated_upstream` in the note so the watchdog can show it. Pinned in Task 3.
4. A coverage row whose `max_date` is after the session date (a stray future-dated bar): treated as current (`None`), never a negative staleness that picks `full`. Pinned in Task 5.
5. `record_job_run` itself failing (it swallows and returns False, `gcp/database.py:1091`): the job logs `job_runs write failed` at ERROR and still exits with the run's own code, so a telemetry failure never masks a data outcome. Pinned in Task 8.

---

### Task 1: `_run_backfill` learns `outputsize` and `data_source`

Spec: § Steps item 3, § Non-goals. Advances done_when[1].

**Files:**
- Modify: `gcp/fetchers/fetch_market_data.py:971-1060` (`_run_backfill`; the plan at `:990-991`, the constant at `:1041`)
- Create: `tests/gcp/test_fetch_watched_tickers.py` (this task adds its first tests; later tasks extend the file)

**Interfaces:**
- Produces: `def _run_backfill(tickers: list | None = None, *, outputsize: str | None = None, data_source: str = 'av_daily_backfill') -> None`. With `outputsize` given and `tickers` non-empty, every explicit ticker is planned at that size (no `_pick_backfill_outputsize` call); `data_source` is the value written at the line that today assigns `'av_daily_backfill'`. Without the keywords the function is byte-for-byte today's behaviour.

- [ ] **Step 1: Write failing tests** `test_run_backfill_forced_outputsize_pulls_every_ticker_at_that_size` (patch `_av_get_full_daily_series` to record `(ticker, outputsize)`, `upsert_dataframe` to record frames, `is_cloud_sql_configured` True, env `ALPHA_VANTAGE_API_KEY`; call `_run_backfill(['AAA','BBB'], outputsize='compact', data_source='av_watched_backfill')`; assert two calls with `'compact'` and every written frame's `data_source` column equals `'av_watched_backfill'`), and `test_run_backfill_without_keywords_keeps_full_and_default_source` (call `_run_backfill(['AAA'])`; assert `'full'` and `'av_daily_backfill'`).
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

### Task 3: Config, the set read, dedup and cap

Spec: § Entry point and schedule, § Steps items 1 and 2. Advances done_when[0].

**Files:**
- Create: `gcp/fetchers/fetch_watched_tickers.py`
- Modify: `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Produces:
  ```python
  JOB_NAME = 'fetch-watched-tickers'
  WATCHED_DATA_SOURCE = 'av_watched_backfill'
  class SetReadError(RuntimeError): ...
  @dataclass(frozen=True)
  class Config:
      url: str; secret: str; max_tickers: int = 50
      @classmethod
      def from_env(cls, env: Mapping[str, str]) -> 'Config'   # WATCHED_TICKERS_URL, WATCHED_TICKERS_READ_SECRET, WATCHED_TICKERS_MAX; raises SetReadError when url or secret is unset, ValueError when max is not an int
  HttpGet = Callable[[str, dict[str, str]], tuple[int, bytes]]        # (url, headers) -> (status, body)
  def read_watched_set(http_get: HttpGet, cfg: Config) -> tuple[list[str], bool]   # (upper-cased tickers in reply order, truncated flag); SetReadError on non-200, non-JSON, missing or non-list tickers, non-string entry
  def dedup_and_cap(tickers: list[str], exclude: Iterable[str], max_tickers: int) -> tuple[list[str], int]   # (kept, overflow)
  def urllib_get(url: str, headers: dict[str, str]) -> tuple[int, bytes]   # the production HttpGet, 30 s timeout
  ```

- [ ] **Step 1: Write failing tests**: `from_env` on missing url or secret raises `SetReadError`; `WATCHED_TICKERS_MAX='x'` raises `ValueError`; `read_watched_set` sends `Authorization: Bearer <secret>`; a 503 raises `SetReadError`; a body without `tickers` raises; a non-string entry raises; `['aapl ', 'AAPL']` becomes `['AAPL']` through `dedup_and_cap`; `dedup_and_cap(60 tickers, TICKERS, 50)` keeps the first 50 in order and returns `overflow=10`; `exclude` drops `SPY`, `IWM`, `QQQ`, `SPX` and the sector ETFs of `fetch_market_data.TICKERS`; `max_tickers=0` keeps nothing with `overflow=len`.
- [ ] **Step 2: Run** `pytest tests/gcp/test_fetch_watched_tickers.py -k "set_read or dedup or config" -v`; expected FAIL.
- [ ] **Step 3: Implement** the module with these functions only.
- [ ] **Step 4: Run** the tests; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): watched-ticker set read, dedup and cap`

### Task 4: Session check

Spec: § Steps item 0. Advances done_when[3].

**Files:**
- Modify: `gcp/fetchers/fetch_watched_tickers.py`, `tests/gcp/test_fetch_watched_tickers.py`

**Interfaces:**
- Produces: `def resolve_session(today: date) -> date | None` returning `today` when `lib.eastern_time.is_session(today)` else `None`; `run()` (Task 8) records `status='success', note='non_session', items_total=0` and returns 0 on `None` before any HTTP or vendor call.

- [ ] **Step 1: Write failing tests**: `resolve_session(date(2026, 11, 26))` (Thanksgiving) is `None`; `date(2026, 11, 14)` (Saturday) is `None`; `date(2026, 11, 13)` returns the date. The run-level assertions (no HTTP call, no upsert, no indicator row) are written in Task 8 against `run()`.
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
  def run(cfg: Config, *, today: date, now: datetime, http_get: HttpGet = urllib_get) -> int
  def main() -> int    # logging.basicConfig as backfill_daily_indicators.main does; Config.from_env(os.environ); run(cfg, today=market_today(), now=datetime.now(timezone.utc)); sys.exit(main()) under __main__
  ```
  `run` order: session check (non-session → `record_job_run(JOB_NAME, started, 'success', items_total=0, note='non_session')`, return 0); set read (failure → `record_job_run(..., 'error', note=f'set_read: {exc}')`, return 2, zero vendor calls); dedup and cap (note `overflow=<n>` when any, `truncated_upstream` when the reply said so); `read_coverage`, `plan_pulls`, one `_run_backfill(group, outputsize=..., data_source=...)` per group; `tickers_with_session_bar`, `compute_indicators`; `refresh_ticker_info`; `verify_tickers`; `record_job_run(JOB_NAME, started, 'error' if failed == kept and kept else 'success', items_total=len(kept), items_processed=len(kept) - len(failed), items_failed=len(failed), rows_written=<sum of bars upserted>, note=<overflow, truncated_upstream, too_short=[...], failed=ticker:reason,...>)`; return 1 when every kept ticker failed, else 0. Per-ticker progress logs `ticker=%s step=%s processed=%d/%d`. A `record_job_run` that returns False logs `job_runs write failed` at ERROR and does not change the exit code.

- [ ] **Step 1: Write failing tests**: a 503 set read → `record_job_run(..., 'error', ...)` once, no `_av_get_full_daily_series` call, return 2; an empty list → `'success'`, `items_total=0`, return 0; sixty tickers with `max_tickers=50` → fifty processed, note contains `overflow=10`; one ticker's Alpha Vantage call raising → counted in `items_failed`, others proceed, return 0; every ticker failing → return 1; Thanksgiving and a Saturday → no HTTP call, no upsert, no indicator call, one `'success'` row with `non_session`; the mixed-set verification case of done_when[2] end to end (`items_failed=3`, the three names and reasons in the note); `record_job_run` called exactly once per run with `job_name='fetch-watched-tickers'`; a `record_job_run` returning False leaves the exit code unchanged and logs at ERROR; a source scan: the module text contains none of `watchlists`, `watchlist_history`, `user_id`, `owner`, `email` (case-insensitive, excluding this test's own strings) and reads `['tickers']` from the reply only; `tests/gcp/test_watchlist_readers_default_owner.py` (lock stage A) stays green once it exists.
- [ ] **Step 2: Run** `pytest tests/gcp/test_fetch_watched_tickers.py -v`; expected FAIL on the new tests.
- [ ] **Step 3: Implement** `run` and `main`.
- [ ] **Step 4: Run** the file and `pytest tests/gcp -q -x`; expected PASS.
- [ ] **Step 5: Commit** `feat(fetchers): fetch-watched-tickers job entry point`

### Task 9: Deploy function, dispatch arm and scheduler

Spec: § Entry point and schedule, § Capacity. Advances done_when[6].

**Files:**
- Modify: `gcp/deploy.sh` (new `deploy_fetch_watched_tickers()` beside `deploy_backfill_daily_indicators()` at `:2175`; add it to `deploy_fetchers()` at `:3207`; a dispatch arm `watched-tickers) _run build_image deploy_fetch_watched_tickers ;;` in the `case` at `:5360`; `_schedule "watched-tickers-nightly" "45 23 * * 1-5" "fetch-watched-tickers"` in `deploy_schedulers()` at `:4438`; help text)
- Test: `tests/gcp/test_deploy_reachability.py` (existing; add `test_watched_tickers_target_deploys_only_the_ingest_job` asserting the arm creates exactly `{"fetch-watched-tickers"}` and that both create and update branches carry `--max-retries 0`... the update branch of `gcloud run jobs update` takes no `--max-retries`, so assert it on the create branch only, as `test_backfill_ticker_declares_max_retries_zero_on_both_branches` does for its job)

**Interfaces:**
- Produces: `gcloud run jobs create fetch-watched-tickers --image "${IMAGE_REF:?...}" --region "${REGION}" --memory 512Mi --cpu 1 --max-retries 0 --task-timeout 2400 --service-account "${SA_EMAIL}" --command "python,-m,gcp.fetchers.fetch_watched_tickers" ${DB_SECRET_FLAG} --set-secrets "WATCHED_TICKERS_READ_SECRET=WATCHED_TICKERS_READ_SECRET:latest" --set-env-vars "${ENV_STRING},WATCHED_TICKERS_URL=https://hajmcfkqmtgidstpggrh.supabase.co/functions/v1/watched-tickers,WATCHED_TICKERS_MAX=50,AV_BACKFILL_SLEEP_SECS=1.0" --quiet 2>/dev/null || gcloud run jobs update ...` (the update branch repeats image, region, task-timeout, command, secret flag, secrets and env vars). Note: `${DB_SECRET_FLAG}` already carries a `--set-secrets`; if gcloud refuses two, fold the new secret into one flag the way `_build_secret_flag` composes it, keeping the secret out of `--set-env-vars`.

- [ ] **Step 1: Write the failing test** in `tests/gcp/test_deploy_reachability.py`.
- [ ] **Step 2: Run** `pytest tests/gcp/test_deploy_reachability.py -v`; expected FAIL (no such arm).
- [ ] **Step 3: Implement** the deploy function, the arm, the `deploy_fetchers` entry and the scheduler line.
- [ ] **Step 4: Run** the file; expected PASS, including `test_every_schedule_target_is_created_by_some_deploy_function` and `test_all_target_creates_every_scheduled_job_and_service`. Run `bash -n gcp/deploy.sh`.
- [ ] **Step 5: Commit** `feat(deploy): fetch-watched-tickers job and its nightly scheduler`

### Task 10: Watchdog heartbeat check

Spec: § Freshness. Advances done_when[9].

**Files:**
- Modify: `scripts/audit_data_freshness.py` (new `_query_watched_tickers_heartbeat(now_utc: datetime) -> list[FreshnessRow]` after `_query_job_duration_regression` at `:1303`; called from `audit_all` at `:1405` after `job_duration_regression` through `_timed`)
- Modify: `tests/audits/test_audit_freshness_job_observability.py`

**Interfaces:**
- Produces: `_query_watched_tickers_heartbeat`: skips with a logged warning and `[]` when `gcp.database.table_exists('job_runs')` is False (as the duration check does); otherwise reads, through `query_to_dataframe_strict(sql, {}, timeout_s=_CHECK_QUERY_TIMEOUT_S)`, the latest `job_runs` row for `job_name = 'fetch-watched-tickers'` and the latest `status = 'success'` row; emits `FreshnessRow(table='job_runs.fetch-watched-tickers heartbeat', ticker=None, status='stale', writer_job='fetch-watched-tickers', detail=...)` when there is no success row or its `started_at` date is before `previous_session(previous_session(today_et))` (two sessions, `lib.eastern_time`); emits `status='warn'` rows `job_runs.fetch-watched-tickers overflow` when the latest row's note contains `overflow=` and `job_runs.fetch-watched-tickers failures` when its `items_failed > 0`, each with the note in `detail`.

- [ ] **Step 1: Write failing tests** with the file's `_patch_strict(monkeypatch, df)` helper: no row → one stale row; latest success three sessions ago → stale; latest success yesterday → no row; a success row whose note has `overflow=10` → one warn row; `items_failed=2` → one warn row; `table_exists` False → `[]`; the heartbeat runs through `_timed` in `audit_all` (patch it and assert it is called).
- [ ] **Step 2: Run** `pytest tests/audits/test_audit_freshness_job_observability.py -v`; expected FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/audits -q`; expected PASS.
- [ ] **Step 5: Commit** `feat(audit): heartbeat check for fetch-watched-tickers`

### Task 11: Secret, manual execution, scheduler, first scheduled run

Spec: § Entry point, § Cross-repo contract (ordering), done_when[7] and done_when[8]. Owner steps and the evidence the PR pastes.

- [ ] **Step 1 (owner):** create the secret, the same value on both sides: `gcloud secrets create WATCHED_TICKERS_READ_SECRET --project=adept-mountain-474619-d4 --replication-policy=automatic` then `gcloud secrets versions add ... --data-file=-` from a generated value, and `supabase secrets set WATCHED_TICKERS_READ_SECRET=<value>` for the solyra function; grant `roles/secretmanager.secretAccessor` on it to `trading-runner@`. Record the secret by name only on the PR.
- [ ] **Step 2:** after the solyra `watched-tickers` function is deployed (solyra#334 plan, Task 6), deploy the job without its scheduler: `./gcp/deploy.sh watched-tickers`.
- [ ] **Step 3:** one manual run: `env -u CLOUDSDK_AUTH_ACCESS_TOKEN gcloud run jobs execute fetch-watched-tickers --region us-east1 --wait`; then `./scripts/db_query_cr.sh -q "SELECT job_name, status, items_total, items_processed, items_failed, rows_written, note FROM job_runs WHERE job_name = 'fetch-watched-tickers' ORDER BY started_at DESC LIMIT 1"`; paste the row and the execution id on the PR (done_when[7]).
- [ ] **Step 4:** only then `./gcp/deploy.sh schedulers` so `watched-tickers-nightly` is created.
- [ ] **Step 5:** after the first scheduled run, the two read-only queries of done_when[8] through `scripts/db_query_cr.sh`, pasted with their execution ids.

### Task 12: Close

Spec: § Done when. Closes done_when[10].

- [ ] Update the FEAT-DATA-001 record in `docs/product/02-FEATURE-CATALOG.md` (line 513: Status, Last reviewed) and add this PR to the FEAT-DATA-001 PR lineage in `docs/product/12-PR-ISSUE-TRACEABILITY.md` (line 346).
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: nothing new.
- [ ] `make test` green; `python3 scripts/gate/spec_gate.py --pr origin/main` ok.
- [ ] PR body: the Capacity numbers of § Capacity (Volume, Velocity, Wall-clock, cost), every done_when line ticked with its evidence, the owner's pasted rows for done_when[7] and [8].
