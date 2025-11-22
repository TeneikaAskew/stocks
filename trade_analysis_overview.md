# Trading Analysis Scripts Overview

This document provides an overview of all scripts that analyze market data for predictive trading signals.

## Main Analysis Scripts

### 1. **trading_analysis.py** (Primary Technical Analysis)
*Formerly `iwm_analysis.py`*

**Purpose**: Most comprehensive technical analysis script with feature engineering, signal generation, and feature importance analysis.

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
  - Analyzes multiple time windows (5, 10, 15, 20, 30, 45, 60 minutes) for potential exits
  - Tracks entry/exit prices, RSI, VWAP, and 195+ technical features

- **Feature Importance Analysis** (NEW):
  - Identifies top 10-20 most predictive features from 195+ indicators
  - Uses correlation analysis to measure linear relationships with profitability
  - Employs RandomForest feature importance for non-linear relationships
  - Combines both approaches with weighted scoring (40% correlation, 60% RF)
  - Exports feature rankings to help focus on most impactful indicators

- **Data Processing**:
  - Supports both CSV and Parquet formats (auto-detects best source)
  - Works with any stock symbol (IWM, SPY, QQQ, etc.)
  - Calculates all technical indicators with proper smoothing
  - Generates trading signals with backtesting
  - Exports enhanced data with indicators and signals

**Usage**:
```bash
# Analyze last 2 months (default) for IWM
python trading_analysis.py

# Analyze specific symbol
python trading_analysis.py -symbol SPY

# Analyze specific time period
python trading_analysis.py -symbol IWM -months 6

# Analyze all available data
python trading_analysis.py -symbol IWM -all

# Choose data source (auto prefers parquet)
python trading_analysis.py -symbol IWM --source parquet
python trading_analysis.py -symbol IWM --source csv
```

**Output Files**:
- `data/historical_iwm_20231114_20251114.parquet` - Combined raw data
- `data/historical_iwm_20231114_20251114_with_indicators.parquet` - Enhanced with all indicators
- `data/signals/historical_iwm_20231114_20251114_signals.parquet` - Generated trading signals
- `data/signals/historical_iwm_20231114_20251114_feature_importance.parquet` - Feature importance rankings

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

**Purpose**: Unified pipeline that automatically runs `trading_analysis.py` if needed, then validates trade patterns against historical data.

**Key Features**:
- **Automatic Prerequisite Handling** (NEW):
  - Automatically checks for indicator files
  - Runs `trading_analysis.py` if indicator files don't exist
  - No manual steps required - just run the pipeline!

- **Trade Tracking**:
  - Reads tracked trades from `data/trade_tracker.csv`
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
PS C:\Users\tenei\Documents\GitHub\stocks> & C:/Users/tenei/.pyenv/pyenv-win/versions/3.11.9/python.exe c:/Users/tenei/Documents/GitHub/stocks/iwm_analysis.py -months 24 
Analyzing last 24 months of IWM data...
Using parquet data from: data/iwm/intraday

============================================================
STEP 1: DATA COLLECTION
============================================================
Loading AlphaVantage parquet data for IWM...
Loaded 1,807,164 rows from parquet
  Including extended hours (4:00 AM - 8:00 PM)
Parquet data loaded: 1,807,164 rows
Date range: 2015-01-02 06:29:00 to 2025-11-14 20:00:00
Limited to last 24 months (450590 rows)

============================================================
STEP 2: TECHNICAL ANALYSIS
============================================================

Calculating technical indicators...
--------------------------------------------------
1/11 - Calculating ATR (Average True Range)...
2/11 - Calculating RSI (Relative Strength Index)...
3/11 - Calculating EMAs (Exponential Moving Averages)...
    - EMA 9...
    - EMA 20...
    - EMA 50...
4/11 - Calculating VWAP (Volume Weighted Average Price)...
5/11 - Calculating RVOL (Relative Volume)...
    - RVOL 20-period...
    - RVOL minute of day...
