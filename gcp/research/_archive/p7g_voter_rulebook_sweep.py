#!/usr/bin/env python3
"""Phase 7g — Voter strength sweep under the RULEBOOK exit ladder.

Critical context from the audit:
  The p7f overlay (-9.79 voter_only, etc) measured the voter through the R=2
  STRUCTURAL exit lens. That is NOT the exit the user trades. Re-running the
  strength sweep under R=2 would just reproduce the same misleading negativity.
  This script runs the voter through the EXIT_SIZING_RULEBOOK ladder:

    STOP    0.15% adverse (CALL) / 0.20% adverse (PUT)   exit full
    TARGET  0.30% favorable (CALL) / 0.38% favorable (PUT) exit full
    TIME    30 min (CALL) / 35 min (PUT)                 exit at market
    RSI     RSI(14) on trade TF > 80 (CALL) or < 20 (PUT) exit at market
    LADDER  STOP -> TARGET -> TIME -> RSI; first match wins;
            whipsaw tie-break = STOP wins
    DEFAULT HOLD

Sweep: strength_floor in {>=3, >=4, >=5, >=6}.
Monitoring: 1m bars for stop/target/time; trade-TF RSI propagated to each 1m
bar via merge_asof (most-recent-closed trade TF RSI).

NOTE: Thresholds are RULEBOOK v1 DRAFT placeholders. Confirm or correct.
"""
from __future__ import annotations
import argparse
import json
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

MODEL_BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
ROUND_TRIP_BPS = 10.0
TF_MINUTES = {"15m": 15, "60m": 60}

# RULEBOOK v1 DRAFT (placeholders, pending lock)
RULEBOOK = {
    "call": {"stop_pct": 0.15, "target_pct": 0.30, "time_min": 30,
             "rsi_extreme": 80.0, "rsi_dir": "above"},
    "put":  {"stop_pct": 0.20, "target_pct": 0.38, "time_min": 35,
             "rsi_extreme": 20.0, "rsi_dir": "below"},
}
STRENGTH_FLOORS = [3, 4, 5, 6]


def _gcs(): return gcs.Client()
def _upload(content, blob, ctype="application/octet-stream"):
    _gcs().bucket(MODEL_BUCKET).blob(blob).upload_from_string(content, content_type=ctype)


