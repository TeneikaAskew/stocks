import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def revision_db():
    # Never permit this migration/concurrency fixture to select production.
    if not os.environ.get("DB_HOST"):
        pytest.skip("requires explicit ephemeral PostgreSQL selectors")
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
