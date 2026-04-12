#!/usr/bin/env python3
"""
Cloud Run Job: Fetch earnings options snapshots → Cloud SQL + GCS.

Replaces the GitHub Actions workflow fetch-earnings-options.yml.
Scheduled 6 times per day by Cloud Scheduler during market hours.

Active tickers are resolved in priority order:
  1. CLI --symbols override
  2. Cloud SQL earnings_calendar table (tickers with earnings in next 7 days)
  3. GCS-hosted strategy CSV files (fallback)
  4. Local google-apps-script/data/ CSVs (fallback)

Usage:
    python -m gcp.fetchers.fetch_earnings_options [--date YYYY-MM-DD] [--limit 10]
"""

import argparse
import logging
import os
import sys
import io
import time as time_module
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet, download_csv_from_gcs
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'
_av_cfg = AlphaVantageConfig()

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


def load_active_tickers_from_sql(snap_date: str, lookahead_days: int = 7) -> list:
    """Load tickers with upcoming earnings from Cloud SQL earnings_calendar.

    Returns tickers whose earnings_date falls between snap_date and
    snap_date + lookahead_days.  This replaces the CSV-based approach
    as the primary ticker source when Cloud SQL is available.
    """
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []

    end_date = (pd.to_datetime(snap_date) + pd.Timedelta(days=lookahead_days)).strftime('%Y-%m-%d')
    sql = """
        SELECT DISTINCT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN :start AND :end
        ORDER BY ticker
    """
    df = query_to_dataframe(sql, {'start': snap_date, 'end': end_date})
    if df.empty:
        return []
    return df['ticker'].tolist()


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


def fetch_options_for_symbol(symbol: str, fetch_date: str, api_key: str) -> pd.DataFrame:
    """Fetch earnings options chain for a single symbol via AV HISTORICAL_OPTIONS."""
    if not api_key:
        log.warning("    No AV API key — cannot fetch options for %s", symbol)
        return pd.DataFrame()

    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol': symbol,
        'date': fetch_date,
        'apikey': api_key,
        'datatype': 'json',
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if data.get('message') != 'success' or data.get('endpoint') != 'Historical Options':
            msg = data.get('message', data.get('Information', ''))
            if msg:
                log.warning("    AV options: unexpected response for %s: %s", symbol, msg)
            return pd.DataFrame()

        records = data.get('data', [])
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)

        # Coerce numeric columns
        numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
                   'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
        for col in numeric:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Map AV field names to match normalize_for_sql expectations
        if 'type' in df.columns:
            df['optionType'] = df['type'].str.lower().map({'call': 'calls', 'put': 'puts'})
        if 'contractID' in df.columns:
            df['contractSymbol'] = df['contractID']
        if 'last' in df.columns:
            df['lastPrice'] = df['last']
        if 'implied_volatility' in df.columns:
            df['impliedVolatility'] = df['implied_volatility']
        if 'open_interest' in df.columns:
            df['openInterest'] = df['open_interest']

        df['symbol'] = symbol
        df['underlying_price'] = 0.0

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
    df['data_source'] = 'alphavantage'

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
    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')

    log.info("Earnings Options Fetch Job (AlphaVantage)")
    log.info("  Date      : %s", snap_date)
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  GCS       : %s", bucket or 'disabled')
    log.info("  AV key    : %s", 'set' if api_key else 'MISSING')

    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set — cannot fetch options")
        sys.exit(1)

    # Resolve tickers: SQL > GCS CSVs > local CSVs
    if args.symbols:
        tickers = [s.upper() for s in args.symbols]
    elif is_cloud_sql_configured():
        tickers = load_active_tickers_from_sql(snap_date)
        log.info("  Loaded %d tickers from earnings_calendar (SQL)", len(tickers))
        if not tickers and bucket:
            log.info("  SQL returned 0 — falling back to GCS CSVs")
            tickers = load_active_tickers_from_gcs(bucket, snap_date)
            log.info("  Loaded %d tickers from GCS strategy CSVs", len(tickers))
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

        for j, symbol in enumerate(batch):
            if j > 0:
                time_module.sleep(_av_cfg.delay_between_calls)
            try:
                df = fetch_options_for_symbol(symbol, snap_date, api_key)
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
