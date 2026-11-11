"""Offline packaging controls for the CLI-only bounded source transport."""
import gzip
import io
import json
import signal
import threading
import time
import zlib

import pytest
import requests

from gcp.fetchers import _av_realtime_transport as source

PARAMS={'function':'REALTIME_OPTIONS','symbol':'SPY','require_greeks':'true',
        'datatype':'json','apikey':'fake-key'}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket
    def blocked(*args,**kwargs):raise AssertionError('external I/O forbidden')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setattr(socket,'create_connection',blocked)
    monkeypatch.setattr(requests.sessions.Session,'request',blocked)


class Raw:
    def __init__(self,body,encoding=''):
        self.body=io.BytesIO(body)
        self.headers={'content-encoding':encoding}
        self.read_bytes=0
    def read(self,size,decode_content=False):
        assert decode_content is False
        result=self.body.read(size);self.read_bytes+=len(result);return result


class Response:
    def __init__(self,body=b'{"data":[]}',status=200,encoding=''):
        self.raw=Raw(body,encoding);self.status_code=status
        self.headers={'x-request-id':'test'};self.closed=False
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError('secret-key/full-url')
    def close(self):self.closed=True


def install(monkeypatch,response,hook=True):
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        if hook:
            prepared=requests.Request('GET',url,auth=kwargs['auth']).prepare()
            for callback in prepared.hooks['response']:callback(response)
        return response
    monkeypatch.setattr(source.requests,'get',get)
    return calls


@pytest.mark.parametrize('encoding,encode',[('',lambda b:b),('gzip',gzip.compress),('deflate',zlib.compress)])
def test_complete_safe_request_and_decoded_body(monkeypatch,encoding,encode):
    response=Response(encode(b'{"data":[]}'),encoding=encoding)
    calls=install(monkeypatch,response);seen=[]
    assert source.decoded_json(PARAMS,source.deadline(),seen.append)=={'data':[]}
    assert seen==[response] and response.closed
    url,kwargs=calls[0]
    assert url=='https://www.alphavantage.co/query'
    assert kwargs['params']==PARAMS
    assert kwargs['stream'] is True and kwargs['allow_redirects'] is False
    assert kwargs['headers']=={'Accept-Encoding':'gzip, deflate'}
    assert 0<kwargs['timeout']<=15
    assert isinstance(kwargs['auth'],source._NoSourceAuth)
    assert response.headers['x-request-id']=='test'


@pytest.mark.parametrize('status',[None,True,'200',99,600,302,400,500])
def test_status_refusal_safe_and_response_closed(monkeypatch,status):
    response=Response(status=status);install(monkeypatch,response);seen=[]
    with pytest.raises((source.SourceUnavailable,requests.HTTPError)) as error:
        source.decoded_json(PARAMS,source.deadline(),seen.append)
    assert str(error.value)=='http_error'
    assert seen==[response] and response.closed


def test_missing_real_hook_still_notifies_once(monkeypatch):
    response=Response();install(monkeypatch,response,hook=False);seen=[]
    source.decoded_json(PARAMS,source.deadline(),seen.append)
    assert seen==[response] and response.closed


@pytest.mark.parametrize('body,encoding',[(b'x'*(10*1024*1024+1),''),
    (gzip.compress(b'x'*(10*1024*1024+1)),'gzip')])
def test_encoded_and_decoded_caps(monkeypatch,body,encoding):
    response=Response(body,encoding=encoding);install(monkeypatch,response)
    with pytest.raises(source.SourceBodyLimit,match='^body_limit$'):
        source.decoded_json(PARAMS,source.deadline(),lambda r:None)
    assert response.closed and response.raw.read_bytes<=10*1024*1024+1


@pytest.mark.parametrize('body,encoding',[(b'secret-key',''),(b'broken','gzip'),
    (gzip.compress(b'{}')[:-3],'gzip'),(b'{}','br')])
def test_json_or_encoding_errors_never_include_content(monkeypatch,body,encoding):
    response=Response(body,encoding=encoding);install(monkeypatch,response)
    with pytest.raises(source.SourceUnavailable,match='^json_error$'):
        source.decoded_json(PARAMS,source.deadline(),lambda r:None)
    assert response.closed


def test_transport_exception_type_preserved_with_safe_text(monkeypatch):
    def fail(*a,**kw):raise requests.Timeout('fake-key/full-query')
    monkeypatch.setattr(source.requests,'get',fail)
    with pytest.raises(requests.Timeout,match='^transport_error$'):
        source.decoded_json(PARAMS,source.deadline(),lambda r:None)


