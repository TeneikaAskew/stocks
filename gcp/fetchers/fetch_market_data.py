#!/usr/bin/env python3
"""
Cloud Run Job: Fetch daily market data and write to Cloud SQL + GCS.

Replaces the GitHub Actions workflow fetch-market-data.yml.
Scheduled by Cloud Scheduler at 5 PM ET (22:00 UTC) weekdays.

Daily OHLCV source: AlphaVantage TIME_SERIES_DAILY_ADJUSTED (split/dividend-adjusted close).
Intraday 1-min source: AlphaVantage TIME_SERIES_INTRADAY (current month).

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
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from gcp.gcs_utils import upload_dataframe_as_parquet

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

TICKERS = ['IWM', 'SPY', 'QQQ', 'SPX']
AV_BASE_URL = 'https://www.alphavantage.co/query'

# AV symbols mapping (same symbol for daily and intraday).
AV_SYMBOL_MAP = {
    'SPY': 'SPY',
    'IWM': 'IWM',
    'QQQ': 'QQQ',
    'SPX': 'SPX',
}


def fetch_minute_data(ticker: str, fetch_date: str, api_key: str) -> pd.DataFrame:
    """Fetch 1-minute OHLCV bars from AlphaVantage TIME_SERIES_INTRADAY.

    Fetches the full current month of data and filters to the requested date.
    Timestamps are returned in naive ET (Eastern Time) as-is from AV.
    """
    av_symbol = AV_SYMBOL_MAP.get(ticker, ticker)
    if not api_key:
        log.warning("    No AV API key — cannot fetch intraday for %s", ticker)
        return pd.DataFrame()

    # AV TIME_SERIES_INTRADAY uses month=YYYY-MM
    month = fetch_date[:7]  # "2026-02-24" → "2026-02"
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': av_symbol,
        'interval': '1min',
        'month': month,
        'outputsize': 'full',
        'adjusted': 'true',
        'apikey': api_key,
        'datatype': 'json',
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            log.error("    AV intraday error for %s: %s", ticker, data['Error Message'])
            return pd.DataFrame()
        if 'Information' in data or 'Note' in data:
            log.warning("    AV intraday rate limit for %s: %s",
                        ticker, data.get('Information', data.get('Note', '')))
            return pd.DataFrame()

        ts_key = 'Time Series (1min)'
        ts = data.get(ts_key, {})
        if not ts:
            log.warning("    AV intraday: no time series for %s month %s", ticker, month)
            return pd.DataFrame()

        df = pd.DataFrame.from_dict(ts, orient='index')
        df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = pd.to_numeric(df[col])
        df['Volume'] = pd.to_numeric(df['Volume']).astype('int64')
        df.index = pd.to_datetime(df.index)
        df.index.name = 'timestamp'
        df = df.sort_index()

        # Filter to the requested date
        target = pd.to_datetime(fetch_date).date()
        df = df[df.index.date == target]

        if df.empty:
            log.warning("    AV intraday: no bars for %s on %s", ticker, fetch_date)
            return pd.DataFrame()

        df['ticker'] = ticker
        log.info("    AV intraday: %d bars for %s on %s", len(df), ticker, fetch_date)
        return df

    except Exception as e:
        log.error("    AV intraday fetch failed for %s: %s", ticker, e)
        return pd.DataFrame()


def fetch_daily_from_av(ticker: str, fetch_date: str, api_key: str) -> dict:
    """
    Fetch daily OHLCV + adjusted_close from AlphaVantage TIME_SERIES_DAILY_ADJUSTED.

    Uses outputsize=compact (last 100 trading days) for the nightly update.
    Returns a dict of price fields, or {} on any error.
    """
    av_symbol = AV_SYMBOL_MAP.get(ticker, ticker)
    if not av_symbol or not api_key:
        return {}

    params = {
        'function': 'TIME_SERIES_DAILY_ADJUSTED',
        'symbol': av_symbol,
        'outputsize': 'compact',
        'datatype': 'json',
        'apikey': api_key,
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            log.warning("    AV daily error for %s: %s", ticker, data['Error Message'])
            return {}
        if 'Information' in data or 'Note' in data:
            log.warning("    AV daily rate limit or info for %s", ticker)
            return {}

        ts = data.get('Time Series (Daily)', {})
        if not ts:
            log.warning("    AV daily: no time series for %s", ticker)
            return {}

        # Find the entry for fetch_date; fall back to the most recent prior day
        # (handles weekends / holidays where today has no trading data yet)
        row_data = ts.get(fetch_date)
        if not row_data:
            for d in sorted(ts.keys(), reverse=True):
                if d <= fetch_date:
                    row_data = ts[d]
                    log.info("    AV daily: using %s data for requested date %s", d, fetch_date)
                    break

        if not row_data:
            log.warning("    AV daily: no matching date for %s on %s", ticker, fetch_date)
            return {}

        return {
            'open':           float(row_data['1. open']),
            'high':           float(row_data['2. high']),
            'low':            float(row_data['3. low']),
            'close':          float(row_data['4. close']),
            'adjusted_close': float(row_data['5. adjusted close']),
            'volume':         int(row_data['6. volume']),
        }

    except Exception as e:
        log.warning("    AV daily fetch failed for %s: %s", ticker, e)
        return {}


def build_daily_row(ticker: str, minute_df: pd.DataFrame, fetch_date: str,
                    av_ohlcv: dict | None = None) -> dict:
    """
    Build a single daily OHLCV row.

    OHLCV source priority:
      1. AlphaVantage TIME_SERIES_DAILY_ADJUSTED (split/dividend-adjusted, canonical)
      2. AV intraday 1-min aggregation (fallback if AV daily unavailable)

    Intraday-derived fields (VWAP, Price_vs_VWAP) are computed from 1-min bars
    and stored as end-of-day snapshot values.  All multi-day indicators (RSI,
    EMA, SMA, MACD, Bollinger, etc.) are computed in a separate step using the
    full daily series from Cloud SQL — see compute_and_upsert_daily_indicators().
    """
    if minute_df.empty:
        return {}

    row: dict = {
        'ticker': ticker,
        'date':   pd.to_datetime(fetch_date).date(),
    }

    if av_ohlcv:
        row.update(av_ohlcv)
        row['data_source'] = 'alphavantage_daily'
    else:
        # Fallback: aggregate from AV intraday 1-min bars
        row.update({
            'open':   float(minute_df['Open'].iloc[0]),
            'high':   float(minute_df['High'].max()),
            'low':    float(minute_df['Low'].min()),
            'close':  float(minute_df['Close'].iloc[-1]),
            'volume': int(minute_df['Volume'].sum()),
            'data_source': 'alphavantage_1min',
        })

    # VWAP and Price_vs_VWAP are intraday session values — compute from 1-min bars
    from lib.indicators import calculate_vwap
    minute_close = minute_df['Close'] if 'Close' in minute_df.columns else minute_df['close']
    minute_high  = minute_df['High']  if 'High'  in minute_df.columns else minute_df['high']
    minute_low   = minute_df['Low']   if 'Low'   in minute_df.columns else minute_df['low']
    minute_vol   = minute_df['Volume'] if 'Volume' in minute_df.columns else minute_df['volume']
    try:
        dates = pd.to_datetime(minute_df.index).date
        vwap_series = calculate_vwap(minute_high, minute_low, minute_close, minute_vol,
                                     pd.Series(dates, index=minute_df.index))
        eod_vwap = float(vwap_series.iloc[-1])
        if pd.notna(eod_vwap) and eod_vwap > 0:
            row['vwap'] = eod_vwap
            eod_close = float(minute_close.iloc[-1])
            row['price_vs_vwap'] = (eod_close - eod_vwap) / eod_vwap * 100.0
    except Exception as e:
        log.debug("  VWAP from 1-min failed for %s: %s", ticker, e)

    return row


# Column mapping: add_all_indicators() output → market_data_daily SQL column
_DAILY_IND_TO_SQL = {
    'RSI14':          'rsi_14',
    'RSI9':           'rsi_9',
    'ATR14':          'atr_14',
    'EMA9':           'ema_9',
    'EMA20':          'ema_20',
    'EMA50':          'ema_50',
    'SMA5':           'ma_5',
    'SMA10':          'ma_10',
    'SMA20':          'ma_20',
    'SMA50':          'ma_50',
    'SMA200':         'sma_200',
    'MACD':           'macd',
    'MACD_Signal':    'macd_signal',
    'MACD_Histogram': 'macd_histogram',
    'BB_Upper':       'bb_upper',
    'BB_Lower':       'bb_lower',
    'BB_Width':       'bb_width',
    'BB_Pct':         'bb_pct',
    'StochRSI_K':     'stoch_rsi_k',
    'StochRSI_D':     'stoch_rsi_d',
    'OBV':            'obv',
    'RVOL':           'rvol',
    'Consecutive_Up':   'consecutive_up',
    'Consecutive_Down': 'consecutive_down',
    'Price_vs_EMA9':    'price_vs_ema9',
    'Price_vs_EMA20':   'price_vs_ema20',
    'volatility_20d':   'volatility_20d',
}


def compute_and_upsert_daily_indicators(ticker: str, fetch_date: str):
    """
    Query the last 250 daily bars from Cloud SQL, compute all multi-day
    technical indicators on the full series, then upsert today's values back.

    Calling this after the OHLCV row for fetch_date has been upserted ensures
    that every indicator uses the correct daily-close series (not 1-min bars).
    """
    import numpy as np
    from lib.indicators import add_all_indicators
    from gcp.database import query_to_dataframe, upsert_dataframe

    sql = """
        SELECT date,
               open  AS "Open",
               high  AS "High",
               low   AS "Low",
               close AS "Close",
               volume AS "Volume"
        FROM market_data_daily
        WHERE ticker = :ticker AND date <= :fetch_date
        ORDER BY date DESC
        LIMIT 250
    """
    df = query_to_dataframe(sql, {'ticker': ticker.upper(), 'fetch_date': fetch_date})
    if df.empty or len(df) < 2:
        log.warning("    Not enough daily history for %s to compute indicators", ticker)
        return

    # Reverse to chronological order (oldest first)
    df = df.iloc[::-1].reset_index(drop=True)

    # add_all_indicators skips VWAP/ORB when 'Time' column is absent — correct for daily
    enriched = add_all_indicators(df, close_col='Close')

    # 20-day annualised historical volatility (not in add_all_indicators)
    enriched['volatility_20d'] = (
        enriched['Close'].pct_change().rolling(20).std() * np.sqrt(252)
    )

    _INT_COLS = {'consecutive_up', 'consecutive_down'}
    last = enriched.iloc[-1]
    row: dict = {'ticker': ticker.upper(), 'date': fetch_date}
    for src, dst in _DAILY_IND_TO_SQL.items():
        val = last.get(src)
        if val is not None and pd.notna(val):
            row[dst] = int(val) if dst in _INT_COLS else float(val)

    upsert_dataframe(pd.DataFrame([row]), 'market_data_daily', ['ticker', 'date'])
    log.info("    ✓ daily indicators computed (%d bars context)", len(df))


def write_intraday_to_sql(ticker: str, df: pd.DataFrame, fetch_date: str):
    """Write 1-minute bars to market_data_intraday."""
    if df.empty:
        return

    out = df.copy()
    out.index = pd.to_datetime(out.index)
    # AV returns naive ET timestamps — strip any tz label if present.
    # ET-as-UTC convention ensures the frontend RTH filter (9:30-16:00 via getUTCHours) works.
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)

    out['ts'] = out.index
    out['ticker'] = ticker
    out['interval'] = '1min'
    out['data_source'] = 'alphavantage'

    col_map = {'Open': 'open', 'High': 'high', 'Low': 'low',
               'Close': 'close', 'Volume': 'volume'}
    out = out.rename(columns={k: v for k, v in col_map.items() if k in out.columns})
    keep = ['ticker', 'interval', 'ts', 'open', 'high', 'low', 'close', 'volume', 'data_source']
    out = out[[c for c in keep if c in out.columns]]
    out = out.drop_duplicates(subset=['ticker', 'interval', 'ts'])

    upsert_dataframe(out, 'market_data_intraday', ['ticker', 'interval', 'ts'])
    log.info("    ✓ intraday: %d rows for %s", len(out), ticker)


def process_ticker(ticker: str, fetch_date: str, bucket: str, av_api_key: str):
    """Full pipeline for one ticker: fetch → enrich → write SQL + GCS."""
    log.info("  Processing %s for %s...", ticker, fetch_date)

    # 1. Fetch 1-min bars from AlphaVantage TIME_SERIES_INTRADAY
    minute_df = fetch_minute_data(ticker, fetch_date, av_api_key)
    if minute_df.empty:
        log.warning("    No minute data for %s on %s", ticker, fetch_date)
        return

    log.info("    Fetched %d minute bars", len(minute_df))

    # 2. Write intraday bars to Cloud SQL
    write_intraday_to_sql(ticker, minute_df, fetch_date)

    # 3. Fetch daily OHLCV from AlphaVantage (primary); fall back to minute aggregation
    av_ohlcv = fetch_daily_from_av(ticker, fetch_date, av_api_key)
    if av_ohlcv:
        log.info("    AV daily: open=%.2f close=%.2f adj=%.2f",
                 av_ohlcv['open'], av_ohlcv['close'], av_ohlcv['adjusted_close'])
    else:
        log.info("    AV daily unavailable; aggregating from AV intraday bars")

    # 4. Build and upsert daily OHLCV row (no multi-day indicators yet)
    daily_row = build_daily_row(ticker, minute_df, fetch_date, av_ohlcv or None)
    if daily_row:
        daily_df = pd.DataFrame([daily_row])
        upsert_dataframe(daily_df, 'market_data_daily', ['ticker', 'date'])
        log.info("    ✓ daily OHLCV upserted (source: %s)", daily_row.get('data_source'))

        # 5. Compute multi-day indicators from the full daily series in Cloud SQL
        compute_and_upsert_daily_indicators(ticker, fetch_date)

    # 6. Back up minute bars to GCS
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
    av_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    tickers = TICKERS if args.tickers == 'ALL' else args.tickers.upper().split()

    log.info("Fetch Market Data Job")
    log.info("  Date      : %s", fetch_date)
    log.info("  Tickers   : %s", tickers)
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO (env vars missing)')
    log.info("  GCS       : %s", bucket or 'disabled')
    log.info("  AV key    : %s", 'yes' if av_api_key else 'NO (required for all data sources)')

    errors = []
    for ticker in tickers:
        try:
            process_ticker(ticker, fetch_date, bucket, av_api_key)
        except Exception as e:
            log.error("  ✗ %s failed: %s", ticker, e)
            errors.append(ticker)

    if errors:
        log.error("Failed tickers: %s", errors)
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
