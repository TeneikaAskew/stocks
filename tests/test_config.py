"""Tests for lib/config.py — Configuration system, dataclass defaults, helpers, and JSON loading."""

import json
import pytest
from datetime import time

from lib.config import (
    IndicatorConfig,
    MarketConfig,
    MonitorConfig,
    BacktestConfig,
    WalkForwardConfig,
    RiskConfig,
    ExitConfig,
    StratConfig,
    SignalConfig,
    AppConfig,
    ConfigValidationError,
    get_position_size,
    get_signal_strength_label,
    load_config,
    _apply_ticker_overrides,
)


# =========================================================================
# 1. Dataclass defaults
# =========================================================================

class TestIndicatorConfigDefaults:
    """Verify every default on IndicatorConfig."""

    def test_rsi_defaults(self):
        cfg = IndicatorConfig()
        assert cfg.rsi_period == 14
        assert cfg.rsi_fast_period == 9

    def test_ema_periods_default(self):
        cfg = IndicatorConfig()
        assert cfg.ema_periods == [9, 20, 50]

    def test_sma_periods_default(self):
        cfg = IndicatorConfig()
        assert cfg.sma_periods == [5, 10, 20, 50, 200]

    def test_atr_period_default(self):
        cfg = IndicatorConfig()
        assert cfg.atr_period == 14

    def test_rvol_period_default(self):
        cfg = IndicatorConfig()
        assert cfg.rvol_period == 20

    def test_stoch_rsi_defaults(self):
        cfg = IndicatorConfig()
        assert cfg.stoch_rsi_period == 14
        assert cfg.stoch_rsi_k_period == 3
        assert cfg.stoch_rsi_d_period == 3

    def test_bollinger_defaults(self):
        cfg = IndicatorConfig()
        assert cfg.bb_period == 20
        assert cfg.bb_std_mult == 2.0

    def test_macd_defaults(self):
        cfg = IndicatorConfig()
        assert cfg.macd_fast == 12
        assert cfg.macd_slow == 26
        assert cfg.macd_signal == 9

    def test_consecutive_periods_default(self):
        cfg = IndicatorConfig()
        assert cfg.consecutive_periods == 3

    def test_orb_windows_default(self):
        cfg = IndicatorConfig()
        assert len(cfg.orb_windows) == 3
        assert cfg.orb_windows[0] == {'minutes': 5, 'label': '5m'}
        assert cfg.orb_windows[1] == {'minutes': 15, 'label': '15m'}
        assert cfg.orb_windows[2] == {'minutes': 30, 'label': '30m'}

    def test_order_block_defaults(self):
        cfg = IndicatorConfig()
        assert cfg.order_block_lookback == 20
        assert cfg.order_block_consol_window == 5
        assert cfg.order_block_consol_threshold == 3
        assert cfg.order_block_vol_ratio == 0.6
        assert cfg.order_block_ffill_limit == 30
        assert cfg.order_block_level_tolerance == 0.001

    def test_mutable_defaults_are_independent(self):
        """Two instances should not share list references."""
        a = IndicatorConfig()
        b = IndicatorConfig()
        a.ema_periods.append(999)
        assert 999 not in b.ema_periods


class TestMarketConfigDefaults:
    def test_tickers_default(self):
        cfg = MarketConfig()
        assert cfg.tickers == ['IWM', 'SPY', 'QQQ']

    def test_market_hours_defaults(self):
        cfg = MarketConfig()
        assert cfg.market_open == '09:30'
        assert cfg.market_close == '16:00'

    def test_directory_defaults(self):
        cfg = MarketConfig()
        assert cfg.data_dir == 'data'
        assert cfg.output_dir == 'data/backtest_results'
        assert cfg.trades_dir == 'data/trades'


class TestMonitorConfigDefaults:
    def test_all_defaults(self):
        cfg = MonitorConfig()
        assert cfg.poll_interval == 60
        assert cfg.rolling_window_bars == 200
        assert cfg.min_bars_for_indicators == 20
        assert cfg.min_bars_for_signals == 30
        assert cfg.pre_market_sleep == 30
        assert cfg.discord_timeout == 10


class TestBacktestConfigDefaults:
    def test_all_defaults(self):
        cfg = BacktestConfig()
        assert cfg.min_bars_per_day == 10
        assert cfg.starting_equity == 1.0
        assert cfg.annualization_factor == 252


class TestWalkForwardConfigDefaults:
    def test_all_defaults(self):
        cfg = WalkForwardConfig()
        assert cfg.min_test_bars == 50
        assert cfg.default_train_months == 6
        assert cfg.default_test_months == 1


class TestRiskConfigDefaults:
    def test_trade_limits(self):
        cfg = RiskConfig()
        assert cfg.max_daily_trades == 5
        assert cfg.max_concurrent_positions == 1

    def test_daily_limits(self):
        cfg = RiskConfig()
        assert cfg.daily_loss_limit == -0.02
        assert cfg.daily_profit_target == 0.03

    def test_position_sizing_default(self):
        cfg = RiskConfig()
        assert cfg.position_sizing == {
            'weak': 0.25,
            'medium': 0.50,
            'strong': 0.75,
            'perfect': 1.00,
        }

    def test_score_thresholds_default(self):
        cfg = RiskConfig()
        assert cfg.score_thresholds == (4, 5, 6)

    def test_max_score_default(self):
        cfg = RiskConfig()
        assert cfg.max_score == 8


class TestExitConfigDefaults:
    def test_targets(self):
        cfg = ExitConfig()
        assert cfg.call_target == 0.0030
        assert cfg.put_target == 0.0038

    def test_stops(self):
        cfg = ExitConfig()
        assert cfg.call_stop == 0.0015
        assert cfg.put_stop == 0.0020

    def test_time_stops(self):
        cfg = ExitConfig()
        assert cfg.call_time_stop == 30
        assert cfg.put_time_stop == 35

    def test_rsi_exits(self):
        cfg = ExitConfig()
        assert cfg.call_rsi_exit == 80.0
        assert cfg.put_rsi_exit == 20.0


