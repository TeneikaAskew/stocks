---
feat_id: FEAT-PLAYBOOK-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-004, REQ-REL-001, REQ-OBS-001, REQ-CAP-001, REQ-CAP-003]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "tests/gcp/test_premarket_brief_late_slot.py::TestRunSlot passes: gcp.premarket_brief.RUN_SLOTS == ('early', 'late'); _resolve_run_slot() returns 'early' when BRIEF_RUN_SLOT is unset, blank or 'early' and 'late' for 'late'; any other value makes main([]) exit with code 2 before any database read, any write and any Discord call; _late_slot_clock(session_date) returns the start, the wait deadline and the write cutoff as the UTC instants of 09:20:00, 09:27:00 and 09:29:30 America/New_York (14:20:00Z, 14:27:00Z and 14:29:30Z on 2026-11-16; 13:20:00Z, 13:27:00Z and 13:29:30Z on 2026-07-13); the class fails on origin/main, where none of the names exists"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotEndToEnd::test_late_run_rewrites_the_early_rows passes: against one in-memory pair of tables whose upsert keeps a stored analysis_ts unless the frame carries the column (as Postgres does), with the exchange clock replaced through lib.eastern_time.eastern_now, a scheduled run at 2026-11-13 08:30:50 America/New_York on snapshots stamped 08:20 is followed by main([]) with BRIEF_RUN_SLOT=late and BRIEF_TRIGGERED_BY=cloud-scheduler:premarket-brief-late at 09:21:30 on snapshots stamped at or after 09:20:00 with pre_filter_status ok and a higher premarket high; afterwards every brief ticker's canonical row dated 2026-11-13 is run_kind live, carries the late build's level_basis (premarket fetched_at equal to the late stamp), the late trigger, stop and target columns, and analysis_ts equal to the frozen instant of the late write; three history rows are added with run_kind scheduled, triggered_by cloud-scheduler:premarket-brief-late and notes LATE_SLOT_APPLIED; exactly one Discord message is sent, to the main webhook, and none to the earnings webhook; one log record carries late_slot outcome=applied with the session date, the tickers, the polls and the seconds waited; the exit code is 0; it fails on origin/main, where the second run rewrites no canonical row and sends four messages"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotWait passes with the clock and the sleep injected: stamps before 09:20:00 on the first two reads and at or after it with pre_filter_status ok on the third return ready after exactly three reads and two 5 second sleeps; a stamp of the same date at 08:20:57 never passes; a stamp at or after 09:20:00 whose pre_filter_status is not ok does not pass and its reason names the status; a ticker with no row does not pass; a read that raises is logged at WARNING and the next poll still runs; when the clock reaches 09:27:00 the wait returns not ready with one reason per ticker that did not pass and makes no further read; the class fails on origin/main, where the function does not exist"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotEndToEnd::test_no_late_snapshot_leaves_the_early_levels passes for three parameters (no ticker's stamp moves; one ticker's stamp moves and two do not; every stamp moves and one carries pre_filter_status level_params_unavailable): after a scheduled 08:30 run, the late run whose clock passes 09:27:00 does not call generate_premarket_brief (so no model call and no strat_levels write), leaves every column of every canonical row as it was, adds no history row, sends exactly one Discord message that names each ticker without a usable 09:20 snapshot and gives the build time of the rows in force, and exits with code 1; it fails on origin/main, where the same run appends three history rows, posts the whole brief and exits 0"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotCutoff passes: a late run whose clock reads 09:29:30.000 America/New_York or later at its first check (09:35:00 is one parameter) does not read the stamps, does not call generate_premarket_brief, writes no canonical row, no history row and no strat_levels row, sends one 'not applied' message and exits 1; a late run whose clock reads 09:19:59 at its first check does the same with the outcome before_slot; a late run whose clock passes 09:29:30 between the end of the wait and the write leaves the canonical rows unchanged, adds history rows whose notes start with 'LATE_SLOT_NOT_APPLIED: past_cutoff', sends one 'not applied' message and exits 1; a late run whose clock reads 09:29:29 at the write check rewrites the rows; the class fails on origin/main"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotRepeat passes: after a late run has rewritten the rows, a second late run at 09:24:00 on the same stamps does not call generate_premarket_brief, sends no statement that writes (no upsert, no insert), sends no Discord message, logs late_slot outcome=already_current and exits 0, so every stored column, analysis_ts included, is unchanged; with one ticker's stamp moved to a later instant the second run rebuilds and rewrites all rows; the class fails on origin/main"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotRefusals passes: (a) a late build in which one ticker's level_basis has premarket_status other than ok, or a premarket fetched_at before 09:20:00, or a status of NO DATA, STALE_DAILY_DATA or PLAYBOOK_FAILED, rewrites no canonical row for any ticker, adds history rows whose notes start with 'LATE_SLOT_NOT_APPLIED: build_not_usable', and exits 1; (b) a canonical row whose run_kind, analysis_ts or level_basis built_at differs at the write check from what the run read after its wait rewrites no canonical row, adds history rows whose notes start with 'LATE_SLOT_NOT_APPLIED: row_changed', and exits 1; in both cases one 'not applied' message gives the build time and the snapshot time of the rows in force; the class fails on origin/main"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotRows passes: with no canonical row for the session (the early run never ran) the late run inserts live rows for every brief ticker and its message says there was no earlier row and lists the late high, low, trigger, stop and first target for each side; with a canonical row of run_kind replay for the session the late run replaces it with a live row; with a live row an operator's BRIEF_UPDATE run wrote at 08:50 on the 08:20 snapshot the late run replaces it; the class fails on origin/main"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotSessionGate::test_holiday_and_weekend_exit_clean passes for 2026-11-26 09:20:30 America/New_York (Thanksgiving) and 2026-11-14 09:20:30 (a Saturday), with the real lib.eastern_time.is_session: no query is sent, generate_premarket_brief is not called, no row is written, no Discord message is sent, one INFO record carries late_slot outcome=not_session with the date, and the exit code is 0; on 2026-11-27 (a half day) the late run proceeds past the gate; it fails on origin/main, where a scheduled run on a weekday holiday writes three live rows dated the holiday and posts the whole brief"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotPrecedence passes: BRIEF_RUN_SLOT=late with --update or with BRIEF_UPDATE=true exits with code 2 before any read or write; BRIEF_RUN_SLOT=late with BRIEF_AS_OF set runs the replay path as on origin/main (no session check, no wait, no cutoff, no Discord message, history run_kind replay_refresh, canonical run_kind replay, the same trigger, stop and target columns as the same replay without the slot) and logs once that the slot has no effect on a replay; an unknown slot value exits 2 with BRIEF_AS_OF set too; the class fails on origin/main"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLevelsUpdatedNote passes on the pure formatter format_levels_updated_note: for each ticker it shows the earlier and the late premarket high and low with the time each snapshot was fetched (HH:MM America/New_York); per side it lists the trigger (name and price), the stop and the first target only where the name or the price in cents changed, and one 'unchanged' phrase where neither side changed; 759.7370 against 759.7401 is unchanged and 759.737 against 762.693 is a change; a missing price renders as N/A through _fmt_price and never as 0, and a missing price that becomes a price is a change; a ticker with no earlier row is shown in full and says so; for the 2026-11-13 example in the spec the SPY block names the high 759.74 to 762.69, the calls trigger PMK_H 759.74 to 762.69 and the first target 762.63 to 763.04 and no puts change; a 12 ticker payload stays within Discord's 4096 character description and 6000 character message limits by dropping whole ticker blocks and saying how many were dropped; the class fails on origin/main, where the function does not exist"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestLateSlotFailures passes: when every model call fails, the late canonical rows hold NULL in llm_overview, llm_orb_explanation, llm_analysis and llm_playbook (never the early text), the levels are rewritten, the message is sent and the exit code is 0; when the Discord post raises, the rewritten rows stay, the history rows carry LATE_SLOT_APPLIED and the exit code is 1; when the history insert raises after the canonical statement returned, the rewritten rows stay, the message says the history row was not recorded and the exit code is 1; when generate_premarket_brief raises, no canonical row changes, one 'run failed' message naming the exception type is attempted and the process exits nonzero; the class fails on origin/main"
  - "tests/integration/test_premarket_brief_late_slot_pg.py::test_late_overwrite_on_postgres passes against the real-SQL Postgres loaded with gcp/schema.sql: after persist_to_cloud_sql writes an early live row and puts_reanchor_open and outcome_resolved_at are set on it by hand, the late write moves analysis_ts to the instant it was given, replaces level_basis and the trigger, stop and target columns, keeps run_kind live, leaves puts_reanchor_open and outcome_resolved_at untouched, and rewrites all tickers in one statement; a second early-slot scheduled write still changes no canonical column; it fails on origin/main, where persist_to_cloud_sql has no late slot argument"
  - "tests/gcp/test_premarket_brief_late_slot.py::TestEarlySlotUnchanged passes on origin/main and on the branch for its unset case and on the branch for its 'early' case: with BRIEF_RUN_SLOT unset and with BRIEF_RUN_SLOT=early, a scheduled 08:30 run followed by a second scheduled run writes the same canonical rows once, skips the second canonical write with the 'row already exists' warning, appends history both times and sends the same messages in both cases; python3 -m pytest over every file under tests/ that names premarket_brief passes"
  - "tests/gcp/test_fetch_premarket_refresh.py::test_compute_logs_the_newest_premarket_bar passes: for a vendor reply holding one-minute bars from 04:00 through 09:19 Eastern, compute_premarket_for_ticker logs one INFO record naming the ticker, the premarket bar count, the newest premarket bar as 09:19 and the fetch time in America/New_York; for a reply that also holds regular-session bars the newest premarket bar is 09:29, not the last bar of the day; a reply with no premarket bar logs no such record; it fails on origin/main, where no record names a bar time"
  - "The only files changed under gcp/, lib/, platform/ and scripts/ are gcp/premarket_brief.py and gcp/fetchers/fetch_premarket_refresh.py; gcp/deploy.sh, gcp/schema.sql and gcp/database.py are unchanged; git diff origin/main -- tests/fixtures/timezone_boundary_baseline.json is empty, neither file gains a tz-ok comment, and python3 -m pytest tests/meta/test_timezone_boundaries.py passes"
  - "docs/plans/MORNING_RUN_PROTECTION_PLAN.md gains a section that names the late slot as the one scheduled path that replaces a live canonical row, with its four conditions (an NYSE session, every brief ticker's snapshot fetched at or after 09:20:00 America/New_York with its prints filtered, the write check before 09:29:30, the rows unchanged since the run read them), and the docstrings of persist_to_cloud_sql and of the module say the same"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-PLAYBOOK-001, DASHBOARD-01) note row carries that source_identity_sha256"
  - "The FEAT-PLAYBOOK-001 catalog record (Status, Last reviewed) and the PR traceability entry are updated, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing new over origin/main, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
  - "tests/api/test_movement_statement_late_slot.py::test_the_ladder_follows_the_late_write passes: with MOVEMENT_STATEMENT_ENABLED on, the exchange clock frozen, and one in-memory premarket_analysis table that takes the brief's canonical writes (gcp.database.upsert_dataframe and the late slot's rewrite) and answers the route's read of the live level_basis (lib.strat_levels.read_live_level_basis through the route's own query function), a scheduled early run at 08:30 America/New_York is followed by GET /api/movement-statement for SPY through TestClient, whose levels block carries the early row's trigger as rung one and the early row's side lists as its ladder; a late-slot run at 09:21:30 on a premarket snapshot stamped 09:20:40 whose high is above the early snapshot's then applies, and the same request returns the late row's trigger and side lists and no longer returns the early trigger; ::test_a_late_run_that_does_not_apply_leaves_the_ladder passes: the same sequence with the late run started at 09:35:00 leaves the response equal, field for field, to the one before it. The first test fails on origin/main, where BRIEF_RUN_SLOT is not read, the 09:21:30 run rewrites no canonical row and the route still answers with the early trigger"
