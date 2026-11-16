---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Before the contract stage, a throwaway draft PR (closed unmerged, its red gate expected) whose registry-check.yml carries the moved base-suite job as designed here records one hosted run on this repository while it is private: the head checkout reaches the PR's commits, the two proposed files land in scripts/gate, and main's two suites run against them; a design change that run forces is made to this spec first."
  - "A contract-stage PR changes only scripts/gate/spec_gate.py and the two gate suites: WORKFLOW_CONTRACTS accepts the base-suite duties in exactly one of two layouts, judged across the live pair and, separately, across the pinned pair: today's (spec-gate.yml job base-suite after the verdict, artifact handoff) or the moved one (registry-check.yml job base-suite as the Design section gives it: base checkout and sparse head checkout both with `persist-credentials: false`, no `git fetch`, the proposed files copied over scripts/gate with no action after, unconditional suites, no secret, no cache action, contents: read, not the registry job); every existing refusal keeps its wording and each other rule of both contracts is unchanged. Only the assertions that read the real workflow files' job layout change, which the owner's approval of this spec permits: the job lists at tests/scripts/test_spec_gate.py (`list(workflow[\"jobs\"]) == [\"gate\", \"base-suite\"]`) and tests/scripts/test_export_model_registry.py (`list(jobs) == [\"registry\"]`), and the base-suite block of `test_the_invoked_command_is_the_contract_and_policy_files_keep_their_schema` (export and upload in the gate job, `needs: gate`, the credential-free checkout, the download, the unconditional suite step); each asserts the same duty in whichever of the two layouts the files hold, and the synthetic workflows the suites build (`GATE_WF`, `gate_workflow()` and the literal spec-gate.yml fixtures) move to the moved layout as a pair of files, each case keeping its intent and expected outcome, except one named group of cases (`old_layout_*` in tests/scripts/test_spec_gate.py) that keeps today's layout to show it is still accepted whole and still refused when weakened; no other test, case or assertion changes, and every case's move is listed in the PR body. New tests show the gate refusing, in the moved layout, a base-suite job whose head checkout keeps credentials or is not sparse to the two files, that runs a `git fetch`, runs a suite before the copy or an action after it, reads a secret or restores a cache, refusing a pair that holds both layouts or neither, and accepting each layout whole, each recorded failing on main and passing on the head; main's own suites pass against the proposed gate in the hosted base-suite job, and both suites pass serially and with `-n 4`."
  - "A pin-stage PR, whose base holds the contract stage, changes only scripts/gate/pinned/registry-check.yml (gains job base-suite) and scripts/gate/pinned/spec-gate.yml (keeps only job gate) to the moved layout; the base's gate accepts it, and .github/workflows/registry-check.yml and .github/workflows/spec-gate.yml stay byte-identical to MAIN."
  - "A live-stage PR makes each live workflow byte-equal to its pinned copy on MAIN (`cmp` recorded) and changes nothing else executable; on its exact head the registry-check base-suite job (plain `pull_request`, the head's workflow) and the spec-gate base-suite job (`pull_request_target`, the base's workflow) both pass every test of main's suites; its body lists every workflow file with its trigger and each job that executes head content, showing no workflow runs pull-request-controlled code under `pull_request_target`, and gives the owner's one settings step for the same sitting as its merge (in the required status checks of main's branch protection or ruleset, replace `spec-gate / base-suite` with `registry-check / base-suite`)."
  - "A retire-stage PR, whose base holds the live stage, removes the `old_layout_*` group and nothing else, so no test on main still requires today's layout to be accepted; the base's base-suite job passes against the unchanged gate."
  - "A tighten-stage PR, whose base holds the retire stage, removes today's layout from WORKFLOW_CONTRACTS and narrows the layout assertions to the moved layout alone, so a later PR that puts a suite back into spec-gate.yml is refused, with that refusal recorded failing on the retire stage's merge and passing on the head; the first PR opened after the live stage shows `registry-check / base-suite` reported and required."
  - "Each stage's own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on each frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check green and zero unresolved threads are complete."
status: approved
supersedes: null
---

# Gate base-suite job moves off pull_request_target

## Why

`spec-gate.yml` runs on `pull_request_target`, so GitHub takes the workflow and `scripts/gate/` from
the base and a pull request cannot edit the check that judges it. Its `gate` job reads the PR head
only as data. Its `base-suite` job is different: it runs the PR's proposed `spec_gate.py` and
`export_model_registry.py` under main's tests, which is pull-request-controlled Python running in
the base repository's context. It holds no secret and its checkout keeps no credentials, but it runs
with main's cache scope, and another workflow (Backtest Pipeline) restores a cache on main and holds
a secret, so a poisoned cache entry is a path from a pull request to a privileged run.

GitHub now blocks `pull_request_target` by default in public repositories (brownouts on
2026-11-09 and 2026-11-16, enforced from 2026-12-02) unless an Actions event policy allows it. The
repository is private today, so the block does not apply, but the owner may make it public again
(2026-11-16). The narrowest allow is one policy for `.github/workflows/spec-gate.yml` only. That
allow is only as safe as what the workflow runs, so this spec takes the one job that runs PR code
out of it first.

## Design

