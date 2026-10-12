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
    estimates.persist_estimate_group([(capture,'gs://expired/source',records)],executor=executor(c))
    assert c.execute(text('SELECT count(*) FROM av_earnings_estimates_observations')).scalar()==1
    payload=c.execute(text('SELECT payload FROM av_earnings_estimates_observations')).scalar()
    assert payload==native['estimates'][0]
    assert receipts[0]['status']=='validated'
