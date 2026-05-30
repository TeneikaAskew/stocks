#!/usr/bin/env python3
"""
Cloud Run Job: Fetch daily market data and write to Cloud SQL.

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
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured

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


def fetch_daily_from_av(ticker: str, fetch_date: str, api_key: str,
                        allow_fallback: bool = True) -> dict:
    """
    Fetch daily OHLCV + adjusted_close from AlphaVantage TIME_SERIES_DAILY_ADJUSTED.

    Uses outputsize=compact (last 100 trading days) for the nightly update.
    Returns a dict of price fields, or {} on any error.

    ``allow_fallback`` (default True): when ``fetch_date`` itself has no AV
    entry, fall back to the most recent prior trading day. This is correct
    for the normal path where intraday bars confirm ``fetch_date`` was a
    real trading session. Callers in the no-intraday path MUST pass
    ``allow_fallback=False`` — without intraday we can't distinguish a
    holiday from a trading day locally, and the prior-day fallback would
    write a holiday-dated row carrying the previous session's prices.
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
        # (handles weekends / holidays where today has no trading data yet) —
        # but ONLY when allow_fallback is set (see docstring).
        row_data = ts.get(fetch_date)
        if not row_data and allow_fallback:
            for d in sorted(ts.keys(), reverse=True):
                if d <= fetch_date:
                    row_data = ts[d]
                    log.info("    AV daily: using %s data for requested date %s", d, fetch_date)
                    break

        if not row_data:
            log.warning("    AV daily: no matching date for %s on %s%s",
                        ticker, fetch_date,
                        "" if allow_fallback else " (exact-match required)")
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

    Returns ``{}`` only when BOTH sources are empty. When intraday is missing
    but ``av_ohlcv`` is present, the row is still built from the AV daily
    endpoint — just without the intraday-derived VWAP fields. This keeps the
    daily OHLCV + downstream indicators populated for tickers AV has no
    1-min coverage for (the long tail of earnings names), which the prior
    `if minute_df.empty: return {}` short-circuit silently dropped.
    """
    has_minute = not minute_df.empty
    if not has_minute and not av_ohlcv:
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

    # VWAP and Price_vs_VWAP are intraday session values — only computable
    # when 1-min bars are present. Skipped (left NULL) for the AV-daily-only
    # path; that's correct, VWAP genuinely can't be derived without intraday.
    if not has_minute:
        return row

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


# Single source of truth for the indicator-to-SQL-column mapping lives in
# gcp/database.py. Imported here so the live fetcher and the one-shot
# migrate_to_gcp.py can never drift on rename.
from gcp.database import DAILY_INDICATOR_TO_SQL_COLUMN as _DAILY_IND_TO_SQL


def compute_and_upsert_daily_indicators(ticker: str, fetch_date: str):
    """
    Query the last 250 daily bars from Cloud SQL, compute all multi-day
    technical indicators on the full series, then upsert today's values back.

    Calling this after the OHLCV row for fetch_date has been upserted ensures
    that every indicator uses the correct daily-close series (not 1-min bars).
    """
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

    # add_all_indicators skips VWAP/ORB when 'Time' column is absent — correct for daily.
    # As of 2026-05-27 volatility_{5,20}d and high_low_spread{,_pct} are also produced
    # by add_all_indicators (see IndicatorConfig.volatility_periods); no manual recompute.
    enriched = add_all_indicators(df, close_col='Close')

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


def process_ticker(ticker: str, fetch_date: str, av_api_key: str):
    """Full pipeline for one ticker: fetch → enrich → write to Cloud SQL.

    Intraday-optional: AV has no 1-min coverage for the long tail of
    earnings tickers, and a missing-intraday day used to short-circuit
    the whole function — no daily OHLCV row, no indicators. Now, when
    intraday is absent we still pull the AV *daily* endpoint (exact-date
    match only) and persist the daily row + indicators from it.
    """
    log.info("  Processing %s for %s...", ticker, fetch_date)

    # 1. Fetch 1-min bars from AlphaVantage TIME_SERIES_INTRADAY
    minute_df = fetch_minute_data(ticker, fetch_date, av_api_key)
    has_intraday = not minute_df.empty
    if has_intraday:
        log.info("    Fetched %d minute bars", len(minute_df))
        # 2. Write intraday bars to Cloud SQL
        write_intraday_to_sql(ticker, minute_df, fetch_date)
    else:
        log.warning("    No minute data for %s on %s — trying AV daily endpoint",
                    ticker, fetch_date)

    # 3. Fetch daily OHLCV from AlphaVantage. With intraday present, the
    #    prior-day fallback is safe (intraday confirms it's a trading day).
    #    Without intraday, require an exact fetch_date match so a holiday
    #    doesn't get a row stamped with the prior session's prices.
    av_ohlcv = fetch_daily_from_av(ticker, fetch_date, av_api_key,
                                   allow_fallback=has_intraday)
    if av_ohlcv:
        log.info("    AV daily: open=%.2f close=%.2f adj=%.2f",
                 av_ohlcv['open'], av_ohlcv['close'], av_ohlcv['adjusted_close'])
    elif has_intraday:
        log.info("    AV daily unavailable; aggregating from AV intraday bars")
    else:
        # No intraday AND no exact-date AV daily — genuinely nothing for
        # this ticker on this date (illiquid name, or a non-trading day).
        log.warning("    No intraday and no AV daily for %s on %s — skipping",
                    ticker, fetch_date)
        return

    # 4. Build and upsert daily OHLCV row (no multi-day indicators yet)
    daily_row = build_daily_row(ticker, minute_df, fetch_date, av_ohlcv or None)
    if daily_row:
        daily_df = pd.DataFrame([daily_row])
        upsert_dataframe(daily_df, 'market_data_daily', ['ticker', 'date'])
        log.info("    ✓ daily OHLCV upserted (source: %s)", daily_row.get('data_source'))

        # 5. Compute multi-day indicators from the full daily series in Cloud SQL
        compute_and_upsert_daily_indicators(ticker, fetch_date)


def _earnings_tickers_in_window(
    days_back: int,
    days_ahead: int,
    top_n: int | None = None,
    require_options: bool = True,
) -> list[str]:
    """Resolve tickers reporting earnings within [today-back, today+ahead].

    Used to extend the always-on watchlist with single-name catalyst
    tickers so the historical-earnings-reaction signal in the ranker
    has daily bars to measure against.

    Filtering:
      - ``require_options=True`` (default): only return tickers with at
        least one source row marking ``has_options=true``. EW and UW
        populate this flag; AV and Yahoo never do, so this is effectively
        "EW or UW listed it as options-tradable" — the right cut for an
        earnings-options pipeline. In a typical 7d window this collapses
        a ~3,500-ticker universe to ~500.
      - ``require_options=False``: legacy behaviour, returns all reporters
        (sorted by the same liquidity signals). Use for non-options
        signal coverage.

    DO NOT use ``is_s_p_500`` as a hard filter — that flag is only ever
    populated by Unusual Whales (other sources leave it NULL), and even
    UW leaves it NULL on many rows including JPM/UNH/MCK. The
    ``has_options`` filter strictly contains every is_s_p_500=true name
    in the window plus another ~450 optionable non-S&P500 names.

    Capacity (CLAUDE.md §0.2): with require_options=True, the universe
    is ~500 tickers in a typical 7d window. AV is 150 RPM × ~3 calls
    per ticker = ~10 min — fits comfortably in the 30-min Cloud Run
    task-timeout. ``top_n=None`` (default) disables the cap because the
    options filter is the real cap.

    Args:
        days_back / days_ahead: symmetric window around today.
        top_n: max tickers to return. ``None`` (default) disables the
            cap. Set explicitly for ad-hoc runs that want a subset.
        require_options: if True, only return tickers where at least one
            data_source marked ``has_options=true``.
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
    # An optionable name with high options volume is the canonical
    # "tradeable earnings ticker" — exactly what we want the daily
    # fetcher to backfill. NULLS LAST on every signal so AV-only /
    # EW-only rows sink without disappearing entirely.
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
    """
    if require_options:
        sql += '        HAVING BOOL_OR(COALESCE(has_options, false)) = true\n'
    sql += """        ORDER BY optionable      DESC,
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


