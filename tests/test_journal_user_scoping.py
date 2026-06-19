"""Per-user journal isolation.

Every Cloud SQL query in the journal router must be scoped to the signed-in
user's email, so one user can never read or delete another user's trades. In
open/local dev (no auth) the owner defaults to "local" so the journal still
works offline; in an authenticated deployment a Cloud SQL failure fails loud
rather than falling back to the shared local file (which would leak trades).

Hermetic: the DB layer is mocked and the recorded SQL + params are asserted —
no network, no real Postgres.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

import api.routers.journal as journal  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _run(coro):
    """Drive a no-await coroutine to completion without an event loop.

    The journal endpoints are ``async def`` but contain no ``await`` (the DB
    layer is synchronous), so a single ``.send(None)`` runs the whole body and
    StopIteration carries the return value. This avoids ``asyncio.run()``, which
    raises "cannot be called from a running event loop" under the repo's test
    session.
    """
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    raise AssertionError("journal endpoint unexpectedly awaited")


class _EmptyDF:
    """Minimal stand-in for an empty DataFrame (only .empty is read here)."""
    empty = True


@pytest.fixture
def scoped(monkeypatch):
    """journal module with the DB layer mocked to record every call."""
    calls = {"q": [], "x": []}

    def fake_q(sql, params=None):
        calls["q"].append((sql, params or {}))
        return _EmptyDF()

    def fake_x(sql, params=None):
        calls["x"].append((sql, params or {}))

    monkeypatch.setattr(journal, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(journal, "query_to_dataframe", fake_q, raising=False)
    monkeypatch.setattr(journal, "execute_sql", fake_x, raising=False)
    return journal, calls


def _as(monkeypatch, email):
    """Pretend the request is authenticated as `email` (None = anonymous)."""
    monkeypatch.setattr(journal, "current_user_email", lambda req: email)


def _trade():
    return journal.JournalTradeCreate(
        ticker="spy", direction="CALL",
        entry_date="2026-06-12", entry_time="10:00", entry_price=500.0,
        exit_date="2026-06-12", exit_time="11:00", exit_price=505.0, notes="x",
    )


def test_get_is_scoped_to_user(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    _run(j.get_trades("spy", object()))
    sql, params = calls["q"][-1]
    assert "user_email = :user_email" in sql
    assert params["user_email"] == "alice@x.com"


def test_post_stamps_owner(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    _run(j.create_trade(_trade(), object()))
    insert_sql, insert_params = calls["x"][-1]
    assert "user_email" in insert_sql
    assert insert_params["user_email"] == "alice@x.com"
    # the read-back is also scoped so it can't surface another user's row
    _, select_params = calls["q"][-1]
    assert select_params["user_email"] == "alice@x.com"


def test_delete_is_scoped_to_owner(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    _run(j.delete_trade("id-123", object()))
    sql, params = calls["x"][-1]
    assert "id = :id AND user_email = :user_email" in sql
    assert params["user_email"] == "alice@x.com"


def test_two_users_are_isolated(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    _run(j.get_trades("spy", object()))
    _as(monkeypatch, "bob@y.com")
    _run(j.get_trades("spy", object()))
    assert calls["q"][-2][1]["user_email"] == "alice@x.com"
    assert calls["q"][-1][1]["user_email"] == "bob@y.com"


def test_open_mode_defaults_to_local(scoped, monkeypatch):
    """No identity (open/local dev) → the shared 'local' owner, never a crash."""
    j, calls = scoped
    _as(monkeypatch, None)
    _run(j.get_trades("spy", object()))
    assert calls["q"][-1][1]["user_email"] == "local"


def test_auth_mode_db_failure_fails_closed(scoped, monkeypatch):
    """A signed-in user must NOT get the shared local file on a Cloud SQL error
    (cross-user leak + Rule 3.7) — it fails loud with a 503 instead."""
    j, _ = scoped

    def boom(sql, params=None):
        raise RuntimeError("cloud sql down")

    _as(monkeypatch, "alice@x.com")
    monkeypatch.setattr(j, "query_to_dataframe", boom, raising=False)
    with pytest.raises(HTTPException) as ei:
        _run(j.get_trades("spy", object()))
    assert ei.value.status_code == 503
