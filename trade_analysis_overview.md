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

---

## System Integration: Phase Analysis + Legacy Pipeline + PineScript

This section describes how the **Phase 1-7 analysis system** (built Feb 2025), the **legacy Python pipeline** (`trading_analysis.py`, `trade_analysis_pipeline.py`, `morning_checklist_analysis.ipynb`), and the **TradingView PineScript indicators** fit together as a unified trading ecosystem.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA LAYER (Python)                              │
│  data_loader.py → Parquet/CSV intraday data (IWM, SPY, QQQ)           │
│  indicators.py  → 195+ technical features (RSI, ATR, EMA, VWAP, etc.) │
│  strat.py       → Strat candle classification + FTFC scoring           │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────────────────┐
│ LEGACY PIPELINE  │ │ PHASE SYSTEM │ │ TRADINGVIEW PINESCRIPT        │
│                  │ │ (Phases 1-7) │ │                              │
│ trading_analysis │ │              │ │ session-levels-trends (90%)  │
│   .py            │ │ Phase 1:     │ │ orb-30 (80%)                 │
│ → 195+ features  │ │  Strat mining│ │ iwm-bsvp (85%)               │
│ → ML feature     │ │ Phase 2:     │ │ iwm-scalping (75%)           │
│   importance     │ │  Indicator   │ │                              │
│ → Signal scoring │ │  confirmation│ │ WHAT THEY DO:                │
│                  │ │ Phase 3:     │ │ → Live chart overlays        │
│ trade_analysis   │ │  ORB strats  │ │ → Real-time alerts           │
│   _pipeline.py   │ │ Phase 4:     │ │ → Visual entry/exit cues     │
│ → Pattern match  │ │  Setup disc. │ │ → Multi-symbol scanning      │
│ → Criteria test  │ │ Phase 5:     │ │                              │
│ → Trade validate │ │  Regime/time │ │ WHAT THEY LACK:              │
│                  │ │ Phase 6:     │ │ → Statistical backing        │
│ morning_checklist│ │  Playbook    │ │ → Probability calibration    │
│   _analysis.ipynb│ │ Phase 7:     │ │ → Strat pattern awareness    │
│ → Daily scoring  │ │  Feedback    │ │ → FTFC multi-TF scoring      │
│ → Live readiness │ │  loop        │ │ → Walk-forward validated     │
│                  │ │              │ │   thresholds                 │
└──────────────────┘ └──────────────┘ └──────────────────────────────┘
          │                │                         │
          └────────────────┼─────────────────────────┘
                           ▼
              ┌────────────────────────┐
              │   COMBINED SYSTEM      │
              │                        │
              │ Python: Discovery +    │
              │   Validation engine    │
              │ PineScript: Live       │
              │   execution interface  │
              │ Playbook: Decision     │
              │   framework            │
              └────────────────────────┘
