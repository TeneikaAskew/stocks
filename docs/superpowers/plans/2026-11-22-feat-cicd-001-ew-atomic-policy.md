---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-22-feat-cicd-001-ew-atomic-registry-policy.md
branch: feature/feat-cicd-001-ew-atomic-policy
pr: 2120
status: ready
---

# Bounded EW registry policy implementation

Base: 444addbce7be6740bc40137ae6aa61be8fac7508; approved specification landed in #2119. Teneika Askew is accountable CI owner for this transition. Execute sequentially in the isolated policy worktree; no runtime, verifier, registry, SITE, sidecar, workflow or production changes.

## Task 1: exact policy append
Spec: Exact policy-only implementation oracle; done_when 1 and 3.
- [x] Extract the literal fenced Markdown block from the immutable approved specification and append it identically to both named policy files, preserving original bytes.
- [x] Prove exact base-prefix and appended-block equality; confirm every other source file remains unchanged.

## Task 2: deterministic qualification
Spec: Sequence, tests and exclusions; done_when 2 and 3.
- [x] Run normal commit and trusted PR gates; demonstrate DOC branch refusal for executable policy.
- [x] Run matched base/head documentation audits using one retained offline issue snapshot and compare full findings, preserving baseline drift.
- [ ] Stop on any new finding; no waiver or scope expansion. No redundant prose-unit tests.

## Task 3: delivery records and review
Spec: Retained predecessor obligations and Capacity; done_when 4.
- [ ] Record exact evidence in own catalog/traceability, with verifier and calendar implementation pending.
- [ ] Publish Draft only after qualification; bind its actual PR number before review and requalify final head. Keep checks truthful and review budget at two rounds.
- [ ] Verify final paths do not match known deployment trigger paths; no production operation.
- [ ] Obtain exact-head required hosted checks and normal CODE/SECURITY receipts; never claim rollout from policy wording.

## Capacity
Two append-only policy files plus this plan and own delivery records. No new runtime workload or vendor/model cost. Existing gate/audit deadlines apply unchanged. No new infrastructure or release.

## Local qualification receipts

On base 444addbc, plan ef572839 then policy source 3e246b88 passed normal hooks. Exact appended literals preserve both original files. Matched offline audits using the same retained November 22 issue snapshot: base 313 findings, head 313, zero new or removed. Draft gate passed with all acceptance lines unchecked; DOC-branch negative control refused both gated files. Initial incomplete-body gate refusal retained separately. Receipts: `/workspace/ew-atomic-policy-receipts/`; full hosted tests and external review not yet run.
