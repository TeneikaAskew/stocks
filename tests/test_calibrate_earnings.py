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
    _archetype_directional_return,
    _reactions_stats_from_past,
    _summary_stats_pct,
    compute_dollar_metrics,
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


class TestArchetypeDirectionalReturn:
    def test_bullish_trend_long(self):
        assert _archetype_directional_return('bullish_trend', 5.0, 3.2) == 3.2

    def test_bearish_trend_short(self):
        assert _archetype_directional_return('bearish_trend', -2.0, 4.0) == -4.0

    def test_reversal_play_fades_positive_gap(self):
        # gap was +5 — bet is to short — hold went +3 → trade lost 3
        assert _archetype_directional_return('reversal_play', 5.0, 3.0) == -3.0

    def test_reversal_play_fades_negative_gap(self):
        # gap was -5 — bet is to long — hold went -2 → trade lost 2
        assert _archetype_directional_return('reversal_play', -5.0, -2.0) == -2.0

    def test_mixed_returns_none(self):
        assert _archetype_directional_return('mixed', 5.0, 3.0) is None

    def test_quiet_returns_none(self):
        assert _archetype_directional_return('quiet', 5.0, 3.0) is None

    def test_none_inputs(self):
        assert _archetype_directional_return(None, 1.0, 1.0) is None
        assert _archetype_directional_return('bullish_trend', 1.0, None) is None
        assert _archetype_directional_return('reversal_play', 0.0, 1.0) is None


class TestSummaryStatsPct:
    def test_empty(self):
        m = _summary_stats_pct(pd.Series([], dtype='float64'))
        assert m['n'] == 0
        # NaN-safe — every metric is NaN, not 0.
        for k in ('win_rate', 'avg_win_pct', 'avg_loss_pct', 'payoff_ratio',
                  'expectancy_pct', 'profit_factor', 'max_drawdown_pct',
                  'sharpe_per_trade'):
            assert m[k] != m[k]  # NaN

    def test_all_wins(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0])
        m = _summary_stats_pct(s)
        assert m['n'] == 4
        assert m['win_rate'] == 1.0
        assert m['avg_win_pct'] == pytest.approx(2.5)
        assert m['avg_loss_pct'] == 0.0
        # No losers → payoff_ratio + profit_factor are inf (caller maps
        # to SQL NULL via _nan_to_none).
        assert m['payoff_ratio'] == float('inf')
        assert m['profit_factor'] == float('inf')
        assert m['expectancy_pct'] == pytest.approx(2.5)
        assert m['max_drawdown_pct'] == 0.0  # never went down

    def test_all_losses(self):
        s = pd.Series([-1.0, -2.0, -3.0])
        m = _summary_stats_pct(s)
        assert m['n'] == 3
        assert m['win_rate'] == 0.0
        assert m['avg_win_pct'] == 0.0
        assert m['avg_loss_pct'] == pytest.approx(-2.0)
        assert m['payoff_ratio'] == 0.0
        assert m['profit_factor'] == 0.0
        assert m['expectancy_pct'] == pytest.approx(-2.0)
        # Cumulative path: -1, -3, -6. Max DD = -6.
        assert m['max_drawdown_pct'] == pytest.approx(-6.0)

    def test_mixed_win_loss(self):
        # Wins: +4, +6 (avg +5). Losses: -2, -2 (avg -2). Payoff = 2.5.
        # Gross win 10, gross loss -4 → profit factor 2.5. Expectancy
        # 6/4 = 1.5.
        s = pd.Series([4.0, -2.0, 6.0, -2.0])
        m = _summary_stats_pct(s)
        assert m['win_rate'] == 0.5
        assert m['avg_win_pct'] == pytest.approx(5.0)
        assert m['avg_loss_pct'] == pytest.approx(-2.0)
        assert m['payoff_ratio'] == pytest.approx(2.5)
        assert m['profit_factor'] == pytest.approx(2.5)
        assert m['expectancy_pct'] == pytest.approx(1.5)

    def test_max_drawdown_path_dependent(self):
        # +5, -10, +6 → cumulative 5, -5, 1 → peak path 5, 5, 5 → DD
        # max = -10 (at idx 1). Caller passes in chronological order.
        s = pd.Series([5.0, -10.0, 6.0])
        assert _summary_stats_pct(s)['max_drawdown_pct'] == pytest.approx(-10.0)


class TestComputeDollarMetrics:
    @staticmethod
    def _make_predictions(n_per_q: int = 20):
        """Build a predictions frame with a clean Q5 directional set:
        bullish_trend predictions where every 5d-hold is +2% (winner)
        and bearish where every 5d-hold is +1% (loser — short missed).
        """
        rows = []
        # 5 quintiles' worth of scores so qcut works.
        for q in range(5):
            base_score = 10 + q * 10  # 10, 20, 30, 40, 50 → Q1..Q5
            for i in range(n_per_q):
                rows.append({
                    'ticker': f'T{q}{i}',
                    'reported_date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=q * n_per_q + i),
                    'archetype': 'bullish_trend' if i % 2 == 0 else 'bearish_trend',
                    'score': float(base_score + i * 0.01),
                    'actual_gap_pct': 1.5,
                    'sustain_3d_pct': 1.8,
                    'sustain_5d_pct': 2.0 if i % 2 == 0 else 1.0,
                    'sustain_10d_pct': 3.0 if i % 2 == 0 else 1.5,
                    'hit': True,
                })
        return pd.DataFrame(rows)

    def test_empty_returns_nan_safe(self):
        m = compute_dollar_metrics(pd.DataFrame())
        assert m['n_q5_directional'] == 0
        assert m['expectancy_pct'] != m['expectancy_pct']  # NaN
        assert m['best_hold_horizon_days'] is None

    def test_none_input(self):
        m = compute_dollar_metrics(None)
        assert m['n_q5_directional'] == 0

    def test_q5_only_directional_archetypes(self):
        df = self._make_predictions(n_per_q=20)
        m = compute_dollar_metrics(df)
        # Q5 has 20 rows, all directional (bullish or bearish).
        assert m['n_q5_directional'] == 20
        # Bulls win (+2%), bears lose (-1% on the short = -hold). So
        # half wins +2, half lose -1: avg_win=2, avg_loss=-1, payoff=2,
        # expectancy = 0.5. Q5 picks the top 20% which here = the
        # highest-score 20 rows.
        assert m['avg_win_pct'] == pytest.approx(2.0)
        assert m['avg_loss_pct'] == pytest.approx(-1.0)
        assert m['payoff_ratio'] == pytest.approx(2.0)
        assert m['expectancy_pct'] == pytest.approx(0.5)
        # $ conversion: 0.5% × $10/$1k = $5/$1k.
        assert m['expectancy_dollars_per_1k'] == pytest.approx(5.0)
        # best_hold should pick one of the horizons.
        assert m['best_hold_horizon_days'] in (1, 3, 5, 10)

    def test_skips_mixed_and_quiet_archetypes(self):
        rows = []
        for i in range(100):
            rows.append({
                'ticker': f'T{i}',
                'reported_date': pd.Timestamp('2024-01-01') + pd.Timedelta(days=i),
                'archetype': 'mixed',  # all mixed → excluded entirely
                'score': float(i),
                'actual_gap_pct': 1.0,
                'sustain_5d_pct': 1.0,
            })
        m = compute_dollar_metrics(pd.DataFrame(rows))
        assert m['n_q5_directional'] == 0


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
