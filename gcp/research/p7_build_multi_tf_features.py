#!/usr/bin/env python3
"""Phase 7 — Multi-Timeframe Strat-Sequence Dataset Builder (Cloud Run Job).

Builds the per-(ticker, TF) bar-level feature tables (`strat_features_1m`,
`_5m`, `_15m`, `_30m`, `_60m`) that the rest of the audit refactor uses
as its foundation. Each row = one bar at that TF, fully featurized:

  - OHLCV
  - strat classification (1/2U/2D/3) + prev_strat + combo + flags
  - 30+ indicators (RSI, EMA, MACD, BB, ATR, VWAP, RVOL, OBV, Stoch)
  - forward-return targets at 5/15/30/60 bars
  - VIX + GEX + VEX context + 9-state dealer_regime (GEX × VEX terciles)

See docs/research/2026-05-24/RESEARCH_PLAN_P7.md (TODO write) +
/root/.claude/plans/no-i-think-it-s-cached-sun.md (approved plan).

Reuses (no reinvention):
  - lib.data_loader.DataLoader.aggregate_to_timeframe — OHLCV rollup
  - lib.strat.StratClassifier.detect_combos — strat classification
  - lib.indicators.add_all_indicators — full indicator suite
  - lib.gamma.total_vex — vega exposure per chain
  - gcp.database.upsert_dataframe — ON CONFLICT DO UPDATE
  - gcp/research/p2_build_gamma_levels.py — direct structural template

Rule 0 capacity:
  Volume:   3 tickers × ~1.04M 1-min RTH bars = ~3.12M rows in _1m table
  Velocity: per ticker 1m pull ~30s; 5 TF aggregations + classifications +
            indicators ~60s; quarterly VEX chain pulls ~7 min total; 5
            batched upserts per ticker
  Wall:     ~15 min/ticker × 3 = ~30-45 min total
  Timeout:  5400s (90 min) = 2x estimate
  Memory:   ~400 MB peak DataFrame; 16 GiB safe
  Retries:  0 (idempotent ON CONFLICT)
"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from datetime import date as _date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import execute_sql, get_engine, upsert_dataframe
from lib.data_loader import DataLoader
from lib.strat import StratClassifier
from lib.indicators import add_all_indicators
from lib.gamma import total_vex
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


TICKERS_DEFAULT = ["SPY", "IWM", "QQQ"]
TF_LIST = [("1m", None), ("5m", "5m"), ("15m", "15m"), ("30m", "30m"), ("60m", "1h")]
# (label_for_table, aggregate_to_timeframe_arg). '1m' = no aggregation.

INTRADAY_TABLE = {
    "SPY": "market_data_intraday_spy",
    "IWM": "market_data_intraday_iwm",
    "QQQ": "market_data_intraday_qqq",
}

# VIX terciles from P1 baselines (10yr ^VIX distribution)
VIX_P33, VIX_P67 = 14.65, 19.40


# ──────────────────────── Data loaders ────────────────────────


def _load_1m_bars(engine, ticker: str, start_date: str) -> pd.DataFrame:
    """Pull 1-min RTH bars for one ticker."""
    table = INTRADAY_TABLE[ticker]
    sql = text(f"""
        SELECT ts, open, high, low, close, volume
        FROM {table}
        WHERE interval = '1min'
          AND ts >= :start_ts
          AND (ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:59'
        ORDER BY ts
    """)
    start_ts = pd.Timestamp(start_date, tz="UTC")
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start_ts": start_ts})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts")
    return df


def _load_vix_per_date(engine) -> pd.DataFrame:
    """Load ^VIX daily closes — returned indexed by date."""
    sql = text("""
        SELECT date, close AS vix_close
        FROM market_data_daily
        WHERE ticker = '^VIX'
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("date")


def _load_gamma_levels(engine, ticker: str) -> pd.DataFrame:
    """Load gamma_levels_eod per-date for the ticker. Each date has multiple
    level rows; pivot to one row per date with total_gex, flip_price, regime,
    and pre-computed min distances to king / gate."""
    sql = text("""
        SELECT snapshot_date, level_kind, level_strike, gex, score, regime,
               flip_price, total_gex, spot_estimate
        FROM gamma_levels_eod
        WHERE ticker = :ticker
    """)
    with engine.connect() as conn:
        raw = pd.read_sql(sql, conn, params={"ticker": ticker})
    raw["snapshot_date"] = pd.to_datetime(raw["snapshot_date"]).dt.date
    rows: list[dict] = []
    for d, g in raw.groupby("snapshot_date"):
        first = g.iloc[0]
        spot = first["spot_estimate"]
        kings = g[g["level_kind"] == "king"]
        gates = g[g["level_kind"] == "gate"]
        rows.append({
            "snapshot_date": d,
            "total_gex": float(first["total_gex"] or 0.0),
            "flip_price": float(first["flip_price"]) if pd.notna(first["flip_price"]) else None,
            "regime": str(first["regime"] or "unknown"),
            "spot": float(spot) if pd.notna(spot) else None,
            "min_king_strike": float(kings["level_strike"].iloc[0]) if not kings.empty else None,
            "min_gate_strike": float(gates["level_strike"].iloc[0]) if not gates.empty else None,
        })
    return pd.DataFrame(rows).set_index("snapshot_date")


def _load_chain_quarter(engine, ticker: str, year: int, q: int) -> pd.DataFrame:
    """Per-quarter chain pull (same pattern as p2_build_gamma_levels for VEX)."""
    q_start = pd.Timestamp(year, (q - 1) * 3 + 1, 1).date()
    q_end_dt = pd.Timestamp(year, (q - 1) * 3 + 1, 1) + pd.offsets.QuarterEnd()
    q_end = q_end_dt.date()
    sql = text("""
        SELECT snapshot_date, option_type, strike, gamma, vega, open_interest,
               bid, ask, mark, last_price, underlying_price
        FROM etf_options_snapshots
        WHERE ticker = :ticker
          AND data_source = 'alphavantage'
          AND market_session = 'EOD'
          AND snapshot_date BETWEEN :start AND :end
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"ticker": ticker, "start": q_start, "end": q_end})
    return df


def _compute_daily_vex(engine, ticker: str, spot_lookup: dict) -> pd.DataFrame:
    """Compute total_vex per (ticker, date) by iterating chain quarter-by-quarter.

    spot_lookup maps date -> spot price for the dealer-vanna formula in
    lib.gamma.total_vex. We pull spot from gamma_levels_eod (already in
    spot_lookup) — if missing for a date, skip that date.
    """
    rows: list[dict] = []
    log.info("%s: computing daily VEX by quarter...", ticker)
    for year in range(2015, 2027):
        for q in (1, 2, 3, 4):
            t0 = time.time()
            chain = _load_chain_quarter(engine, ticker, year, q)
            if chain.empty:
                continue
            # Map column names to what total_vex expects (it reads .get("vega"), .get("open_interest"))
            for snap_date, day_chain in chain.groupby("snapshot_date"):
                spot = spot_lookup.get(snap_date)
                if spot is None or not spot:
                    continue
                # total_vex expects list of dicts with 'vega', 'open_interest'
                opts = day_chain.to_dict("records")
                vex = total_vex(opts, float(spot))
                rows.append({"snapshot_date": snap_date, "total_vex": float(vex)})
            log.info("  %s %dQ%d: %d dates, %.1fs", ticker, year, q,
                     chain["snapshot_date"].nunique(), time.time() - t0)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
    return df.drop_duplicates("snapshot_date").set_index("snapshot_date")


# ──────────────────── TF aggregation + featurization ────────────────────


def _capitalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """lib helpers expect 'Open', 'High', 'Low', 'Close', 'Volume'."""
    out = df.copy()
    rename_map = {}
    for c in df.columns:
        if c.lower() in ("open", "high", "low", "close", "volume"):
            rename_map[c] = c.capitalize()
    return out.rename(columns=rename_map)


def _featurize_tf(df_1m: pd.DataFrame, tf_label: str, tf_arg: Optional[str]) -> pd.DataFrame:
    """Aggregate to TF, classify strat, add indicators, derive flags + fwd returns.

    Returns DataFrame with columns matching the strat_features_<tf> schema
    (lowercase, ready to upsert), indexed by ts. The caller adds context columns.
    """
    df_cap = _capitalize_ohlcv(df_1m)
    df_cap["Time"] = df_cap.index  # required by add_all_indicators for VWAP

    if tf_arg is None:
        df_tf = df_cap.copy()
    else:
        loader = DataLoader()
        df_tf = loader.aggregate_to_timeframe(df_cap, tf_arg)
        df_tf["Time"] = df_tf.index  # re-add Time after aggregation

    # Strat classification + combo detection
    classifier = StratClassifier()
    strat_df = classifier.detect_combos(df_tf)
    # strat_candle / strat_combo / strat_setup / trigger_high / trigger_low

    # prev_strat_candle = shift(1) of strat_candle
    strat_df["prev_strat_candle"] = strat_df["strat_candle"].shift(1)
    # is_continuation / is_reversal / is_inside derived from strat_combo regex
    cmb = strat_df["strat_combo"].fillna("none")
    strat_df["is_continuation"] = cmb.str.contains("_continuation", na=False)
    strat_df["is_reversal"] = cmb.str.contains("_reversal", na=False)
    strat_df["is_inside"] = cmb.str.contains("inside_compression", na=False) | (strat_df["strat_candle"] == "1")
    if "consecutive_1s" not in strat_df.columns:
        # detect_combos may not always emit it; recompute defensively
        is_one = (strat_df["strat_candle"] == "1").astype(int)
        strat_df["consecutive_1s"] = is_one.groupby((is_one == 0).cumsum()).cumsum().astype("int16")

    # Indicators
    ind_df = add_all_indicators(df_tf, close_col="Close")
    # ind_df has columns: ATR14, RSI14, RSI9, EMA9, EMA20, EMA50, SMA5/10/20/50/200,
    #   VWAP, RVOL, OBV, StochRSI_K/D, BB_Upper/Lower/Middle/Width/Pct,
    #   MACD, MACD_Signal, MACD_Histogram, Consecutive_Up/Down, Price_vs_EMA9/20,
    #   Price_vs_VWAP, Daily_Range/Pct

    # Forward returns at 5/15/30/60 bars
    closes = df_tf["Close"].astype(float)
    out = pd.DataFrame(index=df_tf.index)
    out["open"] = df_tf["Open"].astype(float)
    out["high"] = df_tf["High"].astype(float)
    out["low"] = df_tf["Low"].astype(float)
    out["close"] = closes
    out["volume"] = df_tf["Volume"].astype("int64")
    out["tf"] = tf_label
    out["bar_date"] = df_tf.index.tz_convert("America/New_York").date

    # Strat columns
    out["strat_candle"] = strat_df["strat_candle"]
    out["prev_strat_candle"] = strat_df["prev_strat_candle"]
    out["strat_combo"] = strat_df["strat_combo"]
    out["is_continuation"] = strat_df["is_continuation"]
    out["is_reversal"] = strat_df["is_reversal"]
    out["is_inside"] = strat_df["is_inside"]
    out["strat_setup"] = strat_df["strat_setup"]
    out["consecutive_1s"] = strat_df["consecutive_1s"].astype("Int16")
    out["trigger_high"] = strat_df.get("trigger_high")
    out["trigger_low"] = strat_df.get("trigger_low")

    # Indicators (capitalize-to-lowercase mapping)
    def _safe(col: str):
        return ind_df[col] if col in ind_df.columns else pd.Series(index=ind_df.index, dtype=float)

    out["ema_9"] = _safe("EMA9")
    out["ema_20"] = _safe("EMA20")
    out["ema_50"] = _safe("EMA50")
    out["ema_200"] = _safe("EMA200")  # may not exist if 200 not in periods
    out["sma_50"] = _safe("SMA50")
    out["sma_200"] = _safe("SMA200")
    out["rsi_9"] = _safe("RSI9")
    out["rsi_14"] = _safe("RSI14")
    out["stoch_rsi_k"] = _safe("StochRSI_K")
    out["stoch_rsi_d"] = _safe("StochRSI_D")
    out["macd"] = _safe("MACD")
    out["macd_signal"] = _safe("MACD_Signal")
    out["macd_histogram"] = _safe("MACD_Histogram")
    out["atr_14"] = _safe("ATR14")
    out["atr_20"] = _safe("ATR20")
    out["bb_upper"] = _safe("BB_Upper")
    out["bb_lower"] = _safe("BB_Lower")
    out["bb_width"] = _safe("BB_Width")
    out["bb_pct"] = _safe("BB_Pct")
    out["obv"] = _safe("OBV")
    out["rvol"] = _safe("RVOL")
    out["rvol_10"] = _safe("RVol_Recent_20")  # closest match — repurposed
    out["vwap"] = _safe("VWAP")
    out["price_vs_vwap"] = _safe("Price_vs_VWAP")
    out["price_vs_ema9"] = _safe("Price_vs_EMA9")
    out["price_vs_ema20"] = _safe("Price_vs_EMA20")
    out["consecutive_up"] = _safe("Consecutive_Up").astype("Int32")
    out["consecutive_down"] = _safe("Consecutive_Down").astype("Int32")
    out["intraday_return"] = (closes - df_tf["Open"]) / df_tf["Open"] * 100
    out["high_low_spread_pct"] = (df_tf["High"] - df_tf["Low"]) / closes * 100

    # Forward returns
    for nb in (5, 15, 30, 60):
        fwd = closes.shift(-nb)
        out[f"fwd_close_{nb}bars"] = fwd
        out[f"fwd_ret_{nb}bars_bps"] = (fwd - closes) / closes * 10000

    return out


# ──────────────────── Context joining ────────────────────


def _add_context(out: pd.DataFrame, ticker: str, vix_df: pd.DataFrame,
                 gamma_df: pd.DataFrame, vex_df: pd.DataFrame,
                 gex_terciles: tuple, vex_terciles: tuple) -> pd.DataFrame:
    """Add VIX, GEX, VEX, dealer_regime, gamma_regime, distance columns.

    Levels are joined on the PRIOR business day (no leak — matches production's
    _latest_gamma_for_ticker_pure semantics).
    """
    # PRIOR-day join: shift gamma_df / vex_df forward by 1 trading day relative
    # to each row. Simpler: build a lookup of (date -> prior_trading_date_levels)
    # by sorting and shifting.
    gamma_sorted = gamma_df.sort_index()
    vex_sorted = vex_df.sort_index() if not vex_df.empty else pd.DataFrame()
    # Build a "prior-business-day's levels" map. For each date d in gamma_sorted.index,
    # the LATER d uses d's levels (so we shift by 1).
    prior_gamma = gamma_sorted.shift(1).reset_index().rename(
        columns={"snapshot_date": "prior_date"})
    prior_gamma["effective_date"] = gamma_sorted.index
    prior_gamma = prior_gamma.dropna(subset=["effective_date"]).set_index("effective_date")
    # Same for VEX
    if not vex_sorted.empty:
        prior_vex = vex_sorted.shift(1).reset_index().rename(
            columns={"snapshot_date": "prior_vex_date"})
        prior_vex["effective_date"] = vex_sorted.index
        prior_vex = prior_vex.dropna(subset=["effective_date"]).set_index("effective_date")
    else:
        prior_vex = pd.DataFrame()

    bd = out["bar_date"]
    out["vix_close"] = bd.map(vix_df["vix_close"].to_dict())
    # VIX tercile
    out["vix_tercile"] = pd.cut(out["vix_close"], bins=[-np.inf, VIX_P33, VIX_P67, np.inf],
                                 labels=["LOW", "MID", "HIGH"]).astype(object)

    # Gamma context — join via prior-date lookup
    out["total_gex"] = bd.map(prior_gamma["total_gex"].to_dict())
    out["flip_price"] = bd.map(prior_gamma["flip_price"].to_dict())
    out["gamma_regime"] = bd.map(prior_gamma["regime"].to_dict()).fillna("unknown")
    out["distance_to_king_pct"] = (out["close"] - bd.map(prior_gamma["min_king_strike"].to_dict())) \
        / out["close"] * 100
    out["distance_to_gate_pct"] = (out["close"] - bd.map(prior_gamma["min_gate_strike"].to_dict())) \
        / out["close"] * 100

    # VEX context
    if not prior_vex.empty:
        out["total_vex"] = bd.map(prior_vex["total_vex"].to_dict())
    else:
        out["total_vex"] = np.nan

    # GEX tercile (per-ticker 10yr distribution)
    out["gex_tercile"] = pd.cut(out["total_gex"], bins=[-np.inf, gex_terciles[0],
                                                          gex_terciles[1], np.inf],
                                 labels=["LOW", "MID", "HIGH"]).astype(object)
    # VEX tercile
    out["vex_tercile"] = pd.cut(out["total_vex"], bins=[-np.inf, vex_terciles[0],
                                                          vex_terciles[1], np.inf],
                                 labels=["LOW", "MID", "HIGH"]).astype(object)
    # dealer_regime = "GEX_X_VEX_Y" 9-cell label
    out["dealer_regime"] = "GEX_" + out["gex_tercile"].astype(str) + "_VEX_" + out["vex_tercile"].astype(str)
    return out


def _compute_terciles(s: pd.Series) -> tuple[float, float]:
    s = s.dropna()
    if len(s) < 30:
        return (float("nan"), float("nan"))
    return (float(s.quantile(0.333)), float(s.quantile(0.667)))


# ──────────────────── Main per-ticker driver ────────────────────


def _process_ticker(engine, ticker: str, start_date: str, vix_df: pd.DataFrame) -> dict:
    log.info("=== %s: loading 1m bars and gamma context ===", ticker)
    t0 = time.time()
    bars_1m = _load_1m_bars(engine, ticker, start_date)
    log.info("%s: loaded %d 1m RTH bars", ticker, len(bars_1m))
    if bars_1m.empty:
        return {"ticker": ticker, "skipped": True}

    gamma_df = _load_gamma_levels(engine, ticker)
    log.info("%s: loaded gamma_levels_eod for %d dates", ticker, len(gamma_df))

    # Compute spot lookup for VEX
    spot_lookup = gamma_df["spot"].dropna().to_dict()
    vex_df = _compute_daily_vex(engine, ticker, spot_lookup)
    log.info("%s: computed VEX for %d dates", ticker, len(vex_df))

    # Terciles for GEX, VEX (per-ticker, full distribution)
    gex_terciles = _compute_terciles(gamma_df["total_gex"])
    vex_terciles = _compute_terciles(vex_df["total_vex"]) if not vex_df.empty else (float("nan"), float("nan"))
    log.info("%s: GEX terciles (p33, p67) = %s; VEX terciles = %s",
             ticker, gex_terciles, vex_terciles)

    results = {"ticker": ticker, "tfs": {}}
    for tf_label, tf_arg in TF_LIST:
        t_tf = time.time()
        log.info("%s: featurizing %s...", ticker, tf_label)
        feat = _featurize_tf(bars_1m, tf_label, tf_arg)
        feat = _add_context(feat, ticker, vix_df, gamma_df, vex_df, gex_terciles, vex_terciles)
        feat["ticker"] = ticker
        feat = feat.reset_index().rename(columns={"index": "ts"})
        # Ensure ts column is the index name from before
        if "ts" not in feat.columns and "Time" in feat.columns:
            feat["ts"] = feat["Time"]

        table = f"strat_features_{tf_label}"
        n = len(feat)
        # Use ON CONFLICT DO UPDATE so re-runs converge
        update_cols = [c for c in feat.columns
                       if c not in ("ticker", "ts", "computed_at")]
        upsert_dataframe(feat, table,
                         conflict_cols=["ticker", "ts"],
                         update_cols=update_cols)
        log.info("%s %s: upserted %d rows (%.1fs)", ticker, tf_label, n, time.time() - t_tf)
        results["tfs"][tf_label] = n

    log.info("=== %s: done in %.1fs ===", ticker, time.time() - t0)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", default=",".join(TICKERS_DEFAULT))
    parser.add_argument("--start-date", default="2016-01-01")
    parser.add_argument("--tf-only", default=None,
                        help="If set, only build this single TF (e.g. '5m'). Useful for testing.")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    log.info("Phase 7: building strat_features tables for %s since %s",
             tickers, args.start_date)

    engine = get_engine()
    vix_df = _load_vix_per_date(engine)
    log.info("VIX loaded: %d dates", len(vix_df))

    if args.tf_only:
        # Filter the TF_LIST globally for this run
        global TF_LIST
        TF_LIST = [(lbl, arg) for (lbl, arg) in TF_LIST if lbl == args.tf_only]
        log.info("TF filter: only %s", args.tf_only)

    grand = []
    for ticker in tickers:
        try:
            r = _process_ticker(engine, ticker, args.start_date, vix_df)
            grand.append(r)
        except Exception as e:
            log.exception("Ticker %s failed: %s", ticker, e)

    log.info("All done. Per-ticker counts:")
    for r in grand:
        log.info("  %s: %s", r.get("ticker"), r.get("tfs", "SKIPPED"))


if __name__ == "__main__":
    main()
