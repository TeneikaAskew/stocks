# AlphaVantage Data Integration Analysis

## Data Format Comparison

### AlphaVantage Intraday Data (Parquet)
**Source**: `data/iwm/intraday/iwm_av_1min_combined.parquet`

```python
Columns: ['Open', 'High', 'Low', 'Close', 'Volume', 'symbol', 'interval', 'fetch_timestamp']
Index: 'timestamp' (DatetimeIndex)

Sample Data:
                         Open      High       Low     Close  Volume symbol interval
timestamp
2020-01-02 04:00:00  155.1258  155.1258  155.1258  155.1258    1000    IWM     1min
2020-01-02 05:14:00  155.2467  155.2467  155.2467  155.2467     500    IWM     1min
```

### IWM Analysis Expected Format (CSV)
**Source**: `data/stock_prices/*.csv`

```python
Columns: ['Time', 'Open', 'High', 'Low', 'Last', 'Change', '%Chg', 'Volume']

Sample Data:
               Time    Open    High     Low    Last  Change    %Chg  Volume
2025-07-02 19:59  221.47  221.49  221.47  221.49   -0.02  -0.01%    1005
2025-07-02 19:58  221.51  221.51  221.51  221.51    0.00   0.00%     498
```

## Key Differences

| Aspect | AlphaVantage | IWM Analysis CSV | Required Change |
|--------|-------------|------------------|-----------------|
| **Time Column** | `timestamp` (index) | `Time` (column) | Reset index, rename |
| **Close Column** | `Close` | `Last` | Rename `Close` → `Last` |
| **Extra Columns** | `symbol`, `interval`, `fetch_timestamp` | Not present | Can keep or drop |
| **Missing Columns** | - | `Change`, `%Chg` | Calculate from price data |
| **Data Types** | Float (all prices) | Float (prices), String (%Chg) | Convert %Chg format |

## Required Transformations

### 1. Column Mapping
```python
# AlphaVantage → IWM Analysis
'timestamp' (index) → 'Time' (column)
'Close' → 'Last'
'Open' → 'Open' (same)
'High' → 'High' (same)
'Low' → 'Low' (same)
'Volume' → 'Volume' (same)
```

### 2. Calculate Missing Columns
```python
# Change (dollar change from previous close)
df['Change'] = df['Last'].diff()

# %Chg (percentage change formatted as string)
df['%Chg'] = (df['Last'].pct_change() * 100).apply(lambda x: f'{x:.2f}%')
```

### 3. Handle Extra Columns
```python
# Option 1: Drop metadata columns
df = df.drop(['symbol', 'interval', 'fetch_timestamp'], axis=1)

# Option 2: Keep for reference (iwm_analysis.py will ignore them)
# No action needed - extra columns are ignored by analysis
```

## Implementation Options

### Option 1: Create Conversion Script (Recommended)
Create `convert_alphavantage_to_csv.py` to convert AlphaVantage data to IWM Analysis format.

**Pros**:
- Clean separation of concerns
- Can be run independently
- Easy to verify conversion
- Keeps original data intact

**Cons**:
- Extra step in workflow
- Duplicate data storage

### Option 2: Modify IWM Analysis to Accept Both Formats
Update `iwm_analysis.py` to detect and handle AlphaVantage format.

**Pros**:
- No conversion step needed
- Direct analysis from AlphaVantage data
- Single workflow

**Cons**:
- More complex analysis code
- Need to maintain two input paths

### Option 3: Hybrid Approach
Modify `combine_csv_files()` method to handle both CSV and Parquet formats.

**Pros**:
- Flexible input sources
- Automatic format detection
- Best of both worlds

**Cons**:
- Medium complexity
- Need to test both paths

## Recommended Solution: Option 1 (Conversion Script)

Create a simple conversion script that transforms AlphaVantage Parquet to CSV format compatible with IWM Analysis.

### Conversion Script Template

