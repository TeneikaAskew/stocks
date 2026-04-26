"""Tests for lib/strat.py — The Strat candle classification."""

import pandas as pd
import numpy as np
import pytest
from lib.strat import StratClassifier


@pytest.fixture
def classifier():
    return StratClassifier()


class TestCandleClassification:
    def test_inside_bar(self, classifier):
        assert classifier.classify_candle(99, 96, 100, 95) == '1'

    def test_up_bar(self, classifier):
        assert classifier.classify_candle(101, 96, 100, 95) == '2U'

    def test_down_bar(self, classifier):
        assert classifier.classify_candle(99, 94, 100, 95) == '2D'

    def test_outside_bar(self, classifier):
        assert classifier.classify_candle(101, 94, 100, 95) == '3'

    def test_equal_highs_equal_lows(self, classifier):
        # Same high AND same low = inside bar (not higher, not lower)
        assert classifier.classify_candle(100, 95, 100, 95) == '1'

    def test_equal_high_lower_low(self, classifier):
        # Same high but lower low = 2D
        assert classifier.classify_candle(100, 94, 100, 95) == '2D'


class TestSeriesClassification:
    def test_known_sequence(self, classifier, known_strat_sequence):
        labels = classifier.classify_series(known_strat_sequence)
        assert labels.iloc[0] == 'X'   # First bar unknown
        assert labels.iloc[1] == '1'   # Inside bar
        assert labels.iloc[2] == '2U'  # Up bar
        assert labels.iloc[3] == '2D'  # Down bar
        assert labels.iloc[4] == '3'   # Outside bar

    def test_length_matches(self, classifier, sample_ohlcv):
        labels = classifier.classify_series(sample_ohlcv)
        assert len(labels) == len(sample_ohlcv)


class TestComboDetection:
    def test_212_reversal_bullish(self, classifier, strat_combo_sequence):
        """2D → 1 → 2U should detect a bullish reversal."""
        result = classifier.detect_combos(strat_combo_sequence)
        combos = result[result['strat_combo'] != 'none']
        assert len(combos) >= 1
        assert '2D-1-2U_reversal' in combos['strat_combo'].values

    def test_setup_detection(self, classifier, strat_combo_sequence):
        """Inside bar after directional bar should flag as setup."""
        result = classifier.detect_combos(strat_combo_sequence)
        # Bar 3 is an inside bar after 2D bar 2 — should be a setup
        assert result['strat_setup'].iloc[3] == True

    def test_no_false_combos(self, classifier, known_strat_sequence):
        """Known mixed sequence shouldn't produce invalid combos."""
        result = classifier.detect_combos(known_strat_sequence)
        # Should have strat_type and strat_combo columns
        assert 'strat_type' in result.columns
        assert 'strat_combo' in result.columns


class TestFTFC:
    def test_all_bullish(self, classifier):
        """All timeframes 2U → score near +1.0."""
        tf_dfs = {}
        for tf in ['5m', '15m', '1h', 'D', 'W']:
            # Create 3 bars where latest is 2U (higher high, same or higher low)
            tf_dfs[tf] = pd.DataFrame({
                'High': [100, 101, 102],
                'Low': [95, 95, 95],
                'Close': [98, 100, 101],
                'Volume': [1000, 1000, 1000],
            })
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert score > 0.5
        assert direction == 'bullish'

    def test_all_bearish(self, classifier):
        """All timeframes 2D → score near -1.0."""
        tf_dfs = {}
        for tf in ['5m', '15m', '1h', 'D', 'W']:
            tf_dfs[tf] = pd.DataFrame({
                'High': [102, 101, 100],
                'Low': [95, 94, 93],
                'Close': [100, 96, 94],
                'Volume': [1000, 1000, 1000],
            })
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert score < -0.5
        assert direction == 'bearish'

    def test_mixed_returns_near_zero(self, classifier):
        """Mixed directions → score near 0."""
        # Some bullish, some bearish
        tf_dfs = {
            '5m': pd.DataFrame({'High': [100, 101], 'Low': [95, 95], 'Close': [98, 100], 'Volume': [1000, 1000]}),
            '15m': pd.DataFrame({'High': [101, 100], 'Low': [95, 94], 'Close': [100, 96], 'Volume': [1000, 1000]}),
            'D': pd.DataFrame({'High': [100, 99], 'Low': [95, 96], 'Close': [98, 98], 'Volume': [1000, 1000]}),
        }
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert -0.5 < score < 0.5


