---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "A pin-stage PR, whose base holds the contract stage, changes only scripts/gate/pinned/registry-check.yml (gains job base-suite) and scripts/gate/pinned/spec-gate.yml (keeps only job gate) to the moved layout; the base's gate accepts it, and .github/workflows/registry-check.yml and .github/workflows/spec-gate.yml stay byte-identical to MAIN."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check green and zero unresolved threads are complete; the parent's other items stay with their own stages and no global completion is claimed."
status: approved
supersedes: null
---

# Gate base-suite move, stage two: the pin stage

## Authority

This is the stage primary for the pin stage of
`docs/superpowers/specs/2026-11-16-feat-cicd-001-base-suite-off-pull-request-target.md` (merged in
#2007), done_when item 3, in the way the contract stage spec (merged in #2058) is the stage primary
for item 2. It copies item 3 and the records item 7 asks of every stage, and adds no implementation
scope. The parent's Design, Sequence, Capacity, Risks and Rollback sections govern this stage
unchanged.

It takes no position on the Actions event policy or the required-check swap. Those stay owner
settings steps (parent Sequence 3 and 6), each needing the owner's own confirmation when its stage
comes.

## Why a stage primary

As the contract stage spec gives it: the gate's close-out reads every done_when item of the spec a
plan cites and requires each one ticked before a pull request can be marked ready, so each stage
cites a stage primary holding its own items, and the parent's items are ticked stage by stage,
without a global completion claim.

## Design

As the parent's Design section and Sequence step 2 give it. The pinned copy
`scripts/gate/pinned/registry-check.yml` gains a second job, `base-suite`, laid out as the parent's
Design section gives it (base checkout and sparse head checkout, both with
`persist-credentials: false`; no `git fetch`; the two proposed files copied over `scripts/gate` and
the head checkout removed, with no action after the copy; the same pinned installs as the registry
job; main's two suites run unconditionally, the gate suite on four workers; `contents: read`, no
secret, no cache action, a 10-minute timeout). Its `registry` job is unchanged. The pinned copy
`scripts/gate/pinned/spec-gate.yml` keeps only its `gate` job, unchanged, and drops the artifact
handoff that fed today's `base-suite` job.

The base's gate, which holds the contract stage, judges the pinned pair separately from the live
pair, so the pinned pair may hold the moved layout while the live pair still holds today's. The live
workflows do not change here; the live stage makes each one a copy of its pinned file.

## Capacity

As the parent's Capacity section: no live workflow or workload changes at this stage. The pinned
copies run nowhere until the live stage copies them.

## Risks

As the parent's Risks section. The gate-file red-team pass runs on the frozen head before the push.

## Rollback

Revert the pin stage's pull request; the live workflows are unchanged by it.
