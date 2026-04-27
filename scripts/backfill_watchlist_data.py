#!/usr/bin/env python3
"""Backfill all required data for every watchlist ticker — idempotent.

Run after editing `alert_config.json` → `"watchlist"` (or after the
ranker auto-tunes the watchlist). For each ticker the script checks
what's already in Cloud SQL and only re-fetches what's missing or
stale, so re-running it is a quick no-op once everything's caught up.

Coverage per ticker:

  market_data_daily   — full-history backfill via AV
                        TIME_SERIES_DAILY_ADJUSTED `outputsize=full`
                        if fewer than 200 rows exist.
  market_data_intraday — last 5 trading days of 1-min bars (for
                        analog matching + backtest signals).
  etf_options_snapshots — last trading day's chain for the ticker
                        if no rows in the last 7 days.
  news_sentiment      — last 7 days of articles tagged with the
                        ticker (no-op if the most recent article is
                        within 24h).
  earnings_history    — full lifetime via AV EARNINGS endpoint
                        (no-op if any rows exist).
  insider_transactions — full lifetime via AV INSIDER_TRANSACTIONS
                        (no-op if any rows exist).
  sec_filings         — last 30 days, 10-K/10-Q/8-K (no-op if any
                        8-K rows exist in last 14 days).

Usage:
    python -m scripts.backfill_watchlist_data
    python -m scripts.backfill_watchlist_data --tickers AVGO,NVDA
    python -m scripts.backfill_watchlist_data --force        # re-pull
                                                              # everything
    python -m scripts.backfill_watchlist_data --dry-run      # report
                                                              # only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill_watchlist")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _watchlist() -> list[str]:
    """Source of truth: Cloud SQL `watchlists` → alert_config.json → env.

    Delegates to gcp.fetchers._watchlist.load_watchlist so this script
    sees the same active tickers the live fetchers do (no drift between
    the platform UI's adds and the backfill driver's universe)."""
    try:
        from gcp.fetchers._watchlist import load_watchlist
        return load_watchlist()
    except Exception as exc:
        log.error("watchlist load failed: %s", exc)
        return []


# Default cap on the per-invocation ticker count. The backfill drivers
# shell out to multiple AV endpoints per ticker (daily / intraday /
# options / news / earnings / insider / SEC) and a 100-ticker run can
# exhaust AV's free-tier rate limit and burn ~30 minutes.
DEFAULT_MAX_TICKERS = 25


def _scalar(sql: str, params: dict) -> int | None:
    """Run a SELECT that returns one numeric scalar."""
    try:
        from gcp.database import query_to_dataframe
    except Exception as exc:
        log.warning("gcp.database import failed: %s", exc)
        return None
    df = query_to_dataframe(sql, params)
    if df is None or df.empty:
        return 0
    val = df.iloc[0, 0]
    try:
        return int(val) if val is not None else 0
    except Exception:
        return 0


def _has_recent(sql: str, params: dict) -> bool:
    """Run a SELECT 1 EXISTS-ish check (returns True if any rows)."""
    n = _scalar(sql, params)
    return bool(n and n > 0)


# ── Per-source freshness checks ───────────────────────────────────────────────


def needs_daily_backfill(ticker: str) -> bool:
    n = _scalar(
        "SELECT COUNT(*) FROM market_data_daily WHERE ticker = :t",
        {"t": ticker},
    )
    return (n or 0) < 200


def needs_intraday_backfill(ticker: str) -> bool:
    return not _has_recent(
        "SELECT 1 FROM market_data_intraday WHERE ticker = :t "
        "AND ts >= NOW() - INTERVAL '7 days' LIMIT 1",
        {"t": ticker},
    )


def needs_options_backfill(ticker: str) -> bool:
    return not _has_recent(
        "SELECT 1 FROM etf_options_snapshots WHERE ticker = :t "
        "AND snapshot_ts >= NOW() - INTERVAL '7 days' LIMIT 1",
        {"t": ticker},
    )


def needs_news_backfill(ticker: str) -> bool:
    return not _has_recent(
        "SELECT 1 FROM news_sentiment WHERE ticker = :t "
        "AND published_ts >= NOW() - INTERVAL '24 hours' LIMIT 1",
        {"t": ticker},
    )


def needs_earnings_history(ticker: str) -> bool:
    return not _has_recent(
        "SELECT 1 FROM earnings_history WHERE ticker = :t LIMIT 1",
        {"t": ticker},
    )


def needs_insider(ticker: str) -> bool:
    return not _has_recent(
        "SELECT 1 FROM insider_transactions WHERE ticker = :t LIMIT 1",
        {"t": ticker},
    )


def needs_sec_filings(ticker: str) -> bool:
    return not _has_recent(
        "SELECT 1 FROM sec_filings WHERE ticker = :t "
        "AND form = '8-K' AND filing_date >= CURRENT_DATE - 14 LIMIT 1",
        {"t": ticker},
    )


# ── Per-source backfill drivers ───────────────────────────────────────────────
#
# Each driver shells out to the canonical fetcher CLI so the AV rate
# limit / retry / cloud SQL upsert logic stays in one place. We do NOT
# import the fetchers and call functions inline — that would require
# duplicating their argparse setup here.


def _run(cmd: list[str]) -> bool:
    log.info("    $ %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, cwd=str(REPO))
        return True
    except subprocess.CalledProcessError as exc:
        log.warning("    fetcher exited %s: %s", exc.returncode, exc)
        return False


def backfill_daily(ticker: str) -> bool:
    """Pull the full daily history (~5y) via AV outputsize=full and
    upsert into market_data_daily, then compute indicators for the
    most recent date."""
    log.info("  → daily history backfill (outputsize=full)")
    try:
        import requests
        import pandas as pd
        from gcp.database import upsert_dataframe
        from gcp.fetchers.fetch_market_data import compute_and_upsert_daily_indicators
    except Exception as exc:
        log.warning("    skipped (import failed): %s", exc)
        return False

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        log.warning("    skipped (no AV_API_KEY in env)")
        return False

    try:
        resp = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": "full",
                "datatype": "json",
                "apikey": api_key,
            },
            timeout=60,
        )
        ts = resp.json().get("Time Series (Daily)") or {}
    except Exception as exc:
        log.warning("    AV error: %s", exc)
        return False

    if not ts:
        log.warning("    AV returned no daily series for %s", ticker)
        return False

    rows = []
    for d, v in ts.items():
        rows.append({
            "ticker": ticker,
            "date": pd.to_datetime(d).date(),
            "open": float(v["1. open"]),
            "high": float(v["2. high"]),
            "low": float(v["3. low"]),
            "close": float(v["4. close"]),
            "adjusted_close": float(v["5. adjusted close"]),
            "volume": int(v["6. volume"]),
            "data_source": "alphavantage_daily",
        })
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    upsert_dataframe(df, "market_data_daily", conflict_cols=["ticker", "date"])
    log.info("    ✓ upserted %d daily bars", len(df))

    last_date = str(df["date"].iloc[-1])
    compute_and_upsert_daily_indicators(ticker, last_date)
    return True


def backfill_intraday(ticker: str) -> bool:
    """Last 5 trading days of 1-min bars."""
    log.info("  → intraday last 5 trading days")
    today = date.today()
    fetched = 0
    # walk back up to 9 calendar days to find 5 weekdays
    cur = today
    while fetched < 5 and (today - cur).days <= 9:
        if cur.weekday() < 5:
            ok = _run([
                sys.executable, "-m", "gcp.fetchers.fetch_market_data",
                "--tickers", ticker,
                "--date", str(cur),
                "--earnings-window-days", "0",
            ])
            if ok:
                fetched += 1
        cur -= timedelta(days=1)
    return fetched > 0


def backfill_options(ticker: str) -> bool:
    """Last trading day's options chain via AV historical options."""
    log.info("  → options chain (last trading day)")
    today = date.today()
    cur = today
    while cur.weekday() >= 5:  # rewind to most recent weekday
        cur -= timedelta(days=1)
    return _run([
        sys.executable, "-m", "gcp.fetchers.fetch_av_historical_options",
        "--tickers", ticker, "--date", str(cur),
    ])


