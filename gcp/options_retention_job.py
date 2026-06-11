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
- The work is driven **per ticker**. ``idx_etf_options_realtime`` is
  ``(ticker, snapshot_ts DESC) WHERE market_session='REALTIME'``; a predicate
  that pins ``ticker`` is an index seek, while a bare ``snapshot_ts < cutoff``
  (no ticker) makes the planner seq-scan the 51 GB heap — verified the hard way,
  it timed out at 900 s. Tickers come from a loose-index-scan (a handful of
  index seeks), and each delete batch pins one ticker.
- Deletes are **batched by ctid** so a day's ~2.6M-row purge never holds one
  long lock or bloats WAL in a single transaction. Each batch commits on its
  own; a crash leaves partial progress durable and a re-run converges
  (**idempotent**).
- A per-statement ``statement_timeout`` guard fails a pathological batch fast
  and visibly instead of silently eating the whole task-timeout.
- Per-batch counts are logged for **observability**. No up-front ``count(*)``:
  it is expensive at this table's scale and the first empty batch is the no-op
  signal, so a quiet day costs one index probe per ticker.
- ``RETENTION_DAYS`` overrides the window (default 30) but a **14-day floor**
  is enforced so a fat-fingered tiny window can't eat the calibration data.
- ``RETENTION_DRY_RUN=1`` logs the would-delete count per ticker and deletes
  nothing.

Capacity (steady state): ~2.6M eligible rows/day ÷ 50k batch = ~52 DELETE
round-trips ≈ 1-2 min wall-clock. task-timeout 900s gives >4x headroom; a
timeout mid-run is non-fatal (next run resumes).
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
_RETENTION_FLOOR_DAYS = 14        # never prune inside the calibration window
_STATEMENT_TIMEOUT = "300s"       # a healthy batch takes seconds; this is a guard

# Distinct REALTIME tickers via a loose-index-scan over idx_etf_options_realtime
# (a few index seeks — NOT a 36M-row DISTINCT scan).
_TICKERS_SQL = text(
    "WITH RECURSIVE tk AS ("
    "  SELECT min(ticker) AS ticker FROM etf_options_snapshots"
    "    WHERE market_session = 'REALTIME'"
    "  UNION ALL"
    "  SELECT (SELECT min(ticker) FROM etf_options_snapshots"
    "            WHERE market_session = 'REALTIME' AND ticker > tk.ticker)"
    "    FROM tk WHERE tk.ticker IS NOT NULL"
    ") SELECT ticker FROM tk WHERE ticker IS NOT NULL")

# Eligibility predicate — pins ticker (index seek) so it can never seq-scan.
_ELIGIBLE = ("ticker = :tkr AND market_session = 'REALTIME' "
             "AND snapshot_ts < now() - ((:days || ' days')::interval)")
_COUNT_SQL = text(f"SELECT count(*) FROM etf_options_snapshots WHERE {_ELIGIBLE}")
_DELETE_SQL = text(
    "DELETE FROM etf_options_snapshots WHERE ctid IN ("
    f"  SELECT ctid FROM etf_options_snapshots WHERE {_ELIGIBLE} LIMIT :batch)")
_SET_TIMEOUT_SQL = text(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT}'")


def _truthy(val: str) -> bool:
    return val.strip().lower() not in ("", "0", "false", "no")


def _realtime_tickers(engine) -> list[str]:
    with engine.connect() as conn:
        return [row[0] for row in conn.execute(_TICKERS_SQL).fetchall() if row[0]]


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
    tickers = _realtime_tickers(engine)
    log.info("retention: window=%dd tickers=%s dry_run=%s", days, tickers, dry_run)

    if dry_run:
        grand = 0
        for tkr in tickers:
            with engine.connect() as conn:
                n = conn.execute(_COUNT_SQL, {"tkr": tkr, "days": days}).scalar()
            grand += n
            log.info("retention: DRY RUN ticker=%s would_delete=%s", tkr, f"{n:,}")
        log.info("retention: DRY RUN window=%dd would_delete_total=%s (no deletes)",
                 days, f"{grand:,}")
        return 0

    total = 0
    for tkr in tickers:
        tkr_total = 0
        while True:
            with engine.begin() as conn:
                conn.execute(_SET_TIMEOUT_SQL)
                deleted = conn.execute(
                    _DELETE_SQL, {"tkr": tkr, "days": days, "batch": _BATCH_ROWS}
                ).rowcount
            if not deleted:
                break
            tkr_total += deleted
            total += deleted
            log.info("retention: ticker=%s deleted batch=%d ticker_total=%d "
                     "grand_total=%d", tkr, deleted, tkr_total, total)

    log.info("retention: DONE deleted_total=%d window=%dd tickers=%d (EOD untouched)",
             total, days, len(tickers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
