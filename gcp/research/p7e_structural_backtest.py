#!/usr/bin/env python3
"""Phase 7e — Structural-exit P&L backtest (Strat-native).

Addresses two real critiques of p7d:

  1. Fixed-bps stops are NOT Strat-native and pre-determine the failure mode.
     A flat 15-bp stop sits inside the noise band of a tight 5m bar, so the
     2U poke trips it on exactly the bars where signal is weakest. Real
     Strat exits are STRUCTURAL: stop at the trigger bar's low (long) or
     high (short); target as an R-multiple of that distance.

  2. The combo × dealer_regime cells from earlier P7 work never got a
     clean-OOS P&L test. They were computed mixed-sample. This script
     re-derives top cells from training data only, then trades them OOS
     with the same structural-exit framework.

Modes (--signal):
  classifier-long   Top decile (D10) of classifier directional edge, long only
  classifier-both   D10 long + D1 short
  combo-regime      Top (strat_combo, dealer_regime) cells from training data,
                    long when mean_bps > 0, short when < 0

For each signal, tests 4 R-multiple targets (1R, 1.5R, 2R, 3R) with
structural stop and a 20-bar time stop. Reports per-trade SE so the user
can see what's statistically distinguishable from zero.
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
TF = "15m"
MODEL_BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
CLASS_ORDER = ["1", "2U", "2D", "3"]
CATEGORICAL = ["strat_candle", "prev_strat_candle", "strat_combo",
               "vix_tercile", "gex_tercile", "vex_tercile",
               "dealer_regime", "gamma_regime"]

ROUND_TRIP_BPS = 10.0
MAX_TRADES_PER_DAY = 2
MAX_BARS_HELD = 20
R_MULTIPLES = [1.0, 1.5, 2.0, 3.0]


def _gcs():
    return gcs.Client()


def _download(blob):
    b = _gcs().bucket(MODEL_BUCKET).blob(blob)
    return b.download_as_bytes() if b.exists() else None


def _upload(content, blob, ctype="application/octet-stream"):
    b = _gcs().bucket(MODEL_BUCKET).blob(blob)
    b.upload_from_string(content, content_type=ctype)
    return f"gs://{MODEL_BUCKET}/{blob}"


def load_bars(engine, since=None, until=None) -> pd.DataFrame:
    where = "WHERE ticker = :t AND strat_candle IS NOT NULL"
    p = {"t": TICKER}
    if since: where += " AND bar_date >= :s"; p["s"] = since
    if until: where += " AND bar_date < :u"; p["u"] = until
    with engine.connect() as c:
        df = pd.read_sql(text(f"SELECT * FROM strat_features_{TF} {where} ORDER BY ts"), c, params=p)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.reset_index(drop=True)


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


def simulate_structural(bars_after: pd.DataFrame, entry: float, stop: float,
                        side: int, r_mult: float, max_bars: int = MAX_BARS_HELD) -> dict:
    """Structural stop + R-multiple target.
    side: +1 long, -1 short
    stop: absolute price (long: < entry; short: > entry)
    r_mult: target distance as a multiple of (entry - stop)
    """
    if side == 1:
        r_dist = entry - stop
        if r_dist <= 0:
            return {"pnl_bps": 0.0, "reason": "bad_stop", "bars_held": 0, "r_realized": 0.0}
        target = entry + r_mult * r_dist
    else:
        r_dist = stop - entry
        if r_dist <= 0:
            return {"pnl_bps": 0.0, "reason": "bad_stop", "bars_held": 0, "r_realized": 0.0}
        target = entry - r_mult * r_dist

    bars = bars_after.head(max_bars)
    for i, (_, b) in enumerate(bars.iterrows(), 1):
        if side == 1:
            if b["low"] <= stop:
                return {"pnl_bps": float(-r_dist / entry * 1e4), "reason": "stop",
                        "bars_held": i, "r_realized": -1.0}
            if b["high"] >= target:
                return {"pnl_bps": float(r_mult * r_dist / entry * 1e4), "reason": "target",
                        "bars_held": i, "r_realized": float(r_mult)}
        else:
            if b["high"] >= stop:
                return {"pnl_bps": float(-r_dist / entry * 1e4), "reason": "stop",
                        "bars_held": i, "r_realized": -1.0}
            if b["low"] <= target:
                return {"pnl_bps": float(r_mult * r_dist / entry * 1e4), "reason": "target",
                        "bars_held": i, "r_realized": float(r_mult)}
    # Time stop — exit at last bar's close
    if len(bars) == 0:
        return {"pnl_bps": 0.0, "reason": "no_bars", "bars_held": 0, "r_realized": 0.0}
    last = bars.iloc[-1]
    actual = side * (last["close"] - entry)
    return {"pnl_bps": float(actual / entry * 1e4), "reason": "time",
            "bars_held": len(bars), "r_realized": float(actual / r_dist)}


def classifier_signal(df: pd.DataFrame, model, features, side: str) -> pd.DataFrame:
    X = featurize(df)
    for c in features:
        if c not in X.columns: X[c] = 0
    X = X[features].astype(np.float32)
    proba = model.predict_proba(X.values)
    df = df.copy()
    df["p_2u"] = proba[:, CLASS_ORDER.index("2U")]
    df["p_2d"] = proba[:, CLASS_ORDER.index("2D")]
    df["edge"] = df["p_2u"] - df["p_2d"]
    df["decile"] = pd.qcut(df["edge"], 10, labels=False, duplicates="drop") + 1
    df["signal"] = 0
    if side in ("long", "both"):
        df.loc[df["decile"] == 10, "signal"] = 1
    if side in ("short", "both"):
        df.loc[df["decile"] == 1, "signal"] = -1
    return df


def combo_regime_cells(engine, train_until: str, min_n: int = 30, top_n: int = 10) -> pd.DataFrame:
    """Find top (combo, regime) cells in TRAINING data by t-stat on fwd_5bars_bps."""
    sql = text(f"""
        SELECT strat_combo, dealer_regime,
               count(*) AS n,
               avg(fwd_ret_5bars_bps) FILTER (WHERE fwd_ret_5bars_bps::text <> 'NaN') AS mean_bps,
               stddev(fwd_ret_5bars_bps) FILTER (WHERE fwd_ret_5bars_bps::text <> 'NaN') AS std_bps
          FROM strat_features_{TF}
         WHERE ticker = :t AND bar_date < :u
           AND strat_combo IS NOT NULL AND dealer_regime IS NOT NULL
           AND fwd_ret_5bars_bps IS NOT NULL
         GROUP BY strat_combo, dealer_regime
        HAVING count(*) >= :min_n
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": TICKER, "u": train_until, "min_n": min_n})
    df = df[df["std_bps"] > 0].copy()
    df["t_stat"] = df["mean_bps"] / (df["std_bps"] / np.sqrt(df["n"]))
    df["abs_t"] = df["t_stat"].abs()
    return df.sort_values("abs_t", ascending=False).head(top_n).reset_index(drop=True)


