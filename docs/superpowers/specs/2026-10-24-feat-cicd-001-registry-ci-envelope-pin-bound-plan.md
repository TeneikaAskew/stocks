---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The pinned registry workflow has literal jobs.registry.timeout-minutes: 6 while the live registry workflow remains byte-identical to MAIN with timeout-minutes: 5; only that pinned property and authorized delivery records change."
  - "Existing native pin-order and workflow-contract controls pass and reject live-only or simultaneous pin/live changes; every original test, assertion, native invocation, permission and runtime safety deadline remains unchanged."
  - "The exact-head still-five-minute hosted registry job passes with pytest at most 285 seconds and its required exporter completed; actual stage times, exporter mode, counts and headroom against 300 seconds are recorded without claiming the future six-minute envelope is active."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main/proposed no-new audits, four independent prepush reviews, current-head Codex code/security reviews, all required checks and resolved conversations are complete; the parent final-stage criteria remain assigned to the live-stage primary without claiming global completion."
status: approved
supersedes: docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-ci-envelope-pin.md
---

# Registry CI envelope: pinned-copy stage primary

## Authority and delivery correction

This is the stage-one primary for the owner-approved design in `docs/superpowers/specs/2026-10-24-feat-cicd-001-registry-ci-envelope.md`, merged through #1586 at `ffa5f15fd69be64f897354227692b3365a7586f3`. The bounded finish approval includes necessary specification and implementation merges through normal checks. This file corrects only staged delivery bookkeeping; it adds no timeout, runtime, permission or implementation scope.

The parent design explicitly requires the pin PR to merge before the live PR opens, but its global DoD includes future live-stage results. `check_close_out` requires all primary-spec items ticked for readiness and has no stage filter. A pin PR cannot truthfully satisfy the future live result. The parent stays unchanged. This primary contains only achievable pin-stage obligations; the separate live-stage primary retains every original parent DoD verbatim. No global criterion is deleted, waived or marked complete here.

## Exact scope and sequence

After these approved staged primaries are actually MAIN, retain the same writer and preserve the original unpublished plan checkpoint `1ede2cccb72989014d33e43665a9936e72a11731`, its branch, review history and stopped candidates. The gate binds an existing plan permanently to its specification and branch, so do not retarget that plan. From current MAIN create a new pin plan at a unique path on a new FEAT-CICD-001 branch, bound from its first normally gated PLANONLY commit to this primary. Carry forward the existing plan tasks and review lineage without resetting review budgets. Publish its initial draft, then commit the actual PR-number binding through the normal hook before CODE. This corrects delivery bookkeeping only; it grants no check waiver or additional implementation scope.

Change only `scripts/gate/pinned/registry-check.yml`'s `jobs.registry.timeout-minutes` from literal5 to literal6. The live `.github/workflows/registry-check.yml` stays5 and otherwise unchanged. Allowed companion edits are exactly the parent's own plan, FEAT-CICD-001 record/traceability, existing SHARED-01 note/ordinary sidecar and already-admitted exact renderer blocks, if needed. No gate validator, suite, hook, dependency, runner or runtime CODE change is admitted.

The parent's serial native command, every test/assertion/invocation/isolation requirement,285s suite/600s BASE ceiling, renderer60s/512MiB, verifier5s/8MiB/20000entries and all other safety/resource contracts remain exact. No optimization candidate is imported or claimed effective. Run the existing meaningful pin-order controls, not a mirror-number unit test. The four gate-file prepush review seats and ordinary review caps still apply.

## Stage acceptance and evidence

Before merge, this PR must be independently reviewable as the pinned transition only. Its actual five-minute registry job must finish successfully, including exporter, with pytest no more than285s. Record timing/count/skip/warning evidence, exact head/base and source identities, all attempts and actual headroom under300s. No six-minute claim or25s final headroom obligation is applied to this unchanged bootstrap. An unavailable log or failed check is a genuine hold; no future budget is borrowed and no check is bypassed.

After this pin PR genuinely merges, preserve its last reviewed head, merge receipt and hosted receipts for the live-stage proof. Only then may the separate live-stage branch open from actual MAIN. The complete six-minute result is not certified by this stage. The parent and live-stage primary retain all final criteria and proposed reserves.

## Cost, side effects and rollback

The live timeout remains300s, so this stage does not activate the nominal extra60s CI allowance or change any production job/schema. Existing CI jobs and source-proof work still consume normal resources. Actual cancellation tails/billing remain unknown; no occupancy maximum is invented. Readiness/merge authority is conditional on normal protections. If rollback is required, follow the parent's separately authorized normal pin-first protocol; do not change live/pin together or alter protections.
