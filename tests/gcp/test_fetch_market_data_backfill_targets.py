"""_backfill_targets (gcp/fetchers/fetch_market_data.py): the watchlists arm of the manual --backfill
path targets only the active default watchlist (FEAT-INSIGHT-001 stage A, spec section "The one reader
fix").

Until this change the arm was ``SELECT ticker FROM watchlists WHERE COALESCE(in_brief, false) OR
COALESCE(in_insight, false)``: no owner and no removal predicate, so a removed ticker and any owner's rows
were backfill targets. The fixed arm adds ``user_id = 'default' AND removed_at IS NULL`` and keeps the two
COALESCE terms.

Hermetic. The SQL the function sends is captured by patching gcp.database.query_to_dataframe (the pattern
of tests/gcp/test_backfill_targets_orphans.py), and the behavioural test runs that same SQL text, through
the function itself, against an in-memory SQLite database holding the four tables it reads.

Another branch (the FEAT-DATA-001 ingest plan) adds its own tests to a file of this name; the helpers
here are self-contained.
"""
from __future__ import annotations

import re
import sqlite3
from unittest.mock import patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _default_backfill_path(monkeypatch):
    """The watchlists arm exists on the default path only (BACKFILL_ALL_HISTORY unset)."""
    monkeypatch.delenv("BACKFILL_ALL_HISTORY", raising=False)


def _captured_default_path_sql() -> str:
    """The SQL _backfill_targets sends on the manual --backfill path."""
    from gcp.fetchers import fetch_market_data

    captured: dict[str, str] = {}

    def fake_query(sql):
        captured["sql"] = sql
        return pd.DataFrame()

    with patch.object(fetch_market_data, "is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.query_to_dataframe", side_effect=fake_query):
        fetch_market_data._backfill_targets()
    return captured["sql"]


def _normalised(sql: str) -> str:
    return " ".join(sql.split())


FIXED_WATCHLISTS_ARM = (
    "SELECT ticker FROM watchlists WHERE user_id = 'default' AND removed_at IS NULL "
    "AND (COALESCE(in_brief, false) OR COALESCE(in_insight, false))"
)


def test_watchlists_arm_names_the_default_owner_and_excludes_removed_rows():
    sql = _normalised(_captured_default_path_sql())
    assert FIXED_WATCHLISTS_ARM in sql, sql
    # One watchlists arm, and it sits inside the eligible CTE's UNION with the earnings_calendar arm.
    assert sql.count("FROM watchlists") == 1, sql
    assert re.search(r"WITH eligible AS \( SELECT DISTINCT ticker FROM earnings_calendar .*? UNION "
                     + re.escape(FIXED_WATCHLISTS_ARM) + r" \)", sql), sql


# ── the SQL run over rows ──────────────────────────────────────────────────────

_DDL = (
    "CREATE TABLE earnings_calendar (ticker TEXT, options_volume INTEGER, stock_volume INTEGER,"
    " data_source TEXT)",
    "CREATE TABLE watchlists (user_id TEXT NOT NULL, ticker TEXT NOT NULL, in_brief BOOLEAN NOT NULL,"
    " in_insight BOOLEAN NOT NULL, signals BOOLEAN NOT NULL, removed_at TEXT NULL, source TEXT NULL,"
    " PRIMARY KEY (user_id, ticker))",
    "CREATE TABLE earnings_history (ticker TEXT)",
    "CREATE TABLE market_data_daily (ticker TEXT, date TEXT)",
)

REMOVED_AT = "2026-11-13 15:18:00+00:00"   # the owner's cut of the 13 unflagged rows

# (user_id, ticker, in_brief, in_insight, signals, removed_at, source)
WATCHLIST_ROWS = [
    ("default", "SPY", 1, 1, 1, None, "seed"),                  # active, flagged: a target
    ("default", "DDD", 0, 1, 0, None, "seed"),                  # active, in_insight only: a target
    ("default", "AAA", 1, 1, 1, REMOVED_AT, "avgo-peer"),       # removed default row: not a target
    ("alice@example.com", "BBB", 1, 1, 0, None, "ui"),          # another owner's row: not a target
    ("default", "CCC", 0, 0, 0, None, "discord-replay"),        # active, unflagged: not a target
]
CALENDAR_ROWS = [("EEE", 1200, 900_000)]                        # the earnings_calendar arm still unions in
HISTORY_TICKERS = ["SPY", "DDD", "AAA", "BBB", "CCC", "EEE"]   # every candidate has earnings history


def _targets_over(rows) -> list[tuple]:
    """Run _backfill_targets with its SQL executed against SQLite holding ``rows``."""
    from gcp.fetchers import fetch_market_data

    conn = sqlite3.connect(":memory:")
    try:
        for ddl in _DDL:
            conn.execute(ddl)
        conn.executemany(
            "INSERT INTO watchlists (user_id, ticker, in_brief, in_insight, signals, removed_at, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany("INSERT INTO earnings_calendar (ticker, options_volume, stock_volume)"
                         " VALUES (?, ?, ?)", CALENDAR_ROWS)
        conn.executemany("INSERT INTO earnings_history VALUES (?)", [(t,) for t in HISTORY_TICKERS])
        conn.commit()

        def run_in_sqlite(sql):
            return pd.read_sql_query(sql, conn)

        with patch.object(fetch_market_data, "is_cloud_sql_configured", return_value=True), \
             patch("gcp.database.query_to_dataframe", side_effect=run_in_sqlite):
            return fetch_market_data._backfill_targets()
    finally:
        conn.close()


def test_removed_and_other_owner_rows_are_not_backfill_targets():
    targets = _targets_over(WATCHLIST_ROWS)
    tickers = [t for t, _, _ in targets]
    assert tickers == ["DDD", "EEE", "SPY"], targets
    assert "AAA" not in tickers, "a removed default ticker must not be a target"
    assert "BBB" not in tickers, "another owner's ticker must not be a target"
    assert "CCC" not in tickers, "an unflagged default ticker was never a target"
    # No market_data_daily rows: every target reports zero bars and no latest date.
    assert all(bars == 0 and max_date is None for _, bars, max_date in targets), targets


def test_an_empty_default_watchlist_leaves_the_calendar_arm():
    targets = _targets_over([("default", "AAA", 1, 1, 1, REMOVED_AT, "seed")])
    assert [t for t, _, _ in targets] == ["EEE"], targets
