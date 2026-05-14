#!/usr/bin/env python3
"""
One-off deep OHLCV backfill for specific tickers.

Calls AV TIME_SERIES_DAILY_ADJUSTED with outputsize=full and writes
ALL returned bars to market_data_daily (idempotent upsert). Unlike
the standard fetch_market_data._run_backfill which uses smart-switch
and may not always fetch full depth, this one always pulls full
history.

Used when a ticker's earnings_history extends further back than its
market_data_daily, leaving reaction rows uncomputable. Example: MSFT
has 121 quarters of EPS history but only 40 computed reactions
because market_data_daily only goes back ~10 years for MSFT.

Usage:
    python -m scripts.deep_backfill_ticker MSFT META MRVL HIMS CRCL
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcp.database import upsert_dataframe, query_to_dataframe
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE = 'https://www.alphavantage.co/query'


def deep_backfill(ticker: str, api_key: str) -> int:
    """Pull full AV history for a ticker and upsert to market_data_daily.

    Returns the number of rows upserted (or -1 on error).
    """
    log.info("Fetching AV TIME_SERIES_DAILY_ADJUSTED for %s (outputsize=full)…", ticker)
    try:
        r = requests.get(AV_BASE, params={
            'function':   'TIME_SERIES_DAILY_ADJUSTED',
            'symbol':     ticker,
            'outputsize': 'full',
            'apikey':     api_key,
            'datatype':   'json',
        }, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("%s: AV request failed: %s", ticker, e)
        return -1

    msg = data.get('Note') or data.get('Information') or data.get('Error Message')
    if msg:
        log.warning("%s: AV warning: %s", ticker, msg)

    series = data.get('Time Series (Daily)', {})
    if not series:
        log.warning("%s: AV returned no time series data", ticker)
        return 0

    rows = []
    for date_str, bar in series.items():
        try:
            rows.append({
                'ticker': ticker,
                'date':   datetime.strptime(date_str, '%Y-%m-%d').date(),
                'open':   float(bar['1. open']),
                'high':   float(bar['2. high']),
                'low':    float(bar['3. low']),
                'close':  float(bar['5. adjusted close']),
                'volume': int(float(bar['6. volume'])),
            })
        except (KeyError, ValueError):
            continue

    df = pd.DataFrame(rows)
    if df.empty:
        return 0

    df = df.sort_values('date')
    log.info("  %s: %d bars %s..%s",
             ticker, len(df),
             df['date'].iloc[0], df['date'].iloc[-1])

    # Idempotent upsert — won't create duplicates if some bars exist.
    n = upsert_dataframe(df, 'market_data_daily', ['ticker', 'date'])
    log.info("  %s: upserted %d rows", ticker, n)
    return n


def main():
    tickers = [t.upper() for t in sys.argv[1:]]
    if not tickers:
        tickers = ['MSFT', 'META', 'MRVL', 'HIMS', 'CRCL']
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY') or os.environ.get('AV_API_KEY')
    if not api_key:
        log.error("AV_API_KEY not set"); sys.exit(1)

    log.info("Deep backfilling %d tickers: %s", len(tickers), tickers)
    total = 0
    for t in tickers:
        n = deep_backfill(t, api_key)
        if n > 0:
            total += n

    # Show what we have now
    log.info("=" * 60)
    log.info("Coverage after backfill:")
    sql = """
        SELECT ticker, COUNT(*) AS bars, MIN(date) AS first_bar, MAX(date) AS last_bar
        FROM market_data_daily
        WHERE ticker = ANY(:t)
        GROUP BY ticker
        ORDER BY ticker
    """
    df = query_to_dataframe(sql, {'t': tickers})
    for _, row in df.iterrows():
        log.info("  %s: %d bars (%s..%s)",
                 row['ticker'], row['bars'], row['first_bar'], row['last_bar'])

    log.info("Total upserted: %d rows", total)


if __name__ == '__main__':
    main()
