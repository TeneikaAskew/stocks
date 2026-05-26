#!/usr/bin/env python3
"""Phase 7c — Stacked model: classifier outputs feed the return regression.

Two-layer stack:
  Layer 1 (classifier): next-candle multiclass — predicts p(1), p(2U), p(2D), p(3)
  Layer 2 (regressor):  forward-return — predicts fwd_5bars_bps, with the
                        classifier probabilities as ADDITIONAL features
                        alongside the original p7a feature set.

To avoid leakage during training of layer 2, layer 1 is fit via 5-fold OOF
cross-validation on the training data. The OOF predictions are concatenated
into a column "p_2u / p_2d / p_1 / p_3 / directional_edge" and used as
features for the regressor. At OOS time, a SINGLE layer-1 classifier
(trained on ALL training data) generates the OOS classifier features.

This is the rigorous way to stack: training-time classifier features are
out-of-fold (the classifier never saw the row it's predicting), and OOS
classifier features come from a model that has never seen any OOS data.

Modes:
  --mode=evaluate  Holdout evaluation. Reports OOS IC, L/S decile spread,
                   month-by-month performance; compares to a baseline
                   regression that lacks the classifier features.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

import lightgbm as lgb
from sklearn.model_selection import KFold


TICKER = "IWM"
TF = "5m"
FWD_COL = "fwd_ret_5bars_bps"
MODEL_BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
OUT_PREFIX = f"research/p7c"
CLASS_ORDER = ["1", "2U", "2D", "3"]

CATEGORICAL = ["strat_candle", "prev_strat_candle", "strat_combo",
               "vix_tercile", "gex_tercile", "vex_tercile",
               "dealer_regime", "gamma_regime"]


def _gcs():
    return gcs.Client()


def _upload(content: bytes, blob_path: str, ctype="application/octet-stream"):
    b = _gcs().bucket(MODEL_BUCKET).blob(blob_path)
    b.upload_from_string(content, content_type=ctype)
    return f"gs://{MODEL_BUCKET}/{blob_path}"


def load_bars(engine, since=None, until=None) -> pd.DataFrame:
    where = "WHERE ticker = :t AND strat_candle IS NOT NULL"
    p: dict[str, Any] = {"t": TICKER}
    if since: where += " AND bar_date >= :s"; p["s"] = since
    if until: where += " AND bar_date < :u"; p["u"] = until
    with engine.connect() as c:
        df = pd.read_sql(text(f"SELECT * FROM strat_features_{TF} {where} ORDER BY ts"), c, params=p)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def add_next_candle(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("ts").reset_index(drop=True)
    df["next_strat_candle"] = df["strat_candle"].shift(-1)
    return df


def featurize(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    enc = pd.get_dummies(df, columns=CATEGORICAL, dummy_na=False, dtype=np.int8)
    drop = {"ticker","ts","tf","bar_date","open","high","low","close","volume",
            "fwd_close_5bars","fwd_close_15bars","fwd_close_30bars","fwd_close_60bars",
            "fwd_ret_5bars_bps","fwd_ret_15bars_bps","fwd_ret_30bars_bps","fwd_ret_60bars_bps",
            "computed_at","trigger_high","trigger_low",
            "is_continuation","is_reversal","is_inside","strat_setup","next_strat_candle"}
    cols = [c for c in enc.columns
            if c not in drop and enc[c].dtype in (np.float64, np.int64, np.int32, np.int8, np.float32)]
    return enc[cols].replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32), cols


def make_classifier():
    return lgb.LGBMClassifier(objective="multiclass", num_class=4,
                              n_estimators=300, learning_rate=0.05, max_depth=6,
                              num_leaves=31, min_child_samples=100,
                              random_state=42, verbose=-1, n_jobs=-1)


def make_regressor():
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
                             num_leaves=31, min_child_samples=100,
                             random_state=42, verbose=-1, n_jobs=-1)


def evaluate(engine, train_until: str = "2026-01-01"):
    log.info("stacked-model evaluation: ticker=%s tf=%s split=%s", TICKER, TF, train_until)

    # Load + label
    train_df = add_next_candle(load_bars(engine, until=train_until))
    test_df  = add_next_candle(load_bars(engine, since=train_until))

    # Filter rows useful for BOTH classifier and regressor
    train_df = train_df.dropna(subset=["next_strat_candle", FWD_COL]).copy()
    train_df = train_df[train_df["next_strat_candle"].isin(CLASS_ORDER)]
    test_df  = test_df.dropna(subset=["next_strat_candle", FWD_COL]).copy()
    test_df  = test_df[test_df["next_strat_candle"].isin(CLASS_ORDER)]
    log.info("train rows: %d   test rows: %d", len(train_df), len(test_df))

    # Featurize, align columns between train/test
    X_train, train_cols = featurize(train_df)
    X_test, test_cols   = featurize(test_df)
    all_cols = sorted(set(train_cols) | set(test_cols))
    for c in all_cols:
        if c not in X_train.columns: X_train[c] = 0
        if c not in X_test.columns: X_test[c] = 0
    X_train = X_train[all_cols].astype(np.float32)
    X_test  = X_test[all_cols].astype(np.float32)

    y_cls_train = train_df["next_strat_candle"].map({c:i for i,c in enumerate(CLASS_ORDER)}).values
    y_reg_train = train_df[FWD_COL].values
    y_reg_test  = test_df[FWD_COL].values

    # ─── Layer 1: OOF classifier on training data ────────────────────────
    log.info("Layer 1: 5-fold OOF classifier on %d train rows...", len(train_df))
    oof_proba = np.zeros((len(train_df), 4), dtype=np.float32)
    kf = KFold(n_splits=5, shuffle=False)  # time order preserved by virtue of input ordering
    for fi, (tr_idx, va_idx) in enumerate(kf.split(X_train), 1):
        clf = make_classifier()
        clf.fit(X_train.iloc[tr_idx].values, y_cls_train[tr_idx])
        oof_proba[va_idx] = clf.predict_proba(X_train.iloc[va_idx].values)
        log.info("  fold %d done (train=%d, val=%d)", fi, len(tr_idx), len(va_idx))

    # Final classifier on ALL train data, for OOS scoring
    log.info("Layer 1 FINAL: train on all %d rows...", len(train_df))
    final_clf = make_classifier()
    final_clf.fit(X_train.values, y_cls_train)
    oos_proba = final_clf.predict_proba(X_test.values)

    # Build classifier features
    cls_cols = ["p_1", "p_2u", "p_2d", "p_3", "directional_edge"]
    train_cls_feats = pd.DataFrame({
        "p_1": oof_proba[:, 0], "p_2u": oof_proba[:, 1],
        "p_2d": oof_proba[:, 2], "p_3": oof_proba[:, 3],
        "directional_edge": oof_proba[:, 1] - oof_proba[:, 2],
    }, index=X_train.index).astype(np.float32)
    test_cls_feats = pd.DataFrame({
        "p_1": oos_proba[:, 0], "p_2u": oos_proba[:, 1],
        "p_2d": oos_proba[:, 2], "p_3": oos_proba[:, 3],
        "directional_edge": oos_proba[:, 1] - oos_proba[:, 2],
    }, index=X_test.index).astype(np.float32)

    # ─── Layer 2: regression — TWO models for comparison ─────────────────
    log.info("Layer 2 BASELINE: regression WITHOUT classifier features...")
    reg_base = make_regressor()
    reg_base.fit(X_train.values, y_reg_train)
    pred_base = reg_base.predict(X_test.values)

    log.info("Layer 2 STACKED: regression WITH classifier features...")
    X_train_stk = pd.concat([X_train.reset_index(drop=True), train_cls_feats.reset_index(drop=True)], axis=1)
    X_test_stk  = pd.concat([X_test.reset_index(drop=True),  test_cls_feats.reset_index(drop=True)], axis=1)
    reg_stk = make_regressor()
    reg_stk.fit(X_train_stk.values, y_reg_train)
    pred_stk = reg_stk.predict(X_test_stk.values)

    # ─── Honest metrics ──────────────────────────────────────────────────
    def metrics(name, pred, y, df_idx):
        ok = ~np.isnan(y)
        y = y[ok]; pred = pred[ok]
        if len(y) < 50: return {}
        ic = float(np.corrcoef(y, pred)[0,1])
        # decile L/S
        d = pd.qcut(pd.Series(pred), 10, labels=False, duplicates="drop") + 1
        d10 = y[d == 10]; d1 = y[d == 1]
        spread = float(d10.mean() - d1.mean())
        # monthly spread
        sub = test_df.iloc[df_idx].copy()
        sub["pred"] = pred
        sub["actual"] = y
        sub["decile"] = d.values
        sub["month"] = pd.to_datetime(sub["ts"]).dt.to_period("M").astype(str)
        per_month = sub.groupby("month").apply(
            lambda g: float(g.loc[g.decile==10, "actual"].mean()
                            - g.loc[g.decile==1, "actual"].mean()),
            include_groups=False
        ).to_dict()
        log.info("  [%s] IC=%+.4f  L/S spread=%+.2f bps  n=%d", name, ic, spread, len(y))
        log.info("  [%s] month-by-month L/S: %s", name,
                 {m: round(v, 1) for m, v in per_month.items()})
        return {"name": name, "ic": ic, "ls_spread_bps": spread, "n": int(len(y)),
                "per_month_ls_bps": per_month}

    test_idx = test_df.index.values
    m_base = metrics("baseline", pred_base, y_reg_test, np.arange(len(y_reg_test)))
    m_stk  = metrics("stacked",  pred_stk,  y_reg_test, np.arange(len(y_reg_test)))

    # ─── Importance comparison ───────────────────────────────────────────
    log.info("─ Top-15 features in STACKED model ─")
    importances = pd.DataFrame({
        "feature": X_train_stk.columns,
        "importance": reg_stk.feature_importances_,
    }).sort_values("importance", ascending=False)
    for _, r in importances.head(15).iterrows():
        mark = " ←CLASSIFIER" if r["feature"] in cls_cols else ""
        log.info("  %4d  %s%s", int(r["importance"]), r["feature"], mark)

    # Save artifacts
    out = {
        "ticker": TICKER, "tf": TF, "train_until": train_until,
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "baseline": m_base, "stacked": m_stk,
        "ic_lift": m_stk["ic"] - m_base["ic"],
        "spread_lift_bps": m_stk["ls_spread_bps"] - m_base["ls_spread_bps"],
        "classifier_feature_importances": {
            c: int(reg_stk.feature_importances_[list(X_train_stk.columns).index(c)])
            for c in cls_cols
        },
    }
    log.info("")
    log.info("=" * 70)
    log.info("SUMMARY  (%s %s, OOS Jan-May 2026)", TICKER, TF)
    log.info("=" * 70)
    log.info("Baseline (no classifier feats):  IC=%+.4f  L/S=%+.2f bps",
             m_base["ic"], m_base["ls_spread_bps"])
    log.info("Stacked  (with classifier feats): IC=%+.4f  L/S=%+.2f bps",
             m_stk["ic"], m_stk["ls_spread_bps"])
    log.info("LIFT: ΔIC=%+.4f  Δspread=%+.2f bps",
             out["ic_lift"], out["spread_lift_bps"])

    blob = f"{OUT_PREFIX}/{TICKER.lower()}_{TF}_stack_{int(time.time())}.json"
    _upload(json.dumps(out, indent=2, default=str).encode(), blob, "application/json")
    log.info("saved to gs://%s/%s", MODEL_BUCKET, blob)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=["SPY","IWM","QQQ"])
    p.add_argument("--tf", default="5m", choices=["1m","5m","15m","30m","60m"])
    p.add_argument("--train-until", default="2026-01-01")
    args = p.parse_args()
    global TICKER, TF
    TICKER, TF = args.ticker, args.tf
    log.info("P7c stacked evaluation: %s %s", TICKER, TF)
    engine = get_engine()
    evaluate(engine, train_until=args.train_until)


if __name__ == "__main__":
    main()
