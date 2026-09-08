# Data Dependencies — table-level write/read graph

> **Hand-maintained snapshot — nothing automated writes to this file.** It is the copy of
> [`../05-c-DATA_DEPENDENCIES.md`](../05-c-DATA_DEPENDENCIES.md) taken on 2026-09-08, before the monthly refresh began rewriting that
> document. Edit it freely, including inside any `<!-- inventory:* -->` markers: the refresh
> workflow's write policy names the four refreshed files only, its stray-write scan fails the run
> on any other change, and `scripts/verify_docs_against_live.py` does not enrol this folder. Its
> figures are frozen as of that date and do not track the live fleet; see
> [`README.md`](README.md) for how to refresh a copy by hand.

**Generated 2026-09-07** from [`gcp/schema.sql`](../../../../gcp/schema.sql), a whole-word scan of `gcp/`, `lib/`, `scripts/` and `platform/api` (tests and `archive/` excluded), and the 2026-09-07 live table statistics, by [`scripts/maintenance/doc_inventory.py`](../../../../scripts/maintenance/doc_inventory.py). Every citation is a `file:line` you can open. In the original, [`../05-c-DATA_DEPENDENCIES.md`](../05-c-DATA_DEPENDENCIES.md), the blocks between `<!-- inventory:*:start/end -->` markers are re-rendered by the monthly refresh; in this copy nothing is, and every line is yours to edit.

This doc complements [ARCHITECTURE.md](05-a-ARCHITECTURE.md) §5 (schema by domain) and §6 (jobs). Where ARCHITECTURE says "job X runs module Y", this doc answers "module Y writes table Z, and Z is read by A, B, C".

> **Partition handling.** `market_data_intraday` is LIST-partitioned by ticker; the five children (`_spy`, `_iwm`, `_qqq`, `_spx`, `_other`) are routed by Postgres and never named in code, so they appear in §1 and §5 but have no entries of their own in §2/§3.
>
> **Runtime tables.** The live database holds 28 relations that `gcp/schema.sql` does not declare (`strat_features_*`, `magnitude_*`, `gamma_levels_eod`, `daily_vex`, `gamma_events`, `*_30m_predictions`, `market_data_indicators*`, `market_data_cross_asset`); they are created by research and analytics jobs at runtime. They are listed in §1b with row counts but have no write/read graph here because their names are built dynamically in code.
>
> **Ad-hoc access.** [`scripts/db_query_cr.sh`](../../../../scripts/db_query_cr.sh) → the `db-query` Cloud Run Job can read or (with `--commit`) write any table. It is an operator tool, not a pipeline component, and is not listed as a writer or reader.

---

## 1. Table inventory (declared in `gcp/schema.sql`)

