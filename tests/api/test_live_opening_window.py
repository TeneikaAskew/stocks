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
    r=asyncio.run(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
    assert r['opening']['status']=='available'
    assert len(client.calls)==2
    assert client.calls[1]=={'function':'TIME_SERIES_INTRADAY','symbol':'IWM','interval':'1min','outputsize':'full','adjusted':'false','entitlement':'realtime','apikey':'synthetic-offline-key'}

def test_bounded_stream(route,client):
    client.raw=b'x'*(8*1024*1024+1)
    r=asyncio.run(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
    assert r['opening']['reason']=='body_limit'
    assert r['bars']==[]
    assert len(client.calls)==1

def test_capacity_and_cache(route,client):
    async def scenario():
        client.wait=asyncio.Event()
        one=asyncio.create_task(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
        while len(client.calls)<1:await asyncio.sleep(0)
        duplicate=await route._get_opening_history('IWM',NOW, principal='fixture@example.test')
        assert duplicate['opening']['reason']=='acquisition_in_progress'
        two=asyncio.create_task(route._get_opening_history('SPY',NOW, principal='fixture@example.test'))
        while len(client.calls)<2:await asyncio.sleep(0)
        refused=await route._get_opening_history('QQQ',NOW, principal='fixture@example.test')
        assert refused['opening']['reason']=='capacity_unavailable'
        client.wait.set();await asyncio.gather(one,two)
        hit=await route._get_opening_history('IWM',NOW+timedelta(seconds=30), principal='fixture@example.test')
        assert hit['opening']['comparison_age_seconds']==30
        assert len(client.calls)==2
        assert route._OPENING_FLIGHT.in_flight()==0
    asyncio.run(scenario())

def test_all_attempt_budget_and_failure_not_cached(route,client):
    client.raw=b'{}'
    for i in range(8):
        r=asyncio.run(route._get_opening_history('IWM',NOW, principal=f'owner{i//4}@example.test'))
        assert r['opening']['reason']=='source_identity'
    r=asyncio.run(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
    assert r['opening']['reason']=='request_budget_unavailable'
    assert len(client.calls)==8
    assert len(route._OPENING_CACHE)==0

def test_early_no_provider(route,client):
    r=asyncio.run(route._get_opening_history('IWM',NOW-timedelta(minutes=2), principal='fixture@example.test'))
    assert r['opening']['reason']=='opening_in_progress'
    assert not client.calls

def test_cancel_releases_claim_and_slot(route,client):
    async def scenario():
        client.wait=asyncio.Event();task=asyncio.create_task(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
        while not client.calls:await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        client.wait.set();r=await route._get_opening_history('IWM',NOW, principal='fixture@example.test')
        assert r['opening']['status']=='available'
    asyncio.run(scenario())

def test_row_limit_and_non_object():
    p=payload();p['Time Series (1min)']={str(i):{} for i in range(50001)}
    with pytest.raises(OpeningUnavailable,match='row_limit'):parse_acquisition(json.dumps(p).encode(),'IWM',NOW,session_for(NOW))
    for body in (b'[]',b'null',b'{',b'{"x":NaN}'):
        with pytest.raises(OpeningUnavailable):parse_acquisition(body,'IWM',NOW,session_for(NOW))

def test_cache_bound_and_budget_rollover(route,client,monkeypatch):
    clock=[100.0];monkeypatch.setattr(route.monotonic_time,'monotonic',lambda:clock[0])
    for i in range(8):assert route._opening_dispatch_allowed(f"owner{i//4}@example.test")
    assert not route._opening_dispatch_allowed("other@example.test")
    clock[0]+=60
    assert route._opening_dispatch_allowed("owner0@example.test")
    for i in range(9):route._OPENING_CACHE[str(i)]={'fixture':i}
    assert len(route._OPENING_CACHE)==8

def test_failed_required_refresh_does_not_expose_old_success(route,client):
    assert asyncio.run(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))['opening']['status']=='available'
    client.raw=b'{}'
    r=asyncio.run(route._get_opening_history('IWM',NOW+timedelta(seconds=121), principal='fixture@example.test'))
    assert r['opening']['status']=='unavailable'
    assert r['bars']==[]

def test_total_deadline_releases_capacity(route,client,monkeypatch):
    real_timeout=asyncio.timeout
    monkeypatch.setattr(route.asyncio,'timeout',lambda _:real_timeout(.01))
    async def scenario():
        client.wait=asyncio.Event()
        r=await route._get_opening_history('IWM',NOW, principal='fixture@example.test')
        assert r['opening']['reason']=='acquisition_timeout'
        assert route._OPENING_FLIGHT.in_flight()==0
        assert route._OPENING_SLOTS.acquire(blocking=False)
        route._OPENING_SLOTS.release()
    asyncio.run(scenario())


def test_compressed_response_refused_before_decode(route,client):
    client.encoding='gzip'
    r=asyncio.run(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
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
        task=asyncio.create_task(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
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
        async with asyncio.timeout(2):
            while route._OPENING_FLIGHT.in_flight():await asyncio.sleep(.001)
        assert route._OPENING_FLIGHT.in_flight()==0
    asyncio.run(scenario())

@pytest.mark.parametrize('canonical,alias', [
    ('2026-10-29 10:00:00', '2026-10-29 10:0:00'),
    ('2026-10-29 09:30:00', '2026-10-29 9:30:00'),
    ('2026-10-29 08:00:00', '2026-10-29 8:00:00'),
])
def test_repair_rejects_timestamp_aliases_across_series(canonical, alias):
    p=payload(); series=p['Time Series (1min)']
    series[canonical]={'1. open':'100','2. high':'1000','3. low':'99','4. close':'101','5. volume':'10'}
    series[alias]={**series[canonical], '4. close':'999'}
    with pytest.raises(OpeningUnavailable):
        parse_acquisition(json.dumps(p).encode(),'IWM',NOW,session_for(NOW))


def test_repair_cold_calendar_burst_has_one_builder(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from lib import opening_window as ow
    original=ow.mcal.get_calendar
    gate=threading.Barrier(6); release=threading.Event(); entered=threading.Event(); calls=[]
    def slow_calendar(*args, **kwargs):
        calls.append(1); entered.set()
        assert release.wait(2)
        return original(*args, **kwargs)
    monkeypatch.setattr(ow.mcal,'get_calendar',slow_calendar)
    ow._SCHEDULE_CACHE.clear()
    def ask():
        gate.wait()
        try:return ow.session_for(NOW)
        except OpeningUnavailable:return None
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(ask) for _ in range(6)]
        try:
            assert entered.wait(1)
            import time; time.sleep(.05)
            assert len(calls)==1
        finally:release.set()
        results=[f.result() for f in futures]
    assert any(r and r['label']=='2026-10-29' for r in results)
    assert ow.session_for(NOW)['label']=='2026-10-29'
    assert len(calls)==1


def test_repair_timeout_returns_while_worker_owns_capacity(route,client,monkeypatch):
    import threading
    started=threading.Event();release=threading.Event();original=route.parse_acquisition
    def delayed(*args):
        started.set()
        assert release.wait(2)
        return original(*args)
    monkeypatch.setattr(route,'parse_acquisition',delayed)
    real_timeout=asyncio.timeout
    monkeypatch.setattr(route.asyncio,'timeout',lambda _:real_timeout(.01))
    async def scenario():
        task=asyncio.create_task(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
        try:
            done,_=await asyncio.wait({task},timeout=.15)
            assert started.is_set()
            assert task in done, 'response waited for timed-out parser'
            assert task.result()['opening']['reason']=='acquisition_timeout'
            assert route._OPENING_FLIGHT.in_flight()==1
            assert route._OPENING_SLOTS.acquire(blocking=False)
            assert not route._OPENING_SLOTS.acquire(blocking=False)
            route._OPENING_SLOTS.release()
        finally:
            release.set()
            await task
        async with real_timeout(2):
            while route._OPENING_FLIGHT.in_flight():await asyncio.sleep(.001)
        assert len(route._OPENING_CACHE)==0
    asyncio.run(scenario())


def test_repair_vendor_datetime_overflow_is_typed():
    from lib.opening_window import vendor_time
    with pytest.raises(OpeningUnavailable,match='invalid_timestamp'):
        vendor_time('9999-12-31 23:59:00')


def test_repair_all_datetime_arithmetic_is_typed():
    from datetime import timezone
    extreme=datetime.max.replace(tzinfo=timezone.utc)
    with pytest.raises(OpeningUnavailable):
        compute_observed_opening_range([],now=extreme,session={'open':extreme,'close':extreme,'label':'9999-12-31'})
    underflow=datetime.min.replace(tzinfo=timezone(timedelta(hours=14)))
    with pytest.raises(OpeningUnavailable):
        parse_acquisition(b'{}','IWM',underflow,None)


def test_repair_parser_ownership_survives_loop_close(route,client,monkeypatch):
    import threading
    started=threading.Event();release=threading.Event();finished=threading.Event()
    def delayed(*args):
        started.set()
        try:
            assert release.wait(2)
            raise OpeningUnavailable('invalid_json')
        finally:finished.set()
    monkeypatch.setattr(route,'parse_acquisition',delayed)
    async def cancel():
        task=asyncio.create_task(route._get_opening_history('IWM',NOW, principal='fixture@example.test'))
        async with asyncio.timeout(1):
            while not started.is_set():await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    try:
        asyncio.run(cancel())  # caller's loop closes while worker still owns RAM
        assert not finished.is_set()
        assert route._OPENING_FLIGHT.in_flight()==1
    finally:release.set()
    assert finished.wait(1)
    import time
    until=time.monotonic()+1
    while route._OPENING_FLIGHT.in_flight() and time.monotonic()<until:time.sleep(.001)
    assert route._OPENING_FLIGHT.in_flight()==0
    assert route._OPENING_SLOTS.acquire(blocking=False)
    assert route._OPENING_SLOTS.acquire(blocking=False)
    route._OPENING_SLOTS.release();route._OPENING_SLOTS.release()


def test_repair_warm_calendar_survives_other_day_build(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from lib import opening_window as ow
    ow._SCHEDULE_CACHE.clear();expected=ow.session_for(NOW)
    original=ow.mcal.get_calendar;started=threading.Event();release=threading.Event()
    def slow(*args,**kwargs):
        started.set();assert release.wait(2)
        return original(*args,**kwargs)
    monkeypatch.setattr(ow.mcal,'get_calendar',slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        cold=pool.submit(ow.session_for,NOW+timedelta(days=1))
        try:
            assert started.wait(1)
            assert ow.session_for(NOW)==expected
            with pytest.raises(OpeningUnavailable,match='calendar_in_progress'):
                ow.session_for(NOW+timedelta(days=2))
        finally:release.set()
        assert cold.result()['label']=='2026-10-30'


def test_repair_success_claim_held_through_cache_publication(route,client,monkeypatch):
    real_cache=route._OPENING_CACHE
    class ObservedCache:
        def get(self,key):return real_cache.get(key)
        def __setitem__(self,key,value):
            assert route._OPENING_FLIGHT.in_flight()==1
            assert route._OPENING_SLOTS.acquire(blocking=False)
            assert not route._OPENING_SLOTS.acquire(blocking=False)
            route._OPENING_SLOTS.release()
            real_cache[key]=value
    monkeypatch.setattr(route,'_OPENING_CACHE',ObservedCache())
    async def scenario():
        assert (await route._get_opening_history('IWM',NOW, principal='fixture@example.test'))['opening']['status']=='available'
        assert route._OPENING_FLIGHT.in_flight()==0
        assert (await route._get_opening_history('IWM',NOW, principal='fixture@example.test'))['opening']['status']=='available'
        assert len(client.calls)==1
    asyncio.run(scenario())

@pytest.mark.parametrize('late_error',[False,True])
def test_repair_two_expired_parsers_bound_all_remaining_work(route,client,monkeypatch,late_error):
    import threading
    release=threading.Event();original=route.parse_acquisition
    def delayed(*args):
        assert release.wait(2)
        if late_error:raise OpeningUnavailable('invalid_json')
        return original(*args)
    monkeypatch.setattr(route,'parse_acquisition',delayed)
    real_timeout=asyncio.timeout
    monkeypatch.setattr(route.asyncio,'timeout',lambda _:real_timeout(.01))
    async def scenario():
        session_for(NOW)
        tasks=[asyncio.create_task(route._get_opening_history(t,NOW, principal='fixture@example.test')) for t in ('IWM','SPY')]
        try:
            done,_=await asyncio.wait(tasks,timeout=.15)
            assert len(done)==2
            assert all(t.result()['opening']['reason']=='acquisition_timeout' for t in tasks)
            assert route._OPENING_FLIGHT.in_flight()==2
            assert not route._OPENING_SLOTS.acquire(blocking=False)
            assert (await route._get_opening_history('IWM',NOW, principal='fixture@example.test'))['opening']['reason']=='acquisition_in_progress'
            assert (await route._get_opening_history('QQQ',NOW, principal='fixture@example.test'))['opening']['reason']=='capacity_unavailable'
            assert len(client.calls)==2
        finally:
            release.set()
            await asyncio.gather(*tasks)
        async with real_timeout(2):
            while route._OPENING_FLIGHT.in_flight():await asyncio.sleep(.001)
        assert len(route._OPENING_CACHE)==0
        assert route._OPENING_SLOTS.acquire(blocking=False)
        assert route._OPENING_SLOTS.acquire(blocking=False)
        route._OPENING_SLOTS.release();route._OPENING_SLOTS.release()
    asyncio.run(scenario())

# SEC r4420960497: use the real auth middleware and verified-email check;
# only external Firebase verification and provider transport are hermetic.
import httpx as _httpx
_ASGIClient = _httpx.AsyncClient

@pytest.fixture
def authenticated_orb(route,client,monkeypatch):
    import types
    from fastapi import FastAPI
    from api import auth
    monkeypatch.setattr(auth,'AUTH_MODE','firebase')
    monkeypatch.setattr(auth,'_ensure_firebase',lambda:None)
    monkeypatch.setattr(auth,'_is_allowed',lambda email:True)
    class FakeAuth:
        @staticmethod
        def verify_id_token(token,**kwargs):
            assert kwargs=={'clock_skew_seconds':60}
            if token=='invalid':raise ValueError('synthetic invalid token')
            return {'email':f'{token}@example.test','email_verified':token!='unverified'}
    sdk=types.ModuleType('firebase_admin');sdk.auth=FakeAuth
    monkeypatch.setitem(sys.modules,'firebase_admin',sdk)
    class FixedDatetime(datetime):
        @classmethod
        def now(cls,tz=None):return NOW.astimezone(tz or timezone.utc)
    monkeypatch.setattr(route,'datetime',FixedDatetime)
    clock=[100.0]
    monkeypatch.setattr(route,'monotonic_time',types.SimpleNamespace(monotonic=lambda:clock[0]))
    app=FastAPI();principals=[]
    @app.middleware('http')
    async def observe(request,call_next):
        principals.append(request.state.user_email)
        return await call_next(request)
    app.middleware('http')(auth.auth_middleware)
    app.include_router(route.router)
    return app,auth,clock,principals


def test_principal_four_then_victim_retains_global_capacity(route,client,authenticated_orb):
    app,_,_,principals=authenticated_orb
    async def run():
        client.raw=b'{}'
        async with _ASGIClient(transport=_httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            reasons=[]
            for i in range(8):
                r=await http.get(f'/api/live/history/A{i}?include_opening=true',headers={
                    'authorization':'Bearer '+('attacker' if i%2==0 else 'ATTACKER'),'x-user-email':f'fake{i}@example.test',
                    'x-goog-authenticated-user-email':f'accounts.google.com:fake{i}@example.test'})
                assert r.status_code==200
                reasons.append(r.json()['opening']['reason'])
            assert reasons[:4]==['source_identity']*4
            assert reasons[4:]==['request_budget_unavailable']*4
            assert principals==['attacker@example.test']*8
            assert len(client.calls)==4
            client.raw=None
            victim=await http.get('/api/live/history/IWM?include_opening=true',headers={'authorization':'Bearer victim'})
            assert victim.status_code==200 and victim.json()['opening']['status']=='available'
            assert principals[-1]=='victim@example.test'
            assert len(client.calls)==5
    asyncio.run(run())


@pytest.mark.parametrize('mode,token',[('firebase',None),('firebase','invalid'),('firebase','unverified'),('open',None),('open','attacker'),('iap',None),('iap','attacker')])
def test_principal_missing_invalid_and_identity_free_modes_refuse_before_orb(route,client,authenticated_orb,monkeypatch,mode,token):
    app,auth,_,_=authenticated_orb
    def forbidden(_):raise AssertionError('unverified request reached calendar')
    async def run():
        async with _ASGIClient(transport=_httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            url='/api/live/history/IWM?include_opening=true'
            # A real authorized response is already cached; auth refusal must
            # precede even a cache hit, as well as calendar/claim/provider work.
            assert (await http.get(url,headers={'authorization':'Bearer seed'})).json()['opening']['status']=='available'
            monkeypatch.setattr(auth,'AUTH_MODE',mode)
            monkeypatch.setattr(route,'session_for',forbidden)
            headers={'x-user-email':'forged@example.test','x-goog-authenticated-user-email':'accounts.google.com:forged@example.test','x-request-state-user-email':'forged@example.test'}
            if token:headers['authorization']='Bearer '+token
            r=await http.get(url,headers=headers)
            assert r.status_code==(403 if token=='unverified' else 401)
            assert len(client.calls)==1 and len(route._OPENING_ATTEMPTS)==1
            assert route._OPENING_FLIGHT.in_flight()==0
    asyncio.run(run())


def test_principal_cache_hits_uncharged_but_not_anonymous(route,client,authenticated_orb,monkeypatch):
    app,auth,_,_=authenticated_orb
    async def run():
        async with _ASGIClient(transport=_httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            url='/api/live/history/IWM?include_opening=true'
            assert (await http.get(url,headers={'authorization':'Bearer owner'})).json()['opening']['status']=='available'
            client.raw=b'{}'
            for i in range(3):
                assert (await http.get(f'/api/live/history/A{i}?include_opening=true',headers={'authorization':'Bearer owner'})).json()['opening']['reason']=='source_identity'
            for i in range(4):
                assert (await http.get(f'/api/live/history/B{i}?include_opening=true',headers={'authorization':'Bearer second'})).json()['opening']['reason']=='source_identity'
            for who in ('owner','victim'):
                for _ in range(6):
                    assert (await http.get(url,headers={'authorization':'Bearer '+who})).json()['opening']['status']=='available'
            assert len(client.calls)==8 and len(route._OPENING_ATTEMPTS)==8
            monkeypatch.setattr(auth,'AUTH_MODE','open')
            assert (await http.get(url)).status_code==401
            assert len(client.calls)==8
    asyncio.run(run())


def test_principal_global_eight_including_failures_and_rollover(route,client,authenticated_orb):
    app,_,clock,_=authenticated_orb
    async def run():
        client.raw=b'{}'
        async with _ASGIClient(transport=_httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            async def get(who,ticker):
                return await http.get(f'/api/live/history/{ticker}?include_opening=true',headers={'authorization':'Bearer '+who})
            for i in range(4):
                pair=await asyncio.gather(get('a',f'A{i}'),get('b',f'B{i}'))
                assert all(r.json()['opening']['reason']=='source_identity' for r in pair)
            assert len(client.calls)==8 and len(route._OPENING_ATTEMPTS)==8
            assert (await get('c','QQQ')).json()['opening']['reason']=='request_budget_unavailable'
            clock[0]+=59.999
            assert (await get('a','QQQ')).json()['opening']['reason']=='request_budget_unavailable'
            clock[0]+=.001
            assert (await get('a','QQQ')).json()['opening']['reason']=='source_identity'
            assert len(client.calls)==9 and len(route._OPENING_ATTEMPTS)==1
    asyncio.run(run())


def test_principal_many_identities_cannot_grow_budget_memory(route,client,authenticated_orb):
    app,_,clock,_=authenticated_orb
    async def run():
        client.raw=b'{}'
        async with _ASGIClient(transport=_httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            for cycle in range(3):
                for i in range(24):
                    r=await http.get('/api/live/history/IWM?include_opening=true',headers={'authorization':f'Bearer user{cycle}-{i}'})
                    assert r.json()['opening']['reason']==('source_identity' if i<8 else 'request_budget_unavailable')
                    assert len(route._OPENING_ATTEMPTS)<=8
                clock[0]+=60
            assert len(client.calls)==24
    asyncio.run(run())


def test_principal_legacy_compact_history_unchanged(route,client,authenticated_orb,monkeypatch):
    app,auth,_,_=authenticated_orb
    monkeypatch.setattr(auth,'AUTH_MODE','open')
    async def run():
        async with _ASGIClient(transport=_httpx.ASGITransport(app=app),base_url='http://fixture') as http:
            r=await http.get('/api/live/history/IWM')
            assert r.status_code==200 and r.json()['count']>0
            assert len(client.calls)==1 and client.calls[0]['outputsize']=='compact'
            assert len(route._OPENING_ATTEMPTS)==0
    asyncio.run(run())


def test_principal_cancelled_dispatches_remain_charged_and_release_claims(route,client):
    async def run():
        client.wait=asyncio.Event()
        for i in range(4):
            task=asyncio.create_task(route._get_opening_history('IWM',NOW,principal='a@example.test'))
            async with asyncio.timeout(2):
                while len(client.calls)<i+1:await asyncio.sleep(.001)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert route._OPENING_FLIGHT.in_flight()==0
        client.wait=None
        refused=await route._get_opening_history('IWM',NOW,principal='a@example.test')
        assert refused['opening']['reason']=='request_budget_unavailable'
        assert len(client.calls)==4
        accepted=await route._get_opening_history('IWM',NOW,principal='b@example.test')
        assert accepted['opening']['status']=='available'
        assert len(client.calls)==5 and len(route._OPENING_ATTEMPTS)==5
        assert route._OPENING_SLOTS.acquire(blocking=False)
        assert route._OPENING_SLOTS.acquire(blocking=False)
        route._OPENING_SLOTS.release();route._OPENING_SLOTS.release()
    asyncio.run(run())
