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


class TestInvalidObservations:
    """Invalid input must stay unknown and break pattern adjacency."""

    @pytest.mark.parametrize('labels', [
        pd.Series(['X', '2U', '2U'], index=[0, 2, 3]),
        pd.Series(['X', None, '2U', '2U']),
        pd.Series(['X', np.nan, '2U', '2U']),
        pd.Series(['X', pd.NA, '2U', '2U'], dtype='string'),
        pd.Series(['X', 'unrecognized', '2U', '2U']),
        pd.Series(['X', 2, '2U', '2U']),
    ], ids=['missing-index', 'none', 'nan', 'nullable-string', 'unknown-label', 'numeric-label'])
    def test_unknown_supplied_labels_keep_failure_facts_unavailable(self, classifier, labels):
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100),
                     (102, 92, 96, 101), (103, 93, 97, 102)])
        result = classifier.detect_combos(df, labels)
        assert result['strat_candle'].tolist() == ['X', 'X', '2U', '2U']
        unknown = result.iloc[1]
        assert pd.isna(unknown['failed_2u'])
        assert pd.isna(unknown['failed_2d'])
        assert unknown['strat_combo'] == 'none'
        assert unknown['pattern_facts'] == []
        assert result['strat_combo'].iloc[2] == 'clean_2u_bull'
        assert result['strat_combo'].iloc[3] == '22_bull_continuation'
        assert bool(result['failed_2u'].iloc[3]) is False

    def test_fully_misaligned_supplied_labels_are_all_unknown(self, classifier):
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100)])
        result = classifier.detect_combos(df, pd.Series(['X', '2U'], index=[10, 11]))
        assert result['strat_candle'].tolist() == ['X', 'X']
        assert result['failed_2u'].isna().all()
        assert result['failed_2d'].isna().all()
        assert result['strat_combo'].tolist() == ['none', 'none']

    def test_supplied_nullable_canonical_labels_are_preserved(self, classifier, known_strat_sequence):
        labels = pd.Series(['X', '1', '2U', '2D', '3'],
                           index=known_strat_sequence.index, dtype='string')
        result = classifier.detect_combos(known_strat_sequence, labels)
        assert result['strat_candle'].tolist() == ['X', '1', '2U', '2D', '3']
        assert result['strat_combo'].tolist() == [
            'none', 'none', 'clean_2u_bull', '22_bear_reversal', 'none',
        ]

    @pytest.mark.parametrize('values', [
        (np.nan, 95, 100, 90), (100, np.inf, 100, 90),
        (101, 95, np.inf, 90), (101, 95, 100, np.nan),
        (90, 95, 100, 90), (101, 95, 90, 100),
        (None, 95, 100, 90), (101, pd.NA, 100, 90),
        ('bad', 95, 100, 90),
    ])
    def test_invalid_current_or_previous_range_is_unknown(self, classifier, values):
        assert classifier.classify_candle(*values) == 'X'

    @pytest.mark.parametrize('column,value', [
        ('High', np.nan), ('Low', np.inf), ('High', 89),
        ('Open', 101), ('Close', 89), ('Open', np.nan), ('Close', np.inf),
    ])
    def test_invalid_ohlc_breaks_adjacency(self, classifier, column, value):
        from lib.strat import validate_ohlc_rows
        df = _frame([(100, 90, 95, 96)] * 4).astype(float)
        df.loc[1, column] = value
        assert validate_ohlc_rows(df).tolist() == [True, False, True, True]
        assert classifier.classify_series(df).tolist() == ['X', 'X', 'X', '1']
        assert classifier.detect_combos(df)['strat_combo'].tolist() == ['none'] * 4

    def test_high_low_only_is_explicit_legacy_classification(self, classifier):
        df = pd.DataFrame({'High': [100, 101], 'Low': [90, 91]})
        assert classifier.classify_series(df).tolist() == ['X', '2U']
        facts = classifier.detect_combos(df).iloc[-1]
        assert facts['strat_combo'] == 'none'
        assert facts['candle_color'] == 'unknown'
        assert pd.isna(facts['failed_2u'])
        assert pd.isna(facts['close_location'])

    def test_strict_validator_requires_complete_ohlc(self):
        from lib.strat import validate_ohlc_rows
        with pytest.raises(ValueError, match='Open.*Close'):
            validate_ohlc_rows(pd.DataFrame({'High': [100], 'Low': [90]}))

    def test_empty_series_is_empty(self, classifier):
        assert classifier.classify_series(_frame([])).empty

    def test_null_placeholder_preserves_position(self, classifier):
        df = pd.DataFrame({'High': [None, None], 'Low': [None, None],
                           'Open': [None, None], 'Close': [None, None]})
        result = classifier.detect_combos(df)
        assert result['strat_candle'].tolist() == ['X', 'X']
        assert result['candle_color'].tolist() == ['unknown', 'unknown']

    def test_nullable_price_placeholder_stays_unknown(self, classifier):
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100)]).astype('Float64')
        df.loc[1, 'Open'] = pd.NA
        assert classifier.classify_series(df).tolist() == ['X', 'X']

    @pytest.mark.parametrize('column', ['Open', 'High', 'Low', 'Close'])
    def test_malformed_price_value_is_invalid_without_losing_rows(self, classifier, column):
        from lib.strat import validate_ohlc_rows
        df = _frame([(100, 90, 95, 96)] * 4).astype(object)
        df.loc[1, column] = 'bad vendor value'
        assert validate_ohlc_rows(df).tolist() == [True, False, True, True]
        result = classifier.detect_combos(df)
        assert result['strat_candle'].tolist() == ['X', 'X', 'X', '1']
        assert result['candle_color'].iloc[1] == 'unknown'

    @pytest.mark.parametrize('column,value', [('High', 'bad'), ('Open', 101), ('Low', np.inf)])
    def test_invalid_prior_bar_has_no_trigger_lines(self, classifier, column, value):
        df = _frame([(100, 90, 95, 96)] * 3).astype(object)
        df.loc[1, column] = value
        result = classifier.detect_combos(df)
        assert pd.isna(result['trigger_high'].iloc[2])
        assert pd.isna(result['trigger_low'].iloc[2])

    def test_last_alias_keeps_failure_fact_with_explicit_source(self, classifier):
        df = _frame([(100, 90, 95, 96), (101, 91, 100, 95)]).rename(columns={'Close': 'Last'})
        row = classifier.detect_combos(df).iloc[-1]
        assert row['strat_combo'] == 'f2u_bear_reversal'
        assert bool(row['failed_2u']) is True
        assert row['close_source'] == 'Last'
        df.loc[1, 'Last'] = 89
        assert classifier.classify_series(df).tolist() == ['X', 'X']

    def test_canonical_close_wins_over_last_alias(self, classifier):
        df = _frame([(100, 90, 95, 96), (101, 91, 100, 95)])
        df['Last'] = [96, 101]
        row = classifier.detect_combos(df).iloc[-1]
        assert row['strat_combo'] == 'f2u_bear_reversal'
        assert row['close_source'] == 'Close'

    def test_explicit_intraday_gap_stays_unknown(self, classifier):
        df = _frame([(100, 90, 95, 96), (101, 91, 95, 100),
                     (102, 92, 96, 101), (103, 93, 97, 102)])
        df.index = pd.to_datetime(['2026-10-08 09:30', '2026-10-08 09:31',
                                   '2026-10-08 09:33', '2026-10-08 09:34'])
        df.attrs['expected_interval'] = '1min'
        result = classifier.detect_combos(df)
        assert result['strat_candle'].tolist() == ['X', '2U', 'X', '2U']
        assert result['gap_before'].tolist() == [False, False, True, False]
        assert result['strat_combo'].iloc[2] == 'none'
        assert result['strat_combo'].iloc[3] == 'clean_2u_bull'


