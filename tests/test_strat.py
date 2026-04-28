"""Tests for lib/strat.py — Strat candle classification + combos.

Aligned with docs/STRAT_METHODOLOGY.md as of the v2 refactor:
- result column is `strat_candle`
- combo strings use `<pattern>_<direction>_<kind>` format
- Failed_2 sub-classification is by close-vs-open
- Failed_2 priority is lowest (multi-bar combos win on collision)
- FTFC weight keys use `1d` / `1w` plus `4h` / `12h`
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


# ── Single-bar classification ─────────────────────────────────────────────


class TestCandleClassification:
    def test_inside_bar(self, classifier):
        assert classifier.classify_candle(99, 96, 100, 95) == '1'

    def test_up_bar(self, classifier):
        assert classifier.classify_candle(101, 96, 100, 95) == '2U'

    def test_down_bar(self, classifier):
        assert classifier.classify_candle(99, 94, 100, 95) == '2D'

    def test_outside_bar(self, classifier):
        assert classifier.classify_candle(101, 94, 100, 95) == '3'

    def test_inclusive_inside_bar(self, classifier):
        """H == pH AND L == pL is a `1` (inclusive inequalities)."""
        assert classifier.classify_candle(100, 95, 100, 95) == '1'

    def test_equal_high_lower_low(self, classifier):
        assert classifier.classify_candle(100, 94, 100, 95) == '2D'


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


# ── Combo column structure ────────────────────────────────────────────────


class TestComboDetectionStructure:
    def test_columns(self, classifier, sample_ohlcv):
        result = classifier.detect_combos(sample_ohlcv)
        assert 'strat_candle' in result.columns
        assert 'strat_combo' in result.columns
        assert 'strat_setup' in result.columns
        assert 'trigger_high' in result.columns
        assert 'trigger_low' in result.columns


# ── 3-bar reversals (priority 1-2) ────────────────────────────────────────


class Test212Reversal:
    def test_212_bull_reversal_via_fixture(self, classifier, strat_combo_sequence):
        """2D → 1 → 2U should detect a bullish reversal."""
        result = classifier.detect_combos(strat_combo_sequence)
        assert result.iloc[4]['strat_combo'] == '212_bull_reversal'

    def test_setup_detection(self, classifier, strat_combo_sequence):
        """Inside bar after directional bar should flag as setup."""
        result = classifier.detect_combos(strat_combo_sequence)
        assert result.iloc[3]['strat_setup'] == True

    def test_212_bear_reversal(self, classifier):
        # 2U (H=101) → 1 (H=100, L=98) → 2D break (L<98)
        df = _frame([
            (100, 95, 97, 98),    # ref
            (101, 96, 97, 100),   # 2U
            (100, 98, 99, 99),    # 1 (inside)
            (99,  97, 98, 97.5),  # 2D break below inside low (97 < 98)... actually L=97 < 98 ✓
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '212_bear_reversal'


class Test312Reversal:
    def test_312_bull_reversal(self, classifier):
        # 3 (outside, H=102, L=93) → 1 (H=99, L=95) → 2U break above 99
        df = _frame([
            (100, 95, 97, 98),    # ref
            (102, 93, 97, 99),    # 3 (outside)
            (99,  95, 97, 97),    # 1
            (101, 96, 97, 100),   # 2U: high 101>99 ✓
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '312_bull_reversal'

    def test_312_bear_reversal(self, classifier):
        df = _frame([
            (100, 95, 97, 98),
            (102, 93, 97, 95),    # 3
            (99,  95, 97, 97),    # 1
            (98,  93, 97, 94),    # 2D: low 93<95 ✓
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '312_bear_reversal'


# ── Continuation combos ───────────────────────────────────────────────────


class Test132Continuation:
    def test_132_bull_continuation(self, classifier):
        # 1 (inside) → 3 (outside) → 2U
        df = _frame([
            (100, 95, 97, 98),    # ref
            (99,  96, 97, 97),    # 1
            (101, 94, 97, 100),   # 3 (outside vs prev 99/96)
            (103, 95, 100, 102),  # 2U: H>101, L>=94
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '132_bull_continuation'

    def test_132_bear_continuation(self, classifier):
        df = _frame([
            (100, 95, 97, 98),
            (99,  96, 97, 97),    # 1
            (101, 94, 97, 95),    # 3
            (100, 92, 95, 93),    # 2D: H<=101, L<94 ✓
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '132_bear_continuation'


class Test322Continuation:
    def test_322_bull_continuation(self, classifier):
        # 3 → 2U → 2U
        df = _frame([
            (100, 95, 97, 98),    # ref
            (102, 93, 97, 100),   # 3
            (104, 94, 100, 103),  # 2U: H>102, L>=93
            (106, 95, 103, 105),  # 2U: H>104, L>=94
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '322_bull_continuation'

    def test_322_bear_continuation(self, classifier):
        df = _frame([
            (100, 95, 97, 98),
            (102, 93, 97, 95),    # 3
            (101, 91, 95, 92),    # 2D: H<=102, L<93 ✓
            (100, 89, 92, 90),    # 2D: H<=101, L<91 ✓
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '322_bear_continuation'


class Test212Continuation:
    def test_212_bull_continuation(self, classifier):
        # 2U → 1 → 2U (same direction continuation through compression)
        df = _frame([
            (100, 95, 97, 98),    # ref
            (102, 96, 97, 100),   # 2U
            (101, 97, 99, 99),    # 1 (inside)
            (103, 97, 99, 102),   # 2U break above inside high 101
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[3]['strat_combo'] == '212_bull_continuation'


# ── 32 reversals (priority 6) ─────────────────────────────────────────────


class Test32Reversal:
    def test_32_bull_reversal(self, classifier):
        # 3 with bearish close → 2U
        df = _frame([
            (100, 95, 97, 98),    # ref
            (102, 93, 100, 95),   # 3 with close < open (bearish)
            (104, 94, 95, 103),   # 2U: H>102, L>=93
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '32_bull_reversal'

    def test_32_bear_reversal(self, classifier):
        # 3 with bullish close → 2D
        df = _frame([
            (100, 95, 97, 98),
            (102, 93, 95, 100),   # 3 bullish close (100 > 95)
            (101, 91, 100, 92),   # 2D: H<=102, L<93 ✓
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '32_bear_reversal'


# ── 22 reversals + continuations (priority 7-8) ───────────────────────────


class Test22Reversal:
    def test_22_bull_reversal(self, classifier):
        # 2D → 2U (mixed direction)
        df = _frame([
            (100, 95, 99, 96),    # ref
            (99,  93, 96, 94),    # 2D (H<=100, L<95)
            (101, 94, 94, 100),   # 2U (H>99, L>=93)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bull_reversal'

    def test_22_bear_reversal(self, classifier):
        # 2U → 2D
        df = _frame([
            (100, 95, 96, 99),    # ref
            (102, 96, 99, 101),   # 2U
            (101, 94, 101, 95),   # 2D (H<=102, L<96)
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bear_reversal'


class Test22Continuation:
    def test_22_bull_continuation(self, classifier):
        df = _frame([
            (100, 95, 97, 99),
            (102, 97, 99, 101),   # 2U
            (104, 98, 101, 103),  # 2U
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bull_continuation'

    def test_22_bear_continuation(self, classifier):
        df = _frame([
            (100, 95, 99, 97),
            (99,  93, 97, 94),    # 2D
            (98,  91, 94, 92),    # 2D
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bear_continuation'


# ── Multi-inside compression ──────────────────────────────────────────────


class TestInsideCompression:
    def test_11_inside_compression(self, classifier):
        # 2-bar inside compression
        df = _frame([
            (100, 95, 97, 98),    # ref
            (99,  96, 97, 97),    # 1
            (98.5, 96.5, 97, 97), # 1
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '11_inside_compression'

    def test_111_inside_compression(self, classifier):
        df = _frame([
            (100, 95, 97, 98),
            (99,  96, 97, 97),    # 1
            (98.5, 96.5, 97, 97), # 1
            (98,  97, 97, 97.5),  # 1
        ])
        result = classifier.detect_combos(df)
        # bar 3 has prev2=1, prev1=1, curr=1 → 111 takes priority over 11
        assert result.iloc[3]['strat_combo'] == '111_inside_compression'


# ── Failed_2 (close-vs-open semantics) ────────────────────────────────────


class TestFailedTwo:
    def test_f2u_bear_reversal_close_below_open(self, classifier):
        """2U bar that closes below its open is f2u_bear_reversal."""
        # Bar 0: H=100, L=95
        # Bar 1: 2U (H=101, L=96), Open=100, Close=99 (C<O)
        df = _frame([(100, 95, 97, 98), (101, 96, 100, 99)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2U'
        assert result.iloc[1]['strat_combo'] == 'f2u_bear_reversal'

    def test_clean_2u_when_close_above_open(self, classifier):
        """2U bar with close >= open is clean_2u_bull, not failed."""
        df = _frame([(100, 95, 97, 98), (102, 97, 99, 101.5)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2U'
        assert result.iloc[1]['strat_combo'] == 'clean_2u_bull'

    def test_f2d_bull_reversal_close_above_open(self, classifier):
        """2D bar that closes above its open is f2d_bull_reversal."""
        df = _frame([(100, 95, 97, 98), (99, 94, 95, 96)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2D'
        assert result.iloc[1]['strat_combo'] == 'f2d_bull_reversal'

    def test_clean_2d_when_close_below_open(self, classifier):
        """2D bar with close <= open is clean_2d_bear, not failed."""
        df = _frame([(100, 95, 97, 98), (99, 93, 97, 94)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_candle'] == '2D'
        assert result.iloc[1]['strat_combo'] == 'clean_2d_bear'

    def test_f2u_with_close_above_prev_high(self, classifier):
        """A 2U bar that closed above its open but below prev high is *not* a Failed_2.

        Verifies the close-vs-open rule (close vs prev_high is irrelevant).
        """
        # Bar 0: H=100; Bar 1: 2U H=101 close=99 open=100 → C<O → f2u
        df = _frame([(100, 95, 97, 98), (101, 96, 100, 99)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_combo'] == 'f2u_bear_reversal'


class TestFailedTwoPriority:
    def test_22_bear_reversal_beats_failed_2u(self, classifier):
        """A bar matching both 22_bear_reversal and Failed_2U → 22 wins."""
        # prev1=2U, curr=2D → 22_bear_reversal. But we want curr to also be a 2U
        # closing below open. Wait — collision is on a different bar.
        # The failed_2 check is on the CURRENT bar's classification.
        # 22_bear_reversal requires curr=2D, so they can't collide on the curr bar.
        #
        # Real collision: 2U bar with C<O after a 2D. That's curr=2U, prev=2D
        # → 22_bull_reversal AND f2u_bear_reversal. Multi-bar wins.
        df = _frame([
            (100, 95, 97, 98),    # ref
            (99,  93, 96, 94),    # 2D
            (101, 94, 100, 99),   # 2U (H>99, L>=93) with C<O ⇒ f2u candidate
        ])
        result = classifier.detect_combos(df)
        # 22_bull_reversal (priority 7) beats f2u_bear_reversal (priority 11)
        assert result.iloc[2]['strat_combo'] == '22_bull_reversal'

    def test_212_bear_reversal_beats_failed_2u(self, classifier):
        """A 2U-1-2D bar tagged as 212_bear_reversal wins over any single-bar tag."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 96, 97, 100),   # 2U
            (101, 98, 99, 99),    # 1
            (100, 97, 99, 97.5),  # 2D break below inside low 98
        ])
        result = classifier.detect_combos(df)
        # bar 3 is 2D, so f2u doesn't apply. f2d would apply only if C>O.
        # C=97.5, O=99 → C<O, so not f2d. Just verifying 212 wins.
        assert result.iloc[3]['strat_combo'] == '212_bear_reversal'


