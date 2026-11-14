---
feat_id: FEAT-PLAYBOOK-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-004, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "tests/gcp/test_premarket_brief.py::TestLiveDateIsTheExchangeDate::test_sunday_evening_run_is_dated_sunday passes for both parameters, winter (exchange clock 2026-11-15 21:00 America/New_York, host date 2026-11-16) and summer (2026-07-12 21:00 America/New_York, host date 2026-07-13): with BRIEF_AS_OF unset, generate_premarket_brief returns analysis_date 2026-11-15 and 2026-07-12, calls load_earnings_for_brief with weekly=True (windows 2026-11-16 to 2026-11-20 and 2026-07-13 to 2026-07-17), does not call load_yesterday_amc_reactions, calls load_economic_events with days_ahead=7, and persist_to_cloud_sql inserts history rows dated that Sunday and no row dated the Monday; both parameters fail on origin/main, which dates the run Monday and calls the daily earnings loader"
  - "tests/gcp/test_premarket_brief.py::TestLiveDateIsTheExchangeDate::test_monday_run_after_sunday_writes_the_monday_row passes: against one in-memory pair of tables, a scheduled run at exchange clock 2026-11-15 21:00 is followed by a scheduled run at 2026-11-16 08:30 America/New_York whose daily frame holds the session's premarket row; the second run inserts a canonical premarket_analysis row dated 2026-11-16 for every ticker with level_basis premarket_status ok, skips none, and logs no 'row already exists' warning; it fails on origin/main, where the second run writes 0 canonical rows"
  - "tests/gcp/test_premarket_brief.py::TestLiveDateIsTheExchangeDate::test_future_check_and_fallback_use_the_exchange_date passes: at exchange clock 2026-11-15 21:00 America/New_York (host date 2026-11-16), BRIEF_AS_OF=2026-11-16 raises ValueError matching 'future', BRIEF_AS_OF=2026-11-15 returns 2026-11-15, and persist_to_cloud_sql given a brief with no analysis_date writes rows dated 2026-11-15; the first and third assertions fail on origin/main"
  - "tests/gcp/test_premarket_brief.py::TestLiveDateIsTheExchangeDate::test_weekday_morning_run_is_unchanged passes on origin/main and on the branch: at exchange clock 2026-11-10 08:30 America/New_York a scheduled run is dated 2026-11-10, calls load_earnings_for_brief with weekly=False and writes canonical rows dated 2026-11-10"
  - "tests/gcp/test_premarket_brief.py::TestResolveAnalysisDate::test_default_returns_today and ::test_blank_falls_back_to_today, and ::test_brief_pipeline_never_acquires_ew_recap, fix the exchange clock (lib.eastern_time.eastern_now) and assert the exchange date, so none of them depends on the hour the suite runs; python3 -m pytest over every file under tests/ that names premarket_brief passes"
  - "The only file changed under gcp/, lib/, platform/ and scripts/ is gcp/premarket_brief.py, and its diff changes the lib.eastern_time import line, the two date.today() calls in _resolve_analysis_date, the one in persist_to_cloud_sql, and the docstring and comment lines that describe them; gcp/deploy.sh and gcp/schema.sql are unchanged"
  - "tests/fixtures/timezone_boundary_baseline.json, regenerated with python -m tests.meta.test_timezone_boundaries --write-baseline, no longer holds the three host-today entries of gcp/premarket_brief.py (_resolve_analysis_date::date.today() twice, persist_to_cloud_sql::date.today()); its diff removes those three entries and nothing else, so the two tz-localize-none entries of the file remain; gcp/premarket_brief.py gains no tz-ok comment; python3 -m pytest tests/meta/test_timezone_boundaries.py passes"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-PLAYBOOK-001, DASHBOARD-01) note row carries that source_identity_sha256"
  - "The FEAT-PLAYBOOK-001 catalog record (Status, Last reviewed) and the PR traceability entry are updated, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# The brief's live date is the exchange's date

## Authority and status

Draft, written 2026-11-14 for the owner. Nothing is approved and no code is written under it. Merging
this spec-only PR with `status: approved` is the approval. The section-by-section conversation of the
product-delivery skill is replaced here by "Decisions for the owner" (one decision).

Deadline: the fix has to be merged and deployed before Sunday 2026-11-15 21:00 America/New_York
(2026-11-16 02:00 UTC), when `premarket-brief-sunday` next runs.

Every statement is marked by its source: **read** (code on `origin/main` at `20d9c47b`), **live** (a
read-only `gcloud` or `scripts/db_query_cr.sh` call without `--commit` on 2026-11-14, execution named),
**run** (executed on 2026-11-14, see "How the runs were made"), or **not checked**.

