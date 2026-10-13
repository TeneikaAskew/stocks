import json
import pytest

from sqlalchemy import text

from gcp.fetchers import _av_ingestion as av
from gcp.fetchers import fetch_earnings_history as history
from gcp.fetchers import fetch_av_earnings_estimates as estimates


def executor(connection):
    def execute(sql,params=None,read=False,**kw):
        result=connection.execute(text(sql),params or {})
        answer=[dict(r) for r in result.mappings()] if read else result.rowcount
        connection.commit();return answer
    return execute


def test_actual_history_write_links_new_sources_without_financial_duplicates(catalyst_db,monkeypatch):
    c=catalyst_db
    monkeypatch.setattr(av,'archive_capture',lambda capture,**kw:'gs://test/'+capture.observation_id)
    for value in [1.0,2.02,2.02]:
        native={'symbol':'AAPL','quarterlyEarnings':[{'fiscalDateEnding':'2026-06-30','reportedDate':'2026-07-30','reportedEPS':str(value)}]}
        capture=av.Capture.from_bytes('EARNINGS',{'symbol':'AAPL'},json.dumps(native).encode())
        monkeypatch.setattr(av,'fetch_capture',lambda *a,**kw:capture)
        frame=history.fetch_history_for_ticker('AAPL','dummy',enrich_with_yahoo=False)
        assert history.persist_history(frame,executor=executor(c))==1
    assert c.execute(text('SELECT count(*) FROM earnings_history_revisions')).scalar()==2
    assert c.execute(text('SELECT count(*) FROM earnings_revision_observations')).scalar()==3
    assert c.execute(text('SELECT reported_eps FROM earnings_history')).scalar()==2.02


def test_actual_estimates_group_retains_full_native_payload_and_retry_identity(catalyst_db):
    c=catalyst_db
    native={'symbol':'AAPL','estimates':[{'date':'2026-12-31','horizon':'fiscal quarter',
                                        'eps_estimate_average':'2.05','native_extra':{'revision':'1.95'}}]}
    capture=av.Capture.from_bytes('EARNINGS_ESTIMATES',{'symbol':'AAPL'},json.dumps(native).encode())
    records=estimates.parse_estimates(capture)
    receipts=estimates.persist_estimate_group([(capture,'gs://expired/source',records)],executor=executor(c))
    retry=estimates.persist_estimate_group([(capture,'gs://expired/source',records)],executor=executor(c))
    assert retry[0]['known_at']==receipts[0]['known_at']
    assert c.execute(text('SELECT count(*) FROM av_earnings_estimates_observations')).scalar()==1
    payload=c.execute(text('SELECT payload FROM av_earnings_estimates_observations')).scalar()
    assert payload==native['estimates'][0]
    assert receipts[0]['status']=='validated'


@pytest.mark.parametrize('variant',['daily','weekly'])
def test_full_scope_manifests_reuse_verified_sources_and_require_acknowledgement(catalyst_db,monkeypatch,variant):
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    from gcp.fetchers import compute_earnings_reactions as reactions
    c=catalyst_db
    _prepare_estimates_cli(c,monkeypatch)
    execute=executor(c)
    monkeypatch.setattr(av,'isolated_sql',execute)
    day=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    for ticker in ['AAPL','MSFT']:
        native={'symbol':ticker,'quarterlyEarnings':[{'fiscalDateEnding':'2026-06-30','reportedDate':day,'reportedEPS':'1'}]}
        capture=av.Capture.from_bytes('EARNINGS',{'symbol':ticker},json.dumps(native).encode())
        monkeypatch.setattr(av,'fetch_capture',lambda *a,**kw:capture)
        monkeypatch.setattr(av,'archive_capture',lambda *a,**kw:'gs://test/frozen')
        history.persist_history(history.fetch_history_for_ticker(ticker,'dummy',enrich_with_yahoo=False),executor=execute)
    run=av.Run('fetch-earnings-history',variant,expected=1,processed=1)
    manifest=history.assess_history_manifest(run,['AAPL','MSFT'],executor=execute)
    assert not manifest['coverage_complete'] and manifest['event_cohort_complete']
    assert manifest['source_universe_unknown_count']==2 and manifest['complete_through'] is None
    assert manifest['requested_count']==2 and manifest['verified_count']==2
    assert len(manifest['configured_universe'])==2 and len(manifest['verified_events'])==2
    assert run.terminal(extra=manifest)==0
    predecessor=reactions.eligible_history_manifest(variant=variant)
    assert str(predecessor['manifest_id'])==manifest['source_manifest_id']
    # Stored post-ACK clock is stable on reconciliation of the same manifest.
    again=av.publish_manifest(run,predecessor['manifest'],manifest_id=str(predecessor['manifest_id']))
    assert again['source_manifest_known_at']==manifest['source_manifest_known_at']
    derived=reactions.publish_reactions_manifest(av.Run('compute-earnings-reactions',variant),predecessor,executor=execute)
    assert derived['pending_count']==2 and not derived['coverage_complete']
    assert derived['history_source_manifest_id']==manifest['source_manifest_id']
    # Neither an unacknowledged row nor a future publication may become eligible.
    c.execute(text("DELETE FROM av_catalyst_manifest_publications WHERE false"));c.commit()
    import uuid
    later=str(uuid.uuid4())
    c.execute(text("INSERT INTO av_catalyst_source_manifests VALUES(CAST(:id AS uuid),'fetch-earnings-history',:variant,'missing-ack',CAST(:payload AS jsonb))"),{'id':later,'variant':variant,'payload':av.canonical(dict(predecessor['manifest'],coverage_complete=False))});c.commit()
    assert str(reactions.eligible_history_manifest(variant=variant)['manifest_id'])==manifest['source_manifest_id']
    c.execute(text("INSERT INTO av_catalyst_manifest_publications VALUES(CAST(:id AS uuid),clock_timestamp()+interval '1 day')"),{'id':later});c.commit()
    assert str(reactions.eligible_history_manifest(variant=variant)['manifest_id'])==manifest['source_manifest_id']
    import pytest
    with pytest.raises(av.SourceError):reactions.eligible_history_manifest(variant='weekly' if variant=='daily' else 'daily')
    failed_run=av.Run('fetch-earnings-history',variant,failed=1)
    pending=history.assess_history_manifest(failed_run,['AAPL','MSFT'],executor=execute)
    assert failed_run.terminal(extra=pending)==1
    assert not pending['coverage_complete']
    with pytest.raises(av.SourceError):reactions.eligible_history_manifest(variant=variant)


