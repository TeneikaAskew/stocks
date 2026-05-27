"""Walk-forward orchestrator for the exec backtest.

For each cell (5m / 15m / 30m) and each walk-forward fold:
  1. Load the labeled features for IWM (full range; reused across folds).
  2. Featurize once; slice train/test by bar_date < cutoff.
  3. Fit a raw LightGBM (calibration=none — matches production path in
     `strat_pred_train.py`).
  4. Predict on test window; filter to top-class ∈ {2U, 2D} AND
     top_prob >= confidence_threshold.
  5. Build Setup objects from the trigger bar's high/low.
  6. Replay each setup against pre-loaded 1m IWM bars using
     `engine.simulate_setup`.
  7. Aggregate to per-fold-per-cell stats.

Outputs:
  - results dict
  - per-trade DataFrame (for the audit ledger CSV)

We DO NOT modify any code under gcp/research/strat_engine/. We import and
reuse `featurize`, `make_lgbm`, `load_labeled_dataset` to keep the model
identical to the frozen production type model.
"""
from __future__ import annotations
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.research.strat_engine.strat_config import (
    LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX, TF_MINUTES,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize, make_lgbm

from lib.exec_backtest.engine import (
    Setup, Trade, TradeSpec, simulate_setup, fold_stats,
)

log = logging.getLogger(__name__)


# Same regime-spanning cutoffs as the locked walk-forward harness. The
# spec REQUIRES these exact cutoffs.
DEFAULT_CUTOFFS = [
    "2019-01-01",  # test 2019 (recovery)
    "2020-01-01",  # test 2020 (COVID)
    "2021-01-01",  # test 2021 (bull)
    "2022-01-01",  # test 2022 (bear, Fed tightening)
    "2023-01-01",  # test 2023 (recovery)
    "2024-01-01",  # test 2024 (bull continuation)
    "2025-01-01",  # test 2025
    "2026-01-01",  # test Jan-May 2026 (locked OOS cell)
]

# Per-cell time stop. 5m/15m → 30 min; 30m → 60 min. Per spec.
TIME_STOP_BY_CELL = {"5m": 30, "15m": 30, "30m": 60}


INTRADAY_TABLE = {"IWM": "market_data_intraday_iwm"}


def load_1m_iwm(engine, start_date: str = "2018-01-01") -> pd.DataFrame:
    """Pull all 1-min RTH bars for IWM into memory ONCE. Used by every
    fold/cell to evaluate trade lifecycles.

    Returns DataFrame indexed by UTC pd.DatetimeIndex with columns
    Open/High/Low/Close.
    """
    table = INTRADAY_TABLE["IWM"]
    sql = text(f"""
        SELECT ts, open AS "Open", high AS "High", low AS "Low",
               close AS "Close"
        FROM {table}
        WHERE interval = '1min'
          AND ts >= :start_ts
          AND (ts AT TIME ZONE 'America/New_York')::time
              BETWEEN '09:30' AND '15:59'
        ORDER BY ts
    """)
    start_ts = pd.Timestamp(start_date, tz="UTC")
    log.info("loading 1m IWM bars from %s …", start_date)
    t0 = time.time()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start_ts": start_ts})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    log.info("loaded 1m IWM bars: %d rows in %.1fs (%s..%s)",
             len(df), time.time() - t0, df.index.min(), df.index.max())
    return df


def _slice_window_factory(m1_bars: pd.DataFrame):
    """Return a closure that pulls a fast slice of 1m bars covering one
    setup. We need enough trailing bars to evaluate stop/target/time
    stop — 240 minutes (4 hours) is safe (max time-stop = 60 min for
    30m cell; the rest is buffer in case the entry doesn't fire until
    late in bar T+1's window).

    Pre-indexes m1_bars via `index.searchsorted` for O(log n) slicing.
    """
    idx = m1_bars.index
    if not idx.is_monotonic_increasing:
        m1_bars = m1_bars.sort_index()
        idx = m1_bars.index

    def get_window(trigger_ts_close: pd.Timestamp, lookforward_min: int) -> pd.DataFrame:
        # We grab [trigger_ts_close, trigger_ts_close + lookforward) — broad
        # enough that the simulate_setup helper can localize bar T+1 + post-
        # entry follow-on. RTH-only filter is already applied in load_1m_iwm,
        # so a 4-hour ceiling covers any same-session exit.
        end = trigger_ts_close + pd.Timedelta(minutes=lookforward_min)
        # Use searchsorted for speed
        lo = idx.searchsorted(trigger_ts_close)
        hi = idx.searchsorted(end)
        return m1_bars.iloc[lo:hi]

    return get_window


