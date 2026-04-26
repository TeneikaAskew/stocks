"""Tests for lib/strat_levels.py — the levels engine."""

import pandas as pd
import numpy as np
import pytest

from lib.strat_levels import (
    StratLevel, LevelMap,
    classify_level_strat,
    compute_previous_levels,
    compute_current_levels,
    compute_gap_levels,
    detect_level_clusters,
    detect_pmg_temporal,
    compute_room_to_run,
    compute_risk_reward,
    identify_triggers,
    build_level_map,
    format_levels_for_brief,
)


# ── classify_level_strat ──────────────────────────────────────────────────


class TestClassifyLevelStrat:
    def test_inside(self):
        assert classify_level_strat(99, 96, 97, 96.5, 100, 95) == '1'

    def test_2u_clean(self):
        assert classify_level_strat(101, 96, 100, 99, 100, 95) == '2U'

    def test_2u_failed(self):
        # 2U structure (H=101 > 100) but C<O → f2u
        assert classify_level_strat(101, 96, 99, 100, 100, 95) == 'f2u'

    def test_2d_clean(self):
        assert classify_level_strat(99, 94, 95, 96, 100, 95) == '2D'

    def test_2d_failed(self):
        # 2D structure (L=94<95) but C>O → f2d
        assert classify_level_strat(99, 94, 96, 95, 100, 95) == 'f2d'

    def test_outside(self):
        assert classify_level_strat(101, 94, 97, 96, 100, 95) == '3'

    def test_inclusive_inside(self):
        """Equal H and equal L are still inside (1)."""
        assert classify_level_strat(100, 95, 97, 96, 100, 95) == '1'


# ── compute_previous_levels ───────────────────────────────────────────────


class TestComputePreviousLevels:
    def _frame(self):
        return pd.DataFrame([{
            'Open': 100, 'High': 101, 'Low': 99, 'Close': 100.5,
            'Prev_Day_High': 100, 'Prev_Day_Low': 95,
            'Prev_Day_Open': 96, 'Prev_Day_Close': 99,
            'Prev_Week_High': 105, 'Prev_Week_Low': 92,
            'Prev_Week_Open': 95, 'Prev_Week_Close': 102,
            'Prev_Month_High': 110, 'Prev_Month_Low': 85,
            'Prev_Month_Open': 88, 'Prev_Month_Close': 105,
            'Prev_Quarter_High': 115, 'Prev_Quarter_Low': 80,
            'Prev_Quarter_Open': 82, 'Prev_Quarter_Close': 108,
            'Prev_Year_High': 120, 'Prev_Year_Low': 60,
            'Prev_Year_Open': 65, 'Prev_Year_Close': 110,
        }])

    def test_emits_pdh_pdl(self):
        levels = compute_previous_levels(self._frame())
        names = {l.name for l in levels}
        assert {'PDH', 'PDL', 'PWH', 'PMH', 'PQH', 'PYH'}.issubset(names)

    def test_pdh_price_matches(self):
        levels = compute_previous_levels(self._frame())
        pdh = next(l for l in levels if l.name == 'PDH')
        assert pdh.price == 100.0

    def test_skips_missing_columns(self):
        df = pd.DataFrame([{'Open': 100, 'High': 101, 'Low': 99, 'Close': 100}])
        levels = compute_previous_levels(df)
        assert levels == []


# ── compute_current_levels ────────────────────────────────────────────────


class TestComputeCurrentLevels:
    def _frame(self, todays_open=100):
        return pd.DataFrame([{
            'Open': todays_open, 'High': todays_open + 1,
            'Low': todays_open - 1, 'Close': todays_open + 0.5,
            'Prev_Day_High': 100, 'Prev_Day_Low': 95,
            'Prev_Week_High': 105, 'Prev_Week_Low': 92,
        }])

    def test_emits_current_day_open(self):
        levels = compute_current_levels(self._frame(todays_open=98), current_price=98.5)
        cdo = next((l for l in levels if l.name == 'CDO'), None)
        assert cdo is not None
        assert cdo.price == 98.0
        assert cdo.is_current is True

    def test_classifies_2u_when_price_above_pdh(self):
        # current_price 102 > Prev_Day_High 100 → live 2U classification
        levels = compute_current_levels(self._frame(todays_open=99), current_price=102)
        cdo = next(l for l in levels if l.name == 'CDO')
        assert cdo.strat_class == '2U'

    def test_classifies_inside_when_within_range(self):
        levels = compute_current_levels(self._frame(todays_open=98), current_price=98.5)
        cdo = next(l for l in levels if l.name == 'CDO')
        # 98.5 between 95 and 100 → inside
        assert cdo.strat_class == '1'


