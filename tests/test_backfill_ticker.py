"""Unit tests for gcp/backfill_ticker.py.

Lightweight suite — most of the file calls AlphaVantage and Cloud SQL,
which we don't mock for unit tests. The tests here lock down:

  * ``_parse_dates`` — env-var date parsing edge cases
  * ``add_to_watchlist`` — uses the actual schema column names
    (``user_id`` / ``ticker`` / ``added_at`` / ``removed_at``,
    composite PK on (user_id, ticker)). This is a regression
    test for the ``column "created_at" does not exist`` failure
    caught on the first NVDA smoke run.
  * ``av_news_to_rows`` — explosion + sentiment mapping
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ── Date parsing ──────────────────────────────────────────────────────────


def test_parse_dates_default_returns_7_weekdays():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates(None)
    assert len(out) == 7
    # All weekdays
    assert all(d.weekday() < 5 for d in out)
    # Sorted ascending
    assert out == sorted(out)


def test_parse_dates_comma_separated():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("2026-04-23,2026-04-24")
    assert out == [date(2026, 4, 23), date(2026, 4, 24)]


def test_parse_dates_semicolon_separated():
    """Semicolon support — gcloud --update-env-vars uses comma as its
    own delimiter, so multi-date BACKFILL_DATES values must use
    semicolons to pass through cleanly."""
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("2026-04-23;2026-04-24;2026-04-22")
    assert out == [date(2026, 4, 22), date(2026, 4, 23), date(2026, 4, 24)]


def test_parse_dates_whitespace():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("  2026-04-23   2026-04-24  ")
    assert out == [date(2026, 4, 23), date(2026, 4, 24)]


def test_parse_dates_dedupes():
    from gcp.backfill_ticker import _parse_dates
    out = _parse_dates("2026-04-23,2026-04-23,2026-04-23")
    assert out == [date(2026, 4, 23)]


# ── add_to_watchlist schema regression ───────────────────────────────────


def test_add_to_watchlist_uses_correct_columns():
    """Regression for the live failure on backfill-ticker-kddj4
    (NVDA smoke run): the INSERT used a non-existent ``created_at``
    column. The actual schema has ``added_at`` (defaulted) and
    ``removed_at`` (for soft delete), with composite PK
    (user_id, ticker). This test pins the SQL shape so future edits
    don't drift back to the wrong columns."""
    from gcp import backfill_ticker

    captured_sql: list[str] = []
    captured_params: list[dict] = []

    fake_conn = MagicMock()

    def fake_execute(stmt, params=None):
        captured_sql.append(str(stmt))
        if params is not None:
            captured_params.append(dict(params))
        return MagicMock()

    fake_conn.execute.side_effect = fake_execute
    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        backfill_ticker.add_to_watchlist("AMD")

    assert len(captured_sql) == 1
    sql = captured_sql[0]

    # Real column names from gcp/schema.sql watchlists table
    assert "user_id" in sql
    assert "ticker" in sql
    assert "removed_at" in sql
    # Wrong column name caught in production
    assert "created_at" not in sql
    # Composite-PK conflict target
    assert "ON CONFLICT (user_id, ticker)" in sql
    # Param has the upper-cased ticker
    assert captured_params[0]["t"] == "AMD"


def test_add_to_watchlist_uppercases_ticker():
    """Lowercase input must be normalised to upper before hitting SQL."""
    from gcp import backfill_ticker

    captured_params: list[dict] = []
    fake_conn = MagicMock()
    fake_conn.execute.side_effect = lambda stmt, params=None: (
        captured_params.append(dict(params)) if params else None
    )
    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("gcp.database.get_engine", return_value=fake_engine):
        backfill_ticker.add_to_watchlist("nvda")

    assert captured_params[0]["t"] == "NVDA"


# ── av_news_to_rows ──────────────────────────────────────────────────────


def test_av_news_to_rows_explodes_per_ticker_sentiment():
    from gcp.backfill_ticker import av_news_to_rows
    feed = [
        {
            "time_published": "20260423T130000",
            "title": "AMD/Google deal closes",
            "url": "https://example.com/news",
            "summary": "AMD GOOGL announce deal",
            "source": "TestWire",
            "overall_sentiment_score": 0.45,
            "overall_sentiment_label": "Bullish",
            "topics": [{"topic": "Mergers & Acquisitions",
                        "relevance_score": "0.8"}],
            "ticker_sentiment": [
                {"ticker": "AMD", "ticker_sentiment_score": "0.5",
                 "relevance_score": "0.9"},
                {"ticker": "GOOGL", "ticker_sentiment_score": "0.3",
                 "relevance_score": "0.7"},
            ],
        },
    ]
    rows = av_news_to_rows(feed)
    # 1 article × 2 tickers → 2 rows
    assert len(rows) == 2
    by_ticker = {r["ticker"]: r for r in rows}
    assert "AMD" in by_ticker and "GOOGL" in by_ticker
    assert by_ticker["AMD"]["sentiment_score"] == 0.5
    assert by_ticker["GOOGL"]["sentiment_score"] == 0.3
    # Both share the same overall sentiment + topics
    assert by_ticker["AMD"]["overall_sentiment_score"] == 0.45
    assert by_ticker["AMD"]["topics"] == ["Mergers & Acquisitions"]


def test_av_news_to_rows_skips_unparseable_timestamp():
    from gcp.backfill_ticker import av_news_to_rows
    feed = [{"time_published": "garbage", "ticker_sentiment": [
        {"ticker": "AMD"}
    ]}]
    assert av_news_to_rows(feed) == []


def test_av_news_to_rows_tagged_data_source():
    from gcp.backfill_ticker import av_news_to_rows
    feed = [{
        "time_published": "20260423T130000",
        "ticker_sentiment": [{"ticker": "AMD",
                              "ticker_sentiment_score": "0.2",
                              "relevance_score": "0.5"}],
    }]
    rows = av_news_to_rows(feed)
    assert rows[0]["data_source"] == "alphavantage"
    assert rows[0]["match_method"] == "av_ticker_sentiment"
