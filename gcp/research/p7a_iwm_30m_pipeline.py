#!/usr/bin/env python3
"""Phase 7a — IWM 30m LightGBM production pipeline.

Three modes (one Cloud Run Job, --mode controls behavior):

  --mode=train     Train on full IWM 30m history with purged walk-forward
                   CV to confirm Sharpe; save final model trained on ALL
                   data to GCS. Write fold-level results to GCS for audit.

  --mode=predict   Load saved model from GCS; pull last N IWM 30m bars
                   from strat_features_30m; predict next 5-bar fwd return;
                   write predictions to iwm_30m_predictions table.

  --mode=all       Train + Predict in one execution. Default for nightly
                   rerun. Total wall ~3 min.

Why this design:
  Train and predict together = fresh model every run, no stale-model risk.
  Cloud Scheduler fires daily after market close; new strat_features_30m
  rows from the build job land first; this picks them up and refreshes
  the model + writes new predictions.

  IWM 30m LGBM was the top-Sharpe (+3.24, win 59%) of 9 per-ticker cells
  tested in P7_PER_TICKER_COMPARISON.md.

Rule 0 capacity:
  Volume:   ~17k IWM 30m bars × ~60 cols
  Velocity: 1 batched SELECT + 1 model fit + 1 batched UPSERT
  Wall:     ~2 min (load) + ~30s (train) + ~10s (predict + write)
  Timeout:  600s (10 min) = 5x estimate
  Memory:   2 GiB
  CPU:      4 (LGBM uses n_jobs=-1)
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import time
import pickle
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine, bulk_copy_upsert
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

# ML deps from research image
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy import stats as sps


# ─────────────────────── Constants ───────────────────────

TICKER = "IWM"
TF = "30m"
FWD_COL = "fwd_ret_5bars_bps"
MODEL_BUCKET = os.environ.get(
    "GCS_BUCKET", "adept-mountain-474619-d4-trading-data"
)
MODEL_PREFIX = f"research/p7a/{TICKER.lower()}_{TF}"
MODEL_BLOB = f"{MODEL_PREFIX}/model.pkl"
SCALER_BLOB = f"{MODEL_PREFIX}/scaler.pkl"
FEATURES_BLOB = f"{MODEL_PREFIX}/features.txt"

PREDICTIONS_TABLE = f"{TICKER.lower()}_{TF}_predictions"
PREDICTIONS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PREDICTIONS_TABLE} (
    ticker         VARCHAR(16) NOT NULL,
    bar_ts         TIMESTAMPTZ NOT NULL,
    bar_date       DATE        NOT NULL,
    bar_close      DOUBLE PRECISION,
    pred_fwd_bps   DOUBLE PRECISION,
    pred_direction VARCHAR(4),     -- 'UP' | 'DOWN'
    pred_decile    SMALLINT,       -- 1..10 within the prediction batch
    model_version  VARCHAR(64),
    computed_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, bar_ts)
);
CREATE INDEX IF NOT EXISTS ix_{PREDICTIONS_TABLE}_date
    ON {PREDICTIONS_TABLE} (bar_date);
"""

# Numeric features used for prediction (matches p7_analyze_tf.py)
NUMERIC_FEATURES = [
    "rsi_9", "rsi_14", "stoch_rsi_k", "stoch_rsi_d",
    "ema_9", "ema_20", "ema_50", "ema_200", "sma_50", "sma_200",
    "macd", "macd_signal", "macd_histogram",
    "atr_14", "atr_20", "bb_upper", "bb_lower", "bb_width", "bb_pct",
    "obv", "rvol", "rvol_10",
    "vwap", "price_vs_vwap", "price_vs_ema9", "price_vs_ema20",
    "consecutive_up", "consecutive_down",
    "intraday_return", "high_low_spread_pct",
    "vix_close", "total_gex", "total_vex",
    "flip_price", "distance_to_king_pct", "distance_to_gate_pct",
]
CATEGORICAL_FEATURES = [
    "strat_candle", "prev_strat_candle", "strat_combo",
    "vix_tercile", "gex_tercile", "vex_tercile", "dealer_regime", "gamma_regime",
]


