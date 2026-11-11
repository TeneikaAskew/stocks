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

## Detailed local qualification receipt


Base87409f213f2bc910e23f92ba1fa82ea1fd378bfd, implementation plan
2026-11-11-feat-data-001-retire-ew-fetcher-readers.md, spec#1685.
No prior review is reset; original spec ledger remains on#1685.

`OMP_NUM_THREADS=1 python -m pytest -q --mode=mock tests/gcp/test_ew_fetcher_reader_retirement.py`
on the base reader code:14failed in0.45s. The same fourteen cases with predicates
pass within the scoped270-test run (65.71s pytest;67.239s process wall;
439832KiB peak child RSS). These are local measurements, not production forecasts.
The scoped run covers the changed fetchers' existing compute/history/market/news/
premarket/sec suites, shared source tests and the unchanged timezone guard.

Each actual reader executes its own SQL over the landed shared fixture in SQLite.
Test-local adapters handle PGinterval spellings and auxiliary table schema; none
replaces selection/aggregate logic. This is not a PostgreSQL/server-plan receipt.
All14nodes remain in tests/gcp/test_ew_fetcher_reader_retirement.py. Eleven-site
parametrization, event timing majority/tie, refresh LIMIT winner and hydrated AMC
cases separate predicate negative controls from retained-source behavior.
Six source controls (NULL,unknown,Earnings_Whispers,alphavantage,unusual_whales,yahoo)
remain. Both retired spellings disappear. Eligible backfill is expressly the one
consistency case because historical EW rows never had qualifying stock volume.

query-envelope.json records eight-row fixtures and actual query-layer calls:
one per single-reader invocation; refresh executes its existing two calendar
queries. No query/API/job is added and no cadence/timeout/memory setting changes.
Scheduled incremental cost adds no calls; no measured billing-savings claim.

The five old/new timezone identities are in timezone-identities.json. Exact source
reversal (remove only import/predicate/f-string additions) reproduces all seven
base files. Original baseline matches main; updated baseline changes only these
five identities. Debt stays313total/40SQL-date; no scanner/exemption changes.
An unrelated DATE(earnings_date) mutation remains an unbaselined violation.

Generated05-c writes/reads/blast blocks are restored by doc_inventory with the
committed source and frozen live_gcp_snapshot_2026-09-07.json, not live GCP.
Line references move; the shared predicate import brings lib/earnings_reactions.py
inside three job scopes, so their external-downstream counts fall by one. The
reader is not deleted. No prose outside the generated blocks changes.

Current-head CODE/CI and deployed-job qualification remain separate. Spec merge,
source identity and local tests do not certify deployed removal or data recovery.
No schema/data/secret/calendar/evaluator changes or production action occur here.
