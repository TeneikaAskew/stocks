"""
Staging auth-bypass — passcode gate for the public (no-IAP) staging service.

Why this exists
---------------
Prod runs behind IAP (Cloud Run `--no-allow-unauthenticated`), which injects
`X-Goog-Authenticated-User-Email`. IAP is a *service-level* setting, so a
revision tag on the same service can't drop it. To get a staging surface that
is reachable WITHOUT a Google sign-in, staging is deployed as a *separate*
`trading-platform-staging` service with `--allow-unauthenticated`. That makes
the FastAPI endpoints publicly routable, so this module re-protects them with
a shared passcode.

Activation
----------
Everything here is inert unless ``ALLOW_AUTH_BYPASS=1`` is set in the
environment (only the staging deploy sets it — see ``platform/deploy.sh``).
When inactive, the middleware is a no-op and the routes 404, so prod and
local dev behave exactly as before this module existed.

When active:
  * Every ``/api/*`` request (except the auth handshake, ``/api/me`` and
    ``/api/health``) must carry either an IAP email header OR a valid bypass
    cookie. Otherwise → 401.
  * ``POST /api/auth/bypass {passcode}`` checks the passcode against
    ``STAGING_PASSCODE`` and, on success, sets an HttpOnly bypass cookie.
  * ``/api/me`` reports the guest identity when the cookie is valid, so the
    frontend gate flips from "sign in" to "rendered".
  * The SPA shell + ``/assets`` (anything not under ``/api/``) are always
    served so the React sign-in screen can load and run the handshake.

No silent fallbacks (CLAUDE.md Rule 3.7): a wrong/missing passcode is an
explicit 401; ``ALLOW_AUTH_BYPASS=1`` with no ``STAGING_PASSCODE`` configured
is an explicit 503 — never a quiet "let them in" or "lock everyone out".
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Cookie + identity constants
BYPASS_COOKIE = "staging_bypass"
GUEST_EMAIL = "guest@staging.local"
_COOKIE_MAX_AGE = 12 * 60 * 60  # 12h — a working session, then re-enter.

# `/api/*` paths that stay reachable without the cookie so the React app can
# boot and run the passcode handshake. Everything else under /api/ is gated.
_OPEN_API_PREFIXES = ("/api/me", "/api/auth/", "/api/health")


def bypass_enabled() -> bool:
    """True only on the staging service (ALLOW_AUTH_BYPASS=1)."""
    return os.environ.get("ALLOW_AUTH_BYPASS", "").strip() == "1"


def _configured_passcode() -> str:
    """The shared staging passcode from the environment (Secret Manager-backed)."""
    return os.environ.get("STAGING_PASSCODE", "").strip()


def _expected_token(passcode: str) -> str:
    """Derive the opaque cookie value from the passcode.

    The cookie never carries the passcode itself — it carries an HMAC of a
    fixed message keyed by the passcode. The server recomputes and compares
    with ``hmac.compare_digest`` (constant-time). Stateless: no DB, no session
    store, survives instance restarts.
    """
    return hmac.new(passcode.encode(), b"staging-bypass-v1", hashlib.sha256).hexdigest()


def has_valid_bypass_cookie(request: Request) -> bool:
    """True when the request carries a cookie matching the configured passcode."""
    passcode = _configured_passcode()
    if not passcode:
        return False
    token = request.cookies.get(BYPASS_COOKIE)
    if not token:
        return False
    return hmac.compare_digest(token, _expected_token(passcode))


def _has_iap_email(request: Request) -> bool:
    return bool(request.headers.get("x-goog-authenticated-user-email"))


def _api_path_requires_auth(path: str) -> bool:
    """Gate every /api/* path except the auth handshake, /api/me, /api/health.

    Non-/api/ paths (the SPA shell + /assets + /dev) are never gated here so
    the sign-in screen can render; the React gate stops them from seeing data.
    """
    if not path.startswith("/api/"):
        return False
    return not any(path == p or path.startswith(p) for p in _OPEN_API_PREFIXES)


async def staging_auth_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Require IAP email OR a valid bypass cookie on gated /api/* paths.

    No-op unless ALLOW_AUTH_BYPASS=1, so prod and local dev are unaffected.
    """
    if not bypass_enabled():
        return await call_next(request)

    if _api_path_requires_auth(request.url.path):
        if not _has_iap_email(request) and not has_valid_bypass_cookie(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "staging: enter the staging passcode to continue"},
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Auth handshake routes
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/auth", tags=["auth"])


class BypassRequest(BaseModel):
    passcode: str


@router.post("/bypass")
async def bypass(body: BypassRequest, request: Request, response: Response) -> dict:
    """Validate the staging passcode; on success set the bypass cookie.

    404 when bypass is disabled (prod/local), 503 when enabled but the server
    has no passcode configured, 401 on a wrong passcode.
    """
    if not bypass_enabled():
        raise HTTPException(status_code=404, detail="not found")
    expected = _configured_passcode()
    if not expected:
        raise HTTPException(status_code=503, detail="STAGING_PASSCODE not configured on the server")
    if not hmac.compare_digest(body.passcode.strip(), expected):
        raise HTTPException(status_code=401, detail="invalid staging passcode")

    # Secure over HTTPS only. Cloud Run terminates TLS at the edge and may hand
    # the container an http scheme, so trust X-Forwarded-Proto too; local/test
    # harnesses are plain http, so the cookie still round-trips there.
    is_https = request.url.scheme == "https" or (
        request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
    )
    response.set_cookie(
        key=BYPASS_COOKIE,
        value=_expected_token(expected),
        max_age=_COOKIE_MAX_AGE,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
    )
    return {"ok": True, "email": GUEST_EMAIL}


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the bypass cookie (the 'Exit staging' affordance)."""
    response.delete_cookie(BYPASS_COOKIE, path="/")
    return {"ok": True}