def train_predict_fold(
    df_all: pd.DataFrame,
    X_full: np.ndarray,
    y_full: np.ndarray,
    bar_dates_arr: np.ndarray,
    train_end: str,
    test_end: str,
    feature_cols: list,
    confidence: float,
    lgbm_n_jobs: int = -1,
) -> pd.DataFrame:
    """ONE fold. Train raw LGBM, predict on test window, return frame of
    candidate setups (top class + top prob + trigger bar context).
    """
    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    train_mask = bar_dates_arr < train_end_dt
    test_mask = (bar_dates_arr >= train_end_dt) & (bar_dates_arr < test_end_dt)
    n_train = int(train_mask.sum())
    n_test = int(test_mask.sum())
    log.info("    train n=%d test n=%d", n_train, n_test)
    if n_test == 0:
        return pd.DataFrame()

    # Raw LightGBM, no calibration wrapper. This matches the production
    # path in strat_pred_train.py (DEFAULT_CALIBRATION = "none").
    model = make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs)
    model.fit(X_full[train_mask], y_full[train_mask])

    X_te = X_full[test_mask]
    proba = model.predict_proba(X_te)

    # Map model.classes_ → label strings via the LABEL_CLASSES index.
    classes_in_train = list(model.classes_)
    inv_label = {i: LABEL_CLASSES[c] for i, c in enumerate(classes_in_train)}

    top_idx = proba.argmax(axis=1)
    top_prob = proba.max(axis=1)
    top_label = np.array([inv_label[i] for i in top_idx])

    # Test-window rows from the full df (preserves ordering with the model's
    # feature matrix — both came from the same featurize() pass).
    test_df = df_all.iloc[np.where(test_mask)[0]].copy()
    test_df["top_class"] = top_label
    test_df["top_prob"] = top_prob

    # Filter to high-confidence 2U / 2D
    candidates = test_df[
        (test_df["top_class"].isin(("2U", "2D")))
        & (test_df["top_prob"] >= confidence)
    ].copy()
    log.info("    candidates: total=%d  long=%d  short=%d",
             len(candidates),
             int((candidates["top_class"] == "2U").sum()),
             int((candidates["top_class"] == "2D").sum()))
    return candidates


