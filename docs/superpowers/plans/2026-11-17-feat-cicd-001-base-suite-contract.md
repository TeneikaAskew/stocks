---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-17-feat-cicd-001-base-suite-contract-stage.md
branch: feature/feat-cicd-001-base-suite-contract
status: ready
pr: 2057
---

# Base-suite move, stage one: the gate accepts the moved layout

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** the contract stage. `scripts/gate/spec_gate.py` accepts the base-suite duties in exactly one of two layouts, judged across the live pair and, separately, across the pinned pair: today's (`spec-gate.yml` job `base-suite` after the verdict, artifact handoff) or the moved one (`registry-check.yml` job `base-suite` as the spec's Design section gives it). A pair holding both layouts or neither is refused. The workflows and their pinned copies do not change.

**Spec:** `docs/superpowers/specs/2026-11-17-feat-cicd-001-base-suite-contract-stage.md` (approved, merged by #2058 as 666804f9). The parent architecture remains #2007. Stage 0, the experiment, ran as throwaway draft #2042 (closed unmerged); the stage primary admits its public/dedicated-workflow evidence and limits.

**Base:** main ec245a58. One branch, one PR, one author.

## Global constraints

- Only `scripts/gate/spec_gate.py`, `tests/scripts/test_spec_gate.py` and `tests/scripts/test_export_model_registry.py` change in code; every existing refusal keeps its wording.
- Only the layout assertions the spec names change; the synthetic workflows move to the moved layout as a pair, each case keeping its intent and expected outcome, except the `old_layout_*` group, which keeps today's layout and holds every case that needs it accepted or recognised, and the 34 capacity-bridged cases the stage spec names, which keep it unchanged. Every moved case is listed in the PR body.
- Beyond those three files the PR changes only this plan and the FEAT-CICD-001 catalog, PR lineage, SHARED-01 note row and sidecar.
- No hook bypass. History was rewritten only on this unreviewed draft: once before the first push, and once to land the old_layout_* rename, which the commit hook judges against the previous commit (the earlier heads are kept on backup branches). The gate-file red-team pass runs on the frozen head before the one push.

## Task 1: the gate accepts exactly one layout per pair
Spec: § Design, § Sequence step 1. Advances stage-primary done_when 1 and 2.
- [x] Add the moved-layout contract beside today's, the layout judgement per pair (today, moved, both, neither) and the moved base-suite job's own refusals (head checkout credentials and sparseness, `git fetch`, suites before the copy, an action after it, a secret, a cache action, permissions, the registry job).

## Task 2: the suites
Spec: § Sequence step 1. Advances stage-primary done_when 1 and 2.
- [x] Widen the named layout assertions to either layout; move `GATE_WF`, `gate_workflow()` and the literal spec-gate.yml fixtures to the moved layout as a pair; keep the `old_layout_*` group on today's layout.
- [x] Add the refusal and acceptance tests the spec names; record each failing on main's gate and passing on the head.
- [x] Run both suites serially and with `-n 4` on the head, and main's suites against the head's gate.

## Task 3: gate-file red-team pass
Spec: § Risks. Advances stage-primary done_when 3.
- [x] One reviewer per attack surface (shell; YAML/Actions; exporter and policy documents), each bypass proven by running the gate against a concrete snippet, on the exact frozen head; findings fixed in one batch; repeat until a pass finds nothing; then one push.

## Task 4: source identity, records and close
Spec: stage-primary done_when 3.
- [ ] Update the FEAT-CICD-001 catalog Status and Last reviewed, the PR lineage, and the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this stage, keeping its earlier accurate content; produce and commit the sidecar; verify from the committed HEAD.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head.
- [ ] `python3 scripts/gate/spec_gate.py --pr` with the PR body; the hosted base-suite job passes main's suites against the proposed gate; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads.
