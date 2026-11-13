"""Hermetic tests for scripts/analysis/hold_sweep_experiment.py (no Cloud SQL)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.analysis.hold_sweep_experiment as hse  # noqa: E402
from lib.eastern_time import eastern_index_to_utc, utc_to_eastern_naive  # noqa: E402
from lib.trading_analysis import MarketAnalyzer, realized_outcome  # noqa: E402

DAYS = ['2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06']


def _bars_utc(days=DAYS, seed=1):
    """load_intraday_bars' shape: Time tz-aware UTC, 04:00 to 19:59 ET."""
    rng = np.random.default_rng(seed)
    et = pd.DatetimeIndex(np.concatenate([
        pd.date_range(f'{d} 04:00', f'{d} 19:59', freq='1min').to_numpy() for d in days]))
    n = len(et)
    close = 500 + np.cumsum(rng.normal(0, 0.15, n))
    open_ = np.r_[500.0, close[:-1]] + rng.normal(0, 0.03, n)
    hi = np.maximum(open_, close) + np.abs(rng.normal(0, 0.05, n))
    lo = np.minimum(open_, close) - np.abs(rng.normal(0, 0.05, n))
    vol = rng.integers(1_000, 50_000, n)
    vol[(et.hour == 9) & (et.minute == 30)] *= 20
    return pd.DataFrame({'Time': eastern_index_to_utc(et), 'Open': open_, 'High': hi,
                         'Low': lo, 'Last': close, 'Volume': vol})


def test_hold20_reproduces_production_realized_return():
    """Through the production path (Eastern frame -> voter -> entry_time back
    to UTC), hold=20 equals the stored realized_return_pct signal for signal."""
    bars = _bars_utc()
    eastern = bars.assign(Time=utc_to_eastern_naive(bars['Time']))
    analyzer = MarketAnalyzer()
    sigs = analyzer.generate_technical_signals(analyzer.add_technical_indicators(eastern))
    assert len(sigs) > 20, 'synthetic frame should produce signals'
    sigs = sigs.assign(entry_time=eastern_index_to_utc(pd.DatetimeIndex(sigs['entry_time'])))
    scored = hse.score_signals(bars, sigs, (5, 20, 60), 0.01)
    assert scored.attrs['unmatched'] == 0
    expected = sigs.set_index(pd.to_datetime(sigs['entry_time'], utc=True))['realized_return_pct']
    got = scored.set_index('entry_time')['r20']
    assert got.notna().sum() > 0
    np.testing.assert_allclose(got.to_numpy(), expected.loc[got.index].to_numpy(), equal_nan=True)


def test_other_holds_match_helper_called_directly():
    bars = _bars_utc()
    eastern = bars.assign(Time=utc_to_eastern_naive(bars['Time']))
    pos = np.array([300, 340, 341, 600, 700, 1200, 1400, 1500])
    sigs = pd.DataFrame({'entry_time': bars['Time'].iloc[pos].to_numpy(),
                         'trade_type': ['call', 'put'] * 4})
    scored = hse.score_signals(bars, sigs, (5, 45), 0.01)
    for h in (5, 45):
        direct = realized_outcome(eastern, pos, np.array([1, -1] * 4), hold=h, cost=0.01)
        np.testing.assert_allclose(scored[f'r{h}'].to_numpy(), direct, equal_nan=True)


def test_unmatched_signal_is_counted_not_scored():
    bars = _bars_utc()
    sigs = pd.DataFrame({'entry_time': [pd.Timestamp('2026-11-10 15:00', tz='UTC')],
                         'trade_type': ['call']})
    scored = hse.score_signals(bars, sigs, (20,), 0.01)
    assert len(scored) == 0 and scored.attrs['unmatched'] == 1


def test_one_at_a_time_waits_for_the_exit():
    keep = hse.one_at_a_time(np.array([0, 5, 21, 22, 50]), 20)
    assert keep.tolist() == [True, False, True, False, True]


def test_month_chunks_cut_outside_sessions_and_cover_range():
    lo, hi = pd.Timestamp('2026-03-10 14:00', tz='UTC'), pd.Timestamp('2026-05-20 15:00', tz='UTC')
    chunks = list(hse._month_chunks(lo, hi))
    assert chunks[0][0] <= lo and chunks[-1][1] > hi
    for (a, b), (c, _) in zip(chunks, chunks[1:]):
        assert b == c and b.hour == 6   # 01:00 or 02:00 ET, no session open


def test_run_end_to_end_with_stubbed_reads(monkeypatch, tmp_path):
    bars = _bars_utc(days=DAYS + ['2026-11-09', '2026-11-10'])
    rng = np.random.default_rng(3)
    rth = pd.DatetimeIndex(utc_to_eastern_naive(pd.DatetimeIndex(bars['Time'])))
    cand = np.flatnonzero((rth.hour >= 10) & (rth.hour < 15))
    pos = np.sort(rng.choice(cand, 400, replace=False))
    sigs = pd.DataFrame({'entry_time': bars['Time'].iloc[pos].to_numpy(),
                         'trade_type': rng.choice(['call', 'put'], 400),
                         'strategy': 'momentum'})

    def fake_read(engine, sql, params):
        if 'DISTINCT ticker' in sql:
            return pd.DataFrame({'ticker': ['SPY']})
        return sigs.copy()

    import gcp.database
    import gcp.historical_signals
    monkeypatch.setattr(hse, '_read', fake_read)
    monkeypatch.setattr(gcp.database, 'get_engine', lambda: object())
    monkeypatch.setattr(gcp.historical_signals, 'load_intraday_bars',
                        lambda t, a, b: bars[(bars['Time'] >= a) & (bars['Time'] < b)].reset_index(drop=True))
    out = tmp_path / 'sweep.csv'
    assert hse.main(['--out', str(out), '--split', '2026-11-06']) == 0
    s = pd.read_csv(out)
    assert set(s['hold']) == {5, 10, 15, 20, 30, 45, 60}
    own20 = s[(s['set'] == 'own') & (s['count'] == 'all') & (s['hold'] == 20) & (s['period'] == 'all')]
    assert own20['n'].iloc[0] == 400   # every 10:00-14:59 signal is scoreable at 20
    common = s[(s['set'] == 'common') & (s['count'] == 'all') & (s['period'] == 'all')]
    assert common['n'].nunique() == 1  # same trades at every hold
    rec = pd.read_csv(tmp_path / 'sweep_recommend.csv')
    assert len(rec) == 1 and rec['chosen_hold'].iloc[0] in {5, 10, 15, 20, 30, 45, 60}
