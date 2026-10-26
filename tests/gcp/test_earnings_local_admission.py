"""Bounded synthetic proof: legacy behavior versus additive strict local profile."""
from datetime import date
import pandas as pd
from gcp import earnings_reactions_brief as brief
from gcp.fetchers import compute_earnings_reactions as compute


def test_default_event_predicate_refuses_unannounced_quarter(monkeypatch):
    import gcp.database as database
    row = {'ticker': 'SYNTH', 'fiscal_date_ending': date(2026, 6, 30),
           'reported_date': date(2026, 10, 8), 'reaction_gap_pct': 10.0}
    captured = []
    def query(sql, params):
        captured.append(sql)
        # Implement only the actual captured SQL predicate over synthetic data.
        assert 'reported_date < :before' in sql
        return pd.DataFrame([row] if row['reported_date'] < params['before'] else [])
    monkeypatch.setattr(database, 'query_to_dataframe_strict', query)
    actual = brief.load_reaction_history(['SYNTH'], date(2026, 10, 8))
    assert actual == {}
    assert captured


def test_unknown_timing_refuses():
    assert compute.normalize_timing(None, None) is None


def test_session_helpers_exclude_exchange_holiday():
    assert brief._next_session(date(2026, 7, 2)) == date(2026, 7, 6)
    assert brief._prev_session(date(2026, 7, 6)) == date(2026, 7, 2)


def test_default_recap_never_reuses_earlier_quarter(monkeypatch):
    monkeypatch.setattr(brief, 'load_calendar_reporters', lambda day: [
        {'ticker': 'SYNTH'}] if day == date(2026, 5, 13) else [])
    earlier = {'ticker': 'SYNTH', 'reported_date': date(2026, 2, 12),
               'fiscal_date_ending': date(2025, 12, 31), 'reaction_gap_pct': 7.0}
    monkeypatch.setattr(brief, 'load_reaction_history', lambda *a, **k: {'SYNTH': [earlier]})
    monkeypatch.setattr(brief, 'load_insider_net_flow', lambda *a, **k: {})
    monkeypatch.setattr(brief, 'load_exact_reactions', lambda *a, **k: {})
    result = brief.generate_brief(date(2026, 5, 14))
    actual = result['last_session_contexts'][0]
    assert actual.upcoming_report_date == date(2026, 5, 13)
    assert actual.latest_reaction is None

from copy import deepcopy
import json
import socket
import pytest
from lib.earnings_reactions import admit_local_reaction, local_event_timing
from lib.earnings_reactions import earnings_session_schedule as nyse_schedule

CLOCK = '2026-10-07T12:35:00Z'


def receipt(event_id, observed='2026-10-01T22:00:00Z'):
    return {'source_id': 'synthetic-retained-source', 'event_id': event_id,
            'observed_at': observed, 'acquired_at': '2026-10-24T00:00:00Z',
            'recovered_at': '2026-10-24T01:00:00Z',
            'publication_evidence_id': 'synthetic-publication-receipt'}


def event(event_id='quarter-1', reported='2026-09-01', basis='BMO'):
    release = reported + ('T11:00:00Z' if basis == 'BMO' else 'T20:30:00Z')
    day = date.fromisoformat(reported)
    quarter = (day.month - 1) // 3
    fiscal = (date(day.year, quarter * 3 + 1, 1) - pd.Timedelta(days=1)).isoformat()
    return {'event_id': event_id, 'ticker': 'SYNTH', 'reported_date': reported,
            'fiscal_date_ending': fiscal, 'release_ts': release,
            'timing_sources': [{'basis': basis, 'receipt': receipt(event_id)}]}


def reaction(event_id='quarter-1', reported='2026-09-01', basis='BMO'):
    return {'event': event(event_id, reported, basis), 'receipt': receipt(event_id),
            'values': {'reaction_gap_pct': 10.0, 'pre_earnings_drift_10d_pct': 3.0,
                       'sustain_5d_pct': 2.0, 'direction_consistent_5d': True,
                       'is_reversal_5d': False, 'sustain_10d_pct': 999.0,
                       'untrusted_extra': 'must-not-escape'},
            'field_known_at': {key: '2026-10-01T21:00:00Z' for key in (
                'reaction_gap_pct', 'pre_earnings_drift_10d_pct', 'sustain_5d_pct',
                'direction_consistent_5d', 'is_reversal_5d')}}


