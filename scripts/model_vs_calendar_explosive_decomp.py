#!/usr/bin/env python3
"""Decompose the model's EXPLOSIVE predictions: amplification-of-calendar vs bar-feature edge.

Context: the naive (DoW, 30-min time-bucket) lookup baseline passes gates
1-3 (log-loss-beat, ECE, monotone) every fold but fails gate 4 (EXPLOSIVE
lift) by architectural construction — it can never argmax EXPLOSIVE
because EXPLOSIVE has 3% base rate and no calendar cell has it as the
modal class.

So gate-4 is the one place the model could plausibly add value. The
question is HOW it's adding value:

  (A) AMPLIFICATION — the model predicts EXPLOSIVE specifically on bars
      that fall into calendar cells with above-average historical
      EXPLOSIVE rate, i.e. it's just using the cell-level rate as a
      threshold above some value. If so, a thresholded calendar lookup
      would do exactly as well.

  (B) WITHIN-CELL DISCRIMINATION — the model predicts EXPLOSIVE on some
      bars but not others WITHIN the same calendar cell, conditioning
      on bar-level features (RSI, BB width, vol regime, etc.). If so,
      the bar features ARE adding signal beyond pure calendar.

The decisive measure: for each model-predicted-EXPLOSIVE bar, look up its
calendar cell's historical EXPLOSIVE rate. Compute:

  - Mean historical-cell-rate across all model-EXPLOSIVE bars
       vs overall base rate (≈3%)
       → if mean cell rate is ~8-15%, model is picking high-cell bars
       → if mean cell rate is ~3-4%, model is using bar features
  - Within each high-rate cell, what fraction of bars in that cell does
    the model predict EXPLOSIVE for?
       → if ≈100%, model is just amplifying the cell prior
       → if low (<20%), model is discriminating within the cell

Usage:
    python -m scripts.model_vs_calendar_explosive_decomp \\
        --phase phase_calendar --ticker IWM --tf 5m \\
        --run-id magnitude-engine-7jsgk
"""
from __future__ import annotations
import argparse
import collections
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import storage as gcs

sys.path.insert(0, str(Path(__file__).parent.parent))
from gcp.database import get_engine
from gcp.research.magnitude_engine.mag_config import (
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_CUTOFFS, GCS_BUCKET_DEFAULT,
)
from gcp.research.magnitude_engine.mag_dataset import load_magnitude_dataset


