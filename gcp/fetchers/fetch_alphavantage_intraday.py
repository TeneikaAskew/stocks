#!/usr/bin/env python3
"""
Cloud Run Job: Fetch AlphaVantage 1-min historical intraday → Cloud SQL.

Replaces the GitHub Actions workflow fetch-alphavantage-intraday-monthly.yml.
Scheduled on the 1st of each month by Cloud Scheduler.

Usage:
    python -m gcp.fetchers.fetch_alphavantage_intraday --symbol SPY
    python -m gcp.fetchers.fetch_alphavantage_intraday --symbol ALL --start-date 2026-01-01
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import (
    bulk_insert_dataframe,
    execute_sql,
    is_cloud_sql_configured,
    upsert_dataframe,
)
from lib.config import AlphaVantageConfig

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

SYMBOLS = ['SPY', 'IWM', 'QQQ']
AV_BASE_URL = 'https://www.alphavantage.co/query'
# Per-call interval is read from AlphaVantageConfig so the 150 RPM
# premium-tier setting is the single source of truth across fetchers.
# (Previously hardcoded to 13 s — the 5-RPM free-tier value — which
# made a 50-ticker backfill take 5+ hours instead of ~10 minutes.)
_av_cfg = AlphaVantageConfig()


def get_api_keys() -> list:
    """Collect all available AlphaVantage API keys from environment."""
    keys = []
    primary = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if primary:
        keys.append(primary)
    # Support backup keys: ALPHA_VANTAGE_API_KEY_2, _3, _4, _5
    for i in range(2, 6):
        k = os.environ.get(f'ALPHA_VANTAGE_API_KEY_{i}', '')
        if k:
            keys.append(k)
    return keys


def get_trading_months(start_date: str, end_date: str) -> list:
    """Return list of (year, month) tuples covering the date range."""
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append((current.year, current.month))
        current = (current + pd.offsets.MonthBegin(1))
    return months


# Per-month outcome reasons returned from fetch_month. The string is
# distinct from None so the caller can categorise WHY a fetch returned
# no data — critical for the dead-ticker vs transient-error
# classification in process_symbol's outcome (see _TICKER_OUTCOME_*).
FETCH_OK             = 'success'
FETCH_INVALID_API    = 'invalid_api_call'   # AV "Error Message" — symbol unknown / delisted
FETCH_RATE_LIMIT     = 'rate_limit'         # AV "Note" — burned through RPM
FETCH_INFO_MSG       = 'info_message'       # AV "Information" — generic non-data response
FETCH_NO_TIMESERIES  = 'no_timeseries'      # response shape unexpected
FETCH_REQUEST_ERROR  = 'request_error'      # network / HTTP error

# Reasons that indicate a permanently-broken ticker (not a transient).
# A symbol whose entire month-range returns ONLY these is treated as
# a data-quality failure (dead/delisted ticker), not a systemic failure.
_DEAD_TICKER_REASONS = {FETCH_INVALID_API, FETCH_INFO_MSG, FETCH_NO_TIMESERIES}


def fetch_month(
    symbol: str, year: int, month: int, api_key: str,
) -> Tuple[Optional[pd.DataFrame], str]:
    """Fetch one month of 1-minute data from AlphaVantage.

    Returns ``(df, reason)`` where ``df`` is the data (or None on any
    failure) and ``reason`` is one of the ``FETCH_*`` constants above.
    The reason is what lets process_symbol categorise the outcome:
    "every month said INVALID_API" → dead ticker (data quality),
    "every month said REQUEST_ERROR" → systemic (network outage).
    """
    month_str = f"{year}-{month:02d}"
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': symbol,
        'interval': '1min',
        'month': month_str,
        'outputsize': 'full',
        'entitlement': 'realtime',
        'extended_hours': 'true',
        'datatype': 'json',
        'apikey': api_key,
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if 'Error Message' in data:
            log.warning("    AV error for %s %s: %s", symbol, month_str, data['Error Message'])
            return None, FETCH_INVALID_API
        if 'Note' in data:
            log.warning("    AV rate limit for %s %s", symbol, month_str)
            return None, FETCH_RATE_LIMIT
        if 'Information' in data:
            log.warning("    AV info: %s", data['Information'])
            return None, FETCH_INFO_MSG

        ts_key = 'Time Series (1min)'
        if ts_key not in data:
            log.warning("    No time series data for %s %s", symbol, month_str)
            return None, FETCH_NO_TIMESERIES

        records = []
        for ts, values in data[ts_key].items():
            records.append({
                'ts': pd.Timestamp(ts),
                'open':   float(values['1. open']),
                'high':   float(values['2. high']),
                'low':    float(values['3. low']),
                'close':  float(values['4. close']),
                'volume': int(values['5. volume']),
            })

        df = pd.DataFrame(records)
        df['ticker'] = symbol
        df['interval'] = '1min'
        df['data_source'] = 'alphavantage'
        return df.sort_values('ts').reset_index(drop=True), FETCH_OK

    except Exception as e:
        log.error("    Request error for %s %s: %s", symbol, year, e)
        return None, FETCH_REQUEST_ERROR


# Per-ticker outcome categories returned by process_symbol. Used by the
# outer loop to decide whether to exit(1). Only OUTCOME_SYSTEMIC trips
# the failure exit — dead-ticker outcomes are logged at WARNING level
# but don't fail the task (3.7 §5: typed UNAVAILABLE envelope, not
# silent fallback). Per CLAUDE.md Rule 0.4 (bounded retries, idempotent
# re-runs), a single delisted ticker in a 339-ticker watchlist must
# not crash the entire task and auto-file a gcp-job-failure issue —
# that pattern produced 8 spurious issues over 6 days on `s2fpq`.
OUTCOME_OK         = 'ok'                 # at least one month yielded data
OUTCOME_SKIPPED    = 'skipped'            # already-backfilled (not a failure)
OUTCOME_DEAD       = 'dead_ticker'        # every month returned a data-quality reason
OUTCOME_SYSTEMIC   = 'systemic'           # process_symbol raised (caught by outer loop)


# Ticker-level skip threshold for the bulk-backfill re-run path.
# A fully backfilled ticker over 24 months has ~500k 1-min bars; 100k
# is the floor for "substantial coverage already" while still leaving
# room for partial-fetch tickers (where a daily-fetch wrote a single
# day) to be re-fetched. This is intentionally coarser than per-month
# checking because 1,356 tickers × 24 months = 32k queries vs 1,356
# queries — the per-month variant adds 15 minutes of pure DB overhead
# to avoid maybe 5 minutes of AV re-fetches per partial ticker.
_SKIP_TICKER_ROW_THRESHOLD = 100_000


def _ticker_already_backfilled(symbol: str) -> bool:
    """Fast check: does this ticker already have substantial 1-min coverage?

    Returns True when ``market_data_intraday`` has ≥100k rows for this
    ticker in the 2024-01-01+ range — the indicator that a previous
    backfill run completed this ticker. The query uses the
    (ticker, interval, ts) primary-key prefix so it's index-scan fast
    (~10 ms typical). False on any failure (table missing, creds
    missing, transient query error) so a flaky DB doesn't silently
    skip a ticker that should run.
    """
    try:
        from gcp.database import query_to_dataframe, is_cloud_sql_configured
    except ImportError:
        return False
    if not is_cloud_sql_configured():
        return False
    try:
        df = query_to_dataframe(
            "SELECT count(*) AS n FROM market_data_intraday "
            "WHERE ticker = :t AND interval = '1min' "
            "AND ts >= '2024-01-01'",
            {"t": symbol.upper()},
        )
    except Exception as e:
        log.debug("    skip-check failed for %s: %s — will fetch", symbol, e)
        return False
    if df is None or df.empty:
        return False
    try:
        n = int(df.iloc[0]['n'])
    except (TypeError, ValueError, KeyError):
        return False
    return n >= _SKIP_TICKER_ROW_THRESHOLD


def process_symbol(
    symbol: str,
    start_date: str,
    end_date: str,
    api_keys: list,
    force: bool,
) -> str:
    """Fetch all months for a symbol and write to Cloud SQL.

    Returns one of the ``OUTCOME_*`` constants so the outer loop can
    distinguish data-quality failures (dead ticker — every month said
    "Invalid API call") from real successes from systemic errors
    (which still propagate as raised exceptions and are caught by the
    outer loop's try/except). Per CLAUDE.md Rule 3.7: this is a TYPED
    envelope — never a silent fallback.

    Re-fetches every month in the range unconditionally. The previous
    parquet_exists_in_gcs sentinel had completion semantics — a parquet
    only existed after the monthly fetch finished — so it was safe to
    skip on. The SQL table doesn't carry the same signal: fetch_market_data
    inserts daily 1-min bars into the same (ticker, year, month) bucket,
    so an "any row exists" check would mark a month as covered after one
    daily insert and silently drop the rest of the monthly backfill.

    Re-fetching is cheap enough to make the simpler approach worthwhile:
    default range is current_month-1 → today (~2 months), 3 tickers, AV
    premium 150 RPM ≈ 3 sec per night. Backfill of 5 years × 3 tickers ≈
    180 calls ≈ 1.2 min. Idempotent via ON CONFLICT DO UPDATE on
    (ticker, interval, ts).

    For BULK BACKFILL (1,356 tickers via --symbols-file): the script
    skips tickers that already have substantial coverage (≥100k rows
    in 2024-01-01+) so a re-run after a task-timeout completes only
    the NEW tickers, not the ones we already finished. The skip is
    bypassed with --force.
    """
    if not force and _ticker_already_backfilled(symbol):
        log.info("  %s: already has ≥%d rows from a prior run — skipping",
                 symbol, _SKIP_TICKER_ROW_THRESHOLD)
        return OUTCOME_SKIPPED
    months = get_trading_months(start_date, end_date)
    log.info("  %s: %d months (%s → %s)", symbol, len(months), start_date, end_date)

    key_idx = 0
    call_count = 0
    last_call_time = 0.0
    inserted_total = 0
    # Track per-reason counts for the dead-ticker classification at end.
    reason_counts: dict = {}

    for year, month in months:
        month_str = f"{year}-{month:02d}"

        # Rate limiting — uses AlphaVantageConfig.delay_between_calls
        # so premium-tier callers get the full 150 RPM throughput.
        elapsed = time.time() - last_call_time
        if elapsed < _av_cfg.delay_between_calls:
            time.sleep(_av_cfg.delay_between_calls - elapsed)

        api_key = api_keys[key_idx % len(api_keys)]
        df, reason = fetch_month(symbol, year, month, api_key)
        last_call_time = time.time()
        call_count += 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

        # Rotate key on rate limit detection
        if df is None and call_count % 5 == 0:
            key_idx += 1
            log.info("    Rotating to API key %d", key_idx + 1)

        if df is None or df.empty:
            continue

        # Localize timestamps to UTC
        if df['ts'].dt.tz is None:
            df['ts'] = df['ts'].dt.tz_localize('America/New_York').dt.tz_convert('UTC')

        log.info("    %s: %d bars", month_str, len(df))

        # Write to Cloud SQL — upsert so re-runs are safe (overwrites
        # existing rows instead of failing on duplicate primary key).
        if is_cloud_sql_configured():
            upsert_dataframe(
                df, 'market_data_intraday',
                conflict_cols=['ticker', 'interval', 'ts'],
                chunksize=5000,
            )
            inserted_total += len(df)

    log.info("  %s complete: %d rows inserted (reasons=%s)",
             symbol, inserted_total, reason_counts)

    # Dead-ticker classification: ZERO successful fetches AND every
    # non-success fetch returned a permanently-broken reason (Invalid
    # API call / info / no timeseries). If ANY month returned a
    # transient reason (rate_limit, request_error) the ticker is NOT
    # confirmed-dead — a re-run gets another shot at the transient
    # month. We key on FETCH_OK count rather than inserted_total
    # because inserted_total is also 0 when Cloud SQL is unconfigured
    # (dev / dry-run env), which should NOT mark a ticker as dead.
    got_any_data = reason_counts.get(FETCH_OK, 0) > 0
    if not got_any_data and reason_counts:
        non_dead_reasons = set(reason_counts) - _DEAD_TICKER_REASONS
        if not non_dead_reasons:
            return OUTCOME_DEAD
    return OUTCOME_OK


def main():
    parser = argparse.ArgumentParser(description='Fetch AV intraday → Cloud SQL')
    parser.add_argument('--symbol', default='ALL',
                        help='Single symbol, comma- or space-separated list, or ALL '
                             '(SPY IWM QQQ). Examples: --symbol AMD, '
                             '--symbol "AMD NVDA QCOM", --symbol AMD,NVDA,QCOM')
    parser.add_argument('--symbols-file', default=None,
                        help='Path to text file with one ticker per line. Lines '
                             'starting with # are treated as comments. Used by the '
                             'earnings backfill — gives us 50+ tickers without a '
                             'huge --args string in the Cloud Run job spec.')
    parser.add_argument('--start-date', default=None,
                        help='Start date YYYY-MM-DD. Defaults to first of previous month.')
    parser.add_argument('--end-date', default=None,
                        help='End date YYYY-MM-DD. Defaults to today.')
    parser.add_argument('--interval', default='1min',
                        help='Interval (only 1min supported for now)')
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch even if data already exists in GCS')
    args = parser.parse_args()

    # Default date range: previous month → today
    today = date.today()
    first_of_prev_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    start_date = args.start_date or first_of_prev_month.strftime('%Y-%m-%d')
    end_date = args.end_date or today.strftime('%Y-%m-%d')

    api_keys = get_api_keys()
    if not api_keys:
        log.error("No ALPHA_VANTAGE_API_KEY set. Exiting.")
        sys.exit(1)

    # Resolve symbols: ALL → SYMBOLS; file → parse; otherwise split on
    # comma/whitespace to support "AMD,NVDA,QCOM" and "AMD NVDA QCOM"
    # uniformly. Allows the Cloud Run job to take a long list via
    # --args="--symbol,AMD NVDA QCOM" without quoting headaches.
    if args.symbols_file:
        with open(args.symbols_file) as f:
            symbols = [
                line.strip().upper() for line in f
                if line.strip() and not line.strip().startswith('#')
            ]
    elif args.symbol == 'ALL':
        symbols = SYMBOLS
    else:
        raw = args.symbol.replace(',', ' ')
        symbols = [s.strip().upper() for s in raw.split() if s.strip()]

    # Cloud Run Job task sharding — when --tasks=N is set on the job,
    # Cloud Run injects CLOUD_RUN_TASK_INDEX (0..N-1) and
    # CLOUD_RUN_TASK_COUNT (=N) into each task's env. We carve the
    # symbol list into N stripes and each task processes its own.
    # Striping rather than contiguous chunking spreads
    # heavyweight (high-volume) tickers across tasks instead of
    # piling them onto task 0 alphabetically.
    task_idx = int(os.environ.get('CLOUD_RUN_TASK_INDEX', '0'))
    task_cnt = int(os.environ.get('CLOUD_RUN_TASK_COUNT', '1'))
    if task_cnt > 1:
        before = len(symbols)
        symbols = symbols[task_idx::task_cnt]
        log.info("  Task %d/%d — processing %d/%d symbols (stripe)",
                 task_idx, task_cnt, len(symbols), before)

    log.info("AlphaVantage Intraday Fetch Job")
    log.info("  Symbols   : %s", symbols)
    log.info("  Date range: %s → %s", start_date, end_date)
    log.info("  API keys  : %d available", len(api_keys))
    log.info("  SQL       : %s", 'yes' if is_cloud_sql_configured() else 'NO')

    # Per-CLAUDE.md Rule 3.7: typed UNAVAILABLE envelope, not silent
    # swallow. We track three buckets so partial failures are surfaced
    # but only SYSTEMIC failures crash the task:
    #   * dead_tickers    — every month returned a permanently-broken
    #                       AV reason (Invalid API call / info / no
    #                       timeseries). Logged WARNING. Not fatal —
    #                       these tickers should be pruned from the
    #                       watchlist on the next manual sweep.
    #   * systemic_errors — process_symbol raised (DB write failed,
    #                       network outage, anything else). Logged
    #                       ERROR. EXIT 1 — the operator must triage.
    #   * (implicit OK)   — at least one month yielded data.
    dead_tickers: list = []
    systemic_errors: list = []
    succeeded = 0
    for symbol in symbols:
        try:
            outcome = process_symbol(
                symbol, start_date, end_date, api_keys, args.force)
        except Exception as e:
            log.error("  ✗ %s SYSTEMIC failure: %s", symbol, e)
            systemic_errors.append(symbol)
            continue
        if outcome == OUTCOME_DEAD:
            dead_tickers.append(symbol)
        elif outcome in (OUTCOME_OK, OUTCOME_SKIPPED):
            succeeded += 1

    log.info("Run summary: %d succeeded, %d dead_tickers, %d systemic",
             succeeded, len(dead_tickers), len(systemic_errors))
    if dead_tickers:
        log.warning("Dead tickers (consider pruning from watchlist): %s",
                    dead_tickers)
    if systemic_errors:
        log.error("Systemic failures: %s", systemic_errors)
        sys.exit(1)

    log.info("Done.")


if __name__ == '__main__':
    main()
