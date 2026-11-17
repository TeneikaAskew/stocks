---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-14-feat-cicd-001-test-suite-audit-a-live.md
branch: feature/feat-cicd-001-gate-live-xdist-recut
status: done
pr: 2031
---

# Test suite audit, Part A stage three: CI runs the gate suite on four workers

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** the live stage of Part A. `.github/workflows/registry-check.yml` and `.github/workflows/spec-gate.yml` become byte-equal to their trusted copies `scripts/gate/pinned/registry-check.yml` and `scripts/gate/pinned/spec-gate.yml` on main, so each install line adds `pytest-xdist==3.8.0` and each gate suite line gains `-n 4`. Nothing else executable changes.

**Spec:** `docs/superpowers/specs/2026-11-14-feat-cicd-001-test-suite-audit-a-live.md` (approved, merged by #1966). Parent: `docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when item 6). Earlier stages: gate policy #1853, prerequisite #1858, pin #1903. Issue #1847.

**Base:** main 2eba6ebb. One branch, one PR, one author.

## Global constraints

- Each live workflow is a `cp` of its pinned copy on main, with `cmp` recorded; its diff against main is exactly the install line and the gate suite line.
- The pinned copies, `scripts/gate/spec_gate.py`, the exporter, `scripts/gate/pinned/pre-commit` and every test stay byte-identical to main.
- Beyond the two live workflows the PR changes only this plan and the FEAT-CICD-001 catalog, PR lineage, SHARED-01 note row and sidecar.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen head before the one push.
- The registry job runs the head's workflow (plain `pull_request`) and so runs the gate suite on four workers on this PR; the base-suite job runs the base's workflow (`pull_request_target`) and so still runs serially here. Its first four-worker run is recorded in the next FEAT-CICD-001 PR, not here.

## Task 1: the live workflows
Spec: § Design. Advances done_when 1.
- [ ] `cp` each pinned copy over its live workflow; record `cmp` of each pair, each live diff as exactly two lines, YAML loading, and the pinned copies, gate, exporter and tests byte-identical to main.

## Task 2: the suite as the live steps run it
Spec: § Sequence, § Capacity. Advances done_when 2.
- [ ] In a clean environment holding only what the install line installs, run `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest -n 4`, the same command serially, and `python3 -m pytest tests/scripts/test_export_model_registry.py -q -p no:cacheprovider --noconftest` on the exact head; record pass counts, times and identical node ids.
- [ ] After CI on the head, record the gate-suite step time and whole-job time of every attempt of the registry and base-suite jobs, against the five most recent completed runs of each job on pull requests into main.

## Task 3: gate-file red-team pass
Spec: § Risks. Advances done_when 3.
- [ ] One reviewer per attack surface (shell; YAML/Actions; exporter and policy documents), each bypass proven by running the gate against a concrete snippet, on the exact frozen head; findings fixed in one batch; then one push.

## Task 4: source identity, records and close
Spec: done_when 3.
- [ ] Update the FEAT-CICD-001 catalog Status and Last reviewed, the PR lineage, and the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this stage, keeping its earlier accurate content; produce and commit the sidecar; verify from the committed HEAD.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr` with the PR body; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads.
