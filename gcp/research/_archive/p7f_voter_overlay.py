#!/usr/bin/env python3
"""Phase 7f — Classifier-edge OVERLAY on the 3-of-5 voter (historical_signals).

The one question worth asking after p7d/p7e:
  Does filtering the existing voter's fires by next-candle classifier agreement
  improve per-trade net P&L, or does it only cut trade count?

Why this and nothing else:
  - Standalone classifier nets ~+7-8 bps gross (below the 10 bps cost line).
  - Stacking classifier probs into the return regression added ~0 (redundant).
  - But FILTERING is neither of those. It changes WHICH voter trades you take,
    not the features and not the entry trigger. The Strat overlay as a filter
    already lifted Sharpe +133% in the prior IWM backtest, so the honest
    remaining test is whether the ML edge adds anything on top of voter selection.

Schema notes (real `historical_signals` table, probed 2026-05-25):
  - `entry_time` (TIMESTAMPTZ) — the time of entry
  - `trade_type` ('call' = long, 'put' = short)
  - `signal_strength` (3-7) — voter score, 3 is the existing entry floor
  - `timeframe_tag` ('15m' / '60m' / '240m')
  - OOS rows only exist from 2026-04-01 onwards (~7 weeks at the time of this
    audit) — much narrower than the classifier's Jan-May 2026 OOS

Methodology (Strat-native, picks up p7d/p7e indexing fix by construction):
  - SIGNAL bar = bar at (entry_time - 1 period) in strat_features_<tf>
  - Entry price = entry_bar's open (= bar at entry_time)
  - Structural STOP = signal_bar's low (long) / high (short)
  - R-multiple target relative to (entry - stop)
  - Exit walk starts at entry bar — no idx+2 skip
  - Classifier edge attached at signal_bar (not entry_bar — no peek)

Outputs voter-only baseline + filtered rows (agreement + |edge| thresholds),
each with net per-trade, SE, and 95% CI so we see immediately whether the
classifier overlay adds anything or just thins the count.
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

TICKER = "IWM"
TF = "15m"
MODEL_BUCKET = os.environ.get("GCS_BUCKET", "adept-mountain-474619-d4-trading-data")
CLASS_ORDER = ["1", "2U", "2D", "3"]
CATEGORICAL = ["strat_candle", "prev_strat_candle", "strat_combo",
               "vix_tercile", "gex_tercile", "vex_tercile",
               "dealer_regime", "gamma_regime"]
ROUND_TRIP_BPS = 10.0
MAX_BARS_HELD = 20
EDGE_THRESHOLDS = [0.0, 0.10, 0.20, 0.30, 0.50]


def _gcs(): return gcs.Client()
def _download(blob):
    b = _gcs().bucket(MODEL_BUCKET).blob(blob)
    return b.download_as_bytes() if b.exists() else None
def _upload(content, blob, ctype="application/octet-stream"):
    _gcs().bucket(MODEL_BUCKET).blob(blob).upload_from_string(content, content_type=ctype)


TF_MINUTES = {"15m": 15, "60m": 60}


def load_voter_fires(engine, ticker: str, tf: str, since: str,
                     min_strength: int = 3) -> pd.DataFrame:
    """Pull voter fires, floor to TF boundary, dedupe per (signal_bar, side).
    Voter writes minute-level entries and often re-fires while a setup is open
    (e.g. 5 alerts from 17:21-17:30 for the same 17:15-17:30 bar). The user
    would take at most one — keep the FIRST alert per signal-bar/side, with
    the highest signal_strength as a tiebreaker."""
    sql = text("""
        SELECT entry_time, trade_type, signal_strength
          FROM historical_signals
         WHERE ticker = :t
           AND timeframe_tag = :tf
           AND signal_strength >= :s
           AND entry_time >= :u
         ORDER BY entry_time
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker, "tf": tf, "s": min_strength, "u": since})
    if df.empty:
        return df.assign(ts=pd.Series(dtype="datetime64[ns, UTC]"), side=pd.Series(dtype=int))
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    minutes = TF_MINUTES[tf]
    # Floor to TF boundary: the bar CONTAINING the alert is the signal bar.
    df["signal_bar_ts"] = df["entry_time"].dt.floor(f"{minutes}min")
    df["side"] = df["trade_type"].map({"call": 1, "put": -1}).astype("Int64")
    df = df.dropna(subset=["side"]).copy()
    # Dedupe per (signal_bar, side); keep highest strength, break ties by earliest alert
    df = (df.sort_values(["signal_bar_ts", "side", "signal_strength", "entry_time"],
                         ascending=[True, True, False, True])
            .drop_duplicates(subset=["signal_bar_ts", "side"], keep="first")
            .rename(columns={"signal_bar_ts": "ts"})
            .reset_index(drop=True))
    return df[["ts", "side", "signal_strength", "entry_time"]]


