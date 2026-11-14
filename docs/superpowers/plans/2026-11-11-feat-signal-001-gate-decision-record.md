---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-11-11-feat-signal-001-gate-decision-record.md
branch: feature/feat-signal-001-gate-decision-record
pr: 1823
status: ready
---

# Record the live direction gate's decision on every signal alert (implementation plan)

**Goal:** every persisted `signal_alerts` row carries the live direction gate's decision (`gate_action`,
`gate_reason`), the insight it read (`insight_direction`, `insight_conviction`, `insight_regime`) and
`thesis_invalidated` (NULL when unknown), with no change to which alerts fire, their score, strength or
delivery.

**Spec:** `docs/superpowers/specs/2026-11-11-feat-signal-001-gate-decision-record.md` (approved, #1790).

**Requirement:** REQ-SIGNAL-001, REQ-DATA-003.

## Task 1: per-fire stash
Spec: § Design. Advances done_when[1], done_when[2], done_when[4].
- [ ] Reset `_latest_insight_ctx`, `_latest_gate_action`, `_latest_gate_reason`, `_latest_thesis_invalidated` at the start of each fire's gate block, and again when the gate raises.
- [ ] In shadow mode store `gate_reason` as `shadow:<reason>`; set `thesis_invalidated` only when the insight has an invalidation level.

## Task 2: persist the six columns
Spec: § Design. Advances done_when[0], done_when[3].
- [ ] `_persist_signal_alert` adds the six columns from the stash; a direction, conviction or regime longer than its column is truncated to the width with one warning line.

## Task 3: tests
Spec: § Design. Advances done_when[0] to done_when[5].
- [ ] `tests/gcp/test_signal_monitor_gate_record.py` drives `evaluate_ticker` with a stubbed insight cache into the real persist path; record it failing on origin/main.
- [ ] Every existing `tests/gcp/test_signal_monitor*.py` and `tests/scripts/test_replay_signal_monitor.py` passes unchanged.

## Task 4: close-out
Spec: § Design, § Risks. Advances done_when[6].
- [ ] Catalog FEAT-SIGNAL-001 record and 12-PR lineage carry this PR; docs audit shows no new finding versus main; spec_gate --pr passes; Codex review on the current head.
