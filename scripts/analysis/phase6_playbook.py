#!/usr/bin/env python3
"""
Phase 6: Beginner's Playbook — Per-Ticker Decision Cards

Generates 12 decision cards per ticker (36 total) in plain English "If-Then" format.
Each card is populated with actual data from Phases 1-5.

Output: reports/phase6_playbook_{ticker}.md + reports/phase6_playbook_combined.md
"""

import sys
import os
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timezone, date as date_cls, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.analysis.shared_utils import (
    TICKERS, REPORTS_DIR,
    load_ticker_1m, enrich_with_indicators, classify_strat_series,
    build_multi_timeframe_dict, get_trading_dates,
    md_header, md_table, fmt_pct, fmt_bps, fmt_num, save_report,
    timestamp_str, sample_size_label, progress,
    IndicatorConfig, ExitConfig,
)


# ---------------------------------------------------------------------------
# Per-ticker target/stop/hold profile
#
# One source of truth for BOTH the displayed target/stop strings AND the
# basis-point thresholds fed to compute_card_stats. Previously the display
# strings were per-ticker but the backtest bps were hardcoded to IWM's
# 30/15 (CALL) and 38/20 (PUT) for every ticker, so a SPY card claimed
# "+0.15%" while being scored at 30 bps. Now that compute_card_stats
# actually uses the bps, the two must agree. Adding a ticker is a config
# edit here, not a code change in build_all_cards. Unknown tickers get an
# explicit default (not silently IWM's or QQQ's numbers).
# ---------------------------------------------------------------------------

TICKER_PROFILES: Dict[str, Dict[str, float]] = {
    'IWM': {'call_target': 30, 'call_stop': 15, 'put_target': 38, 'put_stop': 20, 'hold': '10-15 min'},
    'SPY': {'call_target': 15, 'call_stop': 10, 'put_target': 20, 'put_stop': 12, 'hold': '12-18 min'},
    'QQQ': {'call_target': 25, 'call_stop': 12, 'put_target': 25, 'put_stop': 12, 'hold': '10-15 min'},
}
DEFAULT_TICKER_PROFILE: Dict[str, float] = {
    'call_target': 25, 'call_stop': 12, 'put_target': 25, 'put_stop': 12, 'hold': '10-15 min',
}


def get_ticker_profile(ticker: str) -> Dict[str, float]:
    """Return the target/stop/hold profile for a ticker (explicit default)."""
    return TICKER_PROFILES.get(ticker.upper(), DEFAULT_TICKER_PROFILE)


# ---------------------------------------------------------------------------
# Card data computation
# ---------------------------------------------------------------------------

# Hold-window horizons (minutes) swept for every card so the UI can show
# win rate / avg return BY timeframe and surface the best-avg-return hold.
HOLD_HORIZONS = (5, 15, 30, 60)


def compute_card_stats(df: pd.DataFrame, labels: pd.Series,
                       pattern_mask: pd.Series, direction: str,
                       target_bps: float, stop_bps: float,
                       time_stop_min: int = 30,
                       horizons=HOLD_HORIZONS) -> Dict:
    """Score the card at its primary hold and attach a per-horizon sweep.

    The primary stats (win_rate, avg_return_bps, …) are computed at
    ``time_stop_min`` exactly as before. The SAME target/stop is then scored at
    each hold window in ``horizons`` and attached so the card can show win rate
    / avg return BY timeframe:

      * ``horizons``     — list of {minutes, win_rate, avg_return_bps, sample_n}
      * ``best_horizon`` — the entry with the highest avg_return_bps among
                           horizons that resolved at least one trade.

    All returns are price-only basis points — NO costs (commission / slippage /
    spread) are modelled anywhere.
    """
    primary = _score_trades(df, labels, pattern_mask, direction,
                            target_bps, stop_bps, time_stop_min)
    if primary.get('count', 0) == 0:
        return primary

    sweep = []
    for h in horizons:
        s = _score_trades(df, labels, pattern_mask, direction,
                          target_bps, stop_bps, h)
        sweep.append({
            'minutes': int(h),
            'win_rate': s.get('win_rate'),
            'avg_return_bps': s.get('avg_return_bps'),
            'sample_n': int(s.get('resolved') or 0),
        })
    primary['horizons'] = sweep

    valid = [x for x in sweep
             if x['sample_n'] and x['avg_return_bps'] is not None
             and not pd.isna(x['avg_return_bps'])]
    if valid:
        primary['best_horizon'] = max(valid, key=lambda x: x['avg_return_bps'])
    return primary