def load_bars(engine, ticker: str, tf: str, since_train: str) -> pd.DataFrame:
    """Load BOTH train (for decile thresholds) and OOS bars."""
    sql = text(f"SELECT * FROM strat_features_{tf} "
               f"WHERE ticker = :t AND strat_candle IS NOT NULL ORDER BY ts")
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
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


def classifier_edge_all_bars(df: pd.DataFrame, ticker: str, tf: str) -> tuple[pd.Series, list[str]]:
    prefix = f"research/p7b/{ticker.lower()}_{tf}"
    mb = _download(f"{prefix}/model.pkl")
    ft = _download(f"{prefix}/features.txt")
    if mb is None or ft is None:
        raise RuntimeError(f"No saved classifier at gs://.../{prefix}")
    model = pickle.loads(mb)
    feats = ft.decode().strip().split("\n")
    X = featurize(df)
    for c in feats:
        if c not in X.columns: X[c] = 0
    X = X[feats].astype(np.float32)
    proba = model.predict_proba(X.values)
    edge = proba[:, CLASS_ORDER.index("2U")] - proba[:, CLASS_ORDER.index("2D")]
    return pd.Series(edge, index=df.index), feats


def simulate_structural_with_entry_bar(bars_from_entry: pd.DataFrame,
                                       entry: float, stop: float,
                                       side: int, r_mult: float,
                                       max_bars: int = MAX_BARS_HELD) -> dict:
    """Exit walk STARTS at entry bar (indexing fix). The entry bar itself is
    stop-eligible AND target-eligible. SL checked first (conservative for
    same-bar both-touched ambiguity)."""
    if side == 1:
        r_dist = entry - stop
        if r_dist <= 0: return {"pnl_bps": 0.0, "reason": "bad_stop", "bars_held": 0}
        target = entry + r_mult * r_dist
    else:
        r_dist = stop - entry
        if r_dist <= 0: return {"pnl_bps": 0.0, "reason": "bad_stop", "bars_held": 0}
        target = entry - r_mult * r_dist
    bars = bars_from_entry.head(max_bars)
    if len(bars) == 0:
        return {"pnl_bps": 0.0, "reason": "no_bars", "bars_held": 0}
    for i, (_, b) in enumerate(bars.iterrows(), 1):
        if side == 1:
            if b["low"] <= stop:
                return {"pnl_bps": float(-r_dist / entry * 1e4), "reason": "stop", "bars_held": i}
            if b["high"] >= target:
                return {"pnl_bps": float(r_mult * r_dist / entry * 1e4), "reason": "target", "bars_held": i}
        else:
            if b["high"] >= stop:
                return {"pnl_bps": float(-r_dist / entry * 1e4), "reason": "stop", "bars_held": i}
            if b["low"] <= target:
                return {"pnl_bps": float(r_mult * r_dist / entry * 1e4), "reason": "target", "bars_held": i}
    last = bars.iloc[-1]
    actual = side * (last["close"] - entry)
    return {"pnl_bps": float(actual / entry * 1e4), "reason": "time", "bars_held": len(bars)}


