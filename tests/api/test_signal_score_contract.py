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


@pytest.mark.parametrize('invalid', [False,True])
def test_known_parquet_metadata_uses_actual_profile_without_leaking_extras(client,monkeypatch,native,invalid):
    monkeypatch.setattr(signals,'_CLOUD_SQL',False)
    explanation=json.loads(json.dumps(native.score_explanation))
    if invalid:
        explanation['base_max']=5
    row={'entry_time':'2024-01-02T14:39Z','trade_type':'call','signal_strength':6,
         'conditions_met':native.conditions_met,'strategy':'momentum',
         'extra':{'score_explanation':explanation,'unrelated_private':'must-not-expose'}}
    monkeypatch.setattr(signals,'_load_ticker_df_parquet',lambda t:('synthetic.parquet',pd.DataFrame([row])))
    r=client.get('/api/signals/IWM')
    assert r.status_code==200
    record=r.json()['signals'][0]
    assert record['score']==6 and record['strategy']=='momentum'
    assert 'unrelated_private' not in r.text and 'extra' not in record
    assert record['score_explanation']['status']==('invalid_record' if invalid else 'recorded')
    assert record['score_explanation']['base_max']==(None if invalid else 7)


def test_typed_score_contract_is_in_actual_openapi(client):
    from api.schemas import HistoricalScoreExplanation
    from pydantic import ValidationError
    schema=client.get('/openapi.json').json()['components']['schemas']
    assert 'HistoricalScoreExplanation' in schema
    assert 'score_explanation' in schema['SignalRow']['properties']
    assert 'strategy' in schema['SignalRow']['properties']
    assert schema['HistoricalScoreExplanation']['properties']['version']['const']=='historical-score-v1'
    assert set(schema['HistoricalScoreExplanation']['properties']['status']['enum'])=={'recorded','legacy_unavailable','invalid_record'}
    with pytest.raises(ValidationError):
        HistoricalScoreExplanation.model_validate({'version':'invented','status':'recorded'})


def test_maximum_limit_typed_http_capacity(client,monkeypatch,native):
    """Real typed serialization at the existing hard limit; synthetic rows only."""
    import os
    import resource
    import time
    monkeypatch.setattr(signals,'_CLOUD_SQL',True)
    calls=[]
    def query(sql,params):
        calls.append((sql,params))
        if 'COUNT(*)' in sql:
            return pd.DataFrame({'n':[50000]})
        return pd.DataFrame([{'time':'2024-01-02T14:39Z','direction':'CALL',
            'score':6,'conditions_met':native.conditions_met,'strategy':'momentum',
            'run_kind':'backfill','score_explanation':native.score_explanation}]*50000)
    monkeypatch.setattr(signals,'_query_or_503',query)
    started=time.perf_counter()
    response=client.get('/api/signals/IWM?limit=50000')
    assert response.status_code==200
    payload=response.json()
    elapsed=time.perf_counter()-started
    peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    assert 'content-length' not in response.headers
    assert payload['returned']==50000 and len(payload['signals'])==50000
    assert len(calls)==2 and calls[1][1]['limit']==50000
    assert len(json.dumps(payload['signals'][0]['score_explanation'],separators=(',',':')).encode())<=2048
    assert payload['signals'][-1]['score_explanation']['base_max']==7
    assert elapsed<300 and peak_bytes<2*1024**3
    # Paired body-size control: the original MAIN SQL projection omits these
    # three additive fields. This is the same synthetic rows, not a production
    # load run or a claim that legacy source metadata can be reconstructed.
    baseline={**payload,'signals':[{k:v for k,v in row.items() if k not in
        {'strategy','inserted_at','score_explanation'}} for row in payload['signals']]}
    baseline_bytes=len(json.dumps(baseline,separators=(',',':'),ensure_ascii=False).encode())
    # Optional owner-selected evidence output, never a network/upload operation.
    if os.environ.get('SCORE_CAPACITY_RECEIPT'):
        Path(os.environ['SCORE_CAPACITY_RECEIPT']).write_text(json.dumps({
            'cases':50000,'rows_returned':payload['returned'],'response_bytes':len(response.content),
            'elapsed_seconds':elapsed,'process_peak_rss_bytes':peak_bytes,'sql_calls':len(calls),
            'baseline_same_rows_original_projection_bytes':baseline_bytes,
            'baseline_definition':'same synthetic rows, original MAIN37778997 SQL response fields only; not a deployed baseline load test',
            'nonstreamed_http1_limit_bytes':32*1024**2,
            'pre_repair_new_wire_eligible':False,
            'current_content_length_header':response.headers.get('content-length'),
            'transport':'typed prevalidated StreamingResponse, <=65536-byte ASGI chunks; configured Uvicorn HTTP1',
            'live_cloud_run_transport_verified':False,
            'source':'first-party synthetic native producer records; real router/Pydantic/HTTP serialization',
            'limits':{'rows':50000,'explanation_bytes':2048,'service_seconds':300,'service_bytes':2*1024**3},
            'no_live_sql_or_provider':True},indent=2)+'\n')


