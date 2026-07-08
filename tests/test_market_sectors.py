"""Sector-rotation endpoint: SPDR daily closes -> per-sector 1d/5d % change
(Phase 1 §Task 5). Pure-helper tests cover the math; endpoint tests cover
the I/O shape (one batched query, never per-symbol) and the loud-503 /
no-fabricated-data contract (CLAUDE.md Rule 3.7)."""
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
finally:
    os.chdir(_original_cwd)


def _df():
    rows = []
    for i, close in enumerate([100, 101, 102, 103, 104, 105]):  # 6 sessions, oldest first
        rows.append({"ticker": "XLK", "date": f"2026-07-0{i+1}", "close": close})
    rows.append({"ticker": "XLF", "date": "2026-07-06", "close": 50})  # only 1 row -> 1d/5d unavailable
    return pd.DataFrame(rows)


def test_sector_rotation_math():
    as_of, sectors = main._sector_rotation_from_df(_df())
    assert as_of == "2026-07-06"
    xlk = next(s for s in sectors if s["symbol"] == "XLK")
    assert xlk["status"] == "ok"
    assert xlk["chg_1d_pct"] == pytest.approx((105 - 104) / 104 * 100, abs=1e-6)
    assert xlk["chg_5d_pct"] == pytest.approx((105 - 100) / 100 * 100, abs=1e-6)
    xlf = next(s for s in sectors if s["symbol"] == "XLF")
    assert xlf["status"] == "unavailable"  # one row: no prior close -> no fabricated 0
    missing = next(s for s in sectors if s["symbol"] == "XLE")
    assert missing["status"] == "unavailable"


def test_sector_rotation_all_missing():
    as_of, sectors = main._sector_rotation_from_df(pd.DataFrame(columns=["ticker", "date", "close"]))
    assert as_of is None
    assert all(s["status"] == "unavailable" for s in sectors)


def test_sector_rotation_partial_window_no_5d():
    """3 rows (< 6): chg_1d_pct present, chg_5d_pct omitted (None), status stays ok."""
    rows = [
        {"ticker": "XLE", "date": "2026-07-01", "close": 80},
        {"ticker": "XLE", "date": "2026-07-02", "close": 81},
        {"ticker": "XLE", "date": "2026-07-03", "close": 79},
    ]
    as_of, sectors = main._sector_rotation_from_df(pd.DataFrame(rows))
    xle = next(s for s in sectors if s["symbol"] == "XLE")
    assert xle["status"] == "ok"
    assert xle["chg_1d_pct"] == pytest.approx((79 - 81) / 81 * 100, abs=1e-6)
    assert xle["chg_5d_pct"] is None


def _clear_cache():
    main._SECTORS_CACHE.clear()


def test_sectors_endpoint_single_batched_query(monkeypatch):
    _clear_cache()
    calls = []

    def fake_query(sql, params=None):
        calls.append((sql, params))
        return _df()

    monkeypatch.setattr(main, "_sectors_query", fake_query, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get("/api/market/sectors")
    assert r.status_code == 200
    assert len(calls) == 1  # one batched query regardless of symbol count
    sql, params = calls[0]
    assert set(params["syms"]) == set(main.SECTOR_NAMES.keys())

    body = r.json()
    assert body["as_of"] == "2026-07-06"
    assert body["status"] == "ok"
    xlk = next(s for s in body["sectors"] if s["symbol"] == "XLK")
    assert xlk["name"] == "Technology"
    assert xlk["status"] == "ok"


def test_sectors_endpoint_uses_cache(monkeypatch):
    _clear_cache()
    calls = []

    def fake_query(sql, params=None):
        calls.append(sql)
        return _df()

    monkeypatch.setattr(main, "_sectors_query", fake_query, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r1 = client.get("/api/market/sectors")
    r2 = client.get("/api/market/sectors")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(calls) == 1  # second request served from the 10-min TTL cache


def test_sectors_endpoint_503s_loud_on_db_failure(monkeypatch):
    """Regression: DB errors surface as 503, never fabricate all-unavailable data."""
    _clear_cache()

    def boom(sql, params=None):
        raise RuntimeError("db down")

    monkeypatch.setattr(main, "_sectors_query", boom, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get("/api/market/sectors")
    assert r.status_code == 503
    assert "sectors" not in r.json()


def test_sectors_endpoint_all_missing_top_status(monkeypatch):
    _clear_cache()

    def fake_query(sql, params=None):
        return pd.DataFrame(columns=["ticker", "date", "close"])

    monkeypatch.setattr(main, "_sectors_query", fake_query, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get("/api/market/sectors")
    assert r.status_code == 200
    body = r.json()
    assert body["as_of"] is None
    assert body["status"] == "unavailable"
    assert body["reason"] == "sector ETFs not ingested yet — run the SPDR backfill"
