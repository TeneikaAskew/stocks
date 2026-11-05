---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-04-feat-cicd-001-done-and-autonomy.md
branch: feature/feat-cicd-001-done-and-autonomy
pr: null
status: ready
---

# Owner directive in CLAUDE.md: definition of done and autonomy

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Spec:** `docs/superpowers/specs/2026-11-04-feat-cicd-001-done-and-autonomy.md` (approved, on main since 692304b, #1705).

**Base:** main 692304b. One branch, one PR, one author.

## Global constraints

- Only CLAUDE.md gains the new section; no other line of CLAUDE.md changes.
- AGENTS.md, `.claude/`, `.githooks/`, `.github/` and `scripts/gate/` are byte-identical to main.
- No code, workflow, job or schema change, so no workload runs differently and no GCP cost changes.

## Task 1: add the owner directive
Spec: Decision 1 to 5; done_when 1 and 2.
- [ ] Insert `## Definition of done and autonomy (owner directive)` directly after `## Before any change (read this first)`, stating done (merged, deployed where the change ships, verified with tests, Playwright evidence per AGENTS.md `## Review guidelines`, and real GCP queries, recorded on the PR), reversible calls within the spec gate, review cap and gate-file red-team rules, the three stop conditions with one specific question, the latest owner instruction superseding earlier holds, and a blocked lane opening a small PR or coordinating.
- [ ] `git diff origin/main -- CLAUDE.md` shows only added lines inside that section; no other process file appears in the diff.

## Task 2: records
Spec: Delivery; done_when 4.
- [ ] The FEAT-CICD-001 catalog record's Status names this directive and its PR, and Last reviewed is current.
- [ ] 12-PR-ISSUE-TRACEABILITY lists this PR in FEAT-CICD-001's PR lineage.

## Task 3: gate and audit
Spec: done_when 3.
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` passes on the PR head with the PR body.
- [ ] Matched main and branch `docs_audit.py` runs report nothing new.
