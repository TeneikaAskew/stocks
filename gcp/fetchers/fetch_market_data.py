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
        # Required to get current-day bars. Without it AV returns
        # historical-only — `month=2026-04` with default entitlement
        # gave 0 bars for 2026-04-30 even mid-session.
        'entitlement': 'realtime',
        'extended_hours': 'true',
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

    # ──────────────────────────────────────────────────────────────────────
    # Strat fields: classify the latest daily candle, detect any in-force
    # combo, compute a daily+weekly FTFC score. Without these, the LLM
    # pipeline's strat snapshot returns ftfc_score=0.0 for any ticker
    # whose `premarket-brief` Cloud Run job hasn't run (e.g. one-off
    # backfills like AVGO).
    try:
        from lib.strat import StratClassifier

        # Build OHLC frame the classifier expects.
        ohlc = enriched.rename(columns={'Open': 'Open', 'High': 'High',
                                        'Low': 'Low', 'Close': 'Close'})
        clf = StratClassifier()
        # Daily candle
        labels = clf.classify_series(ohlc[['Open', 'High', 'Low', 'Close']])
        last_candle = labels.iloc[-1]
        # Combo detection
        combos = clf.detect_combos(ohlc[['Open', 'High', 'Low', 'Close']], labels)
        last_combo = None
        if not combos.empty:
            last_combo_row = combos.iloc[-1]
            last_combo = (last_combo_row.get('combo')
                          if isinstance(last_combo_row, pd.Series)
                          else None)

        # Weekly resample for FTFC. With daily-only data we can build
        # '1d' and '1w'; intraday timeframes are absent here.
        # Override weights so 1d + 1w sum to 1.0.
        df_dt = enriched.copy()
        df_dt['date'] = df['date'].values  # retain date col from raw frame
        df_dt = df_dt.set_index(pd.to_datetime(df_dt['date']))
        weekly = df_dt[['Open', 'High', 'Low', 'Close']].resample('W').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last',
        }).dropna()
        ftfc_inputs = {'1d': df_dt[['Open', 'High', 'Low', 'Close']]}
        if len(weekly) >= 2:
            ftfc_inputs['1w'] = weekly
        ftfc_score, ftfc_dir, _labels = clf.calculate_ftfc(
            ftfc_inputs, weights={'1d': 0.7, '1w': 0.3},
        )

        if last_candle and last_candle != 'X':
            row['strat_candle'] = str(last_candle)
        if last_combo:
            row['strat_combo'] = str(last_combo)[:30]
        row['ftfc_score'] = float(ftfc_score) if ftfc_score is not None else 0.0
        row['ftfc_direction'] = str(ftfc_dir or 'mixed')[:10]
        # `strat_setup` is true when FTFC aligns directionally and a
        # combo is in force — the `premarket-brief` definition.
        row['strat_setup'] = bool(
            last_combo and abs(ftfc_score or 0.0) >= 0.3
        )
    except Exception as e:
        log.warning("    Strat compute failed for %s: %s", ticker, e)

    # ──────────────────────────────────────────────────────────────────────
    # Pre-market context: 4 AM - 9:30 AM ET extended-hours bars from
    # market_data_intraday for fetch_date. Surfaces pre_high/pre_low/
    # pre_vwap/pre_volume/gap_pct/pre_range_atr so the LLM analyst
    # (and strat_levels engine) can calibrate triggers to today's
    # actual pre-market range, not just yesterday's session H/L.
    try:
        from lib.indicators import calculate_premarket_context
        # Pull today's intraday bars (extended hours included)
        intraday_sql = """
            SELECT ts, open, high, low, close, volume
              FROM market_data_intraday
             WHERE ticker = :ticker
               AND ts >= CAST(:fd AS DATE)
               AND ts <  CAST(:fd AS DATE) + INTERVAL '1 day'
             ORDER BY ts
        """
        intraday = query_to_dataframe(
            intraday_sql, {'ticker': ticker.upper(), 'fd': fetch_date}
        )
        if not intraday.empty:
            prev_close = None
            atr14 = None
            try:
                prev_close = float(df['Close'].iloc[-2]) if len(df) >= 2 else None
            except Exception:
                pass
            try:
                atr14 = float(last.get('atr_14')) if last.get('atr_14') is not None else None
            except Exception:
                pass

            pm = calculate_premarket_context(
                times=intraday['ts'],
                open_=intraday['open'],
                high=intraday['high'],
                low=intraday['low'],
                close=intraday['close'],
                volume=intraday['volume'],
                prev_close=prev_close,
                atr14=atr14,
            )
            if pm['bar_count'] > 0:
                if pm['pre_high'] is not None: row['pre_high'] = pm['pre_high']
                if pm['pre_low'] is not None: row['pre_low'] = pm['pre_low']
                if pm['pre_vwap'] is not None: row['pre_vwap'] = pm['pre_vwap']
                if pm['pre_volume'] is not None: row['pre_volume'] = pm['pre_volume']
                if pm['gap_pct'] is not None: row['gap_pct'] = pm['gap_pct']
                if pm['pre_range_atr'] is not None: row['pre_range_atr'] = pm['pre_range_atr']
                log.info("    ✓ pre-market context computed (%d bars)", pm['bar_count'])
            else:
                log.info("    no pre-market bars for %s on %s (likely weekend / holiday)",
                         ticker, fetch_date)
    except Exception as e:
        log.warning("    Pre-market compute failed for %s: %s", ticker, e)

    upsert_dataframe(pd.DataFrame([row]), 'market_data_daily', ['ticker', 'date'])
    log.info("    ✓ daily indicators + strat computed (%d bars context)", len(df))


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


