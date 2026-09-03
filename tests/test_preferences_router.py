"""Tests for GET/PUT /api/me/preferences — per-user appearance settings.

Asserts (spec + CLAUDE.md Rule 3.7):
  (a) GET with nothing stored → 404 (a real "nothing stored yet", never a
      200 with fabricated defaults);
  (b) GET with a row → 200 with exactly the four nullable fields;
  (c) PUT partial → ONE upsert whose SET list contains only the provided
      columns; 200 with the full stored object;
  (d) PUT explicit null → the field is in the SET list with a NULL param
      (clears it), while omitted fields stay out of the statement entirely;
  (e) PUT unknown enum value → 422 ('compact' is deliberately tested:
      the frontend ships comfy/default/dense only);
  (f) PUT unknown field → 422 (extra="forbid"), no DB call;
  (g) DB failure → LOUD 503 on both verbs, never a fake success/empty;
  (h) firebase mode without identity → 401 fail-closed, no DB call
      (guard for the /api/me open-prefix hazard documented in api/auth.py);
  (i) the row is always scoped by the SERVER-verified identity.

Hermetic: gcp.database.get_engine is patched — no Cloud SQL. Identity comes
through the real api.auth.current_user_email code paths (iap header / open
mode), with AUTH_MODE set via setattr per test_platform_auth.py's
setattr-over-reload convention.
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
from api.routers import preferences as prefs_router

FULL_ROW = {"theme": "dark", "nav_pattern": "top-tabs", "density": "dense", "accent": "violet"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(prefs_router.router)
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
        r = _client().get("/api/me/preferences")
    assert r.status_code == 404


def test_get_returns_stored_object_with_nulls_intact():
    stored = {"theme": None, "nav_pattern": "sidebar", "density": None, "accent": "rose"}
    engine, conn = _engine_mock(row=stored)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().get("/api/me/preferences")
    assert r.status_code == 200
    # Nulls pass through as JSON null — never coerced into a default.
    assert r.json() == stored
    # Scoped by owner ("local" in open mode — no auth configured in tests).
    assert _executed_params(conn)["user_email"] == "local"


def test_get_db_failure_is_loud_503():
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = _client().get("/api/me/preferences")
    assert r.status_code == 503


# ── PUT ──────────────────────────────────────────────────────────────────────

def test_put_partial_sets_only_provided_fields():
    engine, conn = _engine_mock(row=FULL_ROW)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put("/api/me/preferences", json={"density": "dense", "accent": "rose"})
    assert r.status_code == 200
    assert r.json() == FULL_ROW  # full stored object, straight from RETURNING

    assert conn.execute.call_count == 1  # ONE round trip (Rule 0)
    sql = _executed_sql(conn)
    assert "density = EXCLUDED.density" in sql
    assert "accent = EXCLUDED.accent" in sql
    # Omitted fields must not appear in the statement at all — an upsert
    # touching them would clobber stored values with NULLs.
    assert "theme" not in sql.replace("RETURNING theme, nav_pattern, density, accent", "")
    assert "nav_pattern = EXCLUDED" not in sql
    assert _executed_params(conn) == {"user_email": "local", "density": "dense", "accent": "rose"}


def test_put_explicit_null_clears_the_field():
    engine, conn = _engine_mock(row={**FULL_ROW, "accent": None})
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put("/api/me/preferences", json={"accent": None})
    assert r.status_code == 200
    assert r.json()["accent"] is None
    sql = _executed_sql(conn)
    assert "accent = EXCLUDED.accent" in sql
    assert _executed_params(conn) == {"user_email": "local", "accent": None}


def test_put_empty_body_is_valid_and_returns_stored_row():
    engine, conn = _engine_mock(row=FULL_ROW)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put("/api/me/preferences", json={})
    assert r.status_code == 200
    assert r.json() == FULL_ROW
    # No preference column may be written by an empty update.
    assert "EXCLUDED.theme" not in _executed_sql(conn)
    assert _executed_params(conn) == {"user_email": "local"}


@pytest.mark.parametrize(
    "body",
    [
        {"density": "compact"},   # spec guessed 'compact'; the frontend has no such density
        {"theme": "solarized"},
        {"nav_pattern": "bottom-bar"},
        {"accent": "chartreuse"},
        {"theme": 1},
    ],
)
def test_put_unknown_enum_value_is_422(body):
    with patch("gcp.database.get_engine") as ge:
        r = _client().put("/api/me/preferences", json=body)
    assert r.status_code == 422
    ge.assert_not_called()


def test_put_unknown_field_is_422_not_silently_dropped():
    with patch("gcp.database.get_engine") as ge:
        r = _client().put("/api/me/preferences", json={"font_size": "big"})
    assert r.status_code == 422
    ge.assert_not_called()


def test_put_db_failure_is_loud_503():
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = _client().put("/api/me/preferences", json={"theme": "dark"})
    assert r.status_code == 503


# ── Identity scoping ─────────────────────────────────────────────────────────

def test_firebase_mode_without_identity_fails_closed_401(monkeypatch):
    """If this path is ever served without the middleware having verified a
    token (the open-prefix regression documented in api/auth.py), the router
    itself must 401 rather than read/write the shared 'local' row."""
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "firebase")
    with patch("gcp.database.get_engine") as ge:
        c = _client()
        assert c.get("/api/me/preferences").status_code == 401
        assert c.put("/api/me/preferences", json={"theme": "dark"}).status_code == 401
    ge.assert_not_called()


def test_owner_is_the_server_verified_identity(monkeypatch):
    """iap mode: the row key comes from the IAP-verified header — normalized,
    and never from anything in the request body."""
    monkeypatch.setattr(auth_mod, "AUTH_MODE", "iap")
    engine, conn = _engine_mock(row=FULL_ROW)
    with patch("gcp.database.get_engine", return_value=engine):
        r = _client().put(
            "/api/me/preferences",
            json={"theme": "dark"},
            headers={"x-goog-authenticated-user-email": "accounts.google.com:Me@X.com"},
        )
    assert r.status_code == 200
    assert _executed_params(conn)["user_email"] == "me@x.com"
