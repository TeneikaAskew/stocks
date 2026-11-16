---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001, REQ-REPLAY-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy rows: gcp/schema.sql seeds two new level_param_policy rows, each effective 2015-01-02 with ON CONFLICT DO NOTHING and each reproducing today's plan: plan_target_marks_atr (method_id policy, extra {\"marks\": []}) and ladder_history_sessions (policy, extra {\"sessions\": 250}); no existing row changes and exit_legs stays {\"legs\": 3}; lib/strat_levels.py names each key once and both join POLICY_WIDE_KEYS; policy_wide_param gives plan_target_marks_atr status ok with value equal to the number of marks when the list holds only numbers, each above zero and each above the one before it (ok with value 0 for an empty list), and input_unavailable for a missing list, an entry that is not a number, an entry at or below zero, a repeat or a falling order, and gives ladder_history_sessions ok for a whole number of at least 1 and input_unavailable otherwise; tests in tests/lib/test_level_params_loader.py assert all of it on the seeded policy loaded from gcp/schema.sql and fail on origin/main, which has neither key"
  - "ATR marks are the targets: tests/lib/test_strat_levels.py passes a TestAtrMarkTargets class on the three stored 2026-11-16 bases (Design 7 fixtures) rebuilt with plan_target_marks_atr [0.25, 0.5, 0.75, 1.0] and exit_legs 4: IWM calls targets are 280.14, 281.36, 282.58 and 283.79 and IWM puts 274.64, 273.42, 272.20 and 270.99; for every side of SPY, QQQ and IWM each target equals the trigger in cents plus (calls) or minus (puts) price_cents(mark x ATR), with ATR the basis's own value for its atr_basis, computed in the test from the fixture and not by the builder; each target records its mark, its share label and source atr_mark; the trigger, the stop and gate_targets of every side equal what origin/main gives for the same basis (IWM calls 278.92 PMK_H with stop 275.86 PMK_L, IWM puts 275.86 PMK_L with stop 277.41 PQL); no target is moved onto a level (IWM puts T1 is 274.64, never 274.67); skipped is empty; with marks [0.25, 0.5, 0.75] and exit_legs 3 each side has the first three of those targets; with more marks than legs, with a marks row that is not ok, with two marks on one cent, with a mark whose offset is zero cents, or with a puts mark at or below zero cents the side publishes no target and target_status carries input_unavailable or the row's status; with the seeded empty list every side's targets, skipped list, target_status and brief text equal origin/main's; the non-empty cases fail on origin/main"
  - "Waypoints and the stronger case: on the same bases each side built under the marks records plan_waypoints: every level of the basis's levels strictly past the trigger on the side's own side, one entry a cent with every name on that cent, in price order outward, out to the last target and past it only inside the side's trigger window, each entry with price, names, segment (before_t1, t1_t2, t2_t3, t3_t4 or beyond), distance_atr from the trigger and, where levels are grouped, zone with far_price and members; the test computes the expected list from the fixture's levels independently of the builder and also asserts by name and price that IWM calls holds PDO 278.95, PDH 279.17 and PMC 279.33 before T1, CMO 281.64 between T2 and T3 and PMH 285.26 beyond, and IWM puts holds PDL 274.67 before T1, 11/9 Gap Low 274.55 between T1 and T2 and PML 269.88 beyond; a target on a level's own cent records on_level with the level's names (IWM calls T4 283.79 records PWH) and that level is not also a waypoint; a level one cent from a target is a waypoint and the target records no on_level; levels within the ticker's level_cluster_atr x ATR in cents of a group's nearest level print as one zone, equal joins, a zone never spans a target, and with level_cluster_atr not ok every level is its own entry and waypoint_zone_status carries the status; the tests fail on origin/main (no plan_waypoints)"
  - "Brief copy: tests/lib/test_strat_levels.py passes golden-string tests on the stored IWM 2026-11-16 basis with the Design 7 reach histories and bias bearish: with the seeded policy the CALLS and PUTS blocks are exactly the text origin/main prints for that basis; with marks [0.25, 0.5, 0.75, 1.0] and exit_legs 4 they are exactly Design 7's After text; with marks [0.25, 0.5, 0.75] and exit_legs 3 the share reads 1/3 and the last target line reads 'sell the last 1/3, or hold to the close or the stop'; a side whose reach history is empty prints 'no history yet' on each line and never '0 of 0'; a side built under the marks prints no 'Skipped, closer than' line and, under Decision 6 as recommended, no 'ATR levels' line, while NEXT LEVELS Calls and Puts lines and PMG ZONES are unchanged; a side whose marks row or leg count is not ok prints the existing 'Targets unavailable ({status}): no exit plan for this side.' line and no target; the new goldens fail on origin/main"
  - "Rule version and stored briefs: a basis built under a non-empty marks list records rule_version feat-strat-001.v5 and a basis built under the empty list records the level rule's version that origin/main holds on the PR's merge base; tests/gcp/test_level_basis.py passes tests that (a) a stored basis of the level rule, with params that record neither new key and with params that record both, rebuilds through SessionLevels.from_basis with targets, skipped list, target_status and brief text equal to origin/main's, and the marks key is never checked for it, (b) a v5 basis rebuilds the same four targets, waypoints and text from the marks and leg count it recorded after the policy rows change, and (c) gcp.premarket_playbook_resolver.plan_inputs on a v5 basis returns the four target prices in order, legs 4 and plan_available true, and on a level-rule basis what origin/main returns; tests/lib/test_movement_statement.py passes a test that with resolved rows of the level rule and of v5 in the population a v5 session's rates count v5 rows only and a level-rule session's count its own version only, and that _new_rule_mark returns the cleared mark for a v5 basis; no file under lib/, gcp/ or platform/ compares a value with a rule version constant outside the helpers named in Design 6 and the population lines of lib/movement_statement.py"
  - "The fourth target is stored and scored: gcp/schema.sql adds nullable calls_plan_t4_price and puts_plan_t4_price to premarket_analysis and to premarket_analysis_history, and nullable calls_plan_t4_hit_ts and puts_plan_t4_hit_ts to premarket_analysis; gcp.premarket_brief.structured_playbook_columns writes plan_t1 to plan_t4 and still writes t1 to t3 from the gate targets, and the persisted row carries them (tests/gcp/test_premarket_brief.py); tests/gcp/test_premarket_playbook_resolver.py passes a TestFourLegs class on synthetic 1-minute bars for a call with trigger 100.00, stop 99.00, targets 100.50, 101.00, 101.50 and 102.00 and four legs: all four reached gives exit 't1,t2,t3,t4', plan_r 1.25 and t4_hit_ts set; the stop after T2 gives 't1,t2,stop,stop' and plan_r -0.125; the mirrored put cases pass; resolve_one's UPDATE sets both t4 columns; every existing three-leg case of the file passes unchanged; the t4_hit_ts assertions fail on origin/main, where PlanOutcome has no such field"
  - "Reach history stored and read: gcp/schema.sql adds nullable calls_plan_mfe_atr and puts_plan_mfe_atr to premarket_analysis; tests/gcp/test_premarket_playbook_resolver.py passes a TestPlanMfe class on synthetic 1-minute bars for a call with trigger 100.00, stop 99.00 and basis ATR 2.00: entered, a high of 103.00 before a later stop gives 1.5; the bar that hits the stop does not count (its high of 104.00 is ignored, stop first); a high reached only on the fill bar does not count; never above the trigger after the fill gives 0.0; a side not entered, or a basis with no ATR, gives NULL; a stop-less entered side is measured to the close; a fill bar that also touches the stop gives 0.0 whatever follows; the mirrored put cases pass with trigger 100.00, stop 101.00 and ATR 2.00 (a low of 97.00 before a later stop gives 1.5); on a half day (2025-11-28, close 13:00 ET) a call whose high is 101.00 before 13:00 and 105.00 at 14:30 gives 0.5; resolve_one's UPDATE sets both columns and RESOLVER_VERSION changes; tests/gcp/test_premarket_brief.py passes a test that the brief reads the reach history for all its tickers in one query, bounded to ladder_history_sessions analysis dates before the session date, to rows whose value is not NULL and to rows whose level_basis rule_version equals the version of the basis being built, never a date on or after the session (a BRIEF_AS_OF run sees only earlier rows), and that a failed read raises instead of printing 'no history yet'; the tests fail on origin/main"
  - "No numbers and no names: tests/lib/test_level_params_structure.py passes unchanged (no new literal or module constant on the build_session_levels walk) and test_the_walk_reaches_the_rules_it_must_cover also asserts that the mark walk and the waypoint builder are reached from build_session_levels; tests/lib/test_level_params_copy.py asserts that no string literal in lib/strat_levels.py contains '25%', '50%', '75%', '100%', '1/4' or 'quarter'; the marks, the leg count and the history length are read only from LevelParams and level_param_policy, and the percent and share texts are formatted from those values"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger and stop rule, gate_targets and the t1..t3 columns, the opened-through rule, the entry cutoff, the level rule's spaced walk and thirds for every basis not built under the marks, the gap-edge rule for those bases, the ATR rungs and their thinning (TestAtrRungs, TestAtrRungsDisplayOnly), the NEXT LEVELS Calls and Puts lines, PMG zones, the signal monitor's fire decisions and put re-anchor, the movement statement's four slots, persona plans, the CALL/PUT pick and the resolver's existing outcome columns"
  - "Experiment through the production paths, before any production change of the plan: the implementation PR body shows, for SPY, QQQ and IWM over 2022-01-03 to 2026-11-10 on the gap-edges spec's ticker-days (one trade per ticker-day, the first side to cross its trigger, a same-bar tie is no trade, a day that opens past a trigger is no trade, half days cut at the exchange close, SPY 2025-04-09 and IWM 2026-06-26 left out), plan R from gcp.premarket_playbook_resolver.resolve_plan with inputs from plan_inputs on bases built by gcp/premarket_brief.py (BRIEF_AS_OF) into a local copy of the schema, never production, for the arms of the Experiment section: A today, Q four quarters at marks 0.25, 0.5, 0.75 and 1.0, and Q3 thirds at marks 0.25, 0.5 and 0.75; per arm every measure of the Experiment section's Reported list; arm A matches the gap-edges spec's +176.8 R over 3,463 trades to 0.1 R before any other arm is read; an arm whose 90% range against A lies wholly below zero overall, or for two of the three tickers, is reported as failing, and the swap rows of Design 8 are not proposed for it without the owner's explicit decision recorded on the PR"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the implementation PR, whose merge applies gcp/schema.sql to production, is merged only after the owner's yes to that merge, recorded on the PR; and the swap rows of Design 8 reach production only after a second yes given on the Experiment's results, recorded separately"
