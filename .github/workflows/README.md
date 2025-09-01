# Market Data Fetching GitHub Actions

## Overview
These GitHub Actions automatically fetch and process daily market data for major indices and ETFs (IWM, SPY, QQQ, SPX), calculating comprehensive technical indicators for analysis and trading strategies.

## Workflow Schedule
- **Automatic Execution**: Runs at 5:00 PM EST (10:00 PM UTC) every weekday after market close
- **Manual Trigger**: Can be manually triggered via GitHub Actions UI using `workflow_dispatch`

## Supported Tickers

- **IWM**: iShares Russell 2000 ETF (small-cap index)
- **SPY**: SPDR S&P 500 ETF (large-cap index)
- **QQQ**: Invesco QQQ Trust (Nasdaq-100 technology-focused)
- **SPX**: S&P 500 Index (^GSPC on Yahoo Finance)

## Files and Components

### 1. `.github/workflows/fetch-market-data.yml`
**Purpose**: Unified workflow for fetching all market data
- Fetches all tickers (IWM, SPY, QQQ, SPX) by default
- Supports manual triggering with specific ticker selection
- Runs daily at 5:00 PM EST after market close

**Manual Trigger Options**:
- `ALL` - Fetch all tickers (default)
- Individual tickers: `IWM`, `SPY`, `QQQ`, `SPX`
- Multiple tickers: `SPY QQQ`

### 2. `scripts/fetch_market_data.py`
**Purpose**: Unified data fetching and processing script

**Usage**:
```bash
# Fetch all tickers
python scripts/fetch_market_data.py --tickers ALL

# Fetch specific tickers
python scripts/fetch_market_data.py --tickers SPY QQQ
python scripts/fetch_market_data.py --tickers IWM
```

### 3. `scripts/analyze_market_data.py`
**Purpose**: Analysis script for all market data

**Usage**:
```bash
# Analyze all tickers
python scripts/analyze_market_data.py

# Analyze specific ticker
python scripts/analyze_market_data.py --ticker SPY

# Compare all tickers
python scripts/analyze_market_data.py --compare

# Show correlations
python scripts/analyze_market_data.py --correlations

# Export to CSV
python scripts/analyze_market_data.py --export SPY
```

**Core Functionality of fetch_market_data.py**:
- Fetches minute-level data from Yahoo Finance (last 30 days) for each ticker
- Aggregates minute data into daily OHLCV
- Calculates technical indicators for each ticker
- Saves data in Parquet format for efficient storage
- Generates summary JSON file with latest metrics for each ticker

**Calculated Indicators**:

#### Price-Based Indicators
- **Moving Averages (MA)**: 5, 10, 20, 50-day simple moving averages
- **Exponential Moving Averages (EMA)**: 9, 21, 50-day EMAs
- **Daily Returns**: Percentage change from previous close
- **Intraday Returns**: Open to close percentage change

#### Volume Indicators
- **Volume Moving Averages**: 10 and 20-day averages
- **RVOL (Relative Volume)**: Current volume vs average (20 and 10-day)
- **OBV (On-Balance Volume)**: Cumulative volume flow indicator
- **Volume USD**: Dollar volume traded

#### Momentum Indicators
- **RSI (Relative Strength Index)**: 14 and 9-period RSI
- **Stochastic RSI**: %K and %D lines for overbought/oversold conditions

#### Volatility Indicators
- **ATR (Average True Range)**: 14 and 20-period ATR for volatility measurement
- **Volatility**: 5 and 20-day standard deviation of returns
- **High-Low Spread**: Daily range in points and percentage

## Data Storage Explanation

### How Data is Saved During Fetch

When `fetch_market_data.py` runs, it performs the following data storage operations for each ticker:

1. **Fetches Minute Data**: Downloads last 30 days of minute-level data from Yahoo Finance
2. **Saves Minute Data**: Stores raw minute data in `data/minute/{ticker}_minute_YYYYMMDD.parquet`
3. **Aggregates to Daily**: Calculates true daily OHLCV from minute data
4. **Merges with Existing**: 
   - Loads existing yearly file if it exists (`data/{ticker}_YYYY.parquet`)
   - Merges new data, avoiding duplicates
   - Recalculates all indicators for consistency
5. **Saves Updated Data**: Writes back to `data/{ticker}_YYYY.parquet`
6. **Creates Summary**: Generates `data/{ticker}_summary.json` with latest metrics

### Data Persistence Strategy

- **Yearly Files**: Daily data is organized by year (e.g., `spy_2025.parquet`)
- **Incremental Updates**: New data is merged with existing data, preserving history
- **Deduplication**: Duplicate dates are automatically removed (keeps latest)
- **Indicator Recalculation**: All technical indicators are recalculated on each update to ensure consistency
- **Minute Data Archive**: Raw minute data is preserved for backtesting and detailed analysis

## Output Files

### Data Directory Structure
```
data/
├── iwm_2025.parquet         # IWM daily data with indicators
├── spy_2025.parquet         # SPY daily data with indicators
├── qqq_2025.parquet         # QQQ daily data with indicators
├── spx_2025.parquet         # SPX daily data with indicators
├── iwm_summary.json         # IWM latest metrics
├── spy_summary.json         # SPY latest metrics
├── qqq_summary.json         # QQQ latest metrics
├── spx_summary.json         # SPX latest metrics
└── minute/
    ├── iwm_minute_20250101.parquet  # IWM minute data
    ├── spy_minute_20250101.parquet  # SPY minute data
    ├── qqq_minute_20250101.parquet  # QQQ minute data
    ├── spx_minute_20250101.parquet  # SPX minute data
    └── ...                          # New file created each day
```

