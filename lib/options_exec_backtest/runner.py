"""Walk-forward orchestrator for the options exec backtest.

Two modes:
  1. emit-timestamps  — runs the frozen type model on `ticker` × cells ×
     test windows, emits unique 5-min-rounded setup timestamps to a
     CSV. This is the input to the AV intraday backfill fetcher. We
     always emit the UNION (5-fold = 2022-2026 range) so the same
     fetched data covers both window-mode backtests.
  2. backtest         — same predictions, but each candidate gets a full
     option-trade lifecycle simulation via engine.simulate_option_setup.

We DO NOT modify any code under gcp/research/strat_engine/. We import
and reuse `featurize`, `make_lgbm`, `load_labeled_dataset` to keep the
per-fold model identical to the production type model.

We DO NOT modify lib/exec_backtest. Track B's reference module stays
untouched.

Walk-forward windows — TWO supported simultaneously (see WINDOWS dict):

  - 5fold (2022-2026): wider regime variety (bear / recovery / bull /
    current / partial). Test years 2022-2023 had only Mon/Wed/Fri 0DTE
    expirations for IWM (~62% coverage); setups on Tue/Thu void with
    `no_iv_snapshot`. Success bar: ≥ 4 of 5 positive folds.

  - 3fold (2024-2026): IWM daily 0DTE started Nov 2023, so 2024+
    has ~99% coverage and zero void-rate ambiguity. Loses 2022 bear
    and 2023 recovery regimes — single-bull-market sample. Success
    bar: ≥ 2 of 3 positive folds.
"""
from __future__ import annotations
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Heavy imports (strat_engine deps + sqlalchemy) deferred to first use —
# the engine + iv_lookup tests don't need the type model to import.
from lib.options_exec_backtest.engine import (
    OptionSetup, OptionTrade, OptionTradeSpec,
    simulate_option_setup, fold_stats,
)
from lib.options_exec_backtest.iv_lookup import IVLookup

log = logging.getLogger(__name__)


# 0DTE-restricted walk-forward windows. All folds train on data < cutoff
# and test on [cutoff, next_cutoff). The last cutoff's test_end is fixed
# at 2026-12-31 (current year-end).
WINDOWS: Dict[str, Dict] = {
    "5fold": {
        "cutoffs": [
            "2022-01-01",
            "2023-01-01",
            "2024-01-01",
            "2025-01-01",
            "2026-01-01",
        ],
        # ≥ 4 of 5 positive folds (75-80% threshold, matches Track B's 6/8)
        "positive_fold_threshold": 4,
    },
    "3fold": {
        "cutoffs": [
            "2024-01-01",
            "2025-01-01",
            "2026-01-01",
        ],
        # ≥ 2 of 3 positive folds (~67%, looser — fewer folds, less
        # statistical power, but coverage is clean)
        "positive_fold_threshold": 2,
    },
}

# Back-compat: callers that imported DEFAULT_CUTOFFS / POSITIVE_FOLD_THRESHOLD
# before the dual-window refactor keep working against the 5fold window.
DEFAULT_CUTOFFS = WINDOWS["5fold"]["cutoffs"]
POSITIVE_FOLD_THRESHOLD = WINDOWS["5fold"]["positive_fold_threshold"]

# Per-cell time stop. 5m/15m → 30 min; 30m → 60 min. Same as Track B.
TIME_STOP_BY_CELL = {"5m": 30, "15m": 30, "30m": 60}

INTRADAY_TABLE = {
    "IWM": "market_data_intraday_iwm",
    "SPY": "market_data_intraday_spy",
    "QQQ": "market_data_intraday_qqq",
}


