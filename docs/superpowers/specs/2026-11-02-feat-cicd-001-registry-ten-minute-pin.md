---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1684]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The pinned `scripts/gate/pinned/registry-check.yml` has literal `jobs.registry.timeout-minutes: 10` while the live `.github/workflows/registry-check.yml` stays byte-identical to MAIN with `timeout-minutes: 6`; the pinned copy's diff is exactly one line, `    timeout-minutes: 6` to `    timeout-minutes: 10`, at the job level of `registry`. A recorded YAML load asserts the integer 10 at job level, with recorded negative controls failing for the key missing, the value only on a step and the value quoted as \"10\"; a recorded text check fails for `012`, `0xA`, `1_0`, `+10`, `!!int \"10\"`, `\"10\"`, `10.0`, a second job without a timeout, a step-level `timeout-minutes` and a change on any other line (#1684 N1); no other file changes beyond this stage's plan and the named delivery records, with no other execution, permission, dependency, isolation, runner or runtime-deadline change."
  - "Existing native pin-order and workflow-contract controls pass and reject a live-only or simultaneous pin/live timeout change; every original test, assertion, native invocation and required check stays present and passes, with the suite still serial and unchanged."
  - "The exact-head registry job, still bounded at six minutes, passes with the unchanged exporter; its head and whole-job time are recorded, without claiming the ten-minute envelope is active."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main/proposed no-new audits, the gate-file red-team pass, current-head review as CLAUDE.md section 2.5 counts it (or an owner-recorded substitute for that PR), every required check and zero unresolved threads are complete; the parent's live-stage criteria stay with the live-stage PR, which binds the parent spec, and no global completion is claimed."
status: approved
supersedes: null
---

# Registry ten-minute envelope: pinned-copy stage primary

## Authority and delivery correction

This is the stage-one primary for the approved design in
`docs/superpowers/specs/2026-11-02-feat-cicd-001-registry-ten-minute-envelope.md` (on main since
fad81fbb, #1683). It corrects only staged delivery bookkeeping. It adds no timeout, runtime,
permission or implementation scope.

The parent requires the pin PR to merge before the live PR opens, but its done_when item 3 is a
live-stage result ("The live-stage hosted registry job on its exact head passes ..."). The
ready-for-review close-out check requires every done_when item of the bound spec to be ticked and
has no stage filter, so a pin PR bound to the parent cannot truthfully go Ready. The parent stays
unchanged and is the live-stage PR's spec, with every item. This primary carries only the
achievable pin-stage obligations, as `2026-10-24-feat-cicd-001-registry-ci-envelope-pin.md` did for
the six-minute envelope (#1591). No parent criterion is deleted, waived or marked complete here.

Item 1 also carries #1684 N1's pin-stage text check, an obligation the parent does not state.
#1684 stays open for N1's live-stage conjunct, which the live-stage PR records alongside the
parent's items.

## Exact scope and sequence

Change only `scripts/gate/pinned/registry-check.yml`'s `jobs.registry.timeout-minutes` from literal
6 to literal 10. The live `.github/workflows/registry-check.yml` stays at 6 and otherwise unchanged.
Allowed companion edits are exactly this stage's plan, the FEAT-CICD-001 catalog and traceability
records, and the SHARED-01 note row with its ordinary sidecar. No gate validator, suite, hook,
dependency, runner or runtime code changes.

Every safety and resource contract of the parent stays exact. The gate-file red-team pass runs on
the frozen head before the one push. The operation the platform refused on stocks#1630 is not
retried, replaced or routed around; the red-team pass's exporter-and-policy seat is staffed only
under its own owner-recorded authorization.

## Stage acceptance and evidence

Before merge, the PR is reviewable as the pinned transition only. Its registry job, still bounded at
six minutes, must finish successfully with the exporter. The parent's timing record and 120-second
reserve belong to the live stage and are not applied here. An unavailable log or failed check is a
hold; nothing is bypassed.

After this pin PR merges, the live-stage branch opens from actual MAIN and binds the parent spec.

## Cost, side effects and rollback

The live timeout stays at 360 seconds, so this stage changes no running job's limit and no
production job or schema. Rollback follows the parent's pin-first order; live and pin never change
together.
