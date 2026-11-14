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
