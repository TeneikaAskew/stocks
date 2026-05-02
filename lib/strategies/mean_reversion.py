"""Phase 0.8 — Mean-reversion strategy (CALL = buy oversold dips).

Extracted from lib/signals.py. CALL fires on:
  - Consecutive_Down >= 3 bars
  - RSI in (25, 50) — oversold but not extreme
  - Below VWAP
  - Near or below EMA fast / EMA mid
  - StochRSI < 30 (oversold)
  - level_break_pdh (Strat v2 — Broke_Prev_Day_High aligned with bullish reversal)

PUT mirrors. Used by `gcp/signal_monitor.py` (live monitor) since well
before this refactor — see lib/signals.py for the original implementation
that this module replaces.

This file IS the canonical mean-reversion implementation. The legacy
`lib/signals.py` is now a thin shim that re-exports from here.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import Signal, Strategy
from .config import (
    CALL_RSI_RANGE,
    CONSECUTIVE_PERIODS,
    EMA_PROXIMITY,
    MIN_CONDITIONS,
    PUT_RSI_RANGE,
    STOCH_RSI_OVERBOUGHT,
    STOCH_RSI_OVERSOLD,
)


def _rsi_col_name() -> str:
    """The indicator column name in the enriched DataFrame."""
    # Late import to avoid coupling the strategies package to lib.config
    from lib.config import IndicatorConfig
    return IndicatorConfig().rsi_col


def _ema_fast_col() -> str:
    from lib.config import IndicatorConfig
    return IndicatorConfig().price_vs_ema_fast_col


def _ema_mid_col() -> str:
    from lib.config import IndicatorConfig
    return IndicatorConfig().price_vs_ema_mid_col


def _check_call_conditions(row: pd.Series) -> tuple[int, list[str]]:
    """Phase 0.7.2: dropped `near_below_emas`.

    Per the §3.10 strategy audit: `near_below_emas` (EMA proximity ≤ 0.1)
    fired on 84.6% of bars — the same "free score" pathology momentum
    had with stoch_rsi_not_overbought. Removing it tightens score
    distribution: bars in the meandering middle of the EMA stack no
    longer get a free contribution to score on top of their other
    conditions.
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Down", 0) >= CONSECUTIVE_PERIODS:
        score += 1
        conditions.append("consecutive_down")

    rsi = row.get(_rsi_col_name(), 50.0)
    if CALL_RSI_RANGE[0] < rsi < CALL_RSI_RANGE[1]:
        score += 1
        conditions.append("rsi_oversold_zone")

    if row.get("Price_vs_VWAP", 0.0) < 0:
        score += 1
        conditions.append("below_vwap")

    if row.get("StochRSI_K", 50.0) < STOCH_RSI_OVERSOLD:
        score += 1
        conditions.append("stoch_rsi_oversold")

    if int(row.get("Broke_Prev_Day_High", 0) or 0) == 1:
        score += 1
        conditions.append("level_break_pdh")

    return score, conditions


def _check_put_conditions(row: pd.Series) -> tuple[int, list[str]]:
    """Phase 0.7.2 mirror: dropped `near_above_emas` (free score)."""
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Up", 0) >= CONSECUTIVE_PERIODS:
        score += 1
        conditions.append("consecutive_up")

    rsi = row.get(_rsi_col_name(), 50.0)
    if PUT_RSI_RANGE[0] < rsi < PUT_RSI_RANGE[1]:
        score += 1
        conditions.append("rsi_overbought_zone")

    if row.get("Price_vs_VWAP", 0.0) > 0:
        score += 1
        conditions.append("above_vwap")

    if row.get("StochRSI_K", 50.0) > STOCH_RSI_OVERBOUGHT:
        score += 1
        conditions.append("stoch_rsi_overbought")

    if int(row.get("Broke_Prev_Day_Low", 0) or 0) == 1:
        score += 1
        conditions.append("level_break_pdl")

    return score, conditions


class MeanReversionStrategy(Strategy):
    """Mean-reversion: fade overextensions, buy oversold dips."""
    name = "mean_reversion"

    def evaluate(self, row: pd.Series) -> Optional[Signal]:
        # Skip warmup bars where indicators are still NaN.
        if pd.isna(row.get(_rsi_col_name())):
            return None
        if pd.isna(row.get("StochRSI_K")):
            return None

        call_score, call_conds = _check_call_conditions(row)
        put_score,  put_conds  = _check_put_conditions(row)

        if call_score >= MIN_CONDITIONS and call_score >= put_score:
            direction = "CALL"
            score = call_score
            conds = call_conds
        elif put_score >= MIN_CONDITIONS:
            direction = "PUT"
            score = put_score
            conds = put_conds
        else:
            return None

        return Signal(
            strategy="mean_reversion",
            direction=direction,
            timestamp=_extract_timestamp(row),
            entry_price=float(row.get("Close", row.get("Last", 0.0))),
            base_score=float(score),
            weighted_score=float(score),  # Phase 4 may add weights; identity for now
            conditions_met=conds,
            rsi=_safe_float(row.get(_rsi_col_name())),
            rvol=_safe_float(row.get("RVOL")),
            ema9=_safe_float(row.get("EMA9")),
            ema20=_safe_float(row.get("EMA20")),
            vwap=_safe_float(row.get("VWAP")),
        )


def _extract_timestamp(row: pd.Series) -> pd.Timestamp:
    """Pull the bar's timestamp from common column conventions."""
    ts = row.get("Time", row.get("ts", row.name))
    return pd.Timestamp(ts) if not isinstance(ts, pd.Timestamp) else ts


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