@pytest.mark.parametrize('optional_present',[False,True])
def test_parquet_optional_projection_one_download_no_full_frame(monkeypatch,optional_present):
    import io
    import pyarrow.parquet as pq
    from api import gcs_reader
    frame=pd.DataFrame({'entry_time':['2024-01-02'],'signal_strength':[6],'irrelevant':['not-decoded']})
    if optional_present:
        frame['strategy']='momentum'
    content=io.BytesIO();frame.to_parquet(content,index=False)
    downloads=[];reads=[]
    monkeypatch.setattr(gcs_reader,'_download_bytes',lambda name:(downloads.append(name) or content.getvalue()))
    original=pq.ParquetFile.read
    def read(self,*a,**kwargs):
        reads.append(kwargs.get('columns'))
        return original(self,*a,**kwargs)
    monkeypatch.setattr(pq.ParquetFile,'read',read)
    result=gcs_reader.download_parquet('synthetic.parquet',columns=['entry_time','signal_strength'],
        optional_columns=['strategy','run_kind','score_explanation'])
    assert downloads==['synthetic.parquet']
    expected=['entry_time','signal_strength']+(['strategy'] if optional_present else [])
    assert list(result.columns)==expected and reads==[expected]
    assert 'irrelevant' not in result


def test_parquet_ordinary_callers_unchanged_and_malformed_refuses(monkeypatch):
    import io
    from api import gcs_reader
    frame=pd.DataFrame({'required':[1],'other':[2]})
    data=io.BytesIO();frame.to_parquet(data,index=False)
    downloads=[]
    monkeypatch.setattr(gcs_reader,'_download_bytes',lambda name:(downloads.append(name) or data.getvalue()))
    pd.testing.assert_frame_equal(gcs_reader.download_parquet('ordinary',columns=['required']),frame[['required']])
    pd.testing.assert_frame_equal(gcs_reader.download_parquet('ordinary'),frame)
    monkeypatch.setattr(gcs_reader,'_download_bytes',lambda name:(downloads.append(name) or b'not parquet'))
    import pyarrow.lib
    with pytest.raises(pyarrow.lib.ArrowInvalid):
        gcs_reader.download_parquet('bad',columns=['required'],optional_columns=['strategy'])
    assert downloads==['ordinary','ordinary','bad']


@pytest.mark.parametrize('nullable_inserted_at',[False,True])
def test_actual_native_parquet_roundtrip_is_described(client,monkeypatch,native,nullable_inserted_at):
    import io
    from api import gcs_reader
    monkeypatch.setattr(signals,'_CLOUD_SQL',False)
    signals._DF_CACHE.clear()
    frame=pd.DataFrame([{
        'entry_time':'2024-01-02T14:39Z','trade_type':'call','entry_price':100.,
        'entry_rsi':35.,'entry_ema9':99.,'entry_ema20':100.,'entry_volume':1000.,
        'signal_strength':6,'conditions_met':native.conditions_met,'return_pct':None,
        'strategy':'momentum','score_explanation':native.score_explanation,
        'irrelevant':['do-not-read']}])
    if nullable_inserted_at:
        frame['inserted_at']=pd.Series([pd.NaT],dtype='datetime64[ns, UTC]')
    content=io.BytesIO();frame.to_parquet(content,index=False)
    downloads=[]
    monkeypatch.setattr(gcs_reader,'list_matching_blobs',lambda *a:['raw/data/signals/historical_iwm_20240102_20240102_signals.parquet'])
    monkeypatch.setattr(gcs_reader,'_download_bytes',lambda name:(downloads.append(name) or content.getvalue()))
    r=client.get('/api/signals/IWM')
    assert r.status_code==200
    row=r.json()['signals'][0]
    assert row['score_explanation']['status']=='recorded'
    assert row['score_explanation']['base_max']==7
    if nullable_inserted_at:
        assert row['inserted_at'] is None
        assert row['score_explanation']['provenance']['inserted_at'] is None
    assert len(downloads)==1
    assert 'irrelevant' not in r.text
    signals._DF_CACHE.clear()


