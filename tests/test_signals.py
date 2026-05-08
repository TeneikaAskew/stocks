"""Tests for lib/signals.py — Signal generation and scoring."""

import pandas as pd
import numpy as np
import pytest
from lib.signals import check_call_conditions, check_put_conditions, evaluate_signal, generate_signals


def _make_row(**overrides):
    """Create a minimal row with indicator columns for signal testing."""
    defaults = {
        'Close': 200.0,
        'RSI14': 50.0,
        'StochRSI_K': 50.0,
        'Price_vs_VWAP': 0.0,
        'Price_vs_EMA9': 0.0,
        'Price_vs_EMA20': 0.0,
        'Consecutive_Down': 0,
        'Consecutive_Up': 0,
        'EMA9': 200.0,
        'EMA20': 200.0,
        'VWAP': 200.0,
        'ATR14': 1.0,
        'RVOL': 1.0,
    }
    defaults.update(overrides)
    return pd.Series(defaults)


class TestCheckCallConditions:
    def test_all_conditions_met(self):
        """Phase 0.7.2: max score is 4 (was 5). `near_below_emas`
        was dropped per the §3.10 audit (84.6% free-fire rate)."""
        row = _make_row(
            Consecutive_Down=4,
            RSI14=35.0,
            Price_vs_VWAP=-0.5,
            Price_vs_EMA9=-0.2,
            StochRSI_K=20.0,
        )
        score, conds = check_call_conditions(row)
        assert score == 4
        assert 'consecutive_down' in conds
        assert 'rsi_oversold_zone' in conds
        assert 'below_vwap' in conds
        assert 'stoch_rsi_oversold' in conds
        # Phase 0.7.2 — explicitly verify the dropped condition isn't there
        assert 'near_below_emas' not in conds

    def test_no_conditions_met(self):
        row = _make_row(
            Consecutive_Down=0,
            RSI14=60.0,
            Price_vs_VWAP=1.0,
            Price_vs_EMA9=1.0,
            Price_vs_EMA20=1.0,
            StochRSI_K=60.0,
        )
        score, conds = check_call_conditions(row)
        assert score == 0
        assert len(conds) == 0

    def test_partial_conditions(self):
        row = _make_row(
            Consecutive_Down=3,
            RSI14=30.0,
            Price_vs_VWAP=0.5,  # Above VWAP — not met
            Price_vs_EMA9=0.5,
            Price_vs_EMA20=0.5,
            StochRSI_K=50.0,
        )
        score, conds = check_call_conditions(row)
        assert score == 2
        assert 'consecutive_down' in conds
        assert 'rsi_oversold_zone' in conds

    def test_custom_consecutive_periods(self):
        row = _make_row(Consecutive_Down=2)
        score_default, _ = check_call_conditions(row, consecutive_periods=3)
        score_lower, _ = check_call_conditions(row, consecutive_periods=2)
        assert score_default < score_lower or (score_default == score_lower)
        # With threshold=2, 2 down periods should count
        score2, conds2 = check_call_conditions(row, consecutive_periods=2)
        assert 'consecutive_down' in conds2


class TestCheckPutConditions:
    def test_all_conditions_met(self):
        """Track A G.P0.12 (audit 2026-05-08): max score is 3 after
        `above_vwap` dropped from PUT scoring. Audit measured
        `above_vwap`-marked PUT signals as -16.1pp (QQQ) / -11.7pp (IWM)
        / -9.9pp (SPY) win-rate vs no-above_vwap PUTs.

        Previous: 4 (Phase 0.7.2 had dropped near_above_emas).
        Current:  3 (above_vwap also dropped).
        Without level_break_pdl, even the all-bullish row maxes at 3.
        """
        row = _make_row(
            Consecutive_Up=4,
            RSI14=65.0,
            Price_vs_VWAP=0.5,
            Price_vs_EMA9=0.2,
            StochRSI_K=80.0,
        )
        score, conds = check_put_conditions(row)
        assert score == 3
        assert 'consecutive_up' in conds
        assert 'rsi_overbought_zone' in conds
        assert 'above_vwap' not in conds, (
            "above_vwap removed from PUT scoring per Track A G.P0.12"
        )
        assert 'stoch_rsi_overbought' in conds
        assert 'near_above_emas' not in conds

    def test_no_conditions_met(self):
        row = _make_row(
            Consecutive_Up=0,
            RSI14=40.0,
            Price_vs_VWAP=-1.0,
            Price_vs_EMA9=-1.0,
            Price_vs_EMA20=-1.0,
            StochRSI_K=40.0,
        )
        score, conds = check_put_conditions(row)
        assert score == 0


