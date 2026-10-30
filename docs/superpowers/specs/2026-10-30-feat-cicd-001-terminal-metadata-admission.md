---
feat_id: FEAT-CICD-001
req_ids: [REQ-GOV-001, REQ-REVIEW-001]
issues: []
canvases: []
site_source_notes: [SHARED-01]
done_when:
  - "The actual-Git historical SITE existence regression fails against the prior verifier and passes after the terminal precheck validates committed path, mode, type, object availability and bounded size without reading document content solely for existence; missing path, wrong mode and missing object controls still fail closed."
  - "The complete tests/scripts/test_doc_source_snapshot.py suite and the actual gate protected-input ownership and legitimate-CICD controls pass, retaining SHA1/SHA256 real producer/verifier/audit/gate, squash/fresh-clone, repeated-input charging, oversized-input and deadline refusals without changed limits or weakened assertions."
  - "The actual portable candidate verifier accepts the immutable landed timezone source/body at d4478433777283524377a61f142893807351b9b7 under the fixed five-second, 8388608-input-byte and 20000-entry limits, reporting exact identities, actual count, bytes and elapsed time; this diagnostic is distinguished from acceptance of the final CICD implementation head."
  - "After this approved successor is on MAIN, the final separate CICD implementation uses the existing FEAT-CICD-001/SHARED-01 note and ordinary declared-note route with a newly produced committed record; actual producer/verifier/audit and unchanged BASE gate validate final source/body and approved baseline/POLICY/SOURCE spec binding without bootstrap reuse or a manufactured terminal marker."
  - "Own catalog, PR traceability and implementation plan retain original specification #1462 and implementation #1470, all known review history and the new actual PR; the complete review ledger is reconciled before publication, normal required independent and authenticated current-head CODE/security reviews, green checks and resolved conversations precede merge, and full-default MAIN/proposed audits have no new findings."
status: draft
supersedes: docs/superpowers/specs/2026-10-13-feat-cicd-001-source-review-verifier.md
---

# Preserve verifier capacity with a metadata-only terminal existence check

## Authority, lineage and unchanged contract

This is a proposed narrow successor to the immutable approved verifier specification delivered through #1462 and implementation #1470 (merge 7e5cb49e). Preparation of this document is authorized; its draft status is not owner approval of the written amendment, implementation publication, or a new review allowance. Original policy #1461/#1464, bounded-review policy #1512, and generated-inventory #1538 are distinct histories, not unused verifier rounds. The original verifier plan records first CODE review at 87c5cad0 and a local correction at 98a04e13. The sole publisher recovered all six native #1470 summary-history nodes: CODE on 87c5cad started October16 00:52:08 UTC and completed01:15:31; CODE on 70255a6 started October18 21:01:44 UTC and completed21:09:50. Thus #1470 consumed two recorded external CODE heads; current SEC remained87c5cad. The total local aggregate remains unknown. Preserve both rounds and original spec #1462; any further allowance needs explicit owner reconciliation before review dispatch. A successor/new PR does not reset that history.

All original protocol requirements remain binding by reference to `2026-10-13-feat-cicd-001-source-review-verifier.md`: exact record format/canonicalization; complete current/baseline source and document identities; trusted policy and immutable approved-spec binding; normal source-note ownership; terminal precedence; Git-state, import-shadow and no-lazy-fetch protections; dirty-index/worktree refusal; deadline/byte/entry bounds; transactional output; truthful external-review and rollout labels; actual refusal/acceptance controls and post-merge close-out. Its Stage1/Stage2 bootstrap delivery is completed history, never an admission route for this repair. This amendment changes only the terminal existence implementation and explicitly declares the existing tooling-note pair for this new implementation. It does not relax any previous invariant or rewrite the original spec.

## Problem and evidence

Timezone runtime #1640 landed at d4478433777283524377a61f142893807351b9b7 after reviewed 3ee7faa4875e38d6ccdcef3f59499de359985af0. The historical-baseline route correctly requires a current-MAIN document read after squash. The verifier reaches 6490603 charged bytes before a required 2047379-byte policy-spec batch, totaling at least 8537982 bytes: 149374 over the fixed 8388608 ceiling. Refusal is correct; it is not an identity mismatch.

Separately, `Snapshot.terminal` reads the entire marker's historical SITE blob solely to test existence before the source-drift predicate already makes terminal acceptance impossible. That content read is unnecessary to the existence predicate. Required source/body and policy/spec roles remain necessary, including repeated roles over equal blobs.

## Alternatives and selected design

Raising the cap or dropping repeated-role charges would change the governing resource contract and is excluded. Skipping current-MAIN equality after squash would weaken identity and is excluded. Replacing only the existence content read with committed-object metadata preserves its predicate and the subsequent full body comparison; this is the selected bounded repair.

