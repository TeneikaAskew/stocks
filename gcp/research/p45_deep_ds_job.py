#!/usr/bin/env python3
"""Phase 4.5 — Deep-data-science predictability audit (Cloud Run Job version).

Runs the same analysis as scripts/research/p45_deep_data_science.py but:
  - Pulls full 10yr × 100-ticker data directly from Cloud SQL (no
    artifact row cap)
  - Installs lightgbm/sklearn/scipy at job startup (these are dev-only
    deps deliberately excluded from requirements-gcp.txt to keep the
    production image lean — see requirements-gcp.txt comment block)
  - Writes results to GCS as parquet + summary CSV so they can be
    pulled to the local report without a separate db-query dispatch

Rule 0 sizing:
  Volume:   100 tickers × ~2500 days = 250k rows × ~50 cols
  Velocity: 1 single batched SELECT (no per-ticker round-trip)
  Wall:     ~2 min data pull + ~5 min feature engineering + ~3 min
            5-fold CV × 3 models = ~10 min total
  Timeout:  1800s (30 min) = 3× wall estimate
  Memory:   ~4GB peak (250k rows × 200 engineered features × 8 bytes
            = 400MB + LightGBM working set ~2GB)
  Retries:  0
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import subprocess
import time
from pathlib import Path

import pandas as pd
import numpy as np

# Install ML deps at startup if missing.
# Cleaner than baking into the prod image — see requirements-gcp.txt
def _ensure_ml_deps():
    needed = ['lightgbm', 'scikit-learn', 'scipy']
    for pkg in needed:
        try:
            __import__(pkg.replace('-', '_').replace('scikit_learn', 'sklearn'))
        except ImportError:
            print(f"installing {pkg}...", flush=True)
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])

_ensure_ml_deps()

import lightgbm as lgb
from sklearn.linear_model import Ridge, Lasso
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy import stats as sps

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gcp.database import get_engine
from google.cloud import storage as gcs
from lib.logging_config import setup_logging


def _upload_to_gcs(content: str, bucket_name: str, blob_path: str):
    """Write a string to gs://bucket/blob_path."""
    client = gcs.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(content, content_type='text/csv')
    return f"gs://{bucket_name}/{blob_path}"

setup_logging()
log = logging.getLogger(__name__)

# ──────────────────── Data ────────────────────

UNIVERSE_DEFAULT = """SPY NVDA QQQ MU MSFT AMD AAPL AMZN META GOOGL IWM AVGO GOOG PLTR
LITE TSM MRVL QCOM CRWV LLY MSTR NBIS AMAT JPM STX BE RKLB CRM V HOOD GLW ARM WMT CSCO IREN
APP COHR COIN TXN COST AAOI JNJ CRCL ASTS DELL BABA ANET IONQ HD ADI ABBV BKNG APH PG ADBE
SHOP INTU UBER TMUS KO ALAB SNOW MCD SMCI ETN ON ACN SPOT PFE NET MELI CEG OXY DIS AMGN
MPWR DDOG MCHP OKLO MCK AZO GILD DASH SNPS PWR SATS AKAM TJX LNG SBUX PDD HIMS SHEL VST DVN
NVO PYPL CVS NU PH""".split()


