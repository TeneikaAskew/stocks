#!/usr/bin/env python3
"""
Cloud Run Job: Fetch ETF options snapshots → Cloud SQL + GCS.

Uses AlphaVantage HISTORICAL_OPTIONS for options chain data.
Called by Cloud Scheduler after market close.

Usage:
    python -m gcp.fetchers.fetch_etf_options [--date YYYY-MM-DD] [--tickers IWM SPY QQQ]
"""

import argparse
import logging
import os
import sys
import time as time_module
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

TICKERS = ['IWM', 'SPY', 'QQQ', 'SPX']
RISK_FREE_RATE = 0.045
AV_BASE_URL = 'https://www.alphavantage.co/query'
_av_cfg = AlphaVantageConfig()


def get_market_session() -> str:
    """Classify current time into a named market session."""
    import pytz
    et = pytz.timezone('America/New_York')
    now = datetime.now(et).time()

    from datetime import time
    if now < time(9, 35):
        return 'OPEN_VOLATILE'
    elif now < time(10, 0):
        return 'MORNING_EARLY'
    elif now < time(12, 0):
        return 'MORNING'
    elif now < time(14, 0):
        return 'MIDDAY'
    elif now < time(15, 30):
        return 'AFTERNOON'
    elif now < time(16, 0):
        return 'POWER_HOUR'
    else:
        return 'CLOSE'


def calculate_greeks(row: pd.Series, underlying_price: float, risk_free_rate: float = RISK_FREE_RATE) -> dict:
    """Calculate Black-Scholes Greeks for a single option contract."""
    try:
        from py_vollib.black_scholes import black_scholes
        from py_vollib.black_scholes.greeks.analytical import (
            delta, gamma, theta, vega, rho
        )
        import warnings

        iv = float(row.get('impliedVolatility', 0) or 0)
        if iv <= 0 or iv > 20:
            return {'delta': None, 'gamma': None, 'theta': None, 'vega': None, 'rho': None}

        strike = float(row['strike'])
        expiry = pd.to_datetime(row['expiration'])
        t = max((expiry - pd.Timestamp.now()).days / 365.0, 1/365)
        flag = 'c' if str(row.get('optionType', '')).lower().startswith('c') else 'p'

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return {
                'delta': delta(flag, underlying_price, strike, t, risk_free_rate, iv),
                'gamma': gamma(flag, underlying_price, strike, t, risk_free_rate, iv),
                'theta': theta(flag, underlying_price, strike, t, risk_free_rate, iv),
                'vega':  vega(flag, underlying_price, strike, t, risk_free_rate, iv),
                'rho':   rho(flag, underlying_price, strike, t, risk_free_rate, iv),
            }
    except Exception:
        return {'delta': None, 'gamma': None, 'theta': None, 'vega': None, 'rho': None}


def fetch_options_for_ticker(ticker: str, fetch_date: str, api_key: str) -> pd.DataFrame:
    """Fetch the full options chain for a single ETF ticker via AV HISTORICAL_OPTIONS."""
    if not api_key:
        log.warning("    No AV API key — cannot fetch options for %s", ticker)
        return pd.DataFrame()

    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol': ticker,
        'date': fetch_date,
        'apikey': api_key,
        'datatype': 'json',
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if data.get('message') != 'success' or data.get('endpoint') != 'Historical Options':
            log.warning("    AV options: unexpected response for %s: %s",
                        ticker, data.get('message', data.get('Information', '')))
            return pd.DataFrame()

        records = data.get('data', [])
        if not records:
            log.info("    AV options: no contracts for %s %s", ticker, fetch_date)
            return pd.DataFrame()

        df = pd.DataFrame(records)

        # Coerce numeric columns
        numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
                   'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
        for col in numeric:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Normalize option_type
        if 'type' in df.columns:
            df['optionType'] = df['type'].str.lower().map({'call': 'calls', 'put': 'puts'})
        # Map AV field names
        if 'contractID' in df.columns:
            df['contractSymbol'] = df['contractID']
        if 'last' in df.columns:
            df['lastPrice'] = df['last']
        if 'implied_volatility' in df.columns:
            df['impliedVolatility'] = df['implied_volatility']
        if 'open_interest' in df.columns:
            df['openInterest'] = df['open_interest']

        df['ticker'] = ticker
        df['underlying_price'] = 0.0  # AV doesn't provide underlying in options endpoint
        df['data_source'] = 'alphavantage'
        return df

    except Exception as e:
        log.error("  Error fetching %s options: %s", ticker, e)
        return pd.DataFrame()


