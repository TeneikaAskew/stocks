---
feat_id: FEAT-STRAT-001
req_ids: [REQ-PLAYBOOK-001, REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-REL-001]
issues: []
canvases: []
site_source_notes: [DASHBOARD-01, DASHBOARD-21, INSIGHTS-07, INSIGHTS-08]
done_when:
  - "Target spacing: tests/lib/test_strat_levels.py passes a TestTargetSpacing class built on the Design 8 fixture (reference 250.00, premarket high 252.10 and low 248.20, prior close 247.00, PDH 253.00, PMH 275.00, PQH 280.00, PYH 285.00, PDL 247.50, PML 225.00, PQL 220.00, PYL 215.00, both windows 2.6, ATR(14) 14.00, target_min_spacing_atr 0.25): build_session_levels gives calls trigger 252.10 (PMK_H), targets 275.00, 280.00, 285.00 and skipped [253.00]; puts trigger 248.20 (PMK_L), targets 225.00, 220.00, 215.00 and skipped [247.50, 247.00]; stops 248.20 and 252.10 as on origin/main; with ATR(14) 24.00 (windows 1.6) calls targets are 275.00 and 285.00 with skipped [253.00, 280.00]; with the ticker_level_params row changed to 0.05 the calls targets are 253.00, 275.00, 280.00 with no code change; a candidate whose distance in cents equals the spacing in cents (price_cents half-up) is kept and one cent less is skipped; a ticker whose target_min_spacing_atr status is not ok keeps its trigger and stop, publishes no target and carries target_status equal to that status; in every case gate_targets equal origin/main's targets (calls 253.00, 275.00, 280.00) and the brief's calls_t1_price to calls_t3_price columns hold them while calls_plan_t1_price to calls_plan_t3_price hold the spaced targets; the first, second and third cases fail on origin/main, where the calls targets are 253.00, 275.00, 280.00"
  - "No numbers: tests/lib/test_level_params_structure.py passes unchanged (no new literal or module constant on the build_session_levels walk), test_the_walk_reaches_the_rules_it_must_cover also asserts that the spacing function is reached from build_session_levels, and tests/lib/test_level_params_copy.py asserts that no string literal in lib/strat_levels.py or gcp/premarket_playbook_resolver.py contains '0.25 x ATR', '0.5 x ATR', '10:00' or '1/3'; the spacing, the gap-fill threshold, the leg count and the cutoff are read only from LevelParams and level_param_policy"
  - "Policy and calibration: gcp/schema.sql seeds level_param_policy rows target_min_spacing_atr (method_id policy_seed, extra {\"seed\": 0.25}), gap_fill_flag_atr (policy_seed, extra {\"seed\": 0.5}), exit_legs (policy, extra {\"legs\": 3}) and entry_cutoff_et (policy, extra {\"time_et\": \"10:00\"}), each effective 2015-01-02 with ON CONFLICT DO NOTHING; lib.level_calibration.calibrate and HistoryCalibrator write one ticker_level_params row per ticker for each policy_seed key with value equal to the policy seed in force on effective_from, status ok, method_id policy_seed and the run's run_id; tests: a calibration of a fixture ticker returns both keys at their seeds, a later policy row with seed 0.30 effective D gives 0.30 from D and 0.25 before it, and a policy with no such row raises LevelParamsUnavailable naming the key; they fail on origin/main"
  - "Exit plan and copy: format_levels_for_brief renders the Design 8 fixture to exactly the Design 8 text (a golden-string test in tests/lib/test_strat_levels.py), including the cutoff line, the opened-through line ('at or above' for calls, 'at or below' for puts), the thirds read from exit_legs, the skipped line with the spacing in dollars, and a side with fewer targets than legs ending in 'hold to the close or the stop'; a side with no target past the spacing renders 'No target at least {spacing} past the trigger: hold to the close or the stop.'; a side whose target_status is not ok renders 'Targets unavailable ({target_status}): no exit plan for this side.' and neither of the previous two lines; a prior close published as a target on a session whose absolute gap (reference minus prior close) is at least gap_fill_flag_atr x ATR renders '(PDC, gap fill: gap {g} x ATR)' and a smaller gap renders '(PDC)'; the orb_only copy is unchanged; the tests fail on origin/main"
  - "Resolver scores the plan: tests/gcp/test_premarket_playbook_resolver.py passes a TestPlanOutcome class on synthetic 1-minute RTH bars for a call with trigger 100.00, stop 99.00, targets 101.00, 102.00, 103.00, cutoff 10:00 ET and three legs: an open at 100.05 gives plan_entry_status opened_through and plan_r NULL even when later bars trade 100.00 and 103.00, and so does an open of exactly 100.00; a later bar that first crosses at 09:40 by opening at 102.00 (low 102.00, high 103.20), followed by bars between 102.10 and 102.90 and a 15:59 close of 102.50, gives plan_fill_price 102.00, plan_exit 'close,close,close' and plan_r 0.1667 (T1 and T2 at or behind the fill are not exits and T3, touched only on the fill bar, is not an exit), where booking T1 and T2 would give a different value; a later bar opening at 103.40 after an entered fill at 100.00 books T3 at 103.00 for that leg, not 103.40; a first cross in the 10:00 bar gives late_cross and plan_r NULL, and in the 09:59 bar gives entered with plan_fill_price 100.00; entered then T1, T2 and a 15:59 close of 102.50 gives plan_r 1.8333 (one third each of 1, 2 and 2.5 R) and plan_exit 't1,t2,close'; entered then T1 then the stop gives plan_r -0.3333 and plan_exit 't1,stop'; a bar that touches both the stop and a target counts the stop first; a leg with one target gives one third at T1 and two thirds to the stop or close; a leg with a trigger and targets but stop None (the state test_no_stop_when_no_fresh_opposite builds) resolves without raising to plan_entry_status entered, plan_r NULL, plan_r_status stop_unavailable and a plan_exit, while its trigger_hit_ts, t1_hit_ts to t3_hit_ts, mae_pct, mfe_pct and eod_pnl_pct equal origin/main's for the same bars; a side whose level_basis target_status is params_unavailable, entered at 09:59 on bars that close at 102.50, gives plan_r NULL, plan_exit NULL and plan_r_status targets_unavailable, while a side with target_status ok and no target (every candidate inside the spacing) on the same bars gives plan_r 2.5, plan_exit 'close,close,close' and plan_r_status ok; on bars that reach 101.00 but not 102.00 with gate targets 100.50, 101.00, 101.50 and plan targets 101.00, 102.00, 103.00, plan_t1_hit_ts is that bar and plan_t2_hit_ts and plan_t3_hit_ts are NULL while t1_hit_ts to t3_hit_ts are as on origin/main; the existing columns (trigger_hit_ts, t1_hit_ts to t3_hit_ts, stop_hit_ts, eod_pnl_pct) are written exactly as on origin/main for the same bars; RESOLVER_VERSION changes; a resolve_one test with a stubbed engine, as the scorer spec's own resolve_one test does, inspects the executed UPDATE and its bound values: calls_ and puts_ plan_entry_status, plan_fill_price, plan_fill_ts, plan_r, plan_r_status, plan_exit and plan_t1_hit_ts to plan_t3_hit_ts are each in the SET list and bound from the two legs, a targets_unavailable leg binds NULL plan_r, plan_exit and hit timestamps, a stop_unavailable leg binds NULL plan_r with its plan_exit, and outcome_resolver_version is bound to the new RESOLVER_VERSION; tests/gcp/test_level_basis.py's persist test asserts that persist_to_cloud_sql writes calls_ and puts_ plan_t1_price to plan_t3_price to both premarket_analysis and premarket_analysis_history beside the unchanged t1_price to t3_price; the TestPlanOutcome, resolve_one and persist cases fail on origin/main (no plan columns)"
  - "level_basis and replay: level_basis records target_min_spacing_atr, gap_fill_flag_atr, exit_legs and entry_cutoff_et (value, status, method_id, effective_from) and a new LEVEL_RULE_VERSION feat-strat-001.v3; SessionLevels.from_basis on a v3 basis rebuilds the same targets, gate_targets and skipped list after the ticker_level_params row changes; from_basis on a stored feat-strat-001.v2 basis (which records no spacing) rebuilds the v2 targets unchanged; a replay of a session before the policy rows' effective_from that the history run did not cover gives target_status params_unavailable rather than unspaced targets; the tests fail on origin/main"
  - "Experiment through the production paths, before any production change: the implementation PR body shows, for SPY, QQQ and IWM over every session from 2025-03-03 to 2026-11-10 replayed through gcp/premarket_brief.py (BRIEF_AS_OF) with history-mode parameters and scored by the updated resolver, the count of ticker-days whose T1, T2 or T3 changes against origin/main, and, with one trade per ticker-day (the side whose plan_fill_ts is earlier; a tie is no trade), total plan_r (sides whose plan_r_status is not ok contribute no R and are counted per status) against today's rule (brief T1 all out, all day, gross R) per window (2026-05-01 to 2026-11-10 and 2025-03-03 to 2026-04-30), with the 90% day-resampled range (seed 7, 2,000 draws); the plan minus today must be above zero in both windows, as the Experiment section's +31.7 R and +63.9 R are; if either is not, the PR stays draft and the owner decides"
  - "Unchanged, each pinned by an existing or added test that passes on origin/main and on the implementation head: the trigger (side rule, broken rule, cents rule, window), the stop pick, the NEXT LEVELS ladder, orb_only reasons and copy, the CALL/PUT pick (_resolve_signal_status), signal-monitor fire decisions and alert targets (including an end-to-end test in tests/gcp/test_signal_monitor.py that builds the brief row from the Design 8 fixture and runs the monitor with level_gate_mode enforce and put_reanchor_mode enforce: a call bar reaching 254.00 leaves the leg post_t1 and the fire suppressed, as on origin/main, and the enforced put re-anchor's tracker T1 equals origin/main's), persona plans (lib/agents/trade_planner.py target_{persona}_{k}_r), and the 15-minute opening-range choice"
  - "Movement statement reach rates: tests/lib/test_movement_statement_level_basis.py, on its in-memory premarket_analysis with the plan columns added, passes a test with two resolved v3 rows built from the Design 8 call fixture (calls t1_price 253.00, plan_t1_price 275.00): one that reached 254.00 (t1_hit_ts set, plan_t1_hit_ts NULL) and one that reached 276.00 (both set), plus the session's live v3 row; _fetch_tracked_levels returns 253.00, not 275.00, as the calls T1 slot; the end-to-end movement statement's calls rungs are 252.10 and 253.00 as on origin/main, the 253.00 rung shows the T1 slot's 2 hits of 2, and no rung shows a rate of 1 of 2 (the plan columns are not read); a second test asserts that _reach_rate_sql reads t1_price with t1_hit_ts and never mixes a plan column with a gating one; on origin/main the first test fails because the fixture's v3 basis is not the current rule"
  - "Source identity (DASHBOARD-01, DASHBOARD-21, INSIGHTS-07, INSIGHTS-08): on the implementation PR head, scripts/maintenance/doc_source_snapshot.py produce and then verify, with the fixed ceilings and run from the committed HEAD, prove committed source and SITE body identity bound to this approved spec at the actual merge base, and the (FEAT-STRAT-001, DASHBOARD-01 / DASHBOARD-21 / INSIGHTS-07 / INSIGHTS-08) note rows carry that source_identity_sha256 with implementation and test prose for this PR"
  - "The FEAT-STRAT-001 catalog record and the PR traceability entry are updated; python3 scripts/gate/spec_gate.py --pr origin/main passes; the four policy rows, the history-mode run for the two seeded keys and the new premarket_analysis columns are applied to production only after the owner's yes and recorded separately"
