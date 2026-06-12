"""Hermetic tests for lib/options_intraday — BSM repricer.

These tests pass synthetic 1-min bars directly to ``intraday_bars=`` so
no Cloud SQL dependency is required. Math is checked against hand-
computable BSM scenarios and intuitive boundary conditions (deep ITM
call → ~spot − strike, expiry-at-money → near zero).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from lib.options_intraday import (
    _bsm_price_vec,
    _combine_legs,
    reprice_intraday_option,
    reprice_structure_intraday,
    cumulative_theta_decay,
    intraday_theta_decay_fraction,
    minutes_from_rth_open,
)


def _synthetic_bars(intraday_date: date, spot_path: list[float],
                    start_min: int = 9*60 + 30) -> pd.DataFrame:
    """Build a 1-min bar DataFrame with the given spot path."""
    times = [datetime.combine(intraday_date, datetime.min.time())
             + timedelta(minutes=start_min + i)
             for i in range(len(spot_path))]
    return pd.DataFrame({'Time': times, 'Spot': spot_path})


class TestBsmPriceVec:
    """Direct unit tests on the vectorised BSM pricer."""

    def test_call_at_the_money_30dte_30iv(self):
        # Classic textbook BSM ATM call. With S=K=100, t=30/365, IV=30%,
        # r=q=0 → C ≈ 100 * (N(d1) - N(d2)) where d1 = sigma*sqrt(t)/2.
        # That works out to ≈ 3.45.
        price = _bsm_price_vec(flag='c', S=100.0, K=100.0,
                               t=30/365, r=0.0, sigma=0.30, q=0.0)
        assert price[0] == pytest.approx(3.45, abs=0.1)

    def test_put_call_parity(self):
        # C - P = F - K (discounted). r=q=0 so F=S. Therefore
        # C - P = S - K. Pick S=110, K=100 → C - P should be 10.
        c = _bsm_price_vec(flag='c', S=110.0, K=100.0,
                           t=30/365, r=0.0, sigma=0.30, q=0.0)[0]
        p = _bsm_price_vec(flag='p', S=110.0, K=100.0,
                           t=30/365, r=0.0, sigma=0.30, q=0.0)[0]
        assert (c - p) == pytest.approx(10.0, abs=0.01)

    def test_deep_itm_call_approaches_intrinsic(self):
        # S=200, K=100, t=1/365. Deep ITM with one day to expiry →
        # value ≈ intrinsic = 100.
        price = _bsm_price_vec(flag='c', S=200.0, K=100.0,
                               t=1/365, r=0.0, sigma=0.30, q=0.0)
        assert price[0] == pytest.approx(100.0, abs=0.1)

    def test_otm_call_near_expiry_approaches_zero(self):
        # S=80, K=100, t=1/365. Deep OTM with one day → near zero.
        price = _bsm_price_vec(flag='c', S=80.0, K=100.0,
                               t=1/365, r=0.0, sigma=0.30, q=0.0)
        assert price[0] == pytest.approx(0.0, abs=0.01)

    def test_vectorised_broadcasting(self):
        # 3 spots, scalar t/sigma → broadcast to 3 outputs.
        prices = _bsm_price_vec(flag='c',
                                S=np.array([90, 100, 110]),
                                K=100.0, t=30/365, r=0.0,
                                sigma=0.30, q=0.0)
        assert prices.shape == (3,)
        # Monotonically increasing in S for a call.
        assert prices[0] < prices[1] < prices[2]


class TestReprice:
    """Integration tests on reprice_intraday_option using synthetic bars."""

    def test_flat_market_close_to_entry(self):
        """When spot stays flat and IV doesn't crush, the option value
        decays modestly via theta but stays close to entry."""
        bars = _synthetic_bars(date(2025, 7, 31), [100.0] * 5)
        tl = reprice_intraday_option(
            ticker='TEST', intraday_date=date(2025, 7, 31),
            strike=100.0, expiration=date(2025, 8, 1),
            option_type='call', iv_t_minus_1=0.30,
            entry_price_per_share=2.0,
            intraday_bars=bars,
            iv_open_multiplier=1.0, iv_close_multiplier=1.0,
            risk_free=0.0, dividend_yield=0.0,
        )
        # Spot stays at strike → option value should be small but positive.
        # PnL should be negative (paid 2.0, worth less).
        assert (tl['Theo_value'] < 2.0).all()
        # Sanity: shape preserved
        assert len(tl) == 5

    def test_rally_into_intrinsic(self):
        """ATM call, spot rallies $20 above strike → at the close, value
        is approximately intrinsic ($20) since IV has crushed near expiry."""
        bars = _synthetic_bars(date(2025, 7, 31),
                               [100.0, 105.0, 110.0, 115.0, 120.0])
        tl = reprice_intraday_option(
            ticker='TEST', intraday_date=date(2025, 7, 31),
            strike=100.0, expiration=date(2025, 8, 1),
            option_type='call', iv_t_minus_1=0.50,
            entry_price_per_share=2.0,
            intraday_bars=bars,
            risk_free=0.0, dividend_yield=0.0,
        )
        # Last bar value should be approximately $20 (intrinsic), with a
        # small extrinsic remaining from the crushed IV.
        assert tl['Theo_value'].iloc[-1] == pytest.approx(20.0, abs=2.0)
        # Pnl per contract = (20 - 2) * 100 = $1,800 ish
        assert tl['Pnl_per_contract'].iloc[-1] == pytest.approx(1800.0, abs=200.0)
        # Pnl % should be ~+800% (10x return; 18/2)
        assert tl['Pnl_pct'].iloc[-1] > 500.0

    def test_iv_decay_monotonic(self):
        """IV path should decrease linearly from open to close."""
        bars = _synthetic_bars(date(2025, 7, 31), [100.0] * 10)
        tl = reprice_intraday_option(
            ticker='TEST', intraday_date=date(2025, 7, 31),
            strike=100.0, expiration=date(2025, 8, 1),
            option_type='call', iv_t_minus_1=0.60,
            entry_price_per_share=2.0,
            intraday_bars=bars,
            iv_open_multiplier=0.50, iv_close_multiplier=0.40,
            risk_free=0.0, dividend_yield=0.0,
        )
        ivs = tl['IV_used'].to_numpy()
        # Monotonically non-increasing
        assert (ivs[:-1] >= ivs[1:]).all()
        # First and last match the multipliers
        assert ivs[0] == pytest.approx(0.60 * 0.50, abs=1e-6)
        assert ivs[-1] == pytest.approx(0.60 * 0.40, abs=1e-6)

    def test_put_inverse_of_call_at_extremes(self):
        bars = _synthetic_bars(date(2025, 7, 31),
                               [100.0, 90.0, 80.0, 75.0])
        tl_call = reprice_intraday_option(
            ticker='T', intraday_date=date(2025, 7, 31),
            strike=100.0, expiration=date(2025, 8, 1),
            option_type='call', iv_t_minus_1=0.40,
            entry_price_per_share=2.0, intraday_bars=bars,
            risk_free=0.0, dividend_yield=0.0,
        )
        tl_put = reprice_intraday_option(
            ticker='T', intraday_date=date(2025, 7, 31),
            strike=100.0, expiration=date(2025, 8, 1),
            option_type='put', iv_t_minus_1=0.40,
            entry_price_per_share=2.0, intraday_bars=bars,
            risk_free=0.0, dividend_yield=0.0,
        )
        # Stock fell to 75 → put intrinsic 25, call ≈ 0.
        assert tl_put['Theo_value'].iloc[-1] > 20.0
        assert tl_call['Theo_value'].iloc[-1] < 1.0

    def test_empty_bars_returns_empty(self):
        tl = reprice_intraday_option(
            ticker='T', intraday_date=date(2025, 7, 31),
            strike=100.0, expiration=date(2025, 8, 1),
            option_type='call', iv_t_minus_1=0.30,
            entry_price_per_share=2.0,
            intraday_bars=pd.DataFrame(columns=['Time', 'Spot']),
            risk_free=0.0, dividend_yield=0.0,
        )
        assert tl.empty
        assert list(tl.columns) == [
            'Time', 'Spot', 'IV_used', 'Theo_value',
            'Pnl_per_share', 'Pnl_per_contract', 'Pnl_pct']

    def test_invalid_option_type(self):
        with pytest.raises(ValueError, match="call/put"):
            reprice_intraday_option(
                ticker='T', intraday_date=date(2025, 7, 31),
                strike=100.0, expiration=date(2025, 8, 1),
                option_type='garbage', iv_t_minus_1=0.30,
                entry_price_per_share=2.0,
                intraday_bars=_synthetic_bars(date(2025,7,31), [100.0]),
                risk_free=0.0, dividend_yield=0.0,
            )

    def test_invalid_iv(self):
        with pytest.raises(ValueError, match="iv_t_minus_1"):
            reprice_intraday_option(
                ticker='T', intraday_date=date(2025, 7, 31),
                strike=100.0, expiration=date(2025, 8, 1),
                option_type='call', iv_t_minus_1=0.0,
                entry_price_per_share=2.0,
                intraday_bars=_synthetic_bars(date(2025,7,31), [100.0]),
                risk_free=0.0, dividend_yield=0.0,
            )


class TestRepriceStructure:

    def test_long_straddle_combines_call_and_put(self):
        # ATM straddle: stock rallies. Call wins, put loses,
        # net depends on magnitudes.
        bars = _synthetic_bars(date(2025, 7, 31),
                               [100.0, 110.0, 115.0])
        tl = reprice_structure_intraday(
            structure='long_straddle', ticker='T',
            intraday_date=date(2025, 7, 31),
            intraday_bars=bars,
            atm_strike=100.0, expiration=date(2025, 8, 1),
            call_entry=2.0, put_entry=2.0,
            call_iv=0.40, put_iv=0.40,
        )
        # At spot=115 the call is worth ~15, put ~0, total ~15 vs $4 entry.
        # PnL_per_contract ≈ (15 - 4) * 100 = $1,100 ish
        assert tl['Pnl_per_contract'].iloc[-1] > 800.0
        # Per-pct against entry of $4 → about +275%
        assert tl['Pnl_pct'].iloc[-1] > 200.0

    def test_short_strangle_max_profit_when_inside_wings(self):
        # Wings at 110 and 90, spot stays at 100. Short strangle keeps
        # the collected premium.
        bars = _synthetic_bars(date(2025, 7, 31),
                               [100.0, 99.0, 101.0, 100.0])
        tl = reprice_structure_intraday(
            structure='short_strangle', ticker='T',
            intraday_date=date(2025, 7, 31),
            intraday_bars=bars,
            call_strike=110.0, put_strike=90.0,
            wing_call_entry=0.50, wing_put_entry=0.50,
            wing_call_iv=0.40, wing_put_iv=0.40,
            expiration=date(2025, 8, 1),
        )
        # At day's end with spot near 100, both wings should be worth
        # near 0 → short pnl close to the $1 collected = $100 per contract.
        # Allow modest extrinsic at end-of-day (not full intrinsic yet).
        assert tl['Pnl_per_contract'].iloc[-1] > 50.0

    def test_short_strangle_loss_when_blow_through(self):
        # Spot blows up to 130, far above the 110 call wing.
        bars = _synthetic_bars(date(2025, 7, 31),
                               [100.0, 115.0, 125.0, 130.0])
        tl = reprice_structure_intraday(
            structure='short_strangle', ticker='T',
            intraday_date=date(2025, 7, 31),
            intraday_bars=bars,
            call_strike=110.0, put_strike=90.0,
            wing_call_entry=0.50, wing_put_entry=0.50,
            wing_call_iv=0.40, wing_put_iv=0.40,
            expiration=date(2025, 8, 1),
        )
        # Call wing now intrinsic $20, you'd buy back at $20 against $0.50
        # collected → big loss. PnL_per_contract negative and large.
        assert tl['Pnl_per_contract'].iloc[-1] < -1000.0


class TestCombineLegs:
    def test_two_long_legs_pnl_sums(self):
        leg1 = pd.DataFrame({
            'Time': pd.to_datetime(['2025-07-31 09:30', '2025-07-31 10:00']),
            'Spot': [100.0, 105.0],
            'Pnl_per_share': [0.5, 3.0]})
        leg2 = pd.DataFrame({
            'Time': pd.to_datetime(['2025-07-31 09:30', '2025-07-31 10:00']),
            'Spot': [100.0, 105.0],
            'Pnl_per_share': [-1.0, -1.5]})
        out = _combine_legs([leg1, leg2], signs=[1.0, 1.0], entry=4.0)
        assert out['Pnl_per_share'].tolist() == [-0.5, 1.5]
        assert out['Pnl_per_contract'].tolist() == [-50.0, 150.0]
        # Pnl_pct = pnl_per_share / entry * 100 = -12.5, 37.5
        assert out['Pnl_pct'].tolist() == [-12.5, 37.5]

    def test_short_position_flips_sign(self):
        leg1 = pd.DataFrame({
            'Time': pd.to_datetime(['2025-07-31 09:30']),
            'Spot': [100.0],
            'Pnl_per_share': [-5.0]})  # Long leg lost $5
        out = _combine_legs([leg1], signs=[-1.0], entry=0.5)
        # Short equivalent: +$5
        assert out['Pnl_per_share'].iloc[0] == 5.0


class TestIntradayThetaDecay:
    """The empirical 0DTE theta-decay curve g(t) and its helpers."""

    def test_cumulative_endpoints_and_clamping(self):
        # g(open)=0, g(close)=1; saturates outside the session.
        assert cumulative_theta_decay(0) == pytest.approx(0.0)
        assert cumulative_theta_decay(390) == pytest.approx(1.0)
        assert cumulative_theta_decay(-60) == pytest.approx(0.0)   # pre-open
        assert cumulative_theta_decay(600) == pytest.approx(1.0)   # post-close

    def test_cumulative_monotonic_non_decreasing(self):
        # Cumulative decay can never run backwards.
        xs = list(range(0, 391, 5))
        gs = [cumulative_theta_decay(x) for x in xs]
        assert all(b >= a - 1e-9 for a, b in zip(gs, gs[1:]))

    def test_full_day_fraction_is_one(self):
        # Magnitude-preserving: a full RTH hold returns the whole daily budget.
        assert intraday_theta_decay_fraction(0, 390) == pytest.approx(1.0)

    def test_fraction_is_additive(self):
        # frac(a,c) == frac(a,b) + frac(b,c) since it is g(c) - g(a).
        whole = intraday_theta_decay_fraction(30, 300)
        split = (intraday_theta_decay_fraction(30, 180)
                 + intraday_theta_decay_fraction(180, 300))
        assert whole == pytest.approx(split, abs=1e-9)

    def test_non_positive_window_is_zero(self):
        assert intraday_theta_decay_fraction(120, 120) == 0.0
        assert intraday_theta_decay_fraction(200, 100) == 0.0

    def test_morning_decays_faster_than_linear(self):
        # Open IV crush → first hour loses more than its time share.
        linear = 60 / 390.0
        assert intraday_theta_decay_fraction(0, 60) > linear

    def test_midday_is_a_lull_below_linear(self):
        # The empirical curve falls below linear midday (≈12:00–15:00):
        # by 1:30pm (240 min) less than the linear 240/390 has decayed.
        assert cumulative_theta_decay(240) < 240 / 390.0

    def test_terminal_cliff_carries_outsized_decay(self):
        # ~0.80 decayed by the last observed bar (~15:55); the final minutes
        # into expiry carry the remaining ~0.20 — far steeper than any
        # equal-length midday window.
        assert cumulative_theta_decay(385) < 0.85
        last_5min = intraday_theta_decay_fraction(385, 390)
        midday_5min = intraday_theta_decay_fraction(180, 185)
        assert last_5min > 10 * midday_5min

    def test_minutes_from_rth_open_naive(self):
        assert minutes_from_rth_open(datetime(2025, 7, 31, 9, 30)) == 0.0
        assert minutes_from_rth_open(datetime(2025, 7, 31, 10, 30)) == 60.0
        assert minutes_from_rth_open(datetime(2025, 7, 31, 16, 0)) == 390.0

    def test_minutes_from_rth_open_tz_aware_converts_to_eastern(self):
        # 14:30 UTC == 10:30 EDT == 60 min after the open.
        ts = pd.Timestamp("2025-07-31 14:30", tz="UTC")
        assert minutes_from_rth_open(ts) == pytest.approx(60.0)

    def test_minutes_from_rth_open_null_inputs_return_none(self):
        assert minutes_from_rth_open(None) is None
        assert minutes_from_rth_open(pd.NaT) is None
        assert minutes_from_rth_open("not-a-time") is None
