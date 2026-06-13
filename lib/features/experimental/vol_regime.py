"""Family 4 — Volatility-regime features.

Adds DAILY-rolled volatility-regime features that the per-bar strat_features
indicators (ATR, Bollinger width, etc.) don't capture. The hypothesis: if
direction is learnable in some regimes but not others, the model needs an
explicit regime label, not just within-bar magnitude.

Per-bar features at bar T (timestamp t, bar_date d):
  - atr_pct_d1            : daily ATR(14) at d-1 / SMA20(close) at d-1
                            (volatility magnitude normalized by price level)
  - atr_ratio_d1_vs_d20   : daily ATR(14) at d-1 / SMA20( daily ATR(14) )
                            (current vol vs trailing month vol → regime
                            expansion / contraction)
  - rv_5d                 : 5-day realized vol of daily returns,
                            annualized (sqrt(252)) at d-1
  - rv_20d                : 20-day realized vol of daily returns at d-1
  - rv_ratio_5d_20d       : rv_5d / rv_20d at d-1 (short-term vol relative
                            to medium-term — leading regime change)
  - gap_open_pct_d        : (open of bar T's session) / (close of d-1) - 1
                            captured at the FIRST bar of each session and
                            broadcast to all bars in the session. This IS
                            available at bar T because by the time the first
                            intraday bar fires, the day's open is already
                            known.
  - true_range_vs_atr_d1  : last bar's (high-low) / daily-ATR(14) of d-1.
                            Magnitude of the CURRENT bar relative to the
                            daily-vol regime. Computed from bar T's own
                            high-low (which IS available at close of bar T).

LEAK SAFETY:
  - All daily features use d-1 (the prior day's data).
  - gap_open_pct uses the first bar's open of the SAME session — by
    definition available at bar T's close (bar T came AFTER the session
    opened).
  - true_range_vs_atr_d1 uses bar T's own close-known high-low, normalized
    by d-1's daily ATR (not d's, which wouldn't exist yet).
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text

log = logging.getLogger(__name__)


def _load_daily(engine, ticker: str, since: str, until: str) -> pd.DataFrame:
    sql = text(
        """
        SELECT date, open, high, low, close
        FROM market_data_daily
        WHERE ticker = :tk AND date >= :s AND date <= :u
        ORDER BY date
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"tk": ticker, "s": since, "u": until})
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("date")


def _true_range(d: pd.DataFrame) -> pd.Series:
    """True range using prev-close (Welles Wilder)."""
    prev_close = d["close"].shift(1)
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - prev_close).abs(),
        (d["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def add_vol_regime_features(df: pd.DataFrame, ticker: str,
                              engine) -> pd.DataFrame:
    """Family-4 feature joiner."""
    log.info("Family 4 (vol regime): adding %d-row dataset for %s", len(df), ticker)
    if "bar_date" not in df.columns:
        raise RuntimeError("vol_regime joiner requires 'bar_date' column")

    bar_dates = pd.to_datetime(df["bar_date"]).dt.date
    since = (pd.Timestamp(bar_dates.min()) - pd.Timedelta(days=120)).date().isoformat()
    until = pd.Timestamp(bar_dates.max()).date().isoformat()

    daily = _load_daily(engine, ticker, since, until)
    if daily.empty:
        raise RuntimeError(f"vol-regime family INFEASIBLE: no daily data for {ticker}")

    # Daily features (indexed by date)
    daily = daily.sort_index()
    tr = _true_range(daily)
    atr14 = tr.rolling(14, min_periods=7).mean()
    sma20 = daily["close"].rolling(20, min_periods=10).mean()

    feats_daily = pd.DataFrame(index=daily.index)
    feats_daily["atr_pct_d1"] = atr14 / sma20
    feats_daily["atr_ratio_d1_vs_d20"] = atr14 / atr14.rolling(20, min_periods=10).mean()

    daily_ret = daily["close"].pct_change()
    rv5 = daily_ret.rolling(5, min_periods=3).std() * np.sqrt(252)
    rv20 = daily_ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    feats_daily["rv_5d"] = rv5
    feats_daily["rv_20d"] = rv20
    feats_daily["rv_ratio_5d_20d"] = rv5 / rv20.replace(0, np.nan)

    # CRITICAL: shift(1) so bar_date D reads D-1's daily features
    feats_daily_shifted = feats_daily.shift(1)
    # Also need raw daily ATR at d-1 for bar-level normalization
    atr14_d1 = atr14.shift(1)

    # Attach daily features by date
    feature_cols = list(feats_daily_shifted.columns)
    lookup: dict = {d: feats_daily_shifted.loc[d].values
                    for d in feats_daily_shifted.index}
    atr_lookup: dict = {d: float(v) if pd.notna(v) else np.nan
                         for d, v in atr14_d1.items()}
    nan_row = np.full(len(feature_cols), np.nan, dtype=np.float64)
    bar_date_arr = pd.to_datetime(df["bar_date"]).dt.date.values
    attached = np.array(
        [lookup.get(d, nan_row) for d in bar_date_arr],
        dtype=np.float64,
    )

    out = df.reset_index(drop=True).copy()
    for i, c in enumerate(feature_cols):
        out[c] = attached[:, i].astype(np.float32)

    # gap_open_pct_d : open of first bar of session D / close of d-1 - 1.
    # In strat_features, each bar has its own open; the FIRST bar of the
    # session has the open that opened the day. We groupby bar_date and take
    # the first bar's open. That value is broadcast back to every bar in
    # the same session.
    df_sorted = out.sort_values(["bar_date", "ts"]).reset_index(drop=False)
    first_open = df_sorted.groupby("bar_date")["open"].transform("first")
    prev_close_lookup: dict = {}
    daily_close = daily["close"]
    daily_close_arr = daily_close.values
    daily_dates = list(daily_close.index)
    # d_to_idx for fast prev-date lookup
    d_to_idx = {d: i for i, d in enumerate(daily_dates)}
    for d in df_sorted["bar_date"].unique():
        idx = d_to_idx.get(d)
        if idx is None or idx == 0:
            prev_close_lookup[d] = np.nan
        else:
            prev_close_lookup[d] = float(daily_close_arr[idx - 1])
    prev_close_arr = df_sorted["bar_date"].map(prev_close_lookup).values
    gap_pct = (first_open.values - prev_close_arr) / prev_close_arr
    # Reorder back to original index
    df_sorted["gap_open_pct_d"] = gap_pct
    df_sorted = df_sorted.sort_values("index").set_index("index")
    out["gap_open_pct_d"] = df_sorted["gap_open_pct_d"].values.astype(np.float32)

    # true_range_vs_atr_d1: bar's (high-low) / d-1's daily ATR
    atr_d1_per_bar = np.array(
        [atr_lookup.get(d, np.nan) for d in bar_date_arr], dtype=np.float64,
    )
    bar_range = (out["high"] - out["low"]).values
    with np.errstate(divide="ignore", invalid="ignore"):
        tr_vs_atr = bar_range / atr_d1_per_bar
    out["true_range_vs_atr_d1"] = tr_vs_atr.astype(np.float32)

    out = out.replace([np.inf, -np.inf], np.nan)
    n_added = len(feature_cols) + 2
    log.info("Family 4 done: added %d feature columns", n_added)
    return out
