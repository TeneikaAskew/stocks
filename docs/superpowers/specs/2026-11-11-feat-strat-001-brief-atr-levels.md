---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01, DASHBOARD-21, INSIGHTS-07, INSIGHTS-08]
done_when:
  - "ATR rungs: tests/lib/test_strat_levels.py passes a TestAtrRungs class on the exits spec's Design 8 fixture (reference 250.00, premarket high 252.10 and low 248.20, prior close 247.00, PDH 253.00, PMH 275.00, PQH 280.00, PYH 285.00, PDL 247.50, PML 225.00, PQL 220.00, PYL 215.00, both windows 2.6, ATR(14) 14.00, target_min_spacing_atr 0.25, exit_legs 3) with atr_rung_step_atr 0.5, atr_rung_max_atr 2.0 and atr_rung_stretch_atr 1.5: SessionLevels.atr_rungs is exactly 254.00 PC+0.5ATR, 261.00 PC+1ATR, 268.00 PC+1.5ATR (stretch), 275.00 PC+2ATR (stretch), 240.00 PC-0.5ATR, 233.00 PC-1ATR, 226.00 PC-1.5ATR (stretch), 219.00 PC-2ATR (stretch); build_session_levels gives calls trigger 252.10 (PMK_H), stop 248.20 (PMK_L), gate_targets 253.00, 275.00, 280.00, plan targets 261.00 (PC+1ATR), 268.00 (PC+1.5ATR, stretch), 275.00 (PMH, alias PC+2ATR, stretch) and skipped [253.00, 254.00]; puts trigger 248.20 (PMK_L), stop 252.10 (PMK_H), gate_targets 247.50, 247.00, 225.00, plan targets 240.00 (PC-0.5ATR), 233.00 (PC-1ATR), 226.00 (PC-1.5ATR, stretch) and skipped [247.50, 247.00]; with ATR(14) 24.00 and windows 1.6 the calls plan targets are 259.00 (PC+0.5ATR), 271.00 (PC+1ATR), 280.00 (PQH) with skipped [253.00, 275.00] and gate_targets still 253.00, 275.00, 280.00; a rung on the same cent as a structural level is that level's alias and never a candidate of its own; a rung whose distance from the prior close in cents equals atr_rung_stretch_atr x ATR in cents (price_cents half-up) is stretch and one cent less is not; a rung on the other side of the reference (prior close 247.00 with a reference of 260.00 puts PC+0.5ATR at 254.00 on the puts side) is listed on the side its price is on; an ATR rung is never a trigger, a stop, a gate target or a NEXT LEVELS ladder entry; any of atr_rung_step_atr, atr_rung_max_atr or atr_rung_stretch_atr not ok gives no ATR rungs, atr_rung_status equal to that status and plan targets equal to the exits spec's (calls 275.00, 280.00, 285.00); these cases fail on the implementation PR's base, which has no ATR rungs"
  - "No numbers: tests/lib/test_level_params_structure.py passes unchanged (no new literal or module constant on the build_session_levels walk) and test_the_walk_reaches_the_rules_it_must_cover also asserts that the rung builder is reached from build_session_levels; tests/lib/test_level_params_copy.py asserts that no string literal in lib/strat_levels.py contains '0.5 x ATR', '1.5 x ATR' or '2 x ATR'; the step, the largest multiple and the stretch mark are read only from LevelParams, and the multiples are i x step for whole i, compared in cents"
  - "Policy and calibration: gcp/schema.sql seeds level_param_policy rows atr_rung_step_atr (method_id policy_seed, extra {\"seed\": 0.5, \"anchor\": \"prior_close\"}), atr_rung_max_atr (policy_seed, extra {\"seed\": 2.0}) and atr_rung_stretch_atr (policy_seed, extra {\"seed\": 1.5}), each effective 2015-01-02 with ON CONFLICT DO NOTHING; lib.level_calibration.calibrate and HistoryCalibrator write one ticker_level_params row per ticker for each key at the seed in force, status ok, method_id policy_seed, as the exits spec's policy_seed method does; tests: a calibration of a fixture ticker returns the three keys at their seeds, a later policy row with atr_rung_max_atr seed 3.0 effective D gives 3.0 from D and 2.0 before it and adds the 2.5 and 3 rungs from D with no code change, and a policy with no such row raises LevelParamsUnavailable naming the key; they fail on the base"
  - "Brief copy: format_levels_for_brief renders the Design 8 fixture to exactly the text in Design 4 (a golden-string test in tests/lib/test_strat_levels.py): plan target lines name an ATR rung as PC+{k}ATR or PC-{k}ATR, a structural target that aliases a rung as '(PMH, also PC+2ATR, stretch)', a stretch target with ', stretch'; the skipped line names skipped rungs the same way; the NEXT LEVELS Calls and Puts lines are byte-identical to the base's; a new last NEXT LEVELS line lists every rung above the prior close as 'up' and below as 'down' with its multiple and ' stretch' where marked; atr_rung_status not ok renders 'ATR levels unavailable ({atr_rung_status}).' as that line; the orb_only copy and a side with no trigger are unchanged; the tests fail on the base"
  - "Unchanged, each pinned by an existing or added test that passes on the base and on the implementation head: the trigger and stop picks, gate_targets and the {calls,puts}_t1_price to _t3_price columns, the NEXT LEVELS ladder (SessionLevels.to_level_map call_levels and put_levels), the strat_levels rows persist_level_map writes (no ATR rung is a StratLevel in SessionLevels.levels), PMG zones, the signal monitor's fire decisions and put re-anchor in every level_gate_mode and put_reanchor_mode (the exits spec's end-to-end test still passes), the movement statement's rungs and its _reach_rate_sql and _fetch_tracked_levels pairing, persona plans (lib/agents/trade_planner.py) and the CALL/PUT pick"
  - "level_basis and replay: level_basis records atr_rungs (price, multiple, sign, stretch), atr_rung_status, the three parameters (value, status, method_id, effective_from) and LEVEL_RULE_VERSION one past the exits spec's feat-strat-001.v3; SessionLevels.from_basis on a basis of this version rebuilds the same rungs, plan targets and skipped list after the ticker_level_params rows change; from_basis on a stored v3 or v2 basis rebuilds that version's targets with no ATR rungs; published_prices includes the rungs' cents; the tests fail on the base"
  - "Experiment through the production paths, before any production change: the implementation PR body shows, for SPY, QQQ and IWM over every session from 2025-03-03 to 2026-11-10 replayed through gcp/premarket_brief.py (BRIEF_AS_OF) on the base and on the head with history-mode parameters, on 1-minute RTH bars where a level is reached when a bar trades through it and held when five consecutive 1-minute closes stay beyond it after the first touch, per window (2026-05-01 to 2026-11-10 and 2025-03-03 to 2026-04-30): (a) on ticker-days whose 09:30 open is at or beyond a side's trigger, the share whose next level the brief printed past the open in that direction (targets, NEXT LEVELS and, on the head, ATR rungs) is reached and held, the share with no printed level past the open, and head minus base with the 90% day-resampled range (seed 7, 2,000 draws); (b) per side, the largest empty stretch between printed levels inside the side's window, median, 90th percentile and share at least 1 x ATR; (c) plan T1, T2 and T3 reach and held shares from plan_t1_hit_ts to plan_t3_hit_ts; (d) total plan_r on base and head with the same range, for the owner; if (a) head minus base has a range that is not above zero in either window, or (d) head minus base has a range wholly below zero in either window, the PR stays draft and the owner decides"
  - "Source identity (DASHBOARD-01, DASHBOARD-21, INSIGHTS-07, INSIGHTS-08): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01 / DASHBOARD-21 / INSIGHTS-07 / INSIGHTS-08) note rows carry that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the three policy rows and the history-mode run for the three keys are applied to production only after the owner's yes and recorded separately"
