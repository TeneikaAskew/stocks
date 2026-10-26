"""Actual PostgreSQL controls. Opt in only with a loopback disposable test DB.

EARNINGS_TEST_DB_URL_FILE names a private URL file (never logged). No provider
or production DB access; full schema/applier, producer upsert and refresh are
used without replacing their SQL. No synthetic control is predictive evidence.
"""
from copy import deepcopy
from datetime import date
import os
from pathlib import Path
import sys

import pandas as pd
import pytest
import sqlalchemy as sa


@pytest.fixture(scope='module')
def engine():
    path = os.environ.get('EARNINGS_TEST_DB_URL_FILE')
    if not path:
        pytest.skip('explicit disposable local PostgreSQL not selected')
    url = sa.engine.make_url(Path(path).read_text().strip())
    if url.host not in ('localhost', '127.0.0.1', '::1') or url.database != 'earnings_integration':
        pytest.fail('test DB must be loopback earnings_integration')
    e = sa.create_engine(url)
    from gcp import apply_schema, database
    old_engine, old_execute = database.get_engine, apply_schema.execute_sql
    database.get_engine = lambda: e
    def execute(sql):
        with e.begin() as c:
            c.execute(sa.text(sql))
    apply_schema.execute_sql = execute
    try:
        for unit in apply_schema.split_statement_groups(Path('gcp/schema.sql').read_text()):
            apply_schema.run_unit(unit)
        yield e
    finally:
        database.get_engine, apply_schema.execute_sql = old_engine, old_execute
        e.dispose()


@pytest.fixture
def db(engine, monkeypatch):
    from gcp import database, refresh_earnings_views
    monkeypatch.setattr(database, 'get_engine', lambda: engine)
    monkeypatch.setattr(refresh_earnings_views, 'get_engine', lambda: engine)
    with engine.begin() as c:
        c.execute(sa.text("DELETE FROM earnings_reactions WHERE ticker LIKE 'SYNTH%';"))
        c.execute(sa.text("DELETE FROM earnings_upcoming_with_history WHERE ticker LIKE 'SYNTH%';"))
    return engine


def payload(status='complete'):
    return {'version': 'earnings-daily-path-v1', 'event_id': 'SYNTH:2025-11-30:2026-01-05',
            'basis_id': 'synthetic:raw', 'status': status,
            'mature_at': '2026-01-12T21:00:00+00:00',
            'observation_ts': '2026-01-12T21:01:00+00:00',
            'computed_at': '2026-01-12T21:02:00+00:00',
            'first_opposite_close_step': 2, 'closing_gap_fill_step': 4,
            'per_metric': {key: {'available': True, 'censored': False, 'status':'observed'}
                           for key in ('first_opposite_close','closing_gap_fill')}}


def record(p=None):
    return dict(ticker='SYNTH', fiscal_date_ending=date(2025,11,30),
                reported_date=date(2026,1,5), reaction_basis='BMO',
                reaction_gap_pct=10., pre_earnings_drift_10d_pct=1.,
                sustain_5d_pct=-8.928571428571, direction_consistent_5d=False,
                is_reversal_5d=True, daily_path_v1=p if p is not None else payload())


def read(db):
    with db.connect() as c:
        return dict(c.execute(sa.text("SELECT * FROM earnings_reactions WHERE ticker='SYNTH'")).mappings().one())


@pytest.mark.parametrize('replacement', ['null','unavailable','immature','missing_native','event','basis','version'])
def test_actual_upsert_retains_qualified_prior_and_original_clocks(db, replacement):
    from gcp.fetchers.compute_earnings_reactions import _persist_reaction_frame
    assert _persist_reaction_frame(pd.DataFrame([record()])) == 1
    before=read(db)
    changed=record(); changed['reaction_gap_pct']=20.
    if replacement=='null': changed['daily_path_v1']=None
    elif replacement=='unavailable': changed['daily_path_v1']=payload('unavailable')
    elif replacement=='immature': changed['daily_path_v1']=payload('maturing')
    elif replacement=='missing_native': changed['sustain_5d_pct']=None
    elif replacement=='event': changed['reported_date']=date(2026,1,6)
    elif replacement=='basis': changed['daily_path_v1']['basis_id']='other-basis'
    elif replacement=='version': changed['daily_path_v1']['version']='v2'
    assert _persist_reaction_frame(pd.DataFrame([changed])) == 0
    assert read(db)==before