6/11 - Calculating OBV (On-Balance Volume)...
7/11 - Calculating Stochastic RSI...
    - RSI stats: min=0.55, max=100.00, mean=50.54
    - RSI valid values: 450589 out of 450590 total rows
    - StochRSI K: 450576 valid values, mean=50.65
    - StochRSI D: 450576 valid values, mean=50.65
8/11 - Calculating Historical Levels (Day, Week, Month, Year)...
    - Calculating previous day levels...
    - Calculating previous week levels...
    - Calculating previous month levels...
    - Calculating previous year levels...
    - Calculating price position relative to levels...
    - Calculating breakout/breakdown indicators...
9/11 - Calculating Order Blocks and ORB (5m, 15m, 30m)...
    - Calculating 5-minute ORB...
    - Calculating 15-minute ORB...
    - Calculating 30-minute ORB...
    - Calculating Order Blocks...
10/11 - Validating indicators...
    OK ATR14_W: 450590 valid values
    OK RSI14_W: 450589 valid values
    OK EMA9: 450590 valid values
    OK EMA20: 450590 valid values
    OK EMA50: 450590 valid values
    OK VWAP: 450590 valid values
    OK RVOL20: 450571 valid values
    OK RVOL_MOD: 450590 valid values
    OK RVOL_MOD_EXCL: 450590 valid values
    OK OBV: 450590 valid values
    OK StochRSI_K: 450576 valid values
    OK StochRSI_D: 450576 valid values

    Historical Levels:
    Prev_Day_High: 450589 valid values
    Prev_Week_High: 447947 valid values
    Prev_Month_High: 441644 valid values
    Prev_Year_High: 424183 valid values

    ORB & Order Blocks:
    ORB_5m_High: 450589 valid values
    ORB_15m_High: 450589 valid values
    ORB_30m_High: 450589 valid values
    Order_Block_High: 0 valid values
11/11 - Technical indicators, levels, and ORB calculated successfully!
--------------------------------------------------

Saving enhanced data with indicators (parquet format)...
SUCCESS: Enhanced data saved to: data/historical_iwm_20231114_20251114_with_indicators.parquet

============================================================
STEP 3: TECHNICAL SIGNAL GENERATION
============================================================

Generating technical indicator-based signals...
--------------------------------------------------
  Progress: 5000/450570 rows processed
  Progress: 10000/450570 rows processed
  Progress: 15000/450570 rows processed
  Progress: 20000/450570 rows processed
  Progress: 25000/450570 rows processed
  Progress: 30000/450570 rows processed
  Progress: 35000/450570 rows processed
  Progress: 40000/450570 rows processed
  Progress: 45000/450570 rows processed
  Progress: 50000/450570 rows processed
  Progress: 55000/450570 rows processed
  Progress: 60000/450570 rows processed
  Progress: 65000/450570 rows processed
  Progress: 70000/450570 rows processed
  Progress: 75000/450570 rows processed
  Progress: 80000/450570 rows processed
  Progress: 85000/450570 rows processed
  Progress: 90000/450570 rows processed
  Progress: 95000/450570 rows processed
  Progress: 100000/450570 rows processed
  Progress: 105000/450570 rows processed
  Progress: 110000/450570 rows processed
  Progress: 115000/450570 rows processed
  Progress: 120000/450570 rows processed
  Progress: 125000/450570 rows processed
  Progress: 130000/450570 rows processed
  Progress: 135000/450570 rows processed
  Progress: 140000/450570 rows processed
  Progress: 145000/450570 rows processed
  Progress: 150000/450570 rows processed
  Progress: 155000/450570 rows processed
  Progress: 160000/450570 rows processed
  Progress: 165000/450570 rows processed
  Progress: 170000/450570 rows processed
  Progress: 175000/450570 rows processed
  Progress: 180000/450570 rows processed
  Progress: 185000/450570 rows processed
  Progress: 190000/450570 rows processed
  Progress: 195000/450570 rows processed
  Progress: 200000/450570 rows processed
  Progress: 205000/450570 rows processed
  Progress: 210000/450570 rows processed
  Progress: 215000/450570 rows processed
  Progress: 220000/450570 rows processed
  Progress: 225000/450570 rows processed
  Progress: 230000/450570 rows processed
  Progress: 235000/450570 rows processed
  Progress: 240000/450570 rows processed
  Progress: 245000/450570 rows processed
  Progress: 250000/450570 rows processed
  Progress: 255000/450570 rows processed
  Progress: 260000/450570 rows processed
  Progress: 265000/450570 rows processed
  Progress: 270000/450570 rows processed
  Progress: 275000/450570 rows processed
  Progress: 280000/450570 rows processed
  Progress: 285000/450570 rows processed
  Progress: 290000/450570 rows processed
  Progress: 295000/450570 rows processed
  Progress: 300000/450570 rows processed
  Progress: 305000/450570 rows processed
  Progress: 310000/450570 rows processed
  Progress: 315000/450570 rows processed
  Progress: 320000/450570 rows processed
  Progress: 325000/450570 rows processed
  Progress: 330000/450570 rows processed
  Progress: 335000/450570 rows processed
  Progress: 340000/450570 rows processed
  Progress: 345000/450570 rows processed
  Progress: 350000/450570 rows processed
  Progress: 355000/450570 rows processed
  Progress: 360000/450570 rows processed
  Progress: 365000/450570 rows processed
  Progress: 370000/450570 rows processed
  Progress: 375000/450570 rows processed
  Progress: 380000/450570 rows processed
  Progress: 385000/450570 rows processed
  Progress: 390000/450570 rows processed
  Progress: 395000/450570 rows processed
  Progress: 400000/450570 rows processed
  Progress: 405000/450570 rows processed
  Progress: 410000/450570 rows processed
  Progress: 415000/450570 rows processed
  Progress: 420000/450570 rows processed
  Progress: 425000/450570 rows processed
  Progress: 430000/450570 rows processed
  Progress: 435000/450570 rows processed
  Progress: 440000/450570 rows processed
  Progress: 445000/450570 rows processed
  Progress: 450000/450570 rows processed
  Progress: 100% - Signal generation complete!