def load_1m_bars(engine, ticker: str, start_date: str = "2021-06-01") -> pd.DataFrame:
    """Pull all 1-min RTH bars for `ticker` into memory ONCE."""
    from sqlalchemy import text
    if ticker not in INTRADAY_TABLE:
        raise ValueError(f"No intraday table mapped for ticker={ticker!r}")
    table = INTRADAY_TABLE[ticker]
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
    log.info("loading 1m %s bars from %s …", ticker, start_date)
    t0 = time.time()
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start_ts": start_ts})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    log.info("loaded 1m %s bars: %d rows in %.1fs (%s..%s)",
             ticker, len(df), time.time() - t0, df.index.min(), df.index.max())
    return df


def _slice_window_factory(m1_bars: pd.DataFrame):
    """O(log n) slice into the 1m bars for one setup window."""
    idx = m1_bars.index
    if not idx.is_monotonic_increasing:
        m1_bars = m1_bars.sort_index()
        idx = m1_bars.index

    def get_window(trigger_ts_close: pd.Timestamp, lookforward_min: int) -> pd.DataFrame:
        end = trigger_ts_close + pd.Timedelta(minutes=lookforward_min)
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
    confidence: float,
    lgbm_n_jobs: int = -1,
) -> pd.DataFrame:
    """ONE fold. Raw LightGBM, no calibration (matches production)."""
    from gcp.research.strat_engine.strat_config import LABEL_CLASSES
    from gcp.research.strat_engine.strat_pred_train import make_lgbm
    train_end_dt = np.datetime64(train_end)
    test_end_dt = np.datetime64(test_end)
    train_mask = bar_dates_arr < train_end_dt
    test_mask = (bar_dates_arr >= train_end_dt) & (bar_dates_arr < test_end_dt)
    n_train = int(train_mask.sum())
    n_test = int(test_mask.sum())
    log.info("    train n=%d test n=%d", n_train, n_test)
    if n_test == 0:
        return pd.DataFrame()

    model = make_lgbm(class_weight=None, n_jobs=lgbm_n_jobs)
    model.fit(X_full[train_mask], y_full[train_mask])
    X_te = X_full[test_mask]
    proba = model.predict_proba(X_te)

    classes_in_train = list(model.classes_)
    inv_label = {i: LABEL_CLASSES[c] for i, c in enumerate(classes_in_train)}

    top_idx = proba.argmax(axis=1)
    top_prob = proba.max(axis=1)
    top_label = np.array([inv_label[i] for i in top_idx])

    test_df = df_all.iloc[np.where(test_mask)[0]].copy()
    test_df["top_class"] = top_label
    test_df["top_prob"] = top_prob

    candidates = test_df[
        (test_df["top_class"].isin(("2U", "2D")))
        & (test_df["top_prob"] >= confidence)
    ].copy()
    log.info("    candidates: total=%d  long=%d  short=%d",
             len(candidates),
             int((candidates["top_class"] == "2U").sum()),
             int((candidates["top_class"] == "2D").sum()))
    return candidates


