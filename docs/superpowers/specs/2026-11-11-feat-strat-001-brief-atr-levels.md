---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01]
done_when:
  - "ATR rungs: tests/lib/test_strat_levels.py passes a TestAtrRungs class on the exits spec's Design 8 fixture (reference 250.00, premarket high 252.10 and low 248.20, prior close 247.00, PDH 253.00, PMH 275.00, PQH 280.00, PYH 285.00, PDL 247.50, PML 225.00, PQL 220.00, PYL 215.00, both windows 2.6, ATR(14) 14.00, target_min_spacing_atr 0.25, exit_legs 3) with atr_rung_anchors [PDH, PDL, PMK_H, PMK_L], atr_rung_step_atr 0.5, atr_rung_max_atr 2.0 and atr_rung_stretch_atr 1.5: before thinning there are 32 rungs (each anchor plus and minus 0.5, 1, 1.5 and 2 x 14.00); after thinning SessionLevels.atr_rungs is exactly 259.10 PMK_H+0.5ATR, 266.10 PMK_H+1ATR, 241.20 PMK_L-0.5ATR and 234.20 PMK_L-1ATR, and atr_rungs_dropped holds the other 28 with the reason neighbor or structural (225.00 PDH-2ATR, on PML's cent, is dropped as structural and recorded as PML's alias); 273.10 (PMK_H+1.5ATR) is dropped because it is 1.90 from 275.00 (PMH) although it is 7.00 from 266.10; a rung whose distance in cents from its open-side neighbor or from a structural candidate equals target_min_spacing_atr x ATR in cents (price_cents half-up) is kept and one cent less is dropped; a rung whose distance in cents from its own anchor equals atr_rung_stretch_atr x ATR in cents is stretch and one cent less is not; two rungs on one cent take the name of the anchor listed first in atr_rung_anchors and the other is its alias; with no premarket snapshot the rungs come from PDH and PDL only and level_basis records PMK_H and PMK_L as anchor_unavailable; any of the four rung parameters or target_min_spacing_atr not ok gives no ATR rungs and atr_rung_status equal to that status; these cases fail on the implementation PR's base, which has no ATR rungs"
  - "Display only: on the Design 8 fixture, on the same fixture with ATR(14) 24.00 and windows 1.6, with each rung parameter not ok, with target_min_spacing_atr not ok and with no premarket snapshot, build_session_levels on the head and on the base give identical triggers, stops, gate_targets, plan targets, skipped lists, target_status and reasons for both sides (Design 8: calls trigger 252.10, stop 248.20, gate_targets 253.00, 275.00, 280.00, plan targets 275.00, 280.00, 285.00, skipped [253.00]; puts trigger 248.20, stop 252.10, gate_targets 247.50, 247.00, 225.00, plan targets 225.00, 220.00, 215.00, skipped [247.50, 247.00]); _candidate_rungs and _pick_side never receive an ATR rung (asserted by a test that builds a session whose only level past the trigger would be a rung and gets the base's targets); the premarket_analysis columns the brief writes, including {calls,puts}_t1_price to _t3_price and the exits spec's plan target columns, are byte-identical on head and base for the same inputs"
  - "No numbers and no names: tests/lib/test_level_params_structure.py passes unchanged (no new literal or module constant on the build_session_levels walk) and test_the_walk_reaches_the_rules_it_must_cover also asserts that the rung builder and the thinning walk are reached from build_session_levels; tests/lib/test_level_params_copy.py asserts that no string literal in lib/strat_levels.py contains '0.5 x ATR', '1.5 x ATR' or '2 x ATR' and that the anchor names are read only from the atr_rung_anchors policy row (no tuple or list of anchor names in lib/strat_levels.py); the step, the largest multiple, the stretch mark and the thinning distance are read only from LevelParams, and the multiples are i x step for whole i, compared in cents"
  - "Policy and calibration: gcp/schema.sql seeds level_param_policy rows atr_rung_anchors (method_id policy, extra {\"anchors\": [\"PDH\", \"PDL\", \"PMK_H\", \"PMK_L\"]}), atr_rung_step_atr (policy_seed, extra {\"seed\": 0.5}), atr_rung_max_atr (policy_seed, extra {\"seed\": 2.0}) and atr_rung_stretch_atr (policy_seed, extra {\"seed\": 1.5}), each effective 2015-01-02 with ON CONFLICT DO NOTHING; load_level_params reads atr_rung_anchors like atr_basis and raises LevelParamsUnavailable when the row is missing, empty or names a level that is not a trigger candidate; lib.level_calibration.calibrate and HistoryCalibrator write one ticker_level_params row per ticker for each policy_seed key at the seed in force, status ok, method_id policy_seed, as the exits spec's policy_seed method does; tests: a calibration of a fixture ticker returns the three numeric keys at their seeds, a later policy row with atr_rung_max_atr seed 3.0 effective D gives 3.0 from D and 2.0 before it and adds the 2.5 and 3 rungs from D, a later atr_rung_anchors row listing [PDC] effective D builds prior-close rungs from D with no code change, and a policy with no atr_rung_anchors row raises LevelParamsUnavailable naming the key; they fail on the base"
  - "Brief copy: format_levels_for_brief renders the Design 8 fixture to exactly the exits spec's Design 8 text with one line added, the last NEXT LEVELS line in Design 5 here (a golden-string test in tests/lib/test_strat_levels.py); every other line, including the CALLS and PUTS blocks, their target and skipped lines and the NEXT LEVELS Calls and Puts lines, is byte-identical to the base's; the added line lists every kept rung inside the side's window above the reference as 'up' and below as 'down', nearest first, each as price ({anchor}{sign}{k}) with ' stretch' where marked and ', also {alias}' where two rungs share a cent; atr_rung_status not ok renders 'ATR levels unavailable ({atr_rung_status}).' as that line; the orb_only copy and a side with no trigger are unchanged; the tests fail on the base"
  - "Unchanged, each pinned by an existing or added test that passes on the base and on the implementation head: the trigger and stop picks, gate_targets, the exits spec's plan targets, skipped list and target_status, the {calls,puts}_t1_price to _t3_price and plan target columns, the resolver's plan columns and plan_r, the NEXT LEVELS ladder (SessionLevels.to_level_map call_levels and put_levels), the strat_levels rows persist_level_map writes (no ATR rung is a StratLevel in SessionLevels.levels), PMG zones, LEVEL_RULE_VERSION, the signal monitor's fire decisions and put re-anchor in every level_gate_mode and put_reanchor_mode (the exits spec's end-to-end test still passes), the movement statement's rungs, reach rates and _reach_rate_sql and _fetch_tracked_levels pairing, the insight report's plan and key levels, persona plans (lib/agents/trade_planner.py) and the CALL/PUT pick"
  - "level_basis and replay: level_basis gains optional keys atr_rungs (price, anchor, multiple, sign, stretch, aliases), atr_rungs_dropped (price, anchor, multiple, reason), atr_rung_status, the anchor list and the four parameters (value, status, method_id, effective_from); SessionLevels.from_basis on a basis with those keys rebuilds the same rungs after the ticker_level_params or policy rows change, and on a stored basis without them rebuilds no rungs and the same targets as before; with_premarket rebuilds the PMK_H and PMK_L rungs from the newer snapshot; published_prices includes the kept rungs' cents; the tests fail on the base"
  - "Experiment through the production paths, before any production change: the implementation PR body shows, for SPY, QQQ and IWM over every session from 2025-03-03 to 2026-11-10 replayed through gcp/premarket_brief.py (BRIEF_AS_OF) with history-mode parameters, three builds: the base, the head with the seeded anchors (PDH, PDL, PMK_H, PMK_L) and, for reference, the head with an atr_rung_anchors row of [PDC] (prior close); on 1-minute RTH bars, where a level is reached when a bar trades through it and held when five consecutive 1-minute closes stay beyond it after the first touch, per window (2026-05-01 to 2026-11-10 and 2025-03-03 to 2026-04-30): (a) on ticker-days whose 09:30 open is at or beyond a side's trigger, the share whose first and second printed levels past the open in that direction (targets, NEXT LEVELS and on the head the ATR line), each at least target_min_spacing_atr x ATR past the open or the level before it, are reached and held, the share with no printed level past the open, and each head build minus the base and the seeded anchors minus the prior-close build, with the 90% day-resampled range (seed 7, 2,000 draws); (b) the same as (a) on every session, both directions from the open, split by gap bucket and with or against the gap; (c) per side, the largest empty stretch between printed levels inside the side's window, median, 90th percentile and share at least 1 x ATR, and the number of printed levels within 3 x ATR; (d) plan T1, T2 and T3 prices and their reach and held shares from plan_t1_hit_ts to plan_t3_hit_ts are equal on every build for every ticker-day; (e) total plan_r is equal on every build; any difference in (d) or (e) fails the PR, and if (a) seeded anchors minus base has a first-level reach range that is not above zero in either window, the PR stays draft and the owner decides"
  - "Source identity (DASHBOARD-01): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01) note row carries that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the four policy rows and the history-mode run for the three seeded keys are applied to production only after the owner's yes and recorded separately"
