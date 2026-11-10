---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-10-feat-cicd-001-declared-relation-total.md
branch: fix/feat-cicd-001-declared-relation-total
pr: PRNUM
status: ready
---

# Render the declared relation total with its breakdown (implementation plan)

**Goal:** `scripts/maintenance/doc_inventory.py` renders the declared relation total written directly
before a declared breakdown from the same three counts the breakdown renders, so a change to the
declared relation set passes both the gate's render check and `tests/scripts/test_check_generated_docs.py`.

**Spec:** `docs/superpowers/specs/2026-11-10-feat-cicd-001-declared-relation-total.md` (merged by #1768, approved by #1782).

**Requirement:** REQ-GOV-004 as amended by #1767.

## Task 1: the substitution
Spec: § Design. Advances done_when[0].
- [ ] Add `RELATION_TOTAL` beside `RELATION_BREAKDOWN`.
- [ ] Apply it inside the existing `if counts:` branch of `insert_blocks`, after the breakdown, with `t + m + v`.

## Task 2: tests
Spec: § Design, § Risks. Advances done_when[1].
- [ ] Both 05-a shapes rendered over an inventory with two more declared tables; record it failing on origin/main.
- [ ] A total not followed by a breakdown is unchanged; the restore path leaves a wrong total.

## Task 3: evidence
Spec: § Capacity and cost, § Delivery. Advances done_when[2], done_when[3], done_when[4].
- [ ] `--insert` over the committed 05-a, 05-c and 05-e changes no byte; the docs test file passes; the renderer measurement passes.
- [ ] The FEAT-STRAT-001 per-ticker parameters branch passes the PR-mode render check and the docs test with this change.
- [ ] Gate passes; catalog Last reviewed and 12-PR lineage updated; Codex review on the current head.