status: draft
supersedes: docs/superpowers/specs/2026-11-16-feat-strat-001-plan-always-three-targets-full-ladder.md
---

# The exit plan sells a quarter at 25, 50, 75 and 100 percent of ATR from the entry, and the levels are waypoints

## Authority

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

`status: draft`: the owner approves this spec. Approval of the spec approves the direction and the
build behind policy rows that reproduce today's plan. It does not change the live plan: the rows of
Design 8 do, and they wait for the Experiment and a second yes.

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
- reach history: one stored number a side from which every target and waypoint gets a count
  (Design 4);
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
- No change to the signal monitor, its fire decisions or its put re-anchor. It reads `gate_targets`
  (`gcp/signal_monitor.py:539`, read), which this spec does not touch.
- No change to the gate targets or the `t1..t3` columns, and none to the movement statement's four
  slots, which are those columns (`lib/movement_statement.py:251`, read).
- No snapping of a target to a nearby level (Design 2; Decision 4).
- No breakeven or trailing stop.
- No change to the insight's risk rules. The under 1.5R rule is a dependency, stated in Design 9,
  not decided here.
- No solyra change in this spec's PR. What the site assumes about three targets is listed in
  Design 9.
- No per-ticker calibration of the four fractions (Conflicts, item 5).
- Filling the reach history from replays. It starts with the first session resolved after deploy.