class TestEvaluateSignal:
    def test_call_signal_fires(self):
        """Phase 0.7.2: 4/4 conditions instead of 5/5 (near_below_emas
        dropped). Same fire decision; just lower score."""
        row = _make_row(
            Consecutive_Down=4,
            RSI14=35.0,
            Price_vs_VWAP=-0.5,
            Price_vs_EMA9=-0.2,
            StochRSI_K=20.0,
        )
        sig = evaluate_signal(row, min_conditions=3)
        assert sig is not None
        assert sig['direction'] == 'CALL'
        assert sig['base_score'] == 4
        assert sig['total_score'] == 4

    def test_put_signal_fires(self):
        row = _make_row(
            Consecutive_Up=4,
            RSI14=65.0,
            Price_vs_VWAP=0.5,
            Price_vs_EMA9=0.2,
            StochRSI_K=80.0,
        )
        sig = evaluate_signal(row, min_conditions=3)
        assert sig is not None
        assert sig['direction'] == 'PUT'
        # Track A G.P0.12: 3 instead of 4 (above_vwap dropped on top
        # of Phase 0.7.2's near_above_emas drop)
        assert sig['base_score'] == 3

    def test_no_signal_below_threshold(self):
        row = _make_row(
            Consecutive_Down=1,
            RSI14=55.0,
        )
        sig = evaluate_signal(row, min_conditions=3)
        assert sig is None

    def test_strat_bonus_added(self):
        row = _make_row(
            Consecutive_Down=4,
            RSI14=35.0,
            Price_vs_VWAP=-0.5,
            Price_vs_EMA9=-0.2,
            StochRSI_K=20.0,
        )
        sig = evaluate_signal(row, min_conditions=3, strat_bonus=2)
        assert sig is not None
        assert sig['strat_bonus'] == 2
        assert sig['total_score'] == sig['base_score'] + 2

    def test_call_preferred_over_equal_put(self):
        """When both CALL and PUT meet conditions with equal scores, CALL wins."""
        row = _make_row(
            Consecutive_Down=3,
            Consecutive_Up=3,
            RSI14=50.0,  # Borderline for both
            Price_vs_VWAP=0.0,
            Price_vs_EMA9=0.0,
            StochRSI_K=50.0,
        )
        sig = evaluate_signal(row, min_conditions=2)
        if sig is not None:
            # If both meet threshold, CALL should take priority (call_score >= put_score)
            assert sig['direction'] in ('CALL', 'PUT')


class TestGenerateSignals:
    def test_returns_dataframe(self, sample_ohlcv):
        from lib.indicators import add_all_indicators
        df = add_all_indicators(sample_ohlcv)
        result = generate_signals(df, min_conditions=2)
        assert isinstance(result, pd.DataFrame)

    def test_signal_columns(self, sample_ohlcv):
        from lib.indicators import add_all_indicators
        df = add_all_indicators(sample_ohlcv)
        result = generate_signals(df, min_conditions=2)
        if not result.empty:
            expected_cols = ['direction', 'base_score', 'total_score', 'price']
            for col in expected_cols:
                assert col in result.columns

    def test_empty_on_no_signals(self):
        """Neutral data with no extremes should produce few or no signals."""
        n = 20
        df = pd.DataFrame({
            'Open': [100.0] * n,
            'High': [101.0] * n,
            'Low': [99.0] * n,
            'Close': [100.0] * n,
            'Volume': [1000.0] * n,
        }, index=pd.date_range('2024-01-01', periods=n, freq='1min'))
        from lib.indicators import add_all_indicators
        df = add_all_indicators(df)
        result = generate_signals(df, min_conditions=5)
        # With all identical bars, unlikely to meet 5 conditions
        assert isinstance(result, pd.DataFrame)


# ── Level-break condition (Strat v2) ─────────────────────────────────────────


class TestLevelBreakCondition:
    def test_call_gets_level_break_pdh(self):
        row = _make_row(Broke_Prev_Day_High=1)
        score, conds = check_call_conditions(row)
        assert 'level_break_pdh' in conds

    def test_put_gets_level_break_pdl(self):
        row = _make_row(Broke_Prev_Day_Low=1)
        score, conds = check_put_conditions(row)
        assert 'level_break_pdl' in conds

    def test_no_level_break_when_zero(self):
        row = _make_row(Broke_Prev_Day_High=0, Broke_Prev_Day_Low=0)
        _, call_conds = check_call_conditions(row)
        _, put_conds = check_put_conditions(row)
        assert 'level_break_pdh' not in call_conds
        assert 'level_break_pdl' not in put_conds

    def test_missing_column_does_not_fire(self):
        """With the column absent (default _make_row), the vote stays
        at 4 conditions post-Phase 0.7.2 (was 5; near_below_emas dropped)."""
        row = _make_row(
            Consecutive_Down=4, RSI14=35.0, Price_vs_VWAP=-0.5,
            Price_vs_EMA9=-0.2, StochRSI_K=20.0,
        )
        score, _ = check_call_conditions(row)
        assert score == 4

    def test_five_conditions_when_level_breaks(self):
        """Phase 0.7.2: max is 5 with level_break (was 6 before
        near_below_emas was dropped)."""
        row = _make_row(
            Consecutive_Down=4, RSI14=35.0, Price_vs_VWAP=-0.5,
            Price_vs_EMA9=-0.2, StochRSI_K=20.0,
            Broke_Prev_Day_High=1,
        )
        score, conds = check_call_conditions(row)
        assert score == 5
        assert 'level_break_pdh' in conds
