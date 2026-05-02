#!/usr/bin/env python3
"""
Migrate all local Parquet data to GCS (raw backup) + Cloud SQL (structured).

Run from GCP Cloud Shell or any machine with sufficient disk space and
gcloud credentials. NOT intended to be run from the codespace (disk may be full).

Usage:
    # Full migration (GCS + Cloud SQL)
    python gcp/migrate_to_gcp.py

    # Dry run (no writes)
    python gcp/migrate_to_gcp.py --dry-run

    # Only upload raw files to GCS, skip Cloud SQL
    python gcp/migrate_to_gcp.py --skip-sql

    # Backfill 20yr daily OHLCV from AlphaVantage
    python gcp/migrate_to_gcp.py --table market_data_daily_av

    # Compute all technical indicators on the daily series already in Cloud SQL
    python gcp/migrate_to_gcp.py --table daily_indicators --skip-gcs

    # Backfill AV EOD historical options (data_source='alphavantage') — run in background
    nohup python gcp/migrate_to_gcp.py --table av_options --skip-gcs > /tmp/av_options.log 2>&1 &

    # Custom data directory
    python gcp/migrate_to_gcp.py --data-dir /path/to/data

Environment variables:
    CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME  (required for --skip-sql=False)
    GCS_BUCKET   e.g. adept-mountain-474619-d4-trading-data
    ALPHA_VANTAGE_API_KEY  (required for --table market_data_daily_av; 150 RPM plan)
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.logging_config import setup_logging
setup_logging()
log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).parent.parent / 'data'
TICKERS = ['spy', 'iwm', 'qqq', 'spx']


# ── GCS helpers ───────────────────────────────────────────────────────────────

def gcs_upload(local_path: Path, bucket: str, blob_prefix: str, dry_run: bool) -> str:
    """Upload a local file to GCS; return the gs:// URI."""
    from google.cloud import storage as gcs
    relative = local_path.name
    blob_name = f"{blob_prefix}/{relative}"
    uri = f"gs://{bucket}/{blob_name}"

    if dry_run:
        log.info("  [DRY RUN] would upload %s → %s", local_path, uri)
        return uri

    client = gcs.Client()
    bkt = client.bucket(bucket)
    blob = bkt.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    log.info("  ↑ %s", uri)
    return uri


def upload_raw_parquets(data_dir: Path, bucket: str, dry_run: bool):
    """Upload every .parquet in data_dir to gs://BUCKET/raw/..."""
    log.info("Uploading raw Parquet files to GCS...")
    files = list(data_dir.rglob('*.parquet'))
    log.info("  Found %d parquet files", len(files))

    for i, f in enumerate(files, 1):
        relative_dir = f.parent.relative_to(data_dir)
        gcs_upload(f, bucket, f"raw/{relative_dir}", dry_run)
        if i % 20 == 0:
            log.info("  %d / %d uploaded", i, len(files))

    log.info("Raw upload complete: %d files", len(files))


# ── Column normalization ───────────────────────────────────────────────────────

COLUMN_MAP = {
    'Last': 'close', 'last': 'close', 'Adj Close': 'close', 'adj_close': 'close',
    'Close': 'close', 'Open': 'open', 'High': 'high', 'Low': 'low',
    'Volume': 'volume', 'open': 'open', 'high': 'high', 'low': 'low',
    'volume': 'volume',
}

