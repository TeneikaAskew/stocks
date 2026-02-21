"""
Typed configuration loaded from alert_config.json.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple


@dataclass
class RiskConfig:
    max_daily_trades: int = 5
    max_concurrent_positions: int = 1
    daily_loss_limit: float = -0.02  # -2%
    daily_profit_target: float = 0.03  # +3%
    position_sizing: Dict[str, float] = field(default_factory=lambda: {
        'weak': 0.25,
        'medium': 0.50,
        'strong': 0.75,
        'perfect': 1.00,
    })


@dataclass
class ExitConfig:
    call_target: float = 0.0030  # +0.30%
    put_target: float = 0.0038  # +0.38%
    call_stop: float = 0.0015  # -0.15%
    put_stop: float = 0.0020  # -0.20%
    call_time_stop: int = 30  # minutes
    put_time_stop: int = 35  # minutes
    call_rsi_exit: float = 80.0
    put_rsi_exit: float = 20.0


@dataclass
class StratConfig:
    enabled: bool = True
    combo_bonus: int = 1
    ftfc_bonus: int = 1
    orb_alignment_bonus: int = 1
    ftfc_threshold: float = 0.6
    timeframes: list = field(default_factory=lambda: ['5m', '15m', '1h', 'D', 'W'])
    # FTFC weights per timeframe
    ftfc_weights: Dict[str, float] = field(default_factory=lambda: {
        '5m': 0.10, '15m': 0.20, '1h': 0.25, 'D': 0.35, 'W': 0.10,
    })


@dataclass
class SignalConfig:
    min_conditions: int = 3
    consecutive_periods: int = 3
    call_rsi_range: Tuple[float, float] = (25.0, 50.0)
    put_rsi_range: Tuple[float, float] = (50.0, 75.0)
    call_entry_start: str = '09:30'
    call_entry_end: str = '10:00'
    put_entry_start: str = '09:30'
    put_entry_end: str = '14:00'
    rvol_minimum: float = 1.5


def get_position_size(score: int, max_score: int = 8) -> float:
    """Map combined signal score to position size fraction.

    Scoring scale (with Strat integration):
      3-4 / 8 → weak  (25%)
      5   / 8 → medium (50%)
      6   / 8 → strong (75%)
      7-8 / 8 → perfect (100%)
    """
    if score <= 4:
        return 0.25
    elif score == 5:
        return 0.50
    elif score == 6:
        return 0.75
    else:
        return 1.00


def get_signal_strength_label(score: int, max_score: int = 8) -> str:
    """Human-readable strength label."""
    if score <= 4:
        return 'weak'
    elif score == 5:
        return 'medium'
    elif score == 6:
        return 'strong'
    else:
        return 'perfect'


def load_config(
    config_path: str = 'alert_config.json',
) -> Tuple[RiskConfig, ExitConfig, SignalConfig, StratConfig]:
    """Load configuration from alert_config.json.

    Falls back to defaults if the file is missing or incomplete.
    """
    risk = RiskConfig()
    exit_ = ExitConfig()
    signal = SignalConfig()
    strat = StratConfig()

    path = Path(config_path)
    if not path.exists():
        return risk, exit_, signal, strat

    with open(path) as f:
        data = json.load(f)

    # Risk parameters
    rp = data.get('risk_parameters', {})
    if rp:
        risk.max_daily_trades = rp.get('max_daily_trades', risk.max_daily_trades)
        risk.max_concurrent_positions = rp.get('max_concurrent_positions', risk.max_concurrent_positions)
        risk.daily_loss_limit = rp.get('daily_loss_limit', risk.daily_loss_limit) / 100.0 if abs(rp.get('daily_loss_limit', -2)) > 1 else rp.get('daily_loss_limit', risk.daily_loss_limit)
        risk.daily_profit_target = rp.get('daily_profit_target', risk.daily_profit_target) / 100.0 if rp.get('daily_profit_target', 3) > 1 else rp.get('daily_profit_target', risk.daily_profit_target)
        ps = rp.get('position_sizing', {})
        if ps:
            risk.position_sizing = {
                'weak': ps.get('weak_signal', 0.25),
                'medium': ps.get('medium_signal', 0.50),
                'strong': ps.get('strong_signal', 0.75),
                'perfect': ps.get('perfect_signal', 1.00),
            }

    # Exit parameters
    alerts = data.get('alerts', {})
    exit_alerts = alerts.get('exit_alerts', {})
    if exit_alerts:
        pt = exit_alerts.get('profit_target_hit', {})
        if pt:
            call_t = pt.get('call_target', '0.30%')
            put_t = pt.get('put_target', '0.38%')
            exit_.call_target = float(str(call_t).replace('%', '')) / 100.0
            exit_.put_target = float(str(put_t).replace('%', '')) / 100.0

        ts = exit_alerts.get('time_stop', {})
        if ts:
            exit_.call_time_stop = ts.get('call_minutes', exit_.call_time_stop)
            exit_.put_time_stop = ts.get('put_minutes', exit_.put_time_stop)

        rsi_exit = exit_alerts.get('extreme_rsi_exit', {})
        if rsi_exit:
            exit_.call_rsi_exit = rsi_exit.get('call_rsi_exit', exit_.call_rsi_exit)
            exit_.put_rsi_exit = rsi_exit.get('put_rsi_exit', exit_.put_rsi_exit)

    # Signal parameters from alert conditions
    call_alert = alerts.get('primary_call_alert', {}).get('conditions', {})
    if call_alert:
        rsi_range = call_alert.get('rsi_range', [45, 70])
        signal.call_rsi_range = (float(rsi_range[0]), float(rsi_range[1]))
        signal.rvol_minimum = call_alert.get('rvol_minimum', signal.rvol_minimum)

    put_alert = alerts.get('primary_put_alert', {}).get('conditions', {})
    if put_alert:
        rsi_range = put_alert.get('rsi_range', [30, 55])
        signal.put_rsi_range = (float(rsi_range[0]), float(rsi_range[1]))

    # Strat config (may not exist yet in alert_config.json)
    strat_data = data.get('strat', {})
    if strat_data:
        strat.enabled = strat_data.get('enabled', strat.enabled)
        strat.combo_bonus = strat_data.get('combo_bonus', strat.combo_bonus)
        strat.ftfc_bonus = strat_data.get('ftfc_bonus', strat.ftfc_bonus)
        strat.orb_alignment_bonus = strat_data.get('orb_alignment_bonus', strat.orb_alignment_bonus)
        strat.ftfc_threshold = strat_data.get('ftfc_threshold', strat.ftfc_threshold)

    return risk, exit_, signal, strat
