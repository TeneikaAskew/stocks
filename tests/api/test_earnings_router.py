"""Hermetic tests for platform/api/routers/earnings.py.

Mocks gcp.database.query_to_dataframe_strict so tests run offline. Verifies:
  - Endpoint shapes (rows + count for collections; single dict for /event)
  - 503 when Cloud SQL unconfigured
  - 404 when ticker/event not found
  - Cache-Control headers set per-endpoint TTL
  - DataFrame → records conversion handles NaN, dates, arrays
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'platform'))

from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """A TestClient with the earnings router mounted in isolation.

    We DON'T import the full platform/api/main.py app because that
    pulls in many heavy deps. Instead, mount just the earnings router
    on a fresh FastAPI app. Cloud-SQL-configured env vars are set so
    the router's `_CLOUD_SQL` flag flips True; we then patch the
    actual query function.
    """
    # Force the router's CLOUD_SQL flag True at import time.
    monkeypatch.setenv('CLOUD_SQL_CONNECTION_NAME', 'test')
    monkeypatch.setenv('DB_USER', 'test')
    # Re-import the router module so it re-reads the env vars.
    import importlib
    from api.routers import earnings as earnings_mod
    importlib.reload(earnings_mod)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(earnings_mod.router)
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/upcoming
# ─────────────────────────────────────────────────────────────────────

class TestUpcoming:
    def test_returns_rows_and_count(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'MSFT', 'earnings_date': date(2026, 7, 30),
             'archetype': 'mixed', 'recommended_structure_long_only': 'LONG STRDL',
             'recommended_structure_ic_mode': 'IC', 'lean_score': 0.12,
             'long_winner_count': 3, 'short_winner_count': 1,
             'last_3_events': '[]'},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/upcoming?days=14')
        assert resp.status_code == 200
        data = resp.json()
        assert data['count'] == 1
        assert data['rows'][0]['ticker'] == 'MSFT'
        # Cache header set to 5 min
        assert resp.headers.get('cache-control') == 'public, max-age=300'

    def test_empty_returns_zero_count(self, client):
        with patch('gcp.database.query_to_dataframe_strict',
                   return_value=pd.DataFrame()):
            resp = client.get('/api/earnings/upcoming')
        assert resp.status_code == 200
        assert resp.json() == {'rows': [], 'count': 0}

    def test_days_param_validation(self, client):
        # days=0 should fail; days=61 should fail
        resp = client.get('/api/earnings/upcoming?days=0')
        assert resp.status_code == 422
        resp = client.get('/api/earnings/upcoming?days=61')
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/history/{ticker}
# ─────────────────────────────────────────────────────────────────────

class TestHistory:
    def test_returns_ticker_history(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'NVAX', 'reported_date': date(2024, 5, 10),
             'beat_meet_miss': 'beat', 'reaction_gap_pct': 124.2,
             'implied_move_pct': 10.2, 'realized_vs_implied_ratio': 12.2,
             'best_long_pnl_pct': 4969},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/history/NVAX?limit=10')
        assert resp.status_code == 200
        data = resp.json()
        assert data['ticker'] == 'NVAX'
        assert data['count'] == 1
        assert data['rows'][0]['beat_meet_miss'] == 'beat'
        # Cache header set to 1 hour
        assert resp.headers.get('cache-control') == 'public, max-age=3600'

    def test_404_when_no_events(self, client):
        with patch('gcp.database.query_to_dataframe_strict',
                   return_value=pd.DataFrame()):
            resp = client.get('/api/earnings/history/UNKNOWNTICKER')
        assert resp.status_code == 404

    def test_uppercases_ticker(self, client):
        captured = {}
        def _capture(sql, params=None):
            captured['params'] = params
            return pd.DataFrame([{'ticker': 'MSFT'}])
        with patch('gcp.database.query_to_dataframe_strict', side_effect=_capture):
            client.get('/api/earnings/history/msft')
        assert captured['params']['t'] == 'MSFT'


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/event/{ticker}/{date}
# ─────────────────────────────────────────────────────────────────────

class TestEvent:
    def test_returns_single_dict(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'MSFT', 'reported_date': date(2025, 7, 30),
             'beat_meet_miss': 'beat', 'reaction_gap_pct': 8.18},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/event/MSFT/2025-07-30')
        assert resp.status_code == 200
        data = resp.json()
        # Returns a dict, NOT a {rows, count} envelope — single event
        assert data['ticker'] == 'MSFT'
        assert data['beat_meet_miss'] == 'beat'
        # Cache header set to 1 day
        assert resp.headers.get('cache-control') == 'public, max-age=86400'

    def test_404_when_missing(self, client):
        with patch('gcp.database.query_to_dataframe_strict',
                   return_value=pd.DataFrame()):
            resp = client.get('/api/earnings/event/MSFT/2099-01-01')
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/lean
# ─────────────────────────────────────────────────────────────────────

class TestLean:
    def test_long_direction(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'NVAX', 'long_winner_count': 6, 'lean_score': 0.15},
            {'ticker': 'MRVL', 'long_winner_count': 9, 'lean_score': 0.08},
        ])
        captured = {}
        def _capture(sql, params=None):
            captured['sql'] = sql
            return fake_df
        with patch('gcp.database.query_to_dataframe_strict', side_effect=_capture):
            resp = client.get('/api/earnings/lean?direction=long')
        assert resp.status_code == 200
        # Long direction → ORDER BY long_winner_count DESC
        assert 'long_winner_count DESC' in captured['sql']

    def test_short_direction(self, client):
        captured = {}
        def _capture(sql, params=None):
            captured['sql'] = sql
            return pd.DataFrame()
        with patch('gcp.database.query_to_dataframe_strict', side_effect=_capture):
            client.get('/api/earnings/lean?direction=short')
        assert 'short_winner_count DESC' in captured['sql']

    def test_invalid_direction_422(self, client):
        resp = client.get('/api/earnings/lean?direction=sideways')
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/calibration
# ─────────────────────────────────────────────────────────────────────

class TestCalibration:
    def test_returns_single_dict(self, client):
        fake_df = pd.DataFrame([
            {'calibration_date': date(2026, 6, 1), 'min_nq': 12,
             'lookback_quarters': 16, 'realized_vs_implied_ratio': 0.636,
             'avg_short_strangle_pnl_pct': 20.3},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/calibration')
        assert resp.status_code == 200
        data = resp.json()
        assert data['realized_vs_implied_ratio'] == 0.636


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/health/ping (keep-warm target)
# ─────────────────────────────────────────────────────────────────────

class TestHealthPing:
    def test_ping_returns_200_with_no_store(self, client):
        with patch('gcp.database.query_to_dataframe_strict',
                   return_value=pd.DataFrame([{'ping': 1}])):
            resp = client.get('/api/earnings/health/ping')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert data['db'] == 'reachable'
        # Cache-Control no-store so intermediaries never serve stale 200
        assert resp.headers.get('cache-control') == 'no-store'

    def test_ping_handles_db_error_gracefully(self, client):
        with patch('gcp.database.query_to_dataframe_strict',
                   side_effect=RuntimeError('cloud sql unreachable')):
            resp = client.get('/api/earnings/health/ping')
        # Still 200 — keep-warm shouldn't trigger pager alerts on
        # transient db blips. Body reports error type for observability.
        assert resp.status_code == 200
        assert resp.json()['db'] == 'error'


# ─────────────────────────────────────────────────────────────────────
# 503 when Cloud SQL not configured
# ─────────────────────────────────────────────────────────────────────

class TestCloudSqlGuard:
    def test_503_when_not_configured(self, monkeypatch):
        # Wipe the env vars BEFORE the router module reimport
        monkeypatch.delenv('CLOUD_SQL_CONNECTION_NAME', raising=False)
        monkeypatch.delenv('DB_USER', raising=False)
        import importlib
        from api.routers import earnings as earnings_mod
        importlib.reload(earnings_mod)
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(earnings_mod.router)
        c = TestClient(app)
        resp = c.get('/api/earnings/upcoming')
        assert resp.status_code == 503


# ─────────────────────────────────────────────────────────────────────
# DataFrame → records helper edge cases
# ─────────────────────────────────────────────────────────────────────

class TestDfToRecords:
    def test_nan_becomes_none(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'X', 'long_winner_count': 3,
             'avg_ratio': float('nan'), 'lean_score': 0.0},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/lean')
        data = resp.json()
        assert data['rows'][0]['avg_ratio'] is None
        assert data['rows'][0]['lean_score'] == 0.0  # zero != nan

    def test_dates_become_iso_strings(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'X', 'reported_date': date(2025, 5, 1),
             'beat_meet_miss': 'beat'},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/history/X')
        assert resp.json()['rows'][0]['reported_date'] == '2025-05-01'


# ─────────────────────────────────────────────────────────────────────
# FEAT-CATALYST-001: additive daily-path descriptors through the router
# ─────────────────────────────────────────────────────────────────────
#
# Hermetic half of spec done_when item 5. The view half (actual
# earnings_event_outcomes / earnings_ticker_lean values from real
# PostgreSQL, matching native producer and brief values) lives in
# tests/integration/test_earnings_daily_path_persistence.py, which runs
# the same router against an isolated database. Here the payloads come
# from the actual producer helper, so this proves the router serializes
# every state it can emit, unchanged, with nothing dropped or coerced.

_DP_DAYS = [date(2026, 1, d) for d in (2, 5, 6, 7, 8, 9, 12)]
_DP_CLOCK = '2026-01-12T21:01:00Z'


def _daily_path(state):
    """Actual compute_daily_path_v1 output for one synthetic BMO event."""
    from lib.earnings_reactions import compute_daily_path_v1
    event = {'ticker': 'SYNTH', 'fiscal_date_ending': '2025-11-30',
             'reported_date': '2026-01-05', 'reaction_basis': 'BMO'}
    evidence = {'event_id': 'SYNTH:2025-11-30:2026-01-05',
                'source_id': 'synthetic-independent-control',
                'observed_at': _DP_CLOCK, 'acquired_at': _DP_CLOCK,
                'price_basis_id': 'synthetic:raw-one-instrument'}
    closes = [100, 112, 115, 113, 105, 99, 102]
    rows = []
    for i, (day, close) in enumerate(zip(_DP_DAYS, closes)):
        opening = 110 if i == 1 else close
        rows.append({'date': day, 'open': opening, 'high': max(opening, close) + 1,
                     'low': min(opening, close) - 1, 'close': close})
    frame = pd.DataFrame(rows)
    if state == 'not_applicable':
        frame.loc[1, ['open', 'low']] = [100, 99]
    elif state == 'unavailable':
        frame = frame[frame['date'] != date(2026, 1, 6)]
    result = compute_daily_path_v1(event, frame, observation_ts=_DP_CLOCK,
                                   price_evidence=evidence)
    return result['payload']


def _daily_summary():
    """The earnings_ticker_lean daily_path_summary_v1 shape (gcp/schema.sql),
    with each metric's explicit denominators and one unavailable event."""
    def metric(step):
        return {'eligible_n': 1, 'observed_n': 1, 'right_censored_n': 0,
                'not_applicable_n': 1, 'unavailable_n': 1,
                'observed_rate_pct': 100.0, 'median_first_observed_step': step}
    return {
        'version': 'earnings-daily-path-summary-v1',
        'mode': 'retrospective_current_vintage',
        'scope': 'latest_12_prior_distinct_mature_admitted_events_daily_closing_steps_only',
        'candidate_audit': {'candidate_n': 4, 'admitted_n': 3, 'excluded_n': 1,
                            'excluded_reason_counts': {'immature': 1},
                            'selected_n': 3, 'not_selected_older_n': 0},
        'point_in_time_verified': False,
        'step_unit': 'trading_session_close_index_zero_is_reaction_session_close',
        'event_n': 3, 'qualified_native_n': 1,
        'native_events': [], 'native_candidate_audit': {'candidate_n': 3},
        'historical_direction_consistency_pct': 0,
        'historical_upward_opening_gap_pct': None,
        'first_opposite_close': metric(2),
        'closing_gap_fill': metric(4),
        'events': [
            {'event_id': 'SYNTH:2025-11-30:2026-01-05', 'reported_date': '2026-01-05',
             'fiscal_date_ending': '2025-11-30', 'status': 'complete', 'reason': None},
            {'event_id': 'SYNTH:2025-08-31:2025-10-06', 'reported_date': '2025-10-06',
             'fiscal_date_ending': '2025-08-31', 'status': 'not_applicable', 'reason': None},
            {'event_id': 'SYNTH:2025-05-31:2025-07-07', 'reported_date': '2025-07-07',
             'fiscal_date_ending': '2025-05-31', 'status': 'unavailable',
             'reason': 'missing_admitted_daily_path'},
        ],
    }


