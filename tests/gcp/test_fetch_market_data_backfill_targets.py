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


# ── FEAT-DATA-001 ingest v2: the all-history union counts only real bars from other writers ──────────

WATCHED_ARM = (
    "SELECT ticker FROM market_data_daily GROUP BY ticker "
    "HAVING bool_or(close IS NOT NULL AND data_source IS DISTINCT FROM 'av_watched_backfill')"
)


def _all_history_sql(monkeypatch) -> str:
    """The SQL _backfill_targets sends with BACKFILL_ALL_HISTORY=true."""
    from gcp.fetchers import fetch_market_data

    monkeypatch.setenv("BACKFILL_ALL_HISTORY", "true")
    captured: dict[str, str] = {}

    def fake_query(sql):
        captured["sql"] = sql
        return pd.DataFrame()

    with patch.object(fetch_market_data, "is_cloud_sql_configured", return_value=True), \
         patch("gcp.database.query_to_dataframe", side_effect=fake_query):
        fetch_market_data._backfill_targets()
    return captured["sql"]


def test_all_history_market_data_daily_arm_counts_only_real_bars_from_other_writers(monkeypatch):
    sql = _normalised(_all_history_sql(monkeypatch))
    assert WATCHED_ARM in sql, sql
    # The earnings_history arm is unchanged and still unions with it.
    assert "SELECT DISTINCT ticker FROM earnings_history UNION " + WATCHED_ARM in sql, sql


# (ticker, date, close, data_source)
DAILY_ROWS = [
    ("WATCHED", "2026-11-12", 10.0, "av_watched_backfill"),    # watched-only: absent
    ("WATCHED", "2026-11-13", 11.0, "av_watched_backfill"),
    ("INDONLY", "2026-11-12", 20.0, "av_watched_backfill"),    # watched plus an indicator-only row: absent
    ("INDONLY", "2026-11-13", None, None),
    ("MIXED", "2026-11-12", 30.0, "av_watched_backfill"),      # another writer's real bar: present
    ("MIXED", "2026-11-13", 31.0, "alphavantage"),
    ("NULLSRC", "2026-11-13", 40.0, None),                     # null-sourced with a close: present
]


def test_all_history_union_skips_watched_only_and_indicator_only_tickers(monkeypatch):
    from gcp.fetchers import fetch_market_data

    # SQLite lacks bool_or and IS DISTINCT FROM (older builds), so the test rewrites the captured
    # Postgres text for evaluation only. The Postgres text is what the SQL-text test above pins.
    sql = _normalised(_all_history_sql(monkeypatch))
    translated = sql.replace(
        "bool_or(close IS NOT NULL AND data_source IS DISTINCT FROM 'av_watched_backfill')",
        "MAX(CASE WHEN close IS NOT NULL AND data_source IS NOT 'av_watched_backfill' "
        "THEN 1 ELSE 0 END) = 1")
    assert translated != sql

    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE earnings_history (ticker TEXT)")
        conn.execute("CREATE TABLE market_data_daily "
                     "(ticker TEXT, date TEXT, close REAL, data_source TEXT)")
        conn.executemany("INSERT INTO market_data_daily VALUES (?, ?, ?, ?)", DAILY_ROWS)
        conn.execute("INSERT INTO earnings_history VALUES ('EARN')")
        conn.commit()

        monkeypatch.setenv("BACKFILL_ALL_HISTORY", "true")
        with patch.object(fetch_market_data, "is_cloud_sql_configured", return_value=True), \
             patch("gcp.database.query_to_dataframe",
                   side_effect=lambda _sql: pd.read_sql_query(translated, conn)):
            targets = fetch_market_data._backfill_targets()
    finally:
        conn.close()

    assert [t for t, _, _ in targets] == ["EARN", "MIXED", "NULLSRC"], targets


# ── FEAT-DATA-001 ingest v2: a pull this job makes for an existing orphan keeps it a target ───────────

def test_watched_job_pull_for_existing_orphan_keeps_it_a_backfill_target(monkeypatch):
    """ORPH has 300 av_daily_backfill bars and no earnings_history row. The plan stamps its pull
    av_daily_backfill, so the rows the job writes keep the union arm true for it."""
    from datetime import date

    from gcp.fetchers import fetch_market_data
    from gcp.fetchers import fetch_watched_tickers as fwt

    today = date(2026, 11, 13)
    cov = fwt.Coverage("ORPH", 300, date(2026, 11, 12), False)
    plan = fwt.plan_pulls({"ORPH": cov}, today)
    assert plan == {("full", "av_daily_backfill"): ["ORPH"]}
    (outputsize, data_source), tickers = next(iter(plan.items()))

    written: list[pd.DataFrame] = []
    bars = pd.DataFrame({
        "ticker": "ORPH", "date": list(pd.bdate_range(end="2026-01-30", periods=300).date),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100, "adjusted_close": 1.0})
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "fake-key")
    monkeypatch.setenv("AV_BACKFILL_SLEEP_SECS", "0")
    monkeypatch.setattr(fetch_market_data, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(fetch_market_data, "_av_get_full_daily_series", lambda t, k, o: bars.copy())
    monkeypatch.setattr("gcp.database.upsert_dataframe", lambda df, table, keys: written.append(df.copy()))
    assert fetch_market_data._run_backfill(tickers, outputsize=outputsize, data_source=data_source) == 300
    stored = pd.concat(written)
    assert set(stored["data_source"]) == {"av_daily_backfill"}

    # Evaluate the all-history union arm over exactly the rows the job wrote (SQLite translation as above).
    sql = _normalised(_all_history_sql(monkeypatch))
    translated = sql.replace(
        "bool_or(close IS NOT NULL AND data_source IS DISTINCT FROM 'av_watched_backfill')",
        "MAX(CASE WHEN close IS NOT NULL AND data_source IS NOT 'av_watched_backfill' "
        "THEN 1 ELSE 0 END) = 1")
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE earnings_history (ticker TEXT)")
        conn.execute("CREATE TABLE market_data_daily (ticker TEXT, date TEXT, close REAL, data_source TEXT)")
        conn.executemany("INSERT INTO market_data_daily VALUES (?, ?, ?, ?)",
                         [(r.ticker, str(r.date), r.close, r.data_source) for r in stored.itertuples()])
        conn.commit()
        monkeypatch.setenv("BACKFILL_ALL_HISTORY", "true")
        with patch.object(fetch_market_data, "is_cloud_sql_configured", return_value=True), \
             patch("gcp.database.query_to_dataframe",
                   side_effect=lambda _sql: pd.read_sql_query(translated, conn)):
            targets = fetch_market_data._backfill_targets()
    finally:
        conn.close()
    assert [t for t, _, _ in targets] == ["ORPH"], targets
