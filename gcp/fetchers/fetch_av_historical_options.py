#!/usr/bin/env python3
"""
Cloud Run Job: Fetch daily AV HISTORICAL_OPTIONS and write to Cloud SQL.

Replaces the GitHub Actions workflow fetch-alphavantage-options-daily.yml.
Writes data to Cloud SQL with data_source='alphavantage' so consumers can
query it directly. GCS parquet backups were retired in favour of Cloud SQL
PITR (granular recovery within 7 days) + a weekly pg_dump → GCS for long-
term archival of all tables, not just this one.

Scheduled by Cloud Scheduler after market close (e.g., 10 PM ET weekdays).

Usage:
    python -m gcp.fetchers.fetch_av_historical_options [--tickers ALL] [--date YYYY-MM-DD]
"""

import argparse
import logging
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import upsert_dataframe, is_cloud_sql_configured
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'
TICKERS = ['SPY', 'IWM', 'QQQ', 'SPX']
_av_cfg = AlphaVantageConfig()


def fetch_av_options(ticker: str, fetch_date: str, api_key: str) -> pd.DataFrame:
    """
    Fetch end-of-day options chain from AV HISTORICAL_OPTIONS for one ticker/date.

    Returns normalized DataFrame ready for etf_options_snapshots, or empty on error.
    """
    symbol = ticker
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol':   symbol,
        'date':     fetch_date,
        'apikey':   api_key,
        'datatype': 'json',
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if data.get('message') != 'success' or data.get('endpoint') != 'Historical Options':
            log.warning("  AV options: unexpected response for %s %s: %s",
                        ticker, fetch_date, data.get('message', data.get('Information', '')))
            return pd.DataFrame()

        records = data.get('data', [])
        if not records:
            log.info("  AV options: no contracts for %s %s", ticker, fetch_date)
            return pd.DataFrame()

        df = pd.DataFrame(records)
        return _normalize_av_response(df, ticker, fetch_date)

    except Exception as e:
        log.error("  AV options fetch failed for %s %s: %s", ticker, fetch_date, e)
        return pd.DataFrame()


def _normalize_av_response(df: pd.DataFrame, ticker: str, fetch_date: str) -> pd.DataFrame:
    """Normalize raw AV HISTORICAL_OPTIONS JSON response to etf_options_snapshots schema."""
    out = df.copy()

    # Coerce numeric columns
    numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
               'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
    for col in numeric:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')

    # snapshot_ts at 23:00 UTC (EOD marker, distinct from yahooquery intraday)
    out['snapshot_ts'] = pd.Timestamp(f"{fetch_date}T23:00:00Z")
    out['snapshot_date'] = pd.to_datetime(fetch_date).date()
    out['market_session'] = 'EOD'
    out['ticker'] = ticker.upper()
    out['data_source'] = 'alphavantage'

    # option_type normalisation
    if 'type' in out.columns:
        out['option_type'] = out['type'].str.lower().map({'call': 'calls', 'put': 'puts'})
    elif 'option_type' in out.columns:
        out['option_type'] = out['option_type'].str.lower()

    # Column renames from AV JSON keys
    rename = {
        'contractID':   'contract_symbol',
        'expiration':   'expiration',
        'last':         'last_price',
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})

    keep = [
        'ticker', 'snapshot_ts', 'snapshot_date', 'market_session',
        'contract_symbol', 'option_type', 'expiration', 'strike',
        'bid', 'ask', 'mark', 'last_price', 'volume', 'open_interest',
        'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho',
        'data_source',
    ]
    out = out[[c for c in keep if c in out.columns]]
    out = out.dropna(subset=['option_type', 'expiration', 'strike'])
    return out


