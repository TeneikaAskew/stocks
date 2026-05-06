"""Phase 0.8 — Momentum strategy (CALL = buy strength).

Extracted from lib/trading_analysis.py:799-836 (the inline signal-gen
block inside MarketAnalyzer.generate_technical_signals). CALL fires on:
  - Consecutive_Up >= 3 bars (price rising)
  - RSI in (25, 50) — bullish recovery range
  - StochRSI < 80 — not yet overbought
  - Above VWAP
  - Above EMA9

PUT mirrors. This is the OPPOSITE call logic from mean_reversion —
that's why both strategies fire opposite directions on the same bar
~78.6% of the time when both fire (per 5/1 morning audit, §3.9 of plan).

This module is the canonical momentum implementation.
`MarketAnalyzer.generate_technical_signals` continues to exist in
lib/trading_analysis.py as a back-compat wrapper that delegates here.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import Signal, Strategy
from .config import (
    ATR_EXPANSION_THRESHOLD,
    CALL_RSI_RANGE,
    CONSECUTIVE_THRESHOLD,
    CORE_CALL_CONDITIONS,
    CORE_PUT_CONDITIONS,
    MIN_CONDITIONS,
    MIN_CORE_CONDITIONS,
    PUT_RSI_RANGE,
    RSI_THRUST_THRESHOLD,
    RVOL_RECENT_THRESHOLD,
    STOCH_RSI_OVERBOUGHT,
    STOCH_RSI_OVERSOLD,
)


def _rsi_col_name() -> str:
    """MarketAnalyzer's enriched DF emits RSI14_W, not RSI14.

    Look up either form so the strategy works against both
    MarketAnalyzer-enriched DataFrames AND the IndicatorConfig-driven
    column naming used by lib/signals.py callers.
    """
    return "RSI14_W"   # the enriched-DF convention from MarketAnalyzer


def _check_call_conditions(
    row: pd.Series,
    call_rsi_range: tuple[float, float] = CALL_RSI_RANGE,
) -> tuple[int, list[str]]:
    """Phase 0.7.1: dropped `stoch_rsi_not_overbought`.
    Phase 0.7.2: relaxed `consecutive_up` from 3-of-3 to 3-of-5.
    Phase 0.7.x: added `rvol_above_recent` (volume confirmation),
    `atr_expansion` (volatility regime gate), and `rsi_thrust`
    (directional RSI velocity).

    Per the §3.10 strategy audit (273 morning bars, 5/1):
    `stoch_rsi_not_overbought` (StochRSI_K < 80) fired on 72.2% of bars
    — pure free score that didn't discriminate setup quality. Removing
    it tightens the score distribution.

    Seven conditions total; min_conditions=3 still gates fires. Bars
    with full alignment reach score=7 (max conviction, room for tiered
    scoring to differentiate).

    `call_rsi_range` defaults to the Tier-B universal constant; callers
    that have a ticker in scope should pass the Tier-A resolved range
    via `lib.strategies.calibration.get_call_rsi_range(ticker)`.
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Up_5", 0) >= CONSECUTIVE_THRESHOLD:
        score += 1
        conditions.append("consecutive_up")

    rsi = row.get(_rsi_col_name(), row.get("RSI14", 50.0))
    if call_rsi_range[0] < rsi < call_rsi_range[1]:
        score += 1
        conditions.append("rsi_bullish_recovery")

    last = row.get("Close", row.get("Last", 0.0))
    vwap = row.get("VWAP", last)
    if last > vwap:
        score += 1
        conditions.append("above_vwap")

    ema9 = row.get("EMA9", last)
    if last > ema9:
        score += 1
        conditions.append("above_ema9")

    rvol_recent = row.get("RVol_Recent_20")
    if rvol_recent is not None and not pd.isna(rvol_recent) and rvol_recent > RVOL_RECENT_THRESHOLD:
        score += 1
        conditions.append("rvol_above_recent")

    atr_exp = row.get("ATR_Expansion")
    if atr_exp is not None and not pd.isna(atr_exp) and atr_exp > ATR_EXPANSION_THRESHOLD:
        score += 1
        conditions.append("atr_expansion")

    rsi_thrust = row.get("RSI_Thrust_3")
    if rsi_thrust is not None and not pd.isna(rsi_thrust) and rsi_thrust > RSI_THRUST_THRESHOLD:
        score += 1
        conditions.append("rsi_thrust")

    return score, conditions


