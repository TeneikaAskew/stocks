---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-25-feat-cicd-001-registry-measured-acceptance.md
branch: fix/feat-cicd-001-registry-envelope-measured
pr: null
status: ready
---

# Matching live registry CI envelope

> For agentic workers: use superpowers:executing-plans. Same existing writer; root is sole publisher. Retain original checkpoint1ede2ccc, pin reviews and stopped candidates.

## Binding and authority

The approved parent #1586 and live-stage primary #1589 are MAIN. Pin #1591 reviewed head `6b6f031e7ff71f75adcae24285baf5366ec41768` merged as actual MAIN `05ab15fcc762e0ce02ddd4ce654604375dbb93df`; pin6/live5 bytes independently checked, all original gate/exporter/suite/hook bytes unchanged. This branch starts only after that merge, not stacked.

Ruling: The owner's explicit one-time #1591 exception supersedes only the pin job-terminal-success and directly dependent readiness conditions. Keep its original 144PASS280.96s/exporter-current evidence and raw CANCELLED status. Interpret the final both-stage receipt criterion with that already-consumed pin exception, never as an unqualified assertion of two green stages. Every nonexcepted pin check and every live check must pass; this grants no second exception. The285s suite target is a CI acceptance target, not a production runtime deadline. Prior reviews and their two-round budgets are retained.

## Files and fixed constraints

Modify only `.github/workflows/registry-check.yml` for executable behavior: `jobs.registry.timeout-minutes: 5` becomes literal `6`, matching the already-landed pin. Existing regression controls are `tests/scripts/test_spec_gate.py::test_gate_workflows_and_hook_are_pinned_and_hidden_steps_are_scanned` and `tests/scripts/test_spec_gate.py::test_lockfiles_twin_workflows_pins_at_step_one_and_ownership_are_the_contract`; run their actual native probes without adding value-mirroring tests.

Delivery-only files: this unique plan; owned FEAT-CICD-001 catalog/traceability records; only declared SHARED-01 SITE note; ordinary `docs/review-evidence/site-source-snapshot.json`; one scoped evidence receipt. Preserve every other row and executable byte.

Review focus: a live-only increase must fail when the base pin is5; simultaneous pin/live mutation must fail; exact native suite and exporter invocations must remain; read-only permissions and original event/runner/dependencies remain; identity/source-drift and oversized-input refusals remain. Existing workflow-contract controls and scoped four-seat concrete probes cover those conditions. Wholejob≤335seconds and reserve≥25seconds under360seconds remain mandatory; original285target UNMET stays historical.

## Task 1: bind and match the live workflow
Spec: § Prerequisites and exact scope. Advances done_when[0] and done_when[1].
- [ ] Preserve actual pin MAIN/merge/head/source proof and raw timing receipts; inspect current protection restoration without changing settings.
- [ ] Publish this normally gated PLANONLY draft, then commit its actual PR-number binding before CODE.
- [ ] Change only `.github/workflows/registry-check.yml` jobs.registry.timeout-minutes5to6, exactly matching the pin already on BASE. Leave pin and every other execution byte unchanged.
- [ ] Run existing native pin-order/workflow-contract controls; no number-mirroring test or full local suite repeat.
- [ ] Use all four existing prepush reviewer seats for scoped concrete probes; fix only confirmed introduced defects in one batch, retaining review limits.

## Task 2: ordinary owned delivery evidence
Spec: §§ Prerequisites and exact scope; Unchanged arithmetic and observation criteria. Advances done_when[3].
- [ ] Update only own FEAT-CICD-001 catalog/status/current commit date and traceability, preserving existing lineage.
- [ ] Update the declared SHARED-01 implementation-source note and ordinary immutable sidecar from committed source; independently verify within5s/8MiB/20000entries.
- [ ] Run full-default actual MAIN/proposed audits with duplicate-preserving all-severity no-new comparison, reusing an unchanged exact-main baseline if available.
- [ ] Run ordinary BASE/proposed PR gate and normal commit hook; preserve every test/assertion/isolation/command, readonly permission and runtime/renderer/verifier deadline.

## Task 3: hosted completion and normal merge
Spec: §§ Unchanged arithmetic and observation criteria; Cost, side effects and rollback. Advances done_when[2] and done_when[3].
- [ ] Record exact-head/base suite counts/warnings/skips, pytest time and complete job/step timings, exporter mode and cleanup.
- [ ] Require live registry six-minute job SUCCESS, the unchanged144tests and exporter to pass; record each stage and preserve original59b9a309 pytest288.72s versus285s targetUNMET; complete job≤335s (at least25s headroom under360s). Label unavailable environmental/billing evidence as unknown; no speed claim or fabricated inputs.
- [ ] Obtain clean current-head Codex code/security reviews, all required CI and zero unresolved threads, truthful DoD evidence acknowledging the consumed pin exception. Restore normal bypass restriction before merge; never use --admin or another exception.
- [ ] Confirm no migration/deploy/provider/GCP/SQL side effect; only nominal CI allowance300to360s increases. Merge normally only after all unwaived obligations pass.
- [ ] Verify actual merged MAIN live/pin equality6 and ordinary source identity. Report actual hosted completion and remaining documentation/parent dependencies without claiming production deployment. If a fresh capacity/evidence failure occurs, diagnose; no blind retry or safety relaxation.

## Explicit ownership and lineage handoff

The original fixture owner continuation failed to start (CloudThreadNotFoundError).
Parent assigned this existing fixture chain to root/fixture_finish on October25.
No competing writer was found in remote comments, local worktrees or running processes.
Use the same accepted live5to6 patch and preserve #1592/59b9a309 original reviews,
original285s targetUNMET at288.72s, complete311s/49sreserve and all prior raw failures.
This unique branch/plan is required by #1594 immutable primary binding, not a fresh
allowance or a timing retry. No accepted source components are rebuilt. Existing
review effort is retained; normal new-head verification cannot substitute for the
original observed sample or claim speed improvement. #1592 closes only after an
actually merged legitimate successor, with its original evidence intact.
