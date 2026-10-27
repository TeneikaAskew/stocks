"""Actual historical routes with native producer records; no external reads."""
import json
from pathlib import Path
import sys
import socket

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'platform'))
from api.routers import signals
from lib.trading_analysis import MarketAnalyzer


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('external I/O forbidden')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(signals.router)
    return TestClient(app)


@pytest.fixture
def native():
    p = Path(__file__).parents[1] / 'fixtures/historical_score_native_controls.json'
    case = json.loads(p.read_text())['cases'][0]
    frame = pd.DataFrame(case['enriched_rows'])
    frame['Time'] = pd.to_datetime(frame.Time)
    return MarketAnalyzer().generate_technical_signals(frame).iloc[-1]


def test_actual_sql_route_preserves_native_six_and_unknown_legacy(client, monkeypatch, native):
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    calls = []
    def query(sql, params):
        calls.append((sql,params))
        if 'COUNT(*)' in sql:
            return pd.DataFrame({'n':[2]})
        return pd.DataFrame([
            {'time':'2024-01-02T14:39Z','direction':'CALL','score':6,
             'conditions_met':native.conditions_met,'strategy':'momentum','run_kind':'backfill',
             'inserted_at':'2026-10-27T17:45:00+00:00','score_explanation':native.score_explanation},
            {'time':'2024-01-02T14:40Z','direction':'CALL','score':6,
             'conditions_met':'6/5','strategy':'momentum','run_kind':'backfill',
             'score_explanation':None}])
    monkeypatch.setattr(signals, '_query_or_503', query)
    response = client.get('/api/signals/IWM?limit=2&min_score=6&direction=CALL')
    assert response.status_code == 200
    rows = response.json()['signals']
    assert len(calls) == 2
    assert "extra -> 'score_explanation'" in calls[1][0]
    assert 'inserted_at' in calls[1][0] and 'strategy' in calls[1][0]
    assert calls[1][1]['min_score'] == 6
    assert rows[0]['score'] == 6 and rows[0]['score_explanation']['base_max'] == 7
    assert rows[0]['score_explanation']['provenance']['storage_source'] == 'cloud_sql'
    assert rows[1]['score'] == 6 and rows[1]['conditions_met'] == '6/5'
    assert rows[1]['score_explanation']['status'] == 'legacy_unavailable'
    assert rows[1]['score_explanation']['base_max'] is None


def test_actual_legacy_parquet_does_not_guess_strategy(client, monkeypatch):
    monkeypatch.setattr(signals, '_CLOUD_SQL', False)
    monkeypatch.setattr(signals, '_load_ticker_df_parquet', lambda t: ('legacy.parquet',pd.DataFrame([
        {'entry_time':'2024-01-02T14:40Z','trade_type':'call','signal_strength':6,'conditions_met':'6/5'}])))
    r = client.get('/api/signals/IWM')
    assert r.status_code == 200
    row = r.json()['signals'][0]
    assert row['score'] == 6
    assert row['strategy'] is None
    assert row['score_explanation']['base_max'] is None
    assert row['score_explanation']['provenance']['storage_source'] == 'gcs_parquet'


def test_actual_similar_transport_accepts_six_without_query_change(client,monkeypatch):
    monkeypatch.setattr(signals,'_CLOUD_SQL',True)
    calls=[]
    def query(sql,params):
        calls.append((sql,params))
        return pd.DataFrame({'count':[0]})
    monkeypatch.setattr(signals,'_query_or_503',query)
    r=client.get('/api/signals/IWM/similar?direction=CALL&rsi=35&score=6')
    assert r.status_code == 200
    assert len(calls)==1
    assert 'signal_strength = :score AND entry_rsi BETWEEN :rsi_lo AND :rsi_hi' in calls[0][0]
    assert calls[0][1]=={'ticker':'IWM','direction':'CALL','score':6,'rsi_lo':30,'rsi_hi':40}
    for score in ('2','6.5','nan'):
        assert client.get('/api/signals/IWM/similar?direction=CALL&rsi=35&score='+score).status_code==422
    assert len(calls)==1