## Approaches considered

1. Chosen: the marks are one policy-wide row; a side built under a non-empty list takes its targets
   at trigger plus or minus mark x ATR; levels become waypoints; a basis built that way records a new
   rule version. The seeded row is empty, which is today's plan, so the merge changes no target and
   the Experiment can score both rules on one code base.
2. Switch in code with no policy row. Rejected: a `BRIEF_AS_OF` replay of a session before the swap
   must rebuild that session's plan as it was (CLAUDE.md 3.5, 3.6), the Experiment needs arm A and
   arm Q from the same code, and the fractions would be literals in code against the standing ruling.
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
  spacing. The signal monitor and the `t1..t3` columns read these. Unchanged.

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
- The number of targets is the number of marks. The share sold at each is 1 / `exit_legs`, as today
  (`lib/strat_levels.py:3205`, read). A list longer than `exit_legs` publishes no target with
  `target_status` `input_unavailable`: `resolve_plan` would otherwise cut the extra targets without
  saying so (`targets[:plan.legs]`, `gcp/premarket_playbook_resolver.py:545`; run, see Design 5). A
  list shorter than `exit_legs` leaves the remaining legs held to the close or the stop, which is
  what `resolve_plan` already does for a leg with no target (`:566`).
- **No snapping.** A target is never moved onto a level. IWM puts T1 is 274.64 with PDL at 274.665
  (274.67 to the cent, run); the level prints as a waypoint just before it.
- Keys checked first, as `_plan_targets` does today (`:2836-2855`): `plan_target_marks_atr`,
  `exit_legs` and `entry_cutoff_et`. One that is not ok publishes no target and records its status.
  Two marks that land on one cent, an offset of zero cents, or a puts mark at or below zero cents
  give `input_unavailable`. There is no fallback to the level walk (CLAUDE.md 3.7).
- `skipped` is empty: nothing is passed over. `target_min_spacing_atr` and
  `plan_target_level_types` are not read for this side's targets.
