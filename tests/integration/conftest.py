"""Fixtures for the real-SQL integration tests.

These run against an ephemeral Postgres loaded with `gcp/schema.sql`
(the `integration-tests` job in `.github/workflows/backtest-pipeline.yml`).
Unlike the hermetic mocked tests, they execute the *production* query
paths against the *real* schema — so a renamed column, a SQL typo, or a
broken JOIN fails here instead of in production.

`gcp.database.get_engine()` takes its `DB_HOST` branch (added alongside
these tests) when `DB_HOST` is set, so the production query functions
(`query_to_dataframe`, the `lib.agents.summarizers` helpers, …) all
transparently hit the test Postgres.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def db_engine():
    """SQLAlchemy engine for the ephemeral test Postgres (DB_HOST branch).

    Skip (don't error) when no Postgres is configured. The CI
    `integration-tests` job sets DB_HOST for the ephemeral container, so
    these run there; locally / in a sandbox without a DB they skip
    cleanly instead of erroring with a RuntimeError that looks like a
    broken test. A *configured-but-unreachable* DB still surfaces a real
    connection error later (in clean_db/seed) rather than being masked.
    """
    from gcp.database import get_engine
    try:
        return get_engine()
    except RuntimeError as e:
        pytest.skip(f"integration tests require a configured Postgres: {e}")


@pytest.fixture
def clean_db(db_engine):
    """Truncate the tables the integration tests write to, before each
    test, so tests are order-independent. The DB is a throwaway CI
    container, so CASCADE is safe."""
    import sqlalchemy

    tables = (
        "signal_alerts",
        "market_data_daily",
        "etf_options_snapshots",
        "premarket_analysis",
        "daily_rates",
        "backtest_trades",
        "backtest_sweeps",
        "backtest_reports",
    )
    with db_engine.begin() as conn:
        for t in tables:
            conn.execute(
                sqlalchemy.text(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
            )
    return db_engine


@pytest.fixture
def seed(db_engine):
    """Return an `insert(table, rows)` helper. `rows` is a list of dicts;
    every dict must have the same keys. Only the provided columns are
    written — the rest take their schema defaults / NULL."""
    import sqlalchemy

    def _insert(table: str, rows: list[dict]) -> None:
        if not rows:
            return
        cols = list(rows[0].keys())
        col_sql = ", ".join(cols)
        ph_sql = ", ".join(f":{c}" for c in cols)
        stmt = sqlalchemy.text(
            f"INSERT INTO {table} ({col_sql}) VALUES ({ph_sql})"
        )
        with db_engine.begin() as conn:
            conn.execute(stmt, rows)

    return _insert


@pytest.fixture
def run_sql(db_engine):
    """Return a `run_sql(sql, params)` helper that executes a query and
    returns a DataFrame. Unlike `gcp.database.query_to_dataframe`, this
    does NOT swallow exceptions — a drifted column raises the real
    Postgres error so the failure is legible."""
    import pandas as pd
    import sqlalchemy

    def _run(sql: str, params: dict | None = None) -> pd.DataFrame:
        with db_engine.connect() as conn:
            return pd.read_sql(sqlalchemy.text(sql), conn, params=params or {})

    return _run