# ── compute_gap_levels ────────────────────────────────────────────────────


class TestComputeGapLevels:
    def test_detects_unfilled_gap_up(self):
        df = pd.DataFrame({
            'Time': pd.to_datetime(['2024-03-01', '2024-03-02', '2024-03-03']),
            'Open':  [100, 105, 107],   # gap up on day 2 (105 > 102 = day 1 high)
            'High':  [102, 106, 108],
            'Low':   [99, 104, 106],     # never returns to 102
            'Close': [101, 105, 107],
        })
        gaps = compute_gap_levels(df, lookback=10)
        assert any(g.level_type == 'gap' and g.price == 102 for g in gaps)

    def test_filled_gap_excluded(self):
        df = pd.DataFrame({
            'Time': pd.to_datetime(['2024-03-01', '2024-03-02', '2024-03-03']),
            'Open':  [100, 105, 103],
            'High':  [102, 106, 104],
            'Low':   [99,  104, 101],   # day 3 low = 101 fills the 102 prev high
            'Close': [101, 105, 102],
        })
        gaps = compute_gap_levels(df, lookback=10)
        assert all(g.price != 102 for g in gaps)


# ── detect_level_clusters ─────────────────────────────────────────────────


class TestDetectLevelClusters:
    def test_clusters_close_levels(self):
        levels = [
            StratLevel('A', 100.0),
            StratLevel('B', 100.10),  # within 0.15% of A
            StratLevel('C', 105.0),
        ]
        clusters = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(clusters) == 1
        assert clusters[0]['strength'] == 2.0
        assert set(clusters[0]['names']) == {'A', 'B'}

    def test_separates_distant_levels(self):
        levels = [
            StratLevel('A', 100.0),
            StratLevel('B', 110.0),
        ]
        clusters = detect_level_clusters(levels, tolerance_pct=0.15)
        assert clusters == []


# ── detect_pmg_temporal ───────────────────────────────────────────────────


class TestDetectPmgTemporal:
    def test_three_higher_highs(self):
        df = pd.DataFrame({
            'High': [100, 101, 102, 103],
            'Low':  [98, 99, 100, 101],
        })
        result = detect_pmg_temporal(df, n_consecutive=3)
        assert result['higher_highs'] is True
        assert result['lower_lows'] is False

    def test_three_lower_lows(self):
        df = pd.DataFrame({
            'High': [105, 104, 103, 102],
            'Low':  [100, 99, 98, 97],
        })
        result = detect_pmg_temporal(df, n_consecutive=3)
        assert result['lower_lows'] is True

    def test_mixed_neither(self):
        df = pd.DataFrame({
            'High': [100, 101, 100, 101],
            'Low':  [98, 99, 98, 99],
        })
        result = detect_pmg_temporal(df, n_consecutive=3)
        assert not result['higher_highs']
        assert not result['lower_lows']


# ── compute_room_to_run / R:R ─────────────────────────────────────────────


class TestRoomAndRR:
    def test_room_to_run_long(self):
        levels = [StratLevel('A', 100), StratLevel('B', 102), StratLevel('C', 110)]
        out = compute_room_to_run(price=101, levels=levels, direction='long')
        assert out['next_level']['price'] == 102.0

    def test_room_to_run_short(self):
        levels = [StratLevel('A', 100), StratLevel('B', 102), StratLevel('C', 110)]
        out = compute_room_to_run(price=101, levels=levels, direction='short')
        assert out['next_level']['price'] == 100.0

    def test_room_to_run_no_target(self):
        out = compute_room_to_run(price=200, levels=[StratLevel('A', 100)], direction='long')
        assert out['next_level'] is None

    def test_risk_reward_basic(self):
        # entry 100, stop 99, target 102 → reward 2 / risk 1 = 2.0
        assert compute_risk_reward(100, 99, 102) == 2.0

    def test_risk_reward_zero_risk(self):
        assert compute_risk_reward(100, 100, 102) == 0.0


