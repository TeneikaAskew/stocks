"""The catalyst snapshot's news window is the Eastern day (FEAT-DATA-001, stage 1).

`GET /api/catalysts/asof/{ticker}` takes its cutoff as an Eastern date (the
exchange's date when the caller names none). `news_sentiment.published_ts` is
a TIMESTAMPTZ and the database session is UTC, so the window has to be turned
into instants on the named zone. This runs the real query against the real
schema with articles on both sides of each edge:

  cutoff 2026-11-13, window_days 7 (EST, UTC-5)
    2026-11-06T04:30Z  23:30 on Nov 5 Eastern   before the window
    2026-11-06T05:30Z  00:30 on Nov 6 Eastern   first day of the window
    2026-11-13T23:00Z  18:00 on Nov 13 Eastern  inside
    2026-11-14T00:30Z  19:30 on Nov 13 Eastern  inside (UTC date is the 14th)
    2026-11-14T05:30Z  00:30 on Nov 14 Eastern  after the window

A window cut at 23:59 UTC of the cutoff date drops the 19:30 article, the
evening news of the day the request is made on.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DB_HOST"),
    reason="integration tests need a Postgres (DB_HOST): see the "
    "integration-tests CI job in backtest-pipeline.yml",
)

ARTICLES = [
    ("2026-11-06T04:30:00Z", "before the window"),
    ("2026-11-06T05:30:00Z", "first Eastern day"),
    ("2026-11-13T23:00:00Z", "afternoon of the cutoff"),
    ("2026-11-14T00:30:00Z", "evening of the cutoff"),
    ("2026-11-14T05:30:00Z", "after the window"),
]


@pytest.fixture
def news_rows(db_engine):
    import sqlalchemy

    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text("DELETE FROM news_sentiment WHERE ticker = 'TSTN'"))
        for published, title in ARTICLES:
            conn.execute(
                sqlalchemy.text(
                    "INSERT INTO news_sentiment (ticker, published_ts, title, url) "
                    "VALUES ('TSTN', CAST(:ts AS timestamptz), :title, :url)"),
                {"ts": published, "title": title, "url": f"https://example.test/{title}"},
            )
    yield
    with db_engine.begin() as conn:
        conn.execute(sqlalchemy.text("DELETE FROM news_sentiment WHERE ticker = 'TSTN'"))


def test_the_window_holds_the_evening_article_and_stops_at_eastern_midnight(news_rows):
    pytest.importorskip("fastapi")
    repo = Path(__file__).resolve().parents[2]
    for path in (repo, repo / "platform", repo / "platform" / "api"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    from api.routers import catalysts

    body = catalysts.get_catalyst_snapshot("TSTN", as_of="2026-11-13", window_days=7)

    titles = [row["title"] for row in body["news"]]
    assert titles == [
        "evening of the cutoff",
        "afternoon of the cutoff",
        "first Eastern day",
    ]