status: approved
supersedes: null
---

# The premarket brief adds ATR levels above and below the prior close

## Authority

Owner rulings in force: values are never hard-coded and are tailored to the actual ticker, using the
ticker's own ATR (2026-11-08, recorded in
`docs/superpowers/specs/2026-11-10-feat-strat-001-per-ticker-params-r2.md`); and a change is tested
against its hypothesis before it is swapped in. On 2026-11-11, after seeing worked examples, the owner
asked for ATR levels to be incorporated into the brief, "prior/previous +/- ... both", because they
"keep the plans in play", and asked that the work be judged by whether levels are reached, not by
profit.

The anchor (prior close), the 0.5 step, the 2 x ATR reach and the 1.5 x ATR stretch mark are this
delivery lane's proposal from the 2026-11-11 level study, not owner rulings. This spec is written by a
FEAT-STRAT-001 delivery lane and is not self-approved: it takes effect only when the owner merges the
spec-only PR that adds it, and that merge is the approval its `status` records. No implementation is
written before that merge.

FEAT-STRAT-001 owns this change because every level is built in `lib.strat_levels.build_session_levels`
(the one level builder) and the step sizes belong in that feature's per-ticker parameter tables (#1784).

## Problem

The brief's levels come only from prior-period highs, lows and closes (day, week, month, quarter,
year), the parent bar and the premarket high and low (`PRIOR_PERIOD_CANDIDATES` and `_CANDIDATE_ORDER`, `lib/strat_levels.py:1373-1383` on origin/main e1a17c2c).
No level is measured from the prior close in ATR. ATR is used only to window and space those levels.

