"""Strat Engine — single-prediction serving module.

The frozen production strat type model produces a calibrated probability
distribution over {1, 2U, 2D, 3} for the next candle's structure type.
This module wraps the model artifacts and exposes a single function
`predict_one(...)` that returns ONE bar's prediction for a given
(ticker, timeframe, optional as_of).

Used by:
  - `POST /api/admin/strat-engine/predict` — the admin-gated FastAPI
    endpoint that returns predictions on-demand
  - Future read-only consumers (e.g. an offline analysis notebook)

The model is FROZEN. This module does not retrain, recalibrate, or
modify any artifact. It only loads from GCS and queries Cloud SQL.

Artifact layout (GCS, written by `strat_pred_train.py`):
  gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/model.pkl
  gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/features.txt
  gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/classes.txt
  gs://${BUCKET}/research/strat_engine/{ticker}_{tf}/metrics.json
"""
from __future__ import annotations

import io
import json
import logging
import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.research.strat_engine.strat_config import (
    LABEL_CLASSES,
    GCS_BUCKET_DEFAULT,
    gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize

log = logging.getLogger(__name__)


STRUCTURE_BRIEF_ECE_CEILING = 0.05
SCOPE_STATEMENT = (
    "Calibrated structure prediction. Not a directional or P&L edge. "
    "Use with discretion."
)


def _gcs_client():
    from google.cloud import storage as gcs
    return gcs.Client()


def _gcs_load_bytes(blob_path: str) -> Optional[bytes]:
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    try:
        client = _gcs_client()
        blob = client.bucket(bucket_name).blob(blob_path)
        if not blob.exists():
            return None
        return blob.download_as_bytes()
    except Exception as e:
        log.warning("GCS load failed for %s: %s", blob_path, e)
        return None


def _load_model(ticker: str, tf: str):
    """Load the frozen production model artifact from GCS for (ticker, tf)."""
    prefix = gcs_model_prefix(ticker, tf)
    pkl_bytes = _gcs_load_bytes(f"{prefix}/model.pkl")
    if pkl_bytes is None:
        return None
    return pickle.loads(pkl_bytes)


def _load_metrics(ticker: str, tf: str) -> dict:
    """Load the metrics.json sidecar for (ticker, tf).

    Includes the training-run identifier (used as model_version) and
    the last training date. Returns empty dict if missing.
    """
    prefix = gcs_model_prefix(ticker, tf)
    raw = _gcs_load_bytes(f"{prefix}/metrics.json")
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _load_live_ece_snapshot() -> dict:
    """Load the rolling-live-ECE snapshot if present.

    The snapshot is written by an upstream monitor that is out of scope
    for this module. When absent, every cell falls back to live_ece=None
    and is NOT muted.
    """
    bucket_name = os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT)
    raw = _gcs_load_bytes("research/strat_engine/structure_brief_latest.json")
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _decide_mute(live_ece: Optional[float],
                  ceiling: float = STRUCTURE_BRIEF_ECE_CEILING) -> tuple[bool, Optional[str]]:
    if live_ece is None:
        return False, None
    if live_ece > ceiling:
        return True, (
            f"model muted, ECE breach (live ECE {live_ece:.3f} "
            f"> ceiling {ceiling:.3f})"
        )
    return False, None