def _score_trades(df: pd.DataFrame, labels: pd.Series,
                  pattern_mask: pd.Series, direction: str,
                  target_bps: float, stop_bps: float,
                  time_stop_min: int = 30) -> Dict:
    """Compute triggered target/stop/time-stop statistics for one card.

    Each pattern occurrence is treated as a trade entered at the close of
    the signal bar and exited by the FIRST of:

      * **target** — price moves ``target_bps`` in the trade's favour,
      * **stop**   — price moves ``stop_bps`` against the trade,
      * **time-stop** — neither is touched within ``time_stop_min`` bars,
        in which case the trade is marked-to-close at the time-stop bar.

    Target/stop touches are detected intrabar from High/Low. When both the
    target and the stop fall inside the SAME bar the stop is assumed first
    (pessimistic — we cannot see intrabar sequencing). The forward window
    is clipped to the signal bar's own trading session so an overnight gap
    never counts as part of the trade (the old next-bar proxy silently let
    it through).

    ``win_rate`` is wins / resolved-trades and ``avg_return_bps`` is the
    mean realised per-trade return in basis points under that exit logic —
    NOT the old "did the next 1-minute bar tick up" proxy, which ignored
    the card's own ``target_bps`` / ``stop_bps`` entirely.

    Returns ``{'count': 0}`` when the pattern never occurs. Occurrences
    with no same-session forward bar are excluded from the denominator and
    counted in ``skipped_insufficient_bars`` — no silent coercion to zero
    (CLAUDE.md §3.7).
    """
    close = df['Close'] if 'Close' in df.columns else df['Last']
    high = df['High'] if 'High' in df.columns else close
    low = df['Low'] if 'Low' in df.columns else close

    n = int(pattern_mask.sum())
    if n == 0:
        return {'count': 0}

    # Bound forward windows to the signal bar's own session so overnight
    # gaps don't leak into a trade's path.
    trade_dates = np.asarray(get_trading_dates(df))
    close_v = close.to_numpy(dtype=float)
    high_v = high.to_numpy(dtype=float)
    low_v = low.to_numpy(dtype=float)
    n_rows = len(close_v)

    indices = df.index[pattern_mask]
    realized_bps: List[float] = []   # per-trade realised return (bps)
    win_flags: List[bool] = []
    mfe_list: List[float] = []
    mae_list: List[float] = []
    skipped = 0

    def _pos(idx):
        p = df.index.get_loc(idx)
        return p.start if isinstance(p, slice) else p

    for idx in indices:
        pos = _pos(idx)
        entry = close_v[pos]
        if not np.isfinite(entry) or entry <= 0:
            skipped += 1
            continue

        end = min(pos + time_stop_min + 1, n_rows)
        sess = trade_dates[pos]
        fwd_idx = [j for j in range(pos + 1, end) if trade_dates[j] == sess]
        if not fwd_idx:
            skipped += 1
            continue

        tgt = entry * (1 + target_bps / 1e4) if direction == 'CALL' \
            else entry * (1 - target_bps / 1e4)
        stp = entry * (1 - stop_bps / 1e4) if direction == 'CALL' \
            else entry * (1 + stop_bps / 1e4)

        outcome = None
        mfe = 0.0
        mae = 0.0
        for j in fwd_idx:
            hi, lo = high_v[j], low_v[j]
            if direction == 'CALL':
                mfe = max(mfe, (hi - entry) / entry * 1e4)
                mae = min(mae, (lo - entry) / entry * 1e4)
                hit_stop = lo <= stp
                hit_tgt = hi >= tgt
            else:
                mfe = max(mfe, (entry - lo) / entry * 1e4)
                mae = min(mae, (entry - hi) / entry * 1e4)
                hit_stop = hi >= stp
                hit_tgt = lo <= tgt
            if hit_stop:                      # stop assumed first within a bar
                outcome = -stop_bps
                break
            if hit_tgt:
                outcome = target_bps
                break

        if outcome is None:                   # time-stop: mark to close
            last = fwd_idx[-1]
            if direction == 'CALL':
                outcome = (close_v[last] - entry) / entry * 1e4
            else:
                outcome = (entry - close_v[last]) / entry * 1e4

        realized_bps.append(float(outcome))
        win_flags.append(bool(outcome > 0))
        mfe_list.append(mfe)
        mae_list.append(mae)

    resolved = len(realized_bps)
    if resolved == 0:
        return {'count': n, 'resolved': 0,
                'skipped_insufficient_bars': skipped,
                'win_rate': np.nan, 'avg_return_bps': np.nan,
                'confidence': sample_size_label(0)}

    win_rate = float(np.mean(win_flags))
    avg_return = float(np.mean(realized_bps))

    # Diagnostic forward-horizon means (same-session, target/stop-agnostic)
    fwd_returns = {}
    for p in [5, 10, 15, 30]:
        vals = []
        for idx in indices:
            pos = _pos(idx)
            tp = pos + p
            if tp >= n_rows or trade_dates[tp] != trade_dates[pos]:
                continue
            ep = close_v[pos]
            if ep <= 0:
                continue
            r = (close_v[tp] - ep) / ep * 1e4
            vals.append(r if direction == 'CALL' else -r)
        fwd_returns[p] = float(np.mean(vals)) if vals else np.nan

    return {
        'count': n,
        'resolved': resolved,
        'skipped_insufficient_bars': skipped,
        'win_rate': win_rate,
        'avg_return_bps': avg_return,
        'fwd_5': fwd_returns.get(5, np.nan),
        'fwd_10': fwd_returns.get(10, np.nan),
        'fwd_15': fwd_returns.get(15, np.nan),
        'fwd_30': fwd_returns.get(30, np.nan),
        'avg_mfe': float(np.mean(mfe_list)) if mfe_list else np.nan,
        'avg_mae': float(np.mean(mae_list)) if mae_list else np.nan,
        'confidence': sample_size_label(resolved),
    }


# ---------------------------------------------------------------------------
# Card definitions
# ---------------------------------------------------------------------------

