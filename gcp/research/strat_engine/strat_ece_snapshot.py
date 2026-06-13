"""Strat Engine — live ECE snapshot writer.

Computes rolling-window Expected Calibration Error for each deployed
(ticker, timeframe) cell and writes a single GCS JSON snapshot consumed
by `/api/admin/structure-brief` and `/api/admin/strat-engine/predict`
for the self-mute decision.

The structure-brief mute logic activates when a cell's live ECE exceeds
the per-cell ceiling (0.05). Without this snapshot, the mute path is a
no-op — `live_ece` is null and the brief always renders the model's
prediction. With this snapshot, the brief hides the prediction when the
calibration health drifts.

WHEN TO RUN

On-demand only. There is NO scheduler trigger. The activation gate in
`docs/STRAT_ENGINE_OPERATIONS.md` §8 governs whether this ever moves to
a scheduler.

CALL PATH

  python -m gcp.research.strat_engine.strat_ece_snapshot
  python -m gcp.research.strat_engine.strat_ece_snapshot --window-days=20

Or as a Cloud Run Job:

  gcloud run jobs execute strat-engine \\
    --args="-m,gcp.research.strat_engine.strat_ece_snapshot,--window-days=20"

OUTPUT (single GCS object, atomic upload):

  gs://${BUCKET}/research/strat_engine/structure_brief_latest.json

Schema (consumed by `_load_structure_brief_snapshot`):

  {
    "cells": {
      "IWM_15m": {
        "distribution": {"1": 0.10, "2U": 0.62, "2D": 0.23, "3": 0.05},
        "live_ece": 0.025,
        "refreshed_at": "2026-05-27T20:45:00+00:00",
        "n_window": 440,
        "model_version": "epoch-1779781975",
        "last_train_date": "2026-05-26T07:52:55+00:00"
      },
      "IWM_5m": { ... },
      ...
    },
    "ece_ceiling": 0.05,
    "computed_at": "2026-05-27T20:45:00+00:00",
    "window_days": 20
  }

The mute decision is downstream: when `live_ece > ece_ceiling`, the brief
strips the prediction and shows the mute reason instead. This module
just publishes the readings.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    LABEL_CLASSES, LABEL_COL, LABEL_TO_IDX,
    GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import (
    expected_calibration_error, featurize,
)
from gcp.research.strat_engine.strat_pred_serve import (
    _load_model, _load_metrics, _load_features_list, _load_classes_list,
)
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


DEPLOYED_TICKERS = ("IWM", "SPY", "QQQ")
DEPLOYED_TFS = ("5m", "15m", "30m")
ECE_CEILING = 0.05
SNAPSHOT_BLOB = "research/strat_engine/structure_brief_latest.json"


def _gcs_upload_json(content: dict, blob_path: str) -> str:
    """Upload a JSON document to GCS, returning the gs:// URI."""
    from google.cloud import storage as gcs
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    client = gcs.Client()
    blob = client.bucket(bucket_name).blob(blob_path)
    blob.upload_from_string(
        json.dumps(content, indent=2, default=str),
        content_type="application/json",
    )
    return f"gs://{bucket_name}/{blob_path}"


def compute_cell_snapshot(engine, ticker: str, tf: str,
                            window_days: int) -> Optional[dict]:
    """Compute the rolling-window ECE + latest distribution for one cell.

    Returns None when the model artifacts aren't available; the consumer
    treats that as "no live snapshot for this cell" (the brief still
    renders, just without an ECE reading and not muted).
    """
    log.info("snapshot cell %s %s window=%dd", ticker, tf, window_days)
    model = _load_model(ticker, tf)
    if model is None:
        log.warning("  no model.pkl found — skipping cell")
        return None

    metrics = _load_metrics(ticker, tf)
    expected_cols = _load_features_list(ticker, tf)
    saved_classes = _load_classes_list(ticker, tf) or list(LABEL_CLASSES)

    # Pull the last `window_days` of labeled bars. We compute ECE on the
    # most recent N closed bars (where labels are known — i.e. the bar
    # after them has resolved). The very latest bar in the dataset has
    # an actionable prediction; the previous (window_days - 1) days are
    # the ECE evaluation window.
    since = (pd.Timestamp.utcnow() - pd.Timedelta(days=window_days)).date().isoformat()
    df = load_labeled_dataset(engine, ticker, tf, since=since)
    if df.empty:
        log.warning("  empty dataset for %s %s since %s — skipping", ticker, tf, since)
        return None

    X, _ = featurize(df)
    if expected_cols:
        X = X.reindex(columns=expected_cols, fill_value=0).astype(np.float32)
    else:
        X = X.astype(np.float32)

    proba = model.predict_proba(X.values)
    y = df[LABEL_COL].map(LABEL_TO_IDX).values

    # Align proba columns to LABEL_CLASSES order
    aligned = np.zeros((proba.shape[0], len(LABEL_CLASSES)), dtype=np.float64)
    if hasattr(model, "classes_"):
        for j, internal in enumerate(model.classes_):
            if isinstance(internal, (int, np.integer)):
                aligned[:, int(internal)] = proba[:, j]
            else:
                try:
                    idx = saved_classes.index(str(internal))
                    aligned[:, idx] = proba[:, j]
                except ValueError:
                    continue
        proba = aligned

    # ECE over the window. We use ALL bars in the window — that's the
    # rolling-window ECE the mute logic checks against the ceiling.
    ece, _bins = expected_calibration_error(y, proba, n_bins=10)
    log.info("  n=%d ECE=%.4f (ceiling %.3f, %s)",
             len(y), ece, ECE_CEILING, "MUTE" if ece > ECE_CEILING else "OK")

    # Latest-bar distribution — the prediction the brief surfaces.
    latest_proba = proba[-1]
    distribution = {}
    for k, cls in enumerate(LABEL_CLASSES):
        distribution[cls] = float(latest_proba[k])

    refreshed_at = pd.Timestamp.utcnow().isoformat()
    return {
        "distribution": distribution,
        "live_ece": float(ece),
        "refreshed_at": refreshed_at,
        "n_window": int(len(y)),
        "model_version": metrics.get("run_id") or metrics.get("model_version"),
        "last_train_date": (
            metrics.get("trained_at")
            or metrics.get("computed_at")
            or metrics.get("train_until")
        ),
    }


def run_snapshot(engine, window_days: int = 20) -> dict:
    """Compute snapshots for every deployed cell and write the GCS file."""
    cells: dict = {}
    for ticker in DEPLOYED_TICKERS:
        for tf in DEPLOYED_TFS:
            try:
                snap = compute_cell_snapshot(engine, ticker, tf, window_days)
            except Exception as exc:
                log.exception("cell %s %s failed: %s", ticker, tf, exc)
                snap = None
            if snap is not None:
                cells[f"{ticker}_{tf}"] = snap
    payload = {
        "cells": cells,
        "ece_ceiling": ECE_CEILING,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
        "window_days": window_days,
    }
    uri = _gcs_upload_json(payload, SNAPSHOT_BLOB)
    log.info("snapshot written: %s (cells=%d)", uri, len(cells))
    return payload


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--window-days", type=int, default=20,
        help="Rolling window over which to compute ECE (default 20)",
    )
    args = p.parse_args()
    engine = get_engine()
    payload = run_snapshot(engine, window_days=args.window_days)
    print(json.dumps({"cells_written": len(payload["cells"]),
                       "ece_ceiling": payload["ece_ceiling"]}))


if __name__ == "__main__":
    main()
