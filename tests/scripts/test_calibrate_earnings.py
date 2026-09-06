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
    _long_call_pnl_pct,
    _long_put_pnl_pct,
    _long_straddle_pnl_pct,
    _reactions_stats_from_past,
    _select_atm_pair,
    _select_delta_n_pair,
    _short_strangle_pnl_pct,
    _summary_stats_pct,
    compute_dollar_metrics,
    compute_options_metrics,
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


class TestLongStraddlePnlPct:
    def test_winner_when_move_exceeds_premium(self):
        # Bought ATM straddle 100C+100P at premium $3+$3=$6. Stock
        # moves to 110. Intrinsic = 10 (call) + 0 = 10. PnL = 10-6 = 4.
        # Return = 4/6 = 66.7%.
        assert _long_straddle_pnl_pct(3.0, 3.0, 100.0, 110.0) == pytest.approx(
            (10.0 - 6.0) / 6.0 * 100.0)

    def test_loser_when_move_below_premium(self):
        # Same straddle, stock stays at 102. Intrinsic = 2. PnL = -4.
        # Return = -4/6 = -66.7%.
        assert _long_straddle_pnl_pct(3.0, 3.0, 100.0, 102.0) == pytest.approx(
            (2.0 - 6.0) / 6.0 * 100.0)

    def test_total_loss_when_pinned(self):
        # Stock pins at strike, intrinsic=0, lose 100% of premium.
        assert _long_straddle_pnl_pct(3.0, 3.0, 100.0, 100.0) == -100.0

    def test_none_inputs(self):
        assert _long_straddle_pnl_pct(None, 3.0, 100.0, 100.0) is None
        assert _long_straddle_pnl_pct(3.0, 3.0, 100.0, None) is None

    def test_zero_premium_unusable(self):
        # Defensive — zero-mid pair shouldn't crash.
        assert _long_straddle_pnl_pct(0.0, 0.0, 100.0, 105.0) is None


class TestShortStranglePnlPct:
    def test_max_profit_when_inside_strikes(self):
        # Sold 110C + 90P for $1+$1=$2. Stock stays at 100. Intrinsic
        # at expiry = 0+0. Keep full $2 premium. Return = 100%.
        assert _short_strangle_pnl_pct(1.0, 1.0, 110.0, 90.0, 100.0) == 100.0

    def test_partial_loss_blow_through_call(self):
        # Same wings, stock moves to 115. Intrinsic = 5 (call) + 0
        # = 5. PnL = 2 - 5 = -3. Return = -3/2 = -150%.
        assert _short_strangle_pnl_pct(1.0, 1.0, 110.0, 90.0, 115.0) == pytest.approx(
            (2.0 - 5.0) / 2.0 * 100.0)

    def test_loss_blow_through_put(self):
        assert _short_strangle_pnl_pct(1.0, 1.0, 110.0, 90.0, 85.0) == pytest.approx(
            (2.0 - 5.0) / 2.0 * 100.0)

    def test_none_inputs(self):
        assert _short_strangle_pnl_pct(None, 1.0, 110.0, 90.0, 100.0) is None
        assert _short_strangle_pnl_pct(1.0, 1.0, None, 90.0, 100.0) is None


class TestLongCallPutPnlPct:
    def test_long_call_in_the_money(self):
        # Paid $2 for 100C, stock goes to 105. Intrinsic = 5. PnL = 3.
        assert _long_call_pnl_pct(2.0, 100.0, 105.0) == pytest.approx(150.0)

    def test_long_call_total_loss_otm(self):
        assert _long_call_pnl_pct(2.0, 100.0, 99.0) == -100.0

    def test_long_put_in_the_money(self):
        # Paid $2 for 100P, stock drops to 95. Intrinsic = 5. PnL = 3.
        assert _long_put_pnl_pct(2.0, 100.0, 95.0) == pytest.approx(150.0)

    def test_long_put_total_loss_otm(self):
        assert _long_put_pnl_pct(2.0, 100.0, 101.0) == -100.0


