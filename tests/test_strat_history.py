"""Tests for the Strat history tape + 1-3-1 detection + upcoming setup.

Covers the additions powering the ticker-list → historical-strat panel:
  - 1-3-1 (coil → expansion → coil) combo detection in detect_combos
  - lib.strat.compute_strat_history (per-timeframe tape + upcoming setup)
  - quarterly ('1q') resampling

All hermetic — synthetic OHLCV, no DB.
"""
import numpy as np
import pandas as pd
import pytest

from lib.strat import (
    StratClassifier, compute_strat_history, _upcoming_setup, _last_directional,
)


def _frame(bars):
    df = pd.DataFrame(bars, columns=['High', 'Low', 'Open', 'Close'])
    df['Volume'] = 1000
    return df


def _daily_frame(bars, start='2024-01-01'):
    """bars = list of (H, L, O, C); index is consecutive trading days."""
    df = _frame(bars)
    df.index = pd.date_range(start, periods=len(bars), freq='B')
    return df


# ── 1-3-1 detection ────────────────────────────────────────────────────────

class TestOneThreeOne:
    def test_131_detected(self):
        clf = StratClassifier()
        # bar0 baseline; bar1 inside(1); bar2 outside(3); bar3 inside(1)
        df = _frame([
            (100, 90, 95, 96),   # bar0
            (99, 91, 95, 96),    # bar1 → 1 (inside of bar0)
            (100, 90, 95, 96),   # bar2 → 3 (outside of bar1)
            (99, 91, 95, 96),    # bar3 → 1 (inside of bar2)
        ])
        res = clf.detect_combos(df)
        assert res['strat_candle'].tolist() == ['X', '1', '3', '1']
        assert res['strat_combo'].iloc[3] == '131_setup'
        # the 1-3-1 third bar is an inside bar → pending break setup
        assert bool(res['strat_setup'].iloc[3]) is True

    def test_131_requires_outside_middle(self):
        clf = StratClassifier()
        # 1-1-1 (no outside middle) must NOT be tagged 131
        df = _frame([
            (100, 90, 95, 96),
            (99, 91, 95, 96),    # 1
            (98, 92, 95, 96),    # 1
            (97, 93, 95, 96),    # 1
        ])
        res = clf.detect_combos(df)
        assert res['strat_combo'].iloc[3] != '131_setup'
        assert 'inside_compression' in res['strat_combo'].iloc[3]


# ── upcoming setup ──────────────────────────────────────────────────────────

class TestUpcomingSetup:
    def test_trigger_lines_and_mid(self):
        clf = StratClassifier()
        df = _frame([
            (100, 90, 95, 96),
            (102, 92, 95, 101),   # 2U
        ])
        labels = clf.classify_series(df)
        combos = clf.detect_combos(df, labels)
        up = _upcoming_setup(df, labels, combos)
        assert up['trigger_high'] == 102.0
        assert up['trigger_low'] == 92.0
        assert up['mid_trigger'] == pytest.approx(97.0)

    def test_direction_read_after_2d(self):
        # most recent directional bar is 2D → break up reverses, break down continues
        labels = pd.Series(['X', '2U', '2D'])
        assert _last_directional(labels) == '2D'
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100), (99, 88, 95, 89)])
        clf = StratClassifier()
        lab = clf.classify_series(df)
        up = _upcoming_setup(df, lab, clf.detect_combos(df, lab))
        assert up['break_up'] == '2U reversal'
        assert up['break_down'] == '2D continuation'


# ── compute_strat_history ───────────────────────────────────────────────────

class TestComputeStratHistory:
    @pytest.fixture
    def daily(self):
        # ~260 business days (>1y) so weekly/monthly/quarterly all have bars
        rng = np.random.default_rng(7)
        n = 260
        close = 100 + np.cumsum(rng.normal(0, 1, n))
        high = close + rng.uniform(0.5, 2.0, n)
        low = close - rng.uniform(0.5, 2.0, n)
        openp = close + rng.normal(0, 0.5, n)
        return _daily_frame(list(zip(high, low, openp, close)))

    def test_structure_all_timeframes(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=10)
        assert res['available'] is True
        assert res['ticker'] == 'TEST'
        for tf in ('1d', '1w', '1mo', '1q'):
            assert tf in res['timeframes'], f"missing {tf}"
            block = res['timeframes'][tf]
            assert block['available'] is True
            assert len(block['history']) <= 10 and len(block['history']) >= 1
            # every record has the canonical fields
            rec = block['history'][-1]
            for k in ('period', 'open', 'high', 'low', 'close', 'candle',
                      'combo', 'is_continuation', 'is_reversal', 'is_inside',
                      'is_setup'):
                assert k in rec, f"{tf} record missing {k}"
            assert rec['candle'] in ('1', '2U', '2D', '3', 'X')
            # upcoming setup present with trigger lines
            up = block['upcoming']
            assert up['trigger_high'] is not None
            assert up['trigger_low'] is not None
            assert up['break_up'].startswith('2U')
            assert up['break_down'].startswith('2D')
        # current == last history bar
        assert res['timeframes']['1d']['current'] == res['timeframes']['1d']['history'][-1]

    def test_quarterly_has_fewer_bars_than_daily(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=999)
        n_daily = len(res['timeframes']['1d']['history'])
        n_q = len(res['timeframes']['1q']['history'])
        assert n_q < n_daily  # quarterly aggregates many daily bars

    def test_insufficient_data(self):
        res = compute_strat_history('TEST', df=_daily_frame([(1, 0, 0.5, 0.5)]))
        assert res['available'] is False

    def test_flags_consistent_with_combo(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=999)
        for tf_block in res['timeframes'].values():
            for rec in tf_block['history']:
                assert rec['is_continuation'] == ('continuation' in rec['combo'])
                assert rec['is_reversal'] == ('reversal' in rec['combo'])
                assert rec['is_inside'] == (rec['candle'] == '1')
