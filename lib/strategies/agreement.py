"""Phase 1.6 — strategy-agreement detection.

When both `MomentumStrategy` and `MeanReversionStrategy` fire on the
same bar AND target the same direction, that's a high-conviction
"stacked" signal — historically only ~21% of overlapping fires.

This module is a *pure helper*: no database access, no I/O. The live
signal monitor (Phase 1.6 follow-up) will call `detect_agreement` once
per bar after running both strategies in parallel, then persist the
returned payload to `signal_alerts.strategy_agreement` and use the
composite score to rank Discord embed output.

Public API:
    detect_agreement(momentum, mean_reversion) -> Optional[dict]
    composite_score(signals)                   -> float
"""
from __future__ import annotations

from typing import Optional

from .base import Signal


# How much to boost a stacked-agreement signal over its strongest leg.
# Tier C (universal, structural) — the entire point of the agreement
# feature is to surface stacked signals above any solo signal of equal
# strength, so this value lives in the code, not in ticker_calibration.
AGREEMENT_BONUS: float = 1.0


def detect_agreement(
    momentum: Optional[Signal],
    mean_reversion: Optional[Signal],
) -> Optional[dict]:
    """Return the agreement payload when both strategies fire same direction.

    Inputs are the per-bar outputs from `MomentumStrategy.evaluate(row)`
    and `MeanReversionStrategy.evaluate(row)` — either may be None when
    that strategy didn't fire on this bar.

    Returns:
        - None when fewer than 2 strategies fired, OR when both fired
          but disagree on direction (CALL vs PUT). Disagreement is
          *informative noise* — the live monitor still emits both solo
          signals, but they don't get the stacked-agreement bonus.
        - A dict with the agreement payload when both fired same way.

    The dict shape matches the `signal_alerts.strategy_agreement` JSONB
    column documented in `gcp/schema.sql`.
    """
    fired = [s for s in (momentum, mean_reversion) if s is not None]
    if len(fired) < 2:
        return None
    if fired[0].direction != fired[1].direction:
        return None

    # Sort to keep payload key order stable across runs (momentum first
    # alphabetically). Stable order matters for JSONB dedup queries and
    # snapshot-style tests.
    fired_sorted = sorted(fired, key=lambda s: s.strategy)
    # Track D / G.P3.4: include each leg's conditions_met list so post-
    # mortems can answer "which conditions did momentum hit when stacked
    # with mean-reversion" without joining back to the per-strategy
    # tables. Pre-fix the payload only carried `strategies`/`directions`/
    # `base_scores`/`composite_score`, dropping every per-leg condition
    # array. The Python list binds natively to a JSONB array of arrays
    # via the SignalMonitor._persist_signal_alert path (see
    # gcp/database.upsert_dataframe).
    return {
        "agree":           True,
        "strategies":      [s.strategy for s in fired_sorted],
        "directions":      [s.direction for s in fired_sorted],
        "base_scores":     [float(s.base_score) for s in fired_sorted],
        "conditions_met":  [list(s.conditions_met) for s in fired_sorted],
        "composite_score": composite_score(fired_sorted),
    }


def composite_score(signals: list[Signal]) -> float:
    """Composite score for ranking signals in the embed-sort step.

    Rule:
        - Single signal → its base_score (no bonus).
        - Two signals same direction → max(base_scores) + AGREEMENT_BONUS.
        - Two signals opposite directions → max(base_scores) (no bonus).
          Caller chooses which solo signal to surface; agreement bonus
          only applies to actual *agreement*.

    The bonus is additive (not multiplicative) so it's predictable
    across the 0-5 base_score range — a 5.0 stacked signal becomes 6.0,
    a 3.0 stacked signal becomes 4.0. Solo signals never reach 6.0,
    guaranteeing stacked signals sort above solo.
    """
    if not signals:
        return 0.0
    if len(signals) == 1:
        return float(signals[0].base_score)

    directions = {s.direction for s in signals}
    base = max(float(s.base_score) for s in signals)
    if len(directions) == 1:
        return base + AGREEMENT_BONUS
    return base


__all__ = ["detect_agreement", "composite_score", "AGREEMENT_BONUS"]
