#!/usr/bin/env python3
"""
Cloud Run Job: Fetch AV TOP_GAINERS_LOSERS daily snapshot → Cloud SQL.

One AV call returns three lists for the current trading session:
  * top_gainers   — biggest % movers up
  * top_losers    — biggest % movers down
  * most_actively_traded — highest volume

Used by the ranker as a "what moved today regardless of cause" signal.
Tickers in these lists almost always have a catalyst behind them, even
when the news article hasn't been ingested yet — useful for catching
setups in names that just had something happen.

Usage:
    python -m gcp.fetchers.fetch_top_movers
    python -m gcp.fetchers.fetch_top_movers --dry-run
"""

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = "https://www.alphavantage.co/query"
CATEGORIES = (
    ("top_gainers", "top_gainers"),
    ("top_losers", "top_losers"),
    ("most_actively_traded", "most_active"),
)


def _safe_float(val) -> float | None:
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_pct(val) -> float | None:
    """Parse AV's '5.42%' string into 5.42."""
    if val is None or val == "":
        return None
    s = str(val).strip().rstrip("%")
    return _safe_float(s)


def fetch_top_movers(api_key: str) -> pd.DataFrame:
    """Pull the daily TOP_GAINERS_LOSERS snapshot and explode into rows."""
    params = {"function": "TOP_GAINERS_LOSERS", "apikey": api_key}
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error("AV TOP_GAINERS_LOSERS request failed: %s", e)
        return pd.DataFrame()

    if "Information" in data:
        log.warning("AV info: %s", data["Information"])
        return pd.DataFrame()

    snapshot_date = date.today()
    rows = []
    for av_key, our_category in CATEGORIES:
        items = data.get(av_key) or []
        for rank, item in enumerate(items, start=1):
            tk = (item.get("ticker") or "").upper().strip()
            if not tk:
                continue
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "ticker": tk,
                    "category": our_category,
                    "rank": rank,
                    "price": _safe_float(item.get("price")),
                    "change_amount": _safe_float(item.get("change_amount")),
                    "change_pct": _safe_pct(item.get("change_percentage")),
                    "volume": int(_safe_float(item.get("volume")) or 0) or None,
                }
            )
        log.info("  %s: %d rows", our_category, len(items))

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Fetch TOP_GAINERS_LOSERS → Cloud SQL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch top movers")
        sys.exit(1)

    log.info("Top Movers Fetch Job")
    log.info("  SQL : %s", "yes" if is_cloud_sql_configured() else "NO")

    df = fetch_top_movers(api_key)
    if df.empty:
        log.warning("No top movers data fetched")
        return

    df = df.drop_duplicates(
        subset=["snapshot_date", "ticker", "category"], keep="last"
    )
    log.info("Total rows: %d", len(df))

    if args.dry_run:
        with pd.option_context("display.max_rows", 60, "display.max_colwidth", 30):
            print(df.to_string(index=False))
        print(f"\n[dry-run] {len(df)} rows — not written to DB")
        return

    if is_cloud_sql_configured():
        n = upsert_dataframe(
            df, "top_movers_daily",
            ["snapshot_date", "ticker", "category"],
        )
        log.info("✓ upserted %d rows to top_movers_daily", n)
        print(f"Persisted {n} top_movers_daily rows to Cloud SQL")
    else:
        log.warning("Cloud SQL not configured — skipping persist")


if __name__ == "__main__":
    main()
