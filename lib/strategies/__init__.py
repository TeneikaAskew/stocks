"""Phase 0.8 — lib/strategies/ package.

Single canonical signal-evaluation path. Replaces the dual-pipeline
mess where lib/signals.py held mean-reversion logic and
lib/trading_analysis.py:MarketAnalyzer.generate_technical_signals
held momentum logic with different output schemas.

Public API:
    from lib.strategies import (
        Signal,           # unified output dataclass
        Strategy,         # abstract base
        MOMENTUM,         # singleton MomentumStrategy()
        MEAN_REVERSION,   # singleton MeanReversionStrategy()
        ALL,              # [MOMENTUM, MEAN_REVERSION]
        get_strategy,     # by name
    )

Both strategies are stateless and thread-safe — they can run in
parallel against the same enriched DataFrame without contention.
This is what makes Phase 3's multi-timeframe parallel evaluator
trivial to implement.

See docs/plans/SIGNAL_QUALITY_TEST_PLAN.md Phase 0.8 for the full
spec including the three-tier configuration model.
"""
from __future__ import annotations

from .base import Signal, Strategy
from .momentum import MomentumStrategy
from .mean_reversion import MeanReversionStrategy

MOMENTUM: Strategy = MomentumStrategy()
MEAN_REVERSION: Strategy = MeanReversionStrategy()
ALL: list[Strategy] = [MOMENTUM, MEAN_REVERSION]

_BY_NAME: dict[str, Strategy] = {
    "momentum": MOMENTUM,
    "mean_reversion": MEAN_REVERSION,
}


def get_strategy(name: str) -> Strategy:
    """Look up a strategy by canonical name. Raises KeyError on unknown."""
    if name not in _BY_NAME:
        raise KeyError(
            f"unknown strategy {name!r}; expected one of {list(_BY_NAME)}"
        )
    return _BY_NAME[name]


__all__ = [
    "Signal",
    "Strategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "MOMENTUM",
    "MEAN_REVERSION",
    "ALL",
    "get_strategy",
]
