#!/usr/bin/env python3
"""Calibrate the intraday 0DTE theta-decay curve g(t) from REALTIME option marks.

g(t) is the cumulative fraction of an ATM 0DTE option's daily time-value that has
decayed by ``t`` minutes after the 09:30 ET open. It is consumed at runtime by
``lib.options_intraday.cumulative_theta_decay`` /
``intraday_theta_decay_fraction`` (which carry a baked snapshot of the knots) and
by ``scripts/analysis/options_pnl_translation.py``.

Methodology
-----------
For each (ticker, session) we take the 5-minute REALTIME ATM straddle from
``etf_options_snapshots``. ATM = ``argmin_K(call_mark + put_mark)`` restricted to
strikes with ``|delta| in [0.15, 0.85]`` (this excludes stale penny-quoted wings
whose both legs sit at the $0.01 floor and otherwise corrupt the minimum). The
straddle is ~pure ATM time value (delta-neutral), so its normalized decay
``g_day(t) = 1 - straddle(t)/straddle(open)`` traces the time-decay shape free of
direction. We pool g_day across tickers+sessions, bin by minute-of-session,
average, and enforce monotonicity (cumulative-max) since cumulative decay cannot
run backwards in expectation. The terminal expiry cliff (the final minutes into
the 16:00 settle) is not directly observable — the last REALTIME bar is ~15:55 —
so g is pinned to 1.0 at 390 min (16:00) and the 385->390 knot encodes the cliff.

Usage
-----
    python -m scripts.analysis.calibrate_intraday_theta \
        --tickers SPY IWM QQQ \
        --dates 2026-05-27 2026-05-29 2026-06-02 2026-06-04 2026-06-08 2026-06-10

Paste the printed BAKED KNOTS into ``lib/options_intraday.py``
(``_THETA_DECAY_KNOT_MIN`` / ``_THETA_DECAY_KNOT_G``) to refresh the runtime curve.
Re-run as more REALTIME sessions accrue to tighten the calibration.
"""
from __future__ import annotations

import argparse
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd

_RTH_OPEN_MIN = 9 * 60 + 30   # 09:30 ET
_RTH_SPAN_MIN = 390           # 09:30 -> 16:00

# Per-(ticker, date) ATM straddle time series. ATM via delta-bracketed argmin so
# stale penny wings don't win the minimum (empirically necessary — see docstring).
_STRADDLE_SQL = """
WITH paired AS (
    SELECT snapshot_ts, strike,
           max(mark) FILTER (WHERE option_type = 'calls') AS c,
           max(mark) FILTER (WHERE option_type = 'puts')  AS p
    FROM etf_options_snapshots
    WHERE ticker = :tkr
      AND market_session = 'REALTIME'
      AND snapshot_date = :d
      AND expiration = :d
      AND abs(delta) BETWEEN 0.15 AND 0.85
    GROUP BY snapshot_ts, strike
)
SELECT snapshot_ts, min(c + p) AS atm_straddle
FROM paired
WHERE c > 0.05 AND p > 0.05
GROUP BY snapshot_ts
ORDER BY snapshot_ts
"""


def fetch_atm_straddle(tickers: Iterable[str],
                       dates: Iterable[str]) -> pd.DataFrame:
    """Pull the per-(ticker, date) ATM straddle series from Cloud SQL.

    Returns a long DataFrame [tkr, d, snapshot_ts, atm_straddle]. Each (ticker,
    date) is queried independently so every scan stays inside one day's
    partition (a pooled multi-day scan of this table times out).
    """
    from gcp.database import query_to_dataframe

    frames: List[pd.DataFrame] = []
    for tkr in tickers:
        for d in dates:
            df = query_to_dataframe(_STRADDLE_SQL, {"tkr": tkr.upper(), "d": str(d)})
            if df is None or df.empty:
                continue
            df = df.assign(tkr=tkr.upper(), d=str(d))
            frames.append(df)
    if not frames:
        raise RuntimeError("No REALTIME straddle data returned for the requested "
                           "tickers/dates — cannot calibrate.")
    return pd.concat(frames, ignore_index=True)


def build_decay_curve(df: pd.DataFrame,
                      knot_step: int = 30) -> List[Tuple[int, float]]:
    """Pure: long ATM-straddle DataFrame -> monotone (minute, g) knot list.

    ``df`` columns: tkr, d, snapshot_ts (UTC), atm_straddle. Hermetic — no I/O.
    """
    df = df.copy()
    ts = pd.to_datetime(df["snapshot_ts"], utc=True).dt.tz_convert("America/New_York")
    df["minfo"] = ts.dt.hour * 60 + ts.dt.minute - _RTH_OPEN_MIN
    df = df[(df["minfo"] >= 0) & (df["minfo"] <= _RTH_SPAN_MIN)]

    curves = []
    for _, g in df.groupby(["tkr", "d"]):
        g = g.sort_values("minfo")
        base = g["atm_straddle"].iloc[0]
        if base <= 0.20:          # degenerate open — drop the session
            continue
        curves.append(g.assign(g_emp=1.0 - g["atm_straddle"] / base))
    if not curves:
        raise RuntimeError("All sessions had a degenerate open straddle.")
    alld = pd.concat(curves, ignore_index=True)

    alld["bin"] = (alld["minfo"] / knot_step).round() * knot_step
    agg = (alld.groupby("bin")["g_emp"].mean()
           .reindex(np.arange(0, _RTH_SPAN_MIN + 1, knot_step))
           .interpolate())
    gmono = np.maximum.accumulate(agg.values)

    knots: List[Tuple[int, float]] = [(0, 0.0)]
    for b, v in zip(agg.index[1:], gmono[1:]):
        if b >= _RTH_SPAN_MIN:
            continue
        knots.append((int(b), round(float(v), 4)))
    knots.append((_RTH_SPAN_MIN, 1.0))     # expiry pin / terminal cliff
    return knots


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", nargs="+", default=["SPY", "IWM", "QQQ"])
    ap.add_argument("--dates", nargs="+", required=True,
                    help="YYYY-MM-DD sessions with REALTIME 0DTE data")
    ap.add_argument("--knot-step", type=int, default=30)
    args = ap.parse_args(argv)

    df = fetch_atm_straddle(args.tickers, args.dates)
    n_sessions = df[["tkr", "d"]].drop_duplicates().shape[0]
    knots = build_decay_curve(df, knot_step=args.knot_step)

    print(f"Calibrated on {n_sessions} (ticker, session) curves "
          f"across tickers={args.tickers}")
    print("\n_THETA_DECAY_KNOT_MIN = " + repr([m for m, _ in knots]))
    print("_THETA_DECAY_KNOT_G   = " + repr([g for _, g in knots]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
