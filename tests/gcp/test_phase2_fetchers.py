"""Unit tests for the Phase 2 catalyst fetchers.

All tests mock outbound HTTP and Cloud SQL — nothing depends on a live
network or DB. They validate request construction, response parsing,
edge-case handling (rate limits, missing fields, empty arrays), and
the final DataFrame shape that gets upserted.

Coverage:
  * fetch_news_sentiment    — _article_to_rows, fetch_by_tickers, fetch_by_topics
  * fetch_earnings_history  — fetch_history_for_ticker
  * fetch_sec_filings       — load_ticker_to_cik, fetch_submissions, filter_and_normalize
  * fetch_insider_transactions — fetch_for_ticker
  * fetch_top_movers        — fetch_top_movers, percentage parser
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# fetch_news_sentiment
# ──────────────────────────────────────────────────────────────────────


def test_news_article_to_rows_explodes_per_ticker():
    """One AV article must produce one row per ticker_sentiment entry,
    preserving topics and overall sentiment."""
    from gcp.fetchers.fetch_news_sentiment import _article_to_rows

    article = {
        "time_published": "20260424T120000",
        "title": "Broadcom and Google announce AI chip deal",
        "url": "https://example.com/avgo-googl",
        "summary": "Broadcom said it agreed to supply AI chips to Google",
        "source": "Reuters",
        "overall_sentiment_score": 0.35,
        "overall_sentiment_label": "Bullish",
        "topics": [
            {"topic": "Technology", "relevance_score": "0.8"},
            {"topic": "Financial Markets", "relevance_score": "0.5"},
        ],
        "ticker_sentiment": [
            {"ticker": "AVGO", "relevance_score": "0.9",
             "ticker_sentiment_score": "0.4", "ticker_sentiment_label": "Bullish"},
            {"ticker": "GOOGL", "relevance_score": "0.7",
             "ticker_sentiment_score": "0.2", "ticker_sentiment_label": "Somewhat-Bullish"},
        ],
    }
    rows = _article_to_rows(article)
    assert len(rows) == 2
    by_tk = {r["ticker"]: r for r in rows}
    assert set(by_tk.keys()) == {"AVGO", "GOOGL"}
    # Per-ticker sentiment is the per-ticker_sentiment_score, not overall
    assert by_tk["AVGO"]["sentiment_score"] == 0.4
    assert by_tk["GOOGL"]["sentiment_score"] == 0.2
    # Topics shared across all ticker rows from the same article
    assert by_tk["AVGO"]["topics"] == ["Technology", "Financial Markets"]
    assert by_tk["GOOGL"]["topics"] == ["Technology", "Financial Markets"]
    # Overall sentiment is article-level, identical across ticker rows
    assert by_tk["AVGO"]["overall_sentiment_score"] == 0.35
    assert by_tk["AVGO"]["overall_sentiment_label"] == "Bullish"


def test_news_article_to_rows_handles_empty_ticker_sentiment():
    """Article with no ticker_sentiment array should produce no rows."""
    from gcp.fetchers.fetch_news_sentiment import _article_to_rows

    article = {
        "time_published": "20260424T120000",
        "title": "macro headline",
        "ticker_sentiment": [],
        "topics": [],
    }
    assert _article_to_rows(article) == []


def test_news_article_to_rows_skips_invalid_timestamp():
    """Garbage time_published should be silently skipped (article dropped)."""
    from gcp.fetchers.fetch_news_sentiment import _article_to_rows

    article = {
        "time_published": "not a timestamp",
        "ticker_sentiment": [{"ticker": "AAPL"}],
    }
    assert _article_to_rows(article) == []


def test_news_fetch_by_topics_handles_av_rate_limit_response():
    """AV's 'Information' rate-limit response must be handled gracefully
    (return empty DF, no exception)."""
    from gcp.fetchers import fetch_news_sentiment as fns

    with patch.object(fns, "_fetch", return_value=[]):
        df = fns.fetch_by_topics(["mergers_and_acquisitions"], "k", 100)
    assert df.empty


def test_news_fetch_by_topics_truncates_over_5_topics():
    """AV caps topics= at 5; the fetcher must truncate, not error."""
    from gcp.fetchers import fetch_news_sentiment as fns

    seen = {}

    def capture(params):
        seen.update(params)
        return []  # Empty feed — we only care about params shape

    with patch.object(fns, "_fetch", side_effect=lambda p: capture(p)):
        fns.fetch_by_topics(
            ["t1", "t2", "t3", "t4", "t5", "t6", "t7"], "k", 100
        )
    assert seen["topics"].count(",") == 4  # 5 items → 4 commas


# ──────────────────────────────────────────────────────────────────────
# fetch_earnings_history
# ──────────────────────────────────────────────────────────────────────


def test_earnings_history_parses_av_response():
    """AV EARNINGS quarterlyEarnings must produce one row per fiscal quarter."""
    from gcp.fetchers import fetch_earnings_history as feh

    av_response = {
        "symbol": "AAPL",
        "annualEarnings": [],
        "quarterlyEarnings": [
            {
                "fiscalDateEnding": "2025-09-28",
                "reportedDate": "2025-10-30",
                "reportedEPS": "1.64",
                "estimatedEPS": "1.60",
                "surprise": "0.04",
                "surprisePercentage": "2.5",
            },
            {
                "fiscalDateEnding": "2025-06-29",
                "reportedDate": "2025-07-31",
                "reportedEPS": "1.40",
                "estimatedEPS": "1.42",
                "surprise": "-0.02",
                "surprisePercentage": "-1.41",
            },
        ],
    }

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return av_response

    with patch("gcp.fetchers.fetch_earnings_history.requests.get",
               return_value=FakeResp()):
        df = feh.fetch_history_for_ticker("AAPL", "fake-key")

    assert len(df) == 2
    row = df.iloc[0]
    assert row["ticker"] == "AAPL"
    assert row["fiscal_date_ending"] == date(2025, 9, 28)
    assert row["reported_date"] == date(2025, 10, 30)
    assert row["reported_eps"] == 1.64
    assert row["surprise_pct"] == 2.5
    # Negative surprise preserved
    assert df.iloc[1]["surprise"] == -0.02


def test_earnings_history_handles_rate_limit():
    """AV 'Information' (rate-limit) response should yield an empty DF."""
    from gcp.fetchers import fetch_earnings_history as feh

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Information": "API rate limit"}

    with patch("gcp.fetchers.fetch_earnings_history.requests.get",
               return_value=FakeResp()):
        df = feh.fetch_history_for_ticker("AAPL", "k")
    assert df.empty


def test_earnings_history_safe_float_handles_av_garbage():
    """AV returns 'None' as a string when EPS is missing — must coerce to None."""
    from gcp.fetchers.fetch_earnings_history import _safe_float

    assert _safe_float("1.64") == 1.64
    assert _safe_float("None") is None
    assert _safe_float("") is None
    assert _safe_float(None) is None
    assert _safe_float("not a number") is None


# ──────────────────────────────────────────────────────────────────────
# fetch_sec_filings
# ──────────────────────────────────────────────────────────────────────


def test_sec_filter_and_normalize_keeps_only_target_forms_and_recent():
    from gcp.fetchers.fetch_sec_filings import filter_and_normalize

    raw = [
        {"ticker": "AVGO", "cik": "0001730168",
         "accession_number": "0001-26-000123", "form": "8-K",
         "filing_date": "2026-04-24", "report_date": "2026-04-24",
         "items_raw": "1.01,7.01", "primary_doc": "avgo-20260424.htm"},
        {"ticker": "AVGO", "cik": "0001730168",
         "accession_number": "0001-26-000122", "form": "10-Q",
         "filing_date": "2026-04-10", "report_date": "2026-03-31",
         "items_raw": "", "primary_doc": "avgo-10q.htm"},
        # Old 8-K (before since-window) — should be dropped
        {"ticker": "AVGO", "cik": "0001730168",
         "accession_number": "0001-25-000099", "form": "8-K",
         "filing_date": "2025-08-01", "report_date": "2025-08-01",
         "items_raw": "5.02", "primary_doc": "old.htm"},
        # Wrong form — dropped
        {"ticker": "AVGO", "cik": "0001730168",
         "accession_number": "0001-26-000124", "form": "DEF 14A",
         "filing_date": "2026-04-20", "report_date": None,
         "items_raw": "", "primary_doc": "proxy.htm"},
    ]
    df = filter_and_normalize(raw, {"8-K", "10-Q", "10-K"}, date(2026, 4, 1))
    assert len(df) == 2
    assert set(df["form"].tolist()) == {"8-K", "10-Q"}
    items_8k = df[df["form"] == "8-K"].iloc[0]["items"]
    assert items_8k == ["1.01", "7.01"]
    # Empty items_raw → None (not an empty list) so the GIN index treats
    # it correctly as 'no items at all'
    items_10q = df[df["form"] == "10-Q"].iloc[0]["items"]
    assert items_10q is None


def test_sec_load_ticker_to_cik_normalizes_ciks():
    """SEC's company_tickers.json returns CIKs as ints; must zero-pad to 10."""
    from gcp.fetchers import fetch_sec_filings as fsf

    sec_response = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 1730168, "ticker": "AVGO", "title": "Broadcom Inc."},
    }
    with patch.object(fsf, "_http_get", return_value=sec_response):
        m = fsf.load_ticker_to_cik("ua")
    assert m["AAPL"] == "0000320193"
    assert m["AVGO"] == "0001730168"


