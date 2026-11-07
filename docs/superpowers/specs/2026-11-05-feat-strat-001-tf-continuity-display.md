---
feat_id: FEAT-STRAT-001
req_ids: [REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-MARKET-001, REQ-REL-001]
issues: [884]
site_source_notes: [DASHBOARD-01, INSIGHTS-08]
canvases:
  - https://claude.ai/artifact/Fg4VQHB6dFGWF9iXSJUDtg
done_when:
  - "Every displayed label of the weighted candle vote reads TF bias (brief Strat box and overview line, brief_explanations inputs, the insight Discord embed, platform/api field descriptions) while every code key, column and API field name stays unchanged"
  - "StratConfig carries continuity_timeframes_premarket ['1q', '1mo', '1w'] and continuity_timeframes_session ['1q', '1mo', '1w', '1d'], loaded from alert_config strat and refused when empty, duplicated or not a period timeframe"
  - "compute_strat_status publishes price-open-v1 timeframe_continuity from a supplied observed price over the requested continuity timeframes at the same observation clock and observed_v2 aggregation; a missing frame or open, an invalid price or a price observed after the clock is unavailable with reasons; without the new arguments its output is unchanged"
  - "On the captured 2026-11-05 08:30 ET brief fixture, the QQQ Strat box shows FTFC bearish with Q, M and W red beside its unchanged TF bias and candle label lines, and IWM and SPY show their own computed states; on the captured 2026-11-02 08:30 ET (first session of the week and month) fixture the state is unavailable while the judged quarter frame is stored and shown and the week and month read as opening today"
  - "premarket_analysis and premarket_analysis_history gain nullable tf_continuity and tf_continuity_frames in gcp/schema.sql, the brief writes both to both tables, the writer still succeeds against tables without them, and the cached /replay path (fetch_premarket_analysis_row into _build_ticker_fields) renders FTFC: unavailable (not recorded) for a migrated row whose two columns hold SQL NULL, read back as None or NaN"
  - "docs/STRAT_METHODOLOGY.md Section 16 describes TF bias (the weighted vote the gates use) and FTFC (price versus current-period open, display and storage only)"
  - "The gates stay on the weighted score: _resolve_signal_status, brief_bias, signal_monitor get_strat_bonus, trade_planner, orchestrator, ranker signals and the backtests read no price-open continuity, and the brief's signal_status on the fixture follows TF bias where FTFC disagrees"
  - "The FEAT-STRAT-001 capability and PR traceability records, focused tests and spec gate pass; the matched docs_audit.py run stays tracked in #1720; the production column migration and deployed verification are recorded separately after normal release gates"
status: approved
supersedes: null
---

# TF bias and true FTFC in the brief (display and storage only)

## Authority

Proposed on 2026-11-05 by the FEAT-STRAT-001 delivery lane after the owner asked whether the brief's "FTFC" matches Rob Smith's Strat, chose the name "TF bias" for the existing weighted number, and approved this plan: relabel the weighted number, publish true price-versus-open continuity, store it, and leave every gate on the weighted score. This file is not self-approved: it takes effect only when the owner authorizes the merge of the PR that adds it, and that merge is the approval its `status` records. It is not a rollout, a gate change or a production migration.

## Problem

The brief's Strat box prints `FTFC: +0.5 (bullish)`. That number is `StratClassifier.calculate_ftfc`: a weighted vote of candle types (daily 0.30, weekly 0.10, monthly weight 0; 2U counts up, 2D down, 1 and 3 count zero). In Rob Smith's Strat, Full Timeframe Continuity means price is above (green) or below (red) the current period's open on every timeframe. The two disagree on real data: on the 2026-11-05 08:30 ET brief, QQQ's latest close 691.95 (2026-11-04) is below the week and month open 695.315 (2026-11-02) and below the quarter open, so true FTFC is bearish, while the weighted vote reads +0.5 bullish because the daily candle was 2U. Issue #884 records the naming problem.

The approved foundation contract (`docs/superpowers/specs/2026-11-05-feat-strat-001-foundation-tracked-docs-audit.md`, carrying Section 3 of `2026-10-12-feat-strat-001-complete-state-contract.md`) already requires the weighted number to stay as legacy weighted candle alignment and a separate `timeframe_continuity` (price versus current period open) to be published. `lib/strat.py` has `calculate_timeframe_continuity` (rule `price-open-v1`), but `compute_strat_status` calls it with `observed_price=None`, so it is always unavailable. The foundation release selected no reference FTFC frame set; this spec selects one, for display and storage only.

## Non-goals

- No gate, signal, bonus, threshold, weight, training feature or backtest change. `ftfc_score` and `ftfc_direction` keep their values and every consumer that reads them.
- No rename of any code key, column, JSON key or API field. Only displayed text changes.
- No API response change beyond field descriptions; the new columns are not served by `/api/dashboard` in this change.
- No production migration, backfill or deploy. The owner runs the schema apply later.
- No site change: the site frontend lives in the solyra repository and is out of scope.
- No in-session consumer. `continuity_timeframes_session` is configuration for later consumers; nothing in this change reads it.

## Approaches considered

