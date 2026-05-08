"""Tests for `scripts/analysis/momentum_eligibility.py`.

Pure helpers (`evaluate_bars`, `format_report`) are tested with
synthetic DataFrames. The CLI (`main`) is not exercised — it pulls
from Cloud SQL which isn't available in unit tests.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd
import pytest

from scripts.analysis.momentum_eligibility import evaluate_bars, format_report


def _bullish_momentum_row(rsi: float = 35.0, vwap: float = 100.0,
                          ema9: float = 100.0, close: float = 105.0,
                          consecutive_up: int = 4,
                          rvol: float = 1.5, atr_exp: float = 1.3,
                          rsi_thrust: float = 6.0) -> dict:
    """Row that triggers all 7 momentum CALL conditions."""
    return {
        'Consecutive_Up': consecutive_up,
        'Consecutive_Down': 0,
        'RSI14': rsi,
        'Close': close,
        'VWAP': vwap,
        'EMA9': ema9,
        'RVol_Recent_20': rvol,
        'ATR_Expansion': atr_exp,
        'RSI_Thrust_3': rsi_thrust,
    }


def _bearish_momentum_row(**overrides) -> dict:
    """Row that triggers all 7 momentum PUT conditions."""
    base = {
        'Consecutive_Up': 0,
        'Consecutive_Down': 4,
        'RSI14': 65.0,
        'Close': 95.0,
        'VWAP': 100.0,
        'EMA9': 100.0,
        'RVol_Recent_20': 1.5,
        'ATR_Expansion': 1.3,
        'RSI_Thrust_3': -6.0,  # negative for PUT
    }
    base.update(overrides)
    return base


class TestEvaluateBars:
    def test_full_call_alignment_scores_seven(self):
        df = pd.DataFrame([_bullish_momentum_row()])
        out = evaluate_bars(df)
        assert out['n_bars'] == 1
        # All 7 CALL conditions met
        assert out['call']['score_dist'][7] == 1
        assert out['call']['would_fire_at'][5] == 1
        assert out['call']['would_fire_at'][3] == 1
        # PUT direction: only rvol_above_recent + atr_expansion fire
        # (symmetric confirmers; PUT-direction conditions all fail on a
        # bullish row). Score = 2 < MIN_CONDITIONS, so no PUT fire.
        assert out['put']['would_fire_at'][3] == 0
        assert out['put']['would_fire_at'][5] == 0

    def test_full_put_alignment_scores_seven(self):
        df = pd.DataFrame([_bearish_momentum_row()])
        out = evaluate_bars(df)
        assert out['n_bars'] == 1
        assert out['put']['score_dist'][7] == 1
        assert out['put']['would_fire_at'][5] == 1
        # CALL direction: only the 2 symmetric confirmers fire (rvol +
        # atr). Score = 2 < MIN_CONDITIONS.
        assert out['call']['would_fire_at'][3] == 0
        assert out['call']['would_fire_at'][5] == 0

    def test_per_condition_fire_rate_counts_each_factor(self):
        # 3 bars with bullish setup: each should fire all 7 CALL conditions
        df = pd.DataFrame([_bullish_momentum_row() for _ in range(3)])
        out = evaluate_bars(df)
        for c in ('consecutive_up', 'rsi_bullish_recovery', 'above_vwap',
                  'above_ema9', 'rvol_above_recent', 'atr_expansion',
                  'rsi_thrust'):
            assert out['call']['condition_fire_count'][c] == 3, c

    def test_partial_score_does_not_meet_threshold_5(self):
        # Mixed row: only 3 conditions met
        row = _bullish_momentum_row()
        row['Consecutive_Up'] = 1  # too few
        row['RSI14'] = 60.0  # outside oversold zone
        row['RSI_Thrust_3'] = 0.0  # below threshold
        row['ATR_Expansion'] = 1.0  # below threshold
        df = pd.DataFrame([row])
        out = evaluate_bars(df)
        # 3 conditions left: above_vwap, above_ema9, rvol_above_recent
        assert out['call']['score_dist'][3] == 1
        assert out['call']['would_fire_at'][3] == 1
        assert out['call']['would_fire_at'][5] == 0

    def test_skips_nan_rsi_bars(self):
        rows = [_bullish_momentum_row(), _bullish_momentum_row()]
        rows[1]['RSI14'] = float('nan')
        df = pd.DataFrame(rows)
        out = evaluate_bars(df)
        # Only the non-NaN bar is counted
        assert out['n_bars'] == 1
        assert out['call']['score_dist'][7] == 1


class TestFormatReport:
    def test_renders_per_ticker_section(self):
        per_ticker = {
            'SPY': {
                'n_bars': 1000,
                'call': {
                    'condition_fire_count': Counter({'above_vwap': 800, 'consecutive_up': 100}),
                    'score_dist': Counter({0: 600, 1: 200, 2: 100, 3: 50, 4: 30, 5: 15, 6: 4, 7: 1}),
                    'would_fire_at': {3: 100, 4: 50, 5: 20, 6: 5},
                },
                'put': {
                    'condition_fire_count': Counter({'below_vwap': 200}),
                    'score_dist': Counter({0: 800, 1: 100, 2: 50, 3: 30, 4: 15, 5: 4, 6: 1, 7: 0}),
                    'would_fire_at': {3: 50, 4: 20, 5: 5, 6: 1},
                },
            }
        }
        md = format_report(per_ticker, days=50)
        assert "# Momentum Strategy" in md
        assert "## SPY" in md
        assert "1,000" in md  # n_bars formatted
        assert "above_vwap" in md
        assert "Would-fire count" in md
        # Live threshold marker present
        assert "← live" in md

    def test_renders_no_data_section_when_n_bars_zero(self):
        per_ticker = {
            'IWM': {
                'n_bars': 0,
                'call': {'condition_fire_count': Counter(),
                         'score_dist': Counter(),
                         'would_fire_at': {3: 0, 4: 0, 5: 0, 6: 0}},
                'put':  {'condition_fire_count': Counter(),
                         'score_dist': Counter(),
                         'would_fire_at': {3: 0, 4: 0, 5: 0, 6: 0}},
            }
        }
        md = format_report(per_ticker, days=50)
        assert "_No bars available for IWM._" in md

    def test_includes_track_d_pairing_callout(self):
        per_ticker = {
            'SPY': {'n_bars': 0,
                    'call': {'condition_fire_count': Counter(),
                             'score_dist': Counter(),
                             'would_fire_at': {3: 0, 4: 0, 5: 0, 6: 0}},
                    'put':  {'condition_fire_count': Counter(),
                             'score_dist': Counter(),
                             'would_fire_at': {3: 0, 4: 0, 5: 0, 6: 0}}},
        }
        md = format_report(per_ticker, days=50)
        assert "issue #312" in md
        assert "Track D" in md
