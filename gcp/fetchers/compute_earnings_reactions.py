#!/usr/bin/env python3
"""
Cloud Run Job: Populate earnings_reactions from earnings_history ⨝ market_data_daily.

For each (ticker, fiscal_date_ending) in earnings_history, compute the
timing-aware post-earnings reaction profile:

  - reaction_basis: 'BMO' (pre-market) or 'AMC' (post-market) from
    earnings_history.report_time. Falls back to earnings_calendar's
    earnings_time, then to AMC default if both are missing.
  - reaction_gap_pct: D-open vs D-1-close (BMO) OR D+1-open vs D-close (AMC)
  - reaction_anchor_price: D close (BMO) or D+1 open (AMC)
  - sustain_{3,5,10}d_pct: anchored at reaction_anchor_price
  - direction_consistent_5d: sign(reaction_gap) == sign(sustain_5d)
  - is_reversal_5d: sign flip + |sustain_5d| >= 0.5 * |reaction_gap|
  - pre_earnings_drift_10d_pct: D-1 close vs D-10 close

Upserts to earnings_reactions on (ticker, fiscal_date_ending).

Usage:
    python -m gcp.fetchers.compute_earnings_reactions
    python -m gcp.fetchers.compute_earnings_reactions --tickers AVGO,LLY
    python -m gcp.fetchers.compute_earnings_reactions --dry-run
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, query_to_dataframe, is_cloud_sql_configured
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# Pure-compute layer (testable without DB)
# ────────────────────────────────────────────────────────────

def normalize_timing(
    report_time: Optional[str],
    earnings_time: Optional[str],
    yahoo_report_time: Optional[str] = None,
) -> str:
    """Resolve reaction_basis from up to three timing sources.

    Precedence (verified by user 2026-05-01):
      1. yahoo_report_time (earnings_history.yahoo_report_time) — preferred,
         derived from Yahoo's wire-feed earnings event timestamps. Yahoo
         is more reliable than AV (AV had NVDA 2026-02-25 as pre-market
         but Yahoo correctly identifies it as post-market).
      2. report_time (earnings_history.report_time from AV) — fallback.
      3. earnings_time (earnings_calendar.earnings_time, majority vote
         across data_sources) — last fallback for upcoming reports.
      4. AMC default — when nothing is known.
    """
    for v in (yahoo_report_time, report_time, earnings_time):
        if v is None:
            continue
        s = str(v).lower().strip()
        if s in ('pre-market', 'premarket', 'before market', 'bmo'):
            return 'BMO'
        if s in ('post-market', 'postmarket', 'after market', 'amc'):
            return 'AMC'
    return 'AMC'  # default


def compute_reaction(
    eps_row: dict,
    daily: pd.DataFrame,
    reaction_basis: str,
) -> Optional[dict]:
    """Pure compute. Returns one earnings_reactions row or None.

    Returns None when:
      - daily window is empty
      - D, D-1, or D+1 cannot be located (insufficient surrounding bars)

    Multi-horizon sustains (3d, 5d, 10d) are nullable — if the daily
    window doesn't reach that far (e.g. for very recent reports), the
    column is left NULL but the row is still returned.

    Required keys in eps_row: ticker, fiscal_date_ending, reported_date,
    reported_eps, estimated_eps, surprise_pct
    """
    reported = eps_row['reported_date']
    if daily.empty:
        return None

    # Locate D = first trading bar at-or-after reported_date.
    on_or_after = daily[daily['date'] >= reported]
    if on_or_after.empty:
        return None
    d_idx = on_or_after.index[0]

    # Need D-1 (for pre_gap and BMO drift anchor) and D+1 (for AMC reaction)
    if d_idx == 0 or d_idx + 1 >= len(daily):
        return None

    def safe(idx):
        return daily.iloc[idx] if 0 <= idx < len(daily) else None

    d_minus_10 = safe(d_idx - 10)
    d_minus_5 = safe(d_idx - 5)
    d_minus_3 = safe(d_idx - 3)
    d_minus_1 = safe(d_idx - 1)
    d = safe(d_idx)
    d_plus_1 = safe(d_idx + 1)
    if any(x is None for x in (d_minus_1, d, d_plus_1)):
        return None

    # Pre-earnings drift over multiple windows. Each is independent — if
    # the daily window doesn't reach back that far, the column stays
    # NULL but the row is still produced. D-10 is the canonical
    # "drifted into earnings" signal; D-3 / D-5 give the analyst a
    # tighter view of accumulation in the immediate run-up.
    pre_drift_10d = None
    d_minus_10_close = None
    if d_minus_10 is not None:
        d_minus_10_close = float(d_minus_10['close'])
        pre_drift_10d = (
            (float(d_minus_1['close']) - d_minus_10_close)
            / d_minus_10_close * 100
        )

    pre_drift_5d = None
    if d_minus_5 is not None:
        d_minus_5_close = float(d_minus_5['close'])
        pre_drift_5d = (
            (float(d_minus_1['close']) - d_minus_5_close)
            / d_minus_5_close * 100
        )

    pre_drift_3d = None
    if d_minus_3 is not None:
        d_minus_3_close = float(d_minus_3['close'])
        pre_drift_3d = (
            (float(d_minus_1['close']) - d_minus_3_close)
            / d_minus_3_close * 100
        )

    # Raw gap math (always computed; raw inputs to reaction_gap)
    pre_report_gap = (
        (float(d['open']) - float(d_minus_1['close']))
        / float(d_minus_1['close']) * 100
    )
    post_gap = (
        (float(d_plus_1['open']) - float(d['close']))
        / float(d['close']) * 100
    )

    # Timing-aware reaction. Sustain horizons (D+3, D+5, D+10) are
    # always measured from D regardless of timing — only the anchor
    # price differs (D close for BMO, D+1 open for AMC).
    if reaction_basis == 'BMO':
        reaction_gap = pre_report_gap
        anchor_price = float(d['close'])
        max_run = (
            (float(d['high']) - float(d['open'])) / float(d['open']) * 100
        )
        max_drawdown = (
            (float(d['low']) - float(d['open'])) / float(d['open']) * 100
        )
    else:  # AMC
        reaction_gap = post_gap
        anchor_price = float(d_plus_1['open'])
        max_run = (
            (float(d_plus_1['high']) - float(d_plus_1['open']))
            / float(d_plus_1['open']) * 100
        )
        max_drawdown = (
            (float(d_plus_1['low']) - float(d_plus_1['open']))
            / float(d_plus_1['open']) * 100
        )

    # Anomaly threshold: sustain values larger than this are almost
    # always stock-split artifacts in the unadjusted price series
    # (e.g. WMT 3-for-1 split between D+1 and D+5 in 2024 produced
    # sustain_5d=-66% on a +5% reaction). Real earnings sustains rarely
    # exceed 30%; 50% is a conservative cutoff that nulls split rows
    # without dropping legitimate large moves.
    SUSTAIN_ANOMALY_PCT = 50.0

    def sustain_at(n_days):
        # n trading days after D (so D+5 = d_idx + 5 in the bars index)
        idx = d_idx + n_days
        bar = safe(idx)
        if bar is None:
            return None, None
        close = float(bar['close'])
        pct = (close - anchor_price) / anchor_price * 100
        if abs(pct) > SUSTAIN_ANOMALY_PCT:
            # Almost certainly a split artifact in unadjusted prices.
            # Null it so downstream aggregates skip this quarter for
            # this horizon. Keep the close value in case audit needs it.
            return close, None
        return close, pct

    d_plus_3_close, sustain_3d = sustain_at(3)
    d_plus_5_close, sustain_5d = sustain_at(5)
    d_plus_10_close, sustain_10d = sustain_at(10)

    direction_consistent = None
    is_reversal = None
    if sustain_5d is not None and reaction_gap != 0:
        direction_consistent = (reaction_gap > 0) == (sustain_5d > 0)
        sign_flipped = (reaction_gap > 0) != (sustain_5d > 0)
        is_reversal = sign_flipped and abs(sustain_5d) >= abs(reaction_gap) * 0.5

    # ATR context — TIMING-AWARE. The "reaction day" is the bar where
    # the earnings reaction actually trades:
    #   BMO: D itself (report drops before open → D is the reaction day)
    #   AMC: D+1 (report drops after close → D+1 is the reaction day)
    #
    # Pre-report ATR  = ATR through the last full bar BEFORE the reaction.
    #                   This is the volatility regime traders see going INTO
    #                   the print. It's the natural denominator for "this
    #                   reaction was Nx ATR."
    #     BMO: atr_14 on D-1
    #     AMC: atr_14 on D       (D is normal trading; report drops after close)
    #
    # Post-report ATR = ATR through the reaction day. Includes the spike,
    #                   so it's the volatility regime AFTER the print. The
    #                   delta vs pre is a "regime shift" signal.
    #     BMO: atr_14 on D
    #     AMC: atr_14 on D+1
    #
    # Reaction-day range is high-low on the reaction-day bar (D for BMO,
    # D+1 for AMC). Dividing by pre-report ATR gives the "this print was
    # Nx normal volatility" number that matches third-party analytics.
    def _atr(bar) -> Optional[float]:
        if bar is None:
            return None
        v = bar.get('atr_14')
        try:
            return float(v) if v is not None and pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    if reaction_basis == 'BMO':
        pre_report_bar = d_minus_1
        post_report_bar = d
        reaction_bar = d
    else:  # AMC
        pre_report_bar = d
        post_report_bar = d_plus_1
        reaction_bar = d_plus_1

    pre_report_atr = _atr(pre_report_bar)
    post_report_atr = _atr(post_report_bar)
    pre_report_close = (
        float(pre_report_bar['close'])
        if pre_report_bar is not None else None
    )
    pre_report_atr_pct = (
        pre_report_atr / pre_report_close * 100
        if pre_report_atr is not None and pre_report_close
        else None
    )
    reaction_day_range = (
        float(reaction_bar['high']) - float(reaction_bar['low'])
        if reaction_bar is not None else None
    )
    reaction_day_range_in_atr_units = (
        reaction_day_range / pre_report_atr
        if reaction_day_range is not None
        and pre_report_atr is not None and pre_report_atr > 0
        else None
    )

    return {
        'ticker': eps_row['ticker'],
        'fiscal_date_ending': eps_row['fiscal_date_ending'],
        'reported_date': reported,
        'reaction_basis': reaction_basis,
        'reported_eps': eps_row.get('reported_eps'),
        'estimated_eps': eps_row.get('estimated_eps'),
        'surprise_pct': eps_row.get('surprise_pct'),
        'd_minus_10_close': d_minus_10_close,
        'd_minus_1_close': float(d_minus_1['close']),
        'pre_earnings_drift_10d_pct': pre_drift_10d,
        'pre_drift_5d_pct': pre_drift_5d,
        'pre_drift_3d_pct': pre_drift_3d,
        'd_open': float(d['open']),
        'd_high': float(d['high']),
        'd_low': float(d['low']),
        'd_close': float(d['close']),
        'pre_report_gap_pct': pre_report_gap,
        'd_plus_1_open': float(d_plus_1['open']),
        'd_plus_1_high': float(d_plus_1['high']),
        'd_plus_1_low': float(d_plus_1['low']),
        'd_plus_1_close': float(d_plus_1['close']),
        'post_gap_pct': post_gap,
        'reaction_gap_pct': reaction_gap,
        'reaction_anchor_price': anchor_price,
        'reaction_max_run_pct': max_run,
        'reaction_max_drawdown_pct': max_drawdown,
        'd_plus_3_close': d_plus_3_close,
        'sustain_3d_pct': sustain_3d,
        'd_plus_5_close': d_plus_5_close,
        'sustain_5d_pct': sustain_5d,
        'd_plus_10_close': d_plus_10_close,
        'sustain_10d_pct': sustain_10d,
        'direction_consistent_5d': direction_consistent,
        'is_reversal_5d': is_reversal,
        # Timing-aware ATR context (replaces the buggy atr_14_d_minus_1 /
        # atr_14_d / day_range_in_atr_units columns from the first cut).
        'pre_report_atr': pre_report_atr,
        'pre_report_atr_pct': pre_report_atr_pct,
        'post_report_atr': post_report_atr,
        'reaction_day_range': reaction_day_range,
        'reaction_day_range_in_atr_units': reaction_day_range_in_atr_units,
    }


# ────────────────────────────────────────────────────────────
# DB integration
# ────────────────────────────────────────────────────────────

def fetch_earnings_history_for_tickers(tickers: list[str]) -> pd.DataFrame:
    """Pull all valid (non-placeholder) earnings_history rows for the
    given tickers, with both AV report_time and Yahoo yahoo_report_time."""
    if not tickers:
        return pd.DataFrame()
    placeholders = ','.join(f"'{t}'" for t in tickers)
    sql = f"""
        SELECT ticker, fiscal_date_ending, reported_date,
               reported_eps, estimated_eps, surprise_pct,
               report_time, yahoo_report_time
        FROM earnings_history
        WHERE ticker IN ({placeholders})
          AND reported_date IS NOT NULL
          AND (reported_eps > 0 OR reported_eps < 0)
        ORDER BY ticker, reported_date DESC
    """
    return query_to_dataframe(sql)


def fetch_calendar_timing_map(tickers: list[str]) -> dict[str, str]:
    """Build a per-ticker fallback timing map from earnings_calendar.

    When earnings_history.report_time is NULL, fall back to whichever
    timing the calendar majority-vote says. Returns ticker -> timing.
    """
    if not tickers:
        return {}
    placeholders = ','.join(f"'{t}'" for t in tickers)
    sql = f"""
        SELECT ticker, earnings_time, COUNT(*) AS c
        FROM earnings_calendar
        WHERE ticker IN ({placeholders})
          AND earnings_time IN ('premarket', 'postmarket')
        GROUP BY ticker, earnings_time
    """
    df = query_to_dataframe(sql)
    if df.empty:
        return {}
    out: dict[str, str] = {}
    for ticker, group in df.groupby('ticker'):
        winner = group.sort_values('c', ascending=False).iloc[0]
        out[str(ticker)] = str(winner['earnings_time'])
    return out


def fetch_daily_window(ticker: str, reported_date: date) -> pd.DataFrame:
    """Return ~30 trading days centered on reported_date for this ticker.

    Wide enough to handle weekends/holidays around D and to reach D+10
    for the 10-day sustain calculation. Includes atr_14 so the
    populator can write ATR-context columns without a second pull
    (the column is populated by the daily fetcher's full-range
    indicator pass; rows without it stay NULL in the output).
    """
    sql = """
        SELECT date, open, high, low, close, volume, atr_14
          FROM market_data_daily
         WHERE ticker = :t AND date BETWEEN :start AND :end
         ORDER BY date
    """
    params = {
        't': ticker,
        'start': reported_date - timedelta(days=20),
        'end': reported_date + timedelta(days=25),
    }
    df = query_to_dataframe(sql, params)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values('date').reset_index(drop=True)
    return df


def populate_for_tickers(tickers: list[str], dry_run: bool = False) -> int:
    """Build earnings_reactions rows for the given tickers, upsert.

    Returns the number of rows produced.
    """
    eps_df = fetch_earnings_history_for_tickers(tickers)
    if eps_df.empty:
        log.warning("No earnings_history rows for %s", tickers)
        return 0

    calendar_timing = fetch_calendar_timing_map(tickers)
    log.info("earnings_history rows: %d  /  calendar timing fallback: %s",
             len(eps_df), calendar_timing)

    rows: list[dict] = []
    skipped: int = 0
    for _, eps in eps_df.iterrows():
        ticker = eps['ticker']
        report_time = eps.get('report_time')
        yahoo_report_time = eps.get('yahoo_report_time')
        cal_timing = calendar_timing.get(ticker)
        basis = normalize_timing(report_time, cal_timing, yahoo_report_time)

        daily = fetch_daily_window(ticker, eps['reported_date'])
        result = compute_reaction(eps.to_dict(), daily, basis)
        if result is None:
            skipped += 1
            continue
        rows.append(result)

    log.info("Computed %d reaction rows  (skipped %d for insufficient bars)",
             len(rows), skipped)

    if not rows:
        return 0
    out_df = pd.DataFrame(rows)

    # Scrub NaN/NaT to None so they land as PostgreSQL NULL
    import numpy as np
    out_df = out_df.replace({np.nan: None}).where(out_df.notna(), None)

    if dry_run:
        with pd.option_context('display.max_columns', 12, 'display.width', 200):
            print(out_df[['ticker', 'reported_date', 'reaction_basis',
                          'reaction_gap_pct', 'sustain_5d_pct',
                          'direction_consistent_5d', 'is_reversal_5d']]
                  .head(20).to_string(index=False))
        print(f"\n[dry-run] {len(out_df)} rows — not written")
        return len(out_df)

    if not is_cloud_sql_configured():
        log.warning("Cloud SQL not configured — skipping persist")
        return 0

    n = upsert_dataframe(
        out_df, 'earnings_reactions',
        ['ticker', 'fiscal_date_ending'],
    )
    log.info("✓ upserted %d rows to earnings_reactions", n)
    return n


# ────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────

def _resolve_tickers(args) -> list[str]:
    """Resolve ticker set: --tickers override, else every ticker we have
    earnings_history for (which also includes the watchlist + tomorrow's
    brief-set since fetch_earnings_history pulls them).

    Earlier this defaulted to a narrow JIT scope (brief-set + watchlist
    only). That left ~289 of 320 historical tickers without
    earnings_reactions rows even though we had their EPS data. Result:
    the brief showed "no historical analog" for major reporters like
    AMZN/MSFT/META despite us having their data.

    The broad scope is cheap — it's a pure DB join with no external API
    calls, so populating 320 tickers takes the same ~5 min as
    populating 30. Coverage matches earnings_history automatically.
    """
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(',') if t.strip()]

    sql = """
        SELECT DISTINCT ticker
          FROM earnings_history
         WHERE reported_date IS NOT NULL
           AND (reported_eps > 0 OR reported_eps < 0)
         ORDER BY ticker
    """
    df = query_to_dataframe(sql)
    if df.empty:
        return []
    return [str(t).upper() for t in df['ticker'].tolist()]


def main():
    parser = argparse.ArgumentParser(
        description="Populate earnings_reactions from earnings_history × market_data_daily"
    )
    parser.add_argument('--tickers', default=None,
                        help="Comma-separated tickers (overrides watchlist+calendar resolution).")
    parser.add_argument('--dry-run', action='store_true',
                        help="Print computed rows without writing.")
    args = parser.parse_args()

    tickers = _resolve_tickers(args)
    if not tickers:
        log.warning("No tickers to process — exiting")
        return

    log.info("compute_earnings_reactions: %d tickers", len(tickers))
    n = populate_for_tickers(tickers, dry_run=args.dry_run)
    print(f"compute_earnings_reactions: {n} rows {'computed' if args.dry_run else 'upserted'}")


if __name__ == '__main__':
    main()
