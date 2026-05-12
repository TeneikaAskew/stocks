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
    d_minus_1 = safe(d_idx - 1)
    d = safe(d_idx)
    d_plus_1 = safe(d_idx + 1)
    if any(x is None for x in (d_minus_1, d, d_plus_1)):
        return None

    # Pre-earnings drift (only when D-10 is in window)
    pre_drift_10d = None
    d_minus_10_close = None
    if d_minus_10 is not None:
        d_minus_10_close = float(d_minus_10['close'])
        pre_drift_10d = (
            (float(d_minus_1['close']) - d_minus_10_close)
            / d_minus_10_close * 100
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

    # Best-exit / worst-drawdown over the swing window (added 2026-05-04).
    # The "sustain" columns above use the close on day N — a swing trader
    # holding the position can exit at any point in the window. These give
    # the actual high/low touched, expressed as % vs reaction_anchor_price
    # (the reaction-day close for BMO, D+1 open for AMC). This converts
    # "did the position make money on day N close?" into "did the position
    # have a profitable exit point during days 1..N?" Cheap — pure agg
    # over the same daily window already loaded for sustain math.
    #
    # Window: [reaction_idx, d_idx + n_days] inclusive — matches the
    # existing sustain_N_pct convention where sustain_5d uses bar at
    # d_idx + 5. For AMC the reaction starts at D+1, so the window
    # spans D+1..D+N (N bars). For BMO the reaction is on D itself,
    # so the window spans D..D+N (N+1 bars). The reaction-day bar
    # itself is included so an intraday gap-and-fade isn't missed.
    reaction_idx = d_idx if reaction_basis == 'BMO' else d_idx + 1

    def best_worst_in_window(n_days):
        """Return (max_high_pct, min_low_pct) over the swing window.

        Anchor = reaction_anchor_price (D close for BMO, D+1 open for
        AMC). Anomaly cap matches the sustain logic so split artifacts
        don't poison the columns.
        """
        end_idx = d_idx + n_days
        # Slice valid bars within the loaded window
        if end_idx >= len(daily) or reaction_idx >= len(daily):
            return None, None
        slice_ = daily.iloc[reaction_idx:end_idx + 1]
        if slice_.empty:
            return None, None
        try:
            hi = float(slice_['high'].max())
            lo = float(slice_['low'].min())
        except (TypeError, ValueError):
            return None, None
        max_pct = (hi - anchor_price) / anchor_price * 100
        min_pct = (lo - anchor_price) / anchor_price * 100
        # Same split-artifact cap used by sustain — null if either side
        # exceeds the anomaly threshold so downstream aggregates skip
        # this quarter for this horizon.
        if abs(max_pct) > SUSTAIN_ANOMALY_PCT:
            max_pct = None
        if abs(min_pct) > SUSTAIN_ANOMALY_PCT:
            min_pct = None
        return max_pct, min_pct

    max_high_3d, min_low_3d = best_worst_in_window(3)
    max_high_5d, min_low_5d = best_worst_in_window(5)
    max_high_10d, min_low_10d = best_worst_in_window(10)

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
        # Best-exit / worst-drawdown over the swing window
        'max_high_3d_pct':  max_high_3d,
        'min_low_3d_pct':   min_low_3d,
        'max_high_5d_pct':  max_high_5d,
        'min_low_5d_pct':   min_low_5d,
        'max_high_10d_pct': max_high_10d,
        'min_low_10d_pct':  min_low_10d,
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

    NOTE: For the bulk populate path (`populate_for_tickers`), prefer
    `fetch_daily_windows_for_ticker_dates` which issues ONE query per
    ticker instead of one per (ticker, reported_date). This per-call
    function is kept for ad-hoc callers (CLI smoke tests) and is the
    legacy code path that caused the 30-min Cloud Run task-timeout —
    see issue #452 and the post-fix benchmarks in the PR description.
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


def fetch_daily_windows_for_ticker_dates(
    ticker: str, reported_dates: list[date],
) -> dict[date, pd.DataFrame]:
    """Bulk-fetch ~30-day windows for one ticker across many earnings dates.

    Issues a single SQL query covering [min(dates) - 20d, max(dates) + 25d]
    and then slices the result in-memory per ``reported_date``. Returns a
    ``{reported_date → 30-day-window DataFrame}`` map matching what
    `fetch_daily_window(ticker, d)` would have returned for each date.

    Why: the prior populate_for_tickers loop called fetch_daily_window
    once per (ticker, reported_date) pair. With ~73,667 earnings_history
    rows across ~1,174 tickers, that produced ~73,667 SQL round-trips
    at ~1s each over the pg8000+Cloud SQL Connector path — wall-clock
    of ~20 hours, well beyond the 30-min Cloud Run task-timeout the
    job has configured. CLAUDE.md Rule 0.4 ("Batch SQL queries by
    partition/grouping key — never per-row when N could exceed 100")
    explicitly calls this anti-pattern out.

    Post-fix: 1 query per ticker × ~1,174 tickers ≈ 1,174 queries ≈ 20
    minutes — comfortably inside the timeout. Issue #452.

    Memory bound: per-ticker window pulls cover that ticker's full
    earnings date span (typically 5-30 years × 252 trading days × 7
    columns ≈ 5,000-50,000 rows × ~80 bytes ≈ <4 MB per ticker). Only
    one ticker's window is materialised at a time when callers iterate
    ticker-by-ticker, so peak working set stays small.
    """
    if not reported_dates:
        return {}
    min_date = min(reported_dates) - timedelta(days=20)
    max_date = max(reported_dates) + timedelta(days=25)
    sql = """
        SELECT date, open, high, low, close, volume, atr_14
          FROM market_data_daily
         WHERE ticker = :t AND date BETWEEN :start AND :end
         ORDER BY date
    """
    df = query_to_dataframe(sql, {'t': ticker, 'start': min_date, 'end': max_date})
    out: dict[date, pd.DataFrame] = {}
    if df.empty:
        # No daily bars at all for this ticker in the union window —
        # every reported_date gets an empty frame so the caller's
        # downstream compute_reaction() returns None for each.
        for d in reported_dates:
            out[d] = df
        return out
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.sort_values('date').reset_index(drop=True)
    for d in reported_dates:
        start = d - timedelta(days=20)
        end = d + timedelta(days=25)
        mask = (df['date'] >= start) & (df['date'] <= end)
        # .copy() so downstream mutations (compute_reaction sets new
        # columns on the slice) don't trigger SettingWithCopyWarning
        # or clobber the parent frame.
        out[d] = df.loc[mask].reset_index(drop=True).copy()
    return out


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

    # Group earnings by ticker so we issue ONE market_data_daily query
    # per ticker (covering the union of its reported_dates) instead of
    # one per (ticker, reported_date) pair. This is the fix for issue
    # #452 — the prior per-row pattern queued ~73,667 round-trips and
    # consistently hit the 30-min Cloud Run task-timeout.
    # CLAUDE.md Rule 0.4: "Batch SQL queries by partition/grouping key
    # — never per-row when N could exceed 100."
    rows: list[dict] = []
    skipped: int = 0
    ticker_groups = list(eps_df.groupby('ticker', sort=False))
    n_tickers = len(ticker_groups)
    log.info("processing %d tickers × ~%d earnings rows each",
             n_tickers, len(eps_df) // max(n_tickers, 1))

    for ti, (ticker, ticker_eps) in enumerate(ticker_groups, start=1):
        # Collect every reported_date this ticker has, then bulk-fetch
        # the daily bars in one query covering the full date span.
        dates_for_ticker = ticker_eps['reported_date'].tolist()
        windows = fetch_daily_windows_for_ticker_dates(ticker, dates_for_ticker)

        ticker_kept = 0
        ticker_skipped = 0
        for _, eps in ticker_eps.iterrows():
            report_time = eps.get('report_time')
            yahoo_report_time = eps.get('yahoo_report_time')
            cal_timing = calendar_timing.get(ticker)
            basis = normalize_timing(report_time, cal_timing, yahoo_report_time)

            daily = windows.get(eps['reported_date'], pd.DataFrame())
            result = compute_reaction(eps.to_dict(), daily, basis)
            if result is None:
                ticker_skipped += 1
                continue
            rows.append(result)
            ticker_kept += 1

        skipped += ticker_skipped
        # Per-ticker progress log — every 25 tickers + the final one.
        # CLAUDE.md Rule 0.4: "Observable progress — log per-group counts
        # so a 30-minute job is debuggable, not a black box."
        if ti % 25 == 0 or ti == n_tickers:
            log.info("ticker=%s [%d/%d] kept=%d skipped=%d  (cum rows=%d)",
                     ticker, ti, n_tickers,
                     ticker_kept, ticker_skipped, len(rows))

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
