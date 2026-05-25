#!/usr/bin/env python3
"""Phase 7b — Next-candle multiclass classifier.

Predicts the NEXT bar's strat candle type ∈ {1, 2U, 2D, 3} from the current
bar's indicators + dealer/VIX regime context. Companion to p7a (forward
return regression) — together they answer "what STATE will the next bar be"
and "what RETURN will follow."

Modes:
  --mode=evaluate  Train on data with bar_date < train_until, hold out the
                   rest. Report per-class precision/recall/log-loss and
                   compare to baseline class-prior. THIS IS THE HONEST OOS
                   REPORT — use it before deciding to ship.

  --mode=train     Train on ALL data (or up to --train-until); save to GCS.

  --mode=predict   Load saved model from GCS; score recent bars; write to
                   {ticker}_{tf}_next_candle_predictions.

  --mode=all       train + predict (no held-out eval).

Why multiclass not binary:
  4 next-candle types have meaningfully different forward-return
  distributions and trade implications. A 2U next means current high will
  break (entry trigger). A 2D next means current low will break (entry
  trigger opposite side). A 1 next means inside-bar compression (no
  trigger). A 3 next means outside (both sides triggered — chop). Reducing
  this to binary throws away the most actionable signal.

Rule 0 capacity:
  Volume:   ~17k IWM 60m bars × ~60 cols (same as p7a)
  Velocity: 1 batched SELECT + 1 model fit + 1 batched UPSERT
  Wall:     ~2 min total (slightly faster than p7a — smaller TF or same)
  Timeout:  600s (10 min) = 5x estimate
  Memory:   2 GiB
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
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine, bulk_copy_upsert, execute_sql
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

import lightgbm as lgb
from sklearn.metrics import log_loss, classification_report, confusion_matrix


# Mutable globals overridden by CLI in main()
TICKER = "IWM"
TF = "60m"
MODEL_BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
MODEL_PREFIX = f"research/p7b/{TICKER.lower()}_{TF}"
MODEL_BLOB = f"{MODEL_PREFIX}/model.pkl"
FEATURES_BLOB = f"{MODEL_PREFIX}/features.txt"
CLASSES_BLOB = f"{MODEL_PREFIX}/classes.txt"
PREDICTIONS_TABLE = f"{TICKER.lower()}_{TF}_next_candle_predictions"

CLASS_ORDER = ["1", "2U", "2D", "3"]

# Same feature set as p7a so the two models can be stacked later.
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


def _predictions_table_sql() -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {PREDICTIONS_TABLE} (
    ticker            VARCHAR(16) NOT NULL,
    bar_ts            TIMESTAMPTZ NOT NULL,
    bar_date          DATE        NOT NULL,
    bar_close         DOUBLE PRECISION,
    curr_candle       VARCHAR(4),
    pred_class        VARCHAR(4),
    pred_class_conf   DOUBLE PRECISION,
    p_inside          DOUBLE PRECISION,
    p_2u              DOUBLE PRECISION,
    p_2d              DOUBLE PRECISION,
    p_outside         DOUBLE PRECISION,
    directional_edge  DOUBLE PRECISION,  -- p_2u - p_2d (positive=up bias)
    model_version     VARCHAR(64),
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, bar_ts)
);
CREATE INDEX IF NOT EXISTS ix_{PREDICTIONS_TABLE}_date
    ON {PREDICTIONS_TABLE} (bar_date);
"""


# ─────────────────────── GCS helpers ───────────────────────

def _gcs_client():
    return gcs.Client()


def _upload_bytes(content: bytes, blob_path: str, ctype: str = "application/octet-stream"):
    bucket = _gcs_client().bucket(MODEL_BUCKET)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(content, content_type=ctype)
    return f"gs://{MODEL_BUCKET}/{blob_path}"


def _download_bytes(blob_path: str) -> bytes | None:
    bucket = _gcs_client().bucket(MODEL_BUCKET)
    blob = bucket.blob(blob_path)
    if not blob.exists():
        return None
    return blob.download_as_bytes()


