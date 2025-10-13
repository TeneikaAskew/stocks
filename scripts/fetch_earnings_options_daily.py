#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Earnings Options Daily Fetcher

Fetch end-of-day options chains for EARNINGS STRATEGIES from Google Sheets.
Designed for multi-day holds (Day 0 through Day 5 tracking).

This captures ONE snapshot per day at market close for stocks with:
- Long Calls, Covered Calls, Bull Spreads, Bear Spreads strategies
- Multi-day holding periods around earnings announcements

For INTRADAY ETF SCALPING, use fetch_etf_options_intraday.py instead.

YOUR OPTIONS:
-------------
1. Manual ticker list (RECOMMENDED for daily use):
   python scripts/fetch_earnings_options_daily.py AAPL MSFT GOOGL AMZN

2. Limited auto-load (for testing):
   python scripts/fetch_earnings_options_daily.py --limit 10

3. Full auto-load (779 tickers - will take 10-15 minutes!):
   python scripts/fetch_earnings_options_daily.py

OTHER OPTIONS:
--------------
# Specify custom data directory
python fetch_earnings_options_daily.py --data-dir google-apps-script/data

# Skip already-fetched tickers from today
python fetch_earnings_options_daily.py --skip-existing

SCHEDULE:
---------
Run ONCE daily at 4:15 PM ET (after market close)
15 16 * * 1-5 cd /path/to/stocks && python scripts/fetch_earnings_options_daily.py
"""

import argparse
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from yahooquery import Ticker
from pathlib import Path
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Strategy files to check for tickers
# Note: Files use camelCase (no spaces)
STRATEGY_FILES = [
    'LongCalls.csv',
    'CoveredCalls.csv',
    'BullSpreads.csv',
    'BearSpreads.csv',
    'LongPuts.csv',
    'ShortCalls.csv',
    'Strangles.csv',
    'Straddles.csv',
    'ShortPuts.csv'
]


def load_active_tickers(data_dir='google-apps-script/data'):
    """
    Load active tickers and their expiration dates from strategy CSV files.
    Only loads tickers where Run Date = today's date.

    Args:
        data_dir: Directory containing strategy CSV files

    Returns:
        tuple: (list of unique tickers,
                dict mapping ticker to list of expiration dates,
                dict mapping ticker to list of (expiration, strike) tuples)
    """
    data_path = Path(data_dir)
    tickers = set()
    ticker_expirations = {}  # ticker -> list of expiration dates
    ticker_strikes = {}  # ticker -> list of (expiration, strike) tuples
    today = datetime.now().date()

    print(f"\n{'='*80}")
    print(f"Loading Active Tickers from Strategy Files")
    print(f"{'='*80}")
    print(f"Directory: {data_path}")
    print(f"Filter: Run Date = {today}")

    for strategy_file in STRATEGY_FILES:
        file_path = data_path / strategy_file

        if not file_path.exists():
            print(f"  ⊘ {strategy_file}: Not found")
            continue

        try:
            df = pd.read_csv(file_path)

            if 'ticker' not in df.columns:
                print(f"  ⚠ {strategy_file}: No 'ticker' column")
                continue

            # Filter by Run Date = today
            if 'Run Date' not in df.columns:
                print(f"  ⚠ {strategy_file}: No 'Run Date' column, skipping file")
                continue

            # Parse Run Date and filter to today only
            df['Run Date'] = pd.to_datetime(df['Run Date'], errors='coerce')
            df_today = df[df['Run Date'].dt.date == today]

            if df_today.empty:
                print(f"  ⊘ {strategy_file}: No rows with Run Date = {today}")
                continue

            # Check for expDate column
            if 'expDate' not in df_today.columns:
                print(f"  ⚠ {strategy_file}: No 'expDate' column, will fetch all expirations")
                file_tickers = set(df_today['ticker'].dropna().unique())
                tickers.update(file_tickers)
                print(f"  ✓ {strategy_file}: {len(file_tickers)} unique tickers, {len(df_today)} rows from today")
                continue

            # Get ticker -> expiration and strike mappings (only from today's rows)
            for _, row in df_today.iterrows():
                ticker = row.get('ticker')
                exp_date = row.get('expDate')
                strike = row.get('strike')

                if pd.isna(ticker):
                    continue

                ticker = str(ticker).strip().upper()
                tickers.add(ticker)

                # Parse expiration date and strike
                if not pd.isna(exp_date):
                    try:
                        exp_dt = pd.to_datetime(exp_date).date()
                        if ticker not in ticker_expirations:
                            ticker_expirations[ticker] = set()
                        ticker_expirations[ticker].add(exp_dt)

                        # Add (expiration, strike) tuple for precise filtering
                        if not pd.isna(strike):
                            strike_val = float(strike)
                            if ticker not in ticker_strikes:
                                ticker_strikes[ticker] = set()
                            ticker_strikes[ticker].add((exp_dt, strike_val))
                    except Exception as e:
                        # Skip invalid dates/strikes
                        pass

            print(f"  ✓ {strategy_file}: {len(set(df_today['ticker'].dropna()))} unique tickers, {len(df_today)} rows from today")

        except Exception as e:
            print(f"  ❌ {strategy_file}: Error - {e}")

    # Convert sets to sorted lists
    for ticker in ticker_expirations:
        ticker_expirations[ticker] = sorted(list(ticker_expirations[ticker]))

    for ticker in ticker_strikes:
        ticker_strikes[ticker] = sorted(list(ticker_strikes[ticker]))

    tickers = sorted(list(tickers))
    print(f"\n✓ Found {len(tickers)} unique tickers across all strategies")
    print(f"✓ Loaded expiration dates for {len(ticker_expirations)} tickers")
    print(f"✓ Loaded strike prices for {len(ticker_strikes)} tickers")

    if len(tickers) <= 20:
        print(f"  Tickers: {', '.join(tickers)}")
    else:
        print(f"  First 20: {', '.join(tickers[:20])}...")

    return tickers, ticker_expirations, ticker_strikes


def check_existing_tickers(date_str, current_time, output_dir='data/options/earnings', time_window_minutes=15):
    """
    Check which tickers already have data for this specific time window.

    This allows multiple snapshots per ticker per day (e.g., 7:30 AM, 9:35 AM, 4:30 PM),
    but prevents duplicate fetches within the same time window (e.g., two 9:35 AM runs).

    Args:
        date_str: Date string in YYYYMMDD format
        current_time: Current datetime object
        output_dir: Directory containing daily snapshots
        time_window_minutes: Minutes within which to consider a snapshot a duplicate (default: 15)

    Returns:
        set: Ticker symbols that already have data for this time window
    """
    existing_tickers = set()
    output_path = Path(output_dir)

    # Check combined file
    combined_file = output_path / f"earnings_options_{date_str}.parquet"
    if combined_file.exists():
        try:
            df = pd.read_parquet(combined_file)

            # Filter to snapshots within time window
            df['snapshot_datetime'] = pd.to_datetime(df['snapshot_datetime'])

            # Define time window (e.g., 9:35 AM ± 15 minutes)
            time_lower = current_time - pd.Timedelta(minutes=time_window_minutes)
            time_upper = current_time + pd.Timedelta(minutes=time_window_minutes)

            # Get tickers that already have data in this time window
            recent_snapshots = df[(df['snapshot_datetime'] >= time_lower) &
                                 (df['snapshot_datetime'] <= time_upper)]

            if not recent_snapshots.empty:
                existing_tickers = set(recent_snapshots['symbol'].unique())
                snapshot_time = current_time.strftime('%I:%M %p')
                print(f"\n✓ Found {len(existing_tickers)} tickers already captured around {snapshot_time}:")
                print(f"  {', '.join(sorted(list(existing_tickers))[:20])}{'...' if len(existing_tickers) > 20 else ''}")
            else:
                print(f"\n✓ No tickers found for current time window ({current_time.strftime('%I:%M %p')})")

        except Exception as e:
            print(f"\n⚠ Error reading existing file: {e}")

    return existing_tickers


def calculate_greeks(row, stock_price, risk_free_rate=0.045):
    """
    Calculate option Greeks using Black-Scholes model.

    Args:
        row: DataFrame row with option data
        stock_price: Current underlying stock price
        risk_free_rate: Annual risk-free rate (default 4.5%)

    Returns:
        dict: Dictionary with calculated Greeks
    """
    try:
        # Extract parameters
        S = float(stock_price)  # Current stock price
        K = float(row['strike'])  # Strike price
        sigma = float(row['impliedVolatility'])  # IV (as decimal, e.g., 0.25 for 25%)

        # Time to expiration in years
        expiration = pd.to_datetime(row['expiration'])
        snapshot_dt = pd.to_datetime(row['snapshot_datetime'])
        days_to_exp = (expiration - snapshot_dt).days
        t = max(days_to_exp / 365.0, 0.000001)  # Avoid division by zero

        # Option type flag for py_vollib
        flag = 'c' if row['optionType'] == 'calls' else 'p'

        # Calculate Greeks
        greeks = {
            'delta': delta(flag, S, K, t, risk_free_rate, sigma),
            'gamma': gamma(flag, S, K, t, risk_free_rate, sigma),
            'theta': theta(flag, S, K, t, risk_free_rate, sigma) / 365.0,  # Convert to daily theta
            'vega': vega(flag, S, K, t, risk_free_rate, sigma) / 100.0,  # Vega per 1% change in IV
            'rho': rho(flag, S, K, t, risk_free_rate, sigma) / 100.0  # Rho per 1% change in rate
        }

        return greeks

    except Exception as e:
        # Return None for all Greeks if calculation fails
        return {
            'delta': None,
            'gamma': None,
            'theta': None,
            'vega': None,
            'rho': None
        }


def update_summary_log(df, output_path, date_str):
    """
    Update JSON summary log tracking fetch history and metadata.

    Args:
        df: DataFrame with options data
        output_path: Path object for output directory
        date_str: Date string in YYYYMMDD format
    """
    summary_file = output_path / "earnings_options_summary.json"

    # Load existing summary or create new
    if summary_file.exists():
        try:
            with open(summary_file, 'r') as f:
                summary = json.load(f)
        except Exception as e:
            print(f"\n⚠ Could not load existing summary: {e}")
            summary = {}
    else:
        summary = {}

    # Calculate statistics
    tickers_fetched = sorted(df['symbol'].unique().tolist())
    expiration_dates = sorted(df['expiration'].unique().tolist())

    # Get per-ticker stats
    ticker_stats = {}
    for ticker in tickers_fetched:
        ticker_df = df[df['symbol'] == ticker]
        ticker_stats[ticker] = {
            'contracts': len(ticker_df),
            'calls': len(ticker_df[ticker_df['optionType'] == 'calls']),
            'puts': len(ticker_df[ticker_df['optionType'] == 'puts']),
            'expirations': ticker_df['expiration'].nunique(),
            'total_volume': int(ticker_df['volume'].sum()) if 'volume' in ticker_df.columns else 0,
            'total_oi': int(ticker_df['openInterest'].sum()) if 'openInterest' in ticker_df.columns else 0,
            'avg_iv': float(ticker_df['impliedVolatility'].mean()) if 'impliedVolatility' in ticker_df.columns else 0.0,
            'underlying_price': float(ticker_df['underlying_price'].iloc[0]) if 'underlying_price' in ticker_df.columns and not ticker_df['underlying_price'].isna().all() else None,
            'avg_delta_calls': float(ticker_df[ticker_df['optionType'] == 'calls']['delta'].mean()) if 'delta' in ticker_df.columns else None,
            'avg_delta_puts': float(ticker_df[ticker_df['optionType'] == 'puts']['delta'].mean()) if 'delta' in ticker_df.columns else None,
            'avg_gamma': float(ticker_df['gamma'].mean()) if 'gamma' in ticker_df.columns else None,
            'avg_theta': float(ticker_df['theta'].mean()) if 'theta' in ticker_df.columns else None,
            'avg_vega': float(ticker_df['vega'].mean()) if 'vega' in ticker_df.columns else None
        }

    # Update summary
    summary.update({
        'last_update': datetime.now().isoformat(),
        'last_fetch_date': date_str,
        'total_tickers': len(tickers_fetched),
        'total_contracts': len(df),
        'total_calls': len(df[df['optionType'] == 'calls']),
        'total_puts': len(df[df['optionType'] == 'puts']),
        'total_expirations': df['expiration'].nunique(),
        'tickers': tickers_fetched,
        'expiration_dates': [str(d) for d in expiration_dates],
        'data_source': 'yahooquery',
        'fetch_frequency': 'daily_eod',
        'ticker_stats': ticker_stats
    })

    # Add fetch history
    if 'fetch_history' not in summary:
        summary['fetch_history'] = []

    summary['fetch_history'].append({
        'date': date_str,
        'timestamp': datetime.now().isoformat(),
        'tickers_fetched': tickers_fetched,
        'total_contracts': len(df)
    })

    # Keep an extended rolling history (default: 180 days) so we preserve more than six months of data
    history_retention_days = 180
    if len(summary['fetch_history']) > history_retention_days:
        summary['fetch_history'] = summary['fetch_history'][-history_retention_days:]

    # Save updated summary
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"✓ Updated summary log: {summary_file}")


def fetch_daily_snapshot(tickers, output_dir='data/options/earnings', skip_existing=False, ticker_expirations=None, ticker_strikes=None):
    """
    Fetch end-of-day options snapshot for earnings strategy tickers.

    Args:
        tickers: List of ticker symbols
        output_dir: Directory to save snapshot files
        skip_existing: If True, skip tickers that already have data for today
        ticker_expirations: Dict mapping ticker to list of expiration dates to fetch
                           If None or ticker not in dict, fetches all available expirations
        ticker_strikes: Dict mapping ticker to list of (expiration, strike) tuples
                       If provided, only fetches specific strikes for each expiration

    Returns:
        DataFrame with options data or None if failed
    """
    if not tickers:
        print("❌ No tickers provided")
        return None

    now = datetime.now()
    date_str = now.strftime('%Y%m%d')

    # Check for existing data and filter if requested
    if skip_existing:
        existing_tickers = check_existing_tickers(date_str, now, output_dir)

        if existing_tickers:
            original_count = len(tickers)
            tickers = [t for t in tickers if t.upper() not in existing_tickers]

            if len(tickers) == 0:
                snapshot_time = now.strftime('%I:%M %p')
                print(f"\n✓ All {original_count} tickers already have data for {snapshot_time}!")
                print(f"   Use without --skip-existing to re-fetch")
                return None

            print(f"\n⚠️  Skipping {original_count - len(tickers)} already-fetched tickers for this time")
            print(f"   Remaining to fetch: {len(tickers)} tickers")

    print(f"\n{'='*80}")
    print(f"Earnings Options Daily Snapshot")
    print(f"{'='*80}")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Tickers: {len(tickers)} symbols")

    # Batch fetch (yahooquery can handle multiple tickers)
    # Split into batches of 10 to avoid overloading
    batch_size = 10
    all_options = []
    stock_prices = {}  # Store stock prices for Greeks calculation

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        print(f"\nFetching batch {i//batch_size + 1}: {', '.join(batch)}")

        try:
            ticker_obj = Ticker(batch)

            # Fetch options chain
            options_df = ticker_obj.option_chain

            if isinstance(options_df, pd.DataFrame) and not options_df.empty:
                df = options_df.reset_index()

                # Filter by expiration dates and strikes if specified
                if ticker_expirations or ticker_strikes:
                    filtered_dfs = []
                    for symbol in batch:
                        symbol_df = df[df['symbol'] == symbol]

                        # Filter by strikes if provided (most specific)
                        if ticker_strikes and symbol in ticker_strikes and ticker_strikes[symbol]:
                            # Filter to specific (expiration, strike) pairs
                            matching_rows = []
                            for exp_date, strike_val in ticker_strikes[symbol]:
                                exp_ts = pd.Timestamp(exp_date)
                                # Match both expiration and strike
                                matches = symbol_df[
                                    (symbol_df['expiration'] == exp_ts) &
                                    (symbol_df['strike'] == strike_val)
                                ]
                                if not matches.empty:
                                    matching_rows.append(matches)

                            if matching_rows:
                                symbol_df = pd.concat(matching_rows, ignore_index=True)
                                strike_info = [f"{d}@{s}" for d, s in ticker_strikes[symbol]]
                                filtered_dfs.append(symbol_df)
                                print(f"    {symbol}: {len(symbol_df)} contracts (strikes: {', '.join(strike_info[:3])}{'...' if len(strike_info) > 3 else ''})")
                            else:
                                print(f"    {symbol}: No contracts found for specified strikes")

                        # Filter by expirations only (if no strikes specified)
                        elif ticker_expirations and symbol in ticker_expirations and ticker_expirations[symbol]:
                            # Convert expiration dates to datetime for comparison
                            target_dates = [pd.Timestamp(d) for d in ticker_expirations[symbol]]

                            # Filter to only matching expiration dates
                            symbol_df = symbol_df[symbol_df['expiration'].isin(target_dates)]

                            if not symbol_df.empty:
                                filtered_dfs.append(symbol_df)
                                print(f"    {symbol}: {len(symbol_df)} contracts (expirations: {[str(d.date()) for d in target_dates]})")
                            else:
                                print(f"    {symbol}: No contracts found for specified expirations")
                        else:
                            # No filter for this ticker, include all
                            if not symbol_df.empty:
                                filtered_dfs.append(symbol_df)
                                print(f"    {symbol}: {len(symbol_df)} contracts (all expirations)")

                    if filtered_dfs:
                        df = pd.concat(filtered_dfs, ignore_index=True)
                    else:
                        df = pd.DataFrame()  # Empty

                # Fetch current stock prices for Greeks calculation
                price_data = ticker_obj.price
                for symbol in batch:
                    if symbol in price_data and isinstance(price_data[symbol], dict):
                        # Use regularMarketPrice (current price) or postMarketPrice if after hours
                        stock_prices[symbol] = price_data[symbol].get('regularMarketPrice') or \
                                               price_data[symbol].get('postMarketPrice')

                if not df.empty:
                    all_options.append(df)
                    print(f"  ✓ Total: {len(df):,} contracts")
                else:
                    print(f"  ⚠ No contracts after filtering")
            else:
                print(f"  ⚠ No data for this batch")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue

    if not all_options:
        print("\n❌ No options data fetched")
        return None

    # Combine all batches
    combined_df = pd.concat(all_options, ignore_index=True)

    # Add metadata
    combined_df['snapshot_datetime'] = now
    combined_df['snapshot_date'] = now.date()
    combined_df['snapshot_time'] = now.time()
    combined_df['data_source'] = 'daily_eod'

    # Add underlying stock prices
    combined_df['underlying_price'] = combined_df['symbol'].map(stock_prices)

    # Calculate Greeks for each option
    print(f"\nCalculating Greeks...")
    greeks_list = []
    for idx, row in combined_df.iterrows():
        stock_price = stock_prices.get(row['symbol'])
        if stock_price:
            greeks = calculate_greeks(row, stock_price)
            greeks_list.append(greeks)
        else:
            # No stock price available
            greeks_list.append({
                'delta': None,
                'gamma': None,
                'theta': None,
                'vega': None,
                'rho': None
            })

    # Add Greeks columns
    greeks_df = pd.DataFrame(greeks_list)
    combined_df = pd.concat([combined_df, greeks_df], axis=1)

    print(f"✓ Greeks calculated for {combined_df['delta'].notna().sum():,} contracts")

    print(f"\n{'='*80}")
    print(f"Combined Results")
    print(f"{'='*80}")
    print(f"Total contracts: {len(combined_df):,}")
    print(f"Symbols: {combined_df['symbol'].nunique()}")
    print(f"Expirations: {combined_df['expiration'].nunique()} dates")
    print(f"Calls: {len(combined_df[combined_df['optionType']=='calls']):,}")
    print(f"Puts: {len(combined_df[combined_df['optionType']=='puts']):,}")

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Timestamp for filenames
    date_str = now.strftime('%Y%m%d')
    timestamp_str = now.strftime('%Y%m%d_%H%M%S')

    # Save snapshot file with timestamp (each run gets its own file)
    snapshot_file = output_path / f"earnings_options_{timestamp_str}.parquet"
    combined_df.to_parquet(snapshot_file, compression='snappy', index=False)
    print(f"\n✓ Saved snapshot: {snapshot_file}")

    # Append to daily combined file (all snapshots from today)
    daily_file = output_path / f"earnings_options_{date_str}.parquet"
    if daily_file.exists():
        try:
            existing_df = pd.read_parquet(daily_file)
            print(f"✓ Found daily file with {len(existing_df)} rows")

            # Append new data (don't remove duplicates - keep all snapshots)
            combined_df = pd.concat([existing_df, combined_df], ignore_index=True)
            print(f"  Appended {len(combined_df) - len(existing_df)} new rows")
            print(f"  Total: {len(combined_df)} rows")
        except Exception as e:
            print(f"⚠ Could not append to daily file: {e}")

    combined_df.to_parquet(daily_file, compression='snappy', index=False)
    print(f"✓ Saved daily file: {daily_file}")

    # Individual ticker files (commented out - combined parquet is sufficient)
    # ticker_dir = output_path / date_str
    # ticker_dir.mkdir(exist_ok=True)
    #
    # for symbol in combined_df['symbol'].unique():
    #     ticker_df = combined_df[combined_df['symbol'] == symbol]
    #     ticker_file = ticker_dir / f"{symbol}_{date_str}.parquet"
    #     ticker_df.to_parquet(ticker_file, compression='snappy', index=False)
    #
    # print(f"✓ Saved {combined_df['symbol'].nunique()} individual ticker files to {ticker_dir}/")

    # Summary stats by ticker
    print(f"\n{'='*80}")
    print(f"Per-Ticker Summary")
    print(f"{'='*80}")

    summary = combined_df.groupby('symbol').agg({
        'contractSymbol': 'count',
        'expiration': 'nunique',
        'volume': 'sum',
        'openInterest': 'sum',
        'impliedVolatility': 'mean'
    }).rename(columns={
        'contractSymbol': 'contracts',
        'expiration': 'expirations',
        'volume': 'total_volume',
        'openInterest': 'total_oi',
        'impliedVolatility': 'avg_iv'
    })

    # Sort by total volume
    summary = summary.sort_values('total_volume', ascending=False)

    print(summary.head(20).to_string())

    # Update JSON summary log
    update_summary_log(combined_df, output_path, date_str)

    print(f"\n{'='*80}")
    print(f"✓ Daily snapshot complete")
    print(f"{'='*80}\n")

    return combined_df


def main():
    parser = argparse.ArgumentParser(
        description='Fetch daily EOD options for earnings strategies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect tickers from strategy CSV files
  python fetch_earnings_options_daily.py

  # Fetch specific tickers
  python fetch_earnings_options_daily.py AAPL MSFT MDB

  # Specify custom data directory
  python fetch_earnings_options_daily.py --data-dir google-apps-script/data

Designed for EARNINGS STRATEGIES (multi-day holds).
For ETF SCALPING (same-day), use fetch_etf_options_intraday.py instead.

Best run at 4:15 PM ET daily via cron:
  15 16 * * 1-5 python fetch_earnings_options_daily.py
        """
    )

    parser.add_argument(
        'tickers',
        nargs='*',
        help='Ticker symbols (leave empty to auto-load from strategy files)'
    )

    parser.add_argument(
        '--data-dir',
        default='google-apps-script/data',
        help='Directory containing strategy CSV files (default: google-apps-script/data)'
    )

    parser.add_argument(
        '--output-dir',
        default='data/options/earnings',
        help='Output directory for snapshots (default: data/options/earnings)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit to first N tickers (useful for testing large CSV files)'
    )

    parser.add_argument(
        '--skip-existing',
        action='store_true',
        help='Skip tickers that already have data for today (avoids re-fetching)'
    )

    args = parser.parse_args()

    # Get tickers and expiration/strike mappings
    ticker_expirations = None
    ticker_strikes = None

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        print(f"Using provided tickers: {', '.join(tickers)}")
        print(f"⚠️  Manual ticker mode: Will fetch ALL available expirations and strikes (no filtering)")
    else:
        tickers, ticker_expirations, ticker_strikes = load_active_tickers(args.data_dir)

        if not tickers:
            print("\n❌ No tickers found in strategy files")
            print(f"   Checked directory: {args.data_dir}")
            print(f"\nProvide tickers manually:")
            print(f"  python fetch_earnings_options_daily.py AAPL MSFT MDB")
            sys.exit(1)

        # Apply limit if specified
        if args.limit and len(tickers) > args.limit:
            print(f"\n⚠️  Limiting to first {args.limit} tickers (found {len(tickers)} total)")
            tickers = tickers[:args.limit]
            # Also limit ticker_expirations and ticker_strikes dicts
            if ticker_expirations:
                ticker_expirations = {k: v for k, v in ticker_expirations.items() if k in tickers}
            if ticker_strikes:
                ticker_strikes = {k: v for k, v in ticker_strikes.items() if k in tickers}

    # Fetch snapshot
    result = fetch_daily_snapshot(tickers, args.output_dir, skip_existing=args.skip_existing,
                                   ticker_expirations=ticker_expirations,
                                   ticker_strikes=ticker_strikes)

    sys.exit(0 if result is not None else 1)


if __name__ == '__main__':
    main()
