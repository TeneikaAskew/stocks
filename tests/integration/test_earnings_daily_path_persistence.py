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
        assert summary['events']==[{'event_id':payload()['event_id'],'reported_date':'2026-01-05','fiscal_date_ending':'2025-11-30','status':'complete','reason':None}]
        assert summary['first_opposite_close']['observed_n']==1
        assert summary['first_opposite_close']['median_first_observed_step']==2
        assert client.get('/api/earnings/event/SYNTH/2026-01-06').status_code==404


def test_preserved_ango_default_producer_to_storage_views_api_and_brief(db, monkeypatch):
    """Optional known private captures; four historical descriptors, no forecast.

    Source retrieval only is injected from the preserved qualified projection.
    Actual default producer, native math, JSON helper, persistence, views,
    router and default brief admission execute. No live DB/provider or scoring.
    """
    import hashlib
    import json
    from datetime import timedelta
    root=os.environ.get('EARNINGS_ANGO_FIXTURE_ROOT')
    if not root:
        pytest.skip('private preserved ANGO captures not supplied')
    root=Path(root)
    f=root/'earnings-five-field-fixture-v1/fixture.json'
    source=root/'actual-earnings-validation-v1/selected-prior-quarter-inputs.jsonl'
    assert hashlib.sha256(f.read_bytes()).hexdigest()=='17a66bfcf650468c371f67e9e4fc5906109a2463854d22a796e6cc6ce416fefe'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='c96c015c904fb447ecf830d662aa4c90d86e76be4ae4f2d33b6c976e30323121'
    fixture=json.loads(f.read_text())
    from gcp.fetchers import compute_earnings_reactions as compute
    from gcp import database, earnings_reactions_brief as brief
    events=[dict(r['event'],reported_date=date.fromisoformat(r['event']['reported_date']),
                 fiscal_date_ending=date.fromisoformat(r['event']['fiscal_date_ending']),report_time='BMO')
            for r in fixture['records']]
    raw=[json.loads(line) for line in source.read_text().splitlines()]
    rows=[]
    for r in raw:
        v=r['raw_provider_values']
        assert r['symbol']=='ANGO' and float(v['8. split coefficient'])==1 and float(v['7. dividend amount'])==0
        rows.append(dict(date=date.fromisoformat(r['date']),**{k:float(v[label]) for k,label in
                    [('open','1. open'),('high','2. high'),('low','3. low'),('close','4. close')]}))
    frame=pd.DataFrame(rows).sort_values('date').reset_index(drop=True)
    assert not frame['date'].duplicated().any() and len(frame)==64
    now=pd.Timestamp.now(tz='UTC').isoformat()
    windows={}
    for ev in events:
        day=ev['reported_date']
        df=frame[(frame['date']>=day-timedelta(days=30))&(frame['date']<=day+timedelta(days=30))].copy().reset_index(drop=True)
        df.attrs['earnings_price_evidence']={
            'event_id':f"ANGO:{ev['fiscal_date_ending']}:{day}",
            'source_id':'preserved-qualified-projection:'+hashlib.sha256(source.read_bytes()).hexdigest(),
            'observed_at':now,'acquired_at':now,
            'price_basis_id':'actual-preserved-av-raw-split1-dividend0-selected-windows'}
        windows[day]=df
    monkeypatch.setattr(compute,'is_cloud_sql_configured',lambda:True)
    monkeypatch.setattr(compute,'fetch_earnings_history_for_tickers',lambda tickers:pd.DataFrame(events))
    monkeypatch.setattr(compute,'fetch_calendar_timing_map',lambda tickers:{})
    monkeypatch.setattr(compute,'fetch_daily_windows_for_ticker_dates',lambda *a:windows)
    with db.begin() as c:c.execute(sa.text("DELETE FROM earnings_reactions WHERE ticker='ANGO'"))
    assert compute.populate_for_tickers(['ANGO'])==4
    with db.begin() as c:
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_event_outcomes'))
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_ticker_lean'))
    def query(sql,params=None):
        with db.connect() as c:return pd.read_sql(sa.text(sql),c,params=params or {})
    monkeypatch.setattr(database,'query_to_dataframe_strict',query)
    admitted=brief.load_reaction_history(['ANGO'],date(2026,10,1))['ANGO']
    ctx=brief.build_ticker_context({'ticker':'ANGO'},admitted,None,date(2026,10,1))
    assert ctx.n_quarters==4 and ctx.hist12q_consistent_rate==.75 and ctx.hist12q_gap_up_rate==.5
    july=next(r for r in admitted if r['reported_date']==date(2026,7,14))
    assert july['reaction_gap_pct']==pytest.approx(6.771037181996088)
    assert july['sustain_5d_pct']==pytest.approx(9.38461538461539)
    assert july['reaction_anchor_price']==13.0
    assert july['daily_path_v1']['status']=='complete'
    sys.path.insert(0,str(Path('platform').resolve()))
    from api.routers import earnings
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(earnings,'_CLOUD_SQL',True)
    app=FastAPI();app.include_router(earnings.router)
    with TestClient(app) as client:
        event=client.get('/api/earnings/event/ANGO/2026-07-14')
        assert event.status_code==200
        assert event.json()['daily_path_v1']==july['daily_path_v1']
        lean=client.get('/api/earnings/ticker/ANGO/lean').json()['daily_path_summary_v1']
        assert lean['qualified_native_n']==4 and lean['historical_direction_consistency_pct']==75
        assert lean['historical_upward_opening_gap_pct']==50 and len(lean['events'])==4
        assert lean['point_in_time_verified'] is False