def combo_signal(df: pd.DataFrame, cells: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["signal"] = 0
    for _, r in cells.iterrows():
        mask = (df["strat_combo"] == r["strat_combo"]) & (df["dealer_regime"] == r["dealer_regime"])
        df.loc[mask, "signal"] = 1 if r["mean_bps"] > 0 else -1
    return df


def run_backtest(df: pd.DataFrame, signal_name: str) -> tuple[dict, dict]:
    cands = df[df["signal"] != 0].copy()
    cands["day"] = pd.to_datetime(cands["ts"]).dt.date
    cands["score"] = cands["edge"].abs() if "edge" in cands.columns else 1.0
    selected = (cands.sort_values(["day", "score"], ascending=[True, False])
                     .groupby("day", group_keys=False).head(MAX_TRADES_PER_DAY))
    log.info("%s: %d candidates, %d after %d-per-day cap",
             signal_name, len(cands), len(selected), MAX_TRADES_PER_DAY)

    trades_by_R = {R: [] for R in R_MULTIPLES}
    for idx, row in selected.iterrows():
        entry_idx = idx + 1
        if entry_idx >= len(df): continue
        entry_bar = df.iloc[entry_idx]
        bars_after = df.iloc[entry_idx+1 : entry_idx+1+MAX_BARS_HELD+5][["open","high","low","close"]]
        if len(bars_after) == 0: continue
        side = int(row["signal"])
        # STRUCTURAL stop: the SIGNAL bar's low (long) / high (short)
        stop = float(row["low"]) if side == 1 else float(row["high"])
        entry = float(entry_bar["open"])
        r_dist_bps = abs(entry - stop) / entry * 1e4
        for R in R_MULTIPLES:
            r = simulate_structural(bars_after, entry, stop, side, R)
            r.update({
                "ts": row["ts"], "side": side, "entry": entry, "stop": stop,
                "r_distance_bps": r_dist_bps,
            })
            trades_by_R[R].append(r)

    log.info("=" * 110)
    log.info("STRUCTURAL EXIT BACKTEST — %s %s, OOS, %d-per-day cap",
             TICKER, TF, MAX_TRADES_PER_DAY)
    log.info("=" * 110)
    log.info("%-22s %5s %6s %6s %6s %6s %9s %9s %8s %8s %8s",
             "config", "n", "win%", "TP%", "SL%", "TIME%", "avg_R(bps)",
             "gross", "net", "avg/tr", "SE/tr")
    log.info("-" * 110)
    summary = {}
    for R, trades in trades_by_R.items():
        if not trades: continue
        t = pd.DataFrame(trades)
        n = len(t)
        gross = float(t["pnl_bps"].sum())
        net = gross - n * ROUND_TRIP_BPS
        wins = float((t["pnl_bps"] > 0).mean())
        tp = float((t["reason"] == "target").mean())
        sl = float((t["reason"] == "stop").mean())
        tm = float((t["reason"] == "time").mean())
        avg_r_dist = float(t["r_distance_bps"].mean())
        avg_pnl = gross / n
        se = float(t["pnl_bps"].std() / np.sqrt(n)) if n > 1 else 0.0
        ci_lo = avg_pnl - 1.96 * se
        ci_hi = avg_pnl + 1.96 * se
        log.info("%-22s %5d %5.1f%% %5.1f%% %5.1f%% %5.1f%% %9.1f %+9.1f %+8.1f %+8.2f %8.2f",
                 f"R={R}", n, wins*100, tp*100, sl*100, tm*100,
                 avg_r_dist, gross, net, avg_pnl, se)
        log.info("                       95%%CI avg_bps/trade: [%+.2f, %+.2f]  (zero %s)",
                 ci_lo, ci_hi, "OUTSIDE" if (ci_lo > 0 or ci_hi < 0) else "INSIDE → cannot reject")
        summary[f"R={R}"] = {
            "n": n, "win_rate": wins, "tp_rate": tp, "sl_rate": sl, "time_rate": tm,
            "avg_r_distance_bps": avg_r_dist,
            "gross_bps": gross, "net_bps": net, "avg_bps_per_trade": avg_pnl,
            "se_per_trade": se, "ci95_lo": ci_lo, "ci95_hi": ci_hi,
        }
    return summary, trades_by_R


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=["SPY","IWM","QQQ"])
    p.add_argument("--tf", default="15m", choices=["1m","5m","15m","30m","60m"])
    p.add_argument("--signal", required=True,
                   choices=["classifier-long", "classifier-both", "combo-regime"])
    p.add_argument("--train-until", default="2026-01-01")
    p.add_argument("--top-n-cells", type=int, default=10)
    args = p.parse_args()

    global TICKER, TF
    TICKER, TF = args.ticker, args.tf
    log.info("P7e structural backtest: %s %s signal=%s", TICKER, TF, args.signal)
    engine = get_engine()
    df = load_bars(engine, since=args.train_until)
    log.info("loaded %d OOS bars (%s..%s)", len(df), df["ts"].min(), df["ts"].max())

    if args.signal in ("classifier-long", "classifier-both"):
        prefix = f"research/p7b/{TICKER.lower()}_{TF}"
        mb = _download(f"{prefix}/model.pkl")
        ft = _download(f"{prefix}/features.txt")
        if mb is None or ft is None:
            raise RuntimeError(f"No saved classifier at gs://.../{prefix}; run p7b --mode=train first")
        model = pickle.loads(mb)
        features = ft.decode().strip().split("\n")
        side = "long" if args.signal == "classifier-long" else "both"
        df = classifier_signal(df, model, features, side=side)
        signal_name = f"classifier_{side}"
    else:
        cells = combo_regime_cells(engine, args.train_until, top_n=args.top_n_cells)
        log.info("Top %d combo×regime cells from TRAINING data (clean OOS test below):", len(cells))
        log.info("\n%s", cells.to_string(index=False))
        df = combo_signal(df, cells)
        signal_name = f"combo_regime_top{len(cells)}"

    summary, trades = run_backtest(df, signal_name)

    blob = f"research/p7e/{TICKER.lower()}_{TF}_{args.signal}_{int(time.time())}.json"
    _upload(json.dumps(summary, indent=2, default=str).encode(), blob, "application/json")
    log.info("saved: gs://%s/%s", MODEL_BUCKET, blob)


if __name__ == "__main__":
    main()