- `plan` records the marks, each mark's price, the ATR and its basis, the leg count and the entry
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
reason line for the side. So no mark is ever built without an ATR, and none is invented. A side with
a trigger whose marks row or leg count is not ok prints the existing line `Targets unavailable
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

### 4. Reach history: what must be stored

One number a side: `{calls,puts}_plan_mfe_atr`, nullable `DOUBLE PRECISION` on `premarket_analysis`
beside the plan columns (`gcp/schema.sql:1987-2004`, read), written by the resolver for a side whose
`plan_entry_status` is `entered`: the distance travelled in the side's direction from the bar after
the fill bar until the bar in which the stop is hit (that bar not counted, stop first, as the plan
scores) or the last bar before the exchange's close, floored at 0 and divided by the basis ATR. For
calls the distance is the highest high minus the trigger; for puts the trigger minus the lowest low.
The bars are the resolver's `plan_bars`, cut at `session_close(analysis_date)`
(`gcp/premarket_playbook_resolver.py:764-765`, read). The stop is looked for from the fill bar
itself, as `resolve_plan` does (`:573`, read): a fill bar that also touches the stop closes the
position and the measure is 0.0. NULL for a side not entered or a basis with no ATR.
`RESOLVER_VERSION` (`:100`) moves.

From it every line's count follows without storing lines: a mark or waypoint `d` x ATR past the
trigger was reached before the stop on the sessions whose value is at least `d`, where `d` is the
line's distance in cents over the ATR. A 25% mark is reached on the sessions whose value is at
least about 0.25. Because each session rounds its own offsets to the cent, a count can differ from
that session's stored `plan_t1_hit_ts` by one cent's rounding; the count is of sessions that went at
least as far as today's line.

The brief reads, in one query for all its tickers, the values of the last
`ladder_history_sessions` analysis dates before the session date (new policy-wide key, extra
`{"sessions": 250}`), **only from rows whose `level_basis` rule version equals the version of the
basis being built** (Design 6), and prints `reached k of n` on each target and waypoint line: n the
side's entered sessions in that span, k those that went at least that far. Counts, never a percent.
Zero rows prints `no history yet`. A failed read raises (CLAUDE.md 3.7). A `BRIEF_AS_OF` run reads
only earlier dates. `ladder_history_sessions` not ok prints `reach history unavailable ({status})`
and changes no target.

### 5. The fourth target: every place three slots are assumed

`resolve_plan` already scores any number of legs: on main, with four targets and `legs=4`, a call
that reaches all four gives exit `t1,t2,t3,t4` and R 1.25, and a stop after T2 gives
`t1,t2,stop,stop` and R -0.125 (run in this session against `main` 97190ef4). With `legs=3` the same
four targets give `t1,t2,t3` and the fourth is cut without a word (run). What is fixed at three is
the storage and the display:

| Place | File and line (read) | What changes |
|---|---|---|
| Leg count | `gcp/schema.sql:2298` (`exit_legs` `{"legs": 3}`); read at `lib/strat_levels.py:2857`, `:3205` | The seeded row stays. A later-dated row `{"legs": 4}` is one of the swap rows (Design 8). |
| Plan target price columns | `gcp/schema.sql:1900-1905` (`premarket_analysis`), `:2166-2171` (`premarket_analysis_history`) | Add nullable `calls_plan_t4_price`, `puts_plan_t4_price` to both tables. |
| Plan target hit columns | `gcp/schema.sql:1992-1994`, `:2001-2003` | Add nullable `calls_plan_t4_hit_ts`, `puts_plan_t4_hit_ts`. |
| Reach columns | new, beside `gcp/schema.sql:1987-2004` | Add `calls_plan_mfe_atr`, `puts_plan_mfe_atr` (Design 4). |
| Writing the price columns | `gcp/premarket_brief.py:1561-1565` (`for k in (1, 2, 3)` for both `t` and `plan_t`); `:3748-3753` (the persisted row) | `plan_t` goes to 4; `t` stays 1 to 3 (gate targets). The persisted row gains the two `plan_t4` values. |
| Plan outcome | `gcp/premarket_playbook_resolver.py:146` (`PlanOutcome.t3_hit_ts`), `:550-553` (`targets[:3]`, three slots), `:877-878` (`_PLAN_FIELDS`) | Add `t4_hit_ts`; the hit walk covers four targets; `_PLAN_FIELDS` gains `t4_hit_ts`, which carries it into the UPDATE (`:843`). |
| Plan inputs | `gcp/premarket_playbook_resolver.py:591-640` | A v5 basis is read like today's current rule: targets by price, legs and cutoff from the side's `plan` (`:611-624`). The v2 fallback's `(1, 2, 3)` (`:636`) reads the gate columns and does not change. |
| Legs cut | `gcp/premarket_playbook_resolver.py:545` | Unchanged; Design 2 refuses more marks than legs so nothing is cut silently. |
| Brief text | `lib/strat_levels.py:3173-3227` (`_plan_block`) | Design 7. The share `1/{legs}` and the last-leg wording are already built from the leg count (`:3205-3219`). |
| Discord | `gcp/premarket_brief.py:2820-2852` (`_playbook_code_fields`), `:2854-2900` | No change: the playbook is the text, split at line breaks with nothing cut (read). The embed's docstring says "T1/T2" (`:2855`); wording only. How the longer text splits across messages was not checked. |
| Movement statement | `lib/movement_statement.py:251` (`_REACH_SLOTS`), `:286-349`, `:406-490` | No fourth slot: its slots are the gate columns `t1..t3`, which stay level-based. What changes is the version handling (Design 6). |
| Signal monitor | `gcp/signal_monitor.py:539-549`, `:576-583` | None (non-goal). |
| Insight plan, stocks | `lib/agents/schema.py:241-244` ("Up to 3 price targets", a description, no length limit); `gcp/insight_discord_push.py:221` (`targets[:3]`); `lib/agents/trade_planner.py:284-287` | Not changed by this spec's PR (Design 9, Decision 8). |
| Insight plan, solyra | `src/components/insights/redesign/Panels.tsx:79-80` (Target 1 and Target 2 only); `src/routes/AiInsightsLovablePage.tsx:108` (`slice(0, 3)`), solyra `main` 80c82c2 | Not changed by this spec (Design 9, Decision 8). |
| Tests and fixtures that hold three legs or `t3` columns | `tests/lib/test_strat_levels.py`, `tests/lib/test_session_levels_rules.py`, `tests/lib/level_params_fixtures.py`, `tests/lib/test_level_params_loader.py`, `tests/lib/test_movement_statement.py`, `tests/lib/test_movement_statement_level_basis.py`, `tests/gcp/test_level_basis.py`, `tests/gcp/test_level_params_consumers.py`, `tests/gcp/test_calibrate_level_params.py`, `tests/gcp/test_premarket_playbook_resolver.py`, `tests/gcp/test_premarket_brief_late_slot.py`, `tests/gcp/test_brief_channel_routing.py`, `tests/api/test_movement_statement_exit_plan.py`, `tests/fixtures/atr_levels_brief_base.json`, `tests/fixtures/atr_levels_display_only_base.json` (found by a search for `t3_hit_ts`, `t3_price`, `plan_t3`, `exit_legs`, `legs` 3 and `sell 1/3`, run) | They pin the level rule and three legs and keep passing unchanged, since the seeded policy keeps both. New cases are added beside them; the policy fixture `tests/lib/level_params_fixtures.py` gains the two new keys. Which assertions inside each file would need a new case was not checked file by file. |
| Other readers of the columns | `gcp/queries/nan_triage.sql:35-36`; `scripts/analysis/honest_scoring_experiment.py:323` | Not checked whether the triage SQL is generated or hand-kept, or whether it must list the new float columns. The analysis script reads three hit times and is not on a production path. |

**The schema change applies itself.** `gcp/cloudbuild/apply-schema-cloudbuild.yaml:1-5` says the
`apply-schema-on-change` trigger fires on a push to main that touches `gcp/schema.sql` and applies
that revision's schema (read; the live trigger was not read). The implementation PR adds two policy
rows and eight nullable columns (four `plan_t4_price`, two `plan_t4_hit_ts`, two `plan_mfe_atr`), so
merging it changes production. The merge is an owner-approved step: one question before merging,
the yes recorded on the PR. The seeded rows change no target, and a job still on the old image reads
a policy key it does not know as a ticker key with status `params_unavailable`, records it and
ignores it (`lib/strat_levels.py:1454-1496`, read).

### 6. Rule version, stored rows and rates

A basis built under a non-empty marks list records `rule_version` `feat-strat-001.v5`. A basis
built under the empty list records the level rule's version: `feat-strat-001.v3` on main today
(`lib/strat_levels.py:1516`, read), `feat-strat-001.v4` once the brief spec's B8b is on main
(`docs/superpowers/specs/2026-11-16-feat-playbook-001-brief-says-what-the-data-says.md`, approved,
done_when B8b and Design 4, read). So the version a row carries always names the rule that picked
its targets, whatever the date it was built on.

**The brief spec's helper.** B8b defines `lib.strat_levels.is_current_pick_rule(version)`, true for
v3 and v4 through `PICK_RULE_VERSIONS`, and a meta test that lets only that helper and the
movement statement's two population lines compare a value with the rule version (its plan, Task
B8b interfaces, read). The helper is not on main and not on
`origin/feature/feat-playbook-001-brief-says-what-the-data-says` at c328134b (run: `git grep` finds
no definition). v3 and v4 share one pick rule. v5 is a different pick rule, so:

- `is_current_pick_rule` answers what its four readers ask: "does this basis carry its own plan,
  cleared mark and version, to be read and rebuilt as recorded?" For v5 the answer is yes, exactly
  as for v3 and v4: `SessionLevels.from_basis` keeps the basis's own version
  (`lib/strat_levels.py:1968`), `_assemble` keeps it (`:2434`), `plan_inputs` reads the plan from the
  basis (`gcp/premarket_playbook_resolver.py:611`) and `_new_rule_mark` returns the cleared mark
  (`lib/movement_statement.py:499`). v5 joins `PICK_RULE_VERSIONS`.
- Which rule picks the targets is a second question, and it gets its own helper in
  `lib/strat_levels.py`, `plan_target_rule(version)`: `v2` for v2, `levels` for v3 and v4,
  `atr_marks` for v5, nothing else. `_pick_side` calls the level walk or the mark walk by it. The
  brief spec's meta test gains this helper as an allowed site, and no other comparison is added.
- A stored level-rule basis is rebuilt by the level walk with the values it recorded, and the marks
  key is never checked for it, even when its params record that key (the loader records every
  policy key once its row exists, `:1441`, `:1452-1456`). A v5 basis is rebuilt by the mark walk from the
  marks and leg count it recorded, so later policy rows leave it unchanged.
- If this change merges before the brief spec's B8b, the implementation adds both helpers itself
  with v3 where B8b would have v3 and v4, and B8b's branch then adds v4 to the two lists.
  Recommended order: the brief spec's branch first (Decision 9).

**Rates never mix rule versions.**

- The movement statement's reach rates select rows by `level_basis->>'rule_version'`
  (`lib/movement_statement.py:348`, `:366-368`, read). After B8b the bound value is the session
  row's own version. So a v5 session's rates count v5 rows only, and a v4 session's v4 rows only.
  Its slots are the gate targets, which v5 does not change, but the rule stays: one version, one
  population. v5 therefore starts with no resolved rows of its own.
- The reach counts of Design 4 are read only from rows of the same rule version as the basis being
  built. At the swap they restart at `no history yet` (Decision 3 gives the alternative).
- The Experiment's rates are per arm and never pooled across arms.

### 7. What the brief prints

For a side built under the marks, the plan block (`_plan_block`) prints, after the stop line:

```
    Targets at {p1}, {p2}, ... and {pn} of ATR({n}) = {atr} past {trigger}, sell {1/legs} at each
      {price or "near to far"} ({names}): level on the way, {d} ATR past the trigger, {reached k of n | no history yet}
    T{i}: {price} ({p}% of ATR[, on {names}: the stronger case]), sell {1/legs}, {reached k of n | no history yet}
      {price} ({names}): level beyond T{last}, {d} ATR past the trigger, {reached k of n | no history yet}
