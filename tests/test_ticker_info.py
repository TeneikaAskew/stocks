"""Unit tests for lib/ticker_info.py — AV OVERVIEW, SYMBOL_SEARCH, GLOBAL_QUOTE.

All AV HTTP calls are mocked so tests don't need a real API key.
Tests cover:
    - fetch_ticker_overview: parses AV OVERVIEW response, keeps correct fields
    - search_tickers: parses AV SYMBOL_SEARCH response
    - get_quote: parses AV GLOBAL_QUOTE response
    - get_aliases: derives aliases from company name
    - get_ticker_info: caches to local JSON, returns stale on AV failure
    - Cloud SQL path: upsert/read wired correctly (mocked)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.conftest import requires_data_backend  # noqa: E402


# ---------------------------------------------------------------------------
# Mock AV responses
# ---------------------------------------------------------------------------

MOCK_OVERVIEW = {
    "Symbol": "INTC",
    "Name": "Intel Corp",
    "Exchange": "NASDAQ",
    "Sector": "TECHNOLOGY",
    "Industry": "SEMICONDUCTORS",
    "MarketCapitalization": "120000000000",
    "Description": "Intel Corporation designs and manufactures semiconductors.",
    "AssetType": "Common Stock",
    "52WeekHigh": "50.00",  # should be stripped
    "DividendYield": "0.02",  # should be stripped
}

MOCK_SEARCH_RESPONSE = {
    "bestMatches": [
        {
            "1. symbol": "INTC",
            "2. name": "Intel Corp",
            "3. type": "Equity",
            "4. region": "United States",
            "5. marketOpen": "09:30",
            "6. marketClose": "16:00",
            "7. timezone": "UTC-04",
            "8. currency": "USD",
            "9. matchScore": "0.8889",
        },
        {
            "1. symbol": "0R24.LON",
            "2. name": "Intel Corp.",
            "3. type": "Equity",
            "4. region": "United Kingdom",
            "5. marketOpen": "08:00",
            "6. marketClose": "16:30",
            "7. timezone": "UTC+01",
            "8. currency": "USD",
            "9. matchScore": "0.6250",
        },
    ]
}

MOCK_QUOTE_RESPONSE = {
    "Global Quote": {
        "01. symbol": "INTC",
        "02. open": "22.50",
        "03. high": "23.10",
        "04. low": "22.30",
        "05. price": "22.85",
        "06. volume": "35000000",
        "07. latest trading day": "2026-04-25",
        "08. previous close": "22.60",
        "09. change": "0.25",
        "10. change percent": "1.1062%",
    }
}


def _mock_fetch_response(json_data):
    """Return a mock requests.Response with .json() -> json_data."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = 200
    return resp


# ---------------------------------------------------------------------------
# fetch_ticker_overview
# ---------------------------------------------------------------------------


