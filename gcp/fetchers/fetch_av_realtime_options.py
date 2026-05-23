#!/usr/bin/env python3
"""
Cloud Run Job: Fetch intraday AV REALTIME_OPTIONS and write to Cloud SQL.

Companion to fetch_av_historical_options.py. The historical job runs nightly
and writes one EOD snapshot per ticker per day (market_session='EOD'). This
job runs every 5 minutes during RTH (09:30-16:00 ET Mon-Fri) and writes one
intraday snapshot per ticker per fire (market_session='REALTIME'). Both
coexist in etf_options_snapshots via the unique key
(ticker, snapshot_ts, option_type, expiration, strike).

Why this exists:
    Added 2026-05-22 after AV subscription upgrade to the $199.99/mo,
    600 req/min, realtime-options tier. Prior to this, the entire repo
    only had EOD options data — see
    docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md for the multi-track
    plan this fetcher unlocks:
      Track 1 — premarket brief gamma section (realtime-primary)
      Track 2 — 0DTE theta replacement (observed > empirical curve)
      Track 3 — signal monitor "approaching the King" alerts
      Track 4 — OptionsFlowPage freshness badge
      Track 5 — AI insights gamma integration

Usage:
    python -m gcp.fetchers.fetch_av_realtime_options [--tickers "SPY IWM QQQ"]
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
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
DEFAULT_TICKERS = ['SPY', 'IWM', 'QQQ']
_av_cfg = AlphaVantageConfig()

# Sentinel contractID prefix AV returns when the subscription tier does NOT
# include REALTIME_OPTIONS — we explicitly detect and reject this so a
# silently-downgraded plan doesn't poison etf_options_snapshots with fake
# rows like contractID=XXYYZZ999999C00020000.
_SAMPLE_CONTRACT_PREFIX = 'XXYYZZ'


class RealtimeOptionsUnavailable(RuntimeError):
    """Raised when AV REALTIME_OPTIONS returned the sample/illustration
    payload (subscription tier doesn't include the endpoint) or any
    response shape we cannot trust. Caller decides retry vs. fail-loud.

    Per CLAUDE.md Rule 3.7: external-API failures must return a typed
    UNAVAILABLE envelope or re-raise, never a synthetic empty DataFrame.
    """


def fetch_av_realtime_options(ticker: str, api_key: str,
                              snapshot_ts: datetime) -> pd.DataFrame:
    """
    Fetch the current intraday options chain from AV REALTIME_OPTIONS.

    Args:
        ticker:       symbol (e.g. 'SPY')
        api_key:      AV API key with realtime-options entitlement
        snapshot_ts:  the wall-clock timestamp to stamp this snapshot with.
                      Passed in so every ticker in a single run shares
                      the same snapshot_ts (multi-ticker queries don't
                      drift across ticker iteration time).

    Returns:
        Normalized DataFrame ready for etf_options_snapshots.

    Raises:
        RealtimeOptionsUnavailable: AV returned sample data or an error
            response — never returns an empty DataFrame to a caller that
            might write it (Rule 3.7).
        requests.exceptions.HTTPError: HTTP-layer failures bubble up.
    """
    params = {
        'function':       'REALTIME_OPTIONS',
        'symbol':         ticker,
        'require_greeks': 'true',
        'apikey':         api_key,
        'datatype':       'json',
    }

    resp = requests.get(AV_BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # AV error shapes — surface them, don't silently swallow.
    if 'Information' in data and 'data' not in data:
        raise RealtimeOptionsUnavailable(
            f"AV REALTIME_OPTIONS rate-limit / info response for {ticker}: "
            f"{data['Information'][:200]}"
        )
    if 'Error Message' in data:
        raise RealtimeOptionsUnavailable(
            f"AV REALTIME_OPTIONS error for {ticker}: {data['Error Message']}"
        )

    records = data.get('data', [])

    # Detect the sample/illustration payload BEFORE the generic
    # unexpected-message check, because the sample response also has
    # endpoint='Realtime Options' but a long disclaimer message instead
    # of 'success'. The contractID prefix is the most specific marker —
    # live SPY contractIDs start 'SPY', the sample starts 'XXYYZZ'.
    if records:
        first_contract = str(records[0].get('contractID', ''))
        if first_contract.startswith(_SAMPLE_CONTRACT_PREFIX):
            raise RealtimeOptionsUnavailable(
                f"AV REALTIME_OPTIONS returned sample/illustration data for "
                f"{ticker} (first contractID={first_contract!r}) — subscription "
                "tier likely lacks realtime-options entitlement"
            )

    if data.get('endpoint') != 'Realtime Options' or data.get('message') != 'success':
        raise RealtimeOptionsUnavailable(
            f"AV REALTIME_OPTIONS unexpected response for {ticker}: "
            f"endpoint={data.get('endpoint')!r} message={data.get('message')!r}"
        )

    if not records:
        # Empty list during market hours is genuinely anomalous — treat as
        # UNAVAILABLE rather than silently writing nothing. Caller logs and
        # the Cloud Run Job exits non-zero so the scheduler surfaces it.
        raise RealtimeOptionsUnavailable(
            f"AV REALTIME_OPTIONS returned 0 contracts for {ticker} — "
            "likely a tier-downgrade or off-hours fire"
        )

    df = pd.DataFrame(records)
    return _normalize_av_response(df, ticker, snapshot_ts)


def _normalize_av_response(df: pd.DataFrame, ticker: str,
                           snapshot_ts: datetime) -> pd.DataFrame:
    """Normalize raw AV REALTIME_OPTIONS JSON response to etf_options_snapshots schema.

    Mirrors fetch_av_historical_options._normalize_av_response with two
    deltas: snapshot_ts is the live fetch time (not 23:00 UTC EOD marker),
    and market_session is 'REALTIME' (not 'EOD'). Same Greek columns, same
    rename map — both AV endpoints return identical JSON shapes.
    """
    out = df.copy()

    numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
               'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
    for col in numeric:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')

    out['snapshot_ts'] = pd.Timestamp(snapshot_ts)
    out['snapshot_date'] = pd.Timestamp(snapshot_ts).date()
    out['market_session'] = 'REALTIME'
    out['ticker'] = ticker.upper()
    out['data_source'] = 'alphavantage'

    if 'type' in out.columns:
        out['option_type'] = out['type'].str.lower().map({'call': 'calls', 'put': 'puts'})
    elif 'option_type' in out.columns:
        out['option_type'] = out['option_type'].str.lower()

    rename = {
        'contractID': 'contract_symbol',
        'expiration': 'expiration',
        'last':       'last_price',
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


def process_ticker(ticker: str, api_key: str, snapshot_ts: datetime) -> int:
    """Fetch realtime options for one ticker → Cloud SQL. Returns row count written."""
    log.info("  Fetching %s realtime options at %s...",
             ticker, snapshot_ts.isoformat())

    df = fetch_av_realtime_options(ticker, api_key, snapshot_ts)
    log.info("    %d contracts received", len(df))

    # Dedupe defensively — AV occasionally returns duplicate contract rows
    # within a single response.
    conflict_cols = ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    before = len(df)
    df = df.drop_duplicates(subset=conflict_cols, keep='last')
    if len(df) < before:
        log.info("    deduped %d → %d rows", before, len(df))

    if is_cloud_sql_configured():
        upsert_dataframe(df, 'etf_options_snapshots', conflict_cols)
        log.info("    ✓ upserted %d rows to Cloud SQL", len(df))
    else:
        log.warning("    Cloud SQL not configured — skipping write")

    return len(df)


def main():
    import time

    parser = argparse.ArgumentParser(
        description='Fetch intraday AV REALTIME_OPTIONS to Cloud SQL'
    )
    parser.add_argument(
        '--tickers',
        default=' '.join(DEFAULT_TICKERS),
        help='Space-separated tickers (default: "SPY IWM QQQ"). '
             'SPX/NDX excluded — AV returns "-" for index-option Greeks; '
             'the BSM solver in lib/options_greeks.py only runs in the '
             'EOD pipeline today.',
    )
    args = parser.parse_args()

    api_key = (os.environ.get('AV_API_KEY')
               or os.environ.get('ALPHA_VANTAGE_API_KEY', ''))
    if not api_key:
        log.error("AV_API_KEY not set — cannot fetch realtime options")
        sys.exit(1)

    tickers = args.tickers.upper().split()
    # Single snapshot_ts for the whole batch so all tickers share an
    # alignment point. Per-ticker iteration time is ~3-5 seconds; the
    # tiny drift across that window is irrelevant for a 5-min cadence.
    snapshot_ts = datetime.now(timezone.utc)

    log.info("Fetch AV Realtime Options Job")
    log.info("  Tickers     : %s", tickers)
    log.info("  Snapshot_ts : %s", snapshot_ts.isoformat())
    log.info("  SQL         : %s",
             'yes' if is_cloud_sql_configured() else 'NO')
    log.info("  AV key      : set (len=%d)", len(api_key))

    errors = []
    total_rows = 0
    for i, ticker in enumerate(tickers):
        if i > 0:
            time.sleep(_av_cfg.delay_between_calls)
        try:
            total_rows += process_ticker(ticker, api_key, snapshot_ts)
        except RealtimeOptionsUnavailable as e:
            # Track which tickers were unavailable; we still try the rest.
            # Job exits non-zero at the end if any ticker failed, which lets
            # Cloud Run/Scheduler surface the failure without spamming
            # one-ticker-failed emails when the other two succeeded.
            log.error("  ✗ %s realtime UNAVAILABLE: %s", ticker, e)
            errors.append(f"{ticker}: {e}")
        except Exception as e:
            log.error("  ✗ %s failed: %s", ticker, e)
            errors.append(f"{ticker}: {e}")

    log.info(
        "Done. %d tickers, %d total contracts written, %d errors.",
        len(tickers), total_rows, len(errors),
    )

    if errors:
        log.error("Failed (%d): %s", len(errors), errors)
        sys.exit(1)


if __name__ == '__main__':
    main()
