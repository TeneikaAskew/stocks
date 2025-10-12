#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF Options Intraday Fetcher

Fetch options chains for ETFs (IWM, SPY, QQQ, SPX) for intraday tracking.
Designed for SCALPING STRATEGIES where you enter/exit within the same day.

Scheduled via GitHub Actions to capture 9 snapshots per day:
- 9:30 AM - Market open (high volatility)
- 9:35 AM - 5 minutes after open
- 9:40 AM - 10 minutes after open
- 10:00 AM - Volatility settling
- 11:30 AM - Mid-morning
- 1:00 PM - Post-lunch
- 2:30 PM - Afternoon session
- 3:30 PM - Power hour begins
- 4:05 PM - After close (EOD)

Usage:
    # Fetch snapshot now
    python fetch_etf_options_intraday.py

    # Analyze intraday P/L for a trade
    python fetch_etf_options_intraday.py --analyze IWM 220 C "2025-10-11 09:35" "2025-10-11 14:00"

Note: Scheduling is handled by .github/workflows/fetch_etf_options.yml
"""

import argparse
import sys
import pandas as pd
import numpy as np
from datetime import datetime, time
from yahooquery import Ticker
from pathlib import Path
import glob
from py_vollib.black_scholes import black_scholes as bs
from py_vollib.black_scholes.greeks import analytical as greeks
import warnings
warnings.filterwarnings('ignore')  # Suppress vollib warnings

# Fix encoding for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ETF tickers for scalping
ETF_TICKERS = ['IWM', 'SPY', 'QQQ', '^SPX']  # Use ^SPX for S&P 500 index options


def calculate_greeks(row, underlying_price, risk_free_rate=0.05):
    """
    Calculate option Greeks using Black-Scholes model.

    Args:
        row: DataFrame row with option data
        underlying_price: Current stock/ETF price
        risk_free_rate: Risk-free interest rate (default 5%)

    Returns:
        dict with delta, gamma, theta, vega, rho
    """
    try:
        # Extract values
        strike = float(row['strike'])
        expiration = pd.to_datetime(row['expiration'])
        option_type = 'c' if row['optionType'] == 'calls' else 'p'
        iv = float(row.get('impliedVolatility', 0))

        # Skip if IV is zero or missing
        if iv <= 0 or pd.isna(iv):
            return {'delta': np.nan, 'gamma': np.nan, 'theta': np.nan, 'vega': np.nan, 'rho': np.nan}

        # Calculate time to expiration in years
        now = pd.Timestamp.now()
        if expiration.tzinfo is None:
            expiration = expiration.tz_localize('US/Eastern')
        if now.tzinfo is None:
            now = now.tz_localize('US/Eastern')

        days_to_exp = (expiration - now).total_seconds() / (365.25 * 24 * 3600)

        # Need at least 1 day to expiration
        if days_to_exp <= 0:
            return {'delta': np.nan, 'gamma': np.nan, 'theta': np.nan, 'vega': np.nan, 'rho': np.nan}

        # Calculate Greeks
        delta = greeks.delta(option_type, underlying_price, strike, days_to_exp, risk_free_rate, iv)
        gamma = greeks.gamma(option_type, underlying_price, strike, days_to_exp, risk_free_rate, iv)
        theta = greeks.theta(option_type, underlying_price, strike, days_to_exp, risk_free_rate, iv)
        vega = greeks.vega(option_type, underlying_price, strike, days_to_exp, risk_free_rate, iv)
        rho = greeks.rho(option_type, underlying_price, strike, days_to_exp, risk_free_rate, iv)

        return {
            'delta': delta,
            'gamma': gamma,
            'theta': theta / 365.25,  # Convert to daily theta
            'vega': vega / 100,  # Convert to per 1% IV change
            'rho': rho / 100  # Convert to per 1% rate change
        }

    except Exception as e:
        # Return NaN if calculation fails
        return {'delta': np.nan, 'gamma': np.nan, 'theta': np.nan, 'vega': np.nan, 'rho': np.nan}


def get_market_session(current_time):
    """Classify current market session."""
    if current_time < time(9, 40):
        return 'OPEN_VOLATILE'  # First 10 mins
    elif current_time < time(10, 30):
        return 'OPEN_SETTLING'
    elif current_time < time(12, 0):
        return 'MORNING'
    elif current_time < time(14, 0):
        return 'MIDDAY'
    elif current_time < time(15, 30):
        return 'AFTERNOON'
    elif current_time < time(16, 0):
        return 'POWER_HOUR'
    else:
        return 'CLOSE'


def fetch_intraday_snapshot(output_dir='data/options/etfs'):
    """
    Fetch and save intraday options snapshot for ETFs.

    Args:
        output_dir: Directory to save snapshot files

    Returns:
        DataFrame with options data or None if failed
    """
    try:
        import pytz
        et = pytz.timezone('America/New_York')
        now = datetime.now(et)
    except ImportError:
        from datetime import timezone, timedelta
        et_offset = timedelta(hours=-5)
        now = datetime.now() + et_offset

    print(f"\n{'='*80}")
    print(f"ETF Options Intraday Snapshot")
    print(f"{'='*80}")
    print(f"Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Session: {get_market_session(now.time())}")
    print(f"Tickers: {', '.join(ETF_TICKERS)}")

    # Fetch options for all ETFs
    print(f"\nFetching options data...")
    ticker = Ticker(ETF_TICKERS)

    try:
        options_df = ticker.option_chain

        if options_df.empty or not isinstance(options_df, pd.DataFrame):
            print("❌ No options data returned")
            return None

        # Reset index and add metadata
        df = options_df.reset_index()
        df['snapshot_datetime'] = now
        df['snapshot_date'] = now.date()
        df['snapshot_time'] = now.time()
        df['market_session'] = get_market_session(now.time())

        print(f"✓ Fetched {len(df):,} contracts")
        print(f"  Symbols: {df['symbol'].unique().tolist()}")
        print(f"  Expirations: {df['expiration'].nunique()} dates")

        # Fetch underlying prices for each ticker
        print(f"\nFetching underlying prices...")
        underlying_prices = {}
        for ticker_symbol in df['symbol'].unique():
            try:
                # Get current price
                t = Ticker(ticker_symbol)
                price_data = t.price
                if isinstance(price_data, dict) and ticker_symbol in price_data:
                    underlying_price = price_data[ticker_symbol].get('regularMarketPrice', None)
                    if underlying_price:
                        underlying_prices[ticker_symbol] = float(underlying_price)
                        print(f"  ✓ {ticker_symbol}: ${underlying_price:.2f}")
            except Exception as e:
                print(f"  ⚠ {ticker_symbol}: Could not fetch price - {e}")

        # Add underlying price column
        df['underlying_price'] = df['symbol'].map(underlying_prices)

        # Calculate Greeks for each option
        print(f"\nCalculating Greeks...")
        greeks_list = []
        for idx, row in df.iterrows():
            ticker_symbol = row['symbol']
            if ticker_symbol in underlying_prices:
                greeks_dict = calculate_greeks(row, underlying_prices[ticker_symbol])
                greeks_list.append(greeks_dict)
            else:
                greeks_list.append({'delta': np.nan, 'gamma': np.nan, 'theta': np.nan, 'vega': np.nan, 'rho': np.nan})

        # Add Greeks columns
        greeks_df = pd.DataFrame(greeks_list)
        df = pd.concat([df, greeks_df], axis=1)

        # Count valid Greeks
        valid_greeks = df['delta'].notna().sum()
        print(f"✓ Calculated Greeks for {valid_greeks:,} contracts ({valid_greeks/len(df)*100:.1f}%)")

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Timestamp for filenames
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')

        # Save combined file (all ETFs)
        combined_file = output_path / f"etf_options_{timestamp_str}.parquet"
        df.to_parquet(combined_file, compression='snappy', index=False)
        print(f"\n✓ Saved combined: {combined_file}")

        # Save per-ticker files for faster individual access
        for ticker_symbol in ETF_TICKERS:
            ticker_df = df[df['symbol'] == ticker_symbol]
            if not ticker_df.empty:
                # Strip ^ from filename for cleaner file naming (e.g., ^SPX -> SPX)
                clean_ticker = ticker_symbol.replace('^', '')
                ticker_file = output_path / f"{clean_ticker}_{timestamp_str}.parquet"
                ticker_df.to_parquet(ticker_file, compression='snappy', index=False)

                # Show stats
                calls = len(ticker_df[ticker_df['optionType'] == 'calls'])
                puts = len(ticker_df[ticker_df['optionType'] == 'puts'])
                print(f"  ✓ {ticker_symbol}: {len(ticker_df):,} contracts ({calls} calls, {puts} puts)")

        print(f"\n{'='*80}")
        print(f"✓ Snapshot complete")
        print(f"{'='*80}\n")

        return df

    except Exception as e:
        print(f"❌ Error fetching options: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_intraday_pnl(ticker, strike, option_type, entry_time, exit_time, data_dir='data/options/etfs'):
    """
    Calculate P/L using intraday snapshots.
    Shows actual P/L plus best/worst possible exits based on captured data.

    Args:
        ticker: ETF symbol (IWM, SPY, QQQ, SPX)
        strike: Strike price (e.g., 220.0)
        option_type: 'C' for calls, 'P' for puts
        entry_time: Entry timestamp (e.g., '2025-10-11 09:35:00')
        exit_time: Exit timestamp (e.g., '2025-10-11 14:00:00')
        data_dir: Directory containing intraday snapshot files

    Returns:
        dict with P/L metrics or None if data unavailable
    """
    print(f"\n{'='*80}")
    print(f"Intraday P&L Analysis")
    print(f"{'='*80}")
    print(f"Ticker: {ticker}")
    print(f"Strike: ${strike}")
    print(f"Type: {'Call' if option_type == 'C' else 'Put'}")
    print(f"Entry: {entry_time}")
    print(f"Exit: {exit_time}")

    # Parse times (make timezone-aware)
    try:
        import pytz
        et = pytz.timezone('America/New_York')
        entry_dt = pd.to_datetime(entry_time)
        if entry_dt.tzinfo is None:
            entry_dt = et.localize(entry_dt)
        exit_dt = pd.to_datetime(exit_time)
        if exit_dt.tzinfo is None:
            exit_dt = et.localize(exit_dt)
    except ImportError:
        entry_dt = pd.to_datetime(entry_time)
        exit_dt = pd.to_datetime(exit_time)

    # Find all snapshots for the trading day(s)
    # Strip ^ from ticker for file pattern matching (e.g., ^SPX -> SPX)
    clean_ticker = ticker.replace('^', '')
    date_str = entry_dt.strftime('%Y%m%d')
    snapshot_pattern = f"{data_dir}/{clean_ticker}_{date_str}_*.parquet"
    snapshot_files = sorted(glob.glob(snapshot_pattern))

    # Also check next day if exit is next day
    if exit_dt.date() > entry_dt.date():
        next_date_str = exit_dt.strftime('%Y%m%d')
        snapshot_pattern_next = f"{data_dir}/{clean_ticker}_{next_date_str}_*.parquet"
        snapshot_files.extend(sorted(glob.glob(snapshot_pattern_next)))

    if not snapshot_files:
        print(f"\n❌ No snapshots found for {ticker} on {date_str}")
        print(f"   Looking for: {snapshot_pattern}")
        print(f"\n   Available files:")
        all_files = sorted(glob.glob(f"{data_dir}/{clean_ticker}_*.parquet"))
        for f in all_files[-5:]:  # Show last 5 files
            print(f"     {Path(f).name}")
        return None

    print(f"\n✓ Found {len(snapshot_files)} snapshots")

    # Track prices throughout the period
    entry_price = None
    exit_price = None
    max_price = 0
    min_price = float('inf')
    price_history = []

    option_type_str = 'calls' if option_type == 'C' else 'puts'

    for snapshot_file in snapshot_files:
        try:
            df = pd.read_parquet(snapshot_file)
            snapshot_time = pd.to_datetime(df['snapshot_datetime'].iloc[0])

            # Filter for specific option
            option_df = df[
                (df['strike'] == float(strike)) &
                (df['optionType'] == option_type_str)
            ]

            if option_df.empty:
                continue

            price = float(option_df['lastPrice'].values[0])
            bid = float(option_df['bid'].values[0]) if 'bid' in option_df.columns else price
            ask = float(option_df['ask'].values[0]) if 'ask' in option_df.columns else price

            # Record price point
            price_history.append({
                'time': snapshot_time,
                'price': price,
                'bid': bid,
                'ask': ask
            })

            # Find entry price (first snapshot at or after entry time)
            if entry_price is None and snapshot_time >= entry_dt:
                entry_price = price
                entry_time_actual = snapshot_time
                print(f"  Entry captured at {snapshot_time.strftime('%H:%M:%S')}: ${price:.2f} (bid ${bid:.2f}, ask ${ask:.2f})")

            # Find exit price (first snapshot at or after exit time)
            if exit_price is None and snapshot_time >= exit_dt:
                exit_price = price
                exit_time_actual = snapshot_time
                print(f"  Exit captured at {snapshot_time.strftime('%H:%M:%S')}: ${price:.2f} (bid ${bid:.2f}, ask ${ask:.2f})")

            # Track highs and lows during holding period
            if entry_price is not None and exit_price is None:
                max_price = max(max_price, price)
                min_price = min(min_price, price)

        except Exception as e:
            print(f"  ⚠ Error reading {Path(snapshot_file).name}: {e}")
            continue

    # Calculate P/L if we have both entry and exit
    if entry_price and exit_price:
        pnl_dollars = (exit_price - entry_price) * 100
        pnl_percent = (exit_price - entry_price) / entry_price * 100

        best_exit_dollars = (max_price - entry_price) * 100
        best_exit_percent = (max_price - entry_price) / entry_price * 100

        worst_exit_dollars = (min_price - entry_price) * 100
        worst_exit_percent = (min_price - entry_price) / entry_price * 100

        print(f"\n{'='*80}")
        print(f"P&L RESULTS")
        print(f"{'='*80}")
        print(f"\nACTUAL TRADE:")
        print(f"  Entry Price:    ${entry_price:.2f}")
        print(f"  Exit Price:     ${exit_price:.2f}")
        print(f"  P&L per 100:    ${pnl_dollars:+.2f}")
        print(f"  P&L %:          {pnl_percent:+.2f}%")

        print(f"\nINTRADAY EXTREMES:")
        print(f"  High:           ${max_price:.2f}")
        print(f"  Best Exit P&L:  ${best_exit_dollars:+.2f} ({best_exit_percent:+.2f}%)")
        print(f"  Low:            ${min_price:.2f}")
        print(f"  Worst Exit P&L: ${worst_exit_dollars:+.2f} ({worst_exit_percent:+.2f}%)")

        print(f"\nOPPORTUNITY ANALYSIS:")
        missed_opportunity = best_exit_dollars - pnl_dollars
        if missed_opportunity > 0:
            print(f"  Missed gains:   ${missed_opportunity:.2f} ({(missed_opportunity/best_exit_dollars)*100:.1f}% of best possible)")
        else:
            print(f"  Excellent exit! Near optimal price")

        dodged_loss = pnl_dollars - worst_exit_dollars
        if dodged_loss > 0:
            print(f"  Avoided loss:   ${dodged_loss:.2f} (vs worst possible)")

        print(f"\n{'='*80}")
        print(f"PRICE HISTORY ({len(price_history)} snapshots):")
        print(f"{'='*80}")
        for i, point in enumerate(price_history, 1):
            marker = ""
            if i == 1 or (point['time'] == entry_time_actual):
                marker = " ← ENTRY"
            elif 'exit_time_actual' in locals() and point['time'] == exit_time_actual:
                marker = " ← EXIT"
            elif point['price'] == max_price:
                marker = " ← HIGH"
            elif point['price'] == min_price:
                marker = " ← LOW"

            print(f"  {point['time'].strftime('%H:%M:%S')}: ${point['price']:.2f} (bid ${point['bid']:.2f}, ask ${point['ask']:.2f}){marker}")

        print(f"{'='*80}\n")

        return {
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_dollars': pnl_dollars,
            'pnl_percent': pnl_percent,
            'intraday_high': max_price,
            'intraday_low': min_price,
            'best_exit_pnl': best_exit_dollars,
            'worst_exit_pnl': worst_exit_dollars,
            'missed_opportunity': missed_opportunity,
            'price_history': price_history
        }
    else:
        print(f"\n❌ Could not calculate P/L")
        if entry_price is None:
            print(f"   Missing entry price at {entry_time}")
        if exit_price is None:
            print(f"   Missing exit price at {exit_time}")
        print(f"\n   Available snapshot times:")
        for point in price_history[-10:]:  # Show last 10
            print(f"     {point['time'].strftime('%Y-%m-%d %H:%M:%S')}: ${point['price']:.2f}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Fetch intraday ETF options snapshots for scalping strategies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch snapshot now
  python fetch_etf_options_intraday.py

  # Analyze a completed trade
  python fetch_etf_options_intraday.py --analyze IWM 220 C "2025-10-11 09:35" "2025-10-11 14:00"

Scheduling:
  Automated captures run via GitHub Actions workflow (.github/workflows/fetch_etf_options.yml)
  - 9 snapshots per trading day (Mon-Fri)
  - Captures at: 9:30, 9:35, 9:40, 10:00, 11:30, 1:00, 2:30, 3:30, 4:05 PM ET

Designed for ETF scalping (same-day entries/exits).
For multi-day earnings strategies, use fetch_earnings_options_daily.py instead.
        """
    )

    parser.add_argument(
        '--analyze',
        nargs=5,
        metavar=('TICKER', 'STRIKE', 'TYPE', 'ENTRY_TIME', 'EXIT_TIME'),
        help='Analyze intraday P/L for a trade (e.g., IWM 220 C "2025-10-11 09:35" "2025-10-11 14:00")'
    )

    parser.add_argument(
        '--output-dir',
        default='data/options/etfs',
        help='Output directory for snapshots (default: data/options/etfs)'
    )

    args = parser.parse_args()

    # Analysis mode
    if args.analyze:
        ticker, strike, option_type, entry_time, exit_time = args.analyze
        result = analyze_intraday_pnl(
            ticker=ticker.upper(),
            strike=float(strike),
            option_type=option_type.upper(),
            entry_time=entry_time,
            exit_time=exit_time,
            data_dir=args.output_dir
        )
        sys.exit(0 if result else 1)

    # Capture mode - always run when called
    result = fetch_intraday_snapshot(args.output_dir)
    sys.exit(0 if result is not None else 1)


if __name__ == '__main__':
    main()
