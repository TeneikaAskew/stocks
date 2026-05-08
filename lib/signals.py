"""
Signal generation — 3-of-5 condition scoring for CALL and PUT entries,
with optional Strat bonus integration (up to +3 points for max 8-point scale).

Extracted from analyze_market_data_enhanced.py and unified with the
alert parameters from alert_config.json.
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional

from lib.config import IndicatorConfig, SignalConfig


def check_call_conditions(
    row: pd.Series,
    consecutive_periods: int = 3,
    rsi_range: Tuple[float, float] = (25.0, 50.0),
    ema_proximity: float = 0.1,
    stoch_rsi_threshold: float = 30.0,
    indicator_config: IndicatorConfig = None,
) -> Tuple[int, List[str]]:
    """Evaluate CALL signal conditions for a single bar.

    Returns (score, list_of_conditions_met) where score is 0-5.
    """
    ind = indicator_config or IndicatorConfig()
    score = 0
    conditions = []

    # 1. Consecutive down periods (contrarian — buy after selling pressure)
    if row.get('Consecutive_Down', 0) >= consecutive_periods:
        score += 1
        conditions.append('consecutive_down')

    # 2. RSI in bullish zone (oversold but not extreme)
    rsi = row.get(ind.rsi_col, 50.0)
    if rsi_range[0] < rsi < rsi_range[1]:
        score += 1
        conditions.append('rsi_oversold_zone')

    # 3. Price below VWAP (contrarian — buying under fair value)
    price_vs_vwap = row.get('Price_vs_VWAP', 0.0)
    if price_vs_vwap < 0:
        score += 1
        conditions.append('below_vwap')

    # Phase 0.7.2: dropped `near_below_emas` (was 84.6% fire rate per
    # §3.10 strategy audit — pure free score). The EMA proximity columns
    # are still computed by lib/indicators and recorded on signal rows
    # for analysis, just not contributing to the score anymore.

    # 5. Stochastic RSI oversold
    stoch_k = row.get('StochRSI_K', 50.0)
    if stoch_k < stoch_rsi_threshold:
        score += 1
        conditions.append('stoch_rsi_oversold')

    # 6. Level break aligned with direction (Strat v2 — see methodology §6).
    # Reads Broke_Prev_Day_High from market_data_daily / calculate_historical_levels.
    if int(row.get('Broke_Prev_Day_High', 0) or 0) == 1:
        score += 1
        conditions.append('level_break_pdh')

    return score, conditions


def check_put_conditions(
    row: pd.Series,
    consecutive_periods: int = 3,
    rsi_range: Tuple[float, float] = (50.0, 75.0),
    ema_proximity: float = 0.1,
    stoch_rsi_threshold: float = 70.0,
    indicator_config: IndicatorConfig = None,
) -> Tuple[int, List[str]]:
    """Evaluate PUT signal conditions for a single bar.

    Returns (score, list_of_conditions_met) where score is 0-5 (now 0-4
    after the 2026-05-08 audit dropped `above_vwap`).
    """
    ind = indicator_config or IndicatorConfig()
    score = 0
    conditions = []

    # 1. Consecutive up periods (contrarian — sell after buying pressure)
    if row.get('Consecutive_Up', 0) >= consecutive_periods:
        score += 1
        conditions.append('consecutive_up')

    # 2. RSI in bearish zone (overbought but not extreme)
    rsi = row.get(ind.rsi_col, 50.0)
    if rsi_range[0] < rsi < rsi_range[1]:
        score += 1
        conditions.append('rsi_overbought_zone')

    # `above_vwap` REMOVED — Track A G.P0.12 (audit 2026-05-08).
    # Audit measured -16.1pp (QQQ), -11.7pp (IWM), -9.9pp (SPY)
    # win-rate vs no-above_vwap PUTs across 90 days. The factor is
    # ANTI-correlated with PUT success and was dragging strategy EV
    # negative. Momentum's `above_vwap` (CALL direction) is a separate
    # code path and remains unchanged.

    # Phase 0.7.2: dropped `near_above_emas` (PUT-side mirror of the
    # CALL-side `near_below_emas` drop). Same 84.6% free-fire issue.

    # 5. Stochastic RSI overbought
    stoch_k = row.get('StochRSI_K', 50.0)
    if stoch_k > stoch_rsi_threshold:
        score += 1
        conditions.append('stoch_rsi_overbought')

    # 6. Level break aligned with direction (Strat v2 — see methodology §6).
    if int(row.get('Broke_Prev_Day_Low', 0) or 0) == 1:
        score += 1
        conditions.append('level_break_pdl')

    return score, conditions


def evaluate_signal(
    row: pd.Series,
    min_conditions: int = 3,
    consecutive_periods: int = 3,
    call_rsi_range: Tuple[float, float] = (25.0, 50.0),
    put_rsi_range: Tuple[float, float] = (50.0, 75.0),
    strat_bonus: int = 0,
    signal_config: SignalConfig = None,
    indicator_config: IndicatorConfig = None,
    ticker: Optional[str] = None,
) -> Optional[dict]:
    """Evaluate both CALL and PUT conditions for a single bar.

    Returns a signal dict if conditions are met, else None.
    The `strat_bonus` parameter adds 0-3 points from Strat integration.

    If `signal_config` is provided its values override the individual
    parameters for EMA proximity and StochRSI thresholds.

    `ticker` (optional): when provided, per-ticker disabled conditions
    from `exit_config_overrides.disabled_conditions` are filtered out
    of CALL and PUT scores BEFORE the MIN_CONDITIONS gate. Track A
    G.P0.13. None = no per-ticker filter (legacy default).
    """
    sig_cfg = signal_config
    ema_prox = sig_cfg.ema_proximity_threshold if sig_cfg else 0.1
    stoch_oversold = sig_cfg.stoch_rsi_oversold if sig_cfg else 30.0
    stoch_overbought = sig_cfg.stoch_rsi_overbought if sig_cfg else 70.0

    call_score, call_conds = check_call_conditions(
        row, consecutive_periods, call_rsi_range,
        ema_proximity=ema_prox, stoch_rsi_threshold=stoch_oversold,
        indicator_config=indicator_config,
    )
    put_score, put_conds = check_put_conditions(
        row, consecutive_periods, put_rsi_range,
        ema_proximity=ema_prox, stoch_rsi_threshold=stoch_overbought,
        indicator_config=indicator_config,
    )

    # Per-ticker drop-list filter (Track A G.P0.13). Filters AFTER
    # scoring so the inline math stays simple. Missing/empty list →
    # no-op.
    if ticker:
        from lib.strategies.exit_config_overrides import get_disabled_conditions
        disabled = set(get_disabled_conditions(ticker))
        if disabled:
            call_conds = [c for c in call_conds if c not in disabled]
            call_score = len(call_conds)
            put_conds = [c for c in put_conds if c not in disabled]
            put_score = len(put_conds)

    signal = None

    if call_score >= min_conditions and call_score >= put_score:
        total_score = call_score + strat_bonus
        signal = {
            'direction': 'CALL',
            'base_score': call_score,
            'strat_bonus': strat_bonus,
            'total_score': total_score,
            'conditions_met': call_conds,
        }
    elif put_score >= min_conditions:
        total_score = put_score + strat_bonus
        signal = {
            'direction': 'PUT',
            'base_score': put_score,
            'strat_bonus': strat_bonus,
            'total_score': total_score,
            'conditions_met': put_conds,
        }

    return signal


def generate_signals(
    df: pd.DataFrame,
    min_conditions: int = 3,
    consecutive_periods: int = 3,
    call_rsi_range: Tuple[float, float] = (25.0, 50.0),
    put_rsi_range: Tuple[float, float] = (50.0, 75.0),
    signal_config: SignalConfig = None,
    indicator_config: IndicatorConfig = None,
) -> pd.DataFrame:
    """Scan an indicator-enriched DataFrame for CALL/PUT signals.

    Returns a DataFrame of detected signals with columns:
    index, direction, base_score, total_score, conditions_met,
    and all indicator values at the signal bar.
    """
    ind = indicator_config or IndicatorConfig()
    signals = []

    for idx in range(consecutive_periods, len(df)):
        row = df.iloc[idx]

        # Skip bars with missing critical indicators
        if pd.isna(row.get(ind.rsi_col)) or pd.isna(row.get('Close', row.get('Last'))):
            continue
        if pd.isna(row.get('Price_vs_VWAP')) or pd.isna(row.get('StochRSI_K')):
            continue

        sig = evaluate_signal(
            row,
            min_conditions=min_conditions,
            consecutive_periods=consecutive_periods,
            call_rsi_range=call_rsi_range,
            put_rsi_range=put_rsi_range,
            signal_config=signal_config,
            indicator_config=indicator_config,
        )

        if sig:
            close_col = 'Close' if 'Close' in df.columns else 'Last'
            sig['bar_index'] = idx
            sig['time'] = df.index[idx] if isinstance(df.index, pd.DatetimeIndex) else row.get('Time')
            sig['price'] = row[close_col]
            sig['rsi'] = row.get(ind.rsi_col)
            sig['stoch_rsi_k'] = row.get('StochRSI_K')
            sig['ema_fast'] = row.get(f'EMA{ind.ema_fast_period}')
            sig['ema_mid'] = row.get(f'EMA{ind.ema_mid_period}')
            sig['vwap'] = row.get('VWAP')
            sig['atr'] = row.get(ind.atr_col)
            sig['rvol'] = row.get('RVOL')
            signals.append(sig)

    return pd.DataFrame(signals) if signals else pd.DataFrame()