def run_set(label: str, fires: pd.DataFrame, df: pd.DataFrame,
            ts_to_loc: dict, r_mult: float) -> dict:
    trades = []
    for _, f in fires.iterrows():
        # f["ts"] is the floored signal bar (the bar containing the alert).
        # Convention: wait for signal bar to close, enter at NEXT bar's open.
        # Structural stop = signal bar's low (long) / high (short).
        signal_loc = ts_to_loc.get(pd.Timestamp(f["ts"]))
        if signal_loc is None: continue
        entry_loc = signal_loc + 1
        if entry_loc >= len(df): continue
        signal_bar = df.iloc[signal_loc]
        entry_bar  = df.iloc[entry_loc]
        side = int(f["side"])
        stop  = float(signal_bar["low"])  if side == 1 else float(signal_bar["high"])
        entry = float(entry_bar["open"])
        # Exit walk starts AT entry bar — indexing fix
        bars_from_entry = df.iloc[entry_loc : entry_loc + MAX_BARS_HELD + 1][["open","high","low","close"]]
        r = simulate_structural_with_entry_bar(bars_from_entry, entry, stop, side, r_mult)
        if r["reason"] != "bad_stop":
            trades.append(r["pnl_bps"])
    if not trades:
        return {"label": label, "n_signals": len(fires), "n_filled": 0}
    t = np.array(trades)
    n = len(t)
    gross = float(t.sum()); net = gross - n * ROUND_TRIP_BPS
    avg = gross / n; net_avg = avg - ROUND_TRIP_BPS
    se = float(t.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    return {
        "label": label, "n_signals": int(len(fires)), "n_filled": n,
        "fill_rate": n / max(len(fires), 1),
        "win_rate": float((t > 0).mean()),
        "tp_rate": float((t > 0).mean()),    # under R-target every win = TP
        "gross_bps": gross, "net_bps": net,
        "avg_gross_per_trade": avg, "avg_net_per_trade": net_avg,
        "se_per_trade": se,
        "ci95_net_lo": net_avg - 1.96 * se,
        "ci95_net_hi": net_avg + 1.96 * se,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=["SPY","IWM","QQQ"])
    p.add_argument("--tf", default="15m", choices=["15m","60m"])  # voter only writes these
    p.add_argument("--r", type=float, default=2.0)
    p.add_argument("--train-until", default="2026-01-01",
                   help="Classifier train cutoff. Voter OOS starts at this date too.")
    p.add_argument("--min-strength", type=int, default=3)
    args = p.parse_args()
    global TICKER, TF
    TICKER, TF = args.ticker, args.tf

    engine = get_engine()
    log.info("P7f voter overlay: %s %s R=%.1f OOS>=%s strength>=%d",
             TICKER, TF, args.r, args.train_until, args.min_strength)

    df = load_bars(engine, TICKER, TF, args.train_until)
    log.info("loaded %d total bars (train+OOS) (%s..%s)", len(df), df["ts"].min(), df["ts"].max())

    edge_all, feats = classifier_edge_all_bars(df, TICKER, TF)
    df["edge"] = edge_all
    ts_to_loc = {pd.Timestamp(t): i for i, t in enumerate(df["ts"])}
    log.info("classifier scored %d bars", len(df))

    fires = load_voter_fires(engine, TICKER, TF, args.train_until, args.min_strength)
    log.info("voter fires (>=strength %d, OOS>=%s): %d", args.min_strength, args.train_until, len(fires))
    if fires.empty:
        log.error("NO VOTER FIRES. Verify timeframe_tag/min-strength/since.")
        return

    # Attach classifier edge AT SIGNAL BAR (the floored alert bar — no peek;
    # the classifier features are derived from that bar's close which is
    # known by the next bar's open where we enter).
    def _edge_at_signal(t):
        loc = ts_to_loc.get(pd.Timestamp(t))
        if loc is None: return np.nan
        return float(df["edge"].iloc[loc])
    fires = fires.copy()
    fires["edge_at_signal"] = fires["ts"].map(_edge_at_signal)
    fires = fires.dropna(subset=["edge_at_signal"])
    log.info("voter fires with matching strat_features bar: %d", len(fires))

    rows = []
    rows.append(run_set("voter_only (no filter)", fires, df, ts_to_loc, args.r))
    for thr in EDGE_THRESHOLDS:
        sub = fires[(np.sign(fires["edge_at_signal"]) == fires["side"]) &
                    (fires["edge_at_signal"].abs() >= thr)]
        rows.append(run_set(f"voter + agree, |edge|>={thr:.2f}", sub, df, ts_to_loc, args.r))

    log.info("=" * 120)
    log.info("VOTER OVERLAY — %s %s, R=%.1f, OOS, structural-stop + indexing-fixed exit",
             TICKER, TF, args.r)
    log.info("cost=%.0f bps round-trip", ROUND_TRIP_BPS)
    log.info("=" * 120)
    log.info("%-32s %8s %8s %7s %6s %10s %10s %9s %s",
             "filter", "signals", "filled", "fill%", "win%",
             "gross", "net", "net/tr", "95% CI net/trade")
    log.info("-" * 120)
    for r in rows:
        if r.get("n_filled", 0) == 0:
            log.info("%-32s %8d %8d   (no trades)", r["label"], r["n_signals"], 0)
            continue
        verdict = "OUT 0" if (r["ci95_net_lo"] > 0 or r["ci95_net_hi"] < 0) else "spans 0"
        log.info("%-32s %8d %8d %6.0f%% %5.1f%% %+10.0f %+10.0f %+9.2f [%+.2f, %+.2f] %s",
                 r["label"], r["n_signals"], r["n_filled"], r["fill_rate"]*100,
                 r["win_rate"]*100, r["gross_bps"], r["net_bps"],
                 r["avg_net_per_trade"], r["ci95_net_lo"], r["ci95_net_hi"], verdict)

    blob = f"research/p7f/{TICKER.lower()}_{TF}_R{args.r}_{int(time.time())}.json"
    _upload(json.dumps(rows, indent=2, default=str).encode(), blob, "application/json")
    log.info("saved: gs://%s/%s", MODEL_BUCKET, blob)


if __name__ == "__main__":
    main()
