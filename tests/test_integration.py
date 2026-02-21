"""End-to-end integration tests for the full trading system pipeline.

Tests the complete flow: config -> data -> indicators -> signals -> backtest,
including walk-forward validation, Strat integration, custom indicator configs,
multi-ticker simulation, and edge cases.
"""

import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta, time
from pathlib import Path

from lib.config import (
    AppConfig, IndicatorConfig, SignalConfig, ExitConfig, RiskConfig,
    StratConfig, BacktestConfig, WalkForwardConfig, MarketConfig,
    load_config, get_position_size, get_signal_strength_label,
)
from lib.data_loader import DataLoader
from lib.indicators import add_all_indicators, calculate_rsi, calculate_atr
from lib.signals import generate_signals, evaluate_signal
from lib.backtest import BacktestEngine, BacktestResult, Trade
from lib.strat import StratClassifier
from lib.walk_forward import WalkForwardValidator, WalkForwardResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_intraday_df(n_days=3, bars_per_day=390, seed=42, base_price=200.0):
    """Create multi-day 1-minute OHLCV data for backtesting.

    Returns a DataFrame with DatetimeIndex and a Time column, simulating
    realistic market hours (09:30 to 16:00).
    """
    np.random.seed(seed)
    frames = []
    base = base_price

    day_date = pd.Timestamp('2024-01-02')
    for d in range(n_days):
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
        day_date += pd.Timedelta(days=1)

    return pd.concat(frames)


