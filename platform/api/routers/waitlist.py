"""Waitlist router — public signup capture for the Solyra landing page.

POST /api/waitlist
    Body: {"email": "...", "source": "landing-hero", "website": ""}

`website` is a honeypot field: the form hides it, humans never fill it, bots
do. A filled honeypot returns 200 WITHOUT writing — the one sanctioned
anti-bot fake success (spec §7). Every real failure is LOUD (Rule 3.7):
400 invalid email · 429 rate-limited · 503 DB unavailable.

Public endpoint: listed in api.auth._OPEN_API_PREFIXES (no bearer token).
"""
from __future__ import annotations

import logging
import re
import sys
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)
router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Per-IP sliding window: 5 requests / 10 min. In-memory = per Cloud Run
# instance; acceptable as a basic abuse guard for a waitlist form — durable
# abuse is already bounded by the UNIQUE(email) upsert.
_RATE_LIMIT = 5
_RATE_WINDOW_S = 600
_hits: dict[str, deque] = {}


class WaitlistBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    source: str | None = Field(default=None, max_length=64)
    website: str = ""  # honeypot — must stay empty


def _client_ip(request: Request) -> str:
    """Best client identity behind Cloud Run's proxy: the LAST entry of
    X-Forwarded-For is the hop Google's frontend itself observed (earlier
    entries are client-supplied and spoofable). Falls back to the socket
    peer for local/dev.

    Valid for direct run.app ingress. If a GCLB/external ALB or IAP ever
    fronts this service, GCLB appends "<client-ip>, <lb-ip>" and last-hop
    keying collapses to the LB address — revisit then."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _hits.setdefault(ip, deque())
    while q and now - q[0] > _RATE_WINDOW_S:
        q.popleft()
    if len(q) >= _RATE_LIMIT:
        return True
    q.append(now)
    # Opportunistically evict other IPs whose windows have fully expired so
    # the dict stays bounded to recently-active clients (public endpoint).
    stale = [k for k, v in _hits.items() if k != ip and v and now - v[-1] > _RATE_WINDOW_S]
    for k in stale:
        del _hits[k]
    return False


@router.post("/api/waitlist")
def join_waitlist(body: WaitlistBody, request: Request) -> dict:
    if body.website:
        # Honeypot tripped — bot traffic. Fake success, write nothing.
        # Checked BEFORE email-format validation: a bot sending a malformed
        # email must still get the fake-success 200, not a 400 that would
        # signal "this is a validation endpoint" back to the bot.
        logger.info("waitlist honeypot tripped ip=%s", _client_ip(request))
        return {"status": "ok"}

    email = body.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="enter a valid email address")

    ip = _client_ip(request)
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="too many attempts — try again later")

    try:
        from gcp.database import get_engine  # noqa: PLC0415 — lazy: sqlalchemy is heavy
        from sqlalchemy import text  # noqa: PLC0415

        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO waitlist_signups (email, source, user_agent)
                    VALUES (:email, :source, :ua)
                    ON CONFLICT (email) DO UPDATE SET updated_at = now()
                    """
                ),
                {
                    "email": email,
                    "source": (body.source or "landing")[:64],
                    "ua": (request.headers.get("user-agent") or "")[:512],
                },
            )
    except HTTPException:
        raise
    except Exception as exc:  # INTERNAL failure → loud 503 (Rule 3.7), never fake success
        logger.error("waitlist insert failed: %s", exc)
        raise HTTPException(
            status_code=503, detail="could not save your signup — please retry"
        ) from exc

    return {"status": "ok"}