def test_actual_yahoo_timing_change_has_independent_clock_and_attribution(catalyst_db,monkeypatch):
    import uuid
    from datetime import datetime,timezone
    c=catalyst_db
    native={'symbol':'AAPL','quarterlyEarnings':[{'fiscalDateEnding':'2026-06-30','reportedDate':'2026-07-30','reportedEPS':'1'}]}
    capture=av.Capture.from_bytes('EARNINGS',{'symbol':'AAPL'},json.dumps(native).encode())
    monkeypatch.setattr(av,'fetch_capture',lambda *a,**kw:capture)
    monkeypatch.setattr(av,'archive_capture',lambda *a,**kw:'gs://test/frozen')
    ids=[]
    for stamp in ['2026-07-30T08:00:00-04:00','2026-07-30T16:30:00-04:00']:
        payload={'rows':[{'timestamp':stamp,'values':{'EPS Estimate':1.2}}],
                 'columns':['EPS Estimate'],'index_timezone':'America/New_York'}
        observation={'observation_id':str(uuid.uuid4()),'ticker':'AAPL','source_retrieved_at':datetime.now(timezone.utc).isoformat(),
                     'library_version':'1.7.0','safe_parameters':{'symbol':'AAPL','limit':40},
                     'content_sha256':av.digest(payload),'payload':payload,'request_attempts':1}
        ids.append(observation['observation_id'])
        monkeypatch.setattr(history,'fetch_yahoo_observation',lambda *a,**kw:observation)
        history.persist_history(history.fetch_history_for_ticker('AAPL','dummy'),executor=executor(c))
    assert c.execute(text('SELECT count(*) FROM av_catalyst_source_captures')).scalar()==1
    assert c.execute(text('SELECT count(*) FROM earnings_timing_observations')).scalar()==2
    facts=c.execute(text("SELECT payload->>'reported_eps',payload->>'yahoo_report_time',yahoo_timing_observation_id FROM earnings_history_revisions ORDER BY revision_id")).all()
    assert [r[0] for r in facts]==['1','1']
    assert [r[1] for r in facts]==['pre-market','post-market']
    assert [str(r[2]) for r in facts]==ids
    assert c.execute(text('SELECT count(DISTINCT content_sha256) FROM earnings_timing_observations')).scalar()==2
    from gcp.fetchers import compute_earnings_reactions as reactions
    monkeypatch.setattr(av,'isolated_sql',executor(c))
    compact=reactions.fetch_earnings_history_for_tickers(['AAPL'],as_of=datetime.now(timezone.utc))
    assert len(compact)==1 and 'yahoo_timing_payload' not in compact.columns
    assert str(compact.iloc[0]['yahoo_timing_observation_id'])==ids[-1]
    timing=reactions.fetch_reaction_timing_observations(compact['yahoo_timing_observation_id'].tolist(),cutoff=datetime.now(timezone.utc))
    assert list(timing)==[ids[-1]] and timing[ids[-1]]['payload']['rows'][0]['timestamp']=='2026-07-30T16:30:00-04:00'


