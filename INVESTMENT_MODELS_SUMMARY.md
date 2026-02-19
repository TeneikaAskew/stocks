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
9. [Signal Generation Methodology](#signal-generation-methodology)
10. [Alert System & Risk Parameters](#alert-system--risk-parameters)
11. [Advanced Features — Historical Levels, ORB, Order Blocks](#advanced-features--historical-levels-orb-order-blocks)
12. [Options Analysis & P/L Tracking](#options-analysis--pl-tracking)
13. [Data Infrastructure & Automation](#data-infrastructure--automation)
14. [Outputs & Deliverables](#outputs--deliverables)
15. [Strategy Outcomes & Insights](#strategy-outcomes--insights)

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

### Signal Strength
- **3/5 conditions met**: Weak signal — 25% position size
- **4/5 conditions met**: Medium signal — 50% position size
- **5/5 conditions met**: Strong signal — 75–100% position size

### Additional Filters (Advanced — IWM Model)
- **Historical level interactions**: Breakout/breakdown of previous day/week/month/year levels
- **ORB trend alignment**: Signal must align with Opening Range Breakout direction
- **Order block tests**: Signal coincides with institutional supply/demand zone test

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
