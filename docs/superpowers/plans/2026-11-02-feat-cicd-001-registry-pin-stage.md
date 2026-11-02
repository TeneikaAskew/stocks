---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-02-feat-cicd-001-registry-ten-minute-pin.md
branch: feature/feat-cicd-001-registry-pin-stage
pr: 1696
status: ready
---

# Registry ten-minute envelope: pin stage implementation plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** the pin stage of the approved ten-minute registry envelope. Only the trusted pinned copy `scripts/gate/pinned/registry-check.yml` moves `jobs.registry.timeout-minutes` from 6 to 10. The live workflow `.github/workflows/registry-check.yml` stays at 6 and bounds this PR's own run; a separate live-stage PR, bound to the unchanged parent spec, follows after this one merges.

**Spec:** `docs/superpowers/specs/2026-11-02-feat-cicd-001-registry-ten-minute-pin.md` (approved pin-stage primary, on main since 1ac70bfd, #1693). Parent design: `docs/superpowers/specs/2026-11-02-feat-cicd-001-registry-ten-minute-envelope.md` (#1683), unchanged and kept for the live stage. Issue #1684 N1's pin-stage text check is carried in the primary's done_when 1.

**Lineage.** Rebuilt from the earlier local candidate 60d38d57 (never pushed), which bound the parent and could not go Ready. The pinned-copy change is byte-identical to that candidate's (blob 8756f0f5).

**Base:** main 1ac70bfd. One branch, one PR, one author.

## Global constraints

- One changed line in the pinned copy; no other execution, permission, dependency, isolation, runner, trigger, check-name or runtime-deadline change.
- The live workflow, `scripts/gate/pinned/spec-gate.yml`, `scripts/gate/pinned/pre-commit`, every gate validator and every test are unchanged.
- No hook bypass, no history rewrite. The gate-file red-team pass runs on the frozen candidate before the one push.
- The operation refused on stocks#1630 is not retried, replaced or routed around.
- The parent's live-stage criteria (timing record, 120-second reserve, live timeout) are not applied or claimed here.

## Task 1: the pinned copy
Spec: Exact scope and sequence. Advances done_when 1.
- [ ] `scripts/gate/pinned/registry-check.yml`: `    timeout-minutes: 6` becomes `    timeout-minutes: 10` at the `registry` job level; the live workflow stays byte-identical to main.

## Task 2: value and text assertions with negative controls
Spec: done_when 1 (#1684 N1).
- [ ] Record a YAML load asserting `jobs.registry.timeout-minutes` is the integer 10 at job level in the pinned copy, with negative controls failing for the key missing, the value only on a step and the value quoted as "10".
- [ ] Record the literal check: exactly one changed line, `    timeout-minutes: 6` to `    timeout-minutes: 10`, in the `registry` job, with `012`, `0xA`, `1_0`, `+10`, `!!int "10"`, `"10"`, `10.0`, a second job without a timeout, a step-level `timeout-minutes` and a change on any other line each failing.

## Task 3: native pin-order and contract controls
Spec: Exact scope and sequence. Advances done_when 2.
- [ ] The gate passes this pin-only change, and refuses a live-only timeout change and a simultaneous pin and live change, each run as a concrete snippet against the real gate.
- [ ] `tests/scripts/test_spec_gate.py` and the workflow-contract tests pass unchanged and serial.

## Task 4: gate-file red-team pass
Spec: Exact scope and sequence. Advances done_when 4.
- [ ] One reviewer per attack surface (shell; YAML/Actions; exporter and policy documents), each bypass proven by running the gate against a concrete snippet, on the exact frozen head; findings fixed in one batch; then one push.

## Task 5: hosted registry job
Spec: Stage acceptance and evidence. Advances done_when 3.
- [ ] The exact-head registry job, still bounded at six minutes, passes with the unchanged exporter; record its head and whole-job time, without claiming the ten-minute envelope is active.

## Task 6: source identity, records and close
Spec: done_when 4.
- [ ] Update only the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this stage, keeping its earlier accurate content; produce and commit the sidecar from the final committed body; verify from the committed HEAD.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] Catalog and PR-traceability records; `python3 scripts/gate/spec_gate.py --pr` with the PR body.
- [ ] Current-head review as CLAUDE.md section 2.5 counts it, or an owner-recorded substitute for this PR; every required check; zero unresolved threads.
