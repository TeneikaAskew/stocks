"""Per-user watchlist router.

Endpoints:
  GET /api/me/watchlist  - the signed-in caller's active watchlist rows

The caller is identified by the verified Firebase uid (api.auth.current_user_identity).
With no identity (open or iap mode, or a rejected token) the route answers 401
"sign in required" before any database call. The read goes through
query_to_dataframe_strict, so a Cloud SQL outage is a 503 via
api.http_errors.unavailable, never an empty list; a defect (KeyError,
TypeError) is not an outage and stays a 500. An empty frame is a true 200
with `tickers: []`. Missing name, exchange, asset_type and last_daily_bar are
null, never an empty string (CLAUDE.md Rule 3.7).
"""
import logging
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from api.auth import UserIdentity, current_user_identity
from api.http_errors import unavailable
from api.schemas import MeWatchlistResponse, MeWatchlistRow
from gcp.database import query_to_dataframe_strict

logger = logging.getLogger(__name__)
router = APIRouter()

ME_WATCHLIST_SQL = """SELECT u.ticker, u.added_at, u.source, ti.name, ti.exchange, ti.asset_type, (SELECT MAX(m.date) FROM market_data_daily m WHERE m.ticker = u.ticker AND m.close IS NOT NULL) AS last_daily_bar FROM user_watchlists u LEFT JOIN ticker_info ti ON ti.ticker = u.ticker WHERE u.owner_uid = :owner_uid AND u.removed_at IS NULL ORDER BY u.added_at, u.ticker"""


def _require_identity(request: Request) -> UserIdentity:
    identity = current_user_identity(request)
    if identity is None:
        raise HTTPException(status_code=401, detail="sign in required")
    return identity


def _none_if_missing(value):
    """pandas NaN, NaT and None all become None; anything else passes through."""
    return None if pd.isna(value) else value


def _iso_date(value):
    value = _none_if_missing(value)
    if value is None:
        return None
    if hasattr(value, "date") and callable(value.date):
        value = value.date()
    return value.isoformat()


def _list(identity: UserIdentity) -> MeWatchlistResponse:
    try:
        df = query_to_dataframe_strict(ME_WATCHLIST_SQL, {"owner_uid": identity.uid})
    except Exception as exc:
        unavailable(f"watchlist read from Cloud SQL failed: {exc}", exc)

    rows = [
        MeWatchlistRow(
            ticker=rec["ticker"],
            added_at=pd.Timestamp(rec["added_at"]).isoformat(),
            source=_none_if_missing(rec["source"]),
            name=_none_if_missing(rec["name"]),
            exchange=_none_if_missing(rec["exchange"]),
            asset_type=_none_if_missing(rec["asset_type"]),
            last_daily_bar=_iso_date(rec["last_daily_bar"]),
        )
        for rec in df.to_dict("records")
    ]
    return MeWatchlistResponse(
        owner_email=identity.email,
        as_of=datetime.now(timezone.utc).isoformat(),
        tickers=rows,
    )


@router.get("/api/me/watchlist", response_model=MeWatchlistResponse)
def get_me_watchlist(request: Request) -> MeWatchlistResponse:
    """List the caller's active watchlist (401 without a signed-in identity,
    503 on a Cloud SQL outage; a defect stays a 500)."""
    return _list(_require_identity(request))
