# Data Dependencies

This document tracks the flow of data through the Cloud SQL database, detailing which tables exist, what they're for, who writes to them, and who reads from them. It's an operator's guide to data provenance and dependency analysis.

*Generated 2026-08-01 by .github/workflows/refresh-architecture-docs.yml*

## 1. Table Inventory

| Table | Purpose |
| --- | --- |
| `market_data_daily` | Daily OHLCV bars and technical indicators for all tickers. |
| `market_data_intraday` | Intraday OHLCV bars (1-min, 5-min, etc.) for all tickers, partitioned by ticker. |
| `etf_options_snapshots` | Per-contract options chain data including prices, volume, and Greeks, captured at various points. |
| `options_daily_features` | Materialized daily options-flow features (PCR, IV skew) for performance. |
| `etf_options_daily_greeks` | Materialized daily directional-greek aggregates (DEX, Vanna, Charm). |
| `intraday_flow_15m` | Materialized per-15m-bucket intraday order-flow imbalance (OFI). |
| `intraday_gex_15m` | Materialized per-15m-bucket reconstructed intraday dealer GEX/DEX. |
| `realtime_gex_15m` | Materialized per-15m-bucket REAL intraday dealer GEX/DEX from live greeks. |
| `earnings_options_snapshots` | Per-contract options chain data specifically for earnings events. |
| `daily_rates` | Daily risk-free interest rates (from FRED) for Black-Scholes calculations. |
| `archive_yahoo_market_data_daily` | Archive of legacy daily market data from Yahoo Finance. |
| `archive_yahoo_market_data_intraday` | Archive of legacy intraday market data from Yahoo Finance. |
| `archive_yahoo_etf_options_snapshots` | Archive of legacy options data from Yahoo Finance. |
| `archive_yahoo_earnings_options_snapshots` | Archive of legacy earnings options data from Yahoo Finance. |
| `earnings_calendar` | Forward-looking earnings calendar with dates, times, and strategy picks. |
| `earnings_history` | Backward-looking quarterly EPS history per ticker. |
| `earnings_reactions` | Per-quarter post-earnings reaction profile (gap, sustain, etc.). |
| `sec_filings` | SEC EDGAR filings (8-K, 10-Q, etc.) for catalyst detection. |
| `insider_transactions` | Form 4 insider transaction filings (buys/sells). |
| `top_movers_daily` | Daily snapshot of top market gainers, losers, and most active stocks. |
| `top_movers_intraday` | Intraday snapshot of most actively traded stocks. |
| `ranker_runs` | Audit trail for the `rank_tickers` agent, capturing inputs and outputs. |
| `signal_alerts` | Fired real-time trading signals from the `signal_monitor`. |
| `trades` | Log of executed trades from the automated pipeline. |
| `journal_entries` | User-authored manual trade log, separate from automated trades. |
| `premarket_analysis` | Daily pre-market analysis and playbook recommendations. |
| `playbook_cards` | Structured playbook decision cards with historical performance stats. |
| `economic_events` | Calendar of major economic events (CPI, FOMC, etc.). |
| `model_routing` | Per-role provider/model routing for the AI agent pipeline. |
| `insight_reports` | Cached output from the AI insight generation pipeline. |
| `insight_runs` | Durable run-state for the asynchronous AI insight pipeline. |
| `news_sentiment` | News articles and associated sentiment scores per ticker. |
| `strat_levels` | Horizontal price levels (support/resistance) per ticker, used by brief and monitor. |
| `premarket_analysis_history` | Append-only audit trail for every run of the pre-market brief. |
| `insight_reports_history` | Append-only audit trail for every run of the AI insight pipeline. |
| `historical_signals` | Idempotent store for historical signal analysis from `trading_analysis.py`. |
| `ticker_info` | Company overview information (name, sector, etc.) for each ticker. |
| `watchlists` | Per-user ticker subscriptions, driving briefs, insights, and signals. |
| `ticker_calibration` | Per-ticker, quarterly-refreshed thresholds for signal evaluation. |
| `exit_config_overrides` | Per-ticker overrides for trade exit parameters (target, stop, time). |
| `signal_metrics` | Persisted output of the signal quality analysis pipeline. |
| `backtest_trades` | Per-trade results from the backtesting pipeline. |
| `backtest_sweeps` | Per-timeframe/combo results from backtest parameter sweeps. |
| `backtest_reports` | Rendered markdown reports and aggregate metrics from backtest runs. |
| `backtest_walk_forward_folds` | Per-fold metrics from walk-forward validation runs. |
| `walk_forward_results` | Per-parameter-combo walk-forward sweep output. |
| `earnings_calibration` | Tuned input parameters for the earnings playability score. |
| `indicator_correlation` | Correlation between intraday indicators and forward returns. |
| `regime_combo_results` | Predictive indicator combinations for forward market regimes. |
| `strat_combo_results` | Predictive indicator combinations for next-candle Strat classifications. |
| `earnings_options_strategy_insights`| Historical options P&L breakdown by quintile, ratio, and structure. |
| `earnings_options_strategy_winners` | Top-10 historical earnings trade winners per structure/quintile. |
| `earnings_upcoming_with_history` | Pre-joined upcoming earnings with historical lean for frontend use. |
| `waitlist_signups` | Landing page waitlist signups for the Solyra platform. |
| `user_style_results` | Per-user mined trading style profiles. |
| `playbook_cards_staging` | Staging area for user-specific playbook card candidates. |

