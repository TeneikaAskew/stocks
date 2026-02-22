#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Earnings Strategy Matcher

Reads EARNINGS strategy CSV files (Long Calls, Covered Calls, Bull Spreads, Bear Spreads)
and matches them with live options chain data from yahooquery to calculate
profit/loss and other metrics.

Designed for MULTI-DAY holds around earnings (Day 0-5 tracking).
For ETF SCALPING, use fetch_etf_options_intraday.py and its analysis function.

Usage:
    python match_earnings_strategy.py --strategy longcalls --limit 5
"""

import argparse
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from yahooquery import Ticker

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


def parse_date_flexible(date_value):
    """
    Parse date from various formats found in the CSV.

    Args:
        date_value: Date value (could be string, datetime, or various formats)

    Returns:
        datetime object or None if parsing fails
    """
    if pd.isna(date_value) or date_value == '':
        return None

    # If already datetime
    if isinstance(date_value, datetime):
        return date_value

    # If string, try various formats
    if isinstance(date_value, str):
        # Try common formats
        formats = [
            '%Y-%m-%d %H:%M:%S',  # 2025-08-22 19:44:55
            '%Y-%m-%d',            # 2025-08-22
            '%m/%d/%Y',            # 08/22/2025
            '%m/%d/%y',            # 08/22/25
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                continue

    # Try pandas to_datetime as last resort
    try:
        return pd.to_datetime(date_value)
    except:
        return None


def create_lookup_keys(df):
    """
    Create lookup keys for matching strategy CSV to options chain data.

    Creates:
    - run_yymmdd_key: TICKER_YYMMDD from Run Date
    - exp_yymmdd_key: TICKER_YYMMDD from Expiration
    - opt_type_inferred: C for calls, P for puts (from Strategy column)
    - join_underlying: uppercase ticker
    - join_expiration: date-only expiration
    - join_strike_x1000: strike × 1000 as integer
    - join_opt_type: C or P
    """
    print("\n" + "="*80)
    print("Creating Lookup Keys")
    print("="*80)

    # Parse dates
    df['run_date_parsed'] = df['Run Date'].apply(parse_date_flexible)
    df['exp_date_parsed'] = df['expDate'].apply(parse_date_flexible)

    # Create run_yymmdd_key: TICKER_YYMMDD
    df['run_yymmdd_key'] = df.apply(
        lambda row: f"{row['ticker']}_{row['run_date_parsed'].strftime('%y%m%d')}"
        if pd.notna(row['run_date_parsed']) else None,
        axis=1
    )

    # Create exp_yymmdd_key: TICKER_YYMMDD
    df['exp_yymmdd_key'] = df.apply(
        lambda row: f"{row['ticker']}_{row['exp_date_parsed'].strftime('%y%m%d')}"
        if pd.notna(row['exp_date_parsed']) else None,
        axis=1
    )

    # Infer option type from Strategy column
    df['opt_type_inferred'] = df['Strategy'].apply(
        lambda x: 'C' if 'call' in str(x).lower() else 'P'
    )

    # Create join fields for matching
    df['join_underlying'] = df['ticker'].str.upper()
    df['join_expiration'] = df['exp_date_parsed'].dt.date
    df['join_strike_x1000'] = (df['strike'] * 1000).astype(int)
    df['join_opt_type'] = df['opt_type_inferred']

    # Create OCC-style symbols (guesses)
    df['occ_guess_call'] = df.apply(
        lambda row: f"{row['ticker']}{row['exp_date_parsed'].strftime('%y%m%d')}C{int(row['strike']*1000):08d}"
        if pd.notna(row['exp_date_parsed']) else None,
        axis=1
    )

    df['occ_guess_put'] = df.apply(
        lambda row: f"{row['ticker']}{row['exp_date_parsed'].strftime('%y%m%d')}P{int(row['strike']*1000):08d}"
        if pd.notna(row['exp_date_parsed']) else None,
        axis=1
    )

    print(f"✓ Created lookup keys for {len(df)} records")
    print(f"  Sample run_yymmdd_key: {df['run_yymmdd_key'].iloc[0]}")
    print(f"  Sample exp_yymmdd_key: {df['exp_yymmdd_key'].iloc[0]}")
    print(f"  Sample OCC call: {df['occ_guess_call'].iloc[0]}")

    return df


def fetch_options_for_tickers(tickers):
    """
    Fetch options chain from yahooquery for given tickers.

    Args:
        tickers: List of ticker symbols

    Returns:
        DataFrame with options chain data
    """
    print("\n" + "="*80)
    print("Fetching Options Chain from yahooquery")
    print("="*80)

    print(f"Fetching options for {len(tickers)} ticker(s): {', '.join(tickers)}")

    try:
        # Fetch all tickers at once
        ticker_obj = Ticker(tickers)
        options_df = ticker_obj.option_chain

        if isinstance(options_df, pd.DataFrame) and not options_df.empty:
            # Reset index to make it easier to work with
            options_df = options_df.reset_index()
            print(f"\n" + "-"*40)
            print("Options Data Summary")
            print("-"*40)
            # print(f"Columns: {options_df.columns.tolist()}")
            # print(f"Data types:\n{options_df.dtypes}")
            print(f"Sample data:\n{options_df.head(3).to_string(index=False)}")

            print(f"✓ Fetched {len(options_df):,} option contracts")
            print(f"  Symbols: {options_df['symbol'].unique().tolist()}")
            print(f"  Expirations: {options_df['expiration'].nunique()} dates")

            # Create matching keys
            options_df['join_underlying'] = options_df['symbol'].str.upper()
            options_df['join_expiration'] = pd.to_datetime(options_df['expiration']).dt.date
            options_df['join_strike_x1000'] = (options_df['strike'] * 1000).astype(int)
            options_df['join_opt_type'] = options_df['optionType'].apply(
                lambda x: 'C' if x == 'calls' else 'P'
            )

            return options_df
        else:
            print("❌ No options data returned")
            return pd.DataFrame()

    except Exception as e:
        print(f"❌ Error fetching options: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def match_strategy_to_options(strategy_df, options_df):
    """
    Match strategy records to options chain data.

    Args:
        strategy_df: Strategy CSV data with lookup keys
        options_df: Options chain data from yahooquery

    Returns:
        Merged DataFrame with matched options
    """
    print("\n" + "="*80)
    print("Matching Strategy to Options Chain")
    print("="*80)

    # Rename overlapping columns in strategy_df to have _EW suffix BEFORE merge
    # This prevents conflicts with market data columns
    ew_rename = {
        'bid': 'bid_EW',
        'ask': 'ask_EW',
        'volume': 'volume_EW',
        'strike': 'strike_EW',
        'price': 'price_EW',
    }

    # Only rename columns that actually exist
    rename_dict = {k: v for k, v in ew_rename.items() if k in strategy_df.columns}
    strategy_df = strategy_df.rename(columns=rename_dict)
    print(f"✓ Renamed {len(rename_dict)} strategy columns with _EW suffix")

    # Merge on join fields (market data keeps original names)
    merged = strategy_df.merge(
        options_df,
        on=['join_underlying', 'join_expiration', 'join_strike_x1000', 'join_opt_type'],
        how='left',
        suffixes=('_dup', '')  # Keep market data clean, add _dup to any remaining conflicts
    )

    matched_count = merged['contractSymbol'].notna().sum()
    print(f"✓ Matched {matched_count} out of {len(strategy_df)} records")
    print(f"  Match rate: {matched_count/len(strategy_df)*100:.1f}%")

    # Show unmatched records
    unmatched = merged[merged['contractSymbol'].isna()]
    if len(unmatched) > 0:
        print(f"\n⚠ {len(unmatched)} unmatched records:")
        for _, row in unmatched.iterrows():
            # Use strategy strike since market strike might not exist
            strike_val = row.get('strike_strategy', row.get('strike', 'N/A'))
            print(f"  {row['ticker']} ${strike_val} {row['opt_type_inferred']} exp {row['join_expiration']}")

    return merged


def calculate_profit_loss(merged_df):
    """
    Calculate profit/loss and other metrics for matched options.

    Args:
        merged_df: Merged data with strategy and market prices

    Returns:
        DataFrame with calculated metrics
    """
    print("\n" + "="*80)
    print("Calculating Profit/Loss Metrics")
    print("="*80)

    # Entry price (what we paid) - from strategy CSV (now has _EW suffix)
    merged_df['entry_price'] = merged_df['price_EW'] if 'price_EW' in merged_df.columns else pd.Series([np.nan]*len(merged_df))

    # Entry bid/ask from EW (original strategy)
    merged_df['entry_bid_EW'] = merged_df['bid_EW'] if 'bid_EW' in merged_df.columns else pd.Series([np.nan]*len(merged_df))
    merged_df['entry_ask_EW'] = merged_df['ask_EW'] if 'ask_EW' in merged_df.columns else pd.Series([np.nan]*len(merged_df))

    # Current market price - from yahooquery (clean names)
    merged_df['current_price'] = merged_df['lastPrice'] if 'lastPrice' in merged_df.columns else pd.Series([np.nan]*len(merged_df))

    # Current Bid/Ask from market - clean names from yahooquery
    merged_df['market_bid'] = merged_df['bid'] if 'bid' in merged_df.columns else pd.Series([np.nan]*len(merged_df))
    merged_df['market_ask'] = merged_df['ask'] if 'ask' in merged_df.columns else pd.Series([np.nan]*len(merged_df))

    # Calculate P&L
    merged_df['pnl_per_contract'] = (merged_df['current_price'] - merged_df['entry_price']) * 100
    merged_df['pnl_percent'] = ((merged_df['current_price'] - merged_df['entry_price']) /
                                 merged_df['entry_price'] * 100)

    # Days to expiration
    today = datetime.now().date()
    merged_df['days_to_expiration'] = (
        pd.to_datetime(merged_df['join_expiration']) - pd.to_datetime(today)
    ).dt.days

    # Volume and Open Interest from market - clean names from yahooquery
    merged_df['market_volume'] = merged_df['volume'] if 'volume' in merged_df.columns else pd.Series([np.nan]*len(merged_df))
    merged_df['market_open_interest'] = merged_df['openInterest'] if 'openInterest' in merged_df.columns else pd.Series([np.nan]*len(merged_df))

    # Implied Volatility from market
    merged_df['market_iv'] = merged_df['impliedVolatility'] if 'impliedVolatility' in merged_df.columns else pd.Series([np.nan]*len(merged_df))

    # In the money status
    merged_df['is_itm'] = merged_df['inTheMoney'] if 'inTheMoney' in merged_df.columns else pd.Series([False]*len(merged_df))

    # Strike price (use _EW version from strategy)
    merged_df['strike_used'] = merged_df['strike_EW'] if 'strike_EW' in merged_df.columns else merged_df.get('strike', pd.Series([np.nan]*len(merged_df)))

    print(f"✓ Calculated metrics for {len(merged_df)} records")

    # Summary statistics
    matched = merged_df[merged_df['contractSymbol'].notna()]
    if len(matched) > 0:
        total_pnl = matched['pnl_per_contract'].sum()
        avg_pnl_pct = matched['pnl_percent'].mean()

        print(f"\nSummary:")
        print(f"  Total P&L: ${total_pnl:,.2f}")
        print(f"  Avg P&L %: {avg_pnl_pct:.2f}%")
        print(f"  Winners: {(matched['pnl_per_contract'] > 0).sum()}")
        print(f"  Losers: {(matched['pnl_per_contract'] < 0).sum()}")

    return merged_df


def load_strategy_csv(strategy_name, data_dir='google-apps-script/data'):
    """
    Load strategy CSV file.

    Args:
        strategy_name: Name of strategy (longcalls, coveredcalls, bullspreads, bearspreads)
        data_dir: Directory containing CSV files

    Returns:
        DataFrame with strategy data
    """
    strategy_files = {
        'longcalls': 'LongCalls.csv',
        'coveredcalls': 'CoveredCalls.csv',
        'bullspreads': 'BullSpreads.csv',
        'bearspreads': 'BearSpreads.csv',
    }

    filename = strategy_files.get(strategy_name.lower())
    if not filename:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    filepath = Path(data_dir) / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Strategy file not found: {filepath}")

    print(f"\n{'='*80}")
    print(f"Loading Strategy: {strategy_name.upper()}")
    print(f"{'='*80}")
    print(f"File: {filepath}")

    df = pd.read_csv(filepath)
    print(f"✓ Loaded {len(df)} records")
    print(f"  Columns: {len(df.columns)}")
    print(f"  Date range: {df['Run Date'].min()} to {df['Run Date'].max()}")

    return df


def main():
    parser = argparse.ArgumentParser(
        description='Match EARNINGS strategy CSV to live options data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test with first 5 long calls
  python match_earnings_strategy.py --strategy longcalls --limit 5

  # Process all covered calls
  python match_earnings_strategy.py --strategy coveredcalls

  # Bull spreads with custom output
  python match_earnings_strategy.py --strategy bullspreads --output data/matched_bullspreads.csv

Note: This is for EARNINGS strategies (multi-day holds).
For ETF SCALPING, use fetch_etf_options_intraday.py --analyze
        """
    )

    parser.add_argument(
        '--strategy',
        required=True,
        choices=['longcalls', 'coveredcalls', 'bullspreads', 'bearspreads'],
        help='Strategy type to process'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit to first N records (for testing)'
    )

    parser.add_argument(
        '--tail',
        action='store_true',
        help='Use last N records instead of first N (for recent data)'
    )

    parser.add_argument(
        '--output',
        default=None,
        help='Output CSV file path (default: data/matched_<strategy>.csv)'
    )

    parser.add_argument(
        '--data-dir',
        default='google-apps-script/data',
        help='Directory containing strategy CSV files'
    )

    args = parser.parse_args()

    print(f"\n{'='*80}")
    print(f"Earnings Strategy Matcher")
    print(f"{'='*80}")
    print(f"Strategy: {args.strategy.upper()}")
    print(f"Limit: {args.limit if args.limit else 'No limit'}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Step 1: Load strategy CSV
        strategy_df = load_strategy_csv(args.strategy, args.data_dir)

        # Limit records if specified
        if args.limit:
            if args.tail:
                print(f"\n⚠ Using last {args.limit} records (most recent) for testing")
                strategy_df = strategy_df.tail(args.limit)
            else:
                print(f"\n⚠ Limiting to first {args.limit} records for testing")
                strategy_df = strategy_df.head(args.limit)

        # Step 2: Create lookup keys
        strategy_df = create_lookup_keys(strategy_df)

        # Step 3: Get unique tickers
        tickers = strategy_df['ticker'].unique().tolist()

        # Step 4: Fetch options chain
        options_df = fetch_options_for_tickers(tickers)

        if options_df.empty:
            print("\n❌ Failed to fetch options data. Exiting.")
            sys.exit(1)

        # Step 5: Match strategy to options
        matched_df = match_strategy_to_options(strategy_df, options_df)

        # Step 6: Calculate profit/loss
        result_df = calculate_profit_loss(matched_df)

        # Step 7: Display results
        print("\n" + "="*80)
        print("Results Summary")
        print("="*80)

        # Select key columns for display
        display_cols = [
            'ticker', 'run_date_parsed', 'strike_used', 'join_opt_type', 'entry_price',
            'entry_bid_EW', 'entry_ask_EW', 'current_price', 'market_bid', 'market_ask',
            'pnl_per_contract', 'pnl_percent', 'join_expiration',
            'days_to_expiration', 'market_volume', 'market_open_interest',
            'market_iv', 'is_itm', 'contractSymbol'
        ]

        # Only include columns that exist
        display_cols = [col for col in display_cols if col in result_df.columns]

        matched_results = result_df[result_df['contractSymbol'].notna()][display_cols]

        if len(matched_results) > 0:
            print("\nMatched Positions:")
            print(matched_results.to_string(index=False))

            # Detailed per-position breakdown
            print("\n" + "="*80)
            print("Detailed Position Analysis")
            print("="*80)

            for idx, row in matched_results.iterrows():
                print(f"\n{row['ticker']} - ${row['strike_used']} {row['join_opt_type']} exp {row['join_expiration']}")
                print(f"  Contract: {row['contractSymbol']}")
                print(f"  ENTRY (EW):  Price: ${row['entry_price']:.2f} | Bid: ${row['entry_bid_EW']:.2f} | Ask: ${row['entry_ask_EW']:.2f}")
                print(f"  MARKET (Now): Price: ${row['current_price']:.2f} | Bid: ${row['market_bid']:.2f} | Ask: ${row['market_ask']:.2f}")
                print(f"  P&L: ${row['pnl_per_contract']:.2f} ({row['pnl_percent']:.2f}%)")
                print(f"  Days to exp: {row['days_to_expiration']}")
                print(f"  Volume: {row['market_volume']:,.0f} | OI: {row['market_open_interest']:,.0f}")
                print(f"  IV: {row['market_iv']:.2%} | ITM: {row['is_itm']}")

        # Step 8: Save to file
        if args.output:
            output_file = args.output
        else:
            output_dir = Path('data')
            output_dir.mkdir(exist_ok=True)
            output_file = output_dir / f"matched_{args.strategy}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        result_df.to_csv(output_file, index=False)
        print(f"\n✓ Saved results to: {output_file}")

        print(f"\n{'='*80}")
        print("✓ Complete!")
        print(f"{'='*80}\n")

    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ Error: {e}")
        print(f"{'='*80}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
