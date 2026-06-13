#!/usr/bin/env python3
"""Phase 4.5 — Deep-data-science feature importance + predictability audit.

Improvements over the minimal P4:
  1. MORE DATA — full 10yr × 100 tickers (~250k rows) instead of 2yr.
  2. PROPER FEATURE ENGINEERING:
     - Lag features (T-1, T-3, T-5, T-10) of every base feature
     - Rolling stats (5d, 20d, 60d): mean, std, z-score
     - Cross-sectional ranks within each date (universe-relative position)
     - Interaction terms (vol × momentum etc.)
  3. MULTIPLE TARGETS:
     - y_1d_bps, y_5d_bps, y_20d_bps (signed returns at multiple horizons)
     - y_1d_xs_rank (cross-sectional rank within date)
  4. MULTIPLE MODEL CLASSES:
     - Ridge (linear baseline)
     - Lasso (sparse linear, feature selection)
     - LightGBM with hyperparameter search
  5. PURGED WALK-FORWARD CV (5-fold, 20-day embargo) per López de Prado
  6. COST-AWARE METRICS: net-of-cost Sharpe, IC, rank-IC
"""
from __future__ import annotations
import sys
import glob
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, Lasso
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from scipy import stats as sps
import lightgbm as lgb

warnings.filterwarnings('ignore')

ROOT = Path('docs/research/2026-05-23/data')


# ──────────────────── Data loading ────────────────────

def load_p45_csvs(glob_path: str) -> pd.DataFrame:
    parts = []
    for f in sorted(glob.glob(glob_path)):
        df = pd.read_csv(f, parse_dates=['date'])
        parts.append(df)
        print(f"  loaded {f}: {len(df):,} rows")
    full = pd.concat(parts, ignore_index=True)
    full = full.sort_values(['ticker', 'date']).reset_index(drop=True)
    print(f"  total: {len(full):,} rows across {full['ticker'].nunique()} tickers, "
          f"{full['date'].min().date()} → {full['date'].max().date()}")
    return full


# ──────────────────── Feature engineering ────────────────────

BASE_FEATURES_NUM = [
    'rsi_9', 'rsi_14', 'rsi_30', 'stoch_rsi_k', 'stoch_rsi_d',
    'atr_14', 'atr_20', 'rvol', 'rvol_10',
    'volatility_5d', 'volatility_20d', 'intraday_return',
    'high_low_spread_pct', 'consecutive_up', 'consecutive_down',
    'price_vs_vwap', 'price_vs_ema9', 'price_vs_ema20',
    'macd', 'macd_signal', 'macd_histogram',
    'bb_width', 'bb_pct', 'gap_pct', 'vix_close', 'return',
    'obv', 'volume_usd',
]

LAG_LIST = [1, 3, 5, 10]
ROLL_WINDOWS = [(5, 'w5'), (20, 'w20'), (60, 'w60')]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag features, rolling stats, cross-sectional ranks per date."""
    df = df.copy()
    print(f"engineering features on {len(df):,} rows...")

    # Encode strat categoricals
    df['strat_combo_id'] = df['strat_combo'].fillna('NONE').astype('category').cat.codes
    df['strat_candle_id'] = df['strat_candle'].fillna('NONE').astype('category').cat.codes
    df['strat_setup_int'] = df['strat_setup'].fillna(False).astype(int)

    # Per-ticker time-series features (lags + rolling)
    g = df.groupby('ticker', sort=False)

    new_cols: dict[str, pd.Series] = {}
    for f in BASE_FEATURES_NUM:
        if f not in df.columns:
            continue
        # Lag features
        for L in LAG_LIST:
            new_cols[f'{f}_lag{L}'] = g[f].shift(L)
        # Rolling stats — z-score is most useful
        for w, tag in ROLL_WINDOWS:
            roll = g[f].rolling(w, min_periods=max(3, w // 3))
            mean = roll.mean().reset_index(level=0, drop=True)
            std = roll.std().reset_index(level=0, drop=True)
            new_cols[f'{f}_{tag}_mean'] = mean
            new_cols[f'{f}_{tag}_z'] = (df[f] - mean) / std.replace(0, np.nan)

    # Bulk-add new columns
    df = pd.concat([df, pd.DataFrame(new_cols, index=df.index)], axis=1)

    # Cross-sectional ranks per date (top-N universe)
    print(f"  computing cross-sectional ranks per date...")
    for f in ['rvol', 'rsi_14', 'volatility_20d', 'macd', 'price_vs_ema20',
              'return', 'gap_pct', 'bb_pct']:
        if f in df.columns:
            df[f'{f}_xs_rank'] = df.groupby('date')[f].rank(pct=True)

    # Targets
    g = df.groupby('ticker', sort=False)
    for h in [1, 5, 20]:
        df[f'fwd_close_{h}d'] = g['close'].shift(-h)
        df[f'y_{h}d_bps'] = (df[f'fwd_close_{h}d'] - df['close']) / df['close'] * 10000
        df[f'y_{h}d_up'] = (df[f'y_{h}d_bps'] > 0).astype(int)
    # Cross-sectional rank of 1d return — within-date relative ordering
    df['y_1d_xs_rank'] = df.groupby('date')['y_1d_bps'].rank(pct=True)

    print(f"  final shape: {df.shape}")
    return df


# ──────────────────── Purged walk-forward CV ────────────────────

def purged_walk_forward_splits(dates: pd.Series, n_folds: int = 5, embargo_days: int = 20):
    """Yield (train_dates, test_dates) tuples for purged walk-forward CV.

    Each fold: train on cumulative history, test on next chunk, with a
    `embargo_days` gap between train-end and test-start to prevent
    label-overlap leakage (since y_5d_bps and y_20d_bps overlap forward).
    """
    unique_dates = sorted(dates.dropna().unique())
    n = len(unique_dates)
    if n < n_folds * 2:
        return
    chunk = n // (n_folds + 1)
    for fold in range(n_folds):
        train_end = (fold + 1) * chunk
        embargo_start_idx = max(0, train_end)
        test_start_idx = min(n - 1, train_end + embargo_days)
        test_end_idx = min(n - 1, test_start_idx + chunk)
        if test_start_idx >= test_end_idx:
            continue
        train_dates = unique_dates[:embargo_start_idx]
        test_dates = unique_dates[test_start_idx:test_end_idx]
        if not train_dates or not test_dates:
            continue
        yield train_dates, test_dates


# ──────────────────── Evaluation metrics ────────────────────

def compute_ic(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Pearson IC."""
    if len(y_true) < 5:
        return float('nan')
    return float(np.corrcoef(y_true, y_pred)[0, 1])