# ────────────────────────────────────────────────────────────
# Backfill mode (--backfill) — historical OHLCV bootstrap.
#
# Targets tickers in earnings_history that the brief would actually
# render (options_volume > 0 + stock_volume >= 500K, OR watchlist).
# Smart-switches between AV outputsize=full and =compact so we do not
# re-pull tickers that are already current. Caps written rows at 10y
# per the BACKFILL_LOOKBACK_DAYS policy.
# ────────────────────────────────────────────────────────────

BACKFILL_LOOKBACK_DAYS = 365 * 10
BACKFILL_DEPTH_THRESHOLD_BARS = 1500   # ~6y; below this needs full pull
# Per-call delay between AV requests in --backfill mode. Default 13s ≈ 5 RPM
# (free-tier safe). Premium AV (75-150 RPM) can run at 1s. Override via
# AV_BACKFILL_SLEEP_SECS env var. Float seconds.
BACKFILL_AV_SLEEP_SECS_DEFAULT = 13.0


def _backfill_targets() -> list:
    """Tickers in earnings_history that the brief would render, with
    their current OHLCV state. Returns (ticker, bar_count, max_date).

    Default filter requires the ticker to be currently active in
    earnings_calendar (options_volume > 0, stock_volume >= 500k).

    Set ``BACKFILL_ALL_HISTORY=true`` to bypass that filter and target
    EVERY ticker in earnings_history — used when backfilling for a
    multi-quarter reactions recompute, where past reporters need OHLCV
    even if they're not in the current options/stock-volume window.

    With ``BACKFILL_ALL_HISTORY=true`` the union also includes tickers
    that already exist in ``market_data_daily`` but are NOT in
    earnings_history. Audit 2026-05-30 found 152 such orphans — real
    S&P 500 names (AAL, AMP, ARI…) that joined the active universe
    via ``earnings_calendar`` ~35 days prior and only ever got a single
    bar fetched. Without this union they're invisible to --backfill
    and stay broken indefinitely.
    """
    if not is_cloud_sql_configured():
        return []
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []

    backfill_all = os.environ.get('BACKFILL_ALL_HISTORY', '').strip().lower() == 'true'

    if backfill_all:
        # Skip the eligible filter — every earnings_history ticker counts,
        # PLUS every ticker already in market_data_daily (catches
        # universe-expansion orphans not yet in earnings_history).
        sql = """
            WITH targets AS (
                SELECT DISTINCT ticker FROM earnings_history
              UNION
                SELECT DISTINCT ticker FROM market_data_daily
            )
            SELECT t.ticker,
                   COALESCE(mdd.n, 0)        AS bar_count,
                   mdd.max_date              AS max_date
              FROM targets t
              LEFT JOIN (
                  SELECT ticker, COUNT(*) AS n, MAX(date) AS max_date
                    FROM market_data_daily
                   GROUP BY ticker
              ) mdd ON mdd.ticker = t.ticker
             ORDER BY t.ticker
        """
    else:
        sql = """
            WITH eligible AS (
                SELECT DISTINCT ticker FROM earnings_calendar
                 WHERE COALESCE(options_volume, 0) > 0
                   AND COALESCE(stock_volume,   0) >= 500000
              UNION
                SELECT ticker FROM watchlists
                 WHERE COALESCE(in_brief, false) OR COALESCE(in_insight, false)
            ),
            eh_eligible AS (
                SELECT DISTINCT eh.ticker FROM earnings_history eh
                 WHERE eh.ticker IN (SELECT ticker FROM eligible)
            )
            SELECT eh.ticker,
                   COALESCE(mdd.n, 0)        AS bar_count,
                   mdd.max_date              AS max_date
              FROM eh_eligible eh
              LEFT JOIN (
                  SELECT ticker, COUNT(*) AS n, MAX(date) AS max_date
                    FROM market_data_daily
                   GROUP BY ticker
              ) mdd ON mdd.ticker = eh.ticker
             ORDER BY eh.ticker
        """
    df = query_to_dataframe(sql)
    if df.empty:
        return []
    return [(r['ticker'], int(r['bar_count']), r['max_date'])
            for _, r in df.iterrows()]


