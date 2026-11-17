---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001, REQ-REPLAY-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy rows: gcp/schema.sql seeds one new level_param_policy row, effective 2015-01-02 with ON CONFLICT DO NOTHING: plan_target_marks_atr (method_id policy, extra {\"marks\": [0.25, 0.5, 0.75, 1.0]}), so every session, past ones included, is built on the four quarters (owner 2026-11-17, What changed from r2 item 7); no existing row changes in this PR, and exit_legs {\"legs\": 3} and plan_target_level_types are read only for a level-rule basis until Design 13 deletes them; lib/strat_levels.py names the key once and it joins POLICY_WIDE_KEYS; policy_wide_param gives plan_target_marks_atr status ok with value equal to the number of marks when the list holds only numbers, each above zero and each above the one before it (ok with value 0 for an empty list), and input_unavailable for a missing list, an entry that is not a number, an entry at or below zero, a repeat or a falling order; tests in tests/lib/test_level_params_loader.py assert all of it, and status ok with value 4 on the seeded policy loaded from gcp/schema.sql, and fail on origin/main, which has no such key"
  - "ATR marks are the targets: tests/lib/test_strat_levels.py passes a TestAtrMarkTargets class on the three stored 2026-11-16 bases (Design 7 fixtures) rebuilt under the seeded policy: IWM calls targets are 280.14, 281.36, 282.58 and 283.79 and IWM puts 274.64, 273.42, 272.20 and 270.99; for every side of SPY, QQQ and IWM each target equals the trigger in cents plus (calls) or minus (puts) price_cents(mark x ATR), with ATR the basis's own value for its atr_basis, computed in the test from the fixture and not by the builder; each target records its mark, its share label and source atr_mark; gate_targets of every side are its four targets in order, and the trigger and the stop of every side equal what origin/main gives for the same basis (IWM calls 278.92 PMK_H with stop 275.86 PMK_L, IWM puts 275.86 PMK_L with stop 277.41 PQL); no target is moved onto a level (IWM puts T1 is 274.64, never 274.67); skipped is empty; with marks [0.25, 0.5, 0.75] each side has the first three of those targets and three legs; with a marks row that is not ok, with two marks on one cent, with a mark whose offset is zero cents, or with a puts mark at or below zero cents the side publishes no target and target_status carries input_unavailable or the row's status; with a local policy of an empty marks list and exit_legs 3 (arm A) every side's targets, skipped list, target_status, gate_targets and brief text equal origin/main's; the marks cases fail on origin/main"
  - "Waypoints and the stronger case: on the same bases each side built under the marks records plan_waypoints: every level of the basis's levels strictly past the trigger on the side's own side, one entry a cent with every name on that cent, in price order outward, out to the last target and past it only inside the side's trigger window, each entry with price, names, segment (before_t1, t1_t2, t2_t3, t3_t4 or beyond), distance_atr from the trigger and, where levels are grouped, zone with far_price and members; the test computes the expected list from the fixture's levels independently of the builder and also asserts by name and price that IWM calls holds PDO 278.95, PDH 279.17 and PMC 279.33 before T1, CMO 281.64 between T2 and T3 and PMH 285.26 beyond, and IWM puts holds PDL 274.67 before T1, 11/9 Gap Low 274.55 between T1 and T2 and PML 269.88 beyond; a target on a level's own cent records on_level with the level's names (IWM calls T4 283.79 records PWH) and that level is not also a waypoint; a level one cent from a target is a waypoint and the target records no on_level; levels within the ticker's level_cluster_atr x ATR in cents of a group's nearest level print as one zone, equal joins, a zone never spans a target, and with level_cluster_atr not ok every level is its own entry and waypoint_zone_status carries the status; the tests fail on origin/main (no plan_waypoints)"
  - "Brief copy: tests/lib/test_strat_levels.py passes golden-string tests on the stored IWM 2026-11-16 basis with the Design 7 plan_excursions fixture and bias bearish: with the seeded policy the CALLS and PUTS blocks are exactly Design 7's After text; with a local policy of an empty marks list and exit_legs 3 they are exactly the text origin/main prints for that basis (arm A, and a stored level-rule basis until Design 12 rebuilds it); with marks [0.25, 0.5, 0.75] (arm Q3 only) the share reads 1/3 and the last target line reads 'sell the last 1/3, or hold to the close or the stop'; the counts line and every target and waypoint count are read through lib.target_reach from that fixture, a side whose ticker has no rows prints 'no history yet' on each line and never '0 of 0', and a ticker with at least min_sample rows prints 'reached k of n (p%)'; a side built under the marks prints no 'Skipped, closer than' line and, under Decision 6 as recommended, no 'ATR levels' line, while NEXT LEVELS Calls and Puts lines and PMG ZONES are unchanged; a side whose marks row is not ok prints the existing 'Targets unavailable ({status}): no exit plan for this side.' line and no target; the new goldens fail on origin/main"
  - "Rule version and stored briefs: a basis built under a non-empty marks list records the marks version as its rule_version (feat-strat-001.v6: the prior-close change, docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md, took feat-strat-001.v5, which origin/main f6e2a736 holds as LEVEL_RULE_VERSION beside is_current_pick_rule at lib/strat_levels.py:1546; the PR body shows both read on its merge base) and a basis built under the empty list records the level rule's version that origin/main holds on the PR's merge base; tests/gcp/test_level_basis.py passes tests that (a) a stored basis of the level rule, with params that record neither new key and with params that record both, rebuilds through SessionLevels.from_basis with targets, skipped list, target_status and brief text equal to origin/main's, and the marks key is never checked for it, (b) a marks-version basis rebuilds the same four targets, waypoints and text from the marks it recorded after the policy row changes, and (c) gcp.premarket_playbook_resolver.plan_inputs on a marks-version basis returns the four target prices in order, legs 4 and plan_available true, and on a level-rule basis what origin/main returns; tests/lib/test_movement_statement.py passes a test that with resolved rows of the level rule and of the marks version in the population a marks-version session's rates count marks-version rows of its own entry_rule_version only (a row rebuilt by Design 12 from v2 never pools with one built from v5) and a level-rule session's count its own version only, and that _new_rule_mark returns the cleared mark for a marks-version basis; entry_rule_version (the hit-rates spec r2) returns the level-rule version on the PR's merge base for a marks-version basis built live and the basis's rebuilt_from_rule_version for one rebuilt by Design 12, and the same tests (a) and (b) assert that a marks-version basis and a level-rule basis built on the same session with the same inputs have the same trigger and stop on both sides; no file under lib/, gcp/ or platform/ compares a value with a rule version constant outside the helpers named in Design 6 and the population lines of lib/movement_statement.py"
  - "The fourth target is stored and scored in the columns every reader uses (Design 5, Design 11): gcp/schema.sql adds nullable calls_t4_price and puts_t4_price to premarket_analysis and to premarket_analysis_history, and nullable calls_t4_hit_ts, puts_t4_hit_ts, calls_plan_t4_hit_ts, puts_plan_t4_hit_ts and puts_reanchor_t4 to premarket_analysis (nine columns, no plan_t4_price); for a marks side gcp.premarket_brief.structured_playbook_columns writes its four targets to t1 to t4 from a loop over the side's targets, not (1, 2, 3), and writes no plan_t1 to plan_t3 price, and the persisted row carries them (tests/gcp/test_premarket_brief.py); for a level-rule basis it writes what origin/main writes; tests/gcp/test_premarket_playbook_resolver.py passes a TestFourLegs class on synthetic 1-minute bars for a call with trigger 100.00, stop 99.00, targets 100.50, 101.00, 101.50 and 102.00 and four legs: all four reached gives exit 't1,t2,t3,t4', plan_r 1.25 and t4_hit_ts set; the stop after T2 gives 't1,t2,stop,stop' and plan_r -0.125; the mirrored put cases pass; resolve_leg on those four targets sets t1_hit_ts to t4_hit_ts, and resolve_one's UPDATE sets every t4 column; every existing three-leg case of the file passes unchanged on a level-rule basis; the t4 assertions fail on origin/main, where neither PlanOutcome nor LegOutcome has such a field"
  - "Alerts and the movement statement read the quarters (owner 2026-11-17, Design 11): on a marks-version row the signal monitor's LegStateTracker takes T1 from calls_t1_price or puts_t1_price, which hold the 25 percent mark, and the put re-anchor builds four targets at the marks from the re-anchored trigger and the row's recorded ATR and writes puts_reanchor_t1 to puts_reanchor_t4; tests/gcp/test_signal_monitor.py and tests/gcp/test_signal_monitor_level_state.py pass cases that the tracker turns post_t1 at the 25 percent mark and not at the first level past the trigger, and that the re-anchor writes four prices each equal to the re-anchored trigger plus or minus price_cents(mark x ATR); lib/movement_statement.py's slots are the trigger and one slot a target, t1 to t4 on a marks-version row, named from the number of marks and not typed, and a marks-version session's rates count marks-version rows only (tests/lib/test_movement_statement.py); gcp/brief_explanations.py's playbook prompt no longer names 'T1/T2/T3' and lists the targets the plan lists, asserted by a new tests/gcp/test_brief_explanations.py on a four-target and a three-target basis; the new cases fail on origin/main"
  - "Thirds leave the analysis code and the docs: scripts/analysis/honest_scoring_experiment.py loses thirds_rule and its 'a third at each' report lines, which git history keeps for a one-off score; scripts/validation/validate_brief_accuracy.py scores T1 to T4 read from the structured t1..t4 price and hit columns, not parsed from playbook or llm_playbook text (tests/scripts/test_validate_brief_accuracy.py); gcp/queries/nan_triage.sql lists the t4 columns; docs/product/infrastructure/05-h-DATA_DICTIONARY.md and ERD.drawio describe the nine new columns and mark plan_t1_price to plan_t3_price as retired by Design 13"
  - "History rebuilt on the quarters (owner 2026-11-17: 'It should be everywhere, even historical'; Design 12), in its own PR after the implementation is deployed: lib/strat_levels.py gains rebuild_on_marks(basis, marks), which keeps the stored basis's trigger, stop, ATR, ATR basis and levels, runs only the mark walk and the waypoint builder, and returns the marks version as rule_version with rebuilt_from_rule_version set to the version the row recorded, refusing a basis that gives no trigger, stop or ATR; scripts/maintenance/rebuild_quarter_history.py has modes count, archive, rebuild, resolve, verify and restore as Design 12 lists them, and gcp/schema.sql in that PR adds premarket_targets_archive; tests/lib/test_strat_levels.py passes a test that rebuild_on_marks on stored v2, v3 and v5 fixture bases keeps each trigger, stop and ATR to the cent and gives targets equal to the trigger plus or minus price_cents(mark x ATR), and tests/scripts/test_rebuild_quarter_history.py passes every mode on a local Postgres built from gcp/schema.sql with fixture rows of v2, v3 and v5 bases in both tables, one premarket_analysis row with no basis, one with a put re-anchor, one session with no 1-minute bars and plan_excursions rows for the fixture dates: count reports rows by version and the sessions with no bars; archive stores every fixture row whole and every plan_excursions row of those tickers and dates, and stops when its counts differ from count's; rebuild writes the four targets, the re-rendered playbook, puts_reanchor_t1 to puts_reanchor_t4 from puts_reanchor_trigger and the row's ATR, and NULL in every outcome column, keeps llm_playbook, and refuses a row whose trigger or stop would change; resolve reads only market_data_intraday and leaves the no-bars row's outcomes NULL; verify reads zero rows of another rule version, zero plan_t1 to plan_t3 prices and the refused rows by name; and restore returns both tables and plan_excursions to a state equal, row for row and column for column, to a snapshot taken before archive; the PR body shows count read from production, the local run, and Design 12's capacity figures; the PR merges, and the archive, rebuild, resolve and restore modes and the alerts replay touch production, only on the owner's yes when each is run, recorded on the PR; live signal_alerts rows are not rewritten"
  - "Thirds dropped, the last step (Design 13): its own PR, merged only on the owner's explicit yes to that drop, recorded on the PR, after verify reads clean in production; gcp/schema.sql drops calls_plan_t1_price, calls_plan_t2_price, calls_plan_t3_price, puts_plan_t1_price, puts_plan_t2_price and puts_plan_t3_price from premarket_analysis and from premarket_analysis_history (12 columns) and deletes the level_param_policy rows exit_legs and plan_target_level_types, all copied into premarket_targets_archive first (a policy row with source_table level_param_policy and its param_key and effective_from as its key); the same PR removes the ADD COLUMN lines of those 12 columns and the seed INSERTs of those two rows from gcp/schema.sql, so a fresh database equals production, and a new tests/gcp/test_schema_quarter_targets.py asserts that a database built from that schema has none of the 12 columns and neither row, keeps every t1..t4 column, and that applying the schema twice changes nothing; it does not merge while verify lists a refused row the owner has not settled; lib/strat_levels.py loses the level walk, the gap-edge plan targets, the v2 rule and the thirds copy, and gcp/premarket_playbook_resolver.py the v2 column fallback; the PR body lists every dropped column and deleted row with its count read from production just before"
  - "Reach counts read, not stored here: the hit-rates spec r2 (docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md) is built first and its plan_excursions table, entry_rule_version and lib.target_reach are on the merge base; this change adds no reach column to premarket_analysis and no ladder_history_sessions key; the brief reads the counts for all its tickers in the one lib.target_reach query that change already makes, filtered to entry_rule_version of the basis being built, so a marks-version brief counts the level-rule rows written from 2022-01-03 on; each target and waypoint line's count is the trades whose excursion in the policy's measure (touch_atr as seeded) is at least that line's distance in cents over the basis ATR; tests/lib/test_strat_levels.py passes a test that a marks-version brief with plan_excursions rows only of the level-rule version prints counts, not 'no history yet', and a test that a failed read raises instead of printing 'no history yet'; tests/gcp/test_premarket_brief.py passes a test that a marks-version BRIEF_AS_OF run reads only rows before the session date; the tests fail on origin/main"
  - "No numbers and no names: tests/lib/test_level_params_structure.py passes unchanged (no new literal or module constant on the build_session_levels walk) and test_the_walk_reaches_the_rules_it_must_cover also asserts that the mark walk and the waypoint builder are reached from build_session_levels; tests/lib/test_level_params_copy.py asserts that the implementation adds no string literal containing '25%', '50%', '75%', '100%', '1/4' or 'quarter' to lib/strat_levels.py beyond those on the PR's merge base: over every ast.Constant of the file whose value is a str (docstrings and the constant parts of f-strings included), the count of literals containing each of the six strings equals a number pinned in the test for that string, taken from the same count run on the merge base and shown with its line numbers in the PR body; on origin/main d410174b2 the six counts are 0, 0, 0, 0, 0 and 5, the five being the quarter timeframe's own names and the docstrings that mention it (the docstrings that open at lines 258 and 3231, '_quarter' and 'quarter' at line 340 and '_quarter' at line 347), so a share or percent text typed into the level code raises a count and fails the test; the marks, the leg count and the history length are read only from LevelParams and level_param_policy, and the percent and share texts are formatted from those values"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger and stop rule, the opened-through rule, the entry cutoff, the ATR rungs and their thinning (TestAtrRungs, TestAtrRungsDisplayOnly), the NEXT LEVELS Calls and Puts lines, PMG zones, the signal monitor's fire decisions apart from the T1 its level state reads, persona plans, the CALL/PUT pick, and, for a basis built under a local empty marks list (arm A, and a stored level-rule basis until Design 12 rebuilds it), the level rule's spaced walk, thirds, gap-edge targets, gate targets and the t1..t3 columns"
  - "Experiment through the production paths, before any production change of the plan: the implementation PR body shows, for SPY, QQQ and IWM over 2022-01-03 to 2026-11-10 on the gap-edges spec's ticker-days (one trade per ticker-day, the first side to cross its trigger, a same-bar tie is no trade, a day that opens past a trigger is no trade, half days cut at the exchange close, SPY 2025-04-09 and IWM 2026-06-26 left out), plan R from gcp.premarket_playbook_resolver.resolve_plan with inputs from plan_inputs on bases built by gcp/premarket_brief.py (BRIEF_AS_OF) into a local copy of the schema, never production, for the arms of the Experiment section: A today, Q four quarters at marks 0.25, 0.5, 0.75 and 1.0, and Q3 thirds at marks 0.25, 0.5 and 0.75; per arm every measure of the Experiment section's Reported list; arm A is checked twice and both checks are required: (a) harness check: the committed driver has a baseline-only mode that scores arm A alone and needs neither the new outcome field mfe_atr nor the Q and Q3 databases; run as a file from the PR head with the working directory and PYTHONPATH set to a detached worktree of commit 97190ef41 (git worktree add --detach <dir> 97190ef41; the base the 2026-11-16 spike ran on), so that every gcp and lib import resolves to that commit, against a local database built from that commit's gcp/schema.sql and prepared by that commit's tools from the same exported inputs as the head run, never production and with no production write, it reproduces the gap-edges spec's +176.8 R over 3,463 trades to 0.1 R; the PR body shows that total and trade count, the worktree's HEAD sha and the file paths the run printed for gcp.premarket_brief, gcp.premarket_playbook_resolver and lib.strat_levels; this proves the harness and its data, not the new code; (b) on the implementation's head: arm A is whatever the head's rules give, with no pinned total; it is reported with its trade count beside the spike's +176.75 R over 3,463 trades, and the PR body attributes the difference to the premarket rule changes merged since that commit (the brief build, PR #2010, and the prior-close print rule, docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md) by one named measure, trigger-changed ticker-days: the count of ticker-days on which the calls trigger or the puts trigger of the head's basis differs to the cent from the basis of the (a) run or exists in one run only, and arm A's R and trade count in each run on those ticker-days and on the rest, with every ticker-day of the rest whose arm A R differs between the two runs listed with its cause; arms Q and Q3 are read against the head's arm A; no arm, the head's arm A included, is read if (a) fails; an arm whose 90% range against A lies wholly below zero overall, or for two of the three tickers, is reported as failing, and the implementation PR is not merged with it without the owner's explicit decision recorded on the PR; arms Q and Q3 are built by the implementation's marks builder under the marks policy rows in that local copy, not by replacing targets or legs on arm A's inputs, and the 2026-11-16 spike's output (which did replace them) is shown beside the new figures and is not accepted in their place"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the implementation PR, whose merge applies gcp/schema.sql to production and so puts the quarters in every new brief, is merged only after the owner's yes to that merge, given after the Experiment is shown in its body and recorded on the PR; the deploy, the Design 12 run and the Design 13 drop are each a step the owner approves when it is run; the deploy puts every reader of a stored level_basis (the playbook resolver, the signal monitor, the API and the insight pipeline) on the implementation before or with the brief job (Design 11)"
status: approved
supersedes: docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md
---

# The exit plan sells a quarter at 25, 50, 75 and 100 percent of ATR from the entry, and the levels are waypoints

## What changed from r2

This spec (r3, 2026-11-17) supersedes `docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets-r2.md`
(r2: approved, merged in stocks #2019), which is marked `superseded` in the same commit, its
`status` line the only edit to it. r2's implementation plan
(`docs/superpowers/plans/2026-11-16-feat-strat-001-atr-quarter-targets.md`) is pointed at this file
by its own change before any code PR opens, since the gate refuses a plan bound to a superseded spec.
No code was written on r2.

The owner, 2026-11-17 (UTC), answered "Yes" to: should the hit rates go on the new quarter-target
lines instead of a separate ladder, with history back to 2022; and added "When I did thos in thirds
it was able to go back. Do last week's". So the reach counts come from the hit-rates spec's table,
which is filled from 2022, and not from new columns that start empty:

1. **Design 4** reads `plan_excursions` through `lib.target_reach` (hit-rates spec r2) instead of
   adding `calls_plan_mfe_atr` and `puts_plan_mfe_atr`. The `ladder_history_sessions` key is dropped;
   the window and measure come from that spec's `target_reach_rate` row (every trade since
   2022-01-03, touch, in ATR). The measure is the same one r2 defined: furthest move past the
   trigger after the fill bar, before the stop bar, cut at the close, over the basis ATR.
2. **Decision 3 is reversed** on the owner's answer: counts are read from every row that shares the
   marks version's trigger and stop rule, through `entry_rule_version`, so the lines carry history
   from 2022 on the first day instead of `no history yet`.
3. **Design 7** gains one counts line after the stop line, as the hit-rates spec prints, and its
   goldens count from one pooled `plan_excursions` fixture (sides pooled per ticker, the hit-rates
   spec's Decision 4), so the counts in the After text change.
4. **The schema change** is six nullable columns, not eight (nine under item 8, all of them different).
5. **Conflicts** gains item 9; **Risks**, **Expected effect**, **Capacity** and **Close-out** follow.
6. **Merge order** gains one step: the hit-rates build first (Decision 9).

Then the owner widened the change, 2026-11-17 (Authority):

7. **Thirds are retired everywhere, with quarters replacing them.** The seeded marks row is the four
   quarters for every date, not an empty list, so the implementation PR's merge, on the owner's yes
   after the Experiment, is the swap; r2's later-dated swap rows are gone (Design 8, Decisions 1 and
   10). A marks side's leg count is its number of marks; `exit_legs` is read only for a level-rule
   basis (Design 2).
8. **The alerts and the target columns move to the quarters.** Decision 12 is reversed: a marks
   side's gate targets are its four targets, written to `t1` to `t4`; the signal monitor's T1 state,
   its put re-anchor and the movement statement's slots follow (Design 11). No `plan_t4_price` is
   added, and a marks side writes no plan price column (Design 5).
9. **History is rebuilt.** Every stored brief row is rebuilt on the quarters and its outcome
   resolved again, the old values archived first, in its own PR and run (Design 12).
10. **The drop is the last step.** The thirds price columns and policy rows are dropped in their
    own PR on the owner's explicit yes (Design 13).
11. **Non-goals, Approaches, Designs 1, 2, 5 and 8, the Experiment's gate, Decisions 1, 6, 7, 10
    and 12, Conflicts, Expected effect, Close-out and Risks** follow these items, and done_when gains five items.
12. **Review fixes, re-cut of stocks #2052** (2026-11-17). The history rebuild keeps each row's
    recorded trigger, stop, ATR and levels through a new `rebuild_on_marks`, and records the
    version it was rebuilt from, so rates pool by the entry rule (Design 12, Design 6); the archive
    takes whole rows and the `plan_excursions` rows resolve rewrites, and restore is tested against
    a full before-run snapshot; a session with no bars keeps NULL outcomes, not old ones; the
    deterministic playbook and the re-anchor targets are rebuilt and `llm_playbook` is an owner
    decision (Decision 13); capacity, a deploy order and the tests are named; the marks version is
    pinned to `feat-strat-001.v6`; stale swap-row and fewer-marks wording is gone.

Everything else is r2's, including r2's own "What changed from r1" notes, kept below.

### Carried from r2: what changed from r1


This spec (r2, 2026-11-16) supersedes `docs/superpowers/specs/2026-11-16-feat-strat-001-atr-quarter-targets.md` (r1: approved, merged in
stocks #2013), which is marked `superseded` in the same commit, its `status` line the only edit to
it. The gate admits exactly that edit to an approved spec, and only when an approved spec for the
same FEAT names it in `supersedes` (`scripts/gate/spec_gate.py:2033-2045`, read on `main`
d410174b2: "an approved spec does not change in place; write a new spec that names it in
`supersedes` and get that one approved, then mark this one superseded"). Once r2 is on main the
gate refuses a plan bound to r1 (`:2515-2525`, read: "point the plan at the current spec"), so the
plan in stocks #2018 must name this file before it merges.

r1 is carried forward word for word: the same `feat_id`, `req_ids` and `site_source_notes`, the
Design, the twelve Decisions, the owner's words and the Experiment's result as run. Only what
follows differs. No decision, no number and no part of the design changed.

1. **done_when, "No numbers and no names": the word 'quarter'.** r1 asked that "no string literal
   in lib/strat_levels.py contains '25%', '50%', '75%', '100%', '1/4' or 'quarter'". That cannot be
   met without renaming the quarter timeframe, which nothing here asks for: on `main` d410174b2
   five string literals of `lib/strat_levels.py` already contain `quarter` (run, by `ast` over
   every string constant: the docstring that opens at `:258`, the docstring that opens at `:3231`,
   `'_quarter'` and `'quarter'` at `:340` and `'_quarter'` at `:347`), and the other five strings
   have no hit. The same five, at the same lines, are on 97190ef4, the commit r1's code references
   are to, and five are on the brief build's branch at 8cd5e686 (run). The item now reads: the
   implementation adds no such literal beyond those on its merge base, checked by a count for each
   of the six strings pinned in the test from the merge base. The intent sentence is kept: the
   percent and share texts are formatted from the policy values.
2. **done_when, "Experiment through the production paths", and the Experiment's Method: arm A's
   pin.** r1 required arm A to reproduce +176.8 R over 3,463 trades to 0.1 R before any other arm
   is read. On the implementation's base that total cannot be assumed: the brief build (stocks
   #2010) and the prior-close print rule
   (`docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md`), both built
   before this change (Decision 9), change how the premarket high and low are taken, and so the
   replay's triggers. r1 says as much under "Limits of this run": "the level of each total may
   move". The pin is now two checks, both required: (a) a harness check, in which the committed
   driver's baseline-only mode reproduces the old figure against the production modules of
   97190ef41, the spike's base; and (b) arm A on the implementation's head, reported as it comes
   out, with the difference attributed by a named measure, and Q and Q3 read against it. No arm is
   read if (a) fails. Everything else of the item stands: the marks builder requirement added in
   review, the spike's figures shown beside, the local copy of the schema, never production. The
   Method paragraph of the Experiment section is reworded to match, and nothing else in that
   section changed.
3. **Authority** gains one paragraph recording where these two corrections came from. The
   frontmatter's `supersedes` names r1.

Not changed, and how to read it here:

- "What this replaces", Close-out step 4 and every use of "the superseded spec" in the carried text
  are r1's own words and still mean the three-targets spec
  (`docs/superpowers/specs/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md`),
  which r1 superseded and which stays `superseded`. The lineage is: that spec, then r1, then this
  one. r1 is called r1 only in this section, in the Authority paragraph added here and in the two
  changed items.
- Code references stay as r1 wrote them, to `main` 97190ef4. They were not re-read for r2 beyond
  the `ast` count above.
- Two notes of the implementation plan (stocks #2018) were checked against the done_when items and
  are silences the plan may fill, not items that cannot be met, so the text is r1's: which rule
  version a fresh build records when the marks row is missing or not ok (the items name only the
  non-empty and the empty list, and ask of a row that is not ok only that the side publishes no
  target and carries the status); and whether a marks-version basis records the reach history it
  printed (the "Rule version and stored briefs" item asks that such a basis rebuilds the same
  text, and does not say where the counts come from; if the basis records them, Design 10's
  Volume line understates the basis by up to `ladder_history_sessions` numbers a side, which the
  plan's capacity section states and the implementation PR's capacity figures must carry).

## Authority

r3, widened: the owner, 2026-11-17 (UTC), as relayed with the owner's words copied by the server:
"I want thirds removed from everything in the data. It can be scored separately as needed by
referencing old code if ever needed" (11:47Z) and "It should be everywhere, even historical"
(11:47Z); then "Yes" (11:48Z), which the session that put the question records as the owner's yes to
switching the live alerts to the four quarters in the same change (the question itself was not read
here). So thirds leave every new brief, alert, exit, replay, scorecard and stored field, history
included, and the old values stay in an archive and in git history for a one-off score.

r3: the owner, 2026-11-17 (UTC), in the hit-rates thread, as relayed with the owner's words copied
by the server: "Yes" to putting the hit rates on the quarter-target lines with history back to 2022,
and "When I did thos in thirds it was able to go back. Do last week's". Asked how the counts work:
"Yes but edplain the reached k of n? Is this something you are doing for hit rates or will it be
done daily,", answered: worked out in every morning brief, from history filled once and one trade
added each day.

T, 2026-11-16, in chat, as relayed to this session (the chat itself was not read here):

> The level-based target design "is getting overly complex".

> "Quarters not thirds anymore"

> "these are the levels between the targets ... help you to understand if you are still moving or
> have momentum towards the average true range"

What the owner decided:

1. Targets are fixed fractions of ATR(14) measured from the entry trigger: T1 25%, T2 50%, T3 75%,
   T4 100%. Calls above the trigger, puts below.
2. Four sales, a quarter at each target.
3. The levels are no longer targets. They are printed by name as waypoints between the targets. A
   target that lands on a level is the stronger case and the brief says so.
4. This is drafted now and run as one more arm of the experiment beside today's plan before the
   live plan changes. The experiment gates the production change.

**Decided by the owner on 2026-11-16, after seeing the experiment** (Experiment, "Result as run").
In chat, as relayed to the session that recorded it; the chat itself was not read there. The quoted
words are the owner's:

- "Quarters are still my preference".
- Put two questions, the owner answered "1 yes" to switching to plain quarters at 25, 50, 75 and
  100 percent of ATR from the entry trigger, and "2 no" to keeping level targets with the ATR
  ladder as display only.
- "Quarters not Thirds anymore". Four sales.
- The entry trigger "is fine". It does not change (Design 1).
- On the insight's under 1.5R check (rule N2): "agree with judge reward on the average of the four
  targets, which is what you bank if the plan completes." Specified in the conviction spec
  (Design 9, Decision 7).
- "Fixing the prior close problem will help with triggers." That is the prior-close spec
  (`docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md`), which merges and is
  built before this one (Decision 9).
- On the three other approved FEAT-STRAT-001 specs that describe the level rule: "Update after we
  finalize experiments and target implementation." (Conflicts, item 1.)
- "the replay is fine, the live brief should be done at 820 and 920 with updates." Recorded as
  said. The run times are an open item (Experiment, "Result as run", limits); this spec designs no
  schedule.
- "Mark specs ready if they are ready and resolve any conflicts. Keep the work moving. Auto merge."
  Every numbered decision under "Decisions for the owner" is therefore decided per its
  recommendation, except a production step, which stays a step the owner approves at the time it is
  run, exactly as written.

`status: approved`, by the owner (T) on 2026-11-16. Under r2, approval approved the build behind policy rows that reproduced today's plan, and later rows changed the live plan. Under r3 the seeded row is the quarters (What changed from r2, item 7), so the implementation PR's merge changes the live plan. The owner has chosen the arm (Q, four quarters) knowing its result. The merge, the deploy, the Design 12 run and the Design 13 drop are each a step on the owner's yes when it is run, the merge after the implementation PR has shown the Experiment as its done_when item requires.

The two corrections of r2 ("What changed from r1") were found by the implementation plan and its
review, and are recorded here because an approved spec cannot be edited in place; the owner said
"Mark specs ready if they are ready and resolve any conflicts. Keep the work moving."

Rulings still in force (restated from the superseded spec's Authority, read): a change is tested
against its hypothesis before it is swapped in; R is the stock's move after the fill measured in stop
distances, never money; values are never hard-coded. The 2026-11-08 ruling also says values are
tailored per ticker through calibration. The four fractions here are one list for every ticker, by
the owner's decision above; they live in a policy row, not in code (see Conflicts, item 5).

Code references are to stocks `main` 97190ef4 (2026-11-16). "Read" means read from the code or a
document at that commit, with file and line. "Run" means a command was run in this session and the
output is given. "Handed" means a number given to this session and not checked. Anything else says
"not checked". Production was not read or written for this spec: no query, no `gcloud`.

## What this replaces

This spec supersedes
`docs/superpowers/specs/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md`
(approved, merged; no code from its plan has been written: `git branch -r` shows no
`feature/feat-strat-001-plan-always-three-targets` branch, run). That spec stops being authority
when this one is approved; it is then marked `superseded` in the same change, which the gate
requires to be the only edit to it (`scripts/gate/spec_gate.py:2035-2044`, read).

Its plan, `docs/superpowers/plans/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md`,
stays on main with `status: ready`. A plan has only `ready` and `done`
(`scripts/gate/spec_gate.py:1351`, read), so it cannot be marked withdrawn. Once this spec is
approved the gate refuses code on that plan's branch because its spec is superseded (`:2515-2525`,
read). Nothing else is needed to retire it.

**Carried over** from the superseded spec, restated here in full where this spec depends on it:

- the whole ladder is printed (Design 3, Design 7);
- close levels are shown as one zone, now only in the display of waypoints (Design 3);
- reach history: one stored number a trade from which every target and waypoint gets a count,
  now the hit-rates spec's table (Design 4);
- the experiment method (Experiment);
- the brief's numbers and the insight's plan are one plan (Design 9).

**Dropped:** the fill rule for a missing T3 (`target_fill_sources`, the two reach keys); the
minimum-distance rule for targets under the new rule (`target_min_spacing_atr` no longer decides a
target; it still thins the display-only ATR rungs); the T1 zone options; `target_merge_atr` and
zones as anything that changes a target.

## Problem

### 1. The level-target design kept growing

Today a side's targets are levels, chosen by a spaced walk. `_plan_targets`
(`lib/strat_levels.py:2821-2890`, read) walks the side's unbroken in-window candidates past the
trigger, keeps one only when it is at least `target_min_spacing_atr` x ATR past the trigger or the
target before it, and stops at `exit_legs` (3, `gcp/schema.sql:2298`, read). Gap edges join the walk
through `plan_target_level_types` (`:2318`). The superseded spec added, on top: zones of close
levels, three ordered fill steps for a missing T3, two reach keys, and a marker in the stored basis.
The owner's judgement on 2026-11-16 is that this is overly complex.

### 2. On 2026-11-16 every side had two targets and an unpriced third

From the superseded spec's table of the stored rows (read there; production not read here): IWM,
SPY and QQQ each printed two targets a side, and the last third had no price.

### 3. A level is where price may stall, not a measure of how far the day can go

The owner's reading: the ATR is the day's expected range, so a sale at each quarter of it is a plan
that does not depend on where levels happen to sit, and the levels in between tell the trader
whether the move still has momentum toward the full range.

### 4. Nothing stored can say how often a mark or a waypoint is reached

Unchanged from the superseded spec (its Problem 4, read): the resolver stores hit times for the gate
targets and for plan targets 1 to 3 (`gcp/schema.sql:1992-1994`, `:2001-2003`, read) and
`{side}_mfe_pct`, which runs past the stop. Nothing says how far price went from the trigger before
the stop. Design 4 stores that one number.

## Non-goals

- No trading costs in R or in the Experiment.
- SPY, QQQ and IWM only.
- No change to the trigger, the stop, the opened-through rule or the entry cutoff.
- No change to the signal monitor's fire rules beyond the T1 its level state reads and the put
  re-anchor's targets, which move to the quarters (Design 11).
- No change to the insight planner's persona R targets (`target_{persona}_{k}_r`,
  `lib/agents/trade_planner.py`): they are multiples of its own stop, not shares of the exit
  (Design 11).
- No snapping of a target to a nearby level (Design 2; Decision 4).
- No breakeven or trailing stop.
- No change to the insight's risk rules in this spec's PR. The under 1.5R rule is a dependency,
  stated in Design 9. The owner decided on 2026-11-16 what it reads; that is specified in the
  conviction spec, not here.
- No solyra change in this spec's PR. What the site assumes about three targets is listed in
  Design 9.
- No per-ticker calibration of the four fractions (Conflicts, item 5).
- Filling the reach history. The hit-rates spec's history job fills it from 2022-01-03 (Design 4).
  Rebuilding the stored brief rows is Design 12.

## Approaches considered

1. Chosen: the marks are one policy-wide row; a side built under a non-empty list takes its targets
   at trigger plus or minus mark x ATR; levels become waypoints; a basis built that way records a new
   rule version. The seeded row is the four quarters for every date (r3), and a local empty list rebuilds the level rule, so the Experiment scores both rules on one code base until Design 13 removes the level rule.
2. Switch in code with no policy row. Rejected: the Experiment needs arm A and arm Q from the same code, and the fractions would be literals in code against the standing ruling. (r2 also rejected it because a replay of a session before the swap had to rebuild that session's plan as it was; under r3 the owner wants past sessions on the quarters too, Design 12.)
3. Use the brief's existing ATR rungs as targets. Rejected: those hang from PDH, PDL, PMK_H and
   PMK_L (`gcp/schema.sql:2307`, read), not from the entry, and the owner asked for marks measured
   from the entry trigger.
4. Snap a mark to a level a few cents away. Rejected for now: the owner did not ask for it. The
   Experiment reports how such marks do (Decision 4).
5. Keep the superseded design. Rejected by the owner as overly complex.

## Design

### 1. Entry trigger and stop: unchanged, and where they come from

Both come from `_pick_side` (`lib/strat_levels.py:2721-2818`, read):

- **Trigger.** The side's candidates are listed with `broken` and `in_window` (`:2758-2762`). The
  unbroken ones inside the side's own window are `rungs` (`:2780-2781`). The trigger is the first of
  them, `trig = rungs[0]` (`:2798`): the nearest unbroken candidate at or past the cleared mark
  inside the side's `trigger_window_*_atr`.
- **Stop.** `stop = next(c for c in other if _within_staleness_window(...))` (`:2813-2814`): the
  nearest candidate on the other side of the reference inside the other side's window.
- **Gate targets.** `out.gate_targets = rungs[1:4]` (`:2802`): the next three rungs, with no
  spacing. The signal monitor and the `t1..t3` columns read these. Unchanged for a level-rule basis; for a marks side they are its four targets (Design 11).

The resolver reads the trigger and the stop from the rebuilt side (`plan_inputs`,
`gcp/premarket_playbook_resolver.py:612-618`, read). None of these lines change in behaviour. The
only branch that changes is the one that today calls `_plan_targets` (`:2812`).

### 2. Targets: fractions of ATR from the trigger

New policy-wide key `plan_target_marks_atr`, method `policy`, extra `{"marks": [...]}`: the
distances of the targets from the trigger, in the policy's ATR basis, nearest first.

For a side with a trigger, built under a non-empty list:

- target k = trigger in cents + sign x `price_cents(marks[k] x ATR)`, sign +1 for calls and -1 for
  puts. The offset is rounded to the cent once, with the one rounding rule (`price_cents`,
  `lib/strat_levels.py:921-937`, read), and added to the trigger's cents, the way the ATR rungs are
  placed (`:2592-2594`, read).
- Each target records `price`, `mark` (0.25), `source` `atr_mark` and, when a level sits on its
  cent, `on_level` (Design 3).
- The number of targets is the number of marks, and so is the leg count: a quarter at each of four
  marks, a third at each of three (arm Q3). `exit_legs` is not read for a marks side (r3); it stays
  read only for a level-rule basis until Design 13 deletes its row. So `resolve_plan` never cuts a
  target (`targets[:plan.legs]`, `gcp/premarket_playbook_resolver.py:545`; run, see Design 5).
- **No snapping.** A target is never moved onto a level. IWM puts T1 is 274.64 with PDL at 274.665
  (274.67 to the cent, run); the level prints as a waypoint just before it.
- Keys checked first, as `_plan_targets` does today (`:2836-2855`): `plan_target_marks_atr` and `entry_cutoff_et`. One that is not ok publishes no target and records its status.
  Two marks that land on one cent, an offset of zero cents, or a puts mark at or below zero cents
  give `input_unavailable`. There is no fallback to the level walk (CLAUDE.md 3.7).
- `skipped` is empty: nothing is passed over. `target_min_spacing_atr` and
  `plan_target_level_types` are not read for this side's targets.
- `plan` records the marks, each mark's price, the ATR and its basis, the leg count (the number of
  marks) and the entry
  cutoff, so the copy and the resolver read one source, as `plan` does today (`:2842-2851`).

The owner's example, checked with the repo's rounding (run, `price_cents` on trigger and offsets,
ATR 4.874951 from the superseded spec's Design 8):

| | Trigger | T1 25% | T2 50% | T3 75% | T4 100% |
|---|---|---|---|---|---|
| IWM calls | 278.92 | 280.14 | 281.36 | 282.58 | 283.79 |
| IWM puts | 275.86 | 274.64 | 273.42 | 272.20 | 270.99 |

Offsets in cents: 122, 244, 366, 487. These are the owner's numbers.

**Which ATR.** The one every distance of the plan already uses: `atr_v = atrs.get(params.atr_basis)`
(`lib/strat_levels.py:2368`, read), where `atr_basis` is the policy row in force
(`{"column": "atr_14"}`, `gcp/schema.sql:2257`, read) and the values are the last completed
session's ATR columns the brief passes (`gcp/premarket_brief.py:1371`, read). The marks use that
same value and no other, and the brief prints which (`ATR(14)`, from `atr_length`, `:1636`).

**ATR unavailable.** A side with no ATR already has no trigger: `_pick_side` returns reason
`atr_unavailable` before any pick (`lib/strat_levels.py:2774-2776`, read), and the brief prints the
reason line for the side. So no mark is ever built without an ATR, and none is invented. A side with a trigger whose marks row is not ok prints the existing line `Targets unavailable
({status}): no exit plan for this side.` (`:3199`, read).

### 3. Levels are waypoints

A side built under the marks records `plan_waypoints`: every level of the session's `levels`
(prior-period highs, lows and closes, opens such as PDO and CMO, gap edges, the parent bar, the
premarket extremes; `lib/strat_levels.py:2393-2408`, `:539-545`, read) strictly past the trigger on
the side's own side, one entry a cent carrying every name on that cent, in price order outward.

- **Range.** From the trigger to the last target, and past the last target only inside the side's
  trigger window (the `in_window` rule the side already applies, `:889-910`). On the owner's
  example this lists PMH 285.26 for calls and PML 269.875 for puts as "beyond" and nothing farther.
- **Segment.** Each entry says where it sits: `before_t1`, `t1_t2`, `t2_t3`, `t3_t4` or `beyond`
  (named from the number of marks, not typed).
- **A target on a level.** A level on a target's own cent is not a waypoint; the target records
  `on_level` with the level's names and the brief calls it the stronger case. IWM calls T4 283.79 is
  PWH 283.79. "On" means the same cent. A level one cent away is a waypoint.
- **Close levels are one zone, for display only.** Within one segment, a level joins the open group
  when its distance in cents from the group's nearest level is at most
  `price_cents(level_cluster_atr x ATR)` (equal joins), so a zone is never wider than that distance.
  A zone never spans a target. `level_cluster_atr` is the ticker's existing calibrated "same place"
  distance (`gcp/schema.sql:2270`, read), so no new number is added (Decision 5). With that key not
  ok every level is its own line and `waypoint_zone_status` records the status. A zone changes no
  target, no score and no stored price.
- **Gap fill note.** A waypoint or `on_level` level that is the prior close keeps the gap fill note
  the plan prints today for a prior-close target, by the same key and rule (`:2875-2888`).

The owner's example, by this rule:

| Side | Before T1 | T1 to T2 | T2 to T3 | T3 to T4 | On a target | Beyond |
|---|---|---|---|---|---|---|
| IWM calls from 278.92 | PDO 278.95, PDH 279.17, PMC 279.33 | none | CMO 281.64 | none | T4 on PWH 283.79 | PMH 285.26 |
| IWM puts from 275.86 | PDL/PWL 274.665 | 11/9 Gap Low 274.55 | none | none | none | PML 269.875 |

Whether the stored 2026-11-16 basis holds any other level in those ranges was not checked
(production was not read); the fixture test computes the list from the fixture itself.

### 4. Reach history: read from the hit-rates table

No new column. The hit-rates spec r2
(`docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md`) stores one row a
ticker-day in `plan_excursions`: the first side to fill, its trigger, stop and ATR, and how far price
went past the trigger after the fill bar and before the stop bar, cut at the exchange close, in stop
distances and in ATR (`excursion_atr`), touch and held 5 minutes. Its history job writes those rows
from 2022-01-03 by rebuilding each session's basis, and its resolver adds one a day. That is the
number r2 asked for (`*_plan_mfe_atr`), with three differences that change no line's meaning: one
trade a ticker-day, sides pooled, as the 1832 tests counted; a side with no valid stop writes no row
instead of being measured to the close; a stop on the fill bar gives NULL, which reaches nothing,
where r2 gave 0.0.

The rows are keyed by `entry_rule_version`, the version whose trigger and stop rule built them. The
marks version keeps the trigger and stop (Design 1), so this change sets `entry_rule_version` of the
marks version to the level-rule version it is built on, and a marks-version brief counts the
level-rule rows. So the lines read history from 2022 on the first day.

From it every line's count follows: a mark or waypoint `d` x ATR past the trigger was reached before
the stop on the trades whose `excursion_atr` is at least `d`, where `d` is the line's distance in
cents over the basis ATR. Because each session rounds its own offsets to the cent, a count can
differ from that session's stored `plan_t1_hit_ts` by one cent's rounding; the count is of trades
that went at least as far as today's line.

The brief already reads the counts for all its tickers in one query (`lib.target_reach`, the
hit-rates spec's Reader), with the window and measure of its `target_reach_rate` row: every trade
since 2022-01-03, touch, in ATR, sessions before the brief's own. It prints after the stop line
`Reached before the stop: {ticker} trades {first} to {last} ({n})` and on each target and waypoint
line `reached k of n (p%)`, or `reached k of n` below the row's `min_sample` (30), or `no history
yet` with no rows. A failed read raises (CLAUDE.md 3.7) and the brief prints that spec's unavailable
line. A `BRIEF_AS_OF` run reads only earlier dates.

### 5. The fourth target: every place three slots are assumed

`resolve_plan` already scores any number of legs: on main, with four targets and `legs=4`, a call
that reaches all four gives exit `t1,t2,t3,t4` and R 1.25, and a stop after T2 gives
`t1,t2,stop,stop` and R -0.125 (run in this session against `main` 97190ef4). With `legs=3` the same
four targets give `t1,t2,t3` and the fourth is cut without a word (run). What is fixed at three is
the storage and the display:

| Place | File and line (read) | What changes |
|---|---|---|
| Leg count | `gcp/schema.sql:2298` (`exit_legs` `{"legs": 3}`); read at `lib/strat_levels.py:2857`, `:3205` | A marks side's leg count is its number of marks; `exit_legs` is read only for a level-rule basis, and its row goes in Design 13. |
| Target price columns | `gcp/schema.sql:1888-1897` (`t1..t3`), `:1898-1905` (`plan_t1..t3`), history `:2138-2171` | Add nullable `calls_t4_price`, `puts_t4_price` to both tables. A marks side writes its four targets to `t1..t4` and no `plan_t*` price; the `plan_t1..t3_price` columns go in Design 13. |
| Hit columns | `gcp/schema.sql:1929-1947` (gate hits), `:1992-1994`, `:2001-2003` (plan hits) | Add nullable `calls_t4_hit_ts`, `puts_t4_hit_ts`, `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts`. |
| Put re-anchor | `gcp/schema.sql:1922-1924`; `gcp/signal_monitor.py:536-603` | Add nullable `puts_reanchor_t4`; the re-anchor builds four targets at the marks (Design 11). |
| Reach counts | `plan_excursions` (hit-rates spec r2) | None here: read through `lib.target_reach` (Design 4). |
| Writing the price columns | `gcp/premarket_brief.py:1561-1565` (`for k in (1, 2, 3)` for both `t` and `plan_t`); `:3748-3753` (the persisted row) | The loop runs over the side's targets: `t1..t4` for a marks side and no `plan_t` price; a level-rule basis writes what main writes. The persisted row's keys come from that loop, not a list of twelve. |
| Plan outcome | `gcp/premarket_playbook_resolver.py:146` (`PlanOutcome.t3_hit_ts`), `:550-553` (`targets[:3]`, three slots), `:877-878` (`_PLAN_FIELDS`) | Add `t4_hit_ts`; the hit walk covers four targets; `_PLAN_FIELDS` gains `t4_hit_ts`, which carries it into the UPDATE (`:843`). |
| Plan inputs | `gcp/premarket_playbook_resolver.py:591-640` | A marks-version basis is read like today's current rule: targets by price, legs and cutoff from the side's `plan` (`:611-624`). The v2 fallback's `(1, 2, 3)` (`:636`) reads the gate columns and stays until Design 13. |
| Legs cut | `gcp/premarket_playbook_resolver.py:545` | Unchanged; a marks side's leg count is its number of marks (Design 2), so nothing is cut. |
| Brief text | `lib/strat_levels.py:3173-3227` (`_plan_block`) | Design 7. The share `1/{legs}` and the last-leg wording are already built from the leg count (`:3205-3219`). |
| Discord | `gcp/premarket_brief.py:2820-2852` (`_playbook_code_fields`), `:2854-2900` | No change: the playbook is the text, split at line breaks with nothing cut (read). The embed's docstring says "T1/T2" (`:2855`); wording only. How the longer text splits across messages was not checked. |
| Movement statement | `lib/movement_statement.py:251` (`_REACH_SLOTS`), `:286-349`, `:406-490` | The slots are the trigger and one a target, `t1..t4` on a marks-version row, named from the number of marks (Design 11), plus the version handling (Design 6). |
| Signal monitor | `gcp/signal_monitor.py:536-603`, `:652-678`; `lib/strategies/brief_bias.py:81-113` | T1 state and the put re-anchor read the quarters (Design 11). |
| Insight plan, stocks | `lib/agents/schema.py:241-244` ("Up to 3 price targets", a description, no length limit); `gcp/insight_discord_push.py:221` (`targets[:3]`); `lib/agents/trade_planner.py:284-287` | Not changed by this spec's PR (Design 9, Decision 8). |
| Insight plan, solyra | `src/components/insights/redesign/Panels.tsx:79-80` (Target 1 and Target 2 only); `src/routes/AiInsightsLovablePage.tsx:108` (`slice(0, 3)`), solyra `main` 80c82c2 | Not changed by this spec (Design 9, Decision 8). |
| Tests and fixtures that hold three legs or `t3` columns | `tests/lib/test_strat_levels.py`, `tests/lib/test_session_levels_rules.py`, `tests/lib/level_params_fixtures.py`, `tests/lib/test_level_params_loader.py`, `tests/lib/test_movement_statement.py`, `tests/lib/test_movement_statement_level_basis.py`, `tests/gcp/test_level_basis.py`, `tests/gcp/test_level_params_consumers.py`, `tests/gcp/test_calibrate_level_params.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/gcp/test_premarket_brief_late_slot.py`, `tests/gcp/test_brief_channel_routing.py`, `tests/api/test_movement_statement_exit_plan.py`, `tests/fixtures/atr_levels_brief_base.json`, `tests/fixtures/atr_levels_display_only_base.json` (found by a search for `t3_hit_ts`, `t3_price`, `plan_t3`, `exit_legs`, `legs` 3 and `sell 1/3`, run) | They pin the level rule and three legs; they keep passing on a level-rule basis built with a local empty marks list and `exit_legs` 3, and cases on the seeded quarters are added beside them; the policy fixture `tests/lib/level_params_fixtures.py` gains the two new keys. Which assertions inside each file would need a new case was not checked file by file. |
| Other readers of the columns | `gcp/queries/nan_triage.sql:35-36`; `scripts/analysis/honest_scoring_experiment.py:317-527`; `scripts/validation/validate_brief_accuracy.py:392-445` | The triage SQL lists the `t4` columns; the analysis script loses `thirds_rule`, which git history keeps; the validation script parses T1 to T4. |

**The schema change applies itself.** `gcp/cloudbuild/apply-schema-cloudbuild.yaml:1-5` says the
`apply-schema-on-change` trigger fires on a push to main that touches `gcp/schema.sql` and applies
that revision's schema (read; the live trigger was not read). The implementation PR adds one policy row and nine nullable columns, so merging it changes production, and the row is the quarters for every date. The merge is an owner-approved step: one question before merging, after the Experiment is shown, the yes recorded on the PR. Until the deploy, a job still on the old image reads
a policy key it does not know as a ticker key with status `params_unavailable`, records it and
ignores it (`lib/strat_levels.py:1454-1496`, read).

### 6. Rule version, stored rows and rates

A basis built under a non-empty marks list records the marks version as its `rule_version`.

**Which number the marks version is: `feat-strat-001.v6`.** The prior-close change
(`docs/superpowers/specs/2026-11-16-feat-playbook-001-prior-close-prints-r2.md`, its decision 3 and
PC6) took `feat-strat-001.v5` in every case and is on main: origin/main f6e2a736 holds
`LEVEL_RULE_VERSION = 'feat-strat-001.v5'` and `PICK_RULE_VERSIONS` v3, v4 and v5
(`lib/strat_levels.py:1542-1543`, read). The marks version is therefore v6, and v3, v4 and v5 are the
level-rule versions. The PR body shows both constants read on its merge base.

A basis built under the empty list records the level rule's version, `feat-strat-001.v5` on main
today. So the version a row carries always names the rule that picked its targets, whatever the date
it was built on.

**The brief spec's helper.** B8b defines `lib.strat_levels.is_current_pick_rule(version)`, true for
v3 and v4 through `PICK_RULE_VERSIONS`, and a meta test that lets only that helper and the
movement statement's two population lines compare a value with the rule version (its plan, Task
B8b interfaces, read). The helper is on main (`lib/strat_levels.py:1546`, read on f6e2a736). v3, v4 and v5 share one pick rule. The marks version is a different pick rule, so:

- `is_current_pick_rule` answers what its four readers ask: "does this basis carry its own plan,
  cleared mark and version, to be read and rebuilt as recorded?" For the marks version the answer is yes, exactly
  as for the level-rule versions: `SessionLevels.from_basis` keeps the basis's own version
  (`lib/strat_levels.py:1968`), `_assemble` keeps it (`:2434`), `plan_inputs` reads the plan from the
  basis (`gcp/premarket_playbook_resolver.py:611`) and `_new_rule_mark` returns the cleared mark
  (`lib/movement_statement.py:499`). The marks version joins `PICK_RULE_VERSIONS`.
- Which rule picks the targets is a second question, and it gets its own helper in
  `lib/strat_levels.py`, `plan_target_rule(version)`: `v2` for v2, `levels` for every level-rule version (v3, v4 and v5), `atr_marks` for the marks version,
  nothing else. `_pick_side` calls the level walk or the mark walk by it. The
  brief spec's meta test gains this helper as an allowed site, and no other comparison is added.
- A stored level-rule basis is rebuilt by the level walk with the values it recorded, and the marks
  key is never checked for it, even when its params record that key (the loader records every
  policy key once its row exists, `:1441`, `:1452-1456`). A marks-version basis is rebuilt by the mark walk from the marks it recorded, so later policy rows leave it unchanged.
- A row rebuilt by Design 12 is a marks-version basis that records `rebuilt_from_rule_version`,
  the level-rule version it was published under. Its entry is that rule's, kept to the cent;
  `entry_rule_version` returns `rebuilt_from_rule_version` when present, and the level-rule version
  of the merge base for a marks basis built live.

**Rates never mix rule versions.**

- The movement statement's reach rates select rows by `level_basis->>'rule_version'`
  (`lib/movement_statement.py:348`, `:366-368`, read). After B8b the bound value is the session
  row's own version. So a marks-version session's rates count marks-version rows only, and a v4
  session's v4 rows only. Its slots are the gate targets, which on a marks-version row are the four quarters (Design 11):
  one version, one population. Within the marks version the rows are pooled by
  `entry_rule_version` as well, so a row rebuilt from v2 never pools with one built live from v5,
  whose entry rule differs. Until Design 12 runs the marks version has no resolved rows of its own.
- The reach counts of Design 4 are read from rows of the basis's entry version: the trigger and
  stop rule, which the marks version shares with the level rule it is built on. They measure only
  the trigger, the stop, the ATR and the bars, so no target rule enters them (Decision 3).
- The Experiment's rates are per arm and never pooled across arms.

### 7. What the brief prints

For a side built under the marks, the plan block (`_plan_block`) prints, after the stop line:

```
    Reached before the stop: {ticker} trades {first} to {last} ({n})
    Targets at {p1}, {p2}, ... and {pn} of ATR({n}) = {atr} past {trigger}, sell {1/legs} at each
      {price or "near to far"} ({names}): level on the way, {d} ATR past the trigger, {reached k of n[ (p%)] | no history yet}
    T{i}: {price} ({p}% of ATR[, on {names}: the stronger case]), sell {1/legs}, {reached k of n[ (p%)] | no history yet}
      {price} ({names}): level beyond T{last}, {d} ATR past the trigger, {reached k of n[ (p%)] | no history yet}
```

Waypoints print in price order between the target lines they sit between. The last target line
keeps the distinction main already makes (`lib/strat_levels.py:3213-3219`, read): a marks side's legs equal its marks (Design 2), so it reads
`sell the last {1/legs}, or hold to the close or the stop`. The percents and the share are formatted from
the policy values; none is a literal. No `Skipped, closer than` line is printed, since nothing is
skipped. The `ATR levels` line of NEXT LEVELS is not printed for such a side (Decision 6). NEXT
LEVELS' Calls and Puts lines and PMG ZONES are unchanged. A basis built under the level rule prints
exactly what main prints.

**Fixtures.** The stored `level_basis` of `premarket_analysis` for 2026-11-16 (IWM, SPY, QQQ; the
superseded spec names the row built 2026-11-16T08:31:19 ET), copied verbatim into
`tests/fixtures/` by a read-only export the owner allows once (the superseded plan's Task 1 step 1,
not done). Rendered with bias `bearish`. Reach history for the goldens: sixteen IWM
`plan_excursions` rows of the level-rule entry version, one a session from 2026-10-23 to
2026-11-13, with `excursion_atr` in date order 0.1, 0.3, 0.4, 0.7, 1.1, 1.2, 1.6, 2.4, 0.05, 0.2,
0.3, 0.6, 0.9, 1.3, 1.5, 2.1 (r2's two side lists, pooled as the hit-rates spec pools sides). IWM: ATR(14) 4.874951;
`level_cluster_atr` about 25 cents (the superseded spec, read there).

Today (origin/main on the stored basis, from the superseded spec's Design 8, read there; not
rendered in this session):

```
  CALLS above 278.92 (PMK_H) -- only if bias denied, new entries 09:30 to 16:00 ET
    No entry if the open is at or above 278.92.
    Stop: 275.86 (PMK_L)
    T1: 283.79 (PWH), sell 1/3
    T2: 285.26 (PMH), sell 1/3, hold the last 1/3 to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 1.22: 279.17 (PDH), 279.33 (PMC)
    Room to trigger: 0.92%

  PUTS below 275.86 (PMK_L), new entries 09:30 to 16:00 ET
    No entry if the open is at or below 275.86.
    Stop: 277.41 (PQL)
    T1: 274.55 (11/9 Gap Low), sell 1/3
    T2: 269.88 (PML), sell 1/3, hold the last 1/3 to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 1.22: 274.67 (PDL)
    Room to trigger: 0.19%
```

After (marks 0.25, 0.5, 0.75, 1.0 and four legs; derived by this spec from the owner's example and
the fixture rows, not produced by an implementation):

```
  CALLS above 278.92 (PMK_H) -- only if bias denied, new entries 09:30 to 16:00 ET
    No entry if the open is at or above 278.92.
    Stop: 275.86 (PMK_L)
    Reached before the stop: IWM trades 2026-10-23 to 2026-11-13 (16)
    Targets at 25%, 50%, 75% and 100% of ATR(14) = 4.87 past 278.92, sell 1/4 at each
      278.95 to 279.17 (PDO, PDH): level on the way, 0.01 ATR past the trigger, reached 16 of 16
      279.33 (PMC): level on the way, 0.08 ATR past the trigger, reached 15 of 16
    T1: 280.14 (25% of ATR), sell 1/4, reached 13 of 16
    T2: 281.36 (50% of ATR), sell 1/4, reached 10 of 16
      281.64 (CMO): level on the way, 0.56 ATR past the trigger, reached 10 of 16
    T3: 282.58 (75% of ATR), sell 1/4, reached 8 of 16
    T4: 283.79 (100% of ATR, on PWH: the stronger case), sell the last 1/4, or hold to the close or the stop, reached 7 of 16
      285.26 (PMH): level beyond T4, 1.30 ATR past the trigger, reached 4 of 16
    Room to trigger: 0.92%

  PUTS below 275.86 (PMK_L), new entries 09:30 to 16:00 ET
    No entry if the open is at or below 275.86.
    Stop: 277.41 (PQL)
    Reached before the stop: IWM trades 2026-10-23 to 2026-11-13 (16)
    Targets at 25%, 50%, 75% and 100% of ATR(14) = 4.87 past 275.86, sell 1/4 at each
      274.67 (PDL, PWL): level on the way, 0.24 ATR past the trigger, reached 13 of 16
    T1: 274.64 (25% of ATR), sell 1/4, reached 13 of 16
      274.55 (11/9 Gap Low): level on the way, 0.27 ATR past the trigger, reached 13 of 16
    T2: 273.42 (50% of ATR), sell 1/4, reached 10 of 16
    T3: 272.20 (75% of ATR), sell 1/4, reached 8 of 16
    T4: 270.99 (100% of ATR), sell the last 1/4, or hold to the close or the stop, reached 7 of 16
      269.88 (PML): level beyond T4, 1.23 ATR past the trigger, reached 5 of 16
    Room to trigger: 0.19%
```

If the fixture holds a level in range that the owner's example does not name, the golden is the
fixture's, and the difference is reported on the PR.

### 8. No swap rows

r2 turned the rule on with later-dated policy rows after a second yes. Under r3 the seeded row is the
four quarters for every date (Decision 1), so there are no swap rows: the implementation PR's merge,
on the owner's yes after the Experiment, applies the row; the deploy puts it in every new brief; a
`BRIEF_AS_OF` replay of any past session builds the quarters; and Design 12 rebuilds the stored rows.
Arm A is scored on the same code with a local copy whose marks list is empty and `exit_legs` 3,
until Design 13 removes the level rule.

### 9. The insight and the site: one plan

The approved insight spec
(`docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`) makes the
insight's plan the brief's plan: entry, stop and targets read from the side record the brief stored,
"the insight follows whatever the row holds" (its Scope and Non-goals, read). Its code is not on
main (`grep` finds no `read_stored_sides` or `compute_rule_flags`, run); on main the planner still
prices targets as R multiples of its own stop (`lib/agents/trade_planner.py:284-287`, read). Once it
lands, a marks-version row gives the insight four targets with no further change, and that rule stands: the
brief's numbers and the insight's plan are one plan.

Three things then assume fewer than four, all outside this spec's PR (Decision 8):

- `gcp/insight_discord_push.py:221` prints `targets[:3]`.
- solyra `Panels.tsx:79-80` shows Target 1 and Target 2; `AiInsightsLovablePage.tsx:108` draws
  `slice(0, 3)`.
- `lib/agents/schema.py:241-244` describes "Up to 3 price targets" (text only).

**The under 1.5R rule: a dependency, decided by the owner and specified in the conviction spec.**
Rule N2 warns when the first target is
under 1.5R (`lib/agents/prompts.py:228-232`, read; the insight spec moves it to
`compute_rule_flags`, its Design 3, read). With T1 at 0.25 x ATR, T1 in R is 0.25 divided by the
stop distance in ATR, so N2 fires whenever the stop is more than about 0.167 x ATR from the entry.
Brief stops sit about 0.4 x ATR from the entry at the median (handed; measured earlier today by
another session, not checked here), which puts T1 near 0.6R. On 2026-11-16 the insight spec gives
stop distances of 0.32 (IWM), 0.71 (QQQ) and 0.22 (SPY) x ATR for the short sides (its Decision 7,
read): T1 would be 0.78R, 0.35R and 1.14R. Run for IWM in this session: calls 0.40R, 0.80R, 1.19R
and 1.59R for T1 to T4; puts 0.79R, 1.57R, 2.36R and 3.15R. So N2 would warn on nearly every plan,
and the insight spec says a warn bars high conviction (its Risks, read; `orchestrator.py` not
opened here).

Measured since, by the spike (Experiment, "Result as run"; quoted from its `report_v1_side.txt`):
"stop distance in ATR (trigger to stop): median 0.36, quartiles 0.26 / 0.51", and T1 at 0.25 ATR is
"under 1.5R on 93.1% of 3463 trades; under 1.0R on 76.2%; median 0.69R". The 0.4 handed above is
that 0.36.

That rule and its 1.5R line are under review in the draft conviction spec
(`docs/superpowers/specs/2026-11-16-feat-insight-001-conviction-reachable.md` on
`origin/docs/spec-feat-insight-001-conviction-reachable` at c6b58201, `status: draft`, read; the
task names it PR #2009, not checked). Its measurement grid tests the first target at 1.0R, 1.5R and
2.0R on the brief's present targets.

The owner decided on 2026-11-16 that the reward is judged on the average of the plan's targets
(Authority). For four quarters at 25, 50, 75 and 100 percent of ATR that average is 0.625 x ATR,
against the same stop distance: 0.625 / 0.36 = 1.74R at the median stop, where T1 alone is 0.69R.
What changes in the insight's code, and its test, is specified in the conviction spec, not here.
This spec's PR changes no risk rule. Until that change is deployed the insight still judges T1
alone, so the merge follows it, or the owner accepts the warning on nearly every plan
when giving the yes to the implementation merge (Decision 7).

### 10. Capacity and cost (CLAUDE.md rule 0)

- **Volume:** one policy row; nine nullable columns; each new `level_basis` gains a waypoint list
  of about 3 to 10 entries a side (IWM 2026-11-16: 5 and 3 by the owner's example) and loses the
  skipped list.
- **Velocity:** no new query: the counts come from the hit-rates spec's one read a brief run (about
  3,500 rows for three tickers). No new query in the resolver.
- **Wall-clock:** none beyond the hit-rates spec's read.
- **Cost:** $0 scheduled; no new job or schedule. The Experiment runs on a local copy. Each
  production dry run of the brief costs one brief's model calls (Decision 11).

### 11. Alerts, target columns and the movement statement move to the quarters

The owner, 2026-11-17: "Yes" to switching the live alerts to the four quarters in the same change
(Authority). So "T1" means the 25 percent mark on every surface, not the first level past the trigger.

- **Gate targets.** For a marks side `gate_targets` is its four targets in order, so
  `_legacy_trigger_dict`'s `targets` and `room_to_first_target` (`lib/strat_levels.py:2994-3027`,
  read by the inventory) and the `t1..t4` price columns carry the quarters. A level-rule basis keeps
  `rungs[1:4]` until Design 13.
- **Resolver.** `resolve_leg` (`gcp/premarket_playbook_resolver.py:277-400`) takes the side's
  target list and writes `t1..t4_hit_ts`; `_traded_exit` (`:403-460`, all out at the stop or T1)
  exits at the 25 percent mark on a marks row, its rule name unchanged; `resolve_plan` writes
  `plan_t1..t4_hit_ts` through `_PLAN_FIELDS`; the self-heal UPDATE (`:880-893`) writes four prices.
  `RESOLVER_VERSION` gains a dated version.
- **Signal monitor.** `LegStateTracker` (`lib/strat_levels.py:101-216`) takes T1 from
  `calls_t1_price` or `puts_t1_price` (`gcp/signal_monitor.py:652-678`,
  `lib/strategies/brief_bias.py:81-113`), which now hold the 25 percent mark, so `post_t1` and
  `post_t1_open` mean past the first quarter. The put re-anchor (`gcp/signal_monitor.py:536-603`)
  builds four targets at the marks from the re-anchored trigger and the row's recorded ATR and writes
  `puts_reanchor_t1..t4`. Its comment "alert targets keep their pre-spacing meaning" goes. The
  TARGET HIT watcher's percent target (`:1661`, `:2173`) is not a plan target and is unchanged.
- **Movement statement.** `_REACH_SLOTS` (`lib/movement_statement.py:236-251`) becomes the trigger
  plus one slot a target, `t1..t4` on a marks-version row, named from the number of marks;
  `_fetch_tracked_levels` and `_reach_rate_sql` read the four columns; `ReachRate.slot`
  (`platform/api/schemas.py:528-538`) documents `t4`. One version, one population (Design 6); after
  Design 12 every stored row is the marks version, so the slots carry history from 2022.
- **Brief explanations.** `_PLAYBOOK_PROMPT` (`gcp/brief_explanations.py:570`) stops naming
  "T1/T2/T3" and names the targets as the plan lists them; a new
  `tests/gcp/test_brief_explanations.py` pins it on a four-target and a three-target basis.
- **Deploy order.** Every image that reads a stored `level_basis` (the playbook resolver, the
  signal monitor, the API that serves the movement statement, and the insight pipeline) is deployed
  from the implementation before or with the brief job. An image that does not know a version in
  `PICK_RULE_VERSIONS` does not refuse it: `SessionLevels.from_basis` rebuilds it under the v2 rule
  (`lib/strat_levels.py:2064` on f6e2a736: `rule = recorded_rule if is_current_pick_rule(recorded_rule)
  else LEVEL_RULE_V2`, read; the prior-close spec r2 ran the same case), so a reader deployed after
  the brief would score a v6 row on v2 targets.
- **Not thirds, and kept:** the persona R targets (`target_{persona}_{k}_r`), multiples of the
  insight planner's own stop; `target_min_spacing_atr`, which after this change only thins the
  display-only ATR rungs; `gap_fill_flag_atr`, which labels a prior-close waypoint.
- **Not in this repo:** solyra's Target 1 and Target 2 panel and its `slice(0, 3)` chart (Design 9,
  Decision 8), and the scorecard files in the project folder, which the scoring task rebuilds from
  the rebuilt rows.

### 12. History rebuilt on the quarters

The owner, 2026-11-17: "It should be everywhere, even historical". Every stored brief row is rebuilt
on the four quarters and its outcome resolved again, so no stored row keeps thirds or level targets
as its plan. Its own PR, opened after the implementation is deployed. That PR merges, each mode that
writes production runs, and the alerts replay runs, each only on the owner's yes when it happens,
recorded on the PR.

**A rebuild keeps the entry the row was published with.** Only the targets change. The rebuild does
not go through `SessionLevels.from_basis`, which rebuilds a level-rule basis by its own level walk
(Design 6), and it does not rebuild the entry under today's rules, which would move triggers on v2
to v4 rows. It goes through one new function in `lib/strat_levels.py`,
`rebuild_on_marks(basis, marks)`: it reads the recorded trigger, stop, ATR, ATR basis and levels,
runs only the mark walk and the waypoint builder of Designs 2 and 3 on them, and returns a basis
with `rule_version` the marks version, `rebuilt_from_rule_version` the version the row recorded,
the four targets, `plan_waypoints` and `plan`. Rates pool marks rows by that entry version
(Design 6). A basis that gives no trigger, stop or ATR is refused, not guessed. A row with no
`level_basis` uses its stored `{side}_trigger_price` and `{side}_stop_price` and the ATR that
`derive_level_map_from_daily` (`gcp/premarket_playbook_resolver.py:173-275`) gives for its date,
and is refused when any of the three is missing. Refused rows are listed by verify, and Design 13
does not run until the owner has settled each: kept with NULL targets, or restored.

`scripts/maintenance/rebuild_quarter_history.py`, modes in order:

1. **count** (read-only): per table (`premarket_analysis`, `premarket_analysis_history`) and
   `run_kind`, the rows by recorded `rule_version` and by whether a basis exists, with the earliest
   and latest date and the average `pg_column_size` of a row; the `plan_excursions` rows by
   `entry_rule_version`; and bar coverage: per ticker, the sessions with and without 1-minute bars
   in `market_data_intraday`. The PR body shows it read from production.
2. **archive**: every row that rebuild or resolve may write goes into `premarket_targets_archive`
   whole, as `to_jsonb` of the row, so `level_basis`, `playbook`, `llm_playbook`, the target,
   hit, plan outcome, honest outcome, re-anchor and self-heal columns (the resolver's UPDATE writes
   trigger, stop, target and outcome columns, `gcp/premarket_playbook_resolver.py:795-895`, read)
   are all kept, and a column added later is kept too. Every `plan_excursions` row of the same
   tickers and dates goes in as well, since resolve upserts and deletes them. The table, added to
   `gcp/schema.sql` by that PR: `archive_id`, `run_id`, `source_table`, `source_key` JSONB (the
   row's primary key; for a policy row in Design 13 its `param_key` and `effective_from`),
   `ticker`, `date`, `run_kind`, `archived_at`, `old_row` JSONB. The run stops unless the archived
   counts equal count's, per table.
3. **rebuild**: `rebuild_on_marks` on each archived row, under the seeded marks. It writes
   `t1..t4_price`, NULL `plan_t1..t3_price`, `level_basis`, and `playbook`, the deterministic
   text, rendered again from the rebuilt basis by `_plan_block`. Where a put re-anchor was
   recorded it writes `puts_reanchor_t1..t4` from `puts_reanchor_trigger` and the row's ATR at the
   marks, leaving `puts_reanchor_open`, `_trigger`, `_trigger_name`, `_stop` and `_at` as they are.
   It sets every outcome column the resolver writes, and `outcome_resolved_at`, to NULL, so no row
   keeps an outcome scored on the old targets. `llm_playbook`, the model's published text, is kept
   as the record of what was sent (Decision 13). A row whose trigger or stop would change by a cent
   is refused.
4. **resolve**: the resolver over every rebuilt `premarket_analysis` row, forced, on as-traded
   1-minute bars from `market_data_intraday` only, writing hit times, the honest outcome, the plan
   outcome with four legs and the `plan_excursions` rows. A session with no bars: `resolve_one`
   returns `no_bars` and writes nothing (`gcp/premarket_playbook_resolver.py:746-748`, read), so the
   row keeps the NULL outcomes rebuild left, never a guessed outcome and never the old one; count's
   coverage line names those sessions.
5. **verify** (read-only): zero rows whose `rule_version` is not the marks version; zero non-NULL
   `plan_t1..t3_price`; zero triggers or stops that differ from the archive; archived, rebuilt and
   refused counts adding up, with each refused row listed; resolved counts by status, the no-bars
   rows equal to count's coverage gap; and zero `playbook` texts that sell a third.
6. **restore**: writes every archived row back whole by `archive_id`, deleting the `plan_excursions`
   rows resolve added for those keys and writing back the archived ones, so every step can be
   undone until Design 13. Its test compares both tables and `plan_excursions` to a snapshot taken
   before archive, row for row and column for column.

- **Readers of the stored text.** `scripts/validation/validate_brief_accuracy.py` reads the
  structured `t1..t4` columns, not the text, so the kept `llm_playbook` does not feed it
  (Design 11's table of other readers).
- **Alerts.** `signal_alerts` rows hold no target price, and a live row is the record of an alert
  that was sent, so it is not rewritten. The quarter history of alerts is
  `scripts/replay_signal_monitor.py` run over 2022-01-03 to the deploy date on the rebuilt rows with
  `--persist` (`run_kind` `replay`, one `replay_id`, removable by that id), its fires by
  `level_state` set beside the live rows' in the PR body. A replay fire on a live fire's minute is
  dropped and logged, as that script already does. `--persist` writes production, so it runs on the
  owner's yes.
- **Hit-rates table.** `plan_excursions` stores no target (hit-rates spec r2), so rebuild writes
  nothing to it; resolve rewrites its rows for the rebuilt sessions, which archive covers.
- **Capacity.** Rows: three tickers, about 1,230 sessions each since 2022-01-03, so about 3,700
  `premarket_analysis` rows, plus the history rows; count gives the real numbers. Round trips:
  archive is one `INSERT ... SELECT` per table and ticker; rebuild one read and one UPDATE a row;
  resolve one 1-minute bar read a session and one UPDATE plus its `plan_excursions` upsert. Work is
  batched per ticker, one transaction a ticker and table, so a failed ticker rolls back alone and
  each run stays inside the job's task timeout, which the PR reads from the job's configuration and
  states. Wall-clock is measured on the local run over the fixture and on one ticker's real count,
  and shown in the PR body. Archive size is count's rows times its average row size, shown before
  archive runs. No model call; $0 beyond Cloud SQL time.

### 13. Drop the thirds columns and rows: the last step

Its own PR, merged only on the owner's explicit yes to the drop, recorded on the PR, after verify
reads clean in production. Until then every old value is in place or in the archive, and restore can
undo the rebuild. What it removes, each value copied into `premarket_targets_archive` first:

| What | Where | Count |
|---|---|---|
| `calls_plan_t1_price`, `calls_plan_t2_price`, `calls_plan_t3_price`, `puts_plan_t1_price`, `puts_plan_t2_price`, `puts_plan_t3_price` | `premarket_analysis` | 6 columns |
| the same six | `premarket_analysis_history` | 6 columns |
| `exit_legs` `{"legs": 3}`, effective 2015-01-02 (`gcp/schema.sql:2298-2299`) | `level_param_policy` | 1 row |
| `plan_target_level_types` `{"level_types": ["gap_high", "gap_low"]}` (`:2318`) | `level_param_policy` | 1 row |

Each policy row is archived with `source_table` `level_param_policy` and its `param_key` and
`effective_from` as `source_key`. The same PR removes from `gcp/schema.sql` the `ADD COLUMN` lines of
the twelve columns and the seed `INSERT`s of the two rows, and adds the `DROP COLUMN` and `DELETE`, so
a fresh database equals production; a new `tests/gcp/test_schema_quarter_targets.py` builds a
database from that schema and asserts none of the twelve columns and neither row is present, every
`t1..t4` column is, and a second apply changes nothing. It does not merge while verify lists a
refused row the owner has not settled.

From the code: the level walk (`_plan_targets`), the gap-edge plan targets (`_plan_extra_rungs`), the
v2 rule, the thirds copy of `_plan_block`, `EXIT_LEGS_KEY`, `PLAN_TARGET_LEVEL_TYPES_KEY` and the
resolver's v2 column fallback. Old code stays in git history for a one-off score of the archived
values. Kept: `premarket_targets_archive`; the `t1..t4`, hit, re-anchor and plan outcome columns,
which now hold the quarters; `target_min_spacing_atr` and `gap_fill_flag_atr` (Design 11). The PR
body lists every dropped column and deleted row with its count read from production just before.

## Experiment

Run before any production change of the plan. A spike ran it on 2026-11-16, before the
implementation exists; its result is recorded under "Result as run" below and is the basis of the
owner's decision. The method, arms and Reported list here are unchanged, and the done_when item
"Experiment through the production paths" stands as written: the implementation PR runs the
Experiment again on the implementation's code. The spike did not build the ATR arms: it took arm
A's `plan_inputs` and replaced `targets` and `legs` by hand, so its totals say nothing about the
marks builder this spec adds. Arms Q and Q3 in the implementation PR are therefore scored on bases
built by `gcp/premarket_brief.py` under the marks policy rows and read through `plan_inputs`, and
the spike's output is not accepted in their place. The spike's figures are set beside the new ones
in the PR body, and any difference in a total, a trade count or a reach share is explained there.
The merge, which puts the quarters live, waits for that and for the owner's yes.

**Hypotheses.**

- H1, quarters: selling a quarter at 25, 50, 75 and 100 percent of ATR from the trigger does no
  worse in total R than today's plan.
- H2, thirds at the first three marks does no worse than today's plan, and Q against Q3 says what
  the fourth sale at the full ATR is worth.

What is known going in, so the result is read fairly (gap-edges spec, Experiment, read): today's
plan made +176.8 R over 3,463 trades with T1 hit before the stop on 22% of trades and T2 on 4%.
Today's targets are far and seldom hit; the marks are near and will be hit more often for less each.
The exits spec removed close first targets on evidence, and today's `target_min_spacing_atr` seed is
0.25 (`gcp/schema.sql:2294`), the same distance as the first mark. From another session's notes,
handed to the superseded spec and not checked: the spacing skip was worth about +80 R and selling
sixths at every merged rung made +90.5 R. Those notes are a reason to expect Q may score below A,
not a result.

**Arms** (policy rows in the local copy; everything else the seeded policy on main):

| Arm | `plan_target_marks_atr` | Legs | Sales |
|---|---|---|---|
| A, today (a local empty list) | `[]` | 3, from `exit_legs` | thirds at the spaced level targets; a leg with no target held to the close or the stop |
| Q, quarters (the seeded policy, r3) | `[0.25, 0.5, 0.75, 1.0]` | 4, the number of marks | a quarter at each mark |
| Q3, thirds | `[0.25, 0.5, 0.75]` | 3, the number of marks | a third at each mark; a leg whose mark is not reached is held to the close or the stop, as today's unsold leg is |

Q3's last third is read here as: sold at the 75% mark when reached, otherwise held to the close or
the stop like any leg today. Decision 2 names the other reading.

**Method.** The gap-edges spec's: every session from 2022-01-03 to 2026-11-10 for SPY, QQQ and IWM
replayed through `gcp/premarket_brief.py` (`BRIEF_AS_OF`) with history-mode parameters into a local
copy of the schema; one trade per ticker-day, the first side to cross its trigger; a same-bar tie
is no trade; a day that opens past a trigger is no trade; the 16:00 cutoff on main; half days cut
at the exchange close; SPY 2025-04-09 and IWM 2026-06-26 left out; each trade scored by
`gcp.premarket_playbook_resolver.resolve_plan` on `plan_inputs` of the arm's basis. No bar walk is
written for the test (CLAUDE.md 3.6). No trading costs. The trigger and stop are the same in every
arm, so the three arms trade the same ticker-days and differ only in exits.

**Arm A is checked twice, and both checks are required.**

- (a) **Harness check.** The committed driver has a baseline-only mode that scores arm A alone. It
  needs neither the new outcome field `mfe_atr` nor the Q and Q3 databases. It is run as a file
  from the PR head with the working directory and `PYTHONPATH` set to a detached worktree of commit
  97190ef41 (`git worktree add --detach <dir> 97190ef41`; the base the 2026-11-16 spike ran on), so
  that every `gcp` and `lib` import resolves to that commit, against a local database built from
  that commit's `gcp/schema.sql` and prepared by that commit's tools from the same exported inputs
  as the head run. It writes nothing to production. Run that way it must reproduce +176.8 R over
  3,463 trades to 0.1 R. The run prints the worktree's HEAD sha and the file paths of
  `gcp.premarket_brief`, `gcp.premarket_playbook_resolver` and `lib.strat_levels` as imported, and
  the PR body shows them with the total and the trade count. This proves the harness and its data,
  not the new code.
- (b) **On the implementation's head.** Arm A is whatever the head's rules give; no total is
  pinned. It is reported with its trade count beside the spike's A (+176.75 R over 3,463 trades).
  The PR body attributes the difference to the premarket rule changes merged since 97190ef41 (the
  brief build, stocks #2010, and the prior-close print rule) by one named measure,
  **trigger-changed ticker-days**: the count of ticker-days on which the calls trigger or the puts
  trigger of the head's basis differs to the cent from the basis of the (a) run, or exists in one
  run only; and arm A's R and trade count, in each run, on those ticker-days and on the rest. Every
  ticker-day of the rest whose arm A R differs between the two runs is listed with its cause. Arms
  Q and Q3 are read against the head's arm A.
- No arm, the head's arm A included, is read if (a) fails.

**Reported, per arm:**

1. total R; SPY, QQQ, IWM;
2. the six-month blocks of the gap-edges spec (Mar to Aug and Sep to Feb, first and last partial);
3. the 90% range of arm minus A, resampling whole days 2,000 times, seed 7;
4. the share of entered trades reaching T1, T2, T3 and, for Q, T4 before the stop;
5. **the reach share of each ATR mark** (0.25, 0.5, 0.75, 1.0) before the stop, from the reach
   measure of Design 4, for every arm including A, so the marks are compared on today's trades too;
6. **the reach share of waypoints**, by level name (PDH, PDC, PMC, CMO, gap edges and so on) and by
   segment (before T1, T1 to T2, and so on, and beyond), with counts;
7. **a target on a level against the rest:** the reach share of marks that sit on a level's cent
   against marks that do not, by mark;
8. **a target just past a level against the rest:** the reach share of marks that have a level
   within the ticker's `level_cluster_atr` x ATR before them (toward the trigger) and not on their
   cent, against marks with no such level, by mark. IWM puts T1 on 2026-11-16 is one such mark;
9. win rate, average win and average loss in R, and the share of trades that end at the stop with
   no sale, since the arms differ in shape and not only in total;
10. the share of entered sides whose T1 is under 1.5R and under 1.0R, for the conviction spec;
11. traded sides with fewer targets than legs, and trades whose exits differ from A.

**What keeps today's plan.** An arm whose range against A lies wholly below zero overall, or for
two of the three tickers, fails this test, and the PR says so. The implementation PR then does not merge with the quarter seed unless the owner decides so on the evidence: the owner
chose this design for its simplicity, so a failing arm goes to the owner with the totals, the
blocks and the shape measures, and the decision is recorded on the PR. An arm whose range spans
zero is put to the owner as "no worse, by this test". If both Q and Q3 pass, the owner picks; the
recommendation is Q, the design the owner asked for, unless Q3's range against Q lies wholly above
zero.

**The production path.** The local replay cannot read production's premarket rows and writes
nothing there. The brief spec's dry run (`BRIEF_NO_PERSIST=true`; approved, its code not on main,
run: `git grep` on main finds no `BRIEF_NO_PERSIST`) lets the deployed job build a past brief
without a write. Once it is on main and deployed, arm A's targets for a sample of stored sessions
are built by the deployed job and compared with the local build. Only arm A can be checked this
way: the deployed job reads its policy rows from production for the analysis date
(`gcp/premarket_brief.py:950-980`, read), and the other arms' rows exist only in the local copy.
The quarters are checked in production once, after the deploy, by a dry run of a stored session. Each dry run calls the model (Decision 11).

### Result as run on 2026-11-16 (a spike; the owner's basis)

**Where a reader stands.** The spike's code is not on main and not on any remote. It is two local
commits on the branch `spike/atr-quarter-targets` (21612e698) under
`docs/superpowers/spikes/2026-11-16-atr-quarter-targets/`; a spike opens no PR. Its outputs are
session files under
`/tmp/claude-0/-home-user/fa186a7b-7434-50ad-97db-844fe591fc0f/scratchpad/atr_exp/out/`
(`report_v1_side.txt`, `report_followup.txt`, the per-trade `arms_followup.csv`), which a cleanup
can clear. So a reviewer cannot open the result from the repo. It is recorded here as what the
owner saw and decided on, quoted from those two report files, not typed from memory. The
implementation PR is where it becomes reproducible (the done_when item).

**How it ran** (read in the spike's scripts): the production brief replayed with `BRIEF_AS_OF` into
a local database, model calls off, for every session from 2022-01-03 to 2026-11-10; every trade
scored by the production `resolve_plan` on `plan_inputs` of the stored basis; for the ATR arms
"only `targets` and `legs` of the PlanInputs change per arm". No bar walk was written. The arms
were therefore not built by a builder under the marks rule, which does not exist yet.

**Arm A reproduced.** `report_followup.txt`: "A   total  +176.75" over "trades 3463", against the
gap-edges spec's +176.8 R over 3,463 trades. Within 0.1 R, so the other arms may be read.

**Totals, quoted** (`report_v1_side.txt`; R; "range = 90%, whole days resampled 2,000 times, numpy
default_rng(7)"):

```
All                                n= 3463  A   +176.7  Q   +152.5  Q-A   -24.3 (-71.8, +21.8)  Q3   +129.7  Q3-A   -47.0 (-109.1, +12.4)
SPY                                n= 1161  A    +64.2  Q    +55.8  Q-A    -8.4 (-28.3, +10.8)  Q3    +44.4  Q3-A   -19.8 (-44.6, +4.6)
QQQ                                n= 1152  A   +114.0  Q    +92.4  Q-A   -21.6 (-43.3, +0.8)  Q3    +80.9  Q3-A   -33.1 (-60.2, -4.0)
IWM                                n= 1150  A     -1.4  Q     +4.3  Q-A    +5.7 (-15.3, +26.0)  Q3     +4.4  Q3-A    +5.8 (-21.4, +31.6)
```

**The other arms, quoted** (`report_followup.txt`, "per arm" and the "All" line; Q2 is the first
three marks with four legs, B1 and B2 the first two marks with level targets beyond, B3 one mark
and a level target with two legs, as the spike's `score_arms2.py` builds them):

```
A   total  +176.75 avg +0.0510 share R>0 43.4% R=0 0.0% worst -1.02 best +8.31 all legs stopped 41.7% any leg stopped 43.6% losing runs {'SPY': 10, 'QQQ': 10, 'IWM': 11} max drawdown 41.2R
Q   total  +152.49 avg +0.0440 share R>0 45.9% R=0 0.0% worst -1.02 best +4.97 all legs stopped 34.7% any leg stopped 43.5% losing runs {'SPY': 7, 'QQQ': 10, 'IWM': 11} max drawdown 37.8R
Q3  total  +129.72 avg +0.0375 share R>0 46.9% R=0 0.0% worst -1.02 best +4.93 all legs stopped 34.7% any leg stopped 43.3% losing runs {'SPY': 7, 'QQQ': 10, 'IWM': 11} max drawdown 36.4R
Q2  total  +148.82 avg +0.0430 share R>0 45.9% R=0 0.0% worst -1.02 best +4.97 all legs stopped 34.7% any leg stopped 43.6% losing runs {'SPY': 7, 'QQQ': 10, 'IWM': 11} max drawdown 37.8R
B1  total  +148.83 avg +0.0430 share R>0 45.8% R=0 0.0% worst -1.02 best +5.11 all legs stopped 34.7% any leg stopped 43.6% losing runs {'SPY': 10, 'QQQ': 10, 'IWM': 11} max drawdown 37.8R
B2  total  +151.09 avg +0.0436 share R>0 45.8% R=0 0.0% worst -1.02 best +5.11 all legs stopped 34.7% any leg stopped 43.6% losing runs {'SPY': 10, 'QQQ': 10, 'IWM': 11} max drawdown 37.8R
B3  total  +101.94 avg +0.0294 share R>0 51.1% R=0 0.1% worst -1.02 best +4.84 all legs stopped 34.7% any leg stopped 41.7% losing runs {'SPY': 9, 'QQQ': 9, 'IWM': 8} max drawdown 32.9R
```

Each arm minus A, all trades, from the same file: Q2 "-27.9 (-70.5,+13.4)", B1 "-27.9
(-67.3,+11.0)", B2 "-25.7 (-64.2,+13.1)", B3 "-74.8 (-149.3,-5.7)".

**Reach before the stop, quoted** (`report_v1_side.txt`, "share of entered trades whose leg sold at
the target"):

```
arm A: {'T1': '22.2%', 'T2': '3.8%', 'T3': '0.7%'}  stop on every leg: 41.7%  any leg stopped: 43.6%
arm Q (0.25, 0.50, 0.75, 1.00 ATR): {'T1': '52.3%', 'T2': '27.1%', 'T3': '12.8%', 'T4': '6.2%'}  any leg stopped: 43.5%  all four stopped: 34.7%
```

**T1 against the stop, quoted** ("from the trigger, risk = trigger to stop"): "under 1.5R on 93.1%
of 3463 trades; under 1.0R on 76.4%; median 0.69R; quartiles 0.49 / 0.98".

**A target just past a level, quoted** ("within 5 cents past a named level"): "all four targets
pooled: 318 of 13852 (2.3%); reached 30.8% against 24.4%", and "trades with at least one such
target: 8.8%". The spike used 5 cents, not the ticker's `level_cluster_atr` that measure 8 names.

**Read by this spec's own rule ("What keeps today's plan").**

- No arm's range against A lies wholly above zero. No arm was shown to be better than today's
  plan.
- Q's range spans zero overall and for each of SPY, QQQ and IWM. By this spec's rule that is "no
  worse, by this test". It is not "better": the best estimate is 24.3 R lower over 3,463 trades,
  and the owner chose Q knowing that.
- Q3, Q2, B1 and B2 span zero overall; each has QQQ wholly below zero and no second ticker, so none
  fails the rule. B3's range overall lies wholly below zero: B3 fails.
- Not part of the rule, and stated so the choice is read with it: in the latest six-month block,
  "2026-09-01 to 2026-11-10           n=  134  A    +33.0  Q    +16.8  Q-A   -16.2 (-33.6, -1.8)",
  Q's range lies wholly below zero; in the other ten blocks it spans zero. By side, calls
  "Q-A   -24.3 (-51.3, +1.7)" and puts "Q-A    +0.1 (-35.8, +37.1)".
- The shape differs as expected: Q sells T1 on 52.3% of trades against A's 22.2%, ends with every
  leg stopped on 34.7% against 41.7%, and its best trade is +4.97 R against A's +8.31.

**Limits of this run.** The first three were handed with the result and checked here as far as
each line says.

- The premarket window. The replay's premarket highs and lows were recomputed from the 04:00 to
  09:30 ET bars (the spike's `recompute2.log`: "recompute-premarket 2022-01-03..2026-11-10 tickers=SPY
  QQQ IWM candidates=3657"; the window read at `gcp/fetchers/fetch_market_data.py:384`, `:573`).
  The live brief is built from the 08:20 ET refresh (as relayed from a GCP read on 2026-11-16, not
  read here: `premarket-refresh-daily` 08:20 ET and `premarket-brief-daily` 08:30 ET on weekdays,
  no 09:20 run). So the replay's triggers know up to 70 minutes of premarket the live brief does
  not. The owner's "the live brief should be done at 820 and 920 with updates" is recorded
  (Authority) and left as an open item; no schedule is designed here.
- The triggers include the prior-close prints. The spike ran on main 97190ef4, before the brief
  spec's premarket rules and before the prior-close rule. The owner: "Fixing the prior close problem
  will help with triggers." Every arm shares those triggers, so the comparison between arms stands
  and the level of each total may move.
- Sessions. The replay holds 3,657 ticker-days over 1,219 sessions (counted in the spike's
  `premarket_analysis_v1.csv.gz`); the report says "ticker-days scored 3655  trades 3463", the two
  left-out days apart. The gap-edges spec states 1,212 sessions. The 3,463 trades fall on 1,212
  dates (counted in `arms_followup.csv`). Whether that is the whole of the difference was not
  checked.
- No trading costs, as the method says. Q sells four times where A sells three.
- Measures the Reported list asks for that the spike did not produce: the reach share of each mark
  from the Design 4 measure for arm A (5), waypoints by level name and segment (6), a target on a
  level's own cent (7), measure 8 at `level_cluster_atr`, and average win and average loss (9). The
  implementation PR owes them.

## Decisions for the owner

Each is written into the text as recommended. Decisions 1 to 12 were decided per the recommendation, owner 2026-11-16: keep the work moving; on 2026-11-17 the owner changed Decisions 1, 3, 10 and 12, as each says. Decision 13, added in the re-cut, is open for the owner. Each says, with the owner's own words where they bear on one. A
production step inside a decision (applying schema, applying policy rows, a deploy, a dry run that
spends) stays a step the owner approves at the time it is run, exactly as written. The alternatives
stay written as the record of what was not chosen.

1. **The marks are a policy row seeded with the quarters for every date, so the merge is the
   swap.** Changed by the owner, 2026-11-17: "I want thirds removed from everything in the data" and
   "It should be everywhere, even historical". r2 recommended an empty seed and later-dated swap rows
   so earlier sessions replayed as they were; the owner wants earlier sessions on the quarters too,
   which Design 12 rebuilds. The marks stay a policy row, not code, so arm A is scored on the same
   code with a local empty list and the fractions are no literal. Alternative, r2's: empty seed and
   dated swap rows.
2. **Arm Q3's last third.** Decided per the recommendation, owner 2026-11-16: keep the work
   moving. The owner chose quarters ("Quarters not Thirds anymore"), so Q3 is a comparison arm
   only. Recommended reading: a third at each of 25, 50 and 75 percent, any
   unreached leg held to the close or the stop. Alternative reading: sell a third at 25 and at 50
   and hold the last third to the close or the stop with no 75 exit (marks `[0.25, 0.5]` with a third held). r2 allowed it at no design cost; r3's leg rule, one leg a mark,
   no longer does, so it would need its own design.
3. **Reach counts are read across the rule versions that share the trigger and stop, so the
   marks version starts with history from 2022.** Decided by the owner, 2026-11-17: "Yes" to the
   hit rates on these lines with history back to 2022, and "When I did thos in thirds it was able to
   go back". r2 had decided the other way (counts per rule version, starting at `no history yet`)
   on the rule that rates never mix rule versions; that rule still holds for the movement
   statement's rates, which read target slots (Design 6). The counts read only the trigger, the
   stop, the ATR and the bars, so the one helper `entry_rule_version` says which versions share
   them, and the "Rule version and stored briefs" item pins that the marks version's trigger and
   stop equal the level rule's. Alternative, r2's: per rule version, `no history yet` until
   sessions build up.
4. **No snapping: a target a few cents past a level stays where the arithmetic puts it**, and the
   level prints as a waypoint (IWM puts T1 274.64 just past PDL/PWL 274.665). Decided per the
   recommendation, owner 2026-11-16: keep the work moving. Whether such marks
   are reached less often is measure 8 of the Experiment; the spike found them on 2.3% of targets
   and reached no less often (Result as run). Alternative, only on that evidence: pull
   a mark back onto a level within the cluster distance, as a later change with its own arm.
5. **Waypoint zones use the ticker's existing `level_cluster_atr`.** Decided per the
   recommendation, owner 2026-11-16: keep the work moving. Recommended: no new number and
   already per ticker. On the example it prints PDO and PDH as one zone and PMC alone. Alternative:
   a new display key seeded at the owner's earlier 0.10 x ATR, which would print PDO, PDH and PMC
   as one zone; or no zones at all, every level its own line, as the owner's example lists them.
6. **The brief's existing `ATR levels` line is not printed for a side built under the marks**, so
   under r3, every side being built under them, the line leaves the brief.
   Decided per the recommendation, owner 2026-11-16: keep the work moving. Recommended: that line's rungs hang from PDH, PDL, PMK_H and PMK_L in half-ATR steps, so on IWM
   it would print 280.73 (PMK_L+1) beside T1 280.14, two different ATR ladders in one brief. The
   rungs are still built and recorded in `level_basis`, so nothing that reads them changes.
   Alternative: keep the line, renamed so it cannot be read as the targets.
7. **The merge waits for the under 1.5R rule.** Decided: the owner decided the reward is judged on
   the average of the plan's targets; it is specified in the conviction spec
   (`docs/superpowers/specs/2026-11-16-feat-insight-001-conviction-reachable.md`). What N2 reads is
   therefore settled as a decision. The merge, which is now the swap, still follows that change being deployed, or the owner accepts a warning on nearly every plan when giving the yes to merge (Design 9). As recommended: do not merge until
   the conviction spec has settled what N2 reads on a four-target plan, or the owner accepts a
   warning on nearly every plan. Alternative: swap on the Experiment alone.
8. **The insight's Discord line, the site's two target fields and the chart's three lines are
   changed under FEAT-INSIGHT-001 and in solyra, before the merge, not in this spec's PR.**
   Decided per the recommendation, owner 2026-11-16: keep the work moving. Recommended: those files belong to other capabilities, and before the merge no row can hold four
   targets. Alternative: change `gcp/insight_discord_push.py:221` in this PR.
9. **Merge order: the brief spec's branch first, then this one, with the hit-rates build before
   this one (r3).** Decided per the recommendation,
   owner 2026-11-16: keep the work moving, and with the prior-close change between the two: the
   brief spec's branch, then the prior-close change, then this one, so the rule version is numbered
   once (Design 6). Recommended, so the helper and v4
   exist once and the production dry run is available. Alternative: this first, adding the helpers
   here.
10. **No swap rows.** Changed by the owner, 2026-11-17 (Decision 1): the seed is the quarters, so
    the implementation PR's merge, on the owner's yes after the Experiment, applies them and a fresh
    database equals production. Alternative, r2's: swap rows in their own small PR on a second yes.
11. **Dry-run sample: five stored sessions**, about five briefs' model calls. The sample size is
    decided per the recommendation, owner 2026-11-16: keep the work moving; each dry run is a
    spend on the deployed job and stays a step the owner approves when it is run. Alternative: none,
    relying on the local replay alone.
12. **Gate targets are the quarters.** Changed by the owner, 2026-11-17: "Yes" to switching the live
    alerts to the four quarters in the same change. The signal monitor's T1, its put re-anchor, the
    `t1..t4` columns and the movement statement's slots read the four marks (Design 11), so "T1"
    means one thing on every surface. r2's recommendation, kept as the record: gate targets stay the
    next three levels, with the two meanings of T1 a known cost.
13. **The model's stored brief text is kept as published.** Open for the owner. Design 12 rebuilds
    the deterministic `playbook` text from the rebuilt basis, but `llm_playbook` is what the model
    wrote and what was sent on the day, and writing it again would take one model call a row and
    still not be what was sent. Recommended: keep it, archived as well, as the record of what went
    out; nothing scores from it (Design 12). Alternative: generate it again on the quarters, about
    3,700 rows of model calls, each run on the owner's yes.

## Conflicts with the code and with approved specs

Found while reading; none is resolved silently.

1. **Three other approved FEAT-STRAT-001 specs describe the rule this replaces for new briefs.**
   Exits in thirds (2026-11-11: thirds, the spacing), ATR levels (2026-11-11: an ATR price is
   display only, never a target) and gap edges (2026-11-15: gap edges join the target walk).
   `supersedes` names one spec, and each of those still describes code that stays: the level rule
   for arm A and, until Design 12 rebuilds them, the stored bases; the rungs; the gap levels. They stay
   approved as the record of the level rule. From the merge their target rules no longer describe new briefs, and from Design 12 no stored row. The owner may prefer them marked superseded in turn; the gate allows one
   target per new spec. The owner, 2026-11-16: "Update after we finalize experiments and target
   implementation." So they are left as they are for now, and updating them is its own change
   after the implementation and its Experiment.
2. **The superseded spec quotes the owner: "The levels are always targets and the ATR levels
   enhance them" and "keep thirds".** Today's decision reverses both. That is the reason for the
   supersession.
3. **The insight spec quotes the owner: "Use the brief's level-based targets"** and its D3 fixtures
   pin level targets for 2026-11-16. Its rule, the insight follows the row, still holds; the words
   "level-based" stop being true for a marks-version row. Its fixtures are v3 rows and are unaffected.
4. **Rule N2 (first target under 1.5R)** would warn on nearly every plan (Design 9). The owner
   decided it is judged on the average of the plan's targets; the conviction spec specifies it.
5. **The 2026-11-08 ruling: values are tailored per ticker through calibration.** The four
   fractions are one list for all tickers. They scale with each ticker's own ATR, and they are a
   policy row, but they are not calibrated per ticker.
6. **Two meanings of T1.** Removed by Decision 12 as changed on 2026-11-17.
7. **`resolve_plan` cuts targets beyond the leg count without a word** (`:545`, run). A marks
   side's leg count is its number of marks (Design 2), so no target is cut; the cut itself is left
   as it is for a level-rule basis.
8. **The spacing seed and the first mark are both 0.25 x ATR.** Today's rule keeps a target only at
   or beyond 0.25 x ATR on the evidence of the exits spec; T1 sits exactly on that line and never
   beyond it. Not a contradiction, but the Experiment's hypothesis should be read with it in mind.
9. **The hit-rates spec (r1, 2026-11-16) printed a separate ladder of rungs under each plan.** Its
   r2 (2026-11-17) drops that block and puts the counts on the target lines, the lines this spec
   prints, so the brief has one set of targets. r2 of this spec stored its own reach columns; this
   revision reads that spec's table instead (Design 4). Merge order: the hit-rates spec r2 and its
   build, then this one.

## Expected effect

At the merge and deploy, each on the owner's yes: every new brief prints four targets at 25, 50, 75
and 100 percent of ATR from the trigger and sells a quarter at each; the levels print between them by
name; a target on a level is called the stronger case; the alerts' T1 state, the put re-anchor and
the movement statement's slots read the quarters; a `BRIEF_AS_OF` replay of any past session builds
the quarters; the insight, once its own spec is in, shows the same four.

After Design 12: every stored brief row back to 2022 shows the quarters with its outcome resolved on
them, and the old values sit in `premarket_targets_archive`. After Design 13: no column or policy row
holds thirds.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new
lines. Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may
describe this implementation, as backend source and local tests only.

After the merge, separately and never as a pre-merge box:

1. The merge itself, on the owner's yes after the Experiment is shown, applies the seeded row and
   the nine columns (Design 5). Confirm by a read that the row exists and the columns are present.
2. Deploy on the owner's yes, readers first (Design 11): the resolver, the signal monitor, the API
   and the insight pipeline, then the brief. Confirm by a dry run of
   a stored session (Decision 11), then on the next live brief, that each side prints its four
   targets at the marks and records the marks version (Design 6), and that the monitor's T1 state
   reads the 25 percent mark.
3. Design 12's PR and run, each writing mode on the owner's yes when it is run; verify reads clean.
4. Design 13's PR, merged on the owner's explicit yes to the drop.
5. Mark the superseded spec `superseded` in the change that sets this one `approved`. Done in that
   change: its `status` line is the only edit to it.
6. Complete the DOC close-out as the product-delivery skill prescribes.

## Risks

- **Q scores below today's plan.** Close first sales cost R in the earlier evidence. The Experiment is the gate: the merge waits for the owner's yes on its result. As run:
  Q made 24.3 R less than A over 3,463 trades with a range that spans zero, and the owner chose Q
  (Result as run).
- **Nearly every plan carries an N2 warning.** Decision 7.
- **A first sale 0.25 x ATR from the entry is inside the noise of the entry bar on a wide bar.**
  Targets count only from the bar after the fill bar (`resolve_plan`, `gcp/premarket_playbook_resolver.py:577-580`), so a same-bar
  touch is not a sale; measure 4 shows how often T1 is hit.
- **Two ATR ladders in one brief.** Decision 6 removes the old line.
- **A rebuild that moves a trigger or a stop.** Rebuild refuses such a row and lists it, and verify
  counts zero (Design 12).
- **Rewriting history is a large production write.** Archive first with matching counts, restore
  tested locally on every rule version, each writing mode on the owner's yes, and the drop only
  after verify reads clean (Designs 12 and 13).
- **The alerts' T1 moves closer to the trigger.** `post_t1` now means past the first quarter, so
  more fires may be held back as past T1. The Design 12 alerts replay shows how many before the
  drop.
- **Deploy order.** Code before rows leaves every side without targets for that run, because a
  missing marks row is not ok and there is no fallback. The merge applies the rows before any
  deploy (Design 5), and close-out step 1 checks it.
- **Version handling.** A reader that compares the version directly would treat a marks-version row as
  unknown. The brief spec's meta test, extended by Design 6, catches it.
- **Counts from before the merge.** The lines count trades back to 2022 that were taken under the
  level rule's exits. Reach before the stop does not depend on the exits, only on the trigger and
  stop, which are the same; a later rule that moves either gets its own entry version.
- **Longer briefs.** About two to six more lines a side. The playbook is split at line breaks
  (`gcp/premarket_brief.py:2820-2852`); whether the split falls well was not checked.

## What was not verified

- Production: nothing was read or written. The stored 2026-11-16 rows, the ATR 4.874951, the
  `level_cluster_atr` of about 25 cents and the "Today" text come from the superseded spec, which
  read them.
- Whether the stored IWM basis holds levels in range beyond those in the owner's example.
- The median stop distance of about 0.4 x ATR: handed, measured by another session. The spike's
  report gives 0.36 on its 3,463 trades.
- The owner's words: relayed to this session and to the one that recorded the decisions; the chat
  was not read.
- The spike's result: quoted from its two report files; the spike was not run again for this
  record, and its three stated limits were checked only as far as each says. The scheduler times
  beside them were relayed, not read.
- Whether a v4 row exists when the prior-close change deploys, and so which number the marks
  version takes: not known until then (Design 6 names both cases).
- Open item, not designed here: the owner's "the live brief should be done at 820 and 920 with
  updates" against the schedule as relayed.
- That the lane's bar files and local schema copy used by the gap-edges Experiment still exist.
- The other session's notes quoted under Experiment (+80 R, +90.5 R).
- The live `apply-schema-on-change` trigger: only its config file was read.
- PR #2009's number and state: no GitHub access; the branch was read at c6b58201.
- `lib/agents/orchestrator.py` (that a warn bars high conviction): taken from the insight spec.
- Which assertions in each listed test file need a new case; `gcp/queries/nan_triage.sql`'s origin.
- solyra beyond the three lines cited; how solyra renders an insight with four targets.
- How the longer playbook splits across Discord messages; the latency of the reach-history read.
- Whether a canvas depicts the brief: `docs/product/canvases.yml` was searched for brief, strat and
  dashboard and gave no match; the canvases were not opened.
- The "After" text: derived by this spec, not produced by an implementation.

## Catalog row and requirements

`docs/product/02-FEATURE-CATALOG.md:23` (read):

> | [FEAT-STRAT-001](#feat-strat-001) | STRAT / levels | Candle classification, FTFC, structural levels | `/charts`, `/live` | via `lib/` | `strat_levels`, `strat_combo_results`, `level_param_policy`, `ticker_level_params` | Production but needs remediation | P0 | 1 | 5 | [#866](https://github.com/TeneikaAskew/stocks/issues/866) [#908](https://github.com/TeneikaAskew/stocks/issues/908) [#907](https://github.com/TeneikaAskew/stocks/issues/907) [#884](https://github.com/TeneikaAskew/stocks/issues/884) |

From `docs/product/01-PRODUCT-REQUIREMENTS.md` (read): REQ-PLAYBOOK-001 (a plan shows entry,
invalidation and targets), REQ-DATA-001 (no silent empty result, no defaulted financial field),
REQ-REL-001 (live and replay pass shared parity fixtures) and REQ-REPLAY-001 (every what-if runs
through a production replay path).
