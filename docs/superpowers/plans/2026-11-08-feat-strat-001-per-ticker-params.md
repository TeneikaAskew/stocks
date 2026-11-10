---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-08-feat-strat-001-per-ticker-params.md
branch: feature/feat-strat-001-per-ticker-params
pr: 1766
status: ready
---

# Per-ticker calibrated level and plan parameters implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

Builds on the FEAT-STRAT-001 one-level-source implementation (PR #1753, head 8b027b6e), which this
branch starts from. Every Open-question default in the spec is taken: the Design 2 policy quantiles
(1), atr_14 as the day-one basis (2), break-derived parameters pooled across sides (3),
reach-probability targets (4), non-universe premarket values written and labelled unfiltered (5),
insufficient_history with no stand-in (6), nightly cadence (7).

## Task 1: ATR(5) next to ATR(14)
Spec: § Design 4. Advances done_when[5].
- [ ] Write `tests/gcp/test_atr5_column.py` (the nightly row builder writes atr_5 equal to calculate_atr(..., 5) on the committed daily fixture; the backfill gap list carries atr_5; the loader maps atr_5 to ATR5)
- [ ] Run (expect FAIL on 8b027b6e)
- [ ] Add `market_data_daily.atr_5` to `gcp/schema.sql`, 5 to `IndicatorConfig.atr_extra_periods`, ATR5 to `DAILY_INDICATOR_TO_SQL_COLUMN`, atr_5 to `lib/data_loader.py`
- [ ] Run again (expect PASS)
- [ ] Commit: `feat(indicators): store ATR(5) beside ATR(14)`

## Task 2: Parameter tables and the one loader
Spec: § Design 1 and 3. Advances done_when[0].
- [ ] Write `tests/lib/test_level_params_loader.py` against the schema.sql DDL and policy seed in SQLite (two versions, one query for ten tickers, dropped table raises, unknown ticker, partial calibration failure across a basis change, basis transition)
- [ ] Run (expect FAIL)
- [ ] Add `level_param_policy` and `ticker_level_params` with the Design 2 policy seed to `gcp/schema.sql`; implement `LevelParams`, `LevelParamUnavailable`, `LevelParamsUnavailable` and `load_level_params` in `lib/strat_levels.py`
- [ ] Run again (expect PASS)
- [ ] Commit: `feat(strat): per-ticker level parameter tables and loader`

## Task 3: No numbers in the level and plan code
Spec: § Problem (inventory), § Design 2, 3 and 6. Advances done_when[1], done_when[8].
- [ ] Write `tests/lib/test_level_params_structure.py` (AST) and `tests/lib/test_level_params_behaviour.py` (one row change moves a side to orb_only; insufficient_history and basis-mismatch outcomes; plan fields null on non-ok persona keys; no published price from a non-ok parameter)
- [ ] Run (expect FAIL)
- [ ] `build_session_levels` takes LevelParams; per-side windows; cluster tolerance in ATR; `calculate_premarket_context` takes stale_print_atr and spike_atr; `compute_persona_plans` reads persona keys; remove the constants, `compute_room_to_run` and `safe_atr`
- [ ] Move every existing caller and test fixture onto LevelParams
- [ ] Run again (expect PASS)
- [ ] Commit: `feat(strat): level and plan code reads per-ticker parameters`

## Task 4: Copy states the ticker's own values
Spec: § Design 6, § Problem items 5, 13 and 14. Advances done_when[12].
- [ ] Write `tests/lib/test_level_params_copy.py` (window copy states coverage and exceedance shares; no '3x ATR', '3 ATR', '8% of price' or '0.5 x ATR' literal; entry-zone rationale states the reach share)
- [ ] Run (expect FAIL), implement in `ORB_ONLY_COPY`, `lib/agents/schema.py`, the planner rationale, run again (expect PASS)
- [ ] Commit: `feat(strat): copy states the ticker's own window and coverage`

## Task 5: Calibration methods
Spec: § Design 2. Advances done_when[2].
- [ ] Write `tests/lib/test_level_calibration.py` (known answers per method, minimum-sample edges, fills, worst-case bar ordering, no_positive_target, no look-ahead)
- [ ] Run (expect FAIL), implement `lib/level_calibration.py`, run again (expect PASS)
- [ ] Commit: `feat(strat): calibration methods for the level parameters`

## Task 6: Calibration job
Spec: § Design 5 and 7. Advances done_when[7].
- [ ] Write `tests/gcp/test_calibrate_level_params.py` (N tickers cost N daily reads, N one-minute reads, N write batches; rerun converges; a failed read skips the ticker and the run exits non-zero; history mode reads strictly before each session)
- [ ] Run (expect FAIL), implement `gcp/calibrate_level_params.py` and `load_calibration_universe`, run again (expect PASS)
- [ ] Commit: `feat(strat): calibrate-level-params job module`

## Task 7: One-minute bars for the calibration universe
Spec: § Design 5. Advances done_when[6].
- [ ] Write `tests/gcp/test_av_intraday_universe.py` (stub watchlist; resolved list; nightly path requests extended hours)
- [ ] Run (expect FAIL), resolve --symbol=ALL at run time in `gcp/fetchers/fetch_alphavantage_intraday.py`, run again (expect PASS)
- [ ] Commit: `feat(fetchers): one-minute bars for every calibrated ticker`

## Task 8: Premarket thresholds in both fetchers
Spec: § Design 6, § Design 8. Advances done_when[4] (offline part).
- [ ] Write `tests/gcp/test_premarket_filter_params.py` (one params read per run; pre_filter_status and pre_filter_params written; params_unavailable gives NULL counts; the builder refuses an unfiltered snapshot)
- [ ] Run (expect FAIL), implement in both fetchers and `gcp/schema.sql` (pre_filter_status, pre_filter_params), run again (expect PASS)
- [ ] Commit: `feat(fetchers): premarket filter reads the ticker's calibrated thresholds`

## Task 9: Missing table is loud, level_basis records the parameters, replays read their session
Spec: § Design 3 and 8. Advances done_when[9], done_when[10], done_when[11].
- [ ] Write `tests/gcp/test_level_params_consumers.py` (brief exits non-zero and writes no row; insight run failed with level_params_unavailable; signal monitor skips the level refresh with the reason; level_basis carries params, policy version, atr_14, atr_5, atr_basis and the new rule_version; from_basis never reads the table; two versions and a replayed session get the first version)
- [ ] Run (expect FAIL), wire `load_level_params` into the brief, the insight pipeline, the planner, the signal monitor, the playbook resolver and the movement statement, run again (expect PASS)
- [ ] Commit: `feat(strat): every consumer reads the parameters in force on its session`

## Task 10: Nothing pinned moves
Spec: § Non-goals. Advances done_when[14].
- [ ] Run the signal-monitor fire tests, `_resolve_signal_status` tests, persona sizing, catalyst damper and FTFC gate tests, and the side, broken and cents rule tests on 8b027b6e and on this head
- [ ] Run `tests/lib tests/agents tests/gcp tests/api`, then the full suite

## Task 11: Production evidence
Spec: § Expected effect, § Source identity and close-out. Advances done_when[3], done_when[4], done_when[13].
- [ ] After the owner's yes: history-mode calibration for SPY, QQQ and IWM against production bars; commit the 2026-11-06 parameter fixture with its run id and input range
- [ ] PR body: calibrated values beside the #1753 constants with their evidence rows; pick-change counts against #1753 from 2015-01-02 to 2026-11-06 through the production replay paths

## Task 12: close
Spec: § Source identity and close-out. Closes done_when[15] and done_when[16].
- [ ] Source identity sidecar and note rows for DASHBOARD-01, DASHBOARD-21, INSIGHTS-01, INSIGHTS-07, INSIGHTS-08
- [ ] Update the 02-FEATURE-CATALOG FEAT-STRAT-001 and FEAT-INSIGHT-001 records (Status, Last reviewed)
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY and set `pr` here
- [ ] Docs audit reports nothing new over origin/main (`python3 scripts/maintenance/docs_audit.py`)
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main`
