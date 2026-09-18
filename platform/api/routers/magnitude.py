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
    # 0..3 (TIGHT/NORMAL/EXPANDED/EXPLOSIVE). The served DECISION, not argmax:
    # the highest bucket whose probability clears DECISION_LIFT_MIN times its
    # class prior, else TIGHT (mag_pred_train.decide_bucket, 2026-09-14).
    pred_bucket: int
    pred_bucket_label: str
    # Probability of the SERVED bucket (pred_bucket). Under the decision
    # rule a tail call is made at P >= 2x its prior, so this is often the
    # smaller number on the row: EXPLOSIVE at 0.08 against a 0.026 prior.
    pred_bucket_proba: float
    # Probability of the argmax bucket, which is TIGHT on nearly every bar
    # of a calibrated model. Kept as the drift-monitoring metric
    # (audit_magnitude_drift averages it); it is NOT the confidence of
    # pred_bucket and must not be rendered beside it as if it were
    # (Codex P1 on #1117).
    max_proba: float
    model_version: str
    source: str                # always 'inference' on this surface
    # Always 'lift' on this surface: the rule pred_bucket was made under.
    # Rows tagged 'argmax' (scored before 2026-09-15) are never served here.
    decision_rule: str
    computed_at: datetime
    usage_guidance: str
    not_for: list[str]
    docs_ref: str


_BUCKET_LABELS = ("TIGHT", "NORMAL", "EXPANDED", "EXPLOSIVE")
# Row column holding each bucket's probability, indexed by pred_bucket.
_BUCKET_PROBA_COLS = ("p_tight", "p_normal", "p_expanded", "p_explosive")


def _row_to_response(row: dict) -> MagnitudePrediction:
    bucket = int(row["pred_bucket"])
    return MagnitudePrediction(
        ticker=row["ticker"], tf=row["tf"], ts=row["ts"],
        probabilities=BucketProbabilities(
            p_tight=row["p_tight"], p_normal=row["p_normal"],
            p_expanded=row["p_expanded"], p_explosive=row["p_explosive"],
        ),
        pred_bucket=bucket,
        pred_bucket_label=_BUCKET_LABELS[bucket],
        pred_bucket_proba=float(row[_BUCKET_PROBA_COLS[bucket]]),
        max_proba=float(row["max_proba"]),
        model_version=row["model_version"],
        source=row["source"],
        decision_rule=row["decision_rule"],
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
    # Live reads serve INFERENCE rows scored under the served DECISION RULE
    # only (decision_rule = 'lift'). Rows from before 2026-09-15 hold argmax
    # in pred_bucket under the same column and model_version; presenting one
    # as a decision would mislabel it (Codex P1 on #1117). Those rows are
    # tagged 'argmax' and stay queryable by direct SQL.
    # The walk-forward harness once wrote
    # every phase0 fold's test predictions into the same table under
    # source='walk_forward' (mag_walk_forward._persist_predictions_table),
    # for promoted AND blocked candidates alike, with `ts` reaching the
    # newest labelled bar. Without the filter a research run would beat the
    # served model here on the strength of a fresher computed_at (Codex P1
    # on #1117). PRIMARY KEY (ticker, tf, ts, model_version) still allows
    # several inference versions per bar: ts DESC gets the latest bar and
    # computed_at DESC breaks the tie toward the freshest write, since
    # Postgres can otherwise return any row among the tie (Codex P2 on #597).
    sql = (
        "SELECT ticker, tf, ts, p_tight, p_normal, p_expanded, "
        "p_explosive, pred_bucket, max_proba, model_version, source, "
        "decision_rule, computed_at "
        "FROM magnitude_per_bar_predictions "
        f"WHERE ticker = '{ticker}' AND tf = '{tf}' "
        "  AND source = 'inference' AND decision_rule = 'lift' "
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
    # Inference rows under the served decision rule only, for the reasons
    # given on /latest; a bar scored only under argmax (before 2026-09-15)
    # is a 404 here, not a mislabeled decision. When several inference
    # versions scored the same bar, prefer the most recent computed_at, the
    # freshest write.
    sql = (
        "SELECT ticker, tf, ts, p_tight, p_normal, p_expanded, "
        "p_explosive, pred_bucket, max_proba, model_version, source, "
        "decision_rule, computed_at "
        "FROM magnitude_per_bar_predictions "
        f"WHERE ticker = '{ticker}' AND tf = '{tf}' "
        f"  AND ts = '{ts.isoformat()}' "
        "  AND source = 'inference' AND decision_rule = 'lift' "
        "ORDER BY computed_at DESC LIMIT 1"
    )
    df = query_to_dataframe(sql)
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=(f"No prediction at {ts.isoformat()} for {ticker}:{tf} "
                    "under the served decision rule. Either inference "
                    "skipped the bar (NaN features), the bar predates "
                    "magnitude_per_bar_predictions coverage or the "
                    "2026-09-15 decision rule (earlier rows hold argmax and "
                    "are not served as decisions), or the cell isn't "
                    "enabled."),
        )
    return _row_to_response(df.iloc[0].to_dict())
