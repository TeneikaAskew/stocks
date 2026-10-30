"""Native CLI outcome regressions; synthetic fixtures, no live provider or SQL."""
import socket, sys
import pytest, requests
from gcp.fetchers import fetch_news_sentiment as news

@pytest.fixture(autouse=True)
def deny_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("live HTTP or SQL forbidden")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(news, "query_to_dataframe", forbidden)
    monkeypatch.setattr(news, "upsert_dataframe", forbidden)

def article(ticker):
 return {'title':'synthetic offline article','url':'https://example.invalid/offline','time_published':'20261027T120000','ticker_sentiment':[{'ticker':ticker,'ticker_sentiment_score':'0.0','relevance_score':'1.0'}]}

@pytest.fixture
def run_entry(monkeypatch):
 calls=[];writes=[]
 monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('NETWORK FORBIDDEN'))
 monkeypatch.setenv('AV_API_KEY','FAKE_OFFLINE_ONLY');monkeypatch.setattr(sys,'argv',['fetch_news_sentiment','--tickers','SPY,QQQ'])
 monkeypatch.setattr(news,'persist_to_cloud_sql',lambda df:(writes.append(df.copy()),len(df))[1])
 def run(payloads):
  def get(*args,**kwargs):
   calls.append(kwargs['params']['tickers']);payload=payloads[len(calls)-1]
   if isinstance(payload,Exception):raise payload
   class Response:
    def raise_for_status(self):pass
    def json(self):return payload
   return Response()
  monkeypatch.setattr(requests,'get',get)
  try:ret=news.main();exit_code=0 if ret is None else ret
  except SystemExit as e:exit_code=e.code
  except Exception as e:exit_code=type(e).__name__
  return exit_code,calls,writes
 return run

@pytest.mark.parametrize('error',[{'Information':'synthetic provider notice'},{'Note':'synthetic provider notice'},{'Error Message':'synthetic invalid request'},{},{'feed':None},TimeoutError('synthetic offline timeout')])
def test_all_failed_sources_exit_nonzero(run_entry,error):
 code,calls,writes=run_entry([error,error])
 assert calls==['SPY','QQQ'];assert writes==[]
 assert code!=0,'all provider/schema/transport failures must not exit successfully'

def test_mixed_failure_preserves_successful_sibling_and_exits_nonzero(run_entry):
 code,calls,writes=run_entry([{'feed':[article('SPY')]},{'Error Message':'synthetic invalid request'}])
 assert calls==['SPY','QQQ'];assert len(writes)==1;assert writes[0]['ticker'].tolist()==['SPY']
 assert code!=0,'committing a successful sibling must not conceal the failed source'

def test_malformed_first_body_does_not_drop_later_sibling(run_entry):
 code,calls,writes=run_entry([[],{'feed':[article('QQQ')]}])
 assert calls==['SPY','QQQ'],'schema failure must be isolated per source'
 assert len(writes)==1;assert writes[0]['ticker'].tolist()==['QQQ'];assert code!=0

def test_valid_empty_is_success_without_writes(run_entry):
 code,calls,writes=run_entry([{'feed':[]},{'feed':[]}]);assert code==0;assert calls==['SPY','QQQ'];assert writes==[]

def test_valid_nonempty_preserves_both_sources_and_neutral_score(run_entry):
 code,calls,writes=run_entry([{'feed':[article('SPY')]},{'feed':[article('QQQ')]}]);assert code==0;assert len(writes)==1
 assert writes[0]['ticker'].tolist()==['SPY','QQQ'];assert writes[0]['sentiment_score'].tolist()==[0.0,0.0]


import logging,sys
from types import SimpleNamespace
import pytest,requests
from gcp.fetchers import fetch_news_sentiment as n
KEY='FAKE-ONLY-NEVER-A-CREDENTIAL'
POISON='https://example.invalid/query?apikey='+KEY+' Authorization: Bearer '+KEY