# add_all_indicators() column name → market_data_daily SQL column name.
# Single source of truth lives in gcp/database.py. Imported here so the
# one-shot migrator and the live fetcher can never drift on rename.
from gcp.database import DAILY_INDICATOR_TO_SQL_COLUMN as _DAILY_IND_TO_SQL


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to lowercase SQL-friendly names."""
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
    return df


# ── Market data daily indicators backfill ─────────────────────────────────────

def backfill_daily_indicators(data_dir: Path, dry_run: bool):
    """
    Compute and upsert all technical indicators for the full market_data_daily
    history already in Cloud SQL (6,600+ rows per ticker from AV backfill).

    Reads each ticker's full OHLCV series, runs add_all_indicators() on it,
    computes 20-day historical volatility, then upserts the indicator columns
    for every row.  Safe to re-run: uses ON CONFLICT UPDATE.

    Usage:
        python gcp/migrate_to_gcp.py --table daily_indicators --skip-gcs
    """
    import numpy as np
    from lib.indicators import add_all_indicators
    from gcp.database import query_to_dataframe, upsert_dataframe

    log.info("Backfilling daily indicators for market_data_daily...")

    for ticker_lower in TICKERS:
        ticker = ticker_lower.upper()
        log.info("  Processing %s...", ticker)

        sql = """
            SELECT date,
                   open  AS "Open",
                   high  AS "High",
                   low   AS "Low",
                   close AS "Close",
                   volume AS "Volume"
            FROM market_data_daily
            WHERE ticker = :ticker
            ORDER BY date ASC
        """
        try:
            df = query_to_dataframe(sql, {'ticker': ticker})
        except Exception as e:
            log.warning("  ✗ %s query failed: %s", ticker, e)
            continue

        if df.empty:
            log.info("  %s: no rows found, skipping", ticker)
            continue

        log.info("  %s: %d rows (%s → %s)",
                 ticker, len(df), df['date'].min(), df['date'].max())

        # Compute indicators on the full series
        enriched = add_all_indicators(df, close_col='Close')
        enriched['volatility_20d'] = (
            enriched['Close'].pct_change().rolling(20).std() * np.sqrt(252)
        )

        # Integer columns in the schema
        _INT_COLS = {'consecutive_up', 'consecutive_down'}

        # Build upsert rows — only include computed (non-NaN) values
        rows = []
        for i, (_, row) in enumerate(enriched.iterrows()):
            r: dict = {'ticker': ticker, 'date': df['date'].iloc[i]}
            for src, dst in _DAILY_IND_TO_SQL.items():
                val = row.get(src)
                if val is not None and pd.notna(val):
                    r[dst] = int(val) if dst in _INT_COLS else float(val)
            rows.append(r)

        out_df = pd.DataFrame(rows)
        log.info("  %s: upserting %d indicator rows...", ticker, len(out_df))

        if not dry_run:
            upsert_dataframe(out_df, 'market_data_daily', ['ticker', 'date'])
            log.info("  ✓ %s done", ticker)
        else:
            log.info("  [DRY RUN] would upsert %d rows for %s", len(out_df), ticker)

    log.info("Daily indicators backfill complete.")


# ── Market data intraday ──────────────────────────────────────────────────────

def migrate_market_data_intraday(data_dir: Path, dry_run: bool):
    from gcp.database import bulk_insert_dataframe, execute_sql

    log.info("Migrating market_data_intraday (1-min combined files)...")

    for ticker_lower in TICKERS:
        combined = data_dir / ticker_lower / 'intraday' / f'{ticker_lower}_av_1min_combined.parquet'
        if not combined.exists():
            log.info("  %s: no combined parquet, skipping", ticker_lower.upper())
            continue

        log.info("  Loading %s...", combined)
        try:
            df = pd.read_parquet(combined)
            df = _normalize_ohlcv(df)

            # Normalize timestamp
            if isinstance(df.index, pd.DatetimeIndex):
                df['ts'] = df.index
                if df['ts'].dt.tz is None:
                    df['ts'] = df['ts'].dt.tz_localize('America/New_York').dt.tz_convert('UTC')
            elif 'timestamp' in df.columns:
                df['ts'] = pd.to_datetime(df['timestamp'], utc=True)

            df['ticker'] = ticker_lower.upper()
            df['interval'] = '1min'
            df['data_source'] = 'alphavantage'

            keep = ['ticker', 'interval', 'ts', 'open', 'high', 'low', 'close', 'volume', 'data_source']
            df = df[[c for c in keep if c in df.columns]]
            df = df.drop_duplicates(subset=['ticker', 'interval', 'ts'])

            log.info("  %s: %d rows", ticker_lower.upper(), len(df))

            if not dry_run:
                # Truncate existing rows for this ticker/interval before bulk insert
                execute_sql(
                    "DELETE FROM market_data_intraday WHERE ticker = :t AND interval = :i",
                    {'t': ticker_lower.upper(), 'i': '1min'}
                )
                bulk_insert_dataframe(df, 'market_data_intraday', chunksize=5000)
                log.info("  ✓ %s intraday loaded", ticker_lower.upper())
            else:
                log.info("  [DRY RUN] would load %d rows for %s", len(df), ticker_lower.upper())

        except Exception as e:
            log.warning("  ✗ %s: %s", ticker_lower.upper(), e)


# ── AV historical options ─────────────────────────────────────────────────────

AV_OPTIONS_TICKERS = ['spy', 'iwm', 'qqq', 'spx']


def _normalize_av_options(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Normalize an AV options parquet (daily file or combined) to etf_options_snapshots schema.

    AV parquet columns: contractID, symbol, expiration, strike, type, last, mark,
    bid, bid_size, ask, ask_size, volume, open_interest, date, implied_volatility,
    delta, gamma, theta, vega, rho, fetch_timestamp, snapshot_date
    """
    out = df.copy()

    # snapshot_ts: midnight UTC of the snapshot date + 23:00 (EOD marker, distinct from
    # yahooquery intraday snapshots which are in 14:30–21:00 UTC range)
    date_col = 'date' if 'date' in out.columns else 'snapshot_date'
    dates = pd.to_datetime(out[date_col]).dt.date
    out['snapshot_ts'] = pd.to_datetime(
        [f"{d}T23:00:00Z" for d in dates], utc=True
    )
    out['snapshot_date'] = dates
    out['market_session'] = 'EOD'
    out['ticker'] = ticker.upper()
    out['data_source'] = 'alphavantage'

    # option_type: 'call' → 'calls', 'put' → 'puts'
    out['option_type'] = out['type'].str.lower().map({'call': 'calls', 'put': 'puts'})

    out = out.rename(columns={'last': 'last_price', 'contractID': 'contract_symbol'})

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


