#!/usr/bin/env python3
"""Costed underlying backtest of the STRUCTURAL (momentum + FTFC) next-bar signal.

Background (E-25 / STRAT-NEXTBAR): the next-bar directional edge is dominated by
close-location (CLV), which is partly MECHANICAL (a strong close puts the next
open near the high, so a 2U is easier to print). The genuinely non-mechanical
residual is momentum (ret_1/2/3) + FTFC — the STRUCT_ONLY set in the CLV
ablation, which beat base by ~+6-13pp held-out. But "predicts which trigger
breaks (2U/2D)" is NOT the same as "makes money close-to-close." This script
takes that structural residual to a REAL underlying backtest WITH costs to test
tradeability.

Separate, additive, reproducible: imports build_bars + FEATS READ-ONLY from
strat_oos_multi_tf. Does NOT modify any existing script or its results.

Method (held-out, no lookahead):
  * Per test year Y, fit a logistic P(next_up) on bars strictly BEFORE Y for the
    chosen feature set, predict on year Y.
  * Trade the UNDERLYING on the directional view:
        long  if p >= 0.5 + band
        short if p <= 0.5 - band
        flat  otherwise
  * Holding modes:
        oc  enter next_open, exit next_close  (DEFAULT — honest: you act after
            seeing bar-T's close, so you enter at the NEXT open; the open-gap is
            NOT capturable. This is where a mechanical CLV signal should die.)
        cc  enter bar-T close, exit next_close (captures the overnight gap; an
            upper bound that rewards close-execution).
  * Costs: --slippage-bps charged PER SIDE (round-trip = 2x) on every non-flat
    trade. ETF commissions ≈ 0.
  * Per-trade P&L reported in % and ATR-20 units; pooled net Sharpe annualized by
    trades/year; compared head-to-head across STRUCT / FULL / CLV_ONLY and vs a
    buy-and-hold benchmark on the same test bars.

Read: if STRUCT nets positive after costs in 'oc' mode while CLV_ONLY does NOT,
the structural residual is tradeable and the CLV edge was mechanical (un-
tradeable once you enter at the open). If neither nets positive, the next-bar
edge predicts structure but not close-to-close P&L (exits must be managed).

    python -m scripts.strat_struct_backtest --tickers SPY,QQQ,IWM \
        --timeframes 1d,1w --hold oc --slippage-bps 2 --band 0.05
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
    "STRUCT":   ["ret_1", "ret_2", "ret_3", "ftfc"],
    "FULL":     FEATS,
    "CLV_ONLY": ["clv"],
}


def _atr20(bars: pd.DataFrame) -> pd.Series:
    h, l, c = bars["High"], bars["Low"], bars["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(20).mean()


def _backtest(d: pd.DataFrame, feats: list, hold: str, slip: float,
              band: float) -> dict | None:
    """Held-out per-year logistic → directional underlying trades → net P&L.

    slip is a fraction per side (bps/1e4). Returns pooled stats or None if no
    scorable folds."""
    from sklearn.linear_model import LogisticRegression
    d = d.copy()
    d["year"] = pd.DatetimeIndex(d.index).year
    recs = []
    for Y in sorted(d["year"].unique()):
        tr, te = d[d["year"] < Y], d[d["year"] == Y]
        if len(te) < 25 or len(tr) < 120:
            continue
        if len(np.unique(tr["next_up"].values)) < 2:
            continue
        Xtr = tr[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        Xte = te[feats].replace([np.inf, -np.inf], np.nan).fillna(0.0).values
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        clf = LogisticRegression(max_iter=2000, C=0.5)
        clf.fit((Xtr - mu) / sd, tr["next_up"].values)
        p = clf.predict_proba((Xte - mu) / sd)[:, 1]
        pos = np.where(p >= 0.5 + band, 1.0, np.where(p <= 0.5 - band, -1.0, 0.0))
        if hold == "oc":
            entry, exitp = te["next_open"].values, te["next_close"].values
        else:  # cc
            entry, exitp = te["cur_close"].values, te["next_close"].values
        with np.errstate(divide="ignore", invalid="ignore"):
            gross = pos * (exitp / entry - 1.0)
        cost = np.abs(pos) * 2.0 * slip
        net = gross - cost
        atr_pct = (te["atr20"].values / entry)
        for i in range(len(te)):
            if pos[i] == 0.0 or not np.isfinite(gross[i]):
                continue
            recs.append({
                "year": Y, "gross": gross[i], "net": net[i],
                "win": 1 if net[i] > 0 else 0,
                "net_atr": net[i] / atr_pct[i] if atr_pct[i] and np.isfinite(atr_pct[i]) else np.nan,
                "bench": exitp[i] / entry[i] - 1.0,  # buy-and-hold this bar
            })
    if not recs:
        return None
    r = pd.DataFrame(recs)
    n_years = r["year"].nunique()
    trades_per_year = len(r) / max(n_years, 1)
    net_mean, net_std = r["net"].mean(), r["net"].std(ddof=1)
    sharpe = (net_mean / net_std * np.sqrt(trades_per_year)) if net_std > 0 else np.nan
    # per-year net for a stability read
    by_year = r.groupby("year")["net"].sum()
    return {
        "n_trades": len(r),
        "hit": float(r["win"].mean()),
        "gross_bps": float(r["gross"].mean() * 1e4),
        "net_bps": float(r["net"].mean() * 1e4),
        "net_atr": float(r["net_atr"].mean(skipna=True)),
        "cum_net": float(r["net"].sum()),
        "bench_bps": float(r["bench"].mean() * 1e4),
        "sharpe": float(sharpe) if np.isfinite(sharpe) else float("nan"),
        "pos_years": int((by_year > 0).sum()),
        "tot_years": int(n_years),
    }


def run(ticker: str, daily: pd.DataFrame, tfs: list, hold: str, slip_bps: float,
        band: float) -> None:
    slip = slip_bps / 1e4
    print("=" * 96)
    print(f"{ticker:6}  {daily.index[0].date()} → {daily.index[-1].date()}  "
          f"hold={hold}  slip={slip_bps}bps/side  band=±{band}")
    for tf in tfs:
        bars = build_bars(daily, tf)
        if bars is None:
            print(f"  {tf}: insufficient bars"); continue
        bars = bars.copy()
        bars["cur_close"] = bars["Close"]
        bars["next_open"] = bars["Open"].shift(-1)
        bars["next_close"] = bars["Close"].shift(-1)
        bars["atr20"] = _atr20(bars)
        d = bars[bars["next_candle"].isin(["2U", "2D"])].copy()
        d["next_up"] = (d["next_candle"] == "2U").astype(int)
        d = d[d["next_open"].notna() & d["next_close"].notna()
              & (d["next_open"] > 0) & d["atr20"].notna()].copy()
        print(f"  {tf}  ({len(d)} directional next-bars)")
        print(f"      {'set':<10}{'trades':>7}{'hit%':>6}{'gross_bps':>10}"
              f"{'net_bps':>9}{'net_ATR':>9}{'cum_net':>9}{'bench_bps':>10}"
              f"{'Sharpe':>8}{'+yrs':>7}")
        for name, feats in SETS.items():
            s = _backtest(d, feats, hold, slip, band)
            if s is None:
                print(f"      {name:<10} (thin)"); continue
            print(f"      {name:<10}{s['n_trades']:>7}{100*s['hit']:>5.0f}%"
                  f"{s['gross_bps']:>+10.1f}{s['net_bps']:>+9.1f}"
                  f"{s['net_atr']:>+9.3f}{100*s['cum_net']:>+8.1f}%"
                  f"{s['bench_bps']:>+10.1f}{s['sharpe']:>8.2f}"
                  f"{s['pos_years']:>4}/{s['tot_years']:<2}")
        print()
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--timeframes", default="1d,1w")
    p.add_argument("--hold", default="oc", choices=["oc", "cc"],
                   help="oc=next_open→next_close (gap NOT capturable, honest); "
                        "cc=cur_close→next_close (captures overnight gap).")
    p.add_argument("--slippage-bps", type=float, default=2.0,
                   help="slippage charged PER SIDE (round-trip = 2x).")
    p.add_argument("--band", type=float, default=0.05,
                   help="trade only when |p-0.5| >= band (else flat).")
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    tfs = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print("STRUCTURAL-RESIDUAL COSTED UNDERLYING BACKTEST — held-out per-year")
    print(f"  {tickers}  TFs={tfs}  hold={args.hold}  "
          f"slip={args.slippage_bps}bps/side  band=±{args.band}")
    print("STRUCT=momentum(ret1/2/3)+FTFC · FULL=all feats · CLV_ONLY=clv.")
    print("Net P&L of trading the UNDERLYING on P(next_up); bench=buy-hold same bars.\n")
    loader = DataLoader()
    for t in tickers:
        daily = loader.load_daily(t)
        if daily is None or len(daily) < 400:
            print(f"{t:6} — UNAVAILABLE"); continue
        try:
            run(t, daily, tfs, args.hold, args.slippage_bps, args.band)
        except Exception as e:
            import traceback
            print(f"{t} ERROR: {e}\n{traceback.format_exc()}")
    print("=" * 96)
    print("⚠️  Underlying close-to-close (or open-to-close) P&L with linear "
          "slippage. No theta/borrow; ETF commission ≈ 0. Directional-only "
          "(no PT/SL barrier — that's BREAKOUT-META's job).")


if __name__ == "__main__":
    main()