def safety_article():
 return {'title':'offline','url':'https://example.invalid/article','time_published':'20261027T120000','ticker_sentiment':[{'ticker':'SPY','ticker_sentiment_score':'0.0'}]}

@pytest.mark.parametrize('payload,kind',[
 ({},'schema'),({'feed':None},'schema'),({'feed':{}},'schema'),({'feed':''},'schema'),([], 'schema'),(None,'schema'),
 ({'feed':[None]},'schema'),({'feed':[{}]},'schema'),({'feed':[{'time_published':POISON}]},'schema'),
 ({'Information':POISON,'feed':[safety_article()]},'provider_information'),({'Note':POISON},'provider_note'),({'Error Message':POISON},'provider_error'),
])
def test_error_envelopes_are_not_feeds_or_sensitive_logs(monkeypatch,caplog,payload,kind):
 calls=[]
 def get(url,**kwargs):calls.append((url,kwargs));return SimpleNamespace(raise_for_status=lambda:None,json=lambda:payload,headers={'Authorization':POISON})
 monkeypatch.setattr(requests,'get',get);caplog.set_level(logging.DEBUG)
 outcome=n._fetch({'function':'NEWS_SENTIMENT','apikey':KEY})
 assert (outcome.state,outcome.error_kind,outcome.feed)==('error',kind,())
 assert len(calls)==1
 assert KEY not in caplog.text and 'apikey=' not in caplog.text and 'Authorization' not in caplog.text
 assert KEY not in repr(outcome)

@pytest.mark.parametrize('stage,kind',[('dispatch','transport'),('http','http'),('json','json')])
def test_transport_http_json_failures_never_retry_or_reflect_poison(monkeypatch,caplog,stage,kind):
 calls=[]
 def fail():raise RuntimeError(POISON)
 def get(url,**kwargs):
  calls.append(1)
  if stage=='dispatch':fail()
  return SimpleNamespace(raise_for_status=fail if stage=='http' else lambda:None,json=fail if stage=='json' else lambda:{'feed':[]})
 monkeypatch.setattr(requests,'get',get);caplog.set_level(logging.DEBUG)
 outcome=n._fetch({'function':'NEWS_SENTIMENT','apikey':KEY})
 assert outcome.error_kind==kind and len(calls)==1 and outcome.feed==()
 assert KEY not in caplog.text and 'apikey=' not in caplog.text

def test_complete_request_and_one_attempt_are_preserved(monkeypatch):
 seen=[]
 def get(url,**kwargs):seen.append((url,kwargs));return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[]})
 monkeypatch.setattr(requests,'get',get)
 b=n.fetch_by_tickers(['SPY'],KEY,1000,time_from='20261026T0000',time_to='20261027T1600')
 assert b.frame.empty and b.outcomes[0].state=='empty'
 assert seen==[(n.AV_BASE_URL,{'params':{'function':'NEWS_SENTIMENT','tickers':'SPY','limit':1000,'apikey':KEY,'time_from':'20261026T0000','time_to':'20261027T1600','sort':'EARLIEST'},'timeout':30})]

@pytest.mark.parametrize('ack',[0,-1,True,None,1.0,2,RuntimeError(POISON)])
def test_ambiguous_or_exceptional_ack_is_failure_without_replay(monkeypatch,caplog,ack):
 calls=[];writes=[]
 monkeypatch.setenv('AV_API_KEY',KEY);monkeypatch.setattr(sys,'argv',['news','--tickers','SPY'])
 monkeypatch.setattr(requests,'get',lambda *a,**k:(calls.append(1),SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[safety_article()]}))[1])
 def persist(df):
  writes.append(df.copy())
  if isinstance(ack,Exception):raise ack
  return ack
 monkeypatch.setattr(n,'persist_to_cloud_sql',persist);caplog.set_level(logging.DEBUG)
 with pytest.raises(SystemExit) as e:n.main()
 assert e.value.code==1 and len(writes)==1 and len(calls)==1
 assert KEY not in caplog.text and 'apikey=' not in caplog.text

