"""Real SQL + actual route controls for retained pre-retirement snapshots."""
from datetime import date, timedelta
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa

from tests.integration.test_catalyst_earnings_estimate_numbers_pg import local_calendar_database
from gcp import refresh_earnings_views as refresh

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'platform'))
from api.routers import earnings

RETIRED = ('playability_score', 'quintile', 'confidence_label',
           'recommended_structure_long_only', 'recommended_structure_ic_mode')


@pytest.fixture
def snapshot_db(local_calendar_database, monkeypatch):
    _, engine, _ = local_calendar_database
    with engine.begin() as conn:
        conn.execute(sa.text('''ALTER TABLE earnings_calendar
            ADD COLUMN market_cap DOUBLE PRECISION,
            ADD COLUMN sector TEXT,
            ADD COLUMN expected_move DOUBLE PRECISION,
            ADD COLUMN options_volume BIGINT,
            ADD COLUMN open_interest BIGINT,
            ALTER COLUMN data_source DROP NOT NULL'''))
        conn.execute(sa.text('CREATE TABLE market_data_daily (ticker TEXT, date DATE, close DOUBLE PRECISION)'))
        conn.execute(sa.text('''CREATE TABLE earnings_upcoming_with_history (
            refresh_date DATE NOT NULL, ticker TEXT NOT NULL, earnings_date DATE NOT NULL,
            company_name TEXT, archetype TEXT, expected_move DOUBLE PRECISION,
            lean_score DOUBLE PRECISION, last_3_events JSONB,
            playability_score DOUBLE PRECISION, quintile TEXT, confidence_label TEXT,
            recommended_structure_long_only TEXT, recommended_structure_ic_mode TEXT,
            PRIMARY KEY(refresh_date, ticker, earnings_date))'''))
    monkeypatch.setattr(refresh, 'get_engine', lambda: engine)
    monkeypatch.setattr(earnings, '_CLOUD_SQL', True)
    app = FastAPI()
    app.include_router(earnings.router)
    return engine, TestClient(app)


def seed(engine, ticker, source, event_date, *, snapshot_date=None):
    day = date.today() - timedelta(days=1) if snapshot_date is None else snapshot_date
    with engine.begin() as conn:
        conn.execute(sa.text('''INSERT INTO earnings_calendar
            (ticker, earnings_date, company_name, strategy, data_source)
            VALUES (:ticker, :event_date, :ticker, '', :source)
            ON CONFLICT DO NOTHING'''), dict(ticker=ticker, event_date=event_date, source=source))
        conn.execute(sa.text('''INSERT INTO earnings_upcoming_with_history
            VALUES (:day, :ticker, :event_date, 'retained company', 'bullish_trend',
                    20, 0.4, CAST(:events AS JSONB), 90, 'Q5',
                    'HIGH', 'LONG CALL', 'IC')'''), dict(day=day,ticker=ticker,event_date=event_date,events='[{"date":"2026-07-30","gap_pct":4}]'))


def test_empty_retirement_refresh_cannot_resurrect_prior_ew_snapshot(snapshot_db):
    engine, client = snapshot_db
    event = date.today() + timedelta(days=2)
    seed(engine, 'EWO', 'earnings_whispers', event)
    seed(engine, 'EWR', 'EarningsWhispers', event)
    seed(engine, 'TODAYEW', 'earnings_whispers', event, snapshot_date=date.today())
    refresh.refresh_daily(14)  # actual SQL + actual atomic empty replacement
    response = client.get('/api/earnings/upcoming?days=14')
    assert response.status_code == 200
    assert response.json() == {'rows': [], 'count': 0}
    with engine.connect() as conn:
        prior = conn.execute(sa.text('SELECT ticker, playability_score FROM earnings_upcoming_with_history ORDER BY ticker')).all()
        assert prior == [('EWO', 90.0), ('EWR', 90.0)]  # historical snapshots untouched
        assert conn.execute(sa.text('SELECT COUNT(*) FROM earnings_calendar')).scalar_one() == 3


def test_prior_non_ew_snapshots_keep_descriptors_but_never_retired_scores(snapshot_db):
    engine, client = snapshot_db
    event = date.today() + timedelta(days=2)
    sources = {'AV':'alphavantage','UW':'unusual_whales','YH':'yahoo',
               'NULL':None,'UNKNOWN':'unknown','NEAR':'Earnings_Whispers',
               'EWO':'earnings_whispers','EWR':'EarningsWhispers'}
    for ticker, source in sources.items():
        seed(engine,ticker,source,event)
    response = client.get('/api/earnings/upcoming?days=14')
    assert response.status_code == 200
    rows = {r['ticker']:r for r in response.json()['rows']}
    assert set(rows) == set(sources) - {'EWO','EWR'}
    for row in rows.values():
        assert all(row[key] is None for key in RETIRED)
        assert row['company_name'] == 'retained company'
        assert row['archetype'] == 'bullish_trend'
        assert row['expected_move'] == 20
        assert row['lean_score'] == 0.4
        assert row['last_3_events'] == [{'date':'2026-07-30','gap_pct':4}]
    with engine.connect() as conn:
        assert conn.execute(sa.text('SELECT COUNT(*) FROM earnings_upcoming_with_history WHERE playability_score=90')).scalar_one() == 8


def test_retained_source_admission_is_bound_to_the_snapshot_event_date(snapshot_db):
    engine, client = snapshot_db
    early = date.today() + timedelta(days=1)
    later = early + timedelta(days=1)
    seed(engine,'MIX','earnings_whispers',early)
    seed(engine,'MIX','alphavantage',later)
    response = client.get('/api/earnings/upcoming?days=14')
    assert response.status_code == 200
    assert [(r['ticker'],r['earnings_date']) for r in response.json()['rows']] == [('MIX',later.isoformat())]
