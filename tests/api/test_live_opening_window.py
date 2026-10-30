"""Hermetic current-session ORB contract; no provider/SQL calls."""
import json
from datetime import datetime, timedelta, timezone
import pytest
from lib.opening_window import compute_observed_opening_range, session_for, parse_acquisition, OpeningUnavailable

NOW = datetime(2026,10,29,14,1,tzinfo=timezone.utc)
def payload(missing=False):
    series={}
    for i in range(31):
        ts=datetime(2026,10,29,9,30)+timedelta(minutes=i)
        series[str(ts)]={'1. open':'100','2. high':str(102+i),'3. low':'99','4. close':'101','5. volume':'10'}
    if missing: series.pop('2026-10-29 09:45:00')
    return {'Meta Data':{'2. Symbol':'IWM','3. Last Refreshed':'2026-10-29 10:00:00','4. Interval':'1min','6. Time Zone':'US/Eastern'},'Time Series (1min)':series}

def test_complete_session():
    r=parse_acquisition(json.dumps(payload()).encode(),'IWM',NOW,session_for(NOW))
    assert r['opening']['high']==131 # 10:00 excluded
    assert r['opening']['low']==99
    assert r['opening']['comparison_price']==101
    assert r['opening']['comparison_as_of']=='2026-10-29T14:01:00+00:00'
    assert len(r['bars'])==31
    with pytest.raises(OpeningUnavailable,match='missing_opening_minutes'):
        parse_acquisition(json.dumps(payload(True)).encode(),'IWM',NOW,session_for(NOW))

@pytest.mark.parametrize('day,expected',[('2026-11-27T16:00:00+00:00','2026-11-27T18:00:00+00:00'),('2026-11-02T16:00:00+00:00','2026-11-02T21:00:00+00:00')])
def test_calendar_boundaries(day,expected):
    assert session_for(datetime.fromisoformat(day))['close'].isoformat()==expected

def test_holiday_and_utc_midnight():
    assert session_for(datetime(2026,12,25,16,tzinfo=timezone.utc)) is None
    assert session_for(datetime(2026,10,30,0,1,tzinfo=timezone.utc))['label']=='2026-10-29'

@pytest.mark.parametrize('change,reason', [('wrong_symbol','identity'),('empty','empty'),('error','provider'),('nan','price'),('future','future'),('offgrid','off_grid'),('stale','stale')])
def test_refusal(change,reason):
    p=payload();now=NOW
    if change=='wrong_symbol':p['Meta Data']['2. Symbol']='SPY'
    if change=='empty':p['Time Series (1min)']={}
    if change=='error':p['Note']='synthetic error'
    if change=='nan':p['Time Series (1min)']['2026-10-29 09:30:00']['2. high']='NaN'
    if change=='future':p['Meta Data']['3. Last Refreshed']='2026-10-29 11:00:00'
    if change=='offgrid':p['Time Series (1min)']['2026-10-29 09:30:30']=p['Time Series (1min)'].pop('2026-10-29 09:30:00')
    if change=='stale':now=NOW+timedelta(seconds=121)
    with pytest.raises(OpeningUnavailable,match=reason):parse_acquisition(json.dumps(p).encode(),'IWM',now,session_for(now))

def test_age_boundary():
    assert parse_acquisition(json.dumps(payload()).encode(),'IWM',NOW+timedelta(seconds=120),session_for(NOW))['opening']['status']=='available'

def test_duplicate_json():
    with pytest.raises(OpeningUnavailable,match='duplicate'):
        parse_acquisition(b'{"Meta Data":{},"Meta Data":{}}','IWM',NOW,session_for(NOW))

import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'platform'))

@pytest.fixture
def route(monkeypatch):
    from api.routers import live
    from cachetools import TTLCache
    from api.threadsafe_cache import ThreadSafeCache
    import threading
    monkeypatch.setattr(live,'AV_API_KEY','synthetic-offline-key')
    monkeypatch.setattr(live,'_OPENING_CACHE',ThreadSafeCache(TTLCache(maxsize=8,ttl=60)))
    monkeypatch.setattr(live,'_OPENING_SLOTS',threading.BoundedSemaphore(2))
    live._OPENING_ATTEMPTS.clear()
    return live

