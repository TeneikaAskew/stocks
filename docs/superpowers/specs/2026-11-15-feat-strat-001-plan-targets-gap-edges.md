---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "Policy: gcp/schema.sql seeds one new level_param_policy row plan_target_level_types (method_id policy, effective 2015-01-02, extra {\"level_types\": [\"gap_high\", \"gap_low\"]}) with ON CONFLICT DO NOTHING; no other level_param_policy row changes; lib/strat_levels.py names the key once (PLAN_TARGET_LEVEL_TYPES_KEY) in POLICY_WIDE_KEYS, and policy_wide_param gives it status ok with value equal to the number of listed types when every listed type is gap_high or gap_low and none repeats, ok with value 0 for an empty list, and input_unavailable for a missing list, an unknown type or a repeat; a test in tests/lib/test_level_params_loader.py loads the seeded policy from gcp/schema.sql and asserts status ok and value 2, and each unusable extra gives input_unavailable"
  - "Plan walk: tests/lib/test_strat_levels.py passes tests on a session built through build_session_levels or SessionLevels.from_basis with the seeded policy where (a) a gap edge (level_type gap_high or gap_low in the session's levels) beyond the trigger, inside the side's own window and at least the spacing past the trigger joins the plan's targets in price order and is published under its own name (GAP_H_YYYY-MM-DD or GAP_L_YYYY-MM-DD, printed as M/D Gap High or Low); (b) a gap edge closer than the spacing to the trigger or the target before it is listed in skipped; (c) a gap edge at or before the trigger, outside the window, or on the same cent as a candidate adds nothing (the candidate's record is byte-identical to origin/main's, no alias added); two gap edges on one cent give one rung, the most recent gap's, high before low; (d) with plan_target_level_types extra {\"level_types\": []} the plan's targets and skipped list equal origin/main's; (e) with the key unusable or missing the side publishes no target and target_status is that key's status, as for the spacing, leg and cutoff keys"
  - "Never anything but a plan target: on the same sessions, the trigger, stop, gate_targets (rungs 1 to 3 of the candidate list), ladder, room, distance_atr, the candidates list, the ATR rungs line, and the legacy targets and t1..t3 columns are byte-identical to origin/main's, each asserted against an origin/main golden; _candidate_rungs is unchanged and gap levels stay out of it"
  - "Stored briefs keep their targets: tests/gcp/test_level_basis.py passes two tests on stored bases with no plan_target_level_types_status key: (a) params that do not record plan_target_level_types at all (every brief stored before the row exists), and (b) params that record it (as the loader records every policy key once the row exists); each rebuilds through SessionLevels.from_basis with target_status ok and plan targets and skipped list equal to origin/main's for that basis, so the new key is never checked for a markerless basis; a basis built on the head records plan_target_level_types_status ok and rebuilds with gap edges; gcp.premarket_playbook_resolver.plan_inputs on each gives the matching targets and plan_available true for (a) and (b)"
  - "Brief copy: a new golden in tests/lib/test_strat_levels.py on the exits spec's Design 8 fixture plus one level GAP_H_2026-10-20 at 262.40 gives the calls lines of this spec's Design 4 byte for byte; the existing D8_CALLS and D8_PUTS goldens (no gap level) are unchanged"
  - "Unchanged, each pinned by an existing test that passes on origin/main and on the implementation head: the trigger and stop rule, gate targets, the opened-through rule, the entry cutoff, exit_legs and the thirds, the ATR rungs line, the signal monitor's fire decisions and put re-anchor, the movement statement, persona plans, the CALL/PUT pick and the resolver's existing outcome columns; LEVEL_RULE_VERSION and RESOLVER_VERSION do not change (the marker in Design 3 tells old and new bases apart, and the resolver's code does not change)"
  - "Experiment through the production paths, before any production change: the implementation PR body shows, for SPY, QQQ and IWM over 2022-01-03 to 2026-11-10 on the same ticker-days as this spec's Experiment (one trade per ticker-day, the first side to cross its trigger, a same-bar tie is no trade, half days cut at the exchange close, SPY 2025-04-09 and IWM 2026-06-26 left out), plan R from gcp.premarket_playbook_resolver.resolve_plan with inputs from plan_inputs on bases built with the seeded policy on origin/main and on the head, both arms reading the entry_cutoff_et seed of 16:00 that #1967 put on main (so no first cross in the session is late_cross and no research-only override is used), per ticker and per six-month block, with the 90% day-resampled range of head minus origin/main (seed 7, 2,000 draws); origin/main matches this spec's +172.3 to 0.1 R and the head matches +176.8 to 1.0 R (the Experiment's walk rounds the spacing outside the production code); a reproduction for the record, not a gate"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the production plan_target_level_types row is inserted only after the owner's yes, by the statement in Design 2, before the code that reads it is deployed, and recorded separately"
