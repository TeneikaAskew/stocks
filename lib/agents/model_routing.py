"""
Read/write helpers for the `model_routing` Cloud SQL table.

The orchestrator loads a snapshot once at pipeline start; the /admin
router uses these helpers to list routes, update a single role, and
probe the model catalog.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional

import atexit

import psycopg2

from .llm_client import RouteSnapshot, available_providers
from .pricing import PRICE_TABLE, Provider, list_priced_models
from .schema import ALL_ROLES, AgentRole


# ---------------------------------------------------------------------------
# Connection — three supported modes, in priority order:
#
#   1. CLOUD_SQL_URL          — a full libpq URL; used by CI and the
#                               Cloud Tasks-triggered Cloud Run job.
#   2. CLOUD_SQL_CONNECTION_NAME — production default. Uses the Cloud
#                               SQL Python Connector with pg8000, the
#                               same path every other router uses via
#                               gcp.database.get_engine(). This works
#                               without a local proxy because the
#                               connector tunnels through IAM.
#   3. DB_HOST / DB_PORT      — direct psycopg2 socket for tests
#                               against a local Postgres container.
#
# All three return a DB-API-2 compliant connection. Callers use
# positional cursor access (no RealDictCursor) so the same code works
# against both psycopg2 and pg8000.
# ---------------------------------------------------------------------------

# Singleton Cloud SQL Connector — reused across all connect() calls so
# we don't leak connection-pool instances on every request.
_CONNECTOR = None


def _get_connector():
    global _CONNECTOR
    if _CONNECTOR is None:
        from google.cloud.sql.connector import Connector  # type: ignore

        _CONNECTOR = Connector()
        atexit.register(_CONNECTOR.close)
    return _CONNECTOR


def connect():
    url = os.environ.get("CLOUD_SQL_URL")
    if url:
        return psycopg2.connect(url)

    conn_name = os.environ.get("CLOUD_SQL_CONNECTION_NAME")
    if conn_name:
        connector = _get_connector()
        return connector.connect(
            conn_name,
            "pg8000",
            user=os.environ.get("DB_USER", "trading_user"),
            password=os.environ.get("DB_PASS", os.environ.get("DB_PASSWORD", "")),
            db=os.environ.get("DB_NAME", "trading"),
        )

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "trading"),
        user=os.environ.get("DB_USER", "trading_user"),
        password=os.environ.get("DB_PASS", os.environ.get("DB_PASSWORD", "")),
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Route:
    role: AgentRole
    provider: Provider
    model: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


def list_routes(conn=None) -> list[Route]:
    """Return all 7 per-role routes ordered by ALL_ROLES."""
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT role, provider, model, updated_at, updated_by "
                "FROM model_routing"
            )
            raw = cur.fetchall()
        finally:
            cur.close()
        by_role: dict[str, tuple] = {row[0]: row for row in raw}
        ordered: list[Route] = []
        for role in ALL_ROLES:
            row = by_role.get(role)
            if row is None:
                continue
            updated_at_val = row[3]
            ordered.append(
                Route(
                    role=role,
                    provider=row[1],
                    model=row[2],
                    updated_at=(
                        updated_at_val.isoformat()
                        if hasattr(updated_at_val, "isoformat")
                        else (str(updated_at_val) if updated_at_val else None)
                    ),
                    updated_by=row[4],
                )
            )
        return ordered
    finally:
        if close:
            conn.close()


def get_route(role: AgentRole, conn=None) -> Route:
    for r in list_routes(conn):
        if r.role == role:
            return r
    raise KeyError(f"No route configured for role {role!r}")


def set_route(
    role: AgentRole,
    provider: Provider,
    model: str,
    updated_by: Optional[str] = None,
    conn=None,
) -> None:
    """Upsert a single role's route."""
    if role not in ALL_ROLES:
        raise ValueError(f"unknown role: {role!r}")
    if (provider, model) not in PRICE_TABLE:
        raise ValueError(
            f"{provider}:{model} is not in the known price table — "
            "add it to lib/agents/pricing.py first"
        )
    if provider not in set(available_providers()):
        raise ValueError(
            f"Provider {provider!r} has no registered adapter — "
            "the pipeline will crash if this route is activated. "
            "Install the SDK and set credentials first."
        )
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_routing (role, provider, model, updated_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (role) DO UPDATE
                  SET provider = EXCLUDED.provider,
                      model = EXCLUDED.model,
                      updated_by = EXCLUDED.updated_by,
                      updated_at = NOW()
                """,
                (role, provider, model, updated_by),
            )
        conn.commit()
    finally:
        if close:
            conn.close()


def load_routes_snapshot(conn=None) -> RouteSnapshot:
    """Capture all 7 routes into an immutable snapshot for a single
    pipeline run. Called once at orchestrator start; never refreshed
    mid-run."""
    snapshot: dict[AgentRole, tuple[Provider, str]] = {}
    for r in list_routes(conn):
        snapshot[r.role] = (r.provider, r.model)
    missing = [role for role in ALL_ROLES if role not in snapshot]
    if missing:
        raise RuntimeError(
            f"model_routing table is missing rows for roles: {missing}"
        )
    return RouteSnapshot(routes=snapshot)


# ---------------------------------------------------------------------------
# Catalog — what the /admin dropdown can show
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AvailableModel:
    provider: Provider
    model: str
    has_credentials: bool
    input_usd_per_mtok: float
    output_usd_per_mtok: float


def list_available_models() -> list[AvailableModel]:
    """Catalog of models the admin can pick from. `has_credentials`
    tells the UI whether the provider is actually usable — e.g. an
    Anthropic model is listed but grayed out when ANTHROPIC_API_KEY
    is unset."""
    providers_ready = set(available_providers())
    out: list[AvailableModel] = []
    for provider, model in list_priced_models():
        rates = PRICE_TABLE[(provider, model)]
        out.append(
            AvailableModel(
                provider=provider,
                model=model,
                has_credentials=provider in providers_ready,
                input_usd_per_mtok=rates.input_usd_per_mtok,
                output_usd_per_mtok=rates.output_usd_per_mtok,
            )
        )
    return out


def unique_providers() -> list[Provider]:
    return sorted({p for p, _ in list_priced_models()})