def test_signal_list_uses_typed_stream_without_content_length(client,monkeypatch,native):
    """Cloud Run HTTP/1 non-streamed bodies have a32MiB limit."""
    monkeypatch.setattr(signals,'_CLOUD_SQL',True)
    def query(sql,params):
        if 'COUNT(*)' in sql:
            return pd.DataFrame({'n':[1]})
        return pd.DataFrame([{'time':'2024-01-02T14:39Z','direction':'CALL','score':6,
            'strategy':'momentum','score_explanation':native.score_explanation}])
    monkeypatch.setattr(signals,'_query_or_503',query)
    r=client.get('/api/signals/IWM?limit=1')
    assert r.status_code==200
    assert 'content-length' not in r.headers
    assert r.headers['content-type']=='application/json'
    assert r.json()['signals'][0]['score_explanation']['base_max']==7


def test_typed_stream_body_parity_chunks_and_preheader_validation(native):
    import anyio
    from pydantic import ValidationError
    from api.schemas import SignalsResponse
    payload={'ticker':'IWM','count':1000,'returned':1000,'source':'cloud_sql',
        'signals':[{'ticker':'IWM','score':6,'conditions_met':'6/7','strategy':'momentum',
                    'score_explanation':native.score_explanation}]*1000}
    baseline=FastAPI()
    @baseline.get('/control',response_model=SignalsResponse,response_model_exclude_unset=True)
    def control():
        return payload
    ordinary=TestClient(baseline).get('/control')
    response=signals._typed_signals_response(payload)
    messages=[]
    async def receive():
        return {'type':'http.request','body':b'','more_body':False}
    async def send(message):
        messages.append(message)
    async def run():
        await response({'type':'http','asgi':{'spec_version':'2.4'},'method':'GET','path':'/api/signals/IWM','headers':[]},receive,send)
    anyio.run(run)
    assert messages[0]['type']=='http.response.start' and messages[0]['status']==200
    assert b'content-length' not in dict(messages[0]['headers'])
    bodies=[m for m in messages if m['type']=='http.response.body']
    assert len(bodies)>2
    assert all(m['more_body'] for m in bodies[:-1])
    assert bodies[-1]['more_body'] is False
    assert all(len(m.get('body',b''))<=65536 for m in bodies)
    assert b''.join(m.get('body',b'') for m in bodies)==ordinary.content
    invalid={**payload,'signals':[payload['signals'][0],{'ticker':'IWM','score':'invalid'}]}
    with pytest.raises(ValidationError):
        signals._typed_signals_response(invalid)  # no response object or headers exist


@pytest.mark.parametrize('bad',[None,False,{},0,''])
def test_malformed_reason_list_keeps_raw_score_and_other_rows(client,monkeypatch,native,bad):
    monkeypatch.setattr(signals,'_CLOUD_SQL',True)
    broken=json.loads(json.dumps(native.score_explanation))
    broken['unavailable_reasons']=bad
    def query(sql,params):
        if 'COUNT(*)' in sql:
            return pd.DataFrame({'n':[2]})
        return pd.DataFrame([{'time':'2024-01-02T14:39Z','direction':'CALL','score':6,
            'strategy':'momentum','score_explanation':e} for e in (native.score_explanation,broken)])
    monkeypatch.setattr(signals,'_query_or_503',query)
    r=client.get('/api/signals/IWM')
    assert r.status_code==200 and r.json()['returned']==2
    rows=r.json()['signals']
    assert rows[0]['score_explanation']['status']=='recorded'
    assert rows[1]['score']==6 and rows[1]['score_explanation']['status']=='invalid_record'


