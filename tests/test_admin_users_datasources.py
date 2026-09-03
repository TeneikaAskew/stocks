"""Tests for the Admin page's Users & roles + Chart & report data endpoints.

  GET  /api/admin/users                       — Firebase directory + user_roles
  PUT  /api/admin/users/{uid}/roles           — replace stored role
  PUT  /api/admin/users/{uid}/status          — enable/disable account
  GET  /api/admin/data-sources                — per-dataset freshness rollup
  POST /api/admin/data-sources/{id}/refresh   — dispatch the fetcher job

Asserts:
  (a) every endpoint sits behind _require_admin (401 anonymous / 403 non-admin);
  (b) users rows merge Firebase identity with user_roles, nullable fields stay
      null, and the ADMIN_EMAIL fallback account reads as admin without a row;
  (c) role writes: unknown role 422, two roles 422 (schema stores ONE role),
      [] deletes, ["user"]/["admin"] upserts, demoting ADMIN_EMAIL 409,
      unknown uid 404;
  (d) status writes: disabling revokes refresh tokens, disabling yourself or
      ADMIN_EMAIL is 409, unknown uid 404;
  (e) data-sources aggregates the shared freshness report per dataset —
      warn maps to stale with lag detail in message, absent datasets are
      honest 'unknown', partial per-ticker counts never sum into a lie;
  (f) refresh: unknown id 404, no-job datasets 409 with the reason, happy
      path returns the execution id, cooldown 429, dispatch failure LOUD 503
      (and does not consume the cooldown).

Hermetic: firebase-admin, gcp.database, and the run_v2 dispatch are all
patched via the module's indirections (_fb_auth, _roles_query/_roles_exec,
_run_refresh_job); identity uses iap mode + the IAP header, per
tests/test_structure_continuation.py's convention.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
# `platform/` makes the `api` package importable (admin.py's own imports);
# `platform/api` makes `routers` importable as a top-level package, the same
# dual-identity convention the other router suites use.
if str(REPO / "platform") not in sys.path:
    sys.path.insert(0, str(REPO / "platform"))
sys.path.insert(0, str(REPO / "platform" / "api"))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import admin as admin_module
from routers import health as health_module

ADMIN_EMAIL = "admin@example.com"
ADMIN_HEADERS = {"x-goog-authenticated-user-email": f"accounts.google.com:{ADMIN_EMAIL}"}
OTHER_HEADERS = {"x-goog-authenticated-user-email": "accounts.google.com:pleb@example.com"}


def _as_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    import api.auth
    monkeypatch.setattr(api.auth, "AUTH_MODE", "iap")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin_module.router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_cooldowns():
    admin_module._last_dispatch.clear()
    yield
    admin_module._last_dispatch.clear()


# ── Fake Firebase directory ──────────────────────────────────────────────────

def _fb_user(uid, email=None, display_name=None, disabled=False,
             created_ms=None, signin_ms=None):
    return SimpleNamespace(
        uid=uid,
        email=email,
        display_name=display_name,
        disabled=disabled,
        user_metadata=SimpleNamespace(
            creation_timestamp=created_ms, last_sign_in_timestamp=signin_ms
        ),
    )


class FakeFbAuth:
    class UserNotFoundError(Exception):
        pass

    def __init__(self, users):
        self.users = {u.uid: u for u in users}
        self.revoked: list[str] = []

    def list_users(self):
        users = list(self.users.values())
        return SimpleNamespace(iterate_all=lambda: iter(users))

    def get_user(self, uid):
        try:
            return self.users[uid]
        except KeyError:
            raise self.UserNotFoundError(uid)

    def update_user(self, uid, disabled):
        user = self.get_user(uid)
        user.disabled = disabled
        return user

    def revoke_refresh_tokens(self, uid):
        self.revoked.append(uid)


def _wire_users(monkeypatch, users, roles: dict[str, str]):
    """Install the fake directory + role store; return (fb, exec_calls)."""
    fb = FakeFbAuth(users)
    monkeypatch.setattr(admin_module, "_fb_auth", lambda: fb)
    monkeypatch.setattr(
        admin_module,
        "_roles_query",
        lambda sql, params=None: pd.DataFrame(
            {"email": list(roles.keys()), "role": list(roles.values())}
        ),
    )
    exec_calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        admin_module,
        "_roles_exec",
        lambda sql, params=None: exec_calls.append((sql, params)) or 1,
    )
    return fb, exec_calls


# ── Auth gate ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/admin/users"),
        ("put", "/api/admin/users/u1/roles"),
        ("put", "/api/admin/users/u1/status"),
        ("get", "/api/admin/data-sources"),
        ("post", "/api/admin/data-sources/market_data_daily/refresh"),
    ],
)
def test_endpoints_require_admin(monkeypatch, method, path):
    _as_admin(monkeypatch)
    c = _client()
    body = {"roles": []} if path.endswith("/roles") else {"disabled": True}
    kwargs = {"json": body} if method == "put" else {}
    assert getattr(c, method)(path, **kwargs).status_code == 401  # anonymous
    r = getattr(c, method)(path, headers=OTHER_HEADERS, **kwargs)
    assert r.status_code == 403  # signed in, not admin


# ── GET /users ───────────────────────────────────────────────────────────────

def test_users_merge_firebase_and_roles(monkeypatch):
    _as_admin(monkeypatch)
    _wire_users(
        monkeypatch,
        [
            _fb_user("u-admin", ADMIN_EMAIL, "Boss", created_ms=1_700_000_000_000),
            _fb_user("u-trader", "trader@example.com", None,
                     created_ms=1_710_000_000_000, signin_ms=1_711_000_000_000),
            _fb_user("u-phone", None, None),  # no email, never signed in
        ],
        roles={"trader@example.com": "user"},
    )
    r = _client().get("/api/admin/users", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["available_roles"] == ["admin", "user"]
    by_uid = {u["uid"]: u for u in data["users"]}
    # ADMIN_EMAIL holds admin via the env fallback despite having no table row.
    assert by_uid["u-admin"]["roles"] == ["admin"]
    assert by_uid["u-trader"]["roles"] == ["user"]
    assert by_uid["u-trader"]["display_name"] is None  # null, never ""
    assert by_uid["u-trader"]["last_sign_in_at"].startswith("2024-03-21")
    assert by_uid["u-phone"]["email"] is None
    assert by_uid["u-phone"]["roles"] == []
    assert by_uid["u-phone"]["created_at"] is None
    assert by_uid["u-phone"]["last_sign_in_at"] is None


def test_users_directory_failure_is_loud_503(monkeypatch):
    _as_admin(monkeypatch)

    class Boom:
        UserNotFoundError = FakeFbAuth.UserNotFoundError

        def list_users(self):
            raise RuntimeError("firebase down")

    monkeypatch.setattr(admin_module, "_fb_auth", lambda: Boom())
    r = _client().get("/api/admin/users", headers=ADMIN_HEADERS)
    assert r.status_code == 503


# ── PUT /users/{uid}/roles ───────────────────────────────────────────────────

def test_roles_unknown_role_is_422(monkeypatch):
    _as_admin(monkeypatch)
    _, exec_calls = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com")], {})
    r = _client().put(
        "/api/admin/users/u1/roles", json={"roles": ["superuser"]}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 422
    assert exec_calls == []


def test_roles_two_roles_is_422_never_partial_write(monkeypatch):
    _as_admin(monkeypatch)
    _, exec_calls = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com")], {})
    r = _client().put(
        "/api/admin/users/u1/roles",
        json={"roles": ["admin", "user"]},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422
    assert exec_calls == []  # never silently persists just one of the two


def test_roles_upsert_and_delete(monkeypatch):
    _as_admin(monkeypatch)
    _, exec_calls = _wire_users(monkeypatch, [_fb_user("u1", "A@X.com")], {})
    c = _client()

    r = c.put("/api/admin/users/u1/roles", json={"roles": ["user"]}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    sql, params = exec_calls[-1]
    assert "INSERT INTO user_roles" in sql and "ON CONFLICT (email)" in sql
    assert params["email"] == "a@x.com"  # normalized
    assert params["role"] == "user"
    assert params["created_by"] == ADMIN_EMAIL  # attributable, server-derived

    r = c.put("/api/admin/users/u1/roles", json={"roles": []}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    sql, params = exec_calls[-1]
    assert sql.strip().startswith("DELETE FROM user_roles")
    assert params["email"] == "a@x.com"


def test_roles_env_admin_cannot_be_demoted(monkeypatch):
    _as_admin(monkeypatch)
    _, exec_calls = _wire_users(monkeypatch, [_fb_user("u-admin", ADMIN_EMAIL)], {})
    r = _client().put(
        "/api/admin/users/u-admin/roles", json={"roles": []}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 409
    assert exec_calls == []


def test_roles_unknown_uid_is_404(monkeypatch):
    _as_admin(monkeypatch)
    _wire_users(monkeypatch, [], {})
    r = _client().put(
        "/api/admin/users/ghost/roles", json={"roles": ["user"]}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 404


def test_roles_no_email_account_is_422(monkeypatch):
    _as_admin(monkeypatch)
    _, exec_calls = _wire_users(monkeypatch, [_fb_user("u-phone", None)], {})
    r = _client().put(
        "/api/admin/users/u-phone/roles", json={"roles": ["user"]}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 422
    assert exec_calls == []


# ── PUT /users/{uid}/status ──────────────────────────────────────────────────

def test_status_disable_updates_and_revokes(monkeypatch):
    _as_admin(monkeypatch)
    fb, _ = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com")], {})
    r = _client().put(
        "/api/admin/users/u1/status", json={"disabled": True}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200
    assert r.json()["disabled"] is True
    assert fb.revoked == ["u1"]  # session dies at next token refresh


def test_status_enable_does_not_revoke(monkeypatch):
    _as_admin(monkeypatch)
    fb, _ = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com", disabled=True)], {})
    r = _client().put(
        "/api/admin/users/u1/status", json={"disabled": False}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 200
    assert r.json()["disabled"] is False
    assert fb.revoked == []


def test_status_cannot_disable_self_or_break_glass(monkeypatch):
    _as_admin(monkeypatch)
    fb, _ = _wire_users(monkeypatch, [_fb_user("u-admin", ADMIN_EMAIL)], {})
    r = _client().put(
        "/api/admin/users/u-admin/status", json={"disabled": True}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 409
    assert fb.users["u-admin"].disabled is False
    assert fb.revoked == []


def test_status_unknown_uid_is_404(monkeypatch):
    _as_admin(monkeypatch)
    _wire_users(monkeypatch, [], {})
    r = _client().put(
        "/api/admin/users/ghost/status", json={"disabled": True}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 404


# ── GET /data-sources ────────────────────────────────────────────────────────

_REPORT = {
    "checked_at": "2026-09-03T12:00:00Z",
    "overall_status": "warn",
    "tables": [
        {"table": "market_data_daily", "ticker": "IWM", "status": "ok",
         "last_row_at": "2026-09-02", "lag_hours": 8.0, "expected_max_hours": 30,
         "row_count_recent": 1},
        {"table": "market_data_daily", "ticker": "SPY", "status": "ok",
         "last_row_at": "2026-09-01", "lag_hours": 9.0, "expected_max_hours": 30,
         "row_count_recent": 2},
        {"table": "etf_options_snapshots", "ticker": "QQQ", "status": "warn",
         "last_row_at": "2026-09-01", "lag_hours": 26.0, "expected_max_hours": 30,
         "row_count_recent": None},
        {"table": "mystery_table", "ticker": None, "status": "stale",
         "last_row_at": None, "lag_hours": None, "expected_max_hours": None,
         "row_count_recent": None},
    ],
}


def _wire_freshness(monkeypatch, report=_REPORT):
    monkeypatch.setattr(health_module, "freshness_report_dict", lambda: report)


def test_data_sources_aggregation(monkeypatch):
    _as_admin(monkeypatch)
    _wire_freshness(monkeypatch)
    r = _client().get("/api/admin/data-sources", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    by_id = {s["id"]: s for s in r.json()["sources"]}

    daily = by_id["market_data_daily"]
    assert daily["status"] == "ok"
    assert daily["row_count"] == 3                      # all members counted
    assert daily["last_refreshed_at"] == "2026-09-02"   # max across tickers
    assert daily["coverage_end"] == "2026-09-02"
    assert daily["coverage_start"] is None              # not computed → null
    assert daily["message"] is None
    assert daily["refreshable"] is True

    options = by_id["etf_options_snapshots"]
    assert options["status"] == "stale"                 # warn → stale on the wire
    assert "lag 26.0h" in options["message"]
    assert options["row_count"] is None                 # None member → no fabricated sum

    # Registry dataset absent from the audit: honest unknown, not omitted.
    rates = by_id["daily_rates"]
    assert rates["status"] == "unknown"
    assert rates["message"] == "not covered by the freshness audit"

    # Audited table missing from the registry still shows up, un-refreshable.
    mystery = by_id["mystery_table"]
    assert mystery["status"] == "stale"
    assert mystery["category"] == "other"
    assert mystery["refreshable"] is False

    # Cost-gated datasets are advertised as non-refreshable.
    assert by_id["insight_reports"]["refreshable"] is False


# ── POST /data-sources/{id}/refresh ──────────────────────────────────────────

def test_refresh_unknown_source_is_404(monkeypatch):
    _as_admin(monkeypatch)
    r = _client().post("/api/admin/data-sources/nope/refresh", headers=ADMIN_HEADERS)
    assert r.status_code == 404


def test_refresh_non_refreshable_is_409_with_reason(monkeypatch):
    _as_admin(monkeypatch)
    r = _client().post(
        "/api/admin/data-sources/insight_reports/refresh", headers=ADMIN_HEADERS
    )
    assert r.status_code == 409
    assert "LLM budget" in r.json()["detail"]


def test_refresh_dispatches_job_and_cools_down(monkeypatch):
    _as_admin(monkeypatch)
    dispatched: list[str] = []

    def fake_run(job):
        dispatched.append(job)
        return "fetch-market-data-abc12"

    monkeypatch.setattr(admin_module, "_run_refresh_job", fake_run)
    c = _client()
    r = c.post("/api/admin/data-sources/market_data_daily/refresh", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json() == {
        "id": "market_data_daily",
        "queued": True,
        "job_id": "fetch-market-data-abc12",
    }
    assert dispatched == ["fetch-market-data"]

    # Immediate second press: cooled down, no second execution.
    r2 = c.post("/api/admin/data-sources/market_data_daily/refresh", headers=ADMIN_HEADERS)
    assert r2.status_code == 429
    assert dispatched == ["fetch-market-data"]


def test_refresh_dispatch_failure_is_loud_503_and_free_to_retry(monkeypatch):
    _as_admin(monkeypatch)
    calls = {"n": 0}

    def flaky(job):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("iam denied")
        return "exec-2"

    monkeypatch.setattr(admin_module, "_run_refresh_job", flaky)
    c = _client()
    r = c.post("/api/admin/data-sources/daily_rates/refresh", headers=ADMIN_HEADERS)
    assert r.status_code == 503
    # A failed dispatch must not consume the cooldown — the retry goes through.
    r2 = c.post("/api/admin/data-sources/daily_rates/refresh", headers=ADMIN_HEADERS)
    assert r2.status_code == 200
    assert r2.json()["job_id"] == "exec-2"