def _get_av_existing_dates(ticker: str) -> set:
    """Return set of snapshot_dates already in Cloud SQL for this ticker + alphavantage."""
    from gcp.database import query_to_dataframe
    sql = (
        "SELECT DISTINCT snapshot_date FROM etf_options_snapshots "
        "WHERE ticker = :ticker AND data_source = 'alphavantage'"
    )
    df = query_to_dataframe(sql, {'ticker': ticker.upper()})
    if df.empty:
        return set()
    return set(pd.to_datetime(df['snapshot_date']).dt.date)


def migrate_av_options(data_dir: Path, dry_run: bool):
    """
    Backfill etf_options_snapshots with AV HISTORICAL_OPTIONS data.

    Uses combined parquets where available (SPY/QQQ have full 2015-2026 coverage);
    falls back to individual daily files for IWM (combined is incomplete).

    Checkpoint/resume: skips dates already present in Cloud SQL per ticker,
    so it can be safely re-run after a crash without duplicating data.

    Runs as: python gcp/migrate_to_gcp.py --table av_options --skip-gcs
    Expected volume: ~45M rows total (SPY 20M + QQQ 14M + IWM ~10M).
    Run in background with nohup for large datasets.
    """
    from gcp.database import bulk_insert_dataframe

    CHUNKSIZE = 200_000  # rows per DB batch

    for ticker_lower in AV_OPTIONS_TICKERS:
        ticker = ticker_lower.upper()
        options_dir = data_dir / ticker_lower / 'options'

        # Check what's already in Cloud SQL for this ticker
        existing_dates = _get_av_existing_dates(ticker)
        if existing_dates:
            log.info("  %s: %d dates already in Cloud SQL (checkpoint resume)",
                     ticker, len(existing_dates))

        # Prefer combined parquet if it covers 2015+ history
        combined = options_dir / f'{ticker_lower}_av_options_combined.parquet'
        if combined.exists():
            try:
                sample = pd.read_parquet(combined, columns=['date'])
                min_date = pd.to_datetime(sample['date']).min()
                use_combined = min_date.year <= 2015
            except Exception:
                use_combined = False
        else:
            use_combined = False

        if use_combined:
            log.info("  %s: streaming combined parquet (%s) in row-group chunks...",
                     ticker, combined.name)
            try:
                import pyarrow.parquet as pq
                pf = pq.ParquetFile(combined)
                inserted = 0
                skipped = 0
                rg_count = pf.metadata.num_row_groups

                for rg_idx in range(rg_count):
                    df = pf.read_row_group(rg_idx).to_pandas()
                    df = _normalize_av_options(df, ticker)

                    # Filter out dates already in Cloud SQL
                    if existing_dates:
                        before = len(df)
                        df = df[~df['snapshot_date'].isin(existing_dates)]
                        skipped += before - len(df)

                    if df.empty:
                        continue

                    if not dry_run:
                        # Insert in sub-chunks if row group is very large
                        for i in range(0, len(df), CHUNKSIZE):
                            chunk = df.iloc[i:i + CHUNKSIZE]
                            bulk_insert_dataframe(chunk, 'etf_options_snapshots')
                            inserted += len(chunk)
                    else:
                        inserted += len(df)

                    if (rg_idx + 1) % 5 == 0 or rg_idx == rg_count - 1:
                        log.info("  %s: row group %d/%d — %d inserted, %d skipped",
                                 ticker, rg_idx + 1, rg_count, inserted, skipped)

                    del df  # free memory between row groups

                log.info("  %s: %d rows inserted (%d skipped as existing)",
                         ticker, inserted, skipped)

            except Exception as e:
                log.error("  %s combined failed: %s", ticker, e, exc_info=True)
            continue

        # Fall back to individual daily files
        daily_files = sorted(options_dir.glob(f'{ticker_lower}_av_options_2*.parquet'))
        if not daily_files:
            log.info("  %s: no AV options files found, skipping", ticker)
            continue

        # Filter out daily files whose date is already in Cloud SQL
        if existing_dates:
            import re
            filtered = []
            for f in daily_files:
                m = re.search(r'(\d{8})\.parquet$', f.name)
                if m:
                    file_date = pd.to_datetime(m.group(1), format='%Y%m%d').date()
                    if file_date not in existing_dates:
                        filtered.append(f)
                else:
                    filtered.append(f)
            log.info("  %s: %d daily files to process (%d skipped as already in DB)",
                     ticker, len(filtered), len(daily_files) - len(filtered))
            daily_files = filtered

        if not daily_files:
            log.info("  %s: all daily files already migrated, skipping", ticker)
            continue

        log.info("  %s: reading %d daily files...", ticker, len(daily_files))
        total = 0
        batch_dfs = []
        batch_rows = 0

        for f in daily_files:
            try:
                df = pd.read_parquet(f)
                df = _normalize_av_options(df, ticker)
                batch_dfs.append(df)
                batch_rows += len(df)

                if batch_rows >= CHUNKSIZE:
                    batch = pd.concat(batch_dfs, ignore_index=True)
                    if not dry_run:
                        bulk_insert_dataframe(batch, 'etf_options_snapshots')
                    total += len(batch)
                    log.info("  %s: %d rows inserted so far", ticker, total)
                    batch_dfs = []
                    batch_rows = 0

            except Exception as e:
                log.warning("  %s: %s", f.name, e)

        if batch_dfs:
            batch = pd.concat(batch_dfs, ignore_index=True)
            if not dry_run:
                bulk_insert_dataframe(batch, 'etf_options_snapshots')
            total += len(batch)

        log.info("  %s: %d total rows inserted", ticker, total)

    log.info("AV options migration complete.")


