---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "`scripts/maintenance/doc_source_snapshot.py` binds the `trunk-closeout-pending` route to a constant `CLOSEOUT_SPEC` naming `docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md`; the constant `SPEC` still names `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md` and the `initial-bootstrap` route still binds it; `spec_binding`, every ceiling, debit, deadline, read and route predicate is unchanged."
  - "Real Git tests in `tests/scripts/test_doc_source_snapshot.py` show a valid DOC-only close-out (sha1 and sha256 object formats) produced and verified as identity-matched with a record naming the 2026-11-02 spec and its blob, and the same tests fail on main 5f16c96e with `bound approved spec has been superseded in trusted POLICY`."
  - "The close-out stays refused, each control asserting its exact reason, when the bound spec is missing, has the wrong FEAT, is not approved, or is superseded by a later approved FEAT-CICD-001 spec; a DOC-only (non-feature) branch that edits the bound spec is refused by route selection with `ordinary production requires its actual named feature branch/source`."
  - "A real initial-bootstrap control still records the 2026-10-13 spec, and the existing close-out, terminal-stamp and bootstrap controls pass with their assertions unchanged."
  - "`tests/scripts/test_doc_source_snapshot.py`, `tests/scripts/test_docs_audit.py` and `tests/scripts/test_spec_gate.py` pass on the implementation head with no failure that main does not also show in the same run order."
  - "The FEAT-CICD-001 record in `docs/product/02-FEATURE-CATALOG.md` and `docs/product/12-PR-ISSUE-TRACEABILITY.md` identifies the implementation PR; no other capability's row or record changes."
  - "Source identity (SHARED-01): on the implementation PR head the existing producer and verifier, run from the committed HEAD with its fixed ceilings, prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CICD-001 / SHARED-01 row of the Implementation-source notes table with the prefix source_identity_sha256=<current source hash> and nonempty prose describing this change and its tests while keeping the earlier accurate own content of that row; the sidecar is produced from the final committed SITE body and committed; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; the required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: approved
supersedes: null
---

# Bind the DOC-only close-out route to the current protocol spec (clarification)

## Problem

The approved spec `2026-11-02-feat-cicd-001-verifier-twelve-mib.md` (on main since 5f16c96e, #1690)
supersedes `2026-10-13-feat-cicd-001-source-review-verifier.md` and retains its protocol text. In
that retained text the DOC-only close-out route reads:

> **DOC trunk-closeout-pending:** exact protocol FEAT/spec above, empty IDs, ...

and the paragraph "above" (Initial-bootstrap) names "exact approved spec
`docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md`". The unchanged binding
check refuses a bound spec that an approved same-FEAT spec in trusted POLICY supersedes. Read
literally, the close-out binds a spec that the governing spec supersedes, so every DOC-only SITE
close-out is refused with `bound approved spec has been superseded in trusted POLICY`, and the
retained done_when item 8 of the 2026-11-02 spec ("actual DOC-only body-update and terminal
current-trunk stamp/sidecar-retirement tests pass") cannot hold.

Evidence: a trial merge of main 5f16c96e into stocks #1673 (36766791) was refused at 5,859,241
bytes in 0.9008 s, which is not a capacity failure. The real-Git controls in stocks #1691 reproduce
the refusal on main 5f16c96e for both object formats.

Approved specs are immutable, so the 2026-11-02 spec cannot be edited. This spec states the
binding explicitly. It does not supersede the 2026-11-02 spec: superseding it would make the
close-out route bind a superseded spec again.

## The clarification

Before (2026-11-02 spec, retained protocol text, unchanged on main):

> **Initial-bootstrap:** exact FEAT `FEAT-CICD-001`, exact approved spec
> `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md`, empty note IDs, ...
>
> **DOC trunk-closeout-pending:** exact protocol FEAT/spec above, empty IDs, ...

After (binding rule this spec adds; the only change is the DOC paragraph's binding, and every other
word of both paragraphs is unchanged):

> **Initial-bootstrap:** exact FEAT `FEAT-CICD-001`, exact approved spec
> `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md`, empty note IDs, ...
>
> **DOC trunk-closeout-pending:** exact FEAT `FEAT-CICD-001`, exact approved spec
> `docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md`, by this exact path only,
> empty IDs, ...

Every binding check still applies to the close-out route: approved status, matching FEAT, an
identical blob/mode/type in baseline, POLICY and SOURCE, refusal of a bound spec that a later
approved FEAT-CICD-001 spec supersedes, SOURCE equal to MAIN in full watched scope, and the
SITE-plus-sidecar-only delta.

On the DOC trunk-closeout-pending binding this spec governs over the 2026-11-02 spec's retained
L196; on everything else the 2026-11-02 spec governs unchanged.

## Non-goals

- No change to the initial-bootstrap route, its spec, or its allowlist.
- No "latest approved spec" resolution: the close-out binds one named path.
- No change to `spec_binding`, the ceilings, debits, deadline, reads, parser or graph.
- No change to the twelve-MiB ceiling work, which stays under the 2026-11-02 spec alone.
- No status change to any spec.

## Approaches considered

- **Additive clarification, no supersedes (chosen).** States the binding and keeps the 2026-11-02
  spec as the live protocol spec, so close-out binds a spec nothing supersedes.
- **A spec that supersedes the 2026-11-02 spec with amended text.** It would repeat 200 lines,
  rebind the twelve-MiB plan, and require the code to name the new path. Rejected as larger.
- **Bind the close-out to whichever approved spec is newest.** Turns an exact binding into a
  search. Rejected.

## Design

`CLOSEOUT_SPEC = "docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md"` beside
`SPEC`, and the `trunk-closeout-pending` branch of `eligibility()` binds it. Six lines. Capacity:
the spec adds about 8 KB to every verify's POLICY spec read (main self-check 8,288,664 → 8,296,827
bytes for this spec's first published text, against the 8,388,608 ceiling; this text is 412 bytes
longer); the implementation adds no read.

## Risks

- **Durability.** A later approved spec that supersedes the 2026-11-02 spec refuses close-outs
  again until its implementation moves `CLOSEOUT_SPEC`. Such a spec states that move in its own
  done_when. No tripwire test is added: one that fails whenever a repo spec supersedes
  `CLOSEOUT_SPEC` would turn the successor's docs-only spec PR red, and that PR cannot change code.
- **Admission.** The negatives in done_when items 3 and 4 keep every refusal causal.

## Source identity and close-out

The implementation evidence is Draft stocks #1691 (code blob 4e3aa25c, test blob fa41b4ae). A plan
binds one spec, so #1691's plan cannot bind this spec. The implementation lands as a separate re-cut
PR from main after this spec is approved, with the same code and test diff against main
(byte-identical blobs 4e3aa25c / fa41b4ae if it lands before the twelve-MiB implementation) and its
own plan bound to this spec. That PR updates only the FEAT-CICD-001 / SHARED-01 row and its sidecar
(done_when item 7). Post-merge main close-out of that row follows the existing protocol.