class TestStratBonus:
    def test_call_with_bullish_reversal(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='2D-1-2U_reversal',
            ftfc_score=0.7,
            ftfc_threshold=0.6,
            orb_trend=1,
        )
        assert bonus == 3  # combo + ftfc + orb

    def test_put_with_bearish_reversal(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT',
            combo='2U-1-2D_reversal',
            ftfc_score=-0.7,
            ftfc_threshold=0.6,
            orb_trend=-1,
        )
        assert bonus == 3

    def test_no_bonus_on_mismatch(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='none',
            ftfc_score=0.0,
            orb_trend=0,
        )
        assert bonus == 0

    def test_ftfc_penalty(self, classifier):
        """FTFC strongly against signal direction → penalty."""
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='none',
            ftfc_score=-0.8,
            ftfc_threshold=0.6,
            orb_trend=0,
        )
        assert bonus == -1


class TestAddStratColumns:
    def test_adds_columns(self, classifier, sample_ohlcv):
        result = classifier.add_strat_columns(sample_ohlcv)
        assert 'strat_type' in result.columns
        assert 'strat_combo' in result.columns
        assert 'strat_setup' in result.columns
        assert len(result) == len(sample_ohlcv)


# ── Failed 2U / Failed 2D detection (community RevStrat patterns) ─────────


class TestFailedTwoPatterns:
    def _frame(self, bars):
        """Build OHLC DataFrame from list of (H, L, O, C) tuples."""
        df = pd.DataFrame(
            bars, columns=['High', 'Low', 'Open', 'Close']
        )
        df['Volume'] = 1000
        return df

    def test_failed_2u_detected(self, classifier):
        """Bar 1 prints higher high than bar 0 but closes back inside bar 0's range."""
        # Bar 0: H=100 L=95 (range 95-100)
        # Bar 1: H=101 (HH) L=97 close=99 (back inside [95,100])
        df = self._frame([(100, 95, 97, 98), (101, 97, 100, 99)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_type'] == '2U'
        assert result.iloc[1]['strat_combo'] == 'Failed_2U'

    def test_failed_2u_not_triggered_when_close_above_prev_high(self, classifier):
        """A clean 2U breakout (close above prev high) is NOT a failed 2U."""
        df = self._frame([(100, 95, 97, 98), (102, 97, 99, 101.5)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_type'] == '2U'
        assert result.iloc[1]['strat_combo'] != 'Failed_2U'

    def test_failed_2d_detected(self, classifier):
        """Bar 1 prints lower low than bar 0 but closes back inside bar 0's range."""
        # Bar 0: H=100 L=95
        # Bar 1: H=99 L=94 (LL) close=96 (back inside [95,100])
        df = self._frame([(100, 95, 97, 98), (99, 94, 97, 96)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_type'] == '2D'
        assert result.iloc[1]['strat_combo'] == 'Failed_2D'

    def test_failed_2d_not_triggered_when_close_below_prev_low(self, classifier):
        """A clean 2D breakdown (close below prev low) is NOT a failed 2D."""
        df = self._frame([(100, 95, 97, 98), (99, 93, 97, 94)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_type'] == '2D'
        assert result.iloc[1]['strat_combo'] != 'Failed_2D'

    def test_simple_2u_continuation(self, classifier):
        """Two consecutive 2U bars → 2U_continuation."""
        # Bar 0: H=100 L=95
        # Bar 1: H=102 L=97 (2U)
        # Bar 2: H=104 L=98 (2U after 2U)
        df = self._frame([
            (100, 95, 97, 99),
            (102, 97, 99, 101),
            (104, 98, 101, 103),
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '2U_continuation'

    def test_simple_2d_continuation(self, classifier):
        """Two consecutive 2D bars → 2D_continuation."""
        df = self._frame([
            (100, 95, 99, 97),
            (99,  93, 97, 94),
            (98,  91, 94, 92),
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '2D_continuation'


class TestNewPatternBonusScoring:
    def test_failed_2u_scores_for_put(self, classifier):
        """Failed 2U is a bearish reversal — should bonus PUT signals."""
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT', combo='Failed_2U',
            ftfc_score=-0.7, ftfc_threshold=0.6, orb_trend=-1,
        )
        # combo + ftfc + orb = 3
        assert bonus == 3

    def test_failed_2d_scores_for_call(self, classifier):
        """Failed 2D is a bullish reversal — should bonus CALL signals."""
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='Failed_2D',
            ftfc_score=0.7, ftfc_threshold=0.6, orb_trend=1,
        )
        assert bonus == 3

    def test_failed_2u_does_not_bonus_call(self, classifier):
        """Failed 2U should NOT bonus a CALL signal (wrong direction)."""
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='Failed_2U',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus == 0

    def test_2u_continuation_bonuses_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='2U_continuation',
            ftfc_score=0.0, orb_trend=0,
        )
        # Just the combo bonus
        assert bonus > 0
