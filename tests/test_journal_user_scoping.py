"""Per-user journal isolation.

Every Cloud SQL query in the journal router must be scoped to the signed-in
user's email, so one user can never read or delete another user's trades. In
open/local dev (no auth) the owner defaults to "local" so the journal still
works offline; in an authenticated deployment a Cloud SQL failure fails loud
rather than falling back to the shared local file (which would leak trades).

Hermetic: the DB layer is mocked and the recorded SQL + params are asserted —
no network, no real Postgres.
"""
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

import api.routers.journal as journal  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _run(result):
    """Return an endpoint's result, whether it is sync or a no-await coroutine.

    The journal endpoints are plain ``def`` now. They were ``async def`` with no
    ``await`` in the body, which is the worst of both worlds: the synchronous DB
    layer ran ON the event loop and serialised every concurrent request behind
    it. As ``def``, FastAPI dispatches them to its threadpool and they return
    their value directly.

    The coroutine branch stays so this helper remains correct if an endpoint
    legitimately becomes ``async`` later. It drives a no-await coroutine with a
    single ``.send(None)`` rather than ``asyncio.run()``, which would raise
    "cannot be called from a running event loop" under this test session.
    """
    if not inspect.iscoroutine(result):
        return result
    try:
        result.send(None)
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

    def fake_returning(sql, params=None, allow_no_row=False):
        """The trade INSERT path — `RETURNING id`, one statement.

        Recorded in the same bucket as `execute_sql` so the scoping
        assertions below read the INSERT's params wherever it ran.
        """
        calls["x"].append((sql, params or {}))
        return "generated-id"

    monkeypatch.setattr(journal, "_HAS_CLOUD_SQL", True, raising=False)
    monkeypatch.setattr(journal, "query_to_dataframe", fake_q, raising=False)
    monkeypatch.setattr(journal, "execute_sql", fake_x, raising=False)
    monkeypatch.setattr(journal, "execute_returning_scalar", fake_returning,
                        raising=False)
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


def test_post_has_no_readback_to_leak_another_users_row(scoped, monkeypatch):
    """The id comes from `RETURNING`, so there is no follow-up SELECT.

    This used to assert that the read-back was *scoped* to the owner. The
    read-back is gone: it was a
    `SELECT ... ORDER BY created_at DESC LIMIT 1` matching on
    (ticker, entry_ts, user_email), which a concurrent create by the SAME
    owner could win, returning that trade's id instead. Scoping made it safe
    across users and never made it correct within one. Not issuing the query
    is strictly stronger than scoping it.
    """
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    _run(j.create_trade(_trade(), object()))
    insert_sql, _ = calls["x"][-1]
    assert "RETURNING" in insert_sql.upper()
    assert not any("SELECT id" in sql for sql, _ in calls["q"]), (
        "the insert path issued a read-back SELECT; the id must come from "
        "RETURNING in the insert statement itself")


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
