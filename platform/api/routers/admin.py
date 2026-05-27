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


# ---------------------------------------------------------------------------
# Structure brief — dev-only readout of the strat-engine type model.
#
# The model is a STRUCTURE predictor (next bar is 1 / 2U / 2D / 3) under
# the calibration=none production config. This endpoint surfaces its
# per-cell predictions for use in a dev-only review surface. It is NOT
# wired into /dashboard, /signals, /live, /premarket_brief, or any other
# user-facing route. It is NOT triggered by any scheduler. Deploy is
# blocked until Tracks B and C report verdicts.
# ---------------------------------------------------------------------------

STRUCTURE_BRIEF_TICKERS = ("IWM", "SPY", "QQQ")
STRUCTURE_BRIEF_TFS = ("5m", "15m", "30m")
STRUCTURE_BRIEF_ECE_CEILING = 0.05
STRUCTURE_BRIEF_SCOPE_STATEMENT = (
    "Calibrated structure prediction. Not a directional or P&L edge. "
    "Use with discretion."
)


class StructureBriefClassProb(BaseModel):
    cls: str  # one of "1", "2U", "2D", "3"
    prob: float


class StructureBriefCell(BaseModel):
    ticker: str
    timeframe: str
    available: bool
    top_class: Optional[str] = None
    top_prob: Optional[float] = None
    distribution: list[StructureBriefClassProb] = []
    live_ece: Optional[float] = None
    ece_ceiling: float = STRUCTURE_BRIEF_ECE_CEILING
    muted: bool = False
    mute_reason: Optional[str] = None
    refreshed_at: Optional[str] = None  # ISO-8601 UTC
    note: Optional[str] = None  # populated when available=false


class StructureBriefResponse(BaseModel):
    scope_statement: str = STRUCTURE_BRIEF_SCOPE_STATEMENT
    cells: list[StructureBriefCell]
    ece_ceiling: float = STRUCTURE_BRIEF_ECE_CEILING


def _load_structure_brief_snapshot() -> Optional[dict]:
    """Load the most recent structure-brief snapshot from GCS.

    The snapshot is written by an upstream process that is OUT OF SCOPE for
    Track A (it is part of the production pipeline blocked behind the
    deploy gate). When the snapshot does not exist, each cell is returned
    with available=False so the brief degrades gracefully.
    """
    bucket_name = os.environ.get(
        "GCS_BUCKET", "adept-mountain-474619-d4-trading-data"
    )
    blob_path = "research/strat_engine/structure_brief_latest.json"
    try:
        from google.cloud import storage as gcs
        client = gcs.Client()
        blob = client.bucket(bucket_name).blob(blob_path)
        if not blob.exists():
            return None
        import json as _json
        return _json.loads(blob.download_as_bytes())
    except Exception:
        return None


def _build_brief_cell(ticker: str, tf: str, snap: Optional[dict]) -> StructureBriefCell:
    """Build one cell from a snapshot dict; return available=False when absent."""
    if snap is None:
        return StructureBriefCell(
            ticker=ticker,
            timeframe=tf,
            available=False,
            note=(
                "No live snapshot available. Production data source is "
                "blocked behind the Track B / Track C deploy gate."
            ),
        )
    key = f"{ticker}_{tf}"
    cell_data = snap.get("cells", {}).get(key)
    if not cell_data:
        return StructureBriefCell(
            ticker=ticker,
            timeframe=tf,
            available=False,
            note="Cell missing from snapshot.",
        )
    live_ece = cell_data.get("live_ece")
    muted = False
    mute_reason = None
    if live_ece is not None and live_ece > STRUCTURE_BRIEF_ECE_CEILING:
        muted = True
        mute_reason = (
            f"model muted, ECE breach (live ECE {live_ece:.3f} "
            f"> ceiling {STRUCTURE_BRIEF_ECE_CEILING:.3f})"
        )
    dist = [
        StructureBriefClassProb(cls=c, prob=float(p))
        for c, p in cell_data.get("distribution", {}).items()
    ]
    if dist:
        top = max(dist, key=lambda x: x.prob)
        top_class = top.cls
        top_prob = top.prob
    else:
        top_class = None
        top_prob = None
    return StructureBriefCell(
        ticker=ticker,
        timeframe=tf,
        available=True,
        top_class=None if muted else top_class,
        top_prob=None if muted else top_prob,
        distribution=[] if muted else dist,
        live_ece=live_ece,
        ece_ceiling=STRUCTURE_BRIEF_ECE_CEILING,
        muted=muted,
        mute_reason=mute_reason,
        refreshed_at=cell_data.get("refreshed_at"),
    )


@router.get("/structure-brief", response_model=StructureBriefResponse)
async def admin_structure_brief(
    request: Request, x_admin_token: Optional[str] = Header(None)
):
    """Dev-only readout of the strat-engine type model's structure predictions.

    Dev-only: this endpoint sits behind the existing admin auth (IAP email
    OR X-Admin-Token header). It is NOT wired into any user-facing route
    and is NOT triggered by any scheduler.
    """
    _require_admin(request, x_admin_token)
    snap = _load_structure_brief_snapshot()
    cells = [
        _build_brief_cell(ticker, tf, snap)
        for ticker in STRUCTURE_BRIEF_TICKERS
        for tf in STRUCTURE_BRIEF_TFS
    ]
    return StructureBriefResponse(
        scope_statement=STRUCTURE_BRIEF_SCOPE_STATEMENT,
        cells=cells,
        ece_ceiling=STRUCTURE_BRIEF_ECE_CEILING,
    )
