#!/usr/bin/env python3
"""
Cloud Run Job: Fetch daily market data and write to Cloud SQL + GCS.

Replaces the GitHub Actions workflow fetch-market-data.yml.
Scheduled by Cloud Scheduler at 5 PM ET (22:00 UTC) weekdays.

Usage:
    python -m gcp.fetchers.fetch_market_data [--tickers ALL] [--date YYYY-MM-DD]
"""

import argparse
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)

TICKERS = ['IWM', 'SPY', 'QQQ', 'SPX']


def fetch_minute_data(ticker: str, fetch_date: str) -> pd.DataFrame:
    """Fetch 1-minute OHLCV bars from Yahoo Finance for a specific date."""
    import yfinance as yf

    symbol = '^GSPC' if ticker == 'SPX' else ticker
    try:
        df = yf.download(
            symbol,
            period='5d',
            interval='1m',
            progress=False,
            prepost=False,
            auto_adjust=True,
        )
        if df.empty:
            return pd.DataFrame()

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Filter to the requested date
        df.index = pd.to_datetime(df.index)
        target = pd.to_datetime(fetch_date).date()
        df = df[df.index.date == target]
        df['ticker'] = ticker
        return df
    except Exception as e:
        log.error("  yfinance error for %s: %s", ticker, e)
        return pd.DataFrame()


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate all technical indicators using lib.indicators."""
    from lib.indicators import add_all_indicators

    if df.empty or len(df) < 2:
        return df

    # Ensure Close column
    if 'Close' not in df.columns:
        for alt in ('close', 'Last', 'Adj Close'):
            if alt in df.columns:
                df = df.rename(columns={alt: 'Close'})
                break

    return add_all_indicators(df, close_col='Close')


def build_daily_row(ticker: str, minute_df: pd.DataFrame, fetch_date: str) -> dict:
    """Aggregate 1-minute bars to a single daily OHLCV row with indicators."""
    if minute_df.empty:
        return {}

    row = {
        'ticker': ticker,
        'date': pd.to_datetime(fetch_date).date(),
        'open': float(minute_df['Open'].iloc[0]),
        'high': float(minute_df['High'].max()),
        'low': float(minute_df['Low'].min()),
        'close': float(minute_df['Close'].iloc[-1]),
        'volume': int(minute_df['Volume'].sum()),
        'data_source': 'yfinance_1min',
    }

    # Add indicators from the last bar (calculated on minute data)
    enriched = calculate_indicators(minute_df)
    last = enriched.iloc[-1]

    indicator_cols = [
        'RSI_14', 'EMA9', 'EMA21', 'ATR_14', 'VWAP', 'RVOL',
        'OBV', 'StochRSI_K', 'StochRSI_D',
        'Consecutive_Up', 'Consecutive_Down', 'Price_vs_VWAP',
    ]
    col_map = {
        'RSI_14': 'rsi_14', 'EMA9': 'ema_9', 'EMA21': 'ema_21',
        'ATR_14': 'atr_14', 'VWAP': 'vwap', 'RVOL': 'rvol',
        'OBV': 'obv', 'StochRSI_K': 'stoch_rsi_k', 'StochRSI_D': 'stoch_rsi_d',
        'Consecutive_Up': 'consecutive_up', 'Consecutive_Down': 'consecutive_down',
        'Price_vs_VWAP': 'price_vs_vwap',
    }
    for src_col, dest_col in col_map.items():
        if src_col in last.index and pd.notna(last[src_col]):
            row[dest_col] = float(last[src_col])

    return row


def write_intraday_to_sql(ticker: str, df: pd.DataFrame, fetch_date: str):
    """Write 1-minute bars to market_data_intraday."""
    if df.empty:
        return

    out = df.copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is None:
        out.index = out.index.tz_localize('America/New_York').tz_convert('UTC')

    out['ts'] = out.index
    out['ticker'] = ticker
    out['interval'] = '1min'
    out['data_source'] = 'yfinance'

    col_map = {'Open': 'open', 'High': 'high', 'Low': 'low',
               'Close': 'close', 'Volume': 'volume'}
    out = out.rename(columns={k: v for k, v in col_map.items() if k in out.columns})
    keep = ['ticker', 'interval', 'ts', 'open', 'high', 'low', 'close', 'volume', 'data_source']
    out = out[[c for c in keep if c in out.columns]]
    out = out.drop_duplicates(subset=['ticker', 'interval', 'ts'])

    upsert_dataframe(out, 'market_data_intraday', ['ticker', 'interval', 'ts'])
    log.info("    ✓ intraday: %d rows for %s", len(out), ticker)


def process_ticker(ticker: str, fetch_date: str, bucket: str):
    """Full pipeline for one ticker: fetch → enrich → write SQL + GCS."""
    log.info("  Processing %s for %s...", ticker, fetch_date)

    minute_df = fetch_minute_data(ticker, fetch_date)
    if minute_df.empty:
        log.warning("    No minute data for %s on %s", ticker, fetch_date)
        return

    log.info("    Fetched %d minute bars", len(minute_df))

    # Write intraday to Cloud SQL
    write_intraday_to_sql(ticker, minute_df, fetch_date)

    # Build and write daily row
    daily_row = build_daily_row(ticker, minute_df, fetch_date)
    if daily_row:
        daily_df = pd.DataFrame([daily_row])
        upsert_dataframe(daily_df, 'market_data_daily', ['ticker', 'date'])
        log.info("    ✓ daily row upserted")

    # Back up to GCS
    if bucket:
        upload_dataframe_as_parquet(
            minute_df,
            bucket,
            f"raw/{ticker.lower()}/minute/{ticker.lower()}_minute_{fetch_date.replace('-', '')}.parquet",
        )


def main():
    parser = argparse.ArgumentParser(description='Fetch daily market data to Cloud SQL + GCS')
    parser.add_argument('--tickers', default='ALL',
                        help='Space-separated tickers or ALL')
    parser.add_argument('--date', default=None,
                        help='Date to fetch (YYYY-MM-DD). Defaults to today.')
    args = parser.parse_args()

    fetch_date = args.date or date.today().strftime('%Y-%m-%d')
    bucket = os.environ.get('GCS_BUCKET', '')
    tickers = TICKERS if args.tickers == 'ALL' else args.tickers.upper().split()

    log.info("Fetch Market Data Job")
    log.info("  Date    : %s", fetch_date)
    log.info("  Tickers : %s", tickers)
    log.info("  SQL     : %s", 'yes' if is_cloud_sql_configured() else 'NO (env vars missing)')
    log.info("  GCS     : %s", bucket or 'disabled')

    errors = []
    for ticker in tickers:
        try:
            process_ticker(ticker, fetch_date, bucket)
        except Exception as e:
            log.error("  ✗ %s failed: %s", ticker, e)
            errors.append(ticker)

    if errors:
        log.error("Failed tickers: %s", errors)
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
