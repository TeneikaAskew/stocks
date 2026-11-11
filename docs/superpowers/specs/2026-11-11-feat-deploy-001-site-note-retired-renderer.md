---
feat_id: FEAT-DEPLOY-001
req_ids: [REQ-DEPLOY-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "Ratchet: tests/meta/test_model_registry_consistency.py's KNOWN_BACKLOG has no entry for 03-SITE-TRACEABILITY.md, and test_known_dead_path_backlog_only_shrinks passes for every docs/product document on the PR head; run with the PR head's test file against origin/main, the 03-SITE-TRACEABILITY.md case fails with 1 > 0."
  - "Dead path gone: on the PR head, scripts/maintenance/docs_audit.py's dead-link check reports no finding on docs/product/03-SITE-TRACEABILITY.md, and the FEAT-DEPLOY-001 / SHARED-01 row names the prompt renderer that #1788 deleted without a backticked path."
  - "Source identity (SHARED-01): on the PR head, the existing bounded producer and verifier (scripts/maintenance/doc_source_snapshot.py produce, then verify with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-DEPLOY-001 / SHARED-01 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty prose that describes only this PR's tests change, followed by ' Earlier: ' and the row's previous text, in which the one sentence that is false on the PR head (the Run 28 comment in the deleted renderer) is reworded in the past tense without the path and every other sentence is kept; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed; the registry docs/DOC_REGISTRY.md blob, mode and type equal main's."
  - "Matched audits: python3 scripts/maintenance/docs_audit.py --no-owning-job-check --json with one issues capture on the PR head and on main reports no finding on the head that main does not, and main's dead-link P2 on 03-SITE (backticked path -> scripts/maintenance/render_doc_prompts.py) is not on the head."
  - "Records: the FEAT-DEPLOY-001 record in docs/product/02-FEATURE-CATALOG.md shows a current Status and Last reviewed, and docs/product/12-PR-ISSUE-TRACEABILITY.md lists the PR under FEAT-DEPLOY-001; no other capability's row or record changes."
status: approved
supersedes: null
---

# Retire the 03-SITE dead path left by the deleted prompt renderer (FEAT-DEPLOY-001)

## Problem

stocks#1384 (FEAT-DEPLOY-001, merged as `ea630a3c`) wrote the FEAT-DEPLOY-001 / SHARED-01 row of the
Implementation-source notes table in `docs/product/03-SITE-TRACEABILITY.md`. One of its sentences is: "The Run 28
comment in `scripts/maintenance/render_doc_prompts.py` names that run's services in the past tense."

stocks#1788 (FEAT-CICD-001, the monthly architecture-doc refresh retirement under the spec merged in #1777)
deletes `scripts/maintenance/render_doc_prompts.py`. A feature branch may not edit another capability's note row
(`doc_source_snapshot.note_delta`: "undeclared/foreign implementation-source row changed"), so #1788 could not
reword the sentence. On #1788's head, measured 2026-11-11:

- `docs_audit.py` reports one finding main does not: `dead-link` P2 on 03-SITE,
  `backticked path -> scripts/maintenance/render_doc_prompts.py`, line 1304.
- `tests/meta/test_model_registry_consistency.py::test_known_dead_path_backlog_only_shrinks[03-SITE-TRACEABILITY.md]`
  failed with `assert 1 <= 0`.

The owner approved, on #1788 on 2026-11-11, that #1788 pins `KNOWN_BACKLOG['03-SITE-TRACEABILITY.md'] = 1` and
carries that one finding, and that the row is reworded afterwards. This spec is that rewording.

Why a feature change and not a documentation close-out: the test's second assert requires the pin to equal the
count (`now has 0 dead paths, fewer than the pinned 1`, executed on #1788's head with the citation removed), so
the commit that rewords the row must also remove the pin in `tests/meta/`. The `trunk-closeout-pending` route of
`doc_source_snapshot.py` admits only a change limited to the SITE document and its sidecar with no watched-path
change (`eligibility`, `doc_pending`), and `tests` is a watched path. Only a FEAT-DEPLOY-001 change whose
approved spec declares SHARED-01 can update that row.

## Non-goals

- No change to any other sentence of the FEAT-DEPLOY-001 / SHARED-01 row, to any other row, or to any SITE cell
  outside the Implementation-source notes table.
- No change to `scripts/`, `platform/`, `gcp/` or `lib/`, and no other test change.
- No marker stamp of 03-SITE and no sidecar retirement: those stay with the skill's close-out routes.
- No deployment: this changes a test and a document; no deployed service changes.

## Approaches considered

1. **This spec: a FEAT-DEPLOY-001 fix branch** that removes the pin and rewords the one sentence, with a new note
   prefix and sidecar. Chosen: it is the only route the gate and the producer admit for a tests change plus a
   foreign-to-everyone-else note row.
2. A documentation-only close-out PR (`trunk-closeout-pending`): refused, because it cannot change `tests/meta/`
   and the ratchet's equality assert would then fail on its head.
3. Leave the pin in place: rejected by the owner's decision on #1788, which made the pin temporary.

## Design

Branch `fix/feat-deploy-001-site-note-renderer`, opened after #1788 merges, one plan, one PR.

1. `tests/meta/test_model_registry_consistency.py`: delete the `"03-SITE-TRACEABILITY.md": 1` entry of
   `KNOWN_BACKLOG` and its comment. TDD order: run the test with the entry removed and the row unchanged (red,
   `1 <= 0`), then reword the row (green).
2. `docs/product/03-SITE-TRACEABILITY.md`, the FEAT-DEPLOY-001 / SHARED-01 row only: new prefix
   `source_identity_sha256=<hash from produce>; `, then prose naming this PR's one tests change, then ` Earlier: `
   and the previous text after its old prefix with the Run 28 sentence reworded, for example: "The Run 28 comment
   in the prompt renderer named that run's services in the past tense; the renderer was deleted with the monthly
   refresh (#1788)." No backticked path to a file that does not exist on the head; no `|`.
3. Commit, `produce` again, commit `docs/review-evidence/site-source-snapshot.json`, then `verify` with the fixed
   ceilings (`--max-seconds 5 --max-input-bytes 12582912 --max-entries 20000`).
4. Records: FEAT-DEPLOY-001 Status clause and Last reviewed in the catalog; the PR under FEAT-DEPLOY-001 in the
   traceability file.

Capacity: n/a, one test constant and documentation; no job, query, schedule or cloud call.

## Source identity and close-out

Pre-merge: done_when items 3 and 4. After the merge, tracked on the PR and never ticked before the evidence
exists: verify main's source and body identity in a fresh clone; set the plan `status: done` on a `docs/`
branch; the sidecar stays on main until a skill close-out route retires it.

## Risks

- Another lane changes watched paths on main before this merges: the sidecar becomes historical. Caught by
  done_when 3 (verify against current main); the remedy is merging main and producing the sidecar again.
- The reworded sentence introduces a new dead path or pointer: caught by done_when 1 and 2.
- The row prose claims something the diff does not do: external code review on the head, and done_when 3 limits
  the prose to this PR's tests change.
