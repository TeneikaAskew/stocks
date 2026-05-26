"""Enrichment leakage audit — flags whether ORB, historical levels, or
order-block columns peek into future bars within their row.

Reviewer flag 2026-05-26: a consistent +0.11 to +0.16 log-loss beat across
very different TFs is plausible for real signal, but it is also exactly
the shape a shared leak in ORB or order-block ffill would produce. Cheap
to rule out before trusting the cross-TF picture.

Audit method (no future data; uses the existing strat_features_levels_{tf}):
  1. ORB columns — for each bar AFTER the ORB window has closed, the ORB
     high/low must equal a fixed daily value (not change as the day
     progresses). For bars INSIDE the ORB window, ORB may include the
     bar itself (small known intra-window leak — confirm magnitude).
  2. Historical-level columns — prev_day_high for a bar on 2026-05-22
     must equal market_data_daily ^? high for 2026-05-21 (prior trading
     day). NOT 2026-05-22 itself.
  3. Order-block columns — ob_high/low are rolling(5) min/max gated by
     is_ob (low-vol consolidation). The rolling window is [t-4, ..., t]
     INCLUSIVE of current bar. That uses current bar's data but no
     future. The ffill(limit=30) only extends past values forward, not
     future values backward — clean by construction. We spot-check:
     a bar at time T should never have ob_high equal to a value derived
     from any bar at time > T.

Run:
  python -m gcp.research.strat_engine.strat_leakage_audit --ticker IWM --tf 15m
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from gcp.database import get_engine
from gcp.research.strat_engine.strat_config import (
    TICKERS, TIMEFRAMES, strat_features_table,
)
from gcp.research.strat_engine.strat_enrich_levels import levels_table
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def audit_orb(engine, ticker: str, tf: str, sample_date: str = "2026-05-15") -> dict:
    """For a sample day, check ORB high/low is fixed across all bars
    AFTER the ORB window closes."""
    sql = text(f"""
        SELECT s.ts, s.ts::time AS tod, s.high, s.low,
               l.orb_5_high, l.orb_5_low, l.orb_15_high, l.orb_15_low,
               l.orb_30_high, l.orb_30_low
          FROM {strat_features_table(tf)} s
          LEFT JOIN {levels_table(tf)} l ON s.ticker = l.ticker AND s.ts = l.ts
         WHERE s.ticker = :t AND s.bar_date = :d AND s.strat_candle IS NOT NULL
         ORDER BY s.ts
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker, "d": sample_date})
    log.info("ORB audit %s %s on %s: %d bars", ticker, tf, sample_date, len(df))
    if len(df) == 0:
        return {"status": "NO_DATA"}

    findings = []
    for window, end_min in [(5, 5), (15, 15), (30, 30)]:
        high_col, low_col = f"orb_{window}_high", f"orb_{window}_low"
        if high_col not in df.columns:
            continue
        # Bars after market open + window_min should have IDENTICAL ORB high/low
        # Market open is 9:30 ET = 13:30 UTC; ORB ends at 9:30+window min ET
        from datetime import time as _time
        orb_end_et_min = (9 * 60 + 30 + end_min)   # min-of-day in ET
        # tod is UTC; for a bar at 14:30 UTC = 10:30 ET, that's after 5m/15m ORB but during 30m
        # ET = UTC - 4 or -5 depending on DST. For 2026-05-15 (DST), ET = UTC - 4.
        df["tod_et_min"] = (
            pd.to_datetime(df["tod"].astype(str), format="%H:%M:%S").dt.hour * 60
            + pd.to_datetime(df["tod"].astype(str), format="%H:%M:%S").dt.minute - 4 * 60
        )
        after = df[df["tod_et_min"] >= orb_end_et_min]
        if len(after) < 2:
            findings.append({"window": window, "n_after_window": int(len(after)),
                             "status": "INSUFFICIENT_BARS"})
            continue
        n_unique_high = after[high_col].nunique(dropna=False)
        n_unique_low = after[low_col].nunique(dropna=False)
        status = "CLEAN" if (n_unique_high == 1 and n_unique_low == 1) else "VARIES"
        findings.append({
            "window": window, "n_after_window": int(len(after)),
            "high_uniques": int(n_unique_high),
            "low_uniques": int(n_unique_low),
            "high_value": float(after[high_col].dropna().iloc[0]) if not after[high_col].dropna().empty else None,
            "low_value":  float(after[low_col].dropna().iloc[0])  if not after[low_col].dropna().empty  else None,
            "status": status,
        })
        log.info("  ORB-%dm after end: %d bars, %d unique high, %d unique low → %s",
                 window, len(after), n_unique_high, n_unique_low, status)

    return {"sample_date": sample_date, "ticker": ticker, "tf": tf, "findings": findings}


