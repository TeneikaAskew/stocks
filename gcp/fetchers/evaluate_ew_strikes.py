#!/usr/bin/env python3
"""
EW strike verdict evaluator — runs after market close to score how
each Earnings Whispers strike pick played out intraday.

Populates these columns on earnings_calendar (only for rows with
``data_source = 'earnings_whispers'`` and ``strike IS NOT NULL``):
    ew_high_on_day, ew_low_on_day, ew_close_on_day
    ew_strike_verdict   — HIT | MISS | KEPT | ASSIGNED
    ew_strike_move_pct  — signed % move vs strike (high or close depending on strategy)
    ew_minutes_to_hit   — first regular-session minute strike was crossed (NULL if MISS)
    ew_minutes_in_zone  — total regular-session minutes spent on profitable side of strike
    ew_day_change_pct   — open-to-close % move (signed; bullish/bearish bias)

Verdicts depend on the strategy:
    Long Calls / Bull Spreads → HIT if high >= strike, else MISS
    Long Puts  / Bear Spreads → HIT if low <= strike, else MISS
    Covered Calls             → KEPT if close <= strike, else ASSIGNED
    (Strangles / Straddles use a different math — skipped here)

Usage:
    python -m gcp.fetchers.evaluate_ew_strikes                 # yesterday only
    python -m gcp.fetchers.evaluate_ew_strikes --start 2026-04-13 --end 2026-04-30
    python -m gcp.fetchers.evaluate_ew_strikes --force         # re-evaluate even rows already scored

Required env vars:
    ALPHA_VANTAGE_API_KEY (intraday bars)
    CLOUD_SQL_CONNECTION_NAME / DB_USER / DB_PASS / DB_NAME
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

log = logging.getLogger(__name__)


# ── Verdict math ─────────────────────────────────────────────────────────────

def _compute_verdict(strategy: str, strike: float,
                     reg_bars: pd.DataFrame) -> dict:
    """Return verdict + supporting metrics for one (strategy, strike, day).

    `reg_bars` must be 1-min OHLCV restricted to the regular session
    09:30-15:59 ET, indexed by timestamp (ET). Empty bars → all None.
    """
    out = {
        'verdict': None, 'move_pct': None,
        'minutes_to_hit': None, 'minutes_in_zone': None,
        'high': None, 'low': None, 'close': None,
        'day_change_pct': None,
    }
    if reg_bars is None or reg_bars.empty:
        return out

    high = float(reg_bars['High'].max())
    low  = float(reg_bars['Low'].min())
    close = float(reg_bars['Close'].iloc[-1])
    day_open = float(reg_bars['Open'].iloc[0])
    out['high'], out['low'], out['close'] = high, low, close
    if day_open != 0:
        out['day_change_pct'] = round((close - day_open) / day_open * 100, 4)

    # Per-bar in-zone mask depends on strategy direction
    if strategy in ('Long Calls', 'Bull Spreads'):
        # Profitable when underlying high >= strike
        in_zone_mask = reg_bars['High'] >= strike
        if high >= strike:
            out['verdict'] = 'HIT'
            out['move_pct'] = round((high - strike) / strike * 100, 4)
        else:
            out['verdict'] = 'MISS'
            out['move_pct'] = round(-(strike - high) / strike * 100, 4)

    elif strategy in ('Long Puts', 'Bear Spreads'):
        in_zone_mask = reg_bars['Low'] <= strike
        if low <= strike:
            out['verdict'] = 'HIT'
            out['move_pct'] = round(-(strike - low) / strike * 100, 4)
        else:
            out['verdict'] = 'MISS'
            out['move_pct'] = round((low - strike) / strike * 100, 4)

    elif strategy == 'Covered Calls':
        # Seller wants underlying to STAY BELOW strike at close.
        # In-zone (good for seller) = close-of-bar at/below strike.
        in_zone_mask = reg_bars['Close'] <= strike
        if close <= strike:
            out['verdict'] = 'KEPT'
            out['move_pct'] = round(-(strike - close) / strike * 100, 4)
        else:
            out['verdict'] = 'ASSIGNED'
            out['move_pct'] = round((close - strike) / strike * 100, 4)

    else:
        # Strangles, Straddles, etc. need EM math, not strike-cross
        return out

    # Time-to-hit: first bar that's in-zone in the strategy's direction.
    # For Covered Calls "in-zone" is close <= strike — time-to-hit is the
    # first bar that BREACHES (above strike), which is the opposite mask.
    if strategy == 'Covered Calls':
        breach_mask = ~in_zone_mask
        first_breach = breach_mask[breach_mask].index.min() if breach_mask.any() else None
        out['minutes_to_hit'] = (
            int((first_breach - reg_bars.index.min()).total_seconds() // 60)
            if first_breach is not None else None
        )
        out['minutes_in_zone'] = int(in_zone_mask.sum())
    else:
        first_hit = in_zone_mask[in_zone_mask].index.min() if in_zone_mask.any() else None
        out['minutes_to_hit'] = (
            int((first_hit - reg_bars.index.min()).total_seconds() // 60)
            if first_hit is not None else None
        )
        out['minutes_in_zone'] = int(in_zone_mask.sum())

    return out


# ── Main loop ───────────────────────────────────────────────────────────────

def evaluate_range(start: date, end: date, force: bool = False) -> int:
    """Score every EW pick row in [start, end] that hasn't been scored yet
    (or all rows if force=True). Returns rows updated."""
    try:
        from gcp.database import get_engine, query_to_dataframe
        from gcp.fetchers.fetch_market_data import fetch_minute_data
    except ImportError as e:
        log.error("required module unavailable: %s", e)
        return 0

    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set")
        return 0

    where_force = '' if force else 'AND ew_strike_verdict IS NULL'
    df = query_to_dataframe(f"""
        SELECT id, ticker, earnings_date, strategy, strike
          FROM earnings_calendar
         WHERE data_source = 'earnings_whispers'
           AND strike IS NOT NULL
           AND earnings_date BETWEEN :s AND :e
           {where_force}
         ORDER BY earnings_date, ticker
    """, {'s': start, 'e': end})

    if df.empty:
        log.info("No EW rows to score in [%s, %s]", start, end)
        return 0

    log.info("Scoring %d EW picks for %s..%s (force=%s)",
             len(df), start, end, force)

    import sqlalchemy
    eng = get_engine()
    upd = sqlalchemy.text("""
        UPDATE earnings_calendar SET
            ew_high_on_day      = :high,
            ew_low_on_day       = :low,
            ew_close_on_day     = :close,
            ew_strike_verdict   = :verdict,
            ew_strike_move_pct  = :move,
            ew_minutes_to_hit   = :ttl,
            ew_minutes_in_zone  = :iz,
            ew_day_change_pct   = :dchg
         WHERE id = :id
    """)

    n = 0
    # Cache intraday bars per (ticker, date) — many EW rows per day per ticker
    bars_cache: dict = {}
    for _, row in df.iterrows():
        key = (row['ticker'], row['earnings_date'])
        if key not in bars_cache:
            iso = row['earnings_date'].strftime('%Y-%m-%d')
            bars = fetch_minute_data(row['ticker'], iso, api_key)
            if not bars.empty:
                bars = bars.between_time('09:30', '15:59')
            bars_cache[key] = bars

        v = _compute_verdict(row['strategy'], float(row['strike']),
                              bars_cache[key])
        if v['verdict'] is None:
            continue  # unsupported strategy or no bars
        with eng.begin() as conn:
            conn.execute(upd, {
                'id': int(row['id']),
                'high': v['high'], 'low': v['low'], 'close': v['close'],
                'verdict': v['verdict'], 'move': v['move_pct'],
                'ttl': v['minutes_to_hit'],
                'iz': v['minutes_in_zone'],
                'dchg': v['day_change_pct'],
            })
        n += 1

    log.info("Updated %d rows", n)
    return n


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s %(message)s',
        datefmt='%H:%M:%S',
    )
    parser = argparse.ArgumentParser(
        description="Score EW strike picks against intraday bars.")
    parser.add_argument('--start', help='YYYY-MM-DD; default = yesterday')
    parser.add_argument('--end',   help='YYYY-MM-DD; default = yesterday')
    parser.add_argument('--force', action='store_true',
                        help='Re-score rows already scored.')
    args = parser.parse_args()

    if args.start and args.end:
        start = datetime.strptime(args.start, '%Y-%m-%d').date()
        end   = datetime.strptime(args.end,   '%Y-%m-%d').date()
    else:
        # Default: yesterday only
        y = date.today() - timedelta(days=1)
        # Walk back over weekend/holiday
        while y.weekday() >= 5:
            y -= timedelta(days=1)
        start = end = y

    n = evaluate_range(start, end, force=args.force)
    print(f"Updated {n} rows for {start}..{end}")


if __name__ == '__main__':
    main()
