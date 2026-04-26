#!/usr/bin/env python3
"""
Cloud Run Job: Fetch macroeconomic rate inputs from FRED into Cloud SQL.

Series fetched
--------------
1. ``DGS3MO``     3-month Treasury constant-maturity rate. The risk-free rate
                  ``r`` for Black-Scholes-Merton Greeks computation. Daily.
2. ``SP500``      S&P 500 daily close. Written to ``market_data_daily`` with
                  ``ticker='SPX'`` so the spot-price lookup used by
                  ``lib.options_greeks.enrich_av_chain_with_greeks`` returns a
                  real value for SPX (AlphaVantage ``TIME_SERIES_DAILY`` does
                  not cover index symbols).

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

    # Single-series mode (testing)
    python -m gcp.fetchers.fetch_fred_rates --series DGS3MO --backfill
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


def fetch_sp500(api_key: str, start: str, end: str) -> pd.DataFrame:
    """Pull S&P 500 daily close.

    FRED's ``SP500`` series is close-only (no OHLV, no volume). Returns a
    DataFrame ready to upsert into ``market_data_daily`` with ``ticker='SPX'``.
    """
    df = _fred_observations("SP500", api_key, start, end)
    if df.empty:
        return df
    df = df.rename(columns={"value": "close"})
    df["ticker"] = "SPX"
    df["adjusted_close"] = df["close"]   # indexes are total-return, no split adjustment
    df["data_source"] = "fred"
    # market_data_daily allows nullable open/high/low/volume — no need to fill.
    return df[["ticker", "date", "close", "adjusted_close", "data_source"]]


def upsert_daily_rates(df_dgs: pd.DataFrame, div_yld: float) -> int:
    """Merge DGS3MO into daily_rates, populating sp500_div_yld with the
    configured default. Idempotent; safe to re-run for the same dates.
    """
    if df_dgs.empty:
        return 0
    out = df_dgs.copy()
    out["sp500_div_yld"] = div_yld
    return upsert_dataframe(out, "daily_rates", conflict_cols=["date"])


def upsert_spx_close(df_sp500: pd.DataFrame) -> int:
    """Upsert SP500 close into market_data_daily as ticker='SPX'."""
    if df_sp500.empty:
        return 0
    return upsert_dataframe(
        df_sp500, "market_data_daily", conflict_cols=["ticker", "date"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch FRED macro rates → Cloud SQL daily_rates + SPX prices.",
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
        "--series", default="ALL",
        choices=["ALL", "DGS3MO", "SP500"],
        help="Restrict to a single series (debugging).",
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

    log.info("FRED rates fetch: %s → %s (series=%s, div_yld=%.4f)",
             start, end, args.series, args.div_yield)

    n_rates = n_spx = 0

    if args.series in ("ALL", "DGS3MO"):
        df_dgs = fetch_dgs3mo(api_key, start, end)
        n_rates = upsert_daily_rates(df_dgs, div_yld=args.div_yield)
        log.info("daily_rates upserted: %d rows", n_rates)

    if args.series in ("ALL", "SP500"):
        df_sp = fetch_sp500(api_key, start, end)
        n_spx = upsert_spx_close(df_sp)
        log.info("market_data_daily(SPX) upserted: %d rows", n_spx)

    log.info("Done. daily_rates=%d, spx_close=%d", n_rates, n_spx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
