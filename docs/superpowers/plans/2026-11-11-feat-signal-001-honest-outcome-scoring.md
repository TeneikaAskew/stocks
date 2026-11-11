---
feat_id: FEAT-SIGNAL-001
spec: docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md
branch: fix/feat-signal-001-honest-outcome-scoring
pr: null
status: ready
---

# Honest outcome scoring implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Score every voter signal and every brief playbook leg with an exit a trader could have taken, and serve that share as `pct_profitable`.
**Architecture:** One vectorised realized-outcome helper inside the producer's existing pass (rule `next-open-20m-1c-v1`), two nullable `historical_signals` columns, `/similar` aggregates on them in the same statistics query, and the resolver's realized P&L replaced by rule `cross-fill-t1-v1` with three new nullable columns per side. Touch timestamps, the signal set and the best-case columns stay as they are.
**Tech Stack:** Python 3.12, pandas, numpy, FastAPI, SQLAlchemy, pytest.
**Spec:** docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md

## Global Constraints

- Base: origin/main 7794e673 (spec merged in #1807).
- Test first: every new behaviour test fails on origin/main before the source change; no test is skipped, disabled or marked xfail.
- No backfill, no migration run, no deploy, no GCP access from this branch. Schema columns are `ADD COLUMN IF NOT EXISTS`, nullable, with no default.
- Eastern time only through `lib.eastern_time` (`utc_to_eastern_naive`, `session_schedule`); no literal zone strings in watched source.
- SITE: only the `(FEAT-SIGNAL-001, CHARTS-06)` implementation-source note row; every other SITE byte unchanged. Product docs: only the FEAT-SIGNAL-001 catalog record and its traceability section, plus `doc_inventory.py` re-renders.
- Research data stays in the project files; no production rows, exports or report text are committed.

## Task 1: Realized outcome on every voter signal
Spec: done_when[0], Design `lib/trading_analysis.py`.
Files: `lib/trading_analysis.py`; tests: `tests/lib/test_trading_analysis_realized_outcome.py`, `tests/scripts/test_run_historical_signals_strategy.py`.
- [x] Write synthetic naive-Eastern frames whose indicator columns make the voter fire on chosen bars; assert call, put, 09:30/15:34 bounds, premarket and 15:35 NULL, 13:00 half day, cross-session exit, tz-aware frame, unchanged best-case columns.
- [x] Add a production-caller regression through `_process_ticker` with UTC bars (10:00 ET scored from 10:01 ET, 05:00 ET NULL).
- [x] Run on origin/main (expect FAIL on the realized cases).
- [x] Add `realized_outcome` and `REALIZED_RULE`; set `realized_return_pct` and `realized_rule` in `generate_technical_signals`.
- [x] Run the files (expect PASS).

## Task 2: Feature ranking and run summary
Spec: done_when[1].
Files: `lib/trading_analysis.py`; tests: `tests/lib/test_trading_analysis_feature_ranking.py`.
- [x] Assert no `exit_`/`realized_`/`return_`/`best_` column or `duration_minutes` is ranked with `exit_rsi` a copy of the target; spy on the forest for the chronological 80/20 split; assert the summary wording.
- [x] Run on origin/main (expect FAIL).
- [x] Exclude outcome columns, fit on the first 80% by `entry_time`, print the out-of-sample score, move the summary print into `print_signal_summary` with the moved-in-favour and realized win-share line.
- [x] Run the file (expect PASS).

## Task 3: Columns, producer, API
Spec: done_when[2], done_when[4], Design `historical_signals` and the API.
Files: `gcp/schema.sql`, `gcp/historical_signals.py`, `scripts/run_historical_signals.py`, `platform/api/routers/signals.py`, `platform/api/schemas.py`, `platform/api/openapi.json`; tests: `tests/gcp/test_historical_signals.py`, `tests/api/test_platform_api.py`.
- [x] Assert the INSERT column list and the schema's nullable, default-free columns; assert `/similar` serves the realized win share, `realized_count` and `pct_moved_in_favor` in one query, and null with count 0 when no row has a realized value.
- [x] Run on origin/main (expect FAIL).
- [x] Add the columns, the mapping and the aggregates; regenerate `openapi.json` with `scripts/export_openapi.py`.
- [x] Run the files and `tests/api/test_openapi_snapshot.py` (expect PASS).

## Task 4: Resolver rule cross-fill-t1-v1
Spec: done_when[3], done_when[4], Design `gcp/premarket_playbook_resolver.py`.
Files: `gcp/premarket_playbook_resolver.py`, `gcp/schema.sql`; tests: `tests/gcp/test_premarket_playbook_resolver.py`.
- [x] Add the gap-through, later-gap, fill-bar target, T1-then-T2, stop/T1 same bar, fill-bar stop, stop-gap, T1-gap, skipped-target, not-triggered, invalid-stop and `resolve_one` binding tests; change the two T3/T2 expectations to T1 as a recorded change of rule.
- [x] Run on origin/main (expect FAIL).
- [x] Implement the rule, the three new fields per leg, the UPDATE and `RESOLVER_VERSION` `2026-11-11.v2`; keep every touch timestamp, MFE, MAE and reversal calculation.
- [x] Run the file (expect PASS).

## Task 5: Experiment script
Spec: done_when[5], Experiment.
Files: `scripts/analysis/honest_scoring_experiment.py`.
- [x] Port `verify_pct.py`, `voter_run.py`, `pct_profitable.py` and `resolver_exp.py`; the spec-rule rows come from the implemented `resolve_leg`, the origin/main rows from a clean origin/main checkout.
- [x] Run `table-a` and `table-b`; diff both against the spec's tables (expect identical).
- [x] Put both tables in the PR body.

## Task 6: Docs, source identity, publication
Spec: done_when[6], done_when[7], Source identity and close-out.
- [ ] Re-render the inventory blocks with `scripts/maintenance/doc_inventory.py` after the `gcp/schema.sql` line shifts.
- [ ] Update the FEAT-SIGNAL-001 catalog record and PR lineage.
- [ ] Commit; read the producer's source identity; update the `(FEAT-SIGNAL-001, CHARTS-06)` note row; commit; produce and commit the sidecar from committed HEAD; verify with the fixed ceilings.
- [ ] Run `docs_audit.py` on branch and origin/main (no new findings) and `spec_gate.py --pr origin/main` with the PR title and body.
- [ ] Run the full local suite; open one Draft PR; record its number here.
