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
        f = float(val)
    except (TypeError, ValueError):
        return None
    # AV returns "NaN" or float('nan') for upcoming-but-not-reported quarters.
    # Storing NaN in NUMERIC columns leaks placeholder rows past the
    # `reported_eps IS NOT NULL` filter (NaN is a value, not NULL).
    if f != f:
        return None
    return f


def _safe_str(val) -> str | None:
    """Normalize AV string fields. Returns None for missing / 'None' / empty."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "nan"):
        return None
    return s


def _yahoo_timing_from_event_dt(event_dt) -> str | None:
    """Derive 'pre-market' | 'post-market' from a Yahoo earnings event datetime.

    Yahoo's get_earnings_dates() returns timestamps in US/Eastern. An
    event at 16:00 ET or later is post-market (AMC); an event at
    09:30 ET or earlier is pre-market (BMO). Anything in between is
    intraday — rare for earnings, treat as None so AV reportTime
    fallback wins.

    Robust to tz-aware and tz-naive timestamps.
    """
    if event_dt is None or pd.isna(event_dt):
        return None
    try:
        ts = pd.Timestamp(event_dt)
    except (TypeError, ValueError):
        return None
    # Convert to US/Eastern if tz-aware; assume already-ET if naive
    if ts.tzinfo is not None:
        try:
            ts = ts.tz_convert('US/Eastern')
        except Exception:
            ts = ts.tz_convert('UTC').tz_convert('US/Eastern')
    # Compare wall-clock time
    hr, mn = ts.hour, ts.minute
    minutes = hr * 60 + mn
    if minutes >= 16 * 60:           # 16:00 ET or later -> AMC
        return 'post-market'
    if minutes <= 9 * 60 + 30:       # 09:30 ET or earlier -> BMO
        return 'pre-market'
    return None  # intraday — let AV fallback decide


def fetch_yahoo_timing_for_ticker(ticker: str, limit: int = 40) -> dict:
    """Pull the last `limit` earnings dates for `ticker` from Yahoo
    (yfinance) and return a {reported_date: 'pre-market'|'post-market'}
    map. yfinance.Ticker.get_earnings_dates() returns historical
    timestamps in US/Eastern with the reaction-day datetime.

    Returns empty dict on any failure (yfinance is often noisy at the
    long tail). Caller should treat absence as 'no Yahoo data — fall
    back to AV reportTime'.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.info("yfinance not installed — skipping Yahoo timing validation")
        return {}
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=limit)
    except Exception as e:
        log.debug("    Yahoo earnings_dates for %s: %s", ticker, e)
        return {}
    if df is None or df.empty:
        return {}
    out: dict = {}
    for ts, _row in df.iterrows():
        timing = _yahoo_timing_from_event_dt(ts)
        if timing is None:
            continue
        # Normalize to a date for joining against earnings_history.reported_date
        try:
            d = pd.Timestamp(ts)
            if d.tzinfo is not None:
                d = d.tz_convert('US/Eastern')
            out[d.date()] = timing
        except Exception:
            continue
    return out


