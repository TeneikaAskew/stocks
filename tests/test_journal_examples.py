"""Task 1 (journal one-stop-shop) — GET /api/journal/examples/{ticker}.

Read-only teaching layer: every signed-in user sees the ADMIN's own
journal_entries rows for a ticker, in the exact JSON shape of
GET /api/journal/trades/{ticker}. Admin identity is a server-side constant
(`journal_module._ADMIN_EMAIL`), never derived from the caller — this is the
whole point of the endpoint (same examples regardless of who's asking).

Scaffold mirrors tests/test_journal_phase2.py: sys.path setup + chdir-guarded
import of `api.main` / `api.routers.journal`, then a real `TestClient(main.app)`
so both the router logic AND the auth middleware (registered on `main.app`)
are exercised end to end.

Hermetic: `_journal_query` is monkeypatched to a tiny in-memory "DB" that
mimics the two predicates the real SQL relies on --- `ticker`/`user_email`
equality (bound params) and the `source IS DISTINCT FROM 'replay'` exclusion
(detected from the literal SQL text, the same way a real Postgres WHERE would
apply it). This lets the tests prove the endpoint (a) scopes to the admin
identity server-side, (b) excludes replay rows, and (c) never leaks another
user's rows -- without a real Cloud SQL connection.
"""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api import main
    from api.routers import journal as journal_module
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient  # noqa: E402

ADMIN_EMAIL = "teneika@bictech.org"  # matches journal_module._ADMIN_EMAIL default
OTHER_USER = "other@x.com"

# A tiny in-memory "table" standing in for `journal_entries`. Columns beyond
# what the real SELECT projects (`user_email`) are stripped before the fake
# query returns, exactly like a real SELECT would never leak them.
_ALL_ROWS = pd.DataFrame([
    {
        "id": "admin-manual-1", "ticker": "SPY", "direction": "CALL",
        "entry_ts": pd.Timestamp("2026-07-01T09:30:00"),
        "exit_ts": pd.Timestamp("2026-07-01T09:45:00"),
        "entry_price": 600.0, "exit_price": 605.0, "return_pct": 0.83,
        "notes": "teaching example", "stop_loss": 598.0,
        "tp1": 602.0, "tp2": None, "tp3": None,
        "status": "win", "source": "manual", "session_id": None,
        "created_at": pd.Timestamp("2026-07-01T09:30:00"),
        "user_email": ADMIN_EMAIL,
    },
    {
        "id": "admin-replay-1", "ticker": "SPY", "direction": "PUT",
        "entry_ts": pd.Timestamp("2026-07-01T10:00:00"),
        "exit_ts": pd.Timestamp("2026-07-01T10:15:00"),
        "entry_price": 610.0, "exit_price": 609.0, "return_pct": 0.16,
        "notes": "practice replay", "stop_loss": None,
        "tp1": None, "tp2": None, "tp3": None,
        "status": "win", "source": "replay", "session_id": "sess-1",
        "created_at": pd.Timestamp("2026-07-01T10:00:00"),
        "user_email": ADMIN_EMAIL,
    },
    {
        "id": "admin-null-source-1", "ticker": "SPY", "direction": "PUT",
        "entry_ts": pd.Timestamp("2026-07-01T10:30:00"),
        "exit_ts": pd.Timestamp("2026-07-01T10:45:00"),
        "entry_price": 612.0, "exit_price": 611.0, "return_pct": 0.16,
        "notes": "NULL source row (test IS DISTINCT FROM)", "stop_loss": None,
        "tp1": None, "tp2": None, "tp3": None,
        "status": "win", "source": None, "session_id": None,
        "created_at": pd.Timestamp("2026-07-01T10:30:00"),
        "user_email": ADMIN_EMAIL,
    },
    {
        "id": "other-user-1", "ticker": "SPY", "direction": "CALL",
        "entry_ts": pd.Timestamp("2026-07-01T11:00:00"),
        "exit_ts": pd.Timestamp("2026-07-01T11:30:00"),
        "entry_price": 611.0, "exit_price": 612.0, "return_pct": 0.16,
        "notes": "not admin's trade", "stop_loss": None,
        "tp1": None, "tp2": None, "tp3": None,
        "status": "win", "source": "manual", "session_id": None,
        "created_at": pd.Timestamp("2026-07-01T11:00:00"),
        "user_email": OTHER_USER,
    },
])