# ─────────────────────── GCS helpers ───────────────────────

def _gcs_client():
    return gcs.Client()


def _upload_bytes(content: bytes, blob_path: str, ctype: str = "application/octet-stream"):
    client = _gcs_client()
    bucket = client.bucket(MODEL_BUCKET)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(content, content_type=ctype)
    return f"gs://{MODEL_BUCKET}/{blob_path}"


def _download_bytes(blob_path: str) -> bytes | None:
    client = _gcs_client()
    bucket = client.bucket(MODEL_BUCKET)
    blob = bucket.blob(blob_path)
    if not blob.exists():
        return None
    return blob.download_as_bytes()


# ─────────────────────── Data + featurization ───────────────────────

def load_iwm_30m(engine, since_date: str | None = None, limit: int | None = None) -> pd.DataFrame:
    where = "WHERE ticker = :ticker AND strat_candle IS NOT NULL"
    params: dict[str, Any] = {"ticker": TICKER}
    if since_date:
        where += " AND bar_date >= :since"
        params["since"] = since_date
    sql = text(f"SELECT * FROM strat_features_{TF} {where} ORDER BY ts" + (f" LIMIT {int(limit)}" if limit else ""))
    log.info("loading strat_features_%s (ticker=%s, since=%s, limit=%s)...",
             TF, TICKER, since_date, limit)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)
    log.info("loaded %d rows × %d cols", len(df), df.shape[1])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """One-hot encode categoricals + select numeric features.
    Returns (X dataframe, feature_column_list)."""
    enc = pd.get_dummies(df, columns=CATEGORICAL_FEATURES,
                         dummy_na=False, dtype=np.int8)
    drop = {"ticker", "ts", "tf", "bar_date",
            "open", "high", "low", "close", "volume",
            "fwd_close_5bars", "fwd_close_15bars", "fwd_close_30bars", "fwd_close_60bars",
            "fwd_ret_5bars_bps", "fwd_ret_15bars_bps", "fwd_ret_30bars_bps", "fwd_ret_60bars_bps",
            "computed_at", "trigger_high", "trigger_low",
            "is_continuation", "is_reversal", "is_inside", "strat_setup"}
    feat_cols = [c for c in enc.columns
                 if c not in drop and enc[c].dtype in
                 (np.float64, np.int64, np.int32, np.int8, np.float32)]
    return enc[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32), feat_cols


def make_lgbm() -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
        n_estimators=300, learning_rate=0.05, max_depth=6,
        num_leaves=31, min_child_samples=100,
        random_state=42, verbose=-1, n_jobs=-1,
    )


# ─────────────────────── Walk-forward eval ───────────────────────

def _ic(y, p):
    if len(y) < 5: return float("nan")
    return float(np.corrcoef(y, p)[0, 1])


def purged_wf(dates: list, n_folds: int = 5, embargo_bars: int = 60):
    n = len(dates)
    if n < n_folds * 2: return
    chunk = n // (n_folds + 1)
    for fold in range(n_folds):
        te = (fold + 1) * chunk
        ts_ = min(n - 1, te + embargo_bars)
        ee = min(n - 1, ts_ + chunk)
        if ts_ >= ee: continue
        yield dates[:te], dates[ts_:ee]


