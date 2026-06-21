"""Tests for the Strat history tape + 1-3-1 detection + upcoming setup.

Hermetic — synthetic OHLCV, no DB.
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
    df = _frame(bars)
    df.index = pd.date_range(start, periods=len(bars), freq='B')
    return df


class TestOneThreeOne:
    def test_131_detected(self):
        clf = StratClassifier()
        df = _frame([
            (100, 90, 95, 96),
            (99, 91, 95, 96),    # 1
            (100, 90, 95, 96),   # 3
            (99, 91, 95, 96),    # 1
        ])
        res = clf.detect_combos(df)
        assert res['strat_candle'].tolist() == ['X', '1', '3', '1']
        assert res['strat_combo'].iloc[3] == '131_setup'
        assert bool(res['strat_setup'].iloc[3]) is True

    def test_131_requires_outside_middle(self):
        clf = StratClassifier()
        df = _frame([
            (100, 90, 95, 96), (99, 91, 95, 96), (98, 92, 95, 96), (97, 93, 95, 96),
        ])
        res = clf.detect_combos(df)
        assert res['strat_combo'].iloc[3] != '131_setup'
        assert 'inside_compression' in res['strat_combo'].iloc[3]


class TestUpcomingSetup:
    def test_trigger_lines_and_mid(self):
        clf = StratClassifier()
        df = _frame([(100, 90, 95, 96), (102, 92, 95, 101)])
        labels = clf.classify_series(df)
        up = _upcoming_setup(df, labels, clf.detect_combos(df, labels))
        assert up['trigger_high'] == 102.0 and up['trigger_low'] == 92.0
        assert up['mid_trigger'] == pytest.approx(97.0)

    def test_direction_read_after_2d(self):
        assert _last_directional(pd.Series(['X', '2U', '2D'])) == '2D'
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100), (99, 88, 95, 89)])
        clf = StratClassifier()
        lab = clf.classify_series(df)
        up = _upcoming_setup(df, lab, clf.detect_combos(df, lab))
        assert up['break_up'] == '2U reversal'
        assert up['break_down'] == '2D continuation'


class TestComputeStratHistory:
    @pytest.fixture
    def daily(self):
        rng = np.random.default_rng(7)
        n = 260
        close = 100 + np.cumsum(rng.normal(0, 1, n))
        high = close + rng.uniform(0.5, 2.0, n)
        low = close - rng.uniform(0.5, 2.0, n)
        openp = close + rng.normal(0, 0.5, n)
        return _daily_frame(list(zip(high, low, openp, close)))

    def test_structure_all_timeframes(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=10)
        assert res['available'] is True and res['ticker'] == 'TEST'
        for tf in ('1d', '1w', '1mo', '1q'):
            assert tf in res['timeframes']
            block = res['timeframes'][tf]
            assert block['available'] is True
            assert 1 <= len(block['history']) <= 10
            rec = block['history'][-1]
            for k in ('period', 'open', 'high', 'low', 'close', 'candle', 'combo',
                      'is_continuation', 'is_reversal', 'is_inside', 'is_setup',
                      'trigger_high', 'trigger_low'):
                assert k in rec
            assert rec['candle'] in ('1', '2U', '2D', '3', 'X')
            up = block['upcoming']
            assert up['trigger_high'] is not None and up['trigger_low'] is not None
            assert up['break_up'].startswith('2U') and up['break_down'].startswith('2D')
        assert res['timeframes']['1d']['current'] == res['timeframes']['1d']['history'][-1]

    def test_quarterly_fewer_than_daily(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=999)
        assert len(res['timeframes']['1q']['history']) < len(res['timeframes']['1d']['history'])

    def test_insufficient_data(self):
        res = compute_strat_history('TEST', df=_daily_frame([(1, 0, 0.5, 0.5)]))
        assert res['available'] is False

    def test_flags_consistent(self, daily):
        res = compute_strat_history('TEST', df=daily, lookback=999)
        for blk in res['timeframes'].values():
            for rec in blk['history']:
                assert rec['is_continuation'] == ('continuation' in rec['combo'])
                assert rec['is_reversal'] == ('reversal' in rec['combo'])
                assert rec['is_inside'] == (rec['candle'] == '1')

    def test_classification_is_non_vacuous(self, daily):
        """Guard against a silent 'all-X' output: the daily tape on real
        random-walk OHLCV must classify a majority of bars into the four
        directional candle types, and fire at least one real combo. If the
        classifier degraded to emitting only 'X' (the unclassifiable
        sentinel), every flag-consistency check above would still pass —
        this makes that regression visible."""
        res = compute_strat_history('TEST', df=daily, lookback=999)
        daily_hist = res['timeframes']['1d']['history']
        candles = [r['candle'] for r in daily_hist]
        non_x = [c for c in candles if c != 'X']
        # A 260-bar random walk should classify almost everything; require
        # the overwhelming majority to be real (not the 'X' sentinel).
        assert len(non_x) >= 0.9 * len(candles), (
            f"too many unclassifiable bars: {len(candles) - len(non_x)}/"
            f"{len(candles)} are 'X'"
        )
        # All four directional types should appear over 260 bars.
        assert {'1', '2U', '2D', '3'}.issubset(set(candles))
        # At least one real combo must fire (not just empty/none strings).
        real_combos = [
            r['combo'] for r in daily_hist
            if r['combo'] and r['combo'] not in ('', 'none')
        ]
        assert real_combos, "no strat combos detected on a 260-bar tape"
        # The continuation/reversal flags must actually be exercised, not
        # uniformly False (which would also pass test_flags_consistent).
        assert any(r['is_continuation'] or r['is_reversal'] for r in daily_hist)
