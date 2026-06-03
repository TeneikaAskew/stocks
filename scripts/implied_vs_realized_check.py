#!/usr/bin/env python3
"""Implied-vs-realized check (gate 7) — the trade-test gate.

The magnitude model's 2-3x within-cell precision boost could be:
  1. Genuine bar-specific structure (potentially unpriced edge)
  2. Finer-grained calendar (priced into IV term structure)
  3. Volatility clustering / GARCH (very priced into intraday IV)

The decomposition can't separate these. The implied-vs-realized check
can: on bars where the model predicts EXPLOSIVE, does the realized
absolute move exceed the implied move priced into the at-the-money
straddle at that moment?

  - If yes with margin: the model is finding moves the market under-prices.
    Real unpriced edge — full straddle backtest is warranted.
  - If realized ≈ implied: the within-cell boost IS the priced finer-
    calendar and vol-clustering effects. No edge no matter how clean
    the 2-3x looked.

Pre-set pass bar (committed before running): ratio ≥ 1.25 in ≥ 6 of
the folds with IV coverage. See docs/MAGNITUDE_ENGINE_RESULTS.md §5e.

Implied-move proxy:
  implied_5min = spot × IV × sqrt(5 / (252 × 390))
where IV is the at-or-before EOD ATM IV from etf_options_snapshots
on date D-1 (the bar's date minus 1 trading day).

Realized move = |next_open − next_close| (the magnitude target's
numerator, in dollar terms).

Usage:
    python -m scripts.implied_vs_realized_check \\
        --phase phase_calendar --ticker IWM --tf 5m \\
        --run-id magnitude-engine-7jsgk
"""
from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from google.cloud import storage as gcs
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))
from gcp.database import get_engine
from gcp.research.magnitude_engine.mag_config import (
    TICKERS, TIMEFRAMES, LABEL_COL, LABEL_CLASSES, LABEL_TO_IDX,
    DEFAULT_CUTOFFS, GCS_BUCKET_DEFAULT,
    SUCCESS_BAR_GATE7_RATIO_MIN as GATE_7_RATIO_THRESHOLD,
    SUCCESS_BAR_GATE7_MIN_PASSING_FOLDS as GATE_7_MIN_PASSING_FOLDS,
    SUCCESS_BAR_GATE7_MIN_COVERAGE_FOLDS as GATE_7_MIN_FOLDS_WITH_COVERAGE,
)
from gcp.research.magnitude_engine.mag_dataset import load_magnitude_dataset

# Trading-minutes per year for the IV-to-5min conversion. 252 trading
# days × 390 RTH minutes = 98,280 minutes. We use this for the time
# fraction sqrt(5/98280). This is the standard intraday convention,
# not the 365×24×60 calendar convention.
TRADING_MINUTES_PER_YEAR = 252 * 390  # 98,280

from scripts._magnitude_analysis_helpers import load_predictions


