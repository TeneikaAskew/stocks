"""Tests for the fail-fast guards added in PR-A2 (track-A G.P0.2).

The guards defend against two failure modes that combined to cause the
2026-04-27 → 2026-05-08 silent freeze:

1. **Sticky --args latch**: a backfill done via
   `gcloud run jobs update --args="--date=..."` left the date latched on
   every subsequent scheduled execution. `_assert_fetch_date_fresh`
   aborts when the resolved fetch_date is more than 5 calendar days
   behind today (ET).

2. **Silent zero-row writes**: AV returning no data caused the per-ticker
   loop to log warnings and exit 0; market_data_daily was never updated
   but the cron looked successful. `_verify_post_fetch_rows` queries the
   table after the loop and exits non-zero if SPY/IWM/QQQ have no NOT
   NULL close for fetch_date on a weekday.

Both helpers are extracted from main() so they're testable without
mocking the full AV/DB/GCS pipeline (matching the pattern used by
test_fetch_market_data_tz.py).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from gcp.fetchers.fetch_market_data import (
    _assert_fetch_date_fresh,
    _verify_post_fetch_rows,
)


class TestAssertFetchDateFresh:
    def test_today_passes(self):
        _assert_fetch_date_fresh('2026-05-08', today_et=date(2026, 5, 8))

    def test_yesterday_passes(self):
        _assert_fetch_date_fresh('2026-05-07', today_et=date(2026, 5, 8))

    def test_long_weekend_monday_passes(self):
        # Mon morning fetcher reaching back to Friday is 3 days back —
        # legitimate and should not trip.
        _assert_fetch_date_fresh('2026-05-01', today_et=date(2026, 5, 4))

    def test_holiday_tuesday_passes(self):
        # Tue after Memorial Day weekend reaching back to Fri is 4 days —
        # still under threshold.
        _assert_fetch_date_fresh('2026-05-22', today_et=date(2026, 5, 26))

    def test_six_days_back_aborts(self):
        with pytest.raises(SystemExit) as exc:
            _assert_fetch_date_fresh('2026-05-02', today_et=date(2026, 5, 8))
        assert exc.value.code == 4

    def test_eleven_days_back_aborts(self):
        # The actual freeze scenario: fetch_date latched 11 days back.
        with pytest.raises(SystemExit) as exc:
            _assert_fetch_date_fresh('2026-04-27', today_et=date(2026, 5, 8))
        assert exc.value.code == 4


def _fake_query(rows: int):
    """Returns a query_fn that pretends the COUNT(*) returned `rows`."""
    def _q(sql, params):
        return pd.DataFrame([{'n': rows}])
    return _q


class TestVerifyPostFetchRows:
    def test_zero_rows_on_weekday_aborts(self, monkeypatch):
        monkeypatch.setattr(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            lambda: True)
        with pytest.raises(SystemExit) as exc:
            _verify_post_fetch_rows(
                '2026-05-07', ['SPY', 'IWM', 'QQQ'],
                _query_fn=_fake_query(0))
        assert exc.value.code == 5

    def test_nonzero_rows_passes(self, monkeypatch):
        monkeypatch.setattr(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            lambda: True)
        _verify_post_fetch_rows(
            '2026-05-07', ['SPY', 'IWM', 'QQQ'],
            _query_fn=_fake_query(3))

    def test_weekend_skips_check(self, monkeypatch):
        # 2026-05-09 is a Saturday — verification is intentionally skipped
        # (no market data exists). Pass _query_fn that would FAIL if called
        # to assert it isn't called.
        def _should_not_be_called(sql, params):
            raise AssertionError("query_fn should not run on weekends")
        monkeypatch.setattr(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            lambda: True)
        _verify_post_fetch_rows(
            '2026-05-09', ['SPY', 'IWM', 'QQQ'],
            _query_fn=_should_not_be_called)

    def test_no_key_tickers_in_universe_skips_check(self, monkeypatch):
        def _should_not_be_called(sql, params):
            raise AssertionError("query_fn should not run if SPY/IWM/QQQ absent")
        monkeypatch.setattr(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            lambda: True)
        # Earnings-window-only run with no SPY/IWM/QQQ
        _verify_post_fetch_rows(
            '2026-05-07', ['AAPL', 'MSFT'],
            _query_fn=_should_not_be_called)

    def test_uses_array_predicate_not_in_clause(self, monkeypatch):
        """SQLAlchemy text() doesn't auto-expand a tuple bind to an
        IN (...) list under pg8000 — Postgres rejects `IN $1` and the
        query silently returns 0 rows, forcing exit 5 on every weekday
        run. Use `= ANY(:tickers)` with a list parameter instead.
        Regression test for codex review on PR #322."""
        captured = {}

        def _capture(sql, params):
            captured['sql'] = sql
            captured['params'] = params
            return pd.DataFrame([{'n': 3}])

        monkeypatch.setattr(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            lambda: True)
        _verify_post_fetch_rows(
            '2026-05-07', ['SPY', 'IWM', 'QQQ'],
            _query_fn=_capture)
        assert '= ANY(:tickers)' in captured['sql'], (
            "Use ANY-array predicate; bare `IN :tk` doesn't bind under pg8000."
        )
        assert isinstance(captured['params']['tickers'], list)
        assert 'tk' not in captured['params']

    def test_local_dev_skips_check_when_sql_unconfigured(self, monkeypatch):
        def _should_not_be_called(sql, params):
            raise AssertionError("query_fn should not run without SQL configured")
        monkeypatch.setattr(
            'gcp.fetchers.fetch_market_data.is_cloud_sql_configured',
            lambda: False)
        _verify_post_fetch_rows(
            '2026-05-07', ['SPY', 'IWM', 'QQQ'],
            _query_fn=_should_not_be_called)
