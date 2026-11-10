---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-10-feat-cicd-001-architecture-export.md
branch: feature/feat-cicd-001-architecture-export
pr: 1773
status: ready
---

# On-demand architecture export implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

## Task 1: declared services in the inventory
Spec: § Design 1, "services". Advances done_when[2].
- [x] Write tests `tests/scripts/test_doc_inventory.py::test_deploy_services_by_literal_name_and_by_variable`, `::test_deploy_services_refuses_an_unassigned_variable`, `::test_real_repo_declares_three_services`
- [x] Implement `deploy_services` in `scripts/maintenance/doc_inventory.py`; `repo_inventory` carries `services` and `counts.services`
- [x] Run: `pytest tests/scripts/test_doc_inventory.py -k services` (PASS)

## Task 2: the exporter
Spec: § Design 1 and 2. Advances done_when[0], [1], [3], [4], [5], [6], [7], [8], [9].
- [x] Write `tests/scripts/test_architecture_export.py`: keys and declared counts, no second parser (AST), services drift, unresolved families, scheduler targets, byte-identical reruns, no file:line strings, provenance and dirty-tree refusal on a temporary clone, unread live counts, repo-only with no gcloud, synthetic drift
- [x] Implement `scripts/maintenance/architecture_export.py` (`build_export` pure; `provenance`; `main`)
- [x] Run: `pytest tests/scripts/test_architecture_export.py` (PASS)

## Task 3: the on-demand workflow
Spec: § Design 3. Advances done_when[10].
- [x] Write `tests/meta/test_architecture_export_workflow.py`
- [x] Add `.github/workflows/architecture-export.yml` (workflow_dispatch only, main only, read-only, artifact and job summary)
- [x] Run: `pytest tests/meta/test_architecture_export_workflow.py` (PASS)

## Task 4: canvas skill
Spec: § Design 4. Advances done_when[12].
- [x] Add the `source_export: architecture` path to `.claude/skills/refresh-canvas/SKILL.md`

## Task 5: close
Spec: § Done when. Closes done_when[11], [13], [14].
- [x] Measure capacity on the PR head and state it in the PR body
- [x] Re-render the inventory blocks (REQ-GOV-004)
- [x] Update the 02-FEATURE-CATALOG FEAT-CICD-001 record (Status, Last reviewed)
- [x] Add this PR to 12-PR-ISSUE-TRACEABILITY
- [x] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [x] `python3 scripts/gate/spec_gate.py --pr origin/main`
