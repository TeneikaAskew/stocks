# IWM Historical Data Storage

This directory contains historical daily data for IWM (iShares Russell 2000 ETF) fetched from Yahoo Finance.

## Data Format

Data is stored in **Parquet format** for optimal performance:
- **Efficient compression**: ~70% smaller than CSV
- **Fast queries**: Columnar storage allows for selective column reading
- **Type preservation**: Maintains data types without parsing overhead
- **Partitioned by year**: Each year's data is stored in a separate file (e.g., `iwm_2024.parquet`)

## File Structure

- `iwm_YYYY.parquet`: Daily OHLCV data for year YYYY
- `iwm_summary.json`: Latest update metadata and statistics

## Data Columns

Each Parquet file contains:
- **OHLCV Data**: Open, High, Low, Close, Volume
- **Calculated Metrics**:
  - `daily_return`: Daily percentage return
  - `volume_usd`: Dollar volume (Volume × Close)
  - `high_low_spread`: Daily range (High - Low)
  - `high_low_spread_pct`: Daily range as percentage
  - `ma_5`, `ma_10`, `ma_20`, `ma_50`: Moving averages
  - `volume_ma_10`: 10-day volume moving average
  - `volatility_5d`, `volatility_20d`: Rolling volatility
- **Metadata**:
  - `ticker`: Always "IWM"
  - `fetch_timestamp`: When the data was fetched

## Usage

### Python
```python
import pandas as pd

# Load current year's data
df = pd.read_parquet('data/iwm_2024.parquet')

# Load all historical data
from pathlib import Path
all_data = pd.concat([
    pd.read_parquet(f) 
    for f in Path('data').glob('iwm_*.parquet')
])
```

### Analysis Script
```bash
python scripts/analyze_iwm_data.py
```

## Update Schedule

Data is automatically updated via GitHub Actions:
- **Schedule**: Every weekday at 5:00 PM EST (after market close)
- **Manual trigger**: Available via GitHub Actions UI

## Storage Efficiency

Parquet provides excellent compression:
- 1 year of daily data: ~50-100 KB
- 10 years of daily data: ~500 KB - 1 MB
- Query single column from 10 years: <100ms