def _make_fake_query(calls: list):
    """Fake `_journal_query`: filters `_ALL_ROWS` by bound params, and applies
    the `source IS DISTINCT FROM 'replay'` exclusion only when the literal SQL
    text carries it (i.e. only the examples endpoint's query, not the trades
    GET's).

    For the examples query (which has "replay" in the SQL), also asserts that
    the SQL text contains both the user_email and ticker predicates — this
    catches mutations that drop those WHERE clauses.
    """

    def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        df = _ALL_ROWS.copy()
        params = params or {}

        # Filter by ticker if bound
        if "ticker" in params:
            df = df[df["ticker"] == params["ticker"]]

        # Filter by user_email if bound
        if "user_email" in params:
            df = df[df["user_email"] == params["user_email"]]

        # If this is the examples endpoint (has "replay" in SQL), apply the
        # IS DISTINCT FROM 'replay' exclusion and assert the predicates
        # are present in the SQL text (not just in params).
        if "replay" in sql.lower():
            # FIX 1: Assert both predicates are in the SQL text. Dropping
            # "AND user_email = :user_email" or "AND ticker = :ticker" from
            # the endpoint's SQL would pass a test that only checked params,
            # so we check the literal SQL instead.
            assert "user_email = :user_email" in sql, \
                f"examples SQL must include 'user_email = :user_email' predicate, got: {sql}"
            assert "ticker = :ticker" in sql, \
                f"examples SQL must include 'ticker = :ticker' predicate, got: {sql}"

            # FIX 2: Implement IS DISTINCT FROM 'replay' correctly.
            # IS DISTINCT FROM returns True when:
            #  - one side is NULL and the other is not (e.g., NULL IS DISTINCT FROM 'replay' = True)
            #  - both are non-NULL and different (e.g., 'manual' IS DISTINCT FROM 'replay' = True)
            # This is different from != which treats NULL != 'replay' as NULL (false in WHERE).
            # So we keep rows where source is NULL or source != 'replay'.
            df = df[df["source"].isna() | (df["source"] != "replay")]

        return df.drop(columns=["user_email"]).reset_index(drop=True)

    return fake_query


@pytest.fixture
def cloud_sql_client(monkeypatch):
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
    return TestClient(main.app)


# ── (a) same field set as trades GET ────────────────────────────────────────


def test_examples_same_field_set_as_trades_get(monkeypatch, cloud_sql_client):
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))
    # trades GET is scoped to whoever is asking; make that the admin so the
    # trades-GET SQL (ticker+user_email, no source filter) also matches a row.
    monkeypatch.setattr(journal_module, "current_user_email", lambda req: ADMIN_EMAIL)

    r_examples = cloud_sql_client.get("/api/journal/examples/SPY")
    r_trades = cloud_sql_client.get("/api/journal/trades/SPY")
    assert r_examples.status_code == 200
    assert r_trades.status_code == 200

    examples_trades = r_examples.json()["trades"]
    trades_trades = r_trades.json()["trades"]
    assert len(examples_trades) >= 1
    assert len(trades_trades) >= 1
    assert set(examples_trades[0].keys()) == set(trades_trades[0].keys())

    # Also pins the outer envelope shape.
    assert set(r_examples.json().keys()) == {"ticker", "source", "count", "trades"}


# ── (b) excludes source='replay' rows ───────────────────────────────────────


def test_examples_excludes_replay_rows(monkeypatch, cloud_sql_client):
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))

    r = cloud_sql_client.get("/api/journal/examples/SPY")
    assert r.status_code == 200
    body = r.json()
    ids = {t["id"] for t in body["trades"]}
    assert "admin-manual-1" in ids
    assert "admin-replay-1" not in ids
    assert all(t.get("source") != "replay" for t in body["trades"])

    # Exactly one SQL query issued (no per-row queries), and the SQL text
    # itself encodes the exclusion (not just the test fixture).
    assert len(calls) == 1
    sql_text = calls[0][0].lower()
    assert "replay" in sql_text


