"""Tests for GET/PUT /api/me/profile — per-user account settings.

Asserts (contract with solyra src/types/profile.ts + CLAUDE.md Rule 3.7):
  (a) GET with nothing stored → 404 (a real "nothing stored yet", never a
      200 with fabricated defaults — solyra's useProfile treats 404 as null);
  (b) GET with a row → 200 with exactly the twelve nullable fields;
  (c) PUT partial → ONE upsert whose SET list contains only the provided
      columns; 200 with the full stored object;
  (d) PUT explicit null → the field is in the SET list with a NULL param;
  (e) PUT unknown enum value → 422;
  (f) PUT unknown field → 422 (extra="forbid"), no DB call;
  (g) DB failure → LOUD 503 on both verbs, never a fake success/empty;
  (h) firebase mode without identity → 401 fail-closed, no DB call;
  (i) the row is always scoped by the SERVER-verified identity.

Hermetic: gcp.database.get_engine is patched — no Cloud SQL. Same
conventions as tests/test_preferences_router.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
PLATFORM_DIR = REPO / "platform"
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth as auth_mod
from api.routers import profile as profile_router

FULL_ROW = {
    "display_name": "Teneika",
    "timezone": "America/New_York",
    "default_ticker": "IWM",
    "default_timeframe": "1D",
    "account_size": 25000.0,
    "risk_per_trade_pct": 1.5,
    "notify_daily_digest": True,
    "notify_catalyst_alerts": False,
    "notify_signal_alerts": True,
    "number_format": "abbreviated",
    "date_format": "iso",
    "show_extended_hours": False,
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(profile_router.router)
    return TestClient(app)


def _engine_mock(row=None) -> tuple[MagicMock, MagicMock]:
    """Engine whose connect()/begin() conns return `row` from
    execute(...).mappings().first()."""
    engine = MagicMock()
    conn = MagicMock()
    for factory in (engine.connect, engine.begin):
        factory.return_value.__enter__.return_value = conn
        factory.return_value.__exit__.return_value = False
    conn.execute.return_value.mappings.return_value.first.return_value = row
    return engine, conn


def _executed_sql(conn: MagicMock) -> str:
    return str(conn.execute.call_args.args[0])


def _executed_params(conn: MagicMock) -> dict:
    return conn.execute.call_args.args[1]


# ── GET ──────────────────────────────────────────────────────────────────────

def test_get_with_nothing_stored_is_404():
    engine, _ = _engine_mock(row=None)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().get("/api/me/profile")
    assert r.status_code == 404


def test_get_returns_stored_object_with_nulls_intact():
    stored = {**FULL_ROW, "account_size": None, "display_name": None}
    engine, conn = _engine_mock(row=stored)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().get("/api/me/profile")
    assert r.status_code == 200
    # Nulls pass through as JSON null — never coerced into $0 or "".
    assert r.json() == stored
    # Scoped by owner ("local" in open mode — no auth configured in tests).
    assert _executed_params(conn)["user_email"] == "local"


def test_get_db_failure_is_loud_503():
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = _client().get("/api/me/profile")
    assert r.status_code == 503


# ── PUT ──────────────────────────────────────────────────────────────────────

def test_put_partial_sets_only_provided_fields():
    engine, conn = _engine_mock(row=FULL_ROW)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put(
            "/api/me/profile", json={"display_name": "T", "account_size": 10000}
        )
    assert r.status_code == 200
    assert r.json() == FULL_ROW  # full stored object, straight from RETURNING

    assert conn.execute.call_count == 1  # ONE round trip
    sql = _executed_sql(conn)
    assert "display_name = EXCLUDED.display_name" in sql
    assert "account_size = EXCLUDED.account_size" in sql
    # Omitted fields must not appear in the SET list — an upsert touching
    # them would clobber stored values with NULLs.
    assert "timezone = EXCLUDED" not in sql
    assert "notify_daily_digest = EXCLUDED" not in sql
    assert _executed_params(conn) == {
        "user_email": "local",
        "display_name": "T",
        "account_size": 10000.0,
    }


def test_put_explicit_null_clears_the_field():
    engine, conn = _engine_mock(row={**FULL_ROW, "risk_per_trade_pct": None})
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put("/api/me/profile", json={"risk_per_trade_pct": None})
    assert r.status_code == 200
    assert r.json()["risk_per_trade_pct"] is None
    sql = _executed_sql(conn)
    assert "risk_per_trade_pct = EXCLUDED.risk_per_trade_pct" in sql
    assert _executed_params(conn) == {"user_email": "local", "risk_per_trade_pct": None}


def test_put_empty_body_is_valid_and_returns_stored_row():
    engine, conn = _engine_mock(row=FULL_ROW)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put("/api/me/profile", json={})
    assert r.status_code == 200
    assert r.json() == FULL_ROW
    # No profile column may be written by an empty update.
    assert "EXCLUDED.display_name" not in _executed_sql(conn)
    assert _executed_params(conn) == {"user_email": "local"}


@pytest.mark.parametrize(
    "body",
    [
        {"default_timeframe": "2W"},     # not a DefaultTimeframe
        {"number_format": "scientific"},
        {"date_format": "eu"},
        # NB not "yes"/"1": pydantic's lax bool coercion accepts those.
        {"notify_daily_digest": "sometimes"},
        {"account_size": "lots"},
    ],
)
def test_put_unknown_enum_value_is_422(body):
    with patch("gcp.database.get_engine") as ge:
        r = _client().put("/api/me/profile", json=body)
    assert r.status_code == 422
    ge.assert_not_called()


def test_put_unknown_field_is_422_not_silently_dropped():
    with patch("gcp.database.get_engine") as ge:
        r = _client().put("/api/me/profile", json={"favorite_color": "green"})
    assert r.status_code == 422
    ge.assert_not_called()


def test_put_db_failure_is_loud_503():
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = _client().put("/api/me/profile", json={"display_name": "T"})
    assert r.status_code == 503


# ── Identity scoping ─────────────────────────────────────────────────────────

def test_firebase_mode_without_identity_fails_closed_401(monkeypatch):
    """If this path is ever served without the middleware having verified a
    token, the router itself must 401 rather than read/write the shared
    'local' row — same guard as preferences."""
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "firebase")
    with patch("gcp.database.get_engine") as ge:
        c = _client()
        assert c.get("/api/me/profile").status_code == 401
        assert c.put("/api/me/profile", json={"display_name": "T"}).status_code == 401
    ge.assert_not_called()


def test_owner_is_the_server_verified_identity(monkeypatch):
    """iap mode: the row key comes from the IAP-verified header — normalized,
    and never from anything in the request body."""
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "iap")
    engine, conn = _engine_mock(row=FULL_ROW)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put(
            "/api/me/profile",
            json={"display_name": "T"},
            headers={"x-goog-authenticated-user-email": "accounts.google.com:Me@X.com"},
        )
    assert r.status_code == 200
    assert _executed_params(conn)["user_email"] == "me@x.com"
