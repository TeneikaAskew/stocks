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
#
# This window is anchored to the LAST AVAILABLE BAR in strat_features_<tf>
# (see _last_settled_ts), not to wall-clock now(). A fixed now()-24h anchor
# broke every Monday: Friday's RTH session ends ~13:30 ET / 19:55 UTC, and
# Monday's 09:25 ET run is ~65h later — 2.7x the 24h window — so
# now()-24h landed on Sunday and captured zero bars for all three cells,
# hard-failing as ZERO-OUTPUT (magnitude-inference-dmvxr 2026-06-29,
# magnitude-inference-h7h6g 2026-06-22). Anchoring to the last settled bar
# instead means the window always starts from the most recent trading
# session regardless of how many calendar days a weekend/holiday spans, and
# it silently closed a second bug: with the old anchor, Friday's session
# was NEVER scored by any run (Monday's window missed it; Friday's own
# pre-market run only reaches Thursday) — a permanent weekly gap in
# magnitude_per_bar_predictions, not just a noisy failure email.
#
# The anchor is bounded by MAX_ANCHOR_STALENESS_HOURS below: an unbounded
# anchor would defeat the ZERO-OUTPUT hard-fail for the OTHER outage this
# job exists to catch — a stalled strat_features_<tf> writer (e.g. the
# strat-engine-daily scheduler itself breaking, as happened 2026-06-09 ->
# 06-19). In that case _last_settled_ts still returns a real (but stale)
# timestamp, so anchoring to it unconditionally would keep re-scoring the
# same old bars, upsert a positive row count, and exit 0 — silently masking
# the outage this hard-fail exists to surface (flagged in review on PR #664).
INFERENCE_LOOKBACK_HOURS = 24

# Longest gap between two consecutive US equity trading sessions is a
# 3-day weekend (holiday Monday or Friday): close ~19:55 UTC Thu/Fri to
# open ~13:30 UTC the following Mon/Tue is ~89-90h. 96h gives a small
# buffer above that without being loose enough to paper over a multi-day
# writer outage. Beyond this, the anchor is treated as unreliable and
# _load_recent_features falls back to wall-clock now() — the pre-fix
# behavior, which correctly zero-outputs and hard-fails on a stalled writer.
MAX_ANCHOR_STALENESS_HOURS = 96


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


