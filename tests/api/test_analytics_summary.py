"""/api/analytics/summary reads production trades only.

Codex on #1022 (#820): 412 simulated trades from a deleted backfill script
sat in `trades` unmarked. Once marked run_kind='backfill' (schema in this
PR), the user-facing win-rate summary must not count them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("fastapi")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_DIR = PROJECT_ROOT / "platform"
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

_original_cwd = os.getcwd()
os.chdir(str(PLATFORM_DIR))
try:
    from api import main
    from api.routers import analytics as analytics_module
finally:
    os.chdir(_original_cwd)

from fastapi.testclient import TestClient  # noqa: E402


def test_summary_restricts_to_live_trades(monkeypatch):
    seen: list = []

    def _capture(sql, params=None):
        seen.append((sql, params))
        return pd.DataFrame(columns=["direction", "return_pct", "exit_time", "entry_time"])

    monkeypatch.setattr(analytics_module, "_HAS_CLOUD_SQL", True)
    monkeypatch.setattr(analytics_module, "query_to_dataframe", _capture)
    r = TestClient(main.app).get("/api/analytics/summary/SPY", params={"days": 30})
    assert r.status_code == 200, r.text
    assert len(seen) == 1
    sql = seen[0][0].lower()
    assert "from trades" in sql and "run_kind = 'live'" in sql, sql
    assert seen[0][1] == {"ticker": "SPY", "days": 30}
