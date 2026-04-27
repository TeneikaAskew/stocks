"""Tests for lib/strat.py — The Strat candle classification.

All combo labels use the <pattern>_<direction>_<kind> naming convention
per docs/STRAT_METHODOLOGY.md §19.
"""

import pandas as pd
import numpy as np
import pytest
from lib.strat import StratClassifier, COMBO_BONUS_CALL, COMBO_BONUS_PUT


@pytest.fixture
def classifier():
    return StratClassifier()


def _frame(bars):
    """Build OHLC DataFrame from list of (H, L, O, C) tuples."""
    df = pd.DataFrame(bars, columns=['High', 'Low', 'Open', 'Close'])
    df['Volume'] = 1000
    return df


# ── Base candle classification ─────────────────────────────────────────────


class TestCandleClassification:
    def test_inside_bar(self, classifier):
        assert classifier.classify_candle(99, 96, 100, 95) == '1'

    def test_up_bar(self, classifier):
        assert classifier.classify_candle(101, 96, 100, 95) == '2U'

    def test_down_bar(self, classifier):
        assert classifier.classify_candle(99, 94, 100, 95) == '2D'

    def test_outside_bar(self, classifier):
        assert classifier.classify_candle(101, 94, 100, 95) == '3'

    def test_equal_highs_equal_lows_is_inside(self, classifier):
        """Inclusive: H==pH AND L==pL → type 1 (not a break)."""
        assert classifier.classify_candle(100, 95, 100, 95) == '1'

    def test_equal_high_lower_low(self, classifier):
        assert classifier.classify_candle(100, 94, 100, 95) == '2D'

    def test_equal_low_higher_high(self, classifier):
        assert classifier.classify_candle(101, 95, 100, 95) == '2U'


class TestSeriesClassification:
    def test_known_sequence(self, classifier, known_strat_sequence):
        labels = classifier.classify_series(known_strat_sequence)
        assert labels.iloc[0] == 'X'
        assert labels.iloc[1] == '1'
        assert labels.iloc[2] == '2U'
        assert labels.iloc[3] == '2D'
        assert labels.iloc[4] == '3'

    def test_length_matches(self, classifier, sample_ohlcv):
        labels = classifier.classify_series(sample_ohlcv)
        assert len(labels) == len(sample_ohlcv)


# ── Combo detection ────────────────────────────────────────────────────────


class TestComboDetection:
    def test_212_reversal_bullish(self, classifier, strat_combo_sequence):
        """2D → 1 → 2U should detect a bullish 212 reversal."""
        result = classifier.detect_combos(strat_combo_sequence)
        combos = result[result['strat_combo'] != 'none']
        assert len(combos) >= 1
        assert '212_bull_reversal' in combos['strat_combo'].values

    def test_setup_detection(self, classifier, strat_combo_sequence):
        result = classifier.detect_combos(strat_combo_sequence)
        assert result['strat_setup'].iloc[3] == True

    def test_columns_present(self, classifier, known_strat_sequence):
        result = classifier.detect_combos(known_strat_sequence)
        assert 'strat_candle' in result.columns
        assert 'strat_combo' in result.columns


# ── Failed 2U / Failed 2D (close vs open, §2) ────────────────────────────


