---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-07-feat-insight-001-trigger-distance-cap.md
branch: fix/feat-insight-001-trigger-distance-cap
pr: 1746
status: in-progress
---

# Insight planner trigger distance cap implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: Regression tests on the 2026-11-06 inputs
Spec: § Problem 1 and 2, § Design. Advances done_when[0].
- [x] Write `tests/lib/test_trade_planner_distance_cap.py` on QQQ, IWM and SPY 2026-11-06 values rebuilt from Alpha Vantage bars, plus the own-ATR, long-tie and pre_low cases
- [x] Run: `python3 -m pytest tests/lib/test_trade_planner_distance_cap.py` (FAIL on origin/main: 6 of 11)
- [x] Implement `_TOUCH_TOLERANCE` and the `_within_staleness_window` filter in `select_trigger_and_regime`
- [x] Run again (PASS)

## Task 2: Existing tests that pinned the uncapped walk
Spec: § Design, consequence paragraph. Advances done_when[1].
- [x] Rewrite the tests named in done_when[1]
- [x] Remove the blue-sky synthesis, its constants, the `PlanContext.blue_sky_atr_offset` field and its lookup; rewrite the four synthesis tests to expect orb_only and delete the override test
- [x] Run `python3 -m pytest tests/lib/test_trade_planner.py` (PASS)

## Task 3: Nothing else moves
Spec: § Non-goals. Advances done_when[2].
- [x] Confirm `lib/strat_levels.py` is not in the diff
- [x] Run `tests/agents`, `tests/lib` and `tests/gcp`

## Task 4: Evidence in the PR body
Spec: § Expected effect. Advances done_when[3].
- [x] Replay 2026-11-06 with origin/main and this branch; put old and new triggers, persona entry zones and fill against the session low in the PR body

## Task 5: Source identity
Spec: § Source identity and close-out. Advances done_when[4].
- [ ] After the spec is on main, merge main, add the `(FEAT-INSIGHT-001, INSIGHTS-07)` note row with the producer's source hash, commit, produce the sidecar from the committed body, commit it and run `verify` from the committed HEAD

## Task 6: close
Spec: § Source identity and close-out. Closes done_when[5].
- [x] Update the 02-FEATURE-CATALOG FEAT-INSIGHT-001 record (Last reviewed, Next action)
- [x] Add this PR to 12-PR-ISSUE-TRACEABILITY once it has a number, and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`, which needs read access to solyra's issues)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
