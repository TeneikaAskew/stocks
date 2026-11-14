---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-a-pin.md
branch: feature/feat-cicd-001-gate-pin-xdist
status: ready
pr: 1903
---

# Test suite audit, Part A stage two: the pinned gate workflows run the suite on four workers

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** the pin stage of Part A. Only the trusted pinned copies `scripts/gate/pinned/registry-check.yml` and `scripts/gate/pinned/spec-gate.yml` change: each install line adds `pytest-xdist==3.8.0`, and each gate suite line gains `-n 4` at its end. The live workflows stay byte-identical to main, so CI still runs the suite serially until the live stage, a separate later PR bound to the parent spec.

**Spec:** `docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-a-pin.md` (approved, merged by #1855). Parent: `docs/superpowers/specs/2026-11-12-feat-cicd-001-test-suite-audit-r2.md` (done_when item 5). Its sequence holds: the prerequisite merged as #1858 under revision 2 (#1856), so the names pytest-xdist imports and the pytest config files are FEAT-CICD-001's before any gate job is set to install it. Issue #1847.

**Base:** main 70bc41da. One branch, one PR, one author.

## Global constraints

- Two changed lines in each pinned copy: the install line becomes `python3 -m pip install --quiet pytest pyyaml pytest-xdist==3.8.0`, and the `tests/scripts/test_spec_gate.py` suite line gains ` -n 4`. The exporter suite line, the export step, every timeout, permission, checkout, runner and other step stay as they are.
- `.github/workflows/registry-check.yml`, `.github/workflows/spec-gate.yml`, `scripts/gate/pinned/pre-commit`, every gate validator and every test are unchanged.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen head before the one push.
- The parent's live-stage criteria (hosted timing record, live workflows equal to these copies) are not applied or claimed here.

## Task 1: the pinned copies
Spec: § Design. Advances done_when 1.
- [ ] In both pinned copies, the install line and the gate suite line change as above; record each copy's diff as exactly those two lines, and the live workflows byte-identical to main.

## Task 2: native pin-order and pin-policy controls
Spec: § Sequence. Advances done_when 2.
- [ ] Record the real gate in PR mode on the suite's own fixture repo, with main's workflow bytes as base and copies: the two new copies together and each alone pass; a live-only change and a simultaneous pin and live change are refused for each workflow; the copies with `-n 2`, `-n 8`, `-n auto`, unpinned `pytest-xdist` and `pytest-xdist>=3.8.0` are refused; and, once the copies land on the base, each live workflow equal to its copy passes.

## Task 3: the suite as the pinned steps run it
Spec: § Design. Advances done_when 3.
- [ ] In a clean environment holding only what the install line installs (pytest, pyyaml, pytest-xdist==3.8.0 and their dependencies), run `python3 -m pytest tests/scripts/test_spec_gate.py -q -p no:cacheprovider --noconftest -n 4` and the same command without `-n 4` on the exact head; record pass counts, times and identical node ids.

## Task 4: gate-file red-team pass
Spec: § Risks. Advances done_when 4.
- [ ] One reviewer per attack surface (shell; YAML/Actions; exporter and policy documents), each bypass proven by running the gate against a concrete snippet, on the exact frozen head; findings fixed in one batch; then one push.

## Task 5: source identity, records and close
Spec: done_when 4.
- [ ] Update the FEAT-CICD-001 catalog Status and Last reviewed, the PR lineage, and the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this stage, keeping its earlier accurate content; produce and commit the sidecar; verify from the committed HEAD.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr` with the PR body; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads.
