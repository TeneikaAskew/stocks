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

# Alpha Vantage API configuration
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', '7E8X3MQLLSW5HPWF')
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
            return None

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

    # Combine all data
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)

        # Sort by snapshot date, expiration, and strike
        combined_df = combined_df.sort_values(['snapshot_date', 'expiration', 'strike', 'type'])

        # Save combined data
        combined_file = data_dir / f"{symbol.lower()}_av_options_combined.parquet"
        combined_df.to_parquet(combined_file, compression='snappy', index=False)

        # Create summary
        summary = {
            'symbol': symbol,
            'start_date': str(start_date),
            'end_date': str(end_date),
            'total_contracts': len(combined_df),
            'total_days': len(trading_days),
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
        print(f"Summary:")
        print(f"  Total contracts: {summary['total_contracts']:,}")
        print(f"  Date range: {summary['start_date']} to {summary['end_date']}")
        print(f"  Unique expirations: {summary['unique_expirations']}")
        print(f"  Unique strikes: {summary['unique_strikes']}")
        print(f"  Calls: {summary['calls_count']:,} | Puts: {summary['puts_count']:,}")
        print(f"  Combined file: {combined_file}")
        print(f"  Summary file: {summary_file}")
        print(f"{'='*60}\n")

        return combined_df
    else:
        print("\nNo data was fetched.")
        return None


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

    args = parser.parse_args()

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