def enrich_with_greeks(df: pd.DataFrame) -> pd.DataFrame:
    """Add Greeks columns to the options DataFrame if not already present from AV."""
    if df.empty:
        return df

    # AV HISTORICAL_OPTIONS already provides greeks — skip if present and non-null
    if 'delta' in df.columns and df['delta'].notna().any():
        return df

    greek_rows = []
    for _, row in df.iterrows():
        g = calculate_greeks(row, float(row.get('underlying_price', 0) or 0))
        greek_rows.append(g)

    greek_df = pd.DataFrame(greek_rows, index=df.index)
    return pd.concat([df, greek_df], axis=1)


def normalize_for_sql(df: pd.DataFrame, snapshot_ts: pd.Timestamp, market_session: str) -> pd.DataFrame:
    """Rename columns to match the etf_options_snapshots schema."""
    df = df.copy()

    col_map = {
        'contractSymbol': 'contract_symbol',
        'optionType':     'option_type',
        'lastPrice':      'last_price',
        'percentChange':  'percent_change',
        'openInterest':   'open_interest',
        'impliedVolatility': 'implied_volatility',
        'inTheMoney':     'in_the_money',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    df['snapshot_ts'] = snapshot_ts
    df['snapshot_date'] = snapshot_ts.date()
    df['market_session'] = market_session

    if 'expiration' in df.columns:
        df['expiration'] = pd.to_datetime(df['expiration'], errors='coerce').dt.date

    # Keep only schema columns
    keep = [
        'ticker', 'snapshot_ts', 'snapshot_date', 'market_session',
        'contract_symbol', 'option_type', 'expiration', 'strike', 'in_the_money',
        'bid', 'ask', 'mark', 'last_price', 'change', 'percent_change',
        'volume', 'open_interest', 'implied_volatility',
        'delta', 'gamma', 'theta', 'vega', 'rho',
        'underlying_price', 'data_source',
    ]
    return df[[c for c in keep if c in df.columns]].dropna(
        subset=['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    )


def main():
    parser = argparse.ArgumentParser(description='Fetch ETF options snapshot → Cloud SQL + GCS')
    parser.add_argument('--date', default=None, help='Snapshot date (YYYY-MM-DD)')
    parser.add_argument('--tickers', nargs='+', default=None,
                        help='Tickers to fetch (default: IWM SPY QQQ SPX)')
    args = parser.parse_args()

    snapshot_ts = pd.Timestamp.now(tz='UTC')
    snap_date = args.date or date.today().strftime('%Y-%m-%d')
    tickers = args.tickers or TICKERS
    bucket = os.environ.get('GCS_BUCKET', '')
    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    market_session = get_market_session()

    log.info("ETF Options Fetch Job (AlphaVantage)")
    log.info("  Date      : %s  Session: %s", snap_date, market_session)
    log.info("  Tickers   : %s", tickers)
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  GCS       : %s", bucket or 'disabled')
    log.info("  AV key    : %s", 'set' if api_key else 'MISSING')

    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set — cannot fetch options")
        sys.exit(1)

    all_frames = []
    errors = []

    for i, ticker in enumerate(tickers):
        if i > 0:
            time_module.sleep(_av_cfg.delay_between_calls)
        try:
            log.info("  Fetching %s...", ticker)
            df = fetch_options_for_ticker(ticker, snap_date, api_key)
            if df.empty:
                log.warning("    No data for %s", ticker)
                continue

            df = enrich_with_greeks(df)
            df = normalize_for_sql(df, snapshot_ts, market_session)

            if df.empty:
                log.warning("    No valid rows after normalization for %s", ticker)
                continue

            log.info("    %d contracts", len(df))
            all_frames.append(df)

            # Write per-ticker to Cloud SQL
            if is_cloud_sql_configured():
                upsert_dataframe(
                    df, 'etf_options_snapshots',
                    ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike'],
                )
                log.info("    ✓ SQL upserted")

            # Back up to GCS
            if bucket:
                ts_str = snapshot_ts.strftime('%Y%m%d_%H%M%S')
                upload_dataframe_as_parquet(
                    df, bucket,
                    f"raw/options/etfs/{ticker}_{ts_str}.parquet",
                )

        except Exception as e:
            log.error("  ✗ %s: %s", ticker, e)
            errors.append(ticker)

    # Also write combined snapshot to GCS
    if all_frames and bucket:
        combined = pd.concat(all_frames, ignore_index=True)
        ts_str = snapshot_ts.strftime('%Y%m%d_%H%M%S')
        upload_dataframe_as_parquet(
            combined, bucket,
            f"raw/options/etfs/etf_options_{ts_str}.parquet",
        )

    if errors:
        log.error("Failed tickers: %s", errors)
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
