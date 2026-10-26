"""Independent synthetic closing-step controls; no real prices or providers."""
from copy import deepcopy
from datetime import date
import pandas as pd
import pytest
from lib.earnings_reactions import compute_daily_path_v1

DAYS = [date(2026, 1, d) for d in (2, 5, 6, 7, 8, 9, 12)]
CLOCK = '2026-01-12T21:01:00Z'

def control(basis):
    ev = {'ticker': 'SYNTH', 'fiscal_date_ending': '2025-11-30',
          'reported_date': '2026-01-05', 'reaction_basis': basis}
    receipt = {'event_id': 'SYNTH:2025-11-30:2026-01-05',
               'source_id': 'synthetic-independent-control',
               'observed_at': CLOCK, 'acquired_at': CLOCK,
               'price_basis_id': 'synthetic:raw-one-instrument'}
    closes = [100, 112, 115, 113, 105, 99, 102] if basis == 'BMO' else [100, 100, 88, 92, 96, 99, 101]
    rows = []
    for i, (day, close) in enumerate(zip(DAYS, closes)):
        opening = 110 if basis == 'BMO' and i == 1 else 90 if basis == 'AMC' and i == 2 else close
        rows.append({'date': day, 'open': opening, 'high': max(opening, close)+1,
                     'low': min(opening, close)-1, 'close': close})
    return ev, pd.DataFrame(rows), receipt

@pytest.mark.parametrize('basis,steps,opposite,fill', [('BMO',6,2,4),('AMC',5,1,4)])
def test_independent_root_oracle_distinguishes_first_opposite_from_gapfill(basis,steps,opposite,fill):
    ev, frame, evidence = control(basis)
    r = compute_daily_path_v1(ev, frame, observation_ts=CLOCK, price_evidence=evidence)
    assert r['available'], r
    p = r['payload']
    assert p['expected_steps'] == steps and p['observed_steps'] == steps
    assert p['first_opposite_close_step'] == opposite
    assert p['closing_gap_fill_step'] == fill
    assert p['first_opposite_close_date'] == '2026-01-07'
    assert p['closing_gap_fill_date'] == ('2026-01-09' if basis=='BMO' else '2026-01-12')
    assert p['status'] == 'complete'
    assert p['historical_publication_verified'] is False
    assert 'is_reversal_5d' not in p


def test_future_append_and_perturbation_leave_fixed_prefix_semantics_identical():
    ev, frame, evidence = control('BMO')
    clock = '2026-01-07T21:01:00Z'
    def observed(f):
        p = compute_daily_path_v1(ev,f,observation_ts=clock,price_evidence=evidence)['payload']
        p.pop('computed_at')  # Actual invocation time is provenance, not a feature.
        return p
    prefix = frame.iloc[:4].copy()
    future = frame.astype({'open':float,'high':float,'low':float,'close':float})
    future.loc[4:, ['open','high','low','close']] = [1,2,0.5,1]
    assert observed(prefix) == observed(frame) == observed(future)
    assert observed(prefix)['status'] == 'maturing'
    assert observed(prefix)['per_metric']['closing_gap_fill']['censored'] is None


def test_missing_prior_sample_cannot_claim_first_occurrence():
    ev,f,e=control('BMO'); f=f[f['date']!=date(2026,1,6)]
    r=compute_daily_path_v1(ev,f,observation_ts=CLOCK,price_evidence=e)
    assert r['available'] is False and r['reason']=='missing_daily_session'
    assert r['payload']['first_opposite_close_step'] is None
    assert r['payload']['censored'] is None


def test_mature_no_occurrence_is_right_censored_not_never_reverses():
    ev,f,e=control('BMO')
    for i in range(1,len(f)):
        opening=110+i; closing=opening+1
        f.loc[i,['open','high','low','close']]=[opening,closing+1,opening-1,closing]
    p=compute_daily_path_v1(ev,f,observation_ts=CLOCK,price_evidence=e)['payload']
    assert p['per_metric']['first_opposite_close']['status']=='right_censored'
    assert p['per_metric']['closing_gap_fill']['status']=='right_censored'
    assert p['first_opposite_close_step'] is None and p['censored'] is True