Those levels bunch near the open and thin out farther away. When price runs past the last one, the
brief has nothing left to say where the move may go next. That is the case the owner raised on
QQQ 2026-06-05, where the prior low minus 1 x ATR would have been the next level down and the brief
does not build it. That session traded through and held every prior-low-minus-k x ATR level down to
2.5 x ATR.

## Evidence

Level study, read only, not in the repo:
`/mnt/project-files/stocks-scorecard/research/fable_lab/triggers_levels/level_reach/` (`tables.md`,
rerun in about two minutes, deterministic with seed 7; script hashes in its report). SPY, QQQ and IWM;
windows primary 2026-05-01 to 2026-11-10, holdout 2025-03-03 to 2026-04-30, long 2016-03-01 to
2025-02-28. Reached means a 1-minute bar traded through the level; held means five consecutive 1-minute
closes stayed beyond it after the first touch. Ranges are 90%, 2,000 whole-day resamples, seed 7. The
study's structural set is the lab's wider ladder (it adds 12-hour, 2-day and period-open levels to the
brief's candidates), and its prior-close ladder ran to 3 x ATR, so the production replay in done_when is
the test that counts.

- ATR levels behave like any other level at the same distance. On the same session, same side and same
  0.05 x ATR distance cell, an ATR level and a structural level are reached within 0.6 points of each
  other in every window (35,669 pairs in the long window, -0.1 points above and below), and only one of
  the two is reached in 1.0 to 1.5% of pairs.
- How often prior-close steps are reached / held 5 minutes (long): PC + 0.5 x ATR 40% / 34%, + 1 14% / 12%,
  + 1.5 3% / 2%, + 2 1% / 0%; PC - 0.5 35% / 29%, - 1 15% / 12%, - 1.5 6% / 5%, - 2 2% / 2%. About
  8 in 10 touches hold. Primary and holdout are within a few points.
- Holes in the ladder. On 26% of sides there is no structural level between 1 and 3 x ATR out, and the
  largest empty stretch out to 3 x ATR has a median of 1.51 x ATR. Adding prior close +/- every 0.5 x ATR
  caps it at 0.50.
- Days that opened past the brief's trigger (299 ticker-days, 2025-03-03 to 2026-11-10): the next
  structural level past the open was reached on 60% (54 to 65), 10% had no level left in that direction
  and on 20% the next level was farther than the whole day's range. With prior close +/- 0.5 x ATR steps
  added: 77% (72 to 81), none without a next level and none farther than the day's range. Long window
  (2,172 cases): 65% to 79%.
- Context only, not used by this spec: with RSI(14) under 30 at the prior close, open +/- 1 x ATR was
  reached about three times as often as with RSI 60 to 70 (23% up and 28% down against 4 to 8%), and
  after gaps of more than 1 x ATR the gap-fill side's 1 x ATR level was reached 33% of the time.

## Non-goals

- The trigger and the stop. ATR rungs never trigger and never stop. The lane's test of entering at the
  next level after the open had passed the trigger did worse than today's rule in all three windows, so
  entries stay as the exits spec set them.
- What the signal monitor gates on (`gate_targets`, the `{calls,puts}_t1_price` to `_t3_price` columns)
  and the `strat_levels` rows it reads: unchanged.
- ATR rungs on PDH, PDL or the open, RSI- or gap-conditioned ladders, and printing reach odds beside a
  level. Each is a follow-up that needs its own test.
- The movement statement's rungs and the persona plans.

## Approaches considered

1. ATR levels on the prior close, PDH, PDL and the open, every 0.5 x ATR to 3. The next level after an
   opened-through trigger was reached 89 to 91% of the time, but only because levels were 0.04 x ATR apart
   (66 to 84 levels within 3 x ATR). Rejected: too crowded to read.
2. PDH + k and PDL - k in 0.5 steps (breakouts past the prior range). 73% on opened-through days.
   Rejected: close to the chosen rule but one-sided per anchor, while the owner asked for both signs.
3. Prior close +/- 1, 2, 3 x ATR. 67%, and 5% of cases still had the next level beyond the day's range.
   Rejected: too coarse.
4. Chosen: prior close +/- every 0.5 x ATR out to 2 x ATR, levels 1.5 x ATR or more from the prior close
   marked stretch, each value a per-ticker parameter.

## Design

### 1. ATR rungs, per ticker

Three new `ticker_level_params` keys, in the policy's ATR basis (`atr_14`, Wilder ATR(14) of the last
completed session):

