import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def revision_db():
    # Never permit this migration/concurrency fixture to select production.
    if not os.environ.get("DB_HOST"):
        pytest.fail("mandatory integration collection requires explicit ephemeral PostgreSQL selectors")
    assert os.environ.get("DB_HOST") in {"127.0.0.1", "localhost"}
    assert os.environ.get("DB_NAME", "").startswith("av_") or (
        os.environ.get("GITHUB_ACTIONS")=="true" and os.environ.get("DB_NAME")=="trading"
        and os.environ.get("DB_USER")=="trading_user" and os.environ.get("DB_PASS")=="testpass")
    from gcp.database import _direct_db_url
    engine = create_engine(_direct_db_url())
    schema = "cat_test_" + uuid.uuid4().hex[:12]
    conn = engine.connect()
    conn.execute(text(f"CREATE SCHEMA {schema}")); conn.commit()
    conn.execute(text(f"SET search_path TO {schema}, public")); conn.commit()
    ddl = Path("gcp/schema.sql").read_text()
    original = ddl[ddl.index("CREATE TABLE IF NOT EXISTS earnings_history ("):ddl.index("-- BEGIN AV CATALYST REVISIONS")]
    conn.exec_driver_sql(original); conn.commit()
    conn.execute(text("INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps) VALUES ('AAPL','2026-06-30','2026-07-30',1.0)")); conn.commit()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.exec_driver_sql("SET search_path TO public"); conn.commit()
        conn.exec_driver_sql(f"DROP SCHEMA {schema} CASCADE"); conn.commit()
        conn.close(); engine.dispose()


def migration():
    sql = Path("gcp/schema.sql").read_text()
    return sql.split("-- BEGIN AV CATALYST REVISIONS", 1)[1].split("-- END AV CATALYST REVISIONS", 1)[0]


def test_migration_and_updates_preserve_observed_versions(revision_db):
    c = revision_db
    before = c.execute(text("SELECT clock_timestamp()")).scalar(); c.commit()
    c.exec_driver_sql(migration()); c.commit()
    seed = c.execute(text("SELECT known_at,availability_quality,source_retrieved_at FROM earnings_history_revisions")).one(); c.commit()
    assert seed.known_at >= before
    assert seed.availability_quality == "observed_legacy"
    assert seed.source_retrieved_at is None
    c.exec_driver_sql(migration()); c.commit()
    for value in [2.02, 2.02, 1.0]:
        c.execute(text("INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_eps,reported_date) VALUES ('AAPL','2026-06-30',:v,'2026-07-30') ON CONFLICT(ticker,fiscal_date_ending) DO UPDATE SET reported_eps=excluded.reported_eps,inserted_at=clock_timestamp()"), {"v": value}); c.commit()
    assert c.execute(text("SELECT payload->>'reported_eps' FROM earnings_history_revisions ORDER BY revision_id")).scalars().all() == ["1", "2.02", "1"]
    c.commit()
    with pytest.raises(Exception, match="append.only"):
        c.execute(text("DELETE FROM earnings_history_revisions"))
    c.rollback()


def test_revision_and_cache_rollback_together(revision_db):
    c = revision_db
    c.exec_driver_sql(migration()); c.commit()
    c.execute(text("UPDATE earnings_history SET reported_eps=2.02")); c.rollback()
    assert c.execute(text("SELECT reported_eps FROM earnings_history")).scalar() == 1
    assert c.execute(text("SELECT count(*) FROM earnings_history_revisions")).scalar() == 1
    c.commit()
    c.execute(text("UPDATE earnings_history SET reported_eps=2.02")); c.commit()
    assert c.execute(text("SELECT count(*) FROM earnings_history_revisions")).scalar() == 2


