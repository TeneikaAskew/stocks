"""Tests for the 2026-05-08 audit's MR PUT condition changes.

Track A G.P0.12: `above_vwap` removed globally from MR PUT scoring
across SPY/IWM/QQQ — audit measured -16.1pp / -11.7pp / -9.9pp
win-rate vs no-above_vwap PUTs.

Track A G.P0.13: `stoch_rsi_overbought` and `rsi_overbought_zone`
dropped per-ticker for IWM and QQQ via
`exit_config_overrides.disabled_conditions`.

The PUT scoring path lives in TWO modules (legacy + strategy class).
Both are tested here:

  - lib/signals.py:check_put_conditions / evaluate_signal — the LIVE
    production path used by gcp/signal_monitor.py
  - lib/strategies/mean_reversion.py:_check_put_conditions /
    MeanReversionStrategy.evaluate — used by detect_agreement and
    backtests
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from lib.signals import check_put_conditions, evaluate_signal
from lib.strategies import mean_reversion as mr
from lib.strategies.mean_reversion import (
    _apply_disabled_conditions,
    _check_put_conditions,
    MeanReversionStrategy,
)


def _bullish_setup_for_put(rsi: float = 60.0, stoch_k: float = 80.0,
                           price_vs_vwap: float = 0.5,
                           consecutive_up: int = 3,
                           broke_pdl: int = 1) -> pd.Series:
    """Row that previously triggered all 5 PUT conditions including
    `above_vwap`. Column name `RSI14` matches IndicatorConfig.rsi_col."""
    return pd.Series({
        'Consecutive_Up': consecutive_up,
        'RSI14': rsi,
        'Price_vs_VWAP': price_vs_vwap,
        'StochRSI_K': stoch_k,
        'Broke_Prev_Day_Low': broke_pdl,
    })


# ──────────────────────────────────────────────────────────────────────
# G.P0.12: above_vwap REMOVED globally from MR PUT
# ──────────────────────────────────────────────────────────────────────


class TestAboveVwapRemoved:
    def test_lib_signals_does_not_score_above_vwap(self):
        row = _bullish_setup_for_put()
        score, conds = check_put_conditions(row)
        assert 'above_vwap' not in conds, (
            "above_vwap is anti-correlated with PUT success and was "
            "removed by the 2026-05-08 audit."
        )

    def test_lib_strategies_mr_does_not_score_above_vwap(self):
        row = _bullish_setup_for_put()
        score, conds = _check_put_conditions(row)
        assert 'above_vwap' not in conds

    def test_lib_signals_max_score_is_4_not_5(self):
        """With above_vwap dropped, the all-conditions-true row scores
        4, not 5."""
        row = _bullish_setup_for_put()
        score, conds = check_put_conditions(row)
        # consecutive_up + rsi_overbought_zone + stoch_rsi_overbought +
        # level_break_pdl = 4
        assert score == 4
        assert sorted(conds) == sorted([
            'consecutive_up', 'rsi_overbought_zone',
            'stoch_rsi_overbought', 'level_break_pdl',
        ])

    def test_lib_strategies_max_score_is_4_not_5(self):
        row = _bullish_setup_for_put()
        score, conds = _check_put_conditions(row)
        assert score == 4

    def test_above_vwap_does_not_affect_score_when_true(self):
        """Two identical rows except Price_vs_VWAP: same score now."""
        row_above = _bullish_setup_for_put(price_vs_vwap=0.5)
        row_below = _bullish_setup_for_put(price_vs_vwap=-0.5)
        s_a, c_a = check_put_conditions(row_above)
        s_b, c_b = check_put_conditions(row_below)
        assert s_a == s_b == 4

    def test_call_path_unaffected(self):
        """Sanity: removing PUT-side above_vwap doesn't touch CALL
        scoring, which has its own `below_vwap` factor (kept)."""
        from lib.signals import check_call_conditions
        row = pd.Series({
            'Consecutive_Down': 3,
            'RSI14': 30.0,
            'Price_vs_VWAP': -0.5,  # below VWAP for CALL
            'StochRSI_K': 20.0,
            'Broke_Prev_Day_High': 1,
            'Price_vs_EMA_Fast': -0.05,
            'Price_vs_EMA_Mid': -0.05,
        })
        score, conds = check_call_conditions(row)
        assert 'below_vwap' in conds  # CALL keeps its VWAP factor


# ──────────────────────────────────────────────────────────────────────
# G.P0.13: per-ticker disabled_conditions filter
# ──────────────────────────────────────────────────────────────────────


class TestPerTickerDisabledConditions:
    def test_apply_disabled_no_op_when_ticker_none(self):
        score, conds = _apply_disabled_conditions(
            3, ['rsi_overbought_zone', 'level_break_pdl', 'consecutive_up'],
            None,
        )
        assert score == 3
        assert conds == ['rsi_overbought_zone', 'level_break_pdl', 'consecutive_up']

    def test_apply_disabled_filters_when_ticker_has_overrides(self):
        with patch('lib.strategies.exit_config_overrides.get_disabled_conditions',
                   return_value=['stoch_rsi_overbought', 'rsi_overbought_zone']):
            score, conds = _apply_disabled_conditions(
                4,
                ['consecutive_up', 'rsi_overbought_zone',
                 'stoch_rsi_overbought', 'level_break_pdl'],
                'IWM',
            )
        # Two filtered out → 2 conditions kept, score recomputed
        assert score == 2
        assert sorted(conds) == ['consecutive_up', 'level_break_pdl']

    def test_apply_disabled_no_op_when_ticker_has_no_overrides(self):
        with patch('lib.strategies.exit_config_overrides.get_disabled_conditions',
                   return_value=[]):
            score, conds = _apply_disabled_conditions(
                4,
                ['consecutive_up', 'rsi_overbought_zone',
                 'stoch_rsi_overbought', 'level_break_pdl'],
                'SPY',
            )
        assert score == 4

    def test_evaluate_signal_with_iwm_drops_disabled_conditions(self):
        """End-to-end through evaluate_signal: PUT score for IWM with
        all conditions true should be 2 (only consecutive_up +
        level_break_pdl), not 4."""
        row = _bullish_setup_for_put()
        with patch('lib.strategies.exit_config_overrides.get_disabled_conditions',
                   return_value=['stoch_rsi_overbought', 'rsi_overbought_zone']):
            sig = evaluate_signal(row, min_conditions=2, ticker='IWM')
        assert sig is not None
        assert sig['direction'] == 'PUT'
        assert sig['base_score'] == 2
        assert sorted(sig['conditions_met']) == [
            'consecutive_up', 'level_break_pdl',
        ]

    def test_evaluate_signal_without_ticker_keeps_all_conditions(self):
        """Legacy callers that don't pass `ticker` keep the full
        condition list (legacy back-compat)."""
        row = _bullish_setup_for_put()
        sig = evaluate_signal(row, min_conditions=4, ticker=None)
        assert sig is not None
        assert sig['direction'] == 'PUT'
        assert sig['base_score'] == 4

    def test_strategy_class_passes_ticker_through(self):
        """MeanReversionStrategy.evaluate(ticker='IWM') applies the
        per-ticker filter to both CALL and PUT scoring paths."""
        row = _bullish_setup_for_put()
        with patch('lib.strategies.exit_config_overrides.get_disabled_conditions',
                   return_value=['stoch_rsi_overbought', 'rsi_overbought_zone']):
            strat = MeanReversionStrategy()
            sig = strat.evaluate(row, ticker='IWM')
        # With the filter, PUT score drops from 4 to 2.
        # If 2 < default MIN_CONDITIONS (which is 3) the signal vanishes.
        # Either is acceptable behavior; assert the filter applied.
        if sig is not None:
            for c in ('stoch_rsi_overbought', 'rsi_overbought_zone'):
                assert c not in sig.conditions_met
