"""API test for the exits in thirds spec (FEAT-STRAT-001, DASHBOARD-21).

The brief's producers write the session's premarket_analysis row: the v3
level_basis (SessionLevels.to_basis) and the structured columns
(gcp.premarket_brief.structured_playbook_columns), which now carry both the
gating targets t1..t3 and the spaced plan targets plan_t1..plan_t3. The
Movement Read card renders GET /api/movement-statement, which rebuilds its
ladder from that stored basis. This drives the real route, the real level
map builder and the real assembler over an in-memory premarket_analysis, and
asserts what the response publishes for the Design 8 call: the trigger and
the gating T1 (253.00) on the ladder, matched to their own slots, and none
of the spaced plan targets (275.00 / 280.00 / 285.00 in plan_t1..plan_t3),
which belong to the brief's exit plan and are scored on their own columns.

Only the continuation model (LightGBM, research-only) and the gamma summary
are stubbed; on origin/main the producer writes no plan columns and the
stored basis carries rule feat-strat-001.v2.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

REPO = Path(__file__).resolve().parent.parent.parent
PLATFORM_DIR = REPO / "platform"
for _p in (REPO, PLATFORM_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api import main as api_main
    from api.routers import dashboard as dashboard_router
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient  # noqa: E402

import lib.movement_statement as ms  # noqa: E402
from gcp.premarket_brief import structured_playbook_columns  # noqa: E402
from lib.strat_levels import LEVEL_RULE_VERSION, SessionLevels  # noqa: E402
from tests.lib.session_levels_helpers import d8_basis  # noqa: E402

SESSION = date(2026, 11, 6)
SLOTS = ("trigger", "t1", "t2", "t3")
SIDE_COLS = ([f"{s}_{k}_price" for s in ("calls", "puts") for k in SLOTS]
             + [f"{s}_{k}_hit_ts" for s in ("calls", "puts") for k in SLOTS]
             + [f"{s}_plan_t{k}_price" for s in ("calls", "puts") for k in (1, 2, 3)]
             + [f"{s}_{c}" for s in ("calls", "puts")
                for c in ("trigger_name", "stop_price", "stop_name")])
COLS = ["ticker", "analysis_date", "run_kind", "price", "level_basis",
        "outcome_resolved_at"] + SIDE_COLS


class _Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.execute(f"CREATE TABLE premarket_analysis ({', '.join(COLS)})")

    def add(self, row: dict):
        row = dict(row)
        if isinstance(row.get("level_basis"), dict):
            row["level_basis"] = json.dumps(row["level_basis"])
        cols = [c for c in COLS if c in row]
        self.conn.execute(
            f"INSERT INTO premarket_analysis ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})", [row[c] for c in cols])

    def query(self, sql, params=None):
        if "premarket_analysis" not in sql:
            return pd.DataFrame()
        sql = sql.replace("::float8", "").replace("::numeric", "")
        p = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in (params or {}).items()}
        return pd.read_sql_query(sql, self.conn, params=p)


def _stored_basis() -> dict:
    b = d8_basis()
    b["ticker"] = "SPY"
    b["session_date"] = SESSION.isoformat()
    return json.loads(json.dumps(SessionLevels.from_basis(b).to_basis()))


@pytest.fixture
def client(monkeypatch):
    stored = _stored_basis()
    lm = SessionLevels.from_basis(stored).to_level_map()
    db = _Db()
    # Five resolved v3 rows on the same ladder: the trigger hit on 4, the
    # gating T1 on 1; a plan price never pairs with a gating hit column.
    for i in range(5):
        row = {"ticker": "SPY", "analysis_date": f"2026-10-{10 + i}", "run_kind": "live",
               "price": stored["prior_close"], "level_basis": stored,
               "outcome_resolved_at": "2026-10-20T21:00:00Z",
               **structured_playbook_columns(lm)}
        if i < 4:
            row["calls_trigger_hit_ts"] = "2026-10-20T15:00:00Z"
        if i == 0:
            row["calls_t1_hit_ts"] = "2026-10-20T15:30:00Z"
        db.add(row)
    # The session's own live row, as the brief writes it.
    db.add({"ticker": "SPY", "analysis_date": SESSION.isoformat(), "run_kind": "live",
            "price": stored["prior_close"], "level_basis": stored,
            **structured_playbook_columns(lm)})

    monkeypatch.setenv("MOVEMENT_STATEMENT_ENABLED", "1")
    monkeypatch.setattr(dashboard_router, "_query_fn", db.query)
    monkeypatch.setattr(dashboard_router, "_movement_analysis_date", lambda: SESSION)
    monkeypatch.setattr(ms, "_strict_query", db.query)
    monkeypatch.setattr(ms, "_build_continuation",
                        lambda *a, **k: ms._unavailable("not under test"))
    import gcp.database as gdb
    import lib.agents.summarizers as summ
    monkeypatch.setattr(gdb, "get_engine", lambda *a, **k: object())
    monkeypatch.setattr(summ, "summarize_gamma_levels", lambda *a, **k: {"available": False})

    return TestClient(api_main.app), stored, lm


def test_the_producer_writes_both_target_sets_on_a_v3_basis(client):
    _, stored, lm = client
    cols = structured_playbook_columns(lm)
    assert stored["rule_version"] == LEVEL_RULE_VERSION
    assert (cols["calls_trigger_price"], cols["calls_t1_price"],
            cols["calls_t2_price"], cols["calls_t3_price"]) == (252.10, 253.00, 275.00, 280.00)
    assert (cols["calls_plan_t1_price"], cols["calls_plan_t2_price"],
            cols["calls_plan_t3_price"]) == (275.00, 280.00, 285.00)


def test_the_movement_read_publishes_the_gating_ladder_not_the_plan(client):
    tc, _, _ = client
    resp = tc.get("/api/movement-statement", params={"ticker": "SPY", "timeframe": "15m"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    levels = body["levels"]
    assert levels["status"] == "OK", levels
    rungs = levels["calls"]
    prices = [r["price"] for r in rungs]
    assert prices[:2] == [252.10, 253.00]
    assert 285.00 not in prices
    trig, t1 = rungs[0]["reach_rate"], rungs[1]["reach_rate"]
    assert (trig["slot"], trig["hits"], trig["sample_n"]) == ("trigger", 4, 5)
    assert (t1["slot"], t1["hits"], t1["sample_n"]) == ("t1", 1, 5)
    assert "plan_" not in json.dumps(body)
