#!/usr/bin/env python3
"""Phase 7d — Honest P&L backtest of the next-candle classifier signal.

Operating assumptions baked in (per user review 2026-05-25):
  - Direction hit-rate is anti-predictive on the median bar; signal lives
    ONLY in the tails (D10 = top, D1 = bottom by directional_edge).
  - 60% next-candle accuracy does NOT equal trade profitability — a "2U"
    can be a one-tick poke that reverses. We must use a REAL exit model.
  - User's live constraint: 2-3 trades/day max. Cap at 2 highest-conviction
    trades per day.
  - User trades 0DTE options, not the ETF. We backtest the ETF P&L AS the
    floor — if the ETF P&L isn't positive, the options P&L cannot be.
    The script PRINTS an option-fill bridge table at the end so the user
    can see what the underlying-move-vs-bid-ask math implies.

Modes:
  --mode=backtest  Runs on a (ticker, tf) cell that has a saved classifier
                   in gs://.../research/p7b/{ticker}_{tf}/model.pkl.
                   Reports per-trade results + summary stats.

Exit models tested (all in parallel — output a table comparing):
  exitA  TP +25bps / SL -15bps / time-stop 10 bars
  exitB  TP +50bps / SL -25bps / time-stop 20 bars
  exitC  hold N bars, take whatever close (matches classifier's natural
         5-bar forward horizon)

Trade selection:
  - Compute predictions via saved p7b classifier on Jan-May 2026
  - Per UTC trading date: take ≤2 bars with highest |directional_edge|
  - Long if edge > 0, short if edge < 0
  - Entry at NEXT bar's open (no peek)
  - Exit per exit model

Cost model:
  - Round-trip: 10 bps of underlying notional (ETF assumption)
  - Reports gross AND net P&L
  - Bridge table at end: what the same trade would need on 0DTE options
    given typical bid-ask
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

from gcp.database import get_engine
from google.cloud import storage as gcs
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

import lightgbm as lgb


TICKER = "IWM"
TF = "5m"
MODEL_BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
CLASS_ORDER = ["1", "2U", "2D", "3"]
CATEGORICAL = ["strat_candle","prev_strat_candle","strat_combo",
               "vix_tercile","gex_tercile","vex_tercile",
               "dealer_regime","gamma_regime"]

ROUND_TRIP_BPS = 10.0
MAX_TRADES_PER_DAY = 2


def _gcs():
    return gcs.Client()


def _download(blob_path: str) -> bytes | None:
    b = _gcs().bucket(MODEL_BUCKET).blob(blob_path)
    return b.download_as_bytes() if b.exists() else None


def _upload(content: bytes, blob_path: str, ctype="application/octet-stream"):
    b = _gcs().bucket(MODEL_BUCKET).blob(blob_path)
    b.upload_from_string(content, content_type=ctype)
    return f"gs://{MODEL_BUCKET}/{blob_path}"


def load_bars(engine, since=None) -> pd.DataFrame:
    sql = text(f"SELECT * FROM strat_features_{TF} "
               f"WHERE ticker = :t AND strat_candle IS NOT NULL "
               f"AND bar_date >= :s ORDER BY ts")
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": TICKER, "s": since})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def featurize(df: pd.DataFrame) -> pd.DataFrame:
    enc = pd.get_dummies(df, columns=CATEGORICAL, dummy_na=False, dtype=np.int8)
    drop = {"ticker","ts","tf","bar_date","open","high","low","close","volume",
            "fwd_close_5bars","fwd_close_15bars","fwd_close_30bars","fwd_close_60bars",
            "fwd_ret_5bars_bps","fwd_ret_15bars_bps","fwd_ret_30bars_bps","fwd_ret_60bars_bps",
            "computed_at","trigger_high","trigger_low",
            "is_continuation","is_reversal","is_inside","strat_setup"}
    cols = [c for c in enc.columns
            if c not in drop and enc[c].dtype in (np.float64, np.int64, np.int32, np.int8, np.float32)]
    return enc[cols].replace([np.inf, -np.inf], np.nan).fillna(0).astype(np.float32)


def load_classifier():
    prefix = f"research/p7b/{TICKER.lower()}_{TF}"
    model_bytes = _download(f"{prefix}/model.pkl")
    feat_text = _download(f"{prefix}/features.txt")
    if model_bytes is None or feat_text is None:
        raise RuntimeError(f"No saved classifier at gs://.../{prefix} — run p7b --mode=train first.")
    model = pickle.loads(model_bytes)
    feats = feat_text.decode().strip().split("\n")
    return model, feats


def simulate_exit(bars_after: pd.DataFrame, entry_open: float, side: int,
                  tp_bps: float, sl_bps: float, time_bars: int) -> dict:
    """side: +1 long, -1 short. Walks forward bar-by-bar from entry+1 to
    entry+time_bars. Exits on TP, SL, or end-of-window. Returns realized
    P&L in bps + reason."""
    if entry_open <= 0 or len(bars_after) == 0:
        return {"pnl_bps": 0.0, "reason": "no_bars", "bars_held": 0}
    tp_price = entry_open * (1 + side * tp_bps / 1e4)
    sl_price = entry_open * (1 - side * sl_bps / 1e4)
    for i, (_, b) in enumerate(bars_after.head(time_bars).iterrows(), 1):
        if side == 1:
            # check SL first (worst-case fill) then TP
            if b["low"] <= sl_price:
                return {"pnl_bps": -sl_bps, "reason": "stop", "bars_held": i}
            if b["high"] >= tp_price:
                return {"pnl_bps": +tp_bps, "reason": "target", "bars_held": i}
        else:
            if b["high"] >= sl_price:
                return {"pnl_bps": -sl_bps, "reason": "stop", "bars_held": i}
            if b["low"] <= tp_price:
                return {"pnl_bps": +tp_bps, "reason": "target", "bars_held": i}
    # Time stop — exit at last bar's close
    last = bars_after.head(time_bars).iloc[-1]
    pnl = side * (last["close"] - entry_open) / entry_open * 1e4
    return {"pnl_bps": float(pnl), "reason": "time", "bars_held": int(time_bars)}


def simulate_hold_n(bars_after: pd.DataFrame, entry_open: float, side: int, n: int) -> dict:
    """Just hold for n bars and exit at close."""
    if len(bars_after) < n:
        return {"pnl_bps": 0.0, "reason": "no_bars", "bars_held": len(bars_after)}
    last = bars_after.head(n).iloc[-1]
    pnl = side * (last["close"] - entry_open) / entry_open * 1e4
    return {"pnl_bps": float(pnl), "reason": "hold", "bars_held": n}


EXIT_MODELS = {
    "exitA_25_15_10": dict(tp=25, sl=15, time=10),
    "exitB_50_25_20": dict(tp=50, sl=25, time=20),
    "exitC_hold5":    "hold5",
    "exitD_hold10":   "hold10",
}


def backtest(engine, train_until: str = "2026-01-01"):
    log.info("loading saved classifier from GCS for %s %s...", TICKER, TF)
    model, saved_features = load_classifier()
    log.info("loaded classifier with %d features", len(saved_features))

    log.info("loading OOS bars (>= %s)...", train_until)
    df = load_bars(engine, since=train_until)
    log.info("loaded %d OOS bars (%s..%s)", len(df), df["ts"].min(), df["ts"].max())

    # Predict
    X = featurize(df)
    for c in saved_features:
        if c not in X.columns: X[c] = 0
    X = X[saved_features].astype(np.float32)
    proba = model.predict_proba(X.values)
    df = df.reset_index(drop=True)
    df["p_2u"] = proba[:, CLASS_ORDER.index("2U")]
    df["p_2d"] = proba[:, CLASS_ORDER.index("2D")]
    df["edge"] = df["p_2u"] - df["p_2d"]

    # Decile bins (fit on full OOS, since we're not using deciles for training)
    df["decile"] = pd.qcut(df["edge"], 10, labels=False, duplicates="drop") + 1

    # Select trades: D10 long, D1 short. Then per day, keep ≤ MAX_TRADES_PER_DAY
    # by |edge|.
    df["signal"] = 0
    df.loc[df["decile"] == 10, "signal"] = 1
    df.loc[df["decile"] == 1,  "signal"] = -1
    cands = df[df["signal"] != 0].copy()
    cands["abs_edge"] = cands["edge"].abs()
    cands["bar_date"] = pd.to_datetime(cands["ts"]).dt.date
    selected = cands.sort_values(["bar_date", "abs_edge"], ascending=[True, False]) \
                    .groupby("bar_date").head(MAX_TRADES_PER_DAY).copy()
    log.info("D10 ∪ D1 candidates: %d   selected after %d-per-day cap: %d",
             len(cands), MAX_TRADES_PER_DAY, len(selected))

    # Simulate
    # We need a wide forward window for the longest exit model (time=20 bars).
    LOOKFWD = 25
    all_trades = {k: [] for k in EXIT_MODELS}
    for idx, row in selected.iterrows():
        # entry at NEXT bar's open
        entry_idx = idx + 1
        if entry_idx >= len(df): continue
        entry_bar = df.iloc[entry_idx]
        bars_after = df.iloc[entry_idx+1 : entry_idx+1+LOOKFWD][["open","high","low","close"]]
        if len(bars_after) == 0: continue
        side = int(row["signal"])
        for name, spec in EXIT_MODELS.items():
            if spec == "hold5":
                r = simulate_hold_n(bars_after, entry_bar["open"], side, 5)
            elif spec == "hold10":
                r = simulate_hold_n(bars_after, entry_bar["open"], side, 10)
            else:
                r = simulate_exit(bars_after, entry_bar["open"], side,
                                  spec["tp"], spec["sl"], spec["time"])
            r.update({
                "ts": row["ts"], "bar_date": row["bar_date"], "side": side,
                "edge": float(row["edge"]), "decile": int(row["decile"]),
                "entry": float(entry_bar["open"]),
            })
            all_trades[name].append(r)

    # Aggregate per exit model
    log.info("=" * 100)
    log.info("BACKTEST RESULTS — %s %s, OOS Jan-May 2026, cap=%d trades/day",
             TICKER, TF, MAX_TRADES_PER_DAY)
    log.info("=" * 100)
    log.info("%-18s %5s %6s %6s %6s %6s %6s %8s %8s %8s",
             "exit_model", "n", "win%", "TP%", "SL%", "TIME%", "NO%",
             "gross_bps", "net_bps", "avg_bps")
    log.info("-" * 100)

    summary = {}
    for name, trades in all_trades.items():
        if not trades: continue
        t = pd.DataFrame(trades)
        gross = float(t["pnl_bps"].sum())
        n = len(t)
        net = gross - n * ROUND_TRIP_BPS
        wins = float((t["pnl_bps"] > 0).mean())
        tp_pct = float((t["reason"] == "target").mean())
        sl_pct = float((t["reason"] == "stop").mean())
        time_pct = float(t["reason"].isin(["time", "hold"]).mean())
        no_pct = float((t["reason"] == "no_bars").mean())
        avg = gross / n if n else 0
        log.info("%-18s %5d %5.1f%% %5.1f%% %5.1f%% %5.1f%% %5.1f%% %+8.1f %+8.1f %+8.2f",
                 name, n, wins*100, tp_pct*100, sl_pct*100, time_pct*100, no_pct*100,
                 gross, net, avg)
        summary[name] = {
            "n": n, "win_rate": wins, "tp_rate": tp_pct, "sl_rate": sl_pct,
            "time_rate": time_pct, "gross_bps": gross, "net_bps": net,
            "avg_bps_per_trade": avg,
        }

    # Per-month detail for the best gross model
    best_name = max(summary, key=lambda k: summary[k]["net_bps"]) if summary else None
    if best_name:
        log.info("")
        log.info("Per-month detail for best exit model: %s", best_name)
        t = pd.DataFrame(all_trades[best_name])
        t["month"] = pd.to_datetime(t["ts"]).dt.to_period("M").astype(str)
        per_month = t.groupby("month").agg(
            n=("pnl_bps", "size"),
            gross_bps=("pnl_bps", "sum"),
            avg_bps=("pnl_bps", "mean"),
            win_rate=("pnl_bps", lambda x: float((x > 0).mean())),
        )
        per_month["net_bps"] = per_month["gross_bps"] - per_month["n"] * ROUND_TRIP_BPS
        log.info("\n%s", per_month.round(2).to_string())
        summary["best_per_month"] = per_month.reset_index().to_dict(orient="records")

    # Per-side detail (long vs short separately)
    log.info("")
    log.info("Per-SIDE breakdown (best model):")
    if best_name:
        t = pd.DataFrame(all_trades[best_name])
        for side, label in [(1, "LONG (D10)"), (-1, "SHORT (D1)")]:
            sub = t[t["side"] == side]
            if len(sub) == 0: continue
            gross = sub["pnl_bps"].sum()
            net = gross - len(sub) * ROUND_TRIP_BPS
            wr = (sub["pnl_bps"] > 0).mean()
            log.info("  %-12s n=%d  win=%.1f%%  gross=%+.1f bps  net=%+.1f bps  avg=%+.2f bps",
                     label, len(sub), wr*100, gross, net, gross/len(sub))

    # Option-fill bridge — what underlying move size is needed to overcome
    # typical 0DTE bid-ask. This is illustrative; user's actual fills vary.
    log.info("")
    log.info("OPTION FILL BRIDGE (illustrative; replace with user's actual fills):")
    log.info("  IWM 0DTE ATM option bid-ask is typically $0.01-0.05 wide, on a")
    log.info("  $0.30-1.00 mid. Round-trip cost = (ask - bid) / mid ≈ 5-15%% of")
    log.info("  premium. For a 0DTE call at delta 0.5, a 25-bp underlying move")
    log.info("  produces roughly a ~50%% gain on premium. So the option round-trip")
    log.info("  cost roughly equals 7-15 bps of underlying-equivalent move.")
    log.info("  CONCLUSION: an exit model that nets +5 to +10 bps on the ETF will")
    log.info("  break even or slightly lose on 0DTE options. You need +20 bps net")
    log.info("  on the ETF to be confidently profitable on options.")

    blob = f"research/p7d/{TICKER.lower()}_{TF}_backtest_{int(time.time())}.json"
    _upload(json.dumps(summary, indent=2, default=str).encode(), blob, "application/json")
    log.info("saved summary to gs://%s/%s", MODEL_BUCKET, blob)

    # Also upload per-trade detail for downstream analysis
    if best_name:
        csv_blob = f"research/p7d/{TICKER.lower()}_{TF}_trades_{int(time.time())}.csv"
        t_csv = pd.DataFrame(all_trades[best_name]).to_csv(index=False).encode()
        _upload(t_csv, csv_blob, "text/csv")
        log.info("saved per-trade CSV to gs://%s/%s", MODEL_BUCKET, csv_blob)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=["SPY","IWM","QQQ"])
    p.add_argument("--tf", default="5m", choices=["1m","5m","15m","30m","60m"])
    p.add_argument("--train-until", default="2026-01-01")
    args = p.parse_args()
    global TICKER, TF
    TICKER, TF = args.ticker, args.tf
    log.info("P7d P&L backtest: %s %s", TICKER, TF)
    engine = get_engine()
    backtest(engine, train_until=args.train_until)


if __name__ == "__main__":
    main()
