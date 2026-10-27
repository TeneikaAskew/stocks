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