```python
#!/usr/bin/env python3
"""
Convert AlphaVantage Parquet data to IWM Analysis CSV format.
"""

import pandas as pd
from pathlib import Path

def convert_alphavantage_to_csv(symbol='IWM', interval='1min'):
    """
    Convert AlphaVantage parquet data to IWM Analysis CSV format.

    Args:
        symbol: Stock ticker (default: IWM)
        interval: Time interval (default: 1min)
    """
    # Load AlphaVantage data
    av_file = Path(f'data/{symbol.lower()}/intraday/{symbol.lower()}_av_{interval}_combined.parquet')

    if not av_file.exists():
        print(f"Error: AlphaVantage data not found at {av_file}")
        return None

    print(f"Loading AlphaVantage data from {av_file}...")
    df = pd.read_parquet(av_file)

    print(f"Loaded {len(df):,} rows")
    print(f"Date range: {df.index.min()} to {df.index.max()}")

    # Transform to IWM Analysis format
    print("\nTransforming data...")

    # Reset index to make timestamp a column
    df = df.reset_index()

    # Rename columns
    df = df.rename(columns={
        'timestamp': 'Time',
        'Close': 'Last'
    })

    # Calculate Change and %Chg
    df['Change'] = df['Last'].diff()
    df['%Chg'] = df['Last'].pct_change() * 100
    df['%Chg'] = df['%Chg'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else '0.00%')

    # Set first row Change and %Chg to 0
    df.loc[0, 'Change'] = 0.0
    df.loc[0, '%Chg'] = '0.00%'

    # Select columns in IWM Analysis order
    columns = ['Time', 'Open', 'High', 'Low', 'Last', 'Change', '%Chg', 'Volume']
    df = df[columns]

    # Sort by time
    df = df.sort_values('Time')

    # Save to CSV
    output_dir = Path('data/stock_prices')
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f'{symbol}_av_{interval}_converted.csv'
    df.to_csv(output_file, index=False)

    print(f"\nConverted data saved to {output_file}")
    print(f"Total rows: {len(df):,}")
    print(f"Date range: {df['Time'].min()} to {df['Time'].max()}")

    return df

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert AlphaVantage data to IWM Analysis format')
    parser.add_argument('--symbol', default='IWM', help='Stock symbol (default: IWM)')
    parser.add_argument('--interval', default='1min', help='Time interval (default: 1min)')

    args = parser.parse_args()

    convert_alphavantage_to_csv(args.symbol, args.interval)
```

### Usage

```bash
# Convert IWM 1-minute data
python convert_alphavantage_to_csv.py

# Convert SPY 5-minute data
python convert_alphavantage_to_csv.py --symbol SPY --interval 5min

# Then run IWM analysis as normal
python iwm_analysis.py
```

## Alternative: Direct Integration into IWM Analysis

If you prefer to modify `iwm_analysis.py` directly, here are the changes needed:

### Modify `combine_csv_files()` Method

```python
def combine_csv_files(self, folder_path: str, output_path: str,
                     use_alphavantage: bool = False,
                     av_symbol: str = 'IWM',
                     av_interval: str = '1min') -> pd.DataFrame:
    """Combine CSV files OR load AlphaVantage parquet data"""

    if use_alphavantage:
        print("Loading AlphaVantage data...")

        # Load parquet
        av_file = Path(f'data/{av_symbol.lower()}/intraday/{av_symbol.lower()}_av_{av_interval}_combined.parquet')
        df = pd.read_parquet(av_file)

        # Transform to expected format
        df = df.reset_index()
        df = df.rename(columns={'timestamp': 'Time', 'Close': 'Last'})

        # Calculate Change and %Chg
        df['Change'] = df['Last'].diff().fillna(0)
        df['%Chg'] = df['Last'].pct_change() * 100
        df['%Chg'] = df['%Chg'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else '0.00%')

        # Select columns
        df = df[['Time', 'Open', 'High', 'Low', 'Last', 'Change', '%Chg', 'Volume']]

    else:
        # Original CSV loading code
        # ... (keep existing code)

    # Rest of the method continues as before
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.sort_values('Time')
    # ...
```

### Add Command Line Argument