def test_concurrent_signal_requests_refuse_before_materialization(client, monkeypatch, native):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    entered, release = Event(), Event()
    monkeypatch.setattr(signals, '_SIGNAL_QUEUE_DEADLINE_SECONDS', 0.02)
    calls = []
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    def query(*args):
        calls.append(args)
        entered.set()
        assert release.wait(10)
        rows = [{"ticker": "IWM", "score": 6, "strategy": "momentum",
                 "score_explanation": native.score_explanation} for _ in range(50000)]
        return 50000, rows
    monkeypatch.setattr(signals, '_query_signals_sql', query)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.get, '/api/signals/IWM?limit=50000')
        assert entered.wait(10)
        try:
            second = client.get('/api/signals/SPY?limit=50000')
            assert second.status_code == 503
            assert second.headers['retry-after'] == '5'
            assert len(calls) == 1
        finally:
            release.set()
        completed = first.result(timeout=30)
        assert completed.status_code == 200
        assert completed.json()["returned"] == 50000
    assert client.get('/api/signals/IWM?limit=50000').status_code == 200


def test_signal_admission_releases_after_query_error(client, monkeypatch):
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    def fail(*args):
        raise RuntimeError('deliberate query defect')
    monkeypatch.setattr(signals, '_query_signals_sql', fail)
    with pytest.raises(RuntimeError, match='deliberate query defect'):
        client.get('/api/signals/IWM')
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *args: (0, []))
    assert client.get('/api/signals/IWM').status_code == 200


@pytest.mark.parametrize('interrupt', [False, True])
def test_signal_slot_held_until_stream_finishes_or_disconnects(monkeypatch, interrupt):
    import anyio
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *args: (0, []))
    monkeypatch.setattr(signals, '_SIGNAL_QUEUE_DEADLINE_SECONDS', 0.001)
    async def response():
        return await signals.get_signals('IWM', 50000, '', 0, None, None)
    first = anyio.run(response)
    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}
    async def send(message):
        with pytest.raises(signals.HTTPException) as refusal:
            await response()
        assert refusal.value.status_code == 503
        if interrupt and message['type'] == 'http.response.body':
            raise OSError('client disconnected')
    async def run(item, sender):
        await item({'type': 'http', 'asgi': {'spec_version': '2.4'}, 'method': 'GET',
                    'path': '/api/signals/IWM', 'headers': []}, receive, sender)
    try:
        anyio.run(run, first, send)
    except Exception as exc:
        from starlette.requests import ClientDisconnect
        assert interrupt and isinstance(exc, ClientDisconnect)
    next_response = anyio.run(response)
    async def discard(message):
        pass
    anyio.run(run, next_response, discard)


def test_signal_admission_releases_after_typed_validation_failure(client, monkeypatch):
    from pydantic import ValidationError
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *args: (1, [{'score': 'bad'}]))
    with pytest.raises(ValidationError):
        client.get('/api/signals/IWM')
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *args: (0, []))
    assert client.get('/api/signals/IWM').status_code == 200


