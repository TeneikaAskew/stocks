#!/usr/bin/env python3
"""
Cloud Run Job: Fetch AV HISTORICAL_OPTIONS at INTRADAY timestamps.

Companion to fetch_av_historical_options.py — that fetcher uses the AV
`date=YYYY-MM-DD` param and returns the EOD chain (snapshot at 4 PM ET).
This one uses `datetime=YYYY-MM-DDTHH:MM:SS` and returns the chain at
the requested intraday minute.

Purpose: backfill SPY 0DTE intraday option snapshots for the
options-exec-backtest's setup-window IV anchors. The EOD-only AV
historical archive (~1 snap/day) is too sparse for an intraday
backtest; the brief's 5-min snapshot-to-trigger window requires
intraday snapshots ALIGNED with the setup timestamps the type model
emits.

Architecture:
  - Reads a list of (ticker, datetime_utc) pairs from EITHER a CSV file
    (--datetimes-file) OR a single inline arg (--ticker --datetime).
  - For each pair, calls AV with `function=HISTORICAL_OPTIONS&datetime=`.
    AV intraday returns the FULL chain (~14k contracts on SPY); we filter
    at insertion time to {0DTE, 1DTE} × ATM±20 strikes to keep the table
    bounded — the backtest never reads the wings.
  - Marks rows with market_session='HISTORICAL_INTRADAY' to distinguish
    from EOD and REALTIME rows.
  - Idempotent: ON CONFLICT (ticker, snapshot_ts, option_type, expiration,
    strike) DO UPDATE so a re-run of the same timestamp converges.

Per CLAUDE.md Rule 0 sizing:
  - Volume: ~5k-30k API calls × ~14k contracts/call = ~70M-420M raw rows.
    After the (0DTE ∪ 1DTE) × ATM-band filter, ~50 rows/call kept;
    final table impact ~250k-1.5M rows for the entire backfill.
  - Velocity: 1 AV call + 1 INSERT per timestamp. AV at 12000/min ceiling
    means network is free; the DB upsert is the throttle (~50 ms/upsert).
  - Wall-clock: 5k calls × ~250 ms = ~20 min. 30k calls × ~250 ms = 2 hr.
  - task-timeout: --task-timeout=14400 (4 hours) gives 2-4x headroom.
  - max-retries: 0. Re-dispatch with --skip-existing for resume.

Usage:
  python -m gcp.fetchers.fetch_av_historical_options_intraday \\
      --datetimes-file /tmp/setup_timestamps.csv \\
      --skip-existing

CSV format expected (header required):
  ticker,datetime_utc
  SPY,2024-06-03T14:00:00
  SPY,2024-06-03T14:30:00
  ...

The datetime is sent to AV verbatim (AV expects ET-local timestamps for
intraday queries — see AV docs). The fetcher converts the CSV's UTC
timestamps to ET before dispatching.
"""

import argparse
import csv
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gcp.database import (
    is_cloud_sql_configured, query_to_dataframe, upsert_dataframe,
)
from lib.config import AlphaVantageConfig
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

AV_BASE_URL = 'https://www.alphavantage.co/query'
_av_cfg = AlphaVantageConfig()

# Strike-band kept per snapshot. SPY's strike grid is $1, so ATM±20 = ~41
# contracts per (option_type, expiration). Times 2 option_types × 2
# expirations (0DTE + 1DTE) = ~164 rows/snapshot kept.
ATM_BAND = 20

# How many expirations forward we keep. 0 = 0DTE only; 1 = 0DTE + 1DTE.
# The backtest's Variant 2 needs 1DTE, so default 1.
EXPIRY_HORIZON_DAYS = 1


def _to_et(dt_utc: datetime) -> str:
    """Convert UTC datetime → America/New_York wall-clock string suitable
    for AV's `datetime=` param. AV docs say the timestamp is local ET."""
    # stdlib zoneinfo (Python 3.9+) — avoids pytz dependency
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        # Python 3.8 backport. Both names cover all our Cloud Run runtimes.
        from backports.zoneinfo import ZoneInfo  # type: ignore
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%dT%H:%M:%S")


