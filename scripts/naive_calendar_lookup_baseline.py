#!/usr/bin/env python3
"""Naive calendar-lookup baseline for magnitude prediction.

Reviewer 2026-05-28 (post phase_calendar): the phase_calendar PASS is
suspicious because intraday calendar volatility (open/lunch/close, DoW,
FOMC/NFP weeks) is the single most-known and most-priced-in pattern in
intraday trading. Bootstrap-robust ≠ tradeable.

This script asks: can a NAIVE (day-of-week, time-of-day-bucket) lookup
predictor — no model, no bar features, no LightGBM — pass the same four
gates on its own? If yes, the magnitude model is adding zero edge
beyond the calendar lookup table. If no, the model is conditioning on
something beyond the calendar slot and there's incremental signal.

Method:
  1. For each walk-forward fold:
     a. Define train and test windows (same cutoffs as the harness).
     b. Group train bars by (DoW, time_bucket_30m) → empirical class
        distribution per cell.
     c. For each test bar, predict P(EXPLOSIVE) and the full 4-class
        distribution as the historical rate of its (DoW, time_bucket)
        cell. Bars whose calendar cell has no training samples fall
        back to the global train prior.
  2. Apply the same four gates (log-loss-beat, ECE, monotone decisive,
     EXPLOSIVE lift ≥1.5) to the naive predictor's per-fold output.
  3. Print comparison: walk-forward model gates vs naive baseline gates,
     side by side, with per-fold detail.

Usage:
    python -m scripts.naive_calendar_lookup_baseline --ticker IWM --tf 5m
"""
from __future__ import annotations
import argparse
import collections
import io
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import storage as gcs

sys.path.insert(0, str(Path(__file__).parent.parent))
from gcp.database import get_engine
from gcp.research.magnitude_engine.mag_config import (
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_CUTOFFS, MIN_TEST_BARS, ECE_CEILING_BY_TF,
    SUCCESS_BAR_EXPLOSIVE_LIFT_MIN, SUCCESS_BAR_CONFIDENCE_THRESHOLDS,
    GCS_BUCKET_DEFAULT,
)
from gcp.research.magnitude_engine.mag_dataset import load_magnitude_dataset
from gcp.research.magnitude_engine.mag_pred_train import (
    expected_calibration_error, decisive_call_hit_rate, explosive_lift,
)
from sklearn.metrics import log_loss