def _prepare_estimates_cli(connection,monkeypatch):
    import re
    from pathlib import Path
    ddl=Path('gcp/schema.sql').read_text()
    definition=re.search(r'^CREATE TABLE IF NOT EXISTS job_runs \(.*?^\);',ddl,re.M|re.S).group()
    connection.exec_driver_sql(definition);connection.commit()
    monkeypatch.setenv('AV_API_KEY','dummy')
    monkeypatch.setattr(av,'close_sql_worker',lambda:None)
    monkeypatch.setattr(estimates,'resolve_universe',lambda:['AAPL','EMPTY','PENDING'])
    def source(fn,params,*a,**kw):
        rows=[] if params['symbol']=='EMPTY' else [{'date':'2026-12-31','horizon':'fiscal quarter','eps_estimate_average':'2.05'}]
        return av.Capture.from_bytes(fn,params,av.canonical({'symbol':params['symbol'],'estimates':rows}).encode())
    monkeypatch.setattr(av,'fetch_capture',source)
    monkeypatch.setattr(av,'archive_capture',lambda c,**kw:'gs://ephemeral-test/'+c.observation_id)
    return executor(connection)


def test_actual_estimates_daily_writer_publishes_selected_receipts_and_pending_scope(catalyst_db,monkeypatch):
    c=catalyst_db
    execute=_prepare_estimates_cli(c,monkeypatch)
    monkeypatch.setattr(av,'isolated_sql',execute)
    assert estimates.main(['--max-tickers=2'])==1
    row=c.execute(text('SELECT m.job_name,m.variant,m.manifest,p.known_at FROM av_catalyst_source_manifests m JOIN av_catalyst_manifest_publications p USING(manifest_id)')).one()
    assert row.job_name=='fetch-av-earnings-estimates' and row.variant=='daily'
    manifest=row.manifest
    assert manifest['universe_count']==3 and manifest['selected_count']==2 and manifest['pending_count']==1
    assert not manifest['coverage_complete'] and manifest['selected_scope_hash']==av.digest(['AAPL','EMPTY'])
    receipts=manifest['captured_receipts']
    assert len(receipts)==2 and [r['status'] for r in receipts]==['validated','validated_empty']
    from datetime import datetime
    assert all(datetime.fromisoformat(r['source_retrieved_at'])<=datetime.fromisoformat(r['known_at'])<=row.known_at for r in receipts)
    assert c.execute(text('SELECT count(*) FROM av_earnings_estimates_observations')).scalar()==1
    assert c.execute(text("SELECT count(*) FROM av_earnings_estimates_observations WHERE ticker='EMPTY'")).scalar()==0
    assert c.execute(text("SELECT validation_status FROM av_catalyst_source_captures WHERE ticker='EMPTY'")).scalar()=='validated_empty'
    terminal=c.execute(text('SELECT note FROM job_runs')).scalar()
    terminal=json.loads(terminal)
    assert terminal['source_manifest_known_at']==av.clock_string(row.known_at) and terminal['pending_count']==1


def test_actual_estimates_uncertain_publication_never_certifies_availability(catalyst_db,monkeypatch):
    c=catalyst_db
    execute=_prepare_estimates_cli(c,monkeypatch)
    def uncertain(sql,params=None,**kw):
        if 'INSERT INTO av_catalyst_manifest_publications' in sql:raise av.SourceError('database_outcome_unavailable:deadline')
        return execute(sql,params,**kw)
    monkeypatch.setattr(av,'isolated_sql',uncertain)
    assert estimates.main(['--max-tickers=2'])==1
    assert c.execute(text('SELECT count(*) FROM av_catalyst_source_manifests')).scalar()==1
    assert c.execute(text('SELECT count(*) FROM av_catalyst_manifest_publications')).scalar()==0
    note=json.loads(c.execute(text('SELECT note FROM job_runs')).scalar())
    assert 'source_manifest_known_at' not in note and note['terminal_status']=='partial'
    assert c.execute(text('SELECT count(*) FROM av_earnings_estimates_observations')).scalar()==1


