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

    def test_trade_ftfc_score_default(self):
        """Trade dataclass should default ftfc_score to 0.0."""
        t = Trade(
            entry_time=datetime(2024, 1, 2, 10, 0),
            entry_price=200.0,
            direction='CALL',
            base_score=3,
            strat_bonus=0,
            total_score=3,
            position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )
        assert t.ftfc_score == 0.0

    def test_trade_orb_trend_default(self):
        """Trade dataclass should default orb_trend to 0."""
        t = Trade(
            entry_time=datetime(2024, 1, 2, 10, 0),
            entry_price=200.0,
            direction='PUT',
            base_score=3,
            strat_bonus=0,
            total_score=3,
            position_size=0.25,
            conditions_met=['c1', 'c2', 'c3'],
        )
        assert t.orb_trend == 0

    def test_trade_ftfc_score_and_orb_trend_can_be_set(self):
        """ftfc_score and orb_trend should accept explicit values."""
        t = Trade(
            entry_time=datetime(2024, 1, 2, 10, 0),
            entry_price=200.0,
            direction='CALL',
            base_score=3,
            strat_bonus=1,
            total_score=4,
            position_size=0.50,
            conditions_met=['c1', 'c2', 'c3'],
            ftfc_score=0.75,
            orb_trend=1,
        )
        assert t.ftfc_score == 0.75
        assert t.orb_trend == 1


