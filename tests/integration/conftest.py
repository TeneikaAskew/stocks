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
    """SQLAlchemy engine for the ephemeral test Postgres (DB_HOST branch)."""
    from gcp.database import get_engine
    return get_engine()


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
        "journal_entries",
        "historical_signals",
        "signal_metrics",
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


"""Explicit local-only PostgreSQL fixtures; no credential discovery fallback."""
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine


@pytest.fixture
def catalyst_db():
    if not os.environ.get("DB_HOST"):
        pytest.fail("mandatory integration collection requires explicit ephemeral PostgreSQL selectors")
    assert os.environ.get("DB_HOST") in {"127.0.0.1", "localhost"}
    assert os.environ.get("DB_NAME", "").startswith("av_") or (
        os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("DB_NAME")=="trading"
        and os.environ.get("DB_USER")=="trading_user" and os.environ.get("DB_PASS")=="testpass")
    from gcp.database import _direct_db_url
    engine = create_engine(_direct_db_url())
    c = engine.connect()
    schema = "cat_scope_" + uuid.uuid4().hex[:12]
    c.exec_driver_sql(f"CREATE SCHEMA {schema}"); c.commit()
    c.exec_driver_sql(f"SET search_path TO {schema}"); c.commit()
    sql = Path("gcp/schema.sql").read_text()
    for name in ["earnings_history", "earnings_reactions", "news_sentiment", "insider_transactions"]:
        definition = re.search(r"^CREATE TABLE IF NOT EXISTS " + name + r" \(.*?^\);", sql, re.M | re.S).group()
        c.exec_driver_sql(definition)
    c.exec_driver_sql("ALTER TABLE earnings_history ADD COLUMN report_time VARCHAR(20),ADD COLUMN yahoo_report_time VARCHAR(20)"); c.commit()
    for marker in ["REVISIONS", "STORAGE"]:
        c.exec_driver_sql(sql.split("-- BEGIN AV CATALYST " + marker)[1].split("-- END AV CATALYST " + marker)[0]); c.commit()
    try:
        yield c
    finally:
        c.rollback()
        c.exec_driver_sql("SET search_path TO public"); c.commit()
        c.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE"); c.commit()
        c.close(); engine.dispose()
