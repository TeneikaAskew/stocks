---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-10-31-feat-option-001-source-budget-excludes-persistence.md
branch: fix/feat-option-001-source-window
pr: 1743
status: ready
---

# Realtime options collector: one cumulative source budget that excludes persistence time

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances. Issue #1646.
> Spec lineage: #1649, #1677 (revision 5), #1744 (revision 6, merged).

## Task 1: reproduce on the predecessor
Spec: § Problem, § Source budget. Advances done_when[0], done_when[4].
- [x] Add the `_SourceSim` harness to `tests/gcp/test_av_options_realtime_producer.py`: fake source clock, fake provider, stubbed persistence time, and a fake interval timer standing in for the transport's SIGALRM (defaults: connect 0.2 s, body 0.8 s, persistence 0.5 s, pace 0.4 s)
- [x] Write `test_persistence_time_excluded_from_shared_source_budget` (13 s and 20 s on the first, middle and final ticker)
- [x] Run against the predecessor collector: first and middle fail, final passes, as the spec states

## Task 2: the budget holder
Spec: § Source budget rules 1 to 10, § Files and source identity (delta). Advances done_when[0] to done_when[4].
- [x] `gcp/fetchers/_av_realtime_collector.py`: `_SourceBudget` with creation, source-admission checkpoints, a post-call checkpoint after every `decoded_json` return or raise, pause and resume around the single `upsert_dataframe` call; terminal exhaustion on any untrusted reading, pairing fault or non-finite arithmetic; resume rounds down so it never restores more than the held remainder
- [x] `main` creates the budget where the window was created and checkpoints each ticker admission; `process_ticker` takes `_source_budget` and still accepts `_source_deadline=<float>`
- [x] Write `test_source_budget_is_cumulative_never_reset_or_revived`, `test_untrusted_clock_readings_fail_later_source_closed_*` (groups a to d), `test_persistence_exception_and_short_ack_keep_outcome_and_resume_budget` and `test_provider_budget_exhaustion_and_retry_pacing_consume_source_budget` (S7 and the retry-refusal fixture)

## Task 3: collector entry
Spec: § Batch timestamp and session boundary, § Files and source identity (delta). Advances done_when[5], done_when[6].
- [x] `tests/gcp/test_av_options_collector_entry.py`: `test_batch_timestamp_and_delayed_session_boundary_are_explicit`
- [x] `test_scheduled_entry_preserves_sibling_commit_on_later_failure` and the `invoke` fixture raise an actual `SourceDeadline()`; the test captures the collector logger in its body and adds the TypeError control; run against local PostgreSQL

## Task 4: carry the rest of the contract forward
Spec: § Non-goals, § Files and source identity. Advances done_when[7], done_when[8].
- [x] The listed existing tests pass unmodified, with all of `tests/gcp/test_av_realtime_transport_cli.py`
- [x] No diff against the merge base to the transport, `fetch_av_realtime_options.py`, `gcp/database.py` or the job's `gcp/deploy.sh` block
- [ ] CI runs `tests/integration/test_options_collector_durability.py` against its PostgreSQL

## Task 5: close
Spec: § Rollout and evidence. Closes done_when[9].
- [x] Update the 02-FEATURE-CATALOG FEAT-OPTION-001 record and the 12-PR-ISSUE-TRACEABILITY lineage
- [x] Docs audit reports nothing new over origin/main; `python3 scripts/gate/spec_gate.py --pr origin/main` passes
- [ ] Current-head Codex review and CI pass; the job image release is separately authorized
