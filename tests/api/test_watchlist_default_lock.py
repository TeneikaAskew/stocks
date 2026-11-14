"""GET /api/insights/watchlist/default, and the owner the ranked route ranks.

FEAT-INSIGHT-001, stage A (docs/superpowers/specs/2026-11-13-feat-insight-001-watchlist-default-lock-a.md,
sections "New read-only endpoint" and "Ranked list").

Hermetic. The default endpoint reads through gcp.database.query_to_dataframe_strict; these tests put a
SQLAlchemy engine over an in-memory SQLite copy of the ``watchlists`` table beneath that reader by
patching gcp.database.get_engine, so the handler's own SQL text runs against real rows, and the 503 case
makes get_engine raise where Cloud SQL would fail. The reader itself is never replaced by a mock: an
implementation on the swallowing query_to_dataframe would answer 200 with ``rows: []`` and fail here
(done_when item 1).

The SQLite table declares ``added_at TIMESTAMPTZ`` and the flags ``BOOLEAN`` and the connection parses
declared types, so the DataFrame the handler sees carries tz-aware timestamps and bools, as pg8000
delivers them from Postgres, and the ISO serialisation is exercised on the real type.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy
from sqlalchemy.pool import StaticPool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="module")
def client():
    """TestClient for the FastAPI app (the fixture of tests/api/test_platform_api.py:33)."""
    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)

    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c

    os.chdir(original_cwd)


# ── an in-memory watchlists table with Postgres-shaped values ──────────────────

sqlite3.register_converter("TIMESTAMPTZ", lambda raw: dt.datetime.fromisoformat(raw.decode()))
sqlite3.register_converter("BOOLEAN", lambda raw: raw == b"1")

# The columns of gcp/schema.sql's watchlists table that the endpoint reads, plus the two predicates.
WATCHLISTS_DDL = (
    "CREATE TABLE watchlists ("
    " user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,"
    " added_at TIMESTAMPTZ NOT NULL, removed_at TIMESTAMPTZ NULL, source TEXT NULL,"
    " in_brief BOOLEAN NOT NULL DEFAULT 0, in_insight BOOLEAN NOT NULL DEFAULT 0,"
    " signals BOOLEAN NOT NULL DEFAULT 0, PRIMARY KEY (user_id, ticker))"
)
INSERT_ROW = (
    "INSERT INTO watchlists (user_id, ticker, added_at, removed_at, source, in_brief, in_insight, signals)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)
T0 = dt.datetime(2026, 4, 27, 13, 0, 0, tzinfo=dt.timezone.utc)


def _row(user_id, ticker, seconds, *, removed=False, source="seed", flags=(True, True, True)):
    added_at = (T0 + dt.timedelta(seconds=seconds)).isoformat()
    removed_at = (T0 + dt.timedelta(days=1)).isoformat() if removed else None
    return (user_id, ticker, added_at, removed_at, source, *[int(f) for f in flags])


# The state the spec records for production: three active default rows carrying every surface flag,
# added in the order SPY, QQQ, IWM (not alphabetical, so `ORDER BY added_at` is what the assertions
# see), plus a removed default row and another owner's row, which the two predicates must exclude.
FIXTURE_ROWS = [
    _row("default", "SPY", 0),
    _row("default", "QQQ", 1),
    _row("default", "IWM", 2, source=None),
    _row("default", "AAA", 3, removed=True),
    _row("alice@example.com", "BBB", 4, source="ui"),
]
EXPECTED_ADDED_AT = {"SPY": T0, "QQQ": T0 + dt.timedelta(seconds=1), "IWM": T0 + dt.timedelta(seconds=2)}


def _watchlists_engine(rows):
    """A SQLAlchemy engine over one in-memory SQLite database holding ``rows``, and the list that
    records every statement executed through it after seeding."""
    engine = sqlalchemy.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False, "detect_types": sqlite3.PARSE_DECLTYPES},
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(WATCHLISTS_DDL)
        if rows:
            conn.exec_driver_sql(INSERT_ROW, list(rows))
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sqlalchemy.event.listen(engine, "before_cursor_execute", record)
    return engine, statements


def _without_as_of(body: dict) -> dict:
    return {k: v for k, v in body.items() if k != "as_of"}


# ── GET /api/insights/watchlist/default ────────────────────────────────────────


def test_default_watchlist_returns_rows_in_added_at_order(client):
    from api.routers import insights as insights_module

    engine, statements = _watchlists_engine(FIXTURE_ROWS)
    with patch("gcp.database.get_engine", return_value=engine):
        r = client.get("/api/insights/watchlist/default")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["owner"] == "default"
    assert [row["ticker"] for row in body["rows"]] == ["SPY", "QQQ", "IWM"]
    for row in body["rows"]:
        assert isinstance(row["added_at"], str)
        # An ISO instant, never a pandas Timestamp repr: fromisoformat parses it back to the
        # instant that was stored.
        assert dt.datetime.fromisoformat(row["added_at"]) == EXPECTED_ADDED_AT[row["ticker"]]
        assert row["in_brief"] is True and row["in_insight"] is True and row["signals"] is True
    assert [row["source"] for row in body["rows"]] == ["seed", "seed", None]
    as_of = dt.datetime.fromisoformat(body["as_of"])
    assert as_of.tzinfo is not None and as_of.utcoffset() == dt.timedelta(0)
    # The handler ran exactly its declared statement, and that statement carries the owner, the
    # removal and the ordering predicates.
    assert statements == [insights_module.WATCHLIST_DEFAULT_SQL]
    assert "user_id = 'default'" in insights_module.WATCHLIST_DEFAULT_SQL
    assert "removed_at IS NULL" in insights_module.WATCHLIST_DEFAULT_SQL
    assert "ORDER BY added_at, ticker" in insights_module.WATCHLIST_DEFAULT_SQL


def test_default_watchlist_sql_excludes_removed_and_other_owners(client):
    """WATCHLIST_DEFAULT_SQL itself, run over the fixture rows: the removed default row AAA and
    alice@example.com's BBB are not returned, and the order is added_at, not ticker."""
    from api.routers import insights as insights_module

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(WATCHLISTS_DDL)
        conn.executemany(INSERT_ROW, FIXTURE_ROWS)
        tickers = [row[0] for row in conn.execute(insights_module.WATCHLIST_DEFAULT_SQL).fetchall()]
    finally:
        conn.close()
    assert tickers == ["SPY", "QQQ", "IWM"]


