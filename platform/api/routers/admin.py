"""
Admin router — model-routing dashboard backend.

All endpoints require the signed-in user to BE the admin: the
server-verified identity (Firebase token in firebase mode, IAP header in
iap mode) must equal `ADMIN_EMAIL`. There is no shared admin token —
identity is per-user, revocable, and attributable in a way a shared
secret pasted into sessionStorage is not.

Endpoints:
  GET    /api/admin/routes         — list per-role provider/model
  PUT    /api/admin/routes/{role}  — update one role
  GET    /api/admin/models         — catalog of priced models with
                                     credential availability
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
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
from api import auth as auth_state  # noqa: E402 — module ref: AUTH_MODE read at call time
from api.auth import configured_admin_email, current_user_email, is_admin_email  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _require_admin(request: Request) -> None:
    """Allow only a signed-in user holding the admin role.

    `current_user_email` returns the identity the auth middleware verified —
    the Firebase token's email in firebase mode, the IAP header in iap mode.
    It is None in open mode, so admin routes are closed there rather than
    falling back to a shared secret.

    `is_admin_email` is shared with /api/me so the flag the frontend renders
    and the check gating these routes cannot drift apart.
    """
    email = current_user_email(request)
    if not email:
        raise HTTPException(status_code=401, detail="sign-in required")
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="admin access required")


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
async def admin_list_routes(request: Request):
    _require_admin(request)
    rows = [_route_to_row(r) for r in list_routes()]
    return RouteListResponse(routes=rows)


@router.put("/routes/{role}", response_model=RouteRow)
async def admin_update_route(
    role: str,
    body: RouteUpdateRequest,
    request: Request,
):
    _require_admin(request)
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
async def admin_list_models(request: Request):
    _require_admin(request)
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
    request: Request
):
    """Dev-only readout of the strat-engine type model's structure predictions.

    Dev-only: this endpoint sits behind the existing admin auth (IAP email
    via ADMIN_EMAIL). It is NOT wired into any user-facing route
    and is NOT triggered by any scheduler.
    """
    _require_admin(request)
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


# ---------------------------------------------------------------------------
# Strat-engine on-demand prediction — admin-gated single-bar prediction.
#
# Wraps `gcp.research.strat_engine.strat_pred_serve.predict_one`. The model
# is FROZEN (calibration=none, 143-col enriched feature set). This endpoint
# does not retrain. It loads the model.pkl from GCS and queries Cloud SQL
# for the most recent labeled features.
#
# This endpoint is admin-gated. It is NOT wired into any user-facing route
# and is NOT triggered by any scheduler. Production triggers are blocked
# until a documented use case + a fresh validation pass land.
# ---------------------------------------------------------------------------


class StratEnginePredictRequest(BaseModel):
    ticker: str
    timeframe: str
    as_of_timestamp: Optional[str] = None  # ISO-8601; defaults to latest


class StratEnginePredictResponse(BaseModel):
    ticker: str
    timeframe: str
    ts: Optional[str] = None  # bar timestamp the prediction was based on
    available: bool
    top_class: Optional[str] = None
    top_prob: Optional[float] = None
    class_probs: dict = {}
    model_version: Optional[str] = None
    last_train_date: Optional[str] = None
    live_ece: Optional[float] = None
    muted: bool = False
    mute_reason: Optional[str] = None
    scope_statement: str
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Strat-engine model state — read-only per-cell artifact metadata.
#
# Powers the admin-side Model State Snapshot card. Identical data shape to
# the inline HTML section at /dev, but returned as JSON for the React UI.
# ---------------------------------------------------------------------------


class StratEngineCellState(BaseModel):
    ticker: str
    timeframe: str
    available: bool
    model_version: Optional[str] = None
    last_train_date: Optional[str] = None
    live_ece: Optional[float] = None


class StratEngineStateResponse(BaseModel):
    cells: list[StratEngineCellState]
    ece_ceiling: float = STRUCTURE_BRIEF_ECE_CEILING


def _strat_engine_state_cells() -> list[StratEngineCellState]:
    """Read each deployed cell's metrics.json + live-ECE snapshot from GCS.

    Best-effort: any cell whose metadata can't be loaded returns
    available=False. The Cloud Run image is responsible for having
    google-cloud-storage available (platform/Dockerfile installs it).

    `available=True` requires the top-level `model.pkl` pointer to exist —
    that's the artifact the predict endpoint actually serves. The Stage 4
    trainer writes a `metrics_<epoch>.json` for EVERY run including
    diagnostic/variant runs, but only LOCKED-default runs update the
    top-level `model.pkl`. So "metrics file exists" ≠ "served model exists";
    we anchor availability + metadata on `model.pkl` and match metrics to
    the served model by epoch proximity to its mtime.
    """
    rows: list[StratEngineCellState] = []
    try:
        from google.cloud import storage as _gcs
    except ImportError:
        return rows
    bucket_name = os.environ.get(
        "GCS_BUCKET", "adept-mountain-474619-d4-trading-data"
    )
    try:
        client = _gcs.Client()
        bucket = client.bucket(bucket_name)
    except Exception:
        return rows

    import json as _json
    snap_cells: dict = {}
    try:
        snap_blob = bucket.blob("research/strat_engine/structure_brief_latest.json")
        if snap_blob.exists():
            snap_cells = _json.loads(snap_blob.download_as_bytes()).get("cells", {})
    except Exception:
        snap_cells = {}

    for ticker in STRUCTURE_BRIEF_TICKERS:
        for tf in STRUCTURE_BRIEF_TFS:
            prefix = f"research/strat_engine/{ticker.lower()}_{tf}"
            row = StratEngineCellState(
                ticker=ticker, timeframe=tf, available=False,
            )
            # Production pointer check — this is the served artifact. If
            # it doesn't exist, the cell is genuinely unavailable; any
            # metrics_<epoch>.json present here would be from a diagnostic
            # run that did NOT update the served model.
            try:
                model_blob = bucket.blob(f"{prefix}/model.pkl")
                model_blob.reload()
                model_mtime = model_blob.updated  # raises if blob missing
            except Exception:
                rows.append(row)
                continue

            row.available = True
            # Match the metrics file to the served model by picking the
            # one whose epoch (encoded in filename) is closest to
            # model.pkl's mtime. Variant runs that wrote metrics after
            # the locked-default model.pkl was written will not be the
            # closest match, so they don't poison the metadata report.
            try:
                import re as _re
                model_epoch = int(model_mtime.timestamp())
                best = None
                best_delta: Optional[int] = None
                for b in client.list_blobs(bucket, prefix=f"{prefix}/metrics_"):
                    if not b.name.endswith(".json"):
                        continue
                    m = _re.search(r"/metrics_(\d{8,})\.json$", b.name)
                    if not m:
                        continue
                    epoch = int(m.group(1))
                    delta = abs(epoch - model_epoch)
                    if best_delta is None or delta < best_delta:
                        best = b
                        best_delta = delta
                if best is not None:
                    metrics = _json.loads(best.download_as_bytes())
                    row.model_version = (
                        metrics.get("run_id")
                        or metrics.get("config_signature")
                        or metrics.get("model_version")
                    )
                    if row.model_version is None:
                        m = _re.search(r"/metrics_(\d{8,})\.json$", best.name)
                        if m:
                            row.model_version = f"epoch-{m.group(1)}"
                    row.last_train_date = (
                        metrics.get("trained_at")
                        or metrics.get("computed_at")
                        or metrics.get("train_until")
                    )
                # Fall back to model.pkl mtime if no metrics matched
                if row.last_train_date is None:
                    row.last_train_date = model_mtime.isoformat()
                if row.model_version is None:
                    row.model_version = f"epoch-{model_epoch}"
            except Exception:
                pass

            ece = snap_cells.get(f"{ticker}_{tf}", {}).get("live_ece")
            if ece is not None:
                row.live_ece = float(ece)
            rows.append(row)
    return rows


@router.get("/strat-engine/state", response_model=StratEngineStateResponse)
async def admin_strat_engine_state(
    request: Request
):
    """Operator snapshot of the on-shelf strat-engine model state.

    Read-only: lists per-cell `model_version`, `last_train_date`, and
    `live_ece` for each deployed (ticker, timeframe). No model is loaded,
    no Cloud SQL query happens — this is GCS metadata only.
    """
    _require_admin(request)
    return StratEngineStateResponse(
        cells=_strat_engine_state_cells(),
        ece_ceiling=STRUCTURE_BRIEF_ECE_CEILING,
    )


@router.post(
    "/strat-engine/predict",
    response_model=StratEnginePredictResponse,
)
async def admin_strat_engine_predict(
    body: StratEnginePredictRequest,
    request: Request,
):
    """Run the frozen strat-engine type model for ONE bar.

    Body:
      { ticker: "IWM", timeframe: "15m", as_of_timestamp: "..." (optional) }

    Returns the 4-class distribution + metadata. When the rolling live
    ECE exceeds the per-cell ceiling, the prediction is muted (top_class
    null, mute_reason populated).
    """
    _require_admin(request)

    ticker = body.ticker.upper().strip()
    tf = body.timeframe.strip()
    if ticker not in STRUCTURE_BRIEF_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"ticker must be one of {STRUCTURE_BRIEF_TICKERS}; got {ticker!r}",
        )
    if tf not in STRUCTURE_BRIEF_TFS:
        raise HTTPException(
            status_code=400,
            detail=f"timeframe must be one of {STRUCTURE_BRIEF_TFS}; got {tf!r}",
        )

    # Lazy-import the predict path so the API container doesn't have
    # lightgbm + scikit-learn loaded into memory unless this endpoint
    # is actually hit. Heavy module-load only when needed.
    from gcp.database import get_engine  # noqa: PLC0415
    from gcp.research.strat_engine.strat_pred_serve import predict_one  # noqa: PLC0415
    import pandas as _pd  # noqa: PLC0415

    as_of = _pd.to_datetime(body.as_of_timestamp) if body.as_of_timestamp else None
    engine = get_engine()
    result = predict_one(engine, ticker, tf, as_of=as_of)
    return StratEnginePredictResponse(**result)


# ---------------------------------------------------------------------------
# PHASE 1 — Structure continuation (feature-flagged, behind-the-scenes).
#
# Surfaces the VALIDATED Strat-TYPE continuation probability — P(next bar
# keeps the current bar's Strat type) — as a READ-ONLY, FEATURE-FLAGGED
# field. This is the low-risk "unlock" step of the movement-statement build
# plan: the calibrated probability is made AVAILABLE behind the existing
# admin gate, but nothing renders to end users until a later phase flips
# the flag on.
#
# Scope guardrails baked in here, not left to the caller:
#   - Tickers: IWM / SPY / QQQ only (the validated cells).
#   - Timeframes: 5m and 15m ONLY. 30m is NOT cleared (QQQ 30m still fails
#     calibration) and is intentionally NOT exposed by this endpoint.
#   - Feature flag: STRUCTURE_CONTINUATION_ENABLED (env var, default OFF).
#     When OFF the endpoint returns 404 so the field is genuinely absent
#     for callers — no UI change, no behaviour change, until a later phase
#     sets the flag to a truthy value.
#   - Rule 3.7: when the model artifact is unavailable/unloadable, or the
#     cell is muted, OR no real current Strat type can be anchored, the
#     response carries status="UNAVAILABLE" + a reason and a NULL
#     continuation_prob. We NEVER fabricate a probability, 0, or 0.5.
# ---------------------------------------------------------------------------

# The validated, exposable cells for Phase 1. 30m is deliberately excluded.
STRUCTURE_CONTINUATION_TICKERS = ("IWM", "SPY", "QQQ")
STRUCTURE_CONTINUATION_TFS = ("5m", "15m")


def _structure_continuation_enabled() -> bool:
    """Feature flag — default OFF.

    Read at request time (not import time) so the flag can be flipped via
    env var / Cloud Run config without a code change. Accepts the common
    truthy spellings; everything else (including unset) is OFF.
    """
    raw = os.environ.get("STRUCTURE_CONTINUATION_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


class StructureContinuationRequest(BaseModel):
    ticker: str
    timeframe: str
    as_of_timestamp: Optional[str] = None  # ISO-8601; defaults to latest


class StructureContinuationResponse(BaseModel):
    # status is the explicit envelope discriminator (Rule 3.7):
    #   "OK"          — continuation_prob is a real calibrated probability
    #   "UNAVAILABLE" — model/feature/mute/current-type problem; prob is null
    status: str
    ticker: str
    timeframe: str
    ts: Optional[str] = None              # bar the prediction is based on
    current_type: Optional[str] = None    # current bar's Strat type (1/2U/2D/3)
    continuation_prob: Optional[float] = None  # P(next bar keeps current_type)
    model_version: Optional[str] = None
    last_train_date: Optional[str] = None
    live_ece: Optional[float] = None
    scope_statement: str
    reason: Optional[str] = None          # populated when status="UNAVAILABLE"


@router.post(
    "/strat-engine/structure-continuation",
    response_model=StructureContinuationResponse,
)
async def admin_structure_continuation(
    body: StructureContinuationRequest,
    request: Request,
):
    """Read-only, feature-flagged calibrated structure-continuation probability.

    Phase 1 of the movement-statement build plan. Behind the existing admin
    gate AND behind the STRUCTURE_CONTINUATION_ENABLED feature flag (default
    OFF). Exposes ONLY IWM/SPY/QQQ at 5m/15m. 30m is never exposed.

    When the flag is OFF the endpoint returns 404 (the field does not exist
    for callers). When ON, it returns the calibrated continuation
    probability, or an explicit UNAVAILABLE envelope when the model can't
    produce one — never a fabricated number (Rule 3.7).
    """
    _require_admin(request)

    # Feature flag — when OFF the endpoint behaves as if it doesn't exist.
    if not _structure_continuation_enabled():
        raise HTTPException(status_code=404, detail="Not Found")

    ticker = body.ticker.upper().strip()
    tf = body.timeframe.strip()
    if ticker not in STRUCTURE_CONTINUATION_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"ticker must be one of {STRUCTURE_CONTINUATION_TICKERS}; "
                f"got {ticker!r}"
            ),
        )
    if tf not in STRUCTURE_CONTINUATION_TFS:
        # 30m (and anything else) is intentionally rejected — not cleared.
        raise HTTPException(
            status_code=400,
            detail=(
                f"timeframe must be one of {STRUCTURE_CONTINUATION_TFS}; "
                f"got {tf!r} (30m is not exposed — calibration not cleared)"
            ),
        )

    # Lazy-import the heavy predict path only when the endpoint is hit.
    from gcp.database import get_engine  # noqa: PLC0415
    from gcp.research.strat_engine.strat_pred_serve import predict_one  # noqa: PLC0415
    import pandas as _pd  # noqa: PLC0415

    as_of = _pd.to_datetime(body.as_of_timestamp) if body.as_of_timestamp else None
    engine = get_engine()
    result = predict_one(engine, ticker, tf, as_of=as_of)

    base = {
        "ticker": result.get("ticker", ticker),
        "timeframe": result.get("timeframe", tf),
        "ts": result.get("ts"),
        "model_version": result.get("model_version"),
        "last_train_date": result.get("last_train_date"),
        "live_ece": result.get("live_ece"),
        "scope_statement": result.get(
            "scope_statement", STRUCTURE_BRIEF_SCOPE_STATEMENT
        ),
    }

    # Rule 3.7 — every failure mode returns an explicit UNAVAILABLE envelope
    # with a NULL continuation_prob, never a fabricated probability.
    cont = result.get("continuation_prob")
    current_type = result.get("current_type")
    if not result.get("available"):
        return StructureContinuationResponse(
            status="UNAVAILABLE",
            current_type=current_type,
            continuation_prob=None,
            reason=result.get("note") or "model unavailable",
            **base,
        )
    if result.get("muted"):
        return StructureContinuationResponse(
            status="UNAVAILABLE",
            current_type=current_type,
            continuation_prob=None,
            reason=result.get("mute_reason") or "model muted",
            **base,
        )
    if current_type is None or cont is None:
        return StructureContinuationResponse(
            status="UNAVAILABLE",
            current_type=current_type,
            continuation_prob=None,
            reason=(
                "no current Strat type to anchor continuation probability"
            ),
            **base,
        )

    return StructureContinuationResponse(
        status="OK",
        current_type=current_type,
        continuation_prob=float(cont),
        reason=None,
        **base,
    )


# ---------------------------------------------------------------------------
# User + role administration — the Admin page's "Users & roles" tab.
#
# Identity vs. authorization, kept in their existing homes rather than a new
# parallel store:
#   - IDENTITY (who exists, enabled/disabled, sign-in metadata) lives in
#     Firebase Auth. Listing and the disabled flag go through firebase-admin,
#     the same SDK api/auth.py already uses to verify tokens.
#   - AUTHORIZATION (what a verified identity may do) lives in the
#     `user_roles` table (gcp/schema.sql) — email-keyed, one role per
#     account, CHECK role IN ('admin', 'user'). `is_admin_email` reads it;
#     these endpoints are its write surface.
#
# The wire shape (uid-keyed rows with a `roles: string[]`) matches the
# frontend's useAdmin.ts hand-maintained contract. The array is capped at
# one role server-side because that is what the schema stores — a request
# with two roles is rejected loudly (422) rather than silently persisting
# only one of them (Rule 3.7: no partial writes reported as success).
#
# ADMIN_EMAIL remains the break-glass fallback (see api/auth.py): that
# account reads as admin regardless of the table, so removing its admin
# role or disabling it is refused with an explanation instead of a no-op
# that would lie about what changed.
# ---------------------------------------------------------------------------

# Mirrors the user_roles_role_valid CHECK constraint. If a role is ever
# added there, add it here in the same change set.
_ASSIGNABLE_ROLES = ("admin", "user")


class AdminUserRow(BaseModel):
    uid: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    roles: list[str] = []
    disabled: bool = False
    created_at: Optional[str] = None
    last_sign_in_at: Optional[str] = None


class AdminUsersResponse(BaseModel):
    users: list[AdminUserRow]
    available_roles: list[str]


class UserRolesUpdate(BaseModel):
    roles: list[str]


class UserStatusUpdate(BaseModel):
    disabled: bool


def _fb_auth():
    """The initialized firebase_admin.auth module.

    Reuses api.auth's one-time initializer (ADC on Cloud Run) so identity
    administration and token verification can never initialize the SDK two
    different ways. Indirection exists so tests can swap in a fake.
    """
    from api.auth import _ensure_firebase  # noqa: PLC0415

    _ensure_firebase()
    from firebase_admin import auth as fb_auth  # noqa: PLC0415

    return fb_auth


def _roles_query(sql: str, params: Optional[dict] = None):
    """Read from user_roles — raises on failure (caller turns it into 503)."""
    from gcp.database import query_to_dataframe_strict  # noqa: PLC0415

    return query_to_dataframe_strict(sql, params, timeout_s=10)


def _roles_exec(sql: str, params: Optional[dict] = None) -> int:
    from gcp.database import execute_sql  # noqa: PLC0415

    return execute_sql(sql, params)


def _ms_to_iso(ms: Optional[int]) -> Optional[str]:
    """Firebase user_metadata epoch-milliseconds -> ISO-8601 UTC, or None.

    None stays None (Rule 3.7 — a user who has never signed in must not be
    given a fabricated timestamp)."""
    if ms is None:
        return None
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _stored_roles() -> dict[str, str]:
    """email -> role for every user_roles row. One batched SELECT (Rule 0)."""
    df = _roles_query("SELECT email, role FROM user_roles")
    return {str(r["email"]): str(r["role"]) for _, r in df.iterrows()}


def _effective_roles(email: Optional[str], stored: dict[str, str]) -> list[str]:
    """The roles an account actually holds, as the authorization layer sees
    them: the stored table role, plus 'admin' for the ADMIN_EMAIL fallback
    account (is_admin_email grants it without a table row — hiding that here
    would render a live admin as role-less)."""
    roles: list[str] = []
    if email:
        stored_role = stored.get(email)
        if stored_role:
            roles.append(stored_role)
        if email == configured_admin_email() and "admin" not in roles:
            roles.append("admin")
    return roles


def _user_row(user, stored: dict[str, str]) -> AdminUserRow:
    email = (user.email or "").strip().lower() or None
    meta = getattr(user, "user_metadata", None)
    return AdminUserRow(
        uid=user.uid,
        email=email,
        display_name=user.display_name or None,
        roles=_effective_roles(email, stored),
        disabled=bool(user.disabled),
        created_at=_ms_to_iso(getattr(meta, "creation_timestamp", None)),
        last_sign_in_at=_ms_to_iso(getattr(meta, "last_sign_in_timestamp", None)),
    )


@router.get("/users", response_model=AdminUsersResponse)
async def admin_list_users(request: Request):
    """Every Firebase account + its stored role(s).

    Capacity (Rule 0): firebase-admin pages the directory at 1000/page and
    the roles map is ONE batched SELECT — no per-user queries. The account
    count on this platform is well under one page.
    """
    _require_admin(request)
    fb = _fb_auth()
    try:
        fb_users = list(fb.list_users().iterate_all())
    except Exception as exc:
        logger.error("firebase user listing failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="user directory temporarily unavailable"
        ) from exc
    try:
        stored = _stored_roles()
    except Exception as exc:
        logger.error("user_roles read failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="role store temporarily unavailable"
        ) from exc

    rows = sorted(
        (_user_row(u, stored) for u in fb_users),
        key=lambda r: (r.email or "", r.uid),
    )
    return AdminUsersResponse(users=rows, available_roles=list(_ASSIGNABLE_ROLES))


def _get_fb_user_or_404(fb, uid: str):
    try:
        return fb.get_user(uid)
    except fb.UserNotFoundError:
        raise HTTPException(status_code=404, detail="no such user")
    except Exception as exc:
        logger.error("firebase user lookup failed for %s: %s", uid, exc)
        raise HTTPException(
            status_code=503, detail="user directory temporarily unavailable"
        ) from exc


@router.put("/users/{uid}/roles", response_model=AdminUserRow)
async def admin_update_user_roles(uid: str, body: UserRolesUpdate, request: Request):
    """Replace an account's stored role.

    Accepts the frontend's `roles: string[]` shape; the schema stores at most
    ONE role per email (user_roles PK), so: [] deletes the row, ["user"] or
    ["admin"] upserts it, and two roles at once is a loud 422 — never a
    silent partial write.
    """
    _require_admin(request)

    roles = sorted({r.strip().lower() for r in body.roles if r.strip()})
    unknown = [r for r in roles if r not in _ASSIGNABLE_ROLES]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown role(s) {unknown}; available: {list(_ASSIGNABLE_ROLES)}",
        )
    if len(roles) > 1:
        raise HTTPException(
            status_code=422,
            detail="an account holds one role — send [], [\"user\"], or [\"admin\"]",
        )

    fb = _fb_auth()
    user = _get_fb_user_or_404(fb, uid)
    email = (user.email or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=422,
            detail="this account has no email; roles are keyed by email",
        )
    if email == configured_admin_email() and "admin" not in roles:
        raise HTTPException(
            status_code=409,
            detail=(
                "this account is ADMIN_EMAIL — its admin role comes from the "
                "service configuration (the break-glass fallback), not the "
                "role table, so it cannot be removed here"
            ),
        )

    try:
        if roles:
            _roles_exec(
                """
                INSERT INTO user_roles (email, role, created_by)
                VALUES (:email, :role, :created_by)
                ON CONFLICT (email) DO UPDATE
                    SET role = EXCLUDED.role, created_by = EXCLUDED.created_by
                """,
                {
                    "email": email,
                    "role": roles[0],
                    "created_by": current_user_email(request),
                },
            )
        else:
            _roles_exec(
                "DELETE FROM user_roles WHERE email = :email", {"email": email}
            )
        stored = _stored_roles()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("user_roles write failed for %s: %s", email, exc)
        raise HTTPException(
            status_code=503, detail="role store temporarily unavailable"
        ) from exc
    return _user_row(user, stored)


@router.put("/users/{uid}/status", response_model=AdminUserRow)
async def admin_update_user_status(uid: str, body: UserStatusUpdate, request: Request):
    """Enable or disable a Firebase account.

    Disabling also revokes the account's refresh tokens so its session ends
    at the next token refresh (Firebase ID tokens live up to an hour; the
    middleware verifies without a per-request revocation check, so that hour
    is the honest upper bound, not instant lockout).

    Two accounts are refused with 409 rather than disabled: your own (the
    UI you are using would lock itself out mid-session), and ADMIN_EMAIL
    (the break-glass account that must survive a bad role table).

    Refused outright in iap mode: there, authentication is the IAP header
    and neither the middleware nor _require_admin consults Firebase account
    status, so flipping the Firebase flag would report `disabled: true`
    while the person keeps full access — a fabricated success (Rule 3.7,
    Codex review PR #972). Access on an IAP deployment is managed in IAP /
    Cloud IAM, and the response says so.
    """
    _require_admin(request)
    if auth_state.AUTH_MODE == "iap":
        raise HTTPException(
            status_code=409,
            detail=(
                "this deployment authenticates at the IAP edge — Firebase "
                "account status does not govern access here; manage access "
                "in IAP / Cloud IAM instead"
            ),
        )
    fb = _fb_auth()
    user = _get_fb_user_or_404(fb, uid)
    email = (user.email or "").strip().lower()

    if body.disabled:
        caller = (current_user_email(request) or "").strip().lower()
        if email and email == caller:
            raise HTTPException(
                status_code=409, detail="you cannot disable your own account"
            )
        if email == configured_admin_email():
            raise HTTPException(
                status_code=409,
                detail="ADMIN_EMAIL is the break-glass account and cannot be disabled here",
            )

    try:
        updated = fb.update_user(uid, disabled=body.disabled)
        if body.disabled:
            fb.revoke_refresh_tokens(uid)
    except Exception as exc:
        logger.error("firebase status update failed for %s: %s", uid, exc)
        raise HTTPException(
            status_code=503, detail="user directory temporarily unavailable"
        ) from exc

    try:
        stored = _stored_roles()
    except Exception as exc:
        logger.error("user_roles read failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="role store temporarily unavailable"
        ) from exc
    return _user_row(updated, stored)


# ---------------------------------------------------------------------------
# Data sources — the Admin page's "Chart & report data" tab.
#
# GET aggregates the SAME freshness audit /api/health/freshness serves
# (scripts/audit_data_freshness.audit_all(), via routers/health.py's shared
# TTL cache) into one row per dataset, so the admin tab, the Dashboard
# widget, and the freshness-watchdog can never disagree about what "stale"
# means (one source of truth; zero extra Cloud SQL load beyond the cached
# audit).
#
# POST /{id}/refresh dispatches the dataset's Cloud Run fetcher job through
# the same google-cloud-run pattern gcp/discord_interactions/main.py uses.
# Only jobs in the explicit allowlist below are dispatchable — the job name
# is NEVER derived from client input beyond this registry lookup.
# ---------------------------------------------------------------------------


class AdminDataSourceRow(BaseModel):
    id: str
    label: str
    category: str
    status: str  # ok | stale | error | unknown (frontend contract)
    row_count: Optional[int] = None
    last_refreshed_at: Optional[str] = None
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    message: Optional[str] = None
    refreshable: bool = False


class AdminDataSourcesResponse(BaseModel):
    sources: list[AdminDataSourceRow]


class DataSourceRefreshResponse(BaseModel):
    id: str
    queued: bool
    job_id: Optional[str] = None


# Dataset registry: id == the audited table name (scripts/audit_data_freshness
# CHECKS). `job` is the Cloud Run Job an on-demand refresh dispatches; None
# means the dataset has NO safe on-demand refresh and the reason is stated to
# the caller rather than silently doing nothing:
#   - market_data_intraday: only writer is the MONTHLY AlphaVantage bulk
#     backfill — far too heavy (API quota + wall-clock) for a button.
#   - premarket_analysis / insight_reports: writers spend real LLM money per
#     run; enable deliberately, not from a reflexively clicked button.
#   - signal_alerts: written by the live market-hours monitor loop, which is
#     scheduler-owned — an ad-hoc second instance would double-fire alerts.
_DATA_SOURCES: dict[str, dict] = {
    "market_data_daily": {"label": "Daily OHLCV bars", "category": "charts", "job": "fetch-market-data"},
    "market_data_intraday": {"label": "Intraday 1-min bars", "category": "charts", "job": None,
                             "no_refresh_reason": "only writer is the monthly bulk backfill — too heavy for on-demand"},
    "strat_features_5m": {"label": "Strat features (5m)", "category": "charts", "job": "strat-engine"},
    "strat_features_15m": {"label": "Strat features (15m)", "category": "charts", "job": "strat-engine"},
    "strat_features_30m": {"label": "Strat features (30m)", "category": "charts", "job": "strat-engine"},
    "etf_options_snapshots": {"label": "Options chain snapshots", "category": "options", "job": "fetch-av-options-backfill"},
    "daily_rates": {"label": "Risk-free rates (FRED)", "category": "macro", "job": "fetch-fred-rates"},
    "economic_events": {"label": "Economic events calendar", "category": "reports", "job": "fetch-economic-events"},
    "earnings_calendar": {"label": "Earnings calendar", "category": "reports", "job": "fetch-earnings-calendar"},
    "premarket_analysis": {"label": "Premarket briefs", "category": "reports", "job": None,
                           "no_refresh_reason": "each run spends LLM budget — run premarket-brief deliberately"},
    "insight_reports": {"label": "AI insight reports", "category": "reports", "job": None,
                        "no_refresh_reason": "each run spends LLM budget — run insight-pipeline deliberately"},
    "signal_alerts": {"label": "Signal alerts", "category": "signals", "job": None,
                      "no_refresh_reason": "written by the live scheduler-owned monitor; an ad-hoc run would double-fire alerts"},
    "historical_signals": {"label": "Historical signals watchlist", "category": "signals", "job": "historical-signals-watchlist"},
}

def _base_table(label: str) -> str:
    """Fold the audit's diagnostic row labels into their base dataset id.

    audit_data_freshness emits derived labels for diagnostic passes on a
    dataset — "<table> [gap]" (gap scan) and "<table> [sanity]" (value
    sanity). Grouping by the raw string would surface each as a phantom
    unregistered source while the base dataset reads `ok` — a stale gap
    scan MUST roll into its dataset's status (Codex review, PR #972).
    "job_runs.<job> duration" rows are left as-is on purpose: they are job
    observability, not a dataset, and still surface as their own honest
    un-refreshable row rather than vanishing.
    """
    base = label.split(" [", 1)[0]
    return base if base in _DATA_SOURCES else label


# Frontend contract is ok|stale|error|unknown; the audit emits
# ok|warn|stale|unknown|skipped. warn maps to stale (it is an
# attention state, and the lag detail rides in `message`); skipped
# maps to unknown. Severity order picks the aggregate per-dataset
# status across its per-ticker rows.
_AUDIT_TO_WIRE_STATUS = {"ok": "ok", "warn": "stale", "stale": "stale",
                         "unknown": "unknown", "skipped": "unknown"}
_STATUS_SEVERITY = {"ok": 0, "unknown": 1, "stale": 2, "error": 3}


def _aggregate_source(source_id: str, entry: dict, rows: list[dict]) -> AdminDataSourceRow:
    """Fold the audit's per-(table, ticker) rows into one dataset row.

    Rule 3.7: a dataset with no audit rows is `unknown` with an explicit
    message, `row_count` is None unless EVERY member reported a count (a
    partial sum would read as a real total), and timestamps stay None when
    the audit has none.
    """
    statuses: list[str] = []
    messages: list[str] = []
    last_row_ats: list[str] = []
    counts: list[Optional[int]] = []
    for r in rows:
        wire = _AUDIT_TO_WIRE_STATUS.get(r.get("status") or "unknown", "unknown")
        statuses.append(wire)
        # A folded diagnostic row ("market_data_daily [gap]") contributes its
        # STATUS and message to the dataset, but not counts or timestamps —
        # a gap scan is not a data member, and folding its Nones in would
        # blank out the dataset's real row_count/last_refreshed_at.
        is_diagnostic = str(r.get("table") or source_id) != source_id
        if wire != "ok":
            # The raw audit label keeps a folded diagnostic identifiable.
            who = r.get("ticker") or str(r.get("table") or source_id)
            lag = r.get("lag_hours")
            allowed = r.get("expected_max_hours")
            detail = f"{who}: {r.get('status')}"
            if lag is not None and allowed is not None:
                detail += f" (lag {lag:.1f}h, allowed {allowed}h)"
            messages.append(detail)
        if is_diagnostic:
            continue
        if r.get("last_row_at"):
            last_row_ats.append(str(r["last_row_at"]))
        counts.append(r.get("row_count_recent"))

    if not rows:
        status = "unknown"
        message: Optional[str] = "not covered by the freshness audit"
    else:
        status = max(statuses, key=lambda s: _STATUS_SEVERITY[s])
        message = "; ".join(messages) or None

    last_at = max(last_row_ats) if last_row_ats else None
    row_count = (
        int(sum(counts)) if counts and all(c is not None for c in counts) else None
    )

    return AdminDataSourceRow(
        id=source_id,
        label=entry.get("label", source_id),
        category=entry.get("category", "other"),
        status=status,
        row_count=row_count,
        last_refreshed_at=last_at,
        coverage_start=None,  # not computed by the audit — None, never a guess
        coverage_end=last_at,
        message=message,
        refreshable=entry.get("job") is not None,
    )


@router.get("/data-sources", response_model=AdminDataSourcesResponse)
async def admin_list_data_sources(request: Request):
    """Per-dataset freshness/coverage, aggregated from the shared audit.

    Capacity (Rule 0): zero direct Cloud SQL queries here — the audit runs
    behind routers/health.py's 5-minute TTL cache, so this endpoint is a
    pure in-memory regrouping of that report.
    """
    _require_admin(request)
    from .health import freshness_report_dict  # noqa: PLC0415 — shared cache

    report = freshness_report_dict()  # raises HTTPException on audit failure
    by_table: dict[str, list[dict]] = {}
    for r in report.get("tables", []):
        by_table.setdefault(_base_table(str(r.get("table"))), []).append(r)

    sources = [
        _aggregate_source(sid, entry, by_table.get(sid, []))
        for sid, entry in _DATA_SOURCES.items()
    ]
    # Audited tables the registry doesn't know yet still show up (honest,
    # un-labeled) instead of silently vanishing from the admin view.
    for table, rows in by_table.items():
        if table not in _DATA_SOURCES:
            sources.append(
                _aggregate_source(table, {"label": table, "category": "other", "job": None}, rows)
            )
    return AdminDataSourcesResponse(sources=sources)


# One dispatch per job per cooldown window — a double-clicked button must
# not launch two executions of the same fetcher. The lease lives in Cloud
# SQL, NOT in process memory: the service runs up to 5 instances
# (platform/deploy.sh --max-instances 5), so two requests routed to
# different instances would each see an empty in-process map and dispatch
# twice (Codex review, PR #972). One indexed upsert per accepted press.
_REFRESH_COOLDOWN_S = 60


def _acquire_refresh_lease(job_name: str, cooldown_s: int) -> bool:
    """Atomically claim the right to dispatch `job_name` — cross-instance.

    ONE statement: insert the lease row, or take it over only when the
    previous dispatch is older than the cooldown. RETURNING tells us
    whether we won; a concurrent press on another instance loses the
    upsert race and gets False. Raises on DB failure — the endpoint turns
    that into a loud 503 rather than dispatching without the cost guard.
    """
    from gcp.database import get_engine  # noqa: PLC0415 — lazy: sqlalchemy is heavy
    from sqlalchemy import text  # noqa: PLC0415

    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO admin_refresh_leases (job_name, dispatched_at)
                VALUES (:job, NOW())
                ON CONFLICT (job_name) DO UPDATE SET dispatched_at = NOW()
                WHERE admin_refresh_leases.dispatched_at
                      < NOW() - make_interval(secs => :cooldown)
                RETURNING job_name
                """
            ),
            {"job": job_name, "cooldown": cooldown_s},
        ).first()
    return row is not None


