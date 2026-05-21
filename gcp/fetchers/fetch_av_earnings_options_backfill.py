#!/usr/bin/env python3
"""
Cloud Run Job: backfill T-1 options snapshots for every earnings event.

Sibling to ``fetch_av_historical_options.py`` (which covers SPY/IWM/QQQ/SPX
end-of-day daily snapshots into ``etf_options_snapshots``). This script
walks ``earnings_reactions`` and, for each (ticker, reported_date), pulls
AV HISTORICAL_OPTIONS for the close-of-T-1 chain (reported_date - 1) and
writes the rows relevant to the earnings event into
``earnings_options_snapshots``.

We filter to options expiring within 14 calendar days of the earnings
report — the post-earnings Friday and one expiry after — so the chain
isn't bloated with monthly/quarterly expiries irrelevant to the event.
This caps storage at ~50-150 rows per event (~3-8M rows for the full
backfill) instead of 2,000+ per event.

Resume-safe: events with any prior row in ``earnings_options_snapshots``
at the same (symbol, snapshot_date) are skipped on a per-event basis,
saving AV quota on partial-completion restarts. Idempotent: writes use
ON CONFLICT DO NOTHING on the table's UNIQUE constraint
``(symbol, snapshot_ts, option_type, expiration, strike)``.

Capacity (CLAUDE.md Rule 0):
  - Volume: ~41,756 events; one AV call per event.
  - Velocity: 150 RPM AV premium → 60/150 = 0.4 s/call.
  - Wall-clock: 41,756 × 0.4 s ≈ 167 min ≈ 2.8 h (network-bound; AV
    response latency dominates over the configured delay so plan for
    ~4.5 h actual).
  - task-timeout: 32400 s (9 h) — 2× headroom over actual estimate.
  - Memory: 1 GiB — processed per-event, no accumulation across events.

Usage:
    python -m gcp.fetchers.fetch_av_earnings_options_backfill
    python -m gcp.fetchers.fetch_av_earnings_options_backfill --limit 100      # test slice
    python -m gcp.fetchers.fetch_av_earnings_options_backfill --tickers AAPL MSFT
    python -m gcp.fetchers.fetch_av_earnings_options_backfill --since 2020-01-01
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import (
    is_cloud_sql_configured,
    query_to_dataframe,
    upsert_dataframe,
)
from lib.config import AlphaVantageConfig
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'
_av_cfg = AlphaVantageConfig()

# Window around the earnings event to retain in earnings_options_snapshots.
# Wide enough to capture both the post-earnings expiry AND the one after
# (for IV-crush comparison) without bloating with quarterly chains.
_EXPIRY_WINDOW_DAYS = 14

# Pre-2008 events are skipped — AV HISTORICAL_OPTIONS coverage starts
# 2008-01-02 per their docs. Calls on earlier dates return empty data.
_AV_FLOOR = date(2008, 1, 2)


def _fetch_av_options(symbol: str, snapshot_dt: date,
                      api_key: str) -> pd.DataFrame:
    """Fetch the AV HISTORICAL_OPTIONS chain for one (symbol, date).

    Returns the raw DataFrame as parsed from AV's JSON `data` array. The
    caller filters expiries + normalises columns. Raises on transient
    HTTP errors so retry/backoff is decided at the outer driver, not
    silently swallowed (CLAUDE.md §3.7 — no silent fallback in
    data-access code).
    """
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol':   symbol,
        'date':     snapshot_dt.isoformat(),
        'apikey':   api_key,
        'datatype': 'json',
    }
    resp = requests.get(AV_BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get('message') != 'success' or data.get('endpoint') != 'Historical Options':
        # Vendor-side soft-failure (rate limit, unknown symbol, pre-IPO
        # date). Log the explanation and return empty — the EVENT-LEVEL
        # caller increments a "no_data" counter; missing rows are
        # reported via the `n_with_options` calibration column, not
        # silently zero (CLAUDE.md §3.7).
        info = data.get('Information') or data.get('Note') or data.get('message')
        log.info("  AV: no data for %s %s — %s", symbol, snapshot_dt, str(info)[:120])
        return pd.DataFrame()
    records = data.get('data', [])
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _normalise(raw: pd.DataFrame, symbol: str, snapshot_dt: date,
               reported_date: date) -> pd.DataFrame:
    """Filter to expiries within the event window + reshape to schema.

    Target schema: ``earnings_options_snapshots`` columns
    (symbol, snapshot_ts, snapshot_date, contract_symbol, option_type,
     expiration, strike, bid, ask, last_price, volume, open_interest,
     implied_volatility, delta, gamma, theta, vega, rho, underlying_price,
     data_source, in_the_money).
    """
    if raw.empty:
        return raw

    out = raw.copy()
    # AV returns strings — coerce numeric.
    numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
               'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
    for col in numeric:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')

    # Parse expiration; drop rows we can't anchor.
    out['expiration'] = pd.to_datetime(out['expiration'], errors='coerce').dt.date
    out = out.dropna(subset=['expiration', 'strike', 'type'])

    # Filter to (reported_date − 0 days) ≤ expiration ≤ (reported_date +
    # window). Note the lower bound: we want post-earnings expiries; an
    # expiry that lapsed BEFORE the earnings event isn't useful.
    lo = reported_date
    hi = reported_date + timedelta(days=_EXPIRY_WINDOW_DAYS)
    out = out[(out['expiration'] >= lo) & (out['expiration'] <= hi)]
    if out.empty:
        return out

    # Reshape to target schema.
    out['symbol'] = symbol.upper()
    out['snapshot_ts'] = pd.Timestamp(f"{snapshot_dt.isoformat()}T23:00:00Z")
    out['snapshot_date'] = snapshot_dt
    out['data_source'] = 'alphavantage'
    out['option_type'] = out['type'].astype(str).str.lower().map(
        {'call': 'calls', 'put': 'puts'})
    # AV doesn't return an underlying_price field — we infer it later
    # from market_data_daily during the sweep's join. Leaving NULL here
    # is correct (CLAUDE.md §3.7 — no fabricated value).
    out['underlying_price'] = None
    # in_the_money requires underlying; defer.
    out['in_the_money'] = None
    rename = {'contractID': 'contract_symbol', 'last': 'last_price'}
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})

    keep = [
        'symbol', 'snapshot_ts', 'snapshot_date', 'contract_symbol',
        'option_type', 'expiration', 'strike',
        'bid', 'ask', 'last_price', 'volume', 'open_interest',
        'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho',
        'underlying_price', 'in_the_money', 'data_source',
    ]
    out = out[[c for c in keep if c in out.columns]]
    out = out.dropna(subset=['option_type'])

    # Dedupe on the UNIQUE constraint key. AV occasionally repeats
    # contracts (e.g. weekly + monthly with the same strike).
    conflict_cols = ['symbol', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    out = out.drop_duplicates(subset=conflict_cols, keep='last')
    return out


def _already_have(symbol: str, snapshot_dt: date) -> bool:
    """True when at least one snapshot row exists for (symbol, snapshot_date).

    Per-event idempotency check — saves AV quota on restart. Granularity
    is coarser than per-strike because backfilling a partial event isn't
    something this script does; the unit of work is one event.
    """
    hit = query_to_dataframe(
        "SELECT 1 FROM earnings_options_snapshots "
        "WHERE symbol = :s AND snapshot_date = :d LIMIT 1",
        {"s": symbol, "d": snapshot_dt},
    )
    return not hit.empty


def _load_event_list(args) -> pd.DataFrame:
    """Pull the (ticker, reported_date) pairs we need to backfill.

    Filters:
      - reported_date >= AV floor (2008-01-02)
      - --since cutoff if provided
      - --tickers filter if provided
      - --limit / --offset for partial runs

    Ordered by reported_date DESC so a partial run prioritises recent
    events first — they're more likely to be needed by an active brief
    consumer than 2010 events.
    """
    where_parts = [f"reported_date >= '{_AV_FLOOR.isoformat()}'"]
    params: dict = {}

    if args.since:
        where_parts.append("reported_date >= :since")
        params['since'] = args.since

    if args.tickers:
        tks = [t.upper() for t in args.tickers]
        placeholders = ",".join(f":t{i}" for i in range(len(tks)))
        where_parts.append(f"ticker IN ({placeholders})")
        for i, t in enumerate(tks):
            params[f"t{i}"] = t

    where_sql = " AND ".join(where_parts)
    limit_sql = ""
    if args.limit:
        limit_sql += f" LIMIT {int(args.limit)}"
    if args.offset:
        limit_sql += f" OFFSET {int(args.offset)}"

    sql = (
        f"SELECT DISTINCT ticker, reported_date "
        f"FROM earnings_reactions "
        f"WHERE {where_sql} "
        f"ORDER BY reported_date DESC, ticker"
        f"{limit_sql}"
    )
    return query_to_dataframe(sql, params)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill T-1 options snapshots for earnings_reactions events"))
    parser.add_argument('--tickers', nargs='+', default=None,
                        help='Restrict to specific tickers (uppercase).')
    parser.add_argument('--since', default=None,
                        help='Only events on/after this YYYY-MM-DD.')
    parser.add_argument('--limit', type=int, default=None,
                        help='Cap number of events processed (testing).')
    parser.add_argument('--offset', type=int, default=None,
                        help='Skip the first N events (shard fan-out).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Plan + count only; no AV calls / no writes.')
    parser.add_argument('--no-skip-existing', action='store_true',
                        help='Re-fetch events even if they already have rows. '
                             'Default: skip (saves AV quota on restart).')
    args = parser.parse_args()

    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        log.error("AV_API_KEY / ALPHA_VANTAGE_API_KEY not set")
        sys.exit(1)
    if not is_cloud_sql_configured():
        log.error("Cloud SQL not configured")
        sys.exit(1)

    log.info("loading event list...")
    events = _load_event_list(args)
    total = len(events)
    log.info("  %d events to consider (filters: since=%s tickers=%s limit=%s offset=%s)",
             total, args.since, args.tickers, args.limit, args.offset)

    if args.dry_run:
        log.info("--dry-run set — exiting without AV calls or writes")
        return

    skip_existing = not args.no_skip_existing
    delay_s = _av_cfg.delay_between_calls

    n_skipped_existing = 0
    n_av_calls = 0
    n_av_empty = 0
    n_rows_written = 0
    n_errors = 0
    t_start = time.time()
    last_call_t = 0.0

    for i, row in events.iterrows():
        symbol = str(row['ticker']).upper()
        reported_dt = pd.to_datetime(row['reported_date']).date()
        snapshot_dt = reported_dt - timedelta(days=1)

        # Per-event idempotency check — coarser than strike-level but
        # the unit of work IS the event, so this is the right grain.
        if skip_existing and _already_have(symbol, snapshot_dt):
            n_skipped_existing += 1
            if (i + 1) % 500 == 0:
                _progress(i + 1, total, n_av_calls, n_av_empty,
                          n_rows_written, n_skipped_existing, n_errors, t_start)
            continue

        # Rate-limit only between AV calls (skip-existing path doesn't
        # call AV, so it shouldn't consume RPM budget).
        if n_av_calls > 0:
            elapsed = time.time() - last_call_t
            if elapsed < delay_s:
                time.sleep(delay_s - elapsed)
        last_call_t = time.time()
        n_av_calls += 1

        try:
            raw = _fetch_av_options(symbol, snapshot_dt, api_key)
        except requests.exceptions.HTTPError as e:
            # HTTP-level error (5xx, rate limit, etc.). Per Rule 0:
            # bounded retry, then surface. One retry here covers
            # transient blips; persistent failures continue with the
            # next event so a single bad ticker doesn't tank a 4h run.
            log.warning("  %s %s HTTPError %s — sleeping 5s, retrying once",
                        symbol, snapshot_dt, e)
            time.sleep(5)
            try:
                raw = _fetch_av_options(symbol, snapshot_dt, api_key)
            except Exception as e2:
                log.error("  %s %s: retry failed (%s) — skipping",
                          symbol, snapshot_dt, e2)
                n_errors += 1
                continue
        except Exception as e:
            log.error("  %s %s: %s — skipping", symbol, snapshot_dt, e)
            n_errors += 1
            continue

        if raw.empty:
            n_av_empty += 1
            continue

        df = _normalise(raw, symbol, snapshot_dt, reported_dt)
        if df.empty:
            # AV returned the chain but no contracts in the event window
            # — usually means the ticker had no listed options expiring
            # near the earnings date. Count as empty, not error.
            n_av_empty += 1
            continue

        try:
            conflict_cols = ['symbol', 'snapshot_ts', 'option_type',
                             'expiration', 'strike']
            upsert_dataframe(df, 'earnings_options_snapshots', conflict_cols)
            n_rows_written += len(df)
        except Exception as e:
            log.error("  %s %s upsert failed (%d rows): %s",
                      symbol, snapshot_dt, len(df), e)
            n_errors += 1

        if (i + 1) % 100 == 0:
            _progress(i + 1, total, n_av_calls, n_av_empty,
                      n_rows_written, n_skipped_existing, n_errors, t_start)

    elapsed = time.time() - t_start
    log.info(
        "DONE in %.1f min — events=%d av_calls=%d av_empty=%d "
        "rows_written=%d skipped_existing=%d errors=%d",
        elapsed / 60.0, total, n_av_calls, n_av_empty,
        n_rows_written, n_skipped_existing, n_errors,
    )
    if n_errors > 0:
        # Surface non-zero errors so the Cloud Run Job exit code reflects
        # partial failures — caller can re-run to mop up.
        sys.exit(2)


def _progress(i: int, total: int, n_calls: int, n_empty: int,
              n_rows: int, n_skipped: int, n_errors: int,
              t_start: float) -> None:
    elapsed = time.time() - t_start
    rate = n_calls / elapsed if elapsed > 0 else 0.0
    remaining = total - i
    eta_min = (remaining / rate / 60.0) if rate > 0 else float('nan')
    log.info(
        "  %d/%d events | av_calls=%d empty=%d rows=%d skipped=%d errors=%d | "
        "%.1f calls/s eta=%.1f min",
        i, total, n_calls, n_empty, n_rows, n_skipped, n_errors, rate, eta_min,
    )


if __name__ == '__main__':
    main()