def process_ticker(ticker: str, fetch_date: str, api_key: str,
                    skip_existing: bool = False):
    """Fetch AV options for one ticker/date → Cloud SQL."""
    if skip_existing and is_cloud_sql_configured():
        from gcp.database import query_to_dataframe
        # market_session = 'EOD' is load-bearing. The av-options-realtime
        # fetcher (Track 0, 2026-05-22) writes data_source='alphavantage'
        # rows every 5 min during RTH. Without this filter the existence
        # check matches a REALTIME row, declares EOD "already ingested",
        # and silently freezes EOD for SPY/IWM/QQQ — exactly what happened
        # 2026-05-22 → 2026-06-11 (SPX, not in the realtime set, kept working).
        hit = query_to_dataframe(
            "SELECT 1 FROM etf_options_snapshots "
            "WHERE ticker = :t AND snapshot_date = :d AND data_source = 'alphavantage' "
            "AND market_session = 'EOD' LIMIT 1",
            {"t": ticker, "d": fetch_date},
        )
        if not hit.empty:
            log.info("  %s %s already ingested — skipping", ticker, fetch_date)
            return

    log.info("  Fetching %s options for %s...", ticker, fetch_date)

    df = fetch_av_options(ticker, fetch_date, api_key)
    if df.empty:
        log.warning("    No options data returned for %s %s", ticker, fetch_date)
        return

    log.info("    %d contracts received", len(df))

    # Dedupe on the unique constraint so ON CONFLICT DO UPDATE never tries to
    # update the same row twice in one batch (AV occasionally returns duplicate
    # contracts within the same response — dates 2017-09-15, 2020-06-22 etc.).
    conflict_cols = ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    before = len(df)
    df = df.drop_duplicates(subset=conflict_cols, keep='last')
    if len(df) < before:
        log.info("    deduped %d → %d rows", before, len(df))

    if is_cloud_sql_configured():
        upsert_dataframe(df, 'etf_options_snapshots', conflict_cols)
        log.info("    ✓ upserted to Cloud SQL")


def _weekday_range(start: date, end: date) -> list[str]:
    """Return YYYY-MM-DD strings for all weekdays in [start, end] inclusive."""
    out = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon-Fri
            out.append(cur.strftime('%Y-%m-%d'))
        cur += timedelta(days=1)
    return out


def _resolve_start_from_latest(tickers: list[str]) -> date:
    """Compute the start date that catches up the WORST-COVERED ticker.

    Strategy: SELECT MAX(snapshot_date) GROUP BY ticker, take MIN across
    those per-ticker watermarks, return MIN + 1 day. Falls back to today
    when no ticker has any rows yet.

    Why MIN-of-per-ticker-MAX instead of a global MAX:
    1. Tail-behind ticker — if QQQ's last fetch failed but SPY/IWM/SPX
       moved on, global MAX picks SPY's tail and the date range starts
       AFTER QQQ's gap. QQQ's missing tail is never re-fetched.
       MIN-of-per-ticker-MAX picks QQQ's older watermark instead,
       sweeping the missing days for QQQ while SPY's already-present
       dates are skipped via per-(ticker, date) skip-existing.
    2. Newly-added ticker with no history — drops out of the GROUP BY
       (no rows means no row in result). It still gets fetched for
       every date in the range that the existing tickers' watermark
       establishes, and per-(ticker, date) skip-existing fall-through
       lets AV calls land for it.

    Does NOT catch mid-range gaps within a single ticker (e.g. QQQ has
    Apr 14, 15, 17, 18, 19 — gap at Apr 16 with later data present).
    Per-ticker MAX is still Apr 19, MIN across tickers might be Apr 19,
    range starts Apr 20 → Apr 16's gap survives. For mid-range gaps,
    invoke explicitly with --start-date pointing at the gap; the
    monthly self-resume cron is for tail-coverage only.
    """
    from gcp.database import query_to_dataframe

    if not tickers:
        return date.today()

    placeholders = ",".join(f":t{i}" for i in range(len(tickers)))
    params = {f"t{i}": t for i, t in enumerate(tickers)}
    # market_session = 'EOD' is load-bearing — see process_ticker(). The MAX
    # watermark must reflect the latest EOD snapshot, NOT the latest REALTIME
    # one. Without this filter SPY/IWM/QQQ watermarks track their daily
    # REALTIME rows, so --from-latest starts at today and never sweeps the
    # missing EOD tail (the 2026-05-22 → 2026-06-11 freeze).
    df = query_to_dataframe(
        f"SELECT ticker, MAX(snapshot_date) AS d FROM etf_options_snapshots "
        f"WHERE ticker IN ({placeholders}) "
        f"AND data_source = 'alphavantage' "
        f"AND market_session = 'EOD' "
        f"GROUP BY ticker",
        params,
    )

    # Tickers with no rows don't appear in the GROUP BY output. They get
    # caught up implicitly: per-(ticker, date) skip-existing in
    # process_ticker returns no hit for them, so AV is called for every
    # date in the established range.
    watermarks = [
        pd.to_datetime(r["d"]).date()
        for _, r in df.iterrows()
        if pd.notna(r["d"])
    ]
    if not watermarks:
        log.warning(
            "  --from-latest: no existing rows for any of %s — defaulting "
            "start to today",
            tickers,
        )
        return date.today()

    oldest = min(watermarks)
    return oldest + timedelta(days=1)


