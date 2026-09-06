"""Verify _backfill_targets includes market_data_daily orphans when
BACKFILL_ALL_HISTORY=true.

Audit 2026-05-30 surfaced 152 single-bar tickers that were in
earnings_calendar (so the nightly fetcher added them to
market_data_daily) but NOT in earnings_history (so --backfill skipped
them, leaving them permanently truncated). This regression test
locks in the UNION that catches them.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for k in ('BACKFILL_ALL_HISTORY',):
        monkeypatch.delenv(k, raising=False)
    yield


def _captured_sql(monkeypatch, backfill_all: bool) -> str:
    """Return the SQL that _backfill_targets sends to query_to_dataframe."""
    if backfill_all:
        monkeypatch.setenv('BACKFILL_ALL_HISTORY', 'true')

    from gcp.fetchers import fetch_market_data

    captured = {}

    def fake_query(sql):
        captured['sql'] = sql
        return pd.DataFrame()

    with patch.object(fetch_market_data, 'is_cloud_sql_configured', return_value=True), \
         patch('gcp.database.query_to_dataframe', side_effect=fake_query):
        fetch_market_data._backfill_targets()
    return captured.get('sql', '')


def test_backfill_all_union_includes_market_data_daily(monkeypatch):
    sql = _captured_sql(monkeypatch, backfill_all=True)
    # Both source tables must appear in the targets CTE, separated by UNION.
    upper = sql.upper()
    assert 'FROM EARNINGS_HISTORY' in upper, sql
    assert 'FROM MARKET_DATA_DAILY' in upper, sql
    # Verify it's a UNION (not just a LEFT JOIN against market_data_daily).
    # Both DISTINCT clauses appear in the WITH targets CTE.
    eh_pos = upper.find('FROM EARNINGS_HISTORY')
    mdd_pos = upper.find('FROM MARKET_DATA_DAILY')
    # The earnings_history reference appears before the FIRST market_data_daily
    # reference (the UNION arm). Both are present, and there's a UNION between
    # the two distinct selects.
    between = upper[eh_pos:mdd_pos]
    assert 'UNION' in between, f'expected UNION between source tables; got: {between!r}'


def test_default_filter_excludes_market_data_daily_orphans(monkeypatch):
    """Without BACKFILL_ALL_HISTORY=true, we still gate on earnings_history
    intersected with the active-volume filter. Verifies the default path
    is unchanged."""
    sql = _captured_sql(monkeypatch, backfill_all=False)
    upper = sql.upper()
    # Default path uses ELIGIBLE / EH_ELIGIBLE CTEs, no raw market_data_daily
    # UNION arm.
    assert 'EH_ELIGIBLE' in upper, sql
    # The only reference to market_data_daily should be the LEFT JOIN for
    # bar_count/max_date enrichment — not as a target-source UNION arm.
    # i.e. the word UNION should NOT appear between earnings_history and
    # the first market_data_daily.
    eh_pos = upper.find('FROM EARNINGS_HISTORY')
    mdd_pos = upper.find('FROM MARKET_DATA_DAILY')
    between = upper[eh_pos:mdd_pos]
    assert 'UNION' not in between, \
        f'default path should not UNION market_data_daily as a target source: {between!r}'
