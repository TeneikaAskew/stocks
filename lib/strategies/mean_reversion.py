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


def _check_call_conditions(
    row: pd.Series,
    call_rsi_range: tuple[float, float] = CALL_RSI_RANGE,
) -> tuple[int, list[str]]:
    """Phase 0.7.2: dropped `near_below_emas`.

    Per the §3.10 strategy audit: `near_below_emas` (EMA proximity ≤ 0.1)
    fired on 84.6% of bars — the same "free score" pathology momentum
    had with stoch_rsi_not_overbought. Removing it tightens score
    distribution: bars in the meandering middle of the EMA stack no
    longer get a free contribution to score on top of their other
    conditions.

    `call_rsi_range` defaults to the Tier-B universal constant; callers
    that have a ticker in scope should pass the Tier-A resolved range
    via `lib.strategies.calibration.get_call_rsi_range(ticker)`.
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Down", 0) >= CONSECUTIVE_PERIODS:
        score += 1
        conditions.append("consecutive_down")

    rsi = row.get(_rsi_col_name(), 50.0)
    if call_rsi_range[0] < rsi < call_rsi_range[1]:
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


def _check_put_conditions(
    row: pd.Series,
    put_rsi_range: tuple[float, float] = PUT_RSI_RANGE,
) -> tuple[int, list[str]]:
    """Phase 0.7.2 mirror: dropped `near_above_emas` (free score).

    Track A G.P0.12 (audit 2026-05-08): `above_vwap` is REMOVED from
    PUT scoring. Across SPY/IWM/QQQ over 90 days the audit measured
    `above_vwap`-marked PUT signals as -16.1pp (QQQ), -11.7pp (IWM),
    and -9.9pp (SPY) win-rate vs no-above_vwap PUTs — i.e. the factor
    is ANTI-correlated with PUT success and was dragging the strategy
    into negative-EV territory. Momentum's `above_vwap` (CALL-direction)
    is a separate code path and is untouched.

    Per-ticker drops (G.P0.13) are applied by the caller via
    `_apply_disabled_conditions(score, conditions, ticker)` after this
    function returns — that keeps the scoring math and the per-ticker
    overrides separate.

    `put_rsi_range` defaults to the Tier-B universal constant; callers
    that have a ticker in scope should pass the Tier-A resolved range
    via `lib.strategies.calibration.get_put_rsi_range(ticker)`.
    """
    score = 0
    conditions: list[str] = []

    if row.get("Consecutive_Up", 0) >= CONSECUTIVE_PERIODS:
        score += 1
        conditions.append("consecutive_up")

    rsi = row.get(_rsi_col_name(), 50.0)
    if put_rsi_range[0] < rsi < put_rsi_range[1]:
        score += 1
        conditions.append("rsi_overbought_zone")

    # `above_vwap` REMOVED — Track A G.P0.12.

    if row.get("StochRSI_K", 50.0) > STOCH_RSI_OVERBOUGHT:
        score += 1
        conditions.append("stoch_rsi_overbought")

    if int(row.get("Broke_Prev_Day_Low", 0) or 0) == 1:
        score += 1
        conditions.append("level_break_pdl")

    return score, conditions


def _apply_disabled_conditions(
    score: int,
    conditions: list[str],
    ticker: Optional[str],
) -> tuple[int, list[str]]:
    """Filter out per-ticker disabled conditions before MIN_CONDITIONS gate.

    Reads the disabled list from `exit_config_overrides.disabled_conditions`
    (PR-E1 schema). Returns the filtered (score, conditions) tuple.

    For IWM/QQQ the audit recommends dropping `stoch_rsi_overbought` and
    `rsi_overbought_zone` from MR PUT scoring (Track A G.P0.13). SPY's
    PUT factor mix was acceptable so it gets no per-ticker drops.

    `ticker=None` → no-op pass-through (keeps test/legacy callers working).
    """
    if not ticker or not conditions:
        return score, conditions

    from lib.strategies.exit_config_overrides import get_disabled_conditions
    disabled = get_disabled_conditions(ticker)
    if not disabled:
        return score, conditions

    kept = [c for c in conditions if c not in disabled]
    return len(kept), kept


class MeanReversionStrategy(Strategy):
    """Mean-reversion: fade overextensions, buy oversold dips."""
    name = "mean_reversion"

    def evaluate(
        self,
        row: pd.Series,
        *,
        call_rsi_range: tuple[float, float] = CALL_RSI_RANGE,
        put_rsi_range: tuple[float, float] = PUT_RSI_RANGE,
        ticker: Optional[str] = None,
    ) -> Optional[Signal]:
        """Evaluate one bar.

        `call_rsi_range` / `put_rsi_range` default to Tier-B universal
        constants. The signal_monitor caller resolves Tier-A values via
        `lib.strategies.calibration` and passes them in per-ticker.

        `ticker` (optional): when provided, per-ticker disabled conditions
        from `exit_config_overrides.disabled_conditions` are removed from
        the score before the MIN_CONDITIONS gate. Track A G.P0.13.
        """
        # Skip warmup bars where indicators are still NaN.
        if pd.isna(row.get(_rsi_col_name())):
            return None
        if pd.isna(row.get("StochRSI_K")):
            return None

        call_score, call_conds = _check_call_conditions(row, call_rsi_range)
        put_score,  put_conds  = _check_put_conditions(row, put_rsi_range)
        # Per-ticker drops applied AFTER scoring so the inline scoring
        # math stays simple. No-op when ticker=None.
        call_score, call_conds = _apply_disabled_conditions(call_score, call_conds, ticker)
        put_score,  put_conds  = _apply_disabled_conditions(put_score, put_conds, ticker)

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