def _last_settled_ts(engine, ticker: str, tf: str) -> Optional[pd.Timestamp]:
    """Timestamp of the most recent bar in strat_features_<tf> for ticker.

    Anchors the inference lookback window to the DATA rather than
    wall-clock time, so a weekend/holiday gap between the last settled
    session and "now" (up to ~65h Fri->Mon) doesn't shrink the effective
    window below one full trading session. Returns None only when the
    ticker/tf has no bars at all — the caller's existing empty-frame
    handling (log + 0 predictions) covers that as a genuine data gap.
    """
    from gcp.research.strat_engine.strat_config import strat_features_table
    from sqlalchemy import text

    s_table = strat_features_table(tf)
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT MAX(ts) AS max_ts FROM {s_table} WHERE ticker = :t"),
            {"t": ticker},
        ).fetchone()
    if row is None or row[0] is None:
        return None
    ts = pd.Timestamp(row[0])
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _load_recent_features(ticker: str, tf: str,
                           lookback_hours: int = INFERENCE_LOOKBACK_HOURS
                           ) -> pd.DataFrame:
    """Pull the most-recent feature rows for scoring.

    Routes through strat_dataset.load_strat_features_with_levels — the SAME
    loader training uses — so inference and training can't drift apart. Loading
    strat_features ALONE dropped the ORB / historical-level / order-block
    columns and made every cell fail the alignment check with "feature drift"
    on e.g. orb_5m_high: the month-long magnitude-inference outage (#628/#629).
    The shared loader falls back to plain features if the levels table is
    missing for this TF — same contract as training.

    ALSO recreate prev1/2/3_candle via the SAME helper training uses
    (add_session_aware_lags). Training calls label_next_bar_type which adds
    those columns BEFORE featurize() one-hots them, so feature_cols.txt lists
    ~12 prev*_candle_<value> dummies per cell. Without recreating them here,
    every dummy is missing at featurize time and the zero-fill heuristic in
    _score_and_persist silently erases the sequence feature on every
    prediction — verified 2026-06-20: 98% of live predictions collapsed to
    bucket TIGHT vs ~36% true base rate.

    Warmup-bar drop matches training's drop_warmup=True. Training NEVER saw
    a row where prev3_candle was NaN; scoring those at inference would feed
    all-zero prev*_candle_* dummies which is out-of-distribution.
    """
    from gcp.research.strat_engine.strat_dataset import (
        load_strat_features_with_levels, add_session_aware_lags,
    )

    engine = get_engine()
    now = datetime.now(timezone.utc)
    last_bar_ts = _last_settled_ts(engine, ticker, tf)
    if last_bar_ts is not None and (now - last_bar_ts) <= timedelta(
            hours=MAX_ANCHOR_STALENESS_HOURS):
        anchor = last_bar_ts
    else:
        # No bars at all, or the writer has been stalled longer than any
        # legitimate weekend/holiday gap — anchoring to a stale timestamp
        # here would mask that outage (see MAX_ANCHOR_STALENESS_HOURS).
        # Fall back to wall-clock now(): the pre-fix behavior, which
        # correctly finds zero bars and hard-fails via ZERO-OUTPUT below.
        if last_bar_ts is not None:
            log.warning(
                "%s:%s — last bar at %s is %.1fh stale (> %dh cap); "
                "anchoring to now() instead of the stale bar",
                ticker, tf, last_bar_ts,
                (now - last_bar_ts).total_seconds() / 3600,
                MAX_ANCHOR_STALENESS_HOURS,
            )
        anchor = now
    cutoff = anchor - timedelta(hours=lookback_hours)
    df = load_strat_features_with_levels(
        engine, ticker, tf,
        since_ts=cutoff.isoformat(), include_levels=True, order_by="s.ts ASC",
    )
    if df.empty:
        log.warning("no bars in strat_features_%s for %s since %s", tf, ticker, cutoff)
        return df

    if "strat_candle" in df.columns and "bar_date" in df.columns:
        # The shared loader returns the joined frame in s.ts order; the lag
        # shift is bar_date-grouped so it must be sorted by (bar_date, ts)
        # first. Matches load_labeled_dataset's pre-label sort.
        df = df.sort_values(["bar_date", "ts"]).reset_index(drop=True)
        df = add_session_aware_lags(df, tf)
        n_before = len(df)
        df = df[df["prev3_candle"].notna()].reset_index(drop=True)
        if n_before > len(df):
            log.info("%s:%s — dropped %d session-warmup bars (prev3_candle NaN)",
                     ticker, tf, n_before - len(df))
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
    present = {c.lower(): c for c in features.columns}
    missing = [c for c in _ESSENTIAL_RAW if c not in present]
    if missing:
        # INTERNAL invariant: strat_features_<tf> always has all five OHLCV
        # columns. Even a PARTIAL drift (e.g. a bad SELECT omitting `close`
        # while `open` survives) must fail loud — featurize() drops OHLCV from
        # the model matrix, so a missing essential input would otherwise
        # silently score and persist past this guard.
        raise RuntimeError(
            f"{ticker}:{tf} — feature frame is missing essential OHLCV "
            f"columns {missing}; cannot apply the raw NaN guard (schema drift?)")
    # Check all five by name (not is_numeric_dtype): an all-NULL essential
    # column reads back object-typed, and we still want its NaNs to drop the
    # bar — isna() works regardless of dtype.
    essential_cols = [present[c] for c in _ESSENTIAL_RAW]
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
