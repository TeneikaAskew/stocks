---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-10-11-feat-cicd-001-review-guidelines.md
branch: feature/feat-cicd-001-review-guidelines
pr: null
status: ready
---

# Ask reviewers for the complete review in the first round: implementation plan

> For agentic workers: use superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: the review guidelines
Spec: § Design. Advances done_when[0].
- [ ] Append `## Review guidelines` to `AGENTS.md` with its three parts (the first review is the
      complete one, later rounds review the new commits, pre-existing problems are issues), citing
      CLAUDE.md Rule 3.7 for no silent fallbacks
- [ ] Read the section against each clause of done_when[0]

## Task 2: close
Spec: done_when[1] and [2].
- [ ] FEAT-CICD-001 record in `docs/product/02-FEATURE-CATALOG.md`: Status, Last reviewed; `docs/product/12-PR-ISSUE-TRACEABILITY.md`: this PR under FEAT-CICD-001
- [ ] `python3 scripts/maintenance/docs_audit.py` on the branch and on `origin/main`; `python3 scripts/gate/spec_gate.py --pr origin/main`