class FakeClient:
    calls=[]
    raw=None
    wait=None
    encoding="identity"
    def __init__(self,**kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    def stream(self,method,url,params):
        self.calls.append(params);p=payload();p['Meta Data']['2. Symbol']=params['symbol']
        body=self.raw if self.raw is not None else json.dumps(p).encode()
        class Response:
            headers={"content-encoding":FakeClient.encoding}
            async def __aenter__(s):return s
            async def __aexit__(s,*args):pass
            def raise_for_status(s):pass
            async def aiter_bytes(s,chunk_size):
                if FakeClient.wait is not None:await FakeClient.wait.wait()
                for i in range(0,len(body),chunk_size):yield body[i:i+chunk_size]
        return Response()
    async def get(self,url,params):
        self.calls.append(params)
        class Response:
            def raise_for_status(s):pass
            def json(s):return payload()
        return Response()

@pytest.fixture
def client(route,monkeypatch):
    FakeClient.calls=[];FakeClient.raw=None;FakeClient.wait=None;FakeClient.encoding="identity"
    monkeypatch.setattr(route.httpx,'AsyncClient',FakeClient)
    return FakeClient

def test_opt_in_contract(route,client):
    asyncio.run(route.get_live_history('IWM'))
    assert client.calls[0]['outputsize']=='compact'
    assert 'adjusted' not in client.calls[0]
    r=asyncio.run(route._get_opening_history('IWM',NOW))
    assert r['opening']['status']=='available'
    assert len(client.calls)==2
    assert client.calls[1]=={'function':'TIME_SERIES_INTRADAY','symbol':'IWM','interval':'1min','outputsize':'full','adjusted':'false','entitlement':'realtime','apikey':'synthetic-offline-key'}

def test_bounded_stream(route,client):
    client.raw=b'x'*(8*1024*1024+1)
    r=asyncio.run(route._get_opening_history('IWM',NOW))
    assert r['opening']['reason']=='body_limit'
    assert r['bars']==[]
    assert len(client.calls)==1

def test_capacity_and_cache(route,client):
    async def scenario():
        client.wait=asyncio.Event()
        one=asyncio.create_task(route._get_opening_history('IWM',NOW))
        while len(client.calls)<1:await asyncio.sleep(0)
        duplicate=await route._get_opening_history('IWM',NOW)
        assert duplicate['opening']['reason']=='acquisition_in_progress'
        two=asyncio.create_task(route._get_opening_history('SPY',NOW))
        while len(client.calls)<2:await asyncio.sleep(0)
        refused=await route._get_opening_history('QQQ',NOW)
        assert refused['opening']['reason']=='capacity_unavailable'
        client.wait.set();await asyncio.gather(one,two)
        hit=await route._get_opening_history('IWM',NOW+timedelta(seconds=30))
        assert hit['opening']['comparison_age_seconds']==30
        assert len(client.calls)==2
        assert route._OPENING_FLIGHT.in_flight()==0
    asyncio.run(scenario())

def test_all_attempt_budget_and_failure_not_cached(route,client):
    client.raw=b'{}'
    for i in range(8):
        r=asyncio.run(route._get_opening_history('IWM',NOW))
        assert r['opening']['reason']=='source_identity'
    r=asyncio.run(route._get_opening_history('IWM',NOW))
    assert r['opening']['reason']=='request_budget_unavailable'
    assert len(client.calls)==8
    assert len(route._OPENING_CACHE)==0

def test_early_no_provider(route,client):
    r=asyncio.run(route._get_opening_history('IWM',NOW-timedelta(minutes=2)))
    assert r['opening']['reason']=='opening_in_progress'
    assert not client.calls

def test_cancel_releases_claim_and_slot(route,client):
    async def scenario():
        client.wait=asyncio.Event();task=asyncio.create_task(route._get_opening_history('IWM',NOW))
        while not client.calls:await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        client.wait.set();r=await route._get_opening_history('IWM',NOW)
        assert r['opening']['status']=='available'
    asyncio.run(scenario())

def test_row_limit_and_non_object():
    p=payload();p['Time Series (1min)']={str(i):{} for i in range(50001)}
    with pytest.raises(OpeningUnavailable,match='row_limit'):parse_acquisition(json.dumps(p).encode(),'IWM',NOW,session_for(NOW))
    for body in (b'[]',b'null',b'{',b'{"x":NaN}'):
        with pytest.raises(OpeningUnavailable):parse_acquisition(body,'IWM',NOW,session_for(NOW))

def test_cache_bound_and_budget_rollover(route,client,monkeypatch):
    clock=[100.0];monkeypatch.setattr(route.monotonic_time,'monotonic',lambda:clock[0])
    for i in range(8):assert route._opening_dispatch_allowed()
    assert not route._opening_dispatch_allowed()
    clock[0]+=60
    assert route._opening_dispatch_allowed()
    for i in range(9):route._OPENING_CACHE[str(i)]={'fixture':i}
    assert len(route._OPENING_CACHE)==8

def test_failed_required_refresh_does_not_expose_old_success(route,client):
    assert asyncio.run(route._get_opening_history('IWM',NOW))['opening']['status']=='available'
    client.raw=b'{}'
    r=asyncio.run(route._get_opening_history('IWM',NOW+timedelta(seconds=121)))
    assert r['opening']['status']=='unavailable'
    assert r['bars']==[]

def test_total_deadline_releases_capacity(route,client,monkeypatch):
    real_timeout=asyncio.timeout
    monkeypatch.setattr(route.asyncio,'timeout',lambda _:real_timeout(.01))
    async def scenario():
        client.wait=asyncio.Event()
        r=await route._get_opening_history('IWM',NOW)
        assert r['opening']['reason']=='acquisition_timeout'
        assert route._OPENING_FLIGHT.in_flight()==0
        assert route._OPENING_SLOTS.acquire(blocking=False)
        route._OPENING_SLOTS.release()
    asyncio.run(scenario())


def test_compressed_response_refused_before_decode(route,client):
    client.encoding='gzip'
    r=asyncio.run(route._get_opening_history('IWM',NOW))
    assert r['opening']['reason']=='unsupported_content_encoding'
    assert r['bars']==[]

def test_repeated_cancel_does_not_release_live_parser_slot(route,client,monkeypatch):
    import threading
    started=threading.Event();release=threading.Event();original=route.parse_acquisition
    def delayed(*args):
        started.set()
        if not release.wait(2):raise AssertionError('test worker release missing')
        return original(*args)
    monkeypatch.setattr(route,'parse_acquisition',delayed)
    async def scenario():
        task=asyncio.create_task(route._get_opening_history('IWM',NOW))
        try:
            async with asyncio.timeout(2):
                while not started.is_set():await asyncio.sleep(.001)
            task.cancel();await asyncio.sleep(.001);task.cancel();await asyncio.sleep(.001)
            assert route._OPENING_FLIGHT.in_flight()==1
            assert route._OPENING_SLOTS.acquire(blocking=False)
            assert not route._OPENING_SLOTS.acquire(blocking=False)
            route._OPENING_SLOTS.release()
        finally:release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert route._OPENING_FLIGHT.in_flight()==0
    asyncio.run(scenario())
