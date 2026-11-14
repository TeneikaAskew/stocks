"""Real-SQL tests for the per-user watchlist statements (FEAT-INSIGHT-001).

The hermetic tests in tests/api/test_me_watchlist.py mock the data layer, so
they cannot see a defect in the SQL itself. These run the router's own SQL
constants against the real gcp/schema.sql on an ephemeral Postgres: one shared
watched_tickers row per ticker, per-user memberships, soft removal that keeps
added_at, the GET scoping and ordering, and the 200-row cap held by the
per-owner advisory lock under two concurrent adds.
"""
from __future__ import annotations

import os
import sys
import threading
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy

# The module truncates tables. The shared db_engine fixture does not skip: it
# calls gcp.database.get_engine(), which reaches Cloud SQL wherever production
# credentials exist. This guard keeps a local run off production.
pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_HOST"),
    reason="integration tests need a Postgres (DB_HOST) - see the "
    "integration-tests CI job in backtest-pipeline.yml",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "platform"))

# Tickers owned by these tests, so cleanup never touches other rows.
BAR_TICKER = "ZWLBAR"
INFO_TICKER = "ZWLINF"


def _sql():
    from api.routers import me_watchlist as m

    return m


def _t(sql: str):
    return sqlalchemy.text(sql)


def _add(conn, uid: str, ticker: str, source: str | None = "ui") -> None:
    m = _sql()
    conn.execute(_t(m.WATCHED_TICKER_INSERT_SQL), {"ticker": ticker})
    conn.execute(
        _t(m.USER_WATCHLIST_UPSERT_SQL),
        {"owner_uid": uid, "owner_email": f"{uid}@example.com",
         "ticker": ticker, "source": source},
    )


def _remove(conn, uid: str, ticker: str) -> int:
    return conn.execute(
        _t(_sql().USER_WATCHLIST_REMOVE_SQL), {"owner_uid": uid, "ticker": ticker}
    ).rowcount


@pytest.fixture
def wl(db_engine):
    """Empty watchlist tables before and after, and remove the ticker_info and
    market_data_daily rows these tests insert, so runs are repeatable."""
    def _clean():
        with db_engine.begin() as conn:
            conn.execute(_t("TRUNCATE TABLE user_watchlists, watched_tickers CASCADE"))
            conn.execute(_t("DELETE FROM ticker_info WHERE ticker = :t"), {"t": INFO_TICKER})
            conn.execute(_t("DELETE FROM market_data_daily WHERE ticker = :t"), {"t": BAR_TICKER})
    _clean()
    yield db_engine
    _clean()


def test_two_users_one_ticker_row(wl):
    with wl.begin() as conn:
        _add(conn, "u1", "NVDA")
        _add(conn, "u2", "NVDA")
    with wl.connect() as conn:
        tickers = conn.execute(_t("SELECT COUNT(*) FROM watched_tickers WHERE ticker = 'NVDA'")).scalar()
        members = conn.execute(
            _t("SELECT owner_uid FROM user_watchlists WHERE ticker = 'NVDA' ORDER BY owner_uid")
        ).scalars().all()
    assert tickers == 1
    assert members == ["u1", "u2"]


def test_readd_keeps_added_at(wl):
    with wl.begin() as conn:
        _add(conn, "u1", "NVDA", source="ui")
    with wl.connect() as conn:
        first = conn.execute(
            _t("SELECT added_at FROM user_watchlists WHERE owner_uid='u1' AND ticker='NVDA'")
        ).scalar()
    with wl.begin() as conn:
        assert _remove(conn, "u1", "NVDA") == 1
    with wl.begin() as conn:
        _add(conn, "u1", "NVDA", source="combobox-auto-add")
    with wl.connect() as conn:
        row = conn.execute(
            _t("SELECT added_at, removed_at, source FROM user_watchlists "
               "WHERE owner_uid='u1' AND ticker='NVDA'")
        ).one()
    assert row.added_at == first
    assert row.removed_at is None
    assert row.source == "combobox-auto-add"


def test_remove_leaves_other_membership_and_ticker_row(wl):
    with wl.begin() as conn:
        _add(conn, "u1", "NVDA")
        _add(conn, "u2", "NVDA")
    with wl.begin() as conn:
        assert _remove(conn, "u1", "NVDA") == 1
        # a second remove finds no active row
        assert _remove(conn, "u1", "NVDA") == 0
    with wl.connect() as conn:
        rows = {
            r.owner_uid: r.removed_at
            for r in conn.execute(_t("SELECT owner_uid, removed_at FROM user_watchlists WHERE ticker='NVDA'"))
        }
        tickers = conn.execute(_t("SELECT COUNT(*) FROM watched_tickers WHERE ticker='NVDA'")).scalar()
    assert rows["u1"] is not None
    assert rows["u2"] is None
    assert tickers == 1