def calendar_keys(ts_series: pd.Series, bucket_minutes: int = 30):
    ts_et = pd.to_datetime(ts_series, utc=True).dt.tz_convert("America/New_York")
    dow = ts_et.dt.dayofweek.values
    minutes_of_day = ts_et.dt.hour.values * 60 + ts_et.dt.minute.values
    bucket = (minutes_of_day // bucket_minutes).astype(int)
    return dow, bucket


def load_predictions(phase, ticker, tf, bucket, run_id):
    client = gcs.Client()
    bkt = client.bucket(bucket)
    prefix = f"research/magnitude_engine/{phase}/{ticker.lower()}_{tf}/"
    blobs = [b for b in bkt.list_blobs(prefix=prefix)
             if b.name.endswith(".csv") and "predictions_" in b.name]
    if run_id:
        blobs = [b for b in blobs if run_id in b.name]
    if not blobs:
        raise SystemExit(f"no predictions CSV under gs://{bucket}/{prefix} for run_id={run_id}")
    target = sorted(blobs, key=lambda b: b.name)[-1]
    print(f"loading predictions: gs://{bucket}/{target.name}", file=sys.stderr)
    return pd.read_csv(io.BytesIO(target.download_as_bytes()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True)
    p.add_argument("--ticker", required=True, choices=list(TICKERS))
    p.add_argument("--tf", required=True, choices=list(TIMEFRAMES))
    p.add_argument("--run-id", required=True)
    p.add_argument("--bucket-minutes", type=int, default=30)
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    args = p.parse_args()

    # Load predictions
    preds = load_predictions(args.phase, args.ticker, args.tf, args.bucket, args.run_id)
    preds["ts"] = pd.to_datetime(preds["ts"], utc=True)
    print(f"loaded {len(preds)} prediction rows", file=sys.stderr)

    # Load training data (only ts + true label) for cell-rate computation
    engine = get_engine()
    print("loading magnitude dataset for training-rate computation...", file=sys.stderr)
    df = load_magnitude_dataset(engine, args.ticker, args.tf, phase="phase0")
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    print(f"loaded {len(df)} dataset rows", file=sys.stderr)

    y_all = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    ts_all = pd.to_datetime(df["ts"], utc=True)
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")

    explosive_idx = LABEL_TO_IDX["EXPLOSIVE"]
    cutoffs = list(DEFAULT_CUTOFFS)

    print()
    print("=" * 100)
    print(f"MODEL EXPLOSIVE DECOMPOSITION  {args.phase} {args.ticker} {args.tf}  "
           f"bucket={args.bucket_minutes}min")
    print("=" * 100)

    # Per-fold analysis
    grand_pred_expl_cell_rates = []
    grand_pred_expl_in_top_cell_pct = []
    grand_baseline_cell_rate = []

    print(f"\n{'fold':25} {'n_pe':>5} {'mean_cell':>10} {'p50_cell':>9} "
           f"{'top-cell coverage':>20} {'within-top-cell':>18}")
    print(f"{'':25} {'':5} {'rate':>10} {'rate':>9} "
           f"{'(% of model-EXPL':>20} {'(% of cell predicted':>18}")
    print(f"{'':25} {'':5} {'':>10} {'':>9} "
           f"{'in top-10% cells)':>20} {' EXPL by model)':>18}")
    print("-" * 100)

    for i, cut in enumerate(cutoffs):
        if i + 1 < len(cutoffs):
            test_end = cutoffs[i + 1]
        else:
            test_end = str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        fold_label = f"{cut}..{test_end}"
        train_end_dt = np.datetime64(cut)
        train_mask = bar_dates_arr < train_end_dt

        # Build cell rates from THIS fold's training data
        y_tr = y_all[train_mask]
        ts_tr = ts_all[train_mask]
        dow_tr, bucket_tr = calendar_keys(ts_tr, args.bucket_minutes)
        cell_expl_rate = collections.defaultdict(lambda: 0.0)
        cell_counts = collections.defaultdict(lambda: 0)
        for j in range(len(y_tr)):
            k = (int(dow_tr[j]), int(bucket_tr[j]))
            cell_counts[k] += 1
            if y_tr[j] == explosive_idx:
                cell_expl_rate[k] += 1.0
        for k in cell_counts:
            cell_expl_rate[k] /= cell_counts[k]
        global_rate = float((y_tr == explosive_idx).mean()) if len(y_tr) else 0.0

        # Pick out THIS fold's predictions
        fold_preds = preds[preds["fold"] == fold_label].copy()
        if fold_preds.empty:
            print(f"{fold_label:25}  (no predictions)")
            continue
        dow_te, bucket_te = calendar_keys(fold_preds["ts"], args.bucket_minutes)
        fold_preds["cell_rate"] = [cell_expl_rate.get((int(dow_te[j]), int(bucket_te[j])),
                                                       global_rate)
                                    for j in range(len(fold_preds))]
        fold_preds["dow"] = dow_te
        fold_preds["time_bucket"] = bucket_te

        # Model-predicted-EXPLOSIVE bars only
        pe = fold_preds[fold_preds["pred_bucket_idx"] == explosive_idx]
        n_pe = len(pe)
        if n_pe == 0:
            print(f"{fold_label:25} {n_pe:>5d}  (no model-EXPLOSIVE predictions)")
            grand_baseline_cell_rate.append(global_rate)
            continue

        mean_cell_rate = float(pe["cell_rate"].mean())
        p50_cell_rate = float(pe["cell_rate"].median())

        # Top-10% cells by historical EXPLOSIVE rate
        sorted_cells = sorted(cell_expl_rate.items(), key=lambda kv: -kv[1])
        n_top = max(1, len(sorted_cells) // 10)
        top_cells = set(c for c, r in sorted_cells[:n_top])
        pe_in_top = pe.apply(
            lambda row: (int(row["dow"]), int(row["time_bucket"])) in top_cells, axis=1
        ).sum()
        in_top_pct = pe_in_top / n_pe

        # Within-top-cell coverage — of all bars whose cell is in the top
        # 10%, what fraction did the model predict EXPLOSIVE?
        in_top_mask = fold_preds.apply(
            lambda row: (int(row["dow"]), int(row["time_bucket"])) in top_cells, axis=1
        )
        n_in_top = int(in_top_mask.sum())
        n_in_top_pe = int(((fold_preds["pred_bucket_idx"] == explosive_idx) & in_top_mask).sum())
        within_top_cov = (n_in_top_pe / n_in_top) if n_in_top else 0.0

        print(f"{fold_label:25} {n_pe:>5d} {mean_cell_rate:>10.3f} "
              f"{p50_cell_rate:>9.3f} {in_top_pct:>20.1%} {within_top_cov:>18.1%}")

        grand_pred_expl_cell_rates.append(mean_cell_rate)
        grand_pred_expl_in_top_cell_pct.append(in_top_pct)
        grand_baseline_cell_rate.append(global_rate)

    if grand_pred_expl_cell_rates:
        print()
        avg_cell_rate = float(np.mean(grand_pred_expl_cell_rates))
        avg_in_top = float(np.mean(grand_pred_expl_in_top_cell_pct))
        avg_baseline = float(np.mean(grand_baseline_cell_rate))
        print(f"OVERALL (avg across folds):")
        print(f"  mean historical cell rate for model-EXPLOSIVE bars  : {avg_cell_rate:.3f}")
        print(f"  global EXPLOSIVE base rate                          : {avg_baseline:.3f}")
        print(f"  ratio (concentration in high-rate cells)            : {avg_cell_rate/avg_baseline if avg_baseline else float('nan'):.2f}x")
        print(f"  % of model-EXPLOSIVE bars in top-10% cells          : {avg_in_top:.1%}")
        print()
        print("Interpretation:")
        print("  - If ratio >= 3x AND in-top% >= 60%: model is amplifying calendar.")
        print("    Bar features add little; calendar threshold would replicate.")
        print("  - If ratio is 1-2x AND in-top% < 30%: model is using bar features")
        print("    to discriminate WITHIN cells. Real incremental edge.")
        print("  - In-between: mixed evidence; eyeball the per-fold table.")


if __name__ == "__main__":
    main()