### File Formats

#### `{ticker}_YYYY.parquet`
Main data file containing:
- **OHLCV data**: Open, High, Low, Close, Volume
- **All calculated technical indicators**: MAs, EMAs, RSI, RVOL, ATR, etc.
- **Metadata**: ticker, fetch_timestamp, data_source
- **Index**: DateTime index for each trading day
- **Persistence**: Data accumulates throughout the year

#### `{ticker}_summary.json`
Summary file with:
- **Latest price and volume**: Most recent close and volume
- **Current indicator values**: RSI, RVOL, Stoch RSI, OBV, ATR
- **Performance metrics**: YTD return, recent returns
- **Data availability**: First and last date in dataset
- **Last update timestamp**: When data was last fetched

#### `minute/{ticker}_minute_YYYYMMDD.parquet`
Raw minute data containing:
- **1-minute OHLCV bars**: Full trading day minute-by-minute data
- **Timestamp index**: Exact time for each minute bar
- **No indicators**: Raw data only for maximum flexibility
- **Daily files**: New file created each trading day

## Customization Guide

### Modifying the Schedule
Edit `.github/workflows/fetch-market-data.yml`:
```yaml
schedule:
  - cron: 'MIN HOUR * * DAYS'  # Example: '30 16 * * 1-5' for 4:30 PM EST
```

### Adding New Indicators
1. Add calculation function in `scripts/fetch_market_data.py`:
```python
def calculate_new_indicator(data, period):
    # Your calculation logic
    return result
```

2. Add to processing sections (both merge and new data blocks):
```python
combined_df['new_indicator'] = calculate_new_indicator(combined_df['Close'], 20)
```

3. Optionally add to summary:
```python
"latest_new_indicator": float(new_daily_df['new_indicator'].iloc[-1]) if 'new_indicator' in new_daily_df.columns else None,
```

### Adding New Tickers
To add support for additional tickers, modify `scripts/fetch_market_data.py`:

1. Add to the ticker_mappings dictionary:
```python
ticker_mappings = {
    'IWM': ('IWM', None),
    'SPY': ('SPY', None),
    'QQQ': ('QQQ', None),
    'SPX': ('SPX', None),
    'NEW': ('NEW_SYMBOL', 'DISPLAY_NAME'),  # Add your ticker here
}
```

2. Update the argparse choices:
```python
parser.add_argument('--tickers', nargs='+', 
                   choices=['IWM', 'SPY', 'QQQ', 'SPX', 'NEW', 'ALL'],  # Add here
                   ...)
```

### Adjusting Data Retention
- **Minute Data**: Currently keeps all minute data files. Add cleanup logic if needed.
- **Daily Data**: Organized by year. Previous years' data remains unchanged.

## Technical Indicator Explanations

### EMAs (Exponential Moving Averages)
- **EMA 9**: Short-term trend (1-2 weeks)
- **EMA 21**: Medium-term trend (1 month)
- **EMA 50**: Long-term trend (2.5 months)
- Used for trend identification and support/resistance levels

### RSI (Relative Strength Index)
- Range: 0-100
- **> 70**: Potentially overbought
- **< 30**: Potentially oversold
- **RSI 14**: Standard period for daily analysis
- **RSI 9**: More sensitive, shorter-term signals

### Stochastic RSI
- Applies stochastic calculation to RSI values
- **%K**: Fast line (smoothed)
- **%D**: Slow line (signal)
- More sensitive than regular RSI for overbought/oversold

### OBV (On-Balance Volume)
- Cumulative volume indicator
- Rising OBV: Buying pressure
- Falling OBV: Selling pressure
- Divergences with price can signal reversals
- Note: Not calculated for SPX (index has no volume)

### ATR (Average True Range)
- Measures volatility in points
- **ATR 14**: Standard period
- **ATR 20**: Longer-term volatility
- Used for stop-loss placement and position sizing

### RVOL (Relative Volume)
- Current volume / Average volume
- **> 1**: Above average volume
- **< 1**: Below average volume
- High RVOL can indicate significant price moves

## Troubleshooting

### Common Issues

1. **No data fetched**: 
   - Check if market was open (weekdays only)
   - Verify Yahoo Finance API availability
   - Check for holidays

2. **Missing indicators**:
   - Ensure sufficient historical data exists
   - Some indicators need minimum periods (e.g., 50-day MA needs 50 days)

3. **GitHub Action fails**:
   - Check Python dependencies
   - Verify file permissions
   - Review action logs for specific errors

### Data Limitations
- Minute data only available for last 30 days from Yahoo Finance
- Older data uses daily aggregates
- Pre/post market data excluded by default

## Dependencies
- **Python 3.11+**
- **yfinance**: Yahoo Finance data API
- **pandas**: Data manipulation
- **pyarrow**: Parquet file support
- **pytz**: Timezone handling

## Contributing
To add features or fix issues:
1. Test changes locally first
2. Ensure all indicators calculate correctly
3. Verify parquet file compatibility
4. Update this README if adding new features

## License
Included in main repository license.