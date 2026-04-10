"""
Typed configuration loaded from alert_config.json.

All behavioral parameters are defined here as dataclass defaults and can be
overridden via JSON. No magic numbers should exist anywhere else in the
codebase — every tunable value flows from these config objects.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Indicator parameters
# ---------------------------------------------------------------------------

@dataclass
class IndicatorConfig:
    """Periods and parameters for all technical indicators."""
    rsi_period: int = 14
    rsi_fast_period: int = 9
    ema_periods: List[int] = field(default_factory=lambda: [9, 20, 50])
    sma_periods: List[int] = field(default_factory=lambda: [5, 10, 20, 50, 200])
    atr_period: int = 14
    rvol_period: int = 20
    stoch_rsi_period: int = 14
    stoch_rsi_k_period: int = 3
    stoch_rsi_d_period: int = 3
    bb_period: int = 20
    bb_std_mult: float = 2.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    consecutive_periods: int = 3
    orb_windows: List[Dict] = field(default_factory=lambda: [
        {'minutes': 5, 'label': '5m'},
        {'minutes': 15, 'label': '15m'},
        {'minutes': 30, 'label': '30m'},
    ])
    order_block_lookback: int = 20
    order_block_consol_window: int = 5
    order_block_consol_threshold: int = 3
    order_block_vol_ratio: float = 0.6
    order_block_ffill_limit: int = 30
    order_block_level_tolerance: float = 0.001

    # --- Column-name helpers (derived from periods) ---

    @property
    def rsi_col(self) -> str:
        return f'RSI{self.rsi_period}'

    @property
    def rsi_fast_col(self) -> str:
        return f'RSI{self.rsi_fast_period}'

    @property
    def atr_col(self) -> str:
        return f'ATR{self.atr_period}'

    @property
    def ema_fast_period(self) -> int:
        """Period of the fast EMA (first entry in ema_periods)."""
        return self.ema_periods[0] if self.ema_periods else 9

    @property
    def ema_mid_period(self) -> int:
        """Period of the mid EMA (second entry in ema_periods)."""
        return self.ema_periods[1] if len(self.ema_periods) > 1 else 20

    @property
    def price_vs_ema_fast_col(self) -> str:
        return f'Price_vs_EMA{self.ema_fast_period}'

    @property
    def price_vs_ema_mid_col(self) -> str:
        return f'Price_vs_EMA{self.ema_mid_period}'


# ---------------------------------------------------------------------------
# AlphaVantage API
# ---------------------------------------------------------------------------

@dataclass
class AlphaVantageConfig:
    """AlphaVantage API rate limits, key management, and settings.

    Current plan: 150 RPM premium.
    Scripts should read AV_RPM from here rather than hardcoding a value.

    API keys are loaded ONLY from environment variables — never hardcoded.
    Supports multi-key rotation via comma-separated ALPHA_VANTAGE_API_KEYS,
    or single key via ALPHA_VANTAGE_API_KEY.
    """
    rpm: int = 150                          # requests per minute (plan limit)

    @property
    def delay_between_calls(self) -> float:
        """Minimum seconds to wait between API calls to stay within RPM."""
        return 60.0 / self.rpm

    @property
    def batch_size(self) -> int:
        """How many calls to make per 60-second window before a forced wait."""
        return self.rpm

    @staticmethod
    def get_api_keys() -> List[str]:
        """Load AV API keys from environment variables.

        Checks ALPHA_VANTAGE_API_KEYS (comma-separated) first, then
        falls back to single ALPHA_VANTAGE_API_KEY. Raises KeyError
        if neither is set.
        """
        import os
        multi = os.environ.get('ALPHA_VANTAGE_API_KEYS', '').strip()
        if multi:
            keys = [k.strip() for k in multi.split(',') if k.strip()]
            if keys:
                return keys
        single = os.environ.get('ALPHA_VANTAGE_API_KEY', '').strip()
        if single:
            return [single]
        raise KeyError(
            "No AlphaVantage API key found. "
            "Set ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEYS in your environment."
        )


# ---------------------------------------------------------------------------
# Market / environment
# ---------------------------------------------------------------------------

@dataclass
class MarketConfig:
    """Market hours, tickers, and filesystem paths."""
    tickers: List[str] = field(default_factory=lambda: ['IWM', 'SPY', 'QQQ'])
    market_open: str = '09:30'
    market_close: str = '16:00'
    data_dir: str = 'data'
    output_dir: str = 'data/backtest_results'
    trades_dir: str = 'data/trades'

    @property
    def market_open_time(self):
        from datetime import time
        h, m = self.market_open.split(':')
        return time(int(h), int(m))

    @property
    def market_close_time(self):
        from datetime import time
        h, m = self.market_close.split(':')
        return time(int(h), int(m))


# ---------------------------------------------------------------------------
# Real-time monitor
# ---------------------------------------------------------------------------

@dataclass
class MonitorConfig:
    """Real-time signal monitor parameters."""
    poll_interval: int = 60          # seconds between polls
    rolling_window_bars: int = 200   # bars kept in rolling window
    min_bars_for_indicators: int = 20
    min_bars_for_signals: int = 30
    pre_market_sleep: int = 30       # seconds to sleep before market open
    discord_timeout: int = 10        # HTTP timeout for Discord webhooks


# ---------------------------------------------------------------------------
# Backtesting engine
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    """Backtesting engine parameters."""
    min_bars_per_day: int = 10
    starting_equity: float = 1.0
    annualization_factor: int = 252  # trading days/year for Sharpe


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardConfig:
    """Walk-forward validation parameters."""
    min_test_bars: int = 50
    default_train_months: int = 6
    default_test_months: int = 1


# ---------------------------------------------------------------------------
# Risk management
# ---------------------------------------------------------------------------

@dataclass
class RiskConfig:
    max_daily_trades: int = 5
    max_concurrent_positions: int = 1
    daily_loss_limit: float = -0.02   # -2%
    daily_profit_target: float = 0.03  # +3%
    position_sizing: Dict[str, float] = field(default_factory=lambda: {
        'weak': 0.25,
        'medium': 0.50,
        'strong': 0.75,
        'perfect': 1.00,
    })
    # Score boundaries: weak ≤ t[0], medium ≤ t[1], strong ≤ t[2], else perfect
    score_thresholds: Tuple[int, int, int] = (4, 5, 6)
    max_score: int = 8


# ---------------------------------------------------------------------------
# Exit rules
# ---------------------------------------------------------------------------

@dataclass
class ExitConfig:
    call_target: float = 0.0030   # +0.30%
    put_target: float = 0.0038    # +0.38%
    call_stop: float = 0.0015     # -0.15%
    put_stop: float = 0.0020      # -0.20%
    call_time_stop: int = 30      # minutes
    put_time_stop: int = 35       # minutes
    call_rsi_exit: float = 80.0
    put_rsi_exit: float = 20.0


# ---------------------------------------------------------------------------
# Strat integration
# ---------------------------------------------------------------------------

@dataclass
class StratConfig:
    enabled: bool = True
    combo_bonus: int = 1
    ftfc_bonus: int = 1
    orb_alignment_bonus: int = 1
    ftfc_threshold: float = 0.6
    ftfc_direction_threshold: float = 0.3
    ftfc_filter_enabled: bool = True    # Reject trades contradicted by FTFC
    orb_filter_enabled: bool = True     # Reject trades contradicted by ORB trend
    timeframes: list = field(default_factory=lambda: ['5m', '15m', '1h', 'D', 'W'])
    ftfc_weights: Dict[str, float] = field(default_factory=lambda: {
        '5m': 0.10, '15m': 0.20, '1h': 0.25, 'D': 0.35, 'W': 0.10,
    })


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

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
    ema_proximity_threshold: float = 0.1
    stoch_rsi_oversold: float = 30.0
    stoch_rsi_overbought: float = 70.0
    premarket_signal_threshold: int = 3   # min score = "setup"
    premarket_building_threshold: int = 2  # min score = "building"


# ---------------------------------------------------------------------------
# Aggregate config container
# ---------------------------------------------------------------------------

class ConfigValidationError(ValueError):
    """Raised when config values fail validation checks."""


@dataclass
class AppConfig:
    """Top-level container for all configuration."""
    risk: RiskConfig = field(default_factory=RiskConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    strat: StratConfig = field(default_factory=StratConfig)
    indicator: IndicatorConfig = field(default_factory=IndicatorConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    walk_forward: WalkForwardConfig = field(default_factory=WalkForwardConfig)

    def validate(self) -> None:
        """Run range checks on all config values. Raises ConfigValidationError."""
        errors = []

        # Risk
        if not (1 <= self.risk.max_daily_trades <= 50):
            errors.append(f"risk.max_daily_trades={self.risk.max_daily_trades}, expected 1-50")
        if not (-1.0 <= self.risk.daily_loss_limit <= 0.0):
            errors.append(f"risk.daily_loss_limit={self.risk.daily_loss_limit}, expected [-1.0, 0.0]")
        if not (0.0 <= self.risk.daily_profit_target <= 1.0):
            errors.append(f"risk.daily_profit_target={self.risk.daily_profit_target}, expected [0.0, 1.0]")
        t = self.risk.score_thresholds
        if len(t) != 3 or not (t[0] <= t[1] <= t[2]):
            errors.append(f"risk.score_thresholds={t}, must be 3 increasing values")

        # Exit
        for attr in ['call_target', 'put_target']:
            v = getattr(self.exit, attr)
            if not (0 < v <= 0.10):
                errors.append(f"exit.{attr}={v}, expected (0, 0.10]")
        for attr in ['call_stop', 'put_stop']:
            v = getattr(self.exit, attr)
            if not (0 < v <= 0.10):
                errors.append(f"exit.{attr}={v}, expected (0, 0.10]")
        for attr in ['call_time_stop', 'put_time_stop']:
            v = getattr(self.exit, attr)
            if not (1 <= v <= 480):
                errors.append(f"exit.{attr}={v}, expected 1-480 minutes")

        # Signal
        if not (1 <= self.signal.min_conditions <= 8):
            errors.append(f"signal.min_conditions={self.signal.min_conditions}, expected 1-8")
        cr = self.signal.call_rsi_range
        if not (0 <= cr[0] < cr[1] <= 100):
            errors.append(f"signal.call_rsi_range={cr}, must be increasing pair in [0, 100]")
        pr = self.signal.put_rsi_range
        if not (0 <= pr[0] < pr[1] <= 100):
            errors.append(f"signal.put_rsi_range={pr}, must be increasing pair in [0, 100]")

        # Indicator
        if not (2 <= self.indicator.rsi_period <= 100):
            errors.append(f"indicator.rsi_period={self.indicator.rsi_period}, expected 2-100")
        if not (2 <= self.indicator.macd_fast < self.indicator.macd_slow):
            errors.append(f"indicator.macd_fast={self.indicator.macd_fast} must be < macd_slow={self.indicator.macd_slow}")

        # Strat
        if not (0.0 <= self.strat.ftfc_threshold <= 1.0):
            errors.append(f"strat.ftfc_threshold={self.strat.ftfc_threshold}, expected [0, 1]")

        if errors:
            raise ConfigValidationError(
                f"Config validation failed ({len(errors)} error(s)):\n  " + "\n  ".join(errors)
            )


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def get_position_size(score: int, risk_config: RiskConfig = None) -> float:
    """Map combined signal score to position size fraction.

    Uses score_thresholds from RiskConfig to bucket the score.
    """
    cfg = risk_config or RiskConfig()
    t = cfg.score_thresholds
    s = cfg.position_sizing
    if score <= t[0]:
        return s['weak']
    elif score <= t[1]:
        return s['medium']
    elif score <= t[2]:
        return s['strong']
    else:
        return s['perfect']


def get_signal_strength_label(score: int, risk_config: RiskConfig = None) -> str:
    """Human-readable strength label derived from score_thresholds."""
    cfg = risk_config or RiskConfig()
    t = cfg.score_thresholds
    if score <= t[0]:
        return 'weak'
    elif score <= t[1]:
        return 'medium'
    elif score <= t[2]:
        return 'strong'
    else:
        return 'perfect'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pct(value) -> float:
    """Parse a percentage value that may be a string like ``"0.30%"`` or a raw float.

    Returns a decimal fraction (e.g. 0.003 for 0.30%).

    Handles three formats:
    - ``"0.30%"`` → strip ``%``, divide by 100 → 0.003
    - ``0.30`` or ``"0.30"`` (no ``%``, >= 0.01) → treat as percent, divide by 100 → 0.003
    - ``0.003`` (already a decimal fraction, < 0.01) → use as-is
    """
    s = str(value)
    if '%' in s:
        return float(s.replace('%', '')) / 100.0
    f = float(s)
    # Profit targets / stops are always < 1%.  A raw value >= 0.01 is almost
    # certainly expressed as a percentage (e.g. 0.30 meaning 0.30%) rather than
    # a decimal fraction (which would mean 30%).
    if abs(f) >= 0.01:
        return f / 100.0
    return f


# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------

def load_config(config_path: str = 'alert_config.json', ticker: str = None) -> AppConfig:
    """Load configuration from alert_config.json.

    Falls back to dataclass defaults if the file is missing or incomplete.
    Returns an AppConfig containing every sub-config used across the system.

    If *ticker* is provided and the JSON contains a ``ticker_overrides.<TICKER>``
    section, those values are merged on top of the base config, allowing
    per-ticker tuning (different targets, timeframes, thresholds, etc.).
    """
    app = AppConfig()

    path = Path(config_path)
    if not path.exists():
        return app

    with open(path) as f:
        data = json.load(f)

    # --- Risk parameters ---
    rp = data.get('risk_parameters', {})
    if rp:
        app.risk.max_daily_trades = rp.get('max_daily_trades', app.risk.max_daily_trades)
        app.risk.max_concurrent_positions = rp.get('max_concurrent_positions', app.risk.max_concurrent_positions)
        dl = rp.get('daily_loss_limit', None)
        if dl is not None:
            app.risk.daily_loss_limit = dl / 100.0 if abs(dl) > 1 else dl
        dp = rp.get('daily_profit_target', None)
        if dp is not None:
            app.risk.daily_profit_target = dp / 100.0 if dp > 1 else dp
        ps = rp.get('position_sizing', {})
        if ps:
            app.risk.position_sizing = {
                'weak': ps.get('weak_signal', 0.25),
                'medium': ps.get('medium_signal', 0.50),
                'strong': ps.get('strong_signal', 0.75),
                'perfect': ps.get('perfect_signal', 1.00),
            }
        st = rp.get('score_thresholds', None)
        if st:
            app.risk.score_thresholds = tuple(st)
        app.risk.max_score = rp.get('max_score', app.risk.max_score)

    # --- Exit parameters (from alerts.exit_alerts) ---
    alerts = data.get('alerts', {})
    exit_alerts = alerts.get('exit_alerts', {})
    if exit_alerts:
        pt = exit_alerts.get('profit_target_hit', {})
        if pt:
            call_t = pt.get('call_target', None)
            if call_t is not None:
                app.exit.call_target = _parse_pct(call_t)
            put_t = pt.get('put_target', None)
            if put_t is not None:
                app.exit.put_target = _parse_pct(put_t)
            call_s = pt.get('call_stop', None)
            if call_s is not None:
                app.exit.call_stop = _parse_pct(call_s)
            put_s = pt.get('put_stop', None)
            if put_s is not None:
                app.exit.put_stop = _parse_pct(put_s)

        ts = exit_alerts.get('time_stop', {})
        if ts:
            app.exit.call_time_stop = ts.get('call_minutes', app.exit.call_time_stop)
            app.exit.put_time_stop = ts.get('put_minutes', app.exit.put_time_stop)

        rsi_exit = exit_alerts.get('extreme_rsi_exit', {})
        if rsi_exit:
            app.exit.call_rsi_exit = rsi_exit.get('call_rsi_exit', app.exit.call_rsi_exit)
            app.exit.put_rsi_exit = rsi_exit.get('put_rsi_exit', app.exit.put_rsi_exit)

    # --- Signal parameters (baseline from alerts, then signal section) ---
    call_alert = alerts.get('primary_call_alert', {}).get('conditions', {})
    if call_alert:
        rsi_range = call_alert.get('rsi_range', list(app.signal.call_rsi_range))
        app.signal.call_rsi_range = (float(rsi_range[0]), float(rsi_range[1]))
        app.signal.rvol_minimum = call_alert.get('rvol_minimum', app.signal.rvol_minimum)

    put_alert = alerts.get('primary_put_alert', {}).get('conditions', {})
    if put_alert:
        rsi_range = put_alert.get('rsi_range', list(app.signal.put_rsi_range))
        app.signal.put_rsi_range = (float(rsi_range[0]), float(rsi_range[1]))

    # Signal section overrides (more specific)
    sig_data = data.get('signal', {})
    if sig_data:
        app.signal.min_conditions = sig_data.get('min_conditions', app.signal.min_conditions)
        app.signal.consecutive_periods = sig_data.get('consecutive_periods', app.signal.consecutive_periods)
        if 'call_rsi_range' in sig_data:
            app.signal.call_rsi_range = tuple(sig_data['call_rsi_range'])
        if 'put_rsi_range' in sig_data:
            app.signal.put_rsi_range = tuple(sig_data['put_rsi_range'])
        app.signal.ema_proximity_threshold = sig_data.get('ema_proximity_threshold', app.signal.ema_proximity_threshold)
        app.signal.stoch_rsi_oversold = sig_data.get('stoch_rsi_oversold', app.signal.stoch_rsi_oversold)
        app.signal.stoch_rsi_overbought = sig_data.get('stoch_rsi_overbought', app.signal.stoch_rsi_overbought)
        app.signal.call_entry_start = sig_data.get('call_entry_start', app.signal.call_entry_start)
        app.signal.call_entry_end = sig_data.get('call_entry_end', app.signal.call_entry_end)
        app.signal.put_entry_start = sig_data.get('put_entry_start', app.signal.put_entry_start)
        app.signal.put_entry_end = sig_data.get('put_entry_end', app.signal.put_entry_end)
        app.signal.premarket_signal_threshold = sig_data.get('premarket_signal_threshold', app.signal.premarket_signal_threshold)
        app.signal.premarket_building_threshold = sig_data.get('premarket_building_threshold', app.signal.premarket_building_threshold)

    # --- Strat config ---
    strat_data = data.get('strat', {})
    if strat_data:
        app.strat.enabled = strat_data.get('enabled', app.strat.enabled)
        app.strat.combo_bonus = strat_data.get('combo_bonus', app.strat.combo_bonus)
        app.strat.ftfc_bonus = strat_data.get('ftfc_bonus', app.strat.ftfc_bonus)
        app.strat.orb_alignment_bonus = strat_data.get('orb_alignment_bonus', app.strat.orb_alignment_bonus)
        app.strat.ftfc_threshold = strat_data.get('ftfc_threshold', app.strat.ftfc_threshold)
        app.strat.ftfc_direction_threshold = strat_data.get('ftfc_direction_threshold', app.strat.ftfc_direction_threshold)
        app.strat.ftfc_filter_enabled = strat_data.get('ftfc_filter_enabled', app.strat.ftfc_filter_enabled)
        app.strat.orb_filter_enabled = strat_data.get('orb_filter_enabled', app.strat.orb_filter_enabled)
        app.strat.timeframes = strat_data.get('timeframes', app.strat.timeframes)
        app.strat.ftfc_weights = strat_data.get('ftfc_weights', app.strat.ftfc_weights)

    # --- Indicator config ---
    ind_data = data.get('indicators', {})
    if ind_data:
        for fld in [
            'rsi_period', 'rsi_fast_period', 'atr_period', 'rvol_period',
            'stoch_rsi_period', 'stoch_rsi_k_period', 'stoch_rsi_d_period',
            'bb_period', 'macd_fast', 'macd_slow', 'macd_signal',
            'consecutive_periods', 'order_block_lookback',
            'order_block_consol_window', 'order_block_consol_threshold',
            'order_block_ffill_limit',
        ]:
            if fld in ind_data:
                setattr(app.indicator, fld, ind_data[fld])
        for fld in ['bb_std_mult', 'order_block_vol_ratio', 'order_block_level_tolerance']:
            if fld in ind_data:
                setattr(app.indicator, fld, float(ind_data[fld]))
        if 'ema_periods' in ind_data:
            app.indicator.ema_periods = ind_data['ema_periods']
        if 'sma_periods' in ind_data:
            app.indicator.sma_periods = ind_data['sma_periods']
        if 'orb_windows' in ind_data:
            app.indicator.orb_windows = ind_data['orb_windows']

    # --- Market config ---
    mkt_data = data.get('market', {})
    if mkt_data:
        for fld in ['tickers', 'market_open', 'market_close', 'data_dir', 'output_dir', 'trades_dir']:
            if fld in mkt_data:
                setattr(app.market, fld, mkt_data[fld])

    # --- Monitor config ---
    mon_data = data.get('monitor', {})
    if mon_data:
        for fld in [
            'poll_interval', 'rolling_window_bars', 'min_bars_for_indicators',
            'min_bars_for_signals', 'pre_market_sleep', 'discord_timeout',
        ]:
            if fld in mon_data:
                setattr(app.monitor, fld, mon_data[fld])

    # --- Backtest config ---
    bt_data = data.get('backtest', {})
    if bt_data:
        for fld in ['min_bars_per_day', 'annualization_factor']:
            if fld in bt_data:
                setattr(app.backtest, fld, bt_data[fld])
        if 'starting_equity' in bt_data:
            app.backtest.starting_equity = float(bt_data['starting_equity'])

    # --- Walk-forward config ---
    wf_data = data.get('walk_forward', {})
    if wf_data:
        for fld in ['min_test_bars', 'default_train_months', 'default_test_months']:
            if fld in wf_data:
                setattr(app.walk_forward, fld, wf_data[fld])

    # --- Per-ticker overrides ---
    if ticker:
        overrides = data.get('ticker_overrides', {}).get(ticker.upper(), {})
        if overrides:
            _apply_ticker_overrides(app, overrides)

    app.validate()
    return app


def _apply_ticker_overrides(app: AppConfig, overrides: dict) -> None:
    """Merge ticker-specific overrides on top of the base AppConfig."""

    # Exit overrides
    exit_ov = overrides.get('exit', {})
    for fld in ['call_target', 'put_target', 'call_stop', 'put_stop']:
        if fld in exit_ov:
            setattr(app.exit, fld, float(exit_ov[fld]))
    for fld in ['call_time_stop', 'put_time_stop']:
        if fld in exit_ov:
            setattr(app.exit, fld, int(exit_ov[fld]))
    for fld in ['call_rsi_exit', 'put_rsi_exit']:
        if fld in exit_ov:
            setattr(app.exit, fld, float(exit_ov[fld]))

    # Signal overrides
    sig_ov = overrides.get('signal', {})
    for fld in ['min_conditions', 'consecutive_periods']:
        if fld in sig_ov:
            setattr(app.signal, fld, int(sig_ov[fld]))
    for fld in ['ema_proximity_threshold', 'stoch_rsi_oversold', 'stoch_rsi_overbought', 'rvol_minimum']:
        if fld in sig_ov:
            setattr(app.signal, fld, float(sig_ov[fld]))
    for fld in ['call_entry_start', 'call_entry_end', 'put_entry_start', 'put_entry_end']:
        if fld in sig_ov:
            setattr(app.signal, fld, sig_ov[fld])
    if 'call_rsi_range' in sig_ov:
        app.signal.call_rsi_range = tuple(sig_ov['call_rsi_range'])
    if 'put_rsi_range' in sig_ov:
        app.signal.put_rsi_range = tuple(sig_ov['put_rsi_range'])

    # Indicator overrides
    ind_ov = overrides.get('indicators', {})
    for fld in ['rsi_period', 'atr_period', 'rvol_period', 'consecutive_periods']:
        if fld in ind_ov:
            setattr(app.indicator, fld, int(ind_ov[fld]))
    if 'ema_periods' in ind_ov:
        app.indicator.ema_periods = ind_ov['ema_periods']

    # Risk overrides
    risk_ov = overrides.get('risk', {})
    for fld in ['max_daily_trades', 'max_concurrent_positions', 'max_score']:
        if fld in risk_ov:
            setattr(app.risk, fld, int(risk_ov[fld]))

    # Strat overrides
    strat_ov = overrides.get('strat', {})
    for fld in ['enabled', 'combo_bonus', 'ftfc_bonus', 'orb_alignment_bonus',
                'ftfc_filter_enabled', 'orb_filter_enabled']:
        if fld in strat_ov:
            setattr(app.strat, fld, strat_ov[fld])
    for fld in ['ftfc_threshold', 'ftfc_direction_threshold']:
        if fld in strat_ov:
            setattr(app.strat, fld, float(strat_ov[fld]))

    # Optimal timeframe combination (metadata for downstream use)
    if 'optimal_timeframe' in overrides:
        app.optimal_timeframe = overrides['optimal_timeframe']
