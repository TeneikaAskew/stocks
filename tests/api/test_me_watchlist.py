"""Per-user watchlist API: GET/POST/DELETE /api/me/watchlist.

This module covers the response and request models first (Task 3), then the
three routes as they land: listing the signed-in user's watchlist, adding a
ticker, and removing one. Hermetic: no database, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform"))


def test_me_watchlist_models_round_trip():
    from api.schemas import (
        MeWatchlistAddRequest,
        MeWatchlistRemoveResponse,
        MeWatchlistResponse,
        MeWatchlistRow,
    )

    row = MeWatchlistRow(ticker="AAPL", added_at="2026-11-14T12:00:00+00:00")
    assert row.source is None
    assert row.name is None
    assert row.exchange is None
    assert row.asset_type is None
    assert row.last_daily_bar is None

    resp = MeWatchlistResponse(
        owner_email="a@b.com", as_of="2026-11-14T12:00:00+00:00", tickers=[row]
    )
    assert resp.tickers[0].ticker == "AAPL"

    removed = MeWatchlistRemoveResponse(**resp.model_dump(), removed=True)
    assert removed.removed is True
    with pytest.raises(ValidationError):
        MeWatchlistRemoveResponse(**resp.model_dump(), removed=False)

    assert MeWatchlistAddRequest(ticker="AAPL", source="ui").source == "ui"
    with pytest.raises(ValidationError):
        MeWatchlistAddRequest(ticker="AAPL", source="cli")


# ── GET /api/me/watchlist ───────────────────────────────────────────────────

import re  # noqa: E402

import pandas as pd  # noqa: E402


@pytest.fixture(scope="module")
def client():
    import os

    original_cwd = os.getcwd()
    platform_dir = str(REPO_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)

    from starlette.testclient import TestClient
    from api.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    os.chdir(original_cwd)


def _sign_in(monkeypatch):
    from api.auth import UserIdentity
    from api.routers import me_watchlist

    monkeypatch.setattr(
        me_watchlist,
        "current_user_identity",
        lambda req: UserIdentity("u1", "alice@example.com"),
    )
    return me_watchlist


def _recorder(monkeypatch, me_watchlist, frame=None, exc=None):
    calls = []

    def fake(sql, params=None, *a, **k):
        calls.append((sql, params))
        if exc is not None:
            raise exc
        return frame

    monkeypatch.setattr(me_watchlist, "query_to_dataframe_strict", fake)
    return calls


def test_get_requires_identity(client, monkeypatch):
    from api.routers import me_watchlist

    monkeypatch.setattr(me_watchlist, "current_user_identity", lambda req: None)
    calls = _recorder(monkeypatch, me_watchlist, frame=pd.DataFrame())
    r = client.get("/api/me/watchlist")
    assert r.status_code == 401
    assert r.json()["detail"] == "sign in required"
    assert calls == []


def test_get_lists_active_rows_in_added_at_order(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    frame = pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT", "ZZZZ"],
            "added_at": [
                pd.Timestamp("2026-11-01T10:00:00+00:00"),
                pd.Timestamp("2026-11-02T10:00:00+00:00"),
                pd.Timestamp("2026-11-03T10:00:00+00:00"),
            ],
            "source": ["ui", "api", None],
            "name": ["Apple Inc.", float("nan"), None],
            "exchange": ["NASDAQ", float("nan"), None],
            "asset_type": ["stock", float("nan"), None],
            "last_daily_bar": [pd.Timestamp("2026-11-13").date(), pd.NaT, None],
        }
    )
    calls = _recorder(monkeypatch, mw, frame=frame)
    r = client.get("/api/me/watchlist")
    assert r.status_code == 200
    body = r.json()
    assert len(calls) == 1
    assert calls[0][0] == mw.ME_WATCHLIST_SQL
    assert calls[0][1] == {"owner_uid": "u1"}
    assert body["owner_email"] == "alice@example.com"
    assert body["as_of"]
    rows = body["tickers"]
    assert [x["ticker"] for x in rows] == ["AAPL", "MSFT", "ZZZZ"]
    assert rows[0]["added_at"] == "2026-11-01T10:00:00+00:00"
    assert rows[0]["last_daily_bar"] == "2026-11-13"
    assert rows[0]["name"] == "Apple Inc."
    for key in ("name", "exchange", "asset_type", "last_daily_bar"):
        assert rows[1][key] is None
        assert rows[2][key] is None
    assert rows[2]["source"] is None


def test_get_empty_is_200(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _recorder(monkeypatch, mw, frame=pd.DataFrame())
    r = client.get("/api/me/watchlist")
    assert r.status_code == 200
    assert r.json()["tickers"] == []


def test_get_503_when_read_fails(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _recorder(monkeypatch, mw, exc=ConnectionError("db down"))
    r = client.get("/api/me/watchlist")
    assert r.status_code == 503
    assert "db down" in r.json()["detail"]


def test_get_defect_is_500_not_503(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _recorder(monkeypatch, mw, exc=KeyError("shape"))
    r = client.get("/api/me/watchlist")
    assert r.status_code == 500


def test_router_reads_only_through_the_strict_reader():
    src = (REPO_ROOT / "platform" / "api" / "routers" / "me_watchlist.py").read_text()
    assert "query_to_dataframe_strict" in src
    assert not re.search(r"query_to_dataframe(?!_strict)", src)
    assert not re.search(r"\bwatchlists\b", src)


# ── POST /api/me/watchlist and DELETE /api/me/watchlist/{ticker} ────────────


class _FakeResult:
    def __init__(self, rowcount=1, scalar=0):
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar(self):
        return self._scalar


class _FakeConn:
    def __init__(self, log, count, rowcount, exc):
        self.log, self.count, self.rowcount, self.exc = log, count, rowcount, exc

    def execute(self, statement, params=None):
        sql = str(statement)
        self.log.append((sql, params))
        if self.exc is not None:
            raise self.exc
        if "COUNT(*)" in sql:
            return _FakeResult(scalar=self.count)
        return _FakeResult(rowcount=self.rowcount)


class _FakeBegin:
    def __init__(self, conn, state):
        self.conn, self.state = conn, state

    def __enter__(self):
        self.state["begins"] += 1
        return self.conn

    def __exit__(self, *exc):
        return False


class _FakeEngine:
    def __init__(self, count=0, rowcount=1, exc=None, begin_exc=None):
        self.log = []
        self.state = {"begins": 0}
        self.begin_exc = begin_exc
        self.conn = _FakeConn(self.log, count, rowcount, exc)

    def begin(self):
        if self.begin_exc is not None:
            raise self.begin_exc
        return _FakeBegin(self.conn, self.state)


def _engine(monkeypatch, mw, **kw):
    eng = _FakeEngine(**kw)
    monkeypatch.setattr(mw, "get_engine", lambda: eng)
    return eng


def _frame_after(monkeypatch, mw):
    return _recorder(monkeypatch, mw, frame=pd.DataFrame())


def test_post_requires_identity_before_any_statement(client, monkeypatch):
    from api.routers import me_watchlist as mw

    monkeypatch.setattr(mw, "current_user_identity", lambda req: None)
    eng = _engine(monkeypatch, mw)
    r = client.post("/api/me/watchlist", json={"ticker": "AAPL", "source": "ui"})
    assert r.status_code == 401
    assert eng.log == [] and eng.state["begins"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"ticker": "ap pl", "source": "ui"},
        {"ticker": "TOOLONGTICKER", "source": "ui"},
        {"ticker": "AAPL", "source": "cli"},
    ],
)
def test_post_rejects_bad_ticker_and_source(client, monkeypatch, body):
    mw = _sign_in(monkeypatch)
    eng = _engine(monkeypatch, mw)
    r = client.post("/api/me/watchlist", json=body)
    assert r.status_code == 422
    assert eng.log == []


def test_post_409_when_full(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    eng = _engine(monkeypatch, mw, count=200)
    r = client.post("/api/me/watchlist", json={"ticker": "AAPL", "source": "ui"})
    assert r.status_code == 409
    assert r.json()["detail"] == "watchlist full"
    assert [s for s, _ in eng.log] == [mw.ME_WATCHLIST_LOCK_SQL, mw.ME_WATCHLIST_COUNT_SQL]


def test_post_inserts_ticker_then_upserts_membership(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    eng = _engine(monkeypatch, mw, count=3)
    _frame_after(monkeypatch, mw)
    r = client.post("/api/me/watchlist", json={"ticker": " nvda ", "source": "ui"})
    assert r.status_code == 200
    assert eng.state["begins"] == 1
    assert [s for s, _ in eng.log] == [
        mw.ME_WATCHLIST_LOCK_SQL,
        mw.ME_WATCHLIST_COUNT_SQL,
        mw.WATCHED_TICKER_INSERT_SQL,
        mw.USER_WATCHLIST_UPSERT_SQL,
    ]
    assert eng.log[0][1] == {"owner_uid": "u1"}
    assert eng.log[1][1] == {"owner_uid": "u1"}
    assert eng.log[2][1] == {"ticker": "NVDA"}
    assert eng.log[3][1] == {
        "owner_uid": "u1",
        "owner_email": "alice@example.com",
        "ticker": "NVDA",
        "source": "ui",
    }
    do_update = mw.USER_WATCHLIST_UPSERT_SQL.split("DO UPDATE SET", 1)[1]
    assert "added_at" not in do_update
    assert "removed_at = NULL" in do_update


def test_delete_404_when_no_active_row(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _engine(monkeypatch, mw, rowcount=0)
    r = client.delete("/api/me/watchlist/AAPL")
    assert r.status_code == 404
    assert r.json()["detail"] == "not on your watchlist"


def test_delete_soft_deletes_and_answers_list(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    eng = _engine(monkeypatch, mw, rowcount=1)
    _frame_after(monkeypatch, mw)
    r = client.delete("/api/me/watchlist/aapl")
    assert r.status_code == 200
    assert r.json()["removed"] is True
    assert r.json()["tickers"] == []
    assert eng.log == [(mw.USER_WATCHLIST_REMOVE_SQL, {"owner_uid": "u1", "ticker": "AAPL"})]


def test_delete_rejects_bad_ticker(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    eng = _engine(monkeypatch, mw)
    assert client.delete("/api/me/watchlist/TOOLONGTICKER").status_code == 422
    assert eng.log == []


def test_write_failure_is_503(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _engine(monkeypatch, mw, exc=ConnectionError("db down"))
    r = client.post("/api/me/watchlist", json={"ticker": "AAPL", "source": "ui"})
    assert r.status_code == 503
    assert "db down" in r.json()["detail"]


def test_post_503_when_cloud_sql_fails(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _engine(monkeypatch, mw, begin_exc=ConnectionError("db down"))
    r = client.post("/api/me/watchlist", json={"ticker": "AAPL", "source": "ui"})
    assert r.status_code == 503


def test_post_defect_is_500_not_503(client, monkeypatch):
    mw = _sign_in(monkeypatch)
    _engine(monkeypatch, mw, begin_exc=KeyError("shape"))
    r = client.post("/api/me/watchlist", json={"ticker": "AAPL", "source": "ui"})
    assert r.status_code == 500
