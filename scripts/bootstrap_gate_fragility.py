#!/usr/bin/env python3
"""Bootstrap gate-fragility analysis for magnitude-engine cells.

Reviewer's concern: SPY 15m Phase 3 has three of four gates at exactly
6/8 — the minimum to pass. How robust is this to test-set sampling
noise within each fold?

Method: for each fold, resample the test bars WITH REPLACEMENT N times,
recompute the four gates each time, count how often the per-fold gate
contributions to each phase-level gate would flip. Returns a distribution
over the four gate counts {g1, g2, g3, g4} so we can read off the
probability that any single gate falls below its 6/8 threshold.

CRITICAL: no retraining. We resample bars from the FIXED predictions
the harness already wrote to GCS. This isolates "is the gate count a
stable function of the test set's bar selection" from "is the trained
model stable" (which the deterministic-LightGBM analysis already
answered).

Usage:
    python -m scripts.bootstrap_gate_fragility \\
        --phase phase3 --ticker SPY --tf 15m \\
        --run-id magnitude-engine-6pd4c --bootstrap-n 1000
"""
from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import storage as gcs

sys.path.insert(0, str(Path(__file__).parent.parent))
from gcp.research.magnitude_engine.mag_config import (
    LABEL_CLASSES, LABEL_TO_IDX, GCS_BUCKET_DEFAULT,
    ECE_CEILING_BY_TF, SUCCESS_BAR_CONFIDENCE_THRESHOLDS,
    SUCCESS_BAR_EXPLOSIVE_LIFT_MIN,
    SUCCESS_BAR_MIN_FOLDS_LOGLOSS, SUCCESS_BAR_MIN_FOLDS_ECE,
    SUCCESS_BAR_MIN_FOLDS_LIFT,
)
from gcp.research.magnitude_engine.mag_pred_train import (
    expected_calibration_error, decisive_call_hit_rate, explosive_lift,
)
from sklearn.metrics import log_loss


def load_predictions(phase, ticker, tf, bucket, run_id):
    client = gcs.Client()
    bkt = client.bucket(bucket)
    prefix = f"research/magnitude_engine/{phase}/{ticker.lower()}_{tf}/"
    blobs = [b for b in bkt.list_blobs(prefix=prefix)
             if b.name.endswith(".csv") and "predictions_" in b.name]
    if run_id:
        blobs = [b for b in blobs if run_id in b.name]
    if not blobs:
        raise SystemExit(f"no prediction CSV under gs://{bucket}/{prefix} matching run_id={run_id}")
    target = sorted(blobs, key=lambda b: b.name)[-1]
    print(f"loading: gs://{bucket}/{target.name}", file=sys.stderr)
    return pd.read_csv(io.BytesIO(target.download_as_bytes()))


def fold_gates(fold_df: pd.DataFrame, tf: str) -> dict:
    """Recompute the four per-fold gate inputs from a (resampled or
    original) fold's predictions+truth."""
    proba_cols = [f"p_{c}" for c in LABEL_CLASSES]
    proba = fold_df[proba_cols].values
    y_true = fold_df["true_bucket_idx"].values
    pred = fold_df["pred_bucket_idx"].values

    if len(y_true) == 0:
        return None
    classes = list(range(len(LABEL_CLASSES)))

    ll = float(log_loss(y_true, proba, labels=classes))
    # We don't have y_train_idx for the base rate; recompute base log-loss
    # from the FOLD's truth distribution (this is what's available from
    # predictions alone). This is slightly different from what the
    # harness recorded (which uses train-prior); for bootstrap
    # comparison we hold the methodology constant across all bootstrap
    # iterations — what matters is variance, not the absolute value.
    prior = np.bincount(y_true, minlength=len(LABEL_CLASSES)).astype(float)
    prior = prior / prior.sum() if prior.sum() > 0 else np.ones(len(LABEL_CLASSES)) / len(LABEL_CLASSES)
    base_proba = np.tile(prior, (len(y_true), 1))
    base_ll = float(log_loss(y_true, base_proba, labels=classes))
    beat = base_ll - ll

    ece, _ = expected_calibration_error(y_true, proba, n_bins=10)
    ece_pass = ece <= ECE_CEILING_BY_TF[tf]

    decisive = decisive_call_hit_rate(y_true, proba, SUCCESS_BAR_CONFIDENCE_THRESHOLDS)
    accs = [decisive[f"{t:.2f}"]["accuracy"] for t in SUCCESS_BAR_CONFIDENCE_THRESHOLDS]
    clean = [a for a in accs if a is not None]
    monotone = (len(clean) >= 2 and all(b >= a for a, b in zip(clean, clean[1:])))

    expl = explosive_lift(y_true, proba, explosive_idx=LABEL_TO_IDX["EXPLOSIVE"])
    lift = expl.get("lift")
    lift_pass = lift is not None and lift >= SUCCESS_BAR_EXPLOSIVE_LIFT_MIN

    return {
        "beat": beat,
        "ece": ece, "ece_pass": ece_pass,
        "monotone": monotone,
        "lift": lift, "lift_pass": lift_pass,
    }


