#!/usr/bin/env python3
"""Strat history + forward-walk report — runs the backend against Cloud SQL.

Prints, per ticker: the past-week DAILY Strat tape with each day's realized
NEXT-day outcome (a causal forward-walk of the deterministic rules — no
lookahead), the weekly/monthly/quarterly current classification, and the
in-progress UPCOMING break setup. Pure rules (lib.strat.compute_strat_history).

Dispatched as the magnitude-engine Cloud Run Job (research image) it reads
market_data_daily over the Cloud SQL connector and emits to Cloud Logging.

    python -m scripts.strat_history_report --tickers SPY,QQQ,IWM --days 7
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.strat import compute_strat_history

_BREAK = {"2U": "broke ↑ high", "2D": "broke ↓ low", "3": "broke BOTH (outside)",
          "1": "held inside", "X": "—"}


def _fwd_outcome(history: list, i: int) -> str:
    if i + 1 >= len(history):
        return "→ pending (upcoming)"
    nxt = history[i + 1]
    return f"→ next: {nxt['candle']:<2} ({_BREAK.get(nxt['candle'], '?')})"


def _continuation(history: list, start: int) -> tuple:
    """(continued, scored) over directional bars from ``start`` whose successor
    is a known candle. An unknown successor (a NULL-OHLC placeholder, ``X``)
    is still pending, not a miss (Codex r4481033984)."""
    correct = total = 0
    for i in range(start, len(history) - 1):
        cur, nxt = history[i]["candle"], history[i + 1]["candle"]
        if cur in ("2U", "2D") and nxt in _BREAK and nxt != "X":
            total += 1
            correct += nxt == cur
    return correct, total


def _fmt(x) -> str:
    return "  —  " if x is None else f"{x:>8.2f}"


def report_ticker(ticker: str, days: int) -> None:
    res = compute_strat_history(ticker, timeframes=["1d", "1w", "1mo", "1q"],
                                lookback=max(days + 2, 12))
    print("=" * 78)
    if not res.get("available"):
        print(f"{ticker:6} — UNAVAILABLE ({res.get('reason')})")
        return
    d = res["timeframes"].get("1d", {})
    if not d.get("available"):
        print(f"{ticker:6} — no daily bars")
        return
    cur = d["current"]
    print(f"{ticker:6}  last={cur['period']}  close={_fmt(cur['close']).strip()}")

    hist = d["history"]
    print(f"\n  DAILY tape + forward-walk (last {days} sessions):")
    print(f"    {'date':<11}{'cand':<5}{'combo':<26}{'O':>8}{'H':>8}{'L':>8}{'C':>8}"
          f"   trig(hi/lo)        outcome")
    start = max(0, len(hist) - days - 1)
    for i in range(start, len(hist)):
        b = hist[i]
        trig = f"{_fmt(b['trigger_high']).strip()}/{_fmt(b['trigger_low']).strip()}"
        outcome = _fwd_outcome(hist, i)
        print(f"    {b['period']:<11}{b['candle']:<5}{(b['combo'] or 'none'):<26}"
              f"{_fmt(b['open'])}{_fmt(b['high'])}{_fmt(b['low'])}{_fmt(b['close'])}"
              f"   {trig:<18}{outcome}")
    correct, total = _continuation(hist, start)
    if total:
        print(f"    directional continuation this week: {correct}/{total} "
              f"({100*correct/total:.0f}%)")

    print("\n  HIGHER TIMEFRAMES (current):")
    for tf, name in (("1w", "Weekly"), ("1mo", "Monthly"), ("1q", "Quarterly")):
        blk = res["timeframes"].get(tf, {})
        if blk.get("available"):
            c = blk["current"]
            print(f"    {name:<10} {c['candle']:<3} {c['combo'] or 'none':<26} "
                  f"(period {c['period']})")
        else:
            print(f"    {name:<10} {blk.get('reason', 'n/a')}")

    up = d["upcoming"]
    coil = "  ⟵ inside/coil pending break" if up["is_inside_setup"] else ""
    print(f"\n  UPCOMING DAILY SETUP:{coil}")
    print(f"    break ↑ {_fmt(up['trigger_high']).strip():>8}  →  {up['break_up']}")
    print(f"    50%     {_fmt(up['mid_trigger']).strip():>8}")
    print(f"    break ↓ {_fmt(up['trigger_low']).strip():>8}  →  {up['break_down']}")
    print()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    print(f"STRAT HISTORY REPORT — {len(tickers)} tickers, last {args.days} sessions\n")
    for t in tickers:
        try:
            report_ticker(t, args.days)
        except Exception as e:
            print(f"{t:6} — ERROR: {e}")
    print("=" * 78)


if __name__ == "__main__":
    main()
