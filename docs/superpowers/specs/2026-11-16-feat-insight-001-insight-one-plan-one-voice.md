---
feat_id: FEAT-INSIGHT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-LLM-001, REQ-PLAYBOOK-001, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002]
issues: [867]
canvases: []
site_source_notes: [INSIGHTS-01]
done_when:
  - "D1 brief row is the source: tests/agents/test_agent_summarizers.py::TestBriefRow passes: summarize_brief_row(ticker, as_of) issues one strict read of the session's premarket_analysis row (run_kind 'live' for a live run) and returns price, rsi, sma200, ema9, ema20, atr14, bb_upper, bb_lower, rvol, volatility_20d, vol_regime, macd_cross, above_sma200, strat_candle, strat_combo, strat_setup, ftfc_score, ftfc_direction, ftfc_labels, tf_continuity, tf_continuity_frames, prev_day_high, prev_day_low, level_basis and brief_ref {analysis_date, analysis_ts, run_kind}; a ticker in the brief's list with no row returns available False with reason brief_row_missing and no value; the read raising ConnectionError raises; fails on origin/main, where the function does not exist"
  - "D2 nothing the brief holds is recalculated: tests/agents/test_brief_is_the_source.py passes: for a brief ticker, with lib.strat.compute_strat_status, lib.strat_levels.build_session_levels, SessionLevels.with_premarket and lib.level_calibration.calibrate_ticker each replaced by a stand-in that raises, build_context_bundle still returns market, strat and session_levels sections whose values equal the fixture row's column for column, and the report carries brief_ref; with the row absent the three sections are unavailable with reason brief_row_missing, every persona plan is unavailable with that reason and entry_zone, stop and targets are null or empty; fails on origin/main, where summarize_strat_status calls compute_strat_status (lib/agents/summarizers.py:466) and summarize_session_levels builds when no row exists (:606-615)"
  - "D3 the insight's plan is the brief's plan: tests/agents/test_trade_planner.py::TestBriefPlan passes on tests/fixtures/insight_2026_11_16/ (the level_basis of the three stored reports, exported read-only, with sources.json naming the db-query execution, the SQL and each file's sha256): for a short, every persona plan of IWM has entry 275.86 (PMK_L), stop 277.41 (PQL) and targets [269.875]; QQQ 668.30, 679.89 (PDC) and [662.02, 637.01]; SPY 747.95, 750.36 (PML) and [741.025, 729.10]; the three personas differ only in position_size_pct and rationale; a side whose plan targets carry a status that is not ok publishes no target and names the status; no target is a multiple of the stop distance; fails on origin/main, where IWM's neutral plan is stop 276.94 and targets [274.85, 274.34, 273.65]"
  - "D4 critics review the plan that is published: tests/agents/test_agent_orchestrator.py::TestOneVoice::test_critics_review_the_published_plan drives the real run_insight_pipeline with an injected factory that records every request: the persona plans are computed before the risk tier; each of the three risk requests carries the brief's plan with its risk_metrics and the computed rule_flags, and no TraderOutput entry, stop or targets; the entry, stop, targets and risk_metrics of every published persona plan equal the ones its critic was sent; the run makes exactly the 14 model requests origin/main makes; fails on origin/main, where _risk_payload sends trader.model_dump() (lib/agents/orchestrator.py:226-231)"
  - "D5 numeric flags are computed: tests/agents/test_trade_planner.py::TestRuleFlags passes: compute_rule_flags(plan) builds rules N1, N2, N3, C1 and C2 of lib/agents/prompts.py from the plan's risk_metrics alone, each tested one step either side of its threshold; on the IWM fixture N1 reads 'Stop 0.32x ATR from entry' with 0.32 equal to abs(275.86 - 277.41) / 4.87495 rounded, and N2 does not fire (first target 3.86R); the three risk prompts no longer state those rules and say they are listed under rule_flags; fails on origin/main, where the function does not exist"
  - "D6 a flag cannot cite a price that is not in the plan: tests/agents/test_agent_orchestrator.py::TestOneVoice::test_flag_naming_a_price_outside_the_plan_is_withheld passes: a critic stub returning 'Target 1 at 272.67 is too conservative' against the IWM fixture publishes that flag with its persona and severity kept and its message replaced by the fixed withheld sentence, failed_section_reasons['risk_flags'] counts it, the severity still counts toward conviction, and a flag citing 277.41 or a key level is published unchanged; fails on origin/main, where the flag is published verbatim (:680)"
  - "D7 one conviction: tests/agents/test_agent_orchestrator.py::TestOneVoice::test_conviction_reaches_the_pm_and_the_header passes: conviction is computed before the portfolio-manager request, that request carries the final direction, conviction, plan and flags, and report.conviction equals it; ::test_thesis_naming_another_conviction_is_replaced passes: a stub thesis saying 'the conviction is tempered to medium' under a computed low is not published, the thesis is the deterministic sentence built from the facts, and failed_sections holds 'thesis' with reason narrative_conflict; a thesis naming the computed level, or none, is published unchanged; fails on origin/main, where conviction is computed after the thesis (:556) and thesis=pm.thesis (:667)"
  - "D8 invalidation is the plan's stop: tests/agents/test_agent_orchestrator.py::TestOneVoice::test_invalidation_is_the_plan_stop passes: on the IWM fixture report.invalidation names 277.41 and no other price, whatever the model returned; on an orb_only side it is the side's orb_only copy and names no price; flat names none; fails on origin/main, where invalidation=pm.invalidation (:672) and the stored text names 282.2"
  - "D9 max pain is max pain: tests/agents/test_agent_summarizers.py::TestMaxPain passes: summarize_options_flow reads one snapshot (its SQL names snapshot_ts and returns the rows of the latest snapshot_ts of the chosen snapshot_date), and its max_pain is lib.gamma.max_pain over lib.gamma.aggregate_by_strike of the nearest expiration on or after the session date, returned as {strike, expiration, snapshot_ts}, and its largest_oi_strike is the strike with the most open interest summed over every expiration of that same one snapshot, returned as {strike, scope: 'all_expirations', snapshot_ts}; on a frame written in the test, two snapshots of two expirations whose summed open interest peaks at 250 while the nearest expiry's max pain is 280, max_pain.strike is 280 and largest_oi_strike.strike is the peak of the latest snapshot alone; with no expiration on or after the session date the value is absent with a reason; the key max_pain_strike_proxy is gone from lib/, and _derive_key_levels writes two separately named levels, 'Max Pain (exp MM/DD)' from max_pain and 'Largest OI Strike (all exp)' from largest_oi_strike, and no level named 'Max Pain' alone; fails on origin/main (:710-714)"
  - "D10 key level order, Discord layout unchanged: tests/agents/test_agent_orchestrator.py::test_key_level_order passes (report.key_level_order lists every key of key_levels by distance from the plan's reference price, nearest first, ties by name), and tests/gcp/test_insight_discord_push.py::test_levels_render_in_report_order passes (_fmt_levels_field renders in that order, and in dict order for a stored report without the field); the existing assertions of that file on the embed's fields, their names and their order pass unmodified; fails on origin/main, where the field does not exist"
  - "D11 evidence in the PR body: the three fixtures run through the real run_insight_pipeline with a recorded-response model stub, each printing header, plan, invalidation, flags and key levels beside the stored 2026-11-16 13:46Z report; EXPLAIN (ANALYZE, BUFFERS) of the new options read for SPY 2026-11-13, run read-only through scripts/db_query_cr.sh with its execution id, beside the same for the statement on origin/main, with rows read and rows returned for each"
  - "D12 records: 02-FEATURE-CATALOG FEAT-INSIGHT-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the (FEAT-INSIGHT-001, INSIGHTS-01) implementation-source note begins with the current source hash and scripts/maintenance/doc_source_snapshot.py verify accepts the regenerated record, platform/api/openapi.json is regenerated and its check passes if InsightReport is part of it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: approved
