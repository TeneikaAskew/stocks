"""FEAT-SIGNAL-001: every voter signal carries a realized outcome under a fixed exit.

docs/superpowers/specs/2026-11-11-feat-signal-001-honest-outcome-scoring.md

``return_pct`` is the best close of the next 20 rows (a maximum favourable
excursion). ``realized_return_pct`` is rule ``next-open-20m-1c-v1``: enter at the
open of the bar after the signal bar, exit at the open 20 bars after the entry,
one cent of cost, only for a signal bar inside 09:30 to 15:34 Eastern whose
entry and exit bars open before the same session's close; otherwise NULL.

The frames are synthetic one-minute bars whose ``Time`` is naive Eastern wall
time, as scripts/run_historical_signals.py passes them after
``utc_to_eastern_naive``. The indicator columns the voter reads are set so that
it fires exactly on the chosen bars and nowhere else.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.trading_analysis import MarketAnalyzer

RULE = 'next-open-20m-1c-v1'


def _day(day: str, start: str = '04:00', end: str = '19:59') -> pd.DataFrame:
    t = pd.date_range(f'{day} {start}', f'{day} {end}', freq='1min')
    return pd.DataFrame({'Time': t, 'Open': 100.0, 'High': 100.0, 'Low': 100.0,
                         'Last': 100.0, 'Volume': 1000})


def _at(df: pd.DataFrame, when: str) -> int:
    hits = np.flatnonzero(df['Time'].to_numpy() == np.datetime64(pd.Timestamp(when)))
    assert len(hits) == 1, when
    return int(hits[0])


def _arm(df: pd.DataFrame, fires: dict[str, str]) -> pd.DataFrame:
    """Neutral indicators everywhere; the voter's call (put) conditions on the
    bars named in ``fires`` (time -> 'call' | 'put')."""
    df = df.copy()
    df['High'] = df[['Open', 'Last']].max(axis=1)
    df['Low'] = df[['Open', 'Last']].min(axis=1)
    df['RSI14_W'] = 50.0
    df['StochRSI_K'] = 50.0
    df['VWAP'] = df['Last']
    df['EMA9'] = df['Last']
    df['EMA20'] = df['Last']
    df['RVol_Recent_20'] = np.nan
    df['ATR_Expansion'] = np.nan
    df['RSI_Thrust_3'] = np.nan
    for when, side in fires.items():
        i = _at(df, when)
        call = side == 'call'
        df.loc[i, 'RSI14_W'] = 40.0 if call else 60.0
        df.loc[i, 'VWAP'] = df.loc[i, 'Last'] - (0.2 if call else -0.2)
        df.loc[i, 'EMA9'] = df.loc[i, 'Last'] - (0.1 if call else -0.1)
        df.loc[i, 'RVol_Recent_20'] = 2.0
        df.loc[i, 'ATR_Expansion'] = 2.0
        df.loc[i, 'RSI_Thrust_3'] = 10.0 if call else -10.0
    return df


def _set(df: pd.DataFrame, when: str, **cols) -> None:
    i = _at(df, when)
    for k, v in cols.items():
        df.loc[i, k] = v


def _regular_frame() -> tuple[pd.DataFrame, dict[str, str]]:
    df = _day('2026-05-06')
    # Call on the 10:00 bar: one of the next 20 closes (10:05) is above its
    # 100.00 close, but the exit open (10:21, 20 bars after the 10:01 entry
    # open of 100.10) is 99.90.
    _set(df, '2026-05-06 10:01', Open=100.10)
    _set(df, '2026-05-06 10:05', Last=100.50)
    _set(df, '2026-05-06 10:21', Open=99.90)
    # Put on the 11:00 bar, the mirror.
    _set(df, '2026-05-06 11:01', Open=99.90)
    _set(df, '2026-05-06 11:05', Last=99.50)
    _set(df, '2026-05-06 11:21', Open=100.10)
    # Bounds: 09:30 and 15:34 score, 09:00 premarket and 15:35 do not.
    _set(df, '2026-05-06 09:31', Open=100.20)
    _set(df, '2026-05-06 09:51', Open=100.40)
    _set(df, '2026-05-06 15:35', Open=100.30)
    _set(df, '2026-05-06 15:55', Open=100.60)
    _set(df, '2026-05-06 09:05', Last=100.70)
    _set(df, '2026-05-06 15:40', Last=100.80)
    fires = {'2026-05-06 10:00': 'call', '2026-05-06 11:00': 'put',
             '2026-05-06 09:30': 'call', '2026-05-06 15:34': 'call',
             '2026-05-06 09:00': 'call', '2026-05-06 15:35': 'call'}
    return _arm(df, fires), fires


def _signals(df: pd.DataFrame) -> pd.DataFrame:
    return MarketAnalyzer().generate_technical_signals(df)


def _row(sig: pd.DataFrame, when) -> pd.Series:
    m = pd.to_datetime(sig['entry_time']) == pd.Timestamp(when)
    assert m.sum() == 1, when
    return sig.loc[m].iloc[0]


def test_every_signal_carries_the_realized_rule():
    df, fires = _regular_frame()
    sig = _signals(df)
    assert sorted(pd.to_datetime(sig['entry_time'])) == sorted(pd.Timestamp(t) for t in fires)
    assert 'realized_return_pct' in sig.columns
    assert (sig['realized_rule'] == RULE).all()


def test_call_with_a_better_close_but_a_lower_exit_open_realizes_a_loss():
    sig = _signals(_regular_frame()[0])
    r = _row(sig, '2026-05-06 10:00')
    assert r['trade_type'] == 'call'
    assert r['return_pct'] > 0
    assert r['return_pct'] == pytest.approx(0.5)
    expected = (99.90 - 100.10 - 0.01) / 100.10 * 100
    assert r['realized_return_pct'] < 0
    assert r['realized_return_pct'] == pytest.approx(expected)


def test_put_is_the_mirror():
    sig = _signals(_regular_frame()[0])
    r = _row(sig, '2026-05-06 11:00')
    assert r['trade_type'] == 'put'
    assert r['return_pct'] == pytest.approx(0.5)
    expected = (-(100.10 - 99.90) - 0.01) / 99.90 * 100
    assert r['realized_return_pct'] == pytest.approx(expected)


def test_regular_hours_bounds():
    sig = _signals(_regular_frame()[0])
    assert _row(sig, '2026-05-06 09:30')['realized_return_pct'] == pytest.approx(
        (100.40 - 100.20 - 0.01) / 100.20 * 100)
    assert _row(sig, '2026-05-06 15:34')['realized_return_pct'] == pytest.approx(
        (100.60 - 100.30 - 0.01) / 100.30 * 100)
    # Before 09:30 and after 15:34: not scoreable, NULL and never 0.
    for when in ('2026-05-06 09:00', '2026-05-06 15:35'):
        r = _row(sig, when)
        assert r['return_pct'] > 0
        assert pd.isna(r['realized_return_pct'])
        assert r['realized_rule'] == RULE


def test_half_day_close_and_cross_session_exits_are_null():
    # 2025-11-28 closes at 13:00 (lib.eastern_time.session_close). A 12:38
    # signal exits on the 12:59 bar and scores; a 12:39 signal's exit bar is
    # 13:00, at the close, and is NULL although the frame has that bar.
    half = _day('2025-11-28')
    _set(half, '2025-11-28 12:39', Open=100.10)
    _set(half, '2025-11-28 12:59', Open=100.30)
    # A full session whose bars stop at 15:45, so a 15:30 signal's exit row
    # falls on the next session: NULL.
    cut = _day('2025-12-01', end='15:45')
    nxt = _day('2025-12-02', start='09:30', end='11:00')
    df = pd.concat([half, cut, nxt], ignore_index=True)
    fires = {'2025-11-28 12:38': 'call', '2025-11-28 12:39': 'call', '2025-12-01 15:30': 'put'}
    for when in fires:
        _set(df, pd.Timestamp(when) + pd.Timedelta(minutes=3), Last=100.40)
    df = _arm(df, fires)
    sig = _signals(df)
    assert _row(sig, '2025-11-28 12:38')['realized_return_pct'] == pytest.approx(
        (100.30 - 100.10 - 0.01) / 100.10 * 100)
    assert pd.isna(_row(sig, '2025-11-28 12:39')['realized_return_pct'])
    assert pd.isna(_row(sig, '2025-12-01 15:30')['realized_return_pct'])


def test_tz_aware_frame_is_read_in_eastern_time():
    df, _ = _regular_frame()
    naive = _signals(df)
    aware = df.assign(Time=pd.DatetimeIndex(df['Time']).tz_localize('America/New_York')
                      .tz_convert('UTC'))
    sig = _signals(aware)
    assert len(sig) == len(naive)
    np.testing.assert_allclose(sig['realized_return_pct'].to_numpy(dtype=float),
                               naive['realized_return_pct'].to_numpy(dtype=float),
                               equal_nan=True)
    # Read as UTC, the 10:00 ET call (14:00 UTC) would be scored from 14:01.
    assert _row(sig, pd.Timestamp('2026-05-06 14:00', tz='UTC'))['realized_return_pct'] < 0


def test_best_case_columns_and_signal_set_are_unchanged():
    df, fires = _regular_frame()
    sig = _signals(df)
    last = df['Last'].to_numpy()
    for _, r in sig.iterrows():
        i = _at(df, r['entry_time'])
        call = r['trade_type'] == 'call'
        best = {}
        for w in (5, 10, 15, 20, 30, 45, 60):
            fut = last[i + 1:i + 1 + w]
            best[w] = ((fut.max() - last[i]) if call else (last[i] - fut.min())) / last[i] * 100
            assert r[f'return_{w}min'] == pytest.approx(best[w])
        assert r['return_pct'] == pytest.approx(best[20])
        assert r['best_return'] == pytest.approx(max([0.0] + list(best.values())))
        fut20 = last[i + 1:i + 21]
        assert r['duration_minutes'] == (np.argmax(fut20) if call else np.argmin(fut20)) + 1
        assert r['entry_price'] == pytest.approx(last[i])


def test_helper_reads_positions_and_directions():
    from lib.trading_analysis import realized_outcome

    df, _ = _regular_frame()
    i = _at(df, '2026-05-06 10:00')
    out = realized_outcome(df, [i, i], [1, -1])
    assert out[0] == pytest.approx((99.90 - 100.10 - 0.01) / 100.10 * 100)
    assert out[1] == pytest.approx((-(99.90 - 100.10) - 0.01) / 100.10 * 100)
    # The frame itself is not changed.
    assert 'realized_return_pct' not in df.columns
