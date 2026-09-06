import logging
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


def test_a_failed_freshness_probe_is_not_reported_as_a_missing_snapshot(
    monkeypatch, caplog
):
    """An unreachable database must not read as an empty winners table.

    Both suppress the post, but only one of them is fixed by re-running the
    upstream fetcher — so the log has to say which happened. Patches the
    engine rather than the query helper so the real swallow path runs.
    """
    monkeypatch.setattr(watchlist, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(watchlist, "date", Mock(today=lambda: date(2026, 8, 30)))

    def unreachable(*_args, **_kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr("gcp.database.get_engine", unreachable)

    query = Mock()
    post = Mock()
    monkeypatch.setattr(watchlist, "_query_watchlist", query)
    monkeypatch.setattr(watchlist, "send_to_discord", post)

    with caplog.at_level(logging.ERROR):
        assert watchlist.main([]) == 1

    query.assert_not_called()
    post.assert_not_called()
    assert "cannot determine" in caplog.text.lower()
    # The stale/missing-snapshot wording is a different finding and must not
    # be what an operator sees when the probe itself could not run.
    assert "older than" not in caplog.text


def test_a_failed_candidate_query_does_not_post_an_empty_watchlist(
    monkeypatch, caplog
):
    """A database failure must not publish as "no candidates this week".

    The freshness probe passes here, so this exercises the second query. The
    swallowing helper turned its failure into an empty frame, which built a
    perfectly well-formed empty Discord post and exited 0.
    """
    monkeypatch.setattr(watchlist, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(watchlist, "date", Mock(today=lambda: date(2026, 8, 30)))
    monkeypatch.setattr(watchlist, "_latest_source_date", lambda: date(2026, 8, 24))

    def unreachable(*_args, **_kwargs):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr("gcp.database.get_engine", unreachable)

    post = Mock()
    monkeypatch.setattr(watchlist, "send_to_discord", post)

    with caplog.at_level(logging.ERROR):
        assert watchlist.main([]) != 0

    post.assert_not_called()
    assert "candidate query failed" in caplog.text.lower()