class TestStratConfigDefaults:
    def test_enabled_default(self):
        cfg = StratConfig()
        assert cfg.enabled is True

    def test_bonus_defaults(self):
        cfg = StratConfig()
        assert cfg.combo_bonus == 1
        assert cfg.ftfc_bonus == 1
        assert cfg.orb_alignment_bonus == 1

    def test_threshold_defaults(self):
        cfg = StratConfig()
        assert cfg.ftfc_threshold == 0.6
        assert cfg.ftfc_direction_threshold == 0.3

    def test_ftfc_filter_enabled_default(self):
        cfg = StratConfig()
        assert cfg.ftfc_filter_enabled is True

    def test_orb_filter_enabled_default(self):
        cfg = StratConfig()
        assert cfg.orb_filter_enabled is True

    def test_filter_enabled_can_be_disabled(self):
        cfg = StratConfig(ftfc_filter_enabled=False, orb_filter_enabled=False)
        assert cfg.ftfc_filter_enabled is False
        assert cfg.orb_filter_enabled is False

    def test_timeframes_default(self):
        cfg = StratConfig()
        assert cfg.timeframes == ['5m', '15m', '1h', '4h', '12h', '1d', '1w']

    def test_ftfc_weights_default(self):
        cfg = StratConfig()
        assert cfg.ftfc_weights == {
            '5m':  0.05, '15m': 0.10, '1h': 0.15,
            '4h':  0.15, '12h': 0.15,
            '1d':  0.30, '1w':  0.10,
        }
        assert abs(sum(cfg.ftfc_weights.values()) - 1.0) < 1e-9


class TestSignalConfigDefaults:
    def test_condition_thresholds(self):
        cfg = SignalConfig()
        assert cfg.min_conditions == 3
        assert cfg.consecutive_periods == 3

    def test_rsi_ranges(self):
        cfg = SignalConfig()
        assert cfg.call_rsi_range == (25.0, 50.0)
        assert cfg.put_rsi_range == (50.0, 75.0)

    def test_entry_windows(self):
        cfg = SignalConfig()
        assert cfg.call_entry_start == '09:30'
        assert cfg.call_entry_end == '10:00'
        assert cfg.put_entry_start == '09:30'
        assert cfg.put_entry_end == '14:00'

    def test_indicator_thresholds(self):
        cfg = SignalConfig()
        assert cfg.rvol_minimum == 1.5
        assert cfg.ema_proximity_threshold == 0.1
        assert cfg.stoch_rsi_oversold == 30.0
        assert cfg.stoch_rsi_overbought == 70.0

    def test_premarket_thresholds(self):
        cfg = SignalConfig()
        assert cfg.premarket_signal_threshold == 3
        assert cfg.premarket_building_threshold == 2


class TestAppConfigDefaults:
    """AppConfig should compose all sub-configs with their defaults."""

    def test_all_sub_configs_present(self):
        app = AppConfig()
        assert isinstance(app.risk, RiskConfig)
        assert isinstance(app.exit, ExitConfig)
        assert isinstance(app.signal, SignalConfig)
        assert isinstance(app.strat, StratConfig)
        assert isinstance(app.indicator, IndicatorConfig)
        assert isinstance(app.market, MarketConfig)
        assert isinstance(app.monitor, MonitorConfig)
        assert isinstance(app.backtest, BacktestConfig)
        assert isinstance(app.walk_forward, WalkForwardConfig)

    def test_sub_configs_have_defaults(self):
        """Quick check that sub-configs are not empty shells."""
        app = AppConfig()
        assert app.risk.max_daily_trades == 5
        assert app.exit.call_target == 0.0030
        assert app.signal.min_conditions == 3
        assert app.indicator.rsi_period == 14
        assert app.market.market_open == '09:30'
        assert app.monitor.poll_interval == 60
        assert app.backtest.starting_equity == 1.0
        assert app.walk_forward.min_test_bars == 50
        assert app.strat.enabled is True


# =========================================================================
# 2. IndicatorConfig column-name properties
# =========================================================================

class TestIndicatorConfigProperties:
    def test_rsi_col(self):
        cfg = IndicatorConfig()
        assert cfg.rsi_col == 'RSI14'

    def test_rsi_col_custom_period(self):
        cfg = IndicatorConfig(rsi_period=21)
        assert cfg.rsi_col == 'RSI21'

    def test_rsi_fast_col(self):
        cfg = IndicatorConfig()
        assert cfg.rsi_fast_col == 'RSI9'

    def test_rsi_fast_col_custom(self):
        cfg = IndicatorConfig(rsi_fast_period=5)
        assert cfg.rsi_fast_col == 'RSI5'

    def test_atr_col(self):
        cfg = IndicatorConfig()
        assert cfg.atr_col == 'ATR14'

    def test_atr_col_custom(self):
        cfg = IndicatorConfig(atr_period=10)
        assert cfg.atr_col == 'ATR10'

    def test_ema_fast_period(self):
        cfg = IndicatorConfig()
        assert cfg.ema_fast_period == 9

    def test_ema_fast_period_custom(self):
        cfg = IndicatorConfig(ema_periods=[5, 12, 26])
        assert cfg.ema_fast_period == 5

    def test_ema_fast_period_empty_list(self):
        cfg = IndicatorConfig(ema_periods=[])
        assert cfg.ema_fast_period == 9  # fallback

    def test_ema_mid_period(self):
        cfg = IndicatorConfig()
        assert cfg.ema_mid_period == 20

    def test_ema_mid_period_custom(self):
        cfg = IndicatorConfig(ema_periods=[5, 12, 26])
        assert cfg.ema_mid_period == 12

    def test_ema_mid_period_single_element(self):
        cfg = IndicatorConfig(ema_periods=[10])
        assert cfg.ema_mid_period == 20  # fallback

    def test_price_vs_ema_fast_col(self):
        cfg = IndicatorConfig()
        assert cfg.price_vs_ema_fast_col == 'Price_vs_EMA9'

    def test_price_vs_ema_fast_col_custom(self):
        cfg = IndicatorConfig(ema_periods=[21, 50, 100])
        assert cfg.price_vs_ema_fast_col == 'Price_vs_EMA21'

    def test_price_vs_ema_mid_col(self):
        cfg = IndicatorConfig()
        assert cfg.price_vs_ema_mid_col == 'Price_vs_EMA20'

    def test_price_vs_ema_mid_col_custom(self):
        cfg = IndicatorConfig(ema_periods=[8, 34, 89])
        assert cfg.price_vs_ema_mid_col == 'Price_vs_EMA34'


