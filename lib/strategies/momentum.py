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
    CALL_RSI_RANGE,
    CONSECUTIVE_THRESHOLD,
    MIN_CONDITIONS,
    PUT_RSI_RANGE,
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


def _check_call_conditions(row: pd.Series) -> tuple[int, list[str]]:
    """Phase 0.7.1: dropped `stoch_rsi_not_overbought`.
    Phase 0.7.2: relaxed `consecutive_up` from 3-of-3 to 3-of-5.
    Phase 0.7.x: added `rvol_above_recent` (volume confirmation).

    The strict 3-of-3 gate misses obvious uptrends with a single
    pullback bar. Reading from `Consecutive_Up_5` (rolling sum of up
    bars over a 5-bar window, populated by add_all_indicators) lets one
    pullback inside an otherwise-trending sequence still satisfy the
    momentum gate.
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Up_5", 0) >= CONSECUTIVE_THRESHOLD:
        score += 1
        conditions.append("consecutive_up")

    rsi = row.get(_rsi_col_name(), row.get("RSI14", 50.0))
    if CALL_RSI_RANGE[0] < rsi < CALL_RSI_RANGE[1]:
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

    return score, conditions


def _check_put_conditions(row: pd.Series) -> tuple[int, list[str]]:
    """Phase 0.7.1 mirror: dropped `stoch_rsi_not_oversold` (free score).
    Phase 0.7.2 mirror: relaxed `consecutive_down` from 3-of-3 to 3-of-5.
    Phase 0.7.x mirror: added `rvol_above_recent` (volume confirmation,
    direction-agnostic — high volume confirms either side of a setup).
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Down_5", 0) >= CONSECUTIVE_THRESHOLD:
        score += 1
        conditions.append("consecutive_down")

    rsi = row.get(_rsi_col_name(), row.get("RSI14", 50.0))
    if PUT_RSI_RANGE[0] < rsi < PUT_RSI_RANGE[1]:
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

    return score, conditions


class MomentumStrategy(Strategy):
    """Momentum: ride strength. Opposite call logic from mean_reversion."""
    name = "momentum"

    def evaluate(self, row: pd.Series) -> Optional[Signal]:
        # Skip warmup bars where indicators are still NaN.
        rsi_val = row.get(_rsi_col_name(), row.get("RSI14"))
        if pd.isna(rsi_val):
            return None
        if pd.isna(row.get("StochRSI_K")):
            return None

        call_score, call_conds = _check_call_conditions(row)
        put_score,  put_conds  = _check_put_conditions(row)

        # Per the original MarketAnalyzer logic: strict greater-than to
        # break ties (one direction must dominate). MIN_CONDITIONS = 3.
        if call_score >= MIN_CONDITIONS and call_score > put_score:
            direction = "CALL"
            score = call_score
            conds = call_conds
        elif put_score >= MIN_CONDITIONS and put_score > call_score:
            direction = "PUT"
            score = put_score
            conds = put_conds
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