def test_schema_reapply_preserves_old_null_evidence_and_views_populated(db,monkeypatch):
    from gcp import apply_schema, database
    from gcp.fetchers.compute_earnings_reactions import _persist_reaction_frame
    row=record();row['daily_path_v1']=None
    _persist_reaction_frame(pd.DataFrame([row]))
    before=read(db)
    monkeypatch.setattr(database,'get_engine',lambda:db)
    def execute(sql):
        with db.begin() as c:c.execute(sa.text(sql))
    monkeypatch.setattr(apply_schema,'execute_sql',execute)
    for unit in apply_schema.split_statement_groups(Path('gcp/schema.sql').read_text()):
        apply_schema.run_unit(unit)
    assert read(db)==before
    with db.connect() as c:
        assert c.execute(sa.text("SELECT daily_path_v1 FROM earnings_event_outcomes WHERE ticker='SYNTH'")).scalar() is None
        summary=c.execute(sa.text("SELECT daily_path_summary_v1 FROM earnings_ticker_lean WHERE ticker='SYNTH'")).scalar()
        assert summary['qualified_native_n']==0
        assert summary['historical_direction_consistency_pct'] is None
        assert summary['events'][0]['event_id']==payload()['event_id']
        assert summary['events'][0]['status']=='unavailable'


def test_actual_event_view_does_not_attach_other_fiscal_period_eps(db):
    from gcp.fetchers.compute_earnings_reactions import _persist_reaction_frame
    _persist_reaction_frame(pd.DataFrame([record()]))
    with db.begin() as c:
        c.execute(sa.text("DELETE FROM earnings_history WHERE ticker='SYNTH'"))
        c.execute(sa.text("INSERT INTO earnings_history(ticker,fiscal_date_ending,reported_date,reported_eps,surprise_pct) VALUES('SYNTH','2025-08-31','2026-01-05',99,999)"))
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_event_outcomes'))
        row=c.execute(sa.text("SELECT * FROM earnings_event_outcomes WHERE ticker='SYNTH'")).mappings().one()
        assert row['fiscal_date_ending']==date(2025,11,30)
        assert row['reported_eps'] is None and row['eps_surprise_pct'] is None
        c.execute(sa.text("DELETE FROM earnings_history WHERE ticker='SYNTH'"))


def test_actual_daily_refresh_embeds_descriptor_without_new_upcoming_column(db,monkeypatch):
    from gcp import database,refresh_earnings_views as refresh
    from gcp.fetchers.compute_earnings_reactions import _persist_reaction_frame
    _persist_reaction_frame(pd.DataFrame([record()]))
    with db.begin() as c:
        c.execute(sa.text("DELETE FROM earnings_calendar WHERE ticker='SYNTH'"))
        c.execute(sa.text("INSERT INTO earnings_calendar(ticker,earnings_date,earnings_time,data_source) VALUES('SYNTH',CURRENT_DATE,'premarket','alphavantage')"))
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_event_outcomes'))
        c.execute(sa.text('REFRESH MATERIALIZED VIEW earnings_ticker_lean'))
    def query(sql,params=None):
        with db.connect() as c:return pd.read_sql(sa.text(sql),c,params=params or {})
    monkeypatch.setattr(refresh,'query_to_dataframe',query)
    monkeypatch.setattr(database,'query_to_dataframe',query)
    refresh.refresh_daily(14)
    with db.connect() as c:
        stored=c.execute(sa.text("SELECT last_3_events FROM earnings_upcoming_with_history WHERE ticker='SYNTH' AND refresh_date=CURRENT_DATE")).scalar_one()
        assert isinstance(stored,list) and stored[0]['daily_path_v1']==payload()
        assert stored[0]['eps_surprise_pct'] is None
    with db.begin() as c:c.execute(sa.text("DELETE FROM earnings_calendar WHERE ticker='SYNTH'"))