status: approved
supersedes: null
---

# The premarket brief's targets are spaced by the ticker's ATR and its exit is planned in thirds

## Authority

Owner rulings in force: values are never hard-coded and are tailored to the actual ticker, using the
ticker's own ATR and never fixed dollar amounts (2026-11-08, recorded in
`docs/superpowers/specs/2026-11-10-feat-strat-001-per-ticker-params-r2.md`); and a change is tested
against its hypothesis before it is swapped in. The owner asked for the brief's exits and targets to be
changed on the evidence of the 2026-11-11 research lanes, with a picture of levels at 275, 280 and 285
for a ticker at 250.

The values below (0.25, 0.5, three legs, 10:00 ET) are this delivery lane's proposal from those
experiments, not owner rulings. This spec is written by a FEAT-STRAT-001 delivery lane and is not
self-approved: it takes effect only when the owner merges the spec-only PR that adds it, and that merge
is the approval its `status` records. No implementation is written before that merge.

FEAT-STRAT-001 owns this change because the targets are built in `lib.strat_levels._pick_side`
(`lib/strat_levels.py:2275-2355` on origin/main 7322f236), the one level builder, and the spacing value
belongs in that feature's per-ticker parameter tables (#1784).

## Problem

`_pick_side` takes the first unbroken, in-window candidate beyond the cleared mark as the trigger and
the next three as targets: `out.targets = [_rung(c, ref) for c in rungs[1:4]]`
(`lib/strat_levels.py:2349`). Nothing keeps a target away from the trigger or from the target before it.
The premarket high (low) sits on the cleared mark, so it is almost always the trigger (1,174 of 1,235
calls triggers and 1,138 of 1,235 puts triggers in the 08:30 replays), and the next structural level is
often a few cents beyond it.

