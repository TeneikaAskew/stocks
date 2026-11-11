---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-11-feat-strat-001-brief-exits-in-thirds.md
branch: fix/feat-strat-001-brief-exits-in-thirds
pr: 1832
status: ready
---

# The brief's targets are spaced by the ticker's ATR and its exit is planned in thirds: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: Space the targets per ticker
Spec: § Design 1, § Design 7. Advances done_when[0], done_when[1], done_when[5].
- [x] Write failing tests in `tests/lib/test_strat_levels.py::TestTargetSpacing` on the Design 8 fixture (`tests/lib/session_levels_helpers.py::d8_basis`)
- [x] Implement `_plan_targets` in `lib/strat_levels.py`, keep the first three rungs as `gate_targets`, bump `LEVEL_RULE_VERSION` to `feat-strat-001.v3` and rebuild a v2 basis with the v2 rule
- [x] Assert in `tests/lib/test_level_params_structure.py` that `_plan_targets` is reached, and forbid the exit values in string literals in `tests/lib/test_level_params_copy.py`

## Task 2: Policy rows and calibration
Spec: § Design 1, § Design 2, § Design 4, § Design 5. Advances done_when[2].
- [x] Seed the four `level_param_policy` rows in `gcp/schema.sql`; load `exit_legs` and `entry_cutoff_et` as policy-wide parameters
- [x] Write the `policy_seed` keys in `lib.level_calibration.calibrate` and `HistoryCalibrator`, raising `LevelParamsUnavailable` when a seeded row is missing; tests in `tests/lib/test_level_calibration.py` and `tests/gcp/test_calibrate_level_params.py`

## Task 3: The brief's copy and columns
Spec: § Design 3, § Design 8. Advances done_when[3], done_when[0].
- [x] Render the exit plan in `format_levels_for_brief` (`tests/lib/test_strat_levels.py::TestExitPlanCopy`)
- [x] Write `plan_t1..t3_price` beside the unchanged `t1..t3_price` through `gcp/premarket_brief.py::structured_playbook_columns` and add the six columns to both tables in `gcp/schema.sql`

## Task 4: Consumers unchanged
Spec: § Design 1, § Non-goals. Advances done_when[7], done_when[8].
- [x] The signal monitor's put re-anchor reads `gate_targets`; end-to-end test in `tests/gcp/test_signal_monitor.py` passes on origin/main and on this head
- [x] The movement statement reads only the gating columns (`tests/lib/test_movement_statement_level_basis.py`)

## Task 5: The resolver scores the plan
Spec: § Design 6, § Dependencies. Advances done_when[4].
- [ ] Add the plan outcome columns and `RESOLVER_VERSION` change once the FEAT-SIGNAL-001 scorer implementation is on main

## Task 6: Experiment and evidence
Spec: § Experiment, § Source identity and close-out. Advances done_when[6], done_when[9], done_when[10].
- [ ] Replay SPY, QQQ and IWM through `gcp/premarket_brief.py` with history-mode parameters and score both windows
- [x] Rebind the four 03-SITE note rows, produce and verify the sidecar, update the catalog and PR lineage, and run the spec gate
