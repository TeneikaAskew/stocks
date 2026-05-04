"""Hermetic tests for gcp/cleanup_stale_data.py.

The cleanup driver issues SQL counts + DELETEs against three tables.
We patch query_to_dataframe + the engine factory so the suite is
hermetic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gcp import cleanup_stale_data as cleanup


# ────────────────────────────────────────────────────────────
# _build_active_ticker_set
# ────────────────────────────────────────────────────────────

class TestActiveTickerSet:
    def test_includes_static_set_even_if_db_empty(self):
        with patch('gcp.database.query_to_dataframe',
                   return_value=pd.DataFrame()):
            active = cleanup._build_active_ticker_set()
        assert set(active) >= set(cleanup.STATIC_SET)

    def test_unions_calendar_watchlist_and_static(self):
        # calendar UNION watchlists returns {AVGO, NVDA, AAPL}
        df = pd.DataFrame({'ticker': ['AVGO', 'NVDA', 'AAPL']})
        with patch('gcp.database.query_to_dataframe', return_value=df):
            active = cleanup._build_active_ticker_set()
        s = set(active)
        # Static set always present
        assert s >= set(cleanup.STATIC_SET)
        # And every db-returned ticker is preserved
        assert {'AVGO', 'NVDA', 'AAPL'}.issubset(s)

    def test_uppercases_and_dedupes(self):
        # Even if DB returned mixed-case + dup, we expect uppercase + unique
        df = pd.DataFrame({'ticker': ['avgo', 'AVGO', 'Nvda']})
        with patch('gcp.database.query_to_dataframe', return_value=df):
            active = cleanup._build_active_ticker_set()
        # uppercase
        assert all(t == t.upper() for t in active)
        # no duplicates
        assert len(active) == len(set(active))


# ────────────────────────────────────────────────────────────
# cleanup_earnings_calendar — date-window-based cleanup
# ────────────────────────────────────────────────────────────

class TestCleanupEarningsCalendar:
    def test_dry_run_does_not_delete(self):
        # Two scalar reads: total + in-window. _execute MUST NOT be called.
        scalar_returns = iter([
            pd.DataFrame([{'count': 9000}]),  # total
            pd.DataFrame([{'count': 7500}]),  # in-window
        ])
        with patch(
            'gcp.database.query_to_dataframe',
            side_effect=lambda *a, **k: next(scalar_returns),
        ), patch.object(cleanup, '_execute') as m_exec:
            before, deleted = cleanup.cleanup_earnings_calendar(
                active=['AAPL', 'MSFT'], dry_run=True,
            )
        assert before == 9000
        assert deleted == 0
        assert m_exec.call_count == 0

    def test_live_run_deletes_outside_window(self):
        scalar_returns = iter([
            pd.DataFrame([{'count': 9000}]),
            pd.DataFrame([{'count': 7500}]),
        ])
        with patch(
            'gcp.database.query_to_dataframe',
            side_effect=lambda *a, **k: next(scalar_returns),
        ), patch.object(cleanup, '_execute', return_value=1500) as m_exec:
            before, deleted = cleanup.cleanup_earnings_calendar(
                active=['AAPL'], dry_run=False,
            )
        assert before == 9000
        assert deleted == 1500
        assert m_exec.call_count == 1
        # The DELETE SQL targets earnings_calendar
        sql_arg = m_exec.call_args[0][0]
        assert 'DELETE FROM earnings_calendar' in sql_arg
        assert 'NOT BETWEEN' in sql_arg

    def test_no_op_when_already_clean(self):
        scalar_returns = iter([
            pd.DataFrame([{'count': 7500}]),  # total
            pd.DataFrame([{'count': 7500}]),  # in-window — already pruned
        ])
        with patch(
            'gcp.database.query_to_dataframe',
            side_effect=lambda *a, **k: next(scalar_returns),
        ), patch.object(cleanup, '_execute') as m_exec:
            before, deleted = cleanup.cleanup_earnings_calendar(
                active=['AAPL'], dry_run=False,
            )
        assert deleted == 0
        assert m_exec.call_count == 0  # nothing to delete


# ────────────────────────────────────────────────────────────
# cleanup_market_data_daily — ticker-set-based
# ────────────────────────────────────────────────────────────

class TestCleanupMarketDataDaily:
    def test_dry_run_does_not_delete(self):
        scalar_returns = iter([
            pd.DataFrame([{'count': 310}]),       # n_distinct
            pd.DataFrame([{'count': 280}]),       # n_active
            pd.DataFrame([{'count': 1_000_000}]), # rows_before
        ])
        with patch(
            'gcp.database.query_to_dataframe',
            side_effect=lambda *a, **k: next(scalar_returns),
        ), patch.object(cleanup, '_execute') as m_exec:
            before, deleted = cleanup.cleanup_market_data_daily(
                active=['AAPL'], dry_run=True,
            )
        assert before == 1_000_000
        assert deleted == 0
        assert m_exec.call_count == 0

    def test_empty_active_set_refuses_to_wipe(self):
        """Defensive: empty active set → no-op (avoids accidental table wipe)."""
        with patch.object(cleanup, '_execute') as m_exec, \
             patch('gcp.database.query_to_dataframe') as m_q:
            before, deleted = cleanup.cleanup_market_data_daily(
                active=[], dry_run=False,
            )
        assert deleted == 0
        assert m_exec.call_count == 0
        assert m_q.call_count == 0

    def test_live_run_deletes_inactive_tickers(self):
        scalar_returns = iter([
            pd.DataFrame([{'count': 310}]),
            pd.DataFrame([{'count': 280}]),
            pd.DataFrame([{'count': 1_000_000}]),
        ])
        with patch(
            'gcp.database.query_to_dataframe',
            side_effect=lambda *a, **k: next(scalar_returns),
        ), patch.object(cleanup, '_execute', return_value=12345) as m_exec:
            before, deleted = cleanup.cleanup_market_data_daily(
                active=['AAPL', 'MSFT'], dry_run=False,
            )
        assert deleted == 12345
        assert m_exec.call_count == 1
        sql_arg = m_exec.call_args[0][0]
        assert 'DELETE FROM market_data_daily' in sql_arg
        assert 'ticker <> ALL' in sql_arg
        # The active param is bound
        params = m_exec.call_args[0][1]
        assert params == {'active': ['AAPL', 'MSFT']}


# ────────────────────────────────────────────────────────────
# cleanup_market_data_intraday — symmetric to daily
# ────────────────────────────────────────────────────────────

class TestCleanupMarketDataIntraday:
    def test_live_run_deletes_inactive_intraday(self):
        scalar_returns = iter([
            pd.DataFrame([{'count': 181}]),
            pd.DataFrame([{'count': 173}]),
            pd.DataFrame([{'count': 5_000_000}]),
        ])
        with patch(
            'gcp.database.query_to_dataframe',
            side_effect=lambda *a, **k: next(scalar_returns),
        ), patch.object(cleanup, '_execute', return_value=8000) as m_exec:
            before, deleted = cleanup.cleanup_market_data_intraday(
                active=['SPY'], dry_run=False,
            )
        assert deleted == 8000
        sql_arg = m_exec.call_args[0][0]
        assert 'DELETE FROM market_data_intraday' in sql_arg


# ────────────────────────────────────────────────────────────
# run() — top-level integration (still hermetic)
# ────────────────────────────────────────────────────────────

class TestRun:
    def test_dry_run_summary_no_writes(self):
        with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
             patch.object(cleanup, '_build_active_ticker_set',
                          return_value=['AAPL', 'MSFT', 'SPY']), \
             patch.object(cleanup, 'cleanup_earnings_calendar',
                          return_value=(9000, 0)), \
             patch.object(cleanup, 'cleanup_market_data_daily',
                          return_value=(1_000_000, 0)), \
             patch.object(cleanup, 'cleanup_market_data_intraday',
                          return_value=(5_000_000, 0)):
            summary = cleanup.run(dry_run=True)
        assert summary['dry_run'] is True
        assert summary['active_count'] == 3
        assert summary['earnings_calendar']['deleted'] == 0
        assert summary['market_data_daily']['deleted'] == 0
        assert summary['market_data_intraday']['deleted'] == 0

    def test_live_run_passes_through_deletes(self):
        with patch('gcp.database.is_cloud_sql_configured', return_value=True), \
             patch.object(cleanup, '_build_active_ticker_set',
                          return_value=['AAPL']), \
             patch.object(cleanup, 'cleanup_earnings_calendar',
                          return_value=(9000, 1500)), \
             patch.object(cleanup, 'cleanup_market_data_daily',
                          return_value=(1_000_000, 12000)), \
             patch.object(cleanup, 'cleanup_market_data_intraday',
                          return_value=(5_000_000, 8000)):
            summary = cleanup.run(dry_run=False)
        assert summary['earnings_calendar']['deleted'] == 1500
        assert summary['market_data_daily']['deleted'] == 12000
        assert summary['market_data_intraday']['deleted'] == 8000