```

Waypoints print in price order between the target lines they sit between. The last target line
reads `sell the last {1/legs}, or hold to the close or the stop`, the wording main already prints
for a full plan (`lib/strat_levels.py:3216-3217`). The percents and the share are formatted from
the policy values; none is a literal. No `Skipped, closer than` line is printed, since nothing is
skipped. The `ATR levels` line of NEXT LEVELS is not printed for such a side (Decision 6). NEXT
LEVELS' Calls and Puts lines and PMG ZONES are unchanged. A basis built under the level rule prints
exactly what main prints.

**Fixtures.** The stored `level_basis` of `premarket_analysis` for 2026-11-16 (IWM, SPY, QQQ; the
superseded spec names the row built 2026-11-16T08:31:19 ET), copied verbatim into
`tests/fixtures/` by a read-only export the owner allows once (the superseded plan's Task 1 step 1,
not done). Rendered with bias `bearish`. Reach histories for the goldens: calls 0.1, 0.3, 0.4,
0.7, 1.1, 1.2, 1.6, 2.4; puts 0.05, 0.2, 0.3, 0.6, 0.9, 1.3, 1.5, 2.1. IWM: ATR(14) 4.874951;
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
the fixture histories, not produced by an implementation):

```
  CALLS above 278.92 (PMK_H) -- only if bias denied, new entries 09:30 to 16:00 ET
    No entry if the open is at or above 278.92.
    Stop: 275.86 (PMK_L)
    Targets at 25%, 50%, 75% and 100% of ATR(14) = 4.87 past 278.92, sell 1/4 at each
      278.95 to 279.17 (PDO, PDH): level on the way, 0.01 ATR past the trigger, reached 8 of 8
      279.33 (PMC): level on the way, 0.08 ATR past the trigger, reached 8 of 8
    T1: 280.14 (25% of ATR), sell 1/4, reached 7 of 8
    T2: 281.36 (50% of ATR), sell 1/4, reached 5 of 8
      281.64 (CMO): level on the way, 0.56 ATR past the trigger, reached 5 of 8
    T3: 282.58 (75% of ATR), sell 1/4, reached 4 of 8
    T4: 283.79 (100% of ATR, on PWH: the stronger case), sell the last 1/4, or hold to the close or the stop, reached 4 of 8
      285.26 (PMH): level beyond T4, 1.30 ATR past the trigger, reached 2 of 8
    Room to trigger: 0.92%

  PUTS below 275.86 (PMK_L), new entries 09:30 to 16:00 ET
    No entry if the open is at or below 275.86.
    Stop: 277.41 (PQL)
    Targets at 25%, 50%, 75% and 100% of ATR(14) = 4.87 past 275.86, sell 1/4 at each
      274.67 (PDL, PWL): level on the way, 0.24 ATR past the trigger, reached 6 of 8
    T1: 274.64 (25% of ATR), sell 1/4, reached 6 of 8
      274.55 (11/9 Gap Low): level on the way, 0.27 ATR past the trigger, reached 6 of 8
    T2: 273.42 (50% of ATR), sell 1/4, reached 5 of 8
    T3: 272.20 (75% of ATR), sell 1/4, reached 4 of 8
    T4: 270.99 (100% of ATR), sell the last 1/4, or hold to the close or the stop, reached 3 of 8
      269.88 (PML): level beyond T4, 1.23 ATR past the trigger, reached 3 of 8
    Room to trigger: 0.19%