# ─────────────────────── Data + featurization ───────────────────────

def load_bars(engine, since_date: str | None = None, until_date: str | None = None) -> pd.DataFrame:
    where = "WHERE ticker = :ticker AND strat_candle IS NOT NULL"
    params: dict[str, Any] = {"ticker": TICKER}
    if since_date:
        where += " AND bar_date >= :since"
        params["since"] = since_date
    if until_date:
        where += " AND bar_date < :until"
        params["until"] = until_date
    sql = text(f"SELECT * FROM strat_features_{TF} {where} ORDER BY ts")
    log.info("loading strat_features_%s (ticker=%s, since=%s, until=%s)...",
             TF, TICKER, since_date, until_date)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    log.info("loaded %d rows × %d cols", len(df), df.shape[1])
    return df


def add_target(df: pd.DataFrame) -> pd.DataFrame:
    """Target = NEXT bar's strat_candle. Drop the last bar (no target)."""
    df = df.sort_values("ts").reset_index(drop=True)
    df["next_strat_candle"] = df["strat_candle"].shift(-1)
    return df


def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """One-hot encode categoricals + select numeric features.
    SAME drop-set as p7a so the two models are feature-compatible."""
    enc = pd.get_dummies(df, columns=CATEGORICAL_FEATURES,
                         dummy_na=False, dtype=np.int8)
    drop = {"ticker", "ts", "tf", "bar_date",
            "open", "high", "low", "close", "volume",
            "fwd_close_5bars", "fwd_close_15bars", "fwd_close_30bars", "fwd_close_60bars",
            "fwd_ret_5bars_bps", "fwd_ret_15bars_bps", "fwd_ret_30bars_bps", "fwd_ret_60bars_bps",
            "computed_at", "trigger_high", "trigger_low",
            "is_continuation", "is_reversal", "is_inside", "strat_setup",
            "next_strat_candle"}
    feat_cols = [c for c in enc.columns
                 if c not in drop and enc[c].dtype in
                 (np.float64, np.int64, np.int32, np.int8, np.float32)]
    return enc[feat_cols].replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32), feat_cols


def make_classifier() -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(
        objective="multiclass",
        num_class=len(CLASS_ORDER),
        n_estimators=300, learning_rate=0.05, max_depth=6,
        num_leaves=31, min_child_samples=100,
        class_weight=None,    # we report per-class metrics; let frequencies speak
        random_state=42, verbose=-1, n_jobs=-1,
    )


# ─────────────────────── Evaluate mode (honest OOS) ───────────────────────

