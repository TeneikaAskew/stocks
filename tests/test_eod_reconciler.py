"""Smoke tests for `gcp/signal_monitor_eod_resolver.py`.

The full main() loop hits Cloud SQL, so we test:
  - The pure helpers (`open_alerts_sql`, `intraday_bars_sql`,
    `_alert_close_ts`, `_alert_ts_to_et_naive`, `_row_to_position`)
    which are I/O-free.
  - End-to-end main() with `query_to_dataframe` mocked so the SQL
    contracts are exercised but no real DB is needed.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from gcp.signal_monitor_eod_resolver import (
    _alert_close_ts,
    _alert_ts_to_et_naive,
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
    # Track A G.P0.10 — codex review on PR #324 caught two bugs:
    # 1. SELECT must NOT include rsi_14 (column doesn't exist on
    #    market_data_intraday — it's OHLCV-only). RSI is computed on
    #    the fly downstream.
    # 2. Range bounds use ET-naive (matching the writer convention),
    #    not UTC. Param names must reflect that to avoid drift.
    assert 'rsi_14' not in sql
    assert ':alert_ts_et' in sql
    assert ':alert_close_et' in sql
    assert 'order by ts' in sql


def test_alert_close_ts_returns_naive_et():
    """Both EDT and EST collapse to the same naive ET timestamp because
    market_data_intraday.ts is stored as naive ET (the AV writer's
    "ET-as-UTC" convention)."""
    edt_close = _alert_close_ts(date(2026, 5, 8))   # EDT month
    est_close = _alert_close_ts(date(2026, 1, 15))  # EST month
    assert edt_close.tzinfo is None
    assert est_close.tzinfo is None
    assert edt_close == datetime(2026, 5, 8, 16, 0, 0)
    assert est_close == datetime(2026, 1, 15, 16, 0, 0)


class TestAlertTsToEtNaive:
    """The intraday writer stores ts as naive ET; signal_alerts.alert_ts
    is TIMESTAMPTZ stored as UTC. Without conversion, a 10:00 ET alert
    at 14:00 UTC would skip every bar before 14:00 (= 14:00 ET, 4
    hours after market close on a 9:30-16:00 session)."""

    def test_tz_aware_utc_converts_to_et(self):
        # 14:00 UTC on 2026-05-08 (EDT) = 10:00 ET
        utc = datetime(2026, 5, 8, 14, 0, 0, tzinfo=timezone.utc)
        out = _alert_ts_to_et_naive(utc)
        assert out.tzinfo is None
        assert out == datetime(2026, 5, 8, 10, 0, 0)

    def test_tz_aware_winter_converts_to_et(self):
        # 14:00 UTC on 2026-01-15 (EST) = 09:00 ET
        utc = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        out = _alert_ts_to_et_naive(utc)
        assert out == datetime(2026, 1, 15, 9, 0, 0)

    def test_naive_ts_is_treated_as_utc(self):
        # Naive 14:00 (assumed UTC) → 10:00 ET (EDT)
        naive = datetime(2026, 5, 8, 14, 0, 0)
        out = _alert_ts_to_et_naive(naive)
        assert out == datetime(2026, 5, 8, 10, 0, 0)


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
    """End-to-end: one open alert + intraday bars → UPDATE called once.

    The alert_ts is 14:00 UTC = 10:00 ET (EDT). Intraday bars are
    stored as naive ET (10:00 ET shows as 10:00 in the ts column).
    The resolver converts alert_ts to ET for the SQL filter, then
    re-anchors the returned bars back to UTC for elapsed-min math
    against pos.alert_ts (naive UTC)."""
    open_alert = pd.DataFrame([{
        'id': 1, 'ticker': 'SPY', 'direction': 'CALL',
        'alert_ts': datetime(2026, 5, 8, 14, 0, 0),  # 14:00 UTC = 10:00 ET
        'alert_date': date(2026, 5, 8),
        'price_at_signal': 500.0, 'target_price': 503.0,
        'time_stop_minutes': 20,
    }])
    # Bars are naive ET (writer convention). Target hit at 10:05 ET = 14:05 UTC.
    bars = pd.DataFrame([
        {'ts': datetime(2026, 5, 8, 10, 1, 0), 'close': 501.0},
        {'ts': datetime(2026, 5, 8, 10, 5, 0), 'close': 503.5},  # target hit
    ])

    eng, conn = _fake_engine()
    captured = {'queries': []}

    def fake_query(sql, params=None):
        captured['queries'].append((sql, params))
        if 'signal_alerts' in sql.lower():
            return open_alert
        return bars.copy()

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
    # Intraday-bar query bound naive ET, not UTC. Track A G.P0.10 fix
    # for codex review on PR #324.
    intra_q = next(p for s, p in captured['queries']
                   if 'market_data_intraday' in s.lower())
    assert intra_q['alert_ts_et'] == datetime(2026, 5, 8, 10, 0, 0)
    assert intra_q['alert_close_et'] == datetime(2026, 5, 8, 16, 0, 0)


@patch('gcp.database.is_cloud_sql_configured', return_value=True)
def test_main_dry_run_does_not_persist(mock_cfg):
    open_alert = pd.DataFrame([{
        'id': 1, 'ticker': 'SPY', 'direction': 'CALL',
        'alert_ts': datetime(2026, 5, 8, 14, 0, 0),
        'alert_date': date(2026, 5, 8),
        'price_at_signal': 500.0, 'target_price': 503.0,
        'time_stop_minutes': 20,
    }])
    # Bars in naive ET (10:05 = 5 minutes after the 10:00 ET alert)
    bars = pd.DataFrame([
        {'ts': datetime(2026, 5, 8, 10, 5, 0), 'close': 503.5},
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
