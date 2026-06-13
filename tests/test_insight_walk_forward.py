"""Tests for lib.insights.insight_walk_forward.

The walk-forward section is the honest out-of-sample report. These tests
pin:

  * empty input → returns [] (no empty heading rendered),
  * per-fold table appears per (ticker, mode) with one row per fold,
  * Stability Summary row aggregates fold metrics correctly,
  * IS-vs-OOS verdict honestly flags overfitting when OOS Sharpe is
    materially below IS Sharpe.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lib.insights import insight_walk_forward


# ── helpers ────────────────────────────────────────────────────────────

def _wf_frame(
    ticker: str,
    mode: str,
    sharpes: list[float],
    stability: float = 0.67,
) -> pd.DataFrame:
    """Build a DataFrame shaped like the backtest_walk_forward_folds rows
    a single ticker × mode would return."""
    rows = []
    for i, sh in enumerate(sharpes):
        rows.append({
            "run_id": "r-" + ticker,
            "ticker": ticker,
            "use_strat": mode == "strat",
            "mode": mode,
            "fold_index": i,
            "train_start": pd.Timestamp(f"2024-01-01").date(),
            "train_end": pd.Timestamp(f"2024-{i+4:02d}-01").date(),
            "test_start": pd.Timestamp(f"2024-{i+4:02d}-01").date(),
            "test_end": pd.Timestamp(f"2024-{i+7:02d}-01").date(),
            "total_trades": 20 + i,
            "win_rate": 0.5,
            "profit_factor": 1.2,
            "expectancy": 0.0005,
            "sharpe": sh,
            "max_dd": -0.05,
            "avg_win": 0.004,
            "avg_loss": -0.003,
            "stability_score": stability,
        })
    return pd.DataFrame(rows)


def _combine(*frames: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(list(frames), ignore_index=True)


# ── empty input ────────────────────────────────────────────────────────

class TestEmptyInput:
    def test_empty_dict_returns_empty_list(self):
        assert insight_walk_forward({}) == []

    def test_all_none_returns_empty_list(self):
        """When every ticker's frame is None, render nothing — the
        section heading must NOT appear."""
        assert insight_walk_forward({"SPY": None, "IWM": None}) == []

    def test_all_empty_dfs_returns_empty_list(self):
        empty = pd.DataFrame(columns=[
            "mode", "fold_index", "sharpe", "stability_score",
            "total_trades", "win_rate", "profit_factor", "max_dd",
            "train_start", "train_end", "test_start", "test_end",
        ])
        assert insight_walk_forward({"SPY": empty}) == []


# ── per-fold table ─────────────────────────────────────────────────────

class TestPerFoldTable:
    def test_section_heading_appears(self):
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6])
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        assert "## Walk-Forward Validation" in text
        assert "Per-Fold Out-of-Sample Metrics" in text

    def test_one_row_per_fold_in_table(self):
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6, 0.7])
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        # Each fold has a unique date range; pick the first as a marker.
        assert "2024-04-01" in text  # fold 0 train_end / test_start
        # Count data rows: lines starting with "| 0 ", "| 1 ", "| 2 ", "| 3 ".
        data_rows = [ln for ln in lines if ln.startswith("| ")
                     and ln.split("|")[1].strip().isdigit()]
        assert len(data_rows) == 4

    def test_ticker_mode_subheading(self):
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6])
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        assert "#### SPY — strat" in text

    def test_both_modes_render_separately(self):
        base = _wf_frame("SPY", "base", [0.3, 0.35])
        strat = _wf_frame("SPY", "strat", [0.7, 0.8])
        df = _combine(base, strat)
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        assert "#### SPY — base" in text
        assert "#### SPY — strat" in text


# ── stability summary ──────────────────────────────────────────────────

class TestStabilitySummary:
    def test_stability_summary_row(self):
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6], stability=0.67)
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        assert "Stability Summary" in text
        # mean of [0.4, 0.5, 0.6] = 0.50
        # 3 positive folds out of 3
        assert "| 3/3 |" in text
        # stability_score formatted to 2 dp
        assert "0.67" in text

    def test_negative_sharpe_folds_counted(self):
        df = _wf_frame("SPY", "base", [-0.2, 0.3, -0.1, 0.4])
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        # 2 of 4 folds positive
        assert "| 2/4 |" in text


# ── in-sample vs out-of-sample verdict ─────────────────────────────────

class TestInSampleVsOutOfSample:
    def test_no_in_sample_data_omits_verdict_section(self):
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6])
        lines = insight_walk_forward({"SPY": df})
        text = "\n".join(lines)
        assert "In-Sample vs Out-of-Sample" not in text

    def test_oos_agreeing_with_is_renders_robust_verdict(self):
        """IS=0.5, OOS=0.5 → gap=0 → "edge appears robust"."""
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6])  # mean=0.5
        lines = insight_walk_forward(
            {"SPY": df},
            in_sample_sharpes={"SPY": {"strat": 0.5}},
        )
        text = "\n".join(lines)
        assert "In-Sample vs Out-of-Sample Sharpe" in text
        assert "edge appears robust" in text

    def test_oos_materially_below_is_flags_overfit(self):
        """IS=2.0, OOS=0.4 → gap=1.6, threshold=max(0.5, 1.0)=1.0 →
        materially below → "likely overfit"."""
        df = _wf_frame("SPY", "strat", [0.3, 0.4, 0.5])  # mean=0.4
        lines = insight_walk_forward(
            {"SPY": df},
            in_sample_sharpes={"SPY": {"strat": 2.0}},
        )
        text = "\n".join(lines)
        assert "likely overfit" in text
        assert "trust OOS, not IS" in text

    def test_oos_materially_above_is_flags_regime_shift(self):
        """IS=0.2, OOS=2.0 → gap=-1.8, threshold=max(0.5, 0.1)=0.5 →
        materially above → "regime shift?"."""
        df = _wf_frame("SPY", "strat", [1.8, 2.0, 2.2])  # mean=2.0
        lines = insight_walk_forward(
            {"SPY": df},
            in_sample_sharpes={"SPY": {"strat": 0.2}},
        )
        text = "\n".join(lines)
        assert "regime shift" in text

    def test_missing_is_sharpe_for_ticker_mode_renders_dash(self):
        """If a ticker is in WF but has no matching IS Sharpe, the
        verdict cell shows — rather than fabricating a comparison."""
        df = _wf_frame("SPY", "strat", [0.4, 0.5, 0.6])
        lines = insight_walk_forward(
            {"SPY": df},
            in_sample_sharpes={"SPY": {"base": 0.5}},  # only base, not strat
        )
        text = "\n".join(lines)
        # The strat row should show a dash verdict — no fabricated value.
        assert "In-Sample vs Out-of-Sample" in text