def reporter(event_id='upcoming', reported='2026-10-08'):
    return {'event': {'event_id': event_id, 'ticker': 'SYNTH', 'reported_date': reported},
            'receipt': receipt(event_id)}


def local(records=None, reporters=None, clock=CLOCK, mode='strict_pit'):
    return brief.generate_local_brief(observation_ts=clock, mode=mode,
        evidence={'reporters': [reporter()] if reporters is None else reporters,
                  'reactions': [] if records is None else records})


def test_local_classification_reuses_four_clean_quarters_and_strips_extras():
    records = [reaction('q' + str(i), day) for i, day in enumerate(
        ['2025-12-01', '2026-03-02', '2026-06-01', '2026-09-01'])]
    actual = local(records)
    context = actual['next_contexts'][0]
    assert actual['available'] and context['n_quarters'] == 4
    assert context['classification'] == brief.CLASS_SELL
    assert context['hist12q_consistent_rate'] == 1.0
    assert actual['score'] is None and actual['strat_prediction'] is None
    serialized = json.dumps(actual, default=str)
    assert '999' not in serialized and 'untrusted_extra' not in serialized
    assert 'sustain_10d_pct' not in serialized
    assert actual['historical_publication_verified'] is False


def test_fiscal_end_does_not_admit_unannounced_quarter():
    row = reaction('future', '2026-10-08')
    actual = local([row])
    assert actual['next_contexts'][0]['n_quarters'] == 0
    assert actual['next_contexts'][0]['classification'] == brief.CLASS_INSUFFICIENT
    assert not admit_local_reaction(row, CLOCK, 'strict_pit')['available']


def test_five_day_maturity_changes_clean_quarter_gate():
    row = reaction('fresh', '2026-10-05')
    row['receipt'] = receipt('fresh', '2026-10-07T12:00:00Z')
    row['event']['timing_sources'][0]['receipt'] = row['receipt']
    row['field_known_at'] = {key: '2026-10-07T12:00:00Z' for key in row['field_known_at']}
    actual = admit_local_reaction(row, CLOCK, 'strict_pit')
    assert not actual['available'] and 'feature_not_mature:sustain_5d_pct' == actual['reason']
    assert admit_local_reaction(row, CLOCK, 'strict_pit', gap_only=True)['available']


@pytest.mark.parametrize('mutation,reason', [
    (lambda r: r.pop('receipt'), 'missing_source_identity'),
    (lambda r: r['receipt'].update(observed_at='2026-10-23T00:00:00Z'), 'source_not_known_at_cutoff'),
    (lambda r: r['receipt'].update(observed_at='2026-10-01T22:00:00'), 'missing_or_naive_observation_clock'),
    (lambda r: r['receipt'].update(event_id='wrong-quarter'), 'source_event_mismatch'),
    (lambda r: r['receipt'].pop('publication_evidence_id'), 'missing_publication_evidence'),
])
def test_missing_late_or_naive_known_at_is_unavailable(mutation, reason):
    row = reaction()
    mutation(row)
    actual = admit_local_reaction(row, CLOCK, 'strict_pit')
    assert not actual['available'] and actual['reason'] == reason


def test_retrospective_vintage_cannot_claim_strict_pit():
    row = reaction()
    row['receipt']['observed_at'] = '2026-10-23T00:00:00Z'
    assert not admit_local_reaction(row, CLOCK, 'strict_pit')['available']
    assert admit_local_reaction(row, CLOCK, 'retrospective_current_vintage')['available']
    actual = local([row], mode='retrospective_current_vintage')
    assert actual['mode'] == 'retrospective_current_vintage'
    assert actual['historical_publication_verified'] is False


@pytest.mark.parametrize('sources,reason', [
    ([], 'unknown_event_timing'),
    ([{'basis': 'AMC', 'receipt': receipt('other-quarter')}], 'source_event_mismatch'),
    ([{'basis': 'BMO', 'receipt': receipt('quarter-1')},
      {'basis': 'AMC', 'receipt': receipt('quarter-1')}], 'conflicting_event_timing'),
])
def test_unknown_or_cross_event_timing_cannot_choose_amc(sources, reason):
    row = reaction()
    row['event']['timing_sources'] = sources
    actual = admit_local_reaction(row, CLOCK, 'strict_pit')
    assert not actual['available'] and actual['reason'] == reason


