"""Phase 0.8 — Signal dataclass + Strategy abstract base.

Both strategies (`MomentumStrategy`, `MeanReversionStrategy`) implement
this interface so callers can swap strategies at runtime via
`get_strategy(name)` without conditional logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import pandas as pd


@dataclass
class Signal:
    """Unified signal output across all strategies.

    All strategies produce this exact shape regardless of internal
    condition definitions. Schema-stable and JSON-serializable so
    downstream tables (`signal_alerts`, `historical_signals`) can be
    written from any strategy without per-strategy mapping code.
    """
    strategy: Literal["momentum", "mean_reversion"]
    direction: Literal["CALL", "PUT"]
    timestamp: pd.Timestamp
    entry_price: float
    base_score: float
    weighted_score: float
    conditions_met: list[str]

    # Phase 0.7.x — count of CORE-tier conditions met (subset of
    # conditions_met). Stashed so downstream observers (replay,
    # dashboards) can audit "fires with core_count==0" — the load-bearing
    # regression target for the tiered-scoring gate.
    core_count: int = 0

    # Optional indicator snapshots at signal time
    rsi: Optional[float] = None
    rvol: Optional[float] = None
    atr_5m_pct: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    vwap: Optional[float] = None

    # Anything strategy-specific that doesn't fit the canonical fields
    # — kept JSON-serializable for the historical_signals.extra column.
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict representation, JSON-safe."""
        out: dict[str, Any] = {
            "strategy":       self.strategy,
            "direction":      self.direction,
            "timestamp":      self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
            "entry_price":    self.entry_price,
            "base_score":     self.base_score,
            "weighted_score": self.weighted_score,
            "conditions_met": list(self.conditions_met),
            "core_count":     self.core_count,
        }
        for k in ("rsi", "rvol", "atr_5m_pct", "ema9", "ema20", "vwap"):
            v = getattr(self, k)
            if v is not None:
                out[k] = float(v)
        if self.extras:
            out["extras"] = self.extras
        return out


class Strategy:
    """Abstract base class for signal-generation strategies.

    Subclass and override `evaluate(row) -> Optional[Signal]`. The
    default `generate_signals(df)` walks the rows and aggregates.

    Strategies MUST be:
      * Stateless — no instance attributes that change between calls
      * Thread-safe — safe to run in parallel against different DataFrames
      * Pure — same input row produces the same Signal output
    """
    name: str = ""   # subclasses set: 'momentum' | 'mean_reversion'

    def evaluate(self, row: pd.Series) -> Optional[Signal]:
        """Evaluate one bar; return Signal if conditions fire, else None."""
        raise NotImplementedError("subclass must implement evaluate()")

    def generate_signals(self, enriched_df: pd.DataFrame) -> list[Signal]:
        """Walk an indicator-enriched DataFrame and return all firing signals.

        `enriched_df` is the output of `MarketAnalyzer.add_technical_indicators`
        — it carries the indicator columns each strategy expects.
        """
        out: list[Signal] = []
        # Skip the warmup rows where indicators are still NaN.
        for _, row in enriched_df.iterrows():
            sig = self.evaluate(row)
            if sig is not None:
                out.append(sig)
        return out
