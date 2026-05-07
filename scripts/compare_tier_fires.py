"""One-off: compare per-ticker fire counts under Tier-A vs Tier-B RSI ranges.

Loads 1-min bars for each ticker from market_data_intraday for the last
N days, computes RSI/StochRSI/etc. via lib.indicators, and runs the same
condition-check helpers used by mean_reversion.py and momentum.py
TWICE per bar — once with the universal Tier-B range, once with the
Tier-A range resolved from ticker_calibration. Reports per-ticker fire-
count deltas so we can gate the per-ticker calibration PR on the
"<50% fire-count change" acceptance threshold.

This bypasses SignalMonitor's full orchestration (window updates,
agreement detection, Discord alerts, persistence) — it just counts how
many bars produce score >= MIN_CONDITIONS under each range definition.
That's a proxy for fire-count impact: if "in range" % drops by X for a
ticker, fire count drops by AT MOST X (other conditions can compensate
upward but never increase RSI's own contribution).

Usage (as Cloud Run Job):
    gcloud run jobs execute compare-tier-fires --wait
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp.database import get_engine, is_cloud_sql_configured  # noqa: E402
from lib.indicators import add_all_indicators  # noqa: E402
from lib.strategies import momentum, mean_reversion  # noqa: E402
from lib.strategies.config import (  # noqa: E402
    CALL_RSI_RANGE, PUT_RSI_RANGE,
    MIN_CONDITIONS,           # mean_reversion threshold (3)
    MIN_CONDITIONS_MOMENTUM,  # momentum threshold (5, B+ phase-0.7.6)
)
from lib.strategies.calibration import (  # noqa: E402
    get_call_rsi_range, get_put_rsi_range, _latest_calibration,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("compare_tier_fires")


def load_bars(engine, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    sql = text("""
        SELECT ts AS "Time",
               open AS "Open",
               high AS "High",
               low AS "Low",
               close AS "Close",
               volume AS "Volume"
        FROM market_data_intraday
        WHERE ticker = :t
          AND ts >= :start AND ts < :end
          AND interval = '1min'
        ORDER BY ts
    """)
    df = pd.read_sql(sql, engine, params={"t": ticker.upper(), "start": start, "end": end})
    df["Time"] = pd.to_datetime(df["Time"])
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add the indicator columns the strategies expect.

    Routes through `lib.indicators.add_all_indicators` so the enrichment
    matches what `lib/strategies/momentum.py` reads — including the four
    Phase 0.7.x derived columns (`Consecutive_Up_5`/`Down_5`,
    `RVol_Recent_20`, `ATR_Expansion`, `RSI_Thrust_3`) that the new
    momentum confirmer conditions credit. Without these, momentum scores
    cap below `MIN_CONDITIONS_MOMENTUM=5` and the script under-reports
    fire counts (Codex P2 review on PR #280).
    """
    enriched = add_all_indicators(df, close_col="Close")
    # Compatibility aliases the rest of the script reads:
    if "RSI14_W" not in enriched.columns and "RSI14" in enriched.columns:
        enriched["RSI14_W"] = enriched["RSI14"]
    if "RSI14" not in enriched.columns and "RSI14_W" in enriched.columns:
        enriched["RSI14"] = enriched["RSI14_W"]
    if "Broke_Prev_Day_High" not in enriched.columns:
        enriched["Broke_Prev_Day_High"] = 0
    if "Broke_Prev_Day_Low" not in enriched.columns:
        enriched["Broke_Prev_Day_Low"] = 0
    return enriched