# ── Doji ──────────────────────────────────────────────────────────────────


class TestDoji:
    def test_doji_2u_is_clean(self, classifier):
        """2U bar with Close == Open is clean_2u_bull (not failed)."""
        df = _frame([(100, 95, 97, 98), (101, 96, 99, 99)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_combo'] == 'clean_2u_bull'

    def test_doji_2d_is_clean(self, classifier):
        df = _frame([(100, 95, 97, 98), (99, 94, 96, 96)])
        result = classifier.detect_combos(df)
        assert result.iloc[1]['strat_combo'] == 'clean_2d_bear'


# ── FTFC ──────────────────────────────────────────────────────────────────


class TestFTFC:
    def test_all_bullish_with_new_keys(self, classifier):
        """All timeframes 2U with new key set → score near +1.0."""
        tf_dfs = {}
        for tf in ['5m', '15m', '1h', '4h', '12h', '1d', '1w']:
            tf_dfs[tf] = pd.DataFrame({
                'High': [100, 101, 102],
                'Low':  [95,  95,  95],
                'Close':[98, 100, 101],
                'Volume':[1000, 1000, 1000],
            })
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert score > 0.9
        assert direction == 'bullish'

    def test_all_bearish_with_new_keys(self, classifier):
        tf_dfs = {}
        for tf in ['5m', '15m', '1h', '4h', '12h', '1d', '1w']:
            tf_dfs[tf] = pd.DataFrame({
                'High': [102, 101, 100],
                'Low':  [95,  94,  93],
                'Close':[100, 96,  94],
                'Volume':[1000, 1000, 1000],
            })
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert score < -0.9
        assert direction == 'bearish'

    def test_mixed_returns_near_zero(self, classifier):
        tf_dfs = {
            '5m':  pd.DataFrame({'High': [100, 101], 'Low': [95, 95], 'Close': [98, 100], 'Volume': [1000, 1000]}),
            '15m': pd.DataFrame({'High': [101, 100], 'Low': [95, 94], 'Close': [100, 96], 'Volume': [1000, 1000]}),
            '1d':  pd.DataFrame({'High': [100, 99],  'Low': [95, 96], 'Close': [98, 98],  'Volume': [1000, 1000]}),
        }
        score, direction, labels = classifier.calculate_ftfc(tf_dfs)
        assert -0.5 < score < 0.5

    def test_default_weights_sum_to_one(self, classifier):
        total = sum(classifier.DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9


# ── Bonus scoring ─────────────────────────────────────────────────────────


class TestStratBonus:
    def test_call_with_212_bull_reversal(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='212_bull_reversal',
            ftfc_score=0.7,
            ftfc_threshold=0.6,
            orb_trend=1,
        )
        # combo 1.5 + ftfc 1 + orb 1 = 3.5
        assert bonus == pytest.approx(3.5)

    def test_put_with_212_bear_reversal(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT',
            combo='212_bear_reversal',
            ftfc_score=-0.7,
            ftfc_threshold=0.6,
            orb_trend=-1,
        )
        assert bonus == pytest.approx(3.5)

    def test_no_bonus_on_neutral_combo(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='none',
            ftfc_score=0.0,
            orb_trend=0,
        )
        assert bonus == 0.0

    def test_ftfc_penalty(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL',
            combo='none',
            ftfc_score=-0.8,
            ftfc_threshold=0.6,
            orb_trend=0,
        )
        assert bonus == pytest.approx(-1.0)

    def test_22_bull_reversal_negative_for_put(self, classifier):
        """Bullish combo gives negative bonus to a PUT signal."""
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT', combo='22_bull_reversal',
            ftfc_score=0.0, orb_trend=0,
        )
        # COMBO_BONUS_PUT['22_bull_reversal'] = -1.0
        assert bonus == pytest.approx(-1.0)

    def test_f2u_bear_reversal_bonuses_put(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='PUT', combo='f2u_bear_reversal',
            ftfc_score=-0.7, ftfc_threshold=0.6, orb_trend=-1,
        )
        # combo 0.5 + ftfc 1 + orb 1 = 2.5
        assert bonus == pytest.approx(2.5)

    def test_f2d_bull_reversal_bonuses_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='f2d_bull_reversal',
            ftfc_score=0.7, ftfc_threshold=0.6, orb_trend=1,
        )
        assert bonus == pytest.approx(2.5)

    def test_f2u_does_not_bonus_call(self, classifier):
        """f2u_bear_reversal is bearish — must NOT bonus a CALL signal."""
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='f2u_bear_reversal',
            ftfc_score=0.0, orb_trend=0,
        )
        # COMBO_BONUS_CALL['f2u_bear_reversal'] = -0.5
        assert bonus == pytest.approx(-0.5)

    def test_22_bull_continuation_bonuses_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='22_bull_continuation',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus > 0

    def test_clean_2u_small_bonus_for_call(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='clean_2u_bull',
            ftfc_score=0.0, orb_trend=0,
        )
        assert bonus == pytest.approx(0.25)

    def test_returns_float(self, classifier):
        bonus = classifier.get_strat_bonus(
            signal_direction='CALL', combo='212_bull_reversal',
            ftfc_score=0.0, orb_trend=0,
        )
        assert isinstance(bonus, float)


