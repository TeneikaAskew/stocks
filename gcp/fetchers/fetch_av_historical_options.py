#!/usr/bin/env python3
"""
Cloud Run Job: Fetch daily AV HISTORICAL_OPTIONS and write to GCS + Cloud SQL.

Replaces the GitHub Actions workflow fetch-alphavantage-options-daily.yml
for the Cloud SQL write path.  The GitHub Actions workflow continues to write
local parquets to GCS; this job writes the same data to Cloud SQL with
data_source='alphavantage' so consumers can query it directly.

Scheduled by Cloud Scheduler after market close (e.g., 10 PM ET weekdays).

Usage:
    python -m gcp.fetchers.fetch_av_historical_options [--tickers ALL] [--date YYYY-MM-DD]
"""

import argparse
import logging
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'
TICKERS = ['SPY', 'IWM', 'QQQ', 'SPX']
_av_cfg = AlphaVantageConfig()


def fetch_av_options(ticker: str, fetch_date: str, api_key: str) -> pd.DataFrame:
    """
    Fetch end-of-day options chain from AV HISTORICAL_OPTIONS for one ticker/date.

    Returns normalized DataFrame ready for etf_options_snapshots, or empty on error.
    """
    symbol = ticker
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol':   symbol,
        'date':     fetch_date,
        'apikey':   api_key,
        'datatype': 'json',
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if data.get('message') != 'success' or data.get('endpoint') != 'Historical Options':
            log.warning("  AV options: unexpected response for %s %s: %s",
                        ticker, fetch_date, data.get('message', data.get('Information', '')))
            return pd.DataFrame()

        records = data.get('data', [])
        if not records:
            log.info("  AV options: no contracts for %s %s", ticker, fetch_date)
            return pd.DataFrame()

        df = pd.DataFrame(records)
        return _normalize_av_response(df, ticker, fetch_date)

    except Exception as e:
        log.error("  AV options fetch failed for %s %s: %s", ticker, fetch_date, e)
        return pd.DataFrame()


def _normalize_av_response(df: pd.DataFrame, ticker: str, fetch_date: str) -> pd.DataFrame:
    """Normalize raw AV HISTORICAL_OPTIONS JSON response to etf_options_snapshots schema."""
    out = df.copy()

    # Coerce numeric columns
    numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
               'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
    for col in numeric:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')

    # snapshot_ts at 23:00 UTC (EOD marker, distinct from yahooquery intraday)
    out['snapshot_ts'] = pd.Timestamp(f"{fetch_date}T23:00:00Z")
    out['snapshot_date'] = pd.to_datetime(fetch_date).date()
    out['market_session'] = 'EOD'
    out['ticker'] = ticker.upper()
    out['data_source'] = 'alphavantage'

    # option_type normalisation
    if 'type' in out.columns:
        out['option_type'] = out['type'].str.lower().map({'call': 'calls', 'put': 'puts'})
    elif 'option_type' in out.columns:
        out['option_type'] = out['option_type'].str.lower()

    # Column renames from AV JSON keys
    rename = {
        'contractID':   'contract_symbol',
        'expiration':   'expiration',
        'last':         'last_price',
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})

    keep = [
        'ticker', 'snapshot_ts', 'snapshot_date', 'market_session',
        'contract_symbol', 'option_type', 'expiration', 'strike',
        'bid', 'ask', 'mark', 'last_price', 'volume', 'open_interest',
        'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho',
        'data_source',
    ]
    out = out[[c for c in keep if c in out.columns]]
    out = out.dropna(subset=['option_type', 'expiration', 'strike'])
    return out


