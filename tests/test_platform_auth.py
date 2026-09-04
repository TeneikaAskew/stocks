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

import os
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

    @app.get("/api/me/preferences")
    async def _me_preferences(request: Request):
        return {"email": a.current_user_email(request)}

    @app.post("/api/waitlist")
    async def _waitlist():
        return {"status": "ok"}

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
    assert c.post("/api/waitlist").status_code == 200         # open path (public signup form)
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


def test_firebase_open_me_is_exact_match_and_subpaths_are_gated(monkeypatch):
    """/api/me is in _OPEN_API_EXACT: the path itself stays open (the login
    screen's pre-auth identity probe), but its SUB-PATHS are gated — the old
    prefix match opened "/api/me/anything", which would have let
    /api/me/preferences (per-user data) through unauthenticated. Regression
    guard for the hazard documented at the _OPEN_API_EXACT definition."""
    c, _ = _build(monkeypatch, "firebase")
    # The exact path stays open...
    assert c.get("/api/me").status_code == 200
    # ...its sub-path requires a verified token...
    assert c.get("/api/me/preferences").status_code == 401
    r = c.get("/api/me/preferences", headers={"authorization": "Bearer good:Me@X.com"})
    assert r.status_code == 200 and r.json()["email"] == "me@x.com"
    # ...and a sibling that merely starts with the string "/api/me" is gated
    # too (the middleware answers before routing, so no route is needed).
    assert c.get("/api/messages").status_code == 401


def test_firebase_allowlist_switch(monkeypatch):
    c, _ = _build(monkeypatch, "firebase", open_signup="0", allowed="ok@x.com, two@y.com")
    assert c.get("/api/secret", headers={"authorization": "Bearer good:ok@x.com"}).status_code == 200
    assert c.get("/api/secret", headers={"authorization": "Bearer good:two@y.com"}).status_code == 200
    r = c.get("/api/secret", headers={"authorization": "Bearer good:nope@x.com"})
    assert r.status_code == 403


def test_verify_bearer_email_tolerates_clock_skew(monkeypatch):
    """`_verify_bearer_email` must call verify_id_token with a clock-skew
    tolerance so a token whose `iat` is a few seconds ahead of THIS server's
    clock (normal, unavoidable device/server drift) isn't rejected as
    'used too early'. Without it, any user with a slightly-off clock gets an
    intermittent 401 and an empty app. Regression guard for PR #674."""
    import types
    import api.auth as a

    monkeypatch.setattr(a, "_ensure_firebase", lambda: None)

    captured: dict = {}

    class _FakeAuth:
        @staticmethod
        def verify_id_token(token, **kwargs):
            captured["kwargs"] = kwargs
            return {"email": "Me@X.com"}

    fake_mod = types.ModuleType("firebase_admin")
    fake_mod.auth = _FakeAuth  # `from firebase_admin import auth as fb_auth`
    monkeypatch.setitem(sys.modules, "firebase_admin", fake_mod)

    from starlette.requests import Request

    req = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/secret",
        "headers": [(b"authorization", b"Bearer sometoken")],
    })

    email = a._verify_bearer_email(req)
    assert email == "me@x.com"
    # The behavior under test: skew tolerance is passed and is a sane, non-zero
    # value within Firebase's allowed 0..60s range.
    skew = captured["kwargs"].get("clock_skew_seconds")
    assert skew is not None, "verify_id_token called with zero clock-skew tolerance"
    assert 0 < skew <= 60


# ─── Authorization: is_admin_email (user_roles table + ADMIN_EMAIL) ─────────
# The table is the source of truth; ADMIN_EMAIL is a fallback so an empty
# table, an unapplied migration, or a DB outage cannot lock every admin out.
# Hermetic: the DB helper is stubbed, so these assert OUR precedence and
# failure handling without a Postgres.

import types  # noqa: E402

from api import auth as auth_mod  # noqa: E402


def _stub_db(monkeypatch, *, rows: int = 0, raises: bool = False):
    """Stand in for gcp.database.query_to_dataframe_strict."""
    import pandas as pd

    def fake(sql, params=None, timeout_s=None):
        if raises:
            raise RuntimeError("connection refused")
        return pd.DataFrame({"?column?": [1] * rows})

    module = types.ModuleType("gcp.database")
    module.query_to_dataframe_strict = fake
    monkeypatch.setitem(sys.modules, "gcp.database", module)


def test_admin_env_fallback_matches_without_touching_db(monkeypatch):
    """ADMIN_EMAIL is checked first, so it works even if the DB is down."""
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    _stub_db(monkeypatch, raises=True)
    assert auth_mod.is_admin_email("boss@example.com") is True


def test_admin_from_user_roles_table(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "someone-else@example.com")
    _stub_db(monkeypatch, rows=1)
    assert auth_mod.is_admin_email("granted@example.com") is True


def test_non_admin_denied(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "someone-else@example.com")
    _stub_db(monkeypatch, rows=0)
    assert auth_mod.is_admin_email("nobody@example.com") is False


def test_admin_check_denies_when_lookup_fails(monkeypatch):
    """A broken lookup denies — it must never grant on error."""
    monkeypatch.setenv("ADMIN_EMAIL", "someone-else@example.com")
    _stub_db(monkeypatch, raises=True)
    assert auth_mod.is_admin_email("granted@example.com") is False


def test_admin_email_is_normalized(monkeypatch):
    """Casing and whitespace must not decide authorization."""
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    _stub_db(monkeypatch, rows=0)
    assert auth_mod.is_admin_email("  BOSS@Example.COM  ") is True


