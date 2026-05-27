"""Unit tests for the exec backtest engine.

These exercise the trade lifecycle (entry, stop, target, time stop, costs,
gap-handling, void-on-no-trigger) with synthetic 1m bars so we can
hand-verify the dollar math. No DB, no model — pure engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.exec_backtest.engine import (
    Setup, TradeSpec, simulate_setup, fold_stats,
    COMMISSION_PER_SIDE, SPREAD_PER_SIDE, SLIPPAGE_PER_SIDE,
)


def _bars(rows):
    """Build a 1m bar DataFrame from rows of (ts_utc_str, o, h, l, c)."""
    idx = pd.to_datetime([r[0] for r in rows], utc=True)
    return pd.DataFrame(
        {"Open": [r[1] for r in rows], "High": [r[2] for r in rows],
         "Low": [r[3] for r in rows], "Close": [r[4] for r in rows]},
        index=idx,
    )


def _setup(direction="long", *, trigger_open="2024-01-02 14:30:00",
            tf_min=5, trigger_h=100.0, trigger_l=99.0, prob=0.6):
    open_ts = pd.Timestamp(trigger_open, tz="UTC")
    close_ts = open_ts + pd.Timedelta(minutes=tf_min)
    return Setup(
        setup_id=1, fold="2024-01-01..2025-01-01", cell=f"{tf_min}m",
        direction=direction,
        trigger_ts_open=open_ts, trigger_ts_close=close_ts,
        trigger_high=trigger_h, trigger_low=trigger_l,
        top_prob=prob,
    )


def test_long_clean_target_hit():
    # Trigger bar high=100, low=99 → long stop-buy at 100. Risk = 1.0,
    # target = entry + 1.5 = 101.5+ depending on fill.
    # Bar T+1 = [14:35, 14:40). Suppose at 14:35 the 1m bar gaps a bit
    # but stays below stop, at 14:36 the high breaks 100.
    setup = _setup("long", tf_min=5)
    bars = _bars([
        ("2024-01-02 14:35:00", 99.50, 99.80, 99.40, 99.70),  # within bar T+1
        ("2024-01-02 14:36:00", 99.70, 100.20, 99.65, 100.10),  # triggers; stop=100
        # Subsequent bars take price to target
        ("2024-01-02 14:37:00", 100.10, 100.50, 100.00, 100.40),
        ("2024-01-02 14:38:00", 100.40, 101.80, 100.30, 101.60),  # hits target 1.5R
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    # entry_fill = 100.00 + slippage(0.005) = 100.005
    assert abs(t.entry_fill_price - 100.005) < 1e-9
    # initial_stop = 99.0; risk = 100.005 - 99.0 = 1.005; target = 100.005 + 1.5*1.005 = 101.5125
    assert abs(t.initial_stop - 99.0) < 1e-9
    assert abs(t.initial_target - (100.005 + 1.5 * 1.005)) < 1e-9
    # The 14:38 bar has high 101.80 > target 101.5125 → target hit at 14:38
    assert t.exit_reason == "target"
    assert t.exit_ts == pd.Timestamp("2024-01-02 14:38:00", tz="UTC")
    assert abs(t.exit_price - (100.005 + 1.5 * 1.005)) < 1e-9
    # gross_pnl = target - entry_fill = 1.5 * 1.005 = 1.5075
    expected_gross = 1.5 * 1.005
    assert abs(t.gross_pnl - expected_gross) < 1e-9
    # net deduction beyond entry_fill (which already has entry slippage):
    # exit slippage (0.005) + (commission + spread) on both legs (2 * 0.02)
    expected_net = expected_gross - 0.005 - 2 * (COMMISSION_PER_SIDE + SPREAD_PER_SIDE)
    assert abs(t.net_pnl - expected_net) < 1e-9


def test_long_stop_hit():
    setup = _setup("long", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    bars = _bars([
        ("2024-01-02 14:35:00", 99.50, 100.20, 99.40, 100.10),  # triggers
        ("2024-01-02 14:36:00", 100.10, 100.30, 98.50, 98.80),   # hits stop 99
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    assert t.exit_reason == "stop"
    # exit_price = 99.0; gross_pnl = 99.0 - 100.005 = -1.005
    assert abs(t.gross_pnl - (99.0 - 100.005)) < 1e-9


def test_long_gap_through_fill_at_open():
    # The 1m bar that triggers OPENS above the stop → fill at open + slip.
    setup = _setup("long", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    bars = _bars([
        ("2024-01-02 14:35:00", 100.50, 101.00, 100.40, 100.80),  # gaps above stop
        ("2024-01-02 14:36:00", 100.80, 102.00, 100.70, 101.90),
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    assert t.entry_gapped is True
    # entry_fill = open + slippage = 100.505
    assert abs(t.entry_fill_price - 100.505) < 1e-9


def test_long_void_when_trigger_never_hit():
    # Bar T+1 entirely below the stop → no trade.
    setup = _setup("long", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    bars = _bars([
        ("2024-01-02 14:35:00", 99.20, 99.80, 99.10, 99.40),
        ("2024-01-02 14:36:00", 99.40, 99.90, 99.30, 99.50),
        ("2024-01-02 14:37:00", 99.50, 99.95, 99.40, 99.60),
        ("2024-01-02 14:38:00", 99.60, 99.95, 99.50, 99.70),
        ("2024-01-02 14:39:00", 99.70, 99.95, 99.60, 99.80),
        # bar T+1 window is [14:35, 14:40) → all 5 bars above. None hit 100.
        # Following bars are OUTSIDE the window so don't count.
        ("2024-01-02 14:40:00", 99.80, 101.00, 99.70, 100.90),  # ignored
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is None


def test_short_clean_target_hit():
    # Trigger high=100, low=99 → short stop-sell at 99.
    setup = _setup("short", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    bars = _bars([
        ("2024-01-02 14:35:00", 99.20, 99.30, 98.80, 98.90),  # triggers; stop=99
        ("2024-01-02 14:36:00", 98.90, 98.95, 97.40, 97.50),  # hits short target
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    # entry_fill (short) = 99.0 - slip = 98.995
    assert abs(t.entry_fill_price - 98.995) < 1e-9
    # initial_stop = 100.0; risk = 100.0 - 98.995 = 1.005; target = 98.995 - 1.5075 = 97.4875
    assert abs(t.initial_stop - 100.0) < 1e-9
    assert abs(t.initial_target - (98.995 - 1.5 * 1.005)) < 1e-9
    # 14:36 low 97.40 ≤ 97.4875 → target hit
    assert t.exit_reason == "target"
    assert abs(t.gross_pnl - (98.995 - (98.995 - 1.5 * 1.005))) < 1e-9
    # = 1.5 * 1.005 = 1.5075


def test_stop_precedence_on_collision():
    # If both target AND stop fall within the same 1m bar's range, spec
    # says conservatively assume STOP first.
    setup = _setup("long", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    bars = _bars([
        ("2024-01-02 14:35:00", 99.50, 100.20, 99.40, 100.10),  # triggers @100
        ("2024-01-02 14:36:00", 100.10, 102.00, 98.50, 100.00),  # H=102 > target,
                                                                  # L=98.50 < stop99
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    assert t.exit_reason == "stop"
    assert abs(t.exit_price - 99.0) < 1e-9


def test_time_stop():
    # Time stop = 30 min from entry. Construct bars where neither target
    # nor stop hit; we should exit at the next bar's close after the
    # 30-min mark.
    setup = _setup("long", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    # entry at 14:35; deadline = 15:05
    rows = [("2024-01-02 14:35:00", 99.50, 100.20, 99.40, 100.10)]  # trigger
    # 30 quiet bars until deadline at 15:05
    for i in range(1, 31):
        ts = pd.Timestamp("2024-01-02 14:35:00", tz="UTC") + pd.Timedelta(minutes=i)
        rows.append((ts.strftime("%Y-%m-%d %H:%M:%S"), 100.05, 100.15, 99.95, 100.00))
    # Bar at 15:05 (i=30) is where ts >= deadline → time exit
    bars = _bars(rows)
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    assert t.exit_reason == "time"
    # First bar at ts >= 14:35 + 30 = 15:05 → that's i=30
    assert t.exit_ts == pd.Timestamp("2024-01-02 15:05:00", tz="UTC")


def test_round_trip_cost_is_5c():
    # Sanity: net P&L on a target win = gross - $0.05 round trip.
    setup = _setup("long", tf_min=5, trigger_h=100.0, trigger_l=99.0)
    bars = _bars([
        ("2024-01-02 14:35:00", 99.50, 100.20, 99.40, 100.10),
        ("2024-01-02 14:36:00", 100.10, 101.80, 100.10, 101.70),
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    t = simulate_setup(setup, bars, spec)
    assert t is not None
    assert t.exit_reason == "target"
    # entry slippage (0.005, in entry_fill) + exit slip (0.005, in exit_slip_adj)
    # + 2 * (commission 0.01 + spread 0.01) = 0.05 total
    cost = (t.entry_fill_price - t.entry_stop_price) + (t.exit_price - 0) - (t.exit_price - 0)
    # Easier check: gross - net should equal total friction:
    #   slip on exit + 2*(comm+spread)
    expected_friction = SLIPPAGE_PER_SIDE + 2 * (COMMISSION_PER_SIDE + SPREAD_PER_SIDE)
    assert abs((t.gross_pnl - t.net_pnl) - expected_friction) < 1e-9


def test_fold_stats_basic():
    # Build minimal trades for a hit-rate sanity check.
    setup = _setup("long")
    bars = _bars([
        ("2024-01-02 14:35:00", 99.50, 100.20, 99.40, 100.10),
        ("2024-01-02 14:36:00", 100.10, 101.80, 100.00, 101.70),
    ])
    spec = TradeSpec(target_multiple=1.5, time_stop_minutes=30)
    winner = simulate_setup(setup, bars, spec)
    bars2 = _bars([
        ("2024-01-02 14:35:00", 99.50, 100.20, 99.40, 100.10),
        ("2024-01-02 14:36:00", 100.10, 100.30, 98.50, 98.80),
    ])
    loser = simulate_setup(setup, bars2, spec)
    s = fold_stats([winner, loser])
    assert s["n"] == 2
    assert s["hit_rate"] == 0.5
    # winner net ≈ 1.5075 - 0.045 ≈ 1.4625
    # loser  net ≈ -1.005 - 0.045 ≈ -1.05
    # total ≈ 0.4125 ; avg ≈ 0.20625
    assert s["total_net"] == pytest.approx(winner.net_pnl + loser.net_pnl)