@pytest.mark.parametrize('slow_mode', ['headers', 'stalled_body', 'trickle'])
def test_signal_slow_consumer_deadline_releases_memory_and_admission(monkeypatch, slow_mode):
    """A client cannot renew exclusive admission by slowly accepting chunks."""
    import anyio
    monkeypatch.setattr(signals, '_SIGNAL_STREAM_DEADLINE_SECONDS', 0.08, raising=False)
    monkeypatch.setattr(signals, '_SIGNAL_QUEUE_DEADLINE_SECONDS', 0.001)
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    # Enough JSON chunks for trickle delivery to exceed the total deadline.
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *a: (3000, [
        {'ticker': 'IWM', 'score': 6, 'conditions_met': 'x' * 200}
        for _ in range(3000)]))
    response = anyio.run(signals.get_signals, 'IWM', 50000, '', 0, None, None)
    sent = []
    async def receive():
        await anyio.sleep_forever()
    async def send(message):
        sent.append(message)
        with pytest.raises(signals.HTTPException) as refused:
            await signals.get_signals('SPY', 50000, '', 0, None, None)
        assert refused.value.status_code == 503
        if slow_mode == 'headers' or message['type'] == 'http.response.body':
            await anyio.sleep(0.015 if slow_mode == 'trickle' else 1)
    async def exercise():
        # Outer watchdog distinguishes an enforced transport deadline from a hang.
        with anyio.fail_after(0.5):
            with pytest.raises(TimeoutError):
                await response({'type': 'http', 'asgi': {'spec_version': '2.4'},
                                'method': 'GET', 'headers': []}, receive, send)
            # Closed iterator cannot retain/continue delivering the large body.
            assert [chunk async for chunk in response.body_iterator] == []
    anyio.run(exercise)
    assert not any(m['type'] == 'http.response.body' and not m.get('more_body', False)
                   for m in sent), 'timeout must not falsely finish partial JSON'
    assert response.owns_slot is False
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *a: (0, []))
    next_response = anyio.run(signals.get_signals, 'SPY', 50000, '', 0, None, None)
    async def discard(message):
        pass
    async def finish():
        await next_response({'type': 'http', 'asgi': {'spec_version': '2.4'},
                             'method': 'GET', 'headers': []}, receive, discard)
    anyio.run(finish)


def test_signal_cancelled_transport_closes_body_before_readmission(monkeypatch):
    import anyio
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *a: (0, []))
    response = anyio.run(signals.get_signals, 'IWM', 50000, '', 0, None, None)
    async def receive():
        await anyio.sleep_forever()
    async def exercise():
        with anyio.CancelScope() as scope:
            async def send(message):
                if message['type'] == 'http.response.body':
                    scope.cancel()
                    await anyio.sleep_forever()
            await response({'type': 'http', 'asgi': {'spec_version': '2.4'},
                            'method': 'GET', 'headers': []}, receive, send)
        assert [chunk async for chunk in response.body_iterator] == []
        assert response.owns_slot is False
        next_response = await signals.get_signals('SPY', 50000, '', 0, None, None)
        async def discard(message):
            pass
        await next_response({'type': 'http', 'asgi': {'spec_version': '2.4'},
                             'method': 'GET', 'headers': []}, receive, discard)
    anyio.run(exercise)


@pytest.mark.parametrize('ending', ['complete', 'timeout', 'disconnect'])
def test_three_immediate_recaptures_cannot_overtake_waiting_competitor(monkeypatch, ending):
    """Permanent SEC regression: repeat caller A must yield to already waiting B."""
    import anyio
    import inspect
    from api import auth
    from starlette.requests import Request
    from starlette.requests import ClientDisconnect
    monkeypatch.setattr(auth, 'AUTH_MODE', 'firebase')
    monkeypatch.setattr(signals, '_SIGNAL_STREAM_DEADLINE_SECONDS', .03)
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    monkeypatch.setattr(signals, '_query_signals_sql', lambda *a: (0, []))
    order = []
    async def acquire(who='a'):
        request = Request({'type': 'http', 'state': {'user_email': who + '@example.test'}})
        value = signals.get_signals('IWM', 50000, '', 0, None, None, request=request)
        return await value if inspect.isawaitable(value) else value
    async def finish(item, held=False):
        async def receive():
            await anyio.sleep_forever()
        async def send(message):
            if held and message['type'] == 'http.response.body':
                if ending == 'timeout':
                    await anyio.sleep_forever()
                if ending == 'disconnect':
                    raise OSError('disconnected client')
        await item({'type': 'http', 'asgi': {'spec_version': '2.4'},
                    'method': 'GET', 'headers': []}, receive, send)
    async def run():
        for round_number in range(3):
            held = await acquire()
            started = anyio.Event()
            async def competitor():
                started.set()
                try:
                    item = await acquire('b')
                except signals.HTTPException:
                    order.append(('refused', round_number))
                    return
                order.append(('competitor', round_number))
                await finish(item)
            async with anyio.create_task_group() as group:
                group.start_soon(competitor)
                await started.wait()
                await anyio.sleep(0)
                if ending == 'complete':
                    await finish(held, True)
                else:
                    with pytest.raises(TimeoutError if ending == 'timeout' else ClientDisconnect):
                        await finish(held, True)
                immediate_retry = await acquire()
                order.append(('repeat', round_number))
                await finish(immediate_retry)
        assert order == [(who, i) for i in range(3) for who in ('competitor', 'repeat')]
    anyio.run(run)