# ── identify_triggers (uses both combo + daily_strat_class) ───────────────


class TestIdentifyTriggers:
    def test_reasoning_uses_both_args(self):
        levels = [StratLevel('PDH', 102), StratLevel('PDL', 98)]
        triggers = identify_triggers(
            price=100,
            levels=levels,
            daily_strat_class='2U',
            combo='212_bull_reversal',
        )
        assert '2U' in triggers['reasoning']
        assert '212_bull_reversal' in triggers['reasoning']

    def test_long_entry_is_nearest_above(self):
        levels = [StratLevel('PDH', 102), StratLevel('PWH', 105), StratLevel('PDL', 98)]
        triggers = identify_triggers(price=100, levels=levels,
                                       daily_strat_class='2U', combo=None)
        assert triggers['entry_long']['price'] == 102.0
        assert triggers['t1_long']['price'] == 105.0


# ── build_level_map orchestrator ──────────────────────────────────────────


class TestBuildLevelMap:
    def test_orchestrator_emits_levels(self):
        df = pd.DataFrame([{
            'Time': pd.Timestamp('2024-04-15'),
            'Open': 100, 'High': 101, 'Low': 99, 'Close': 100.5,
            'Prev_Day_High': 100, 'Prev_Day_Low': 95,
            'Prev_Day_Open': 96, 'Prev_Day_Close': 99,
            'Prev_Week_High': 105, 'Prev_Week_Low': 92,
            'Prev_Week_Open': 93, 'Prev_Week_Close': 104,
        }])
        lm = build_level_map('IWM', df, current_price=100.5)
        names = {l.name for l in lm.levels}
        assert 'PDH' in names
        assert 'PDL' in names
        assert 'CDO' in names

    def test_above_below_helpers(self):
        df = pd.DataFrame([{
            'Time': pd.Timestamp('2024-04-15'),
            'Open': 100, 'High': 101, 'Low': 99, 'Close': 100.5,
            'Prev_Day_High': 102, 'Prev_Day_Low': 98,
            'Prev_Day_Open': 99, 'Prev_Day_Close': 101,
        }])
        lm = build_level_map('IWM', df, current_price=100)
        assert any(l.name == 'PDH' for l in lm.above(100))
        assert any(l.name == 'PDL' for l in lm.below(100))


# ── format_levels_for_brief ───────────────────────────────────────────────


class TestFormatLevelsForBrief:
    def test_renders_playbook_lines(self):
        df = pd.DataFrame([{
            'Time': pd.Timestamp('2024-04-15'),
            'Open': 215.40, 'High': 215.50, 'Low': 215.30, 'Close': 215.42,
            'Prev_Day_High': 215.85, 'Prev_Day_Low': 213.20,
            'Prev_Day_Open': 213.50, 'Prev_Day_Close': 215.00,
            'Prev_Week_High': 217.10, 'Prev_Week_Low': 212.50,
            'Prev_Week_Open': 213.00, 'Prev_Week_Close': 215.50,
            'Prev_Month_High': 218.45, 'Prev_Month_Low': 210.00,
            'Prev_Month_Open': 211.00, 'Prev_Month_Close': 217.00,
        }])
        lm = build_level_map('IWM', df, current_price=215.42)
        out = format_levels_for_brief(
            lm, bias='bullish',
            combo='212_bull_reversal', daily_strat_class='2U',
        )
        assert 'IWM 215.42' in out
        assert 'Daily 2U' in out
        assert 'Combo: 212_bull_reversal' in out
        assert 'CALLS above ' in out
        assert 'Stop: ' in out
        # T1 + T2 lines should reference PDH/PWH/PMH (resistance levels above)
        assert 'PWH' in out or 'PMH' in out or 'PDH' in out
        # Risk:reward annotation should appear at least once
        assert 'R:R' in out
