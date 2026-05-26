"""Diagnostic for a saved Stage 4 model — pull the metrics JSON, show per-bin
reliability, confusion matrix, predicted-class distribution.

Used to answer "why did the gate fail?" without re-running training. Output
matches what you'd see in the matching notebook
`notebooks/strat_pred_diagnose.ipynb`.

Run:
  # show winning model (sigmoid by default per LOCKED config)
  python -m gcp.research.strat_engine.strat_pred_diagnose --ticker IWM --tf 15m

  # show a specific calibration method's latest run
  python -m gcp.research.strat_engine.strat_pred_diagnose --ticker IWM --tf 15m --calibration isotonic

  # list every metrics file in the cell with its calibration + gate verdict
  python -m gcp.research.strat_engine.strat_pred_diagnose --ticker IWM --tf 15m --list
"""
from __future__ import annotations
import argparse
import json
import os

from google.cloud import storage as gcs

from gcp.research.strat_engine.strat_config import (
    GCS_BUCKET_DEFAULT, gcs_model_prefix, LABEL_CLASSES,
    DEFAULT_CALIBRATION,
)


def list_all_metrics(ticker: str, tf: str) -> list[dict]:
    """Return EVERY metrics_*.json for a (ticker, tf) cell with summary info.
    Sorted oldest → newest by GCS create time."""
    bucket = gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))
    prefix = gcs_model_prefix(ticker, tf)
    blobs = sorted(bucket.list_blobs(prefix=f"{prefix}/metrics_"),
                   key=lambda b: b.time_created or b.name)
    rows = []
    for b in blobs:
        try:
            payload = json.loads(b.download_as_bytes().decode())
        except Exception:
            continue
        rows.append({
            "blob": b.name,
            "ts": b.time_created.isoformat() if b.time_created else "?",
            "calibration": payload.get("calibration", "?"),
            "log_loss": payload.get("oos_log_loss"),
            "accuracy": payload.get("oos_accuracy"),
            "ece": payload.get("ece"),
            "verdict": payload.get("gate", {}).get("verdict", "?"),
            "payload": payload,
        })
    return rows


def latest_metrics_for(ticker: str, tf: str,
                       calibration: str | None = None) -> dict | None:
    """Return the latest metrics_*.json matching the requested calibration.
    calibration=None means 'no filter' — picks the chronological latest
    (legacy behavior, useful for --list)."""
    rows = list_all_metrics(ticker, tf)
    if not rows:
        return None
    if calibration is None:
        return rows[-1]["payload"]
    matches = [r for r in rows if r["calibration"] == calibration]
    if not matches:
        return None
    return matches[-1]["payload"]


def load_metrics(ticker: str, tf: str,
                 calibration: str | None = None) -> dict:
    """For backward compat with the notebook. Filters by calibration if given."""
    m = latest_metrics_for(ticker, tf, calibration=calibration)
    if m is None:
        if calibration:
            raise RuntimeError(
                f"No metrics_*.json with calibration={calibration} for "
                f"{ticker} {tf}. Run Stage 4 with --calibration={calibration}."
            )
        raise RuntimeError(f"No metrics_*.json for {ticker} {tf}; run Stage 4 first.")
    return m


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


def diagnose(ticker: str, tf: str, calibration: str | None = None) -> dict:
    m = load_metrics(ticker, tf, calibration=calibration)
    print_summary(m)
    print_reliability(m)
    print_per_class(m)
    print_confusion(m)
    return m


def list_mode(ticker: str, tf: str) -> None:
    """Print one line per saved metrics file for the (ticker, tf) cell."""
    rows = list_all_metrics(ticker, tf)
    if not rows:
        print(f"No metrics_*.json found for {ticker} {tf}.")
        return
    print(f"\n{ticker} {tf} — {len(rows)} metrics file(s) on GCS "
          f"(oldest → newest):")
    print(f"  {'created_at':<27}  {'cal':<9}  {'log-loss':>9}  {'acc':>7}  {'ECE':>7}  verdict")
    print("  " + "-" * 78)
    for r in rows:
        ll = f"{r['log_loss']:.4f}" if r['log_loss'] is not None else "?"
        ac = f"{r['accuracy']:.3f}" if r['accuracy'] is not None else "?"
        ec = f"{r['ece']:.4f}" if r['ece'] is not None else "?"
        print(f"  {r['ts']:<27}  {r['calibration']:<9}  {ll:>9}  {ac:>7}  {ec:>7}  {r['verdict']}")
    print(f"\nDefault when `--calibration` is omitted: filter to '{DEFAULT_CALIBRATION}' "
          f"(the LOCKED production default).")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True)
    p.add_argument("--tf", required=True)
    p.add_argument("--calibration", default=DEFAULT_CALIBRATION,
                   choices=["sigmoid", "isotonic", "any"],
                   help=f"Pick latest metrics matching this calibration. "
                        f"Default '{DEFAULT_CALIBRATION}' is the LOCKED "
                        f"production default. 'any' = chronologically latest "
                        f"regardless of method.")
    p.add_argument("--list", action="store_true",
                   help="List ALL metrics files for the cell instead of "
                        "printing the diagnostic. Useful to audit which "
                        "calibration variants have been tried.")
    args = p.parse_args()
    if args.list:
        list_mode(args.ticker, args.tf)
        return
    cal = None if args.calibration == "any" else args.calibration
    diagnose(args.ticker, args.tf, calibration=cal)


if __name__ == "__main__":
    main()



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