def generate_card(card_num: int, title: str, ticker: str,
                  visual_setup: str, checklist: List[str],
                  direction: str, stats: Dict,
                  target_pct: str, stop_pct: str,
                  hold_time: str, warnings: List[str],
                  ticker_notes: List[str]) -> Tuple[str, Dict]:
    """Generate a single playbook card.

    Returns ``(markdown, record)`` — the human-readable markdown card AND a
    structured record dict. The record is the source of truth the
    ``playbook_cards`` table (and hence ``/api/playbook``) is built from, so the
    UI reads typed columns instead of regex-scraping the prose. Both come from
    the same inputs, so they cannot drift.
    """

    card = f"\n---\n\n"
    card += md_header(f"{ticker} CARD {card_num}: {title}", 3)

    # What you see
    card += "**WHAT YOU SEE ON THE CHART:**\n"
    card += visual_setup + "\n\n"

    # Checklist
    card += "**WHAT TO CHECK:**\n"
    for item in checklist:
        card += f"  - [ ] {item}\n"
    card += "\n"

    # Entry — win_rate/avg_return are computed under the card's own
    # target/stop/time-stop exit (see compute_card_stats). They are NaN only
    # when the pattern never resolved a same-session trade.
    resolved = stats.get('resolved', stats.get('count', 0))
    wr = stats.get('win_rate')
    if stats['count'] > 0 and resolved and wr is not None and not pd.isna(wr):
        card += f"**IF ALL CONFIRMED -> {direction} ENTRY**\n"
        card += f"  - Confidence: {stats['confidence']} (n={resolved:,} resolved trades)\n"
        card += f"  - Historical win rate: {wr:.1%} (target {target_pct} before stop {stop_pct})\n"
        card += f"  - Avg return: {fmt_bps(stats['avg_return_bps'])} (per trade)\n"
        card += f"  - Target: {target_pct}\n"
        card += f"  - Stop: {stop_pct}\n"
        card += f"  - Expected hold: {hold_time}\n"
        card += f"  - Avg MFE: {fmt_bps(stats['avg_mfe'])}\n"
        card += f"  - Avg MAE: {fmt_bps(stats['avg_mae'])}\n"
        # Win rate / avg return BY hold window (price-only, no costs).
        sweep = stats.get('horizons') or []
        if sweep:
            cells = []
            for h in sweep:
                hw = h.get('win_rate'); ha = h.get('avg_return_bps')
                hw = '—' if hw is None or pd.isna(hw) else f"{hw:.0%}"
                ha = '—' if ha is None or pd.isna(ha) else fmt_bps(ha)
                cells.append(f"{h['minutes']}min {hw}/{ha}")
            card += f"  - By hold window: {' | '.join(cells)}\n"
        best = stats.get('best_horizon')
        if best:
            bw = best.get('win_rate')
            bw = '—' if bw is None or pd.isna(bw) else f"{bw:.1%}"
            card += (f"  - Best avg return: {best['minutes']}-min hold "
                     f"({bw} win, {fmt_bps(best['avg_return_bps'])})\n")
        card += "\n"
    else:
        card += f"**IF ALL CONFIRMED -> {direction} ENTRY**\n"
        card += f"  - Insufficient data for this pattern on {ticker}\n\n"

    # Warnings
    card += "**REVERSAL WARNING SIGNS (exit early):**\n"
    for w in warnings:
        card += f"  - {w}\n"
    card += "\n"

    # Ticker notes
    card += f"**{ticker}-SPECIFIC NOTES:**\n"
    for note in ticker_notes:
        card += f"  - {note}\n"
    card += "\n"

    # Structured record — mirrors what the markdown displays, but typed.
    # win_rate is a fraction in [0, 1]; avg_return_bps is per-trade bps. Both
    # are None (not 0) when the pattern never resolved a same-session trade —
    # missing must never be confused with a real value (CLAUDE.md §3.7).
    desc_bullets = [
        ln.strip().lstrip('*').strip()
        for ln in visual_setup.splitlines() if ln.strip()
    ]

    def _num(v):
        return None if v is None or pd.isna(v) else float(v)

    # Per-hold-window sweep + best-avg-return hold (price-only, no costs).
    sweep = [
        {'minutes': h['minutes'], 'win_rate': _num(h.get('win_rate')),
         'avg_return_bps': _num(h.get('avg_return_bps')),
         'sample_n': int(h.get('sample_n') or 0)}
        for h in (stats.get('horizons') or [])
    ]
    best = stats.get('best_horizon') or {}

    record = {
        'card_num': card_num,
        'name': f"{ticker} CARD {card_num}: {title}",
        'direction': direction,
        'description': '; '.join(desc_bullets[:3]),
        'conditions': list(checklist),
        'win_rate': _num(stats.get('win_rate')),
        'avg_return_bps': _num(stats.get('avg_return_bps')),
        'sample_n': int(stats.get('resolved') or 0) or None,
        'target_pct': target_pct,
        'stop_pct': stop_pct,
        'avg_mfe_bps': _num(stats.get('avg_mfe')),
        'avg_mae_bps': _num(stats.get('avg_mae')),
        'confidence': stats.get('confidence'),
        'horizons': sweep,
        'best_horizon_min': int(best['minutes']) if best.get('minutes') is not None else None,
        'best_horizon_win_rate': _num(best.get('win_rate')),
        'best_horizon_avg_bps': _num(best.get('avg_return_bps')),
    }

    return card, record


