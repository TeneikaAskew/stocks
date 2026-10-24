---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-ci-envelope-pin.md
branch: fix/feat-cicd-001-registry-envelope-pin-bound
pr: null
status: ready
---

# Registry CI envelope pin-stage implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One implementation writer; root is sole external publisher.

**Goal:** Prepare the trusted pinned registry workflow for an eventual separately reviewed six-minute live job, keeping this stage's actual live timeout at five minutes.

**Architecture:** Change only the pinned `jobs.registry.timeout-minutes` scalar from5to6. Preserve exact live workflow bytes, all runtime/suite bytes, native pin-first checks and existing source-proof workflow.

**Tech Stack:** Existing GitHub Actions YAML, Python gate and unchanged native tests. No new dependency or provider/SQL operation.

**Spec:** `docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-ci-envelope-pin.md`, already approved and merged through #1589 at actual MAIN `d9731ecd8c5e82920079f5d6f66e29c7ac3e8d0e`. The parent #1586 design remains unchanged.

**Delivery ruling:** The owner explicitly corrected the contradictory plan-retarget instruction and authorized a unique new plan from current MAIN with this same writer. This new plan binds the already-merged pin primary from its first commit. #1590 remains frozen evidence, not a prerequisite imposed by the gate. Original unpublished plan checkpoint `1ede2cccb72989014d33e43665a9936e72a11731`, branch and prior review history are preserved; review budgets are not reset. Only the delivery instruction is superseded by the owner, not any DoD, test or scope constraint. The285s criterion is a CI-envelope acceptance target, not a production safety deadline.

## Global constraints

- PIN stage only: `scripts/gate/pinned/registry-check.yml` literal5to6; `.github/workflows/registry-check.yml` stays byte-for-byte at5.
- All existing triggers, permissions, checkout, installs, commands, job name, runner, tests/assertions/native calls and isolation remain unchanged.
- Preserve285s pytest and600s BASE ceilings, renderer60s/512MiB and verifier5s/8MiB/20000entries. No runtime cap change, optimization, stopped-candidate import, gate logic or test edit.
- Publish initial PLANONLY draft, then locally commit actual PR binding before CODE. Root may combine the binding's eventual push with reviewed CODE; the binding commit itself remains mandatory.
- Four independent prepush gate-file seats, exact-head authenticated reviews, all required CI and no unresolved conversations precede merge.
- Stage1's actual five-minute registry must pass exporter and pytest≤285s; record actual300s headroom without using future360s authority to waive failure.
- Stage2 cannot branch until stage1 actually MAIN; stage2 execution remains a separate PR and plan.

## Review focus

Pin/live sequencing, unintended YAML byte changes, scope or permission expansion, false timing/receipt claims, and truthful stage-specific readiness under the primary specification.

## Task 1: preserved inputs and trusted pin edit
Spec: § Exact scope and sequence. Advances done_when[0] and done_when[1].
- [ ] Preserve current MAIN/spec/pin/live/gate/suite identities in durable owner evidence.
- [ ] Bind this draft PR number in a second normally gated PLANONLY commit before CODE.
- [ ] Change only the pinned registry timeout scalar5to6; assert byte-for-byte equality outside that token and unchanged live5.
- [ ] Run existing focused native pin-order/workflow-contract controls and demonstrate live-only/simultaneous edits remain refused; do not add tests mirroring6.
- [ ] Commit with staged manual gate and normal hook, then obtain four independent concrete scoped prepush reviews.

## Task 2: owned records and ordinary proof
Spec: §§ Exact scope and sequence; Stage acceptance and evidence. Advances done_when[3].
- [ ] Update only own FEAT-CICD-001 catalog/traceability records and the existing declared SHARED-01 implementation-source note, preserving other SITE content.
- [ ] Produce and independently verify the ordinary committed-source sidecar using actual trusted MAIN; perform only exact renderer-owned updates if required by current MAIN.
- [ ] Compare full-default actual-main/proposed audits with duplicate-preserving no-new findings and run ordinary BASE/proposed PR gates.
- [ ] Resolve any genuine primary-spec readiness mismatch before claiming complete DoD or marking this PR ready; do not tick evidence for the unavailable future live stage.

## Task 3: actual hosted admission and merge boundary
Spec: §§ Stage acceptance and evidence; Cost, side effects and rollback. Advances done_when[2] and done_when[3].
- [ ] Record exact-head/base, all check/review receipts, original case/skip/warning counts, pytest duration and every relevant job/step timestamp.
- [ ] Require the unchanged live300s job to pass with exporter and pytest≤285s; distinguish full exporter comparison from its legitimate unchanged-input notice.
- [ ] Record actual pre-suite/suite residual/exporter/cleanup/whole-job timing, missing environmental evidence and normal CI cost; no blind retry or hidden unfavorable observation.
- [ ] Confirm the scoped pin change triggers no deployment, schema migration, provider request, runtime deadline change or live workflow activation.
- [ ] Merge only with separately verified owner authority and all ordinary safeguards satisfied. After actual pin MAIN, hand off the exact identity for a separate live-stage plan; no stacking or combined pin/live edit.
