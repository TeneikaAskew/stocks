---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-11-11-feat-signal-001-brief-rsi-bands-r2.md
branch: fix/feat-signal-001-brief-rsi-bands
pr: 1808
status: ready
---

# The brief scores RSI against the ticker's calibrated band: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: Point-in-time resolver
Spec: § Design, `lib/strategies/calibration.py`. Advances done_when[0].
- [x] Write failing tests in `tests/lib/test_strategies_calibration.py` (as_of filter on both queries, staleness from as_of, unchanged query without as_of, getters pass as_of, `resolve_rsi_bands` Tier A and Tier B)
- [x] Run: `python -m pytest -q tests/lib/test_strategies_calibration.py` (expect FAIL)
- [x] Implement `as_of` on `_latest_calibration` and the getters, and `resolve_rsi_bands`
- [x] Run again (expect PASS)

## Task 2: The brief scores with the resolved bands
Spec: § Design, `gcp/premarket_brief.py`. Advances done_when[1] and done_when[2].
- [x] Write failing tests in `tests/gcp/test_premarket_brief.py::TestBriefRsiBands` (as_of is the analysis date, Tier-A band changes the RSI point, Tier B scores as before, AST guard on the two calls)
- [x] Let the two brief-harness stubs (`tests/gcp/test_strat_snapshot_parity.py`, `tests/lib/strat_2026_11_06.py`) accept the `rsi_range` keyword
- [x] Implement in `gcp/premarket_brief.py`; run again (expect PASS)

## Task 3: Experiment
Spec: § Experiment. Advances done_when[3].
- [x] Commit `scripts/analysis/brief_rsi_band_experiment.py`, run it with the spec's command and check its summary equals the spec's table
- [ ] Put the table and the rebuilt Tier-A rows in the PR body

## Task 4: Source identity
Spec: § Source identity and close-out. Advances done_when[4].
- [ ] After the spec is on main, merge main, add the `(FEAT-SIGNAL-001, DASHBOARD-01)` note row with the producer's source hash, commit, produce the sidecar from the committed body, commit it and run `verify` from the committed HEAD

## Task 5: close
Spec: § Source identity and close-out. Closes done_when[5].
- [x] Update the 02-FEATURE-CATALOG FEAT-SIGNAL-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY once it has a number, and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`, which needs read access to solyra's issues)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (after the spec is on main)
