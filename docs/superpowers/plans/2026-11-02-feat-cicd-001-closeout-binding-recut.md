---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-02-feat-cicd-001-closeout-spec-binding.md
branch: fix/feat-cicd-001-closeout-binding-recut
pr: null
status: ready
---

# DOC-only close-out binds the current protocol spec: re-cut plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Defect.** Since main 5f16c96e (#1690), trusted POLICY holds the approved 2026-11-02 FEAT-CICD-001 spec, whose `supersedes` names the 2026-10-13 protocol spec. `scripts/maintenance/doc_source_snapshot.py` binds the `trunk-closeout-pending` route to the module constant `SPEC` (the 2026-10-13 spec), and `spec_binding` refuses a bound spec that an approved spec in POLICY supersedes. So every DOC-only SITE close-out is refused with "bound approved spec has been superseded in trusted POLICY" (trial merge 36766791 into #1673: refused at 5,859,241 bytes in 0.9008 s, not a capacity failure).

**Spec:** `docs/superpowers/specs/2026-11-02-feat-cicd-001-closeout-spec-binding.md` (approved, on main since c3d31c2b, #1692). It states the binding explicitly: the historical initial-bootstrap route binds the 2026-10-13 spec, and the DOC trunk-closeout-pending route binds the 2026-11-02 spec by that exact path.

**Lineage.** This re-cut carries the code and test diff of Draft #1691 (code blob 4e3aa25c, test blob fa41b4ae), which cannot bind this spec because a plan binds one spec. The runtime and tests are byte-identical to #1691's head. Against #1691's reviewed head 9ed663c1 they differ only in the documented reason assertion of 41f0db97 (the branch-edit control asserts the route-selection reason). #1691's review history and findings stay with this lineage.

**Base:** main c3d31c2b. One branch, one PR, one author.

## Global constraints

- `SPEC` and the historical `initial-bootstrap` route are unchanged.
- `spec_binding` is unchanged: approved status, FEAT, an identical blob in baseline, POLICY and SOURCE, and refusal of a superseded bound spec all still apply to the close-out route.
- No ceiling, deadline, read, debit, parser or graph change. No network, database, provider or deployment call. Nothing under `platform/`, `lib/`, `gcp/` or `.github/workflows/` changes.

## Task 1: bind the close-out route
Spec: done_when 1 and 2.
- [ ] Add `CLOSEOUT_SPEC` naming the 2026-11-02 spec and use it for `trunk-closeout-pending` only; `SPEC` still names the 2026-10-13 spec.
- [ ] The valid close-out (sha1, sha256) produces and verifies, and its record names the 2026-11-02 spec and its blob; the same tests fail on main with "bound approved spec has been superseded in trusted POLICY".

## Task 2: refusal and bootstrap controls
Spec: done_when 3 and 4.
- [ ] The close-out stays refused, each control asserting its exact reason, when the bound spec is missing, has the wrong FEAT, is not approved or is superseded by a later approved FEAT-CICD-001 spec; a DOC-only (non-feature) branch that edits the bound spec is refused by route selection with "ordinary production requires its actual named feature branch/source".
- [ ] The initial-bootstrap record still names the 2026-10-13 spec; existing close-out, terminal stamp and bootstrap controls pass with their assertions unchanged.

## Task 3: suites
Spec: done_when 5.
- [ ] `tests/scripts/test_doc_source_snapshot.py`, `tests/scripts/test_docs_audit.py` and `tests/scripts/test_spec_gate.py` pass on the head with no failure that main does not also show in the same run order.

## Task 4: records, source identity and close
Spec: done_when 6 and 7.
- [ ] Catalog and PR-traceability records for this PR, naming #1691 as its evidence predecessor; no other capability's row or record changes.
- [ ] Update only the `(FEAT-CICD-001, SHARED-01)` row of the SITE Implementation-source notes table with the current `source_identity_sha256=<hash>; ` prefix and prose for this change, keeping its earlier accurate content.
- [ ] Produce the sidecar from the final committed SITE body, commit it, and verify from the committed HEAD bound to this spec at the actual merge base.
- [ ] Registry blob, mode and type equal main's; matched main and branch `docs_audit.py` runs report nothing new; `python3 scripts/gate/spec_gate.py --pr` with the PR body.
