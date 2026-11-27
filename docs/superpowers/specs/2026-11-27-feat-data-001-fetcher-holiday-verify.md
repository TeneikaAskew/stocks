---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-004, REQ-DATA-001, REQ-OBS-001]
issues: [2152, 1045]
canvases: []
done_when:
  - "tests/gcp/test_fetch_market_data_fail_fast.py::TestVerifyPostFetchRows passes with these new cases: 2026-11-26 (Thanksgiving) and 2026-09-07 (Labor Day) return without calling the query function; 2026-11-27 (the 13:00 ET half day) with 0 rows exits 5; Saturday 2026-05-09 still returns without a query; a calendar that raises (lib.eastern_time._build_session_cache patched to raise, cache reset) propagates its exception instead of exiting 5 or returning; the two holiday cases fail on origin/main"
  - "tests/gcp/test_fetch_market_data_vix.py passes a test that feeds fetch_and_upsert_vix a Yahoo chart payload with settled bars dated 2026-11-25, 2026-11-26 and 2026-11-27 and proves the upsert receives the 2026-11-25 and 2026-11-27 rows only, the return value is 2, and one WARNING names the 2026-11-26 bar, its close and that the date is not an NYSE session; the test fails on origin/main"
  - "The docstring of _verify_post_fetch_rows no longer says a holiday may produce a false positive; the PR body quotes the SELECT over market_data_daily that lists the ^VIX rows dated on NYSE weekday closures and the four rows it returned on 2026-11-27 (2026-05-25, 2026-07-03, 2026-09-07, 2026-11-26, all data_source yahoo), and states that deleting them is a separate owner-authorised --commit the PR does not perform"
  - "The FEAT-DATA-001 catalog record and the PR traceability entry are updated, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# The daily fetcher reads the NYSE calendar: no exit 5 on a holiday, no holiday-dated ^VIX row

## Authority

Written by the automated failure-response routine from #2152 (Thanksgiving 2026-11-26) and #1045
(Labor Day 2026-09-07). No owner instruction exists for it yet. It is not self-approved: it takes
effect only when the owner merges the spec-only PR that adds it, and that merge is the approval its
`status` records; closing the PR unmerged is the refusal.

## Problem

`fetch-market-data-daily` fires at 23:00 ET Monday to Friday, so on every weekday NYSE closure the
job's `fetch_date` is a day with no session. Two things then go wrong in
`gcp/fetchers/fetch_market_data.py` (origin/main `a3ee1aa`):

1. **A false failure.** `_verify_post_fetch_rows` (`:1227-1270`) skips Saturdays and Sundays by
   `weekday() >= 5` and otherwise requires a NOT NULL close for SPY, IWM or QQQ on `fetch_date`.
   On a closure AlphaVantage correctly returns no bars (every ticker logs `no bars` and
   `no matching date`), the count is 0, the job exits 5, and `gcp/failure_notifier.py` opens a
   `gcp-job-failure` issue. Its own docstring calls this an accepted false positive. It happened on
   2026-09-07 (#1045, `fetch-market-data-qq2ls`, closed as transient) and 2026-11-26 (#2152,
   `fetch-market-data-pf5rt`), and recurs on each of the ten weekday closures a year
   (2026: 01-01, 01-19, 02-16, 04-03, 05-25, 06-19, 07-03, 09-07, 11-26, 12-25; 2027: 01-01, 01-18,
   02-15, 03-26, 05-31, 06-18, 07-05, 09-06, 11-25, 12-24, from `lib.eastern_time.holidays_in`).
   Each one pages the owner and costs a triage pass for a run that did nothing wrong.

2. **A fabricated session row.** `fetch_and_upsert_vix` (`:730-775`) writes every Yahoo daily bar
   whose close is not `None`. Yahoo publishes a `^VIX` bar dated on NYSE closures (read on
   2026-11-27 13:5xZ from `query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=10d`:
   a 2026-11-26 bar, close 26.80, beside 2026-11-25 at 28.29 and the forming 2026-11-27 bar), and
   the fetcher stores it. `market_data_daily` held four such rows on 2026-11-27, the only rows with
   a close on any 2024 to 2026 weekday closure for any ticker (read-only `db-query-fcqfh`):

   ```sql
   SELECT ticker, date, close, data_source FROM market_data_daily
   WHERE ticker = '^VIX' AND date IN (<lib.eastern_time.holidays_in(2024..2026)>) ORDER BY date;
   -- 2026-05-25 16.59 yahoo | 2026-07-03 15.81 yahoo | 2026-09-07 15.30 yahoo | 2026-11-26 26.80 yahoo
   ```

   A row dated on a day the exchange did not trade is a value where none exists (REQ-DATA-001).
   `strat_data_builder` reads `vix_close` by date for its `vix_close` / `vix_tercile` features, so a
   holiday-dated row is a session the builder can be handed that never happened.