def count_fires_for_ranges(
    df: pd.DataFrame, call_range: tuple, put_range: tuple,
) -> dict:
    """Count how many bars would fire CALL/PUT in each strategy under the
    given ranges. Mirrors the score-aggregation logic in
    momentum.MomentumStrategy.evaluate / mean_reversion.MeanReversionStrategy.
    """
    out = {
        "momentum_call": 0, "momentum_put": 0,
        "mr_call":       0, "mr_put":       0,
        "bars_with_rsi_in_call_range": 0,
        "bars_with_rsi_in_put_range":  0,
    }

    for _, row in df.iterrows():
        rsi = row.get("RSI14_W")
        if pd.isna(rsi) or pd.isna(row.get("StochRSI_K")):
            continue

        if call_range[0] < rsi < call_range[1]:
            out["bars_with_rsi_in_call_range"] += 1
        if put_range[0] < rsi < put_range[1]:
            out["bars_with_rsi_in_put_range"] += 1

        # Momentum — gated by MIN_CONDITIONS_MOMENTUM (B+ phase-0.7.6: 5)
        m_call_score, _ = momentum._check_call_conditions(row, call_range)
        m_put_score,  _ = momentum._check_put_conditions(row, put_range)
        if m_call_score >= MIN_CONDITIONS_MOMENTUM and m_call_score > m_put_score:
            out["momentum_call"] += 1
        elif m_put_score >= MIN_CONDITIONS_MOMENTUM and m_put_score > m_call_score:
            out["momentum_put"] += 1

        # Mean reversion — gated by the original MIN_CONDITIONS (3)
        mr_call_score, _ = mean_reversion._check_call_conditions(row, call_range)
        mr_put_score,  _ = mean_reversion._check_put_conditions(row, put_range)
        if mr_call_score >= MIN_CONDITIONS and mr_call_score >= mr_put_score:
            out["mr_call"] += 1
        elif mr_put_score >= MIN_CONDITIONS:
            out["mr_put"] += 1

    return out


def pct_delta(new: int, old: int) -> str:
    if old == 0:
        return "n/a (baseline=0)"
    delta = (new - old) / old * 100.0
    return f"{delta:+.1f}%"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", default="SPY,QQQ,IWM")
    p.add_argument("--days", type=int, default=90)
    args = p.parse_args()

    if not is_cloud_sql_configured():
        log.error("Cloud SQL env vars missing — aborting.")
        sys.exit(2)

    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    log.info("window: %s → %s (%d days)", start.date(), end.date(), args.days)

    engine = get_engine()
    tickers = [t.strip().upper() for t in args.tickers.split(",")]

    rows = []
    for ticker in tickers:
        log.info("→ %s", ticker)
        bars = load_bars(engine, ticker, start, end)
        if bars.empty:
            log.warning("  no bars for %s; skipping", ticker)
            continue
        log.info("  loaded %d bars", len(bars))

        enriched = enrich(bars)

        tier_b_call = CALL_RSI_RANGE
        tier_b_put = PUT_RSI_RANGE
        tier_a_call = get_call_rsi_range(ticker)
        tier_a_put = get_put_rsi_range(ticker)
        cal_row = _latest_calibration(ticker)
        cal_date = cal_row["calibration_date"] if cal_row else None

        log.info("  Tier-B call=%s put=%s", tier_b_call, tier_b_put)
        log.info("  Tier-A call=%s put=%s (cal=%s)", tier_a_call, tier_a_put, cal_date)

        b = count_fires_for_ranges(enriched, tier_b_call, tier_b_put)
        a = count_fires_for_ranges(enriched, tier_a_call, tier_a_put)

        rows.append({
            "ticker": ticker,
            "bars": len(enriched),
            "calibration_date": str(cal_date) if cal_date else None,
            "tier_b_call_range": list(tier_b_call),
            "tier_b_put_range": list(tier_b_put),
            "tier_a_call_range": list(tier_a_call),
            "tier_a_put_range": list(tier_a_put),
            "tier_b": b,
            "tier_a": a,
            "delta_pct": {
                k: pct_delta(a[k], b[k]) for k in (
                    "momentum_call", "momentum_put", "mr_call", "mr_put",
                    "bars_with_rsi_in_call_range", "bars_with_rsi_in_put_range",
                )
            },
        })

    log.info("\n========= SUMMARY =========")
    log.info(json.dumps(rows, indent=2, default=str))
    print("\n=== JSON_RESULTS_BEGIN ===")
    print(json.dumps(rows, indent=2, default=str))
    print("=== JSON_RESULTS_END ===")


if __name__ == "__main__":
    main()