# =========================================================================
# 3. MarketConfig time properties
# =========================================================================

class TestMarketConfigTimeProperties:
    def test_market_open_time_default(self):
        cfg = MarketConfig()
        assert cfg.market_open_time == time(9, 30)

    def test_market_close_time_default(self):
        cfg = MarketConfig()
        assert cfg.market_close_time == time(16, 0)

    def test_market_open_time_custom(self):
        cfg = MarketConfig(market_open='08:00')
        assert cfg.market_open_time == time(8, 0)

    def test_market_close_time_custom(self):
        cfg = MarketConfig(market_close='15:30')
        assert cfg.market_close_time == time(15, 30)

    def test_market_open_time_type(self):
        cfg = MarketConfig()
        assert isinstance(cfg.market_open_time, time)

    def test_market_close_time_type(self):
        cfg = MarketConfig()
        assert isinstance(cfg.market_close_time, time)


# =========================================================================
# 4. get_position_size()
# =========================================================================

class TestGetPositionSize:
    """Test score-to-position-size mapping with default and custom RiskConfig."""

    def test_weak_score_default(self):
        # Default thresholds: (4, 5, 6) — score <= 4 is weak
        assert get_position_size(1) == 0.25
        assert get_position_size(4) == 0.25

    def test_medium_score_default(self):
        assert get_position_size(5) == 0.50

    def test_strong_score_default(self):
        assert get_position_size(6) == 0.75

    def test_perfect_score_default(self):
        assert get_position_size(7) == 1.00
        assert get_position_size(8) == 1.00

    def test_zero_score(self):
        assert get_position_size(0) == 0.25

    def test_negative_score(self):
        # Negative score is below all thresholds -> weak
        assert get_position_size(-1) == 0.25

    def test_custom_risk_config(self):
        custom = RiskConfig(
            score_thresholds=(2, 4, 6),
            position_sizing={
                'weak': 0.10,
                'medium': 0.30,
                'strong': 0.60,
                'perfect': 1.00,
            },
        )
        assert get_position_size(1, custom) == 0.10   # <= 2 -> weak
        assert get_position_size(2, custom) == 0.10
        assert get_position_size(3, custom) == 0.30   # <= 4 -> medium
        assert get_position_size(4, custom) == 0.30
        assert get_position_size(5, custom) == 0.60   # <= 6 -> strong
        assert get_position_size(6, custom) == 0.60
        assert get_position_size(7, custom) == 1.00   # > 6 -> perfect

    def test_explicit_none_risk_config(self):
        """Passing None explicitly should use defaults."""
        assert get_position_size(5, None) == 0.50


# =========================================================================
# 5. get_signal_strength_label()
# =========================================================================

class TestGetSignalStrengthLabel:
    def test_weak_label_default(self):
        assert get_signal_strength_label(1) == 'weak'
        assert get_signal_strength_label(4) == 'weak'

    def test_medium_label_default(self):
        assert get_signal_strength_label(5) == 'medium'

    def test_strong_label_default(self):
        assert get_signal_strength_label(6) == 'strong'

    def test_perfect_label_default(self):
        assert get_signal_strength_label(7) == 'perfect'
        assert get_signal_strength_label(8) == 'perfect'

    def test_zero_score_label(self):
        assert get_signal_strength_label(0) == 'weak'

    def test_custom_risk_config(self):
        custom = RiskConfig(score_thresholds=(3, 5, 7))
        assert get_signal_strength_label(3, custom) == 'weak'
        assert get_signal_strength_label(4, custom) == 'medium'
        assert get_signal_strength_label(5, custom) == 'medium'
        assert get_signal_strength_label(6, custom) == 'strong'
        assert get_signal_strength_label(7, custom) == 'strong'
        assert get_signal_strength_label(8, custom) == 'perfect'

    def test_explicit_none_risk_config(self):
        assert get_signal_strength_label(5, None) == 'medium'


# =========================================================================
# 6. load_config() from file — default and with ticker overrides
# =========================================================================

def _write_config(tmp_path, data):
    """Helper: write a JSON config to a temp file and return its path string."""
    p = tmp_path / 'alert_config.json'
    p.write_text(json.dumps(data, indent=2))
    return str(p)


