"""Tests for lib/strat_levels.py — Strat levels engine."""

import pandas as pd
import numpy as np
import pytest

from lib.strat_levels import (
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
    StratLevel,
    LevelMap,
    MIN_ROOM_PCT,
)


def _daily_df(n=60):
    """Build a sample daily OHLCV DataFrame with ~n trading days."""
    np.random.seed(42)
    dates = pd.bdate_range('2025-01-02', periods=n)
    close = 200 * np.exp(np.cumsum(np.random.normal(0.0003, 0.01, n)))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    open_ = np.roll(close, 1)
    open_[0] = 200.0
    return pd.DataFrame({
        'Date': dates,
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': np.random.randint(1_000_000, 5_000_000, n),
    })


# ─── classify_level_strat ─────────────────────────────────────────────────


class TestClassifyLevelStrat:
    def test_inside(self):
        assert classify_level_strat(99, 96, 98, 97, 100, 95) == '1'

    def test_2u_bullish(self):
        assert classify_level_strat(101, 96, 100, 97, 100, 95) == '2U'

    def test_2d_bearish(self):
        assert classify_level_strat(99, 94, 95, 97, 100, 95) == '2D'

    def test_failed_2u(self):
        """Broke prev high but closed bearish (C < O)."""
        assert classify_level_strat(101, 96, 97, 100, 100, 95) == 'Failed_2U'

    def test_failed_2d(self):
        """Broke prev low but closed bullish (C > O)."""
        assert classify_level_strat(99, 94, 98, 96, 100, 95) == 'Failed_2D'

    def test_outside(self):
        assert classify_level_strat(101, 94, 98, 97, 100, 95) == '3'

    def test_equal_is_inside(self):
        """H==pH AND L==pL → inside."""
        assert classify_level_strat(100, 95, 98, 97, 100, 95) == '1'


# ─── compute_previous_levels ──────────────────────────────────────────────


