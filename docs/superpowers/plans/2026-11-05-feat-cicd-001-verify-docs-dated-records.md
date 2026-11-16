---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-05-feat-cicd-001-verify-docs-dated-records.md
branch: fix/feat-cicd-001-verify-docs-dated-records
pr: 1728
status: ready
---

# Live-docs check: leave the two dated traceability records out (implementation plan)

**Goal:** `scripts/verify_docs_against_live.py` stops reading `docs/product/03-SITE-TRACEABILITY.md` and
`docs/product/12-PR-ISSUE-TRACEABILITY.md`, and nothing else about its scope or checks changes.

**Spec:** `docs/superpowers/specs/2026-11-05-feat-cicd-001-verify-docs-dated-records.md` (approved, merged by #1725 as 4fdcd53a).

**Base:** main after #1701 (eaa6080b), which fixed the real doc drift.

## Task 1: the exclusion
Spec: § Design. Advances done_when[0].
- [ ] Add `DATED_RECORD_DOCS` next to `LIVE_STATE_GLOBS`.
- [ ] `doc_paths()` drops those two root-relative paths after expanding the list and the globs; order otherwise unchanged.

## Task 2: tests
Spec: § Design. Advances done_when[1], done_when[2], done_when[3].
- [ ] `test_dated_records_are_not_live_state_docs` on a temporary tree.
- [ ] `test_repository_scope_keeps_every_other_product_doc` on the real root, with the scope expanded independently of `doc_paths()`.
- [ ] Record both failing on main's unchanged script (red), then the full suite passing on the head.

## Task 3: evidence
Spec: § Risks, § Validation and rollout. Advances done_when[4], done_when[5].
- [ ] One `--snapshot` run on the head, every remaining finding listed by file and check in the PR.
- [ ] Codex code review on the current head, green CI, no unresolved threads.
