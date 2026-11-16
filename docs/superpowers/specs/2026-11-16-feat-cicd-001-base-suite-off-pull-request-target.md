---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "A pin-stage PR changes only the trusted copies and the gate: scripts/gate/pinned/registry-check.yml gains a job named base-suite and scripts/gate/pinned/spec-gate.yml keeps only its gate job; WORKFLOW_CONTRACTS in scripts/gate/spec_gate.py moves the base-suite contract (base checkout without credentials, proposed gate and exporter read from the fetched head with `git show` and written over scripts/gate before the suites, main's tests/scripts/test_spec_gate.py and tests/scripts/test_export_model_registry.py run, no secret, no cache action, contents: read) from spec-gate.yml to registry-check.yml; .github/workflows/registry-check.yml and .github/workflows/spec-gate.yml stay byte-identical to MAIN; new tests in tests/scripts/test_spec_gate.py show the gate refusing a registry-check.yml whose base-suite job checks out the head, keeps credentials, runs the suites before the proposed files are written, reads a secret or restores a cache, and refusing a spec-gate.yml that still runs a suite, each recorded failing on main and passing on the head; every existing test, case and assertion stays and passes serially and with `-n 4`."
  - "A live-stage PR makes each live workflow byte-equal to its pinned copy on MAIN (`cmp` recorded) and changes nothing else executable; on its exact head the registry-check base-suite job (plain `pull_request`, the head's workflow) and the spec-gate base-suite job (`pull_request_target`, the base's workflow) both pass every test of main's suites, and a recorded throwaway PR whose proposed gate fails main's suite turns the new job red."
  - "After the live stage no workflow in the repository runs pull-request-controlled code under `pull_request_target`: the live-stage PR body lists every workflow file with its trigger and each job that executes head content, and spec-gate.yml's only job reads the head as data."
  - "The live-stage PR body gives the owner's one settings step for the same sitting as its merge (in the required status checks of main's branch protection or ruleset, replace `spec-gate / base-suite` with `registry-check / base-suite`), and the first PR opened after it shows `registry-check / base-suite` reported and required."
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
- fetch the head as git objects and write the proposed `scripts/gate/spec_gate.py` and
  `scripts/gate/export_model_registry.py` over the base copies with `git show`;
- install the same pinned tools as the registry job and run main's
  `tests/scripts/test_spec_gate.py` (on four workers, as the live stage of Part A set) and
  `tests/scripts/test_export_model_registry.py`;
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

1. Pin stage (FEAT-CICD-001): the pinned copies, `WORKFLOW_CONTRACTS` and its tests.
2. Live stage (FEAT-CICD-001): each live workflow becomes a `cp` of its pinned copy.
3. Owner, in the same sitting as the live-stage merge: replace the required check
   `spec-gate / base-suite` with `registry-check / base-suite`. Until then every pull request waits
   on a check that no longer reports.
4. Owner, only if the repository becomes public: allow `pull_request_target` for
   `.github/workflows/spec-gate.yml` only, in Settings, Actions, Policies, as written up separately.

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
- **The gate's contract misses a weakening of the new job.** The pin-stage tests name each
  weakening above, and the red-team pass runs on each frozen head.
- **Older gate gaps stay open.** The gaps listed on #1903 and #1971 go to their own spec.

## Rollback

Two PRs, in the pin-order the gate requires: revert the pinned copies and contract, then make each
live workflow equal to the reverted copy, with the required check swapped back in the same sitting.
