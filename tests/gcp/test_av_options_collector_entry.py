"""New actual main/process/normalizer controls; source and persistence boundaries fake."""
import sys,logging
from datetime import datetime,timezone
from types import SimpleNamespace
import pandas as pd
import pytest
from gcp.fetchers import _av_realtime_collector as m
from gcp.fetchers import fetch_av_realtime_options as api
FIXED=datetime(2026,10,27,14,0,tzinfo=timezone.utc)
KEY='FAKE_OFFLINE_OPTIONS_KEY';POISON=KEY+' apikey='+KEY

def raw_rows():
 return [{'contractID':'SYNTH_CALL' if side=='call' else 'SYNTH_PUT','type':side,'expiration':'2026-10-30','strike':'280','last':'1.20','bid':'1.10','ask':'1.30','mark':'1.20','volume':'12','open_interest':'100','implied_volatility':'0.35','delta':'0.50' if side=='call' else '-0.50','gamma':'0.02','theta':'-0.10','vega':'0.15','rho':'0.01'} for side in ['call','put']]

@pytest.fixture
def invoke(monkeypatch):
 from gcp.fetchers import evaluate_ew_strikes as ew
 monkeypatch.setenv('AV_API_KEY',KEY);monkeypatch.setattr(sys,'argv',['fetch_av_realtime_options','--tickers','SPY IWM QQQ'])
 monkeypatch.setattr(m,'_av_cfg',SimpleNamespace(delay_between_calls=0))
 def run(*,ack=2,fail=None,configured=True,now=FIXED,calendar='open',deadline_exhausted=False):
  calls=[];writes=[];committed={}
  class Clock(datetime):
   @classmethod
   def now(cls,tz=None):return now
  monkeypatch.setattr(m,'datetime',Clock)
  monkeypatch.setattr(m,'is_cloud_sql_configured',lambda:configured)
  def sessions(start,end):
   if calendar=='invalid':return pd.DataFrame({'wrong':[1]})
   if calendar=='closed':return pd.DataFrame(columns=['market_open','market_close'],index=pd.DatetimeIndex([]))
   day=pd.Timestamp(start)
   return pd.DataFrame({'market_open':[pd.Timestamp(str(start)+'T13:30:00Z')],'market_close':[pd.Timestamp(str(start)+'T20:00:00Z')]},index=pd.DatetimeIndex([day]))
  monkeypatch.setattr(ew,'nyse_sessions',sessions)
  def fetch(ticker,key,stamp,**kwargs):
   assert key==KEY;calls.append((ticker,stamp))
   if fail=='source' and ticker=='IWM':raise m.RealtimeOptionsUnavailable(POISON)
   if fail=='empty' and ticker=='IWM':raise m.RealtimeOptionsEmpty('synthetic eligible empty')
   return m._normalize_av_response(pd.DataFrame(raw_rows()),ticker,stamp)
  def upsert(df,table,keys):
   assert table=='etf_options_snapshots'
   assert keys==['ticker','snapshot_ts','option_type','expiration','strike']
   ticker=df['ticker'].iloc[0];writes.append((ticker,df.copy()))
   for _,r in df.iterrows():committed[tuple(r[k] for k in keys)]=r.to_dict()
   if ticker=='IWM':
    if fail=='commit_before_exception':raise RuntimeError(POISON)
    return ack
   return len(df)
  monkeypatch.setattr(m,'fetch_av_realtime_options',fetch);monkeypatch.setattr(m,'upsert_dataframe',upsert)
  if deadline_exhausted and hasattr(m,'_cli_transport'):
   def exhausted(*a,**k):raise m._cli_transport.SourceDeadline('source_deadline')
   monkeypatch.setattr(m._cli_transport,'pace',exhausted)
  try:r=api.main();code=0 if r is None else r
  except SystemExit as e:code=e.code
  return code,calls,writes,committed
 return run

@pytest.mark.parametrize('ack',[0,-1,True,None,1,2.0,3])
def test_scheduled_entry_rejects_bad_ack_without_replay(invoke,ack):
 code,calls,writes,store=invoke(ack=ack)
 assert code==1
 assert [t for t,_ in calls]==['SPY','IWM','QQQ'] and [t for t,_ in writes]==['SPY','IWM','QQQ']
 assert {k[0] for k in store}>={'SPY','QQQ'}
 assert len({t for _,t in calls})==1

def test_commit_before_exception_is_uncertain_not_replayed(invoke,caplog):
 caplog.set_level(logging.DEBUG);code,calls,writes,store=invoke(fail='commit_before_exception')
 assert code==1 and [t for t,_ in calls]==['SPY','IWM','QQQ']
 assert len(writes)==3 and {k[0] for k in store}=={'SPY','IWM','QQQ'}
 assert KEY not in caplog.text

def test_no_database_refuses_before_any_source_call(invoke):
 code,calls,writes,store=invoke(configured=False);assert code==1 and calls==writes==[] and store=={}

