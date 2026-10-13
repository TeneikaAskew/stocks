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

from gcp.database import upsert_dataframe, query_to_dataframe_strict as query_to_dataframe, is_cloud_sql_configured
from gcp.fetchers import _av_ingestion as av
from datetime import datetime, timezone
import math
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
    if not daily.attrs.get('validated_common_basis'):
        if 'split_coefficient' in daily and (daily['split_coefficient'].dropna()!=1).any():
            return None
        ratios=daily['close'].astype(float).pct_change().add(1).dropna()
        split_ratios=(.5,2/3,.75,2,1.5,4/3)
        if any(math.isclose(r,s,rel_tol=0,abs_tol=1e-8) for r in ratios for s in split_ratios):
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
        """Bounds-checked ``daily.iloc[idx]`` — returns None on out-of-range.

        Lets the surrounding window math (D-10..D+10) silently skip bars
        that don't exist (fresh IPOs, current-quarter reports without a
        forward window) without raising IndexError. Callers branch on
        the None sentinel and emit explicit NULLs to the DB column.
        """
        return daily.iloc[idx] if 0 <= idx < len(daily) else None

    d_minus_10 = safe(d_idx - 10)
    d_minus_5  = safe(d_idx - 5)
    d_minus_3  = safe(d_idx - 3)
    d_minus_2  = safe(d_idx - 2)
    d_minus_1  = safe(d_idx - 1)
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

    # Finer-grained pre-earnings drift (added 2026-05-14). Each horizon
    # is computed independently — a freshly-IPO'd ticker may have D-3 but
    # not D-5, etc. Nulls are explicit; downstream consumers handle them.
    d_minus_5_close = float(d_minus_5['close']) if d_minus_5 is not None else None
    d_minus_3_close = float(d_minus_3['close']) if d_minus_3 is not None else None
    d_minus_2_close = float(d_minus_2['close']) if d_minus_2 is not None else None
    drift_5d_pct = (
        (float(d_minus_1['close']) - d_minus_5_close) / d_minus_5_close * 100
        if d_minus_5_close else None
    )
    drift_3d_pct = (
        (float(d_minus_1['close']) - d_minus_3_close) / d_minus_3_close * 100
        if d_minus_3_close else None
    )
    # Behavioral flag: consistent run-up/down across both horizons + non-trivial magnitude.
    pre_drift_consistent_5d = None
    if drift_5d_pct is not None and drift_3d_pct is not None:
        pre_drift_consistent_5d = bool(
            ((drift_5d_pct > 0 and drift_3d_pct > 0)
             or (drift_5d_pct < 0 and drift_3d_pct < 0))
            and abs(drift_5d_pct) >= 1.0
        )
    # pre_drift_reverses_into_gap is post-event (sign of drift_5d vs
    # reaction_gap). Computed below after reaction_gap is known.

    # Intraday range over each pre-earnings window. Symmetric with post-
    # earnings max_high_3d_pct / min_low_3d_pct etc. Anchor is the D-N close
    # (start of window). Captures "ran and gave back" patterns that pure
    # close-to-close drift misses — e.g. HIMS 2026-05-11 closed up only
    # 3.67% over the prior week but its intraday high in that window was
    # ~10% above D-5 close.
    def pre_window_high_low(window_days: int, anchor_close):
        """Return (max_high_pct, min_low_pct) over the pre-earnings window.

        Walks bars D-N..D-1 inclusive (the same window the matching
        ``drift_Nd_pct`` close-to-close metric uses) and returns the
        intraday high and low expressed as % vs ``anchor_close`` (the
        D-N close that anchors the drift calculation).

        Returns (None, None) when the anchor is missing or invalid, or
        when no bars in the window exist — the caller emits NULL.
        Surfaces "ran and gave back" patterns that pure close-to-close
        drift misses (see the in-line HIMS 2026-05-11 example).
        """
        if anchor_close is None or anchor_close <= 0:
            return (None, None)
        bars = []
        for off in range(window_days, 0, -1):   # D-N .. D-1 inclusive
            bar = safe(d_idx - off)
            if bar is not None:
                bars.append(bar)
        if not bars:
            return (None, None)
        max_high = max(float(b['high']) for b in bars)
        min_low  = min(float(b['low'])  for b in bars)
        return (
            (max_high - anchor_close) / anchor_close * 100,
            (min_low  - anchor_close) / anchor_close * 100,
        )

    max_high_pre_3d_pct,  min_low_pre_3d_pct  = pre_window_high_low(3,  d_minus_3_close)
    max_high_pre_5d_pct,  min_low_pre_5d_pct  = pre_window_high_low(5,  d_minus_5_close)
    max_high_pre_10d_pct, min_low_pre_10d_pct = pre_window_high_low(10, d_minus_10_close)

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
        """Return (close_at_D+N, sustain_pct) for the reaction window.

        ``sustain_pct`` = (close_at_D+N − anchor_price) / anchor_price × 100,
        where ``anchor_price`` = D close (BMO) or D+1 open (AMC) — set
        by the surrounding scope.

        Returns (None, None) when D+N is past the loaded daily range.
        Returns (close, None) when the magnitude exceeds
        ``SUSTAIN_ANOMALY_PCT`` (almost certainly a stock-split artifact
        in unadjusted prices — see the WMT 2024 example above); keeping
        the close value preserves audit info while nulling the percent
        so downstream aggregates skip this quarter for this horizon.
        """
        # n trading days after D (so D+5 = d_idx + 5 in the bars index)
        idx = d_idx + n_days
        bar = safe(idx)
        if bar is None:
            return None, None
        close = float(bar['close'])
        pct = (close - anchor_price) / anchor_price * 100
        if abs(pct) > SUSTAIN_ANOMALY_PCT:
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
        """ATR-14 at the requested bar.

        Prefers the pre-computed ``atr_14`` column when present, otherwise
        falls back to an inline Wilder ATR over the 14 trading bars
        ending at ``bar``. The inline path makes this populator self-
        sufficient — historical ``market_data_daily`` rows had ``atr_14``
        populated for only ~1.7% of the corpus (the fetcher only computes
        it on live daily pulls), so relying on the column meant
        ``pre_report_atr`` was NULL for ~99% of earnings_reactions rows.
        Computing inline from OHLC the populator already has is O(14)
        per call and removes the upstream-coverage dependency entirely.
        """
        if bar is None:
            return None
        # Fast path: pre-computed column is present.
        v = bar.get('atr_14')
        try:
            f = float(v) if v is not None and pd.notna(v) else None
        except (TypeError, ValueError):
            f = None
        if f is not None and f > 0:
            return f
        # Inline Wilder ATR-14. ``daily`` is the per-event window in
        # scope of the enclosing compute_reaction(); the bar's ``date``
        # locates its position. We need 14 prior bars to form TR_t.
        try:
            bar_date = bar['date']
        except (KeyError, TypeError):
            return None
        idx_arr = daily.index[daily['date'] == bar_date]
        if len(idx_arr) == 0:
            return None
        end_idx = int(idx_arr[0])
        start_idx = end_idx - 14
        if start_idx < 0:
            # Genuinely under-historied — market_data_daily doesn't have
            # 14 prior bars for this ticker at this date. Log so the
            # operator can decide whether to backfill the upstream
            # daily-bars fetcher for the ticker.
            log.warning(
                "inline ATR-14 skipped for %s @ %s: only %d prior bars "
                "in window (need 14). Consider backfilling "
                "market_data_daily for this ticker.",
                eps_row.get('ticker', '?'), bar_date, end_idx,
            )
            return None
        window = daily.iloc[start_idx:end_idx + 1].copy()
        if len(window) < 15:
            log.warning(
                "inline ATR-14 skipped for %s @ %s: window has %d bars "
                "after slice (need 15).",
                eps_row.get('ticker', '?'), bar_date, len(window),
            )
            return None
        h = window['high'].astype(float).to_numpy()
        l = window['low'].astype(float).to_numpy()
        c = window['close'].astype(float).to_numpy()
        # True range needs prev-close — first row has no prev so its TR
        # is just (high - low); subsequent rows take the 3-way max.
        prev_c = c[:-1]
        cur_h = h[1:]
        cur_l = l[1:]
        tr = pd.Series(
            [
                max(cur_h[i] - cur_l[i],
                    abs(cur_h[i] - prev_c[i]),
                    abs(cur_l[i] - prev_c[i]))
                for i in range(len(cur_h))
            ],
            dtype='float64',
        )
        # Wilder smoothing == EMA with alpha=1/14
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
        return float(atr) if pd.notna(atr) and atr > 0 else None

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

    # Post-event flag: did the pre-earnings drift reverse on the gap?
    # Useful as a contrarian signal in the backtest.
    pre_drift_reverses_into_gap = None
    if drift_5d_pct is not None and reaction_gap is not None:
        pre_drift_reverses_into_gap = bool(
            (drift_5d_pct > 0 and reaction_gap < 0)
            or (drift_5d_pct < 0 and reaction_gap > 0)
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
        'd_minus_5_close':  d_minus_5_close,
        'd_minus_3_close':  d_minus_3_close,
        'd_minus_2_close':  d_minus_2_close,
        'd_minus_1_close': float(d_minus_1['close']),
        'pre_earnings_drift_10d_pct': pre_drift_10d,
        'drift_5d_pct': drift_5d_pct,
        'drift_3d_pct': drift_3d_pct,
        'pre_drift_consistent_5d': pre_drift_consistent_5d,
        'pre_drift_reverses_into_gap': pre_drift_reverses_into_gap,
        # Intraday pre-window range (symmetric with post-earnings max_high_*d_pct / min_low_*d_pct)
        'max_high_pre_3d_pct':  max_high_pre_3d_pct,
        'min_low_pre_3d_pct':   min_low_pre_3d_pct,
        'max_high_pre_5d_pct':  max_high_pre_5d_pct,
        'min_low_pre_5d_pct':   min_low_pre_5d_pct,
        'max_high_pre_10d_pct': max_high_pre_10d_pct,
        'min_low_pre_10d_pct':  min_low_pre_10d_pct,
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

def fetch_earnings_history_for_tickers(tickers,*,as_of=None,max_quarters=100):
    if not tickers:
        return pd.DataFrame()
    if len(tickers)>100 or not 1<=max_quarters<=100:
        raise av.SourceError('reaction_admission_limit')
    from lib.earnings_history import aware_cutoff
    cutoff=aware_cutoff(as_of) if as_of is not None else datetime.now(timezone.utc)
    return av.read_dataframe("""WITH vintages AS(
      SELECT DISTINCT ON(ticker,fiscal_date_ending) * FROM earnings_history_revisions
      WHERE ticker=ANY(CAST(:tickers AS text[])) AND known_at<=:cutoff
      ORDER BY ticker,fiscal_date_ending,known_at DESC,revision_id DESC
    ), ranked AS(SELECT *,row_number() OVER(PARTITION BY ticker ORDER BY fiscal_date_ending DESC) AS position FROM vintages)
    SELECT r.ticker,r.fiscal_date_ending,(r.payload->>'reported_date')::date AS reported_date,
      (r.payload->>'reported_eps')::double precision AS reported_eps,
      (r.payload->>'estimated_eps')::double precision AS estimated_eps,
      (r.payload->>'surprise_pct')::double precision AS surprise_pct,
      r.payload->>'report_time' AS report_time,r.payload->>'yahoo_report_time' AS yahoo_report_time,
      r.revision_id,COALESCE(proof.known_at,r.known_at) AS known_at,
      CASE WHEN proof.capture_id IS NOT NULL THEN 'source_verified' ELSE CASE WHEN r.availability_quality='source_verified' THEN 'source_provenance_unavailable' ELSE r.availability_quality END END AS availability_quality,
      COALESCE(proof.yahoo_timing_observation_id,r.yahoo_timing_observation_id) AS yahoo_timing_observation_id
      FROM ranked r
      LEFT JOIN LATERAL(SELECT o.* FROM earnings_revision_observations o
        JOIN av_catalyst_source_captures c ON c.capture_id=o.capture_id AND c.validation_status='validated' AND c.function='EARNINGS' AND c.ticker=r.ticker
        WHERE o.revision_id=r.revision_id AND o.known_at<=:cutoff AND c.source_retrieved_at<=:cutoff
        ORDER BY o.known_at DESC,o.capture_id DESC LIMIT 1) proof ON true
      WHERE position<=:quarters AND r.payload->>'reported_date' IS NOT NULL
      ORDER BY r.ticker,r.fiscal_date_ending DESC""",{'tickers':tickers,'cutoff':cutoff,'quarters':max_quarters})


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
        SELECT date, open, high, low, close, volume, atr_14, adjusted_close, split_coefficient, daily_source_journal_id AS source_journal_id, daily_provenance
          FROM market_data_daily
         WHERE ticker = :t AND date BETWEEN :start AND :end
         ORDER BY date
    """
    # Window: −90 calendar / +25 calendar. The −90 floor (was −40) gives
    # ~60 trading bars before D — comfortably above the 14 needed by the
    # inline ATR-14 fallback even after stretches of weekends/holidays,
    # so we essentially never NULL out pre_report_atr because of a thin
    # slice. The lookback is local Cloud SQL (no API cost) so widening
    # is free.
    params = {
        't': ticker,
        'start': reported_date - timedelta(days=90),
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
    # −90 calendar floor (was −40) so the inline ATR-14 fallback in
    # compute_reaction()._atr() always has ~60 trading bars even after
    # weekend/holiday clusters. Local Cloud SQL pull, no API cost.
    min_date = min(reported_dates) - timedelta(days=90)
    max_date = max(reported_dates) + timedelta(days=25)
    sql = """
        SELECT date, open, high, low, close, volume, atr_14, adjusted_close, split_coefficient, daily_source_journal_id AS source_journal_id, daily_provenance
          FROM market_data_daily
         WHERE ticker = :t AND date BETWEEN :start AND :end
         ORDER BY date
    """
    df = av.read_dataframe(sql, {'t': ticker, 'start': min_date, 'end': max_date})
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
        # Match the −90 floor used by the SQL pull above so the inline
        # ATR-14 fallback in _atr() always has ~60 prior bars.
        start = d - timedelta(days=90)
        end = d + timedelta(days=25)
        mask = (df['date'] >= start) & (df['date'] <= end)
        # .copy() so downstream mutations (compute_reaction sets new
        # columns on the slice) don't trigger SettingWithCopyWarning
        # or clobber the parent frame.
        out[d] = df.loc[mask].reset_index(drop=True).copy()
    return out


def fetch_reaction_timing_observations(ids,*,cutoff):
    """One deduplicated bounded read; complete source payload stays permanent."""
    import uuid
    try:ids=sorted({str(uuid.UUID(str(value))) for value in ids if value is not None})
    except (ValueError,TypeError,AttributeError):raise av.SourceError('timing_identity_unavailable') from None
    if len(ids)>100:raise av.SourceError('timing_observation_admission_limit')
    frame=av.read_dataframe("""WITH selected AS(SELECT observation_id,ticker,known_at,source_retrieved_at,
        content_sha256,library_version,safe_parameters,payload FROM earnings_timing_observations
        WHERE observation_id=ANY(CAST(:ids AS uuid[])) AND known_at<=:cutoff AND source_retrieved_at<=:cutoff),
      measured AS(SELECT count(*) AS observation_count,COALESCE(sum(octet_length(to_jsonb(s)::text)),0) AS bytes FROM selected s)
      SELECT CASE WHEN m.bytes<=2097152 AND m.observation_count<=100 THEN
        (SELECT COALESCE(jsonb_agg(to_jsonb(s) ORDER BY observation_id),'[]'::jsonb) FROM selected s) ELSE NULL END AS records,
        m.bytes,m.observation_count FROM measured m""",{'ids':ids,'cutoff':cutoff},timeout_s=8)
    if frame.empty:
        if ids:raise av.SourceError('timing_read_unavailable')
        return {}
    row=frame.iloc[0]
    if row['records'] is None:raise av.SourceError('timing_batch_byte_limit')
    records=row['records']
    if len(av.canonical(records).encode())>2*1024*1024:raise av.SourceError('timing_batch_byte_limit')
    result={}
    for record in records:
        payload=record['payload']
        if (not isinstance(payload,dict) or not isinstance(payload.get('rows'),list)
            or len(payload['rows'])>50 or any(len(av.canonical(r).encode())>400 for r in payload['rows'])
            or av.digest(payload)!=record['content_sha256']):raise av.SourceError('timing_observation_provenance_unavailable')
        result[record['observation_id']]=record
    return result


def fetch_daily_windows_for_ticker_batch(groups):
    """One <=10-ticker, <=26000-bar, <=16MiB guarded SQL price read."""
    if len(groups)>10:raise av.SourceError('price_batch_ticker_limit')
    windows=[{'ticker':ticker,'start':(min(dates)-timedelta(days=90)).isoformat(),
              'end':(max(dates)+timedelta(days=25)).isoformat()} for ticker,dates in groups.items() if dates]
    frame=av.read_dataframe("""WITH source AS(SELECT m.ticker,m.date,m.open,m.high,m.low,m.close,m.volume,m.atr_14,
        m.adjusted_close,m.split_coefficient,m.daily_source_journal_id AS source_journal_id,m.daily_provenance
      FROM market_data_daily m JOIN jsonb_to_recordset(CAST(:windows AS jsonb)) w(ticker text,start date,"end" date)
        ON m.ticker=w.ticker AND m.date BETWEEN w.start AND w."end" ORDER BY m.ticker,m.date LIMIT 26001),
      measured AS(SELECT count(*) AS bar_count,COALESCE(sum(octet_length(to_jsonb(s)::text)),0) AS bytes FROM source s)
      SELECT s.*,NULL::text AS capacity_error FROM source s CROSS JOIN measured m
        WHERE m.bar_count<=26000 AND m.bytes<=16777216
      UNION ALL SELECT NULL::text,NULL::date,NULL::numeric,NULL::numeric,NULL::numeric,NULL::numeric,
        NULL::bigint,NULL::numeric,NULL::numeric,NULL::numeric,NULL::uuid,NULL::jsonb,'price_batch_capacity_limit'
        FROM measured m WHERE m.bar_count>26000 OR m.bytes>16777216""",{'windows':av.canonical(windows)},timeout_s=8)
    if not frame.empty and frame['capacity_error'].notna().any():raise av.SourceError('price_batch_capacity_limit')
    if not frame.empty:
        frame=frame.drop(columns=['capacity_error'])
        if len(frame)>26000 or len(av.canonical(frame.to_dict('records')).encode())>16*1024*1024:
            raise av.SourceError('price_batch_capacity_limit')
        frame['date']=pd.to_datetime(frame['date']).dt.date
    result={}
    for ticker,dates in groups.items():
        source=frame.loc[frame['ticker']==ticker].drop(columns=['ticker']).sort_values('date') if not frame.empty else frame
        result[ticker]={d:source.loc[(source['date']>=d-timedelta(days=90)) & (source['date']<=d+timedelta(days=25))].reset_index(drop=True).copy()
            if not source.empty else source for d in set(dates)}
    return result


def _iter_reaction_price_batches(eps_df,*,run,deadline):
    tickers=eps_df['ticker'].drop_duplicates().tolist()
    for offset in range(0,len(tickers),10):
        if deadline is not None and __import__('time').monotonic()>=deadline-48:
            run.pending+=len(tickers)-offset
            run.groups.append({'coverage_complete':False,'error_class':'reaction_deadline_pending'})
            return
        batch={ticker:eps_df.loc[eps_df['ticker']==ticker,'reported_date'].tolist() for ticker in tickers[offset:offset+10]}
        windows=fetch_daily_windows_for_ticker_batch(batch)
        for ticker in batch:yield ticker,eps_df.loc[eps_df['ticker']==ticker],windows[ticker]


def prepare_reaction_inputs(eps,daily,*,as_of=None):
    """Use only the actually merged DATA helper; absent dependency is unavailable."""
    import importlib.util
    if as_of is not None:
        from lib.earnings_history import aware_cutoff
        aware_cutoff(as_of)
        if not daily.attrs.get('immutable_vintage'):
            raise av.SourceError('price_vintage_unavailable')
    if importlib.util.find_spec('lib.price_basis') is None:
        raise av.SourceError('price_basis_dependency_unavailable')
    # No unmerged sibling module is imported or copied into this branch.
    from lib.price_basis import prepare_daily_basis
    if eps.get('availability_quality')!='source_verified' or eps.get('revision_id') is None:
        raise av.SourceError('earnings_revision_unverified')
    dindex=daily.index[daily['date']>=eps['reported_date']]
    if not len(dindex):
        raise av.SourceError('reaction_session_missing')
    position=daily.index.get_loc(dindex[0])
    daily=daily.iloc[max(0,position-15):position+11].reset_index(drop=True).copy()
    clean=daily.astype(object).where(daily.notna(),None)
    price_columns={'date':'date','open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume',
                   'adjusted_close':'adjusted_close','split_coefficient':'split_coefficient'}
    raw=[{out:row.get(source) for source,out in price_columns.items()} |
         ({'source_journal_id':str(row['source_journal_id'])} if row.get('source_journal_id') else {}) for row in clean.to_dict('records')]
    price_receipts={}
    for row in clean.to_dict('records'):
        receipt={'source_journal_id':str(row['source_journal_id']) if row.get('source_journal_id') else None,
                 'daily_provenance':row.get('daily_provenance')}
        price_receipts[av.digest(receipt)]=receipt
    clock=datetime.now(timezone.utc)
    config={'rule_version':'earnings-reaction/v2','mode':'strict_as_of' if as_of is not None else 'current_revision_analytics'}
    timing_payload=eps.get('yahoo_timing_payload') or {}
    applicable_timing=[r for r in timing_payload.get('rows',[])
      if pd.Timestamp(r['timestamp']).tz_convert('America/New_York').date()==eps['reported_date']]
    captured_eps={k:v for k,v in eps.items() if k!='yahoo_timing_payload'}
    content={'earnings':captured_eps,'price_inputs':raw,'price_receipts':price_receipts,
             'price_source_quality':'cache_receipts_retained' if all(r.get('source_journal_id') for r in raw) else 'legacy_unlinked',
             'price_basis':'av-adjusted-daily-v1','yahoo_timing':applicable_timing,
             'observed_at':clock.isoformat(),'configuration':config,**av.code_identity()}
    sha=av.digest(content)
    artifact={'artifact_id':sha,'artifact_sha256':sha,'source_as_of':clock,
              'artifact_payload':av.canonical(content).encode(),
              'pipeline_version':av.PIPELINE_VERSION,'configuration_sha256':av.digest(config),
              'rule_version':config['rule_version'],'code_revision':content['code_revision'],
              'source_window_start':str(daily['date'].min()),'source_window_end':str(daily['date'].max()),
              'availability_quality':config['mode'],**daily.attrs.get('immutable_vintage',{})}
    frame=daily.rename(columns={'open':'Open','high':'High','low':'Low','close':'Close','volume':'Volume'})
    basis=prepare_daily_basis(frame,basis_date=max(daily['date']),observed_at=clock,mode=config['mode'],as_of=as_of,input_artifact=artifact)
    analysis=basis.analysis_frame.rename(columns={'Open':'open','High':'high','Low':'low','Close':'close','Volume':'volume'}).copy()
    analysis['atr_14']=None  # Legacy raw-spine ATR cannot certify adjusted windows.
    analysis.attrs['validated_common_basis']=True
    if basis.basis_version!='av-adjusted-daily-v1':
        raise av.SourceError('price_basis_version_unavailable')
    if len(av.canonical(content).encode())>10_000:
        raise av.SourceError('reaction_artifact_byte_limit')
    return analysis,content,sha,config,dict(basis.provenance)


def persist_reaction_group(rows,artifacts,*,executor=None):
    executor=executor or av.isolated_sql
    if not rows or len(rows)>100 or len(artifacts)!=len(rows) or len(av.canonical(artifacts).encode())>1024*1024 or len(av.canonical(rows).encode())>1024*1024:
        raise av.SourceError('reaction_group_limit')
    if any(a['artifact_sha256']!=av.digest(a['payload']) for a in artifacts):raise av.SourceError('reaction_artifact_hash_mismatch')
    if {r['input_artifact_sha256'] for r in rows}!={a['artifact_sha256'] for a in artifacts}:
        raise av.SourceError('reaction_artifact_scope_mismatch')
    columns=[c for c in rows[0] if c not in {'id','inserted_at'}]
    updates=','.join(c+'=excluded.'+c for c in columns if c not in {'ticker','fiscal_date_ending'})
    sql="""WITH requested AS(SELECT * FROM jsonb_populate_recordset(NULL::earnings_reaction_input_artifacts,CAST(:artifacts AS jsonb))),
      inputs AS(INSERT INTO earnings_reaction_input_artifacts SELECT * FROM requested
        ON CONFLICT DO NOTHING RETURNING artifact_sha256,payload),
      matched AS(SELECT DISTINCT q.artifact_sha256 FROM requested q JOIN(
        SELECT artifact_sha256,payload FROM inputs UNION ALL
        SELECT artifact_sha256,payload FROM earnings_reaction_input_artifacts
        WHERE artifact_sha256=ANY(CAST(:hashes AS text[]))) a
        ON a.artifact_sha256=q.artifact_sha256 AND a.payload=q.payload),
      guarded AS(SELECT 1/(CASE WHEN (SELECT count(*) FROM matched)=
        (SELECT count(DISTINCT artifact_sha256) FROM requested) THEN 1 ELSE 0 END) AS identity_ok)
    INSERT INTO earnings_reactions("""+','.join(columns)+") SELECT "+','.join('r.'+c for c in columns)+" FROM jsonb_populate_recordset(NULL::earnings_reactions,CAST(:rows AS jsonb)) r CROSS JOIN guarded g WHERE g.identity_ok=1 ON CONFLICT(ticker,fiscal_date_ending) DO UPDATE SET "+updates
    return executor(sql,{'artifacts':av.canonical(artifacts),'rows':av.canonical(rows),'hashes':[a['artifact_sha256'] for a in artifacts]},timeout_s=8)


def populate_for_tickers(tickers,dry_run=False,*,as_of=None,source_as_of=None,run=None,max_quarters=100,event_scope=None,deadline=None):
    if len(tickers)>100:
        raise av.SourceError('reaction_admission_limit')
    run=run or av.Run('compute-earnings-reactions','daily',expected=len(tickers))
    eps_df=fetch_earnings_history_for_tickers(tickers,as_of=source_as_of or as_of,max_quarters=max_quarters)
    if eps_df.empty:
        return 0
    if event_scope is not None:
        allowed={(e['ticker'],str(e['event_reported_date'])) for e in event_scope}
        eps_df=eps_df.loc[[(r['ticker'],str(r['reported_date'])) in allowed for r in eps_df.to_dict('records')]]
    if len(eps_df)>10000:raise av.SourceError('reaction_financial_row_limit')
    from lib.earnings_history import aware_cutoff
    source_cutoff=aware_cutoff(source_as_of or as_of) if source_as_of or as_of else datetime.now(timezone.utc)
    timing=fetch_reaction_timing_observations(eps_df['yahoo_timing_observation_id'].astype(object).where(eps_df['yahoo_timing_observation_id'].notna(),None).tolist(),cutoff=source_cutoff)
    count=0
    for ticker,group,windows in _iter_reaction_price_batches(eps_df,run=run,deadline=deadline):
        if deadline is not None and __import__('time').monotonic()>=deadline-40:
            run.pending+=eps_df['ticker'].nunique()-len({g.get('ticker') for g in run.groups if g.get('coverage_complete')})
            run.groups.append({'ticker':ticker,'coverage_complete':False,'error_class':'reaction_deadline_pending'})
            break
        rows=[];artifacts=[]
        for _,entry in group.iterrows():
            eps=entry.astype(object).where(entry.notna(),None).to_dict()
            observation=timing.get(str(eps.get('yahoo_timing_observation_id')))
            if observation and observation['ticker']!=ticker:raise av.SourceError('timing_symbol_mismatch')
            eps['yahoo_timing_payload']=observation['payload'] if observation else None
            eps['yahoo_timing_content_sha256']=observation['content_sha256'] if observation else None
            eps['yahoo_timing_known_at']=observation['known_at'] if observation else None
            daily=windows.get(eps['reported_date'],pd.DataFrame())
            run.attempted+=1
            try:
                if deadline is not None and __import__('time').monotonic()>=deadline-32:
                    raise av.SourceError('reaction_deadline_pending')
                if daily.empty:
                    raise av.SourceError('price_depth_unavailable')
                if eps.get('yahoo_timing_observation_id') is not None and not observation:
                    raise av.SourceError('timing_observation_unavailable')
                prepared,payload,sha,config,basis_provenance=prepare_reaction_inputs(eps,daily,as_of=as_of)
                timing=normalize_timing(eps.get('report_time'),None,eps.get('yahoo_report_time'))
                result=compute_reaction(eps,prepared,timing)
                if result is None:
                    raise av.SourceError('reaction_window_unavailable')
                provenance={'source_as_of':as_of.isoformat() if as_of else payload['observed_at'],
                  'source_revision_id':eps['revision_id'],'source_known_at':eps['known_at'],
                  'source_quality':eps['availability_quality'],'price_basis':payload['price_basis'],
                  'price_basis_provenance':basis_provenance,'pipeline_version':av.PIPELINE_VERSION,
                  'configuration':config,'configuration_sha256':av.digest(config),'rule_version':config['rule_version'],
                  'input_artifact_sha256':sha,**av.code_identity()}
                result.update(source_revision_id=eps['revision_id'],source_known_at=eps['known_at'],
                  yahoo_timing_observation_id=eps.get('yahoo_timing_observation_id'),input_artifact_sha256=sha,
                  provenance=provenance,provenance_quality='validated_current_revision' if as_of is None else 'validated_as_of')
                rows.append(result);artifacts.append({'artifact_sha256':sha,'captured_at':datetime.now(timezone.utc),'payload':payload})
            except Exception as exc:
                run.failed+=1
                run.groups.append({'ticker':ticker,'fiscal_date_ending':str(eps['fiscal_date_ending']),
                  'coverage_complete':False,'error_class':str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__})
        if rows and not dry_run:
            persist_reaction_group(rows,artifacts)
            run.rows_written+=len(rows)
        count+=len(rows);run.processed+=len(rows)
        if rows:
            run.groups.append({'ticker':ticker,'rows_written':len(rows),'coverage_complete':not any(
                g.get('ticker')==ticker and not g.get('coverage_complete') for g in run.groups)})
    return count


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


def _tickers_reporting_in_window(window_days: int) -> set:
    """Tickers in earnings_calendar with earnings_date in [today, today+window]."""
    try:
        # Anchor the window in America/New_York, NOT the DB session timezone.
        # Cloud SQL Postgres is set to UTC (verified `SHOW timezone` returns
        # 'UTC') and these jobs are scheduled at 7:30 PM ET. During EST
        # (UTC-5, Nov–Mar) that's 00:30 UTC the NEXT day, so a bare
        # CURRENT_DATE returns tomorrow's reporters and reactions for the
        # tickers that just reported tonight get skipped. During EDT (UTC-4)
        # 19:30 ET = 23:30 UTC, same calendar day, so the bug is dormant —
        # but anchoring in ET removes the seasonal failure mode.
        df = query_to_dataframe(
            """
            SELECT DISTINCT ticker
            FROM earnings_calendar
            WHERE earnings_date BETWEEN (NOW() AT TIME ZONE 'America/New_York')::date
                AND (NOW() AT TIME ZONE 'America/New_York')::date + (:days || ' days')::interval
            """,
            {"days": int(window_days)},
        )
    except Exception as e:
        log.warning("report-window lookup failed (%s)", e)
        return set()
    if df is None or df.empty:
        return set()
    return {str(t).upper() for t in df['ticker'].tolist()}


def _resolve_scope(cli_scope=None) -> str:
    """'weekly' on Sundays or when overridden; else 'daily'."""
    if cli_scope in ('daily', 'weekly'):
        return cli_scope
    import os as _os
    env = _os.environ.get('PIPELINE_SCOPE', '').strip().lower()
    if env in ('daily', 'weekly'):
        return env
    from datetime import datetime as _dt
    return 'weekly' if _dt.now().weekday() == 6 else 'daily'


def _filter_already_have_reactions(
    tickers, force_set=None,
):
    """Skip tickers with existing reactions UNLESS in force_set.

    force_set: tickers reporting in the current run's window — always
    re-compute these (their just-released quarter needs a new reaction
    row).
    """
    if not tickers:
        return tickers, 0
    force_set = force_set or set()
    try:
        df = query_to_dataframe(
            "SELECT DISTINCT ticker FROM earnings_reactions WHERE ticker = ANY(:t)",
            {"t": tickers},
        )
    except Exception as e:
        log.warning("earnings_reactions skip-check failed (%s) — computing all", e)
        return tickers, 0
    if df is None or df.empty:
        return tickers, 0
    already = {str(t).upper() for t in df['ticker'].tolist()}
    remaining = [t for t in tickers if t not in already or t in force_set]
    n_skipped = len(tickers) - len(remaining)
    return remaining, n_skipped


def eligible_history_manifest(as_of=None,*,variant="daily"):
    cutoff=as_of or datetime.now(timezone.utc)
    from lib.earnings_history import aware_cutoff
    cutoff=aware_cutoff(cutoff)
    facts=av.isolated_sql("""SELECT m.manifest_id,m.execution_name,m.manifest,p.known_at,j.note AS terminal_note,j.status AS terminal_status
      FROM av_catalyst_source_manifests m JOIN av_catalyst_manifest_publications p USING(manifest_id)
      LEFT JOIN LATERAL(SELECT note,status FROM job_runs r WHERE r.job_name=m.job_name AND r.variant=m.variant
        AND r.execution_name=m.execution_name AND r.finished_at<=:cutoff
        AND r.note::jsonb->>'source_manifest_id'=m.manifest_id::text ORDER BY r.finished_at DESC,r.id DESC LIMIT 1) j ON true
      WHERE m.job_name='fetch-earnings-history' AND m.variant=:variant AND p.known_at<=:cutoff
      ORDER BY p.known_at DESC,m.manifest_id DESC LIMIT 1""",{'cutoff':cutoff,'variant':variant},read=True,timeout_s=8)
    if not facts:
        raise av.SourceError('history_predecessor_coverage_unavailable')
    source=facts[0];manifest=source['manifest']
    if (not manifest.get('event_cohort_complete') or manifest.get('source_scope_quality')!='observed_snapshot'
        or manifest.get('coverage_complete') is not False or manifest.get('complete_through') is not None
        or manifest.get('independent_expected_cohort_proof') is not None
        or manifest.get('full_current_cohort_status')!='dependency_pending'
        or manifest.get('scope_hash')!=av.manifest_digest(av.event_scope(manifest['expected_events']))
        or manifest.get('source_universe_scope_hash')!=av.manifest_digest(av.symbol_scope(manifest['configured_universe']))
        or source['terminal_status'] not in {'success','no_data','partial'} or not source['terminal_note']):
        raise av.SourceError('history_predecessor_coverage_unavailable')
    note=av.parse_manifest_json(source['terminal_note'])
    if (note.get('manifest_sha256')!=av.manifest_digest(manifest)
        or note.get('manifest_bytes')!=len(av.manifest_bytes(manifest))
        or av.clock_string(note.get('source_manifest_known_at'))!=av.clock_string(source['known_at'])
        or note.get('failed')!=0):raise av.SourceError('history_predecessor_terminal_unavailable')
    source.pop('terminal_note');source.pop('terminal_status')
    return facts[0]


def publish_reactions_manifest(run,history_manifest,*,selected=None,executor=None):
    executor=executor or av.isolated_sql
    manifest=history_manifest['manifest']
    selected=av.symbol_scope(selected or [])
    if len(selected)>100 or not set(selected)<=set(manifest['configured_universe']):raise av.SourceError('reaction_selected_scope')
    events=manifest.get('expected_events',[])
    # Assess the full inherited scope in one indexed batch, including events
    # outside this bounded invocation. Existing verified revisions can qualify.
    facts=executor("""SELECT e.ticker,e.event_reported_date,
      r.source_revision_id,r.provenance_quality,r.input_artifact_sha256,
      r.provenance->>'configuration_sha256' AS configuration_sha256
      FROM jsonb_to_recordset(CAST(:events AS jsonb)) e(ticker text,event_reported_date date,revision_id bigint)
      LEFT JOIN earnings_reactions r ON r.ticker=e.ticker AND r.reported_date=e.event_reported_date
      AND r.source_revision_id=e.revision_id AND r.source_known_at<=:history_known_at
      AND r.provenance_quality='validated_current_revision'
      AND r.provenance->>'configuration_sha256' ~ '^[0-9a-f]{64}$'
      AND EXISTS(SELECT 1 FROM earnings_reaction_input_artifacts a WHERE a.artifact_sha256=r.input_artifact_sha256
        AND a.payload->'earnings'->>'ticker'=e.ticker
        AND (a.payload->'earnings'->>'revision_id')::bigint=e.revision_id
        AND (a.payload->'earnings'->>'reported_date')::date=e.event_reported_date
        AND (a.payload->'earnings'->>'fiscal_date_ending')::date=r.fiscal_date_ending
        AND (a.payload->'earnings'->>'known_at')::timestamptz=r.source_known_at
        AND a.payload->'configuration'=r.provenance->'configuration'
        AND a.payload->>'price_basis'='av-adjusted-daily-v1'
        AND a.payload->'configuration'->>'mode'='current_revision_analytics')
      ORDER BY e.ticker,e.event_reported_date""",
      {'events':av.canonical(manifest['verified_events']),'history_known_at':history_manifest['known_at']},read=True,timeout_s=8)
    verified=[f for f in facts if f['source_revision_id'] is not None]
    source_facts=sorted([{key:(str(f[key]) if key=='event_reported_date' else f[key]) for key in
        ('ticker','event_reported_date','source_revision_id','input_artifact_sha256','configuration_sha256')} for f in verified],
        key=lambda f:(f['ticker'],f['event_reported_date'],f['source_revision_id'],av.manifest_bytes(f)))
    result={"schema_version":"av_catalyst_run/v1","pipeline_scope":run.mode,
      "scope_hash":manifest['scope_hash'],"universe_count":manifest['universe_count'],
      "configured_universe":manifest['configured_universe'],"expected_events":events,
      "source_window_start":manifest['source_window_start'],"source_window_end":manifest['source_window_end'],
      "complete_through":None,"coverage_complete":False,
      "requested_count":len(events),"verified_count":len(verified),"excluded_count":0,
      "pending_count":len(events)-len(verified),"event_pending_count":len(events)-len(verified),
      "source_revision_ids":[f['source_revision_id'] for f in verified],
      "source_scope_quality":"observed_snapshot","source_scope_proofs":manifest['source_scope_proofs'],
      "assessment_cutoff":av.clock_string(datetime.now(timezone.utc)),
      "independent_expected_cohort_proof":None,"source_universe_unknown_count":manifest['source_universe_unknown_count'],
      "source_universe_scope_hash":manifest['source_universe_scope_hash'],
      "selected_count":len(selected),"selected_scope_hash":av.manifest_digest(selected),
      "full_current_cohort_status":"dependency_pending","full_scope_reason":"independent_cohort_proof_unavailable",
      "event_cohort_complete":len(verified)==len(events) and not run.failed,
      "raw_refresh_pending":run.pending,"raw_refresh_status":run.status,
      "observed_source_facts":source_facts,"source_digest":av.manifest_digest(source_facts),
      "source_digest_kind":"canonical_source_facts/v1","predecessor_execution_name":history_manifest['execution_name'],
      "history_source_manifest_id":str(history_manifest['manifest_id']),
      "history_source_manifest_known_at":av.clock_string(history_manifest['known_at']),
      "history_source_manifest_sha256":av.manifest_digest(manifest),**av.code_identity()}
    return av.publish_manifest(run,result)


def main(argv=None):
    parser=argparse.ArgumentParser(description="Bounded source-qualified reaction generation")
    parser.add_argument('--tickers')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--force',action='store_true')
    parser.add_argument('--scope',choices=['daily','weekly'])
    parser.add_argument('--max-tickers',type=int,default=100)
    parser.add_argument('--max-quarters',type=int,default=100)
    parser.add_argument('--as-of')
    args=parser.parse_args(argv)
    run=av.Run('compute-earnings-reactions',_resolve_scope(args.scope))
    deadline=__import__('time').monotonic()+450
    manifest=None
    try:
        cutoff=datetime.fromisoformat(args.as_of.replace('Z','+00:00')) if args.as_of else None
        if cutoff is not None:
            from lib.earnings_history import aware_cutoff
            aware_cutoff(cutoff)
            raise av.SourceError('price_vintage_unavailable')  # Existing SQL cache has no immutable vintage reader.
        if not 1<=args.max_tickers<=100 or not 1<=args.max_quarters<=100:
            raise av.SourceError('reaction_admission_limit')
        predecessor=eligible_history_manifest(variant=run.mode)
        universe=sorted({t.strip().upper() for t in args.tickers.split(',') if t.strip()}) if args.tickers else predecessor['manifest']['configured_universe']
        eligible=sorted({e['ticker'] for e in predecessor['manifest']['expected_events']} & set(universe))
        run.expected=len(eligible)
        selected=av.claim_work('EARNINGS_REACTIONS',eligible,run.mode,run.execution_name,limit=args.max_tickers,force=args.force,dry_run=args.dry_run)
        run.pending=len(eligible)-len(selected)
        populate_for_tickers(selected,dry_run=args.dry_run,source_as_of=predecessor['known_at'],run=run,max_quarters=args.max_quarters,
                             event_scope=predecessor['manifest']['expected_events'],deadline=deadline)
        if not args.dry_run:
            outcomes=[{'ticker':t,'success':any(g.get('ticker')==t and g.get('coverage_complete') for g in run.groups) and not any(g.get('ticker')==t and not g.get('coverage_complete') for g in run.groups),
                       'observed_at':datetime.now(timezone.utc).isoformat()} for t in selected]
            av.finish_work('EARNINGS_REACTIONS',run.mode,outcomes,owner=run.execution_name)
            manifest=publish_reactions_manifest(run,predecessor,selected=selected)
    except Exception as exc:
        run.failed+=1
        run.groups.append({'coverage_complete':False,'error_class':str(exc) if isinstance(exc,av.SourceError) else type(exc).__name__})
    try:
        return run.terminal(dry_run=args.dry_run,extra=manifest)
    finally:
        av.close_sql_worker()


if __name__=='__main__':
    raise SystemExit(main())
