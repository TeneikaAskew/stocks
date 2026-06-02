"""Hermetic tests for platform/api/routers/earnings.py.

Mocks gcp.database.query_to_dataframe so tests run offline. Verifies:
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
        with patch('gcp.database.query_to_dataframe', return_value=fake_df):
            resp = client.get('/api/earnings/upcoming?days=14')
        assert resp.status_code == 200
        data = resp.json()
        assert data['count'] == 1
        assert data['rows'][0]['ticker'] == 'MSFT'
        # Cache header set to 5 min
        assert resp.headers.get('cache-control') == 'public, max-age=300'

    def test_empty_returns_zero_count(self, client):
        with patch('gcp.database.query_to_dataframe',
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
        with patch('gcp.database.query_to_dataframe', return_value=fake_df):
            resp = client.get('/api/earnings/history/NVAX?limit=10')
        assert resp.status_code == 200
        data = resp.json()
        assert data['ticker'] == 'NVAX'
        assert data['count'] == 1
        assert data['rows'][0]['beat_meet_miss'] == 'beat'
        # Cache header set to 1 hour
        assert resp.headers.get('cache-control') == 'public, max-age=3600'

    def test_404_when_no_events(self, client):
        with patch('gcp.database.query_to_dataframe',
                   return_value=pd.DataFrame()):
            resp = client.get('/api/earnings/history/UNKNOWNTICKER')
        assert resp.status_code == 404

    def test_uppercases_ticker(self, client):
        captured = {}
        def _capture(sql, params=None):
            captured['params'] = params
            return pd.DataFrame([{'ticker': 'MSFT'}])
        with patch('gcp.database.query_to_dataframe', side_effect=_capture):
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
        with patch('gcp.database.query_to_dataframe', return_value=fake_df):
            resp = client.get('/api/earnings/event/MSFT/2025-07-30')
        assert resp.status_code == 200
        data = resp.json()
        # Returns a dict, NOT a {rows, count} envelope — single event
        assert data['ticker'] == 'MSFT'
        assert data['beat_meet_miss'] == 'beat'
        # Cache header set to 1 day
        assert resp.headers.get('cache-control') == 'public, max-age=86400'

    def test_404_when_missing(self, client):
        with patch('gcp.database.query_to_dataframe',
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
        with patch('gcp.database.query_to_dataframe', side_effect=_capture):
            resp = client.get('/api/earnings/lean?direction=long')
        assert resp.status_code == 200
        # Long direction → ORDER BY long_winner_count DESC
        assert 'long_winner_count DESC' in captured['sql']

    def test_short_direction(self, client):
        captured = {}
        def _capture(sql, params=None):
            captured['sql'] = sql
            return pd.DataFrame()
        with patch('gcp.database.query_to_dataframe', side_effect=_capture):
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
        with patch('gcp.database.query_to_dataframe', return_value=fake_df):
            resp = client.get('/api/earnings/calibration')
        assert resp.status_code == 200
        data = resp.json()
        assert data['realized_vs_implied_ratio'] == 0.636


# ─────────────────────────────────────────────────────────────────────
# /api/earnings/health/ping (keep-warm target)
# ─────────────────────────────────────────────────────────────────────

class TestHealthPing:
    def test_ping_returns_200_with_no_store(self, client):
        with patch('gcp.database.query_to_dataframe',
                   return_value=pd.DataFrame([{'ping': 1}])):
            resp = client.get('/api/earnings/health/ping')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert data['db'] == 'reachable'
        # Cache-Control no-store so intermediaries never serve stale 200
        assert resp.headers.get('cache-control') == 'no-store'

    def test_ping_handles_db_error_gracefully(self, client):
        with patch('gcp.database.query_to_dataframe',
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
        with patch('gcp.database.query_to_dataframe', return_value=fake_df):
            resp = client.get('/api/earnings/lean')
        data = resp.json()
        assert data['rows'][0]['avg_ratio'] is None
        assert data['rows'][0]['lean_score'] == 0.0  # zero != nan

    def test_dates_become_iso_strings(self, client):
        fake_df = pd.DataFrame([
            {'ticker': 'X', 'reported_date': date(2025, 5, 1),
             'beat_meet_miss': 'beat'},
        ])
        with patch('gcp.database.query_to_dataframe', return_value=fake_df):
            resp = client.get('/api/earnings/history/X')
        assert resp.json()['rows'][0]['reported_date'] == '2025-05-01'