def test_local_sessions_skip_exchange_holiday():
    actual = local(reporters=[reporter(reported='2026-07-06')], clock='2026-07-02T12:35:00Z')
    assert actual['next_session'] == date(2026, 7, 6)
    actual = local(reporters=[reporter(reported='2026-07-07')], clock='2026-07-06T12:35:00Z',
                   mode='retrospective_current_vintage')
    assert actual['last_session'] == date(2026, 7, 2)


def test_local_cutoff_uses_early_close_and_dst():
    schedule = nyse_schedule(date(2026, 11, 27), date(2026, 11, 27))
    assert schedule.iloc[0]['market_close'] == pd.Timestamp('2026-11-27T18:00:00Z')
    for day, opening in [('2026-03-06', '14:30'), ('2026-03-09', '13:30')]:
        row = nyse_schedule(date.fromisoformat(day), date.fromisoformat(day)).iloc[0]
        assert row['market_open'].strftime('%H:%M') == opening
    ev = event(reported='2026-11-27', basis='AMC')
    ev['release_ts'] = '2026-11-27T18:01:00Z'
    for src in ev['timing_sources']:
        src['receipt'] = receipt(ev['event_id'], '2026-11-27T18:02:00Z')
        src['receipt']['acquired_at'] = '2026-11-27T18:02:00Z'
        src['receipt'].pop('recovered_at')
    assert local_event_timing(ev, '2026-11-27T18:03:00Z', 'strict_pit')[0] == 'AMC'


def test_local_recap_never_substitutes_previous_quarter():
    actual = local([reaction()], reporters=[reporter('last-event', '2026-10-06')])
    item = actual['last_session_contexts'][0]
    assert item['n_quarters'] == 1 and item['latest_reaction'] is None
    assert not item['recap_available']
    current = reaction('last-event', '2026-10-06')
    current['receipt'] = receipt('last-event', '2026-10-07T12:00:00Z')
    current['event']['timing_sources'][0]['receipt'] = current['receipt']
    current['field_known_at']['reaction_gap_pct'] = '2026-10-06T14:00:00Z'
    actual = local([reaction(), current], reporters=[reporter('last-event', '2026-10-06')])
    item = actual['last_session_contexts'][0]
    assert item['recap_available'] and item['latest_reaction']['event_id'] == 'last-event'
    assert 'sustain_5d_pct' not in item['latest_reaction']