Both come from the same omission: the fetcher never consults the shared NYSE calendar that
FEAT-DATA-001 made the one source of sessions
(`docs/superpowers/specs/2026-10-19-feat-data-001-shared-market-calendar.md`, superseded by
`2026-11-18-feat-data-001-canonical-calendar-import.md`; `lib/eastern_time.py`;
`pandas-market-calendars` pinned `>=4.3.1` in `requirements.txt` and `requirements-gcp.txt`, `==5.3.0` in `platform/api/requirements.txt`). Neither spec's
consumer inventory lists these two sites, so this spec is the slice for them.

## Non-goals

- The per-ticker loop is unchanged. On a closure it still asks AlphaVantage for each ticker
  (about two calls per ticker, each returning nothing); skipping the whole run on a non-session
  changes what the job writes (the ^VIX trailing window, premarket bars for the next session) and
  is a separate decision.
- No change to what exit 5 means on a session, to the 5-day `_assert_fetch_date_fresh` guard, or to
  the half-day handling: a 13:00 ET close is a session and is verified like any other day.
- No deletion of the four stored rows. The PR lists them and the query; removing them is an
  owner-authorised `--commit`, outside this spec (CLAUDE.md rule 3.5 escape hatches and the
  routine's no-write rule).
- No change to `fetch_and_upsert_vix`'s source, window or settled-bar rule (`close is None` skips
  the forming bar); only the session filter is added.

## Approaches considered

1. Keep the acknowledged false positive and close each issue as transient (the #1045 disposition).
   Rejected: ten pages a year for a non-event, and the ^VIX defect stays.
2. A holiday date set in the fetcher. Rejected: the defect class the shared calendar removed
   (#1076; REQ-DATA-004).
3. Chosen: both sites call `lib.eastern_time.is_session`. A non-session skips the verification
   with an INFO line; a non-session Yahoo bar is dropped with a WARNING line. A calendar failure
   raises (the calendar's contract, rule 3.7), so the job goes red loudly rather than guessing.

## Design

`gcp/fetchers/fetch_market_data.py`:

- `_verify_post_fetch_rows`: replace `if fetch_d.weekday() >= 5: return` with
  `if not is_session(fetch_d): log.info("... %s is not an NYSE session; nothing to verify", fetch_date); return`.
  Weekends are non-sessions, so the weekend case is unchanged. The docstring drops the holiday
  false-positive sentence and names the calendar. `is_session` raises when
  `pandas_market_calendars` is missing or the schedule is empty; nothing catches it here.
- `fetch_and_upsert_vix`: after the `close is None` skip, `if not is_session(d): log.warning("    ^VIX: dropping Yahoo bar dated %s (close=%.2f): not an NYSE session", ...); continue`.
  The returned count and the `upserted N daily rows` line count only the rows written
  (REQ-OBS-001). A payload whose bars are all non-sessions takes the existing `no settled bars`
  path and returns 0.
- Imports: `from lib.eastern_time import is_session` beside the module's existing
  `lib.eastern_time` imports.

Tests, as `done_when` lists them: the verification cases in
`tests/gcp/test_fetch_market_data_fail_fast.py::TestVerifyPostFetchRows` (holiday skip, half-day
verified, weekend unchanged, calendar failure propagates), and the ^VIX case in
`tests/gcp/test_fetch_market_data_vix.py` with a payload built like the module's existing fixtures.
The calendar-failure test resets the cache with `lib.eastern_time._reset_session_cache()` and
patches `lib.eastern_time._build_session_cache` to raise, the pattern the shared-calendar tests use.

### Capacity and cost (CLAUDE.md rule 0)

- **Volume:** one `is_session` call per run for the verification, plus one per Yahoo bar in the
  ^VIX window (`VIX_LOOKBACK_DAYS`, default 7, so at most about seven).
- **Velocity:** no query or network call is added or removed; `is_session` reads the process-wide
  session cache built once from `pandas_market_calendars`.
- **Wall-clock:** the first calendar call builds the 2000-to-2028 schedule once per process (the
  cost the shared-calendar PR recorded, under a second); each later call is a bisect. The job's
  task timeout is unaffected.
- **Cost:** $0; no new job, schedule or resource. On a closure the job still exits 0 after its
  existing AlphaVantage calls.

## Expected effect

On 2026-12-25 and every later weekday closure the job logs the closure and exits 0, `gcp-job-failure`
stays quiet, and `market_data_daily` gains no `^VIX` row for the date. On 2026-11-27 and every other
session, including half days, the verification and the ^VIX upsert behave exactly as today.

## Risks

- **A session the library does not know.** An unscheduled closure (a national day of mourning) is
  a session to the library until its release lists it; that day behaves as today (exit 5 and a
  page), no worse. An unscheduled open on a listed closure drops a real ^VIX bar; the WARNING line
  names the date and close so it can be backfilled with `--date`.
- **Calendar unavailable in the job image.** The job then exits non-zero from the verification or
  the ^VIX step with the import error in the log, instead of exiting 0 on a guess. `requirements-gcp.txt`
  already lists the library, so the image carries it; the shared-calendar PR verified the import in
  the `trading-system` image.
- **The four stored rows stay until deleted.** `done_when[2]` keeps them visible on the PR so the
  owner can decide; nothing in this spec reads them.
