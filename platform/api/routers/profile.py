"""Profile router — per-user account settings beyond appearance.

Endpoints:
  GET /api/me/profile — the signed-in user's stored profile.
      404 when the user has never saved one: the frontend treats that as a
      legitimate "nothing stored yet" state (solyra useProfile.fetchProfile
      returns null on 404) and renders empty fields, so this endpoint never
      fabricates defaults (CLAUDE.md Rule 3.7 — a missing value must stay
      distinguishable from a real choice).
  PUT /api/me/profile — partial update: any subset of the twelve fields.
      An explicit null CLEARS a field; an omitted field is left untouched.
      Returns the full stored object after the update. Unknown fields and
      unknown enum values are rejected with 422.

Contract: the response shape is hand-mirrored by solyra's
src/types/profile.ts (twelve nullable snake_case fields) and narrowed by its
useProfile.sanitizeProfile. Nothing mechanically ties the two repos
together, so a change to either side must land on both in the same change
set (solyra CLAUDE.md Rule 6). The Settings page PUTs only the diff of
changed fields (profileDiff), which is exactly the partial-update semantics
here.

Auth: /api/me/profile is GATED. Only /api/me itself is open
(api/auth._OPEN_API_EXACT) — the sub-path deliberately is not, so in
firebase mode the middleware requires a verified token before this router
runs. The row is always scoped by the server-verified identity, never a
client-supplied one, and `_profile_owner` fails closed if that gate ever
regresses — same posture as routers/preferences.py.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Module import (not `from api.auth import current_user_email`) so tests can
# monkeypatch api.auth.AUTH_MODE and this router sees it — same convention as
# routers/preferences.py.
from api import auth

logger = logging.getLogger(__name__)
router = APIRouter()

# Column order is fixed here; SQL below is only ever built from these
# literals (never from client-supplied strings).
_PROFILE_FIELDS = (
    "display_name",
    "timezone",
    "default_ticker",
    "default_timeframe",
    "account_size",
    "risk_per_trade_pct",
    "notify_daily_digest",
    "notify_catalyst_alerts",
    "notify_signal_alerts",
    "number_format",
    "date_format",
    "show_extended_hours",
)

_RETURNING = ", ".join(_PROFILE_FIELDS)


class ProfileUpdate(BaseModel):
    """Partial update for PUT /api/me/profile.

    The Literal values are the contract with solyra (see module docstring):
      default_timeframe — types/profile.ts DefaultTimeframe
      number_format     — 'abbreviated' | 'full'
      date_format       — 'iso' | 'us'

    `extra="forbid"` turns an unknown field into a 422 rather than silently
    dropping it — a client that sends a field this API doesn't store must
    hear about it, not believe it saved (Rule 3.7: no fabricated success).
    """

    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = Field(default=None, max_length=120)
    timezone: Optional[str] = Field(default=None, max_length=120)
    default_ticker: Optional[str] = Field(default=None, max_length=16)
    default_timeframe: Optional[Literal["1D", "5D", "1M", "3M", "6M", "1Y"]] = None
    account_size: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    notify_daily_digest: Optional[bool] = None
    notify_catalyst_alerts: Optional[bool] = None
    notify_signal_alerts: Optional[bool] = None
    number_format: Optional[Literal["abbreviated", "full"]] = None
    date_format: Optional[Literal["iso", "us"]] = None
    show_extended_hours: Optional[bool] = None


def _profile_owner(request: Request) -> str:
    """Owner key the profile row is scoped by (mirrors preferences._prefs_owner).

    Fail-closed guard: in firebase mode an absent identity means the request
    somehow bypassed the middleware — 401 rather than serving the shared
    "local" row to an anonymous caller.
    """
    email = auth.current_user_email(request)
    if email:
        return email
    if auth.AUTH_MODE == "firebase":
        raise HTTPException(status_code=401, detail="sign in to continue")
    return "local"


def _select_row(owner: str) -> Optional[dict]:
    """The owner's stored row, or None when they've never saved. Raises on a
    real DB failure — the caller turns that into a loud 503, never an empty
    fabricated result (Rule 3.7)."""
    from gcp.database import get_engine  # noqa: PLC0415 — lazy: sqlalchemy is heavy
    from sqlalchemy import text  # noqa: PLC0415

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"""
                SELECT {_RETURNING}
                FROM user_profile
                WHERE user_email = :user_email
                """
            ),
            {"user_email": owner},
        ).mappings().first()
    return None if row is None else dict(row)


@router.get("/api/me/profile")
def get_profile(request: Request) -> dict:
    owner = _profile_owner(request)
    try:
        row = _select_row(owner)
    except Exception as exc:
        logger.error("profile read failed for %s: %s", owner, exc)
        raise HTTPException(
            status_code=503, detail="profile temporarily unavailable"
        ) from exc
    if row is None:
        # A real, distinguishable "nothing stored yet" — the frontend renders
        # empty fields. Never a 200 with fabricated defaults.
        raise HTTPException(status_code=404, detail="no profile stored")
    return row


@router.put("/api/me/profile")
def put_profile(body: ProfileUpdate, request: Request) -> dict:
    """Upsert the provided subset of fields and return the full stored row.

    ONE round trip: INSERT ... ON CONFLICT (user_email) DO UPDATE with only
    the provided columns in the SET list, RETURNING the stored object.
    Omitted fields are untouched; explicit nulls persist as NULL. Repeated
    identical PUTs are the same single idempotent upsert.
    """
    owner = _profile_owner(request)

    # model_fields_set distinguishes "omitted" (leave as-is) from "explicit
    # null" (clear). Iterating _PROFILE_FIELDS keeps column order fixed and
    # guarantees the SQL below is built from our literals only.
    cols = [f for f in _PROFILE_FIELDS if f in body.model_fields_set]
    insert_cols = ", ".join(["user_email", *cols])
    insert_vals = ", ".join([":user_email", *[f":{c}" for c in cols]])
    # Empty update ({}): keep the statement valid with a no-op assignment so
    # RETURNING still yields the row (a new user gets an all-NULL row — an
    # explicit "saved nothing", which GET then reports as stored nulls).
    set_clause = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in cols
    ) or "user_email = EXCLUDED.user_email"

    sql = f"""
        INSERT INTO user_profile ({insert_cols})
        VALUES ({insert_vals})
        ON CONFLICT (user_email) DO UPDATE SET {set_clause}
        RETURNING {_RETURNING}
    """
    params = {"user_email": owner, **{c: getattr(body, c) for c in cols}}

    try:
        from gcp.database import get_engine  # noqa: PLC0415 — lazy: sqlalchemy is heavy
        from sqlalchemy import text  # noqa: PLC0415

        engine = get_engine()
        with engine.begin() as conn:
            row = conn.execute(text(sql), params).mappings().first()
    except Exception as exc:
        logger.error("profile write failed for %s: %s", owner, exc)
        raise HTTPException(
            status_code=503, detail="profile temporarily unavailable"
        ) from exc
    return dict(row)
