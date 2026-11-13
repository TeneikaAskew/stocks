---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-GOV-004]
issues: [1847]
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "One PR changes only scripts/gate/pinned/registry-check.yml and scripts/gate/pinned/spec-gate.yml, so that the step `Proposed gate passes its own suite` and the base-suite step install pytest-xdist at one exact version (`pytest-xdist==3.8.0`) beside pytest and pyyaml and run tests/scripts/test_spec_gate.py with `-n 4`; tests/scripts/test_export_model_registry.py, every timeout-minutes value, permission, checkout, runner and other step stay byte-identical (the diff of each pinned copy is recorded as exactly its install line and its suite line), and .github/workflows/registry-check.yml and .github/workflows/spec-gate.yml stay byte-identical to MAIN."
  - "The native pin-order controls refuse a live-only and a simultaneous pin and live change (recorded gate runs), and recorded gate runs refuse the pinned copies with another worker count and with pytest-xdist unpinned; the base gate on the exact head accepts the two pinned copies."
  - "The PR body records the suite run exactly as the pinned steps would run it, in a clean environment holding only what their install line installs: tests/scripts/test_spec_gate.py passes with `-n 4` with the same node ids as the serial run on the exact head."
  - "Beyond the two pinned copies the PR changes only its own plan and the delivery records (FEAT-CICD-001 catalog and traceability entries, SHARED-01 note row and its sidecar), with no other executable, workflow, test or dependency change; own delivery records, ordinary SHARED-01 source proof, full-default main and proposed docs audits with no new finding, the gate-file red-team pass on the frozen head, current-head review as CLAUDE.md section 2.5 counts it, every required check and zero unresolved threads are complete; the parent's live-stage criteria stay with that PR and no global completion is claimed."
status: approved
supersedes: null
---

# Test suite audit, Part A stage two: the pinned gate workflows run the suite on four workers

## Authority

This is the stage primary for Part A's pin stage under
`docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when item 5), as that
spec's "Delivery contract" requires. It copies only item 5 and the records item 1 asks of every PR,
names the exact version item 5 leaves open, and adds no scope. The gate-policy stage it follows
merged as #1853.

## Sequence

The pin PR opens after `2026-11-12-feat-cicd-001-test-suite-audit-a-xdist-guards.md` merges, so the
names pytest-xdist imports and the pytest config files are FEAT-CICD-001's before any gate job is
set to install it. The live stage, a separate later PR bound to the parent, then makes the two
workflows equal to these copies; until it merges, CI still runs the suite serially.

## Design

In both pinned copies, the install line becomes
`python3 -m pip install --quiet pytest pyyaml pytest-xdist==3.8.0` and the gate suite line gains
`-n 4` at its end. The exporter suite line, the export step, every timeout, permission, checkout and
runner stay as they are. 3.8.0 is the current release, installs with the pytest the jobs resolve
today (9.2.0) and is the version the Part A experiment and the prerequisite were measured with.

## Capacity

No workload changes in this stage: the pinned copies are read by the gate, not run. The live stage
carries the timing record.

## Risks

- **pytest resolves to a release xdist 3.8.0 does not support.** The live stage's hosted run is the
  check; a failure there holds the live PR, and a version change is a pin-stage change again.

## Rollback

Revert the PR. The live workflows are unchanged, so nothing CI runs changes.
