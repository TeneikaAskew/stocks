---
feat_id: FEAT-CICD-001
spec: docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md
branch: fix/feat-cicd-001-closeout-spec-binding
pr: null
status: ready
---

# DOC-only close-out binds the current protocol spec: fix plan

> For agentic workers: use superpowers:executing-plans. Every task cites a spec section and the done_when item it advances.

**Defect.** Since main 5f16c96e (#1690) trusted POLICY holds the approved 2026-11-02 FEAT-CICD-001 spec, whose `supersedes` names the 2026-10-13 protocol spec. `scripts/maintenance/doc_source_snapshot.py` binds the `trunk-closeout-pending` route to the module constant `SPEC` (the 2026-10-13 spec), and `spec_binding` refuses a bound spec that an approved spec in POLICY supersedes. So every DOC-only SITE close-out is refused with "bound approved spec has been superseded in trusted POLICY". Measured: Solyra identity thread trial merge 36766791 (5f16c96e into stocks #1673's ca79bfb0), produce refused at 5,859,241 bytes in 0.9008 s, which is not a capacity failure. Main itself still verifies through the declared-note route.

**Spec:** `docs/superpowers/specs/2026-11-02-feat-cicd-001-verifier-twelve-mib.md`. Its retained done_when[7] (byte for byte the 2026-10-13 item 8) requires actual DOC-only body-update and terminal current-trunk stamp/sidecar-retirement tests to pass. The retained protocol text is literal about the spec: "**DOC trunk-closeout-pending:** exact protocol FEAT/spec above", where "above" is the Initial-bootstrap paragraph naming `docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md`. Read literally, that binds the close-out to a spec this same spec supersedes, which the unchanged binding refuses, so done_when[7] cannot hold. This fix reads "the exact protocol FEAT/spec" as the current approved protocol spec, the 2026-11-02 one. That is an interpretation, recorded for the owner's confirmation, not literal text. It is a separate PR because that spec's done_when[8] keeps the twelve-MiB change to the ceiling alone.

**Base:** main 5f16c96e. One branch, one PR, one author.

## Global constraints

- `SPEC` and the historical `initial-bootstrap` route are unchanged.
- `spec_binding` is unchanged: approved status, FEAT, an identical blob in baseline, POLICY and SOURCE, and refusal of a superseded bound spec all still apply to the close-out route.
- No ceiling, deadline, read, debit, parser or graph change. No network, database, provider or deployment call. Nothing under `platform/`, `lib/`, `gcp/` or `.github/workflows/` changes.

## Task 1: reproduce on main first
Spec: retained done_when[7].
- [ ] Add close-out controls in `tests/scripts/test_doc_source_snapshot.py` whose fixture main holds the real 2026-11-02 spec, and record that the valid close-out (sha1, sha256) is refused on 5f16c96e with "bound approved spec has been superseded in trusted POLICY".

## Task 2: bind the close-out route to the current protocol spec
Spec: retained done_when[7].
- [ ] Add `CLOSEOUT_SPEC` naming the 2026-11-02 spec and use it for `trunk-closeout-pending` only.
- [ ] The valid close-out produces and verifies, and its record names `CLOSEOUT_SPEC` and its blob.

## Task 3: refusal controls
Spec: retained done_when[0] and [7].
- [ ] The close-out stays refused, each with its own asserted reason, when the bound spec is missing, has the wrong FEAT, is not approved or is superseded by a later approved FEAT-CICD-001 spec; a branch that edits the bound spec is not a DOC-only close-out and is refused by route selection.
- [ ] The initial-bootstrap record still names the 2026-10-13 spec.
- [ ] Existing close-out, terminal stamp and bootstrap controls pass unchanged in their assertions.

## Task 4: suites
Spec: § Retained done_when items.
- [ ] `tests/scripts/test_doc_source_snapshot.py`, `tests/scripts/test_docs_audit.py` and `tests/scripts/test_spec_gate.py` pass on the head.

## Task 5: source identity and close
Spec: § Source identity and close-out; done_when[12].
- [ ] Update only the `(FEAT-CICD-001, SHARED-01)` row of the SITE Implementation-source notes table with the current `source_identity_sha256=<hash>; ` prefix and prose for this change, keeping its earlier accurate content.
- [ ] Produce the sidecar from the final committed SITE body, commit it, and verify from the committed HEAD.
- [ ] Registry blob, mode and type equal main's; matched main and branch `docs_audit.py` runs report nothing new.
- [ ] Catalog and PR-traceability records for this PR; `python3 scripts/gate/spec_gate.py --pr origin/main HEAD` with the PR body.