def main():
    import time

    parser = argparse.ArgumentParser(
        description='Fetch daily AV HISTORICAL_OPTIONS to Cloud SQL')
    parser.add_argument('--tickers', default='ALL',
                        help='Space-separated tickers or ALL')
    parser.add_argument('--date', default=None,
                        help='Single date to fetch (YYYY-MM-DD). Defaults to today. '
                             'Ignored if --start-date / --end-date are provided.')
    parser.add_argument('--start-date', default=None,
                        help='Backfill range start (YYYY-MM-DD, inclusive).')
    parser.add_argument('--end-date', default=None,
                        help='Backfill range end (YYYY-MM-DD, inclusive). Defaults to today.')
    parser.add_argument('--from-latest', action='store_true', default=False,
                        help='Set start-date to MAX(snapshot_date in Cloud SQL) + 1 day '
                             'across the requested tickers. end-date defaults to today. '
                             'Used by the monthly scheduler so the job is self-resuming '
                             'and doesn\'t need hardcoded date args. Mutually exclusive '
                             'with --start-date.')
    parser.add_argument('--skip-existing', action='store_true', default=False,
                        help='Skip (ticker, date) pairs already in Cloud SQL. '
                             'Automatically enabled when --start-date is provided.')
    args = parser.parse_args()

    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    tickers = TICKERS if args.tickers == 'ALL' else args.tickers.upper().split()

    # Union watchlist when running in ALL mode so curated single-name tickers
    # (e.g. AVGO) get options chains for the iv_signals ranker input.
    # Done up front so --from-latest's SQL lookup includes them.
    if args.tickers == 'ALL':
        from gcp.fetchers._watchlist import load_watchlist
        wl_added = [t for t in load_watchlist() if t not in tickers]
        if wl_added:
            log.info("  Adding %d watchlist tickers: %s", len(wl_added), wl_added)
            tickers.extend(wl_added)

    # Resolve --from-latest before working out the date range.
    if args.from_latest:
        if args.start_date:
            log.error("--from-latest is mutually exclusive with --start-date")
            sys.exit(2)
        if not is_cloud_sql_configured():
            log.error("--from-latest requires Cloud SQL configured (it queries the "
                      "current MAX(snapshot_date) to compute start)")
            sys.exit(2)
        args.start_date = _resolve_start_from_latest(tickers).isoformat()
        log.info("--from-latest resolved start_date=%s (end=today)", args.start_date)

    # Resolve date list: range mode wins if either bound is given.
    is_range_mode = bool(args.start_date or args.end_date)
    if is_range_mode:
        start = date.fromisoformat(args.start_date) if args.start_date else date.today()
        end = date.fromisoformat(args.end_date) if args.end_date else date.today()
        if start > end:
            log.info("start_date %s > end_date %s — nothing to fetch (already current)",
                     start, end)
            sys.exit(0)
        fetch_dates = _weekday_range(start, end)
        log.info("Backfill range: %s → %s (%d weekdays)", start, end, len(fetch_dates))
    else:
        fetch_dates = [args.date or date.today().strftime('%Y-%m-%d')]

    # Auto-enable --skip-existing in range/backfill mode.
    skip_existing = args.skip_existing or is_range_mode

    log.info("Fetch AV Historical Options Job")
    log.info("  Dates   : %d date(s)", len(fetch_dates))
    log.info("  Tickers : %s", tickers)
    log.info("  SQL     : %s", 'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  AV key  : %s", 'set' if api_key else 'MISSING')

    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch options")
        sys.exit(1)

    errors = []
    total_calls = 0
    for fetch_date in fetch_dates:
        for ticker in tickers:
            if total_calls > 0:
                time.sleep(_av_cfg.delay_between_calls)
            total_calls += 1
            try:
                process_ticker(ticker, fetch_date, api_key,
                               skip_existing=skip_existing)
            except Exception as e:
                log.error("  ✗ %s %s failed: %s", ticker, fetch_date, e)
                errors.append(f"{ticker}/{fetch_date}")

    if errors:
        log.error("Failed (%d): first 20 = %s", len(errors), errors[:20])
        sys.exit(1)
    log.info("Done. %d AV calls across %d dates × %d tickers.",
             total_calls, len(fetch_dates), len(tickers))


if __name__ == '__main__':
    main()