class TestPatternTruthTable:
    @pytest.mark.parametrize('ranges,expected', [
        ([(100, 90), (99, 89), (98, 90), (99, 91)], '212_bull_reversal'),
        ([(100, 90), (101, 91), (100, 92), (99, 91)], '212_bear_reversal'),
        ([(100, 90), (101, 89), (100, 90), (101, 91)], '312_bull_reversal'),
        ([(100, 90), (101, 89), (100, 90), (99, 89)], '312_bear_reversal'),
        ([(100, 90), (99, 91), (100, 90), (101, 91)], '132_bull_continuation'),
        ([(100, 90), (99, 91), (100, 90), (99, 89)], '132_bear_continuation'),
        ([(100, 90), (101, 89), (102, 90), (103, 91)], '322_bull_continuation'),
        ([(100, 90), (101, 89), (100, 88), (99, 87)], '322_bear_continuation'),
        ([(100, 90), (101, 91), (100, 92), (101, 93)], '212_bull_continuation'),
        ([(100, 90), (99, 89), (98, 90), (97, 89)], '212_bear_continuation'),
        ([(100, 90), (101, 89), (102, 90)], '32_bull_reversal'),
        ([(100, 90), (101, 89), (100, 88)], '32_bear_reversal'),
        ([(100, 90), (99, 89), (100, 90)], '22_bull_reversal'),
        ([(100, 90), (101, 91), (100, 90)], '22_bear_reversal'),
        ([(100, 90), (101, 91), (102, 92)], '22_bull_continuation'),
        ([(100, 90), (99, 89), (98, 88)], '22_bear_continuation'),
        ([(100, 90), (99, 91), (100, 90), (99, 91)], '131_setup'),
        ([(100, 90), (99, 91), (98, 92), (97, 93)], '111_inside_compression'),
        ([(100, 90), (99, 91), (98, 92)], '11_inside_compression'),
        ([(100, 90), (101, 91)], 'clean_2u_bull'),
        ([(100, 90), (99, 89)], 'clean_2d_bear'),
    ])
    def test_documented_patterns_and_facts(self, classifier, ranges, expected):
        # Literal H/L sequences determine the pattern; midpoint dojis impose
        # no directional color filter and remain clean by methodology §2.
        df = _frame([(high, low, (high + low) / 2, (high + low) / 2)
                     for high, low in ranges])
        row = classifier.detect_combos(df).iloc[-1]
        assert row['strat_combo'] == expected
        assert expected in row['pattern_facts']

    @pytest.mark.parametrize('middle', [
        (99, 88, 95, 96),   # 2D
        (102, 91, 95, 96),  # 2U
        (102, 88, 95, 96),  # 3
    ])
    def test_outside_terminal_cannot_be_directional_212_or_312(self, classifier, middle):
        df = _frame([(100, 90, 95, 96), middle,
                     (98, 92, 95, 96), (101, 89, 95, 96)])
        result = classifier.detect_combos(df)
        assert result['strat_candle'].iloc[-1] == '3'
        assert result['strat_combo'].iloc[-1] == 'none'
        assert result['pattern_facts'].iloc[-1] == []

    @pytest.mark.parametrize('outside_open,outside_close', [(95, 100), (100, 95), (97, 97)])
    @pytest.mark.parametrize('terminal,expected', [
        ((104, 94, 95, 103), '32_bull_reversal'),
        ((101, 91, 100, 92), '32_bear_reversal'),
    ])
    def test_32_does_not_filter_outside_color(self, classifier, outside_open, outside_close,
                                             terminal, expected):
        result = classifier.detect_combos(_frame([
            (100, 95, 97, 98), (102, 93, outside_open, outside_close), terminal,
        ]))
        assert result['strat_combo'].iloc[-1] == expected

    def test_failed_2d_survives_322_priority(self, classifier):
        # Synthetic IWM-shape reproduction; not a captured October 8 price tape.
        df = _frame([(100, 90, 95, 96), (102, 88, 95, 96),
                     (101, 87, 95, 90), (100, 86, 88, 94)])
        row = classifier.detect_combos(df).iloc[-1]
        assert row['strat_combo'] == '322_bear_continuation'
        assert bool(row['failed_2d']) is True
        assert bool(row['failed_2u']) is False
        assert row['candle_color'] == 'green'
        assert row['close_location'] == pytest.approx(8 / 14)
        assert row['pattern_facts'] == [
            '322_bear_continuation', '22_bear_continuation', 'f2d_bull_reversal',
        ]

    def test_captured_iwm_october_8_failed_2d_survives_22_priority(self, classifier):
        # Current-vintage Alpha Vantage daily capture, acquired for the October
        # baseline; not contemporaneously acquired live observations. All rows
        # precede or equal October 8; no later close enters this fixture.
        df = _frame([
            (280.61, 275.45, 277.36, 279.02),  # 2026-10-01
            (283.565, 280.89, 282.33, 281.52), # 2026-10-02
            (284.24, 280.03, 281.95, 283.38),  # 2026-10-05
            (284.64, 280.76, 284.40, 281.34),  # 2026-10-06
            (279.04, 276.945, 278.25, 277.70), # 2026-10-07
            (277.83, 274.52, 276.32, 277.57),  # 2026-10-08
        ])
        df.index = pd.to_datetime(['2026-10-01', '2026-10-02', '2026-10-05',
                                   '2026-10-06', '2026-10-07', '2026-10-08'])
        row = classifier.detect_combos(df).iloc[-1]
        assert row['strat_candle'] == '2D'
        assert row['strat_combo'] == '22_bear_continuation'
        assert bool(row['failed_2d']) is True
        assert row['candle_color'] == 'green'
        assert row['pattern_facts'] == ['22_bear_continuation', 'f2d_bull_reversal']

    def test_all_overlapping_132_32_and_clean_facts_survive(self, classifier):
        row = classifier.detect_combos(_frame([
            (100, 90, 95, 96), (99, 91, 95, 96),
            (101, 89, 95, 100), (102, 90, 95, 101),
        ])).iloc[-1]
        assert row['strat_combo'] == '132_bull_continuation'
        assert row['pattern_facts'] == [
            '132_bull_continuation', '32_bull_reversal', 'clean_2u_bull',
        ]

    def test_compression_is_current_streak_not_two_bar_sum(self, classifier):
        result = classifier.detect_combos(_frame([
            (110, 90, 99, 100), (109, 91, 99, 100), (108, 92, 99, 100),
            (107, 93, 99, 100), (111, 94, 99, 110),
        ]))
        assert result['consecutive_1s'].tolist() == [0, 1, 2, 3, 0]
        assert result['pattern_facts'].iloc[3] == [
            '111_inside_compression', '11_inside_compression',
        ]

    def test_legacy_rule_keeps_two_bar_compression_feature(self):
        """legacy-pattern-v1 feeds persisted research feature tables; its
        consecutive_1s keeps main's two-bar rolling sum (Codex r4476732524)."""
        result = StratClassifier(rule_version='legacy-pattern-v1').detect_combos(_frame([
            (110, 90, 99, 100), (109, 91, 99, 100), (108, 92, 99, 100),
            (107, 93, 99, 100), (111, 94, 99, 110),
        ]))
        assert result['consecutive_1s'].tolist() == [0, 1, 2, 2, 1]

    def test_zero_range_doji_has_no_invented_close_location(self, classifier):
        row = classifier.detect_combos(_frame([(100, 90, 95, 96), (95, 95, 95, 95)])).iloc[-1]
        assert row['candle_color'] == 'doji'
        assert pd.isna(row['close_location'])

    def test_supplied_labels_cannot_reclassify_invalid_prices(self, classifier):
        df = _frame([(100, 90, 95, 96), (np.nan, np.nan, np.nan, np.nan)])
        row = classifier.detect_combos(df, pd.Series(['X', '2U'])).iloc[-1]
        assert row['strat_candle'] == 'X'
        assert row['strat_combo'] == 'none'


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


