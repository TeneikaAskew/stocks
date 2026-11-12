---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1847, 1849]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The PR body records the Part A experiment on main 56d63397 with identical suite and gate bytes in both modes: on one ordinary 4-core Linux machine and on hosted ubuntu-latest (run 43286379174), the wall-clock of three serial and three `-n 4` runs of tests/scripts/test_spec_gate.py, every run passing the same 185 node ids, and the failing node ids of each mutated-gate control (the empty done_items, invokes accepting any tail and the deferral pattern without WIP, plus locally the pip check with `and` for `or`), identical in both modes; the 4-worker median is at least 40 percent below the serial median on both machines."
  - "scripts/gate/spec_gate.py accepts the suite contract command `python3 -m pytest tests/scripts/test_spec_gate.py` with exactly the extra arguments `-n 4` (two words, in that order) beside the arguments already in PYTEST_ARGS, and refuses every other worker form; new tests in tests/scripts/test_spec_gate.py accept the exact command and refuse `-n 3`, `-n auto`, `-n4`, `--numprocesses 4`, `--dist load`, `-p xdist`, `--maxprocesses 4` and a second `-n 4`, and refuse a step whose pip line installs `pytest-xdist` without an exact `==` version; each new acceptance test is recorded failing on main and passing on the head, and each new refusal test passing on the head and failing on a recorded one-line gate mutation that lets that form through."
  - "New tests in tests/scripts/test_spec_gate.py refuse a spec whose frontmatter has no `status` and a spec whose status is outside draft, approved and superseded (#1849); each is recorded passing on the head and failing on the one-line mutation that removes `status` from REQUIRED_SPEC_KEYS or adds a status to SPEC_STATUSES."
  - "Every existing test, case and assertion in tests/scripts/test_spec_gate.py stays and passes, the suite passes serially and with `-n 4` on the exact head with the same node ids, and .github/workflows/registry-check.yml, .github/workflows/spec-gate.yml, scripts/gate/pinned/registry-check.yml and scripts/gate/pinned/spec-gate.yml stay byte-identical to MAIN; beyond the gate and its suite the PR changes only its own plan and the delivery records (FEAT-CICD-001 catalog and traceability entries, SHARED-01 note row and its sidecar)."
  - "Own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check and zero unresolved threads are complete; the parent's pin-stage and live-stage criteria stay with those PRs and no global completion is claimed."
status: approved
supersedes: null
---

# Test suite audit, Part A stage one: the gate accepts exactly the four-worker suite command

## Authority

This is the stage primary for Part A's gate-policy stage under
`docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when items 3 and 4),
as that spec's "Delivery contract" requires: the ready-for-review close-out check ticks every item of
the bound spec, so this PR cannot bind the parent. It carries only this stage's items and the records
item 1 of the parent asks of every PR. It adds no scope beyond the parent's items 3 and 4.

## Problem

`invokes()` in scripts/gate/spec_gate.py accepts a pytest contract command only when its extra
arguments are a subset of PYTEST_ARGS, which holds neither `-n` nor `4`. A pinned or live workflow
running the gate suite with `-n 4` would lose its required suite invocation in the gate's eyes and
be refused by `tool_offence()` (#1847). The experiment also found two one-line gate changes the suite
does not catch: dropping `status` from REQUIRED_SPEC_KEYS and adding a status to SPEC_STATUSES (#1849).

## Design

Accept the exact tail `-n 4` for the suite contract command only, as a fixed pair, so no other worker
count, alias or distribution mode passes, and require an exact `==` version for `pytest-xdist` in a
pip line. Add the #1849 refusal tests in the same PR, because both are gate-suite changes that take
the same red-team pass. No workflow or pinned copy changes in this stage; the pin stage follows once
this merges, then the live stage.

## Capacity

No workload changes in this stage: the suite still runs serially in CI. Test count rises by the new
tests only (about a dozen), each a temporary-repository check like its neighbours.

## Risks

- **The gate accepts more than intended.** Each refused form has its own test and a recorded mutation
  that the test catches.
- **A later worker count needs a new gate change.** Intended: the worker count is a reviewed decision.

## Rollback

Revert the PR. Nothing outside the gate and its suite changes, and no workflow uses `-n 4` until the
pin stage.