<!-- inventory:tables:start -->
| Relation | Kind | Defined |
|---|---|---|
| `admin_refresh_leases` | table | [`gcp/schema.sql:4087`](../../../../gcp/schema.sql#L4087) |
| `archive_yahoo_earnings_options_snapshots` | table | [`gcp/schema.sql:541`](../../../../gcp/schema.sql#L541) |
| `archive_yahoo_etf_options_snapshots` | table | [`gcp/schema.sql:538`](../../../../gcp/schema.sql#L538) |
| `archive_yahoo_market_data_daily` | table | [`gcp/schema.sql:532`](../../../../gcp/schema.sql#L532) |
| `archive_yahoo_market_data_intraday` | table | [`gcp/schema.sql:535`](../../../../gcp/schema.sql#L535) |
| `backtest_reports` | table | [`gcp/schema.sql:3034`](../../../../gcp/schema.sql#L3034) |
| `backtest_sweeps` | table | [`gcp/schema.sql:3005`](../../../../gcp/schema.sql#L3005) |
| `backtest_trades` | table | [`gcp/schema.sql:2963`](../../../../gcp/schema.sql#L2963) |
| `backtest_walk_forward_folds` | table | [`gcp/schema.sql:3060`](../../../../gcp/schema.sql#L3060) |
| `daily_rates` | table | [`gcp/schema.sql:511`](../../../../gcp/schema.sql#L511) |
| `earnings_calendar` | table | [`gcp/schema.sql:551`](../../../../gcp/schema.sql#L551) |
| `earnings_calibration` | table | [`gcp/schema.sql:3153`](../../../../gcp/schema.sql#L3153) |
| `earnings_history` | table | [`gcp/schema.sql:712`](../../../../gcp/schema.sql#L712) |
| `earnings_options_snapshots` | table | [`gcp/schema.sql:450`](../../../../gcp/schema.sql#L450) |
| `earnings_options_strategy_insights` | table | [`gcp/schema.sql:3381`](../../../../gcp/schema.sql#L3381) |
| `earnings_options_strategy_winners` | table | [`gcp/schema.sql:3409`](../../../../gcp/schema.sql#L3409) |
| `earnings_reactions` | table | [`gcp/schema.sql:758`](../../../../gcp/schema.sql#L758) |
| `earnings_upcoming_with_history` | table | [`gcp/schema.sql:3799`](../../../../gcp/schema.sql#L3799) |
| `economic_events` | table | [`gcp/schema.sql:1418`](../../../../gcp/schema.sql#L1418) |
| `etf_options_daily_greeks` | table | [`gcp/schema.sql:357`](../../../../gcp/schema.sql#L357) |
| `etf_options_snapshots` | table | [`gcp/schema.sql:150`](../../../../gcp/schema.sql#L150) |
| `exit_config_overrides` | table | [`gcp/schema.sql:2417`](../../../../gcp/schema.sql#L2417) |
| `historical_signals` | table | [`gcp/schema.sql:2103`](../../../../gcp/schema.sql#L2103) |
| `indicator_correlation` | table | [`gcp/schema.sql:3222`](../../../../gcp/schema.sql#L3222) |
| `insider_transactions` | table | [`gcp/schema.sql:964`](../../../../gcp/schema.sql#L964) |
| `insight_reports` | table | [`gcp/schema.sql:1517`](../../../../gcp/schema.sql#L1517) |
| `insight_reports_history` | table | [`gcp/schema.sql:2034`](../../../../gcp/schema.sql#L2034) |
| `insight_runs` | table | [`gcp/schema.sql:1553`](../../../../gcp/schema.sql#L1553) |
| `intraday_flow_15m` | table | [`gcp/schema.sql:397`](../../../../gcp/schema.sql#L397) |
| `intraday_gex_15m` | table | [`gcp/schema.sql:418`](../../../../gcp/schema.sql#L418) |
| `job_runs` | table | [`gcp/schema.sql:3936`](../../../../gcp/schema.sql#L3936) |
| `journal_entries` | table | [`gcp/schema.sql:1176`](../../../../gcp/schema.sql#L1176) |
| `market_data_daily` | table | [`gcp/schema.sql:12`](../../../../gcp/schema.sql#L12) |
| `market_data_intraday` | table | [`gcp/schema.sql:115`](../../../../gcp/schema.sql#L115) |
| `market_data_intraday_iwm` | partition of `market_data_intraday` | [`gcp/schema.sql:133`](../../../../gcp/schema.sql#L133) |
| `market_data_intraday_other` | partition of `market_data_intraday` | [`gcp/schema.sql:139`](../../../../gcp/schema.sql#L139) |
| `market_data_intraday_qqq` | partition of `market_data_intraday` | [`gcp/schema.sql:135`](../../../../gcp/schema.sql#L135) |
| `market_data_intraday_spx` | partition of `market_data_intraday` | [`gcp/schema.sql:137`](../../../../gcp/schema.sql#L137) |
| `market_data_intraday_spy` | partition of `market_data_intraday` | [`gcp/schema.sql:131`](../../../../gcp/schema.sql#L131) |
| `model_routing` | table | [`gcp/schema.sql:1485`](../../../../gcp/schema.sql#L1485) |
| `news_sentiment` | table | [`gcp/schema.sql:1595`](../../../../gcp/schema.sql#L1595) |
| `options_daily_features` | table | [`gcp/schema.sql:260`](../../../../gcp/schema.sql#L260) |
| `playbook_cards` | table | [`gcp/schema.sql:1344`](../../../../gcp/schema.sql#L1344) |
| `playbook_cards_staging` | table | [`gcp/schema.sql:3910`](../../../../gcp/schema.sql#L3910) |
| `premarket_analysis` | table | [`gcp/schema.sql:1290`](../../../../gcp/schema.sql#L1290) |
| `premarket_analysis_history` | table | [`gcp/schema.sql:1919`](../../../../gcp/schema.sql#L1919) |
| `ranker_runs` | table | [`gcp/schema.sql:1039`](../../../../gcp/schema.sql#L1039) |
| `realtime_gex_15m` | table | [`gcp/schema.sql:437`](../../../../gcp/schema.sql#L437) |
| `regime_combo_results` | table | [`gcp/schema.sql:3299`](../../../../gcp/schema.sql#L3299) |
| `sec_filings` | table | [`gcp/schema.sql:931`](../../../../gcp/schema.sql#L931) |
| `signal_alerts` | table | [`gcp/schema.sql:1057`](../../../../gcp/schema.sql#L1057) |
| `signal_metrics` | table | [`gcp/schema.sql:2647`](../../../../gcp/schema.sql#L2647) |
| `strat_combo_results` | table | [`gcp/schema.sql:3331`](../../../../gcp/schema.sql#L3331) |
| `strat_levels` | table | [`gcp/schema.sql:1635`](../../../../gcp/schema.sql#L1635) |
| `ticker_calibration` | table | [`gcp/schema.sql:2330`](../../../../gcp/schema.sql#L2330) |
| `ticker_info` | table | [`gcp/schema.sql:2156`](../../../../gcp/schema.sql#L2156) |
| `top_movers_daily` | table | [`gcp/schema.sql:990`](../../../../gcp/schema.sql#L990) |
| `top_movers_intraday` | table | [`gcp/schema.sql:1014`](../../../../gcp/schema.sql#L1014) |
| `trades` | table | [`gcp/schema.sql:1133`](../../../../gcp/schema.sql#L1133) |
| `user_preferences` | table | [`gcp/schema.sql:4024`](../../../../gcp/schema.sql#L4024) |
| `user_profile` | table | [`gcp/schema.sql:4055`](../../../../gcp/schema.sql#L4055) |
| `user_roles` | table | [`gcp/schema.sql:3973`](../../../../gcp/schema.sql#L3973) |
| `user_style_results` | table | [`gcp/schema.sql:3892`](../../../../gcp/schema.sql#L3892) |
| `waitlist_signups` | table | [`gcp/schema.sql:3879`](../../../../gcp/schema.sql#L3879) |
| `walk_forward_results` | table | [`gcp/schema.sql:3106`](../../../../gcp/schema.sql#L3106) |
| `watchlists` | table | [`gcp/schema.sql:2212`](../../../../gcp/schema.sql#L2212) |
| `earnings_event_outcomes` | materialized view | [`gcp/schema.sql:3547`](../../../../gcp/schema.sql#L3547) |
| `earnings_ticker_lean` | materialized view | [`gcp/schema.sql:3738`](../../../../gcp/schema.sql#L3738) |
| `v_etf_options_node` | view | [`gcp/schema.sql:294`](../../../../gcp/schema.sql#L294) |
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
<!-- inventory:dbtables:end -->

---

## 2. Write graph

A "write" is `upsert_dataframe` / `bulk_copy_upsert` / `bulk_insert_dataframe`, `INSERT INTO`, `UPDATE`, `DELETE FROM`, `to_sql`, `TRUNCATE`, `REFRESH MATERIALIZED VIEW` or `ON CONFLICT` within three lines of the table name, including through a module constant (`TABLE = "…"`). Writers under `scripts/` are one-shot or operator-run unless a Cloud Run Job's entrypoint names them (see §6).

<!-- inventory:writes:start -->
### `admin_refresh_leases`
- [`platform/api/routers/admin.py`](../../../../platform/api/routers/admin.py) — line [1275](../../../../platform/api/routers/admin.py#L1275), [1278](../../../../platform/api/routers/admin.py#L1278), [1301](../../../../platform/api/routers/admin.py#L1301)

### `archive_yahoo_earnings_options_snapshots`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_etf_options_snapshots`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_market_data_daily`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `archive_yahoo_market_data_intraday`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `backtest_reports`
- [`scripts/generate_backtest_report.py`](../../../../scripts/generate_backtest_report.py) — line [387](../../../../scripts/generate_backtest_report.py#L387)

### `backtest_sweeps`
- [`scripts/run_timeframe_sweep.py`](../../../../scripts/run_timeframe_sweep.py) — line [65](../../../../scripts/run_timeframe_sweep.py#L65)

### `backtest_trades`
- [`scripts/run_backtest.py`](../../../../scripts/run_backtest.py) — line [78](../../../../scripts/run_backtest.py#L78)

### `backtest_walk_forward_folds`
- [`scripts/run_walk_forward.py`](../../../../scripts/run_walk_forward.py) — line [144](../../../../scripts/run_walk_forward.py#L144)

### `daily_rates`
- [`gcp/fetchers/fetch_fred_rates.py`](../../../../gcp/fetchers/fetch_fred_rates.py) — line [113](../../../../gcp/fetchers/fetch_fred_rates.py#L113), [120](../../../../gcp/fetchers/fetch_fred_rates.py#L120), [170](../../../../gcp/fetchers/fetch_fred_rates.py#L170), [171](../../../../gcp/fetchers/fetch_fred_rates.py#L171)

### `earnings_calendar`
- [`gcp/fetchers/evaluate_ew_strikes.py`](../../../../gcp/fetchers/evaluate_ew_strikes.py) — line [170](../../../../gcp/fetchers/evaluate_ew_strikes.py#L170)
- [`scripts/fetch_earnings_calendar.py`](../../../../scripts/fetch_earnings_calendar.py) — line [1198](../../../../scripts/fetch_earnings_calendar.py#L1198)

### `earnings_calibration`
- [`scripts/calibrate_earnings.py`](../../../../scripts/calibrate_earnings.py) — line [156](../../../../scripts/calibrate_earnings.py#L156)

### `earnings_event_outcomes`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `earnings_history`
- [`gcp/fetchers/fetch_earnings_history.py`](../../../../gcp/fetchers/fetch_earnings_history.py) — line [536](../../../../gcp/fetchers/fetch_earnings_history.py#L536)

### `earnings_options_snapshots`
- [`gcp/fetchers/fetch_av_earnings_options_backfill.py`](../../../../gcp/fetchers/fetch_av_earnings_options_backfill.py) — line [348](../../../../gcp/fetchers/fetch_av_earnings_options_backfill.py#L348)
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [534](../../../../gcp/migrate_to_gcp.py#L534)

### `earnings_options_strategy_insights`
- [`scripts/backtest_playability.py`](../../../../scripts/backtest_playability.py) — line [997](../../../../scripts/backtest_playability.py#L997)

### `earnings_options_strategy_winners`
- [`scripts/backtest_playability.py`](../../../../scripts/backtest_playability.py) — line [1005](../../../../scripts/backtest_playability.py#L1005)

### `earnings_reactions`
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../../gcp/fetchers/compute_earnings_reactions.py) — line [771](../../../../gcp/fetchers/compute_earnings_reactions.py#L771)

### `earnings_ticker_lean`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `earnings_upcoming_with_history`
- [`gcp/refresh_earnings_views.py`](../../../../gcp/refresh_earnings_views.py) — line [168](../../../../gcp/refresh_earnings_views.py#L168), [301](../../../../gcp/refresh_earnings_views.py#L301), [306](../../../../gcp/refresh_earnings_views.py#L306), [363](../../../../gcp/refresh_earnings_views.py#L363)

### `economic_events`
- [`gcp/fetchers/fetch_economic_events.py`](../../../../gcp/fetchers/fetch_economic_events.py) — line [400](../../../../gcp/fetchers/fetch_economic_events.py#L400), [401](../../../../gcp/fetchers/fetch_economic_events.py#L401)

### `etf_options_daily_greeks`
- [`gcp/build_options_daily_greeks.py`](../../../../gcp/build_options_daily_greeks.py) — line [62](../../../../gcp/build_options_daily_greeks.py#L62)

### `etf_options_snapshots`
- [`gcp/fetchers/fetch_av_historical_options.py`](../../../../gcp/fetchers/fetch_av_historical_options.py) — line [162](../../../../gcp/fetchers/fetch_av_historical_options.py#L162)
- [`gcp/fetchers/fetch_av_realtime_options.py`](../../../../gcp/fetchers/fetch_av_realtime_options.py) — line [256](../../../../gcp/fetchers/fetch_av_realtime_options.py#L256)
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [379](../../../../gcp/migrate_to_gcp.py#L379), [438](../../../../gcp/migrate_to_gcp.py#L438), [450](../../../../gcp/migrate_to_gcp.py#L450), [491](../../../../gcp/migrate_to_gcp.py#L491)
- [`gcp/options_retention_job.py`](../../../../gcp/options_retention_job.py) — line [79](../../../../gcp/options_retention_job.py#L79)
- [`platform/api/routers/grid.py`](../../../../platform/api/routers/grid.py) — line [594](../../../../platform/api/routers/grid.py#L594)
- [`scripts/maintenance/compute_spx_greeks.py`](../../../../scripts/maintenance/compute_spx_greeks.py) — line [149](../../../../scripts/maintenance/compute_spx_greeks.py#L149)
- [`scripts/validate_track2_live.py`](../../../../scripts/validate_track2_live.py) — line [80](../../../../scripts/validate_track2_live.py#L80), [112](../../../../scripts/validate_track2_live.py#L112)

### `exit_config_overrides`
- [`scripts/run_param_sweep.py`](../../../../scripts/run_param_sweep.py) — line [134](../../../../scripts/run_param_sweep.py#L134)

### `historical_signals`
- [`gcp/historical_signals.py`](../../../../gcp/historical_signals.py) — line [114](../../../../gcp/historical_signals.py#L114), [117](../../../../gcp/historical_signals.py#L117), [221](../../../../gcp/historical_signals.py#L221)
- [`scripts/backfill_timeframe_tags.py`](../../../../scripts/backfill_timeframe_tags.py) — line [172](../../../../scripts/backfill_timeframe_tags.py#L172)
- [`scripts/run_historical_signals.py`](../../../../scripts/run_historical_signals.py) — line [112](../../../../scripts/run_historical_signals.py#L112)

### `indicator_correlation`
- [`gcp/indicator_correlation_job.py`](../../../../gcp/indicator_correlation_job.py) — line [725](../../../../gcp/indicator_correlation_job.py#L725), [726](../../../../gcp/indicator_correlation_job.py#L726)

### `insider_transactions`
- [`gcp/fetchers/fetch_insider_transactions.py`](../../../../gcp/fetchers/fetch_insider_transactions.py) — line [227](../../../../gcp/fetchers/fetch_insider_transactions.py#L227)

### `insight_reports`
- [`gcp/insight_pipeline_job.py`](../../../../gcp/insight_pipeline_job.py) — line [285](../../../../gcp/insight_pipeline_job.py#L285), [302](../../../../gcp/insight_pipeline_job.py#L302), [333](../../../../gcp/insight_pipeline_job.py#L333)
- [`platform/api/routers/insights.py`](../../../../platform/api/routers/insights.py) — line [349](../../../../platform/api/routers/insights.py#L349)
- [`scripts/generate_historical_report.py`](../../../../scripts/generate_historical_report.py) — line [67](../../../../scripts/generate_historical_report.py#L67)

### `insight_reports_history`
- [`gcp/insight_pipeline_job.py`](../../../../gcp/insight_pipeline_job.py) — line [261](../../../../gcp/insight_pipeline_job.py#L261)
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [169](../../../../scripts/backfill_history_tables.py#L169)

### `insight_runs`
- [`gcp/auto_refresh_top_n.py`](../../../../gcp/auto_refresh_top_n.py) — line [98](../../../../gcp/auto_refresh_top_n.py#L98)
- [`gcp/discord_interactions/main.py`](../../../../gcp/discord_interactions/main.py) — line [377](../../../../gcp/discord_interactions/main.py#L377)
- [`gcp/insight_pipeline_job.py`](../../../../gcp/insight_pipeline_job.py) — line [177](../../../../gcp/insight_pipeline_job.py#L177), [200](../../../../gcp/insight_pipeline_job.py#L200), [206](../../../../gcp/insight_pipeline_job.py#L206), [215](../../../../gcp/insight_pipeline_job.py#L215)
- [`platform/api/routers/insights.py`](../../../../platform/api/routers/insights.py) — line [262](../../../../platform/api/routers/insights.py#L262), [315](../../../../platform/api/routers/insights.py#L315), [321](../../../../platform/api/routers/insights.py#L321), [330](../../../../platform/api/routers/insights.py#L330)

### `intraday_flow_15m`
- [`gcp/build_intraday_flow.py`](../../../../gcp/build_intraday_flow.py) — line [73](../../../../gcp/build_intraday_flow.py#L73)

### `intraday_gex_15m`
- [`gcp/build_intraday_gex.py`](../../../../gcp/build_intraday_gex.py) — line [186](../../../../gcp/build_intraday_gex.py#L186)

### `job_runs`
- [`gcp/database.py`](../../../../gcp/database.py) — line [905](../../../../gcp/database.py#L905)

### `journal_entries`
- [`platform/api/routers/journal.py`](../../../../platform/api/routers/journal.py) — line [668](../../../../platform/api/routers/journal.py#L668), [1180](../../../../platform/api/routers/journal.py#L1180), [1234](../../../../platform/api/routers/journal.py#L1234)
- [`scripts/backfill_journal_embeddings.py`](../../../../scripts/backfill_journal_embeddings.py) — line [79](../../../../scripts/backfill_journal_embeddings.py#L79)

### `market_data_daily`
- [`gcp/backfill_ticker.py`](../../../../gcp/backfill_ticker.py) — line [329](../../../../gcp/backfill_ticker.py#L329), [436](../../../../gcp/backfill_ticker.py#L436), [504](../../../../gcp/backfill_ticker.py#L504)
- [`gcp/fetchers/backfill_daily_indicators.py`](../../../../gcp/fetchers/backfill_daily_indicators.py) — line [415](../../../../gcp/fetchers/backfill_daily_indicators.py#L415)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [436](../../../../gcp/fetchers/fetch_market_data.py#L436), [512](../../../../gcp/fetchers/fetch_market_data.py#L512), [520](../../../../gcp/fetchers/fetch_market_data.py#L520), [561](../../../../gcp/fetchers/fetch_market_data.py#L561), [938](../../../../gcp/fetchers/fetch_market_data.py#L938)
- [`gcp/fetchers/fetch_premarket_refresh.py`](../../../../gcp/fetchers/fetch_premarket_refresh.py) — line [215](../../../../gcp/fetchers/fetch_premarket_refresh.py#L215), [251](../../../../gcp/fetchers/fetch_premarket_refresh.py#L251), [256](../../../../gcp/fetchers/fetch_premarket_refresh.py#L256), [257](../../../../gcp/fetchers/fetch_premarket_refresh.py#L257), [258](../../../../gcp/fetchers/fetch_premarket_refresh.py#L258), [320](../../../../gcp/fetchers/fetch_premarket_refresh.py#L320)
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [134](../../../../gcp/migrate_to_gcp.py#L134), [186](../../../../gcp/migrate_to_gcp.py#L186), [667](../../../../gcp/migrate_to_gcp.py#L667)
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [256](../../../../gcp/premarket_brief.py#L256)
- [`scripts/backfill_and_replay.py`](../../../../scripts/backfill_and_replay.py) — line [324](../../../../scripts/backfill_and_replay.py#L324), [488](../../../../scripts/backfill_and_replay.py#L488)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [233](../../../../scripts/backfill_watchlist_data.py#L233)
- [`scripts/deep_backfill_ticker.py`](../../../../scripts/deep_backfill_ticker.py) — line [102](../../../../scripts/deep_backfill_ticker.py#L102)

### `market_data_intraday`
- [`gcp/backfill_ticker.py`](../../../../gcp/backfill_ticker.py) — line [525](../../../../gcp/backfill_ticker.py#L525)
- [`gcp/fetchers/fetch_alphavantage_intraday.py`](../../../../gcp/fetchers/fetch_alphavantage_intraday.py) — line [307](../../../../gcp/fetchers/fetch_alphavantage_intraday.py#L307)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [464](../../../../gcp/fetchers/fetch_market_data.py#L464)
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [210](../../../../gcp/migrate_to_gcp.py#L210), [244](../../../../gcp/migrate_to_gcp.py#L244), [247](../../../../gcp/migrate_to_gcp.py#L247)
- [`scripts/backfill_and_replay.py`](../../../../scripts/backfill_and_replay.py) — line [351](../../../../scripts/backfill_and_replay.py#L351)

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
- [`lib/agents/model_routing.py`](../../../../lib/agents/model_routing.py) — line [193](../../../../lib/agents/model_routing.py#L193)

### `news_sentiment`
- [`gcp/backfill_ticker.py`](../../../../gcp/backfill_ticker.py) — line [538](../../../../gcp/backfill_ticker.py#L538)
- [`gcp/fetchers/fetch_news_sentiment.py`](../../../../gcp/fetchers/fetch_news_sentiment.py) — line [375](../../../../gcp/fetchers/fetch_news_sentiment.py#L375), [376](../../../../gcp/fetchers/fetch_news_sentiment.py#L376)
- [`gcp/fetchers/fetch_rss_news.py`](../../../../gcp/fetchers/fetch_rss_news.py) — line [710](../../../../gcp/fetchers/fetch_rss_news.py#L710), [711](../../../../gcp/fetchers/fetch_rss_news.py#L711)
- [`scripts/backfill_and_replay.py`](../../../../scripts/backfill_and_replay.py) — line [652](../../../../scripts/backfill_and_replay.py#L652)
- [`scripts/backfill_news_sentiment.py`](../../../../scripts/backfill_news_sentiment.py) — line [101](../../../../scripts/backfill_news_sentiment.py#L101), [102](../../../../scripts/backfill_news_sentiment.py#L102)

### `options_daily_features`
- [`lib/features/experimental/options_derived.py`](../../../../lib/features/experimental/options_derived.py) — line [396](../../../../lib/features/experimental/options_derived.py#L396)

### `playbook_cards`
- [`scripts/analysis/phase6_playbook.py`](../../../../scripts/analysis/phase6_playbook.py) — line [990](../../../../scripts/analysis/phase6_playbook.py#L990), [993](../../../../scripts/analysis/phase6_playbook.py#L993), [1097](../../../../scripts/analysis/phase6_playbook.py#L1097)

### `playbook_cards_staging`
- [`platform/api/routers/backtest.py`](../../../../platform/api/routers/backtest.py) — line [875](../../../../platform/api/routers/backtest.py#L875)

### `premarket_analysis`
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [3295](../../../../gcp/premarket_brief.py#L3295), [3296](../../../../gcp/premarket_brief.py#L3296), [3311](../../../../gcp/premarket_brief.py#L3311), [3313](../../../../gcp/premarket_brief.py#L3313)
- [`gcp/premarket_playbook_resolver.py`](../../../../gcp/premarket_playbook_resolver.py) — line [478](../../../../gcp/premarket_playbook_resolver.py#L478)
- [`gcp/signal_monitor.py`](../../../../gcp/signal_monitor.py) — line [544](../../../../gcp/signal_monitor.py#L544)

### `premarket_analysis_history`
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [3268](../../../../gcp/premarket_brief.py#L3268), [3269](../../../../gcp/premarket_brief.py#L3269)
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [123](../../../../scripts/backfill_history_tables.py#L123)

### `ranker_runs`
- [`lib/agents/ranker/rank.py`](../../../../lib/agents/ranker/rank.py) — line [158](../../../../lib/agents/ranker/rank.py#L158)

### `realtime_gex_15m`
- [`gcp/build_realtime_gex.py`](../../../../gcp/build_realtime_gex.py) — line [128](../../../../gcp/build_realtime_gex.py#L128), [135](../../../../gcp/build_realtime_gex.py#L135)

### `regime_combo_results`
- [`gcp/regime_combo_job.py`](../../../../gcp/regime_combo_job.py) — line [189](../../../../gcp/regime_combo_job.py#L189), [190](../../../../gcp/regime_combo_job.py#L190)

### `sec_filings`
- [`gcp/fetchers/fetch_sec_filings.py`](../../../../gcp/fetchers/fetch_sec_filings.py) — line [581](../../../../gcp/fetchers/fetch_sec_filings.py#L581), [582](../../../../gcp/fetchers/fetch_sec_filings.py#L582), [583](../../../../gcp/fetchers/fetch_sec_filings.py#L583)

### `signal_alerts`
- [`gcp/signal_monitor.py`](../../../../gcp/signal_monitor.py) — line [1598](../../../../gcp/signal_monitor.py#L1598), [1599](../../../../gcp/signal_monitor.py#L1599), [1601](../../../../gcp/signal_monitor.py#L1601), [2204](../../../../gcp/signal_monitor.py#L2204)
- [`gcp/signal_monitor_eod_resolver.py`](../../../../gcp/signal_monitor_eod_resolver.py) — line [400](../../../../gcp/signal_monitor_eod_resolver.py#L400)
- [`scripts/backfill_signals.py`](../../../../scripts/backfill_signals.py) — line [227](../../../../scripts/backfill_signals.py#L227), [228](../../../../scripts/backfill_signals.py#L228)
- [`scripts/replay_signal_monitor.py`](../../../../scripts/replay_signal_monitor.py) — line [283](../../../../scripts/replay_signal_monitor.py#L283)

### `signal_metrics`
- [`scripts/signal_quality_report.py`](../../../../scripts/signal_quality_report.py) — line [426](../../../../scripts/signal_quality_report.py#L426), [461](../../../../scripts/signal_quality_report.py#L461), [656](../../../../scripts/signal_quality_report.py#L656)

### `strat_combo_results`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `strat_levels`
- [`lib/strat_levels.py`](../../../../lib/strat_levels.py) — line [1843](../../../../lib/strat_levels.py#L1843)

### `ticker_calibration`
- [`scripts/calibrate_thresholds.py`](../../../../scripts/calibrate_thresholds.py) — line [313](../../../../scripts/calibrate_thresholds.py#L313), [487](../../../../scripts/calibrate_thresholds.py#L487), [489](../../../../scripts/calibrate_thresholds.py#L489)

### `ticker_info`
- [`lib/ticker_info.py`](../../../../lib/ticker_info.py) — line [61](../../../../lib/ticker_info.py#L61), [66](../../../../lib/ticker_info.py#L66), [624](../../../../lib/ticker_info.py#L624), [629](../../../../lib/ticker_info.py#L629)

### `top_movers_daily`
- [`gcp/fetchers/fetch_top_movers.py`](../../../../gcp/fetchers/fetch_top_movers.py) — line [291](../../../../gcp/fetchers/fetch_top_movers.py#L291)

### `top_movers_intraday`
- [`gcp/fetchers/fetch_top_movers.py`](../../../../gcp/fetchers/fetch_top_movers.py) — line [261](../../../../gcp/fetchers/fetch_top_movers.py#L261)

### `trades`
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [716](../../../../gcp/migrate_to_gcp.py#L716), [735](../../../../gcp/migrate_to_gcp.py#L735)
- [`gcp/signal_monitor.py`](../../../../gcp/signal_monitor.py) — line [2218](../../../../gcp/signal_monitor.py#L2218)
- [`gcp/signal_monitor_eod_resolver.py`](../../../../gcp/signal_monitor_eod_resolver.py) — line [413](../../../../gcp/signal_monitor_eod_resolver.py#L413)
- [`gcp/trade_logger.py`](../../../../gcp/trade_logger.py) — line [68](../../../../gcp/trade_logger.py#L68), [71](../../../../gcp/trade_logger.py#L71)
- [`scripts/analysis/phase7_feedback_loop.py`](../../../../scripts/analysis/phase7_feedback_loop.py) — line [276](../../../../scripts/analysis/phase7_feedback_loop.py#L276)
- [`scripts/backfill_signals.py`](../../../../scripts/backfill_signals.py) — line [231](../../../../scripts/backfill_signals.py#L231), [232](../../../../scripts/backfill_signals.py#L232)
- [`scripts/strat_struct_backtest.py`](../../../../scripts/strat_struct_backtest.py) — line [154](../../../../scripts/strat_struct_backtest.py#L154)

### `user_preferences`
- [`platform/api/routers/preferences.py`](../../../../platform/api/routers/preferences.py) — line [175](../../../../platform/api/routers/preferences.py#L175)

### `user_profile`
- [`platform/api/routers/profile.py`](../../../../platform/api/routers/profile.py) — line [187](../../../../platform/api/routers/profile.py#L187)

### `user_roles`
- [`platform/api/routers/admin.py`](../../../../platform/api/routers/admin.py) — line [932](../../../../platform/api/routers/admin.py#L932), [945](../../../../platform/api/routers/admin.py#L945)

### `user_style_results`
- [`platform/api/routers/backtest.py`](../../../../platform/api/routers/backtest.py) — line [845](../../../../platform/api/routers/backtest.py#L845)

### `v_etf_options_node`
- _no writer found in gcp/, lib/, scripts/, platform/api_

### `waitlist_signups`
- [`platform/api/routers/waitlist.py`](../../../../platform/api/routers/waitlist.py) — line [111](../../../../platform/api/routers/waitlist.py#L111)

### `walk_forward_results`
- [`scripts/run_param_sweep.py`](../../../../scripts/run_param_sweep.py) — line [108](../../../../scripts/run_param_sweep.py#L108)

### `watchlists`
- [`gcp/backfill_ticker.py`](../../../../gcp/backfill_ticker.py) — line [242](../../../../gcp/backfill_ticker.py#L242), [246](../../../../gcp/backfill_ticker.py#L246)
- [`gcp/discord_interactions/main.py`](../../../../gcp/discord_interactions/main.py) — line [655](../../../../gcp/discord_interactions/main.py#L655), [691](../../../../gcp/discord_interactions/main.py#L691)
- [`gcp/fetchers/_watchlist.py`](../../../../gcp/fetchers/_watchlist.py) — line [258](../../../../gcp/fetchers/_watchlist.py#L258), [262](../../../../gcp/fetchers/_watchlist.py#L262), [263](../../../../gcp/fetchers/_watchlist.py#L263), [295](../../../../gcp/fetchers/_watchlist.py#L295)
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
- [`scripts/generate_backtest_report.py`](../../../../scripts/generate_backtest_report.py) — line [664](../../../../scripts/generate_backtest_report.py#L664), [666](../../../../scripts/generate_backtest_report.py#L666)

### `backtest_sweeps`
- [`scripts/generate_backtest_report.py`](../../../../scripts/generate_backtest_report.py) — line [175](../../../../scripts/generate_backtest_report.py#L175), [181](../../../../scripts/generate_backtest_report.py#L181), [184](../../../../scripts/generate_backtest_report.py#L184)

### `backtest_trades`
- [`scripts/generate_backtest_report.py`](../../../../scripts/generate_backtest_report.py) — line [141](../../../../scripts/generate_backtest_report.py#L141), [150](../../../../scripts/generate_backtest_report.py#L150), [153](../../../../scripts/generate_backtest_report.py#L153)
- [`scripts/run_pipeline.py`](../../../../scripts/run_pipeline.py) — line [72](../../../../scripts/run_pipeline.py#L72), [87](../../../../scripts/run_pipeline.py#L87)

### `backtest_walk_forward_folds`
- [`scripts/calibrate_iwm_strat.py`](../../../../scripts/calibrate_iwm_strat.py) — line [199](../../../../scripts/calibrate_iwm_strat.py#L199)
- [`scripts/generate_backtest_report.py`](../../../../scripts/generate_backtest_report.py) — line [214](../../../../scripts/generate_backtest_report.py#L214), [221](../../../../scripts/generate_backtest_report.py#L221), [224](../../../../scripts/generate_backtest_report.py#L224)

### `daily_rates`
- [`lib/options_exec_backtest/runner.py`](../../../../lib/options_exec_backtest/runner.py) — line [207](../../../../lib/options_exec_backtest/runner.py#L207), [214](../../../../lib/options_exec_backtest/runner.py#L214)
- [`lib/options_greeks.py`](../../../../lib/options_greeks.py) — line [196](../../../../lib/options_greeks.py#L196), [202](../../../../lib/options_greeks.py#L202)

### `earnings_calendar`
- [`gcp/earnings_long_watchlist.py`](../../../../gcp/earnings_long_watchlist.py) — line [149](../../../../gcp/earnings_long_watchlist.py#L149)
- [`gcp/earnings_reactions_brief.py`](../../../../gcp/earnings_reactions_brief.py) — line [293](../../../../gcp/earnings_reactions_brief.py#L293)
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../../gcp/fetchers/compute_earnings_reactions.py) — line [567](../../../../gcp/fetchers/compute_earnings_reactions.py#L567), [827](../../../../gcp/fetchers/compute_earnings_reactions.py#L827)
- [`gcp/fetchers/evaluate_ew_strikes.py`](../../../../gcp/fetchers/evaluate_ew_strikes.py) — line [152](../../../../gcp/fetchers/evaluate_ew_strikes.py#L152)
- [`gcp/fetchers/fetch_earnings_history.py`](../../../../gcp/fetchers/fetch_earnings_history.py) — line [251](../../../../gcp/fetchers/fetch_earnings_history.py#L251), [265](../../../../gcp/fetchers/fetch_earnings_history.py#L265), [295](../../../../gcp/fetchers/fetch_earnings_history.py#L295)
- [`gcp/fetchers/fetch_insider_transactions.py`](../../../../gcp/fetchers/fetch_insider_transactions.py) — line [127](../../../../gcp/fetchers/fetch_insider_transactions.py#L127), [136](../../../../gcp/fetchers/fetch_insider_transactions.py#L136)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [630](../../../../gcp/fetchers/fetch_market_data.py#L630), [733](../../../../gcp/fetchers/fetch_market_data.py#L733)
- [`gcp/fetchers/fetch_news_sentiment.py`](../../../../gcp/fetchers/fetch_news_sentiment.py) — line [163](../../../../gcp/fetchers/fetch_news_sentiment.py#L163), [172](../../../../gcp/fetchers/fetch_news_sentiment.py#L172)
- [`gcp/fetchers/fetch_premarket_refresh.py`](../../../../gcp/fetchers/fetch_premarket_refresh.py) — line [86](../../../../gcp/fetchers/fetch_premarket_refresh.py#L86), [111](../../../../gcp/fetchers/fetch_premarket_refresh.py#L111)
- [`gcp/fetchers/fetch_sec_filings.py`](../../../../gcp/fetchers/fetch_sec_filings.py) — line [428](../../../../gcp/fetchers/fetch_sec_filings.py#L428), [437](../../../../gcp/fetchers/fetch_sec_filings.py#L437)
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [369](../../../../gcp/premarket_brief.py#L369), [769](../../../../gcp/premarket_brief.py#L769)
- [`gcp/refresh_earnings_views.py`](../../../../gcp/refresh_earnings_views.py) — line [157](../../../../gcp/refresh_earnings_views.py#L157)
- [`lib/agents/ranker/candidates.py`](../../../../lib/agents/ranker/candidates.py) — line [89](../../../../lib/agents/ranker/candidates.py#L89)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [1262](../../../../lib/agents/summarizers.py#L1262)
- [`lib/strategies/catalyst_proximity.py`](../../../../lib/strategies/catalyst_proximity.py) — line [235](../../../../lib/strategies/catalyst_proximity.py#L235)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [446](../../../../platform/api/routers/catalysts.py#L446), [453](../../../../platform/api/routers/catalysts.py#L453), [716](../../../../platform/api/routers/catalysts.py#L716)
- [`scripts/fetch_earnings_calendar.py`](../../../../scripts/fetch_earnings_calendar.py) — line [357](../../../../scripts/fetch_earnings_calendar.py#L357)

### `earnings_calibration`
- [`lib/earnings_reactions.py`](../../../../lib/earnings_reactions.py) — line [107](../../../../lib/earnings_reactions.py#L107), [434](../../../../lib/earnings_reactions.py#L434)
- [`platform/api/routers/earnings.py`](../../../../platform/api/routers/earnings.py) — line [309](../../../../platform/api/routers/earnings.py#L309)
- [`scripts/calibrate_earnings.py`](../../../../scripts/calibrate_earnings.py) — line [268](../../../../scripts/calibrate_earnings.py#L268)

### `earnings_event_outcomes`
- [`gcp/refresh_earnings_views.py`](../../../../gcp/refresh_earnings_views.py) — line [63](../../../../gcp/refresh_earnings_views.py#L63), [200](../../../../gcp/refresh_earnings_views.py#L200)
- [`platform/api/routers/earnings.py`](../../../../platform/api/routers/earnings.py) — line [153](../../../../platform/api/routers/earnings.py#L153), [178](../../../../platform/api/routers/earnings.py#L178)

### `earnings_history`
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../../gcp/fetchers/compute_earnings_reactions.py) — line [547](../../../../gcp/fetchers/compute_earnings_reactions.py#L547), [802](../../../../gcp/fetchers/compute_earnings_reactions.py#L802), [883](../../../../gcp/fetchers/compute_earnings_reactions.py#L883)
- [`gcp/fetchers/fetch_earnings_history.py`](../../../../gcp/fetchers/fetch_earnings_history.py) — line [330](../../../../gcp/fetchers/fetch_earnings_history.py#L330), [372](../../../../gcp/fetchers/fetch_earnings_history.py#L372), [374](../../../../gcp/fetchers/fetch_earnings_history.py#L374)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [715](../../../../gcp/fetchers/fetch_market_data.py#L715), [741](../../../../gcp/fetchers/fetch_market_data.py#L741)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [356](../../../../lib/agents/ranker/signals.py#L356)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [730](../../../../platform/api/routers/catalysts.py#L730)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [141](../../../../scripts/backfill_watchlist_data.py#L141)

### `earnings_options_snapshots`
- [`gcp/fetchers/fetch_av_earnings_options_backfill.py`](../../../../gcp/fetchers/fetch_av_earnings_options_backfill.py) — line [189](../../../../gcp/fetchers/fetch_av_earnings_options_backfill.py#L189)
- [`scripts/backtest_playability.py`](../../../../scripts/backtest_playability.py) — line [383](../../../../scripts/backtest_playability.py#L383), [551](../../../../scripts/backtest_playability.py#L551)

### `earnings_options_strategy_insights`
- [`platform/api/routers/earnings.py`](../../../../platform/api/routers/earnings.py) — line [263](../../../../platform/api/routers/earnings.py#L263), [270](../../../../platform/api/routers/earnings.py#L270)

### `earnings_options_strategy_winners`
- [`gcp/earnings_long_watchlist.py`](../../../../gcp/earnings_long_watchlist.py) — line [100](../../../../gcp/earnings_long_watchlist.py#L100), [130](../../../../gcp/earnings_long_watchlist.py#L130), [136](../../../../gcp/earnings_long_watchlist.py#L136)
- [`platform/api/routers/earnings.py`](../../../../platform/api/routers/earnings.py) — line [288](../../../../platform/api/routers/earnings.py#L288), [295](../../../../platform/api/routers/earnings.py#L295)

### `earnings_reactions`
- [`gcp/earnings_reactions_brief.py`](../../../../gcp/earnings_reactions_brief.py) — line [348](../../../../gcp/earnings_reactions_brief.py#L348)
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../../gcp/fetchers/compute_earnings_reactions.py) — line [867](../../../../gcp/fetchers/compute_earnings_reactions.py#L867), [883](../../../../gcp/fetchers/compute_earnings_reactions.py#L883)
- [`gcp/fetchers/fetch_av_earnings_options_backfill.py`](../../../../gcp/fetchers/fetch_av_earnings_options_backfill.py) — line [232](../../../../gcp/fetchers/fetch_av_earnings_options_backfill.py#L232)
- [`lib/earnings_reactions.py`](../../../../lib/earnings_reactions.py) — line [540](../../../../lib/earnings_reactions.py#L540), [704](../../../../lib/earnings_reactions.py#L704)
- [`scripts/analysis/earnings_reaction_walkforward.py`](../../../../scripts/analysis/earnings_reaction_walkforward.py) — line [440](../../../../scripts/analysis/earnings_reaction_walkforward.py#L440)
- [`scripts/backtest_playability.py`](../../../../scripts/backtest_playability.py) — line [77](../../../../scripts/backtest_playability.py#L77)

### `earnings_ticker_lean`
- [`gcp/refresh_earnings_views.py`](../../../../gcp/refresh_earnings_views.py) — line [63](../../../../gcp/refresh_earnings_views.py#L63), [179](../../../../gcp/refresh_earnings_views.py#L179)
- [`platform/api/routers/earnings.py`](../../../../platform/api/routers/earnings.py) — line [219](../../../../platform/api/routers/earnings.py#L219), [238](../../../../platform/api/routers/earnings.py#L238)

### `earnings_upcoming_with_history`
- [`platform/api/routers/earnings.py`](../../../../platform/api/routers/earnings.py) — line [122](../../../../platform/api/routers/earnings.py#L122), [124](../../../../platform/api/routers/earnings.py#L124)

### `economic_events`
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [846](../../../../gcp/premarket_brief.py#L846)
- [`gcp/research/magnitude_engine/mag_dataset.py`](../../../../gcp/research/magnitude_engine/mag_dataset.py) — line [131](../../../../gcp/research/magnitude_engine/mag_dataset.py#L131)
- [`lib/agents/ranker/candidates.py`](../../../../lib/agents/ranker/candidates.py) — line [195](../../../../lib/agents/ranker/candidates.py#L195)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [1253](../../../../lib/agents/summarizers.py#L1253)
- [`lib/gamma_glossary.py`](../../../../lib/gamma_glossary.py) — line [260](../../../../lib/gamma_glossary.py#L260)
- [`lib/strategies/catalyst_proximity.py`](../../../../lib/strategies/catalyst_proximity.py) — line [195](../../../../lib/strategies/catalyst_proximity.py#L195)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [416](../../../../platform/api/routers/catalysts.py#L416), [424](../../../../platform/api/routers/catalysts.py#L424)
- [`platform/api/routers/grid.py`](../../../../platform/api/routers/grid.py) — line [925](../../../../platform/api/routers/grid.py#L925)
- [`scripts/check_event_window_concentration.py`](../../../../scripts/check_event_window_concentration.py) — line [60](../../../../scripts/check_event_window_concentration.py#L60)

### `etf_options_daily_greeks`
- [`lib/features/flow_direction.py`](../../../../lib/features/flow_direction.py) — line [516](../../../../lib/features/flow_direction.py#L516)

### `etf_options_snapshots`
- [`gcp/build_intraday_gex.py`](../../../../gcp/build_intraday_gex.py) — line [61](../../../../gcp/build_intraday_gex.py#L61)
- [`gcp/build_realtime_gex.py`](../../../../gcp/build_realtime_gex.py) — line [64](../../../../gcp/build_realtime_gex.py#L64)
- [`gcp/fetchers/fetch_av_historical_options.py`](../../../../gcp/fetchers/fetch_av_historical_options.py) — line [134](../../../../gcp/fetchers/fetch_av_historical_options.py#L134), [232](../../../../gcp/fetchers/fetch_av_historical_options.py#L232)
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [303](../../../../gcp/migrate_to_gcp.py#L303)
- [`gcp/options_retention_job.py`](../../../../gcp/options_retention_job.py) — line [65](../../../../gcp/options_retention_job.py#L65), [68](../../../../gcp/options_retention_job.py#L68), [73](../../../../gcp/options_retention_job.py#L73), [75](../../../../gcp/options_retention_job.py#L75)
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [164](../../../../gcp/premarket_brief.py#L164), [191](../../../../gcp/premarket_brief.py#L191)
- [`gcp/research/p2_build_gamma_levels.py`](../../../../gcp/research/p2_build_gamma_levels.py) — line [126](../../../../gcp/research/p2_build_gamma_levels.py#L126)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../../gcp/research/p7_build_multi_tf_features.py) — line [161](../../../../gcp/research/p7_build_multi_tf_features.py#L161)
- [`gcp/research/strat_engine/breakout_meta_walk_forward.py`](../../../../gcp/research/strat_engine/breakout_meta_walk_forward.py) — line [117](../../../../gcp/research/strat_engine/breakout_meta_walk_forward.py#L117), [124](../../../../gcp/research/strat_engine/breakout_meta_walk_forward.py#L124)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../../gcp/research/strat_engine/strat_data_builder.py) — line [247](../../../../gcp/research/strat_engine/strat_data_builder.py#L247)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [113](../../../../lib/agents/ranker/signals.py#L113), [117](../../../../lib/agents/ranker/signals.py#L117)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [522](../../../../lib/agents/summarizers.py#L522), [527](../../../../lib/agents/summarizers.py#L527), [649](../../../../lib/agents/summarizers.py#L649), [655](../../../../lib/agents/summarizers.py#L655), [676](../../../../lib/agents/summarizers.py#L676), [682](../../../../lib/agents/summarizers.py#L682)
- [`lib/data_loader.py`](../../../../lib/data_loader.py) — line [556](../../../../lib/data_loader.py#L556)
- [`lib/features/experimental/options_derived.py`](../../../../lib/features/experimental/options_derived.py) — line [67](../../../../lib/features/experimental/options_derived.py#L67), [115](../../../../lib/features/experimental/options_derived.py#L115)
- [`lib/features/flow_direction.py`](../../../../lib/features/flow_direction.py) — line [408](../../../../lib/features/flow_direction.py#L408), [445](../../../../lib/features/flow_direction.py#L445)
- [`lib/options_exec_backtest/iv_lookup.py`](../../../../lib/options_exec_backtest/iv_lookup.py) — line [127](../../../../lib/options_exec_backtest/iv_lookup.py#L127)
- [`lib/options_intraday.py`](../../../../lib/options_intraday.py) — line [165](../../../../lib/options_intraday.py#L165)
- [`platform/api/routers/grid.py`](../../../../platform/api/routers/grid.py) — line [241](../../../../platform/api/routers/grid.py#L241), [247](../../../../platform/api/routers/grid.py#L247), [271](../../../../platform/api/routers/grid.py#L271), [277](../../../../platform/api/routers/grid.py#L277), [318](../../../../platform/api/routers/grid.py#L318), [324](../../../../platform/api/routers/grid.py#L324), [1162](../../../../platform/api/routers/grid.py#L1162)
- [`platform/api/routers/options.py`](../../../../platform/api/routers/options.py) — line [335](../../../../platform/api/routers/options.py#L335), [411](../../../../platform/api/routers/options.py#L411), [417](../../../../platform/api/routers/options.py#L417), [514](../../../../platform/api/routers/options.py#L514), [520](../../../../platform/api/routers/options.py#L520), [533](../../../../platform/api/routers/options.py#L533)
- [`scripts/analysis/calibrate_intraday_theta.py`](../../../../scripts/analysis/calibrate_intraday_theta.py) — line [52](../../../../scripts/analysis/calibrate_intraday_theta.py#L52)
- [`scripts/analysis/options_pnl_translation.py`](../../../../scripts/analysis/options_pnl_translation.py) — line [258](../../../../scripts/analysis/options_pnl_translation.py#L258), [359](../../../../scripts/analysis/options_pnl_translation.py#L359)
- [`scripts/audit_data_freshness.py`](../../../../scripts/audit_data_freshness.py) — line [979](../../../../scripts/audit_data_freshness.py#L979)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [125](../../../../scripts/backfill_watchlist_data.py#L125)
- [`scripts/implied_vs_realized_check.py`](../../../../scripts/implied_vs_realized_check.py) — line [114](../../../../scripts/implied_vs_realized_check.py#L114), [129](../../../../scripts/implied_vs_realized_check.py#L129)
- [`scripts/maintenance/compute_spx_greeks.py`](../../../../scripts/maintenance/compute_spx_greeks.py) — line [91](../../../../scripts/maintenance/compute_spx_greeks.py#L91), [101](../../../../scripts/maintenance/compute_spx_greeks.py#L101), [121](../../../../scripts/maintenance/compute_spx_greeks.py#L121)

### `exit_config_overrides`
- [`lib/strategies/exit_config_overrides.py`](../../../../lib/strategies/exit_config_overrides.py) — line [104](../../../../lib/strategies/exit_config_overrides.py#L104)
- [`scripts/run_param_sweep.py`](../../../../scripts/run_param_sweep.py) — line [143](../../../../scripts/run_param_sweep.py#L143)

### `historical_signals`
- [`gcp/historical_signals.py`](../../../../gcp/historical_signals.py) — line [95](../../../../gcp/historical_signals.py#L95), [98](../../../../gcp/historical_signals.py#L98)
- [`platform/api/routers/signals.py`](../../../../platform/api/routers/signals.py) — line [142](../../../../platform/api/routers/signals.py#L142), [165](../../../../platform/api/routers/signals.py#L165), [345](../../../../platform/api/routers/signals.py#L345), [387](../../../../platform/api/routers/signals.py#L387)
- [`scripts/analyze_timeframe_heuristic.py`](../../../../scripts/analyze_timeframe_heuristic.py) — line [316](../../../../scripts/analyze_timeframe_heuristic.py#L316), [476](../../../../scripts/analyze_timeframe_heuristic.py#L476)
- [`scripts/backfill_timeframe_tags.py`](../../../../scripts/backfill_timeframe_tags.py) — line [73](../../../../scripts/backfill_timeframe_tags.py#L73)
- [`scripts/signal_quality_report.py`](../../../../scripts/signal_quality_report.py) — line [382](../../../../scripts/signal_quality_report.py#L382)

### `indicator_correlation`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `insider_transactions`
- [`gcp/earnings_reactions_brief.py`](../../../../gcp/earnings_reactions_brief.py) — line [396](../../../../gcp/earnings_reactions_brief.py#L396)
- [`lib/agents/ranker/candidates.py`](../../../../lib/agents/ranker/candidates.py) — line [144](../../../../lib/agents/ranker/candidates.py#L144)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [422](../../../../lib/agents/ranker/signals.py#L422)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [488](../../../../platform/api/routers/catalysts.py#L488), [497](../../../../platform/api/routers/catalysts.py#L497), [703](../../../../platform/api/routers/catalysts.py#L703)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [148](../../../../scripts/backfill_watchlist_data.py#L148)

### `insight_reports`
- [`gcp/auto_refresh_top_n.py`](../../../../gcp/auto_refresh_top_n.py) — line [70](../../../../gcp/auto_refresh_top_n.py#L70)
- [`gcp/discord_interactions/main.py`](../../../../gcp/discord_interactions/main.py) — line [354](../../../../gcp/discord_interactions/main.py#L354), [357](../../../../gcp/discord_interactions/main.py#L357)
- [`gcp/insight_discord_push.py`](../../../../gcp/insight_discord_push.py) — line [86](../../../../gcp/insight_discord_push.py#L86), [97](../../../../gcp/insight_discord_push.py#L97), [663](../../../../gcp/insight_discord_push.py#L663)
- [`gcp/insight_pipeline_job.py`](../../../../gcp/insight_pipeline_job.py) — line [357](../../../../gcp/insight_pipeline_job.py#L357)
- [`lib/strategies/insight_cache.py`](../../../../lib/strategies/insight_cache.py) — line [274](../../../../lib/strategies/insight_cache.py#L274)
- [`platform/api/routers/insights.py`](../../../../platform/api/routers/insights.py) — line [163](../../../../platform/api/routers/insights.py#L163), [175](../../../../platform/api/routers/insights.py#L175), [196](../../../../platform/api/routers/insights.py#L196), [232](../../../../platform/api/routers/insights.py#L232)
- [`scripts/backfill_and_replay.py`](../../../../scripts/backfill_and_replay.py) — line [549](../../../../scripts/backfill_and_replay.py#L549)
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [154](../../../../scripts/backfill_history_tables.py#L154), [156](../../../../scripts/backfill_history_tables.py#L156), [188](../../../../scripts/backfill_history_tables.py#L188), [189](../../../../scripts/backfill_history_tables.py#L189)
- [`scripts/validation/validate_brief_accuracy.py`](../../../../scripts/validation/validate_brief_accuracy.py) — line [365](../../../../scripts/validation/validate_brief_accuracy.py#L365)

### `insight_reports_history`
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [159](../../../../scripts/backfill_history_tables.py#L159)

### `insight_runs`
- [`platform/api/routers/insights.py`](../../../../platform/api/routers/insights.py) — line [281](../../../../platform/api/routers/insights.py#L281)
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [174](../../../../scripts/backfill_history_tables.py#L174)

### `intraday_flow_15m`
- [`gcp/build_intraday_flow.py`](../../../../gcp/build_intraday_flow.py) — line [92](../../../../gcp/build_intraday_flow.py#L92)
- [`lib/features/intraday_flow.py`](../../../../lib/features/intraday_flow.py) — line [185](../../../../lib/features/intraday_flow.py#L185)

### `intraday_gex_15m`
- [`gcp/build_intraday_gex.py`](../../../../gcp/build_intraday_gex.py) — line [198](../../../../gcp/build_intraday_gex.py#L198)
- [`lib/features/intraday_gex.py`](../../../../lib/features/intraday_gex.py) — line [226](../../../../lib/features/intraday_gex.py#L226), [227](../../../../lib/features/intraday_gex.py#L227), [231](../../../../lib/features/intraday_gex.py#L231), [226](../../../../lib/features/intraday_gex.py#L226)

### `job_runs`
- [`scripts/audit_data_freshness.py`](../../../../scripts/audit_data_freshness.py) — line [1172](../../../../scripts/audit_data_freshness.py#L1172), [1173](../../../../scripts/audit_data_freshness.py#L1173), [1184](../../../../scripts/audit_data_freshness.py#L1184)

### `journal_entries`
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [1541](../../../../lib/agents/summarizers.py#L1541)
- [`platform/api/routers/backtest.py`](../../../../platform/api/routers/backtest.py) — line [545](../../../../platform/api/routers/backtest.py#L545), [717](../../../../platform/api/routers/backtest.py#L717)
- [`platform/api/routers/journal.py`](../../../../platform/api/routers/journal.py) — line [845](../../../../platform/api/routers/journal.py#L845), [882](../../../../platform/api/routers/journal.py#L882), [974](../../../../platform/api/routers/journal.py#L974), [1157](../../../../platform/api/routers/journal.py#L1157)
- [`scripts/backfill_journal_embeddings.py`](../../../../scripts/backfill_journal_embeddings.py) — line [59](../../../../scripts/backfill_journal_embeddings.py#L59)

### `market_data_daily`
- [`gcp/backfill_ticker.py`](../../../../gcp/backfill_ticker.py) — line [288](../../../../gcp/backfill_ticker.py#L288), [353](../../../../gcp/backfill_ticker.py#L353)
- [`gcp/build_intraday_gex.py`](../../../../gcp/build_intraday_gex.py) — line [79](../../../../gcp/build_intraday_gex.py#L79)
- [`gcp/discord_interactions/main.py`](../../../../gcp/discord_interactions/main.py) — line [332](../../../../gcp/discord_interactions/main.py#L332)
- [`gcp/fetchers/backfill_daily_indicators.py`](../../../../gcp/fetchers/backfill_daily_indicators.py) — line [117](../../../../gcp/fetchers/backfill_daily_indicators.py#L117), [216](../../../../gcp/fetchers/backfill_daily_indicators.py#L216), [222](../../../../gcp/fetchers/backfill_daily_indicators.py#L222), [252](../../../../gcp/fetchers/backfill_daily_indicators.py#L252)
- [`gcp/fetchers/compute_earnings_reactions.py`](../../../../gcp/fetchers/compute_earnings_reactions.py) — line [600](../../../../gcp/fetchers/compute_earnings_reactions.py#L600), [659](../../../../gcp/fetchers/compute_earnings_reactions.py#L659), [883](../../../../gcp/fetchers/compute_earnings_reactions.py#L883)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [299](../../../../gcp/fetchers/fetch_market_data.py#L299), [717](../../../../gcp/fetchers/fetch_market_data.py#L717), [725](../../../../gcp/fetchers/fetch_market_data.py#L725), [750](../../../../gcp/fetchers/fetch_market_data.py#L750), [1011](../../../../gcp/fetchers/fetch_market_data.py#L1011)
- [`gcp/fetchers/fetch_premarket_refresh.py`](../../../../gcp/fetchers/fetch_premarket_refresh.py) — line [146](../../../../gcp/fetchers/fetch_premarket_refresh.py#L146)
- [`gcp/migrate_to_gcp.py`](../../../../gcp/migrate_to_gcp.py) — line [147](../../../../gcp/migrate_to_gcp.py#L147)
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [365](../../../../gcp/premarket_brief.py#L365), [370](../../../../gcp/premarket_brief.py#L370), [770](../../../../gcp/premarket_brief.py#L770)
- [`gcp/premarket_playbook_resolver.py`](../../../../gcp/premarket_playbook_resolver.py) — line [116](../../../../gcp/premarket_playbook_resolver.py#L116)
- [`gcp/refresh_earnings_views.py`](../../../../gcp/refresh_earnings_views.py) — line [140](../../../../gcp/refresh_earnings_views.py#L140)
- [`gcp/research/p2_outcomes_grid.py`](../../../../gcp/research/p2_outcomes_grid.py) — line [144](../../../../gcp/research/p2_outcomes_grid.py#L144), [149](../../../../gcp/research/p2_outcomes_grid.py#L149)
- [`gcp/research/p45_deep_ds_job.py`](../../../../gcp/research/p45_deep_ds_job.py) — line [110](../../../../gcp/research/p45_deep_ds_job.py#L110), [111](../../../../gcp/research/p45_deep_ds_job.py#L111)
- [`gcp/research/p7_build_multi_tf_features.py`](../../../../gcp/research/p7_build_multi_tf_features.py) — line [112](../../../../gcp/research/p7_build_multi_tf_features.py#L112)
- [`gcp/research/strat_engine/strat_data_builder.py`](../../../../gcp/research/strat_engine/strat_data_builder.py) — line [198](../../../../gcp/research/strat_engine/strat_data_builder.py#L198)
- [`gcp/research/strat_engine/strat_data_pipeline.py`](../../../../gcp/research/strat_engine/strat_data_pipeline.py) — line [127](../../../../gcp/research/strat_engine/strat_data_pipeline.py#L127)
- [`gcp/research/strat_engine/strat_leakage_audit.py`](../../../../gcp/research/strat_engine/strat_leakage_audit.py) — line [112](../../../../gcp/research/strat_engine/strat_leakage_audit.py#L112), [114](../../../../gcp/research/strat_engine/strat_leakage_audit.py#L114), [116](../../../../gcp/research/strat_engine/strat_leakage_audit.py#L116)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [56](../../../../lib/agents/ranker/signals.py#L56), [134](../../../../lib/agents/ranker/signals.py#L134), [310](../../../../lib/agents/ranker/signals.py#L310), [357](../../../../lib/agents/ranker/signals.py#L357), [360](../../../../lib/agents/ranker/signals.py#L360)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [184](../../../../lib/agents/summarizers.py#L184), [204](../../../../lib/agents/summarizers.py#L204), [938](../../../../lib/agents/summarizers.py#L938), [1163](../../../../lib/agents/summarizers.py#L1163)
- [`lib/agents/trade_planner.py`](../../../../lib/agents/trade_planner.py) — line [96](../../../../lib/agents/trade_planner.py#L96)
- [`lib/data_loader.py`](../../../../lib/data_loader.py) — line [402](../../../../lib/data_loader.py#L402), [581](../../../../lib/data_loader.py#L581)
- [`lib/earnings_reactions.py`](../../../../lib/earnings_reactions.py) — line [594](../../../../lib/earnings_reactions.py#L594)
- [`lib/features/experimental/cross_asset.py`](../../../../lib/features/experimental/cross_asset.py) — line [45](../../../../lib/features/experimental/cross_asset.py#L45)
- [`lib/features/experimental/vol_regime.py`](../../../../lib/features/experimental/vol_regime.py) — line [52](../../../../lib/features/experimental/vol_regime.py#L52)
- [`platform/api/main.py`](../../../../platform/api/main.py) — line [1040](../../../../platform/api/main.py#L1040), [1115](../../../../platform/api/main.py#L1115), [1259](../../../../platform/api/main.py#L1259), [1429](../../../../platform/api/main.py#L1429), [1431](../../../../platform/api/main.py#L1431)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [743](../../../../platform/api/routers/catalysts.py#L743)
- [`platform/api/routers/dashboard.py`](../../../../platform/api/routers/dashboard.py) — line [149](../../../../platform/api/routers/dashboard.py#L149), [278](../../../../platform/api/routers/dashboard.py#L278)
- [`platform/api/routers/live.py`](../../../../platform/api/routers/live.py) — line [407](../../../../platform/api/routers/live.py#L407)
- [`scripts/audit_data_freshness.py`](../../../../scripts/audit_data_freshness.py) — line [964](../../../../scripts/audit_data_freshness.py#L964), [971](../../../../scripts/audit_data_freshness.py#L971), [1095](../../../../scripts/audit_data_freshness.py#L1095), [1103](../../../../scripts/audit_data_freshness.py#L1103)
- [`scripts/backfill_and_replay.py`](../../../../scripts/backfill_and_replay.py) — line [370](../../../../scripts/backfill_and_replay.py#L370), [542](../../../../scripts/backfill_and_replay.py#L542)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [109](../../../../scripts/backfill_watchlist_data.py#L109)
- [`scripts/deep_backfill_ticker.py`](../../../../scripts/deep_backfill_ticker.py) — line [127](../../../../scripts/deep_backfill_ticker.py#L127)
- [`scripts/strat_backtest.py`](../../../../scripts/strat_backtest.py) — line [37](../../../../scripts/strat_backtest.py#L37)

### `market_data_intraday`
- [`gcp/backfill_ticker.py`](../../../../gcp/backfill_ticker.py) — line [406](../../../../gcp/backfill_ticker.py#L406)
- [`gcp/build_intraday_gex.py`](../../../../gcp/build_intraday_gex.py) — line [106](../../../../gcp/build_intraday_gex.py#L106)
- [`gcp/build_realtime_gex.py`](../../../../gcp/build_realtime_gex.py) — line [99](../../../../gcp/build_realtime_gex.py#L99)
- [`gcp/fetchers/fetch_alphavantage_intraday.py`](../../../../gcp/fetchers/fetch_alphavantage_intraday.py) — line [207](../../../../gcp/fetchers/fetch_alphavantage_intraday.py#L207)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [391](../../../../gcp/fetchers/fetch_market_data.py#L391)
- [`gcp/historical_signals.py`](../../../../gcp/historical_signals.py) — line [285](../../../../gcp/historical_signals.py#L285)
- [`gcp/premarket_playbook_resolver.py`](../../../../gcp/premarket_playbook_resolver.py) — line [362](../../../../gcp/premarket_playbook_resolver.py#L362)
- [`gcp/research/strat_engine/breakout_meta_walk_forward.py`](../../../../gcp/research/strat_engine/breakout_meta_walk_forward.py) — line [339](../../../../gcp/research/strat_engine/breakout_meta_walk_forward.py#L339)
- [`gcp/signal_monitor.py`](../../../../gcp/signal_monitor.py) — line [1745](../../../../gcp/signal_monitor.py#L1745)
- [`lib/data_loader.py`](../../../../lib/data_loader.py) — line [301](../../../../lib/data_loader.py#L301)
- [`lib/features/intraday_flow.py`](../../../../lib/features/intraday_flow.py) — line [124](../../../../lib/features/intraday_flow.py#L124)
- [`lib/options_intraday.py`](../../../../lib/options_intraday.py) — line [591](../../../../lib/options_intraday.py#L591)
- [`platform/api/main.py`](../../../../platform/api/main.py) — line [622](../../../../platform/api/main.py#L622), [767](../../../../platform/api/main.py#L767), [1263](../../../../platform/api/main.py#L1263), [1617](../../../../platform/api/main.py#L1617), [1635](../../../../platform/api/main.py#L1635)
- [`scripts/analysis/per_ticker_calibration.py`](../../../../scripts/analysis/per_ticker_calibration.py) — line [208](../../../../scripts/analysis/per_ticker_calibration.py#L208)
- [`scripts/backfill_and_replay.py`](../../../../scripts/backfill_and_replay.py) — line [459](../../../../scripts/backfill_and_replay.py#L459)
- [`scripts/backfill_signals.py`](../../../../scripts/backfill_signals.py) — line [52](../../../../scripts/backfill_signals.py#L52)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [117](../../../../scripts/backfill_watchlist_data.py#L117)
- [`scripts/calibrate_thresholds.py`](../../../../scripts/calibrate_thresholds.py) — line [232](../../../../scripts/calibrate_thresholds.py#L232)
- [`scripts/compare_tier_fires.py`](../../../../scripts/compare_tier_fires.py) — line [65](../../../../scripts/compare_tier_fires.py#L65)
- [`scripts/replay_signal_monitor.py`](../../../../scripts/replay_signal_monitor.py) — line [118](../../../../scripts/replay_signal_monitor.py#L118), [225](../../../../scripts/replay_signal_monitor.py#L225)
- [`scripts/signal_quality_report.py`](../../../../scripts/signal_quality_report.py) — line [407](../../../../scripts/signal_quality_report.py#L407), [410](../../../../scripts/signal_quality_report.py#L410)
- [`scripts/validation/validate_brief_accuracy.py`](../../../../scripts/validation/validate_brief_accuracy.py) — line [247](../../../../scripts/validation/validate_brief_accuracy.py#L247), [311](../../../../scripts/validation/validate_brief_accuracy.py#L311), [538](../../../../scripts/validation/validate_brief_accuracy.py#L538)

### `market_data_intraday_iwm`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_other`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_qqq`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_spx`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `market_data_intraday_spy`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `model_routing`
- [`lib/agents/model_routing.py`](../../../../lib/agents/model_routing.py) — line [126](../../../../lib/agents/model_routing.py#L126)

### `news_sentiment`
- [`gcp/fetchers/fetch_news_sentiment.py`](../../../../gcp/fetchers/fetch_news_sentiment.py) — line [191](../../../../gcp/fetchers/fetch_news_sentiment.py#L191)
- [`gcp/insight_discord_push.py`](../../../../gcp/insight_discord_push.py) — line [264](../../../../gcp/insight_discord_push.py#L264), [280](../../../../gcp/insight_discord_push.py#L280)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [194](../../../../lib/agents/ranker/signals.py#L194), [268](../../../../lib/agents/ranker/signals.py#L268)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [1276](../../../../lib/agents/summarizers.py#L1276), [1437](../../../../lib/agents/summarizers.py#L1437), [1454](../../../../lib/agents/summarizers.py#L1454)
- [`lib/features/experimental/news_sentiment.py`](../../../../lib/features/experimental/news_sentiment.py) — line [83](../../../../lib/features/experimental/news_sentiment.py#L83)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [114](../../../../platform/api/routers/catalysts.py#L114), [677](../../../../platform/api/routers/catalysts.py#L677)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [133](../../../../scripts/backfill_watchlist_data.py#L133)

### `options_daily_features`
- [`lib/features/experimental/options_derived.py`](../../../../lib/features/experimental/options_derived.py) — line [355](../../../../lib/features/experimental/options_derived.py#L355)

### `playbook_cards`
- [`platform/api/routers/playbook.py`](../../../../platform/api/routers/playbook.py) — line [156](../../../../platform/api/routers/playbook.py#L156), [161](../../../../platform/api/routers/playbook.py#L161), [168](../../../../platform/api/routers/playbook.py#L168)
- [`scripts/audit_data_freshness.py`](../../../../scripts/audit_data_freshness.py) — line [218](../../../../scripts/audit_data_freshness.py#L218)

### `playbook_cards_staging`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `premarket_analysis`
- [`gcp/discord_interactions/main.py`](../../../../gcp/discord_interactions/main.py) — line [342](../../../../gcp/discord_interactions/main.py#L342), [345](../../../../gcp/discord_interactions/main.py#L345)
- [`gcp/premarket_brief.py`](../../../../gcp/premarket_brief.py) — line [3303](../../../../gcp/premarket_brief.py#L3303), [3348](../../../../gcp/premarket_brief.py#L3348)
- [`gcp/premarket_playbook_resolver.py`](../../../../gcp/premarket_playbook_resolver.py) — line [320](../../../../gcp/premarket_playbook_resolver.py#L320), [326](../../../../gcp/premarket_playbook_resolver.py#L326), [503](../../../../gcp/premarket_playbook_resolver.py#L503), [586](../../../../gcp/premarket_playbook_resolver.py#L586)
- [`lib/movement_statement.py`](../../../../lib/movement_statement.py) — line [321](../../../../lib/movement_statement.py#L321), [391](../../../../lib/movement_statement.py#L391)
- [`lib/strategies/brief_bias.py`](../../../../lib/strategies/brief_bias.py) — line [83](../../../../lib/strategies/brief_bias.py#L83)
- [`platform/api/routers/dashboard.py`](../../../../platform/api/routers/dashboard.py) — line [108](../../../../platform/api/routers/dashboard.py#L108), [116](../../../../platform/api/routers/dashboard.py#L116)
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [104](../../../../scripts/backfill_history_tables.py#L104), [106](../../../../scripts/backfill_history_tables.py#L106), [127](../../../../scripts/backfill_history_tables.py#L127), [128](../../../../scripts/backfill_history_tables.py#L128)
- [`scripts/validation/validate_brief_accuracy.py`](../../../../scripts/validation/validate_brief_accuracy.py) — line [336](../../../../scripts/validation/validate_brief_accuracy.py#L336)

### `premarket_analysis_history`
- [`scripts/backfill_history_tables.py`](../../../../scripts/backfill_history_tables.py) — line [109](../../../../scripts/backfill_history_tables.py#L109)

### `ranker_runs`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `realtime_gex_15m`
- [`gcp/build_realtime_gex.py`](../../../../gcp/build_realtime_gex.py) — line [146](../../../../gcp/build_realtime_gex.py#L146)
- [`lib/features/intraday_gex.py`](../../../../lib/features/intraday_gex.py) — line [226](../../../../lib/features/intraday_gex.py#L226)

### `regime_combo_results`
- [`gcp/regime_combo_job.py`](../../../../gcp/regime_combo_job.py) — line [51](../../../../gcp/regime_combo_job.py#L51)

### `sec_filings`
- [`lib/agents/ranker/candidates.py`](../../../../lib/agents/ranker/candidates.py) — line [116](../../../../lib/agents/ranker/candidates.py#L116)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [542](../../../../lib/agents/ranker/signals.py#L542)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [1291](../../../../lib/agents/summarizers.py#L1291)
- [`lib/strategies/catalyst_proximity.py`](../../../../lib/strategies/catalyst_proximity.py) — line [277](../../../../lib/strategies/catalyst_proximity.py#L277)
- [`platform/api/routers/catalysts.py`](../../../../platform/api/routers/catalysts.py) — line [529](../../../../platform/api/routers/catalysts.py#L529), [538](../../../../platform/api/routers/catalysts.py#L538), [687](../../../../platform/api/routers/catalysts.py#L687), [690](../../../../platform/api/routers/catalysts.py#L690)
- [`scripts/backfill_watchlist_data.py`](../../../../scripts/backfill_watchlist_data.py) — line [155](../../../../scripts/backfill_watchlist_data.py#L155)

### `signal_alerts`
- [`gcp/indicator_correlation_job.py`](../../../../gcp/indicator_correlation_job.py) — line [506](../../../../gcp/indicator_correlation_job.py#L506)
- [`gcp/signal_monitor_eod_resolver.py`](../../../../gcp/signal_monitor_eod_resolver.py) — line [141](../../../../gcp/signal_monitor_eod_resolver.py#L141)
- [`gcp/signal_quality_alarm.py`](../../../../gcp/signal_quality_alarm.py) — line [197](../../../../gcp/signal_quality_alarm.py#L197)
- [`gcp/signal_replay.py`](../../../../gcp/signal_replay.py) — line [109](../../../../gcp/signal_replay.py#L109), [117](../../../../gcp/signal_replay.py#L117)
- [`lib/agents/summarizers.py`](../../../../lib/agents/summarizers.py) — line [812](../../../../lib/agents/summarizers.py#L812), [829](../../../../lib/agents/summarizers.py#L829)
- [`platform/api/routers/journal.py`](../../../../platform/api/routers/journal.py) — line [1027](../../../../platform/api/routers/journal.py#L1027)
- [`scripts/analysis/per_factor_walkforward.py`](../../../../scripts/analysis/per_factor_walkforward.py) — line [254](../../../../scripts/analysis/per_factor_walkforward.py#L254)
- [`scripts/analysis/per_ticker_calibration.py`](../../../../scripts/analysis/per_ticker_calibration.py) — line [196](../../../../scripts/analysis/per_ticker_calibration.py#L196), [893](../../../../scripts/analysis/per_ticker_calibration.py#L893)
- [`scripts/analysis/verify_brief_bias.py`](../../../../scripts/analysis/verify_brief_bias.py) — line [153](../../../../scripts/analysis/verify_brief_bias.py#L153)

### `signal_metrics`
- [`gcp/signal_quality_alarm.py`](../../../../gcp/signal_quality_alarm.py) — line [174](../../../../gcp/signal_quality_alarm.py#L174), [198](../../../../gcp/signal_quality_alarm.py#L198)
- [`scripts/analyze_timeframe_heuristic.py`](../../../../scripts/analyze_timeframe_heuristic.py) — line [317](../../../../scripts/analyze_timeframe_heuristic.py#L317), [476](../../../../scripts/analyze_timeframe_heuristic.py#L476)
- [`scripts/backfill_timeframe_tags.py`](../../../../scripts/backfill_timeframe_tags.py) — line [74](../../../../scripts/backfill_timeframe_tags.py#L74)

### `strat_combo_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `strat_levels`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `ticker_calibration`
- [`lib/strategies/calibration.py`](../../../../lib/strategies/calibration.py) — line [91](../../../../lib/strategies/calibration.py#L91), [110](../../../../lib/strategies/calibration.py#L110), [119](../../../../lib/strategies/calibration.py#L119)
- [`scripts/analysis/per_ticker_calibration.py`](../../../../scripts/analysis/per_ticker_calibration.py) — line [216](../../../../scripts/analysis/per_ticker_calibration.py#L216)
- [`scripts/refresh_calibration_table.py`](../../../../scripts/refresh_calibration_table.py) — line [74](../../../../scripts/refresh_calibration_table.py#L74)

### `ticker_info`
- [`lib/ticker_info.py`](../../../../lib/ticker_info.py) — line [102](../../../../lib/ticker_info.py#L102)

### `top_movers_daily`
- [`lib/agents/ranker/candidates.py`](../../../../lib/agents/ranker/candidates.py) — line [169](../../../../lib/agents/ranker/candidates.py#L169)
- [`lib/agents/ranker/signals.py`](../../../../lib/agents/ranker/signals.py) — line [496](../../../../lib/agents/ranker/signals.py#L496)

### `top_movers_intraday`
- [`platform/api/main.py`](../../../../platform/api/main.py) — line [1541](../../../../platform/api/main.py#L1541), [1542](../../../../platform/api/main.py#L1542)

### `trades`
- [`gcp/research/strat_engine/strat_walk_forward.py`](../../../../gcp/research/strat_engine/strat_walk_forward.py) — line [513](../../../../gcp/research/strat_engine/strat_walk_forward.py#L513)
- [`gcp/trade_logger.py`](../../../../gcp/trade_logger.py) — line [94](../../../../gcp/trade_logger.py#L94), [117](../../../../gcp/trade_logger.py#L117), [143](../../../../gcp/trade_logger.py#L143)
- [`lib/backtest.py`](../../../../lib/backtest.py) — line [326](../../../../lib/backtest.py#L326)
- [`lib/data_loader.py`](../../../../lib/data_loader.py) — line [615](../../../../lib/data_loader.py#L615)
- [`platform/api/routers/analytics.py`](../../../../platform/api/routers/analytics.py) — line [138](../../../../platform/api/routers/analytics.py#L138), [143](../../../../platform/api/routers/analytics.py#L143)
- [`platform/api/routers/journal.py`](../../../../platform/api/routers/journal.py) — line [1024](../../../../platform/api/routers/journal.py#L1024), [1314](../../../../platform/api/routers/journal.py#L1314)
- [`scripts/analysis/phase4_setup_discovery.py`](../../../../scripts/analysis/phase4_setup_discovery.py) — line [270](../../../../scripts/analysis/phase4_setup_discovery.py#L270)
- [`scripts/run_pipeline.py`](../../../../scripts/run_pipeline.py) — line [71](../../../../scripts/run_pipeline.py#L71), [87](../../../../scripts/run_pipeline.py#L87)

### `user_preferences`
- [`platform/api/routers/preferences.py`](../../../../platform/api/routers/preferences.py) — line [123](../../../../platform/api/routers/preferences.py#L123)

### `user_profile`
- [`platform/api/routers/profile.py`](../../../../platform/api/routers/profile.py) — line [136](../../../../platform/api/routers/profile.py#L136)

### `user_roles`
- [`platform/api/auth.py`](../../../../platform/api/auth.py) — line [230](../../../../platform/api/auth.py#L230), [275](../../../../platform/api/auth.py#L275)
- [`platform/api/routers/admin.py`](../../../../platform/api/routers/admin.py) — line [809](../../../../platform/api/routers/admin.py#L809)

### `user_style_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `v_etf_options_node`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `waitlist_signups`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `walk_forward_results`
- _no readr found in gcp/, lib/, scripts/, platform/api_

### `watchlists`
- [`gcp/discord_interactions/main.py`](../../../../gcp/discord_interactions/main.py) — line [178](../../../../gcp/discord_interactions/main.py#L178), [711](../../../../gcp/discord_interactions/main.py#L711)
- [`gcp/fetchers/_watchlist.py`](../../../../gcp/fetchers/_watchlist.py) — line [90](../../../../gcp/fetchers/_watchlist.py#L90)
- [`gcp/fetchers/fetch_market_data.py`](../../../../gcp/fetchers/fetch_market_data.py) — line [737](../../../../gcp/fetchers/fetch_market_data.py#L737)
- [`gcp/insight_pipeline_job.py`](../../../../gcp/insight_pipeline_job.py) — line [478](../../../../gcp/insight_pipeline_job.py#L478)
- [`scripts/analysis/per_ticker_calibration.py`](../../../../scripts/analysis/per_ticker_calibration.py) — line [227](../../../../scripts/analysis/per_ticker_calibration.py#L227), [890](../../../../scripts/analysis/per_ticker_calibration.py#L890)
- [`scripts/run_historical_signals.py`](../../../../scripts/run_historical_signals.py) — line [94](../../../../scripts/run_historical_signals.py#L94)
<!-- inventory:reads:end -->

---

## 4. Multi-writer tables (coordination risks)

Tables with two or more writing files. The risk in each case is the same shape: two writers with different conflict keys or different column subsets on the same row.

<!-- inventory:multiwriter:start -->
| Table | Writers | Files |
|---|---|---|
| `earnings_calendar` | 2 | `gcp/fetchers/evaluate_ew_strikes.py`, `scripts/fetch_earnings_calendar.py` |
| `earnings_options_snapshots` | 2 | `gcp/fetchers/fetch_av_earnings_options_backfill.py`, `gcp/migrate_to_gcp.py` |
| `etf_options_snapshots` | 7 | `gcp/fetchers/fetch_av_historical_options.py`, `gcp/fetchers/fetch_av_realtime_options.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `platform/api/routers/grid.py`, `scripts/maintenance/compute_spx_greeks.py`, `scripts/validate_track2_live.py` |
| `historical_signals` | 3 | `gcp/historical_signals.py`, `scripts/backfill_timeframe_tags.py`, `scripts/run_historical_signals.py` |
| `insight_reports` | 3 | `gcp/insight_pipeline_job.py`, `platform/api/routers/insights.py`, `scripts/generate_historical_report.py` |
| `insight_reports_history` | 2 | `gcp/insight_pipeline_job.py`, `scripts/backfill_history_tables.py` |
| `insight_runs` | 4 | `gcp/auto_refresh_top_n.py`, `gcp/discord_interactions/main.py`, `gcp/insight_pipeline_job.py`, `platform/api/routers/insights.py` |
| `journal_entries` | 2 | `platform/api/routers/journal.py`, `scripts/backfill_journal_embeddings.py` |
| `market_data_daily` | 9 | `gcp/backfill_ticker.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `scripts/backfill_and_replay.py`, `scripts/backfill_watchlist_data.py`, `scripts/deep_backfill_ticker.py` |
| `market_data_intraday` | 5 | `gcp/backfill_ticker.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/migrate_to_gcp.py`, `scripts/backfill_and_replay.py` |
| `news_sentiment` | 5 | `gcp/backfill_ticker.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_rss_news.py`, `scripts/backfill_and_replay.py`, `scripts/backfill_news_sentiment.py` |
| `premarket_analysis` | 3 | `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/signal_monitor.py` |
| `premarket_analysis_history` | 2 | `gcp/premarket_brief.py`, `scripts/backfill_history_tables.py` |
| `signal_alerts` | 4 | `gcp/signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py`, `scripts/backfill_signals.py`, `scripts/replay_signal_monitor.py` |
| `trades` | 7 | `gcp/migrate_to_gcp.py`, `gcp/signal_monitor.py`, `gcp/signal_monitor_eod_resolver.py`, `gcp/trade_logger.py`, `scripts/analysis/phase7_feedback_loop.py`, `scripts/backfill_signals.py`, `scripts/strat_struct_backtest.py` |
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
| `earnings_event_outcomes` | 0 | 2 | read-only (no writer names it in code) |
| `earnings_ticker_lean` | 0 | 2 | read-only (no writer names it in code) |
| `indicator_correlation` | 1 | 0 | write-only (no reader in code) |
| `market_data_intraday_iwm` | 0 | 0 | partition of `market_data_intraday` — routed by Postgres, never named in code; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_other` | 0 | 0 | partition of `market_data_intraday` — routed by Postgres, never named in code; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_qqq` | 0 | 0 | partition of `market_data_intraday` — routed by Postgres, never named in code; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_spx` | 0 | 0 | partition of `market_data_intraday` — routed by Postgres, never named in code; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `market_data_intraday_spy` | 0 | 0 | partition of `market_data_intraday` — routed by Postgres, never named in code; name built at runtime in `gcp/research/p2_outcomes_grid.py`, `scripts/analysis/per_ticker_calibration.py` |
| `playbook_cards_staging` | 1 | 0 | write-only (no reader in code) |
| `ranker_runs` | 1 | 0 | write-only (no reader in code) |
| `strat_combo_results` | 0 | 0 | no writer and no reader in code |
| `strat_levels` | 1 | 0 | write-only (no reader in code) |
| `user_style_results` | 1 | 0 | write-only (no reader in code) |
| `v_etf_options_node` | 0 | 0 | no writer and no reader in code |
| `waitlist_signups` | 1 | 0 | write-only (no reader in code) |
| `walk_forward_results` | 1 | 0 | write-only (no reader in code) |
<!-- inventory:orphans:end -->

Reading the statuses: the four `archive_yahoo_*` tables are frozen forensics (0 rows live); `earnings_event_outcomes` / `earnings_ticker_lean` are materialized views refreshed by `gcp/refresh_earnings_views.py` (the `REFRESH MATERIALIZED VIEW` names reach the statement through the `_WEEKLY_VIEWS` tuple, so both are attributed to that job in §6); `ranker_runs`, `admin_refresh_leases`, `user_style_results`, `playbook_cards_staging`, `waitlist_signups` and `indicator_correlation` are write-only audit or staging tables; `strat_combo_results` and `v_etf_options_node` have no code reference and are drop candidates pending an operator decision.

---

## 6. Blast radius per Cloud Run Job

If the job stops, the listed readers lose fresh data from the tables it writes. Tables are attributed to the code reachable from the job's entrypoint: the whole entry module, then every name it imports from repo modules, what those definitions call, and each reached module's module-level statements, transitively (`gcp/backtest_job.py` → `scripts/run_backtest.py` → `DataLoader` in `lib/data_loader.py` → `market_data_daily`). A function that sits in an imported file but is never called is not attributed (`build_materialized()` in `lib/features/experimental/options_derived.py` writes `options_daily_features` only for `build-options-daily-features`, not for the magnitude jobs that import `add_options_features` from the same file). `job_runs` (written by `gcp/database.py` for every job) is excluded so it does not appear on every row.

<!-- inventory:blast:start -->
| Job | Entry module | Tables written (code reachable from the entry module through the names it imports) | Readers of those tables |
|---|---|---|---|
| `apply-schema-migrations` | `gcp/apply_schema.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-brief-bias` | `gcp/audit_job_runner.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-infra-drift` | `gcp/audit_infra_drift.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-magnitude-drift` | `gcp/audit_magnitude_drift.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `audit-walkforward` | `gcp/audit_job_runner.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `auto-refresh-top-n` | `gcp/auto_refresh_top_n.py` | `insight_runs`, `ranker_runs` | `platform/api/routers/insights.py`, `scripts/backfill_history_tables.py` |
| `backfill-daily-indicators` | `gcp/fetchers/backfill_daily_indicators.py` | `market_data_daily` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py`, `gcp/research/p45_deep_ds_job.py` (+20) |
| `backfill-ticker` | `gcp/backfill_ticker.py` | `market_data_daily`, `market_data_intraday`, `news_sentiment`, `watchlists` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/_watchlist.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/historical_signals.py`, `gcp/insight_discord_push.py` (+40) |
| `backtest` | `gcp/backtest_job.py` | `backtest_trades` | `scripts/generate_backtest_report.py`, `scripts/run_pipeline.py` |
| `backtest-pipeline` | `scripts/run_pipeline.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `build-options-daily-features` | `gcp/fetchers/build_options_daily_features.py` | `options_daily_features` | — |
| `build-options-greeks` | `gcp/build_options_daily_greeks.py` | `etf_options_daily_greeks` | — |
| `build-realtime-gex` | `gcp/build_realtime_gex.py` | `realtime_gex_15m` | — |
| `calibrate-thresholds` | `scripts/calibrate_thresholds.py` | `ticker_calibration` | `lib/strategies/calibration.py`, `scripts/analysis/per_ticker_calibration.py`, `scripts/refresh_calibration_table.py` |
| `cloud-sql-weekly-export` | `gcp/sql_export_to_gcs.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `compute-earnings-reactions` | `gcp/fetchers/compute_earnings_reactions.py` | `earnings_reactions` | `gcp/earnings_reactions_brief.py`, `gcp/fetchers/fetch_av_earnings_options_backfill.py`, `lib/earnings_reactions.py`, `scripts/analysis/earnings_reaction_walkforward.py`, `scripts/backtest_playability.py` |
| `compute-spx-greeks-backfill` | `scripts/maintenance/compute_spx_greeks.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py` (+11) |
| `db-query` | `gcp/db_query_job.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-baseline` | `gcp/research/direction_program/baseline_runner.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-importance` | `gcp/research/direction_program/feature_importance.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-phase2` | `gcp/research/direction_program/phase2_ablation.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `direction-probe` | `gcp/research/strat_engine/strat_dir_probes.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `earnings-long-watchlist` | `gcp/earnings_long_watchlist.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `earnings-options-backfill` | `gcp/fetchers/fetch_av_earnings_options_backfill.py` | `earnings_options_snapshots` | `scripts/backtest_playability.py` |
| `earnings-reactions-brief` | `gcp/earnings_reactions_brief.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `earnings-sweep` | `scripts/calibrate_earnings.py` | `earnings_calibration`, `earnings_options_strategy_insights`, `earnings_options_strategy_winners` | `gcp/earnings_long_watchlist.py`, `platform/api/routers/earnings.py` |
| `etf-options-retention` | `gcp/options_retention_job.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/data_loader.py` (+12) |
| `evaluate-ew-strikes` | `gcp/fetchers/evaluate_ew_strikes.py` | `earnings_calendar` | `gcp/earnings_long_watchlist.py`, `gcp/earnings_reactions_brief.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_earnings_history.py`, `gcp/fetchers/fetch_insider_transactions.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/fetchers/fetch_sec_filings.py`, `gcp/premarket_brief.py`, `gcp/refresh_earnings_views.py`, `lib/agents/ranker/candidates.py`, `lib/agents/summarizers.py` (+3) |
| `fetch-alphavantage-intraday` | `gcp/fetchers/fetch_alphavantage_intraday.py` | `market_data_intraday` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/historical_signals.py`, `gcp/premarket_playbook_resolver.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/signal_monitor.py`, `lib/data_loader.py`, `lib/features/intraday_flow.py`, `lib/options_intraday.py`, `platform/api/main.py` (+9) |
| `fetch-av-options-backfill` | `gcp/fetchers/fetch_av_historical_options.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/data_loader.py` (+12) |
| `fetch-av-options-realtime` | `gcp/fetchers/fetch_av_realtime_options.py` | `etf_options_snapshots` | `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_av_historical_options.py`, `gcp/migrate_to_gcp.py`, `gcp/options_retention_job.py`, `gcp/premarket_brief.py`, `gcp/research/p2_build_gamma_levels.py`, `gcp/research/p7_build_multi_tf_features.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/research/strat_engine/strat_data_builder.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py` (+13) |
| `fetch-earnings-calendar` | `scripts/fetch_earnings_calendar.py` | `earnings_calendar` | `gcp/earnings_long_watchlist.py`, `gcp/earnings_reactions_brief.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/evaluate_ew_strikes.py`, `gcp/fetchers/fetch_earnings_history.py`, `gcp/fetchers/fetch_insider_transactions.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_news_sentiment.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/fetchers/fetch_sec_filings.py`, `gcp/premarket_brief.py`, `gcp/refresh_earnings_views.py` (+4) |
| `fetch-earnings-history` | `gcp/fetchers/fetch_earnings_history.py` | `earnings_history`, `market_data_daily` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py`, `gcp/research/p45_deep_ds_job.py` (+20) |
| `fetch-economic-events` | `gcp/fetchers/fetch_economic_events.py` | `economic_events` | `gcp/premarket_brief.py`, `gcp/research/magnitude_engine/mag_dataset.py`, `lib/agents/ranker/candidates.py`, `lib/agents/summarizers.py`, `lib/gamma_glossary.py`, `lib/strategies/catalyst_proximity.py`, `platform/api/routers/catalysts.py`, `platform/api/routers/grid.py`, `scripts/check_event_window_concentration.py` |
| `fetch-fred-rates` | `gcp/fetchers/fetch_fred_rates.py` | `daily_rates` | `lib/options_exec_backtest/runner.py`, `lib/options_greeks.py` |
| `fetch-insider-transactions` | `gcp/fetchers/fetch_insider_transactions.py` | `insider_transactions` | `gcp/earnings_reactions_brief.py`, `lib/agents/ranker/candidates.py`, `lib/agents/ranker/signals.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-market-data` | `gcp/fetchers/fetch_market_data.py` | `market_data_daily`, `market_data_intraday` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_alphavantage_intraday.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/historical_signals.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py` (+34) |
| `fetch-news-sentiment` | `gcp/fetchers/fetch_news_sentiment.py` | `news_sentiment` | `gcp/insight_discord_push.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/features/experimental/news_sentiment.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-news-sentiment-earnings` | `gcp/fetchers/fetch_news_sentiment.py` | `news_sentiment` | `gcp/insight_discord_push.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/features/experimental/news_sentiment.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-news-sentiment-topics` | `gcp/fetchers/fetch_news_sentiment.py` | `news_sentiment` | `gcp/insight_discord_push.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/features/experimental/news_sentiment.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-premarket-refresh` | `gcp/fetchers/fetch_premarket_refresh.py` | `market_data_daily` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py`, `gcp/research/p45_deep_ds_job.py`, `gcp/research/p7_build_multi_tf_features.py` (+19) |
| `fetch-sec-filings` | `gcp/fetchers/fetch_sec_filings.py` | `sec_filings` | `lib/agents/ranker/candidates.py`, `lib/agents/ranker/signals.py`, `lib/agents/summarizers.py`, `lib/strategies/catalyst_proximity.py`, `platform/api/routers/catalysts.py`, `scripts/backfill_watchlist_data.py` |
| `fetch-top-movers` | `gcp/fetchers/fetch_top_movers.py` | `top_movers_daily`, `top_movers_intraday` | `lib/agents/ranker/candidates.py`, `lib/agents/ranker/signals.py`, `platform/api/main.py` |
| `freshness-watchdog` | `scripts/audit_data_freshness.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `historical-signals-watchlist` | `scripts/run_historical_signals.py` | `historical_signals` | `platform/api/routers/signals.py`, `scripts/analyze_timeframe_heuristic.py`, `scripts/backfill_timeframe_tags.py`, `scripts/signal_quality_report.py` |
| `indicator-correlation` | `gcp/indicator_correlation_job.py` | `indicator_correlation` | — |
| `insight-discord-push` | `gcp/insight_discord_push.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `insight-pipeline` | `gcp/insight_pipeline_job.py` | `insight_reports`, `insight_reports_history`, `insight_runs` | `gcp/auto_refresh_top_n.py`, `gcp/discord_interactions/main.py`, `gcp/insight_discord_push.py`, `lib/strategies/insight_cache.py`, `platform/api/routers/insights.py`, `scripts/backfill_and_replay.py`, `scripts/backfill_history_tables.py`, `scripts/validation/validate_brief_accuracy.py` |
| `intraday-bulk-backfill` | `gcp/fetchers/fetch_alphavantage_intraday.py` | `market_data_intraday` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/build_realtime_gex.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/historical_signals.py`, `gcp/premarket_playbook_resolver.py`, `gcp/research/strat_engine/breakout_meta_walk_forward.py`, `gcp/signal_monitor.py`, `lib/data_loader.py`, `lib/features/intraday_flow.py`, `lib/options_intraday.py`, `platform/api/main.py` (+9) |
| `magnitude-engine` | `gcp/research/magnitude_engine/mag_walk_forward.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `magnitude-inference` | `gcp/research/magnitude_engine/mag_inference.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `magnitude-recal` | `gcp/research/magnitude_engine/mag_walk_forward.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `options-exec-backtest` | `lib/options_exec_backtest/cli.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `param-sweep` | `scripts/run_param_sweep.py` | `exit_config_overrides`, `walk_forward_results` | — |
| `phase6-playbook` | `scripts/analysis/phase6_playbook.py` | `playbook_cards` | `platform/api/routers/playbook.py`, `scripts/audit_data_freshness.py` |
| `premarket-brief` | `gcp/premarket_brief.py` | `market_data_daily`, `premarket_analysis`, `premarket_analysis_history`, `strat_levels` | `gcp/backfill_ticker.py`, `gcp/build_intraday_gex.py`, `gcp/discord_interactions/main.py`, `gcp/fetchers/backfill_daily_indicators.py`, `gcp/fetchers/compute_earnings_reactions.py`, `gcp/fetchers/fetch_market_data.py`, `gcp/fetchers/fetch_premarket_refresh.py`, `gcp/migrate_to_gcp.py`, `gcp/premarket_playbook_resolver.py`, `gcp/refresh_earnings_views.py`, `gcp/research/p2_outcomes_grid.py`, `gcp/research/p45_deep_ds_job.py` (+20) |
| `premarket-playbook-resolver` | `gcp/premarket_playbook_resolver.py` | `premarket_analysis` | `gcp/discord_interactions/main.py`, `gcp/premarket_brief.py`, `lib/movement_statement.py`, `lib/strategies/brief_bias.py`, `platform/api/routers/dashboard.py`, `scripts/backfill_history_tables.py`, `scripts/validation/validate_brief_accuracy.py` |
| `refresh-earnings-views` | `gcp/refresh_earnings_views.py` | `earnings_upcoming_with_history` | `platform/api/routers/earnings.py` |
| `regime-combo` | `gcp/regime_combo_job.py` | `regime_combo_results` | — |
| `signal-monitor` | `gcp/signal_monitor.py` | `premarket_analysis`, `signal_alerts`, `trades` | `gcp/discord_interactions/main.py`, `gcp/indicator_correlation_job.py`, `gcp/premarket_brief.py`, `gcp/premarket_playbook_resolver.py`, `gcp/research/strat_engine/strat_walk_forward.py`, `gcp/signal_monitor_eod_resolver.py`, `gcp/signal_quality_alarm.py`, `gcp/signal_replay.py`, `lib/agents/summarizers.py`, `lib/backtest.py`, `lib/movement_statement.py`, `platform/api/routers/analytics.py` (+9) |
| `signal-monitor-eod-resolver` | `gcp/signal_monitor_eod_resolver.py` | `signal_alerts`, `trades` | `gcp/indicator_correlation_job.py`, `gcp/research/strat_engine/strat_walk_forward.py`, `gcp/signal_quality_alarm.py`, `gcp/signal_replay.py`, `gcp/trade_logger.py`, `lib/agents/summarizers.py`, `lib/backtest.py`, `platform/api/routers/analytics.py`, `platform/api/routers/journal.py`, `scripts/analysis/per_factor_walkforward.py`, `scripts/analysis/per_ticker_calibration.py`, `scripts/analysis/phase4_setup_discovery.py` (+2) |
| `signal-quality-alarm` | `gcp/signal_quality_alarm.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `signal-quality-report` | `scripts/signal_quality_report.py` | `signal_metrics` | `gcp/signal_quality_alarm.py`, `scripts/analyze_timeframe_heuristic.py`, `scripts/backfill_timeframe_tags.py` |
| `signal-replay` | `gcp/signal_replay.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `strat-engine` | `gcp/research/strat_engine/strat_data_builder.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `validate-brief` | `gcp/validate_brief_job.py` | — (Discord / GCS / no Cloud SQL write found) | — |
| `weekend-review` | `gcp/weekend_review.py` | `trades` | `gcp/research/strat_engine/strat_walk_forward.py`, `lib/backtest.py`, `lib/data_loader.py`, `platform/api/routers/analytics.py`, `platform/api/routers/journal.py`, `scripts/analysis/phase4_setup_discovery.py`, `scripts/run_pipeline.py` |
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
        J_direction_importance[direction-importance]
        J_direction_phase2[direction-phase2]
        J_direction_probe[direction-probe]
        J_earnings_long_watchlist[earnings-long-watchlist]
        J_earnings_options_backfill[earnings-options-backfill]
        J_earnings_reactions_brief[earnings-reactions-brief]
        J_earnings_sweep[earnings-sweep]
        J_etf_options_retention[etf-options-retention]
        J_evaluate_ew_strikes[evaluate-ew-strikes]
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
        T_backtest_trades[(backtest_trades)]
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
        T_intraday_flow_15m[(intraday_flow_15m)]
        T_intraday_gex_15m[(intraday_gex_15m)]
        T_job_runs[(job_runs)]
        T_journal_entries[(journal_entries)]
        T_market_data_daily[(market_data_daily)]
        T_market_data_intraday[(market_data_intraday)]
        T_model_routing[(model_routing)]
        T_news_sentiment[(news_sentiment)]
        T_options_daily_features[(options_daily_features)]
        T_playbook_cards[(playbook_cards)]
        T_premarket_analysis[(premarket_analysis)]
        T_premarket_analysis_history[(premarket_analysis_history)]
        T_ranker_runs[(ranker_runs)]
        T_realtime_gex_15m[(realtime_gex_15m)]
        T_regime_combo_results[(regime_combo_results)]
        T_sec_filings[(sec_filings)]
        T_signal_alerts[(signal_alerts)]
        T_signal_metrics[(signal_metrics)]
        T_strat_levels[(strat_levels)]
        T_ticker_calibration[(ticker_calibration)]
        T_top_movers_daily[(top_movers_daily)]
        T_top_movers_intraday[(top_movers_intraday)]
        T_trades[(trades)]
        T_walk_forward_results[(walk_forward_results)]
        T_watchlists[(watchlists)]
    end

    J_auto_refresh_top_n ==> T_insight_runs
    J_auto_refresh_top_n ==> T_ranker_runs
    J_backfill_daily_indicators ==> T_market_data_daily
    J_backfill_ticker ==> T_market_data_daily
    J_backfill_ticker ==> T_market_data_intraday
    J_backfill_ticker ==> T_news_sentiment
    J_backfill_ticker ==> T_watchlists
    J_backtest ==> T_backtest_trades
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
    J_evaluate_ew_strikes ==> T_earnings_calendar
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
    J_intraday_bulk_backfill ==> T_market_data_intraday
    J_param_sweep ==> T_exit_config_overrides
    J_param_sweep ==> T_walk_forward_results
    J_phase6_playbook ==> T_playbook_cards
    J_premarket_brief ==> T_market_data_daily
    J_premarket_brief ==> T_premarket_analysis
    J_premarket_brief ==> T_premarket_analysis_history
    J_premarket_brief ==> T_strat_levels
    J_premarket_playbook_resolver ==> T_premarket_analysis
    J_refresh_earnings_views ==> T_earnings_upcoming_with_history
    J_regime_combo ==> T_regime_combo_results
    J_signal_monitor ==> T_premarket_analysis
    J_signal_monitor ==> T_signal_alerts
    J_signal_monitor ==> T_trades
    J_signal_monitor_eod_resolver ==> T_signal_alerts
    J_signal_monitor_eod_resolver ==> T_trades
    J_signal_quality_report ==> T_signal_metrics
    J_weekend_review ==> T_trades

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
    T_market_data_daily --> J_backfill_ticker
    T_market_data_intraday --> J_backfill_ticker
    T_etf_options_snapshots --> J_backtest
    T_exit_config_overrides --> J_backtest
    T_market_data_daily --> J_backtest
    T_market_data_intraday --> J_backtest
    T_trades --> J_backtest
    T_backtest_trades --> J_backtest_pipeline
    T_trades --> J_backtest_pipeline
    T_etf_options_snapshots --> J_build_options_daily_features
    T_etf_options_snapshots --> J_build_options_greeks
    T_etf_options_snapshots --> J_build_realtime_gex
    T_market_data_intraday --> J_build_realtime_gex
    T_realtime_gex_15m --> J_build_realtime_gex
    T_market_data_intraday --> J_calibrate_thresholds
    T_earnings_calendar --> J_compute_earnings_reactions
    T_earnings_history --> J_compute_earnings_reactions
    T_earnings_reactions --> J_compute_earnings_reactions
    T_market_data_daily --> J_compute_earnings_reactions
    T_daily_rates --> J_compute_spx_greeks_backfill
    T_etf_options_snapshots --> J_compute_spx_greeks_backfill
    T_market_data_daily --> J_compute_spx_greeks_backfill
    T_market_data_intraday --> J_compute_spx_greeks_backfill
    T_trades --> J_compute_spx_greeks_backfill
    T_economic_events --> J_direction_baseline
    T_etf_options_snapshots --> J_direction_baseline
    T_options_daily_features --> J_direction_baseline
    T_economic_events --> J_direction_importance
    T_economic_events --> J_direction_phase2
    T_etf_options_snapshots --> J_direction_phase2
    T_options_daily_features --> J_direction_phase2
    T_etf_options_daily_greeks --> J_direction_probe
    T_intraday_flow_15m --> J_direction_probe
    T_intraday_gex_15m --> J_direction_probe
    T_realtime_gex_15m --> J_direction_probe
    T_earnings_calendar --> J_earnings_long_watchlist
    T_earnings_options_strategy_winners --> J_earnings_long_watchlist
    T_earnings_options_snapshots --> J_earnings_options_backfill
    T_earnings_reactions --> J_earnings_options_backfill
    T_earnings_calendar --> J_earnings_reactions_brief
    T_earnings_reactions --> J_earnings_reactions_brief
    T_etf_options_snapshots --> J_earnings_reactions_brief
    T_insider_transactions --> J_earnings_reactions_brief
    T_market_data_daily --> J_earnings_reactions_brief
    T_market_data_intraday --> J_earnings_reactions_brief
    T_trades --> J_earnings_reactions_brief
    T_earnings_calibration --> J_earnings_sweep
    T_earnings_options_snapshots --> J_earnings_sweep
    T_earnings_reactions --> J_earnings_sweep
    T_etf_options_snapshots --> J_etf_options_retention
    T_earnings_calendar --> J_evaluate_ew_strikes
    T_market_data_intraday --> J_fetch_alphavantage_intraday
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
    T_earnings_history --> J_fetch_market_data
    T_market_data_daily --> J_fetch_market_data
    T_market_data_intraday --> J_fetch_market_data
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
    T_market_data_daily --> J_fetch_premarket_refresh
    T_watchlists --> J_fetch_premarket_refresh
    T_earnings_calendar --> J_fetch_sec_filings
    T_watchlists --> J_fetch_sec_filings
    T_etf_options_snapshots --> J_freshness_watchdog
    T_job_runs --> J_freshness_watchdog
    T_market_data_daily --> J_freshness_watchdog
    T_playbook_cards --> J_freshness_watchdog
    T_earnings_calendar --> J_historical_signals_watchlist
    T_economic_events --> J_historical_signals_watchlist
    T_exit_config_overrides --> J_historical_signals_watchlist
    T_historical_signals --> J_historical_signals_watchlist
    T_market_data_intraday --> J_historical_signals_watchlist
    T_sec_filings --> J_historical_signals_watchlist
    T_watchlists --> J_historical_signals_watchlist
    T_etf_options_snapshots --> J_indicator_correlation
    T_market_data_daily --> J_indicator_correlation
    T_market_data_intraday --> J_indicator_correlation
    T_signal_alerts --> J_indicator_correlation
    T_trades --> J_indicator_correlation
    T_etf_options_snapshots --> J_insight_discord_push
    T_insight_reports --> J_insight_discord_push
    T_market_data_daily --> J_insight_discord_push
    T_market_data_intraday --> J_insight_discord_push
    T_news_sentiment --> J_insight_discord_push
    T_trades --> J_insight_discord_push
    T_daily_rates --> J_insight_pipeline
    T_earnings_calendar --> J_insight_pipeline
    T_economic_events --> J_insight_pipeline
    T_etf_options_snapshots --> J_insight_pipeline
    T_exit_config_overrides --> J_insight_pipeline
    T_insight_reports --> J_insight_pipeline
    T_journal_entries --> J_insight_pipeline
    T_market_data_daily --> J_insight_pipeline
    T_market_data_intraday --> J_insight_pipeline
    T_model_routing --> J_insight_pipeline
    T_news_sentiment --> J_insight_pipeline
    T_sec_filings --> J_insight_pipeline
    T_trades --> J_insight_pipeline
    T_watchlists --> J_insight_pipeline
    T_market_data_intraday --> J_intraday_bulk_backfill
    T_economic_events --> J_magnitude_engine
    T_etf_options_snapshots --> J_magnitude_engine
    T_options_daily_features --> J_magnitude_engine
    T_economic_events --> J_magnitude_recal
    T_etf_options_snapshots --> J_magnitude_recal
    T_options_daily_features --> J_magnitude_recal
    T_daily_rates --> J_options_exec_backtest
    T_etf_options_snapshots --> J_options_exec_backtest
    T_etf_options_snapshots --> J_param_sweep
    T_exit_config_overrides --> J_param_sweep
    T_market_data_daily --> J_param_sweep
    T_market_data_intraday --> J_param_sweep
    T_trades --> J_param_sweep
    T_etf_options_snapshots --> J_phase6_playbook
    T_market_data_daily --> J_phase6_playbook
    T_market_data_intraday --> J_phase6_playbook
    T_trades --> J_phase6_playbook
    T_earnings_calendar --> J_premarket_brief
    T_earnings_calibration --> J_premarket_brief
    T_earnings_reactions --> J_premarket_brief
    T_economic_events --> J_premarket_brief
    T_etf_options_snapshots --> J_premarket_brief
    T_market_data_daily --> J_premarket_brief
    T_market_data_intraday --> J_premarket_brief
    T_premarket_analysis --> J_premarket_brief
    T_trades --> J_premarket_brief
    T_watchlists --> J_premarket_brief
    T_market_data_daily --> J_premarket_playbook_resolver
    T_market_data_intraday --> J_premarket_playbook_resolver
    T_premarket_analysis --> J_premarket_playbook_resolver
    T_earnings_calendar --> J_refresh_earnings_views
    T_earnings_calibration --> J_refresh_earnings_views
    T_earnings_event_outcomes --> J_refresh_earnings_views
    T_earnings_ticker_lean --> J_refresh_earnings_views
    T_market_data_daily --> J_refresh_earnings_views
    T_etf_options_snapshots --> J_regime_combo
    T_market_data_daily --> J_regime_combo
    T_market_data_intraday --> J_regime_combo
    T_regime_combo_results --> J_regime_combo
    T_trades --> J_regime_combo
    T_earnings_calendar --> J_signal_monitor
    T_economic_events --> J_signal_monitor
    T_etf_options_snapshots --> J_signal_monitor
    T_exit_config_overrides --> J_signal_monitor
    T_insight_reports --> J_signal_monitor
    T_market_data_daily --> J_signal_monitor
    T_market_data_intraday --> J_signal_monitor
    T_premarket_analysis --> J_signal_monitor
    T_sec_filings --> J_signal_monitor
    T_ticker_calibration --> J_signal_monitor
    T_trades --> J_signal_monitor
    T_watchlists --> J_signal_monitor
    T_etf_options_snapshots --> J_signal_monitor_eod_resolver
    T_market_data_daily --> J_signal_monitor_eod_resolver
    T_market_data_intraday --> J_signal_monitor_eod_resolver
    T_signal_alerts --> J_signal_monitor_eod_resolver
    T_trades --> J_signal_monitor_eod_resolver
    T_signal_alerts --> J_signal_quality_alarm
    T_signal_metrics --> J_signal_quality_alarm
    T_historical_signals --> J_signal_quality_report
    T_market_data_intraday --> J_signal_quality_report
    T_signal_alerts --> J_signal_replay
    T_etf_options_snapshots --> J_strat_engine
    T_market_data_daily --> J_strat_engine
    T_market_data_intraday --> J_strat_engine
    T_trades --> J_strat_engine
    T_insight_reports --> J_validate_brief
    T_market_data_intraday --> J_validate_brief
    T_premarket_analysis --> J_validate_brief
    T_watchlists --> J_validate_brief
    T_trades --> J_weekend_review

    classDef job fill:#3B82F6,stroke:#1E40AF,color:#fff
    classDef tbl fill:#10B981,stroke:#065F46,color:#fff
    class J_auto_refresh_top_n,J_backfill_daily_indicators,J_backfill_ticker,J_backtest,J_backtest_pipeline,J_build_options_daily_features,J_build_options_greeks,J_build_realtime_gex,J_calibrate_thresholds,J_compute_earnings_reactions,J_compute_spx_greeks_backfill,J_direction_baseline,J_direction_importance,J_direction_phase2,J_direction_probe,J_earnings_long_watchlist,J_earnings_options_backfill,J_earnings_reactions_brief,J_earnings_sweep,J_etf_options_retention,J_evaluate_ew_strikes,J_fetch_alphavantage_intraday,J_fetch_av_options_backfill,J_fetch_av_options_realtime,J_fetch_earnings_calendar,J_fetch_earnings_history,J_fetch_economic_events,J_fetch_fred_rates,J_fetch_insider_transactions,J_fetch_market_data,J_fetch_news_sentiment,J_fetch_news_sentiment_earnings,J_fetch_news_sentiment_topics,J_fetch_premarket_refresh,J_fetch_sec_filings,J_fetch_top_movers,J_freshness_watchdog,J_historical_signals_watchlist,J_indicator_correlation,J_insight_discord_push,J_insight_pipeline,J_intraday_bulk_backfill,J_magnitude_engine,J_magnitude_recal,J_options_exec_backtest,J_param_sweep,J_phase6_playbook,J_premarket_brief,J_premarket_playbook_resolver,J_refresh_earnings_views,J_regime_combo,J_signal_monitor,J_signal_monitor_eod_resolver,J_signal_quality_alarm,J_signal_quality_report,J_signal_replay,J_strat_engine,J_validate_brief,J_weekend_review job
    class T_backtest_trades,T_daily_rates,T_earnings_calendar,T_earnings_calibration,T_earnings_event_outcomes,T_earnings_history,T_earnings_options_snapshots,T_earnings_options_strategy_insights,T_earnings_options_strategy_winners,T_earnings_reactions,T_earnings_ticker_lean,T_earnings_upcoming_with_history,T_economic_events,T_etf_options_daily_greeks,T_etf_options_snapshots,T_exit_config_overrides,T_historical_signals,T_indicator_correlation,T_insider_transactions,T_insight_reports,T_insight_reports_history,T_insight_runs,T_intraday_flow_15m,T_intraday_gex_15m,T_job_runs,T_journal_entries,T_market_data_daily,T_market_data_intraday,T_model_routing,T_news_sentiment,T_options_daily_features,T_playbook_cards,T_premarket_analysis,T_premarket_analysis_history,T_ranker_runs,T_realtime_gex_15m,T_regime_combo_results,T_sec_filings,T_signal_alerts,T_signal_metrics,T_strat_levels,T_ticker_calibration,T_top_movers_daily,T_top_movers_intraday,T_trades,T_walk_forward_results,T_watchlists tbl
```
<!-- inventory:graph:end -->

Rendered from `table_refs` by `scripts/maintenance/doc_inventory.py`: thick `==>` is a write by code reachable from the job's entry module through the names it imports, thin `-->` is a read by the same scope (the attribution rule is stated under §6). Every job with at least one edge and every table with at least one edge appears; `gcp/database.py`'s `job_runs` bookkeeping is excluded, as in §6.

---

## 8. Notes for follow-up work

1. `strat_combo_results` and `v_etf_options_node` have no writer or reader in code — confirm nobody queries them by hand, then drop.
2. `earnings_options_snapshots` has 0 live rows but 588 MB of dead space; its only production writer is the on-demand `earnings-options-backfill`. A `VACUUM FULL` or drop is an operator call.
3. `gcp/fetchers/fetch_rss_news.py` writes `news_sentiment` but has no `deploy_*` function and no scheduler.
4. The 26 runtime-created relations are outside the schema migration path (`gcp/schema.sql` + `apply-schema-migrations`) and outside `scripts/audit_data_freshness.py`; `strat_features_levels_1m` alone is 8 GB.
5. `market_data_intraday_other` (5.7 M rows, 67 GB) is larger than the three ETF partitions combined; it holds every non-ETF ticker ever backfilled and has more index than data ([`docs/audits/COST_AUDIT_2026-09-06.md`](../../../audits/COST_AUDIT_2026-09-06.md) §7).

## 9. Removed since last refresh

- 2026-09-07: the 2026-09-02 layout's "1. Table inventory" became "1. Table inventory (declared in `gcp/schema.sql`)" plus "1b. Live relations"; its "`market_data_intraday` (and partitions)" write-graph subsection became the per-table `market_data_intraday` subsection (partitions are routed by Postgres and are listed in §1 and §5 only). Every table that had a §2/§3 entry still has one.

Generated 2026-09-07 by hand from the audit in [`docs/audits/ARCHITECTURE_DOCS_AUDIT_2026-09-07.md`](../../../audits/ARCHITECTURE_DOCS_AUDIT_2026-09-07.md); inventory blocks rendered by `scripts/maintenance/doc_inventory.py`. This hand-maintained copy is not refreshed; update this line yourself when you edit it.
