# Alpha Vantage Data Fetching Scripts

This document describes the Alpha Vantage data fetching scripts for historical intraday and options chain data.

## Overview

Two scripts are provided to fetch data from Alpha Vantage API:

1. **`fetch_alphavantage_intraday.py`** - Fetches 1-minute (or other interval) intraday OHLCV data
2. **`fetch_alphavantage_options.py`** - Fetches historical options chain data with Greeks

## Setup

### 1. Get API Key

1. Visit [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
2. Sign up for a free API key
3. Add your API key to `.env` file:

```bash
ALPHA_VANTAGE_API_KEY=your_actual_api_key_here
```

### 2. Install Dependencies

Dependencies are already in `requirements.txt`:
```bash
pip install -r requirements.txt
```

Required packages:
- `requests` - For API calls
- `pandas` - For data manipulation
- `pyarrow` - For parquet file support
- `python-dotenv` - For environment variables

## Rate Limits

**Free Tier Limits:**
- 5 API calls per minute
- 500 API calls per day

The scripts automatically handle rate limiting with 12-second delays between calls.

## Script 1: Intraday Data (`fetch_alphavantage_intraday.py`)

### Purpose

Fetches high-frequency intraday OHLCV data at 1-minute, 5-minute, 15-minute, 30-minute, or 60-minute intervals.

### Features

- Fetches data month-by-month for efficient chunking
- Automatically caches data in parquet files
- Supports multiple time intervals
- Can fetch up to 20+ years of historical data
- Handles rate limiting automatically
- Creates combined dataset and summary files

### Data Structure

Each month's data includes:
- **timestamp**: DateTime index
- **Open**: Opening price
- **High**: Highest price
- **Low**: Lowest price
- **Close**: Closing price
- **Volume**: Trading volume
- **symbol**: Ticker symbol
- **interval**: Time interval (1min, 5min, etc.)
- **fetch_timestamp**: When data was fetched

### Usage Examples

#### Fetch 5 years of 1-minute data for IWM
```bash
python scripts/fetch_alphavantage_intraday.py --symbol IWM
```

#### Fetch 3 years of 5-minute data for SPY
```bash
python scripts/fetch_alphavantage_intraday.py --symbol SPY --years 3 --interval 5min
```

#### Fetch specific month only
```bash
python scripts/fetch_alphavantage_intraday.py --symbol IWM --month 2025-01
```

#### Fetch different intervals
```bash
# 15-minute bars
python scripts/fetch_alphavantage_intraday.py --symbol QQQ --interval 15min --years 2

# 1-hour bars
python scripts/fetch_alphavantage_intraday.py --symbol SPY --interval 60min --years 1
```

### Output Files

Data is saved in: `data/{symbol}/intraday/`

**Monthly files:**
```
data/iwm/intraday/iwm_av_1min_202501.parquet
data/iwm/intraday/iwm_av_1min_202502.parquet
...
```

**Combined file:**
```
data/iwm/intraday/iwm_av_1min_combined.parquet
```

**Summary file:**
```json
{
  "symbol": "IWM",
  "interval": "1min",
  "start_date": "2020-01-02 09:30:00-05:00",
  "end_date": "2025-11-14 16:00:00-05:00",
  "total_bars": 487520,
  "total_months": 59,
  "latest_close": 237.45,
  "latest_volume": 1234567,
  "last_update": "2025-11-15T10:30:00",
  "file": "data/iwm/intraday/iwm_av_1min_combined.parquet"
}
```

### Command-Line Options

```
--symbol SYMBOL       Stock ticker symbol (required)
--years YEARS         Number of years to fetch (default: 5)
--interval INTERVAL   Time interval: 1min, 5min, 15min, 30min, 60min (default: 1min)
--month MONTH         Fetch specific month only (YYYY-MM format)
```

### Time Estimates

For IWM with 5 years of 1-minute data:
- **Months to fetch**: ~60 months
- **Time per call**: ~12 seconds (rate limiting)
- **Total time**: ~12 minutes
- **API calls used**: 60 calls

## Script 2: Options Chain Data (`fetch_alphavantage_options.py`)

### Purpose

Fetches historical options chain data including all strikes, expirations, bid/ask prices, volume, open interest, and Greeks.

### Features

- Fetches complete options chain for specific dates
- Includes all strikes and expirations available
- Provides Greeks: delta, gamma, theta, vega, rho
- Automatically caches data in parquet files
- Handles rate limiting automatically
- Supports date ranges or lookback periods
- Optional analysis of fetched data

### Data Structure

Each contract includes:
- **contractID**: Unique contract identifier
- **symbol**: Underlying ticker
- **expiration**: Expiration date
- **strike**: Strike price
- **type**: 'call' or 'put'
- **last**: Last trade price
- **mark**: Mid-point between bid/ask
- **bid/ask**: Bid and ask prices
- **bid_size/ask_size**: Sizes at bid/ask
- **volume**: Daily volume
- **open_interest**: Total open contracts
- **date**: Snapshot date
- **implied_volatility**: IV
- **delta, gamma, theta, vega, rho**: Greeks
- **snapshot_date**: Date this data was captured
- **fetch_timestamp**: When data was fetched

### Usage Examples

#### Fetch last 30 days of options data
```bash
python scripts/fetch_alphavantage_options.py --symbol IWM --days 30
```

#### Fetch specific date range
```bash
python scripts/fetch_alphavantage_options.py --symbol SPY \
  --start-date 2025-01-01 \
  --end-date 2025-01-31
```

#### Fetch single day with analysis
```bash
python scripts/fetch_alphavantage_options.py --symbol IWM \
  --date 2025-11-14 \
  --analyze
```

#### Fetch recent week
```bash
python scripts/fetch_alphavantage_options.py --symbol QQQ --days 7 --analyze
```

### Output Files

Data is saved in: `data/{symbol}/options/`

**Daily files:**
```
data/iwm/options/iwm_av_options_20251114.parquet
data/iwm/options/iwm_av_options_20251115.parquet
...
```

**Combined file:**
```
data/iwm/options/iwm_av_options_combined.parquet
```

**Summary file:**
```json
{
  "symbol": "IWM",
  "start_date": "2025-10-15",
  "end_date": "2025-11-14",
  "total_contracts": 45678,
  "total_days": 23,
  "unique_expirations": 12,
  "unique_strikes": 145,
  "calls_count": 22839,
  "puts_count": 22839,
  "last_update": "2025-11-15T10:30:00",
  "file": "data/iwm/options/iwm_av_options_combined.parquet"
}
```

### Command-Line Options

```
--symbol SYMBOL           Stock ticker symbol (required)
--days DAYS              Number of days back from today
--start-date START       Start date (YYYY-MM-DD format)
--end-date END           End date (YYYY-MM-DD format)
--date DATE              Fetch single date only (YYYY-MM-DD format)
--analyze                Show analysis of fetched data
```

### Analysis Output

When using `--analyze`, you'll get:

```json
{
  "symbol": "IWM",
  "total_contracts": 1234,
  "date_range": {
    "start": "2025-11-14",
    "end": "2025-11-14"
  },
  "expiration_range": {
    "nearest": "2025-11-15",
    "farthest": "2026-11-20"
  },
  "strike_range": {
    "min": 180.0,
    "max": 290.0
  },
  "by_type": {
    "calls": 617,
    "puts": 617
  },
  "avg_implied_vol": {
    "calls": 0.32,
    "puts": 0.34
  },
  "total_volume": {
    "calls": 12345,
    "puts": 23456
  },
  "total_open_interest": {
    "calls": 123456,
    "puts": 234567
  }
}
```

### Time Estimates

For 30 days of options data:
- **Trading days**: ~22 days
- **Time per call**: ~12 seconds (rate limiting)
- **Total time**: ~4-5 minutes
- **API calls used**: 22 calls

## Working with the Data

### Loading Parquet Files

```python
import pandas as pd

# Load intraday data
intraday_df = pd.read_parquet('data/iwm/intraday/iwm_av_1min_combined.parquet')

# Load options data
options_df = pd.read_parquet('data/iwm/options/iwm_av_options_combined.parquet')

# Load specific month
jan_2025 = pd.read_parquet('data/iwm/intraday/iwm_av_1min_202501.parquet')
```

### Example Analysis: Intraday Data

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load data
df = pd.read_parquet('data/iwm/intraday/iwm_av_1min_combined.parquet')

# Calculate VWAP
df['vwap'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

# Plot a single day
day_data = df[df.index.date == pd.to_datetime('2025-11-14').date()]
plt.figure(figsize=(14, 6))
plt.plot(day_data.index, day_data['Close'], label='Close')
plt.plot(day_data.index, day_data['vwap'], label='VWAP', alpha=0.7)
plt.legend()
plt.title('IWM Intraday - 2025-11-14')
plt.show()
```

### Example Analysis: Options Data

```python
import pandas as pd

# Load options data
df = pd.read_parquet('data/iwm/options/iwm_av_options_combined.parquet')

# Get latest snapshot
latest = df[df['snapshot_date'] == df['snapshot_date'].max()]

# Analyze near-the-money options
underlying_price = 237.45
atm_calls = latest[
    (latest['type'] == 'call') &
    (abs(latest['strike'] - underlying_price) < 5)
].sort_values('strike')

print("\nATM Call Options:")
print(atm_calls[['strike', 'expiration', 'mark', 'volume', 'open_interest', 'implied_volatility', 'delta']])

# Find highest volume strikes
high_vol = latest.nlargest(10, 'volume')
print("\nHighest Volume Contracts:")
print(high_vol[['strike', 'type', 'expiration', 'volume', 'open_interest']])

# Calculate put/call ratio
total_call_vol = latest[latest['type'] == 'call']['volume'].sum()
total_put_vol = latest[latest['type'] == 'put']['volume'].sum()
put_call_ratio = total_put_vol / total_call_vol
print(f"\nPut/Call Ratio (Volume): {put_call_ratio:.2f}")
```

### Combining Intraday and Options Data

```python
import pandas as pd

# Load both datasets
intraday = pd.read_parquet('data/iwm/intraday/iwm_av_1min_combined.parquet')
options = pd.read_parquet('data/iwm/options/iwm_av_options_combined.parquet')

# Get intraday close at market close (4:00 PM)
daily_closes = intraday.resample('D').last()['Close']

# For each options snapshot, get the underlying price
for date in options['snapshot_date'].dt.date.unique():
    underlying = daily_closes.loc[pd.to_datetime(date)]
    date_options = options[options['snapshot_date'].dt.date == date]

    # Analyze ATM options relative to actual underlying price
    atm_options = date_options[abs(date_options['strike'] - underlying) < 2]

    print(f"\n{date} - Underlying: ${underlying:.2f}")
    print(f"ATM Options: {len(atm_options)} contracts")
```

## Best Practices

### 1. Start Small
Begin with a short date range or specific month to test before fetching years of data:
```bash
# Test with 1 month
python scripts/fetch_alphavantage_intraday.py --symbol IWM --month 2025-01
```

### 2. Monitor API Usage
Track your daily API call count:
- Free tier: 500 calls/day
- 1 month of intraday = 1 call
- 1 day of options = 1 call

### 3. Use Caching
The scripts automatically cache data in parquet files. If you interrupt a fetch:
- Already-fetched months/days won't be re-downloaded
- Just re-run the same command to continue

### 4. Incremental Updates
To update data with new days/months, run the same command:
```bash
# This will only fetch new data, not re-download existing files
python scripts/fetch_alphavantage_intraday.py --symbol IWM --years 5
```

### 5. Storage Considerations
Approximate file sizes:
- 1 month of 1-minute data: ~2-5 MB (compressed parquet)
- 1 day of options data: ~0.5-2 MB (compressed parquet)
- 5 years of 1-minute data: ~150-300 MB
- 30 days of options: ~15-60 MB

## Troubleshooting

### "Rate limit reached"
**Solution**: Script will automatically wait 60 seconds and retry. Be patient.

### "No data found for month/date"
**Possible causes**:
- Weekend/holiday (no trading)
- Date too far back (>20 years for intraday)
- Symbol not available

### "API Error" or "Error Message"
**Check**:
- API key is correct in `.env`
- Symbol is valid
- Date format is correct (YYYY-MM-DD or YYYY-MM)

### Script interrupted
**Solution**: Just re-run it. Cached files won't be re-downloaded.

## Comparison with Existing Yahoo Finance Script

| Feature | Alpha Vantage | Yahoo Finance (yfinance) |
|---------|---------------|--------------------------|
| Intraday intervals | 1, 5, 15, 30, 60 min | 1, 2, 5, 15, 30, 60, 90 min |
| Intraday history | 20+ years | Last 7-60 days |
| Options data | Yes, with Greeks | Yes, but limited history |
| Options history | Any historical date | Current chains only |
| Greeks | Yes (IV, delta, gamma, theta, vega, rho) | Basic IV only |
| Rate limits | 5/min, 500/day | Varies, generally more permissive |
| Cost | Free tier available | Free |
| Data quality | High, from vendor | Good, from Yahoo |

### When to Use Which

**Use Alpha Vantage when:**
- Need historical intraday data beyond 7 days
- Need historical options chains and Greeks
- Require precise Greeks calculations
- Building backtest with historical options data

**Use Yahoo Finance when:**
- Need recent intraday data (last 7 days)
- Want current options chains only
- Need higher rate limits
- Working with daily data

## NYSE Trading Calendar

To get the full list of NYSE trading days, you can:

### Option 1: Use pandas_market_calendars
```python
import pandas_market_calendars as mcal

# Get NYSE calendar
nyse = mcal.get_calendar('NYSE')

# Get trading days for 5 years
schedule = nyse.schedule(start_date='2020-01-01', end_date='2025-11-15')
trading_days = schedule.index

print(f"Total trading days: {len(trading_days)}")
```

### Option 2: Use our fetch script with skip-weekends
The scripts already skip weekends automatically. To also skip holidays, you could:

```python
# Add to either script
from pandas.tseries.holiday import USFederalHolidayCalendar

cal = USFederalHolidayCalendar()
holidays = cal.holidays(start='2020-01-01', end='2025-12-31')

# When generating trading_days, exclude holidays
is_holiday = pd.to_datetime(date) in holidays
if not is_holiday:
    # Fetch data
```

## Additional Resources

- [Alpha Vantage Documentation](https://www.alphavantage.co/documentation/)
- [API Key Registration](https://www.alphavantage.co/support/#api-key)
- [Rate Limit FAQs](https://www.alphavantage.co/support/#support)
- [Parquet File Format](https://arrow.apache.org/docs/python/parquet.html)
