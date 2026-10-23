from datetime import datetime,timezone,timedelta
import pytest
from gcp.fetchers import _av_ingestion as av


def test_manifest_retry_returns_actual_acknowledged_publication(monkeypatch):
    stored=datetime(2026,10,1,tzinfo=timezone.utc)
    calls=[]
    def sql(query,params,**kw):
        calls.append(query)
        return [{'manifest_id':params['id']}] if 'INSERT INTO av_catalyst_source_manifests' in query else [{'known_at':stored}]
    monkeypatch.setattr(av,'isolated_sql',sql)
    run=av.Run('fetch-earnings-history','daily')
    result=av.publish_manifest(run,{'coverage_complete':True},manifest_id='00000000-0000-0000-0000-000000000001')
    assert result['source_manifest_known_at']==av.clock_string(stored)
    assert 'RETURNING known_at' in calls[-1]


def test_failed_manifest_ack_never_emits_availability(monkeypatch):
    def fail(*a,**kw):raise av.SourceError('sql_deadline')
    monkeypatch.setattr(av,'isolated_sql',fail)
    with pytest.raises(av.SourceError):av.publish_manifest(av.Run('fetch-earnings-history','daily'),{})


def test_daily_manifest_links_full_assessed_scope_and_acknowledged_sources(monkeypatch):
    """Producer-adapter shape; matching immutable joins also run in real SQL."""
    from gcp.fetchers import fetch_earnings_history as history,compute_earnings_reactions as reactions
    clock=datetime(2026,10,9,12,tzinfo=timezone.utc)
    run=av.Run('fetch-earnings-history','daily',started_at=clock,expected=1,processed=1)
    queried=[]
    def assess(sql,params,**kw):
        queried.append((sql,params))
        return [{'partitions':[{'ticker':ticker,'capture_id':f'00000000-0000-0000-0000-{i:012d}',
                 'source_retrieved_at':clock,'function':'EARNINGS','validation_status':'validated',
                 'normalized_count':1,'raw_sha256':'a'*64,'raw_uri':'gs://test/source','quarter_observations':[],
                 'event_facts':[{'ticker':ticker,'reported_date':clock.date().isoformat(),'revision_id':i,'known_at':clock,
                   'observation_known_at':clock,'capture_id':f'00000000-0000-0000-0000-{i:012d}',
                   'source_retrieved_at':clock,'validation_status':'validated',
                   'reported_eps':'1','coherent_cache':True,'availability_quality':'source_verified',
                   'yahoo_timing_observation_id':None}]} for i,ticker in enumerate(['AAPL','MSFT'],1)]}]
    monkeypatch.setattr(av,'publish_manifest',lambda run,m:dict(m,source_manifest_id='00000000-0000-0000-0000-000000000001',source_manifest_known_at=clock.isoformat()))
    manifest=history.assess_history_manifest(run,['AAPL','MSFT'],executor=assess)
    assert run.expected==1 and manifest['requested_count']==manifest['verified_count']==2
    assert manifest['universe_count']==2 and not manifest['coverage_complete'] and manifest['event_cohort_complete']
    assert manifest['source_universe_unknown_count']==2 and manifest['complete_through'] is None
    assert queried[0][1]['universe']==['AAPL','MSFT']
    assert "c.function='EARNINGS'" in queried[0][0] and 'source_retrieved_at<=:cutoff' in queried[0][0]
    parent={'manifest':manifest,'manifest_id':manifest['source_manifest_id'],'known_at':clock,'execution_name':run.execution_name}
    def derived(sql,params,**kw):
        assert 'r.source_revision_id=e.revision_id' in sql
        assert params['history_known_at']==clock
        import json
        assert len(json.loads(params['events']))==2
        return [{'ticker':'AAPL','event_reported_date':clock.date(),'source_revision_id':1,
                 'input_artifact_sha256':'a'*64,'configuration_sha256':'b'*64},
                {'ticker':'MSFT','event_reported_date':clock.date(),'source_revision_id':None,
                 'input_artifact_sha256':None,'configuration_sha256':None}]
    result=reactions.publish_reactions_manifest(av.Run('compute-earnings-reactions','daily'),parent,executor=derived)
    assert result['history_source_manifest_id']==manifest['source_manifest_id']
    assert result['scope_hash']==manifest['scope_hash'] and result['pending_count']==1
    assert not result['coverage_complete']


def test_manifest_oversize_refuses_before_publication(monkeypatch):
    called=[]
    monkeypatch.setattr(av,'isolated_sql',lambda *a,**kw:called.append(a))
    with pytest.raises(av.SourceError,match='manifest_byte_limit'):
        av.publish_manifest(av.Run('fetch-earnings-history','weekly'),{'proof':'x'*(8*1024*1024)})
    assert not called


