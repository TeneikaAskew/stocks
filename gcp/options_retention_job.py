"""Cloud Run Job: prune stale REALTIME rows from etf_options_snapshots.

Retention policy (decided 2026-06-11)
-------------------------------------
- ``market_session='REALTIME'`` intraday option snapshots: keep a ROLLING
  30-day window. These land at ~2.6M rows/day and would otherwise grow the
  table unbounded (~0.5 GB/day; the table is already 51 GB). Every consumer of
  REALTIME data only needs it recently — the premarket-brief gamma freshness
  probe (2 trading days), ``idx_etf_options_realtime`` ("last 15 days"), and the
  ~14-day intraday-theta calibration window — so 30 days preserves every use
  with margin while bounding REALTIME at ~30 days (~78M rows). NB: DELETE frees
  space for REUSE by new inserts (it caps unbounded growth — the table goes
  ~flat at steady state) but does NOT return the existing 51 GB to disk; a
  one-time VACUUM FULL / pg_repack after the first large prune reclaims that.
- ``market_session='EOD'`` (and anything else): NEVER deleted. The EOD-only
  models (gamma_levels_eod, options-derived direction, 0DTE theta calibration)
  depend on full history.

Implementation notes (CLAUDE.md Rule 0)
---------------------------------------
The delete is driven **per ticker, in fixed timestamp windows** — NOT by a
``ctid IN (… LIMIT n)`` batch. That matters for the planner:
``idx_etf_options_realtime`` is ``(ticker, snapshot_ts DESC) WHERE
market_session='REALTIME'``. A predicate that pins ``ticker`` and bounds
``snapshot_ts`` to ``[lo, hi)`` is a clean index range scan; a bare
``snapshot_ts < cutoff`` (no ticker) seq-scans the 51 GB heap, and a
``SELECT ctid … LIMIT n`` defeats the index plan too — both were verified the
hard way at the 300-900 s timeout. So:

- Per ticker we read ``min(snapshot_ts)`` (one index seek) and walk
  ``[oldest, cutoff)`` in ``_WINDOW`` chunks, deleting each window in its own
  committed transaction. Each delete is an index range scan bounded to one
  ticker-window (~170k rows/hour), so progress is **durable** window-by-window
  and a re-run **converges** (idempotent — ``min`` advances as rows are freed).
- A ticker whose oldest row is already inside the window is skipped after a
  single ``min`` probe, so a quiet day costs ~one index seek per ticker.
- A per-statement ``statement_timeout`` guard fails a pathological window fast
  and visibly instead of silently eating the task-timeout.
- ``RETENTION_DAYS`` overrides the window (default 30); a **14-day floor** is
  enforced so a fat-fingered tiny window can't eat the calibration data.
- ``RETENTION_DRY_RUN=1`` logs the per-ticker eligible count and deletes nothing.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import timedelta

from sqlalchemy import text

from gcp.database import get_engine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_RETENTION_FLOOR_DAYS = 14        # never prune inside the calibration window
_WINDOW = timedelta(hours=1)      # delete one ticker-hour per transaction
_STATEMENT_TIMEOUT = "300s"       # a healthy window takes seconds; this is a guard

_TICKERS_SQL = text(
    "WITH RECURSIVE tk AS ("
    "  SELECT min(ticker) AS ticker FROM etf_options_snapshots"
    "    WHERE market_session = 'REALTIME'"
    "  UNION ALL"
    "  SELECT (SELECT min(ticker) FROM etf_options_snapshots"
    "            WHERE market_session = 'REALTIME' AND ticker > tk.ticker)"
    "    FROM tk WHERE tk.ticker IS NOT NULL"
    ") SELECT ticker FROM tk WHERE ticker IS NOT NULL")
_CUTOFF_SQL = text("SELECT now() - ((:days || ' days')::interval)")
_OLDEST_SQL = text("SELECT min(snapshot_ts) FROM etf_options_snapshots "
                   "WHERE ticker = :tkr AND market_session = 'REALTIME'")
_COUNT_SQL = text("SELECT count(*) FROM etf_options_snapshots "
                  "WHERE ticker = :tkr AND market_session = 'REALTIME' "
                  "AND snapshot_ts < :cutoff")
_DELETE_WINDOW_SQL = text(
    "DELETE FROM etf_options_snapshots "
    "WHERE ticker = :tkr AND market_session = 'REALTIME' "
    "AND snapshot_ts >= :lo AND snapshot_ts < :hi")
_SET_TIMEOUT_SQL = text(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT}'")


def _truthy(val: str) -> bool:
    return val.strip().lower() not in ("", "0", "false", "no")


def _prune_ticker(engine, tkr: str, cutoff) -> int:
    """Delete REALTIME rows for one ticker older than ``cutoff``, window by
    window. Returns rows deleted."""
    with engine.connect() as conn:
        oldest = conn.execute(_OLDEST_SQL, {"tkr": tkr}).scalar()
    if oldest is None or oldest >= cutoff:
        log.info("retention: ticker=%s up-to-date (oldest=%s cutoff=%s)",
                 tkr, oldest, cutoff)
        return 0

    deleted_total = 0
    lo = oldest
    while lo < cutoff:
        hi = min(lo + _WINDOW, cutoff)
        with engine.begin() as conn:
            conn.execute(_SET_TIMEOUT_SQL)
            deleted = conn.execute(
                _DELETE_WINDOW_SQL, {"tkr": tkr, "lo": lo, "hi": hi}).rowcount
        if deleted:
            deleted_total += deleted
            log.info("retention: ticker=%s window=[%s,%s) deleted=%d",
                     tkr, lo, hi, deleted)
        lo = hi
    log.info("retention: ticker=%s done deleted=%d", tkr, deleted_total)
    return deleted_total


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
        cutoff = conn.execute(_CUTOFF_SQL, {"days": days}).scalar()
        tickers = [row[0] for row in conn.execute(_TICKERS_SQL).fetchall() if row[0]]
    log.info("retention: window=%dd cutoff=%s tickers=%s dry_run=%s",
             days, cutoff, tickers, dry_run)

    if dry_run:
        grand = 0
        for tkr in tickers:
            with engine.connect() as conn:
                n = conn.execute(_COUNT_SQL, {"tkr": tkr, "cutoff": cutoff}).scalar()
            grand += n
            log.info("retention: DRY RUN ticker=%s would_delete=%s", tkr, f"{n:,}")
        log.info("retention: DRY RUN window=%dd would_delete_total=%s (no deletes)",
                 days, f"{grand:,}")
        return 0

    total = sum(_prune_ticker(engine, tkr, cutoff) for tkr in tickers)
    log.info("retention: DONE deleted_total=%d window=%dd tickers=%d (EOD untouched)",
             total, days, len(tickers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
