"""Stage 5 — FTFC assembly — `strat_ftfc_assemble.py`.

For a given ticker, pulls the calibrated predictions from each TF's saved
model (Stage 4), aligns them on the 1m clock via as-of join, and computes
a continuity score (weighted agreement across TFs).

OUTPUT: rows of (ts, ticker, per-TF top_class + probs, continuity_score,
aligned_direction). One row per 1m bar in OOS.

This is the "stack 1m/5m/15m/30m/60m/4h reads at the same moment" piece
the PRD calls for. It does NOT train any model; it consumes Stage 4 output.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, TF_MINUTES, LABEL_CLASSES, DEFAULT_TRAIN_UNTIL,
    FTFC_WEIGHTS, GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def _gcs_bucket():
    return gcs.Client().bucket(os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT))


def _download(blob_path: str) -> bytes | None:
    b = _gcs_bucket().blob(blob_path)
    return b.download_as_bytes() if b.exists() else None


def _upload(content: bytes, blob_path: str, ctype="application/json"):
    _gcs_bucket().blob(blob_path).upload_from_string(content, content_type=ctype)


def load_model_and_features(ticker: str, tf: str):
    prefix = gcs_model_prefix(ticker, tf)
    mb = _download(f"{prefix}/model.pkl")
    ft = _download(f"{prefix}/features.txt")
    if mb is None or ft is None:
        return None, None
    model = pickle.loads(mb)
    feats = ft.decode().strip().split("\n")
    return model, feats


def score_tf(engine, ticker: str, tf: str, since: str) -> pd.DataFrame | None:
    """Score OOS bars at one TF. Returns DataFrame[ts, p_1, p_2u, p_2d, p_3, top]."""
    model, feats = load_model_and_features(ticker, tf)
    if model is None:
        log.warning("  %s %s: no saved model — skipping (run Stage 4 first)", ticker, tf)
        return None
    df = load_labeled_dataset(engine, ticker, tf, since=since)
    X = featurize(df)[0]
    for c in feats:
        if c not in X.columns: X[c] = 0
    X = X[feats].astype(np.float32)
    proba = model.predict_proba(X.values)

    # Reviewer-flagged 2026-05-25 (item 5): map predict_proba columns
    # through model.classes_ so we're robust to sparse classes (a class
    # missing in training => fewer columns in proba). Index by class label,
    # not position.
    if hasattr(model, "classes_"):
        cls_to_col = {LABEL_CLASSES[c]: i for i, c in enumerate(model.classes_)}
    else:
        cls_to_col = {c: i for i, c in enumerate(LABEL_CLASSES)}

    def _p(cls_label):
        i = cls_to_col.get(cls_label)
        return proba[:, i] if i is not None else np.zeros(len(proba))

    p1 = _p("1"); p2u = _p("2U"); p2d = _p("2D"); p3 = _p("3")
    top_idx = proba.argmax(axis=1)
    inv = {v: k for k, v in cls_to_col.items()}
    top_labels = [inv.get(i, "?") for i in top_idx]

    out = pd.DataFrame({
        "ts": df["ts"].values,
        f"{tf}_p_1":  p1, f"{tf}_p_2u": p2u, f"{tf}_p_2d": p2d, f"{tf}_p_3":  p3,
        f"{tf}_top":  top_labels,
    })

    # Reviewer-flagged 2026-05-25 (item 4): strat_features ts is BAR OPEN
    # (pandas resample defaults to label='left'). For an as-of join to be
    # leak-free, a higher-TF prediction can only be USED after its bar
    # closes. Shift the ts forward by the bar's duration so the join sees
    # the prediction at close, not open.
    duration_min = TF_MINUTES[tf]
    out["ts"] = pd.to_datetime(out["ts"], utc=True) + pd.Timedelta(minutes=duration_min)

    log.info("  %s %s: %d scored bars (ts shifted +%dm = bar-close stamp)",
             ticker, tf, len(out), duration_min)
    return out.sort_values("ts").reset_index(drop=True)


def assemble_ftfc(engine, ticker: str, since: str) -> pd.DataFrame:
    """As-of join all available TFs onto the finest one. Compute continuity."""
    tf_dfs = {}
    for tf in TIMEFRAMES:
        d = score_tf(engine, ticker, tf, since)
        if d is not None and len(d) > 0:
            tf_dfs[tf] = d
    if not tf_dfs:
        raise RuntimeError(f"no TFs have saved models for {ticker} — run Stage 4")

    # Use the finest available TF as the clock
    clock_tf = next((tf for tf in TIMEFRAMES if tf in tf_dfs), None)
    out = tf_dfs[clock_tf].copy()
    log.info("clock TF: %s  (%d bars)", clock_tf, len(out))
    for tf in TIMEFRAMES:
        if tf == clock_tf: continue
        if tf not in tf_dfs: continue
        out = pd.merge_asof(out, tf_dfs[tf], on="ts", direction="backward")

    # Continuity score: weighted sum of agreement on majority direction (2U vs 2D)
    # per-TF direction in {-1, 0, +1} = (p_2u - p_2d > 0.05) - (p_2d - p_2u > 0.05)
    # weighted by FTFC_WEIGHTS, normalized by sum of weights of present TFs
    present = [tf for tf in TIMEFRAMES if tf in tf_dfs]
    w_total = sum(FTFC_WEIGHTS.get(tf, 0) for tf in present)
    cont = np.zeros(len(out))
    for tf in present:
        edge = out[f"{tf}_p_2u"] - out[f"{tf}_p_2d"]
        sign = np.where(edge > 0.05, 1.0, np.where(edge < -0.05, -1.0, 0.0))
        cont += sign * FTFC_WEIGHTS.get(tf, 0)
    out["continuity_score"] = cont / max(w_total, 1e-9)
    out["aligned_direction"] = np.where(
        out["continuity_score"] > 0.5, "UP",
        np.where(out["continuity_score"] < -0.5, "DOWN", "MIXED"))
    out["ticker"] = ticker

    log.info("FTFC summary:")
    log.info("  rows: %d  TFs joined: %s", len(out), present)
    log.info("  continuity distribution: mean=%+.3f std=%.3f",
             out["continuity_score"].mean(), out["continuity_score"].std())
    log.info("  aligned_direction counts: %s",
             out["aligned_direction"].value_counts().to_dict())
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--since", default=DEFAULT_TRAIN_UNTIL,
                   help="Score OOS bars from this date forward")
    args = p.parse_args()
    engine = get_engine()
    out = assemble_ftfc(engine, args.ticker, args.since)

    # Save head/tail samples + summary to GCS (avoid uploading huge full CSV)
    prefix = f"research/strat_engine/_ftfc/{args.ticker.lower()}"
    sample = pd.concat([out.head(50), out.tail(50)])
    _upload(sample.to_csv(index=False).encode(),
            f"{prefix}/sample_{int(time.time())}.csv", "text/csv")
    summary = {
        "ticker": args.ticker, "n_rows": int(len(out)),
        "tfs_with_models": [tf for tf in TIMEFRAMES
                            if load_model_and_features(args.ticker, tf)[0] is not None],
        "continuity_mean": float(out["continuity_score"].mean()),
        "continuity_std": float(out["continuity_score"].std()),
        "aligned_direction_counts": out["aligned_direction"].value_counts().to_dict(),
        "ts_min": str(out["ts"].min()),
        "ts_max": str(out["ts"].max()),
    }
    _upload(json.dumps(summary, indent=2, default=str).encode(),
            f"{prefix}/summary_{int(time.time())}.json")
    log.info("saved sample + summary to gs://%s/%s/",
             os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), prefix)


if __name__ == "__main__":
    main()
