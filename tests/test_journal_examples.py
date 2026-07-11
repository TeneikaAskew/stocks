"""Task 1 (journal one-stop-shop) — GET /api/journal/examples/{ticker}.

Read-only teaching layer: every signed-in user sees the ADMIN's own
journal_entries rows for a ticker, in the exact JSON shape of
GET /api/journal/trades/{ticker}. Admin identity is a server-side constant
(`journal_module._ADMIN_EMAIL`), never derived from the caller — this is the
whole point of the endpoint (same examples regardless of who's asking).

task-examples-union (2026-07-11, user decision): the endpoint now UNIONS the
admin journal_entries rows above with ALL automated-pipeline `trades` rows
for the ticker (the trading_analysis.py dataset), mapped to the same trade
JSON shape and labeled `source: 'pipeline'`. Two SQL queries total (one per
source table, never per-row) — see `_make_fake_query` below, which now
serves BOTH shapes: a `journal_entries` query (as before) and a `trades`
(pipeline) query, distinguished by SQL text ("from trades" without
"journal_entries").

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
    # task-examples-union: an admin-authored IWM row, used alongside the
    # IWM pipeline fixture below (_ALL_PIPELINE_ROWS) to test the union's
    # cross-source ordering. Its entry_ts (09:00) sits BEFORE both pipeline
    # rows (09:31, 10:00) so the union's entry_ts-DESC sort must put it last.
    {
        "id": "admin-iwm-1", "ticker": "IWM", "direction": "CALL",
        "entry_ts": pd.Timestamp("2026-07-05T09:00:00"),
        "exit_ts": pd.Timestamp("2026-07-05T09:20:00"),
        "entry_price": 598.0, "exit_price": 601.0, "return_pct": 0.5,
        "notes": "admin IWM example", "stop_loss": None,
        "tp1": None, "tp2": None, "tp3": None,
        "status": "win", "source": "manual", "session_id": None,
        "created_at": pd.Timestamp("2026-07-05T09:00:00"),
        "user_email": ADMIN_EMAIL,
    },
])

# task-examples-union: fixture for the automated-pipeline `trades` table
# (gcp/schema.sql:1065). Scoped to ticker IWM only so every PRE-EXISTING
# SPY/ZZZZ-ticker test above sees an empty pipeline result (no fixture
# overlap) and is byte-for-byte unaffected by the union — only the new
# union-specific tests below query IWM.
#
# pipe-9001 (id=9001): a CLOSED win — entry 09:31, exit 09:45, return_pct
# 0.01 is a RAW FRACTION (1.00% once the endpoint's ×100 conversion runs),
# exit_reason + strat_combo both present (tests the " · "-joined notes).
#
# pipe-9002 (id=9002): an ACTIVE trade (real production shape for an
# unexited pipeline row) — exit_ts/exit_price/return_pct/exit_reason/
# strat_combo are ALL NaT/None, its entry_ts (10:00) is the LATEST of the
# three IWM rows so it must sort first in the union.
_ALL_PIPELINE_ROWS = pd.DataFrame([
    {
        "id": 9001, "ticker": "IWM", "direction": "CALL",
        "entry_ts": pd.Timestamp("2026-07-05T09:31:00"),
        "exit_ts": pd.Timestamp("2026-07-05T09:45:00"),
        "entry_price": 600.0, "exit_price": 606.0,
        "return_pct": 0.01,
        "exit_reason": "target_hit", "strat_combo": "2U-2D",
    },
    {
        "id": 9002, "ticker": "IWM", "direction": "PUT",
        "entry_ts": pd.Timestamp("2026-07-05T10:00:00"),
        "exit_ts": pd.NaT,
        "entry_price": 605.0, "exit_price": None,
        "return_pct": None,
        "exit_reason": None, "strat_combo": None,
    },
])


def _is_pipeline_sql(sql: str) -> bool:
    """Distinguishes the pipeline `trades`-table query from the
    `journal_entries` query by SQL text (task-examples-union) — the
    endpoint's pipeline SELECT reads `FROM trades` and never mentions
    `journal_entries`, while the admin SELECT always reads
    `FROM journal_entries`.
    """
    sql_lower = sql.lower()
    return "from trades" in sql_lower and "journal_entries" not in sql_lower


def _make_fake_query(calls: list):
    """Fake `_journal_query`: filters `_ALL_ROWS` (journal_entries) by bound
    params, applies the `source IS DISTINCT FROM 'replay'` exclusion only
    when the literal SQL text carries it (i.e. only the examples endpoint's
    admin query, not the trades GET's), and — task-examples-union — ALSO
    serves the pipeline `trades`-table query (`_is_pipeline_sql`) from
    `_ALL_PIPELINE_ROWS`, filtered by ticker only (no user scoping — the
    pipeline table has no owner column).

    For the examples query (which has "replay" in the SQL), also asserts that
    the SQL text contains both the user_email and ticker predicates — this
    catches mutations that drop those WHERE clauses.
    """

    def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        params = params or {}

        if _is_pipeline_sql(sql):
            assert "ticker = :ticker" in sql, \
                f"pipeline SQL must include 'ticker = :ticker' predicate, got: {sql}"
            df = _ALL_PIPELINE_ROWS.copy()
            if "ticker" in params:
                df = df[df["ticker"] == params["ticker"]]
            return df.drop(columns=["ticker"]).reset_index(drop=True)

        df = _ALL_ROWS.copy()

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

    # Exactly two SQL queries issued (one per source table, task-examples-
    # union — never per-row), and the admin query's SQL text itself encodes
    # the exclusion (not just the test fixture). The admin (journal_entries)
    # query runs first — see get_examples.
    assert len(calls) == 2
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
    # Two queries now (admin + pipeline, task-examples-union); the admin
    # query is calls[0] (see get_examples).
    assert len(calls) == 2
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


# ── task-examples-union: admin journal_entries UNION pipeline trades ───────
#
# Uses ticker IWM throughout — _ALL_PIPELINE_ROWS and the admin-iwm-1 fixture
# row are scoped to IWM only, so every test above (all SPY/ZZZZ) is
# untouched by the union: their pipeline query always finds zero rows.


def test_examples_union_contains_both_sources_ordered_desc(monkeypatch, cloud_sql_client):
    """Union of admin + pipeline rows for one ticker, sorted entry_ts DESC
    across BOTH sources (not just within each) — exactly two SQL queries."""
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))

    r = cloud_sql_client.get("/api/journal/examples/IWM")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3

    ids = [t["id"] for t in body["trades"]]
    # pipe-9002 (entry 10:00) > pipe-9001 (entry 09:31) > admin-iwm-1 (09:00).
    assert ids == ["pipe-9002", "pipe-9001", "admin-iwm-1"]

    sources = {t["id"]: t["source"] for t in body["trades"]}
    assert sources["pipe-9001"] == "pipeline"
    assert sources["pipe-9002"] == "pipeline"
    assert sources["admin-iwm-1"] == "manual"

    # One SQL per source table (never per-row): admin journal_entries query
    # + pipeline trades query, total 2.
    assert len(calls) == 2


def test_examples_pipeline_row_field_mapping(monkeypatch, cloud_sql_client):
    """Closed pipeline row (pipe-9001) maps id/return_pct/notes/status/
    take_profits/stop_loss/source exactly per the union spec."""
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query([]))

    r = cloud_sql_client.get("/api/journal/examples/IWM")
    trades = {t["id"]: t for t in r.json()["trades"]}
    pipe1 = trades["pipe-9001"]

    assert pipe1["direction"] == "CALL"
    assert pipe1["entry_price"] == 600.0
    assert pipe1["exit_price"] == 606.0
    # return_pct is a RAW FRACTION on the source table (0.01) -> ×100 = 1.0,
    # matching the TRUE-PERCENT convention every other journal row uses.
    assert pipe1["return_pct"] == 1.0
    assert pipe1["notes"] == "target_hit · 2U-2D"
    assert pipe1["take_profits"] == []
    assert pipe1["stop_loss"] is None
    assert pipe1["status"] == "win"
    assert pipe1["source"] == "pipeline"
    assert pipe1["ticker"] == "IWM"


def test_examples_pipeline_active_row_null_exit_maps_to_active(monkeypatch, cloud_sql_client):
    """An un-exited pipeline row (pipe-9002: NULL exit_ts/exit_price/
    return_pct/exit_reason/strat_combo) maps to status 'active' with a null
    return_pct — never a fabricated 0/closed (CLAUDE.md Rule 3.7)."""
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query([]))

    r = cloud_sql_client.get("/api/journal/examples/IWM")
    trades = {t["id"]: t for t in r.json()["trades"]}
    pipe2 = trades["pipe-9002"]

    assert pipe2["exit_ts"] is None
    assert pipe2["exit_price"] is None
    assert pipe2["return_pct"] is None
    assert pipe2["status"] == "active"
    assert pipe2["notes"] == ""
    assert pipe2["take_profits"] == []
    assert pipe2["stop_loss"] is None
    assert pipe2["source"] == "pipeline"


def test_examples_union_replay_exclusion_still_applies_to_journal_rows_only(
    monkeypatch, cloud_sql_client
):
    """The `source IS DISTINCT FROM 'replay'` exclusion still applies to the
    admin journal_entries half of the union (SPY: admin-replay-1 excluded);
    pipeline rows have no 'replay' concept and are unaffected."""
    calls: list = []
    monkeypatch.setattr(journal_module, "_journal_query", _make_fake_query(calls))

    r = cloud_sql_client.get("/api/journal/examples/SPY")
    assert r.status_code == 200
    body_trades = r.json()["trades"]
    ids = {t["id"] for t in body_trades}
    assert "admin-replay-1" not in ids
    assert "admin-manual-1" in ids
    # SPY has no pipeline fixture rows -> the union is admin-only here, same
    # membership as the pre-union endpoint.
    assert all(t["source"] != "pipeline" for t in body_trades)


def test_examples_503_when_pipeline_query_fails(monkeypatch, cloud_sql_client):
    """A real pipeline-query failure fails the WHOLE endpoint loud (503) —
    never a silent degrade to admin-only rows (CLAUDE.md Rule 3.7)."""
    inner = _make_fake_query([])

    def flaky(sql, params=None):
        if _is_pipeline_sql(sql):
            raise RuntimeError("pipeline db down")
        return inner(sql, params)

    monkeypatch.setattr(journal_module, "_journal_query", flaky)
    r = cloud_sql_client.get("/api/journal/examples/IWM")
    assert r.status_code == 503
    assert r.json()["detail"] == "journal temporarily unavailable"