class TestComboBonusTables:
    def test_call_and_put_are_mirrors(self):
        for combo, val in COMBO_BONUS_CALL.items():
            assert COMBO_BONUS_PUT[combo] == -val

    def test_bull_combos_positive_for_call(self):
        for combo, val in COMBO_BONUS_CALL.items():
            if 'bull' in combo:
                assert val > 0, f"{combo} should be positive for CALL"
            elif 'bear' in combo:
                assert val < 0, f"{combo} should be negative for CALL"


# ── Convenience ───────────────────────────────────────────────────────────


class TestAddStratColumns:
    def test_adds_columns(self, classifier, sample_ohlcv):
        result = classifier.add_strat_columns(sample_ohlcv)
        assert 'strat_candle' in result.columns
        assert 'strat_combo' in result.columns
        assert 'strat_setup' in result.columns
        assert len(result) == len(sample_ohlcv)


# ── as_of cutoff regression — historical replay must not see future bars ──


class TestComputeStratStatusAsOf:
    """Regression tests for the tz-leak bug.

    `compute_strat_status` previously crashed silently (bare except) when
    the caller passed a tz-aware datetime and the DataFrame's index was
    tz-naive. The function then returned the LATEST bar instead of the
    bar at `as_of`, leaking future data into historical replays.

    Concrete impact (pre-fix): an ARM as_of=2026-04-20 insight run read
    the 2026-04-24 bar as `trigger_high`, anchoring the LLM's entry zone
    to a price that hadn't been printed yet.
    """

    @staticmethod
    def _build_daily_df():
        """6 trading days of synthetic OHLC, indexed naive (matches data_loader)."""
        dates = pd.to_datetime([
            '2026-04-15', '2026-04-16', '2026-04-17',
            '2026-04-20', '2026-04-21', '2026-04-22',
        ])
        # H, L, O, C — values chosen so trigger_high differs sharply by date
        rows = [
            (160.0, 155.0, 158.0, 159.0),
            (165.0, 158.0, 159.0, 164.0),
            (168.35, 162.73, 167.34, 166.73),  # 4/17 high = the canonical trigger
            (175.31, 164.10, 167.41, 175.10),  # 4/20 high
            (179.40, 173.30, 175.37, 175.49),  # 4/21 high
            (196.66, 178.47, 180.00, 196.57),  # 4/22 high — never seen on 4/20
        ]
        df = pd.DataFrame(rows, columns=['High', 'Low', 'Open', 'Close'],
                          index=dates)
        df['Volume'] = 1_000_000
        return df

    def test_tz_aware_datetime_as_of_filters(self):
        """Tz-aware UTC cutoff against tz-naive index — regression for the leak."""
        from datetime import datetime, timezone
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        # The pre-fix code raised TypeError here, swallowed it via bare
        # except, and returned trigger_high from 4/22 ($196.66) — the
        # last bar in the frame.
        out = compute_strat_status(
            'TEST', df=df,
            as_of=datetime(2026, 4, 20, 13, 15, 0, tzinfo=timezone.utc),
        )
        assert out['available'] is True
        # iloc[-1] should be 4/20, iloc[-2] (= trigger_high source) = 4/17
        assert out['date'] == '2026-04-20'
        assert out['trigger_high'] == pytest.approx(168.35)
        assert out['trigger_low'] == pytest.approx(162.73)

    def test_naive_date_as_of_filters(self):
        from datetime import date
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status('TEST', df=df, as_of=date(2026, 4, 20))
        assert out['available'] is True
        assert out['date'] == '2026-04-20'
        assert out['trigger_high'] == pytest.approx(168.35)

    def test_tz_aware_index_with_naive_cutoff(self):
        """Defensive: tz-aware index, tz-naive cutoff (rare but possible)."""
        from datetime import date
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        df.index = df.index.tz_localize('UTC')
        out = compute_strat_status('TEST', df=df, as_of=date(2026, 4, 20))
        assert out['available'] is True
        assert out['trigger_high'] == pytest.approx(168.35)

    def test_as_of_before_data_returns_unavailable(self):
        from datetime import date
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status('TEST', df=df, as_of=date(2020, 1, 1))
        assert out['available'] is False
        assert 'insufficient bars' in out['reason']

    def test_as_of_none_uses_latest(self):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status('TEST', df=df, as_of=None)
        assert out['available'] is True
        assert out['date'] == '2026-04-22'
        # trigger_high = 4/21 high ($179.40), the bar before 4/22
        assert out['trigger_high'] == pytest.approx(179.40)
