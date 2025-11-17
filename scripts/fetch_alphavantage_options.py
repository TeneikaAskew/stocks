#!/usr/bin/env python3
"""
Fetch historical options chain data from Alpha Vantage API for a given symbol.

This script fetches options chain data including Greeks (delta, gamma, theta, vega, rho)
for all available strikes and expirations on specific dates.

API Documentation: https://www.alphavantage.co/documentation/#options
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

# Load environment variables
load_dotenv()

# Alpha Vantage API configuration - Multiple keys for failover
ALPHA_VANTAGE_API_KEYS = [
    os.getenv('ALPHA_VANTAGE_API_KEY', 'KKYWD9FJ9VITR3F5'),  # Primary key
    'PWXSRHD4ZXX8S1HI',   # Backup key 1
    'VNMXDQ9LBOJ5X2I6',   # Backup key 2
    '7E8X3MQLLSW5HPWF',   # Backup key 3
    'VFIN9SZWRAI1SCGW'    # Backup key 4
]
current_key_index = 0
ALPHA_VANTAGE_API_KEY = ALPHA_VANTAGE_API_KEYS[current_key_index]
BASE_URL = 'https://www.alphavantage.co/query'

# Rate limiting: Alpha Vantage free tier allows 5 API calls/minute, 500/day
CALLS_PER_MINUTE = 5
DELAY_BETWEEN_CALLS = 60 / CALLS_PER_MINUTE  # 12 seconds


def get_trading_days(start_date, end_date, skip_weekends=True):
    """
    Generate a list of trading days between start and end dates.

    Args:
        start_date: Start date (datetime or string YYYY-MM-DD)
        end_date: End date (datetime or string YYYY-MM-DD)
        skip_weekends: Whether to skip Saturday and Sunday

    Returns:
        List of datetime.date objects
    """
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    days = []
    current = start_date

    while current <= end_date:
        # Skip weekends if requested
        if skip_weekends and current.weekday() >= 5:  # Saturday=5, Sunday=6
            current += timedelta(days=1)
            continue

        days.append(current)
        current += timedelta(days=1)

    return days


def switch_api_key():
    """Switch to the next available API key."""
    global current_key_index, ALPHA_VANTAGE_API_KEY

    current_key_index = (current_key_index + 1) % len(ALPHA_VANTAGE_API_KEYS)
    ALPHA_VANTAGE_API_KEY = ALPHA_VANTAGE_API_KEYS[current_key_index]

    print(f"\n  Switching to backup API key #{current_key_index + 1}")
    print(f"  New key: {ALPHA_VANTAGE_API_KEY[:4]}...{ALPHA_VANTAGE_API_KEY[-4:]}")

    return ALPHA_VANTAGE_API_KEY


def fetch_options_chain(symbol, date):
    """
    Fetch options chain data for a specific date from Alpha Vantage.

    Args:
        symbol: Stock ticker symbol (e.g., 'IWM')
        date: Date in YYYY-MM-DD format or datetime.date object

    Returns:
        DataFrame with options chain data or None on failure
    """
    if isinstance(date, datetime):
        date = date.date()
    if hasattr(date, 'strftime'):
        date_str = date.strftime('%Y-%m-%d')
    else:
        date_str = str(date)

    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol': symbol,
        'date': date_str,
        'apikey': ALPHA_VANTAGE_API_KEY
    }

    try:
        print(f"  Fetching {symbol} options chain for {date_str}...")
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
                        if data.get('endpoint') == 'Historical Options' and data.get('message') == 'success':
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

        # Check response status
        if data.get('endpoint') != 'Historical Options':
            print(f"  Unexpected endpoint response: {data.get('endpoint')}")
            return None

        if data.get('message') != 'success':
            print(f"  API message: {data.get('message')}")
            return None

        # Extract options data
        if 'data' not in data or not data['data']:
            print(f"  No options data found for {date_str}")
            print(f"  API Response: {json.dumps(data, indent=2)}")
            return None

        # Convert to DataFrame
        df = pd.DataFrame(data['data'])

        # Convert numeric columns
        numeric_columns = [
            'strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
            'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho'
        ]

        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Convert integer columns
        integer_columns = ['bid_size', 'ask_size', 'volume', 'open_interest']
        for col in integer_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int64')

        # Convert date columns
        date_columns = ['expiration', 'date']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

        print(f"  Fetched {len(df)} contracts for {date_str}")
        return df

    except requests.exceptions.RequestException as e:
        print(f"  Request error for {date_str}: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  JSON decode error for {date_str}: {e}")
        return None
    except Exception as e:
        print(f"  Unexpected error for {date_str}: {e}")
        return None


def fetch_historical_options(symbol, start_date=None, end_date=None, days=None):
    """
    Fetch historical options chain data for a date range.

    Args:
        symbol: Stock ticker symbol
        start_date: Start date (YYYY-MM-DD or datetime)
        end_date: End date (YYYY-MM-DD or datetime)
        days: Number of days back from today (alternative to date range)

    Returns:
        Combined DataFrame with all data
    """
    # Determine date range
    if days:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
    else:
        if not start_date or not end_date:
            print("ERROR: Must provide either --days or both --start-date and --end-date")
            return None

        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    # Get list of trading days
    trading_days = get_trading_days(start_date, end_date, skip_weekends=True)

    print(f"\n{'='*60}")
    print(f"Fetching {symbol} Options Chain Data")
    print(f"Period: {start_date} to {end_date}")
    print(f"Total trading days: {len(trading_days)}")
    print(f"{'='*60}\n")

    # Create data directory
    data_dir = Path('data') / symbol.lower() / 'options'
    data_dir.mkdir(parents=True, exist_ok=True)

    all_data = []
    api_calls = 0
    start_time = time.time()

    for date in trading_days:
        # Check if file already exists
        date_str = date.strftime('%Y%m%d')
        date_file = data_dir / f"{symbol.lower()}_av_options_{date_str}.parquet"

        if date_file.exists():
            print(f"  Loading cached data for {date} from {date_file}")
            try:
                df = pd.read_parquet(date_file)
                all_data.append(df)
                continue
            except Exception as e:
                print(f"  Error loading cached file: {e}. Re-fetching...")

        # Fetch data from API
        df = fetch_options_chain(symbol, date)

        if df is not None and not df.empty:
            # Add metadata
            df['symbol'] = symbol
            df['fetch_timestamp'] = datetime.now()
            df['snapshot_date'] = pd.to_datetime(date)

            # Save to parquet
            df.to_parquet(date_file, compression='snappy', index=False)
            print(f"  Saved to {date_file}")

            all_data.append(df)

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

    # ALWAYS combine ALL daily files (not just the ones fetched in this run)
    # This ensures the combined file is always complete and up-to-date
    print(f"\n{'='*60}")
    print("Combining ALL daily options parquet files...")
    print(f"{'='*60}\n")

    # Find all daily parquet files
    import glob as glob_module
    pattern = str(data_dir / f"{symbol.lower()}_av_options_*.parquet")
    all_daily_files = glob_module.glob(pattern)
    # Exclude the combined file itself
    all_daily_files = [f for f in all_daily_files if 'combined' not in f]
    all_daily_files = sorted(all_daily_files)

    if not all_daily_files:
        print("No daily files found to combine.")
        return None

    # Load ALL daily files
    all_daily_data = []
    for i, file_path in enumerate(all_daily_files, 1):
        file_name = Path(file_path).name
        try:
            df = pd.read_parquet(file_path)
            all_daily_data.append(df)
            if i % 10 == 0:
                print(f"  Loaded {i}/{len(all_daily_files)} daily files...")
        except Exception as e:
            print(f"  Warning: Could not load {file_name}: {e}")
            continue

    if not all_daily_data:
        print("ERROR: No data could be loaded from daily files!")
        return None

    print(f"  Loaded {len(all_daily_data)}/{len(all_daily_files)} daily files")

    # Combine all daily data
    combined_df = pd.concat(all_daily_data, ignore_index=True)

    # Sort by snapshot date, expiration, strike, and type
    combined_df = combined_df.sort_values(['snapshot_date', 'expiration', 'strike', 'type'])

    # Remove duplicates (keep first occurrence)
    original_len = len(combined_df)
    combined_df = combined_df.drop_duplicates(
        subset=['snapshot_date', 'expiration', 'strike', 'type', 'contractID'],
        keep='first'
    )
    duplicates_removed = original_len - len(combined_df)

    if duplicates_removed > 0:
        print(f"  Removed {duplicates_removed:,} duplicate contracts")

    # Save combined data (overwrites previous combined file)
    combined_file = data_dir / f"{symbol.lower()}_av_options_combined.parquet"
    combined_df.to_parquet(combined_file, compression='snappy', index=False)

    # Count unique dates
    unique_dates = combined_df['snapshot_date'].nunique()

    # Create summary
    summary = {
        'symbol': symbol,
        'start_date': str(combined_df['snapshot_date'].min().date()),
        'end_date': str(combined_df['snapshot_date'].max().date()),
        'total_contracts': len(combined_df),
        'total_days': unique_dates,
        'daily_files_combined': len(all_daily_files),
        'duplicates_removed': duplicates_removed,
        'unique_expirations': int(combined_df['expiration'].nunique()),
        'unique_strikes': int(combined_df['strike'].nunique()),
        'calls_count': int(len(combined_df[combined_df['type'] == 'call'])),
        'puts_count': int(len(combined_df[combined_df['type'] == 'put'])),
        'last_update': datetime.now().isoformat(),
        'file': str(combined_file)
    }

    summary_file = data_dir / f"{symbol.lower()}_av_options_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}")
    print("COMBINED FILE SUMMARY")
    print(f"{'='*60}")
    print(f"Symbol: {symbol}")
    print(f"Daily files combined: {len(all_daily_files)}")
    print(f"Unique snapshot dates: {unique_dates}")
    print(f"Total contracts: {len(combined_df):,}")
    print(f"Duplicates removed: {duplicates_removed:,}")
    print(f"Date range: {summary['start_date']} to {summary['end_date']}")
    print(f"Unique expirations: {summary['unique_expirations']}")
    print(f"Unique strikes: {summary['unique_strikes']}")
    print(f"Calls: {summary['calls_count']:,} | Puts: {summary['puts_count']:,}")
    print(f"\nFiles created/updated:")
    print(f"  {combined_file}")
    print(f"  {summary_file}")
    print(f"{'='*60}\n")

    return combined_df


def analyze_options_data(df, symbol):
    """
    Provide basic analysis of options chain data.

    Args:
        df: DataFrame with options data
        symbol: Stock symbol

    Returns:
        Dictionary with analysis results
    """
    if df is None or df.empty:
        return None

    analysis = {
        'symbol': symbol,
        'total_contracts': len(df),
        'date_range': {
            'start': str(df['snapshot_date'].min().date()),
            'end': str(df['snapshot_date'].max().date())
        },
        'expiration_range': {
            'nearest': str(df['expiration'].min().date()),
            'farthest': str(df['expiration'].max().date())
        },
        'strike_range': {
            'min': float(df['strike'].min()),
            'max': float(df['strike'].max())
        },
        'by_type': {
            'calls': int(len(df[df['type'] == 'call'])),
            'puts': int(len(df[df['type'] == 'put']))
        },
        'avg_implied_vol': {
            'calls': float(df[df['type'] == 'call']['implied_volatility'].mean()),
            'puts': float(df[df['type'] == 'put']['implied_volatility'].mean())
        },
        'total_volume': {
            'calls': int(df[df['type'] == 'call']['volume'].sum()),
            'puts': int(df[df['type'] == 'put']['volume'].sum())
        },
        'total_open_interest': {
            'calls': int(df[df['type'] == 'call']['open_interest'].sum()),
            'puts': int(df[df['type'] == 'put']['open_interest'].sum())
        }
    }

    return analysis


def show_parquet_data(symbol, rows=100):
    """
    Load and display options parquet data for a given symbol.

    Args:
        symbol: Stock ticker symbol
        rows: Number of rows to display (default: 100)
    """
    data_dir = Path('data') / symbol.lower() / 'options'
    combined_file = data_dir / f"{symbol.lower()}_av_options_combined.parquet"
    summary_file = data_dir / f"{symbol.lower()}_av_options_summary.json"

    if not combined_file.exists():
        print(f"\nERROR: Combined file not found: {combined_file}")
        print(f"Please fetch data first using:")
        print(f"  python scripts/fetch_alphavantage_options.py --symbol {symbol} --days 30")
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
        print(f"  Date Range: {summary.get('start_date', 'N/A')} to {summary.get('end_date', 'N/A')}")
        print(f"  Total Contracts: {summary.get('total_contracts', 'N/A'):,}")
        print(f"  Total Days: {summary.get('total_days', 'N/A')}")
        print(f"  Unique Expirations: {summary.get('unique_expirations', 'N/A')}")
        print(f"  Unique Strikes: {summary.get('unique_strikes', 'N/A')}")
        print(f"  Calls: {summary.get('calls_count', 'N/A'):,}")
        print(f"  Puts: {summary.get('puts_count', 'N/A'):,}")
        print(f"  Last Update: {summary.get('last_update', 'N/A')}")
        print()

    # Show dataframe info
    print(f"DataFrame Info:")
    print(f"  Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print(f"  Columns: {', '.join(df.columns.tolist())}")
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

    # Show some basic stats by type
    if 'type' in df.columns:
        print("Distribution by Option Type:")
        print(f"{'-'*60}")
        print(df['type'].value_counts())
        print()

    # Show snapshot dates if available
    if 'snapshot_date' in df.columns:
        unique_dates = df['snapshot_date'].nunique()
        print(f"Unique Snapshot Dates: {unique_dates}")
        if unique_dates <= 10:
            print(f"Dates: {sorted(df['snapshot_date'].dt.date.unique())}")
        print()


def main():
    """Main function to fetch Alpha Vantage options chain data."""
    parser = argparse.ArgumentParser(
        description='Fetch historical options chain data from Alpha Vantage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch last 30 days of options data for IWM
  python fetch_alphavantage_options.py --symbol IWM --days 30

  # Fetch options data for a specific date range
  python fetch_alphavantage_options.py --symbol SPY --start-date 2025-01-01 --end-date 2025-01-31

  # Fetch single day
  python fetch_alphavantage_options.py --symbol IWM --date 2025-11-14

  # Show existing data
  python fetch_alphavantage_options.py --symbol IWM --show
  python fetch_alphavantage_options.py --symbol IWM --show --rows 200

Note: Free tier is limited to 5 calls/minute and 500 calls/day.
      One call per trading day is required.
        """
    )

    parser.add_argument('--symbol', type=str, required=True,
                       help='Stock ticker symbol (e.g., IWM, SPY)')
    parser.add_argument('--days', type=int,
                       help='Number of days back from today to fetch')
    parser.add_argument('--start-date', type=str,
                       help='Start date (YYYY-MM-DD format)')
    parser.add_argument('--end-date', type=str,
                       help='End date (YYYY-MM-DD format)')
    parser.add_argument('--date', type=str,
                       help='Fetch single date only (YYYY-MM-DD format)')
    parser.add_argument('--analyze', action='store_true',
                       help='Show analysis of fetched data')
    parser.add_argument('--show', action='store_true',
                       help='Display existing parquet data instead of fetching')
    parser.add_argument('--rows', type=int, default=100,
                       help='Number of rows to display when using --show (default: 100)')

    args = parser.parse_args()

    # If --show flag is set, display data and exit
    if args.show:
        show_parquet_data(args.symbol, args.rows)
        return

    # Validate API key
    if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == 'your_alpha_vantage_api_key_here':
        print("ERROR: ALPHA_VANTAGE_API_KEY not set in .env file")
        print("Please add your API key to .env file:")
        print("  ALPHA_VANTAGE_API_KEY=your_key_here")
        sys.exit(1)

    try:
        if args.date:
            # Fetch single date
            print(f"\nFetching {args.symbol} options chain for {args.date}")
            df = fetch_options_chain(args.symbol, args.date)

            if df is not None:
                # Save to file
                data_dir = Path('data') / args.symbol.lower() / 'options'
                data_dir.mkdir(parents=True, exist_ok=True)

                date_str = datetime.strptime(args.date, '%Y-%m-%d').strftime('%Y%m%d')
                date_file = data_dir / f"{args.symbol.lower()}_av_options_{date_str}.parquet"

                df['symbol'] = args.symbol
                df['fetch_timestamp'] = datetime.now()
                df['snapshot_date'] = pd.to_datetime(args.date)

                df.to_parquet(date_file, compression='snappy', index=False)
                print(f"\nSaved {len(df)} contracts to {date_file}")

                if args.analyze:
                    analysis = analyze_options_data(df, args.symbol)
                    if analysis:
                        print("\nAnalysis:")
                        print(json.dumps(analysis, indent=2))
        else:
            # Fetch date range or days back
            df = fetch_historical_options(
                args.symbol,
                start_date=args.start_date,
                end_date=args.end_date,
                days=args.days
            )

            if df is None:
                sys.exit(1)

            if args.analyze:
                analysis = analyze_options_data(df, args.symbol)
                if analysis:
                    print("\nAnalysis:")
                    print(json.dumps(analysis, indent=2))

        print("\nFetch completed successfully!")

    except KeyboardInterrupt:
        print("\n\nFetch interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
