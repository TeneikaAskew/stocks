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

## Task 4: strict empty admission under the existing approved A10 contract
Spec: A10 actual direct-fetch typed source admission and REQ-OBS-001. The original Task2 preserved parser behavior for its diagnostic stage; this subsequent bounded stage intentionally corrects missing/null/wrong-type records being admitted as retryable empty. No change to #1602 or its pending acceptance amendment.
- [x] Add failing actual process_ticker/main fixtures: valid-success envelope with missing/null/non-list data is terminal with one call/zero writes; literal[] retains exactly the existing three attempts; provider Error Message remains one attempt; good siblings continue once with acknowledged counts only.
- [x] Admit RealtimeOptionsEmpty only for literal data:[]; emit fixed data_missing/data_null/data_type classifications without retaining provider values. Keep outgoing request, timeout, error/info/sample behavior, pacing, EMPTY_RETRY_ATTEMPTS, normalizer, SQL keys/writes and existing partial/uncertain-ACK safeguards unchanged.
- [x] Run only changed/affected mocked collector suites with external boundaries blocked; preserve the accepted A8/A10 packets and unrelated tests. No new source-journal tables, quota grant, provider calls, SQL, production job or deployment.
- [ ] Preserve local evidence and complete later actual current-main source proof/audit and current-head review through normal draft gates. This is partial A10 admission work, not complete A1–A15/durable targeted recovery or deployment readiness.
