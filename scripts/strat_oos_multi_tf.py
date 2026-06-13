#!/usr/bin/env python3
"""Held-out OOS forward-walk across TIMEFRAMES (daily / weekly / monthly).

Generalises the daily held-out test (scripts/strat_forward_walk_oos.py) to higher
timeframes: resample daily bars up to each TF, build TF-agnostic features
(returns, RSI, close-location, EMA distance, streaks) + FTFC from the next-higher
TFs (causal, prior-completed), classify the next TF candle, and run a held-out
test (train strictly before the test window).

Daily & weekly have enough bars for per-YEAR held-out folds; monthly is thin so a
single 65/35 train/test split is used (reported with the small-N caveat).

    python -m scripts.strat_oos_multi_tf --tickers SPY,QQQ,IWM --timeframes 1d,1w,1mo
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_loader import DataLoader
from lib.strat import StratClassifier

HIGHER = {"1d": ["1w", "1mo"], "1w": ["1mo", "1q"], "1mo": ["1q"]}
FEATS = ["ret_1", "ret_2", "ret_3", "rsi_14", "clv", "ema10_dist",
         "ema20_dist", "range_pct", "consec_up", "consec_dn", "ftfc"]


def _candle_dir(s: pd.Series) -> pd.Series:
    return s.map({"2U": 1, "2D": -1}).fillna(0)


def _ftfc(daily: pd.DataFrame, bar_index: pd.DatetimeIndex, higher_tfs: list) -> pd.Series:
    loader, clf = DataLoader(), StratClassifier()
    out = pd.Series(0.0, index=bar_index)
    ohlcv = daily[["Open", "High", "Low", "Close"]].copy()
    ohlcv["Volume"] = daily["Volume"] if "Volume" in daily.columns else 0.0
    for tf in higher_tfs:
        try:
            agg = loader.aggregate_to_timeframe(ohlcv, tf).dropna(subset=["High", "Low"])
            dirs = _candle_dir(clf.classify_series(agg))
            right = pd.DataFrame({"htf": agg.index, "dir": dirs.values}).sort_values("htf")
            left = pd.DataFrame({"date": bar_index}).sort_values("date")
            m = pd.merge_asof(left, right, left_on="date", right_on="htf",
                              direction="backward", allow_exact_matches=False)
            out = out + pd.Series(m["dir"].fillna(0).values, index=bar_index)
        except Exception:
            continue
    return out


def build_bars(daily: pd.DataFrame, tf: str) -> pd.DataFrame:
    loader, clf = DataLoader(), StratClassifier()
    if "Volume" not in daily.columns:
        daily = daily.assign(Volume=0.0)
    bars = daily if tf == "1d" else loader.aggregate_to_timeframe(
        daily[["Open", "High", "Low", "Close", "Volume"]], tf)
    bars = bars.dropna(subset=["High", "Low", "Close"]).copy()
    if len(bars) < 80:
        return None
    c, h, l = bars["Close"], bars["High"], bars["Low"]
    bars["candle"] = clf.classify_series(bars).values
    bars["next_candle"] = bars["candle"].shift(-1)
    f = pd.DataFrame(index=bars.index)
    for n in (1, 2, 3):
        f[f"ret_{n}"] = c.pct_change(n)
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean(); dn = (-delta.clip(upper=0)).rolling(14).mean()
    f["rsi_14"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    f["clv"] = ((c - l) - (h - c)) / (h - l).replace(0, np.nan)
    for n in (10, 20):
        f[f"ema{n}_dist"] = (c - c.ewm(span=n, adjust=False).mean()) / c
    f["range_pct"] = (h - l) / c
    prev_c = c.shift(1)
    ud = (c > prev_c).astype(int)
    f["consec_up"] = ud * (ud.groupby((ud != ud.shift()).cumsum()).cumcount() + 1)
    dd = (c < prev_c).astype(int)
    f["consec_dn"] = dd * (dd.groupby((dd != dd.shift()).cumsum()).cumcount() + 1)
    f["ftfc"] = _ftfc(daily, bars.index, HIGHER.get(tf, []))
    return pd.concat([bars, f], axis=1)


def _eval(tr, te):
    """(base%, fixed%, logreg%, logreg_LLbeat) on a train/test split of directional bars."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    yte = te["next_up"].values
    base = max(yte.mean(), 1 - yte.mean())
    votes = (te["clv"].fillna(0) > 0).astype(int) + (te["ret_3"].fillna(0) > 0).astype(int) + (te["ftfc"].fillna(0) > 0).astype(int)
    fixed = ((votes >= 2).astype(int).values == yte).mean()
    Xtr = tr[FEATS].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    Xte = te[FEATS].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    clf = LogisticRegression(max_iter=2000, C=0.5)
    clf.fit((Xtr - mu) / sd, tr["next_up"].values)
    p = clf.predict_proba((Xte - mu) / sd)[:, 1]
    lr = ((p >= 0.5).astype(int) == yte).mean()
    prior = tr["next_up"].mean()
    beat = log_loss(yte, np.full(len(yte), prior), labels=[0, 1]) - log_loss(yte, p, labels=[0, 1])
    return base, fixed, lr, beat, len(te)


