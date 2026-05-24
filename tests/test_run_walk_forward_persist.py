"""Tests for scripts/run_walk_forward.py:persist_walk_forward.

Mirrors tests/test_backtest_pipeline_tables.py:TestPersistTrades — the
walk-forward stage of the backtest pipeline writes per-fold aggregate
metrics to backtest_walk_forward_folds. These tests pin:

  * the table + conflict-cols contract,
  * one-row-per-fold shape with stability_score denormalised,
  * the INT-coercion guard (so a zero-trade fold doesn't break pg8000),
  * fail-loud behaviour on DB error (CLAUDE.md §3.7).

Cloud SQL is fully mocked. The WalkForwardValidator is also mocked at
the persist-helper boundary so the tests are hermetic.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

import gcp.database as db
import scripts.run_walk_forward as rwf


RUN_ID = "11111111-2222-3333-4444-555555555555"


# ── helpers ────────────────────────────────────────────────────────────

def _fake_fold_result(metrics: dict) -> MagicMock:
    """A BacktestResult-shaped mock whose .metrics() returns ``metrics``."""
    m = MagicMock()
    m.metrics.return_value = metrics
    return m


def _fake_wf_result(n_folds: int = 3, stability: float = 0.67) -> MagicMock:
    """A WalkForwardResult-shaped mock with ``n_folds`` folds."""
    wf = MagicMock()
    fold_results = []
    fold_dates = []
    for i in range(n_folds):
        # Per-fold metric dict matching BacktestResult.metrics() keys.
        fold_results.append(_fake_fold_result({
            'total_trades': 20 + i,
            'win_rate': 0.5 + 0.02 * i,
            'profit_factor': 1.0 + 0.1 * i,
            'expectancy_pct': 0.0005 + 0.00005 * i,
            'sharpe_ratio': 0.3 + 0.1 * i,
            'max_drawdown_pct': -0.05 - 0.01 * i,
            'avg_win_pct': 0.004,
            'avg_loss_pct': -0.003,
        }))
        fold_dates.append({
            'train_start': pd.Timestamp(f'2024-01-01'),
            'train_end': pd.Timestamp(f'2024-{i+4:02d}-01'),
            'test_start': pd.Timestamp(f'2024-{i+4:02d}-01'),
            'test_end': pd.Timestamp(f'2024-{i+7:02d}-01'),
        })
    wf.fold_results = fold_results
    wf.fold_dates = fold_dates
    wf.stability_score = stability
    return wf


# ── _wf_result_to_dataframe ────────────────────────────────────────────

class TestWFResultToDataFrame:
    def test_one_row_per_fold(self):
        wf = _fake_wf_result(n_folds=5)
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "SPY", use_strat=True,
        )
        assert len(df) == 5
        assert list(df["fold_index"]) == [0, 1, 2, 3, 4]

    def test_tags_run_grouping_columns(self):
        wf = _fake_wf_result(n_folds=3)
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "IWM", use_strat=False,
        )
        assert (df["run_id"] == RUN_ID).all()
        assert (df["ticker"] == "IWM").all()
        assert (df["use_strat"] == False).all()  # noqa: E712
        assert (df["mode"] == "base").all()

    def test_strat_mode_label(self):
        wf = _fake_wf_result(n_folds=2)
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "QQQ", use_strat=True,
        )
        assert (df["mode"] == "strat").all()
        assert (df["use_strat"] == True).all()  # noqa: E712

    def test_stability_score_denormalised(self):
        """Same value on every row — schema says so. Simple query."""
        wf = _fake_wf_result(n_folds=4, stability=0.75)
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "SPY", use_strat=True,
        )
        assert (df["stability_score"] == 0.75).all()

    def test_metric_columns_present(self):
        wf = _fake_wf_result(n_folds=2)
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "SPY", use_strat=True,
        )
        for col in ("total_trades", "win_rate", "profit_factor",
                    "expectancy", "sharpe", "max_dd", "avg_win", "avg_loss"):
            assert col in df.columns

    def test_dates_as_date_objects(self):
        """train_start / test_end / etc must be DATEs, not timestamps —
        the table column type is DATE."""
        import datetime as dt
        wf = _fake_wf_result(n_folds=1)
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "SPY", use_strat=True,
        )
        for col in ("train_start", "train_end", "test_start", "test_end"):
            v = df[col].iloc[0]
            assert isinstance(v, dt.date) and not isinstance(v, dt.datetime), \
                f"{col} should be a date, got {type(v)}"

    def test_empty_wf_yields_empty_df(self):
        wf = MagicMock()
        wf.fold_results = []
        wf.fold_dates = []
        wf.stability_score = 0.0
        df = rwf._wf_result_to_dataframe(
            wf, RUN_ID, "SPY", use_strat=True,
        )
        assert df.empty


# ── persist_walk_forward ───────────────────────────────────────────────

class TestPersistWalkForward:
    def _wf_df(self, n: int = 3) -> pd.DataFrame:
        wf = _fake_wf_result(n_folds=n)
        return rwf._wf_result_to_dataframe(
            wf, RUN_ID, "SPY", use_strat=True,
        )

    def test_writes_to_backtest_walk_forward_folds_table(self):
        wf_df = self._wf_df(3)
        with patch.object(db, "upsert_dataframe", return_value=3) as ups:
            n = rwf.persist_walk_forward(
                wf_df, RUN_ID, "SPY", use_strat=True,
            )
        assert n == 3
        ups.assert_called_once()
        kwargs = ups.call_args[1]
        assert kwargs["table"] == "backtest_walk_forward_folds"
        assert kwargs["conflict_cols"] == [
            "run_id", "ticker", "mode", "fold_index",
        ]

    def test_one_row_per_fold_shape(self):
        wf_df = self._wf_df(4)
        with patch.object(db, "upsert_dataframe", return_value=4) as ups:
            rwf.persist_walk_forward(
                wf_df, RUN_ID, "SPY", use_strat=True,
            )
        df = ups.call_args[0][0]
        assert len(df) == 4
        assert list(df["fold_index"]) == [0, 1, 2, 3]

    def test_persist_does_not_bypass_int_coercion(self):
        """A zero-trade fold can produce NaN-widened total_trades. The
        caller-side coercion guard in persist_walk_forward (and the
        systemic _coerce_int_columns inside upsert_dataframe, PR #518)
        must keep that column safe to bind as INTEGER. The contract
        verified here: after persist_walk_forward, no float NaN remains
        in total_trades — every NaN must have become None so pg8000
        can bind NULL rather than the string '15.0'."""
        wf_df = self._wf_df(3).copy()
        wf_df.loc[1, "total_trades"] = float("nan")
        with patch.object(db, "upsert_dataframe", return_value=3) as ups:
            rwf.persist_walk_forward(
                wf_df, RUN_ID, "SPY", use_strat=True,
            )
        written = ups.call_args[0][0]
        # The NaN entry must not survive — it must be None (NULL).
        # pd.isna(None) is True AND v is None — distinguish the two.
        assert written["total_trades"].iloc[1] is None
        # Finite entries must round-trip to an integer value (not a
        # fractional float). 20 + 0 == 20 (fold 0), 20 + 2 == 22 (fold 2).
        assert int(written["total_trades"].iloc[0]) == 20
        assert int(written["total_trades"].iloc[2]) == 22

    def test_empty_df_writes_nothing(self):
        with patch.object(db, "upsert_dataframe") as ups:
            n = rwf.persist_walk_forward(
                pd.DataFrame(), RUN_ID, "SPY", use_strat=True,
            )
        assert n == 0
        ups.assert_not_called()

    def test_db_failure_propagates(self):
        """No silent fallback: a Cloud SQL write failure must raise
        (CLAUDE.md §3.7 — data-access code re-raises)."""
        wf_df = self._wf_df(2)
        with patch.object(db, "upsert_dataframe",
                          side_effect=RuntimeError("cloud sql down")):
            with pytest.raises(RuntimeError, match="cloud sql down"):
                rwf.persist_walk_forward(
                    wf_df, RUN_ID, "SPY", use_strat=True,
                )

    def test_stability_score_survives_persist(self):
        """The denormalised stability_score column must NOT be dropped
        on the upsert path — the schema column exists and the report
        reads it as the canonical stability metric."""
        wf_df = self._wf_df(3)
        with patch.object(db, "upsert_dataframe", return_value=3) as ups:
            rwf.persist_walk_forward(
                wf_df, RUN_ID, "SPY", use_strat=True,
            )
        df = ups.call_args[0][0]
        assert "stability_score" in df.columns
        # The fake WF result fixed stability_score at 0.67.
        assert (df["stability_score"] == 0.67).all()
