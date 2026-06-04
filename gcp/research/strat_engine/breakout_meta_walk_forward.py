"""Strat Engine — BREAKOUT META-LABEL walk-forward (STRAT-BREAKOUT-META).

Reframings #2 + #7 from the 2026-06-04 rethink, and the flagship of the set.

The Strat is a STOP-ENTRY BREAKOUT system: when bar t+1 trades through bar t's
high you are long (a 2U); through bar t's low you are short (a 2D). The
DIRECTION is therefore DETERMINISTIC, given by the rule — which is why training
a model to predict next_close>next_open (strat_dir) failed 24/24: it was the
wrong target. Here we do López de Prado META-LABELING instead:

  PRIMARY (rule, no ML): did t+1 break bar t's range? side = break direction.
  META  (the ML model):  given the breakout fired, does it FOLLOW THROUGH —
                         hit a +k_PT·ATR profit target before a -k_SL·ATR stop
                         within N bars (triple-barrier label)? Binary.

The meta-model predicts TRADE QUALITY, not direction — a well-posed problem.
The success test (López de Prado): does taking only the model's high-confidence
breakouts beat taking EVERY breakout? Vehicle is the underlying (no IV), so we
report precision, profit factor, and per-trade expectancy in R-multiples.

Triple-barrier is labeled on the SAME-tf forward bars (v1). Single-bar
ambiguity (both barriers touched in one bar) is resolved conservatively as a
STOP (the pessimistic assumption — never inflates the edge).

Run:
  python -m gcp.research.strat_engine.breakout_meta_walk_forward \\
      --ticker IWM --tf 15m --pt 1.0 --sl 0.5 --horizon 12
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

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, GCS_BUCKET_DEFAULT, gcs_model_prefix,
)
from gcp.research.strat_engine.strat_dataset import load_labeled_dataset
from gcp.research.strat_engine.strat_pred_train import featurize
from gcp.research.strat_engine.strat_walk_forward import (
    DEFAULT_CUTOFFS, MIN_TEST_BARS, _gcs_upload,
)
from gcp.research.strat_engine.strat_dir_walk_forward import make_direction_lgbm
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

MIN_EVENTS = 150  # per fold-side; below this the fold is reported but not scored


def build_breakout_events(df: pd.DataFrame, pt_atr: float, sl_atr: float,
                           horizon: int) -> pd.DataFrame:
    """Detect primary breakout events and triple-barrier label them.

    df MUST be sorted by (bar_date, ts) and carry open/high/low/close + atr_20.
    For each bar t (decision at close of t), the trigger levels for t+1 are
    bar t's own high/low. A LONG event = high[t+1] > high[t]; SHORT = low[t+1]
    < low[t]. Outside bars on t+1 (both broke) are ambiguous for entry order
    and skipped. Barriers are scanned over t+1..t+horizon WITHIN the same
    session (no overnight cross).

    Returns a per-event frame: row index = the DECISION bar t (so features at t
    align), columns: side (+1/-1), entry, label (1=PT first, 0=SL-first/timeout),
    r_multiple (realized, +pt or -sl or partial at timeout), event_date.
    """
    g = df.reset_index(drop=True)
    n = len(g)
    high = g["high"].values; low = g["low"].values
    close = g["close"].values; openv = g["open"].values
    atr = g["atr_20"].values
    bar_date = g["bar_date"].values
    pos_idx, side_a, entry_a, label_a, rmult_a = [], [], [], [], []

    for t in range(n - 1):
        if not (np.isfinite(atr[t]) and atr[t] > 0):
            continue
        if bar_date[t + 1] != bar_date[t]:
            continue  # next bar is a new session — no intraday trigger
        up_break = high[t + 1] > high[t]
        dn_break = low[t + 1] < low[t]
        if up_break == dn_break:
            continue  # neither, or both (outside bar) → ambiguous entry
        side = 1 if up_break else -1
        entry = high[t] if side == 1 else low[t]
        pt = entry + side * pt_atr * atr[t]
        sl = entry - side * sl_atr * atr[t]
        # scan forward within the session
        label, rmult = 0, None
        end = t + horizon
        for j in range(t + 1, min(end, n - 1) + 1):
            if bar_date[j] != bar_date[t]:
                break
            hi, lo = high[j], low[j]
            hit_pt = (hi >= pt) if side == 1 else (lo <= pt)
            hit_sl = (lo <= sl) if side == 1 else (hi >= sl)
            if hit_pt and hit_sl:
                label, rmult = 0, -sl_atr   # conservative: stop first
                break
            if hit_pt:
                label, rmult = 1, pt_atr
                break
            if hit_sl:
                label, rmult = 0, -sl_atr
                break
        if rmult is None:  # vertical barrier (timeout) — mark to last close
            last = j
            realized = side * (close[last] - entry) / atr[t]
            rmult = float(realized)
            label = 1 if realized >= pt_atr else 0
        pos_idx.append(t); side_a.append(side); entry_a.append(entry)
        label_a.append(label); rmult_a.append(rmult)

    ev = pd.DataFrame({
        "decision_pos": pos_idx, "side": side_a, "entry": entry_a,
        "label": label_a, "r_multiple": rmult_a,
    })
    ev["event_date"] = bar_date[ev["decision_pos"].values]
    return ev


def walk_forward_meta(engine, ticker, tf, pt_atr, sl_atr, horizon, cutoffs=None) -> dict:
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    log.info("=" * 72)
    log.info("BREAKOUT-META  %s %s  PT=%.2f SL=%.2f H=%d", ticker, tf, pt_atr, sl_atr, horizon)
    log.info("=" * 72)

    df = load_labeled_dataset(engine, ticker, tf, include_next_bar_ohlc=False)
    df = df.sort_values(["bar_date", "ts"]).reset_index(drop=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date

    ev = build_breakout_events(df, pt_atr, sl_atr, horizon)
    if ev.empty:
        log.warning("no breakout events — aborting"); return {"status": "NO_EVENTS"}
    base_precision = float(ev["label"].mean())
    log.info("primary breakouts: %d  (base follow-through rate=%.3f, long=%d short=%d)",
             len(ev), base_precision, int((ev.side == 1).sum()), int((ev.side == -1).sum()))

    # Features at the DECISION bar (align by integer position).
    X_df, feat_cols = featurize(df)
    X_all = X_df.values.astype(np.float32, copy=False)
    Xev = X_all[ev["decision_pos"].values]
    # add side as a feature (long vs short breakouts behave differently)
    Xev = np.hstack([Xev, ev["side"].values.reshape(-1, 1).astype(np.float32)])
    y = ev["label"].values.astype(np.int64)
    rmult = ev["r_multiple"].values.astype(np.float64)
    edates = pd.DatetimeIndex(ev["event_date"]).values.astype("datetime64[D]")

    folds = []
    for i, cut in enumerate(cutoffs):
        test_end = cutoffs[i + 1] if i + 1 < len(cutoffs) else \
            str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        tr = edates < np.datetime64(cut)
        te = (edates >= np.datetime64(cut)) & (edates < np.datetime64(test_end))
        n_tr, n_te = int(tr.sum()), int(te.sum())
        if n_te < MIN_EVENTS or n_tr < MIN_EVENTS:
            folds.append({"fold": f"{cut}..{test_end}", "n_test": n_te, "status": "SKIP_THIN"})
            continue
        model = make_direction_lgbm()
        model.fit(Xev[tr], y[tr])
        p = model.predict_proba(Xev[te])[:, 1]

        base_pf = _profit_factor(rmult[te], np.ones(n_te, bool))
        base_exp = float(rmult[te].mean())
        row = {"fold": f"{cut}..{test_end}", "n_train": n_tr, "n_test": n_te,
               "base_precision": float(y[te].mean()),
               "base_expectancy_R": base_exp, "base_profit_factor": base_pf,
               "by_threshold": {}, "status": "OK"}
        for thr in (0.50, 0.55, 0.60, 0.65):
            take = p >= thr
            n_take = int(take.sum())
            if n_take < 20:
                row["by_threshold"][thr] = {"n": n_take, "status": "thin"}
                continue
            prec = float(y[te][take].mean())
            exp = float(rmult[te][take].mean())
            pf = _profit_factor(rmult[te], take)
            row["by_threshold"][thr] = {
                "n": n_take, "precision": prec, "expectancy_R": exp,
                "profit_factor": pf,
                "precision_lift_pp": (prec - row["base_precision"]) * 100,
            }
        folds.append(row)
        b60 = row["by_threshold"].get(0.60, {})
        log.info("  %s n_te=%d base[prec=%.3f exp=%+.3fR pf=%.2f] | take≥0.60 n=%s prec=%s exp=%s",
                 row["fold"], n_te, row["base_precision"], base_exp, base_pf,
                 b60.get("n"), _f(b60.get("precision")), _f(b60.get("expectancy_R"), "+.3f"))

    # Verdict: meta-filter PASSES if take≥0.60 lifts precision AND expectancy
    # over base in ≥5 OK folds.
    oks = [f for f in folds if f.get("status") == "OK"]
    lift_folds = sum(1 for f in oks
                     if f["by_threshold"].get(0.60, {}).get("precision_lift_pp", -1) > 0
                     and f["by_threshold"].get(0.60, {}).get("expectancy_R", -9) >
                         f["base_expectancy_R"])
    verdict = "PASS" if (len(oks) >= 4 and lift_folds >= 5) else (
        "INSUFFICIENT_DATA" if len(oks) < 4 else "FAIL")
    log.info("META verdict: %s (take≥0.60 beat base in %d of %d OK folds)",
             verdict, lift_folds, len(oks))

    summary = {
        "ticker": ticker, "tf": tf, "model": "STRAT-BREAKOUT-META",
        "params": {"pt_atr": pt_atr, "sl_atr": sl_atr, "horizon": horizon},
        "n_events": int(len(ev)), "overall_base_precision": base_precision,
        "verdict": verdict, "lift_folds": lift_folds, "folds": folds,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    blob = f"{gcs_model_prefix(ticker, tf)}/breakout_meta_wf_pt{pt_atr}_sl{sl_atr}_h{horizon}_{int(time.time())}.json"
    _gcs_upload(json.dumps(summary, indent=2, default=str).encode(), blob)
    log.info("saved gs://%s/%s", os.environ.get("GCS_BUCKET", GCS_BUCKET_DEFAULT), blob)
    return summary


def _profit_factor(rmult: np.ndarray, take: np.ndarray) -> float:
    r = rmult[take]
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    return float(gains / losses) if losses > 0 else float("inf")


def _f(v, fmt=".3f"):
    return format(v, fmt) if isinstance(v, (int, float)) else "—"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--pt", type=float, default=1.0, help="profit target in ATR")
    p.add_argument("--sl", type=float, default=0.5, help="stop in ATR")
    p.add_argument("--horizon", type=int, default=12, help="vertical barrier in bars")
    p.add_argument("--cutoffs", default=None)
    args = p.parse_args()
    cutoffs = args.cutoffs.split(",") if args.cutoffs else None
    walk_forward_meta(get_engine(), args.ticker, args.tf,
                      args.pt, args.sl, args.horizon, cutoffs=cutoffs)


if __name__ == "__main__":
    main()
