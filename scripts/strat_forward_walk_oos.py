#!/usr/bin/env python3
"""Held-out forward-walk: is the FTFC+CLV+momentum edge real OUT-OF-SAMPLE?

For each test YEAR Y, train/fit on bars strictly before Y, evaluate on Y only —
so the test year is never used to choose features or fit parameters. Reports, on
the directional next-bars of each held-out year:

  base%     — majority-class (always-guess-the-bigger-side) accuracy on Y
  fixed%    — the fixed rule (≥2 of {CLV>0, ret3d>0, FTFC>0} → UP) on Y
              (no fitted params — pure OOS application)
  logreg%   — a logistic regression FIT on <Y, predicting next-up, tested on Y
              (real parameter held-out) + its log-loss beat vs the train prior

If fixed% / logreg% stay well above base% in every held-out year, the edge is
real, not full-sample flattery.

    python -m scripts.strat_forward_walk_oos --tickers SPY,QQQ,IWM --test-years 2022,2023,2024,2025,2026
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strat_next_candle_analysis import build_daily

FEATS = ["ret_1d", "ret_2d", "ret_3d", "ret_5d", "rsi_14", "ema20_dist",
         "ema50_dist", "macd_hist", "bb_pctb", "vol_z", "clv", "consec_up",
         "consec_dn", "ftfc"]


def analyze(ticker: str, days: int, test_years: list) -> None:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    print("=" * 78)
    df = build_daily(ticker, days)
    if df is None:
        print(f"{ticker:6} — UNAVAILABLE"); return
    df = df.copy()
    df["clv_up"] = (df["clv"].fillna(0) > 0).astype(int)
    df["mom_up"] = (df["ret_3d"].fillna(0) > 0).astype(int)
    df["ftfc_up"] = (df["ftfc"].fillna(0) > 0).astype(int)
    df["up_votes"] = df["clv_up"] + df["mom_up"] + df["ftfc_up"]
    d = df[df["next_candle"].isin(["2U", "2D"])].copy()
    d["next_up"] = (d["next_candle"] == "2U").astype(int)
    d["year"] = pd.DatetimeIndex(d.index).year

    print(f"{ticker:6}  {df.index[0].date()} → {df.index[-1].date()}  "
          f"({len(d)} directional next-bars)")
    print(f"  {'test yr':<8}{'n':>5}{'base%':>7}{'fixed%':>8}{'logreg%':>9}{'logreg_LLbeat':>15}")

    agg = {"n": 0, "base": 0, "fixed": 0, "logreg": 0}
    for Y in test_years:
        tr = d[d["year"] < Y]
        te = d[d["year"] == Y]
        if len(te) < 40 or len(tr) < 250:
            print(f"  {Y:<8}{len(te):>5}   (thin — skipped)")
            continue
        yte = te["next_up"].values
        base_acc = max(yte.mean(), 1 - yte.mean())
        # fixed rule
        fixed_pred = (te["up_votes"] >= 2).astype(int).values
        fixed_acc = (fixed_pred == yte).mean()
        # logistic, fit on <Y
        Xtr = tr[FEATS].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        Xte = te[FEATS].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        clf = LogisticRegression(max_iter=2000, C=0.5)
        clf.fit((Xtr - mu) / sd, tr["next_up"].values)
        proba = clf.predict_proba((Xte - mu) / sd)[:, 1]
        lr_acc = ((proba >= 0.5).astype(int) == yte).mean()
        prior = tr["next_up"].mean()
        ll = log_loss(yte, proba, labels=[0, 1])
        base_ll = log_loss(yte, np.full(len(yte), prior), labels=[0, 1])
        print(f"  {Y:<8}{len(te):>5}{100*base_acc:>6.0f}%{100*fixed_acc:>7.0f}%"
              f"{100*lr_acc:>8.0f}%{base_ll-ll:>+14.3f}")
        agg["n"] += len(te); agg["base"] += base_acc * len(te)
        agg["fixed"] += fixed_acc * len(te); agg["logreg"] += lr_acc * len(te)

    if agg["n"]:
        n = agg["n"]
        print(f"  {'POOLED':<8}{n:>5}{100*agg['base']/n:>6.0f}%"
              f"{100*agg['fixed']/n:>7.0f}%{100*agg['logreg']/n:>8.0f}%")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--days", type=int, default=2200)
    p.add_argument("--test-years", default="2022,2023,2024,2025,2026")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    years = [int(y) for y in args.test_years.split(",")]
    print(f"HELD-OUT FORWARD-WALK — train < Y, test = Y (directional next-bars)\n")
    for t in tickers:
        try:
            analyze(t, args.days, years)
        except Exception as e:
            import traceback
            print(f"{t:6} — ERROR: {e}\n{traceback.format_exc()}")
    print("=" * 78)


if __name__ == "__main__":
    main()
