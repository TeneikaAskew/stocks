"""Weighted aggregation of signal scores into a single ranker score.

Pure-Python, no I/O. Takes the dict produced by `signals.py` plus a
weights dict (from alert_config.json) and returns a typed result with
the aggregate score plus per-signal breakdown — every contribution to
the final score is auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalContribution:
    name: str
    available: bool
    score_0_to_1: float
    weight: float
    points: float        # score_0_to_1 × weight (the actual contribution)
    reason: str
    raw: dict = field(default_factory=dict)


@dataclass
class ScoreResult:
    total: float                            # sum of `points` across signals
    max_possible: float                     # if every signal were 1.0
    pct_of_max: float                       # total / max_possible
    breakdown: list[SignalContribution]
    excluded_reason: Optional[str] = None   # set when liquidity (or other
                                            # gate signal) fails

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 3),
            "max_possible": round(self.max_possible, 3),
            "pct_of_max": round(self.pct_of_max, 3),
            "excluded_reason": self.excluded_reason,
            "breakdown": [
                {
                    "name": c.name,
                    "available": c.available,
                    "score_0_to_1": round(c.score_0_to_1, 3),
                    "weight": round(c.weight, 3),
                    "points": round(c.points, 3),
                    "reason": c.reason,
                    "raw": c.raw,
                }
                for c in self.breakdown
            ],
        }


def weighted_score(
    signal_results: dict[str, dict],
    weights: dict[str, float],
    *,
    gate_signal: str = "liquidity",
) -> ScoreResult:
    """Combine per-signal results into a ScoreResult.

    Args:
        signal_results: {signal_name: {available, score_0_to_1, reason, raw}}.
        weights: {signal_name: weight_float}. Signals without a weight
            entry are still recorded in the breakdown but contribute 0.
        gate_signal: name of the binary pass/fail signal that, if it
            returns 0.0, marks the ticker as excluded entirely. Default
            is `liquidity`.
    """
    breakdown: list[SignalContribution] = []
    total = 0.0
    max_possible = 0.0
    excluded_reason: Optional[str] = None

    for name, result in signal_results.items():
        score = float(result.get("score_0_to_1") or 0.0)
        available = bool(result.get("available", False))
        reason = result.get("reason", "")
        raw = result.get("raw") or {}
        weight = float(weights.get(name, 0.0))
        points = score * weight if available else 0.0

        breakdown.append(
            SignalContribution(
                name=name,
                available=available,
                score_0_to_1=score,
                weight=weight,
                points=points,
                reason=reason,
                raw=raw,
            )
        )

        if available and weight > 0:
            total += points
            max_possible += weight

        # Gate: if the gate signal fails (score_0_to_1 == 0 with
        # available=True), the whole ticker is dropped.
        if name == gate_signal and available and score == 0.0:
            excluded_reason = f"{gate_signal} gate failed: {reason}"

    pct_of_max = (total / max_possible) if max_possible > 0 else 0.0
    return ScoreResult(
        total=total,
        max_possible=max_possible,
        pct_of_max=pct_of_max,
        breakdown=breakdown,
        excluded_reason=excluded_reason,
    )


# ---------------------------------------------------------------------------
# Defaults — override via alert_config.json `ranker.weights`
# ---------------------------------------------------------------------------


DEFAULT_WEIGHTS: dict[str, float] = {
    "strat_alignment":               3.0,   # The Strat is the primary signal
    "historical_earnings_reaction":  2.0,
    "iv_signals":                    2.0,
    "has_recent_8k":                 2.0,
    "insider_cluster":               1.5,
    "news_topic_score":              1.5,
    "sentiment_shift":               1.0,
    "is_top_mover_today":            1.0,
    "liquidity":                     0.0,   # gate, not weighted into score
}
