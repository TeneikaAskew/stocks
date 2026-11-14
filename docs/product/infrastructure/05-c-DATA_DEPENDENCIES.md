# Data Dependencies — table-level write/read graph

**Last reviewed:** unknown · **Last scanned:** 2026-11-10 · **Owner:** TBD

**Generated 2026-09-07** from [`gcp/schema.sql`](../../../gcp/schema.sql), a whole-word scan of `gcp/`, `lib/`, `scripts/` and `platform/api` (tests and `archive/` excluded), and the 2026-09-07 live table statistics, by [`scripts/maintenance/doc_inventory.py`](../../../scripts/maintenance/doc_inventory.py). Every citation is a `file:line` you can open. The blocks between `<!-- inventory:*:start/end -->` markers are rendered by `doc_inventory.py`, and the pull request that changes what they cite carries the new render (REQ-GOV-004); the prose between them is maintained by hand.

This doc complements [ARCHITECTURE.md](05-a-ARCHITECTURE.md) §5 (schema by domain) and §6 (jobs). Where ARCHITECTURE says "job X runs module Y", this doc answers "module Y writes table Z, and Z is read by A, B, C".

> **Partition handling.** `market_data_intraday` is LIST-partitioned by ticker into five children (`_spy`, `_iwm`, `_qqq`, `_spx`, `_other`). Writes are routed by Postgres through the parent, so no child has a writer of its own. Four of them ARE read directly, by name assembled at run time: `scripts/analysis/per_ticker_calibration.py` builds the suffix for SPY / IWM / QQQ / SPX, and `gcp/research/p2_outcomes_grid.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/options_exec_backtest/runner.py` and `gcp/research/p7_build_multi_tf_features.py` look one up in a per-ticker mapping. Those four therefore carry §3 reference sections; `_other` is named by no branch and appears only in §1 and §5.
>
> **Runtime tables.** The live database holds 28 relations that `gcp/schema.sql` does not declare (`strat_features_*`, `magnitude_*`, `gamma_levels_eod`, `daily_vex`, `gamma_events`, `*_30m_predictions`, `market_data_indicators*`, `market_data_cross_asset`); they are created by research and analytics jobs at runtime. They are listed in §1b with row counts but have no write/read graph here because their names are built dynamically in code.
>
> **Ad-hoc access.** [`scripts/db_query_cr.sh`](../../../scripts/db_query_cr.sh) → the `db-query` Cloud Run Job can read or (with `--commit`) write any table. It is an operator tool, not a pipeline component, and is not listed as a writer or reader.

---

## 1. Table inventory (declared in `gcp/schema.sql`)