class TestSetupVsComboOrthogonality:
    """Lock in the documented orthogonality between `strat_setup` and
    `strat_combo` (Track B audit B.5 / G.P1.6).

    `strat_setup` flips True ONLY when the latest bar is '1' (inside)
    AND the prior bar is directional ('2U'/'2D'/'3') — read as
    "inside-bar pending, watch the next bar's break". `strat_combo`
    is the multi-bar pattern label and is independent: continuation
    combos like 322 / 22 / clean_2u FIRE on a directional bar, so the
    latest bar is '2U' or '2D' (not '1') and `strat_setup` MUST be
    False on those rows.

    The audit originally flagged a row with strat_combo='322_bull_continuation'
    AND strat_setup=False as "internally inconsistent." Walking the
    truth table revealed it's the documented behaviour. These tests
    pin it so the next time someone notices, they get a concrete
    failure pointing at this docstring rather than rediscovering the
    contract from scratch.
    """

    def test_322_continuation_has_setup_false(self, classifier):
        """The audit's specific reproduction: a 322_bull_continuation
        row publishes strat_combo populated AND strat_setup=False,
        because the row's own bar is '2U' (directional), not '1'.
        That's correct, not a bug."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 93, 97, 100),   # 3
            (104, 94, 100, 103),  # 2U
            (106, 95, 103, 105),  # 2U → 322_bull_continuation
        ])
        result = classifier.detect_combos(df)
        # Combo populated
        assert result.iloc[3]['strat_combo'] == '322_bull_continuation'
        # Setup flag MUST be False — last bar is 2U, not 1
        assert result.iloc[3]['strat_setup'] is False or \
            result.iloc[3]['strat_setup'] == False, (
                "322_bull_continuation row must have strat_setup=False "
                "(last bar is 2U, not the inside bar required for setup)"
            )
        # Sanity: the same row's strat_candle is '2U'
        assert result.iloc[3]['strat_candle'] == '2U'

    def test_22_continuation_also_has_setup_false(self, classifier):
        """Same orthogonality for any continuation combo whose latest
        bar is directional. 22_bull_continuation: 2U → 2U, last bar
        is 2U, setup=False."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 96, 97, 100),   # 2U
            (104, 97, 100, 103),  # 2U → 22_bull_continuation
        ])
        result = classifier.detect_combos(df)
        assert result.iloc[2]['strat_combo'] == '22_bull_continuation'
        assert not result.iloc[2]['strat_setup']

    def test_setup_true_only_when_last_bar_is_inside_after_directional(
        self, classifier,
    ):
        """The dual: setup=True ONLY when the latest bar IS an inside
        bar following a directional bar — regardless of whether a
        named combo also fires. 2U → 1: setup=True, combo='none'
        (bare inside-bar setup, not yet a 2-1-2)."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 96, 97, 100),   # 2U
            (101, 97, 99, 99),    # 1 (inside; H<=102, L>=96)
        ])
        result = classifier.detect_combos(df)
        # Last bar IS the inside bar — setup must fire
        assert result.iloc[2]['strat_setup'] is True or \
            result.iloc[2]['strat_setup'] == True, (
                "2U → 1 row should have strat_setup=True"
            )
        # No multi-bar combo on that row yet (the 212 needs the next
        # break)
        assert result.iloc[2]['strat_combo'] == 'none'

    def test_setup_false_when_last_bar_is_inside_after_inside(
        self, classifier,
    ):
        """Setup also requires the PRIOR bar to be directional. Two
        inside bars in a row → setup=False (no preceding directional
        bar to anchor the watch-the-break logic)."""
        df = _frame([
            (100, 95, 97, 98),
            (102, 96, 97, 100),   # 2U
            (101, 97, 99, 99),    # 1 (inside)
            (100, 98, 98, 99),    # 1 (inside again; H<=101, L>=97)
        ])
        result = classifier.detect_combos(df)
        # Latest bar is 1 but prior bar is also 1 — setup=False
        assert result.iloc[3]['strat_candle'] == '1'
        assert not result.iloc[3]['strat_setup']


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

    def test_reclassification_replaces_existing_facts_without_duplicate_columns(self, classifier):
        df = _frame([(100, 90, 95, 96), (101, 91, 100, 95)])
        once = classifier.add_strat_columns(df)
        once.loc[1, 'Close'] = 101
        twice = classifier.add_strat_columns(once)
        assert twice.columns.is_unique
        assert twice['strat_candle'].tolist() == ['X', '2U']
        assert bool(twice['failed_2u'].iloc[1]) is False
        assert twice['pattern_facts'].iloc[1] == ['clean_2u_bull']


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
        # 09:15 Eastern cannot observe the later 4/20 OHLC. Latest is
        # 4/17; the trigger is the completed 4/16 bar.
        assert out['date'] == '2026-04-17'
        assert out['trigger_high'] == pytest.approx(165.0)
        assert out['trigger_low'] == pytest.approx(158.0)

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

    # ── inclusive_today contract (added 2026-05-11) ────────────────────
    #
    # `as_of` semantic by default is inclusive (`<=`) for legacy backtest
    # callers that want "the strat as of close of day X". The premarket
    # contract — used by the insight pipeline AND the brief — is strict
    # (`<`): today's bar isn't visible because at 8:30 AM ET on day X,
    # today's daily row either hasn't been written yet OR has NULL OHLC.

    def test_inclusive_today_default_true_legacy_contract(self):
        """Default inclusive_today=True → as_of=4/20 includes the 4/20 bar."""
        from datetime import date
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status('TEST', df=df, as_of=date(2026, 4, 20))
        assert out['available'] is True
        assert out['date'] == '2026-04-20'                 # ← 4/20 included
        # iloc[-2] = 4/17 = the trigger source
        assert out['trigger_high'] == pytest.approx(168.35)

    def test_inclusive_today_false_premarket_contract(self):
        """inclusive_today=False → as_of=4/20 excludes the 4/20 bar.

        Mirrors the brief's `idx < cutoff` semantic. iloc[-1] becomes
        the most recent completed bar BEFORE 4/20, which is 4/17.
        trigger_high then comes from iloc[-2] = 4/16 ($165.0).
        """
        from datetime import date
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status(
            'TEST', df=df, as_of=date(2026, 4, 20),
            inclusive_today=False,
        )
        assert out['available'] is True
        assert out['date'] == '2026-04-17'                 # ← 4/20 excluded
        # iloc[-2] is now 4/16, high = 165.0
        assert out['trigger_high'] == pytest.approx(165.0)

    def test_inclusive_today_false_with_tz_aware_datetime(self):
        """Strict-less semantic also handles tz-aware as_of correctly."""
        from datetime import datetime, timezone
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status(
            'TEST', df=df,
            as_of=datetime(2026, 4, 20, 13, 15, 0, tzinfo=timezone.utc),
            inclusive_today=False,
        )
        assert out['available'] is True
        assert out['date'] == '2026-04-17'                 # 4/20 excluded
        assert out['trigger_high'] == pytest.approx(165.0)

    @pytest.mark.parametrize('placeholder', [False, True])
    @pytest.mark.parametrize('inclusive', [False, True])
    def test_frozen_live_and_replay_exclude_unfinished_daily(self, monkeypatch, placeholder, inclusive):
        from lib import strat
        clock = pd.Timestamp('2026-04-20 10:30', tz='America/New_York')
        monkeypatch.setattr(strat, 'eastern_now', lambda: clock, raising=False)
        df = self._build_daily_df()
        if placeholder:
            df.loc['2026-04-20', ['Open', 'High', 'Low', 'Close']] = np.nan
        live = strat.compute_strat_status('TEST', df=df, inclusive_today=inclusive)
        replay = strat.compute_strat_status('TEST', df=df, as_of=clock, inclusive_today=inclusive)
        assert live['date'] == replay['date'] == '2026-04-17'
        assert live == replay
        assert live['observation_ts'] == clock.isoformat()
        assert live['data_as_of'] == '2026-04-17T16:00:00-04:00'
        assert live['coverage']['1w']['partial'] is True
        assert live['coverage']['1w']['period_open_observed'] is False

    def test_date_only_eod_and_instant_are_distinct(self):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        # Include Monday/Tuesday so the prior weekly range is fully observed;
        # a truncated prior week must not supply a known comparison/vote.
        opening = df.iloc[[0, 0]].copy()
        opening.index = pd.to_datetime(['2026-04-13', '2026-04-14'])
        df = pd.concat([opening, df])
        eod = compute_strat_status('TEST', df=df, as_of='2026-04-20')
        intraday = compute_strat_status('TEST', df=df, as_of='2026-04-20T15:59:00-04:00')
        assert eod['date'] == '2026-04-20'
        assert intraday['date'] == '2026-04-17'
        assert eod['clock_policy'] == 'date_only_eod'
        assert intraday['clock_policy'] == 'observation_instant'
        assert eod['ftfc_score'] == pytest.approx(1.0)  # unchanged equal-input legacy vote

    def test_malformed_completed_bar_is_not_replaced_by_older_valid_bar(self):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        df.loc['2026-04-20', 'Close'] = np.inf
        out = compute_strat_status('TEST', df=df, as_of='2026-04-20')
        assert out['available'] is False
        assert out['date'] == '2026-04-20'
        assert out['bar_validity']['valid'] is False
        assert 'invalid_ohlc' in out['bar_validity']['reasons']
        assert out['last_candle'] == 'X'
        assert out['rule_version']
        assert out['coverage']['1d']['available'] is False

    @pytest.mark.parametrize('clock,want', [
        ('2026-04-21T01:00:00+00:00', '2026-04-17'),
        ('2026-04-21T05:00:00+00:00', '2026-04-20'),
    ])
    def test_strict_cutoff_uses_eastern_observation_date(self, clock, want):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        df.index = df.index.tz_localize('UTC')  # session labels, not instants
        out = compute_strat_status('TEST', df=df, as_of=clock, inclusive_today=False)
        assert out['date'] == want

    @pytest.mark.parametrize('clock,want', [
        ('2026-11-27T17:59:00Z', '2026-11-25'),
        ('2026-11-27T18:00:00Z', '2026-11-27'),  # NYSE 13:00 half-day close
        ('2026-11-26T23:00:00Z', '2026-11-25'),  # Thanksgiving closed
        ('2026-11-30T20:59:00Z', '2026-11-27'),  # EST close is 21:00Z
    ])
    def test_holiday_halfday_and_standard_time_cutoff(self, clock, want):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        df.index = pd.to_datetime(['2026-11-23', '2026-11-24', '2026-11-25',
                                   '2026-11-26', '2026-11-27', '2026-11-30'])
        out = compute_strat_status('TEST', df=df, as_of=clock)
        assert out['date'] == want

    @pytest.mark.parametrize('clock,want', [
        ('2026-03-09T19:59:00Z', '2026-03-06'),
        ('2026-03-09T20:00:00Z', '2026-03-09'),
    ])
    def test_dst_close_uses_exchange_clock(self, clock, want):
        from lib.strat import compute_strat_status
        df = self._build_daily_df().iloc[:3].copy()
        df.index = pd.to_datetime(['2026-03-05', '2026-03-06', '2026-03-09'])
        assert compute_strat_status('TEST', df=df, as_of=clock)['date'] == want

    def test_unavailable_retains_clock_and_coverage(self):
        from lib.strat import compute_strat_status
        out = compute_strat_status('TEST', df=self._build_daily_df(), as_of='2020-01-01')
        assert out['available'] is False
        assert out['rule_version']
        assert out['observation_ts'].startswith('2020-01-01')
        assert out['data_as_of'] is None
        assert out['coverage']['1mo']['available'] is False

    def test_partial_periods_and_missing_period_open_remain_distinct(self):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        out = compute_strat_status('TEST', df=df, as_of='2026-04-22',
                                   timeframes=['1d', '1w', '1mo', '1q', '1y'])
        week, month = out['coverage']['1w'], out['coverage']['1mo']
        assert week['partial'] is True
        assert week['coverage_complete'] is True
        assert week['period_open_observed'] is True
        assert week['open'] == 167.41
        assert week['source_cutoff'] == '2026-04-22T16:00:00-04:00'
        assert month['partial'] is True
        assert month['coverage_complete'] is False
        assert month['period_open_observed'] is False
        assert month['open'] is None
        assert 'missing_period_open' in month['reasons']
        assert out['coverage']['1q']['period_start'].startswith('2026-04-01')
        assert out['coverage']['1y']['period_start'].startswith('2026-01-02')


    def test_invalid_previous_bar_does_not_publish_known_classification(self):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        df.loc['2026-04-17', 'Close'] = np.nan
        out = compute_strat_status('TEST', df=df, as_of='2026-04-20')
        assert out['available'] is False
        assert out['date'] == '2026-04-20'
        assert out['last_candle'] == 'X'
        assert 'invalid_previous_ohlc' in out['bar_validity']['reasons']

    def test_missing_session_does_not_publish_known_classification(self):
        from lib.strat import compute_strat_status
        df = self._build_daily_df().drop(pd.Timestamp('2026-04-17'))
        out = compute_strat_status('TEST', df=df, as_of='2026-04-20')
        assert out['available'] is False
        assert out['last_candle'] == 'X'
        assert 'missing_previous_observation' in out['bar_validity']['reasons']

    @pytest.mark.parametrize('attrs,reason', [
        ({'session_policy': 'unknown'}, 'unknown_session_policy'),
        ({'source_resolution': '1min'}, 'unsupported_daily_source_resolution'),
        ({'source_resolution': 'unknown'}, 'unsupported_daily_source_resolution'),
        ({'timestamp_semantics': 'bar_start'}, 'unsupported_timestamp_semantics'),
    ])
    def test_explicit_unknown_snapshot_contract_is_not_rewritten(self, attrs, reason):
        from lib.strat import compute_strat_status
        df = self._build_daily_df()
        df.attrs.update(source_resolution='1d', session_policy='NYSE_regular',
                        timestamp_semantics='session_label')
        df.attrs.update(attrs)
        out = compute_strat_status('TEST', df=df, as_of='2026-04-20')
        assert out['available'] is False
        assert reason in out['bar_validity']['reasons']
        for key, value in attrs.items():
            assert out['coverage']['1d'][key] == value
        assert out['data_as_of'] is None


class TestContinuityContracts:
    """Catch subset agreement, prior-open substitution and weighted/strict conflation."""

    @staticmethod
    def observed(open_=98., label='2U', **coverage):
        bars = {'2U': [(100, 90, 95, 96), (101, 91, 98, 97)],
                '2D': [(100, 90, 95, 96), (99, 89, 94, 95)],
                '1': [(100, 90, 95, 96), (99, 91, 94, 95)],
                '3': [(100, 90, 95, 96), (101, 89, 94, 95)]}
        frame = _frame(bars[label])
        if np.isfinite(open_):
            # Keep the declared current open coherent with the OHLC fixture.
            columns = ['High', 'Low', 'Open', 'Close']
            frame[columns] = frame[columns] + (open_ - frame.iloc[-1]['Open'])
        frame.index = pd.to_datetime(['2026-04-17', '2026-04-20'])
        record = dict(aggregation_policy='observed_v2', available=True,
                      coverage_complete=True, period_open_observed=True, open=open_,
                      period_start='2026-04-20T09:30:00-04:00',
                      period_end='2026-04-24T16:00:00-04:00',
                      partial=True, completed=False, source_resolution='1d',
                      session_policy='NYSE_regular', timestamp_semantics='session_label',
                      source_cutoff='2026-04-20T16:00:00-04:00', source_age_seconds=0.,
                      source_acquired_at=None, price_adjustment='unknown', reasons=[])
        record.update(coverage)
        frame.attrs.update(aggregation_policy='observed_v2', coverage=record,
                           period_key_semantics='session_label',
                           period_coverage={frame.index[-1].isoformat(): record.copy()})
        return frame

    @pytest.mark.parametrize('opens,price,want', [([98,99],100,'bullish'),
        ([102,101],100,'bearish'), ([98,102],100,'mixed'), ([100,98],100,'mixed')])
    def test_one_price_against_every_current_open(self, opens, price, want):
        from lib.strat import calculate_timeframe_continuity
        frames = dict(zip(['1d','1w'], [self.observed(o) for o in opens]))
        result = calculate_timeframe_continuity(frames, price, ['1d','1w'])
        assert result['version'] == 'price-open-v1'
        assert result['available'] is True
        assert result['direction'] == want
        assert result['full_continuity'] is (want != 'mixed')
        assert result['frames']['1d']['relation'] == ('at_open' if opens[0] == price else
                                                      'above' if opens[0] < price else 'below')

    @pytest.mark.parametrize('required', [[], ['1d','1mo']])
    def test_empty_required_or_missing_month_cannot_assert_agreement(self, required):
        from lib.strat import calculate_timeframe_continuity
        result = calculate_timeframe_continuity({'1d': self.observed()}, 100, required)
        assert result['available'] is False
        assert result['direction'] == 'unavailable'
        assert result['full_continuity'] is False
        assert result['reasons']

    @pytest.mark.parametrize('price', [None, np.nan, np.inf, 'bad'])
    def test_nonfinite_observed_price_is_not_invented(self, price):
        from lib.strat import calculate_timeframe_continuity
        result = calculate_timeframe_continuity({'1d': self.observed()}, price, ['1d'])
        assert result['available'] is False
        assert 'invalid_observed_price' in result['reasons']

    @pytest.mark.parametrize('updates,reason', [
        ({'open':np.nan},'invalid_period_open'),
        ({'period_open_observed':False,'open':None},'missing_period_open'),
        ({'available':False},'unavailable_coverage'),
        ({'coverage_complete':False},'incomplete_coverage'),
        ({'session_policy':'unknown'},'unknown_session_policy'),
        ({'reasons':['source_resolution_too_coarse']},'source_resolution_too_coarse'),
        ({'reasons':['stale_source']},'stale_source'),
    ])
    def test_unsafe_required_coverage_is_unavailable(self, updates, reason):
        from lib.strat import calculate_timeframe_continuity
        result = calculate_timeframe_continuity({'1d': self.observed(**updates)}, 100, ['1d'])
        assert result['available'] is False
        assert reason in result['frames']['1d']['reasons']

    def test_partial_observed_open_preserves_unknown_provenance_and_age(self):
        from lib.strat import calculate_timeframe_continuity
        result = calculate_timeframe_continuity({'1w': self.observed(source_age_seconds=86400)}, 100, ['1w'])
        frame = result['frames']['1w']
        assert result['direction'] == 'bullish'
        assert frame['coverage']['partial'] is True
        assert frame['coverage']['source_age_seconds'] == 86400
        assert frame['coverage']['source_acquired_at'] is None
        assert frame['coverage']['price_adjustment'] == 'unknown'
        assert result['freshness_policy'] == 'unknown'

    def test_last_retained_open_never_replaces_missing_current_open(self):
        from lib.strat import calculate_timeframe_continuity
        frame = self.observed(available=False, period_open_observed=False, open=None)
        assert frame.iloc[-1]['Open'] == 98
        result = calculate_timeframe_continuity({'1d': frame}, 100, ['1d'])
        assert result['frames']['1d']['open'] is None
        assert result['direction'] == 'unavailable'

    def test_plain_or_legacy_frame_does_not_certify_strict_coverage(self):
        from lib.strat import calculate_timeframe_continuity
        frame = self.observed()
        frame.attrs['aggregation_policy'] = 'legacy_v1'
        result = calculate_timeframe_continuity({'1d': frame}, 100, ['1d'])
        assert 'unsupported_aggregation_policy' in result['frames']['1d']['reasons']
        frame.attrs.clear()
        assert calculate_timeframe_continuity({'1d':frame},100,['1d'])['available'] is False

    def test_aliases_resolve_but_duplicate_aliases_are_explicit_conflicts(self):
        from lib.strat import calculate_timeframe_continuity
        frame = self.observed()
        result = calculate_timeframe_continuity({'60m':frame},100,['1h'])
        assert result['direction'] == 'bullish'
        assert result['frames']['1h']['input_timeframe'] == '60m'
        with pytest.raises(ValueError, match='alias'):
            calculate_timeframe_continuity({'60m':frame,'1h':frame},100,['1h'])
        with pytest.raises(ValueError, match='alias'):
            calculate_timeframe_continuity({'1h':frame},100,['60m','1h'])

    @pytest.mark.parametrize('labels,want', [(['2U','2U'],'bullish'),(['2D','2D'],'bearish'),
        (['2U','2D'],'mixed'),(['2U','1'],'mixed'),(['2U','3'],'mixed')])
    def test_directional_candles_use_classes_not_color_or_vote(self, labels, want):
        from lib.strat import calculate_directional_candle_continuity
        frames = dict(zip(['1d','1w'],[self.observed(label=label) for label in labels]))
        result = calculate_directional_candle_continuity(frames,['1d','1w'])
        assert result['direction'] == want
        assert result['version'] == 'directional-candle-v1'
        assert result['frames']['1w']['coverage']['partial'] is True

    def test_unknown_and_prior_period_candles_cannot_claim_continuity(self):
        from lib.strat import calculate_directional_candle_continuity
        frame = self.observed()
        frame.iloc[-1, frame.columns.get_loc('High')] = np.nan
        assert calculate_directional_candle_continuity({'1w':frame},['1w'])['available'] is False
        frame = self.observed()
        frame.attrs['coverage']['period_start'] = '2026-04-27T09:30:00-04:00'
        result = calculate_directional_candle_continuity({'1w':frame},['1w'])
        assert 'missing_current_period_candle' in result['frames']['1w']['reasons']

    def test_monthly_zero_weight_is_still_required_and_denominator_is_actual(self, classifier):
        from lib.strat import calculate_timeframe_continuity
        frames = {'1d':self.observed(), '1w':self.observed(label='1'),
                  '1mo':self.observed(102,label='2D'), '15m':pd.DataFrame()}
        score, direction, labels = classifier.calculate_ftfc(frames)
        assert score == pytest.approx(.75)
        assert direction == 'bullish'
        descriptor = classifier.describe_weighted_candle_alignment(frames)
        assert descriptor['version'] == 'legacy-candle-v1'
        assert descriptor['score'] == score
        assert descriptor['labels'] == labels
        assert descriptor['denominator'] == pytest.approx(.4)
        assert descriptor['contributing_frames'] == ['1d','1w']
        assert descriptor['zero_weight_frames'] == ['1mo']
        assert '15m' in descriptor['missing_frames']
        assert descriptor['frames']['1w']['weighted_contribution'] == 0
        assert descriptor['weights']['1d'] == .3
        assert calculate_timeframe_continuity(frames,100,['1d','1w','1mo'])['direction'] == 'mixed'

    def test_custom_legacy_weights_and_alias_keys_are_not_rewritten(self, classifier):
        frames = {'60m':self.observed(), '1h':self.observed(label='2D')}
        result = classifier.describe_weighted_candle_alignment(frames, {'60m':.3,'1h':.1})
        assert result['score'] == pytest.approx(.5)
        assert result['denominator'] == .4
        assert result['weights'] == {'60m':.3,'1h':.1}
        assert result['frames']['60m']['canonical_timeframe'] == '1h'

    def test_snapshot_has_no_invented_current_quote(self):
        from lib.strat import compute_strat_status
        frame = self.observed()
        frame.attrs.clear()
        result = compute_strat_status('SPY',frame,as_of='2026-04-20')
        assert result['timeframe_continuity']['direction'] == 'unavailable'
        assert 'invalid_observed_price' in result['timeframe_continuity']['reasons']
        assert result['weighted_candle_alignment']['version'] == 'legacy-candle-v1'
        assert 'directional_candle_continuity' in result

    def test_legacy_pattern_mode_retains_valid_masks_but_never_invalid_labels(self):
        legacy = StratClassifier(rule_version='legacy-pattern-v1')
        frame = _frame([(100,90,95,96),(99,89,94,93),(98,90,94,95),(99,89,94,95)])
        assert legacy.detect_combos(frame).iloc[-1]['strat_combo'] == '212_bull_reversal'
        assert StratClassifier().detect_combos(frame).iloc[-1]['strat_combo'] == 'none'
        frame.loc[3,'Open'] = 200
        result = legacy.detect_combos(frame)
        assert result.iloc[-1]['strat_candle'] == 'X'
        assert result.iloc[-1]['strat_combo'] == 'none'
        with pytest.raises(ValueError,match='rule version'):
            StratClassifier(rule_version='unversioned')

    def test_no_denominator_is_explicit_even_though_legacy_zero_is_retained(self,classifier):
        result = classifier.describe_weighted_candle_alignment({'1mo':self.observed()})
        assert result['score'] == 0
        assert result['direction'] == 'mixed'
        assert result['available'] is False
        assert result['denominator'] == 0

    def test_declared_open_evidence_is_independent_of_prior_candle_cutoff(self):
        from lib.strat import calculate_timeframe_continuity, calculate_directional_candle_continuity
        frame = self.observed()
        frame.attrs['period_coverage'][frame.index[-1].isoformat()]['period_start'] = '2026-04-13T09:30:00-04:00'
        assert calculate_timeframe_continuity({'1w':frame},100,['1w'])['direction'] == 'bullish'
        assert calculate_directional_candle_continuity({'1w':frame},['1w'])['available'] is False

    def test_real_observed_adapter_partial_week_and_utc_intraday_key(self):
        from lib.data_loader import DataLoader
        from lib.strat import calculate_timeframe_continuity, calculate_directional_candle_continuity
        index = pd.date_range('2026-04-20 09:30',periods=10,freq='min',tz='America/New_York')
        values = 100 + np.arange(10)/100
        raw = pd.DataFrame({'Open':values,'High':values+.02,'Low':values-.02,'Close':values+.01,'Volume':100},index=index)
        raw.attrs.update(source_resolution='1min',session_policy='NYSE_regular',timestamp_semantics='bar_start')
        frames = DataLoader().build_multi_timeframe(raw,['5m'],observation_ts='2026-04-20 09:39:59-04:00',aggregation_policy='observed_v2')
        frames['5m'].index = frames['5m'].index.tz_convert('UTC')
        result = calculate_timeframe_continuity(frames,101,['5m'])
        assert result['direction'] == 'bullish'
        assert result['frames']['5m']['coverage']['partial'] is True
        assert calculate_directional_candle_continuity(frames,['5m'])['direction'] == 'bullish'

    def test_unannotated_range_only_frame_stays_unavailable_without_datetime_index(self):
        from lib.strat import calculate_directional_candle_continuity
        frame = _frame([(100,90,95,96),(101,91,95,96)])
        result = calculate_directional_candle_continuity({'1d':frame},['1d'])
        assert result['available'] is False
        assert 'unsupported_aggregation_policy' in result['frames']['1d']['reasons']

    def test_strict_candle_cannot_use_legacy_range_only_validity(self):
        from lib.strat import calculate_directional_candle_continuity
        frame = self.observed().drop(columns=['Open','Close'])
        result = calculate_directional_candle_continuity({'1d':frame},['1d'])
        assert result['available'] is False
        assert 'missing_ohlc_columns' in result['frames']['1d']['reasons']

    @pytest.mark.parametrize('semantics', [None,'unknown','utc_instant'])
    def test_missing_period_key_contract_cannot_claim_known_candle(self,semantics):
        from lib.strat import calculate_directional_candle_continuity
        frame = self.observed()
        frame.attrs['period_key_semantics'] = semantics
        result = calculate_directional_candle_continuity({'1d':frame},['1d'])
        assert result['available'] is False
        assert 'unknown_period_index' in result['frames']['1d']['reasons']

    def test_invalid_open_result_remains_json_serializable(self):
        import json
        from lib.strat import calculate_timeframe_continuity
        result = calculate_timeframe_continuity({'1d':self.observed(open_=np.inf)},100,['1d'])
        assert result['available'] is False
        json.dumps(result,allow_nan=False)
        assert result['frames']['1d']['coverage']['open'] is None

    @pytest.mark.parametrize('column', ['High','Low'])
    def test_legacy_pattern_mode_keeps_malformed_range_unknown(self,column):
        frame = _frame([(100,90,95,96),(99,89,94,93),(98,90,94,95),(99,89,94,95)]).astype(object)
        frame.loc[3,column] = 'malformed'
        result = StratClassifier(rule_version='legacy-pattern-v1').detect_combos(frame)
        assert result.iloc[-1]['strat_candle'] == 'X'
        assert result.iloc[-1]['strat_combo'] == 'none'


class TestClosedCandleConfirmation:
    """Owner rule: a setup confirms only after its selected candle has closed.

    Each case builds source rows where the target bar B is an inside bar after
    a 2U bar (a pending setup), then exercises the clock one minute before B's
    validated close, exactly at it, and with later rows perturbed.
    """

    # B and its previous bar P, Eastern wall time, on validated conventions:
    # intraday buckets anchor at the session open; 1w ends at the last session
    # close (Thanksgiving week 2024: Thursday holiday, Friday 13:00 close).
    INTRADAY = {
        '5m': (('2024-01-03 09:55', '2024-01-03 10:00'), ('2024-01-03 10:00', '2024-01-03 10:05')),
        '15m': (('2024-01-03 09:45', '2024-01-03 10:00'), ('2024-01-03 10:00', '2024-01-03 10:15')),
        '30m': (('2024-01-03 09:30', '2024-01-03 10:00'), ('2024-01-03 10:00', '2024-01-03 10:30')),
        '1h': (('2024-01-03 09:30', '2024-01-03 10:30'), ('2024-01-03 10:30', '2024-01-03 11:30')),
        '4h': (('2024-01-02 13:30', '2024-01-02 16:00'), ('2024-01-03 09:30', '2024-01-03 13:30')),
    }
    WEEKLY = (('2024-11-18', '2024-11-22'), ('2024-11-25', '2024-11-29'))
    WEEKLY_CLOSE = '2024-11-29 13:00'
    TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1w']

    @staticmethod
    def _rows(index, *, daily):
        frame = pd.DataFrame({'Low': 99.0, 'High': 101.0}, index=pd.DatetimeIndex(index))
        frame.attrs = {'source_resolution': '1d' if daily else '1min',
                       'session_policy': 'NYSE_regular',
                       'timestamp_semantics': 'session_label' if daily else 'bar_start'}
        return frame

    @staticmethod
    def _finish(frame):
        frame['Open'] = frame['Close'] = (frame['Low'] + frame['High']) / 2
        frame['Volume'] = 10.0
        return frame[['Open', 'High', 'Low', 'Close', 'Volume']]

    @classmethod
    def _source(cls, timeframe, b_range=(99.5, 101.5)):
        from lib.eastern_time import session_schedule
        if timeframe == '1w':
            sessions = session_schedule('2024-11-04', '2024-12-06').index
            frame = cls._rows(sessions, daily=True)
            (p_start, p_end), (b_start, b_end) = cls.WEEKLY
            frame.loc[p_start:p_end, ['Low', 'High']] = (99.0, 102.0)
            frame.loc[b_start:b_end, ['Low', 'High']] = b_range
            return cls._finish(frame)
        minutes = pd.date_range('2024-01-02 09:30', '2024-01-02 15:59', freq='min').append(
            pd.date_range('2024-01-03 09:30', '2024-01-03 15:59', freq='min'))
        frame = cls._rows(minutes, daily=False)
        (p_start, p_end), (b_start, b_end) = cls.INTRADAY[timeframe]
        p = (frame.index >= p_start) & (frame.index < p_end)
        b = (frame.index >= b_start) & (frame.index < b_end)
        frame.loc[p, ['Low', 'High']] = (99.0, 102.0)
        frame.loc[b, ['Low', 'High']] = b_range
        return cls._finish(frame)

    @classmethod
    def _b_window(cls, timeframe):
        if timeframe == '1w':
            return (pd.Timestamp('2024-11-25 09:30', tz='America/New_York'),
                    pd.Timestamp(cls.WEEKLY_CLOSE, tz='America/New_York'))
        start, end = cls.INTRADAY[timeframe][1]
        return (pd.Timestamp(start, tz='America/New_York'),
                pd.Timestamp(end, tz='America/New_York'))

    @classmethod
    def _confirm(cls, timeframe, clock, source=None):
        from lib.strat import compute_confirmed_setups
        source = cls._source(timeframe) if source is None else source
        key = 'daily_df' if timeframe == '1w' else 'intraday_df'
        out = compute_confirmed_setups(observation_ts=clock, timeframes=[timeframe],
                                       **{key: source})
        return out, out['timeframes'][timeframe]

    @staticmethod
    def _decision(result):
        return {key: result[key] for key in
                ('state', 'confirmed', 'candle', 'combo', 'setup', 'period_start',
                 'period_end', 'reasons')}

    @pytest.mark.parametrize('timeframe', TIMEFRAMES)
    def test_developing_candle_is_not_confirmed_before_close(self, timeframe):
        start, end = self._b_window(timeframe)
        clock = end - pd.Timedelta(minutes=1)
        out, result = self._confirm(timeframe, clock)
        assert result['developing']['state'] == 'developing'
        assert pd.Timestamp(result['developing']['period_end']) == end
        assert result['developing']['confirmed'] is False
        assert pd.Timestamp(result['period_end']) <= start
        assert timeframe not in out['confirmed'] or result['period_end'] != end.isoformat()
        # Cutoff precedes aggregation: B's observed rows cannot leak in.
        source = self._source(timeframe)
        stamps = source.index if timeframe != '1w' else source.index + pd.Timedelta(hours=16)
        stamps = pd.DatetimeIndex(stamps).tz_localize('America/New_York')
        truncated = source.loc[(stamps < start).tolist()]
        _, before = self._confirm(timeframe, clock, truncated)
        assert {k: result[k] for k in ('state', 'candle', 'combo', 'setup', 'period_start')} == \
            {k: before[k] for k in ('state', 'candle', 'combo', 'setup', 'period_start')}

    @pytest.mark.parametrize('timeframe', TIMEFRAMES)
    def test_same_setup_confirms_exactly_at_close(self, timeframe):
        start, end = self._b_window(timeframe)
        out, result = self._confirm(timeframe, end)
        assert result['state'] == 'confirmed', result
        assert result['confirmed'] is True and timeframe in out['confirmed']
        assert result['candle'] == '1' and result['setup'] is True
        assert pd.Timestamp(result['period_start']) == start
        assert pd.Timestamp(result['period_end']) == end
        assert result['reasons'] == []

    @pytest.mark.parametrize('timeframe', TIMEFRAMES)
    def test_later_rows_cannot_change_the_confirmed_result(self, timeframe):
        _, end = self._b_window(timeframe)
        source = self._source(timeframe)
        _, baseline = self._confirm(timeframe, end, source)
        perturbed = source.copy()
        stamps = perturbed.index if timeframe != '1w' else perturbed.index + pd.Timedelta(hours=9, minutes=30)
        later = (pd.DatetimeIndex(stamps).tz_localize('America/New_York') >= end)
        assert later.any()
        perturbed.loc[later, ['Open', 'High', 'Low', 'Close']] = (500.0, 900.0, 1.0, 2.0)
        _, after = self._confirm(timeframe, end, perturbed)
        assert self._decision(after) == self._decision(baseline)

    @pytest.mark.parametrize('timeframe', TIMEFRAMES)
    def test_missing_observation_inside_bar_stays_unconfirmed(self, timeframe):
        start, end = self._b_window(timeframe)
        source = self._source(timeframe)
        drop = (pd.Timestamp('2024-11-26') if timeframe == '1w'
                else (start + pd.Timedelta(minutes=2)).tz_localize(None))
        _, result = self._confirm(timeframe, end, source.drop(index=drop))
        assert result['state'] == 'unconfirmed' and result['confirmed'] is False
        assert 'incomplete_coverage' in result['reasons']
        assert 'missing_observations' in result['reasons']

    @pytest.mark.parametrize('timeframe', TIMEFRAMES)
    def test_invalid_observation_inside_bar_stays_unconfirmed(self, timeframe):
        start, end = self._b_window(timeframe)
        source = self._source(timeframe)
        bad = (pd.Timestamp('2024-11-26') if timeframe == '1w'
               else (start + pd.Timedelta(minutes=1)).tz_localize(None))
        source.loc[bad, ['High', 'Low']] = (90.0, 110.0)
        _, result = self._confirm(timeframe, end, source)
        assert result['state'] == 'unconfirmed'
        assert 'invalid_ohlc' in result['reasons']

    @pytest.mark.parametrize('timeframe', TIMEFRAMES)
    def test_missing_latest_period_is_not_replaced_by_an_older_bar(self, timeframe):
        start, end = self._b_window(timeframe)
        source = self._source(timeframe)
        if timeframe == '1w':
            source = source.drop(index=source.loc['2024-11-25':'2024-11-29'].index)
        else:
            stamps = source.index.tz_localize('America/New_York')
            source = source.loc[~((stamps >= start) & (stamps < end))]
        _, result = self._confirm(timeframe, end, source)
        assert result['state'] == 'unconfirmed'
        assert 'latest_closed_period_missing' in result['reasons']

    def test_weekly_confirms_at_actual_shortened_final_session_close(self):
        # Not at Friday 16:00 or midnight: the 13:00 early close completes it.
        _, before = self._confirm('1w', pd.Timestamp('2024-11-29 12:59', tz='America/New_York'))
        _, at = self._confirm('1w', pd.Timestamp('2024-11-29 13:00', tz='America/New_York'))
        assert before['state'] != 'confirmed' or before['period_start'] != at['period_start']
        assert at['state'] == 'confirmed'

    @pytest.mark.parametrize('clock', ['2024-12-02 16:00', '2024-12-02 17:00', '2024-12-03 10:00',
                                       '2024-12-05 16:30'])
    def test_weekly_stays_confirmed_until_the_current_week_closes(self, clock):
        # Monday to Thursday of the next week: the developing week ends at its
        # Friday close, so the week that closed on 2024-11-29 stays the
        # confirmed one (Codex r4476732518).
        stamp = pd.Timestamp(clock, tz='America/New_York')
        _, at_close = self._confirm('1w', pd.Timestamp(self.WEEKLY_CLOSE, tz='America/New_York'))
        _, result = self._confirm('1w', stamp)
        assert self._decision(result) == self._decision(at_close)
        assert pd.Timestamp(result['developing']['period_end']) == pd.Timestamp(
            '2024-12-06 16:00', tz='America/New_York')

    def test_date_only_replay_excluding_the_day_confirms_before_its_open(self):
        # inclusive_today=False drops the replay day's RTH bars, so a weekly
        # setup that closes later that day cannot confirm (Codex r4480286394).
        from lib.strat import compute_strat_status
        source = self._source('1w')
        before_open = pd.Timestamp('2024-11-29 09:29:59.999999', tz='America/New_York')
        _, expected = self._confirm('1w', before_open, source)
        out = compute_strat_status('TEST', df=source, as_of='2024-11-29', inclusive_today=False)
        result = out['confirmed_setups']['timeframes']['1w']
        assert self._decision(result) == self._decision(expected)
        assert pd.Timestamp(result['period_end']) < pd.Timestamp(self.WEEKLY_CLOSE, tz='America/New_York')
        moved = source.copy()
        moved.loc['2024-11-29', ['Low', 'High', 'Open', 'Close']] = (90.0, 110.0, 100.0, 100.0)
        again = compute_strat_status('TEST', df=moved, as_of='2024-11-29', inclusive_today=False)
        assert again['confirmed_setups'] == out['confirmed_setups']
        included = compute_strat_status('TEST', df=source, as_of='2024-11-29')
        assert pd.Timestamp(included['confirmed_setups']['timeframes']['1w']['period_end']) == \
            pd.Timestamp(self.WEEKLY_CLOSE, tz='America/New_York')

    def test_shorter_final_4h_bucket_stays_unconfirmed_pending_owner(self):
        source = self._source('4h')
        clipped = (source.index >= '2024-01-03 13:30') & (source.index < '2024-01-03 16:00')
        source.loc[clipped, ['Low', 'High', 'Open', 'Close']] = (99.6, 100.4, 100.0, 100.0)
        _, result = self._confirm('4h', pd.Timestamp('2024-01-03 16:00', tz='America/New_York'), source)
        assert result['period_start'] == '2024-01-03T13:30:00-05:00'
        assert result['state'] == 'unconfirmed'
        assert 'shorter_session_bucket_unapproved' in result['reasons']

    def test_missing_source_is_explicit_per_timeframe(self):
        from lib.strat import compute_confirmed_setups
        out = compute_confirmed_setups(observation_ts='2024-01-03 12:00-05:00')
        assert out['confirmed'] == []
        for timeframe, result in out['timeframes'].items():
            assert result['state'] == 'unavailable'
            assert result['reasons'] == ['source_not_supplied']

    def test_explicit_clock_is_required(self):
        from lib.strat import compute_confirmed_setups
        with pytest.raises(ValueError, match='observation clock'):
            compute_confirmed_setups(observation_ts=None, intraday_df=self._source('5m'))

    def test_unvalidated_source_contract_cannot_confirm(self):
        source = self._source('5m')
        source.attrs = {'source_resolution': '1min'}
        _, end = self._b_window('5m')
        _, result = self._confirm('5m', end, source)
        assert result['state'] == 'unavailable' and result['confirmed'] is False
        assert 'unknown_session_policy' in result['reasons']

    @pytest.mark.parametrize('timeframe', ['5m', '1w'])
    def test_status_consumer_uses_the_same_confirmation_boundary(self, timeframe):
        from lib.strat import compute_strat_status
        start, end = self._b_window(timeframe)
        daily = self._source('1w')
        intraday = self._source(timeframe) if timeframe != '1w' else None
        before = compute_strat_status('TEST', df=daily, intraday_df=intraday,
                                      as_of=end - pd.Timedelta(minutes=1))
        at = compute_strat_status('TEST', df=daily, intraday_df=intraday, as_of=end)
        before_tf = before['confirmed_setups']['timeframes'][timeframe]
        at_tf = at['confirmed_setups']['timeframes'][timeframe]
        assert at_tf['state'] == 'confirmed'
        assert at_tf['period_end'] == end.isoformat()
        assert before_tf['period_end'] != end.isoformat()
        assert before_tf['developing']['period_end'] == end.isoformat()
        assert before['confirmed_setups']['observation_ts'] == before['observation_ts']


class TestStratStatusReviewFollowups:
    """Codex P2 findings on #1714 at 3f1bb61b, fixed after its review cap."""

    def test_date_only_replay_excluding_the_day_aggregates_at_the_premarket_cutoff(self):
        # r4481033962: coverage and FTFC must use the same cutoff as confirmation.
        from lib.strat import compute_strat_status
        from scripts.research.strat_foundation_diagnostic import load_fixture
        df, _ = load_fixture()
        out = compute_strat_status('IWM', df=df, as_of='2026-04-08',
                                   timeframes=['1d', '1w', '1mo'], inclusive_today=False)
        assert out['ftfc_labels'] == {'1d': '3', '1w': '2U', '1mo': '1'}
        assert out['ftfc_score'] == 0.25

    def test_legacy_last_alias_is_accepted(self):
        # r4481033971: a frame naming its close `Last` returns a status, not a ValueError.
        from lib.strat import compute_strat_status
        from scripts.research.strat_foundation_diagnostic import load_fixture
        df, _ = load_fixture()
        cut = df.loc[df.index < pd.Timestamp('2026-04-08')].tail(40)
        expected = compute_strat_status('IWM', df=cut, as_of='2026-04-07', timeframes=['1d'])
        out = compute_strat_status('IWM', df=cut.rename(columns={'Close': 'Last'}),
                                   as_of='2026-04-07', timeframes=['1d'])
        assert out['ftfc_labels'] == expected['ftfc_labels']
        assert out['bar_validity'] == expected['bar_validity']


