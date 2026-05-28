#!/usr/bin/env python3
"""Check 3 — Event-window concentration of magnitude-engine EXPLOSIVE predictions.

Reads the per-bar prediction CSV that the walk-forward harness now writes
to GCS (predictions_{run_id}.csv per phase/ticker/tf), joins it against
`economic_events` high-impact rows, and reports:

  - Of bars predicted EXPLOSIVE by the model, what % fall within ±4 hours
    of a high-impact event?
  - What % of ALL test-set bars are within ±4 hours of an event (base rate)?
  - The ratio = concentration factor. Per reviewer guidance, we DO NOT
    pre-commit to a 3x threshold; we report the breakdown and let the
    reader decide which regime they're in.

The check is *only* informative if the prediction CSV exists. The cells
prior to commit 8dcfd71 didn't persist predictions; for those, re-dispatch
the cell first.

Usage:
    python -m scripts.check_event_window_concentration \\
        --phase phase3 --ticker SPY --tf 15m

    python -m scripts.check_event_window_concentration \\
        --phase phase3 --ticker SPY --tf 15m --window-hours 2
"""
from __future__ import annotations
import argparse
import io
import os
import sys
from pathlib import Path

import pandas as pd
from google.cloud import storage as gcs

sys.path.insert(0, str(Path(__file__).parent.parent))
from gcp.research.magnitude_engine.mag_config import (
    LABEL_CLASSES, LABEL_TO_IDX, GCS_BUCKET_DEFAULT,
)


def load_predictions(phase: str, ticker: str, tf: str,
                      bucket: str, run_id: str | None) -> pd.DataFrame:
    """List + load via google-cloud-storage SDK (the Cloud Run image
    has this, not the gcloud CLI)."""
    client = gcs.Client()
    bkt = client.bucket(bucket)
    prefix = f"research/magnitude_engine/{phase}/{ticker.lower()}_{tf}/"
    blobs = [b for b in bkt.list_blobs(prefix=prefix)
             if b.name.endswith(".csv") and "predictions_" in b.name]
    if not blobs:
        raise SystemExit(f"no prediction CSV under gs://{bucket}/{prefix}")
    if run_id:
        blobs = [b for b in blobs if run_id in b.name]
        if not blobs:
            raise SystemExit(f"no prediction CSV matching run_id={run_id}")
    target = sorted(blobs, key=lambda b: b.name)[-1]
    print(f"loading predictions: gs://{bucket}/{target.name}", file=sys.stderr)
    return pd.read_csv(io.BytesIO(target.download_as_bytes()))


def load_high_impact_events(min_ts: pd.Timestamp, max_ts: pd.Timestamp) -> pd.DataFrame:
    """Pull high-impact events via db-query workflow.

    For sandbox + speed, we instead query Cloud SQL directly when an
    engine is reachable. From a sandbox that can't reach 5432, fall back
    to a pre-cached CSV at gs://.../research/magnitude_engine/_cache/.
    For this check we use the direct path — the script is intended to
    run from a context with network access (Cloud Run Job or local with
    Cloud SQL Auth Proxy). Sandbox callers can replace this with a
    `db-query.yml` fetched artifact.
    """
    from sqlalchemy import text
    from gcp.database import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        ev = pd.read_sql(
            text("""
                SELECT event_date, event_time, importance, event_name
                  FROM economic_events
                 WHERE LOWER(importance) = 'high'
                   AND event_date BETWEEN :lo AND :hi
                 ORDER BY event_date, event_time
            """),
            conn,
            params={
                "lo": min_ts.date(),
                "hi": max_ts.date(),
            },
        )
    if ev.empty:
        return ev
    # Build UTC event_ts (event_date + event_time + EDT offset, same as
    # mag_dataset._add_phase3_features).
    ev["event_time"] = ev["event_time"].fillna(pd.Timestamp("09:00").time())
    ev["event_ts"] = (
        pd.to_datetime(ev["event_date"].astype(str) + " "
                        + ev["event_time"].astype(str), utc=False)
        + pd.Timedelta(hours=4)
    ).dt.tz_localize("UTC")
    return ev[["event_ts", "event_name", "importance"]]


