---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-19-feat-data-001-shared-market-calendar.md
branch: feature/feat-data-001-market-calendar
pr: 1546
status: ready
---

# Shared NYSE market calendar implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** One NYSE calendar in `lib/eastern_time.py` that every job, script and the API use, replacing three 2026-only holiday sets and seven ad hoc library wrappers.

**Architecture:** Calendar functions are added to the existing market-time module and backed by `pandas_market_calendars`, imported on first use and cached per process. Consumers keep their public names and return shapes; their bodies call the module. The API image gains the library at the lock files' pin.

**Tech stack:** Python 3, pandas, pandas_market_calendars 5.3.0, FastAPI, pytest.

**Spec:** docs/superpowers/specs/2026-10-19-feat-data-001-shared-market-calendar.md

## Global constraints

- Every calendar function raises when the library is unavailable, and propagates any error from `get_calendar` or `schedule` after a successful import; no weekday-only fallback anywhere (spec § Design, "Fails loud"; REQ-DATA-001).
- Building and extending the session cache happen under one `threading.Lock` (spec § Behaviour, "Single flight").
- The library is imported inside the first calendar call, never at `lib/eastern_time.py` import time (41 importers use only its time-zone helpers).
- `pandas-market-calendars==5.3.0`, the pin in `requirements.lock:128` and `requirements-gcp.lock:129`.
- Consumers keep their public function names, parameters and return shapes (spec § Replacements 2).
- `strat_levels.daily_data_freshness`, `np.busday_count`, the brief walk-backs and earnings T-1 sites are not touched (Spec B and C).
- Commits: conventional format, imperative mood, no AI attribution (CLAUDE.md Rule 2). Run `python3 scripts/gate/spec_gate.py --commit` before each commit and check its exit code directly, not through a pipe.

## Review focus

- A date passed as a tz-aware `datetime` late in the Eastern evening (for example 2026-10-19T02:00Z, which is still 10-18 in New York) must be read as its Eastern market date. Pinned by `test_datetime_inputs_use_eastern_date` in Task 1.
- A date at either edge of the cached range must get its true neighbour: `previous_session(2000-01-01)` is 1999-12-31 and `next_session(2028-12-29)` is 2029-01-02. Pinned by `test_cache_boundaries_find_neighbours` in Task 1.
- Sixteen API threads hitting a cold cache at once must trigger one schedule build and agree. Pinned by `test_concurrent_first_calls_build_once` in Task 1.
- A live `premarket_analysis` row dated on a weekday closure (Thanksgiving) must be evaluated, not crash `session_close`. Pinned by `test_non_session_date_row_anchored_at_16_et` in Task 6.
- On Black Friday, `/api/live/status` at 13:30 ET must report after-hours, not regular. Pinned by `test_black_friday_closes_at_13_et` in Task 3.
- On a Monday holiday before 09:30 ET, `_next_open_et` must return Tuesday 09:30, not Monday. Pinned by `test_next_open_skips_holiday_monday` in Task 3.
- The freshness audit on the Monday after Black Friday weekend must expect Black Friday's data (it is a session), which changes its old lenient behaviour. Pinned by `test_black_friday_is_an_expected_session` in Task 6, and listed in the PR.

---

## Task 1: Calendar core in `lib/eastern_time.py`

Spec: § Design, "Module surface" and "Behaviour"; § Testing items 1 to 4. Advances done_when[0].

**Files:**
- Modify: `lib/eastern_time.py` (append a "NYSE sessions" section after `market_today_sql`)
- Create: `tests/lib/test_market_sessions.py`

**Interfaces (produced, used by every later task):**
- `is_session(day: DateLike) -> bool`
- `previous_session(day: DateLike) -> date` (strictly before)
- `next_session(day: DateLike) -> date` (strictly after)
- `latest_session_on_or_before(day: DateLike) -> date`
- `sessions_between(start: DateLike, end: DateLike) -> list[date]` (inclusive, ascending)
- `session_count(start: DateLike, end: DateLike) -> int` (sessions in `(start, end]`; 0 when `end <= start`)
- `session_close(day: DateLike) -> datetime` (aware UTC; `ValueError` when `day` is not a session)
- `holidays_in(year: int) -> list[date]` (weekdays in `year` that are not sessions, ascending)
- `session_schedule(start: DateLike, end: DateLike) -> pd.DataFrame` (index: session `Timestamp`s; columns `market_open`, `market_close` as UTC timestamps, early closes included). This is the spec's schedule exposed directly so `nyse_sessions` and `expected_session_bars` keep their DataFrame shape (Task 8). The spec's function table does not list it; it is the primitive the other eight are built on.
- Every `DateLike` argument is normalised with the module's existing `market_date()`, so a datetime is read as its Eastern date.