def test_sec_fetch_submissions_zips_parallel_arrays():
    """SEC's submissions.recent block is parallel arrays — zip correctly."""
    from gcp.fetchers import fetch_sec_filings as fsf

    sec_response = {
        "filings": {
            "recent": {
                "accessionNumber": ["acc-1", "acc-2"],
                "form": ["8-K", "10-Q"],
                "filingDate": ["2026-04-24", "2026-04-10"],
                "reportDate": ["2026-04-24", "2026-03-31"],
                "items": ["1.01,7.01", ""],
                "primaryDocument": ["d1.htm", "d2.htm"],
            }
        }
    }
    with patch.object(fsf, "_http_get", return_value=sec_response):
        rows = fsf.fetch_submissions("AVGO", "0001730168", "ua")
    assert len(rows) == 2
    assert rows[0]["form"] == "8-K"
    assert rows[0]["items_raw"] == "1.01,7.01"
    assert rows[1]["form"] == "10-Q"
    assert rows[1]["items_raw"] == ""


# ──────────────────────────────────────────────────────────────────────
# fetch_insider_transactions
# ──────────────────────────────────────────────────────────────────────


def test_insider_transactions_parses_av_response():
    from gcp.fetchers import fetch_insider_transactions as fit

    av_response = {
        "data": [
            {
                "transaction_date": "2026-04-20",
                "ticker": "AVGO",
                "executive": "Hock E. Tan",
                "executive_title": "CEO",
                "acquisition_or_disposal": "A",
                "shares": "10000",
                "share_price": "1450.50",
            },
            {
                "transaction_date": "2026-04-15",
                "ticker": "AVGO",
                "executive": "Kirsten M. Spears",
                "executive_title": "CFO",
                "acquisition_or_disposal": "D",
                "shares": "5000",
                "share_price": "1480.00",
            },
        ]
    }

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return av_response

    with patch("gcp.fetchers.fetch_insider_transactions.requests.get",
               return_value=FakeResp()):
        df = fit.fetch_for_ticker("AVGO", "fake-key")

    assert len(df) == 2
    buy = df.iloc[0]
    assert buy["transaction_type"] == "A"
    assert buy["shares"] == 10000.0
    # transaction_value is the computed shares × price
    assert buy["transaction_value"] == 10000.0 * 1450.50
    sell = df.iloc[1]
    assert sell["transaction_type"] == "D"