class TestBacktestResult:
    def test_empty_result(self):
        result = BacktestResult(trades=[], daily_pnl=[], equity_curve=pd.Series(dtype=float))
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.avg_win == 0.0
        assert result.avg_loss == 0.0
        assert result.expectancy == 0.0

    def test_sharpe_ratio_single_day_returns_zero_not_nan(self):
        """REGRESSION: a fold/result with a SINGLE day of PnL produced a
        NaN Sharpe (pandas std(ddof=1) needs ≥2 samples). The NaN landed
        in backtest_walk_forward_folds.sharpe as a Postgres `NaN` value
        (distinct from NULL), then poisoned downstream AVG/MAX aggregates
        in the SPY/QQQ WF summaries. The original `if std == 0` guard
        didn't catch it because `NaN == 0` is False in IEEE 754.

        Sharpe with no return variance to measure is honestly 0.0; this
        test pins that contract."""
        result = BacktestResult(
            trades=[], daily_pnl=[{'pnl': 0.01}],
            equity_curve=pd.Series(dtype=float),
        )
        sh = result.sharpe_ratio
        assert sh == 0.0, f"single-day Sharpe should be 0.0, got {sh!r}"
        assert not pd.isna(sh), "Sharpe must never be NaN — poisons AVG"

    def test_sharpe_ratio_zero_variance_returns_zero(self):
        """All-identical daily PnL → std=0 → return 0.0. Existing
        behaviour, pin so a refactor doesn't accidentally return
        +/-inf via division by zero."""
        result = BacktestResult(
            trades=[],
            daily_pnl=[{'pnl': 0.005}, {'pnl': 0.005}, {'pnl': 0.005}],
            equity_curve=pd.Series(dtype=float),
        )
        assert result.sharpe_ratio == 0.0

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

    def test_filter_counts_default(self):
        """BacktestResult should have filter_counts with default keys."""
        result = BacktestResult(trades=[], daily_pnl=[])
        assert isinstance(result.filter_counts, dict)
        assert 'ftfc_rejected' in result.filter_counts
        assert 'orb_rejected' in result.filter_counts
        assert 'signals_evaluated' in result.filter_counts
        assert result.filter_counts['ftfc_rejected'] == 0
        assert result.filter_counts['orb_rejected'] == 0
        assert result.filter_counts['signals_evaluated'] == 0

    def test_filter_counts_custom(self):
        """filter_counts should accept custom values."""
        fc = {'ftfc_rejected': 5, 'orb_rejected': 3, 'signals_evaluated': 20}
        result = BacktestResult(trades=[], daily_pnl=[], filter_counts=fc)
        assert result.filter_counts['ftfc_rejected'] == 5
        assert result.filter_counts['orb_rejected'] == 3
        assert result.filter_counts['signals_evaluated'] == 20

    def test_metrics_by_exit_reason_empty(self):
        """metrics_by_exit_reason with no trades returns empty DataFrame."""
        result = BacktestResult(trades=[], daily_pnl=[])
        df = result.metrics_by_exit_reason()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_metrics_by_exit_reason_with_trades(self):
        """metrics_by_exit_reason groups trades by exit reason."""
        trades = [
            Trade(entry_time=datetime(2024, 1, 2, 10, 0), entry_price=200.0,
                  direction='CALL', base_score=3, strat_bonus=0, total_score=3,
                  position_size=0.25, conditions_met=['c1', 'c2', 'c3'],
                  exit_time=datetime(2024, 1, 2, 10, 15), exit_price=200.60,
                  exit_reason='target', return_pct=0.003),
            Trade(entry_time=datetime(2024, 1, 2, 11, 0), entry_price=200.50,
                  direction='PUT', base_score=3, strat_bonus=0, total_score=3,
                  position_size=0.25, conditions_met=['c1', 'c2', 'c3'],
                  exit_time=datetime(2024, 1, 2, 11, 30), exit_price=200.80,
                  exit_reason='stop_loss', return_pct=-0.0015),
            Trade(entry_time=datetime(2024, 1, 2, 12, 0), entry_price=201.0,
                  direction='CALL', base_score=3, strat_bonus=0, total_score=3,
                  position_size=0.25, conditions_met=['c1', 'c2', 'c3'],
                  exit_time=datetime(2024, 1, 2, 12, 30), exit_price=201.50,
                  exit_reason='target', return_pct=0.0025),
        ]
        result = BacktestResult(trades=trades, daily_pnl=[])
        df = result.metrics_by_exit_reason()
        assert not df.empty
        assert 'target' in df.index
        assert 'stop_loss' in df.index
        assert df.loc['target', 'trades'] == 2
        assert df.loc['stop_loss', 'trades'] == 1

    def test_metrics_by_direction_empty(self):
        """metrics_by_direction with no trades returns empty DataFrame."""
        result = BacktestResult(trades=[], daily_pnl=[])
        df = result.metrics_by_direction()
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_metrics_by_direction_with_trades(self):
        """metrics_by_direction groups trades by CALL/PUT."""
        trades = [
            Trade(entry_time=datetime(2024, 1, 2, 10, 0), entry_price=200.0,
                  direction='CALL', base_score=3, strat_bonus=0, total_score=3,
                  position_size=0.25, conditions_met=['c1', 'c2', 'c3'],
                  exit_time=datetime(2024, 1, 2, 10, 15), exit_price=200.60,
                  exit_reason='target', return_pct=0.003),
            Trade(entry_time=datetime(2024, 1, 2, 11, 0), entry_price=200.50,
                  direction='PUT', base_score=3, strat_bonus=0, total_score=3,
                  position_size=0.25, conditions_met=['c1', 'c2', 'c3'],
                  exit_time=datetime(2024, 1, 2, 11, 30), exit_price=200.80,
                  exit_reason='stop_loss', return_pct=-0.0015),
            Trade(entry_time=datetime(2024, 1, 2, 12, 0), entry_price=201.0,
                  direction='CALL', base_score=3, strat_bonus=0, total_score=3,
                  position_size=0.25, conditions_met=['c1', 'c2', 'c3'],
                  exit_time=datetime(2024, 1, 2, 12, 30), exit_price=201.50,
                  exit_reason='target', return_pct=0.0025),
        ]
        result = BacktestResult(trades=trades, daily_pnl=[])
        df = result.metrics_by_direction()
        assert not df.empty
        assert 'CALL' in df.index
        assert 'PUT' in df.index
        assert df.loc['CALL', 'trades'] == 2
        assert df.loc['PUT', 'trades'] == 1

    def test_to_dataframe_includes_ftfc_and_orb_columns(self):
        """to_dataframe() should include ftfc_score and orb_trend columns."""
        trades = [
            Trade(entry_time=datetime(2024, 1, 2, 10, 0), entry_price=200.0,
                  direction='CALL', base_score=3, strat_bonus=1, total_score=4,
                  position_size=0.50, conditions_met=['c1', 'c2', 'c3'],
                  ftfc_score=0.8, orb_trend=1,
                  exit_time=datetime(2024, 1, 2, 10, 15), exit_price=200.60,
                  exit_reason='target', return_pct=0.003),
        ]
        result = BacktestResult(trades=trades, daily_pnl=[])
        df = result.to_dataframe()
        assert 'ftfc_score' in df.columns
        assert 'orb_trend' in df.columns
        assert df.iloc[0]['ftfc_score'] == 0.8
        assert df.iloc[0]['orb_trend'] == 1


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

    def test_strat_filtering_produces_fewer_or_equal_trades(self, intraday_data):
        """With use_strat=True and filtering enabled, trade count should be
        <= the unfiltered count (filters can only remove trades)."""
        signal_cfg = SignalConfig(min_conditions=2)

        engine_no_strat = BacktestEngine(
            risk_config=RiskConfig(),
            exit_config=ExitConfig(),
            signal_config=signal_cfg,
        )
        result_no_strat = engine_no_strat.run(intraday_data, use_strat=False)

        engine_strat = BacktestEngine(
            risk_config=RiskConfig(),
            exit_config=ExitConfig(),
            signal_config=signal_cfg,
            strat_config=StratConfig(ftfc_filter_enabled=True, orb_filter_enabled=True),
        )
        result_strat = engine_strat.run(intraday_data, use_strat=True)

        # Strat filtering can only reduce (or equal) the number of trades
        assert result_strat.total_trades <= result_no_strat.total_trades

    def test_filter_counts_populated_with_strat(self, intraday_data):
        """When use_strat=True, filter_counts['signals_evaluated'] should be > 0."""
        engine = BacktestEngine(
            risk_config=RiskConfig(),
            exit_config=ExitConfig(),
            signal_config=SignalConfig(min_conditions=2),
            strat_config=StratConfig(ftfc_filter_enabled=True, orb_filter_enabled=True),
        )
        result = engine.run(intraday_data, use_strat=True)

        # signals_evaluated should be positive since we process signals
        assert result.filter_counts['signals_evaluated'] > 0
        # Rejection counts should be non-negative integers
        assert result.filter_counts['ftfc_rejected'] >= 0
        assert result.filter_counts['orb_rejected'] >= 0

    def test_filter_counts_zero_without_strat(self, engine, intraday_data):
        """Without use_strat, filter_counts should remain at zero for rejections,
        but signals_evaluated should still be tracked."""
        result = engine.run(intraday_data, use_strat=False)
        # FTFC and ORB rejection counts should be zero without strat
        assert result.filter_counts['ftfc_rejected'] == 0
        assert result.filter_counts['orb_rejected'] == 0

    def test_strat_trades_have_ftfc_and_orb_fields(self, intraday_data):
        """When use_strat=True, trades should have ftfc_score and orb_trend set."""
        engine = BacktestEngine(
            risk_config=RiskConfig(),
            exit_config=ExitConfig(),
            signal_config=SignalConfig(min_conditions=2),
            strat_config=StratConfig(),
        )
        result = engine.run(intraday_data, use_strat=True)

        for trade in result.trades:
            assert isinstance(trade.ftfc_score, float)
            assert isinstance(trade.orb_trend, int)
            assert -1.0 <= trade.ftfc_score <= 1.0
            assert trade.orb_trend in (-1, 0, 1)

    # ── Happy-path: the engine actually GENERATES trades and computes P&L ──
    #
    # The existing TestBacktestEngine assertions iterate `result.trades`,
    # so they all pass VACUOUSLY if the engine produces zero trades. These
    # companions pin that the realistic synthetic OHLCV fixture exercises a
    # non-empty trade path and that the derived metrics obey their
    # mathematical invariants. No expected numbers are hand-typed — every
    # assertion is either "> 0", a known bound (win-rate in [0,1]), or a
    # cross-check between two independently-computed quantities.

    def test_engine_generates_nonzero_trades(self, engine, intraday_data):
        """Guard against the silent empty-trade path: the realistic fixture
        must produce real trades, otherwise every per-trade test above is
        a no-op."""
        result = engine.run(intraday_data)
        assert result.total_trades > 0, (
            "engine produced 0 trades on realistic OHLCV — all per-trade "
            "assertions would pass vacuously"
        )
        # winners + losers must partition all completed trades exactly.
        completed = [t for t in result.trades if t.return_pct is not None]
        assert len(result.winners) + len(result.losers) == len(completed)

    def test_win_rate_in_unit_interval_and_matches_counts(self, engine,
                                                          intraday_data):
        """win_rate is a probability: in [0, 1], and equals
        winners / total computed independently."""
        result = engine.run(intraday_data)
        assert result.total_trades > 0
        wr = result.win_rate
        assert 0.0 <= wr <= 1.0
        expected = len(result.winners) / result.total_trades
        assert wr == pytest.approx(expected)

    def test_pnl_accounting_self_consistent(self, engine, intraday_data):
        """Expectancy = mean(return_pct) over completed trades, and the
        winner/loser split agrees with the signs of avg_win/avg_loss.
        Cross-checks the engine's aggregates against a from-scratch
        recompute on the raw per-trade returns (no fabricated constants)."""
        result = engine.run(intraday_data)
        assert result.total_trades > 0
        returns = [t.return_pct for t in result.trades if t.return_pct is not None]
        assert returns, "completed trades must carry a return_pct"
        assert result.expectancy == pytest.approx(float(np.mean(returns)))
        if result.winners:
            assert result.avg_win > 0
            assert result.avg_win == pytest.approx(
                float(np.mean([t.return_pct for t in result.winners])))
        if result.losers:
            assert result.avg_loss <= 0
        # daily_pnl pnl should sum to the position-weighted trade P&L the
        # engine booked, not be an independent fabrication: total booked
        # P&L is finite and not NaN.
        total_daily = sum(d['pnl'] for d in result.daily_pnl)
        assert np.isfinite(total_daily)

    def test_no_look_ahead_exit_after_entry(self, engine, intraday_data):
        """Every closed trade exits at or after it enters, and the exit
        price is a real number — i.e. the engine cannot 'see' a future
        bar before the entry bar. Look-ahead would manifest as an exit
        timestamp earlier than entry."""
        result = engine.run(intraday_data)
        assert result.total_trades > 0
        for t in result.trades:
            if t.exit_time is not None:
                assert t.exit_time >= t.entry_time, (
                    f"exit {t.exit_time} precedes entry {t.entry_time} — "
                    "look-ahead bug"
                )
                assert t.exit_price is not None and np.isfinite(t.exit_price)

    def test_sharpe_and_profit_factor_finite_on_real_run(self, engine,
                                                         intraday_data):
        """Real multi-day run must yield finite (never NaN/inf) Sharpe and
        profit_factor — the exact failure mode the single-day regression
        test guards, here on the full happy path."""
        result = engine.run(intraday_data)
        assert result.total_trades > 0
        assert np.isfinite(result.sharpe_ratio)
        assert not pd.isna(result.sharpe_ratio)
        pf = result.profit_factor
        assert pf >= 0 and not pd.isna(pf)
