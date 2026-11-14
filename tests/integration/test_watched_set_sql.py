"""Real-SQL test of WATCHED_SET_SQL against the real schema.

Seeds watched_tickers / user_watchlists and runs the job's own set query,
including the mixed static and non-static case: the static list must be
excluded BEFORE the LIMIT, so it cannot eat slots of the 50.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy

from gcp.fetchers import fetch_market_data
from gcp.fetchers.fetch_watched_tickers import WATCHED_SET_SQL

pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_HOST"),
    reason="integration tests need a Postgres (DB_HOST) - see the "
    "integration-tests CI job in backtest-pipeline.yml",
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _clean(conn):
    conn.execute(sqlalchemy.text(
        "TRUNCATE TABLE user_watchlists, watched_tickers CASCADE"))


@pytest.fixture
def seeded(db_engine):
    with db_engine.begin() as conn:
        _clean(conn)
    yield db_engine
    with db_engine.begin() as conn:
        _clean(conn)


def _seed(engine, n_eligible: int):
    """SPY and IWM earliest, then n_eligible tickers, then one removed."""
    names = ['SPY', 'IWM'] + [f'E{i:03d}' for i in range(n_eligible)] + ['GONE']
    with engine.begin() as conn:
        for i, t in enumerate(names):
            conn.execute(sqlalchemy.text(
                "INSERT INTO watched_tickers (ticker, created_at) VALUES (:t, :c)"),
                {'t': t, 'c': _BASE + timedelta(minutes=i)})
            conn.execute(sqlalchemy.text(
                "INSERT INTO user_watchlists (owner_uid, owner_email, ticker, removed_at) "
                "VALUES ('u1', 'u1@example.com', :t, :r)"),
                {'t': t, 'r': _BASE if t == 'GONE' else None})
    return names[2:-1]


def _run(engine):
    with engine.connect() as conn:
        return conn.execute(sqlalchemy.text(WATCHED_SET_SQL),
                            {'limit': 50, 'exclude': list(fetch_market_data.TICKERS)}).all()


def test_static_excluded_before_limit_and_removed_dropped(seeded):
    eligible = _seed(seeded, 60)
    rows = _run(seeded)
    assert len(rows) == 50
    got = [r[0] for r in rows]
    assert not set(got) & set(fetch_market_data.TICKERS)
    assert 'GONE' not in got
    assert {r[1] for r in rows} == {60}
    assert got == eligible[:50]


def test_overflow_count_is_exact_at_51(seeded):
    _seed(seeded, 51)
    rows = _run(seeded)
    assert len(rows) == 50
    assert {r[1] for r in rows} == {51}
