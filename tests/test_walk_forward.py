"""Tests for lib/walk_forward.py — Walk-forward validation."""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime

from lib.walk_forward import (
    WalkForwardValidator, WalkForwardResult, select_calibration_winner,
)
from lib.backtest import BacktestResult
from lib.config import RiskConfig, ExitConfig, SignalConfig, StratConfig


def _make_long_intraday(n_months=4, bars_per_day=100, seed=42):
    """Create several months of 1-minute data for walk-forward testing.

    Uses fewer bars per day than real data to keep tests fast.
    """
    np.random.seed(seed)
    frames = []
    base = 200.0

    start = pd.Timestamp('2024-01-02')
    end = start + pd.DateOffset(months=n_months)
    trading_days = pd.bdate_range(start, end)

    for day in trading_days:
        times = pd.date_range(
            f'{day.date()} 09:30',
            periods=bars_per_day,
            freq='1min',
        )

        returns = np.random.normal(0, 0.001, bars_per_day)
        close = base * np.exp(np.cumsum(returns))
        high = close * (1 + np.abs(np.random.normal(0, 0.001, bars_per_day)))
        low = close * (1 - np.abs(np.random.normal(0, 0.001, bars_per_day)))
        open_ = np.roll(close, 1)
        open_[0] = base
        volume = np.random.randint(10000, 100000, bars_per_day).astype(float)

        df = pd.DataFrame({
            'Time': times,
            'Open': open_,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': volume,
        }, index=times)
        frames.append(df)
        base = close[-1]

    return pd.concat(frames)


@pytest.fixture
def long_data():
    """4 months of data: enough for 1 train + multiple test folds."""
    return _make_long_intraday(n_months=4)


@pytest.fixture
def validator():
    return WalkForwardValidator(
        risk_config=RiskConfig(),
        exit_config=ExitConfig(),
        signal_config=SignalConfig(min_conditions=2),
        strat_config=StratConfig(),
        train_months=2,
        test_months=1,
    )


class TestWalkForwardResult:
    def test_empty_result(self):
        result = WalkForwardResult(
            fold_results=[],
            fold_dates=[],
            aggregate_metrics={},
            stability_score=0.0,
        )
        assert result.stability_score == 0.0
        summary = result.summary()
        assert 'Walk-Forward' in summary
        assert 'Total Folds: 0' in summary


class TestWalkForwardValidator:
    def test_run_produces_result(self, validator, long_data):
        result = validator.run(long_data)
        assert isinstance(result, WalkForwardResult)

    def test_fold_count(self, validator, long_data):
        result = validator.run(long_data)
        # 4 months of data, 2 train + 1 test = at least 1 fold
        assert len(result.fold_results) >= 1

    def test_fold_dates_populated(self, validator, long_data):
        result = validator.run(long_data)
        assert len(result.fold_dates) == len(result.fold_results)
        for dates in result.fold_dates:
            assert 'train_start' in dates
            assert 'train_end' in dates
            assert 'test_start' in dates
            assert 'test_end' in dates

    def test_fold_dates_non_overlapping(self, validator, long_data):
        result = validator.run(long_data)
        if len(result.fold_dates) >= 2:
            for i in range(1, len(result.fold_dates)):
                prev_end = result.fold_dates[i-1]['test_end']
                curr_start = result.fold_dates[i]['test_start']
                assert curr_start >= prev_end

    def test_stability_score_range(self, validator, long_data):
        result = validator.run(long_data)
        assert 0.0 <= result.stability_score <= 1.0

    def test_aggregate_metrics(self, validator, long_data):
        result = validator.run(long_data)
        if result.fold_results:
            assert 'total_folds' in result.aggregate_metrics
            assert 'total_trades_all_folds' in result.aggregate_metrics

    def test_summary_string(self, validator, long_data):
        result = validator.run(long_data)
        summary = result.summary()
        assert isinstance(summary, str)
        assert 'Walk-Forward' in summary

    def test_with_strat(self, validator, long_data):
        result = validator.run(long_data, use_strat=True)
        assert isinstance(result, WalkForwardResult)


