"""Real local SQL NULL -> pandas -> actual catalyst adapter, never Cloud SQL."""
import os
import json
import re
import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
import sqlalchemy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from gcp import database
from scripts import fetch_earnings_calendar as calendar

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform"))
from api.routers import catalysts


def _local_test_url():
    socket_dir = os.environ.get("CATALYST_TEST_PG_SOCKET_DIR")
    if socket_dir:
        expected = ROOT / ".superpowers/sdd/2026-10-27-feat-catalyst-001-finite-earnings-estimates/pg-socket"
        path = Path(socket_dir).absolute()
        if path.resolve() != expected or not (path / ".s.PGSQL.5432").is_socket():
            pytest.fail("Only the explicitly provisioned owned test socket is allowed")
        # A short test-owned alias avoids sockaddr_un's path-length limit;
        # validation still binds its resolved target to this exact fixture.
        if len(os.fsencode(path / ".s.PGSQL.5432")) > 107:
            pytest.fail("Use a short alias for the owned PostgreSQL test socket")
        return sqlalchemy.URL.create(
            "postgresql+pg8000", username="trading_user", password="testpass",
            database="finite_nullable_test", query={"unix_sock": str(path / ".s.PGSQL.5432")},
        )
    if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("DB_HOST") == "localhost":
        # Exact existing backtest-pipeline.yml ephemeral-container contract.
        return sqlalchemy.URL.create(
            "postgresql+pg8000", username="trading_user", password="testpass",
            host="localhost", port=5432, database="trading",
        )
    pytest.fail("Explicit owned local PostgreSQL fixture required; no backend fallback")


@pytest.fixture
def local_calendar_database(monkeypatch):
    import requests

    def forbidden(*args, **kwargs):
        raise AssertionError("Provider acquisition forbidden")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    url = _local_test_url()  # Fail closed BEFORE constructing any connection.
    schema = "finite_eps_test_" + uuid4().hex
    assert re.fullmatch(r"finite_eps_test_[0-9a-f]{32}", schema)
    bootstrap = sqlalchemy.create_engine(url, poolclass=StaticPool, connect_args={"timeout": 5})
    engine = None
    with bootstrap.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    try:
        engine = sqlalchemy.create_engine(
            url, poolclass=StaticPool,
            connect_args={"timeout": 5, "startup_params": {"search_path": schema}},
        )
        with engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE earnings_calendar (
                    ticker TEXT NOT NULL, earnings_date DATE NOT NULL,
                    company_name TEXT, earnings_time TEXT,
                    eps_estimate DOUBLE PRECISION, strategy TEXT NOT NULL,
                    data_source TEXT NOT NULL,
                    UNIQUE (ticker, earnings_date, strategy, data_source)
                )
            """)
        monkeypatch.setattr(database, "get_engine", lambda: engine)
        monkeypatch.setattr(database, "is_cloud_sql_configured", lambda: True)
        monkeypatch.setattr(database, "_REFLECTED_TABLES", {})
        yield bootstrap, engine, schema
    finally:
        if engine is not None:
            engine.dispose()
        with bootstrap.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        bootstrap.dispose()


def test_sql_null_dataframe_roundtrip_preserves_missing(local_calendar_database, monkeypatch, tmp_path):
    bootstrap, engine, schema = local_calendar_database
    frame = pd.DataFrame({
        "ticker": ["IWM", "QQQ", "SPY"], "date": ["2026-10-27"] * 3,
        "time": ["BMO"] * 3,
        "company_name": ["NullableCo", "ZeroCo", "NegativeCo"],
        "eps_estimate": [calendar._safe_num(None), calendar._safe_num(0), calendar._safe_num(-1.25)],
        "source": ["AlphaVantage"] * 3, "strategy": [""] * 3,
    })
    assert calendar.persist_to_cloud_sql(frame) == 3
    # Independent local session sees the committed values, not merely a write ACK.
    with bootstrap.connect() as observer:
        rows = observer.execute(sqlalchemy.text(
            f'SELECT ticker, eps_estimate FROM "{schema}".earnings_calendar ORDER BY ticker'
        )).all()
    assert rows == [("IWM", None), ("QQQ", 0.0), ("SPY", -1.25)]

    actual_query = database.query_to_dataframe
    retrieved = actual_query("SELECT ticker, eps_estimate FROM earnings_calendar ORDER BY ticker")
    assert len(retrieved) == 3
    assert str(retrieved["eps_estimate"].dtype) == "float64"
    assert pd.isna(retrieved.iloc[0]["eps_estimate"])

    def relevant_real_query(sql, params):
        if "FROM earnings_calendar " in sql:
            return actual_query(sql, params)
        if any(table in sql for table in (
            "FROM news_sentiment ", "FROM economic_events ",
            "FROM insider_transactions ", "FROM sec_filings ",
        )):
            return pd.DataFrame()
        raise AssertionError("Unexpected query outside the local earnings fixture")

    monkeypatch.setattr(database, "query_to_dataframe", relevant_real_query)
    events = catalysts._db_catalyst_events("2026-10-27", "2026-10-28", None)
    expected_titles = [
        ("IWM", "NullableCo earnings (BMO)"),
        ("QQQ", "ZeroCo earnings (BMO, est 0.00)"),
        ("SPY", "NegativeCo earnings (BMO, est -1.25)"),
    ]
    assert sorted((e["ticker"], e["title"]) for e in events) == expected_titles
    assert all(e["source"] == "AV earnings_calendar" and e["date"] == "2026-10-27" for e in events)

    # Complete the existing real router/response path over that same local SQL.
    def forbidden(*args, **kwargs):
        raise AssertionError("Provider refresh forbidden in PostgreSQL API proof")

    cache = tmp_path / "catalysts.json"
    cache.write_text(json.dumps({"events": []}), encoding="utf-8")
    monkeypatch.setattr(catalysts, "CATALYSTS_FILE", cache)
    monkeypatch.setattr(catalysts, "_fetch_live_events", forbidden)
    app = FastAPI()
    app.include_router(catalysts.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/catalysts/events", params={
            "date_from": "2026-10-27", "date_to": "2026-10-28",
        })
    assert response.status_code == 200
    assert response.json()["total"] == 3
    rendered_rows = response.json()["events_by_date"]["2026-10-27"]
    assert sorted((e["ticker"], e["title"]) for e in rendered_rows) == expected_titles
