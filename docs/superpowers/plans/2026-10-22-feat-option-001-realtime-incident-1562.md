---
feat_id: FEAT-OPTION-001
spec: docs/superpowers/specs/2026-10-13-feat-option-001-av-source-journal.md
branch: fix/feat-option-001-realtime-incident-1562
pr: 1565
status: ready
---

# Realtime incident diagnostics release cut

Scoped A10 / REQ-OBS-001 increment for #1547 and #1562; not full source-journal delivery, historical repair or a provider root-cause fix. Original reviewed telemetry/admission work remains preserved in its original worktree. This branch targets current main independently and never stacks on that unfinished branch.

## Task 1: preserve admission and safe attempt diagnostics
Spec: A10 actual main/direct producer admission and observability; advances done_when A10 without claiming its complete native publisher/terminal contract.
- [ ] Preserve bounded request/status/timing/classification telemetry, no unsafe raw error logging, NYSE session and configured SQL admission before provider dispatch, acknowledged writes only.
- [ ] Verify original mocked transport/redaction/retry and admission suites offline; no live provider requests, SQL or production actions.

## Task 2: distinguish unexpected envelopes safely
Spec: A10 actual fetch transport / REQ-OBS-001 response classification; advances done_when A10.
- [ ] Write failing regressions for fixed schema-only enums/key presence, null/missing/wrong shapes, malicious secret-bearing values and one-call/zero-write refusals.
- [ ] Emit bounded schema projection without values, arbitrary keys, bodies, full URLs, credentials or derived hashes. Preserve parser and retry policy.
- [ ] Run affected suites with network/SQL/subprocess boundaries blocked.

## Task 3: review and draft publication
Spec: A15 evidence/partial requirement status; advances done_when A15 only within this diagnostics release cut.
- [ ] Complete independent full diff review and applicable delivery checks.
- [ ] Publish DRAFT only; list full spec acceptance unchecked and actual scope/evidence explicitly. No merge/deploy/restart/replay.
- [ ] Document exact proposed rollout and discriminating validation for parent approval. SQL completeness and underlying provider cause remain unknown.