## 2. Write Graph

This section details every code module that writes to a given table.

### `market_data_daily`
- `gcp/fetchers/backfill_daily_indicators.py`: (line 284) via `upsert_dataframe` (historical backfill)
- `gcp/fetchers/fetch_market_data.py`: (lines 436, 512, 561, 890) via `upsert_dataframe` (daily fetch)
- `gcp/migrate_to_gcp.py`: (lines 186, 667) via `upsert_dataframe` (one-shot historical)
- `scripts/backfill_watchlist_data.py`: (line 233) via `upsert_dataframe` (backfill script)
- `scripts/deep_backfill_ticker.py`: (line 102) via `upsert_dataframe` (backfill script)
- `gcp/fetchers/fetch_premarket_refresh.py`: (line 251) `INSERT INTO` (pre-market refresh)
- `gcp/premarket_brief.py`: (line 256) `DELETE FROM` (cleans null-close rows)

### `market_data_intraday`
- `gcp/fetchers/fetch_alphavantage_intraday.py`: (line 306) via `upsert_dataframe` with dynamic table name `f"market_data_intraday_{self.index_name.lower()}"` writing to partitions.
- `gcp/fetchers/fetch_market_data.py`: (line 464) via `upsert_dataframe`
- `gcp/migrate_to_gcp.py`: (line 244) `DELETE FROM` (one-shot historical data clearing)

### `etf_options_snapshots`
- `gcp/fetchers/fetch_av_historical_options.py`: (line 162) via `upsert_dataframe` (historical backfill)
- `gcp/fetchers/fetch_av_realtime_options.py`: (line 212) via `upsert_dataframe` (real-time fetch)
- `scripts/validate_track2_live.py`: (line 80) `INSERT INTO` and (line 112) `DELETE FROM` (validation script)
- `gcp/options_retention_job.py`: (line 79) `DELETE FROM` (data retention job)
- `scripts/maintenance/compute_spx_greeks.py`: (line 149) `UPDATE` (maintenance script)

### `options_daily_features`
- No direct writers found. This is a materialized view, populated from `etf_options_snapshots`.

### `etf_options_daily_greeks`
- `gcp/build_options_daily_greeks.py`: (line 62) `INSERT INTO` (build job)

### `earnings_options_snapshots`
- `gcp/fetchers/fetch_av_earnings_options_backfill.py`: (line 348) via `upsert_dataframe` (historical backfill)

### `daily_rates`
- `gcp/fetchers/fetch_fred_rates.py`: (line 120) via `upsert_dataframe` (daily fetch)

### `earnings_calendar`
- `scripts/fetch_earnings_calendar.py`: (line 1196) via `upsert_dataframe` (fetch script)
- `gcp/fetchers/evaluate_ew_strikes.py`: (line 170) `UPDATE` (post-earnings evaluation)

### `earnings_history`
- `gcp/fetchers/fetch_earnings_history.py`: (line 535) via `upsert_dataframe` (fetch script)

