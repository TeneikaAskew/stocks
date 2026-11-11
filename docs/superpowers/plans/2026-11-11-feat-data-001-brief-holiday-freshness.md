---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-11-11-feat-data-001-brief-holiday-freshness.md
branch: fix/feat-data-001-brief-holiday-freshness
pr: 1803
status: ready
---

# The brief's freshness check counts NYSE sessions: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: The shared rule counts sessions
Spec: § Design. Advances done_when[0].
- [x] Write failing tests in `tests/lib/test_strat_levels.py::TestDailyDataFreshness` (post-holiday sessions fresh, missing sessions stale, gap 0 and 1 never call the calendar, a calendar failure raises)
- [x] Run: `python -m pytest -q tests/lib/test_strat_levels.py -k DailyDataFreshness` (expect FAIL on the holiday cases)
- [x] Implement in `lib/strat_levels.py::daily_data_freshness` with `lib.eastern_time.previous_session`
- [x] Run again (expect PASS), with every pre-existing expectation unchanged

## Task 2: The brief publishes on a post-holiday session
Spec: § Expected effect. Advances done_when[1].
- [x] Write a failing test in `tests/gcp/test_premarket_brief.py` running `generate_premarket_brief` with `BRIEF_AS_OF=2026-11-27` on bars ending 2026-11-25 (scored) and 2026-11-24 (stale)
- [x] Run it (expect FAIL on origin/main, PASS after Task 1); update the `_resolve_data_freshness` docstring

## Task 3: The movement-statement ladder follows
Spec: § Expected effect. Advances done_when[2].
- [x] Write a failing test in `tests/api/test_movement_statement_router.py` for session 2026-05-26 on bars ending 2026-05-22 (ladder) and 2026-05-21 (refused); update the comment in `platform/api/routers/dashboard.py`

## Task 4: Evidence
Spec: § Design (the 21 sessions). Advances done_when[3].
- [x] Compare the origin/main rule and the new rule over every NYSE session 2025-01-02 to 2026-12-31 paired with each of its ten previous sessions; put the result in the PR body

## Task 5: Source identity
Spec: § Source identity and close-out. Advances done_when[4].
- [ ] After the spec is on main, merge main, add the `(FEAT-DATA-001, DASHBOARD-01)` note row with the producer's source hash, commit, produce the sidecar from the committed body, commit it and run `verify` from the committed HEAD

## Task 6: close
Spec: § Source identity and close-out. Closes done_when[5].
- [x] Update the 02-FEATURE-CATALOG FEAT-DATA-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY once it has a number, and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`, which needs read access to solyra's issues)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` (after the spec is on main)
