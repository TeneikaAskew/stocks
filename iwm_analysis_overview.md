# IWM Analysis Scripts Overview

This document provides an overview of all scripts that analyze IWM and market data for predictive trading signals.

## Main Analysis Scripts

### 1. **iwm_analysis.py** (Primary Technical Analysis)

**Purpose**: Most comprehensive technical analysis script with feature engineering and signal generation.

**Key Features**:
- **Technical Indicators**:
  - RSI (14-period with Wilder's smoothing)
  - ATR (Average True Range)
  - EMA (9, 20, 50-period)
  - VWAP (Volume Weighted Average Price)
  - RVOL (Relative Volume - multiple methods)
  - OBV (On-Balance Volume)
  - Stochastic RSI

- **Signal Generation**:
  - Creates CALL/PUT signals based on consecutive price movements
  - Requires minimum 3 out of 5 indicator conditions met
  - Analyzes 20-period lookahead for potential exits
  - Tracks entry/exit prices, RSI, VWAP, and other indicators

- **Data Processing**:
  - Combines CSV files from `data/stock_prices/`
  - Calculates all technical indicators with proper smoothing
  - Generates trading signals with backtesting
  - Exports enhanced data with indicators and signals

**Usage**:
```bash
# Analyze last 2 months (default)
python iwm_analysis.py

# Analyze specific time period
python iwm_analysis.py -months 6

# Analyze all available data
python iwm_analysis.py -all
```

**Output Files**:
- `data/historical_iwm_0824_0825.csv` - Combined raw data
- `data/historical_iwm_0824_0825_with_indicators.csv` - Enhanced with all indicators
- `data/historical_iwm_0824_0825_signals.csv` - Generated trading signals

---

### 2. **iwm_trading_alerts.py** (Real-time Alert System)

**Purpose**: Real-time monitoring system that applies patterns learned from historical analysis.

**Key Features**:
- **Contrarian Approach**:
  - CALL signals when price < VWAP (buying dips)
  - PUT signals when price > VWAP (selling rallies)

- **Signal Conditions**:
  - Minimum requirements: VWAP position, RSI range, RVOL > 1.0
  - Strong setup: 6+ conditions met out of 10 possible
  - Time-based filtering (prime time: 9:30-10:00 AM)

- **Position Management**:
  - Profit targets: 0.30% (CALL), 0.38% (PUT)
  - Stop losses: 0.15% (CALL), 0.20% (PUT)
  - Time stops: 30 min (CALL), 35 min (PUT)
  - RSI-based exits

- **Alert Features**:
  - Audio alerts (Windows beep)
  - Console notifications
  - JSON logging to `trading_alerts_log.json`
  - Prevents duplicate alerts within same minute

**Usage**:
```python
from iwm_trading_alerts import IWMAlertSystem

alert_system = IWMAlertSystem()
alert_system.monitor_conditions(current_data)
```

---

### 3. **trade_analysis_pipeline.py** (Trade Matching & Validation)

**Purpose**: Large pipeline (2,546 lines) that validates trade patterns against historical data.

**Key Features**:
- **Trade Tracking**:
  - Reads tracked trades from `data/trade_examples/trade_tracker.csv`
  - Calculates durations and updates trade records
  - Pivots to tall format (exit, stop_loss, runner scenarios)

- **Pattern Matching**:
  - Finds similar historical trades matching your criteria
  - Uses parallel processing for performance
  - Caches DataFrames to avoid re-reading CSVs

- **Effectiveness Analysis**:
  - Tests which indicator combinations are most predictive
  - Vectorized criteria analysis for performance
  - Minimum 100 trades threshold for statistical significance
  - Calculates win rates, average returns, total returns

- **Data Processing**:
  - Cleans up old test/validation files
  - Handles multiple exit scenarios per trade
  - Joins with indicator data to identify patterns

**Key Methods**:
- `_vectorized_criteria_analysis()` - Fast criteria testing
- `_get_cached_df()` - DataFrame caching
- Pattern matching with configurable search windows

---

### 4. **scripts/analyze_market_data.py** (Basic Multi-Ticker Analysis)

**Purpose**: Basic performance metrics and analysis for all major tickers.

**Supported Tickers**: IWM, SPY, QQQ, SPX

**Key Features**:
- Price statistics (52-week high/low, current price)
- Return metrics (daily, 5-day, 20-day, 1-year)
- Volatility analysis (daily volatility, Sharpe ratio)
- Volume analysis (average daily volume, dollar volume)
- Technical indicators (MA 20/50, RSI, RVOL)
- Correlation analysis between tickers
- CSV export functionality

**Usage**:
```bash
# Analyze specific ticker
python scripts/analyze_market_data.py --ticker IWM

# Compare all tickers
python scripts/analyze_market_data.py --compare

# Show correlations
python scripts/analyze_market_data.py --correlations

# Export to CSV
python scripts/analyze_market_data.py --export all
```

---

### 5. **scripts/analyze_market_data_enhanced.py** (Advanced Multi-Ticker Analysis)

**Purpose**: Most comprehensive multi-ticker analyzer (680 lines) with full signal generation.

**Supported Tickers**: IWM, SPY, QQQ, SPX

**Key Features**:
- **All Indicators from iwm_analysis.py**:
  - RSI (9 and 14-period with Wilder's smoothing)
  - ATR (14-period)
  - Stochastic RSI
  - Moving Averages (SMA 5/10/20/50/200, EMA 9/21/50)
  - Bollinger Bands
  - MACD
  - Stochastic Oscillator
  - VWAP (daily reset)

- **Additional Metrics**:
  - 52-week high/low tracking
  - Support/Resistance levels
  - Pivot points
  - Gap analysis
  - Price position relative to all MAs
  - Consecutive movement detection

- **Signal Generation**:
  - Same methodology as iwm_analysis.py
  - Applied to all tickers (IWM, SPY, QQQ, SPX)
  - Win rate calculation
  - Profitability analysis

- **Comparative Analysis**:
  - Cross-ticker performance comparison
  - Risk metrics comparison
  - Technical indicator comparison

**Usage**:
```bash
# Analyze all tickers
python scripts/analyze_market_data_enhanced.py

# Analyze specific ticker
python scripts/analyze_market_data_enhanced.py --ticker IWM

# Export signals to CSV
python scripts/analyze_market_data_enhanced.py --export

# Compare all tickers
python scripts/analyze_market_data_enhanced.py --compare

# Filter by date
python scripts/analyze_market_data_enhanced.py --ticker IWM --start-date 2024-01-01 --end-date 2024-12-31
```

**Output Files**:
- `data/signals/{ticker}_signals.csv` - Generated signals for each ticker

---

## Data Flow Architecture

```
┌─────────────────────────────────────┐
│   Raw Data Sources                  │
│   - data/stock_prices/*.csv         │
│   - data/{ticker}/*.parquet         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   iwm_analysis.py                   │
│   - Combines CSV files              │
│   - Calculates indicators           │
│   - Generates signals               │
└──────────────┬──────────────────────┘
               │
               ├──────────────────────┐
               │                      │
               ▼                      ▼
┌──────────────────────┐    ┌────────────────────────┐
│ iwm_trading_alerts.py│    │ trade_analysis_pipeline│
│ - Real-time alerts   │    │ - Validate patterns    │
│ - Position mgmt      │    │ - Match historical     │
└──────────────────────┘    │ - Test criteria        │
                             └────────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   analyze_market_data_enhanced.py   │
│   - Apply to all tickers            │
│   - Comparative analysis            │
│   - Export signals                  │
└─────────────────────────────────────┘
```

---

## Summary: Which Script Does What?

### **For IWM-Specific Predictive Modeling:**
1. **iwm_analysis.py** - Main technical analysis and signal generation (historical backtesting)
2. **iwm_trading_alerts.py** - Real-time application of learned patterns (live trading)
3. **trade_analysis_pipeline.py** - Validation and pattern matching against historical data

### **For Broader Market Analysis:**
1. **analyze_market_data.py** - Basic multi-ticker performance analysis
2. **analyze_market_data_enhanced.py** - Advanced multi-ticker with same methodology as IWM analysis

### **Primary Script for Feature Engineering:**
**iwm_analysis.py** is the main script containing all indicator transformations and modeling for predicting successful trades. All other scripts either:
- Apply those patterns in real-time (iwm_trading_alerts.py)
- Validate them against historical data (trade_analysis_pipeline.py)
- Extend them to other tickers (analyze_market_data_enhanced.py)

---

## Key Technical Indicators Used Across Scripts

All scripts use consistent indicator calculations:

- **RSI**: Wilder's smoothing method (14-period standard)
- **ATR**: True Range with Wilder's smoothing
- **EMA**: Exponential moving average (9, 20, 50)
- **VWAP**: Daily reset, typical price weighted by volume
- **RVOL**: Multiple methods (20-period rolling, minute-of-day)
- **Stochastic RSI**: RSI fed through stochastic calculation
- **OBV**: Continuous calculation without daily resets

---

## File Locations

### Input Data:
- `data/stock_prices/*.csv` - Raw historical data
- `data/iwm/*.parquet` - Processed IWM data
- `data/trade_examples/trade_tracker.csv` - Tracked trades

### Output Data:
- `data/historical_iwm_0824_0825_with_indicators.csv` - Enhanced data
- `data/historical_iwm_0824_0825_signals.csv` - Generated signals
- `data/signals/{ticker}_signals.csv` - Per-ticker signals
- `trading_alerts_log.json` - Real-time alert log

---

## Recent Updates (December 2024)

### NEW: Historical Levels Feature ✓
- **Documentation**: [HISTORICAL_LEVELS_FEATURE.md](HISTORICAL_LEVELS_FEATURE.md)
- **Columns Added**: 80
- **Test Script**: `test_historical_levels.py`
- Tracks previous period levels (day, week, month, year)
- Includes high, low, open, close, and 50% midpoints
- Breakout/breakdown flags for each period
- At-level indicators (within 0.1% tolerance)
- Price position percentages relative to all levels

### NEW: Opening Range Breakout (ORB) ✓
- **Documentation**: [ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md)
- **Columns Added**: 108
- Three timeframes: 5-minute, 15-minute, 30-minute
- ORB high, low, mid, and range for each timeframe
- Trend direction indicators (bullish/bearish/neutral)
- Breakout/breakdown/within-range flags
- Distance from ORB levels

### NEW: Order Blocks ✓
- **Documentation**: [ORB_AND_ORDER_BLOCKS_FEATURE.md](ORB_AND_ORDER_BLOCKS_FEATURE.md)
- **Columns Added**: 7
- Consolidation zone detection using volatility
- Order block boundaries (high, low, mid)
- Price position relative to blocks
- Block test indicators
- Distance from block levels

### Summary of New Features
- **Total New Columns**: 195 (80 + 108 + 7)
- **Signal Export Enhancement**: 117 new columns per signal
- **Processing Steps**: Updated from 9 to 11 steps

See [NEW_FEATURES_SUMMARY.md](NEW_FEATURES_SUMMARY.md) for complete overview and usage examples.

---

## Performance Considerations

### iwm_analysis.py:
- Processes entire historical dataset
- Can limit to recent months with `-months` flag
- Progress indicators for long-running calculations

### trade_analysis_pipeline.py:
- Uses parallel processing (ProcessPoolExecutor)
- Caches DataFrames to avoid re-reading
- Vectorized operations for criteria analysis
- Minimum 100 trades threshold for statistical validity

### analyze_market_data_enhanced.py:
- Handles multiple tickers simultaneously
- Min periods set to 1 for limited data compatibility
- Optimized for daily data analysis

---

## Next Steps / Recommended Workflow

1. **Historical Analysis**: Run `iwm_analysis.py` to generate signals from historical data
2. **Pattern Validation**: Use `trade_analysis_pipeline.py` to validate which patterns work best
3. **Live Monitoring**: Deploy `iwm_trading_alerts.py` for real-time alerts
4. **Multi-Asset**: Extend analysis to other tickers with `analyze_market_data_enhanced.py`
5. **Refinement**: Iterate based on actual trade results tracked in trade_tracker.csv