def fetch_av_intraday(ticker: str, dt_utc: datetime, api_key: str) -> pd.DataFrame:
    """Fetch ONE intraday options chain snapshot from AV.

    Returns normalized DataFrame ready for etf_options_snapshots, or
    empty on error. NEVER swallows the error silently (Rule 3.7) — logs
    a warning and the caller treats empty as missing-data.
    """
    dt_et_str = _to_et(dt_utc)
    params = {
        'function': 'HISTORICAL_OPTIONS',
        'symbol': ticker,
        'datetime': dt_et_str,
        'apikey': api_key,
        'datatype': 'json',
    }
    try:
        resp = requests.get(AV_BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.error("  AV intraday fetch failed for %s @ %s ET: %s",
                  ticker, dt_et_str, e)
        return pd.DataFrame()

    if data.get('message') != 'success' or data.get('endpoint') != 'Historical Options':
        # AV rate-limit, illegal datetime, or "premium feature" gate
        info = data.get('message') or data.get('Information') or data.get('Error Message') or ''
        log.warning("  AV intraday unexpected response for %s @ %s ET: %s",
                    ticker, dt_et_str, str(info)[:200])
        return pd.DataFrame()

    records = data.get('data', [])
    if not records:
        log.info("  AV intraday: 0 contracts for %s @ %s ET", ticker, dt_et_str)
        return pd.DataFrame()

    return _normalize_intraday_response(pd.DataFrame(records), ticker, dt_utc)


def _normalize_intraday_response(df: pd.DataFrame, ticker: str,
                                  dt_utc: datetime) -> pd.DataFrame:
    """Normalize raw AV HISTORICAL_OPTIONS intraday JSON → etf_options_snapshots.

    Critical differences from the EOD path:
      - snapshot_ts is the REQUESTED intraday timestamp (UTC), not 23:00.
      - market_session = 'HISTORICAL_INTRADAY' (vs 'EOD').
      - Filtered to ATM ± ATM_BAND strikes × {0DTE, 1DTE} expirations.
    """
    out = df.copy()

    numeric = ['strike', 'last', 'mark', 'bid', 'ask', 'volume', 'open_interest',
               'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']
    for col in numeric:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors='coerce')

    snap_ts = pd.Timestamp(dt_utc).tz_convert("UTC") if dt_utc.tzinfo else \
              pd.Timestamp(dt_utc, tz="UTC")
    out['snapshot_ts'] = snap_ts
    out['snapshot_date'] = snap_ts.date()
    out['market_session'] = 'HISTORICAL_INTRADAY'
    out['ticker'] = ticker.upper()
    out['data_source'] = 'alphavantage'

    if 'type' in out.columns:
        out['option_type'] = out['type'].str.lower().map({'call': 'calls', 'put': 'puts'})
    elif 'option_type' in out.columns:
        out['option_type'] = out['option_type'].str.lower()

    rename = {'contractID': 'contract_symbol', 'last': 'last_price'}
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
    if out.empty:
        return out

    # Filter to {0DTE, 1DTE} expirations only — the backtest never reads
    # further-dated contracts.
    out['expiration'] = pd.to_datetime(out['expiration']).dt.date
    snap_date = snap_ts.date()
    horizon = snap_date + pd.Timedelta(days=EXPIRY_HORIZON_DAYS).to_pytimedelta()
    out = out[(out['expiration'] >= snap_date) & (out['expiration'] <= horizon)]
    if out.empty:
        return out

    # Filter to ATM ± ATM_BAND strikes. We don't know the spot from the
    # AV intraday response in a guaranteed-clean field — but we can
    # approximate by using the median strike across all calls with
    # 0 < delta < 0.6 (i.e. roughly ATM±OTM band). Cheap heuristic.
    # If we have an `underlying_price` column from AV, prefer that.
    if 'underlying_price' in out.columns and out['underlying_price'].notna().any():
        spot = float(out['underlying_price'].dropna().iloc[0])
    else:
        atm_calls = out[(out['option_type'] == 'calls')
                        & out['delta'].notna()
                        & (out['delta'] > 0.4) & (out['delta'] < 0.6)]
        if not atm_calls.empty:
            spot = float(atm_calls['strike'].median())
        else:
            spot = float(out['strike'].median())

    out = out[(out['strike'] >= spot - ATM_BAND)
              & (out['strike'] <= spot + ATM_BAND)]
    return out


