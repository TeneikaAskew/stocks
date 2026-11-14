"""The 1-min session scan as the two routes that serve the freshness report show it.

``GET /api/health/freshness`` and ``GET /api/admin/data-sources`` both read one
cached run of ``audit_data_freshness.audit_all()`` (FEAT-DATA-001, Design B).
The audit runs for real here, over stubbed readers, at a fixed clock:

* a session with no regular-hours bar is a stale
  ``market_data_intraday [sessions]`` row on the first route and a stale
  ``market_data_intraday`` dataset on the second;
* a failed read of the scan is a 503 when the database is unreachable and a
  500 when the failure is a defect, never an empty result that reads as a gap.

No file under ``platform/api`` changes for this: the routes carry the new rows
as they carry every other row.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
# `platform/` makes the `api` package importable; `platform/api` makes
# `routers` a top-level package, so admin.py's `from .health import ...` and
# this module share ONE health module and therefore one report cache
# (the convention of tests/api/test_admin_users_datasources.py).
if str(REPO / "platform") not in sys.path:
    sys.path.insert(0, str(REPO / "platform"))
sys.path.insert(0, str(REPO / "platform" / "api"))

import pg8000.exceptions
import sqlalchemy.exc
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import admin as admin_module
from routers import health as health_module

# The name routers/health.py imports the audit under; a different module
# object from `scripts.audit_data_freshness`.
import audit_data_freshness as audit_mod

from tests.fixtures.intraday_checks import install_audit_readers, rth_frame

ADMIN_EMAIL = "admin@example.com"
ADMIN_HEADERS = {"x-goog-authenticated-user-email": f"accounts.google.com:{ADMIN_EMAIL}"}
NOW = datetime(2026, 11, 13, 15, 0)
FIVE = ("2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11")
SESSIONS = "market_data_intraday [sessions]"


@pytest.fixture
def routes(monkeypatch):
    """``get(path, scan)``: one request against both routers, with the audit
    running for real at NOW over readers whose session scan answers *scan*,
    and nothing cached from an earlier request."""
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    import api.auth
    monkeypatch.setattr(api.auth, "AUTH_MODE", "iap")

    real = audit_mod.audit_all
    monkeypatch.setattr(audit_mod, "audit_all", lambda: real(NOW))

    app = FastAPI()
    app.include_router(health_module.router)
    app.include_router(admin_module.router)
    client = TestClient(app, raise_server_exceptions=False)

    def get(path: str, scan):
        install_audit_readers(monkeypatch, audit_mod, scan)
        monkeypatch.setattr(health_module, "_cache", None)
        return client.get(path, headers=ADMIN_HEADERS)

    return get


def _no_spy_bar_on_the_ninth(ticker: str):
    return rth_frame({d: 390 for d in FIVE
                      if not (ticker == "SPY" and d == "2026-11-09")})


def test_a_missing_session_shows_on_both_routes(routes):
    r = routes("/api/health/freshness", _no_spy_bar_on_the_ninth)
    assert r.status_code == 200, r.text
    body = r.json()
    session_rows = [t for t in body["tables"] if t["table"] == SESSIONS]
    assert len(session_rows) == 1
    row = session_rows[0]
    assert row["ticker"] == "SPY"
    assert row["status"] == "stale"
    assert row["expected_latest"] == "2026-11-09"
    assert row["detail"].startswith("MISSING")
    assert body["overall_status"] == "stale"

    r = routes("/api/admin/data-sources", _no_spy_bar_on_the_ninth)
    assert r.status_code == 200, r.text
    (source,) = [s for s in r.json()["sources"] if s["id"] == "market_data_intraday"]
    assert source["status"] == "stale"
    assert "market_data_intraday [sessions] (SPY): stale" in source["message"]


@pytest.mark.parametrize("error,status", [
    (ConnectionError("connection refused"), 503),
    (KeyError("inserted_at"), 500),
    (sqlalchemy.exc.OperationalError(
        "SELECT 1", {}, pg8000.exceptions.DatabaseError({"C": "57014"})), 500),
], ids=["database-unreachable", "defect-in-the-read", "statement-timeout"])
def test_an_outage_is_503_and_a_defect_is_500(routes, error, status):
    assert routes("/api/health/freshness", error).status_code == status
    assert routes("/api/admin/data-sources", error).status_code == status
