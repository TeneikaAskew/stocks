"""Task 3 (journal one-stop-shop) — broker-import preview/commit endpoints.

POST /api/journal/import/preview  — multipart CSV upload -> parse (lib.broker_import
  detect_broker/parse_csv) -> FIFO-pair (pair_orders) -> flag duplicates against
  this user's existing journal_entries. Never writes.
POST /api/journal/import/commit   — {broker, trades:[selected PairedTrade dicts]}
  -> re-checks duplicates server-side (idempotent) -> inserts via the SAME insert
  path POST /api/journal/trades uses, source='import:<broker>', owner ALWAYS the
  authenticated caller.

Scaffold mirrors tests/test_journal_phase2.py / tests/test_journal_examples.py:
sys.path setup + chdir-guarded import of `api.main` / `api.routers.journal`, a
real TestClient(main.app) so router logic AND auth middleware are both
exercised end to end, and a `client_local_owner` fixture (force `_HAS_CLOUD_SQL`
False + redirect `LOCAL_JOURNAL_DIR` to tmp_path) for the local/open-mode
happy-path tests -- hermetic, no Cloud SQL mocking required for those.
"""
import json
import os
import sys
from pathlib import Path

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

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "broker_csv"


@pytest.fixture
def client_local_owner(monkeypatch, tmp_path):
    """TestClient exercising the local/open-mode JSON-file branch (no Cloud
    SQL, no auth). Same convention as tests/test_journal_phase2.py."""
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", False)
    monkeypatch.setattr(journal_module, "LOCAL_JOURNAL_DIR", tmp_path)
    return TestClient(main.app)


def _upload_robinhood(client, **extra_data):
    with open(FIXTURES / "robinhood_sample.csv", "rb") as f:
        return client.post(
            "/api/journal/import/preview",
            files={"file": ("robinhood_sample.csv", f, "text/csv")},
            data=extra_data,
        )


# ── (a) preview parses fixture upload end-to-end ────────────────────────────


def test_preview_parses_robinhood_fixture_end_to_end(client_local_owner):
    r = _upload_robinhood(client_local_owner)
    assert r.status_code == 200
    body = r.json()
    assert body["broker"] == "robinhood"

    trades = body["trades"]
    # Fixture: IWM BTO/STC (closed), SPY BTO/STC (closed), QQQ BTO only (active).
    assert len(trades) == 3
    by_ticker = {t["ticker"]: t for t in trades}
    assert set(by_ticker) == {"IWM", "SPY", "QQQ"}

    iwm = by_ticker["IWM"]
    assert iwm["status"] == "closed"
    assert iwm["entry_price"] == pytest.approx(1.42)
    assert iwm["exit_price"] == pytest.approx(1.71)
    assert iwm["return_pct"] == pytest.approx(20.42, abs=0.01)
    assert iwm["duplicate"] is False

    qqq = by_ticker["QQQ"]
    assert qqq["status"] == "active"
    assert qqq["exit_ts"] is None
    assert qqq["exit_price"] is None
    assert qqq["return_pct"] is None
    assert qqq["duplicate"] is False

    # Every dropped row lands in skipped with a reason (Rule 3.7) — shares row,
    # short-option (STO) row, and the two non-trade activity rows (CDIV, ACH).
    reasons = {s["reason"] for s in body["skipped"]}
    assert "shares — options only in v1" in reasons
    assert "short options not supported" in reasons
    assert len(body["skipped"]) == 4


def test_preview_never_writes_anything(client_local_owner, tmp_path):
    _upload_robinhood(client_local_owner)
    # No local journal files should have been created by a preview-only call.
    assert list(tmp_path.glob("*_journal.json")) == []


# ── (b) duplicate flagged when a matching row pre-exists ───────────────────


def test_preview_flags_duplicate_against_existing_local_entry(client_local_owner):
    # Pre-seed a local journal row matching the IWM round-trip's entry leg
    # exactly (ticker, entry_ts, entry_price, direction) — the dedupe key.
    journal_module._save_local("IWM", [{
        "id": "pre-existing-1",
        "ticker": "IWM",
        "direction": "CALL",
        "entry_ts": "2026-06-01T00:00:00",
        "exit_ts": "2026-06-03T00:00:00",
        "entry_price": 1.42,
        "exit_price": 1.71,
        "return_pct": 20.42,
        "notes": "",
        "status": "win",
        "source": "manual",
    }])

    r = _upload_robinhood(client_local_owner)
    assert r.status_code == 200
    by_ticker = {t["ticker"]: t for t in r.json()["trades"]}
    assert by_ticker["IWM"]["duplicate"] is True
    # SPY / QQQ are NOT pre-seeded — must not be flagged.
    assert by_ticker["SPY"]["duplicate"] is False
    assert by_ticker["QQQ"]["duplicate"] is False


def test_preview_duplicate_detection_cloud_sql(monkeypatch):
    """Same dedupe semantics through the Cloud-SQL branch: one batched SELECT
    (ticker = ANY(:tickers)), not a per-trade query."""
    import pandas as pd

    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
    monkeypatch.setattr(journal_module, "current_user_email", lambda req: "alice@x.com")

    calls: list = []

    def fake_query(sql, params=None):
        calls.append((sql, params or {}))
        return pd.DataFrame([{
            "ticker": "IWM", "direction": "CALL", "entry_price": 1.42,
            "entry_ts": pd.Timestamp("2026-06-01T00:00:00"),
        }])

    monkeypatch.setattr(journal_module, "_journal_query", fake_query)

    client = TestClient(main.app)
    r = _upload_robinhood(client)
    assert r.status_code == 200
    by_ticker = {t["ticker"]: t for t in r.json()["trades"]}
    assert by_ticker["IWM"]["duplicate"] is True
    assert by_ticker["SPY"]["duplicate"] is False

    assert len(calls) == 1
    sql_text = calls[0][0]
    assert "ANY(:tickers)" in sql_text
    assert calls[0][1]["user_email"] == "alice@x.com"


