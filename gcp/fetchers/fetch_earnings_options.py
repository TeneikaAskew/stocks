#!/usr/bin/env python3
"""
Cloud Run Job: Fetch earnings options snapshots → Cloud SQL + GCS.

Replaces the GitHub Actions workflow fetch-earnings-options.yml.
Scheduled 6 times per day by Cloud Scheduler during market hours.

Strategy tickers are read from GCS-hosted CSV files (mirroring the
google-apps-script/data/ CSVs that the Google Sheets sync populates).

Usage:
    python -m gcp.fetchers.fetch_earnings_options [--date YYYY-MM-DD] [--limit 10]
"""

import argparse
import logging
import os
import sys
import io
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet, download_csv_from_gcs

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)

STRATEGY_FILES = [
    'LongCalls.csv', 'CoveredCalls.csv', 'BullSpreads.csv', 'BearSpreads.csv',
    'LongPuts.csv', 'ShortCalls.csv', 'Strangles.csv', 'Straddles.csv', 'ShortPuts.csv',
]
RISK_FREE_RATE = 0.045
BATCH_SIZE = 10


def load_active_tickers_from_gcs(bucket: str, snap_date: str) -> list:
    """Load tickers from strategy CSVs stored in GCS under sheets/."""
    tickers = set()
    for csv_name in STRATEGY_FILES:
        try:
            df = download_csv_from_gcs(bucket, f"sheets/{csv_name}")
            if df is None or df.empty:
                continue
            # Filter to rows where Run Date matches today
            if 'Run Date' in df.columns:
                df = df[pd.to_datetime(df['Run Date'], errors='coerce').dt.strftime('%Y-%m-%d') == snap_date]
            if 'Ticker' in df.columns:
                tickers.update(df['Ticker'].dropna().str.upper().tolist())
            elif 'Symbol' in df.columns:
                tickers.update(df['Symbol'].dropna().str.upper().tolist())
        except Exception as e:
            log.warning("  Could not read %s from GCS: %s", csv_name, e)

    return sorted(tickers)


def load_active_tickers_from_local(snap_date: str) -> list:
    """Fallback: read tickers from local google-apps-script/data/ CSVs."""
    tickers = set()
    data_dir = Path(__file__).parent.parent.parent / 'google-apps-script' / 'data'

    for csv_name in STRATEGY_FILES:
        csv_path = data_dir / csv_name
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path)
            if 'Run Date' in df.columns:
                df = df[pd.to_datetime(df['Run Date'], errors='coerce').dt.strftime('%Y-%m-%d') == snap_date]
            for col in ('Ticker', 'Symbol', 'ticker', 'symbol'):
                if col in df.columns:
                    tickers.update(df[col].dropna().str.upper().tolist())
                    break
        except Exception as e:
            log.warning("  Could not read %s: %s", csv_name, e)

    return sorted(tickers)


def calculate_greeks(row: pd.Series, underlying_price: float) -> dict:
    """Calculate Black-Scholes Greeks for a single option row."""
    try:
        from py_vollib.black_scholes.greeks.analytical import (
            delta, gamma, theta, vega, rho
        )
        import warnings

        iv = float(row.get('impliedVolatility', 0) or 0)
        if iv <= 0 or iv > 20:
            return dict.fromkeys(['delta', 'gamma', 'theta', 'vega', 'rho'], None)

        strike = float(row['strike'])
        expiry = pd.to_datetime(row['expiration'])
        t = max((expiry - pd.Timestamp.now()).days / 365.0, 1/365)
        flag = 'c' if str(row.get('optionType', '')).lower().startswith('c') else 'p'

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return {
                'delta': delta(flag, underlying_price, strike, t, RISK_FREE_RATE, iv),
                'gamma': gamma(flag, underlying_price, strike, t, RISK_FREE_RATE, iv),
                'theta': theta(flag, underlying_price, strike, t, RISK_FREE_RATE, iv),
                'vega':  vega(flag, underlying_price, strike, t, RISK_FREE_RATE, iv),
                'rho':   rho(flag, underlying_price, strike, t, RISK_FREE_RATE, iv),
            }
    except Exception:
        return dict.fromkeys(['delta', 'gamma', 'theta', 'vega', 'rho'], None)


