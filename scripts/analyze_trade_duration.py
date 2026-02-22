#!/usr/bin/env python3
"""Analyze trade durations from existing backtest CSVs.

Reads the most recent backtest CSV per ticker and produces detailed
duration breakdowns: by exit reason, direction, win/loss, and FTFC alignment.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

RESULTS_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest_results"


def find_latest_csv(ticker: str, strat: bool = True) -> Path:
    """Find the most recent backtest CSV for a ticker."""
    pattern = f"backtest_{ticker}_*.csv"
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files:
        df = pd.read_csv(f, nrows=2)
        has_strat = 'ftfc_score' in df.columns and df['ftfc_score'].notna().any()
        if strat and has_strat:
            return f
        if not strat and not has_strat:
            return f
    return files[0] if files else None


def load_trades(filepath: Path) -> pd.DataFrame:
    df = pd.read_csv(filepath, parse_dates=["entry_time", "exit_time"])
    df["duration_min"] = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0
    df["won"] = df["return_pct"] > 0
    df["return_bps"] = df["return_pct"] * 10_000
    return df


def analyze_ticker(df: pd.DataFrame, ticker: str):
    n = len(df)
    winners = df[df["won"]]
    losers = df[~df["won"]]

    print(f"\n{'='*70}")
    print(f"  {ticker} — {n:,} trades")
    print(f"{'='*70}")

    # Overall
    print(f"\n  Overall:")
    print(f"    Win Rate:          {df['won'].mean():.1%}")
    print(f"    Avg Hold (all):    {df['duration_min'].mean():.1f} min")
    print(f"    Avg Hold (wins):   {winners['duration_min'].mean():.1f} min")
    print(f"    Avg Hold (losses): {losers['duration_min'].mean():.1f} min")

    # By exit reason
    print(f"\n  By Exit Reason:")
    print(f"  {'Reason':<14} {'Count':>6} {'%':>7} {'Avg Dur':>10} {'Med Dur':>10} {'IQR':>14} {'Avg Ret':>12} {'WR':>8}")
    print(f"  {'-'*14} {'-'*6} {'-'*7} {'-'*10} {'-'*10} {'-'*14} {'-'*12} {'-'*8}")

    for reason in ['target', 'stop_loss', 'time_stop', 'rsi_extreme', 'eod_close']:
        sub = df[df['exit_reason'] == reason]
        if len(sub) == 0:
            continue
        q25 = sub['duration_min'].quantile(0.25)
        q75 = sub['duration_min'].quantile(0.75)
        print(f"  {reason:<14} {len(sub):>6} {len(sub)/n:>6.1%} "
              f"{sub['duration_min'].mean():>8.1f}m "
              f"{sub['duration_min'].median():>8.1f}m "
              f"{q25:>5.0f}–{q75:.0f}m "
              f"{sub['return_bps'].mean():>+10.1f}bp "
              f"{sub['won'].mean():>7.1%}")

    # By direction
    print(f"\n  By Direction:")
    for direction in ['CALL', 'PUT']:
        sub = df[df['direction'] == direction]
        if len(sub) == 0:
            continue
        w = sub[sub['won']]
        l = sub[~sub['won']]
        print(f"    {direction}: {len(sub)} trades, WR={sub['won'].mean():.1%}, "
              f"hold={sub['duration_min'].mean():.0f}min (wins={w['duration_min'].mean():.0f}m, "
              f"losses={l['duration_min'].mean():.0f}m), "
              f"avg win=+{w['return_bps'].mean():.0f}bp, avg loss={l['return_bps'].mean():.0f}bp")

    # Duration percentiles
    pcts = [5, 25, 50, 75, 95]
    vals = df["duration_min"].quantile([p/100 for p in pcts])
    print(f"\n  Duration Percentiles:")
    for p, v in zip(pcts, vals):
        bar = "█" * int(v / 2)
        print(f"    P{p:>2}: {v:>5.0f} min  {bar}")

    # Key insight
    print(f"\n  Key Insight:")
    target = df[df['exit_reason'] == 'target']
    stop = df[df['exit_reason'] == 'stop_loss']
    time_s = df[df['exit_reason'] == 'time_stop']
    if len(target) > 0:
        print(f"    Target hits: {target['duration_min'].median():.0f} min median "
              f"({target['duration_min'].quantile(0.25):.0f}–{target['duration_min'].quantile(0.75):.0f} IQR) "
              f"→ +{target['return_bps'].mean():.0f} bps avg")
    if len(stop) > 0:
        print(f"    Stop losses: {stop['duration_min'].median():.0f} min median "
              f"({stop['duration_min'].quantile(0.25):.0f}–{stop['duration_min'].quantile(0.75):.0f} IQR) "
              f"→ {stop['return_bps'].mean():.0f} bps avg")
    if len(time_s) > 0:
        print(f"    Time stops:  ~{time_s['duration_min'].median():.0f} min → "
              f"WR {time_s['won'].mean():.0%}, "
              f"{time_s['return_bps'].mean():+.1f} bps (small moves)")


def main():
    tickers = ['IWM', 'SPY', 'QQQ']
    for ticker in tickers:
        fpath = find_latest_csv(ticker, strat=True)
        if fpath is None:
            print(f"  No backtest CSV for {ticker}")
            continue
        print(f"  Using: {fpath.name}")
        df = load_trades(fpath)
        analyze_ticker(df, ticker)
    print()


if __name__ == "__main__":
    main()
