"""Backtest router unit-convention tests (spec §4 items 0.2, 0.6).

The BacktestEngine writes return_pct as a raw fraction (0.003 = 0.3%).
The router must emit TRUE PERCENT units for every *_pct field so the
frontend can render `${v.toFixed(2)}%` without unit knowledge.
win_rate stays a 0-1 fraction (UI multiplies by 100).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

from api.routers import backtest  # noqa: E402


def _df():
    return pd.DataFrame({
        "return_pct": [0.003, -0.002, 0.004, -0.001],  # fractions from the engine
        "entry_time": ["2026-01-02 10:00"] * 4,
    })


def test_summarize_returns_emits_percent_units():
    s = backtest._summarize_returns(_df())
    assert s["avg_return_pct"] == pytest.approx(0.1)     # mean fraction 0.001 -> 0.1%
    assert s["avg_win_pct"] == pytest.approx(0.35)       # (0.3+0.4)/2 %
    assert s["avg_loss_pct"] == pytest.approx(-0.15)     # (-0.2+-0.1)/2 %
    assert s["total_return_pct"] == pytest.approx(0.4)
    assert s["win_rate"] == pytest.approx(0.5)           # stays a fraction


def test_trade_records_emit_percent_units():
    recs = backtest._trades_to_percent_records(_df())
    assert recs[0]["return_pct"] == pytest.approx(0.3)


def test_run_pattern_accepts_specific_timestamp():
    pat = backtest._backtest_pattern("SPY", run="20260222_231417")
    assert pat == r"^backtest_SPY_20260222_231417\.csv$"
