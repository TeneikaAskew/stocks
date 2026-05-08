"""Smoke tests for `gcp/signal_monitor_eod_resolver.py`.

The full main() loop hits Cloud SQL, so we test:
  - The pure helpers (`open_alerts_sql`, `intraday_bars_sql`,
    `_alert_close_ts`, `_row_to_position`) which are I/O-free.
  - End-to-end main() with `query_to_dataframe` mocked so the SQL
    contracts are exercised but no real DB is needed.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from gcp.signal_monitor_eod_resolver import (
    _alert_close_ts,
    _row_to_position,
    intraday_bars_sql,
    main,
    open_alerts_sql,
)


# ── Pure helper tests ────────────────────────────────────────────────


def test_open_alerts_sql_filters_by_cutoff_and_open_state():
    sql = open_alerts_sql().lower()
    assert 'alert_date >= :cutoff_date' in sql
    # The OR clause catches both legacy rows (no is_open) AND live-set rows
    assert 'is_open is not false' in sql
    assert 'exit_ts is null' in sql


def test_intraday_bars_sql_bounds_to_alert_date_close():
    sql = intraday_bars_sql().lower()
    assert "interval = '1min'" in sql
    assert ':alert_ts' in sql
    assert ':alert_close_ts' in sql
    assert 'order by ts' in sql


def test_alert_close_ts_returns_naive_utc():
    """Mar–Nov: 16:00 ET = 20:00 UTC (EDT)."""
    out = _alert_close_ts(date(2026, 5, 8))
    assert out.tzinfo is None
    # 16:00 ET on May 8 (EDT) → 20:00 UTC
    assert out == datetime(2026, 5, 8, 20, 0, 0)


def test_alert_close_ts_winter_returns_correct_utc():
    """Nov–Mar: 16:00 ET = 21:00 UTC (EST)."""
    out = _alert_close_ts(date(2026, 1, 15))
    assert out == datetime(2026, 1, 15, 21, 0, 0)


def test_row_to_position_strips_tz():
    """Cloud SQL returns alert_ts as TIMESTAMPTZ; replay expects naive UTC."""
    row = {
        'ticker': 'SPY',
        'direction': 'CALL',
        'alert_ts': datetime(2026, 5, 8, 14, 30, 0, tzinfo=timezone.utc),
        'price_at_signal': 500.0,
        'target_price': 502.5,
        'time_stop_minutes': 20,
    }
    pos = _row_to_position(row)
    assert pos.alert_ts.tzinfo is None
    assert pos.alert_ts == datetime(2026, 5, 8, 14, 30, 0)
    assert pos.target_price == 502.5


# ── main() loop with mocked DB ───────────────────────────────────────


def _fake_engine():
    """Returns a MagicMock that supports `with engine.begin() as conn`."""
    eng = MagicMock()
    conn = MagicMock()
    eng.begin.return_value.__enter__.return_value = conn
    eng.begin.return_value.__exit__.return_value = False
    return eng, conn


@patch('gcp.database.is_cloud_sql_configured', return_value=False)
def test_main_exits_2_when_sql_unconfigured(mock_cfg):
    code = main(['--dry-run'])
    assert code == 2


@patch('gcp.database.is_cloud_sql_configured', return_value=True)
def test_main_returns_zero_when_no_open_alerts(mock_cfg):
    with patch('gcp.database.query_to_dataframe',
               return_value=pd.DataFrame()):
        with patch('gcp.database.get_engine'):
            code = main(['--dry-run'])
    assert code == 0


@patch('gcp.database.is_cloud_sql_configured', return_value=True)
def test_main_persists_resolved_exits(mock_cfg):
    """End-to-end: one open alert + intraday bars → UPDATE called once."""
    open_alert = pd.DataFrame([{
        'id': 1, 'ticker': 'SPY', 'direction': 'CALL',
        'alert_ts': datetime(2026, 5, 8, 14, 0, 0),
        'alert_date': date(2026, 5, 8),
        'price_at_signal': 500.0, 'target_price': 503.0,
        'time_stop_minutes': 20,
    }])
    # Bars include a target-hit at minute 5
    bars = pd.DataFrame([
        {'ts': datetime(2026, 5, 8, 14, 1, 0), 'close': 501.0, 'rsi_14': 60},
        {'ts': datetime(2026, 5, 8, 14, 5, 0), 'close': 503.5, 'rsi_14': 65},  # target hit
    ])

    eng, conn = _fake_engine()
    call_count = {'n': 0}

    def fake_query(sql, params=None):
        call_count['n'] += 1
        # First call returns open alerts; subsequent calls return bars.
        if 'signal_alerts' in sql.lower():
            return open_alert
        return bars

    with patch('gcp.database.query_to_dataframe', side_effect=fake_query):
        with patch('gcp.database.get_engine', return_value=eng):
            code = main(['--lookback-days', '7'])

    assert code == 0
    # UPDATE was executed once via conn.execute
    assert conn.execute.call_count == 1
    # Verify the params dict carries the right shape
    _stmt, params = conn.execute.call_args.args
    assert params['ticker'] == 'SPY'
    assert params['exit_reason'] == 'target_hit'
    assert params['exit_price'] == 503.5
    assert params['alert_ts'] == datetime(2026, 5, 8, 14, 0, 0)


@patch('gcp.database.is_cloud_sql_configured', return_value=True)
def test_main_dry_run_does_not_persist(mock_cfg):
    open_alert = pd.DataFrame([{
        'id': 1, 'ticker': 'SPY', 'direction': 'CALL',
        'alert_ts': datetime(2026, 5, 8, 14, 0, 0),
        'alert_date': date(2026, 5, 8),
        'price_at_signal': 500.0, 'target_price': 503.0,
        'time_stop_minutes': 20,
    }])
    bars = pd.DataFrame([
        {'ts': datetime(2026, 5, 8, 14, 5, 0), 'close': 503.5, 'rsi_14': 65},
    ])
    eng, conn = _fake_engine()

    def fake_query(sql, params=None):
        return open_alert if 'signal_alerts' in sql.lower() else bars

    with patch('gcp.database.query_to_dataframe', side_effect=fake_query):
        with patch('gcp.database.get_engine', return_value=eng):
            code = main(['--dry-run'])

    assert code == 0
    # In dry-run mode, NO UPDATE is fired
    assert conn.execute.call_count == 0


@patch('gcp.database.is_cloud_sql_configured', return_value=True)
def test_main_skips_when_no_intraday_bars(mock_cfg):
    """If market_data_intraday is empty for the alert window (dropped
    on a weekend or the data is gone), the script should log and skip,
    not crash."""
    open_alert = pd.DataFrame([{
        'id': 1, 'ticker': 'SPY', 'direction': 'CALL',
        'alert_ts': datetime(2026, 5, 8, 14, 0, 0),
        'alert_date': date(2026, 5, 8),
        'price_at_signal': 500.0, 'target_price': 503.0,
        'time_stop_minutes': 20,
    }])
    eng, conn = _fake_engine()

    def fake_query(sql, params=None):
        return open_alert if 'signal_alerts' in sql.lower() else pd.DataFrame()

    with patch('gcp.database.query_to_dataframe', side_effect=fake_query):
        with patch('gcp.database.get_engine', return_value=eng):
            code = main([])

    assert code == 0
    assert conn.execute.call_count == 0