Evidence (research lanes, `/mnt/project-files/stocks-scorecard/research/fable_lab/`, not in the repo):

- `level_hits/README.md`: T1 sits a median 0.21 x ATR from the trigger and 30% of T1s are closer than
  0.1 x ATR; of the T1s reached after a 5-minute hold, 48% were reached inside the hold itself.
- `triggers_levels/README.md`: with the brief's own trigger, stop and T1, all out, both sides, one cent a
  side, gap-through fills skipped, 2016-03-01 to 2025-02-28 (2,169 sessions, SPY, QQQ, IWM) made
  -88.7 R. Average win +0.68 R against average loss -0.93 R. Scaling out by thirds at the brief's own
  T1, T2 and T3 was +136.4 R better (range +55.7 to +216.5).
- The brief prints T1 as the whole exit (`format_levels_for_brief`, `lib/strat_levels.py:2573-2574`),
  and the resolver books the last target reached as the exit
  (`gcp/premarket_playbook_resolver.py:316-330`).

## Non-goals

- The trigger rule. "Nearest ladder level to the open" looked best but is not proven: 64% of its entries
  fall in the first minute, where 1-minute bars cannot order prints, and scoring same-minute days as
  losses turns it negative. It is a named follow-up that needs tick data or paper fills.
- The stop. It stays the nearest in-window level on the other side of the reference. A 0.25 x ATR stop
  held to the close did better over nine years (+287.9 R) but is the most cost-sensitive variant
  (-12 R at 3 cents a side) and is a separate decision.
