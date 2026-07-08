"""
Style miner — derives a user's trading-style condition profile from their
labeled journal entries (Task 4.2, Phase 4 of the 2026-07-08 trade-journal
program plan).

Condition vocabulary
---------------------
A small, FIXED vocabulary of 8 boolean conditions. Each is evaluated at the
entry bar via the exact PRODUCTION indicator path
(``lib.indicators.add_signal_indicators`` — CLAUDE.md Rule 3.6; the same
function ``platform/api/routers/live.py``'s signal-series endpoint and
``lib.backtest.replay_labeled_trades`` use), never a hand-rolled formula.

Every condition maps 1:1 onto a ``lib.config.SignalConfig`` tunable so a
mined ``StyleProfile`` can be converted straight into engine configuration
in Task 4.3:

=====================  ================================  ===================================
condition               reads (indicator column)          SignalConfig tunable
=====================  ================================  ===================================
``rsi_25_50``           ``RSI{rsi_period}``                ``call_rsi_range`` (default 25-50)
``rsi_50_75``           ``RSI{rsi_period}``                ``put_rsi_range`` (default 50-75)
``above_vwap``          ``Price_vs_VWAP`` > 0               vwap side (``check_put_conditions``'s
                                                             ``above_vwap`` factor, lib/signals.py)
``below_vwap``          ``Price_vs_VWAP`` < 0               vwap side (``check_call_conditions``'s
                                                             ``below_vwap`` factor, lib/signals.py)
``consec_up_ge_{N}``    ``Consecutive_Up`` >= N             ``consecutive_periods``
``consec_down_ge_{N}``  ``Consecutive_Down`` >= N           ``consecutive_periods``
``stoch_oversold``      ``StochRSI_K`` < threshold          ``stoch_rsi_oversold``
``stoch_overbought``    ``StochRSI_K`` > threshold          ``stoch_rsi_overbought``
=====================  ================================  ===================================

``N`` and every threshold above are read from a fresh ``SignalConfig()`` —
the same defaults ``evaluate_signal`` falls back to with no per-ticker
override — so the vocabulary and the engine that later validates a mined
profile (Task 4.3's ``WalkForwardValidator.run_profile``) never drift apart.
RSI/VWAP/consecutive-move/StochRSI-K are mutually independent signals, so a
kept condition set can legitimately mix any subset of the 8 (e.g. an
``above_vwap`` + ``rsi_25_50`` pairing is unusual for a live CALL setup but
is a perfectly valid *mined* combination if that is what a user's actual
entries show).

Warm-up honesty
-----------------
``add_signal_indicators`` needs bars to warm up before RSI / StochRSI /
consecutive-move columns are trustworthy. Mirroring
``lib.backtest._SIGNAL_WARMUP_BARS`` / ``platform/api/routers/live.py``'s
14-bar gate, any entry landing in the first 14 bars of its day's frame
produces NO condition observations (``snapshot_entry_conditions`` returns
``None``) and is excluded from BOTH the numerator and the denominator for
that entry's direction — never zero-filled or treated as "every condition
false" (CLAUDE.md Rule 3.7). The same exclusion applies to any entry whose
date has no bars, or whose ``entry_ts`` doesn't minute-match any bar in its
day's frame — these are honestly "we can't observe this entry", not "this
entry has no conditions".

Minimums
---------
- Fewer than ``_MIN_TOTAL_ENTRIES`` (10) labeled entries TOTAL (both
  directions, counted BEFORE warm-up/unresolvable exclusion) -> `mine_style`
  returns ``[]`` immediately. Mirrors Task 4.3's endpoint contract ("need
  >= 10 closed trades") — spec §8's minimum-sample floor.
- A direction needs >= ``_MIN_DIRECTION_ENTRIES`` (5) RESOLVED entries
  (i.e. after warm-up/unresolvable exclusion) to receive a profile at all.
  5 is half of the 10-trade floor split across the two possible directions
  (CALL/PUT) — the smallest per-direction sample below which a frequency
  count is too coarse (denominators of 1-4) to call the result a "style"
  rather than noise. If warm-up exclusion drops a direction's resolved
  count below 5, that direction gets no profile even though its RAW count
  was >= 5.
- A profile is only emitted for a direction if at least one condition
  clears ``min_support_frac``; a direction where every condition falls
  short produces no ``StyleProfile`` for that direction (an "everything
  and nothing" profile isn't a style).

``entries`` is expected to already be filtered to CLOSED trades by the
caller — the same contract ``lib.backtest.replay_labeled_trades``'s
``labeled`` parameter uses. This module mines ENTRY conditions only; it
does not re-derive "closed" from exit fields (Task 4.3's endpoint owns that
filter: "loads the caller's closed chart/manual journal trades").

Determinism
------------
``mine_style`` sorts entries internally before processing (by entry
timestamp, then id) so the CALLER's input order never affects the result,
iterates directions in a fixed ``('CALL', 'PUT')`` order, and returns each
profile's ``conditions`` pre-sorted alphabetically. Same input (in any
order) -> same output, always.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from lib.config import IndicatorConfig, SignalConfig
from lib.indicators import add_signal_indicators

# Mirrors lib.backtest._SIGNAL_WARMUP_BARS / platform/api/routers/live.py's
# compute_live_signal_series warm-up gate — indicators aren't trustworthy
# before this many bars have accumulated in the day's frame.
_WARMUP_BARS = 14

# spec §8 / Task 4.3's endpoint contract ("need >= 10 closed trades") —
# the absolute floor before mining is attempted at all.
_MIN_TOTAL_ENTRIES = 10

# Half of _MIN_TOTAL_ENTRIES, split across the two possible directions —
# below this a direction's frequency counts are too coarse (denominators of
# 1-4) to call the result a "style" rather than noise.
_MIN_DIRECTION_ENTRIES = _MIN_TOTAL_ENTRIES // 2

_DIRECTIONS = ('CALL', 'PUT')


@dataclass
class StyleProfile:
    """A mined per-direction condition profile.

    Attributes
    ----------
    direction : 'CALL' or 'PUT'.
    conditions : kept condition names (see module docstring vocabulary
        table), sorted alphabetically for determinism.
    support : count of this direction's RESOLVED entries where ALL of
        ``conditions`` were simultaneously true (the joint AND, not the
        per-condition frequency that decided which conditions to keep).
    total : count of this direction's RESOLVED entries (post warm-up /
        unresolvable exclusion) — the denominator used for both the
        per-condition frequency threshold and ``support``.
    """
    direction: str
    conditions: List[str] = field(default_factory=list)
    support: int = 0
    total: int = 0


def _safe_lt(value, threshold) -> bool:
    """value < threshold, honestly False (not fabricated) when value is
    NaN/None — a missing/undefined indicator value can't confirm a
    condition is true."""
    return value is not None and pd.notna(value) and value < threshold


def _safe_gt(value, threshold) -> bool:
    return value is not None and pd.notna(value) and value > threshold


def _safe_between(value, lo, hi) -> bool:
    return value is not None and pd.notna(value) and lo < value < hi


def _safe_ge(value, threshold) -> bool:
    return value is not None and pd.notna(value) and value >= threshold


def snapshot_entry_conditions(bars: pd.DataFrame, entry_idx: int) -> Optional[Dict[str, bool]]:
    """Indicator/condition snapshot at one entry bar via the production
    indicator path (``add_signal_indicators`` — Rule 3.6).

    Parameters
    ----------
    bars : the day's 1-min OHLCV frame (uppercase Open/High/Low/Close/
        Volume + a 'Time' column), sorted ascending and reset-indexed —
        same shape ``lib.backtest.replay_labeled_trades`` walks.
    entry_idx : positional (``iloc``) index of the entry bar within `bars`.

    Returns
    -------
    A dict of {condition_name: bool} covering every condition in the
    vocabulary (module docstring), or ``None`` if `entry_idx` falls within
    the first ``_WARMUP_BARS`` (14) bars of the frame — indicators aren't
    trustworthy yet, so this entry contributes NO observation (excluded
    from both numerator and denominator by the caller, never zero-filled).
    """
    if entry_idx < 0 or entry_idx >= len(bars):
        raise ValueError(
            f"entry_idx={entry_idx} out of range for a {len(bars)}-bar frame"
        )

    if entry_idx + 1 < _WARMUP_BARS:
        return None

    ind_cfg = IndicatorConfig()
    sig_cfg = SignalConfig()
    n = sig_cfg.consecutive_periods

    ind_df = add_signal_indicators(bars, close_col='Close')
    row = ind_df.iloc[entry_idx]

    rsi = row.get(ind_cfg.rsi_col)
    price_vs_vwap = row.get('Price_vs_VWAP')
    consec_up = row.get('Consecutive_Up')
    consec_down = row.get('Consecutive_Down')
    stoch_k = row.get('StochRSI_K')

    call_lo, call_hi = sig_cfg.call_rsi_range
    put_lo, put_hi = sig_cfg.put_rsi_range

    return {
        'rsi_25_50': _safe_between(rsi, call_lo, call_hi),
        'rsi_50_75': _safe_between(rsi, put_lo, put_hi),
        'above_vwap': _safe_gt(price_vs_vwap, 0),
        'below_vwap': _safe_lt(price_vs_vwap, 0),
        f'consec_up_ge_{n}': _safe_ge(consec_up, n),
        f'consec_down_ge_{n}': _safe_ge(consec_down, n),
        'stoch_oversold': _safe_lt(stoch_k, sig_cfg.stoch_rsi_oversold),
        'stoch_overbought': _safe_gt(stoch_k, sig_cfg.stoch_rsi_overbought),
    }


def _resolve_entry_idx(entry_dt: pd.Timestamp, day_bars: pd.DataFrame) -> Optional[int]:
    """Minute-truncated Time match — mirrors lib.backtest._score_one_trade's
    entry-bar lookup (lib/backtest.py, ~line 952-961) exactly, since that
    logic isn't factored into a standalone importable helper there.
    Returns the matched positional index into `day_bars` (already assumed
    sorted+reset by the caller), or None if no bar matches."""
    entry_minute_key = entry_dt.strftime('%Y-%m-%d %H:%M')
    bar_minutes = pd.to_datetime(day_bars['Time']).dt.strftime('%Y-%m-%d %H:%M')
    matches = day_bars.index[bar_minutes == entry_minute_key]
    if len(matches) == 0:
        return None
    return int(matches[0])


def _entry_sort_key(entry: dict) -> tuple:
    """Deterministic ordering independent of the caller's input order (e.g.
    a DB query result with no explicit ORDER BY)."""
    return (str(entry.get('entry_ts') or ''), str(entry.get('id') or ''))


def mine_style(
    entries: List[dict],
    bars_by_date: Dict[str, pd.DataFrame],
    min_support_frac: float = 0.6,
) -> List[StyleProfile]:
    """Frequency-threshold mining: per direction, keep conditions true at
    >= `min_support_frac` of that direction's RESOLVED entries. See the
    module docstring for the full vocabulary, warm-up-exclusion, and
    minimum-sample rules. Deterministic — see module docstring.
    """
    if len(entries) < _MIN_TOTAL_ENTRIES:
        return []

    by_direction: Dict[str, List[Dict[str, bool]]] = {d: [] for d in _DIRECTIONS}

    for entry in sorted(entries, key=_entry_sort_key):
        direction = str(entry.get('direction') or '').upper()
        if direction not in _DIRECTIONS:
            continue

        entry_ts_raw = entry.get('entry_ts')
        if entry_ts_raw is None:
            continue
        try:
            entry_dt = pd.to_datetime(entry_ts_raw)
        except (ValueError, TypeError):
            continue

        date_key = entry_dt.strftime('%Y-%m-%d')
        day_bars = bars_by_date.get(date_key)
        if day_bars is None or day_bars.empty:
            continue

        day_bars = day_bars.sort_values('Time').reset_index(drop=True)
        entry_idx = _resolve_entry_idx(entry_dt, day_bars)
        if entry_idx is None:
            continue

        snapshot = snapshot_entry_conditions(day_bars, entry_idx)
        if snapshot is None:
            continue  # warm-up — excluded from BOTH numerator and denominator

        by_direction[direction].append(snapshot)

    profiles: List[StyleProfile] = []
    for direction in _DIRECTIONS:  # fixed order -> deterministic output
        snapshots = by_direction[direction]
        total = len(snapshots)
        if total < _MIN_DIRECTION_ENTRIES:
            continue

        vocabulary = sorted(snapshots[0].keys())
        kept = [
            cond for cond in vocabulary
            if sum(1 for s in snapshots if s[cond]) / total >= min_support_frac
        ]
        if not kept:
            continue

        support = sum(1 for s in snapshots if all(s[cond] for cond in kept))

        profiles.append(StyleProfile(
            direction=direction,
            conditions=kept,
            support=support,
            total=total,
        ))

    return profiles
