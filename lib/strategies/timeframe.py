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


# ── Bucketization helpers (mirrored in scripts/analyze_timeframe_heuristic.py) ─

def _bucket_atr(atr_5m_pct: Optional[float]) -> str:
    """3 ATR tiers + unknown sentinel.
    Identical to the bucketization used to build EMPIRICAL_LOOKUP."""
    if atr_5m_pct is None:
        return "unknown"
    a = float(atr_5m_pct)
    if a != a:    # NaN
        return "unknown"
    if a >= HIGH_ATR_5M_PCT / 100.0:
        return "high"
    if a <= 0.001:
        return "low"
    return "avg"


def _bucket_rsi(rsi: Optional[float]) -> str:
    """3 RSI zones + unknown sentinel.
    Identical to the bucketization used to build EMPIRICAL_LOOKUP."""
    if rsi is None:
        return "unknown"
    r = float(rsi)
    if r != r:    # NaN
        return "unknown"
    if r < 30:
        return "low"
    if r > 70:
        return "high"
    return "mid"


# ── Empirical lookup table (data-driven heuristic) ─────────────────────────────
#
# Auto-generated by scripts/analyze_timeframe_heuristic.py against the
# full historical_signals × signal_metrics join (91,831 rows as of
# 2026-05-02). Methodology: max_clean_rate_min_15m — for each
# (strategy, signal_strength, atr_bucket, rsi_bucket) bucket, picks
# the timeframe ≥ 15m with the highest CLEAN_HIT rate.
#
# Holdout validation (PRs #218 + #219 + #221):
#   * Empirical heuristic: 91.51% clean-hit rate
#   * Placeholder heuristic: 83.31% clean-hit rate
#   * Δ = +8.20pp on 18,366-row holdout
#   * 4-feature better than 5-feature (per-ticker hurts by 0.12pp)
#
# Cold-start: buckets not in this dict (e.g. mean_reversion, which the
# research-pipeline iterator hasn't been run for yet) fall back to the
# placeholder tier defaults below — a safe, sensible default.
#
# Re-train cadence: weekly during early ops, when CLEAN_HIT threshold
# changes, or after 30+ days of new signal_metrics data.
EMPIRICAL_LOOKUP: dict[tuple[str, int, str, str], str] = {
    ("momentum", 3, "avg",     "high"): "60m",
    ("momentum", 3, "avg",     "low"):  "60m",
    ("momentum", 3, "avg",     "mid"):  "60m",
    ("momentum", 3, "high",    "high"): "60m",
    ("momentum", 3, "high",    "low"):  "60m",
    ("momentum", 3, "high",    "mid"):  "60m",
    ("momentum", 3, "low",     "high"): "60m",
    ("momentum", 3, "low",     "low"):  "60m",
    ("momentum", 3, "low",     "mid"):  "60m",
    ("momentum", 3, "unknown", "high"): "60m",
    ("momentum", 3, "unknown", "low"):  "60m",
    ("momentum", 3, "unknown", "mid"):  "60m",
    ("momentum", 4, "avg",     "high"): "60m",
    ("momentum", 4, "avg",     "low"):  "60m",
    ("momentum", 4, "avg",     "mid"):  "60m",
    ("momentum", 4, "high",    "high"): "30m",
    ("momentum", 4, "high",    "low"):  "240m",
    ("momentum", 4, "high",    "mid"):  "60m",
    ("momentum", 4, "low",     "high"): "60m",
    ("momentum", 4, "low",     "low"):  "60m",
    ("momentum", 4, "low",     "mid"):  "60m",
    ("momentum", 4, "unknown", "high"): "15m",
    ("momentum", 4, "unknown", "low"):  "60m",
    ("momentum", 4, "unknown", "mid"):  "60m",
    ("momentum", 5, "avg",     "mid"):  "60m",
    ("momentum", 5, "high",    "mid"):  "60m",
    ("momentum", 5, "low",     "mid"):  "60m",
    ("momentum", 5, "unknown", "mid"):  "60m",
}


def _placeholder_assign(
    strategy: Optional[str],
    signal_strength: Optional[int],
    atr_5m_pct: Optional[float],
) -> tuple[str, int]:
    """Original placeholder heuristic — kept as cold-start fallback.

    Uses the tier structure that pre-dates the empirical lookup:
    high vol + strong → 15m, mean-rev → 30m, momentum → 15m, default
    → 30m. Holdout clean-rate: 83.31%.
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


def assign_timeframe_for_backfill(
    strategy: Optional[str],
    signal_strength: Optional[int],
    atr_5m_pct: Optional[float] = None,
    entry_rsi: Optional[float] = None,
) -> tuple[str, int]:
    """Empirical timeframe tag for HISTORICAL rows that lack live RVOL.

    Consults `EMPIRICAL_LOOKUP` (data-driven from 91,831-row holdout
    analysis, +8.2pp better than placeholder) using a 4-feature
    bucket: (strategy, signal_strength, atr_bucket, rsi_bucket).

    Cold-start (bucket not in lookup, e.g. mean_reversion which the
    research iterator hasn't been run for yet) falls back to the
    placeholder tier structure — `_placeholder_assign`.

    Re-train cadence: see EMPIRICAL_LOOKUP module-level comment.
    """
    bucket = (
        str(strategy or "unknown"),
        int(signal_strength or 0),
        _bucket_atr(atr_5m_pct),
        _bucket_rsi(entry_rsi),
    )
    tf = EMPIRICAL_LOOKUP.get(bucket)
    if tf is not None:
        return (tf, _HOLD_MIN_BY_TAG[tf])
    # Cold start — bucket the empirical analysis didn't see. Most common
    # case: mean_reversion fires (analyzed dataset only had momentum).
    return _placeholder_assign(strategy, signal_strength, atr_5m_pct)


__all__ = [
    "assign_timeframe",
    "assign_timeframe_for_backfill",
    "EMPIRICAL_LOOKUP",
    "VALID_TAGS",
    "HIGH_RVOL",
    "HIGH_ATR_5M_PCT",
    "LOW_RVOL",
    "STRONG_CONFIRMATION",
]