def load_data(engine, tickers: list[str], start_date: str) -> pd.DataFrame:
    """Pull market_data_daily for the universe via SQLAlchemy text() query."""
    from sqlalchemy import text
    tickers_sql = ",".join(f"'{t}'" for t in tickers)
    sql = text(f"""
        SELECT m.ticker, m.date,
               m.open, m.high, m.low, m.close, m.volume,
               m.ma_5, m.ma_10, m.ma_20, m.ma_50, m.ema_9, m.ema_20, m.ema_50, m.sma_200,
               m.rsi_9, m.rsi_14, m.rsi_30, m.stoch_rsi_k, m.stoch_rsi_d,
               m.atr_14, m.atr_20, m.obv, m.rvol, m.rvol_10, m.volume_ma_10, m.volume_ma_20,
               m.return, m.volatility_5d, m.volatility_20d, m.intraday_return, m.high_low_spread_pct,
               m.consecutive_up, m.consecutive_down, m.vwap, m.price_vs_vwap, m.price_vs_ema9, m.price_vs_ema20,
               m.strat_candle, m.strat_combo, m.strat_setup,
               m.macd, m.macd_signal, m.macd_histogram, m.bb_width, m.bb_pct,
               m.gap_pct, v.close AS vix_close
        FROM market_data_daily m
        LEFT JOIN market_data_daily v ON v.ticker = '^VIX' AND v.date = m.date
        WHERE m.ticker IN ({tickers_sql}) AND m.date >= :start_date
        ORDER BY m.ticker, m.date
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start_date": start_date})
    df['date'] = pd.to_datetime(df['date'])
    return df


# ──────────────────── Feature engineering ────────────────────

BASE_FEATURES_NUM = [
    'rsi_9', 'rsi_14', 'rsi_30', 'stoch_rsi_k', 'stoch_rsi_d',
    'atr_14', 'atr_20', 'rvol', 'rvol_10',
    'volatility_5d', 'volatility_20d', 'intraday_return',
    'high_low_spread_pct', 'consecutive_up', 'consecutive_down',
    'price_vs_vwap', 'price_vs_ema9', 'price_vs_ema20',
    'macd', 'macd_signal', 'macd_histogram',
    'bb_width', 'bb_pct', 'gap_pct', 'vix_close', 'return',
    'obv',
]
LAG_LIST = [1, 3, 5, 10]
ROLL_WINDOWS = [(5, 'w5'), (20, 'w20'), (60, 'w60')]
XS_RANK_FEATS = ['rvol', 'rsi_14', 'volatility_20d', 'macd', 'price_vs_ema20',
                 'return', 'gap_pct', 'bb_pct']


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['strat_combo_id'] = df['strat_combo'].fillna('NONE').astype('category').cat.codes
    df['strat_candle_id'] = df['strat_candle'].fillna('NONE').astype('category').cat.codes
    df['strat_setup_int'] = df['strat_setup'].fillna(False).astype(int)

    g = df.groupby('ticker', sort=False)
    new_cols: dict[str, pd.Series] = {}
    for f in BASE_FEATURES_NUM:
        if f not in df.columns: continue
        for L in LAG_LIST:
            new_cols[f'{f}_lag{L}'] = g[f].shift(L)
        for w, tag in ROLL_WINDOWS:
            roll = g[f].rolling(w, min_periods=max(3, w // 3))
            mean = roll.mean().reset_index(level=0, drop=True)
            std = roll.std().reset_index(level=0, drop=True)
            new_cols[f'{f}_{tag}_mean'] = mean
            new_cols[f'{f}_{tag}_z'] = (df[f] - mean) / std.replace(0, np.nan)
    df = pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)

    log.info("computing cross-sectional ranks per date...")
    for f in XS_RANK_FEATS:
        if f in df.columns:
            df[f'{f}_xs_rank'] = df.groupby('date')[f].rank(pct=True)

    g = df.groupby('ticker', sort=False)
    for h in [1, 5, 20]:
        df[f'fwd_close_{h}d'] = g['close'].shift(-h)
        df[f'y_{h}d_bps'] = (df[f'fwd_close_{h}d'] - df['close']) / df['close'] * 10000
        df[f'y_{h}d_up'] = (df[f'y_{h}d_bps'] > 0).astype(int)
    df['y_1d_xs_rank'] = df.groupby('date')['y_1d_bps'].rank(pct=True)
    return df


# ──────────────────── CV and metrics ────────────────────

def purged_walk_forward_splits(dates: pd.Series, n_folds: int = 5, embargo_days: int = 20):
    unique_dates = sorted(dates.dropna().unique())
    n = len(unique_dates)
    if n < n_folds * 2: return
    chunk = n // (n_folds + 1)
    for fold in range(n_folds):
        train_end = (fold + 1) * chunk
        test_start = min(n - 1, train_end + embargo_days)
        test_end = min(n - 1, test_start + chunk)
        if test_start >= test_end: continue
        yield unique_dates[:train_end], unique_dates[test_start:test_end]


def compute_ic(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 5: return float('nan')
    return float(np.corrcoef(y_true, y_pred)[0, 1])


def compute_rank_ic(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    if len(y_true) < 5: return float('nan')
    return float(sps.spearmanr(y_true, y_pred, nan_policy='omit').correlation)


def daily_long_short(df_test: pd.DataFrame, pred_col: str, ret_col: str,
                     n_long_short: int = 10, cost_bps: float = 5.0) -> dict:
    dates = sorted(df_test['date'].dropna().unique())
    pnl = []
    for d in dates:
        s = df_test[df_test['date'] == d].dropna(subset=[pred_col, ret_col])
        if len(s) < n_long_short * 2: continue
        ss = s.sort_values(pred_col, ascending=False)
        pnl.append(ss.head(n_long_short)[ret_col].mean() - ss.tail(n_long_short)[ret_col].mean() - 2 * cost_bps)
    if not pnl:
        return {'sharpe': float('nan'), 'mean_daily_bps': float('nan'), 'n_days': 0,
                'win_rate': float('nan'), 'std_daily_bps': float('nan')}
    arr = np.array(pnl)
    mean = arr.mean(); std = arr.std(ddof=1) or float('nan')
    sharpe = (mean / std) * np.sqrt(252) if std and not np.isnan(std) else float('nan')
    return {'sharpe': float(sharpe), 'mean_daily_bps': float(mean),
            'std_daily_bps': float(std), 'n_days': len(pnl),
            'win_rate': float((arr > 0).mean())}


# ──────────────────── Main ────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tickers', default=','.join(UNIVERSE_DEFAULT))
    parser.add_argument('--start-date', default='2016-01-01')
    parser.add_argument('--n-folds', type=int, default=5)
    parser.add_argument('--embargo-days', type=int, default=20)
    parser.add_argument('--gcs-prefix', default=f'p45-{int(time.time())}')
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.replace(',', ' ').split() if t.strip()]
    log.info("P4.5 deep DS audit: %d tickers, since %s, %d folds embargo=%d",
             len(tickers), args.start_date, args.n_folds, args.embargo_days)

    engine = get_engine()
    t0 = time.time()

    log.info("loading raw bars...")
    df = load_data(engine, tickers, args.start_date)
    log.info("loaded %d rows; engineering features...", len(df))

    df = engineer_features(df)
    log.info("post-engineering: %s (%.1fs)", df.shape, time.time() - t0)

    drop = {'ticker', 'date', 'open', 'high', 'low', 'close', 'volume',
            'strat_combo', 'strat_candle', 'strat_setup', 'vwap',
            'fwd_close_1d', 'fwd_close_5d', 'fwd_close_20d',
            'y_1d_bps', 'y_5d_bps', 'y_20d_bps', 'y_1d_up', 'y_5d_up', 'y_20d_up',
            'y_1d_xs_rank'}
    feature_cols = [c for c in df.columns if c not in drop and df[c].dtype in (np.float64, np.int64, np.int32, 'int8')]
    log.info("feature count: %d", len(feature_cols))

    df_eval = df.dropna(subset=['y_1d_bps']).copy().replace([np.inf, -np.inf], np.nan)
    folds = list(purged_walk_forward_splits(df_eval['date'], args.n_folds, args.embargo_days))
    log.info("CV folds: %d", len(folds))

    results: list[dict] = []
    feat_imp_rows: list[dict] = []
    for fi, (train_dates, test_dates) in enumerate(folds):
        train = df_eval[df_eval['date'].isin(train_dates)]
        test = df_eval[df_eval['date'].isin(test_dates)]
        if len(train) < 1000 or len(test) < 500:
            log.info("fold %d skip: train=%d test=%d", fi + 1, len(train), len(test))
            continue
        log.info("fold %d/%d: train=%s..%s (%d) test=%s..%s (%d)",
                 fi + 1, len(folds),
                 pd.Timestamp(train_dates[0]).date(), pd.Timestamp(train_dates[-1]).date(), len(train),
                 pd.Timestamp(test_dates[0]).date(), pd.Timestamp(test_dates[-1]).date(), len(test))

        Xt = train[feature_cols].fillna(0).values
        Xv = test[feature_cols].fillna(0).values
        sc = StandardScaler(); Xt_s = sc.fit_transform(Xt); Xv_s = sc.transform(Xv)
        yt_bps = train['y_1d_bps'].fillna(0).values
        yv_bps = test['y_1d_bps'].fillna(0).values
        yv_up = test['y_1d_up'].fillna(0).astype(int).values

        for name, model, use_scaled in [
            ('ridge', Ridge(alpha=1.0), True),
            ('lasso', Lasso(alpha=0.001, max_iter=5000), True),
            ('lgbm',  lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, max_depth=6,
                                        num_leaves=31, min_child_samples=100,
                                        random_state=42, verbose=-1), False),
        ]:
            try:
                X_train = Xt_s if use_scaled else Xt
                X_test = Xv_s if use_scaled else Xv
                model.fit(X_train, yt_bps)
                pred = model.predict(X_test)
                ic = compute_ic(yv_bps, pred)
                rank_ic = compute_rank_ic(yv_bps, pred)
                auc = roc_auc_score(yv_up, pred) if len(np.unique(yv_up)) > 1 else float('nan')
                test_eval = test.copy(); test_eval['pred'] = pred
                pnl = daily_long_short(test_eval, 'pred', 'y_1d_bps', n_long_short=10, cost_bps=5.0)

                results.append({'fold': fi + 1, 'model': name,
                                 'n_train': len(train), 'n_test': len(test),
                                 'ic': round(ic, 4), 'rank_ic': round(rank_ic, 4),
                                 'auc': round(auc, 4) if not np.isnan(auc) else None,
                                 'ls_sharpe': round(pnl['sharpe'], 3) if not np.isnan(pnl['sharpe']) else None,
                                 'ls_mean_bps': round(pnl['mean_daily_bps'], 2) if not np.isnan(pnl['mean_daily_bps']) else None,
                                 'ls_win_rate': round(pnl['win_rate'], 3) if pnl['n_days'] > 0 else None,
                                 'ls_n_days': pnl['n_days']})
                log.info("  %s: IC=%+.4f rank_IC=%+.4f AUC=%.3f LS_Sharpe=%+.2f mean_bps=%+.1f",
                         name, ic, rank_ic, auc if not np.isnan(auc) else 0, pnl['sharpe'] if not np.isnan(pnl['sharpe']) else 0,
                         pnl['mean_daily_bps'] if not np.isnan(pnl['mean_daily_bps']) else 0)

                # Feature importance for the lgbm model — only on last fold to save space
                if name == 'lgbm' and fi == len(folds) - 1:
                    fi_arr = model.booster_.feature_importance(importance_type='gain')
                    for fc, imp in zip(feature_cols, fi_arr):
                        feat_imp_rows.append({'feature': fc, 'importance_gain': float(imp), 'fold': fi + 1})

            except Exception as e:
                log.exception("model %s failed: %s", name, e)

    out_df = pd.DataFrame(results)
    summary = out_df.groupby('model').agg(
        mean_ic=('ic', 'mean'),
        std_ic=('ic', 'std'),
        mean_rank_ic=('rank_ic', 'mean'),
        mean_auc=('auc', 'mean'),
        mean_ls_sharpe=('ls_sharpe', 'mean'),
        mean_ls_bps=('ls_mean_bps', 'mean'),
        mean_ls_win=('ls_win_rate', 'mean'),
    ).round(4)
    log.info("\n=== CV SUMMARY ===\n%s", summary.to_string())

    # Upload to GCS
    bucket = os.environ.get('GCS_BUCKET', f'{os.environ.get("PROJECT_ID","adept-mountain-474619-d4")}-trading-data')
    prefix = f"research/{args.gcs_prefix}"
    log.info("uploading to gs://%s/%s/", bucket, prefix)

    _upload_to_gcs(out_df.to_csv(index=False), bucket, f"{prefix}/walkforward_results.csv")
    _upload_to_gcs(summary.to_csv(), bucket, f"{prefix}/walkforward_summary.csv")
    if feat_imp_rows:
        fi_df = pd.DataFrame(feat_imp_rows).sort_values('importance_gain', ascending=False)
        _upload_to_gcs(fi_df.to_csv(index=False), bucket, f"{prefix}/feature_importance.csv")
    log.info("Done in %.1fs", time.time() - t0)


if __name__ == '__main__':
    main()