supersedes: null
---

# AI Insights: one plan, the brief's, and one voice about it

## Authority and status

Approved by the owner (T) on 2026-11-16. After reviewing the fixes the owner said "Continue working, keep it moving", having said "I approve ... any others that need to be approved to move forward". The numbered recommendations under "Decisions for the owner" stand as written unless the owner strikes one.

The owner (T, 2026-11-16), after checking the 11/16 Discord output against market data:

> "Everything in the AI Insights - can we investigate how to fix all of this?"

> "a new one will be needed for ai insights. Once completed i want to CHECK IWM, QQQ, SPY against market again. And that will require a replay."

Decided by the owner on 2026-11-16, and written into the design below:

> "Use the brief's level-based targets"

> "Ensure everything from the briefing is used, never recalculated or point it to the source data from briefing. Whichever is best."

> "ensure there is a clean table for all of these"

> "where is max pain naming from? Fix display order"

> "I agree with max pain and all but the naming is confusing lol."

The Discord output keeps its layout (owner, same day).

## Scope

- The insight report reads its levels, trigger, stop, targets, ATR, indicators, timeframe labels and TF bias from the session's `premarket_analysis` row, records which row it read, and recalculates none of them. A brief ticker without a row gets "unavailable", never a rebuilt value.
- The insight's plan is the brief's plan: same trigger, same stop, same targets.
- The risk critics review that plan, the numeric risk rules are computed in Python, and no published flag, thesis or invalidation names a price or a conviction the report does not hold.
- Max pain becomes true max pain with its expiry, and the number that was wrongly shown under that name gets its own name, "Largest open interest strike". Two values, two names. Key levels get a stated order.
- One spec, one PR, under FEAT-INSIGHT-001. No schema change, no new model call, no Discord layout change.
- Code references are to `main` 4155a10f (2026-11-16), read for this spec. The max pain references of Design 5 were read again on `main` 060c89a0 the same day. Every production number has its db-query execution beside it; every read was made without `--commit`.