status: draft
supersedes: null
---

# The brief's late slot: a second run at 09:20 ET rebuilds the day's levels from the 09:20 premarket snapshot

## Authority and status

Draft, written 2026-11-14 for the owner's review. Nothing here is approved and no code is written
under it. The section-by-section approval conversation of the product-delivery skill is replaced, for
this draft, by the list in "Decisions for the owner".

This spec is the prerequisite named by
`docs/superpowers/specs/2026-11-14-feat-deploy-001-premarket-late-run.md` (PR #1929, approved, head `dd09c577`,
not yet on main), section "Prerequisite: the brief's late slot". That spec adds the two 09:20 scheduler
entries. This one adds the behaviour that makes the second run useful. The owner's seven decisions on
#1929 (2026-11-14, all as recommended) bind this spec and are restated in "Decisions for the owner".

Precondition: the fix of `docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-market-date.md`
is on main (its code PR is being opened on `fix/feat-playbook-001-brief-market-date`). The late slot
takes its date from `lib.eastern_time.market_today()`, which that fix imports into the brief. The
implementation branch of this spec starts from main after that fix.

Every statement is marked by its source: **read** (code on `origin/main` at `161fa992`), **live** (a
read-only `gcloud` or `scripts/db_query_cr.sh` call without `--commit` on 2026-11-14, execution
named), **run** (executed on 2026-11-14, see "How the runs were made"), **given** (taken from #1929,
not re-run), or **not checked**.

## Scope

