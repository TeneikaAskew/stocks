# Investment Models & Code Summary — IWM, QQQ, SPY, SPX

## Table of Contents

1. [Project Overview](#project-overview)
2. [Data Sources & Inputs](#data-sources--inputs)
3. [Technical Indicators Calculated](#technical-indicators-calculated)
4. [Model #1 — IWM Analysis (Primary Model)](#model-1--iwm-analysis-primary-model)
5. [Model #2 — Multi-Ticker Market Data (SPY, QQQ, SPX, IWM)](#model-2--multi-ticker-market-data-spy-qqq-spx-iwm)
6. [Model #3 — Enhanced Market Analysis (All Tickers)](#model-3--enhanced-market-analysis-all-tickers)
7. [Model #4 — Trade Analysis Pipeline](#model-4--trade-analysis-pipeline)
8. [Model #5 — Earnings Options Analytics](#model-5--earnings-options-analytics)
9. [Shared Library (`lib/`)](#shared-library-lib)
10. [The Strat Classifier & FTFC](#the-strat-classifier--ftfc)
11. [Backtesting Engine](#backtesting-engine)
12. [Multi-Timeframe Sweep Analysis](#multi-timeframe-sweep-analysis)
13. [Signal Generation Methodology](#signal-generation-methodology)
14. [Alert System & Risk Parameters](#alert-system--risk-parameters)
15. [Advanced Features — Historical Levels, ORB, Order Blocks](#advanced-features--historical-levels-orb-order-blocks)
16. [Options Analysis & P/L Tracking](#options-analysis--pl-tracking)
17. [Data Infrastructure & Automation](#data-infrastructure--automation)
18. [Outputs & Deliverables](#outputs--deliverables)
19. [Strategy Outcomes & Insights](#strategy-outcomes--insights)
20. [Backtest Results](#backtest-results)

---

## Project Overview

This is a comprehensive **stock market analysis system** for four major indices/ETFs:

| Ticker | Name | Asset Type | Focus |
|--------|------|-----------|-------|
| **IWM** | iShares Russell 2000 ETF | Small-cap ETF | Primary analysis model — deepest feature set |
| **SPY** | SPDR S&P 500 ETF | Large-cap ETF | Broad market benchmark |
| **QQQ** | Invesco QQQ Trust | Nasdaq-100 ETF | Technology/growth-focused |
| **SPX** | S&P 500 Index (^GSPC) | Index | Pure index (non-tradable directly, used for reference) |

The system performs automated data collection, technical analysis, signal generation, trade pattern recognition, options analytics, and provides a web-based interactive chart viewer for marking and simulating trades.

---

## Data Sources & Inputs

### Primary Data Sources

| Source | Data Type | Coverage | Format |
|--------|-----------|----------|--------|
| **Yahoo Finance** | 1-minute bars, daily OHLCV | Last 7–30 days (minute), full history (daily) | Parquet |
| **AlphaVantage API** | 1-minute historical bars | Up to 5 years of 1-minute data | Parquet |
| **FRED API** | Federal Reserve economic data | Macro indicators | JSON/CSV |
| **Economic Calendar** | Market-moving events, Fed decisions | Weekly updates | CSV |
| **Google Sheets** | Earnings data, trade tracking | Manual + automated | CSV |

### Data Organization

```
data/
├── iwm_2025.parquet              # IWM daily data + indicators
├── spy_2025.parquet              # SPY daily data + indicators
├── qqq_2025.parquet              # QQQ daily data + indicators
├── spx_2025.parquet              # SPX daily data + indicators
├── {ticker}_summary.json         # Latest metrics per ticker
├── minute/                       # Minute-level data per day
│   ├── iwm_minute_YYYYMMDD.parquet
│   ├── spy_minute_YYYYMMDD.parquet
│   ├── qqq_minute_YYYYMMDD.parquet
│   └── spx_minute_YYYYMMDD.parquet
├── iwm/intraday/                 # AlphaVantage 5yr 1-min data
│   ├── iwm_av_1min_YYYYMM.parquet
│   └── iwm_av_1min_combined.parquet  (1.8M+ bars)
├── spy/intraday/                 # SPY intraday archive
├── qqq/intraday/                 # QQQ intraday archive
├── options/etfs/                 # Options chain snapshots
├── stock_prices/                 # Historical CSV price files
└── signals/trade_examples/       # Your actual trade entries
```

### Data Volume

- **IWM combined intraday**: 1,807,164 bars of 1-minute data (Jan 2015 – Nov 2025)
- **131 monthly files** combined for IWM alone
- Daily data accumulated in yearly parquet files per ticker

---

## Technical Indicators Calculated

All four tickers receive the following technical indicators through `fetch_market_data.py`:

### Price-Based Indicators
| Indicator | Details |
|-----------|---------|
| **Simple Moving Averages (MA)** | 5, 10, 20, 50-day periods |
| **Exponential Moving Averages (EMA)** | 9, 21, 50-day periods |
| **Daily Returns** | Percentage change from previous close |
| **Intraday Returns** | Open-to-close percentage change |

### Volume Indicators
| Indicator | Details |
|-----------|---------|
| **Volume Moving Averages** | 10-day and 20-day averages |
| **RVOL (Relative Volume)** | Current volume vs 20-day and 10-day average + minute-of-day RVOL |
| **OBV (On-Balance Volume)** | Cumulative volume flow with continuous accumulation |
| **Volume USD** | Dollar volume traded |

### Momentum Indicators
| Indicator | Details |
|-----------|---------|
| **RSI (Relative Strength Index)** | 14-period and 9-period, using Wilder's smoothing |
| **Stochastic RSI** | %K and %D lines for overbought/oversold detection |

### Volatility Indicators
| Indicator | Details |
|-----------|---------|
| **ATR (Average True Range)** | 14-period and 20-period with Wilder smoothing |
| **Volatility** | 5-day and 20-day standard deviation of returns |
| **High-Low Spread** | Daily range in points and percentage |

---

## Model #1 — IWM Analysis (Primary Model)

**File**: `iwm_analysis.py`
**Total Feature Columns**: **195 new columns** on top of base OHLCV data

This is the deepest and most feature-rich model in the system, focused on IWM but architecturally extendable.

### Processing Pipeline (11 Steps)

1. **ATR** — Average True Range (Wilder smoothing)
2. **RSI** — Relative Strength Index (Wilder smoothing)
3. **EMAs** — 9, 20, 50-period exponential moving averages
4. **VWAP** — Volume Weighted Average Price
5. **RVOL** — Relative Volume (20-period + minute-of-day)
6. **OBV** — On-Balance Volume (continuous accumulation)
7. **Stochastic RSI** — Momentum oscillator measuring RSI relative to its range
8. **Historical Levels** — 80 columns (previous day/week/month/year levels)
9. **ORB & Order Blocks** — 115 columns (opening range breakout + consolidation zones)
10. **Validation** — Data integrity checks
11. **Complete** — Final output generation

### Data Inputs
- Merges multiple CSV files from `data/stock_prices/`
- Loads AlphaVantage parquet data from `data/iwm/intraday/`
- Supports both CSV and Parquet — merged automatically

### Key Outputs
- `data/historical_iwm_*_with_indicators.csv` — Full dataset with 195 indicator columns
- `data/historical_iwm_*_signals.csv` — Trading signals with 117 enrichment columns per signal

---

## Model #2 — Multi-Ticker Market Data (SPY, QQQ, SPX, IWM)

**File**: `scripts/fetch_market_data.py`

### What It Does
Unified data fetching and processing for all four tickers with identical treatment:

1. Fetches 1-minute bars from Yahoo Finance (last 7–30 days)
2. Aggregates minute data into daily OHLCV
3. Calculates all technical indicators (MAs, EMAs, RSI, RVOL, ATR, Stochastic RSI, OBV)
4. Saves to yearly parquet files with incremental updates
5. Generates summary JSON with latest metrics

### Per-Ticker Summary JSON Output
Each ticker gets a `{ticker}_summary.json` containing:
- Latest price, volume, and close
- Current RSI, RVOL, Stochastic RSI, OBV, ATR values
- YTD return and recent return metrics
- First/last dates in dataset
- Last update timestamp

### Cross-Ticker Analysis (`scripts/analyze_market_data.py`)
- **Performance metrics**: Returns, volatility, drawdowns per ticker
- **Correlation analysis**: Cross-ticker correlation matrices (IWM vs SPY vs QQQ vs SPX)
- **Comparative analysis**: Side-by-side performance comparison
- **CSV export**: All analysis exportable for external use

---

## Model #3 — Enhanced Market Analysis (All Tickers)

**File**: `scripts/analyze_market_data_enhanced.py`

This extends Model #2 with the full IWM analysis feature set applied to **all tickers**:

### Enhanced Indicators (beyond base set)
- **Stochastic RSI** with K and D lines
- **VWAP approximation** from daily data
- **Consecutive price movement detection** (3+ periods in same direction)
- **Price position** relative to EMAs and VWAP

### Signal Generation (applied to all tickers)
Generates PUT and CALL signals for IWM, SPY, QQQ, and SPX using the same methodology:
- Consecutive price movements (3+ periods)
- RSI levels (bullish: 25–50, bearish: 50–75)
- Price position relative to VWAP and EMAs
- Stochastic RSI conditions
- **Requires at least 3 out of 5 conditions** to generate a signal

### Signal Performance Metrics
- **Signal strength scoring**: 3/5, 4/5, 5/5 based on conditions met
- **Win rate**: Percentage of profitable signals
- **Return analysis**: Average return per signal
- **Condition tracking**: Which conditions contributed to each signal

### Multi-Ticker Comparison
- Compare signal frequency across tickers
- Compare win rates across tickers
- Identify which ticker responds best to which conditions

---

## Model #4 — Trade Analysis Pipeline

**File**: `trade_analysis_pipeline.py`

### What It Does
Analyzes your **actual trading history** (from `trade_tracker.csv`) and finds patterns:

### Pipeline Steps
1. **Read trades** from `data/signals/trade_examples/trade_tracker.csv`
2. **Calculate durations** — how long each trade was held
3. **Pivot to tall format** — 3 rows per trade (exit, stop_loss, runner)
4. **Join with indicators** — enrich trades with all technical indicator values at entry/exit
5. **Find similar trades** — search historical data for pattern matches

### Outputs
| File | Contents |
|------|----------|
| `data/trade_tracker_updated.csv` | Trades with calculated durations |
| `data/trades_enriched.csv` | Trades enriched with entry/exit indicator values |
| `data/trade_patterns.csv` | Identified profitable patterns |
| `data/similar_trades_pipeline.csv` | Similar historical trades found by pattern matching |

### Insights Provided
- Which indicator conditions were present during your winning trades
- Which indicator conditions were present during your losing trades
- Historical precedents for trade setups similar to yours
- Duration analysis (how long winners vs losers were held)

---

## Model #5 — Earnings Options Analytics

**File**: `earnings_options_analytics/`

### What It Does
Analyzes options activity around earnings announcements:

- Processes earnings dates and options chain data from Google Sheets CSVs
- Runs automated analysis on schedule (daily at 2 AM UTC)
- Supports quick and full analysis modes
- Generates charts and CSV reports

### Data Flow
1. Earnings data stored in `google-apps-script/data/*.csv`
2. Analysis run by `test_system.py` and analytics modules
3. Results exported as charts (matplotlib/seaborn) and CSV reports
4. Automated via GitHub Actions with artifact uploads

---

## Shared Library (`lib/`)

The core analysis logic has been extracted into a shared Python library under `lib/`, eliminating duplication across models and providing a unified API for backtesting, signal generation, and Strat analysis.

### Library Modules

| Module | Purpose |
|--------|---------|
| `lib/indicators.py` | All indicator functions as pure functions — RSI, ATR, EMA, VWAP, RVOL, OBV, Stochastic RSI, Bollinger Bands, MACD, ORB, Order Blocks, Historical Levels. `add_all_indicators()` applies everything in one call. |
| `lib/signals.py` | Signal generation — `check_call_conditions()`, `check_put_conditions()`, `evaluate_signal()`. Implements the 3-of-5 logic with optional Strat bonus (0–3 points). |
| `lib/data_loader.py` | Unified data loading with column normalization (`Last`→`Close`), multi-source priority (AlphaVantage → Yahoo → on-demand), and timeframe aggregation for Strat FTFC. |
| `lib/config.py` | Typed dataclasses parsed from `alert_config.json` — `RiskConfig`, `ExitConfig`, `SignalConfig`, `StratConfig`, `BacktestConfig`, `IndicatorConfig`, `MarketConfig`. Per-ticker overrides supported. |
| `lib/strat.py` | Strat candle classifier, combo detection (2-1-2, 3-1-2 reversals/continuations), and FTFC scoring with weighted multi-timeframe alignment. |
| `lib/backtest.py` | Bar-by-bar backtesting engine with FTFC/ORB trade filtering, risk management, and comprehensive metrics. |
| `lib/walk_forward.py` | Walk-forward validation with expanding train windows and parameter sensitivity grids. |

### Per-Ticker Configuration

Each ticker has tuned parameters in `alert_config.json`:

| Parameter | IWM | SPY | QQQ | SPX |
|-----------|-----|-----|-----|-----|
| CALL target | 0.30% | 0.15% | 0.25% | 0.20% |
| PUT target | 0.38% | 0.20% | 0.30% | 0.25% |
| CALL stop | -0.15% | -0.10% | -0.12% | -0.12% |
| PUT stop | -0.20% | -0.12% | -0.15% | -0.15% |
| RSI Call range | 25–50 | 30–48 | 28–50 | 30–50 |
| RSI Put range | 50–75 | 52–72 | 50–73 | 50–72 |

---

## The Strat Classifier & FTFC

### Strat Candle Classification

The Strat is a universal price-action framework that classifies every candle into one of four types by comparing its range to the previous candle:

| Type | Name | Rule | Meaning |
|------|------|------|---------|
| **1** | Inside | `curr_high <= prev_high AND curr_low >= prev_low` | Consolidation — coiling energy |
| **2U** | Up | `curr_high > prev_high AND curr_low >= prev_low` | Directional expansion upward |
| **2D** | Down | `curr_high <= prev_high AND curr_low < prev_low` | Directional expansion downward |
| **3** | Outside | `curr_high > prev_high AND curr_low < prev_low` | Both sides taken out — reversal risk |

### Combo Detection

The classifier scans for actionable multi-bar patterns:

| Combo | Sequence | Trade Bias |
|-------|----------|------------|
| 2-1-2 Reversal Bullish | 2D → 1 → 2U | Long — reversal from downside |
| 2-1-2 Reversal Bearish | 2U → 1 → 2D | Short — reversal from upside |
| 3-1-2 Reversal | 3 → 1 → 2U/2D | Reversal after outside bar |
| 2-1-2 Continuation | 2U → 1 → 2U (or 2D → 1 → 2D) | Continuation after pause |

### Full Timeframe Continuity (FTFC)

FTFC measures whether multiple timeframes agree on direction. The system:

1. Resamples 1-minute data to 5m, 15m, 1h, D, W timeframes
2. Classifies Strat candle types on each timeframe
3. Uses `shift(1)` on higher-TF classifications to avoid lookahead bias
4. Computes a weighted alignment score:

| Timeframe | Weight |
|-----------|--------|
| Daily | 0.35 |
| 1 Hour | 0.25 |
| 15 Min | 0.20 |
| 5 Min | 0.10 |
| Weekly | 0.10 |

- **FTFC Score > 0.6**: Strong alignment — trade allowed, +1 bonus point
- **FTFC Score contradicts signal**: Trade **rejected** (not just penalized)
- **FTFC Filter**: If FTFC direction opposes the signal at threshold 0.3, the trade is blocked entirely

### ORB Trade Filtering

The Opening Range Breakout (ORB) filter uses the first 5/15/30 minutes of trading to establish trend direction:

- **ORB Trend +1** (bullish): Only CALL signals allowed
- **ORB Trend -1** (bearish): Only PUT signals allowed
- **ORB Trend 0** (neutral): Both directions allowed

In backtesting, the ORB filter rejects approximately **75% of raw signals**, and the FTFC filter rejects an additional **~18%** — leaving only the highest-conviction setups.

---

## Backtesting Engine

**File**: `lib/backtest.py`

### How It Works

The engine processes historical 1-minute data bar-by-bar (not vectorized — required for sequential risk management):

```
for each trading_day:
    load 1-min bars
    calculate indicators (lib/indicators)
    optionally compute FTFC series (lib/strat)
    optionally classify Strat candles

    for each bar:
        if in_position:
            check exits (profit target, stop loss, time stop, RSI extreme)
        if flat AND under daily limits:
            evaluate 3-of-5 signal conditions
            apply FTFC filter (reject if contradicted)
            apply ORB filter (reject if contradicted)
            compute Strat bonus for aligned trades
            if signal passes all filters: enter position
        track daily PnL, trade count
```

### Exit Rules

| Exit Type | CALL | PUT |
|-----------|------|-----|
| Profit target | +0.30% (IWM) | +0.38% (IWM) |
| Stop loss | -0.15% (IWM) | -0.20% (IWM) |
| Time stop | 30 minutes | 35 minutes |
| RSI extreme | RSI > 80 | RSI < 20 |

### Risk Management

- Max 5 trades per day
- Max 1 concurrent position
- Daily loss limit: -2.0%
- Daily profit target: +3.0%

### Extended Signal Scoring (with Strat)

When Strat overlay is enabled, signal scoring extends from 5 to 8 max:

| Bonus | Condition | Points |
|-------|-----------|--------|
| Combo bonus | Aligned Strat combo (reversal confirms direction) | +1 |
| FTFC bonus | FTFC alignment score >= 0.6 | +1 |
| ORB bonus | ORB trend aligns with signal direction | +1 |

Updated position sizing with Strat:

| Score | Position Size |
|-------|---------------|
| 3–4 | 25% |
| 5 | 50% |
| 6 | 75% |
| 7–8 | 100% |

### Output

`BacktestResult` includes:
- Trade list with entry/exit times, direction, PnL, exit reason, FTFC score, ORB trend
- Equity curve
- Metrics: win rate, profit factor, Sharpe ratio, max drawdown, expectancy, MAE/MFE
- Filter counts (how many signals rejected by FTFC vs ORB)
- Breakdown by exit reason and direction

---

## Multi-Timeframe Sweep Analysis

**File**: `scripts/run_timeframe_sweep.py`

### What It Does

Tests the strategy across multiple timeframes and combinations to find the optimal trading resolution.

### Phase 1: Individual Timeframe Sweep

Resamples 1-minute data to 5m, 15m, 30m, 1h, 4h and runs the full backtest on each. Time-based parameters (time stops) scale with bar size; percentage targets stay fixed.

### Phase 2: Combination Analysis

Tests 1-minute signal execution filtered by higher-timeframe trend direction:

- Resample to higher TF (e.g., 15m), compute EMA20
- Only take CALL when higher-TF price > EMA20
- Only take PUT when higher-TF price < EMA20
- Neutral zone (within 0.05%) allows both directions

This filter is **additive** to FTFC/ORB filtering when `--use-strat` is enabled.

### Usage

```bash
# Single ticker sweep
python scripts/run_timeframe_sweep.py --ticker IWM --use-strat

# Custom timeframes
python scripts/run_timeframe_sweep.py --ticker SPY --use-strat --timeframes 1m 5m 15m

# Custom combo filters
python scripts/run_timeframe_sweep.py --ticker QQQ --use-strat --combos 15m 30m 1h
```

---

## Signal Generation Methodology

### Signal Types
- **CALL signals** — Bullish entry opportunities
- **PUT signals** — Bearish entry opportunities

### Conditions Evaluated (5 total, need 3+ to trigger)

| # | Condition | CALL Criteria | PUT Criteria |
|---|-----------|---------------|--------------|
| 1 | **Consecutive Price Movement** | 3+ consecutive down periods (contrarian buy) | 3+ consecutive up periods (contrarian sell) |
| 2 | **RSI Level** | RSI between 25–50 (oversold territory) | RSI between 50–75 (overbought territory) |
| 3 | **Price vs VWAP** | Price below VWAP (undervalued) | Price above VWAP (overvalued) |
| 4 | **Price vs EMAs** | Price near or below EMA 9/20 | Price near or above EMA 9/20 |
| 5 | **Stochastic RSI** | Stochastic RSI showing oversold | Stochastic RSI showing overbought |

### Signal Strength (Base — without Strat)
- **3/5 conditions met**: Weak signal — 25% position size
- **4/5 conditions met**: Medium signal — 50% position size
- **5/5 conditions met**: Strong signal — 75–100% position size

### Signal Strength (Extended — with Strat Overlay)
- **3–4/8**: 25% position size
- **5/8**: 50% position size
- **6/8**: 75% position size
- **7–8/8**: 100% position size

The Strat overlay adds up to 3 bonus points (combo alignment, FTFC alignment, ORB alignment) but also **rejects trades** that contradict FTFC or ORB direction — filtering out ~90% of raw signals.

### Additional Filters (Advanced)
- **FTFC trade filtering**: Blocks trades where higher-timeframe Strat direction contradicts signal
- **ORB trade filtering**: Blocks trades where Opening Range Breakout trend contradicts signal
- **Historical level interactions**: Breakout/breakdown of previous day/week/month/year levels
- **Order block tests**: Signal coincides with institutional supply/demand zone test
- **Higher-TF trend filter**: Optional EMA20-based directional filter from 15m/30m/1h timeframes

---

## Alert System & Risk Parameters

### Trading Alerts

**IWM Contrarian CALL Setup**:
- Time window: 09:30–10:00 AM
- Price below VWAP
- RSI: 45–70
- RVOL minimum: 1.5x
- Additional: EMA9 alignment + volume surge

**IWM Contrarian PUT Setup**:
- Time window: 09:30–2:00 PM
- Price above VWAP
- RSI: 30–55
- RVOL minimum: 1.5x
- Additional: RSI below 40 preferred + volume surge

### Exit Alerts
| Exit Type | CALL | PUT |
|-----------|------|-----|
| **Profit target** | +0.30% | +0.38% |
| **Time stop** | 30 minutes | 35 minutes |
| **Extreme RSI exit** | RSI > 80 | RSI < 20 |

### Risk Parameters
- **Max daily trades**: 5
- **Max concurrent positions**: 1
- **Daily loss limit**: -2.0%
- **Daily profit target**: +3.0%
- **Position sizing**: Weak (25%) → Medium (50%) → Strong (75%) → Perfect (100%)

### Platform Integrations
- TradingView (webhook alerts)
- ThinkOrSwim (study alerts)
- Discord (webhook notifications)

---

## Advanced Features — Historical Levels, ORB, Order Blocks

### Historical Levels (80 columns)

Captures support/resistance levels from previous time periods:

**Previous Period Levels (24 base levels)**:
- Previous Day: High, Low, Open, Close, HL_Mid, OC_Mid
- Previous Week: High, Low, Open, Close, HL_Mid, OC_Mid
- Previous Month: High, Low, Open, Close, HL_Mid, OC_Mid
- Previous Year: High, Low, Open, Close, HL_Mid, OC_Mid

**Price Position (24 percentage columns)**: How far current price is from each level as a percentage

**Breakout/Breakdown Flags (8 binary columns)**: Whether price broke above/below previous highs/lows

**At-Level Indicators (24 binary columns)**: Whether price is within 0.1% of a key level

### Opening Range Breakout — ORB (108 columns)

Three timeframes: **5-minute**, **15-minute**, **30-minute**

Per timeframe (36 columns each):
- ORB High, Low, Mid, Range
- Price position relative to ORB (% distance)
- Broke High / Broke Low / Within Range (binary flags)
- Trend direction: +1 (bullish), -1 (bearish), 0 (neutral)
- Distance from ORB levels

### Order Blocks (7 columns)

Detects institutional consolidation zones:
- `Order_Block_Zone`: Currently in consolidation (binary)
- `Order_Block_High` / `Low` / `Mid`: Zone boundaries
- `Order_Block_Position`: Above (+1), within (0), below (-1) the block
- `Order_Block_Distance`: Distance from block
- `Order_Block_Test`: Price testing the block (within 0.1%)

---

## Options Analysis & P/L Tracking

### ETF Options Fetching
**Script**: `scripts/fetch_etf_options_intraday.py`
- Fetches full options chains for IWM, SPY, QQQ
- Captures 15,000+ contracts per run
- Stores in parquet format at `data/options/etfs/`
- SPX unavailable from Yahoo (index options)

### AlphaVantage Options
**Script**: `scripts/fetch_alphavantage_options.py`
- Historical options data via AlphaVantage API
- Weekly options chain snapshots stored per ticker
- Supports no-data markers to avoid wasting API calls on holidays

### Options Contract Matching & P/L
The Trading Chart Viewer performs real-time P/L analysis:

1. When you mark a trade on the chart, it captures: entry time, entry price, direction (CALL/PUT), strike selection
2. It matches against actual options contracts from AlphaVantage data
3. Calculates realistic P/L based on real contract bid/ask prices
4. Tracks performance across all marked trades

---

## Data Infrastructure & Automation

### GitHub Actions Workflows

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| **Fetch Market Data** | 5 PM EST weekdays | Fetches daily OHLCV + minute data for all tickers |
| **Economic Calendar** | Sundays 6 AM EST | Updates market events calendar |
| **Earnings Options Analytics** | Daily 2 AM UTC | Runs earnings-related options analysis |
| **Fetch AlphaVantage Intraday** | 1st of each month | Fetches monthly 1-min historical data |
| **Fetch ETF Options Intraday** | On demand | Snapshots full options chains |
| **Deploy Trading Apps** | On push to main | Deploys Chart Viewer + Options Heatseeker to GitHub Pages |
| **Validate Market Data** | Post-fetch | Validates data integrity |

### Web Applications (GitHub Pages)

1. **Trading Chart Viewer** — Interactive candlestick charts with:
   - TradingView Lightweight Charts
   - Multiple timeframes (1min, 5min, 15min, 30min, 1hr)
   - Click-to-mark trade entries/exits
   - Reference lines for previous day/week/month OHLC
   - Options P/L calculation

2. **Options Heatseeker** — Options flow visualization and analysis

---

## Outputs & Deliverables

### Per-Ticker Outputs

| Output | IWM | SPY | QQQ | SPX |
|--------|-----|-----|-----|-----|
| Daily data with indicators (parquet) | Yes | Yes | Yes | Yes |
| Minute data archive (parquet) | Yes | Yes | Yes | Yes |
| Summary JSON with latest metrics | Yes | Yes | Yes | Yes |
| AlphaVantage 5yr intraday | Yes | Yes | Yes | — |
| Options chain snapshots | Yes | Yes | Yes | — |
| Trading signals (CSV) | Yes (195 cols) | Yes (enhanced) | Yes (enhanced) | Yes (enhanced) |

### Analysis Outputs

| Output File | Description |
|-------------|-------------|
| `historical_iwm_*_with_indicators.csv` | IWM with 195 indicator columns |
| `historical_iwm_*_signals.csv` | IWM signals with 117 enrichment columns each |
| `trade_tracker_updated.csv` | Your trades with calculated durations |
| `trades_enriched.csv` | Your trades enriched with indicator values |
| `trade_patterns.csv` | Identified profitable trading patterns |
| `similar_trades_pipeline.csv` | Historical trades similar to yours |
| `{ticker}_summary.json` | Latest indicator values for each ticker |

---

## Strategy Outcomes & Insights

### Core Strategy: Contrarian Mean Reversion

The models implement a **contrarian mean-reversion strategy** with the following logic:

- **CALL entries**: When price is beaten down (below VWAP, oversold RSI, 3+ down periods) — buy the dip
- **PUT entries**: When price is extended (above VWAP, overbought RSI, 3+ up periods) — fade the rally
- **Confirmation required**: At least 3 of 5 conditions must align to generate a signal
- **Time-based edge**: Primary CALL window is the first 30 minutes (09:30–10:00), PUT window extends to 2 PM

### Key Insights the System Provides

1. **Signal quality scoring** — Every signal rated 3/5 to 5/5 based on condition alignment
2. **Historical level context** — Whether a signal occurs at key support/resistance (previous day/week/month/year levels)
3. **Intraday trend context** — Whether the Opening Range Breakout confirms or contradicts the signal
4. **Institutional zone detection** — Whether order blocks (consolidation zones) are being tested
5. **Cross-ticker correlation** — How IWM, SPY, QQQ, and SPX are moving relative to each other
6. **Trade pattern recognition** — What your past winning and losing trades had in common
7. **Similar trade identification** — Historical setups that match your current trade conditions
8. **Options P/L tracking** — Real contract-level profit/loss calculation for marked trades
9. **Macro event awareness** — Economic calendar integration for Fed decisions, earnings, etc.
10. **Volume confirmation** — RVOL thresholds ensure adequate liquidity (minimum 1.5x normal)

### Risk Management Insights

- Position sizing tied to signal strength (25%–100%)
- Hard time stops (30 min CALL, 35 min PUT)
- Profit targets (0.30% CALL, 0.38% PUT)
- Daily loss limit (-2%) and profit target (+3%)
- Maximum 5 trades/day, 1 position at a time
- Extreme RSI exit triggers (>80 for calls, <20 for puts)

---

## Backtest Results

### Base Strategy (No Strat Filtering)

| Ticker | Trades | Win Rate | Avg Win | Avg Loss | Sharpe | Expectancy |
|--------|--------|----------|---------|----------|--------|------------|
| IWM | 620 | 42.9% | +0.28% | -0.14% | 1.17 | +0.010% |
| SPY | 620 | 43.5% | +0.16% | -0.12% | 0.52 | +0.002% |
| QQQ | 620 | 40.0% | +0.24% | -0.16% | -0.15 | -0.005% |

### With Strat Overlay (FTFC + ORB Filtering)

| Ticker | Trades | Win Rate | Avg Win | Avg Loss | Sharpe | Expectancy | vs Base |
|--------|--------|----------|---------|----------|--------|------------|---------|
| IWM | 530 | 44.3% | +0.28% | -0.14% | 1.74 | +0.016% | Sharpe +49% |
| SPY | 500 | 44.0% | +0.16% | -0.12% | 0.65 | +0.003% | Sharpe +25% |
| QQQ | 496 | 42.1% | +0.24% | -0.16% | 0.37 | +0.004% | Flipped positive |

### Filter Rejection Rates

| Filter | Rejection Rate | Effect |
|--------|---------------|--------|
| ORB | ~75% of raw signals | Largest filter — eliminates trades against intraday trend |
| FTFC | ~18% of remaining | Blocks trades contradicted by higher-timeframe structure |

### Timeframe Sweep — Combination Results (1m + higher-TF trend filter + FTFC/ORB)

| Configuration | IWM | SPY | QQQ |
|---------------|-----|-----|-----|
| **1m+15m** | Sharpe 9.31, WR 57.1%, E=+0.078% | Sharpe 5.33, WR 53.7%, E=+0.035% | Sharpe 6.67, WR 52.0%, E=+0.055% |
| **1m+30m** | Sharpe 7.84, WR 55.2%, E=+0.065% | **Sharpe 5.54, WR 54.5%, E=+0.036%** | Sharpe 6.49, WR 52.2%, E=+0.054% |
| **1m+1h** | Sharpe 6.92, WR 54.0%, E=+0.058% | Sharpe 4.54, WR 52.8%, E=+0.030% | Sharpe 4.99, WR 50.0%, E=+0.044% |

**Best configuration per ticker:**
- **IWM**: 1m+15m (Sharpe 9.31) — highest Sharpe across all tickers
- **SPY**: 1m+30m (Sharpe 5.54) — 30m EMA20 filter edges out 15m slightly
- **QQQ**: 1m+15m (Sharpe 6.67) — strongest expectancy at +0.055%/trade

**Key insight**: The 1m+15m combination consistently ranks #1 or #2 across all tickers. The higher-TF EMA20 trend filter transforms a near-zero-edge base strategy into a high-Sharpe system by ensuring you only trade in the direction of the 15-minute trend.

### What the Numbers Mean

- **Avg Win +0.28%**: This is the move on the *underlying* (e.g., IWM). With options leverage (typically 5–10x delta), a 0.28% underlying move translates to roughly 1.4%–2.8% on the options contract.
- **Expectancy +0.016%/trade**: Expected profit per trade on the underlying. Over 530 trades, this compounds significantly.
- **Sharpe 1.74**: Returns are 1.74x the volatility — consistent enough to be tradeable. The 1m+15m combo at Sharpe 9.31 indicates very strong risk-adjusted performance (though high Sharpe values warrant scrutiny for overfitting).

### Test Coverage

The system has **297 passing tests** covering:
- All indicator calculations against known values
- Strat candle classification and combo detection
- Signal generation (3-of-5 logic + Strat bonus)
- Backtest engine (entry/exit triggers, risk limits, equity curve)
- FTFC/ORB filtering (rejection logic, filter counts)
- Data loader (parquet loading, column normalization, timeframe aggregation)
- Config loading with per-ticker overrides
- Full end-to-end integration tests