def test_firebase_repeated_principal_cannot_fill_queue_or_spoof_identity(monkeypatch):
    import anyio
    import httpx
    from threading import Event
    from api import auth
    monkeypatch.setattr(auth, 'AUTH_MODE', 'firebase')
    # Exercise the real authentication middleware; stub only external token verification.
    monkeypatch.setattr(auth, '_verify_bearer_email', lambda request:
        {'Bearer A': 'a@example.test', 'Bearer B': 'b@example.test',
         'Bearer C': 'c@example.test'}[request.headers['authorization']])
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    entered, release = Event(), Event()
    calls = []
    def query(ticker, *args):
        calls.append(ticker)
        if ticker == 'IWM':
            entered.set()
            assert release.wait(5)
        return 0, []
    monkeypatch.setattr(signals, '_query_signals_sql', query)
    app = FastAPI()
    app.middleware('http')(auth.auth_middleware)
    app.include_router(signals.router)
    async def exercise():
        results = {}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            async def get(who, ticker):
                results[who] = await client.get('/api/signals/' + ticker, headers={'authorization': 'Bearer ' + who})
            async with anyio.create_task_group() as group:
                group.start_soon(get, 'A', 'IWM')
                with anyio.fail_after(2):
                    while not entered.is_set():
                        await anyio.sleep(.001)
                try:
                    for i in range(10):
                        rejected = await client.get('/api/signals/IWM', headers={
                            'authorization': 'Bearer A', 'x-goog-authenticated-user-email': f'attacker:{i}@fake.test',
                            'x-user-email': f'{i}@fake.test'})
                        assert rejected.status_code == 503
                        assert rejected.headers['retry-after'] == '5'
                    assert calls == ['IWM'] and len(signals._SIGNAL_ADMISSION.waiters) == 0
                    group.start_soon(get, 'B', 'SPY')
                    with anyio.fail_after(2):
                        while len(signals._SIGNAL_ADMISSION.waiters) != 1:
                            await anyio.sleep(.001)
                    group.start_soon(get, 'C', 'QQQ')
                    with anyio.fail_after(2):
                        while len(signals._SIGNAL_ADMISSION.waiters) != 2:
                            await anyio.sleep(.001)
                finally:
                    release.set()
            assert calls == ['IWM', 'SPY', 'QQQ']
            assert all(r.status_code == 200 for r in results.values())
            assert not signals._SIGNAL_ADMISSION.principals
            assert (await client.get('/api/signals/SPY', headers={'authorization': 'Bearer A'})).status_code == 200
    anyio.run(exercise)


def test_firebase_missing_verified_state_refuses_before_allocation(client, monkeypatch):
    from api import auth
    monkeypatch.setattr(auth, 'AUTH_MODE', 'firebase')
    def forbidden(*args):
        raise AssertionError('must not allocate before verified identity')
    monkeypatch.setattr(signals, '_query_signals_sql', forbidden)
    # No authentication middleware on this fixture: raw headers cannot substitute.
    r = client.get('/api/signals/IWM', headers={'authorization': 'Bearer invented',
        'x-goog-authenticated-user-email': 'accounts.google.com:claimed@example.test'})
    assert r.status_code == 401


