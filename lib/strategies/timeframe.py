"""Phase 1 — assign a timeframe tag to every signal at fire time.

Different signals work on different timeframes — a 5m scalp setup, a
15m breakout, and a 60m trend-continuation are not the same trade.
Currently the system fires them all the same way (with one global
time stop). Tagging gives the consumer (Discord embed, exit logic,
post-mortem) the predicted holding-period horizon so trade management
can match the signal class.

Public API:
    assign_timeframe(...) -> tuple[str, int]   # (tag, expected_hold_min)

This module is a *pure helper*: no I/O, no DB. The live signal monitor
calls it once per fire after conditions are evaluated.

⚠ Heuristic notes:

The mapping below is a **documented placeholder** based on first
principles (volatility regime + condition strength + signal type).
It WILL be refined empirically in a follow-up phase using
`signal_metrics.best_tf` once enough data accumulates — that table
records which timeframe ACTUALLY classified CLEAN_HIT per signal.
The follow-up will compute condition-set → best-tf correlations
and replace the rule chain below with the data-driven mapping.

Until then the rules are:

  * High volatility (RVOL ≥ 2× or ATR_5m ≥ 0.4%) with strong
    confirmation (≥4 conditions met) → 15m
  * High volatility, weaker confirmation → 30m
  * Low volatility (RVOL < 1×) → 60m
  * Mean-reversion signals (consecutive_down, oversold, below_*) → 30m
  * Momentum signals (consecutive_up, breakout, above_*) → 15m
  * Default fall-through → 30m

These are sensible defaults; they are NOT empirically validated.
"""
from __future__ import annotations

from typing import Optional


# Timeframe → expected holding period (minutes).
# expected_hold_min is the upper bound of the bucket — Phase 2's
# outcome-adaptive cooldown will use this as the time-stop default
# unless the bar's MFE has already realized.
_HOLD_MIN_BY_TAG: dict[str, int] = {
    "5m":   5,
    "15m":  15,
    "30m":  30,
    "60m":  60,
    "90m":  90,
    "120m": 120,
    "240m": 240,
}

VALID_TAGS: tuple[str, ...] = tuple(_HOLD_MIN_BY_TAG.keys())


# Threshold constants — Tier C (universal, structural). Locked in
# code rather than ticker_calibration because the heuristic is
# global pending the empirical refinement phase.
HIGH_RVOL: float = 2.0           # 2× normal volume = elevated activity
HIGH_ATR_5M_PCT: float = 0.40    # 0.4% 5-min ATR = volatile session
LOW_RVOL: float = 1.0            # below-average volume = quiet
STRONG_CONFIRMATION: int = 4     # 4+ conditions out of 5 = strong


def _is_mean_reversion(conditions_met: list[str]) -> bool:
    """Heuristic: any condition that names a 'down' or 'oversold' or
    'below' state suggests the strategy is fading a move (mean-rev)."""
    return any(
        ("consecutive_down" in c)
        or ("oversold" in c)
        or c.startswith("below_")
        or c.startswith("near_below_")
        for c in conditions_met
    )


def _is_momentum(conditions_met: list[str]) -> bool:
    """Heuristic: any condition that names an 'up' or 'breakout' or
    'above' state suggests the strategy is riding strength (momentum)."""
    return any(
        ("consecutive_up" in c)
        or ("breakout" in c)
        or c.startswith("above_")
        or c.startswith("near_above_")
        for c in conditions_met
    )


def assign_timeframe(
    conditions_met: list[str],
    *,
    rsi: Optional[float] = None,
    rvol: Optional[float] = None,
    atr_5m_pct: Optional[float] = None,
) -> tuple[str, int]:
    """Predict the timeframe horizon at signal fire time.

    Args:
        conditions_met: list of fired-condition names from the
            strategy (e.g. ['consecutive_down', 'rsi_oversold_zone']).
        rsi:        14-period RSI at the entry bar (0-100), or None.
        rvol:       Relative volume vs typical (1.0 = average), or None.
        atr_5m_pct: 5-minute ATR as fraction of price (0.005 = 0.5%),
                    or None.

    Returns:
        (timeframe_tag, expected_hold_min) — both never None. The tag
        is one of VALID_TAGS; expected_hold_min is the bucket's upper
        bound minute count.

    Inputs may be None for missing indicator values (warmup bars,
    incomplete enrichment) — the function falls back to safe defaults.
    """
    conds = list(conditions_met or [])
    n_conds = len(conds)

    rvol_v = float(rvol) if rvol is not None else 1.0
    atr_v = float(atr_5m_pct) if atr_5m_pct is not None else 0.0

    high_vol = (rvol_v >= HIGH_RVOL) or (atr_v >= HIGH_ATR_5M_PCT / 100.0)
    low_vol = rvol_v < LOW_RVOL

    if high_vol and n_conds >= STRONG_CONFIRMATION:
        return ("15m", _HOLD_MIN_BY_TAG["15m"])
    if high_vol:
        return ("30m", _HOLD_MIN_BY_TAG["30m"])
    if low_vol:
        return ("60m", _HOLD_MIN_BY_TAG["60m"])
    if _is_mean_reversion(conds):
        return ("30m", _HOLD_MIN_BY_TAG["30m"])
    if _is_momentum(conds):
        return ("15m", _HOLD_MIN_BY_TAG["15m"])
    return ("30m", _HOLD_MIN_BY_TAG["30m"])


def assign_timeframe_for_backfill(
    strategy: Optional[str],
    signal_strength: Optional[int],
    atr_5m_pct: Optional[float] = None,
) -> tuple[str, int]:
    """Approximate timeframe tag for HISTORICAL rows that lack live RVOL.

    historical_signals stores conditions_met as a count string (e.g.
    '4/5'), not the live monitor's granular list, and never persists
    RVOL. The retrospective backfill therefore can't use the full live
    heuristic. This function uses only what's available historically:

      * strategy           — 'momentum' or 'mean_reversion'
      * signal_strength    — 3..5 (count of conditions met)
      * atr_5m_pct         — joined from signal_metrics if present

    Tier structure mirrors the live heuristic:
      * High vol + strong confirmation (signal_strength >= 4) → 15m
      * High vol, weaker confirmation                          → 30m
      * Mean-reversion strategy at avg vol                     → 30m
      * Momentum strategy at avg vol                           → 15m
      * Default / unknown                                      → 30m

    Documented as APPROXIMATE — the live monitor's tags will be more
    precise. When a future phase ships the empirically-derived
    heuristic, this function can be replaced with a backfill that
    consumes more historical fields (joined indicator snapshots).
    """
    high_vol = (
        atr_5m_pct is not None and atr_5m_pct >= HIGH_ATR_5M_PCT / 100.0
    )
    strong = (signal_strength or 0) >= STRONG_CONFIRMATION

    if high_vol and strong:
        return ("15m", _HOLD_MIN_BY_TAG["15m"])
    if high_vol:
        return ("30m", _HOLD_MIN_BY_TAG["30m"])
    if strategy == "mean_reversion":
        return ("30m", _HOLD_MIN_BY_TAG["30m"])
    if strategy == "momentum":
        return ("15m", _HOLD_MIN_BY_TAG["15m"])
    return ("30m", _HOLD_MIN_BY_TAG["30m"])


__all__ = [
    "assign_timeframe",
    "assign_timeframe_for_backfill",
    "VALID_TAGS",
    "HIGH_RVOL",
    "HIGH_ATR_5M_PCT",
    "LOW_RVOL",
    "STRONG_CONFIRMATION",
]
