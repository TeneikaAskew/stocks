#!/usr/bin/env python3
"""
Pre-market refresh fetcher — runs at 8:30 AM ET, before the 8:45 brief.

Targets a small set of tickers (today's earnings reporters + watchlist),
fetches today's pre-market bars from AlphaVantage, and UPSERTs the
``pre_high / pre_low / pre_vwap / pre_volume / gap_pct / pre_range_atr``
columns into ``market_data_daily`` for today's date.

Why a separate job from ``fetch_market_data.py``:
  - The nightly 11 PM fetcher captures the full session (including
    pre-market), but that's after the brief has fired.
  - At 8:45 AM brief render time, today's market_data_daily row doesn't
    yet exist, so the brief's LEFT JOIN to gap_pct returns NULL.
  - A targeted ~30-50 ticker refresh at 8:30 AM costs <1 minute of AV
    budget and populates today's gap_pct in time for the 8:45 brief.

Usage:
    python -m gcp.fetchers.fetch_premarket_refresh
    python -m gcp.fetchers.fetch_premarket_refresh --tickers AAPL MSFT
    python -m gcp.fetchers.fetch_premarket_refresh --max-tickers 25

Required env vars:
    ALPHA_VANTAGE_API_KEY
    CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger(__name__)


# ── Universe selection ──────────────────────────────────────────────────────

def resolve_universe(target_date: date, max_tickers: int = 50) -> list[str]:
    """Build the priority ticker set for pre-market refresh.

    Priority order:
      1. Watchlist tickers (always included)
      2. Today's earnings reporters with options flow (UW-confirmed) —
         filtered by ``options_volume > 0`` so we don't waste AV budget
         on long-tail names without tradeable options.

    Capped at ``max_tickers`` to keep the AV call count bounded — the
    AV premium tier allows 1200/day and ~150/min so 50 tickers leaves
    plenty of headroom for the rest of the daily pipeline.
    """
    try:
        from gcp.database import is_cloud_sql_configured, query_to_dataframe
    except ImportError:
        log.warning("gcp.database unavailable — cannot resolve universe")
        return []
    if not is_cloud_sql_configured():
        log.warning("Cloud SQL not configured — cannot resolve universe")
        return []

    universe: dict[str, int] = {}  # ticker → priority bucket (0=watchlist)

    # Watchlist (priority 0)
    try:
        from gcp.fetchers._watchlist import load_watchlist
        for t in load_watchlist():
            universe[t.upper()] = 0
    except Exception as e:
        log.warning("Watchlist load failed: %s", e)

    # Today's earnings tickers with options flow (priority 1)
    try:
        sql = """
            SELECT ticker, MAX(options_volume) AS opt_vol,
                   MAX(market_cap)            AS mcap
              FROM earnings_calendar
             WHERE earnings_date = :d
               AND COALESCE(options_volume, 0) > 0
             GROUP BY ticker
             ORDER BY (COALESCE(MAX(options_volume), 0) + 1)
                      * (COALESCE(MAX(market_cap), 0) / 1e9 + 1) DESC
             LIMIT :lim
        """
        df = query_to_dataframe(sql, {'d': target_date,
                                       'lim': max_tickers})
        for tk in df['ticker'].tolist():
            tk = str(tk).upper()
            if tk not in universe:
                universe[tk] = 1
    except Exception as e:
        log.warning("Earnings universe lookup failed: %s", e)

    # Yesterday's AMC reporters (priority 2) — their reaction shows in
    # today's pre-market, so we need today's bars for them too.
    try:
        prior = target_date - timedelta(days=1)
        # Walk back over weekends/holidays — find most recent weekday
        while prior.weekday() >= 5:
            prior -= timedelta(days=1)
        sql_amc = """
            SELECT DISTINCT ticker FROM earnings_calendar
             WHERE earnings_date = :d
               AND earnings_time = 'postmarket'
               AND COALESCE(options_volume, 0) > 0
        """
        df_amc = query_to_dataframe(sql_amc, {'d': prior})
        for tk in df_amc['ticker'].tolist():
            tk = str(tk).upper()
            if tk not in universe:
                universe[tk] = 2
    except Exception as e:
        log.warning("Yesterday-AMC universe lookup failed: %s", e)

    # Cap (watchlist always included; trim earnings tail)
    if len(universe) > max_tickers:
        sorted_tk = sorted(universe.items(), key=lambda kv: kv[1])
        universe = dict(sorted_tk[:max_tickers])

    return sorted(universe.keys())


# ── Pre-market computation ──────────────────────────────────────────────────

def _prev_close_from_db(ticker: str, fetch_date: date) -> float | None:
    """Most recent regular-session close prior to ``fetch_date``.

    The 11pm-yesterday market_data_daily row has yesterday's close
    already, so a simple backward lookup is enough.
    """
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return None
    sql = """
        SELECT close
          FROM market_data_daily
         WHERE ticker = :tk
           AND date < :d
         ORDER BY date DESC
         LIMIT 1
    """
    try:
        df = query_to_dataframe(sql, {'tk': ticker, 'd': fetch_date})
        if df.empty:
            return None
        v = df['close'].iloc[0]
        return float(v) if pd.notna(v) else None
    except Exception:
        return None


def compute_premarket_for_ticker(ticker: str, fetch_date: date,
                                  api_key: str) -> dict | None:
    """Fetch today's intraday bars from AV and return pre-market metrics.

    Returns a dict with keys ``pre_high pre_low pre_vwap pre_volume
    gap_pct pre_range_atr`` (any of which may be None) plus ``ticker``
    and ``date``. Returns None if the AV fetch fails or no bars are in
    the pre-market window.
    """
    from gcp.fetchers.fetch_market_data import fetch_minute_data
    from lib.indicators import calculate_premarket_context

    iso_date = fetch_date.strftime('%Y-%m-%d')
    df = fetch_minute_data(ticker, iso_date, api_key)
    if df.empty:
        log.info("  %s: no AV intraday bars for %s", ticker, iso_date)
        return None

    prev_close = _prev_close_from_db(ticker, fetch_date)

    # `times` must be a Series so calculate_premarket_context's tz-aware
    # path runs (DatetimeIndex falls to a per-row Python loop that builds
    # a default-int-index Series, which then fails to align with OHLCV).
    times_series = df.index.to_series().reset_index(drop=True)
    pm = calculate_premarket_context(
        times=times_series,
        open_=df['Open'].reset_index(drop=True),
        high=df['High'].reset_index(drop=True),
        low=df['Low'].reset_index(drop=True),
        close=df['Close'].reset_index(drop=True),
        volume=df['Volume'].reset_index(drop=True),
        prev_close=prev_close,
        atr14=None,  # Not needed for the brief embed; can be filled tonight
    )
    if pm.get('bar_count', 0) <= 0:
        log.info("  %s: 0 pre-market bars for %s (early run, weekend, or holiday)",
                 ticker, iso_date)
        return None

    return {
        'ticker': ticker,
        'date': fetch_date,
        'pre_high': pm.get('pre_high'),
        'pre_low': pm.get('pre_low'),
        'pre_vwap': pm.get('pre_vwap'),
        'pre_volume': pm.get('pre_volume'),
        'gap_pct': pm.get('gap_pct'),
    }


# ── Persist (UPSERT only the pre_* columns) ─────────────────────────────────

def upsert_premarket(rows: list[dict]) -> int:
    """UPSERT today's pre-market columns into market_data_daily.

    If today's row exists (rare at 8:30am — only if a manual run already
    populated it), UPDATE the pre_* columns only. If it doesn't exist,
    INSERT a row with only the pre_* fields populated; full OHLC will
    fill tonight at 11pm.

    Returns the number of rows touched.
    """
    if not rows:
        return 0
    try:
        from gcp.database import get_engine
    except ImportError:
        log.warning("gcp.database unavailable — cannot persist")
        return 0

    import sqlalchemy
    eng = get_engine()
    sql = sqlalchemy.text("""
        INSERT INTO market_data_daily
            (ticker, date, pre_high, pre_low, pre_vwap, pre_volume, gap_pct)
        VALUES
            (:ticker, :date, :pre_high, :pre_low, :pre_vwap, :pre_volume, :gap_pct)
        ON CONFLICT (ticker, date) DO UPDATE SET
            pre_high   = COALESCE(EXCLUDED.pre_high,   market_data_daily.pre_high),
            pre_low    = COALESCE(EXCLUDED.pre_low,    market_data_daily.pre_low),
            pre_vwap   = COALESCE(EXCLUDED.pre_vwap,   market_data_daily.pre_vwap),
            pre_volume = COALESCE(EXCLUDED.pre_volume, market_data_daily.pre_volume),
            gap_pct    = COALESCE(EXCLUDED.gap_pct,    market_data_daily.gap_pct)
    """)
    n = 0
    with eng.begin() as conn:
        for r in rows:
            conn.execute(sql, r)
            n += 1
    return n


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S',
    )

    parser = argparse.ArgumentParser(
        description="Pre-market refresh: fetch today's pre-market bars "
                    "for earnings + watchlist tickers, write gap_pct.")
    parser.add_argument('--tickers', nargs='*', default=None,
                        help='Override universe with explicit tickers')
    parser.add_argument('--max-tickers', type=int,
                        default=int(os.environ.get('PREMARKET_MAX_TICKERS', '50')),
                        help='Cap on universe size (default 50)')
    parser.add_argument('--date', default=None,
                        help='Date to refresh (YYYY-MM-DD). Default: today.')
    args = parser.parse_args()

    target = (datetime.strptime(args.date, '%Y-%m-%d').date()
              if args.date else date.today())

    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set — cannot fetch")
        sys.exit(1)

    if args.tickers:
        universe = [t.upper() for t in args.tickers]
        log.info("Override universe: %d tickers", len(universe))
    else:
        universe = resolve_universe(target, max_tickers=args.max_tickers)
        log.info("Resolved universe: %d tickers (target_date=%s)",
                 len(universe), target)

    if not universe:
        log.warning("No tickers to refresh — exiting cleanly")
        return

    rows = []
    for tk in universe:
        result = compute_premarket_for_ticker(tk, target, api_key)
        if result:
            rows.append(result)

    log.info("Computed pre-market for %d/%d tickers", len(rows), len(universe))

    n = upsert_premarket(rows)
    log.info("Upserted %d rows into market_data_daily for %s", n, target)


if __name__ == '__main__':
    main()