def test_default_watchlist_is_identical_for_open_and_signed_in_callers(client, monkeypatch):
    from api.routers import insights as insights_module

    engine, _ = _watchlists_engine(FIXTURE_ROWS)
    with patch("gcp.database.get_engine", return_value=engine):
        open_body = client.get("/api/insights/watchlist/default").json()
        monkeypatch.setattr(insights_module, "current_user_email", lambda req: "alice@example.com")
        signed_in_body = client.get("/api/insights/watchlist/default").json()
    assert _without_as_of(open_body) == _without_as_of(signed_in_body)
    assert [row["ticker"] for row in signed_in_body["rows"]] == ["SPY", "QQQ", "IWM"]


def test_default_watchlist_503_when_cloud_sql_fails(client):
    """The failure is injected beneath the strict reader. The swallowing query_to_dataframe would
    turn it into an empty DataFrame and a 200 with rows: [], which this test refuses."""
    with patch("gcp.database.get_engine", side_effect=RuntimeError("db down")):
        r = client.get("/api/insights/watchlist/default")
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert "db down" in detail
    assert detail.startswith("watchlist read from Cloud SQL failed")


def test_default_watchlist_empty_list_is_200(client):
    """Zero active default rows is a true state (an empty default list), not a failure."""
    engine, _ = _watchlists_engine([
        _row("default", "AAA", 0, removed=True),
        _row("alice@example.com", "BBB", 1, source="ui"),
    ])
    with patch("gcp.database.get_engine", return_value=engine):
        r = client.get("/api/insights/watchlist/default")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["owner"] == "default"
    assert body["rows"] == []