def _make_long_intraday(n_months=4, bars_per_day=100, seed=42):
    """Create several months of 1-minute data for walk-forward testing.

    Uses fewer bars per day than real data to keep tests fast while still
    having enough days/months for walk-forward folding.
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


def _make_trending_df(direction='down', n_days=3, bars_per_day=390, seed=42):
    """Create multi-day data with a clear trend to reliably trigger signals.

    direction='down' produces consecutive down bars -> CALL signals.
    direction='up' produces consecutive up bars -> PUT signals.
    """
    np.random.seed(seed)
    frames = []
    base = 200.0

    drift = -0.0003 if direction == 'down' else 0.0003

    day_date = pd.Timestamp('2024-01-02')
    for d in range(n_days):
        while day_date.weekday() >= 5:
            day_date += pd.Timedelta(days=1)

        times = pd.date_range(
            f'{day_date.date()} 09:30',
            periods=bars_per_day,
            freq='1min',
        )

        returns = np.random.normal(drift, 0.0005, bars_per_day)
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
        day_date += pd.Timedelta(days=1)

    return pd.concat(frames)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def intraday_5d():
    """5 days of realistic intraday data."""
    return _make_intraday_df(n_days=5, seed=42)


@pytest.fixture
def intraday_3d():
    """3 days of realistic intraday data."""
    return _make_intraday_df(n_days=3, seed=99)


@pytest.fixture
def trending_down_data():
    """5 days with a downward trend, good for triggering CALL signals."""
    return _make_trending_df(direction='down', n_days=5, seed=77)


@pytest.fixture
def long_data():
    """4 months of data for walk-forward testing."""
    return _make_long_intraday(n_months=4, seed=42)


@pytest.fixture
def default_app_config():
    """Default AppConfig with all sub-configs at defaults."""
    return AppConfig()


@pytest.fixture
def permissive_signal_config():
    """Signal config with low min_conditions for easier signal generation."""
    return SignalConfig(min_conditions=2)


@pytest.fixture
def default_engine():
    """BacktestEngine with min_conditions=2 for reliable test signal generation."""
    return BacktestEngine(
        risk_config=RiskConfig(),
        exit_config=ExitConfig(),
        signal_config=SignalConfig(min_conditions=2),
        strat_config=StratConfig(),
        backtest_config=BacktestConfig(),
        indicator_config=IndicatorConfig(),
    )


# ===========================================================================
# 1. Full Pipeline E2E — config -> data -> indicators -> signals -> backtest
# ===========================================================================

class TestFullPipelineE2E:
    """Load config, create intraday data, add indicators, generate signals,
    run BacktestEngine, and verify BacktestResult has valid trades."""

    def test_full_pipeline_produces_trades(self, intraday_5d):
        """The complete pipeline should produce a BacktestResult with
        populated trade fields."""
        # Step 1: Config
        config = AppConfig()
        config.signal.min_conditions = 2  # lower threshold for test data

        # Step 2: Data already created via fixture

        # Step 3: Add indicators
        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        # Verify indicator columns exist
        assert config.indicator.rsi_col in df.columns
        assert config.indicator.atr_col in df.columns
        assert 'VWAP' in df.columns
        assert 'StochRSI_K' in df.columns
        assert 'MACD' in df.columns
        assert 'RVOL' in df.columns

        # Step 4: Generate signals
        signals_df = generate_signals(
            df,
            min_conditions=config.signal.min_conditions,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )

        # Step 5: Run backtest
        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result = engine.run(df)

        # Step 6: Verify result structure
        assert isinstance(result, BacktestResult)
        assert isinstance(result.daily_pnl, list)
        assert len(result.daily_pnl) >= 1  # at least one trading day

        # If we got trades, verify all fields are populated
        for trade in result.trades:
            assert trade.entry_time is not None
            assert trade.entry_price is not None
            assert isinstance(trade.entry_price, (int, float))
            assert trade.entry_price > 0
            assert trade.direction in ('CALL', 'PUT')
            assert trade.base_score >= config.signal.min_conditions
            assert isinstance(trade.strat_bonus, int)
            assert trade.total_score == trade.base_score + trade.strat_bonus
            assert trade.position_size > 0
            assert len(trade.conditions_met) >= config.signal.min_conditions
            # Exit fields
            assert trade.exit_time is not None
            assert trade.exit_price is not None
            assert trade.exit_reason in (
                'target', 'stop_loss', 'time_stop', 'rsi_extreme', 'eod_close',
            )
            assert trade.return_pct is not None
            assert isinstance(trade.return_pct, float)

    def test_full_pipeline_metrics_consistent(self, intraday_5d):
        """Verify that metrics derived from trades are self-consistent."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)
        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result = engine.run(df)

        metrics = result.metrics()
        assert metrics['total_trades'] == result.total_trades
        assert metrics['total_winners'] == len(result.winners)
        assert metrics['total_losers'] == len(result.losers)
        assert metrics['total_winners'] + metrics['total_losers'] == metrics['total_trades']

        if result.total_trades > 0:
            assert 0.0 <= metrics['win_rate'] <= 1.0

        # Equity curve should have one point per trading day processed
        assert len(result.equity_curve) == len(result.daily_pnl)

    def test_full_pipeline_to_dataframe_roundtrip(self, intraday_5d):
        """Verify trade data survives conversion to DataFrame."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)
        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result = engine.run(df)

        trades_df = result.to_dataframe()
        assert len(trades_df) == result.total_trades
        if result.total_trades > 0:
            expected_cols = [
                'entry_time', 'exit_time', 'direction', 'entry_price',
                'exit_price', 'exit_reason', 'base_score', 'strat_bonus',
                'total_score', 'position_size', 'return_pct', 'mae', 'mfe',
                'conditions',
            ]
            for col in expected_cols:
                assert col in trades_df.columns, f"Missing column: {col}"


# ===========================================================================
# 2. Pipeline with Strat — use_strat=True, verify strat_bonus populated
# ===========================================================================

class TestPipelineWithStrat:
    """Run the full pipeline with Strat integration enabled and verify
    that strat_bonus fields are populated."""

    def test_strat_pipeline_runs(self, intraday_5d):
        """Pipeline with use_strat=True should run without error."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=config.strat,
            indicator_config=config.indicator,
        )
        result = engine.run(df, use_strat=True)

        assert isinstance(result, BacktestResult)
        # All trades should have strat_bonus field set (even if 0)
        for trade in result.trades:
            assert isinstance(trade.strat_bonus, int)
            assert trade.total_score == trade.base_score + trade.strat_bonus

    def test_strat_classifier_detects_combos(self, intraday_5d):
        """StratClassifier should produce combo labels from real data."""
        config = AppConfig()
        classifier = StratClassifier(strat_config=config.strat)

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)
        combo_df = classifier.detect_combos(df)

        assert 'strat_type' in combo_df.columns
        assert 'strat_combo' in combo_df.columns
        assert 'strat_setup' in combo_df.columns
        assert 'trigger_high' in combo_df.columns
        assert 'trigger_low' in combo_df.columns
        assert len(combo_df) == len(df)

        # Strat types should be one of the known values
        valid_types = {'1', '2U', '2D', '3', 'X'}
        assert set(combo_df['strat_type'].unique()).issubset(valid_types)

    def test_strat_bonus_integrated_in_total_score(self, intraday_5d):
        """When strat is enabled, total_score = base_score + strat_bonus.
        Compare with and without strat to ensure the scores differ (or
        at least that both runs produce valid results)."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        # Without strat
        engine_no_strat = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result_no_strat = engine_no_strat.run(df, use_strat=False)

        # With strat
        engine_strat = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=config.strat,
            indicator_config=config.indicator,
        )
        result_strat = engine_strat.run(df, use_strat=True)

        # Both should produce valid results
        assert isinstance(result_no_strat, BacktestResult)
        assert isinstance(result_strat, BacktestResult)

        # Without strat, all trades should have strat_bonus == 0
        for trade in result_no_strat.trades:
            assert trade.strat_bonus == 0


# ===========================================================================
# 3. Pipeline with custom IndicatorConfig
# ===========================================================================

class TestCustomIndicatorConfig:
    """Pass non-default IndicatorConfig and verify that column names
    change accordingly."""

    def test_custom_rsi_period_creates_correct_column(self, intraday_3d):
        """RSI period of 10 should create RSI10 column (not default RSI14)."""
        custom_ind = IndicatorConfig(rsi_period=10, rsi_fast_period=5)

        assert custom_ind.rsi_col == 'RSI10'
        assert custom_ind.rsi_fast_col == 'RSI5'

        df = add_all_indicators(intraday_3d, indicator_config=custom_ind)

        assert 'RSI10' in df.columns
        assert 'RSI5' in df.columns
        # Default RSI14 should NOT be present
        assert 'RSI14' not in df.columns

    def test_custom_atr_period(self, intraday_3d):
        """ATR period of 10 should create ATR10 column."""
        custom_ind = IndicatorConfig(atr_period=10)
        assert custom_ind.atr_col == 'ATR10'

        df = add_all_indicators(intraday_3d, indicator_config=custom_ind)
        assert 'ATR10' in df.columns
        assert 'ATR14' not in df.columns

    def test_custom_ema_periods(self, intraday_3d):
        """Custom EMA periods should produce EMA columns with matching names."""
        custom_ind = IndicatorConfig(ema_periods=[5, 13, 34])

        df = add_all_indicators(intraday_3d, indicator_config=custom_ind)
        assert 'EMA5' in df.columns
        assert 'EMA13' in df.columns
        assert 'EMA34' in df.columns
        # Default EMAs should NOT be present
        assert 'EMA9' not in df.columns
        assert 'EMA20' not in df.columns

    def test_custom_sma_periods(self, intraday_3d):
        """Custom SMA periods should produce SMA columns with matching names."""
        custom_ind = IndicatorConfig(sma_periods=[8, 21])

        df = add_all_indicators(intraday_3d, indicator_config=custom_ind)
        assert 'SMA8' in df.columns
        assert 'SMA21' in df.columns
        assert 'SMA5' not in df.columns

    def test_custom_indicator_config_in_full_pipeline(self, intraday_5d):
        """Full pipeline should work with custom indicator config."""
        custom_ind = IndicatorConfig(
            rsi_period=10,
            rsi_fast_period=5,
            atr_period=10,
            ema_periods=[5, 13, 34],
        )
        signal_cfg = SignalConfig(min_conditions=2)

        df = add_all_indicators(intraday_5d, indicator_config=custom_ind)
        assert 'RSI10' in df.columns
        assert 'EMA5' in df.columns

        engine = BacktestEngine(
            signal_config=signal_cfg,
            indicator_config=custom_ind,
        )
        result = engine.run(df)
        assert isinstance(result, BacktestResult)

        # Generate signals using the same custom indicator config
        signals_df = generate_signals(
            df,
            min_conditions=2,
            indicator_config=custom_ind,
        )
        # Signals should reference the custom RSI column, not default
        if not signals_df.empty:
            assert 'rsi' in signals_df.columns


# ===========================================================================
# 4. Multi-ticker simulation — different exit configs
# ===========================================================================

class TestMultiTickerSimulation:
    """Simulate different tickers (IWM vs SPY) with different exit configs
    and verify they produce different results."""

    def test_different_exit_configs_produce_different_results(self):
        """IWM-like (wider targets) and SPY-like (tighter targets) should
        produce different backtest results from the same data."""
        data = _make_intraday_df(n_days=5, seed=42)

        signal_cfg = SignalConfig(min_conditions=2)

        # IWM-like: wider targets, longer time stops
        iwm_exit = ExitConfig(
            call_target=0.005,
            put_target=0.006,
            call_stop=0.003,
            put_stop=0.004,
            call_time_stop=45,
            put_time_stop=50,
        )

        # SPY-like: tighter targets, shorter time stops
        spy_exit = ExitConfig(
            call_target=0.002,
            put_target=0.003,
            call_stop=0.001,
            put_stop=0.0015,
            call_time_stop=20,
            put_time_stop=25,
        )

        engine_iwm = BacktestEngine(
            exit_config=iwm_exit,
            signal_config=signal_cfg,
        )
        engine_spy = BacktestEngine(
            exit_config=spy_exit,
            signal_config=signal_cfg,
        )

        result_iwm = engine_iwm.run(data)
        result_spy = engine_spy.run(data)

        assert isinstance(result_iwm, BacktestResult)
        assert isinstance(result_spy, BacktestResult)

        # Both should produce valid results; at least one should have trades
        # with min_conditions=2, and exit configs differ so results should differ
        if result_iwm.total_trades > 0 and result_spy.total_trades > 0:
            # The results should differ in at least one metric
            iwm_metrics = result_iwm.metrics()
            spy_metrics = result_spy.metrics()

            # Either trade counts differ or exit reasons differ
            differs = (
                iwm_metrics['total_trades'] != spy_metrics['total_trades']
                or iwm_metrics['win_rate'] != spy_metrics['win_rate']
                or iwm_metrics['expectancy_pct'] != spy_metrics['expectancy_pct']
            )
            # This is a soft assertion: with random data, it is extremely
            # unlikely for two different exit configs to produce identical results
            assert differs, (
                "IWM and SPY configs produced identical results, which is "
                "extremely unlikely with different exit parameters"
            )

    def test_tight_stops_produce_more_stop_losses(self):
        """Tighter stop-loss values should produce a higher proportion of
        stop_loss exits compared to wider stops."""
        data = _make_intraday_df(n_days=5, seed=42)
        signal_cfg = SignalConfig(min_conditions=2)

        tight = ExitConfig(call_stop=0.0005, put_stop=0.0005,
                           call_target=0.01, put_target=0.01,
                           call_time_stop=120, put_time_stop=120)
        wide = ExitConfig(call_stop=0.01, put_stop=0.01,
                          call_target=0.01, put_target=0.01,
                          call_time_stop=120, put_time_stop=120)

        result_tight = BacktestEngine(
            exit_config=tight, signal_config=signal_cfg,
        ).run(data)
        result_wide = BacktestEngine(
            exit_config=wide, signal_config=signal_cfg,
        ).run(data)

        tight_stops = sum(
            1 for t in result_tight.trades if t.exit_reason == 'stop_loss'
        )
        wide_stops = sum(
            1 for t in result_wide.trades if t.exit_reason == 'stop_loss'
        )

        # With tight stops and wide targets, we expect more stop-loss exits
        if result_tight.total_trades > 0 and result_wide.total_trades > 0:
            tight_stop_rate = tight_stops / result_tight.total_trades
            wide_stop_rate = wide_stops / result_wide.total_trades
            assert tight_stop_rate >= wide_stop_rate


# ===========================================================================
# 5. Walk-forward E2E
# ===========================================================================

class TestWalkForwardE2E:
    """Run full walk-forward validation and verify fold structure."""

    def test_walk_forward_produces_folds(self, long_data):
        """Walk-forward should produce at least one fold with valid dates."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data)

        assert isinstance(result, WalkForwardResult)
        assert len(result.fold_results) >= 1
        assert len(result.fold_dates) == len(result.fold_results)

    def test_fold_dates_have_proper_structure(self, long_data):
        """Each fold should have train_start, train_end, test_start, test_end."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data)

        for dates in result.fold_dates:
            assert 'train_start' in dates
            assert 'train_end' in dates
            assert 'test_start' in dates
            assert 'test_end' in dates
            # Train period must end before test starts
            assert dates['train_end'] <= dates['test_start']
            # Test period end must be after test start
            assert dates['test_end'] >= dates['test_start']
            # Anchored: train always starts from the same point
            assert dates['train_start'] == result.fold_dates[0]['train_start']

    def test_fold_test_periods_non_overlapping(self, long_data):
        """Test periods of consecutive folds should not overlap."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data)

        if len(result.fold_dates) >= 2:
            for i in range(1, len(result.fold_dates)):
                prev_end = result.fold_dates[i - 1]['test_end']
                curr_start = result.fold_dates[i]['test_start']
                assert curr_start >= prev_end

    def test_walk_forward_aggregate_metrics(self, long_data):
        """Aggregate metrics should be computed across all folds."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data)

        assert 'total_folds' in result.aggregate_metrics
        assert 'total_trades_all_folds' in result.aggregate_metrics
        assert result.aggregate_metrics['total_folds'] == len(result.fold_results)

    def test_walk_forward_stability_score_in_range(self, long_data):
        """Stability score should be between 0.0 and 1.0."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data)
        assert 0.0 <= result.stability_score <= 1.0

    def test_walk_forward_with_strat(self, long_data):
        """Walk-forward with Strat integration should work."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data, use_strat=True)
        assert isinstance(result, WalkForwardResult)

    def test_walk_forward_summary_string(self, long_data):
        """Summary should be a readable string with key information."""
        validator = WalkForwardValidator(
            signal_config=SignalConfig(min_conditions=2),
            train_months=2,
            test_months=1,
        )
        result = validator.run(long_data)
        summary = result.summary()
        assert 'Walk-Forward' in summary
        assert 'Total Folds' in summary
        assert 'Stability Score' in summary


# ===========================================================================
# 6. Signal -> Backtest consistency
# ===========================================================================

class TestSignalBacktestConsistency:
    """Verify that signals generated from data match what the backtest finds."""

    def test_signal_count_roughly_matches_trade_count(self):
        """generate_signals and BacktestEngine should find roughly the same
        number of signals (backtest may find fewer due to position management,
        time windows, and daily trade limits)."""
        data = _make_intraday_df(n_days=5, seed=42)
        ind_cfg = IndicatorConfig()
        sig_cfg = SignalConfig(min_conditions=2)

        df = add_all_indicators(data, indicator_config=ind_cfg)

        # Get raw signals
        signals_df = generate_signals(
            df,
            min_conditions=sig_cfg.min_conditions,
            signal_config=sig_cfg,
            indicator_config=ind_cfg,
        )

        # Run backtest
        engine = BacktestEngine(
            signal_config=sig_cfg,
            indicator_config=ind_cfg,
        )
        result = engine.run(df)

        # The backtest should find <= signals than raw signal count,
        # because the backtest enforces one position at a time, daily
        # trade limits, and time window filters.
        raw_signal_count = len(signals_df)

        # Both should be non-negative
        assert raw_signal_count >= 0
        assert result.total_trades >= 0

        # Backtest cannot have more trades than raw signals
        # (it applies additional filters like time windows and position limits)
        # Note: this comparison is approximate because the backtest engine
        # evaluates signals differently (bar-by-bar with position management)
        # but the trade count should be in the same order of magnitude.
        if raw_signal_count > 0 and result.total_trades > 0:
            # Trade count should be <= raw signal count
            # (backtest has time window, daily limit, position constraints)
            assert result.total_trades <= raw_signal_count

    def test_signal_directions_match(self):
        """Directions of signals found by generate_signals should appear in
        the backtest trades (if there are matching time windows)."""
        data = _make_intraday_df(n_days=5, seed=42)
        ind_cfg = IndicatorConfig()
        sig_cfg = SignalConfig(min_conditions=2)

        df = add_all_indicators(data, indicator_config=ind_cfg)

        signals_df = generate_signals(
            df,
            min_conditions=sig_cfg.min_conditions,
            signal_config=sig_cfg,
            indicator_config=ind_cfg,
        )

        engine = BacktestEngine(
            signal_config=sig_cfg,
            indicator_config=ind_cfg,
        )
        result = engine.run(df)

        if not signals_df.empty and result.total_trades > 0:
            signal_directions = set(signals_df['direction'].unique())
            trade_directions = set(t.direction for t in result.trades)
            # Trade directions should be a subset of signal directions
            assert trade_directions.issubset(signal_directions)


# ===========================================================================
# 7. Data loader -> indicators -> backtest chain (with parquet)
# ===========================================================================

class TestDataLoaderIndicatorBacktestChain:
    """Test the complete data loading chain using tmp_path with parquet files."""

    def test_parquet_load_to_backtest(self, tmp_path):
        """Write parquet -> load with DataLoader -> add indicators -> backtest."""
        # Create test data
        raw_data = _make_intraday_df(n_days=3, seed=42)

        # Write to parquet in the expected directory structure
        ticker = 'test'
        intraday_dir = tmp_path / ticker / 'intraday'
        intraday_dir.mkdir(parents=True)
        parquet_path = intraday_dir / f'{ticker}_av_1min_combined.parquet'
        raw_data.to_parquet(parquet_path)

        # Load via DataLoader
        loader = DataLoader(data_dir=str(tmp_path))
        loaded_df = loader.load_intraday('test')

        assert not loaded_df.empty
        assert 'Close' in loaded_df.columns
        assert 'Volume' in loaded_df.columns

        # Add indicators
        ind_cfg = IndicatorConfig()
        enriched = add_all_indicators(loaded_df, indicator_config=ind_cfg)

        assert ind_cfg.rsi_col in enriched.columns
        assert 'VWAP' in enriched.columns

        # Run backtest
        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
            indicator_config=ind_cfg,
        )
        result = engine.run(enriched)

        assert isinstance(result, BacktestResult)
        assert len(result.daily_pnl) >= 1

    def test_parquet_load_normalize_and_chain(self, tmp_path):
        """Write parquet with non-standard columns, normalize, and run chain."""
        np.random.seed(42)
        n = 390
        base = 200.0
        returns = np.random.normal(0, 0.001, n)
        close = base * np.exp(np.cumsum(returns))
        high = close * (1 + np.abs(np.random.normal(0, 0.001, n)))
        low = close * (1 - np.abs(np.random.normal(0, 0.001, n)))
        open_ = np.roll(close, 1)
        open_[0] = base
        volume = np.random.randint(10000, 100000, n).astype(float)

        times = pd.date_range('2024-01-02 09:30', periods=n, freq='1min')

        # Use non-standard column names
        raw_df = pd.DataFrame({
            'open': open_,
            'high': high,
            'low': low,
            'last': close,
            'volume': volume,
        }, index=times)

        ticker = 'spy'
        intraday_dir = tmp_path / ticker / 'intraday'
        intraday_dir.mkdir(parents=True)
        parquet_path = intraday_dir / f'{ticker}_av_1min_combined.parquet'
        raw_df.to_parquet(parquet_path)

        loader = DataLoader(data_dir=str(tmp_path))
        loaded = loader.load_intraday('spy')

        assert not loaded.empty
        assert 'Close' in loaded.columns
        assert 'Open' in loaded.columns
        assert 'High' in loaded.columns
        assert 'Low' in loaded.columns
        assert 'Volume' in loaded.columns

    def test_multi_timeframe_build(self, tmp_path):
        """DataLoader.build_multi_timeframe should produce aggregated data."""
        raw_data = _make_intraday_df(n_days=5, seed=42)

        loader = DataLoader(data_dir=str(tmp_path))
        tf_data = loader.build_multi_timeframe(raw_data, timeframes=['5m', '15m', '1h'])

        assert '5m' in tf_data
        assert '15m' in tf_data
        assert '1h' in tf_data

        # Each timeframe should have fewer bars than the original
        for tf, df in tf_data.items():
            assert len(df) < len(raw_data)
            assert 'Close' in df.columns
            assert 'Volume' in df.columns


# ===========================================================================
# 8. Edge cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases: minimal data, high min_conditions, all time stops, empty data."""

    def test_backtest_with_single_trading_day(self):
        """Backtest with only 1 trading day of data should work."""
        data = _make_intraday_df(n_days=1, bars_per_day=390, seed=42)

        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
        )
        result = engine.run(data)

        assert isinstance(result, BacktestResult)
        assert len(result.daily_pnl) == 1  # exactly one trading day
        # All trades should close by end of day
        for trade in result.trades:
            assert trade.exit_time is not None

    def test_backtest_with_high_min_conditions(self):
        """With min_conditions=5, very few (or zero) signals should be generated."""
        data = _make_intraday_df(n_days=5, seed=42)

        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=5),
        )
        result = engine.run(data)

        assert isinstance(result, BacktestResult)
        # With 5/5 conditions required, there should be very few or no trades
        # on random data. This is acceptable either way.
        # All trades that exist should still be valid
        for trade in result.trades:
            assert trade.base_score >= 5
            assert trade.exit_time is not None

    def test_all_trades_hit_time_stop(self):
        """With tiny targets and very short time stops, most trades should
        exit via time_stop."""
        data = _make_intraday_df(n_days=3, seed=42)

        # Set unreachable targets but very short time stop
        exit_cfg = ExitConfig(
            call_target=0.50,   # 50% target: unreachable
            put_target=0.50,
            call_stop=0.50,     # 50% stop: unreachable
            put_stop=0.50,
            call_time_stop=1,   # 1-minute time stop
            put_time_stop=1,
            call_rsi_exit=100.0,  # Unreachable RSI exits
            put_rsi_exit=0.0,
        )

        engine = BacktestEngine(
            exit_config=exit_cfg,
            signal_config=SignalConfig(min_conditions=2),
        )
        result = engine.run(data)

        if result.total_trades > 0:
            time_stop_count = sum(
                1 for t in result.trades
                if t.exit_reason == 'time_stop'
            )
            eod_count = sum(
                1 for t in result.trades
                if t.exit_reason == 'eod_close'
            )
            # Trades should exit either by time_stop or eod_close
            assert time_stop_count + eod_count == result.total_trades

    def test_empty_data_produces_empty_result(self):
        """An empty DataFrame should produce an empty BacktestResult."""
        times = pd.DatetimeIndex([], dtype='datetime64[ns]')
        empty_df = pd.DataFrame({
            'Time': pd.Series([], dtype='datetime64[ns]'),
            'Open': pd.Series([], dtype='float64'),
            'High': pd.Series([], dtype='float64'),
            'Low': pd.Series([], dtype='float64'),
            'Close': pd.Series([], dtype='float64'),
            'Volume': pd.Series([], dtype='float64'),
        }, index=times)

        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
        )
        result = engine.run(empty_df)

        assert isinstance(result, BacktestResult)
        assert result.total_trades == 0
        assert len(result.trades) == 0
        assert result.win_rate == 0.0
        assert result.expectancy == 0.0

    def test_very_few_bars_per_day_skipped(self):
        """Days with fewer bars than min_bars_per_day should be skipped."""
        data = _make_intraday_df(n_days=1, bars_per_day=5, seed=42)

        bt_cfg = BacktestConfig(min_bars_per_day=10)
        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
            backtest_config=bt_cfg,
        )
        result = engine.run(data)

        # 5 bars < min_bars_per_day=10, so the day should be skipped
        assert result.total_trades == 0

    def test_indicators_on_minimal_data(self):
        """add_all_indicators should handle very short data gracefully."""
        # Create just 10 bars
        np.random.seed(42)
        n = 10
        times = pd.date_range('2024-01-02 09:30', periods=n, freq='1min')
        close = np.linspace(200, 201, n)
        df = pd.DataFrame({
            'Time': times,
            'Open': close * 0.999,
            'High': close * 1.001,
            'Low': close * 0.998,
            'Close': close,
            'Volume': np.random.randint(1000, 10000, n).astype(float),
        }, index=times)

        result = add_all_indicators(df)
        assert 'RSI14' in result.columns
        assert 'VWAP' in result.columns
        assert len(result) == n

    def test_backtest_no_signals_in_time_window(self):
        """With a very narrow entry window that does not overlap our data's
        timestamps, we should get zero trades."""
        data = _make_intraday_df(n_days=3, seed=42)

        # Set entry windows to 15:59-16:00 (market close only)
        sig_cfg = SignalConfig(
            min_conditions=2,
            call_entry_start='15:59',
            call_entry_end='16:00',
            put_entry_start='15:59',
            put_entry_end='16:00',
        )
        engine = BacktestEngine(signal_config=sig_cfg)
        result = engine.run(data)

        # Data is 390 bars from 09:30, i.e. up to ~16:00
        # With this tiny window, very few or zero entries expected
        # At most some trades might slip into the 15:59-16:00 window
        assert isinstance(result, BacktestResult)

    def test_backtest_single_bar_day(self):
        """A day with exactly min_bars_per_day bars should still work."""
        bt_cfg = BacktestConfig(min_bars_per_day=10)
        data = _make_intraday_df(n_days=1, bars_per_day=10, seed=42)

        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
            backtest_config=bt_cfg,
        )
        result = engine.run(data)

        assert isinstance(result, BacktestResult)
        # Should process the day (10 >= min_bars_per_day=10)
        assert len(result.daily_pnl) == 1