class TestParameterSensitivity:
    def test_param_sweep(self, long_data):
        """Small param sweep to verify it runs."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
        )
        param_grid = {
            'consecutive_periods': [2, 3],
        }
        results_df = validator.parameter_sensitivity(
            long_data, param_grid, close_col='Close',
        )
        assert isinstance(results_df, pd.DataFrame)
        assert len(results_df) == 2
        assert 'consecutive_periods' in results_df.columns
        assert 'expectancy_pct' in results_df.columns


class TestWalkForwardSweep:
    """lib/walk_forward.py:WalkForwardValidator.walk_forward_sweep — the
    per-combo walk-forward used by the ETF calibration sweep."""

    def test_sweep_shape(self, long_data):
        """One row per combo, with the param values and the WF aggregate
        metrics the calibration sweep ranks on."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        param_grid = {
            'consecutive_periods': [2, 3],
            'call_target': [0.0030, 0.0035],
        }
        df = validator.walk_forward_sweep(long_data, param_grid, close_col='Close')
        assert isinstance(df, pd.DataFrame)
        # 2 x 2 grid -> 4 combos.
        assert len(df) == 4
        # Param values echoed back.
        assert 'consecutive_periods' in df.columns
        assert 'call_target' in df.columns
        # Walk-forward aggregate metrics present for every row.
        for col in ('stability_score', 'avg_expectancy_pct', 'avg_win_rate',
                    'std_expectancy_pct', 'total_folds', 'total_trades'):
            assert col in df.columns
        # stability_score is a fraction-of-profitable-folds in [0, 1].
        assert ((df['stability_score'] >= 0.0)
                & (df['stability_score'] <= 1.0)).all()

    def test_sweep_single_combo(self, long_data):
        """A 1-combo grid still returns a well-formed 1-row frame."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        df = validator.walk_forward_sweep(
            long_data, {'consecutive_periods': [3]}, close_col='Close',
        )
        assert len(df) == 1
        assert df.iloc[0]['consecutive_periods'] == 3


class TestSelectCalibrationWinner:
    """lib/walk_forward.py:select_calibration_winner — the strategic
    auto-apply gate. Pure function; build frames directly."""

    def _frame(self, rows):
        return pd.DataFrame(rows)

    def test_picks_highest_expectancy_among_gated(self):
        df = self._frame([
            # clears gates, lower expectancy
            {'call_target': 0.0030, 'stability_score': 0.8,
             'avg_expectancy_pct': 0.0010, 'total_trades': 100},
            # clears gates, highest expectancy -> winner
            {'call_target': 0.0035, 'stability_score': 0.7,
             'avg_expectancy_pct': 0.0025, 'total_trades': 80},
        ])
        winner = select_calibration_winner(df)
        assert winner is not None
        assert winner['call_target'] == 0.0035

    def test_none_when_stability_too_low(self):
        df = self._frame([
            {'call_target': 0.0030, 'stability_score': 0.4,
             'avg_expectancy_pct': 0.0025, 'total_trades': 100},
        ])
        assert select_calibration_winner(df) is None

    def test_none_when_expectancy_not_positive(self):
        df = self._frame([
            {'call_target': 0.0030, 'stability_score': 0.9,
             'avg_expectancy_pct': -0.0001, 'total_trades': 100},
        ])
        assert select_calibration_winner(df) is None

    def test_none_when_too_few_trades(self):
        df = self._frame([
            {'call_target': 0.0030, 'stability_score': 0.9,
             'avg_expectancy_pct': 0.0025, 'total_trades': 12},
        ])
        assert select_calibration_winner(df) is None

    def test_none_on_empty_frame(self):
        assert select_calibration_winner(pd.DataFrame()) is None
        assert select_calibration_winner(None) is None

    def test_weak_combo_excluded_strong_combo_wins(self):
        """A frame mixing failing and passing combos returns the best
        *passing* one, not the global-max-expectancy row."""
        df = self._frame([
            # highest expectancy overall but fails the stability gate
            {'call_target': 0.0040, 'stability_score': 0.2,
             'avg_expectancy_pct': 0.0090, 'total_trades': 100},
            # the best combo that actually clears every gate
            {'call_target': 0.0032, 'stability_score': 0.75,
             'avg_expectancy_pct': 0.0018, 'total_trades': 60},
        ])
        winner = select_calibration_winner(df)
        assert winner is not None
        assert winner['call_target'] == 0.0032


class TestRebuildConsecutive:
    """lib/walk_forward.py:_rebuild_consecutive — the per-combo rebuild
    that keeps the Consecutive_Up/Down column window in lockstep with the
    swept consecutive_periods threshold."""

    def test_window_saturates_at_n(self):
        from lib.walk_forward import _rebuild_consecutive
        # A strictly rising series — every bar is an up-move, so the
        # rolling-N up-count saturates at the window size N.
        df = pd.DataFrame({'Close': list(range(1, 21))})
        assert _rebuild_consecutive(df, 3)['Consecutive_Up'].max() == 3
        assert _rebuild_consecutive(df, 5)['Consecutive_Up'].max() == 5

    def test_does_not_mutate_input(self):
        from lib.walk_forward import _rebuild_consecutive
        df = pd.DataFrame({'Close': [100.0, 101.0, 102.0]})
        _rebuild_consecutive(df, 3)
        assert 'Consecutive_Up' not in df.columns

    def test_uses_existing_price_change_column(self):
        from lib.walk_forward import _rebuild_consecutive
        # When Price_Change is already present it is used as-is rather
        # than recomputed from Close.
        df = pd.DataFrame({
            'Close': [100.0, 100.0, 100.0],
            'Price_Change': [1.0, 1.0, 1.0],  # all up despite flat Close
        })
        out = _rebuild_consecutive(df, 2)
        assert out['Consecutive_Up'].iloc[-1] == 2