def build_all_cards(ticker: str, df: pd.DataFrame,
                    labels: pd.Series) -> Tuple[str, List[Dict]]:
    """Build all 12 playbook cards for a ticker.

    Returns ``(markdown, records)`` — the concatenated markdown report and the
    list of structured card records (one per card) for ``playbook_cards``.
    """
    report = ""
    card_records: List[Dict] = []

    def card(*args, **kwargs):
        """Collect each card's structured record while accumulating markdown."""
        md, rec = generate_card(*args, **kwargs)
        card_records.append(rec)
        return md

    ind = IndicatorConfig()
    rsi_col = ind.rsi_col
    close = df['Close'] if 'Close' in df.columns else df['Last']

    rsi = df.get(rsi_col, pd.Series(50, index=df.index))
    vwap_pos = df.get('Price_vs_VWAP', pd.Series(0, index=df.index))
    ema_cross = df.get('EMA_Cross', pd.Series(0, index=df.index))
    orb_trend = df.get('ORB_30m_Trend', pd.Series(0, index=df.index))
    stoch_k = df.get('StochRSI_K', pd.Series(50, index=df.index))
    rvol = df.get('RVOL', pd.Series(1.0, index=df.index))

    prev = labels.shift(1)
    prev2 = labels.shift(2)
    next_label = labels.shift(-1)

    # Per-ticker target/stop/hold profile — single source for both the
    # displayed strings and the backtest bps (see TICKER_PROFILES).
    prof = get_ticker_profile(ticker)
    ct_bps, cs_bps = prof['call_target'], prof['call_stop']
    pt_bps, ps_bps = prof['put_target'], prof['put_stop']
    hold_time = prof['hold']
    call_target = f"+{ct_bps / 100:.2f}%"
    call_stop = f"-{cs_bps / 100:.2f}%"
    put_target = f"+{pt_bps / 100:.2f}%"
    put_stop = f"-{ps_bps / 100:.2f}%"

    # --- CARD 1: Bullish Continuation (2U-2U-2U) ---
    mask = (prev2 == '2U') & (prev == '2U') & (labels == '2U')
    stats = compute_card_stats(df, labels, mask, 'CALL', ct_bps, cs_bps)
    report += card(
        1, "Bullish Continuation (2U-2U-2U)", ticker,
        "  * Daily bar is 2U (higher high, higher low)\n"
        "  * 15m bar is 2U\n"
        "  * 1m shows: 2U -> 2U -> 2U (three consecutive bullish bars)",
        [
            f"RSI between 40-65 (not overbought yet)",
            "Price above VWAP",
            f"Price above EMA{ind.ema_fast_period}",
            "ORB 30m trend is bullish",
            f"EMA{ind.ema_fast_period} > EMA{ind.ema_mid_period} (bullish cross)",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "RSI crosses above 75 -> take profit",
            "1m bar prints 2D -> tighten stop to breakeven",
            "RVOL drops below 0.8 -> momentum fading",
            "Price hits prev day/week high -> resistance",
        ],
        _get_ticker_notes(ticker, 'bullish_continuation'),
    )

    # --- CARD 2: Bearish Continuation (2D-2D-2D) ---
    mask = (prev2 == '2D') & (prev == '2D') & (labels == '2D')
    stats = compute_card_stats(df, labels, mask, 'PUT', pt_bps, ps_bps)
    report += card(
        2, "Bearish Continuation (2D-2D-2D)", ticker,
        "  * Daily bar is 2D (lower high, lower low)\n"
        "  * 15m bar is 2D\n"
        "  * 1m shows: 2D -> 2D -> 2D (three consecutive bearish bars)",
        [
            "RSI between 35-60 (not oversold yet)",
            "Price below VWAP",
            f"Price below EMA{ind.ema_fast_period}",
            "ORB 30m trend is bearish",
            f"EMA{ind.ema_fast_period} < EMA{ind.ema_mid_period} (bearish cross)",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "RSI crosses below 25 -> take profit",
            "1m bar prints 2U -> tighten stop to breakeven",
            "RVOL drops below 0.8 -> selling pressure fading",
            "Price hits prev day/week low -> support",
        ],
        _get_ticker_notes(ticker, 'bearish_continuation'),
    )

    # --- CARD 3: Bullish Reversal 2-1-2 ---
    mask = (prev2 == '2D') & (prev == '1') & (labels == '2U')
    stats = compute_card_stats(df, labels, mask, 'CALL', ct_bps, cs_bps)
    report += card(
        3, "Bullish Reversal (2D-1-2U)", ticker,
        "  * Previous bars: 2D (bearish) -> 1 (inside bar compression)\n"
        "  * Current bar: Breaking above the inside bar's high (2U)",
        [
            "RSI < 45 (was oversold from the 2D move)",
            "Price at or near support level (prev day low, VWAP, order block)",
            "StochRSI was oversold (< 20), now turning up",
            "Volume confirming (RVOL > 1.0)",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "If breakout fails and price drops back inside the 1 bar -> exit immediately",
            "RSI fails to cross above 50 -> weak reversal",
            "No volume on breakout -> likely false breakout",
        ],
        _get_ticker_notes(ticker, 'bullish_reversal'),
    )

    # --- CARD 4: Bearish Reversal 2-1-2 ---
    mask = (prev2 == '2U') & (prev == '1') & (labels == '2D')
    stats = compute_card_stats(df, labels, mask, 'PUT', pt_bps, ps_bps)
    report += card(
        4, "Bearish Reversal (2U-1-2D)", ticker,
        "  * Previous bars: 2U (bullish) -> 1 (inside bar compression)\n"
        "  * Current bar: Breaking below the inside bar's low (2D)",
        [
            "RSI > 55 (was overbought from the 2U move)",
            "Price at or near resistance (prev day high, upper BB)",
            "StochRSI was overbought (> 80), now turning down",
            "Volume confirming (RVOL > 1.0)",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "If price recovers back above inside bar's low -> exit immediately",
            "RSI fails to cross below 50 -> weak reversal",
            "No volume on breakdown -> likely false breakdown",
        ],
        _get_ticker_notes(ticker, 'bearish_reversal'),
    )

    # --- CARD 5: Outside Bar Breakout (Type 3) ---
    mask = labels == '3'
    bullish_3 = mask & (close > close.shift(1))
    stats_bull = compute_card_stats(df, labels, bullish_3, 'CALL', ct_bps, cs_bps)
    report += card(
        5, "Outside Bar Breakout (Type 3 Bullish)", ticker,
        "  * Current bar is Type 3 (higher high AND lower low than prev bar)\n"
        "  * Close is above previous bar's close (bullish resolution)",
        [
            "RSI between 40-60 (room to run)",
            "Close in upper half of the bar's range",
            "Volume above average (RVOL > 1.2)",
            "Higher timeframe supports the direction",
        ],
        'CALL', stats_bull, call_target, call_stop, hold_time,
        [
            "If next bar is Type 1 (inside) -> tighten stop",
            "Price drops below midpoint of the 3 bar -> exit",
            "Outside bars often exhaust moves -> be ready for reversal",
        ],
        _get_ticker_notes(ticker, 'outside_bar'),
    )

    # --- CARD 6: ORB Breakout Bullish ---
    mask = (orb_trend == 1) & (labels.isin(['2U', '3']))
    stats = compute_card_stats(df, labels, mask, 'CALL', ct_bps, cs_bps)
    report += card(
        6, "ORB Breakout — Bullish", ticker,
        "  * Price has broken above 30m Opening Range High\n"
        "  * Current Strat bar confirms: 2U or 3",
        [
            "RSI not overbought (< 70)",
            "Price above VWAP",
            f"EMA{ind.ema_fast_period} > EMA{ind.ema_mid_period}",
            "RVOL > 1.0 (volume confirming breakout)",
            "At least 30 min after market open",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Price returns inside ORB range -> failed breakout, exit",
            "Declining volume on continuation -> fade risk",
            "Approaching prev day/week high -> resistance ahead",
        ],
        _get_ticker_notes(ticker, 'orb_breakout'),
    )

    # --- CARD 7: ORB Breakout Bearish ---
    mask = (orb_trend == -1) & (labels.isin(['2D', '3']))
    stats = compute_card_stats(df, labels, mask, 'PUT', pt_bps, ps_bps)
    report += card(
        7, "ORB Breakout — Bearish", ticker,
        "  * Price has broken below 30m Opening Range Low\n"
        "  * Current Strat bar confirms: 2D or 3",
        [
            "RSI not oversold (> 30)",
            "Price below VWAP",
            f"EMA{ind.ema_fast_period} < EMA{ind.ema_mid_period}",
            "RVOL > 1.0",
            "At least 30 min after market open",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "Price returns inside ORB range -> failed breakdown, exit",
            "RSI reaching extreme oversold -> bounce risk",
            "Approaching prev day/week low -> support ahead",
        ],
        _get_ticker_notes(ticker, 'orb_breakdown'),
    )

    # --- CARD 8: ORB Failure / Mean Reversion ---
    # Detect bars that went above ORB high then came back within
    if 'ORB_30m_High' in df.columns and 'ORB_30m_Low' in df.columns:
        was_above = close.shift(1) > df['ORB_30m_High']
        now_within = (close <= df['ORB_30m_High']) & (close >= df['ORB_30m_Low'])
        mask = was_above & now_within & (labels == '2D')
    else:
        mask = pd.Series(False, index=df.index)
    mr_target_bps = 20  # mean-reversion uses a tighter fixed target than the trend profile
    stats = compute_card_stats(df, labels, mask, 'PUT', mr_target_bps, ps_bps)
    report += card(
        8, "ORB Failure / Mean Reversion", ticker,
        "  * Price broke above ORB high, then FAILED and returned inside range\n"
        "  * Current Strat shows 2D (confirming the failure)",
        [
            "RSI was elevated (> 60) at breakout",
            "Volume declining on the failed breakout",
            "Strat shows reversal (2D after 2U or 3)",
            "VWAP is nearby (target)",
        ],
        'PUT', stats, f"+{mr_target_bps / 100:.2f}%", put_stop, '8-15 min',
        [
            "Price re-breaks ORB high -> failure of the failure, exit",
            "Price hits ORB mid and stalls -> take partial profit",
            "RSI crosses below 40 -> full reversal, let it run",
        ],
        _get_ticker_notes(ticker, 'orb_failure'),
    )

    # --- CARD 9: Support Bounce ---
    if 'At_Prev_Day_Low' in df.columns:
        mask = (df['At_Prev_Day_Low'] == 1) & (labels == '2U')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'CALL', ct_bps, cs_bps)
    report += card(
        9, "Support Bounce (at Historical Level)", ticker,
        "  * Price is at previous day's low (support level)\n"
        "  * Current bar is 2U (bouncing off support)",
        [
            "RSI < 40 (oversold at support)",
            "StochRSI crossed above 20 (turning up)",
            "Order block nearby (institutional interest)",
            "Volume increasing on bounce",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Price breaks below prev day low -> support failed, exit immediately",
            "No follow-through (next bar is 1 or 2D) -> tighten stop",
            "RSI fails to clear 50 -> weak bounce",
        ],
        _get_ticker_notes(ticker, 'support_bounce'),
    )

    # --- CARD 10: Resistance Rejection ---
    if 'At_Prev_Day_High' in df.columns:
        mask = (df['At_Prev_Day_High'] == 1) & (labels == '2D')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'PUT', pt_bps, ps_bps)
    report += card(
        10, "Resistance Rejection (at Historical Level)", ticker,
        "  * Price is at previous day's high (resistance level)\n"
        "  * Current bar is 2D (rejecting off resistance)",
        [
            "RSI > 60 (overbought at resistance)",
            "StochRSI crossed below 80 (turning down)",
            "Volume declining on approach to resistance",
            "Bearish divergence (price higher, RSI lower)",
        ],
        'PUT', stats, put_target, put_stop, hold_time,
        [
            "Price breaks above prev day high -> resistance cleared, exit",
            "No follow-through on rejection -> tighten stop",
            "RSI fails to drop below 50 -> weak rejection",
        ],
        _get_ticker_notes(ticker, 'resistance_rejection'),
    )

    # --- CARD 11: Order Block Test ---
    if 'Order_Block_Test' in df.columns:
        # Bullish: testing order block from above
        mask = (df['Order_Block_Test'] == 1) & (df.get('Order_Block_Position', 0) >= 0) & (labels == '2U')
    else:
        mask = pd.Series(False, index=df.index)
    stats = compute_card_stats(df, labels, mask, 'CALL', ct_bps, cs_bps)
    report += card(
        11, "Order Block Test (Institutional Zone)", ticker,
        "  * Price is testing an identified order block zone\n"
        "  * Current bar is 2U (bouncing off the institutional zone)",
        [
            "Price is at order block high or low boundary",
            "RSI between 35-55 (not extreme)",
            "Volume increasing at the zone",
            "Strat shows reversal or continuation with direction",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Price slices through the order block cleanly -> zone invalidated, exit",
            "No bounce within 5 bars -> zone may be broken",
            "Multiple tests weaken the zone -> less reliable each time",
        ],
        _get_ticker_notes(ticker, 'order_block'),
    )

    # --- CARD 12: FTFC Maximum Conviction ---
    # All timeframes aligned (approximate: EMA cross + ORB trend + 2U or 2D)
    bull_ftfc = (ema_cross == 1) & (orb_trend == 1) & (labels == '2U') & (rsi.between(40, 65))
    stats = compute_card_stats(df, labels, bull_ftfc, 'CALL', ct_bps, cs_bps)
    report += card(
        12, "FTFC Maximum Conviction (All Aligned)", ticker,
        "  * ALL timeframes showing the same direction\n"
        "  * EMAs bullish, ORB bullish, Strat 2U, RSI healthy\n"
        "  * This is the STRONGEST possible setup",
        [
            f"EMA{ind.ema_fast_period} > EMA{ind.ema_mid_period} (bullish cross)",
            "ORB 30m trend is bullish",
            "Current Strat bar is 2U",
            "RSI between 40-65 (healthy, not overbought)",
            "Price above VWAP",
            "RVOL > 1.0 (volume confirms)",
        ],
        'CALL', stats, call_target, call_stop, hold_time,
        [
            "Any single alignment breaks -> reduce size",
            "RSI > 75 -> take profit regardless",
            "RVOL drops below 0.8 -> conviction weakening",
            "Losing money after 5 min in this setup -> something's wrong, exit",
        ],
        _get_ticker_notes(ticker, 'ftfc_conviction'),
    )

    return report, card_records


