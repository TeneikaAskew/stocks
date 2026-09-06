"""Tests for lib/insights.insight_general_combo_sweep — the Phase 3
(coarser-entry-TF combo) report renderer.

Phase 3 sweep rows are tagged type=='general_combo'. insight_combo_sweep
only renders type=='combo', so without this renderer the 5m/15m/30m
entry-timeframe combos are computed + stored but never appear in
BACKTEST_RESULTS.md. (Codex P2 on PR #519.)
"""
from __future__ import annotations

import pandas as pd

from lib.insights import insight_general_combo_sweep


def _sweep_df(rows):
    """Build a sweep DataFrame with the columns the insight fns expect."""
    return pd.DataFrame(rows, columns=[
        "type", "label", "trades", "win_rate", "pf",
        "sharpe", "max_dd", "expectancy",
    ])


def test_renders_general_combo_rows():
    """Phase 3 rows (type=general_combo) appear in the rendered table."""
    df = _sweep_df([
        ("single", "5m", 4999, 0.48, 1.03, 0.07, -0.025, 0.00001),
        ("combo", "1m+1h", 4089, 0.528, 1.56, 2.47, -0.0167, 0.00042),
        ("general_combo", "5m+15m", 3000, 0.51, 1.30, 1.80, -0.03, 0.00028),
        ("general_combo", "15m+30m", 1200, 0.55, 1.45, 2.10, -0.02, 0.00038),
    ])
    out = "\n".join(insight_general_combo_sweep({"IWM": df}))
    assert "Coarser Entry TF" in out
    assert "5m+15m" in out
    assert "15m+30m" in out
    # The 1m-anchored combo and single-TF rows must NOT leak into this section
    assert "1m+1h" not in out
    # Best per ticker = highest Sharpe (15m+30m at 2.10)
    assert "**IWM**: **15m+30m**" in out


def test_empty_when_no_general_combo_rows():
    """A sweep with only single + combo rows (no --all-combos) → no section."""
    df = _sweep_df([
        ("single", "1m", 7215, 0.472, 1.12, 0.85, -0.05, 0.0001),
        ("combo", "1m+15m", 4717, 0.513, 1.40, 2.08, -0.025, 0.00031),
    ])
    assert insight_general_combo_sweep({"IWM": df}) == []


def test_empty_dict_returns_empty():
    assert insight_general_combo_sweep({}) == []


def test_multi_ticker_best_per_ticker():
    """Each ticker gets its own best-combo line, by Sharpe."""
    iwm = _sweep_df([
        ("general_combo", "5m+15m", 3000, 0.51, 1.3, 1.8, -0.03, 0.0003),
        ("general_combo", "5m+1h", 2000, 0.53, 1.4, 2.2, -0.02, 0.0004),
    ])
    spy = _sweep_df([
        ("general_combo", "15m+30m", 1500, 0.49, 1.1, 0.9, -0.04, 0.0001),
    ])
    out = "\n".join(insight_general_combo_sweep({"IWM": iwm, "SPY": spy}))
    assert "**IWM**: **5m+1h**" in out      # higher Sharpe of IWM's two
    assert "**SPY**: **15m+30m**" in out
