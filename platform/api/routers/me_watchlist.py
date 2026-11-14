"""Per-user watchlist router.

Endpoints:
  GET    /api/me/watchlist           - the signed-in caller's active watchlist rows
  POST   /api/me/watchlist           - add a ticker (one shared watched_tickers row)
  DELETE /api/me/watchlist/{ticker}  - soft-remove a ticker from the caller's list

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
import re
from datetime import datetime, timezone

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from api.auth import UserIdentity, current_user_identity
from api.http_errors import unavailable
from api.schemas import (
    MeWatchlistAddRequest,
    MeWatchlistRemoveResponse,
    MeWatchlistResponse,
    MeWatchlistRow,
)
from gcp.database import get_engine, query_to_dataframe_strict

logger = logging.getLogger(__name__)
router = APIRouter()

ME_WATCHLIST_SQL = """SELECT u.ticker, u.added_at, u.source, ti.name, ti.exchange, ti.asset_type, (SELECT MAX(m.date) FROM market_data_daily m WHERE m.ticker = u.ticker AND m.close IS NOT NULL) AS last_daily_bar FROM user_watchlists u LEFT JOIN ticker_info ti ON ti.ticker = u.ticker WHERE u.owner_uid = :owner_uid AND u.removed_at IS NULL ORDER BY u.added_at, u.ticker"""

TICKER_RE = re.compile(r"^[A-Z0-9.]{1,10}$")
MAX_ACTIVE_ROWS = 200
ME_WATCHLIST_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext(:owner_uid))"
ME_WATCHLIST_COUNT_SQL = "SELECT COUNT(*) AS n FROM user_watchlists WHERE owner_uid = :owner_uid AND removed_at IS NULL"
WATCHED_TICKER_INSERT_SQL = "INSERT INTO watched_tickers (ticker) VALUES (:ticker) ON CONFLICT (ticker) DO NOTHING"
USER_WATCHLIST_UPSERT_SQL = "INSERT INTO user_watchlists (owner_uid, owner_email, ticker, source) VALUES (:owner_uid, :owner_email, :ticker, :source) ON CONFLICT (owner_uid, ticker) DO UPDATE SET removed_at = NULL, source = EXCLUDED.source, owner_email = EXCLUDED.owner_email"
USER_WATCHLIST_REMOVE_SQL = "UPDATE user_watchlists SET removed_at = NOW() WHERE owner_uid = :owner_uid AND ticker = :ticker AND removed_at IS NULL"


def _normalize_ticker(raw: str) -> str:
    ticker = raw.strip().upper()
    if not TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="invalid ticker")
    return ticker


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


@router.post("/api/me/watchlist", response_model=MeWatchlistResponse)
def add_me_watchlist(body: MeWatchlistAddRequest, request: Request) -> MeWatchlistResponse:
    """Add a ticker to the caller's watchlist and answer the updated list.

    One transaction: the per-owner advisory lock first (adds for one owner
    serialize, so the cap cannot be raced), then the count (409 at the cap),
    the shared ticker row, and the membership upsert. A re-add clears
    removed_at and never rewrites added_at. 401 without an identity, 422 for a
    bad ticker, 503 on a Cloud SQL outage; a defect stays a 500.
    """
    identity = _require_identity(request)
    ticker = _normalize_ticker(body.ticker)
    try:
        with get_engine().begin() as conn:
            conn.execute(text(ME_WATCHLIST_LOCK_SQL), {"owner_uid": identity.uid})
            active = conn.execute(
                text(ME_WATCHLIST_COUNT_SQL), {"owner_uid": identity.uid}
            ).scalar()
            if active >= MAX_ACTIVE_ROWS:
                raise HTTPException(status_code=409, detail="watchlist full")
            conn.execute(text(WATCHED_TICKER_INSERT_SQL), {"ticker": ticker})
            conn.execute(
                text(USER_WATCHLIST_UPSERT_SQL),
                {
                    "owner_uid": identity.uid,
                    "owner_email": identity.email,
                    "ticker": ticker,
                    "source": body.source,
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        unavailable(f"watchlist write to Cloud SQL failed: {exc}", exc)
    return _list(identity)


@router.delete("/api/me/watchlist/{ticker}", response_model=MeWatchlistRemoveResponse)
def remove_me_watchlist(ticker: str, request: Request) -> MeWatchlistRemoveResponse:
    """Soft-remove a ticker from the caller's watchlist and answer the list.

    404 when the caller has no active row for it, 422 for a bad ticker, 401
    without an identity, 503 on a Cloud SQL outage; a defect stays a 500.
    """
    identity = _require_identity(request)
    ticker = _normalize_ticker(ticker)
    try:
        with get_engine().begin() as conn:
            result = conn.execute(
                text(USER_WATCHLIST_REMOVE_SQL),
                {"owner_uid": identity.uid, "ticker": ticker},
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="not on your watchlist")
    except HTTPException:
        raise
    except Exception as exc:
        unavailable(f"watchlist write to Cloud SQL failed: {exc}", exc)
    return MeWatchlistRemoveResponse(**_list(identity).model_dump(), removed=True)
