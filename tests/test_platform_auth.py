"""
Tests for the AUTH_MODE auth middleware (platform/api/auth.py).

Covers the three modes and the access switch:
  - open:     middleware is a no-op (local dev).
  - iap:      no enforcement; identity read from the IAP header.
  - firebase: gated /api/* requires a verified Bearer token; open-signup vs
              allow-list switch; open paths stay reachable pre-auth.

Hermetic: the Firebase verify primitive (`_verify_bearer_email`) is stubbed so
the test exercises OUR middleware decision logic without firebase-admin or a
real token. Run with `make test` or `pytest tests/test_platform_auth.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PLATFORM = Path(__file__).resolve().parent.parent / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _build(monkeypatch, mode: str, *, open_signup: str = "1", allowed: str = ""):
    monkeypatch.setenv("AUTH_OPEN_SIGNUP", open_signup)
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", allowed)

    import api.auth as a
    # Set the module-level AUTH_MODE via setattr — NOT setenv + importlib.reload.
    # reload() re-executes api.auth in place, persistently mutating its shared
    # module globals; because api.main's auth_middleware reads AUTH_MODE from
    # that same module namespace, a left-over "firebase" leaks into every later
    # TestClient test in the session (it 401'd test_playbook_evaluate). setattr
    # is reverted by monkeypatch at teardown, so each test stays isolated.
    monkeypatch.setattr(a, "AUTH_MODE", mode)

    # Stub Firebase verification: Bearer "good:<email>" -> email; "bad" -> raise;
    # anything else / no header -> None. Exercises middleware logic, not the SDK.
    def fake_verify(request):
        authz = request.headers.get("authorization") or ""
        if not authz.lower().startswith("bearer "):
            return None
        tok = authz.split(" ", 1)[1]
        if tok == "bad":
            raise ValueError("invalid token")
        if tok.startswith("good:"):
            return tok.split(":", 1)[1].strip().lower() or None
        return None

    monkeypatch.setattr(a, "_verify_bearer_email", fake_verify)

    app = FastAPI()
    app.middleware("http")(a.auth_middleware)

    @app.get("/api/secret")
    async def _secret(request: Request):
        return {"email": a.current_user_email(request)}

    @app.get("/api/health")
    async def _health():
        return {"ok": True}

    @app.get("/api/me")
    async def _me(request: Request):
        return {"email": a.current_user_email(request)}

    return TestClient(app), a


def test_open_mode_is_noop(monkeypatch):
    c, _ = _build(monkeypatch, "open")
    r = c.get("/api/secret")
    assert r.status_code == 200
    assert r.json()["email"] is None


def test_iap_mode_reads_header_and_does_not_enforce(monkeypatch):
    c, _ = _build(monkeypatch, "iap")
    # Identity comes from the IAP header...
    r = c.get("/api/secret", headers={"x-goog-authenticated-user-email": "accounts.google.com:Me@X.com"})
    assert r.status_code == 200 and r.json()["email"] == "me@x.com"
    # ...and the middleware never blocks (the edge already gated the request).
    assert c.get("/api/secret").status_code == 200


def test_firebase_requires_valid_token(monkeypatch):
    c, _ = _build(monkeypatch, "firebase")
    assert c.get("/api/secret").status_code == 401            # no token
    assert c.get("/api/health").status_code == 200            # open path
    assert c.get("/api/me").status_code == 200                # open path
    # /api/me is open (middleware skips it) but must STILL report the verified
    # identity when a token is present — admin detection depends on it — and
    # None when anonymous.
    assert c.get("/api/me").json()["email"] is None
    assert (
        c.get("/api/me", headers={"authorization": "Bearer good:Me@X.com"}).json()["email"]
        == "me@x.com"
    )
    assert c.get("/api/secret", headers={"authorization": "Bearer bad"}).status_code == 401
    r = c.get("/api/secret", headers={"authorization": "Bearer good:Trader@X.com"})
    assert r.status_code == 200 and r.json()["email"] == "trader@x.com"


def test_firebase_allowlist_switch(monkeypatch):
    c, _ = _build(monkeypatch, "firebase", open_signup="0", allowed="ok@x.com, two@y.com")
    assert c.get("/api/secret", headers={"authorization": "Bearer good:ok@x.com"}).status_code == 200
    assert c.get("/api/secret", headers={"authorization": "Bearer good:two@y.com"}).status_code == 200
    r = c.get("/api/secret", headers={"authorization": "Bearer good:nope@x.com"})
    assert r.status_code == 403