## Intake

- Capability. Catalog row, `docs/product/02-FEATURE-CATALOG.md` line 22: "FEAT-PLAYBOOK-001 | Premarket
  / playbook | Structured daily setups | `/playbook` | `/api/playbook` | `premarket_analysis`,
  `playbook_cards` | Production but needs remediation | P0". Its record (line 222) names
  `gcp/premarket_brief.py` as Code. The spec gate fixes a capability by path only for process files
  (FEAT-CICD-001) and deploy files (FEAT-DEPLOY-001), `scripts/gate/spec_gate.py:1114-1119` and
  `:4836-4841`; any other file takes its FEAT from the branch name, so this fix is
  `fix/feat-playbook-001-<slug>` under the record that names the file.
- Requirements: REQ-PLAYBOOK-001 (a plan shows its data time), REQ-DATA-004 (sessions and DST resolve
  through one shared calendar), REQ-REL-001 (live and replay stay in step; the replay path is not
  changed).
- Issues: none found. A GitHub search for "premarket sunday" returns #1168 and #396, both closed and
  neither this defect.
- Canvases: none (`docs/product/canvases.yml` has no entry for FEAT-PLAYBOOK-001).
- SITE component: DASHBOARD-01, the briefing strip, which serves the newest live `premarket_analysis`
  row. `gcp/` and `tests/` are inside the watched scope of `docs/product/03-SITE-TRACEABILITY.md`
  (`docs/DOC_REGISTRY.md` line 196), so the implementation PR needs a declared note. The brief specs
  that changed which row or value the strip serves declared the same element
  (`2026-11-11-feat-data-001-brief-holiday-freshness.md`, `2026-11-11-feat-signal-001-brief-rsi-bands-r2.md`).

## Problem

`_resolve_analysis_date()` returns `date.today()` when `BRIEF_AS_OF` is unset
(`gcp/premarket_brief.py:883-897`, the read at `:893`). The job's container runs on UTC: the live job
sets no `TZ` (live, `gcloud run jobs describe premarket-brief`: its env names hold none).
`premarket-brief-sunday` fires Sunday 21:00 America/New_York (`gcp/deploy.sh:4454`, `0 21 * * 0`; live,
`gcloud scheduler jobs list`: ENABLED, America/New_York), which is Monday 01:00 or 02:00 UTC. So the
Sunday run dates itself Monday.

1. It writes Monday's canonical `premarket_analysis` row on Sunday evening, with no premarket snapshot.
   On Monday the 08:30 run finds a live row for the date and ticker and skips the canonical write
   (`:3227-3249`, "Skipped premarket_analysis write ... row already exists").
   - live, `db-query-cl4zv`: `premarket_analysis_history` for SPY, analysis_date 2026-11-09 holds a row
     written 2026-11-08 21:01:23 ET by `cloud-scheduler:premarket-brief-sunday` and one written
     2026-11-09 08:31:01 ET by `cloud-scheduler:premarket-brief-daily`; the canonical row for 2026-11-09
     carries `analysis_ts` 2026-11-08 21:01:23 ET. Same shape for 2026-11-02 and 2026-07-13.
   - live, `db-query-cl4zv`: since 2026-06-01 each of SPY, QQQ and IWM has 22 Monday-dated live rows,
     and 22 of 22 were written the day before. Every history row the Sunday entry wrote since
     2026-06-01 (72) is dated a Monday.
   - run: on main, a Monday 08:30 run after a Sunday run writes 0 canonical rows and posts a brief whose
     triggers are the premarket high and low (PMK_H, PMK_L), while the stored row keeps Sunday's triggers
     (PMC, PQC, PML) and `premarket_status` `premarket_unavailable`. On Mondays Discord and the stored row
     disagree.
   - Who reads the stored row on Monday, each by Eastern date (read): the signal monitor's level build
     and brief bias (`gcp/signal_monitor.py:929`, `:976`, `:2100`), the insight planner
     (`lib/agents/summarizers.py:599`), the movement statement (`platform/api/routers/dashboard.py:455-457`),
     the 21:15 resolver (`gcp/premarket_playbook_resolver.py:431`), and the briefing strip.
     `level_basis` has been written only since 2026-11-11 (live, `db-query-qnt5l`), so Monday 2026-11-16
     would be the first Monday on which these consumers rebuild their levels from a Sunday-built basis.
2. The Sunday run never selects the week-ahead view it is scheduled for: `is_sunday =
   today.weekday() == 6` (`:1296`) is computed from the same date. run: on main at both Sunday clocks the
   earnings loader is called with `weekly=False` for the Monday, the prior-day reaction loader runs, and
   the post carries Monday's date with the daily messages "Earnings Today" and "Economic Calendar".
