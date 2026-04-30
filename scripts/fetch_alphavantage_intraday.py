#!/usr/bin/env python3
"""
Fetch 1-minute intraday data from Alpha Vantage API for a given symbol.

This script fetches up to 5 years of 1-minute OHLCV data from Alpha Vantage.
Data is fetched month-by-month and stored in parquet files for efficient storage.

API Documentation: https://www.alphavantage.co/documentation/#intraday-extended
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import time
import argparse
import sys
import json
import os
from dotenv import load_dotenv

# Try to import market calendar for holiday detection
try:
    import pandas_market_calendars as mcal
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False
    print("Note: pandas_market_calendars not installed. Install with: pip install pandas_market_calendars")
    print("      Holiday detection will be disabled.\n")

# Load environment variables
load_dotenv()

# Alpha Vantage API configuration — keys loaded from environment only (never hardcoded).
# Set ALPHA_VANTAGE_API_KEY (single) or ALPHA_VANTAGE_API_KEYS (comma-separated) in .env.
from lib.config import AlphaVantageConfig as _AV

_av_cfg = _AV()
ALPHA_VANTAGE_API_KEYS = _av_cfg.get_api_keys()
current_key_index = 0
ALPHA_VANTAGE_API_KEY = ALPHA_VANTAGE_API_KEYS[current_key_index]
BASE_URL = 'https://www.alphavantage.co/query'

# Rate limiting — driven by lib.config.AlphaVantageConfig (currently 150 RPM premium plan).
# Can be overridden at runtime with --delay argument.
CALLS_PER_MINUTE = _av_cfg.rpm
DELAY_BETWEEN_CALLS = _av_cfg.delay_between_calls  # overridden by --delay at runtime


def is_month_all_non_trading_days(month_str):
    """
    Check if an entire month has no trading days (unlikely but possible for future months).

    Args:
        month_str: Month in YYYY-MM format

    Returns:
        True if entire month is non-trading days, False otherwise
    """
    if not CALENDAR_AVAILABLE:
        return False  # Can't determine, assume it has trading days

    try:
        # Parse month
        year, month = map(int, month_str.split('-'))
        # Get first and last day of month
        from calendar import monthrange
        _, last_day = monthrange(year, month)

        start = pd.Timestamp(year, month, 1)
        end = pd.Timestamp(year, month, last_day)

        # Get NYSE calendar (covers most US stocks including ETFs)
        nyse = mcal.get_calendar('NYSE')
        schedule = nyse.schedule(start_date=start, end_date=end)

        # If schedule is empty, no trading days in this month
        return len(schedule) == 0

    except Exception as e:
        # If any error, assume it has trading days
        return False


def get_trading_months(start_date, end_date):
    """
    Generate a list of trading months in YYYY-MM format between start and end dates.

    Args:
        start_date: Start date (datetime or string YYYY-MM-DD)
        end_date: End date (datetime or string YYYY-MM-DD)

    Returns:
        List of strings in YYYY-MM format
    """
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    months = []
    current = start_date.replace(day=1)  # Start from first day of month

    while current <= end_date:
        months.append(current.strftime('%Y-%m'))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months


def switch_api_key():
    """Switch to the next available API key."""
    global current_key_index, ALPHA_VANTAGE_API_KEY

    current_key_index = (current_key_index + 1) % len(ALPHA_VANTAGE_API_KEYS)
    ALPHA_VANTAGE_API_KEY = ALPHA_VANTAGE_API_KEYS[current_key_index]

    print(f"\n  Switching to backup API key #{current_key_index + 1}")
    print(f"  New key: {ALPHA_VANTAGE_API_KEY[:4]}...{ALPHA_VANTAGE_API_KEY[-4:]}")

    return ALPHA_VANTAGE_API_KEY


def fetch_intraday_month(symbol, month, interval='1min', outputsize='full', adjusted=True):
    """
    Fetch 1-minute intraday data for a specific month from Alpha Vantage.

    Args:
        symbol: Stock ticker symbol (e.g., 'IWM')
        month: Month in YYYY-MM format
        interval: Time interval (1min, 5min, 15min, 30min, 60min)
        outputsize: 'compact' (last 100 points) or 'full' (full month)
        adjusted: Whether to adjust for splits/dividends

    Returns:
        DataFrame with OHLCV data or None on failure
    """
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': symbol,
        'interval': interval,
        'month': month,
        'outputsize': outputsize,
        'adjusted': 'true' if adjusted else 'false',
        'entitlement': 'realtime',
        'extended_hours': 'true',
        'apikey': ALPHA_VANTAGE_API_KEY,
        'datatype': 'json'
    }

    try:
        print(f"  Fetching {symbol} data for {month}...")
        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Check for API errors
        if 'Error Message' in data:
            print(f"  API Error: {data['Error Message']}")
            print(f"  Full Response: {json.dumps(data, indent=2)}")
            return None

        if 'Note' in data:
            print(f"  API Note: {data['Note']}")
            print(f"  Full Response: {json.dumps(data, indent=2)}")
            print("  Rate limit reached. Waiting 60 seconds...")
            time.sleep(60)
            return None

        # Check for Information message (usually rate limit warnings)
        if 'Information' in data:
            print(f"  API Information: {data['Information']}")
            print(f"  Full Response: {json.dumps(data, indent=2)}")

            # Try switching to backup key if available
            if current_key_index < len(ALPHA_VANTAGE_API_KEYS) - 1:
                new_key = switch_api_key()
                # Retry with new key
                params['apikey'] = new_key
                print(f"  Retrying with backup key...")
                time.sleep(2)  # Brief pause before retry

                try:
                    response = requests.get(BASE_URL, params=params, timeout=30)
                    response.raise_for_status()
                    data = response.json()

                    # Check if the retry worked
                    if 'Information' not in data and 'Error Message' not in data:
                        time_series_key = f'Time Series ({interval})'
                        if time_series_key in data:
                            print(f"  ✓ Successfully switched to backup key!")
                            # Continue with processing below
                        else:
                            return None
                    else:
                        return None
                except Exception as e:
                    print(f"  Retry with backup key failed: {e}")
                    return None
            else:
                print(f"\n{'='*60}")
                print(f"❌ ALL API KEYS EXHAUSTED")
                print(f"{'='*60}")
                print(f"All {len(ALPHA_VANTAGE_API_KEYS)} API keys have hit their daily rate limits.")
                print(f"Please wait 24 hours before trying again.")
                print(f"Script will now exit.")
                print(f"{'='*60}\n")
                sys.exit(1)  # Exit the entire script

        # Extract time series data
        time_series_key = f'Time Series ({interval})'
        if time_series_key not in data:
            print(f"  No data found for {month}")
            print(f"  API Response: {json.dumps(data, indent=2)}")
            return None

        time_series = data[time_series_key]

        # Convert to DataFrame
        df = pd.DataFrame.from_dict(time_series, orient='index')

        # Rename columns (remove numbering from API response)
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

        # Convert data types
        df['Open'] = pd.to_numeric(df['Open'])
        df['High'] = pd.to_numeric(df['High'])
        df['Low'] = pd.to_numeric(df['Low'])
        df['Close'] = pd.to_numeric(df['Close'])
        df['Volume'] = pd.to_numeric(df['Volume']).astype('int64')

        # Convert index to datetime
        df.index = pd.to_datetime(df.index)
        df.index.name = 'timestamp'

        # Sort by timestamp (oldest first)
        df = df.sort_index()

        print(f"  Fetched {len(df)} bars for {month}")
        return df

    except requests.exceptions.RequestException as e:
        print(f"  Request error for {month}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  JSON decode error for {month}: {e}")
        return None
    except Exception as e:
        print(f"  Unexpected error for {month}: {e}")
        return None


def fetch_historical_intraday(symbol, years=5, interval='1min', start_date=None, end_date=None):
    """
    Fetch historical intraday data for specified number of years.

    Args:
        symbol: Stock ticker symbol
        years: Number of years of history to fetch (default: 5)
        interval: Time interval for bars (default: 1min)
        start_date: Custom start date (string YYYY-MM-DD or datetime)
        end_date: Custom end date (string YYYY-MM-DD or datetime)

    Returns:
        Combined DataFrame with all data
    """
    # Calculate date range
    if start_date and end_date:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years)

    # Get list of months to fetch
    months = get_trading_months(start_date, end_date)

    print(f"\n{'='*60}")
    print(f"Fetching {symbol} {interval} data")
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    print(f"Total months: {len(months)}")
    print(f"{'='*60}\n")

    # Create data directory
    data_dir = Path('data') / symbol.lower() / 'intraday'
    data_dir.mkdir(parents=True, exist_ok=True)

    all_data = []
    api_calls = 0
    start_time = time.time()

    for month in months:
        # Check if file already exists
        month_file = data_dir / f"{symbol.lower()}_av_{interval}_{month.replace('-', '')}.parquet"
        nodata_marker = data_dir / f"{symbol.lower()}_av_{interval}_{month.replace('-', '')}.nodata"

        # Check for actual data file FIRST
        if month_file.exists():
            print(f"  Loading cached data for {month} from {month_file}")
            try:
                df = pd.read_parquet(month_file)
                all_data.append(df)
                # Delete marker file if it exists but we have data (shouldn't happen, but cleanup)
                if nodata_marker.exists():
                    nodata_marker.unlink()
                continue
            except Exception as e:
                print(f"  Error loading cached file: {e}. Re-fetching...")

        # Check for "no data" marker file - skip API call if exists AND no data file
        if nodata_marker.exists():
            print(f"  Skipping {month} (previously returned 'No data')")
            continue

        # Fetch data from API
        df = fetch_intraday_month(symbol, month, interval=interval)

        if df is not None and not df.empty:
            # Add metadata
            df['symbol'] = symbol
            df['interval'] = interval
            df['fetch_timestamp'] = datetime.now()

            # Save to parquet
            df.to_parquet(month_file, compression='snappy', index=True)
            print(f"  Saved to {month_file}")

            all_data.append(df)
        else:
            # Only create marker if this month should have trading days
            # Don't create markers for months that are entirely holidays/weekends
            if is_month_all_non_trading_days(month):
                print(f"  No data for {month} (entire month is non-trading days - no marker created)")
            else:
                # Create marker file for months with no data to avoid wasting API calls on re-runs
                nodata_marker.touch()
                print(f"  Created 'no data' marker for {month} (skipped on future runs)")

        api_calls += 1

        # Rate limiting
        elapsed = time.time() - start_time
        if api_calls % CALLS_PER_MINUTE == 0:
            sleep_time = max(0, 60 - elapsed)
            if sleep_time > 0:
                print(f"\n  Rate limit: Waiting {sleep_time:.1f} seconds...\n")
                time.sleep(sleep_time)
            start_time = time.time()
        else:
            time.sleep(DELAY_BETWEEN_CALLS)

    # ALWAYS combine ALL monthly files (not just the ones fetched in this run)
    # This ensures the combined file is always complete and up-to-date
    print(f"\n{'='*60}")
    print("Combining ALL monthly parquet files...")
    print(f"{'='*60}\n")

    # Find all monthly parquet files
    import glob as glob_module
    pattern = str(data_dir / f"{symbol.lower()}_av_{interval}_*.parquet")
    all_monthly_files = glob_module.glob(pattern)
    # Exclude the combined file itself
    all_monthly_files = [f for f in all_monthly_files if 'combined' not in f]
    all_monthly_files = sorted(all_monthly_files)

    if not all_monthly_files:
        print("No monthly files found to combine.")
        return None

    # Load ALL monthly files
    all_monthly_data = []
    for i, file_path in enumerate(all_monthly_files, 1):
        file_name = Path(file_path).name
        try:
            df = pd.read_parquet(file_path)
            all_monthly_data.append(df)
            if i % 10 == 0:
                print(f"  Loaded {i}/{len(all_monthly_files)} monthly files...")
        except Exception as e:
            print(f"  Warning: Could not load {file_name}: {e}")
            continue

    if not all_monthly_data:
        print("ERROR: No data could be loaded from monthly files!")
        return None

    print(f"  Loaded {len(all_monthly_data)}/{len(all_monthly_files)} monthly files")

    # Combine all monthly data
    combined_df = pd.concat(all_monthly_data, ignore_index=False)
    combined_df = combined_df.sort_index()

    # Remove duplicates (keep first occurrence)
    original_len = len(combined_df)
    combined_df = combined_df[~combined_df.index.duplicated(keep='first')]
    duplicates_removed = original_len - len(combined_df)

    if duplicates_removed > 0:
        print(f"  Removed {duplicates_removed:,} duplicate timestamps")

    # Save combined data (overwrites previous combined file)
    combined_file = data_dir / f"{symbol.lower()}_av_{interval}_combined.parquet"
    combined_df.to_parquet(combined_file, compression='snappy', index=True)

    # Count unique months
    combined_df_temp = combined_df.reset_index()
    combined_df_temp['month'] = pd.to_datetime(combined_df_temp['timestamp']).dt.to_period('M')
    unique_months = combined_df_temp['month'].nunique()

    # Create summary
    summary = {
        'symbol': symbol,
        'interval': interval,
        'start_date': str(combined_df.index.min()),
        'end_date': str(combined_df.index.max()),
        'total_bars': len(combined_df),
        'total_months': unique_months,
        'monthly_files_combined': len(all_monthly_files),
        'duplicates_removed': duplicates_removed,
        'latest_close': float(combined_df['Close'].iloc[-1]),
        'latest_volume': int(combined_df['Volume'].iloc[-1]),
        'last_update': datetime.now().isoformat(),
        'file': str(combined_file)
    }

    summary_file = data_dir / f"{symbol.lower()}_av_{interval}_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print("COMBINED FILE SUMMARY")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}")
    print(f"Monthly files combined: {len(all_monthly_files)}")
    print(f"Unique months: {unique_months}")
    print(f"Total bars: {len(combined_df):,}")
    print(f"Duplicates removed: {duplicates_removed:,}")
    print(f"Date range: {summary['start_date']} to {summary['end_date']}")
    print(f"Latest close: ${summary['latest_close']:.2f}")
    print(f"\nFiles created/updated:")
    print(f"  {combined_file}")
    print(f"  {summary_file}")
    print(f"{'='*60}\n")

    return combined_df


def show_parquet_data(symbol, interval='1min', rows=100):
    """
    Load and display parquet data for a given symbol.

    Args:
        symbol: Stock ticker symbol
        interval: Time interval (default: 1min)
        rows: Number of rows to display (default: 100)
    """
    data_dir = Path('data') / symbol.lower() / 'intraday'
    combined_file = data_dir / f"{symbol.lower()}_av_{interval}_combined.parquet"
    summary_file = data_dir / f"{symbol.lower()}_av_{interval}_summary.json"

    if not combined_file.exists():
        print(f"\nERROR: Combined file not found: {combined_file}")
        print(f"Please fetch data first using:")
        print(f"  python scripts/fetch_alphavantage_intraday.py --symbol {symbol} --interval {interval}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Loading: {combined_file}")
    print(f"{'='*60}\n")

    # Load data
    df = pd.read_parquet(combined_file)

    # Show summary if available
    if summary_file.exists():
        with open(summary_file, 'r') as f:
            summary = json.load(f)
        print("Summary:")
        print(f"  Symbol: {summary.get('symbol', 'N/A')}")
        print(f"  Interval: {summary.get('interval', 'N/A')}")
        print(f"  Date Range: {summary.get('start_date', 'N/A')} to {summary.get('end_date', 'N/A')}")
        print(f"  Total Bars: {summary.get('total_bars', 'N/A'):,}")
        print(f"  Latest Close: ${summary.get('latest_close', 0):.2f}")
        print(f"  Last Update: {summary.get('last_update', 'N/A')}")
        print()

    # Show dataframe info
    print(f"DataFrame Info:")
    print(f"  Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print(f"  Columns: {', '.join(df.columns.tolist())}")
    print(f"  Index: {df.index.name} ({df.index.dtype})")
    print(f"  Memory: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    print()

    # Show first N rows
    display_rows = min(rows, len(df))
    print(f"First {display_rows} rows:")
    print(f"{'-'*60}")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 20)
    print(df.head(display_rows))
    print(f"{'-'*60}\n")

    # Show last 5 rows for context
    print(f"Last 5 rows:")
    print(f"{'-'*60}")
    print(df.tail(5))
    print(f"{'-'*60}\n")


def main():
    """Main function to fetch Alpha Vantage intraday data."""
    parser = argparse.ArgumentParser(
        description='Fetch intraday data from Alpha Vantage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch 5 years of 1-minute data for IWM
  python fetch_alphavantage_intraday.py --symbol IWM

  # Fetch 3 years of 5-minute data for SPY
  python fetch_alphavantage_intraday.py --symbol SPY --years 3 --interval 5min

  # Fetch specific month
  python fetch_alphavantage_intraday.py --symbol IWM --month 2025-01

  # Show existing data
  python fetch_alphavantage_intraday.py --symbol IWM --show
  python fetch_alphavantage_intraday.py --symbol IWM --show --rows 200
        """
    )

    parser.add_argument('--symbol', type=str, required=True,
                       help='Stock ticker symbol (e.g., IWM, SPY)')
    parser.add_argument('--years', type=int, default=5,
                       help='Number of years of history to fetch (default: 5)')
    parser.add_argument('--interval', type=str, default='1min',
                       choices=['1min', '5min', '15min', '30min', '60min'],
                       help='Time interval for bars (default: 1min)')
    parser.add_argument('--month', type=str,
                       help='Fetch specific month only (YYYY-MM format)')
    parser.add_argument('--start-date', type=str,
                       help='Custom start date (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                       help='Custom end date (YYYY-MM-DD format)')
    parser.add_argument('--show', action='store_true',
                       help='Display existing parquet data instead of fetching')
    parser.add_argument('--rows', type=int, default=100,
                       help='Number of rows to display when using --show (default: 100)')
    parser.add_argument('--delay', type=float, default=None,
                       help='Seconds between API calls (default: 12 for free tier, use 1 for premium plans)')

    args = parser.parse_args()

    # Override rate limiting if --delay provided (premium keys support much higher RPM)
    if args.delay is not None:
        global DELAY_BETWEEN_CALLS, CALLS_PER_MINUTE
        DELAY_BETWEEN_CALLS = args.delay
        # Set CALLS_PER_MINUTE high enough that the 60s batch-wait never triggers
        CALLS_PER_MINUTE = max(60, int(60 / args.delay)) if args.delay > 0 else 150

    # If --show flag is set, display data and exit
    if args.show:
        show_parquet_data(args.symbol, args.interval, args.rows)
        return

    # Validate API key
    if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == 'your_alpha_vantage_api_key_here':
        print("ERROR: ALPHA_VANTAGE_API_KEY not set in .env file")
        print("Please add your API key to .env file:")
        print("  ALPHA_VANTAGE_API_KEY=your_key_here")
        sys.exit(1)

    try:
        if args.month:
            # Fetch single month
            print(f"\nFetching {args.symbol} {args.interval} data for {args.month}")
            df = fetch_intraday_month(args.symbol, args.month, interval=args.interval)

            if df is not None:
                # Save to file
                data_dir = Path('data') / args.symbol.lower() / 'intraday'
                data_dir.mkdir(parents=True, exist_ok=True)

                month_file = data_dir / f"{args.symbol.lower()}_av_{args.interval}_{args.month.replace('-', '')}.parquet"
                df['symbol'] = args.symbol
                df['interval'] = args.interval
                df['fetch_timestamp'] = datetime.now()
                df.to_parquet(month_file, compression='snappy', index=True)

                print(f"\nSaved {len(df)} bars to {month_file}")
        else:
            # Fetch full history
            df = fetch_historical_intraday(
                args.symbol,
                years=args.years,
                interval=args.interval,
                start_date=args.start_date,
                end_date=args.end_date
            )

            if df is None:
                sys.exit(1)

        print("\nFetch completed successfully!")

    except KeyboardInterrupt:
        print("\n\nFetch interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
