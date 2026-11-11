---
feat_id: FEAT-DATA-001
spec: docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-fetcher-readers.md
branch: fix/feat-data-001-retire-ew-fetcher-readers
pr: null
status: ready
---

# Retire EW fetcher readers implementation plan

For agentic workers: use superpowers:executing-plans. One author owns this branch.

Goal: exclude both retired EW aliases before all eleven fetcher selections/aggregates.
Architecture: import the landed EARNINGS_NOT_RETIRED_SQL constant in the seven
admitted fetchers; add it inside existing WHERE clauses only. Preserve dates,
parameters, grouping, ordering, fallbacks and all supported/NULL/unknown sources.
Tech stack: Python, existing PostgreSQL query interfaces, hermetic SQLite query tests.
Spec: docs/superpowers/specs/2026-10-31-feat-data-001-retire-ew-fetcher-readers.md.
Base:87409f213f2bc910e23f92ba1fa82ea1fd378bfd; spec merged as #1685.

## Constraints and review focus

Retain historical rows, shared calendar, API contracts and other authors' work.
No schema, deployment, schedule, secret or vendor behavior changes. All source-proof
limits remain fixed. Null semantics, two exact aliases, mixed-source aggregation,
event-bound timing and hydrated volume ranking each need discriminating controls.
The market eligible query is expressly a consistency case: EW has no stock volume.
Five existing date debts may only change full-query identity one-for-one after
exact predicate-only source proof; no exemption, new debt or scanner weakening.
No code-review history is erased: #1685's spec reviews remain there. This fresh
implementation follows the existing two-round limit; no judgment review yet spent.

## Task 1: actual-reader predicates and tests
Spec: done_when items1–3; Ownership and collisions.
- [x] Replay the prepared test file on the actual base; record failing controls.
- [x] Apply only seven fetcher diffs and the actual-reader test file from preserved
  /workspace/ew-pf-uncommitted-preparation.patch, excluding its historical spike note.
- [x] Verify eleven predicate sites, both aliases removed and six retained controls.
- [x] Run14actual-reader cases and scoped fetcher suites; preserve event-specific
  timing ties, hydrated AMC and refresh LIMIT negative controls.
- [x] Prove removing only import/predicate/f-string additions restores base bytes.
- [x] Record exact node inventory, elapsed/RSS and row/query envelope. No production
  performance or PostgreSQL claim follows from the SQLite adapter.

## Task 2: generated records and truthful source evidence
Spec: done_when item4; Source identity and close-out.
- [ ] Reconcile exactly five existing timezone identities with unchanged debt/count
  and negative control; preserve all other baseline entries.
- [ ] Regenerate inventory blocks from committed source/current base via supported
  renderer, preserving unrelated generated/main changes and prose.
- [ ] Update only FEAT-DATA-001 catalog/lineage and its SHARED-07 note, preserving
  earlier own prose and every foreign SITE byte. Coordinate shared publication.
- [ ] Produce/verify actual committed source identity with fixed limits, compare
  registry blob/mode/type, and run matched current-main/branch audits.
- [ ] Run unchanged source-proof/audit tests, generated/timezone/meta checks, trusted
  BASE/PR-mode gates and ordinary hooks. Record failures rather than waive them.

## Task 3: Draft publication and later close-out
Spec: done_when item4; Ownership and collisions; post-merge obligations.
- [ ] Coordinate #1430/#1643 shared-reader notice through the authorized coordinator;
  do not message external agents. Recheck #1800/#1801/main before shared records push.
- [ ] Publish Draft only after local qualification, bind pr number in next normal
  commit, and retain unchecked current-head review/CI obligations until genuinely met.
- [ ] Normal current-head review/CI, resolved threads and coordinated merge follow.
- [ ] Fresh actual-main source verification and separate deployed-job image evidence
  follow merge; never mark plan done or remove sidecar before genuine close-out.

Qualification receipt:14 red on87409f21, then270 scoped tests passed65.71s, measured67.239s wall/439832KiB peak child RSS. Source changes restore exactly to base after removal of predicate/import additions. Shared fixture/helper and all seven original reader date expressions remain unchanged. Original scratch receipts are historical; these are fresh-base runs.
