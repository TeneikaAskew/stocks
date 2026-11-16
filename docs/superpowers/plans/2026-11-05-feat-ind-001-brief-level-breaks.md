---
feat_id: FEAT-IND-001
spec: docs/superpowers/specs/2026-11-05-feat-ind-001-brief-level-breaks.md
branch: fix/feat-ind-001-brief-level-breaks
pr: 1734
status: ready
---

# The brief's level-break flags implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: Produce Broke_Prev_Day_High / Broke_Prev_Day_Low on the brief path
Spec: § Approaches considered 3 and § Design. Advances done_when[0].
- [x] Write failing tests `tests/lib/test_brief_level_breaks.py` (definition, parity with `calculate_historical_levels`, index-only frame, no later bar read, on real bars a broken level adds exactly one point and moves building to setup)
- [x] Run: `python3 -m pytest tests/lib/test_brief_level_breaks.py` (FAIL on origin/main: the columns are absent)
- [x] Implement `_add_prev_session_level_breaks` in `lib/indicators.py`, run last in `add_brief_indicators`
- [x] Run again (PASS)

## Task 2: The other indicator paths are unchanged
Spec: § Non-goals. Advances done_when[1].
- [x] Run `tests/lib/test_indicators.py` (pinned `add_all_indicators` columns, signal and brief tier parity), then `tests/lib` and `tests/gcp`

## Task 3: Evidence in the PR body
Spec: § Expected effect and § Risks. Advances done_when[2].
- [x] Replay the old (origin/main) and new brief CALL/PUT scores and status for IWM, SPY and QQQ from 2015-01-02 to the 2026-11-05 brief with the repo's own functions
- [x] Put the 21-day table and the changed-day counts in the PR body

## Task 4: Source identity
Spec: § Source identity and close-out. Advances done_when[3].
- [x] After the spec is on main, merge main, add the `(FEAT-IND-001, DASHBOARD-01)` note row with the producer's source hash, commit, produce the sidecar from the committed body, commit it and run `verify` from the committed HEAD

## Task 5: close
Spec: § Source identity and close-out. Closes done_when[4].
- [x] Update the 02-FEATURE-CATALOG FEAT-IND-001 record (Status, Last reviewed, Next action)
- [x] Add this PR to 12-PR-ISSUE-TRACEABILITY once it has a number, and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`, which needs read access to solyra's issues)
- [x] `python3 scripts/gate/spec_gate.py --pr origin/main`
