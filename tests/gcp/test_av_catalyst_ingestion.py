from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from gcp.fetchers import _av_ingestion as av
from datetime import datetime,timedelta,timezone
import json


def test_terminal_note_includes_source_watermark_and_attempts(monkeypatch):
    monkeypatch.setenv("CLOUD_RUN_TASK_ATTEMPT", "2")
    run = av.Run("fetch-news-sentiment", "daily", expected=3, failed=1, processed=2, rows_written=5, request_attempts=3, application_retries=1)
    run.groups = [{"source_event_max": "2026-10-08T15:00:00+00:00", "complete_through": None, "coverage_complete": False, "cursor_before": None, "cursor_after": None}]
    note = run.note()
    assert note["terminal_status"] == "partial"
    assert note["task_attempt"] == "2"
    assert note["application_retry_count"] == 1
    assert note["groups"][0]["coverage_complete"] is False


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
    monkeypatch.setattr(av,'read_dataframe',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('db')))
    with pytest.raises(RuntimeError):
        history.resolve_refresh_universe('daily')
    monkeypatch.setattr(av,'read_dataframe',lambda *a,**kw:pd.DataFrame())
    assert history.resolve_refresh_universe('daily').empty


def test_group_commit_failure_does_not_certify_news_frontier():
    from gcp.fetchers import fetch_news_sentiment as news
    start=datetime(2026,10,9,tzinfo=timezone.utc)
    scopes=news.news_window_scopes(['IWM'],[],start,start+timedelta(minutes=1))
    def execute(sql,params,**kw):
        if 'av_claim_news_windows' in sql:return [dict(scopes[0],window_id='00000000-0000-0000-0000-000000000001')]
        if 'av_complete_news_windows' in sql:raise av.SourceError('sql_deadline')
        return []
    capture=av.Capture.from_bytes('NEWS_SENTIMENT',{'tickers':'IWM'},b'{"feed":[]}')
    run=av.Run('fetch-news-sentiment','tickers')
    with pytest.raises(av.SourceError):
        news.run_news_windows(run,scopes,'dummy',max_requests=1,executor=execute,
          fetcher=lambda *a,**kw:news.CapturedFeed([],capture,'gs://test/raw'))
    assert run.processed==0 and run.rows_written==0
    assert all(not g['coverage_complete'] and g.get('complete_through') is None for g in run.groups)


def test_estimates_failed_group_is_not_reused_as_oversized_group(monkeypatch):
    from gcp.fetchers import fetch_av_earnings_estimates as estimates
    monkeypatch.setenv('AV_API_KEY','dummy')
    runs=[];groups=[]
    monkeypatch.setattr(av.Run,'terminal',lambda self,**kw:runs.append(self) or (1 if self.failed else 0))
    monkeypatch.setattr(av,'claim_work',lambda fn,universe,*a,**kw:universe)
    monkeypatch.setattr(av,'close_sql_worker',lambda:None)
    monkeypatch.setattr(av,'fetch_capture',lambda fn,params,*a,**kw:av.Capture.from_bytes(fn,params,av.canonical({'symbol':params['symbol'],'estimates':[]}).encode()))
    monkeypatch.setattr(av,'archive_capture',lambda *a,**kw:'gs://test/raw')
    def persist(group):
        groups.append(len(group))
        if len(groups)==1:raise av.SourceError('sql_deadline')
        return [{'ticker':c.parameters['symbol'],'source_retrieved_at':c.retrieved_at.isoformat(),'fetch_id':c.observation_id} for c,_,_ in group]
    monkeypatch.setattr(estimates,'persist_estimate_group',persist)
    monkeypatch.setattr(av,'finish_work',lambda *a,**kw:None)
    monkeypatch.setattr(av,'publish_manifest',lambda run,m:m)
    assert estimates.main(['--tickers',','.join(f'T{i:02}' for i in range(11))])==1
    assert groups==[10,1]
    assert runs[0].failed==10 and runs[0].processed==1


def test_rss_and_standalone_actual_source_paths_preserve_nullable_identity(monkeypatch):
    from gcp.fetchers import fetch_rss_news as rss
    from scripts import backfill_news_sentiment as standalone
    stamp=datetime(2026,10,9,tzinfo=timezone.utc)
    frame=rss.build_dataframe([{'ticker':'IWM','published_ts':stamp,'url':None,'title':'same','source':'wire'}])
    assert len(frame)==1 and frame.iloc[0]['url'] is None
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'feed':[{'time_published':'20261009T000000','url':None,'title':'same','source':'wire',
                                      'ticker_sentiment':[{'ticker':'IWM'}]}]}
    monkeypatch.setattr(standalone.requests,'get',lambda *a,**kw:Response())
    rows=standalone.fetch_av_news('IWM','dummy')
    assert len(rows)==1 and rows[0]['url'] is None and rows[0]['sentiment_score'] is None