Saving trading signals (parquet format)...
SUCCESS: Trading signals saved to: data/signals/historical_iwm_20231114_20251114_signals.parquet

============================================================
ANALYSIS SUMMARY
============================================================
Total signals generated: 358693
  - Call signals: 183200
  - Put signals: 175493
  - Average return (20min): 0.12%
  - Best average return: 0.24% (avg window: 33 min)
  - Profitable signals: 311421 (86.8%)

  Returns by time window:
     5 min:   0.04% avg (73.4% profitable)
    10 min:   0.07% avg (81.2% profitable)
    15 min:   0.10% avg (84.7% profitable)
    20 min:   0.12% avg (86.8% profitable)
    30 min:   0.16% avg (89.4% profitable)
    45 min:   0.20% avg (91.5% profitable)
    60 min:   0.24% avg (92.8% profitable)

============================================================
SUCCESS: ANALYSIS COMPLETE!
============================================================

Output files:
  1. Combined data: data/historical_iwm_20231114_20251114.parquet
  2. Enhanced data: data/historical_iwm_20231114_20251114_with_indicators.parquet
  3. Trading signals: data/signals/historical_iwm_20231114_20251114_signals.parquet


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

### Unified Pipeline (Recommended)
```
┌─────────────────────────────────────────────────┐
│   User Action                                   │
│   - Log trades in data/trade_tracker.csv       │
│   - Run: python trade_analysis_pipeline.py     │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│   trade_analysis_pipeline.py                    │
│   STEP 0: Check for indicator files            │
│   └─► If missing, auto-run trading_analysis.py │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│   trading_analysis.py (if needed)               │
│   - Loads raw data (CSV/Parquet)                │
│   - Calculates 195+ indicators                  │
│   - Generates signals                           │
│   - Analyzes feature importance                 │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│   trade_analysis_pipeline.py (continued)        │
│   - Validates your trades vs historical         │
│   - Pattern matching                            │
│   - Criteria effectiveness analysis             │
│   - Comprehensive reports                       │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│   Output Files                                  │
│   - Feature importance rankings                 │
│   - Trade validation reports                    │
│   - Pattern analysis                            │
└─────────────────────────────────────────────────┘
```

