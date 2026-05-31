#!/usr/bin/env python3
"""Strat Engine — Multi-Timeframe Strat-Features Dataset Builder.

This is the source-of-truth data builder for the Strat Directionality
Engine. Copied 2026-05-26 from the original p7_build_multi_tf_features
with forward-compat fixes folded in: ORB, historical levels, order
blocks, and current-period running levels are now emitted natively so
the strat_features_levels_{tf} companion table eventually becomes
redundant.

Builds the per-(ticker, TF) bar-level feature tables (`strat_features_1m`,
`_5m`, `_15m`, `_30m`, `_60m`). Each row = one bar at that TF:

  - OHLCV
  - strat classification (1/2U/2D/3) + prev_strat + combo + flags
  - 30+ indicators (RSI, EMA, MACD, BB, ATR, VWAP, RVOL, OBV, Stoch)
  - ORB (5/15/30 min windows) — NEW vs original p7 builder
  - Historical levels (prev day/week/month/quarter/year HLOC + flags) — NEW
  - Current-period running levels (today/WTD/MTD/QTD/YTD HLO) — NEW
  - Order blocks (institutional consolidation zones) — NEW
  - forward-return targets at 5/15/30/60 bars
  - VIX + GEX + VEX context + 9-state dealer_regime (GEX × VEX terciles)

VIX same-day-leak fix from 2026-05-25 is preserved (vix_close uses
prior-day VIX, not same-day).

Reuses:
  - lib.data_loader.DataLoader.aggregate_to_timeframe — OHLCV rollup
  - lib.strat.StratClassifier.detect_combos — strat classification
  - lib.indicators.add_all_indicators — core indicator suite
  - lib.indicators.calculate_historical_levels — prev day/week/month/...
  - lib.indicators.calculate_current_period_levels — today/WTD/MTD/...
  - lib.indicators.calculate_order_blocks — institutional zones
  - lib.gamma.total_vex — vega exposure per chain
  - gcp.database.bulk_copy_upsert — ON CONFLICT DO UPDATE

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
from datetime import date as _date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import execute_sql, get_engine, upsert_dataframe, bulk_copy_upsert
from lib.data_loader import DataLoader
from lib.strat import StratClassifier
from lib.indicators import (
    add_all_indicators,
    calculate_all_orb,
    calculate_historical_levels,
    calculate_current_period_levels,
    calculate_order_blocks,
    calculate_atr,
)
from lib.gamma import total_vex
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


TICKERS_DEFAULT = ["SPY", "IWM", "QQQ"]
TF_LIST = [("1m", None), ("5m", "5m"), ("15m", "15m"), ("30m", "30m"),
           ("60m", "1h"), ("4h", "4h")]
# (label_for_table, aggregate_to_timeframe_arg). '1m' = no aggregation.
# 4h added 2026-05-26: lib.data_loader.RESAMPLE_RULES supports "4h".


# DDL for strat_features_4h — kept here (NOT in gcp/queries/p7_schema.sql)
# because 4h was added LATER than the other TFs. Applied just-in-time before
# upsert if a 4h run is requested. Schema mirrors strat_features_60m exactly.
FOUR_H_DDL = """
CREATE TABLE IF NOT EXISTS strat_features_4h (
    ticker          VARCHAR(16) NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    tf              VARCHAR(8) NOT NULL DEFAULT '4h',
    bar_date        DATE NOT NULL,
    open            DOUBLE PRECISION,
    high            DOUBLE PRECISION,
    low             DOUBLE PRECISION,
    close           DOUBLE PRECISION,
    volume          BIGINT,
    strat_candle    VARCHAR(8),
    prev_strat_candle VARCHAR(8),
    strat_combo     VARCHAR(64),
    is_continuation BOOLEAN,
    is_reversal     BOOLEAN,
    is_inside       BOOLEAN,
    strat_setup     BOOLEAN,
    consecutive_1s  SMALLINT,
    trigger_high    DOUBLE PRECISION,
    trigger_low     DOUBLE PRECISION,
    ema_9 DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50 DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9 DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14 DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper DOUBLE PRECISION, bb_lower DOUBLE PRECISION, bb_width DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv DOUBLE PRECISION, rvol DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap DOUBLE PRECISION,
    price_vs_vwap DOUBLE PRECISION, price_vs_ema9 DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up INTEGER, consecutive_down INTEGER,
    realized_vol_short DOUBLE PRECISION, mins_since_open DOUBLE PRECISION,
    price_vs_ema9_atr DOUBLE PRECISION, price_vs_ema20_atr DOUBLE PRECISION,
    price_vs_vwap_atr DOUBLE PRECISION, ema_spread_atr DOUBLE PRECISION,
    ema9_slope DOUBLE PRECISION, bb_squeeze DOUBLE PRECISION, rsi_divergence DOUBLE PRECISION,
    intraday_return DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime VARCHAR(32), gamma_regime VARCHAR(32),
    flip_price DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION, distance_to_gate_pct DOUBLE PRECISION,
    computed_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_4h_date ON strat_features_4h (bar_date);
CREATE INDEX IF NOT EXISTS ix_strat_features_4h_combo ON strat_features_4h (ticker, strat_combo);
"""

INTRADAY_TABLE = {
    "SPY": "market_data_intraday_spy",
    "IWM": "market_data_intraday_iwm",
    "QQQ": "market_data_intraday_qqq",
}

# VIX terciles from P1 baselines (10yr ^VIX distribution)
VIX_P33, VIX_P67 = 14.65, 19.40


# ──────────────────────── Data loaders ────────────────────────


def _max_cached_date(engine, ticker: str, tf_label: str) -> Optional[_date]:
    """Return max(bar_date) currently in strat_features_<tf> for this ticker,
    or None if table is empty for this ticker. Drives incremental backfill —
    only featurize+upsert dates strictly after this."""
    table = f"strat_features_{tf_label}"
    sql = text(f"SELECT max(bar_date) FROM {table} WHERE ticker = :t")
    with engine.connect() as conn:
        row = conn.execute(sql, {"t": ticker}).fetchone()
    return row[0] if row and row[0] else None


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
    """Compute total_vex per (ticker, date), using daily_vex cache to skip
    already-computed dates. ~7 min on first run per ticker → near-zero on
    subsequent runs.
    """
    # Load already-cached dates
    cache_sql = text("""
        SELECT snapshot_date, total_vex
        FROM daily_vex
        WHERE ticker = :ticker
    """)
    with engine.connect() as conn:
        cached = pd.read_sql(cache_sql, conn, params={"ticker": ticker})
    if not cached.empty:
        cached["snapshot_date"] = pd.to_datetime(cached["snapshot_date"]).dt.date
        cached_dates = set(cached["snapshot_date"].tolist())
        log.info("%s: %d dates already in daily_vex cache", ticker, len(cached_dates))
    else:
        cached_dates = set()
        log.info("%s: daily_vex cache empty — computing fresh", ticker)

    target_dates = set(spot_lookup.keys())
    missing_dates = target_dates - cached_dates
    log.info("%s: %d dates need VEX compute (%d cached)",
             ticker, len(missing_dates), len(cached_dates))

    if not missing_dates:
        return cached.set_index("snapshot_date")

    new_rows: list[dict] = []
    log.info("%s: computing daily VEX by quarter (missing dates only)...", ticker)
    for year in range(2015, 2027):
        for q in (1, 2, 3, 4):
            t0 = time.time()
            chain = _load_chain_quarter(engine, ticker, year, q)
            if chain.empty:
                continue
            n_done = 0
            for snap_date, day_chain in chain.groupby("snapshot_date"):
                if snap_date not in missing_dates:
                    continue
                spot = spot_lookup.get(snap_date)
                if spot is None or not spot:
                    continue
                opts = day_chain.to_dict("records")
                vex = total_vex(opts, float(spot))
                new_rows.append({
                    "ticker": ticker,
                    "snapshot_date": snap_date,
                    "total_vex": float(vex),
                    "spot_estimate": float(spot),
                })
                n_done += 1
            if n_done:
                log.info("  %s %dQ%d: %d new dates, %.1fs",
                         ticker, year, q, n_done, time.time() - t0)

    # Persist new rows to cache
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        bulk_copy_upsert(
            new_df, "daily_vex",
            conflict_cols=["ticker", "snapshot_date"],
            update_cols=["total_vex", "spot_estimate"],
        )
        log.info("%s: cached %d new VEX rows to daily_vex", ticker, len(new_df))

    # Combine cache + new for return
    combined = pd.concat([
        cached if not cached.empty else pd.DataFrame(columns=["snapshot_date", "total_vex"]),
        pd.DataFrame([{"snapshot_date": r["snapshot_date"], "total_vex": r["total_vex"]}
                       for r in new_rows]) if new_rows else pd.DataFrame(columns=["snapshot_date", "total_vex"]),
    ], ignore_index=True)
    combined = combined.drop_duplicates("snapshot_date").set_index("snapshot_date")
    return combined


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
    #   Price_vs_VWAP, Daily_Range/Pct, ORB_5m/15m/30m_* (NEW — picked up
    #   automatically by add_all_indicators when Time column is present)

    # Historical levels (prev day/week/month/quarter/year HLOC + flags). NEW
    # 2026-05-26: not invoked by add_all_indicators; folded in here so the
    # source table has them natively and the companion enrichment table
    # eventually becomes redundant.
    times = df_tf["Time"] if "Time" in df_tf.columns else pd.Series(df_tf.index)
    hist_df = calculate_historical_levels(
        times, df_tf["High"], df_tf["Low"], df_tf["Open"], df_tf["Close"],
    )
    hist_df.index = df_tf.index

    # Current-period running levels (today/WTD/MTD/QTD/YTD HLO + position). NEW.
    cur_df = calculate_current_period_levels(
        times, df_tf["High"], df_tf["Low"], df_tf["Open"], df_tf["Close"],
    )
    cur_df.index = df_tf.index

    # Order blocks (institutional consolidation zones). NEW.
    atr14 = ind_df["ATR14"] if "ATR14" in ind_df.columns else calculate_atr(
        df_tf["High"], df_tf["Low"], df_tf["Close"], period=14)
    ob_df = calculate_order_blocks(
        df_tf["High"], df_tf["Low"], df_tf["Close"], atr=atr14)
    ob_df.index = df_tf.index
    ob_df = ob_df.rename(columns={c: (c if c.startswith("OB_") else f"OB_{c}")
                                    for c in ob_df.columns})

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
    # Promoted 2026-05-31 volatility/momentum features — persisted so research
    # SQL / training can query them historically (previously computed-then-dropped).
    out["realized_vol_short"] = _safe("Realized_Vol_Short")
    out["mins_since_open"] = _safe("Mins_Since_Open")
    out["price_vs_ema9_atr"] = _safe("Price_vs_EMA9_ATR")
    out["price_vs_ema20_atr"] = _safe("Price_vs_EMA20_ATR")
    out["price_vs_vwap_atr"] = _safe("Price_vs_VWAP_ATR")
    out["ema_spread_atr"] = _safe("EMA_Spread_ATR")
    out["ema9_slope"] = _safe("EMA9_Slope")
    out["bb_squeeze"] = _safe("BB_Squeeze")
    out["rsi_divergence"] = _safe("RSI_Divergence")
    out["intraday_return"] = (closes - df_tf["Open"]) / df_tf["Open"] * 100
    out["high_low_spread_pct"] = (df_tf["High"] - df_tf["Low"]) / closes * 100

    # Forward returns
    for nb in (5, 15, 30, 60):
        fwd = closes.shift(-nb)
        out[f"fwd_close_{nb}bars"] = fwd
        out[f"fwd_ret_{nb}bars_bps"] = (fwd - closes) / closes * 10000

    # NEW 2026-05-26 — TODO: when strat_features_{tf} schema is migrated
    # to include ORB / historical / current / order-block cols, uncomment
    # the loop below to emit them natively. Until then, those columns
    # remain in the strat_features_levels_{tf} companion table populated
    # by gcp/research/strat_engine/strat_enrich_levels.py.
    #
    # The computations above (ind_df ORB_*, hist_df, cur_df, ob_df) are
    # left in place so the migration is a one-line change.
    #
    # def _snake_lower(c): return c.replace("__", "_").lower()
    # for src in (hist_df, cur_df, ob_df):
    #     for col in src.columns:
    #         out[_snake_lower(col)] = src[col].values
    # for col in ind_df.columns:
    #     if col.startswith("ORB_"):
    #         out[_snake_lower(col)] = ind_df[col].values

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
    # NO-LEAK FIX 2026-05-25: use PRIOR trading day's VIX close. The previous
    # implementation used same-day close, which is end-of-day data and would
    # be unknown to any intraday bar (e.g. a 10am bar wouldn't yet know that
    # day's VIX close). Audit on 2026-05-25 confirmed s_vix at 14:30 ET equaled
    # the daily close — a textbook lookahead leak.
    prior_vix = vix_df.sort_index().shift(1)
    out["vix_close"] = bd.map(prior_vix["vix_close"].to_dict())
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

    # Incremental: query per-TF max cached date. If all TFs are up to date,
    # skip ticker. Otherwise load 1m bars from (min cached date - 30 day
    # lookback for indicator warmup) → only featurize+upsert NEW dates.
    max_dates_per_tf = {tf_label: _max_cached_date(engine, ticker, tf_label)
                        for tf_label, _ in TF_LIST}
    log.info("%s: max cached bar_date per TF: %s", ticker, max_dates_per_tf)

    cached_dates = [d for d in max_dates_per_tf.values() if d is not None]
    if cached_dates and len(cached_dates) == len(TF_LIST):
        # All TFs have some cache. Load bars from (earliest_cached - 30 days)
        # to ensure indicator warmup. Earlier cached dates won't be reupserted
        # because we filter post-featurize on bar_date > max_cached.
        earliest_cached = min(cached_dates)
        # 30 trading-day lookback ≈ 45 calendar days; 60m × 200 bar warmup = ~30 trading days
        lookback_start = earliest_cached - timedelta(days=45)
        bar_load_start = max(
            pd.Timestamp(start_date).date(),
            lookback_start,
        ).strftime("%Y-%m-%d")
        log.info("%s: INCREMENTAL — loading 1m bars from %s (earliest cached=%s, with 45d lookback)",
                 ticker, bar_load_start, earliest_cached)
    else:
        bar_load_start = start_date
        log.info("%s: FULL BACKFILL — loading from %s (some TFs have empty cache)",
                 ticker, bar_load_start)

    bars_1m = _load_1m_bars(engine, ticker, bar_load_start)
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

        # Incremental skip: drop rows whose bar_date is already in cache.
        # Keeps lookback bars in `feat` (needed for indicator warmup of
        # newer rows) but doesn't re-upsert them.
        max_cached = max_dates_per_tf.get(tf_label)
        if max_cached is not None:
            before = len(feat)
            feat = feat[feat["bar_date"] > max_cached]
            log.info("%s %s: skipped %d already-cached rows (max_cached=%s); %d new to upsert",
                     ticker, tf_label, before - len(feat), max_cached, len(feat))
            if feat.empty:
                log.info("%s %s: nothing new to upsert", ticker, tf_label)
                results["tfs"][tf_label] = 0
                continue

        n = len(feat)
        # Use ON CONFLICT DO UPDATE so re-runs converge. bulk_copy_upsert
        # uses psycopg2 COPY FROM STDIN → 10-30× faster than pg8000 binds.
        # Falls back to upsert_dataframe if psycopg2 unavailable.
        update_cols = [c for c in feat.columns
                       if c not in ("ticker", "ts", "computed_at")]
        bulk_copy_upsert(feat, table,
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

    # 4h DDL applied just-in-time (the other TFs' tables live in p7_schema.sql;
    # 4h was added later and lives here for now). Idempotent.
    if any(lbl == "4h" for lbl, _ in TF_LIST):
        execute_sql(FOUR_H_DDL)
        log.info("ensured schema: strat_features_4h")

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
