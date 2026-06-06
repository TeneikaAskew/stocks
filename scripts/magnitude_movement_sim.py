#!/usr/bin/env python3
"""Movement-only options P&L simulation for magnitude-engine predictions.

⚠️  COSTS DEFERRED — this simulates GROSS movement only. Bid-ask spread,
commission, slippage, and theta decay are NOT subtracted (per the user's
explicit scope: "focused on the movements; I'll handle that later"). Do NOT
read these numbers as net/tradeable P&L — they are an upper bound that measures
whether the underlying MOVEMENT on the model's EXPLOSIVE-predicted bars is large
enough to be worth pursuing, before friction.

What it does
------------
For each bar the magnitude model predicted EXPLOSIVE (pred_bucket_idx ==
EXPLOSIVE), enter a hypothetical option position at the next bar's open and mark
it against the next bar's path (high/low/close). Four position types:

  straddle  ATM call + ATM put. Profits from |close - entry| range either way.
  strangle  OTM call + OTM put at +/- k*ATR. Move must clear the OTM offset.
  call      Long call. Profit from upside excursion  max(next_high - entry, 0).
  put       Long put.  Profit from downside excursion max(entry - next_low, 0).

Direction source (for call/put — a directional bet needs up-vs-down):
  none   no filter (straddle/strangle, or fire call+put on every EXPLOSIVE bar)
  label  ARM A — trust the directional magnitude label the predictions were
         trained on (run mag_walk_forward --label-mode call|put first; the CSV's
         EXPLOSIVE class already means "big up" / "big down").
  strat  ARM B — join strat_features_<tf> on (ticker, ts) and take direction
         from the CURRENT bar's Strat structure (2U / up-continuation -> call;
         2D / down-continuation -> put). The size signal stays the (symmetric)
         excursion model; Strat only supplies direction.

P&L is reported in ATR-20 units (move / atr_20) so it's comparable across
tickers/regimes, and (when --with-iv) as a multiple of the implied move the
option market priced — the same realized/implied ratio gate-7 uses, but here
turned into a per-position payoff.

Usage
-----
    python -m scripts.magnitude_movement_sim \
        --ticker QQQ --tf 5m --phase phase0 --run-id <exec> \
        --position straddle --direction none
    python -m scripts.magnitude_movement_sim \
        --ticker QQQ --tf 5m --phase phase0 --run-id <call-run> \
        --position call --direction label
"""
from __future__ import annotations
import argparse
import io
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from gcp.database import get_engine
from gcp.research.magnitude_engine.mag_config import (
    TICKERS, TIMEFRAMES, LABEL_TO_IDX, DEFAULT_CUTOFFS, GCS_BUCKET_DEFAULT,
)
from gcp.research.magnitude_engine.mag_dataset import load_magnitude_dataset
from scripts._magnitude_analysis_helpers import load_predictions

# Minutes in a trading year, for the implied-move scaling (mirrors gate-7).
TRADING_MINUTES_PER_YEAR = 252 * 390