# ── FTFC proper vs TF bias (FEAT-STRAT-001, 2026-11-05 spec) ─────────────

_NOV5_FIXTURE = 'tests/fixtures/strat_brief_2026-11-05_daily.json'
_NOV5_CLOCK = pd.Timestamp('2026-11-05 08:30', tz='America/New_York')


def nov5_daily(ticker):
    """Captured unadjusted daily bars, 2026-07-01..2026-11-04, as the brief loads them."""
    import json
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / _NOV5_FIXTURE
    rows = json.loads(path.read_text())['tickers'][ticker]
    frame = pd.DataFrame(rows)
    frame.index = pd.to_datetime(frame.pop('date'))
    frame.index.name = None
    return frame.sort_index().rename(columns=str.title)


class TestObservedPriceContinuity:
    """compute_strat_status publishes price-open-v1 FTFC from a supplied price."""

    PREMARKET = ['1q', '1mo', '1w']

    def _status(self, ticker='QQQ', df=None, **overrides):
        from lib.strat import compute_strat_status
        df = nov5_daily(ticker) if df is None else df
        kwargs = dict(observed_price=float(df['Close'].iloc[-1]),
                      observed_price_session=df.index[-1].date(),
                      price_provenance='latest_completed_close',
                      continuity_timeframes=self.PREMARKET)
        kwargs.update(overrides)
        return compute_strat_status(ticker, df=df, timeframes=['1d', '1w', '1mo'],
                                    as_of=_NOV5_CLOCK, inclusive_today=False, **kwargs)

    def test_nov5_qqq_is_bearish_below_quarter_month_and_week_opens(self):
        from lib.strat import timeframe_continuity_record
        out = self._status('QQQ')
        cont = out['timeframe_continuity']
        assert cont['version'] == 'price-open-v1'
        assert cont['available'] is True and cont['direction'] == 'bearish'
        assert cont['observed_price'] == 691.95
        assert cont['price_provenance'] == 'latest_completed_close'
        assert cont['observed_price_session'] == '2026-11-04'
        assert {tf: (f['relation'], f['open']) for tf, f in cont['frames'].items()} == {
            '1q': ('below', 742.51), '1mo': ('below', 695.315), '1w': ('below', 695.315)}
        state, frames = timeframe_continuity_record(cont)
        assert state == 'bearish'
        assert {tf: f['relation'] for tf, f in frames.items()} == {'1q': 'red', '1mo': 'red', '1w': 'red'}
        assert frames['1w'] == {'relation': 'red', 'open': 695.315, 'observed_price': 691.95,
                                'price_provenance': 'latest_completed_close',
                                'price_session': '2026-11-04', 'rule_version': 'price-open-v1',
                                'period_start': '2026-11-02T09:30:00-05:00',
                                'observation_ts': '2026-11-05T08:30:00-05:00',
                                'reasons': []}

    def test_tf_bias_is_unchanged_by_the_continuity_frames(self):
        """The weighted vote still reads +0.5 bullish for QQQ, from D/W/M only."""
        from lib.strat import compute_strat_status
        df = nov5_daily('QQQ')
        plain = compute_strat_status('QQQ', df=df, timeframes=['1d', '1w', '1mo'],
                                     as_of=_NOV5_CLOCK, inclusive_today=False)
        out = self._status('QQQ', df=df)
        assert out['ftfc_score'] == pytest.approx(0.5) and out['ftfc_direction'] == 'bullish'
        assert out['ftfc_labels'] == {'1d': '2U', '1w': '2D', '1mo': '2D'}
        assert '1q' not in out['weighted_candle_alignment']['frames']
        assert set(out['coverage']) == {'1d', '1w', '1mo'}
        for key in plain:
            if key != 'timeframe_continuity':
                assert out[key] == plain[key], key

    def test_without_new_arguments_continuity_keeps_its_unavailable_shape(self):
        from lib.strat import compute_strat_status
        out = compute_strat_status('QQQ', df=nov5_daily('QQQ'), timeframes=['1d', '1w', '1mo'],
                                   as_of=_NOV5_CLOCK, inclusive_today=False)
        cont = out['timeframe_continuity']
        assert cont['required_timeframes'] == ['1d', '1w', '1mo']
        assert cont['available'] is False and cont['direction'] == 'unavailable'
        assert cont['reasons'][0] == 'invalid_observed_price'
        assert cont['price_provenance'] == 'unknown' and cont['observed_price'] is None
        assert 'observed_price_session' not in cont
        assert all('invalid_observed_price' in f['reasons'] for f in cont['frames'].values())

    def test_premarket_daily_frame_has_no_open_and_stays_unavailable(self):
        out = self._status('QQQ', continuity_timeframes=['1q', '1mo', '1w', '1d'])
        cont = out['timeframe_continuity']
        assert cont['available'] is False and cont['direction'] == 'unavailable'
        assert 'unavailable_required_frames' in cont['reasons']
        assert cont['frames']['1d']['relation'] == 'unavailable'
        assert 'missing_period_open' in cont['frames']['1d']['reasons']
        assert all(cont['frames'][tf]['available'] for tf in self.PREMARKET)

    def test_a_price_from_after_the_clock_is_refused(self):
        out = self._status('QQQ', observed_price_session=pd.Timestamp('2026-11-05').date())
        cont = out['timeframe_continuity']
        assert cont['available'] is False and cont['observed_price'] is None
        assert cont['reasons'][0] == 'observed_price_after_clock'
        assert 'invalid_observed_price' not in cont['reasons']
        assert all(f['reasons'] == ['observed_price_after_clock'] for f in cont['frames'].values())

    def test_a_price_session_that_is_not_a_trading_day_is_refused(self):
        out = self._status('QQQ', observed_price_session=pd.Timestamp('2026-11-01').date())
        assert out['timeframe_continuity']['reasons'][0] == 'observed_price_session_not_trading_day'

    def test_a_missing_quarter_open_is_unavailable_never_a_later_bar(self):
        df = nov5_daily('QQQ')
        df = df.drop(pd.Timestamp('2026-10-01'))
        cont = self._status('QQQ', df=df)['timeframe_continuity']
        assert cont['direction'] == 'unavailable'
        assert cont['frames']['1q']['open'] is None
        assert 'missing_period_open' in cont['frames']['1q']['reasons']
        assert cont['frames']['1mo']['relation'] == 'below'

    def test_invalid_price_is_unavailable(self):
        cont = self._status('QQQ', observed_price=float('nan'))['timeframe_continuity']
        assert cont['direction'] == 'unavailable' and cont['reasons'][0] == 'invalid_observed_price'

    def test_price_at_an_open_is_at_open_and_mixed(self):
        from lib.strat import timeframe_continuity_record
        cont = self._status('QQQ', observed_price=695.315)['timeframe_continuity']
        assert cont['available'] is True and cont['direction'] == 'mixed'
        assert cont['frames']['1w']['relation'] == 'at_open'
        assert cont['frames']['1q']['relation'] == 'below'
        state, frames = timeframe_continuity_record(cont)
        assert (state, frames['1w']['relation'], frames['1q']['relation']) == ('mixed', 'at_open', 'red')

    def test_iwm_and_spy_are_bullish_above_every_open(self):
        for ticker, price in (('IWM', 284.02), ('SPY', 766.81)):
            cont = self._status(ticker)['timeframe_continuity']
            assert cont['direction'] == 'bullish', ticker
            assert cont['observed_price'] == price
            assert {f['relation'] for f in cont['frames'].values()} == {'above'}

    def test_record_of_no_result_is_none(self):
        from lib.strat import timeframe_continuity_record
        assert timeframe_continuity_record(None) == (None, None)


