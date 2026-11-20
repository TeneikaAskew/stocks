"""Synthetic HTTP boundary controls; no external acquisition or persistence."""
import copy
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'platform'))
from api.routers import catalysts
from gcp import database

DAY = '2026-11-19'


def event(**values):
    return dict(date=DAY, ticker='T', catalyst_type='EARNINGS', title='Independent', **values)


@pytest.fixture
def api(monkeypatch, tmp_path):
    def forbidden(*a, **kw):
        raise AssertionError('Real network/database/job forbidden')
    import requests
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(database, 'get_engine', forbidden)
    monkeypatch.setattr(database, 'query_to_dataframe', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(catalysts, 'market_today', lambda: date.fromisoformat(DAY))
    cache = tmp_path / 'events.json'
    monkeypatch.setattr(catalysts, 'CATALYSTS_FILE', cache)
    monkeypatch.setattr(catalysts, '_db_catalyst_events', lambda *a: [])
    state = {'live': [], 'calls': 0}
    def live(*a):
        state['calls'] += 1
        return state['live']
    monkeypatch.setattr(catalysts, '_fetch_live_events', live)
    app = FastAPI()
    app.include_router(catalysts.router)
    with TestClient(app) as client:
        yield client, cache, state, monkeypatch


def read(client, endpoint, **params):
    if endpoint == 'events':
        params.update(date_from=DAY, date_to=DAY)
    response = client.get('/api/catalysts/' + endpoint, params=params)
    assert response.status_code == 200
    body = response.json()
    events = body.get('events', [e for rows in body.get('events_by_date', {}).values() for e in rows])
    assert body['total'] == len(events)
    return body, events


BAD = [
    {'source': ' earnings_whispers '}, {'source': 'EarningsWhispers'},
    {'provider': 'Earnings Whispers'},
    {'source': 'earnings_calendar (alphavantage, earnings_whispers)'},
    {'data_source': 'EarningsWhispers'},
    {'sources': ['yahoo', {'provider': {'name': 'EarningsWhispers'}}]},
    {'provenance': {'sources': [{'provenance': {'data_source': 'earnings_whispers'}}]}},
]


@pytest.mark.parametrize('endpoint', ['events', 'ticker/T'])
@pytest.mark.parametrize('provenance', BAD)
def test_retired_provenance_absent_from_http(api, endpoint, provenance):
    client, cache, state, _ = api
    good = event(source='alphavantage')
    cache.write_text(json.dumps({'events': [event(**provenance), good]}))
    before = cache.read_bytes()
    _, rows = read(client, endpoint)
    assert rows == [good]
    assert cache.read_bytes() == before
    assert state['calls'] == 0


@pytest.mark.parametrize('endpoint', ['events', 'ticker/T'])
@pytest.mark.parametrize('provenance', [
    {}, {'source': None}, {'provider': 42}, {'source': 'unknown'},
    {'source': 'Earnings_Whispers'}, {'source': 'Alpha Vantage'},
    {'source': 'unusual_whales'}, {'source': 'yahoo'}, {'source': 'Benzinga'},
    {'source': 'earnings_calendar (yahoo, unusual_whales)'},
    {'source': 'mentions earnings_whispers'}, {'source': 'earnings_calendar (earnings_whispers'},
    {'provenance': {'description': 'earnings_whispers', 'url': 'EarningsWhispers'}},
])
def test_supported_and_unknown_provenance_preserved(api, endpoint, provenance):
    client, cache, _, _ = api
    good = event(**provenance)
    good['title'] = 'EarningsWhispers discussion only'
    cache.write_text(json.dumps({'events': [good]}))
    _, rows = read(client, endpoint)
    # Existing response-model formatting can omit unknown extra fields.
    assert len(rows) == 1
    assert rows[0]['title'] == good['title']
    for key in ('source', 'date', 'ticker', 'catalyst_type'):
        if key in good:
            assert rows[0][key] == good[key]


@pytest.mark.parametrize('mode', ['fresh', 'fallback', 'peer', 'decliner', 'timeout'])
def test_acquisition_paths_qualify_provenance(api, mode):
    client, cache, state, monkeypatch = api
    good = event(source='yahoo')
    batch = [event(source='earnings_whispers'), good]
    cache.write_text(json.dumps({'events': batch, 'last_updated': 'old'}))
    before = cache.read_bytes()
    state['live'] = None if mode == 'fallback' else batch
    class Flight:
        @contextmanager
        def claim(self, key):
            yield mode not in ('decliner', 'timeout')
        def wait(self, key, timeout):
            return mode != 'timeout'
    monkeypatch.setattr(catalysts, '_CATALYST_FLIGHT', Flight())
    if mode == 'peer':
        snapshots = iter([{'events': batch, 'last_updated': 'old'}, {'events': batch, 'last_updated': 'new'}])
        monkeypatch.setattr(catalysts, '_load_cached_events', lambda: next(snapshots))
    body, rows = read(client, 'events', refresh='true')
    assert rows == [good]
    assert state['calls'] == (1 if mode in ('fresh', 'fallback') else 0)
    assert ('in flight' in body['source']) == (mode == 'timeout')
    assert cache.read_bytes() == before


def test_retired_only_ticker_cache_uses_one_qualified_fallback(api):
    client, cache, state, _ = api
    cache.write_text(json.dumps({'events': [event(source='earnings_whispers')]}))
    good = event(source='yahoo')
    state['live'] = [event(source='EarningsWhispers'), good]
    assert read(client, 'ticker/T')[1] == [good]
    assert state['calls'] == 1
    state['live'] = [event(source='EarningsWhispers')]
    assert read(client, 'ticker/T')[1] == []
    assert state['calls'] == 2


def test_deep_provenance_is_iterative_and_nonmutating():
    value = {'source': 'earnings_whispers'}
    for _ in range(2000):
        value = {'provenance': [value]}
    assert catalysts._has_retired_provenance(value)
    sample = event(provenance={'provider': {'name': 'EarningsWhispers'}})
    before = copy.deepcopy(sample)
    assert catalysts._has_retired_provenance(sample)
    assert sample == before


def test_filters_counts_and_db_contributions(api):
    client, cache, _, monkeypatch = api
    keep = event(source='yahoo')
    elsewhere = dict(keep, ticker='OTHER')
    old = dict(keep, date='2020-01-01')
    other_type = dict(keep, catalyst_type='DIVIDEND')
    retired = event(source='earnings_whispers')
    cache.write_text(json.dumps({'events': [retired, elsewhere, old, other_type, keep]}))
    monkeypatch.setattr(catalysts, '_db_catalyst_events', lambda *a: [retired])
    body, rows = read(client, 'events', tickers='T', types='EARNINGS')
    assert rows == [keep]
    assert body['events_by_date'] == {DAY: [keep]}
    assert 'DB (' not in body['source']
    # Existing ticker route keeps other event types and sorts eligible dates.
    tomorrow = dict(keep, date='2026-11-20')
    cache.write_text(json.dumps({'events': [tomorrow, retired, keep, elsewhere, old]}))
    assert read(client, 'ticker/T')[1] == [keep, tomorrow]


def test_unrecognized_payload_is_not_provenance():
    assert not catalysts._has_retired_provenance(event(
        provenance={'payload': {'source': 'earnings_whispers'}},
        details={'source': 'EarningsWhispers'},
    ))
    cyclic = {'sources': []}
    cyclic['sources'].append(cyclic)
    assert not catalysts._has_retired_provenance(cyclic)