status: approved
supersedes: null
---

# The premarket brief shows ATR levels above and below the prior day's and the premarket's high and low

## Authority

Owner rulings in force: values are never hard-coded and are tailored to the actual ticker, using the
ticker's own ATR (2026-11-08, recorded in
`docs/superpowers/specs/2026-11-10-feat-strat-001-per-ticker-params-r2.md`); and a change is tested
against its hypothesis before it is swapped in. On 2026-11-11, after seeing worked examples, the owner
asked for ATR levels to be incorporated into the brief, "prior/previous +/- ... both", because they
"keep the plans in play", and asked that the work be judged by whether levels are reached, not by
profit.

The anchors (prior day high and low, premarket high and low), the 0.5 step, the 2 x ATR reach, the
1.5 x ATR stretch mark, the thinning rule and keeping the rungs out of the trade plan are this delivery
lane's proposal from the 2026-11-11 level, anchor and exits studies, not owner rulings. This spec is written by a FEAT-STRAT-001 delivery lane and is not
self-approved: it takes effect only when the owner merges the spec-only PR that adds it, and that merge
is the approval its `status` records. No implementation is written before that merge.

FEAT-STRAT-001 owns this change because every level is built in `lib.strat_levels.build_session_levels`
(the one level builder) and the step sizes belong in that feature's per-ticker parameter tables (#1784).

