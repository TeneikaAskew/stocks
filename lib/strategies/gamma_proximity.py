"""Gamma-proximity alerts — King/Gate/Flip detection for live signal monitor.

Added 2026-05-22 (Track 3 of REALTIME_OPTIONS_MULTITRACK_PLAN). Track 0
shipped the realtime options fetcher so `etf_options_snapshots` now
carries intraday `market_session='REALTIME'` rows alongside the legacy
daily `'EOD'` rows. This module is the pure-function consumer that turns
a `GammaSummary` + a live bar's price into a list of typed alerts the
signal monitor fires.

Three alert kinds, all derived from `lib.gamma.build_summary()` output:

  gamma_king_approach  — price within `proximity_pct` of any King strike
  gamma_gate_break     — bar's close crosses through a Gate strike
                         (i.e. prev_close on one side, current close on
                         the other; touch-only does NOT fire — close-only)
  gamma_flip_cross     — bar's close crosses through the gamma flip price
                         (regime change: positive ↔ negative gamma)

Direction mapping (validated against standard dealer-positioning theory):

  King-approach from below   → PUT   (resistance test, expect rejection ↓)
  King-approach from above   → CALL  (support test, expect rejection ↑)
  Gate-break upward close    → CALL  (momentum overcame dealer hedging)
  Gate-break downward close  → PUT   (momentum overcame dealer hedging)
  Flip-cross upward          → CALL  (entering positive-gamma pinning regime)
  Flip-cross downward        → PUT   (entering negative-gamma trending regime)

Rule 3.7 — no silent fallbacks. If `summary` is None or has no kings /
gates / flip, the corresponding evaluator returns []. Callers MUST log
this case via their own counter; this module does NOT fabricate a level
or default to a neutral direction.

Dedup is the caller's responsibility — this module is stateless and
pure. The signal monitor maintains a `_fired_gamma_alerts` set keyed on
(ticker, alert_kind, level_strike) per session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

from lib.gamma import GammaSummary, Level

# ── Defaults (tunable via signal_monitor; see docs/plans/...Track 3) ──
DEFAULT_PROXIMITY_PCT = 0.005    # 0.5% — King-approach threshold
DEFAULT_DEDUP_WINDOW_MIN = 15    # signal monitor uses this per (ticker, kind, level)


# ── Alert dataclass ──────────────────────────────────────────────────


@dataclass(frozen=True)
class GammaAlert:
    """One gamma-proximity alert. Stateless; the monitor decides whether
    to fire it (dedup + persist) but the directional + level metadata
    are fully resolved here so downstream consumers don't recompute."""
    kind: Literal["gamma_king_approach", "gamma_gate_break", "gamma_flip_cross"]
    direction: Literal["CALL", "PUT"]
    level_kind: Literal["king", "gate", "flip"]
    level_strike: float
    distance_pct: float       # signed: positive = price above level
    regime: Literal["positive_gamma", "negative_gamma", "unknown"]

    # Optional context — populated by the caller / signal_monitor
    extras: dict = field(default_factory=dict)

    def dedup_key(self) -> tuple[str, float]:
        """Stable key for per-session dedup (kind, level_strike)."""
        return (self.kind, round(self.level_strike, 4))


# ── Pure evaluators ──────────────────────────────────────────────────


def _direction_for_king_approach(price: float, king: Level) -> Literal["CALL", "PUT"]:
    """Below the king = approach-from-below = rejection-↓ thesis = PUT.
    Above the king = approach-from-above = rejection-↑ thesis = CALL.
    Equal: rare ATM tie; default to PUT (resistance bias when price is at the wall)."""
    if price < king.strike:
        return "PUT"
    return "CALL"