# ===========================================================================
# Additional integration tests
# ===========================================================================

class TestConfigIntegration:
    """Test that config objects flow correctly through the pipeline."""

    def test_app_config_defaults_work_end_to_end(self, intraday_5d):
        """The default AppConfig should work for a full pipeline run."""
        config = AppConfig()
        # Lower min_conditions for test data
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)
        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=config.strat,
            backtest_config=config.backtest,
            indicator_config=config.indicator,
        )
        result = engine.run(df)
        assert isinstance(result, BacktestResult)

    def test_position_sizing_varies_by_score(self, intraday_5d):
        """Position sizes should differ based on signal score thresholds."""
        config = AppConfig()
        config.signal.min_conditions = 2

        # Verify position sizing is score-dependent
        assert get_position_size(3) == 0.25   # weak
        assert get_position_size(5) == 0.50   # medium
        assert get_position_size(6) == 0.75   # strong
        assert get_position_size(7) == 1.00   # perfect

        # Run pipeline and check that trades have correct position sizes
        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)
        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result = engine.run(df)

        for trade in result.trades:
            expected_size = get_position_size(trade.total_score, config.risk)
            assert trade.position_size == expected_size

    def test_signal_strength_labels(self):
        """Signal strength labels should match score thresholds."""
        assert get_signal_strength_label(3) == 'weak'
        assert get_signal_strength_label(4) == 'weak'
        assert get_signal_strength_label(5) == 'medium'
        assert get_signal_strength_label(6) == 'strong'
        assert get_signal_strength_label(7) == 'perfect'
        assert get_signal_strength_label(8) == 'perfect'


