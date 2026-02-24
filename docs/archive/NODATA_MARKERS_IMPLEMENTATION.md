# No-Data Markers Implementation

## Overview

Implemented a marker file system to prevent wasting API calls on dates/months that previously returned "No data" from AlphaVantage API.

## Problem

When fetching AlphaVantage data, some dates return "No data" (e.g., market holidays like 2025-01-01, 2025-01-09, 2025-01-20). On subsequent script re-runs, the scripts would attempt to fetch these dates again, wasting API calls.

Example error log:
```
Fetching IWM options chain for 2025-01-09...
API message: No data for symbol IWM on date 2025-01-09. Please specify a valid combination of symbol and trading day.
```

With only 5 API calls per minute and 500 calls per day, wasting calls on known "no data" dates is inefficient.

## Solution

Created a marker file system that:
1. Checks for actual data file FIRST (priority over marker)
2. If no data file exists, checks for `.nodata` marker file
3. Skips API call if marker file exists (and no data file)
4. Creates marker file when API returns no data (BUT only for trading days)
5. Uses `pandas_market_calendars` to detect holidays and skip marker creation
6. Auto-deletes marker if data file exists (cleanup for edge cases)
7. Logs that date is being skipped

### Holiday Detection

If `pandas_market_calendars` is installed, the scripts will:
- **Intraday**: Check if entire month is non-trading days before creating marker
- **Options**: Automatically skip weekends and market holidays (NYSE calendar)
- **Options**: Only create markers for dates that SHOULD have data

Install holiday detection with:
```bash
pip install pandas_market_calendars
```

If not installed, scripts fall back to basic weekend detection (weekdays only).

## Implementation Details

### Files Modified

1. **[scripts/fetch_alphavantage_intraday.py](scripts/fetch_alphavantage_intraday.py)**
   - Added marker file check before fetching each month
   - Creates `.nodata` marker when API returns no data for a month
   - Skips API call on subsequent runs if marker exists

2. **[scripts/fetch_alphavantage_options.py](scripts/fetch_alphavantage_options.py)**
   - Added marker file check before fetching each date
   - Creates `.nodata` marker when API returns no data for a date
   - Skips API call on subsequent runs if marker exists

### Code Changes

#### Intraday Script (lines 255-293)

**Before:**
```python
for month in months:
    month_file = data_dir / f"{symbol.lower()}_av_{interval}_{month.replace('-', '')}.parquet"

    if month_file.exists():
        # Load cached data
        ...

    # Fetch data from API
    df = fetch_intraday_month(symbol, month, interval=interval)

    if df is not None and not df.empty:
        # Save to parquet
        ...

    api_calls += 1
```

**After:**
```python
for month in months:
    month_file = data_dir / f"{symbol.lower()}_av_{interval}_{month.replace('-', '')}.parquet"
    nodata_marker = data_dir / f"{symbol.lower()}_av_{interval}_{month.replace('-', '')}.nodata"

    # Check for actual data file FIRST (priority over marker)
    if month_file.exists():
        # Load cached data
        df = pd.read_parquet(month_file)
        all_data.append(df)
        # Delete marker file if it exists but we have data (cleanup)
        if nodata_marker.exists():
            nodata_marker.unlink()
        continue

    # Check for "no data" marker file - skip API call if exists AND no data file
    if nodata_marker.exists():
        print(f"  Skipping {month} (previously returned 'No data')")
        continue

    # Fetch data from API
    df = fetch_intraday_month(symbol, month, interval=interval)

    if df is not None and not df.empty:
        # Save to parquet
        ...
    else:
        # Create marker file for months with no data
        nodata_marker.touch()
        print(f"  Created 'no data' marker for {month} (skipped on future runs)")

    api_calls += 1
```

**Key Logic:** Data file check happens BEFORE marker check to ensure existing data is never skipped.

#### Options Script (lines 270-309)

Same pattern applied to options script - checks for `.nodata` markers before fetching each date, creates markers when API returns no data.

## Marker File Naming

### Intraday Data
- **Data file**: `{symbol}_av_{interval}_{YYYYMM}.parquet`
- **Marker file**: `{symbol}_av_{interval}_{YYYYMM}.nodata`
- **Example**: `iwm_av_1min_202501.nodata`

