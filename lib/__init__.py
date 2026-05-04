"""
Shared trading library — consolidated indicators, signals, data loading,
configuration, Strat classification, and backtesting.
"""

from lib.indicators import (
    wilder_moving_average,
    calculate_rsi,
    calculate_atr,
    calculate_atr_expansion,
    calculate_ema,
    calculate_vwap,
    calculate_rvol,
    calculate_rvol_recent,
    calculate_obv,
    calculate_stoch_rsi,
    calculate_bollinger_bands,
    calculate_macd,
    calculate_consecutive_moves,
)
from lib.config import load_config, RiskConfig, ExitConfig

__all__ = [
    'wilder_moving_average',
    'calculate_rsi',
    'calculate_atr',
    'calculate_atr_expansion',
    'calculate_ema',
    'calculate_vwap',
    'calculate_rvol',
    'calculate_rvol_recent',
    'calculate_obv',
    'calculate_stoch_rsi',
    'calculate_bollinger_bands',
    'calculate_macd',
    'calculate_consecutive_moves',
    'load_config',
    'RiskConfig',
    'ExitConfig',
]
