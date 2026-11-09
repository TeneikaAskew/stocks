# Spec template

File: `docs/superpowers/specs/YYYY-MM-DD-<feat-id-lowercase>-<slug>.md`

```markdown
---
feat_id: FEAT-SIGNAL-001
req_ids: [REQ-SIGNAL-001, REQ-REL-001]
issues: [905, 928]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "tests/test_signals.py::test_live_replay_parity passes on the shared golden fixtures"
  - "SELECT count(*) FROM signal_alerts WHERE fire_id IS NULL returns 0 after backfill"
  - "02-FEATURE-CATALOG FEAT-SIGNAL-001 row shows Status and this PR"
status: draft
supersedes: null
---

# <Title>

## Problem
What is wrong or missing, with the evidence (issue, query, failing test, user report).

## Non-goals
What this spec deliberately does not do. Be specific; this is what stops scope creep in review.

## Approaches considered
The two or three options brainstorming produced, one line each, and why the chosen one won.

## Design
The chosen approach in enough detail that writing-plans can decompose it without asking questions.
Data contracts, file paths, interfaces, capacity numbers (volume, velocity, wall-clock per CLAUDE.md rule 0).

## Risks
What could regress and how done_when catches it.
```

Rules:
- `status` is `draft` until the user says approved, then `approved`. A replaced spec becomes `superseded` and the new one names it in `supersedes`.
- `feat_id` must exist in `docs/product/02-FEATURE-CATALOG.md`.
- `req_ids` is a non-empty list of IDs from the stocks `docs/product/01-PRODUCT-REQUIREMENTS.md`. The gate checks each one against that file's definitions where the repo holds it, and by shape (`REQ-XXX-000`) elsewhere.
- `done_when` is a non-empty list, and its items must each be checkable by a reviewer without asking the author. Each item is copied into the PR body as a `- [ ]` line that starts with the item's text.
- `supersedes` names the spec path this one replaces. The gate refuses a plan that points at a superseded spec.
- `issues` and `canvases` are lists and may be empty. Include only canvases that depict this area.

- The optional `site_source_notes: [CHARTS-02, JOURNAL-09]` field is used only for the approved branch-document-review protocol after its implementation is on main. IDs are sorted, unique existing SITE Chain element IDs. Declare them in the separately approved spec before implementation; an implementation PR cannot add or widen its own declaration. Omit the field when no SITE note row is needed. It authorizes only the capability's own declared rows in the appended implementation-source notes table, not existing SITE cells or other product documents.
- For that protocol, pre-merge `done_when` identifies exact eligible committed source/body identity with actual source-bound declared note changes and approved FEAT/spec binding, normal authenticated current-head external CODE review/required checks, and actual implementation tests of the close-out/retirement rules. Mandatory real post-merge main/staging close-out and sidecar retirement are separately tracked obligations in the specification Close-out section, PR and plan; they are never pre-merge `done_when` boxes and never ticked before the corresponding genuine evidence exists. A local identity record is not review authentication or deployment/data-freshness evidence. Tests must use actual producer/verifier/audit/BASE-gate commands, real squash/fresh clone, and refused as well as accepted controls: missing/unchanged notes, CODE changes masquerading as DOC close-out, bootstrap reuse, registry SOURCE/POLICY blob/mode/type inequality, premature retirement and genuine terminal current-trunk marker with no record. No synthetic successful proof dictionary can establish acceptance.
- Gated skill/template policy is a separate policy-only FEAT-CICD-001 CODE change after its own approved specification is on main. That completed policy CODE implementation and the separately approved verifier specification must both be on main before the verifier branch opens; policy-only done_when does not require future verifier tests. Initial implementation edits no SITE content and must pass the unchanged BASE gate and actual branch-versus-main audit with no new findings; it authorizes no waiver. Only subsequent capability branches can use the now-trusted SITE note allowance. Preserve broad watchers, verifier/init ownership, normal reviews/checks and the separate renderer/registry resource contracts.
