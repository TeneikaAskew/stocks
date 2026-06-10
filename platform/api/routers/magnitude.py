"""FastAPI router for the live magnitude predictions surface.

Phase C of magnitude-engine productionization. Exposes per-bar bucket
probabilities from `magnitude_per_bar_predictions` to UI / agent
consumers.

**Gate-7 caveat carried through in the response envelope:** the
predictions are a SIZING / FILTERING / STRIKE-SELECTION signal, not a
standalone non-directional trade signal. See
`docs/MAGNITUDE_ENGINE_RESULTS.md` §gate-7 for the verdict context.
Consumers must respect the `usage_guidance` and `not_for` fields and
not interpret high p_EXPLOSIVE as a buy-straddle signal on its own.

Endpoints:

    GET /api/magnitude/{ticker}/{tf}/latest
        Latest scored bar for (ticker, tf). Returns the 4-bucket
        distribution + model_version + ts.

    GET /api/magnitude/{ticker}/{tf}/at/{ts}
        Specific (ticker, tf, ts) bar. 404 if no prediction exists at
        that ts. NEVER fabricates a uniform distribution (CLAUDE.md §3.7
        no silent fallback).
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Path as FastAPIPath
from pydantic import BaseModel

# Project root on sys.path so we can import lib.* / gcp.* — same
# pattern other routers use.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from gcp.database import query_to_dataframe  # noqa: E402

log = logging.getLogger(__name__)

router = APIRouter()


# Gate-7 caveat embedded in every response so a consumer who only
# reads the JSON sees the constraint without needing to read the docs.
_USAGE_GUIDANCE = (
    "Sizing / filtering / strike-selection signal only. Magnitude_engine "
    "FAILED gate-7 (realized/implied move ratio < 1.25 in 0 of 23 "
    "IV-covered folds) — predictions identify volatility CLUSTERS the "
    "option chain has already priced in. Use to size up/down or filter "
    "directional setups, never as a standalone non-directional trade."
)
_NOT_FOR = [
    "standalone long-straddle / long-strangle entry decisions",
    "non-directional vol-arbitrage",
    "implied-vol mispricing claims",
]
_DOCS_REF = "docs/MAGNITUDE_ENGINE_RESULTS.md"


class BucketProbabilities(BaseModel):
    p_tight: float
    p_normal: float
    p_expanded: float
    p_explosive: float


class MagnitudePrediction(BaseModel):
    ticker: str
    tf: str
    ts: datetime
    probabilities: BucketProbabilities
    pred_bucket: int           # 0..3 (TIGHT/NORMAL/EXPANDED/EXPLOSIVE)
    pred_bucket_label: str
    max_proba: float
    model_version: str
    source: str                # 'walk_forward' | 'inference'
    computed_at: datetime
    usage_guidance: str
    not_for: list[str]
    docs_ref: str


_BUCKET_LABELS = ("TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE")


def _row_to_response(row: dict) -> MagnitudePrediction:
    return MagnitudePrediction(
        ticker=row["ticker"], tf=row["tf"], ts=row["ts"],
        probabilities=BucketProbabilities(
            p_tight=row["p_tight"], p_normal=row["p_normal"],
            p_expanded=row["p_expanded"], p_explosive=row["p_explosive"],
        ),
        pred_bucket=int(row["pred_bucket"]),
        pred_bucket_label=_BUCKET_LABELS[int(row["pred_bucket"])],
        max_proba=float(row["max_proba"]),
        model_version=row["model_version"],
        source=row["source"],
        computed_at=row["computed_at"],
        usage_guidance=_USAGE_GUIDANCE,
        not_for=_NOT_FOR,
        docs_ref=_DOCS_REF,
    )


@router.get(
    "/api/magnitude/{ticker}/{tf}/latest",
    response_model=MagnitudePrediction,
    summary="Latest magnitude prediction for (ticker, tf)",
)
def get_latest_prediction(
    ticker: str = FastAPIPath(..., min_length=1, max_length=10,
                                 pattern=r"^[A-Z0-9.\-]+$"),
    tf: str = FastAPIPath(..., min_length=2, max_length=5,
                              pattern=r"^[0-9]+[mhd]$"),
) -> MagnitudePrediction:
    """Return the most-recent prediction for this (ticker, tf).

    404 if the cell has no predictions yet (e.g. inference job hasn't
    run, or this ticker/tf isn't covered). NEVER fabricates a uniform
    distribution — CLAUDE.md §3.7 explicit fail-loud envelope.
    """
    ticker = ticker.upper()
    # PRIMARY KEY (ticker, tf, ts, model_version) intentionally allows
    # multiple model versions per (ticker, tf, ts). Order by ts DESC
    # gets the latest bar; computed_at DESC is the model-version
    # tiebreaker so a fresher inference row beats a stale walk_forward
    # backfill for the same timestamp. Without this tiebreaker,
    # Postgres can return any row among the tie — Codex P2 on PR #597.
    sql = (
        "SELECT ticker, tf, ts, p_tight, p_normal, p_expanded, "
        "p_explosive, pred_bucket, max_proba, model_version, source, "
        "computed_at "
        "FROM magnitude_per_bar_predictions "
        f"WHERE ticker = '{ticker}' AND tf = '{tf}' "
        "ORDER BY ts DESC, computed_at DESC LIMIT 1"
    )
    df = query_to_dataframe(sql)
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=(f"No magnitude predictions for {ticker}:{tf}. "
                    "Cell may not be covered or the inference job hasn't "
                    "run yet. See "
                    "gcp/research/magnitude_engine/mag_inference.py."),
        )
    return _row_to_response(df.iloc[0].to_dict())


@router.get(
    "/api/magnitude/{ticker}/{tf}/at/{ts}",
    response_model=MagnitudePrediction,
    summary="Magnitude prediction for a specific bar",
)
def get_prediction_at(
    ts: datetime = FastAPIPath(..., description="ISO 8601 timestamp"),
    ticker: str = FastAPIPath(..., min_length=1, max_length=10,
                                 pattern=r"^[A-Z0-9.\-]+$"),
    tf: str = FastAPIPath(..., min_length=2, max_length=5,
                              pattern=r"^[0-9]+[mhd]$"),
) -> MagnitudePrediction:
    """Return the prediction for exactly this (ticker, tf, ts).

    404 if no row exists. We do not interpolate between nearby bars
    and do not return a uniform fallback distribution — both would
    silently mislead consumers about model confidence.
    """
    ticker = ticker.upper()
    # When multiple model_versions exist for the same bar, prefer the
    # most-recent computed_at — that's the freshest inference, while
    # older walk_forward backfill rows stay queryable via direct SQL.
    sql = (
        "SELECT ticker, tf, ts, p_tight, p_normal, p_expanded, "
        "p_explosive, pred_bucket, max_proba, model_version, source, "
        "computed_at "
        "FROM magnitude_per_bar_predictions "
        f"WHERE ticker = '{ticker}' AND tf = '{tf}' "
        f"  AND ts = '{ts.isoformat()}' "
        "ORDER BY computed_at DESC LIMIT 1"
    )
    df = query_to_dataframe(sql)
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=(f"No prediction at {ts.isoformat()} for {ticker}:{tf}."
                    " This bar was never scored — either inference "
                    "skipped it (NaN features), the bar predates "
                    "magnitude_per_bar_predictions coverage, or the "
                    "cell isn't enabled."),
        )
    return _row_to_response(df.iloc[0].to_dict())