In: `gcp/premarket_brief.py` (a named run slot, the wait on the refresh, one guarded overwrite of the
day's canonical rows, the short Discord note) and one log record in
`gcp/fetchers/fetch_premarket_refresh.py` (the newest premarket bar per ticker). Tickers: the brief's
own list, which is SPY, QQQ and IWM (live, `db-query-qh5ms`: the scheduled brief wrote exactly those
three on each of 2026-11-09 to 2026-11-13).

Out: the schedule (FEAT-DEPLOY-001, #1929), the insight pipeline, the signal monitor, the refresh's
computation, any schema change, and the replay cut of decision 7 (its own spec, see "Implementation
plan: size").

## Capability

Catalog row, `docs/product/02-FEATURE-CATALOG.md` line 22: "FEAT-PLAYBOOK-001 | Premarket / playbook |
Structured daily setups | `/playbook` | `/api/playbook` | `premarket_analysis`, `playbook_cards` |
Production but needs remediation | P0". Its record (line 205) names `gcp/premarket_brief.py` as Code
and MODEL-BRIEF-001 and MODEL-LEVEL-001 as Models.

- Requirements: REQ-PLAYBOOK-001 (a plan shows its data time and marks what is unavailable),
  REQ-DATA-001 (a read that cannot see fresh upstream data fails explicitly), REQ-DATA-004 (sessions,
  holidays and DST through one calendar), REQ-REL-001 (live and replay stay in step), REQ-OBS-001 (a
  run reports its identity, counts and terminal status), REQ-CAP-001 and REQ-CAP-003 (capacity and
  cost of a scheduled run).
- Issues: none of the 19 open issues listed for this capability in
  `docs/product/12-PR-ISSUE-TRACEABILITY.md` (line 631) concerns the brief's premarket time. GitHub
  itself was not searched.
- Canvases: none (`docs/product/canvases.yml` has no entry whose `feat_ids` holds FEAT-PLAYBOOK-001).
- The one log record in `gcp/fetchers/fetch_premarket_refresh.py` rides this spec by the owner's
  decision 6. The gate fixes a capability by path only for process and deploy files, so the file
  takes its FEAT from the branch name (read, as the market-date spec records).

## Decisions for the owner

Decided on 2026-11-14 for #1929, and binding here:

1. The insight pipeline and its Discord push stay as they are.
2. The late brief posts a short "levels updated" note, every session.
3. The signal monitor is left as it is.
4. Paid model calls in the late brief: yes. Up to 8 Gemini Flash-Lite calls a late run, about
   0.012 USD a run, about 0.36 USD a month.
5. This spec first, then the schedule.
6. The refresh logs the newest bar's time per ticker. No schema change, no label on the brief.
7. A `BRIEF_AS_OF` replay cuts premarket at the slot's clock, here if it fits, otherwise its own spec.

New decisions this design needs. Each has a recommendation, written into the design below.

**A. Decision 7: in this spec or its own? Recommended: its own spec.** This spec's plan is about 14
tasks. The replay cut adds about 7 (see "Implementation plan: size"), which passes the 15 task limit
of the product-delivery skill. It is also a different problem: a replay would have to rebuild the
snapshot from stored one-minute bars, and the stored bars are not what the live run read. On
2026-11-13 the live 08:20 read gave SPY a high of 759.737 while the stored bars through 08:19 give
759.75, and QQQ's raw stored bars reach 712.2 before 09:20 where the filtered snapshot is 693.13
(live, `db-query-h9rwv`). So the cut needs its own definition of what a faithful replay is. Choosing
"in this spec" makes this one plan of about 20 tasks, which the skill says to split.

**B. All tickers or none. Recommended: the late run rewrites every brief ticker's row or none.**
#1929 says the late brief "proceeds only when every one" of its tickers has a 09:20 snapshot. One
rule covers the wait, the build check and the write, and the write is one statement. The cost: one
ticker without a usable snapshot holds back the other two, and a brief ticker that can never be built
would hold the late run back every day. Today's three were all built with a usable snapshot on each
of 2026-11-11 to 2026-11-13 (live, `db-query-h9rwv`).
Choosing "per ticker" changes `done_when` items 4 and 7, the note (three states per ticker) and the
timeline row of #1929 that says the late brief "writes nothing" at the deadline.

**C. Which rows the late run may replace. Recommended: any row of the session that was built on an
older snapshot.** That is the row the early scheduled run wrote, a row an operator's `BRIEF_UPDATE`
run wrote before 09:20, and a replay row (which live readers do not read). The canonical table has no
column that says which run wrote a row, and `analysis_ts` does not move when a row is overwritten
(run, live), so "written by the early scheduled run" cannot be read from the row. What can be read is
the snapshot the row was built on, `level_basis.premarket.fetched_at`. Choosing "only rows of the
early scheduled run" needs a provenance column on `premarket_analysis` (a schema apply) or a lookup
in history that is not a key.

**D. `analysis_ts` moves on the late write. Recommended: yes.** Today no overwrite moves it (run on
Postgres; live: the 2026-11-10 rows were rebuilt at 17:30 and still read 08:31:16). If the late write
left it, the row would say 08:30 beside levels built at 09:22, and no close-out query could tell from
the row when the levels in force were written. Choosing "no" removes one column from the late write
and the close-out then reads `level_basis.built_at` only.

**E. A late run that could not tell the owner exits nonzero. Recommended: yes.** If the note cannot
be posted, the levels are rewritten and the only other channel is the job-failure lane, so the run
exits 1 with the write kept. The early run keeps today's behaviour (a failed post is logged and the
run exits 0). Choosing "exit 0" means a morning with changed levels and no message looks like a
morning with no late run.

**F. The wait deadline stays 09:27:00. Recommended: yes, as approved in #1929.** The expected run is
about 140 s and the task timeout (1800 s) is about 13 times that. On the path where the refresh lands
just before the deadline the run is bounded at about 496 s. The timeout is 3.6 times that, under
the 4 times of CLAUDE.md rule 0.5. That path needs the refresh to take more than five times its
slowest run of the last ten (70 s, live). Choosing 09:26:00 bounds the run at about 436 s (4.1 times)
and changes one time in #1929's timeline. Raising the timeout is the schedule spec's file, not this
one's.

**G. The late slot refuses `BRIEF_UPDATE`. Recommended: yes.** `BRIEF_RUN_SLOT=late` together with
`--update` or `BRIEF_UPDATE=true` exits 2. The operator's overwrite and the late slot's overwrite have
different rules, and a run that claimed both would have neither's clearly. Choosing "allow" needs a
rule for which gates an operator's late run skips.

## Problem

The 08:30 brief builds its levels on the premarket snapshot fetched at 08:20. #1929 gives the size of
what that misses (the range moves after 08:20 in about 55% of sessions, given) and adds a refresh and
a brief at 09:20. A second brief run does not deliver the change with the code on main:

1. **A second scheduled run never reaches the row every reader uses.** `persist_to_cloud_sql`
   inserts only where no live row exists for the date and ticker (`gcp/premarket_brief.py:3216-3250`,
   read).
   - run (Postgres 16, the real function): after an early scheduled write, a second scheduled write
     with a higher trigger returned 0, left `calls_trigger_price` at 759.737 and added a history row.
   - run (end to end, frozen clock): a scheduled run at 09:21:30 after the 08:30:50 run, on a snapshot
     stamped 09:20, wrote no canonical row, appended three history rows, and logged "Skipped
     premarket_analysis write for 3 ticker(s) (row already exists ...)".
   - live, `db-query-h9rwv`: on 2026-11-13 a run at 10:32:02 ET added history rows and the canonical
     rows still read 08:30:54.
2. **It posts the whole brief again.** run: the second run sent four messages holding five embeds
   (the overview with Ticker Analysis, the Strat Playbook, Earnings Today, the Economic Calendar).
3. **The operator's overwrite is not a late slot.** `BRIEF_UPDATE=true` overwrites whatever is there
   (`:3210-3214`, read).
   - run: at a frozen 09:31:00, after the open, it rewrote all three canonical rows. Nothing stops a
     write after the signal monitor has loaded its levels.
   - run: it does not wait for the refresh. With the early snapshot still in place it rebuilds from
     the 08:20 values and stores them as the newest write.
   - run: its history rows are `manual_update`, and it sends the same four messages.
   - run (Postgres 16) and live (`db-query-h9rwv`): the overwrite leaves `analysis_ts` at the first
     write. `gcp.database.upsert_dataframe` updates only the columns in the frame (`:484`, read), and
     the brief's rows carry no `analysis_ts`.
4. **On a weekday holiday a 09:20 run writes a row.** run: at a frozen 2026-09-07 09:20:30 EDT (Labor
   Day) a scheduled run wrote three live rows dated the holiday with `premarket_unavailable` and
   posted the whole brief. `lib.eastern_time.is_session('2026-09-07')` is False (run).
5. **The 09:20 snapshot does not outlive the day in the table it is read from.** live,
   `db-query-h9rwv`: `market_data_daily.pre_fetched_at` for 2026-11-10 to 2026-11-13 reads 23:00 to
   23:01 ET, and the premarket high and low there are the nightly job's full-window values (SPY
   2026-11-13: 762.693 where the 08:30 brief recorded 759.737). After 23:00 the only record of what a
   morning run read is the brief's own `level_basis`.

What the refresh gives the late run to wait on (read, unless marked):

- Each row it writes carries `pre_fetched_at`, the instant the ticker's bars were fetched
  (`gcp/fetchers/fetch_premarket_refresh.py:204`), and `pre_filter_status`. The early stamps are
  08:20:33 to 08:20:57 (live, the canonical rows' `level_basis` for 2026-11-11 to 2026-11-13).
- All rows of a run are written in one transaction (`:311-314`). A ticker with no bars, no premarket
  bars or a failed prior-session lookup is left out and keeps its earlier row (`:205-214`, `:241-244`).
- On conflict the stamp, the high, the low and the VWAP take the new value when it is not null; the
  filter status and counts are always overwritten (`:342-362`; run: the statement text).
- When the level parameters cannot be read, the refresh writes every snapshot unfiltered with
  `pre_filter_status` `level_params_unavailable` and exits 1 (`:413-415`, `:428-429`). The job has one
  retry (live, `gcloud run jobs describe fetch-premarket-refresh`: `maxRetries` 1), so a second
  attempt can replace those rows a minute later. The level builder refuses a snapshot whose status is
  not `ok` (`lib/strat_levels.py:1925-1942`).

Timing (live, `gcloud run jobs executions list`, the last ten executions of each job): the refresh
completes 30 to 70 s after its trigger. The brief's container starts 2 to 53 s after its trigger and
the run takes 44 to 79 s. The signal monitor sleeps 30 s at a time until 09:30:00
(`gcp/signal_monitor.py:322-336`, `:2557`; `lib/config.py:212`), so its first level read is between
09:30:00 and about 09:30:30 (given: 09:30:18 on 2026-11-13), and it keeps what it read for the day
(`gcp/signal_monitor.py:1252-1253`).

## Non-goals

- The scheduler entries, the job's flags, its image, memory, timeout or retries. `gcp/deploy.sh` is
  not changed.
- The early run. With `BRIEF_RUN_SLOT` unset or `early` the brief does what it does on main,
  including its Discord messages, its exit codes and the rule that a scheduled run does not overwrite
  a live row.
- `--update` and `BRIEF_UPDATE`: unchanged, including that they do not move `analysis_ts`, do not
  wait and have no cutoff.
- Replays. A `BRIEF_AS_OF` run does what it does on main whatever the slot says. The cut of
  premarket at the slot's clock is decision A.
- The refresh's computation, universe, date and retries. The only change there is one log record.
- The insight pipeline, its Discord push, the signal monitor and the 21:15 resolver.
- A schema change. No column is added.
- The row a weekday holiday gets from the early run. The late slot does not write on a holiday; the
  early run still does, as on main.

## Approaches considered

1. **`BRIEF_UPDATE=true` in the 09:20 scheduler body, no code.** Refused in #1929 and by the runs in
   "Problem" item 3: no wait, no cutoff, the wrong run kind, the whole brief posted twice.
2. **Let any scheduled run overwrite when its snapshot is newer.** No environment variable, the data
   decides. It gives the overwrite to the 08:30 run and to every run labelled scheduled, has nowhere
   to put the cutoff or the short note, and weakens the protection of the morning row for all runs.
   Rejected.
3. **A second module or job for the late brief.** It would copy the build and the persist code, or
   import them and still need every change below. Rejected (CLAUDE.md rule 1).
4. **The guard inside the SQL statement** (a conditional upsert helper in `gcp/database.py`). The
   strictest form of the cutoff and of "the row has not changed". It adds a write helper to a shared
   module for one caller, and a commit can still land after a check that passed. Not chosen for the
   first delivery; the bound it would tighten is stated in "Risks".
5. **A named slot in the existing job. Chosen.** `BRIEF_RUN_SLOT=late` turns on four gates, one
   guarded overwrite and the short note. Everything else is the code that runs at 08:30.

## Design

All times are America/New_York. Every clock read goes through `lib.eastern_time`: the date is
`market_today()`, the slot's instants are `eastern_bounds_utc(session_date, ...)`, "now" is
`eastern_now()` looked up at call time (so one replacement freezes the run in tests), a stored instant
is shown with `as_eastern_time`, and the session test is `is_session`. No zone is built in the file,
no host-clock date is read and no `tz_localize(None)` is added (CLAUDE.md 3.9;
`tests/meta/test_timezone_boundaries.py`).

### The slot

```python
RUN_SLOTS = ('early', 'late')
LATE_SLOT_START = time(9, 20)            # a usable snapshot is stamped at or after this
LATE_SLOT_WAIT_DEADLINE = time(9, 27)    # the wait ends here
LATE_SLOT_WRITE_CUTOFF = time(9, 29, 30) # no canonical statement is sent at or after this
LATE_SLOT_POLL_SECONDS = 5
```

`_resolve_run_slot()` reads `BRIEF_RUN_SLOT`: unset, blank or `early` is `early`; `late` is `late`;
anything else exits 2. It runs after the `--post-existing` branch of `main()` and before any read.
`_late_slot_clock(session_date)` returns the three instants in UTC (run: 14:20:00Z, 14:27:00Z and
14:29:30Z on 2026-11-16; 13:20:00Z, 13:27:00Z and 13:29:30Z on 2026-07-13).

Run kind and trigger are not new. With the body #1929 sends
(`BRIEF_TRIGGERED_BY=cloud-scheduler:premarket-brief-late`, `BRIEF_RUN_SLOT=late`),
`_resolve_run_kind_and_update` returns `scheduled` (`:2989-2991`, read) and `triggered_by` is the
variable's value (`:3409-3412`). A late run started by hand without that variable is recorded as
`manual_replay` by the same function; the slot's gates and its overwrite apply to it all the same,
because the gates are the protection, not the caller.

Combinations:

| Environment | What runs |
|---|---|
| `BRIEF_RUN_SLOT` unset or `early` | Today's run, unchanged. |
| `late`, no `BRIEF_AS_OF`, no update | The late flow below. |
| `late` with `--update` or `BRIEF_UPDATE=true` | Exit 2, nothing read or written (decision G). |
| `late` with `BRIEF_AS_OF` | Today's replay, unchanged. One log line says the slot has no effect on a replay. |
| `late` with `BRIEF_POST_TO_DISCORD=false` or `--no-discord` | The late flow; the note is printed, not posted. |
| `late` with `BRIEF_LLM_DISABLE=1` | The late flow with no model call; the four text columns are NULL in the late rows. |

### The late flow

1. **Session.** `session_date = market_today()`. If `is_session(session_date)` is False: one INFO
   record (`late_slot outcome=not_session`), exit 0. No query, no row, no post. A half day is a session and opens at 09:30 (run:
   2026-11-27 is a session, open 09:30, close 13:00).
2. **The slot's window.** If `eastern_now()` is before the slot's start the outcome is
   `before_slot`; at or after the cutoff it is `past_cutoff`. Either way the run does not wait and
   does not build: no canonical write, no history row, no `strat_levels` row, no model call. It reads
   the rows in force, posts the one "not applied" line (unless posting is turned off) and exits 1.
   This is what a late run started at 09:35 does, which #1929's smoke step relies on; its execution
   shows as failed by design. #1929 describes a run started before 09:20 as waiting; here it refuses
   at once, so the wait is never longer than seven minutes.
3. **Wait for the refresh.** Every 5 s, one keyed read through `query_to_dataframe_strict` with a 5 s
   statement timeout:

   ```sql
   SELECT ticker, pre_fetched_at, pre_filter_status
   FROM market_data_daily
   WHERE date = :session_date AND ticker IN (<the brief tickers>)
   ```

   A ticker passes when its row exists, `pre_fetched_at` is at or after the slot's start (compared
   as instants) and `pre_filter_status` is `ok`. The wait ends when every brief ticker passes, or at
   the deadline; a read that began before the deadline counts. A read that raises is logged at
   WARNING and the next poll runs. At the deadline the
   outcome is `snapshot_not_ready`, with one reason per ticker (`stamp 08:20:57`, `no row`,
   `status level_params_unavailable`, `read failed: <type>`): no build, the "not applied" line, exit
   1. This is the refusal CLAUDE.md 3.7 asks for: the run never rebuilds from the early snapshot and
   calls the result late.

   The filter status is part of the test because an unfiltered snapshot is one the builder refuses,
   and because the refresh's retry can replace it a minute later (see "Problem"). #1929 states the
   test as the stamp alone; this is the same test made exact.
4. **Rows in force.** One keyed read of `premarket_analysis` for the session and the brief tickers
   (run kind, `analysis_ts`, `level_basis`, and the trigger name and price, stop and first target of
   each side). A ticker is **current** when its row is live and its
   `level_basis.premarket.fetched_at` is at or after the stamp read in step 3 (the basis keeps the
   stamp to the microsecond: live, `db-query-wnszb`). If every ticker is
   current: outcome `already_current`, one INFO line, exit 0. Nothing is built, written or posted.
   This is what a duplicate trigger or a rerun after a success does.
5. **Build.** `generate_premarket_brief()` as it is: the daily frames, the session's own premarket
   row, the levels, `strat_levels`, and the model text (decision 4). No change inside it.
6. **Check the build.** Every brief ticker must have a `level_basis` whose `premarket_status` is `ok`
   and whose premarket `fetched_at` is at or after the slot's start, and a status that is not
   `NO DATA`, `STALE_DAILY_DATA` or `PLAYBOOK_FAILED`. The build resolves the brief's ticker list
   itself, so its tickers must also be the set the wait checked. Otherwise the outcome is
   `build_not_usable`, naming the ticker and why.
7. **Write** (`persist_to_cloud_sql(..., late_slot=...)`):
   - If step 6 refused: history rows only, notes `LATE_SLOT_NOT_APPLIED: build_not_usable ...`.
   - Read the rows in force again. If any ticker's run kind, `analysis_ts` or `level_basis.built_at`
     differs from step 4: outcome `row_changed`, history rows only.
   - If `eastern_now()` is at or after the cutoff: outcome `past_cutoff`, history rows only.
   - Otherwise one `upsert_dataframe` call writes every brief ticker's canonical row: the columns the
     early run writes, `run_kind` live, and `analysis_ts` set to the instant of the check (decision
     D). Three rows are one statement in one transaction (`gcp/database.py:484-523`, read; run on
     Postgres 16: three rows, one INSERT, one commit), so all tickers change or none does (decision
     B). A ticker with no row is inserted;
     a replay row becomes live. Then the history rows are inserted with notes `LATE_SLOT_APPLIED`.
   - The order is canonical first, history second, so a late history row's notes say what happened
     to the canonical row. If the history insert fails after the canonical statement returned, the
     rewritten rows stay, the error is logged, the note says the history row was not recorded and the
     run exits 1. The late build is still in the job's log, which prints the whole brief (`:3464`).
8. **Note.** One message to the main webhook: "levels updated" when the rows were rewritten, a "not
   applied" line otherwise. If the post raises, the write stays and the run exits 1 (decision E).
9. **One log record** per late run (REQ-OBS-001): `late_slot outcome=<...> session=<date>
   tickers=<...> polls=<n> waited_s=<n> stamps=<per ticker> applied=<bool>`.

Exit codes: 0 for `applied` (with the note posted, or posting turned off), for a day that is not a
session and for `already_current`; 1 for every other outcome; 2 for a bad slot value or decision G.
An exception in the late flow is not swallowed: the run tries once to post "Late brief run failed
(<exception type>). Check the brief row before the open." and re-raises.

What a late write does not touch (run on Postgres 16): the columns the frame does not carry. Those
are the signal monitor's put re-anchor columns, written at the first regular-session bar, and the
resolver's outcome columns, written at 21:15. Before 09:29:30 on the session both are still NULL.

`strat_levels` gets a new set of rows from every build, applied or not (`:1456-1495`, read). No job
reads that table (given, #1929).

### The note

A pure function, `format_levels_updated_note(session_date, earlier, brief, result)`, returns the
Discord payload. `earlier` is what step 4 read. The times it prints are the rows' own: when the
earlier row was built (`level_basis.built_at`, which every rebuild moves; `analysis_ts` for a row
with no basis) and both snapshots' `fetched_at`, never the literals 08:20 and 09:20.

- Per ticker, always: the premarket high and low of the earlier row and of the late build, and when
  each snapshot was fetched.
- Per side, only what changed: the trigger (name and price), the stop, the first target. A change is
  a different name or a different price in cents (`lib.strat_levels.price_cents`). If nothing changed
  on either side: one phrase saying the trigger, stop and first target are unchanged.
- A missing price is shown as N/A (`_fmt_price`), never as 0. No earlier row: the ticker says so and
  shows the late values in full.
- Limits: Discord's 4096 characters a description and 6000 a message. Whole ticker blocks are dropped
  from the end and counted, never cut inside a block.
- "Not applied": one line with the outcome and its reason, then, per ticker, when the row in force
  was built and on which snapshot, or that no row exists for the session.

Example, from the hermetic run of 2026-11-13 (premarket values as production recorded them, trigger
prices from the test fixture's parameters, so not production's):

```
Levels updated: Fri Nov 13, 09:21 ET
Compared with the rows built 08:30:50.
SPY  premarket high 759.74 to 762.69, low 755.73 unchanged (fetched 08:20, 09:20)
     calls: trigger PMK_H 759.74 to PMK_H 762.69; first target 762.63 to 763.04
QQQ  premarket high 691.94 to 693.13, low 685.00 to 684.94 (fetched 08:20, 09:20)
     calls: trigger PMK_H 691.94 to PMK_H 693.13
IWM  premarket high 279.30 to 280.65, low 277.86 unchanged (fetched 08:20, 09:20)
     calls: stop 279.33 to 280.65
```

The wording is the plan's; the content rules above are the contract. The earnings and calendar
messages are not sent by the late run.

No note by 09:30 means the late run failed before it could post, or did not start. The job-failure
lane carries those.

### The refresh's log record (decision 6)

In `compute_premarket_for_ticker`, after the snapshot is computed and it has at least one premarket
bar, one INFO record: the ticker, the premarket bar count, the newest premarket bar's time (the
vendor's own Eastern wall time, `HH:MM`) and the fetch time shown through `as_eastern_time`. The
newest premarket bar is the last bar at or after 04:00 and before 09:30 (`lib/indicators.py:519-520`),
not the last bar of the reply. Nothing is stored. The module docstring's "runs at 8:20 AM ET" gains
the 09:20 run.

### How the runs were made

- **Postgres 16.** A scratch database on the session's local Postgres 16 with `gcp/schema.sql`
  applied (three statements failed, all for the absent `vector` extension). The real
  `gcp.premarket_brief.persist_to_cloud_sql` and `gcp.database.upsert_dataframe` ran against it
  through the `DB_HOST` path: an early scheduled write, a second scheduled write, an `allow_update`
  write, an upsert whose frame carries `analysis_ts`, a `BRIEF_AS_OF` write over the live row, and a
  scheduled write over that replay row.
- **End to end, frozen clock.** `gcp.premarket_brief.main([])` from a scratch script outside the
  repository (not committed), on `origin/main`. Replaced: the clock (frozen, process zone UTC as in
  the container), sockets (refused), Cloud SQL reads (the rows the market-date spec read from
  production, `db-query-qnt5l`, cut to the frozen instant), Cloud SQL writes (in-memory tables that
  keep `analysis_ts` as Postgres does), the level parameters (the fixture of
  `tests/lib/level_params_fixtures.py`), the RSI calibration row (none), the gamma probe
  (unavailable), model text (off), `strat_levels` writes (captured) and the Discord webhook
  (captured). The session's premarket row is simulated: its high, low and stamp are the values
  production recorded for 2026-11-13 (`db-query-h9rwv`), early and nightly, with the nightly values
  given a 09:20 stamp. Trigger prices are the fixture's, not production's.
- The late slot itself was not run: it does not exist. Its behaviour is the `done_when` tests'.

## What bad input gets

| Input | What the late run does | Exit |
|---|---|---|
| No refresh write by 09:27:00 (every stamp still 08:20) | No build. No canonical or history write. One "not applied" line naming each ticker and its stamp, and when the rows in force were built. | 1 |
| The refresh wrote for some tickers only | The same: no ticker is rewritten (decision B). The line names the tickers without a 09:20 snapshot. | 1 |
| The refresh wrote unfiltered snapshots (`pre_filter_status` not `ok`) | The wait keeps polling: the refresh's retry may replace them. At 09:27:00, as the first row, with the status as the reason. | 1 |
| A stamp read fails | Logged, polled again. If no read succeeds by 09:27:00, as the first row with `read failed`. | 1 |
| The early row is missing for one or all tickers | The late rows are inserted. The note says there was no earlier row and shows the late values in full. | 0 |
| The row for the session is a replay row | Replaced by the live late row. | 0 |
| The rows are already built on this snapshot (a duplicate trigger, a rerun) | No build, no write, no post. One log line. | 0 |
| A row changed between the run's read and its write | No canonical write. History rows with `LATE_SLOT_NOT_APPLIED: row_changed`. The line gives the build time and snapshot of the rows now in force. | 1 |
| The late build did not use the late snapshot, or a ticker failed to build | No canonical write for any ticker. History rows with `LATE_SLOT_NOT_APPLIED: build_not_usable`. The line names the ticker. | 1 |
| A model call fails or times out (12 s each) | That text is NULL in the late rows, never the early text. Levels rewritten, note sent. | 0 |
| The Discord post fails | The rewritten rows stay. The error is logged. | 1 |
| The history insert fails after the canonical write | The rewritten rows stay. The note says the history row was not recorded. | 1 |
| The run starts at or after 09:29:30 (09:35, say), or before 09:20:00 | No wait, no build. No canonical write, no history row, no `strat_levels` row, no model call. One "not applied" line saying when the rows in force were built. | 1 |
| The build ends at or after 09:29:30 | No canonical write. History rows with `LATE_SLOT_NOT_APPLIED: past_cutoff`. The same line. | 1 |
| A holiday or a weekend | One log record. Nothing read, written or posted. | 0 |
| The NYSE calendar cannot be read | The error is raised (`lib.eastern_time` has no fallback). Nothing written. The "run failed" line is attempted. | nonzero |
| `BRIEF_RUN_SLOT` is not `early` or `late` | Nothing read, written or posted. | 2 |
| `late` with `BRIEF_UPDATE` or `--update` | Nothing read, written or posted. | 2 |
| `late` with `BRIEF_AS_OF` | Today's replay. The slot has no effect. | as today |
| The level parameters cannot be read | No row for any ticker, as on main. One "run failed" line is attempted. | 1 |

## Consumers

Who reads the canonical row, and what a rewrite before 09:29:30 means for each (read, unless marked).

| Reader | How it reads | With the late row |
|---|---|---|
| Signal monitor, levels and brief bias | The session's live row, once, at its first poll at or after 09:30:00 (`gcp/signal_monitor.py:976`, `:1252-1253`; `lib/strategies/brief_bias.py:86`) | Reads the late row. The cutoff keeps the row from changing after that read, so a replay of the day reads the row the live monitor read. On a day the late run does not apply, it reads the early row, as now. |
| Signal monitor, put re-anchor | Writes `puts_reanchor_*` on the row at the first regular-session bar | Unaffected: the late write is earlier and does not carry those columns (run). |
| Insight pipeline | 08:45, the live `level_basis` plus the newest snapshot (`lib/agents/summarizers.py:597-603`) | Already ran. Its reports and the 09:15 digest describe the 08:20 premarket (decision 1). |
| 21:15 resolver | The session's row, no run-kind filter (`gcp/premarket_playbook_resolver.py:425-436`) | Grades the late levels from the first applied late run on. History keeps both sets. |
| Briefing strip, `GET /api/dashboard/brief/{ticker}` | The newest live row; RSI, streaks, signal status, Strat and TF bias (`platform/api/routers/dashboard.py:104-136`) | Those fields come from daily bars and are the same in both builds (run: equal for all three tickers). The route returns no level. |
| Movement statement, `GET /api/movement-statement` | The session's live `level_basis` (`platform/api/routers/dashboard.py:455-461`) | Its ladder is the late levels from the next request on. Its reach rates count resolved rows, so from the first late run they include rows graded on late levels. |
| Freshness audit | The newest live date per ticker (`scripts/audit_data_freshness.py:206-216`) | Unchanged: the date does not move. |
| Discord `/replay`, brief validation | The requested date (`gcp/discord_interactions/main.py:351-357`; `scripts/validation/validate_brief_accuracy.py:343-355`, which orders by `analysis_ts`) | A late-rewritten row shows the late write time. |
| The four model text columns | No reader outside the brief (read: no other module names them) | Audit trail only. |

`premarket_analysis_history` has no reader on a request path. It holds the early row in full (the 54
columns the two tables share besides the keys and the run kind, run on Postgres 16) beside the late
one.

## Site traceability

`site_source_notes` declares DASHBOARD-01, the first Chain row of
`docs/product/03-SITE-TRACEABILITY.md` that names what changes: `premarket_analysis` written by
`premarket-brief`, and `market_data_daily` written by `fetch-premarket-refresh` (line 331). `gcp/`
and `tests/` are in that document's watched scope (`docs/DOC_REGISTRY.md` line 196), so the
implementation PR updates the (FEAT-PLAYBOOK-001, DASHBOARD-01) note row that the market-date fix
adds. #1929 declares the same element for the schedule. DASHBOARD-21 (the movement statement) reads
the same row and is named in the note's prose, not declared: one note carries the identity.

No route, response schema or frontend file changes. For a given stored row every API answer is what
it is on main; what changes is when the row changes. That is still a change a user can see: from the
next request after the late write, `GET /api/movement-statement` returns a different ladder. So the
implementation PR carries an API test of the changed response, as AGENTS.md asks of a stocks change
("Browser proof"): the last `done_when` item runs the early write, the late write and the route
against one in-memory table and reads the ladder through `TestClient` before and after, and its
second test holds the answer still when the late run does not apply. The existing tests of the
ladder's source (`tests/api/test_movement_statement_router.py`) do not exercise a late write and are
not that proof. The runs against the deployed site, before the merge and after the first late run,
stay the owner's close-out steps with screenshots (Close-out, step 4).

## Capacity

One more run of an existing job on each session, with a wait in front of the build.

- **Volume.** Three tickers. Three canonical rows rewritten and three history rows appended, about
  5.7 KB a row of which the `level_basis` is about 2.8 KB (live, `db-query-f5vhr`, the nine rows of
  2026-11-11 to 2026-11-13). One `strat_levels` set per ticker, as the early run writes.
- **Velocity.** The early run's statements, counted in the end-to-end run: 1 level-parameter read, 6
  daily-frame reads, 4 other reads (the earnings calendar, the prior-day reactions, the economic
  events, the earnings calibration), 3 `strat_levels` writes, 1 history insert, 3 existence checks, 1
  canonical upsert; not simulated there and read from code: 1 watchlist read, up
  to 6 gamma probe queries, the RSI calibration reads. The late run drops the 3 existence checks and
  adds 2 reads of the rows in force and the wait: one keyed read per 5 s, at most 84 in the 7
  minutes, 3 rows each, by the unique key of `market_data_daily` (ticker, date). Up to 8 model calls
  in parallel, 12 s timeout each (`gcp/brief_explanations.py:87`, `:345-354`). One Discord post where
  the early run sends four.
- **Wall-clock.** Expected about 140 s: the refresh lands 30 to 70 s after 09:20:00 and the build
  takes 44 to 79 s (live), so the write is expected between about 09:21:15 and 09:22:30. Bound when
  the refresh lands just before the deadline: 420 s of wait plus the slowest build, about 496 s. The
  task timeout is 1800 s (live): about 13 times the expected run and 3.6 times that bound (decision
  F). A build that starts at the deadline has 150 s before the cutoff; the slowest of the last ten
  took 79 s.
- **Cost per late run, and x 1 run a day x 30.** Compute at the audit's rates
  (`docs/audits/COST_AUDIT_2026-09-06.md:227`: 0.000018 USD a vCPU-second, 0.000002 USD a
  GiB-second; 1 vCPU, 1 GiB): 140 s is 0.0028 USD, the 496 s bound is 0.0099 USD. Model calls: about
  0.012 USD (given, #1929: 8 calls, output capped at 500 tokens at 1.50 USD a million,
  `lib/agents/pricing.py:42-46`; input assumed, not measured). About 0.015 USD a run, about 0.45 USD
  over 30 runs, about 0.31 USD over 21 sessions. The owner's yes to the model spend is decision 4.
- **Retries.** `premarket-brief` runs with `--max-retries 0` (`gcp/deploy.sh:1384`, `:1393`; live:
  `maxRetries` 0), so a late run that exits 1 is not run again and cannot post twice. The refresh's
  one retry is handled by the wait. The refresh's log record adds at most 50 lines a run.

## Implementation plan: size

About 14 tasks, one branch (`feature/feat-playbook-001-brief-late-slot`), one PR:

1. The slot: `RUN_SLOTS`, `_resolve_run_slot`, `_late_slot_clock`, the combinations table.
2. The session gate.
3. The stamp read and the wait.
4. The read of the rows in force, "current", and `already_current`.
5. The build check.
6. The late write in `persist_to_cloud_sql`: the re-read, the cutoff check, the one statement with
   `analysis_ts`, the history notes.
7. The real-SQL test of the late write.
8. The note formatter.
9. `main()`: the late flow, exit codes, the log record, the failure line.
10. The early slot's regression test and the existing suites.
11. The API test of the changed ladder (`tests/api/test_movement_statement_late_slot.py`): the early
    write, the late write and the route against one in-memory table.
12. The refresh's log record.
13. The protection plan document and the docstrings.
14. The SITE note, the sidecar, the catalog record and the traceability entry.

Decision 7, the replay cut, is about 7 more: a reader of the session's stored one-minute premarket
bars up to a cut; the snapshot rebuilt from them with the print filter, the prior session's ATR and
the parameters in force; that snapshot put in place of the stored row when `BRIEF_AS_OF` is set; the
replay's observation clock by slot (`_strat_observation_clock` is fixed at 08:30 today, `:900-908`);
bars stored before 2026-09-28 in the older timestamp convention (CLAUDE.md 3.9); a live-against-replay
parity fixture; a production replay checked against a morning's history row. Together that is about
20 tasks, so it is split out: `docs/superpowers/specs/<date>-feat-playbook-001-brief-replay-premarket-cut.md`,
after this change. Until then a replay, with or without the slot, reads the nightly full-window
premarket (given, #1929; live, `db-query-h9rwv`).

Other lanes on the file: the market-date fix (four lines, the precondition), and the two FEAT-STRAT-001
branches the market-date spec names (#1832, #1845; not re-checked). This change adds functions and
one branch in `persist_to_cloud_sql` and `main()`; it edits no line those change.

## Close-out (the owner's steps, each production step on the owner's yes; none is a done_when item)

1. Deploy both jobs this change touches, after the merge: `./gcp/deploy.sh premarket`
   (`premarket-brief`) and `./gcp/deploy.sh market-data` (`fetch-premarket-refresh`, for the log
   record; it also redeploys `fetch-market-data` from main). These are the first two of #1929's three
   deploys; if they are done here, #1929 records the two digests and runs only `schedulers`. A merge
   to main ships neither job (given, the market-date spec). Check, for each job, that
   `gcloud run jobs describe <job> --region=us-east1 --format='value(spec.template.spec.template.spec.containers[0].image)'`
   prints the new digest. The brief's new code is inert until a run carries `BRIEF_RUN_SLOT=late`.
2. The same day, on a day that is not a session, touching nothing:
   `gcloud run jobs execute premarket-brief --region=us-east1 --project=adept-mountain-474619-d4 --update-env-vars="BRIEF_RUN_SLOT=late,BRIEF_POST_TO_DISCORD=false,BRIEF_TRIGGERED_BY=operator:late-slot-session-check" --wait`.
   Expected: the execution succeeds, its log holds `late_slot outcome=not_session`, and
   `./scripts/db_query_cr.sh -q "SELECT count(*) FROM premarket_analysis_history WHERE triggered_by = 'operator:late-slot-session-check'"`
   returns 0. The cutoff's own smoke run is #1929's step 3 (a session day, at or after 09:35 ET): the
   late brief logs `outcome=past_cutoff`, writes no canonical row, no history row and no
   `strat_levels` row, posts the one "not applied" line and exits 1, so that execution shows as
   failed and the job-failure lane may open one issue, to be closed citing the step.
3. Replay through the production path, now and not next session (CLAUDE.md 3.5, 3.6):
   `gcloud run jobs execute premarket-brief --region=us-east1 --project=adept-mountain-474619-d4 --update-env-vars="BRIEF_AS_OF=2026-11-07,BRIEF_RUN_SLOT=late,BRIEF_LLM_DISABLE=1,BRIEF_TRIGGERED_BY=operator:late-slot-replay-check" --wait`.
   2026-11-07 is a Saturday with no canonical row (live, `db-query-f5vhr`). Expected (run on main in
   the frozen-clock harness, where the variable is ignored): three history rows with `run_kind`
   `replay_refresh`; three canonical rows dated 2026-11-07 with `run_kind` `replay` and
   `premarket_unavailable`, which live readers filter out and the resolver skips (a weekend date);
   `strat_levels` rows; no Discord message; no model call. On the new image the log also says the
   slot has no effect on a replay. This is a production write. It proves the deployed image takes the
   variable and that a replay is unchanged by it. It does not exercise the wait, the overwrite or the
   note: those need the live clock. Never replay a date that has a live row: the replay turns that
   row into a replay row (see "Found while reading").
4. The first live late run (the schedule of #1929, or by hand between 09:20 and 09:27 on a session:
   the refresh first, then the brief with `BRIEF_RUN_SLOT=late`; a paid run and a production write).
   Read-only checks, the same day before 23:00 ET, when the nightly job overwrites the snapshot:
   - `./scripts/db_query_cr.sh -q "SELECT c.ticker, c.run_kind, to_char(c.analysis_ts AT TIME ZONE 'America/New_York','HH24:MI:SS') AS written_et, to_char((c.level_basis->'premarket'->>'fetched_at')::timestamptz AT TIME ZONE 'America/New_York','HH24:MI:SS') AS basis_fetched_et, to_char(d.pre_fetched_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS row_fetched_et, c.level_basis->'premarket'->>'pre_high' AS basis_high, d.pre_high AS row_high, c.level_basis->'premarket'->>'pre_low' AS basis_low, d.pre_low AS row_low FROM premarket_analysis c JOIN market_data_daily d ON d.ticker = c.ticker AND d.date = c.analysis_date WHERE c.analysis_date = '<the session>' AND c.ticker IN ('SPY','QQQ','IWM') ORDER BY 1; SELECT ticker, to_char(written_at AT TIME ZONE 'America/New_York','HH24:MI:SS') AS written_et, run_kind, triggered_by, notes FROM premarket_analysis_history WHERE analysis_date = '<the session>' ORDER BY written_at, ticker"`.
     Expected: `run_kind` live; `written_et` after 09:20:00 and before 09:29:30; the two fetch times
     equal and at or after 09:20:00; the highs and lows equal; history holds the 08:30 rows and three
     late rows with `LATE_SLOT_APPLIED`. The comparison is with the row the refresh wrote, not with
     the raw one-minute bars: the snapshot is filtered and the bars are not (QQQ 2026-11-13: 693.13
     against a raw 712.2, live `db-query-h9rwv`).
   - The refresh's log for the 09:20 execution: the "newest premarket bar" record for SPY, QQQ and
     IWM, and how far each is behind the fetch time.
   - The signal monitor's log for the session: its first line that uses levels (given, #1929:
     `put_reanchor` at 09:30:27 on 2026-11-13) is after `written_et`.
   - Discord: one "Levels updated" message, and its numbers match the first query.
   - On the site after the run: `GET /api/movement-statement` for SPY shows the late trigger; the
     owner posts the before and after screenshots on the PR.
   Record the date on the PR as the first session graded on late levels.
5. To stop the late run: pause `premarket-brief-late` (and `premarket-refresh-late`), as #1929 says.
   The early run is not affected. There is no automatic way back to the 08:30 levels inside a
   session; the early row is in history in full.
6. Post-merge source-identity close-out and sidecar retirement for the DASHBOARD-01 note, as the
   product-delivery skill sets them out; the plan's `status: done` follows on a `docs/` branch.

## Risks

- **A late write lands after the monitor has read.** The cutoff check is on the job's clock just
  before one statement is sent. At production driver speeds (0.5 to 2 s a round trip, CLAUDE.md rule
  0) plus the table reflection the first upsert of a process makes, the commit can follow a passing
  check by about 1 to 3 s, so by about 09:29:33 at the worst. The monitor's earliest possible read is
  09:30:00. `TestLateSlotCutoff` pins the check; approach 4 is the stricter form if this margin ever
  proves thin.
- **Two writers at 09:2x.** An operator's `BRIEF_UPDATE` run, a `/replay` for today or a duplicate
  trigger while the late run builds. The re-read before the write refuses on any change and the note
  says which rows are in force. The check is not atomic: a change in the same 1 to 3 s can be
  overwritten. A duplicate late run that starts after the first has written does nothing
  (`TestLateSlotRepeat`).
- **The late levels are worse than the early ones** (a bad print the filter passes). The note shows
  both highs and lows and every changed level seven minutes before the open, and history holds the
  early row in full. Nothing restores it automatically.
- **The late run fails every day and nobody pauses it** (CLAUDE.md rule 0.6). Every failure exits 1
  into the job-failure lane and, where it can, posts one line. The early run is a separate trigger.
- **The early run changes by accident.** `TestEarlySlotUnchanged`, and the existing suites.
- **One ticker holds back the others** (decision B). Visible each time in the note, which names the
  ticker.
- **The outcome statistics change meaning.** From the first applied late run the resolver grades
  late levels and the movement statement's reach rates mix both. Close-out step 4 records the date.
- **The retry flag changes.** If `premarket-brief` ever gets a retry, a late run that exits 1 after
  posting its line would post it again. The flag is 0 in the deploy file and live, and is the
  schedule spec's to keep.
- **A new host-clock read slips in.** The ratchet's baseline must not change (`done_when` item 16).

## Found while reading (not changed by this spec)

- A `BRIEF_AS_OF` replay of a date that has a live row turns that row into a replay row, and no live
  row is left for the date. `gcp/premarket_brief.py:3194` sets the run kind and `:3210-3214` upserts
  over the row. run (Postgres 16): the live row became `replay`. live, `db-query-h9rwv` and
  `db-query-f5vhr`: the rows of 2026-11-10 for SPY, QQQ and IWM are `replay` (rebuilt at 17:30 that
  day), as are 2026-08-25 (3 rows) and 2026-09-25 (1), and all carry resolved outcomes.
- No overwrite moves `premarket_analysis.analysis_ts` (`gcp/premarket_brief.py:3052-3143` builds rows
  without it; `gcp/database.py:484`), while `gcp/schema.sql:5417-5419` calls it "the write timestamp".
  run and live, as in "Problem" item 3.
- The nightly fetch overwrites `market_data_daily.pre_fetched_at` and the premarket columns at 23:00
  ET (live, `db-query-h9rwv`), so a morning snapshot is not kept there.
- #1929's close-out step 5 compares the late `pre_high` and `pre_low` with the maximum and minimum of
  `market_data_intraday` through 09:19. The snapshot is filtered and the bars are not (QQQ
  2026-11-13: 693.13 against 712.2), so that comparison can differ on a correct run. Close-out step
  4 here compares with the refresh's own row instead.
- `gcp/fetchers/fetch_premarket_refresh.py:342-353`: on conflict a null high, low or VWAP keeps the
  earlier value while `pre_fetched_at` takes the new instant, so a value can be older than its stamp.
  Read: it needs every premarket bar's high, open and close to be missing, which a real reply does
  not give. Not run.
- `gcp/deploy.sh:2845-2850`: the update branch of `deploy_fetch_premarket_refresh` sets neither
  `--max-retries` nor `--task-timeout`, so those come from whenever the job was created. Live they
  are 1 and 300.

## What was not verified, in those words

- The late slot has not run anywhere. Every "run" above is of the code on main.
- The late chain's landing time, about 09:21 to 09:23, is the sum of measured parts.
- Trigger, stop and target prices in the example are the fixture's, not production's, and the late
  premarket row in the end-to-end run is simulated from the nightly values.
- The model cost per run is #1929's estimate, not measured; the brief does not record what it spends.
- How late the vendor's newest bar is at 09:20. The refresh's new log record is what will show it.
- The commit latency behind the cutoff margin is the repository's stated range for the driver, not
  measured for this statement.
- Whether Cloud Scheduler can deliver one trigger twice was not checked; the design assumes it can.
- What solyra draws when the ladder changes at about 09:22 was not checked; only the routes were read.
- GitHub was not searched for an issue on the late levels, the replay-over-live row or `analysis_ts`.
- The open branches the market-date spec names for this file (#1832, #1845) were not re-read.
- A statement that copies the early history row back over the canonical row was run once on the
  scratch database only. It is not part of this change.