```

If the fixture holds a level in range that the owner's example does not name, the golden is the
fixture's, and the difference is reported on the PR.

### 8. The rows that change the plan

The seeded rows change no target. After the Experiment and the owner's second yes, later-dated rows
turn the rule on, so sessions before that date replay as they were:

```sql
INSERT INTO level_param_policy (param_key, method_id, statistic_q, lookback_sessions, min_sample,
                                extra, effective_from, note)
VALUES ('plan_target_marks_atr', 'policy', NULL, NULL, NULL,
        '{"marks": [0.25, 0.5, 0.75, 1.0]}', :swap_date,
        'targets at these distances from the entry trigger / ATR, nearest first'),
       ('exit_legs', 'policy', NULL, NULL, NULL, '{"legs": 4}', :swap_date,
        'equal legs the exit plan sells, one at each ATR mark')
ON CONFLICT (param_key, effective_from) DO NOTHING;
```

The two rows carry one date and go in together: marks without the leg row would be four marks
against three legs, which Design 2 refuses. For arm Q3 the rows would be marks `[0.25, 0.5, 0.75]`
and no leg row. The values written are the ones the Experiment supports and the owner picks. How
the rows reach production is Decision 10.

### 9. The insight and the site: one plan

The approved insight spec
(`docs/superpowers/specs/2026-11-16-feat-insight-001-insight-one-plan-one-voice.md`) makes the
insight's plan the brief's plan: entry, stop and targets read from the side record the brief stored,
"the insight follows whatever the row holds" (its Scope and Non-goals, read). Its code is not on
main (`grep` finds no `read_stored_sides` or `compute_rule_flags`, run); on main the planner still
prices targets as R multiples of its own stop (`lib/agents/trade_planner.py:284-287`, read). Once it
lands, a v5 row gives the insight four targets with no further change, and that rule stands: the
brief's numbers and the insight's plan are one plan.

Three things then assume fewer than four, all outside this spec's PR (Decision 8):

- `gcp/insight_discord_push.py:221` prints `targets[:3]`.
- solyra `Panels.tsx:79-80` shows Target 1 and Target 2; `AiInsightsLovablePage.tsx:108` draws
  `slice(0, 3)`.
- `lib/agents/schema.py:241-244` describes "Up to 3 price targets" (text only).

**The under 1.5R rule: a dependency, not decided here.** Rule N2 warns when the first target is
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

That rule and its 1.5R line are under review in the draft conviction spec
(`docs/superpowers/specs/2026-11-16-feat-insight-001-conviction-reachable.md` on
`origin/docs/spec-feat-insight-001-conviction-reachable` at c6b58201, `status: draft`, read; the
task names it PR #2009, not checked). Its measurement grid tests the first target at 1.0R, 1.5R and
2.0R on the brief's present targets. This spec states the dependency and decides nothing: what N2
should read when the plan has four ATR targets is for that spec. The swap of Design 8 should not
happen until that is settled or the owner accepts the warning on nearly every plan (Decision 7).

### 10. Capacity and cost (CLAUDE.md rule 0)

- **Volume:** two policy rows; eight nullable columns; each new `level_basis` gains a waypoint list
  of about 3 to 10 entries a side (IWM 2026-11-16: 5 and 3 by the owner's example) and loses the
  skipped list.
- **Velocity:** one new query a brief run, for all tickers: at most `ladder_history_sessions` x
  tickers rows (250 x 3 = 750) of two numbers and the version filter, by the
  `(analysis_date, ticker)` unique index. No new query in the resolver.
- **Wall-clock:** one more round trip a brief run, about 0.5 to 2 s at the connector's speed. The
  read's latency was not measured.
- **Cost:** $0 scheduled; no new job or schedule. The Experiment runs on a local copy. Each
  production dry run of the brief costs one brief's model calls (Decision 11).

## Experiment

Run before any production change of the plan. It is not run by this spec and was not run by this
session. A separate helper is running an experiment on this design; what it runs was not read here.
Its result is context. The result that gates the swap is the one produced as written below, through
the production paths, on the implementation's code.

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

| Arm | `plan_target_marks_atr` | `exit_legs` | Sales |
|---|---|---|---|
| A, today | `[]` | 3 | thirds at the spaced level targets; a leg with no target held to the close or the stop |
| Q, quarters | `[0.25, 0.5, 0.75, 1.0]` | 4 | a quarter at each mark |
| Q3, thirds | `[0.25, 0.5, 0.75]` | 3 | a third at each mark; a leg whose mark is not reached is held to the close or the stop, as today's unsold leg is |

Q3's last third is read here as: sold at the 75% mark when reached, otherwise held to the close or
the stop like any leg today. Decision 2 names the other reading.

**Method.** The gap-edges spec's: every session from 2022-01-03 to 2026-11-10 for SPY, QQQ and IWM
replayed through `gcp/premarket_brief.py` (`BRIEF_AS_OF`) with history-mode parameters into a local
copy of the schema; one trade per ticker-day, the first side to cross its trigger; a same-bar tie
is no trade; a day that opens past a trigger is no trade; the 16:00 cutoff on main; half days cut
at the exchange close; SPY 2025-04-09 and IWM 2026-06-26 left out; each trade scored by
`gcp.premarket_playbook_resolver.resolve_plan` on `plan_inputs` of the arm's basis. No bar walk is
written for the test (CLAUDE.md 3.6). No trading costs. Arm A must reproduce +176.8 R over 3,463
trades to 0.1 R before any other arm is read. The trigger and stop are the same in every arm, so
the three arms trade the same ticker-days and differ only in exits.

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
two of the three tickers, fails this test, and the PR says so. The seeded rows then stay and the
brief keeps today's level targets, unless the owner decides otherwise on the evidence: the owner
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
The arm the owner picks is checked in production once, after the second yes, by a dry run of the
first session the swap rows cover. Each dry run calls the model (Decision 11).

## Decisions for the owner

Each is written into the text as recommended.

1. **The marks are a policy row and the swap is by dated rows, not a code switch.** Recommended, so
   earlier sessions replay as they were and both rules run from one code base. Alternative: switch
   in code at deploy, which is simpler to read and cannot replay an earlier session's plan.
2. **Arm Q3's last third.** Recommended reading: a third at each of 25, 50 and 75 percent, any
   unreached leg held to the close or the stop. Alternative reading: sell a third at 25 and at 50
   and hold the last third to the close or the stop with no 75 exit (marks `[0.25, 0.5]`, three
   legs, which Design 2 already allows); it can be run as a fourth arm at no design cost.
3. **Reach counts and rates are per rule version, so v5 starts at `no history yet`.** Recommended,
   because the standing rule is that rates never mix rule versions. Alternative: let the Design 4
   reach counts pool level-rule rows resolved after deploy with v5 rows, since that measure reads
   only the trigger, the stop and the ATR, which v5 does not change; it would need its own helper
   and test saying exactly which versions share an entry rule.
4. **No snapping: a target a few cents past a level stays where the arithmetic puts it**, and the
   level prints as a waypoint (IWM puts T1 274.64 just past PDL/PWL 274.665). Whether such marks
   are reached less often is measure 8 of the Experiment. Alternative, only on that evidence: pull
   a mark back onto a level within the cluster distance, as a later change with its own arm.
5. **Waypoint zones use the ticker's existing `level_cluster_atr`.** Recommended: no new number and
   already per ticker. On the example it prints PDO and PDH as one zone and PMC alone. Alternative:
   a new display key seeded at the owner's earlier 0.10 x ATR, which would print PDO, PDH and PMC
   as one zone; or no zones at all, every level its own line, as the owner's example lists them.
6. **The brief's existing `ATR levels` line is not printed for a side built under the marks.**
   Recommended: that line's rungs hang from PDH, PDL, PMK_H and PMK_L in half-ATR steps, so on IWM
   it would print 280.73 (PMK_L+1) beside T1 280.14, two different ATR ladders in one brief. The
   rungs are still built and recorded in `level_basis`, so nothing that reads them changes.
   Alternative: keep the line, renamed so it cannot be read as the targets.
7. **The swap waits for the under 1.5R rule.** Recommended: do not insert the Design 8 rows until
   the conviction spec has settled what N2 reads on a four-target plan, or the owner accepts a
   warning on nearly every plan. Alternative: swap on the Experiment alone.
8. **The insight's Discord line, the site's two target fields and the chart's three lines are
   changed under FEAT-INSIGHT-001 and in solyra, before the swap, not in this spec's PR.**
   Recommended: those files belong to other capabilities, and before the swap no row can hold four
   targets. Alternative: change `gcp/insight_discord_push.py:221` in this PR.
9. **Merge order: the brief spec's branch first, then this one.** Recommended, so the helper and v4
   exist once and the production dry run is available. Alternative: this first, adding the helpers
   here.
10. **The swap rows go into `gcp/schema.sql` through their own small PR**, merged on the second
    yes, so a fresh database equals production and the merge is the recorded approval. Alternative:
    insert them with `scripts/db_query_cr.sh --commit`, which leaves source and production apart.
11. **Dry-run sample: five stored sessions**, about five briefs' model calls. Alternative: none,
    relying on the local replay alone.
12. **Gate targets stay level-based.** The brief will print T1 to T4 as ATR marks while the signal
    monitor's legs and the movement statement's `t1..t3` slots stay the next three levels.
    Recommended for this change, since the monitor is a non-goal. The two meanings of "T1" on one
    site are a known cost; aligning them is its own spec.

## Conflicts with the code and with approved specs

Found while reading; none is resolved silently.

1. **Three other approved FEAT-STRAT-001 specs describe the rule this replaces for new briefs.**
   Exits in thirds (2026-11-11: thirds, the spacing), ATR levels (2026-11-11: an ATR price is
   display only, never a target) and gap edges (2026-11-15: gap edges join the target walk).
   `supersedes` names one spec, and each of those still describes code that stays: the level rule
   for every stored basis and every session before the swap, the rungs, the gap levels. They stay
   approved as the record of the level rule. From the swap date their target rules no longer
   describe new briefs. The owner may prefer them marked superseded in turn; the gate allows one
   target per new spec.
2. **The superseded spec quotes the owner: "The levels are always targets and the ATR levels
   enhance them" and "keep thirds".** Today's decision reverses both. That is the reason for the
   supersession.
3. **The insight spec quotes the owner: "Use the brief's level-based targets"** and its D3 fixtures
   pin level targets for 2026-11-16. Its rule, the insight follows the row, still holds; the words
   "level-based" stop being true for a v5 row. Its fixtures are v3 rows and are unaffected.
4. **Rule N2 (first target under 1.5R)** would warn on nearly every plan (Design 9).
5. **The 2026-11-08 ruling: values are tailored per ticker through calibration.** The four
   fractions are one list for all tickers. They scale with each ticker's own ATR, and they are a
   policy row, but they are not calibrated per ticker.
6. **Two meanings of T1.** Decision 12.
7. **`resolve_plan` cuts targets beyond the leg count without a word** (`:545`, run). Design 2
   refuses that input; the cut itself is left as it is.
8. **The spacing seed and the first mark are both 0.25 x ATR.** Today's rule keeps a target only at
   or beyond 0.25 x ATR on the evidence of the exits spec; T1 sits exactly on that line and never
   beyond it. Not a contradiction, but the Experiment's hypothesis should be read with it in mind.

## Expected effect

At deploy, with the seeded rows: every side's targets, plan R, gate targets and brief text are what
they are today; the resolver starts storing the reach number.

After the Design 8 rows: every side with a trigger and an ATR prints four targets a fixed share of
ATR apart and sells a quarter at each; the levels print between them by name; a target on a level
is called the stronger case; the insight, once its own spec is in, shows the same four.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new
lines. Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may
describe this implementation, as backend source and local tests only.

After the merge, separately and never as a pre-merge box:

1. The merge itself, on the owner's first yes, applies the two seeded rows and the eight columns
   (Design 5). Confirm by a read that the rows exist and the columns are present.
2. Deploy the brief and the resolver. Confirm the next live brief's targets and text equal what the
   previous image gives for the same basis (the seeded rows change none), and that re-resolving the
   latest sessions fills the two reach columns for entered sides.
3. Post the Experiment on the implementation PR or, if merged, on a new issue. On the owner's
   second yes, with Decisions 7 and 8 met, add the Design 8 rows with the values chosen and confirm
   by a dry run, then on the next live brief, that each side prints its targets at the marks and
   records `feat-strat-001.v5`.
4. Mark the superseded spec `superseded` in the change that sets this one `approved`.
5. Complete the DOC close-out as the product-delivery skill prescribes.

## Risks

- **Q scores below today's plan.** Close first sales cost R in the earlier evidence. The Experiment
  is the gate, and the seeded rows keep today's plan until the owner decides on its result.
- **Nearly every plan carries an N2 warning.** Decision 7.
- **A first sale 0.25 x ATR from the entry is inside the noise of the entry bar on a wide bar.**
  Targets count only from the bar after the fill bar (`resolve_plan`, `gcp/premarket_playbook_resolver.py:577-580`), so a same-bar
  touch is not a sale; measure 4 shows how often T1 is hit.
- **Two ATR ladders in one brief.** Decision 6 removes the old line for such sides.
- **Deploy order.** Code before rows leaves every side without targets for that run, because a
  missing marks row is not ok and there is no fallback. The merge applies the rows before any
  deploy (Design 5), and close-out step 1 checks it.
- **Version handling.** A reader that compares the version directly would treat a v5 row as
  unknown. The brief spec's meta test, extended by Design 6, catches it.
- **Thin history after the swap.** Counts print as counts, and `no history yet` when there are
  none.
- **Longer briefs.** About two to six more lines a side. The playbook is split at line breaks
  (`gcp/premarket_brief.py:2820-2852`); whether the split falls well was not checked.

## What was not verified

- Production: nothing was read or written. The stored 2026-11-16 rows, the ATR 4.874951, the
  `level_cluster_atr` of about 25 cents and the "Today" text come from the superseded spec, which
  read them.
- Whether the stored IWM basis holds levels in range beyond those in the owner's example.
- The median stop distance of about 0.4 x ATR: handed, measured by another session.
- The owner's words: relayed to this session; the chat was not read.
- What the separately running experiment helper runs, and any result from it.
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
