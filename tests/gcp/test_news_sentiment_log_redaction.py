"""Typed outcome diagnostic safety: synthetic credentials, zero live HTTP/SQL."""
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
    assert record.msg=="NEWS_SENTIMENT unavailable category=%s"
    assert record.args==(expected,)
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
    assert fetcher._fetch(dict(PARAMS)).state=="error"
    assert calls==[(fetcher.AV_BASE_URL,PARAMS,30)]
    safe_records(caplog,fetcher,{'dispatch':'transport','http_status':'http','json':'json'}[stage])


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
    assert fetcher._fetch(dict(PARAMS)) == fetcher.FetchOutcome("error", "provider_information")
    assert calls==[(fetcher.AV_BASE_URL,PARAMS,30)]
    safe_records(caplog,fetcher,'provider_information')


@pytest.mark.parametrize('payload,state,kind',[
    ({},'error','schema'),({'feed':None},'error','schema'),({'feed':[]},'empty',None),
    ({'feed':[{'title':'unchanged article'}]},'error','schema'),
    ({'Note':'synthetic notice'},'error','provider_note'),({'Error Message':'synthetic error'},'error','provider_error'),
])
def test_typed_outcomes_preserve_request_and_safe_diagnostics(fetcher,monkeypatch,caplog,payload,state,kind):
    calls=[]
    def get(url,*,params,timeout):
        calls.append((url,params.copy(),timeout))
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'get',get)
    assert fetcher._fetch(dict(PARAMS))==fetcher.FetchOutcome(state,kind)
    assert calls==[('https://www.alphavantage.co/query',PARAMS,30)]
    if kind:
        safe_records(caplog,fetcher,kind)
    else:
        assert not [r for r in caplog.records if r.name==fetcher.logger.name]


@pytest.mark.parametrize('payload',[None,[],False,'ordinary string','Information '+FAKE_KEY])
def test_nonmapping_payload_remains_failure_not_new_empty_success(fetcher,monkeypatch,payload):
    calls=[]
    def get(*args,**kwargs):
        calls.append(1)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload)
    monkeypatch.setattr(requests,'get',get)
    assert fetcher._fetch(dict(PARAMS)) == fetcher.FetchOutcome("error", "schema")
    assert calls==[1]


@pytest.mark.parametrize('ticker',[FAKE_KEY, 'bad\nAuthorization: '+FAKE_KEY+'\r'+('x'*500)])
def test_incremental_lookup_failure_keeps_query_and_request_but_not_raw_identifier(fetcher,monkeypatch,caplog,ticker):
    """A cursor failure must retain the cold-start request, without reflecting inputs."""
    from datetime import datetime, timezone
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026,10,29,12,0,tzinfo=timezone.utc)
    queries=[]; calls=[]
    def query(sql,params):
        queries.append((sql,params))
        raise RuntimeError(UNSAFE)
    def get(url,*,params,timeout):
        calls.append((url,params.copy(),timeout))
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[]})
    monkeypatch.setattr(fetcher,'datetime',FixedDatetime)
    monkeypatch.setattr(fetcher,'query_to_dataframe',query)
    monkeypatch.setattr(requests,'get',get)
    caplog.set_level(logging.DEBUG,logger=fetcher.logger.name)
    batch=fetcher.fetch_by_tickers([ticker],FAKE_KEY,1000,incremental=True)
    assert batch.frame.empty and batch.outcomes==(fetcher.SourceOutcome('empty'),)
    assert queries==[('SELECT MAX(published_ts) AS max_ts FROM news_sentiment WHERE ticker = :tk',{'tk':ticker.upper()})]
    assert calls==[(fetcher.AV_BASE_URL,{
        'function':'NEWS_SENTIMENT','tickers':ticker,'limit':1000,'apikey':FAKE_KEY,
        'time_from':'20261027T1200','sort':'EARLIEST',
    },30)]
    records=[r for r in caplog.records if r.name==fetcher.logger.name]
    assert records and any(r.levelno==logging.WARNING for r in records)
    for record in records:
        assert FAKE_KEY not in record.getMessage()
        assert FAKE_KEY not in repr(record.args)
        assert 'Authorization' not in record.getMessage()
        assert '\n' not in record.getMessage() and '\r' not in record.getMessage()
        assert len(record.getMessage())<200
        assert record.exc_info is None and record.stack_info is None


@pytest.mark.parametrize('ticker',[FAKE_KEY, 'bad\nAuthorization: '+FAKE_KEY+'\r'+('x'*500)])
@pytest.mark.parametrize('last_ts,expected',[
    (None,'20261027T1200'),
    ('2026-10-29T11:30:00+00:00','20261029T1100'),
    ('2026-10-01T12:00:00+00:00','20261022T1200'),
])
def test_incremental_floor_diagnostics_do_not_retain_raw_identifier(fetcher,monkeypatch,caplog,ticker,last_ts,expected):
    """Cold, normal and stale bounds survive removing unsafe log identifiers."""
    from datetime import datetime,timezone
    import pandas as pd
    queries=[]
    def query(sql,params):
        queries.append(params)
        return pd.DataFrame()
    monkeypatch.setattr(fetcher,'query_to_dataframe',query)
    caplog.set_level(logging.INFO,logger=fetcher.logger.name)
    prior=datetime.fromisoformat(last_ts) if last_ts else None
    actual=fetcher._resolve_incremental_time_from(ticker,datetime(2026,10,29,12,0,tzinfo=timezone.utc),last_ts=prior)
    assert actual==expected
    assert queries==([{'tk':ticker.upper()}] if last_ts is None else [])
    records=[r for r in caplog.records if r.name==fetcher.logger.name]
    assert records
    for record in records:
        assert FAKE_KEY not in record.getMessage() and FAKE_KEY not in repr(record.args)
        assert '\n' not in record.getMessage() and '\r' not in record.getMessage()
        assert len(record.getMessage())<200
        assert record.exc_info is None and record.stack_info is None