def _existing_snapshot_keys(ticker: str, datetimes: list[datetime]) -> set[pd.Timestamp]:
    """Return the set of (ticker, snapshot_ts) UTC timestamps already in
    etf_options_snapshots — used by --skip-existing to make re-dispatch
    idempotent."""
    if not is_cloud_sql_configured() or not datetimes:
        return set()
    # SQL IN-list of timestamps. Postgres handles a few hundred params
    # fine; if the caller is dispatching 10k+, this becomes a perf issue —
    # then we'd switch to a temp-table pattern. For our backfill volume
    # (~5-30k total split across many invocations), inline is fine.
    placeholders = ",".join(f":t{i}" for i in range(len(datetimes)))
    params = {f"t{i}": pd.Timestamp(dt, tz="UTC").to_pydatetime()
              for i, dt in enumerate(datetimes)}
    params["tkr"] = ticker
    df = query_to_dataframe(
        f"SELECT DISTINCT snapshot_ts FROM etf_options_snapshots "
        f"WHERE ticker = :tkr "
        f"AND market_session = 'HISTORICAL_INTRADAY' "
        f"AND snapshot_ts IN ({placeholders})",
        params,
    )
    return set(pd.to_datetime(df['snapshot_ts'], utc=True))


def process_pair(ticker: str, dt_utc: datetime, api_key: str) -> int:
    """Fetch + insert one (ticker, datetime) pair. Returns row count inserted."""
    df = fetch_av_intraday(ticker, dt_utc, api_key)
    if df.empty:
        return 0

    conflict_cols = ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike']
    before = len(df)
    df = df.drop_duplicates(subset=conflict_cols, keep='last')
    if len(df) < before:
        log.info("    deduped %d → %d rows", before, len(df))

    if is_cloud_sql_configured():
        upsert_dataframe(df, 'etf_options_snapshots', conflict_cols)
        log.info("    ✓ %d rows upserted for %s @ %s",
                 len(df), ticker, dt_utc.isoformat())
    return len(df)


def _load_timestamps_from_csv(path: str) -> list[tuple[str, datetime]]:
    """Read a CSV of (ticker, datetime_utc) pairs. The CSV must have a
    header row with columns 'ticker' and 'datetime_utc'.

    Accepts a local path or a gs:// URL. The Cloud Run Job that emits
    the CSV (`options-exec-backtest --mode=emit_timestamps`) and this
    fetcher run in different containers; the canonical handoff is via
    GCS, so the loader handles `gs://` transparently.
    """
    pairs = []
    if path.startswith("gs://"):
        # gs://bucket/blob/path
        without_scheme = path[len("gs://"):]
        bucket_name, _, blob_path = without_scheme.partition("/")
        if not blob_path:
            raise ValueError(f"Invalid GCS URL (missing blob path): {path!r}")
        from google.cloud import storage as gcs
        log.info("downloading timestamps CSV from %s", path)
        text = gcs.Client().bucket(bucket_name).blob(blob_path).download_as_text()
        reader = csv.DictReader(text.splitlines())
        source_desc = path
    else:
        f = open(path)  # noqa: SIM115 — we iterate then close manually below
        reader = csv.DictReader(f)
        source_desc = path
    try:
        for row in reader:
            t = row['ticker'].upper().strip()
            dt_str = row['datetime_utc'].strip()
            dt = pd.Timestamp(dt_str)
            if dt.tzinfo is None:
                dt = dt.tz_localize("UTC")
            else:
                dt = dt.tz_convert("UTC")
            pairs.append((t, dt.to_pydatetime()))
    finally:
        if not path.startswith("gs://"):
            f.close()
    log.info("loaded %d (ticker, datetime) pairs from %s", len(pairs), source_desc)
    return pairs