def _release_refresh_lease(job_name: str) -> None:
    """Give the lease back after a FAILED dispatch so the retry isn't
    locked out for the full cooldown. Ages the row rather than deleting it
    (a delete would race a concurrent successful acquire). Raises on DB
    failure; the caller treats release as best-effort cleanup."""
    from gcp.database import get_engine  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE admin_refresh_leases
                SET dispatched_at = NOW() - make_interval(secs => :cooldown)
                WHERE job_name = :job
                """
            ),
            {"job": job_name, "cooldown": _REFRESH_COOLDOWN_S + 1},
        )


def _run_refresh_job(job_name: str) -> Optional[str]:
    """Dispatch one Cloud Run Job execution; return its execution id.

    Same client + request shape as gcp/discord_interactions/main.py's
    `execute_cloud_run_job` (`run_job(request=RunJobRequest(...))` — the
    kwarg form raises TypeError on the v2 client). Fire-and-forget: the
    operation is NOT awaited; the admin tab re-polls freshness instead.
    Raises on failure — the endpoint turns that into a loud 503.
    """
    from google.cloud import run_v2  # noqa: PLC0415

    # platform/deploy.sh exports GCP_PROJECT_ID (and, since the Codex review
    # of PR #972, GCP_REGION) — read those so a PROJECT_ID/REGION-overridden
    # deployment targets ITS OWN jobs, never the hardcoded prod defaults.
    # GCP_PROJECT stays first for parity with gcp/discord_interactions.
    project = (
        os.environ.get("GCP_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
        or "adept-mountain-474619-d4"
    )
    region = os.environ.get("GCP_REGION") or "us-east1"
    client = run_v2.JobsClient()
    op = client.run_job(request=run_v2.RunJobRequest(
        name=f"projects/{project}/locations/{region}/jobs/{job_name}",
    ))
    try:
        # run_job's long-running operation carries the Execution as metadata;
        # its name ends in the execution id.
        return str(op.metadata.name).rsplit("/", 1)[-1]
    except Exception:
        # Losing the id is cosmetic (the dispatch already succeeded) — the
        # frontend renders job_id as nullable.
        return None


@router.post("/data-sources/{source_id}/refresh", response_model=DataSourceRefreshResponse)
async def admin_refresh_data_source(source_id: str, request: Request):
    """Queue the dataset's Cloud Run fetcher job.

    404 unknown dataset · 409 dataset with no on-demand job (the reason is
    spelled out) · 429 inside the per-job cooldown · 503 when the dispatch
    itself fails (missing IAM, missing client lib — logged, never silent).

    Cost (Rule 0): one Cloud Run Job execution per accepted call — the same
    workload the daily scheduler already runs, and the cooldown bounds the
    worst case to one execution per job per minute.
    """
    _require_admin(request)
    entry = _DATA_SOURCES.get(source_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown data source {source_id!r}")
    job = entry.get("job")
    if not job:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{source_id} has no on-demand refresh: "
                f"{entry.get('no_refresh_reason', 'not refreshable')}"
            ),
        )

    try:
        acquired = _acquire_refresh_lease(job, _REFRESH_COOLDOWN_S)
    except Exception as exc:
        # No lease means no cost guard — refuse loudly rather than dispatch
        # unguarded (Rule 3.7: never a silent degrade of a documented guard).
        logger.error("refresh lease acquire failed for %s (%s): %s", source_id, job, exc)
        raise HTTPException(
            status_code=503,
            detail="refresh coordination unavailable — see server logs",
        ) from exc
    if not acquired:
        raise HTTPException(
            status_code=429,
            detail=f"{job} was dispatched moments ago — wait {_REFRESH_COOLDOWN_S}s between refreshes",
        )

    try:
        execution_id = _run_refresh_job(job)
    except Exception as exc:
        logger.error("refresh dispatch failed for %s (%s): %s", source_id, job, exc)
        try:
            _release_refresh_lease(job)
        except Exception:  # cleanup — original error already propagating
            logger.warning("refresh lease release failed for %s", job)
        raise HTTPException(
            status_code=503,
            detail=f"could not queue {job} — see server logs",
        ) from exc
    logger.info("admin refresh: %s -> job %s execution %s (by %s)",
                source_id, job, execution_id, current_user_email(request))
    return DataSourceRefreshResponse(id=source_id, queued=True, job_id=execution_id)
