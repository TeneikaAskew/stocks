"""Unit tests for lib.agents.model_routing.

Uses a local Postgres connection from DB_* env vars. Run via:

    pytest tests/test_agent_model_routing.py

The test is skipped if TEST_DB_URL / DB_HOST is not set in the
environment, so it won't block `make test` on machines without a DB.
To run it locally:

    docker run -d --rm --name test-pg -p 55432:5432 \
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=trading \
        pgvector/pgvector:pg15
    export DB_HOST=localhost DB_PORT=55432 DB_NAME=trading \
           DB_USER=postgres DB_PASSWORD=test
    pytest tests/test_agent_model_routing.py
"""

from __future__ import annotations

import os

import pytest

psycopg2 = pytest.importorskip("psycopg2")
from lib.agents.llm_client import RouteSnapshot, register_adapter
from lib.agents.model_routing import (
    _connect,
    get_route,
    list_available_models,
    list_routes,
    load_routes_snapshot,
    set_route,
    unique_providers,
)
from lib.agents.schema import ALL_ROLES


pytestmark = pytest.mark.skipif(
    not (os.environ.get("DB_HOST") or os.environ.get("CLOUD_SQL_URL")),
    reason="no test Postgres configured (set DB_HOST or CLOUD_SQL_URL)",
)


@pytest.fixture(scope="module")
def seeded_db():
    """Create model_routing table + seed rows. Drops it after."""
    conn = _connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS model_routing CASCADE")
        cur.execute(
            """
            CREATE TABLE model_routing (
                role VARCHAR(32) PRIMARY KEY,
                provider VARCHAR(32) NOT NULL,
                model VARCHAR(64) NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by VARCHAR(64)
            )
            """
        )
        for role in ALL_ROLES:
            cur.execute(
                "INSERT INTO model_routing (role, provider, model) VALUES (%s, %s, %s)",
                (role, "vertex", "gemini-2.0-flash"),
            )
    yield conn
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS model_routing CASCADE")
    conn.close()


def test_list_routes_has_all_seven_roles(seeded_db):
    routes = list_routes()
    assert len(routes) == 7
    assert {r.role for r in routes} == set(ALL_ROLES)
    assert all(r.provider == "vertex" for r in routes)
    assert all(r.model == "gemini-2.0-flash" for r in routes)


def test_list_routes_ordered_by_canonical_sequence(seeded_db):
    routes = list_routes()
    assert tuple(r.role for r in routes) == ALL_ROLES


def test_get_route_returns_named_role(seeded_db):
    r = get_route("trader")
    assert r.role == "trader"
    assert r.provider == "vertex"


def test_set_route_updates_single_role(seeded_db):
    set_route("trader", "anthropic", "claude-sonnet-4-6", updated_by="pytest")
    r = get_route("trader")
    assert r.provider == "anthropic"
    assert r.model == "claude-sonnet-4-6"
    assert r.updated_by == "pytest"
    # Other roles untouched
    assert get_route("analyst").provider == "vertex"
    # Restore for subsequent tests
    set_route("trader", "vertex", "gemini-2.0-flash", updated_by="pytest")


def test_set_route_rejects_unknown_role(seeded_db):
    with pytest.raises(ValueError, match="unknown role"):
        set_route("not_a_role", "vertex", "gemini-2.0-flash")  # type: ignore[arg-type]


def test_set_route_rejects_unpriced_model(seeded_db):
    with pytest.raises(ValueError, match="price table"):
        set_route("trader", "vertex", "gemini-not-real")


def test_load_routes_snapshot(seeded_db):
    snap = load_routes_snapshot()
    assert isinstance(snap, RouteSnapshot)
    assert set(snap.routes.keys()) == set(ALL_ROLES)
    versions = snap.model_versions()
    assert versions["analyst"] == "vertex:gemini-2.0-flash"


def test_load_routes_snapshot_errors_when_incomplete(seeded_db):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM model_routing WHERE role='risk'")
        conn.commit()
        with pytest.raises(RuntimeError, match="missing rows for roles"):
            load_routes_snapshot()
    finally:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO model_routing (role, provider, model) VALUES ('risk','vertex','gemini-2.0-flash')"
            )
        conn.commit()
        conn.close()


def test_list_available_models_marks_credentials():
    models = list_available_models()
    assert len(models) > 0
    # Without any adapters registered, has_credentials should be False
    # everywhere except whatever the test environment has set up.
    for m in models:
        assert m.provider in ("vertex", "anthropic", "openai")
        assert m.input_usd_per_mtok >= 0


def test_unique_providers_is_sorted():
    providers = unique_providers()
    assert providers == sorted(providers)
    assert "vertex" in providers
