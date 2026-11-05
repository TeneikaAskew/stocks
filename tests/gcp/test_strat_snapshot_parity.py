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
    monkeypatch.setattr(pb, 'check_call_conditions', lambda row: (4, []))
    monkeypatch.setattr(pb, 'check_put_conditions', lambda row: (3, []))
    monkeypatch.setattr(pb, 'load_earnings_for_brief', lambda *a, **k: {'earnings': []})
    monkeypatch.setattr(pb, '_ew_recap_or_unavailable', lambda *a, **k: {})
    monkeypatch.setattr(pb, 'load_economic_events', lambda *a, **k: {'today': []})
    monkeypatch.setattr(pb, '_load_gamma_freshness', lambda *a, **k: dict(
        data_source='unavailable', snapshot_ts=None, snapshot_date=None, days_behind=None))
    # Stop the unrelated playbook/persistence branch at its isolated boundary.
    monkeypatch.setattr(pb, 'build_level_map', lambda **k: (_ for _ in ()).throw(
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
    assert 'ftfc: unavailable' in rendered
    assert 'daily: 1' not in rendered

    # Positive control through the same producer: a valid latest bar keeps
    # its real classification and score.
    pb, cfg = _brief(monkeypatch, _daily())
    good = pb.generate_premarket_brief(cfg=cfg)['tickers']['IWM']
    assert good['strat_available'] is True and good['strat_reason'] is None
    assert good['strat_candle'] == '2D'
    assert isinstance(good['ftfc_score'], float)
    assert good['ftfc_direction'] in ('bullish', 'bearish', 'mixed')
