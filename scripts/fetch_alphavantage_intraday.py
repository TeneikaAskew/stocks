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

# Load environment variables
load_dotenv()

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', 'VNMXDQ9LBOJ5X2I6')
#7E8X3MQLLSW5HPWF
BASE_URL = 'https://www.alphavantage.co/query'

# Rate limiting: Alpha Vantage free tier allows 5 API calls/minute, 500/day
CALLS_PER_MINUTE = 5
DELAY_BETWEEN_CALLS = 60 / CALLS_PER_MINUTE  # 12 seconds


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
            return None

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


def fetch_historical_intraday(symbol, years=5, interval='1min'):
    """
    Fetch historical intraday data for specified number of years.

    Args:
        symbol: Stock ticker symbol
        years: Number of years of history to fetch (default: 5)
        interval: Time interval for bars (default: 1min)

    Returns:
        Combined DataFrame with all data
    """
    # Calculate date range
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

        if month_file.exists():
            print(f"  Loading cached data for {month} from {month_file}")
            try:
                df = pd.read_parquet(month_file)
                all_data.append(df)
                continue
            except Exception as e:
                print(f"  Error loading cached file: {e}. Re-fetching...")

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

    # Combine all data
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=False)
        combined_df = combined_df.sort_index()

        # Save combined data
        combined_file = data_dir / f"{symbol.lower()}_av_{interval}_combined.parquet"
        combined_df.to_parquet(combined_file, compression='snappy', index=True)

        # Create summary
        summary = {
            'symbol': symbol,
            'interval': interval,
            'start_date': str(combined_df.index.min()),
            'end_date': str(combined_df.index.max()),
            'total_bars': len(combined_df),
            'total_months': len(months),
            'latest_close': float(combined_df['Close'].iloc[-1]),
            'latest_volume': int(combined_df['Volume'].iloc[-1]),
            'last_update': datetime.now().isoformat(),
            'file': str(combined_file)
        }

        summary_file = data_dir / f"{symbol.lower()}_av_{interval}_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Total bars: {summary['total_bars']:,}")
        print(f"  Date range: {summary['start_date']} to {summary['end_date']}")
        print(f"  Latest close: ${summary['latest_close']:.2f}")
        print(f"  Combined file: {combined_file}")
        print(f"  Summary file: {summary_file}")
        print(f"{'='*60}\n")

        return combined_df
    else:
        print("\nNo data was fetched.")
        return None


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

    args = parser.parse_args()

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
            df = fetch_historical_intraday(args.symbol, years=args.years, interval=args.interval)

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
