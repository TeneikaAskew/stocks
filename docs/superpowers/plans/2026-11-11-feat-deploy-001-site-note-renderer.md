---
feat_id: FEAT-DEPLOY-001
spec: docs/superpowers/specs/2026-11-11-feat-deploy-001-site-note-retired-renderer.md
branch: fix/feat-deploy-001-site-note-renderer
pr: 1794
status: ready
---

# Retire the 03-SITE dead path left by the deleted prompt renderer: implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Goal:** remove the `KNOWN_BACKLOG['03-SITE-TRACEABILITY.md'] = 1` pin and reword the one sentence of the
FEAT-DEPLOY-001 / SHARED-01 note that cites the deleted `scripts/maintenance/render_doc_prompts.py`, in one PR.

**Architecture:** one test-constant change and one note row. The ratchet test drives it (red with the pin
removed, green once the citation is gone); the note row then takes a new source-identity prefix and the sidecar
is produced from the final committed SITE body.

**Tech stack:** pytest, `scripts/maintenance/doc_source_snapshot.py`, `scripts/maintenance/docs_audit.py`,
`scripts/gate/spec_gate.py`.

**Spec:** docs/superpowers/specs/2026-11-11-feat-deploy-001-site-note-retired-renderer.md

**Preconditions:** #1788 (deletes the renderer, adds the pin) and #1791 (this spec) are on main; the branch is cut
from main `dded588d`.

## Global Constraints

- Only these files change: `tests/meta/test_model_registry_consistency.py`, `docs/product/03-SITE-TRACEABILITY.md`
  (the FEAT-DEPLOY-001 / SHARED-01 row only), `docs/review-evidence/site-source-snapshot.json`,
  `docs/product/02-FEATURE-CATALOG.md` (FEAT-DEPLOY-001 record only), `docs/product/12-PR-ISSUE-TRACEABILITY.md`
  (FEAT-DEPLOY-001 lineage only) and this plan.
- The FEAT-DEPLOY-001 / SHARED-07 row (#1789) and every other SITE byte stay unchanged.
- The reworded sentence names the renderer without a backticked path and without `|`; no em or en dash anywhere
  this plan writes.
- Verifier ceilings, verbatim: `--max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`.
- No gate file changes (`scripts/gate/`, `.githooks/pre-commit`, the two gate workflows, their suites).

## Review Focus

- A reworded sentence that still contains a backticked path to a file absent on the head: done_when 1 and 2 fail.
- The new prose describing anything beyond this PR's one tests change: done_when 3 limits it; review checks it.
- A changed byte in the SHARED-07 row or anywhere else in the SITE body: `note_delta` refuses a foreign row change.
- Main moving before merge (another SITE note lands): the sidecar goes historical; merge main and produce again.
- The equality half of the ratchet: removing the pin while a citation remains fails `1 <= 0`; leaving the pin after
  the citation is gone fails "fewer than the pinned 1". Both directions are exercised in Tasks 1 and 2.

## Task 1: remove the pin, red first
Spec: § Design 1. Advances done_when 1.
- [ ] Delete the `"03-SITE-TRACEABILITY.md": 1` entry of `KNOWN_BACKLOG` and the six comment lines above it, leaving
      `"14-WORK-BREAKDOWN.md": 2` as the only entry.
- [ ] Run `python3 -m pytest "tests/meta/test_model_registry_consistency.py::test_known_dead_path_backlog_only_shrinks" -q`.
      Expected: FAIL for `03-SITE-TRACEABILITY.md` with `assert 1 <= 0` (the row still cites the path). At this
      point 03-SITE on disk is main's byte for byte, so this run is also done_when 1's check of this test file
      against origin/main. Record the output; nothing is committed in this task.

## Task 2: reword the sentence, green
Spec: § Design 2. Advances done_when 1 and 2.
- [ ] In the FEAT-DEPLOY-001 / SHARED-01 row, replace exactly
      "The Run 28 comment in `scripts/maintenance/render_doc_prompts.py` names that run's services in the past tense."
      with
      "The Run 28 comment in the prompt renderer named that run's services in the past tense; the renderer was deleted with the monthly refresh (#1788)."
      Change nothing else yet (the prefix moves in Task 3).
- [ ] Run the Task 1 test. Expected: PASS for every document.
- [ ] Run the dead-link check on 03-SITE (`docs_audit.check_dead_links` with `TOP_LEVEL_DIRS` filled from the tree,
      or the full `docs_audit.py --no-owning-job-check --json` filtered to `dead-link` on 03-SITE). Expected: no finding.
- [ ] Commit both files: `fix(site): retire the 03-SITE citation of the deleted prompt renderer`.

## Task 3: note prefix and sidecar
Spec: § Design 2 and 3. Advances done_when 3.
- [ ] `python3 scripts/maintenance/doc_source_snapshot.py produce --policy-ref origin/main --source-ref HEAD --output docs/review-evidence/site-source-snapshot.json`;
      take its `source_identity_sha256`. Do not commit this sidecar yet (`git checkout -- docs/review-evidence/site-source-snapshot.json`).
- [ ] In the same row, the cell becomes:
      `source_identity_sha256=<hash>; ` +
      "`tests/meta/test_model_registry_consistency.py` drops the `03-SITE-TRACEABILITY.md` entry that #1788 added to `KNOWN_BACKLOG`, so `test_known_dead_path_backlog_only_shrinks` holds this document at zero dead paths." +
      " Earlier: " + the cell's previous text after its old prefix `source_identity_sha256=a1a524e2…; `, byte for byte,
      including Task 2's reworded sentence. Commit: `docs(site): bind the FEAT-DEPLOY-001 note to the pin removal`.
- [ ] `produce` again with the same arguments; commit the sidecar:
      `docs(site): commit the FEAT-DEPLOY-001 source identity sidecar`.
- [ ] `verify --policy-ref origin/main --source-ref HEAD --record docs/review-evidence/site-source-snapshot.json --max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`.
      Expected: exit 0, `identity-matched`, `eligible_route: declared-note`, FEAT-DEPLOY-001, SHARED-01, baseline
      current main, `source_identity_sha256` equal to the prefix. `git diff --exit-code origin/main -- docs/DOC_REGISTRY.md` exits 0.
      `git diff origin/main -- docs/product/03-SITE-TRACEABILITY.md` changes the SHARED-01 row only.

## Task 4: close
Spec: § Done when. Advances done_when 4 and 5.
- [ ] Catalog: in the FEAT-DEPLOY-001 record, add the clause "03-SITE citation of the deleted prompt renderer
      retired (#<this PR>)" to Status and set Last reviewed to the head commit's date; traceability: this PR under
      FEAT-DEPLOY-001's lineage. Touch no other record or row. Commit.
- [ ] `docs_audit.py --issues-snapshot <capture under a day old> --no-owning-job-check --json` on the head and on main
      with one capture, diffed by (check, document, severity, detail): `NEW 0`, and main's
      `('dead-link', 'docs/product/03-SITE-TRACEABILITY.md', 'P2', 'backticked path -> scripts/maintenance/render_doc_prompts.py')`
      is in `GONE`.
- [ ] `python3 -m pytest tests/meta -q` passes. `python3 scripts/gate/spec_gate.py --pr origin/main` in ready mode
      passes; tick every done_when box in the PR body with its evidence.
