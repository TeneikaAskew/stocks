"""Cloud Run Job: prune stale REALTIME rows from etf_options_snapshots.

Retention policy (decided 2026-06-11)
-------------------------------------
- ``market_session='REALTIME'`` intraday option snapshots: keep a ROLLING
  30-day window. These land at ~2.6M rows/day and would otherwise grow the
  table unbounded (~0.5 GB/day; the table is already 51 GB). Every consumer of
  REALTIME data only needs it recently — the premarket-brief gamma freshness
  probe (2 trading days), ``idx_etf_options_realtime`` ("last 15 days"), and the
  ~14-day intraday-theta calibration window — so 30 days preserves every use
  with margin while capping the table at ~12 GB steady-state.
- ``market_session='EOD'`` (and anything else): NEVER deleted. The EOD-only
  models (gamma_levels_eod, options-derived direction, 0DTE theta calibration)
  depend on full history.

Implementation notes (CLAUDE.md Rule 0)
---------------------------------------
- Deletes are **batched by ctid** so a day's ~2.6M-row purge never holds one
  long lock or bloats WAL in a single transaction. Each batch commits on its
  own; a crash leaves partial progress durable and a re-run converges
  (**idempotent**).
- Per-batch counts are logged for **observability**.
- The eligibility predicate rides ``idx_etf_options_realtime`` (the partial
  index on REALTIME rows), so the daily no-op run (nothing older than 30 days
  yet, before ~2026-06-22) is sub-second.
- ``RETENTION_DAYS`` overrides the window (default 30) but a **14-day floor**
  is enforced so a fat-fingered tiny window can't eat the calibration data.
- ``RETENTION_DRY_RUN=1`` logs the would-delete count and deletes nothing.

Capacity (steady state): ~2.6M eligible rows/day ÷ 50k batch = ~52 DELETE
round-trips ≈ 1-2 min wall-clock. task-timeout 900s gives >4x headroom.
"""
from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import text

from gcp.database import get_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_BATCH_ROWS = 50_000
_RETENTION_FLOOR_DAYS = 14   # never prune inside the calibration/freshness window

# Eligibility predicate — shared by the count and the delete so they can never
# diverge. Rides idx_etf_options_realtime (WHERE market_session='REALTIME').
_ELIGIBLE = ("market_session = 'REALTIME' "
             "AND snapshot_ts < now() - ((:days || ' days')::interval)")

_COUNT_SQL = text(f"SELECT count(*) FROM etf_options_snapshots WHERE {_ELIGIBLE}")
_DELETE_SQL = text(
    "DELETE FROM etf_options_snapshots WHERE ctid IN ("
    f"  SELECT ctid FROM etf_options_snapshots WHERE {_ELIGIBLE} LIMIT :batch)")


def _truthy(val: str) -> bool:
    return val.strip().lower() not in ("", "0", "false", "no")


def main() -> int:
    days = int(os.environ.get("RETENTION_DAYS", "30"))
    dry_run = _truthy(os.environ.get("RETENTION_DRY_RUN", ""))

    if days < _RETENTION_FLOOR_DAYS:
        # Fail loud — a window under the calibration floor is a config error,
        # not something to silently apply (CLAUDE.md Rule 3.7).
        log.error("RETENTION_DAYS=%d is below the %d-day calibration floor — "
                  "refusing to prune", days, _RETENTION_FLOOR_DAYS)
        return 2

    engine = get_engine()

    with engine.connect() as conn:
        # count(*) always returns exactly one row, so .scalar() is a non-None int.
        eligible = conn.execute(_COUNT_SQL, {"days": days}).scalar()
    log.info("retention: window=%dd eligible_realtime_rows=%s dry_run=%s",
             days, f"{eligible:,}", dry_run)

    if dry_run or eligible == 0:
        log.info("retention: no deletions performed (dry_run=%s eligible=%d)",
                 dry_run, eligible)
        return 0

    total = 0
    while True:
        with engine.begin() as conn:
            deleted = conn.execute(_DELETE_SQL,
                                   {"days": days, "batch": _BATCH_ROWS}).rowcount
        if not deleted:
            break
        total += deleted
        log.info("retention: deleted batch=%d cumulative=%d/%d",
                 deleted, total, eligible)

    log.info("retention: DONE deleted_total=%d window=%dd (EOD untouched)",
             total, days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