## Capability

- Catalog row FEAT-INSIGHT-001 (`docs/product/02-FEATURE-CATALOG.md:25`, record `:279-300`): AI insights, LLM per-ticker reports, `lib/agents/`, `gcp/insight_pipeline_job.py`.
- Requirements: REQ-DATA-001 (no silent fallback), REQ-DATA-002 (as-of), REQ-DATA-003 (a derived record names its source: `brief_ref`), REQ-LLM-001, REQ-PLAYBOOK-001, REQ-REPLAY-001, REQ-CAP-001, REQ-CAP-002.
- Issue #867 (risk reviews a different plan) is touched; whether it closes is the owner's call after the replay.

## Problem

### 1. Every defect, in one table

What was shown is the stored report of 2026-11-16 13:46Z (`cloud-scheduler:insight-pipeline-daily`) unless another run is named; all rows from db-query-55fxv and db-query-dk8lg, run for this spec.

| # | What was shown | What is right | Cause (main 4155a10f) | Fix | Test |
|---|---|---|---|---|---|
| 1 | IWM header conviction low; thesis "the conviction is tempered to medium" (both runs of the day) | one conviction, the computed one | the portfolio manager writes the thesis, then `_calibrate_conviction` replaces its conviction (`lib/agents/orchestrator.py:556`, function `:887`); the thesis passes through (`:667`) | conviction is computed before the PM writes and is given to it; a thesis naming another level is replaced (Design 4) | D7 |
| 2 | IWM flag "Target 1 at 272.67 is too conservative"; published targets 274.85, 274.34, 273.65. QQQ 13:46 flag "capping the trade at 640.0"; SPY 13:11 "exiting at 725.0"; flags citing stops 282.2, 694.56, 763.04 against published stops 276.94, 672.55, 750.86 | a flag names only prices of the plan it reviewed | the critics are sent the LLM trader's draft (`_risk_payload`, `:226-231`, called `:430`); the published plan is then replaced by the deterministic one (`:629-636`) and the flags are kept verbatim (`:680`) | plans are computed before the risk tier and the critics get the published plan; a flag citing another price is withheld (Design 3) | D4, D6 |
| 3 | IWM flag "Stop only 0.95x ATR from entry midpoint" (0.77x in the 13:11 run, SPY 0.88x); the stored neutral plan's `stop_distance_atr` is 0.273 (SPY 0.299, QQQ 0.312) | the ratio the plan has | the prompts tell the critics to read `risk_metrics` (`lib/agents/prompts.py:190`, `:218`); what they are sent is a `TraderOutput` (`lib/agents/schema.py:453`), which has none, so the ratio is invented | the five numeric rules are computed in Python from `risk_metrics` (Design 3) | D5 |
| 4 | IWM stop 276.94; invalidation "A daily close above the trigger high of 282.2" (QQQ 694.56, SPY 763.04) | the invalidation is the plan's stop | stop is midpoint plus a stop multiple times ATR (`lib/agents/trade_planner.py:279-281`); the invalidation is the PM's prose (`orchestrator.py:672`) echoing the strat section's `trigger_high` (`lib/agents/summarizers.py:480`, from `lib/strat.py:1224-1226`, the high of the bar before the last) | invalidation text is built from the plan's stop; `trigger_high` and `trigger_low` leave the bundle (Design 4) | D8 |
| 5 | IWM targets 274.85, 274.34, 273.65: gaps 0.51 and 0.69, all within 0.4 ATR of the entry, the first 0.18 above the prior day low 274.665 | the brief's targets for the side: 269.875 (PML), spaced by `spacing_price` 1.22 (0.25 ATR) | targets are midpoint minus R multiples of the stop distance, $1.33 (`trade_planner.py:284-287`), with no spacing and no level; the brief's side targets sit unused in the same report's `level_basis` (`lib/strat_levels.py:991`, `:2821-2830`) | the plan is the brief's plan (owner's decision; Design 2) | D3 |
| 6 | "Max Pain" 250.0 (IWM), 700.0 (QQQ), 500.0 (SPY) | max pain of the 11/16 expiry from the 11/13 EOD chain: 280, 686, 762 (db-query-xgkkp) | the value is the strike with the most open interest summed over every expiry and every snapshot of the date (`summarizers.py:710-714`); the read has no snapshot filter (`:676-688`) and 11/13 holds 77 snapshots for IWM, 76 REALTIME and one EOD (db-query-xgkkp). The label "Max Pain" is set at `orchestrator.py:1022-1024`, from the key `max_pain_strike_proxy` (`summarizers.py:734`) | two separately named values (Design 5): "Max Pain (exp 11/16)" from `lib.gamma.max_pain` (`lib/gamma.py:852`) on the nearest expiry of the latest single snapshot, and "Largest OI Strike (all exp)" for the open-interest peak of that same snapshot | D9 |
| 7 | key levels listed as EMA 20, SMA 200, Max Pain, Prev Day Low, Gamma Balance, ... | nearest to price first | `key_levels` is a dict stored in JSONB, which orders keys by length and then bytes; Discord renders dict order (`gcp/insight_discord_push.py:140-152`) | an explicit `key_level_order` (Design 6) | D10 |
| 8 | the 13:11Z run (`cron:auto-refresh-top-n`) published IWM stop 278.49 and targets 276.4, 275.89, 275.2; the 13:46Z run 276.94 and 274.85, 274.34, 273.65 | one plan for the session | the brief's row was written at 13:31:23Z (`premarket_analysis_history`, db-query-nrfqn); before it exists `summarize_session_levels` builds its own levels (`summarizers.py:606-615`), and with it applies its own newer premarket snapshot (`:604-605`) | the row is the only source; no row, no plan (Design 1) | D2 |

### 2. What the insight computes that the brief already holds

The brief's row for the session (`premarket_analysis`, unique on `analysis_date, ticker`) holds each of these. On 2026-11-16 the three rows are `run_kind` live, with `ftfc_labels` `{"1d": "2D", "1w": "1", "1mo": "2U"}` for IWM (db-query-h2n49).

| Value | Where the insight gets it today | The brief column that replaces it |
|---|---|---|
| levels, side lists, trigger, stop, targets, plan spacing, ATR and its basis, parameters | `summarizers.py:566-624`: reads the live row's `level_basis`, applies a newer premarket snapshot, builds with `build_session_levels` when no live row exists | `level_basis` (and `calls_trigger_price`, `puts_trigger_price`, `calls_stop_price`, `puts_stop_price` for a check) |
| entry zone | `trade_planner.py:262-266`: trigger plus entry buffers times ATR | the side's trigger in `level_basis` |
| stop | `trade_planner.py:279-281` | the side's stop in `level_basis` |
| targets | `trade_planner.py:284-287` | the side's targets in `level_basis` |
| candle, combo, setup | `summarizers.py:466` (`compute_strat_status`) | `strat_candle`, `strat_combo`, `strat_setup` |
| TF bias score, direction, labels | the same call, `:478-490` | `ftfc_score`, `ftfc_direction`, `ftfc_labels` |
| price-open continuity | the same call (`_strat_foundation`) | `tf_continuity`, `tf_continuity_frames` |
| `trigger_high`, `trigger_low` | `:480-492` | none: removed; the trigger is the side's in `level_basis` |
| close | `summarizers.py:223-232`, a read of `market_data_daily` | `price` |
| RSI, 200 SMA, 20 EMA, Bollinger bands, ATR(14) | the same read (`rsi_14`, `sma_200`, `ema_20`, `bb_upper`, `bb_lower`, `atr_14`) | `rsi`, `sma200`, `ema20` (and `ema9`), `bb_upper`, `bb_lower`, `atr14` |
| above 200 SMA, RVOL, 20 day volatility, volatility tag, MACD | the same read, with tags computed in the function | `above_sma200`, `rvol`, `volatility_20d`, `vol_regime`, `macd_cross` |
| premarket high, low, VWAP, gap | the same read (`pre_high`, `pre_low`, `pre_vwap`, `gap_pct`) | the premarket block of `level_basis` |
| gamma levels (flip, balance, kings, gates), max pain | `summarize_gamma_levels` (`summarizers.py:746`) and `summarize_options_flow` (`:655`), from `etf_options_snapshots` | none. The brief row holds no gamma value: its gamma probe is metadata for a footer and is not stored (`gcp/premarket_brief.py:1253-1263`). The insight stays the source and names the snapshot it read |

### 3. Open PR #1831

- `docs/superpowers/specs/2026-11-11-feat-insight-001-report-consistency.md` on branch `docs/spec-feat-insight-001-report-consistency-recut2` (head e3cc1504) is a draft, not approved, and waits on #1828's DATA spec.
- It owns, and this spec does not touch: `plan_status` and the plan states, `reviewed_plan_id` hashes and the three-reviewer quorum, `risk_plan_mismatch`, `DecisionFacts` and `report_consistency.py`, failure reasons and telemetry, immutable report versions, leases, the history API, replay inputs at a cutoff, the missing FTFC read as 0.0 (`orchestrator.py:554`, `trade_planner.py:641`), and the fallbacks that publish invented values (#1295).
- It overlaps here: its Problem 3 (risk reviews a different plan) and Problem 4 (calibration follows the narrative) are rows 2 and 1 of the table above, and its Design C reorders the tiers (PM proposal before the risk tier). This spec fixes those two rows with a smaller order change (Design 3 and 4) and no identity hash.
- If this spec is approved and merged first, #1831 must be re-cut: its Problems 3 and 4 will no longer hold on main, its candidates become the brief's plan, and its tier order must start from this one. Decision 1 puts that to the owner.

## Decisions for the owner

**Decided on 2026-11-16:** the insight's plan uses the brief's level-based targets; everything the brief holds is used and never recalculated; one table of the defects; true naming for max pain, as two separately named values ("Max pain (exp <date>)" and "Largest open interest strike", Design 5); a fixed key level order; the Discord layout stays.

The rest are written into the text as recommended. Striking one changes only the sections named.

1. **This spec before #1831** (Problem 3). Recommended: approve this smaller correction now, so the 11/16 replay can be checked, and re-cut #1831 on top of it. Alternative: fold rows 1 and 2 into #1831 and keep only rows 3 to 8 here; the replay would then still show the contradicting thesis and flags.
2. **Tickers the brief does not cover** (Design 1). The brief covers the watchlist rows with `in_brief = TRUE` (`gcp/premarket_brief.py:915-925`); the insight pipeline also runs other tickers, which can never have a row. Recommended: for those, the insight points at the brief's source: the same one builder (`build_session_levels`) and the same readers, labelled `source: builder` with no `brief_ref`, as today. For a brief ticker a missing row is "unavailable". Alternative: no row, no plan, for every ticker; every report outside SPY, QQQ and IWM would then carry no plan.
3. **Runs before the brief has written its row** (Problem 1 row 8). Recommended: they publish the report with the plan unavailable (`brief_row_missing`); on 11/16 that is the 13:11Z auto-refresh run. Moving that schedule after the brief is a deploy change under FEAT-DEPLOY-001 and is not in this spec. Alternative: the run reads the latest earlier live row; rejected, a prior day's levels are not this session's.
4. **The brief's late premarket snapshot** (Design 1). Recommended: the insight reads the stored row as it is and applies no snapshot of its own; when the brief's late slot rewrites the row (`2026-11-14-feat-playbook-001-brief-late-slot.md`), the next insight run reads the new one and records its `analysis_ts`. Alternative: keep `with_premarket`; that is a recalculation.
5. **Three personas, one plan** (Design 2). Recommended: `persona_plans` keeps its three entries, each with the brief's entry, stop and targets; they differ in `position_size_pct` (allocation policy, which the brief does not hold) and rationale. `entry_zone` is the trigger at both ends. Alternative: keep per-persona entry buffers and stops from the calibrated parameters; that recalculates the stop the brief already published.
6. **Who decides direction** (Design 4). Conviction needs a direction, a confidence and the risk severities, and today the PM supplies the first two after the risk tier. Recommended: direction and confidence are the trader's (`TraderOutput.direction`, `.confidence`), a block still makes it flat, and the PM becomes the narrator of fixed facts. Alternative: #1831's order (PM proposes before the risk tier, never sees the reviews, and its thesis is checked afterwards). How often the PM overrules the trader today is not measured: the trader's output is not stored.
7. **Rule N1 on the brief's stop** (Design 3). Computed truthfully, "stop under 1.0 ATR from entry" fires on all three tickers on 11/16 (IWM 0.32, QQQ 0.71 and SPY 0.22 ATR), and a warn bars high conviction (`orchestrator.py:887-940`). Recommended: keep the rule and its severity as written, show the true number, and decide the threshold in its own spec with its own evidence; the rule's evidence is a 36-day sample of May 2026 (`lib/agents/schema.py:141-157`). Alternative: make N1 informational here.
8. **A withheld flag keeps its severity** (Design 3). Recommended: the message is replaced, the severity still counts, so a block cannot be dropped by a bad citation. Alternative: drop the flag.
9. **Max pain's expiry** (Design 5). Recommended: the nearest expiration on or after the session date. Alternative: the nearest monthly expiry.
10. **Key level order** (Design 6). Recommended: nearest to the plan's reference price first. Alternative: a fixed order by family (day, week, month, quarter, year, averages, gamma).

## Non-goals

- Nothing #1831 owns (Problem 3).
- No change to the brief, to `lib/strat_levels.py`, to the level builder, to the level parameters or to how the brief picks targets. A separate spec will cover targets; the insight follows whatever the row holds.
- No change to `_calibrate_conviction`'s rules or thresholds, to the risk rules' thresholds, or to the FTFC weights.
- No schema change. `key_level_order` and `brief_ref` are fields of the report JSON.
- No Discord layout change: no field added, removed, renamed or moved.
- No schedule or deploy change, and no production write from the implementation PR.
- No change to gamma levels (flip, balance, kings, gates).
- No solyra change. The site shows the same fields with different values; the browser proof AGENTS.md asks for is in Close-out.

## Approaches considered

1. Read the brief's row and publish its plan; reorder so the critics and the PM see that plan (chosen).
2. Keep the planner's R-multiple targets and thin them by the brief's spacing: rejected by the owner's decision; it is a second plan.
3. Keep the insight's own readers and assert parity with the brief in a test (`tests/lib/test_brief_planner_parity.py` does this for the trigger): parity tests did not stop 8 rows of defects; a value read once cannot drift.
4. Point every value at the brief's source tables instead of its row: for a brief ticker the row is what was published at 08:30 ET, and a later rebuild from source can differ (row 8). Used only where no row can exist (decision 2).
5. Prompt-only fixes ("do not cite other prices"): the prompt already forbids prices in the thesis (`lib/agents/prompts.py`, PM prompt) and `_validate_thesis_consistency` only warns (`orchestrator.py:738`).

## Design

### 1. The brief row: `summarize_brief_row` (`lib/agents/summarizers.py`)

- One strict read per ticker of the session's `premarket_analysis` row, by `analysis_date` and `ticker`, with `run_kind = 'live'` on a live run. Which `run_kind` an `INSIGHT_AS_OF` replay reads is fixed by `read_live_level_basis` today (live only) and stays so.
- It returns the columns named in D1 and `brief_ref {analysis_date, analysis_ts, run_kind}`. `InsightReport` gains the optional field `brief_ref`.
- `build_context_bundle` (`:2055-2059`) fills `market`, `strat` and `session_levels` from that one row for a brief ticker. `summarize_strat_status` and the indicator part of `summarize_market_context` are not called for it. The sections keep their key names, so prompts and `context_from_bundle` read them as today; `trigger_high` and `trigger_low` are removed and `lib/agents/prompts.py:168` is rewritten to name the side's trigger.
- No row for a brief ticker: the three sections are `available: False`, reason `brief_row_missing`, they join `failed_sections`, and the planner returns unavailable plans. No builder call, no on-demand calibration, no `with_premarket`.
- A null column is null in the section. Nothing is coerced.
- A ticker outside the brief's list keeps today's path (decision 2), labelled `source: builder`.
- Sections the row does not hold (options, gamma, catalysts, sentiment, backtest) are unchanged apart from Design 5.

### 2. The plan (`lib/agents/trade_planner.py`)

- For a side with a trigger: entry is the trigger, stop is the side's stop, targets are the side's targets, all from `ctx.levels` (`SessionLevels.from_basis` of the row's `level_basis`). `_plan` loses its entry buffers, `persona_stop_price` call, R multiples and the aggressive analog stretch.
- A side with no stop in its window publishes the plan with stop null and says so in the rationale; a side whose targets carry a status that is not ok publishes no target and names the status. There is no R-multiple fallback.
- `risk_metrics` is computed from those prices by `compute_risk_metrics` as today (distances are measurements, not plan values).
- `position_size_pct` stays per persona and conviction (`_SIZE_BY_CONVICTION`, `:140-144`), with the conservative gates as they are.
- The headline stays the neutral entry of `persona_plans` (`orchestrator.py:629-636`).

### 3. Risk tier (`lib/agents/orchestrator.py`, `lib/agents/prompts.py`)

Order in `run_insight_pipeline`: analysts, bull and bear, judge, trader, **plans**, **rule flags**, risk critics, conviction, portfolio manager, assembly. The model requests are the same 14.

- Plans are computed from the trader's direction before the risk tier. Their prices do not depend on conviction; only sizing does, and sizing is filled after conviction.
- `compute_rule_flags(plan)` in `trade_planner.py` applies N1 (`stop_distance_atr < 1.0`), N2 (first target under 1.5R), N3 (`ftfc_aligned` false), C1 (`stop_distance_pct > 1.0`) and C2 (long, `entry_vs_sma200_pct > 10.0`) with the severities and wording the prompts hold today, formatted from `risk_metrics`. A metric that is null gives no flag and is counted in `failed_section_reasons`.
- `_risk_payload` sends each critic the plan, its `risk_metrics`, the rule flags, and the strat, catalysts and market sections. The prompts drop the five rules, say the platform computed them, and say any price a critic names must be one in the plan or in the key levels.
- Every price-like number in a critic's flag (`_PRICE_PATTERN`, already in the module) must match the plan's entry, stop or a target, or a key level, within the 0.5 percent the thesis check uses. A flag that fails keeps persona and severity; its message becomes "A {persona} reviewer's note was withheld: it cited a price that is not in the plan."; the original goes to the log, and `failed_section_reasons['risk_flags']` holds the count.
- A block still makes the direction flat. The flat plan is computed after the review, as today.

### 4. Conviction, thesis, invalidation

- `_calibrate_conviction` runs before the PM with the trader's direction and confidence, the analyst agreement, the row's `ftfc_score` and the severities of rule flags and critic flags. `report.confidence_score` is the value used.
- The PM request carries direction, conviction, the plan, the flags and the cases, marked as fixed. `PortfolioManagerOutput` keeps its shape; its direction, conviction, entry, stop, targets, invalidation and confidence are not published.
- Thesis check, replacing the warn-only one: the thesis, bull case and bear case may not name a conviction level other than the computed one (the words low, medium, high within the same sentence as "conviction"), nor a price outside the plan and key levels. On a conflict the field is replaced by a sentence built from the facts ("Short, low conviction. Entry 275.86 (PMK_L), stop 277.41 (PQL), target 269.88 (PML)."), `failed_sections` gains the field's name with reason `narrative_conflict`, and the original goes to the log. No second model call.
- `report.invalidation` is built from the plan: "Stop 277.41 (PQL): the plan is invalid beyond it." On an `orb_only` side it is the side's copy; flat has none.

### 5. Max pain (`lib/agents/summarizers.py`, `lib/agents/orchestrator.py`)

- `summarize_options_flow` reads the rows of the latest `snapshot_ts` of the chosen `snapshot_date`, adding `expiration` and `snapshot_ts` to its columns. Volumes, put/call ratio, top open-interest strikes and weighted IV are then of one snapshot, not of 77 added together.
- **Where today's name comes from.** `summarize_options_flow` sums open interest by strike and takes the largest (`summarizers.py:710-714`); its own comment calls that an "approximation" and a "simple proxy" for max pain (`:707-708`). It returns the number under the key `max_pain_strike_proxy` (`:734`), and `_derive_key_levels` drops the word "proxy" and stores it as the key level "Max Pain" (`orchestrator.py:1022-1024`). Discord prints key level names as stored (`gcp/insight_discord_push.py:144-148`). So "Max Pain 250" was never max pain: it was the strike with the most open interest, added across every expiry and all 77 snapshots of the date.
- **Two values, two names.** Nothing else in the report is called max pain, and neither name is used for the other value.

| | Max pain | Largest open interest strike |
|---|---|---|
| Plain meaning | the strike where option holders, calls and puts together, lose the most if the stock closes there at that expiry | the strike with the most contracts open, calls plus puts |
| Computed by | `lib.gamma.max_pain(lib.gamma.aggregate_by_strike(rows))` (`lib/gamma.py:852`), the function the options API already uses (`platform/api/routers/options.py:823`) | the strike with the largest summed `open_interest` |
| Scope | the nearest expiration on or after the session date, of one snapshot | every expiration of that same one snapshot |
| Key in the options section of the stored bundle | `max_pain: {strike, expiration, snapshot_ts}` | `largest_oi_strike: {strike, scope: "all_expirations", snapshot_ts}` |
| Key in the stored report's `key_levels`, which is the label Discord prints | `Max Pain (exp 11/16)`, as `Max Pain (exp MM/DD)` | `Largest OI Strike (all exp)` |
| 11/13 EOD chain | IWM 280, QQQ 686, SPY 762 (db-query-xgkkp) | not read for one snapshot; 250, 700 and 500 were the sums over every snapshot |

- **Kept or dropped.** Recommended, and written into D9: keep the largest open interest strike as its own key level, because Design 5 already reads one snapshot, so it is an honest number, and the label carries its scope. If it could only be had by adding snapshots together it would be dropped; a value summed over 77 snapshots is not published under any name. Alternative: drop the key level and leave the strike only in `top_oi_strikes`, which the models already receive.
- Contracts with null open interest are left out of both values and counted in the section; with none left, or no expiration on or after the session date, max pain is absent with a reason. The largest open interest strike is absent with a reason when no contract has open interest.
- `max_pain_strike_proxy` is removed with its readers (`orchestrator.py:1022-1024`, the tests that name it). The Discord embed keeps its "Key Levels" field and its format; it gains one line, because the one mislabelled level becomes two labelled ones. A report stored before this change keeps its old "Max Pain" key and is not rewritten.
- The two `.fillna(0)` on volume and IV (`:704-705`, `:720-721`) are existing fallbacks on adjacent lines: they get the `AUDIT-2026-05-13` marker and are not extended.

### 6. Key level order

- `InsightReport.key_level_order: list[str]`: the keys of `key_levels` by absolute distance from the plan's reference price (the level basis's reference, else the row's price), nearest first, ties by name.
- `_fmt_levels_field` renders in that order when the field is present and in dict order for a stored report without it. Same field, same format.

### 7. Capacity (CLAUDE.md rule 0)

| Step | Volume | Velocity | Wall-clock |
|---|---|---|---|
| brief row | one row per ticker | one read in place of the strat and session-level reads | under 2 s at rule 0's 0.5 to 2 s a round trip |
| options read | one snapshot: 5,024 rows (IWM), 11,052 (QQQ), 12,738 (SPY) on 11/13, against 386,848, 828,900 and 955,608 rows returned today (db-query-xgkkp) | one statement, as today | not measured; D11 measures it. Today's statement already reads every row of the date, so the new one cannot read more |
| model calls | 14 per report, as today | unchanged | unchanged |

- Memory falls: the options frame is one snapshot. Job limits are unchanged (`gcp/deploy.sh:615-628`).
- Cost: no new call, no new job, no new schedule. The replay in Close-out is three reports; the cost of one is `cost_usd` on its row and was not read.

## Implementation plan: size

11 tasks, one branch, one PR.

1. The fixture export and `sources.json`.
2. `summarize_brief_row` and its tests.
3. The bundle wiring, the brief ticker list, `brief_missing` states, `brief_ref`.
4. The planner on the brief's plan, and `TestBriefPlan`.
5. `compute_rule_flags` and the prompt edits.
6. The order change, `_risk_payload`, the flag price check.
7. Conviction before the PM, the PM payload, the thesis check.
8. Invalidation text; removal of `trigger_high` and `trigger_low`.
9. The options read and max pain.
10. `key_level_order` and the Discord renderer.
11. PR-body evidence, the site note, catalog and traceability.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes.

1. **Deploy**: `./gcp/deploy.sh insights`, from `main` at or after the merge.
2. **Replay 2026-11-16**, on the owner's yes:
   `gcloud run jobs execute insight-pipeline --region us-east1 --update-env-vars="^|^INSIGHT_AS_OF=2026-11-16|INSIGHT_TICKERS=SPY,IWM,QQQ" --args="--update" --wait`
   - What it writes, read on main 4155a10f: a row per ticker in `insight_reports` with `run_kind` 'replay' (`gcp/insight_pipeline_job.py:352-370`, `:388-415`), keyed `(ticker, as_of)` with `as_of` midnight UTC of the date, so the day's live rows (13:11Z and 13:46Z) are not overwritten; and a history row (`:317-343`).
   - It does not post: the job has no Discord call, and the scheduled push reads `run_kind = 'live'` only (`gcp/insight_discord_push.py:95-105`).
   - Check, read-only: the three replay rows exist with `brief_ref` naming the 11/16 row; the three live rows are unchanged.
3. **Check each output against market data**, on the owner's yes, ticker by ticker: entry, stop and targets equal the brief row's; max pain and its expiry against the 11/13 chain, and the largest open interest strike against the same snapshot; the invalidation price is the stop; every flag's numbers are the plan's; the header's conviction is the thesis's; key levels in order. Recorded on the PR.
4. **Browser proof**: the owner's runs against the deployed site, as AGENTS.md defines, for the insights report card.
5. On a `docs/` branch after the merge: `docs/product/08-AI-AGENT-ARCHITECTURE.md` (tier order, node contract), the plan's status, and the re-cut of #1831 (decision 1).

## Risks

- **Reports outside the brief's list keep the builder path** (decision 2). They are not "the brief's plan", and they say so by having no `brief_ref`.
- **The 08:11 ET auto-refresh run publishes no plan** until its schedule moves (decision 3).
- **The brief's plan is thinner than the old one**: IWM has one target on 11/16, and a side can have no stop in its window. The report shows that as it is. The separate targets spec may change what the row holds.
- **N1 fires on every plan whose stop is under 1.0 ATR**, which is all three on 11/16; high conviction is then out of reach until decision 7's threshold is settled.
- **Direction is the trader's** (decision 6). Reports where the PM used to overrule the trader change direction; how many is not known.
- **The calibrated persona parameters** (entry buffers, stops, target R) stop being read by the planner for brief tickers. They stay in `ticker_level_params`; the nightly calibration still writes them.
- **The thesis check is text matching.** It can miss a paraphrase ("moderate conviction") and can replace a sentence that only quotes a level. D7 pins the 11/16 sentence.
- **Options volumes drop about 77 times** in the options analyst's input, because one snapshot is read. The put/call ratio and IV change less. Analyst prose may shift.
- **The fixture is the insight's stored copy of `level_basis`**, not the brief row's column; they should be equal and were not compared.
- **#1831 goes stale** on its Problems 3 and 4 and its tier order.

## What was not verified

- That the stored report's `level_basis` equals `premarket_analysis.level_basis` for 11/16: not compared.
- How often the portfolio manager's direction or confidence differs from the trader's: not measured; the trader's output is not stored.
- What an `INSIGHT_AS_OF=2026-11-16` date-only replay reads for the premarket snapshot and for the options and gamma cutoffs: not run. `summarize_options_flow`'s docstring says one snapshot per date (`:666-667`); production holds 77 (db-query-xgkkp).
- The wall-clock of the new options read: not measured (D11).
- The per-ticker manual Discord push (`insight_discord_push.py:82-91`) has no `run_kind` filter. It orders by `as_of` descending, so on 11/16 it would pick the 13:46Z live row over a midnight replay row; not run.
- Whether `tests/lib/test_brief_planner_parity.py` needs new expectations under Design 2: its docstring was read, its assertions were not.
- Whether `InsightReport` is part of `platform/api/openapi.json`: not checked.
- The cost of one report and of the replay: not read.
- Whether the insights canvas depicts the tier order: not opened.
- solyra's rendering of `key_levels` and of an empty target list: not opened.
- The largest open interest strike of the single 11/13 EOD snapshot for IWM, QQQ and SPY: not read. The 250, 700 and 500 on record are sums over every snapshot of the date.
- Whether any stored-report reader matches a key level by the exact name "Max Pain": `lib/`, `gcp/` and `platform/api/` were searched on origin/main 060c89a0 and only `orchestrator.py:1024` writes it; solyra was not searched.
