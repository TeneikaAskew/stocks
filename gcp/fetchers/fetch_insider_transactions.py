#!/usr/bin/env python3
"""
Cloud Run Job: Fetch insider transactions from AV INSIDER_TRANSACTIONS → Cloud SQL.

Form 4 filings: every officer/director/10%-owner buy or sell. AV
returns up to 1000 rows per ticker per call going back several years.

Used by the ranker to derive an "insider cluster" signal — 3+ insiders
buying within 30 days, or a single insider transacting >$1M, are
historically strong directional tells on single names.

Ticker source priority:
  1. CLI --tickers override
  2. earnings_calendar within ±N days (default 7) — the catalyst
     window where insider activity matters most.

Usage:
    python -m gcp.fetchers.fetch_insider_transactions
    python -m gcp.fetchers.fetch_insider_transactions --tickers AAPL,AVGO --dry-run
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
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def fetch_for_ticker(ticker: str, api_key: str) -> pd.DataFrame:
    """Pull all insider transactions AV has for one ticker."""
    params = {
        "function": "INSIDER_TRANSACTIONS",
        "symbol": ticker.upper(),
        "apikey": api_key,
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("    AV INSIDER_TRANSACTIONS request failed for %s: %s", ticker, e)
        return pd.DataFrame()

    if "Information" in data:
        log.warning("    AV info for %s: %s", ticker, data["Information"])
        return pd.DataFrame()

    txns = data.get("data") or []
    if not txns:
        log.info("    No insider transactions for %s", ticker)
        return pd.DataFrame()

    rows = []
    today = pd.Timestamp.utcnow().date()
    skipped_future = 0
    for t in txns:
        td = t.get("transaction_date")
        if not td:
            continue
        try:
            txn_date = pd.to_datetime(td).date()
        except Exception:
            continue
        # AV occasionally returns garbage future dates (e.g. 2031-01-29).
        # Insider transactions are by definition reported after they happen,
        # so anything more than a week in the future is almost certainly a
        # source data error.
        if (txn_date - today).days > 7:
            skipped_future += 1
            continue
        shares = _safe_float(t.get("shares"))
        price = _safe_float(t.get("share_price"))
        value = (shares * price) if (shares is not None and price is not None) else None
        rows.append(
            {
                "ticker": ticker.upper(),
                "transaction_date": txn_date,
                "executive": (t.get("executive") or "")[:200] or None,
                "title": (t.get("executive_title") or "")[:200] or None,
                "transaction_type": (t.get("acquisition_or_disposal") or "")[:20] or None,
                "shares": shares,
                "share_price": price,
                "transaction_value": value,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        log.info("    %s: %d transactions", ticker, len(df))
    if skipped_future:
        log.warning("    %s: skipped %d rows with implausible future dates",
                    ticker, skipped_future)
    return df


def _earnings_calendar_tickers(window_days: int) -> list[str]:
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []
    sql = """
        SELECT DISTINCT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN
            CURRENT_DATE - (:w || ' days')::interval AND
            CURRENT_DATE + (:w || ' days')::interval
        ORDER BY ticker
    """
    try:
        df = query_to_dataframe(sql, {"w": window_days})
    except Exception as e:
        log.warning("earnings_calendar lookup failed: %s", e)
        return []
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def main():
    parser = argparse.ArgumentParser(
        description="Fetch insider transactions from AV → Cloud SQL"
    )
    parser.add_argument(
        "--tickers", default=None,
        help="Comma-separated tickers (overrides earnings_calendar resolution).",
    )
    parser.add_argument(
        "--earnings-window-days", type=int,
        default=int(os.environ.get("EARNINGS_WINDOW_DAYS", "7")),
    )
    parser.add_argument(
        "--max-tickers", type=int,
        default=int(os.environ.get("MAX_TICKERS", "300")),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch insider transactions")
        sys.exit(1)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        from gcp.fetchers._watchlist import load_watchlist

        ec = _earnings_calendar_tickers(args.earnings_window_days)
        wl = load_watchlist()
        # Union (preserve order: earnings-window first, then watchlist extras).
        seen: set[str] = set(ec)
        tickers = list(ec) + [t for t in wl if t not in seen]
        log.info("Resolved %d tickers (%d earnings ±%dd ∪ %d watchlist)",
                 len(tickers), len(ec), args.earnings_window_days, len(wl))

    if not tickers:
        log.info("No tickers to process — exiting")
        return

    if len(tickers) > args.max_tickers:
        log.warning("Ticker count %d exceeds cap %d; truncating",
                    len(tickers), args.max_tickers)
        tickers = tickers[:args.max_tickers]

    log.info("Insider Transactions Fetch Job")
    log.info("  Tickers : %d", len(tickers))
    log.info("  SQL     : %s", "yes" if is_cloud_sql_configured() else "NO")

    frames = []
    errors = []
    for i, tk in enumerate(tickers):
        if i > 0:
            time_module.sleep(_av_cfg.delay_between_calls)
        try:
            df = fetch_for_ticker(tk, api_key)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            log.error("  ✗ %s: %s", tk, e)
            errors.append(tk)

    if not frames:
        log.warning("No insider data fetched")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(
        subset=["ticker", "transaction_date", "executive",
                "transaction_type", "shares", "share_price"],
        keep="last",
    )
    log.info("Total rows: %d across %d tickers",
             len(combined), combined["ticker"].nunique())

    if args.dry_run:
        with pd.option_context("display.max_rows", 30, "display.max_colwidth", 30):
            print(combined.head(30).to_string(index=False))
        print(f"\n[dry-run] {len(combined)} rows — not written to DB")
        return

    if is_cloud_sql_configured():
        n = upsert_dataframe(
            combined, "insider_transactions",
            ["ticker", "transaction_date", "executive",
             "transaction_type", "shares", "share_price"],
        )
        log.info("✓ upserted %d rows to insider_transactions", n)
        print(f"Persisted {n} insider_transactions rows to Cloud SQL")
    else:
        log.warning("Cloud SQL not configured — skipping persist")

    if errors:
        log.warning("Failed (%d): %s", len(errors), errors[:20])


if __name__ == "__main__":
    main()
