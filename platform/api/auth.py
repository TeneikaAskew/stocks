"""
App-level authentication, gated by the AUTH_MODE env var.

Replaces the staging passcode bypass (the former auth_bypass.py). One middleware
serves three modes so prod can stay on IAP while staging runs the in-app login,
all from the same image:

  - "firebase": verify a Firebase ID token (Authorization: Bearer ...) on every
    gated /api/* request. Identity = the verified email. Used by the public
    staging service, and later production once we flip it off IAP.
  - "iap": pass-through. Identity comes from the IAP-injected
    `X-Goog-Authenticated-User-Email` header at the edge (current production).
    The middleware does NOT enforce here — IAP already gated the request.
  - "open": no-op (local dev — no auth).

Access policy (firebase mode): open self-signup by default
(`AUTH_OPEN_SIGNUP=1`). Flip to an allow-list with `AUTH_OPEN_SIGNUP=0` +
`AUTH_ALLOWED_EMAILS=a@x.com,b@y.com` — one env change, no code edit.

No silent fallbacks (CLAUDE.md Rule 3.7): a missing/invalid token is an explicit
401, a disallowed account an explicit 403 — never a quiet allow.
"""
from __future__ import annotations

import os
from typing import Awaitable, Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse

AUTH_MODE = os.environ.get("AUTH_MODE", "open").strip().lower()

# Reachable without a token so the SPA shell + login screen can boot and probe.
# Matching is prefix-based (see _path_requires_auth: `path == p or
# path.startswith(p)`), so each entry must be chosen narrowly enough that it
# doesn't unintentionally open a future sibling route (e.g. "/api/me" also
# opens "/api/me/anything" — pick exact, specific prefixes here).
_OPEN_API_PREFIXES = ("/api/health", "/api/me", "/api/config/firebase", "/api/waitlist")

_firebase_ready = False


def _ensure_firebase() -> None:
    """Initialize firebase-admin once (ADC on Cloud Run — no key file needed)."""
    global _firebase_ready
    if _firebase_ready:
        return
    import firebase_admin  # imported lazily so non-firebase modes don't need the dep

    if not firebase_admin._apps:
        project = (
            os.environ.get("FIREBASE_PROJECT_ID")
            or os.environ.get("GCP_PROJECT_ID")
            or None
        )
        firebase_admin.initialize_app(
            options={"projectId": project} if project else None
        )
    _firebase_ready = True


def _verify_bearer_email(request: Request) -> Optional[str]:
    """Return the verified email from the Firebase ID token, or None if absent.

    Raises on an invalid/expired token (caller turns that into a 401).
    """
    authz = request.headers.get("authorization") or ""
    if not authz.lower().startswith("bearer "):
        return None
    token = authz.split(" ", 1)[1].strip()
    if not token:
        return None
    _ensure_firebase()
    from firebase_admin import auth as fb_auth

    # Tolerate small clock skew between the token-issuing client and this
    # server. Firebase stamps a token's `iat`/`exp` from Google's clock; a
    # user's device (or this server) can legitimately be a few seconds off,
    # and with the default zero tolerance a valid, freshly-minted token is
    # rejected as "used too early" — an intermittent, unfixable-from-our-side
    # 401 for anyone whose clock isn't perfectly synced. Firebase permits up
    # to 60s of skew; using the max is harmless on 1-hour tokens and is the
    # documented, production-grade way to handle real-world clock drift.
    decoded = fb_auth.verify_id_token(token, clock_skew_seconds=60)
    email = (decoded.get("email") or "").strip().lower()
    return email or None


def _iap_email(request: Request) -> Optional[str]:
    raw = request.headers.get("x-goog-authenticated-user-email")
    if not raw:
        return None
    return raw.split(":", 1)[-1].strip().lower() or None


def current_user_email(request: Request) -> Optional[str]:
    """Identity accessor for routers.

    firebase mode: the email the middleware verified and stashed on
    request.state; for OPEN paths (e.g. /api/me) the middleware skips
    verification, so resolve from the bearer token here when present. iap mode:
    the IAP header. Otherwise None.
    """
    email = getattr(request.state, "user_email", None)
    if email:
        return email
    if AUTH_MODE == "iap":
        return _iap_email(request)
    if AUTH_MODE == "firebase":
        try:
            return _verify_bearer_email(request)
        except Exception:
            return None
    return None


def _is_allowed(email: str) -> bool:
    if os.environ.get("AUTH_OPEN_SIGNUP", "1").strip() == "1":
        return True
    allow = {
        e.strip().lower()
        for e in os.environ.get("AUTH_ALLOWED_EMAILS", "").split(",")
        if e.strip()
    }
    return email in allow


def _path_requires_auth(path: str) -> bool:
    if not path.startswith("/api/"):
        return False  # SPA shell + /assets are always served so the login UI loads
    return not any(path == p or path.startswith(p) for p in _OPEN_API_PREFIXES)


async def auth_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Enforce Firebase auth on gated /api/* in firebase mode; pass-through otherwise."""
    request.state.user_email = None

    if AUTH_MODE != "firebase":
        # iap: edge already gated; identity read lazily via current_user_email.
        # open: local dev, no auth.
        return await call_next(request)

    if not _path_requires_auth(request.url.path):
        return await call_next(request)

    try:
        email = _verify_bearer_email(request)
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "invalid or expired sign-in"})

    if not email:
        return JSONResponse(status_code=401, content={"detail": "sign in to continue"})
    if not _is_allowed(email):
        return JSONResponse(status_code=403, content={"detail": "this account is not allowed"})

    request.state.user_email = email
    return await call_next(request)