def test_get_sql_scopes_and_orders(wl):
    m = _sql()
    with wl.begin() as conn:
        _add(conn, "u1", INFO_TICKER)
        _add(conn, "u1", BAR_TICKER)
        _add(conn, "u1", "GONE")
        _add(conn, "u2", "OTHR")
        assert _remove(conn, "u1", "GONE") == 1
        # distinct added_at values so the order is by added_at, not ticker
        conn.execute(_t("UPDATE user_watchlists SET added_at = '2026-01-02T00:00:00Z' "
                        "WHERE owner_uid='u1' AND ticker=:t"), {"t": BAR_TICKER})
        conn.execute(_t("UPDATE user_watchlists SET added_at = '2026-01-03T00:00:00Z' "
                        "WHERE owner_uid='u1' AND ticker=:t"), {"t": INFO_TICKER})
        conn.execute(
            _t("INSERT INTO ticker_info (ticker, name, exchange, asset_type) "
               "VALUES (:t, 'Info Corp', 'NASDAQ', 'Common Stock')"),
            {"t": INFO_TICKER},
        )

    def read():
        with wl.connect() as conn:
            return conn.execute(_t(m.ME_WATCHLIST_SQL), {"owner_uid": "u1"}).mappings().all()

    rows = read()
    # only u1's active rows, in added_at order
    assert [r["ticker"] for r in rows] == [BAR_TICKER, INFO_TICKER]
    bar, info = rows
    # no ticker_info row: name is null, never ''; no daily bar: null
    assert bar["name"] is None and bar["exchange"] is None and bar["asset_type"] is None
    assert bar["last_daily_bar"] is None
    assert info["name"] == "Info Corp" and info["exchange"] == "NASDAQ"
    assert info["last_daily_bar"] is None

    with wl.begin() as conn:
        conn.execute(
            _t("INSERT INTO market_data_daily (ticker, date, close) VALUES (:t, '2026-11-12', 10.5), "
               "(:t, '2026-11-13', NULL)"),
            {"t": BAR_TICKER},
        )
    bar = read()[0]
    # the latest bar WITH a close, not the later bar whose close is null
    assert bar["ticker"] == BAR_TICKER
    assert bar["last_daily_bar"] == date(2026, 11, 12)


def test_schema_objects_exist(wl):
    with wl.connect() as conn:
        tables = set(conn.execute(_t(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
            "AND table_name IN ('watched_tickers','user_watchlists')")).scalars())
        cols = {
            (r.table_name, r.column_name): (r.data_type, r.is_nullable, r.character_maximum_length)
            for r in conn.execute(_t(
                "SELECT table_name, column_name, data_type, is_nullable, character_maximum_length "
                "FROM information_schema.columns WHERE table_schema='public' "
                "AND table_name IN ('watched_tickers','user_watchlists')"))
        }
        idx = dict(conn.execute(_t(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND indexname IN ('user_watchlists_active_idx','user_watchlists_ticker_active_idx')")).all())
    assert tables == {"watched_tickers", "user_watchlists"}
    assert cols == {
        ("watched_tickers", "ticker"): ("character varying", "NO", 10),
        ("watched_tickers", "created_at"): ("timestamp with time zone", "NO", None),
        ("user_watchlists", "owner_uid"): ("character varying", "NO", 128),
        ("user_watchlists", "owner_email"): ("character varying", "NO", 320),
        ("user_watchlists", "ticker"): ("character varying", "NO", 10),
        ("user_watchlists", "source"): ("character varying", "YES", 20),
        ("user_watchlists", "added_at"): ("timestamp with time zone", "NO", None),
        ("user_watchlists", "removed_at"): ("timestamp with time zone", "YES", None),
    }
    assert set(idx) == {"user_watchlists_active_idx", "user_watchlists_ticker_active_idx"}
    for name, definition in idx.items():
        assert "WHERE (removed_at IS NULL)" in definition, (name, definition)


def test_cap_holds_under_concurrent_adds(wl):
    m = _sql()
    with wl.begin() as conn:
        for i in range(199):
            _add(conn, "u1", f"T{i:03d}")

    barrier = threading.Barrier(2)
    outcomes: dict[str, str] = {}
    errors: list[BaseException] = []

    def attempt(ticker: str) -> None:
        try:
            with wl.connect() as conn:
                tx = conn.begin()
                try:
                    barrier.wait(timeout=30)
                    conn.execute(_t(m.ME_WATCHLIST_LOCK_SQL), {"owner_uid": "u1"})
                    active = conn.execute(_t(m.ME_WATCHLIST_COUNT_SQL), {"owner_uid": "u1"}).scalar()
                    if active >= m.MAX_ACTIVE_ROWS:
                        tx.rollback()
                        outcomes[ticker] = "refused"
                        return
                    _add(conn, "u1", ticker)
                    tx.commit()
                    outcomes[ticker] = "added"
                except BaseException:
                    tx.rollback()
                    raise
        except BaseException as exc:  # surfaced in the main thread
            errors.append(exc)

    threads = [threading.Thread(target=attempt, args=(t,)) for t in ("AAA", "BBB")]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert not errors, errors
    assert sorted(outcomes.values()) == ["added", "refused"]
    with wl.connect() as conn:
        total = conn.execute(_t(
            "SELECT COUNT(*) FROM user_watchlists WHERE owner_uid = 'u1' AND removed_at IS NULL"
        )).scalar()
    assert total == 200
