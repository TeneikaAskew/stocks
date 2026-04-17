"""
Integration tests for the insights and admin routers.

Uses FastAPI TestClient against a real pgvector/pg15 container so
we exercise the actual SQL paths. The tests seed `insight_reports`,
`insight_runs`, and `model_routing` directly, then call the
endpoints and assert on response shapes and auth behavior.

Skipped when DB_HOST / CLOUD_SQL_URL isn't configured. Run locally:

    docker run -d --rm --name test-pg -p 55432:5432 \
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=trading \
        pgvector/pgvector:pg15
    export DB_HOST=localhost DB_PORT=55432 DB_NAME=trading \
           DB_USER=postgres DB_PASSWORD=test ADMIN_TOKEN=test-token
    pytest tests/test_routers_insights_admin.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "platform"))
sys.path.insert(0, str(PROJECT_ROOT))

psycopg2 = pytest.importorskip("psycopg2")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("DB_HOST") or os.environ.get("CLOUD_SQL_URL")),
    reason="no test Postgres configured (set DB_HOST)",
)

from fastapi.testclient import TestClient  # noqa: E402

from lib.agents.model_routing import connect  # noqa: E402
from lib.agents.schema import ALL_ROLES  # noqa: E402


# ---------------------------------------------------------------------------
# Schema + seed
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _schema():
    """Create the insights tables (no full schema.sql replay — only
    what the insights/admin routers touch)."""
    conn = connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS model_routing (
                role VARCHAR(32) PRIMARY KEY,
                provider VARCHAR(32) NOT NULL,
                model VARCHAR(64) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by VARCHAR(64)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS insight_reports (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                ticker VARCHAR(10) NOT NULL,
                as_of TIMESTAMPTZ NOT NULL,
                report JSONB NOT NULL,
                model_versions JSONB NOT NULL,
                cost_usd NUMERIC(10, 4),
                latency_ms INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_insight_reports_ticker_asof UNIQUE (ticker, as_of)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS insight_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                ticker VARCHAR(10) NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'queued',
                trigger VARCHAR(16) NOT NULL DEFAULT 'on_demand',
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                error TEXT,
                report_id UUID REFERENCES insight_reports(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute("DELETE FROM insight_runs")
        cur.execute("DELETE FROM insight_reports")
        cur.execute("DELETE FROM model_routing")
        for role in ALL_ROLES:
            cur.execute(
                "INSERT INTO model_routing (role, provider, model) VALUES (%s, %s, %s)",
                (role, "vertex", "gemini-2.0-flash"),
            )
    yield
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS insight_runs CASCADE")
        cur.execute("DROP TABLE IF EXISTS insight_reports CASCADE")
        cur.execute("DROP TABLE IF EXISTS model_routing CASCADE")
    conn.close()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("ENV", "local")
    # Import app *after* env is set so the admin token check uses it
    from api.main import app

    return TestClient(app)


@pytest.fixture
def seed_report():
    """Insert a fresh insight report for SPY and return the id."""
    conn = connect()
    row_id = str(uuid4())
    as_of = datetime.now(timezone.utc)
    payload = {
        "ticker": "SPY",
        "as_of": as_of.isoformat(),
        "direction": "long",
        "conviction": "medium",
        "thesis": "Breakout above prior-day high with FTFC bullish.",
        "entry_zone": {"low": 500.0, "high": 502.0},
        "stop": 497.5,
        "targets": [504.0, 508.0],
        "invalidation": "Close below 497.",
        "time_horizon": "swing",
        "key_levels": {"support": 497.5, "resistance": 504.0, "pivot": 500.0},
        "strat_status": {
            "last_candle": "2U",
            "in_force_combo": "2D-1-2U_reversal",
            "ftfc_score": 0.6,
            "ftfc_direction": "bullish",
            "trigger_high": 502.0,
            "trigger_low": 498.0,
        },
        "catalysts": [],
        "bull_case": "Trigger break with volume.",
        "bear_case": "Tight stop.",
        "risk_flags": [],
        "supporting_signals": [],
        "similar_past_trades": [],
        "confidence_score": 0.72,
        "failed_sections": [],
        "model_versions": {"trader": "vertex:gemini-2.0-flash"},
        "run_cost_usd": 0.012,
        "run_latency_ms": 11_500,
    }
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO insight_reports
                    (id, ticker, as_of, report, model_versions, cost_usd, latency_ms)
                VALUES (%s, 'SPY', %s, %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    row_id,
                    as_of,
                    json.dumps(payload),
                    json.dumps({"trader": "vertex:gemini-2.0-flash"}),
                    0.012,
                    11_500,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    yield row_id
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM insight_reports WHERE id=%s", (row_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Insights router
# ---------------------------------------------------------------------------


def test_get_insight_report_returns_latest(client, seed_report):
    r = client.get("/api/insights/report/SPY")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "SPY"
    assert body["report"]["direction"] == "long"
    assert body["cost_usd"] == 0.012
    assert body["latency_ms"] == 11_500


def test_get_insight_report_404_when_missing(client):
    r = client.get("/api/insights/report/QQQ")
    assert r.status_code == 404
    assert "QQQ" in r.json()["detail"]


def test_get_insight_history_returns_list(client, seed_report):
    r = client.get("/api/insights/report/SPY/history?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert body["reports"][0]["direction"] == "long"


def test_get_insight_history_rejects_bad_limit(client):
    r = client.get("/api/insights/report/SPY/history?limit=500")
    assert r.status_code == 400


def test_refresh_inserts_run(client, monkeypatch):
    # Don't actually execute the pipeline — monkey-patch the sync wrapper
    from api.routers import insights as insights_router

    called = {}

    def fake_sync_run(run_id, ticker):
        called["run_id"] = run_id
        called["ticker"] = ticker

    monkeypatch.setattr(insights_router, "_sync_run", fake_sync_run)

    r = client.post("/api/insights/report/IWM/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "IWM"
    assert body["status"] == "queued"
    run_id = body["run_id"]

    # Status endpoint should find the queued row
    r = client.get(f"/api/insights/runs/{run_id}")
    assert r.status_code == 200
    assert r.json()["status"] in ("queued", "running", "done")


def test_run_status_rejects_invalid_uuid(client):
    r = client.get("/api/insights/runs/not-a-uuid")
    assert r.status_code == 400


def test_run_status_404(client):
    r = client.get("/api/insights/runs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Admin router
# ---------------------------------------------------------------------------


def test_admin_requires_token(client):
    r = client.get("/api/admin/routes")
    assert r.status_code == 401


def test_admin_wrong_token_401(client):
    r = client.get("/api/admin/routes", headers={"X-Admin-Token": "nope"})
    assert r.status_code == 401


def test_admin_list_routes(client):
    r = client.get("/api/admin/routes", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["routes"]) == 7
    roles = [r["role"] for r in body["routes"]]
    assert set(roles) == set(ALL_ROLES)


def test_admin_update_route(client):
    r = client.put(
        "/api/admin/routes/trader",
        headers={"X-Admin-Token": "test-token"},
        json={"provider": "anthropic", "model": "claude-sonnet-4-6"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "trader"
    assert body["provider"] == "anthropic"
    # Restore
    client.put(
        "/api/admin/routes/trader",
        headers={"X-Admin-Token": "test-token"},
        json={"provider": "vertex", "model": "gemini-2.0-flash"},
    )


def test_admin_update_route_unknown_role(client):
    r = client.put(
        "/api/admin/routes/wizard",
        headers={"X-Admin-Token": "test-token"},
        json={"provider": "vertex", "model": "gemini-2.0-flash"},
    )
    assert r.status_code == 400


def test_admin_update_route_unpriced_model(client):
    r = client.put(
        "/api/admin/routes/trader",
        headers={"X-Admin-Token": "test-token"},
        json={"provider": "vertex", "model": "gemini-imaginary"},
    )
    assert r.status_code == 400


def test_admin_list_models(client):
    r = client.get("/api/admin/models", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["models"]) > 0
    assert all("provider" in m for m in body["models"])


def test_admin_503_when_token_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    from api.main import app

    c = TestClient(app)
    r = c.get("/api/admin/routes", headers={"X-Admin-Token": "anything"})
    assert r.status_code == 503