<!-- inventory:tables:start -->
| Relation | Kind | Defined |
|---|---|---|
| `admin_refresh_leases` | table | [`gcp/schema.sql:5315`](../../../gcp/schema.sql#L5315) |
| `archive_yahoo_earnings_options_snapshots` | table | [`gcp/schema.sql:566`](../../../gcp/schema.sql#L566) |
| `archive_yahoo_etf_options_snapshots` | table | [`gcp/schema.sql:563`](../../../gcp/schema.sql#L563) |
| `archive_yahoo_market_data_daily` | table | [`gcp/schema.sql:557`](../../../gcp/schema.sql#L557) |
| `archive_yahoo_market_data_intraday` | table | [`gcp/schema.sql:560`](../../../gcp/schema.sql#L560) |
| `backtest_reports` | table | [`gcp/schema.sql:4124`](../../../gcp/schema.sql#L4124) |
| `backtest_sweeps` | table | [`gcp/schema.sql:4095`](../../../gcp/schema.sql#L4095) |
| `backtest_trades` | table | [`gcp/schema.sql:4053`](../../../gcp/schema.sql#L4053) |
| `backtest_walk_forward_folds` | table | [`gcp/schema.sql:4150`](../../../gcp/schema.sql#L4150) |
| `daily_rates` | table | [`gcp/schema.sql:536`](../../../gcp/schema.sql#L536) |
| `earnings_calendar` | table | [`gcp/schema.sql:576`](../../../gcp/schema.sql#L576) |
| `earnings_calibration` | table | [`gcp/schema.sql:4243`](../../../gcp/schema.sql#L4243) |
| `earnings_history` | table | [`gcp/schema.sql:737`](../../../gcp/schema.sql#L737) |
| `earnings_options_snapshots` | table | [`gcp/schema.sql:475`](../../../gcp/schema.sql#L475) |
| `earnings_options_strategy_insights` | table | [`gcp/schema.sql:4471`](../../../gcp/schema.sql#L4471) |
| `earnings_options_strategy_winners` | table | [`gcp/schema.sql:4499`](../../../gcp/schema.sql#L4499) |
| `earnings_reactions` | table | [`gcp/schema.sql:783`](../../../gcp/schema.sql#L783) |
| `earnings_upcoming_with_history` | table | [`gcp/schema.sql:5027`](../../../gcp/schema.sql#L5027) |
| `economic_events` | table | [`gcp/schema.sql:1455`](../../../gcp/schema.sql#L1455) |
| `etf_options_daily_greeks` | table | [`gcp/schema.sql:382`](../../../gcp/schema.sql#L382) |
| `etf_options_snapshots` | table | [`gcp/schema.sql:175`](../../../gcp/schema.sql#L175) |
| `exit_config_overrides` | table | [`gcp/schema.sql:3472`](../../../gcp/schema.sql#L3472) |
| `historical_signals` | table | [`gcp/schema.sql:2339`](../../../gcp/schema.sql#L2339) |
| `indicator_correlation` | table | [`gcp/schema.sql:4312`](../../../gcp/schema.sql#L4312) |
| `insider_transactions` | table | [`gcp/schema.sql:992`](../../../gcp/schema.sql#L992) |
| `insight_reports` | table | [`gcp/schema.sql:1554`](../../../gcp/schema.sql#L1554) |
| `insight_reports_history` | table | [`gcp/schema.sql:2270`](../../../gcp/schema.sql#L2270) |
| `insight_runs` | table | [`gcp/schema.sql:1590`](../../../gcp/schema.sql#L1590) |
| `intraday_flow_15m` | table | [`gcp/schema.sql:422`](../../../gcp/schema.sql#L422) |
| `intraday_gex_15m` | table | [`gcp/schema.sql:443`](../../../gcp/schema.sql#L443) |
| `job_runs` | table | [`gcp/schema.sql:5164`](../../../gcp/schema.sql#L5164) |
| `journal_entries` | table | [`gcp/schema.sql:1213`](../../../gcp/schema.sql#L1213) |
| `level_param_policy` | table | [`gcp/schema.sql:2162`](../../../gcp/schema.sql#L2162) |
| `market_data_daily` | table | [`gcp/schema.sql:37`](../../../gcp/schema.sql#L37) |
| `market_data_intraday` | table | [`gcp/schema.sql:140`](../../../gcp/schema.sql#L140) |
| `market_data_intraday_iwm` | partition of `market_data_intraday` | [`gcp/schema.sql:158`](../../../gcp/schema.sql#L158) |
| `market_data_intraday_other` | partition of `market_data_intraday` | [`gcp/schema.sql:164`](../../../gcp/schema.sql#L164) |
| `market_data_intraday_qqq` | partition of `market_data_intraday` | [`gcp/schema.sql:160`](../../../gcp/schema.sql#L160) |
| `market_data_intraday_spx` | partition of `market_data_intraday` | [`gcp/schema.sql:162`](../../../gcp/schema.sql#L162) |
| `market_data_intraday_spy` | partition of `market_data_intraday` | [`gcp/schema.sql:156`](../../../gcp/schema.sql#L156) |
| `model_routing` | table | [`gcp/schema.sql:1522`](../../../gcp/schema.sql#L1522) |
| `news_sentiment` | table | [`gcp/schema.sql:1632`](../../../gcp/schema.sql#L1632) |
| `options_daily_features` | table | [`gcp/schema.sql:285`](../../../gcp/schema.sql#L285) |
| `playbook_cards` | table | [`gcp/schema.sql:1381`](../../../gcp/schema.sql#L1381) |
| `playbook_cards_staging` | table | [`gcp/schema.sql:5138`](../../../gcp/schema.sql#L5138) |
| `premarket_analysis` | table | [`gcp/schema.sql:1327`](../../../gcp/schema.sql#L1327) |
| `premarket_analysis_history` | table | [`gcp/schema.sql:2010`](../../../gcp/schema.sql#L2010) |
| `ranker_runs` | table | [`gcp/schema.sql:1067`](../../../gcp/schema.sql#L1067) |
| `realtime_gex_15m` | table | [`gcp/schema.sql:462`](../../../gcp/schema.sql#L462) |
| `regime_combo_results` | table | [`gcp/schema.sql:4389`](../../../gcp/schema.sql#L4389) |
| `schema_apply_history` | table | [`gcp/schema.sql:5329`](../../../gcp/schema.sql#L5329) |
| `sec_filings` | table | [`gcp/schema.sql:959`](../../../gcp/schema.sql#L959) |
| `signal_alerts` | table | [`gcp/schema.sql:1085`](../../../gcp/schema.sql#L1085) |
| `signal_metrics` | table | [`gcp/schema.sql:3702`](../../../gcp/schema.sql#L3702) |
| `strat_combo_results` | table | [`gcp/schema.sql:4421`](../../../gcp/schema.sql#L4421) |
| `strat_levels` | table | [`gcp/schema.sql:1672`](../../../gcp/schema.sql#L1672) |
| `ticker_calibration` | table | [`gcp/schema.sql:3385`](../../../gcp/schema.sql#L3385) |
| `ticker_info` | table | [`gcp/schema.sql:2404`](../../../gcp/schema.sql#L2404) |
| `ticker_level_params` | table | [`gcp/schema.sql:2175`](../../../gcp/schema.sql#L2175) |
| `top_movers_daily` | table | [`gcp/schema.sql:1018`](../../../gcp/schema.sql#L1018) |
| `top_movers_intraday` | table | [`gcp/schema.sql:1042`](../../../gcp/schema.sql#L1042) |
| `trades` | table | [`gcp/schema.sql:1170`](../../../gcp/schema.sql#L1170) |
| `user_preferences` | table | [`gcp/schema.sql:5252`](../../../gcp/schema.sql#L5252) |
| `user_profile` | table | [`gcp/schema.sql:5283`](../../../gcp/schema.sql#L5283) |
| `user_roles` | table | [`gcp/schema.sql:5201`](../../../gcp/schema.sql#L5201) |
| `user_style_results` | table | [`gcp/schema.sql:5120`](../../../gcp/schema.sql#L5120) |
| `waitlist_signups` | table | [`gcp/schema.sql:5107`](../../../gcp/schema.sql#L5107) |
| `walk_forward_results` | table | [`gcp/schema.sql:4196`](../../../gcp/schema.sql#L4196) |
| `watchlist_history` | table | [`gcp/schema.sql:2672`](../../../gcp/schema.sql#L2672) |
| `watchlist_history_origin` | table | [`gcp/schema.sql:3278`](../../../gcp/schema.sql#L3278) |
| `watchlists` | table | [`gcp/schema.sql:2460`](../../../gcp/schema.sql#L2460) |
| `earnings_event_outcomes` | materialized view | [`gcp/schema.sql:4637`](../../../gcp/schema.sql#L4637) |
| `earnings_ticker_lean` | materialized view | [`gcp/schema.sql:4832`](../../../gcp/schema.sql#L4832) |
| `v_etf_options_node` | view | [`gcp/schema.sql:319`](../../../gcp/schema.sql#L319) |
<!-- inventory:tables:end -->

### 1b. Live relations, rows and sizes (2026-09-07)

<!-- inventory:dbtables:start -->
| Relation (live) | Rows (estimate; — for views) | Size | Declared in |
|---|---|---|---|
| `admin_refresh_leases` | 0 | 16 kB | `gcp/schema.sql` |
| `archive_yahoo_earnings_options_snapshots` | 0 | 24 kB | `gcp/schema.sql` |
| `archive_yahoo_etf_options_snapshots` | 0 | 40 kB | `gcp/schema.sql` |
| `archive_yahoo_market_data_daily` | 0 | 24 kB | `gcp/schema.sql` |
| `archive_yahoo_market_data_intraday` | 0 | 5920 kB | `gcp/schema.sql` |
| `backtest_reports` | 1 | 144 kB | `gcp/schema.sql` |
| `backtest_sweeps` | 45 | 96 kB | `gcp/schema.sql` |
| `backtest_trades` | 149,898 | 48 MB | `gcp/schema.sql` |
| `backtest_walk_forward_folds` | 0 | 496 kB | `gcp/schema.sql` |
| `daily_rates` | 2,916 | 424 kB | `gcp/schema.sql` |
| `daily_vex` | 218 | 936 kB | **runtime-created** (not in schema.sql) |
| `earnings_calendar` | 60,076 | 24 MB | `gcp/schema.sql` |
| `earnings_calibration` | 0 | 48 kB | `gcp/schema.sql` |
| `earnings_event_outcomes` | 0 | 24 kB | `gcp/schema.sql` (materialized view) |
| `earnings_history` | 132,353 | 41 MB | `gcp/schema.sql` |
| `earnings_options_snapshots` | 0 | 588 MB | `gcp/schema.sql` |
| `earnings_options_strategy_insights` | 0 | 104 kB | `gcp/schema.sql` |
| `earnings_options_strategy_winners` | 0 | 160 kB | `gcp/schema.sql` |
| `earnings_reactions` | 62,783 | 50 MB | `gcp/schema.sql` |
| `earnings_ticker_lean` | 0 | 32 kB | `gcp/schema.sql` (materialized view) |
| `earnings_upcoming_with_history` | 46,320 | 15 MB | `gcp/schema.sql` |
| `economic_events` | 2,981 | 648 kB | `gcp/schema.sql` |
| `etf_options_daily_greeks` | 8,042 | 976 kB | `gcp/schema.sql` |
| `etf_options_snapshots` | 141,113,379 | 74 GB | `gcp/schema.sql` |
| `exit_config_overrides` | 0 | 48 kB | `gcp/schema.sql` |
| `gamma_events` | 0 | 3456 kB | **runtime-created** (not in schema.sql) |
| `gamma_levels_eod` | 102,442 | 31 MB | **runtime-created** (not in schema.sql) |
| `historical_signals` | 96,376 | 3376 MB | `gcp/schema.sql` |
| `indicator_correlation` | 3,016 | 1512 kB | `gcp/schema.sql` |
| `insider_transactions` | 1,708,432 | 594 MB | `gcp/schema.sql` |
| `insight_reports` | 790 | 4384 kB | `gcp/schema.sql` |
| `insight_reports_history` | 846 | 3200 kB | `gcp/schema.sql` |
| `insight_runs` | 948 | 360 kB | `gcp/schema.sql` |
| `intraday_flow_15m` | 529,920 | 63 MB | `gcp/schema.sql` |
| `intraday_gex_15m` | 487,540 | 87 MB | `gcp/schema.sql` |
| `iwm_30m_predictions` | 0 | 352 kB | **runtime-created** (not in schema.sql) |
| `job_runs` | 14 | 48 kB | `gcp/schema.sql` |
| `journal_entries` | 2 | 1288 kB | `gcp/schema.sql` |
| `magnitude_per_bar_predictions` | 15,380 | 4584 kB | **runtime-created** (not in schema.sql) |
| `magnitude_walk_forward_results` | 1,695 | 1184 kB | **runtime-created** (not in schema.sql) |
| `market_data_cross_asset` | 0 | 16 kB | **runtime-created** (not in schema.sql) |
| `market_data_daily` | 5,553,479 | 3895 MB | `gcp/schema.sql` |
| `market_data_indicators` | 0 | 0 bytes | **runtime-created** (not in schema.sql) (partitioned table) |
| `market_data_indicators_iwm` | 0 | 2200 kB | **runtime-created** (not in schema.sql) |
| `market_data_indicators_other` | 0 | 16 kB | **runtime-created** (not in schema.sql) |
| `market_data_indicators_qqq` | 0 | 2224 kB | **runtime-created** (not in schema.sql) |
| `market_data_indicators_spy` | 0 | 2232 kB | **runtime-created** (not in schema.sql) |
| `market_data_intraday` | 0 | 0 bytes | `gcp/schema.sql` (partitioned table) |
| `market_data_intraday_iwm` | 2,006,813 | 512 MB | `gcp/schema.sql` |
| `market_data_intraday_other` | 5,653,650 | 67 GB | `gcp/schema.sql` |
| `market_data_intraday_qqq` | 2,281,849 | 585 MB | `gcp/schema.sql` |
| `market_data_intraday_spx` | 0 | 2144 kB | `gcp/schema.sql` |
| `market_data_intraday_spy` | 2,432,886 | 664 MB | `gcp/schema.sql` |
| `model_routing` | 0 | 24 kB | `gcp/schema.sql` |
| `news_sentiment` | 212,368 | 298 MB | `gcp/schema.sql` |
| `options_daily_features` | 8,042 | 1112 kB | `gcp/schema.sql` |
| `playbook_cards` | 72 | 144 kB | `gcp/schema.sql` |
| `playbook_cards_staging` | 0 | 16 kB | `gcp/schema.sql` |
| `premarket_analysis` | 383 | 1208 kB | `gcp/schema.sql` |
| `premarket_analysis_history` | 702 | 1664 kB | `gcp/schema.sql` |
| `qqq_30m_predictions` | 0 | 352 kB | **runtime-created** (not in schema.sql) |
| `ranker_runs` | 93 | 840 kB | `gcp/schema.sql` |
| `realtime_gex_15m` | 6,321 | 904 kB | `gcp/schema.sql` |
| `regime_combo_results` | 8,640 | 3872 kB | `gcp/schema.sql` |
| `sec_filings` | 4,274 | 1560 kB | `gcp/schema.sql` |
| `signal_alerts` | 3,011 | 2648 kB | `gcp/schema.sql` |
| `signal_metrics` | 179,485 | 58 MB | `gcp/schema.sql` |
| `spy_30m_predictions` | 0 | 352 kB | **runtime-created** (not in schema.sql) |
| `strat_combo_results` | 0 | 32 kB | `gcp/schema.sql` |
| `strat_features_15m` | 206,458 | 303 MB | **runtime-created** (not in schema.sql) |
| `strat_features_1m` | 3,105,422 | 4080 MB | **runtime-created** (not in schema.sql) |
| `strat_features_30m` | 103,261 | 152 MB | **runtime-created** (not in schema.sql) |
| `strat_features_4h` | 18,542 | 26 MB | **runtime-created** (not in schema.sql) |
| `strat_features_5m` | 587,853 | 811 MB | **runtime-created** (not in schema.sql) |
| `strat_features_60m` | 55,619 | 81 MB | **runtime-created** (not in schema.sql) |
| `strat_features_levels_15m` | 206,661 | 368 MB | **runtime-created** (not in schema.sql) |
| `strat_features_levels_1m` | 3,087,834 | 8155 MB | **runtime-created** (not in schema.sql) |
| `strat_features_levels_30m` | 103,261 | 184 MB | **runtime-created** (not in schema.sql) |
| `strat_features_levels_4h` | 18,542 | 28 MB | **runtime-created** (not in schema.sql) |
| `strat_features_levels_5m` | 617,241 | 1134 MB | **runtime-created** (not in schema.sql) |
| `strat_features_levels_60m` | 55,619 | 86 MB | **runtime-created** (not in schema.sql) |
| `strat_levels` | 13,889 | 3184 kB | `gcp/schema.sql` |
| `ticker_calibration` | 1 | 48 kB | `gcp/schema.sql` |
| `ticker_info` | 0 | 24 kB | `gcp/schema.sql` |
| `top_movers_daily` | 5,760 | 1128 kB | `gcp/schema.sql` |
| `top_movers_intraday` | 6,380 | 1152 kB | `gcp/schema.sql` |
| `trades` | 2,968 | 1360 kB | `gcp/schema.sql` |
| `user_preferences` | 1 | 32 kB | `gcp/schema.sql` |
| `user_profile` | 0 | 16 kB | `gcp/schema.sql` |
| `user_roles` | 2 | 48 kB | `gcp/schema.sql` |
| `user_style_results` | 0 | 24 kB | `gcp/schema.sql` |
| `v_etf_options_node` | — | 0 bytes | `gcp/schema.sql` (view) |
| `waitlist_signups` | 1 | 48 kB | `gcp/schema.sql` |
| `walk_forward_results` | 0 | 264 kB | `gcp/schema.sql` |
| `watchlists` | 0 | 64 kB | `gcp/schema.sql` |

Declared in `gcp/schema.sql` but absent live: `level_param_policy`, `schema_apply_history`, `ticker_level_params`, `watchlist_history`, `watchlist_history_origin`
<!-- inventory:dbtables:end -->

---

## 2. Write graph

A "write" is `upsert_dataframe` / `bulk_copy_upsert` / `bulk_insert_dataframe`, `INSERT INTO`, `UPDATE`, `DELETE FROM`, `to_sql`, `TRUNCATE`, `REFRESH MATERIALIZED VIEW` or `ON CONFLICT` within three lines of the table name, including through a module constant (`TABLE = "…"`). Writers under `scripts/` are one-shot or operator-run unless a Cloud Run Job's entrypoint names them (see §6).

<!-- inventory:writes:start -->
### `admin_refresh_leases`
- [`platform/api/routers/admin.py`](../../../platform/api/routers/admin.py) — line [1454](../../../platform/api/routers/admin.py#L1454), [1457](../../../platform/api/routers/admin.py#L1457), [1480](../../../platform/api/routers/admin.py#L1480)

### `archive_yahoo_earnings_options_snapshots`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_etf_options_snapshots`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_market_data_daily`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_market_data_intraday`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `backtest_reports`
- [`scripts/generate_backtest_report.py`](../../../scripts/generate_backtest_report.py) — line [387](../../../scripts/generate_backtest_report.py#L387)

### `backtest_sweeps`
- [`scripts/run_timeframe_sweep.py`](../../../scripts/run_timeframe_sweep.py) — line [65](../../../scripts/run_timeframe_sweep.py#L65)

### `backtest_trades`
- [`scripts/run_backtest.py`](../../../scripts/run_backtest.py) — line [78](../../../scripts/run_backtest.py#L78)

### `backtest_walk_forward_folds`
- [`scripts/run_walk_forward.py`](../../../scripts/run_walk_forward.py) — line [144](../../../scripts/run_walk_forward.py#L144)

### `daily_rates`
- [`gcp/fetchers/fetch_fred_rates.py`](../../../gcp/fetchers/fetch_fred_rates.py) — line [120](../../../gcp/fetchers/fetch_fred_rates.py#L120)

### `earnings_calendar`
- [`gcp/fetchers/evaluate_ew_strikes.py`](../../../gcp/fetchers/evaluate_ew_strikes.py) — line [280](../../../gcp/fetchers/evaluate_ew_strikes.py#L280), [296](../../../gcp/fetchers/evaluate_ew_strikes.py#L296)
- [`scripts/fetch_earnings_calendar.py`](../../../scripts/fetch_earnings_calendar.py) — line [948](../../../scripts/fetch_earnings_calendar.py#L948)

### `earnings_calibration`
- [`scripts/calibrate_earnings.py`](../../../scripts/calibrate_earnings.py) — line [156](../../../scripts/calibrate_earnings.py#L156)

### `earnings_event_outcomes`
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [113](../../../gcp/refresh_earnings_views.py#L113), [116](../../../gcp/refresh_earnings_views.py#L116)

### `earnings_history`
- [`gcp/fetchers/fetch_earnings_history.py`](../../../gcp/fetchers/fetch_earnings_history.py) — line [537](../../../gcp/fetchers/fetch_earnings_history.py#L537)

### `earnings_options_snapshots`
- [`gcp/fetchers/fetch_av_earnings_options_backfill.py`](../../../gcp/fetchers/fetch_av_earnings_options_backfill.py) — line [348](../../../gcp/fetchers/fetch_av_earnings_options_backfill.py#L348)
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [543](../../../gcp/migrate_to_gcp.py#L543)

### `earnings_options_strategy_insights`
- [`scripts/backtest_playability.py`](../../../scripts/backtest_playability.py) — line [997](../../../scripts/backtest_playability.py#L997)

### `earnings_options_strategy_winners`
- [`scripts/backtest_playability.py`](../../../scripts/backtest_playability.py) — line [1005](../../../scripts/backtest_playability.py#L1005)

### `earnings_reactions`
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../gcp/fetchers/compute_earnings_reactions.py) — line [867](../../../gcp/fetchers/compute_earnings_reactions.py#L867), [868](../../../gcp/fetchers/compute_earnings_reactions.py#L868), [1102](../../../gcp/fetchers/compute_earnings_reactions.py#L1102)

### `earnings_ticker_lean`
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [113](../../../gcp/refresh_earnings_views.py#L113), [116](../../../gcp/refresh_earnings_views.py#L116)

### `earnings_upcoming_with_history`
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [349](../../../gcp/refresh_earnings_views.py#L349), [351](../../../gcp/refresh_earnings_views.py#L351)

### `economic_events`
- [`gcp/fetchers/fetch_economic_events.py`](../../../gcp/fetchers/fetch_economic_events.py) — line [400](../../../gcp/fetchers/fetch_economic_events.py#L400)

### `etf_options_daily_greeks`
- [`gcp/build_options_daily_greeks.py`](../../../gcp/build_options_daily_greeks.py) — line [62](../../../gcp/build_options_daily_greeks.py#L62)

### `etf_options_snapshots`
- [`gcp/fetchers/_av_realtime_collector.py`](../../../gcp/fetchers/_av_realtime_collector.py) — line [539](../../../gcp/fetchers/_av_realtime_collector.py#L539)
- [`gcp/fetchers/fetch_av_historical_options.py`](../../../gcp/fetchers/fetch_av_historical_options.py) — line [163](../../../gcp/fetchers/fetch_av_historical_options.py#L163)
- [`gcp/fetchers/fetch_av_realtime_options.py`](../../../gcp/fetchers/fetch_av_realtime_options.py) — line [256](../../../gcp/fetchers/fetch_av_realtime_options.py#L256)
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [388](../../../gcp/migrate_to_gcp.py#L388), [447](../../../gcp/migrate_to_gcp.py#L447), [459](../../../gcp/migrate_to_gcp.py#L459), [500](../../../gcp/migrate_to_gcp.py#L500)
- [`gcp/options_retention_job.py`](../../../gcp/options_retention_job.py) — line [79](../../../gcp/options_retention_job.py#L79)
- [`platform/api/routers/grid.py`](../../../platform/api/routers/grid.py) — line [620](../../../platform/api/routers/grid.py#L620)
- [`scripts/maintenance/compute_spx_greeks.py`](../../../scripts/maintenance/compute_spx_greeks.py) — line [149](../../../scripts/maintenance/compute_spx_greeks.py#L149)

### `exit_config_overrides`
- [`scripts/run_param_sweep.py`](../../../scripts/run_param_sweep.py) — line [134](../../../scripts/run_param_sweep.py#L134)

### `historical_signals`
- [`gcp/historical_signals.py`](../../../gcp/historical_signals.py) — line [127](../../../gcp/historical_signals.py#L127), [130](../../../gcp/historical_signals.py#L130), [241](../../../gcp/historical_signals.py#L241)
- [`scripts/backfill_timeframe_tags.py`](../../../scripts/backfill_timeframe_tags.py) — line [194](../../../scripts/backfill_timeframe_tags.py#L194)

### `indicator_correlation`
- [`gcp/indicator_correlation_job.py`](../../../gcp/indicator_correlation_job.py) — line [734](../../../gcp/indicator_correlation_job.py#L734)

### `insider_transactions`
- [`gcp/fetchers/fetch_insider_transactions.py`](../../../gcp/fetchers/fetch_insider_transactions.py) — line [227](../../../gcp/fetchers/fetch_insider_transactions.py#L227)

### `insight_reports`
- [`gcp/insight_pipeline_job.py`](../../../gcp/insight_pipeline_job.py) — line [391](../../../gcp/insight_pipeline_job.py#L391), [428](../../../gcp/insight_pipeline_job.py#L428)
- [`platform/api/routers/insights.py`](../../../platform/api/routers/insights.py) — line [429](../../../platform/api/routers/insights.py#L429)
- [`scripts/generate_historical_report.py`](../../../scripts/generate_historical_report.py) — line [72](../../../scripts/generate_historical_report.py#L72)

### `insight_reports_history`
- [`gcp/insight_pipeline_job.py`](../../../gcp/insight_pipeline_job.py) — line [329](../../../gcp/insight_pipeline_job.py#L329)
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [169](../../../scripts/backfill_history_tables.py#L169)

### `insight_runs`
- [`gcp/auto_refresh_top_n.py`](../../../gcp/auto_refresh_top_n.py) — line [123](../../../gcp/auto_refresh_top_n.py#L123), [150](../../../gcp/auto_refresh_top_n.py#L150)
- [`gcp/discord_interactions/main.py`](../../../gcp/discord_interactions/main.py) — line [377](../../../gcp/discord_interactions/main.py#L377)
- [`gcp/insight_pipeline_job.py`](../../../gcp/insight_pipeline_job.py) — line [202](../../../gcp/insight_pipeline_job.py#L202), [248](../../../gcp/insight_pipeline_job.py#L248), [258](../../../gcp/insight_pipeline_job.py#L258), [267](../../../gcp/insight_pipeline_job.py#L267)
- [`platform/api/routers/insights.py`](../../../platform/api/routers/insights.py) — line [332](../../../platform/api/routers/insights.py#L332), [385](../../../platform/api/routers/insights.py#L385), [391](../../../platform/api/routers/insights.py#L391), [400](../../../platform/api/routers/insights.py#L400)

### `intraday_flow_15m`
- [`gcp/build_intraday_flow.py`](../../../gcp/build_intraday_flow.py) — line [73](../../../gcp/build_intraday_flow.py#L73)

### `intraday_gex_15m`
- [`gcp/build_intraday_gex.py`](../../../gcp/build_intraday_gex.py) — line [187](../../../gcp/build_intraday_gex.py#L187)

### `job_runs`
- [`gcp/database.py`](../../../gcp/database.py) — line [1125](../../../gcp/database.py#L1125)

### `journal_entries`
- [`platform/api/routers/journal.py`](../../../platform/api/routers/journal.py) — line [685](../../../platform/api/routers/journal.py#L685), [1205](../../../platform/api/routers/journal.py#L1205), [1260](../../../platform/api/routers/journal.py#L1260)
- [`scripts/backfill_journal_embeddings.py`](../../../scripts/backfill_journal_embeddings.py) — line [79](../../../scripts/backfill_journal_embeddings.py#L79)

### `level_param_policy`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `market_data_daily`
- [`gcp/backfill_ticker.py`](../../../gcp/backfill_ticker.py) — line [415](../../../gcp/backfill_ticker.py#L415), [561](../../../gcp/backfill_ticker.py#L561), [630](../../../gcp/backfill_ticker.py#L630)
- [`gcp/fetchers/backfill_daily_indicators.py`](../../../gcp/fetchers/backfill_daily_indicators.py) — line [415](../../../gcp/fetchers/backfill_daily_indicators.py#L415)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [546](../../../gcp/fetchers/fetch_market_data.py#L546), [621](../../../gcp/fetchers/fetch_market_data.py#L621), [670](../../../gcp/fetchers/fetch_market_data.py#L670), [1050](../../../gcp/fetchers/fetch_market_data.py#L1050)
- [`gcp/fetchers/fetch_premarket_refresh.py`](../../../gcp/fetchers/fetch_premarket_refresh.py) — line [354](../../../gcp/fetchers/fetch_premarket_refresh.py#L354)
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [187](../../../gcp/migrate_to_gcp.py#L187), [676](../../../gcp/migrate_to_gcp.py#L676)
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [266](../../../gcp/premarket_brief.py#L266)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [236](../../../scripts/backfill_watchlist_data.py#L236)
- [`scripts/deep_backfill_ticker.py`](../../../scripts/deep_backfill_ticker.py) — line [102](../../../scripts/deep_backfill_ticker.py#L102)

### `market_data_intraday`
- [`gcp/backfill_ticker.py`](../../../gcp/backfill_ticker.py) — line [653](../../../gcp/backfill_ticker.py#L653)
- [`gcp/fetchers/fetch_alphavantage_intraday.py`](../../../gcp/fetchers/fetch_alphavantage_intraday.py) — line [321](../../../gcp/fetchers/fetch_alphavantage_intraday.py#L321)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [573](../../../gcp/fetchers/fetch_market_data.py#L573)
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [249](../../../gcp/migrate_to_gcp.py#L249), [252](../../../gcp/migrate_to_gcp.py#L252)

### `market_data_intraday_iwm`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_other`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_qqq`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_spx`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_spy`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `model_routing`
- [`lib/agents/model_routing.py`](../../../lib/agents/model_routing.py) — line [193](../../../lib/agents/model_routing.py#L193)

### `news_sentiment`
- [`gcp/backfill_ticker.py`](../../../gcp/backfill_ticker.py) — line [666](../../../gcp/backfill_ticker.py#L666)
- [`gcp/fetchers/fetch_news_sentiment.py`](../../../gcp/fetchers/fetch_news_sentiment.py) — line [375](../../../gcp/fetchers/fetch_news_sentiment.py#L375)
- [`gcp/fetchers/fetch_rss_news.py`](../../../gcp/fetchers/fetch_rss_news.py) — line [710](../../../gcp/fetchers/fetch_rss_news.py#L710)
- [`scripts/backfill_news_sentiment.py`](../../../scripts/backfill_news_sentiment.py) — line [101](../../../scripts/backfill_news_sentiment.py#L101)

### `options_daily_features`
- [`lib/features/experimental/options_derived.py`](../../../lib/features/experimental/options_derived.py) — line [396](../../../lib/features/experimental/options_derived.py#L396)

### `playbook_cards`
- [`scripts/analysis/phase6_playbook.py`](../../../scripts/analysis/phase6_playbook.py) — line [990](../../../scripts/analysis/phase6_playbook.py#L990)

### `playbook_cards_staging`
- [`platform/api/routers/backtest.py`](../../../platform/api/routers/backtest.py) — line [875](../../../platform/api/routers/backtest.py#L875)

### `premarket_analysis`
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [3212](../../../gcp/premarket_brief.py#L3212), [3239](../../../gcp/premarket_brief.py#L3239)
- [`gcp/premarket_playbook_resolver.py`](../../../gcp/premarket_playbook_resolver.py) — line [603](../../../gcp/premarket_playbook_resolver.py#L603)
- [`gcp/signal_monitor.py`](../../../gcp/signal_monitor.py) — line [573](../../../gcp/signal_monitor.py#L573)

### `premarket_analysis_history`
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [3175](../../../gcp/premarket_brief.py#L3175)
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [123](../../../scripts/backfill_history_tables.py#L123)

### `ranker_runs`
- [`lib/agents/ranker/rank.py`](../../../lib/agents/ranker/rank.py) — line [158](../../../lib/agents/ranker/rank.py#L158)

### `realtime_gex_15m`
- [`gcp/build_realtime_gex.py`](../../../gcp/build_realtime_gex.py) — line [135](../../../gcp/build_realtime_gex.py#L135)

### `regime_combo_results`
- [`gcp/regime_combo_job.py`](../../../gcp/regime_combo_job.py) — line [189](../../../gcp/regime_combo_job.py#L189)

### `schema_apply_history`
- [`gcp/apply_schema.py`](../../../gcp/apply_schema.py) — line [267](../../../gcp/apply_schema.py#L267), [485](../../../gcp/apply_schema.py#L485)

### `sec_filings`
- [`gcp/fetchers/fetch_sec_filings.py`](../../../gcp/fetchers/fetch_sec_filings.py) — line [581](../../../gcp/fetchers/fetch_sec_filings.py#L581)

### `signal_alerts`
- [`gcp/signal_monitor.py`](../../../gcp/signal_monitor.py) — line [1814](../../../gcp/signal_monitor.py#L1814), [2463](../../../gcp/signal_monitor.py#L2463)
- [`gcp/signal_monitor_eod_resolver.py`](../../../gcp/signal_monitor_eod_resolver.py) — line [402](../../../gcp/signal_monitor_eod_resolver.py#L402)
- [`scripts/replay_signal_monitor.py`](../../../scripts/replay_signal_monitor.py) — line [552](../../../scripts/replay_signal_monitor.py#L552)

### `signal_metrics`
- [`scripts/signal_quality_report.py`](../../../scripts/signal_quality_report.py) — line [576](../../../scripts/signal_quality_report.py#L576)

### `strat_combo_results`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `strat_levels`
- [`lib/strat_levels.py`](../../../lib/strat_levels.py) — line [2822](../../../lib/strat_levels.py#L2822)

### `ticker_calibration`
- [`scripts/calibrate_thresholds.py`](../../../scripts/calibrate_thresholds.py) — line [497](../../../scripts/calibrate_thresholds.py#L497)

### `ticker_info`
- [`lib/ticker_info.py`](../../../lib/ticker_info.py) — line [66](../../../lib/ticker_info.py#L66), [629](../../../lib/ticker_info.py#L629)

### `ticker_level_params`
- [`gcp/calibrate_level_params.py`](../../../gcp/calibrate_level_params.py) — line [113](../../../gcp/calibrate_level_params.py#L113)

### `top_movers_daily`
- [`gcp/fetchers/fetch_top_movers.py`](../../../gcp/fetchers/fetch_top_movers.py) — line [291](../../../gcp/fetchers/fetch_top_movers.py#L291)

### `top_movers_intraday`
- [`gcp/fetchers/fetch_top_movers.py`](../../../gcp/fetchers/fetch_top_movers.py) — line [261](../../../gcp/fetchers/fetch_top_movers.py#L261)

### `trades`
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [756](../../../gcp/migrate_to_gcp.py#L756)
- [`gcp/signal_monitor.py`](../../../gcp/signal_monitor.py) — line [2478](../../../gcp/signal_monitor.py#L2478)
- [`gcp/signal_monitor_eod_resolver.py`](../../../gcp/signal_monitor_eod_resolver.py) — line [416](../../../gcp/signal_monitor_eod_resolver.py#L416)
- [`gcp/trade_logger.py`](../../../gcp/trade_logger.py) — line [97](../../../gcp/trade_logger.py#L97), [100](../../../gcp/trade_logger.py#L100)

### `user_preferences`
- [`platform/api/routers/preferences.py`](../../../platform/api/routers/preferences.py) — line [175](../../../platform/api/routers/preferences.py#L175)

### `user_profile`
- [`platform/api/routers/profile.py`](../../../platform/api/routers/profile.py) — line [187](../../../platform/api/routers/profile.py#L187)

### `user_roles`
- [`platform/api/routers/admin.py`](../../../platform/api/routers/admin.py) — line [1111](../../../platform/api/routers/admin.py#L1111), [1124](../../../platform/api/routers/admin.py#L1124)

### `user_style_results`
- [`platform/api/routers/backtest.py`](../../../platform/api/routers/backtest.py) — line [845](../../../platform/api/routers/backtest.py#L845)

### `v_etf_options_node`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `waitlist_signups`
- [`platform/api/routers/waitlist.py`](../../../platform/api/routers/waitlist.py) — line [111](../../../platform/api/routers/waitlist.py#L111)

### `walk_forward_results`
- [`scripts/run_param_sweep.py`](../../../scripts/run_param_sweep.py) — line [108](../../../scripts/run_param_sweep.py#L108)

### `watchlist_history`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `watchlist_history_origin`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `watchlists`
- [`gcp/backfill_ticker.py`](../../../gcp/backfill_ticker.py) — line [328](../../../gcp/backfill_ticker.py#L328), [332](../../../gcp/backfill_ticker.py#L332)
- [`gcp/discord_interactions/main.py`](../../../gcp/discord_interactions/main.py) — line [655](../../../gcp/discord_interactions/main.py#L655), [691](../../../gcp/discord_interactions/main.py#L691)
- [`gcp/fetchers/_watchlist.py`](../../../gcp/fetchers/_watchlist.py) — line [539](../../../gcp/fetchers/_watchlist.py#L539), [543](../../../gcp/fetchers/_watchlist.py#L543), [544](../../../gcp/fetchers/_watchlist.py#L544), [576](../../../gcp/fetchers/_watchlist.py#L576)
<!-- inventory:writes:end -->

---

## 3. Read graph

A "read" is `SELECT`, `FROM`, `JOIN`, `query_to_dataframe`, `read_sql` or `row_exists` within three lines of the table name. Tests are excluded.

<!-- inventory:reads:start -->
### `admin_refresh_leases`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_earnings_options_snapshots`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_etf_options_snapshots`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_market_data_daily`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_market_data_intraday`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `backtest_reports`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `backtest_sweeps`
- [`scripts/generate_backtest_report.py`](../../../scripts/generate_backtest_report.py) — line [175](../../../scripts/generate_backtest_report.py#L175), [181](../../../scripts/generate_backtest_report.py#L181), [184](../../../scripts/generate_backtest_report.py#L184)

### `backtest_trades`
- [`scripts/generate_backtest_report.py`](../../../scripts/generate_backtest_report.py) — line [141](../../../scripts/generate_backtest_report.py#L141), [150](../../../scripts/generate_backtest_report.py#L150), [153](../../../scripts/generate_backtest_report.py#L153)

### `backtest_walk_forward_folds`
- [`scripts/calibrate_iwm_strat.py`](../../../scripts/calibrate_iwm_strat.py) — line [199](../../../scripts/calibrate_iwm_strat.py#L199)
- [`scripts/generate_backtest_report.py`](../../../scripts/generate_backtest_report.py) — line [214](../../../scripts/generate_backtest_report.py#L214), [221](../../../scripts/generate_backtest_report.py#L221), [224](../../../scripts/generate_backtest_report.py#L224)

### `daily_rates`
- [`lib/options_exec_backtest/runner.py`](../../../lib/options_exec_backtest/runner.py) — line [207](../../../lib/options_exec_backtest/runner.py#L207)
- [`lib/options_greeks.py`](../../../lib/options_greeks.py) — line [196](../../../lib/options_greeks.py#L196), [202](../../../lib/options_greeks.py#L202)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)

### `earnings_calendar`
- [`gcp/earnings_long_watchlist.py`](../../../gcp/earnings_long_watchlist.py) — line [151](../../../gcp/earnings_long_watchlist.py#L151)
- [`gcp/earnings_reactions_brief.py`](../../../gcp/earnings_reactions_brief.py) — line [293](../../../gcp/earnings_reactions_brief.py#L293)
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../gcp/fetchers/compute_earnings_reactions.py) — line [580](../../../gcp/fetchers/compute_earnings_reactions.py#L580), [922](../../../gcp/fetchers/compute_earnings_reactions.py#L922)
- [`gcp/fetchers/evaluate_ew_strikes.py`](../../../gcp/fetchers/evaluate_ew_strikes.py) — line [355](../../../gcp/fetchers/evaluate_ew_strikes.py#L355)
- [`gcp/fetchers/fetch_earnings_history.py`](../../../gcp/fetchers/fetch_earnings_history.py) — line [252](../../../gcp/fetchers/fetch_earnings_history.py#L252), [296](../../../gcp/fetchers/fetch_earnings_history.py#L296)
- [`gcp/fetchers/fetch_insider_transactions.py`](../../../gcp/fetchers/fetch_insider_transactions.py) — line [127](../../../gcp/fetchers/fetch_insider_transactions.py#L127)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [739](../../../gcp/fetchers/fetch_market_data.py#L739), [842](../../../gcp/fetchers/fetch_market_data.py#L842)
- [`gcp/fetchers/fetch_news_sentiment.py`](../../../gcp/fetchers/fetch_news_sentiment.py) — line [163](../../../gcp/fetchers/fetch_news_sentiment.py#L163)
- [`gcp/fetchers/fetch_premarket_refresh.py`](../../../gcp/fetchers/fetch_premarket_refresh.py) — line [87](../../../gcp/fetchers/fetch_premarket_refresh.py#L87), [112](../../../gcp/fetchers/fetch_premarket_refresh.py#L112)
- [`gcp/fetchers/fetch_sec_filings.py`](../../../gcp/fetchers/fetch_sec_filings.py) — line [428](../../../gcp/fetchers/fetch_sec_filings.py#L428)
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [369](../../../gcp/premarket_brief.py#L369), [723](../../../gcp/premarket_brief.py#L723)
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [163](../../../gcp/refresh_earnings_views.py#L163)
- [`lib/agents/ranker/candidates.py`](../../../lib/agents/ranker/candidates.py) — line [91](../../../lib/agents/ranker/candidates.py#L91)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [1707](../../../lib/agents/summarizers.py#L1707)
- [`lib/strategies/catalyst_proximity.py`](../../../lib/strategies/catalyst_proximity.py) — line [235](../../../lib/strategies/catalyst_proximity.py#L235)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [476](../../../platform/api/routers/catalysts.py#L476), [758](../../../platform/api/routers/catalysts.py#L758)
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [131](../../../platform/api/routers/earnings.py#L131)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/fetch_earnings_calendar.py`](../../../scripts/fetch_earnings_calendar.py) — line [344](../../../scripts/fetch_earnings_calendar.py#L344)

### `earnings_calibration`
- [`lib/earnings_reactions.py`](../../../lib/earnings_reactions.py) — line [107](../../../lib/earnings_reactions.py#L107), [434](../../../lib/earnings_reactions.py#L434)
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [327](../../../platform/api/routers/earnings.py#L327)

### `earnings_event_outcomes`
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [204](../../../gcp/refresh_earnings_views.py#L204)
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [171](../../../platform/api/routers/earnings.py#L171), [196](../../../platform/api/routers/earnings.py#L196)

### `earnings_history`
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../gcp/fetchers/compute_earnings_reactions.py) — line [559](../../../gcp/fetchers/compute_earnings_reactions.py#L559), [897](../../../gcp/fetchers/compute_earnings_reactions.py#L897)
- [`gcp/fetchers/fetch_earnings_history.py`](../../../gcp/fetchers/fetch_earnings_history.py) — line [331](../../../gcp/fetchers/fetch_earnings_history.py#L331), [373](../../../gcp/fetchers/fetch_earnings_history.py#L373)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [824](../../../gcp/fetchers/fetch_market_data.py#L824), [850](../../../gcp/fetchers/fetch_market_data.py#L850)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [356](../../../lib/agents/ranker/signals.py#L356)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [773](../../../platform/api/routers/catalysts.py#L773)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [141](../../../scripts/backfill_watchlist_data.py#L141)

### `earnings_options_snapshots`
- [`gcp/fetchers/fetch_av_earnings_options_backfill.py`](../../../gcp/fetchers/fetch_av_earnings_options_backfill.py) — line [189](../../../gcp/fetchers/fetch_av_earnings_options_backfill.py#L189)
- [`lib/data_loader.py`](../../../lib/data_loader.py) — line [792](../../../lib/data_loader.py#L792), [793](../../../lib/data_loader.py#L793)
- [`scripts/backtest_playability.py`](../../../scripts/backtest_playability.py) — line [551](../../../scripts/backtest_playability.py#L551)

### `earnings_options_strategy_insights`
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [281](../../../platform/api/routers/earnings.py#L281), [288](../../../platform/api/routers/earnings.py#L288)

### `earnings_options_strategy_winners`
- [`gcp/earnings_long_watchlist.py`](../../../gcp/earnings_long_watchlist.py) — line [101](../../../gcp/earnings_long_watchlist.py#L101), [132](../../../gcp/earnings_long_watchlist.py#L132), [138](../../../gcp/earnings_long_watchlist.py#L138)
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [306](../../../platform/api/routers/earnings.py#L306), [313](../../../platform/api/routers/earnings.py#L313)

### `earnings_reactions`
- [`gcp/earnings_reactions_brief.py`](../../../gcp/earnings_reactions_brief.py) — line [332](../../../gcp/earnings_reactions_brief.py#L332), [395](../../../gcp/earnings_reactions_brief.py#L395)
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../gcp/fetchers/compute_earnings_reactions.py) — line [962](../../../gcp/fetchers/compute_earnings_reactions.py#L962)
- [`gcp/fetchers/fetch_av_earnings_options_backfill.py`](../../../gcp/fetchers/fetch_av_earnings_options_backfill.py) — line [232](../../../gcp/fetchers/fetch_av_earnings_options_backfill.py#L232)
- [`lib/earnings_reactions.py`](../../../lib/earnings_reactions.py) — line [540](../../../lib/earnings_reactions.py#L540), [704](../../../lib/earnings_reactions.py#L704)
- [`scripts/backtest_playability.py`](../../../scripts/backtest_playability.py) — line [77](../../../scripts/backtest_playability.py#L77)

### `earnings_ticker_lean`
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [183](../../../gcp/refresh_earnings_views.py#L183)
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [237](../../../platform/api/routers/earnings.py#L237), [256](../../../platform/api/routers/earnings.py#L256)

### `earnings_upcoming_with_history`
- [`platform/api/routers/earnings.py`](../../../platform/api/routers/earnings.py) — line [125](../../../platform/api/routers/earnings.py#L125), [127](../../../platform/api/routers/earnings.py#L127)

### `economic_events`
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [801](../../../gcp/premarket_brief.py#L801)
- [`gcp/research/magnitude_engine/mag_dataset.py`](../../../gcp/research/magnitude_engine/mag_dataset.py) — line [133](../../../gcp/research/magnitude_engine/mag_dataset.py#L133)
- [`lib/agents/ranker/candidates.py`](../../../lib/agents/ranker/candidates.py) — line [198](../../../lib/agents/ranker/candidates.py#L198)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [1698](../../../lib/agents/summarizers.py#L1698)
- [`lib/strategies/catalyst_proximity.py`](../../../lib/strategies/catalyst_proximity.py) — line [195](../../../lib/strategies/catalyst_proximity.py#L195)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [444](../../../platform/api/routers/catalysts.py#L444)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/check_event_window_concentration.py`](../../../scripts/check_event_window_concentration.py) — line [61](../../../scripts/check_event_window_concentration.py#L61)

### `etf_options_daily_greeks`
- [`lib/features/flow_direction.py`](../../../lib/features/flow_direction.py) — line [516](../../../lib/features/flow_direction.py#L516)

### `etf_options_snapshots`
- [`gcp/build_intraday_gex.py`](../../../gcp/build_intraday_gex.py) — line [62](../../../gcp/build_intraday_gex.py#L62)
- [`gcp/build_realtime_gex.py`](../../../gcp/build_realtime_gex.py) — line [64](../../../gcp/build_realtime_gex.py#L64)
- [`gcp/fetchers/fetch_av_historical_options.py`](../../../gcp/fetchers/fetch_av_historical_options.py) — line [135](../../../gcp/fetchers/fetch_av_historical_options.py#L135), [218](../../../gcp/fetchers/fetch_av_historical_options.py#L218)
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [312](../../../gcp/migrate_to_gcp.py#L312)
- [`gcp/options_retention_job.py`](../../../gcp/options_retention_job.py) — line [65](../../../gcp/options_retention_job.py#L65), [68](../../../gcp/options_retention_job.py#L68), [73](../../../gcp/options_retention_job.py#L73), [75](../../../gcp/options_retention_job.py#L75)
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [171](../../../gcp/premarket_brief.py#L171), [198](../../../gcp/premarket_brief.py#L198)
- [`gcp/research/p2_build_gamma_levels.py`](../../../gcp/research/p2_build_gamma_levels.py) — line [127](../../../gcp/research/p2_build_gamma_levels.py#L127)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../gcp/research/p7_build_multi_tf_features.py) — line [162](../../../gcp/research/p7_build_multi_tf_features.py#L162)
- [`gcp/research/strat_engine/breakout_meta_walk_forward.py`](../../../gcp/research/strat_engine/breakout_meta_walk_forward.py) — line [118](../../../gcp/research/strat_engine/breakout_meta_walk_forward.py#L118), [125](../../../gcp/research/strat_engine/breakout_meta_walk_forward.py#L125)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../gcp/research/strat_engine/strat_data_builder.py) — line [266](../../../gcp/research/strat_engine/strat_data_builder.py#L266)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [113](../../../lib/agents/ranker/signals.py#L113), [117](../../../lib/agents/ranker/signals.py#L117)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [677](../../../lib/agents/summarizers.py#L677), [682](../../../lib/agents/summarizers.py#L682), [803](../../../lib/agents/summarizers.py#L803), [809](../../../lib/agents/summarizers.py#L809), [830](../../../lib/agents/summarizers.py#L830), [836](../../../lib/agents/summarizers.py#L836)
- [`lib/data_loader.py`](../../../lib/data_loader.py) — line [792](../../../lib/data_loader.py#L792), [793](../../../lib/data_loader.py#L793)
- [`lib/features/experimental/options_derived.py`](../../../lib/features/experimental/options_derived.py) — line [67](../../../lib/features/experimental/options_derived.py#L67), [115](../../../lib/features/experimental/options_derived.py#L115)
- [`lib/features/flow_direction.py`](../../../lib/features/flow_direction.py) — line [408](../../../lib/features/flow_direction.py#L408), [445](../../../lib/features/flow_direction.py#L445)
- [`lib/options_exec_backtest/iv_lookup.py`](../../../lib/options_exec_backtest/iv_lookup.py) — line [127](../../../lib/options_exec_backtest/iv_lookup.py#L127)
- [`lib/options_intraday.py`](../../../lib/options_intraday.py) — line [166](../../../lib/options_intraday.py#L166)
- [`platform/api/routers/grid.py`](../../../platform/api/routers/grid.py) — line [264](../../../platform/api/routers/grid.py#L264), [270](../../../platform/api/routers/grid.py#L270), [295](../../../platform/api/routers/grid.py#L295), [301](../../../platform/api/routers/grid.py#L301), [343](../../../platform/api/routers/grid.py#L343), [349](../../../platform/api/routers/grid.py#L349), [1205](../../../platform/api/routers/grid.py#L1205)
- [`platform/api/routers/options.py`](../../../platform/api/routers/options.py) — line [356](../../../platform/api/routers/options.py#L356), [458](../../../platform/api/routers/options.py#L458), [464](../../../platform/api/routers/options.py#L464), [581](../../../platform/api/routers/options.py#L581), [587](../../../platform/api/routers/options.py#L587), [600](../../../platform/api/routers/options.py#L600)
- [`scripts/analysis/calibrate_intraday_theta.py`](../../../scripts/analysis/calibrate_intraday_theta.py) — line [52](../../../scripts/analysis/calibrate_intraday_theta.py#L52)
- [`scripts/analysis/options_pnl_translation.py`](../../../scripts/analysis/options_pnl_translation.py) — line [258](../../../scripts/analysis/options_pnl_translation.py#L258), [359](../../../scripts/analysis/options_pnl_translation.py#L359)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [1137](../../../scripts/audit_data_freshness.py#L1137), [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [125](../../../scripts/backfill_watchlist_data.py#L125)
- [`scripts/implied_vs_realized_check.py`](../../../scripts/implied_vs_realized_check.py) — line [118](../../../scripts/implied_vs_realized_check.py#L118), [133](../../../scripts/implied_vs_realized_check.py#L133)
- [`scripts/maintenance/compute_spx_greeks.py`](../../../scripts/maintenance/compute_spx_greeks.py) — line [91](../../../scripts/maintenance/compute_spx_greeks.py#L91), [101](../../../scripts/maintenance/compute_spx_greeks.py#L101), [121](../../../scripts/maintenance/compute_spx_greeks.py#L121)

### `exit_config_overrides`
- [`lib/strategies/exit_config_overrides.py`](../../../lib/strategies/exit_config_overrides.py) — line [124](../../../lib/strategies/exit_config_overrides.py#L124)
- [`scripts/run_param_sweep.py`](../../../scripts/run_param_sweep.py) — line [143](../../../scripts/run_param_sweep.py#L143)

### `historical_signals`
- [`gcp/historical_signals.py`](../../../gcp/historical_signals.py) — line [108](../../../gcp/historical_signals.py#L108), [111](../../../gcp/historical_signals.py#L111)
- [`platform/api/routers/signals.py`](../../../platform/api/routers/signals.py) — line [205](../../../platform/api/routers/signals.py#L205), [232](../../../platform/api/routers/signals.py#L232), [576](../../../platform/api/routers/signals.py#L576), [621](../../../platform/api/routers/signals.py#L621)
- [`scripts/analyze_timeframe_heuristic.py`](../../../scripts/analyze_timeframe_heuristic.py) — line [322](../../../scripts/analyze_timeframe_heuristic.py#L322)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/backfill_timeframe_tags.py`](../../../scripts/backfill_timeframe_tags.py) — line [84](../../../scripts/backfill_timeframe_tags.py#L84)
- [`scripts/signal_quality_report.py`](../../../scripts/signal_quality_report.py) — line [418](../../../scripts/signal_quality_report.py#L418), [425](../../../scripts/signal_quality_report.py#L425), [445](../../../scripts/signal_quality_report.py#L445)

### `indicator_correlation`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `insider_transactions`
- [`gcp/earnings_reactions_brief.py`](../../../gcp/earnings_reactions_brief.py) — line [469](../../../gcp/earnings_reactions_brief.py#L469)
- [`lib/agents/ranker/candidates.py`](../../../lib/agents/ranker/candidates.py) — line [147](../../../lib/agents/ranker/candidates.py#L147)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [422](../../../lib/agents/ranker/signals.py#L422)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [526](../../../platform/api/routers/catalysts.py#L526), [745](../../../platform/api/routers/catalysts.py#L745)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [148](../../../scripts/backfill_watchlist_data.py#L148)

### `insight_reports`
- [`gcp/auto_refresh_top_n.py`](../../../gcp/auto_refresh_top_n.py) — line [90](../../../gcp/auto_refresh_top_n.py#L90)
- [`gcp/discord_interactions/main.py`](../../../gcp/discord_interactions/main.py) — line [357](../../../gcp/discord_interactions/main.py#L357)
- [`gcp/insight_discord_push.py`](../../../gcp/insight_discord_push.py) — line [86](../../../gcp/insight_discord_push.py#L86), [97](../../../gcp/insight_discord_push.py#L97)
- [`gcp/insight_pipeline_job.py`](../../../gcp/insight_pipeline_job.py) — line [467](../../../gcp/insight_pipeline_job.py#L467)
- [`lib/strategies/insight_cache.py`](../../../lib/strategies/insight_cache.py) — line [284](../../../lib/strategies/insight_cache.py#L284)
- [`platform/api/routers/insights.py`](../../../platform/api/routers/insights.py) — line [227](../../../platform/api/routers/insights.py#L227), [239](../../../platform/api/routers/insights.py#L239), [260](../../../platform/api/routers/insights.py#L260), [301](../../../platform/api/routers/insights.py#L301)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/backfill_and_replay.py`](../../../scripts/backfill_and_replay.py) — line [247](../../../scripts/backfill_and_replay.py#L247)
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [154](../../../scripts/backfill_history_tables.py#L154), [188](../../../scripts/backfill_history_tables.py#L188), [189](../../../scripts/backfill_history_tables.py#L189)
- [`scripts/validation/validate_brief_accuracy.py`](../../../scripts/validation/validate_brief_accuracy.py) — line [380](../../../scripts/validation/validate_brief_accuracy.py#L380)

### `insight_reports_history`
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [159](../../../scripts/backfill_history_tables.py#L159)

### `insight_runs`
- [`platform/api/routers/insights.py`](../../../platform/api/routers/insights.py) — line [351](../../../platform/api/routers/insights.py#L351)
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [174](../../../scripts/backfill_history_tables.py#L174)

### `intraday_flow_15m`
- [`gcp/build_intraday_flow.py`](../../../gcp/build_intraday_flow.py) — line [92](../../../gcp/build_intraday_flow.py#L92)
- [`lib/features/intraday_flow.py`](../../../lib/features/intraday_flow.py) — line [186](../../../lib/features/intraday_flow.py#L186)

### `intraday_gex_15m`
- [`gcp/build_intraday_gex.py`](../../../gcp/build_intraday_gex.py) — line [199](../../../gcp/build_intraday_gex.py#L199)
- [`lib/features/intraday_gex.py`](../../../lib/features/intraday_gex.py) — line [231](../../../lib/features/intraday_gex.py#L231)

### `job_runs`
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [1342](../../../scripts/audit_data_freshness.py#L1342)

### `journal_entries`
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [1992](../../../lib/agents/summarizers.py#L1992)
- [`platform/api/routers/backtest.py`](../../../platform/api/routers/backtest.py) — line [545](../../../platform/api/routers/backtest.py#L545), [717](../../../platform/api/routers/backtest.py#L717)
- [`platform/api/routers/journal.py`](../../../platform/api/routers/journal.py) — line [862](../../../platform/api/routers/journal.py#L862), [899](../../../platform/api/routers/journal.py#L899), [994](../../../platform/api/routers/journal.py#L994), [1182](../../../platform/api/routers/journal.py#L1182)
- [`scripts/backfill_journal_embeddings.py`](../../../scripts/backfill_journal_embeddings.py) — line [59](../../../scripts/backfill_journal_embeddings.py#L59)

### `level_param_policy`
- [`gcp/calibrate_level_params.py`](../../../gcp/calibrate_level_params.py) — line [75](../../../gcp/calibrate_level_params.py#L75)
- [`lib/strat_levels.py`](../../../lib/strat_levels.py) — line [1206](../../../lib/strat_levels.py#L1206)

### `market_data_daily`
- [`gcp/backfill_ticker.py`](../../../gcp/backfill_ticker.py) — line [374](../../../gcp/backfill_ticker.py#L374), [442](../../../gcp/backfill_ticker.py#L442)
- [`gcp/build_intraday_gex.py`](../../../gcp/build_intraday_gex.py) — line [80](../../../gcp/build_intraday_gex.py#L80)
- [`gcp/calibrate_level_params.py`](../../../gcp/calibrate_level_params.py) — line [79](../../../gcp/calibrate_level_params.py#L79)
- [`gcp/discord_interactions/main.py`](../../../gcp/discord_interactions/main.py) — line [332](../../../gcp/discord_interactions/main.py#L332)
- [`gcp/fetchers/backfill_daily_indicators.py`](../../../gcp/fetchers/backfill_daily_indicators.py) — line [117](../../../gcp/fetchers/backfill_daily_indicators.py#L117), [216](../../../gcp/fetchers/backfill_daily_indicators.py#L216), [222](../../../gcp/fetchers/backfill_daily_indicators.py#L222), [252](../../../gcp/fetchers/backfill_daily_indicators.py#L252)
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../gcp/fetchers/compute_earnings_reactions.py) — line [617](../../../gcp/fetchers/compute_earnings_reactions.py#L617), [676](../../../gcp/fetchers/compute_earnings_reactions.py#L676)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [361](../../../gcp/fetchers/fetch_market_data.py#L361), [826](../../../gcp/fetchers/fetch_market_data.py#L826), [834](../../../gcp/fetchers/fetch_market_data.py#L834), [859](../../../gcp/fetchers/fetch_market_data.py#L859), [1122](../../../gcp/fetchers/fetch_market_data.py#L1122)
- [`gcp/fetchers/fetch_premarket_refresh.py`](../../../gcp/fetchers/fetch_premarket_refresh.py) — line [150](../../../gcp/fetchers/fetch_premarket_refresh.py#L150), [331](../../../gcp/fetchers/fetch_premarket_refresh.py#L331)
- [`gcp/migrate_to_gcp.py`](../../../gcp/migrate_to_gcp.py) — line [148](../../../gcp/migrate_to_gcp.py#L148)
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [365](../../../gcp/premarket_brief.py#L365), [370](../../../gcp/premarket_brief.py#L370), [724](../../../gcp/premarket_brief.py#L724)
- [`gcp/premarket_playbook_resolver.py`](../../../gcp/premarket_playbook_resolver.py) — line [170](../../../gcp/premarket_playbook_resolver.py#L170)
- [`gcp/refresh_earnings_views.py`](../../../gcp/refresh_earnings_views.py) — line [148](../../../gcp/refresh_earnings_views.py#L148)
- [`gcp/research/p2_outcomes_grid.py`](../../../gcp/research/p2_outcomes_grid.py) — line [145](../../../gcp/research/p2_outcomes_grid.py#L145), [150](../../../gcp/research/p2_outcomes_grid.py#L150)
- [`gcp/research/p45_deep_ds_job.py`](../../../gcp/research/p45_deep_ds_job.py) — line [110](../../../gcp/research/p45_deep_ds_job.py#L110), [111](../../../gcp/research/p45_deep_ds_job.py#L111)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../gcp/research/p7_build_multi_tf_features.py) — line [113](../../../gcp/research/p7_build_multi_tf_features.py#L113)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../gcp/research/strat_engine/strat_data_builder.py) — line [217](../../../gcp/research/strat_engine/strat_data_builder.py#L217)
- [`gcp/research/strat_engine/strat_data_pipeline.py`](../../../gcp/research/strat_engine/strat_data_pipeline.py) — line [127](../../../gcp/research/strat_engine/strat_data_pipeline.py#L127)
- [`gcp/research/strat_engine/strat_leakage_audit.py`](../../../gcp/research/strat_engine/strat_leakage_audit.py) — line [112](../../../gcp/research/strat_engine/strat_leakage_audit.py#L112), [114](../../../gcp/research/strat_engine/strat_leakage_audit.py#L114), [116](../../../gcp/research/strat_engine/strat_leakage_audit.py#L116)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [56](../../../lib/agents/ranker/signals.py#L56), [134](../../../lib/agents/ranker/signals.py#L134), [310](../../../lib/agents/ranker/signals.py#L310), [357](../../../lib/agents/ranker/signals.py#L357), [360](../../../lib/agents/ranker/signals.py#L360)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [229](../../../lib/agents/summarizers.py#L229), [267](../../../lib/agents/summarizers.py#L267), [1116](../../../lib/agents/summarizers.py#L1116), [1581](../../../lib/agents/summarizers.py#L1581)
- [`lib/data_loader.py`](../../../lib/data_loader.py) — line [178](../../../lib/data_loader.py#L178), [574](../../../lib/data_loader.py#L574), [817](../../../lib/data_loader.py#L817)
- [`lib/earnings_reactions.py`](../../../lib/earnings_reactions.py) — line [594](../../../lib/earnings_reactions.py#L594)
- [`lib/features/experimental/cross_asset.py`](../../../lib/features/experimental/cross_asset.py) — line [45](../../../lib/features/experimental/cross_asset.py#L45)
- [`lib/features/experimental/vol_regime.py`](../../../lib/features/experimental/vol_regime.py) — line [52](../../../lib/features/experimental/vol_regime.py#L52)
- [`lib/strat_levels.py`](../../../lib/strat_levels.py) — line [1816](../../../lib/strat_levels.py#L1816)
- [`platform/api/main.py`](../../../platform/api/main.py) — line [1060](../../../platform/api/main.py#L1060), [1135](../../../platform/api/main.py#L1135), [1279](../../../platform/api/main.py#L1279), [1449](../../../platform/api/main.py#L1449), [1451](../../../platform/api/main.py#L1451)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [786](../../../platform/api/routers/catalysts.py#L786)
- [`platform/api/routers/dashboard.py`](../../../platform/api/routers/dashboard.py) — line [150](../../../platform/api/routers/dashboard.py#L150), [285](../../../platform/api/routers/dashboard.py#L285)
- [`platform/api/routers/live.py`](../../../platform/api/routers/live.py) — line [546](../../../platform/api/routers/live.py#L546)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [1122](../../../scripts/audit_data_freshness.py#L1122), [1129](../../../scripts/audit_data_freshness.py#L1129), [1253](../../../scripts/audit_data_freshness.py#L1253), [1261](../../../scripts/audit_data_freshness.py#L1261), [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/backfill_and_replay.py`](../../../scripts/backfill_and_replay.py) — line [240](../../../scripts/backfill_and_replay.py#L240)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [109](../../../scripts/backfill_watchlist_data.py#L109)
- [`scripts/deep_backfill_ticker.py`](../../../scripts/deep_backfill_ticker.py) — line [127](../../../scripts/deep_backfill_ticker.py#L127)
- [`scripts/strat_backtest.py`](../../../scripts/strat_backtest.py) — line [37](../../../scripts/strat_backtest.py#L37)

### `market_data_intraday`
- [`gcp/backfill_ticker.py`](../../../gcp/backfill_ticker.py) — line [500](../../../gcp/backfill_ticker.py#L500)
- [`gcp/build_intraday_gex.py`](../../../gcp/build_intraday_gex.py) — line [107](../../../gcp/build_intraday_gex.py#L107)
- [`gcp/build_realtime_gex.py`](../../../gcp/build_realtime_gex.py) — line [99](../../../gcp/build_realtime_gex.py#L99)
- [`gcp/calibrate_level_params.py`](../../../gcp/calibrate_level_params.py) — line [84](../../../gcp/calibrate_level_params.py#L84)
- [`gcp/fetchers/fetch_alphavantage_intraday.py`](../../../gcp/fetchers/fetch_alphavantage_intraday.py) — line [222](../../../gcp/fetchers/fetch_alphavantage_intraday.py#L222), [522](../../../gcp/fetchers/fetch_alphavantage_intraday.py#L522), [555](../../../gcp/fetchers/fetch_alphavantage_intraday.py#L555), [840](../../../gcp/fetchers/fetch_alphavantage_intraday.py#L840)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [460](../../../gcp/fetchers/fetch_market_data.py#L460)
- [`gcp/historical_signals.py`](../../../gcp/historical_signals.py) — line [321](../../../gcp/historical_signals.py#L321)
- [`gcp/premarket_playbook_resolver.py`](../../../gcp/premarket_playbook_resolver.py) — line [472](../../../gcp/premarket_playbook_resolver.py#L472)
- [`gcp/research/strat_engine/breakout_meta_walk_forward.py`](../../../gcp/research/strat_engine/breakout_meta_walk_forward.py) — line [340](../../../gcp/research/strat_engine/breakout_meta_walk_forward.py#L340)
- [`gcp/signal_monitor.py`](../../../gcp/signal_monitor.py) — line [2001](../../../gcp/signal_monitor.py#L2001)
- [`lib/data_loader.py`](../../../lib/data_loader.py) — line [457](../../../lib/data_loader.py#L457)
- [`lib/features/intraday_flow.py`](../../../lib/features/intraday_flow.py) — line [125](../../../lib/features/intraday_flow.py#L125)
- [`lib/options_intraday.py`](../../../lib/options_intraday.py) — line [599](../../../lib/options_intraday.py#L599)
- [`platform/api/main.py`](../../../platform/api/main.py) — line [650](../../../platform/api/main.py#L650), [786](../../../platform/api/main.py#L786), [1283](../../../platform/api/main.py#L1283), [1645](../../../platform/api/main.py#L1645), [1664](../../../platform/api/main.py#L1664)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [208](../../../scripts/analysis/per_ticker_calibration.py#L208), [205](../../../scripts/analysis/per_ticker_calibration.py#L205)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [117](../../../scripts/backfill_watchlist_data.py#L117)
- [`scripts/calibrate_thresholds.py`](../../../scripts/calibrate_thresholds.py) — line [233](../../../scripts/calibrate_thresholds.py#L233)
- [`scripts/replay_signal_monitor.py`](../../../scripts/replay_signal_monitor.py) — line [119](../../../scripts/replay_signal_monitor.py#L119), [494](../../../scripts/replay_signal_monitor.py#L494)
- [`scripts/signal_quality_report.py`](../../../scripts/signal_quality_report.py) — line [522](../../../scripts/signal_quality_report.py#L522)
- [`scripts/validation/validate_brief_accuracy.py`](../../../scripts/validation/validate_brief_accuracy.py) — line [187](../../../scripts/validation/validate_brief_accuracy.py#L187)

### `market_data_intraday_iwm`
- [`gcp/research/p2_outcomes_grid.py`](../../../gcp/research/p2_outcomes_grid.py) — line [183](../../../gcp/research/p2_outcomes_grid.py#L183)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../gcp/research/p7_build_multi_tf_features.py) — line [95](../../../gcp/research/p7_build_multi_tf_features.py#L95)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../gcp/research/strat_engine/strat_data_builder.py) — line [191](../../../gcp/research/strat_engine/strat_data_builder.py#L191)
- [`lib/options_exec_backtest/runner.py`](../../../lib/options_exec_backtest/runner.py) — line [113](../../../lib/options_exec_backtest/runner.py#L113)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [205](../../../scripts/analysis/per_ticker_calibration.py#L205), [208](../../../scripts/analysis/per_ticker_calibration.py#L208)

### `market_data_intraday_other`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_qqq`
- [`gcp/research/p2_outcomes_grid.py`](../../../gcp/research/p2_outcomes_grid.py) — line [183](../../../gcp/research/p2_outcomes_grid.py#L183)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../gcp/research/p7_build_multi_tf_features.py) — line [95](../../../gcp/research/p7_build_multi_tf_features.py#L95)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../gcp/research/strat_engine/strat_data_builder.py) — line [191](../../../gcp/research/strat_engine/strat_data_builder.py#L191)
- [`lib/options_exec_backtest/runner.py`](../../../lib/options_exec_backtest/runner.py) — line [113](../../../lib/options_exec_backtest/runner.py#L113)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [205](../../../scripts/analysis/per_ticker_calibration.py#L205), [208](../../../scripts/analysis/per_ticker_calibration.py#L208)

### `market_data_intraday_spx`
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [205](../../../scripts/analysis/per_ticker_calibration.py#L205), [208](../../../scripts/analysis/per_ticker_calibration.py#L208)

### `market_data_intraday_spy`
- [`gcp/research/p2_outcomes_grid.py`](../../../gcp/research/p2_outcomes_grid.py) — line [183](../../../gcp/research/p2_outcomes_grid.py#L183)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../gcp/research/p7_build_multi_tf_features.py) — line [95](../../../gcp/research/p7_build_multi_tf_features.py#L95)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../gcp/research/strat_engine/strat_data_builder.py) — line [191](../../../gcp/research/strat_engine/strat_data_builder.py#L191)
- [`lib/options_exec_backtest/runner.py`](../../../lib/options_exec_backtest/runner.py) — line [113](../../../lib/options_exec_backtest/runner.py#L113)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [205](../../../scripts/analysis/per_ticker_calibration.py#L205), [208](../../../scripts/analysis/per_ticker_calibration.py#L208)

### `model_routing`
- [`lib/agents/model_routing.py`](../../../lib/agents/model_routing.py) — line [126](../../../lib/agents/model_routing.py#L126)

### `news_sentiment`
- [`gcp/fetchers/fetch_news_sentiment.py`](../../../gcp/fetchers/fetch_news_sentiment.py) — line [191](../../../gcp/fetchers/fetch_news_sentiment.py#L191)
- [`gcp/insight_discord_push.py`](../../../gcp/insight_discord_push.py) — line [290](../../../gcp/insight_discord_push.py#L290), [306](../../../gcp/insight_discord_push.py#L306)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [194](../../../lib/agents/ranker/signals.py#L194), [268](../../../lib/agents/ranker/signals.py#L268)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [1722](../../../lib/agents/summarizers.py#L1722), [1883](../../../lib/agents/summarizers.py#L1883), [1900](../../../lib/agents/summarizers.py#L1900)
- [`lib/features/experimental/news_sentiment.py`](../../../lib/features/experimental/news_sentiment.py) — line [83](../../../lib/features/experimental/news_sentiment.py#L83)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [118](../../../platform/api/routers/catalysts.py#L118), [719](../../../platform/api/routers/catalysts.py#L719)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [133](../../../scripts/backfill_watchlist_data.py#L133)

### `options_daily_features`
- [`lib/features/experimental/options_derived.py`](../../../lib/features/experimental/options_derived.py) — line [355](../../../lib/features/experimental/options_derived.py#L355)

### `playbook_cards`
- [`platform/api/routers/playbook.py`](../../../platform/api/routers/playbook.py) — line [162](../../../platform/api/routers/playbook.py#L162), [167](../../../platform/api/routers/playbook.py#L167), [174](../../../platform/api/routers/playbook.py#L174)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)

### `playbook_cards_staging`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `premarket_analysis`
- [`gcp/discord_interactions/main.py`](../../../gcp/discord_interactions/main.py) — line [345](../../../gcp/discord_interactions/main.py#L345)
- [`gcp/premarket_brief.py`](../../../gcp/premarket_brief.py) — line [3231](../../../gcp/premarket_brief.py#L3231), [3276](../../../gcp/premarket_brief.py#L3276)
- [`gcp/premarket_playbook_resolver.py`](../../../gcp/premarket_playbook_resolver.py) — line [430](../../../gcp/premarket_playbook_resolver.py#L430), [628](../../../gcp/premarket_playbook_resolver.py#L628), [737](../../../gcp/premarket_playbook_resolver.py#L737)
- [`lib/movement_statement.py`](../../../lib/movement_statement.py) — line [346](../../../lib/movement_statement.py#L346), [421](../../../lib/movement_statement.py#L421)
- [`lib/strat_levels.py`](../../../lib/strat_levels.py) — line [2380](../../../lib/strat_levels.py#L2380)
- [`lib/strategies/brief_bias.py`](../../../lib/strategies/brief_bias.py) — line [83](../../../lib/strategies/brief_bias.py#L83)
- [`platform/api/routers/dashboard.py`](../../../platform/api/routers/dashboard.py) — line [107](../../../platform/api/routers/dashboard.py#L107), [116](../../../platform/api/routers/dashboard.py#L116)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [104](../../../scripts/backfill_history_tables.py#L104), [127](../../../scripts/backfill_history_tables.py#L127), [128](../../../scripts/backfill_history_tables.py#L128)
- [`scripts/validation/validate_brief_accuracy.py`](../../../scripts/validation/validate_brief_accuracy.py) — line [351](../../../scripts/validation/validate_brief_accuracy.py#L351)

### `premarket_analysis_history`
- [`scripts/backfill_history_tables.py`](../../../scripts/backfill_history_tables.py) — line [109](../../../scripts/backfill_history_tables.py#L109)

### `ranker_runs`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `realtime_gex_15m`
- [`gcp/build_realtime_gex.py`](../../../gcp/build_realtime_gex.py) — line [146](../../../gcp/build_realtime_gex.py#L146)
- [`lib/features/intraday_gex.py`](../../../lib/features/intraday_gex.py) — line [231](../../../lib/features/intraday_gex.py#L231)

### `regime_combo_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `schema_apply_history`
- [`gcp/apply_schema.py`](../../../gcp/apply_schema.py) — line [379](../../../gcp/apply_schema.py#L379), [453](../../../gcp/apply_schema.py#L453)

### `sec_filings`
- [`lib/agents/ranker/candidates.py`](../../../lib/agents/ranker/candidates.py) — line [119](../../../lib/agents/ranker/candidates.py#L119)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [542](../../../lib/agents/ranker/signals.py#L542)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [1737](../../../lib/agents/summarizers.py#L1737)
- [`lib/strategies/catalyst_proximity.py`](../../../lib/strategies/catalyst_proximity.py) — line [278](../../../lib/strategies/catalyst_proximity.py#L278)
- [`platform/api/routers/catalysts.py`](../../../platform/api/routers/catalysts.py) — line [567](../../../platform/api/routers/catalysts.py#L567), [729](../../../platform/api/routers/catalysts.py#L729), [732](../../../platform/api/routers/catalysts.py#L732)
- [`scripts/backfill_watchlist_data.py`](../../../scripts/backfill_watchlist_data.py) — line [155](../../../scripts/backfill_watchlist_data.py#L155)

### `signal_alerts`
- [`gcp/indicator_correlation_job.py`](../../../gcp/indicator_correlation_job.py) — line [514](../../../gcp/indicator_correlation_job.py#L514)
- [`gcp/signal_monitor_eod_resolver.py`](../../../gcp/signal_monitor_eod_resolver.py) — line [142](../../../gcp/signal_monitor_eod_resolver.py#L142)
- [`gcp/signal_quality_alarm.py`](../../../gcp/signal_quality_alarm.py) — line [209](../../../gcp/signal_quality_alarm.py#L209)
- [`gcp/signal_replay.py`](../../../gcp/signal_replay.py) — line [118](../../../gcp/signal_replay.py#L118)
- [`lib/agents/summarizers.py`](../../../lib/agents/summarizers.py) — line [967](../../../lib/agents/summarizers.py#L967), [985](../../../lib/agents/summarizers.py#L985)
- [`platform/api/routers/journal.py`](../../../platform/api/routers/journal.py) — line [1048](../../../platform/api/routers/journal.py#L1048)
- [`scripts/analysis/per_factor_walkforward.py`](../../../scripts/analysis/per_factor_walkforward.py) — line [254](../../../scripts/analysis/per_factor_walkforward.py#L254)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [196](../../../scripts/analysis/per_ticker_calibration.py#L196)
- [`scripts/analysis/verify_brief_bias.py`](../../../scripts/analysis/verify_brief_bias.py) — line [153](../../../scripts/analysis/verify_brief_bias.py#L153)
- [`scripts/audit_data_freshness.py`](../../../scripts/audit_data_freshness.py) — line [647](../../../scripts/audit_data_freshness.py#L647), [648](../../../scripts/audit_data_freshness.py#L648), [807](../../../scripts/audit_data_freshness.py#L807)

### `signal_metrics`
- [`gcp/signal_quality_alarm.py`](../../../gcp/signal_quality_alarm.py) — line [180](../../../gcp/signal_quality_alarm.py#L180)
- [`scripts/analyze_timeframe_heuristic.py`](../../../scripts/analyze_timeframe_heuristic.py) — line [323](../../../scripts/analyze_timeframe_heuristic.py#L323)
- [`scripts/backfill_timeframe_tags.py`](../../../scripts/backfill_timeframe_tags.py) — line [85](../../../scripts/backfill_timeframe_tags.py#L85)
- [`scripts/signal_quality_report.py`](../../../scripts/signal_quality_report.py) — line [383](../../../scripts/signal_quality_report.py#L383)

### `strat_combo_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `strat_levels`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `ticker_calibration`
- [`lib/strategies/calibration.py`](../../../lib/strategies/calibration.py) — line [101](../../../lib/strategies/calibration.py#L101), [120](../../../lib/strategies/calibration.py#L120)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [216](../../../scripts/analysis/per_ticker_calibration.py#L216)
- [`scripts/calibrate_thresholds.py`](../../../scripts/calibrate_thresholds.py) — line [323](../../../scripts/calibrate_thresholds.py#L323)
- [`scripts/refresh_calibration_table.py`](../../../scripts/refresh_calibration_table.py) — line [74](../../../scripts/refresh_calibration_table.py#L74)

### `ticker_info`
- [`lib/ticker_info.py`](../../../lib/ticker_info.py) — line [102](../../../lib/ticker_info.py#L102)

### `ticker_level_params`
- [`gcp/calibrate_level_params.py`](../../../gcp/calibrate_level_params.py) — line [89](../../../gcp/calibrate_level_params.py#L89)
- [`lib/strat_levels.py`](../../../lib/strat_levels.py) — line [1218](../../../lib/strat_levels.py#L1218)

### `top_movers_daily`
- [`lib/agents/ranker/candidates.py`](../../../lib/agents/ranker/candidates.py) — line [172](../../../lib/agents/ranker/candidates.py#L172)
- [`lib/agents/ranker/signals.py`](../../../lib/agents/ranker/signals.py) — line [496](../../../lib/agents/ranker/signals.py#L496)

### `top_movers_intraday`
- [`platform/api/main.py`](../../../platform/api/main.py) — line [1561](../../../platform/api/main.py#L1561), [1562](../../../platform/api/main.py#L1562)

### `trades`
- [`gcp/trade_logger.py`](../../../gcp/trade_logger.py) — line [176](../../../gcp/trade_logger.py#L176), [212](../../../gcp/trade_logger.py#L212), [243](../../../gcp/trade_logger.py#L243)
- [`lib/data_loader.py`](../../../lib/data_loader.py) — line [865](../../../lib/data_loader.py#L865)
- [`lib/strategies/insight_cache.py`](../../../lib/strategies/insight_cache.py) — line [285](../../../lib/strategies/insight_cache.py#L285)
- [`platform/api/routers/analytics.py`](../../../platform/api/routers/analytics.py) — line [148](../../../platform/api/routers/analytics.py#L148)
- [`platform/api/routers/journal.py`](../../../platform/api/routers/journal.py) — line [1045](../../../platform/api/routers/journal.py#L1045), [1341](../../../platform/api/routers/journal.py#L1341)

### `user_preferences`
- [`platform/api/routers/preferences.py`](../../../platform/api/routers/preferences.py) — line [123](../../../platform/api/routers/preferences.py#L123)

### `user_profile`
- [`platform/api/routers/profile.py`](../../../platform/api/routers/profile.py) — line [136](../../../platform/api/routers/profile.py#L136)

### `user_roles`
- [`platform/api/auth.py`](../../../platform/api/auth.py) — line [250](../../../platform/api/auth.py#L250), [295](../../../platform/api/auth.py#L295)
- [`platform/api/routers/admin.py`](../../../platform/api/routers/admin.py) — line [988](../../../platform/api/routers/admin.py#L988)

### `user_style_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `v_etf_options_node`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `waitlist_signups`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `walk_forward_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `watchlist_history`
- [`gcp/fetchers/_watchlist.py`](../../../gcp/fetchers/_watchlist.py) — line [203](../../../gcp/fetchers/_watchlist.py#L203), [212](../../../gcp/fetchers/_watchlist.py#L212), [235](../../../gcp/fetchers/_watchlist.py#L235)

### `watchlist_history_origin`
- [`gcp/fetchers/_watchlist.py`](../../../gcp/fetchers/_watchlist.py) — line [237](../../../gcp/fetchers/_watchlist.py#L237)

### `watchlists`
- [`gcp/calibrate_level_params.py`](../../../gcp/calibrate_level_params.py) — line [97](../../../gcp/calibrate_level_params.py#L97)
- [`gcp/discord_interactions/main.py`](../../../gcp/discord_interactions/main.py) — line [178](../../../gcp/discord_interactions/main.py#L178), [711](../../../gcp/discord_interactions/main.py#L711)
- [`gcp/fetchers/_watchlist.py`](../../../gcp/fetchers/_watchlist.py) — line [371](../../../gcp/fetchers/_watchlist.py#L371)
- [`gcp/fetchers/fetch_market_data.py`](../../../gcp/fetchers/fetch_market_data.py) — line [846](../../../gcp/fetchers/fetch_market_data.py#L846)
- [`scripts/analysis/per_ticker_calibration.py`](../../../scripts/analysis/per_ticker_calibration.py) — line [227](../../../scripts/analysis/per_ticker_calibration.py#L227)
<!-- inventory:reads:end -->

---

## 4. Multi-writer tables (coordination risks)

Tables with two or more writing files. The risk in each case is the same shape: two writers with different conflict keys or different column subsets on the same row.

<!-- inventory:multiwriter:start -->
| Table | Writers | Files |
|---|---|---|
| `earnings_calendar` | 2 | `gcp/fetchers/evaluate_ew_strikes.py`, `scripts/fetch_earnings_calendar.py` |
| `earnings_options_snapshots` | 2 | `gcp/fetchers/fetch_av_earnings_options_backfill.py`, `gcp/migrate_to_gcp.py` |
| `etf_options_snapshots` | 7 | `gcp/fetchers/_av_realtime_collector.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/fetchers/fetch_av_realtime_options.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `platform/api/routers/grid.py`, `scripts/maintenance/compute_spx_greeks.py` |
| `historical_signals` | 2 | `gcp/historical_signals.py`, `scripts/backfill_timeframe_tags.py` |
| `insight_reports` | 3 | `gcp/insight_pipeline_job.py`, `platform/api/routers/insights.py`, `scripts/generate_historical_report.py` |
| `insight_reports_history` | 2 | `gcp/insight_pipeline_job.py`, `scripts/backfill_history_tables.py` |
| `insight_runs` | 4 | `gcp/auto_refresh_top_n.py`, `gcp/discord_interactions/main.py`, `gcp/insight_pipeline_job.py`, `platform/api/routers/insights.py` |
| `journal_entries` | 2 | `platform/api/routers/journal.py`, `scripts/backfill_journal_embeddings.py` |
| `market_data_daily` | 8 | `gcp/backfill_ticker.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `scripts/backfill_watchlist_data.py`, `scripts/deep_backfill_ticker.py` |
| `market_data_intraday` | 4 | `gcp/backfill_ticker.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/migrate_to_gcp.py` |
| `news_sentiment` | 4 | `gcp/backfill_ticker.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_rss_news.py`, `scripts/backfill_news_sentiment.py` |
| `premarket_analysis` | 3 | `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/signal_monitor.py` |
| `premarket_analysis_history` | 2 | `gcp/premarket_brief.py`, `scripts/backfill_history_tables.py` |
| `signal_alerts` | 3 | `gcp/signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py`, `scripts/replay_signal_monitor.py` |
| `trades` | 4 | `gcp/migrate_to_gcp.py`, `gcp/signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py`, `gcp/trade_logger.py` |
| `watchlists` | 3 | `gcp/backfill_ticker.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/_watchlist.py` |
<!-- inventory:multiwriter:end -->

Notes on the ones that matter operationally:

- **`market_data_daily`** — `fetch_market_data` is canonical (nightly OHLCV + indicators); `fetch_premarket_refresh` UPDATEs only `gap_pct`/`pre_*` at 08:20; `backfill_daily_indicators` recomputes NULL indicator columns; `premarket_brief` DELETEs NULL-close placeholder rows; `backfill_ticker` and the two backfill scripts are on-demand. Ordering is enforced by the schedule (08:20 before 08:30, 23:00 after close).
- **`etf_options_snapshots`** — `fetch_av_historical_options` (nightly) and `fetch_av_realtime_options` (every 5 min in RTH) both upsert on `(ticker, snapshot_ts, contract)`; `options_retention_job` DELETEs by age; `compute_spx_greeks` UPDATEs Greek columns; the grid router writes derived rows. A re-fetch can overwrite computed Greeks.
- **`signal_alerts` / `trades`** — `signal_monitor` (live fires and closes), `signal_monitor_eod_resolver` (outcome columns), and the replay/backfill scripts. Replays must not clobber live alerts; `scripts/replay_signal_monitor.py` mocks the upsert (CLAUDE.md Rule 3.6).
- **`insight_reports` / `insight_runs`** — the pipeline job, the insights router (on-demand), `auto_refresh_top_n` and `discord_interactions` all insert runs with their own UUIDs; the `status` UPDATE path is shared between job and router.
- **`watchlists`** — `backfill_ticker`, `discord_interactions` (`/watchlist`), `_watchlist.py` and `signal_monitor` (seed flags); soft-delete via `removed_at`.

---

## 5. Orphan tables

<!-- inventory:orphans:start -->
| Table | Writers | Readers | Status |
|---|---|---|---|
| `admin_refresh_leases` | 1 | 0 | write-only (no reader in code) |
| `archive_yahoo_earnings_options_snapshots` | 0 | 0 | no writer and no reader in code |
| `archive_yahoo_etf_options_snapshots` | 0 | 0 | no writer and no reader in code |
| `archive_yahoo_market_data_daily` | 0 | 0 | no writer and no reader in code |
| `archive_yahoo_market_data_intraday` | 0 | 0 | no writer and no reader in code |
| `backtest_reports` | 1 | 0 | write-only (no reader in code) |
| `indicator_correlation` | 1 | 0 | write-only (no reader in code) |
| `level_param_policy` | 0 | 2 | read-only (no writer names it in code) |
| `market_data_intraday_iwm` | 0 | 5 | partition of `market_data_intraday` — routed by Postgres; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_other` | 0 | 0 | partition of `market_data_intraday` — routed by Postgres, never named in code; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_qqq` | 0 | 5 | partition of `market_data_intraday` — routed by Postgres; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_spx` | 0 | 1 | partition of `market_data_intraday` — routed by Postgres; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_spy` | 0 | 5 | partition of `market_data_intraday` — routed by Postgres; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `playbook_cards_staging` | 1 | 0 | write-only (no reader in code) |
| `ranker_runs` | 1 | 0 | write-only (no reader in code) |
| `regime_combo_results` | 1 | 0 | write-only (no reader in code) |
| `strat_combo_results` | 0 | 0 | no writer and no reader in code |
| `strat_levels` | 1 | 0 | write-only (no reader in code) |
| `user_style_results` | 1 | 0 | write-only (no reader in code) |
| `v_etf_options_node` | 0 | 0 | no writer and no reader in code |
| `waitlist_signups` | 1 | 0 | write-only (no reader in code) |
| `walk_forward_results` | 1 | 0 | write-only (no reader in code) |
| `watchlist_history` | 0 | 1 | read-only (no writer names it in code) |
| `watchlist_history_origin` | 0 | 1 | read-only (no writer names it in code) |
<!-- inventory:orphans:end -->

Reading the statuses: the four `archive_yahoo_*` tables are frozen forensics (0 rows live); `earnings_event_outcomes` / `earnings_ticker_lean` are materialized views refreshed by `gcp/refresh_earnings_views.py` (the `REFRESH MATERIALIZED VIEW` names reach the statement through the `_WEEKLY_VIEWS` tuple, so both are attributed to that job in §6); `ranker_runs`, `admin_refresh_leases`, `user_style_results`, `playbook_cards_staging`, `waitlist_signups` and `indicator_correlation` are write-only audit or staging tables; `strat_combo_results` and `v_etf_options_node` have no code reference and are drop candidates pending an operator decision.

---

## 6. Blast radius per Cloud Run Job

If the job stops, the listed readers lose fresh data from the tables it writes. Tables are attributed to the code reachable from the job's entrypoint: the whole entry module, then every name it imports from repo modules, what those definitions call, and each reached module's module-level statements, transitively (`gcp/backtest_job.py` → `scripts/run_backtest.py` → `DataLoader` in `lib/data_loader.py` → `market_data_daily`). A function that sits in an imported file but is never called is not attributed (`build_materialized()` in `lib/features/experimental/options_derived.py` writes `options_daily_features` only for `build-options-daily-features`, not for the magnitude jobs that import `add_options_features` from the same file). `job_runs` (written by `gcp/database.py` for every job) is excluded so it does not appear on every row. The job's declared command line scopes it further: `refresh-earnings-views` is deployed with `--mode=weekly` and scheduled a second time with `--mode=daily`, so both branches of its `main()` count, while `direction-probe` fixes `--experiment=e1_horizon` and the `e4_triple_barrier` probe reachable only behind that flag does not. The scope is the deployed configuration (a job's own `--args` plus every scheduler override that targets it, each applied to the module it actually runs), not what an operator could pass by hand. A value only some of those invocations pass decides nothing: `fetch-top-movers` runs hourly with `--intraday-snapshot` and daily without it, so both its writes stand. A scalar option **no** invocation passes carries its declared default and settles on it, exactly as a `store_true` switch it never passes is false: `fetch-market-data` declares `--tickers` with default `ALL` and is deployed without it, so `args.tickers == 'ALL'` holds and the arm that splits a caller-supplied list is not code that job runs. The declared **environment** scopes the job the same way, and its absences carry as much as its values: `MAG_PLAN` is set on `magnitude-engine` and not on `magnitude-recal`, so `os.environ.get("MAG_PLAN", "")` is empty for the latter, its task-parallel dispatch returns early, and the phase-3 `economic_events` read that dispatch could otherwise have reached is not attributed to a job deployed with `--phase=phase0`. Only a name `gcp/deploy.sh` itself sets somewhere is read as absent; one Cloud Run injects (`CLOUD_RUN_TASK_INDEX`) stays unknown, and an execute-time `--update-env-vars` is outside the declared configuration exactly as an execute-time `--args` is. A decided branch prunes both the arm not taken and, when the arm taken ends in a `return` or `raise`, everything after it. A relation named through a container is followed like a scalar constant: `_WEEKLY_VIEWS = ("earnings_event_outcomes", "earnings_ticker_lean")` reaches `REFRESH MATERIALIZED VIEW {view}` through its loop variable and the parameter it is passed as, so both views have `refresh-earnings-views` as their writer. The table names relations declared in `gcp/schema.sql` only; a job whose only edges are to runtime-created relations (`magnitude-inference` writes `magnitude_per_bar_predictions`) shows "no Cloud SQL write found" here and is covered by the hand-created-jobs and runtime-relations prose below.

<!-- inventory:blast:start -->
| Job | Entry module | Tables written (code reachable from the entry module through the names it imports) | Readers of those tables |
|---|---|---|---|
| `apply-schema-migrations` | `gcp/apply_schema.py` | `schema_apply_history` | — |
| `audit-brief-bias` | `gcp/audit_job_runner.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-infra-drift` | `gcp/audit_infra_drift.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-magnitude-drift` | `gcp/audit_magnitude_drift.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-walkforward` | `gcp/audit_job_runner.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `auto-refresh-top-n` | `gcp/auto_refresh_top_n.py` | `insight_runs`, `ranker_runs` | `platform/api/routers/insights.py`, `scripts/backfill_history_tables.py` |
| `backfill-daily-indicators` | `gcp/fetchers/backfill_daily_indicators.py` | `market_data_daily` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/calibrate_level_params.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py` (+21) |
| `backfill-ticker` | `gcp/backfill_ticker.py` | `market_data_daily`, `market_data_intraday`, `news_sentiment`, `watchlists` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/calibrate_level_params.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/_watchlist.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/historical_signals.py` (+36) |
| `backtest` | `gcp/backtest_job.py` | `backtest_trades` | `scripts/generate_backtest_report.py` |
| `backtest-pipeline` | `scripts/run_pipeline.py` | `backtest_reports`, `backtest_sweeps`, `backtest_trades` | — |
| `build-options-daily-features` | `gcp/fetchers/build_options_daily_features.py` | `options_daily_features` | — |
| `build-options-greeks` | `gcp/build_options_daily_greeks.py` | `etf_options_daily_greeks` | — |
| `build-realtime-gex` | `gcp/build_realtime_gex.py` | `realtime_gex_15m` | — |
| `calibrate-thresholds` | `scripts/calibrate_thresholds.py` | `ticker_calibration` | `lib/strategies/calibration.py`, `scripts/analysis/per_ticker_calibration.py`, `scripts/refresh_calibration_table.py` |
| `cloud-sql-weekly-export` | `gcp/sql_export_to_gcs.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `compute-earnings-reactions` | `gcp/fetchers/compute_earnings_reactions.py` | `earnings_reactions` | `gcp/earnings_reactions_brief.py`, `gcp/fetchers/fetch_av_earnings_options_backfill.py`, `scripts/backtest_playability.py` |
| `compute-spx-greeks-backfill` | `scripts/maintenance/compute_spx_greeks.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py` (+11) |
| `db-query` | `gcp/db_query_job.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-baseline` | `gcp/research/direction_program/baseline_runner.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-importance` | `gcp/research/direction_program/feature_importance.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-phase2` | `gcp/research/direction_program/phase2_ablation.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-probe` | `gcp/research/strat_engine/strat_dir_probes.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `earnings-long-watchlist` | `gcp/earnings_long_watchlist.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `earnings-options-backfill` | `gcp/fetchers/fetch_av_earnings_options_backfill.py` | `earnings_options_snapshots` | `lib/data_loader.py`, `scripts/backtest_playability.py` |
| `earnings-reactions-brief` | `gcp/earnings_reactions_brief.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `earnings-sweep` | `scripts/calibrate_earnings.py` | `earnings_calibration`, `earnings_options_strategy_insights`, `earnings_options_strategy_winners` | `gcp/earnings_long_watchlist.py`, `platform/api/routers/earnings.py` |
| `etf-options-retention` | `gcp/options_retention_job.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/data_loader.py` (+12) |
| `fetch-alphavantage-intraday` | `gcp/fetchers/fetch_alphavantage_intraday.py` | `market_data_intraday` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/historical_signals.py`, `gcp/premarket_playbook_resolver.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/signal_monitor.py`, `lib/data_loader.py`, `lib/features/intraday_flow.py`, `lib/options_intraday.py`, `platform/api/main.py` (+7) |
| `fetch-av-options-backfill` | `gcp/fetchers/fetch_av_historical_options.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/data_loader.py` (+12) |
| `fetch-av-options-realtime` | `gcp/fetchers/fetch_av_realtime_options.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py` (+13) |
| `fetch-earnings-calendar` | `scripts/fetch_earnings_calendar.py` | `earnings_calendar` | `gcp/earnings_long_watchlist.py`, `gcp/earnings_reactions_brief.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/evaluate_ew_strikes.py`, `gcp/fetchers/fetch_earnings_history.py`, `gcp/fetchers/fetch_insider_transactions.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/fetchers/fetch_sec_filings.py`, `gcp/premarket_brief.py`, `gcp/refresh_earnings_views.py` (+6) |
| `fetch-earnings-history` | `gcp/fetchers/fetch_earnings_history.py` | `earnings_history`, `market_data_daily` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/calibrate_level_params.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py` (+20) |
| `fetch-economic-events` | `gcp/fetchers/fetch_economic_events.py` | `economic_events` | `gcp/premarket_brief.py`, `gcp/research/magnitude_engine/mag_dataset.py`, `lib/agents/ranker/candidates.py`, `lib/agents/summarizers.py`, `lib/strategies/catalyst_proximity.py`, `platform/api/routers/catalysts.py`, `scripts/audit_data_freshness.py`, `scripts/check_event_window_concentration.py` |
| `fetch-fred-rates` | `gcp/fetchers/fetch_fred_rates.py` | `daily_rates` | `lib/options_exec_backtest/runner.py`, `lib/options_greeks.py`, `scripts/audit_data_freshness.py` |
| `fetch-insider-transactions` | `gcp/fetchers/fetch_insider_transactions.py` | `insider_transactions` | `gcp/earnings_reactions_brief.py`, `lib/agents/ranker/candidates.py`, `lib/agents/ranker/signals.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-market-data` | `gcp/fetchers/fetch_market_data.py` | `market_data_daily`, `market_data_intraday` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/calibrate_level_params.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/historical_signals.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py` (+31) |
| `fetch-news-sentiment` | `gcp/fetchers/fetch_news_sentiment.py` | `news_sentiment` | `gcp/insight_discord_push.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/features/experimental/news_sentiment.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-news-sentiment-earnings` | `gcp/fetchers/fetch_news_sentiment.py` | `news_sentiment` | `gcp/insight_discord_push.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/features/experimental/news_sentiment.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-news-sentiment-topics` | `gcp/fetchers/fetch_news_sentiment.py` | `news_sentiment` | `gcp/insight_discord_push.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/features/experimental/news_sentiment.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-premarket-refresh` | `gcp/fetchers/fetch_premarket_refresh.py` | `market_data_daily` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/calibrate_level_params.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py`, `gcp/research/p45_deep_ds_job.py` (+19) |
| `fetch-sec-filings` | `gcp/fetchers/fetch_sec_filings.py` | `sec_filings` | `lib/agents/ranker/candidates.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/strategies/catalyst_proximity.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-top-movers` | `gcp/fetchers/fetch_top_movers.py` | `top_movers_daily`, `top_movers_intraday` | `lib/agents/ranker/candidates.py`, `lib/agents/ranker/signals.py`, `platform/api/main.py` |
| `freshness-watchdog` | `scripts/audit_data_freshness.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `historical-signals-watchlist` | `scripts/run_historical_signals.py` | `historical_signals` | `platform/api/routers/signals.py`, `scripts/analyze_timeframe_heuristic.py`, `scripts/audit_data_freshness.py`, `scripts/backfill_timeframe_tags.py`, `scripts/signal_quality_report.py` |
| `indicator-correlation` | `gcp/indicator_correlation_job.py` | `indicator_correlation` | — |
| `insight-discord-push` | `gcp/insight_discord_push.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `insight-pipeline` | `gcp/insight_pipeline_job.py` | `insight_reports`, `insight_reports_history`, `insight_runs`, `ticker_level_params` | `gcp/auto_refresh_top_n.py`, `gcp/discord_interactions/main.py`, `gcp/insight_discord_push.py`, `lib/strategies/insight_cache.py`, `platform/api/routers/insights.py`, `scripts/audit_data_freshness.py`, `scripts/backfill_and_replay.py`, `scripts/backfill_history_tables.py`, `scripts/validation/validate_brief_accuracy.py` |
| `intraday-bulk-backfill` | `gcp/fetchers/fetch_alphavantage_intraday.py` | `market_data_intraday` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/historical_signals.py`, `gcp/premarket_playbook_resolver.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/signal_monitor.py`, `lib/data_loader.py`, `lib/features/intraday_flow.py`, `lib/options_intraday.py`, `platform/api/main.py` (+7) |
| `magnitude-engine` | `gcp/research/magnitude_engine/mag_walk_forward.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `magnitude-inference` | `gcp/research/magnitude_engine/mag_inference.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `magnitude-recal` | `gcp/research/magnitude_engine/mag_walk_forward.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `options-exec-backtest` | `lib/options_exec_backtest/cli.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `p2-build-gamma-levels` | `gcp/research/p2_build_gamma_levels.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `param-sweep` | `scripts/run_param_sweep.py` | `exit_config_overrides`, `walk_forward_results` | — |
| `phase6-playbook` | `scripts/analysis/phase6_playbook.py` | `playbook_cards` | `platform/api/routers/playbook.py`, `scripts/audit_data_freshness.py` |
| `premarket-brief` | `gcp/premarket_brief.py` | `market_data_daily`, `premarket_analysis`, `premarket_analysis_history`, `strat_levels` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/calibrate_level_params.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py` (+21) |
| `premarket-playbook-resolver` | `gcp/premarket_playbook_resolver.py` | `premarket_analysis` | `gcp/discord_interactions/main.py`, `gcp/premarket_brief.py`, `lib/movement_statement.py`, `lib/strategies/brief_bias.py`, `platform/api/routers/dashboard.py`, `scripts/audit_data_freshness.py`, `scripts/backfill_history_tables.py`, `scripts/validation/validate_brief_accuracy.py` |
| `refresh-earnings-views` | `gcp/refresh_earnings_views.py` | `earnings_event_outcomes`, `earnings_ticker_lean`, `earnings_upcoming_with_history` | `platform/api/routers/earnings.py` |
| `regime-combo` | `gcp/regime_combo_job.py` | `regime_combo_results` | — |
| `signal-monitor` | `gcp/signal_monitor.py` | `premarket_analysis`, `signal_alerts`, `trades` | `gcp/discord_interactions/main.py`, `gcp/indicator_correlation_job.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/signal_monitor_eod_resolver.py`, `gcp/signal_quality_alarm.py`, `gcp/signal_replay.py`, `lib/agents/summarizers.py`, `lib/movement_statement.py`, `platform/api/routers/analytics.py`, `platform/api/routers/dashboard.py`, `platform/api/routers/journal.py` (+6) |
| `signal-monitor-eod-resolver` | `gcp/signal_monitor_eod_resolver.py` | `signal_alerts`, `trades` | `gcp/indicator_correlation_job.py`, `gcp/signal_quality_alarm.py`, `gcp/signal_replay.py`, `gcp/trade_logger.py`, `lib/agents/summarizers.py`, `lib/strategies/insight_cache.py`, `platform/api/routers/analytics.py`, `platform/api/routers/journal.py`, `scripts/analysis/per_factor_walkforward.py`, `scripts/analysis/per_ticker_calibration.py`, `scripts/analysis/verify_brief_bias.py`, `scripts/audit_data_freshness.py` |
| `signal-quality-alarm` | `gcp/signal_quality_alarm.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `signal-quality-report` | `scripts/signal_quality_report.py` | `signal_metrics` | `gcp/signal_quality_alarm.py`, `scripts/analyze_timeframe_heuristic.py`, `scripts/backfill_timeframe_tags.py` |
| `signal-replay` | `gcp/signal_replay.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `strat-engine` | `gcp/research/strat_engine/strat_data_builder.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `validate-brief` | `gcp/validate_brief_job.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `weekend-review` | `gcp/weekend_review.py` | — (Discord / GCS / no Cloud SQL write found) | — |
<!-- inventory:blast:end -->

Hand-created live jobs (no `deploy_*` function, so not in the table above): `p2-build-gamma-levels` writes `gamma_levels_eod`; the `p7*`, `p45-deep-ds`, `strat-dir-features`, `exec-backtest`, `backtest-playability` and `compare-tier-fires` jobs write research tables or GCS reports only.

---

## 7. Mermaid graph

Job → table writes (thick) and reads (thin). Full lists with `file:line` are in §2/§3.

<!-- inventory:graph:start -->
```mermaid
flowchart LR
    subgraph JOBS [Cloud Run Jobs]
        direction TB
        J_apply_schema_migrations[apply-schema-migrations]
        J_audit_brief_bias[audit-brief-bias]
        J_audit_walkforward[audit-walkforward]
        J_auto_refresh_top_n[auto-refresh-top-n]
        J_backfill_daily_indicators[backfill-daily-indicators]
        J_backfill_ticker[backfill-ticker]
        J_backtest[backtest]
        J_backtest_pipeline[backtest-pipeline]
        J_build_options_daily_features[build-options-daily-features]
        J_build_options_greeks[build-options-greeks]
        J_build_realtime_gex[build-realtime-gex]
        J_calibrate_thresholds[calibrate-thresholds]
        J_compute_earnings_reactions[compute-earnings-reactions]
        J_compute_spx_greeks_backfill[compute-spx-greeks-backfill]
        J_direction_baseline[direction-baseline]
        J_direction_phase2[direction-phase2]
        J_earnings_long_watchlist[earnings-long-watchlist]
        J_earnings_options_backfill[earnings-options-backfill]
        J_earnings_reactions_brief[earnings-reactions-brief]
        J_earnings_sweep[earnings-sweep]
        J_etf_options_retention[etf-options-retention]
        J_fetch_alphavantage_intraday[fetch-alphavantage-intraday]
        J_fetch_av_options_backfill[fetch-av-options-backfill]
        J_fetch_av_options_realtime[fetch-av-options-realtime]
        J_fetch_earnings_calendar[fetch-earnings-calendar]
        J_fetch_earnings_history[fetch-earnings-history]
        J_fetch_economic_events[fetch-economic-events]
        J_fetch_fred_rates[fetch-fred-rates]
        J_fetch_insider_transactions[fetch-insider-transactions]
        J_fetch_market_data[fetch-market-data]
        J_fetch_news_sentiment[fetch-news-sentiment]
        J_fetch_news_sentiment_earnings[fetch-news-sentiment-earnings]
        J_fetch_news_sentiment_topics[fetch-news-sentiment-topics]
        J_fetch_premarket_refresh[fetch-premarket-refresh]
        J_fetch_sec_filings[fetch-sec-filings]
        J_fetch_top_movers[fetch-top-movers]
        J_freshness_watchdog[freshness-watchdog]
        J_historical_signals_watchlist[historical-signals-watchlist]
        J_indicator_correlation[indicator-correlation]
        J_insight_discord_push[insight-discord-push]
        J_insight_pipeline[insight-pipeline]
        J_intraday_bulk_backfill[intraday-bulk-backfill]
        J_magnitude_engine[magnitude-engine]
        J_magnitude_recal[magnitude-recal]
        J_options_exec_backtest[options-exec-backtest]
        J_p2_build_gamma_levels[p2-build-gamma-levels]
        J_param_sweep[param-sweep]
        J_phase6_playbook[phase6-playbook]
        J_premarket_brief[premarket-brief]
        J_premarket_playbook_resolver[premarket-playbook-resolver]
        J_refresh_earnings_views[refresh-earnings-views]
        J_regime_combo[regime-combo]
        J_signal_monitor[signal-monitor]
        J_signal_monitor_eod_resolver[signal-monitor-eod-resolver]
        J_signal_quality_alarm[signal-quality-alarm]
        J_signal_quality_report[signal-quality-report]
        J_signal_replay[signal-replay]
        J_strat_engine[strat-engine]
        J_validate_brief[validate-brief]
        J_weekend_review[weekend-review]
    end
    subgraph TABLES [Cloud SQL tables]
        direction TB
        T_backtest_reports[(backtest_reports)]
        T_backtest_sweeps[(backtest_sweeps)]
        T_backtest_trades[(backtest_trades)]
        T_backtest_walk_forward_folds[(backtest_walk_forward_folds)]
        T_daily_rates[(daily_rates)]
        T_earnings_calendar[(earnings_calendar)]
        T_earnings_calibration[(earnings_calibration)]
        T_earnings_event_outcomes[(earnings_event_outcomes)]
        T_earnings_history[(earnings_history)]
        T_earnings_options_snapshots[(earnings_options_snapshots)]
        T_earnings_options_strategy_insights[(earnings_options_strategy_insights)]
        T_earnings_options_strategy_winners[(earnings_options_strategy_winners)]
        T_earnings_reactions[(earnings_reactions)]
        T_earnings_ticker_lean[(earnings_ticker_lean)]
        T_earnings_upcoming_with_history[(earnings_upcoming_with_history)]
        T_economic_events[(economic_events)]
        T_etf_options_daily_greeks[(etf_options_daily_greeks)]
        T_etf_options_snapshots[(etf_options_snapshots)]
        T_exit_config_overrides[(exit_config_overrides)]
        T_historical_signals[(historical_signals)]
        T_indicator_correlation[(indicator_correlation)]
        T_insider_transactions[(insider_transactions)]
        T_insight_reports[(insight_reports)]
        T_insight_reports_history[(insight_reports_history)]
        T_insight_runs[(insight_runs)]
        T_job_runs[(job_runs)]
        T_journal_entries[(journal_entries)]
        T_level_param_policy[(level_param_policy)]
        T_market_data_daily[(market_data_daily)]
        T_market_data_intraday[(market_data_intraday)]
        T_market_data_intraday_iwm[(market_data_intraday_iwm)]
        T_market_data_intraday_qqq[(market_data_intraday_qqq)]
        T_market_data_intraday_spy[(market_data_intraday_spy)]
        T_model_routing[(model_routing)]
        T_news_sentiment[(news_sentiment)]
        T_options_daily_features[(options_daily_features)]
        T_playbook_cards[(playbook_cards)]
        T_premarket_analysis[(premarket_analysis)]
        T_premarket_analysis_history[(premarket_analysis_history)]
        T_ranker_runs[(ranker_runs)]
        T_realtime_gex_15m[(realtime_gex_15m)]
        T_regime_combo_results[(regime_combo_results)]
        T_schema_apply_history[(schema_apply_history)]
        T_sec_filings[(sec_filings)]
        T_signal_alerts[(signal_alerts)]
        T_signal_metrics[(signal_metrics)]
        T_strat_levels[(strat_levels)]
        T_ticker_calibration[(ticker_calibration)]
        T_ticker_level_params[(ticker_level_params)]
        T_top_movers_daily[(top_movers_daily)]
        T_top_movers_intraday[(top_movers_intraday)]
        T_trades[(trades)]
        T_walk_forward_results[(walk_forward_results)]
        T_watchlist_history[(watchlist_history)]
        T_watchlist_history_origin[(watchlist_history_origin)]
        T_watchlists[(watchlists)]
    end

    J_apply_schema_migrations ==> T_schema_apply_history
    J_auto_refresh_top_n ==> T_insight_runs
    J_auto_refresh_top_n ==> T_ranker_runs
    J_backfill_daily_indicators ==> T_market_data_daily
    J_backfill_ticker ==> T_market_data_daily
    J_backfill_ticker ==> T_market_data_intraday
    J_backfill_ticker ==> T_news_sentiment
    J_backfill_ticker ==> T_watchlists
    J_backtest ==> T_backtest_trades
    J_backtest_pipeline ==> T_backtest_reports
    J_backtest_pipeline ==> T_backtest_sweeps
    J_backtest_pipeline ==> T_backtest_trades
    J_build_options_daily_features ==> T_options_daily_features
    J_build_options_greeks ==> T_etf_options_daily_greeks
    J_build_realtime_gex ==> T_realtime_gex_15m
    J_calibrate_thresholds ==> T_ticker_calibration
    J_compute_earnings_reactions ==> T_earnings_reactions
    J_compute_spx_greeks_backfill ==> T_etf_options_snapshots
    J_earnings_options_backfill ==> T_earnings_options_snapshots
    J_earnings_sweep ==> T_earnings_calibration
    J_earnings_sweep ==> T_earnings_options_strategy_insights
    J_earnings_sweep ==> T_earnings_options_strategy_winners
    J_etf_options_retention ==> T_etf_options_snapshots
    J_fetch_alphavantage_intraday ==> T_market_data_intraday
    J_fetch_av_options_backfill ==> T_etf_options_snapshots
    J_fetch_av_options_realtime ==> T_etf_options_snapshots
    J_fetch_earnings_calendar ==> T_earnings_calendar
    J_fetch_earnings_history ==> T_earnings_history
    J_fetch_earnings_history ==> T_market_data_daily
    J_fetch_economic_events ==> T_economic_events
    J_fetch_fred_rates ==> T_daily_rates
    J_fetch_insider_transactions ==> T_insider_transactions
    J_fetch_market_data ==> T_market_data_daily
    J_fetch_market_data ==> T_market_data_intraday
    J_fetch_news_sentiment ==> T_news_sentiment
    J_fetch_news_sentiment_earnings ==> T_news_sentiment
    J_fetch_news_sentiment_topics ==> T_news_sentiment
    J_fetch_premarket_refresh ==> T_market_data_daily
    J_fetch_sec_filings ==> T_sec_filings
    J_fetch_top_movers ==> T_top_movers_daily
    J_fetch_top_movers ==> T_top_movers_intraday
    J_historical_signals_watchlist ==> T_historical_signals
    J_indicator_correlation ==> T_indicator_correlation
    J_insight_pipeline ==> T_insight_reports
    J_insight_pipeline ==> T_insight_reports_history
    J_insight_pipeline ==> T_insight_runs
    J_insight_pipeline ==> T_ticker_level_params
    J_intraday_bulk_backfill ==> T_market_data_intraday
    J_param_sweep ==> T_exit_config_overrides
    J_param_sweep ==> T_walk_forward_results
    J_phase6_playbook ==> T_playbook_cards
    J_premarket_brief ==> T_market_data_daily
    J_premarket_brief ==> T_premarket_analysis
    J_premarket_brief ==> T_premarket_analysis_history
    J_premarket_brief ==> T_strat_levels
    J_premarket_playbook_resolver ==> T_premarket_analysis
    J_refresh_earnings_views ==> T_earnings_event_outcomes
    J_refresh_earnings_views ==> T_earnings_ticker_lean
    J_refresh_earnings_views ==> T_earnings_upcoming_with_history
    J_regime_combo ==> T_regime_combo_results
    J_signal_monitor ==> T_premarket_analysis
    J_signal_monitor ==> T_signal_alerts
    J_signal_monitor ==> T_trades
    J_signal_monitor_eod_resolver ==> T_signal_alerts
    J_signal_monitor_eod_resolver ==> T_trades
    J_signal_quality_report ==> T_signal_metrics

    T_schema_apply_history --> J_apply_schema_migrations
    T_signal_alerts --> J_audit_brief_bias
    T_signal_alerts --> J_audit_walkforward
    T_earnings_calendar --> J_auto_refresh_top_n
    T_earnings_history --> J_auto_refresh_top_n
    T_economic_events --> J_auto_refresh_top_n
    T_etf_options_snapshots --> J_auto_refresh_top_n
    T_insider_transactions --> J_auto_refresh_top_n
    T_insight_reports --> J_auto_refresh_top_n
    T_market_data_daily --> J_auto_refresh_top_n
    T_news_sentiment --> J_auto_refresh_top_n
    T_sec_filings --> J_auto_refresh_top_n
    T_top_movers_daily --> J_auto_refresh_top_n
    T_watchlists --> J_auto_refresh_top_n
    T_market_data_daily --> J_backfill_daily_indicators
    T_level_param_policy --> J_backfill_ticker
    T_market_data_daily --> J_backfill_ticker
    T_market_data_intraday --> J_backfill_ticker
    T_ticker_level_params --> J_backfill_ticker
    T_exit_config_overrides --> J_backtest
    T_market_data_daily --> J_backtest
    T_market_data_intraday --> J_backtest
    T_backtest_sweeps --> J_backtest_pipeline
    T_backtest_trades --> J_backtest_pipeline
    T_backtest_walk_forward_folds --> J_backtest_pipeline
    T_exit_config_overrides --> J_backtest_pipeline
    T_market_data_daily --> J_backtest_pipeline
    T_market_data_intraday --> J_backtest_pipeline
    T_etf_options_snapshots --> J_build_options_daily_features
    T_etf_options_snapshots --> J_build_options_greeks
    T_etf_options_snapshots --> J_build_realtime_gex
    T_market_data_intraday --> J_build_realtime_gex
    T_realtime_gex_15m --> J_build_realtime_gex
    T_market_data_intraday --> J_calibrate_thresholds
    T_ticker_calibration --> J_calibrate_thresholds
    T_earnings_calendar --> J_compute_earnings_reactions
    T_earnings_history --> J_compute_earnings_reactions
    T_earnings_reactions --> J_compute_earnings_reactions
    T_market_data_daily --> J_compute_earnings_reactions
    T_daily_rates --> J_compute_spx_greeks_backfill
    T_etf_options_snapshots --> J_compute_spx_greeks_backfill
    T_market_data_daily --> J_compute_spx_greeks_backfill
    T_etf_options_snapshots --> J_direction_baseline
    T_options_daily_features --> J_direction_baseline
    T_etf_options_snapshots --> J_direction_phase2
    T_options_daily_features --> J_direction_phase2
    T_earnings_calendar --> J_earnings_long_watchlist
    T_earnings_options_strategy_winners --> J_earnings_long_watchlist
    T_earnings_options_snapshots --> J_earnings_options_backfill
    T_earnings_reactions --> J_earnings_options_backfill
    T_earnings_calendar --> J_earnings_reactions_brief
    T_earnings_reactions --> J_earnings_reactions_brief
    T_insider_transactions --> J_earnings_reactions_brief
    T_earnings_options_snapshots --> J_earnings_sweep
    T_earnings_reactions --> J_earnings_sweep
    T_etf_options_snapshots --> J_etf_options_retention
    T_market_data_intraday --> J_fetch_alphavantage_intraday
    T_watchlists --> J_fetch_alphavantage_intraday
    T_etf_options_snapshots --> J_fetch_av_options_backfill
    T_watchlists --> J_fetch_av_options_backfill
    T_earnings_calendar --> J_fetch_earnings_calendar
    T_earnings_calendar --> J_fetch_earnings_history
    T_earnings_history --> J_fetch_earnings_history
    T_market_data_daily --> J_fetch_earnings_history
    T_watchlists --> J_fetch_earnings_history
    T_earnings_calendar --> J_fetch_insider_transactions
    T_watchlists --> J_fetch_insider_transactions
    T_earnings_calendar --> J_fetch_market_data
    T_level_param_policy --> J_fetch_market_data
    T_market_data_daily --> J_fetch_market_data
    T_market_data_intraday --> J_fetch_market_data
    T_ticker_level_params --> J_fetch_market_data
    T_watchlists --> J_fetch_market_data
    T_earnings_calendar --> J_fetch_news_sentiment
    T_news_sentiment --> J_fetch_news_sentiment
    T_watchlists --> J_fetch_news_sentiment
    T_earnings_calendar --> J_fetch_news_sentiment_earnings
    T_news_sentiment --> J_fetch_news_sentiment_earnings
    T_watchlists --> J_fetch_news_sentiment_earnings
    T_earnings_calendar --> J_fetch_news_sentiment_topics
    T_news_sentiment --> J_fetch_news_sentiment_topics
    T_watchlists --> J_fetch_news_sentiment_topics
    T_earnings_calendar --> J_fetch_premarket_refresh
    T_level_param_policy --> J_fetch_premarket_refresh
    T_market_data_daily --> J_fetch_premarket_refresh
    T_ticker_level_params --> J_fetch_premarket_refresh
    T_watchlists --> J_fetch_premarket_refresh
    T_earnings_calendar --> J_fetch_sec_filings
    T_watchlists --> J_fetch_sec_filings
    T_daily_rates --> J_freshness_watchdog
    T_earnings_calendar --> J_freshness_watchdog
    T_economic_events --> J_freshness_watchdog
    T_etf_options_snapshots --> J_freshness_watchdog
    T_historical_signals --> J_freshness_watchdog
    T_insight_reports --> J_freshness_watchdog
    T_job_runs --> J_freshness_watchdog
    T_market_data_daily --> J_freshness_watchdog
    T_market_data_intraday --> J_freshness_watchdog
    T_playbook_cards --> J_freshness_watchdog
    T_premarket_analysis --> J_freshness_watchdog
    T_signal_alerts --> J_freshness_watchdog
    T_earnings_calendar --> J_historical_signals_watchlist
    T_economic_events --> J_historical_signals_watchlist
    T_exit_config_overrides --> J_historical_signals_watchlist
    T_historical_signals --> J_historical_signals_watchlist
    T_market_data_intraday --> J_historical_signals_watchlist
    T_sec_filings --> J_historical_signals_watchlist
    T_watchlists --> J_historical_signals_watchlist
    T_market_data_intraday --> J_indicator_correlation
    T_signal_alerts --> J_indicator_correlation
    T_insight_reports --> J_insight_discord_push
    T_news_sentiment --> J_insight_discord_push
    T_daily_rates --> J_insight_pipeline
    T_earnings_calendar --> J_insight_pipeline
    T_economic_events --> J_insight_pipeline
    T_etf_options_snapshots --> J_insight_pipeline
    T_insight_reports --> J_insight_pipeline
    T_journal_entries --> J_insight_pipeline
    T_level_param_policy --> J_insight_pipeline
    T_market_data_daily --> J_insight_pipeline
    T_market_data_intraday --> J_insight_pipeline
    T_model_routing --> J_insight_pipeline
    T_news_sentiment --> J_insight_pipeline
    T_premarket_analysis --> J_insight_pipeline
    T_sec_filings --> J_insight_pipeline
    T_ticker_level_params --> J_insight_pipeline
    T_watchlist_history --> J_insight_pipeline
    T_watchlist_history_origin --> J_insight_pipeline
    T_watchlists --> J_insight_pipeline
    T_market_data_intraday --> J_intraday_bulk_backfill
    T_watchlists --> J_intraday_bulk_backfill
    T_economic_events --> J_magnitude_engine
    T_etf_options_snapshots --> J_magnitude_engine
    T_options_daily_features --> J_magnitude_engine
    T_etf_options_snapshots --> J_magnitude_recal
    T_options_daily_features --> J_magnitude_recal
    T_daily_rates --> J_options_exec_backtest
    T_etf_options_snapshots --> J_options_exec_backtest
    T_market_data_intraday_iwm --> J_options_exec_backtest
    T_market_data_intraday_qqq --> J_options_exec_backtest
    T_market_data_intraday_spy --> J_options_exec_backtest
    T_daily_rates --> J_p2_build_gamma_levels
    T_etf_options_snapshots --> J_p2_build_gamma_levels
    T_exit_config_overrides --> J_param_sweep
    T_market_data_daily --> J_param_sweep
    T_market_data_intraday --> J_param_sweep
    T_market_data_intraday --> J_phase6_playbook
    T_earnings_calendar --> J_premarket_brief
    T_earnings_calibration --> J_premarket_brief
    T_earnings_reactions --> J_premarket_brief
    T_economic_events --> J_premarket_brief
    T_etf_options_snapshots --> J_premarket_brief
    T_level_param_policy --> J_premarket_brief
    T_market_data_daily --> J_premarket_brief
    T_premarket_analysis --> J_premarket_brief
    T_ticker_calibration --> J_premarket_brief
    T_ticker_level_params --> J_premarket_brief
    T_watchlists --> J_premarket_brief
    T_level_param_policy --> J_premarket_playbook_resolver
    T_market_data_daily --> J_premarket_playbook_resolver
    T_market_data_intraday --> J_premarket_playbook_resolver
    T_premarket_analysis --> J_premarket_playbook_resolver
    T_ticker_level_params --> J_premarket_playbook_resolver
    T_earnings_calendar --> J_refresh_earnings_views
    T_earnings_event_outcomes --> J_refresh_earnings_views
    T_earnings_ticker_lean --> J_refresh_earnings_views
    T_market_data_daily --> J_refresh_earnings_views
    T_market_data_intraday --> J_regime_combo
    T_earnings_calendar --> J_signal_monitor
    T_economic_events --> J_signal_monitor
    T_exit_config_overrides --> J_signal_monitor
    T_insight_reports --> J_signal_monitor
    T_level_param_policy --> J_signal_monitor
    T_market_data_daily --> J_signal_monitor
    T_market_data_intraday --> J_signal_monitor
    T_premarket_analysis --> J_signal_monitor
    T_sec_filings --> J_signal_monitor
    T_ticker_calibration --> J_signal_monitor
    T_ticker_level_params --> J_signal_monitor
    T_trades --> J_signal_monitor
    T_watchlists --> J_signal_monitor
    T_market_data_intraday --> J_signal_monitor_eod_resolver
    T_signal_alerts --> J_signal_monitor_eod_resolver
    T_signal_alerts --> J_signal_quality_alarm
    T_signal_metrics --> J_signal_quality_alarm
    T_historical_signals --> J_signal_quality_report
    T_market_data_intraday --> J_signal_quality_report
    T_signal_metrics --> J_signal_quality_report
    T_signal_alerts --> J_signal_replay
    T_etf_options_snapshots --> J_strat_engine
    T_market_data_daily --> J_strat_engine
    T_market_data_intraday_iwm --> J_strat_engine
    T_market_data_intraday_qqq --> J_strat_engine
    T_market_data_intraday_spy --> J_strat_engine
    T_insight_reports --> J_validate_brief
    T_market_data_intraday --> J_validate_brief
    T_premarket_analysis --> J_validate_brief
    T_watchlists --> J_validate_brief
    T_trades --> J_weekend_review

    classDef job fill:#3B82F6,stroke:#1E40AF,color:#fff
    classDef tbl fill:#10B981,stroke:#065F46,color:#fff
    class J_apply_schema_migrations,J_audit_brief_bias,J_audit_walkforward,J_auto_refresh_top_n,J_backfill_daily_indicators,J_backfill_ticker,J_backtest,J_backtest_pipeline,J_build_options_daily_features,J_build_options_greeks,J_build_realtime_gex,J_calibrate_thresholds,J_compute_earnings_reactions,J_compute_spx_greeks_backfill,J_direction_baseline,J_direction_phase2,J_earnings_long_watchlist,J_earnings_options_backfill,J_earnings_reactions_brief,J_earnings_sweep,J_etf_options_retention,J_fetch_alphavantage_intraday,J_fetch_av_options_backfill,J_fetch_av_options_realtime,J_fetch_earnings_calendar,J_fetch_earnings_history,J_fetch_economic_events,J_fetch_fred_rates,J_fetch_insider_transactions,J_fetch_market_data,J_fetch_news_sentiment,J_fetch_news_sentiment_earnings,J_fetch_news_sentiment_topics,J_fetch_premarket_refresh,J_fetch_sec_filings,J_fetch_top_movers,J_freshness_watchdog,J_historical_signals_watchlist,J_indicator_correlation,J_insight_discord_push,J_insight_pipeline,J_intraday_bulk_backfill,J_magnitude_engine,J_magnitude_recal,J_options_exec_backtest,J_p2_build_gamma_levels,J_param_sweep,J_phase6_playbook,J_premarket_brief,J_premarket_playbook_resolver,J_refresh_earnings_views,J_regime_combo,J_signal_monitor,J_signal_monitor_eod_resolver,J_signal_quality_alarm,J_signal_quality_report,J_signal_replay,J_strat_engine,J_validate_brief,J_weekend_review job
    class T_backtest_reports,T_backtest_sweeps,T_backtest_trades,T_backtest_walk_forward_folds,T_daily_rates,T_earnings_calendar,T_earnings_calibration,T_earnings_event_outcomes,T_earnings_history,T_earnings_options_snapshots,T_earnings_options_strategy_insights,T_earnings_options_strategy_winners,T_earnings_reactions,T_earnings_ticker_lean,T_earnings_upcoming_with_history,T_economic_events,T_etf_options_daily_greeks,T_etf_options_snapshots,T_exit_config_overrides,T_historical_signals,T_indicator_correlation,T_insider_transactions,T_insight_reports,T_insight_reports_history,T_insight_runs,T_job_runs,T_journal_entries,T_level_param_policy,T_market_data_daily,T_market_data_intraday,T_market_data_intraday_iwm,T_market_data_intraday_qqq,T_market_data_intraday_spy,T_model_routing,T_news_sentiment,T_options_daily_features,T_playbook_cards,T_premarket_analysis,T_premarket_analysis_history,T_ranker_runs,T_realtime_gex_15m,T_regime_combo_results,T_schema_apply_history,T_sec_filings,T_signal_alerts,T_signal_metrics,T_strat_levels,T_ticker_calibration,T_ticker_level_params,T_top_movers_daily,T_top_movers_intraday,T_trades,T_walk_forward_results,T_watchlist_history,T_watchlist_history_origin,T_watchlists tbl
```
<!-- inventory:graph:end -->

Rendered from `table_refs` by `scripts/maintenance/doc_inventory.py`: thick `==>` is a write by code reachable from the job's entry module through the names it imports, thin `-->` is a read by the same scope (the attribution rule is stated under §6). Every job with at least one edge to a relation declared in `gcp/schema.sql`, and every such relation with at least one edge, appears; runtime-created relations (§1b) and the jobs whose only edges are to them are not drawn, and `gcp/database.py`'s `job_runs` bookkeeping is excluded, as in §6.

---

## 8. Notes for follow-up work

1. `strat_combo_results` and `v_etf_options_node` have no writer or reader in code — confirm nobody queries them by hand, then drop.
2. `earnings_options_snapshots` has 0 live rows but 588 MB of dead space; its only production writer is the on-demand `earnings-options-backfill`. A `VACUUM FULL` or drop is an operator call.
3. `gcp/fetchers/fetch_rss_news.py` writes `news_sentiment` but has no `deploy_*` function and no scheduler.
4. The 26 runtime-created relations are outside the schema migration path (`gcp/schema.sql` + `apply-schema-migrations`) and outside `scripts/audit_data_freshness.py`; `strat_features_levels_1m` alone is 8 GB.
5. `market_data_intraday_other` (5.7 M rows, 67 GB) is larger than the three ETF partitions combined; it holds every non-ETF ticker ever backfilled and has more index than data ([`docs/audits/COST_AUDIT_2026-09-06.md`](../../audits/COST_AUDIT_2026-09-06.md) §7).

## 9. Removed since last refresh

- 2026-09-07: the 2026-09-02 layout's "1. Table inventory" became "1. Table inventory (declared in `gcp/schema.sql`)" plus "1b. Live relations"; its "`market_data_intraday` (and partitions)" write-graph subsection became the per-table `market_data_intraday` subsection (partitions are routed by Postgres and are listed in §1 and §5 only). Every table that had a §2/§3 entry still has one.

Generated 2026-09-07; inventory blocks rendered by `scripts/maintenance/doc_inventory.py`. The audits that established this layout are in [`docs/audits/`](../../audits).
