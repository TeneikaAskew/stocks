# Fetcher reader qualification

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