def walk_forward_train_eval(df: pd.DataFrame) -> tuple[lgb.LGBMRegressor, pd.DataFrame, list[str]]:
    """Run 5-fold purged walk-forward CV to confirm Sharpe; then train a
    final model on ALL data. Returns (final_model, fold_results, feature_cols).
    """
    sub = df.dropna(subset=[FWD_COL]).copy().sort_values("ts").reset_index(drop=True)
    X_full, feat_cols = build_feature_matrix(sub)
    y_full = sub[FWD_COL].fillna(0).values
    dates = sorted(sub["ts"].dt.date.unique())

    results = []
    for fi, (train_dates, test_dates) in enumerate(purged_wf(dates, n_folds=5, embargo_bars=60), start=1):
        train_mask = sub["ts"].dt.date.isin(train_dates)
        test_mask = sub["ts"].dt.date.isin(test_dates)
        if train_mask.sum() < 500 or test_mask.sum() < 200:
            continue
        Xt = X_full[train_mask].values
        Xv = X_full[test_mask].values
        yt = y_full[train_mask]
        yv = y_full[test_mask]
        model = make_lgbm()
        model.fit(Xt, yt)
        pred = model.predict(Xv)
        ic = _ic(yv, pred)
        results.append({
            "fold": fi,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "ic": round(ic, 4),
            "test_start": str(test_dates[0]),
            "test_end": str(test_dates[-1]),
        })
        log.info("  fold %d: IC=%+.4f train=%d test=%d (%s..%s)",
                 fi, ic, train_mask.sum(), test_mask.sum(),
                 test_dates[0], test_dates[-1])

    # Final model on ALL data
    log.info("training FINAL model on all %d rows...", len(sub))
    final_model = make_lgbm()
    final_model.fit(X_full.values, y_full)
    return final_model, pd.DataFrame(results), feat_cols


# ─────────────────────── Train mode ───────────────────────

def run_train(engine) -> tuple[lgb.LGBMRegressor, list[str], pd.DataFrame]:
    df = load_iwm_30m(engine)
    log.info("walk-forward eval + final train...")
    model, fold_results, feat_cols = walk_forward_train_eval(df)

    log.info("CV IC summary: mean=%+.4f  std=%.4f  folds=%d",
             fold_results["ic"].mean(), fold_results["ic"].std(), len(fold_results))

    # Persist model + features list
    model_bytes = pickle.dumps(model)
    _upload_bytes(model_bytes, MODEL_BLOB)
    _upload_bytes(("\n".join(feat_cols)).encode(), FEATURES_BLOB, "text/plain")
    log.info("saved model to gs://%s/%s (%d bytes)", MODEL_BUCKET, MODEL_BLOB, len(model_bytes))
    log.info("saved features (%d cols) to gs://%s/%s", len(feat_cols), MODEL_BUCKET, FEATURES_BLOB)

    # Save fold results to GCS as audit trail
    _upload_bytes(fold_results.to_csv(index=False).encode(),
                  f"{MODEL_PREFIX}/cv_fold_results_{int(time.time())}.csv",
                  "text/csv")

    return model, feat_cols, fold_results


# ─────────────────────── Predict mode ───────────────────────

def run_predict(engine, n_bars: int = 100) -> pd.DataFrame:
    # Load model + features
    model_bytes = _download_bytes(MODEL_BLOB)
    feat_text = _download_bytes(FEATURES_BLOB)
    if model_bytes is None or feat_text is None:
        raise RuntimeError(f"Model not found in GCS: {MODEL_BLOB}; run --mode=train first.")
    model = pickle.loads(model_bytes)
    saved_features = feat_text.decode().strip().split("\n")
    log.info("loaded model + %d feature columns from GCS", len(saved_features))

    # Pull last N bars from strat_features_30m
    # Use SQL ORDER BY ts DESC LIMIT N (then re-sort)
    sql = text(f"""
        SELECT * FROM strat_features_{TF}
        WHERE ticker = :ticker AND strat_candle IS NOT NULL
        ORDER BY ts DESC
        LIMIT :n
    """)
    log.info("pulling last %d IWM 30m bars...", n_bars)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"ticker": TICKER, "n": n_bars})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    log.info("loaded %d bars (%s..%s)", len(df), df["ts"].min(), df["ts"].max())

    # Featurize — align to saved feature columns
    X_pred, feat_cols_pred = build_feature_matrix(df)
    # Add missing columns (one-hot categories not present in this batch) with 0
    for c in saved_features:
        if c not in X_pred.columns:
            X_pred[c] = 0
    # Drop extra columns not in saved features
    X_pred = X_pred[saved_features].astype(np.float32)

    preds = model.predict(X_pred.values)
    # Compute deciles
    rng = pd.Series(preds).rank(pct=True)
    deciles = (np.ceil(rng * 10).astype(int)).clip(1, 10).values
    directions = np.where(preds > 0, "UP", "DOWN")

    out = pd.DataFrame({
        "ticker": TICKER,
        "bar_ts": df["ts"],
        "bar_date": df["bar_date"],
        "bar_close": df["close"].astype(float),
        "pred_fwd_bps": np.round(preds, 4),
        "pred_direction": directions,
        "pred_decile": deciles,
        "model_version": f"iwm_30m_lgbm_v1_{time.strftime('%Y%m%d')}",
    })
    return out


