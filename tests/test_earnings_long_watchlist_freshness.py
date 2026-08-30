from datetime import date, datetime
from unittest.mock import Mock

import pandas as pd
import pytest

from gcp import earnings_long_watchlist as watchlist


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 8, 30), date(2026, 8, 30)),
        (datetime(2026, 8, 30, 12, 0), date(2026, 8, 30)),
        (pd.Timestamp("2026-08-30T12:00:00Z"), date(2026, 8, 30)),
        ("2026-08-30", date(2026, 8, 30)),
        (None, None),
    ],
)
def test_normalize_source_date(value, expected):
    assert watchlist._normalize_source_date(value) == expected


def test_stale_source_suppresses_query_and_post(monkeypatch):
    monkeypatch.setattr(watchlist, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(watchlist, "_latest_source_date", lambda: date(2026, 5, 22))
    monkeypatch.setattr(watchlist, "date", Mock(today=lambda: date(2026, 8, 30)))
    query = Mock()
    post = Mock()
    monkeypatch.setattr(watchlist, "_query_watchlist", query)
    monkeypatch.setattr(watchlist, "send_to_discord", post)

    assert watchlist.main([]) == 1
    query.assert_not_called()
    post.assert_not_called()


def test_fresh_source_reaches_posting_path(monkeypatch):
    monkeypatch.setattr(watchlist, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(watchlist, "_latest_source_date", lambda: date(2026, 8, 24))
    monkeypatch.setattr(watchlist, "date", Mock(today=lambda: date(2026, 8, 30)))
    monkeypatch.setattr(watchlist, "_query_watchlist", lambda *_: pd.DataFrame())
    post = Mock(return_value=True)
    monkeypatch.setattr(watchlist, "send_to_discord", post)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")

    assert watchlist.main([]) == 0
    post.assert_called_once()
