"""Logger-only safety: synthetic credentials, real fetcher, zero live HTTP/SQL.

Legacy error-to-empty semantics remain intentionally unchanged in this narrow
repair; typed outcome correctness is the separate producer specification.
"""
import logging
from types import SimpleNamespace

import pytest
import requests

FAKE_KEY = 'FAKE-NEWS-KEY-REDACTION-ONLY'
PARAMS = {
    'function':'NEWS_SENTIMENT','tickers':'APLD','limit':1000,
    'time_from':'20260725T2005','time_to':'20260727T2005',
    'sort':'EARLIEST','apikey':FAKE_KEY,
}
UNSAFE = f'https://example.invalid/query?apikey={FAKE_KEY} Authorization: Bearer {FAKE_KEY}'


@pytest.fixture
def fetcher(monkeypatch):
    from gcp.fetchers import fetch_news_sentiment as module
    def forbidden(*args,**kwargs):
        raise AssertionError('live HTTP or SQL forbidden')
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)
    monkeypatch.setattr(requests,'get',forbidden)
    monkeypatch.setattr(module,'query_to_dataframe',forbidden)
    monkeypatch.setattr(module,'upsert_dataframe',forbidden)
    return module


def safe_records(caplog,module,expected):
    records=[r for r in caplog.records if r.name==module.logger.name]
    assert len(records)==1
    record=records[0]
    assert record.msg==expected
    assert record.args==()
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.stack_info is None
    assert FAKE_KEY not in record.getMessage()
    assert 'apikey=' not in record.getMessage()
    assert 'Authorization' not in record.getMessage()


@pytest.mark.parametrize('stage',['dispatch','http_status','json'])
def test_exception_warning_does_not_retain_request_response_or_exception(fetcher,monkeypatch,caplog,stage):
    calls=[]
    def fail():raise RuntimeError(UNSAFE)
    def get(url,*,params,timeout):
        calls.append((url,params.copy(),timeout))
        if stage=='dispatch':fail()
        return SimpleNamespace(
            raise_for_status=fail if stage=='http_status' else lambda:None,
            json=fail if stage=='json' else lambda:{'feed':[]},
            headers={'Authorization':UNSAFE,'request-id':FAKE_KEY},
        )
    monkeypatch.setattr(requests,'get',get)
    caplog.set_level(logging.WARNING,logger=fetcher.logger.name)
    assert fetcher._fetch(dict(PARAMS))==[]
    assert calls==[(fetcher.AV_BASE_URL,PARAMS,30)]
    safe_records(caplog,fetcher,'AV NEWS_SENTIMENT request failed')


class PoisonInformation:
    def __str__(self):raise AssertionError('provider Information must not be stringified')
    def __repr__(self):return FAKE_KEY


@pytest.mark.parametrize('info',[UNSAFE,{'headers':{'Authorization':UNSAFE},'error':FAKE_KEY},PoisonInformation()])
@pytest.mark.parametrize('feed',[[],[{'title':'unchanged synthetic article'}]])
def test_provider_information_is_never_logged_or_stringified(fetcher,monkeypatch,caplog,info,feed):
    calls=[]
    def get(url,*,params,timeout):
        calls.append((url,params.copy(),timeout))
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'Information':info,'feed':feed})
    monkeypatch.setattr(requests,'get',get)
    caplog.set_level(logging.WARNING,logger=fetcher.logger.name)
    assert fetcher._fetch(dict(PARAMS)) == feed
    assert calls==[(fetcher.AV_BASE_URL,PARAMS,30)]
    safe_records(caplog,fetcher,'AV NEWS_SENTIMENT provider Information response')


@pytest.mark.parametrize('payload,expected',[
    ({},[]),({'feed':None},[]),({'feed':[]},[]),
    ({'feed':[{'title':'unchanged article'}]},[{'title':'unchanged article'}]),
    ({'Note':'synthetic legacy notice'},[]),({'Error Message':'synthetic legacy error'},[]),
])
def test_logger_only_scope_preserves_request_and_legacy_return_semantics(fetcher,monkeypatch,caplog,payload,expected):
    calls=[]
    def get(url,*,params,timeout):
        calls.append((url,params.copy(),timeout))
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'get',get)
    assert fetcher._fetch(dict(PARAMS))==expected
    assert calls==[('https://www.alphavantage.co/query',PARAMS,30)]
    assert not [r for r in caplog.records if r.name==fetcher.logger.name]


@pytest.mark.parametrize('payload',[None,[],False,'ordinary string','Information '+FAKE_KEY])
def test_nonmapping_payload_remains_failure_not_new_empty_success(fetcher,monkeypatch,payload):
    calls=[]
    def get(*args,**kwargs):
        calls.append(1)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'get',get)
    with pytest.raises((TypeError,AttributeError)):
        fetcher._fetch(dict(PARAMS))
    assert calls==[1]
