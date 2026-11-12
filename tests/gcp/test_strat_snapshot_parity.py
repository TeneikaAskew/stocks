"""FEAT-STRAT-001 done_when 4: shared status reaches consumer adapters intact.

Bounded adapter acceptance through the actual producers (no stubbed status
dict), with all external I/O guarded. Not a storage migration or a full
production-brief replay.
"""
import socket

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError('external I/O attempted in isolated acceptance')
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)
    import gcp.database as database
    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: False)
    # The level parameter tables (per-ticker parameters, 2026-11-08), read
    # once per brief run: every key at the #1753 values.
    from tests.lib.level_params_fixtures import install_level_params
    install_level_params(monkeypatch)


def _daily(invalid=False):
    frame = pd.DataFrame([(100, 110, 90, 105), (105, 108, 92, 100),
                          (100, 107, 91, 99), (99, 106, 89, 104)],
                         index=pd.bdate_range('2026-10-05', periods=4),
                         columns=['Open', 'High', 'Low', 'Close'], dtype=float).assign(Volume=1000.)
    if invalid:
        # High below Low: malformed, still a non-null close (no row deletion).
        frame.iloc[-1, frame.columns.get_loc('High')] = 80.0
    return frame


def _brief(monkeypatch, frame):
    from gcp import premarket_brief as pb
    from lib.config import AppConfig
    from lib.data_loader import DataLoader
    cfg = AppConfig()
    cfg.market.tickers = ['IWM']
    for key, value in {'BRIEF_AS_OF': '2026-10-09', 'BRIEF_AMC_REACTIONS': '0',
                       'BRIEF_LLM_DISABLE': '1', 'BRIEF_TICKERS': 'IWM'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(DataLoader, 'load_daily', lambda *a, **k: frame.copy())
    monkeypatch.setattr(pb, 'add_brief_indicators',
                        lambda df, **k: df.assign(RSI=50., Consecutive_Up=0, Consecutive_Down=0))
    monkeypatch.setattr(pb, 'check_call_conditions', lambda row, **k: (4, []))
    monkeypatch.setattr(pb, 'check_put_conditions', lambda row, **k: (3, []))
    monkeypatch.setattr(pb, 'load_earnings_for_brief', lambda *a, **k: {'earnings': []})
    monkeypatch.setattr(pb, '_ew_recap_or_unavailable', lambda *a, **k: {})
    monkeypatch.setattr(pb, 'load_economic_events', lambda *a, **k: {'today': []})
    monkeypatch.setattr(pb, '_load_gamma_freshness', lambda *a, **k: dict(
        data_source='unavailable', snapshot_ts=None, snapshot_date=None, days_behind=None))
    # Stop the unrelated playbook/persistence branch at its isolated boundary.
    monkeypatch.setattr(pb, 'build_session_levels', lambda *a, **k: (_ for _ in ()).throw(
        ValueError('isolated playbook boundary')))
    monkeypatch.setattr(pb, '_delete_null_close_rows',
                        lambda *a: pytest.fail('STRAT must not delete invalid observations'))
    return pb, cfg


def test_foundation_brief_unavailable_is_not_inside(monkeypatch, no_network):
    pb, cfg = _brief(monkeypatch, _daily(invalid=True))
    brief = pb.generate_premarket_brief(cfg=cfg)
    out = brief['tickers']['IWM']
    assert out['strat_available'] is False
    assert out['strat_reason'] == 'invalid_ohlc'
    assert out['strat_observation_ts']
    assert out['strat_candle'] == 'X'           # never the old '1' inside bar
    assert out['strat_setup'] is False and out['strat_combo'] is None
    assert out['ftfc_score'] is None and out['ftfc_direction'] is None
    rendered = str(pb._build_ticker_fields(brief)).lower()
    assert 'daily: unavailable (invalid_ohlc)' in rendered
    assert 'tf bias: unavailable' in rendered
    assert 'daily: 1' not in rendered

    # Positive control through the same producer: a valid latest bar keeps
    # its real classification and score.
    pb, cfg = _brief(monkeypatch, _daily())
    good = pb.generate_premarket_brief(cfg=cfg)['tickers']['IWM']
    assert good['strat_available'] is True and good['strat_reason'] is None
    assert good['strat_candle'] == '2D'
    assert isinstance(good['ftfc_score'], float)
    assert good['ftfc_direction'] in ('bullish', 'bearish', 'mixed')


def _nov5_daily(ticker):
    from tests.lib.test_strat import nov5_daily
    return nov5_daily(ticker)


@pytest.mark.parametrize('ticker, ftfc_line, tf_bias_line, labels_line, state', [
    ('QQQ', 'FTFC: bearish (Q red, M red, W red)', 'TF bias: +0.5 (bullish)',
     '1D:2U 1W:2D 1M:2D', 'bearish'),
    ('IWM', 'FTFC: bullish (Q green, M green, W green)', 'TF bias: +1.0 (bullish)',
     '1D:2U 1W:2U 1M:2U', 'bullish'),
    ('SPY', 'FTFC: bullish (Q green, M green, W green)', 'TF bias: +1.0 (bullish)',
     '1D:2U 1W:2U 1M:1', 'bullish'),
])
def test_nov5_brief_strat_box_shows_tf_bias_and_ftfc(monkeypatch, no_network, ticker,
                                                     ftfc_line, tf_bias_line, labels_line, state):
    """The 2026-11-05 08:30 ET brief through the actual producer on captured
    bars: QQQ's latest close 691.95 is below the week and month open 695.315
    (2026-11-02) and the quarter open, so FTFC is bearish while the weighted
    vote (TF bias) reads +0.5 bullish. The signal gate follows TF bias."""
    import json
    pb, cfg = _brief(monkeypatch, _nov5_daily(ticker))
    cfg.market.tickers = [ticker]
    monkeypatch.setenv('BRIEF_AS_OF', '2026-11-05')
    monkeypatch.setenv('BRIEF_TICKERS', ticker)
    brief = pb.generate_premarket_brief(cfg=cfg)
    out = brief['tickers'][ticker]
    assert out['strat_observation_ts'] == '2026-11-05T08:30:00-05:00'
    assert out['tf_continuity'] == state
    assert set(out['tf_continuity_frames']) == {'1q', '1mo', '1w'}
    for frame in out['tf_continuity_frames'].values():
        assert frame['observed_price'] == out['price']
        assert frame['price_provenance'] == 'latest_completed_close'
        assert frame['price_session'] == '2026-11-04'
        assert frame['rule_version'] == 'price-open-v1'
    if ticker == 'QQQ':
        assert out['price'] == 691.95
        assert out['tf_continuity_frames']['1w']['open'] == 695.315
        assert out['tf_continuity_frames']['1mo']['open'] == 695.315
    strat = next(f['value'] for f in pb._build_ticker_fields(brief) if f['name'] == f'{ticker} Strat')
    lines = strat.split('\n')
    assert lines[lines.index(tf_bias_line) + 1] == labels_line
    assert lines[lines.index(labels_line) + 1] == ftfc_line
    # The gate reads the weighted vote: CALL side under bullish TF bias,
    # even where FTFC is bearish (check_call_conditions=4, put=3 above).
    assert out['ftfc_direction'] == 'bullish'
    def gate(direction):
        return pb._resolve_signal_status(
            call_score=4, put_score=3, ftfc_direction=direction,
            signal_threshold=cfg.signal.premarket_signal_threshold,
            building_threshold=cfg.signal.premarket_building_threshold)
    assert out['signal_status'] == gate('bullish')
    assert gate('bullish') != gate('bearish')
    json.dumps(out['tf_continuity_frames'])   # storable as JSONB


@pytest.mark.parametrize('ticker, ftfc_line', [
    ('QQQ', 'FTFC: unavailable (Q red, M opens today, W opens today)'),
    ('IWM', 'FTFC: unavailable (Q green, M opens today, W opens today)'),
    ('SPY', 'FTFC: unavailable (Q red, M opens today, W opens today)'),
])
def test_first_session_of_month_and_week_keeps_judged_frames(monkeypatch, no_network,
                                                             ticker, ftfc_line):
    """The 2026-11-02 (Monday, first session of November) 08:30 ET brief on
    captured bars through 2026-10-30. The week and month open at 09:30, so
    the state is unavailable and nothing claims agreement, while the quarter
    (opened 2026-10-01) is still judged, stored and shown."""
    import json
    daily = _nov5_daily(ticker)
    pb, cfg = _brief(monkeypatch, daily[daily.index <= '2026-10-30'])
    cfg.market.tickers = [ticker]
    monkeypatch.setenv('BRIEF_AS_OF', '2026-11-02')
    monkeypatch.setenv('BRIEF_TICKERS', ticker)
    brief = pb.generate_premarket_brief(cfg=cfg)
    out = brief['tickers'][ticker]
    assert out['strat_observation_ts'] == '2026-11-02T08:30:00-05:00'
    assert out['tf_continuity'] == 'unavailable'
    frames = out['tf_continuity_frames']
    assert frames['1q']['relation'] in ('green', 'red')
    assert frames['1q']['observed_price'] == out['price']
    assert frames['1q']['price_session'] == '2026-10-30'
    for tf in ('1mo', '1w'):
        assert frames[tf]['relation'] == 'unavailable' and frames[tf]['open'] is None
        assert frames[tf]['reasons'][0] == 'period_opens_after_clock'
    strat = next(f['value'] for f in pb._build_ticker_fields(brief) if f['name'] == f'{ticker} Strat')
    assert strat.split('\n')[-1] == ftfc_line
    json.dumps(frames)   # storable as JSONB


def _diagnostic_module():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / 'scripts/research/strat_foundation_diagnostic.py'
    spec = importlib.util.spec_from_file_location('strat_foundation_diagnostic', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_captured_foundation_diagnostic_matches_actual_producers(no_network):
    """done_when 5: the committed diagnostic over captured IWM rows agrees
    with the actual producers and adapters run now, binds exact input/code/
    config hashes and the retained visual, keeps unavailable cases, and
    states its retrospective-vintage limits."""
    import hashlib
    import json
    import re
    diag = _diagnostic_module()
    root = diag.ROOT
    manifest = json.loads((root / diag.ARTIFACT_DIR / 'manifest.json').read_text())
    assert manifest['diagnostic_version'] == diag.DIAGNOSTIC_VERSION
    assert manifest['input']['sha256'] == diag.sha256_file(root / diag.FIXTURE)
    assert set(manifest['code_sha256']) == set(diag.CODE_FILES)
    assert all(re.fullmatch('[0-9a-f]{64}', h) for h in manifest['code_sha256'].values())
    assert manifest['limitations'] == diag.LIMITATIONS
    assert any('not_point_in_time' in item for item in manifest['limitations'])
    summary = manifest['summary']
    assert summary['all_checks_pass'] is True
    assert summary['unavailable_cases'], 'unavailable cases must be retained, not omitted'
    assert summary['weekly_confirmed_cases']
    for case in manifest['cases']:
        assert all(case['checks'].values()), case['case']
        assert pd.Timestamp(case['status']['observation_ts']) == pd.Timestamp(case['clock'])
    # Retained visual is bound by hash and is exactly what the manifest renders.
    svg = (root / manifest['visual']['path']).read_text()
    assert hashlib.sha256(svg.encode()).hexdigest() == manifest['visual']['sha256']
    assert svg == diag.render_svg({k: v for k, v in manifest.items() if k != 'visual'})

    # Re-run a representative subset through the actual producers now.
    frame, legacy = diag.load_fixture(root)
    cases = {c['case']: c for c in manifest['cases']}
    weekly = summary['weekly_confirmed_cases']
    week_close = next(name for name in weekly if name.startswith('week_close_'))
    picks = ['before_second_bar', summary['unavailable_cases'][-1], week_close,
             week_close.replace('week_close_', 'week_pre_close_')]
    with diag.isolated(frame):
        for name in picks:
            fresh = diag.run_case(frame, legacy, {'case': name, 'clock': cases[name]['clock']})
            assert json.loads(json.dumps(fresh)) == cases[name], name