### Options Data
- **Data file**: `{symbol}_av_options_{YYYYMMDD}.parquet`
- **Marker file**: `{symbol}_av_options_{YYYYMMDD}.nodata`
- **Example**: `iwm_av_options_20250109.nodata`

## Benefits

1. **API Call Savings**: Avoids wasting API calls on dates/months with no data
2. **Faster Execution**: Skips unnecessary API calls on re-runs
3. **Rate Limit Protection**: Preserves API quota for fetching actual data
4. **Clear Logging**: Shows which dates are being skipped and why

## Example Usage

### First Run (Creates Markers)
```bash
python scripts/fetch_alphavantage_options.py --symbol IWM --start-date 2025-01-01 --end-date 2025-01-31
```

Output:
```
Fetching IWM options chain for 2025-01-01...
API message: No data for symbol IWM on date 2025-01-01
Created 'no data' marker for 2025-01-01 (skipped on future runs)

Fetching IWM options chain for 2025-01-02...
[Success - data saved]

Fetching IWM options chain for 2025-01-09...
API message: No data for symbol IWM on date 2025-01-09
Created 'no data' marker for 2025-01-09 (skipped on future runs)
```

### Subsequent Run (Skips Markers)
```bash
python scripts/fetch_alphavantage_options.py --symbol IWM --start-date 2025-01-01 --end-date 2025-01-31
```

Output:
```
Skipping 2025-01-01 (previously returned 'No data')
Loading cached data for 2025-01-02...
Skipping 2025-01-09 (previously returned 'No data')
...
```

## Marker File Management

### When to Delete Markers

Delete `.nodata` marker files if:
- AlphaVantage adds historical data for previously unavailable dates
- You suspect the marker is incorrect
- You want to force a re-fetch

### How to Delete Markers

**Windows PowerShell:**
```powershell
# Delete all .nodata markers
Get-ChildItem -Path "data\iwm\*" -Filter "*.nodata" -Recurse | Remove-Item

# Delete specific marker
Remove-Item "data\iwm\intraday\iwm_av_1min_202501.nodata"
```

**Git Bash / Linux:**
```bash
# Delete all .nodata markers
find data/iwm -name "*.nodata" -delete

# Delete specific marker
rm data/iwm/intraday/iwm_av_1min_202501.nodata
```

### .gitignore Handling

The `.nodata` marker files are local cache indicators and should NOT be committed to git. Add to `.gitignore`:

```gitignore
# AlphaVantage no-data markers
*.nodata
```

## Testing

To test the marker system:

1. **Create a test marker manually:**
   ```bash
   # Windows
   type nul > data\iwm\intraday\iwm_av_options_20250101.nodata

   # Linux/Mac
   touch data/iwm/intraday/iwm_av_options_20250101.nodata
   ```

2. **Run the fetch script:**
   ```bash
   python scripts/fetch_alphavantage_options.py --symbol IWM --start-date 2025-01-01 --end-date 2025-01-05
   ```

3. **Verify marker is respected:**
   - Should see: `Skipping 2025-01-01 (previously returned 'No data')`
   - Should NOT make API call for that date

## Technical Notes

- Marker files are empty (0 bytes) - they only need to exist
- Uses `Path.touch()` for cross-platform compatibility
- Marker check happens BEFORE checking for existing data file
- Marker check happens BEFORE making API call
- Combining logic excludes `.nodata` files (glob pattern is `*.parquet`)

## File Locations

### Intraday Markers
- Location: `data/{symbol}/intraday/{symbol}_av_{interval}_{YYYYMM}.nodata`
- Example: `data/iwm/intraday/iwm_av_1min_202501.nodata`

### Options Markers
- Location: `data/{symbol}/options/{symbol}_av_options_{YYYYMMDD}.nodata`
- Example: `data/iwm/options/iwm_av_options_20250109.nodata`

## Integration with Existing Features

The marker system works seamlessly with:
- ✓ Automatic file combining (markers are excluded from glob pattern)
- ✓ Cached data loading (marker check happens before cache check)
- ✓ Rate limiting (skipped dates don't count toward API calls)
- ✓ Progress indicators (skipped dates are logged clearly)

## Summary

This implementation prevents wasting API calls on dates/months that AlphaVantage has confirmed have no data. On the first run, markers are created for "no data" responses. On subsequent runs, these dates are automatically skipped, preserving your API quota for fetching actual data.