class TestSelectAtmPair:
    @staticmethod
    def _chain(strikes_with_call_put):
        """Build a chain DF from a list of (strike, has_call, has_put, bid, ask)."""
        from datetime import date
        rows = []
        for strike, has_c, has_p, bid, ask in strikes_with_call_put:
            if has_c:
                rows.append({'strike': strike, 'option_type': 'calls',
                             'expiration': date(2025, 2, 7),
                             'bid': bid, 'ask': ask, 'last_price': (bid+ask)/2,
                             'implied_volatility': 0.30, 'delta': 0.5})
            if has_p:
                rows.append({'strike': strike, 'option_type': 'puts',
                             'expiration': date(2025, 2, 7),
                             'bid': bid, 'ask': ask, 'last_price': (bid+ask)/2,
                             'implied_volatility': 0.32, 'delta': -0.5})
        return pd.DataFrame(rows)

    def test_picks_closest_paired_strike(self):
        # spot=100, paired strikes at 95, 100, 105 — should pick 100.
        chain = self._chain([(95, True, True, 0.5, 0.6),
                              (100, True, True, 2.0, 2.2),
                              (105, True, True, 0.5, 0.6)])
        atm = _select_atm_pair(chain, spot=100.0)
        assert atm is not None
        assert atm['strike'] == 100.0
        assert atm['call_mid'] == pytest.approx(2.1)
        assert atm['put_mid'] == pytest.approx(2.1)

    def test_skips_unpaired_strikes(self):
        # 100 has call only, 99 has both → pick 99.
        chain = self._chain([(100, True, False, 2.0, 2.2),
                              (99, True, True, 1.5, 1.7)])
        atm = _select_atm_pair(chain, spot=100.0)
        assert atm is not None
        assert atm['strike'] == 99.0

    def test_returns_none_no_paired_strike(self):
        chain = self._chain([(100, True, False, 2.0, 2.2)])
        assert _select_atm_pair(chain, spot=100.0) is None

    def test_returns_none_empty_chain(self):
        assert _select_atm_pair(pd.DataFrame(), spot=100.0) is None

    def test_returns_none_invalid_spot(self):
        chain = self._chain([(100, True, True, 2.0, 2.2)])
        assert _select_atm_pair(chain, spot=0.0) is None
        assert _select_atm_pair(chain, spot=None) is None


class TestSelectDeltaNPair:
    @staticmethod
    def _chain_with_deltas(items):
        """items: list of (strike, option_type, delta, bid, ask)."""
        from datetime import date
        rows = []
        for strike, ot, delta, bid, ask in items:
            rows.append({'strike': strike, 'option_type': ot,
                         'expiration': date(2025, 2, 7),
                         'bid': bid, 'ask': ask, 'last_price': (bid+ask)/2,
                         'implied_volatility': 0.30, 'delta': delta})
        return pd.DataFrame(rows)

    def test_picks_closest_to_target(self):
        chain = self._chain_with_deltas([
            (110, 'calls', 0.18, 0.5, 0.6),
            (105, 'calls', 0.35, 1.5, 1.7),
            (95, 'puts', -0.20, 0.5, 0.6),
            (90, 'puts', -0.10, 0.2, 0.3),
        ])
        w = _select_delta_n_pair(chain, target_delta=0.20)
        assert w is not None
        # Closest to +0.20 call is delta 0.18 at strike 110.
        assert w['call_strike'] == 110.0
        # Closest to -0.20 put is delta -0.20 at strike 95.
        assert w['put_strike'] == 95.0

    def test_returns_none_no_calls_or_puts(self):
        chain = self._chain_with_deltas([(110, 'calls', 0.18, 0.5, 0.6)])
        assert _select_delta_n_pair(chain) is None


