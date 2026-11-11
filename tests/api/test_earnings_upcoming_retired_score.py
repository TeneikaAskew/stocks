"""/api/earnings/upcoming serves the refreshed rows with the five retired
EarningsWhispers-derived fields as null and archetype present.

The rows are the ones ``refresh_daily`` actually upserts for the
bullish_trend over-priced fixture of
tests/gcp/test_refresh_earnings_views_retired_score.py; only the SQL read
is faked. No response model change: ``_df_to_records`` already maps
None/NaN to null.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.gcp.test_refresh_earnings_views_retired_score import (
    RETIRED_FIELDS, run_refresh,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'platform'))


def test_upcoming_returns_retired_fields_null_with_archetype(monkeypatch):
    refreshed = run_refresh(monkeypatch)
    monkeypatch.setenv('CLOUD_SQL_CONNECTION_NAME', 'test')
    monkeypatch.setenv('DB_USER', 'test')
    from api.routers import earnings as earnings_mod
    importlib.reload(earnings_mod)
    app = FastAPI()
    app.include_router(earnings_mod.router)
    with patch('gcp.database.query_to_dataframe_strict', return_value=refreshed):
        resp = TestClient(app).get('/api/earnings/upcoming?days=14')
    assert resp.status_code == 200
    data = resp.json()
    assert data['count'] == len(refreshed) == 3
    rows = {r['ticker']: r for r in data['rows']}
    for r in rows.values():
        for f in RETIRED_FIELDS:
            assert f in r and r[f] is None, (r['ticker'], f)
    assert rows['BULL']['archetype'] == 'bullish_trend'
    assert rows['BEAR']['archetype'] == 'bearish_trend'
    assert rows['BULL']['implied_move_pct'] == 20.0
