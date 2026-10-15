"""Mandatory real PostgreSQL producer scope, fair queues and frontier tests."""
import json
from datetime import datetime,timedelta,timezone
import pytest
from sqlalchemy import text
from gcp.fetchers import _av_ingestion as av

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




def test_minimum_minute_saturation_remains_explicitly_blocked(catalyst_db):
    from gcp.fetchers import fetch_news_sentiment as news
    from tests.integration.test_av_catalyst_producer_writes import executor
    c=catalyst_db;execute=executor(c)
    start=datetime(2026,10,9,tzinfo=timezone.utc)
    scopes=news.news_window_scopes(['IWM'],[],start,start+timedelta(minutes=1))
    feed=[{'time_published':'20261009T000030','ticker_sentiment':[]} for _ in range(1000)]
    capture=av.Capture.from_bytes('NEWS_SENTIMENT',{'tickers':'IWM'},av.canonical({'feed':feed}).encode())
    run=av.Run('fetch-news-sentiment','tickers')
    news.run_news_windows(run,scopes,'dummy',max_requests=1,executor=execute,
                         fetcher=lambda *a,**kw:news.CapturedFeed(feed,capture,'gs://ephemeral/raw'))
    assert run.pending==1
    assert c.execute(text('SELECT status FROM av_catalyst_news_windows')).scalar()=='blocked_vendor_granularity'
    assert c.execute(text('SELECT count(*) FROM av_catalyst_news_windows')).scalar()==1