def _get_ticker_notes(ticker: str, card_type: str) -> List[str]:
    """Return ticker-specific notes for each card type."""
    notes = {
        'IWM': {
            'bullish_continuation': [
                "IWM mean-reverts more than SPY/QQQ — continuation is less reliable",
                "If RSI > 70, reversal risk is ELEVATED — IWM reverses hard",
                "Best combo: 1m+15m (Sharpe 9.31)",
                "IWM has widest targets but also widest stops",
            ],
            'bearish_continuation': [
                "IWM PUTs win more often (43.4%) than CALLs (38.5%)",
                "72% of IWM trades are PUTs — natural bearish lean",
                "Losers fail fast: 8 min median to stop",
                "Highest per-trade return on target hits (+41 bps avg)",
            ],
            'bullish_reversal': [
                "IWM is the BEST ticker for mean-reversion setups",
                "2-1-2 reversals work particularly well on small caps",
                "Look for reversals at prev week lows",
            ],
            'bearish_reversal': [
                "Bearish reversals strongest when RSI > 70 on IWM",
                "Small caps overshoot — look for exhaustion at resistance",
            ],
            'outside_bar': [
                "IWM has MORE Type 3 bars than SPY (higher volatility)",
                "Outside bars on IWM often lead to sharp continuation",
            ],
            'orb_breakout': [
                "IWM has the WIDEST opening ranges — breakouts are more decisive",
                "Once IWM breaks ORB, it tends to run further than SPY",
            ],
            'orb_breakdown': [
                "IWM bearish ORB breakdowns are particularly strong",
                "Small caps sell off harder — bigger moves on downside",
            ],
            'orb_failure': [
                "IWM has fewer ORB failures but LARGER moves when they happen",
                "Mean reversion works well after failed breakouts on IWM",
            ],
            'support_bounce': [
                "IWM bounces harder off support (mean reversion character)",
                "Previous week low is a strong support level for IWM",
            ],
            'resistance_rejection': [
                "IWM rejections at resistance tend to be sharp",
                "Look for RSI > 70 at resistance for highest probability",
            ],
            'order_block': [
                "Institutional order blocks may be less defined on IWM (small cap)",
                "Use with other confirmation for better results",
            ],
            'ftfc_conviction': [
                "When all aligned, IWM provides the BEST risk/reward",
                "Sharpe 9.64 on 1m+15m — strongest of all tickers",
                "But these setups are RARE (492 trades in 10 years)",
            ],
        },
        'SPY': {
            'bullish_continuation': [
                "SPY trends more cleanly — continuation IS more likely than IWM",
                "VWAP is the #1 indicator for SPY (institutional reference)",
                "Most balanced CALL/PUT distribution of all tickers",
                "Best combo: 1m+30m (Sharpe 5.54, WR 54.5%)",
            ],
            'bearish_continuation': [
                "SPY CALL WR (43.5%) nearly identical to PUT WR (43.7%)",
                "SPY has tightest targets (+0.15% CALL, +0.20% PUT)",
                "Time stops produce 55% win rate on SPY",
            ],
            'bullish_reversal': [
                "SPY reversals are subtler — less dramatic than IWM",
                "VWAP reclaim is the strongest confirmation for SPY reversals",
            ],
            'bearish_reversal': [
                "SPY trend following works better than reversal",
                "Be more selective with bearish reversals on SPY",
            ],
            'outside_bar': [
                "SPY has FEWER Type 3 bars — they're rarer but meaningful",
                "Outside bars on SPY often signal trend change",
            ],
            'orb_breakout': [
                "SPY has tightest opening ranges — false breakouts MORE common",
                "Wait for confirmation before entering SPY ORB breakouts",
            ],
            'orb_breakdown': [
                "SPY bearish ORB breaks tend to be more measured",
                "Tighter targets appropriate (-0.12% stop, +0.20% target)",
            ],
            'orb_failure': [
                "SPY may have the MOST ORB failures (tighter range)",
                "SPY ORB failures are a good mean-reversion opportunity",
            ],
            'support_bounce': [
                "VWAP is the strongest support for SPY",
                "Previous day close also acts as strong reference",
            ],
            'resistance_rejection': [
                "SPY respects previous day high as resistance",
                "Use VWAP crossing to confirm rejection",
            ],
            'order_block': [
                "SPY order blocks are more defined (institutional trading)",
                "SPX-derived levels also apply to SPY",
            ],
            'ftfc_conviction': [
                "SPY FTFC alignment flipped Sharpe from -0.19 to +0.18",
                "The BIGGEST relative improvement from Strat filtering",
                "Best combo: 1m+30m (NOT 1m+15m like other tickers)",
            ],
        },
        'QQQ': {
            'bullish_continuation': [
                "QQQ CALLS only win 37.6% — be EXTRA selective",
                "Momentum matters MORE here — StochRSI is more predictive",
                "Score 6/8 signals hit 52.0% with +3.5 bps — quality over quantity",
                "Best combo: 1m+15m (Sharpe 6.67, WR 52.0%)",
            ],
            'bearish_continuation': [
                "QQQ has the MOST stops hit (49.2%)",
                "Fastest failures: 7 min median to stop",
                "QQQ momentum means 2D sequences may accelerate",
            ],
            'bullish_reversal': [
                "QQQ needs MORE consecutive bars before reversal than IWM",
                "Momentum character means reversals are harder to time",
            ],
            'bearish_reversal': [
                "QQQ bullish-to-bearish exhaustion CAN be profitable",
                "Look for RSI divergence on QQQ (price higher, RSI lower)",
            ],
            'outside_bar': [
                "QQQ outside bars often reflect gap-and-go momentum",
                "Post-gap Type 3 bars have different characteristics",
            ],
            'orb_breakout': [
                "QQQ often GAPS at open — ORB sets differently",
                "After gap opens, ORB breakouts may be more decisive",
            ],
            'orb_breakdown': [
                "QQQ bearish ORB breaks can accelerate fast",
                "Momentum makes stops important — respect -0.12%",
            ],
            'orb_failure': [
                "QQQ ORB failures after gap opens may be especially profitable",
                "Gap fills combine well with failed ORB breakouts",
            ],
            'support_bounce': [
                "QQQ bounces less reliably than IWM (momentum character)",
                "Need STRONG volume confirmation for bounces on QQQ",
            ],
            'resistance_rejection': [
                "QQQ tends to blow through resistance on momentum days",
                "Only fade QQQ at resistance with STRONG reversal signals",
            ],
            'order_block': [
                "Tech mega-caps drive QQQ — order blocks reflect their activity",
                "QQQ order block tests need volume confirmation",
            ],
            'ftfc_conviction': [
                "HARDEST ticker to trade — needs HIGHEST conviction entry",
                "Consider ONLY taking score 5+ signals on QQQ",
                "When aligned, QQQ momentum provides excellent returns",
            ],
        },
    }

    return notes.get(ticker, {}).get(card_type, [f"No specific notes for {ticker}."])