def _load_daily_rates(engine, start: str, end: str) -> Dict[pd.Timestamp, tuple]:
    """Load daily_rates for the fold range. Returns dict {date: (r, q)}.

    Per CLAUDE.md Rule 3.7, we do NOT silently default. If a date has no
    row, the setup at that date is voided ('r_unavailable' reason).
    """
    from sqlalchemy import text
    sql = text("""
        SELECT date, dgs3mo, sp500_div_yld
        FROM daily_rates
        WHERE date BETWEEN :s AND :e
        ORDER BY date
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"s": start, "e": end})
    if df.empty:
        log.warning("daily_rates: 0 rows for [%s..%s] — every setup will void", start, end)
        return {}
    out = {}
    for _, row in df.iterrows():
        d = pd.Timestamp(row["date"]).date()
        r = float(row["dgs3mo"]) if pd.notna(row["dgs3mo"]) else None
        q = float(row["sp500_div_yld"]) if pd.notna(row["sp500_div_yld"]) else 0.0
        if r is not None:
            out[d] = (r / 100.0 if r > 1.0 else r, q / 100.0 if q > 1.0 else q)
    log.info("daily_rates: %d valid days in [%s..%s]", len(out), start, end)
    return out


def emit_setup_timestamps(
    engine,
    ticker: str,
    cells: List[str],
    cutoffs: List[str],
    confidence: float,
    output_csv: str,
) -> int:
    """MODE 1: run the type model across all (cell, fold) combinations and
    write a CSV of unique (ticker, datetime_utc) pairs at which a setup
    fired. The CSV becomes the input to the AV intraday backfill.

    Timestamps are rounded to 5-min boundaries to maximize hit rate when
    fetching (the fetcher would otherwise need a separate snapshot per
    cell per minute).
    """
    from gcp.research.strat_engine.strat_config import (
        LABEL_COL, LABEL_TO_IDX, TF_MINUTES,
    )
    from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
    from gcp.research.strat_engine.strat_pred_train import featurize
    rows = []
    for cell in cells:
        df = load_labeled_dataset(engine, ticker, cell, include_next_bar_ohlc=False)
        df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

        X_df, _ = featurize(df)
        X_full = X_df.values.astype(np.float32, copy=False)
        y_full = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
        bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
        log.info("cell %s: dataset %d rows (%s..%s)",
                 cell, X_full.shape[0], df["bar_date"].min(), df["bar_date"].max())

        tf_min = TF_MINUTES[cell]
        for i, cut in enumerate(cutoffs):
            test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else "2026-12-31"
            log.info("  fold %d: %s..%s", i + 1, cut, test_end)
            cands = train_predict_fold(
                df, X_full, y_full, bar_dates_arr,
                cut, test_end, confidence=confidence,
            )
            if cands.empty:
                continue
            # trigger_ts_close = ts_open + TF minutes; that's the moment
            # the prediction emits and the moment we'd fetch IV.
            for _, row in cands.iterrows():
                ts_open = pd.Timestamp(row["ts"])
                if ts_open.tzinfo is None:
                    ts_open = ts_open.tz_localize("UTC")
                ts_close = ts_open + pd.Timedelta(minutes=tf_min)
                # Round to 5-min boundary
                ts_5 = ts_close.floor("5min")
                rows.append({"ticker": ticker, "datetime_utc": ts_5.isoformat()})

    if not rows:
        log.warning("emit_setup_timestamps: 0 candidates across all cells/folds")
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=["ticker", "datetime_utc"]).to_csv(output_csv, index=False)
        return 0

    out_df = pd.DataFrame(rows)
    # Dedupe so we never fetch the same (ticker, ts_5min) twice
    before = len(out_df)
    out_df = out_df.drop_duplicates().sort_values(["ticker", "datetime_utc"]).reset_index(drop=True)
    log.info("emit_setup_timestamps: %d candidates → %d unique 5-min timestamps",
             before, len(out_df))
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_csv, index=False)
    log.info("emit_setup_timestamps: wrote %s", output_csv)
    return len(out_df)


def run_one_cell(
    engine,
    ticker: str,
    cell: str,
    m1_bars: pd.DataFrame,
    cutoffs: List[str],
    confidence: float,
    target_multiple: float,
    otm_offset: int = 0,
    expiration_dte: int = 0,
) -> tuple[List[OptionTrade], List[dict]]:
    """Run all folds for one cell. Returns (trades, per-fold-stats)."""
    from gcp.research.strat_engine.strat_config import (
        LABEL_COL, LABEL_TO_IDX, TF_MINUTES,
    )
    from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
    from gcp.research.strat_engine.strat_pred_train import featurize
    log.info("─" * 70)
    log.info("CELL %s  cutoffs=%d  conf=%.2f  target=%.1fR  otm=%d  dte=%d",
             cell, len(cutoffs), confidence, target_multiple,
             otm_offset, expiration_dte)

    df = load_labeled_dataset(engine, ticker, cell, include_next_bar_ohlc=False)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

    X_df, _ = featurize(df)
    X_full = X_df.values.astype(np.float32, copy=False)
    y_full = df[LABEL_COL].map(LABEL_TO_IDX).values.astype(np.int64)
    bar_dates_arr = pd.DatetimeIndex(df["bar_date"]).values.astype("datetime64[D]")
    log.info("  cell dataset: %d rows × %d cols  (%s..%s)",
             X_full.shape[0], X_full.shape[1],
             df["bar_date"].min(), df["bar_date"].max())

    tf_minutes = TF_MINUTES[cell]
    time_stop = TIME_STOP_BY_CELL[cell]
    spec = OptionTradeSpec(
        target_multiple=target_multiple, time_stop_minutes=time_stop,
        otm_offset=otm_offset, expiration_dte=expiration_dte,
    )

    get_window = _slice_window_factory(m1_bars)
    lookforward_min = max(240, tf_minutes + time_stop + 60)

    # Risk-free + div yield once per fold (full-year span; per-day lookup
    # within engine call uses this dict)
    rates_full = _load_daily_rates(engine, cutoffs[0], cutoffs[-1])

    all_trades: List[OptionTrade] = []
    per_fold = []

    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else "2026-12-31"
        fold_label = f"{cut}..{test_end}"
        log.info("  fold %d/%d  %s", i + 1, len(cutoffs), fold_label)

        t0 = time.time()
        candidates = train_predict_fold(
            df, X_full, y_full, bar_dates_arr,
            cut, test_end, confidence=confidence,
        )
        if candidates.empty:
            per_fold.append({"fold": fold_label, "cell": cell, **fold_stats([])})
            continue

        # Preload IVs for this fold's date range — ONE query, never per setup
        iv_lookup = IVLookup.preload(
            engine, ticker=ticker, start=cut, end=test_end,
            expiry_horizon_days=max(1, expiration_dte),
        )

        fold_trades: List[OptionTrade] = []
        voided = {
            "no_iv_snapshot": 0,
            "no_underlying_trigger": 0,
            "no_rate": 0,
            "bsm_void": 0,
        }
        for setup_id, row in candidates.iterrows():
            ts_open = pd.Timestamp(row["ts"])
            if ts_open.tzinfo is None:
                ts_open = ts_open.tz_localize("UTC")
            ts_close = ts_open + pd.Timedelta(minutes=tf_minutes)
            direction = "long" if row["top_class"] == "2U" else "short"

            rate_date = ts_close.date()
            if rate_date not in rates_full:
                voided["no_rate"] += 1
                continue
            r, q = rates_full[rate_date]

            setup = OptionSetup(
                setup_id=int(setup_id), fold=fold_label, cell=cell,
                direction=direction,
                trigger_ts_open=ts_open, trigger_ts_close=ts_close,
                trigger_high=float(row["high"]),
                trigger_low=float(row["low"]),
                top_prob=float(row["top_prob"]),
            )
            window = get_window(ts_close, lookforward_min)
            trade = simulate_option_setup(
                setup, window, iv_lookup, spec, risk_free=r, div_yield=q,
            )
            if trade is not None:
                fold_trades.append(trade)
            else:
                voided["bsm_void"] += 1  # rough bucket — engine doesn't split

        stats = fold_stats(fold_trades)
        per_fold.append({"fold": fold_label, "cell": cell, **stats, "voided": voided})
        all_trades.extend(fold_trades)
        log.info("    fold trades=%d  hit_rate=%.3f  net_exp=$%.4f  total_net=$%.2f  voided=%s",
                 stats["n"], stats["hit_rate"], stats["net_exp"],
                 stats["total_net"], voided)
        log.info("    fold time: %.1fs", time.time() - t0)

    return all_trades, per_fold


def trades_to_dataframe(trades: List[OptionTrade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([{
        "setup_id": t.setup_id, "fold": t.fold, "cell": t.cell,
        "direction": t.direction, "kind": t.kind,
        "trigger_ts_open": t.trigger_ts_open,
        "trigger_ts_close": t.trigger_ts_close,
        "trigger_high": t.trigger_high, "trigger_low": t.trigger_low,
        "top_prob": t.top_prob,
        "iv_snapshot_ts": t.iv_snapshot_ts,
        "iv_snapshot_age_sec": t.iv_snapshot_age_sec,
        "iv_source": t.iv_source,
        "anchor_iv": t.anchor_iv,
        "strike": t.strike,
        "expiration": t.expiration,
        "risk_free": t.risk_free, "div_yield": t.div_yield,
        "entry_ts": t.entry_ts,
        "entry_underlying": t.entry_underlying,
        "entry_T_years": t.entry_T_years,
        "entry_premium": t.entry_premium,
        "initial_stop_underlying": t.initial_stop_underlying,
        "initial_target_underlying": t.initial_target_underlying,
        "target_multiple": t.target_multiple,
        "time_stop_minutes": t.time_stop_minutes,
        "exit_ts": t.exit_ts,
        "exit_underlying": t.exit_underlying,
        "exit_T_years": t.exit_T_years,
        "exit_premium": t.exit_premium,
        "exit_reason": t.exit_reason,
        "gross_pnl_per_contract": t.gross_pnl_per_contract,
        "cost_per_contract": t.cost_per_contract,
        "net_pnl_per_contract": t.net_pnl_per_contract,
        "theta_drag_share": t.theta_drag_share,
        "delta_implied_at_entry": t.delta_implied_at_entry,
    } for t in trades])


def evaluate_base_case_per_cell(
    per_fold_stats: List[dict],
    positive_fold_threshold: int = POSITIVE_FOLD_THRESHOLD,
) -> dict:
    """Apply the spec's binary pass/fail bar — parameterized on fold count.

    A cell PASSES base case iff ALL FOUR hold:
      1. net expectancy/trade > 0 in ≥ `positive_fold_threshold` folds
         (4/5 for 5fold window, 2/3 for 3fold window)
      2. aggregate net expectancy > $5 / contract (per brief)
      3. hit_rate × avg_win > miss_rate × avg_loss with ≥ 20% margin
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

    if total_net > 0:
        max_fold_share = max(f["total_net"] for f in per_fold_stats) / total_net
    else:
        max_fold_share = float("inf")

    # Asymmetry check: hit_rate × avg_win vs miss_rate × avg_loss
    # We aggregate avg_win / avg_loss across folds as weighted by n
    total_pos = sum(max(f["avg_win"], 0.0) * (f["hit_rate"] * f["n"]) for f in per_fold_stats)
    total_neg = sum(min(f["avg_loss"], 0.0) * ((1 - f["hit_rate"]) * f["n"]) for f in per_fold_stats)
    # positive number: hit × avg_win = aggregate winning P&L (per trade)
    # negative number: miss × avg_loss = aggregate losing P&L (per trade)
    if total_trades > 0:
        agg_pos_per_trade = total_pos / total_trades
        agg_neg_per_trade = total_neg / total_trades  # negative
        # 20% margin check: agg_pos / |agg_neg| >= 1.20
        if agg_neg_per_trade < 0:
            asymm_ratio = agg_pos_per_trade / abs(agg_neg_per_trade)
        else:
            asymm_ratio = float("inf") if agg_pos_per_trade > 0 else 0.0
    else:
        asymm_ratio = 0.0

    checks = {
        "c1_pos_exp_folds": (pos_exp, n_folds, pos_exp >= positive_fold_threshold),
        "c2_agg_net_exp": (weighted_exp, 5.0, weighted_exp > 5.0),
        "c3_asymm_ratio": (asymm_ratio, 1.20, asymm_ratio >= 1.20),
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
        "asymm_ratio": asymm_ratio,
        "total_net": total_net,
        "max_fold_share": max_fold_share,
    }
