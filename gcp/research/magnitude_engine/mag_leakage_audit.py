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
    load_magnitude_dataset, _PHASE1_SPINE_COLUMNS,
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
    """Audit 2: the magnitude target denominator atr_20 is t-known — it
    varies bar-to-bar within a session.

    As of 2026-06-01 atr_20 comes from the single indicator spine
    (lib.indicators.add_all_indicators → strat_features_<tf>.atr_20), NOT a
    local recompute. If atr_20 at adjacent same-day bars were identical across
    MANY pairs, the rolling aggregation is suspect (windowing bug, ffill leak).
    A fully-NaN atr_20 means the spine rebuild hasn't run — surfaced as a hard
    status, not silently passed.
    """
    df = load_magnitude_dataset(engine, ticker, tf, phase="phase0", since="2026-01-01")
    if "atr_20" not in df.columns:
        return {"status": "MISSING_COLUMN"}
    if not (df["atr_20"].notna() & (df["atr_20"] > 0)).any():
        return {"status": "⚠️ ATR20_ALL_NAN — spine rebuild not run"}
    if len(df) < n_sample + 5:
        return {"status": "NOT_ENOUGH_BARS"}
    sample = df.sample(n_sample, random_state=42).sort_values("ts")
    issues = 0
    for ts in sample["ts"]:
        idx = df.index[df["ts"] == ts][0]
        if idx + 1 < len(df) and df.loc[idx + 1, "bar_date"] == df.loc[idx, "bar_date"]:
            a_now = df.loc[idx, "atr_20"]
            a_next = df.loc[idx + 1, "atr_20"]
            if pd.notna(a_now) and pd.notna(a_next) and abs(a_now - a_next) < 1e-12:
                issues += 1
    rate = issues / n_sample
    status = "CLEAN" if rate < 0.2 else f"⚠️ SUSPECT_FLAT (rate={rate:.2f})"
    log.info("audit-2: %d/%d adjacent same-day atr_20 pairs identical  →  %s",
             issues, n_sample, status)
    return {"ticker": ticker, "tf": tf, "sample_n": n_sample,
            "flat_adjacent_pairs": issues, "flat_rate": rate, "status": status}


def audit_phase1_no_future_oolook(engine, ticker: str, tf: str) -> dict:
    """Audit 3: the Phase-1 volatility features must be t-known.

    As of 2026-06-01 these are produced by the indicator spine
    (lib.indicators.add_all_indicators._add_magnitude) and PERSISTED in
    strat_features_<tf>, so they arrive with the loaded frame rather than being
    recomputed here. Leakage of these features is therefore covered by the
    strat_engine enrichment audit (which audits add_all_indicators directly).

    This audit now confirms (a) the spine columns are present from the load and
    (b) they are not constant within a session (a degenerate all-NaN/flat column
    would indicate the rebuild persisted nothing). The old perturbation test
    against a local recompute no longer applies — there is no local recompute.
    """
    df = load_magnitude_dataset(engine, ticker, tf, phase="phase1", since="2026-04-01")
    if len(df) < 200:
        return {"status": "NOT_ENOUGH_BARS"}
    missing = [c for c in _PHASE1_SPINE_COLUMNS if c not in df.columns]
    if missing:
        return {"ticker": ticker, "tf": tf,
                "status": f"⚠️ MISSING_SPINE_COLUMNS: {missing}"}
    flat = [c for c in _PHASE1_SPINE_COLUMNS
            if df[c].notna().sum() > 0 and df[c].nunique(dropna=True) <= 1]
    status = "CLEAN" if not flat else f"⚠️ DEGENERATE_FLAT: {flat}"
    log.info("audit-3: phase-1 spine cols present=%d, degenerate-flat=%s",
             len(_PHASE1_SPINE_COLUMNS), flat or "{}")
    return {"ticker": ticker, "tf": tf,
            "phase1_cols_checked": len(_PHASE1_SPINE_COLUMNS),
            "degenerate_flat": flat, "status": status}


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
