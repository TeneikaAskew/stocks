# Alpha Vantage Quick Start Guide

## Setup (One-time)

1. **Get API Key**: Visit https://www.alphavantage.co/support/#api-key
2. **Add to .env file**:
   ```
   ALPHA_VANTAGE_API_KEY=your_actual_key_here
   ```

## Quick Commands

### Intraday Data

```bash
# Fetch 5 years of 1-minute IWM data (default)
python scripts/fetch_alphavantage_intraday.py --symbol IWM

# Fetch 1 specific month to test
python scripts/fetch_alphavantage_intraday.py --symbol IWM --month 2025-11

# Fetch 5-minute bars for last 2 years
python scripts/fetch_alphavantage_intraday.py --symbol SPY --years 2 --interval 5min

# Show existing data (no API calls)
python scripts/fetch_alphavantage_intraday.py --symbol IWM --show
python scripts/fetch_alphavantage_intraday.py --symbol IWM --show --rows 200
```

### Options Chain Data

```bash
# Fetch last 7 days of options data
python scripts/fetch_alphavantage_options.py --symbol IWM --days 7

# Fetch single day with analysis
python scripts/fetch_alphavantage_options.py --symbol IWM --date 2025-11-14 --analyze

# Fetch specific date range
python scripts/fetch_alphavantage_options.py --symbol SPY --start-date 2025-01-01 --end-date 2025-01-31

# Show existing data (no API calls)
python scripts/fetch_alphavantage_options.py --symbol IWM --show
python scripts/fetch_alphavantage_options.py --symbol IWM --show --rows 200
```

## Output Locations

All data saved in `data/{symbol}/` directory:

```
data/
  iwm/
    intraday/
      iwm_av_1min_202501.parquet        # Monthly files
      iwm_av_1min_202502.parquet
      iwm_av_1min_combined.parquet      # All data combined
      iwm_av_1min_summary.json          # Metadata
    options/
      iwm_av_options_20251114.parquet   # Daily files
      iwm_av_options_20251115.parquet
      iwm_av_options_combined.parquet   # All data combined
      iwm_av_options_summary.json       # Metadata
```

## Loading Data in Python

```python
import pandas as pd

# Load intraday data
intraday_df = pd.read_parquet('data/iwm/intraday/iwm_av_1min_combined.parquet')

# Load options data
options_df = pd.read_parquet('data/iwm/options/iwm_av_options_combined.parquet')

# View summary
import json
with open('data/iwm/intraday/iwm_av_1min_summary.json') as f:
    print(json.dumps(json.load(f), indent=2))
```

## Important Notes

- **Rate Limits**: Free tier = 5 calls/min, 500 calls/day
- **Auto-caching**: Re-running won't re-download existing data
- **Time estimates**:
  - 1 month intraday = 12 seconds
  - 1 year intraday = ~2.5 minutes
  - 5 years intraday = ~12 minutes
  - 30 days options = ~4.5 minutes

## Recommended Workflow

1. **Test with small dataset first**:
   ```bash
   python scripts/fetch_alphavantage_intraday.py --symbol IWM --month 2025-11
   ```

2. **Verify data loaded correctly**:
   ```python
   import pandas as pd
   df = pd.read_parquet('data/iwm/intraday/iwm_av_1min_202511.parquet')
   print(df.head())
   print(df.info())
   ```

3. **Fetch full dataset**:
   ```bash
   python scripts/fetch_alphavantage_intraday.py --symbol IWM --years 5
   ```

4. **Repeat for other symbols** (SPY, QQQ, etc.)

## Full Documentation

See [docs/alpha-vantage-data-fetching.md](./alpha-vantage-data-fetching.md) for complete documentation including:
- Detailed usage examples
- Data structure reference
- Analysis examples
- Troubleshooting guide
- Comparison with Yahoo Finance
