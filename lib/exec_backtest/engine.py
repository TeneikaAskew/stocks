"""Realistic trade-lifecycle simulator.

Given:
  - A *trigger bar* (the bar whose close emitted a high-confidence
    2U / 2D prediction) — characterized by (ts_open, ts_close, high, low).
  - A *direction* (long for 2U, short for 2D).
  - A 1m OHLC window covering the predicted bar (bar T+1) AND every
    subsequent bar up to a generous lookforward (we need enough 1m bars
    to evaluate target / stop / time stop sequentially).

Apply the mechanical lifecycle the spec lays out:
  Entry  = stop-buy at trigger.high (long) / stop-sell at trigger.low (short)
           Fill ONLY within bar T+1's window. Voided if trigger not hit.
           Fill price = stop ± slippage; gap-through filled at bar open ± slip.
  Stop   = opposite extreme of trigger bar (long stop = trigger.low,
           short stop = trigger.high). Intrabar 1m fills.
  Target = 1.5R (or configurable). Long target = entry + R*(entry-stop).
  Time   = exit at next 1m bar's close after the time-stop boundary.
  Per-1m bar evaluation: target > stop > time stop is the precedence,
           BUT when both target and stop fall within the same 1m bar's
           range, conservatively assume STOP hit first.

Costs (per share, charged on both legs; 5¢ total round-trip):
  commission 1¢ + spread 1¢ + slippage 0.5¢ per side.

This module is hermetic: no I/O. Takes pre-loaded numpy/pandas arrays;
returns a list of trade dicts.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

import numpy as np
import pandas as pd


# Per-side execution friction in DOLLARS-per-share. Sum × 2 = $0.05 round-trip.
COMMISSION_PER_SIDE = 0.01
SPREAD_PER_SIDE = 0.01
SLIPPAGE_PER_SIDE = 0.005
COST_PER_SIDE = COMMISSION_PER_SIDE + SPREAD_PER_SIDE + SLIPPAGE_PER_SIDE  # 0.025
COST_ROUND_TRIP = 2 * COST_PER_SIDE  # 0.05


@dataclass
class Trade:
    """One executed trade. All prices in $/share."""
    setup_id: int                         # row index in the predictions table
    fold: str                             # walk-forward fold label
    cell: str                             # "5m" / "15m" / "30m"
    direction: str                        # "long" / "short"

    # Setup context
    trigger_ts_open: pd.Timestamp         # ts_open of trigger bar T (UTC)
    trigger_ts_close: pd.Timestamp        # ts_close of trigger bar T (= ts_open of T+1)
    trigger_high: float
    trigger_low: float
    top_prob: float                       # model's max-class probability
    ftfc_score: float                     # may be NaN if not computed

    # Entry
    entry_ts: pd.Timestamp                # 1m bar that triggered entry
    entry_stop_price: float               # the stop-order price (trigger high/low)
    entry_fill_price: float               # actual fill (gap-aware) + slippage
    entry_gapped: bool                    # True if 1m bar opened past stop

    # Trade plan
    initial_stop: float                   # planned stop price
    initial_target: float                 # planned target price
    target_multiple: float                # 1.5 by default
    time_stop_minutes: int                # 30 (5m/15m) or 60 (30m)

    # Exit
    exit_ts: pd.Timestamp
    exit_price: float                     # gross before round-trip cost
    exit_reason: str                      # "target" / "stop" / "time"

    # P&L
    gross_pnl: float                      # $/share (exit - entry) signed
    net_pnl: float                        # $/share after costs


@dataclass
class TradeSpec:
    """Lifecycle parameters that vary per variant."""
    target_multiple: float = 1.5
    # time stop in MINUTES from entry timestamp
    time_stop_minutes: int = 30
    # cost knobs (defaults match spec)
    commission_per_side: float = COMMISSION_PER_SIDE
    spread_per_side: float = SPREAD_PER_SIDE
    slippage_per_side: float = SLIPPAGE_PER_SIDE


@dataclass
class Setup:
    """One prediction → potential trade. Sized so it serializes cheaply."""
    setup_id: int
    fold: str
    cell: str
    direction: str                        # "long" / "short"
    trigger_ts_open: pd.Timestamp         # trigger bar T's open (UTC)
    trigger_ts_close: pd.Timestamp        # trigger bar T's close
    trigger_high: float
    trigger_low: float
    top_prob: float
    ftfc_score: float = float("nan")


def _cost_per_side(spec: TradeSpec) -> float:
    return spec.commission_per_side + spec.spread_per_side + spec.slippage_per_side


def simulate_setup(setup: Setup, m1_bars: pd.DataFrame, spec: TradeSpec) -> Optional[Trade]:
    """Run the trade lifecycle for ONE setup. Returns Trade or None.

    Parameters
    ----------
    setup : Setup
    m1_bars : DataFrame with index = pd.DatetimeIndex (UTC, RTH-only),
        columns Open/High/Low/Close. Should cover at least the predicted
        bar's window AND `time_stop_minutes` of follow-on bars.
    spec : TradeSpec

    Returns
    -------
    Trade if trigger fires AND exit found; None if setup voided (trigger
    not hit in bar T+1 window) or window data is missing.
    """
    if len(m1_bars) == 0:
        return None

    side_cost = _cost_per_side(spec)
    tf_minutes = int(round((setup.trigger_ts_close - setup.trigger_ts_open).total_seconds() / 60))

    # Predicted-bar window: bar T+1 = [trigger_ts_close, trigger_ts_close + TF)
    bar_tplus1_start = setup.trigger_ts_close
    bar_tplus1_end = setup.trigger_ts_close + timedelta(minutes=tf_minutes)

    bars_in_window = m1_bars.loc[
        (m1_bars.index >= bar_tplus1_start) & (m1_bars.index < bar_tplus1_end)
    ]
    if bars_in_window.empty:
        # No 1m data inside the predicted bar (e.g. close-of-session or data gap)
        return None

    is_long = setup.direction == "long"

    # ── Entry: stop-buy at trigger.high (long) or stop-sell at trigger.low (short) ──
    stop_price = setup.trigger_high if is_long else setup.trigger_low

    entry_row = None
    entry_fill = None
    gapped = False
    for ts, row in bars_in_window.iterrows():
        o, h, l = row["Open"], row["High"], row["Low"]
        if is_long:
            # Long: triggers when high crosses stop_price
            if h >= stop_price:
                if o >= stop_price:
                    # Gapped through → fill at open + slip
                    entry_fill = o + spec.slippage_per_side
                    gapped = True
                else:
                    entry_fill = stop_price + spec.slippage_per_side
                entry_row = ts
                break
        else:
            # Short: triggers when low crosses stop_price (downward)
            if l <= stop_price:
                if o <= stop_price:
                    entry_fill = o - spec.slippage_per_side
                    gapped = True
                else:
                    entry_fill = stop_price - spec.slippage_per_side
                entry_row = ts
                break

    if entry_row is None:
        # Trigger never hit during bar T+1 window → setup voided
        return None

    # ── Trade plan ──
    if is_long:
        initial_stop = setup.trigger_low
        risk = entry_fill - initial_stop  # > 0
        initial_target = entry_fill + spec.target_multiple * risk
    else:
        initial_stop = setup.trigger_high
        risk = initial_stop - entry_fill  # > 0
        initial_target = entry_fill - spec.target_multiple * risk

    if risk <= 0:
        # Trigger bar was zero-range or the entry got a worse fill than the
        # stop — unusual but possible on a gap-through. Skip; not a real
        # 1.5R setup.
        return None

    # ── Exit: target > stop > time, with stop-precedence on collision ──
    time_stop_deadline = entry_row + timedelta(minutes=spec.time_stop_minutes)

    # Bars AFTER entry bar (we evaluate exit starting from the bar that
    # ENTERED, but the entry bar's range BELOW the entry price still
    # counts — except we already used part of that bar for the entry
    # itself. To be conservative, we evaluate the entry bar's range
    # post-entry too: the worst case is the bar runs to its stop after
    # filling at the trigger.
    #
    # Implementation: iterate from entry_row inclusive. For the entry
    # bar, use the full bar's H/L because we have no sub-minute info.
    # This matches the spec's "conservatively assume STOP hit first" on
    # collision and is consistent with how the entry bar's H/L is used
    # for entry detection.
    eval_bars = m1_bars.loc[m1_bars.index >= entry_row]

    exit_ts = None
    exit_price = None
    exit_reason = None

    for ts, row in eval_bars.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]

        if is_long:
            target_hit = h >= initial_target
            stop_hit = l <= initial_stop
        else:
            target_hit = l <= initial_target
            stop_hit = h >= initial_stop

        if target_hit and stop_hit:
            # Spec: conservatively assume STOP first
            exit_ts = ts
            exit_price = initial_stop
            exit_reason = "stop"
            break
        if stop_hit:
            exit_ts = ts
            exit_price = initial_stop
            exit_reason = "stop"
            break
        if target_hit:
            exit_ts = ts
            exit_price = initial_target
            exit_reason = "target"
            break

        # Time stop boundary — exit on the NEXT 1m bar's close after the deadline
        if ts >= time_stop_deadline:
            exit_ts = ts
            exit_price = c
            exit_reason = "time"
            break

    if exit_ts is None:
        # Ran out of bars (e.g. end of session before time stop) — close
        # at the last bar's close. This is rare; treat as a time exit so
        # nothing is left dangling.
        last = eval_bars.iloc[-1]
        exit_ts = eval_bars.index[-1]
        exit_price = last["Close"]
        exit_reason = "time"

    # ── P&L ──
    # entry_fill already has entry-side slippage baked in (it's stop ±
    # slippage). exit_price is the THEORETICAL stop / target level — we
    # add exit-side slippage explicitly. Commission + spread are
    # explicit on both legs.
    #
    # Total round-trip friction = 2 * (commission + spread + slippage) = $0.05,
    # split as:
    #   entry: slippage already in entry_fill (worse-by-slippage)
    #        + spread + commission deducted here
    #   exit : slippage subtracted from exit_price (worse-by-slippage)
    #        + spread + commission deducted here
    if is_long:
        gross_pnl = exit_price - entry_fill
        # Exit slippage worsens the realized exit price
        exit_slip_adj = -spec.slippage_per_side
    else:
        gross_pnl = entry_fill - exit_price
        # Short: a worse exit means higher fill on a buy-back stop, or
        # lower fill on a sell-target; either way slippage hurts P&L.
        exit_slip_adj = -spec.slippage_per_side

    net_pnl = (
        gross_pnl
        + exit_slip_adj
        - (spec.commission_per_side + spec.spread_per_side)  # entry leg
        - (spec.commission_per_side + spec.spread_per_side)  # exit leg
    )

    return Trade(
        setup_id=setup.setup_id, fold=setup.fold, cell=setup.cell,
        direction=setup.direction,
        trigger_ts_open=setup.trigger_ts_open,
        trigger_ts_close=setup.trigger_ts_close,
        trigger_high=setup.trigger_high, trigger_low=setup.trigger_low,
        top_prob=setup.top_prob, ftfc_score=setup.ftfc_score,
        entry_ts=entry_row,
        entry_stop_price=stop_price,
        entry_fill_price=entry_fill,
        entry_gapped=gapped,
        initial_stop=initial_stop, initial_target=initial_target,
        target_multiple=spec.target_multiple,
        time_stop_minutes=spec.time_stop_minutes,
        exit_ts=exit_ts, exit_price=exit_price, exit_reason=exit_reason,
        gross_pnl=float(gross_pnl), net_pnl=float(net_pnl),
    )


def fold_stats(trades: List[Trade]) -> dict:
    """Aggregate per-trade $/share P&L into the spec's reported stats."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "hit_rate": 0.0, "gross_exp": 0.0, "net_exp": 0.0,
                "total_net": 0.0, "max_dd": 0.0, "sharpe": 0.0}
    nets = np.array([t.net_pnl for t in trades])
    grosses = np.array([t.gross_pnl for t in trades])
    wins = nets > 0
    cum = np.cumsum(nets)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak).min()
    sd = nets.std(ddof=1) if len(nets) > 1 else 0.0
    sharpe = (nets.mean() / sd) if sd > 0 else 0.0
    return {
        "n": n,
        "hit_rate": float(wins.mean()),
        "gross_exp": float(grosses.mean()),
        "net_exp": float(nets.mean()),
        "total_net": float(nets.sum()),
        "max_dd": float(dd),
        "sharpe": float(sharpe),
    }