# ---------------------------------------------------------------------------
# Quick Reference: Which Ticker Should I Trade?
# ---------------------------------------------------------------------------

def generate_quick_reference() -> str:
    """Generate the 'which ticker to trade' decision tree."""
    report = md_header("Quick Reference: Which Ticker Should I Trade Right Now?", 2)

    report += """
**Decision Tree:**

1. Check daily Strat for all 3 tickers
2. If IWM shows 2-1-2 reversal setup -> **IWM** (strongest mean reversion)
3. If SPY has cleanest FTFC alignment -> **SPY** (strongest trend following)
4. If QQQ has score 6+ signal -> **QQQ** (highest per-trade return at 6+)
5. If all 3 tickers signal the same direction -> **Highest conviction day**
6. If tickers conflict -> **Reduce size or sit out**

**Ticker Personality Summary:**

| Trait | IWM | SPY | QQQ |
|-------|-----|-----|-----|
| Character | Volatile Mean Reverter | Steady Grinder | Momentum Runner |
| Best For | Reversal setups | Trend following | High-conviction momentum |
| Base WR | ~42% | ~43.5% | ~40% |
| PUT lean | Strong (72%) | Balanced (50/50) | Moderate |
| Best combo | 1m+15m | 1m+30m | 1m+15m |
| Target width | Widest | Tightest | Medium |
| Stop speed | 8 min | Moderate | 7 min (fastest) |
| Risk level | Medium | Low | High |

"""
    return report


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def write_playbook_cards(ticker: str, records: List[Dict], analysis_date=None) -> int:
    """Upsert the structured playbook cards into Cloud SQL (``playbook_cards``).

    This is the typed source of truth ``/api/playbook`` reads — it replaces the
    fragile regex-scrape of the markdown. A DB/schema failure is INTERNAL (our
    code), so it is raised, never swallowed into a fake success (CLAUDE.md §3.7).

    ``analysis_date`` keys the cards to the date they were computed AS OF so the
    dashboard's historical "view as of" mode can read a past card set. None →
    today (UTC), matching the table's CURRENT_DATE default for the daily run.
    """
    if not records:
        return 0

    from gcp.database import upsert_dataframe

    if analysis_date is None:
        analysis_date = datetime.now(timezone.utc).date()

    rows = []
    for r in records:
        rows.append({
            'ticker': ticker.upper(),
            'card_num': r['card_num'],
            'analysis_date': analysis_date,
            'name': r['name'],
            'direction': r['direction'],
            'description': r.get('description') or None,
            # JSONB column — pass the Python list; upsert_dataframe builds a
            # typed pg_insert against the reflected JSONB column, so SQLAlchemy
            # serializes it exactly once (a pre-dumped string would double-encode).
            'conditions': r.get('conditions') or [],
            'win_rate': r.get('win_rate'),
            'avg_return_bps': r.get('avg_return_bps'),
            'sample_n': r.get('sample_n'),
            'target_pct': r.get('target_pct'),
            'stop_pct': r.get('stop_pct'),
            'avg_mfe_bps': r.get('avg_mfe_bps'),
            'avg_mae_bps': r.get('avg_mae_bps'),
            'confidence': r.get('confidence'),
            # Per-hold-window sweep (JSONB) + best-avg-return hold.
            'horizons': r.get('horizons') or [],
            'best_horizon_min': r.get('best_horizon_min'),
            'best_horizon_win_rate': r.get('best_horizon_win_rate'),
            'best_horizon_avg_bps': r.get('best_horizon_avg_bps'),
        })

    n = upsert_dataframe(
        pd.DataFrame(rows), 'playbook_cards',
        conflict_cols=['ticker', 'card_num', 'analysis_date'],
    )
    progress(f"Upserted {n} playbook_cards rows (analysis_date={analysis_date})", ticker)
    return n