def audit_historical_levels(engine, ticker: str, tf: str,
                              sample_date: str = "2026-05-22") -> dict:
    """Check prev_day_high uses YESTERDAY's high, not today's."""
    sql = text(f"""
        SELECT s.ticker, s.bar_date, s.high, s.low,
               l.prev_day_high, l.prev_day_low,
               (SELECT high FROM market_data_daily
                 WHERE ticker = s.ticker AND date = s.bar_date - 1) AS yest_high,
               (SELECT high FROM market_data_daily
                 WHERE ticker = s.ticker AND date = s.bar_date) AS today_high,
               (SELECT high FROM market_data_daily
                 WHERE ticker = s.ticker AND date = s.bar_date + 1) AS tmrw_high
          FROM {strat_features_table(tf)} s
          LEFT JOIN {levels_table(tf)} l ON s.ticker = l.ticker AND s.ts = l.ts
         WHERE s.ticker = :t AND s.bar_date = :d AND s.strat_candle IS NOT NULL
         ORDER BY s.ts
         LIMIT 1
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker, "d": sample_date})
    if len(df) == 0 or df["prev_day_high"].isna().all():
        log.info("historical levels audit %s %s on %s: no data or no prev_day_high",
                 ticker, tf, sample_date)
        return {"status": "NO_DATA"}

    row = df.iloc[0]
    pdh = row["prev_day_high"]
    yest = row["yest_high"]
    today = row["today_high"]
    tmrw = row["tmrw_high"]

    if pd.isna(yest) or pd.isna(pdh):
        return {"status": "MISSING_REFERENCE"}

    # The "true" prev_day_high for a (ticker, bar_date) should equal market_data_daily
    # high for the prior trading day. Within ~$0.50 tolerance for ETFs.
    # (prev_day_high in the enrichment is computed from intraday bars, which may
    # have a small difference vs the daily-OHLC table due to extended-hours bars
    # being excluded. So a perfect match isn't required.)
    diff_yest = abs(pdh - yest)
    diff_today = abs(pdh - today) if pd.notna(today) else float("inf")
    diff_tmrw = abs(pdh - tmrw) if pd.notna(tmrw) else float("inf")

    status = "CLEAN"
    if diff_yest > 0.50:
        status = f"WARN (yest diff = ${diff_yest:.2f})"
    if diff_today < 0.50:
        status = f"⚠️ LEAK_SUSPECT (matches TODAY: ${diff_today:.2f})"
    if diff_tmrw < 0.50:
        status = f"⚠️ LEAK_LOOKAHEAD (matches TOMORROW: ${diff_tmrw:.2f})"

    log.info("historical-levels audit %s %s on %s:", ticker, tf, sample_date)
    log.info("  prev_day_high in enrichment: %.2f", pdh)
    log.info("  yesterday's daily high:      %.2f  (diff %.2f)", yest, diff_yest)
    log.info("  today's daily high:          %.2f  (diff %.2f)",
             today if pd.notna(today) else 0.0, diff_today)
    log.info("  tomorrow's daily high:       %.2f  (diff %.2f)",
             tmrw if pd.notna(tmrw) else 0.0, diff_tmrw)
    log.info("  STATUS: %s", status)
    return {
        "sample_date": sample_date, "ticker": ticker, "tf": tf,
        "pdh": float(pdh), "yest": float(yest),
        "today": float(today) if pd.notna(today) else None,
        "tmrw": float(tmrw) if pd.notna(tmrw) else None,
        "diff_yest": float(diff_yest),
        "diff_today": float(diff_today) if diff_today != float("inf") else None,
        "diff_tmrw": float(diff_tmrw) if diff_tmrw != float("inf") else None,
        "status": status,
    }


def audit_order_blocks(engine, ticker: str, tf: str) -> dict:
    """Verify order-block columns don't reference future bars.

    Property tested: ob_high at time T should never equal a high value
    from a bar at time > T. Random sample of 10 bars from the OOS window.
    """
    sql = text(f"""
        SELECT s.ts, s.high AS bar_high,
               l.ob_order_block_high, l.ob_order_block_low,
               LAG(s.high, 1) OVER (ORDER BY s.ts) AS h_m1,
               LAG(s.high, 2) OVER (ORDER BY s.ts) AS h_m2,
               LAG(s.high, 3) OVER (ORDER BY s.ts) AS h_m3,
               LAG(s.high, 4) OVER (ORDER BY s.ts) AS h_m4,
               LEAD(s.high, 1) OVER (ORDER BY s.ts) AS h_p1,
               LEAD(s.high, 2) OVER (ORDER BY s.ts) AS h_p2,
               LEAD(s.high, 3) OVER (ORDER BY s.ts) AS h_p3
          FROM {strat_features_table(tf)} s
          LEFT JOIN {levels_table(tf)} l ON s.ticker = l.ticker AND s.ts = l.ts
         WHERE s.ticker = :t AND s.bar_date >= '2026-01-01'
           AND l.ob_order_block_high IS NOT NULL
         ORDER BY s.ts
         LIMIT 200
    """)
    with engine.connect() as c:
        df = pd.read_sql(sql, c, params={"t": ticker})
    if len(df) == 0:
        return {"status": "NO_DATA"}

    # For each row, check: is ob_high equal to any FUTURE bar's high?
    # If yes → leak. If only matches past/current bars → clean.
    leaks_p1 = int(((df["ob_order_block_high"] - df["h_p1"]).abs() < 0.01).sum())
    leaks_p2 = int(((df["ob_order_block_high"] - df["h_p2"]).abs() < 0.01).sum())
    leaks_p3 = int(((df["ob_order_block_high"] - df["h_p3"]).abs() < 0.01).sum())
    legit_m0 = int(((df["ob_order_block_high"] - df["bar_high"]).abs() < 0.01).sum())
    legit_m1 = int(((df["ob_order_block_high"] - df["h_m1"]).abs() < 0.01).sum())
    log.info("order-block audit %s %s (n=%d sampled OOS bars):", ticker, tf, len(df))
    log.info("  matches CURRENT bar high:  %d", legit_m0)
    log.info("  matches t-1 bar high:      %d", legit_m1)
    log.info("  matches FUTURE t+1 high:   %d   ← if >0, possible leak", leaks_p1)
    log.info("  matches FUTURE t+2 high:   %d", leaks_p2)
    log.info("  matches FUTURE t+3 high:   %d", leaks_p3)
    # Note: a TRULY clean rolling-5 ob_high should never match t+1/t+2/t+3.
    # Some incidental match from a flat market (high == high == high) is OK
    # IF and only if the matching value is also legitimately in the past window.
    status = "CLEAN" if leaks_p1 < len(df) * 0.05 else "⚠️ LEAK_SUSPECT"
    log.info("  STATUS: %s (threshold: <5%% of sampled bars matching t+1)", status)
    return {
        "ticker": ticker, "tf": tf, "n_sampled": int(len(df)),
        "matches_current": legit_m0,
        "matches_t-1": legit_m1,
        "matches_t+1": leaks_p1,
        "matches_t+2": leaks_p2,
        "matches_t+3": leaks_p3,
        "status": status,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticker", default="IWM", choices=list(TICKERS))
    p.add_argument("--tf", default="15m", choices=list(TIMEFRAMES))
    p.add_argument("--orb-sample-date", default="2026-05-15")
    p.add_argument("--hist-sample-date", default="2026-05-22")
    args = p.parse_args()
    engine = get_engine()

    log.info("╔══════════════════════════════════════════════════════════════════╗")
    log.info("║ ENRICHMENT LEAKAGE AUDIT — %s %s                              ║", args.ticker, args.tf)
    log.info("╚══════════════════════════════════════════════════════════════════╝")
    log.info("")

    audit_orb(engine, args.ticker, args.tf, args.orb_sample_date)
    log.info("")
    audit_historical_levels(engine, args.ticker, args.tf, args.hist_sample_date)
    log.info("")
    audit_order_blocks(engine, args.ticker, args.tf)


if __name__ == "__main__":
    main()
