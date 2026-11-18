---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "A contract-stage PR changes only scripts/gate/spec_gate.py and the two gate suites: WORKFLOW_CONTRACTS accepts the base-suite duties in exactly one of two layouts, judged across the live pair and, separately, across the pinned pair: today's (spec-gate.yml job base-suite after the verdict, artifact handoff) or the moved one (registry-check.yml job base-suite as the Design section gives it: base checkout and sparse head checkout both with `persist-credentials: false`, no `git fetch`, the proposed files copied over scripts/gate with no action after, unconditional suites, no secret, no cache action, contents: read, not the registry job); every existing refusal keeps its wording and each other rule of both contracts is unchanged. Only the assertions that read the real workflow files' job layout change, which the owner's approval of this spec permits: the job lists at tests/scripts/test_spec_gate.py (`list(workflow[\"jobs\"]) == [\"gate\", \"base-suite\"]`) and tests/scripts/test_export_model_registry.py (`list(jobs) == [\"registry\"]`), and the base-suite block of `test_the_invoked_command_is_the_contract_and_policy_files_keep_their_schema` (export and upload in the gate job, `needs: gate`, the credential-free checkout, the download, the unconditional suite step); each asserts the same duty in whichever of the two layouts the files hold, and the synthetic workflows the suites build (`GATE_WF`, `gate_workflow()` and the literal spec-gate.yml fixtures) move to the moved layout as a pair of files, each case keeping its intent and expected outcome, except one named group of cases (`old_layout_*` in tests/scripts/test_spec_gate.py) that keeps today's layout to show it is still accepted whole and still refused when weakened; no other test, case or assertion changes, and every case's move is listed in the PR body. New tests show the gate refusing, in the moved layout, a base-suite job whose head checkout keeps credentials or is not sparse to the two files, that runs a `git fetch`, runs a suite before the copy or an action after it, reads a secret or restores a cache, refusing a pair that holds both layouts or neither, and accepting each layout whole, each recorded failing on main and passing on the head; main's own suites pass against the proposed gate in the hosted base-suite job, and both suites pass serially and with `-n 4`."
  - "Outside the `old_layout_*` group, the only cases whose spec-gate.yml fixture carries today's artifact handoff are the 34 capacity-bridged cases this spec names under Fixture transition, unchanged from main; every other case that needs today's layout accepted or recognised (accepted whole, a pair moving from it in one change, a pair dropping its suites from it, a pair holding it beside the moved layout) is an `old_layout_*` case, and the PR body lists both sets."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check green and zero unresolved threads are complete; the parent's other items stay with their own stages and no global completion is claimed."
status: approved
supersedes: null
---

# Gate base-suite move, stage one: the contract stage

## Authority

This is the stage primary for the contract stage of
`docs/superpowers/specs/2026-11-16-feat-cicd-001-base-suite-off-pull-request-target.md` (merged in
#2007), done_when item 2, in the way #1966 was the stage primary for Part A's live stage. It copies
that item and the records item 7 asks of every stage, and adds one item that pins down the fixture
transition below; it adds no implementation scope. The parent's Design, Sequence, Capacity, Risks
and Rollback sections govern this stage unchanged, except for the two admissions below, which the
owner's merge of this spec makes: the experiment that ran stands for parent item 1 as the repository
now is, and the fixture transition names what the retire stage inherits beyond the `old_layout_*`
group.

#2035, a draft successor of the parent, would restate item 1 for a public repository. This spec
neither depends on it nor supersedes it, and repeats its factual limits: visibility was checked on
2026-11-17, the repository's Actions event policy was not inspected, and no exploit, token exposure
or cache poisoning is established. It takes no position on the event policy or the required-check
swap; those stay owner settings steps (parent Sequence 3 and 6), each needing the owner's own
confirmation when its stage comes.

## Admission: the experiment

Parent item 1 asks for a throwaway draft PR whose registry-check.yml carries the moved job, run while
the repository is private. #2042 (closed unmerged) recorded one hosted run on 2026-11-17, with two
differences:

- The job lived in a new file, `.github/workflows/experiment-base-suite-move.yml` (job
  `moved-base-suite-experiment`), because the commit hook refuses an edit to registry-check.yml that
  differs from its pinned copy. It had the same event (plain `pull_request`), `contents: read`, the
  same two checkouts with the same options, the same copy and the same two suites. It added
  evidence-only lines (the head checkout's commit and files, the credential check, file hashes, the
  marker) and installed pytest, PyYAML and pytest-xdist 3.8.0 itself rather than through the
  registry job's pinned install.
- The repository was public, as it is today.

What the run shows: the head checkout reached the PR's commit, only the two files were on disk, they
landed in scripts/gate with no credentials left in either checkout, and main's gate suite (196
passed, four workers) and exporter suite (41 passed) ran against them. What it does not show: that
the head checkout reaches a PR's commits in a private repository, or the registry job's pinned
install in this job. The owner's merge of this spec admits #2042 as meeting parent item 1 for the
repository as it is. If the repository is made private before the live stage merges, the experiment
runs again, private, before that stage. The first run of the job in registry-check.yml itself is the
live stage's, which the parent's live-stage item already requires to pass every test of main's
suites.

## Fixture transition

The retire stage removes `old_layout_*` "and nothing else, so no test on main still requires
today's layout to be accepted". After this stage, the cases that put today's layout in a fixture are:

- The `old_layout_*` group, which holds every case that needs today's layout accepted or recognised:
  accepted whole, refused when weakened, a pair moving from it in one change, a pair dropping its
  suites from it, and a pair holding it beside the moved layout.
- 34 capacity-bridged cases, in oracle order: cases 7 and 8 of
  `test_a_workload_change_carries_its_capacity_numbers`, and cases 17, 20 to 23 and 25 to 51 of
  `test_lockfiles_twin_workflows_pins_at_step_one_and_ownership_are_the_contract`. They stay on
  `old_gate_workflow()` here because the capacity fixture bridge
  (`docs/superpowers/specs/2026-10-13-feat-cicd-001-capacity-fixture-bridge.md` and its 2026-11-04
  whole-job amendment) holds each of those functions to its recorded BASE oracle, case by case, so a
  moved fixture is an oracle change that bridge does not admit.

So the retire stage cannot meet its item by removing `old_layout_*` alone. Its own stage primary
must also admit, by name, a re-capture of those 34 cases: each case whose duty exists in the moved
layout (the gate job's permissions, writers, install and test allow-lists, pinned-copy, ownership and
capacity rules) moves to the moved pair with its verdict and reasons unchanged and its oracle entry
re-captured; each case whose duty exists only in today's layout (the artifact handoff, which the
moved layout does not have) leaves its function, with `CAPACITY_BRIDGE_CASES` lowered by the same
count, its duty going with the layout at the tighten stage. That PR records every changed oracle row.
No moved-layout coverage is removed, and the tighten stage's refusal is not weakened.

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
a pair and keep the `old_layout_*` group on today's layout, and the 34 capacity-bridged cases above
on today's layout, unchanged. The workflows and their pinned copies do
not change. The implementation is #2057.

## Capacity

As the parent's Capacity section: no workflow or workload changes. The gate suite grows by the new
tests in the same two jobs, inside the unchanged 600 s timeouts; the pull request body records the
local serial and four-worker times.

## Risks

As the parent's Risks section. The gate-file red-team pass runs on the frozen head before the push.

## Rollback

Revert the contract stage's pull request; the workflows and pinned copies are unchanged by it.