- Breakeven or trailing stops after T1, and re-entry on a push through: tested and no better.
- Persona plans (`lib/agents/trade_planner.py`, `target_{persona}_{k}_r`), signal-monitor fires and
  alerts, the volume and isolated-extreme premarket rules, the gap odds line and report-day re-cuts.
- The resolver's gap-through fill and same-bar ordering for its existing columns: the FEAT-SIGNAL-001
  scorer spec fixes those (Dependencies).
- Option pricing. Every number here is share R.

## Approaches considered

1. Push T1 out and exit all at once (the next level at least 0.25 x ATR away). Long window +144.1 R
   better than today, holdout +16.5 R, ranges across zero in both recent windows. Rejected: thirds did
   better everywhere it was tested.
2. Chosen: keep the brief's trigger, stop and candidate list; skip any candidate closer than the ticker's
   spacing (0.25 x ATR seed) to the trigger or to the target before it; plan one third at each of up to
   three targets, the rest held to the close or the stop; no entry when the open is already through the
   trigger; no new entry after 10:00 ET.
3. The lane's wider ladder (12HR candle, 2-day candle, ATR bands, opens) as targets (`lad0.25_3`,
   +231.9 R better over nine years). Rejected for now: those levels are not built by the brief, and the
   brief's own candidate list did as well (+269.1 R, Experiment).
4. Mark late triggers "smaller expected move" instead of banning them (`level_hits` H-D). Rejected:
   untested as a trading rule, while the ban held in both recent windows (Design 4).

## Design

### 1. Minimum target spacing, per ticker

New `ticker_level_params` key `target_min_spacing_atr`, in the policy's ATR basis. In `_pick_side`,
after the trigger is chosen, walk the side's rungs beyond it in order with `prev` = the trigger:

```
spacing_cents = price_cents(spacing * atr)
for c in rungs[1:]:
    if abs(c.cents - prev.cents) >= spacing_cents:   # equal is kept
        targets.append(c); prev = c
    else:
        skipped.append(c)
    stop when len(targets) == legs   (Design 2)
```

`SideLevels` gains `skipped` (the candidates passed over, each with its distance in ATR) and
`target_status` (`ok` or the parameter's status). When the parameter's status is not ok the side keeps
its trigger and stop, publishes no target and records the status; there is no unspaced fallback
(CLAUDE.md 3.7). That side is not a plan: the brief says "Targets unavailable ({target_status}): no
exit plan for this side." instead of any target or hold line, and the resolver scores it as unavailable
(Design 6). It is a different state from an ok spacing that finds no candidate far enough away, which
is a valid plan holding every leg to the close or the stop (Design 2). A level the walk skips stays on
NEXT LEVELS and on the candidate list, so the brief
still shows it.

`SideLevels` also keeps `gate_targets`, the first three rungs past the trigger with no spacing, exactly
origin/main's `targets` (`rungs[1:4]`). They are not shown as targets in the brief. They exist because
the signal monitor's leg trackers gate fires on T1: `gcp/signal_monitor.py:648-672` builds each
`LegStateTracker` from the brief's `calls_t1_price` / `puts_t1_price` (or, with `put_reanchor_mode`
enforce, the re-anchor's `t1`), and with `level_gate_mode` enforce `:1533-1539` suppresses fires once a
leg is `post_t1`. On the Design 8 fixture a bar reaching 254.00 is `post_t1` with origin/main's T1 of
253.00 but only `triggered` with a spaced T1 of 275.00, which would let a suppressed alert fire. So:

- The structured columns `{calls,puts}_t1_price`, `_t2_price`, `_t3_price` (`gcp/premarket_brief.py:1526-1543`)
  keep origin/main's meaning and are written from `gate_targets`; the monitor's trackers, the resolver's
  existing outcome columns and every other reader of those columns see the same prices as today.
- The spaced targets are written to new columns `{calls,puts}_plan_t1_price`, `_plan_t2_price`,
  `_plan_t3_price` and recorded in level_basis; the brief text, the resolver's plan columns (Design 6)
  and the insight report read them. The resolver also records whether each spaced target was reached,
  in its own `{side}_plan_tK_hit_ts` columns (Design 6), so a reach of 253.00 is never counted as a
  reach of 275.00.
- The movement statement does not read the spaced targets. Its rungs are the NEXT LEVELS ladder
  (`SessionLevels.to_level_map`, `call_levels=list(self.long.ladder)`), which this spec leaves unchanged:
  the trigger and the nearest rung past it, 252.10 and 253.00 on the Design 8 call fixture. Its reach
  rates, `_reach_rate_sql` (`lib/movement_statement.py:286`) over `{side}_tK_price` and
  `{side}_tK_hit_ts` and `_fetch_tracked_levels` (`:406`) over `{side}_tK_price`, describe exactly
  those prices because the gating columns keep their origin/main meaning. Pointing either reader at the
  spaced targets would attach a 275.00 rate to nothing on the ladder, and pointing the tracked prices at
  level_basis while the rates stay on the gating columns would put the 253.00 rate on 275.00; both are
  ruled out, and done_when pins the pairing.
- `_reanchor_put_leg` (`gcp/signal_monitor.py:527-547`) takes its `t1` to `t3` from the re-anchored
  side's `gate_targets`, so `puts_reanchor_t1` to `_t3` and an enforced re-anchor's tracker T1 are
  unchanged.

Changing what the monitor gates on is not part of this spec; it needs its own experiment.

Calibration: a new method `policy_seed`. `lib.level_calibration` writes, for every ticker it calibrates,
one row whose value is the seed in the policy row in force on `effective_from` (0.25 on day one), status
ok, `method_id` policy_seed. The value is per ticker in the table, so a later per-ticker method replaces
the seed with a policy row and a run, not a code change; any such method must first beat the seed in
the Experiment's test. 0.25 is the seed because it is where the gain levels off (Experiment: 0.15 gave
+206.3 R, 0.25 +269.1 R, 0.35 +270.2 R over nine years against today) and it is the distance
`level_hits` H-B proposed from the T1 distribution.

