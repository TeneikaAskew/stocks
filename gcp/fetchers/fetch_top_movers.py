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
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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

_ET = ZoneInfo("America/New_York")


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


def _parse_intraday_row(item: dict, rank: int) -> dict | None:
    """Parse one `most_actively_traded` row into an intraday snapshot row.

    Wire format is all-strings, e.g.
    {"ticker":"BURU","price":"0.1516","change_amount":"0.0104",
     "change_percentage":"7.3654%","volume":"72424171"} — negatives look
    like "-1.84%".

    Returns None (and logs a warning) for a malformed row rather than
    fabricating a value (Rule 3.7). A field is "malformed" when the raw
    value is present/non-empty but fails to parse — that indicates
    corrupt upstream data, distinct from a legitimately-missing optional
    field (which stays None/NULL, same as the daily table).
    """
    tk = (item.get("ticker") or "").upper().strip()
    if not tk:
        log.warning("Skipping malformed most_actively_traded row (no ticker): %r", item)
        return None

    raw_price = item.get("price")
    raw_change_amount = item.get("change_amount")
    raw_change_pct = item.get("change_percentage")
    raw_volume = item.get("volume")

    price = _safe_float(raw_price)
    change_amount = _safe_float(raw_change_amount)
    change_pct = _safe_pct(raw_change_pct)
    volume_f = _safe_float(raw_volume)

    def _unparseable(raw, parsed) -> bool:
        return raw not in (None, "", "None") and parsed is None

    if (
        _unparseable(raw_price, price)
        or _unparseable(raw_change_amount, change_amount)
        or _unparseable(raw_change_pct, change_pct)
        or _unparseable(raw_volume, volume_f)
    ):
        log.warning(
            "Skipping malformed most_actively_traded row for ticker=%s: %r", tk, item
        )
        return None

    return {
        "rank": rank,
        "ticker": tk,
        "price": price,
        "change_amount": change_amount,
        "change_pct": change_pct,
        "volume": int(volume_f) if volume_f is not None else None,
    }


def fetch_intraday_snapshot(api_key: str) -> pd.DataFrame:
    """Pull the current `most_actively_traded` snapshot for the hourly
    most-active marquee bar.

    Unlike `fetch_top_movers` (which swallows AV failures into an empty
    DataFrame for the daily path — pre-existing behavior, left
    untouched), this function RAISES on any AV failure. The job runs
    hourly with max-retries=0 upstream; an hourly gap is acceptable and
    visible in Cloud Run logs, but a silently-empty "success" is not
    (Rule 3.7 — no silent fallbacks).
    """
    params = {"function": "TOP_GAINERS_LOSERS", "apikey": api_key}
    resp = requests.get(AV_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "Information" in data:
        raise RuntimeError(
            f"AV TOP_GAINERS_LOSERS returned an Information payload "
            f"(rate limit or bad key?): {data['Information']}"
        )

    if "most_actively_traded" not in data:
        raise RuntimeError(
            f"AV TOP_GAINERS_LOSERS response missing 'most_actively_traded' "
            f"key; keys={sorted(data.keys())}"
        )

    # One snapshot_ts for the whole batch — explicitly tz-aware. See the
    # documented naive-datetime.now() UTC incident this repo already hit
    # (gcp/fetchers/fetch_market_data.py tz fix / tests/gcp/test_fetch_market_data_tz.py).
    snapshot_ts = datetime.now(timezone.utc)
    snapshot_date = snapshot_ts.astimezone(_ET).date()

    items = data["most_actively_traded"] or []
    rows = []
    for rank, item in enumerate(items, start=1):
        parsed = _parse_intraday_row(item, rank)
        if parsed is None:
            continue
        parsed["snapshot_ts"] = snapshot_ts
        parsed["snapshot_date"] = snapshot_date
        rows.append(parsed)

    df = pd.DataFrame(rows)
    log.info("  most_active (intraday snapshot): %d/%d rows parsed", len(df), len(items))

    # Dedupe on ticker, keeping the first (lowest rank) occurrence. AlphaVantage
    # occasionally returns the same ticker twice; without this guard, the
    # multi-row ON CONFLICT DO UPDATE upsert would fail with Postgres 21000
    # ("cannot affect row a second time") since snapshot_ts is constant per
    # batch. See the daily path at line ~261 for the precedent.
    rows_before_dedup = len(df)
    df = df.drop_duplicates(subset=["ticker"], keep="first")
    if len(df) < rows_before_dedup:
        dropped = rows_before_dedup - len(df)
        log.warning(
            "Deduplicated %d repeated ticker(s) in intraday snapshot; "
            "kept first occurrence of each",
            dropped
        )

    return df


def main():
    parser = argparse.ArgumentParser(description="Fetch TOP_GAINERS_LOSERS → Cloud SQL")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--intraday-snapshot",
        action="store_true",
        help=(
            "Fetch only most_actively_traded (hourly cadence) and persist "
            "to top_movers_intraday instead of the daily top_movers_daily path."
        ),
    )
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch top movers")
        sys.exit(1)

    if args.intraday_snapshot:
        log.info("Top Movers Intraday Snapshot Job")
        log.info("  SQL : %s", "yes" if is_cloud_sql_configured() else "NO")

        df = fetch_intraday_snapshot(api_key)
        log.info("Total rows: %d", len(df))

        if args.dry_run:
            with pd.option_context("display.max_rows", 30, "display.max_colwidth", 30):
                print(df.to_string(index=False))
            print(f"\n[dry-run] {len(df)} rows — not written to DB")
            return

        if df.empty:
            log.warning("No most_actively_traded rows in this snapshot")
            return

        if is_cloud_sql_configured():
            n = upsert_dataframe(
                df, "top_movers_intraday",
                ["snapshot_ts", "ticker"],
            )
            log.info("✓ upserted %d rows to top_movers_intraday", n)
            print(f"Persisted {n} top_movers_intraday rows to Cloud SQL")
        else:
            log.warning("Cloud SQL not configured — skipping persist")
        return

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
