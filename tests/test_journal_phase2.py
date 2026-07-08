"""Task 2.2 — journal API extensions: active trades w/ TP/SL, close PATCH,
admin seed layer.

Local/open-mode focus for create/PATCH: LOCAL_JOURNAL_DIR redirected to
tmp_path and `_HAS_CLOUD_SQL` forced False, driving requests through a real
TestClient (so FastAPI's own request validation — e.g. take-profits capped
at 3 — fires exactly as it does in production, unlike calling the router
function directly). The seed endpoint is Cloud-SQL only, so its tests flip
`_HAS_CLOUD_SQL` True and monkeypatch the `_seed_query` indirection.

Also regression-covers the 2.1 handoff bug: an active trade's null
exit_ts/exit_price/return_pct must reach the client as real JSON null, never
the literal string "NaT" that `.astype(str)` on a NaT produces.
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


@pytest.fixture
def client_local_owner(monkeypatch, tmp_path):
    """TestClient exercising the local/open-mode JSON-file branch.

    Forces `_HAS_CLOUD_SQL` False and redirects `LOCAL_JOURNAL_DIR` to
    tmp_path so tests never touch the real data/journal/ directory.
    """
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", False)
    monkeypatch.setattr(journal_module, "LOCAL_JOURNAL_DIR", tmp_path)
    return TestClient(main.app)


def _create(client, **overrides):
    body = {
        "ticker": "SPY",
        "direction": "CALL",
        "entry_date": "2026-07-02",
        "entry_time": "10:15",
        "entry_price": 620.5,
    }
    body.update(overrides)
    return client.post("/api/journal/trades", json=body)


# ── Active-trade creation ────────────────────────────────────────────────────


def test_create_active_trade_without_exit_returns_null_return_pct(client_local_owner):
    r = _create(
        client_local_owner,
        stop_loss=619.0,
        take_profits=[621.2, 622.0, 623.1],
        source="chart",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["return_pct"] is None
    assert body["status"] == "active"


def test_take_profits_capped_at_three(client_local_owner):
    r = _create(client_local_owner, take_profits=[1.0, 2.0, 3.0, 4.0])
    assert r.status_code == 422


# ── PATCH close ──────────────────────────────────────────────────────────────


def test_patch_close_computes_percent_return_and_status(client_local_owner):
    created = _create(client_local_owner).json()
    tid = created["id"]
    r = client_local_owner.patch(
        f"/api/journal/trades/{tid}",
        json={"exit_date": "2026-07-02", "exit_time": "10:45", "exit_price": 621.74},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "win"
    assert body["return_pct"] == pytest.approx(
        (621.74 - 620.5) / 620.5 * 100, rel=1e-6
    )


def test_patch_close_conflicts_on_already_closed(client_local_owner):
    created = _create(client_local_owner).json()
    tid = created["id"]
    client_local_owner.patch(
        f"/api/journal/trades/{tid}",
        json={"exit_date": "2026-07-02", "exit_time": "10:45", "exit_price": 621.74},
    )
    r2 = client_local_owner.patch(
        f"/api/journal/trades/{tid}",
        json={"exit_date": "2026-07-02", "exit_time": "11:00", "exit_price": 625.0},
    )
    assert r2.status_code == 409


def test_patch_close_404_for_unknown_trade(client_local_owner):
    r = client_local_owner.patch(
        "/api/journal/trades/does-not-exist",
        json={"exit_date": "2026-07-02", "exit_time": "10:45", "exit_price": 621.74},
    )
    assert r.status_code == 404


# ── GET list: real null, not "NaT" ──────────────────────────────────────────


def test_get_list_emits_real_null_not_nat_for_active_trade(client_local_owner):
    _create(client_local_owner, stop_loss=619.0, take_profits=[621.2])
    r = client_local_owner.get("/api/journal/trades/SPY")
    assert r.status_code == 200
    trades = r.json()["trades"]
    assert len(trades) == 1
    assert trades[0]["exit_ts"] is None
    assert trades[0]["exit_price"] is None
    assert trades[0]["return_pct"] is None
    assert trades[0]["exit_ts"] != "NaT"


def test_get_list_cloud_sql_emits_real_null_not_nat(monkeypatch):
    """Same regression, but through the Cloud-SQL branch: a NaT/NaN-bearing
    DataFrame (what pandas.read_sql returns for NULL columns) must not
    surface as the literal string "NaT"/NaN in the JSON response."""
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
    monkeypatch.setattr(journal_module, "current_user_email", lambda req: None)

    df = pd.DataFrame([
        {
            "id": "abc-123",
            "ticker": "SPY",
            "direction": "CALL",
            "entry_ts": pd.Timestamp("2026-07-02T10:15:00"),
            "exit_ts": pd.NaT,
            "entry_price": 620.5,
            "exit_price": float("nan"),
            "return_pct": float("nan"),
            "notes": "",
            "stop_loss": 619.0,
            "tp1": 621.2,
            "tp2": float("nan"),
            "tp3": float("nan"),
            "status": "active",
            "source": "chart",
            "session_id": None,
            "created_at": pd.Timestamp("2026-07-02T10:15:00"),
        }
    ])
    monkeypatch.setattr(journal_module, "_journal_query", lambda *a, **k: df)

    client = TestClient(main.app)
    r = client.get("/api/journal/trades/SPY")
    assert r.status_code == 200
    trade = r.json()["trades"][0]
    assert trade["exit_ts"] is None
    assert trade["exit_price"] is None
    assert trade["return_pct"] is None
    assert trade["take_profits"] == [621.2]


# ── Seed layer (Cloud-SQL only) ──────────────────────────────────────────────


def test_seed_endpoint_converts_fraction_to_percent(monkeypatch):
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)
    df = pd.DataFrame([
        {
            "id": 1,
            "direction": "CALL",
            "entry_time": "2026-07-02 10:00:00",
            "entry_price": 500.0,
            "exit_time": "2026-07-02 10:30:00",
            "exit_price": 501.5,
            "return_pct": 0.003,
            "strat_combo": "212",
            "exit_reason": "tp1",
        }
    ])
    monkeypatch.setattr(journal_module, "_seed_query", lambda *a, **k: df)

    client = TestClient(main.app)
    r = client.get("/api/journal/seed/SPY", params={"date": "2026-07-02"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    trade = body["trades"][0]
    assert trade["return_pct"] == pytest.approx(0.3)
    assert trade["strat_combo"] == "212"


def test_seed_endpoint_503_on_db_failure(monkeypatch):
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", True)

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(journal_module, "_seed_query", boom)
    client = TestClient(main.app)
    r = client.get("/api/journal/seed/SPY", params={"date": "2026-07-02"})
    assert r.status_code == 503


def test_seed_endpoint_unavailable_in_local_mode(monkeypatch):
    monkeypatch.setattr(journal_module, "_HAS_CLOUD_SQL", False)
    client = TestClient(main.app)
    r = client.get("/api/journal/seed/SPY", params={"date": "2026-07-02"})
    assert r.status_code == 200
    assert r.json() == {
        "status": "unavailable",
        "reason": "seed layer requires Cloud SQL",
    }


# ── Regression tests: Fix #2 & #3 ────────────────────────────────────────────


def test_patch_close_on_put_inverts_return_sign(client_local_owner):
    """Regression: PATCH-close on a PUT trade inverts the return sign.

    Entry at 620.5 on PUT, exit at 615.0 (lower price = profit for PUT).
    Expected return_pct ≈ +0.886382 (i.e. -((615.0-620.5)/620.5*100)).
    """
    created = _create(client_local_owner, direction="PUT").json()
    tid = created["id"]
    r = client_local_owner.patch(
        f"/api/journal/trades/{tid}",
        json={"exit_date": "2026-07-02", "exit_time": "10:45", "exit_price": 615.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "win"
    # For PUT: return = -((615.0 - 620.5) / 620.5 * 100)
    expected_pct = -((615.0 - 620.5) / 620.5 * 100)
    assert body["return_pct"] == pytest.approx(expected_pct, rel=1e-6)


def test_post_with_exit_price_only_creates_active_trade(client_local_owner):
    """Regression: POST with exit_price but NO exit_date/exit_time creates
    active trade with null exit_price (not a stray value).

    Verifies fix for: partial-exit payload leaves inconsistent row.
    """
    # Create with exit_price but no exit date/time
    r = _create(client_local_owner, exit_price=625.0)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert body["return_pct"] is None

    # GET the list and verify exit_price is null (not stray 625.0)
    r_list = client_local_owner.get("/api/journal/trades/SPY")
    assert r_list.status_code == 200
    trades = r_list.json()["trades"]
    assert len(trades) == 1
    assert trades[0]["exit_price"] is None
    assert trades[0]["status"] == "active"
