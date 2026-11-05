---
feat_id: FEAT-STRAT-001
spec: docs/superpowers/specs/2026-11-05-feat-strat-001-tf-continuity-display.md
branch: fix/feat-strat-001-tf-continuity-display
pr: null
status: ready
---

# TF bias and true FTFC in the brief implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans.
> Every task cites a spec section and the done_when item it advances.

**Spec:** `docs/superpowers/specs/2026-11-05-feat-strat-001-tf-continuity-display.md` (lands first on `docs/spec-feat-strat-001-tf-continuity-display`).

## Task 1: Continuity timeframes in StratConfig
Spec: § Design, "Configuration". Advances done_when 2.
- [x] `lib/config.py`: `continuity_timeframes_premarket` `['1q', '1mo', '1w']`, `continuity_timeframes_session` `['1q', '1mo', '1w', '1d']`, loaded from `strat` and validated by `validate_continuity_timeframes` (also in `AppConfig.validate`)
- [x] `tests/lib/test_config.py::TestContinuityTimeframes`

## Task 2: Observed price into price-open continuity
Spec: § Design, "Producer". Advances done_when 3.
- [x] `lib/strat.py`: `compute_strat_status(observed_price=, observed_price_session=, price_provenance=, continuity_timeframes=)`; continuity-only frames built at the same clock and `observed_v2` policy; `observed_price_after_clock` and `observed_price_session_not_trading_day`; `calculate_timeframe_continuity(price_provenance=, price_reasons=)`; `timeframe_continuity_record` for storage and display
- [x] `tests/lib/test_strat.py::TestObservedPriceContinuity` on the captured `tests/fixtures/strat_brief_2026-11-05_daily.json`
- [x] A frame whose period starts after the clock leads its reasons with `period_opens_after_clock` and records `period_start` and `observation_ts`; the state stays unavailable while judged frames keep their relation (`tests/lib/test_strat.py::TestFirstSessionOfPeriod`, Monday 2026-11-02 08:30 ET)

## Task 3: Brief Strat box, TF bias relabel and storage
Spec: § Design, "Brief", "Storage" and "Relabel". Advances done_when 1, 4 and 5.
- [x] `gcp/premarket_brief.py`: pass `curr_close`, its session, `latest_completed_close` and the premarket frames; `tf_continuity` / `tf_continuity_frames` on the brief and both tables; `TF bias:` and `FTFC:` lines; `**TF bias:**` overview line
- [x] `gcp/brief_explanations.py`, `gcp/insight_discord_push.py`, `platform/api/schemas.py` (regenerated `platform/api/openapi.json`) relabelled
- [x] `gcp/schema.sql`: nullable `tf_continuity VARCHAR(12)` and `tf_continuity_frames JSONB` on `premarket_analysis` and `premarket_analysis_history`
- [x] `FTFC: unavailable (Q red, M opens today, W opens today)` on the first session of a week or month: `tests/gcp/test_strat_snapshot_parity.py::test_first_session_of_month_and_week_keeps_judged_frames`, `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender::test_unavailable_keeps_judged_frames_and_says_which_open_today`
- [x] `tests/gcp/test_strat_snapshot_parity.py::test_nov5_brief_strat_box_shows_tf_bias_and_ftfc`, `tests/gcp/test_premarket_brief.py::TestTfBiasAndFtfcRender`, `::TestFtfcPersistence`, `::TestExplanationInputsReadTfBias`, `tests/gcp/test_insight_discord_push.py::test_embed_labels_weighted_vote_tf_bias`, `tests/integration/test_schema_query_contract.py::test_brief_writes_ftfc_continuity_to_both_premarket_tables`

## Task 4: Methodology and gates
Spec: § Design, "Methodology"; § Risks. Advances done_when 6 and 7.
- [x] `docs/STRAT_METHODOLOGY.md` Section 16: FTFC and TF bias
- [x] `tests/lib/test_strat.py::TestGatesStayOnTfBias` and the fixture brief's `signal_status` under bullish TF bias with bearish FTFC

## Task 5: close
Spec: § Validation and rollout. Advances done_when 8.
- [x] FEAT-STRAT-001 catalog record (Status, Last reviewed, Next action); SITE notes rebound to the new source identity; diagnostic manifest code hashes
- [ ] Add this PR to 12-PR-ISSUE-TRACEABILITY and set `pr` here once the PR is open
- [ ] `python3 scripts/gate/spec_gate.py --pr origin/main` once the spec is on main