# ── ETF options ───────────────────────────────────────────────────────────────

def migrate_etf_options(data_dir: Path, dry_run: bool):
    from gcp.database import upsert_dataframe

    options_dir = data_dir / 'options' / 'etfs'
    if not options_dir.exists():
        log.info("No ETF options data found, skipping")
        return

    log.info("Migrating etf_options_snapshots...")
    files = sorted(options_dir.glob('*.parquet'))
    # only process per-ticker files (not combined etf_options_*.parquet)
    files = [f for f in files if not f.stem.startswith('etf_options_')]

    total = 0
    for f in files:
        try:
            df = pd.read_parquet(f)
            df = _normalize_options_df(df, source='etf')
            if df.empty:
                continue
            if not dry_run:
                upsert_dataframe(
                    df, 'etf_options_snapshots',
                    ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike'],
                )
            else:
                log.info("  [DRY RUN] %s: %d rows", f.name, len(df))
            total += len(df)
        except Exception as e:
            log.warning("  ✗ %s: %s", f.name, e)

    log.info("etf_options_snapshots: %d rows", total)


# ── Earnings options ──────────────────────────────────────────────────────────

def migrate_earnings_options(data_dir: Path, dry_run: bool):
    from gcp.database import upsert_dataframe

    options_dir = data_dir / 'options' / 'earnings'
    if not options_dir.exists():
        log.info("No earnings options data found, skipping")
        return

    log.info("Migrating earnings_options_snapshots...")
    files = sorted(options_dir.glob('earnings_options_????????.parquet'))

    total = 0
    for f in files:
        try:
            df = pd.read_parquet(f)
            df = _normalize_options_df(df, source='earnings')
            if df.empty:
                continue
            if not dry_run:
                upsert_dataframe(
                    df, 'earnings_options_snapshots',
                    ['symbol', 'snapshot_ts', 'option_type', 'expiration', 'strike'],
                )
            else:
                log.info("  [DRY RUN] %s: %d rows", f.name, len(df))
            total += len(df)
        except Exception as e:
            log.warning("  ✗ %s: %s", f.name, e)

    log.info("earnings_options_snapshots: %d rows", total)


