---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-11-06-feat-option-001-source-window-excludes-writes.md
branch: fix/feat-option-001-source-window
pr: null
status: ready
---

# Realtime options source window excludes database writes implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: reproduce the production failure
Spec: § Problem, § Design. Advances done_when[0], done_when[1].
- [x] Write failing tests `tests/gcp/test_av_options_realtime_producer.py::test_persistence_time_does_not_spend_the_source_window` and `::test_failed_write_time_does_not_spend_the_source_window`
- [x] Run: `pytest tests/gcp/test_av_options_realtime_producer.py -k window` (FAIL on main: QQQ refused with source_deadline after two 12-second writes; failed-write sibling refused)

## Task 2: hand write time back to the source window
Spec: § Design. Advances done_when[0], done_when[1].
- [x] `gcp/fetchers/_av_realtime_collector.py`: `process_ticker(_persistence_elapsed=)` records each write's monotonic duration in a `finally`; `main` moves the one source deadline forward by it before pacing the next ticker (`_exclude_persistence`), never backwards
- [x] Run the two tests again (PASS)

## Task 3: carry the rest of the contract forward
Spec: § Non-goals. Advances done_when[2].
- [x] Run the collector suites: realtime producer, collector entry, response schema; transport file unchanged (pinned hash test passes)
- [ ] CI runs `tests/integration/test_options_collector_durability.py` against its PostgreSQL

## Task 4: close
Spec: § Done when, § Rollout and evidence. Closes done_when[3].
- [ ] Update the 02-FEATURE-CATALOG FEAT-OPTION-001 record (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY
- [ ] Docs audit reports nothing new over origin/main
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
