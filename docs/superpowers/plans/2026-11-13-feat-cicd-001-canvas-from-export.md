---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-13-feat-cicd-001-canvas-from-export.md
branch: feature/feat-cicd-001-canvas-from-export
pr: 1860
status: ready
---

# Update the backend diagram from the architecture export: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: the script
Spec: § Design 1 and 2. Advances done_when[0] to [6].
- [x] Write `tests/scripts/test_canvas_from_export.py`: trigger rebuild and order, service-path detail, card removal and stale mentions, stub card, no stub for a named job, schedule-text flags (parametrized), stamp, idempotency, unnamed services and tables, undeclared rows ignored, bad export and bad page refused, only the data asset re-encoded, CLI write, report and `--check`
- [x] Implement `scripts/maintenance/canvas_from_export.py` (`Bundle.parse`/`render`, `update`, `report`, `main`)
- [x] Run: `pytest tests/scripts/test_canvas_from_export.py` (PASS, 22)

## Task 2: real page check
Spec: § Design 3. Advances done_when[7] and [8].
- [x] Run the script on the 2026-11-13 export (main f1868806) against the diagram as it stood before the hand edit; compare with the hand edit; `node --check` the updated script; run again and confirm no change
- [x] Measure wall-clock and peak memory on that page

## Task 3: the canvas skill
Spec: § Design 4. Advances done_when[9].
- [x] Update the architecture-export section of `.claude/skills/refresh-canvas/SKILL.md` to read the page, run the script with `--report`, show the report as the diff and publish the output only on approval

## Task 4: records and gate
Spec: § Close-out and done_when. Advances done_when[10] and [11].
- [x] FEAT-CICD-001 Status and Last reviewed in 02-FEATURE-CATALOG; this PR in 12-PR-ISSUE-TRACEABILITY
- [ ] SHARED-01 implementation-source note in 03-SITE-TRACEABILITY at the current source hash; produce and verify `docs/review-evidence/site-source-snapshot.json`
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main HEAD`; docs audit on the branch against origin/main
