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
    assert result['source_manifest_known_at']==stored.isoformat()
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
        return [{'ticker':ticker,'reported_date':clock.date(),'revision_id':i,'known_at':clock,
                 'reported_eps':'1','coherent_cache':True,'availability_quality':'source_verified',
                 'yahoo_timing_observation_id':None} for i,ticker in enumerate(['AAPL','MSFT'],1)]
    monkeypatch.setattr(av,'publish_manifest',lambda run,m:dict(m,source_manifest_id='00000000-0000-0000-0000-000000000001',source_manifest_known_at=clock.isoformat()))
    manifest=history.assess_history_manifest(run,['AAPL','MSFT'],executor=assess)
    assert run.expected==1 and manifest['requested_count']==manifest['verified_count']==2
    assert manifest['universe_count']==2 and manifest['coverage_complete']
    assert queried[0][1]['universe']==['AAPL','MSFT']
    assert "c.function='EARNINGS'" in queried[0][0] and 'source_retrieved_at<=:cutoff' in queried[0][0]
    parent={'manifest':manifest,'manifest_id':manifest['source_manifest_id'],'known_at':clock,'execution_name':run.execution_name}
    def derived(sql,params,**kw):
        assert 'r.source_revision_id=e.revision_id' in sql
        assert params['history_known_at']==clock
        import json
        assert len(json.loads(params['events']))==2
        return [{'ticker':'AAPL','event_reported_date':clock.date(),'source_revision_id':1},
                {'ticker':'MSFT','event_reported_date':clock.date(),'source_revision_id':None}]
    result=reactions.publish_reactions_manifest(av.Run('compute-earnings-reactions','daily'),parent,executor=derived)
    assert result['history_source_manifest_id']==manifest['source_manifest_id']
    assert result['scope_hash']==manifest['scope_hash'] and result['pending_count']==1
    assert not result['coverage_complete']