### 2. Exit plan in thirds

A policy row `exit_legs` (extra `{"legs": 3}`) replaces the slice bound: up to `legs` targets are
published and each leg is 1/legs of the position. When fewer targets pass the spacing, the unassigned
legs are held to the close or the stop. The stop does not move after a target is reached (breakeven and
trailing were worse: -24 R holdout, -45 R long on the ladder trigger). The leg count is plan shape, not
a distance, so it is policy-wide; Open question 2 asks whether it should be per ticker.

### 3. A trigger already passed at the open is not an entry

If the 09:30 bar opens at or beyond a side's trigger, that side has no entry that session, even if price
later comes back and crosses it. The brief says so on each side, with the equality spelled out ("at
or above" for calls, "at or below" for puts), so the copy and the resolver's `opened_through` agree on an
open exactly at the trigger. Evidence: filling at the open when
already through, against waiting for a cross, with the lane's 0.25 x ATR stop and 0.5 x ATR target, was
-18.1 R primary, -13.7 R holdout and -221.4 R long (only the long range, -372 to -68, is clear of zero),
and the Experiment's whole-spec result already scores this rule.

### 4. No new entry after 10:00 ET

A policy row `entry_cutoff_et` (extra `{"time_et": "10:00"}`). A side whose first cross of the trigger
comes in a bar starting at or after the cutoff has no entry; a trade entered before it runs to its
targets, stop or close. The brief prints the window on each side.

Ban, not label, because: for today's trade the cutoff added +13.5 R (range +4.0 to +22.3) primary and
+27.0 R (+7.9 to +46.9) holdout; for this spec's plan it added +14.5 R (+0.3 to +27.7) primary and
+37.3 R (+11.0 to +63.6) holdout; and `level_hits` found holds that start at 10:00 or later reach
0.5 x ATR half as often (14% against 31%, every year since 2016) and lost per trade in 2025 to 2026
(-0.09 R against +0.09 R). Over 2016 to 2025 the cutoff's effect on the plan is -39.2 R with a range of
-131.3 to +52.7 (SPY -13.9, QQQ -12.1, IWM -13.3, every range across zero), so it is not proven there,
and IWM's holdout leans against it (Open question 1). It is one row, so the owner can move or drop it
without a code change.

### 5. Prior close as a gap-fill target

`gappers_events/README.md`: on gaps of 0.50 to 1.00 x ATR the prior close is reached the same day 29% of
the time (2016 to 2025), so it must not stand as an unflagged target. New key `gap_fill_flag_atr`
(policy_seed, seed 0.5): when a published target is the prior close (PDC, or a level aliased to its cent)
and the absolute gap, reference minus prior close, is at least that multiple of ATR, the target is
labelled "gap fill" with the gap in ATR. The label does not move or remove the target. The gap odds
table is a follow-up.

### 6. The resolver scores the plan

`gcp/premarket_playbook_resolver.py` reads the side's targets, stop, legs and cutoff from the row's
`level_basis` (falling back to the structured columns only for a basis of rule v2, which has no plan)
and writes, per side, new nullable `premarket_analysis` columns:

| Column | Meaning |
|---|---|
| `{calls,puts}_plan_entry_status` | `entered`, `opened_through`, `late_cross`, `no_cross`, `no_trigger` |
| `{calls,puts}_plan_fill_price`, `_plan_fill_ts` | the trigger, or the bar's open when a later bar gaps past it |
| `{calls,puts}_plan_r` | sum over legs of share x (exit minus fill) x sign / abs(fill minus stop), gross; NULL unless `_plan_r_status` is `ok` |
| `{calls,puts}_plan_r_status` | `ok`, `targets_unavailable` (level_basis `target_status` not ok), `stop_unavailable` (the side published no stop), `not_entered` (entry status other than `entered`); the first that applies |
| `{calls,puts}_plan_t1_hit_ts` to `_plan_t3_hit_ts` | first bar at or after the trigger bar reaching each plan target, by the same walk and rule as the existing `t1_hit_ts` to `t3_hit_ts`; no current reader shows them, and the movement statement does not read them (Design 1) |
| `{calls,puts}_plan_exit` | the legs' exits in order, for example `t1,t2,close` |

A side can have a trigger and targets but no stop: `_pick_side` leaves `stop` None when no candidate on
the other side passes the stop window (pinned by
`tests/lib/test_strat_levels_playbook.py::test_no_stop_when_no_fresh_opposite`). Its risk is undefined,
so the resolver writes the entry status, fill and `plan_exit` (each leg exiting at its target or the
close, with no stop) as usual, `plan_r` NULL and `plan_r_status` `stop_unavailable`, never raises, and
still writes the existing outcome columns for that side as origin/main does.

A side whose level_basis `target_status` is not ok published no plan, so the resolver writes its
`plan_entry_status`, fill and fill time as usual, `plan_r` and `plan_exit` NULL, `plan_r_status`
`targets_unavailable` and no plan hit timestamps, and never scores it as an all-close trade. A side
whose `target_status` is ok and whose walk found no target is a valid plan: every leg exits at the stop
or the close and `plan_r_status` is `ok`.

Within the trade a target fills at its price, the stop at its price or the bar's open on a gap through
it, and a bar touching both counts the stop first, as in the Experiment. Plan exits are causal, by the
same rules the scorer spec sets for the existing columns: when the fill is a later bar's open beyond the
trigger, a plan target at or behind that fill is not an exit, and its leg is held to the stop or the
close like a leg with no target (Design 2); a target touched only on the fill bar is not an exit, since
targets count from the next bar; and a later bar opening beyond a target books that target's price, not
the better open. The plan hit timestamps keep the existing walk's rule and are not exits. The scorer spec's rules for
fills and same-bar order govern the existing columns; where they differ from these, the implementation
PR shows both. Existing columns keep their meaning, and `RESOLVER_VERSION` moves past the scorer spec's
`2026-11-11.v2` so re-resolved rows can be told apart.

### 7. level_basis and rule version

`LEVEL_RULE_VERSION` becomes `feat-strat-001.v3`. level_basis records the spaced targets, the skipped
levels and `gate_targets` per side, and the four new parameters with value,
status, method_id and effective_from. `SessionLevels.from_basis` rebuilds a v3 basis with its recorded
values and a v2 basis with the v2 rule (no spacing, three targets), so stored briefs and their replays do
not change. The movement statement's reach rates count rows of the current rule version only, as #1784
set, so its v3 population starts empty (Risks).

### 8. What the brief will look like

A ticker at 250.00 (premarket VWAP), premarket high 252.10 and low 248.20, prior close 247.00, ATR(14)
14.00, windows 2.6 x ATR on both sides, so the spacing is 0.25 x 14.00 = 3.50. Levels above: PDH 253.00,
PMH 275.00, PQH 280.00, PYH 285.00; below: PDL 247.50, PML 225.00, PQL 220.00, PYL 215.00.

Today:

```
  CALLS above 252.10 (PMK_H)
    Stop: 248.20 (PMK_L)
    T1: 253.00 (PDH)
    T2: 275.00 (PMH)
    T3: 280.00 (PQH)
    Room to trigger: 0.84%
```

After:

```
  CALLS above 252.10 (PMK_H), new entries 09:30 to 10:00 ET
    No entry if the open is at or above 252.10.
    Stop: 248.20 (PMK_L)
    T1: 275.00 (PMH), sell 1/3
    T2: 280.00 (PQH), sell 1/3
    T3: 285.00 (PYH), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 253.00 (PDH)
    Room to trigger: 0.84%

  PUTS below 248.20 (PMK_L), new entries 09:30 to 10:00 ET
    No entry if the open is at or below 248.20.
    Stop: 252.10 (PMK_H)
    T1: 225.00 (PML), sell 1/3
    T2: 220.00 (PQL), sell 1/3
    T3: 215.00 (PYL), sell the last 1/3, or hold to the close or the stop
    Skipped, closer than 0.25 x ATR(14) = 3.50: 247.50 (PDL), 247.00 (PDC)
    Room to trigger: 0.72%
```

The same levels on a ticker whose ATR(14) is 24.00 (spacing 6.00): calls T1 275.00, T2 285.00 (280.00
is 5.00 past 275.00, under 6.00, so skipped), and the last third is held to the close or the stop. The
gap from the prior close is 3.00, 0.21 x ATR, so nothing is flagged; had the ticker gapped from 241.00
(0.64 x ATR), the puts T1 would be the prior close, printed `T1: 241.00 (PDC, gap fill: gap 0.64 x ATR),
sell 1/3`.

## Experiment

Hypothesis: spacing the brief's own targets by the ticker's ATR, scaling out by thirds, and taking no
entry that is already through at the open or first crosses after 10:00 ET, does better than today's
all-out T1, with the brief's trigger and stop unchanged.

Data (read only, not in the repo): 1-minute bars with extended hours, Alpha Vantage,
`/mnt/project-files/stocks-scorecard/inputs/bars_raw/{SPY,QQQ,IWM}_1min_YYYY-MM.csv` (2025-03 to
2026-11-10) and `/mnt/project-files/stocks-scorecard/research/fable_lab/data/bars_1min/` (2016-01 to
2025-02); daily bars `/mnt/project-files/strat-verify/ftfc-replay/raw/{SPY,QQQ,IWM}_daily_adjusted.csv`;
the brief's 08:30 replays of main (`triggers_levels/inputs/brief_rows.json`, 1,236 ticker-days). Levels
for 2016 to 2025 come from the brief's own `build_session_levels` on daily bars and the brief's filtered
premarket snapshot (the lane read origin/main dded588d).

Windows: primary 2026-05-01 to 2026-11-10 (130 sessions), holdout 2025-03-03 to 2026-04-30 (282),
long 2016-03-01 to 2025-02-28 (2,169). Both sides: each day the first side to cross its trigger is the
one trade per ticker-day, a same-minute tie is no trade. Brief direction: only the side the brief
called. One cent a share each side. A trigger already passed at the open is no trade. Entry at the
trigger or a later bar's open beyond it; a bar touching stop and target counts the stop; open trades
close at 15:59. Half days dropped. R is net profit over entry-to-stop risk. Ranges are 90%, resampling
whole days 2,000 times, seed 7.

The lane's commands rebuild the sessions and every variant; the spec check reuses them read only:

```bash
LANE=/mnt/project-files/stocks-scorecard/research/fable_lab/triggers_levels
WT=/tmp/wt-triggers_levels                      # any clean checkout of the stocks repo
git -C /home/claude/stocks worktree add --detach $WT origin/main
PY=/home/claude/venv/bin/python                 # pandas, numpy, pyarrow
cd $LANE
$PY -I code/build_sessions.py $WT      # work/sessions.pkl
$PY -I code/build_long.py $WT          # work/sessions_long.pkl
$PY -I code/sim.py                     # results.csv
$PY -I code/sim.py --long              # results_long.csv
cd /tmp
$PY -I -B $LANE/spec_check/own_spacing.py $LANE $LANE/spec_check/out   # spacing 0.15/0.25/0.35 vs today
$PY -I -B $LANE/spec_check/cost_ticker.py $LANE                       # cost and per ticker
$PY -I -B $LANE/spec_check/combined.py $LANE                          # the whole spec minus today
$PY -I -B $LANE/spec_check/b10_ticker.py $LANE                        # the 10:00 cutoff per ticker
```

`spec_check/` (sha256 own_spacing.py c9be31f2, cost_ticker.py 0055e5bf, combined.py 572f48f2,
b10_ticker.py e2dade8f) tests the
exact rule of Designs 1 and 2: targets only from the brief's own candidates (prior-period highs, lows
and closes, parent bar, premarket high and low), each at least spacing x ATR(14) past the trigger or the
previous target, one third each, the rest to the close. It does not apply the trigger window to targets.