def test_compatible_complete_refresh_is_atomic_and_idempotent(db):
    from gcp.fetchers.compute_earnings_reactions import _persist_reaction_frame
    _persist_reaction_frame(pd.DataFrame([record()]))
    new=record(); new['reaction_gap_pct']=12.
    new['daily_path_v1']['computed_at']='2026-01-13T21:02:00+00:00'
    assert _persist_reaction_frame(pd.DataFrame([new]))==1
    after=read(db)
    assert after['reaction_gap_pct']==12. and after['daily_path_v1']==new['daily_path_v1']
    assert _persist_reaction_frame(pd.DataFrame([new]))==1
    assert read(db)==after


def test_failed_upcoming_insert_rolls_back_actual_prior_snapshot(db):
    from gcp.refresh_earnings_views import _replace_upcoming_rows
    day=date(2026,1,1)
    good=pd.DataFrame([dict(ticker='SYNTH',refresh_date=day,earnings_date=date(2026,1,5),
                            last_3_events=[{'daily_path_v1':payload()}])])
    assert _replace_upcoming_rows(good,day)==1
    with db.connect() as c:
        before=c.execute(sa.text("SELECT * FROM earnings_upcoming_with_history WHERE ticker='SYNTH'")).mappings().one()
    bad=good.copy(); bad.loc[0,'ticker']=None
    with pytest.raises(sa.exc.DBAPIError): _replace_upcoming_rows(bad,day)
    with db.connect() as c:
        assert dict(c.execute(sa.text("SELECT * FROM earnings_upcoming_with_history WHERE ticker='SYNTH'")).mappings().one())==dict(before)


def test_actual_views_and_router_keep_event_list_unknowns_and_native_fields(db,monkeypatch):
    from gcp.fetchers.compute_earnings_reactions import _persist_reaction_frame
    from gcp import database
    _persist_reaction_frame(pd.DataFrame([record()]))
    with db.begin() as c:
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_event_outcomes'))
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_ticker_lean'))
    def query(sql,params=None):
        with db.connect() as c: return pd.read_sql(sa.text(sql),c,params=params or {})
    monkeypatch.setattr(database,'query_to_dataframe_strict',query)
    sys.path.insert(0,str(Path('platform').resolve()))
    from api.routers import earnings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(earnings,'_CLOUD_SQL',True)
    app=FastAPI(); app.include_router(earnings.router)
    with TestClient(app) as client:
        event=client.get('/api/earnings/event/SYNTH/2026-01-05')
        assert event.status_code==200,event.text
        ev=event.json(); assert ev['daily_path_v1']==payload()
        assert ev['sustain_5d_pct']==record()['sustain_5d_pct']
        assert ev['reaction_anchor_price'] is None
        response=client.get('/api/earnings/ticker/SYNTH/lean')
        assert response.status_code==200,response.text
        summary=response.json()['daily_path_summary_v1']
        assert summary['event_n']==1 and summary['qualified_native_n']==1
        assert summary['historical_direction_consistency_pct']==0
        assert summary['events']==[{'event_id':payload()['event_id'],'reported_date':'2026-01-05','status':'complete','reason':None}]
        assert summary['first_opposite_close']['observed_n']==1
        assert summary['first_opposite_close']['median_first_observed_step']==2
        assert client.get('/api/earnings/event/SYNTH/2026-01-06').status_code==404
