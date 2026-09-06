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
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

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
_cache_value: dict | None = None
_cache_expires_at: float = 0.0


# Serialises the audit itself, not just the cache read/write: see the
# docstring below for why this one waits where the grid fetch declines.
_AUDIT_LOCK = threading.Lock()


def freshness_report_dict() -> dict:
    """The cached freshness report, shared by GET /api/health/freshness and
    the admin data-sources endpoint (routers/admin.py) so both surfaces read
    the SAME audit run and the Cloud SQL queries happen at most once per TTL.
    Raises HTTPException on audit failure — callers pass it through.

    Single-flighted. `audit_all()` issues many Cloud SQL queries, and with
    this route threadpooled every overlapping request past a cold or expired
    cache used to start its own audit: a dashboard burst launched one full
    audit per worker, defeating the once-per-TTL bound this docstring claims
    and contending for the shared 5+2 connection pool. The event loop had been
    the only thing serialising them.

    The lock is held across the audit, deliberately and unlike the on-demand
    grid fetch. There the waiter has something honest to return (a typed
    `unavailable` envelope) and parking a worker would be pure loss; here the
    waiter wants exactly the value the holder is about to store, so waiting
    IS the useful behaviour — it re-checks the cache on entry and returns the
    fresh result without a second audit."""
    global _cache_value, _cache_expires_at
    now = time.monotonic()
    if _cache_value is not None and now < _cache_expires_at:
        return _cache_value

    with _AUDIT_LOCK:
        # Re-check: another request may have completed the audit while this
        # one waited, which is the whole point of waiting.
        now = time.monotonic()
        if _cache_value is not None and now < _cache_expires_at:
            return _cache_value
        return _run_audit_and_cache(now)


def _run_audit_and_cache(now: float) -> dict:
    """Run the freshness audit and store it. Caller must hold `_AUDIT_LOCK`."""
    global _cache_value, _cache_expires_at
    try:
        # Import lazily so the module loads even if the audit script has issues
        import audit_data_freshness as audit_mod
        report = audit_mod.audit_all()
    except ModuleNotFoundError as exc:
        log.error("Failed to import audit_data_freshness: %s", exc)
        raise HTTPException(status_code=500, detail="Freshness audit module not available")
    except Exception as exc:
        log.error("Freshness audit failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Freshness audit failed: {exc}")

    response = report.to_dict()
    _cache_value = response
    _cache_expires_at = now + _CACHE_TTL
    return response


@router.get("/api/health/freshness")
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
