---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "A contract-stage PR changes only scripts/gate/spec_gate.py and the two gate suites: WORKFLOW_CONTRACTS accepts the base-suite duties in exactly one of two layouts, judged across the live pair and, separately, across the pinned pair: today's (spec-gate.yml job base-suite after the verdict, artifact handoff) or the moved one (registry-check.yml job base-suite as the Design section gives it: base checkout and sparse head checkout both with `persist-credentials: false`, no `git fetch`, the proposed files copied over scripts/gate with no action after, unconditional suites, no secret, no cache action, contents: read, not the registry job); every existing refusal keeps its wording and each other rule of both contracts is unchanged. Only the assertions that read the real workflow files' job layout change, which the owner's approval of this spec permits: the job lists at tests/scripts/test_spec_gate.py (`list(workflow[\"jobs\"]) == [\"gate\", \"base-suite\"]`) and tests/scripts/test_export_model_registry.py (`list(jobs) == [\"registry\"]`), and the base-suite block of `test_the_invoked_command_is_the_contract_and_policy_files_keep_their_schema` (export and upload in the gate job, `needs: gate`, the credential-free checkout, the download, the unconditional suite step); each asserts the same duty in whichever of the two layouts the files hold, and the synthetic workflows the suites build (`GATE_WF`, `gate_workflow()` and the literal spec-gate.yml fixtures) move to the moved layout as a pair of files, each case keeping its intent and expected outcome, except one named group of cases (`old_layout_*` in tests/scripts/test_spec_gate.py) that keeps today's layout to show it is still accepted whole and still refused when weakened; no other test, case or assertion changes, and every case's move is listed in the PR body. New tests show the gate refusing, in the moved layout, a base-suite job whose head checkout keeps credentials or is not sparse to the two files, that runs a `git fetch`, runs a suite before the copy or an action after it, reads a secret or restores a cache, refusing a pair that holds both layouts or neither, and accepting each layout whole, each recorded failing on main and passing on the head; main's own suites pass against the proposed gate in the hosted base-suite job, and both suites pass serially and with `-n 4`."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check green and zero unresolved threads are complete; the parent's other items stay with their own stages and no global completion is claimed."
status: approved
supersedes: null
---

# Gate base-suite move, stage one: the contract stage

## Authority

This is the stage primary for the contract stage of
`docs/superpowers/specs/2026-11-16-feat-cicd-001-base-suite-off-pull-request-target.md` (merged in
#2007), done_when item 2, in the way #1966 was the stage primary for Part A's live stage. It copies
only that item and the records item 7 asks of every stage, and adds no scope. The parent's Design,
Sequence, Capacity, Risks and Rollback sections govern this stage unchanged.

## Why a stage primary

The parent lists all seven stage items in one spec. The gate's close-out reads every done_when item
of the spec a plan cites and requires each one ticked before a pull request can be marked ready,
so a stage pull request citing the parent could only be marked ready by ticking the items of the
stages after it. Each stage therefore cites a stage primary holding its own items, and the parent's
items are ticked stage by stage, without a global completion claim.

## Design

As the parent's Design section and Sequence step 1 give it: `scripts/gate/spec_gate.py` accepts the
base-suite duties in exactly one of today's layout or the moved one, judged across the live pair and,
separately, across the pinned pair; the suites move their synthetic workflows to the moved layout as
a pair and keep the `old_layout_*` group on today's layout. The workflows and their pinned copies do
not change. The implementation is #2057.

## Capacity

As the parent's Capacity section: no workflow or workload changes. The gate suite grows by the new
tests in the same two jobs, inside the unchanged 600 s timeouts; the pull request body records the
local serial and four-worker times.

## Risks

As the parent's Risks section. The gate-file red-team pass runs on the frozen head before the push.

## Rollback

Revert the contract stage's pull request; the workflows and pinned copies are unchanged by it.
