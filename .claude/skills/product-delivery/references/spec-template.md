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

## Conditional MODEL-EWV-001 atomic registry transition

Registry SOURCE/POLICY blob, mode and type equality remains mandatory except for the following single transition, and only after a separately approved FEAT-CICD-001 verifier contract and its tested implementation have landed on trusted main. This policy text alone activates no exception. Before the verifier implementation branch opens, this policy-only implementation and the approved verifier specification must both be on main. Before a DATA implementation consumes it, an approved same-FEAT successor to docs/superpowers/specs/2026-11-18-feat-data-001-retire-ew-calendar-name.md must expressly declare this transition and preserve its other acceptance requirements.

Only the Class D row for docs/models/MODEL-EWV-001.md in docs/DOC_REGISTRY.md may replace its code-path cell gcp/fetchers/evaluate_ew_strikes.py with lib/eastern_time.py, gcp/fetchers/_av_realtime_collector.py, lib/earnings_reactions.py, tests/gcp/test_fetch_market_data_vendor_answers.py. Preserve its selector/class, every other registry byte, registry mode/type, retained watcher coverage and all foreign SITE bytes. The replacement binds historical documentation to preserved calendar functionality and regression evidence; it does not designate a new EW scorer or transfer runtime feature ownership.

The same candidate must remove the old module, move both runtime callers and all three collector mock targets to lib.eastern_time.session_schedule, preserve all 22 vendor cases byte-for-byte and pass the mapped calendar controls. An unchanged approved transition declaration must be on trusted main and the actual ancestral base. Neither a branch-edited declaration nor a source-only or registry-only half-transition qualifies. No other registry row or transition is admitted.

The canonical source record must bind actual base/source trees, both registry blob/mode/type identities, the old module blob, every replacement path/blob, approved spec identity and final SITE body. The verifier must independently validate both sides and retain deleted-path evidence, never treating candidate policy as trusted main. Normal squash/fresh-checkout verification must reconstruct that transition. Real producer/verifier, matched audit and trusted BASE entry-point controls must accept this exact complete transition and refuse unrelated edits, partial migrations, missing/nonregular paths, tampered records, unapproved declarations, foreign SITE changes and bootstrap or terminal impersonation. Existing negative controls remain for every undeclared registry inequality; synthetic success dictionaries do not establish acceptance.

Keep the five-second shared deadline, 16777216 combined bytes, 8388608 per-file bound, 20000 entries, charged reads, complete source hashing and separate renderer/registry budgets unchanged. Identity output remains implementation-source; rollout-pending. It is not authenticated review, terminal retirement, deployment or live-output proof. Historical records, ordinary audits, required checks, two-round reviews and separate release authorization remain intact.