# ── (c) commit inserts + idempotent second identical commit ────────────────


def _commit_body_from_preview(preview_json):
    return {
        "broker": preview_json["broker"],
        "trades": preview_json["trades"],
    }


def test_commit_inserts_then_second_identical_commit_is_idempotent(client_local_owner):
    preview = _upload_robinhood(client_local_owner).json()
    body = _commit_body_from_preview(preview)

    r1 = client_local_owner.post("/api/journal/import/commit", json=body)
    assert r1.status_code == 200
    assert r1.json() == {"imported": 3, "skipped_duplicates": 0}

    r2 = client_local_owner.post("/api/journal/import/commit", json=body)
    assert r2.status_code == 200
    assert r2.json() == {"imported": 0, "skipped_duplicates": 3}


def test_commit_writes_source_import_broker(client_local_owner):
    preview = _upload_robinhood(client_local_owner).json()
    body = _commit_body_from_preview(preview)
    client_local_owner.post("/api/journal/import/commit", json=body)

    r = client_local_owner.get("/api/journal/trades/IWM")
    trades = r.json()["trades"]
    assert len(trades) == 1
    assert trades[0]["source"] == "import:robinhood"


# ── (d) active trades commit with null exit; GET returns them active ───────


def test_commit_active_trade_has_null_exit_and_get_shows_active(client_local_owner):
    preview = _upload_robinhood(client_local_owner).json()
    body = _commit_body_from_preview(preview)
    r = client_local_owner.post("/api/journal/import/commit", json=body)
    assert r.json()["imported"] == 3

    r_get = client_local_owner.get("/api/journal/trades/QQQ")
    assert r_get.status_code == 200
    trades = r_get.json()["trades"]
    assert len(trades) == 1
    assert trades[0]["status"] == "active"
    assert trades[0]["exit_ts"] is None
    assert trades[0]["exit_price"] is None
    assert trades[0]["return_pct"] is None


# ── (e) auth required ───────────────────────────────────────────────────────


def test_import_endpoints_require_auth(monkeypatch, tmp_path):
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
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", False)
    monkeypatch.setattr(journal_module, "LOCAL_JOURNAL_DIR", tmp_path)

    client = TestClient(main.app)

    # Unauthenticated -> 401 on both endpoints.
    r_preview_noauth = _upload_robinhood(client)
    assert r_preview_noauth.status_code == 401

    r_commit_noauth = client.post(
        "/api/journal/import/commit",
        json={"broker": "robinhood", "trades": []},
    )
    assert r_commit_noauth.status_code == 401

    # Authenticated -> 200 on both.
    headers = {"authorization": "Bearer good:trader@x.com"}
    r_preview_auth = _upload_robinhood(client, **{})
    r_preview_auth = client.post(
        "/api/journal/import/preview",
        files={"file": ("robinhood_sample.csv", open(FIXTURES / "robinhood_sample.csv", "rb"), "text/csv")},
        headers=headers,
    )
    assert r_preview_auth.status_code == 200

    r_commit_auth = client.post(
        "/api/journal/import/commit",
        json={"broker": "robinhood", "trades": []},
        headers=headers,
    )
    assert r_commit_auth.status_code == 200
    assert r_commit_auth.json() == {"imported": 0, "skipped_duplicates": 0}


# ── (f) 5,000-row cap -> 413 ────────────────────────────────────────────────


def test_preview_413_when_csv_exceeds_row_cap(client_local_owner):
    cap = journal_module.MAX_IMPORT_ROWS
    header = "sym,dir,act,when,px,qty\n"
    row = "IWM,CALL,open,2026-06-01 09:30,1.42,1\n"
    text = header + row * (cap + 1)
    mapping = {
        "ticker": "sym", "direction": "dir", "action": "act",
        "ts": "when", "price": "px", "quantity": "qty",
    }
    r = client_local_owner.post(
        "/api/journal/import/preview",
        files={"file": ("big.csv", text.encode("utf-8"), "text/csv")},
        data={"broker": "generic", "mapping": json.dumps(mapping)},
    )
    assert r.status_code == 413


def test_preview_at_cap_is_not_rejected(client_local_owner):
    cap = journal_module.MAX_IMPORT_ROWS
    header = "sym,dir,act,when,px,qty\n"
    row = "IWM,CALL,open,2026-06-01 09:30,1.42,1\n"
    text = header + row * cap
    mapping = {
        "ticker": "sym", "direction": "dir", "action": "act",
        "ts": "when", "price": "px", "quantity": "qty",
    }
    r = client_local_owner.post(
        "/api/journal/import/preview",
        files={"file": ("atcap.csv", text.encode("utf-8"), "text/csv")},
        data={"broker": "generic", "mapping": json.dumps(mapping)},
    )
    assert r.status_code == 200


def test_commit_413_when_trades_exceed_row_cap(client_local_owner):
    cap = journal_module.MAX_IMPORT_ROWS
    trade = {
        "ticker": "IWM", "direction": "CALL", "entry_ts": "2026-06-01 09:30",
        "entry_price": 1.42, "quantity": 1, "status": "active",
    }
    r = client_local_owner.post(
        "/api/journal/import/commit",
        json={"broker": "generic", "trades": [trade] * (cap + 1)},
    )
    assert r.status_code == 413
