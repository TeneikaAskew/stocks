---
feat_id: FEAT-CATALYST-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-REL-001]
issues: []
site_source_notes: [CATALYSTS-04]
canvases: []
done_when:
  - "tests/integration/test_earnings_daily_path_persistence.py::test_unavailable_sidecar_lets_matured_legacy_fields_advance: on real PostgreSQL through the actual `_upsert_reaction_frame`, a row first stored with the producer's own unavailable `daily_path_v1` (from `compute_daily_path_v1` with no price evidence, observation 2026-01-06T21:01Z) and NULL `sustain_5d_pct`, `direction_consistent_5d` and `is_reversal_5d` is replaced by a refresh whose sidecar is still unavailable (observation 2026-01-21T21:01Z) and whose legacy sustain fields are non-NULL: the upsert returns 1, the stored legacy fields and sidecar equal the refresh, and a `persistence` receipt reads `upserted`. In the same test a later unavailable refresh that would NULL a stored legacy value, and one with an earlier observation clock, each return 0 and leave the row byte-identical; a later qualified (`complete`) sidecar still replaces the unavailable one."
  - "tests/integration/test_earnings_daily_path_persistence.py::test_unavailable_sidecar_still_never_replaces_qualified_evidence[complete|maturing]: with a stored `complete` or `maturing` sidecar, an unavailable refresh with newer legacy values returns 0, leaves the row byte-identical and emits the `unavailable_replacement:daily_path_v1` receipt."
  - "The new test in item 1 fails on main f366c481 (the stored sustain fields stay NULL) and passes on the PR head; every existing test in tests/integration/test_earnings_daily_path_persistence.py and tests/gcp/test_compute_earnings_reactions.py passes unmodified."
  - "git diff against the merge base changes runtime code only in gcp/fetchers/compute_earnings_reactions.py: the status condition inside `_upsert_reaction_frame`'s conflict guard, that function's docstring, and the matching `unavailable_replacement:daily_path_v1` reason test in `_retention_receipts`. The only test file changed is tests/integration/test_earnings_daily_path_persistence.py (two new tests and one helper). No schema, view, API, brief or lib/ change."
  - "Own narrow plan and product records, the no-new documentation audit, current-head required Codex code review and CI pass through the normal gates."
  - "Source identity (CATALYSTS-04): on the implementation PR head, the existing bounded producer and verifier (`scripts/maintenance/doc_source_snapshot.py produce`, then `verify` with the fixed ceilings, run from the committed HEAD) prove committed source and SITE body identity bound to this approved spec at the actual merge base, where its blob equals the one on current main; the plan binds this spec; the only SITE change is the FEAT-CATALYST-001 / CATALYSTS-04 row of the Implementation-source notes table, updated with the prefix source_identity_sha256=<current source hash> and nonempty implementation and test prose that describes this PR's conflict-guard change and its tests and keeps the earlier accurate own content of that row; every other SITE byte is unchanged; the sidecar is produced from the final committed SITE body and committed; the matched main and branch `scripts/maintenance/docs_audit.py` runs report no finding that main does not; `tests/scripts/test_doc_source_snapshot.py` and `tests/scripts/test_docs_audit.py` pass unchanged; the registry `docs/DOC_REGISTRY.md` blob, mode and type equal main's; required current-head checks pass before merge under the repository's existing review rules, which this spec does not extend."
status: draft
supersedes: null
---

# Earnings reactions: let legacy fields advance past an unavailable sidecar

## Problem

stocks#1608 (merged 2026-11-07 as f366c481) added the `daily_path_v1` sidecar to `earnings_reactions` and a
conflict guard in `_upsert_reaction_frame` (`gcp/fetchers/compute_earnings_reactions.py`) that refuses any
refresh whose incoming sidecar status is not `complete`, `maturing` or `not_applicable`. The guard decides the
whole row, legacy columns included.

Codex code review on #1608 (thread r4503329917, P2, verified and deferred to this follow-up under the owner's
decision D1) found the consequence. When an event is first stored before D+5 with an unavailable sidecar (for
example no recognised price-basis evidence, `missing_source_identity`), its `sustain_5d_pct`,
`direction_consistent_5d` and `is_reversal_5d` are NULL. If the evidence stays unavailable, every later refresh
is refused, so those legacy outcomes are never saved even after they mature. Verified locally on f366c481: the
item 1 test fails with the stored sustain still NULL after the January 21 refresh.

