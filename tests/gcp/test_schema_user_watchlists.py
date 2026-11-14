"""Schema tests for the per-user watchlist tables (FEAT-INSIGHT-001).

`gcp/schema.sql` is parsed with `split_statements`, the way the apply job
does, so the assertions run against the statements it would execute.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gcp.apply_schema import split_statements

SCHEMA = Path(__file__).resolve().parents[2] / "gcp" / "schema.sql"


def _norm(stmt: str) -> str:
    """Strip comment lines and collapse whitespace."""
    lines = [ln.split("--")[0] if "--" in ln else ln for ln in stmt.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


@pytest.fixture(scope="module")
def statements() -> list[str]:
    return [_norm(s) for s in split_statements(SCHEMA.read_text())]


def _one(statements: list[str], prefix: str) -> str:
    found = [s for s in statements if s.startswith(prefix)]
    assert len(found) == 1, f"expected exactly one statement starting {prefix!r}, got {len(found)}"
    return found[0]


def test_watched_tickers_table_statement(statements):
    s = _one(statements, "CREATE TABLE IF NOT EXISTS watched_tickers")
    assert "ticker VARCHAR(10) PRIMARY KEY" in s
    assert "CHECK (ticker = UPPER(ticker) AND ticker ~ '^[A-Z0-9.]{1,10}$')" in s
    assert "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()" in s


def test_user_watchlists_table_statement(statements):
    s = _one(statements, "CREATE TABLE IF NOT EXISTS user_watchlists")
    for col in (
        "owner_uid VARCHAR(128) NOT NULL",
        "owner_email VARCHAR(320) NOT NULL",
        "ticker VARCHAR(10) NOT NULL REFERENCES watched_tickers(ticker)",
        "source VARCHAR(20) NULL",
        "added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "removed_at TIMESTAMPTZ NULL",
    ):
        assert col in s, col
    assert "PRIMARY KEY (owner_uid, ticker)" in s


def test_user_watchlists_partial_indexes(statements):
    a = _one(statements, "CREATE INDEX IF NOT EXISTS user_watchlists_active_idx")
    assert a.rstrip(";").endswith("ON user_watchlists (owner_uid) WHERE removed_at IS NULL")
    b = _one(statements, "CREATE INDEX IF NOT EXISTS user_watchlists_ticker_active_idx")
    assert b.rstrip(";").endswith("ON user_watchlists (ticker) WHERE removed_at IS NULL")


def test_statements_are_idempotent(statements):
    mine = [
        s
        for s in statements
        if s.startswith(
            (
                "CREATE TABLE IF NOT EXISTS watched_tickers",
                "CREATE TABLE IF NOT EXISTS user_watchlists",
                "CREATE INDEX IF NOT EXISTS user_watchlists_",
            )
        )
        or re.match(r"CREATE (TABLE|INDEX)\b.*\b(watched_tickers|user_watchlists)", s[:90])
    ]
    assert len(mine) == 4
    assert all("IF NOT EXISTS" in s for s in mine)