def test_worker_refuses_before_dispatch_and_expired_deadline(monkeypatch):
    def fail(*a,**kw):raise AssertionError('no dispatch')
    monkeypatch.setattr(source.requests,'get',fail)
    errors=[]
    def worker():
        try:source.decoded_json(PARAMS,source.deadline(),lambda r:None)
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=worker);thread.start();thread.join()
    assert len(errors)==1 and isinstance(errors[0],source.SourceDeadline)
    with pytest.raises(source.SourceDeadline):source.remaining(time.monotonic()-1)


def test_deadline_interrupts_blocking_body_and_restores_timer(monkeypatch):
    response=Response()
    def slow(*a,**kw):time.sleep(1);return b''
    response.raw.read=slow;install(monkeypatch,response)
    original=signal.getsignal(signal.SIGALRM);started=time.monotonic()
    with pytest.raises(source.SourceDeadline,match='^source_deadline$'):
        source.decoded_json(PARAMS,started+0.04,lambda r:None)
    assert time.monotonic()-started<0.5 and response.closed
    assert signal.getsignal(signal.SIGALRM)==original
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)


def test_pacing_respects_existing_budget_without_extra_sleep(monkeypatch):
    sleeps=[];monkeypatch.setattr(source.time,'sleep',sleeps.append)
    source.pace(source.deadline(),0.4)
    assert sleeps==[0.4]
    with pytest.raises(source.SourceDeadline):source.pace(time.monotonic()+0.01,0.4)
    assert sleeps==[0.4]


@pytest.mark.parametrize('status',[200,302])
def test_real_requests_preparation_never_uses_netrc_or_redirect(monkeypatch,status):
    # Exercise real Requests preparation/hook behavior below mocked send only.
    monkeypatch.undo()
    import socket
    def blocked(*a,**kw):raise AssertionError('unexpected socket or netrc')
    monkeypatch.setattr(socket.socket,'connect',blocked)
    monkeypatch.setattr(socket,'create_connection',blocked)
    monkeypatch.setattr(requests.sessions,'get_netrc_auth',blocked)
    sends=[]
    def send(adapter,request,**kwargs):
        sends.append(request)
        response=requests.Response();response.status_code=status
        response.request=request;response.url=request.url
        response.headers={'Location':'https://never-follow.invalid/?fake-key'}
        response.raw=Raw(b'{}');response.raw.close=lambda:None
        return response
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',send)
    if status==302:
        with pytest.raises(source.SourceUnavailable,match='^http_error$'):
            source.decoded_json(PARAMS,source.deadline(),lambda r:None)
    else:
        assert source.decoded_json(PARAMS,source.deadline(),lambda r:None)=={}
    assert len(sends)==1 and 'Authorization' not in sends[0].headers


@pytest.mark.parametrize('value',[None,float('nan'),float('inf'),True,'15'])
def test_invalid_deadline_fails_safely(value):
    with pytest.raises(source.SourceDeadline,match='^source_deadline$'):
        source.remaining(value)


def test_owned_timer_is_preserved_without_dispatch(monkeypatch):
    response=Response();calls=install(monkeypatch,response)
    old_handler=signal.getsignal(signal.SIGALRM)
    signal.setitimer(signal.ITIMER_REAL,2)
    try:
        with pytest.raises(source.SourceDeadline):
            source.decoded_json(PARAMS,source.deadline(),lambda r:None)
        assert not calls
        assert signal.getitimer(signal.ITIMER_REAL)[0]>1
        assert signal.getsignal(signal.SIGALRM)==old_handler
    finally:signal.setitimer(signal.ITIMER_REAL,0)


@pytest.mark.parametrize('status',[200,500])
def test_slow_close_is_bounded_inside_original_deadline_and_preserves_error(monkeypatch,status):
    response=Response(status=status);install(monkeypatch,response)
    def close():
        response.closed=True
        time.sleep(1)
    response.close=close
    started=time.monotonic()
    expected=source.SourceDeadline if status==200 else requests.HTTPError
    with pytest.raises(expected):
        source.decoded_json(PARAMS,started+0.1,lambda r:None)
    assert response.closed
    assert time.monotonic()-started<0.7
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)


def test_fully_expired_cleanup_does_not_begin_potentially_blocking_close(monkeypatch):
    clock=[10.0];monkeypatch.setattr(source,'_source_clock',lambda:clock[0])
    response=Response();install(monkeypatch,response)
    def read(*a,**kw):clock[0]=21.0;return b'{}'
    response.raw.read=read
    with pytest.raises(source.SourceDeadline):
        source.decoded_json(PARAMS,20.0,lambda r:None)
    assert not response.closed
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)