def _earnings_tickers_in_window(
    days_back: int,
    days_ahead: int,
    top_n: int = 25,
) -> list[str]:
    """Resolve **top-N** tickers reporting earnings within [today-back, today+ahead].

    Used to extend the always-on watchlist with single-name catalyst
    tickers so the historical-earnings-reaction signal in the ranker
    has daily bars to measure against.

    Ranking — optionable names by market cap descending. Non-optionable
    earnings names (no listed contracts) and rows missing market_cap fall
    to the bottom; we still keep them if there's room under ``top_n`` so
    a thin earnings week doesn't starve the union.

    Why a cap: AlphaVantage allows 150 req/min on the current tier, and
    each ticker costs ~3 calls (intraday + daily + supporting). The full
    earnings calendar can return 200+ tickers, blowing through the
    minute budget before the loop reaches IWM/QQQ/SPY — those silently
    skip with empty AV responses, leaving the core tickers stale. The
    cap stays well under the budget.

    Args:
        days_back / days_ahead: symmetric window around today.
        top_n: max tickers to return. Default 25; ``0`` disables the
            cap and returns the full set (legacy behaviour, NOT
            recommended for the daily Cloud Run Job).
    """
    if days_back <= 0 and days_ahead <= 0:
        return []
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []

    # Aggregate per ticker. UW liquidity signals (stock_volume,
    # options_volume, is_s_p_500) outrank market_cap because market_cap is
    # only filled on UW rows, while many UW rows ALSO have stock_volume.
    # An SP500 name with high options volume is the canonical "tradeable
    # earnings ticker" — exactly what we want the daily fetcher to backfill.
    # NULLS LAST on every signal so AV-only / EW-only rows sink without
    # disappearing entirely.
    sql = """
        SELECT ticker,
               BOOL_OR(COALESCE(has_options, false))   AS optionable,
               BOOL_OR(COALESCE(is_s_p_500, false))    AS sp500,
               MAX(stock_volume)                       AS stock_volume,
               MAX(options_volume)                     AS options_volume,
               MAX(market_cap)                         AS market_cap
        FROM earnings_calendar
        WHERE earnings_date BETWEEN
            CURRENT_DATE - (:back || ' days')::interval AND
            CURRENT_DATE + (:ahead || ' days')::interval
        GROUP BY ticker
        ORDER BY optionable      DESC,
                 sp500           DESC NULLS LAST,
                 options_volume  DESC NULLS LAST,
                 stock_volume    DESC NULLS LAST,
                 market_cap      DESC NULLS LAST,
                 ticker
    """
    if top_n and top_n > 0:
        sql += '\n        LIMIT :top_n'

    params: dict = {'back': days_back, 'ahead': days_ahead}
    if top_n and top_n > 0:
        params['top_n'] = top_n

    try:
        df = query_to_dataframe(sql, params)
    except Exception as e:
        log.warning("earnings ticker lookup failed: %s", e)
        return []
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df['ticker'].tolist()]


