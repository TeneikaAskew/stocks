#!/usr/bin/env python3
"""Cloud Run Job: live per-bar magnitude inference.

Phase B of magnitude-engine productionization (Phase A added the
per-bar predictions table). This job:

  1. Loads the canonical production model artifact from GCS for each
     (ticker, tf) cell. The artifact is the LightGBM model + feature
     spec persisted by mag_walk_forward (Phase B prerequisite: the
     walk-forward must have been run with --persist-production-model
     at least once per cell).

  2. Loads today's most-recent feature rows from strat_features_5m
     (or strat_features_15m / _30m for the corresponding tf) for each
     ticker that should be scored.

  3. Calls model.predict_proba on those rows, producing per-bar
     probability distributions across {TIGHT, NORMAL, EXPANDED,
     EXPLOSIVE}.

  4. Upserts to magnitude_per_bar_predictions with source='inference'
     and model_version=<artifact version tag>.

  5. Surfaces zero-output as a hard failure (no silent fallback per
     CLAUDE.md §3.7 — if today's bars are missing or the model can't
     load, exit 1 so the failure-notifier opens an issue).

Scheduled daily at 09:25 ET (`magnitude-inference-daily`), 5 minutes
before market open so the prior-session bars from strat_features
have settled but new bars haven't started arriving yet.

For the gate-7 caveat — these predictions are SIZING/FILTERING/STRIKE-
SELECTION inputs, not a standalone non-directional trade signal. See
docs/MAGNITUDE_ENGINE_RESULTS.md for the verdict context.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Add project root for gcp.* / lib.* imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gcp.database import get_engine, query_to_dataframe  # noqa: E402
from gcp.research.magnitude_engine.mag_config import (  # noqa: E402
    LABEL_CLASSES, LABEL_TO_IDX,
)
from gcp.research.magnitude_engine.mag_walk_forward import (  # noqa: E402
    PREDICTIONS_DDL_CREATE, PREDICTIONS_DDL_INDEX,
)
from lib.logging_config import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger(__name__)

# Default cells. Override via INFERENCE_CELLS env var as
# "TICKER:TF,TICKER:TF,...". 5m is the only TF where the docs found
# stable signal in IWM/SPY/QQQ (see MAGNITUDE_ENGINE_RESULTS.md §6).
# 15m/30m get retrained models but aren't scored live — they failed
# gate 1 (log-loss) in the original audit.
DEFAULT_CELLS: list[tuple[str, str]] = [
    ("IWM", "5m"),
    ("SPY", "5m"),
    ("QQQ", "5m"),
]

# Lookback for "today's" inference. The job runs at 09:25 ET; the
# most recent settled bars are from yesterday's close. Pull the last
# 24h of bars and score every one that doesn't already have a
# prediction at the same (ticker, tf, ts, model_version).
INFERENCE_LOOKBACK_HOURS = 24


def _parse_cells(spec: Optional[str]) -> list[tuple[str, str]]:
    """'IWM:5m,SPY:5m' -> [('IWM','5m'), ('SPY','5m')].

    Empty / unset -> DEFAULT_CELLS.
    """
    if not spec or not spec.strip():
        return list(DEFAULT_CELLS)
    out: list[tuple[str, str]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"bad INFERENCE_CELLS item {item!r} — expected TICKER:TF")
        t, tf = item.split(":", 1)
        out.append((t.strip().upper(), tf.strip()))
    if not out:
        raise ValueError("INFERENCE_CELLS produced no cells")
    return out


def _gcs_model_path(ticker: str, tf: str) -> str:
    """Canonical GCS path for the production model artifact.

    Layout: gs://<bucket>/magnitude-models/production/IWM/5m/model.joblib
    The version label comes from a sibling VERSION file with the
    walk-forward run_id that produced it.
    """
    bucket = os.environ.get("GCS_BUCKET",
                            "adept-mountain-474619-d4-trading-data")
    return f"gs://{bucket}/magnitude-models/production/{ticker}/{tf}"


def _load_model_and_version(ticker: str, tf: str) -> tuple[object, list[str], str]:
    """Load (model, feature_cols, model_version) for the given cell.

    Returns the model with a `.predict_proba` interface (joblib-pickled
    LightGBMClassifier or CalibratedClassifierCV) plus the ordered
    feature columns the model was trained on, plus a version string
    persisted alongside.

    Raises FileNotFoundError if the artifact is missing — caller must
    decide whether to skip or fail. The default policy here is FAIL —
    no silent fallback.
    """
    import joblib
    from google.cloud import storage as gcs

    bucket_name = os.environ.get("GCS_BUCKET",
                                  "adept-mountain-474619-d4-trading-data")
    base_prefix = f"magnitude-models/production/{ticker}/{tf}"

    client = gcs.Client()
    bucket = client.bucket(bucket_name)
    # Atomic-publish layout (#615): LATEST is a pointer to a per-run
    # subprefix. Reading it last is what makes the artifact set consistent
    # — model.joblib + feature_cols.txt + VERSION at <base>/<run_id>/ are
    # guaranteed to belong together because the operator only flips
    # LATEST after all three uploads succeed.
    latest_blob = bucket.blob(f"{base_prefix}/LATEST")
    if not latest_blob.exists():
        raise FileNotFoundError(
            f"no production model deployed for {ticker}:{tf} — LATEST "
            f"pointer missing at gs://{bucket_name}/{base_prefix}/LATEST. "
            f"Run walk_forward with --persist-production-model to publish."
        )
    run_id = latest_blob.download_as_text().strip()
    prefix = f"{base_prefix}/{run_id}"
    model_blob = bucket.blob(f"{prefix}/model.joblib")
    version_blob = bucket.blob(f"{prefix}/VERSION")
    features_blob = bucket.blob(f"{prefix}/feature_cols.txt")

    if not model_blob.exists():
        raise FileNotFoundError(
            f"production model missing for {ticker}:{tf} — LATEST points "
            f"at run={run_id} but model.joblib is missing at "
            f"gs://{bucket_name}/{prefix}/model.joblib"
        )

    # Download to a temp file (joblib.load can't take a stream cleanly
    # for sklearn models). Tempfile cleanup happens by GC.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".joblib") as tf_file:
        model_blob.download_to_filename(tf_file.name)
        model = joblib.load(tf_file.name)

    version = (version_blob.download_as_text().strip()
               if version_blob.exists() else "unknown")
    feature_cols = (features_blob.download_as_text().strip().split("\n")
                    if features_blob.exists() else None)
    if not feature_cols:
        raise RuntimeError(
            f"feature_cols.txt missing for {ticker}:{tf} — cannot align"
            " inference features with training schema"
        )

    return model, feature_cols, version


def _load_recent_features(ticker: str, tf: str,
                           lookback_hours: int = INFERENCE_LOOKBACK_HOURS
                           ) -> pd.DataFrame:
    """Pull the most-recent feature rows for scoring.

    MUST mirror the TRAINING loader (strat_dataset.load_labeled_dataset): the
    model is trained on `strat_features_{tf}` LEFT JOIN
    `strat_features_levels_{tf}` (the ORB / historical-level / order-block
    enrichment columns). Loading strat_features ALONE drops those
    non-categorical columns, so every cell fails the alignment check in
    _score_and_persist with "feature drift" on e.g. orb_5m_high. Falls back to
    plain features if the levels table is missing for this TF — same contract
    as training.
    """
    from sqlalchemy import text
    from gcp.research.strat_engine.strat_enrich_levels import levels_table

    s_table = f"strat_features_{tf}"
    l_table = levels_table(tf)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    params = {"t": ticker, "cutoff": cutoff.isoformat()}
    engine = get_engine()
    try:
        sql = text(
            f"SELECT s.*, l.* FROM {s_table} s "
            f"LEFT JOIN {l_table} l ON l.ticker = s.ticker AND l.ts = s.ts "
            f"WHERE s.ticker = :t AND s.ts >= :cutoff ORDER BY s.ts ASC"
        )
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
    except Exception as e:
        log.warning("levels join failed (%s); falling back to plain features",
                    type(e).__name__)
        sql = text(
            f"SELECT * FROM {s_table} s "
            f"WHERE s.ticker = :t AND s.ts >= :cutoff ORDER BY s.ts ASC"
        )
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
    # Deduplicate the ticker/ts columns that `s.*, l.*` duplicates (mirror
    # load_labeled_dataset).
    df = df.loc[:, ~df.columns.duplicated()]
    if df.empty:
        log.warning("no bars in %s for %s since %s", s_table, ticker, cutoff)
    return df


def _score_and_persist(engine, ticker: str, tf: str,
                        model, feature_cols: list[str], version: str,
                        features: pd.DataFrame) -> int:
    """Run model.predict_proba and upsert results. Returns rows written."""
    if features.empty:
        return 0

    # NaN guard on the RAW frame — drop rows whose ESSENTIAL price inputs
    # (OHLCV) are NaN, BEFORE featurize() fills the rest with 0. A settled bar
    # always has OHLCV; a NaN there means the upstream builder hasn't populated
    # the row (session boundary) and scoring it would ship a zero-filled
    # prediction tagged as real inference.
    #
    # We deliberately guard ONLY OHLCV, not every numeric column, because:
    #   - Engineered features (order_block, gamma/vex/vix, ORB, indicators) are
    #     legitimately sparse or vendor-gapped and are featurize()-filled at
    #     TRAIN time. Dropping a bar for their NaN makes inference stricter than
    #     training and zeroes output.
    #   - Forward-looking label columns (fwd_*) are NULL on the most-recent bars
    #     (the future hasn't happened) and are not model inputs at all — guarding
    #     them dropped exactly the fresh bars we exist to score.
    #   - The old "any numeric NaN" guard was dtype-dependent: an all-NULL column
    #     read back object-typed and was silently skipped, while a partially
    #     populated one was float64 and enforced. So a ticker with SOME sparse
    #     data (QQQ's order blocks: 27/156 populated) lost every bar, while one
    #     with none (IWM: all-NULL order_block) passed — a ticker-dependent
    #     asymmetry that produced QQQ's persistent ZERO-OUTPUT.
    import numpy as np
    _ESSENTIAL_RAW = ("open", "high", "low", "close", "volume")
    essential_cols = [
        c for c in features.columns
        if c.lower() in _ESSENTIAL_RAW
        and pd.api.types.is_numeric_dtype(features[c].dtype)
    ]
    if not essential_cols:
        # INTERNAL invariant: strat_features_<tf> always has OHLCV. An empty
        # set means schema drift — fail loud rather than silently score every
        # row with no guard at all.
        raise RuntimeError(
            f"{ticker}:{tf} — feature frame is missing the essential OHLCV "
            f"columns {_ESSENTIAL_RAW}; cannot apply the raw NaN guard")
    nan_mask = features[essential_cols].isna().any(axis=1).to_numpy()
    if nan_mask.any():
        log.info("%s:%s — %d/%d bars missing essential OHLCV; skipping those",
                 ticker, tf, int(nan_mask.sum()), len(features))
        features = features.loc[~nan_mask].reset_index(drop=True)
    if len(features) == 0:
        log.warning("%s:%s — zero scorable bars after essential NaN filter", ticker, tf)
        return 0

    # CRITICAL — apply the SAME preprocessing the training pipeline used
    # (Codex P1 #615). `feature_cols` was captured AFTER mag_pred_train.
    # featurize() one-hot encoded CATEGORICAL_FEATURES (prev1_candle,
    # prev2_candle, …) and dropped forward-looking columns. The raw
    # SELECT * frame from strat_features_<tf> does NOT have the dummy
    # column names — without running featurize() here, every alignment
    # check fails with "feature drift" and the cron raises on every cell.
    from gcp.research.magnitude_engine.mag_pred_train import featurize
    # Preserve `ts` for the persistence loop below, since featurize drops
    # it (it's not a model input). Re-attach after the transform.
    ts_series = features["ts"].reset_index(drop=True)
    enc, _live_cols = featurize(features)
    enc = enc.reset_index(drop=True)
    # Some training-time dummy columns may be absent from a given live
    # window (e.g. a rare prev1_candle category that didn't occur today).
    # Fabricating them as zeros is the CORRECT one-hot semantics — not a
    # silent fallback. We DO NOT fabricate any non-dummy numeric column;
    # if a real numeric is missing, that's still a hard error.
    for col in feature_cols:
        if col not in enc.columns:
            # Heuristic: training-time one-hot dummies look like
            # `<categorical>_<value>`; raw numerics don't. Anything that
            # matches a known CATEGORICAL prefix is safe to zero-fill
            # (correct one-hot semantics for a value that didn't occur
            # in the live window — NOT a silent fallback).
            from gcp.research.strat_engine.strat_config import (
                CATEGORICAL_FEATURES,
            )
            if any(col.startswith(f"{c}_") for c in CATEGORICAL_FEATURES):
                enc[col] = np.int8(0)
            else:
                raise RuntimeError(
                    f"feature drift for {ticker}:{tf} — model expects "
                    f"non-categorical column {col!r} which featurize() did "
                    f"not produce from the live frame. Schema may have "
                    f"changed since the model was trained (run={version})."
                )
    # Rebuild features as a DataFrame keyed to (ts, feature_cols)
    features = pd.concat(
        [ts_series.rename("ts"), enc[feature_cols]],
        axis=1,
    )
    # No more missing-column check needed — we either added zero-dummies
    # above or raised on a real numeric drift. Raw NaN was already
    # filtered earlier; featurize() then fillna(0)'d any infs.
    X = features[feature_cols].to_numpy()

    proba = model.predict_proba(X)
    if proba.shape[1] != len(LABEL_CLASSES):
        raise RuntimeError(
            f"{ticker}:{tf} — model returned {proba.shape[1]} classes;"
            f" expected {len(LABEL_CLASSES)} ({LABEL_CLASSES})"
        )

    pred_bucket = proba.argmax(axis=1)
    max_proba = proba.max(axis=1)

    rows = []
    for i in range(len(features)):
        rows.append({
            "ticker": ticker, "tf": tf,
            "ts": features["ts"].iloc[i],
            "p_tight":     float(proba[i, LABEL_TO_IDX["TIGHT"]]),
            "p_normal":    float(proba[i, LABEL_TO_IDX["NORMAL"]]),
            "p_expanded":  float(proba[i, LABEL_TO_IDX["EXPANDED"]]),
            "p_explosive": float(proba[i, LABEL_TO_IDX["EXPLOSIVE"]]),
            "pred_bucket": int(pred_bucket[i]),
            "max_proba":   float(max_proba[i]),
            "model_version": version,
            "fold_label": None,
            "source": "inference",
        })

    df = pd.DataFrame(rows)
    # Use INSERT ... ON CONFLICT DO UPDATE so re-runs of the same job
    # against overlapping bar windows are idempotent.
    from sqlalchemy import text
    with engine.begin() as conn:
        for chunk_start in range(0, len(df), 1000):
            chunk = df.iloc[chunk_start:chunk_start + 1000]
            # Build a multi-row INSERT with ON CONFLICT (...) DO UPDATE
            cols = list(chunk.columns)
            placeholders = ",".join(
                "(" + ",".join(f":{c}_{i}" for c in cols) + ")"
                for i in range(len(chunk))
            )
            update_clause = ", ".join(f"{c}=EXCLUDED.{c}"
                                       for c in cols
                                       if c not in ("ticker", "tf", "ts",
                                                    "model_version"))
            stmt = text(f"""
                INSERT INTO magnitude_per_bar_predictions ({",".join(cols)})
                VALUES {placeholders}
                ON CONFLICT (ticker, tf, ts, model_version)
                DO UPDATE SET {update_clause}
            """)
            params: dict = {}
            for i, (_, row) in enumerate(chunk.iterrows()):
                for c in cols:
                    params[f"{c}_{i}"] = row[c]
            conn.execute(stmt, params)
    return len(df)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cells", default=os.environ.get("INFERENCE_CELLS"),
                    help="Override DEFAULT_CELLS, e.g. 'IWM:5m,SPY:5m'")
    ap.add_argument("--lookback-hours", type=int,
                    default=int(os.environ.get("INFERENCE_LOOKBACK_HOURS",
                                                INFERENCE_LOOKBACK_HOURS)))
    args = ap.parse_args()

    cells = _parse_cells(args.cells)
    log.info("mag_inference starting — cells=%s lookback=%dh",
             cells, args.lookback_hours)

    engine = get_engine()
    # Ensure DDL — race-safe (CREATE TABLE IF NOT EXISTS).
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text(PREDICTIONS_DDL_CREATE))
        conn.execute(text(PREDICTIONS_DDL_INDEX))

    total_written = 0
    failures: list[tuple[str, str, str]] = []
    for ticker, tf in cells:
        try:
            model, feature_cols, version = _load_model_and_version(ticker, tf)
            features = _load_recent_features(ticker, tf, args.lookback_hours)
            n = _score_and_persist(engine, ticker, tf,
                                    model, feature_cols, version, features)
            log.info("%s:%s — %d predictions written (model_version=%s)",
                     ticker, tf, n, version)
            total_written += n
        except Exception as e:
            log.exception("%s:%s failed: %s", ticker, tf, e)
            failures.append((ticker, tf, str(e)))

    log.info("mag_inference done — %d total predictions, %d cell failure(s)",
             total_written, len(failures))

    # Zero-output is itself a silent-failure mode (Codex P1 on PR #597):
    # if every cell quietly produces 0 scorable rows (empty features
    # window, all-NaN, or some other data outage that doesn't raise),
    # the cell loop finishes with no `failures` entries and we'd exit 0
    # — making a data outage look like a healthy run. Treat
    # total_written == 0 as a hard failure independent of the
    # per-cell exception count. This is the same CLAUDE.md §3.7
    # silent-fallback class that F11 surfaced for historical-signals-
    # watchlist (qjllq 2026-06-02): "exit 0 while writing nothing".
    if total_written == 0:
        log.error("ZERO-OUTPUT — no predictions written across any cell; "
                  "treating as failure (data outage or universal NaN filter)")
        return 1

    # No silent fallback: any cell failure is a real production issue.
    # Half-or-more failures -> exit 1 so failure-notifier opens an issue.
    # Matches the F11 pattern from
    # docs/incidents/2026-06-01-pipeline-failures-audit.md.
    if failures and len(failures) > len(cells) // 2:
        log.error("TOO-MANY-FAILURES — %d/%d cells failed: %s",
                  len(failures), len(cells), failures)
        return 1
    if failures:
        log.warning("partial success — %d/%d cells failed (under 50%% threshold)",
                    len(failures), len(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
