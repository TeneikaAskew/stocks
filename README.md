# Stock Market Analysis System

## Overview
This repository contains tools for analyzing stock market data (IWM, SPY, QQQ, SPX), calculating technical indicators, generating trading signals, and fetching real-time market data.

## Main Components

### 1. IWM Analysis (`iwm_analysis.py`)
Comprehensive stock analysis tool that:
- **Combines CSV data**: Merges multiple CSV files containing historical stock price data
- **Calculates technical indicators**:
  - ATR (Average True Range) with Wilder smoothing
  - RSI (Relative Strength Index) with Wilder's smoothing
  - EMAs (9, 20, 50 period) using standard exponential weighting
  - VWAP (Volume Weighted Average Price)
  - RVOL (Relative Volume - both 20-period and minute-of-day)
  - OBV (On-Balance Volume) with continuous accumulation
  - Stochastic RSI (momentum oscillator measuring RSI relative to its range)
- **Generates trading signals**: Creates PUT/CALL signals based on:
  - Consecutive price movements (3+ periods)
  - RSI levels (bullish: 25-50, bearish: 50-75)
  - Price position relative to VWAP and EMAs
  - Stochastic RSI conditions
  - Requires at least 3 out of 5 conditions to be met
- **Outputs**:
  - Combined historical data CSV
  - Enhanced data with all technical indicators
  - Trading signals with entry/exit points and performance metrics

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
- `data/trade_examples/trade_tracker.csv` - Your trade entries

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

## Notes
- **Minute Data Limitation**: Yahoo Finance only provides minute-level data for the past 7 days. Historical data beyond 7 days uses daily aggregates
- The first run of `iwm_analysis.py` may take 2-3 minutes to process all data
- Indicators are calculated to match popular trading platforms (Robinhood, etc.)
- Trade examples have been moved to `data/trade_examples/`
- All market data is stored in efficient Parquet format for fast loading