---
feat_id: FEAT-DATA-001
req_ids: [REQ-DATA-004, REQ-DATA-001, REQ-DEPLOY-001]
issues: [1076]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "tests/lib/test_market_sessions.py passes: known 2026 and 2027 dates, day-by-day parity with the NYSE library for 2020-2027, and every calendar function raising when pandas_market_calendars is unimportable"
  - "A guard test passes proving no hard-coded holiday date set and no direct pandas_market_calendars import exists under lib/, gcp/, scripts/ or platform/api/ outside lib/eastern_time.py"
  - "git grep for MARKET_HOLIDAYS_2026 and NYSE_FULL_CLOSURES returns no match in lib/, gcp/, scripts/ or platform/api/"
  - "Frozen-clock consumer tests pass: the live router (Juneteenth closed, Black Friday regular before and after-hours after its 13:00 ET close, 2027-01-18 closed, _next_open_et across a holiday Monday and a Friday close, the most-active label), the dashboard (Juneteenth skipped, exclusive end, calendar failure returns stale_days null), the freshness audit (2027 holiday, Black Friday expected, winter and half-day session closes, calendar failure gives an unknown row and --strict exit 2) and the playbook resolver (2025 and 2027 holidays benign, Black Friday still a failure); the PR lists every pre-existing expectation that changed with its reason"
  - "platform/api/requirements.txt pins pandas-market-calendars==5.3.0 and a test proves the pin equals requirements.lock and requirements-gcp.lock"
  - "A TestClient test of /api/config/market-hours proves 2026-06-19 is in holidays_2026 and holidays, 2027 holidays are in holidays, and early_closes holds 2026-11-27 at 13:00; the first calendar call's latency with the API requirements is recorded in the PR; after merge, the same values read from staging are recorded on the PR as a close-out step"
  - "The stocks OpenAPI snapshot is regenerated, and solyra's contract test passes when run locally against it before merge; the solyra contract sync PR follows the merge as a close-out step"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record and 12-PR-ISSUE-TRACEABILITY list this PR"
status: approved
supersedes: null
---

# Shared NYSE market calendar (Spec A of the trading-day standardization)

## Problem

The codebase has no single answer to "is this a trading session" or "what
was the previous session". A read-only audit on 2026-10-18 (Appendix A)
found about 13 separate calendar implementations and about 20 call sites that
step back one calendar day where a trading session is meant.

Three defects are live today or have a fixed date:

