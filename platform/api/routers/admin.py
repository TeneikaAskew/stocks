"""
Admin router — model-routing dashboard backend.

All endpoints require the `X-Admin-Token` header to match the
`ADMIN_TOKEN` environment variable on the server. The token is
NEVER exposed in the frontend bundle — the browser fetches it from
sessionStorage (entered once per tab) and sends it as a header.
If the token is unset or the header doesn't match, every endpoint
returns 401.

Endpoints:
  GET    /api/admin/routes         — list per-role provider/model
  PUT    /api/admin/routes/{role}  — update one role
  GET    /api/admin/models         — catalog of priced models with
                                     credential availability
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.agents.model_routing import (  # noqa: E402
    AvailableModel,
    Route,
    list_available_models,
    list_routes,
    set_route,
)
from lib.agents.schema import ALL_ROLES, AgentRole  # noqa: E402

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "teneika@bictech.org").lower()


def _iap_user_email(request: Request) -> Optional[str]:
    """Extract email from the IAP-injected header."""
    raw = request.headers.get("x-goog-authenticated-user-email")
    if not raw:
        return None
    return raw.split(":", 1)[-1].strip().lower()


def _require_admin(
    request: Request,
    x_admin_token: Optional[str],
) -> None:
    # Allow the admin email through without a token (IAP-authenticated)
    iap_email = _iap_user_email(request)
    if iap_email and iap_email == _ADMIN_EMAIL:
        return

    expected = os.environ.get("ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_TOKEN not configured on the server",
        )
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="invalid admin token")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RouteRow(BaseModel):
    role: str
    provider: str
    model: str
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class RouteListResponse(BaseModel):
    routes: list[RouteRow]


class RouteUpdateRequest(BaseModel):
    provider: str
    model: str


class AvailableModelRow(BaseModel):
    provider: str
    model: str
    has_credentials: bool
    input_usd_per_mtok: float
    output_usd_per_mtok: float


class AvailableModelsResponse(BaseModel):
    models: list[AvailableModelRow]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _route_to_row(r: Route) -> RouteRow:
    return RouteRow(
        role=r.role,
        provider=r.provider,
        model=r.model,
        updated_at=r.updated_at,
        updated_by=r.updated_by,
    )


def _model_to_row(m: AvailableModel) -> AvailableModelRow:
    return AvailableModelRow(
        provider=m.provider,
        model=m.model,
        has_credentials=m.has_credentials,
        input_usd_per_mtok=m.input_usd_per_mtok,
        output_usd_per_mtok=m.output_usd_per_mtok,
    )


@router.get("/routes", response_model=RouteListResponse)
async def admin_list_routes(request: Request, x_admin_token: Optional[str] = Header(None)):
    _require_admin(request, x_admin_token)
    rows = [_route_to_row(r) for r in list_routes()]
    return RouteListResponse(routes=rows)


@router.put("/routes/{role}", response_model=RouteRow)
async def admin_update_route(
    role: str,
    body: RouteUpdateRequest,
    request: Request,
    x_admin_token: Optional[str] = Header(None),
):
    _require_admin(request, x_admin_token)
    if role not in ALL_ROLES:
        raise HTTPException(status_code=400, detail=f"unknown role: {role}")
    try:
        set_route(role, body.provider, body.model, updated_by="admin-ui")  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Return the updated row
    for r in list_routes():
        if r.role == role:
            return _route_to_row(r)
    raise HTTPException(status_code=500, detail="update succeeded but row not found")


@router.get("/models", response_model=AvailableModelsResponse)
async def admin_list_models(request: Request, x_admin_token: Optional[str] = Header(None)):
    _require_admin(request, x_admin_token)
    return AvailableModelsResponse(
        models=[_model_to_row(m) for m in list_available_models()]
    )