def test_no_identity_is_not_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    _stub_db(monkeypatch, rows=1)
    assert auth_mod.is_admin_email(None) is False
    assert auth_mod.is_admin_email("") is False


# ─── is_admin_email against a REAL engine ───────────────────────────────────
# The stubbed tests above cover precedence and failure handling, but they
# replace the DB helper wholesale — so the SQL string itself is never executed
# and a malformed one passes. That is exactly what happened: the query was
# written with psycopg2 `%(email)s` placeholders while the helper wraps SQL in
# sqlalchemy.text(), which only binds `:name`. Nothing raised; the parameter
# simply never bound, and every table-based admin silently resolved to False
# in production. This test runs the real query so that cannot recur.

_DB_HOST = os.environ.get("DB_HOST")
pytestmark_db = pytest.mark.skipif(
    not _DB_HOST, reason="no test Postgres configured (set DB_HOST)"
)


@pytestmark_db
def test_is_admin_email_binds_against_a_real_engine(monkeypatch):
    from sqlalchemy import text

    from gcp.database import get_engine

    monkeypatch.setenv("ADMIN_EMAIL", "not-the-user@example.com")
    granted = "role-binding-test@example.com"

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_roles (
                email       TEXT PRIMARY KEY,
                role        TEXT NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by  TEXT,
                note        TEXT
            )
        """))
        conn.execute(text("DELETE FROM user_roles WHERE email = :e"), {"e": granted})

    try:
        # Absent from the table, and not ADMIN_EMAIL → not an admin.
        assert auth_mod.is_admin_email(granted) is False

        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO user_roles (email, role) VALUES (:e, 'admin')"),
                {"e": granted},
            )

        # Present with role=admin → admin. Fails if the placeholder never binds.
        assert auth_mod.is_admin_email(granted) is True
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM user_roles WHERE email = :e"), {"e": granted})


# ---------------------------------------------------------------------------
# CORS origin allow-list (platform/api/main.py)
#
# The browser preview surfaces Lovable serves this project from must be
# allowed, or the very first /api/config/firebase call is blocked and the app
# boots into "Could not load application configuration". Lovable rotates the
# project UUID between preview builds, so the policy is DOMAIN-wide
# (*.lovable.app / *.lovableproject.com) rather than pinned to a name or
# UUID — see the trade-off note in api/main.py. These tests exercise the
# REAL app's middleware via CORS preflight, which CORSMiddleware answers
# before auth or routing runs.
# ---------------------------------------------------------------------------

_PREFLIGHT_HEADERS = {"Access-Control-Request-Method": "GET"}


def _preflight(origin: str):
    from api.main import app

    client = TestClient(app)
    return client.options(
        "/api/health",
        headers={"Origin": origin, **_PREFLIGHT_HEADERS},
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "https://solyra-stocks.lovable.app",
        "https://preview--solyra-stocks.lovable.app",
        "https://id-preview--f6c1be2f-245d-4a43-8110-dd05ffafa8af.lovable.app",
        "https://f6c1be2f-245d-4a43-8110-dd05ffafa8af.lovableproject.com",
        # A DIFFERENT UUID — Lovable rotates the project UUID between preview
        # builds, which is exactly why the policy is domain-wide.
        "https://0a1b2c3d-0000-4444-8888-9e8d7c6b5a40.lovableproject.com",
        "https://id-preview--0a1b2c3d-0000-4444-8888-9e8d7c6b5a40.lovable.app",
        "https://fuzzy-space-tunnel-1234.app.github.dev",
    ],
)
def test_cors_allows_this_projects_origins(origin):
    r = _preflight(origin)
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin


@pytest.mark.parametrize(
    "origin",
    [
        # Suffix attack: a Lovable-looking label as a subdomain of an
        # attacker's domain. Starlette fullmatches allow_origin_regex, so the
        # origin must END at lovable.app / lovableproject.com to pass.
        "https://foo.lovable.app.evil.example",
        "https://f6c1be2f-245d-4a43-8110-dd05ffafa8af.lovableproject.com.evil.example",
        # Lookalike registrable domains — dash or extra chars, not a dot.
        "https://evil-lovable.app",
        "https://xlovable.app",
        "https://foo.lovableproject.com.co",
        # Bare apex (Lovable serves projects from subdomains only).
        "https://lovable.app",
        # Wrong scheme.
        "http://preview--solyra-stocks.lovable.app",
    ],
)
def test_cors_rejects_other_origins(origin):
    r = _preflight(origin)
    # Starlette answers a disallowed preflight with 400 and, decisively, no
    # allow-origin header — the browser blocks the real request either way.
    assert r.headers.get("access-control-allow-origin") is None


def test_cors_regex_excludes_lovable_in_iap_mode():
    """Prod runs AUTH_MODE=iap, where auth_middleware enforces nothing (IAP at
    the edge is the gate) — so a cross-site Lovable allowance there would ride
    the IAP session cookie instead of a Firebase token. The Lovable branches
    must exist only in non-iap modes; previews only ever target staging."""
    import re

    from api.main import _cors_origin_regex

    iap = re.compile(_cors_origin_regex("iap"))
    fb = re.compile(_cors_origin_regex("firebase"))

    lovable = "https://preview--solyra-stocks.lovable.app"
    project = "https://0a1b2c3d-0000-4444-8888-9e8d7c6b5a40.lovableproject.com"
    codespace = "https://fuzzy-space-tunnel-1234.app.github.dev"

    assert fb.fullmatch(lovable) and fb.fullmatch(project)
    assert iap.fullmatch(lovable) is None
    assert iap.fullmatch(project) is None
    # The Codespaces branch survives in every mode.
    assert iap.fullmatch(codespace) and fb.fullmatch(codespace)