def process_ticker(ticker: str, fetch_date: str, bucket: str, api_key: str,
                    skip_existing: bool = False):
    """Fetch AV options for one ticker/date → Cloud SQL + GCS."""
    if skip_existing and is_cloud_sql_configured():
        from gcp.database import query_to_dataframe
        hit = query_to_dataframe(
            "SELECT 1 FROM etf_options_snapshots "
            "WHERE ticker = :t AND snapshot_date = :d AND data_source = 'alphavantage' LIMIT 1",
            {"t": ticker, "d": fetch_date},
        )
        if not hit.empty:
            log.info("  %s %s already ingested — skipping", ticker, fetch_date)
            return

    log.info("  Fetching %s options for %s...", ticker, fetch_date)

    df = fetch_av_options(ticker, fetch_date, api_key)
    if df.empty:
        log.warning("    No options data returned for %s %s", ticker, fetch_date)
        return

    log.info("    %d contracts received", len(df))

    # Dedupe on the unique constraint so ON CONFLICT DO UPDATE never tries to
    # update the same row twice in one batch (AV occasionally returns duplicate
    # contracts within the same response — dates 2017-09-15, 2020-06-22 etc.).
    conflict_cols = ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    before = len(df)
    df = df.drop_duplicates(subset=conflict_cols, keep='last')
    if len(df) < before:
        log.info("    deduped %d → %d rows", before, len(df))

    if is_cloud_sql_configured():
        upsert_dataframe(df, 'etf_options_snapshots', conflict_cols)
        log.info("    ✓ upserted to Cloud SQL")

    if bucket:
        upload_dataframe_as_parquet(
            df, bucket,
            f"raw/{ticker.lower()}/options/"
            f"{ticker.lower()}_av_options_{fetch_date.replace('-', '')}.parquet",
        )


def _weekday_range(start: date, end: date) -> list[str]:
    """Return YYYY-MM-DD strings for all weekdays in [start, end] inclusive."""
    out = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon-Fri
            out.append(cur.strftime('%Y-%m-%d'))
        cur += timedelta(days=1)
    return out


def main():
    import time

    parser = argparse.ArgumentParser(
        description='Fetch daily AV HISTORICAL_OPTIONS to Cloud SQL + GCS')
    parser.add_argument('--tickers', default='ALL',
                        help='Space-separated tickers or ALL')
    parser.add_argument('--date', default=None,
                        help='Single date to fetch (YYYY-MM-DD). Defaults to today. '
                             'Ignored if --start-date / --end-date are provided.')
    parser.add_argument('--start-date', default=None,
                        help='Backfill range start (YYYY-MM-DD, inclusive).')
    parser.add_argument('--end-date', default=None,
                        help='Backfill range end (YYYY-MM-DD, inclusive). Defaults to today.')
    parser.add_argument('--skip-existing', action='store_true', default=False,
                        help='Skip (ticker, date) pairs already in Cloud SQL. '
                             'Automatically enabled when --start-date is provided.')
    args = parser.parse_args()

    # Resolve date list: range mode wins if either bound is given.
    is_range_mode = bool(args.start_date or args.end_date)
    if is_range_mode:
        start = date.fromisoformat(args.start_date) if args.start_date else date.today()
        end = date.fromisoformat(args.end_date) if args.end_date else date.today()
        if start > end:
            log.error("start-date must be <= end-date")
            sys.exit(2)
        fetch_dates = _weekday_range(start, end)
        log.info("Backfill range: %s → %s (%d weekdays)", start, end, len(fetch_dates))
    else:
        fetch_dates = [args.date or date.today().strftime('%Y-%m-%d')]

    # Auto-enable --skip-existing in range/backfill mode.
    skip_existing = args.skip_existing or is_range_mode

    bucket = os.environ.get('GCS_BUCKET', '')
    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    tickers = TICKERS if args.tickers == 'ALL' else args.tickers.upper().split()

    log.info("Fetch AV Historical Options Job")
    log.info("  Dates   : %d date(s)", len(fetch_dates))
    log.info("  Tickers : %s", tickers)
    log.info("  SQL     : %s", 'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  GCS     : %s", bucket or 'disabled')
    log.info("  AV key  : %s", 'set' if api_key else 'MISSING')

    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch options")
        sys.exit(1)

    errors = []
    total_calls = 0
    for fetch_date in fetch_dates:
        for ticker in tickers:
            if total_calls > 0:
                time.sleep(_av_cfg.delay_between_calls)
            total_calls += 1
            try:
                process_ticker(ticker, fetch_date, bucket, api_key,
                               skip_existing=skip_existing)
            except Exception as e:
                log.error("  ✗ %s %s failed: %s", ticker, fetch_date, e)
                errors.append(f"{ticker}/{fetch_date}")

    if errors:
        log.error("Failed (%d): first 20 = %s", len(errors), errors[:20])
        sys.exit(1)
    log.info("Done. %d AV calls across %d dates × %d tickers.",
             total_calls, len(fetch_dates), len(tickers))


if __name__ == '__main__':
    main()