### `earnings_reactions`
- `gcp/fetchers/compute_earnings_reactions.py`: (line 770) via `upsert_dataframe` (computation job)

### `economic_events`
- `gcp/fetchers/fetch_economic_events.py`: (line 400) via `upsert_dataframe` (fetch script)

### `historical_signals`
- `gcp/historical_signals.py`: (line 221) `INSERT INTO` and (lines 114, 117) `DELETE FROM` (historical signal generation)
- `scripts/backfill_timeframe_tags.py`: (line 172) `UPDATE` (backfill script)

### `insider_transactions`
- `gcp/fetchers/fetch_insider_transactions.py`: (line 226) via `upsert_dataframe` (fetch script)

### `insight_reports`
- `gcp/insight_pipeline_job.py`: (lines 302, 333) `INSERT INTO` (AI insight pipeline)
- `scripts/generate_historical_report.py`: (line 67) `INSERT INTO` (report generation script)

### `insight_reports_history`
- `gcp/insight_pipeline_job.py`: (line 261) `INSERT INTO` (AI insight pipeline)
- `scripts/backfill_history_tables.py`: (line 169) `INSERT INTO` (backfill script)

### `insight_runs`
- `gcp/auto_refresh_top_n.py`: (line 98) `INSERT INTO` (auto-refresh job)
- `gcp/discord_interactions/main.py`: (line 372) `INSERT INTO` (Discord bot interaction)
- `gcp/insight_pipeline_job.py`: (line 177) `INSERT INTO` and (lines 200, 206, 215) `UPDATE` (AI insight pipeline)

### `journal_entries`
- `scripts/backfill_journal_embeddings.py`: (line 79) `UPDATE` (backfill script)

### `news_sentiment`
- `gcp/backfill_ticker.py`: (line 538) via `upsert_dataframe` (backfill)
- `gcp/fetchers/fetch_news_sentiment.py`: (line 375) via `upsert_dataframe` (fetch script)
- `gcp/fetchers/fetch_rss_news.py`: (line 710) via `upsert_dataframe` (fetch script)
- `scripts/backfill_news_sentiment.py`: (line 101) via `upsert_dataframe` (backfill script)

### `playbook_cards`
- `scripts/analysis/phase6_playbook.py`: (line 988) via `upsert_dataframe` (analysis script)

### `playbook_cards_staging`
- `gcp/research/p2_outcomes_grid.py`: (line 421) via `upsert_dataframe` (research script)

### `premarket_analysis`
- `gcp/premarket_brief.py`: (lines 3289, 3305) via `upsert_dataframe` (pre-market brief generation)
- `gcp/premarket_playbook_resolver.py`: (line 463) `UPDATE` (EOD playbook resolver)

### `premarket_analysis_history`
- `gcp/premarket_brief.py`: (line 3264) via `bulk_insert_dataframe` (pre-market brief generation)
- `scripts/backfill_history_tables.py`: (line 123) `INSERT INTO` (backfill script)

### `sec_filings`
- `gcp/fetchers/fetch_sec_filings.py`: (line 303) via `upsert_dataframe` (fetch script)

### `signal_alerts`
- `gcp/signal_monitor.py`: (line 1078) via `upsert_dataframe` and (line 1317) `UPDATE` (live signal monitor)
- `gcp/signal_monitor_eod_resolver.py`: (line 338) `UPDATE` (EOD resolver job)
- `scripts/backfill_signals.py`: (line 227) via `upsert_dataframe` (backfill script)
- `scripts/replay_signal_monitor.py`: (line 257) `INSERT INTO` (replay script)

### `signal_metrics`
- `scripts/signal_quality_report.py`: (line 461) `INSERT INTO` (quality report script)

### `strat_levels`
- `gcp/research/p2_build_gamma_levels.py`: (line 250) via `upsert_dataframe` (research script)

### `ticker_calibration`
- `scripts/calibrate_thresholds.py`: (line 487) via `upsert_dataframe` (calibration script)

### `top_movers_daily`
- `gcp/fetchers/fetch_top_movers.py`: (line 290) via `upsert_dataframe` (fetch script)

### `top_movers_intraday`
- `gcp/fetchers/fetch_top_movers.py`: (line 260) via `upsert_dataframe` (fetch script)

