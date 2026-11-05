"""The brief's level-break conditions: Broke_Prev_Day_High / Broke_Prev_Day_Low.

check_call_conditions / check_put_conditions score `level_break_pdh` /
`level_break_pdl` from these two columns. The brief scores the row of the
last completed session D (gcp/premarket_brief.py keeps bars dated before the
analysis date), so the flags compare D's close with the high / low of the
session before it, the definition calculate_historical_levels and
lib/trading_analysis.py already use. Only bars up to D are read.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.indicators import add_brief_indicators, calculate_historical_levels
from lib.signals import check_call_conditions, check_put_conditions


def _daily(n: int = 60, seed: int = 4) -> pd.DataFrame:
    """Daily bars shaped like the brief's SQL frame: a session-label
    DatetimeIndex plus the Time column _load_daily_from_sql adds."""
    rng = np.random.RandomState(seed)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1.0, n)))
    idx = pd.bdate_range('2026-06-01', periods=n, name='Time')
    df = pd.DataFrame({
        'Open': close.shift(1).fillna(close.iloc[0]).to_numpy(),
        'High': (close + rng.uniform(0.2, 1.5, n)).to_numpy(),
        'Low': (close - rng.uniform(0.2, 1.5, n)).to_numpy(),
        'Close': close.to_numpy(),
        'Volume': rng.randint(1e6, 5e6, n).astype(float),
    }, index=idx)
    df['Time'] = df.index
    return df


def test_brief_indicators_produce_the_level_break_flags():
    df = _daily()
    out = add_brief_indicators(df, close_col='Close')
    prev_high = df['High'].shift(1)
    prev_low = df['Low'].shift(1)
    expected_high = (df['Close'] > prev_high).astype(int)
    expected_low = (df['Close'] < prev_low).astype(int)
    assert out['Broke_Prev_Day_High'].tolist() == expected_high.tolist()
    assert out['Broke_Prev_Day_Low'].tolist() == expected_low.tolist()
    # Both outcomes occur in the fixture, so the comparison is not vacuous.
    assert set(out['Broke_Prev_Day_High']) == {0, 1}
    assert set(out['Broke_Prev_Day_Low']) == {0, 1}
    # The first session has no prior session: no break.
    assert out['Broke_Prev_Day_High'].iloc[0] == 0 and out['Broke_Prev_Day_Low'].iloc[0] == 0


def test_brief_level_breaks_match_calculate_historical_levels():
    df = _daily()
    out = add_brief_indicators(df, close_col='Close')
    ref = calculate_historical_levels(df['Time'], df['High'], df['Low'], df['Open'], df['Close'])
    assert out['Broke_Prev_Day_High'].tolist() == ref['Broke_Prev_Day_High'].tolist()
    assert out['Broke_Prev_Day_Low'].tolist() == ref['Broke_Prev_Day_Low'].tolist()


def test_brief_level_breaks_use_the_index_when_there_is_no_time_column():
    df = _daily().drop(columns='Time')
    out = add_brief_indicators(df, close_col='Close')
    assert out['Broke_Prev_Day_High'].tolist() == (df['Close'] > df['High'].shift(1)).astype(int).tolist()


def test_brief_level_breaks_read_no_later_bar():
    """Appending later sessions, or changing them, leaves every earlier flag as it was."""
    df = _daily(80)
    cut = 50
    early = add_brief_indicators(df.iloc[:cut].copy(), close_col='Close')
    later = df.copy()
    later.iloc[cut:, later.columns.get_loc('High')] += 50.0
    later.iloc[cut:, later.columns.get_loc('Low')] -= 50.0
    full = add_brief_indicators(later, close_col='Close')
    for col in ('Broke_Prev_Day_High', 'Broke_Prev_Day_Low'):
        assert full[col].iloc[:cut].tolist() == early[col].tolist()


_SIDES = {
    'call': (check_call_conditions, 'Broke_Prev_Day_High', 'level_break_pdh', 'consecutive_down',
             ['consecutive_down', 'rsi_oversold_zone', 'below_vwap', 'stoch_rsi_oversold']),
    'put': (check_put_conditions, 'Broke_Prev_Day_Low', 'level_break_pdl', 'consecutive_up',
            ['consecutive_up', 'rsi_overbought_zone', 'above_vwap', 'stoch_rsi_overbought']),
}


@pytest.mark.parametrize('side', ['call', 'put'])
def test_a_broken_level_adds_exactly_one_point_on_real_bars(side):
    """Every indicator comes from add_brief_indicators on the bars; nothing is
    overwritten. A close above the prior high (below the prior low) is an up
    (down) close, so it never holds with three down (up) closes and the
    realizable maximum stays 4 of 5."""
    check, flag, factor, consecutive, others = _SIDES[side]
    from gcp.premarket_brief import _resolve_signal_status
    rows = add_brief_indicators(_daily(250), close_col='Close')
    broken = rows[rows[flag] == 1]
    assert len(broken) > 0
    crossed = 0
    for _, row in broken.iterrows():
        score, conditions = check(row)
        without, _ = check(row, enabled_conditions=others)
        assert factor in conditions and consecutive not in conditions
        assert score == without + 1 <= 4
        bias = 'bullish' if side == 'call' else 'bearish'
        if without == 2:
            # the default premarket thresholds: building at 2, setup at 3
            assert 'building' in _resolve_signal_status(
                without if side == 'call' else 0, without if side == 'put' else 0, bias, 3, 2)
            assert 'setup' in _resolve_signal_status(
                score if side == 'call' else 0, score if side == 'put' else 0, bias, 3, 2)
            crossed += 1
    assert crossed > 0