Impact is bounded: nothing stored is lost, and the guard is evaluated on every refresh, so held-back rows are
written on the first producer run after the fix is deployed.

## Non-goals

- No change to what counts as qualified evidence, to the prefix, clock, identity or per-metric guards, or to
  the rule that no legacy value goes back to NULL.
- No schema, view, API, brief, `lib/` or frontend change. No backfill job; the normal producer run is enough.
- No change to how `compute_daily_path_v1` builds an unavailable sidecar.

## Approaches considered

1. Admit `unavailable` over a prior that is itself unqualified (`unavailable` or no status). Chosen: the prior
   holds no evidence to protect, every other guard still applies, and it is one SQL condition.
2. Split the guard so legacy columns and the sidecar are updated independently. Rejected: larger change to a
   just-reviewed writer, two updates per row, and a new partial-row state to reason about.
3. Keep the unavailable prior sidecar but write legacy columns. Rejected: needs per-column CASE expressions and
   leaves a stale sidecar clock behind newer legacy values.

## Design

In `_upsert_reaction_frame`, the status clause of `acceptable_payload` becomes:

- incoming status in (`complete`, `maturing`, `not_applicable`), as today; or
- incoming status `unavailable` and the prior status NULL or `unavailable`.

The remaining clauses are unchanged and still apply to this new case: a qualified prior (`complete`,
`not_applicable`) is never replaced by a weaker status; a `maturing` prior is never replaced by `unavailable`;
event, basis and version identity must match where the prior has them; `observation_ts` and `observed_steps`
never regress; an available per-metric result never becomes unavailable; available native classifier inputs
are never dropped; and the per-column rule keeps every non-NULL legacy value from going back to NULL.

`_retention_receipts` mirrors the condition so a refused unavailable-over-unavailable refresh is not reported as
`unavailable_replacement:daily_path_v1` (it is reported by whichever other guard refused it). The docstring is
updated to say that an unavailable sidecar may replace an unavailable one.

Capacity: unchanged. The upsert is still one `INSERT ... ON CONFLICT DO UPDATE` per chunk of at most 250 rows,
with at most one batched read of refused keys; the new clause adds no query or round trip. The producer's
volume, velocity, wall-clock and cost are as on main.

Rollout: none beyond the existing producer. After merge the change takes effect when the operator redeploys the
fetcher jobs (`./gcp/deploy.sh fetchers`), and held-back rows fill on the next scheduled run.

## Risks

- Overwriting evidence: only an unqualified prior can be replaced by `unavailable`; item 2 proves `complete` and
  `maturing` priors are retained with the existing receipt.
- Legacy regression: item 1 proves a NULL-ing refresh and a clock-regressing refresh are still refused.
- Breaking the existing contract: item 3 keeps every existing persistence and producer test unmodified.

## Ownership and dependencies

- Follows stocks#1608 (merged). No open PR is known to change `_upsert_reaction_frame`.
- The `(FEAT-CATALYST-001, CATALYSTS-04)` SITE note row is shared by name with other FEAT-CATALYST-001
  implementations; whichever PR lands later composes the cell from the row then on main, keeps earlier accurate
  content and recomputes the source hash.

## Source identity and close-out

Declaration: only the `(FEAT-CATALYST-001, CATALYSTS-04)` row in the existing Implementation-source notes table
of `docs/product/03-SITE-TRACEABILITY.md` may describe this implementation and its local tests. Every other SITE
byte stays unchanged. The note describes backend source and local tests only and claims no deployment.

Pre-merge (item 6), on the implementation branch: the plan binds this spec; this spec's blob is the same in the
merge base, current main and the branch head with `status: approved`; the note carries the current
`source_identity_sha256`; the sidecar is produced from the final committed body, committed and verified, and
redone after any later merge of main.

Post-merge obligations, tracked here, in the plan and in the PR, never as pre-merge `done_when` boxes:

- Verify the actual main source and body identity in a fresh clone after the squash.
- Retire the sidecar only as the product-delivery skill prescribes.
- Set the plan to `status: done` on a `docs/` branch after the merge.

## Status

Draft. Becomes `approved` only on the owner's word.