def predict_one(
    engine,
    ticker: str,
    tf: str,
    as_of: Optional[pd.Timestamp] = None,
) -> dict:
    """Predict the next bar's structure-type distribution for (ticker, tf).

    Args:
      engine: SQLAlchemy engine from `gcp.database.get_engine()`.
      ticker: one of the deployed cells (IWM, SPY, QQQ in prod scope).
      tf: one of the deployed timeframes (5m, 15m, 30m in prod scope).
      as_of: optional ISO timestamp. If provided, use the bar whose
             `ts` is the latest <= as_of. If None, use the most recent
             bar in the labeled dataset.

    Returns a dict with the contract used by
    `POST /api/admin/strat-engine/predict`:
      top_class, top_prob, class_probs,
      model_version, last_train_date, live_ece, muted, mute_reason,
      scope_statement, ticker, timeframe, ts, available, note
    """
    response = {
        "ticker": ticker,
        "timeframe": tf,
        "available": False,
        "top_class": None,
        "top_prob": None,
        "class_probs": {},
        "model_version": None,
        "last_train_date": None,
        "live_ece": None,
        "muted": False,
        "mute_reason": None,
        "scope_statement": SCOPE_STATEMENT,
        "ts": None,
        "note": None,
    }

    model = _load_model(ticker, tf)
    if model is None:
        response["note"] = (
            f"No model.pkl found at gs://${{BUCKET}}/research/strat_engine/"
            f"{ticker.lower()}_{tf}/. Dispatch the strat-engine Cloud Run "
            "Job to train and save the artifact before calling this endpoint."
        )
        return response

    metrics = _load_metrics(ticker, tf)
    response["model_version"] = (
        metrics.get("run_id")
        or metrics.get("config_signature")
        or metrics.get("model_version")
    )
    response["last_train_date"] = (
        metrics.get("trained_at")
        or metrics.get("computed_at")
        or metrics.get("train_until")
    )

    # Apply live-ECE mute first. If the cell is muted we hide the
    # prediction values but still return the metadata.
    snap = _load_live_ece_snapshot()
    cell_key = f"{ticker}_{tf}"
    cell_snap = snap.get("cells", {}).get(cell_key, {}) if snap else {}
    live_ece = cell_snap.get("live_ece")
    response["live_ece"] = live_ece
    muted, mute_reason = _decide_mute(live_ece)
    response["muted"] = muted
    response["mute_reason"] = mute_reason
    if muted:
        response["available"] = True
        response["note"] = mute_reason
        return response

    # Load features. We use the labeled dataset loader so the featurize
    # pipeline matches training exactly. Then pick one row.
    df = load_labeled_dataset(
        engine, ticker, tf,
        # Cap the lookback to the most recent ~30 days of bars for
        # efficiency. We only need the latest bar (or as_of).
        since=(pd.Timestamp.utcnow() - pd.Timedelta(days=30)).date().isoformat(),
    )
    if as_of is not None:
        as_of_ts = pd.to_datetime(as_of, utc=True)
        mask = pd.to_datetime(df["ts"], utc=True) <= as_of_ts
        df = df[mask]
    if df.empty:
        response["note"] = (
            f"No features available in the lookback window for {ticker} {tf}"
            + (f" up to {as_of}" if as_of else "")
            + ". The strat-features tables may be stale; re-run the data "
              "build pipeline."
        )
        return response

    # The latest row in the labeled set is the most recent fully-labeled
    # bar — i.e. the prediction is FOR the bar after that one (next bar).
    latest = df.iloc[[-1]].copy()
    response["ts"] = pd.to_datetime(latest["ts"].iloc[0], utc=True).isoformat()

    X, cols = featurize(latest)
    # Align to model's expected feature shape. We accept a small drift —
    # any missing columns get filled with 0 (same as training-time reindex).
    expected_cols: Optional[list[str]] = None
    if hasattr(model, "booster_") and hasattr(model.booster_, "feature_name"):
        try:
            expected_cols = list(model.booster_.feature_name())
        except Exception:
            expected_cols = None
    if expected_cols:
        X = X.reindex(columns=expected_cols, fill_value=0).astype(np.float32)
    else:
        X = X.astype(np.float32)

    proba = model.predict_proba(X.values)[0]
    # Align proba to LABEL_CLASSES order
    class_probs = {}
    if hasattr(model, "classes_"):
        for j, idx in enumerate(model.classes_):
            class_probs[LABEL_CLASSES[int(idx)]] = float(proba[j])
    else:
        for j, cls in enumerate(LABEL_CLASSES):
            class_probs[cls] = float(proba[j])
    # Ensure all four classes are present (zero-pad rare-class absences)
    for cls in LABEL_CLASSES:
        class_probs.setdefault(cls, 0.0)

    top_cls = max(class_probs, key=class_probs.get)
    response["available"] = True
    response["top_class"] = top_cls
    response["top_prob"] = class_probs[top_cls]
    response["class_probs"] = class_probs
    return response


def main():
    """CLI entry point — for use as `python -m gcp.research.strat_engine.strat_pred_serve`.

    Optional, for one-shot manual predictions during ops. Same args as
    the API endpoint accepts.
    """
    import argparse
    from gcp.database import get_engine

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True)
    p.add_argument("--tf", required=True)
    p.add_argument("--as-of", default=None, help="ISO timestamp; default=latest")
    args = p.parse_args()

    engine = get_engine()
    as_of = pd.to_datetime(args.as_of) if args.as_of else None
    result = predict_one(engine, args.ticker, args.tf, as_of=as_of)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