def fetch_history_for_ticker(
    ticker: str,
    api_key: str,
    enrich_with_yahoo: bool = True,
) -> pd.DataFrame:
    """Pull AV EARNINGS for one ticker; optionally enrich with Yahoo timing.

    AV's `reportTime` is the primary timing source per quarter, but it
    has occasional errors (e.g. NVDA 2026-02-25 was reported by AV as
    pre-market when it actually released after-hours). Yahoo's
    earnings-dates timestamps are derived from the wire feed and are
    reliable. When `enrich_with_yahoo=True`, we also pull yfinance's
    earnings_dates for the same ticker and store the per-quarter Yahoo
    timing in `yahoo_report_time` so the consumer can prefer it.
    """
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

    yahoo_timing_map = (
        fetch_yahoo_timing_for_ticker(ticker.upper())
        if enrich_with_yahoo else {}
    )

    rows = []
    yahoo_hits = 0
    yahoo_disagreements = 0
    for q in quarterly:
        fiscal = q.get("fiscalDateEnding")
        reported = q.get("reportedDate")
        if not fiscal:
            continue
        reported_date = (
            pd.to_datetime(reported).date() if reported else None
        )
        av_report_time = _safe_str(q.get("reportTime"))
        yahoo_report_time = (
            yahoo_timing_map.get(reported_date) if reported_date else None
        )
        if yahoo_report_time:
            yahoo_hits += 1
            if av_report_time and av_report_time.lower() != yahoo_report_time.lower():
                yahoo_disagreements += 1
                log.info(
                    "    %s %s: AV reportTime=%s but Yahoo says %s — Yahoo wins",
                    ticker, reported_date, av_report_time, yahoo_report_time,
                )
        rows.append(
            {
                "ticker": ticker.upper(),
                "fiscal_date_ending": pd.to_datetime(fiscal).date(),
                "reported_date": reported_date,
                "reported_eps": _safe_float(q.get("reportedEPS")),
                "estimated_eps": _safe_float(q.get("estimatedEPS")),
                "surprise": _safe_float(q.get("surprise")),
                "surprise_pct": _safe_float(q.get("surprisePercentage")),
                "report_time": av_report_time,
                "yahoo_report_time": yahoo_report_time,
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        log.info(
            "    %s: %d quarterly entries  (Yahoo timing: %d/%d, %d disagreements)",
            ticker, len(df), yahoo_hits, len(df), yahoo_disagreements,
        )
    return df


def _earnings_calendar_tickers(
    lookahead_days: int,
    require_options: bool = True,
) -> list[str]:
    """Resolve tickers reporting earnings in the next N days from Cloud SQL.

    With ``require_options=True`` (default), only returns tickers we
    have evidence have a tradeable options market:
      (a) ``options_volume > 0`` set by the AV HISTORICAL_OPTIONS
          enrichment in fetch_earnings_calendar.py (~3,000 tickers
          enriched per daily run, covering the full optionable
          universe), OR
      (b) the legacy ``has_options=true`` flag (set by EW or UW
          when they pick a strategy — covers ~500 tickers).

    (a) is the primary filter post-AV-enrichment (broad coverage of
    the actual optionable universe); (b) is a fallback for any ticker
    AV hasn't been called on yet. Combined, this collapses a typical
    7d window from ~3,500 reporters to ~3,000 tradeable names — vs
    the prior ~500 from the EW/UW-only flag.
    """
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []

    sql = """
        SELECT ticker
        FROM earnings_calendar
        WHERE earnings_date BETWEEN CURRENT_DATE
            AND CURRENT_DATE + (:days || ' days')::interval
        GROUP BY ticker
    """
    if require_options:
        sql += (
            '        HAVING BOOL_OR(COALESCE(options_volume, 0) > 0) = true\n'
            '            OR BOOL_OR(COALESCE(has_options, false)) = true\n'
        )
    sql += "        ORDER BY ticker\n"
    try:
        df = query_to_dataframe(sql, {"days": lookahead_days})
    except Exception as e:
        log.warning("earnings_calendar lookup failed: %s", e)
        return []
    if df is None or df.empty:
        return []
    return [str(t).upper() for t in df["ticker"].tolist()]


def _earnings_history_tickers() -> list[str]:
    """Self-heal source: every ticker we've ever pulled history for.

    earnings_calendar is now clamped to today-1..today+7 (PR #174 OOM
    fix) which means a ticker like MSFT can drift out of the
    ``_earnings_calendar_tickers`` view if it isn't in that 8-day
    window when this job runs (e.g. weekly Sunday cadence + ticker
    reports next Wednesday). Adding the historical-ticker source keeps
    every ticker we've ever touched on the refresh list so it stays
    current as new quarters drop.
    """
    try:
        from gcp.database import query_to_dataframe
    except ImportError:
        return []

    try:
        df = query_to_dataframe("SELECT DISTINCT ticker FROM earnings_history")
    except Exception as e:
        log.warning("earnings_history ticker lookup failed: %s", e)
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
        default=int(os.environ.get("EARNINGS_HISTORY_LOOKAHEAD_DAYS", "14")),
        help="When --tickers is unset, pull history for any ticker reporting "
             "earnings in the next N days (default: 14). Was 90 — tightened "
             "because pulling history for tickers reporting 60+ days out "
             "wastes the AV budget (the weekly Sunday cron will catch them "
             "naturally as their reports approach).",
    )
    parser.add_argument(
        "--max-tickers", type=int,
        default=int(os.environ.get("MAX_TICKERS", "1500")),
        help="Safety cap on total ticker count (default: 1500). Bumped "
             "from 500 because the new 14d + has_options filter typically "
             "returns ~200-400 names, well under the cap, which is now a "
             "true safety belt rather than a silent truncator.",
    )
    parser.add_argument(
        "--require-options", action="store_true",
        default=os.environ.get("REQUIRE_OPTIONS", "true").lower() != "false",
        help="Filter earnings_calendar tickers to those with "
             "has_options=true (EW or UW confirmed). Default: true. "
             "Set REQUIRE_OPTIONS=false to disable for non-options use.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and print without writing to DB.")
    parser.add_argument(
        "--no-backfill", action="store_true",
        help="Skip the post-fetch market-data backfill chain. "
             "Default: after a successful earnings_history fetch we kick "
             "off fetch_market_data._run_backfill() so any new ticker that "
             "just landed in earnings_history gets OHLCV depth before the "
             "11pm compute-earnings-reactions run. Smart-switch makes this "
             "free (zero AV calls) when no new tickers appeared.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("AV_API_KEY") or os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch earnings history")
        sys.exit(1)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        from gcp.fetchers._watchlist import load_watchlist

        ec = _earnings_calendar_tickers(
            args.lookahead_days, require_options=args.require_options,
        )
        wl = load_watchlist()
        eh = _earnings_history_tickers()  # self-heal source — see fn docstring
        seen: set[str] = set()
        tickers: list[str] = []
        for source in (ec, wl, eh):
            for t in source:
                if t not in seen:
                    tickers.append(t)
                    seen.add(t)
        log.info(
            "Resolved %d tickers (%d earnings %dd + %d watchlist + %d historical)",
            len(tickers), len(ec), args.lookahead_days, len(wl), len(eh),
        )

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

    # Scrub NaN -> None so they land as PostgreSQL NULL, not 'NaN'::numeric.
    # _safe_float already returns Python None for NaN inputs, but pd.concat
    # rebuilds float columns and re-introduces np.nan. Without this scrub,
    # upcoming-but-not-yet-reported quarters leak past the
    # `reported_eps IS NOT NULL` filter on the consumer side.
    import numpy as np
    combined = combined.replace({np.nan: None}).where(combined.notna(), None)

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

    # Chain: any new ticker that just landed in earnings_history needs
    # OHLCV depth before tonight's compute-earnings-reactions run, so
    # we hand off to fetch_market_data._run_backfill() in-process.
    # Smart-switch in the backfill (≥1500 bars + ≤1d stale → skip) makes
    # this free on no-op days. Wrapped so a backfill failure does NOT
    # mark the earnings fetch as failed — the persist already succeeded.
    if not args.no_backfill and not args.dry_run and is_cloud_sql_configured():
        log.info("─" * 60)
        log.info("Post-fetch chain: fetch_market_data._run_backfill()")
        try:
            from gcp.fetchers.fetch_market_data import _run_backfill
            _run_backfill()
        except Exception as e:
            log.warning("Post-fetch backfill failed (non-fatal): %s", e)


if __name__ == "__main__":
    main()
