"""Preferences router — per-user appearance settings, synced across devices.

Endpoints:
  GET /api/me/preferences — the signed-in user's stored preferences.
      404 when the user has never saved any: the frontend treats that as a
      legitimate "nothing stored yet" state and keeps its local values, so
      this endpoint never fabricates defaults (CLAUDE.md Rule 3.7 — a
      missing preference must stay distinguishable from a real choice).
  PUT /api/me/preferences — partial update: any subset of the four fields.
      An explicit null CLEARS a field ("no preference stored"); an omitted
      field is left untouched. Returns the full stored object after the
      update. Unknown fields and unknown enum values are rejected with 422.

Contract: the response shape is hand-mirrored by solyra's
src/types/preferences.ts (four nullable snake_case fields), and the accepted
values by its stores — themeStore.Theme, settingsStore.NavPattern / Density /
ACCENTS (which the density-*/accent-* classes in src/index.css implement).
Nothing mechanically ties the two repos together, so a change to either side
must land on both in the same change set (solyra CLAUDE.md Rule 6).

Auth: /api/me/preferences is GATED. Only /api/me itself is open
(api/auth._OPEN_API_EXACT) — the sub-path deliberately is not, so in
firebase mode the middleware requires a verified token before this router
runs. The row is always scoped by the server-verified identity, never a
client-supplied one, and `_prefs_owner` fails closed if that gate ever
regresses.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Module import (not `from api.auth import current_user_email`) so tests can
# monkeypatch api.auth.AUTH_MODE and this router sees it — same convention as
# tests/test_platform_auth.py's setattr-over-reload rationale.
from api import auth

logger = logging.getLogger(__name__)
router = APIRouter()

# Column order is fixed here; SQL below is only ever built from these
# literals (never from client-supplied strings).
_PREF_FIELDS = ("theme", "nav_pattern", "density", "accent")


class PreferencesUpdate(BaseModel):
    """Partial update for PUT /api/me/preferences.

    The Literal values are the contract with solyra (see module docstring):
      theme        — themeStore.Theme
      nav_pattern  — settingsStore.NavPattern
      density      — settingsStore.Density (there is NO 'compact' — the CSS
                     ships density-comfy/-default/-dense only)
      accent       — settingsStore.ACCENTS / the accent-* classes in
                     src/index.css

    `extra="forbid"` turns an unknown field into a 422 rather than silently
    dropping it — a client that sends a field this API doesn't store must
    hear about it, not believe it saved (Rule 3.7: no fabricated success).
    """

    model_config = ConfigDict(extra="forbid")

    theme: Optional[Literal["light", "dark"]] = None
    nav_pattern: Optional[Literal["top-tabs", "sidebar"]] = None
    density: Optional[Literal["comfy", "default", "dense"]] = None
    accent: Optional[
        Literal[
            "blue", "amber", "violet", "cyan", "teal", "pink",
            "magenta", "orange", "yellow", "indigo", "rose",
        ]
    ] = None


def _prefs_owner(request: Request) -> str:
    """Owner key preferences are scoped by (mirrors journal._journal_owner).

    firebase/iap (deployed): the middleware/edge guarantees a verified
    identity on this gated path, so this is the user's email and one user
    can never read or write another's row. open/local dev has no auth, so
    preferences share the "local" owner — Settings keeps working against a
    local Postgres.

    Fail-closed guard: in firebase mode an absent identity means the request
    somehow bypassed the middleware (e.g. this sub-path regressing back into
    the open set — exactly the hazard api/auth.py's _OPEN_API_EXACT comment
    warns about). 401 rather than serving the shared "local" row to an
    anonymous caller.
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
                """
                SELECT theme, nav_pattern, density, accent
                FROM user_preferences
                WHERE user_email = :user_email
                """
            ),
            {"user_email": owner},
        ).mappings().first()
    return None if row is None else dict(row)


@router.get("/api/me/preferences")
async def get_preferences(request: Request) -> dict:
    owner = _prefs_owner(request)
    try:
        row = _select_row(owner)
    except Exception as exc:
        logger.error("preferences read failed for %s: %s", owner, exc)
        raise HTTPException(
            status_code=503, detail="preferences temporarily unavailable"
        ) from exc
    if row is None:
        # A real, distinguishable "nothing stored yet" — the frontend keeps
        # its local values. Never a 200 with fabricated defaults.
        raise HTTPException(status_code=404, detail="no preferences stored")
    return row


@router.put("/api/me/preferences")
async def put_preferences(body: PreferencesUpdate, request: Request) -> dict:
    """Upsert the provided subset of fields and return the full stored row.

    ONE round trip (Rule 0): INSERT ... ON CONFLICT (user_email) DO UPDATE
    with only the provided columns in the SET list, RETURNING the stored
    object. Omitted fields are untouched; explicit nulls persist as NULL
    ("no preference stored"). Repeated identical PUTs are the same single
    idempotent upsert — cheap, and always 200.
    """
    owner = _prefs_owner(request)

    # model_fields_set distinguishes "omitted" (leave as-is) from "explicit
    # null" (clear). Iterating _PREF_FIELDS keeps column order fixed and
    # guarantees the SQL below is built from our literals only.
    cols = [f for f in _PREF_FIELDS if f in body.model_fields_set]
    insert_cols = ", ".join(["user_email", *cols])
    insert_vals = ", ".join([":user_email", *[f":{c}" for c in cols]])
    # Empty update ({}): keep the statement valid with a no-op assignment so
    # RETURNING still yields the row (a new user gets an all-NULL row — an
    # explicit "saved nothing", which GET then reports as stored nulls).
    set_clause = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in cols
    ) or "user_email = EXCLUDED.user_email"

    sql = f"""
        INSERT INTO user_preferences ({insert_cols})
        VALUES ({insert_vals})
        ON CONFLICT (user_email) DO UPDATE SET {set_clause}
        RETURNING theme, nav_pattern, density, accent
    """
    params = {"user_email": owner, **{c: getattr(body, c) for c in cols}}

    try:
        from gcp.database import get_engine  # noqa: PLC0415 — lazy: sqlalchemy is heavy
        from sqlalchemy import text  # noqa: PLC0415

        engine = get_engine()
        with engine.begin() as conn:
            row = conn.execute(text(sql), params).mappings().first()
    except Exception as exc:
        logger.error("preferences write failed for %s: %s", owner, exc)
        raise HTTPException(
            status_code=503, detail="preferences temporarily unavailable"
        ) from exc
    return dict(row)
