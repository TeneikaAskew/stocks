from datetime import datetime, timezone

from sqlalchemy import text


def test_estimate_vintages_survive_refresh_and_raw_expiry(catalyst_db):
    c = catalyst_db
    for i, eps in enumerate([1, 2]):
        fetch = f"00000000-0000-0000-0000-00000000000{i+1}"
        c.execute(text("""INSERT INTO av_catalyst_source_captures VALUES(CAST(:id AS uuid),'EARNINGS_ESTIMATES','AAPL',clock_timestamp(),'gs://fake/source',repeat('a',64),'{}','validated',1)"""), {"id": fetch}); c.commit()
        c.execute(text("""INSERT INTO av_earnings_estimates_observations VALUES(CAST(:id AS uuid),CAST(:id AS uuid),'AAPL','2026-12-31','fiscal quarter',clock_timestamp(),clock_timestamp(),'gs://expired/source',repeat('a',64),jsonb_build_object('eps',CAST(:eps AS integer))) ON CONFLICT(fetch_id,ticker,fiscal_date_ending,horizon) DO NOTHING"""), {"id": fetch,"eps": eps}); c.commit()
        if i == 0:
            cutoff = c.execute(text("SELECT clock_timestamp()")).scalar(); c.commit()
    assert c.execute(text("SELECT payload->>'eps' FROM av_earnings_estimates_observations WHERE known_at<=:cutoff"), {"cutoff": cutoff}).scalars().all() == ['1']
    assert c.execute(text("SELECT count(*) FROM av_earnings_estimates_observations")).scalar() == 2
    # Distinct fiscal-year and fiscal-quarter horizons share a business date.
    c.execute(text("""INSERT INTO av_earnings_estimates_observations SELECT '00000000-0000-0000-0000-000000000003',fetch_id,ticker,fiscal_date_ending,'fiscal year',known_at,source_retrieved_at,raw_uri,raw_sha256,payload FROM av_earnings_estimates_observations ORDER BY known_at LIMIT 1""")); c.commit()
    assert c.execute(text("SELECT count(*) FROM av_earnings_estimates_observations")).scalar() == 3