def test_full_manifest_has_bounded_terminal_reference(monkeypatch,caplog):
    import json,logging
    from datetime import datetime,timezone
    calls=[]
    def execute(sql,params=None,read=False,**kw):
        calls.append((sql,params))
        if 'WITH inserted' in sql:return [{'manifest_id':params['id']}]
        if 'WITH published' in sql:return [{'known_at':params['known']}]
        return 1
    monkeypatch.setattr(av,'isolated_sql',execute)
    payload={'schema_version':'av_catalyst_run/v1','configured_universe':[f'S{i:04d}' for i in range(1239)],
             'source_scope_proofs':[{'ticker':f'S{i:04d}','state':'unknown','reason':'no_capture','capture_id':None,
                                    'raw_uri':None,'raw_sha256':None,'quarter_observations':[]} for i in range(1239)],
             'universe_count':1239,'scope_hash':'a'*64,'coverage_complete':False,'source_universe_unknown_count':1239}
    run=av.Run('fetch-earnings-history','weekly',pending=1139,processed=100)
    published=av.publish_manifest(run,payload)
    with caplog.at_level(logging.INFO):assert run.terminal(extra=published)==1
    stored=json.loads(next(p['note'] for sql,p in calls if 'INSERT INTO job_runs' in sql))
    assert len(av.canonical(stored).encode())<=64*1024
    assert 'source_scope_proofs' not in stored and 'configured_universe' not in stored
    assert stored['manifest_sha256']==av.digest(payload)
    assert stored['manifest_bytes']==len(av.canonical(payload).encode())
    assert stored['source_manifest_id']==published['source_manifest_id']
    assert any(record.message==av.canonical(stored) for record in caplog.records)
    sql_manifest=json.loads(next(p['manifest'] for sql,p in calls if 'WITH inserted' in sql))
    assert len(sql_manifest['source_scope_proofs'])==1239


def test_canonical_scope_vectors_are_byte_exact_and_typed():
    import json
    from pathlib import Path
    for vector in json.loads(Path('tests/fixtures/av_catalyst_scope_vectors.json').read_text()):
        assert av.manifest_bytes(vector['input']).hex()==vector['canonical_utf8_hex']
        assert av.manifest_digest(vector['input'])==vector['sha256']
    for value in [float('nan'),float('inf'),1.0,2**63,{1:'wrong-key'}]:
        with pytest.raises(av.SourceError):av.manifest_bytes(value)
    with pytest.raises(av.SourceError):av.parse_manifest_json('{"x":1,"x":2}')


def test_optional_terminal_detail_is_omitted_before_failing_required_projection(monkeypatch):
    calls=[]
    monkeypatch.setattr(av,'isolated_sql',lambda sql,params,**kw:calls.append(params) or 1)
    run=av.Run('fetch-av-earnings-estimates','daily',processed=1,rows_written=1,
               metrics={'oversized_optional':'x'*(70*1024)})
    assert run.terminal(extra={'source_manifest_id':'00000000-0000-0000-0000-000000000001',
        'manifest_sha256':'a'*64,'manifest_bytes':10})==0
    import json
    note=json.loads(calls[0]['note'])
    assert note['source_manifest_id'] and note['optional_details_omitted_count']>0
    assert len(calls[0]['note'].encode())<=64*1024


def test_required_terminal_overflow_fails_with_small_controlled_note(monkeypatch):
    calls=[]
    monkeypatch.setattr(av,'isolated_sql',lambda sql,params,**kw:calls.append(params) or 1)
    run=av.Run('fetch-earnings-history','weekly',execution_name='x'*(70*1024))
    assert run.terminal(extra={'source_manifest_id':'00000000-0000-0000-0000-000000000001'})==1
    assert len(calls[0]['note'].encode())<=4*1024


def test_future_publication_clock_cannot_certify_replayed_manifest(monkeypatch):
    def execute(sql,params,**kw):
        if 'WITH inserted' in sql:return [{'manifest_id':params['id']}]
        return [{'known_at':datetime.now(timezone.utc)+timedelta(days=1)}]
    monkeypatch.setattr(av,'isolated_sql',execute)
    with pytest.raises(av.SourceError,match='publication_clock'):
        av.publish_manifest(av.Run('fetch-earnings-history','daily'),{})


def test_maximum_news_group_note_retains_full_sql_details_and_bounded_terminal(monkeypatch):
    import json
    calls=[]
    def execute(sql,params=None,**kw):
        calls.append((sql,params))
        if 'WITH inserted' in sql:return [{'manifest_id':params['id']}]
        if 'WITH published' in sql:return [{'known_at':params['known']}]
        return 1
    monkeypatch.setattr(av,'isolated_sql',execute)
    run=av.Run('fetch-news-sentiment','tickers',expected=300,attempted=300,processed=300,rows_written=300)
    run.groups=[{'query_identity':f'{i:064x}','requested_source_window':['2026-10-01T00:00:00+00:00','2026-10-02T00:00:00+00:00'],
        'source_event_max':'2026-10-01T23:00:00+00:00','complete_through':'2026-10-02T00:00:00+00:00',
        'coverage_complete':True,'cursor_before':'2026-10-01T00:00:00+00:00','cursor_after':'2026-10-02T00:00:00+00:00',
        'saturated':False} for i in range(300)]
    assert len(av.canonical(run.note()).encode())>64*1024
    assert run.terminal()==0
    manifest=json.loads(next(p['manifest'] for sql,p in calls if 'WITH inserted' in sql))
    note=json.loads(next(p['note'] for sql,p in calls if 'INSERT INTO job_runs' in sql))
    assert len(manifest['run_groups'])==300 and manifest['run_groups']==run.groups
    assert note['manifest_sha256']==av.manifest_digest(manifest)
    assert len(av.canonical(note).encode())<=64*1024 and 'groups' not in note
    assert av.clock_string('2026-10-12T08:00:00-04:00')=='2026-10-12T12:00:00.000000Z'
    with pytest.raises(av.SourceError):av.clock_string('2026-10-12T12:00:00')
    assert av.symbol_scope(['msft',' AAPL ','AAPL'])==['AAPL','MSFT']
