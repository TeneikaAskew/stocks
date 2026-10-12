from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text

from gcp.fetchers import _av_ingestion as av


def write(c,table,rows,final=False):
    frame=av.prepare_identity_frame(pd.DataFrame(rows),table)
    c.execute(text(av.identity_write_sql(table,final)), {"rows":av.canonical(frame.to_dict('records'))})
    c.commit()


def test_nullable_feed_replay_converges(catalyst_db):
    c=catalyst_db
    for table,row in [('news_sentiment',{'ticker':'AAPL','published_ts':datetime(2026,10,9,tzinfo=timezone.utc),
                                       'url':None,'title':'wire headline','source':'wire','sentiment_score':None}),
                      ('insider_transactions',{'ticker':'AAPL','transaction_date':'2026-10-09',
                                               'executive':None,'shares':None,'share_price':None,'transaction_type':'A'})]:
        write(c,table,[row]);write(c,table,[row])
        assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar()==1
        c.commit()
        c.exec_driver_sql(f"CREATE UNIQUE INDEX av_{table}_identity_unique ON {table}(source_identity_hash)");c.commit()
        c.execute(text("UPDATE av_catalyst_identity_migrations SET phase='final',old_writers_drained=true,checkpoint_at=clock_timestamp() WHERE table_name=:table"),{"table":table});c.commit()
        write(c,table,[row],True);write(c,table,[row],True)
        assert c.execute(text(f"SELECT count(*) FROM {table}")).scalar()==1
        c.commit()


def test_all_news_writers_replay_under_migrated_constraints(catalyst_db):
    c=catalyst_db
    # Actual writer preparation paths are added by this remediation; this
    # parametrized integration uses their one shared SQL identity contract.
    from gcp.fetchers.fetch_news_sentiment import prepare_news_rows
    from gcp.fetchers.fetch_rss_news import prepare_news_rows as rss_prepare
    from scripts.backfill_news_sentiment import prepare_news_rows as standalone_prepare
    from gcp.backfill_ticker import prepare_news_rows as ticker_prepare
    row={'ticker':'IWM','published_ts':datetime(2026,10,9,tzinfo=timezone.utc),'url':None,'title':'same','source':'wire'}
    for prepare in [prepare_news_rows,rss_prepare,standalone_prepare,ticker_prepare]:
        rows=prepare(pd.DataFrame([row])).to_dict('records')
        c.execute(text(av.identity_write_sql('news_sentiment',False)),{'rows':av.canonical(rows)});c.commit()
    assert c.execute(text("SELECT count(*) FROM news_sentiment")).scalar()==1


def test_staged_identity_migration_requires_drain_and_preserves_duplicate_evidence(catalyst_db):
    import pytest
    c=catalyst_db
    c.execute(text("INSERT INTO news_sentiment(ticker,published_ts,title,source) VALUES ('IWM','2026-10-09T12:00:00Z','headline','wire')"));c.commit()
    def execute(sql,params=None,read=False,**kw):
        r=c.execute(text(sql),params or {})
        result=[dict(row) for row in r.mappings()] if read else r.rowcount
        c.commit();return result
    result=av.backfill_identity_chunk('news_sentiment',executor=execute)
    assert result['changed_count']==1 and result['complete']
    required=['gcp.fetchers.fetch_news_sentiment','gcp.backfill_ticker','gcp.fetchers.fetch_rss_news','scripts.backfill_news_sentiment']
    manifest={'old_writers_drained':True,'verification_evidence_uri':'gs://test/verified',
              'writer_checks':{n:{'entrypoint_verified':True,'inactive_old_commands_blocked':True,
                                  'identity_contract':'av-source-identity/v1','source_commit':'a'*40,'image_digest':'sha256:'+'b'*64} for n in required}}
    with pytest.raises(av.SourceError,match='checkpoint'):
        av.finalize_identity('news_sentiment',dict(manifest,old_writers_drained=False),executor=execute)
    assert av.finalize_identity('news_sentiment',manifest,dry_run=True,executor=execute)['preflight']=='verified'
    c.execute(text("INSERT INTO news_sentiment(ticker,published_ts,title,source) VALUES ('IWM','2026-10-09T12:00:00Z','headline','wire')"));c.commit()
    av.backfill_identity_chunk('news_sentiment',executor=execute)
    with pytest.raises(av.SourceError,match='duplicate_reconciliation'):
        av.finalize_identity('news_sentiment',manifest,executor=execute)
    assert c.execute(text('SELECT count(*) FROM news_sentiment')).scalar()==2