## Problem

The brief's levels come only from prior-period highs, lows and closes (day, week, month, quarter,
year), the parent bar and the premarket high and low (`PRIOR_PERIOD_CANDIDATES` and
`_CANDIDATE_ORDER`, `lib/strat_levels.py:1373-1383` on origin/main e1a17c2c). No level is measured from
another level in ATR; ATR is used only to window and space those levels.

Those levels bunch near the open and thin out farther away. When price runs past the last one, the
brief has nothing left to say where the move may go next. That is the case the owner raised on
QQQ 2026-06-05, where the prior low minus 1 x ATR would have been the next level down and the brief
does not build it. That session traded through and held every prior-low-minus-k x ATR level down to
2.5 x ATR.

## Evidence

Three read-only studies in the research lab, not in the repo, on SPY, QQQ and IWM:
`/mnt/project-files/stocks-scorecard/research/fable_lab/triggers_levels/level_reach/` (`tables.md`) and
its `anchors/` folder (`README.md`, `anchor_summary.csv`; `anchors.py` sha256 3463d004,
`summary.py` 4f5b888a; rerun `python -I -B anchors.py && python -I -B summary.py`). Windows: recent
2025-03-03 to 2026-11-10, split into primary from 2026-05-01 and holdout before it, and long 2016-03-01 to
2025-02-28. Reached means a 1-minute bar traded through the level; held means five consecutive 1-minute
closes stayed beyond it after the first touch. Ranges are 90%, 2,000 whole-day resamples, seed 7. The
level and anchor studies use the lab's structural set, which is wider than the brief's candidates (it adds 12-hour,
2-day and period-open levels), and ATR steps out to 3 x ATR, so the production replay in done_when is the
test that counts.

Level study (whether ATR levels are worth adding at all):

- ATR levels behave like any other level at the same distance. On the same session, same side and same
  0.05 x ATR distance cell, an ATR level and a structural level are reached within 0.6 points of each
  other in every window (35,669 pairs in the long window, -0.1 points above and below), and only one of
  the two is reached in 1.0 to 1.5% of pairs.
- About 8 in 10 touches of an ATR level go on to hold 5 minutes. Reach falls fast with distance:
  0.5 x ATR from the open 35%, 1 x ATR 9%, 2 x ATR under 1% (long).
- Holes in the ladder: on 26% of sides there is no structural level between 1 and 3 x ATR out, and the
  largest empty stretch out to 3 x ATR has a median of 1.51 x ATR.
- Context only, not used by this spec: with RSI(14) under 30 at the prior close, open +/- 1 x ATR was
  reached about three times as often as with RSI 60 to 70.