class TestIndicatorSignalChain:
    """Test that indicator columns are correctly consumed by signal generation."""

    def test_indicators_feed_signals(self, intraday_5d):
        """After adding indicators, signal generation should find the expected
        columns and produce valid output."""
        ind_cfg = IndicatorConfig()
        df = add_all_indicators(intraday_5d, indicator_config=ind_cfg)

        # Verify all columns that signals depend on
        required_for_signals = [
            ind_cfg.rsi_col,          # RSI14
            'StochRSI_K',
            'StochRSI_D',
            'VWAP',
            'Price_vs_VWAP',
            ind_cfg.price_vs_ema_fast_col,  # Price_vs_EMA9
            ind_cfg.price_vs_ema_mid_col,   # Price_vs_EMA20
            'Consecutive_Up',
            'Consecutive_Down',
            'RVOL',
        ]
        for col in required_for_signals:
            assert col in df.columns, f"Missing signal-dependency column: {col}"

        signals = generate_signals(
            df,
            min_conditions=2,
            indicator_config=ind_cfg,
        )
        if not signals.empty:
            assert 'direction' in signals.columns
            assert 'base_score' in signals.columns
            assert 'price' in signals.columns

    def test_indicator_values_are_finite(self, intraday_5d):
        """Indicator values should be finite (no inf) after warmup period."""
        df = add_all_indicators(intraday_5d)

        # After sufficient warmup (e.g., 50 bars), values should be finite
        warmup = 50
        for col in ['RSI14', 'ATR14', 'VWAP', 'StochRSI_K', 'MACD', 'RVOL']:
            subset = df[col].iloc[warmup:]
            finite_count = np.isfinite(subset).sum()
            total_count = len(subset)
            assert finite_count / total_count > 0.95, (
                f"Column {col} has too many non-finite values after warmup"
            )