def run_tf(ticker: str, daily: pd.DataFrame, tf: str) -> None:
    bars = build_bars(daily, tf)
    if bars is None:
        print(f"  {tf:<4} — insufficient bars"); return
    d = bars[bars["next_candle"].isin(["2U", "2D"])].copy()
    d["next_up"] = (d["next_candle"] == "2U").astype(int)
    d["year"] = pd.DatetimeIndex(d.index).year
    per_year = d.groupby("year").size().median() >= 25
    print(f"  {tf:<4} {len(d)} directional next-bars  "
          f"({'per-year held-out' if per_year else 'single 65/35 split (thin)'})")
    print(f"      {'fold':<10}{'n':>5}{'base%':>7}{'fixed%':>8}{'logreg%':>9}{'LLbeat':>9}")
    rows = []
    if per_year:
        for Y in sorted(d["year"].unique()):
            tr, te = d[d["year"] < Y], d[d["year"] == Y]
            if len(te) < 25 or len(tr) < 120:
                continue
            rows.append((str(Y), *_eval(tr, te)))
    else:
        cut = int(len(d) * 0.65)
        tr, te = d.iloc[:cut], d.iloc[cut:]
        if len(te) >= 20 and len(tr) >= 50:
            rows.append((f"{d.index[cut].date()}+", *_eval(tr, te)))
    if not rows:
        print("      (no scorable folds)"); return
    tot = sum(r[5] for r in rows)
    for lbl, base, fixed, lr, beat, n in rows:
        print(f"      {lbl:<10}{n:>5}{100*base:>6.0f}%{100*fixed:>7.0f}%{100*lr:>8.0f}%{beat:>+9.3f}")
    wb = sum(r[1]*r[5] for r in rows)/tot; wf = sum(r[2]*r[5] for r in rows)/tot; wl = sum(r[3]*r[5] for r in rows)/tot
    print(f"      {'POOLED':<10}{tot:>5}{100*wb:>6.0f}%{100*wf:>7.0f}%{100*wl:>8.0f}%")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--timeframes", default="1d,1w,1mo")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    tfs = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print(f"HELD-OUT OOS BY TIMEFRAME — {tickers}  TFs={tfs}\n")
    loader = DataLoader()
    for t in tickers:
        print("=" * 70)
        daily = loader.load_daily(t)
        if daily is None or len(daily) < 300:
            print(f"{t:6} — UNAVAILABLE"); continue
        print(f"{t:6}  {daily.index[0].date()} → {daily.index[-1].date()}")
        for tf in tfs:
            try:
                run_tf(t, daily, tf)
            except Exception as e:
                import traceback
                print(f"  {tf} ERROR: {e}\n{traceback.format_exc()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