1. **Hard-coded 2026-only holiday sets expire on 2027-01-01.**
   `platform/api/routers/live.py:109`, `scripts/audit_data_freshness.py:367`
   and `gcp/premarket_playbook_resolver.py:79` (derived from the audit's set)
   recognise no holiday after 2026. From that date the freshness audit
   false-alarms, the playbook resolver marks holiday dates `failed` (the #1068
   incident class) and the API reports the market open on holidays. Tracked in
   #1076. Verified against `pandas_market_calendars`: 2027 weekday closures are
   01-01, 01-18, 02-15, 03-26, 05-31, 06-18, 07-05, 09-06, 11-25, 12-24.
2. **The API's set is wrong for 2026.** `live.py` omits Juneteenth
   (2026-06-19, verified closed: the library's sessions for 06-17..06-23 are
   06-17, 06-18, 06-22, 06-23) and lists Black Friday 2026-11-27 as closed,
   although NYSE trades until 13:00 ET (library close 18:00 UTC). The error
   reaches `_is_market_open`, `_next_open_et`, `dashboard._trading_days_between`,
   `main._most_active_label` and `/api/config/market-hours`, which solyra's
   replay picker reads.
3. **Library wrappers fall back silently.** Several wrappers around
   `pandas_market_calendars` answer weekday-only when the import or a lookup
   fails (Appendix A, B-list), and `dashboard._trading_days_between` uses no
   holidays at all if its import fails. Each is a CLAUDE.md §3.7 silent
   fallback.

The API image cannot share the jobs' calendar today:
`pandas-market-calendars` is pinned in `requirements.lock` and
`requirements-gcp.lock` (5.3.0) but absent from `platform/api/requirements.txt`,
the only file `platform/Dockerfile` installs. That is why the API keeps its own
list.

## Non-goals

- The earnings options pipeline and every earnings T-1 call site (Spec B,
  which implements the served earnings-options coverage section of
  `2026-10-12-feat-ops-001-av-operations.md` on this calendar, plus the
  backfill fetcher's session choice, `backtest_playability`,
  `earnings_event_outcomes` and the ranker SQL).
- Migrating the other likely-bug call sites, `np.busday_count`, the brief and
  refresh walk-backs, `strat_levels.daily_data_freshness` semantics, solyra's
  `ReplayControl`, and the unsure items (Spec C).
- A sessions table in Cloud SQL. SQL keeps the "latest prior row" pattern it
  already uses correctly (Appendix A, models).
- The `earnings_reactions` volume drop after May 2026 (Spec D).

## Approaches considered

- **Add the library to the API image (chosen).** One Python module serves
  jobs, scripts and the API; the hard-coded sets are deleted. Cost measured
  below is small.
- Library plus a generated `market_sessions` table: more reach for SQL, but a
  second copy of the calendar that must be kept in sync and extended yearly.
  Deferred until a SQL consumer needs it.
- Sessions table only, read by the API: keeps the API image unchanged but makes
  every market-open check a database call and makes the API depend on a job
  having run.

The module lives in `lib/eastern_time.py`, the existing market-time module
(CLAUDE.md Rule 1: extend before creating). Issue #1076 suggested a new
`lib/market_calendar.py`; extending the existing module keeps REQ-DATA-004's
"one place" literal.

## Design

### Module surface (`lib/eastern_time.py`)

All arguments and results are Eastern market dates unless stated.

| Function | Returns |
|---|---|
| `is_session(d)` | True when NYSE trades on `d`, half days included |
| `previous_session(d)` | Last session strictly before `d` |
| `next_session(d)` | First session strictly after `d` |
| `latest_session_on_or_before(d)` | `d` when it is a session, else `previous_session(d)` |
| `sessions_between(start, end)` | Sessions in `[start, end]`, ascending |
| `session_count(start, end)` | Number of sessions in `(start, end]` |
| `session_close(d)` | Close as an aware UTC datetime; 13:00 ET on half days; raises when `d` is not a session |
| `holidays_in(year)` | Weekday full closures in `year`, ascending |
| `session_schedule(start, end)` | The schedule itself: one row per session in `[start, end]`, with the library's actual UTC `market_open` and `market_close` (early closes and delayed opens included, e.g. 2002-09-11 opened at 12:00 ET) |

`session_schedule` is the primitive the other eight are built on. It lets
`nyse_sessions` and `expected_session_bars` keep their DataFrame shape and
their real open times instead of assuming 09:30 ET (review finding on #1540).

Behaviour:

- Backed by `pandas_market_calendars.get_calendar("NYSE")`. The library is
  imported inside the first calendar call, never at module import, so the 41
  importers that use only the time-zone helpers do not pay for it.
- Fails loud: an import error or a lookup error propagates. No weekday-only
  fallback anywhere (REQ-DATA-001, §3.7).
- Cached: one schedule per process over a padded range (2000 to current year
  plus 2); a date outside it extends the cache once. Year-agnostic, so it
  closes #1076.

### Replacements in this spec

1. Hard-coded sets and their consumers:
   - `platform/api/routers/live.py`: `MARKET_HOLIDAYS_2026` removed;
     `_is_market_open` and `_next_open_et` use `is_session`, `session_close`
     and `next_session`, so Black Friday closes at 13:00 ET.
   - `platform/api/routers/dashboard.py:_trading_days_between` keeps its
     meaning, sessions strictly between `start` and `end` with both excluded
     (today's bar does not exist yet): `session_count(start, end)` minus one
     when `end` is itself a session. Its silent `set()` holiday fallback is
     removed. The caller in `dashboard_brief` (`dashboard.py:178-180`) catches
     every exception and reports `stale_days = 0`, which would show a calendar
     failure as fresh data; it reports `stale_days: null` instead (the
     response schema already allows null), so the failure is visible.
   - `platform/api/main.py:_most_active_label` keeps calling
     `live._is_market_open`.
   - `scripts/audit_data_freshness.py`:
     - `MARKET_HOLIDAYS_2026` is removed; `most_recent_trading_day` and
       `_recent_trading_days` use the module, keeping each writer's settle
       hour and lag policy.
     - The fixed 20:00 UTC close (`audit_data_freshness.py:596-612`, #1066) is
       replaced by `session_close`: a DATE row's close and the expected close
       are the session's real close, so winter (21:00 UTC) and half days
       (18:00 UTC on 2026-11-27) are measured correctly.
     - A calendar failure is reported as one explicit row named
       `nyse_calendar` with status `unknown` and the error text, and
       `--strict` exits 2 when that row is present. No check falls back to
       weekdays.
   - `gcp/premarket_playbook_resolver.py`: `NYSE_FULL_CLOSURES` and its import
     from `scripts/` are removed in favour of `is_session`.
2. Library wrappers become thin calls to the module, losing their fallbacks:
   `lib/strat_levels.py:_trading_days_between`,
   `gcp/research/magnitude_engine/evaluation_windows.py` (`last_expected_session`,
   `expected_session_bars`), `gcp/fetchers/evaluate_ew_strikes.py`
   (`nyse_sessions`, `scoring_session`), `gcp/fetchers/fetch_av_historical_options.py:_trading_days`,
   `scripts/fetch_alphavantage_options.py` (`is_trading_day`, `get_trading_days`),
   `scripts/fetch_alphavantage_intraday.py:is_month_all_non_trading_days`.
   Their public signatures and return shapes stay the same.
3. `/api/config/market-hours` adds `holidays` (current and next year, from
   `holidays_in`) and `early_closes`, a list of `{date, close}` objects for
   the same two years with `close` as `HH:MM` Eastern (for example
   `{"date": "2026-11-27", "close": "13:00"}`), so clients no longer read the
   static 16:00 `regular.close` on half days. `holidays_2026` stays, filled from the module, so solyra's
   replay picker is unchanged until Spec C moves it to `holidays` and removes
   the old key. The vendored OpenAPI snapshot and solyra's contract test are
   updated in the same change set (solyra CLAUDE.md Rule 6).
4. `platform/api/requirements.txt` adds `pandas-market-calendars==5.3.0`, the
   pin both lock files already carry.

### Intended behaviour changes

| Surface | Before | After |
|---|---|---|
| `/api/live/status`, `_next_open_et`, most-active label | Juneteenth a session; Black Friday closed; 2027 has no holidays | Correct closures for any year; Black Friday a 13:00 ET session |
| Freshness audit | Correct for 2026 only | Correct for any year |
| Playbook resolver | Correct for 2026 only | Correct for any year, including pre-2026 backfills |
| Freshness audit lag math | Closes assumed at 20:00 UTC (one hour early all winter, two hours late on Black Friday) | Each session's real close |
| Freshness audit on calendar failure | n/a (no calendar used) | One `nyse_calendar` row, status `unknown`; `--strict` exits 2 |
| `/api/config/market-hours` | `holidays_2026` only | Adds `holidays` and `early_closes` for the current and next year |
| Library wrappers | Weekday-only on import or lookup failure | Raise |
| `dashboard._trading_days_between` | No holidays when its import fails | Holiday-aware; import failure raises |
| `dashboard_brief` on calendar failure | `stale_days: 0` (reads as fresh) | `stale_days: null` |

`strat_levels.daily_data_freshness` is deliberately unchanged: it flags a
post-holiday session as stale by design, and changing that alters what the
dashboard and brief show. Spec C decides it.

### Testing

Hermetic, against the real library (no calendar mocks except the
unimportable case):

1. Known dates: Monday 2026-10-19 gives previous session Friday 2026-10-16;
   2026-06-19 is not a session; 2026-11-27 is a session closing
   2026-11-27T18:00Z; 2027-01-18 is not a session; the next session after
   2027-12-24 is Monday 2027-12-27.
2. Parity: for every calendar day 2020-01-01 to 2027-12-31, `is_session`,
   `previous_session` and `next_session` agree with the library's raw schedule.
3. Fail loud: with `pandas_market_calendars` unimportable, every function
   raises.
4. Cache: repeated calls within the cached range make one schedule build.
5. Guard: no hard-coded holiday date set and no direct
   `pandas_market_calendars` import outside `lib/eastern_time.py` under
   `lib/ gcp/ scripts/ platform/api/`.
6. Pin parity: `platform/api/requirements.txt`, `requirements.lock` and
   `requirements-gcp.lock` pin the same version.
7. Consumer tests with a frozen clock, so a wrong wiring fails even when the
   module parity suite passes (the existing live-router tests only assert
   field presence against the wall clock):
   - Live router: 2026-06-19 closed; 2026-11-27 regular at 12:59 ET and
     after-hours at 13:30 ET; 2027-01-18 closed; `_next_open_et` from a
     holiday Monday before 09:30 gives Tuesday 09:30 and from Friday after
     the close gives Monday 09:30; `_most_active_label` is not "live" on
     2026-06-19 during regular hours.
   - Market hours: a TestClient request returns 2026-06-19 in `holidays_2026`
     and `holidays`, 2027 holidays in `holidays`, and
     `{"date": "2026-11-27", "close": "13:00"}` in `early_closes`.
   - Dashboard: Thursday to Monday counts 1 session; 2026-06-18 to 2026-06-22
     counts 0; with the calendar failing, `dashboard_brief` returns
     `stale_days: null`.
   - Freshness audit: 2027-01-18 is skipped; Black Friday is an expected
     session; a DATE row's lag uses 21:00 UTC in January and 18:00 UTC on
     2026-11-27; with the calendar failing, the report holds a `nyse_calendar`
     row with status `unknown` and `--strict` exits 2.
   - Playbook resolver: `classify_date_outcome` returns `benign_holiday` for
     2025-07-04 and 2027-01-18, and still `failed` for 2026-11-27.
8. Existing tests for these consumers pass; each changed expectation is listed
   in the PR with its reason.

### Capacity and cost (CLAUDE.md Rule 0)

Measured 2026-10-19 in a sandbox with `pandas_market_calendars` 5.5.0 (the
lock pins 5.3.0; the measurement with the API requirements in done_when 6,
and the staging read after merge, replace this):

- Volume: no new data. One cached schedule per process; 2010-2032 is 5,782
  sessions.
- Velocity: one library import (1,302 ms, pandas included) and one schedule
  build (320 ms for 2010-2032) per process; every later call is in memory.
- Wall-clock: about 1.6 s once per process, on the first calendar call. For
  jobs this is negligible. For the API it lands on the first calendar-using
  request after a cold start; loading at startup would instead slow every cold
  start.
- Cost: no new job, schedule or database object, so $0/month. Each image grows
  by about 4 MB (pandas_market_calendars 1.3 MB, exchange_calendars 1.7 MB,
  toolz 0.7 MB, pyluach 0.25 MB, korean_lunar_calendar 0.07 MB).

### Deployment

Both images rebuild. The API change ships through the existing
`deploy-staging.yml` workflow, which deploys only from `main`; jobs pick up
the module on their next deploy. No IAM, schedule or schema change.

Close-out after merge (not pre-merge `done_when` items, because staging and
solyra's contract sync both read `main`):

1. Dispatch `deploy-staging.yml` from `main`, read `/api/config/market-hours`
   and `/api/live/status` on staging, and record the done_when 6 values and
   the first calendar call's latency on the PR.
2. Open the solyra contract sync PR (`npm run contract:sync`), updating the
   market-hours mock for `holidays` and `early_closes`.

## Relationship to approved specifications

This spec takes over the section "One actual exchange calendar" of
`docs/superpowers/specs/2026-10-12-feat-ops-001-av-operations.md` (approved
2026-10-13, no plan or implementation yet), with the user's approval on
2026-10-19. Its other sections are unchanged.

- Kept from that section: the audit resolves sessions through
  `gcp.fetchers.evaluate_ew_strikes.nyse_sessions` (which now delegates to
  `lib/eastern_time.py`); session closes are real (DST and half days);
  Black Friday is a session; 2027 holidays are closed; a calendar failure is
  an attributable `unknown` with a nonzero `--strict` exit; no hard-coded
  holiday set or weekday fallback in the audit.
- Changed: that section keeps `MARKET_HOLIDAYS_2026` as a deprecated
  compatibility export for `gcp/premarket_playbook_resolver.py`. This spec
  removes it, because the resolver, its only consumer, moves to `is_session`
  in the same PR. That section's rule not to delete a public import while its
  consumer remains unchanged is met: the consumer changes with it.
- Not taken over: the AV indicator coverage clocks and the served
  earnings-options coverage sections. Spec B implements the latter on this
  calendar.

## Risks

- A consumer or test depended on a wrong old answer (Juneteenth open, Black
  Friday closed). Caught by done_when 4: each changed expectation is listed.
- A job that used to run weekday-only after a calendar failure now fails.
  Intended (§3.7); the failure notifier reports it.
- Pin drift between the API image and the jobs image. Caught by the pin parity
  test (done_when 5).
- First-call latency on the API is higher than measured. Caught by the
  measurement with the API requirements (done_when 6) and the staging read
  after merge; loading at startup is the fallback design.
- A calendar failure hidden by a caller's catch-all, as in `dashboard_brief`.
  Caught by the failure-path consumer tests (done_when 4); the guard test
  (done_when 2) does not see callers, so the PR's review checks every
  `except` around a migrated call.

## Appendix A: audit of calendar-day versus trading-day logic (2026-10-18)

Read-only audit of `lib/`, `gcp/`, `scripts/`, `platform/api/`,
`gcp/schema.sql`, `gcp/queries/` and solyra `src/`; tests and archives
excluded. Classified by reading the code. Items marked (verified) were checked
against the code or the library during brainstorming. The spec that owns each
item is in brackets.

### Existing calendar implementations

| Where | Holiday-aware | Fallback |
|---|---|---|
| `lib/strat_levels.py:1705` `_trading_days_between` | yes (library) | calendar days / 1.4 on ImportError [A] |
| `lib/strat_levels.py:1671` `daily_data_freshness` | no, by design | none [C] |
| `gcp/research/magnitude_engine/evaluation_windows.py:110, :152` | yes | `BDay(1)` [A] |
| `gcp/fetchers/evaluate_ew_strikes.py:196, :208` `nyse_sessions`, `scoring_session` | yes, early closes too | none [A] |
| `gcp/fetchers/fetch_av_historical_options.py:166` `_trading_days` | yes | weekday on ImportError [A] |
| `scripts/fetch_alphavantage_options.py:58-125` | yes | weekday on any exception [A] |
| `scripts/fetch_alphavantage_intraday.py:50-90` | yes | weekday on ImportError [A] |
| `scripts/audit_data_freshness.py:367-454, :646-670` | 2026 only | none [A] |
| `gcp/premarket_playbook_resolver.py:65-79` `NYSE_FULL_CLOSURES` | 2026 only | none [A] |
| `platform/api/routers/live.py:109-171` (verified) | 2026 only, Juneteenth missing | none [A] |
| `platform/api/routers/dashboard.py:62-79` | inherits live.py | empty set on import failure [A] |
| `np.busday_count`: `lib/agents/summarizers.py:151, :760`, `gcp/premarket_brief.py:211`, `platform/api/routers/grid.py:293, :340` | no | n/a [C] |
| solyra `src/components/shared/ReplayControl.tsx:37-58` | inherits live.py | weekday walk-back [C] |

### Likely bugs: calendar step where a session is meant

| # | Site | Effect | Spec |
|---|---|---|---|
| 1 | `gcp/fetchers/fetch_av_earnings_options_backfill.py:291` (verified) | Monday reporters request a Sunday chain; measured 0 of 915 Monday events have a snapshot | B |
| 2 | `scripts/backtest_playability.py:621, :780, :1072` (621 verified) | Monday reporters never match options in calibration and winners | B |
| 3 | `gcp/schema.sql` `earnings_event_outcomes` `snapshot_date + INTERVAL '1 day'` | Same mismatch in the view | B |
| 4 | `lib/agents/ranker/signals.py:359-362` (verified) | Monday reports lose the pre close, Friday reports the post close | B |
| 5 | `lib/options_exec_backtest/iv_lookup.py:131, :176` (verified) | Monday triggers never find a Monday expiry; `variant_1dte` targets Saturday | C |
| 6 | `gcp/research/strat_engine/strat_leakage_audit.py:113-117` | Default Friday sample disables the leaked-from-tomorrow check | C |
| 7 | `gcp/queries/strat_engine_data_validation.sql:95, :99`, `gcp/queries/p7_audit.sql:42` | Latent: Monday samples return UNCLEAR | C |
| 8 | `gcp/premarket_brief.py:815-817` | Tuesday after a Monday holiday loses Friday's AMC reporters | C |
| 9 | `gcp/fetchers/fetch_premarket_refresh.py:106-109` | Same, for the refresh universe | C |
| 10 | `gcp/earnings_reactions_brief.py:208-221` | Next or last session lands on a holiday | C |
| 11 | `gcp/backfill_ticker.py:646-648, :85-93` | Prior day can be a holiday | C |
| 12 | `lib/agents/summarizers.py:1766-1769` | Post-holiday Tuesday gets a 48 h news window | C |
| 13 | `gcp/premarket_brief.py:1966-1971` | Calendar days labelled as sessions | C |
| 14 | `scripts/backfill_watchlist_data.py:245-271` | Holidays counted as sessions | C |
| 15 | `scripts/fetch_earnings_calendar.py:237-243` | Post-holiday options enrichment skipped | C |
| 16 | `scripts/validate_market_data.py:85-100, :285-287` | Holiday raises a missing-data error | C |
| 17 | `lib/agents/ranker/signals.py:312` | "20d volume" is 20 calendar days | C |
| 18 | `lib/strategies/catalyst_proximity.py:279` | "4 trading days" is 6 calendar days | C |
| 19 | `gcp/queries/strat_engine_data_validation.sql:157-159` | Holidays reported as missing business days | C |
| 20 | `platform/api/routers/grid.py:814-819` | Third-Friday OPEX ignores holiday shift | C |

### Unsure, for Spec C to decide

`lib/strategies/catalyst_proximity.py:195-196, :236-237` (plus or minus 24 h
earnings window), `gcp/discord_interactions/main.py:144` (`today-N` in
calendar days), `gcp/signal_monitor.py:1961` (30-day RVOL baseline),
`gcp/audit_magnitude_drift.py:91, :122-131`, `scripts/fetch_earnings_calendar.py:1542`,
`gcp/signal_quality_alarm.py:370-372`, `scripts/run_historical_signals.py:155`,
`gcp/insight_discord_push.py:286-287`, `platform/api/main.py:1423`,
solyra `src/routes/CatalystsPage.tsx:446-452`, solyra
`src/routes/DashboardPage.tsx:395-437`.

### Correct patterns to copy

Previous-row lookups that need no calendar:
`gcp/queries/strat_features_gamma_backfill.sql:16-20`,
`platform/api/main.py:1104-1110`, `lib/earnings_reactions.py:589-606`,
`gcp/research/p2_outcomes_grid.py:159`, `gcp/build_intraday_gex.py:146-161`,
`gcp/fetchers/compute_earnings_reactions.py:118-124`.

About 100 further sites use calendar days correctly (retention windows, TTLs,
fetch margins, calendar horizons, day-of-week features) and are out of scope.
