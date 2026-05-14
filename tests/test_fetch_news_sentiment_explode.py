"""Regression guard for `_article_to_rows` ticker filtering.

AV's `ticker_sentiment` array includes non-equity identifiers like
`CRYPTO:BTC` and `FOREX:USD`. Those rows used to flow straight into
`news_sentiment.ticker`, which is `VARCHAR(10)`, and broke the job
with `22001 value too long for type character varying(10)` once an
identifier like `CRYPTO:DOGE` (11 chars) showed up.

This test pins the parse-time filter so the bug can't return.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gcp.fetchers.fetch_news_sentiment import _article_to_rows


def _make_article(ticker_entries):
    return {
        "title": "t",
        "url": "https://example.com/a",
        "summary": "s",
        "time_published": "20260514T120000",
        "overall_sentiment_score": 0.0,
        "overall_sentiment_label": "Neutral",
        "topics": [{"topic": "earnings", "relevance_score": "1.0"}],
        "source": "src",
        "ticker_sentiment": ticker_entries,
    }


def _entry(tk):
    return {"ticker": tk, "ticker_sentiment_score": "0.1", "relevance_score": "0.5"}


def test_drops_crypto_and_forex_identifiers():
    article = _make_article([
        _entry("SPY"),
        _entry("CRYPTO:BTC"),
        _entry("CRYPTO:DOGE"),  # 11 chars — would overflow VARCHAR(10)
        _entry("FOREX:USD"),
        _entry("AAPL"),
    ])
    rows = _article_to_rows(article)
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"SPY", "AAPL"}


def test_drops_overlong_plain_tickers():
    article = _make_article([
        _entry("VALIDTKR"),
        _entry("WAYTOOLONGTICKER"),
    ])
    rows = _article_to_rows(article)
    tickers = {r["ticker"] for r in rows}
    assert tickers == {"VALIDTKR"}