### `trades`
- `gcp/migrate_to_gcp.py`: (line 713) via `upsert_dataframe` (one-shot historical)
- `gcp/signal_monitor.py`: (line 1331) `UPDATE` (live signal monitor)
- `gcp/signal_monitor_eod_resolver.py`: (line 351) `UPDATE` (EOD resolver job)
- `gcp/trade_logger.py`: (line 68) via `upsert_dataframe` (trade logger)
- `scripts/backfill_signals.py`: (line 231) via `upsert_dataframe` (backfill script)

### `watchlists`
- `gcp/backfill_ticker.py`: (line 242) `INSERT INTO` (backfill script)
- `gcp/discord_interactions/main.py`: (line 650) `INSERT INTO` and (line 686) `UPDATE` (Discord bot)
- `gcp/fetchers/_watchlist.py`: (line 258) `INSERT INTO` and (line 295) `UPDATE` (watchlist utility)

### `archive_*` tables
- `scripts/archive_yahoo_data.py`: `INSERT INTO` (line 127) and `DELETE FROM` (line 154) with dynamic table names. (one-shot historical)

### `backtest_reports`
- `scripts/backtest_playability.py`: (line 996) via `upsert_dataframe`
- `scripts/run_backtest.py`: (line 76) via `upsert_dataframe`
- `scripts/run_timeframe_sweep.py`: (line 63) via `upsert_dataframe`
- `scripts/generate_backtest_report.py`: (line 387) `INSERT INTO`

### `backtest_sweeps`
- `scripts/run_param_sweep.py`: (line 107) via `upsert_dataframe`

### `backtest_trades`
- `scripts/backtest_playability.py`: (line 1004) via `upsert_dataframe`

### `earnings_calibration`
- `scripts/calibrate_earnings.py`: (line 156) `INSERT INTO`

### `earnings_upcoming_with_history`
- `gcp/refresh_earnings_views.py`: (line 305) via `upsert_dataframe` and `DELETE FROM` (lines 168, 301)

### `exit_config_overrides`
- `scripts/run_param_sweep.py`: (line 134) `INSERT INTO`

### `indicator_correlation`
- `gcp/indicator_correlation_job.py`: (line 725) via `upsert_dataframe`

### `regime_combo_results`
- `gcp/regime_combo_job.py`: (line 189) via `upsert_dataframe`

### `walk_forward_results`
- `scripts/run_walk_forward.py`: (line 142) via `upsert_dataframe`

## 3. Read Graph

This section details every code module that reads from a given table. Test files under `tests/` are excluded.

### `market_data_daily`
- `gcp/premarket_brief.py`: (lines 365, 370, 770) `SELECT` and `JOIN`
- `gcp/historical_signals.py`: (multiple locations) `SELECT` for indicator calculations
- `gcp/research/p2_outcomes_grid.py`: (lines 144, 149) `SELECT`
- `gcp/fetchers/compute_earnings_reactions.py`: `SELECT` to get price data around earnings
- Many other research and analysis scripts.

### `etf_options_snapshots`
- `gcp/premarket_brief.py`: (lines 176, 202) `SELECT`
- `gcp/build_intraday_gex.py`: Reads EOD snapshots to reconstruct intraday GEX.
- `gcp/build_realtime_gex.py`: Reads `REALTIME` snapshots to build real GEX.

### `earnings_calendar`
- `gcp/premarket_brief.py`: (lines 361, 768) `SELECT` and `JOIN`
- `gcp/refresh_earnings_views.py`: `SELECT` to build `earnings_upcoming_with_history`.

### `earnings_history`
- `gcp/fetchers/compute_earnings_reactions.py`: `JOIN` to get EPS data.
- `gcp/refresh_earnings_views.py`: `JOIN` within materialized view creation.

### `earnings_reactions`
- `gcp/premarket_brief.py`: `SELECT` within `_load_earnings_data` to get playability scores.
- `gcp/refresh_earnings_views.py`: `JOIN` within materialized view creation.

### `economic_events`
- `gcp/premarket_brief.py`: (line 859) `SELECT`