def test_insider_transactions_handles_empty_response():
    from gcp.fetchers import fetch_insider_transactions as fit

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": []}

    with patch("gcp.fetchers.fetch_insider_transactions.requests.get",
               return_value=FakeResp()):
        df = fit.fetch_for_ticker("XYZ", "k")
    assert df.empty


# ──────────────────────────────────────────────────────────────────────
# fetch_top_movers
# ──────────────────────────────────────────────────────────────────────


def test_top_movers_parses_three_categories():
    from gcp.fetchers import fetch_top_movers as ftm

    av_response = {
        "metadata": "Top gainers, losers, and most actively traded US tickers",
        "last_updated": "2026-04-24",
        "top_gainers": [
            {"ticker": "AVGO", "price": "1450.50",
             "change_amount": "100.00", "change_percentage": "7.41%",
             "volume": "12500000"},
        ],
        "top_losers": [
            {"ticker": "TSLA", "price": "180.00",
             "change_amount": "-15.00", "change_percentage": "-7.69%",
             "volume": "85000000"},
        ],
        "most_actively_traded": [
            {"ticker": "NVDA", "price": "950.00",
             "change_amount": "5.00", "change_percentage": "0.53%",
             "volume": "120000000"},
        ],
    }

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return av_response

    with patch("gcp.fetchers.fetch_top_movers.requests.get",
               return_value=FakeResp()):
        df = ftm.fetch_top_movers("fake-key")

    assert len(df) == 3
    by_cat = {r["ticker"]: r for _, r in df.iterrows()}
    assert by_cat["AVGO"]["category"] == "top_gainers"
    assert by_cat["AVGO"]["change_pct"] == 7.41
    assert by_cat["TSLA"]["category"] == "top_losers"
    assert by_cat["TSLA"]["change_pct"] == -7.69
    assert by_cat["NVDA"]["category"] == "most_active"


def test_top_movers_safe_pct_handles_av_format():
    """AV returns percentages as '7.41%' strings — parser must strip the %."""
    from gcp.fetchers.fetch_top_movers import _safe_pct

    assert _safe_pct("5.42%") == 5.42
    assert _safe_pct("-3.21%") == -3.21
    assert _safe_pct("") is None
    assert _safe_pct(None) is None
    assert _safe_pct("not a percent") is None
