#!/usr/bin/env python3
"""
Archive Yahoo Finance legacy data out of production Cloud SQL tables.

For each affected table, this script:
  1. Copies Yahoo rows into `archive_yahoo_<table>` in chunks of N rows
  2. Deletes those rows from the production table in matching chunks
  3. (Optionally) runs VACUUM ANALYZE afterwards

Yahoo rows are identified by:
    data_source IS NULL OR data_source IN ('yfinance', 'yahoo', 'yahooquery')

Safety rails:
  - --dry-run prints what would happen without touching the database
  - --confirm <table> required per table (no multi-table confirm via one flag)
  - Pre-flight check refuses to operate on etf_options_snapshots while the
    fetch-av-options-backfill Cloud Run Job is in RUNNING state
  - Resume-safe: the INSERT step uses NOT EXISTS so re-runs pick up where
    a prior run left off

Usage:
    # Dry run (all tables)
    python scripts/archive_yahoo_data.py --dry-run

    # Archive one table
    python scripts/archive_yahoo_data.py --confirm market_data_intraday

    # Archive + delete
    python scripts/archive_yahoo_data.py --confirm market_data_intraday --delete

    # After backfill completes
    python scripts/archive_yahoo_data.py --confirm etf_options_snapshots --delete
"""

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlalchemy
from gcp.database import get_engine

logger = logging.getLogger(__name__)

# ── Table configuration ─────────────────────────────────────────────────────

YAHOO_PREDICATE = (
    "(data_source IS NULL OR data_source IN ('yfinance', 'yahoo', 'yahooquery'))"
)

# Each entry: production table → archive table + dedup key columns
# The dedup key is used by NOT EXISTS to avoid copying rows already archived.
TABLES = {
    'market_data_daily': {
        'archive': 'archive_yahoo_market_data_daily',
        'dedup_key': ['ticker', 'date'],
        'partitioned': False,
    },
    'market_data_intraday': {
        'archive': 'archive_yahoo_market_data_intraday',
        'dedup_key': ['ticker', 'interval', 'ts'],
        'partitioned': True,
    },
    'etf_options_snapshots': {
        'archive': 'archive_yahoo_etf_options_snapshots',
        'dedup_key': ['ticker', 'snapshot_ts', 'option_type', 'expiration', 'strike'],
        'partitioned': False,
        'backfill_gate': 'fetch-av-options-backfill',
    },
    'earnings_options_snapshots': {
        'archive': 'archive_yahoo_earnings_options_snapshots',
        'dedup_key': ['symbol', 'snapshot_ts', 'option_type', 'expiration', 'strike'],
        'partitioned': False,
    },
}

CHUNK_SIZE_DEFAULT = 500_000


# ── Pre-flight checks ───────────────────────────────────────────────────────