def add_event_proximity(preds: pd.DataFrame, events: pd.DataFrame,
                         window_hours: float) -> pd.DataFrame:
    """Annotate each prediction row with min |delta-to-nearest-event| in hours
    and an `in_window` boolean (True if within ±window_hours)."""
    preds = preds.copy()
    preds["ts"] = pd.to_datetime(preds["ts"], utc=True)
    if events.empty:
        preds["nearest_event_hours"] = float("nan")
        preds["in_window"] = False
        return preds
    bar_ts = preds["ts"].values.astype("datetime64[ns]")
    ev_ts = events["event_ts"].sort_values().values.astype("datetime64[ns]")
    # For each bar, find index of nearest event by binary search
    import numpy as np
    idx_right = np.searchsorted(ev_ts, bar_ts, side="left")
    idx_left = np.clip(idx_right - 1, 0, len(ev_ts) - 1)
    idx_right = np.clip(idx_right, 0, len(ev_ts) - 1)
    delta_left = np.abs((bar_ts - ev_ts[idx_left]) / np.timedelta64(1, "h"))
    delta_right = np.abs((bar_ts - ev_ts[idx_right]) / np.timedelta64(1, "h"))
    nearest = np.minimum(delta_left, delta_right)
    preds["nearest_event_hours"] = nearest
    preds["in_window"] = nearest <= window_hours
    return preds


def report(preds: pd.DataFrame, phase: str, ticker: str, tf: str,
            window_hours: float) -> None:
    """Print the concentration breakdown."""
    print()
    print("=" * 78)
    print(f"CHECK 3 — Event-window concentration: {phase} {ticker} {tf}")
    print(f"Window: ±{window_hours} hours around high-impact events")
    print("=" * 78)
    explosive_idx = LABEL_TO_IDX["EXPLOSIVE"]

    n_total = len(preds)
    n_window = int(preds["in_window"].sum())
    base_window_rate = n_window / n_total if n_total else 0.0

    pred_explosive = preds[preds["pred_bucket_idx"] == explosive_idx]
    n_pred_expl = len(pred_explosive)
    n_pred_expl_window = int(pred_explosive["in_window"].sum())
    pred_expl_in_window_rate = (n_pred_expl_window / n_pred_expl) if n_pred_expl else 0.0

    true_explosive = preds[preds["true_bucket_idx"] == explosive_idx]
    n_true_expl = len(true_explosive)
    n_true_expl_window = int(true_explosive["in_window"].sum())
    true_expl_in_window_rate = (n_true_expl_window / n_true_expl) if n_true_expl else 0.0

    print()
    print(f"Test-set base rates")
    print(f"  total bars                       : {n_total:>8d}")
    print(f"  bars within event window         : {n_window:>8d}  ({base_window_rate:.1%})")
    print(f"  bars predicted EXPLOSIVE          : {n_pred_expl:>8d}  ({n_pred_expl/n_total:.2%})")
    print(f"  bars actually EXPLOSIVE           : {n_true_expl:>8d}  ({n_true_expl/n_total:.2%})")
    print()
    print(f"Concentration")
    print(f"  predicted-EXPLOSIVE in window    : {n_pred_expl_window:>8d}  ({pred_expl_in_window_rate:.1%})")
    print(f"  actually-EXPLOSIVE in window     : {n_true_expl_window:>8d}  ({true_expl_in_window_rate:.1%})")
    print()
    if base_window_rate > 0:
        pred_ratio = pred_expl_in_window_rate / base_window_rate
        true_ratio = true_expl_in_window_rate / base_window_rate
        print(f"Concentration ratios (vs base rate)")
        print(f"  predicted-EXPLOSIVE / base rate  : {pred_ratio:.2f}x")
        print(f"  actually-EXPLOSIVE / base rate   : {true_ratio:.2f}x")
    print()
    # Per-fold breakdown — sometimes the concentration shifts dramatically
    # between regimes
    print(f"Per-fold breakdown of predicted-EXPLOSIVE concentration")
    print(f"  {'fold':25} {'n_pred_expl':>11} {'% in window':>12} {'base rate':>10}")
    print(f"  {'-' * 25} {'-' * 11} {'-' * 12} {'-' * 10}")
    for fold, g in preds.groupby("fold"):
        n_total_fold = len(g)
        n_window_fold = int(g["in_window"].sum())
        base_fold = n_window_fold / n_total_fold if n_total_fold else 0
        pe = g[g["pred_bucket_idx"] == explosive_idx]
        n_pe = len(pe)
        n_pe_w = int(pe["in_window"].sum())
        pe_rate = (n_pe_w / n_pe) if n_pe else 0
        print(f"  {fold:25} {n_pe:>11d} {pe_rate:>12.1%} {base_fold:>10.1%}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True)
    p.add_argument("--ticker", required=True)
    p.add_argument("--tf", required=True)
    p.add_argument("--run-id", default=None)
    p.add_argument("--window-hours", type=float, default=4.0)
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    args = p.parse_args()

    preds = load_predictions(args.phase, args.ticker, args.tf, args.bucket, args.run_id)
    preds["ts"] = pd.to_datetime(preds["ts"], utc=True)
    events = load_high_impact_events(preds["ts"].min(), preds["ts"].max())
    annotated = add_event_proximity(preds, events, args.window_hours)
    report(annotated, args.phase, args.ticker, args.tf, args.window_hours)


if __name__ == "__main__":
    main()