`registry-check.yml` already runs on plain `pull_request` with a read-only token, no secrets and
the pull request's own cache scope, and the gate already keeps it honest: the live file must equal
its pinned copy on the base (`PINNED`), and `WORKFLOW_CONTRACTS` checks what each job must still
do. The base-suite job moves there as a second job, `base-suite`, doing what it does today:

- check out the base sha with `persist-credentials: false`;
- check out the head sha a second time, into a subdirectory, with `persist-credentials: false`
  and `sparse-checkout` (with `sparse-checkout-cone-mode: false`) limited to `scripts/gate/spec_gate.py` and
  `scripts/gate/export_model_registry.py`. `actions/checkout` authenticates its own fetch with the
  job's read-only token and keeps no credentials after it, so the head is reached in a private
  repository too and no later step holds a token. There is no `git fetch` step: once credentials
  are gone an unauthenticated fetch fails in a private repository;
- copy the two proposed files over the base copies in `scripts/gate/`, remove the subdirectory,
  and run no action after that copy, so nothing puts the base's files back;
- install the same pinned tools as the registry job and run main's
  `tests/scripts/test_spec_gate.py` (on four workers, as the live stage of Part A set) and
  `tests/scripts/test_export_model_registry.py`, unconditionally;
- `permissions: contents: read`, no secret, no cache action, 10-minute timeout.

`spec-gate.yml` keeps only its `gate` job, unchanged.

What changes in trust: today the base-suite job runs the base's copy of its own workflow; after
the move it runs the head's copy, which the base's gate requires to equal the pinned copy on the
base, exactly as for the registry job. A pull request that edits either workflow outside a
FEAT-CICD-001 pin or live stage fails the gate, which stays on `pull_request_target` and stays a
required check. The new job no longer waits for the gate's verdict (`needs` does not cross
workflows); it holds nothing the verdict protects, and the merge still needs both checks.

A side effect: the base-suite job's four-worker run starts on the live-stage PR itself, because
`pull_request` takes the head's workflow.

## Sequence

The base's gate judges every pull request, including the one that changes the gate, and its
contract today requires the suites inside `spec-gate.yml`. A pull request that moves them in one
step is refused by the very gate it carries a fix for, so the move lands in stages, each judged
by a base that already accepts it:

0. Experiment: a throwaway draft PR runs the moved job once on this private repository, to prove
   the head checkout and the copy work before anything is built on them.
1. Contract stage (FEAT-CICD-001): `WORKFLOW_CONTRACTS` accepts either layout whole, never both or
   neither, and the assertions that read the real workflows' job layout (named in done_when) accept
   the same two layouts. The workflows and pinned copies do not change. The owner's approval of
   this spec is the say-so for changing those assertions and for moving the synthetic workflow
   fixtures to the new layout, keeping one named group (`old_layout_*`) on today's layout; any
   other existing test the stage would have to change goes back to the owner first.
2. Pin stage (FEAT-CICD-001): the pinned copies move to the new layout.
3. Live stage (FEAT-CICD-001): each live workflow becomes a `cp` of its pinned copy.
   Owner, in the same sitting as its merge: replace the required check `spec-gate / base-suite`
   with `registry-check / base-suite`. Until then every pull request waits on a check that no
   longer reports.
4. Retire stage (FEAT-CICD-001): the `old_layout_*` group goes. The base's own suite judges every
   proposed gate, so no test on the base may still expect today's layout to pass when the tighten
   stage proposes refusing it.
5. Tighten stage (FEAT-CICD-001): the contract and the layout assertions drop today's layout, so the
   suites cannot move back under `pull_request_target`.
6. Owner, only if the repository becomes public: allow `pull_request_target` for
   `.github/workflows/spec-gate.yml` only, in Settings, Actions, Policies, as written up separately.

Between stages 1 and 5 the contract accepts both layouts. That is no weaker than today for either
one: each layout must hold every duty it holds today, and a pull request still cannot edit a live
workflow except to make it equal to its pinned copy on the base.

## Capacity (CLAUDE.md rule 0)

- Volume: the same two suites per pull request push (196 and 41 tests on main c57009f6).
- Velocity: one registry-check run per push, as today; one spec-gate run per push, edit or ready
  event, as today, with one job instead of two.
- Wall-clock: 600 s job timeouts, unchanged. The base-suite step took 250 to 370 s serially on the
  five main-bound runs before the Part A live stage; on four workers the suite measured 123.7 s on
  hosted ubuntu-latest (run 43286379174).
- Cost: 0 new jobs per run; the same job moves between workflows.

## Risks

- **The required-check swap is missed.** Every pull request then waits on `spec-gate / base-suite`.
  The live-stage PR body carries the step and the merge link goes with it.
- **The gate's contract misses a weakening of the new job.** The contract-stage tests name each
  weakening above, and the red-team pass runs on each frozen head.
- **Both layouts accepted for too long.** The tighten stage is part of this spec, not a follow-up.
- **Older gate gaps stay open.** The gaps listed on #1903 and #1971 go to their own spec.

## Rollback

In reverse stage order, each its own PR judged by the base it lands on: the contract accepts both
layouts again (undo the tighten stage); the `old_layout_*` group returns; the pinned copies and then
the live workflows go back to today's layout, with the required check swapped back in the same
sitting as the live merge; the synthetic fixtures move back to today's layout; and last the contract
and layout assertions drop the moved layout.
