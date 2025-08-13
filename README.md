# stocks

# IWM Stock Analysis and Trading Signal System

## Overview
This repository contains tools for analyzing IWM (iShares Russell 2000 ETF) historical data, calculating technical indicators, and generating trading signals.

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

## Notes
- The first run of `iwm_analysis.py` may take 2-3 minutes to process all data
- Indicators are calculated to match popular trading platforms (Robinhood, etc.)
- Trade examples have been moved to `data/trade_examples/`