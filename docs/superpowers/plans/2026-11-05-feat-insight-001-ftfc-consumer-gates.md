---
feat_id: FEAT-INSIGHT-001
spec: docs/superpowers/specs/2026-11-05-feat-insight-001-ftfc-consumer-gates.md
branch: fix/feat-insight-001-ftfc-aligned-conservative
pr: 1737
status: ready
---

# FTFC consumer gates in lib/agents implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: One aligned rule for the raw score and its snapshot
Spec: § Problem 1, § Approaches considered 3 and § Design, first and third bullets. Advances done_when[0].
- [x] Write failing test `tests/agents/test_ftfc_consumer_gates.py::test_aligned_is_the_same_for_the_raw_score_and_its_snapshot` on the producer's (0.3 - 0.1) / 0.4
- [x] Run: `python3 -m pytest tests/agents/test_ftfc_consumer_gates.py` (FAIL on origin/main: raw not aligned, snapshot aligned)
- [x] Implement `is_ftfc_aligned` in `lib/agents/trade_planner.py`; `compute_risk_metrics` and `orchestrator._calibrate_conviction` call it
- [x] Run again (PASS)

## Task 2: Directional conservative minimum
Spec: § Problem 2 and § Design, first bullet. Advances done_when[1].
- [x] Write failing tests `test_conservative_minimum_follows_the_trade_direction` and `test_conservative_short_rationale_names_the_bearish_threshold`
- [x] Run (FAIL on origin/main: a bearish short stands aside, a bullish short sizes)
- [x] Implement `_fails_conservative_ftfc` in `lib/agents/trade_planner.py`, used by `_plan` and `_build_rationale`
- [x] Run again (PASS)

## Task 3: Nothing else moves
Spec: § Non-goals. Advances done_when[2].
- [x] Confirm `lib/strat.py`, `lib/config.py` and `lib/agents/ranker/` are not in the diff, and `tests/agents/test_ranker.py` passes unchanged
- [x] Run `tests/lib/test_backtest_ftfc_causality.py`, `tests/lib/test_exec_ftfc_contract.py`, `tests/lib/test_trade_planner.py`, `tests/agents/test_persona_risk_metrics.py`, `tests/agents/test_agent_orchestrator.py`, then `tests/agents`, `tests/lib` and `tests/gcp`

## Task 4: Evidence in the PR body
Spec: § Expected effect and § Risks. Advances done_when[3].
- [x] Replay old (origin/main) and new decisions of each gate for IWM, SPY and QQQ from 2015-01-02 to the 2026-11-05 brief with the repo's own functions
- [x] Put the 21-day tables and the changed-day counts in the PR body

## Task 5: Source identity
Spec: § Source identity and close-out. Advances done_when[4].
- [x] After the spec is on main, merge main, add the `(FEAT-INSIGHT-001, INSIGHTS-07)` note row with the producer's source hash, commit, produce the sidecar from the committed body, commit it and run `verify` from the committed HEAD

## Task 6: close
Spec: § Source identity and close-out. Closes done_when[5].
- [x] Update the 02-FEATURE-CATALOG FEAT-INSIGHT-001 record (Status, Last reviewed, Next action)
- [x] Add this PR to 12-PR-ISSUE-TRACEABILITY once it has a number, and set `pr` here
- [x] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`, which needs read access to solyra's issues)
- [x] `python3 scripts/gate/spec_gate.py --pr origin/main`
