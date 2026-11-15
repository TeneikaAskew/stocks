---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-15-feat-strat-001-drop-entry-cutoff.md
branch: fix/feat-strat-001-drop-entry-cutoff
pr: null
status: ready
---

# The exits plan drops its 10:00 ET entry cutoff: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

Builds on the exits in thirds implementation (#1832) and the ATR levels change (#1951), both on main.
The spec merged in #1958.

## Task 1: The seed
Spec: § Design 1. Advances done_when[0].
- [x] Move the `entry_cutoff_et` seed in `gcp/schema.sql` to `{"time_et": "16:00"}` with its note; `ON CONFLICT DO NOTHING` stays
- [x] Assert the seeded policy gives 960 minutes (`tests/lib/test_level_params_loader.py`) and the basis records 16:00 (`tests/gcp/test_level_params_consumers.py`)

## Task 2: The plan's bars end at the exchange's close
Spec: § Design 3. Advances done_when[1], done_when[4].
- [x] Pass `resolve_plan` only the bars before `lib.eastern_time.session_close(analysis_date)` in `resolve_one`; `resolve_leg` reads the same bars as before; move `RESOLVER_VERSION`
- [x] Test a first cross at 10:00 and at 15:59 under the seeded policy, and a half day's post-close cross and close legs through `resolve_one` (`tests/gcp/test_premarket_playbook_resolver.py`)

## Task 3: Brief copy and stored briefs
Spec: § Design 4, § Design 2. Advances done_when[2], done_when[3].
- [x] Move the Design 8 golden strings and the brief fixtures' recorded cutoff to 16:00 (`tests/lib/test_strat_levels.py`, `tests/fixtures/atr_levels_*_base.json`)
- [x] Test that a stored basis keeps its 10:00 cutoff and a new one records 16:00 (`tests/gcp/test_level_basis.py`)

## Task 4: Experiment and evidence
Spec: done_when "Experiment", "Source identity", catalog. Advances done_when[5], done_when[6], done_when[7].
- [x] Reproduce the spec's Experiment through `resolve_plan` with the cutoff read from each tree's seeded policy
- [x] Rebind the 03-SITE note row, produce and verify the sidecar, update the catalog and PR lineage, and run the spec gate
- [ ] Change the production `entry_cutoff_et` row by Design 2's statement after the owner's yes, and record it
