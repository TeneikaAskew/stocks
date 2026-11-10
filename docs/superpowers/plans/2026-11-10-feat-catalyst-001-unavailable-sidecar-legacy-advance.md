---
feat_id: FEAT-CATALYST-001
spec: docs/superpowers/specs/2026-11-07-feat-catalyst-001-unavailable-sidecar-legacy-advance.md
branch: fix/feat-catalyst-001-unavailable-sidecar-legacy-advance
pr: 1769
status: ready
---

# Unavailable Sidecar Lets Legacy Fields Advance Implementation Plan

Goal: a still-unavailable `daily_path_v1` refresh may replace an unavailable (or status-less) prior row, so matured legacy sustain fields are saved; qualified evidence keeps every existing protection.
Architecture: one condition inside the existing conflict guard of `_upsert_reaction_frame`, its docstring, and the matching reason test in `_retention_receipts`. No schema, view, API, brief or lib/ change; no new query.
Tech stack: existing Python/SQLAlchemy/PostgreSQL/pytest.
Spec: docs/superpowers/specs/2026-11-07-feat-catalyst-001-unavailable-sidecar-legacy-advance.md.

## Global constraints

- No production, provider or Cloud SQL request. Integration tests run only against the local ephemeral PostgreSQL fixture.
- No historical recovery: a forced refresh of held-back rows needs the owner's separate authorization, as the spec's Rollout says.
- The clock guard, the NULL-erasure guard and every protection of `complete`, `maturing` and `not_applicable` sidecars stay as they are.

### Task 1: conflict-guard status condition and receipts (done_when 1, 2, 4)

Spec: § Design and § Done when; advances done_when[0,1,3].

Files: gcp/fetchers/compute_earnings_reactions.py (`_upsert_reaction_frame` status condition and docstring, `_retention_receipts` reason test); tests/integration/test_earnings_daily_path_persistence.py (helper `_unavailable_row`, `test_unavailable_sidecar_lets_matured_legacy_fields_advance`, `test_unavailable_sidecar_still_never_replaces_qualified_evidence[complete|maturing]`).

- [x] Add the two tests and the helper, built from the producer's own `compute_daily_path_v1` with no price evidence.
- [x] Confirm the legacy-advance test fails on main f366c481 (stored sustain fields stay NULL).
- [x] Admit an unavailable refresh only over an unavailable or status-less prior; keep the qualified statuses unchanged.
- [x] Skip the `unavailable_replacement:daily_path_v1` receipt for that same unqualified refresh only.
- [x] Run the integration file and the producer unit tests; all pass unmodified.

### Task 2: records, source identity and review (done_when 5, 6)

Spec: § Done when and § Rollout; advances done_when[4,5].

- [ ] Rebind the FEAT-CATALYST-001 / CATALYSTS-04 SITE row with the new source hash and prose for this change, keeping its earlier accurate content; produce and commit the sidecar from the final SITE body; verify with the fixed ceilings.
- [ ] Matched main and branch docs audit with no new finding; docs registry unchanged.
- [ ] Spec gate in PR mode, current-head Codex code review and all required CI checks green before the owner merges.
- [ ] After merge, the owner deploys the producer image (`./gcp/deploy.sh fetchers`); nothing is deployed or refreshed from this branch.