def test_local_entrypoint_never_reads_or_writes_external_state(monkeypatch):
    import gcp.database as database
    import requests
    def forbidden(*a, **kw):
        raise AssertionError('external side effect attempted')
    for name in ('query_to_dataframe', 'upsert_dataframe', 'is_cloud_sql_configured'):
        monkeypatch.setattr(database, name, forbidden)
    monkeypatch.setattr(brief, 'send_to_discord', forbidden)
    monkeypatch.setattr(brief, 'load_calendar_reporters', forbidden)
    monkeypatch.setattr(brief, 'load_reaction_history', forbidden)
    monkeypatch.setattr(brief, 'load_insider_net_flow', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    assert local([reaction()])['available']
    for value in (None, '2026-10-07', 'malformed'):
        assert not local(clock=value)['available']
    assert not brief.generate_local_brief(observation_ts=CLOCK, evidence=None, mode='strict_pit')['available']
    assert not local(reporters=[{'event': {'event_id': 'x'}}])['available']


def synthetic_daily():
    schedule = nyse_schedule(date(2026, 8, 17), date(2026, 9, 2))
    rows = [{'date': day.date(), 'open': 100.0, 'high': 120.0, 'low': 80.0,
             'close': 100.0, 'volume': 1000} for day in schedule.index]
    frame = pd.DataFrame(rows)
    frame.loc[frame['date'] == date(2026, 9, 1), 'open'] = 110.0
    frame.loc[frame['date'] == date(2026, 9, 2), 'open'] = 90.0
    receipts = {row['date'].isoformat(): dict(receipt('quarter-1'), price_basis_id='synthetic-raw-v1')
                for row in rows}
    return frame, receipts


@pytest.mark.parametrize('basis,gap', [('BMO', 10.0), ('AMC', -10.0)])
def test_confirmed_bmo_amc_preserve_reaction_math(basis, gap):
    frame, receipts = synthetic_daily()
    ev = event(basis=basis)
    expected = compute.compute_reaction(dict(ev, reported_date=date.fromisoformat(ev['reported_date'])), frame, basis)
    actual = compute.compute_local_reaction(event=ev, daily=frame, price_receipts=receipts,
                                            observation_ts=CLOCK, mode='strict_pit')
    assert actual['available'], actual
    assert actual['row']['reaction_gap_pct'] == pytest.approx(gap)
    assert actual['row']['reaction_gap_pct'] == expected['reaction_gap_pct']
    assert actual['row']['reaction_anchor_price'] == expected['reaction_anchor_price']
    assert 'sustain_10d_pct' not in actual['row']


@pytest.mark.parametrize('damage,reason', [
    ('missing_receipt', 'missing_source_identity'),
    ('basis', 'incoherent_price_basis'),
    ('gap', 'missing_daily_session'),
    ('ohlc', 'incoherent_local_ohlc'),
    ('future', 'daily_bar_not_complete_at_cutoff'),
])
def test_local_computation_rejects_inadmissible_daily(damage, reason):
    frame, receipts = synthetic_daily()
    clock = CLOCK
    if damage == 'missing_receipt':
        receipts.pop(next(iter(receipts)))
    elif damage == 'basis':
        receipts[next(iter(receipts))]['price_basis_id'] = 'different'
    elif damage == 'gap':
        frame = frame.drop(index=3)
    elif damage == 'ohlc':
        frame.loc[0, 'high'] = 50.0
    elif damage == 'future':
        clock = '2026-09-02T15:00:00Z'
        for r in receipts.values():
            r['observed_at'] = '2026-09-02T14:00:00Z'
        ev = event()
        ev['timing_sources'][0]['receipt']['observed_at'] = '2026-09-01T12:00:00Z'
    ev = ev if damage == 'future' else event()
    actual = compute.compute_local_reaction(event=ev, daily=frame, price_receipts=receipts,
                                            observation_ts=clock, mode='strict_pit')
    assert not actual['available'] and actual['reason'] == reason


def test_distinct_event_aliases_cannot_inflate_clean_quarters():
    rows = [reaction('alias-' + str(i)) for i in range(4)]
    result = local(rows)
    assert result['next_contexts'][0]['n_quarters'] == 0
    assert result['next_contexts'][0]['classification'] == brief.CLASS_INSUFFICIENT
    assert {r['reason'] for r in result['rejections']} == {'duplicate_reaction_or_quarter_identity'}


def test_planned_clock_cannot_certify_actual_release():
    row = reaction()
    row['event']['timing_sources'][0]['receipt']['observed_at'] = '2026-08-01T00:00:00Z'
    result = admit_local_reaction(row, CLOCK, 'strict_pit')
    assert result == {'available': False, 'reason': 'actual_release_not_observed'}


def test_field_availability_must_follow_maturity_and_precede_source_receipt():
    row = reaction()
    row['field_known_at']['sustain_5d_pct'] = '2026-09-02T12:00:00Z'
    assert admit_local_reaction(row, CLOCK, 'strict_pit')['reason'] == 'feature_not_mature:sustain_5d_pct'
    row = reaction()
    row['field_known_at']['sustain_5d_pct'] = '2026-10-02T12:00:00Z'
    assert admit_local_reaction(row, CLOCK, 'strict_pit')['reason'] == 'feature_known_after_source_observation:sustain_5d_pct'


@pytest.mark.parametrize('evidence', [
    {'reporters': [None], 'reactions': []},
    {'reporters': [], 'reactions': [{'event': []}]},
    {'reporters': [], 'reactions': None},
])
def test_malformed_local_evidence_refuses_without_fallback(evidence):
    result = brief.generate_local_brief(observation_ts=CLOCK, evidence=evidence, mode='strict_pit')
    assert not result['available'] and result['reason']


def test_local_batch_and_symbol_limits_are_explicit():
    assert not local([reaction('q' + str(i)) for i in range(401)])['available']
    reporters = [reporter('r' + str(i)) for i in range(13)]
    for i, row in enumerate(reporters):
        row['event']['ticker'] = 'SYNTH' + str(i)
    assert local(reporters=reporters)['reason'] == 'local_symbol_limit_exceeded'


def test_mixed_fiscal_date_aliases_cannot_make_three_quarters_four():
    rows = [reaction('q' + str(i), day) for i, day in enumerate(
        ['2025-12-01', '2026-03-02', '2026-09-01'])]
    alias = deepcopy(rows[-1])
    alias['event']['event_id'] = 'alias'
    alias['event']['fiscal_date_ending'] = date(2026, 6, 30)
    alias['receipt']['event_id'] = 'alias'
    alias['event']['timing_sources'][0]['receipt']['event_id'] = 'alias'
    result = local(rows + [alias])
    context = result['next_contexts'][0]
    assert context['n_quarters'] < 4
    assert context['classification'] == brief.CLASS_INSUFFICIENT
    assert any(r['reason'] == 'duplicate_reaction_or_quarter_identity' for r in result['rejections'])


def test_valid_mixed_reported_dates_produce_ordered_history():
    rows = [reaction('q' + str(i), day) for i, day in enumerate(
        ['2025-12-01', '2026-03-02', '2026-06-01', '2026-09-01'])]
    rows[1]['event']['reported_date'] = date(2026, 3, 2)
    rows[2]['event']['fiscal_date_ending'] = date(2026, 3, 31)
    result = local(rows)
    assert result['available'], result
    context = result['next_contexts'][0]
    assert context['n_quarters'] == 4
    assert context['classification'] == brief.CLASS_SELL
    assert [r['reported_date'] for r in context['history_rows']] == [
        '2026-09-01', '2026-06-01', '2026-03-02', '2025-12-01']
    assert all(type(r['reported_date']) is str and type(r['fiscal_date_ending']) is str
               for r in context['history_rows'])


@pytest.mark.parametrize('mismatch', ['reported_date', 'fiscal_date'])
def test_recap_requires_target_reported_and_optional_fiscal_identity(mismatch):
    target = reporter('last-event', '2026-10-06')
    target['event']['fiscal_date_ending'] = date(2026, 9, 30)
    row = reaction('last-event', '2026-09-01' if mismatch == 'reported_date' else '2026-10-06')
    if mismatch == 'fiscal_date':
        row['event']['fiscal_date_ending'] = '2026-06-30'
        row['receipt'] = receipt('last-event', '2026-10-07T12:00:00Z')
        row['event']['timing_sources'][0]['receipt'] = row['receipt']
        row['field_known_at']['reaction_gap_pct'] = '2026-10-06T14:00:00Z'
    result = local([row], reporters=[target])
    context = result['last_session_contexts'][0]
    assert not context['recap_available']
    assert context['latest_reaction'] is None
    assert any(r['reason'] == 'recap_target_identity_mismatch' for r in result['rejections'])
    # A genuinely earlier quarter may still supply historical context.
    assert context['n_quarters'] == (1 if mismatch == 'reported_date' else 0)


@pytest.mark.parametrize('database_dates', [False, True])
def test_matching_recap_accepts_canonical_optional_fiscal_identity(database_dates):
    target = reporter('last-event', '2026-10-06')
    target['event']['fiscal_date_ending'] = '2026-09-30'
    row = reaction('last-event', '2026-10-06')
    row['receipt'] = receipt('last-event', '2026-10-07T12:00:00Z')
    row['event']['timing_sources'][0]['receipt'] = row['receipt']
    row['field_known_at']['reaction_gap_pct'] = '2026-10-06T14:00:00Z'
    if database_dates:
        target['event']['reported_date'] = date(2026, 10, 6)
        row['event']['reported_date'] = date(2026, 10, 6)
        row['event']['fiscal_date_ending'] = date(2026, 9, 30)
    result = local([row], reporters=[target])
    context = result['last_session_contexts'][0]
    assert context['recap_available']
    assert context['latest_reaction']['reported_date'] == '2026-10-06'
    assert context['latest_reaction']['fiscal_date_ending'] == '2026-09-30'
    assert context['latest_reaction']['event_id'] == 'last-event'


@pytest.mark.parametrize('field', ['reported_date', 'fiscal_date_ending'])
def test_invalid_local_dates_refuse_before_identity_and_sort(field):
    row = reaction()
    row['event'][field] = 'invalid-date'
    result = local([row])
    assert result['available']
    assert result['next_contexts'][0]['n_quarters'] == 0
    assert any('Invalid isoformat string' in r['reason'] for r in result['rejections'])
