---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-16-feat-cicd-001-verifier-sixteen-mib.md
branch: feature/feat-cicd-001-verifier-sixteen-mib
status: ready
pr: null
---

# SITE source verifier: sixteen-MiB aggregate input ceiling

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Goal:** `MAX_BYTES` in `scripts/maintenance/doc_source_snapshot.py` moves from 12,582,912 to 16,777,216 bytes, so a branch that edits `docs/product/03-SITE-TRACEABILITY.md` can prove its source identity again. Nothing about what is read, hashed, admitted or refused changes.

**Spec:** `docs/superpowers/specs/2026-11-16-feat-cicd-001-verifier-sixteen-mib.md` (approved, merged by #2006). It amends one number of `docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md` (#1690, implemented in #1699) without superseding it.

**Base:** main 97190ef4. One branch, one PR, one author.

## Global constraints

- Exactly one constant changes in `scripts/maintenance/doc_source_snapshot.py`; `MAX_FILE_BYTES`, the deadline, the entry ceiling and every read stay as they are.
- Exactly one assertion changes in `tests/scripts/test_doc_source_snapshot.py`: the pin of the approved ceiling. No other test, case or assertion changes.
- `.claude/skills/product-delivery/SKILL.md` changes only the verify command's `--max-input-bytes` value.
- Beyond those three lines the PR changes only this plan and the FEAT-CICD-001 catalog, PR lineage, SHARED-01 note row and sidecar.

## Task 1: the ceiling and its pin
Spec: § Exact change the implementation makes. Advances done_when 1 and 2.
- [ ] Set `MAX_BYTES = 16777216`; change the pin to `assert MAX_BYTES == 16777216`; record the pin failing against main's verifier and passing on the head; run `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` in full on the head.

## Task 2: measured need
Spec: § Experiment, § Capacity. Advances done_when 3.
- [ ] From the unchanged CLI on the head, record `counted_bytes` and `elapsed_seconds` for a main self-check and for the head; name #1968's head 56168a1d as a ref the old ceiling refused, with its result under the new one.

## Task 3: the skill's verify command
Spec: § Exact change the implementation makes. Advances done_when 4.
- [ ] `.claude/skills/product-delivery/SKILL.md` shows `--max-input-bytes 16777216`.

## Task 4: source identity, records and close
Spec: § Source identity and close-out. Advances done_when 5.
- [ ] Update the FEAT-CICD-001 catalog Status, the PR lineage, and the `(FEAT-CICD-001, SHARED-01)` SITE note row with the current source hash and prose for this change, keeping its earlier accurate content; produce and commit the sidecar; verify from the committed HEAD.
- [ ] Full-default `docs_audit.py` on main and on the head: nothing new on the head; `docs/DOC_REGISTRY.md` equal to main's.
- [ ] `python3 scripts/gate/spec_gate.py --pr` with the PR body; current-head review as CLAUDE.md section 2.5 counts it; every required check; zero unresolved threads.
