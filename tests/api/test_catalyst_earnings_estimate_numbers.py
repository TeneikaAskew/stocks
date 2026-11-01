"""A missing/nonfinite optional estimate must not become a quoted number.

The real router, adapter, date filters, cache reader and response schema run.
Only provider acquisition and SQL I/O are replaced; no production app startup.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests._catalyst_number_cases import CASES, input_value

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "platform"))
from api.routers import catalysts
from gcp import database

DAY = "2026-10-27"


def earnings_frame(values, *, dtype=object):
    return pd.DataFrame({
        "ticker": ["IWM", "QQQ"],
        "date": [DAY, DAY],
        "company_name": ["ExampleCo", "SiblingCo"],
        "earnings_time": ["BMO", "AMC"],
        "eps_estimate": pd.Series(values, dtype=dtype),
    })


@pytest.fixture
def event_client(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("External provider/database I/O forbidden")

    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(database, "get_engine", forbidden)
    monkeypatch.setattr(catalysts, "_fetch_live_events", forbidden)
    cache = tmp_path / "catalysts.json"
    cache.write_text(json.dumps({"events": [{
        "date": DAY, "ticker": "SPY", "catalyst_type": "ECONOMIC",
        "title": "Keep cached event", "source": "fixture cache",
    }]}), encoding="utf-8")
    monkeypatch.setattr(catalysts, "CATALYSTS_FILE", cache)
    state = {"earnings": earnings_frame([None, -1.25]), "queries": []}

    def query(sql, params):
        state["queries"].append((sql, dict(params)))
        if "FROM earnings_calendar " in sql:
            return state["earnings"].copy()
        if "FROM news_sentiment " in sql:
            return pd.DataFrame([{
                "ticker": "SPY", "date": DAY, "title": "Keep news sibling",
                "overall_sentiment_label": "Bullish", "sentiment_score": 0.5,
                "relevance_score": 0.95, "topics": ["earnings"],
                "url": "https://example.invalid/news",
            }])
        if "FROM insider_transactions " in sql and "insider" in state:
            return state["insider"].copy()
        if "FROM sec_filings " in sql and "sec" in state:
            return state["sec"].copy()
        if any(t in sql for t in (
            "FROM economic_events ", "FROM insider_transactions ",
            "FROM sec_filings ",
        )):
            return pd.DataFrame()
        raise AssertionError("Unexpected SQL boundary")

    monkeypatch.setattr(database, "query_to_dataframe", query)
    app = FastAPI()
    app.include_router(catalysts.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, state


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
def test_nullable_estimate_contract_at_actual_response(event_client, case):
    client, state = event_client
    state["earnings"] = earnings_frame([input_value(case), -1.25])
    response = client.get("/api/catalysts/events", params={
        "date_from": DAY, "date_to": "2026-10-28",
    })
    assert response.status_code == 200
    result = response.json()
    events = result["events_by_date"][DAY]
    iwms = [e for e in events if e.get("ticker") == "IWM"]
    assert iwms == [{
        "date": DAY, "ticker": "IWM", "catalyst_type": "EARNINGS",
        "title": "ExampleCo earnings (BMO" + case["suffix"] + ")",
        "impact": "High", "source": "AV earnings_calendar",
    }]
    assert result["total"] == 4
    assert any(e.get("title") == "SiblingCo earnings (AMC, est -1.25)" for e in events)
    assert any(e.get("title") == "Keep news sibling" and e["source"] == "AV news" for e in events)
    assert any(e.get("title") == "Keep cached event" for e in events)
    assert len(state["queries"]) == 5
    earning_queries = [params for sql, params in state["queries"] if "FROM earnings_calendar " in sql]
    assert earning_queries == [{"d_from": DAY, "d_to": "2026-10-28"}]


def test_numeric_dataframe_null_is_not_a_published_estimate(event_client):
    client, state = event_client
    state["earnings"] = earnings_frame([None, 1.25], dtype="float64")
    assert pd.isna(state["earnings"].loc[0, "eps_estimate"])
    response = client.get("/api/catalysts/events", params={
        "date_from": DAY, "date_to": "2026-10-28",
    })
    assert response.status_code == 200
    events = response.json()["events_by_date"][DAY]
    assert next(e["title"] for e in events if e.get("ticker") == "IWM") == "ExampleCo earnings (BMO)"
    assert next(e["title"] for e in events if e.get("ticker") == "QQQ") == "SiblingCo earnings (AMC, est 1.25)"


def test_nullable_estimate_preserves_duplicate_and_non_earnings_events(event_client):
    client, state = event_client
    # Preserve the existing one-per-(ticker, date) earnings dedup rule,
    # without losing unrelated source events when an estimate is missing.
    state["earnings"] = pd.concat(
        [earnings_frame([None, -1.25]), earnings_frame([None, -1.25]).iloc[:1]],
        ignore_index=True,
    )
    state["insider"] = pd.DataFrame([{
        "ticker": "NVDA", "date": DAY, "transaction_type": "A",
        "insiders": 3, "txns": 4, "total_value": 2_000_000.0,
    }])
    state["sec"] = pd.DataFrame([{
        "ticker": "APOG", "date": DAY, "form": "8-K", "items": ["1.01"],
        "primary_doc": "fixture.htm", "accession_number": "fixture-accession",
    }])
    response = client.get("/api/catalysts/events", params={
        "date_from": DAY, "date_to": "2026-10-28",
    })
    assert response.status_code == 200
    result = response.json()
    events = result["events_by_date"][DAY]
    assert result["total"] == 6
    assert [e for e in events if e.get("ticker") == "IWM"] == [{
        "date": DAY, "ticker": "IWM", "catalyst_type": "EARNINGS",
        "title": "ExampleCo earnings (BMO)", "impact": "High",
        "source": "AV earnings_calendar",
    }]
    assert next(e for e in events if e.get("ticker") == "NVDA") == {
        "date": DAY, "ticker": "NVDA", "catalyst_type": "INSIDER_BUY",
        "title": "3 insiders buying ~$2.0M", "impact": "Medium",
        "source": "AV insider", "insiders": 3, "total_value": 2_000_000.0,
    }
    assert next(e for e in events if e.get("ticker") == "APOG") == {
        "date": DAY, "ticker": "APOG", "catalyst_type": "SEC_8K",
        "title": "8-K — Material Definitive Agreement", "impact": "High",
        "source": "SEC EDGAR", "items": ["1.01"],
        "primary_doc": "fixture.htm", "accession_number": "fixture-accession",
    }
    assert next(e["title"] for e in events if e.get("ticker") == "QQQ") == "SiblingCo earnings (AMC, est -1.25)"
    assert any(e.get("title") == "Keep news sibling" for e in events)
    assert any(e.get("title") == "Keep cached event" for e in events)
    assert len(state["queries"]) == 5