def check_backfill_running(job_name: str) -> bool:
    """Return True if any execution of the given Cloud Run Job is still running."""
    try:
        result = subprocess.run(
            ['gcloud', 'run', 'jobs', 'executions', 'list',
             '--region=us-east1',
             f'--filter=metadata.labels."run.googleapis.com/job"={job_name}',
             '--format=value(status.runningCount)',
             '--limit=5'],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stdout.strip().splitlines():
            if line.strip() and int(line.strip()) > 0:
                return True
    except Exception as e:
        logger.warning("Couldn't check backfill status: %s — proceeding cautiously", e)
    return False


# ── Core ops ────────────────────────────────────────────────────────────────

def measure(conn, table: str) -> tuple[int, int]:
    """Return (yahoo_rows, total_rows) for a table."""
    r = conn.execute(sqlalchemy.text(
        f"SELECT COUNT(*) FILTER (WHERE {YAHOO_PREDICATE}) AS yahoo, "
        f"COUNT(*) AS total FROM {table}"
    )).fetchone()
    return int(r[0]), int(r[1])


def archive_chunk(conn, table: str, cfg: dict, chunk_size: int) -> int:
    """Copy one chunk of Yahoo rows from production → archive.

    Uses NOT EXISTS against the archive dedup key so the script is
    idempotent and resume-safe.  Returns the number of rows copied.
    """
    archive = cfg['archive']
    keys = cfg['dedup_key']
    key_match = ' AND '.join(f'a.{k} = t.{k}' for k in keys)

    sql = f"""
        INSERT INTO {archive}
        SELECT t.* FROM {table} t
        WHERE {YAHOO_PREDICATE.replace('data_source', 't.data_source')}
          AND NOT EXISTS (
              SELECT 1 FROM {archive} a
              WHERE {key_match}
          )
        LIMIT {chunk_size}
    """
    result = conn.execute(sqlalchemy.text(sql))
    conn.commit()
    return result.rowcount


def delete_chunk(conn, table: str, cfg: dict, chunk_size: int) -> int:
    """Delete one chunk of Yahoo rows from production.

    CRITICAL: Uses the primary key columns (not ctid) to identify rows.
    PostgreSQL's ctid is PARTITION-LOCAL — a DELETE that batches by ctid
    on a partitioned table will match rows ACROSS partitions that happen
    to share the same ctid value, causing silent data loss of unrelated
    rows.  Found the hard way on market_data_intraday:
    https://www.postgresql.org/docs/current/ddl-partitioning.html
    """
    keys = cfg['dedup_key']
    key_cols = ', '.join(keys)
    sql = f"""
        DELETE FROM {table}
        WHERE ({key_cols}) IN (
            SELECT {key_cols} FROM {table}
            WHERE {YAHOO_PREDICATE}
            LIMIT {chunk_size}
        )
    """
    result = conn.execute(sqlalchemy.text(sql))
    conn.commit()
    return result.rowcount


def process_table(engine, table: str, cfg: dict, args) -> dict:
    """Archive + optionally delete Yahoo rows for one table."""
    with engine.connect() as conn:
        yahoo_before, total_before = measure(conn, table)

    stats = {
        'table': table,
        'yahoo_before': yahoo_before,
        'total_before': total_before,
        'copied': 0,
        'deleted': 0,
    }

    if yahoo_before == 0:
        logger.info("[%s] 0 Yahoo rows — nothing to do", table)
        return stats

    logger.info("[%s] %s Yahoo rows out of %s total (%.1f%%)",
                table, f'{yahoo_before:,}', f'{total_before:,}',
                yahoo_before / total_before * 100 if total_before else 0)

    if args.dry_run:
        logger.info("[%s] DRY RUN — would copy %s rows to %s",
                    table, f'{yahoo_before:,}', cfg['archive'])
        return stats

    # Pre-flight: don't touch etf_options_snapshots if backfill is running
    gate = cfg.get('backfill_gate')
    if gate:
        if check_backfill_running(gate):
            logger.error(
                "[%s] ABORT — Cloud Run Job '%s' is still running. "
                "Wait for it to finish before archiving this table.",
                table, gate,
            )
            return stats

    # Step 1: Archive in chunks
    logger.info("[%s] copying → %s in chunks of %s",
                table, cfg['archive'], f'{args.chunk_size:,}')
    total_copied = 0
    chunk_num = 0
    while True:
        chunk_num += 1
        t0 = time.time()
        with engine.connect() as conn:
            n = archive_chunk(conn, table, cfg, args.chunk_size)
        total_copied += n
        elapsed = time.time() - t0
        logger.info("[%s]   chunk %d: +%s rows (%ds) — total %s",
                    table, chunk_num, f'{n:,}', int(elapsed),
                    f'{total_copied:,}')
        if n == 0:
            break
        if args.max_chunks and chunk_num >= args.max_chunks:
            logger.info("[%s] stopping at max_chunks=%d", table, args.max_chunks)
            break

    stats['copied'] = total_copied

    # Step 2: Verify count before deleting
    with engine.connect() as conn:
        archived_count = conn.execute(sqlalchemy.text(
            f"SELECT COUNT(*) FROM {cfg['archive']}"
        )).scalar()
    logger.info("[%s] archive now has %s rows", table, f'{archived_count:,}')

    # Step 3: Delete (only if requested)
    if not args.delete:
        logger.info("[%s] --delete not set; skipping DELETE step", table)
        return stats

    logger.info("[%s] deleting Yahoo rows from production", table)
    total_deleted = 0
    chunk_num = 0
    while True:
        chunk_num += 1
        t0 = time.time()
        with engine.connect() as conn:
            n = delete_chunk(conn, table, cfg, args.chunk_size)
        total_deleted += n
        elapsed = time.time() - t0
        logger.info("[%s]   delete chunk %d: -%s rows (%ds) — total %s",
                    table, chunk_num, f'{n:,}', int(elapsed),
                    f'{total_deleted:,}')
        if n == 0:
            break
        if args.max_chunks and chunk_num >= args.max_chunks:
            break

    stats['deleted'] = total_deleted

    # Final measurement
    with engine.connect() as conn:
        yahoo_after, total_after = measure(conn, table)
    logger.info("[%s] after: %s Yahoo left in prod (was %s), %s total (was %s)",
                table,
                f'{yahoo_after:,}', f'{yahoo_before:,}',
                f'{total_after:,}', f'{total_before:,}')
    stats['yahoo_after'] = yahoo_after
    stats['total_after'] = total_after

    return stats


# ── Entrypoint ──────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
    )

    parser = argparse.ArgumentParser(description='Archive Yahoo data out of prod tables')
    parser.add_argument(
        '--confirm', type=str, action='append', default=[],
        choices=list(TABLES.keys()) + ['all'],
        help='Table name to process. Use multiple times or "all" for everything.',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print counts and SQL without modifying the database.',
    )
    parser.add_argument(
        '--delete', action='store_true',
        help='After archiving, DELETE Yahoo rows from the production table. '
             'Without this flag, only the archive copy step runs.',
    )
    parser.add_argument(
        '--chunk-size', type=int, default=CHUNK_SIZE_DEFAULT,
        help=f'Rows per batch (default: {CHUNK_SIZE_DEFAULT:,})',
    )
    parser.add_argument(
        '--max-chunks', type=int, default=None,
        help='Stop after this many chunks (for testing, default: unlimited)',
    )
    args = parser.parse_args()

    # Resolve table list
    if 'all' in args.confirm:
        tables = list(TABLES.keys())
    elif args.confirm:
        tables = args.confirm
    elif args.dry_run:
        tables = list(TABLES.keys())
    else:
        parser.error('Pass --confirm <table> or --dry-run')

    logger.info("Yahoo archive — tables: %s | dry_run=%s | delete=%s | chunks=%s",
                tables, args.dry_run, args.delete, f'{args.chunk_size:,}')

    engine = get_engine()
    results = []
    for table in tables:
        cfg = TABLES[table]
        logger.info("")
        logger.info("=" * 70)
        logger.info("Processing: %s → %s", table, cfg['archive'])
        logger.info("=" * 70)
        stats = process_table(engine, table, cfg, args)
        results.append(stats)

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    logger.info(f'{"table":<32}{"yahoo":>12}{"copied":>12}{"deleted":>12}')
    for s in results:
        logger.info(
            f'{s["table"]:<32}{s["yahoo_before"]:>12,}'
            f'{s["copied"]:>12,}{s["deleted"]:>12,}'
        )


if __name__ == '__main__':
    main()
