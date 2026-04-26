#!/usr/bin/env python3
"""
Cloud Run Job: Fetch historical quarterly earnings from AV EARNINGS → Cloud SQL.

This is the *backward-looking* counterpart to fetch_earnings_calendar
(which pulls forward-only upcoming earnings). The AV `EARNINGS` endpoint
returns quarterly EPS history per ticker — `reportedDate`, `reportedEPS`,
`estimatedEPS`, `surprise`, `surprisePercentage` — going back 10+ years.

Used by the upcoming ranker to compute historical post-earnings reaction
stats (avg T+1 move, direction consistency, beat/miss streaks).

Ticker source priority:
  1. CLI --tickers override
  2. Cloud SQL earnings_calendar table — anyone reporting in the next
     ``--lookahead-days`` (default 90). Captures every name we'd want
     to rank without us maintaining a separate watchlist.

Usage:
    python -m gcp.fetchers.fetch_earnings_history
    python -m gcp.fetchers.fetch_earnings_history --tickers AAPL,MSFT,AVGO
    python -m gcp.fetchers.fetch_earnings_history --lookahead-days 30 --dry-run
"""

import argparse
import logging
import os
import sys
import time as time_module
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.config import AlphaVantageConfig
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = "https://www.alphavantage.co/query"
_av_cfg = AlphaVantageConfig()


def _safe_float(val) -> float | None:
    if val is None or val == "None" or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def fetch_history_for_ticker(ticker: str, api_key: str) -> pd.DataFrame:
    """Pull AV EARNINGS for one ticker; return rows for `quarterlyEarnings`."""
    params = {"function": "EARNINGS", "symbol": ticker.upper(), "apikey": api_key}
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("    AV EARNINGS request failed for %s: %s", ticker, e)
        return pd.DataFrame()

    if "Information" in data:
        log.warning("    AV info for %s: %s", ticker, data["Information"])
        return pd.DataFrame()

    quarterly = data.get("quarterlyEarnings") or []
    if not quarterly:
        log.info("    No quarterly history for %s", ticker)
        return pd.DataFrame()

    rows = []
    for q in quarterly:
        fiscal = q.get("fiscalDateEnding")
        reported = q.get("reportedDate")
        if not fiscal:
            continue
        rows.append(
            {
                "ticker": ticker.upper(),
                "fiscal_date_ending": pd.to_datetime(fiscal).date(),
                "reported_date": (
                    pd.to_datetime(reported).date() if reported else None
                ),
                "reported_eps": _safe_float(q.get("reportedEPS")),
                "estimated_eps": _safe_float(q.get("estimatedEPS")),
                "surprise": _safe_float(q.get("surprise")),
                "surprise_pct": _safe_float(q.get("surprisePercentage")),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        log.info("    %s: %d quarterly entries", ticker, len(df))
    return df


def _earnings_calendar_tickers(lookahead_days: int) -> list[str]:
    """Resolve tickers reporting earnings in the next N days from Cloud SQL."""
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []

    sql = """
        SELECT DISTINCT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN CURRENT_DATE
            AND CURRENT_DATE + (:days || ' days')::interval
        ORDER BY ticker
    """
    try:
        df = query_to_dataframe(sql, {"days": lookahead_days})
    except Exception as e:
        log.warning("earnings_calendar lookup failed: %s", e)
        return []
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def main():
    parser = argparse.ArgumentParser(description="Fetch AV EARNINGS history → Cloud SQL")
    parser.add_argument(
        "--tickers", default=None,
        help="Comma-separated tickers (overrides earnings_calendar resolution).",
    )
    parser.add_argument(
        "--lookahead-days", type=int,
        default=int(os.environ.get("EARNINGS_HISTORY_LOOKAHEAD_DAYS", "90")),
        help="When --tickers is unset, pull history for any ticker reporting "
             "earnings in the next N days (default: 90).",
    )
    parser.add_argument(
        "--max-tickers", type=int,
        default=int(os.environ.get("MAX_TICKERS", "500")),
        help="Safety cap on total ticker count (default: 500).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print without writing to DB.")
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch earnings history")
        sys.exit(1)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        from gcp.fetchers._watchlist import load_watchlist

        ec = _earnings_calendar_tickers(args.lookahead_days)
        wl = load_watchlist()
        seen: set[str] = set(ec)
        tickers = list(ec) + [t for t in wl if t not in seen]
        log.info("Resolved %d tickers (%d earnings %dd ∪ %d watchlist)",
                 len(tickers), len(ec), args.lookahead_days, len(wl))

    if not tickers:
        log.info("No tickers to process — exiting")
        return

    if len(tickers) > args.max_tickers:
        log.warning("Ticker count %d exceeds max-tickers cap %d; truncating",
                    len(tickers), args.max_tickers)
        tickers = tickers[:args.max_tickers]

    log.info("Earnings History Fetch Job (AlphaVantage EARNINGS)")
    log.info("  Tickers : %d", len(tickers))
    log.info("  SQL     : %s", "yes" if is_cloud_sql_configured() else "NO")

    frames = []
    errors = []
    for i, ticker in enumerate(tickers):
        if i > 0:
            time_module.sleep(_av_cfg.delay_between_calls)
        try:
            df = fetch_history_for_ticker(ticker, api_key)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            log.error("  ✗ %s: %s", ticker, e)
            errors.append(ticker)

    if not frames:
        log.warning("No earnings history fetched")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["ticker", "fiscal_date_ending"], keep="last"
    )
    log.info("Total rows: %d across %d tickers", len(combined), combined["ticker"].nunique())

    if args.dry_run:
        with pd.option_context("display.max_rows", 20, "display.max_colwidth", 30):
            print(combined.head(20).to_string(index=False))
        print(f"\n[dry-run] {len(combined)} rows — not written to DB")
        return

    if is_cloud_sql_configured():
        n = upsert_dataframe(
            combined, "earnings_history",
            ["ticker", "fiscal_date_ending"],
        )
        log.info("✓ upserted %d rows to earnings_history", n)
        print(f"Persisted {n} earnings_history rows to Cloud SQL")
    else:
        log.warning("Cloud SQL not configured — skipping persist")

    if errors:
        log.warning("Failed (%d): %s", len(errors), errors[:20])


if __name__ == "__main__":
    main()