class TestDailyPathDescriptors:
    @pytest.mark.parametrize('state', ['complete', 'not_applicable', 'unavailable'])
    def test_event_serializes_actual_producer_payload_unchanged(self, client, state):
        payload = _daily_path(state)
        if state == 'complete':
            assert payload['status'] == 'complete'
            assert payload['first_opposite_close_step'] == 2
        elif state == 'not_applicable':
            assert payload['status'] == 'not_applicable' and payload['gap_sign'] == 0
        else:
            assert payload['first_opposite_close_step'] is None
            assert payload['censored'] is None
        fake_df = pd.DataFrame([
            {'ticker': 'SYNTH', 'reported_date': date(2026, 1, 5),
             'sustain_5d_pct': 1.25, 'reaction_anchor_price': None,
             'daily_path_v1': payload},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/event/SYNTH/2026-01-05')
        assert resp.status_code == 200
        body = resp.json()
        assert body['daily_path_v1'] == payload
        # Native field beside the additive one is untouched; an explicit
        # NULL stays null and is not dropped.
        assert body['sustain_5d_pct'] == 1.25
        assert 'reaction_anchor_price' in body and body['reaction_anchor_price'] is None

    def test_history_keeps_old_null_rows_beside_new_payloads(self, client):
        payload = _daily_path('complete')
        fake_df = pd.DataFrame([
            {'ticker': 'SYNTH', 'reported_date': date(2026, 1, 5), 'daily_path_v1': payload},
            {'ticker': 'SYNTH', 'reported_date': date(2025, 10, 6), 'daily_path_v1': None},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/history/SYNTH')
        assert resp.status_code == 200
        rows = resp.json()['rows']
        assert rows[0]['daily_path_v1'] == payload
        assert 'daily_path_v1' in rows[1] and rows[1]['daily_path_v1'] is None

    def test_ticker_lean_serializes_summary_and_denominators_unchanged(self, client):
        summary = _daily_summary()
        fake_df = pd.DataFrame([
            {'ticker': 'SYNTH', 'long_winner_count': 1, 'lean_score': 0.0,
             'daily_path_summary_v1': summary},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/ticker/SYNTH/lean')
        assert resp.status_code == 200
        body = resp.json()
        assert body['daily_path_summary_v1'] == summary
        for name in ('first_opposite_close', 'closing_gap_fill'):
            got = body['daily_path_summary_v1'][name]
            assert (got['observed_n'], got['not_applicable_n'], got['unavailable_n']) == (1, 1, 1)
        assert body['daily_path_summary_v1']['historical_upward_opening_gap_pct'] is None

    def test_ticker_lean_without_summary_is_explicit_null(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'OLD', 'long_winner_count': 2, 'lean_score': 0.1,
             'daily_path_summary_v1': None},
        ])
        with patch('gcp.database.query_to_dataframe_strict', return_value=fake_df):
            resp = client.get('/api/earnings/ticker/OLD/lean')
        assert resp.status_code == 200
        body = resp.json()
        assert 'daily_path_summary_v1' in body and body['daily_path_summary_v1'] is None
