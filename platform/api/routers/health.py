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


@router.get("/api/health/freshness")
async def get_freshness():
    """Return a freshness report for every tracked Cloud SQL data table.

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
          "status": "ok",
          "row_count_recent": 1
        },
        ...
      ]
    }
    ```
    """
    global _cache_value, _cache_expires_at
    now = time.monotonic()
    if _cache_value is not None and now < _cache_expires_at:
        return _cache_value

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