def write_predictions(predictions: pd.DataFrame, engine):
    # Ensure table exists
    from gcp.database import execute_sql
    execute_sql(PREDICTIONS_TABLE_SQL)
    log.info("ensured %s table exists", PREDICTIONS_TABLE)

    bulk_copy_upsert(
        predictions, PREDICTIONS_TABLE,
        conflict_cols=["ticker", "bar_ts"],
        update_cols=["bar_date", "bar_close", "pred_fwd_bps", "pred_direction",
                     "pred_decile", "model_version", "computed_at"],
    )
    log.info("wrote %d prediction rows to %s", len(predictions), PREDICTIONS_TABLE)


# ─────────────────────── Main ───────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["train", "predict", "all"], default="all")
    p.add_argument("--ticker", default="IWM", choices=["SPY", "IWM", "QQQ"])
    p.add_argument("--tf", default="30m", choices=["15m", "30m", "60m"])
    p.add_argument("--n-pred-bars", type=int, default=100,
                   help="How many of the most recent bars to score in predict mode")
    args = p.parse_args()

    # Override globals from CLI so functions pick them up
    global TICKER, TF, FWD_COL, MODEL_PREFIX, MODEL_BLOB, SCALER_BLOB, FEATURES_BLOB, PREDICTIONS_TABLE, PREDICTIONS_TABLE_SQL
    TICKER = args.ticker
    TF = args.tf
    FWD_COL = "fwd_ret_5bars_bps"
    MODEL_PREFIX = f"research/p7a/{TICKER.lower()}_{TF}"
    MODEL_BLOB = f"{MODEL_PREFIX}/model.pkl"
    SCALER_BLOB = f"{MODEL_PREFIX}/scaler.pkl"
    FEATURES_BLOB = f"{MODEL_PREFIX}/features.txt"
    PREDICTIONS_TABLE = f"{TICKER.lower()}_{TF}_predictions"
    PREDICTIONS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PREDICTIONS_TABLE} (
    ticker         VARCHAR(16) NOT NULL,
    bar_ts         TIMESTAMPTZ NOT NULL,
    bar_date       DATE        NOT NULL,
    bar_close      DOUBLE PRECISION,
    pred_fwd_bps   DOUBLE PRECISION,
    pred_direction VARCHAR(4),
    pred_decile    SMALLINT,
    model_version  VARCHAR(64),
    computed_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, bar_ts)
);
CREATE INDEX IF NOT EXISTS ix_{PREDICTIONS_TABLE}_date
    ON {PREDICTIONS_TABLE} (bar_date);
"""
    log.info("P7a pipeline: ticker=%s tf=%s mode=%s", TICKER, TF, args.mode)
    engine = get_engine()

    if args.mode in ("train", "all"):
        log.info("=== TRAIN ===")
        t0 = time.time()
        model, feat_cols, folds = run_train(engine)
        log.info("train done in %.1fs", time.time() - t0)

    if args.mode in ("predict", "all"):
        log.info("=== PREDICT ===")
        t0 = time.time()
        preds = run_predict(engine, n_bars=args.n_pred_bars)
        log.info("predict done in %.1fs; %d rows", time.time() - t0, len(preds))

        log.info("Top 10 predictions by predicted fwd bps:")
        log.info("\n%s", preds.sort_values("pred_fwd_bps", ascending=False).head(10).to_string(index=False))
        log.info("Bottom 10 predictions:")
        log.info("\n%s", preds.sort_values("pred_fwd_bps").head(10).to_string(index=False))

        write_predictions(preds, engine)


if __name__ == "__main__":
    main()