Anchor study (which level the ATR steps should hang from). Every ladder is the structural levels plus ATR
steps above and below each anchor; a level counts only when it is at least 0.25 x ATR past the open or
the level before it, so a ladder cannot win by packing levels near the open (this is why its reach
shares are lower than the level study's):

| Days that opened past the brief's trigger, next level in that direction | Long (2,172) | Recent (299) |
|---|---|---|
| Structural only: 1st level reached / 2nd held 5 min | 30% / 5% | 26% / 5% |
| + ATR from the prior close | 43% / 11% | 36% / 10% |
| + ATR from PDH, PDL, premarket high and low | 50% / 16% | 47% / 16% |
| 1st reached, these anchors minus prior close (pp, range) | +7.0 (+5.9, +8.1) | +10.4 (+7.2, +13.8) |
| 2nd held, these anchors minus prior close (pp, range) | +5.4 (+4.4, +6.4) | +5.7 (+3.5, +8.0) |

- On every session, both directions from the open, the same anchors beat the prior close by +4.3 pp
  (+3.9, +4.6) long and +4.7 (+3.8, +5.7) recent on the first level reached.
- The gain is largest on the with-gap side of gap days. Long window, 1st level reached against the prior
  close: gap up more than 0.75 x ATR +14.2 pp, gap down more than 0.75 +11.3, gaps of 0.25 to 0.75
  +10.4 up and +8.1 down; against the gap +1.2 to +1.6.
- Anchors on the open (-2.4 pp long) or the trigger were not better than the prior close, and on every
  session the trigger anchor was worse (-2.0 pp long).
- Week and month high/low anchors were also tested (long window, opened-through, spaced rule): week alone
  held the 2nd level 12.7% vs 16.3% for the four anchors; adding week and month on top raised it to 19.5%
  but needed 39 lines within 3 ATR instead of 26, and in the recent window the gain was +0.7 pp
  [0.0, +1.4]. Not adopted; the anchor list stays a policy row so it can be added later.
- With these four anchors there are about 25 to 30 levels within 3 x ATR of the open in a direction,
  against 9 to 14 for prior close or structural only, which is why this spec thins the rungs (Design 3).

Exits replay (whether ATR levels should be plan targets): `/mnt/project-files/stocks-scorecard/research/
fable_lab/triggers_levels/gap_open/atr4/` (`README.md`, `atr4.csv`). With the exits spec's plan and only
its targets changed to include ATR rungs from the four anchors, T1 was reached more often (long 24% to
35%, recent 25% to 39%) but each reach paid less, and the plan earned no more R: long -14.0 R (-64.1 to
+34.4) over 4,316 trades, holdout +5.0 R (-6.5 to +15.4), recent -7.8 R (-20.4 to +1.8), and using them on
gap days only gave -13.1, +1.4 and -5.1 R. So the rungs are shown as a map of where price can travel and
hold, and are never plan targets.

## Non-goals

- The trade plan. ATR rungs are never a trigger, a stop, a gate target or a plan target, and never enter
  the skipped list or plan R (Evidence: as targets they earned no more R). The exits spec's plan is
  unchanged.
- What the signal monitor gates on (`gate_targets`, the `{calls,puts}_t1_price` to `_t3_price` columns)
  and the `strat_levels` rows it reads: unchanged.
- RSI- or gap-conditioned ladders, and printing reach odds beside a level. Each is a follow-up that needs
  its own test.
- The movement statement, the insight report's levels and the persona plans.

## Approaches considered

1. ATR from the prior close only (this spec's first draft). Fewer levels, but the anchor study shows the
   prior-day and premarket extremes reach the next level more often on opened-through days (+7.0 pp long,
   +10.4 recent). Kept as the done_when reference build, one policy row away.
2. ATR from the prior close, PDH and PDL. Second best (+5.6 pp long, +7.7 recent). Rejected: below the
   chosen set in both windows.
3. ATR from the open or from the trigger. Not better than the prior close (open -2.4 pp long; trigger
   -2.0 pp on every session). Rejected.
4. Every anchor at every k with no thinning. The level study's version reached the next level 89 to 91%
   of the time only because levels were 0.04 x ATR apart. Rejected: unreadable.
5. ATR rungs as plan targets (this spec's second draft). T1 was reached more often, but the plan earned
   no more R in any window and less in the long and recent ones (Evidence). Rejected.
6. Chosen: ATR from PDH, PDL, the premarket high and the premarket low, every 0.5 x ATR out to 2 x ATR,
   both signs, thinned so no rung sits within the exits spec's spacing of its open-side neighbor or of a
   structural level, with stretch marked from 1.5 x ATR, printed as a map line in NEXT LEVELS. The anchor
   list and every value are data.

## Design

### 1. Parameters, per ticker and in policy

| Key | Where | Seed | Meaning |
|---|---|---|---|
| `atr_rung_anchors` | `level_param_policy`, method `policy` | `["PDH", "PDL", "PMK_H", "PMK_L"]` | the levels the steps hang from, in name priority |
| `atr_rung_step_atr` | `ticker_level_params`, `policy_seed` | 0.5 | distance between rungs, in ATR |
| `atr_rung_max_atr` | `ticker_level_params`, `policy_seed` | 2.0 | the farthest rung from its anchor, in ATR |
| `atr_rung_stretch_atr` | `ticker_level_params`, `policy_seed` | 1.5 | a rung at least this far from its anchor is marked stretch |

The thinning distance is the exits spec's `target_min_spacing_atr` (seed 0.25), not a new key. The
anchor list is policy-wide like `atr_basis`: it names levels, not distances, so it is one row the owner
changes without a code change, and the repo's no-literals rule (`tests/lib/test_level_params_structure.py`)
is kept by reading it from that row. Each name must be a trigger candidate name (`_CANDIDATE_ORDER`), so
`PDC` is a valid anchor and is how done_when builds the prior-close reference. Every distance is in the
policy's ATR basis (`atr_14`, Wilder ATR(14) of the last completed session).

`PMK_H` and `PMK_L` are the brief's names for the premarket high and low. `PMH` and `PML` already mean the
prior month's high and low, so the labels keep `PMK_H` and `PMK_L`.

### 2. ATR rungs

`_assemble` (where the premarket snapshot is applied, so a newer snapshot rebuilds the premarket rungs)
builds, for each anchor in the list that the session has, for whole i = 1, 2, ... while i x step <= max
(compared in cents), a rung at anchor + i x step x ATR named `{anchor}+{k}ATR` and one at
anchor - i x step x ATR named `{anchor}-{k}ATR`, k = i x step written by `multiple_text`. Each rung records
its anchor, multiple, sign and `stretch` (distance from its anchor in cents at least stretch x ATR in
cents). Two rungs on one cent take the name of the anchor listed first and the other is recorded as its
alias. An anchor the session lacks (no premarket snapshot, so no `PMK_H`) gives no rungs and is recorded
as `anchor_unavailable`. When any of the four rung keys or `target_min_spacing_atr` is not ok there are
no rungs and `atr_rung_status` records the first status that is not ok; there is no fallback
(CLAUDE.md 3.7).

Rungs are stored in a new `SessionLevels.atr_rungs`, never in `SessionLevels.levels` and never passed to
`_candidate_rungs` or `_pick_side`. So the trigger, the stop, `gate_targets`, the exits spec's plan
targets, skipped list and `target_status`, `persist_level_map`, the `strat_levels` table, PMG zones and
every reader of `levels` are exactly as on the base.

### 3. Thinning, so the line stays readable

Before thinning, four anchors give up to 32 rungs. On each side of the reference, walk the side's
structural candidates (as `_candidate_rungs` lists them) and its rungs together, in price order outward
from the reference:

- A structural candidate is always kept.
- A rung is kept only when it is at least `target_min_spacing_atr` x ATR in cents from the last kept
  price toward the reference (the reference itself when there is none), its open-side neighbor, and at
  least that far from every structural candidate. Otherwise it is dropped with the reason `neighbor` or
  `structural`; a rung on a structural candidate's own cent is dropped as `structural` and recorded as
  that level's alias. Structural levels always win.

Dropped rungs are recorded in level_basis (`atr_rungs_dropped`) and are not shown.

### 4. level_basis

level_basis gains optional keys: the kept and dropped rungs, `atr_rung_status`, the anchor list and the
four parameters with value, status, method_id and effective_from. `LEVEL_RULE_VERSION` does not change,
because no trigger, stop or target changes: `SessionLevels.from_basis` rebuilds the recorded rungs when
the keys are present and no rungs when they are absent, so stored briefs, their replays and the movement
statement's reach-rate population are unchanged. `published_prices` includes the kept rungs' cents,
because the brief prints them.

### 5. What the brief will look like

The exits spec's Design 8 ticker: reference 250.00, premarket high 252.10 and low 248.20, prior close
247.00, PDH 253.00, PDL 247.50, ATR(14) 14.00, windows 2.6 x ATR, spacing 0.25 x ATR = 3.50, steps of 7.00.
Before thinning the 32 rungs are PDH 253.00 +/- 7.00, 14.00, 21.00, 28.00 (260.00 to 281.00 and 246.00 to
225.00), PDL 247.50 +/- (254.50 to 275.50 and 240.50 to 219.50), PMK_H 252.10 +/- (259.10 to 280.10 and
245.10 to 224.10) and PMK_L 248.20 +/- (255.20 to 276.20 and 241.20 to 220.20). Thinning keeps 259.10,
266.10, 241.20 and 234.20: for example 254.50 is 1.50 from 253.00 (PDH), 260.00 is 0.90 from 259.10,
273.10 is 7.00 from 266.10 but 1.90 from 275.00 (PMH), and 225.00 (PDH-2ATR) is PML's own cent.

The CALLS and PUTS blocks are exactly the exits spec's Design 8 "After" text (calls T1 275.00 PMH,
T2 280.00 PQH, T3 285.00 PYH, skipped 253.00 PDH; puts T1 225.00 PML, T2 220.00 PQL, T3 215.00 PYL,
skipped 247.50 PDL and 247.00 PDC). The NEXT LEVELS Calls and Puts lines are unchanged, and a last line
is added:

```
    ATR levels, ATR(14) 14.00: up 259.10 (PMK_H+0.5), 266.10 (PMK_H+1); down 241.20 (PMK_L-0.5), 234.20 (PMK_L-1)
```

When the rungs are unavailable the line reads, for example, `ATR levels unavailable (params_unavailable).`

## Dependencies

- `docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md` (#1812): its
  `target_min_spacing_atr`, `policy_seed` calibration method and Design 8 brief text. This spec's
  implementation opens after that spec's implementation is on main and builds on it; it does not
  re-specify those rules.
- #1784 (per-ticker parameters), on main.

## Open questions for the owner

1. Reach out to 2 x ATR (seed) or 3? The studies ran to 3; past 2 x ATR levels were reached on 1% of
   sessions or fewer. Each is one policy row to change.
2. Should ATR rungs ever trigger or become targets? Not in this spec: as targets they earned no more R.

## Expected effect

Every brief with an ATR shows one more NEXT LEVELS line: the kept ATR levels from the prior day's high and
low and the premarket's high and low, above and below each, labelled with their anchor and multiple and
marked stretch from 1.5 x ATR, with no two shown levels closer than the ticker's spacing. Nothing else in
the brief, the plan, the resolver, the signal monitor, the movement statement or the insight report
changes.

## Capacity and cost

- **Volume:** four more policy rows; three more `ticker_level_params` rows per calibrated ticker per
  effective date (the history run writes about 2,980 per ticker per key); up to 32 rungs, kept and
  dropped, per session in level_basis. No new column.
- **Velocity:** no new query; the rows ride the one `load_level_params` query per run.
- **Wall-clock:** a walk over a few dozen prices per side per session.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief) shows the new line.
Only the `(FEAT-STRAT-001, DASHBOARD-01)` row of the Implementation-source notes table may describe this
implementation, as backend source and local tests only. Every other SITE byte stays unchanged.

After the merge, separately and never as a pre-merge box: apply the policy rows, run the history mode for
the three seeded keys, verify main's source and body identity in a fresh clone, complete the DOC main and
staging close-out with real evidence (a live brief showing the ATR line), retire the sidecar as the
product-delivery skill prescribes, and set the plan to `status: done` on a `docs/` branch.

## Risks

- **The studies' ladder is wider than the brief's.** Their structural baseline has more levels than the
  brief builds and their steps ran to 3 x ATR, so the brief's own gain may differ; done_when's replay
  measures it on the brief, against the base and against the prior-close build.
- **Premarket anchors move.** The premarket high and low change with each snapshot until 09:30, so their
  rungs do too; the brief prints the snapshot it was built from, as it already does for the trigger.
- **More to read.** The line adds up to a handful of prices per side; thinning keeps them at least the
  ticker's spacing apart.
- **Order of delivery.** This spec waits on the exits spec's implementation; if that changes before it
  lands, this spec is revised, not stretched.
