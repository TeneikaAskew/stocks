#!/usr/bin/env python3
"""Non-transactional DB maintenance (VACUUM / ANALYZE / REINDEX).

The standard query path (`gcp/queries/run_query.py`, dispatched by
`scripts/db_query_cr.sh`) wraps every statement in a transaction — so VACUUM,
which Postgres forbids inside a transaction block, cannot run there. This module
opens an AUTOCOMMIT connection and runs the maintenance command directly.

Why this exists: `etf_options_snapshots` grew to ~52 GB once the REALTIME
intraday session landed (1.19M rows/ticker/day). After bulk inserts of that
size, the visibility map and planner statistics go stale. A `VACUUM (ANALYZE)`
refreshes both — restoring index-only scans for the IV aggregates (delta / IV are
in the `idx_etf_options_eod_agg` covering index) and sane row estimates.

NOTE (verified 2026-06-12): VACUUM alone does NOT make the PCR aggregate
(SUM(volume)) fast on the raw table — `volume` is not in the covering index, so
the planner still seq-scans. Full raw-table PCR query-ability needs `volume` +
`open_interest` added to the covering index (a slow, write-locking rebuild best
done in a maintenance window). Research + frontend reads go through the
materialized `options_daily_features` table, so this is a low-priority follow-up.

Run via the research image (full gcp/ + Cloud SQL connector). Pick a long
task-timeout — VACUUM on a 52 GB table can take tens of minutes:

    gcloud run jobs execute magnitude-engine --region us-east1 --task-timeout 10800 \
      --args="^|^-m|gcp.db_maintenance|--vacuum-analyze|etf_options_snapshots" --wait

NOTE: plain VACUUM (ANALYZE) does NOT take an exclusive lock and does NOT shrink
the table on disk — it only reclaims dead tuples for reuse and refreshes stats.
It will NOT meaningfully shrink a table whose size is live REALTIME rows (which
this one mostly is). Use --vacuum-full ONLY with a maintenance window: it takes
ACCESS EXCLUSIVE (blocks all reads/writes) and needs ~2× the table size free.
"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from gcp.database import get_engine
from lib.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)

# Only allow maintenance on known tables — never interpolate arbitrary input
# into a non-parameterizable identifier position.
_ALLOWED_TABLES = {
    "etf_options_snapshots", "options_daily_features", "market_data_intraday",
    "market_data_daily", "signal_alerts", "earnings_options_snapshots",
}


def _run(engine, stmt: str) -> None:
    """Execute one maintenance statement on an AUTOCOMMIT connection."""
    log.info("running: %s", stmt)
    t0 = time.time()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(stmt))
    log.info("done in %.1fs: %s", time.time() - t0, stmt)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vacuum-analyze", metavar="TABLE",
                   help="VACUUM (ANALYZE) the table (no lock, refresh stats+VM)")
    p.add_argument("--analyze", metavar="TABLE",
                   help="ANALYZE only (refresh planner statistics)")
    p.add_argument("--vacuum-full", metavar="TABLE",
                   help="VACUUM FULL — ACCESS EXCLUSIVE lock + 2x disk; maintenance window only")
    p.add_argument("--reindex", metavar="TABLE",
                   help="REINDEX TABLE (rebuild bloated indexes)")
    args = p.parse_args()

    jobs: list[str] = []
    if args.vacuum_analyze:
        jobs.append(("vacuum_analyze", args.vacuum_analyze, f"VACUUM (ANALYZE) {args.vacuum_analyze}"))
    if args.analyze:
        jobs.append(("analyze", args.analyze, f"ANALYZE {args.analyze}"))
    if args.vacuum_full:
        jobs.append(("vacuum_full", args.vacuum_full, f"VACUUM (FULL, ANALYZE) {args.vacuum_full}"))
    if args.reindex:
        jobs.append(("reindex", args.reindex, f"REINDEX TABLE {args.reindex}"))
    if not jobs:
        p.error("specify at least one of --vacuum-analyze / --analyze / "
                "--vacuum-full / --reindex")

    for _, table, stmt in jobs:
        if table not in _ALLOWED_TABLES:
            raise SystemExit(f"refusing maintenance on unknown table {table!r}; "
                             f"allowed: {sorted(_ALLOWED_TABLES)}")

    engine = get_engine()
    for _, _, stmt in jobs:
        _run(engine, stmt)
    log.info("maintenance complete (%d statement(s))", len(jobs))


if __name__ == "__main__":
    main()