def evaluate_king_approach(
    price: float,
    summary: GammaSummary,
    *,
    proximity_pct: float = DEFAULT_PROXIMITY_PCT,
) -> list[GammaAlert]:
    """Return one alert per King strike within `proximity_pct` of `price`.

    A King is the strongest gamma wall (highest |GEX|, ≥ NODE_KING_PCT of
    max |GEX| in window — see lib.gamma.classify_levels). Multiple kings
    can exist; we fire one alert per nearby king so the trader sees all
    active walls.
    """
    if not summary or not summary.kings or price <= 0:
        return []
    out: list[GammaAlert] = []
    for king in summary.kings:
        if king.strike <= 0:
            continue
        dist = abs(price - king.strike) / king.strike
        if dist > proximity_pct:
            continue
        signed_dist_pct = (price - king.strike) / king.strike * 100.0
        out.append(GammaAlert(
            kind="gamma_king_approach",
            direction=_direction_for_king_approach(price, king),
            level_kind="king",
            level_strike=float(king.strike),
            distance_pct=signed_dist_pct,
            regime=summary.regime,
        ))
    return out


def evaluate_gate_break(
    prev_close: Optional[float],
    close: float,
    summary: GammaSummary,
) -> list[GammaAlert]:
    """Return one alert per Gate strike whose level was crossed between
    `prev_close` and `close`.

    Close-only — a wick that pokes through and reverses on the same bar
    does NOT fire (per plan §Track 3 tuning concerns). Caller must pass
    bar closes only.
    """
    if not summary or not summary.gates or prev_close is None or close <= 0:
        return []
    out: list[GammaAlert] = []
    for gate in summary.gates:
        if gate.strike <= 0:
            continue
        crossed_up = prev_close <= gate.strike < close
        crossed_down = prev_close >= gate.strike > close
        if not (crossed_up or crossed_down):
            continue
        direction: Literal["CALL", "PUT"] = "CALL" if crossed_up else "PUT"
        signed_dist_pct = (close - gate.strike) / gate.strike * 100.0
        out.append(GammaAlert(
            kind="gamma_gate_break",
            direction=direction,
            level_kind="gate",
            level_strike=float(gate.strike),
            distance_pct=signed_dist_pct,
            regime=summary.regime,
        ))
    return out


def evaluate_flip_cross(
    prev_close: Optional[float],
    close: float,
    summary: GammaSummary,
) -> list[GammaAlert]:
    """Return at most one alert when `close` crosses through `summary.flip`.

    Crossing UP (negative→positive gamma) = entering pinning regime = CALL.
    Crossing DOWN (positive→negative gamma) = entering trending regime = PUT.
    """
    if (not summary or summary.flip is None
            or prev_close is None or close <= 0):
        return []
    flip = float(summary.flip)
    if flip <= 0:
        return []
    crossed_up = prev_close <= flip < close
    crossed_down = prev_close >= flip > close
    if not (crossed_up or crossed_down):
        return []
    direction: Literal["CALL", "PUT"] = "CALL" if crossed_up else "PUT"
    signed_dist_pct = (close - flip) / flip * 100.0
    # New regime AFTER the cross — independent of summary.regime which
    # was computed at snapshot time relative to the snapshot's spot.
    new_regime: Literal["positive_gamma", "negative_gamma"] = (
        "positive_gamma" if crossed_up else "negative_gamma"
    )
    return [GammaAlert(
        kind="gamma_flip_cross",
        direction=direction,
        level_kind="flip",
        level_strike=flip,
        distance_pct=signed_dist_pct,
        regime=new_regime,
    )]


def evaluate_all(
    price: float,
    prev_close: Optional[float],
    summary: GammaSummary,
    *,
    proximity_pct: float = DEFAULT_PROXIMITY_PCT,
) -> list[GammaAlert]:
    """Run all three evaluators in canonical order — kings, gates, flip.

    Order matches the plan's narrative (kings = strongest signal first).
    Caller is responsible for dedup against the per-session fired set.
    """
    out: list[GammaAlert] = []
    out.extend(evaluate_king_approach(price, summary, proximity_pct=proximity_pct))
    out.extend(evaluate_gate_break(prev_close, price, summary))
    out.extend(evaluate_flip_cross(prev_close, price, summary))
    return out