class TestLoadConfigFromFile:
    """Test load_config() reading from a JSON file."""

    def test_empty_json_returns_defaults(self, tmp_path):
        path = _write_config(tmp_path, {})
        app = load_config(path)
        assert app.risk.max_daily_trades == 5
        assert app.exit.call_target == 0.0030
        assert app.signal.min_conditions == 3

    def test_risk_parameters_loaded(self, tmp_path):
        data = {
            'risk_parameters': {
                'max_daily_trades': 10,
                'max_concurrent_positions': 3,
                'daily_loss_limit': -5,    # absolute > 1, so / 100 -> -0.05
                'daily_profit_target': 8,  # absolute > 1, so / 100 -> 0.08
                'max_score': 12,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.risk.max_daily_trades == 10
        assert app.risk.max_concurrent_positions == 3
        assert app.risk.daily_loss_limit == pytest.approx(-0.05)
        assert app.risk.daily_profit_target == pytest.approx(0.08)
        assert app.risk.max_score == 12

    def test_risk_daily_limits_already_fractional(self, tmp_path):
        """When values are already fractional (abs <= 1) they pass through."""
        data = {
            'risk_parameters': {
                'daily_loss_limit': -0.01,
                'daily_profit_target': 0.05,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.risk.daily_loss_limit == pytest.approx(-0.01)
        assert app.risk.daily_profit_target == pytest.approx(0.05)

    def test_risk_position_sizing_loaded(self, tmp_path):
        data = {
            'risk_parameters': {
                'position_sizing': {
                    'weak_signal': 0.10,
                    'medium_signal': 0.40,
                    'strong_signal': 0.80,
                    'perfect_signal': 1.00,
                }
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.risk.position_sizing['weak'] == 0.10
        assert app.risk.position_sizing['medium'] == 0.40
        assert app.risk.position_sizing['strong'] == 0.80
        assert app.risk.position_sizing['perfect'] == 1.00

    def test_risk_score_thresholds_loaded(self, tmp_path):
        data = {
            'risk_parameters': {
                'score_thresholds': [3, 5, 7],
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.risk.score_thresholds == (3, 5, 7)

    def test_exit_parameters_loaded(self, tmp_path):
        data = {
            'alerts': {
                'exit_alerts': {
                    'profit_target_hit': {
                        'call_target': '0.50%',
                        'put_target': '0.60%',
                        'call_stop': '0.25%',
                        'put_stop': '0.30%',
                    },
                    'time_stop': {
                        'call_minutes': 45,
                        'put_minutes': 50,
                    },
                    'extreme_rsi_exit': {
                        'call_rsi_exit': 85.0,
                        'put_rsi_exit': 15.0,
                    },
                }
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.exit.call_target == pytest.approx(0.005)
        assert app.exit.put_target == pytest.approx(0.006)
        assert app.exit.call_stop == pytest.approx(0.0025)
        assert app.exit.put_stop == pytest.approx(0.003)
        assert app.exit.call_time_stop == 45
        assert app.exit.put_time_stop == 50
        assert app.exit.call_rsi_exit == 85.0
        assert app.exit.put_rsi_exit == 15.0

    def test_exit_targets_numeric_strings(self, tmp_path):
        """Targets expressed as plain numbers (not 'x%' strings) also work."""
        data = {
            'alerts': {
                'exit_alerts': {
                    'profit_target_hit': {
                        'call_target': '0.40',
                        'put_target': 0.50,
                    }
                }
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.exit.call_target == pytest.approx(0.004)
        assert app.exit.put_target == pytest.approx(0.005)

    def test_signal_from_alerts_section(self, tmp_path):
        data = {
            'alerts': {
                'primary_call_alert': {
                    'conditions': {
                        'rsi_range': [20, 45],
                        'rvol_minimum': 2.0,
                    }
                },
                'primary_put_alert': {
                    'conditions': {
                        'rsi_range': [55, 80],
                    }
                },
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.signal.call_rsi_range == (20.0, 45.0)
        assert app.signal.put_rsi_range == (55.0, 80.0)
        assert app.signal.rvol_minimum == 2.0

    def test_signal_section_overrides(self, tmp_path):
        data = {
            'signal': {
                'min_conditions': 5,
                'consecutive_periods': 5,
                'call_rsi_range': [30, 55],
                'put_rsi_range': [45, 70],
                'ema_proximity_threshold': 0.2,
                'stoch_rsi_oversold': 25.0,
                'stoch_rsi_overbought': 75.0,
                'call_entry_start': '09:45',
                'call_entry_end': '10:30',
                'put_entry_start': '10:00',
                'put_entry_end': '15:00',
                'premarket_signal_threshold': 4,
                'premarket_building_threshold': 3,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.signal.min_conditions == 5
        assert app.signal.consecutive_periods == 5
        assert app.signal.call_rsi_range == (30, 55)
        assert app.signal.put_rsi_range == (45, 70)
        assert app.signal.ema_proximity_threshold == 0.2
        assert app.signal.stoch_rsi_oversold == 25.0
        assert app.signal.stoch_rsi_overbought == 75.0
        assert app.signal.call_entry_start == '09:45'
        assert app.signal.call_entry_end == '10:30'
        assert app.signal.put_entry_start == '10:00'
        assert app.signal.put_entry_end == '15:00'
        assert app.signal.premarket_signal_threshold == 4
        assert app.signal.premarket_building_threshold == 3

    def test_strat_section_loaded(self, tmp_path):
        data = {
            'strat': {
                'enabled': False,
                'combo_bonus': 2,
                'ftfc_bonus': 3,
                'orb_alignment_bonus': 2,
                'ftfc_threshold': 0.5,
                'ftfc_direction_threshold': 0.4,
                'timeframes': ['1m', '5m', '15m'],
                'ftfc_weights': {'1m': 0.30, '5m': 0.30, '15m': 0.40},
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.strat.enabled is False
        assert app.strat.combo_bonus == 2
        assert app.strat.ftfc_bonus == 3
        assert app.strat.orb_alignment_bonus == 2
        assert app.strat.ftfc_threshold == 0.5
        assert app.strat.ftfc_direction_threshold == 0.4
        assert app.strat.timeframes == ['1m', '5m', '15m']
        assert app.strat.ftfc_weights == {'1m': 0.30, '5m': 0.30, '15m': 0.40}

    def test_strat_filter_flags_loaded(self, tmp_path):
        """load_config should read ftfc_filter_enabled and orb_filter_enabled
        from the strat section in JSON."""
        data = {
            'strat': {
                'ftfc_filter_enabled': False,
                'orb_filter_enabled': False,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.strat.ftfc_filter_enabled is False
        assert app.strat.orb_filter_enabled is False

    def test_strat_filter_flags_default_when_absent(self, tmp_path):
        """When ftfc_filter_enabled / orb_filter_enabled are absent from JSON,
        they should default to True."""
        data = {
            'strat': {
                'enabled': True,
                'combo_bonus': 1,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.strat.ftfc_filter_enabled is True
        assert app.strat.orb_filter_enabled is True

    def test_indicator_section_loaded(self, tmp_path):
        data = {
            'indicators': {
                'rsi_period': 21,
                'rsi_fast_period': 7,
                'atr_period': 10,
                'rvol_period': 30,
                'stoch_rsi_period': 21,
                'stoch_rsi_k_period': 5,
                'stoch_rsi_d_period': 5,
                'bb_period': 30,
                'bb_std_mult': 2.5,
                'macd_fast': 8,
                'macd_slow': 21,
                'macd_signal': 5,
                'consecutive_periods': 5,
                'ema_periods': [8, 21, 55],
                'sma_periods': [10, 30, 100],
                'order_block_lookback': 30,
                'order_block_consol_window': 10,
                'order_block_consol_threshold': 5,
                'order_block_vol_ratio': 0.8,
                'order_block_ffill_limit': 50,
                'order_block_level_tolerance': 0.002,
                'orb_windows': [{'minutes': 10, 'label': '10m'}],
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.indicator.rsi_period == 21
        assert app.indicator.rsi_fast_period == 7
        assert app.indicator.atr_period == 10
        assert app.indicator.rvol_period == 30
        assert app.indicator.stoch_rsi_period == 21
        assert app.indicator.stoch_rsi_k_period == 5
        assert app.indicator.stoch_rsi_d_period == 5
        assert app.indicator.bb_period == 30
        assert app.indicator.bb_std_mult == 2.5
        assert app.indicator.macd_fast == 8
        assert app.indicator.macd_slow == 21
        assert app.indicator.macd_signal == 5
        assert app.indicator.consecutive_periods == 5
        assert app.indicator.ema_periods == [8, 21, 55]
        assert app.indicator.sma_periods == [10, 30, 100]
        assert app.indicator.order_block_lookback == 30
        assert app.indicator.order_block_consol_window == 10
        assert app.indicator.order_block_consol_threshold == 5
        assert app.indicator.order_block_vol_ratio == 0.8
        assert app.indicator.order_block_ffill_limit == 50
        assert app.indicator.order_block_level_tolerance == 0.002
        assert app.indicator.orb_windows == [{'minutes': 10, 'label': '10m'}]

    def test_market_section_loaded(self, tmp_path):
        data = {
            'market': {
                'tickers': ['AAPL', 'TSLA'],
                'market_open': '08:00',
                'market_close': '17:00',
                'data_dir': '/tmp/data',
                'output_dir': '/tmp/output',
                'trades_dir': '/tmp/trades',
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.market.tickers == ['AAPL', 'TSLA']
        assert app.market.market_open == '08:00'
        assert app.market.market_close == '17:00'
        assert app.market.data_dir == '/tmp/data'
        assert app.market.output_dir == '/tmp/output'
        assert app.market.trades_dir == '/tmp/trades'

    def test_monitor_section_loaded(self, tmp_path):
        data = {
            'monitor': {
                'poll_interval': 30,
                'rolling_window_bars': 300,
                'min_bars_for_indicators': 50,
                'min_bars_for_signals': 60,
                'pre_market_sleep': 15,
                'discord_timeout': 5,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.monitor.poll_interval == 30
        assert app.monitor.rolling_window_bars == 300
        assert app.monitor.min_bars_for_indicators == 50
        assert app.monitor.min_bars_for_signals == 60
        assert app.monitor.pre_market_sleep == 15
        assert app.monitor.discord_timeout == 5

    def test_backtest_section_loaded(self, tmp_path):
        data = {
            'backtest': {
                'min_bars_per_day': 20,
                'starting_equity': 10000.0,
                'annualization_factor': 365,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.backtest.min_bars_per_day == 20
        assert app.backtest.starting_equity == 10000.0
        assert app.backtest.annualization_factor == 365

    def test_walk_forward_section_loaded(self, tmp_path):
        data = {
            'walk_forward': {
                'min_test_bars': 100,
                'default_train_months': 12,
                'default_test_months': 3,
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.walk_forward.min_test_bars == 100
        assert app.walk_forward.default_train_months == 12
        assert app.walk_forward.default_test_months == 3

    def test_full_config_round_trip(self, tmp_path):
        """Comprehensive config with every section populated."""
        data = {
            'risk_parameters': {'max_daily_trades': 8},
            'alerts': {
                'exit_alerts': {
                    'profit_target_hit': {'call_target': '0.40%'},
                    'time_stop': {'call_minutes': 40},
                    'extreme_rsi_exit': {'call_rsi_exit': 82.0},
                },
                'primary_call_alert': {
                    'conditions': {'rsi_range': [30, 55]}
                },
            },
            'signal': {'min_conditions': 4},
            'strat': {'enabled': False},
            'indicators': {'rsi_period': 21},
            'market': {'tickers': ['GOOG']},
            'monitor': {'poll_interval': 120},
            'backtest': {'min_bars_per_day': 15},
            'walk_forward': {'min_test_bars': 75},
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.risk.max_daily_trades == 8
        assert app.exit.call_target == pytest.approx(0.004)
        assert app.exit.call_time_stop == 40
        assert app.exit.call_rsi_exit == 82.0
        assert app.signal.call_rsi_range == (30.0, 55.0)
        assert app.signal.min_conditions == 4
        assert app.strat.enabled is False
        assert app.indicator.rsi_period == 21
        assert app.market.tickers == ['GOOG']
        assert app.monitor.poll_interval == 120
        assert app.backtest.min_bars_per_day == 15
        assert app.walk_forward.min_test_bars == 75

    def test_load_config_with_ticker_override(self, tmp_path):
        data = {
            'risk_parameters': {'max_daily_trades': 5},
            'ticker_overrides': {
                'SPY': {
                    'exit': {
                        'call_target': 0.005,
                        'put_stop': 0.003,
                    },
                    'signal': {
                        'min_conditions': 4,
                    },
                }
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path, ticker='SPY')
        assert app.exit.call_target == 0.005
        assert app.exit.put_stop == 0.003
        assert app.signal.min_conditions == 4
        # Non-overridden values remain default
        assert app.exit.put_target == 0.0038
        assert app.risk.max_daily_trades == 5

    def test_load_config_ticker_case_insensitive(self, tmp_path):
        """Ticker should be uppercased before lookup."""
        data = {
            'ticker_overrides': {
                'QQQ': {
                    'exit': {'call_target': 0.007}
                }
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path, ticker='qqq')
        assert app.exit.call_target == 0.007

    def test_load_config_ticker_not_in_overrides(self, tmp_path):
        """When ticker has no overrides, base config is returned unchanged."""
        data = {
            'risk_parameters': {'max_daily_trades': 10},
            'ticker_overrides': {
                'SPY': {'exit': {'call_target': 0.009}},
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path, ticker='IWM')
        assert app.risk.max_daily_trades == 10
        assert app.exit.call_target == 0.0030  # default, not SPY override


# =========================================================================
# 7. load_config() with missing file
# =========================================================================

class TestLoadConfigMissingFile:
    def test_missing_file_returns_defaults(self):
        app = load_config('/nonexistent/path/alert_config.json')
        assert isinstance(app, AppConfig)
        assert app.risk.max_daily_trades == 5
        assert app.exit.call_target == 0.0030
        assert app.signal.min_conditions == 3
        assert app.indicator.rsi_period == 14

    def test_missing_file_all_sub_configs_are_defaults(self):
        app = load_config('/nonexistent/path/config.json')
        default = AppConfig()
        assert app.risk.max_daily_trades == default.risk.max_daily_trades
        assert app.exit.call_target == default.exit.call_target
        assert app.signal.min_conditions == default.signal.min_conditions
        assert app.indicator.rsi_period == default.indicator.rsi_period
        assert app.market.tickers == default.market.tickers
        assert app.monitor.poll_interval == default.monitor.poll_interval
        assert app.backtest.starting_equity == default.backtest.starting_equity
        assert app.walk_forward.min_test_bars == default.walk_forward.min_test_bars
        assert app.strat.enabled == default.strat.enabled


# =========================================================================
# 8. load_config() with ticker=None vs ticker='SPY'
# =========================================================================

class TestLoadConfigTickerNoneVsTicker:
    def test_ticker_none_skips_overrides(self, tmp_path):
        data = {
            'ticker_overrides': {
                'SPY': {'exit': {'call_target': 0.009}}
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path, ticker=None)
        assert app.exit.call_target == 0.0030  # default, no override applied

    def test_ticker_spy_applies_overrides(self, tmp_path):
        data = {
            'ticker_overrides': {
                'SPY': {'exit': {'call_target': 0.009}}
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path, ticker='SPY')
        assert app.exit.call_target == 0.009

    def test_default_ticker_parameter(self, tmp_path):
        """When ticker is not passed at all, no overrides are applied."""
        data = {
            'ticker_overrides': {
                'SPY': {'exit': {'call_target': 0.009}}
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.exit.call_target == 0.0030


# =========================================================================
# 9. _apply_ticker_overrides() direct testing
# =========================================================================

class TestApplyTickerOverrides:
    """Test _apply_ticker_overrides() with targeted override dicts."""

    def test_exit_overrides(self):
        app = AppConfig()
        overrides = {
            'exit': {
                'call_target': 0.006,
                'put_target': 0.007,
                'call_stop': 0.002,
                'put_stop': 0.003,
                'call_time_stop': 45,
                'put_time_stop': 55,
                'call_rsi_exit': 85.0,
                'put_rsi_exit': 15.0,
            }
        }
        _apply_ticker_overrides(app, overrides)
        assert app.exit.call_target == 0.006
        assert app.exit.put_target == 0.007
        assert app.exit.call_stop == 0.002
        assert app.exit.put_stop == 0.003
        assert app.exit.call_time_stop == 45
        assert app.exit.put_time_stop == 55
        assert app.exit.call_rsi_exit == 85.0
        assert app.exit.put_rsi_exit == 15.0

    def test_signal_overrides(self):
        app = AppConfig()
        overrides = {
            'signal': {
                'min_conditions': 4,
                'consecutive_periods': 5,
                'ema_proximity_threshold': 0.2,
                'stoch_rsi_oversold': 25.0,
                'stoch_rsi_overbought': 75.0,
                'rvol_minimum': 2.0,
                'call_entry_start': '09:45',
                'call_entry_end': '11:00',
                'put_entry_start': '10:00',
                'put_entry_end': '15:00',
                'call_rsi_range': [20, 45],
                'put_rsi_range': [55, 80],
            }
        }
        _apply_ticker_overrides(app, overrides)
        assert app.signal.min_conditions == 4
        assert app.signal.consecutive_periods == 5
        assert app.signal.ema_proximity_threshold == 0.2
        assert app.signal.stoch_rsi_oversold == 25.0
        assert app.signal.stoch_rsi_overbought == 75.0
        assert app.signal.rvol_minimum == 2.0
        assert app.signal.call_entry_start == '09:45'
        assert app.signal.call_entry_end == '11:00'
        assert app.signal.put_entry_start == '10:00'
        assert app.signal.put_entry_end == '15:00'
        assert app.signal.call_rsi_range == (20, 45)
        assert app.signal.put_rsi_range == (55, 80)

    def test_indicator_overrides(self):
        app = AppConfig()
        overrides = {
            'indicators': {
                'rsi_period': 21,
                'atr_period': 10,
                'rvol_period': 30,
                'consecutive_periods': 5,
                'ema_periods': [5, 13, 34],
            }
        }
        _apply_ticker_overrides(app, overrides)
        assert app.indicator.rsi_period == 21
        assert app.indicator.atr_period == 10
        assert app.indicator.rvol_period == 30
        assert app.indicator.consecutive_periods == 5
        assert app.indicator.ema_periods == [5, 13, 34]

    def test_risk_overrides(self):
        app = AppConfig()
        overrides = {
            'risk': {
                'max_daily_trades': 10,
                'max_concurrent_positions': 3,
                'max_score': 12,
            }
        }
        _apply_ticker_overrides(app, overrides)
        assert app.risk.max_daily_trades == 10
        assert app.risk.max_concurrent_positions == 3
        assert app.risk.max_score == 12

    def test_strat_overrides(self):
        app = AppConfig()
        overrides = {
            'strat': {
                'enabled': False,
                'combo_bonus': 2,
                'ftfc_bonus': 3,
                'orb_alignment_bonus': 2,
                'ftfc_threshold': 0.8,
                'ftfc_direction_threshold': 0.5,
            }
        }
        _apply_ticker_overrides(app, overrides)
        assert app.strat.enabled is False
        assert app.strat.combo_bonus == 2
        assert app.strat.ftfc_bonus == 3
        assert app.strat.orb_alignment_bonus == 2
        assert app.strat.ftfc_threshold == 0.8
        assert app.strat.ftfc_direction_threshold == 0.5

    def test_optimal_timeframe_override(self):
        app = AppConfig()
        overrides = {
            'optimal_timeframe': '15m',
        }
        _apply_ticker_overrides(app, overrides)
        assert app.optimal_timeframe == '15m'

    def test_multiple_sections_combined(self):
        app = AppConfig()
        overrides = {
            'exit': {'call_target': 0.010},
            'signal': {'min_conditions': 6},
            'indicators': {'rsi_period': 28},
            'risk': {'max_daily_trades': 20},
            'strat': {'enabled': False},
        }
        _apply_ticker_overrides(app, overrides)
        assert app.exit.call_target == 0.010
        assert app.signal.min_conditions == 6
        assert app.indicator.rsi_period == 28
        assert app.risk.max_daily_trades == 20
        assert app.strat.enabled is False

    def test_non_overridden_fields_preserved(self):
        """Fields not mentioned in overrides should remain at their defaults."""
        app = AppConfig()
        overrides = {
            'exit': {'call_target': 0.010},
        }
        _apply_ticker_overrides(app, overrides)
        assert app.exit.call_target == 0.010
        # All other exit fields remain at defaults
        assert app.exit.put_target == 0.0038
        assert app.exit.call_stop == 0.0015
        assert app.exit.put_stop == 0.0020
        assert app.exit.call_time_stop == 30
        assert app.exit.put_time_stop == 35
        assert app.exit.call_rsi_exit == 80.0
        assert app.exit.put_rsi_exit == 20.0


# =========================================================================
# 10. Edge cases
# =========================================================================

class TestEdgeCases:
    def test_custom_score_thresholds_affect_helpers(self):
        """Custom thresholds should be respected by helper functions."""
        cfg = RiskConfig(score_thresholds=(2, 3, 4))
        assert get_position_size(2, cfg) == 0.25    # weak
        assert get_position_size(3, cfg) == 0.50    # medium
        assert get_position_size(4, cfg) == 0.75    # strong
        assert get_position_size(5, cfg) == 1.00    # perfect

        assert get_signal_strength_label(2, cfg) == 'weak'
        assert get_signal_strength_label(3, cfg) == 'medium'
        assert get_signal_strength_label(4, cfg) == 'strong'
        assert get_signal_strength_label(5, cfg) == 'perfect'

    def test_empty_overrides_dict(self):
        """Empty overrides should leave everything at defaults."""
        app = AppConfig()
        _apply_ticker_overrides(app, {})
        default = AppConfig()
        assert app.exit.call_target == default.exit.call_target
        assert app.signal.min_conditions == default.signal.min_conditions
        assert app.indicator.rsi_period == default.indicator.rsi_period
        assert app.risk.max_daily_trades == default.risk.max_daily_trades
        assert app.strat.enabled == default.strat.enabled

    def test_partial_exit_overrides(self):
        """Only some exit fields overridden, rest should stay default."""
        app = AppConfig()
        _apply_ticker_overrides(app, {'exit': {'call_target': 0.010}})
        assert app.exit.call_target == 0.010
        assert app.exit.put_target == 0.0038
        assert app.exit.call_stop == 0.0015

    def test_partial_signal_overrides(self):
        app = AppConfig()
        _apply_ticker_overrides(app, {'signal': {'min_conditions': 7}})
        assert app.signal.min_conditions == 7
        assert app.signal.consecutive_periods == 3  # default
        assert app.signal.rvol_minimum == 1.5        # default

    def test_partial_indicator_overrides(self):
        app = AppConfig()
        _apply_ticker_overrides(app, {'indicators': {'rsi_period': 30}})
        assert app.indicator.rsi_period == 30
        assert app.indicator.atr_period == 14  # default

    def test_partial_risk_overrides(self):
        app = AppConfig()
        _apply_ticker_overrides(app, {'risk': {'max_daily_trades': 15}})
        assert app.risk.max_daily_trades == 15
        assert app.risk.max_concurrent_positions == 1  # default

    def test_partial_strat_overrides(self):
        app = AppConfig()
        _apply_ticker_overrides(app, {'strat': {'combo_bonus': 5}})
        assert app.strat.combo_bonus == 5
        assert app.strat.enabled is True  # default
        assert app.strat.ftfc_bonus == 1  # default

    def test_load_config_only_unrecognized_keys(self, tmp_path):
        """JSON with keys not matching any section is silently ignored."""
        data = {'foo': 'bar', 'baz': 123}
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.risk.max_daily_trades == 5  # all defaults

    def test_ticker_overrides_empty_sections(self, tmp_path):
        """Ticker overrides with empty sub-dicts should not break anything."""
        data = {
            'ticker_overrides': {
                'SPY': {
                    'exit': {},
                    'signal': {},
                    'indicators': {},
                    'risk': {},
                    'strat': {},
                }
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path, ticker='SPY')
        default = AppConfig()
        assert app.exit.call_target == default.exit.call_target
        assert app.signal.min_conditions == default.signal.min_conditions

    def test_score_at_exact_boundaries(self):
        """Test scores that land exactly on threshold values."""
        cfg = RiskConfig(score_thresholds=(4, 5, 6))
        # At boundary
        assert get_signal_strength_label(4, cfg) == 'weak'
        assert get_signal_strength_label(5, cfg) == 'medium'
        assert get_signal_strength_label(6, cfg) == 'strong'
        # Just above boundary
        assert get_signal_strength_label(7, cfg) == 'perfect'

    def test_indicator_column_names_after_override(self, tmp_path):
        """After loading config with overridden periods, column names update."""
        data = {
            'indicators': {
                'rsi_period': 21,
                'atr_period': 10,
                'ema_periods': [5, 13, 34],
            }
        }
        path = _write_config(tmp_path, data)
        app = load_config(path)
        assert app.indicator.rsi_col == 'RSI21'
        assert app.indicator.atr_col == 'ATR10'
        assert app.indicator.ema_fast_period == 5
        assert app.indicator.ema_mid_period == 13
        assert app.indicator.price_vs_ema_fast_col == 'Price_vs_EMA5'
        assert app.indicator.price_vs_ema_mid_col == 'Price_vs_EMA13'

    def test_multiple_tickers_only_requested_applied(self, tmp_path):
        """With multiple ticker overrides, only the requested one is applied."""
        data = {
            'ticker_overrides': {
                'SPY': {'exit': {'call_target': 0.010}},
                'QQQ': {'exit': {'call_target': 0.020}},
                'IWM': {'exit': {'call_target': 0.030}},
            }
        }
        path = _write_config(tmp_path, data)

        app_spy = load_config(path, ticker='SPY')
        assert app_spy.exit.call_target == 0.010

        app_qqq = load_config(path, ticker='QQQ')
        assert app_qqq.exit.call_target == 0.020

        app_iwm = load_config(path, ticker='IWM')
        assert app_iwm.exit.call_target == 0.030

    def test_very_high_score(self):
        """Very high scores should map to 'perfect'."""
        assert get_position_size(100) == 1.00
        assert get_signal_strength_label(100) == 'perfect'

    def test_position_sizing_custom_values(self):
        """Custom position sizing values are respected by get_position_size."""
        cfg = RiskConfig(
            position_sizing={
                'weak': 0.05,
                'medium': 0.15,
                'strong': 0.50,
                'perfect': 0.90,
            }
        )
        assert get_position_size(1, cfg) == 0.05
        assert get_position_size(5, cfg) == 0.15
        assert get_position_size(6, cfg) == 0.50
        assert get_position_size(7, cfg) == 0.90


# =========================================================================
# 11. Config validation (AppConfig.validate)
# =========================================================================

class TestConfigValidation:
    """Test that AppConfig.validate() catches invalid values."""

    def test_default_config_passes_validation(self):
        app = AppConfig()
        app.validate()  # should not raise

    def test_invalid_max_daily_trades_zero(self):
        app = AppConfig()
        app.risk.max_daily_trades = 0
        with pytest.raises(ConfigValidationError, match="max_daily_trades"):
            app.validate()

    def test_invalid_max_daily_trades_too_high(self):
        app = AppConfig()
        app.risk.max_daily_trades = 100
        with pytest.raises(ConfigValidationError, match="max_daily_trades"):
            app.validate()

    def test_invalid_daily_loss_limit_positive(self):
        app = AppConfig()
        app.risk.daily_loss_limit = 0.05
        with pytest.raises(ConfigValidationError, match="daily_loss_limit"):
            app.validate()

    def test_invalid_daily_loss_limit_below_minus_one(self):
        app = AppConfig()
        app.risk.daily_loss_limit = -1.5
        with pytest.raises(ConfigValidationError, match="daily_loss_limit"):
            app.validate()

    def test_invalid_daily_profit_target_negative(self):
        app = AppConfig()
        app.risk.daily_profit_target = -0.01
        with pytest.raises(ConfigValidationError, match="daily_profit_target"):
            app.validate()

    def test_invalid_score_thresholds_not_increasing(self):
        app = AppConfig()
        app.risk.score_thresholds = (6, 5, 4)
        with pytest.raises(ConfigValidationError, match="score_thresholds"):
            app.validate()

    def test_invalid_exit_target_zero(self):
        app = AppConfig()
        app.exit.call_target = 0.0
        with pytest.raises(ConfigValidationError, match="exit.call_target"):
            app.validate()

    def test_invalid_exit_target_too_large(self):
        app = AppConfig()
        app.exit.put_target = 0.20
        with pytest.raises(ConfigValidationError, match="exit.put_target"):
            app.validate()

    def test_invalid_exit_stop_zero(self):
        app = AppConfig()
        app.exit.call_stop = 0.0
        with pytest.raises(ConfigValidationError, match="exit.call_stop"):
            app.validate()

    def test_invalid_time_stop_zero(self):
        app = AppConfig()
        app.exit.call_time_stop = 0
        with pytest.raises(ConfigValidationError, match="exit.call_time_stop"):
            app.validate()

    def test_invalid_time_stop_too_large(self):
        app = AppConfig()
        app.exit.put_time_stop = 600
        with pytest.raises(ConfigValidationError, match="exit.put_time_stop"):
            app.validate()

    def test_invalid_min_conditions_zero(self):
        app = AppConfig()
        app.signal.min_conditions = 0
        with pytest.raises(ConfigValidationError, match="min_conditions"):
            app.validate()

    def test_invalid_min_conditions_too_high(self):
        app = AppConfig()
        app.signal.min_conditions = 10
        with pytest.raises(ConfigValidationError, match="min_conditions"):
            app.validate()

    def test_invalid_call_rsi_range_not_increasing(self):
        app = AppConfig()
        app.signal.call_rsi_range = (60.0, 40.0)
        with pytest.raises(ConfigValidationError, match="call_rsi_range"):
            app.validate()

    def test_invalid_put_rsi_range_out_of_bounds(self):
        app = AppConfig()
        app.signal.put_rsi_range = (50.0, 110.0)
        with pytest.raises(ConfigValidationError, match="put_rsi_range"):
            app.validate()

    def test_invalid_rsi_period_too_small(self):
        app = AppConfig()
        app.indicator.rsi_period = 1
        with pytest.raises(ConfigValidationError, match="rsi_period"):
            app.validate()

    def test_invalid_rsi_period_too_large(self):
        app = AppConfig()
        app.indicator.rsi_period = 200
        with pytest.raises(ConfigValidationError, match="rsi_period"):
            app.validate()

    def test_invalid_macd_fast_not_less_than_slow(self):
        app = AppConfig()
        app.indicator.macd_fast = 30
        app.indicator.macd_slow = 20
        with pytest.raises(ConfigValidationError, match="macd_fast"):
            app.validate()

    def test_invalid_ftfc_threshold_above_one(self):
        app = AppConfig()
        app.strat.ftfc_threshold = 1.5
        with pytest.raises(ConfigValidationError, match="ftfc_threshold"):
            app.validate()

    def test_invalid_ftfc_threshold_negative(self):
        app = AppConfig()
        app.strat.ftfc_threshold = -0.1
        with pytest.raises(ConfigValidationError, match="ftfc_threshold"):
            app.validate()

    def test_multiple_errors_reported(self):
        """When multiple fields are invalid, all are reported."""
        app = AppConfig()
        app.risk.max_daily_trades = 0
        app.exit.call_target = 0.0
        app.signal.min_conditions = 0
        with pytest.raises(ConfigValidationError, match="3 error"):
            app.validate()

    def test_boundary_values_pass(self):
        """Values at exact boundaries should pass."""
        app = AppConfig()
        app.risk.max_daily_trades = 1
        app.risk.daily_loss_limit = -1.0
        app.risk.daily_profit_target = 0.0
        app.exit.call_target = 0.10
        app.exit.call_stop = 0.10
        app.exit.call_time_stop = 480
        app.signal.min_conditions = 8
        app.indicator.rsi_period = 2
        app.strat.ftfc_threshold = 0.0
        app.validate()  # should not raise

    def test_load_config_rejects_invalid_json(self, tmp_path):
        """load_config should raise ConfigValidationError for bad values."""
        data = {
            'risk_parameters': {'max_daily_trades': 0},
        }
        path = _write_config(tmp_path, data)
        with pytest.raises(ConfigValidationError, match="max_daily_trades"):
            load_config(path)
