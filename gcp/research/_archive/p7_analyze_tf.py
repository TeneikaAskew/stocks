#!/usr/bin/env python3
"""Phase 7 — Per-TF predictability + modeling analysis (Cloud Run Job).

Designed to be dispatched ONCE PER TIMEFRAME so 5 instances run in parallel
(--tf=1m, 5m, 15m, 30m, 60m). With 8 CPUs each, that's 40 CPUs of effective
parallelism. Each instance:

  1. Pulls strat_features_<tf> from Cloud SQL for SPY+IWM+QQQ
  2. Per-(prev_strat, curr_strat) transition grid: counts, fwd-return stats
  3. Per-(strat_combo, dealer_regime) 9-cell grid: bootstrap CI on hit_rate
  4. Per-(strat_combo, vix_tercile / gex_tercile / vex_tercile) marginal grids
  5. Indicator × strat-combo Pearson + Spearman correlations
  6. Cross-sectional Ridge / Lasso / LightGBM models with purged walk-forward
     CV using ALL features (indicators + dealer_regime one-hot + strat dummies)
  7. SHAP feature importance for the LightGBM model
  8. Writes everything to gs://{bucket}/research/p7-analysis/{tf}/

Uses the research image (lightgbm + sklearn + scipy + shap baked in).

Rule 0 sizing per TF:
  Volume:   1m=3M rows; 5m=600k; 15m=200k; 30m=100k; 60m=50k (3 ETFs total)
  Velocity: 1 batched SELECT per TF (under db-query 50k cap thanks to per-TF dispatch)
  Wall:     1m ~10min model training; smaller TFs ~3min each
  Timeout:  3600s (60min) = generous safety
  Memory:   1m worst case ~3GB; deploy 32GiB
  CPU:      8 (LightGBM + scipy use all cores via n_jobs=-1)
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import get_engine
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

# ML deps come from the research image (gcp/Dockerfile.research)
import lightgbm as lgb
from sklearn.linear_model import Ridge, Lasso, ElasticNet, BayesianRidge
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy import stats as sps


# ────────────────────── GCS upload helper ──────────────────────

def _upload(content: str | bytes, bucket: str, blob_path: str, ctype: str = "text/csv"):
    client = gcs.Client()
    b = client.bucket(bucket)
    blob = b.blob(blob_path)
    if isinstance(content, str):
        blob.upload_from_string(content, content_type=ctype)
    else:
        blob.upload_from_string(content, content_type=ctype)
    return f"gs://{bucket}/{blob_path}"


# ────────────────────── Data load ──────────────────────

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


def load_data(engine, tf: str, ticker: str | None = None) -> pd.DataFrame:
    table = f"strat_features_{tf}"
    if ticker:
        sql = text(f"SELECT * FROM {table} WHERE strat_candle IS NOT NULL AND ticker = :ticker")
        params = {"ticker": ticker}
    else:
        sql = text(f"SELECT * FROM {table} WHERE strat_candle IS NOT NULL")
        params = {}
    log.info("loading %s (ticker=%s)...", table, ticker or "ALL")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)
    log.info("loaded %d rows × %d cols from %s", len(df), df.shape[1], table)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


# ────────────────────── Analysis 1: strat transition grid ──────────────────────

def strat_transition_grid(df: pd.DataFrame, fwd_col: str = "fwd_ret_5bars_bps") -> pd.DataFrame:
    """(prev_strat → curr_strat) transition counts + fwd-return stats.

    The most basic 'is strat predictive' check. For each (prev, curr) cell,
    count occurrences and compute mean fwd return + hit rate.
    """
    sub = df.dropna(subset=["prev_strat_candle", "strat_candle", fwd_col]).copy()
    grp = sub.groupby(["ticker", "prev_strat_candle", "strat_candle"]).agg(
        n=(fwd_col, "count"),
        mean_bps=(fwd_col, "mean"),
        std_bps=(fwd_col, "std"),
        hit_pct=(fwd_col, lambda x: 100.0 * (x > 0).mean()),
    ).reset_index()
    return grp


# ────────────────────── Analysis 2: combo × dealer_regime ──────────────────────

def combo_dealer_grid(df: pd.DataFrame, fwd_col: str = "fwd_ret_5bars_bps") -> pd.DataFrame:
    """For each (ticker, strat_combo, dealer_regime), count + hit rate + bootstrap CI."""
    rng = np.random.default_rng(42)
    rows = []
    sub = df.dropna(subset=["strat_combo", "dealer_regime", fwd_col]).copy()
    for (ticker, combo, regime), g in sub.groupby(["ticker", "strat_combo", "dealer_regime"]):
        v = g[fwd_col].dropna().to_numpy()
        if len(v) < 30:
            continue
        hit = 100.0 * float((v > 0).mean())
        # Bootstrap 95% CI on hit rate
        boots = np.empty(500)
        for i in range(500):
            sample = rng.choice(v, size=len(v), replace=True)
            boots[i] = 100.0 * float((sample > 0).mean())
        rows.append({
            "ticker": ticker, "strat_combo": combo, "dealer_regime": regime,
            "n": len(v),
            "hit_pct": round(hit, 2),
            "hit_ci_lo": round(float(np.percentile(boots, 2.5)), 2),
            "hit_ci_hi": round(float(np.percentile(boots, 97.5)), 2),
            "mean_bps": round(float(v.mean()), 2),
            "std_bps": round(float(v.std(ddof=1)), 2),
        })
    return pd.DataFrame(rows)


# ────────────────────── Analysis 3: combo × marginal context ──────────────────────

def combo_marginal_grid(df: pd.DataFrame, ctx_col: str,
                         fwd_col: str = "fwd_ret_5bars_bps") -> pd.DataFrame:
    """For each (ticker, strat_combo, ctx_col), hit rate + mean. ctx_col is one of
    vix_tercile / gex_tercile / vex_tercile."""
    sub = df.dropna(subset=["strat_combo", ctx_col, fwd_col]).copy()
    grp = sub.groupby(["ticker", "strat_combo", ctx_col]).agg(
        n=(fwd_col, "count"),
        mean_bps=(fwd_col, "mean"),
        hit_pct=(fwd_col, lambda x: 100.0 * (x > 0).mean()),
    ).reset_index()
    grp = grp[grp["n"] >= 30]
    return grp


# ────────────────────── Analysis 4: indicator correlations ──────────────────────

def indicator_correlations(df: pd.DataFrame, fwd_col: str = "fwd_ret_5bars_bps") -> pd.DataFrame:
    """For each (ticker, strat_combo), Pearson + Spearman of each indicator vs fwd return."""
    rows = []
    sub = df.dropna(subset=["strat_combo", fwd_col]).copy()
    for (ticker, combo), g in sub.groupby(["ticker", "strat_combo"]):
        if len(g) < 50:
            continue
        for feat in NUMERIC_FEATURES:
            if feat not in g.columns:
                continue
            vals = g[feat].replace([np.inf, -np.inf], np.nan).dropna()
            if len(vals) < 30:
                continue
            target = g.loc[vals.index, fwd_col].dropna()
            if len(target) < 30:
                continue
            common_idx = vals.index.intersection(target.index)
            if len(common_idx) < 30:
                continue
            x = vals.loc[common_idx].to_numpy()
            y = target.loc[common_idx].to_numpy()
            try:
                pearson = float(np.corrcoef(x, y)[0, 1])
                spearman = float(sps.spearmanr(x, y, nan_policy="omit").correlation)
            except Exception:
                continue
            rows.append({
                "ticker": ticker, "strat_combo": combo, "feature": feat,
                "n": len(common_idx),
                "pearson": round(pearson, 4) if not np.isnan(pearson) else None,
                "spearman": round(spearman, 4) if not np.isnan(spearman) else None,
            })
    return pd.DataFrame(rows)


# ────────────────────── Analysis 5: ML modeling ──────────────────────

def _purged_wf_splits(dates: pd.Series, n_folds: int = 5, embargo_bars: int = 60):
    """López de Prado purged walk-forward. Embargo expressed in bar units (not days)."""
    unique = sorted(pd.Series(dates.unique()).dropna().tolist())
    n = len(unique)
    if n < n_folds * 2:
        return
    chunk = n // (n_folds + 1)
    for fold in range(n_folds):
        train_end = (fold + 1) * chunk
        test_start = min(n - 1, train_end + embargo_bars)
        test_end = min(n - 1, test_start + chunk)
        if test_start >= test_end:
            continue
        yield unique[:train_end], unique[test_start:test_end]


def _ic(y, p):
    if len(y) < 5: return float("nan")
    return float(np.corrcoef(y, p)[0, 1])


def _rank_ic(y, p):
    if len(y) < 5: return float("nan")
    return float(sps.spearmanr(y, p, nan_policy="omit").correlation)


def _ls_sharpe(test_df: pd.DataFrame, pred_col: str, ret_col: str,
                n_long_short: int = 5, cost_bps: float = 5.0) -> dict:
    """Daily long/short top-N: long top-N by pred, short bottom-N. Daily PnL =
    mean(long) - mean(short) - 2*cost_bps (entry + exit per side)."""
    bars_per_day = test_df.groupby(test_df["ts"].dt.date)
    pnl = []
    for d, day_slice in bars_per_day:
        s = day_slice.dropna(subset=[pred_col, ret_col])
        if len(s) < n_long_short * 2:
            continue
        ss = s.sort_values(pred_col, ascending=False)
        pnl.append(ss.head(n_long_short)[ret_col].mean()
                    - ss.tail(n_long_short)[ret_col].mean()
                    - 2 * cost_bps)
    if not pnl:
        return {"sharpe": float("nan"), "mean": float("nan"), "n_days": 0,
                "win_rate": float("nan")}
    a = np.array(pnl)
    mean = a.mean(); std = a.std(ddof=1) or float("nan")
    sharpe = (mean / std) * np.sqrt(252) if std and not np.isnan(std) else float("nan")
    return {"sharpe": float(sharpe), "mean": float(mean), "n_days": len(a),
            "win_rate": float((a > 0).mean())}


def train_models(df: pd.DataFrame, fwd_col: str = "fwd_ret_5bars_bps") -> dict:
    """Train Ridge / Lasso / LightGBM with purged walk-forward CV. Returns fold-level
    results + feature importance from the LGBM final fold."""
    sub = df.dropna(subset=[fwd_col]).copy().sort_values("ts").reset_index(drop=True)
    # One-hot encode categorical features
    sub_enc = pd.get_dummies(sub, columns=[
        "strat_candle", "prev_strat_candle", "strat_combo",
        "vix_tercile", "gex_tercile", "vex_tercile", "dealer_regime", "gamma_regime",
    ], dummy_na=False, dtype=np.int8)
    drop = {"ticker", "ts", "tf", "bar_date", "open", "high", "low", "close", "volume",
            "fwd_close_5bars", "fwd_close_15bars", "fwd_close_30bars", "fwd_close_60bars",
            "fwd_ret_5bars_bps", "fwd_ret_15bars_bps", "fwd_ret_30bars_bps", "fwd_ret_60bars_bps",
            "computed_at", "trigger_high", "trigger_low", "is_continuation", "is_reversal",
            "is_inside", "strat_setup"}
    feature_cols = [c for c in sub_enc.columns
                     if c not in drop and sub_enc[c].dtype in
                     (np.float64, np.int64, np.int32, np.int8, np.float32)]
    log.info("model features: %d", len(feature_cols))

    folds = list(_purged_wf_splits(sub_enc["ts"].dt.date, n_folds=5, embargo_bars=60))
    log.info("CV folds: %d", len(folds))

    results = []
    feat_imp_rows = []
    for fi, (train_dates, test_dates) in enumerate(folds):
        train_mask = sub_enc["ts"].dt.date.isin(train_dates)
        test_mask = sub_enc["ts"].dt.date.isin(test_dates)
        train = sub_enc[train_mask]
        test = sub_enc[test_mask]
        if len(train) < 1000 or len(test) < 500:
            continue

        Xt = train[feature_cols].fillna(0).values.astype(np.float32)
        Xv = test[feature_cols].fillna(0).values.astype(np.float32)
        sc = StandardScaler(); Xt_s = sc.fit_transform(Xt); Xv_s = sc.transform(Xv)
        yt = train[fwd_col].fillna(0).values
        yv = test[fwd_col].fillna(0).values
        yv_up = (yv > 0).astype(int)

        # Expanded linear model family per user request — validate signal
        # is robust across regularization styles + that linear-vs-tree gap
        # holds with more model variants.
        # PLSRegression must use a small n_components since we have 100+ feats
        for name, model, use_scaled in [
            ("ridge", Ridge(alpha=1.0), True),
            ("ridge_strong", Ridge(alpha=10.0), True),
            ("lasso", Lasso(alpha=0.001, max_iter=3000), True),
            ("lasso_sparse", Lasso(alpha=0.01, max_iter=3000), True),
            ("elasticnet", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=3000), True),
            ("bayes_ridge", BayesianRidge(), True),
            ("pls5", PLSRegression(n_components=5, max_iter=500), True),
            ("pls10", PLSRegression(n_components=10, max_iter=500), True),
            ("lgbm", lgb.LGBMRegressor(
                n_estimators=300, learning_rate=0.05, max_depth=6, num_leaves=31,
                min_child_samples=100, random_state=42, verbose=-1,
                n_jobs=-1,
            ), False),
            ("lgbm_shallow", lgb.LGBMRegressor(
                n_estimators=500, learning_rate=0.03, max_depth=4, num_leaves=15,
                min_child_samples=200, random_state=42, verbose=-1,
                n_jobs=-1,
            ), False),
        ]:
            try:
                model.fit(Xt_s if use_scaled else Xt, yt)
                pred = model.predict(Xv_s if use_scaled else Xv)
                # PLSRegression returns (n, 1) — flatten for downstream stats
                if hasattr(pred, "ndim") and pred.ndim > 1:
                    pred = pred.ravel()
                ic = _ic(yv, pred); ric = _rank_ic(yv, pred)
                try: auc = roc_auc_score(yv_up, pred)
                except Exception: auc = float("nan")
                tt = test.copy(); tt["pred"] = pred
                ls = _ls_sharpe(tt, "pred", fwd_col, n_long_short=5, cost_bps=5.0)
                results.append({
                    "fold": fi + 1, "model": name,
                    "n_train": len(train), "n_test": len(test),
                    "ic": round(ic, 4), "rank_ic": round(ric, 4),
                    "auc": round(auc, 4) if not np.isnan(auc) else None,
                    "ls_sharpe": round(ls["sharpe"], 3) if not np.isnan(ls["sharpe"]) else None,
                    "ls_mean_bps": round(ls["mean"], 2) if not np.isnan(ls["mean"]) else None,
                    "ls_win_rate": round(ls["win_rate"], 3) if ls["n_days"] > 0 else None,
                })
                if name == "lgbm" and fi == len(folds) - 1:
                    imp = model.booster_.feature_importance(importance_type="gain")
                    for fc, im in zip(feature_cols, imp):
                        feat_imp_rows.append({"feature": fc, "gain": float(im)})
                log.info("fold %d %s: IC=%+.4f rIC=%+.4f Sharpe=%+.2f bps=%+.1f",
                         fi + 1, name, ic, ric,
                         ls["sharpe"] if not np.isnan(ls["sharpe"]) else 0,
                         ls["mean"] if not np.isnan(ls["mean"]) else 0)
            except Exception as e:
                log.exception("model %s fold %d failed: %s", name, fi, e)

    return {
        "results": pd.DataFrame(results),
        "feat_imp": pd.DataFrame(feat_imp_rows).sort_values("gain", ascending=False)
                     if feat_imp_rows else pd.DataFrame(),
    }


# ────────────────────── Main ──────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tf", required=True, choices=["1m", "5m", "15m", "30m", "60m"])
    parser.add_argument("--ticker", default=None,
                        help="If set, filter to one ticker (SPY/IWM/QQQ). Default: pooled across all.")
    parser.add_argument("--fwd-col", default=None,
                        help="Forward-return column to use. Defaults to fwd_ret_5bars_bps.")
    parser.add_argument("--gcs-prefix", default=None,
                        help="GCS prefix. Defaults to research/p7-analysis[-per-ticker/{ticker}]/{tf}.")
    args = parser.parse_args()

    tf = args.tf
    fwd_col = args.fwd_col or "fwd_ret_5bars_bps"
    if args.gcs_prefix:
        prefix = args.gcs_prefix
    elif args.ticker:
        prefix = f"research/p7-analysis-per-ticker/{args.ticker}/{tf}"
    else:
        prefix = f"research/p7-analysis/{tf}"
    bucket = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
    log.info("P7 analysis: tf=%s ticker=%s fwd_col=%s gcs=gs://%s/%s",
             tf, args.ticker or "ALL", fwd_col, bucket, prefix)

    engine = get_engine()
    t0 = time.time()
    df = load_data(engine, tf, args.ticker)

    # Each analysis runs independently — log timing for each
    log.info("=== Analysis 1: strat transition grid ===")
    t = time.time()
    grid_trans = strat_transition_grid(df, fwd_col)
    _upload(grid_trans.to_csv(index=False), bucket, f"{prefix}/01_strat_transition.csv")
    log.info("  %d rows in %.1fs", len(grid_trans), time.time() - t)

    log.info("=== Analysis 2: combo × dealer_regime ===")
    t = time.time()
    grid_dealer = combo_dealer_grid(df, fwd_col)
    _upload(grid_dealer.to_csv(index=False), bucket, f"{prefix}/02_combo_dealer_regime.csv")
    log.info("  %d rows in %.1fs", len(grid_dealer), time.time() - t)

    log.info("=== Analysis 3a: combo × vix_tercile ===")
    t = time.time()
    _upload(combo_marginal_grid(df, "vix_tercile", fwd_col).to_csv(index=False),
            bucket, f"{prefix}/03a_combo_vix.csv")
    log.info("=== Analysis 3b: combo × gex_tercile ===")
    _upload(combo_marginal_grid(df, "gex_tercile", fwd_col).to_csv(index=False),
            bucket, f"{prefix}/03b_combo_gex.csv")
    log.info("=== Analysis 3c: combo × vex_tercile ===")
    _upload(combo_marginal_grid(df, "vex_tercile", fwd_col).to_csv(index=False),
            bucket, f"{prefix}/03c_combo_vex.csv")
    log.info("  marginal grids done in %.1fs", time.time() - t)

    log.info("=== Analysis 4: indicator correlations ===")
    t = time.time()
    grid_ind = indicator_correlations(df, fwd_col)
    _upload(grid_ind.to_csv(index=False), bucket, f"{prefix}/04_indicator_correlations.csv")
    log.info("  %d rows in %.1fs", len(grid_ind), time.time() - t)

    log.info("=== Analysis 5: ML models with purged walk-forward CV ===")
    t = time.time()
    ml = train_models(df, fwd_col)
    _upload(ml["results"].to_csv(index=False), bucket, f"{prefix}/05a_model_walkforward.csv")
    summary = ml["results"].groupby("model").agg(
        mean_ic=("ic", "mean"),
        std_ic=("ic", "std"),
        mean_rank_ic=("rank_ic", "mean"),
        mean_auc=("auc", "mean"),
        mean_ls_sharpe=("ls_sharpe", "mean"),
        mean_ls_bps=("ls_mean_bps", "mean"),
        mean_ls_win=("ls_win_rate", "mean"),
    ).round(4)
    _upload(summary.to_csv(), bucket, f"{prefix}/05b_model_summary.csv")
    _upload(ml["feat_imp"].head(50).to_csv(index=False), bucket,
            f"{prefix}/05c_feature_importance_top50.csv")
    log.info("  ML done in %.1fs", time.time() - t)

    log.info("=== ALL DONE for %s in %.1fs ===", tf, time.time() - t0)


if __name__ == "__main__":
    main()
