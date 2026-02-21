"""Tests for lib/backtest.py — Backtesting engine."""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta

from lib.backtest import BacktestEngine, BacktestResult, Trade
from lib.config import RiskConfig, ExitConfig, SignalConfig, StratConfig


def _make_intraday_df(n_days=3, bars_per_day=390, seed=42):
    """Create multi-day 1-minute OHLCV data for backtesting."""
    np.random.seed(seed)
    frames = []
    base = 200.0

    for d in range(n_days):
        day_date = pd.Timestamp('2024-01-02') + pd.Timedelta(days=d)
        # Skip weekends
        while day_date.weekday() >= 5:
            day_date += pd.Timedelta(days=1)

        times = pd.date_range(
            f'{day_date.date()} 09:30',
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
def intraday_data():
    return _make_intraday_df(n_days=5)


@pytest.fixture
def engine():
    return BacktestEngine(
        risk_config=RiskConfig(),
        exit_config=ExitConfig(),
        signal_config=SignalConfig(min_conditions=2),  # Lower threshold for testing
        strat_config=StratConfig(),
    )


class TestTradeDataclass:
    def test_trade_defaults(self):
        t = Trade(
            entry_time=datetime(2024, 1, 2, 10, 0),
            entry_price=200.0,
            direction='CALL',
            base_score=3,
            strat_bonus=0,
            total_score=3,
            position_size=0.25,
            conditions_met=['consecutive_down', 'rsi_oversold_zone', 'below_vwap'],
        )
        assert t.exit_time is None
        assert t.exit_price is None
        assert t.exit_reason is None
        assert t.return_pct is None
        assert t.mae == 0.0
        assert t.mfe == 0.0


class TestBacktestResult:
    def test_empty_result(self):
        result = BacktestResult(trades=[], daily_pnl=[], equity_curve=pd.Series(dtype=float))
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.avg_win == 0.0
        assert result.avg_loss == 0.0
        assert result.expectancy == 0.0

    def test_result_with_trades(self):
        trades = [
            Trade(
                entry_time=datetime(2024, 1, 2, 10, 0),
                entry_price=200.0,
                direction='CALL',
                base_score=3,
                strat_bonus=0,
                total_score=3,
                position_size=0.25,
                conditions_met=['c1', 'c2', 'c3'],
                exit_time=datetime(2024, 1, 2, 10, 15),
                exit_price=200.60,
                exit_reason='target',
                return_pct=0.003,
            ),
            Trade(
                entry_time=datetime(2024, 1, 2, 11, 0),
                entry_price=200.50,
                direction='PUT',
                base_score=3,
                strat_bonus=0,
                total_score=3,
                position_size=0.25,
                conditions_met=['c1', 'c2', 'c3'],
                exit_time=datetime(2024, 1, 2, 11, 30),
                exit_price=200.80,
                exit_reason='stop_loss',
                return_pct=-0.0015,
            ),
        ]
        result = BacktestResult(
            trades=trades,
            daily_pnl=[{'date': '2024-01-02', 'trades': 2, 'pnl': 0.001}],
            equity_curve=pd.Series([1.001], index=['2024-01-02']),
        )
        assert result.total_trades == 2
        assert result.win_rate == 0.5
        assert result.avg_win == 0.003
        assert result.avg_loss == -0.0015
        assert len(result.winners) == 1
        assert len(result.losers) == 1

    def test_profit_factor(self):
        trades = [
            Trade(entry_time=datetime.now(), entry_price=100, direction='CALL',
                  base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
                  conditions_met=[], return_pct=0.004),
            Trade(entry_time=datetime.now(), entry_price=100, direction='CALL',
                  base_score=3, strat_bonus=0, total_score=3, position_size=0.25,
                  conditions_met=[], return_pct=-0.002),
        ]
        result = BacktestResult(trades=trades, daily_pnl=[])
        assert result.profit_factor == 0.004 / 0.002

    def test_to_dataframe(self):
        trades = [
            Trade(entry_time=datetime.now(), entry_price=100, direction='CALL',
                  base_score=3, strat_bonus=1, total_score=4, position_size=0.25,
                  conditions_met=['c1'], exit_time=datetime.now(),
                  exit_price=100.3, exit_reason='target', return_pct=0.003),
        ]
        result = BacktestResult(trades=trades, daily_pnl=[])
        df = result.to_dataframe()
        assert len(df) == 1
        assert 'direction' in df.columns
        assert 'return_pct' in df.columns
        assert 'strat_bonus' in df.columns

    def test_summary_string(self):
        result = BacktestResult(trades=[], daily_pnl=[])
        summary = result.summary()
        assert 'Backtest Results' in summary
        assert 'Win Rate' in summary

    def test_metrics_dict(self):
        result = BacktestResult(trades=[], daily_pnl=[])
        m = result.metrics()
        assert 'total_trades' in m
        assert 'win_rate' in m
        assert 'profit_factor' in m
        assert 'sharpe_ratio' in m


class TestBacktestEngine:
    def test_engine_runs_without_error(self, engine, intraday_data):
        result = engine.run(intraday_data)
        assert isinstance(result, BacktestResult)

    def test_engine_produces_daily_pnl(self, engine, intraday_data):
        result = engine.run(intraday_data)
        assert isinstance(result.daily_pnl, list)
        # Should have at least one day of data
        assert len(result.daily_pnl) >= 1

    def test_engine_respects_max_daily_trades(self, intraday_data):
        engine = BacktestEngine(
            risk_config=RiskConfig(max_daily_trades=1),
            signal_config=SignalConfig(min_conditions=1),
        )
        result = engine.run(intraday_data)
        # Check that no day has more trades than the limit
        for day_info in result.daily_pnl:
            assert day_info['trades'] <= 1

    def test_engine_with_strat(self, engine, intraday_data):
        result = engine.run(intraday_data, use_strat=True)
        assert isinstance(result, BacktestResult)

    def test_all_trades_have_exit(self, engine, intraday_data):
        result = engine.run(intraday_data)
        for trade in result.trades:
            assert trade.exit_time is not None
            assert trade.exit_price is not None
            assert trade.exit_reason is not None
            assert trade.return_pct is not None

    def test_exit_reasons_valid(self, engine, intraday_data):
        result = engine.run(intraday_data)
        valid_reasons = {'target', 'stop_loss', 'time_stop', 'rsi_extreme', 'eod_close'}
        for trade in result.trades:
            assert trade.exit_reason in valid_reasons

    def test_equity_curve_length(self, engine, intraday_data):
        result = engine.run(intraday_data)
        # Equity curve should have one point per trading day
        assert len(result.equity_curve) == len(result.daily_pnl)
