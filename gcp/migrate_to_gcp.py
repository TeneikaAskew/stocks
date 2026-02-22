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

    # Only one table
    python gcp/migrate_to_gcp.py --table market_data_daily

    # Custom data directory
    python gcp/migrate_to_gcp.py --data-dir /path/to/data

Environment variables:
    CLOUD_SQL_CONNECTION_NAME, DB_USER, DB_PASS, DB_NAME  (required for --skip-sql=False)
    GCS_BUCKET   e.g. adept-mountain-474619-d4-trading-data
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-7s  %(message)s',
    datefmt='%H:%M:%S',
)
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

DAILY_INDICATOR_MAP = {
    'ma_5': 'ma_5', 'ma_10': 'ma_10', 'ma_20': 'ma_20', 'ma_50': 'ma_50',
    'ma_390': 'ma_390', 'ema_9': 'ema_9', 'ema_21': 'ema_21', 'ema_50': 'ema_50',
    'rsi_14': 'rsi_14', 'rsi_9': 'rsi_9', 'rsi_30': 'rsi_30',
    'stoch_rsi_k': 'stoch_rsi_k', 'stoch_rsi_d': 'stoch_rsi_d',
    'atr_14': 'atr_14', 'atr_20': 'atr_20', 'obv': 'obv',
    'rvol': 'rvol', 'rvol_10': 'rvol_10',
    'volume_ma_10': 'volume_ma_10', 'volume_ma_20': 'volume_ma_20',
    'volume_usd': 'volume_usd', 'return': 'return',
    'volatility_30min': 'volatility_30min', 'volatility_day': 'volatility_day',
    'volatility_5d': 'volatility_5d', 'volatility_20d': 'volatility_20d',
    'intraday_return': 'intraday_return',
    'high_low_spread': 'high_low_spread', 'high_low_spread_pct': 'high_low_spread_pct',
    'Consecutive_Up': 'consecutive_up', 'Consecutive_Down': 'consecutive_down',
    'VWAP': 'vwap', 'Price_vs_VWAP': 'price_vs_vwap',
}


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to lowercase SQL-friendly names."""
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)
    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
    return df


# ── Market data daily ─────────────────────────────────────────────────────────

def migrate_market_data_daily(data_dir: Path, dry_run: bool):
    from gcp.database import upsert_dataframe

    log.info("Migrating market_data_daily...")
    total = 0

    for ticker_lower in TICKERS:
        ticker_dir = data_dir / ticker_lower
        if not ticker_dir.exists():
            continue

        files = sorted(ticker_dir.glob(f'{ticker_lower}_*.parquet'))
        # skip intraday / options / minute files
        files = [f for f in files if f.parent == ticker_dir]

        for f in files:
            try:
                df = pd.read_parquet(f)
                df = _normalize_ohlcv(df)

                # Ensure date column
                if isinstance(df.index, pd.DatetimeIndex):
                    df['date'] = df.index.date
                elif 'date' not in df.columns and 'Time' in df.columns:
                    df['date'] = pd.to_datetime(df['Time']).dt.date

                df['ticker'] = ticker_lower.upper()

                # Rename indicator columns
                df = df.rename(columns={
                    k: v for k, v in DAILY_INDICATOR_MAP.items() if k in df.columns
                })

                # Keep only schema columns
                keep = [c for c in df.columns if c in _daily_schema_cols()]
                df = df[keep].drop_duplicates(subset=['ticker', 'date'])

                if dry_run:
                    log.info("  [DRY RUN] %s: %d rows", f.name, len(df))
                else:
                    upsert_dataframe(df, 'market_data_daily', ['ticker', 'date'])
                    log.info("  ✓ %s: %d rows", f.name, len(df))

                total += len(df)
            except Exception as e:
                log.warning("  ✗ %s: %s", f.name, e)

    log.info("market_data_daily: %d total rows processed", total)


def _daily_schema_cols():
    return {
        'ticker', 'date', 'open', 'high', 'low', 'close', 'volume',
        'ma_5', 'ma_10', 'ma_20', 'ma_50', 'ma_390',
        'ema_9', 'ema_21', 'ema_50',
        'rsi_14', 'rsi_9', 'rsi_30', 'stoch_rsi_k', 'stoch_rsi_d',
        'atr_14', 'atr_20', 'obv', 'rvol', 'rvol_10',
        'volume_ma_10', 'volume_ma_20', 'volume_usd',
        'return', 'volatility_30min', 'volatility_day', 'volatility_5d', 'volatility_20d',
        'intraday_return', 'high_low_spread', 'high_low_spread_pct',
        'consecutive_up', 'consecutive_down',
        'vwap', 'price_vs_vwap', 'data_source',
    }


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
                bulk_insert_dataframe(df, 'market_data_intraday', chunksize=10000)
                log.info("  ✓ %s intraday loaded", ticker_lower.upper())
            else:
                log.info("  [DRY RUN] would load %d rows for %s", len(df), ticker_lower.upper())

        except Exception as e:
            log.warning("  ✗ %s: %s", ticker_lower.upper(), e)


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
    'gcs_raw':                 upload_raw_parquets,
    'market_data_daily':       migrate_market_data_daily,
    'market_data_intraday':    migrate_market_data_intraday,
    'etf_options_snapshots':   migrate_etf_options,
    'earnings_options_snapshots': migrate_earnings_options,
    'trades':                  migrate_trades,
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
    parser.add_argument('--table', choices=list(TABLE_FUNCS.keys()),
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
            migrate_market_data_daily(data_dir, dry)
            migrate_market_data_intraday(data_dir, dry)
            migrate_etf_options(data_dir, dry)
            migrate_earnings_options(data_dir, dry)
            migrate_trades(data_dir, dry)

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Migration complete in %.1f seconds", elapsed)


if __name__ == '__main__':
    main()