def fetch_options_for_symbol(symbol: str) -> pd.DataFrame:
    """Fetch earnings options chain for a single symbol via yahooquery."""
    from yahooquery import Ticker

    try:
        t = Ticker(symbol)
        chain = t.option_chain
        if isinstance(chain, (str, dict)) or chain is None:
            return pd.DataFrame()

        price_info = t.price
        underlying_price = 0.0
        if isinstance(price_info, dict) and symbol in price_info:
            underlying_price = float(
                price_info[symbol].get('regularMarketPrice', 0) or 0
            )

        df = chain.reset_index()
        df['symbol'] = symbol
        df['underlying_price'] = underlying_price

        # Add Greeks
        greek_rows = [calculate_greeks(row, underlying_price) for _, row in df.iterrows()]
        greek_df = pd.DataFrame(greek_rows, index=df.index)
        df = pd.concat([df, greek_df], axis=1)

        return df

    except Exception as e:
        log.error("    Error fetching %s: %s", symbol, e)
        return pd.DataFrame()


def normalize_for_sql(df: pd.DataFrame, snapshot_ts: pd.Timestamp) -> pd.DataFrame:
    """Rename columns to match earnings_options_snapshots schema."""
    df = df.copy()

    col_map = {
        'contractSymbol':    'contract_symbol',
        'optionType':        'option_type',
        'lastPrice':         'last_price',
        'percentChange':     'percent_change',
        'openInterest':      'open_interest',
        'impliedVolatility': 'implied_volatility',
        'inTheMoney':        'in_the_money',
        'lastTradeDate':     'last_trade_date',
        'contractSize':      'contract_size',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    df['snapshot_ts'] = snapshot_ts
    df['snapshot_date'] = snapshot_ts.date()
    df['data_source'] = 'daily_eod'

    if 'expiration' in df.columns:
        df['expiration'] = pd.to_datetime(df['expiration'], errors='coerce').dt.date

    keep = [
        'symbol', 'snapshot_ts', 'snapshot_date',
        'contract_symbol', 'option_type', 'expiration', 'strike', 'in_the_money',
        'contract_size', 'bid', 'ask', 'last_price', 'change', 'percent_change',
        'last_trade_date', 'volume', 'open_interest', 'implied_volatility',
        'delta', 'gamma', 'theta', 'vega', 'rho',
        'underlying_price', 'data_source',
    ]
    return df[[c for c in keep if c in df.columns]].dropna(
        subset=['symbol', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    )


def main():
    parser = argparse.ArgumentParser(description='Fetch earnings options → Cloud SQL + GCS')
    parser.add_argument('--date', default=None, help='Snapshot date (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Max tickers to process')
    parser.add_argument('symbols', nargs='*', help='Explicit symbols to fetch')
    args = parser.parse_args()

    snap_date = args.date or date.today().strftime('%Y-%m-%d')
    snapshot_ts = pd.Timestamp.now(tz='UTC')
    bucket = os.environ.get('GCS_BUCKET', '')

    log.info("Earnings Options Fetch Job")
    log.info("  Date      : %s", snap_date)
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  GCS       : %s", bucket or 'disabled')

    # Resolve tickers
    if args.symbols:
        tickers = [s.upper() for s in args.symbols]
    elif bucket:
        tickers = load_active_tickers_from_gcs(bucket, snap_date)
        log.info("  Loaded %d tickers from GCS strategy CSVs", len(tickers))
    else:
        tickers = load_active_tickers_from_local(snap_date)
        log.info("  Loaded %d tickers from local CSVs", len(tickers))

    if args.limit:
        tickers = tickers[:args.limit]

    if not tickers:
        log.info("No active tickers for %s — exiting", snap_date)
        return

    all_frames = []
    errors = []

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i: i + BATCH_SIZE]
        log.info("  Batch %d-%d / %d: %s",
                 i + 1, min(i + BATCH_SIZE, len(tickers)), len(tickers), batch)

        for symbol in batch:
            try:
                df = fetch_options_for_symbol(symbol)
                if df.empty:
                    continue

                df = normalize_for_sql(df, snapshot_ts)
                if df.empty:
                    continue

                all_frames.append(df)

                if is_cloud_sql_configured():
                    upsert_dataframe(
                        df, 'earnings_options_snapshots',
                        ['symbol', 'snapshot_ts', 'option_type', 'expiration', 'strike'],
                    )

            except Exception as e:
                log.error("    ✗ %s: %s", symbol, e)
                errors.append(symbol)

    # Write combined daily snapshot to GCS
    if all_frames and bucket:
        combined = pd.concat(all_frames, ignore_index=True)
        ts_str = snapshot_ts.strftime('%Y%m%d_%H%M%S')
        upload_dataframe_as_parquet(
            combined, bucket,
            f"raw/options/earnings/earnings_options_{ts_str}.parquet",
        )
        log.info("✓ Combined snapshot (%d rows) backed up to GCS", len(combined))

    if errors:
        log.warning("Failed symbols (%d): %s", len(errors), errors[:20])
        if len(errors) == len(tickers):
            sys.exit(1)

    log.info("Done. Processed %d symbols.", len(tickers) - len(errors))


if __name__ == '__main__':
    main()