### `premarket_analysis`
- `gcp/premarket_brief.py`: (line 3342) `SELECT` and (line 3314) `row_exists` for replay functionality.
- `gcp/premarket_playbook_resolver.py`: `SELECT` to get playbook details for EOD resolution.

### `watchlists`
- `gcp/fetchers/_watchlist.py`: `SELECT` queries in `get_watchlist` and `load_watchlist`.
- `gcp/premarket_brief.py`: (line 961) `load_watchlist` call.

### `historical_signals`
- `gcp/indicator_correlation_job.py`: `SELECT` as a source for indicator correlation.
- `scripts/signal_quality_report.py`: `SELECT` to generate quality metrics.

### `ticker_calibration`
- `lib/strategies/calibration.py`: `load_calibration_for_ticker` reads the latest calibration.
- `gcp/signal_monitor.py`: Uses calibration data for signal evaluation.

### `exit_config_overrides`
- `lib/strategies/exit_config_overrides.py`: `get_exit_config` reads the latest overrides.
- `gcp/signal_monitor.py`: Uses overrides for trade exit logic.

## 4. Multi-Writer Tables

| Table | Writers | Why a coordination risk |
| --- | --- | --- |
| `market_data_daily` | `fetch_market_data.py`, `backfill_daily_indicators.py`, `migrate_to_gcp.py`, `deep_backfill_ticker.py` | Multiple backfill/migration scripts writing to the same live table. All use `upsert_dataframe`, which is safe, but concurrent runs could lead to unpredictable states if not coordinated. |
| `signal_alerts` | `signal_monitor.py`, `signal_monitor_eod_resolver.py`, `backfill_signals.py` | The live monitor (`signal_monitor.py`) writes and updates alerts. The EOD resolver (`signal_monitor_eod_resolver.py`) updates open alerts. A backfill script also writes. The EOD resolver is the main risk, as it runs on a schedule and could race with a manual `UPDATE` or a late-day live signal. |
| `trades` | `trade_logger.py`, `signal_monitor.py`, `signal_monitor_eod_resolver.py`, `migrate_to_gcp.py` | Similar to `signal_alerts`, the live monitor and EOD resolver both update trade records. The logger and migration scripts are additional writers. Coordination is managed by state (`is_open` flags), but complexity is high. |
| `watchlists` | `discord_interactions/main.py`, `_watchlist.py`, `backfill_ticker.py` | The Discord bot and a utility library both handle `INSERT` and `UPDATE`. A backfill script also `INSERT`s. All seem to operate on different user scopes or are one-off, but it adds complexity. |
| `etf_options_snapshots`| `fetch_av_historical_options.py`, `fetch_av_realtime_options.py`, `options_retention_job.py`, `compute_spx_greeks.py`, `validate_track2_live.py` | Multiple fetchers for historical and real-time data, a retention job (`DELETE`), a maintenance script (`UPDATE`), and a validation script (`INSERT`/`DELETE`). High risk of race conditions or data integrity issues if not carefully managed. The `market_session` and `data_source` columns are critical for partitioning writes. |

## 5. Orphan Tables

| Table | Writers | Readers | Status |
| --- | --- | --- | --- |
| `archive_yahoo_*` | `scripts/archive_yahoo_data.py` (one-shot) | None found in live code | **Intentional (archive)**. These tables hold legacy data and are not part of the live pipeline. |
| `waitlist_signups` | None found | None found | **Decision needed**. Appears to be for a future feature (Solyra landing page). Not currently used. |
| `user_style_results` | None found | None found | **Decision needed**. Appears to be for a future feature (style mining). Not currently used. |
| `ranker_runs` | None found | None found | **Decision needed**. An audit table for a ranker agent that doesn't appear to have any writers in the current codebase. Potentially legacy or feature-flagged. |
| `strat_combo_results`| None found | None found | **Decision needed**. Part of "Effort B - strat_combo_miner" which may not be implemented or enabled. |

## 6. Blast Radius per Cloud Run Job