def load_voter_fires(engine, ticker, tf, min_strength, since):
    sql = text("""
        SELECT entry_time, trade_type, signal_strength
          FROM historical_signals
         WHERE ticker = :t AND timeframe_tag = :tf
           AND signal_strength >= :s AND entry_time >= :u
         ORDER BY entry_time
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker, "tf": tf,
                                          "s": min_strength, "u": since})
    if df.empty:
        return df
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    minutes = TF_MINUTES[tf]
    df["signal_bar_ts"] = df["entry_time"].dt.floor(f"{minutes}min")
    df["side"] = df["trade_type"].map({"call": 1, "put": -1}).astype("Int64")
    df = df.dropna(subset=["side"])
    # Dedupe per signal-bar/side: keep highest strength, earliest alert
    df = (df.sort_values(["signal_bar_ts", "side", "signal_strength", "entry_time"],
                         ascending=[True, True, False, True])
            .drop_duplicates(subset=["signal_bar_ts", "side"], keep="first")
            .reset_index(drop=True))
    return df[["signal_bar_ts", "side", "trade_type", "signal_strength"]]


def load_trade_tf_bars(engine, ticker, tf, since):
    sql = text(f"SELECT ts, open, high, low, close, rsi_14 "
               f"FROM strat_features_{tf} "
               f"WHERE ticker = :t AND ts >= :u ORDER BY ts")
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker, "u": since})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.reset_index(drop=True)


def load_1m_bars(engine, ticker, since):
    sql = text("SELECT ts, open, high, low, close FROM strat_features_1m "
               "WHERE ticker = :t AND ts >= :u ORDER BY ts")
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker, "u": since})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.reset_index(drop=True)


def simulate_rulebook(entry: float, side: int, trade_type: str,
                      window_1m: pd.DataFrame) -> dict:
    """Walk 1m bars with attached trade-TF RSI. Ladder: STOP -> TARGET -> TIME -> RSI."""
    if entry <= 0 or window_1m.empty:
        return {"pnl_bps": 0.0, "reason": "bad_entry", "minutes": 0}

    rb = RULEBOOK[trade_type]
    stop_d = rb["stop_pct"] / 100.0
    tgt_d  = rb["target_pct"] / 100.0
    tmax   = rb["time_min"]
    rsi_x  = rb["rsi_extreme"]
    rsi_d  = rb["rsi_dir"]

    stop_price   = entry * (1 - side * stop_d)
    target_price = entry * (1 + side * tgt_d)

    for i, (_, b) in enumerate(window_1m.iterrows(), 1):
        if side == 1:
            if b["low"] <= stop_price:
                return {"pnl_bps": float(-stop_d * 1e4), "reason": "stop", "minutes": i}
            if b["high"] >= target_price:
                return {"pnl_bps": float(tgt_d * 1e4), "reason": "target", "minutes": i}
        else:
            if b["high"] >= stop_price:
                return {"pnl_bps": float(-stop_d * 1e4), "reason": "stop", "minutes": i}
            if b["low"] <= target_price:
                return {"pnl_bps": float(tgt_d * 1e4), "reason": "target", "minutes": i}

        if i >= tmax:
            actual = side * (b["close"] - entry) / entry * 1e4
            return {"pnl_bps": float(actual), "reason": "time", "minutes": i}

        if pd.notna(b.get("rsi_14")):
            r = float(b["rsi_14"])
            triggered = (rsi_d == "above" and r > rsi_x) or (rsi_d == "below" and r < rsi_x)
            if triggered:
                actual = side * (b["close"] - entry) / entry * 1e4
                return {"pnl_bps": float(actual), "reason": "rsi", "minutes": i}

    # ran out of 1m bars before time stop
    last = window_1m.iloc[-1]
    actual = side * (last["close"] - entry) / entry * 1e4
    return {"pnl_bps": float(actual), "reason": "time_truncated", "minutes": len(window_1m)}


def _tod_bucket(ts_utc: pd.Timestamp) -> str:
    """Map a UTC timestamp to the rulebook §4 ET time-of-day bucket."""
    et = ts_utc.tz_convert("America/New_York")
    h, m = et.hour, et.minute
    minutes = h * 60 + m
    if 9 * 60 + 30 <= minutes < 11 * 60 + 30:
        return "09:30-11:30_prime"
    if 11 * 60 + 30 <= minutes < 13 * 60 + 30:
        return "11:30-13:30_lunch"
    if 13 * 60 + 30 <= minutes < 14 * 60:
        return "13:30-14:00_normal"
    if 14 * 60 <= minutes < 16 * 60:
        return "14:00-16:00_degraded"
    return "off_hours"


def run_strength(fires: pd.DataFrame, tf_bars: pd.DataFrame, bars_1m: pd.DataFrame,
                 tf_lookup: dict, m1_lookup: dict, floor: int) -> dict:
    trades = []
    for _, f in fires.iterrows():
        signal_loc = tf_lookup.get(pd.Timestamp(f["signal_bar_ts"]))
        if signal_loc is None: continue
        entry_loc_tf = signal_loc + 1
        if entry_loc_tf >= len(tf_bars): continue
        entry_bar = tf_bars.iloc[entry_loc_tf]
        entry_price = float(entry_bar["open"])
        entry_ts = pd.Timestamp(entry_bar["ts"])
        entry_loc_1m = m1_lookup.get(entry_ts)
        if entry_loc_1m is None: continue
        # Pull enough 1m bars to cover the longest time stop
        max_window = max(rb["time_min"] for rb in RULEBOOK.values()) + 5
        window = bars_1m.iloc[entry_loc_1m : entry_loc_1m + max_window]
        r = simulate_rulebook(entry_price, int(f["side"]),
                              str(f["trade_type"]), window)
        r.update({
            "side": int(f["side"]), "trade_type": str(f["trade_type"]),
            "signal_strength": int(f["signal_strength"]),
            "ts": entry_ts, "entry": entry_price,
        })
        if r["reason"] not in ("bad_entry",):
            trades.append(r)

    if not trades:
        return {"floor": floor, "n": 0}
    t = pd.DataFrame(trades)
    n = len(t)
    gross = float(t["pnl_bps"].sum())
    net = gross - n * ROUND_TRIP_BPS
    wins = float((t["pnl_bps"] > 0).mean())
    se = float(t["pnl_bps"].std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    avg = gross / n
    net_avg = avg - ROUND_TRIP_BPS
    reasons = t["reason"].value_counts().to_dict()
    # Per-TOD breakdown (rulebook §4)
    t["tod"] = t["ts"].apply(_tod_bucket)
    per_tod = {}
    for tod, sub in t.groupby("tod"):
        sub_n = len(sub)
        sub_gross = float(sub["pnl_bps"].sum())
        sub_se = float(sub["pnl_bps"].std(ddof=1) / np.sqrt(sub_n)) if sub_n > 1 else 0.0
        sub_avg = sub_gross / sub_n
        per_tod[tod] = {
            "n": sub_n, "win_rate": float((sub["pnl_bps"] > 0).mean()),
            "gross_bps": sub_gross,
            "avg_gross_per_trade": sub_avg,
            "avg_net_per_trade": sub_avg - ROUND_TRIP_BPS,
            "se_per_trade": sub_se,
            "ci95_net_lo": sub_avg - ROUND_TRIP_BPS - 1.96 * sub_se,
            "ci95_net_hi": sub_avg - ROUND_TRIP_BPS + 1.96 * sub_se,
        }
    per_side = {}
    for sd_int, sd_lbl in [(1, "long"), (-1, "short")]:
        sub = t[t["side"] == sd_int]
        if len(sub) == 0: continue
        sub_n = len(sub)
        sub_gross = float(sub["pnl_bps"].sum())
        sub_se = float(sub["pnl_bps"].std(ddof=1) / np.sqrt(sub_n)) if sub_n > 1 else 0.0
        per_side[sd_lbl] = {
            "n": sub_n, "win_rate": float((sub["pnl_bps"] > 0).mean()),
            "gross_bps": sub_gross, "net_bps": sub_gross - sub_n * ROUND_TRIP_BPS,
            "avg_net_per_trade": sub_gross / sub_n - ROUND_TRIP_BPS,
            "se_per_trade": sub_se,
        }
    return {
        "floor": floor, "n": n, "win_rate": wins,
        "gross_bps": gross, "net_bps": net,
        "avg_gross_per_trade": avg, "avg_net_per_trade": net_avg,
        "se_per_trade": se,
        "ci95_net_lo": net_avg - 1.96 * se,
        "ci95_net_hi": net_avg + 1.96 * se,
        "exit_reasons": reasons,
        "per_side": per_side,
        "per_tod": per_tod,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=["SPY","IWM","QQQ"])
    p.add_argument("--tf", default="15m", choices=["15m","60m"])
    p.add_argument("--train-until", default="2026-01-01")
    args = p.parse_args()

    engine = get_engine()
    log.info("p7g: %s %s OOS>=%s", args.ticker, args.tf, args.train_until)
    log.info("RULEBOOK v1 draft (PLACEHOLDERS):")
    log.info("  CALL  stop=%.2f%% target=%.2f%% time=%dm RSI>%g",
             RULEBOOK["call"]["stop_pct"], RULEBOOK["call"]["target_pct"],
             RULEBOOK["call"]["time_min"], RULEBOOK["call"]["rsi_extreme"])
    log.info("  PUT   stop=%.2f%% target=%.2f%% time=%dm RSI<%g",
             RULEBOOK["put"]["stop_pct"], RULEBOOK["put"]["target_pct"],
             RULEBOOK["put"]["time_min"], RULEBOOK["put"]["rsi_extreme"])

    bars_1m = load_1m_bars(engine, args.ticker, args.train_until)
    tf_bars = load_trade_tf_bars(engine, args.ticker, args.tf, args.train_until)
    log.info("loaded %d 1m bars, %d %s bars (OOS)", len(bars_1m), len(tf_bars), args.tf)

    # Attach trade-TF RSI to each 1m bar via merge_asof backward
    bars_1m = pd.merge_asof(
        bars_1m.sort_values("ts"),
        tf_bars[["ts", "rsi_14"]].sort_values("ts"),
        on="ts", direction="backward",
    ).reset_index(drop=True)

    tf_lookup = {pd.Timestamp(t): i for i, t in enumerate(tf_bars["ts"])}
    m1_lookup = {pd.Timestamp(t): i for i, t in enumerate(bars_1m["ts"])}

    summary = {"ticker": args.ticker, "tf": args.tf,
               "train_until": args.train_until,
               "rulebook": RULEBOOK, "by_floor": {}}

    log.info("=" * 118)
    log.info("STRENGTH SWEEP — %s %s, OOS, RULEBOOK exits, %.0f bps round-trip cost",
             args.ticker, args.tf, ROUND_TRIP_BPS)
    log.info("=" * 118)
    log.info("%-18s %6s %7s %9s %9s %8s %8s   %s   %s",
             "filter", "n", "win%", "gross", "net", "net/tr", "SE",
             "95% CI net/trade", "exit reasons")
    log.info("-" * 118)
    for floor in STRENGTH_FLOORS:
        fires = load_voter_fires(engine, args.ticker, args.tf, floor, args.train_until)
        r = run_strength(fires, tf_bars, bars_1m, tf_lookup, m1_lookup, floor)
        if r["n"] == 0:
            log.info("strength>=%d: 0 trades", floor)
            continue
        verdict = "OUT 0" if (r["ci95_net_lo"] > 0 or r["ci95_net_hi"] < 0) else "spans 0"
        log.info("strength>=%-7d %6d %6.1f%% %+9.0f %+9.0f %+8.2f %8.2f   [%+.2f, %+.2f] %s   %s",
                 floor, r["n"], r["win_rate"]*100, r["gross_bps"], r["net_bps"],
                 r["avg_net_per_trade"], r["se_per_trade"],
                 r["ci95_net_lo"], r["ci95_net_hi"], verdict,
                 r["exit_reasons"])
        # per-side detail
        for sd, sd_r in r["per_side"].items():
            log.info("    %-14s  %5d %5.1f%% %+9.0f %+9.0f %+8.2f %8.2f",
                     sd, sd_r["n"], sd_r["win_rate"]*100,
                     sd_r["gross_bps"], sd_r["net_bps"],
                     sd_r["avg_net_per_trade"], sd_r["se_per_trade"])
        # per-TOD detail (rulebook §4 windows)
        for tod, td_r in sorted(r["per_tod"].items()):
            if td_r["n"] < 20: continue
            verdict_t = "OUT 0" if (td_r["ci95_net_lo"] > 0 or td_r["ci95_net_hi"] < 0) else "spans 0"
            log.info("    TOD %-24s  n=%-5d win=%5.1f%%  gross/tr=%+6.2f  net/tr=%+6.2f  CI=[%+.2f,%+.2f] %s",
                     tod, td_r["n"], td_r["win_rate"]*100,
                     td_r["avg_gross_per_trade"], td_r["avg_net_per_trade"],
                     td_r["ci95_net_lo"], td_r["ci95_net_hi"], verdict_t)
        summary["by_floor"][floor] = r

    blob = f"research/p7g/{args.ticker.lower()}_{args.tf}_rulebook_{int(time.time())}.json"
    _upload(json.dumps(summary, indent=2, default=str).encode(), blob, "application/json")
    log.info("saved: gs://%s/%s", MODEL_BUCKET, blob)


if __name__ == "__main__":
    main()
