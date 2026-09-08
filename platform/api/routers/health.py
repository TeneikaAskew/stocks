"""
Health / freshness router.

GET /api/health/freshness → data pipeline status across Cloud SQL tables.

Wraps the `scripts.audit_data_freshness` module so the CLI and the Dashboard
widget share a single source of truth. Results are cached for 5 min because
the freshness queries touch Cloud SQL (cheap, but no point running them on
every Dashboard render).
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from lib.single_flight import SingleFlight
from api.schemas import (
    FreshnessResponse,
)

# Add project root so we can import the script module
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Make scripts/ importable as a package
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

log = logging.getLogger(__name__)
router = APIRouter()

# Silence the underlying gcp.database warnings — the audit module handles failures
logging.getLogger("gcp.database").setLevel(logging.ERROR + 1)

# 5-minute TTL cache — freshness doesn't change faster than this.
# Stdlib-only to avoid adding the cachetools dep just for one entry.
_CACHE_TTL = 300  # seconds
# ONE tuple, `(report, expires_at)`, replaced by a single name rebinding.
# Two separate globals were written in sequence, so a reader arriving between
# the two saw the NEW report against the OLD expiry: it judged a report that
# had just been produced as expired, declined the still-active flight, and
# returned that fresh report labelled `stale: true` with an age measured from
# the previous expiry. On the first fill the previous expiry is 0.0, which
# made `stale_age_seconds` roughly the process's entire monotonic uptime plus
# the TTL -- a number with no meaning at all, on the field an operator reads
# to decide how much to trust the report (Codex, PR #991).
#
# A tuple rebinding is atomic under the GIL and every reader takes ONE
# snapshot of it, so the two halves can no longer disagree. That is cheaper
# and harder to get wrong than a lock around three accesses, and this is the
# health surface: it should not be able to block on itself.
_cache: "tuple[dict, float] | None" = None


# Coalesces concurrent audits without parking a worker on a lock. See
# `lib/single_flight.py` for why blocking here would recreate the starvation
# this branch removes.
_AUDIT_FLIGHT = SingleFlight()
_AUDIT_KEY = "freshness"


def freshness_report_dict() -> dict:
    """The cached freshness report, shared by GET /api/health/freshness and
    the admin data-sources endpoint (routers/admin.py) so both surfaces read
    the SAME audit run and the Cloud SQL queries happen at most once per TTL.
    Raises HTTPException on audit failure — callers pass it through.

    Single-flighted, and **without blocking**. `audit_all()` issues many Cloud
    SQL queries and takes real time; with this route threadpooled, every
    overlapping request past a cold or expired cache used to start its own
    audit. The event loop had been the only thing serialising them.

    A lock was the first fix and it was wrong. Waiters would each hold a
    FastAPI worker for the whole audit, so a dashboard burst fills the pool
    and starves unrelated routes — `/api/health` and `/api/me` included, which
    is the instance-wide starvation this migration exists to remove. Doing
    that on the health surface itself is the worst place to do it.

    So the claimant audits and a decliner answers immediately with whatever is
    honest:

    * a **stale cached report**, labelled `stale: true` with the age, because
      a monitoring surface tolerates a slightly old answer far better than it
      tolerates a starved worker pool. The caller can see it is stale and
      decide;
    * **503** when there is nothing cached at all, which says "ask again in a
      moment" rather than fabricating a report or holding the connection.
    """
    now = time.monotonic()
    snapshot = _cache            # one read; see the comment on `_cache`
    if snapshot is not None and now < snapshot[1]:
        return snapshot[0]

    with _AUDIT_FLIGHT.claim(_AUDIT_KEY) as mine:
        if mine:
            # Re-check under the claim. The cache read above happened before
            # the claim was taken, so a contender descheduled between the two
            # can win the claim moments after the previous claimant finished
            # and populated the cache -- and would then run a second full
            # audit inside one TTL, which is the bound this function's
            # docstring promises. Claiming is not the same as being first.
            now = time.monotonic()
            snapshot = _cache
            if snapshot is not None and now < snapshot[1]:
                return snapshot[0]
            return _run_audit_and_cache(now)

        # Another request is auditing. Never wait for it.
        snapshot = _cache
        if snapshot is not None:
            report, expires_at = snapshot
            age_s = round(time.monotonic() - (expires_at - _CACHE_TTL))
            log.info("freshness audit in flight; serving a %ds-old report", age_s)
            return {**report, "stale": True, "stale_age_seconds": age_s}
        raise HTTPException(
            status_code=503,
            detail=("Freshness audit in progress and no cached report is "
                    "available yet. Retry shortly."),
        )


def _run_audit_and_cache(now: float) -> dict:
    """Run the freshness audit and store it. Caller must hold the claim."""
    global _cache
    try:
        # Import lazily so the module loads even if the audit script has issues
        import audit_data_freshness as audit_mod
        report = audit_mod.audit_all()
    except ModuleNotFoundError as exc:
        log.error("Failed to import audit_data_freshness: %s", exc)
        raise HTTPException(status_code=500, detail="Freshness audit module not available")
    except Exception as exc:
        log.error("Freshness audit failed: %s", exc)
        # Which failure it was decides the status. An unreachable Cloud SQL is
        # EXTERNAL (CLAUDE.md 3.7): explicit, renderable, retryable — a 503.
        # Anything else is a defect in the audit and must stay a loud 500,
        # because a 503 tells an operator to retry code that will never
        # succeed. table_exists() answering False for every error used to hide
        # the outage as a fabricated "table missing" (audit P2-#6, closed on
        # #1022); with it raising, this is where the two must be told apart.
        from lib.infra_errors import is_infrastructure_error  # noqa: PLC0415
        if is_infrastructure_error(exc):
            raise HTTPException(
                status_code=503,
                detail=f"Freshness audit unavailable: {exc}") from exc
        raise HTTPException(status_code=500, detail=f"Freshness audit failed: {exc}")

    response = report.to_dict()
    _cache = (response, now + _CACHE_TTL)   # one rebinding, see `_cache`
    return response


@router.get("/api/health/freshness", response_model=FreshnessResponse, response_model_exclude_unset=True)
def get_freshness():
    """Return the cached freshness report (see freshness_report_dict).

    Response shape:
    ```
    {
      "checked_at": "2026-04-14T03:30:00.000Z",
      "expected_market_close": "2026-04-13",
      "overall_status": "ok" | "warn" | "stale" | "unknown",
      "tables": [
        {
          "table": "market_data_daily",
          "ticker": "IWM",          # null if per_ticker=false
          "last_row_at": "2026-04-13",
          "expected_latest": "2026-04-13",
          "lag_hours": 7.5,
          "expected_max_hours": 30,
          "status": "ok",   # ok | warn | stale | unknown | skipped
          "row_count_recent": 1
        },
        ...
      ]
    }
    ```
    """
    return freshness_report_dict()
