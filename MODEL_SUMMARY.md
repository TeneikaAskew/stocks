# Investment Models Summary

## Overview

This repository contains a **multi-model stock market analysis and trading system** targeting 4 major indices/ETFs — **IWM, SPY, QQQ, SPX** — built around a **contrarian mean-reversion strategy**. The system spans 5 primary models, automated data pipelines, technical indicator generation, signal detection, options analytics, and trade performance tracking.

---

## Model 1: IWM Deep Analysis Engine

**File:** `iwm_analysis.py`

### What It Does
The flagship model — an 11-step processing pipeline that generates **195 technical indicator columns** on top of base OHLCV price data for IWM (Russell 2000 ETF).

### Methodology
| Step | Indicator | Detail |
|------|-----------|--------|
| 1 | ATR | Average True Range with Wilder's smoothing |
| 2 | RSI | 14-period Relative Strength Index |
| 3 | EMAs | 9, 20, 50-period exponential moving averages |
| 4 | VWAP | Volume Weighted Average Price |
| 5 | RVOL | Relative Volume (20-period + minute-of-day) |
| 6 | OBV | On-Balance Volume (continuous accumulation) |
| 7 | Stochastic RSI | Momentum oscillator |
| 8 | Historical Levels | 80 columns — prior day/week/month/year OHLC, price position %, breakout flags |
| 9 | ORB & Order Blocks | 115 columns — Opening Range Breakout (5/15/30 min) + institutional zone detection |
| 10 | Validation | Data integrity checks |
| 11 | Output | Final dataset creation |

### Impact & Insights
- **Historical Levels (80 columns)** provide multi-timeframe support/resistance context — the model tracks where price sits relative to prior day, week, month, and year levels, generating breakout/breakdown flags and "at-level" proximity indicators.
- **Opening Range Breakout (108 columns)** across three timeframes gives intraday trend confirmation or contradiction for every signal.
- **Order Block detection (7 columns)** identifies institutional consolidation zones, boundaries, price position within blocks, and test flags — surfacing where large players likely have interest.
- Combined, these 195 features turn raw 1-minute candle data into a rich, context-aware dataset for signal generation.

### Outputs
- `data/historical_iwm_*_with_indicators.csv` — full dataset with all 195 indicators
- `data/historical_iwm_*_signals.csv` — trading signals enriched with 117 columns each

---

## Model 2: Multi-Ticker Market Data Pipeline

**File:** `scripts/fetch_market_data.py`

### What It Does
Automated daily data collection and indicator calculation for **all 4 tickers** (IWM, SPY, QQQ, SPX), fetching 1-minute bars from Yahoo Finance and aggregating into daily data with a uniform technical indicator set.

### Indicators Calculated
- **Moving Averages:** SMA (5, 10, 20, 50), EMA (9, 21, 50)
- **Momentum:** RSI (14-period, 9-period), Stochastic RSI (%K, %D)
- **Volume:** RVOL (minute-of-day adjusted), OBV, Volume MA (10, 20)
- **Volatility:** ATR (14, 20), Std Dev (5-day, 20-day), High-Low spread
- **Returns:** Daily, intraday, YTD

### Impact & Insights
- **Unified cross-ticker comparison** — identical indicators computed for all 4 indices enables apples-to-apples relative analysis.
- **Incremental updates** — fetches only new data and appends to yearly parquet files, keeping the dataset current without full re-downloads.
- **Summary JSONs** (`{ticker}_summary.json`) provide a real-time dashboard snapshot: latest RSI, RVOL, Stochastic RSI, OBV, ATR, and YTD return per ticker.
- **Scale:** IWM alone contains 1.8M+ bars of 1-minute data spanning Jan 2015 – Nov 2025.

### Outputs
- `data/{ticker}_2025.parquet` — daily data with indicators per ticker
- `data/{ticker}_summary.json` — latest metric snapshots
- `data/minute/` — minute-level parquet archives

---

## Model 3: Enhanced Multi-Ticker Signal Generator

**File:** `scripts/analyze_market_data_enhanced.py`

### What It Does
Extends Model 2 by applying the full IWM-style analysis to all 4 tickers and adding a **signal scoring system** that identifies CALL and PUT trading opportunities.

### Signal Generation Logic
A signal fires when **3 or more of 5 conditions** align:

| # | Condition | CALL (Bullish) | PUT (Bearish) |
|---|-----------|----------------|---------------|
| 1 | Consecutive moves | 3+ down periods | 3+ up periods |
| 2 | RSI level | 25–50 (oversold) | 50–75 (overbought) |
| 3 | Price vs VWAP | Below VWAP | Above VWAP |
| 4 | Price vs EMAs | Near/below EMA 9/20 | Near/above EMA 9/20 |
| 5 | Stochastic RSI | Oversold zone | Overbought zone |

### Signal Strength → Position Sizing
| Conditions Met | Strength | Position Size |
|----------------|----------|---------------|
| 3 / 5 | Weak | 25% |
| 4 / 5 | Medium | 50% |
| 5 / 5 | Strong | 75–100% |

### Impact & Insights
- **Win rate tracking per signal** — every signal is scored and tracked for historical accuracy, allowing ongoing calibration.
- **Cross-ticker comparison** — signal frequency and win rates compared across IWM, SPY, QQQ, and SPX to find which indices respond best to mean reversion.
- **Position sizing discipline** — signal strength directly controls capital allocation, preventing oversized bets on marginal setups.

---

