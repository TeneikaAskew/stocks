---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-15-feat-strat-001-plan-targets-gap-edges.md
branch: feature/feat-strat-001-plan-gap-edges
pr: 1972
status: ready
---

# The exits plan's targets also walk the brief's gap edges: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

Builds on the exits in thirds implementation (#1832), the ATR levels change (#1951) and the entry cutoff
change (#1967), all on main. The spec merged in #1970.

## Task 1: The policy row
Spec: § Design 1. Advances done_when[0].
- [x] Seed `plan_target_level_types` in `gcp/schema.sql` with `{"level_types": ["gap_high", "gap_low"]}` and `ON CONFLICT DO NOTHING`; name the key once in `lib/strat_levels.py` (`PLAN_TARGET_LEVEL_TYPES_KEY`, in `POLICY_WIDE_KEYS`)
- [x] `policy_wide_param` gives ok with value = the count of listed types, ok with 0 for an empty list, and input_unavailable for a missing list, an unknown type or a repeat (`tests/lib/test_level_params_loader.py`, `tests/gcp/test_level_params_consumers.py`)

## Task 2: The walk
Spec: § Design 3. Advances done_when[1], done_when[2].
- [x] `_plan_extra_rungs` turns the listed level types into rungs distinct by cent, dropping a candidate's cent and keeping the most recent gap's edge (high before low); `_pick_side` passes `_plan_targets` the ones past the trigger and inside the side's window; `_candidate_rungs` is unchanged
- [x] Test cases (a) to (e) and that only the plan's targets and skipped list move (`tests/lib/test_strat_levels.py::TestPlanGapEdges`, `::TestAtrRungsDisplayOnly::test_gap_edges_move_only_plan_targets`); the display-only golden runs with gap edges off

## Task 3: Stored briefs and brief copy
Spec: § Design 3, § Design 4. Advances done_when[3], done_when[4], done_when[5].
- [x] A basis built under the rule records `plan_target_level_types_status` and the list; `from_basis` applies the rule only when the marker is present
- [x] Test markerless bases with and without the key, a head-built basis, and `plan_inputs` on each (`tests/gcp/test_level_basis.py`); the Design 4 golden and the unchanged Design 8 goldens (`tests/lib/test_strat_levels.py`)

## Task 4: Experiment and evidence
Spec: done_when "Experiment", "Source identity", catalog. Advances done_when[6], done_when[7], done_when[8].
- [x] Reproduce the spec's Experiment through `plan_inputs` and `resolve_plan` on bases built with each tree's seeded policy
- [x] Rebind the 03-SITE note row, produce and verify the sidecar, update the catalog and PR lineage, and run the spec gate
- [ ] Insert the production `plan_target_level_types` row by Design 2's statement after the owner's yes, before the deploy, and record it