Results, both sides, total R (range); "vs today" is minus brief T1 all out, all day:

| Rule | Primary | Holdout | Long |
|---|---|---|---|
| Today: brief T1 all out | +4.7 (-24.7, +36.3) | -36.2 (-76.7, +4.4) | -88.7 (-229.6, +52.5) |
| Brief T1/T2/T3 by thirds, no spacing, vs today | +12.7 (-3.3, +29.6) | +8.2 (-17.1, +32.5) | +136.4 (+55.7, +216.5) |
| Spacing 0.15, thirds, vs today | +16.6 (-6.0, +42.0) | +22.5 (-16.7, +59.7) | +206.3 (+76.2, +331.8) |
| Spacing 0.25, thirds, vs today | +17.2 (-7.2, +44.4) | +26.6 (-17.0, +69.8) | +269.1 (+120.4, +418.5) |
| Spacing 0.35, thirds, vs today | +17.2 (-8.6, +46.3) | +29.9 (-17.1, +75.8) | +270.2 (+110.9, +427.3) |
| 10:00 cutoff on the 0.25 plan (before-10 minus all day) | +14.5 (+0.3, +27.7) | +37.3 (+11.0, +63.6) | -39.2 (-131.3, +52.7) |
| Whole spec (0.25, thirds, 10:00 cutoff) vs today | +31.7 (+7.8, +57.2) | +63.9 (+22.2, +103.5) | +229.8 (+86.0, +373.1) |
| Whole spec, brief direction only, vs today | +24.8 (+10.5, +40.0) | +10.8 (-13.0, +37.0) | n/a (no brief before 2025-03) |