def test_duplicate_rows_keep_existing_upsert_identity(monkeypatch):
 writes=[];monkeypatch.setenv('AV_API_KEY',KEY);monkeypatch.setattr(sys,'argv',['news','--tickers','SPY'])
 monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[safety_article(),safety_article()]}))
 monkeypatch.setattr(n,'persist_to_cloud_sql',lambda df:(writes.append(df.copy()),len(df))[1]);n.main()
 assert len(writes)==1 and len(writes[0])==1
 assert writes[0][['ticker','published_ts','url']].notna().all().all()

def test_topics_and_ticker_source_failures_preserve_prior_sibling(monkeypatch):
 seen=[];writes=[];monkeypatch.setenv('AV_API_KEY',KEY);monkeypatch.setattr(sys,'argv',['news','--tickers','SPY','--topics','technology'])
 def get(*a,**k):
  seen.append(k['params'])
  return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[safety_article()]} if 'tickers' in k['params'] else {'Note':POISON})
 monkeypatch.setattr(requests,'get',get);monkeypatch.setattr(n,'persist_to_cloud_sql',lambda df:(writes.append(df.copy()),len(df))[1])
 with pytest.raises(SystemExit) as e:n.main()
 assert e.value.code==1 and len(seen)==2 and len(writes)==1 and writes[0]['ticker'].tolist()==['SPY']

def test_unconfigured_database_is_not_acknowledged_as_success(monkeypatch):
 calls=[];monkeypatch.setenv('AV_API_KEY',KEY);monkeypatch.setattr(sys,'argv',['news','--tickers','SPY'])
 monkeypatch.setattr(requests,'get',lambda *a,**k:(calls.append(1),SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[safety_article()]}))[1])
 monkeypatch.setattr(n,'is_cloud_sql_configured',lambda:False)
 with pytest.raises(SystemExit) as e:n.main()
 assert e.value.code==1 and len(calls)==1

def test_one_malformed_member_refuses_whole_source_feed(monkeypatch):
 monkeypatch.setattr(requests,'get',lambda *a,**k:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'feed':[safety_article(),None]}))
 outcome=n._fetch({'function':'NEWS_SENTIMENT','apikey':KEY})
 assert (outcome.state,outcome.error_kind,outcome.feed)==('error','schema',())

@pytest.mark.parametrize('status',[429,503])
def test_http_status_failures_are_terminal_single_attempt(monkeypatch,caplog,status):
 calls=[]
 def fail():raise requests.HTTPError(POISON)
 def get(*a,**kw):calls.append(1);return SimpleNamespace(status_code=status,raise_for_status=fail,json=lambda:pytest.fail('HTTP error body must not be consumed'))
 monkeypatch.setattr(requests,'get',get);caplog.set_level(logging.DEBUG)
 outcome=n._fetch({'function':'NEWS_SENTIMENT','apikey':KEY})
 assert (outcome.state,outcome.error_kind,outcome.feed)==('error','http',()) and len(calls)==1
 assert KEY not in caplog.text and 'apikey=' not in caplog.text


def test_topic_transform_failure_does_not_persist_a_successful_prefix(monkeypatch):
    bad = safety_article()
    bad["overall_sentiment_score"] = 10 ** 400  # valid JSON integer, cannot convert to float
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: (calls.append(1), SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"feed": [safety_article(), bad]},
    ))[1])
    batch = n.fetch_by_topics(["technology"], KEY, 1000)
    assert batch.outcomes[0].state == "error"
    assert batch.frame.empty
    assert calls == [1]


def test_earnings_lookup_exception_is_not_reflected_in_diagnostics(monkeypatch, caplog):
    def fail(*args, **kwargs):
        raise RuntimeError(POISON)
    monkeypatch.setattr(n, "query_to_dataframe", fail)
    caplog.set_level(logging.DEBUG)
    assert n._earnings_calendar_tickers(7) == []
    assert KEY not in caplog.text and "apikey=" not in caplog.text
