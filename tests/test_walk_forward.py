"""Tests for lib/walk_forward.py — Walk-forward validation."""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime

from lib.walk_forward import WalkForwardValidator, WalkForwardResult
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
