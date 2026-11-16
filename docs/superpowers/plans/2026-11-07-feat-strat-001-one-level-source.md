---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-07-feat-strat-001-one-level-source-r2.md
branch: feature/feat-strat-001-one-level-source
pr: 1753
status: ready
---

# One level source for the brief, the planner and every consumer implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

Builds on the FEAT-INSIGHT-001 trigger distance cap (PR #1746), merged into this branch ahead of main.
Spec revision 2 (#1750) supersedes the first spec with one rule change (Task 3). Every Open-question default in the spec is taken: inside bar and parent bar are both candidates (1),
the Design 2 thresholds (2), no trigger with reason atr_unavailable when ATR(14) is missing (3),
auto-refresh-top-n reports carry premarket_unavailable (4), fixtures rebuilt from real bars (5),
R-multiple targets and ATR stops are offsets, not levels (6).

## Task 1: One builder and the structural test
Spec: § Design 1 and 7. Advances done_when[0] and done_when[2].
- [ ] Write `tests/lib/test_session_levels_structure.py` (AST walk over lib/, gcp/, platform/, scripts/: no call to compute_previous_levels, compute_current_levels, identify_triggers, select_nearest_levels or reanchor_triggers outside lib/strat_levels.py, no level walk in lib/agents/trade_planner.py, no parent-bar walk outside lib/strat_levels.py)
- [ ] Write `tests/lib/test_session_levels_builder.py` session-date cases (AVGO 2026-11-06 before its daily row exists, prior bar 2U, stale_daily, premarket dated another day refused)
- [ ] Run both (expect FAIL on the pre-change code)
- [ ] Implement `build_session_levels`, `SessionLevels`, `SideLevels`, `find_parent_bar` in `lib/strat_levels.py`; make the old helpers private
- [ ] Run again (expect PASS)
- [ ] Commit: `feat(strat): build_session_levels is the one level builder`

## Task 2: Premarket print filter and pre_vwap
Spec: § Design 2, § Problem 12. Advances done_when[3].
- [ ] Commit the 2026-11-06 Alpha Vantage 1-minute extended-hours fixtures under `tests/fixtures/premarket_2026-11-06/`
- [ ] Write `tests/lib/test_premarket_print_filter.py` (filtered extremes, drop counts, real early moves kept, pre_vwap 100.00 case)
- [ ] Write caller tests in `tests/gcp/test_premarket_filter_callers.py` (both fetchers pass the last completed session's ATR(14); the fetch date's own OHLC does not move the filtered values)
- [ ] Run (expect FAIL), implement in `lib/indicators.calculate_premarket_context`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, run again (expect PASS)
- [ ] Commit: `feat(indicators): drop stale prior-close and isolated spike premarket prints`

## Task 3: One window, one side rule, one broken rule
Spec: § Design 1. Advances done_when[4], done_when[5], done_when[6].
- [ ] Write `tests/lib/test_session_levels_rules.py` (window and atr_unavailable, side-rule and touch fixtures, QQQ PDL 647.05 unbroken behind 649.62, PDL on the premarket cent is one rung named PDL)
- [ ] Run (expect FAIL), implement, run again (expect PASS)
- [ ] Commit: `feat(strat): one window, one side rule and one cents broken rule`
- [ ] Revision 2: write the no-premarket reference-cent fixture (prior close and reference 100, PDC 100, PWL 103, PYH 97 give long PWL 103 and short PYH 97, in the brief and the planner) and the with-premarket control (a level on the reference's cent stays on both lists); run (expect FAIL), drop reference-cent candidates when there is no snapshot, run again (expect PASS)
- [ ] Commit: `feat(strat): with no premarket, a level on the reference's cent is on neither side`

## Task 4: Brief and planner on the builder, parity on 2026-11-06
Spec: § Design 4 (brief, planner), § Expected effect. Advances done_when[1].
- [ ] Commit daily fixtures `tests/fixtures/strat_levels_2026-11-06_daily.json` (Alpha Vantage TIME_SERIES_DAILY, unadjusted)
- [ ] Write `tests/lib/test_brief_planner_parity.py` (fidelity on the pre-change identify_triggers rules, parity through the brief's playbook path and context_from_bundle then compute_persona_plans)
- [ ] Run (expect FAIL), switch `gcp/premarket_brief.py`, `lib/agents/summarizers.py`, `lib/agents/trade_planner.py`, `lib/agents/orchestrator.py`, run again (expect PASS)
- [ ] Commit: `feat(strat): brief and planner read one SessionLevels`

## Task 5: No synthesized numbers, one copy per reason, parent bar
Spec: § Design 5, 6, 7. Advances done_when[7], done_when[8], done_when[9].
- [ ] Write `tests/lib/test_no_synthesized_levels.py`, `tests/lib/test_orb_only_copy.py`, `tests/lib/test_parent_bar_naming.py`
- [ ] Run (expect FAIL), implement Optional entry_zone and stop, remove trigger_for and the legacy branch, `ORB_ONLY_COPY`, rename, run again (expect PASS)
- [ ] Commit: `feat(strat): no synthesized plan numbers, one orb_only copy table, parent bar`

## Task 6: level_basis snapshot and every consumer
Spec: § Design 3 and 4. Advances done_when[10] and done_when[4] (consumer paths).
- [ ] Add nullable `level_basis` JSONB to premarket_analysis and premarket_analysis_history in `gcp/schema.sql`
- [ ] Write `tests/gcp/test_level_basis.py` and `tests/lib/test_movement_statement_level_basis.py`
- [ ] Run (expect FAIL), switch the signal monitor, playbook resolver, movement statement and dashboard router, run again (expect PASS)
- [ ] Commit: `feat(strat): level_basis snapshot read by every live consumer`

## Task 7: Nothing pinned moves
Spec: § Non-goals. Advances done_when[11].
- [ ] Run the signal monitor replay fixtures and `_resolve_signal_status` tests before and after; the planner ATR stop and R-multiple tests on a side with a trigger; the strat_levels row writer test
- [ ] Run `tests/lib tests/agents tests/gcp tests/api`

## Task 8: History counts
Spec: § Expected effect, § Risks. Advances done_when[12].
- [ ] Replay IWM, SPY and QQQ from 2015-01-02 to 2026-11-06 through the production replay paths on origin/main and on this branch; put the per-side change counts and the last 20 sessions' picks in the PR body

## Task 9: close
Spec: § Source identity and close-out. Closes done_when[13] and done_when[14].
- [ ] Source identity sidecar and note rows for DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, INSIGHTS-08
- [ ] Update the 02-FEATURE-CATALOG FEAT-STRAT-001 and FEAT-INSIGHT-001 records (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