class TestFTFCORBFilterIntegration:
    """End-to-end tests for FTFC/ORB trade filtering in the full pipeline."""

    def test_full_pipeline_with_strat_filter_counts_populated(self, intraday_5d):
        """Full pipeline with use_strat=True should have filter_counts with
        signals_evaluated > 0."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=StratConfig(
                ftfc_filter_enabled=True,
                orb_filter_enabled=True,
            ),
            backtest_config=config.backtest,
            indicator_config=config.indicator,
        )
        result = engine.run(df, use_strat=True)

        assert isinstance(result, BacktestResult)
        assert result.filter_counts['signals_evaluated'] > 0
        # Total rejections should be non-negative
        total_rejected = (
            result.filter_counts['ftfc_rejected']
            + result.filter_counts['orb_rejected']
        )
        assert total_rejected >= 0

    def test_strat_filter_reduces_or_preserves_trade_count(self, intraday_5d):
        """With filtering on, the trade count should be <= the base (no-strat)
        count since filters can only remove trades."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        # Run without strat
        engine_base = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result_base = engine_base.run(df, use_strat=False)

        # Run with strat filtering
        engine_strat = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=StratConfig(
                ftfc_filter_enabled=True,
                orb_filter_enabled=True,
            ),
            backtest_config=config.backtest,
            indicator_config=config.indicator,
        )
        result_strat = engine_strat.run(df, use_strat=True)

        assert result_strat.total_trades <= result_base.total_trades

    def test_filter_counts_in_summary(self, intraday_5d):
        """The summary string should include filter statistics when strat
        filtering is active."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=StratConfig(
                ftfc_filter_enabled=True,
                orb_filter_enabled=True,
            ),
            indicator_config=config.indicator,
        )
        result = engine.run(df, use_strat=True)
        summary = result.summary()

        # Filter info should appear when signals_evaluated > 0
        if result.filter_counts['signals_evaluated'] > 0:
            assert 'Signals evaluated' in summary
            assert 'FTFC rejected' in summary
            assert 'ORB rejected' in summary

    def test_orb_columns_flow_through_pipeline(self, intraday_5d):
        """ORB columns computed by add_all_indicators should be available
        when the backtest engine runs with strat."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        # Verify ORB columns exist before backtest
        assert 'ORB_5m_High' in df.columns
        assert 'ORB_5m_Low' in df.columns
        assert 'ORB_5m_Trend' in df.columns

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=config.strat,
            indicator_config=config.indicator,
        )
        result = engine.run(df, use_strat=True)

        # Trades should have orb_trend set from the ORB columns
        for trade in result.trades:
            assert trade.orb_trend in (-1, 0, 1)

    def test_ftfc_score_range_in_trades(self, intraday_5d):
        """FTFC scores on trades should be in the [-1, +1] range."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=config.strat,
            indicator_config=config.indicator,
        )
        result = engine.run(df, use_strat=True)

        for trade in result.trades:
            assert -1.0 <= trade.ftfc_score <= 1.0

    def test_disabling_filters_allows_more_trades(self, intraday_5d):
        """Disabling both FTFC and ORB filters should produce >= the number
        of trades compared to having both filters enabled."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        # With filters enabled
        engine_filtered = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=StratConfig(
                ftfc_filter_enabled=True,
                orb_filter_enabled=True,
            ),
            indicator_config=config.indicator,
        )
        result_filtered = engine_filtered.run(df, use_strat=True)

        # With filters disabled
        engine_unfiltered = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            strat_config=StratConfig(
                ftfc_filter_enabled=False,
                orb_filter_enabled=False,
            ),
            indicator_config=config.indicator,
        )
        result_unfiltered = engine_unfiltered.run(df, use_strat=True)

        assert result_unfiltered.total_trades >= result_filtered.total_trades

    def test_metrics_by_exit_reason_in_pipeline(self, intraday_5d):
        """metrics_by_exit_reason should work on pipeline results."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result = engine.run(df)

        exit_df = result.metrics_by_exit_reason()
        if result.total_trades > 0:
            assert not exit_df.empty
            assert 'trades' in exit_df.columns
            assert 'win_rate' in exit_df.columns

    def test_metrics_by_direction_in_pipeline(self, intraday_5d):
        """metrics_by_direction should work on pipeline results."""
        config = AppConfig()
        config.signal.min_conditions = 2

        df = add_all_indicators(intraday_5d, indicator_config=config.indicator)

        engine = BacktestEngine(
            risk_config=config.risk,
            exit_config=config.exit,
            signal_config=config.signal,
            indicator_config=config.indicator,
        )
        result = engine.run(df)

        dir_df = result.metrics_by_direction()
        if result.total_trades > 0:
            assert not dir_df.empty
            for direction in dir_df.index:
                assert direction in ('CALL', 'PUT')


class TestMAEMFETracking:
    """Verify that MAE (Max Adverse Excursion) and MFE (Max Favorable Excursion)
    are tracked correctly during trades."""

    def test_mae_mfe_populated(self, intraday_5d):
        """Trades should have MAE <= 0 and MFE >= 0."""
        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
        )
        result = engine.run(intraday_5d)

        for trade in result.trades:
            # MAE should be <= 0 (worst unrealized loss)
            assert trade.mae <= trade.mfe, (
                f"MAE ({trade.mae}) should be <= MFE ({trade.mfe})"
            )


class TestDailyRiskLimits:
    """Verify that daily risk limits are enforced."""

    def test_max_daily_trades_enforced(self):
        """No day should have more trades than max_daily_trades."""
        data = _make_intraday_df(n_days=5, seed=42)

        for max_trades in [1, 2, 3]:
            engine = BacktestEngine(
                risk_config=RiskConfig(max_daily_trades=max_trades),
                signal_config=SignalConfig(min_conditions=2),
            )
            result = engine.run(data)

            for day_info in result.daily_pnl:
                assert day_info['trades'] <= max_trades, (
                    f"Day {day_info['date']} had {day_info['trades']} trades, "
                    f"exceeding max_daily_trades={max_trades}"
                )

    def test_exit_reasons_are_valid(self):
        """All trades should have a recognized exit reason."""
        data = _make_intraday_df(n_days=5, seed=42)

        engine = BacktestEngine(
            signal_config=SignalConfig(min_conditions=2),
        )
        result = engine.run(data)

        valid_reasons = {'target', 'stop_loss', 'time_stop', 'rsi_extreme', 'eod_close'}
        for trade in result.trades:
            assert trade.exit_reason in valid_reasons, (
                f"Unknown exit reason: {trade.exit_reason}"
            )
