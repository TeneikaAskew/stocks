"""Lightweight FTFC weighted score for the exec backtest variant 1.

We need a per-trigger-bar FTFC alignment score in [-1, +1] that:
  - Uses ONLY COMPLETED higher-TF bars (no lookahead).
  - Weighted by `FTFC_WEIGHTS` from `strat_config`.
  - Computed deterministically from the 1m bars we already loaded.

The classification rule matches `lib/strat.py:StratClassifier.classify_series`:
  2U if higher_high & ~lower_low → +1
  2D if ~higher_high & lower_low → -1
  1 / 3 / X → 0

This is intentionally simpler than `strat_ftfc_assemble.py` (which uses
per-TF calibrated probabilities) because:
  - This backtest only uses FTFC as a hard filter, not a fine signal.
  - Computing per-TF predictions per trigger bar would require running
    SIX models per cell — out of scope for a single-cell variant test.
  - The spec calls this variant "FTFC alignment filter (require FTFC
    weighted score ≥ 0.5)" — strat-candle-based alignment is the
    standard meaning.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from gcp.research.strat_engine.strat_config import FTFC_WEIGHTS

log = logging.getLogger(__name__)


# Resample rules for pandas .resample on a UTC DatetimeIndex.
# Use ET origin so 4h aligns to 09:30 ET sessions — though for FTFC we
# only need 15m, 30m, 60m, and 4h here. 5m is the trigger cell and would
# self-reference.
RESAMPLE_RULES = {
    "5m": "5min", "15m": "15min", "30m": "30min", "60m": "60min", "4h": "4h",
}


def _classify(o: pd.Series, h: pd.Series, l: pd.Series) -> pd.Series:
    """Per-bar Strat classification → numeric: +1 (2U) / -1 (2D) / 0 else."""
    higher_high = h > h.shift(1)
    lower_low = l < l.shift(1)
    out = pd.Series(0, index=h.index, dtype=float)
    out[higher_high & ~lower_low] = 1.0
    out[~higher_high & lower_low] = -1.0
    return out


def build_ftfc_lookup(m1_bars: pd.DataFrame,
                      timeframes=("15m", "30m", "60m")) -> pd.DataFrame:
    """Pre-compute per-TF classifications.

    Returns DataFrame indexed by UTC pd.DatetimeIndex (the 1m clock),
    columns = per-TF numeric classification (shift(1) so the value at
    timestamp t is the LAST COMPLETED higher-TF bar). NaN where no
    completed bar exists yet.

    For each higher TF, the resampled bar at time `T` covers
    [T, T+TF_min). We use closed='left', label='left' (pandas default for
    fixed offsets), then shift(1) so the value at the 1m bar with ts=T
    is the classification of the higher-TF bar that ENDED at T (i.e.
    the bar starting at T-TF).
    """
    res = {}
    for tf in timeframes:
        rule = RESAMPLE_RULES[tf]
        agg = m1_bars.resample(rule, label="left", closed="left").agg({
            "Open": "first", "High": "max", "Low": "min", "Close": "last",
        }).dropna()
        cls = _classify(agg["Open"], agg["High"], agg["Low"])
        cls = cls.shift(1)  # ONLY use completed bars
        # Forward-fill into the 1m clock
        res[tf] = cls.reindex(m1_bars.index, method="ffill")
    return pd.DataFrame(res, index=m1_bars.index)


def ftfc_score_at(lookup: pd.DataFrame, ts: pd.Timestamp,
                  weights: Optional[Dict[str, float]] = None) -> float:
    """Return weighted FTFC score in [-1, +1] for a given UTC timestamp.

    Uses pandas Index.searchsorted-style lookup: forward-fills from the
    most recent 1m bar at or before `ts`. NaNs ignored in the weight
    denominator.
    """
    if weights is None:
        weights = FTFC_WEIGHTS
    if ts not in lookup.index:
        # Find the most recent index <= ts (asof lookup)
        try:
            idx_pos = lookup.index.get_indexer([ts], method="ffill")[0]
        except Exception:
            return float("nan")
        if idx_pos < 0:
            return float("nan")
        row = lookup.iloc[idx_pos]
    else:
        row = lookup.loc[ts]
    num = 0.0
    den = 0.0
    for tf, val in row.items():
        w = weights.get(tf, 0.0)
        if w == 0 or pd.isna(val):
            continue
        num += val * w
        den += w
    if den == 0:
        return float("nan")
    return float(num / den)


def ftfc_scores_for_setups(lookup: pd.DataFrame,
                            timestamps: pd.DatetimeIndex,
                            weights: Optional[Dict[str, float]] = None) -> pd.Series:
    """Batched version of ftfc_score_at — much faster than a Python loop
    for large prediction frames."""
    if weights is None:
        weights = FTFC_WEIGHTS
    aligned = lookup.reindex(timestamps, method="ffill")
    num = pd.Series(0.0, index=aligned.index)
    den = pd.Series(0.0, index=aligned.index)
    for tf in aligned.columns:
        w = weights.get(tf, 0.0)
        if w == 0:
            continue
        col = aligned[tf]
        valid = col.notna()
        num.loc[valid] += col.loc[valid] * w
        den.loc[valid] += w
    score = num / den.replace(0.0, np.nan)
    return score