@pytest.mark.parametrize('when,calendar',[(datetime(2026,10,27,13,29,tzinfo=timezone.utc),'open'),(datetime(2026,10,27,20,0,tzinfo=timezone.utc),'open'),(datetime(2026,10,31,14,0,tzinfo=timezone.utc),'closed')])
def test_ineligible_session_is_noop_not_a_snapshot(invoke,when,calendar):
 code,calls,writes,store=invoke(now=when,calendar=calendar);assert code==0 and calls==writes==[] and store=={}

def test_unprovable_calendar_fails_closed(invoke):
 code,calls,writes,store=invoke(calendar='invalid');assert code==1 and calls==writes==[]

def test_source_error_does_not_replay_successful_siblings(invoke):
 code,calls,writes,store=invoke(fail='source');assert code==1 and [t for t,_ in calls]==['SPY','IWM','QQQ']
 assert [t for t,_ in writes]==['SPY','QQQ'] and {k[0] for k in store}=={'SPY','QQQ'}

def test_eligible_empty_keeps_existing_bounded_attempt_count(invoke):
 code,calls,writes,store=invoke(fail='empty');assert code==1
 assert [t for t,_ in calls].count('IWM')==m.EMPTY_RETRY_ATTEMPTS+1
 assert [t for t,_ in writes]==['SPY','QQQ']

def test_deadline_exhaustion_keeps_first_commit_and_makes_no_later_source_call(invoke):
 code,calls,writes,store=invoke(deadline_exhausted=True)
 assert code==1 and [t for t,_ in calls]==['SPY'] and [t for t,_ in writes]==['SPY']
 assert {k[0] for k in store}=={'SPY'}

def test_valid_batch_keeps_both_sides_and_one_source_clock(invoke):
 code,calls,writes,store=invoke();assert code==0 and len(calls)==len(writes)==3 and len(store)==6
 assert len({t for _,t in calls})==1
 for ticker,df in writes:
  assert set(df['option_type'])=={'calls','puts'}
  assert set(df['market_session'])=={'REALTIME'} and set(df['data_source'])=={'alphavantage'}

from datetime import datetime,timezone
from types import SimpleNamespace
import gcp.fetchers.fetch_av_realtime_options as api
import gcp.fetchers._av_realtime_collector as collector

def test_existing_entry_delegates_exactly_once(monkeypatch):
 calls=[];monkeypatch.setattr(collector,'main',lambda:calls.append('collector'))
 api.main();assert calls==['collector']

def test_API_import_fetch_retains_existing_request_path(monkeypatch):
 seen=[]
 def get(url,**kw):seen.append((url,kw));return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'endpoint':'Realtime Options','message':'success','data':raw_rows()})
 monkeypatch.setattr(api.requests,'get',get)
 def forbidden(*a,**kw):raise AssertionError('API fetch must not invoke CLI transport/signals')
 monkeypatch.setattr(collector._cli_transport,'decoded_json',forbidden)
 df=api.fetch_av_realtime_options('IWM','FAKE_OFFLINE_ONLY',datetime(2026,10,27,14,tzinfo=timezone.utc))
 assert len(df)==2 and len(seen)==1
 assert seen[0][1]=={'params':{'function':'REALTIME_OPTIONS','symbol':'IWM','require_greeks':'true','apikey':'FAKE_OFFLINE_ONLY','datatype':'json'},'timeout':60}
 assert api._normalize_av_response is collector._normalize_av_response


@pytest.mark.parametrize("now,calendar,configured,expected_code,expected_calls", [
 (FIXED, "open", True, 0, 3),
 (datetime(2026, 12, 25, 15, tzinfo=timezone.utc), "closed", True, 0, 0),
 (datetime(2026, 10, 31, 14, tzinfo=timezone.utc), "closed", True, 0, 0),
 (datetime(2026, 10, 27, 13, 29, tzinfo=timezone.utc), "open", True, 0, 0),
 (FIXED, "open", False, 1, 0),
 (FIXED, "invalid", True, 1, 0),
], ids=["regular", "holiday", "weekend", "premarket", "missing-db", "unknown-calendar"])
def test_scheduled_entry_admits_only_due_configured_sessions(
    invoke, now, calendar, configured, expected_code, expected_calls
):
 code, calls, writes, committed = invoke(now=now, calendar=calendar, configured=configured)
 assert code == expected_code
 assert len(calls) == len(writes) == expected_calls
 assert len(committed) == expected_calls * 2