class TestComputePreviousLevels:
    def test_returns_daily_levels(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        assert 'PDH' in levels
        assert 'PDL' in levels
        assert levels['PDH'].timeframe == 'day'
        assert levels['PDL'].level_type == 'low'

    def test_returns_weekly_levels(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        assert 'PWH' in levels
        assert 'PWL' in levels
        assert levels['PWH'].timeframe == 'week'

    def test_returns_monthly_levels(self):
        df = _daily_df(60)
        levels = compute_previous_levels(df)
        assert 'PMH' in levels
        assert 'PML' in levels

    def test_returns_quarter_levels(self):
        df = _daily_df(200)
        levels = compute_previous_levels(df)
        assert 'PQH' in levels
        assert 'PQL' in levels
        assert levels['PQH'].timeframe == 'quarter'

    def test_pdh_price_matches_prev_day_high(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        expected = float(df['High'].iloc[-2])
        assert levels['PDH'].price == expected

    def test_levels_classified(self):
        df = _daily_df(30)
        levels = compute_previous_levels(df)
        assert levels['PDH'].strat_class in ('1', '2U', '2D', '3', 'Failed_2U', 'Failed_2D')

    def test_empty_df(self):
        assert compute_previous_levels(pd.DataFrame()) == {}


# ─── compute_current_levels ───────────────────────────────────────────────


class TestComputeCurrentLevels:
    def test_returns_cdo(self):
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        levels = compute_current_levels(df, price)
        assert 'CDO' in levels
        assert levels['CDO'].is_current is True

    def test_cdo_price_is_today_open(self):
        df = _daily_df(10)
        price = float(df['Close'].iloc[-1])
        levels = compute_current_levels(df, price)
        assert levels['CDO'].price == float(df['Open'].iloc[-1])

    def test_cdo_flips_to_2u_on_high_price(self):
        df = _daily_df(10)
        # Price well above prev day high → should be 2U
        prev_high = float(df['High'].iloc[-2])
        price = prev_high + 5.0
        levels = compute_current_levels(df, price)
        # CDO should be 2U or Failed_2U depending on open
        assert levels['CDO'].strat_class in ('2U', 'Failed_2U')

    def test_cdo_inside_when_price_in_range(self):
        df = _daily_df(10)
        prev_high = float(df['High'].iloc[-2])
        prev_low = float(df['Low'].iloc[-2])
        mid = (prev_high + prev_low) / 2
        # Override today's OHLC to be well within prev range
        df.iloc[-1, df.columns.get_loc('High')] = prev_high - 0.5
        df.iloc[-1, df.columns.get_loc('Low')] = prev_low + 0.5
        df.iloc[-1, df.columns.get_loc('Open')] = mid
        levels = compute_current_levels(df, mid)
        assert levels['CDO'].strat_class == '1'


# ─── compute_gap_levels ──────────────────────────────────────────────────


class TestComputeGapLevels:
    def test_detects_gap_up(self):
        df = pd.DataFrame({
            'Date': pd.bdate_range('2025-01-02', periods=3),
            'Open': [100, 105, 108],
            'High': [102, 107, 110],
            'Low': [99, 104, 107],     # day 2 low (104) > day 1 high (102) → gap
            'Close': [101, 106, 109],
        })
        gaps = compute_gap_levels(df, lookback=5)
        assert len(gaps) >= 2  # gap_high and gap_low
        gap_types = {g.level_type for g in gaps}
        assert 'gap_high' in gap_types
        assert 'gap_low' in gap_types

    def test_filled_gap_excluded(self):
        df = pd.DataFrame({
            'Date': pd.bdate_range('2025-01-02', periods=4),
            'Open': [100, 105, 100, 98],
            'High': [102, 107, 103, 101],
            'Low': [99, 104, 99, 97],    # day 2 low (104) > day 1 high (102) → gap
            'Close': [101, 106, 100, 99], # but day 3 low (99) fills the gap
        })
        gaps = compute_gap_levels(df, lookback=5)
        # Gap should be filtered out because day 3 filled it
        gap_up = [g for g in gaps if g.strat_class == 'gap_up']
        assert len(gap_up) == 0

    def test_empty_df(self):
        assert compute_gap_levels(pd.DataFrame(), lookback=5) == []


# ─── detect_level_clusters (spatial PMG) ──────────────────────────────────


class TestDetectLevelClusters:
    def test_finds_cluster(self):
        levels = [
            StratLevel('PDL', 262.14, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 262.30, 'week', 'low', '2D', False, ''),
            StratLevel('PMH', 270.00, 'month', 'high', '2U', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(zones) == 1
        assert 'PDL' in zones[0]['level_names']
        assert 'PWL' in zones[0]['level_names']

    def test_no_cluster_when_far_apart(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            StratLevel('PWH', 270.00, 'week', 'high', '2U', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(zones) == 0

    def test_strength_scoring(self):
        levels = [
            StratLevel('PDL', 262.14, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 262.30, 'week', 'low', '2D', False, ''),
            StratLevel('GAP_L', 262.10, 'day', 'gap_low', 'gap_up', False, ''),
        ]
        zones = detect_level_clusters(levels, tolerance_pct=0.15)
        assert len(zones) == 1
        # count=3, unique TFs=2 (day, week) → 3 + 0.5 = 3.5
        assert zones[0]['strength'] == 3.5

    def test_empty(self):
        assert detect_level_clusters([], tolerance_pct=0.15) == []


# ─── detect_pmg_temporal ──────────────────────────────────────────────────


class TestDetectPMGTemporal:
    def test_detects_higher_highs(self):
        df = pd.DataFrame({
            'High': [100, 101, 102, 103, 104],
            'Low': [95, 96, 97, 98, 99],
        })
        results = detect_pmg_temporal(df, n_consecutive=3)
        hh = [r for r in results if r['type'] == 'higher_highs']
        assert len(hh) >= 1
        assert hh[0]['count'] >= 3

    def test_detects_lower_lows(self):
        df = pd.DataFrame({
            'High': [104, 103, 102, 101, 100],
            'Low': [99, 98, 97, 96, 95],
        })
        results = detect_pmg_temporal(df, n_consecutive=3)
        ll = [r for r in results if r['type'] == 'lower_lows']
        assert len(ll) >= 1

    def test_no_streak(self):
        df = pd.DataFrame({
            'High': [100, 101, 99, 102, 98],
            'Low': [95, 96, 94, 97, 93],
        })
        results = detect_pmg_temporal(df, n_consecutive=3)
        assert len(results) == 0


# ─── compute_room_to_run ─────────────────────────────────────────────────


class TestRoomToRun:
    def test_call_direction(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            StratLevel('PWH', 268.00, 'week', 'high', '2U', False, ''),
        ]
        result = compute_room_to_run(263.00, levels, 'CALL')
        assert result['next_level'].name == 'PDH'
        assert result['distance_pct'] > 0
        assert result['has_room'] is True

    def test_put_direction(self):
        levels = [
            StratLevel('PDL', 260.00, 'day', 'low', '2D', False, ''),
            StratLevel('PWL', 257.00, 'week', 'low', '2D', False, ''),
        ]
        result = compute_room_to_run(263.00, levels, 'PUT')
        assert result['next_level'].name == 'PDL'
        assert result['has_room'] is True

    def test_insufficient_room(self):
        levels = [
            StratLevel('PDH', 263.05, 'day', 'high', '2U', False, ''),
        ]
        result = compute_room_to_run(263.00, levels, 'CALL')
        # 0.05/263 = 0.019% < MIN_ROOM_PCT
        assert result['has_room'] is False

    def test_no_levels_in_direction(self):
        levels = [
            StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
        ]
        result = compute_room_to_run(266.00, levels, 'CALL')
        assert result['next_level'] is None


# ─── compute_risk_reward ─────────────────────────────────────────────────


class TestRiskReward:
    def test_basic(self):
        assert compute_risk_reward(100, 99, 102) == 2.0

    def test_zero_risk(self):
        assert compute_risk_reward(100, 100, 105) == 0.0

    def test_put_direction(self):
        assert compute_risk_reward(100, 101, 97) == 3.0


# ─── identify_triggers ───────────────────────────────────────────────────


class TestIdentifyTriggers:
    def _levels(self):
        return {
            'PDH': StratLevel('PDH', 265.00, 'day', 'high', '2U', False, ''),
            'PDL': StratLevel('PDL', 260.00, 'day', 'low', '2D', False, ''),
            'PWH': StratLevel('PWH', 268.00, 'week', 'high', '2U', False, ''),
            'PWL': StratLevel('PWL', 257.00, 'week', 'low', '2D', False, ''),
        }

    def test_calls_trigger(self):
        triggers = identify_triggers(263.00, self._levels())
        assert triggers['calls'] is not None
        assert triggers['calls']['trigger_name'] == 'PDH'
        assert triggers['calls']['trigger_level'] == 265.00

    def test_puts_trigger(self):
        triggers = identify_triggers(263.00, self._levels())
        assert triggers['puts'] is not None
        assert triggers['puts']['trigger_name'] == 'PDL'

    def test_reasoning_includes_combo(self):
        triggers = identify_triggers(
            263.00, self._levels(),
            daily_strat_class='2U', combo='212_bull_reversal',
        )
        assert '212_bull_reversal' in triggers['calls']['reasoning']
        assert 'Daily 2U' in triggers['calls']['reasoning']

    def test_reasoning_empty_when_no_context(self):
        triggers = identify_triggers(263.00, self._levels())
        assert triggers['calls']['reasoning'] == ''


# ─── build_level_map ──────────────────────────────────────────────────────


class TestBuildLevelMap:
    def test_returns_level_map(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price, '2U', '212_bull_reversal')
        assert isinstance(lm, LevelMap)
        assert lm.ticker == 'IWM'
        assert len(lm.levels) > 0
        assert lm.current_price == price

    def test_has_triggers(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('SPY', df, price)
        # Should have at least calls or puts
        assert lm.calls_trigger is not None or lm.puts_trigger is not None


# ─── format_levels_for_brief ──────────────────────────────────────────────


class TestFormatLevelsForBrief:
    def test_contains_calls_puts(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price, '2U', '212_bull_reversal')
        text = format_levels_for_brief(lm, 'bullish', '212_bull_reversal', '2U')
        assert 'CALLS above' in text or 'PUTS below' in text

    def test_bias_denied_for_puts_when_bullish(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')
        if 'PUTS below' in text:
            assert 'only if bias denied' in text

    def test_bearish_bias_denied_for_calls(self):
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bearish')
        if 'CALLS above' in text:
            assert 'only if bias denied' in text

    # ── Regime-aware playbook output (PR α) ───────────────────────────

    def test_orb_only_regime_suppresses_calls_and_puts(self):
        """orb_only: pre-market cleared every level; the playbook
        replaces CALLS/PUTS with an ORB-wait banner."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish', regime='orb_only')
        assert 'ORB-only' in text
        assert 'wait' in text.lower() or '15-min' in text
        # Suppressed: no CALLS/PUTS lines
        assert 'CALLS above' not in text
        assert 'PUTS below' not in text

    def test_extended_regime_prepends_warning_keeps_triggers(self):
        """extended: warning header + standard CALLS/PUTS still rendered."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish', regime='extended')
        assert 'Extended gap' in text
        assert 'ORB' in text
        # Still has trigger lines (extended ≠ skip the trade)
        assert 'CALLS above' in text or 'PUTS below' in text

    def test_normal_regime_matches_legacy_output(self):
        """normal regime: identical to the legacy no-regime call."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text_normal = format_levels_for_brief(lm, 'bullish', regime='normal')
        text_legacy = format_levels_for_brief(lm, 'bullish')
        assert text_normal == text_legacy

    def test_default_regime_is_normal(self):
        """No regime kwarg → backwards-compat with pre-α callers."""
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        text = format_levels_for_brief(lm, 'bullish')
        assert 'Extended gap' not in text
        assert 'ORB-only' not in text


# ─── levels_to_named_dict (PR α adapter) ──────────────────────────────────


class TestLevelsToNamedDict:
    def test_extracts_named_levels(self):
        from lib.strat_levels import levels_to_named_dict
        df = _daily_df(60)
        price = float(df['Close'].iloc[-1])
        lm = build_level_map('IWM', df, price)
        d = levels_to_named_dict(lm)
        # PDH/PDL should always be present after 60 days of data
        assert 'PDH' in d
        assert 'PDL' in d
        # All values should be floats
        assert all(isinstance(v, float) for v in d.values())

    def test_empty_level_map(self):
        from lib.strat_levels import LevelMap, levels_to_named_dict
        empty = LevelMap(
            ticker='X', as_of='2026-01-01', current_price=100.0,
            levels=[], pmg_zones=[],
        )
        assert levels_to_named_dict(empty) == {}