- [ ] Write failing tests in `tests/lib/test_market_sessions.py`:
  - `test_known_dates`: `previous_session("2026-10-19") == date(2026,10,16)`; `is_session("2026-06-19") is False`; `is_session("2026-11-27") is True`; `session_close("2026-11-27") == datetime(2026,11,27,18,0,tzinfo=timezone.utc)`; `is_session("2027-01-18") is False`; `next_session("2027-12-24") == date(2027,12,27)`; `holidays_in(2027) == [date(2027,1,1), date(2027,1,18), date(2027,2,15), date(2027,3,26), date(2027,5,31), date(2027,6,18), date(2027,7,5), date(2027,9,6), date(2027,11,25), date(2027,12,24)]`.
  - `test_parity_2020_2027`: with `valid = {d.date() for d in mcal.get_calendar("NYSE").valid_days("2020-01-01","2027-12-31")}`, for every calendar day `d` from 2020-01-02 to 2027-12-30: `is_session(d) == (d in valid)`, `previous_session(d) == max(s for s in valid if s < d)`, `next_session(d) == min(s for s in valid if s > d)`.
  - `test_session_count_and_between`: `session_count("2026-10-16","2026-10-19") == 1`; `session_count("2026-10-19","2026-10-19") == 0`; `sessions_between("2026-06-17","2026-06-23") == [date(2026,6,17), date(2026,6,18), date(2026,6,22), date(2026,6,23)]`; `latest_session_on_or_before("2026-10-18") == date(2026,10,16)`.
  - `test_session_close_rejects_non_session`: `pytest.raises(ValueError)` for `session_close("2026-06-19")`.
  - `test_datetime_inputs_use_eastern_date`: `is_session(datetime(2026,10,19,2,0,tzinfo=timezone.utc)) is False` (still Sunday 10-18 in New York).
  - `test_schedule_open_close_parity_2000_2027`: `session_schedule("2000-01-03","2027-12-31")` equals the library's `schedule(...)[["market_open","market_close"]]` exactly; the 2002-09-11 row has `market_open == Timestamp("2002-09-11 16:00", tz="UTC")` and `market_close == Timestamp("2002-09-11 20:00", tz="UTC")`.
  - `test_cache_boundaries_find_neighbours`: with the cache reset and first built by `is_session("2000-01-01")`, `previous_session(date(2000,1,1)) == date(1999,12,31)`; with the clock frozen in 2026 (cache through 2028-12-31), `next_session(date(2028,12,29)) == date(2029,1,2)`.
  - `test_fails_loud_without_library`: with `monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)` and the module cache reset, each of the nine functions raises `ImportError`.
  - `test_fails_loud_on_lookup_error`: with the library importable but `get_calendar` patched to return a fake whose `schedule` raises `RuntimeError("boom")`, and the cache reset, each of the nine functions raises `RuntimeError` with `"boom"` in its message.
  - `test_fails_loud_when_get_calendar_raises`: with `get_calendar` patched to raise `RuntimeError("no cal")` and the cache reset, each of the nine functions raises `RuntimeError` with `"no cal"` in its message.
  - `test_empty_schedule_rejected_and_not_cached`: with a fake calendar whose `schedule` returns an empty DataFrame, each of the nine functions raises `RuntimeError`; with the real calendar restored (cache not reset), `is_session("2026-10-19") is True`.
  - `test_schedule_built_once`: wrap the calendar's `schedule` method with a counter; 1,000 mixed calls inside the cached range make exactly one schedule call.
  - `test_concurrent_first_calls_build_once`: cache reset, `schedule` wrapped with a counter and a short sleep; 16 threads released by `threading.Barrier(16)` each call `previous_session("2026-10-19")`; exactly one schedule call, and all 16 results equal `date(2026,10,16)`.
  - `test_concurrent_extensions_both_kept`: with the cache built for 2000 to 2028, two threads released by `threading.Barrier(2)` call `previous_session(date(1995,1,3))` and `next_session(date(2032,12,31))`; results are `date(1994,12,30)` and `date(2033,1,3)`; afterwards, with the schedule counter reset, repeating both calls makes zero schedule calls.
