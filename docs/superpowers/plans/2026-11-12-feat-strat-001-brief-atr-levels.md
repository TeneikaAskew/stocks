---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-11-feat-strat-001-brief-atr-levels.md
branch: fix/feat-strat-001-brief-atr-levels
pr: 1845
status: ready
---

# The brief shows ATR levels from the prior day and premarket high and low, display only: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

Stacked on the exits in thirds implementation (#1832, branch `fix/feat-strat-001-brief-exits-in-thirds`),
whose `target_min_spacing_atr`, `policy_seed` method and Design 8 fixture this spec builds on.

## Task 1: Policy rows and the loader
Spec: § Design 1. Advances done_when[3].
- [x] Seed `atr_rung_anchors` (policy) and `atr_rung_step_atr`, `atr_rung_max_atr`, `atr_rung_stretch_atr` (policy_seed) in `gcp/schema.sql`
- [x] Read the anchor list like `atr_basis` in `load_level_params`, raising `LevelParamsUnavailable` when the row is missing, empty or names a level that is not a trigger candidate (`tests/lib/test_level_params_loader.py`)
- [x] Calibrate the three numeric keys at their seeds through `POLICY_SEEDED_KEYS` (`tests/lib/test_level_calibration.py`, `tests/gcp/test_calibrate_level_params.py`)

## Task 2: ATR rungs and thinning
Spec: § Design 2, § Design 3. Advances done_when[0], done_when[1], done_when[2].
- [x] Write failing `tests/lib/test_strat_levels.py::TestAtrRungs` on the Design 8 fixture
- [x] Build the rungs in `_atr_rung_ladder`, thin them in `_thin_atr_rungs`, place them on `SessionLevels.atr_rungs` from `_assemble` (never in `levels`, never a candidate)
- [x] Pin the plan, the ladders and the brief's columns to the base (`TestAtrRungsDisplayOnly`, goldens written on the base) and extend the structure and copy tests

## Task 3: Brief copy
Spec: § Design 5. Advances done_when[4].
- [x] Render the ATR line as the last NEXT LEVELS line (`TestAtrLevelsCopy`)

## Task 4: level_basis and replay
Spec: § Design 4. Advances done_when[6], done_when[5].
- [x] Record the rungs, the status, the anchors and the four parameters in level_basis; rebuild them in `from_basis`, none for a basis without them; `with_premarket` rebuilds the premarket rungs; `published_prices` includes the kept rungs (`tests/gcp/test_level_basis.py`)

## Task 5: Experiment and evidence
Spec: done_when "Experiment", § Source identity and close-out. Advances done_when[7], done_when[8], done_when[9].
- [ ] Replay SPY, QQQ and IWM through `gcp/premarket_brief.py` with history-mode parameters on a database copy and score both windows (needs GCP and the owner)
- [x] Rebind the 03-SITE note row, produce and verify the sidecar, update the catalog and PR lineage, and run the spec gate
