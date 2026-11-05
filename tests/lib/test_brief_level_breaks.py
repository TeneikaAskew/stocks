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


@pytest.mark.parametrize('side', ['call', 'put'])
def test_brief_row_can_score_five_of_five(side):
    """The brief row reaches 5/5 when every condition holds; before the flags
    existed on this path the level-break factor could never score."""
    df = _daily()
    last = len(df) - 1
    if side == 'call':
        df.iloc[last, df.columns.get_loc('Close')] = df['High'].iloc[last - 1] + 1.0
    else:
        df.iloc[last, df.columns.get_loc('Close')] = df['Low'].iloc[last - 1] - 1.0
    df.iloc[last, df.columns.get_loc('High')] = max(df['High'].iloc[last], df['Close'].iloc[last])
    df.iloc[last, df.columns.get_loc('Low')] = min(df['Low'].iloc[last], df['Close'].iloc[last])
    row = add_brief_indicators(df, close_col='Close').iloc[-1].copy()
    if side == 'call':
        assert row['Broke_Prev_Day_High'] == 1
        row[['Consecutive_Down', 'RSI14', 'Price_vs_VWAP', 'StochRSI_K']] = [3, 40.0, -1.0, 10.0]
        score, conditions = check_call_conditions(row)
        assert 'level_break_pdh' in conditions
    else:
        assert row['Broke_Prev_Day_Low'] == 1
        row[['Consecutive_Up', 'RSI14', 'Price_vs_VWAP', 'StochRSI_K']] = [3, 60.0, 1.0, 90.0]
        score, conditions = check_put_conditions(row)
        assert 'level_break_pdl' in conditions
    assert score == 5