def test_fifo_capacity_cancel_timeout_and_grant_boundary_cleanup(monkeypatch):
    import anyio
    from starlette.requests import Request
    from api import auth
    monkeypatch.setattr(auth, 'AUTH_MODE', 'firebase')
    admission = signals._SignalAdmission()
    monkeypatch.setattr(signals, '_SIGNAL_ADMISSION', admission)
    async def exercise():
        await admission.acquire('holder')
        cancelled = anyio.Event()
        async def waiter(i):
            try:
                await admission.acquire('user' + str(i))
            finally:
                cancelled.set()
        async with anyio.create_task_group() as group:
            for i in range(signals._SIGNAL_MAX_WAITERS):
                group.start_soon(waiter, i)
            with anyio.fail_after(2):
                while len(admission.waiters) != signals._SIGNAL_MAX_WAITERS:
                    await anyio.sleep(.001)
            with pytest.raises(signals.HTTPException) as full:
                await admission.acquire('overflow')
            assert full.value.status_code == 503 and 'full' in full.value.detail
            group.cancel_scope.cancel()
        assert not admission.waiters and admission.principals == {'holder'}
        monkeypatch.setattr(signals, '_SIGNAL_QUEUE_DEADLINE_SECONDS', .01)
        with pytest.raises(signals.HTTPException) as expired:
            await admission.acquire('timeout')
        assert 'expired' in expired.value.detail
        assert admission.principals == {'holder'} and not admission.waiters
        admission.release()
        # Cancellation immediately after grant, before the worker starts, must release it.
        with anyio.CancelScope() as cancel_scope:
            async def cancelled_worker(*args, **kwargs):
                cancel_scope.cancel()
                await anyio.sleep_forever()
            monkeypatch.setattr(signals, 'run_in_threadpool', cancelled_worker)
            request = Request({'type': 'http', 'state': {'user_email': 'boundary@example.test'}})
            await signals.get_signals('IWM', 50000, '', 0, None, None, request=request)
        assert not admission.active and not admission.principals and not admission.waiters
    anyio.run(exercise)


@pytest.mark.parametrize('failure', ['query', 'serialization'])
def test_verified_principal_released_after_materialization_error(monkeypatch, failure):
    from api import auth
    monkeypatch.setattr(auth, 'AUTH_MODE', 'firebase')
    monkeypatch.setattr(auth, '_verify_bearer_email', lambda request: 'canonical@example.test')
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    def query(*args):
        if failure == 'query':
            raise RuntimeError('query failure')
        return 1, [{'score': 'bad'}]
    monkeypatch.setattr(signals, '_query_signals_sql', query)
    app = FastAPI()
    app.middleware('http')(auth.auth_middleware)
    app.include_router(signals.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get('/api/signals/IWM').status_code == 500
        assert not signals._SIGNAL_ADMISSION.active
        assert not signals._SIGNAL_ADMISSION.principals
        monkeypatch.setattr(signals, '_query_signals_sql', lambda *args: (0, []))
        assert client.get('/api/signals/IWM').status_code == 200


def test_cancel_during_materialization_keeps_slot_then_closes_unconsumed_body(monkeypatch):
    import anyio
    from threading import Event
    from starlette.requests import Request
    from api import auth
    monkeypatch.setattr(auth, 'AUTH_MODE', 'firebase')
    monkeypatch.setattr(signals, '_CLOUD_SQL', True)
    entered, release = Event(), Event()
    def query(*args):
        entered.set()
        assert release.wait(5)
        return 0, []
    monkeypatch.setattr(signals, '_query_signals_sql', query)
    created = []
    original = signals._typed_signals_response
    def record(payload):
        response = original(payload)
        created.append(response)
        return response
    monkeypatch.setattr(signals, '_typed_signals_response', record)
    async def exercise():
        request = Request({'type': 'http', 'state': {'user_email': 'a@example.test'}})
        async with anyio.create_task_group() as group:
            async def invoke():
                await signals.get_signals('IWM', 50000, '', 0, None, None, request=request)
                pytest.fail('cancelled materialization must not transfer response ownership')
            group.start_soon(invoke)
            with anyio.fail_after(2):
                while not entered.is_set():
                    await anyio.sleep(.001)
            group.cancel_scope.cancel()
            assert signals._SIGNAL_ADMISSION.active
            assert signals._SIGNAL_ADMISSION.principals == {'a@example.test'}
            release.set()
        assert not signals._SIGNAL_ADMISSION.active and not signals._SIGNAL_ADMISSION.principals
        assert len(created) == 1
        assert [chunk async for chunk in created[0].body_iterator] == []
    anyio.run(exercise)
