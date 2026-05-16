#!/usr/bin/env python3
"""
Cloud Run Job: Fetch the FRED 3-month Treasury rate into Cloud SQL.

Series fetched
--------------
1. ``DGS3MO``     3-month Treasury constant-maturity rate. The risk-free rate
                  ``r`` for Black-Scholes-Merton Greeks computation. Daily.

This job used to ALSO pull the FRED ``SP500`` series and write it to
``market_data_daily`` with ``ticker='SPX'``. That was removed 2026-05-15:
FRED's ``SP500`` is close-only (no OHLV, no volume) and publishes 1-2
trading days late, so it was never real market data — just a stale
spot-price stand-in. The SPX options Greeks path
(``lib.options_greeks.enrich_av_chain_with_greeks``) derives spot from
the live option chain via put-call parity, which is same-day and exact;
it does not need a ``market_data_daily`` SPX row. Do NOT re-add an
``SP500 → SPX`` write here — index price data does not belong in a FRED
macro-rates fetcher.

Dividend yield ``q`` is NOT pulled from FRED — the agency does not publish a
clean S&P 500 dividend-yield series. Instead we write a configurable constant
into ``daily_rates.sp500_div_yld`` so the lookup interface stays uniform.
This default lives in :data:`SP500_DIV_YIELD_DEFAULT`. Adjust quarterly or
swap to a scraped source later without touching call sites.

Usage
-----
    # Full backfill (FRED returns ~3000 daily rows for DGS3MO since 2015)
    python -m gcp.fetchers.fetch_fred_rates --backfill

    # Daily incremental — pulls last 14 days only
    python -m gcp.fetchers.fetch_fred_rates
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import is_cloud_sql_configured, upsert_dataframe
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_BACKFILL_START = "2015-01-02"  # matches AV options backfill window

# Default S&P 500 trailing 12-month dividend yield used to populate
# daily_rates.sp500_div_yld until/unless a richer source is wired in.
# Update quarterly. Source: WSJ market data → S&P 500 yield, last reviewed
# 2026-04. BSM Greeks are weakly sensitive to a ~20bp drift in q.
SP500_DIV_YIELD_DEFAULT = 0.013


def _fred_observations(series_id: str, api_key: str,
                       start: str, end: str) -> pd.DataFrame:
    """Fetch a FRED series as a DataFrame with columns ['date','value'].

    Returns empty on any error. Treats the FRED placeholder '.' (no data
    published for the date) as a missing value and drops it.
    """
    params = {
        "api_key": api_key,
        "file_type": "json",
        "series_id": series_id,
        "observation_start": start,
        "observation_end": end,
    }
    try:
        resp = requests.get(FRED_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("FRED fetch failed for %s: %s", series_id, exc)
        return pd.DataFrame()

    rows = data.get("observations", [])
    if not rows:
        log.warning("FRED returned 0 observations for %s [%s..%s]",
                    series_id, start, end)
        return pd.DataFrame()

    df = pd.DataFrame(rows)[["date", "value"]]
    # FRED uses '.' for missing
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    log.info("FRED %s: %d observations [%s..%s]",
             series_id, len(df), df["date"].min(), df["date"].max())
    return df


def fetch_dgs3mo(api_key: str, start: str, end: str) -> pd.DataFrame:
    """Pull DGS3MO and convert percent to decimal (4.45 → 0.0445)."""
    df = _fred_observations("DGS3MO", api_key, start, end)
    if df.empty:
        return df
    df["dgs3mo"] = df["value"] / 100.0  # FRED returns percent units
    return df[["date", "dgs3mo"]]


def upsert_daily_rates(df_dgs: pd.DataFrame, div_yld: float) -> int:
    """Merge DGS3MO into daily_rates, populating sp500_div_yld with the
    configured default. Idempotent; safe to re-run for the same dates.
    """
    if df_dgs.empty:
        return 0
    out = df_dgs.copy()
    out["sp500_div_yld"] = div_yld
    return upsert_dataframe(out, "daily_rates", conflict_cols=["date"])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the FRED 3-month Treasury rate → Cloud SQL daily_rates.",
    )
    parser.add_argument(
        "--backfill", action="store_true",
        help=f"Pull from {FRED_BACKFILL_START} to today instead of the 14-day "
             "incremental window.",
    )
    parser.add_argument(
        "--start", default=None,
        help="Custom start date YYYY-MM-DD (overrides --backfill).",
    )
    parser.add_argument(
        "--end", default=None,
        help="Custom end date YYYY-MM-DD. Defaults to today.",
    )
    parser.add_argument(
        "--div-yield", type=float, default=SP500_DIV_YIELD_DEFAULT,
        help=f"S&P 500 dividend yield to write into daily_rates.sp500_div_yld "
             f"(default {SP500_DIV_YIELD_DEFAULT}).",
    )
    args = parser.parse_args()

    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        log.error("FRED_API_KEY not set in environment")
        return 2

    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured — cannot upsert")
        return 2

    today = date.today()
    if args.start:
        start = args.start
    elif args.backfill:
        start = FRED_BACKFILL_START
    else:
        start = (today - timedelta(days=14)).isoformat()
    end = args.end or today.isoformat()

    log.info("FRED rates fetch: %s → %s (div_yld=%.4f)",
             start, end, args.div_yield)

    df_dgs = fetch_dgs3mo(api_key, start, end)
    n_rates = upsert_daily_rates(df_dgs, div_yld=args.div_yield)
    log.info("daily_rates upserted: %d rows", n_rates)
    log.info("Done. daily_rates=%d", n_rates)
    return 0


if __name__ == "__main__":
    sys.exit(main())