- [ ] Run: `python3 -m pytest tests/lib/test_market_sessions.py -q` (expect FAIL: names not defined)
- [ ] Implement the nine functions in `lib/eastern_time.py`. Hold the schedule in a module-level cache covering 2000-01-01 through December 31 of (current year + 2). Before answering, ensure the cache covers the requested date ±10 calendar days (for ranges, `start - 10` to `end + 10`); otherwise extend it once over the union. Build and extend under one module-level `threading.Lock`, re-checking coverage after acquiring it. Never catch library errors. A build whose schedule has no rows raises `RuntimeError` before the cache is assigned. Provide a private `_reset_session_cache()` for tests. `holidays_in` is weekdays in the year minus sessions.
- [ ] Run: `python3 -m pytest tests/lib/test_market_sessions.py tests/lib/test_eastern_time.py -q` (expect PASS)
- [ ] Commit: `feat(calendar): add shared NYSE session functions to eastern_time`

## Task 2: Library in the API image, with a pin parity test

Spec: § Replacements 4; § Testing item 6. Advances done_when[4].

**Files:**
- Modify: `platform/api/requirements.txt` (add `pandas-market-calendars==5.3.0`)
- Create: `tests/meta/test_market_calendar_pin.py`

- [ ] Write failing test `test_api_pin_matches_locks`: parse the `pandas-market-calendars` / `pandas_market_calendars` pin from `platform/api/requirements.txt`, `requirements.lock` and `requirements-gcp.lock` (normalise `-`/`_`); assert all three equal `5.3.0`.
- [ ] Run: `python3 -m pytest tests/meta/test_market_calendar_pin.py -q` (expect FAIL: no pin in the API file)
- [ ] Add the line to `platform/api/requirements.txt`.
- [ ] Run the test again (expect PASS)
- [ ] Commit: `build(api): install pandas-market-calendars in the API image`

## Task 3: Live router uses the shared calendar

Spec: § Replacements 1 (live.py); § Intended behaviour changes row 1. Advances done_when[2], done_when[3].

**Files:**
- Modify: `platform/api/routers/live.py:108-171` (remove `MARKET_HOLIDAYS_2026`; rewrite `_is_market_open`, `_next_open_et`)
- Modify: `platform/api/main.py:1484-1487` (docstring names the shared calendar instead of `MARKET_HOLIDAYS_2026`)
- Modify: `tests/api/test_most_active_endpoint.py:254` (reference the shared calendar)
- Create: `tests/api/test_live_market_calendar.py`

**Interfaces:** consumes Task 1 `is_session`, `next_session`, `session_close`. `_is_market_open(now_et: datetime) -> tuple[bool, str]` and `_next_open_et(now_et: datetime) -> str | None` keep their signatures and session labels (`"regular"`, `"pre-market"`, `"after-hours"`, `"closed"`).

