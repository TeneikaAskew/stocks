"""Diagnostic for a saved Stage 4 model — pull the metrics JSON, show per-bin
reliability, confusion matrix, predicted-class distribution.

Used to answer "why did the gate fail?" without re-running training. Output
matches what you'd see in the matching notebook
`notebooks/strat_pred_diagnose.ipynb`.

Run:
  python -m gcp.research.strat_engine.strat_pred_diagnose --ticker IWM --tf 15m
"""
from __future__ import annotations
import argparse
import json
import os

from google.cloud import storage as gcs

from gcp.research.strat_engine.strat_config import (
    GCS_BUCKET_DEFAULT, gcs_model_prefix, LABEL_CLASSES,
)


def latest_metrics_blob(ticker: str, tf: str) -> str | None:
    bucket = gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    prefix = gcs_model_prefix(ticker, tf)
    blobs = sorted(bucket.list_blobs(prefix=f"{prefix}/metrics_"),
                   key=lambda b: b.time_created or b.name)
    return blobs[-1].name if blobs else None


def load_metrics(ticker: str, tf: str) -> dict:
    blob_name = latest_metrics_blob(ticker, tf)
    if not blob_name:
        raise RuntimeError(f"No metrics_*.json for {ticker} {tf}; run Stage 4 first.")
    bucket = gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    return json.loads(bucket.blob(blob_name).download_as_bytes().decode())


def print_summary(m: dict) -> None:
    print("=" * 70)
    print(f"{m['ticker']} {m['tf']} — n_train={m['n_train']}  n_test={m['n_test']}  "
          f"calibration={m.get('calibration','?')}")
    print("=" * 70)
    print(f"\nOOS log-loss: {m['oos_log_loss']:.4f}  vs base {m['base_log_loss']:.4f}  "
          f"Δ=+{m['log_loss_improvement']:.4f}")
    print(f"OOS accuracy: {m['oos_accuracy']:.3f}  vs base {m['base_accuracy']:.3f}  "
          f"Δ=+{m['accuracy_beat_pp']:.1f}pp")
    print(f"OOS ECE     : {m['ece']:.4f}  ceiling {m['gate']['ece_ceiling']:.3f}  "
          f"miss=+{m['ece']-m['gate']['ece_ceiling']:.4f}")
    print(f"Gate verdict: {m['gate']['verdict']}")


def print_reliability(m: dict) -> None:
    print("\nECE per-bin reliability (avg_conf should ≈ avg_acc):")
    print(f"  {'bin':>3}  {'range':>14}  {'n':>5}  {'avg_conf':>9}  {'avg_acc':>9}  "
          f"{'|diff|':>8}  weight×|diff|")
    n_total = m['n_test']
    for b in m['ece_bins']:
        if b['n'] == 0:
            print(f"  {b['bin']:>3}  [{b['lo']:.2f},{b['hi']:.2f})   "
                  f"{b['n']:>5}  -          -          -         -")
        else:
            diff = abs(b['avg_conf'] - b['avg_acc'])
            contrib = (b['n']/n_total) * diff
            arrow = ""
            if b['avg_conf'] < b['avg_acc'] - 0.03:
                arrow = "  ← UNDERconfident"
            elif b['avg_conf'] > b['avg_acc'] + 0.03:
                arrow = "  ← OVERconfident"
            print(f"  {b['bin']:>3}  [{b['lo']:.2f},{b['hi']:.2f})   {b['n']:>5}  "
                  f"{b['avg_conf']:>9.3f}  {b['avg_acc']:>9.3f}  {diff:>8.4f}  "
                  f"{contrib:>7.4f}{arrow}")
    print(f"\nSUM contribution = {m['ece']:.4f} (this IS the ECE)")


def print_per_class(m: dict) -> None:
    print("\nPer-class P/R/F1 (does the model predict every class?):")
    for cls in LABEL_CLASSES:
        r = m['per_class'][cls]
        flag = "  ← NEVER PREDICTED" if r['precision'] == 0 and r['recall'] == 0 else ""
        print(f"  {cls:>3}  prec={r['precision']:.3f}  rec={r['recall']:.3f}  "
              f"f1={r['f1-score']:.3f}  support={int(r['support'])}{flag}")


def print_confusion(m: dict) -> None:
    print("\nConfusion matrix (rows=actual, cols=predicted):")
    cm = m['confusion_matrix']
    print(f"  {'actual':>6} " + " ".join(f"{'pred_'+c:>7}" for c in LABEL_CLASSES))
    for cls in LABEL_CLASSES:
        row = cm[cls]
        print(f"  {cls:>6} " + " ".join(f"{row[c]:>7d}" for c in LABEL_CLASSES))

    # Predicted-class distribution — surfaces "model never calls class X"
    preds = {c: sum(cm[a][c] for a in LABEL_CLASSES) for c in LABEL_CLASSES}
    total = sum(preds.values())
    print(f"\nPredicted-class distribution (out of {total} OOS bars):")
    for c in LABEL_CLASSES:
        flag = ""
        if preds[c] == 0:
            flag = "  ← NEVER PREDICTED"
        elif preds[c] / total < 0.02:
            flag = "  ← almost never predicted"
        cls_name = {"1": "inside", "2U": "up", "2D": "down", "3": "outside"}[c]
        print(f"  {c} ({cls_name:>7}):  {preds[c]:>5d} ({preds[c]/total:>5.1%}){flag}")


def diagnose(ticker: str, tf: str) -> dict:
    m = load_metrics(ticker, tf)
    print_summary(m)
    print_reliability(m)
    print_per_class(m)
    print_confusion(m)
    return m


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True)
    p.add_argument("--tf", required=True)
    args = p.parse_args()
    diagnose(args.ticker, args.tf)


if __name__ == "__main__":
    main()