## Model 4: Trade Analysis Pipeline

**File:** `trade_analysis_pipeline.py`

### What It Does
Analyzes **actual completed trades** from a trade tracker, enriching them with indicator context and finding similar historical setups to identify what distinguishes winners from losers.

### Pipeline Steps
1. Read trades from `data/signals/trade_examples/trade_tracker.csv`
2. Calculate hold durations for each trade
3. Pivot to tall format (3 rows per trade: exit, stop loss, runner)
4. Join with indicator values at entry and exit times
5. Search historical data for pattern-matching setups

### Impact & Insights
- **Winner vs. loser profiling** — identifies which indicator conditions were present during profitable trades vs. losing trades, revealing the most predictive features.
- **Duration analysis** — compares how long winning trades were held vs. losers, informing time-stop calibration.
- **Similar trade lookup** — for any new setup, the pipeline finds historical precedents and their outcomes, giving a probabilistic edge.
- **Feedback loop** — connects live trading results back to the model, enabling continuous improvement.

### Outputs
- `data/trade_tracker_updated.csv` — trades with calculated durations
- `data/trades_enriched.csv` — trades enriched with indicator values
- `data/trade_patterns.csv` — identified profitable patterns
- `data/similar_trades_pipeline.csv` — similar historical trades

---

## Model 5: Earnings Options Analytics

**File:** `earnings_options_analytics/`

### What It Does
Analyzes options market activity around **earnings announcements** to identify opportunities in elevated implied volatility and unusual options flow.

### Methodology
- Ingests earnings data from Google Sheets (`google-apps-script/data/*.csv`)
- Runs quick and full analysis modes
- Generates charts (matplotlib/seaborn) and CSV reports
- Automated daily via GitHub Actions with artifact uploads

### Impact & Insights
- **Earnings edge detection** — surfaces patterns in how options are priced before and after earnings, identifying recurring mispricings.
- **Automated scheduling** — runs daily at 2 AM UTC, ensuring no earnings event is missed.
- **Visual reporting** — chart outputs make patterns immediately actionable.

---

## Supporting Infrastructure

### Options Data Collection
- **ETF Options Fetcher** (`scripts/fetch_etf_options_intraday.py`) — captures 15,000+ contracts per run for IWM, SPY, QQQ
- **AlphaVantage Options** (`scripts/fetch_alphavantage_options.py`) — weekly historical options chain snapshots
- **P/L Matching** — real-time matching of trade entries against actual option contracts using bid/ask prices

### Data Sources
| Source | Data | Format |
|--------|------|--------|
| Yahoo Finance | 1-minute bars, daily OHLCV | Parquet |
| AlphaVantage | 5 years of 1-minute intraday | Parquet |
| FRED | Federal Reserve economic data | JSON/CSV |
| Economic Calendar | Market-moving events, Fed decisions | CSV |
| Google Sheets | Earnings data, trade tracking | CSV |

### Automation (GitHub Actions)
| Workflow | Schedule |
|----------|----------|
| Fetch Market Data | 5 PM EST weekdays |
| Economic Calendar | Sundays 6 AM EST |
| Earnings Options Analytics | Daily 2 AM UTC |
| AlphaVantage Fetch | 1st of each month |
| Data Validation | Post-fetch |

### Web Applications
1. **Trading Chart Viewer** — TradingView-based charting with click-to-mark trade entries, multi-timeframe support (1m/5m/15m/30m/1h), reference lines, and live options P/L calculation
2. **Options Heatseeker** — Options flow visualization and activity analysis

---

## Core Strategy: Contrarian Mean Reversion

All models feed into a single unified trading strategy:

- **CALL entries:** Price beaten down (below VWAP, oversold RSI, 3+ consecutive down periods) → buy the dip during the 09:30–10:00 AM window
- **PUT entries:** Price extended (above VWAP, overbought RSI, 3+ consecutive up periods) → fade the rally during the 09:30–2:00 PM window
- **Confirmation:** At least 3 of 5 conditions must align before entry

### Risk Management
| Parameter | Value |
|-----------|-------|
| Max daily trades | 5 |
| Max concurrent positions | 1 |
| Daily loss limit | -2.0% |
| Daily profit target | +3.0% |
| CALL profit target | +0.30% |
| PUT profit target | +0.38% |
| CALL time stop | 30 minutes |
| PUT time stop | 35 minutes |
| Extreme RSI exits | >80 (CALL), <20 (PUT) |

### Platform Integrations
- TradingView webhooks
- ThinkOrSwim study alerts
- Discord webhook notifications

---

## Key Takeaways

1. **195-feature IWM model** is the analytical core — multi-timeframe levels, ORB, and order blocks give institutional-grade context to every signal.
2. **Signal scoring (3/5 to 5/5)** with direct position sizing tie creates built-in risk discipline — weak signals get small size, strong signals get full allocation.
3. **Trade feedback loop** (Model 4) connects actual P/L back to indicator conditions, enabling data-driven refinement of entry/exit rules.
4. **Cross-ticker analysis** reveals which indices are most responsive to mean reversion, allowing capital to flow toward the highest-probability setups.
5. **Full automation** — from data fetching through signal generation to alerting — ensures no opportunity is missed and removes manual bottlenecks.
6. **Earnings options analytics** add an orthogonal edge by exploiting implied volatility patterns around catalytic events.
7. **Strict risk parameters** (1 position, 5 trades/day, -2% stop) protect capital even when signals misfire.
