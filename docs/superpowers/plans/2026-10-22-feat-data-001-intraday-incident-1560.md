---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-12-feat-data-001-av-market-data.md
branch: fix/feat-data-001-intraday-incident-1560
pr: null
status: ready
---

# Incident1560: truthful month outcomes and recovery guidance

Goal: preserve the existing completeness refusal and isolate operational recovery candidates from structural coverage review. This is a narrow REQ-OBS-001 corrective subset under the approved DATA source/replace-month observability obligations, not full DATA delivery or an authorization to repair data.

One operator owns both incident branches. Existing telemetry/native-source work remains untouched. No provider, SQL, credential, production, deploy, restart or replay actions; only mocked tests and a draft PR are authorized.

## Task 1: month outcomes and discriminating recovery guidance
Spec: Design (bounded repair complete/partial/error counts), native replace_month qualification, and observability. Advances existing observability acceptance without claiming full source-journal adoption.
- [ ] Write failing real run_replace_months tests proving incomplete/unknown failures remain nonzero and require review, only existing transient/concurrency reasons become targeted retry candidates, and sibling outcomes continue.
- [ ] Add bounded structured per-month result logs distinguishing planned dry-run rows from acknowledged committed rows and uncertain exceptions, with safe fields and no raw errors.
- [ ] Keep all month completeness, lock/recheck, atomic replacement, pacing and provider request/retry behavior unchanged. No automatic rerun or threshold relaxation.
- [ ] Run focused and affected mocked suites with external boundaries blocked, then independent complete diff review and actual staged gate.

## Task 2: review and operational handoff
Spec: observability/operating contract; production evidence remains separately gated.
- [ ] Record actual1199dry-run outcomes/55refusals and exact targeted review lists from retained logs, with no persisted-repair claim.
- [ ] Publish only a draft PR; preserve open full-contract acceptance and current-main checks. No merge/auto-merge/deploy/job execution.
- [ ] Provide exact proposed recovery scope, quota bounds, partial-write risk and read-access blocker for later parent approval.
