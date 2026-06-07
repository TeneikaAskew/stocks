#!/usr/bin/env python3
"""Forward-walk: stack FTFC + CLV + momentum, count hits, show the day-to-day call.

Answers, on real daily bars from Cloud SQL:
  PART 1 — does stacking FTFC → +CLV → +momentum SHARPEN the next-bar up/down edge?
           (P(next bar is 2U) as we add agreeing conditions, vs baseline.)
  PART 2 — FORWARD-WALK hit count: predict each day's next directional bar, how
           many predicted, how many correct, accuracy vs baseline.
  PART 3 — DAY-TO-DAY: the last N sessions as you'd have seen them — "given this
           close, the call for the next session was X; it actually did Y (✓/✗)"
           + the live call for the next session.

All causal: every feature is known at bar T's close; the prediction is for T+1.

    python -m scripts.strat_forward_walk --tickers SPY,QQQ,IWM --recent 12
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.strat_next_candle_analysis import build_daily


def _votes(row) -> tuple:
    """Three causal UP-votes at bar T: closed upper-half (CLV>0), 3-day momentum
    up, and higher-TF (FTFC weekly+monthly) up. Returns (clv_up, mom_up, ftfc_up)."""
    clv = row.get("clv"); r3 = row.get("ret_3d"); ft = row.get("ftfc")
    clv_up = 1 if (pd.notna(clv) and clv > 0) else 0
    mom_up = 1 if (pd.notna(r3) and r3 > 0) else 0
    ftfc_up = 1 if (pd.notna(ft) and ft > 0) else 0
    return clv_up, mom_up, ftfc_up


def analyze(ticker: str, days: int, recent: int) -> None:
    print("=" * 84)
    df = build_daily(ticker, days)
    if df is None:
        print(f"{ticker:6} — UNAVAILABLE"); return
    df = df.copy()
    v = df.apply(_votes, axis=1, result_type="expand")
    df["clv_up"], df["mom_up"], df["ftfc_up"] = v[0], v[1], v[2]
    df["up_votes"] = df["clv_up"] + df["mom_up"] + df["ftfc_up"]

    # restrict to bars whose NEXT candle is directional (2U/2D) — the up/down call
    d = df[df["next_candle"].isin(["2U", "2D"])].copy()
    d["next_up"] = (d["next_candle"] == "2U").astype(int)
    n_all = df["next_candle"].notna().sum()
    print(f"{ticker:6}  {df.index[0].date()} → {df.index[-1].date()}  "
          f"({len(df)} sessions; {len(d)} have a directional next bar = "
          f"{100*len(d)/max(n_all,1):.0f}% of days)")

    base_up = d["next_up"].mean()
    print(f"  PART 1 — does stacking sharpen the edge?  (baseline P(next=2U)={100*base_up:.0f}%)")

    def rate(mask, want_up=True):
        g = d[mask]
        if len(g) < 20:
            return None, len(g)
        return (g["next_up"].mean() if want_up else (1 - g["next_up"]).mean()), len(g)

    print("    UP stack — P(next = 2U):")
    for label, m in (("FTFC up", d["ftfc_up"] == 1),
                     ("FTFC + CLV up", (d["ftfc_up"] == 1) & (d["clv_up"] == 1)),
                     ("FTFC + CLV + mom up", d["up_votes"] == 3)):
        r, n = rate(m, True)
        print(f"      {label:<22} {'%2.0f%%' % (100*r) if r is not None else ' thin':>6}  (n={n})")
    print("    DOWN stack — P(next = 2D):")
    for label, m in (("FTFC down", d["ftfc_up"] == 0),
                     ("FTFC + CLV down", (d["ftfc_up"] == 0) & (d["clv_up"] == 0)),
                     ("FTFC + CLV + mom down", d["up_votes"] == 0)):
        r, n = rate(m, False)
        print(f"      {label:<22} {'%2.0f%%' % (100*r) if r is not None else ' thin':>6}  (n={n})")

    # PART 2 — forward-walk hit count
    pred_up = d["up_votes"] >= 2          # 2-or-3 votes → predict UP, else DOWN
    correct = (pred_up == d["next_up"].astype(bool))
    acc = correct.mean()
    hi = d[d["up_votes"].isin([0, 3])]    # high-conviction (unanimous)
    hi_pred_up = hi["up_votes"] == 3
    hi_corr = (hi_pred_up == hi["next_up"].astype(bool))
    print("  PART 2 — FORWARD-WALK (rule: ≥2 up-votes → predict UP, else DOWN):")
    print(f"      predicted {len(d)} directional next-bars; correct {int(correct.sum())} "
          f"({100*acc:.1f}%)  vs baseline {100*max(base_up,1-base_up):.1f}%")
    if len(hi) >= 20:
        print(f"      HIGH-CONVICTION (unanimous 3/3 or 0/3): {len(hi)} bars; "
              f"correct {int(hi_corr.sum())} ({100*hi_corr.mean():.1f}%)")

    # PART 3 — day-to-day log + live next-session call
    print(f"  PART 3 — last {recent} sessions as you'd have seen them "
          f"(close on T → call for T+1 → actual):")
    print(f"    {'date(T)':<12}{'cand':<5}{'CLV':>6}{'ret3d':>8}{'FTFC':>6}"
          f"{'votes':>6}{'CALL':>6}   {'T+1':<6}{'result'}")
    tail = df[df["next_candle"].notna()].tail(recent)
    for idx, r in tail.iterrows():
        votes = int(r["up_votes"])
        call = "UP" if votes >= 2 else "DOWN"
        nxt = r["next_candle"]
        if nxt in ("2U", "2D"):
            hit = (call == "UP" and nxt == "2U") or (call == "DOWN" and nxt == "2D")
            res = "✓" if hit else "✗"
        else:
            res = f"{nxt} (non-dir)"
        clv = r.get("clv"); r3 = r.get("ret_3d")
        print(f"    {str(idx.date()):<12}{r['candle']:<5}"
              f"{(('%+.2f'%clv) if pd.notna(clv) else '  —'):>6}"
              f"{(('%+.1f%%'%(100*r3)) if pd.notna(r3) else '   —'):>8}"
              f"{int(r['ftfc']):>6}{votes:>6}{call:>6}   {nxt:<6}{res}")
    # live call: the latest bar has no next yet
    last = df.iloc[-1]
    votes = int(last["up_votes"])
    call = "UP (expect 2U)" if votes >= 2 else "DOWN (expect 2D)"
    print(f"    → LIVE CALL for the session after {df.index[-1].date()} "
          f"(last bar {last['candle']}): votes={votes}/3 → {call}  "
          f"[CLV={last.get('clv'):+.2f}, ret3d={100*last.get('ret_3d'):+.1f}%, FTFC={int(last['ftfc'])}]")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--days", type=int, default=2000)
    p.add_argument("--recent", type=int, default=12)
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    print(f"STRAT FORWARD-WALK — {len(tickers)} tickers, {args.days} sessions\n")
    for t in tickers:
        try:
            analyze(t, args.days, args.recent)
        except Exception as e:
            import traceback
            print(f"{t:6} — ERROR: {e}\n{traceback.format_exc()}")
    print("=" * 84)


if __name__ == "__main__":
    main()