class TestFailedTwoPatterns:
    def test_f2u_detected_close_below_open(self, classifier):
        """2U bar (broke prev high) with bearish close (C < O) → f2u_bear_reversal."""
        df = _frame([(100, 95, 97, 98), (101, 97, 100, 99)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2U'
        assert result.iloc[1]['strat_combo'] == 'f2u_bear_reversal'

    def test_f2u_close_above_prev_high_but_bearish(self, classifier):
        """Close above prev high but still below open → Failed 2U.
        This is the key difference from the old close-vs-prev-range definition.
        """
        df = _frame([(100, 95, 97, 98), (103, 97, 102, 100.5)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2U'
        assert result.iloc[1]['strat_combo'] == 'f2u_bear_reversal'

    def test_clean_2u_when_close_above_open(self, classifier):
        """A clean bullish 2U breakout (C >= O) is clean_2u_bull, not failed."""
        df = _frame([(100, 95, 97, 98), (102, 97, 99, 101.5)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2U'
        assert result.iloc[1]['strat_combo'] == 'clean_2u_bull'

    def test_f2d_detected_close_above_open(self, classifier):
        """2D bar with bullish close (C > O) → f2d_bull_reversal."""
        df = _frame([(100, 95, 97, 98), (99, 94, 96, 97)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2D'
        assert result.iloc[1]['strat_combo'] == 'f2d_bull_reversal'

    def test_clean_2d_when_close_below_open(self, classifier):
        """Clean bearish 2D (C <= O) → clean_2d_bear."""
        df = _frame([(100, 95, 97, 98), (99, 93, 97, 94)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2D'
        assert result.iloc[1]['strat_combo'] == 'clean_2d_bear'

    def test_doji_2u_is_clean_not_failed(self, classifier):
        """C == O on a 2U bar → clean_2u_bull (doji edge case)."""
        df = _frame([(100, 95, 97, 98), (102, 97, 101, 101)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_combo'] == 'clean_2u_bull'


# ── 22 REV and 22 CON ────────────────────────────────────────────────────


class TestTwoBarCombos:
    def test_22_rev_bull(self, classifier):
        """2D then 2U = 22_bull_reversal."""
        df = _frame([
            (100, 95, 97, 98),
            (99, 93, 97, 94),     # 2D (clean: C < O)
            (100, 94, 95, 99),    # 2U (broke bar 1 high, not low)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bull_reversal'

    def test_22_rev_bear(self, classifier):
        """2U then 2D = 22_bear_reversal."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 96, 98, 101),   # 2U
            (101, 94, 100, 95),   # 2D
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bear_reversal'

    def test_22_con_bull(self, classifier):
        """2U then 2U = 22_bull_continuation."""
        df = _frame([
            (100, 95, 97, 99),
            (102, 97, 99, 101),   # 2U
            (104, 98, 101, 103),  # 2U again
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bull_continuation'

    def test_22_con_bear(self, classifier):
        """2D then 2D = 22_bear_continuation."""
        df = _frame([
            (100, 95, 99, 97),
            (99, 93, 97, 94),     # 2D
            (98, 91, 94, 92),     # 2D again
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bear_continuation'


# ── 132 and 322 ──────────────────────────────────────────────────────────


class TestNewThreeBarCombos:
    def test_132_bull(self, classifier):
        """Inside → Outside → 2U = 132_bull_continuation."""
        df = _frame([
            (100, 95, 97, 98),    # bar 0: base (wide range)
            (99, 96, 97, 98),     # bar 1: inside
            (101, 94, 97, 99),    # bar 2: outside (3)
            (102, 95, 99, 101),   # bar 3: 2U (broke bar 2 high, not low)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '132_bull_continuation'

    def test_132_bear(self, classifier):
        """Inside → Outside → 2D = 132_bear_continuation."""
        df = _frame([
            (100, 95, 97, 98),
            (99, 96, 97, 98),     # inside
            (101, 94, 97, 96),    # outside (3)
            (100, 93, 96, 94),    # 2D
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '132_bear_continuation'

    def test_322_bull(self, classifier):
        """Outside → 2U → 2U = 322_bull_continuation."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 93, 97, 100),   # 3 (outside)
            (104, 94, 100, 103),  # 2U
            (106, 95, 103, 105),  # 2U again
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '322_bull_continuation'

    def test_322_bear(self, classifier):
        """Outside → 2D → 2D = 322_bear_continuation."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 93, 97, 95),    # 3 (outside)
            (101, 91, 95, 92),    # 2D
            (100, 89, 92, 90),    # 2D again
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '322_bear_continuation'


# ── Multi-inside ─────────────────────────────────────────────────────────


class TestMultiInside:
    def test_double_inside(self, classifier):
        """Two consecutive inside bars = 11_inside_compression."""
        df = _frame([
            (100, 90, 95, 95),
            (99, 91, 95, 95),     # inside (1)
            (98, 92, 95, 95),     # inside again (1-1)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '11_inside_compression'

    def test_triple_inside(self, classifier):
        """Four consecutive inside bars (after base) — bar 4 = 111_inside_compression."""
        df = _frame([
            (100, 90, 95, 95),    # bar 0: base
            (99, 91, 95, 95),     # bar 1: inside
            (98, 92, 95, 95),     # bar 2: inside (1-1)
            (97, 93, 95, 95),     # bar 3: inside (1-1-1)
            (96.5, 93.5, 95, 95), # bar 4: inside (prev3=1, prev2=1, prev1=1, curr=1)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[4]['strat_combo'] == '111_inside_compression'


# ── Priority collision tests ─────────────────────────────────────────────


class TestPriorityCollision:
    def test_212_beats_22_rev(self, classifier):
        """A 2D-1-2U sequence is 212_bull_reversal, NOT 22_bull_reversal."""
        df = _frame([
            (100, 95, 97, 98),
            (100, 95, 97, 98),
            (99, 93, 97, 94),     # 2D
            (98, 94, 95, 97),     # 1 (inside)
            (99.5, 94.5, 95, 99), # breaks above inside bar high
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[4]['strat_combo'] == '212_bull_reversal'

    def test_failed_2u_does_not_override_22_rev(self, classifier):
        """22 REV is higher priority than Failed_2U."""
        df = _frame([
            (100, 95, 97, 98),
            (99, 93, 97, 94),     # 2D (clean)
            (100, 94, 98, 95),    # 2U with C < O (bearish close)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bull_reversal'


# ── FTFC ──────────────────────────────────────────────────────────────────


class TestFTFC:
    def test_all_bullish(self, classifier):
        tf_dfs = {}
        for tf in ['5m', '15m', '1h', '1d', '1w']:
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
        tf_dfs = {}
        for tf in ['5m', '15m', '1h', '1d', '1w']:
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
        tf_dfs = {
            '5m': pd.DataFrame({'High': [100, 101], 'Low': [95, 95], 'Close': [98, 100], 'Volume': [1000, 1000]}),
            '15m': pd.DataFrame({'High': [101, 100], 'Low': [95, 94], 'Close': [100, 96], 'Volume': [1000, 1000]}),
            '1d': pd.DataFrame({'High': [100, 99], 'Low': [95, 96], 'Close': [98, 98], 'Volume': [1000, 1000]}),
        }
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert -0.5 < score < 0.5

    def test_new_timeframe_keys_accepted(self, classifier):
        """4h and 12h keys should contribute to FTFC."""
        tf_dfs = {
            '4h': pd.DataFrame({'High': [100, 101, 102], 'Low': [95, 95, 95], 'Close': [98, 100, 101], 'Volume': [1000]*3}),
            '12h': pd.DataFrame({'High': [100, 101, 102], 'Low': [95, 95, 95], 'Close': [98, 100, 101], 'Volume': [1000]*3}),
        }
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert score > 0
        assert '4h' in labels
        assert '12h' in labels


# ── Bonus scoring ─────────────────────────────────────────────────────────


class TestStratBonus:
    def test_call_with_bullish_212_reversal(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='212_bull_reversal',
            ftfc_score=0.7, ftfc_threshold=0.6, orb_trend=1,
        )
        assert bonus == 3.0

    def test_put_with_bearish_212_reversal(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT',
            combo='212_bear_reversal',
            ftfc_score=-0.7, ftfc_threshold=0.6, orb_trend=-1,
        )
        assert bonus == 3.0

    def test_no_bonus_on_none(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='none',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus == 0.0

    def test_ftfc_penalty(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='none',
            ftfc_score=-0.8, ftfc_threshold=0.6, orb_trend=0,
        )
        assert bonus == -1.0

    def test_f2u_scores_for_put(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT', combo='f2u_bear_reversal',
            ftfc_score=-0.7, ftfc_threshold=0.6, orb_trend=-1,
        )
        assert bonus == 3.0

    def test_f2d_scores_for_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='f2d_bull_reversal',
            ftfc_score=0.7, ftfc_threshold=0.6, orb_trend=1,
        )
        assert bonus == 3.0

    def test_f2u_negative_for_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='f2u_bear_reversal',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus == -0.5

    def test_22_con_bull_for_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='22_bull_continuation',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus == 0.5

    def test_clean_2u_small_bonus(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='clean_2u_bull',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus == 0.25

    def test_bonus_returns_float(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='none',
            ftfc_score=0.0, orb_trend=0,
        )
        assert isinstance(bonus, float)


# ── Add strat columns convenience ────────────────────────────────────────


class TestAddStratColumns:
    def test_adds_columns(self, classifier, sample_ohlcv):
        result = classifier.add_strat_columns(sample_ohlcv)
        assert 'strat_candle' in result.columns
        assert 'strat_combo' in result.columns
        assert 'strat_setup' in result.columns
        assert len(result) == len(sample_ohlcv)


# ── Bonus dict completeness ──────────────────────────────────────────────


class TestBonusDictCompleteness:
    def test_call_and_put_dicts_have_same_keys(self):
        assert set(COMBO_BONUS_CALL.keys()) == set(COMBO_BONUS_PUT.keys())

    def test_all_combo_labels_in_bonus_dicts(self, classifier, sample_ohlcv):
        """Every combo label produced by detect_combos should exist in the bonus dicts."""
        result = classifier.detect_combos(sample_ohlcv)
        for combo in result['strat_combo'].unique():
            assert combo in COMBO_BONUS_CALL, f"'{combo}' missing from COMBO_BONUS_CALL"
            assert combo in COMBO_BONUS_PUT, f"'{combo}' missing from COMBO_BONUS_PUT"