def bootstrap_one_cell(preds: pd.DataFrame, tf: str, n_iter: int, seed: int = 1):
    """Resample bars within each fold (with replacement) N times and count
    how often each cell-level gate (g1, g2, g3, g4) passes its 6/8 threshold."""
    folds = sorted(preds["fold"].unique())
    n_folds = len(folds)
    rng = np.random.default_rng(seed)

    # Per-iteration counts
    iter_g_counts = []  # list of (g1, g2, g3, g4) each in [0..n_folds]

    fold_groups = {f: preds[preds["fold"] == f].reset_index(drop=True) for f in folds}

    # Also keep the deterministic (no-resample) result for reference
    det_g = [0, 0, 0, 0]
    for f in folds:
        g = fold_gates(fold_groups[f], tf)
        if g is None:
            continue
        if g["beat"] > 0:        det_g[0] += 1
        if g["ece_pass"]:        det_g[1] += 1
        if g["monotone"]:        det_g[2] += 1
        if g["lift_pass"]:       det_g[3] += 1

    for it in range(n_iter):
        gc = [0, 0, 0, 0]
        for f in folds:
            g = fold_groups[f]
            n = len(g)
            if n == 0:
                continue
            idx = rng.integers(0, n, size=n)
            sample = g.iloc[idx]
            r = fold_gates(sample, tf)
            if r is None:
                continue
            if r["beat"] > 0:    gc[0] += 1
            if r["ece_pass"]:    gc[1] += 1
            if r["monotone"]:    gc[2] += 1
            if r["lift_pass"]:   gc[3] += 1
        iter_g_counts.append(gc)

    counts = np.array(iter_g_counts)
    return {
        "n_folds": n_folds,
        "deterministic": tuple(det_g),
        "mean": counts.mean(axis=0),
        "p_lt_6":  (counts < 6).mean(axis=0),
        "p_eq_6":  (counts == 6).mean(axis=0),
        "p_gt_6":  (counts > 6).mean(axis=0),
        "p5":  np.percentile(counts, 5, axis=0),
        "p50": np.percentile(counts, 50, axis=0),
        "p95": np.percentile(counts, 95, axis=0),
        "cell_pass_rate": float((counts >= 6).all(axis=1).mean()),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True)
    p.add_argument("--ticker", required=True)
    p.add_argument("--tf", required=True)
    p.add_argument("--run-id", default=None)
    p.add_argument("--bootstrap-n", type=int, default=1000)
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args()

    preds = load_predictions(args.phase, args.ticker, args.tf, args.bucket, args.run_id)
    print(f"\nLoaded {len(preds)} prediction rows for {args.phase} {args.ticker} {args.tf}")
    print(f"Bootstrap iterations: {args.bootstrap_n}")

    r = bootstrap_one_cell(preds, args.tf, args.bootstrap_n, seed=args.seed)

    print()
    print("=" * 86)
    print(f"BOOTSTRAP GATE FRAGILITY — {args.phase} {args.ticker} {args.tf}")
    print("=" * 86)
    gate_names = ["g1 logloss-beat", "g2 ece-pass", "g3 monotone", "g4 lift>=1.5"]
    print(f"\n{'gate':20} {'det':>5} {'mean':>6} {'p5':>4} {'p50':>4} {'p95':>4} "
           f"{'P(<6)':>7} {'P(=6)':>7} {'P(>6)':>7}")
    print("-" * 86)
    for i, name in enumerate(gate_names):
        print(f"{name:20} {r['deterministic'][i]:>5d} "
              f"{r['mean'][i]:>6.2f} "
              f"{int(r['p5'][i]):>4d} {int(r['p50'][i]):>4d} {int(r['p95'][i]):>4d} "
              f"{r['p_lt_6'][i]:>7.1%} {r['p_eq_6'][i]:>7.1%} {r['p_gt_6'][i]:>7.1%}")
    print()
    print(f"Cell-level PASS rate across {args.bootstrap_n} bootstrap samples: "
          f"{r['cell_pass_rate']:.1%}")
    print()
    print("Interpretation:")
    print(f"  P(<6) is the bootstrap-estimated probability that a gate falls")
    print(f"  below the 6/8 threshold under resampling of test bars within folds.")
    print(f"  For a gate that 'just-barely-passed' (deterministic=6), a P(<6)")
    print(f"  near 50% signals the gate is at the edge of sampling noise.")


if __name__ == "__main__":
    main()