def test_history_manifest_refuses_unbacked_source_pointer(catalyst_db,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    c=catalyst_db
    day=datetime.now(ZoneInfo('America/New_York')).date()
    c.execute(text("""INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps,source_fetch_id,source_retrieved_at,raw_uri,raw_sha256)
      VALUES('AAPL','2026-06-30',:day,1,'00000000-0000-0000-0000-000000000001',clock_timestamp(),'gs://missing/source',repeat('a',64))"""),{'day':day});c.commit()
    execute=executor(c);monkeypatch.setattr(av,'isolated_sql',execute)
    result=history.assess_history_manifest(av.Run('fetch-earnings-history','daily'),['AAPL'],executor=execute)
    assert not result['coverage_complete'] and result['pending_count']==1


def test_manifest_identity_collision_cannot_relabel_acknowledged_scope(catalyst_db,monkeypatch):
    c=catalyst_db;monkeypatch.setattr(av,'isolated_sql',executor(c))
    run=av.Run('fetch-earnings-history','daily')
    manifest={'scope_hash':'a'*64,'coverage_complete':False}
    first=av.publish_manifest(run,manifest,manifest_id='00000000-0000-0000-0000-000000000001')
    with pytest.raises(av.SourceError,match='manifest_identity_conflict'):
        av.publish_manifest(run,dict(manifest,scope_hash='b'*64,coverage_complete=True),manifest_id=first['source_manifest_id'])


def test_daily_selector_fetches_new_report_after_prior_complete_quarter(catalyst_db,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    c=catalyst_db
    c.exec_driver_sql('CREATE TABLE earnings_calendar(ticker TEXT,earnings_date DATE)')
    c.exec_driver_sql('CREATE TABLE watchlists(ticker TEXT,removed_at TIMESTAMPTZ)')
    c.execute(text("INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps) VALUES('AAPL','2026-03-31','2026-04-30',1)"))
    c.execute(text('INSERT INTO earnings_calendar VALUES(:ticker,:day)'),{'ticker':'AAPL','day':datetime.now(ZoneInfo('America/New_York')).date()});c.commit()
    monkeypatch.setattr(av,'isolated_sql',executor(c))
    selected=history.resolve_refresh_universe('daily',30)
    assert selected.iloc[0]['needs_refresh']


@pytest.mark.parametrize('variant',['daily','weekly'])
def test_history_event_window_is_exactly_thirty_inclusive_dates(catalyst_db,monkeypatch,variant):
    from datetime import datetime,timedelta,timezone
    from zoneinfo import ZoneInfo
    c=catalyst_db;execute=executor(c)
    monkeypatch.setattr(av,'isolated_sql',execute)
    monkeypatch.setattr(av,'archive_capture',lambda capture,**kw:'gs://test/'+capture.observation_id)
    end=datetime.now(ZoneInfo('America/New_York')).date();start=end-timedelta(days=29)
    for ticker,day in [('FIRST',start),('OUTSIDE',start-timedelta(days=1)),('LAST',end)]:
        body={'symbol':ticker,'quarterlyEarnings':[{'fiscalDateEnding':'2026-06-30','reportedDate':day.isoformat(),'reportedEPS':'1'}]}
        capture=av.Capture.from_bytes('EARNINGS',{'symbol':ticker},av.canonical(body).encode())
        monkeypatch.setattr(av,'fetch_capture',lambda *a,**kw:capture)
        history.persist_history(history.fetch_history_for_ticker(ticker,'dummy',enrich_with_yahoo=False),executor=execute)
    manifest=history.assess_history_manifest(av.Run('fetch-earnings-history',variant),['FIRST','LAST','OUTSIDE'],executor=execute)
    assert manifest['source_window_start']==start.isoformat()
    assert manifest['source_window_end']==end.isoformat()
    assert manifest['expected_events']==[{'ticker':'FIRST','event_reported_date':start.isoformat()},
                                         {'ticker':'LAST','event_reported_date':end.isoformat()}]
    assert manifest['scope_hash']==av.digest(manifest['expected_events'])


@pytest.mark.parametrize('empty',[False,True])
def test_estimate_receipt_availability_follows_complete_source_ack(catalyst_db,empty):
    from datetime import datetime,timezone
    import time
    c=catalyst_db;ack=[]
    base=executor(c)
    def delayed(sql,params=None,**kw):
        result=base(sql,params,**kw)
        if 'av_earnings_estimates_observations' in sql:
            time.sleep(.03)
            ack.append(datetime.now(timezone.utc))
        return result
    rows=[] if empty else [{'date':'2026-12-31','horizon':'fiscal quarter','eps_estimate_average':'2.05'}]
    capture=av.Capture.from_bytes('EARNINGS_ESTIMATES',{'symbol':'AAPL'},av.canonical({'symbol':'AAPL','estimates':rows}).encode())
    records=estimates.parse_estimates(capture)
    first=estimates.persist_estimate_group([(capture,'gs://test/post-ack',records)],executor=delayed)[0]
    assert datetime.fromisoformat(first['known_at'])>=ack[0]
    second=estimates.persist_estimate_group([(capture,'gs://test/post-ack',records)],executor=delayed)[0]
    assert second['known_at']==first['known_at']
    receipt=c.execute(text('SELECT source_commit_acknowledged_at FROM av_estimate_receipt_publications')).scalar()
    assert receipt==datetime.fromisoformat(first['known_at'])
    if not empty:
        observed=c.execute(text('SELECT known_at FROM av_earnings_estimates_observations')).scalar()
        assert observed<receipt


def test_estimate_reader_requires_source_ack_and_matching_run_publication(catalyst_db,monkeypatch):
    from datetime import datetime,timezone
    import pandas as pd
    from lib import earnings_history as readers
    c=catalyst_db
    execute=_prepare_estimates_cli(c,monkeypatch)
    monkeypatch.setattr(av,'isolated_sql',execute)
    def read(sql,params,**kw):
        return pd.DataFrame(execute(sql,params,read=True))
    monkeypatch.setattr(readers,'query_to_dataframe_strict',read)
    native={'symbol':'AAPL','estimates':[{'date':'2026-12-31','horizon':'fiscal quarter','eps_estimate_average':'2.05'}]}
    capture=av.Capture.from_bytes('EARNINGS_ESTIMATES',{'symbol':'AAPL'},av.canonical(native).encode())
    receipt=estimates.persist_estimate_group([(capture,'gs://test/reader',estimates.parse_estimates(capture))],executor=execute)[0]
    proposed=c.execute(text('SELECT known_at FROM av_earnings_estimates_observations')).scalar()
    source_ack=datetime.fromisoformat(receipt['known_at'])
    between=proposed+(source_ack-proposed)/2
    assert readers.read_estimates_asof('AAPL',between)['status']=='unavailable'
    assert readers.read_estimates_asof('AAPL',datetime.now(timezone.utc))['status']=='unavailable'
    run=av.Run('fetch-av-earnings-estimates','daily',expected=1,processed=1,rows_written=1)
    manifest=av.publish_manifest(run,{'schema_version':'av_catalyst_run/v1','pipeline_scope':'estimates_daily',
        'scope_hash':av.manifest_digest(['AAPL']),'selected_scope_hash':av.manifest_digest(['AAPL']),
        'configured_universe':['AAPL'],'universe_count':1,'selected_count':1,'pending_count':0,
        'coverage_complete':True,'captured_receipts':[receipt]})
    assert readers.read_estimates_asof('AAPL',datetime.now(timezone.utc))['status']=='unavailable'
    assert run.terminal(extra=manifest)==0
    result=readers.read_estimates_asof('AAPL',datetime.now(timezone.utc))
    assert result['status']=='ok'
    assert result['records'][0]['known_at']>=source_ack
    assert result['records'][0]['observation_known_at']==proposed
    assert result['records'][0]['source_manifest_id']==manifest['source_manifest_id']


def test_full_manifest_has_bounded_terminal_reference(catalyst_db,monkeypatch,caplog):
    import logging
    c=catalyst_db
    execute=_prepare_estimates_cli(c,monkeypatch)
    monkeypatch.setattr(av,'isolated_sql',execute)
    universe=[f'S{i:04d}' for i in range(1239)]
    payload={'schema_version':'av_catalyst_run/v1','configured_universe':universe,'universe_count':1239,
        'scope_hash':av.manifest_digest(universe),'coverage_complete':False,'complete_through':None,
        'source_universe_unknown_count':1239,'full_current_cohort_status':'dependency_pending',
        'independent_expected_cohort_proof':None,
        'source_scope_proofs':[{'ticker':ticker,'state':'unknown','reason':'no_capture','capture_id':None,
            'source_retrieved_at':None,'function':None,'validation_status':None,'normalized_count':None,
            'raw_uri':None,'raw_sha256':None,'quarter_observations':[],
            'required_window_status':'not_assessed','required_window_reason':'required_source_cutoff_missing',
            'vendor_covered_through':None,'full_scope_reason':'independent_expected_cohort_proof_missing'} for ticker in universe]}
    run=av.Run('fetch-earnings-history','weekly',expected=1239,processed=100,pending=1139)
    published=av.publish_manifest(run,payload)
    with caplog.at_level(logging.INFO):assert run.terminal(extra=published)==1
    stored=c.execute(text('SELECT manifest FROM av_catalyst_source_manifests WHERE manifest_id=CAST(:id AS uuid)'),
        {'id':published['source_manifest_id']}).scalar()
    note_raw=c.execute(text('SELECT note FROM job_runs')).scalar()
    note=json.loads(note_raw)
    assert len(av.manifest_bytes(stored))>256*1024
    assert len(note_raw.encode())<=64*1024
    assert len(stored['source_scope_proofs'])==1239 and stored['configured_universe']==universe
    assert note['manifest_sha256']==av.manifest_digest(stored)
    assert note['manifest_bytes']==len(av.manifest_bytes(stored))
    assert 'configured_universe' not in note and 'source_scope_proofs' not in note
    assert any(record.message==note_raw for record in caplog.records)


@pytest.mark.parametrize('empty',[False,True])
def test_estimate_receipt_uncertain_ack_preserves_identity_and_requires_reconciliation(catalyst_db,empty):
    c=catalyst_db;execute=executor(c)
    rows=[] if empty else [{'date':'2026-12-31','horizon':'fiscal year','native_revision':'unchanged'}]
    capture=av.Capture.from_bytes('EARNINGS_ESTIMATES',{'symbol':'AAPL'},av.canonical({'symbol':'AAPL','estimates':rows}).encode())
    group=[(capture,'gs://test/reconcile',estimates.parse_estimates(capture))]
    def lost_ack(sql,params=None,**kw):
        answer=execute(sql,params,**kw)
        if 'INSERT INTO av_estimate_receipt_publications' in sql:raise av.SourceError('database_outcome_unavailable:deadline')
        return answer
    with pytest.raises(av.SourceError,match='database_outcome_unavailable'):
        estimates.persist_estimate_group(group,executor=lost_ack)
    clock=c.execute(text('SELECT source_commit_acknowledged_at FROM av_estimate_receipt_publications')).scalar()
    assert c.execute(text('SELECT count(*) FROM av_earnings_estimates_observations')).scalar()==len(rows)
    reconciled=estimates.persist_estimate_group(group,executor=execute)[0]
    assert reconciled['known_at']==av.clock_string(clock)
    assert reconciled['status']==('validated_empty' if empty else 'validated')
    with pytest.raises(av.SourceError,match='estimate_capture_identity_conflict'):
        estimates.persist_estimate_group([(capture,'gs://different/identity',group[0][2])],executor=execute)


def test_future_estimate_receipt_publication_is_not_replay_eligible(catalyst_db):
    from datetime import datetime,timedelta,timezone
    c=catalyst_db;execute=executor(c)
    capture=av.Capture.from_bytes('EARNINGS_ESTIMATES',{'symbol':'AAPL'},b'{"symbol":"AAPL","estimates":[]}')
    execute("INSERT INTO av_catalyst_source_captures SELECT * FROM jsonb_populate_recordset(NULL::av_catalyst_source_captures,CAST(:captures AS jsonb))",
        {'captures':av.canonical([av.capture_record(capture,'gs://test/future',0)])})
    execute("INSERT INTO av_estimate_receipt_publications VALUES(CAST(:id AS uuid),'AAPL','validated_empty',0,:clock)",
        {'id':capture.observation_id,'clock':datetime.now(timezone.utc)+timedelta(days=1)})
    with pytest.raises(av.SourceError,match='estimate_receipt_conflict_or_ack_unknown'):
        estimates.persist_estimate_group([(capture,'gs://test/future',[])],executor=execute)


@pytest.mark.parametrize('variant',['daily','weekly'])
def test_native_history_cli_retains_nullable_full_universe_without_global_certification(catalyst_db,monkeypatch,variant):
    from datetime import datetime,timezone
    import pandas as pd
    c=catalyst_db;execute=_prepare_estimates_cli(c,monkeypatch)
    universe=['AAPL','EMPTY','FAILED']+[f'S{i:04d}' for i in range(1236)]
    day=datetime.now(timezone.utc).astimezone(history.ET).date().isoformat()
    monkeypatch.setattr(av,'isolated_sql',execute)
    monkeypatch.setattr(history,'resolve_refresh_universe',lambda *a,**kw:pd.DataFrame({'ticker':universe,'needs_refresh':True}))
    monkeypatch.setattr(history.time_module,'sleep',lambda *a:None)
    def source(fn,params,*a,**kw):
        if params['symbol']=='FAILED':raise av.SourceError('transport_failed')
        rows=[] if params['symbol']=='EMPTY' else [{'fiscalDateEnding':'2026-06-30','reportedDate':day,'reportedEPS':'1'}]
        return av.Capture.from_bytes(fn,params,av.canonical({'symbol':params['symbol'],'quarterlyEarnings':rows}).encode())
    monkeypatch.setattr(av,'fetch_capture',source)
    assert history.main([f'--scope={variant}','--max-tickers=3','--no-yahoo','--no-backfill'])==1
    manifest=c.execute(text("SELECT manifest FROM av_catalyst_source_manifests WHERE job_name='fetch-earnings-history'")).scalar()
    assert manifest['configured_universe']==universe and manifest['universe_count']==1239
    assert manifest['selected_count']==3 and manifest['raw_refresh_pending']==1236
    assert not manifest['coverage_complete'] and manifest['complete_through'] is None
    assert manifest['independent_expected_cohort_proof'] is None
    assert manifest['full_current_cohort_status']=='dependency_pending'
    assert manifest['source_universe_unknown_count']==1239
    proofs={p['ticker']:p for p in manifest['source_scope_proofs']}
    assert len(proofs)==1239
    assert proofs['AAPL']['state']=='observed_snapshot' and proofs['AAPL']['capture_id']
    assert proofs['EMPTY']['validation_status']=='validated_empty' and proofs['EMPTY']['normalized_count']==0
    assert proofs['FAILED']['state']=='failed' and proofs['FAILED']['reason']=='retrieval_failed'
    assert proofs['S0000']['state']=='unknown' and proofs['S0000']['reason']=='no_capture'
    for ticker in ['FAILED','S0000']:
        assert all(proofs[ticker][key] is None for key in ['capture_id','source_retrieved_at','function','validation_status','normalized_count','raw_sha256','raw_uri'])
        assert proofs[ticker]['quarter_observations']==[]
    assert all(p['vendor_covered_through'] is None for p in proofs.values())
    assert c.execute(text('SELECT count(*) FROM av_catalyst_manifest_publications')).scalar()==1
    terminal=json.loads(c.execute(text("SELECT note FROM job_runs WHERE job_name='fetch-earnings-history'")).scalar())
    assert terminal['source_universe_unknown_count']==1239 and terminal['coverage_complete'] is False


@pytest.mark.parametrize('variant',['daily','weekly'])
def test_native_history_cli_reuses_observed_events_with_partial_raw_refresh(catalyst_db,monkeypatch,variant):
    from datetime import datetime,timezone
    import pandas as pd
    from gcp.fetchers import compute_earnings_reactions as reactions
    c=catalyst_db;execute=_prepare_estimates_cli(c,monkeypatch)
    universe=['AAPL','MSFT']+[f'S{i:04d}' for i in range(1237)]
    day=datetime.now(timezone.utc).astimezone(history.ET).date().isoformat()
    monkeypatch.setattr(av,'isolated_sql',execute)
    monkeypatch.setattr(history,'resolve_refresh_universe',lambda *a,**kw:pd.DataFrame({'ticker':universe,'needs_refresh':True}))
    monkeypatch.setattr(history.time_module,'sleep',lambda *a:None)
    calls=[]
    def source(fn,params,*a,**kw):
        calls.append(params['symbol'])
        rows=[{'fiscalDateEnding':'2026-06-30','reportedDate':day,'reportedEPS':'1'}] if params['symbol'] in {'AAPL','MSFT'} else []
        return av.Capture.from_bytes(fn,params,av.canonical({'symbol':params['symbol'],'quarterlyEarnings':rows}).encode())
    monkeypatch.setattr(av,'fetch_capture',source)
    assert history.main([f'--scope={variant}','--max-tickers=2','--no-yahoo','--no-backfill'])==1
    prior=reactions.eligible_history_manifest(variant=variant)
    prior_facts=prior['manifest']['observed_source_facts']
    assert history.main([f'--scope={variant}','--max-tickers=100','--no-yahoo','--no-backfill'])==1
    latest=reactions.eligible_history_manifest(variant=variant)
    m=latest['manifest']
    assert len(calls)==102 and len(set(calls))==102
    assert m['universe_count']==1239 and m['selected_count']==100 and m['raw_refresh_pending']==1139
    assert m['raw_refresh_status']=='partial' and m['event_pending_count']==0 and m['event_cohort_complete']
    assert m['observed_source_facts']==prior_facts and m['verified_count']==m['requested_count']==2
    assert m['source_universe_unknown_count']==1239 and not m['coverage_complete'] and m['complete_through'] is None
    assert m['independent_expected_cohort_proof'] is None and m['full_current_cohort_status']=='dependency_pending'
    assert all(p['vendor_covered_through'] is None for p in m['source_scope_proofs'])
    assert sum(p['state']=='observed_snapshot' for p in m['source_scope_proofs'])==102


@pytest.mark.parametrize('malformed',[False,True])
def test_native_calendar_archives_full_feed_before_business_selection(catalyst_db,monkeypatch,malformed):
    from scripts import fetch_earnings_calendar as calendar
    c=catalyst_db;execute=executor(c)
    monkeypatch.setenv('AV_API_KEY','dummy')
    body=b'symbol,name,reportDate,fiscalDateEnding,estimate,currency\nAAPL,Apple,2026-10-14,2026-09-30,2.1,USD\nMSFT,Microsoft,'+(b'bad-date' if malformed else b'2026-11-14')+b',2026-09-30,3.2,USD\n'
    capture=av.Capture.from_bytes('EARNINGS_CALENDAR',{'horizon':'3month'},body)
    archives=[]
    monkeypatch.setattr(av,'fetch_capture',lambda *a,**kw:capture)
    monkeypatch.setattr(av,'archive_capture',lambda captured,**kw:archives.append(captured.body) or 'gs://test/full-calendar')
    monkeypatch.setattr(av,'isolated_sql',execute)
    frame=calendar.fetch_alphavantage_earnings(scope='weekly')
    m=c.execute(text('SELECT manifest FROM av_catalyst_source_manifests')).scalar()
    assert archives==[body]
    assert m['native_csv_rows']==m['requested_count']==2
    assert m['verified_count']==(1 if malformed else 2) and m['pending_count']==int(malformed)
    assert m['source_digest_kind']=='raw_body_sha256' and m['source_digest']==capture.body_sha256
    assert m['source_window_start']=='2026-10-14' and m['source_window_end']==('2026-10-14' if malformed else '2026-11-14')
    assert m['coverage_complete'] is (not malformed)
    assert m['source_all_coverage']=='unavailable' and m['business_subset_coverage']=='not_assessed'
    business=frame.loc[frame['date']=='2026-10-14']
    assert len(business)==1 and m['native_csv_rows']==2
    assert c.execute(text('SELECT count(*) FROM av_catalyst_source_captures')).scalar()==1
    assert c.execute(text('SELECT count(*) FROM av_catalyst_manifest_publications')).scalar()==1


def test_reaction_artifact_identity_collision_rolls_back_derived_write(catalyst_db):
    from datetime import datetime,timezone
    from gcp.fetchers import compute_earnings_reactions as reactions
    from sqlalchemy.exc import DBAPIError
    c=catalyst_db;execute=executor(c)
    config={'rule_version':'earnings-reaction/v2','mode':'current_revision_analytics'}
    payload={'earnings':{'ticker':'AAPL','fiscal_date_ending':'2026-06-30'},'configuration':config}
    sha=av.digest(payload)
    execute('INSERT INTO earnings_reaction_input_artifacts VALUES(:sha,clock_timestamp(),CAST(:body AS jsonb))',
        {'sha':sha,'body':av.canonical({'wrong':'immutable identity'})})
    rows=[{'ticker':'AAPL','fiscal_date_ending':'2026-06-30','reported_date':'2026-07-30','input_artifact_sha256':sha}]
    with pytest.raises((DBAPIError,av.SourceError)):
        reactions.persist_reaction_group(rows,[{'artifact_sha256':sha,'captured_at':datetime.now(timezone.utc),'payload':payload}],executor=execute)
    c.rollback()
    assert c.execute(text('SELECT count(*) FROM earnings_reactions')).scalar()==0
    assert c.execute(text('SELECT payload FROM earnings_reaction_input_artifacts')).scalar()=={'wrong':'immutable identity'}


def test_native_news_three_hundred_calls_keep_full_sql_group_detail(catalyst_db,monkeypatch):
    import time
    from gcp.fetchers import fetch_news_sentiment as news
    c=catalyst_db;execute=_prepare_estimates_cli(c,monkeypatch)
    calls=[];statements=[]
    def source(fn,params,*a,**kw):
        calls.append(params)
        return av.Capture.from_bytes(fn,params,b'{"feed":[]}')
    def observed(sql,params=None,**kw):
        statements.append(sql)
        return execute(sql,params,**kw)
    monkeypatch.setattr(av,'fetch_capture',source)
    monkeypatch.setattr(av,'isolated_sql',observed)
    monkeypatch.setattr(time,'sleep',lambda *a:None)
    names=','.join(f'S{i:03d}' for i in range(300))
    outcome=news.main([f'--tickers={names}','--max-tickers=300','--max-requests=300',
        '--time-from=20261001T0000','--time-to=20261002T0000'])
    assert outcome==0,{'calls':len(calls),'statements':len(statements),'groups':[json.loads(n)['groups'] for n in c.execute(text('SELECT note FROM job_runs')).scalars()]}
    m=c.execute(text('SELECT manifest FROM av_catalyst_source_manifests')).scalar()
    note_raw=c.execute(text('SELECT note FROM job_runs')).scalar();note=json.loads(note_raw)
    assert len(calls)==300 and len(m['run_groups'])==600
    assert len(av.canonical(m['run_groups']).encode())>64*1024 and len(note_raw.encode())<=64*1024
    assert len([s for s in statements if 'INSERT INTO av_catalyst_source_manifests' in s])==1
    assert len([s for s in statements if 'INSERT INTO av_catalyst_manifest_publications' in s])==1
    assert len([s for s in statements if 'INSERT INTO job_runs' in s])==1
    assert note['manifest_sha256']==av.manifest_digest(m) and note['manifest_bytes']==len(av.manifest_bytes(m))
    assert note['processed']==300 and note['pending']==0 and note['terminal_status']=='no_data'
    assert c.execute(text('SELECT count(*) FROM av_catalyst_source_captures')).scalar()==300
    assert c.execute(text("SELECT count(*) FROM av_catalyst_news_windows WHERE status='complete'")).scalar()==300
    captures={str(r.capture_id):r.raw_sha256 for r in c.execute(text('SELECT capture_id,raw_sha256 FROM av_catalyst_source_captures'))}
    assert {g['source_capture_id'] for g in m['run_groups'] if 'source_capture_id' in g}==set(captures)
    assert all(g['raw_sha256']==captures[g['source_capture_id']] for g in m['run_groups'] if 'source_capture_id' in g)