def test_actual_applier_installation_rollback_and_concurrent_upserts(revision_db):
    from concurrent.futures import ThreadPoolExecutor
    from gcp.apply_schema import split_statement_groups
    c=revision_db
    unit=split_statement_groups(migration())[0]
    # Genuine failed migration rolls back DDL, seed and trigger as one unit.
    with pytest.raises(Exception):
        for statement in unit:c.execute(text(statement))
        c.execute(text('SELECT definitely_missing_column FROM earnings_history'))
    c.rollback()
    assert c.execute(text("SELECT to_regclass('earnings_history_revisions')")).scalar() is None
    c.commit()
    for statement in unit:c.execute(text(statement))
    c.commit()
    schema=c.execute(text('SELECT current_schema()')).scalar();c.commit()
    engine=c.engine
    def upsert():
        with engine.begin() as worker:
            worker.execute(text(f'SET search_path TO {schema},public'))
            worker.execute(text("INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps) VALUES('MSFT','2026-06-30','2026-07-30',2.02) ON CONFLICT(ticker,fiscal_date_ending) DO UPDATE SET reported_eps=excluded.reported_eps"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in [pool.submit(upsert),pool.submit(upsert)]:result.result(timeout=5)
    assert c.execute(text("SELECT count(*) FROM earnings_history_revisions WHERE ticker='MSFT'")).scalar()==1
    assert c.execute(text("SELECT count(*) FROM earnings_history WHERE ticker='MSFT'")).scalar()==1


def test_full_candidate_schema_reapplies_in_fresh_ephemeral_database(revision_db):
    from gcp.apply_schema import split_statement_groups
    from gcp.database import _direct_db_url
    from sqlalchemy.engine import make_url
    from sqlalchemy import create_engine
    # Full schema has legacy information_schema queries assuming one schema;
    # use a genuinely fresh database, not duplicated private/public tables.
    name='av_cat_schema_'+uuid.uuid4().hex[:12]
    admin=revision_db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
    admin.exec_driver_sql(f'CREATE DATABASE {name}')
    url=make_url(_direct_db_url()).set(database=name)
    engine=create_engine(url)
    try:
        with engine.connect() as c:
            sql=Path('gcp/schema.sql').read_text()
            original=sql[sql.index('CREATE TABLE IF NOT EXISTS earnings_history ('):sql.index('-- BEGIN AV CATALYST REVISIONS')]
            c.exec_driver_sql(original);c.commit()
            c.execute(text("INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps) VALUES('AAPL','2026-06-30','2026-07-30',1)"));c.commit()
            for _ in range(2):
                for unit in split_statement_groups(sql):
                    for statement in unit:c.execute(text(statement))
                    c.commit()
            assert c.execute(text("SELECT count(*) FROM earnings_history_revisions WHERE ticker='AAPL'")).scalar()==1
            assert c.execute(text("SELECT reported_eps FROM earnings_history WHERE ticker='AAPL'")).scalar()==1
    finally:
        engine.dispose();admin.exec_driver_sql(f'DROP DATABASE {name} WITH (FORCE)');admin.close()


def test_actual_catalyst_api_reads_sql_cutoff_before_late_correction(revision_db,monkeypatch):
    import sys
    import pandas as pd
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    c=revision_db
    c.exec_driver_sql(migration());c.commit()
    # Explicit test vintage simulates a prior actually observed cache tuple;
    # the production seed remains real-clock and is never backdated by code.
    c.execute(text("""INSERT INTO earnings_history_revisions(ticker,fiscal_date_ending,known_at,availability_quality,payload,value_sha256)
      SELECT ticker,fiscal_date_ending,'2026-10-08T12:00:00Z','observed_cache',av_earnings_values(to_jsonb(e)),repeat('b',64) FROM earnings_history e"""));c.commit()
    c.execute(text('UPDATE earnings_history SET reported_eps=2.02'));c.commit()
    from lib import earnings_history
    def read(sql,params=None,**kw):
        result=c.execute(text(sql),params or {})
        frame=pd.DataFrame([dict(row) for row in result.mappings()]);c.commit();return frame
    monkeypatch.setattr(earnings_history,'query_to_dataframe_strict',read)
    sys.path.insert(0,str(Path('platform').resolve()))
    from api.routers import catalysts
    app=FastAPI();app.include_router(catalysts.router)
    with TestClient(app) as client:
        body=client.get('/api/catalysts/asof/AAPL?as_of=2026-10-08').json()
        assert float(body['earnings_history_recent'][0]['reported_eps'])==1
        assert body['knowledge_cutoff']=='2026-10-09T03:59:59.999999+00:00'
        assert body['availability']['news']['status']=='unavailable'
        old=client.get('/api/catalysts/asof/AAPL?as_of=2026-10-07').json()
        assert old['earnings_history_recent']==[] and old['availability']['earnings_history_recent']['status']=='unavailable'
    assert c.execute(text('SELECT reported_eps FROM earnings_history')).scalar()==2.02