### Manual Workflow (Advanced)
```
┌─────────────────────────────────────┐
│   Raw Data Sources                  │
│   - data/stock_prices/*.csv         │
│   - data/{ticker}/*.parquet         │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│   trading_analysis.py               │
│   - Combines CSV files              │
│   - Calculates indicators           │
│   - Generates signals               │
│   - Feature importance              │
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
**trading_analysis.py** is the main script containing all indicator transformations and modeling for predicting successful trades. All other scripts either:
- Apply those patterns in real-time (iwm_trading_alerts.py)
- Validate them against historical data (trade_analysis_pipeline.py)
- Extend them to other tickers (analyze_market_data_enhanced.py)

## Analysis Pipeline Steps

The `trading_analysis.py` script runs through 4 main steps:

### Step 1: Data Collection
- Loads historical price data from Parquet or CSV sources
- Auto-detects best available data source (prefers Parquet)
- Filters to specified time period (defaults to last 2 months)
- Validates data integrity and date ranges

### Step 2: Technical Analysis
- Calculates 195+ technical indicators across 11 categories:
  1. ATR (Average True Range)
  2. RSI (Relative Strength Index)
  3. EMAs (Exponential Moving Averages - 9, 20, 50)
  4. VWAP (Volume Weighted Average Price)
  5. RVOL (Relative Volume - multiple methods)
  6. OBV (On-Balance Volume)
  7. Stochastic RSI
  8. Historical Levels (Day, Week, Month, Year - 80 features)
  9. Order Blocks and ORB (5m, 15m, 30m - 115 features)
  10. Price position and breakout indicators
  11. Validation of all calculated indicators

### Step 3: Technical Signal Generation
- Evaluates every 1-minute bar for trading opportunities
- Generates CALL/PUT signals when conditions are met
- Analyzes multiple exit windows (5-60 minutes)
- Captures 195+ features at signal entry point
- Calculates actual returns for each time window

### Step 4: Feature Importance Analysis (NEW)
- Analyzes which features are most predictive of profitable trades
- Uses dual approach:
  - **Correlation Analysis** (40% weight): Measures linear relationships
  - **RandomForest Importance** (60% weight): Captures non-linear patterns
- Ranks all 195+ features by combined score
- Exports top 20 most important features
- Provides model performance metrics (R² score)

This identifies which indicators actually matter for predicting profitable trades.

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
- `data/signals/trade_examples/trade_tracker.csv` - Tracked trades

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

### Option 1: Simple Workflow (Recommended for Beginners)
**Just run one command and let the pipeline handle everything:**

```bash
# Log your trades in data/trade_tracker.csv, then run:
python trade_analysis_pipeline.py -months 2
```

This automatically:
- Runs `trading_analysis.py` if indicator files don't exist
- Generates signals and feature importance analysis
- Validates your trades against historical patterns
- Produces comprehensive analysis reports

### Option 2: Manual Workflow (Advanced Users)

1. **Historical Analysis**: Run `trading_analysis.py` to generate signals from historical data
   ```bash
   python trading_analysis.py -symbol IWM -months 6
   ```

2. **Review Feature Importance**: Examine the feature importance report to identify top indicators
   - Check `data/signals/historical_iwm_*_feature_importance.parquet`
   - Focus on top 10-20 features with highest combined scores
   - Use these insights to optimize signal generation logic

3. **Pattern Validation**: Use `trade_analysis_pipeline.py` to validate which patterns work best
   ```bash
   python trade_analysis_pipeline.py -months 6
   ```
   - Reads your trades from `data/trade_tracker.csv`
   - Matches your trades against historical patterns
   - Identifies which criteria combinations are most effective

4. **Live Monitoring**: Deploy `iwm_trading_alerts.py` for real-time alerts
   - Uses patterns learned from historical analysis
   - Generates alerts when conditions match profitable setups

5. **Multi-Asset**: Extend analysis to other tickers with `analyze_market_data_enhanced.py`
   - Apply same methodology to SPY, QQQ, etc.
   - Compare performance across different instruments

6. **Refinement**: Iterate based on actual trade results tracked in trade_tracker.csv
   - Update signal logic based on feature importance findings
   - Adjust thresholds for top-ranked indicators
   - Re-run analysis to validate improvements





PS C:\Users\tenei\Documents\GitHub\stocks> & C:/Users/tenei/.pyenv/pyenv-win/versions/3.11.9/python.exe c:/Users/tenei/Documents/GitHub/stocks/iwm_analysis.py -months 24 
Analyzing last 24 months of IWM data...
Using parquet data from: data/iwm/intraday

============================================================
STEP 1: DATA COLLECTION
============================================================
Loading AlphaVantage parquet data for IWM...
Loaded 1,807,164 rows from parquet
  Including extended hours (4:00 AM - 8:00 PM)
Parquet data loaded: 1,807,164 rows
Date range: 2015-01-02 06:29:00 to 2025-11-14 20:00:00
Limited to last 24 months (450590 rows)

============================================================
STEP 2: TECHNICAL ANALYSIS
============================================================

Calculating technical indicators...
--------------------------------------------------
1/11 - Calculating ATR (Average True Range)...
2/11 - Calculating RSI (Relative Strength Index)...
3/11 - Calculating EMAs (Exponential Moving Averages)...
    - EMA 9...
    - EMA 20...
    - EMA 50...
4/11 - Calculating VWAP (Volume Weighted Average Price)...
5/11 - Calculating RVOL (Relative Volume)...
    - RVOL 20-period...
    - RVOL minute of day...
6/11 - Calculating OBV (On-Balance Volume)...
7/11 - Calculating Stochastic RSI...
    - RSI stats: min=0.55, max=100.00, mean=50.54
    - RSI valid values: 450589 out of 450590 total rows
    - StochRSI K: 450576 valid values, mean=50.65
    - StochRSI D: 450576 valid values, mean=50.65
8/11 - Calculating Historical Levels (Day, Week, Month, Year)...
    - Calculating previous day levels...
    - Calculating previous week levels...
    - Calculating previous month levels...
    - Calculating previous year levels...
    - Calculating price position relative to levels...
    - Calculating breakout/breakdown indicators...
9/11 - Calculating Order Blocks and ORB (5m, 15m, 30m)...
    - Calculating 5-minute ORB...
    - Calculating 15-minute ORB...
    - Calculating 30-minute ORB...
    - Calculating Order Blocks...
10/11 - Validating indicators...
    OK ATR14_W: 450590 valid values
    OK RSI14_W: 450589 valid values
    OK EMA9: 450590 valid values
    OK EMA20: 450590 valid values
    OK EMA50: 450590 valid values
    OK VWAP: 450590 valid values
    OK RVOL20: 450571 valid values
    OK RVOL_MOD: 450590 valid values
    OK RVOL_MOD_EXCL: 450590 valid values
    OK OBV: 450590 valid values
    OK StochRSI_K: 450576 valid values
    OK StochRSI_D: 450576 valid values

    Historical Levels:
    Prev_Day_High: 450589 valid values
    Prev_Week_High: 447947 valid values
    Prev_Month_High: 441644 valid values
    Prev_Year_High: 424183 valid values

    ORB & Order Blocks:
    ORB_5m_High: 450589 valid values
    ORB_15m_High: 450589 valid values
    ORB_30m_High: 450589 valid values
    Order_Block_High: 0 valid values
11/11 - Technical indicators, levels, and ORB calculated successfully!
--------------------------------------------------

Saving enhanced data with indicators (parquet format)...
SUCCESS: Enhanced data saved to: data/historical_iwm_20231114_20251114_with_indicators.parquet

============================================================
STEP 3: TECHNICAL SIGNAL GENERATION
============================================================

Generating technical indicator-based signals...
--------------------------------------------------
  Progress: 5000/450570 rows processed
  Progress: 10000/450570 rows processed
  Progress: 15000/450570 rows processed
  Progress: 20000/450570 rows processed
  Progress: 25000/450570 rows processed
  Progress: 30000/450570 rows processed
  Progress: 35000/450570 rows processed
  Progress: 40000/450570 rows processed
  Progress: 45000/450570 rows processed
  Progress: 50000/450570 rows processed
  Progress: 55000/450570 rows processed
  Progress: 60000/450570 rows processed
  Progress: 65000/450570 rows processed
  Progress: 70000/450570 rows processed
  Progress: 75000/450570 rows processed
  Progress: 80000/450570 rows processed
  Progress: 85000/450570 rows processed
  Progress: 90000/450570 rows processed
  Progress: 95000/450570 rows processed
  Progress: 100000/450570 rows processed
  Progress: 105000/450570 rows processed
  Progress: 110000/450570 rows processed
  Progress: 115000/450570 rows processed
  Progress: 120000/450570 rows processed
  Progress: 125000/450570 rows processed
  Progress: 130000/450570 rows processed
  Progress: 135000/450570 rows processed
  Progress: 140000/450570 rows processed
  Progress: 145000/450570 rows processed
  Progress: 150000/450570 rows processed
  Progress: 155000/450570 rows processed
  Progress: 160000/450570 rows processed
  Progress: 165000/450570 rows processed
  Progress: 170000/450570 rows processed
  Progress: 175000/450570 rows processed
  Progress: 180000/450570 rows processed
  Progress: 185000/450570 rows processed
  Progress: 190000/450570 rows processed
  Progress: 195000/450570 rows processed
  Progress: 200000/450570 rows processed
  Progress: 205000/450570 rows processed
  Progress: 210000/450570 rows processed
  Progress: 215000/450570 rows processed
  Progress: 220000/450570 rows processed
  Progress: 225000/450570 rows processed
  Progress: 230000/450570 rows processed
  Progress: 235000/450570 rows processed
  Progress: 240000/450570 rows processed
  Progress: 245000/450570 rows processed
  Progress: 250000/450570 rows processed
  Progress: 255000/450570 rows processed
  Progress: 260000/450570 rows processed
  Progress: 265000/450570 rows processed
  Progress: 270000/450570 rows processed
  Progress: 275000/450570 rows processed
  Progress: 280000/450570 rows processed
  Progress: 285000/450570 rows processed
  Progress: 290000/450570 rows processed
  Progress: 295000/450570 rows processed
  Progress: 300000/450570 rows processed
  Progress: 305000/450570 rows processed
  Progress: 310000/450570 rows processed
  Progress: 315000/450570 rows processed
  Progress: 320000/450570 rows processed
  Progress: 325000/450570 rows processed
  Progress: 330000/450570 rows processed
  Progress: 335000/450570 rows processed
  Progress: 340000/450570 rows processed
  Progress: 345000/450570 rows processed
  Progress: 350000/450570 rows processed
  Progress: 355000/450570 rows processed
  Progress: 360000/450570 rows processed
  Progress: 365000/450570 rows processed
  Progress: 370000/450570 rows processed
  Progress: 375000/450570 rows processed
  Progress: 380000/450570 rows processed
  Progress: 385000/450570 rows processed
  Progress: 390000/450570 rows processed
  Progress: 395000/450570 rows processed
  Progress: 400000/450570 rows processed
  Progress: 405000/450570 rows processed
  Progress: 410000/450570 rows processed
  Progress: 415000/450570 rows processed
  Progress: 420000/450570 rows processed
  Progress: 425000/450570 rows processed
  Progress: 430000/450570 rows processed
  Progress: 435000/450570 rows processed
  Progress: 440000/450570 rows processed
  Progress: 445000/450570 rows processed
  Progress: 450000/450570 rows processed
  Progress: 100% - Signal generation complete!

Saving trading signals (parquet format)...
SUCCESS: Trading signals saved to: data/signals/historical_iwm_20231114_20251114_signals.parquet

============================================================
ANALYSIS SUMMARY
============================================================
Total signals generated: 358693
  - Call signals: 183200
  - Put signals: 175493
  - Average return (20min): 0.12%
  - Best average return: 0.24% (avg window: 33 min)
  - Profitable signals: 311421 (86.8%)

  Returns by time window:
     5 min:   0.04% avg (73.4% profitable)
    10 min:   0.07% avg (81.2% profitable)
    15 min:   0.10% avg (84.7% profitable)
    20 min:   0.12% avg (86.8% profitable)
    30 min:   0.16% avg (89.4% profitable)
    45 min:   0.20% avg (91.5% profitable)
    60 min:   0.24% avg (92.8% profitable)

============================================================
SUCCESS: ANALYSIS COMPLETE!
============================================================

Output files:
  1. Combined data: data/historical_iwm_20231114_20251114.parquet
  2. Enhanced data: data/historical_iwm_20231114_20251114_with_indicators.parquet
  3. Trading signals: data/signals/historical_iwm_20231114_20251114_signals.parquet



Industry Trading Algorithm Suggestions
Based on quantitative trading best practices, here are some additional features you might consider adding:
1. Market Microstructure Features
# Bid-Ask Spread Analysis
- Effective spread
- Price impact
- Order flow imbalance (buy vs sell volume)
Why: Helps identify liquidity conditions and transaction costs
2. Volume Profile Analysis
# Volume-at-Price Analysis
- Point of Control (POC) - price level with most volume
- Value Area High/Low (70% of volume)
- Volume delta (buy volume - sell volume per bar)
Why: Institutional traders use volume profile to identify support/resistance
3. Market Regime Detection
# Volatility Regimes
- GARCH-based volatility forecasting
- Regime switching models (high/low volatility states)
- Correlation regime changes

# Trend Regimes
- ADX (Average Directional Index) for trend strength
- Choppiness Index
Why: Different strategies work better in different market conditions
4. Time-Based Features
# Time-of-Day Effects
- First 15 minutes bias (opening range expansion)
- Lunch hour doldrums (11:30-1:30 PM EST)
- Power hour (3:00-4:00 PM EST momentum)
- Day of week effects
- Options expiration effects (OpEx Friday)
Why: Markets have predictable intraday patterns
5. Sentiment & News Features
# News Impact
- Earnings announcement proximity
- Fed meeting days
- Economic calendar events (NFP, CPI, FOMC)
- Tweet/news sentiment scores
Why: Major news events drive volatility and directional moves
6. Cross-Asset Features
# Correlation Features
- SPY vs IWM ratio (large cap vs small cap)
- VIX level and changes (fear gauge)
- Treasury yields (TLT, risk-on/risk-off)
- Sector rotation indicators
Why: IWM doesn't trade in isolation; correlations matter
7. Order Flow Features
# Advanced Volume Analysis
- VWAP deviation bands
- Cumulative Delta (buy vs sell aggression)
- Large lot detection (>10x average)
- Iceberg order detection
Why: Institutional order flow reveals intent
8. Machine Learning Enhancements
# Feature Engineering
- Polynomial features (RSI², RSI³)
- Interaction features (RSI * ATR)
- Lagged features (RSI_lag_1, RSI_lag_5)
- Rolling statistics (std, skew, kurtosis)

# Advanced Models
- XGBoost (usually beats RandomForest)
- LightGBM (faster, often better)
- Neural networks (LSTM for time series)
- Ensemble stacking
Why: Non-linear relationships need advanced ML
9. Risk Management Features
# Position Sizing
- Kelly Criterion based on win rate
- ATR-based position sizing
- Max drawdown constraints

# Dynamic Exits
- Trailing stops based on ATR
- Time-decay based exits (longer hold = wider stop)
- RSI divergence exits
Why: Most edge is in risk management, not entry signals
10. Walk-Forward Optimization
# Backtesting Enhancements
- Out-of-sample testing (train on 70%, test on 30%)
- Walk-forward analysis (rolling window optimization)
- Monte Carlo simulation for robustness
- Sharpe ratio maximization
Why: Prevents overfitting to historical data
Priority Recommendations
If you want to improve the current system, I'd suggest implementing in this order:
Time-based features (easy to add, high impact)
XGBoost/LightGBM models (better than RandomForest)
Walk-forward optimization (validates strategy robustness)
Volume profile analysis (institutional-grade insights)
Market regime detection (adapts to changing conditions)
The feature importance analysis you now have will help you identify which of these additions actually improve performance!