| Key | Seed | Meaning |
|---|---|---|
| `atr_rung_step_atr` | 0.5 | distance between rungs, in ATR |
| `atr_rung_max_atr` | 2.0 | the farthest rung from the prior close, in ATR |
| `atr_rung_stretch_atr` | 1.5 | a rung at least this far from the prior close is marked stretch |

`build_session_levels` builds, after the prior close is known, for whole i = 1, 2, ... while
i x step <= max (compared in cents), a rung at prior close + i x step x ATR named `PC+{k}ATR` and one at
prior close - i x step x ATR named `PC-{k}ATR`, k = i x step written by `multiple_text`. Each rung records
its multiple, its sign and `stretch` (distance from the prior close in cents at least stretch x ATR in
cents). They are stored in a new `SessionLevels.atr_rungs`, never in `SessionLevels.levels`, so
`persist_level_map`, the `strat_levels` table, PMG zones and every reader of `levels` are unchanged.
When any of the three parameters is not ok there are no rungs and `atr_rung_status` records the first
status that is not ok; there is no unparameterised fallback (CLAUDE.md 3.7).

### 2. Where the rungs enter

- `_candidate_rungs` adds the ATR rungs after every structural candidate in priority, so at one cent a
  structural level wins and the rung becomes its alias. A rung lies on the side its price is on relative
  to the reference: after a gap up of more than 0.5 x ATR, PC+0.5ATR sits below the reference on the puts
  side, which is the gap-fill direction.
- The side, broken and window rules apply to rungs exactly as to any candidate (`_pick_side`).
- The trigger is the first unbroken in-window structural candidate, as on the base. The stop is the
  first in-window structural candidate on the other side, as on the base. `gate_targets` are the first
  three structural candidates past the trigger, as the exits spec defines them, and the NEXT LEVELS
  ladder is the trigger and the next structural candidate, as on the base.
- The exits spec's spacing walk (its Design 1) picks plan targets from every candidate past the trigger,
  structural and ATR, in price order, with the same spacing and leg count. So on a side whose structural
  levels run out, the plan still has targets, and where a rung lies between the trigger and a far
  structural level it becomes a nearer target.

### 3. level_basis and rule version

`LEVEL_RULE_VERSION` moves one past the exits spec's `feat-strat-001.v3`. level_basis records the rungs,
`atr_rung_status` and the three parameters with value, status, method_id and effective_from.
`SessionLevels.from_basis` rebuilds a basis of this version with its recorded rungs and a v3 or v2 basis
with that version's rule, so stored briefs and their replays do not change. `published_prices` includes
the rungs' cents. The resolver needs no change: its plan columns already read the plan targets from
level_basis.

### 4. What the brief will look like

The exits spec's Design 8 ticker: reference 250.00, premarket high 252.10 and low 248.20, prior close
247.00, ATR(14) 14.00, windows 2.6 x ATR, spacing 0.25 x ATR = 3.50. The rungs are 254.00, 261.00,
268.00 and 275.00 above and 240.00, 233.00, 226.00 and 219.00 below; 275.00 is also PMH.

Exits spec (base):

```
  CALLS above 252.10 (PMK_H), new entries 09:30 to 10:00 ET
    No entry if the open is at or above 252.10.
    Stop: 248.20 (PMK_L)
    T1: 275.00 (PMH), sell 1/3
    T2: 280.00 (PQH), sell 1/3
    T3: 285.00 (PYH), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 253.00 (PDH)
    Room to trigger: 0.84%
```

After:

```
  CALLS above 252.10 (PMK_H), new entries 09:30 to 10:00 ET
    No entry if the open is at or above 252.10.
    Stop: 248.20 (PMK_L)
    T1: 261.00 (PC+1ATR), sell 1/3
    T2: 268.00 (PC+1.5ATR, stretch), sell 1/3
    T3: 275.00 (PMH, also PC+2ATR, stretch), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 253.00 (PDH), 254.00 (PC+0.5ATR)
    Room to trigger: 0.84%

  PUTS below 248.20 (PMK_L), new entries 09:30 to 10:00 ET
    No entry if the open is at or below 248.20.
    Stop: 252.10 (PMK_H)
    T1: 240.00 (PC-0.5ATR), sell 1/3
    T2: 233.00 (PC-1ATR), sell 1/3
    T3: 226.00 (PC-1.5ATR, stretch), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 247.50 (PDL), 247.00 (PDC)
    Room to trigger: 0.72%
```

The NEXT LEVELS Calls and Puts lines are unchanged, and a last line is added:

```
    ATR from prior close 247.00, ATR(14) 14.00: up 254.00 (+0.5), 261.00 (+1), 268.00 (+1.5 stretch), 275.00 (+2 stretch); down 240.00 (-0.5), 233.00 (-1), 226.00 (-1.5 stretch), 219.00 (-2 stretch)
```

On a ticker whose ATR(14) is 24.00 (windows 1.6, spacing 6.00) the rungs above are 259.00, 271.00,
283.00 and 295.00 (outside the 288.40 window), and the calls plan targets are 259.00, 271.00 and 280.00
(275.00 is 4.00 past 271.00, under 6.00, so skipped).

## Dependencies

- `docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md` (#1812): its spacing walk,
  plan target columns, `policy_seed` calibration method and rule v3. This spec's implementation opens
  after that spec's implementation is on main and builds on it; it does not re-specify those rules.
- #1784 (per-ticker parameters), on main.

## Open questions for the owner

1. Reach out to 2 x ATR (seed) or 3? Past 2 x ATR from the prior close levels were reached on 1% of
   sessions or fewer; each is one policy row to change.
2. Should ATR rungs later be allowed to trigger? Not in this spec (Non-goals).

## Expected effect

Every brief with a prior close and an ATR shows up to four ATR levels on each side of the prior close,
labelled with their multiple and marked stretch from 1.5 x ATR. Plan targets change on ticker-days where a
rung is nearer than the next spaced structural level or the structural levels run out; done_when
counts them. Triggers, stops, the NEXT LEVELS ladder, signal-monitor fires and the movement statement's
rungs do not change. The insight report's plan levels read the new targets through level_basis.

## Capacity and cost

- **Volume:** three more policy rows; three more `ticker_level_params` rows per calibrated ticker per
  effective date (the history run writes about 2,980 per ticker per key); up to eight rungs per session
  in level_basis. No new column: the exits spec's plan target columns hold the targets.
- **Velocity:** no new query; the rows ride the one `load_level_params` query per run.
- **Wall-clock:** a handful of in-process additions per session.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief), DASHBOARD-21 (the
movement statement, whose reach-rate population restarts at the new rule version while its rungs stay),
INSIGHTS-07 and INSIGHTS-08 (the report's plan and key levels from level_basis) show or read the changed
levels. Only the `(FEAT-STRAT-001, <component>)` rows of the Implementation-source notes table for those
four may describe this implementation, as backend source and local tests only. Every other SITE byte
stays unchanged.

After the merge, separately and never as a pre-merge box: apply the policy rows, run the history mode for
the three keys, verify main's source and body identity in a fresh clone, complete the DOC main and
staging close-out with real evidence (a live brief showing the ATR line and labelled targets), retire
the sidecar as the product-delivery skill prescribes, and set the plan to `status: done` on a `docs/`
branch.

## Risks

- **The study's ladder is wider than the brief's.** Its 60% baseline used more structural levels than the
  brief builds, so the brief's own gain may differ; done_when's replay measures it on the brief.
- **Nearer plan targets.** Rungs can pull T1 closer than the exits spec's targets; done_when (c) and (d)
  show the change in reach and plan R before anything ships.
- **Reach-rate history restarts** for the movement statement under the new rule version.
- **Order of delivery.** This spec waits on the exits spec's implementation; if that changes before it
  lands, this spec is revised, not stretched.
