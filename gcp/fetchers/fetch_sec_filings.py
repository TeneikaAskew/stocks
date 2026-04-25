#!/usr/bin/env python3
"""
Cloud Run Job: Poll SEC EDGAR for recent filings (8-K, 10-Q, 10-K) → Cloud SQL.

8-K filings are the "something material happened" form: M&A (item 1.01),
bankruptcy (1.03), exec changes (5.02), Reg-FD disclosures (7.01), etc.
This fetcher captures them in real time as a free catalyst stream for
the ranker — covering any ticker SEC tracks, no AV quota cost.

EDGAR endpoints used:
  * https://www.sec.gov/files/company_tickers.json
        — public ticker ↔ CIK map. ~10k entries, refreshed weekly.
  * https://data.sec.gov/submissions/CIK{cik:010d}.json
        — last 1000 filings per company, JSON arrays.

Rate limit: SEC publishes 10 req/sec/IP. The 0.15s delay between calls
keeps us at ~7 RPS — safely under the cap.

A descriptive User-Agent header is required by SEC. Set via env var
SEC_USER_AGENT (defaults to a generic identifier — override in deploy).

Usage:
    python -m gcp.fetchers.fetch_sec_filings
    python -m gcp.fetchers.fetch_sec_filings --tickers AAPL,MSFT,AVGO --forms 8-K,10-Q
"""

import argparse
import logging
import os
import sys
import time as time_module
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

EDGAR_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_FORMS = ("8-K", "10-Q", "10-K")
SEC_RATE_DELAY_S = 0.15  # ~7 RPS, well under the 10 RPS limit
DEFAULT_USER_AGENT = "Trading System Research research@example.com"


def _http_get(url: str, user_agent: str, timeout: int = 30) -> dict | None:
    """GET an EDGAR JSON endpoint with the required User-Agent header."""
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("SEC GET failed for %s: %s", url, e)
        return None


def load_ticker_to_cik(user_agent: str) -> dict[str, str]:
    """Pull SEC's public ticker → CIK map.

    Response shape: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ... }
    Returns: {"AAPL": "0000320193", ...} — CIKs zero-padded to 10 digits.
    """
    data = _http_get(TICKERS_URL, user_agent)
    if not data:
        return {}
    mapping: dict[str, str] = {}
    for entry in data.values():
        tk = (entry.get("ticker") or "").upper().strip()
        cik = entry.get("cik_str")
        if tk and cik is not None:
            mapping[tk] = f"{int(cik):010d}"
    log.info("Loaded SEC ticker→CIK map: %d tickers", len(mapping))
    return mapping


def fetch_submissions(ticker: str, cik: str, user_agent: str) -> list[dict]:
    """Return parsed `recent` submissions for one CIK.

    The `filings.recent` block is a parallel-arrays structure:
        accessionNumber: ['0001234567-25-...', ...]
        filingDate     : ['2026-04-24', ...]
        form           : ['8-K', '10-Q', ...]
        items          : ['1.01,7.01', '', ...]
        primaryDocument: ['avgo-20260424.htm', ...]

    We zip the arrays together into one dict per filing.
    """
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    data = _http_get(url, user_agent)
    if not data:
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    if not recent:
        return []

    n = len(recent.get("accessionNumber") or [])
    rows = []
    for i in range(n):
        rows.append(
            {
                "ticker": ticker.upper(),
                "cik": cik,
                "accession_number": (recent.get("accessionNumber") or [None])[i],
                "form": (recent.get("form") or [None])[i],
                "filing_date": (recent.get("filingDate") or [None])[i],
                "report_date": (recent.get("reportDate") or [None])[i] or None,
                "items_raw": (recent.get("items") or [""])[i] or "",
                "primary_doc": (recent.get("primaryDocument") or [None])[i],
            }
        )
    return rows


