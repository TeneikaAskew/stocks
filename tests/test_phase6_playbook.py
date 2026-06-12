"""Unit tests for the triggered target/stop/time-stop backtest in
scripts/analysis/phase6_playbook.compute_card_stats.

These lock in the methodology upgrade away from the old "did the next
1-minute bar tick up" proxy (which ignored the card's own target/stop).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.analysis.phase6_playbook import compute_card_stats

TARGET_BPS = 30.0   # +0.30%
STOP_BPS = 15.0     # -0.15%
ENTRY = 100.0
TGT_PX = ENTRY * (1 + TARGET_BPS / 1e4)   # 100.30
STP_PX = ENTRY * (1 - STOP_BPS / 1e4)     # 99.85


def _bars(rows, start="2026-06-01 09:30"):
    """rows: list of (open, high, low, close). Single RTH session."""
    idx = pd.date_range(start, periods=len(rows), freq="1min")
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)
    df["Volume"] = 1
    return df


def _mask(df, positions):
    m = pd.Series(False, index=df.index)
    for p in positions:
        m.iloc[p] = True
    return m


def _stats(df, mask, direction="CALL", time_stop_min=30):
    return compute_card_stats(df, pd.Series("2U", index=df.index), mask,
                              direction, TARGET_BPS, STOP_BPS, time_stop_min)


def test_no_occurrence_returns_count_zero():
    df = _bars([(100, 100, 100, 100)] * 3)
    out = _stats(df, _mask(df, []))
    assert out == {"count": 0}


def test_target_before_stop_is_a_win():
    # entry bar (pos 0) close 100; next bar tags the target, never the stop
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.35, 99.95, 100.3),  # hits 100.30 target, low stays > 99.85
    ])
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["resolved"] == 1
    assert out["win_rate"] == 1.0
    assert out["avg_return_bps"] == pytest.approx(TARGET_BPS)


def test_stop_before_target_is_a_loss():
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.05, 99.80, 99.85),  # hits 99.85 stop, never 100.30
    ])
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["win_rate"] == 0.0
    assert out["avg_return_bps"] == pytest.approx(-STOP_BPS)


def test_same_bar_target_and_stop_assumes_stop():
    # both target and stop inside one bar -> pessimistic: stop counted
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.40, 99.80, 100.0),  # high>=tgt AND low<=stop
    ])
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["win_rate"] == 0.0
    assert out["avg_return_bps"] == pytest.approx(-STOP_BPS)


def test_time_stop_marks_to_close():
    # neither target nor stop touched within time_stop_min -> mark to close
    df = _bars([
        (100, 100, 100, 100),          # entry
        (100, 100.10, 99.95, 100.05),  # drift
        (100, 100.12, 99.95, 100.10),  # close here at time stop
    ])
    out = _stats(df, _mask(df, [0]), "CALL", time_stop_min=2)
    assert out["resolved"] == 1
    # marked to close at 100.10 -> +10 bps, a win
    assert out["avg_return_bps"] == pytest.approx(10.0, abs=0.5)
    assert out["win_rate"] == 1.0


def test_put_direction_mirrors():
    # PUT target is price DOWN; this bar drops to the put target
    df = _bars([
        (100, 100, 100, 100),       # entry
        (100, 100.05, 99.65, 99.70),  # low 99.65 <= 100*(1-30bps)=99.70 target
    ])
    out = _stats(df, _mask(df, [0]), "PUT")
    assert out["win_rate"] == 1.0
    assert out["avg_return_bps"] == pytest.approx(TARGET_BPS)


def test_insufficient_forward_bars_are_skipped_not_zeroed():
    # entry on the LAST bar -> no forward bar -> excluded from denominator
    df = _bars([(100, 100, 100, 100), (100, 100, 100, 100)])
    out = _stats(df, _mask(df, [1]), "CALL")
    assert out["count"] == 1
    assert out["resolved"] == 0
    assert out["skipped_insufficient_bars"] == 1
    assert np.isnan(out["win_rate"])        # NOT coerced to 0 (CLAUDE.md 3.7)


def test_overnight_gap_does_not_leak_into_trade():
    # entry at end of session 1; session 2 gaps up past target. The gap must
    # NOT count -- there are no same-session forward bars, so it's skipped.
    idx = pd.to_datetime([
        "2026-06-01 15:59",   # entry (last bar of day 1)
        "2026-06-02 09:30",   # next day open, gaps to 101 (would be a win)
        "2026-06-02 09:31",
    ])
    df = pd.DataFrame(
        [(100, 100, 100, 100), (101, 101.5, 101, 101.4), (101.4, 101.6, 101.3, 101.5)],
        columns=["Open", "High", "Low", "Close"], index=idx)
    df["Volume"] = 1
    out = _stats(df, _mask(df, [0]), "CALL")
    assert out["resolved"] == 0
    assert out["skipped_insufficient_bars"] == 1