def run_evaluate(engine, train_until: str, predict_since: str | None = None) -> dict:
    """Train on bar_date < train_until, evaluate on bar_date >= train_until."""
    log.info("EVALUATE: train < %s, test >= %s", train_until, train_until)
    train_df = add_target(load_bars(engine, until_date=train_until))
    test_df = add_target(load_bars(engine, since_date=train_until))

    # Both must have non-null targets
    train_df = train_df.dropna(subset=["next_strat_candle"]).copy()
    test_df = test_df.dropna(subset=["next_strat_candle"]).copy()
    # Filter to known classes only
    train_df = train_df[train_df["next_strat_candle"].isin(CLASS_ORDER)]
    test_df = test_df[test_df["next_strat_candle"].isin(CLASS_ORDER)]
    log.info("train rows: %d   test rows: %d", len(train_df), len(test_df))

    # Build feature matrices INDEPENDENTLY then align columns (one-hot
    # classes may differ between splits).
    X_train, train_cols = build_feature_matrix(train_df)
    X_test, test_cols = build_feature_matrix(test_df)
    all_cols = sorted(set(train_cols) | set(test_cols))
    for c in all_cols:
        if c not in X_train.columns: X_train[c] = 0
        if c not in X_test.columns: X_test[c] = 0
    X_train = X_train[all_cols].astype(np.float32)
    X_test = X_test[all_cols].astype(np.float32)

    # Map labels to int indices
    y_train_idx = train_df["next_strat_candle"].map({c: i for i, c in enumerate(CLASS_ORDER)}).values
    y_test_idx = test_df["next_strat_candle"].map({c: i for i, c in enumerate(CLASS_ORDER)}).values

    log.info("training multiclass LightGBM on %d cols × %d rows...", len(all_cols), len(X_train))
    t0 = time.time()
    model = make_classifier()
    model.fit(X_train.values, y_train_idx)
    log.info("fit done in %.1fs", time.time() - t0)

    # OOS predictions
    proba = model.predict_proba(X_test.values)
    preds = model.predict(X_test.values)

    # Baseline = class prior from training data
    prior = np.bincount(y_train_idx, minlength=len(CLASS_ORDER)) / len(y_train_idx)
    baseline_proba = np.tile(prior, (len(y_test_idx), 1))
    baseline_loss = log_loss(y_test_idx, baseline_proba, labels=list(range(len(CLASS_ORDER))))
    model_loss = log_loss(y_test_idx, proba, labels=list(range(len(CLASS_ORDER))))

    accuracy = float((preds == y_test_idx).mean())
    baseline_acc = float(prior.max())  # always predict majority class

    # Per-class report
    report = classification_report(
        y_test_idx, preds,
        labels=list(range(len(CLASS_ORDER))),
        target_names=CLASS_ORDER,
        output_dict=True, zero_division=0,
    )
    cm = confusion_matrix(y_test_idx, preds, labels=list(range(len(CLASS_ORDER))))

    log.info("─" * 70)
    log.info("OOS RESULTS  (%s %s, test >= %s, n=%d)", TICKER, TF, train_until, len(y_test_idx))
    log.info("─" * 70)
    log.info("log-loss:  model=%.4f  baseline(prior)=%.4f  improvement=%.4f",
             model_loss, baseline_loss, baseline_loss - model_loss)
    log.info("accuracy:  model=%.3f  baseline(maj-class)=%.3f", accuracy, baseline_acc)
    log.info("")
    log.info("PER-CLASS:")
    log.info("  class  prec   rec   f1     support  (test prior=%s)",
             {c: f"{(y_test_idx == i).mean():.2%}" for i, c in enumerate(CLASS_ORDER)})
    for c in CLASS_ORDER:
        r = report[c]
        log.info("    %3s   %.3f  %.3f  %.3f  %5d",
                 c, r["precision"], r["recall"], r["f1-score"], int(r["support"]))
    log.info("")
    log.info("CONFUSION MATRIX  (rows = actual, cols = predicted; order=%s)", CLASS_ORDER)
    log.info("        %s", "  ".join(f"{c:>5}" for c in CLASS_ORDER))
    for i, c in enumerate(CLASS_ORDER):
        log.info("  %3s   %s", c, "  ".join(f"{cm[i,j]:>5d}" for j in range(len(CLASS_ORDER))))

    # Decision-time check: when the model gives high confidence,
    # how often is it right?
    max_proba = proba.max(axis=1)
    for thresh in [0.40, 0.50, 0.60, 0.70]:
        mask = max_proba >= thresh
        if mask.sum() < 10: continue
        acc_at = float((preds[mask] == y_test_idx[mask]).mean())
        log.info("  P(top class) >= %.2f: n=%d (%.1f%% of OOS)  accuracy=%.3f",
                 thresh, mask.sum(), 100 * mask.mean(), acc_at)

    # Directional edge: P(next=2U) − P(next=2D) as an up/down lean signal
    p_2u = proba[:, CLASS_ORDER.index("2U")]
    p_2d = proba[:, CLASS_ORDER.index("2D")]
    directional = p_2u - p_2d
    # Sort into deciles by directional edge, check actual 2U/2D outcome rates
    df_check = pd.DataFrame({
        "edge": directional,
        "actual_2u": (y_test_idx == CLASS_ORDER.index("2U")).astype(int),
        "actual_2d": (y_test_idx == CLASS_ORDER.index("2D")).astype(int),
    })
    df_check["decile"] = pd.qcut(df_check["edge"], 10, labels=False, duplicates="drop") + 1
    decile_stats = df_check.groupby("decile").agg(
        n=("edge", "size"),
        edge=("edge", "mean"),
        actual_2u_rate=("actual_2u", "mean"),
        actual_2d_rate=("actual_2d", "mean"),
    )
    decile_stats["net_up"] = decile_stats["actual_2u_rate"] - decile_stats["actual_2d_rate"]
    log.info("")
    log.info("DIRECTIONAL EDGE (p_2u - p_2d) decile sort, OOS:")
    log.info("%s", decile_stats.round(4).to_string())

    # Persist artifacts
    metrics = {
        "ticker": TICKER, "tf": TF, "train_until": train_until,
        "n_train": int(len(X_train)), "n_test": int(len(X_test)),
        "model_log_loss": float(model_loss),
        "baseline_log_loss": float(baseline_loss),
        "improvement": float(baseline_loss - model_loss),
        "accuracy": accuracy,
        "baseline_accuracy": baseline_acc,
        "per_class": {c: report[c] for c in CLASS_ORDER},
        "confusion": {CLASS_ORDER[i]: {CLASS_ORDER[j]: int(cm[i,j]) for j in range(4)} for i in range(4)},
        "decile_stats": decile_stats.reset_index().to_dict(orient="records"),
    }
    eval_blob = f"{MODEL_PREFIX}/eval_{int(time.time())}.json"
    _upload_bytes(json.dumps(metrics, indent=2).encode(), eval_blob, "application/json")
    log.info("saved eval metrics to gs://%s/%s", MODEL_BUCKET, eval_blob)
    return metrics