def filter_and_normalize(
    rows: list[dict], forms: set[str], since: date,
) -> pd.DataFrame:
    """Keep only target forms within the date window, normalize types."""
    keep = []
    for r in rows:
        form = r.get("form") or ""
        if form not in forms:
            continue
        fd = r.get("filing_date")
        if not fd:
            continue
        try:
            filing_d = pd.to_datetime(fd).date()
        except Exception:
            continue
        if filing_d < since:
            continue

        # Items is a comma-separated string in the response, e.g. "1.01,7.01".
        items_raw = r.get("items_raw", "") or ""
        items = [s.strip() for s in items_raw.split(",") if s.strip()]

        rd = r.get("report_date")
        try:
            report_d = pd.to_datetime(rd).date() if rd else None
        except Exception:
            report_d = None

        keep.append(
            {
                "ticker": r["ticker"],
                "cik": r["cik"],
                "accession_number": r["accession_number"],
                "form": form,
                "filing_date": filing_d,
                "report_date": report_d,
                "items": items or None,
                "primary_doc": (r.get("primary_doc") or "")[:200] or None,
            }
        )
    return pd.DataFrame(keep)


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
    parser = argparse.ArgumentParser(description="Fetch SEC EDGAR filings → Cloud SQL")
    parser.add_argument(
        "--tickers", default=None,
        help="Comma-separated tickers (overrides earnings_calendar resolution).",
    )
    parser.add_argument(
        "--forms", default=",".join(DEFAULT_FORMS),
        help=f"Comma-separated forms to keep (default: {','.join(DEFAULT_FORMS)}).",
    )
    parser.add_argument(
        "--since-days", type=int,
        default=int(os.environ.get("SEC_SINCE_DAYS", "14")),
        help="Only keep filings from the last N days (default: 14).",
    )
    parser.add_argument(
        "--earnings-window-days", type=int,
        default=int(os.environ.get("EARNINGS_WINDOW_DAYS", "7")),
        help="When --tickers is unset, pull filings for tickers reporting "
             "earnings within ±N days (default: 7).",
    )
    parser.add_argument(
        "--max-tickers", type=int,
        default=int(os.environ.get("MAX_TICKERS", "500")),
        help="Safety cap on total ticker count (default: 500).",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print without writing to DB.")
    args = parser.parse_args()

    user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    if user_agent == DEFAULT_USER_AGENT:
        log.warning(
            "SEC_USER_AGENT not set — using generic identifier. SEC requests "
            "you identify your organization + contact email."
        )

    forms = {f.strip().upper() for f in args.forms.split(",") if f.strip()}
    since = date.today() - timedelta(days=args.since_days)

    # Resolve ticker universe
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        from gcp.fetchers._watchlist import load_watchlist

        ec = _earnings_calendar_tickers(args.earnings_window_days)
        wl = load_watchlist()
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

    # Build CIK map (one shared call)
    ticker_to_cik = load_ticker_to_cik(user_agent)
    if not ticker_to_cik:
        log.error("Failed to load SEC ticker→CIK map; cannot proceed")
        sys.exit(1)

    log.info("SEC EDGAR Fetch Job")
    log.info("  Tickers   : %d", len(tickers))
    log.info("  Forms     : %s", sorted(forms))
    log.info("  Since     : %s (%d days back)", since, args.since_days)
    log.info("  SQL       : %s", "yes" if is_cloud_sql_configured() else "NO")

    all_filings: list[dict] = []
    skipped_no_cik = 0
    errors: list[str] = []

    for i, tk in enumerate(tickers):
        cik = ticker_to_cik.get(tk)
        if not cik:
            skipped_no_cik += 1
            continue
        if i > 0:
            time_module.sleep(SEC_RATE_DELAY_S)
        try:
            rows = fetch_submissions(tk, cik, user_agent)
            all_filings.extend(rows)
        except Exception as e:
            log.error("  ✗ %s (CIK %s): %s", tk, cik, e)
            errors.append(tk)

    log.info("Pulled %d raw filing rows (%d tickers without CIK)",
             len(all_filings), skipped_no_cik)

    if not all_filings:
        log.info("No filings fetched")
        return

    df = filter_and_normalize(all_filings, forms, since)
    if df.empty:
        log.info("No filings matched form/date filters")
        return

    df = df.drop_duplicates(subset=["cik", "accession_number"], keep="last")
    log.info("After filter+dedup: %d filings", len(df))

    if args.dry_run:
        with pd.option_context("display.max_rows", 30, "display.max_colwidth", 30):
            print(df.head(30).to_string(index=False))
        print(f"\n[dry-run] {len(df)} rows — not written to DB")
        return

    if is_cloud_sql_configured():
        n = upsert_dataframe(df, "sec_filings", ["cik", "accession_number"])
        log.info("✓ upserted %d rows to sec_filings", n)
        print(f"Persisted {n} sec_filings rows to Cloud SQL")
    else:
        log.warning("Cloud SQL not configured — skipping persist")

    if errors:
        log.warning("Failed (%d): %s", len(errors), errors[:20])


if __name__ == "__main__":
    main()