def run_one_cell(
    engine,
    cell: str,
    m1_bars: pd.DataFrame,
    cutoffs: list,
    confidence: float,
    target_multiple: float,
    apply_ftfc_filter: bool = False,
    ftfc_threshold: float = 0.5,
    ftfc_lookup: pd.DataFrame | None = None,
) -> tuple[List[Trade], List[dict]]:
    """Run all walk-forward folds for one cell. Returns (trades, per-fold-stats)."""
    log.info("─" * 70)
    log.info("CELL %s  cutoffs=%d  conf=%.2f  target=%.1fR  ftfc=%s",
             cell, len(cutoffs), confidence, target_multiple,
             "on" if apply_ftfc_filter else "off")

    # Load labeled dataset for the cell (IWM only).
    df = load_labeled_dataset(engine, "IWM", cell, include_next_bar_ohlc=False)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

    # Featurize ONCE; same pattern as strat_walk_forward.py.
    X_df, feature_cols = featurize(df)
    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    log.info("  cell dataset: %d rows × %d cols  (%s..%s)",
             X_full.shape[0], X_full.shape[1],
             df["bar_date"].min(), df["bar_date"].max())

    # FTFC score from the existing strat_features column (if requested).
    # Falls back to NaN if the column isn't present.
    df["_ftfc_score"] = np.nan  # placeholder; computed per-bar below if needed

    tf_minutes = TF_MINUTES[cell]
    time_stop = TIME_STOP_BY_CELL[cell]
    spec = TradeSpec(target_multiple=target_multiple,
                      time_stop_minutes=time_stop)

    get_window = _slice_window_factory(m1_bars)
    # Lookforward: predicted bar's window (TF mins) + time stop (≤ 60) + 30
    # min buffer = 130 max. Use 240 to be very safe.
    lookforward_min = max(240, tf_minutes + time_stop + 60)

    all_trades: List[Trade] = []
    per_fold = []

    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else (
            (df["bar_date"].max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            if hasattr(df["bar_date"].max(), "strftime")
            else str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        )
        fold_label = f"{cut}..{test_end}"
        log.info("  fold %d/%d  %s", i + 1, len(cutoffs), fold_label)

        t0 = time.time()
        candidates = train_predict_fold(
            df, X_full, y_full, bar_dates_arr,
            cut, test_end, feature_cols, confidence=confidence,
        )
        if candidates.empty:
            per_fold.append({"fold": fold_label, "cell": cell, **fold_stats([])})
            continue

        # Replay each candidate
        fold_trades: List[Trade] = []
        for setup_id, row in candidates.iterrows():
            ts_open = pd.Timestamp(row["ts"])
            if ts_open.tzinfo is None:
                ts_open = ts_open.tz_localize("UTC")
            ts_close = ts_open + pd.Timedelta(minutes=tf_minutes)

            direction = "long" if row["top_class"] == "2U" else "short"

            # FTFC filter (variant 1 only). FTFC score is computed at the
            # trigger bar's CLOSE — that's the moment the prediction emitted.
            ftfc_score = float("nan")
            if ftfc_lookup is not None:
                from lib.exec_backtest.ftfc import ftfc_score_at
                ftfc_score = ftfc_score_at(ftfc_lookup, ts_close)

            if apply_ftfc_filter:
                if np.isnan(ftfc_score):
                    # No FTFC score available → reject
                    continue
                if direction == "long" and ftfc_score < ftfc_threshold:
                    continue
                if direction == "short" and ftfc_score > -ftfc_threshold:
                    continue

            setup = Setup(
                setup_id=int(setup_id),
                fold=fold_label, cell=cell, direction=direction,
                trigger_ts_open=ts_open, trigger_ts_close=ts_close,
                trigger_high=float(row["high"]),
                trigger_low=float(row["low"]),
                top_prob=float(row["top_prob"]),
                ftfc_score=ftfc_score,
            )
            window = get_window(ts_close, lookforward_min)
            trade = simulate_setup(setup, window, spec)
            if trade is not None:
                fold_trades.append(trade)

        stats = fold_stats(fold_trades)
        per_fold.append({"fold": fold_label, "cell": cell, **stats})
        all_trades.extend(fold_trades)
        log.info("    fold trades=%d  hit_rate=%.3f  net_exp=%.4f  total_net=%.2f  ddm=%.2f",
                 stats["n"], stats["hit_rate"], stats["net_exp"],
                 stats["total_net"], stats["max_dd"])
        log.info("    fold time: %.1fs", time.time() - t0)

    return all_trades, per_fold


def trades_to_dataframe(trades: List[Trade]) -> pd.DataFrame:
    return pd.DataFrame([{
        "setup_id": t.setup_id, "fold": t.fold, "cell": t.cell,
        "direction": t.direction,
        "trigger_ts_open": t.trigger_ts_open,
        "trigger_ts_close": t.trigger_ts_close,
        "trigger_high": t.trigger_high, "trigger_low": t.trigger_low,
        "top_prob": t.top_prob, "ftfc_score": t.ftfc_score,
        "entry_ts": t.entry_ts,
        "entry_stop_price": t.entry_stop_price,
        "entry_fill_price": t.entry_fill_price,
        "entry_gapped": t.entry_gapped,
        "initial_stop": t.initial_stop,
        "initial_target": t.initial_target,
        "target_multiple": t.target_multiple,
        "time_stop_minutes": t.time_stop_minutes,
        "exit_ts": t.exit_ts, "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "gross_pnl": t.gross_pnl, "net_pnl": t.net_pnl,
    } for t in trades])


def evaluate_base_case_per_cell(per_fold_stats: List[dict]) -> dict:
    """Apply the spec's binary pass/fail bar.

    A cell PASSES iff ALL FOUR hold:
      1. net expectancy/trade > 0 in >=6 of 8 folds
      2. aggregate net expectancy/trade > 2¢/share
      3. hit rate > 40%
      4. no single fold's net P&L > 50% of total (no single-regime dependence)
    """
    n_folds = len(per_fold_stats)
    if n_folds == 0:
        return {"verdict": "FAIL", "reason": "no_folds"}

    pos_exp = sum(1 for f in per_fold_stats if f["n"] > 0 and f["net_exp"] > 0)
    total_trades = sum(f["n"] for f in per_fold_stats)
    if total_trades == 0:
        return {"verdict": "FAIL", "reason": "no_trades",
                "pos_exp_folds": 0, "total_trades": 0}

    total_net = sum(f["total_net"] for f in per_fold_stats)
    weighted_exp = total_net / total_trades
    overall_wins = sum(f["hit_rate"] * f["n"] for f in per_fold_stats)
    overall_hit_rate = overall_wins / total_trades if total_trades > 0 else 0.0
    # Single-regime dominance
    if total_net > 0:
        max_fold_share = max(f["total_net"] for f in per_fold_stats) / total_net
    else:
        max_fold_share = float("inf")  # negative total ⇒ no concept of "share"

    checks = {
        "c1_pos_exp_folds": (pos_exp, n_folds, pos_exp >= 6),
        "c2_agg_net_exp": (weighted_exp, 0.02, weighted_exp > 0.02),
        "c3_hit_rate": (overall_hit_rate, 0.40, overall_hit_rate > 0.40),
        "c4_no_dom": (max_fold_share, 0.50,
                       max_fold_share <= 0.50 and total_net > 0),
    }
    passed = all(v[2] for v in checks.values())
    return {
        "verdict": "PASS" if passed else "FAIL",
        "checks": checks,
        "total_trades": total_trades,
        "pos_exp_folds": pos_exp,
        "n_folds": n_folds,
        "weighted_net_exp": weighted_exp,
        "overall_hit_rate": overall_hit_rate,
        "total_net": total_net,
        "max_fold_share": max_fold_share,
    }