def test_failed_weekly_head_does_not_starve_universe(monkeypatch):
    """Actual caller passes the full denominator to the fair DB claim function;
    integration/test_av_catalyst_scope_coverage proves SQL rotation itself."""
    names=[f'T{i:03}' for i in range(150)]
    seen=[]
    def read(sql,params,**kw):
        seen.append(params)
        assert 'av_claim_catalyst_work' in sql and kw['read']
        return [{'ticker':t} for t in names[100:]]
    monkeypatch.setattr(av,'isolated_sql',read)
    assert av.claim_work('EARNINGS',names,'weekly','test-owner',limit=100)==names[100:]
    assert seen[0]['tickers']==names and seen[0]['limit']==100


def test_saturated_news_subdivisions_eventually_advance_watermark():
    """Actual adapter forwards saturation+capture/lease identity to durable SQL;
    real subdivision/restart/frontier proof is in the integration collection."""
    from gcp.fetchers import fetch_news_sentiment as news
    start=datetime(2026,10,9,tzinfo=timezone.utc)
    scope=news.news_window_scopes(['IWM'],[],start,start+timedelta(minutes=1))[0]
    capture=av.Capture.from_bytes('NEWS_SENTIMENT',{'tickers':'IWM'},b'{"feed":[]}')
    outcomes=[]
    def execute(sql,params,**kw):
        if 'av_claim_news_windows' in sql:return [dict(scope,window_id='00000000-0000-0000-0000-000000000001')]
        if 'av_complete_news_windows' in sql:outcomes.extend(json.loads(params['outcomes']))
        if 'first_gap' in sql:return [{'query_identity':scope['query_identity'],'first_gap':start,'completed_end':None,'pending':1}]
        return []
    feed=[{'time_published':'20261009T000030','ticker_sentiment':[]} for _ in range(1000)]
    run=av.Run('fetch-news-sentiment','tickers')
    news.run_news_windows(run,[scope],'dummy',max_requests=1,executor=execute,
                         fetcher=lambda *a,**kw:news.CapturedFeed(feed,capture,'gs://ephemeral/raw'))
    assert outcomes[0]['saturated'] and outcomes[0]['capture_id']==capture.observation_id
    assert outcomes[0]['lease_owner']==run.execution_name
    assert run.pending==1 and not run.groups[0]['coverage_complete']


@pytest.mark.parametrize('module,args',[
 ('gcp.fetchers.fetch_earnings_history',['--tickers=IWM','--dry-run','--no-yahoo','--no-backfill']),
 ('gcp.fetchers.fetch_av_earnings_estimates',['--tickers=IWM','--dry-run']),
 ('gcp.fetchers.fetch_news_sentiment',['--tickers=IWM','--dry-run']),
 ('gcp.fetchers.fetch_insider_transactions',['--tickers=IWM','--dry-run']),
])
def test_actual_module_cli_dry_run_has_no_storage_writes(module,args):
    import subprocess,sys,os
    code='''import os,sys,runpy
from gcp.fetchers import _av_ingestion as av
os.environ['AV_API_KEY']='dummy'
def source(fn,parameters,key,**kw):
    data={'symbol':parameters.get('symbol','IWM')}
    data.update({'quarterlyEarnings':[]} if fn=='EARNINGS' else {'estimates':[]} if fn=='EARNINGS_ESTIMATES' else {'feed':[]} if fn=='NEWS_SENTIMENT' else {'data':[]})
    return av.Capture.from_bytes(fn,parameters,av.canonical(data).encode())
av.fetch_capture=source
def forbidden(*a,**kw):raise AssertionError('SQLwrite-or-network-read-in-explicit-dry-scope')
av.isolated_sql=forbidden
sys.argv=[sys.argv[1],*sys.argv[2:]]
runpy.run_module(sys.argv[0],run_name='__main__')
'''
    env=dict(os.environ)
    for key in ['CLOUD_SQL_CONNECTION_NAME','CLOUD_SQL_URL','GOOGLE_APPLICATION_CREDENTIALS','CLOUD_RUN_JOB','SOURCE_COMMIT','SOURCE_IMAGE_DIGEST']:
        env.pop(key,None)
    result=subprocess.run([sys.executable,'-c',code,module,*args],env=env,text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'dummy' not in result.stdout+result.stderr
