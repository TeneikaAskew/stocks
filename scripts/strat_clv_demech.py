#!/usr/bin/env python3
"""De-mechanize CLV — isolate the GENUINE close-location edge from the partly
MECHANICAL close→next-open effect.

Background (E-25 / STRAT-NEXTBAR): the held-out next-bar edge (~70% daily,
~75-80% weekly) is dominated by close-location-value (CLV). Part of that is
mechanical: a strong close (CLV→+1) puts the next OPEN near the current HIGH, so
a higher-high (2U) is mechanically easier to print — without any genuine
predictive content. This script quantifies how much of the CLV edge survives two
de-mechanizing transforms.

Separate, additive, reproducible: imports build_bars + FEATS READ-ONLY from
strat_oos_multi_tf. Does NOT modify any existing CLV / ablation script or its
results — the old scripts reproduce their numbers unchanged.

Two de-mechanizing levers, run as a 2-target × N-feature-set grid:

  TARGETS
    next_up         next Strat candle 2U vs 2D  (= next_high>cur_high vs
                    next_low<cur_low). This is the ORIGINAL target and is the
                    one the opening gap mechanically helps.
    next_intrabar   next_close > next_open. GAP-NEUTRAL: measured entirely
                    inside the next bar, so the open-gap from a strong close
                    gives NO free advantage. CLV lift here is genuine momentum.

  FEATURE SETS
    FULL            all FEATS (incl. current-bar clv)         — inflated reference
    CLV_NOW         current-bar clv alone                     — the suspect signal
    CLV_LAG1        PRIOR-bar clv alone (clv.shift(1))        — close-location that
                    cannot mechanically set the next open (a full bar intervenes)
    NO_CLV          all FEATS except clv                      — non-CLV residual
    STRUCT_ONLY     momentum (ret_1/2/3) + FTFC               — pure structural

How to read it:
  * If CLV_NOW has a big lift on next_up but its lift COLLAPSES toward base on
    next_intrabar, the CLV edge is largely MECHANICAL (it only helps break the
    prior high via the gap; it does not predict the next bar's own direction).
  * If CLV_LAG1 retains lift on BOTH targets, there is GENUINE close-location
    persistence beyond the mechanical open-gap.

    python -m scripts.strat_clv_demech --tickers SPY,QQQ,IWM --timeframes 1d,1w
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

# Feature sets. CLV_LAG1 is injected as a derived column 'clv_lag1' in run().
SETS = {
    "FULL":        FEATS,
    "CLV_NOW":     ["clv"],
    "CLV_LAG1":    ["clv_lag1"],
    "NO_CLV":      [f for f in FEATS if f != "clv"],
    "STRUCT_ONLY": ["ret_1", "ret_2", "ret_3", "ftfc"],
}

TARGETS = ("next_up", "next_intrabar")


def _oos_pooled(d: pd.DataFrame, feats: list, target: str) -> tuple | None:
    """Per-year held-out logistic; return (pooled_acc, pooled_base, LLbeat, n).

    Train strictly before each test year (no lookahead). Identical fold logic to
    strat_oos_clv_ablation._oos_pooled, parameterized on the target column."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    d = d.copy()
    d["year"] = pd.DatetimeIndex(d.index).year
    accs = bases = beats = ntot = 0.0
    for Y in sorted(d["year"].unique()):
        tr, te = d[d["year"] < Y], d[d["year"] == Y]
        if len(te) < 25 or len(tr) < 120:
            continue
        ytr, yte = tr[target].values, te[target].values
        if len(np.unique(ytr)) < 2:        # need both classes to fit
            continue
        Xtr = tr[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        Xte = te[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        clf = LogisticRegression(max_iter=2000, C=0.5)
        clf.fit((Xtr - mu) / sd, ytr)
        p = clf.predict_proba((Xte - mu) / sd)[:, 1]
        n = len(te)
        accs += ((p >= 0.5).astype(int) == yte).mean() * n
        bases += max(yte.mean(), 1 - yte.mean()) * n
        prior = ytr.mean()
        beats += (log_loss(yte, np.full(n, prior), labels=[0, 1])
                  - log_loss(yte, p, labels=[0, 1])) * n
        ntot += n
    if ntot == 0:
        return None
    return accs / ntot, bases / ntot, beats / ntot, int(ntot)


def run(ticker: str, daily: pd.DataFrame, tfs: list) -> None:
    print("=" * 86)
    print(f"{ticker:6}  {daily.index[0].date()} → {daily.index[-1].date()}")
    for tf in tfs:
        bars = build_bars(daily, tf)
        if bars is None:
            print(f"  {tf}: insufficient bars"); continue
        # Derived columns (additive; do not mutate build_bars output contract).
        bars = bars.copy()
        bars["clv_lag1"] = bars["clv"].shift(1)
        nxt_open = bars["Open"].shift(-1)
        nxt_close = bars["Close"].shift(-1)
        bars["next_intrabar"] = (nxt_close > nxt_open).astype("Int64")
        # Same row population for BOTH targets: directional (2U/2D) next-bars.
        d = bars[bars["next_candle"].isin(["2U", "2D"])].copy()
        d["next_up"] = (d["next_candle"] == "2U").astype(int)
        d = d[d["next_intrabar"].notna()].copy()
        d["next_intrabar"] = d["next_intrabar"].astype(int)
        print(f"  {tf}  ({len(d)} directional next-bars; held-out per-year logistic)")
        for target in TARGETS:
            tname = "next_up (2U/2D — gap-aided)" if target == "next_up" \
                else "next_intrabar (next_close>next_open — GAP-NEUTRAL)"
            print(f"    target = {tname}")
            print(f"      {'feature set':<13}{'OOS acc':>9}{'base':>7}{'lift':>7}{'LLbeat':>9}")
            for name, feats in SETS.items():
                r = _oos_pooled(d, feats, target)
                if r is None:
                    print(f"      {name:<13} (thin)"); continue
                acc, base, beat, n = r
                print(f"      {name:<13}{100*acc:>8.0f}%{100*base:>6.0f}%"
                      f"{100*(acc-base):>+6.1f}{beat:>+9.3f}")
        print()
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--timeframes", default="1d,1w")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    tfs = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print("CLV DE-MECHANIZATION — held-out OOS, 2 targets × feature sets  "
          f"{tickers}  TFs={tfs}")
    print("Mechanical effect: strong close → next open near high → 2U easier.")
    print("GAP-NEUTRAL target (next_close>next_open) removes that free advantage;")
    print("CLV_LAG1 = prior-bar close-location (cannot set the next open).\n")
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
    print("=" * 86)


if __name__ == "__main__":
    main()
