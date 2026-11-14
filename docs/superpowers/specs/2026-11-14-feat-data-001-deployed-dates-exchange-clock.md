---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-DATA-004]
issues: []
canvases: []
site_source_notes: [ADMIN-08, DASHBOARD-01, DASHBOARD-03, DASHBOARD-06, DASHBOARD-21, OPTIONS-01]
done_when:
  - "The diff of tests/fixtures/timezone_boundary_baseline.json against the merge base removes exactly the 71 identities of Appendix A (64 host-today and 7 sql-utc-date, in 39 files) and adds no line; tests/meta/test_market_date_stage_one.py passes, holding those 71 identities and the 31 of Appendix B as written-out data and asserting that none of the 71 is in the baseline and each of the 31 still is; tests/meta/test_timezone_boundaries.py is unmodified and passes."
  - "tests/scripts/test_fetch_earnings_calendar_evening.py passes with the clock frozen at lib.eastern_time.eastern_now: _resolve_scope gives weekly at 2026-11-09T00:00:30Z (Sunday 19:00 EST) and at 2026-10-25T23:00:30Z (Sunday 19:00 EDT), and daily at 2026-11-03T00:01Z; _resolve_target_dates_for_av_options gives 2026-11-09 to 2026-11-13 for that winter Sunday, [2026-11-03] at 2026-11-03T00:01Z (Monday 19:01 EST), [2026-11-06] at 2026-11-06T00:00:30Z (Thursday), [] at 2026-11-07T00:00:30Z (Friday) and [2026-10-27] at 2026-10-26T23:00Z (Monday 19:00 EDT); the snapshot date main() hands enrich_with_av_options is 2026-10-30, 2026-11-04 and 2026-11-06 for the Monday, Thursday and Sunday winter runs; PIPELINE_SCOPE and --scope still decide when set; and the file runs as the job runs it: python scripts/fetch_earnings_calendar.py --help from the repo root with PYTHONPATH unset exits 0, and a subprocess that loads the file by path with only scripts/ on sys.path and calls its market-date read prints a date, the same two checks passing for scripts/fetch_catalyst_calendar.py. tests/gcp/test_earnings_scope_evening.py passes the same two Sundays (weekly) and the Monday (daily) for fetch_earnings_history._resolve_scope and compute_earnings_reactions._resolve_scope."
  - "tests/scripts/test_backtest_playability_calculation_date.py passes: compute_options_insights stamps calculation_date 2026-11-08 on every insight and winner row at 2026-11-09T01:30Z (Sunday 20:30 EST) and 2026-07-12 at 2026-07-13T00:30Z (Sunday 20:30 EDT). tests/gcp/test_earnings_long_watchlist_evening.py passes: main() at 2026-11-09T00:45Z (Sunday 19:45 EST) hands build_discord_message 2026-11-08, judges the source age from 2026-11-08, and the SQL _query_watchlist issues holds the text lib.eastern_time.market_today_sql() returns and no CURRENT_DATE."
  - "tests/gcp/test_evening_windows.py passes: fetch_av_historical_options.main with --from-latest at 2026-11-13T02:00Z (Thursday 21:00 EST) and a stored EOD watermark of 2026-11-11 fetches 2026-11-12 and no other date; build_options_daily_features.main and build_options_daily_greeks.main with --incremental --days=7 at 2026-11-13T03:00Z and 2026-11-13T04:15Z (Thursday 22:00 and 23:15 EST) pass since 2026-11-05 and until 2026-11-12."
  - "tests/api/test_evening_dates.py passes through TestClient at 2026-11-14T01:30Z (Friday 2026-11-13 20:30 EST): get_catalyst_events with no dates filters 2026-11-10 to 2026-11-27, get_catalysts_for_ticker counts its window from 2026-11-13, get_catalyst_snapshot with no as_of cuts off at 2026-11-13, get_grid_timeseries with no expiration and a chain holding 2026-11-13 and 2026-11-20 picks 2026-11-13, _load_chain_for_live floors at 2026-10-24, get_reference_levels judges recency from 2026-11-13, and strat_pred_serve.predict_one loads features since 2026-10-14. tests/gcp/test_discord_date_arg_evening.py passes: parse_date_arg at 2026-11-14T01:00Z gives 2026-11-13 for today, 2026-11-12 for -1, and refuses 2026-11-14 as a future date. tests/lib/test_library_today_defaults.py passes at the same instant: _check_chain_freshness and summarize_gamma_levels with no as_of, _check_staleness with no today, _latest_calibration with no as_of and _latest_overrides count from 2026-11-13, and calculate_orb and MarketAnalyzer._calculate_orb return the same opening-range end time at two instants on different dates."
  - "tests/lib/test_market_today_hours.py passes: over every hour of 2026 in UTC, lib.eastern_time.market_today() differs from the UTC date at exactly 1,587 of the 8,760 hours, UTC hours 0 to 3 while Eastern is UTC-4 and 0 to 4 while it is UTC-5. tests/meta/test_stage_one_run_hours.py passes: for each scheduled job all of whose sites Appendix A marks no, the scheduler entries gcp/deploy.sh declares start no run from 19:00 to 23:59 America/New_York, so a schedule moved into the evening fails a test instead of silently making a no into a yes."
  - "Every test named above runs the code under test with its module's date and datetime names replaced by classes whose today(), utcnow() and zone-less now() raise, through one fixture in tests/fixtures/market_clock.py, and each family's test also asserts the pre-change value at 2026-11-12T15:00Z (Thursday 10:00 EST), a daytime instant where the host date and the Eastern date agree. git grep -c 'tz-ok:' over gcp, lib, scripts and platform/api gives the merge base's count per file (26 lines in 10 files on 20d9c47b): no opt-out is added."
  - "make test passes on the PR head; the PR body lists every existing test whose expectation or clock stub changed, with the reason, and pastes the EXPLAIN (ANALYZE, BUFFERS) of one changed query in both spellings, run read-only through scripts/db_query_cr.sh with its execution id, showing the same scan node and the same rows read."
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-DATA-001, component) row for each of the six declared components that begins with the current source hash (a row an earlier change left is extended: the new hash and this change's prose first, then 'Earlier:' and the earlier prose unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes."
status: draft
supersedes: null
---

# Deployed code takes "today" from the exchange's clock (stage 1 of the market-time sweep)

## Scope

- This is stage 1 of seven. It changes 71 sites in 39 files: every place where a deployed job, a deployed service or a library they import takes **a date** from the container's clock, plus the 7 `CURRENT_DATE` reads in those same files.
- It continues `2026-10-19-feat-data-001-shared-market-calendar.md`, which put the calendar in `lib/eastern_time.py`, and the ratchet `tests/meta/test_timezone_boundaries.py` (#1185), whose baseline is the backlog this stage starts to clear. It adds no helper: `market_today()` and `market_today_sql()` exist.
- The inventory behind every number here is a scratch file, not in the repo: 339 rows (313 baseline sites, 26 `# tz-ok:` lines), produced by importing the ratchet's own scanner. Appendix A is its stage 1 slice; Appendix C is the staging.

## Decisions for the owner

Each has a default the plan follows if nothing is said.

1. **One PR of 71 sites in 39 files, or two.** Default: one, grouped by job family (Design 6, 13 tasks). Alternative: 1a the jobs (55 sites, 27 files, families A to F), then 1b the API, the Discord service and the libraries (16 sites, 12 files, families G to I). Choosing two means this spec is cut in two before approval.
2. **Which session the weekday 19:00 options enrichment snapshots.** `_previous_trading_weekday(today)` gives the session before the run day. In summer that is what runs. In winter the host date is tomorrow, so the job has been snapshotting the run day itself, which AlphaVantage does serve at 19:00 ET (the winter log lines show data for it). Default: keep the function as written, so winter becomes what summer is; the snapshot is one session older than winter has now. Alternative: snapshot the run day's session in both seasons (`latest_session_on_or_before(market_today())`), a behaviour change of its own.
3. **Rows already stored with the wrong date are left alone.** `earnings_options_strategy_winners.calculation_date` is a Monday on the last four sweeps; the enrichment gaps in `earnings_calendar` are in the past. Default: no rewrite (Non-goals); the next sweep writes a Sunday date, and the watchlist's 14-day freshness check accepts both.
4. **`fetch_alphavantage_intraday.py:1179` waits.** It is wrong on a schedule (verified, the last evening of each month), but the bucket-copy plan edits the same `main()`. Default: held until that PR merges; the next occurrence is Monday 2026-11-30 21:00 ET. Alternative: take the one line here and rebase whichever lands second.
5. **Two sites are left out because any fix changes signal-monitor behaviour:** `gcp/signal_monitor.py:1180` and its replay twin `scripts/replay_signal_monitor.py:653` stamp a fire with `datetime.now()` when the bar has no `Time`. Default: they stay in the baseline until FEAT-SIGNAL-001 decides between refusing such a bar and `eastern_now()`, with a production replay.
6. **`TZ=America/New_York` on the containers is refused** (Approaches). The owner can overrule; it would be a FEAT-DEPLOY-001 change and would not replace this one.
7. **What a remaining `# tz-ok:` may say at the end of the sweep.** Of the 26 lines today, 5 name a UTC contract, 19 name a label dropped after conversion to Eastern, 2 are document review dates. Default for the end condition: a `tz-ok` names one of those three kinds of contract. "UTC by contract only" would refuse 19 lines that are correct.

## Problem

`CLAUDE.md` 3.9: market time is Eastern, named, converted once, through `lib/eastern_time.py`. The owner's instruction of 2026-11-14 is that the helper be used in all files. It is not: the ratchet's baseline on `origin/main` 20d9c47b still lists **313** hand-rolled sites in **139** files (`host-today` 169 in 92 files, `utc-parse` 67, `sql-utc-date` 40, `tz-localize-none` 29, `zone-built-locally` 6, `fixed-offset` 2; gcp 147, scripts 104, lib 48, platform/api 14), and 26 lines opt out with `# tz-ok:`. Recounted with `current_hits()`; it equals the committed baseline.

Why a host date is wrong here: 66 jobs and 3 services run with no `TZ` (read from the live fleet, 2026-11-14), so their clock is UTC, while all 65 scheduler entries are in `America/New_York`. From 19:00 Eastern in winter and 20:00 in summer until midnight Eastern, `date.today()` is tomorrow: 1,587 of the 8,760 hours of 2026 (executed).

What that is doing in production now. "Verified" means production logs or a read-only query, and a frozen-clock run of the production function where one was cheap; "read-only" means the path was read end to end and nothing was run.

| # | Site | Run | What is wrong | Checked |
|---|---|---|---|---|
| 1 | `scripts/fetch_earnings_calendar.py:243`, `:265`, `:1306` | `fetch-earnings-calendar`, 19:00 ET Mon-Fri and Sun. Winter only: 19:00 EST is 00:00 UTC. | The AV options enrichment of `earnings_calendar` goes to the wrong reporters. Weekday runs target the day after tomorrow; Thursday and Friday runs target nobody; the Sunday run resolves `scope=daily` and targets Tuesday alone. Monday's reporters are never enriched. | verified: `2026-11-03T00:01Z ... target_dates=['2026-11-04'] on snapshot=2026-11-02`; `2026-10-26T23:00Z ... target_dates=['2026-10-27'] on snapshot=2026-10-23`; `2026-11-09T00:00Z [scope=daily] ... target_dates=['2026-11-10']`; `2026-10-25T23:00Z [scope=weekly]` Monday to Friday. A frozen-clock run reproduces each. |
| 2 | `gcp/fetchers/fetch_earnings_history.py:354`, `gcp/fetchers/compute_earnings_reactions.py:947` | the Sunday 19:15 and 19:30 ET weekly runs. Winter only. | Both resolve `scope=daily`: the week-ahead fetch and recompute have not run since clocks changed on 2026-11-01. | verified: history `force-refetch=0` and `=1` tickers on 2026-11-02 and 2026-11-09 against `scope=weekly ... force-refetch=277` on 2026-10-25; reactions 0 and 1 against 276. A frozen-clock run reproduces both seasons. |
| 3 | `scripts/backtest_playability.py:853` | `earnings-sweep-sunday`, 20:30 ET Sun, both seasons | `calculation_date` is the Monday after the sweep. | verified, `db-query-ngvls`: 360 rows each on 2026-11-09, 2026-11-02, 2026-10-26 and 2026-10-19, all Mondays. |
| 4 | `gcp/earnings_long_watchlist.py:338` and its SQL at `:125` | `earnings-long-watchlist-sunday`, 19:45 ET Sun. Winter only. | The Discord watchlist is dated Monday, and its window runs Monday to Monday+7. | verified for the date (frozen-clock run: 2026-11-09 on Sunday 2026-11-08 19:45 EST); the post was not run. |
| 5 | `gcp/fetchers/fetch_av_historical_options.py:301` | `av-options-daily`, 21:00 ET Mon-Fri, both seasons | Asks AlphaVantage for tomorrow's chain Monday to Thursday: 4 calls and 4 `Date parameter out of range` warnings a night. Nothing wrong is stored. | verified: the runs logged at 02:0xZ on 2026-11-11, 2026-11-12 and 2026-11-13 show `Backfill range: D -> D+1 (2 trading days)` and the warning for D+1 on SPY, IWM, QQQ and SPX; the Friday-night run of 2026-11-14 shows the range ending on Saturday and no extra call. |
| 6 | `gcp/fetchers/build_options_daily_features.py:50-51`, `gcp/build_options_daily_greeks.py:168-170` | 22:00 and 23:15 ET Mon-Fri | The 7-day window is `[D-6, D+1]`, not `[D-7, D]`. Rows are upserts, so no stored value is wrong. | features verified (frozen-clock `main()` logs `[2026-11-06..2026-11-13]` on Thursday 2026-11-12 22:00 EST); greeks read-only. |
| 7 | `gcp/discord_interactions/main.py:136` | any `/replay` or `/validate` in the evening | `today` is tomorrow, `-1` is today, and tomorrow's date passes the "not in the future" check. | verified by a frozen-clock run at Friday 2026-11-13 20:00 EST. |
| 8 | `platform/api/routers/catalysts.py:175`, `:621`, `:685`; `grid.py:254`, `:1244`; `main.py:1143`; `strat_pred_serve.py:372` | any request in the evening | Default windows, cutoffs, the default expiration on an expiry day, and age checks count from tomorrow. | read-only |

Three more are wrong on a schedule and are not in this stage: `gcp/premarket_brief.py:893` (its own spec, PR #1930), `gcp/fetchers/fetch_alphavantage_intraday.py:1179` (Decision 4), and `gcp/research/strat_engine/strat_data_builder.py:718` (a lag warning off by one; the same held file as the bucket-copy plan).

Of the 71 sites, 19 are wrong on a schedule, 8 on request in the evening, 13 only on a hand run or a rare path, and 31 are not wrong at the hours their code runs today. The 31 are in scope because nothing but the schedule keeps them right: `refresh_daily` at 07:30, `fetch_top_movers` during the session, `trade_logger` under the signal monitor.

## Non-goals

- The later stages (Appendix C): `CURRENT_DATE` in the rest of deployed code and the scanner's blind spots (2), instants (3), local zones and fixed offsets (4), hand-run scripts and research (5), conversions (6), the readers of `market_data_intraday` (7).
- Any site that reads `market_data_intraday.ts`. None of the 71 does. `CLAUDE.md` 3.9 holds those readers until the misplaced rows are removed; 82,481 such rows are still stored for SPY, QQQ and IWM alone (`db-query-ngvls`, UTC hours 4 to 7, 2026-04-06 to 2026-09-25).
- `gcp/premarket_brief.py` (PR #1930), and the files open branches are editing: `gcp/backfill_ticker.py`, `gcp/migrate_to_gcp.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/research/strat_engine/strat_data_builder.py`, and `platform/api/routers/backtest.py:649`, which the strict-bar-loader spec keeps.
- Instants. The 12 `utcnow()` and stamp sites that share a file with a stage 1 site stay (Appendix B).
- Stored data: no row is rewritten, re-dated or deleted.
- Schedules, job definitions, `gcp/deploy.sh`, Dockerfiles: unchanged. No `TZ` on any container.
- The scanner and its test: `tests/meta/test_timezone_boundaries.py` is unmodified. No new `# tz-ok:`.
- What each date means. A calendar-day age stays a calendar-day age; no site moves from days to sessions (that is Spec C of the calendar work). Decision 2 is the one place where the pure date-source change has a visible second effect.
- solyra. No response shape changes; `stocks` `openapi.json` is not regenerated.

## Approaches considered

- **Set `TZ=America/New_York` on every job and service. Refused.**
  - What it would fix: `date.today()`, `datetime.now().date()` and `datetime.today()`: 62 of the 64 Python sites here, with no code change (the other two read `pd.Timestamp.utcnow()`).
  - What it would not fix: `CURRENT_DATE` (the database session is UTC; read today: `current_setting('TimeZone')` is `UTC`), `datetime.utcnow()`, `pd.Timestamp.utcnow().date()`, and `datetime.now(timezone.utc).date()`, the form #1308 had and of which 16 more exist outside the scanner's sight.
  - What it would break: code that reads the host clock as naive UTC on purpose. `gcp/signal_monitor.py:2129` does `now_utc = datetime.now()` and subtracts `alert_ts`, which is naive UTC; under an Eastern host clock every time-based exit would be 4 or 5 hours off. Log stamps and `datetime.now().isoformat()` texts would move too.
  - What it would leave fragile: the answer would depend on a deploy flag on 69 resources. A job run from a laptop, CI, `scripts/replay_signal_monitor.py`, or a resource deployed without the flag would silently differ. `verify_eastern_is_dst_correct()` vouches for `zoneinfo`, not for the C library's `TZ`. It is also the opposite of the rule: a zone taken from the environment, not converted once through the helper.
- **Site-by-site replacement with the existing helper. Chosen.** Each site says what it means. The ratchet already measures it, and each change is provable with one frozen instant.
- **A lint that bans the patterns outright.** That is what the ratchet becomes when its baseline is empty (the end condition in Appendix C). Doing it first would mean 313 failures or a wholesale `tz-ok`, which is the outcome the owner's instruction rules out.
- **Bind one Python date into the SQL instead of `market_today_sql()`.** Better where a run could cross Eastern midnight, but it changes function signatures in 7 places. Not needed in this stage: none of the seven runs in a scheduled job that crosses midnight Eastern. The latest scheduled start is 19:45 (600 s timeout), and the longest, `fetch-earnings-history` from 19:15, ended by 20:45 on its last six runs.

## Design

### 1. The replacement rule, by meaning

| The site means | Replace with | Notes |
|---|---|---|
| today's market date: `date.today()`, `datetime.now().date()`, `pd.Timestamp.utcnow().date()`, `datetime.now()` used only for `± timedelta` and a `%Y-%m-%d` string | `market_today()` | The variable becomes a `date`. Where it was a `datetime` formatted with `strftime("%Y-%m-%d")`, the text is identical. |
| today's weekday: `datetime.now().weekday()` | `market_today().weekday()` | The three `_resolve_scope` functions. `PIPELINE_SCOPE` and `--scope` keep their precedence. |
| the current year | `market_today().year` | |
| a date that is thrown away: `datetime.combine(datetime.today(), market_open) + timedelta(...)` then `.time()` | no clock: combine with a fixed date | `lib/indicators.py:734`, `lib/trading_analysis.py:618`. The result does not depend on the date. |
| today in SQL, in a file this stage edits: `CURRENT_DATE` | the text `market_today_sql()` returns, placed in the statement | 7 sites. The fragment is a constant from the helper, never caller input. |
| an optional `today` / `as_of` argument defaulting to the host date | the same argument defaulting to `market_today()` | A caller that passes a date is unaffected: `parse_date_arg`, `_check_staleness`, `_latest_calibration`, `_load_chain_for_live`, `_check_chain_freshness`, `summarize_gamma_levels`. |
| a dead branch: `datetime.now(ET_TZ).date() if ET_TZ else datetime.now().date()` | `market_today()` | `platform/api/routers/dashboard.py:303`. |

Appendix A gives the rule for each of the 71.

### 2. How the helper is imported

- A module run with `-m` or imported as a package (`gcp.*`, `lib.*`, `platform/api`, and `scripts.*` when its job runs `python -m scripts.x`) imports at module level: `from lib.eastern_time import market_today`.
- **A file run by path that has no module-level route to the repo root cannot.** `fetch-earnings-calendar` runs `python scripts/fetch_earnings_calendar.py`, so `sys.path[0]` is `scripts/`, and the image sets no `PYTHONPATH`. Executed on a copy of the tree: a module-level `from lib.eastern_time import market_today` there ends in `ModuleNotFoundError: No module named 'lib'`, while a test run from the repo root passes. The file already reaches `lib` inside functions after putting the repo root on `sys.path` (`:328`, `:855`). Its market-date read goes through one small function in the file that does the same, and done_when 2 runs the file the way the job does.
  - It is the only stage 1 file a live job runs by path (read from the 66 job commands). `scripts/fetch_catalyst_calendar.py` has the same shape for a hand run (no module-level bootstrap; the API imports it as a package) and gets the same treatment and the same test.
  - `scripts/backtest_playability.py`, `scripts/calibrate_thresholds.py` and `scripts/run_param_sweep.py` put the repo root on `sys.path` at module level (`:36`, `:49`, `:38`) and import `lib` below it; the helper import goes there.
- The API image, the jobs image and the Discord service (the jobs image, `uvicorn gcp.discord_interactions.main:app`) all carry `lib/` and already import `lib.eastern_time`.

### 3. Frozen-clock tests

- **One seam.** `tests/fixtures/market_clock.py` freezes one instant by replacing `lib.eastern_time.eastern_now` and `utc_now`. `market_today()` reads `eastern_now()` through the module, so every module that imported `market_today` by name follows (executed: with the seam at `2026-11-09T00:00:30Z`, `market_today()` is 2026-11-08). No test hands the code a ready-made date in place of the clock: that would prove the wiring and not the evening.
- **The host clock is forbidden in the same test.** The fixture replaces the `date` and `datetime` names of the module under test with subclasses whose `today()`, `utcnow()` and zone-less `now()` raise. A site that was missed fails the test; on `main` it would pass on the test machine's clock.
- **Four instants a family**, the evening ones chosen from the job's own schedule:
  - a winter evening inside the window (for a 19:00 job, `00:00:30Z`);
  - the same clock time in summer, where the host date was already right (`23:00:30Z`), to pin that summer does not move;
  - a summer evening inside the window, for jobs that start at 20:00 or later;
  - a daytime instant, `2026-11-12T15:00Z`, asserted to give the value `main` gives.
- **Why "no value changes" is proven and not argued.** `tests/lib/test_market_today_hours.py` pins the hours at which the two dates differ. `tests/meta/test_stage_one_run_hours.py` pins that the scheduled jobs whose sites Appendix A marks "no" have no scheduler entry in those hours. Together: a "no" site returns the same value after the change at every hour its job runs, and a later schedule change that breaks that fails a test.
- **The I/O shape** (`CLAUDE.md` Rule 0.3): the two `main()` tests of family C assert the dates handed to the fetch loop and the builder, not a helper's return; the path-run test starts a real subprocess.

### 4. What was executed for this spec

On a copy of `origin/main` with six sites changed (`scripts/fetch_earnings_calendar.py:243`, `:265`, `:1306`, the two `_resolve_scope` twins, `gcp/discord_interactions/main.py:136`), not committed anywhere:

| Instant (UTC) | Eastern | `main` | Changed |
|---|---|---|---|
| 2026-11-09T00:00:30 | Sun 19:00 EST | scope daily (all three), targets `[2026-11-10]`, snapshot 2026-11-06 | weekly, targets 2026-11-09 to 2026-11-13, snapshot 2026-11-06 |
| 2026-11-03T00:01 | Mon 19:01 EST | targets `[2026-11-04]`, snapshot 2026-11-02 | `[2026-11-03]`, snapshot 2026-10-30 |
| 2026-11-06T00:00:30 | Thu 19:00 EST | targets `[]`, snapshot 2026-11-05 | `[2026-11-06]`, snapshot 2026-11-04 |
| 2026-11-07T00:00:30 | Fri 19:00 EST | not run | `[]`, snapshot 2026-11-05 |
| 2026-10-25T23:00:30 | Sun 19:00 EDT | weekly | weekly |
| 2026-10-26T23:00 | Mon 19:00 EDT | `[2026-10-27]`, snapshot 2026-10-23 | the same |
| 2026-11-14T01:00 | Fri 20:00 EST | `/replay today` 2026-11-14, `-1` 2026-11-13, 2026-11-14 accepted | 2026-11-13, 2026-11-12, 2026-11-14 refused as future |

The snapshot column is Decision 2. On that copy, the 21 non-integration test files that name these modules and the ratchet gave 713 passed, 2 skipped, 23 failed: the ratchet, naming the six cleared entries and nothing else, and 22 cases of `tests/scripts/test_doc_inventory.py` that read `docs/` and `platform/deploy.sh`, which the copy did not hold. No existing test pins the evening values, in either direction. The other 65 sites were not prototyped: their expected values in `done_when` follow from the rule and the frozen instant, and the plan's first run of each test on `main` is what shows the pre-change value.

`market_today_sql()` against `CURRENT_DATE`, read-only, `db-query-x6t5w`: for `earnings_calendar WHERE earnings_date BETWEEN <today> AND <today> + 7`, both spellings use `Index Scan using idx_earnings_calendar_date` with the bound in the Index Cond, 1,240 rows read on the scan node and 921 groups returned (62 ms cold, 1.4 ms warm). The fragment is a stable expression, as `CURRENT_DATE` is. The other six queries were not measured; done_when 8 asks for one more in the PR.

### 5. The baseline

- The implementation removes its 71 entries and regenerates the file with `python -m tests.meta.test_timezone_boundaries --write-baseline`. The diff against the merge base is the checklist: 71 identities gone, none added.
  - A `sql-utc-date` identity is a hash of the whole statement. All seven statements hold `CURRENT_DATE` and no other flagged pattern (read), so after the change they no longer match and leave cleanly.
  - If another PR's baseline change lands first, merge `main` and regenerate; the 71 are judged by identity, not by the file's total.
- 31 entries stay in the 39 files (Appendix B): 12 instants, 13 conversions and SQL column dates, 5 blocked bar readers, 1 undecided. `tests/meta/test_market_date_stage_one.py` pins both lists so a later edit cannot quietly widen or narrow the stage.
- No `# tz-ok:` is added. If a site turns out to be UTC by contract, it is not "fixed" with an opt-out here: it is taken out of this stage in the PR, with the reason, and the owner is told.

### 6. Work order (for the plan; about 13 tasks)

1. The clock fixture and `tests/lib/test_market_today_hours.py`.
2. Family A: the three earnings refresh jobs, with the path-run test.
3. Family B: the Sunday sweep, the watchlist (Python and SQL together), `refresh_earnings_views`.
4. Family C: AV options nightly and the three builders.
5. Family D: seven daytime fetchers, three with their `CURRENT_DATE`.
6. Family E: `signal_monitor.py:381`, `trade_logger`, `weekend_review`.
7. Family F: seven jobs with no scheduler, or one outside the evening; `run_param_sweep` with its SQL.
8. Family G: the API routes and `strat_pred_serve`.
9. Family H: the Discord date argument.
10. Family I: the library defaults.
11. `tests/meta/test_stage_one_run_hours.py` and `tests/meta/test_market_date_stage_one.py`.
12. The baseline, and the list of changed existing tests.
13. Catalog, traceability, the six site notes, the snapshot, the audits.

If the plan passes 15 tasks it is cut at Decision 1's line, not stretched.

### 7. Site traceability

`site_source_notes` cannot be widened by the implementation PR, so it is declared by rule. Line numbers are those of `docs/product/03-SITE-TRACEABILITY.md` on 20d9c47b.

- **Rule 1:** for each route whose answer changes in the evening, the first Chain row of the document that names the route.
- **Rule 2:** for each scheduled job whose stored or requested values change in the evening, the first Chain row that names the job.

| Changed | First Chain row that names it | Declared |
|---|---|---|
| `GET /api/market/reference/{ticker}/{date}` (`get_reference_levels`) | DASHBOARD-03 (`:333`) | DASHBOARD-03 |
| `GET /api/catalysts` and its per-ticker and snapshot routes | DASHBOARD-06 (`:336`) | DASHBOARD-06 |
| `GET /api/options/{ticker}/grid` (`_load_chain_for_live`) and `.../grid/timeseries` | OPTIONS-01 (`:598`) | OPTIONS-01 |
| `POST /api/admin/strat-engine/predict` (`predict_one`) | ADMIN-08 (`:1125`) | ADMIN-08 |
| job `fetch-earnings-calendar` | DASHBOARD-06 (`:336`) | (the same) |
| job `fetch-earnings-history` | DASHBOARD-01 (`:331`) | DASHBOARD-01 |
| job `fetch-av-options-backfill` | DASHBOARD-21 (`:351`) | DASHBOARD-21 |
| jobs `compute-earnings-reactions`, `earnings-sweep`, `earnings-long-watchlist`, `build-options-daily-features`, `build-options-greeks`; the Discord service | named in no Chain row (searched) | none |

So `site_source_notes: [ADMIN-08, DASHBOARD-01, DASHBOARD-03, DASHBOARD-06, DASHBOARD-21, OPTIONS-01]`. On `main` the notes table holds a FEAT-DATA-001 row for DASHBOARD-01 and none for the other five; an existing row is extended, not replaced (done_when 9). Each note says what the source now does (which date it reads) and claims no change on a page.

## Capacity

No workload runs differently in kind: no job, schedule, query shape, table or timeout changes. Three runs change in size, back to what the same jobs do every summer:

- **Volume:** no new rows or tables. The Sunday weekly runs in winter again cover the week ahead: history about 277 tickers and reactions about 276 (the 2026-10-25 runs) where the last two winter Sundays did 0 and 1; the Sunday enrichment about 65 to 88 tickers (2026-10-18, 2026-10-25) where the last two did 29 and 24.
- **Velocity:** `av-options-daily` makes 4 fewer AlphaVantage calls a night, Monday to Thursday. The Sunday enrichment makes about 40 to 60 more calls at its existing 150 a minute. Each of the 7 SQL statements stays one statement with the same plan (Design 4). No per-row query is added; `market_today()` is one clock read.
- **Wall-clock**, measured from the live executions, against each job's timeout:
  - `fetch-earnings-history`, weekly scope: 4,296 s and 4,453 s (2026-10-25, 2026-10-18) against 28,800 s, 15%. Its daily-scope runs already take 4,004 to 5,347 s.
  - `compute-earnings-reactions`, weekly scope: 365 s and 739 s against 1,800 s. The winter Sunday run goes from 25 to 36 s back to that. 739 s is 41% of the timeout, over the quarter REQ-CAP-001 allows; so is the daily run of 2026-11-14 at 776 s, which this change does not touch. The ratio exists today and is not made worse than the summer already has it; it is reported here, not fixed here.
  - `fetch-earnings-calendar`, weekly scope: 77 s and 87 s against 1,800 s.
- **Cost:** $0 a month of new spend: no new job or schedule. AlphaVantage is a flat plan.

## Risks

| Risk | What catches it |
|---|---|
| A site is "fixed" with a value that differs in the daytime | The daytime assertion in each family's test (done_when 7), and the hour test and run-hour test (done_when 6). |
| A missed site in an edited file | The host clock raises inside the tests; the baseline diff must show all 71 gone. |
| The import fails only in the container | The path-run subprocess test (done_when 2); Design 2 names the one file. |
| A reader depends on the wrong date: something matches `calculation_date` to a Monday, or expects the winter snapshot | `calculation_date` is read by `_latest_source_date()` as a `MAX` and by a 14-day age check (read); Decision 2 puts the snapshot change to the owner. Close-out step 3 checks the first real Sunday. |
| The Python date and the SQL date of one job disagree | The 7 `CURRENT_DATE` sites are taken with their files; done_when 3 pins the watchlist's two together. |
| The Sunday weekly runs are heavier than the winter runs of the last two weeks | Capacity: they are the summer's size, measured. |
| Another PR edits the baseline or one of the 39 files first | Identities, not totals, are asserted; the held files are out of scope. |
| The stage grows in review (an instant "while we are there") | Non-goals and Appendix B; `test_market_date_stage_one.py` fails if the 31 change. |

## Close-out (the owner's steps; the PR deploys nothing)

1. Deploy the jobs image and the services the usual way (`./gcp/deploy.sh` for the jobs and the Discord service, `deploy-staging.yml` for the API). No flag, schedule or IAM change.
2. Read-only, the same evening or by replay (`CLAUDE.md` 3.5): execute `fetch-av-options-backfill` after 19:00 ET and read its log for `Backfill range: D -> D` with no `Date parameter out of range` line.
3. Read-only, the first weekday evening after the deploy: the calendar job's 19:00 ET log line shows `target_dates` holding tomorrow, not the day after, on the previous session's snapshot (or the run day's, under Decision 2's alternative).
4. The Sunday scope is read from the clock, and these jobs take no as-of date, so no replay on another day can show it; the frozen-clock tests are its proof before the merge. The production record is added when the data exists: on the first Sunday the three jobs log `scope=weekly` at 19:00, 19:15 and 19:30 ET, `SELECT calculation_date, count(*) FROM earnings_options_strategy_winners GROUP BY 1 ORDER BY 1 DESC LIMIT 3` shows a Sunday on top, and the watchlist post is dated Sunday.
5. Record the log lines and the query on the PR, with the execution ids.
6. The post-merge site-note close-out and the plan's `status: done`, as the delivery skill sets out.

## Appendix A: the 71 sites

Wrong today? is the inventory's verdict: on a schedule, on request in the evening, only by hand or on a rare path, or no.

**A. Evening earnings refresh** (12 sites, 3 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `scripts/fetch_earnings_calendar.py:243` | `_resolve_target_dates_for_av_options` | host-today | `market_today()` | yes, on schedule: every 19:00 ET run in winter targets the day after tomorrow; the Thursday and Friday runs target nothing; Monday reporters are never enriched | value changes in the evening: earnings_calendar.options_volume / open_interest are written for tomorrow's reporters again |
| `scripts/fetch_earnings_calendar.py:265` | `_resolve_scope` | host-today | `market_today().weekday()` | yes, on schedule: weekly-earnings-refresh-calendar Sun 19:00 ET resolves scope=daily in winter (the host weekday is Monday) | value changes in the evening: the Sunday run goes back to weekly scope (targets Mon-Fri, not Tuesday alone) |
| `scripts/fetch_earnings_calendar.py:1013` | `EarningsCalendarFetcher.fetch_unusual_whales_earnings` | host-today | `market_today()` | yes, on schedule: the Unusual Whales window starts one day late in winter | value changes in the evening: window start one day earlier (winter only) |
| `scripts/fetch_earnings_calendar.py:1132` | `EarningsCalendarFetcher.print_summary` | host-today | `market_today()` | yes, on schedule: printed summary only | none (log text) |
| `scripts/fetch_earnings_calendar.py:1221` | `main` | host-today | `market_today()` | only if run by hand in the evening (needs --start-date and --end-date) | none on the scheduled path |
| `scripts/fetch_earnings_calendar.py:1258` | `main` | host-today | `market_today()` | yes, on schedule: the Yahoo window starts and ends one day late in winter | value changes in the evening: the Yahoo cross-check window shifts one day earlier (winter only) |
| `scripts/fetch_earnings_calendar.py:1259` | `main` | host-today | `market_today()` | yes, on schedule: as line 1258 | value changes in the evening: as line 1258 |
| `scripts/fetch_earnings_calendar.py:1283` | `main` | host-today | `market_today()` | yes, on schedule: in winter the kept window is today..today+8 instead of today-1..today+7 | value changes in the evening: the rows kept for earnings_calendar shift one day earlier (winter only) |
| `scripts/fetch_earnings_calendar.py:1306` | `main` | host-today | `_previous_trading_weekday(market_today())` | yes, on schedule: in winter the AV snapshot is the run day itself, in summer the session before it | value changes in the evening: the winter snapshot date moves back one session, to what summer already uses (see Decisions) |
| `gcp/fetchers/fetch_earnings_history.py:251` | `_earnings_calendar_tickers` | SQL `CURRENT_DATE` | `market_today_sql()` | yes, on schedule: 19:15 ET in winter the earnings window starts tomorrow | changes query results: in the evening the window moves back one day |
| `gcp/fetchers/fetch_earnings_history.py:354` | `_resolve_scope` | host-today | `market_today().weekday()` | yes, on schedule: weekly-earnings-refresh-history Sun 19:15 ET resolves scope=daily in winter; the 7-day pre-fetch has not run since 2026-11-01 | value changes in the evening: the Sunday run fetches the week ahead again |
| `gcp/fetchers/compute_earnings_reactions.py:947` | `_resolve_scope` | host-today | `market_today().weekday()` | yes, on schedule: weekly-earnings-refresh-reactions Sun 19:30 ET resolves scope=daily in winter | value changes in the evening: the Sunday run recomputes the week ahead again |

**B. Sunday sweep, watchlist and views** (5 sites, 3 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `scripts/backtest_playability.py:853` | `compute_options_insights` | host-today | `market_today()` | yes, on schedule: earnings-sweep-sunday Sun 20:30 ET stamps calculation_date with Monday, in both seasons | value changes in the evening: calculation_date in earnings_options_strategy_winners and the insights table becomes the Sunday the sweep ran (rows already stored are not rewritten) |
| `gcp/earnings_long_watchlist.py:125` | `_query_watchlist` | SQL `CURRENT_DATE` | `market_today_sql()` | yes, on schedule: Sun 19:45 ET in winter the window is Monday..Monday+7 | changes query results: in the evening the window moves back one day |
| `gcp/earnings_long_watchlist.py:338` | `main` | host-today | `market_today()` | yes, on schedule: earnings-long-watchlist-sunday Sun 19:45 ET reads Monday as today in winter (the post date and the source-age check; its SQL window at line 125 uses CURRENT_DATE, also Monday) | value changes in the evening: the post is dated Sunday; with the SQL site at line 125, taken in the same stage, the window is Sunday..Sunday+7 |
| `gcp/refresh_earnings_views.py:136` | `refresh_daily` | host-today | `market_today()` | no: refresh_daily runs 07:30 ET; the Sunday 20:00 run is --mode=weekly and does not call it | none at 07:30 ET |
| `gcp/refresh_earnings_views.py:144` | `refresh_daily` | SQL `CURRENT_DATE` | `market_today_sql()` | no: refresh_daily runs 07:30 ET | changes query results: in the evening the window moves back one day |

**C. AV options nightly and the option builders** (11 sites, 4 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `gcp/fetchers/fetch_av_historical_options.py:208` | `_resolve_start_from_latest` | host-today | `market_today()` | no: only with an empty ticker list | none on the scheduled path |
| `gcp/fetchers/fetch_av_historical_options.py:241` | `_resolve_start_from_latest` | host-today | `market_today()` | only when no EOD row exists for any ticker (a first run): the start would be tomorrow at 21:00 ET | value changes in the evening (first run only) |
| `gcp/fetchers/fetch_av_historical_options.py:300` | `main` | host-today | `market_today()` | no: the scheduled run passes --from-latest, which sets start_date | none on the scheduled path |
| `gcp/fetchers/fetch_av_historical_options.py:301` | `main` | host-today | `market_today()` | yes, on schedule: av-options-daily 21:00 ET asks AlphaVantage for tomorrow's chain Mon-Thu (4 calls and 4 'Date parameter out of range' warnings a night) | value changes in the evening: the range ends today; no stored row changes (AV returns no data for tomorrow) |
| `gcp/fetchers/fetch_av_historical_options.py:309` | `main` | host-today | `market_today()` | only if run by hand in the evening without a range | value changes in the evening (hand run) |
| `gcp/fetchers/build_options_daily_features.py:50` | `main` | host-today | `market_today()` | yes, on schedule: options-daily-features 22:00 ET: the --days=7 window is [D-6, D+1], not [D-7, D] | value changes in the evening: the recompute window reaches one day further back; rows are upserts, so no stored value changes |
| `gcp/fetchers/build_options_daily_features.py:51` | `main` | host-today | `market_today()` | yes, on schedule: as line 50 | value changes in the evening: as line 50 |
| `gcp/build_options_daily_greeks.py:168` | `main` | host-today | `market_today()` | yes, on schedule: options-daily-greeks 23:15 ET: the window is [D-6, D+1], not [D-7, D] | value changes in the evening: window one day further back; upserts |
| `gcp/build_options_daily_greeks.py:170` | `main` | host-today | `market_today()` | yes, on schedule: as line 168 | value changes in the evening: as line 168 |
| `gcp/build_realtime_gex.py:191` | `main` | host-today | `market_today()` | no: realtime-gex-daily runs 17:00 ET (22:00 UTC, the same date) | none at 17:00 ET |
| `gcp/build_realtime_gex.py:194` | `main` | host-today | `market_today()` | no: as line 191 | none at 17:00 ET |

**D. Daytime fetchers** (10 sites, 7 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `gcp/fetchers/fetch_top_movers.py:81` | `fetch_top_movers` | host-today | `market_today()` | no: runs 09:30-16:15 ET | none at those hours |
| `gcp/fetchers/fetch_premarket_refresh.py:387` | `main` | host-today | `market_today()` | no: runs 08:20 ET | none at 08:20 ET |
| `gcp/fetchers/fetch_economic_events.py:262` | `fetch_fred_releases` | host-today | `market_today()` | no: runs 07:00 ET | none at 07:00 ET |
| `gcp/fetchers/fetch_fred_rates.py:156` | `main` | host-today | `market_today()` | no: runs 06:30 ET | none at 06:30 ET |
| `gcp/fetchers/fetch_sec_filings.py:427` | `_earnings_calendar_tickers` | SQL `CURRENT_DATE` | `market_today_sql()` | no: its job has no evening run | changes query results: in the evening the window moves back one day |
| `gcp/fetchers/fetch_sec_filings.py:483` | `main` | host-today | `market_today()` | no: runs 07:00, 10:00, 13:00 and 17:00 ET | none at those hours |
| `gcp/fetchers/fetch_insider_transactions.py:80` | `fetch_for_ticker` | host-today | `market_today()` | no: runs 07:00 ET | none at 07:00 ET |
| `gcp/fetchers/fetch_insider_transactions.py:126` | `_earnings_calendar_tickers` | SQL `CURRENT_DATE` | `market_today_sql()` | no: its job has no evening run | changes query results: in the evening the window moves back one day |
| `gcp/fetchers/backfill_daily_indicators.py:202` | `_tickers_with_gaps` | SQL `CURRENT_DATE` | `market_today_sql()` | no: its job has no evening run | changes query results: in the evening the window moves back one day |
| `gcp/fetchers/backfill_daily_indicators.py:388` | `_filter_recent_rows` | host-today | `market_today()` | no: runs 02:30 and 03:00 ET | none at those hours |

**E. Signal monitor, trade log, weekend review** (7 sites, 3 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `gcp/signal_monitor.py:381` | `SignalMonitor.fetch_latest_bar` | host-today | `market_today()` | no: the monitor runs 09:25-16:00 ET | none during market hours |
| `gcp/trade_logger.py:61` | `TradeLogger._daily_file` | host-today | `market_today()` | no: its callers run 09:25-16:00 ET (signal-monitor) and Sat 09:00 ET (weekend-review) | none at those hours |
| `gcp/trade_logger.py:87` | `TradeLogger.log_trade` | host-today | `market_today()` | no: as line 61 | none at those hours |
| `gcp/trade_logger.py:173` | `TradeLogger.get_daily_trades` | host-today | `market_today()` | no: as line 61 | none at those hours |
| `gcp/trade_logger.py:208` | `TradeLogger.get_weekly_trades` | host-today | `market_today()` | no: as line 61 | none at those hours |
| `gcp/trade_logger.py:224` | `TradeLogger.get_weekly_trades` | host-today | `market_today()` | no: as line 61 | none at those hours |
| `gcp/weekend_review.py:116` | `generate_weekly_review` | host-today | `market_today()` | no: weekend-review-weekly runs Sat 09:00 ET | none at 09:00 ET |

**F. Jobs with no scheduler, or one outside the evening** (10 sites, 7 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `gcp/backtest_job.py:81` | `_resolve_window` | host-today | `market_today()` | only if dispatched in the evening (no scheduler; Discord /backtest) | value changes in the evening: the default window ends today |
| `gcp/audit_job_runner.py:125` | `main` | host-today | `market_today()` | no: runs Sat 09:00 and Sun 10:00 ET | none at those hours |
| `gcp/indicator_correlation_job.py:744` | `main` | host-today | `market_today()` | only if run by hand in the evening (no scheduler) | value changes in the evening (hand run) |
| `gcp/regime_combo_job.py:199` | `main` | host-today | `market_today()` | no: runs Sun 05:00 ET | none at 05:00 ET |
| `scripts/calibrate_thresholds.py:152` | `calibrate_ticker` | host-today | `market_today()` | no: as line 229 | none at 02:00 ET |
| `scripts/calibrate_thresholds.py:229` | `fetch_bars` | host-today | `market_today()` | no: calibrate-thresholds-quarterly runs 02:00 ET | none at 02:00 ET |
| `scripts/calibrate_thresholds.py:390` | `_parse_as_of` | host-today | `market_today()` | no: as line 229 | none at 02:00 ET |
| `scripts/run_param_sweep.py:133` | `apply_winner` | SQL `CURRENT_DATE` | `market_today_sql()` | only if dispatched in the evening with --apply: exit_config_overrides.calibration_date would be tomorrow | value changes in the evening: the calibration_date the statement writes is the Eastern day |
| `scripts/run_param_sweep.py:266` | `main` | host-today | `market_today()` | only if dispatched in the evening (no scheduler) | value changes in the evening (the lookback starts one day earlier) |
| `scripts/fetch_catalyst_calendar.py:618` | `main` | host-today | `market_today()` | only if run by hand in the evening (main(); the API imports other functions of this file) | value changes in the evening (hand run) |

**G. API routes** (8 sites, 5 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `platform/api/main.py:1143` | `get_reference_levels` | host-today | `market_today()` | yes, on request in the evening: a date 29 days back is judged 30 days old | value changes in the evening: the is_recent boundary only |
| `platform/api/routers/catalysts.py:175` | `get_catalyst_events` | host-today | `market_today()` | yes, on request in the evening: the default window is today-2..today+15 | value changes in the evening: the /api/catalysts default window moves back one day |
| `platform/api/routers/catalysts.py:621` | `get_catalysts_for_ticker` | host-today | `market_today()` | yes, on request in the evening: as line 175 | value changes in the evening: the per-ticker window moves back one day |
| `platform/api/routers/catalysts.py:685` | `get_catalyst_snapshot` | host-today | `market_today()` | yes, on request in the evening: the snapshot cutoff is tomorrow | value changes in the evening: the cutoff is today |
| `platform/api/routers/dashboard.py:303` | `_apply_live_overlay` | host-today | `market_today()` | no: the host branch runs only if ET_TZ is None, which a working image never has | none (removes a dead branch) |
| `platform/api/routers/grid.py:254` | `_load_chain_for_live` | host-today | `market_today()` | yes, on request in the evening: the 20-day floor and days_behind count from tomorrow | value changes in the evening: days_behind for the EOD fallback drops by one |
| `platform/api/routers/grid.py:1244` | `get_grid_timeseries` | host-today | `market_today()` | yes, on request in the evening of an expiry day: today's expiration is treated as past | value changes in the evening: the default expiration is today's until midnight Eastern |
| `gcp/research/strat_engine/strat_pred_serve.py:372` | `predict_one` | host-today | `market_today()` | yes, on request in the evening through the API: the 30-day feature window starts one day late | value changes in the evening: window start one day earlier; the latest bar is unchanged |

**H. Discord service** (1 site, 1 file)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `gcp/discord_interactions/main.py:136` | `parse_date_arg` | host-today | `market_today()` | yes, on request in the evening: /replay and /validate read 'today' as tomorrow, '-1' as today, and accept tomorrow's date | value changes in the evening: relative dates resolve to the Eastern day |

**I. Library defaults** (7 sites, 6 files)

| Site | Function | Rule | Replacement | Wrong today? | What changes |
|---|---|---|---|---|---|
| `lib/agents/summarizers.py:152` | `_check_chain_freshness` | host-today | `market_today()` | only when a caller passes no as_of and runs in the evening (an insight refresh from the API): the chain age counts one more trading day | value changes in the evening: the stale-chain verdict comes one trading day later |
| `lib/agents/summarizers.py:850` | `summarize_gamma_levels` | host-today | `market_today()` | only when a caller passes no as_of and runs in the evening: days_behind is one more | value changes in the evening: the gamma freshness tier changes one day later |
| `lib/data_loader.py:259` | `_check_staleness` | host-today | `market_today()` | only for a caller that opts in (on_stale warn or error; the default is silent) and runs in the evening | value changes in the evening: the staleness age drops by one |
| `lib/strategies/calibration.py:132` | `_latest_calibration` | host-today | `market_today()` | only when as_of is not passed and the caller runs in the evening | value changes in the evening: the calibration age drops by one (stale threshold) |
| `lib/strategies/exit_config_overrides.py:145` | `_latest_overrides` | host-today | `market_today()` | only when signals are evaluated in the evening (lib.signals.evaluate_signal: a backtest or replay started then; the route was not traced); the monitor calls it in market hours | value changes in the evening: the override age drops by one (stale threshold) |
| `lib/indicators.py:734` | `calculate_orb` | host-today | no clock needed: add the minutes to a fixed date | no: the date is thrown away (combine, add minutes, take .time()) | none |
| `lib/trading_analysis.py:618` | `MarketAnalyzer._calculate_orb` | host-today | no clock needed | no: as lib/indicators.py:734 | none |

## Appendix B: the 31 baseline entries that stay in these 39 files

| Site | Rule | Stays for |
|---|---|---|
| `gcp/audit_job_runner.py:116` `main` | host-today | stage 3 deployed instants |
| `gcp/build_realtime_gex.py:82` `_load_realtime_chain` | utc-parse | stage 6 conversions and SQL dates |
| `gcp/build_realtime_gex.py:107` `_load_intraday_spots` | utc-parse | stage 7 blocked bar readers |
| `gcp/build_realtime_gex.py:116` `compute_realtime_frame` | host-today | stage 3 deployed instants |
| `gcp/build_realtime_gex.py:120` `compute_realtime_frame` | host-today | stage 3 deployed instants |
| `gcp/fetchers/backfill_daily_indicators.py:1` `<module>` | sql-utc-date | stage 6 conversions and SQL dates |
| `gcp/research/strat_engine/strat_pred_serve.py:379` `predict_one` | utc-parse | stage 6 conversions and SQL dates |
| `gcp/research/strat_engine/strat_pred_serve.py:380` `predict_one` | utc-parse | stage 6 conversions and SQL dates |
| `gcp/research/strat_engine/strat_pred_serve.py:396` `predict_one` | utc-parse | stage 6 conversions and SQL dates |
| `gcp/signal_monitor.py:768` `SignalMonitor._bound_daily_frame` | tz-localize-none | stage 6 conversions and SQL dates |
| `gcp/signal_monitor.py:772` `SignalMonitor._bound_daily_frame` | tz-localize-none | stage 6 conversions and SQL dates |
| `gcp/signal_monitor.py:1180` `SignalMonitor._evaluate_strategies_for_bar` | host-today | stage held: needs a decision |
| `gcp/signal_monitor.py:1644` `SignalMonitor.fire_alert` | host-today | stage 3 deployed instants |
| `gcp/signal_monitor.py:1921` `SignalMonitor._now` | tz-localize-none | stage 6 conversions and SQL dates |
| `gcp/signal_monitor.py:2052` `SignalMonitor._corrected_rvol` | tz-localize-none | stage 6 conversions and SQL dates |
| `gcp/signal_monitor.py:2055` `SignalMonitor._corrected_rvol` | tz-localize-none | stage 6 conversions and SQL dates |
| `gcp/signal_monitor.py:2057` `SignalMonitor._corrected_rvol` | tz-localize-none | stage 7 blocked bar readers |
| `gcp/signal_monitor.py:2129` `SignalMonitor._check_exits` | host-today | stage 3 deployed instants |
| `lib/data_loader.py:872` `DataLoader._strip_timezone` | tz-localize-none | stage 7 blocked bar readers |
| `lib/data_loader.py:874` `DataLoader._strip_timezone` | tz-localize-none | stage 7 blocked bar readers |
| `lib/trading_analysis.py:115` `MarketAnalyzer._archive_file` | host-today | stage 3 deployed instants |
| `platform/api/main.py:983` `get_market_data` | tz-localize-none | stage 7 blocked bar readers |
| `platform/api/main.py:1221` `_reference_from_gcs_local_dev` | tz-localize-none | stage 6 conversions and SQL dates |
| `platform/api/routers/catalysts.py:115` `_news_sql` | sql-utc-date | stage 6 conversions and SQL dates |
| `platform/api/routers/dashboard.py:492` `_build_movement_level_map` | tz-localize-none | stage 6 conversions and SQL dates |
| `scripts/fetch_catalyst_calendar.py:561` `_save_catalysts_locked` | host-today | stage 3 deployed instants |
| `scripts/fetch_earnings_calendar.py:200` `fetch_alphavantage_earnings` | host-today | stage 3 deployed instants |
| `scripts/fetch_earnings_calendar.py:671` `_fetch_yahoo_bulk` | host-today | stage 3 deployed instants |
| `scripts/fetch_earnings_calendar.py:763` `_fetch_yahoo_one` | host-today | stage 3 deployed instants |
| `scripts/fetch_earnings_calendar.py:807` `_fetch_yahoo_one` | host-today | stage 3 deployed instants |
| `scripts/fetch_earnings_calendar.py:1069` `EarningsCalendarFetcher.fetch_unusual_whales_earnings` | host-today | stage 3 deployed instants |

## Appendix C: the stages, and the end condition

| Stage | What | Sites | Files |
|---|---|---|---|
| **1 (this spec)** | Dates in deployed code: `host-today` date sites, and `CURRENT_DATE` in the same files | 71 | 39 |
| 2 | `CURRENT_DATE` in the rest of deployed code (the ranker, the watchdog's sanity windows, four more files); and a scanner rule for an aware UTC "now" truncated to a date, with its 16 sites baselined and the deployed ones fixed | 18, plus 16 new | 8, plus 9 |
| 3 | Instants in deployed code (`utc_now()`); no value changes | 33 | 19 |
| 4 | Zones built locally and fixed offsets | 8 | 6 |
| 5 | Hand-run scripts, research modules and hand-run SQL | 69 | 39 |
| 6 | Conversions that are not bar reads; needs one public helper for "a stored TIMESTAMPTZ as an aware UTC index" | 70 | 40 |
| 7 | The 32 readers of `market_data_intraday`, after the misplaced rows are removed and verified (#1190), then the end condition | 32 | 21 |
| held | `gcp/premarket_brief.py` (5), the four in-flight files (9), `backtest.py:649`, and the two undecided sites: each joins its stage when its owner is done | 17 | 8 |
| end | Review of the 21 `tz-ok` lines that are not blocked | 21 | 9 |

71 + 18 + 33 + 8 + 69 + 70 + 32 + 17 + 21 = 339 rows of the inventory.

- **One PR may carry several capabilities' files.** `scripts/gate/spec_gate.py` binds a changed file to a capability in two places only: process files to FEAT-CICD-001 (`:4835-4838`) and deploy files to FEAT-DEPLOY-001 (`:4839-4842`). None of the 139 baseline files is either. The catalog's Code fields spread stage 1 over FEAT-DATA-001 (21 sites), no field (19), FEAT-DEBT-001 (16) and eight others; only FEAT-DATA-001's record is edited at close-out, as `check_product_scope` requires.
- **End condition:** the baseline file is `{}`; the scanner has first been widened to what it cannot see today, so that an empty baseline is a statement about the code; every remaining `# tz-ok:` names a contract (Decision 7); and `tests/meta/test_timezone_boundaries.py` no longer reads a baseline at all: it asserts `current_hits() == {}`, and the fixture and `--write-baseline` are deleted.