def _pick_backfill_outputsize(bar_count: int, max_date,
                              today_et: date) -> str | None:
    """Decide AV outputsize — or skip entirely. Returns 'full',
    'compact', or None (skip)."""
    if bar_count == 0:
        return 'full'
    days_stale = (today_et - max_date).days if max_date else 99999
    if bar_count >= BACKFILL_DEPTH_THRESHOLD_BARS:
        if days_stale <= 1:
            return None
        if days_stale <= 90:
            return 'compact'
        return 'full'
    return 'full'  # partial history → bootstrap to full depth


def _av_get_full_daily_series(ticker: str, api_key: str,
                              outputsize: str) -> pd.DataFrame:
    """Pull the entire daily series response from AV TIME_SERIES_DAILY_ADJUSTED.

    Uses adjusted endpoint so split-adjusted close is available
    downstream. Returns a DataFrame with columns
        ticker, date, open, high, low, close, volume
    or empty on any error. The caller is responsible for filtering
    to the lookback cap and upserting to market_data_daily.
    """
    av_symbol = AV_SYMBOL_MAP.get(ticker, ticker)
    if not av_symbol or not api_key:
        return pd.DataFrame()
    try:
        resp = requests.get(AV_BASE_URL, params={
            'function': 'TIME_SERIES_DAILY_ADJUSTED',
            'symbol': av_symbol,
            'outputsize': outputsize,
            'datatype': 'json',
            'apikey': api_key,
        }, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if 'Information' in data or 'Error Message' in data or 'Note' in data:
            log.warning("    AV daily error for %s: %s",
                        ticker, data.get('Information') or data.get('Error Message'))
            return pd.DataFrame()
        ts = data.get('Time Series (Daily)') or {}
        if not ts:
            return pd.DataFrame()
        rows = []
        for d_str, v in ts.items():
            rows.append({
                'ticker': ticker,
                'date':   pd.to_datetime(d_str).date(),
                'open':   float(v['1. open']),
                'high':   float(v['2. high']),
                'low':    float(v['3. low']),
                'close':  float(v['4. close']),
                'volume': int(v['6. volume']),
            })
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values('date').reset_index(drop=True)
    except Exception as e:
        log.warning("    AV daily fetch failed for %s: %s", ticker, e)
        return pd.DataFrame()


def _run_backfill() -> None:
    """--backfill mode: pull historical daily bars for every ticker in
    earnings_history that the brief would render but lacks depth.

    Skip + smart-switch keep this idempotent and cheap on re-runs:
    already-current tickers do zero AV calls."""
    from zoneinfo import ZoneInfo
    today_et = datetime.now(ZoneInfo("America/New_York")).date()
    av_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')

    if not is_cloud_sql_configured():
        raise RuntimeError("Cloud SQL not configured — backfill cannot proceed")
    if not av_api_key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY not set — backfill cannot proceed")

    targets = _backfill_targets()
    plan = [(t, n, mx, _pick_backfill_outputsize(n, mx, today_et))
            for (t, n, mx) in targets]
    pending = [(t, n, mx, sz) for (t, n, mx, sz) in plan if sz is not None]

    n_full = sum(1 for _, _, _, sz in pending if sz == 'full')
    n_compact = sum(1 for _, _, _, sz in pending if sz == 'compact')
    skipped = len(plan) - len(pending)

    try:
        sleep_secs = float(os.environ.get('AV_BACKFILL_SLEEP_SECS',
                                          BACKFILL_AV_SLEEP_SECS_DEFAULT))
    except ValueError:
        sleep_secs = BACKFILL_AV_SLEEP_SECS_DEFAULT
    if sleep_secs < 0:
        sleep_secs = 0.0

    log.info("Backfill mode")
    log.info("  Eligible targets: %d", len(plan))
    log.info("  Already current (skipped): %d", skipped)
    log.info("  Full pulls (~20y, filtered to 10y on write): %d", n_full)
    log.info("  Compact pulls (last 100 days): %d", n_compact)
    log.info("  AV sleep: %.2fs/call (env=AV_BACKFILL_SLEEP_SECS)", sleep_secs)
    log.info("  Estimated wall clock: %d min",
             int(len(pending) * sleep_secs) // 60 + 1)

    if not pending:
        log.info("Nothing to do — all eligible tickers are already current.")
        return

    cutoff = today_et - timedelta(days=BACKFILL_LOOKBACK_DAYS)
    upserted = 0
    failures = []

    # Lazy import to avoid pulling SQL deps when --backfill is not used
    from gcp.database import upsert_dataframe

    import time as _time
    for i, (ticker, bar_count, max_dt, outputsize) in enumerate(pending):
        log.info("  [%d/%d] %s (have=%d bars, max=%s, mode=%s)",
                 i + 1, len(pending), ticker, bar_count, max_dt, outputsize)
        df = _av_get_full_daily_series(ticker, av_api_key, outputsize)
        if df.empty:
            failures.append(ticker)
            log.warning("    (no data returned)")
        else:
            df = df[df['date'] >= cutoff]  # enforce 10y cap on write
            if not df.empty:
                upsert_dataframe(df, 'market_data_daily', ['ticker', 'date'])
                upserted += len(df)
                log.info("    %d bars upserted: %s..%s",
                         len(df), df['date'].min(), df['date'].max())
        if i < len(pending) - 1 and sleep_secs > 0:
            _time.sleep(sleep_secs)

    log.info("Backfill done: %d bars upserted across %d tickers",
             upserted, len(pending) - len(failures))
    if failures:
        log.warning("Failures (%d): %s", len(failures), failures[:20])


def _assert_fetch_date_fresh(fetch_date: str, today_et: date | None = None,
                             max_stale_days: int = 5) -> None:
    """Abort if `fetch_date` is more than `max_stale_days` calendar days
    behind today (ET). Defends against the sticky-args latch documented
    in docs/RUNBOOK_BACKFILL.md: a backfill done via
    `gcloud run jobs update --args="--date=..."` (instead of the correct
    `execute --args=...`) leaves the date latched on every subsequent
    scheduled execution, silently producing 8+ days of bad rows.

    A 5-day threshold catches the bug without false-positives on the
    Monday after a long weekend (3 calendar days back) or a holiday
    Tuesday (4 calendar days back).
    """
    if today_et is None:
        from zoneinfo import ZoneInfo
        today_et = datetime.now(ZoneInfo("America/New_York")).date()
    fetch_d = datetime.strptime(fetch_date, '%Y-%m-%d').date()
    stale_days = (today_et - fetch_d).days
    if stale_days > max_stale_days:
        log.error(
            "Aborting: fetch_date=%s is %d calendar days behind today_ET=%s "
            "(threshold: %d). This is almost always a sticky --args latch "
            "from `gcloud run jobs update --args=...`. Run "
            "`gcloud run jobs update fetch-market-data --args='' --region=us-east1` "
            "to clear, then re-dispatch backfills via `execute --args=...`. "
            "See docs/RUNBOOK_BACKFILL.md.",
            fetch_date, stale_days, today_et.strftime('%Y-%m-%d'),
            max_stale_days)
        sys.exit(4)


def _verify_post_fetch_rows(fetch_date: str, tickers: list[str],
                            key_tickers: tuple[str, ...] = ('SPY', 'IWM', 'QQQ'),
                            _query_fn=None) -> None:
    """After the per-ticker loop, confirm that at least one of the key
    tickers (SPY/IWM/QQQ) has a NOT NULL close in market_data_daily for
    fetch_date. Skips on weekends (no market data exists). Holidays may
    produce a single false-positive that the runbook acknowledges.

    Catches the silent-failure mode where AV returns no data and the
    per-ticker loop logs warnings but exits 0 — the bug behind the
    2026-04-14 incident.
    """
    fetch_d = datetime.strptime(fetch_date, '%Y-%m-%d').date()
    if fetch_d.weekday() >= 5:
        return  # weekend; no data expected
    if not set(key_tickers).intersection(t.upper() for t in tickers):
        return  # key tickers weren't in this run's universe
    if not is_cloud_sql_configured():
        return  # local/dev run; nothing to verify
    if _query_fn is None:
        from gcp.database import query_to_dataframe as _query_fn  # type: ignore[no-redef]
    # `ticker = ANY(:tickers)` not `ticker IN :tk`. SQLAlchemy `text()`
    # doesn't auto-expand a tuple bind param to an `IN (...)` list when
    # the underlying driver is pg8000 — Postgres rejects `IN $1` and
    # query_to_dataframe swallows the error to an empty DataFrame, which
    # would force exit 5 on every weekday. The repo's calibrate /
    # reconciler scripts use the same `= ANY(:tickers)` pattern with a
    # native Python list.
    sql = """
        SELECT COUNT(*) AS n FROM market_data_daily
        WHERE ticker = ANY(:tickers)
          AND date = :d
          AND close IS NOT NULL
    """
    df = _query_fn(sql, {'tickers': list(key_tickers), 'd': fetch_date})
    n = int(df.iloc[0]['n']) if not df.empty else 0
    if n == 0:
        log.error(
            "Post-fetch verification failed: 0 rows for %s in "
            "market_data_daily on %s with NOT NULL close. AV may have "
            "returned no data, or the writer silently failed. "
            "See docs/RUNBOOK_BACKFILL.md.",
            list(key_tickers), fetch_date)
        sys.exit(5)


def main():
    parser = argparse.ArgumentParser(description='Fetch daily market data to Cloud SQL')
    parser.add_argument('--tickers', default='ALL',
                        help='Space-separated tickers or ALL')
    parser.add_argument('--date', default=None,
                        help='Date to fetch (YYYY-MM-DD). Defaults to today.')
    parser.add_argument('--earnings-window-days', type=int,
                        default=int(os.environ.get('EARNINGS_WINDOW_DAYS', '0')),
                        help=('Augment ticker list with anyone reporting earnings within N '
                              'days before AND after today (symmetric window). 0 disables.'))
    parser.add_argument('--max-tickers', type=int,
                        default=int(os.environ.get('MAX_TICKERS', '800')),
                        help='Safety cap on total ticker count (default: 800). '
                             'Headroom above the optionable-earnings universe '
                             '(~500/week) + 16 static + watchlist.')
    parser.add_argument('--max-earnings-tickers', type=int,
                        default=int(os.environ.get('MAX_EARNINGS_TICKERS', '0')),
                        help=('Within --earnings-window-days, cap the earnings '
                              'union to the top N (sorted optionable→sp500→'
                              'options_volume→stock_volume→market_cap). '
                              '0 = no cap (default) — relies on the '
                              '--require-options filter to bound the universe. '
                              'AV at 150 RPM × 3 calls/ticker = ~10 min for '
                              '500 names, well within the 30-min timeout.'))
    parser.add_argument('--require-options', action='store_true',
                        default=os.environ.get('REQUIRE_OPTIONS', 'true').lower() != 'false',
                        help=('Filter the earnings union to tickers with '
                              '`has_options=true` from EW or UW. Default: '
                              'true. AV/Yahoo never set this flag, so the '
                              'filter effectively means "EW or UW confirmed '
                              'this is options-tradable around earnings" — '
                              'the right cut for an earnings-options pipeline. '
                              'Set REQUIRE_OPTIONS=false to disable.'))
    parser.add_argument('--backfill', action='store_true',
                        help=('Historical OHLCV backfill mode: pull 10y of daily bars '
                              'for every ticker in earnings_history that has options + '
                              'volume but lacks depth in market_data_daily. Smart-switch '
                              'between AV outputsize=full (bootstrap) and compact (catch-up) '
                              'so we do not waste bandwidth on already-current tickers. '
                              'Skips the intraday + indicator path; only writes daily bars.'))
    args = parser.parse_args()

    if args.backfill:
        return _run_backfill()

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
    _assert_fetch_date_fresh(fetch_date, today_et=datetime.now(_ET).date())
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
        # Asymmetric window: lookahead-only is the actually-actionable
        # cut. Looking back 7d only matters for reaction backfill, which
        # compute_earnings_reactions handles on its own SQL join — the
        # daily fetcher doesn't need to re-pull yesterday's reporters.
        earnings = _earnings_tickers_in_window(
            days_back=0,
            days_ahead=args.earnings_window_days,
            top_n=args.max_earnings_tickers if args.max_earnings_tickers > 0 else None,
            require_options=args.require_options,
        )
        added = [t for t in earnings if t not in tickers]
        if added:
            log.info("  Adding %d earnings tickers (next %dd, options=%s): %s",
                     len(added), args.earnings_window_days,
                     args.require_options,
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
    log.info("  AV key        : %s", 'yes' if av_api_key else 'NO (required for all data sources)')

    errors = []
    for ticker in tickers:
        try:
            process_ticker(ticker, fetch_date, av_api_key)
        except Exception as e:
            log.error("  ✗ %s failed: %s", ticker, e)
            errors.append(ticker)

    if errors:
        log.error("Failed tickers: %s", errors)
        sys.exit(1)

    _verify_post_fetch_rows(fetch_date, tickers)

    log.info("Done.")


if __name__ == '__main__':
    main()
