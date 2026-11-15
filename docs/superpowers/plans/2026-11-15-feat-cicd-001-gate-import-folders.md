---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-15-feat-cicd-001-test-suite-audit-a-import-folders.md
branch: feature/feat-cicd-001-gate-import-folders
status: ready
---

# Test suite audit, Part A follow-up: the gate guards folders the gate suites import from the checkout

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** `scripts/gate/spec_gate.py` counts as FEAT-CICD-001's work every path under a folder named after a startup import name at the places the gate suites import from, when the import would find nothing else, and every root `*.dist-info` or `*.egg-info` path. Nothing else executable changes.

**Spec:** `docs/superpowers/specs/2026-11-15-feat-cicd-001-test-suite-audit-a-import-folders.md` (approved, merged by #1969). Parent: `docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when item 6). It unblocks the live stage, #1968. Issue #1847.

**Base:** main b93f7662. One branch, one PR, one author.

## Global constraints

- Only the gate, its suite, this plan and the delivery records change; the four workflows and pinned copies stay byte-identical to main.
- Every existing test, case and assertion stays.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen head before the one push.

## Task 1: the experiment
Spec: § Problem. Advances done_when 1.
- [ ] On main 2eba6ebb in the pinned environment, plant each shape (setproctitle namespace, with and without a payload; `nt/_getfullpathname.py`; a root `zzq-1.0.dist-info` plugin; the `platform/` and `json/` controls) one at a time and run the serial gate suite, the four-worker gate suite and the exporter suite; record which processes ran the planted code and each outcome.

## Task 2: the gate rule and its tests
Spec: § Design. Advances done_when 2 and 3.
- [ ] Add the namespace-folder rule to `source_import_shadow()` and the package-metadata rule to `is_process_file()`.
- [ ] Add tests for every shape, real gate refusals and accepted controls; record them failing on main and passing on the head, and failing under each recorded one-line mutation.
- [ ] Confirm no tracked file on main changes classification.

## Task 3: the suite, red-team and records
Spec: § Risks. Advances done_when 4 and 5.
- [ ] Run the suite serially and with `-n 4` in a clean environment of exactly pytest, pyyaml and pytest-xdist==3.8.0; same node ids; the exporter suite passes.
- [ ] Gate-file red-team pass on the frozen head; findings fixed in one batch; then one push.
- [ ] Update the FEAT-CICD-001 catalog Status and Last reviewed, the PR lineage, and the SHARED-01 note row with the current source hash; produce and verify the sidecar; full-default docs audits on main and the head with nothing new.
- [ ] `spec_gate.py --pr` with the PR body; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads.