def _normalize_options_df(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Normalize an options DataFrame to match the Cloud SQL schema."""
    df = df.copy()

    rename = {
        'contractSymbol': 'contract_symbol',
        'optionType': 'option_type',
        'lastPrice': 'last_price',
        'percentChange': 'percent_change',
        'openInterest': 'open_interest',
        'impliedVolatility': 'implied_volatility',
        'inTheMoney': 'in_the_money',
        'snapshot_datetime': 'snapshot_ts',
        'lastTradeDate': 'last_trade_date',
        'contractSize': 'contract_size',
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})

    # Ticker column
    if source == 'etf' and 'ticker' not in df.columns and 'symbol' in df.columns:
        df['ticker'] = df['symbol']
    elif source == 'earnings' and 'symbol' not in df.columns and 'ticker' in df.columns:
        df['symbol'] = df['ticker']

    # Ensure snapshot_ts is a proper timestamp
    if 'snapshot_ts' in df.columns:
        df['snapshot_ts'] = pd.to_datetime(df['snapshot_ts'], utc=True, errors='coerce')

    if 'snapshot_date' not in df.columns and 'snapshot_ts' in df.columns:
        df['snapshot_date'] = df['snapshot_ts'].dt.date

    if 'expiration' in df.columns:
        df['expiration'] = pd.to_datetime(df['expiration'], errors='coerce').dt.date

    return df.dropna(subset=['snapshot_ts'])


# ── AlphaVantage daily backfill ───────────────────────────────────────────────

AV_BASE_URL = 'https://www.alphavantage.co/query'
# AV symbols for TIME_SERIES_DAILY_ADJUSTED (index symbol differs from yfinance)
AV_DAILY_SYMBOLS = {
    'spy': 'SPY',
    'iwm': 'IWM',
    'qqq': 'QQQ',
    'spx': 'SPX',
}


def migrate_market_data_daily_av(data_dir: Path, dry_run: bool):
    """
    Backfill market_data_daily with 20+ years of AlphaVantage TIME_SERIES_DAILY_ADJUSTED data.

    - Uses outputsize=full to get the complete history per ticker (4 API calls total).
    - Upserts into market_data_daily, so existing rows are updated with adjusted_close.
    - Requires ALPHA_VANTAGE_API_KEY environment variable.
    - Rate limit: 150 req/min; waits 1s between calls (4 calls total — well within limit).
    """
    from gcp.database import upsert_dataframe

    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
    if not api_key:
        log.error("ALPHA_VANTAGE_API_KEY not set — cannot run AV daily backfill")
        return

    log.info("Backfilling market_data_daily from AlphaVantage TIME_SERIES_DAILY_ADJUSTED...")
    log.info("  outputsize=full → 20+ years per ticker (4 calls, 1s apart).")

    total = 0
    for i, (ticker_lower, av_symbol) in enumerate(AV_DAILY_SYMBOLS.items()):
        if i > 0:
            time.sleep(1)  # 150 RPM plan; 1s gap is sufficient for 4 calls

        log.info("  Fetching %s (AV symbol: %s)...", ticker_lower.upper(), av_symbol)
        params = {
            'function':   'TIME_SERIES_DAILY_ADJUSTED',
            'symbol':     av_symbol,
            'outputsize': 'full',
            'datatype':   'json',
            'apikey':     api_key,
        }
        try:
            resp = requests.get(AV_BASE_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            if 'Error Message' in data:
                log.warning("  AV error for %s: %s", av_symbol, data['Error Message'])
                continue
            if 'Information' in data or 'Note' in data:
                log.warning("  AV rate limit hit for %s — try again later", av_symbol)
                continue

            ts = data.get('Time Series (Daily)', {})
            if not ts:
                log.warning("  No data returned for %s", av_symbol)
                continue

            rows = []
            for date_str, v in ts.items():
                rows.append({
                    'ticker':         ticker_lower.upper(),
                    'date':           date_str,
                    'open':           float(v['1. open']),
                    'high':           float(v['2. high']),
                    'low':            float(v['3. low']),
                    'close':          float(v['4. close']),
                    'adjusted_close': float(v['5. adjusted close']),
                    'volume':         int(v['6. volume']),
                    'data_source':    'alphavantage_daily',
                })

            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date']).dt.date
            df = df.sort_values('date').reset_index(drop=True)

            log.info("  %s: %d rows (%s → %s)",
                     ticker_lower.upper(), len(df),
                     df['date'].min(), df['date'].max())

            if not dry_run:
                upsert_dataframe(df, 'market_data_daily', ['ticker', 'date'])
                log.info("  ✓ %s upserted", ticker_lower.upper())
            else:
                log.info("  [DRY RUN] would upsert %d rows for %s", len(df), ticker_lower.upper())

            total += len(df)

        except Exception as e:
            log.warning("  ✗ %s failed: %s", ticker_lower.upper(), e)

    log.info("market_data_daily_av backfill: %d total rows processed", total)


# ── Trades ────────────────────────────────────────────────────────────────────

def migrate_trades(data_dir: Path, dry_run: bool):
    from gcp.database import upsert_dataframe

    trades_dir = data_dir / 'trades'
    if not trades_dir.exists():
        log.info("No trades data found, skipping")
        return

    log.info("Migrating trades...")
    files = sorted(trades_dir.glob('*.parquet'))
    total = 0

    for f in files:
        try:
            df = pd.read_parquet(f)
            if 'trade_date' not in df.columns:
                df['trade_date'] = f.stem   # filename is YYYY-MM-DD.parquet
            if 'entry_time' in df.columns:
                df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True, errors='coerce')
            if 'exit_time' in df.columns:
                df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True, errors='coerce')
            if not dry_run:
                upsert_dataframe(df, 'trades', ['ticker', 'entry_time'])
            total += len(df)
        except Exception as e:
            log.warning("  ✗ %s: %s", f.name, e)

    log.info("trades: %d rows", total)


# ── Main ──────────────────────────────────────────────────────────────────────

TABLE_FUNCS = {
    'gcs_raw':                    upload_raw_parquets,
    'market_data_daily_av':       migrate_market_data_daily_av,    # AV 20yr OHLCV backfill
    'daily_indicators':           backfill_daily_indicators,        # compute indicators on existing rows
    'market_data_intraday':       migrate_market_data_intraday,
    'etf_options_snapshots':      migrate_etf_options,              # Yahoo intraday snapshots
    'av_options':                 migrate_av_options,               # AV EOD historical options (data_source='alphavantage')
    'earnings_options_snapshots': migrate_earnings_options,
    'trades':                     migrate_trades,
}


def main():
    parser = argparse.ArgumentParser(description='Migrate local Parquet data to GCS + Cloud SQL')
    parser.add_argument('--data-dir', default=str(DEFAULT_DATA_DIR),
                        help='Path to local data/ directory')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would be done without writing anything')
    parser.add_argument('--skip-gcs', action='store_true',
                        help='Skip raw Parquet upload to GCS')
    parser.add_argument('--skip-sql', action='store_true',
                        help='Skip Cloud SQL inserts')
    parser.add_argument('--table', choices=sorted(TABLE_FUNCS.keys()),
                        help='Migrate only one specific table/task')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    bucket = os.environ.get('GCS_BUCKET', 'adept-mountain-474619-d4-trading-data')
    dry = args.dry_run

    if dry:
        log.info("=== DRY RUN MODE — no data will be written ===")

    start = datetime.now()

    if args.table:
        fn = TABLE_FUNCS[args.table]
        if args.table == 'gcs_raw':
            fn(data_dir, bucket, dry)
        else:
            fn(data_dir, dry)
    else:
        if not args.skip_gcs:
            upload_raw_parquets(data_dir, bucket, dry)

        if not args.skip_sql:
            migrate_market_data_intraday(data_dir, dry)
            migrate_etf_options(data_dir, dry)
            migrate_earnings_options(data_dir, dry)
            migrate_trades(data_dir, dry)

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Migration complete in %.1f seconds", elapsed)


if __name__ == '__main__':
    main()