1. Rename `ftfc_score` everywhere. Touches every gate, the API and the site; rejected by the owner.
2. Replace the weighted number with true continuity. Changes gates and signals; rejected (display and storage only).
3. Chosen: relabel the weighted number as TF bias where it is displayed, publish true continuity beside it from the brief's own price, and store it in two new nullable columns.

## Design

**Names.** The weighted vote is displayed as "TF bias". "FTFC" is displayed only for price-open continuity.

**Configuration.** `lib/config.py` `StratConfig` gains `continuity_timeframes_premarket = ['1q', '1mo', '1w']` and `continuity_timeframes_session = ['1q', '1mo', '1w', '1d']`. Daily is excluded premarket because the brief runs at 08:30 ET, before the 09:30 open, so today's daily period has no observed open. Both load from `alert_config.json` `strat` and are refused (ValueError) when empty, duplicated, or not one of `1d`, `1w`, `1mo`, `1q`, `1y`.

**Producer.** `compute_strat_status` gains keyword arguments `observed_price`, `observed_price_session`, `price_provenance` and `continuity_timeframes`. Continuity frames not already in `timeframes` (such as `1q`) are built from the same filtered daily source with `build_multi_timeframe` at the same confirmation clock and `observed_v2` policy, and get the same source-contract reasons. They are used only for continuity: the weighted vote, `ftfc_labels` and directional continuity keep their frames. When `observed_price_session` is given, the price counts only if that session's actual NYSE close is at or before the clock; otherwise every frame is unavailable with `observed_price_after_clock` (or `observed_price_session_not_trading_day`). `calculate_timeframe_continuity` keeps `price-open-v1` and records the provenance. With none of the new arguments the output is byte-identical to today's.

**Brief.** `gcp/premarket_brief.py` passes its own `price` (`curr_close`, the latest completed daily close), that bar's session, provenance `latest_completed_close` and `cfg.strat.continuity_timeframes_premarket`. It records `tf_continuity` (`bullish`, `bearish`, `mixed` or `unavailable`) and `tf_continuity_frames`: per timeframe, `relation` (`green` above the open, `red` below, `at_open`, `unavailable`), `open`, `observed_price`, `price_provenance`, `price_session`, `rule_version`, `period_start`, `observation_ts` and `reasons`. The Strat box keeps its TF bias line (`TF bias: +0.5 (bullish)`) and candle label line (`1D:2U 1W:2D 1M:2D`) and adds `FTFC: bearish (Q red, M red, W red)` or `FTFC: mixed (Q green, M red, W red)`. When any frame is unavailable the state is `unavailable` (no partial claim of agreement) but the line still lists every frame: a judged frame by its color, a frame whose current period starts after the observation clock (the first session of a week, month or quarter at 08:30 ET; the producer leads its reasons with `period_opens_after_clock`) as `opens today` (or `opens <date>`), and any other unavailable frame as `<frame>: <first reason>`, for example `FTFC: unavailable (Q red, M opens today, W opens today)`. Frames render quarter, month, week, day in that order. A row without the columns, or a migrated row whose two columns are SQL NULL (no backfill; pandas can return the NULL as `None` or `NaN`), renders `FTFC: unavailable (not recorded)`, and any `tf_continuity_frames` value that is not an object is read as no frames.

**Storage.** `gcp/schema.sql` adds `tf_continuity VARCHAR(12)` and `tf_continuity_frames JSONB`, nullable, to `premarket_analysis` and `premarket_analysis_history` with `ADD COLUMN IF NOT EXISTS`. The history rows are built from the canonical rows, so one row-builder change writes both. `upsert_dataframe` and `bulk_insert_dataframe` drop DataFrame columns the reflected table lacks, so the writer keeps working before the migration; a test proves it against a reflected table without the columns.

**Relabel.** Displayed text only: the brief Strat box and overview line, the three `gcp/brief_explanations.py` LLM inputs (which also receive the FTFC state, and no longer read a missing score as 0), the insight Discord embed's Strat field, and the `ftfc_score`/`ftfc_direction` field descriptions in `platform/api/schemas.py` (regenerated `platform/api/openapi.json`).

**Methodology.** `docs/STRAT_METHODOLOGY.md` Section 16 documents both measures and which one the gates use.

## Capacity and cost

- **Volume:** the brief's in-brief tickers (three ETFs today), each about 250 daily rows already loaded; two more columns per row in two tables.
- **Velocity:** zero new queries or API calls; one extra in-memory `observed_v2` aggregation (`1q`) per ticker.
- **Wall-clock:** milliseconds per ticker, inside the existing brief job.
- **Cost:** $0 new GCP workload, schedule or resource.

## Risks

- **A gate could start reading the new state.** done_when 7 pins the gate modules to the weighted score.
- **A price from after the clock in a replay.** The session-close check refuses it with a reason.
- **The columns are not in production until the owner applies the schema.** The writer drops them until then (done_when 5); the brief still renders FTFC from memory.

## Validation and rollout

1. This spec-only change lands on `docs/spec-feat-strat-001-tf-continuity-display` and merges on owner authorization.
2. The implementation branch `fix/feat-strat-001-tf-continuity-display` then carries the plan, code, tests and records.
3. The owner applies `gcp/schema.sql` to production when they choose; no production action here.
