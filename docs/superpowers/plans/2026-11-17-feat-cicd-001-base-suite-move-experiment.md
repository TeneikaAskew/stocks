---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-16-feat-cicd-001-base-suite-off-pull-request-target.md
branch: feature/feat-cicd-001-base-suite-move-experiment
status: ready
---

# Base-suite move, stage 0: one hosted run of the moved job (throwaway)

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** done_when item 1 of the spec. One throwaway draft pull request, closed unmerged with its gate red as expected, runs the base-suite job as the Design section gives it once on GitHub's hosted runners, and records that the head checkout reaches the pull request's commits, the two proposed files land in scripts/gate, and main's two suites run against them.

**Spec:** `docs/superpowers/specs/2026-11-16-feat-cicd-001-base-suite-off-pull-request-target.md` (approved, merged by #2007), Sequence step 0.

**Base:** main a92a9369. One branch, one draft PR, never merged.

## Deviations from the spec text, stated up front

- The spec puts the job in registry-check.yml. The commit-time gate refuses any edit to that file that does not equal its pinned copy, and refuses a new workflow that reuses the job key `base-suite`. So the job runs from a new file, `.github/workflows/experiment-base-suite-move.yml`, on the same trigger (`pull_request`, types opened, synchronize, reopened), with the same permissions and steps, under the job key `moved-base-suite-experiment`. The mechanism under test (trigger, base checkout, sparse head checkout without credentials, copy, suites) is the same.
- The spec says the run is recorded while the repository is private. The repository is public again since 2026-11-17 01:48Z, so the run is public; the private case is not recorded here.
- `scripts/gate/spec_gate.py` carries one added comment line (a marker) so the run can show the copied file is the head's and not the base's.

## Task 1: hosted run of the moved job
Spec: § Sequence, § Design. Advances done_when 1.
- [ ] Simulate the job locally first: a base checkout, a sparse no-credential clone of the head limited to the two files, the copy, and both suites (`-n 4` and serially for the gate suite).
- [ ] Open the draft PR with these three files and record from the job log the head sha the sparse checkout holds, the files it lists, that no `http.*extraheader` stayed in either checkout, the marker line in the copied `scripts/gate/spec_gate.py`, and both suites' results and times.
- [ ] Close the PR unmerged; any design change the run forces goes into the spec first.
