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


FIREBASE_ADMIN_HEADERS = {"authorization": f"Bearer good:{ADMIN_EMAIL}"}


def _as_admin_firebase(monkeypatch):
    """firebase-mode identity (needed by the status endpoint, which refuses
    iap mode outright): stub the token verifier per test_platform_auth.py's
    convention — 'Bearer good:<email>' verifies as <email>."""
    monkeypatch.setenv("ADMIN_EMAIL", ADMIN_EMAIL)
    import api.auth

    monkeypatch.setattr(api.auth, "AUTH_MODE", "firebase")

    def fake_verify(request):
        authz = request.headers.get("authorization") or ""
        if not authz.lower().startswith("bearer "):
            return None
        tok = authz.split(" ", 1)[1]
        return tok.split(":", 1)[1].strip().lower() if tok.startswith("good:") else None

    monkeypatch.setattr(api.auth, "_verify_bearer_email", fake_verify)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin_module.router)
    return TestClient(app)


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
    assert data["available_roles"] == ["admin", "user", "dev"]
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

    # 'dev' is assignable like any other role (it drives the frontend's
    # mock-data mode via /api/me is_dev; no extra API access).
    r = c.put("/api/admin/users/u1/roles", json={"roles": ["dev"]}, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    sql, params = exec_calls[-1]
    assert "INSERT INTO user_roles" in sql
    assert params["role"] == "dev"

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
# firebase-mode identity throughout: the endpoint refuses iap mode (below).

def test_status_disable_updates_and_revokes(monkeypatch):
    _as_admin_firebase(monkeypatch)
    fb, _ = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com")], {})
    r = _client().put(
        "/api/admin/users/u1/status", json={"disabled": True},
        headers=FIREBASE_ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["disabled"] is True
    assert fb.revoked == ["u1"]  # session dies at next token refresh


def test_status_enable_does_not_revoke(monkeypatch):
    _as_admin_firebase(monkeypatch)
    fb, _ = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com", disabled=True)], {})
    r = _client().put(
        "/api/admin/users/u1/status", json={"disabled": False},
        headers=FIREBASE_ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert r.json()["disabled"] is False
    assert fb.revoked == []


def test_status_cannot_disable_self_or_break_glass(monkeypatch):
    _as_admin_firebase(monkeypatch)
    fb, _ = _wire_users(monkeypatch, [_fb_user("u-admin", ADMIN_EMAIL)], {})
    r = _client().put(
        "/api/admin/users/u-admin/status", json={"disabled": True},
        headers=FIREBASE_ADMIN_HEADERS,
    )
    assert r.status_code == 409
    assert fb.users["u-admin"].disabled is False
    assert fb.revoked == []


def test_status_unknown_uid_is_404(monkeypatch):
    _as_admin_firebase(monkeypatch)
    _wire_users(monkeypatch, [], {})
    r = _client().put(
        "/api/admin/users/ghost/status", json={"disabled": True},
        headers=FIREBASE_ADMIN_HEADERS,
    )
    assert r.status_code == 404


def test_status_refused_in_iap_mode(monkeypatch):
    """iap mode authenticates at the edge; Firebase account status does not
    govern access there, so flipping it would be a fabricated success. The
    endpoint must refuse with an explanation, and never touch Firebase."""
    _as_admin(monkeypatch)  # iap identity
    fb, _ = _wire_users(monkeypatch, [_fb_user("u1", "a@x.com")], {})
    r = _client().put(
        "/api/admin/users/u1/status", json={"disabled": True}, headers=ADMIN_HEADERS
    )
    assert r.status_code == 409
    assert "IAP" in r.json()["detail"]
    assert fb.users["u1"].disabled is False
    assert fb.revoked == []


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
        # Diagnostic pass on the SAME dataset: must fold into
        # market_data_daily's status, never surface as a phantom source.
        # Shape matches the PRODUCER (audit_data_freshness.py:664): gap rows
        # carry a real ticker and a row count.
        {"table": "market_data_daily [gap]", "ticker": "SPY", "status": "stale",
         "last_row_at": None, "lag_hours": None, "expected_max_hours": None,
         "row_count_recent": 4},
        # Column-nullity diagnostic (dotted label, audit line 888): must fold
        # into strat_features_5m rather than surface as a phantom source.
        {"table": "strat_features_5m.vix_close", "ticker": None, "status": "stale",
         "last_row_at": None, "lag_hours": None, "expected_max_hours": None,
         "row_count_recent": None},
        {"table": "strat_features_5m", "ticker": "IWM", "status": "ok",
         "last_row_at": "2026-09-02", "lag_hours": 5.0, "expected_max_hours": 24,
         "row_count_recent": 70},
        # Enrichment-coverage check outside its window (audit line ~1027):
        # a skipped diagnostic must NOT degrade or annotate a live dataset.
        {"table": "market_data_daily.atr_14 enrichment coverage", "ticker": None,
         "status": "skipped", "last_row_at": None, "lag_hours": None,
         "expected_max_hours": None, "row_count_recent": None},
        {"table": "etf_options_snapshots", "ticker": "QQQ", "status": "warn",
         "last_row_at": "2026-09-01", "lag_hours": 26.0, "expected_max_hours": 30,
         "row_count_recent": None},
        # Job observability row — not a dataset; stays its own honest row.
        {"table": "job_runs.backfill-daily-indicators duration", "ticker": None,
         "status": "warn", "last_row_at": None, "lag_hours": None,
         "expected_max_hours": None, "row_count_recent": None},
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
    # The stale [gap] diagnostic folds into the dataset's status (Codex
    # PR #972 finding): the main row must NOT read ok while its gap scan
    # is stale — but the diagnostic contributes no counts/timestamps, and
    # its message keeps the audit label + ticker so a mid-window hole is
    # never mistaken for an ordinary lag.
    assert daily["status"] == "stale"
    assert "market_data_daily [gap] (SPY): stale" in daily["message"]
    assert daily["row_count"] == 3                      # real members only
    assert daily["last_refreshed_at"] == "2026-09-02"   # max across tickers
    assert daily["coverage_end"] == "2026-09-02"
    assert daily["coverage_start"] is None              # not computed → null
    assert daily["refreshable"] is True
    assert "market_data_daily [gap]" not in by_id       # no phantom source
    # A SKIPPED diagnostic (enrichment check outside its window) neither
    # degrades the dataset nor litters the message or the source list.
    assert "enrichment" not in (daily["message"] or "")
    assert "market_data_daily.atr_14 enrichment coverage" not in by_id

    # Dotted column-nullity diagnostics fold into their dataset too — the
    # NULL-cascade class the nullity check exists for must not hide behind
    # an ok dataset row.
    strat5 = by_id["strat_features_5m"]
    assert strat5["status"] == "stale"
    assert "strat_features_5m.vix_close: stale" in strat5["message"]
    assert strat5["row_count"] == 70                    # nullity row not counted
    assert "strat_features_5m.vix_close" not in by_id

    # Job observability rows are not datasets — they stay their own row.
    duration = by_id["job_runs.backfill-daily-indicators duration"]
    assert duration["status"] == "stale"                # warn → stale on wire
    assert duration["refreshable"] is False

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
    """The cooldown is a CROSS-INSTANCE DB lease (Codex PR #972 finding):
    the endpoint dispatches only after winning the lease, and a lost lease
    is a 429 with no dispatch — whatever instance served the press."""
    _as_admin(monkeypatch)
    dispatched: list[str] = []
    lease_results = iter([True, False])
    lease_calls: list[tuple[str, int]] = []

    def fake_lease(job, cooldown_s):
        lease_calls.append((job, cooldown_s))
        return next(lease_results)

    monkeypatch.setattr(admin_module, "_acquire_refresh_lease", fake_lease)
    monkeypatch.setattr(
        admin_module, "_run_refresh_job",
        lambda job: dispatched.append(job) or "fetch-market-data-abc12",
    )
    c = _client()
    r = c.post("/api/admin/data-sources/market_data_daily/refresh", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json() == {
        "id": "market_data_daily",
        "queued": True,
        "job_id": "fetch-market-data-abc12",
    }
    assert dispatched == ["fetch-market-data"]
    assert lease_calls[0] == ("fetch-market-data", admin_module._REFRESH_COOLDOWN_S)

    # Second press loses the lease: cooled down, no second execution.
    r2 = c.post("/api/admin/data-sources/market_data_daily/refresh", headers=ADMIN_HEADERS)
    assert r2.status_code == 429
    assert dispatched == ["fetch-market-data"]


def test_refresh_dispatch_failure_is_loud_503_and_releases_lease(monkeypatch):
    _as_admin(monkeypatch)
    released: list[str] = []
    monkeypatch.setattr(admin_module, "_acquire_refresh_lease", lambda job, cd: True)
    monkeypatch.setattr(
        admin_module, "_release_refresh_lease", lambda job: released.append(job)
    )

    def boom(job):
        raise RuntimeError("iam denied")

    monkeypatch.setattr(admin_module, "_run_refresh_job", boom)
    r = _client().post("/api/admin/data-sources/daily_rates/refresh", headers=ADMIN_HEADERS)
    assert r.status_code == 503
    # The lease is handed back so the retry isn't locked out for the cooldown.
    assert released == ["fetch-fred-rates"]


def test_refresh_lease_store_failure_is_loud_503_without_dispatch(monkeypatch):
    """No lease means no cost guard — the endpoint must refuse rather than
    dispatch unguarded."""
    _as_admin(monkeypatch)
    dispatched: list[str] = []

    def lease_down(job, cd):
        raise RuntimeError("db down")

    monkeypatch.setattr(admin_module, "_acquire_refresh_lease", lease_down)
    monkeypatch.setattr(
        admin_module, "_run_refresh_job", lambda job: dispatched.append(job) or "x"
    )
    r = _client().post("/api/admin/data-sources/daily_rates/refresh", headers=ADMIN_HEADERS)
    assert r.status_code == 503
    assert dispatched == []


def test_acquire_refresh_lease_maps_returning_row_to_bool(monkeypatch):
    """The lease helper's contract with Postgres: a RETURNING row means the
    upsert won (lease acquired), no row means the cooldown predicate blocked
    the takeover."""
    from unittest.mock import MagicMock, patch

    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False

    conn.execute.return_value.first.return_value = ("fetch-fred-rates",)
    with patch("gcp.database.get_engine", return_value=engine):
        assert admin_module._acquire_refresh_lease("fetch-fred-rates", 60) is True
    sql = str(conn.execute.call_args.args[0])
    assert "ON CONFLICT (job_name) DO UPDATE" in sql and "RETURNING" in sql
    assert conn.execute.call_args.args[1] == {"job": "fetch-fred-rates", "cooldown": 60}

    conn.execute.return_value.first.return_value = None
    with patch("gcp.database.get_engine", return_value=engine):
        assert admin_module._acquire_refresh_lease("fetch-fred-rates", 60) is False


def test_release_refresh_lease_ages_the_row_past_the_cooldown(monkeypatch):
    """The release helper's SQL contract: it UPDATEs the job's row to a
    dispatched_at older than the cooldown (never DELETEs — a delete would
    race a concurrent successful acquire), so a retry after a failed
    dispatch wins the next acquire instead of being locked out for 60s.
    Pins the statement shape end-to-end since the endpoint's cleanup path
    swallows release errors into a warning log."""
    from unittest.mock import MagicMock, patch

    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=engine):
        admin_module._release_refresh_lease("fetch-fred-rates")
    sql = str(conn.execute.call_args.args[0])
    assert "UPDATE admin_refresh_leases" in sql
    assert "SET dispatched_at = NOW() - make_interval(secs => :cooldown)" in sql
    assert "WHERE job_name = :job" in sql
    assert "DELETE" not in sql
    assert conn.execute.call_args.args[1] == {
        "job": "fetch-fred-rates",
        "cooldown": admin_module._REFRESH_COOLDOWN_S + 1,
    }