3. The slot wrote Sunday-dated rows until it moved. live, `db-query-qnt5l`: live rows dated Sunday
   2026-05-03 and 2026-05-10 were written at 09:00 ET by `cloud-scheduler:premarket-brief-sunday`. The
   entry moved to 21:00 on 2026-05-14 (read, `git log -S'"0 21 * * 0"' -- gcp/deploy.sh`: d037f3d5, #488),
   and no weekend-dated live row exists since (live, `db-query-cl4zv`). The move is where the defect
   began.

## Non-goals

- No schedule change, no `TZ` on the job, no change to `gcp/deploy.sh`.
- No change to the rule that a scheduled run does not overwrite an existing live row, to `--update` or
  `BRIEF_UPDATE`, or to replays (`BRIEF_AS_OF` still wins).
- No rewrite of stored rows. The 22 past Mondays per ticker stay as they are.
- No change to what the week-ahead view contains, to the level builder, or to the Discord layout.
- Not the other two baseline entries of this file (section "The file's five ratchet entries").
- Not the other jobs that read the host clock in the evening (section "Other evening jobs"), and not
  `gcp/fetchers/fetch_premarket_refresh.py:387`, which has the same read, runs at 08:20 ET when both
  dates agree, and belongs to FEAT-DATA-001 (its catalog record, line 530, names `gcp/fetchers/`).

## Approaches considered

1. **Set `TZ=America/New_York` on the job.** Fixes this job by configuration and leaves the code
   reading the host clock, so the next job built from the image, a local run and a test all keep the
   defect; it would also move every other naive clock read in the process (log stamps,
   `datetime.now()` in imported modules), which no test covers (not run). Rejected.
2. **Let the Monday run overwrite a row the Sunday run wrote.** Keeps writing a Monday row on Sunday
   evening, which the site serves as Monday's brief until 08:30, keeps the Sunday post in daily mode,
   and weakens the protection of the canonical row for one case. Rejected.
3. **Date the Sunday run for the next session on purpose and skip its canonical write.** Keeps the
   Sunday post's levels framed for Monday (see consequence 1 below), but needs two dates in the run (the
   day it runs, the session it describes), a skip rule and new tests. It is a redesign of the Sunday
   run, not this defect, and does not fit before Sunday. Named in "Decisions for the owner" as the
   separate work to ask for if the Sunday post should carry Monday's levels.
4. **Use the exchange's date. Chosen.** `lib.eastern_time.market_today()` (`lib/eastern_time.py:561-568`)
   exists for this; its docstring states the trap. Four lines in one file.

## Design

In `gcp/premarket_brief.py`, and nowhere else:

| Line on main | Now | After |
|---|---|---|
| 22 | `from lib.eastern_time import ET, ET_NAME` | adds `market_today` |
| 893 | `return date.today()` | `return market_today()` |
| 895 | `if parsed > date.today():` | `if parsed > market_today():` |
| 3028 | `brief.get('analysis_date') or date.today()` | `... or market_today()` |

plus the docstring of `_resolve_analysis_date` and the comment above line 3028, which say "today".

Tests freeze the clock without a new dependency: `lib.eastern_time.eastern_now` is replaced (the
pattern of `tests/api/test_market_hours_endpoint.py:51`) and `gcp.premarket_brief.date` is replaced by
a subclass whose `today()` returns the UTC date (the pattern of `tests/gcp/test_premarket_brief.py:3632-3636`),
so each new test fails on main for the stated reason. Three existing tests pin the host clock and are
rewritten to pin the exchange clock (done_when item 5). run: with the four lines changed, the 30 test
files that name `premarket_brief` plus the ratchet gave 2 failed, 1281 passed, 17 skipped (main: all
pass). The two failures are `test_brief_pipeline_never_acquires_ew_recap[2026-04-27-True]`, which
replaces `pb.date`, and the ratchet (below). The two `TestResolveAnalysisDate` tests that compare with
`date.today()` passed at the hour of the run and would fail between 00:00 UTC and Eastern midnight.

Plan size: about five tasks (the failing frozen-clock tests; the four lines; the three existing tests;
the baseline; the SITE note, sidecar, catalog and traceability records).

### How the runs were made

