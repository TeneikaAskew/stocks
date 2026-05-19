"""Unit tests for the earnings playability calibration sweep —
hermetic, no DB required.

Covers:
  - compute_quintile_spread: the sweep's ranking metric
  - _reactions_stats_from_past lookback window cap
  - select_earnings_winner: the strategic auto-apply gate
  - get_earnings_calibration Tier-B fallback
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.backtest_playability import (
    _reactions_stats_from_past,
    compute_quintile_spread,
)
from lib.earnings_reactions import select_earnings_winner


class TestComputeQuintileSpread:
    def test_empty_or_none(self):
        zero = {"n_predictions": 0, "overall_hit_rate": 0.0,
                "quintile_spread": 0.0}
        assert compute_quintile_spread(pd.DataFrame()) == zero
        assert compute_quintile_spread(None) == zero

    def test_perfect_separation(self):
        # 10 distinct scores; the bottom half all miss, the top half hit.
        df = pd.DataFrame({
            "score": [float(i) for i in range(10)],
            "hit": [False] * 5 + [True] * 5,
        })
        m = compute_quintile_spread(df)
        assert m["n_predictions"] == 10
        assert m["overall_hit_rate"] == pytest.approx(0.5)
        # Top score quintile hits 100%, bottom 0% -> spread 1.0.
        assert m["quintile_spread"] == pytest.approx(1.0)

    def test_drops_nan_rows(self):
        df = pd.DataFrame({
            "score": [1.0, 2.0, None, 4.0],
            "hit": [True, False, True, None],
        })
        # Only the two fully-populated rows count.
        assert compute_quintile_spread(df)["n_predictions"] == 2


class TestReactionsStatsLookback:
    @staticmethod
    def _past(n):
        return pd.DataFrame({
            "reaction_gap_pct": [1.0] * n,
            "direction_consistent_5d": [True] * n,
            "is_reversal_5d": [False] * n,
        })

    def test_lookback_caps_window(self):
        past = self._past(20)
        assert _reactions_stats_from_past(past)["n_q"] == 20
        assert _reactions_stats_from_past(past, lookback=5)["n_q"] == 5

    def test_lookback_none_or_zero_uses_all(self):
        past = self._past(12)
        assert _reactions_stats_from_past(past, lookback=None)["n_q"] == 12
        assert _reactions_stats_from_past(past, lookback=0)["n_q"] == 12


class TestSelectEarningsWinner:
    @staticmethod
    def _r(**kw):
        base = {"min_nq": 12, "lookback_quarters": 12,
                "n_predictions": 8000, "overall_hit_rate": 0.55,
                "quintile_spread": 0.20}
        base.update(kw)
        return base

    def test_picks_highest_spread_among_eligible(self):
        results = [self._r(lookback_quarters=8, quintile_spread=0.18),
                   self._r(lookback_quarters=12, quintile_spread=0.27)]
        assert select_earnings_winner(results)["lookback_quarters"] == 12

    def test_none_when_too_few_predictions(self):
        assert select_earnings_winner(
            [self._r(n_predictions=100, quintile_spread=0.30)]) is None

    def test_none_when_spread_not_positive(self):
        assert select_earnings_winner(
            [self._r(quintile_spread=0.0)]) is None

    def test_none_on_empty(self):
        assert select_earnings_winner([]) is None

    def test_high_spread_low_sample_excluded(self):
        # A spike combo with too little sample loses to a solid one.
        results = [self._r(n_predictions=50, quintile_spread=0.9),
                   self._r(n_predictions=9000, quintile_spread=0.15)]
        assert select_earnings_winner(results)["n_predictions"] == 9000


class TestGetEarningsCalibration:
    def test_tier_b_when_not_configured(self, monkeypatch):
        from lib import earnings_reactions as er
        er.get_earnings_calibration.cache_clear()
        monkeypatch.setattr("gcp.database.is_cloud_sql_configured",
                            lambda: False)
        cal = er.get_earnings_calibration()
        assert cal == {"min_nq": er.DEFAULT_MIN_NQ,
                       "lookback_quarters": er.DEFAULT_LOOKBACK_QUARTERS}
        er.get_earnings_calibration.cache_clear()