def backfill_news(ticker: str) -> bool:
    log.info("  → news (last 7 days)")
    return _run([
        sys.executable, "-m", "gcp.fetchers.fetch_news_sentiment",
        "--tickers", ticker, "--limit", "100",
    ])


def backfill_earnings_history(ticker: str) -> bool:
    log.info("  → earnings history")
    return _run([
        sys.executable, "-m", "gcp.fetchers.fetch_earnings_history",
        "--tickers", ticker,
    ])


def backfill_insider(ticker: str) -> bool:
    log.info("  → insider transactions")
    return _run([
        sys.executable, "-m", "gcp.fetchers.fetch_insider_transactions",
        "--tickers", ticker,
    ])


def backfill_sec(ticker: str) -> bool:
    log.info("  → SEC filings (last 30d, 10-K/10-Q/8-K)")
    return _run([
        sys.executable, "-m", "gcp.fetchers.fetch_sec_filings",
        "--tickers", ticker, "--since-days", "30",
    ])


# ── Driver ────────────────────────────────────────────────────────────────────


SOURCES: list[tuple[str, Callable[[str], bool], Callable[[str], bool]]] = [
    ("daily",            needs_daily_backfill,    backfill_daily),
    ("intraday",         needs_intraday_backfill, backfill_intraday),
    ("options",          needs_options_backfill,  backfill_options),
    ("news",             needs_news_backfill,     backfill_news),
    ("earnings_history", needs_earnings_history,  backfill_earnings_history),
    ("insider",          needs_insider,           backfill_insider),
    ("sec_filings",      needs_sec_filings,       backfill_sec),
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--tickers", default=None,
                   help="Override watchlist. Comma-separated.")
    p.add_argument("--force", action="store_true",
                   help="Re-pull every source regardless of freshness.")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would be backfilled without fetching.")
    p.add_argument(
        "--max-tickers", type=int, default=DEFAULT_MAX_TICKERS,
        help=(f"Cap on ticker count per invocation (default {DEFAULT_MAX_TICKERS}). "
              "Each ticker triggers ~7 AV calls, so a runaway list can exhaust "
              "the free-tier quota in minutes. Use --override-max to bypass."),
    )
    p.add_argument(
        "--override-max", action="store_true",
        help="Bypass --max-tickers cap. Required when running > max-tickers.",
    )
    args = p.parse_args()

    tickers = (
        [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        if args.tickers else _watchlist()
    )
    if not tickers:
        log.error("no tickers — set --tickers or populate the watchlist")
        return 2

    if len(tickers) > args.max_tickers and not args.override_max:
        log.error(
            "refusing to backfill %d tickers (max-tickers=%d). "
            "Use --override-max=1 to bypass. tickers=%s",
            len(tickers), args.max_tickers, tickers,
        )
        return 1

    log.info("Watchlist backfill — %d ticker(s): %s",
             len(tickers), ", ".join(tickers))
    if args.dry_run:
        log.info("DRY RUN — no fetches will run")

    summary: dict[str, dict[str, str]] = {}
    for tk in tickers:
        log.info("─── %s ───", tk)
        summary[tk] = {}
        for name, needs_fn, backfill_fn in SOURCES:
            try:
                stale = args.force or needs_fn(tk)
            except Exception as exc:
                log.warning("  %-18s freshness check failed: %s", name, exc)
                summary[tk][name] = "error"
                continue
            if not stale:
                log.info("  %-18s already current — skipping", name)
                summary[tk][name] = "skip"
                continue
            log.info("  %-18s STALE — backfilling", name)
            if args.dry_run:
                summary[tk][name] = "would-run"
                continue
            ok = False
            try:
                ok = backfill_fn(tk)
            except Exception as exc:
                log.warning("    %s backfill error: %s", name, exc)
            summary[tk][name] = "ok" if ok else "fail"

    # ── Final report ─────────────────────────────────────────────────────────
    log.info("")
    log.info("════════════════════════════════════════════════════════════════")
    log.info("Backfill summary")
    log.info("════════════════════════════════════════════════════════════════")
    headers = ["ticker"] + [s[0] for s in SOURCES]
    log.info("  ".join(f"{h:<16}" for h in headers))
    for tk in tickers:
        row = [tk] + [summary[tk].get(s[0], "?") for s in SOURCES]
        log.info("  ".join(f"{c:<16}" for c in row))

    return 0


if __name__ == "__main__":
    sys.exit(main())