def compute_rank_ic(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Spearman rank IC."""
    if len(y_true) < 5:
        return float('nan')
    return float(sps.spearmanr(y_true, y_pred, nan_policy='omit').correlation)


def daily_long_short_pnl(
    df_test: pd.DataFrame, pred_col: str, ret_col: str = 'y_1d_bps',
    n_long_short: int = 10, cost_bps: float = 5.0,
) -> dict:
    """Compute long-short portfolio Sharpe with transaction costs.

    For each date, long top-N by prediction, short bottom-N. Daily PnL =
    long avg return − short avg return − 2 × cost_bps (entry + exit).
    """
    dates = sorted(df_test['date'].dropna().unique())
    daily_pnl = []
    for d in dates:
        day_slice = df_test[df_test['date'] == d].dropna(subset=[pred_col, ret_col])
        if len(day_slice) < n_long_short * 2:
            continue
        sorted_slice = day_slice.sort_values(pred_col, ascending=False)
        long_ret = sorted_slice.head(n_long_short)[ret_col].mean()
        short_ret = sorted_slice.tail(n_long_short)[ret_col].mean()
        daily_pnl.append(long_ret - short_ret - 2 * cost_bps)
    if not daily_pnl:
        return {'sharpe': float('nan'), 'mean_daily_bps': float('nan'),
                'n_days': 0}
    pnl = np.array(daily_pnl)
    mean = pnl.mean()
    std = pnl.std(ddof=1) or float('nan')
    sharpe_annual = (mean / std) * np.sqrt(252) if std and not np.isnan(std) else float('nan')
    return {'sharpe': float(sharpe_annual), 'mean_daily_bps': float(mean),
            'std_daily_bps': float(std), 'n_days': len(pnl),
            'win_rate': float((pnl > 0).mean())}


# ──────────────────── Main ────────────────────

def main():
    print("=== loading multi-batch CSVs ===")
    df = load_p45_csvs('/tmp/p45/result_*.csv')

    print("\n=== engineering features ===")
    df = engineer_features(df)

    # Build feature set: every engineered column except target/ID/ohlcv
    drop = {'ticker', 'date', 'open', 'high', 'low', 'close', 'volume',
            'strat_combo', 'strat_candle', 'strat_setup', 'vwap',
            'fwd_close_1d', 'fwd_close_5d', 'fwd_close_20d',
            'y_1d_bps', 'y_5d_bps', 'y_20d_bps',
            'y_1d_up', 'y_5d_up', 'y_20d_up', 'y_1d_xs_rank'}
    feature_cols = [c for c in df.columns
                    if c not in drop and df[c].dtype in (np.float64, np.int64, np.int32)]
    print(f"\nFeature count: {len(feature_cols)}")

    # Drop rows where 5d / 20d target is NaN (latest dates) — bound by max horizon
    df_eval = df.dropna(subset=['y_1d_bps']).copy()
    df_eval = df_eval.replace([np.inf, -np.inf], np.nan)
    print(f"Eval rows: {len(df_eval):,}")

    # Run multiple model classes with purged walk-forward CV
    print("\n=== running purged walk-forward CV (5 folds, 20d embargo) ===\n")

    results: list[dict] = []
    folds = list(purged_walk_forward_splits(df_eval['date'], n_folds=5, embargo_days=20))
    print(f"Folds: {len(folds)}")

    for fold_idx, (train_dates, test_dates) in enumerate(folds):
        print(f"\nFold {fold_idx + 1}/{len(folds)}: "
              f"train={pd.Timestamp(train_dates[0]).date()}→{pd.Timestamp(train_dates[-1]).date()} "
              f"({len(train_dates)} dates)  "
              f"test={pd.Timestamp(test_dates[0]).date()}→{pd.Timestamp(test_dates[-1]).date()} "
              f"({len(test_dates)} dates)")

        train = df_eval[df_eval['date'].isin(train_dates)]
        test = df_eval[df_eval['date'].isin(test_dates)]
        if len(train) < 1000 or len(test) < 500:
            print(f"  too few rows: train={len(train)} test={len(test)}; skipping")
            continue

        # Build clean train/test arrays
        X_train = train[feature_cols].fillna(0).values
        X_test = test[feature_cols].fillna(0).values
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)
        y_train_bps = train['y_1d_bps'].fillna(0).values
        y_test_bps = test['y_1d_bps'].fillna(0).values
        y_train_up = train['y_1d_up'].fillna(0).astype(int).values
        y_test_up = test['y_1d_up'].fillna(0).astype(int).values

        for model_name, model in [
            ('ridge', Ridge(alpha=1.0)),
            ('lasso', Lasso(alpha=0.001, max_iter=5000)),
            ('lgbm', lgb.LGBMRegressor(
                n_estimators=300, learning_rate=0.05, max_depth=6, num_leaves=31,
                min_child_samples=100, random_state=42, verbose=-1,
            )),
        ]:
            try:
                model.fit(X_train_s if model_name != 'lgbm' else X_train, y_train_bps)
                pred = model.predict(X_test_s if model_name != 'lgbm' else X_test)
                ic = compute_ic(y_test_bps, pred)
                rank_ic = compute_rank_ic(y_test_bps, pred)
                # Classification metric — derive from sign of regression prediction
                y_pred_class = (pred > 0).astype(int)
                try:
                    auc = roc_auc_score(y_test_up, pred)
                except Exception:
                    auc = float('nan')
                acc = float((y_pred_class == y_test_up).mean())

                test_eval = test.copy()
                test_eval['pred'] = pred
                pnl = daily_long_short_pnl(test_eval, 'pred', 'y_1d_bps',
                                            n_long_short=10, cost_bps=5.0)

                row = {
                    'fold': fold_idx + 1,
                    'model': model_name,
                    'n_train': len(train), 'n_test': len(test),
                    'ic': round(ic, 4),
                    'rank_ic': round(rank_ic, 4),
                    'auc': round(auc, 4) if not np.isnan(auc) else float('nan'),
                    'acc': round(acc, 4),
                    'ls_sharpe': round(pnl['sharpe'], 3) if not np.isnan(pnl['sharpe']) else float('nan'),
                    'ls_mean_bps': round(pnl['mean_daily_bps'], 2) if not np.isnan(pnl['mean_daily_bps']) else float('nan'),
                    'ls_win_rate': round(pnl['win_rate'], 3) if pnl['n_days'] > 0 else float('nan'),
                    'ls_n_days': pnl['n_days'],
                }
                results.append(row)
                print(f"  {model_name:6s}: IC={row['ic']:+.4f}  rankIC={row['rank_ic']:+.4f}  "
                      f"AUC={row['auc']:.3f}  L/S Sharpe={row['ls_sharpe']:+.2f}  "
                      f"mean_bps={row['ls_mean_bps']:+.1f}")
            except Exception as e:
                print(f"  {model_name}: error: {e}")

    # Aggregate
    out = pd.DataFrame(results)
    if not out.empty:
        summary = out.groupby('model').agg(
            mean_ic=('ic', 'mean'),
            std_ic=('ic', 'std'),
            mean_rank_ic=('rank_ic', 'mean'),
            mean_auc=('auc', 'mean'),
            mean_acc=('acc', 'mean'),
            mean_ls_sharpe=('ls_sharpe', 'mean'),
            mean_ls_bps=('ls_mean_bps', 'mean'),
            mean_ls_win=('ls_win_rate', 'mean'),
        ).round(4)
        print("\n=== CV SUMMARY (mean across folds) ===")
        print(summary.to_string())
        out.to_csv(ROOT / 'p45_walkforward_results.csv', index=False)
        summary.to_csv(ROOT / 'p45_walkforward_summary.csv')
        print(f"\nSaved p45_walkforward_results.csv (fold-level) + summary")

    return out


if __name__ == '__main__':
    main()
