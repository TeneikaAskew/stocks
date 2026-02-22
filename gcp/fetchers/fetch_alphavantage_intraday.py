#!/usr/bin/env python3
"""
Cloud Run Job: Fetch AlphaVantage 1-min historical intraday → Cloud SQL + GCS.

Replaces the GitHub Actions workflow fetch-alphavantage-intraday-monthly.yml.
Scheduled on the 1st of each month by Cloud Scheduler.

Usage:
    python -m gcp.fetchers.fetch_alphavantage_intraday --symbol SPY
    python -m gcp.fetchers.fetch_alphavantage_intraday --symbol ALL --start-date 2026-01-01
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import bulk_insert_dataframe, execute_sql, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet, parquet_exists_in_gcs

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)

SYMBOLS = ['SPY', 'IWM', 'QQQ']
AV_BASE_URL = 'https://www.alphavantage.co/query'
# Rate limits: 5 calls/min on free tier; 75/min on premium
CALL_INTERVAL_SECS = 13


def get_api_keys() -> list:
    """Collect all available AlphaVantage API keys from environment."""
    keys = []
    primary = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if primary:
        keys.append(primary)
    # Support backup keys: ALPHA_VANTAGE_API_KEY_2, _3, _4, _5
    for i in range(2, 6):
        k = os.environ.get(f'ALPHA_VANTAGE_API_KEY_{i}', '')
        if k:
            keys.append(k)
    return keys


def get_trading_months(start_date: str, end_date: str) -> list:
    """Return list of (year, month) tuples covering the date range."""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append((current.year, current.month))
        current = (current + pd.offsets.MonthBegin(1))
    return months


def fetch_month(symbol: str, year: int, month: int, api_key: str) -> Optional[pd.DataFrame]:
    """Fetch one month of 1-minute data from AlphaVantage."""
    month_str = f"{year}-{month:02d}"
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': symbol,
        'interval': '1min',
        'month': month_str,
        'outputsize': 'full',
        'datatype': 'json',
        'apikey': api_key,
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            log.warning("    AV error for %s %s: %s", symbol, month_str, data['Error Message'])
            return None
        if 'Note' in data:
            log.warning("    AV rate limit for %s %s", symbol, month_str)
            return None
        if 'Information' in data:
            log.warning("    AV info: %s", data['Information'])
            return None

        ts_key = 'Time Series (1min)'
        if ts_key not in data:
            log.warning("    No time series data for %s %s", symbol, month_str)
            return None

        records = []
        for ts, values in data[ts_key].items():
            records.append({
                'ts': pd.Timestamp(ts),
                'open':   float(values['1. open']),
                'high':   float(values['2. high']),
                'low':    float(values['3. low']),
                'close':  float(values['4. close']),
                'volume': int(values['5. volume']),
            })

        df = pd.DataFrame(records)
        df['ticker'] = symbol
        df['interval'] = '1min'
        df['data_source'] = 'alphavantage'
        return df.sort_values('ts').reset_index(drop=True)

    except Exception as e:
        log.error("    Request error for %s %s: %s", symbol, year, e)
        return None


def process_symbol(
    symbol: str,
    start_date: str,
    end_date: str,
    api_keys: list,
    bucket: str,
    force: bool,
):
    """Fetch all months for a symbol and write to Cloud SQL + GCS."""
    months = get_trading_months(start_date, end_date)
    log.info("  %s: %d months (%s → %s)", symbol, len(months), start_date, end_date)

    key_idx = 0
    call_count = 0
    last_call_time = 0.0
    inserted_total = 0

    for year, month in months:
        month_str = f"{year}-{month:02d}"
        gcs_path = f"raw/{symbol.lower()}/intraday/{symbol.lower()}_av_1min_{year}{month:02d}.parquet"

        # Skip if already in GCS and not forcing
        if not force and bucket and parquet_exists_in_gcs(bucket, gcs_path):
            log.info("    %s: already in GCS, skipping", month_str)
            continue

        # Rate limiting
        elapsed = time.time() - last_call_time
        if elapsed < CALL_INTERVAL_SECS:
            time.sleep(CALL_INTERVAL_SECS - elapsed)

        api_key = api_keys[key_idx % len(api_keys)]
        df = fetch_month(symbol, year, month, api_key)
        last_call_time = time.time()
        call_count += 1

        # Rotate key on rate limit detection
        if df is None and call_count % 5 == 0:
            key_idx += 1
            log.info("    Rotating to API key %d", key_idx + 1)

        if df is None or df.empty:
            continue

        # Localize timestamps to UTC
        if df['ts'].dt.tz is None:
            df['ts'] = df['ts'].dt.tz_localize('America/New_York').dt.tz_convert('UTC')

        log.info("    %s: %d bars", month_str, len(df))

        # Write to Cloud SQL
        if is_cloud_sql_configured():
            bulk_insert_dataframe(df, 'market_data_intraday', chunksize=5000)
            inserted_total += len(df)

        # Backup to GCS
        if bucket:
            upload_dataframe_as_parquet(df, bucket, gcs_path)
            log.info("    ✓ backed up to GCS")

    log.info("  %s complete: %d rows inserted", symbol, inserted_total)


def main():
    parser = argparse.ArgumentParser(description='Fetch AV intraday → Cloud SQL + GCS')
    parser.add_argument('--symbol', default='ALL',
                        help='Symbol to fetch or ALL (SPY IWM QQQ)')
    parser.add_argument('--start-date', default=None,
                        help='Start date YYYY-MM-DD. Defaults to first of previous month.')
    parser.add_argument('--end-date', default=None,
                        help='End date YYYY-MM-DD. Defaults to today.')
    parser.add_argument('--interval', default='1min',
                        help='Interval (only 1min supported for now)')
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch even if data already exists in GCS')
    args = parser.parse_args()

    # Default date range: previous month → today
    today = date.today()
    first_of_prev_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    start_date = args.start_date or first_of_prev_month.strftime('%Y-%m-%d')
    end_date = args.end_date or today.strftime('%Y-%m-%d')
    bucket = os.environ.get('GCS_BUCKET', '')

    api_keys = get_api_keys()
    if not api_keys:
        log.error("No ALPHA_VANTAGE_API_KEY set. Exiting.")
        sys.exit(1)

    symbols = SYMBOLS if args.symbol == 'ALL' else [args.symbol.upper()]

    log.info("AlphaVantage Intraday Fetch Job")
    log.info("  Symbols   : %s", symbols)
    log.info("  Date range: %s → %s", start_date, end_date)
    log.info("  API keys  : %d available", len(api_keys))
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  GCS       : %s", bucket or 'disabled')

    errors = []
    for symbol in symbols:
        try:
            process_symbol(symbol, start_date, end_date, api_keys, bucket, args.force)
        except Exception as e:
            log.error("  ✗ %s failed: %s", symbol, e)
            errors.append(symbol)

    if errors:
        log.error("Failed: %s", errors)
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
