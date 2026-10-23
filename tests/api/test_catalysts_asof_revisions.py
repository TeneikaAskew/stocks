import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform"))
from api.routers import catalysts


@pytest.fixture(autouse=True)
def no_legacy_database_access(monkeypatch):
    from gcp import database
    monkeypatch.setattr(database, "query_to_dataframe", lambda *a, **kw: pd.DataFrame())


def client():
    app = FastAPI()
    app.include_router(catalysts.router)
    return TestClient(app)


def test_snapshot_before_eps_correction_returns_known_revision(monkeypatch):
    from lib import earnings_history
    seen = []
    def read(ticker, cutoff, **kw):
        seen.append(cutoff)
        return {"status": "ok", "records": [{"reported_eps": 1.0}], "cutoff": cutoff.isoformat()}
    monkeypatch.setattr(earnings_history, "read_earnings_asof", read)
    response = client().get("/api/catalysts/asof/AAPL?as_of=2026-10-08")
    assert response.status_code == 200
    assert response.json()["earnings_history_recent"][0]["reported_eps"] == 1
    assert seen[0].isoformat() == "2026-10-09T03:59:59.999999+00:00"


def test_historical_snapshot_suppresses_unversioned_sections(monkeypatch):
    from gcp import database
    from lib import earnings_history
    monkeypatch.setattr(earnings_history, "read_earnings_asof", lambda *a, **kw: {"status": "unavailable", "records": [], "reason": "pre_observation_coverage_gap"})
    def forbidden(*a, **kw):
        raise AssertionError("mutable historical source queried")
    monkeypatch.setattr(database, "query_to_dataframe_strict", forbidden)
    body = client().get("/api/catalysts/asof/AAPL?as_of=2026-10-08").json()
    for section in ["news", "sec_filings", "insider_transactions", "next_earnings", "price_context_daily"]:
        assert body["availability"][section]["status"] == "unavailable"
        assert body["availability"][section]["reason"] == "historical_provenance_unavailable"
        assert not body[section]


def test_every_section_query_failure_is_explicit(monkeypatch):
    from gcp import database
    from lib import earnings_history
    monkeypatch.setattr(earnings_history, "read_earnings_asof", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("db")))
    monkeypatch.setattr(database, "query_to_dataframe_strict", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("db")))
    body = client().get("/api/catalysts/asof/AAPL").json()
    assert all(facts["status"] == "error" for facts in body["availability"].values())
