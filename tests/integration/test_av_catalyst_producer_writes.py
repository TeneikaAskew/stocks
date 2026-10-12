import json

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


def test_full_scope_manifests_reuse_verified_sources_and_require_acknowledgement(catalyst_db,monkeypatch):
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    from gcp.fetchers import compute_earnings_reactions as reactions
    c=catalyst_db
    execute=executor(c)
    monkeypatch.setattr(av,'isolated_sql',execute)
    day=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    for ticker in ['AAPL','MSFT']:
        native={'symbol':ticker,'quarterlyEarnings':[{'fiscalDateEnding':'2026-06-30','reportedDate':day,'reportedEPS':'1'}]}
        capture=av.Capture.from_bytes('EARNINGS',{'symbol':ticker},json.dumps(native).encode())
        monkeypatch.setattr(av,'fetch_capture',lambda *a,**kw:capture)
        monkeypatch.setattr(av,'archive_capture',lambda *a,**kw:'gs://test/frozen')
        history.persist_history(history.fetch_history_for_ticker(ticker,'dummy',enrich_with_yahoo=False),executor=execute)
    run=av.Run('fetch-earnings-history','daily',expected=1,processed=1)
    manifest=history.assess_history_manifest(run,['AAPL','MSFT'],executor=execute)
    assert manifest['coverage_complete'] and manifest['requested_count']==2 and manifest['verified_count']==2
    assert len(manifest['configured_universe'])==2 and len(manifest['verified_events'])==2
    predecessor=reactions.eligible_history_manifest(variant='daily')
    assert str(predecessor['manifest_id'])==manifest['source_manifest_id']
    # Stored post-ACK clock is stable on reconciliation of the same manifest.
    again=av.publish_manifest(run,predecessor['manifest'],manifest_id=str(predecessor['manifest_id']))
    assert again['source_manifest_known_at']==manifest['source_manifest_known_at']
    derived=reactions.publish_reactions_manifest(av.Run('compute-earnings-reactions','daily'),predecessor,executor=execute)
    assert derived['pending_count']==2 and not derived['coverage_complete']
    assert derived['history_source_manifest_id']==manifest['source_manifest_id']
    # Neither an unacknowledged row nor a future publication may become eligible.
    c.execute(text("DELETE FROM av_catalyst_manifest_publications WHERE false"));c.commit()
    import uuid
    later=str(uuid.uuid4())
    c.execute(text("INSERT INTO av_catalyst_source_manifests VALUES(CAST(:id AS uuid),'fetch-earnings-history','daily','missing-ack',CAST(:payload AS jsonb))"),{'id':later,'payload':av.canonical(dict(predecessor['manifest'],coverage_complete=False))});c.commit()
    assert str(reactions.eligible_history_manifest(variant='daily')['manifest_id'])==manifest['source_manifest_id']
    c.execute(text("INSERT INTO av_catalyst_manifest_publications VALUES(CAST(:id AS uuid),clock_timestamp()+interval '1 day')"),{'id':later});c.commit()
    assert str(reactions.eligible_history_manifest(variant='daily')['manifest_id'])==manifest['source_manifest_id']
    import pytest
    with pytest.raises(av.SourceError):reactions.eligible_history_manifest(variant='weekly')
    pending=history.assess_history_manifest(av.Run('fetch-earnings-history','daily',failed=1),['AAPL','MSFT'],executor=execute)
    assert not pending['coverage_complete']
    with pytest.raises(av.SourceError):reactions.eligible_history_manifest(variant='daily')


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
    assert terminal['source_manifest_known_at']==row.known_at.isoformat() and terminal['pending_count']==1


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