`gcp.premarket_brief.main([])` was run end to end from a scratch script outside the repository (not
committed), on `origin/main` and on a scratch copy with the four lines changed. Replaced: the clock
(frozen, process zone UTC as in the container), sockets (refused), Cloud SQL reads (answered from rows
read from production that day, `db-query-qnt5l`: the loader's own daily query for SPY, QQQ and IWM, the
brief's own earnings query for 2026-11-15 to 2026-11-20 and the events query, cut to what the tables
hold at the frozen instant), Cloud SQL writes (in-memory tables), level parameters (the fixture of
`tests/lib/level_params_fixtures.py`), the RSI calibration row (none, Tier B), the gamma probe
(unavailable), model text (off) and the Discord webhook (captured). The Monday run's premarket row is
simulated from the previous row's premarket columns. Check against a known case: frozen at 2026-11-09
02:00 UTC, main dated the run 2026-11-09 and gave `signal_status` CALL building (2/5), CALL setup (3/5)
and No signal for SPY, QQQ and IWM, the values production stored that night (`db-query-cl4zv`). Trigger
prices are not compared with production, because the parameters are the fixture's.

### What the Sunday run does, on main and after the change (run)

| | main, 2026-11-15 21:00 EST | changed, same clock | changed, 2026-07-12 21:00 EDT |
|---|---|---|---|
| `date.today()` / exchange date | 2026-11-16 / 2026-11-15 | same | 2026-07-13 / 2026-07-12 |
| analysis_date | 2026-11-16 | 2026-11-15 | 2026-07-12 |
| Daily-data freshness | fresh (last bar 2026-11-13) | fresh (last bar 2026-11-13) | fresh (last bar 2026-07-10) |
| History rows | 3, dated 2026-11-16 | 3, dated 2026-11-15 | 3, dated 2026-07-12 |
| Canonical rows | 3, dated 2026-11-16, live | 3, dated 2026-11-15, live | 3, dated 2026-07-12, live |
| `premarket_status` | premarket_unavailable | premarket_unavailable | premarket_unavailable |
| Earnings loader | daily, 2026-11-16 only | weekly, 2026-11-16 to 2026-11-20 | weekly, 2026-07-13 to 2026-07-17 |
| Prior-day reaction loader | called | not called | not called |
| Events window | 5 days from Monday | 7 days from Sunday | 7 days from Sunday |
| Discord messages | brief dated Mon Nov 16; Ticker Analysis; Strat Playbook; Earnings Today; Economic Calendar | brief dated Sun Nov 15; Ticker Analysis; Strat Playbook; Earnings Week Ahead; Economic Calendar, Week Ahead | the same five, dated Sun Jul 12; the two week-ahead messages are the empty forms, because the rows read from production cover November only |
| Raised | nothing | nothing | nothing |

`signal_status` is the same on main and after the change for all three tickers at both clocks. The
freshness rule accepts a Sunday that reads Friday and refuses one that reads Thursday (run,
`lib.strat_levels.daily_data_freshness`: last bar 2026-11-13 gives fresh, 2026-11-12 gives
STALE_DAILY_DATA). A weekday run is unchanged: at 2026-11-10 08:30 EST the two trees' outputs are equal
field for field (run).

### Consequences

1. **The Sunday post's levels are framed on Sunday, not on Monday.** The level builder's weeks run
   Monday to Sunday, so on a Sunday the week that just ended is still the current week. run: for SPY at
   the winter clock, main (session Monday) gives PWH 763.04, PWL 741.025, PWC 754.37 from the week of
   2026-11-09; the changed run (session Sunday) gives PWH 775.64, PWL 732.71, PWC 735.29 from the week
   of 2026-11-02 and shows the ended week's open as the current week open. For all three tickers at
   both clocks only those weekly levels differ (PWH, PWL, PWC, PWO, CWO); daily, monthly, quarterly and
   yearly levels are equal. In the summer run this changes the picked triggers (IWM
   calls PWC 297.58 where the Monday framing gives PDH 298.21). The Sunday post therefore stops being a
   preview of Monday's playbook; Monday's own post at 08:30 carries Monday's levels with premarket. The
   rows dated 2026-05-03 and 2026-05-10 were framed the same way.
2. **What the Sunday run stores** is the one decision below.
3. **Monday 08:30 writes Monday's row.** run: after a Sunday run on the changed tree, the Monday 08:30
   run inserts three canonical rows dated 2026-11-16 with `premarket_status` ok and triggers PMK_H and
   PMK_L, and the Sunday rows stay dated 2026-11-15. On main the same run inserts none. The summer pair
   behaves the same.