def main():
    parser = argparse.ArgumentParser(description='Fetch daily market data to Cloud SQL + GCS')
    parser.add_argument('--tickers', default='ALL',
                        help='Space-separated tickers or ALL')
    parser.add_argument('--date', default=None,
                        help='Date to fetch (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--earnings-window-days', type=int,
                        default=int(os.environ.get('EARNINGS_WINDOW_DAYS', '0')),
                        help=('Augment ticker list with anyone reporting earnings within N '
                              'days before AND after today (symmetric window). 0 disables.'))
    parser.add_argument('--max-tickers', type=int,
                        default=int(os.environ.get('MAX_TICKERS', '300')),
                        help='Safety cap on total ticker count (default: 300).')
    parser.add_argument('--max-earnings-tickers', type=int,
                        default=int(os.environ.get('MAX_EARNINGS_TICKERS', '25')),
                        help=('Within --earnings-window-days, only the top N earnings '
                              'names by market cap (optionable first) are added. Keeps '
                              'AV rate-limit budget reserved for core + watchlist. 0 = '
                              'no cap (legacy unbounded behaviour). Default: 25.'))
    args = parser.parse_args()

    # Use ET (market timezone), not the container's UTC. The 23:00 ET cron
    # fires at 03:00–04:00 UTC the NEXT calendar day, so a UTC-based
    # date.today() resolves to tomorrow — fetcher then asks AV for tomorrow's
    # bars (none exist; market hasn't opened yet), filter on line ~104
    # discards everything, write_intraday_to_sql gets empty df, nothing
    # is persisted. Symptom: cron exits 0, but market_data_intraday goes
    # stale. See docs/incidents/2026-05-01-fetch-market-data-tz-bug.md.
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    fetch_date = args.date or datetime.now(_ET).date().strftime('%Y-%m-%d')
    bucket = os.environ.get('GCS_BUCKET', '')
    av_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    tickers = TICKERS if args.tickers == 'ALL' else args.tickers.upper().split()

    # Union watchlist (alert_config.json → "watchlist") so curated names get
    # daily bars even when their earnings are out of window.
    if args.tickers == 'ALL':
        from gcp.fetchers._watchlist import load_watchlist
        wl_added = [t for t in load_watchlist() if t not in tickers]
        if wl_added:
            log.info("  Adding %d watchlist tickers: %s", len(wl_added), wl_added)
            tickers.extend(wl_added)

    if args.earnings_window_days > 0:
        earnings = _earnings_tickers_in_window(
            args.earnings_window_days,
            args.earnings_window_days,
            top_n=args.max_earnings_tickers,
        )
        added = [t for t in earnings if t not in tickers]
        if added:
            log.info("  Adding %d earnings tickers (±%dd window): %s",
                     len(added), args.earnings_window_days,
                     added[:10] + (['...'] if len(added) > 10 else []))
            tickers.extend(added)

    if len(tickers) > args.max_tickers:
        log.warning("  Ticker count %d exceeds max-tickers cap %d; truncating",
                    len(tickers), args.max_tickers)
        tickers = tickers[:args.max_tickers]

    log.info("Fetch Market Data Job")
    log.info("  Date          : %s", fetch_date)
    log.info("  Total tickers : %d", len(tickers))
    log.info("  Earnings win  : %s",
             f"±{args.earnings_window_days}d" if args.earnings_window_days else "off")
    log.info("  SQL           : %s", 'yes' if is_cloud_sql_configured() else 'NO (env vars missing)')
    log.info("  GCS           : %s", bucket or 'disabled')
    log.info("  AV key        : %s", 'yes' if av_api_key else 'NO (required for all data sources)')

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
