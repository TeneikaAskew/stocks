"""
Tests for the staging passcode gate (platform/api/auth_bypass.py).

Covers the four states the gate must distinguish:
  1. Bypass DISABLED (prod behind IAP / local dev) — middleware is a no-op,
     the data API is reachable, and the handshake routes 404.
  2. Bypass ENABLED but no passcode configured — gated routes 401, the
     handshake returns an explicit 503 (no silent "let everyone in").
  3. Bypass ENABLED with a passcode — full handshake: wrong passcode 401,
     correct passcode sets the cookie and opens the gated routes + /api/me.
  4. An IAP email header satisfies the gate even without a cookie (so a
     staging revision that *does* sit behind IAP still works).

Hermetic: builds a tiny FastAPI app wired to the real middleware + router,
no Cloud SQL / GCS / network. Run with `make test` or
`pytest tests/test_platform_auth_bypass.py`.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# platform/ is a sibling of the repo root; add it so `import api.auth_bypass`
# resolves the same module the FastAPI app uses.
_PLATFORM = Path(__file__).resolve().parent.parent / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _build_client(monkeypatch, *, enabled: bool, passcode: str | None):
    """Build a TestClient with the gate configured via env, reloading the module."""
    if enabled:
        monkeypatch.setenv("ALLOW_AUTH_BYPASS", "1")
    else:
        monkeypatch.delenv("ALLOW_AUTH_BYPASS", raising=False)
    if passcode is None:
        monkeypatch.delenv("STAGING_PASSCODE", raising=False)
    else:
        monkeypatch.setenv("STAGING_PASSCODE", passcode)

    import api.auth_bypass as ab
    importlib.reload(ab)  # re-read env at import time

    app = FastAPI()
    app.middleware("http")(ab.staging_auth_middleware)
    app.include_router(ab.router)

    @app.get("/api/secret")
    async def _secret():  # a stand-in for any DB-backed data endpoint
        return {"ok": True}

    @app.get("/api/health")
    async def _health():
        return {"status": "ok"}

    @app.get("/api/me")
    async def _me(request: Request):
        email = None
        if ab.bypass_enabled() and ab.has_valid_bypass_cookie(request):
            email = ab.GUEST_EMAIL
        return {"email": email, "auth_bypass_allowed": ab.bypass_enabled()}

    return TestClient(app), ab


def test_disabled_is_a_noop(monkeypatch):
    c, _ = _build_client(monkeypatch, enabled=False, passcode=None)
    assert c.get("/api/secret").status_code == 200
    assert c.get("/api/me").json() == {"email": None, "auth_bypass_allowed": False}
    # Handshake is invisible when the gate is off.
    assert c.post("/api/auth/bypass", json={"passcode": "x"}).status_code == 404


def test_enabled_without_passcode_fails_loud(monkeypatch):
    c, _ = _build_client(monkeypatch, enabled=True, passcode=None)
    # Data endpoints are locked...
    assert c.get("/api/secret").status_code == 401
    # ...but the handshake + probe stay reachable so the screen can load.
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/me").status_code == 200
    assert c.get("/api/me").json()["auth_bypass_allowed"] is True
    # Misconfiguration is explicit, never a quiet allow.
    assert c.post("/api/auth/bypass", json={"passcode": "anything"}).status_code == 503


def test_full_passcode_handshake(monkeypatch):
    c, _ = _build_client(monkeypatch, enabled=True, passcode="hunter2-staging")
    # Gated before the cookie exists.
    assert c.get("/api/secret").status_code == 401
    assert c.get("/api/me").json()["email"] is None
    # Wrong passcode is rejected.
    assert c.post("/api/auth/bypass", json={"passcode": "nope"}).status_code == 401
    # Correct passcode sets the cookie and opens the gate.
    r = c.post("/api/auth/bypass", json={"passcode": "hunter2-staging"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert c.get("/api/secret").status_code == 200
    assert c.get("/api/me").json()["email"] == "guest@staging.local"
    # Logout closes it again.
    assert c.post("/api/auth/logout").status_code == 200
    c.cookies.clear()
    assert c.get("/api/secret").status_code == 401


def test_iap_email_header_satisfies_gate(monkeypatch):
    c, _ = _build_client(monkeypatch, enabled=True, passcode="hunter2-staging")
    r = c.get(
        "/api/secret",
        headers={"x-goog-authenticated-user-email": "accounts.google.com:a@b.com"},
    )
    assert r.status_code == 200


def test_cookie_value_never_contains_passcode(monkeypatch):
    """The bypass cookie carries an HMAC, not the passcode itself."""
    c, ab = _build_client(monkeypatch, enabled=True, passcode="hunter2-staging")
    r = c.post("/api/auth/bypass", json={"passcode": "hunter2-staging"})
    token = c.cookies.get(ab.BYPASS_COOKIE)
    assert token and "hunter2-staging" not in token
    assert token == ab._expected_token("hunter2-staging")
