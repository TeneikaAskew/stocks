---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1847]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "One PR makes .github/workflows/registry-check.yml byte-equal to scripts/gate/pinned/registry-check.yml and .github/workflows/spec-gate.yml byte-equal to scripts/gate/pinned/spec-gate.yml as they stand on MAIN (`cmp` of each pair recorded in the PR body); the pinned copies themselves, scripts/gate/spec_gate.py, the exporter and every test stay byte-identical to MAIN, and beyond the two live workflows the PR changes only its own plan and the delivery records (FEAT-CICD-001 catalog and traceability entries, SHARED-01 note row and its sidecar), with no other executable, workflow, test or dependency change."
  - "The hosted registry job on the exact head, which runs on plain `pull_request` and so executes the head's own workflow, passes every test of tests/scripts/test_spec_gate.py then on MAIN with `-n 4`; the hosted spec-gate base-suite job on the exact head, which runs on `pull_request_target` and so executes the base's workflow (serially until this stage merges), passes every test of the same suite; tests/scripts/test_export_model_registry.py passes unchanged in each job that runs it; the PR body records the gate-suite step time and the whole-job time of every attempt of both jobs on the head, against the same two times from the five most recent completed runs of each job on pull requests into main. The first four-worker base-suite run happens on a later pull request and is not an item of this stage."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check green and zero unresolved threads are complete; the parent's other items stay with their own PRs and no global completion is claimed."
status: approved
supersedes: null
---

# Test suite audit, Part A stage three: CI runs the gate suite on four workers

## Authority

This is the stage primary for Part A's live stage under
`docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when item 6), as that
spec's "Delivery contract" requires. It copies only item 6 and the records item 1 asks of every PR,
and adds no scope. The gate-policy stage merged as #1853, the prerequisite as #1858 and the pin
stage as #1903.

## Sequence

The pin stage made the trusted copies `scripts/gate/pinned/registry-check.yml` and
`scripts/gate/pinned/spec-gate.yml` install `pytest-xdist==3.8.0` and run the gate suite with `-n 4`.
The gate's pin-order rule accepts a live workflow only when it equals its pinned copy on the base, so
this stage is a plain copy: each live workflow becomes byte-equal to its copy on main.

The two jobs pick up the change at different times. registry-check.yml runs on plain
`pull_request` and executes the head's own workflow, so this stage's own registry job already runs
the gate suite on four workers. spec-gate.yml runs on `pull_request_target` and executes the base's
workflow, so this stage's own base-suite job still runs serially, and the first four-worker
base-suite run is on the first pull request whose base holds this stage. That run's step and job
times go in the next FEAT-CICD-001 PR body (the pin stage plan close-out).

## Design

`cp scripts/gate/pinned/registry-check.yml .github/workflows/registry-check.yml` and
`cp scripts/gate/pinned/spec-gate.yml .github/workflows/spec-gate.yml`. Each live workflow then
differs from main by exactly the two lines the pin stage changed in its copy: the install line and
the gate suite line. Timeouts, permissions, checkouts, runners and every other step are already
equal between each live workflow and its copy.

## Capacity

The registry job's own-suite step runs the gate suite on four workers on the hosted ubuntu-latest
runner from this stage's own head on; the spec-gate base-suite step does so from the first pull
request whose base holds this stage. The Part A experiment measured the gate suite there at a
median of 276.1 s serially against 123.7 s with four workers (run 43286379174); the PR body records
the real step and job times against the five most recent completed runs of each job on pull
requests into main. Job timeouts are unchanged (registry 10 minutes, spec-gate
base-suite 10 minutes).

## Risks

- **A hosted run behaves unlike the local and experiment runs.** The PR's own hosted jobs are the
  check: every test must pass with the same suite as main, and a failure holds the PR.
- **Older gate gaps the pin stage's red-team found stay open.** They predate Part A and are not
  widened by it (the four-worker base-suite run closes one: a proposed gate that exits the process
  on import now fails the run instead of passing it). They are listed in #1903 and go to their own
  spec.

## Rollback

The pin-order rule refuses a live workflow that differs from its copy, so a rollback is two PRs:
revert the pin stage's copies first, then make each live workflow equal to the reverted copy.