def _check_put_conditions(
    row: pd.Series,
    put_rsi_range: tuple[float, float] = PUT_RSI_RANGE,
) -> tuple[int, list[str]]:
    """Phase 0.7.1 mirror: dropped `stoch_rsi_not_oversold` (free score).
    Phase 0.7.2 mirror: relaxed `consecutive_down` from 3-of-3 to 3-of-5.
    Phase 0.7.x mirror: added `rvol_above_recent` and `atr_expansion`
    (direction-agnostic confirmers) and `rsi_thrust` (directional —
    fires on negative RSI delta, opposite of CALL's positive-delta gate).

    `put_rsi_range` defaults to the Tier-B universal constant; callers
    that have a ticker in scope should pass the Tier-A resolved range
    via `lib.strategies.calibration.get_put_rsi_range(ticker)`.
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Down_5", 0) >= CONSECUTIVE_THRESHOLD:
        score += 1
        conditions.append("consecutive_down")

    rsi = row.get(_rsi_col_name(), row.get("RSI14", 50.0))
    if put_rsi_range[0] < rsi < put_rsi_range[1]:
        score += 1
        conditions.append("rsi_bearish_recovery")

    last = row.get("Close", row.get("Last", 0.0))
    vwap = row.get("VWAP", last)
    if last < vwap:
        score += 1
        conditions.append("below_vwap")

    ema9 = row.get("EMA9", last)
    if last < ema9:
        score += 1
        conditions.append("below_ema9")

    rvol_recent = row.get("RVol_Recent_20")
    if rvol_recent is not None and not pd.isna(rvol_recent) and rvol_recent > RVOL_RECENT_THRESHOLD:
        score += 1
        conditions.append("rvol_above_recent")

    atr_exp = row.get("ATR_Expansion")
    if atr_exp is not None and not pd.isna(atr_exp) and atr_exp > ATR_EXPANSION_THRESHOLD:
        score += 1
        conditions.append("atr_expansion")

    rsi_thrust = row.get("RSI_Thrust_3")
    # PUT mirrors CALL: looking for negative RSI delta (RSI accelerating
    # down). Threshold is symmetric — same magnitude, opposite sign.
    if rsi_thrust is not None and not pd.isna(rsi_thrust) and rsi_thrust < -RSI_THRUST_THRESHOLD:
        score += 1
        conditions.append("rsi_thrust")

    return score, conditions


class MomentumStrategy(Strategy):
    """Momentum: ride strength. Opposite call logic from mean_reversion."""
    name = "momentum"

    def evaluate(
        self,
        row: pd.Series,
        *,
        call_rsi_range: tuple[float, float] = CALL_RSI_RANGE,
        put_rsi_range: tuple[float, float] = PUT_RSI_RANGE,
    ) -> Optional[Signal]:
        """Evaluate one bar.

        `call_rsi_range` / `put_rsi_range` default to Tier-B universal
        constants. The signal_monitor caller resolves Tier-A values via
        `lib.strategies.calibration` and passes them in per-ticker.
        """
        # Skip warmup bars where indicators are still NaN.
        rsi_val = row.get(_rsi_col_name(), row.get("RSI14"))
        if pd.isna(rsi_val):
            return None
        if pd.isna(row.get("StochRSI_K")):
            return None

        call_score, call_conds = _check_call_conditions(row, call_rsi_range)
        put_score,  put_conds  = _check_put_conditions(row, put_rsi_range)

        # Phase 0.7.x — tier gate. Total-score floor (MIN_CONDITIONS=3)
        # alone allows 3 confirmers + 0 core to fire ("noise + activity").
        # Require at least MIN_CORE_CONDITIONS core conditions so every
        # fire has a credible setup before confirmers can pile on. A
        # gate-blocked direction can't block the other from firing —
        # leaky CALL noise must not suppress a legitimate PUT setup.
        call_core = sum(1 for c in call_conds if c in CORE_CALL_CONDITIONS)
        put_core  = sum(1 for c in put_conds  if c in CORE_PUT_CONDITIONS)

        call_eligible = (call_score >= MIN_CONDITIONS
                         and call_core >= MIN_CORE_CONDITIONS)
        put_eligible  = (put_score  >= MIN_CONDITIONS
                         and put_core  >= MIN_CORE_CONDITIONS)

        # Strict greater-than tie-break only matters when both directions
        # are eligible. A non-eligible direction is silenced — its score
        # cannot suppress the eligible direction's fire.
        if call_eligible and put_eligible:
            if call_score > put_score:
                direction, score, conds, core_count = "CALL", call_score, call_conds, call_core
            elif put_score > call_score:
                direction, score, conds, core_count = "PUT", put_score, put_conds, put_core
            else:
                return None
        elif call_eligible:
            direction, score, conds, core_count = "CALL", call_score, call_conds, call_core
        elif put_eligible:
            direction, score, conds, core_count = "PUT", put_score, put_conds, put_core
        else:
            return None

        return Signal(
            strategy="momentum",
            direction=direction,
            timestamp=_extract_timestamp(row),
            entry_price=float(row.get("Close", row.get("Last", 0.0))),
            base_score=float(score),
            weighted_score=float(score),
            conditions_met=conds,
            core_count=core_count,
            rsi=_safe_float(rsi_val),
            rvol=_safe_float(row.get("RVOL")),
            ema9=_safe_float(row.get("EMA9")),
            ema20=_safe_float(row.get("EMA20")),
            vwap=_safe_float(row.get("VWAP")),
        )


def _extract_timestamp(row: pd.Series) -> pd.Timestamp:
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
