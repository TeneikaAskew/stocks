#!/usr/bin/env python3
"""CLV ablation — how much of the next-bar edge is close-location (partly
mechanical) vs the rest (momentum + FTFC + structure)?

Separate, additive, reproducible: imports build_bars READ-ONLY from
strat_oos_multi_tf (does not modify any existing CLV script or its results).
Runs the SAME held-out OOS (train strictly before each test year, daily+weekly)
under four feature sets and compares:

  FULL        all features (incl. CLV)            — reproduces the prior result
  NO_CLV      everything EXCEPT close-location     — the non-mechanical signal
  CLV_ONLY    close-location alone                 — how much CLV carries solo
  STRUCT_ONLY momentum (ret_1/2/3) + FTFC only     — pure structural/trend signal

If NO_CLV stays well above base, the edge is largely genuine (momentum/FTFC).
If NO_CLV collapses toward base and CLV_ONLY ≈ FULL, the edge is mostly the
mechanical close→next-open effect.

    python -m scripts.strat_oos_clv_ablation --tickers SPY,QQQ,IWM --timeframes 1d,1w
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_loader import DataLoader
from scripts.strat_oos_multi_tf import build_bars, FEATS  # READ-ONLY reuse

SETS = {
    "FULL":        FEATS,
    "NO_CLV":      [f for f in FEATS if f != "clv"],
    "CLV_ONLY":    ["clv"],
    "STRUCT_ONLY": ["ret_1", "ret_2", "ret_3", "ftfc"],
}


def _oos_pooled(d: pd.DataFrame, feats: list) -> tuple:
    """Per-year held-out logistic over directional bars; return (pooled_acc,
    pooled_base, pooled_LLbeat, n)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    d = d.copy()
    d["year"] = pd.DatetimeIndex(d.index).year
    accs = bases = beats = ntot = 0.0
    for Y in sorted(d["year"].unique()):
        tr, te = d[d["year"] < Y], d[d["year"] == Y]
        if len(te) < 25 or len(tr) < 120:
            continue
        yte = te["next_up"].values
        Xtr = tr[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        Xte = te[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        clf = LogisticRegression(max_iter=2000, C=0.5)
        clf.fit((Xtr - mu) / sd, tr["next_up"].values)
        p = clf.predict_proba((Xte - mu) / sd)[:, 1]
        n = len(te)
        accs += ((p >= 0.5).astype(int) == yte).mean() * n
        bases += max(yte.mean(), 1 - yte.mean()) * n
        prior = tr["next_up"].mean()
        beat = log_loss(yte, np.full(n, prior), labels=[0, 1]) - log_loss(yte, p, labels=[0, 1])
        beats += beat * n
        ntot += n
    if ntot == 0:
        return None
    return accs / ntot, bases / ntot, beats / ntot, int(ntot)


def run(ticker: str, daily: pd.DataFrame, tfs: list) -> None:
    print("=" * 74)
    print(f"{ticker:6}  {daily.index[0].date()} → {daily.index[-1].date()}")
    for tf in tfs:
        bars = build_bars(daily, tf)
        if bars is None:
            print(f"  {tf}: insufficient bars"); continue
        d = bars[bars["next_candle"].isin(["2U", "2D"])].copy()
        d["next_up"] = (d["next_candle"] == "2U").astype(int)
        print(f"  {tf}  ({len(d)} directional next-bars; held-out per-year logistic)")
        print(f"      {'feature set':<13}{'OOS acc':>9}{'base':>7}{'lift':>7}{'LLbeat':>9}{'Δacc vs FULL':>14}")
        full_acc = None
        for name, feats in SETS.items():
            r = _oos_pooled(d, feats)
            if r is None:
                print(f"      {name:<13} (thin)"); continue
            acc, base, beat, n = r
            if name == "FULL":
                full_acc = acc
            dvs = "" if name == "FULL" else f"{100*(acc-full_acc):+.1f}pp" if full_acc else ""
            print(f"      {name:<13}{100*acc:>8.0f}%{100*base:>6.0f}%{100*(acc-base):>+6.1f}{beat:>+9.3f}{dvs:>14}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--timeframes", default="1d,1w")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    tfs = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print(f"CLV ABLATION — held-out OOS by feature set  {tickers}  TFs={tfs}")
    print("FULL=all · NO_CLV=all−clv · CLV_ONLY=clv · STRUCT_ONLY=momentum+FTFC\n")
    loader = DataLoader()
    for t in tickers:
        daily = loader.load_daily(t)
        if daily is None or len(daily) < 400:
            print(f"{t:6} — UNAVAILABLE"); continue
        try:
            run(t, daily, tfs)
        except Exception as e:
            import traceback
            print(f"{t} ERROR: {e}\n{traceback.format_exc()}")
    print("=" * 74)


if __name__ == "__main__":
    main()