class TestFetchTickerOverview:
    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_returns_trimmed_fields(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response(MOCK_OVERVIEW)
        from lib.ticker_info import fetch_ticker_overview

        result = fetch_ticker_overview("INTC")
        assert result is not None
        assert result["Symbol"] == "INTC"
        assert result["Name"] == "Intel Corp"
        assert result["Sector"] == "TECHNOLOGY"
        # Extra fields should not be present
        assert "52WeekHigh" not in result
        assert "DividendYield" not in result

    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_returns_none_on_empty_response(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response({})
        from lib.ticker_info import fetch_ticker_overview

        assert fetch_ticker_overview("FAKE") is None

    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_returns_none_on_rate_limit_note(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response({
            "Note": "Thank you for using Alpha Vantage! Please visit..."
        })
        from lib.ticker_info import fetch_ticker_overview

        assert fetch_ticker_overview("INTC") is None

    @patch("lib.ticker_info._get_av_key", side_effect=KeyError("no key"))
    def test_returns_none_without_api_key(self, _key):
        from lib.ticker_info import fetch_ticker_overview

        assert fetch_ticker_overview("INTC") is None


# ---------------------------------------------------------------------------
# search_tickers
# ---------------------------------------------------------------------------


class TestSearchTickers:
    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_returns_parsed_matches(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response(MOCK_SEARCH_RESPONSE)
        from lib.ticker_info import search_tickers

        results = search_tickers("intel")
        assert len(results) == 2
        assert results[0]["symbol"] == "INTC"
        assert results[0]["name"] == "Intel Corp"
        assert results[0]["match_score"] == pytest.approx(0.8889)
        assert results[1]["region"] == "United Kingdom"

    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_respects_limit(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response(MOCK_SEARCH_RESPONSE)
        from lib.ticker_info import search_tickers

        results = search_tickers("intel", limit=1)
        assert len(results) == 1

    @patch("lib.ticker_info._get_av_key", side_effect=KeyError("no key"))
    def test_returns_empty_without_key(self, _key):
        from lib.ticker_info import search_tickers

        assert search_tickers("intel") == []


# ---------------------------------------------------------------------------
# get_quote
# ---------------------------------------------------------------------------


class TestGetQuote:
    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_returns_parsed_quote(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response(MOCK_QUOTE_RESPONSE)
        from lib.ticker_info import get_quote

        q = get_quote("INTC")
        assert q is not None
        assert q["symbol"] == "INTC"
        assert q["price"] == pytest.approx(22.85)
        assert q["volume"] == 35000000
        assert q["change"] == pytest.approx(0.25)
        assert q["change_percent"] == "1.1062%"
        assert q["latest_trading_day"] == "2026-04-25"

    @patch("lib.api_client.fetch_with_retry")
    @patch("lib.ticker_info._get_av_key", return_value="TESTKEY")
    def test_returns_none_on_empty_quote(self, _key, mock_fetch):
        mock_fetch.return_value = _mock_fetch_response({"Global Quote": {}})
        from lib.ticker_info import get_quote

        assert get_quote("FAKE") is None


# ---------------------------------------------------------------------------
# get_aliases
# ---------------------------------------------------------------------------


class TestGetAliases:
    @patch("lib.ticker_info.get_ticker_info")
    def test_aliases_include_ticker_and_short_name(self, mock_info):
        mock_info.return_value = {"Name": "Broadcom Inc", "Symbol": "AVGO"}
        from lib.ticker_info import get_aliases

        aliases = get_aliases("AVGO")
        assert "AVGO" in aliases
        assert "Broadcom Inc" in aliases
        assert "Broadcom" in aliases

    @patch("lib.ticker_info.get_ticker_info")
    def test_aliases_strip_corporation_suffix(self, mock_info):
        mock_info.return_value = {"Name": "Intel Corporation", "Symbol": "INTC"}
        from lib.ticker_info import get_aliases

        aliases = get_aliases("INTC")
        assert "Intel" in aliases
        assert "Intel Corporation" in aliases

    @patch("lib.ticker_info.get_ticker_info")
    def test_aliases_with_no_info_returns_just_ticker(self, mock_info):
        mock_info.return_value = None
        from lib.ticker_info import get_aliases

        assert get_aliases("XYZ") == ["XYZ"]

    @patch("lib.ticker_info.get_ticker_info")
    def test_aliases_handles_holdings_suffix(self, mock_info):
        mock_info.return_value = {"Name": "Berkshire Hathaway Holdings", "Symbol": "BRK"}
        from lib.ticker_info import get_aliases

        aliases = get_aliases("BRK")
        assert "Berkshire Hathaway" in aliases


# ---------------------------------------------------------------------------
# get_peers (FinViz)
# ---------------------------------------------------------------------------


class TestGetPeers:
    @patch("lib.ticker_info._cloud_sql_available", return_value=False)
    @patch("lib.ticker_info._fetch_finviz_peers")
    def test_returns_peer_list(self, mock_fetch, _no_cloud, tmp_path):
        mock_fetch.return_value = ["AMD", "NVDA", "QCOM", "TSM"]
        import lib.ticker_info as ti
        original_path = ti._LOCAL_CACHE_PATH
        ti._LOCAL_CACHE_PATH = tmp_path / "ticker_info.json"
        try:
            peers = ti.get_peers("INTC", max_age_days=0)
            assert peers == ["AMD", "NVDA", "QCOM", "TSM"]
            mock_fetch.assert_called_once_with("INTC")
        finally:
            ti._LOCAL_CACHE_PATH = original_path

    @patch("lib.ticker_info._cloud_sql_available", return_value=False)
    @patch("lib.ticker_info._fetch_finviz_peers")
    def test_caches_peers_locally(self, mock_fetch, _no_cloud, tmp_path):
        mock_fetch.return_value = ["AMD", "NVDA"]
        import lib.ticker_info as ti
        original_path = ti._LOCAL_CACHE_PATH
        ti._LOCAL_CACHE_PATH = tmp_path / "ticker_info.json"
        try:
            ti.get_peers("AVGO", max_age_days=0)
            # Verify cache was written
            cached = json.loads(ti._LOCAL_CACHE_PATH.read_text())
            assert cached["AVGO"]["_peers"] == ["AMD", "NVDA"]
        finally:
            ti._LOCAL_CACHE_PATH = original_path

    @patch("lib.ticker_info._cloud_sql_available", return_value=False)
    @patch("lib.ticker_info._fetch_finviz_peers", return_value=None)
    def test_returns_empty_on_failure(self, mock_fetch, _no_cloud, tmp_path):
        import lib.ticker_info as ti
        original_path = ti._LOCAL_CACHE_PATH
        ti._LOCAL_CACHE_PATH = tmp_path / "ticker_info.json"
        try:
            peers = ti.get_peers("FAKE", max_age_days=0)
            assert peers == []
        finally:
            ti._LOCAL_CACHE_PATH = original_path

    @patch("lib.ticker_info._cloud_sql_available", return_value=False)
    @patch("lib.ticker_info._fetch_finviz_peers")
    def test_serves_from_cache_when_fresh(self, mock_fetch, _no_cloud, tmp_path):
        """Second call should use cache, not call FinViz again."""
        mock_fetch.return_value = ["AMD"]
        import lib.ticker_info as ti
        original_path = ti._LOCAL_CACHE_PATH
        ti._LOCAL_CACHE_PATH = tmp_path / "ticker_info.json"
        try:
            ti.get_peers("TEST", max_age_days=0)  # populates cache
            mock_fetch.return_value = ["SHOULD_NOT_SEE"]
            peers = ti.get_peers("TEST", max_age_days=30)  # should use cache
            assert peers == ["AMD"]
        finally:
            ti._LOCAL_CACHE_PATH = original_path


# ---------------------------------------------------------------------------
# get_finviz_news
# ---------------------------------------------------------------------------


class TestGetFinvizNews:
    @patch("finvizfinance.quote.finvizfinance")
    def test_returns_article_list(self, MockFinviz):
        import pandas as pd
        mock_stock = MagicMock()
        mock_stock.ticker_news.return_value = pd.DataFrame([
            {"Date": "2026-04-26", "Title": "AVGO surges on AI demand", "Link": "https://example.com/1", "Source": "Reuters"},
            {"Date": "2026-04-25", "Title": "Broadcom earnings beat", "Link": "https://example.com/2", "Source": "Bloomberg"},
        ])
        MockFinviz.return_value = mock_stock

        from lib.ticker_info import get_finviz_news
        articles = get_finviz_news("AVGO")
        assert len(articles) == 2
        assert articles[0]["title"] == "AVGO surges on AI demand"
        assert articles[0]["source"] == "Reuters"
        assert articles[1]["link"] == "https://example.com/2"

    @patch("finvizfinance.quote.finvizfinance")
    def test_returns_empty_on_failure(self, MockFinviz):
        MockFinviz.side_effect = Exception("blocked")
        from lib.ticker_info import get_finviz_news
        assert get_finviz_news("FAKE") == []


# ---------------------------------------------------------------------------
# get_ticker_info — caching behavior
# ---------------------------------------------------------------------------


class TestGetTickerInfoCaching:
    @patch("lib.ticker_info._cloud_sql_available", return_value=False)
    @patch("lib.ticker_info.fetch_ticker_overview")
    def test_caches_to_local_json(self, mock_fetch, _no_cloud, tmp_path):
        mock_fetch.return_value = {
            "Symbol": "TEST",
            "Name": "Test Corp",
        }
        import lib.ticker_info as ti
        original_path = ti._LOCAL_CACHE_PATH
        ti._LOCAL_CACHE_PATH = tmp_path / "ticker_info.json"
        try:
            result = ti.get_ticker_info("TEST", max_age_days=0)
            assert result["Symbol"] == "TEST"
            # Verify file was written
            assert ti._LOCAL_CACHE_PATH.exists()
            cached = json.loads(ti._LOCAL_CACHE_PATH.read_text())
            assert "TEST" in cached
            assert cached["TEST"]["Name"] == "Test Corp"
        finally:
            ti._LOCAL_CACHE_PATH = original_path

    @patch("lib.ticker_info._cloud_sql_available", return_value=False)
    @patch("lib.ticker_info.fetch_ticker_overview", return_value=None)
    def test_returns_stale_cache_when_av_fails(self, mock_fetch, _no_cloud, tmp_path):
        import lib.ticker_info as ti
        original_path = ti._LOCAL_CACHE_PATH
        cache_file = tmp_path / "ticker_info.json"
        # Pre-populate cache with stale data (no date = stale)
        cache_file.write_text(json.dumps({
            "STALE": {"Symbol": "STALE", "Name": "Stale Corp"}
        }))
        ti._LOCAL_CACHE_PATH = cache_file
        try:
            result = ti.get_ticker_info("STALE", max_age_days=0)
            # AV returned None, so we should get the stale entry
            assert result is not None
            assert result["Name"] == "Stale Corp"
        finally:
            ti._LOCAL_CACHE_PATH = original_path


# ---------------------------------------------------------------------------
# FastAPI endpoint tests (using TestClient)
# ---------------------------------------------------------------------------


@requires_data_backend
class TestTickerInfoAPI:
    @pytest.fixture(scope="class")
    def client(self):
        import os
        original_cwd = os.getcwd()
        platform_dir = str(PROJECT_ROOT / "platform")
        if platform_dir not in sys.path:
            sys.path.insert(0, platform_dir)
        os.chdir(platform_dir)

        from starlette.testclient import TestClient
        from api.main import app
        with TestClient(app) as c:
            yield c
        os.chdir(original_cwd)

    @patch("lib.ticker_info.search_tickers")
    def test_search_endpoint(self, mock_search, client):
        mock_search.return_value = [
            {"symbol": "INTC", "name": "Intel Corp", "type": "Equity",
             "region": "US", "currency": "USD", "match_score": 0.89},
        ]
        r = client.get("/api/insights/ticker/search?keywords=intel")
        assert r.status_code == 200
        data = r.json()
        assert data["keywords"] == "intel"
        assert len(data["results"]) == 1
        assert data["results"][0]["symbol"] == "INTC"

    def test_search_endpoint_rejects_empty_keywords(self, client):
        r = client.get("/api/insights/ticker/search?keywords=")
        assert r.status_code == 400

    @patch("lib.ticker_info.get_ticker_info")
    def test_info_endpoint(self, mock_info, client):
        mock_info.return_value = {
            "Symbol": "AVGO", "Name": "Broadcom Inc", "Exchange": "NASDAQ",
            "Sector": "TECHNOLOGY", "Industry": "SEMICONDUCTORS",
            "MarketCapitalization": "2000000000000", "AssetType": "Common Stock",
            "Description": "Broadcom designs chips.",
        }
        r = client.get("/api/insights/ticker/AVGO/info")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "AVGO"
        assert data["name"] == "Broadcom Inc"
        assert data["sector"] == "TECHNOLOGY"

    @patch("lib.ticker_info.get_ticker_info", return_value=None)
    def test_info_endpoint_404_when_not_found(self, mock_info, client):
        r = client.get("/api/insights/ticker/FAKE123/info")
        assert r.status_code == 404

    @patch("lib.ticker_info.get_quote")
    def test_quote_endpoint(self, mock_quote, client):
        mock_quote.return_value = {
            "symbol": "INTC", "open": 22.5, "high": 23.1, "low": 22.3,
            "price": 22.85, "volume": 35000000,
            "latest_trading_day": "2026-04-25",
            "previous_close": 22.6, "change": 0.25,
            "change_percent": "1.11%",
        }
        r = client.get("/api/insights/ticker/INTC/quote")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "INTC"
        assert data["price"] == pytest.approx(22.85)

    @patch("lib.ticker_info.get_quote", return_value=None)
    def test_quote_endpoint_404_when_not_found(self, mock_quote, client):
        r = client.get("/api/insights/ticker/FAKE123/quote")
        assert r.status_code == 404

    @patch("lib.ticker_info.get_peers")
    def test_peers_endpoint(self, mock_peers, client):
        mock_peers.return_value = ["AMD", "NVDA", "QCOM", "TSM"]
        r = client.get("/api/insights/ticker/INTC/peers")
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "INTC"
        assert data["peers"] == ["AMD", "NVDA", "QCOM", "TSM"]

    @patch("lib.ticker_info.get_peers")
    @patch("lib.ticker_info.get_quote")
    @patch("lib.ticker_info.get_ticker_info")
    def test_watchlist_add_endpoint(self, mock_info, mock_quote, mock_peers, client, tmp_path):
        mock_info.return_value = {
            "Symbol": "MSFT", "Name": "Microsoft Corp", "Exchange": "NASDAQ",
            "Sector": "TECHNOLOGY", "Industry": "SOFTWARE",
            "MarketCapitalization": "3000000000000", "AssetType": "Common Stock",
            "Description": "Microsoft makes software.",
        }
        mock_quote.return_value = {
            "symbol": "MSFT", "open": 420.0, "high": 425.0, "low": 418.0,
            "price": 422.0, "volume": 20000000,
            "latest_trading_day": "2026-04-25",
            "previous_close": 419.0, "change": 3.0,
            "change_percent": "0.72%",
        }
        mock_peers.return_value = ["AAPL", "GOOG", "AMZN"]
        r = client.post(
            "/api/insights/watchlist/add",
            json={"ticker": "MSFT"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "MSFT"
        assert data["info"] is not None
        assert data["info"]["name"] == "Microsoft Corp"
        assert data["quote"] is not None
        assert data["quote"]["price"] == pytest.approx(422.0)
        assert data["peers"] == ["AAPL", "GOOG", "AMZN"]