After marker validation, commit resolution and ancestry checks, inspect the historical SITE tree row. An absent path returns nonterminal. A non-100644 mode or non-blob type is unavailable. Resolve actual blob metadata through existing bounded Git plumbing; missing/unsupported objects are unavailable. Admit the actual object size against the remaining byte allowance before continuing, preserving oversized-object refusal. This existence check consumes and charges actual tree/metadata input, without issuing a content read solely for presence.

Keep ordinary source-drift evaluation unchanged. Only when that predicate permits terminal acceptance do the existing complete source and historical body reads execute; each reads/charges its complete role and normalizes the full document under the existing algorithm. No cache accounting, selected-spec batch, logical body role, source manifest, failure predicate, cap or deadline changes. Missing or unavailable required objects cannot establish proof.

Implementation source scope is `scripts/maintenance/doc_source_snapshot.py` and `tests/scripts/test_doc_source_snapshot.py`; existing integration tests run unchanged. Companion edits are the new bound plan, own catalog/traceability, explicitly declared own implementation-source note, sidecar and normal exact generated inventories if genuinely required. No gate/auditor algorithm, workflow, credential, permission, service configuration, application runtime or unrelated product prose change is admitted.

## Existing component and ordinary identity admission

`SHARED-01` is an existing SITE Chain ID for the shared API service/auth middleware. MAIN already contains the `(FEAT-CICD-001, SHARED-01)` implementation-source note for delivery tooling. Approved `2026-10-24-feat-cicd-001-registry-ci-envelope-pin.md` and `2026-10-25-feat-cicd-001-registry-measured-acceptance.md` explicitly use this same pair for CICD source-proof evidence. This successor declares that existing pair, not a new component or a reinterpretation of its application behavior.

The verifier protects complete API-delivery source evidence, including the existing `platform/api` watched root. Update only the existing CICD/SHARED-01 appended note to describe the verifier repair and tests, retain historical pin/live evidence accurately, and bind the final complete source hash. Do not replace another feature's note or claim API behavior, authentication, deployment, frontend or S/T/V/Te status changed. Preserve all original Chain/checklist/marker bytes and all foreign note rows.

The successor must be approved and merged independently before a new implementation plan selects it. Do not change the historical spec's content, add a selector to it, borrow another spec's declaration, reuse initial-bootstrap, fabricate a current-trunk marker or use the timezone feature's note. The real existing declared-note producer/verifier, immutable baseline/POLICY/SOURCE spec comparison, supersession check and unchanged BASE gate must admit the final implementation. Any refusal remains a hold; this text is not a gate exception.

## Validation and capacity

One shared five-second deadline, 8388608 admitted input bytes including all actual repeated content roles, and 20000 combined manifest entries remain exact. Renderer60seconds/512MiB, registry suite285seconds and all independent contracts remain exact. New network/auth/vendor calls, deployed jobs/services and incremental hosted allocation: zero. Normal required CI remains ordinary delivery work.

The isolated candidate has a meaningful original-code RED regression, 199 passing verifier tests and two passing ownership/admission gate controls. Its execution against the immutable landed timezone commit reports 7557718 bytes, 1482 entries and 1.021701 seconds with source identity 8a939f6ae390dc1ce828bd027d4b23cefc2a4f86de070931f4b9832e4f7ec5ad, policy identity 8009cb4dc0e87842d6dc52ad44bd38e576e40a1ec9adbcecdcb2a377efe0b8ef and body identity 9b168d8057faa2c15c077caff86fd2eb0635f27ead1456f98173e473a14be4df. This is candidate-executor evidence against committed landed source, not a new accepted CICD head, hosted review, final CI or deployment receipt. Revalidate the final integrated implementation and exact new note/record normally.

Risks are skipped historical-object checks, accidental content-role deduplication and incorrectly retained terminal status. Actual missing-path/wrong-mode/missing-object tests, repeated-spec charging, oversized input, source/body drift and genuine terminal squash/retirement controls must remain passing. No new independent-review cohort is consumed by this author preparation; normal required final review remains separately accounted.

## Normal delivery and close-out

Publish this specification alone through the normal draft/approval/spec review path; no implementation patch or ready implementation plan rides with it. Once approved, the successor names the original in `supersedes`. Preserve the original content and all #1462/#1470 evidence; any repository-required status-only retirement is performed only with an approved replacement and never rewrites its contract.

After actual spec merge, create a single narrow named `fix/feat-cicd-001-terminal-metadata` implementation branch/ready plan, preserve historical allowances, bind its real draft PR, and apply only the reviewed local candidate with normal source-note/record and exact gate checks. Four required independent process-file review seats and ordinary current-head external CODE/security review remain prerequisites, with lineage reconciled before dispatch; no approval is inferred for an exhausted budget.

Post-merge, verify actual MAIN from a fresh complete clone without the original feature commit under the unchanged limits. Record genuine local-tool acceptance and keep external-review/deployed status distinct. Retain the original separate DOC close-out and terminal stamp/sidecar-retirement obligations; source identity alone is not rollout completion. These post-merge obligations are not prematurely checked pre-merge done_when items.