| Cloud Run Job | Writes To | Downstream Consumers | Severity |
| --- | --- | --- | --- |
| `premarket-brief` | `premarket_analysis`, `premarket_analysis_history` | `premarket_playbook_resolver` | **Highest** |
| `fetch-market-data` | `market_data_daily`, `market_data_intraday` | `premarket-brief`, `historical_signals`, All analysis | **Highest** |
| `fetch-options-eod` | `etf_options_snapshots` | `build-intraday-gex`, `build-options-daily-greeks`, `premarket-brief` | **Highest** |
| `fetch-options-rt` | `etf_options_snapshots` | `build-realtime-gex`, `premarket-brief` | **Very High** |
| `signal-monitor` | `signal_alerts`, `trades` | `signal_monitor_eod_resolver`, Downstream alerting & UIs | **High** |
| `insight-pipeline` | `insight_reports`, `insight_runs`, `insight_reports_history` | `insight_discord_push` | **High** |
| `premarket-playbook-resolver` | `premarket_analysis` | Analytics Dashboards | **Medium** |
| `signal-monitor-eod-resolver` | `signal_alerts`, `trades` | Analytics Dashboards | **Medium** |
| `refresh-earnings-views` | `earnings_upcoming_with_history`| Earnings Dashboard App | **Medium** |
| `build-intraday-flow`| `intraday_flow_15m` | Research & Backtesting | **Low** |
| `build-intraday-gex` | `intraday_gex_15m` | Research & Backtesting | **Low** |
| `build-realtime-gex`| `realtime_gex_15m` | Research & Backtesting | **Low** |
| `build-options-daily-greeks` | `etf_options_daily_greeks`| Research & Backtesting | **Low** |
| `options-retention`| `etf_options_snapshots` | (Internal maintenance) | **Very Narrow** |

## 7. Mermaid Graph

```mermaid
flowchart LR
    classDef orphan stroke-dasharray: 5 5;

    subgraph "Market Data"
        market_data_daily
        market_data_intraday
    end

    subgraph "Options Data"
        etf_options_snapshots
        options_daily_features
        etf_options_daily_greeks
        intraday_gex_15m
    end

    subgraph "Earnings"
        earnings_calendar
        earnings_history
        earnings_reactions
        earnings_upcoming_with_history
    end

    subgraph "Catalysts"
        economic_events
        sec_filings
        news_sentiment
    end

    subgraph "Signals & Trades"
        signal_alerts
        trades
        historical_signals
        premarket_analysis
    end

    subgraph "AI Insights"
        insight_reports
        insight_runs
    end

    subgraph "Ops & Config"
        watchlists
        ticker_calibration
        exit_config_overrides
    end

    subgraph "Unused / Orphan"
        waitlist_signups:::orphan
        user_style_results:::orphan
        ranker_runs:::orphan
    end

    %% Writers
    job_fetch_market_data["fetch-market-data (Job)"] ==> market_data_daily
    job_fetch_market_data ==> market_data_intraday
    job_fetch_options_eod["fetch-options-eod (Job)"] ==> etf_options_snapshots
    job_fetch_options_rt["fetch-options-rt (Job)"] ==> etf_options_snapshots
    job_premarket_brief["premarket-brief (Job)"] ==> premarket_analysis
    job_signal_monitor["signal-monitor (Job)"] ==> signal_alerts
    job_signal_monitor ==> trades
    job_insight_pipeline["insight-pipeline (Job)"] ==> insight_reports
    job_insight_pipeline ==> insight_runs
    job_eod_resolver["signal-monitor-eod-resolver (Job)"] -.-> signal_alerts
    job_eod_resolver -.-> trades
    job_fetch_earnings["fetch-earnings-calendar (Script)"] ==> earnings_calendar
    job_compute_reactions["compute-earnings-reactions (Job)"] ==> earnings_reactions
    job_refresh_earnings["refresh-earnings-views (Job)"] ==> earnings_upcoming_with_history

    %% Readers
    market_data_daily --> job_premarket_brief
    etf_options_snapshots --> job_premarket_brief
    earnings_calendar --> job_premarket_brief
    earnings_reactions --> job_premarket_brief
    premarket_analysis --> job_eod_resolver

    market_data_intraday --> job_signal_monitor
    strat_levels --> job_signal_monitor
    ticker_calibration --> job_signal_monitor
    exit_config_overrides --> job_signal_monitor
    insight_reports --> job_signal_monitor

    market_data_daily --> job_insight_pipeline
    news_sentiment --> job_insight_pipeline
end
```
