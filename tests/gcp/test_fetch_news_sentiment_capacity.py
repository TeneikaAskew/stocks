"""Actual streaming/parser/group I/O shape; vendor/SQL latency is an envelope."""
import json,math,time
from datetime import datetime,timedelta,timezone
import pytest
from gcp.fetchers import _av_ingestion as av
from gcp.fetchers import fetch_news_sentiment as news


@pytest.mark.parametrize('mode,cap',[('tickers',300),('earnings',300),('topics',30)])
def test_news_modes_io_shape_and_quarter_timeout_budget(monkeypatch,mode,cap):
    start=datetime(2026,10,9,tzinfo=timezone.utc)
    scopes=news.news_window_scopes([f'T{i:03}' for i in range(10)] if mode!='topics' else [],
                                  ['earnings'] if mode=='topics' else [],start,start+timedelta(minutes=1))
    native=[{'title':str(i),'url':None,'source':'wire','time_published':'20261009T000030',
             'ticker_sentiment':[{'ticker':f'E{j}','ticker_sentiment_score':'.2','relevance_score':'.8'} for j in range(4)]} for i in range(1000)]
    calls=[];writes=[];queries=[];paces=[];claimed=0
    # Instrument pacing rather than consuming119.6s of CI idle time; whole
    # transformed native payload and all actual call/group paths still run.
    monkeypatch.setattr(time,'sleep',paces.append)
    def execute(sql,params,**kw):
        nonlocal claimed
        queries.append(sql)
        if 'av_claim_news_windows' in sql:
            rows=[]
            for i in range(min(10,cap-claimed)):
                scope=scopes[(claimed+i)%len(scopes)]
                rows.append(dict(scope,window_id=f'00000000-0000-0000-0000-{claimed+i+1:012}'))
            claimed+=len(rows);return rows
        if 'av_complete_news_windows' in sql:
            rows=json.loads(params['rows']);captures=json.loads(params['captures'])
            assert len(rows)<=40000 and len(captures)<=10
            assert len(params['rows'].encode())<=64*1024*1024
            writes.append((len(rows),len(captures)))
        if 'first_gap' in sql:
            return [{'query_identity':s['query_identity'],'first_gap':start,'completed_end':None,'pending':1} for s in scopes]
        return []
    def source(params,**kw):
        calls.append(params)
        # First ten responses run the full40,000-row admitted group. Further
        # requests exercise complete mode I/O counts without redundant CPU.
        feed=[dict(article,title=str(len(calls))+'-'+article['title']) for article in native] if len(calls)<=10 else []
        body=json.dumps({'feed':feed}).encode()
        assert len(body)<=2_000_000
        capture=av.Capture.from_bytes('NEWS_SENTIMENT',av.safe_parameters(params),body)
        return news.CapturedFeed(feed,capture,'gs://ephemeral-test/'+capture.observation_id)
    began=time.monotonic()
    run=av.Run('fetch-news-sentiment',mode,expected=len(scopes))
    news.run_news_windows(run,scopes,'dummy',max_requests=cap,executor=execute,fetcher=source)
    elapsed=time.monotonic()-began
    assert len(calls)==cap and run.request_attempts==cap
    assert writes[0]==(40000,10) and len(writes)==math.ceil(cap/10)
    assert paces==[.4]*(cap-1)
    assert len(queries)==2+2*math.ceil(cap/10)  # seed,claims,writes,full-scope assessment
    assert run.pending==len(scopes) and run.status=='partial'
    assert all(p['sort']=='EARLIEST' and p['time_from'] and p['time_to'] for p in calls)
    planning=cap*(1+.4+.3+.3)+math.ceil(cap/10)*4*2+30
    assert planning<=900
    assert elapsed+sum(paces)+math.ceil(cap/10)*4*2+30<900
    assert run.rows_written==40000  # no silent output truncation in largest group