def _calendar_keys(ts_series: pd.Series, bucket_minutes: int = 30) -> pd.DataFrame:
    """Compute (day_of_week, time_bucket) keys for each timestamp.

    bucket_minutes = 30 → 13 RTH buckets per day × 5 DoW = 65 cells.
    At ~250 trading days per year × 8 training years ≈ 2000 days, that's
    ~30 days of samples per cell — enough for stable rates.
    """
    ts_et = pd.to_datetime(ts_series, utc=True).dt.tz_convert("America/New_York")
    dow = ts_et.dt.dayofweek.values
    minutes_of_day = ts_et.dt.hour.values * 60 + ts_et.dt.minute.values
    bucket = (minutes_of_day // bucket_minutes).astype(int)
    return dow, bucket


def naive_lookup_predict(y_tr: np.ndarray, ts_tr: pd.Series,
                          ts_te: pd.Series,
                          n_classes: int = 4,
                          bucket_minutes: int = 30) -> np.ndarray:
    """Build a (DoW, time_bucket) → class-dist lookup from training data and
    apply it to test data. Returns probability matrix of shape (n_test, n_classes)."""
    dow_tr, bucket_tr = _calendar_keys(ts_tr, bucket_minutes)
    dow_te, bucket_te = _calendar_keys(ts_te, bucket_minutes)

    counts = collections.defaultdict(lambda: np.zeros(n_classes, dtype=np.float64))
    for i in range(len(y_tr)):
        counts[(int(dow_tr[i]), int(bucket_tr[i]))][int(y_tr[i])] += 1.0

    # Cell-level probabilities (no smoothing — sparse cells fall back to prior)
    cell_probs = {}
    for k, v in counts.items():
        s = v.sum()
        if s > 0:
            cell_probs[k] = v / s

    # Global train prior for fallback
    prior = np.bincount(y_tr, minlength=n_classes).astype(np.float64)
    prior = prior / prior.sum() if prior.sum() > 0 else np.ones(n_classes) / n_classes

    out = np.empty((len(ts_te), n_classes), dtype=np.float64)
    fallback_count = 0
    for i in range(len(ts_te)):
        k = (int(dow_te[i]), int(bucket_te[i]))
        if k in cell_probs:
            out[i] = cell_probs[k]
        else:
            out[i] = prior
            fallback_count += 1
    return out, fallback_count


def evaluate_fold(y_tr, y_te, proba_te, tf):
    """Compute the same 4 gates the walk-forward harness uses."""
    classes = list(range(len(LABEL_CLASSES)))
    ll = float(log_loss(y_te, proba_te, labels=classes))
    prior = np.bincount(y_tr, minlength=len(LABEL_CLASSES)).astype(float)
    prior = prior / prior.sum()
    base_proba = np.tile(prior, (len(y_te), 1))
    base_ll = float(log_loss(y_te, base_proba, labels=classes))
    beat = base_ll - ll

    ece, _ = expected_calibration_error(y_te, proba_te, n_bins=10)
    ece_pass = ece <= ECE_CEILING_BY_TF[tf]

    decisive = decisive_call_hit_rate(y_te, proba_te, SUCCESS_BAR_CONFIDENCE_THRESHOLDS)
    accs = [decisive[f"{t:.2f}"]["accuracy"] for t in SUCCESS_BAR_CONFIDENCE_THRESHOLDS]
    clean = [a for a in accs if a is not None]
    monotone = (len(clean) >= 2 and all(b >= a for a, b in zip(clean, clean[1:])))

    explosive = explosive_lift(y_te, proba_te, explosive_idx=LABEL_TO_IDX["EXPLOSIVE"])
    lift = explosive.get("lift")
    lift_pass = lift is not None and lift >= SUCCESS_BAR_EXPLOSIVE_LIFT_MIN

    return {
        "beat": beat, "logloss": ll, "base_logloss": base_ll,
        "ece": ece, "ece_pass": ece_pass,
        "monotone": monotone,
        "lift": lift, "lift_pass": lift_pass,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True, choices=list(TICKERS))
    p.add_argument("--tf", required=True, choices=list(TIMEFRAMES))
    p.add_argument("--bucket-minutes", type=int, default=30,
                   help="Time-bucket granularity (30 = 13 RTH buckets per day)")
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    args = p.parse_args()

    engine = get_engine()
    # Load full dataset for this cell — same query the walk-forward uses
    # but we only need ts + magnitude_bucket. Pull phase0 to avoid the
    # phase-specific feature joins; the target depends only on OHLCV+atr20
    # which are present in phase0.
    print(f"loading magnitude dataset for {args.ticker} {args.tf}...", file=sys.stderr)
    df = load_magnitude_dataset(engine, args.ticker, args.tf, phase="phase0")
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    print(f"loaded {len(df)} rows", file=sys.stderr)

    y_all = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    ts_all = pd.to_datetime(df["ts"], utc=True)
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")

    cutoffs = list(DEFAULT_CUTOFFS)
    folds = []
    for i, cut in enumerate(cutoffs):
        if i + 1 < len(cutoffs):
            test_end = cutoffs[i + 1]
        else:
            test_end = str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        train_end_dt = np.datetime64(cut)
        test_end_dt = np.datetime64(test_end)
        train_mask = bar_dates_arr < train_end_dt
        test_mask = (bar_dates_arr >= train_end_dt) & (bar_dates_arr < test_end_dt)
        if int(test_mask.sum()) < MIN_TEST_BARS:
            folds.append({"fold": f"{cut}..{test_end}", "status": "SKIP_THIN"})
            continue
        y_tr = y_all[train_mask]; y_te = y_all[test_mask]
        ts_tr = ts_all[train_mask]; ts_te = ts_all[test_mask]

        proba_te, fallback_n = naive_lookup_predict(y_tr, ts_tr, ts_te,
                                                     bucket_minutes=args.bucket_minutes)
        r = evaluate_fold(y_tr, y_te, proba_te, args.tf)
        r["fold"] = f"{cut}..{test_end}"
        r["n_train"] = int(len(y_tr))
        r["n_test"] = int(len(y_te))
        r["fallback_n"] = fallback_n
        r["status"] = "OK"
        folds.append(r)

    # Tabulate
    print()
    print("=" * 100)
    print(f"NAIVE CALENDAR-LOOKUP BASELINE  ticker={args.ticker} tf={args.tf}  "
           f"bucket={args.bucket_minutes}min")
    print("=" * 100)
    print(f"\n{'fold':25} {'n_tr':>7} {'n_te':>7} {'beat':>8} "
           f"{'ece':>6} {'ece_p':>5} {'mono':>5} {'lift':>7}")
    print("-" * 100)
    g_pass = {"beat": 0, "ece": 0, "mono": 0, "lift": 0}
    n_ok = 0
    for f in folds:
        if f.get("status") != "OK":
            print(f"{f['fold']:25} {f.get('status','?')}")
            continue
        n_ok += 1
        beat_s = f"{f['beat']:+8.4f}"
        ece_s = f"{f['ece']:6.4f}"
        lift = f["lift"]
        lift_s = f"{lift:7.2f}" if lift is not None else "    —  "
        if f["beat"] > 0: g_pass["beat"] += 1
        if f["ece_pass"]: g_pass["ece"] += 1
        if f["monotone"]: g_pass["mono"] += 1
        if f["lift_pass"]: g_pass["lift"] += 1
        print(f"{f['fold']:25} {f['n_train']:>7d} {f['n_test']:>7d} "
              f"{beat_s:>8} {ece_s:>6} "
              f"{str(f['ece_pass']):>5} {str(f['monotone']):>5} {lift_s:>7}")
    print()
    print(f"GATE COUNTS  (naive predictor only, no model)")
    print(f"  g1 logloss-beat:    {g_pass['beat']}/{n_ok}")
    print(f"  g2 ece-pass:        {g_pass['ece']}/{n_ok}")
    print(f"  g3 monotone:        {g_pass['mono']}/{n_ok}")
    print(f"  g4 lift >= 1.5:     {g_pass['lift']}/{n_ok}")
    cell_pass = all(c >= 6 for c in g_pass.values())
    print(f"\nNaive predictor cell_pass: {'YES' if cell_pass else 'NO'}")
    print()
    print("Interpretation:")
    print("  YES → the magnitude model is NOT adding edge beyond a calendar")
    print("        lookup table.  The phase_calendar pass is a calendar")
    print("        rediscovery, which is priced into 0DTE theta and IV term.")
    print("  NO  → the naive lookup fails on its own; the model is conditioning")
    print("        on bar features in combination with calendar slot. There is")
    print("        incremental signal beyond pure (DoW, time) — worth chasing.")


if __name__ == "__main__":
    main()