Totals of the whole spec: +36.4 R primary (211 trades), +27.8 R holdout (467), +141.1 R long (3,840).
Today's rule with the 10:00 cutoff alone: +18.2, -9.2 and -56.8 R.

Cost, both sides, the 0.25 plan with the cutoff, R at 1 / 2 / 3 / 5 cents a side: primary +36.4 / +34.3 /
+32.3 / +28.1; holdout +27.8 / +22.2 / +16.7 / +5.7; long +141.1 / +4.3 / -132.6 / -406.4 (median risk
265, 201 and 89 cents). Per ticker at 1 cent, primary / holdout / long: SPY +11.5 / +11.1 / +1.0, QQQ
+14.7 / +27.1 / +12.7, IWM +10.2 / -10.4 / +127.5.

Reading: the whole spec beats today in all three windows with every range above zero, both sides. With
the brief's CALL/PUT direction it is ahead in the primary window and not proven in the holdout: better
exits do not repair a wrong direction call. The long-window result depends on cost: at 2 cents a side it
is flat, at 3 cents negative, when prices and ATR were smaller; the recent windows hold to 5 cents.

## Dependencies

- The scorer spec that fixes the resolver's gap-through fill and same-bar stop and target order
  (`gcp/premarket_playbook_resolver.resolve_leg`):
  `docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md` (FEAT-SIGNAL-001, merged
  as #1807). Design 6's implementation opens after that spec's implementation is on main, and this spec
  does not re-specify those rules.
- #1784 (per-ticker parameters), on main.

## Open questions for the owner

1. The 10:00 cutoff is policy-wide. On the plan, IWM's holdout leans against it (-3.4 R, range -15.3 to
   +7.4) while SPY (+29.4 R, +15.6 to +44.0) and QQQ (+11.3 R, -1.0 to +24.0) gain, and all three lean
   negative over 2016 to 2025. Keep it for all tickers, or calibrate it per ticker later?