status: approved
supersedes: null
---

# The exits plan's targets also walk the brief's gap edges: an unfilled gap's high or low can be T1, T2 or T3

## Authority

The owner asked on 2026-11-15 (UTC) what gap edges are and whether the levels and ATR could be used
together for targets ("it should be like a combination of both"), and answered "Yes" to testing gap
edges as targets. The Experiment below is that test. This spec is the change the test supports.

Rulings still in force: values are never hard-coded and come from policy or per-ticker parameter rows
(2026-11-08); a change is tested against its hypothesis before it is swapped in; R is the stock's move
after the fill measured in stop distances, never money, and comparisons are like for like.

This spec is written by a FEAT-STRAT-001 delivery lane and is not self-approved: it takes effect only
when the owner merges the spec-only PR that adds it, and that merge is the approval its `status`
records. No implementation is written before that merge.

Not in this spec: the entry cutoff (its own spec and PR), whether IWM keeps today's rule, and gap
edges as triggers or stops (Non-goals).

## Problem

The brief already finds unfilled gaps over the last 20 daily bars (`compute_gap_levels`) and lists
their edges, but the exits plan never uses them: `_candidate_rungs` takes prior-period highs, lows and
closes, the parent bar and the premarket extremes only, and the plan's spaced walk
(`_plan_targets`, exits spec Designs 1 and 2) walks that list. An unfilled gap's edge is a price the
stock often comes back to, so a trader would mark it as a target.

Replayed through the production code over 2022-01-03 to 2026-11-10 (Experiment), letting the plan's
walk use gap edges changes the targets on 711 of 3,463 trades and adds +4.5 R in total, just short of
clear over the whole stretch, clearly better for IWM and on flat opens, and ahead in 6 of 9 equal
six-month blocks.

## Non-goals

