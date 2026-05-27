"""Strat Engine — one-week prediction-vs-actual report (IWM 15m, production config).

Trains production-config model (LightGBM multiclass, no calibration) on data
STRICTLY BEFORE the test window. Predicts on each 15m bar in the test week.
Compares argmax + per-bar probabilities against the actual next-bar type.

Prints both summary and per-bar tables to stdout as markdown. The orchestrator
that dispatches this scrapes the logs.

Usage:
  python -m gcp.research.strat_engine.strat_pred_report \\
      --ticker IWM --tf 15m \\
      --test-start 2026-05-11 --test-end 2026-05-16  # exclusive end
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
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize, make_lgbm
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--test-start", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--test-end", required=True, help="YYYY-MM-DD EXCLUSIVE")
    args = p.parse_args()

    log.info("=" * 70)
    log.info("STRAT-PRED REPORT  %s %s  test=[%s..%s)",
             args.ticker, args.tf, args.test_start, args.test_end)
    log.info("=" * 70)

    engine = get_engine()
    df = load_labeled_dataset(engine, args.ticker, args.tf)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    log.info("loaded full dataset: %d rows  (%s..%s)",
             len(df), df["bar_date"].min(), df["bar_date"].max())

    test_start = pd.Timestamp(args.test_start).date()
    test_end = pd.Timestamp(args.test_end).date()

    train_df = df[df["bar_date"] < test_start].copy()
    test_df = df[(df["bar_date"] >= test_start) & (df["bar_date"] < test_end)].copy()

    # Boundary print
    log.info("─" * 70)
    log.info("TRAIN / TEST BOUNDARY")
    log.info("  train: %d bars, dates %s..%s",
             len(train_df), train_df["bar_date"].min(), train_df["bar_date"].max())
    log.info("  test:  %d bars, dates %s..%s",
             len(test_df), test_df["bar_date"].min(), test_df["bar_date"].max())
    overlap = set(train_df["bar_date"].unique()) & set(test_df["bar_date"].unique())
    if overlap:
        raise RuntimeError(f"LEAK: train/test overlap on dates {sorted(overlap)}")
    log.info("  overlap: 0 dates (leak-free)")

    if len(test_df) == 0:
        log.error("test window is empty — aborting")
        return

    # Featurize, align
    X_train, train_cols = featurize(train_df)
    X_test, test_cols = featurize(test_df)
    all_cols = sorted(set(train_cols) | set(test_cols))
    X_train = X_train.reindex(columns=all_cols, fill_value=0).astype(np.float32)
    X_test = X_test.reindex(columns=all_cols, fill_value=0).astype(np.float32)
    y_train = train_df[LABEL_COL].map(LABEL_TO_IDX).values
    y_test = test_df[LABEL_COL].map(LABEL_TO_IDX).values
    log.info("featurize: train %s, test %s",
             X_train.shape, X_test.shape)

    # Production config — LightGBM, NO calibration
    log.info("training LightGBM (no calibration) ...")
    model = make_lgbm(class_weight=None)
    model.fit(X_train.values, y_train)
    log.info("training done.")

    proba = model.predict_proba(X_test.values)  # shape (n_test, 4)
    # Align proba columns to LABEL_CLASSES ordering
    # model.classes_ is index space; LABEL_CLASSES are strings.
    # Build a column reorder that maps model.classes_ idx → LABEL_CLASSES idx.
    proba_aligned = np.zeros((proba.shape[0], len(LABEL_CLASSES)))
    for j, idx in enumerate(model.classes_):
        proba_aligned[:, idx] = proba[:, j]
    proba = proba_aligned

    pred_idx = np.argmax(proba, axis=1)
    top_prob = proba.max(axis=1)
    actual_idx = y_test
    hit = (pred_idx == actual_idx).astype(int)

    # Build per-bar dataframe for reporting
    rep = pd.DataFrame({
        "ts": test_df["ts"].values,
        "bar_date": test_df["bar_date"].values,
        "open": test_df["open"].values,
        "high": test_df["high"].values,
        "low": test_df["low"].values,
        "close": test_df["close"].values,
        "prev_strat": test_df["strat_candle"].values,  # CURRENT bar — "prev" relative to label
        "p1":  proba[:, 0],
        "p2u": proba[:, 1],
        "p2d": proba[:, 2],
        "p3":  proba[:, 3],
        "predicted": [LABEL_CLASSES[i] for i in pred_idx],
        "top_prob": top_prob,
        "actual": [LABEL_CLASSES[i] for i in actual_idx],
        "hit": hit,
    })
    rep["ts"] = pd.to_datetime(rep["ts"], utc=True).dt.tz_convert("America/New_York")

    # ── TABLE 1 — Summary ──
    log.info("=" * 70)
    log.info("TABLE 1 — SUMMARY")
    log.info("=" * 70)

    n_total = len(rep)
    overall_hit = float(hit.mean())
    base_rate_each = pd.Series(actual_idx).value_counts(normalize=True).reindex(
        range(len(LABEL_CLASSES)), fill_value=0)
    majority_class_in_test = int(np.bincount(actual_idx, minlength=len(LABEL_CLASSES)).argmax())
    base_rate = float((actual_idx == majority_class_in_test).mean())

    dir_mask = np.isin(actual_idx, [LABEL_TO_IDX["2U"], LABEL_TO_IDX["2D"]])
    dir_hit = float(hit[dir_mask].mean()) if dir_mask.sum() else float("nan")

    log.info("| metric | value |")
    log.info("|---|---|")
    log.info(f"| total test bars | {n_total} |")
    log.info(f"| overall accuracy (argmax==actual) | {overall_hit:.3f} |")
    log.info(f"| test-window base rate (majority class={LABEL_CLASSES[majority_class_in_test]}) | {base_rate:.3f} |")
    log.info(f"| accuracy beat over base | +{(overall_hit-base_rate)*100:.1f}pp |")
    log.info(f"| accuracy on directional actuals (2U or 2D) | {dir_hit:.3f} |")

    log.info("")
    log.info("**Actual next-bar-type distribution in test week:**")
    log.info("| type | count | share |")
    log.info("|---|---|---|")
    for k, cls in enumerate(LABEL_CLASSES):
        n = int((actual_idx == k).sum())
        log.info(f"| {cls} | {n} | {n/n_total:.1%} |")

    log.info("")
    log.info("**Confident-call hit rate at top-prob thresholds:**")
    log.info("| top-prob ≥ | n calls | hit rate | avg stated conf | calibration gap |")
    log.info("|---|---|---|---|---|")
    for thresh in [0.50, 0.55, 0.60]:
        mask = top_prob >= thresh
        n = int(mask.sum())
        if n == 0:
            log.info(f"| {thresh:.2f} | 0 | — | — | — |")
        else:
            hr = float(hit[mask].mean())
            avg_conf = float(top_prob[mask].mean())
            log.info(f"| {thresh:.2f} | {n} | {hr:.3f} | {avg_conf:.3f} | {(avg_conf - hr):+.3f} |")

    # ── TABLE 2 — Confident directional calls ──
    log.info("")
    log.info("=" * 70)
    log.info("TABLE 2 — CONFIDENT DIRECTIONAL CALLS (top-prob ≥ 0.55, predicted ∈ {2U, 2D})")
    log.info("=" * 70)

    conf_dir_mask = (top_prob >= 0.55) & (
        (pred_idx == LABEL_TO_IDX["2U"]) | (pred_idx == LABEL_TO_IDX["2D"]))
    conf_rep = rep[conf_dir_mask].copy()
    if len(conf_rep) == 0:
        log.info("(no confident directional calls in the test week)")
    else:
        log.info("| timestamp ET | prev | P(1) | P(2U) | P(2D) | P(3) | pred | top_p | actual | result | open | high | low | close |")
        log.info("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in conf_rep.iterrows():
            mark = "HIT ✓" if (r["predicted"] == r["actual"]) else "MISS ✗"
            log.info(f"| {r['ts'].strftime('%a %m-%d %H:%M')} | {r['prev_strat']} "
                     f"| {r['p1']:.2f} | {r['p2u']:.2f} | {r['p2d']:.2f} | {r['p3']:.2f} "
                     f"| {r['predicted']} | {r['top_prob']:.2f} | {r['actual']} | {mark} "
                     f"| {r['open']:.2f} | {r['high']:.2f} | {r['low']:.2f} | {r['close']:.2f} |")

        n_calls = len(conf_rep)
        n_hits = int((conf_rep["predicted"] == conf_rep["actual"]).sum())
        log.info("")
        log.info(f"**Tradeable subset (confident + directional, top-prob ≥ 0.55):**")
        log.info(f"- n calls: {n_calls}")
        log.info(f"- hits: {n_hits}")
        log.info(f"- hit rate: {n_hits/n_calls:.3f}")

    log.info("=" * 70)
    log.info("REPORT COMPLETE")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