def run_phase6(tickers: list = None, write_db: bool = False, as_of=None):
    """Run Phase 6 — generate all playbook cards.

    When ``write_db`` is set (``--write-db`` / ``PHASE6_WRITE_DB=1``) the
    structured card records are upserted into the ``playbook_cards`` Cloud SQL
    table, which is the source of truth ``/api/playbook`` reads. Markdown is
    still written for human consumption.

    ``as_of`` (a ``date``) computes the cards AS OF a past date for the
    dashboard's historical "view as of" mode: only intraday bars dated strictly
    BEFORE ``as_of`` are loaded (no look-ahead, CLAUDE.md §3.6 — matches the
    premarket-brief "data through D-1" convention), and the resulting card set
    is keyed to ``as_of`` in ``playbook_cards.analysis_date``. None → today,
    using the full history (the normal daily run).
    """
    if tickers is None:
        tickers = TICKERS

    # As-of cutoff: load only bars dated <= (as_of - 1 day) so the as-of day's
    # own session can't leak into stats keyed to it. load_ticker_1m's end_date
    # is inclusive, so we pass the day before.
    end_date = None
    if as_of is not None:
        end_date = (as_of - timedelta(days=1)).isoformat()

    combined_report = md_header("Phase 6: The Beginner's Playbook — All Tickers", 1)
    combined_report += f"\nGenerated: {timestamp_str()}\n"
    combined_report += "\n12 decision cards per ticker, each with specific entry/exit rules.\n\n"

    combined_report += generate_quick_reference()

    for ticker in tickers:
        progress(f"Starting Phase 6 — building playbook cards", ticker)

        df_1m = load_ticker_1m(ticker, end_date=end_date)
        if df_1m.empty:
            progress("No data, skipping.", ticker)
            continue

        df = enrich_with_indicators(df_1m)
        labels = df['strat_candle'] if 'strat_candle' in df.columns else classify_strat_series(df)
        progress(f"Data loaded: {len(df):,} bars", ticker)

        # Build per-ticker report
        report = md_header(f"Phase 6: {ticker} Playbook", 1)
        report += f"\nGenerated: {timestamp_str()}\n"
        report += f"Data: {df.index.min()} to {df.index.max()} ({len(df):,} bars)\n"
        report += "\n12 decision cards for real-time trading.\n"

        cards, card_records = build_all_cards(ticker, df, labels)
        report += cards

        save_report(report, f'phase6_playbook_{ticker.lower()}.md')
        combined_report += f"\n---\n\n" + cards

        if write_db:
            write_playbook_cards(ticker, card_records, analysis_date=as_of)

        progress("Phase 6 complete!", ticker)

    save_report(combined_report, 'phase6_playbook_combined.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Phase 6: Playbook')
    parser.add_argument('--tickers', nargs='+', default=TICKERS)
    parser.add_argument(
        '--write-db', action='store_true',
        default=os.environ.get('PHASE6_WRITE_DB') == '1',
        help='Upsert structured cards into the playbook_cards Cloud SQL table',
    )
    parser.add_argument(
        '--as-of', dest='as_of', default=os.environ.get('PHASE6_AS_OF'),
        help=('Compute cards AS OF this date (YYYY-MM-DD) using only bars '
              'before it, and key them to it in analysis_date. For historical '
              '"view as of" backfill. Default: today (full history).'),
    )
    args = parser.parse_args()

    as_of_date = None
    if args.as_of:
        try:
            as_of_date = date_cls.fromisoformat(args.as_of.strip())
        except ValueError:
            parser.error(f"--as-of must be YYYY-MM-DD, got {args.as_of!r}")
        if as_of_date > datetime.now(timezone.utc).date():
            parser.error(f"--as-of {as_of_date} is in the future")

    run_phase6(tickers=args.tickers, write_db=args.write_db, as_of=as_of_date)