class TestFirstSessionOfPeriod:
    """2026-11-02 08:30 ET, the first session of November and of the week.

    The week and month open at 09:30 that day, so at 08:30 they have no open:
    the state is unavailable (no partial claim of agreement) while the
    quarter, opened 2026-10-01, is still judged and kept.
    """

    CLOCK = pd.Timestamp('2026-11-02 08:30', tz='America/New_York')

    def _status(self, ticker, frames=('1q', '1mo', '1w')):
        from lib.strat import compute_strat_status
        df = nov5_daily(ticker)
        df = df[df.index <= '2026-10-30']
        return compute_strat_status(
            ticker, df=df, timeframes=['1d', '1w', '1mo'], as_of=self.CLOCK, inclusive_today=False,
            observed_price=float(df['Close'].iloc[-1]), observed_price_session=df.index[-1].date(),
            price_provenance='latest_completed_close', continuity_timeframes=list(frames))

    def test_month_and_week_open_after_the_clock_and_the_quarter_is_kept(self):
        from lib.strat import timeframe_continuity_record
        cont = self._status('QQQ')['timeframe_continuity']
        assert cont['available'] is False and cont['direction'] == 'unavailable'
        assert cont['full_continuity'] is False
        state, frames = timeframe_continuity_record(cont)
        assert state == 'unavailable'
        assert frames['1q']['relation'] == 'red' and frames['1q']['open'] == 742.51
        assert frames['1q']['observed_price'] == float(nov5_daily('QQQ').loc['2026-10-30', 'Close'])
        for tf in ('1mo', '1w'):
            assert frames[tf]['relation'] == 'unavailable' and frames[tf]['open'] is None
            assert frames[tf]['reasons'][0] == 'period_opens_after_clock'
            assert 'missing_period_open' in frames[tf]['reasons']
            assert frames[tf]['period_start'] == '2026-11-02T09:30:00-05:00'
            assert frames[tf]['observation_ts'] == '2026-11-02T08:30:00-05:00'

    def test_a_frame_missing_for_another_reason_is_not_called_not_open(self):
        from lib.strat import timeframe_continuity_record
        df = nov5_daily('QQQ')
        df = df[(df.index <= '2026-10-30') & (df.index != '2026-10-01')]
        from lib.strat import compute_strat_status
        cont = compute_strat_status(
            'QQQ', df=df, timeframes=['1d', '1w', '1mo'], as_of=self.CLOCK, inclusive_today=False,
            observed_price=float(df['Close'].iloc[-1]), observed_price_session=df.index[-1].date(),
            price_provenance='latest_completed_close',
            continuity_timeframes=['1q', '1mo', '1w'])['timeframe_continuity']
        _, frames = timeframe_continuity_record(cont)
        assert frames['1q']['relation'] == 'unavailable'
        assert 'period_opens_after_clock' not in frames['1q']['reasons']

    def test_without_an_observed_price_the_frames_carry_no_new_reason(self):
        from lib.strat import compute_strat_status
        df = nov5_daily('QQQ')
        df = df[df.index <= '2026-10-30']
        cont = compute_strat_status('QQQ', df=df, timeframes=['1d', '1w', '1mo'], as_of=self.CLOCK,
                                    inclusive_today=False)['timeframe_continuity']
        assert all('period_opens_after_clock' not in f['reasons'] for f in cont['frames'].values())
        assert all('observation_ts' not in f for f in cont['frames'].values())