def main():
    parser = argparse.ArgumentParser(
        description='Fetch AV HISTORICAL_OPTIONS intraday → Cloud SQL.')
    parser.add_argument('--ticker', default=None,
                        help='Ticker for single-shot mode (e.g. SPY).')
    parser.add_argument('--datetime', default=None,
                        help='UTC ISO timestamp for single-shot mode (e.g. 2024-06-03T14:00:00).')
    parser.add_argument('--datetimes-file', default=None,
                        help='CSV with header (ticker, datetime_utc) for batch mode.')
    parser.add_argument('--skip-existing', action='store_true', default=False,
                        help='Skip (ticker, snapshot_ts) pairs already in Cloud SQL.')
    parser.add_argument('--limit', type=int, default=0,
                        help='Process at most N pairs (0 = no limit). For sandbox smoke tests.')
    args = parser.parse_args()

    api_key = os.environ.get('AV_API_KEY') or os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        log.error("AV_API_KEY / ALPHA_VANTAGE_API_KEY not set")
        sys.exit(2)

    # Resolve pair list.
    if args.datetimes_file:
        pairs = _load_timestamps_from_csv(args.datetimes_file)
    elif args.ticker and args.datetime:
        dt = pd.Timestamp(args.datetime)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        pairs = [(args.ticker.upper(), dt.to_pydatetime())]
    else:
        log.error("Pass either --datetimes-file OR (--ticker --datetime)")
        sys.exit(2)

    if args.limit > 0:
        pairs = pairs[:args.limit]

    # --skip-existing: pre-fetch the set of already-ingested keys, group by
    # ticker for batched lookups.
    skip = set()
    if args.skip_existing:
        by_ticker: dict[str, list[datetime]] = {}
        for t, dt in pairs:
            by_ticker.setdefault(t, []).append(dt)
        for t, dts in by_ticker.items():
            # Chunk the lookup so the IN-list doesn't exceed Postgres param limits.
            CHUNK = 500
            for i in range(0, len(dts), CHUNK):
                existing = _existing_snapshot_keys(t, dts[i:i + CHUNK])
                for ts in existing:
                    skip.add((t, pd.Timestamp(ts).floor("s").to_pydatetime()))
        log.info("skip-existing: %d/%d pairs already present", len(skip), len(pairs))

    total_inserts = 0
    t0 = time.time()
    for i, (ticker, dt_utc) in enumerate(pairs, 1):
        key = (ticker, pd.Timestamp(dt_utc, tz="UTC").floor("s").to_pydatetime())
        if args.skip_existing and key in skip:
            if i % 100 == 0:
                log.info("[%d/%d] skipped (already present)", i, len(pairs))
            continue
        try:
            n = process_pair(ticker, dt_utc, api_key)
            total_inserts += n
            if i % 25 == 0 or i == len(pairs):
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0
                log.info("[%d/%d] %.1f pairs/sec  cumulative_rows=%d",
                         i, len(pairs), rate, total_inserts)
        except Exception as e:
            log.error("[%d/%d] FAILED %s @ %s: %s",
                      i, len(pairs), ticker, dt_utc.isoformat(), e)
            # Per Rule 0: continue the batch, log the failure — partial
            # progress is durable via per-pair upsert. Do NOT silently swallow:
            # the error went to stderr via log.error.

    log.info("done — %d pairs processed, %d rows upserted, %.1fs wall-clock",
             len(pairs), total_inserts, time.time() - t0)


if __name__ == '__main__':
    main()
