#!/usr/bin/env python3
"""
Print Stratalyst-style gamma levels (King / Gate / Spot / Flip) from the
options-heatseeker JSON snapshots already in this repo.

Thin wrapper around lib.gamma — the canonical math lives there. This script
exists so you can compare the project's analytics against third-party
gamma-positioning tools without spinning up the React app.

Usage:
    python3 scripts/show_gamma_levels.py qqq
    python3 scripts/show_gamma_levels.py iwm --date 20251121 --window 8
    python3 scripts/show_gamma_levels.py qqq --expiry 2025-11-21
    python3 scripts/show_gamma_levels.py qqq --spot 590.50  # override
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO / "options-heatseeker" / "data"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib import gamma  # noqa: E402


def latest_snapshot(ticker: str, date: str | None) -> Path:
    folder = DATA_ROOT / ticker.lower()
    if not folder.exists():
        sys.exit(f"no data folder: {folder}")
    files = sorted(folder.glob(f"{ticker.lower()}_options_*.json"))
    if not files:
        sys.exit(f"no snapshots in {folder}")
    if date:
        match = [f for f in files if date in f.name]
        if not match:
            sys.exit(f"no snapshot for date {date}")
        return match[-1]
    return files[-1]


def fmt_gex(x: float) -> str:
    sign = "+" if x >= 0 else "-"
    a = abs(x)
    if a >= 1e9:
        return f"{sign}{a/1e9:.1f}B"
    if a >= 1e6:
        return f"{sign}{a/1e6:.1f}M"
    if a >= 1e3:
        return f"{sign}{a/1e3:.0f}K"
    return f"{sign}{a:.0f}"


def render(summary: gamma.GammaSummary, snap_name: str) -> None:
    spot = summary.spot.price
    print()
    print(f"  {summary.ticker}   spot≈{spot:.2f} ({summary.spot.method})   "
          f"flip={'%.2f' % summary.flip if summary.flip else 'n/a'}   "
          f"regime={summary.regime}   ({snap_name})")
    if summary.spot.note:
        print(f"  spot detail: {summary.spot.note}")
    print()
    print(f"  {'STRIKE':>7}  {'NET GEX':>10}  {'CALL OI':>8}  {'PUT OI':>8}   TAGS")
    print(f"  {'-'*7}  {'-'*10}  {'-'*8}  {'-'*8}   {'-'*16}")

    for lv in summary.levels:
        marker = "►" if "spot" in lv.tags else " "
        tags_str = " ".join(t.upper() for t in lv.tags) or ""
        print(
            f"{marker} {lv.strike:>7.2f}  {fmt_gex(lv.gex):>10}  "
            f"{lv.call_oi:>8,}  {lv.put_oi:>8,}   {tags_str}"
        )

    print()
    if summary.kings:
        print(f"  KINGS:  {', '.join(f'{l.strike:.2f}' for l in summary.kings)}")
    if summary.gates:
        print(f"  GATES:  {', '.join(f'{l.strike:.2f}' for l in summary.gates)}")
    if summary.flip_levels:
        print(f"  FLIPS:  {', '.join(f'{l.strike:.2f}' for l in summary.flip_levels)}")
    print(f"  TOTAL GEX: {fmt_gex(summary.total_gex)}")
    if summary.warnings:
        print()
        for w in summary.warnings:
            print(f"  ⚠ {w}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", help="qqq | iwm | spy")
    ap.add_argument("--date", help="YYYYMMDD; default = latest snapshot")
    ap.add_argument("--window", type=float, default=8.0,
                    help="percent +/- spot to display (default 8)")
    ap.add_argument("--expiry", help="restrict to one expiration YYYY-MM-DD")
    ap.add_argument("--spot", type=float, help="override estimated spot price")
    args = ap.parse_args()

    snap = latest_snapshot(args.ticker, args.date)
    payload = json.loads(snap.read_text())
    snapshot_date = payload.get("date", snap.stem.split("_")[-1])

    summary = gamma.build_summary(
        ticker=args.ticker,
        snapshot_date=snapshot_date,
        options=payload["options"],
        spot_override=args.spot,
        window_pct=args.window,
        expiry_filter=args.expiry,
    )
    render(summary, snap.name)


if __name__ == "__main__":
    main()
