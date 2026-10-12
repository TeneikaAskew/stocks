from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from gcp.fetchers import _av_ingestion as av
from tests.integration.conftest import catalyst_db
from datetime import datetime,timedelta,timezone
import json


def test_failed_weekly_head_does_not_starve_universe(catalyst_db):
    c = catalyst_db
    names = [f"T{i:03}" for i in range(150)]
    claim = text("SELECT ticker FROM av_claim_catalyst_work('EARNINGS',CAST(:names AS text[]),'weekly','worker',100,false)")
    first = c.execute(claim, {"names": names}).scalars().all(); c.commit()
    assert set(first) == set(names[:100])
    c.execute(text("UPDATE av_catalyst_work SET failure_count=1,next_retry_at=clock_timestamp()+interval '1 hour',lease_owner=NULL,lease_expires_at=NULL WHERE last_attempt_at IS NOT NULL")); c.commit()
    second = c.execute(claim, {"names": names}).scalars().all(); c.commit()
    assert set(second) == set(names[100:])
    assert c.execute(text("SELECT count(*) FROM av_catalyst_work WHERE last_successful_observation_at IS NOT NULL")).scalar() == 0


def test_terminal_note_includes_source_watermark_and_attempts(monkeypatch):
    monkeypatch.setenv("CLOUD_RUN_TASK_ATTEMPT", "2")
    run = av.Run("fetch-news-sentiment", "daily", expected=3, failed=1, processed=2, rows_written=5, request_attempts=3, application_retries=1)
    run.groups = [{"source_event_max": "2026-10-08T15:00:00+00:00", "complete_through": None, "coverage_complete": False, "cursor_before": None, "cursor_after": None}]
    note = run.note()
    assert note["terminal_status"] == "partial"
    assert note["task_attempt"] == "2"
    assert note["application_retry_count"] == 1
    assert note["groups"][0]["coverage_complete"] is False


@pytest.mark.parametrize('parameters',[{'tickers':'IWM'},{'topics':'earnings,technology'}])
def test_saturated_news_subdivisions_eventually_advance_watermark(catalyst_db,parameters):
    from gcp.fetchers import fetch_news_sentiment as news
    c=catalyst_db
    start=datetime(2026,10,9,9,30,tzinfo=timezone.utc)
    scope={'query_identity':av.digest(parameters),'parameters':parameters,
           'window_start':start.isoformat(),'window_end':(start+timedelta(minutes=4)).isoformat()}
    articles=[{'title':str(i),'url':None,'source':'wire','time_published':(start+timedelta(seconds=i%240)).strftime('%Y%m%dT%H%M%S'),
               'ticker_sentiment':[{'ticker':'IWM','ticker_sentiment_score':'.1','relevance_score':'.8'}]} for i in range(1100)]
    def execute(sql,params,read=False,**kw):
        result=c.execute(text(sql),params)
        answer=[dict(r) for r in result.mappings()] if read else result.rowcount
        c.commit();return answer
    def source(params,**kw):
        low=datetime.strptime(params['time_from'],'%Y%m%dT%H%M').replace(tzinfo=timezone.utc)
        high=datetime.strptime(params['time_to'],'%Y%m%dT%H%M').replace(tzinfo=timezone.utc)+timedelta(minutes=1)
        feed=sorted([a for a in articles if low<=news._parse_av_timestamp(a['time_published'])<high],key=lambda a:a['time_published'])[:1000]
        capture=av.Capture.from_bytes('NEWS_SENTIMENT',av.safe_parameters(params),json.dumps({'feed':feed}).encode())
        return news.CapturedFeed(feed,capture,'gs://test/frozen')
    first=av.Run('fetch-news-sentiment','tickers')
    news.run_news_windows(first,[scope],'dummy',max_requests=1,executor=execute,fetcher=source)
    assert first.pending==2
    # A crashed claim is explicitly recoverable after its real lease expires.
    execute('SELECT * FROM av_claim_news_windows(CAST(:limits AS jsonb),:owner,1)',
            {'limits':av.canonical({scope['query_identity']:30}),'owner':'crashed'},read=True)
    execute("UPDATE av_catalyst_news_windows SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE lease_owner='crashed'",{})
    second=av.Run('fetch-news-sentiment','tickers')
    news.run_news_windows(second,[scope],'dummy',max_requests=30,executor=execute,fetcher=source)
    assert second.pending==0
    assert c.execute(text('SELECT count(*) FROM news_sentiment')).scalar()==1100
    assert any(g.get('coverage_complete') and g.get('complete_through') for g in second.groups)


def test_insider_full_scope_batched_capacity(monkeypatch):
    from gcp.fetchers import fetch_insider_transactions as insider
    source_calls=[];writes=[]
    native=[{'transaction_date':'2026-10-09','executive':str(i),'acquisition_or_disposal':'A',
             'shares':'10','share_price':'1.25','executive_title':None} for i in range(1000)]
    def source(function,parameters,key,**kw):
        source_calls.append(parameters['symbol'])
        return av.Capture.from_bytes(function,parameters,json.dumps({'data':native}).encode())
    monkeypatch.setattr(av,'fetch_capture',source)
    monkeypatch.setattr(av,'archive_capture',lambda c,**kw:'gs://test/'+c.observation_id)
    def write(table,rows,**kw):
        assert table=='insider_transactions'
        assert len(rows)<=10000 and len(kw['captures'])<=10 and len(kw['outcomes'])<=10
        assert len(av.canonical(rows).encode())<=16*1024*1024
        writes.append((len(rows),len(kw['captures'])))
        return len(rows)
    tickers=[f'T{i:03}' for i in range(300)]
    run=av.Run('fetch-insider-transactions','daily',expected=300)
    insider.run_insider(run,tickers,'dummy',writer=write)
    assert source_calls==tickers
    assert len(writes)==30
    assert sum(n for n,_ in writes)==300000
    assert run.rows_written==300000 and run.processed==300 and run.failed==0
    assert 300*2+30*4*2+30==870 <=3600/4


def test_mixed_failure_preserves_success_and_exits_nonzero(monkeypatch):
    from gcp.fetchers import fetch_insider_transactions as insider
    written=[]
    def source(ticker,key,**kw):
        if ticker=='BAD':
            raise av.SourceError('transport_failed')
        frame=pd.DataFrame([{'ticker':ticker,'transaction_date':'2026-10-09','executive':None,
                             'transaction_type':'A','shares':None,'share_price':None}])
        capture=av.Capture.from_bytes('INSIDER_TRANSACTIONS',{'symbol':ticker},b'{"data":[]}')
        frame.attrs.update(capture=capture,raw_uri='gs://test/source',skipped_future=0,source_count=1)
        return frame
    run=av.Run('fetch-insider-transactions','daily',expected=2)
    insider.run_insider(run,['GOOD','BAD'],'dummy',fetcher=source,writer=lambda table,rows,**kw:written.extend(rows))
    assert len(written)==1 and run.rows_written==1 and run.failed==1
    assert run.terminal(dry_run=True)==1


def test_universe_failure_is_not_valid_empty(monkeypatch):
    from gcp.fetchers import fetch_earnings_history as history
    from gcp import database
    monkeypatch.setattr(database,'query_to_dataframe_strict',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('db')))
    with pytest.raises(RuntimeError):
        history.resolve_refresh_universe('daily')
    monkeypatch.setattr(database,'query_to_dataframe_strict',lambda *a,**kw:pd.DataFrame())
    assert history.resolve_refresh_universe('daily').empty
