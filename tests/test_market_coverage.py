"""Coverage endpoint: which tickers have daily/intraday data (spec §5.1).
Pure-helper tests only — SQL is exercised by the I/O-shape assertion that
the endpoint issues exactly TWO batched queries (never per-symbol)."""
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
finally:
    os.chdir(_original_cwd)


def test_coverage_from_frames_shapes():
    cov = main._coverage_from_frames(
        ["SPY", "AAPL", "ZZZZ"],
        daily_tickers={"SPY", "AAPL"},
        intraday_tickers={"SPY"},
    )
    assert cov == {
        "SPY": {"intraday": True, "daily": True},
        "AAPL": {"intraday": False, "daily": True},
        "ZZZZ": {"intraday": False, "daily": False},
    }


def test_coverage_uppercases_and_dedupes():
    cov = main._coverage_from_frames(["spy", "SPY"], {"SPY"}, {"SPY"})
    assert list(cov) == ["SPY"]


def test_coverage_endpoint_batches_queries(monkeypatch):
    calls = []
    import pandas as pd

    def fake_query(sql, params=None):
        calls.append(sql)
        return pd.DataFrame({"ticker": ["SPY"]})

    # Patch at the site the handler calls through — main._coverage_query.
    monkeypatch.setattr(main, "_coverage_query", fake_query, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get("/api/market/coverage", params={"symbols": "SPY,AAPL,IWM,QQQ,XLK"})
    assert r.status_code == 200
    assert len(calls) == 2  # one daily, one intraday — regardless of symbol count
    body = r.json()
    assert body["coverage"]["SPY"] == {"intraday": True, "daily": True}
    assert body["coverage"]["AAPL"] == {"intraday": False, "daily": False}


def test_coverage_endpoint_503s_loud_on_db_failure(monkeypatch):
    """Regression: DB errors surface as 503, never fabricate all-false coverage."""
    def boom(sql, params=None):
        raise RuntimeError("db down")
    monkeypatch.setattr(main, "_coverage_query", boom, raising=True)
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    r = client.get("/api/market/coverage", params={"symbols": "SPY"})
    assert r.status_code == 503
    assert "coverage" not in r.json()  # never fabricate all-false coverage
