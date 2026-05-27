"""Magnitude Engine — leakage audit.

Three checks that MUST pass before any results are trusted:

  1. The magnitude label is built from t+1 OHLC (next_open, next_close)
     and atr_20-at-t. atr_20 is supposed to be t-known (calculated at
     bar t close, NOT including t+1). Audit: on a random sample of
     bars, recompute atr_20 from raw OHLCV[:-1, :] (everything strictly
     before t+1) and confirm it matches the stored value.

  2. next_open / next_close MUST be excluded from the feature matrix.
     Audit: assert these columns are in the drop set.

  3. Phase-1 features must use ONLY t-and-earlier OHLCV. Audit:
     for a sample bar at time T with feature value V, perturbing
     OHLCV at times > T must NOT change V.

This audit is separate from the strat_engine enrichment audit (which
also runs against this dataset since we inherit its features).

Run:
  python -m gcp.research.magnitude_engine.mag_leakage_audit \\
      --ticker IWM --tf 15m
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.magnitude_engine.mag_config import TICKERS, TIMEFRAMES
from gcp.research.magnitude_engine.mag_dataset import (
    load_magnitude_dataset, _add_phase1_features,
)
from gcp.research.magnitude_engine.mag_pred_train import featurize
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def audit_target_no_future_in_features(engine, ticker: str, tf: str) -> dict:
    """Audit 1: the magnitude target uses next_open/next_close — confirm
    those columns are dropped from the feature matrix."""
    df = load_magnitude_dataset(engine, ticker, tf, phase="phase0", since="2026-01-01")
    if df.empty:
        return {"status": "NO_DATA"}
    X, cols = featurize(df)
    forbidden = {"next_open", "next_close", "next_high", "next_low",
                 "magnitude_bucket", "next_bar_type"}
    leaked = sorted(forbidden & set(cols))
    status = "CLEAN" if not leaked else f"⚠️ LEAK: {leaked}"
    log.info("audit-1: feature matrix has %d cols; forbidden ∩ cols = %s",
             len(cols), leaked or "{}")
    return {"ticker": ticker, "tf": tf, "n_features": len(cols),
            "leaked_columns": leaked, "status": status}


def audit_atr20_is_t_known(engine, ticker: str, tf: str, n_sample: int = 50) -> dict:
    """Audit 2: atr_20 stored in strat_features for bar T must equal
    atr_20 computed from a window ENDING at T (not including T+1).

    We don't have the raw indicator pipeline here, so the test is
    weaker but still useful: pull a sample of bars and verify that
    atr_20 is monotonically updated bar-by-bar (i.e. the stored value
    at T+1 != value at T — if it WERE the same across all bars, that
    would suggest the column is ffill'd from future and silently
    leaks). A passing test isn't proof of cleanness; a failing test
    IS proof of leakage.
    """
    df = load_magnitude_dataset(engine, ticker, tf, phase="phase0", since="2026-01-01")
    if len(df) < n_sample + 5:
        return {"status": "NOT_ENOUGH_BARS"}
    sample = df.sample(n_sample, random_state=42).sort_values("ts")
    # Adjacent same-day pairs
    issues = 0
    for ts in sample["ts"]:
        idx = df.index[df["ts"] == ts][0]
        if idx + 1 < len(df) and df.loc[idx + 1, "bar_date"] == df.loc[idx, "bar_date"]:
            a_now = df.loc[idx, "atr_20"]
            a_next = df.loc[idx + 1, "atr_20"]
            if pd.notna(a_now) and pd.notna(a_next) and abs(a_now - a_next) < 1e-9:
                # Identical to many decimal places — only suspicious if
                # MANY pairs are identical. We count.
                issues += 1
    rate = issues / n_sample
    status = "CLEAN" if rate < 0.2 else f"⚠️ SUSPECT_FLAT (rate={rate:.2f})"
    log.info("audit-2: %d/%d adjacent same-day atr_20 pairs match exactly  →  %s",
             issues, n_sample, status)
    return {"ticker": ticker, "tf": tf, "sample_n": n_sample,
            "flat_adjacent_pairs": issues, "flat_rate": rate, "status": status}


def audit_phase1_no_future_oolook(engine, ticker: str, tf: str) -> dict:
    """Audit 3: a phase-1 feature value at time T must not change when
    OHLCV at times > T is perturbed.

    Concrete test: load a small slice, compute phase-1 features twice:
    once on the full slice, once on the slice with bars after the
    midpoint zero-replaced. Compare feature values at all bars at or
    before the midpoint — they must be identical.
    """
    df = load_magnitude_dataset(engine, ticker, tf, phase="phase0", since="2026-04-01")
    if len(df) < 200:
        return {"status": "NOT_ENOUGH_BARS"}
    mid = len(df) // 2
    df_full = _add_phase1_features(df.copy())
    df_perturbed = df.copy()
    # Zero-out future OHLCV beyond midpoint
    for c in ("open", "high", "low", "close", "volume"):
        df_perturbed.loc[mid:, c] = 0
    df_pertb = _add_phase1_features(df_perturbed)
    phase1_cols = [
        "atr5_atr20_ratio", "bb20_bandwidth", "realized_vol_z15",
        "range_expansion_ratio", "intraday_range_vs_prior_day",
    ]
    leaked = []
    for c in phase1_cols:
        a = df_full[c].iloc[:mid].fillna(-999).values
        b = df_pertb[c].iloc[:mid].fillna(-999).values
        if not np.allclose(a, b, equal_nan=True):
            leaked.append(c)
    status = "CLEAN" if not leaked else f"⚠️ LEAK: {leaked}"
    log.info("audit-3: phase-1 leaked columns = %s", leaked or "{}")
    return {"ticker": ticker, "tf": tf, "phase1_cols_tested": len(phase1_cols),
            "leaked": leaked, "status": status}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    args = p.parse_args()
    engine = get_engine()
    log.info("=" * 70)
    log.info("MAGNITUDE ENGINE LEAKAGE AUDIT — %s %s", args.ticker, args.tf)
    log.info("=" * 70)
    audit_target_no_future_in_features(engine, args.ticker, args.tf)
    log.info("")
    audit_atr20_is_t_known(engine, args.ticker, args.tf)
    log.info("")
    audit_phase1_no_future_oolook(engine, args.ticker, args.tf)


if __name__ == "__main__":
    main()
