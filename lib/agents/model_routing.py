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

import psycopg2
import psycopg2.extras

from .llm_client import RouteSnapshot, available_providers
from .pricing import PRICE_TABLE, Provider, list_priced_models
from .schema import ALL_ROLES, AgentRole


# ---------------------------------------------------------------------------
# Connection — reuses the same env-var contract as the rest of the
# codebase (CLOUD_SQL_URL takes precedence, else DB_* fallbacks).
# ---------------------------------------------------------------------------


def _connect():
    url = os.environ.get("CLOUD_SQL_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "trading"),
        user=os.environ.get("DB_USER", "trading_user"),
        password=os.environ.get("DB_PASSWORD", ""),
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
        conn = _connect()
        close = True
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT role, provider, model, updated_at, updated_by "
                "FROM model_routing"
            )
            rows = {r["role"]: r for r in cur.fetchall()}
        ordered: list[Route] = []
        for role in ALL_ROLES:
            r = rows.get(role)
            if r is None:
                continue
            ordered.append(
                Route(
                    role=role,
                    provider=r["provider"],
                    model=r["model"],
                    updated_at=(
                        r["updated_at"].isoformat() if r["updated_at"] else None
                    ),
                    updated_by=r["updated_by"],
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
    close = False
    if conn is None:
        conn = _connect()
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