```

### How the Three Systems Complement Each Other

#### 1. Legacy Python Pipeline → Discovery & Feature Engineering

**`trading_analysis.py`** is the feature factory:
- Calculates all 195+ indicators on historical data
- ML-driven feature importance identifies which indicators actually predict profitable trades
- Generates raw CALL/PUT signals with the 3-of-5 scoring system
- Produces the enhanced datasets that feed everything else

**`trade_analysis_pipeline.py`** is the trade validator:
- Takes real trades from `trade_tracker.csv` and enriches them with indicator snapshots
- Tests 100+ boolean criteria against actual outcomes
- Finds similar historical trades matching current patterns
- Answers: "Given these exact conditions, what happened historically?"

**`morning_checklist_analysis.ipynb`** is the daily decision tool:
- Scores current market conditions against your patterns
- 8-condition checklist per trade type based on actual trade data
- Bridges the gap between "the system says X" and "should I trade today?"

#### 2. Phase 1-7 Analysis → Statistical Foundation & Probability Calibration

The phase system provides what the legacy pipeline and PineScript indicators lack — **statistically validated probabilities**:

| Phase | What It Provides to the Combined System |
|-------|----------------------------------------|
| **Phase 1** | Exact transition probabilities for every Strat pattern (e.g., "after 2U-2U on IWM 1m, next bar is 2U 38% of the time") |
| **Phase 2** | Predictive lift of each indicator — which ones actually move the needle vs. noise |
| **Phase 3** | Backtested ORB strategy parameters (targets, stops, time limits) per ticker |
| **Phase 4** | High-probability indicator combinations with sample sizes and confidence levels |
| **Phase 5** | Context adjustments: regime-dependent parameters, time-of-day edges, options translation |
| **Phase 6** | 12 actionable playbook cards per ticker with specific entry/exit rules and expected stats |
| **Phase 7** | Live feedback templates to track whether real trading matches backtest expectations |

#### 3. TradingView PineScript Indicators → Live Execution Interface

The existing PineScript indicators are the **front-end** where trades are actually executed:

| Indicator | Current Capability | Phase System Enhancement Opportunity |
|-----------|-------------------|--------------------------------------|
| **session-levels-trends** | Previous D/W/M levels, ORB, Supertrend | Add Strat candle type labels, FTFC score overlay, Phase 4 "at level" probability labels |
| **orb-30** | Multi-symbol ORB breakout scanner | Add Phase 3 ORB failure detection, mean-reversion alerts, ATR-adjusted targets from Phase 5A |
| **iwm-bsvp** | Volume pressure analysis + entry scoring | Integrate Phase 2 reversal early warning scorecard, add Phase 4 high-probability combo alerts |
| **iwm-scalping** | 27-lane multi-indicator dashboard | Replace hardcoded thresholds with Phase 4's statistically validated thresholds, add FTFC lane |

### PineScript Integration Roadmap

The Phase analysis outputs are directly translatable to PineScript indicators. Here's what's actionable:

#### Tier 1: Direct Ports (Highest Impact)

**A. Strat Candle Classifier + FTFC Overlay**
- Port `strat.py`'s `classify_candle()` to Pine — label every bar as 1/2U/2D/3
- Display FTFC score from 5m/15m/1h/D (weighted 0.10/0.20/0.25/0.35)
- Color bars by Strat type, show combo patterns (2-1-2, 3-1-2) as arrows
- **Why first:** FTFC filtering was the single biggest edge improvement (Sharpe +70-195%)

**B. Phase 6 Playbook Signal Alerts**
- Encode the 12 playbook cards per ticker as Pine conditions
- Fire alerts when card conditions are met (e.g., "Bullish Reversal 2D-1-2U + RSI<45 + Below VWAP")
- Display signal score (3-8) and expected win rate from Phase 4 data
- **Why second:** Turns research into real-time actionable alerts

**C. Multi-Timeframe Trend Filter**
- The 1m+15m combo (Sharpe 9.31 on IWM) only needs: 15m EMA20 direction
- Add a simple overlay showing higher-TF EMA20 trend alignment
- Block/dim signals that contradict the higher-TF trend
- **Why third:** This single filter transforms near-zero-edge signals into high-Sharpe trades

#### Tier 2: Enhanced Existing Indicators

**D. ORB Strategy Enhancement**
- Add Phase 3's ORB failure/mean-reversion logic to orb-30
- Display ORB width percentile (is today's range narrow or wide vs. history?)
- ATR-adaptive targets from Phase 5A regime analysis
- Add time-of-day optimal windows from Phase 5B

**E. Reversal Early Warning Scorecard**
- Port Phase 2's weighted reversal checklist to a Pine panel
- Score 0-10 reversal risk in real-time
- Flash warning when score exceeds threshold (7+ = "exit now")
- Integrate with iwm-bsvp's divergence detection

**F. Regime-Aware Parameter Adjustment**
- Auto-detect ATR regime (Low/Normal/High Vol) from Phase 5A
- Adjust displayed targets/stops based on current regime
- Change indicator colors/labels to reflect regime

#### Tier 3: New Indicators from Phase Data

**G. Cross-Ticker Confirmation Panel**
- Show IWM/SPY/QQQ Strat types side-by-side
- When all three agree: flag "Cross-Ticker Confirmation" (Phase 5D shows 2-5pp win rate lift)
- Alert when agreement breaks down

**H. Probability Label Overlay**
- At key levels (Prev Day High/Low, ORB boundaries), show Phase 1 probabilities
- "At Prev Day High: 62% chance of 2D next bar" based on Phase 1 transition data
- Turn support/resistance from visual lines into probability-annotated zones

### Data Flow: Python → PineScript

The Phase analysis produces statistics that PineScript indicators consume as hardcoded constants:

```
Python Phase Analysis                    PineScript Constants
─────────────────────                    ────────────────────
Phase 1: P(2U→2D|IWM,1m) = 0.25    →   reversal_prob_2u = 0.25
Phase 3: ORB target = +0.30%        →   orb_target_pct = 0.0030
Phase 4: RSI<30 + >VWAP WR = 72%   →   combo_threshold = 0.72
Phase 5A: High vol → 2x target      →   vol_regime_mult = 2.0
Phase 5B: Best CALL hour = 9:30-10  →   call_start = 0930, call_end = 1000
Phase 6: Card thresholds per ticker  →   iwm_rsi_call_max = 50
```

This means: **re-run the Python phases periodically (monthly/quarterly), extract the latest statistics, and update PineScript constants.** The indicators don't need to compute probabilities live — they apply pre-computed probability-calibrated thresholds.

### What the Combined System Achieves

| Capability | Legacy Only | Phases Only | PineScript Only | **Combined** |
|-----------|-------------|-------------|-----------------|-------------|
| Feature engineering | 195+ features | 195+ features | ~20 indicators | 195+ features |
| Statistical validation | ML importance | Walk-forward, 10yr backtest | None | Walk-forward validated |
| Live execution | None (batch) | None (batch) | Real-time charts | Real-time + validated |
| Probability calibration | RandomForest | Per-pattern, per-ticker | Hardcoded | Phase-calibrated live |
| Multi-timeframe | Single TF | All TFs + combos | 1-3 TFs | Full FTFC stack |
| Strat awareness | Basic | Complete (1/2U/2D/3, FTFC, combos) | None | Strat-native live |
| Trade management | Post-hoc analysis | Backtest-simulated | Manual | Guided by stats |
| Regime adaptation | None | ATR/VIX regimes | Static params | Dynamic + validated |
| Feedback loop | trade_tracker.csv | Phase 7 templates | None | Closed loop |

### Recommended Combined Workflow

1. **Monthly:** Re-run Phase 1-5 scripts to update transition probabilities and regime parameters
2. **Weekly:** Run Phase 7B weekly review template against your trade journal
3. **Daily (Pre-Market):** Run `morning_checklist_analysis.ipynb` + Phase 7C regime check
4. **Live Trading:** Use PineScript indicators (with Phase-calibrated thresholds) for entry/exit
5. **Post-Trade:** Log in Phase 7A tracker, run `trade_analysis_pipeline.py` for pattern matching
6. **Quarterly:** Run Phase 5G walk-forward validation to check if patterns still hold

---

## Trading Terms Glossary

A plain-English reference for every trading term used in the analysis system, backtest results, and playbook. Organized by category. When a term has a specific meaning in THIS system (vs. general trading), that's noted.

---

### The Strat (Rob Smith's Method)

**The Strat** — A price action methodology that classifies every candle (bar) into one of four types based on how its high and low compare to the PREVIOUS candle's high and low. It's a framework for reading what the market is doing right now and what's likely to happen next.

#### Candle Types (Strat Classification)

- **Type 1 — Inside Bar:** The current bar's high is at or below the previous bar's high AND the current bar's low is at or above the previous bar's low. The bar fits entirely "inside" the prior bar. This means the market is compressing, pausing, or building energy. Think of it as indecision — neither buyers nor sellers are winning. The next bar that breaks out of this range often moves with conviction.

- **Type 2U — Up Bar:** The current bar makes a higher high than the previous bar BUT does not make a lower low. The market is pushing up. Buyers are in control. The "U" stands for Up.

- **Type 2D — Down Bar:** The current bar makes a lower low than the previous bar BUT does not make a higher high. The market is pushing down. Sellers are in control. The "D" stands for Down.

- **Type 3 — Outside Bar:** The current bar makes BOTH a higher high AND a lower low than the previous bar. The range expanded in both directions. This is high volatility — both sides are fighting. Often a sign of a big move coming, and the direction it closes tells you who won.

**Strat Combo** — A specific sequence of 2-3 candle types that forms a recognizable pattern. The most important ones:

- **2-1-2 Reversal:** A directional bar (2U or 2D), followed by an Inside bar (1), followed by a bar in the OPPOSITE direction (2D or 2U). This is the classic Strat reversal pattern. Example: 2U → 1 → 2D means price went up, paused, then reversed down.

- **3-1-2 Reversal:** An Outside bar (3), followed by an Inside bar (1), followed by a directional bar (2U or 2D). Considered a stronger reversal than 2-1-2 because the outside bar shows extreme volatility before the pause and reversal.

- **Continuation:** Multiple bars in the same direction. Example: 2U → 2U → 2U means price keeps pushing higher. The question is always "how many in a row before it reverses?"

**Transition Probability** — The statistical likelihood that one candle type follows another. Example: "After a 2U bar on IWM 1-minute charts, the next bar is 2U 38% of the time, 2D 25% of the time, Inside 30% of the time, Outside 7% of the time." This is what Phase 1 of the analysis calculates.

**FTFC — Full Timeframe Continuity** — When multiple timeframes are all pointing in the same direction. If the daily bar is 2U, the 1-hour is 2U, and the 15-minute is 2U, you have full bullish timeframe continuity. In this system, FTFC is calculated as a weighted score: Daily counts most (0.35), then 1h (0.25), 15m (0.20), 5m (0.10), Weekly (0.10). A score above 0.6 means strong alignment. Trades that CONTRADICT the FTFC direction are rejected entirely.

*Why FTFC matters:* If you see a CALL signal on the 1-minute chart but the daily and hourly are both bearish (2D), you're fighting the larger trend. FTFC filtering prevents this.

---

### Price Action & Chart Reading

**OHLCV** — The five basic data points for any candle/bar: Open, High, Low, Close, Volume. Open is where price started that period, High is the highest point reached, Low is the lowest point reached, Close is where it ended, and Volume is how many shares traded.

**Candle / Bar** — A visual representation of price movement over a time period. A 1-minute candle shows what happened in one minute. A daily candle shows what happened in one day. Every candle has an open, high, low, and close.

**Timeframe** — The time period each candle represents. This system uses: 1-minute (1m), 5-minute (5m), 15-minute (15m), 30-minute (30m), 1-hour (1h), daily, and weekly. Lower timeframes show more detail but more noise. Higher timeframes show the bigger picture.

**Multi-Timeframe Analysis** — Looking at the same ticker across different timeframes to get context. A signal on the 1-minute chart is more trustworthy when the 15-minute and daily charts agree with the direction. This system's best result (Sharpe 9.31) comes from combining 1m signals with 15m trend direction.

**Support** — A price level where buying pressure tends to increase, stopping price from falling further. Think of it as a floor. In this system, support levels include previous day/week/month lows, ORB lows, and order block lows. "At support" means price is currently at or very near (within 0.1%) one of these levels.

**Resistance** — A price level where selling pressure tends to increase, stopping price from rising further. Think of it as a ceiling. Resistance levels include previous day/week/month highs, ORB highs, and order block highs. "At resistance" means price is at or very near one of these levels.

**Breakout** — When price moves decisively above a resistance level or below a support level. A breakout above yesterday's high means buyers pushed through that ceiling. Breakouts can be real (price continues in the breakout direction) or false (price reverses back — see "ORB Failure").

**Breakdown** — The bearish version of a breakout — price drops below a support level. Same concept, opposite direction.

**Confluence** — When multiple indicators, levels, or signals point to the same conclusion at the same time. Example: RSI is oversold, price is at the previous week low, AND the Strat shows a 2-1-2 reversal — that's confluence. More confluence = higher confidence in the trade.

**Price Action** — Trading based on what price itself is doing (the candles, the levels, the patterns) rather than relying only on calculated indicators. The Strat is a price action method. It reads the candles directly.

---

### Technical Indicators

**RSI — Relative Strength Index** — A momentum oscillator that measures how fast and how much price has moved recently, on a scale of 0 to 100. This system uses a 14-period RSI with Wilder's smoothing.
- Below 30: Oversold (price has dropped a lot — potential bounce coming)
- 30-50: Bearish but not extreme
- 50-70: Bullish but not extreme
- Above 70: Overbought (price has risen a lot — potential pullback coming)
- Above 80: Extremely overbought (this system exits CALL trades here)
- Below 20: Extremely oversold (this system exits PUT trades here)

**RSI Divergence** — When price makes a new high but RSI makes a LOWER high (or price makes a new low but RSI makes a higher low). This disconnect between price and momentum is an early warning that the trend is weakening. Phase 2 of the analysis looks for this as a reversal predictor.

**EMA — Exponential Moving Average** — A smoothed average of price that gives more weight to recent data. This system uses EMA 9 (fast, tracks price closely), EMA 20 (medium, shows short-term trend), and EMA 50 (slow, shows longer trend).
- Price above EMA = bullish (uptrend)
- Price below EMA = bearish (downtrend)
- EMA 9 crossing above EMA 20 = "bullish cross" (short-term momentum turning up)
- EMA 9 crossing below EMA 20 = "bearish cross" (short-term momentum turning down)

**SMA — Simple Moving Average** — Like EMA but gives equal weight to all periods. Slower to react. This system uses SMA 5, 10, 20, 50. EMAs are generally preferred for faster signals.

**VWAP — Volume Weighted Average Price** — The average price weighted by volume throughout the trading day. Resets every day at market open. Institutional traders heavily reference VWAP.
- Price above VWAP: Institutions who bought today are generally profitable — bullish bias
- Price below VWAP: Institutions who bought today are generally underwater — bearish bias
- VWAP acts as a magnet — price tends to return to it (mean reversion)

**ATR — Average True Range** — Measures how much a ticker typically moves per bar, accounting for gaps. Higher ATR = more volatile. This system uses 14-period and 20-period ATR.
- ATR > 1.5x average = unusually volatile day (wider stops may be needed)
- ATR < 0.5x average = unusually quiet day (targets may not be reached)

**Stochastic RSI (StochRSI)** — An oscillator that measures where RSI is relative to its own recent range. More sensitive than RSI alone. Has two lines: %K (fast) and %D (slow).
- StochRSI oversold: momentum is at the bottom of its recent range — potential bounce
- StochRSI overbought: momentum is at the top of its recent range — potential pullback
- Most useful at extremes; less meaningful in the middle

**RVOL — Relative Volume** — Current volume compared to what's "normal" for this time of day and this ticker. RVOL of 1.0 = average volume. This system also adjusts for minute-of-day (volume is naturally higher at open and close).
- RVOL > 1.5: Significantly above average — big players are active, moves are more likely to follow through
- RVOL 0.8-1.5: Normal range
- RVOL < 0.8: Below average — low conviction, moves may fizzle

**OBV — On-Balance Volume** — A running total that adds volume on up-bars and subtracts volume on down-bars. Shows whether volume is flowing into the stock (buying pressure) or out (selling pressure).
- OBV rising while price rises = healthy trend (volume confirms)
- OBV falling while price rises = divergence (price going up on declining participation — warning)
- OBV rising while price falls = accumulation (someone is buying the dip)

---

### ORB — Opening Range Breakout

**Opening Range (OR)** — The high and low of the first N minutes of trading after market open (9:30 AM). This system calculates three opening ranges: 5-minute (9:30-9:35), 15-minute (9:30-9:45), and 30-minute (9:30-10:00). The opening range sets the "battlefield" for the day.

**ORB High / ORB Low / ORB Mid** — The top, bottom, and midpoint of the opening range. These act as intraday support and resistance levels.

**ORB Range** — The distance (in price or percentage) between the ORB High and ORB Low. Wider ranges = more volatile open. Narrow ranges = compressed, expecting a breakout.

**ORB Trend** — The direction price has moved relative to the opening range:
- +1 (Bullish): Price broke above the ORB high — buyers won the opening battle
- -1 (Bearish): Price broke below the ORB low — sellers won
- 0 (Neutral): Price is still within the opening range — undecided

**ORB Breakout** — When price moves above the ORB high (bullish breakout) or below the ORB low (bearish breakout). A confirmed breakout with volume (RVOL > 1.0) and Strat continuation (2U for bullish) is higher conviction.

**ORB Failure** — When price breaks out of the ORB but then reverses back inside the range. A false breakout. In Phase 3 of the analysis, we test a strategy that specifically trades these failures — fading the false breakout back toward the ORB mid.

**ORB Range-Bound** — When price stays inside the opening range for an extended period. In this scenario, ORB high and low act as resistance and support for bounce trades.

---

### Order Blocks

**Order Block** — A price zone where large institutional players (banks, hedge funds, mutual funds) have significant buy or sell orders clustered together. Identified by detecting areas of consolidation (tight range, high volume) that precede a strong directional move. When price returns to an order block, it often reacts because those institutional orders may still be there.

**Order Block Zone** — A flag (1 or 0) indicating the current bar is part of a consolidation zone that qualifies as an order block.

**Order Block Position** — Where current price sits relative to the nearest order block:
- +1 (Above): Price has cleared the order block — it now acts as support below
- 0 (Within): Price is inside the order block — testing institutional levels
- -1 (Below): Price failed at the order block — it acts as resistance above

**Order Block Test** — When price touches or gets very close to an order block boundary. These are moments where price often bounces or reverses. A test of an order block combined with a Strat reversal pattern is a higher-conviction setup.

---

### Historical Levels

**Previous Day/Week/Month/Year High and Low** — The highest and lowest prices from the prior day, week, month, or year. These are key support and resistance levels because many traders watch them.
- Breaking above a prior high = bullish (old resistance becomes new support)
- Falling below a prior low = bearish (old support becomes new resistance)

**HL Mid** — The midpoint between the high and low of a period. Example: if yesterday's high was $200 and low was $198, the HL Mid is $199. Acts as a secondary support/resistance level.

**Price Position (%)** — How far current price is from a historical level, expressed as a percentage. Example: "Price is 0.3% below the previous week high" tells you you're close to resistance.

**"At Level" Flag** — A binary indicator (1 or 0) that fires when price is within 0.1% of a key level. When this flag is 1, you're right at a decision point where price often reacts.

**Breakout Flag** — A binary indicator (1 or 0) that fires when price has moved above a prior high (or below a prior low). "Broke Prev Day High = 1" means today's price exceeded yesterday's high.

---

### Signal Generation & Scoring

**Signal** — An alert that trading conditions have been met. In this system, a signal fires when 3 or more of 5 conditions align. Signals are either CALL (bullish — expect price to go up) or PUT (bearish — expect price to go down).

**CALL Signal** — A bullish entry signal. The system looks for price that's been beaten down (below VWAP, oversold RSI, consecutive down bars) and expects a bounce. You would buy a call option to profit from the expected upward move.

**PUT Signal** — A bearish entry signal. The system looks for price that's extended (above VWAP, overbought RSI, consecutive up bars) and expects a pullback. You would buy a put option to profit from the expected downward move.

**Signal Strength / Score** — How many conditions are met. Base system scores 3-5 (out of 5 conditions). With Strat overlay, scores go up to 8 (5 base + 3 bonuses for Strat combo, FTFC alignment, and ORB alignment). Higher score = higher confidence = larger position size.

**3-of-5 Conditions** — The core signal logic. For a CALL, these five conditions are checked:
1. 3+ consecutive down bars (contrarian — price has dropped enough)
2. RSI between 25-50 (oversold territory)
3. Price below VWAP (undervalued vs. daily average)
4. Price near or below EMA 9/20 (below short-term trend)
5. Stochastic RSI showing oversold

At least 3 must be true. For PUT signals, it's the mirror image (3+ up bars, RSI 50-75, above VWAP, etc.).

**Signal Filtering** — The process of rejecting signals that pass the 3-of-5 test but fail additional checks. FTFC filtering rejects trades that contradict higher-timeframe direction. ORB filtering rejects trades that contradict the session's opening range trend. Approximately 16% of raw signals get filtered out.

**Position Sizing** — How much capital to put into each trade, based on signal strength:
- Score 3-4: 25% of normal position (low conviction)
- Score 5: 50% (medium conviction)
- Score 6: 75% (high conviction)
- Score 7-8: 100% (maximum conviction)

---

### Trade Management

**Entry** — The moment you open a trade (buy the option). In this system, entries are on 1-minute candles during specific windows: CALLs between 9:30-10:00 AM, PUTs between 9:30-2:00 PM.

**Exit** — The moment you close a trade (sell the option). Four possible exit types in this system:
- *Profit Target:* Price moved in your favor by the target amount. You take profit. For IWM: +0.30% for CALLs, +0.38% for PUTs. This is a WIN.
- *Stop Loss:* Price moved against you by the maximum allowed amount. You cut the loss. For IWM: -0.15% for CALLs, -0.20% for PUTs. This is a LOSS.
- *Time Stop:* Neither target nor stop was hit within the allowed time (30 min for CALLs, 35 min for PUTs). You exit at whatever price it's at. These win 55-63% of the time with small gains.
- *RSI Extreme Exit:* RSI hit an extreme level while you're in a trade (above 80 for CALLs, below 20 for PUTs). This forces an exit because the move may be exhausted. Rare but profitable when triggered.

**Profit Target** — The price level where you take profit and close the trade. Set as a percentage move on the underlying: +0.30% for IWM CALLs means if IWM moves up 0.30% from your entry, you exit with profit.

**Stop Loss** — The maximum you're willing to lose on a single trade. If price moves against you by this amount, you exit immediately. Protects capital from large losses. Must be respected — moving stops wider is how accounts blow up.

**Time Stop** — A time-based exit. If the trade hasn't hit its profit target or stop loss within the allotted time, you close it. Prevents capital from being tied up in a trade that isn't working. This system uses 30 minutes for CALLs and 35 minutes for PUTs.

**Trailing Stop** — A stop loss that moves in your favor as the trade works. Example: if you entered at $200 with a trailing stop of -0.10%, and price moves to $201, your stop automatically moves up to $200.80. This system doesn't currently use trailing stops, but the analysis suggests testing them for time-stop trades (which win 55-63% but with small returns that could be larger with a trailing stop).

**Hold Time / Duration** — How long you're in a trade from entry to exit. In this system, average hold time is 17-19 minutes. Winners take longer to develop (21-22 min) than losers take to fail (14-17 min). If a trade hasn't moved in your favor within 7-10 minutes, the probability of success drops significantly.

---

### Backtest & Performance Metrics

**Backtest** — Testing a trading strategy on historical data to see how it would have performed. This system backtests on 10 years of 1-minute data (Jan 2015 – Feb 2025). Backtesting tells you if a strategy has a statistical edge, but past performance doesn't guarantee future results.

**Walk-Forward Validation** — A more rigorous way to backtest. Instead of testing on ALL historical data at once (which can find patterns that don't repeat), you train on a chunk of data, then test on the NEXT chunk, then move forward. If a strategy works in walk-forward testing, it's much more likely to work in live trading. Strategies that only work in regular backtesting but fail walk-forward are "overfit" to historical noise.

**Win Rate** — The percentage of trades that are profitable. A 42% win rate means 42 out of every 100 trades make money. Win rate alone doesn't determine profitability — you also need to know how much the winners make vs. how much the losers lose.

**Profit Factor (PF)** — Total gross profits divided by total gross losses. PF = 1.0 means you broke even. PF > 1.0 means profitable. PF > 1.5 is good. PF > 2.0 is exceptional. Example: if your winners made $10,000 total and your losers lost $8,000, PF = 10,000/8,000 = 1.25.

**Sharpe Ratio** — A measure of risk-adjusted return. It tells you how much return you get per unit of risk (volatility). Higher is better. Calculated as average return divided by the standard deviation of returns.
- Below 0: Losing money
- 0-1: Positive but not impressive
- 1-2: Good, tradeable edge
- 2-3: Very good
- Above 3: Exceptional (but verify it's not overfitting)
- The 1m+15m IWM combo shows Sharpe 9.31 — extremely high, which is why it warrants scrutiny for overfitting

**Expectancy** — The average profit or loss you can expect per trade, in percentage terms. Calculated as: (win rate × avg win) - (loss rate × avg loss). Positive expectancy means the strategy is profitable over many trades. Even small positive expectancy compounds over thousands of trades.
- IWM Strat: +0.004% per trade × 11,664 trades = cumulative edge
- IWM 1m+15m: +0.078% per trade — much larger per-trade edge, fewer trades

**Max Drawdown (Max DD)** — The largest peak-to-trough decline in your account during the backtest period. If your account grew from $10,000 to $12,000, then dropped to $10,800 before recovering, the max drawdown was ($12,000 - $10,800) / $12,000 = 10%. Important for understanding worst-case scenarios and psychological tolerance.

**MAE — Maximum Adverse Excursion** — The furthest a trade goes AGAINST you before it either recovers or gets stopped out. If you buy at $200, price drops to $199.50, then rallies to $201 where you take profit, the MAE was $0.50 (or -0.25%). Useful for calibrating stop losses — if most winners have an MAE of -0.10%, setting a stop at -0.15% gives them room to work.

**MFE — Maximum Favorable Excursion** — The furthest a trade goes IN YOUR FAVOR before you exit. If you buy at $200, price rises to $201.50, then you exit at $200.60, the MFE was $1.50 (+0.75%) but you only captured $0.60 of it. Useful for calibrating profit targets — if the MFE is regularly much larger than your target, you might be leaving money on the table.

**Basis Points (bps)** — One basis point = 0.01%. So 30 bps = 0.30%. Used to express small price movements on the underlying. When the backtest shows "+41 bps avg return on target hits," that means the underlying (e.g., IWM) moved 0.41% on average for those winning trades.

**Equity Curve** — A graph showing your account value over time as each trade is taken. A smooth upward equity curve = consistent strategy. A jagged curve = inconsistent. A curve that goes up then dramatically falls = strategy stopped working (possible regime change or overfitting).

---

### Options-Specific Terms

**0DTE — Zero Days to Expiration** — Options that expire on the same day they're traded. These have no time value left (only intrinsic value if in-the-money), which means they're cheaper to buy but decay very fast. High leverage, high risk. IWM, SPY, and QQQ all have 0DTE options available.

**CALL Option** — A contract that gives you the right to buy 100 shares at a specific price (strike) by a specific date (expiration). You buy a CALL when you think price will go UP. If the underlying goes up, the CALL's value increases. If it doesn't move or goes down, you lose what you paid (the premium).

**PUT Option** — A contract that gives you the right to sell 100 shares at a specific price by a specific date. You buy a PUT when you think price will go DOWN. If the underlying drops, the PUT's value increases. If it doesn't move or goes up, you lose the premium.

**Strike Price** — The price at which the option can be exercised. An IWM call with a strike of $200 gives you the right to buy IWM at $200. If IWM is at $203, that option has $3 of intrinsic value.

**ATM — At The Money** — An option whose strike price equals or is very close to the current price. ATM options have the most time value and roughly 50 delta. They cost more than OTM options but have higher probability of profiting.

**OTM — Out of The Money** — A CALL option with a strike above current price, or a PUT option with a strike below current price. OTM options are cheaper but less likely to profit. They provide more leverage (higher % return if the move happens) but lose their entire value more often.

**Delta** — How much the option's price changes for every $1 move in the underlying. ATM options have ~0.50 delta (50 cents per $1 move). OTM options might have 0.20 delta. The backtest measures moves on the underlying — to translate to options, multiply by delta. A +30 bps move on IWM with an ATM option (~5x leverage) ≈ +150 bps on the option.

**Theta (Time Decay)** — How much the option loses in value each day just from time passing. 0DTE options have the highest theta — they're literally racing against the clock. During your 18-minute average hold time, theta is eating into your position. This is why quick trades work better with 0DTE.

**Implied Volatility (IV)** — The market's estimate of how much the stock will move, baked into option prices. Higher IV = more expensive options. Before earnings, IV spikes (everyone expects a big move). After earnings, IV crushes (uncertainty resolved).

**Bid-Ask Spread** — The difference between what buyers are willing to pay (bid) and what sellers are asking (ask). You buy at the ask and sell at the bid, so the spread is an immediate cost. On a liquid ETF like SPY, the spread might be $0.01-0.02. On less liquid strikes, it could be $0.05-0.10. Phase 5F asks whether your backtest "wins" on the underlying are actually profitable after accounting for this cost.

**Gamma** — How much delta changes for each $1 move in the underlying. ATM 0DTE options have extremely high gamma, meaning they accelerate rapidly in your favor (or against you). This is why 0DTE trading is so leveraged — small underlying moves create large option price swings.

**Premium** — The price you pay to buy an option. This is the maximum you can lose on a long (bought) option trade. When you buy a $2.00 call, your max loss is $2.00 per share ($200 per contract).

---

### Market Context & Regime

**Market Regime** — The current overall character of the market. The same trading setup performs very differently depending on the regime:
- *Low Volatility:* VIX below 15, small daily ranges, trends are gentle. Targets may not be reached. Tighter strategies needed.
- *Normal:* VIX 15-25, typical daily ranges. Standard parameters work.
- *High Volatility:* VIX above 25, large daily swings. Wider stops needed, bigger targets possible. Mean reversion works best here.
- *Trending:* Price consistently moves in one direction (EMA 20 > EMA 50 and price above both for uptrend). Trend-following setups dominate.
- *Range-Bound/Choppy:* Price oscillates without clear direction. Mean reversion and ORB range-bound strategies work better.

**VIX — Volatility Index** — Often called the "fear gauge." Measures expected volatility of the S&P 500 over the next 30 days.
- VIX < 15: Calm, complacent market
- VIX 15-20: Normal
- VIX 20-30: Elevated anxiety
- VIX > 30: High fear, potential crisis

**Mean Reversion** — The core strategy philosophy of this system. The idea that price tends to return to an average (like VWAP or an EMA) after moving too far away from it. When IWM drops 3 bars in a row and RSI is oversold, the mean reversion bet is that it bounces back. This works better on IWM (small caps tend to mean-revert more) than QQQ (tech tends to momentum/trend more).

**Contrarian** — Trading against the current direction, betting on a reversal. This system is contrarian: it buys CALLs after drops (expecting a bounce) and buys PUTs after rallies (expecting a pullback). The opposite of trend-following.

**Momentum** — The tendency for price to continue moving in the same direction. QQQ (tech stocks) shows stronger momentum characteristics than IWM. A momentum approach would buy CALLs after UP moves (expecting continuation), which is the opposite of this system's contrarian approach.

**Trend Following** — Trading in the direction of the existing trend. While the core signal is contrarian (buying dips), the FTFC filter and higher-TF trend filter are trend-following components — they ensure you're only buying dips WITHIN an overall uptrend (or selling rallies within a downtrend).

---

### Cross-Ticker & Data Terms

**Ticker** — The shorthand symbol for a tradeable security. This system uses:
- *IWM:* iShares Russell 2000 ETF (small-cap stocks, most volatile, strongest mean reversion edge)
- *SPY:* SPDR S&P 500 ETF (large-cap stocks, most balanced, tightest ranges)
- *QQQ:* Invesco QQQ Trust (Nasdaq-100, tech-heavy, momentum character, hardest to trade)
- *SPX:* S&P 500 Index (reference only, not directly traded)

**ETF — Exchange Traded Fund** — A fund that trades like a stock. IWM, SPY, and QQQ are all ETFs that track their respective indices. You can buy and sell them (and their options) during market hours.

**Parquet** — A file format for storing large datasets efficiently. The system stores historical price data in parquet files. You don't interact with these directly — the scripts read them automatically.

**Pipeline** — The automated sequence of steps that processes raw data into trading signals. In this system: fetch data → calculate indicators → generate signals → run backtests → produce reports. Running `make pipeline` executes all of this end-to-end.

**Sample Size** — The number of trades or occurrences used to calculate a statistic. A win rate based on 10 trades is unreliable. A win rate based on 500 trades is meaningful. Phase 4 sets minimum thresholds: need at least 30 samples for moderate confidence, 100+ for actionable confidence.

**Overfitting / Curve Fitting** — Finding a pattern in historical data that doesn't actually repeat in the future. If you test 10,000 combinations, some will show 90% win rates by random chance alone. Walk-forward validation (Phase 5G) is the cure — it checks whether patterns hold up on data the model hasn't seen before.

**Predictive Lift** — How much an indicator improves your prediction accuracy compared to not having it. If a Strat pattern alone predicts 60% continuation, and adding "RSI > 70" changes that to 40% continuation (meaning 60% reversal), the predictive lift of RSI > 70 for reversal detection is +20 percentage points. Phase 2 ranks all indicators by their predictive lift per ticker.

---

### Risk Management Terms

**Daily Loss Limit** — The maximum you're allowed to lose in a single day before stopping. This system uses -2.0%. If your account drops 2% from where it started the day, you stop trading. No exceptions. Protects against catastrophic days.

**Daily Profit Target** — The gain level at which you stop trading for the day. This system uses +3.0%. Once you're up 3% on the day, you stop. Locks in profits and prevents giving them back.

**Max Daily Trades** — The maximum number of trades allowed per day. This system allows 5. Prevents overtrading, which typically happens after losses (revenge trading) or wins (overconfidence).

**Max Concurrent Positions** — How many trades can be open at the same time. This system allows only 1. You must close your current trade before opening another. Keeps risk contained and focus sharp.

**Risk-Adjusted Return** — Any return metric that accounts for how much risk was taken to achieve it. The Sharpe ratio is the most common. A 50% return that required 50% drawdown risk is worse than a 30% return with only 5% drawdown risk.

**Consecutive Losses / Losing Streak** — Multiple losing trades in a row. Even a 70% win rate system will have streaks of 3-4 consecutive losses regularly, and occasional streaks of 5-7. This is normal and expected. Phase 5E calculates exact streak probabilities per setup per ticker so you know what to expect.

**Recovery Time** — How long it takes your account to get back to its previous high after a drawdown. Important for psychological preparation — knowing "the average recovery from a 5-loss streak takes 12 trades" helps you stay disciplined.