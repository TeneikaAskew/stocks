#!/usr/bin/env python3
"""Strat backtest — classification correctness, follow-through, and the
NEXT-BAR belief (transition distribution).

PART 1 — CLASSIFICATION CORRECTNESS (not a forecast): the daily candle is a
  deterministic label of a bar that already printed. Confirmed RIGHT by comparing
  to market_data_daily.strat_candle (production). It's implementation-correct, not
  "prediction accuracy."

PART 2 — FOLLOW-THROUGH: when a bull/bear combo fired on bar T, did T+1 actually
  go that way (break the trigger + close in that direction), vs the unconditional
  baseline.

PART 3 — NEXT-BAR BELIEF: P(next candle | current candle/combo) over the window —
  "given all bars so far, will the next bar continue / reverse / stay inside /
  expand outside, and how often." Applied to the latest bar = the forward belief.

    python -m scripts.strat_backtest --tickers SPY,QQQ,IWM --days 252
"""
from __future__ import annotations
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.strat import compute_strat_history
from gcp.database import get_engine


def _persisted_candles(engine, ticker: str) -> dict:
    try:
        from sqlalchemy import text
        sql = text("SELECT date, strat_candle FROM market_data_daily "
                   "WHERE ticker = :t AND strat_candle IS NOT NULL")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={"t": ticker})
        df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
        return dict(zip(df["date"], df["strat_candle"].astype(str)))
    except Exception as e:
        print(f"    (persisted cross-check unavailable: {e})")
        return {}


def backtest_ticker(engine, ticker: str, days: int) -> None:
    res = compute_strat_history(ticker, timeframes=["1d"], lookback=days + 1)
    print("=" * 76)
    if not res.get("available") or not res["timeframes"].get("1d", {}).get("available"):
        print(f"{ticker:6} — UNAVAILABLE"); return
    hist = res["timeframes"]["1d"]["history"]
    print(f"{ticker:6}  {hist[0]['period']} → {hist[-1]['period']}  ({len(hist)} sessions)")

    # ── PART 1: classification correctness vs production ───────────────────
    persisted = _persisted_candles(engine, ticker)
    if persisted:
        checked = matched = 0
        mism = []
        for b in hist:
            if b["candle"] == "X":
                continue
            p = persisted.get(b["period"])
            if p is None:
                continue
            checked += 1
            if p == b["candle"]:
                matched += 1
            elif len(mism) < 3:
                mism.append(f"{b['period']} engine={b['candle']} prod={p}")
        if checked:
            print(f"  PART 1 classification vs production: {matched}/{checked} "
                  f"({100*matched/checked:.1f}%) match"
                  + (f"  e.g. {mism}" if mism else ""))
    else:
        print("  PART 1 classification vs production: (no persisted labels)")

    # ── PART 2: follow-through of fired combos ─────────────────────────────
    base_up = base_dn = base_n = 0
    fam = defaultdict(lambda: {"n": 0, "broke": 0, "closed": 0})
    for i in range(len(hist) - 1):
        cur, nxt = hist[i], hist[i + 1]
        if None in (cur["high"], cur["low"], cur["close"], nxt["high"], nxt["low"], nxt["close"]):
            continue
        base_n += 1
        base_up += int(nxt["high"] > cur["high"])
        base_dn += int(nxt["low"] < cur["low"])
        combo = cur["combo"] or "none"
        if "bull" in combo:
            key = "bull_continuation" if "continuation" in combo else \
                  ("bull_reversal" if "reversal" in combo else "bull_other")
            d = fam[key]; d["n"] += 1
            d["broke"] += int(nxt["high"] > cur["high"])
            d["closed"] += int(nxt["close"] > cur["close"])
        elif "bear" in combo:
            key = "bear_continuation" if "continuation" in combo else \
                  ("bear_reversal" if "reversal" in combo else "bear_other")
            d = fam[key]; d["n"] += 1
            d["broke"] += int(nxt["low"] < cur["low"])
            d["closed"] += int(nxt["close"] < cur["close"])

    if base_n:
        print(f"  baseline: next bar breaks UP {100*base_up/base_n:.0f}% / "
              f"DOWN {100*base_dn/base_n:.0f}%  (n={base_n})")
    print("  PART 2 follow-through (combo fired on T → did T+1 go that way?):")
    print(f"    {'combo family':<20}{'n':>5}{'broke-trigger':>15}{'closed-dir':>13}")
    for key in ("bull_continuation", "bull_reversal", "bear_continuation", "bear_reversal"):
        d = fam.get(key)
        if not d or d["n"] == 0:
            continue
        print(f"    {key:<20}{d['n']:>5}{100*d['broke']/d['n']:>13.0f}% "
              f"{100*d['closed']/d['n']:>11.0f}%")

    # ── PART 3: NEXT-BAR belief ────────────────────────────────────────────
    trans = defaultdict(lambda: defaultdict(int))
    combo_trans = defaultdict(lambda: defaultdict(int))
    for i in range(len(hist) - 1):
        cc, nc = hist[i]["candle"], hist[i + 1]["candle"]
        if cc == "X" or nc == "X":
            continue
        trans[cc][nc] += 1
        combo_trans[hist[i]["combo"] or "none"][nc] += 1

    print("  PART 3 next-bar distribution  P(next | current candle):")
    print(f"    {'current':<9}{'→ 2U':>7}{'2D':>7}{'1':>7}{'3':>7}    n")
    for cc in ("2U", "2D", "1", "3"):
        row = trans.get(cc, {})
        tot = sum(row.values())
        if not tot:
            continue
        print(f"    {cc:<9}" + "".join(f"{100*row.get(x,0)/tot:>6.0f}%" for x in ("2U", "2D", "1", "3")) + f"  {tot:>5}")

    cur = hist[-1]
    cc = cur["candle"]; combo = cur["combo"] or "none"

    def _belief(counts: dict, cur_candle: str) -> str:
        tot = sum(counts.values())
        if not tot:
            return "no historical samples"
        parts = []
        for nxt in ("2U", "2D", "1", "3"):
            n = counts.get(nxt, 0)
            if n == 0:
                continue
            if nxt == "1":
                lbl = "inside/stay"
            elif nxt == "3":
                lbl = "outside/expand"
            elif cur_candle == "2U":
                lbl = "CONTINUATION (2U)" if nxt == "2U" else "reversal (2D)"
            elif cur_candle == "2D":
                lbl = "CONTINUATION (2D)" if nxt == "2D" else "reversal (2U)"
            else:
                lbl = nxt
            parts.append(f"{lbl} {100*n/tot:.0f}%")
        return " | ".join(parts) + f"   (n={tot})"

    print(f"  → CURRENT state: last bar {cc}  ({combo}); upcoming-bar belief:")
    print(f"      by candle ({cc}):  {_belief(trans.get(cc, {}), cc)}")
    if combo != "none" and sum(combo_trans.get(combo, {}).values()) >= 10:
        print(f"      by combo  ({combo}):  {_belief(combo_trans.get(combo, {}), cc)}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--days", type=int, default=252)
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    engine = get_engine()
    print(f"STRAT BACKTEST — {len(tickers)} tickers, last {args.days} sessions")
    print("broke-trigger = T+1 took out T's high(bull)/low(bear); "
          "closed-dir = T+1 closed in the combo's direction.\n")
    for t in tickers:
        try:
            backtest_ticker(engine, t, args.days)
        except Exception as e:
            print(f"{t:6} — ERROR: {e}")
    print("=" * 76)


if __name__ == "__main__":
    main()