4. **What a user sees.**
   - Discord, Sunday 21:00: the title carries Sunday's date; the earnings message is the week-ahead
     view and the calendar is grouped by day for the week; the ticker and playbook messages are framed
     as in consequence 1.
   - Site, Sunday 21:00 to Monday 08:30: no Monday brief exists. `GET /api/dashboard/brief/{ticker}`
     returns the newest live row (`platform/api/routers/dashboard.py:116-118`): under decision (a) the
     row dated Sunday, built on Friday's close; under (b) Friday's row, which is what the route returns
     on any other morning before 08:30 (the previous session's brief). The movement statement and the
     planner look for a row dated today in Eastern time, find none on Monday before 08:30 and build
     their own levels, as on every other weekday (`lib/movement_statement.py:412-426`: "before the brief
     has run, there is no row for today and every rung reports that honestly").
   - From Monday 08:30 the site, the monitor and the resolver use the row built with the 08:20
     premarket snapshot.
5. **Existing rows are not rewritten.** The Monday rows written on Sundays stay; their `analysis_ts`
   already tells them apart.
6. **`BRIEF_AS_OF` on a Sunday evening.** A replay for the coming Monday is refused as "in the future"
   until Eastern midnight; today it is accepted from 19:00 or 20:00 Eastern on (run at the winter
   clock: main returns 2026-11-16 for `BRIEF_AS_OF=2026-11-16`, the changed tree raises). No replay of
   a past date changes.

### How each reader treats a canonical row whose date is not a session (read, unless marked)

Precedent rows: 2026-07-03 (a Friday holiday, written that morning at 08:30 ET) and 2026-09-07 (Labor
Day, written by the Sunday run), each never resolved (`outcome_resolved_at` null, live `db-query-cl4zv`),
and the Sunday rows of 2026-05-03 and 2026-05-10.

| Reader | How it picks a row | A Sunday-dated row |
|---|---|---|
| 21:15 resolver | `gcp/premarket_playbook_resolver.py:615-633`: unresolved dates with `isodow < 6`; its docstring names "the Sunday brief writes rows dated Sunday" | never selected; a weekday holiday is classed benign (`:692`) |
| Signal monitor, level build and brief bias | Eastern date of the bar, `gcp/signal_monitor.py:929`, `:976`, `:2100`; `lib/strategies/brief_bias.py:86` | never read: the monitor runs Monday to Friday |
| Insight planner | Eastern date of the run, `lib/agents/summarizers.py:502-513`, `:599` | read only by a report generated on that Sunday; without the row it builds the same Sunday framing itself |
| Movement statement | Eastern today, `platform/api/routers/dashboard.py:455-457`, `lib/movement_statement.py:421-426` | read on that Sunday only; reach rates count resolved rows only (`:347`), so it never enters them |
| Briefing strip | newest live row, `platform/api/routers/dashboard.py:116-118` | served from Sunday 21:00 until Monday 08:30; the route returns no levels |
| Freshness audit | newest live date per ticker, `scripts/audit_data_freshness.py:206-216`, `:475-488`, `:712` | anchored at 16:00 Eastern, does not raise (run). A Monday whose 08:30 run fails then reads ok at 19:30 (24 h), as a failed run does on any weekday; without the Sunday row it would read stale (72 h) |
| `audit-brief-bias` | `signal_alerts` only, `scripts/analysis/verify_brief_bias.py:152-154` | not a reader of this table |
| Discord `/replay`, brief validation | the requested date, `gcp/discord_interactions/main.py:351-357`, `scripts/validation/validate_brief_accuracy.py:343-355` | read only when that Sunday is asked for |

### The file's five ratchet entries

`tests/fixtures/timezone_boundary_baseline.json` lists five hand-written sites for
`gcp/premarket_brief.py` (read; `tests/meta/test_timezone_boundaries.py` passes on main, run).

| Rule | Enclosing function | Expression | This fix |
|---|---|---|---|
| host-today | `_resolve_analysis_date` | `date.today()` (line 893) | cleared, `market_today()` |
| host-today | `_resolve_analysis_date` | `date.today()` (line 895) | cleared, `market_today()` |
| host-today | `persist_to_cloud_sql` | `date.today()` (line 3028) | cleared, `market_today()` |
| tz-localize-none | `generate_premarket_brief` | `df.index.tz_localize(None)` (line 1006) | left for the repo-wide sweep |
| tz-localize-none | `generate_premarket_brief` | `df.index.tz_localize(None)` (line 1361) | left for the repo-wide sweep |

run: with the four lines changed the meta test fails naming exactly the three host-today entries as
"no longer occur", so the baseline moves and done_when item 7 covers it. No `# tz-ok:` comment is added
(the file has none today).

The two `tz_localize(None)` sites do the same thing: before `df.loc[idx < cutoff]` cuts the daily frame
to bars dated before the analysis date, they drop the zone from the frame's index if it has one. The
index holds session labels (a date at midnight), not instants. They stay out of this fix because no
helper of `lib/eastern_time.py` replaces them without changing values: the one for an aware index,
`utc_to_eastern_naive`, converts, and a label at 00:00 UTC becomes 19:00 or 20:00 Eastern of the day
before. run: for labels 2026-11-12, 2026-11-13 and 2026-11-16 in UTC and a cutoff of 2026-11-16, the
current expression keeps the first two and the helper keeps all three, which would let the session's
own row in as the last completed bar and change stored levels. On the production path the expression
is not evaluated at all: the Cloud SQL loader returns a naive index (run, `DataLoader.load_daily` over
production-shaped rows: `tz = None`). Removing them needs a decision on the daily frame's index
contract, which is the sweep's.

### Other evening jobs that read the host clock (read from each job's live command; none run)

From 19:00 Eastern in winter and 20:00 in summer the host date is tomorrow. Same defect means the
date or weekday decides what the job does. All are left out of this fix and named for the repo-wide
sweep.

| Scheduler entries (America/New_York) | Site | Same defect |
|---|---|---|
| `weekly-earnings-refresh-calendar`, `-history`, `-reactions`, Sun 19:00, 19:15, 19:30 (`gcp/deploy.sh:4777-4779`) | `scripts/fetch_earnings_calendar.py:265`, `gcp/fetchers/fetch_earnings_history.py:354`, `gcp/fetchers/compute_earnings_reactions.py:947`: scope is weekly only if the host weekday is Sunday | **Yes, in winter, and it is live.** `fetch-earnings-history` logged `scope=daily ... force-refetch=1` on Sunday 2026-11-08 (execution `fetch-earnings-history-f74sk`) and `scope=weekly ... force-refetch=277` on Sunday 2026-10-25 under EDT (`fetch-earnings-history-lgxdm`). These jobs feed the week-ahead view |
| `daily-earnings-refresh-calendar`, Mon to Fri 19:00 (`:4773`) | `scripts/fetch_earnings_calendar.py:243`, `:1283`, `:1306`: "tomorrow" and the window are taken from the host date | Yes in winter: "tomorrow" is the day after tomorrow |
| `earnings-long-watchlist-sunday`, Sun 19:45 (`:4782`) | `gcp/earnings_long_watchlist.py:338` (source age and the message date), `:152` (`CURRENT_DATE`) | Yes in winter: the date is Monday's |
| `earnings-sweep-sunday`, Sun 20:30 (`:4796`) | `scripts/calibrate_earnings.py:166`: `CURRENT_DATE` as the calibration date | Yes where that statement runs: stamped Monday. Which path reaches it and its readers: not traced |
| `av-options-daily`, Mon to Fri 21:00 (`:4667`) | `gcp/fetchers/fetch_av_historical_options.py:208`, `:241`, `:300-301`: range end | Yes: the range ends tomorrow. Effect not run |
| `av-intraday-nightly`, Mon to Sat 21:00, `av-intraday-monthly` (`:4741`) | `gcp/fetchers/fetch_alphavantage_intraday.py:1179`: default range end | Same read; a wider end date. Effect not run |
| `options-daily-features` 22:00, `options-daily-greeks` 23:15, Mon to Fri (`:4700`, `:4716`) | `gcp/fetchers/build_options_daily_features.py:50-51`, `gcp/build_options_daily_greeks.py:168-170`: a 7-day window ending today | Same read; the window is one day forward |
| `strat-engine-daily`, Mon to Fri 23:35 (`:4501`) | `gcp/research/strat_engine/strat_data_builder.py:308` (year), `:718` (source lag) | Same read; the lag reads one day more, the year differs on 31 December |
| `fetch-market-data-daily`, Mon to Fri 23:00 | `gcp/fetchers/fetch_market_data.py:742-743`: `CURRENT_DATE` window of the earnings universe | Same read in SQL; its fetch date is Eastern (`:1206`) |
| `premarket-playbook-resolver-daily` 21:15, `gamma-levels-daily` 22:30, `freshness-watchdog` 19:00 and 19:30, `refresh-earnings-views-weekly` Sun 20:00 | `gcp/premarket_playbook_resolver.py:712`, `gcp/research/p2_build_gamma_levels.py:291`, `scripts/audit_data_freshness.py:629`, `gcp/refresh_earnings_views.py:120-123` | No: Eastern or explicit UTC on the scheduled path |

`reconcile-failure-notifier-hourly` targets a service, not a job: not checked.

### Other lanes on this file

- #1832 (`fix/feat-strat-001-brief-exits-in-thirds`, FEAT-STRAT-001) changes `gcp/premarket_brief.py`
  in eight hunks, none at lines 22, 893, 895 or 3028; draft #1845
  (`fix/feat-strat-001-brief-atr-levels`) is based on #1832's branch and adds no hunk to the file.
  run: the four-line change applies to both heads (`87cf6820`, `a121406e`) with one hunk offset by 91
  lines and no conflict, and neither changes the baseline file. After this fix merges each lane merges
  main and regenerates its own SITE note hash and sidecar, as any watched-source change on main
  requires; nothing else is expected.
- Draft spec #1929 names a later FEAT-PLAYBOOK-001 "late slot" change to this file. It starts from main
  after this fix. Its "Found while reading" item on Monday's row is this spec.

## Capacity

No workload runs differently in size: same job, same two scheduler entries, same tickers, no new query
shape.

- **Volume:** per run, 3 history rows and at most 3 canonical rows, as now. The Monday 08:30 run writes
  3 canonical rows it used to skip. The Sunday run's earnings query covers 5 dates, not 1: 1,239
  calendar rows against 577 for the week of 2026-11-16 (live, `db-query-qnt5l`), cut to 25 names after
  the sort.
- **Velocity:** the Sunday run makes one query fewer (no prior-day reaction query in weekly mode); the
  enrichment queries are per run, not per row (run: four in both modes).
- **Wall-clock:** the last 12 production runs took 44 to 79 s (live, `gcloud run jobs executions list`)
  against a task timeout of 1800 s, more than 4 times over. The weekly earnings path last ran in
  production on 2026-05-10 and its time on today's volume is not measured; in the run above it added
  no measurable time with the database answered from memory (3.2 s for either mode). Close-out step 1
  measures it through the production replay path before Sunday.
- **Cost:** $0; no new job, schedule or resource.

## Risks

- **The weekly path is slow or raises on today's data.** It has not run in production since
  2026-05-10. Rows are written after the brief is built, so a failure writes nothing and Monday 08:30
  is unaffected. The winter and summer tests cover the path with fixtures; close-out step 1 runs it on
  production data.
- **A reader mistakes the Sunday row for Monday's.** Every by-date reader asks for the Eastern date
  (table above). The Monday-after test proves the Monday row is written and is the one dated Monday.
- **A test passes only at some hours.** The three existing tests that read the host date are rewritten
  to a fixed exchange clock (done_when item 5).
- **The deploy ships more than this fix.** `./gcp/deploy.sh premarket` builds the image from main.
  Which commit the job's current image (`sha256:ecdcb64407ec...`, live) was built from is not checked.

## Close-out (the owner's steps, on their yes; none is a done_when item)

1. Optional, before the deploy, to time the weekly path on production data through the replay path:
   `gcloud run jobs execute premarket-brief --region=us-east1 --project=adept-mountain-474619-d4
   --update-env-vars="BRIEF_AS_OF=2026-11-08,BRIEF_LLM_DISABLE=1,BRIEF_TRIGGERED_BY=operator:weekly-path-timing" --wait`.
   run on main with the clock at 2026-11-14: it selects the weekly view for 2026-11-09 to 2026-11-13,
   writes three history rows (`run_kind` replay_refresh) and three canonical rows dated 2026-11-08 with
   `run_kind` replay, which the live readers filter out, and posts nothing to Discord. With
   `BRIEF_LLM_DISABLE=1` it makes no model call. It also writes `strat_levels` rows (not run here: that
   write was captured). The execution's duration is the measurement.
2. Deploy before Sunday 21:00 America/New_York: `./gcp/deploy.sh premarket`. A merge to main does not
   ship this job (live, `gcloud builds triggers list`: the two triggers on main are the API and the
   schema). Check: `gcloud run jobs describe premarket-brief --region=us-east1
   --format='value(spec.template.spec.template.spec.containers[0].image)'` no longer prints the digest
   ending `...6beec684b490`.
3. After the Sunday run (from 21:05 Eastern):
   `./scripts/db_query_cr.sh -q "SELECT analysis_date, ticker, run_kind, triggered_by, (written_at AT TIME ZONE 'America/New_York') AS written_et FROM premarket_analysis_history WHERE written_at >= '2026-11-16 01:55+00' ORDER BY written_at; SELECT analysis_date, ticker, run_kind, (analysis_ts AT TIME ZONE 'America/New_York') AS written_et, level_basis->>'premarket_status' AS premarket_status FROM premarket_analysis WHERE analysis_date >= '2026-11-15' ORDER BY 1, 2"`.
   Expected: history rows dated 2026-11-15 by `cloud-scheduler:premarket-brief-sunday`; canonical rows
   dated 2026-11-15 under decision (a), none under (b); no row dated 2026-11-16. The Discord earnings
   message is titled "Earnings Week Ahead".
4. After Monday 08:35 Eastern: the second query again. Expected: canonical rows dated 2026-11-16 with
   `written_et` between 08:30 and 08:32 and a `premarket_status` other than premarket_unavailable (ok
   on 2026-11-11 to 2026-11-13, live `db-query-qnt5l`). And
   `gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="premarket-brief" AND timestamp>="2026-11-16T13:29:00Z" AND textPayload:"row already exists"' --project=adept-mountain-474619-d4 --limit=5`
   returns nothing.
5. Post-merge source-identity close-out and sidecar retirement for the DASHBOARD-01 note, as the
   product-delivery skill sets them out; the plan's `status: done` follows on a `docs/` branch.

**Fallback if the deploy does not happen before Sunday 21:00 Eastern** (also if it happens between then
and Monday 08:30: Monday's row is already written). On Monday between 08:35 and 09:25 Eastern, when
the signal monitor starts (`signal-monitor-daily`, `25 9 * * 1-5`):
`gcloud run jobs execute premarket-brief --region=us-east1 --project=adept-mountain-474619-d4
--update-env-vars="BRIEF_UPDATE=true,BRIEF_POST_TO_DISCORD=false,BRIEF_TRIGGERED_BY=operator:monday-overwrite" --wait`.
run on main at a frozen Monday 08:40: it overwrites the three canonical rows dated 2026-11-16 with rows
built on the 08:20 premarket snapshot (`premarket_status` ok), appends three history rows with
`run_kind` manual_update, and posts nothing. Without `BRIEF_POST_TO_DISCORD=false` it posts the whole
brief a second time (five embeds in four messages: the overview with Ticker Analysis, the Strat
Playbook, Earnings Today to the earnings channel, the Economic Calendar). It is a production write and
a paid run (the brief's model calls), so it is the owner's step.

## Decisions for the owner

**One decision: what the Sunday run stores once it is dated Sunday.**

- **(a) A Sunday-dated canonical row, like any other run. Recommended.** It is the four lines and
  nothing else. Verified safe: the same scheduler entry wrote Sunday-dated live rows on 2026-05-03 and
  2026-05-10, weekday-holiday rows exist (2026-07-03, 2026-09-07), the resolver already excludes
  weekend dates by name, every other reader was read (table above), and the Sunday and Monday runs
  were executed with it. Its two visible effects: the
  briefing strip serves the Sunday row (Friday's close, dated Sunday) from Sunday 21:00 to Monday
  08:30, and a Monday whose 08:30 run fails reads ok in that evening's freshness audit, as on any
  weekday.
- **(b) On a date that is not an NYSE session the run writes history and posts to Discord, and writes
  no canonical row.** The strip keeps Friday's brief over the weekend and a failed Monday run reads
  stale in the audit. It needs more code (a session check in `persist_to_cloud_sql`, tests for it) and
  it also ends the canonical row on weekday holidays, which exists today. Not verified beyond reading;
  it would not fit before Sunday with the same confidence. Choosing it changes done_when items 1, 2
  and 6 before this spec is approved.

For the owner to know; none is decided or changed here:

- Under either choice the Sunday post's ticker and playbook messages are framed on Sunday (consequence
  1). If they should describe Monday's session, that is approach 3, its own spec.
- The week-ahead earnings view sorts by date before it cuts to 25 names (`gcp/premarket_brief.py:653-676`).
  run on the production calendar for the week of 2026-11-16 (577 rows on the Monday): the message is
  titled Earnings Week Ahead with the range "Mon 11/16 to Mon 11/16" and the count 25, and lists Monday
  only. The order within the day is not production's, because the scoring queries were not simulated;
  the date-first sort and the cap do not depend on them.
- The weekly earnings refresh the Sunday brief was moved to 21:00 to follow runs in daily scope on
  winter Sundays (first row of "Other evening jobs": live for the history job, read for the calendar
  and reactions jobs), so on 2026-11-15 the week-ahead view is built on a calendar whose refresh did
  not cover the week.

## What was not verified, in those words

- The change has not run in production; every "run" above is hermetic, with the substitutions listed.
- Trigger prices were not compared with production (fixture parameters), and the Monday run's
  premarket row is simulated.
- The weekly earnings path's wall-clock on production data is not measured.
- What the frontend draws for a brief dated Sunday was not checked in solyra; only the route was read.
- Decision (b) was read, not built or run.
- The effects in "Other evening jobs" were read from code, except the earnings-history scope, which
  was read from two production logs. No job was run.
- Since 2026-06-01, 2 of 24 Mondays and 3 of 24 Tuesdays have no live row for these tickers
  (`db-query-cl4zv`); why was not looked at.
- Which commit the job's current image was built from, and whether Monday 2026-11-16's consumers run
  the code that reads `level_basis`, were not checked.