# ─────────────────────── Train mode ───────────────────────

def run_train(engine, train_until: str | None = None) -> tuple[lgb.LGBMClassifier, list[str]]:
    df = add_target(load_bars(engine, until_date=train_until))
    df = df.dropna(subset=["next_strat_candle"])
    df = df[df["next_strat_candle"].isin(CLASS_ORDER)].copy()
    X, feat_cols = build_feature_matrix(df)
    y_idx = df["next_strat_candle"].map({c: i for i, c in enumerate(CLASS_ORDER)}).values
    log.info("training FINAL multiclass model on %d rows × %d cols...", len(X), len(feat_cols))
    t0 = time.time()
    model = make_classifier()
    model.fit(X.values, y_idx)
    log.info("fit done in %.1fs", time.time() - t0)

    _upload_bytes(pickle.dumps(model), MODEL_BLOB)
    _upload_bytes("\n".join(feat_cols).encode(), FEATURES_BLOB, "text/plain")
    _upload_bytes("\n".join(CLASS_ORDER).encode(), CLASSES_BLOB, "text/plain")
    log.info("saved model to gs://%s/%s", MODEL_BUCKET, MODEL_BLOB)
    return model, feat_cols


# ─────────────────────── Predict mode ───────────────────────

def run_predict(engine, n_bars: int = 100, predict_since: str | None = None) -> pd.DataFrame:
    model_bytes = _download_bytes(MODEL_BLOB)
    feat_text = _download_bytes(FEATURES_BLOB)
    if model_bytes is None or feat_text is None:
        raise RuntimeError(f"Model not in GCS: {MODEL_BLOB}; run --mode=train first.")
    model = pickle.loads(model_bytes)
    saved_features = feat_text.decode().strip().split("\n")
    log.info("loaded model + %d feature cols from GCS", len(saved_features))

    if predict_since:
        df = load_bars(engine, since_date=predict_since)
    else:
        sql = text(f"SELECT * FROM strat_features_{TF} "
                   f"WHERE ticker = :ticker AND strat_candle IS NOT NULL "
                   f"ORDER BY ts DESC LIMIT :n")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={"ticker": TICKER, "n": n_bars})
        df = df.sort_values("ts").reset_index(drop=True)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)

    X, _ = build_feature_matrix(df)
    for c in saved_features:
        if c not in X.columns: X[c] = 0
    X = X[saved_features].astype(np.float32)

    proba = model.predict_proba(X.values)
    pred_idx = proba.argmax(axis=1)
    pred_class = [CLASS_ORDER[i] for i in pred_idx]
    pred_conf = proba.max(axis=1)
    p_inside = proba[:, CLASS_ORDER.index("1")]
    p_2u = proba[:, CLASS_ORDER.index("2U")]
    p_2d = proba[:, CLASS_ORDER.index("2D")]
    p_outside = proba[:, CLASS_ORDER.index("3")]

    out = pd.DataFrame({
        "ticker": TICKER,
        "bar_ts": df["ts"],
        "bar_date": df["bar_date"],
        "bar_close": df["close"].astype(float),
        "curr_candle": df["strat_candle"],
        "pred_class": pred_class,
        "pred_class_conf": np.round(pred_conf, 4),
        "p_inside": np.round(p_inside, 4),
        "p_2u": np.round(p_2u, 4),
        "p_2d": np.round(p_2d, 4),
        "p_outside": np.round(p_outside, 4),
        "directional_edge": np.round(p_2u - p_2d, 4),
        "model_version": f"{TICKER.lower()}_{TF}_nextcandle_lgbm_v1_{time.strftime('%Y%m%d')}",
    })
    return out


