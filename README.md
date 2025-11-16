# Stock Market Analysis System

## Overview
This repository contains tools for analyzing stock market data (IWM, SPY, QQQ, SPX), calculating technical indicators, generating trading signals, and fetching real-time market data.

## Main Components

### 1. IWM Analysis (`iwm_analysis.py`)
Comprehensive stock analysis tool with **195 feature columns** that:
- **Combines CSV data**: Merges multiple CSV files containing historical stock price data
- **Calculates technical indicators**:
  - ATR (Average True Range) with Wilder smoothing
  - RSI (Relative Strength Index) with Wilder's smoothing
  - EMAs (9, 20, 50 period) using standard exponential weighting
  - VWAP (Volume Weighted Average Price)
  - RVOL (Relative Volume - both 20-period and minute-of-day)
  - OBV (On-Balance Volume) with continuous accumulation
  - Stochastic RSI (momentum oscillator measuring RSI relative to its range)
- **NEW: Historical Levels** (80 columns):
  - Previous day, week, month, year: High, Low, Open, Close
  - 50% midpoint levels (HL_Mid, OC_Mid)
  - Breakout/breakdown flags
  - At-level indicators (within 0.1% tolerance)
  - Price position percentages
- **NEW: Opening Range Breakout - ORB** (108 columns):
  - 5-minute, 15-minute, 30-minute opening ranges
  - Trend direction (bullish/bearish/neutral)
  - Breakout/breakdown/within-range flags
  - Shows if stock trended above/below ORB or stayed sideways
  - Distance from ORB levels
- **NEW: Order Blocks** (7 columns):
  - Consolidation zone detection
  - Support/resistance identification
  - Block test indicators
- **Generates trading signals**: Creates PUT/CALL signals based on:
  - Consecutive price movements (3+ periods)
  - RSI levels (bullish: 25-50, bearish: 50-75)
  - Price position relative to VWAP and EMAs
  - Stochastic RSI conditions
  - Historical level interactions
  - ORB trend alignment
  - Order block tests
  - Requires at least 3 out of 5 conditions to be met
- **Outputs**:
  - Combined historical data CSV
  - Enhanced data with all technical indicators (195 new columns)
  - Trading signals with entry/exit points, performance metrics, and level data (117 new columns per signal)

### 2. Trade Analysis Pipeline (`trade_analysis_pipeline.py`)
Analyzes your trading history and finds patterns:
- Reads your trades from CSV
- Calculates trade durations
- Enriches trades with technical indicators
- Identifies profitable patterns
- Finds similar historical trades

## Getting Started

### Step 1: Run IWM Analysis
```bash
# Default: Analyze last 2 months
python3 iwm_analysis.py

# Analyze all available data
python3 iwm_analysis.py -all

# Analyze specific number of months (e.g., 6 months)
python3 iwm_analysis.py -months 6
```

### Step 2: Run Trade Analysis Pipeline
After indicators are calculated, analyze your trades:

```bash
# Default: Search last 1 month for similar trades
python3 trade_analysis_pipeline.py

# Search all available data for similar trades
python3 trade_analysis_pipeline.py -all

# Search specific number of months (e.g., 2 months)
python3 trade_analysis_pipeline.py -months 2
```

## Key Files

### Input Data
- `data/stock_prices/` - Historical IWM price data (CSV files)
- `data/iwm/intraday/` - AlphaVantage Parquet data (up to 5 years of 1-minute bars)
- `data/trade_examples/trade_tracker.csv` - Your trade entries

**Note**: The pipeline automatically loads and merges both CSV and Parquet data sources. No conversion needed!

### Output Files
- `data/historical_iwm_*_with_indicators.csv` - Data with calculated indicators
- `data/historical_iwm_*_signals.csv` - Generated trading signals
- `data/trade_tracker_updated.csv` - Trades with durations
- `data/trades_enriched.csv` - Trades with entry/exit indicators
- `data/trade_patterns.csv` - Analyzed trading patterns
- `data/similar_trades_pipeline.csv` - Similar profitable trades found

## Market Data Scripts (scripts/)

### 1. Fetch Market Data (`fetch_market_data.py`)
Fetches minute-level and daily data from Yahoo Finance:
- **Supports**: IWM, SPY, QQQ, SPX (S&P 500 Index)
- **IMPORTANT**: Minute-level data is only available for the past 7 days due to Yahoo Finance limitations
- **Features**:
  - Fetches 1-minute bars for recent trading days (last 7 days)
  - Calculates true daily OHLCV from minute data
  - Computes comprehensive technical indicators
  - Stores data in efficient Parquet format
  - Saves minute data for future reference

```bash
# Fetch all tickers
python3 scripts/fetch_market_data.py

# Fetch specific tickers
python3 scripts/fetch_market_data.py --tickers IWM SPY
```