def load_atm_iv_per_date(engine, ticker: str,
                          min_date: pd.Timestamp,
                          max_date: pd.Timestamp,
                          only_dates: "set | None" = None) -> pd.DataFrame:
    """Pull EOD ATM IV per (ticker, date) from etf_options_snapshots.

    'EOD' = the LAST snapshot of the day for nearest-expiry, closest-to-
    spot contract. ATM = strike closest to spot at snapshot.

    Returns df with columns: date (datetime.date), atm_iv (float).

    Performance: etf_options_snapshots is ~92M rows; a window-function over the
    full min..max span (7 years × every contract per snapshot) cannot complete
    within the Cloud Run task-timeout. gate 7 only needs IV on the handful of
    dates the model predicted EXPLOSIVE (+ their T-1 anchors), so `only_dates`
    scopes the scan to those dates via the existing (ticker, snapshot_date)
    index — turning a full-table scan into a few-hundred-date lookup. The set
    MUST include each bar's T-1..T-N candidate anchor dates (we widen by a small
    calendar margin so weekends/holidays still resolve a backward IV anchor).
    """
    date_clause = ""
    params = {"t": ticker, "lo": min_date.date(), "hi": max_date.date()}
    if only_dates:
        date_clause = "AND snapshot_date = ANY(:dates)"
        params["dates"] = sorted(only_dates)
        print(f"querying etf_options_snapshots for ticker={ticker} "
              f"scoped to {len(only_dates)} dates", file=sys.stderr)
    else:
        print(f"querying etf_options_snapshots for ticker={ticker} "
              f"{min_date.date()}..{max_date.date()} (FULL SPAN)", file=sys.stderr)
    sql = text(f"""
        WITH last_snapshots AS (
            SELECT
                ticker,
                snapshot_date,
                MAX(snapshot_ts) AS last_ts
              FROM etf_options_snapshots
             WHERE ticker = :t
               AND snapshot_date BETWEEN :lo AND :hi
               {date_clause}
             GROUP BY ticker, snapshot_date
        ),
        eod_contracts AS (
            SELECT s.ticker, s.snapshot_date, s.snapshot_ts,
                   s.strike, s.expiration, s.implied_volatility,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.ticker, s.snapshot_date
                       ORDER BY
                           ABS(s.delta - 0.5) ASC NULLS LAST,
                           s.expiration ASC NULLS LAST
                   ) AS rn
              FROM etf_options_snapshots s
              JOIN last_snapshots l
                ON s.ticker = l.ticker
               AND s.snapshot_date = l.snapshot_date
               AND s.snapshot_ts = l.last_ts
             WHERE s.implied_volatility IS NOT NULL
               AND s.implied_volatility > 0
               AND s.option_type = 'calls'
        )
        SELECT snapshot_date AS d, implied_volatility AS atm_iv
          FROM eod_contracts
         WHERE rn = 1
         ORDER BY snapshot_date
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params=params)
    if df.empty:
        return df
    df["d"] = pd.to_datetime(df["d"]).dt.date
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True)
    p.add_argument("--ticker", required=True, choices=list(TICKERS))
    p.add_argument("--tf", required=True, choices=list(TIMEFRAMES))
    p.add_argument("--run-id", required=True)
    p.add_argument("--bucket", default=GCS_BUCKET_DEFAULT)
    p.add_argument("--label-mode", default="body", choices=["body", "excursion"],
                   help="Must match the label the predictions were trained on. "
                        "'body' realized move = |next_close-next_open|; 'excursion' "
                        "= |next_high-next_low| (intrabar range a straddle harvests).")
    args = p.parse_args()

    # Load model predictions for EXPLOSIVE filtering
    preds = load_predictions(args.phase, args.ticker, args.tf, args.bucket, args.run_id)
    preds["ts"] = pd.to_datetime(preds["ts"], utc=True)
    explosive_idx = LABEL_TO_IDX["EXPLOSIVE"]
    pe = preds[preds["pred_bucket_idx"] == explosive_idx].copy()
    print(f"\nLoaded {len(preds)} predictions; {len(pe)} predicted EXPLOSIVE",
          file=sys.stderr)
    if len(pe) == 0:
        print("No EXPLOSIVE predictions to test. Exiting.")
        return

    # Load magnitude dataset (need next_open, next_close, open, ts for spot)
    engine = get_engine()
    print("loading magnitude dataset for spot + realized-move computation...",
          file=sys.stderr)
    df = load_magnitude_dataset(engine, args.ticker, args.tf, phase="phase0",
                                label_mode=args.label_mode)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["bar_date"] = pd.to_datetime(df["bar_date"]).dt.date
    # Realized move MUST match the label the model was trained/predicting on,
    # else we'd compare an excursion prediction against a body realization.
    if args.label_mode == "excursion":
        df["realized_move_dollars"] = (df["next_high"] - df["next_low"]).abs()
    else:
        df["realized_move_dollars"] = (df["next_open"] - df["next_close"]).abs()

    # Join predictions ↔ dataset on ts to get realized_move + spot
    join = pe.merge(
        df[["ts", "open", "close", "bar_date", "realized_move_dollars"]],
        on="ts", how="inner", validate="one_to_one",
    )
    print(f"Joined {len(join)} EXPLOSIVE-predicted bars with dataset",
          file=sys.stderr)
    if len(join) == 0:
        print("ts join produced no rows — check that prediction CSV ts matches dataset ts.")
        return

    # Pull ATM IV ONLY for the dates we need: each EXPLOSIVE bar's date plus a
    # backward calendar margin so the T-1 (strictly-prior) IV anchor still
    # resolves across weekends/holidays. Scoping the 92M-row table to these
    # ~hundreds of dates is what makes gate 7 finish within the task-timeout.
    bar_dates = pd.to_datetime(join["bar_date"]).dt.normalize().unique()
    needed = set()
    for d in bar_dates:
        for back in range(0, 6):  # D and up to 5 calendar days prior
            needed.add((d - pd.Timedelta(days=back)).date())
    iv = load_atm_iv_per_date(engine, args.ticker,
                                join["ts"].min(), join["ts"].max(),
                                only_dates=needed)
    print(f"IV coverage: {len(iv)} EOD snapshots between "
          f"{iv['d'].min() if not iv.empty else 'NONE'} and "
          f"{iv['d'].max() if not iv.empty else 'NONE'}", file=sys.stderr)
    if iv.empty:
        print("\n=== NO IV COVERAGE — gate 7 verdict: INSUFFICIENT_DATA ===")
        return

    # For each predicted bar at date D, use the IV on date D-1 (or earlier).
    # Pandas merge_asof with backward search on bar_date.
    iv_by_date = iv.sort_values("d").rename(columns={"d": "iv_date"})
    iv_by_date["iv_date"] = pd.to_datetime(iv_by_date["iv_date"])
    join["bar_date_dt"] = pd.to_datetime(join["bar_date"])
    # Bar at date D → IV anchor is most recent iv_date STRICTLY before D
    # (one trading day prior at the latest). merge_asof requires both
    # sorted; bound by D-1 to avoid same-day leakage.
    join = join.sort_values("bar_date_dt")
    iv_by_date = iv_by_date.sort_values("iv_date")
    join = pd.merge_asof(
        join, iv_by_date,
        left_on="bar_date_dt", right_on="iv_date",
        direction="backward", allow_exact_matches=False,
    )
    has_iv = join["atm_iv"].notna()
    n_with_iv = int(has_iv.sum())
    print(f"{n_with_iv} of {len(join)} EXPLOSIVE-predicted bars have a "
          f"T-1-or-earlier IV anchor", file=sys.stderr)

    # implied_5min = spot * IV * sqrt(5 / 98280)
    join["implied_move_dollars"] = (
        join["open"] * join["atm_iv"] * np.sqrt(5.0 / TRADING_MINUTES_PER_YEAR)
    )

    # Per-fold aggregation
    print()
    print("=" * 100)
    print(f"IMPLIED-VS-REALIZED  (gate 7)  {args.phase} {args.ticker} {args.tf}")
    print("=" * 100)
    print(f"\n{'fold':25} {'n_pe':>5} {'n_iv':>5} {'mean_real':>11} "
           f"{'mean_impl':>11} {'ratio':>7} {'gate7':>7}")
    print("-" * 100)

    fold_results = []
    cutoffs = list(DEFAULT_CUTOFFS)
    for i, cut in enumerate(cutoffs):
        if i + 1 < len(cutoffs):
            test_end = cutoffs[i + 1]
        else:
            test_end = str(pd.Timestamp(df["bar_date"].max()) + pd.Timedelta(days=1))[:10]
        fold_label = f"{cut}..{test_end}"
        fold_data = join[join["fold"] == fold_label]
        n_pe = len(fold_data)
        fold_with_iv = fold_data[fold_data["atm_iv"].notna()]
        n_iv = len(fold_with_iv)

        if n_iv < 20:  # too few for stable mean
            status = "NO_COVERAGE" if n_iv == 0 else f"THIN_n={n_iv}"
            print(f"{fold_label:25} {n_pe:>5d} {n_iv:>5d}  ({status})")
            fold_results.append({"fold": fold_label, "status": status})
            continue

        mean_real = float(fold_with_iv["realized_move_dollars"].mean())
        mean_impl = float(fold_with_iv["implied_move_dollars"].mean())
        ratio = mean_real / mean_impl if mean_impl > 0 else float("nan")
        gate7 = "PASS" if ratio >= GATE_7_RATIO_THRESHOLD else "FAIL"
        print(f"{fold_label:25} {n_pe:>5d} {n_iv:>5d} {mean_real:>11.4f} "
              f"{mean_impl:>11.4f} {ratio:>7.2f} {gate7:>7}")
        fold_results.append({
            "fold": fold_label, "status": "OK",
            "n_pe": n_pe, "n_iv": n_iv,
            "mean_real": mean_real, "mean_impl": mean_impl,
            "ratio": ratio, "gate7": (ratio >= GATE_7_RATIO_THRESHOLD),
        })

    print()
    ok_folds = [f for f in fold_results if f.get("status") == "OK"]
    pass_count = sum(1 for f in ok_folds if f.get("gate7"))
    n_cov = len(ok_folds)
    print(f"Folds with IV coverage: {n_cov} of {len(cutoffs)}")
    print(f"Folds passing gate 7 (ratio ≥ {GATE_7_RATIO_THRESHOLD}): {pass_count}")
    if n_cov < GATE_7_MIN_FOLDS_WITH_COVERAGE:
        verdict = f"INSUFFICIENT_DATA ({n_cov} < {GATE_7_MIN_FOLDS_WITH_COVERAGE} folds with coverage)"
    elif pass_count >= GATE_7_MIN_PASSING_FOLDS:
        verdict = "PASS — within-cell signal is finding moves the option market under-prices"
    else:
        verdict = "FAIL — within-cell boost is at-or-below the priced implied move; not tradeable as a non-directional bet"
    print(f"\nGate 7 verdict: {verdict}")


if __name__ == "__main__":
    main()