- [ ] Write failing tests:
  - `test_juneteenth_is_closed`: `_is_market_open(ET 2026-06-19 11:00) == (False, "closed")`.
  - `test_black_friday_closes_at_13_et`: `_is_market_open(ET 2026-11-27 12:59) == (True, "regular")`; `_is_market_open(ET 2026-11-27 13:30) == (False, "after-hours")`.
  - `test_2027_holiday_is_closed`: `_is_market_open(ET 2027-01-18 11:00) == (False, "closed")`.
  - `test_next_open_same_day_premarket`: `_next_open_et(ET 2026-10-19 08:00) == "2026-10-19 09:30:00"`.
  - `test_next_open_skips_holiday_monday`: `_next_open_et(ET 2027-01-18 08:00) == "2027-01-19 09:30:00"`.
  - `test_next_open_after_early_close`: `_next_open_et(ET 2026-11-27 13:30) == "2026-11-30 09:30:00"` (#1542 item 3).
  - `test_next_open_after_friday_close`: `_next_open_et(ET 2026-10-16 17:00) == "2026-10-19 09:30:00"`.
  - `test_regular_hours_unchanged`: `_is_market_open(ET 2026-10-19 10:00) == (True, "regular")`; `_is_market_open(ET 2026-10-19 08:00) == (False, "pre-market")`; `_is_market_open(ET 2026-10-19 17:00) == (False, "after-hours")`.
  - `test_most_active_not_live_on_juneteenth` (in `tests/api/test_most_active_endpoint.py`): `_most_active_label(latest_ts=2026-06-19T15:00Z, snapshot_date_str="2026-06-19", now_utc=2026-06-19T15:10Z) == "2026-06-19"`, not `"live"`.
- [ ] Write failing test `test_cold_calendar_does_not_stall_event_loop` (#1542 item 2): with the session cache reset and the schedule build patched to sleep 1 s, start the app with `TestClient` as a context manager (runs lifespan), then concurrently issue `/api/health` and `/api/dashboard/brief/SPY` via `httpx.AsyncClient`; `/api/health` completes in under 0.3 s.
- [ ] Run: `python3 -m pytest tests/api/test_live_market_calendar.py -q` (expect FAIL on Juneteenth, Black Friday, 2027, the early-close next open and the event-loop test)
- [ ] In the API lifespan (`platform/api/main.py`), warm the calendar with `await run_in_threadpool(lib.eastern_time.is_session, market_today())` so no request pays the build on the loop; a failure there is logged and re-raised by the first request, never swallowed.
- [ ] Rewrite both functions: a day is closed unless `is_session(today)`; the regular window ends at `session_close(today)` converted to ET (13:00 on half days); after-hours runs from that close to 20:00; `_next_open_et` returns today 09:30 when today is a session and now is before 09:30, else `next_session(today)` at 09:30.
- [ ] Run: `python3 -m pytest tests/api/test_live_market_calendar.py tests/api/test_most_active_endpoint.py -q` (expect PASS)
- [ ] Commit: `fix(api): use the shared NYSE calendar for market status`

## Task 4: Market-hours endpoint serves holidays for any year

Spec: § Replacements 3. Advances done_when[5], done_when[6].

**Files:**
- Modify: `platform/api/routers/config.py:30-33, 129-143` (stop importing `MARKET_HOLIDAYS_2026`; add `holidays`)
- Modify: `platform/api/schemas.py:269-274` (`MarketHoursResponse` gains `holidays: list[str]`; `holidays_2026` stays)
- Modify: `platform/api/openapi.json` (regenerated with `python3 scripts/export_openapi.py`, never by hand)
- Create: `tests/api/test_market_hours_endpoint.py`

**Interfaces:** consumes Task 1 `holidays_in`, `session_close`.

- [ ] Write failing test `test_market_hours_payload` (FastAPI `TestClient` on `/api/config/market-hours`, frozen at 2026-10-19 12:00 ET): `body["holidays_2026"] == ["2026-01-01","2026-01-19","2026-02-16","2026-04-03","2026-05-25","2026-06-19","2026-07-03","2026-09-07","2026-11-26","2026-12-25"]`; `body["holidays"]` equals that list followed by `["2027-01-01","2027-01-18","2027-02-15","2027-03-26","2027-05-31","2027-06-18","2027-07-05","2027-09-06","2027-11-25","2027-12-24"]` (literals, not `holidays_in`, so a wrong `holidays_in` fails); `body["early_closes"] == [{"date": "2026-11-27", "close": "13:00"}, {"date": "2026-12-24", "close": "13:00"}, {"date": "2027-11-26", "close": "13:00"}]`.
- [ ] Write failing test `test_market_hours_year_rollover`: frozen at 2026-12-31 23:59 ET, `body["holidays"]` equals `holidays_in(2026) + holidays_in(2027)`; frozen at 2027-01-01 00:01 ET (05:01 UTC), it equals `holidays_in(2027) + holidays_in(2028)` and `[e["date"] for e in body["early_closes"]] == ["2027-11-26", "2028-07-03", "2028-11-24"]`.
- [ ] Write failing test `test_black_friday_close_via_api`: `/api/live/status` with the clock frozen at ET 2026-11-27 13:30 reports not open with session `"after-hours"`.
- [ ] Run: `python3 -m pytest tests/api/test_market_hours_endpoint.py -q` (expect FAIL)
- [ ] Implement: `holidays_2026` = `holidays_in(2026)`; `holidays` = `holidays_in(y) + holidays_in(y + 1)` for `y = market_today().year` (Eastern date, so the window rolls at 00:00 ET); `early_closes` = `[{"date": d.isoformat(), "close": "HH:MM"}]` for every session in those two years whose `session_schedule` close in Eastern time is before 16:00. `MarketHoursResponse` gains `holidays: list[str]` and `early_closes: list[EarlyClose]` with a new `EarlyClose(ApiModel)` holding `date: str` and `close: str`. The docstring states that `holidays_2026` is kept for solyra until Spec C removes it.
- [ ] Run: `python3 scripts/export_openapi.py`, then `python3 -m pytest tests/api/test_market_hours_endpoint.py tests/api/test_openapi_snapshot.py -q` (expect PASS)
- [ ] Commit: `feat(api): serve current and next year holidays from the shared calendar`

## Task 5: Dashboard session count without a silent empty set

Spec: § Replacements 1 (dashboard); § Intended behaviour changes row 5. Advances done_when[2], done_when[3].

**Files:**
- Modify: `platform/api/routers/dashboard.py:38-79` (drop `MARKET_HOLIDAYS_2026` from both import attempts and the `set()` fallback; rewrite `_trading_days_between`)
- Create or extend: `tests/api/test_dashboard_trading_days.py`

**Interfaces:** consumes Task 1 `session_count`, `is_session`. `_trading_days_between(start: date, end: date) -> int` keeps its meaning: sessions strictly between `start` and `end`, both excluded.

- [ ] Write failing tests: `_trading_days_between(date(2026,10,15), date(2026,10,19)) == 1` (Friday only); `_trading_days_between(date(2026,6,18), date(2026,6,22)) == 0` (Juneteenth skipped); `_trading_days_between(date(2026,10,19), date(2026,10,19)) == 0`; `_trading_days_between(date(2026,10,19), date(2026,10,16)) == 0`; `test_brief_stale_days_null_on_calendar_failure`: with `_trading_days_between` patched to raise `RuntimeError`, `GET /api/dashboard/brief/SPY` (daily row fixture) returns `daily.stale_days is None`, not `0`.
- [ ] Run them (expect FAIL on the Juneteenth and failure cases)
- [ ] Implement as 0 when `end <= start` (checked first; without it a same-day session gives -1), else `session_count(start, end) - (1 if is_session(end) else 0)`. In `dashboard_brief` (`dashboard.py:171-180`) the `except Exception` sets `stale_days = None` and logs the exception with `logger.exception`. Other names in the import-fallback block are out of scope and stay.
- [ ] Run: `python3 -m pytest tests/api/test_dashboard_trading_days.py tests/api -q -k "dashboard"` (expect PASS)
- [ ] Commit: `fix(api): count dashboard staleness in NYSE sessions`

## Task 6: Freshness audit uses the shared calendar

Spec: § Replacements 1 (audit); § Intended behaviour changes row 2. Advances done_when[2], done_when[3].

**Files:**
- Modify: `scripts/audit_data_freshness.py:365-449, 646-670` (remove `MARKET_HOLIDAYS_2026`; `most_recent_trading_day` and `_recent_trading_days` call the module)
- Modify: `scripts/audit_data_freshness.py:457-472` (`FreshnessRow` gains `detail: str | None = None`; `to_dict()` and the terminal printer include it)
- Modify: `scripts/audit_data_freshness.py:596-612` (real session closes; non-session DATE rows anchored at 16:00 ET)
- Modify: `platform/api/schemas.py:1411-1420` (`FreshnessRow` gains `detail: Optional[str] = None`, #1542 item 4) and regenerate `platform/api/openapi.json` with `python3 scripts/export_openapi.py`
- Modify: `tests/audits/test_audit_data_freshness.py` (expectations that relied on the 2026 set)

**Interfaces:** consumes Task 1 `is_session`, `latest_session_on_or_before`, `previous_session`. `most_recent_trading_day(now_utc, settle_hour_et=16, settle_lag_days=0) -> date` and `_recent_trading_days(now_utc, n, settle_hour_et=16, settle_lag_days=0) -> list[date]` keep their signatures and the settle-hour and lag model in the docstring.

- [ ] Write failing tests: `test_2027_holiday_skipped`: `most_recent_trading_day(datetime(2027,1,18,22,0))` (17:00 ET on MLK Day) returns `date(2027,1,15)`; `test_black_friday_is_an_expected_session`: `_recent_trading_days(datetime(2026,11,30,22,0), 3)` returns `[date(2026,11,30), date(2026,11,27), date(2026,11,25)]`; `test_winter_close_is_21_utc` and `test_half_day_close_is_18_utc`: the lag computed for a DATE row on 2026-01-15 and on 2026-11-27 uses `21:00` and `18:00` UTC respectively for both the row's close and the expected close (assert on the `lag_hours` the row-evaluation function returns for a fixed `now`); `test_non_session_date_row_anchored_at_16_et`: a `premarket_analysis` row dated 2026-11-26 (Thanksgiving) evaluated at a fixed `now` produces no exception, and its row close is 2026-11-26 21:00 UTC (16:00 EST); `test_calendar_failure_is_unknown_and_strict_exits_2`: with the session functions patched to raise `RuntimeError("boom")`, `audit_all()` returns a report holding a row named `nyse_calendar` with status `"unknown"` whose `to_dict()["detail"]` and the captured terminal output both contain `"RuntimeError"` and `"boom"`; a 1,000-character message is cut to 300 characters in `detail`; `main()` with `--strict` exits `2`; `test_freshness_api_carries_calendar_detail`: `TestClient` `GET /api/health/freshness` with the calendar patched to raise returns a `tables` entry with `table == "nyse_calendar"` and `"RuntimeError"` in its `detail`.
- [ ] Run: `python3 -m pytest tests/audits/test_audit_data_freshness.py -q` (expect FAIL on all six)
- [ ] Implement: lag 0 uses `latest_session_on_or_before(cron_day)`; each lag step uses `previous_session`; `_recent_trading_days` walks back with `previous_session` from the anchor. At `:596-612`, `expected_close_dt` is `session_close(expected_date)`; a DATE row whose date is a session uses `session_close(row_date)`; a DATE row whose date is not a session is anchored at 16:00 Eastern on that date via the module's Eastern helpers and never passed to `session_close` (all converted to naive UTC to match the existing lag math). `detail` is `f"{type(e).__name__}: {e}"[:300]`. `audit_all` catches the calendar error once, appends the `nyse_calendar` unknown row and skips session-dependent checks; `main` exits 2 under `--strict` when that row is present.
- [ ] Run the audit test file (expect PASS). For every pre-existing assertion that changes, write one line for the PR body: the test, the old value, the new value, the reason (Black Friday is a session).
- [ ] Commit: `fix(audit): use the shared NYSE calendar for expected sessions`

## Task 7: Playbook resolver uses the shared calendar

Spec: § Replacements 1 (resolver); § Intended behaviour changes row 3. Advances done_when[2], done_when[3].

**Files:**
- Modify: `gcp/premarket_playbook_resolver.py:65-79, 534, 584` (remove the `scripts.audit_data_freshness` import and `NYSE_FULL_CLOSURES`; use `is_session`)
- Modify: `tests/gcp/test_premarket_playbook_resolver.py:339-360`

**Interfaces:** consumes Task 1 `is_session`. The weekend SQL filter at `:518-524` is unchanged (Spec C).

- [ ] Write failing tests on `classify_date_outcome(analysis_date, n_resolved, n_skipped, now_et)`, with `n_resolved=0, n_skipped=3` and `now_et` a later date: `date(2025,7,4)` returns `'benign_holiday'` (today `'failed'`); `date(2027,1,18)` returns `'benign_holiday'`. Keep the existing Black Friday case: `date(2026,11,27)` still returns `'failed'`.
- [ ] Run: `python3 -m pytest tests/gcp/test_premarket_playbook_resolver.py -q` (expect FAIL on the 2025 and 2027 cases)
- [ ] Replace `analysis_date in NYSE_FULL_CLOSURES` with `not is_session(analysis_date)`, and update the comment block at `:65-79` to cite the shared calendar.
- [ ] Run the resolver tests (expect PASS)
- [ ] Commit: `fix(resolver): recognise NYSE holidays in any year`

## Task 8: Research and analysis wrappers delegate to the module

Spec: § Replacements 2. Advances done_when[1].

**Files:**
- Modify: `lib/strat_levels.py:1705-1749` (`_trading_days_between` returns `session_count(source_ts, ref_ts)`; the ImportError approximation is removed)
- Modify: `gcp/research/magnitude_engine/evaluation_windows.py:110-131, 152-176` (`last_expected_session` returns `previous_session(window.end)`; `expected_session_bars` reads `session_schedule`; both lose their direct library imports and the `BDay` fallback)
- Modify: `gcp/fetchers/evaluate_ew_strikes.py:196-205` (`nyse_sessions(start, end)` returns `session_schedule(start, end)`)
- Tests: `tests/lib/test_strat_levels_freshness.py`, `tests/lib/test_silent_fallback_fixes.py`, `tests/gcp/test_magnitude_evaluation_windows.py`, `tests/gcp/test_evaluate_ew_strikes.py`

**Interfaces:** consumes Task 1 `session_count`, `previous_session`, `session_schedule`. Signatures unchanged; `nyse_sessions` keeps its DataFrame shape.

- [ ] Write failing test `test_expected_session_bars_delayed_open` in `tests/gcp/test_magnitude_evaluation_windows.py`: `expected_session_bars` for a window covering only 2002-09-11 at 15-minute bars expects 16 bars, not 26.
- [ ] Write failing test `test_strat_levels_raises_without_calendar` in `tests/lib/test_silent_fallback_fixes.py`: with the library made unimportable and the session cache reset, `_trading_days_between(pd.Timestamp("2026-10-16"), pd.Timestamp("2026-10-19"))` raises `ImportError` (today it returns the calendar/1.4 estimate).
- [ ] Run both (expect FAIL)
- [ ] Rewrite the four functions as listed.
- [ ] Run: `python3 -m pytest tests/lib/test_strat_levels_freshness.py tests/lib/test_silent_fallback_fixes.py tests/gcp/test_magnitude_evaluation_windows.py tests/gcp/test_evaluate_ew_strikes.py -q` (expect PASS; any test asserting the old fallback values is updated and listed for the PR)
- [ ] Commit: `refactor(calendar): route research wrappers through the shared NYSE calendar`

## Task 9: Fetcher and script wrappers delegate to the module

Spec: § Replacements 2. Advances done_when[1].

**Files:**
- Modify: `gcp/fetchers/fetch_av_historical_options.py:166-189` (`_trading_days` returns `[d.strftime("%Y-%m-%d") for d in sessions_between(start, end)]`)
- Modify: `scripts/fetch_alphavantage_options.py:58-125` (`is_trading_day` returns `is_session(date)`; `get_trading_days` returns `sessions_between(...)`; remove `CALENDAR_AVAILABLE` and the module-level library import; `skip_weekends` stays in the signature and is documented as having no effect, since sessions never include weekends)
- Modify: `scripts/fetch_alphavantage_intraday.py:50-90` (`is_month_all_non_trading_days` returns `len(sessions_between(first, last)) == 0`; remove `CALENDAR_AVAILABLE` and the library import)
- Tests: `tests/gcp/test_fetch_av_historical_options.py`; create `tests/scripts/test_av_calendar_helpers.py` (no existing test covers the two scripts' helpers)

- [ ] Write failing test `test_trading_days_raises_without_calendar` in `tests/gcp/test_fetch_av_historical_options.py`: with the library unimportable, `_trading_days(date(2026,5,22), date(2026,5,26))` raises `ImportError` (today it returns weekdays, including Memorial Day).
- [ ] Write failing tests in `tests/scripts/test_av_calendar_helpers.py`: `scripts.fetch_alphavantage_options.is_trading_day(date(2026,6,19)) is False`; `get_trading_days("2026-06-17","2026-06-23") == [date(2026,6,17), date(2026,6,18), date(2026,6,22), date(2026,6,23)]`; with the library unimportable, `is_trading_day(date(2026,6,19))` raises `ImportError` (today it returns `True` from the weekday fallback); `scripts.fetch_alphavantage_intraday.is_month_all_non_trading_days("2026-06") is False`.
- [ ] Run both files (expect FAIL on the fail-loud cases)
- [ ] Rewrite the four helpers as listed.
- [ ] Run: `python3 -m pytest tests/gcp/test_fetch_av_historical_options.py tests/scripts/test_av_calendar_helpers.py -q` (expect PASS)
- [ ] Commit: `refactor(calendar): route fetcher calendar helpers through the shared module`

## Task 10: Guard against new calendars and holiday lists

Spec: § Testing item 5. Advances done_when[1], done_when[2].

**Files:**
- Create: `tests/meta/test_market_calendar_single_source.py`

- [ ] Write `test_no_direct_calendar_import`: walk `lib/`, `gcp/`, `scripts/`, `platform/api/` Python files with `ast`; fail on any `import pandas_market_calendars` or `from pandas_market_calendars ...` outside `lib/eastern_time.py`, naming file and line.
- [ ] Write `test_no_hardcoded_holiday_sets`: in the same files, fail on any assignment whose target name contains `HOLIDAY` or `CLOSURE` (case-insensitive) and whose value is a set, list, tuple or frozenset literal containing a `date(...)` call.
- [ ] Write `test_retired_names_absent`: no occurrence of `MARKET_HOLIDAYS_2026` or `NYSE_FULL_CLOSURES` in those directories.
- [ ] Run: `python3 -m pytest tests/meta/test_market_calendar_single_source.py -q` (expect PASS after Tasks 3 to 9; a failure names the remaining site, which is fixed in its owning file before continuing)
- [ ] Commit: `test(meta): guard the single NYSE calendar source`

## Task 11: Cross-repo contract and first-call latency

Spec: § Replacements 3; § Capacity. Advances done_when[5], done_when[6].

- [ ] Copy the regenerated `platform/api/openapi.json` over solyra's `tests/fixtures/stocks-openapi.json` in a local solyra checkout, without committing, and run solyra's `npm test -- src/mocks/contract.test.ts`. Expect PASS. Record the command and result for the PR body. If solyra's mock for `/api/config/market-hours` lacks a now-required `holidays` field, record that the solyra sync PR must add it.
- [ ] Measure first-call latency with the API's requirements in a fresh virtualenv: `python3 -c "import time,datetime as d; t=time.perf_counter(); from lib.eastern_time import is_session; is_session(d.date(2026,10,19)); print(round((time.perf_counter()-t)*1000))"`. Record the number in the PR's Capacity section.
- [ ] Revert the solyra fixture copy (`git -C <solyra> checkout -- tests/fixtures/stocks-openapi.json`).

## Task 12: Close

Spec: § Done when. Closes done_when[7]; sets up the after-merge steps of done_when[5] and [6].

- [ ] Update the FEAT-DATA-001 record in `docs/product/02-FEATURE-CATALOG.md` (Status, Last reviewed 2026-10-19 or the merge date; Code adds `lib/eastern_time.py` (NYSE sessions))
- [ ] Add this PR under FEAT-DATA-001 in `docs/product/12-PR-ISSUE-TRACEABILITY.md`
- [ ] PR body lists every changed test expectation from Tasks 3 to 9 with its reason; adds `Closes #1076` and `Closes #1542`; adds `Canvas check pending (report-only): https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN`; fills Capacity with the measured numbers.
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`: no new finding.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` passes.
- [ ] After merge, as named close-out steps: dispatch `deploy-staging.yml` from main, read `/api/config/market-hours` and `/api/live/status` on staging for the done_when[5] values, record them on the PR; open the solyra contract sync PR (`npm run contract:sync`, update the market-hours mock if needed); then set this plan's `status: done` on a `docs/` branch.