### 1b. Fetch Historical Intraday Data (`fetch_alphavantage_intraday.py`)
**Fetch up to 5 years of 1-minute historical data from AlphaVantage:**
- **Overcomes Yahoo Finance 7-day limit**
- **Supports**: Any ticker symbol
- **Features**:
  - Fetches historical 1-minute bars (up to 5 years)
  - Stores data in efficient Parquet format
  - Automatically integrated with `iwm_analysis.py`
  - Month-by-month fetching with progress tracking
  - API rate limit handling (5 calls/minute)
  - **Auto-combines all monthly files** at end of every fetch

```bash
# Fetch 5 years of IWM data
python3 scripts/fetch_alphavantage_intraday.py --symbol IWM --years 5

# Fetch specific date range
python3 scripts/fetch_alphavantage_intraday.py --symbol IWM \
  --start-date 2020-01-01 --end-date 2025-11-16

# Fetch SPY data
python3 scripts/fetch_alphavantage_intraday.py --symbol SPY --years 2
```

**Output**: `data/{symbol}/intraday/{symbol}_av_1min_combined.parquet`

**Note**: The IWM analysis pipeline automatically loads and merges this data with CSV files. No conversion needed!

### 2. Analyze Market Data (`analyze_market_data.py`)
Basic market data analysis:
- Performance metrics and statistics
- Correlation analysis between tickers
- Export to CSV format
- Technical indicator analysis

```bash
# Analyze specific ticker
python3 scripts/analyze_market_data.py --ticker IWM

# Compare all tickers
python3 scripts/analyze_market_data.py --compare

# Correlation analysis
python3 scripts/analyze_market_data.py --correlations

# Export to CSV
python3 scripts/analyze_market_data.py --export
```

### 3. Enhanced Market Analysis (`analyze_market_data_enhanced.py`)
**Comprehensive analysis with all IWM analysis features for all tickers:**
- **Calculates enhanced technical indicators**:
  - Stochastic RSI with K and D lines
  - VWAP approximation from daily data
  - Consecutive price movement detection
  - Price position relative to EMAs and VWAP
- **Generates trading signals** based on:
  - Consecutive price movements (3+ periods)
  - RSI levels (bullish: 25-50, bearish: 50-75)
  - Price position relative to VWAP and EMAs
  - Stochastic RSI conditions
  - Requires at least 3 out of 5 conditions to be met
- **Signal analysis and performance metrics**:
  - Entry/exit points with return calculations
  - Signal strength scoring (3/5, 4/5, 5/5)
  - Win rate and profitability analysis
  - Condition tracking for each signal
- **Multi-ticker comparison**: Compare signals and performance across IWM, SPY, QQQ, SPX

```bash
# Analyze all tickers with signal generation
python3 scripts/analyze_market_data_enhanced.py

# Analyze specific ticker
python3 scripts/analyze_market_data_enhanced.py --ticker SPY

# Export signals to CSV files
python3 scripts/analyze_market_data_enhanced.py --export

# Compare all tickers
python3 scripts/analyze_market_data_enhanced.py --compare
```

## Data Storage
- `data/` - Daily aggregated data in Parquet format
- `data/minute/` - Minute-level data (last 7 days only)
- `data/*_summary.json` - Latest statistics for each ticker

## Recent Updates (December 2024)

### New Features: Historical Levels, ORB, and Order Blocks
Three major feature sets have been added with **195 new columns** for enhanced pattern recognition:

1. **Historical Levels** (80 columns) - [Details](HISTORICAL_LEVELS_FEATURE.md)
   - Track previous day/week/month/year levels
   - Identify breakouts and support/resistance tests
   - 50% retracement levels (HL_Mid, OC_Mid)

2. **Opening Range Breakout - ORB** (108 columns) - [Details](ORB_AND_ORDER_BLOCKS_FEATURE.md)
   - 5m, 15m, 30m opening range analysis
   - Trend identification (bullish/bearish/neutral)
   - Intraday direction and momentum tracking

3. **Order Blocks** (7 columns) - [Details](ORB_AND_ORDER_BLOCKS_FEATURE.md)
   - Consolidation zone detection
   - Institutional supply/demand zones
   - Support/resistance confirmation

### Quick Test
```bash
# Test historical levels feature
python test_historical_levels.py

# Run analysis with new features (2 months for testing)
python iwm_analysis.py -months 2
```

### Documentation
- [NEW_FEATURES_SUMMARY.md](NEW_FEATURES_SUMMARY.md) - Complete feature overview
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick reference guide
- [iwm_analysis_overview.md](iwm_analysis_overview.md) - All analysis scripts overview

## Notes
- **New Features**: 195 additional columns now available for analysis (80 Historical Levels + 108 ORB + 7 Order Blocks)
- **Minute Data Limitation**: Yahoo Finance only provides minute-level data for the past 7 days. Historical data beyond 7 days uses daily aggregates
- The first run of `iwm_analysis.py` may take 3-4 minutes with new features
- Indicators are calculated to match popular trading platforms (Robinhood, etc.)
- Trade examples have been moved to `data/trade_examples/`
- All market data is stored in efficient Parquet format for fast loading