2. Three equal legs for every ticker, or a per-ticker split once there is evidence for one?

## Expected effect

Every brief side with a trigger shows up to three targets at least 0.25 x its own ATR apart, a thirds
exit, the 09:30 to 10:00 entry window and the opened-through rule. T1 changes on most ticker-days
because the premarket extreme's nearest neighbour is usually inside the spacing (counted in
done_when 7). The insight report's key levels read the same targets through level_basis; the movement
statement keeps its ladder and its rates on the gating levels, and the resolver records spaced-target
reaches separately. The signal monitor keeps gating on the unspaced T1 (`gate_targets`, Design 1), so its
fire decisions and its put re-anchor do not change in any `level_gate_mode` or `put_reanchor_mode`. The
resolver reports a plan R per side.

## Capacity and cost

- **Volume:** four more policy rows, two more `ticker_level_params` rows per calibrated ticker per
  effective date (the history run writes them for every session from 2015-01-02, about 2,980 rows per
  ticker per key), and twenty-four nullable columns on `premarket_analysis` (six plan target
  prices from Design 1, twelve plan outcome columns and six plan hit timestamps from Design 6), plus
  the six plan target prices on `premarket_analysis_history`, which mirrors the brief's columns.
- **Velocity:** no new query: the policy rows ride the one `load_level_params` query per run, and the
  resolver already reads each row's level_basis and the day's bars.
- **Wall-clock:** in-process walks over at most a few dozen candidates per side; the history run adds
  two constant rows per session to a job that already computes 23 parameters per session.
- **Cost:** $0; no new job, schedule or resource.

## Source identity and close-out

`lib/`, `gcp/` and `tests/` are inside SITE's watched scope. DASHBOARD-01 (the brief), DASHBOARD-21 (the
movement statement, whose reach-rate population restarts at rule v3 while its rungs stay), INSIGHTS-07
(the report plan's levels from level_basis) and
INSIGHTS-08 (the report's key-levels block) show or read the changed targets. Only the
`(FEAT-STRAT-001, <component>)` rows of the Implementation-source notes table for those four may
describe this implementation, as backend source and local tests only. Every other SITE byte stays
unchanged.

After the merge, separately and never as a pre-merge box: apply the policy rows and the new columns,
run the history mode for the two seeded keys, verify main's source and body identity in a fresh clone,
complete the DOC main and staging close-out with real evidence (a live brief showing spaced targets and
the resolver writing plan columns), retire the sidecar as the product-delivery skill prescribes, and set
the plan to `status: done` on a `docs/` branch.

## Risks

- **Cost in older, cheaper years.** The nine-year gain is mostly gone at 2 cents a side. Option trades
  carry wider spreads and decay; the recent windows are the better guide for today's prices.
- **Direction is still the weak part.** With the brief's CALL/PUT pick the plan is not proven in the
  holdout (+10.8 R, range -13.0 to +37.0).
- **Recent windows are short.** Most of the gain is shown in the primary window (130 sessions) and the
  holdout (282); done_when 7 repeats the test through the production replay before anything ships.
- **Fewer full plans.** With spacing, more sides have one or two targets; the unassigned legs ride to
  the close, which is what the experiment scored.
- **Reach-rate history restarts** for the movement statement under rule v3.
- **Spacing in the lane ignored the trigger window for targets.** The production builder windows them;
  done_when 7 measures the difference.