def _strat_direction(engine, ticker: str, tf: str) -> pd.DataFrame:
    """Per-bar direction from CURRENT-bar Strat structure (ARM B).

    Returns df[ts, strat_dir] where strat_dir ∈ {'call','put',None}. 2U or an
    up-continuation → call; 2D or a down-continuation → put; inside/outside/
    ambiguous → None (no directional trade). Read-only; one query.
    """
    from sqlalchemy import text
    q = text(
        f"SELECT ts, strat_candle, strat_combo, is_continuation, is_reversal "
        f"FROM strat_features_{tf} WHERE ticker = :t"
    )
    with engine.connect() as conn:
        s = pd.read_sql(q, conn, params={"t": ticker})
    cand = s["strat_candle"].astype("string").fillna("")
    combo = s["strat_combo"].astype("string").fillna("").str.lower()
    up = cand.eq("2U") | combo.str.contains("bull")
    dn = cand.eq("2D") | combo.str.contains("bear")
    s["strat_dir"] = np.where(up & ~dn, "call",
                       np.where(dn & ~up, "put", None))
    s["ts"] = pd.to_datetime(s["ts"], utc=True)
    return s[["ts", "strat_dir"]]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", required=True, choices=list(TICKERS))
    p.add_argument("--tf", required=True, choices=list(TIMEFRAMES))
    p.add_argument("--phase", default="phase0")
    p.add_argument("--run-id", required=True,
                   help="exec/run-id of the mag_walk_forward predictions CSV")
    p.add_argument("--position", required=True,
                   choices=["straddle", "strangle", "call", "put"])
    p.add_argument("--direction", default="none",
                   choices=["none", "label", "strat"],
                   help="call/put direction source: label=trust the directional "
                        "magnitude label; strat=Strat structure overlay (ARM B).")
    p.add_argument("--strangle-atr", type=float, default=0.5,
                   help="OTM offset for strangle legs, in ATR-20 units.")
    p.add_argument("--label-mode", default="body",
                   choices=["body", "excursion", "call", "put"],
                   help="Label the predictions were trained on (for loading the "
                        "matching dataset/realized columns).")
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    args = p.parse_args()

    print("=" * 96)
    print("⚠️  MOVEMENT-ONLY SIMULATION — COSTS DEFERRED (no spread/commission/"
          "theta). Gross movement, an UPPER BOUND, not net P&L.")
    print("=" * 96)

    # 1. Predictions → EXPLOSIVE-predicted bars.
    preds = load_predictions(args.phase, args.ticker, args.tf, args.bucket, args.run_id)
    preds["ts"] = pd.to_datetime(preds["ts"], utc=True)
    expl = LABEL_TO_IDX["EXPLOSIVE"]
    pe = preds[preds["pred_bucket_idx"] == expl].copy()
    print(f"\nLoaded {len(preds)} preds; {len(pe)} predicted EXPLOSIVE", file=sys.stderr)
    if pe.empty:
        print("No EXPLOSIVE predictions — nothing to simulate.")
        return

    # 2. Dataset OHLC (entry = next_open; path = next_high/low/close; atr_20).
    engine = get_engine()
    df = load_magnitude_dataset(engine, args.ticker, args.tf, phase=args.phase,
                                label_mode=args.label_mode)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    cols = ["ts", "next_open", "next_high", "next_low", "next_close", "atr_20"]
    j = pe.merge(df[cols], on="ts", how="inner")
    j = j[j["atr_20"].notna() & (j["atr_20"] > 0)].copy()
    print(f"Joined {len(j)} EXPLOSIVE bars with OHLC+atr_20", file=sys.stderr)
    if j.empty:
        print("No EXPLOSIVE bars joined to OHLC — check ts alignment.")
        return

    entry = j["next_open"]
    atr = j["atr_20"]

    # 3. Direction source (call/put only).
    if args.position in ("call", "put") and args.direction == "strat":
        sd = _strat_direction(engine, args.ticker, args.tf)
        j = j.merge(sd, on="ts", how="left")
        want = args.position  # 'call' or 'put'
        keep = j["strat_dir"] == want
        print(f"strat overlay: {int(keep.sum())} of {len(j)} EXPLOSIVE bars are "
              f"Strat-{want.upper()} direction", file=sys.stderr)
        j = j[keep].copy()
        entry = j["next_open"]; atr = j["atr_20"]
        if j.empty:
            print("No bars after Strat-direction filter."); return
    # direction == 'label': the predictions were trained on call/put label, so an
    # EXPLOSIVE pred already means the directional move — no extra filter.

    # 4. Gross movement payoff per position type (in $).
    nh, nl, nc = j["next_high"], j["next_low"], j["next_close"]
    if args.position == "call":
        payoff = (nh - entry).clip(lower=0)               # best upside excursion
        realized_for_ratio = payoff
    elif args.position == "put":
        payoff = (entry - nl).clip(lower=0)               # best downside excursion
        realized_for_ratio = payoff
    elif args.position == "straddle":
        # symmetric: a long straddle captures the larger of up/down excursion
        # (movement-only, exit at best point in the bar — upper bound).
        payoff = pd.concat([(nh - entry).clip(lower=0),
                            (entry - nl).clip(lower=0)], axis=1).max(axis=1)
        realized_for_ratio = (nh - nl).abs()              # full range (vs gate-7)
    else:  # strangle: legs sit k*ATR OTM; payoff is excursion beyond the offset
        off = args.strangle_atr * atr
        up = (nh - (entry + off)).clip(lower=0)
        dn = ((entry - off) - nl).clip(lower=0)
        payoff = pd.concat([up, dn], axis=1).max(axis=1)
        realized_for_ratio = (nh - nl).abs()

    j["payoff_atr"] = payoff / atr
    j["realized_atr"] = realized_for_ratio / atr

    # 5. Per-fold + overall summary.
    cutoffs = list(DEFAULT_CUTOFFS)
    bar_d = pd.to_datetime(j["ts"]).dt.tz_convert(None).dt.normalize()
    rows = []
    for i, cut in enumerate(cutoffs):
        lo = pd.Timestamp(cut)
        hi = pd.Timestamp(cutoffs[i + 1]) if i + 1 < len(cutoffs) else bar_d.max() + pd.Timedelta(days=1)
        m = (bar_d >= lo) & (bar_d < hi)
        n = int(m.sum())
        if n == 0:
            continue
        rows.append({
            "fold": f"{cut}..{hi.date()}",
            "n": n,
            "mean_payoff_atr": round(float(j.loc[m, "payoff_atr"].mean()), 4),
            "median_payoff_atr": round(float(j.loc[m, "payoff_atr"].median()), 4),
            "pct_payoff_gt_0": round(float((j.loc[m, "payoff_atr"] > 0).mean()), 3),
        })

    print(f"\nposition={args.position}  direction={args.direction}  "
          f"label_mode={args.label_mode}  ticker={args.ticker} {args.tf}")
    print(f"{'fold':28} {'n':>5} {'mean_atr':>9} {'med_atr':>9} {'%>0':>6}")
    print("-" * 64)
    for r in rows:
        print(f"{r['fold']:28} {r['n']:>5} {r['mean_payoff_atr']:>9.3f} "
              f"{r['median_payoff_atr']:>9.3f} {r['pct_payoff_gt_0']:>6.2f}")
    overall_mean = float(j["payoff_atr"].mean())
    overall_med = float(j["payoff_atr"].median())
    print("-" * 64)
    print(f"OVERALL  n={len(j)}  mean_payoff={overall_mean:.3f} ATR  "
          f"median={overall_med:.3f} ATR  %>0={(j['payoff_atr']>0).mean():.2f}")
    print("\n⚠️  COSTS DEFERRED — gross movement only; not net/tradeable P&L.")

    # 6. GCS json (mirrors the gate-7 / walk-forward report convention).
    summary = {
        "ticker": args.ticker, "tf": args.tf, "phase": args.phase,
        "run_id": args.run_id, "position": args.position,
        "direction": args.direction, "label_mode": args.label_mode,
        "costs": "DEFERRED — gross movement only",
        "n_bars": int(len(j)),
        "overall_mean_payoff_atr": round(overall_mean, 4),
        "overall_median_payoff_atr": round(overall_med, 4),
        "folds": rows,
        "computed_at": pd.Timestamp.utcnow().isoformat(),
    }
    try:
        from google.cloud import storage as gcs
        blob = (f"research/magnitude_engine/{args.phase}/{args.ticker.lower()}_{args.tf}/"
                f"movement_sim_{args.position}_{args.direction}_{int(time.time())}.json")
        gcs.Client().bucket(args.bucket).blob(blob).upload_from_string(
            json.dumps(summary, indent=2, default=str), content_type="application/json")
        print(f"saved gs://{args.bucket}/{blob}", file=sys.stderr)
    except Exception as e:  # cleanup — report write is non-fatal to the analysis
        print(f"(GCS summary upload skipped: {e})", file=sys.stderr)


if __name__ == "__main__":
    main()