class TestGatesStayOnTfBias:
    """done_when 7: no gate reads price-open continuity; the weighted vote drives them."""

    GATE_SOURCES = (
        'lib/strategies/brief_bias.py', 'gcp/signal_monitor.py',
        'lib/agents/trade_planner.py', 'lib/agents/orchestrator.py',
        'lib/agents/ranker/signals.py', 'lib/backtest.py', 'lib/exec_backtest/ftfc.py',
    )

    def test_gate_modules_never_name_the_continuity_fields(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        for path in self.GATE_SOURCES:
            source = (root / path).read_text()
            for name in ('timeframe_continuity', 'tf_continuity'):
                assert name not in source, f'{path} reads {name}'

    def test_brief_signal_gate_and_strat_bonus_read_only_the_weighted_vote(self):
        import inspect
        from gcp.premarket_brief import _resolve_signal_status
        source = inspect.getsource(_resolve_signal_status)
        assert 'continuity' not in source
        assert list(inspect.signature(_resolve_signal_status).parameters) == [
            'call_score', 'put_score', 'ftfc_direction', 'signal_threshold', 'building_threshold']
        assert list(inspect.signature(StratClassifier.get_strat_bonus).parameters) == [
            'self', 'signal_direction', 'combo', 'ftfc_score', 'ftfc_threshold', 'orb_trend']