```python
def main():
    parser = argparse.ArgumentParser(description='Analyze IWM historical data')
    parser.add_argument('-months', type=int, default=2)
    parser.add_argument('-all', action='store_true')
    parser.add_argument('--alphavantage', action='store_true',
                       help='Use AlphaVantage parquet data instead of CSV')
    parser.add_argument('--av-symbol', default='IWM',
                       help='AlphaVantage symbol (default: IWM)')
    parser.add_argument('--av-interval', default='1min',
                       help='AlphaVantage interval (default: 1min)')

    args = parser.parse_args()

    # Pass to analyzer
    if args.alphavantage:
        analyzer.combine_csv_files(
            input_folder, output_file,
            use_alphavantage=True,
            av_symbol=args.av_symbol,
            av_interval=args.av_interval
        )
```

### Usage with Direct Integration

```bash
# Use AlphaVantage data
python iwm_analysis.py --alphavantage

# Use AlphaVantage with different symbol
python iwm_analysis.py --alphavantage --av-symbol SPY --av-interval 5min

# Use CSV as before (no flags)
python iwm_analysis.py
```

## Data Considerations

### AlphaVantage Data Advantages
1. **Clean data**: No "Downloaded from" footer rows
2. **Consistent format**: Parquet is more reliable
3. **Historical depth**: Up to 5 years of 1-minute data
4. **Metadata**: Includes symbol, interval, fetch timestamp

### Potential Issues
1. **Missing %Chg column**: Needs calculation (trivial)
2. **Index vs Column**: Timestamp is index in AV, column in CSV
3. **Extended hours**: AV includes pre/post market (4am-8pm)
4. **Column naming**: 'Close' vs 'Last'

### Extended Hours Handling

AlphaVantage data includes extended hours (4am-8pm). You may want to filter:

```python
# Filter to regular market hours only (9:30am - 4:00pm)
df['Time'] = pd.to_datetime(df['Time'])
df['Hour'] = df['Time'].dt.hour
df['Minute'] = df['Time'].dt.minute

# Regular market hours: 9:30 AM - 4:00 PM
regular_hours = (
    ((df['Hour'] == 9) & (df['Minute'] >= 30)) |
    ((df['Hour'] >= 10) & (df['Hour'] < 16)) |
    ((df['Hour'] == 16) & (df['Minute'] == 0))
)

df = df[regular_hours]
df = df.drop(['Hour', 'Minute'], axis=1)
```

## Testing Checklist

Before running full analysis with AlphaVantage data:

- [ ] Convert sample month of data
- [ ] Verify column names match
- [ ] Check Time column is datetime
- [ ] Validate Change calculation
- [ ] Verify %Chg formatting
- [ ] Test with iwm_analysis.py (small dataset)
- [ ] Compare results with CSV-based analysis
- [ ] Check ORB calculations work (need market hours)
- [ ] Verify Historical Levels calculate correctly
- [ ] Test Order Block detection

## Recommendation

**Best Approach**: Create the conversion script (Option 1)

### Why?
1. **Simplest**: Least code changes
2. **Safest**: Keeps IWM analysis unchanged
3. **Testable**: Easy to verify conversion
4. **Flexible**: Can convert different intervals/symbols
5. **Reusable**: One-time conversion, multiple analyses

### Workflow

```bash
# 1. Fetch AlphaVantage data (if not already done)
python scripts/fetch_alphavantage_intraday.py --symbol IWM --years 5

# 2. Convert to CSV format
python convert_alphavantage_to_csv.py --symbol IWM

# 3. Run analysis as normal
python iwm_analysis.py -all

# Or combine steps in a script
```

## Next Steps

1. Create `convert_alphavantage_to_csv.py` script
2. Test conversion with one month of data
3. Verify output matches expected CSV format
4. Run iwm_analysis.py on converted data
5. Compare results with original CSV data
6. Document any differences found

## Summary

**Minimal Changes Required**:
- Rename `Close` → `Last`
- Move `timestamp` index to `Time` column
- Calculate `Change` and `%Chg` columns
- Optionally filter to market hours

**No Changes Needed**:
- OHLCV data is identical
- Timestamps are compatible
- Volume data matches
- All technical indicators will work

The AlphaVantage data is **fully compatible** with the IWM analysis pipeline after simple column transformations!
