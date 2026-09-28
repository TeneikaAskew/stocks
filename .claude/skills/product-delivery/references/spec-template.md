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
