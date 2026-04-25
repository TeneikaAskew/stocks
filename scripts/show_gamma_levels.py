#!/usr/bin/env python3
"""
Print Stratalyst-style gamma levels (King / Gate / Spot / Flip) from the
options-heatseeker JSON snapshots already in this repo.

Usage:
    python3 scripts/show_gamma_levels.py qqq
    python3 scripts/show_gamma_levels.py iwm --date 20251121 --window 15
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO / "options-heatseeker" / "data"

CONTRACT_MULT = 100
KING_THRESHOLD = 0.50      # >= 50% of max |gex| in window -> KING
GATE_THRESHOLD = 0.20      # >= 20% of max |gex| in window -> GATE
FLIP_BAND = 0.10           # strikes whose net gex flips sign neighbor-to-neighbor


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


def estimate_spot(options: list[dict]) -> float:
    """Estimate spot from put-call parity proxy: strike where |call_delta|≈0.5."""
    nearest_exp = min(o["expiration"] for o in options)
    near = [o for o in options if o["expiration"] == nearest_exp and o["type"] == "call"]
    if not near:
        return 0.0
    near.sort(key=lambda o: abs(abs(o.get("delta", 0)) - 0.5))
    return float(near[0]["strike"])


def aggregate_gex(options: list[dict], spot: float) -> dict[float, dict]:
    """Net dealer GEX per strike. Convention: dealer is short calls / long puts."""
    book: dict[float, dict] = defaultdict(lambda: {"call_oi": 0, "put_oi": 0, "gex": 0.0})
    for o in options:
        strike = float(o["strike"])
        gamma = float(o.get("gamma") or 0)
        oi = int(o.get("open_interest") or 0)
        if gamma == 0 or oi == 0:
            continue
        sign = -1 if o["type"] == "call" else 1
        # GEX per strike (notional $ gamma): gamma * OI * 100 * spot^2 * sign / 100
        gex = sign * gamma * oi * CONTRACT_MULT * (spot ** 2) / 100.0
        book[strike]["gex"] += gex
        if o["type"] == "call":
            book[strike]["call_oi"] += oi
        else:
            book[strike]["put_oi"] += oi
    return book


def classify(book: dict[float, dict], spot: float, window_pct: float) -> list[dict]:
    lo, hi = spot * (1 - window_pct / 100), spot * (1 + window_pct / 100)
    rows = [
        {"strike": k, **v} for k, v in book.items() if lo <= k <= hi
    ]
    if not rows:
        return rows
    rows.sort(key=lambda r: r["strike"])
    max_abs = max(abs(r["gex"]) for r in rows) or 1.0

    # Detect flips: consecutive strikes whose GEX changes sign
    for i, r in enumerate(rows):
        tag = ""
        ratio = abs(r["gex"]) / max_abs
        if ratio >= KING_THRESHOLD:
            tag = "KING"
        elif ratio >= GATE_THRESHOLD:
            tag = "GATE"
        # spot proximity tag
        if abs(r["strike"] - spot) <= max(0.5, spot * 0.002):
            tag = ("SPOT " + tag).strip()
        # flip detection
        if i > 0 and rows[i - 1]["gex"] * r["gex"] < 0:
            tag = ("FLIP " + tag).strip()
        r["tag"] = tag
    return rows


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


def render(rows: list[dict], spot: float, ticker: str, snap: Path) -> None:
    print(f"\n  {ticker.upper()}   spot≈{spot:.2f}   ({snap.name})\n")
    print(f"  {'STRIKE':>7}  {'NET GEX':>10}  {'CALL OI':>8}  {'PUT OI':>8}   TAG")
    print(f"  {'-'*7}  {'-'*10}  {'-'*8}  {'-'*8}   {'-'*16}")
    for r in rows:
        marker = "►" if abs(r["strike"] - spot) <= max(0.5, spot * 0.002) else " "
        print(
            f"{marker} {r['strike']:>7.2f}  {fmt_gex(r['gex']):>10}  "
            f"{r['call_oi']:>8,}  {r['put_oi']:>8,}   {r['tag']}"
        )

    kings = [r for r in rows if "KING" in r["tag"]]
    gates = [r for r in rows if "GATE" in r["tag"]]
    flips = [r for r in rows if "FLIP" in r["tag"]]
    print()
    def _join(items: list[dict]) -> str:
        return ", ".join(f"{r['strike']:.2f}" for r in items)
    if kings:
        print(f"  KINGS:  {_join(kings)}")
    if gates:
        print(f"  GATES:  {_join(gates)}")
    if flips:
        print(f"  FLIPS:  {_join(flips)}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", help="qqq | iwm | spy")
    ap.add_argument("--date", help="YYYYMMDD; default = latest")
    ap.add_argument("--window", type=float, default=10.0,
                    help="percent +/- spot to display (default 10)")
    ap.add_argument("--expiry", help="restrict to one expiration YYYY-MM-DD")
    args = ap.parse_args()

    snap = latest_snapshot(args.ticker, args.date)
    payload = json.loads(snap.read_text())
    options = payload["options"]
    if args.expiry:
        options = [o for o in options if o["expiration"] == args.expiry]
        if not options:
            sys.exit(f"no contracts for expiry {args.expiry}")

    spot = estimate_spot(options)
    if spot == 0:
        sys.exit("could not estimate spot")
    book = aggregate_gex(options, spot)
    rows = classify(book, spot, args.window)
    render(rows, spot, args.ticker, snap)


if __name__ == "__main__":
    main()
