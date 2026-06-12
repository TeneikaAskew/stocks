"""Per-user journal isolation.

Every Cloud SQL query in the journal router must be scoped to the signed-in
user's email, so one user can never read or delete another user's trades.
Hermetic: the DB layer is mocked and the recorded SQL + params are asserted —
no network, no real Postgres.
"""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

import api.routers.journal as journal  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class _EmptyDF:
    """Minimal stand-in for an empty DataFrame (only .empty is used here)."""
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
    asyncio.run(j.get_trades("spy", object()))
    sql, params = calls["q"][-1]
    assert params["user_email"] == "alice@x.com"
    assert "user_email = :user_email" in sql


def test_create_stamps_owner(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    asyncio.run(j.create_trade(_trade(), object()))
    insert_sql, insert_params = calls["x"][-1]
    assert insert_params["user_email"] == "alice@x.com"
    assert "user_email" in insert_sql
    # the follow-up id lookup is scoped too (can't grab another user's row id)
    _, sel_params = calls["q"][-1]
    assert sel_params["user_email"] == "alice@x.com"


def test_delete_matches_owner(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    asyncio.run(j.delete_trade("some-id", object()))
    sql, params = calls["x"][-1]
    assert params == {"id": "some-id", "user_email": "alice@x.com"}
    assert "id = :id AND user_email = :user_email" in sql


def test_two_users_are_isolated(scoped, monkeypatch):
    j, calls = scoped
    _as(monkeypatch, "alice@x.com")
    asyncio.run(j.get_trades("spy", object()))
    _as(monkeypatch, "bob@x.com")
    asyncio.run(j.get_trades("spy", object()))
    assert calls["q"][-2][1]["user_email"] == "alice@x.com"
    assert calls["q"][-1][1]["user_email"] == "bob@x.com"


def test_anonymous_is_rejected(scoped, monkeypatch):
    j, _ = scoped
    _as(monkeypatch, None)
    for make in (
        lambda: j.get_trades("spy", object()),
        lambda: j.create_trade(_trade(), object()),
        lambda: j.delete_trade("x", object()),
    ):
        with pytest.raises(HTTPException) as ei:
            asyncio.run(make())
        assert ei.value.status_code == 401
