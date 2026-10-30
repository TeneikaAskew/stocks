"""Native score contract, not market or prediction performance evidence."""
import copy
import json
from pathlib import Path
import socket
import subprocess

import pandas as pd
import pytest

from lib.signals import build_score_explanation, read_score_explanation
from lib.trading_analysis import MarketAnalyzer


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("external I/O forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def native_momentum(case_index=0):
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/historical_score_native_controls.json").read_text())
    case = fixture['cases'][case_index]
    frame = pd.DataFrame(case['enriched_rows'])
    frame['Time'] = pd.to_datetime(frame.Time)
    out = MarketAnalyzer().generate_technical_signals(frame)
    return out.loc[out.entry_time == frame.Time.iloc[case['expected']['target_index']]].iloc[0]


@pytest.mark.parametrize('index,strength', [(0,6),(1,7)])
def test_native_momentum_no_universal_five_point_ceiling(index, strength):
    row = native_momentum(index)
    assert row.signal_strength == strength
    assert row.conditions_met == f"{strength}/7"
    e = row.score_explanation
    assert e['base_count'] == strength
    assert e['base_max'] == e['composite_max'] == 7
    assert len(e['matched_conditions']) == strength
    assert e['provenance']['producer_definition'] == 'historical-momentum-v1'
    assert e['provenance']['input_sha256']
    assert len(json.dumps(e).encode()) <= 2048


def test_legacy_six_preserves_unknown_definition():
    e = read_score_explanation(None, score=6, strategy='momentum', storage_source='cloud_sql')
    assert e['status'] == 'legacy_unavailable'
    assert e['base_max'] is None and e['composite_strength'] is None
    assert e['unavailable_reasons'] == ['legacy_score_contract_missing']


@pytest.mark.parametrize('mutation', [
    {'base_count':2}, {'composite_strength':float('nan')}, {'unexpected':'x'},
    {'matched_conditions':['above_vwap']*6}, {'version':'invented'},
    {'provenance':{'producer_definition':'invented'}},
    {'unavailable_reasons':['x'*2100]},
    *[{'unavailable_reasons':bad} for bad in (None,False,{},0,'')],
])
def test_invalid_metadata_never_qualifies(mutation):
    e = copy.deepcopy(native_momentum().score_explanation)
    e.update(mutation)
    result = read_score_explanation(e, score=6, strategy='momentum', storage_source='cloud_sql')
    assert result['status'] == 'invalid_record'
    assert result['base_max'] is None


def test_strategy_and_native_total_must_match():
    e = native_momentum().score_explanation
    assert read_score_explanation(e,score=7,strategy='momentum',storage_source='cloud_sql')['status'] == 'invalid_record'
    assert read_score_explanation(e,score=6,strategy='mean_reversion',storage_source='cloud_sql')['status'] == 'invalid_record'
    assert read_score_explanation(e,score=6,strategy='momentum',storage_source='cloud_sql')['status'] == 'recorded'


def test_generic_bonus_is_native_total_not_a_universal_maximum():
    from lib.signals import evaluate_signal
    row=pd.Series({'Consecutive_Down':3,'RSI14':35.,'Price_vs_VWAP':-1.,'StochRSI_K':20.})
    result=evaluate_signal(row,strat_bonus=2)
    assert result['base_score']==4 and result['strat_bonus']==2 and result['total_score']==6
    assert 'score_explanation' not in result  # generic caller has no declared ceiling


def test_actual_native_momentum_negative_remains_no_signal():
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/historical_score_native_controls.json').read_text())
    frame=pd.DataFrame(fixture['cases'][0]['enriched_rows'])
    frame['Time']=pd.to_datetime(frame.Time)
    frame['Last']=100.; frame['VWAP']=100.; frame['EMA9']=100.
    frame['RSI14_W']=50.; frame['ATR_Expansion']=1.; frame['RVol_Recent_20']=1.
    assert MarketAnalyzer().generate_technical_signals(frame).empty


def test_missing_stored_score_does_not_qualify_metadata():
    e=native_momentum().score_explanation
    assert read_score_explanation(e,score=None,strategy='momentum',storage_source='cloud_sql')['status']=='invalid_record'


def test_input_identity_distinguishes_native_threshold_crossing_and_adjacent_float_neighbors():
    import numpy as np
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/historical_score_native_controls.json').read_text())['cases'][0]
    for low, high in [(1.2 - 1e-12, 1.2 + 1e-12), (np.nextafter(1.2, -np.inf), np.nextafter(1.2, np.inf))]:
        rows = []
        for value in (low, high):
            frame = pd.DataFrame(fixture['enriched_rows'])
            frame['Time'] = pd.to_datetime(frame.Time)
            frame['RVol_Recent_20'] = value
            rows.append(MarketAnalyzer().generate_technical_signals(frame).iloc[-1])
        assert [int(row.signal_strength) for row in rows] == [5, 6]
        assert rows[0].score_explanation['provenance']['input_sha256'] != rows[1].score_explanation['provenance']['input_sha256']


def test_mapper_rejects_opposite_direction_native_metadata():
    from scripts.run_historical_signals import map_signals_to_table
    row = native_momentum().copy()
    row['trade_type'] = 'put'
    with pytest.raises(ValueError, match='invalid native score_explanation'):
        map_signals_to_table(pd.DataFrame([row]), 'IWM')


def test_input_identity_preserves_nanosecond_time_index_and_dtype():
    from lib.signals import _score_input_sha256
    frame = pd.DataFrame({'Time': [pd.Timestamp('2026-10-30T12:00:00.000000001Z')], 'value': [1.0]})
    original = _score_input_sha256(frame)
    assert _score_input_sha256(frame.copy(deep=True)) == original
    later = frame.copy(); later['Time'] += pd.Timedelta(1, unit='ns')
    assert _score_input_sha256(later) != original
    moved = frame.copy(); moved.index = [1]
    assert _score_input_sha256(moved) != original
    typed = frame.copy(); typed['value'] = typed['value'].astype('float32')
    assert _score_input_sha256(typed) != original


def test_lossless_input_identity_retains_bounded_scratch_memory():
    import tracemalloc
    from lib.signals import _score_input_sha256
    frame = pd.DataFrame({'price': [1.2345678901234567] * 10000, 'volume': range(10000)})
    tracemalloc.start()
    try:
        _score_input_sha256(frame)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 2 * 1024 * 1024, 'input hashing must not retain a serialized copy of the complete frame'