def test_unknown_basis_and_strict_pit_refuse_without_fabricating_clocks():
    ev,f,e=control('BMO'); e.pop('price_basis_id')
    r=compute_daily_path_v1(ev,f,observation_ts=CLOCK,price_evidence=e)
    assert not r['available'] and r['reason']=='missing_price_basis'
    ev,f,e=control('BMO')
    r=compute_daily_path_v1(ev,f,observation_ts=CLOCK,price_evidence=e,mode='strict_pit')
    assert not r['available'] and r['reason']=='missing_exact_release_clock_for_strict_pit'
    assert 'release_ts' not in ev


@pytest.mark.parametrize('defect,reason',[
    ('duplicate','duplicate_daily_session'),('zero','invalid_daily_price'),
    ('nonfinite','invalid_daily_price'),('incoherent','incoherent_daily_ohlc')])
def test_price_quality_refusals_do_not_become_negative_outcomes(defect,reason):
    ev,f,e=control('BMO')
    f=f.astype({'open':float,'high':float,'low':float,'close':float})
    if defect=='duplicate': f=pd.concat([f,f.iloc[[2]]],ignore_index=True)
    elif defect=='zero': f.loc[2,'low']=0
    elif defect=='nonfinite': f.loc[2,'close']=float('nan')
    elif defect=='incoherent': f.loc[2,'high']=1
    r=compute_daily_path_v1(ev,f,observation_ts=CLOCK,price_evidence=e)
    assert not r['available'] and r['reason']==reason
    assert r['payload']['first_opposite_close_step'] is None
    assert r['payload']['censored'] is None


def test_zero_gap_is_not_applicable_not_an_observed_reversal():
    ev,f,e=control('BMO');f.loc[1,['open','low']]=[100,99]
    p=compute_daily_path_v1(ev,f,observation_ts=CLOCK,price_evidence=e)['payload']
    assert p['status']=='not_applicable' and p['gap_sign']==0
    assert p['first_opposite_close_step'] is None
    assert p['per_metric']['first_opposite_close']['status']=='not_applicable'
    assert p['per_metric']['closing_gap_fill']['available'] is False


def test_canonical_halfday_and_dst_endpoint_clocks_are_not_fixed_24hour_math():
    from lib.earnings_reactions import earnings_session_schedule
    schedule=earnings_session_schedule(date(2026,11,17),date(2026,12,10))
    ev={'ticker':'SYNTH','fiscal_date_ending':'2026-08-31','reported_date':'2026-11-19','reaction_basis':'BMO'}
    labels=[date(2026,11,d) for d in (18,19,20,23,24,25,27)]
    frame=pd.DataFrame([{'date':day,'open':100+i,'high':102+i,'low':99+i,'close':101+i}
                        for i,day in enumerate(labels)])
    frame.loc[1,['open','high']]=[110,111]
    evidence={'event_id':'SYNTH:2026-08-31:2026-11-19','source_id':'synthetic-halfday',
              'observed_at':'2026-11-27T18:00:00Z','acquired_at':'2026-11-27T18:00:00Z',
              'price_basis_id':'synthetic-raw'}
    p=compute_daily_path_v1(ev,frame,observation_ts='2026-11-27T18:00:00Z',
                            price_evidence=evidence,schedule=schedule)['payload']
    assert p['status']=='complete' and p['observed_steps']==6
    assert p['mature_at']=='2026-11-27T18:00:00+00:00'
    early=compute_daily_path_v1(ev,frame,observation_ts='2026-11-27T17:59:59Z',
                                price_evidence=evidence,schedule=schedule)['payload']
    assert early['status']=='maturing' and early['observed_steps']==5
    assert date(2026,11,26) not in [x.date() for x in schedule.index]
    march=earnings_session_schedule(date(2026,3,6),date(2026,3,9))
    assert pd.Timestamp(march.iloc[0]['market_close']).hour==21
    assert pd.Timestamp(march.iloc[1]['market_close']).hour==20
