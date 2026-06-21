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
    request: Request, x_admin_token: Optional[str] = Header(None)
):
    """Operator snapshot of the on-shelf strat-engine model state.

    Read-only: lists per-cell `model_version`, `last_train_date`, and
    `live_ece` for each deployed (ticker, timeframe). No model is loaded,
    no Cloud SQL query happens — this is GCS metadata only.
    """
    _require_admin(request, x_admin_token)
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
    x_admin_token: Optional[str] = Header(None),
):
    """Run the frozen strat-engine type model for ONE bar.

    Body:
      { ticker: "IWM", timeframe: "15m", as_of_timestamp: "..." (optional) }

    Returns the 4-class distribution + metadata. When the rolling live
    ECE exceeds the per-cell ceiling, the prediction is muted (top_class
    null, mute_reason populated).
    """
    _require_admin(request, x_admin_token)

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
    x_admin_token: Optional[str] = Header(None),
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
    _require_admin(request, x_admin_token)

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