- Gap edges as triggers, stops, gate targets (the t1..t3 columns), ladder entries or ATR rung anchors.
  The trigger rule (#1753: opens and gap levels are never triggers) is unchanged.
- The spacing, the leg count, the thirds, the entry cutoff, the opened-through rule.
- Opens as targets. Opens stay the FTFC reference.
- The gap finder itself (`compute_gap_levels`, its 20-bar lookback and its fill test).

## Approaches considered

1. Chosen: gap edges join the plan's spaced walk only, behind a policy-wide row that names which extra
   level types the walk may use. Experiment GS: +176.8 R against +172.3 R.
2. Gap edges in the next three without the spacing walk (Experiment G): +95.0 R, clearly behind the
   plan (-77.3, range -131.2 to -26.4). Rejected.
3. Gap edges as full candidates (triggers, stops and gate targets too). Rejected: it changes the
   trigger rule the owner set on 2026-11-07, the monitor and the movement statement, and was not
   tested.

## Design

### 1. The policy row

`gcp/schema.sql` seeds, next to the exits spec's rows:

```sql
('plan_target_level_types', 'policy', NULL, NULL, NULL, '{"level_types": ["gap_high", "gap_low"]}', '2015-01-02',
 'level types, beyond the trigger candidates, the exits plan''s spaced target walk may use'),
```

`policy_wide_param` reads it like `atr_rung_anchors`: the value is the number of listed types; an empty
list is ok with value 0 (the walk uses candidates only, as on origin/main); a missing list, a type other
than `gap_high` or `gap_low`, or a repeat is `input_unavailable`. For a session built under this rule
(every new build, and a stored basis that carries the Design 3 marker), `_plan_targets` adds the key to
the keys it checks first (spacing, legs, cutoff), so a side whose row is unusable or missing publishes
no target and says why, never a walk without the rule it is scored on (CLAUDE.md 3.7). A stored basis
without the marker is rebuilt under the old walk and the key is not checked at all, because a brief
stored before the row existed recorded no such parameter (Design 3).

### 2. The production row

After the owner's yes, and before the code that reads it is deployed:

```sql
INSERT INTO level_param_policy (param_key, method_id, statistic_q, lookback_sessions, min_sample,
                                extra, effective_from, note)
VALUES ('plan_target_level_types', 'policy', NULL, NULL, NULL,
        '{"level_types": ["gap_high", "gap_low"]}', '2015-01-02',
        'level types, beyond the trigger candidates, the exits plan''s spaced target walk may use')
ON CONFLICT (param_key, effective_from) DO NOTHING;
```

The row first, because the code treats a missing row as no plan (Design 1). Today's code ignores the
key, and bases it builds without the marker keep their old walk (Design 3), so the row alone changes
nothing. The run records whether it inserted one row or none. Turning gap edges off later is one
update of `extra` to `{"level_types": []}`.

### 3. The walk, and stored briefs

In `_assemble`, after the candidates are built, the session's levels whose `level_type` is in the
policy's list become gap rungs, distinct by cent: a cent that a candidate holds is dropped (the
candidate's record is not touched, so its name and aliases stay as on origin/main); two gap edges on one
cent give the most recent gap's, high before low. They are passed to `_pick_side`, which passes
`_plan_targets` the side's rungs merged with the gap rungs that are beyond the trigger and inside the
side's own window, in price order away from the reference. The walk itself is unchanged: from the
trigger, keep a rung at least the spacing past the trigger or the target before it, until `exit_legs`
are kept; a closer rung is listed in `skipped`. The trigger, stop, `gate_targets`, ladder and room are
still taken from the candidates alone.

A basis built under this rule records a top-level `plan_target_level_types_status` (`ok` or the key's
status) and the list used. `SessionLevels.from_basis` rebuilds gap rungs, and checks the new key, only when that key is present;
without it the walk and its checked keys are exactly origin/main's, whether or not the basis's params
record `plan_target_level_types`. This is
the same marker pattern as `atr_rung_status` (Codex P2 on #1951): the parameter itself is not a marker,
because the loader records every policy key once the row exists. So a stored brief, its replay and the
resolver's plan R for it do not change. `LEVEL_RULE_VERSION` does not move, because moving it would
restart the movement statement's reach rates, which read gate targets that this spec does not touch.

### 4. What the brief will look like

On the exits spec's Design 8 fixture plus one unfilled gap whose high is GAP_H_2026-10-20 at 262.40
(spacing 3.50), the calls side's target lines become:

```
    T1: 262.40 (10/20 Gap High), sell 1/3
    T2: 275.00 (PMH), sell 1/3
    T3: 280.00 (PQH), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 253.00 (PDH)
```

Every other line, and the puts side, is unchanged. Without a gap edge in reach the brief is byte for
byte what it is today.

## Experiment

Hypothesis: with the exits plan's trigger, stop, spacing, thirds and fill unchanged, letting the spaced
walk use the brief's gap edges does no worse than the plan without them.

Data (read only, not in the repo): every session from 2022-01-03 to 2026-11-10 (1,212 sessions; SPY,
QQQ, IWM) replayed through #1832's `gcp/premarket_brief.py` (BRIEF_AS_OF) into a local copy of the
schema, with the as-traded 1-minute bars in `/mnt/project-files/stocks-scorecard/inputs/bars_raw/`,
the same replay and data check as the entry cutoff spec
(`docs/superpowers/specs/2026-11-15-feat-strat-001-drop-entry-cutoff.md`); half days cut at the
exchange close; SPY 2025-04-09 and IWM 2026-06-26 left out.

Method: one trade per ticker-day, the first side to cross its trigger; a same-bar tie is no trade; a day
that opens past a trigger is no trade; no entry cutoff, which is what the seeded policy gives now that
#1967 moved `entry_cutoff_et` to 16:00 on main. The gap edges are the stored basis's
`GAP_H_`/`GAP_L_` levels beyond the trigger and inside the side's window, merged with the side's
unbroken in-window candidates by cent. Each trade is scored by
`gcp.premarket_playbook_resolver.resolve_plan` on the same bars with three targets from each rule. R per
trade is the stock's move after the fill in stop distances, summed over the three legs. Ranges are 90%,
resampling whole days 2,000 times, seed 7.

Results, total R over 3,463 trades (gap edges minus plan, range):

| Group | Trades | Plan (1832) | Plan with gap edges | Gap edges minus plan |
|---|---|---|---|---|
| All | 3,463 | +172.3 | +176.8 | +4.5 (-0.4, +9.3) |
| SPY | 1,161 | +65.4 | +64.2 | -1.2 (-4.0, +1.4) |
| QQQ | 1,152 | +110.9 | +114.0 | +3.0 (-0.1, +6.7) |
| IWM | 1,150 | -4.1 | -1.4 | +2.7 (+0.7, +5.1) clear |
| Flat opens (gap under 0.1 ATR) | 766 | -10.8 | -7.4 | +3.3 (+0.6, +6.5) clear |
| 2022-01-03 to 2025-02-28 | 2,275 | +139.7 | +144.3 | +4.6 (+0.5, +9.0) clear |
| 2025-03-03 to 2026-04-30 | 829 | +8.5 | +7.9 | -0.6 (-3.2, +1.6) |
| 2026-05-01 to 2026-11-10 | 359 | +24.0 | +24.5 | +0.5 (-0.8, +2.0) |

Targets differ on 711 trades (240 QQQ, 236 SPY, 235 IWM); the whole +4.5 R comes from them. Hit rates
before the stop: T1 22% against 20%, T2 4% against 3%; stop first 42% for both.

Six-month blocks, gap edges minus plan (the first and last are partial): Jan to Feb 2022 +0.7, Mar to
Aug 2022 -0.9 (-2.2 to 0.0), Sep 2022 to Feb 2023 +0.4, Mar to Aug 2023 +2.3 (+0.1 to +5.1), Sep 2023
to Feb 2024 +1.7 (+0.2 to +3.6), Mar to Aug 2024 +0.2, Sep 2024 to Feb 2025 +0.2, Mar to Aug 2025 +0.3,
Sep 2025 to Feb 2026 -0.3, Mar to Aug 2026 -0.6, Sep to Nov 10 2026 +0.6. Ahead in 6 of the 9 full
blocks; the two with a range above zero are clear, and Mar to Aug 2022 is just behind (-2.2 to 0.0).

Examples (dated, targets as published on that date):

- QQQ 2024-11-20, puts: the plan's targets were 497.08 and 494.49 (two in reach); with gap edges
  499.60, 497.08, 494.49. The plan took T1 and held two thirds to the close (+0.98 R); with gap edges
  T1 and T2 were taken and one third held (+1.83 R).
- SPY 2022-03-31, puts: the plan's targets were 452.98, 440.68, 436.63; with gap edges 455.91, 452.98,
  440.68. With gap edges the second third was sold at 452.98 instead of riding to the close, so the
  plan did better here (+2.72 R against +2.05 R).

Reading: a small, steady gain made almost entirely before 2025-03; flat on the recent windows. It never
loses much in any block, and it helps where the plan is weakest (IWM, flat opens).

Commands (the replay database is the local copy described above):

```bash
LAB=/mnt/project-files/stocks-scorecard/research/combine
python3 $LAB/gaps.py 2022-01-03 2026-11-10 gaps_all.csv   # one row per trade
python3 $LAB/gaps_report.py gaps_all.csv                  # the tables above
```

sha256 prefixes: gaps.py 2576b8d8, gaps_report.py f68a4c7b, gaps_all.csv 9b742aa2.

## Expected effect

About one traded side in five prints a gap edge among its targets, named like `10/20 Gap High`; a gap
edge too close to the trigger or the target before it shows in the Skipped line. The resolver's plan R
for new briefs follows those targets. The t1..t3 columns, the monitor, the movement statement and every
stored brief are unchanged.

## Capacity and cost

- **Volume:** one new policy row; each new `level_basis` gains one status key and a short list.
- **Velocity:** no new query; the row rides the one `load_level_params` query per run.
- **Wall-clock:** unchanged; the gap levels are already computed for every brief.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new
target names. Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may
describe this implementation, as backend source and local tests only. Every other SITE byte stays
unchanged.

After the merge, separately and never as a pre-merge box: on the owner's yes, run Design 2's statement
against production and record the row count, then deploy; confirm the next live brief records
`plan_target_level_types_status` ok and that a side with a gap edge in reach prints it; and complete the
DOC close-out as the product-delivery skill prescribes.

## Risks

- **Not clear overall.** The whole-stretch range just touches zero (-0.4), and the recent windows are
  flat. The gain is small next to the plan's own swings; it is offered because it never costs much and
  helps IWM and flat opens.
- **Deploy order.** Code deployed before the row would leave every side without a plan for that run
  (Design 1). Design 2 puts the row first.
- **A gap edge can be stale.** An edge from up to 20 sessions back still counts until filled; the
  side's window keeps far edges out, the same window every target already uses.

## Found while reading (not changed by this spec)

None.