def write_predictions(predictions: pd.DataFrame):
    execute_sql(_predictions_table_sql())
    log.info("ensured %s table exists", PREDICTIONS_TABLE)
    bulk_copy_upsert(
        predictions, PREDICTIONS_TABLE,
        conflict_cols=["ticker", "bar_ts"],
        update_cols=["bar_date", "bar_close", "curr_candle",
                     "pred_class", "pred_class_conf",
                     "p_inside", "p_2u", "p_2d", "p_outside",
                     "directional_edge", "model_version", "computed_at"],
    )
    log.info("wrote %d prediction rows to %s", len(predictions), PREDICTIONS_TABLE)


# ─────────────────────── Main ───────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["evaluate", "train", "predict", "all"], default="evaluate")
    p.add_argument("--ticker", default="IWM", choices=["SPY", "IWM", "QQQ"])
    p.add_argument("--tf", default="60m", choices=["1m", "5m", "15m", "30m", "60m"])
    p.add_argument("--train-until", default="2026-01-01",
                   help="In evaluate mode: split at this date. In train mode: cap training data.")
    p.add_argument("--predict-since", default=None,
                   help="In predict mode: score ALL bars from this date.")
    p.add_argument("--n-pred-bars", type=int, default=100)
    args = p.parse_args()

    global TICKER, TF, MODEL_PREFIX, MODEL_BLOB, FEATURES_BLOB, CLASSES_BLOB, PREDICTIONS_TABLE
    TICKER = args.ticker
    TF = args.tf
    MODEL_PREFIX = f"research/p7b/{TICKER.lower()}_{TF}"
    MODEL_BLOB = f"{MODEL_PREFIX}/model.pkl"
    FEATURES_BLOB = f"{MODEL_PREFIX}/features.txt"
    CLASSES_BLOB = f"{MODEL_PREFIX}/classes.txt"
    PREDICTIONS_TABLE = f"{TICKER.lower()}_{TF}_next_candle_predictions"

    log.info("P7b classifier: ticker=%s tf=%s mode=%s", TICKER, TF, args.mode)
    engine = get_engine()

    if args.mode == "evaluate":
        run_evaluate(engine, train_until=args.train_until)
        return

    if args.mode in ("train", "all"):
        run_train(engine, train_until=args.train_until)

    if args.mode in ("predict", "all"):
        preds = run_predict(engine, n_bars=args.n_pred_bars, predict_since=args.predict_since)
        log.info("Top 10 by p_2u (most up-bias):")
        log.info("\n%s", preds.nlargest(10, "p_2u").to_string(index=False))
        log.info("Top 10 by p_2d (most down-bias):")
        log.info("\n%s", preds.nlargest(10, "p_2d").to_string(index=False))
        write_predictions(preds)


if __name__ == "__main__":
    main()