class TestComputeOptionsMetrics:
    @staticmethod
    def _build_predictions_and_options():
        """Q5 events with matched options snapshots — small but
        deterministic so the means are computable by hand."""
        from datetime import date, timedelta
        events = []
        opt_rows = []
        for q in range(5):
            base_score = 10 + q * 10
            for i in range(20):
                ticker = f'T{q}{i}'
                # Spread events across a year so dates differ
                reported = date(2024, 1, 1) + timedelta(days=q * 20 + i)
                snapshot = reported - timedelta(days=1)
                events.append({
                    'ticker': ticker,
                    'reported_date': reported,
                    'archetype': 'bullish_trend',
                    'score': float(base_score + i * 0.01),
                    'actual_gap_pct': 3.0,
                    'sustain_5d_pct': 2.0,
                    'd_minus_1_close': 100.0,
                    'd_plus_1_close':  103.0,  # 3% move (matches gap)
                })
                # Only attach options for Q5 events
                if q == 4:
                    # ATM 100C + 100P at $2 each → straddle premium $4
                    # → implied move 4%. Realized 3% < implied 4% →
                    # long straddle loses, short strangle wins.
                    expiry = reported + timedelta(days=7)
                    opt_rows.append({'symbol': ticker, 'snapshot_date': snapshot,
                                     'expiration': expiry, 'strike': 100.0,
                                     'option_type': 'calls', 'bid': 1.9, 'ask': 2.1,
                                     'last_price': 2.0, 'implied_volatility': 0.40,
                                     'delta': 0.50})
                    opt_rows.append({'symbol': ticker, 'snapshot_date': snapshot,
                                     'expiration': expiry, 'strike': 100.0,
                                     'option_type': 'puts', 'bid': 1.9, 'ask': 2.1,
                                     'last_price': 2.0, 'implied_volatility': 0.40,
                                     'delta': -0.50})
                    # Add delta-20 wings for the strangle calc
                    opt_rows.append({'symbol': ticker, 'snapshot_date': snapshot,
                                     'expiration': expiry, 'strike': 105.0,
                                     'option_type': 'calls', 'bid': 0.4, 'ask': 0.6,
                                     'last_price': 0.5, 'implied_volatility': 0.40,
                                     'delta': 0.20})
                    opt_rows.append({'symbol': ticker, 'snapshot_date': snapshot,
                                     'expiration': expiry, 'strike': 95.0,
                                     'option_type': 'puts', 'bid': 0.4, 'ask': 0.6,
                                     'last_price': 0.5, 'implied_volatility': 0.40,
                                     'delta': -0.20})
        return pd.DataFrame(events), pd.DataFrame(opt_rows)

    def test_empty_predictions(self):
        m = compute_options_metrics(pd.DataFrame(), pd.DataFrame())
        assert m['n_with_options'] == 0
        assert m['avg_long_straddle_pnl_pct'] != m['avg_long_straddle_pnl_pct']  # NaN

    def test_empty_options(self):
        preds, _ = self._build_predictions_and_options()
        m = compute_options_metrics(preds, pd.DataFrame())
        assert m['n_with_options'] == 0

    def test_q5_matched_metrics(self):
        preds, opts = self._build_predictions_and_options()
        m = compute_options_metrics(preds, opts)
        # Q5 = 20 events, all matched.
        assert m['n_with_options'] == 20
        # Implied move from $4 straddle / $100 = 4.0%.
        assert m['avg_implied_move_pct'] == pytest.approx(4.0)
        # Realized move |3%| = 3.0%.
        assert m['avg_realized_move_pct'] == pytest.approx(3.0)
        # Ratio = 3/4 = 0.75.
        assert m['realized_vs_implied_ratio'] == pytest.approx(0.75)
        # Long straddle: spot exit 103, strike 100, intrinsic = 3.
        # Premium = $4. PnL = 3-4 = -1 → -25% return.
        assert m['avg_long_straddle_pnl_pct'] == pytest.approx(-25.0)
        # Short delta-20 strangle (105C + 95P @ $0.5 each, $1 total premium).
        # Spot 103, intrinsic = max(103-105,0) + max(95-103,0) = 0.
        # PnL = premium - 0 = 1 = 100% return.
        assert m['avg_short_strangle_pnl_pct'] == pytest.approx(100.0)
        # Long ATM call: paid $2, spot 103, intrinsic 3, PnL = 1 = 50%.
        assert m['avg_long_call_pnl_pct'] == pytest.approx(50.0)
        # Long ATM put: paid $2, spot 103, intrinsic 0, total loss -100%.
        assert m['avg_long_put_pnl_pct'] == pytest.approx(-100.0)


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