def test_scheduled_entry_delegates_without_changing_threaded_api(monkeypatch):
 from concurrent.futures import ThreadPoolExecutor
 import hashlib
 from pathlib import Path
 # Accepted transport is carried byte-for-byte; API normalization is shared.
 assert hashlib.sha256(Path(collector._cli_transport.__file__).read_bytes()).hexdigest() == 'af238d07c2043a0d34319dd533f6e36842e68a9ff536c37d9700e859de117284'
 assert api._normalize_av_response is collector._normalize_av_response
 delegated = []
 monkeypatch.setattr(collector, 'main', lambda: delegated.append('collector'))
 api.main()
 assert delegated == ['collector']
 seen = []
 def get(url, **kwargs):
  seen.append(kwargs)
  return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
   'endpoint': 'Realtime Options', 'message': 'success', 'data': raw_rows()})
 monkeypatch.setattr(api.requests, 'get', get)
 def forbidden(*args, **kwargs):
  raise AssertionError('Threaded API must not enter collector signals/transport')
 monkeypatch.setattr(collector._cli_transport, 'decoded_json', forbidden)
 with ThreadPoolExecutor(max_workers=1) as pool:
  result = pool.submit(api.fetch_av_realtime_options, 'IWM', 'FAKE_OFFLINE_ONLY', FIXED).result(timeout=5)
 assert len(result) == 2 and len(seen) == 1
 assert seen[0] == {'params': {'function': 'REALTIME_OPTIONS', 'symbol': 'IWM',
  'require_greeks': 'true', 'apikey': 'FAKE_OFFLINE_ONLY', 'datatype': 'json'}, 'timeout': 60}
 assert delegated == ['collector']


@pytest.fixture
def options_postgres_engine():
 """Explicit opt-in owned socket only; CI supplies its ephemeral engine below."""
 import os
 from pathlib import Path
 from sqlalchemy import create_engine
 from sqlalchemy.engine import URL
 socket = os.environ.get('OPTIONS_TEST_PG_SOCKET')
 if socket is None:
  pytest.skip('real durability is run by tests/integration/test_options_collector_durability.py')
 assert socket == '/workspace/options-collector-pg-socket'
 assert Path(socket, '.s.PGSQL.5432').is_socket()
 engine = create_engine(URL.create('postgresql+psycopg2', username='postgres',
  database='options_fixture', query={'host': socket}),
  connect_args={'options': '-c statement_timeout=5000 -c lock_timeout=2000'})
 try:
  yield engine
 finally:
  engine.dispose()


def test_scheduled_entry_preserves_sibling_commit_on_later_failure(monkeypatch, options_postgres_engine):
 """Actual SQL commit and separate-connection read after later source deadline."""
 from pathlib import Path
 from sqlalchemy import text
 from gcp import database as db
 from gcp.fetchers import evaluate_ew_strikes as ew
 engine = options_postgres_engine
 with engine.begin() as conn:
  database, address = conn.execute(text('SELECT current_database(), inet_server_addr()')).one()
  assert (database == 'options_fixture' and address is None) or (
   database == 'trading' and engine.url.host in {'localhost', '127.0.0.1', '::1'})
  sql = Path(__file__).resolve().parents[2].joinpath('gcp/schema.sql').read_text()
  start = sql.index('CREATE TABLE IF NOT EXISTS etf_options_snapshots (')
  conn.execute(text(sql[start:sql.index('\n);', start) + 3]))
  conn.execute(text('TRUNCATE etf_options_snapshots RESTART IDENTITY'))
 monkeypatch.setattr(db, '_REFLECTED_TABLES', {})
 monkeypatch.setattr(db, 'get_engine', lambda: engine)
 monkeypatch.setattr(collector, 'upsert_dataframe', db.upsert_dataframe)
 monkeypatch.setenv('AV_API_KEY', KEY)
 monkeypatch.setattr(sys, 'argv', ['fetch_av_realtime_options', '--tickers', 'SPY IWM QQQ'])
 monkeypatch.setattr(collector, 'is_cloud_sql_configured', lambda: True)
 class Clock(datetime):
  @classmethod
  def now(cls, tz=None): return FIXED
 monkeypatch.setattr(collector, 'datetime', Clock)
 monkeypatch.setattr(ew, 'nyse_sessions', lambda start, end: pd.DataFrame({
  'market_open': [pd.Timestamp('2026-10-27T13:30:00Z')],
  'market_close': [pd.Timestamp('2026-10-27T20:00:00Z')]},
  index=pd.DatetimeIndex([pd.Timestamp('2026-10-27')])))
 calls = []
 def fetch(ticker, key, stamp, **kwargs):
  calls.append(ticker)
  return collector._normalize_av_response(pd.DataFrame(raw_rows()), ticker, stamp)
 monkeypatch.setattr(collector, 'fetch_av_realtime_options', fetch)
 def expired(*args, **kwargs):
  raise collector._cli_transport.SourceDeadline('source_deadline')
 monkeypatch.setattr(collector._cli_transport, 'pace', expired)
 with pytest.raises(SystemExit) as failure:
  api.main()
 assert failure.value.code == 1 and calls == ['SPY']
 # A separate engine/physical connection cannot see uncommitted writer-local rows.
 from sqlalchemy import create_engine
 from sqlalchemy.pool import NullPool
 reader_engine = create_engine(engine.url, poolclass=NullPool)
 try:
  with reader_engine.connect() as reader:
   rows = reader.execute(text('SELECT ticker, option_type, snapshot_ts FROM etf_options_snapshots ORDER BY option_type LIMIT 10')).all()
 finally:
  reader_engine.dispose()
 assert len(rows) == 2
 assert {r.ticker for r in rows} == {'SPY'}
 assert {r.option_type for r in rows} == {'calls', 'puts'}
 assert all(r.snapshot_ts == FIXED for r in rows)