# ── (c) NULL-source rows are included (IS DISTINCT FROM semantics) ───────────


def test_examples_includes_null_source_rows(monkeypatch, cloud_sql_client):
    """IS DISTINCT FROM 'replay' includes NULL, unlike != 'replay'.

    A mutation from IS DISTINCT FROM to != 'replay' would exclude the
    admin-null-source-1 row. This test catches that.
    """
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))

    r = cloud_sql_client.get("/api/journal/examples/SPY")
    assert r.status_code == 200
    body = r.json()
    ids = {t["id"] for t in body["trades"]}
    # Both manual and NULL-source rows are included; replay is excluded.
    assert "admin-manual-1" in ids
    assert "admin-null-source-1" in ids
    assert "admin-replay-1" not in ids

    # Verify the SQL uses IS DISTINCT FROM (not !=) so NULL is included.
    assert len(calls) == 1
    sql_text = calls[0][0]
    assert "IS DISTINCT FROM 'replay'" in sql_text


# ── (d) another user's rows never appear, regardless of caller identity ────


def test_examples_never_leaks_other_users_rows(monkeypatch, cloud_sql_client):
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))
    # Simulate a DIFFERENT signed-in user asking -- examples must still only
    # ever return the admin's rows, never the caller's own identity's rows,
    # and never the unrelated other-user's row.
    monkeypatch.setattr(journal_module, "current_user_email", lambda req: OTHER_USER)

    r = cloud_sql_client.get("/api/journal/examples/SPY")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()["trades"]}
    assert "other-user-1" not in ids
    # Both admin-manual-1 (source='manual') and admin-null-source-1 (source=NULL)
    # are included because the examples SQL uses IS DISTINCT FROM 'replay'
    # (which includes NULL), not != 'replay'.
    assert ids == {"admin-manual-1", "admin-null-source-1"}

    # The bound query param must be the server-side admin constant, not the
    # caller's identity.
    assert calls[0][1].get("user_email") == journal_module._ADMIN_EMAIL
    assert calls[0][1].get("user_email") != OTHER_USER


# ── (e) requires auth exactly like the trades GET ───────────────────────────


def test_examples_requires_auth_like_trades_get(monkeypatch):
    import api.auth as auth_module

    monkeypatch.setenv("AUTH_OPEN_SIGNUP", "1")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "")
    monkeypatch.setattr(auth_module, "AUTH_MODE", "firebase")

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

    monkeypatch.setattr(auth_module, "_verify_bearer_email", fake_verify)
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query([]))

    client = TestClient(main.app)

    r_examples_noauth = client.get("/api/journal/examples/SPY")
    r_trades_noauth = client.get("/api/journal/trades/SPY")
    assert r_examples_noauth.status_code == 401
    assert r_trades_noauth.status_code == 401
    assert r_examples_noauth.status_code == r_trades_noauth.status_code

    headers = {"authorization": "Bearer good:trader@x.com"}
    r_examples_auth = client.get("/api/journal/examples/SPY", headers=headers)
    r_trades_auth = client.get("/api/journal/trades/SPY", headers=headers)
    assert r_examples_auth.status_code == 200
    assert r_trades_auth.status_code == 200


# ── (f) unknown ticker -> empty trades, count 0 ─────────────────────────────


def test_examples_unknown_ticker_returns_empty(monkeypatch, cloud_sql_client):
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))

    r = cloud_sql_client.get("/api/journal/examples/ZZZZ")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "ZZZZ"
    assert body["count"] == 0
    assert body["trades"] == []


# ── DB-unavailable envelope parity (Rule 3.7) ───────────────────────────────


def test_examples_503_on_db_query_failure(monkeypatch, cloud_sql_client):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(journal_module, "_journal_query", boom)
    r = cloud_sql_client.get("/api/journal/examples/SPY")
    assert r.status_code == 503
    assert r.json()["detail"] == "journal temporarily unavailable"


def test_examples_503_when_cloud_sql_not_configured(monkeypatch):
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", False)
    client = TestClient(main.app)
    r = client.get("/api/journal/examples/SPY")
    assert r.status_code == 503
    assert r.json()["detail"] == "journal temporarily unavailable"
