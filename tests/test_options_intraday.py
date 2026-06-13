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
    DATA_SOURCE_EMPIRICAL_FALLBACK,
    DATA_SOURCE_REALTIME,
    _bsm_price_vec,
    _combine_legs,
    _interpolate_observed_iv,
    load_realtime_theta_curve,
    reprice_intraday_option,
    reprice_structure_intraday,
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
            'Pnl_per_share', 'Pnl_per_contract', 'Pnl_pct', 'data_source']

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


# ──────────────────────────────────────────────────────────────────────
# Track 2 phase 2a — realtime-observed IV path with empirical fallback
# ──────────────────────────────────────────────────────────────────────

def _realtime_snapshots(intraday_date: date, ivs: list[float],
                        snap_minutes: list[int] | None = None) -> pd.DataFrame:
    """Build a synthetic REALTIME observations DataFrame.

    Mirrors the column shape returned by ``load_realtime_theta_curve``:
    snapshot_ts, implied_volatility, delta, gamma, theta, vega, mark.
    """
    if snap_minutes is None:
        # Default: 5-min cadence from RTH open
        snap_minutes = [9*60 + 30 + 5*i for i in range(len(ivs))]
    assert len(snap_minutes) == len(ivs)
    return pd.DataFrame({
        'snapshot_ts': [
            datetime.combine(intraday_date, datetime.min.time())
            + timedelta(minutes=m)
            for m in snap_minutes
        ],
        'implied_volatility': ivs,
        'delta': [0.5] * len(ivs),
        'gamma': [0.02] * len(ivs),
        'theta': [-0.10] * len(ivs),
        'vega':  [0.20] * len(ivs),
        'mark':  [2.0]  * len(ivs),
    })


class TestLoadRealtimeThetaCurve:
    """The DB loader is dependency-injected so tests are hermetic."""

    def test_returns_dataframe_when_snapshots_exist(self):
        captured = {}

        def fake_query(sql, params):
            captured['sql'] = sql
            captured['params'] = params
            return _realtime_snapshots(date(2026, 5, 22), [0.30, 0.25, 0.20])

        out = load_realtime_theta_curve(
            ticker='spy', intraday_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='call', query_fn=fake_query,
        )
        assert out is not None
        assert len(out) == 3
        # Normalises option_type 'call' → 'calls' for the schema
        assert captured['params']['ot'] == 'calls'
        assert captured['params']['ticker'] == 'SPY'
        assert captured['params']['strike'] == 500.0
        assert "market_session = 'REALTIME'" in captured['sql']

    def test_normalises_put_option_type(self):
        captured = {}

        def fake_query(sql, params):
            captured['params'] = params
            return _realtime_snapshots(date(2026, 5, 22), [0.30])

        load_realtime_theta_curve(
            ticker='SPY', intraday_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='put', query_fn=fake_query,
        )
        assert captured['params']['ot'] == 'puts'

    def test_returns_none_on_empty_response(self):
        out = load_realtime_theta_curve(
            ticker='SPY', intraday_date=date(2020, 1, 2),
            expiration=date(2020, 1, 3), strike=300.0,
            option_type='call',
            query_fn=lambda sql, params: pd.DataFrame(),
        )
        assert out is None

    def test_returns_none_when_all_iv_are_nan(self):
        """If every observation has NaN IV, we can't anchor a path —
        better to fall back than to interpolate over a no-op series."""
        df = _realtime_snapshots(date(2026, 5, 22), [0.30])
        df['implied_volatility'] = float('nan')
        out = load_realtime_theta_curve(
            ticker='SPY', intraday_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='call',
            query_fn=lambda sql, params: df,
        )
        assert out is None

    def test_drops_rows_with_partial_nan_iv(self):
        df = _realtime_snapshots(date(2026, 5, 22), [0.30, float('nan'), 0.20])
        out = load_realtime_theta_curve(
            ticker='SPY', intraday_date=date(2026, 5, 22),
            expiration=date(2026, 5, 22), strike=500.0,
            option_type='call',
            query_fn=lambda sql, params: df,
        )
        assert out is not None
        # NaN row dropped; observed IV values kept in order
        assert out['implied_volatility'].tolist() == [0.30, 0.20]


class TestInterpolateObservedIv:

    def test_linear_interpolation_between_snapshots(self):
        d = date(2026, 5, 22)
        rt = _realtime_snapshots(d, [0.50, 0.40], snap_minutes=[9*60+30, 9*60+40])
        bars = _synthetic_bars(d, [100.0] * 11)  # 9:30 through 9:40
        iv = _interpolate_observed_iv(rt, bars['Time'])
        # First bar = first snapshot IV, last bar = last snapshot IV
        assert iv[0] == pytest.approx(0.50, abs=1e-9)
        assert iv[-1] == pytest.approx(0.40, abs=1e-9)
        # Midpoint should be halfway
        assert iv[5] == pytest.approx(0.45, abs=0.01)

    def test_edge_clamp_before_first_and_after_last(self):
        d = date(2026, 5, 22)
        rt = _realtime_snapshots(d, [0.30], snap_minutes=[9*60+45])
        bars = _synthetic_bars(d, [100.0] * 60)  # 9:30 through 10:29
        iv = _interpolate_observed_iv(rt, bars['Time'])
        # Single observation → flat IV at the observed value (every bar)
        assert iv == pytest.approx(np.full_like(iv, 0.30), abs=1e-9)


class TestRealtimePathInReprice:
    """Integration: reprice_intraday_option consumes realtime data."""

    def test_realtime_path_tags_data_source(self):
        d = date(2026, 5, 22)
        rt = _realtime_snapshots(d, [0.30, 0.28, 0.25],
                                 snap_minutes=[9*60+30, 9*60+35, 9*60+40])
        bars = _synthetic_bars(d, [100.0] * 11)
        tl = reprice_intraday_option(
            ticker='SPY', intraday_date=d, strike=100.0,
            expiration=date(2026, 5, 23), option_type='call',
            iv_t_minus_1=0.60,  # would be the empirical anchor; observed wins
            entry_price_per_share=2.0,
            intraday_bars=bars,
            realtime_iv_path=rt,
            risk_free=0.0, dividend_yield=0.0,
        )
        # Every row tagged 'realtime'
        assert (tl['data_source'] == DATA_SOURCE_REALTIME).all()
        # IV path follows observed snapshots, not 0.60 * (0.55..0.40)
        assert tl['IV_used'].iloc[0] == pytest.approx(0.30, abs=1e-9)
        assert tl['IV_used'].iloc[-1] == pytest.approx(0.25, abs=1e-9)

    def test_empirical_fallback_when_no_realtime_data(self):
        d = date(2020, 7, 31)  # Pre-Track-0 date — no realtime data
        bars = _synthetic_bars(d, [100.0] * 5)
        tl = reprice_intraday_option(
            ticker='SPY', intraday_date=d, strike=100.0,
            expiration=date(2020, 8, 1), option_type='call',
            iv_t_minus_1=0.60,
            entry_price_per_share=2.0,
            intraday_bars=bars,
            realtime_iv_path=None,        # explicitly no realtime
            use_realtime=False,           # short-circuit the loader
            iv_open_multiplier=0.55, iv_close_multiplier=0.40,
            risk_free=0.0, dividend_yield=0.0,
        )
        assert (tl['data_source'] == DATA_SOURCE_EMPIRICAL_FALLBACK).all()
        # Empirical curve: open=0.60*0.55=0.33, close=0.60*0.40=0.24
        assert tl['IV_used'].iloc[0] == pytest.approx(0.33, abs=1e-9)
        assert tl['IV_used'].iloc[-1] == pytest.approx(0.24, abs=1e-9)

    def test_shape_parity_between_realtime_and_fallback(self):
        """Both branches must return the same column set so downstream
        code can consume either without conditional schema handling."""
        d = date(2026, 5, 22)
        bars = _synthetic_bars(d, [100.0] * 3)
        rt = _realtime_snapshots(d, [0.30, 0.25],
                                 snap_minutes=[9*60+30, 9*60+32])
        tl_realtime = reprice_intraday_option(
            ticker='SPY', intraday_date=d, strike=100.0,
            expiration=date(2026, 5, 23), option_type='call',
            iv_t_minus_1=0.60, entry_price_per_share=2.0,
            intraday_bars=bars, realtime_iv_path=rt,
            risk_free=0.0, dividend_yield=0.0,
        )
        tl_fallback = reprice_intraday_option(
            ticker='SPY', intraday_date=d, strike=100.0,
            expiration=date(2026, 5, 23), option_type='call',
            iv_t_minus_1=0.60, entry_price_per_share=2.0,
            intraday_bars=bars, use_realtime=False,
            risk_free=0.0, dividend_yield=0.0,
        )
        assert list(tl_realtime.columns) == list(tl_fallback.columns)
        assert len(tl_realtime) == len(tl_fallback)

    def test_loader_called_when_realtime_not_preloaded(self, monkeypatch):
        """Repricer pulls from load_realtime_theta_curve when caller
        doesn't pre-supply it."""
        d = date(2026, 5, 22)
        rt = _realtime_snapshots(d, [0.30],
                                 snap_minutes=[9*60+30])
        calls = []

        def fake_loader(**kwargs):
            calls.append(kwargs)
            return rt

        monkeypatch.setattr(
            'lib.options_intraday.load_realtime_theta_curve', fake_loader)

        bars = _synthetic_bars(d, [100.0] * 2)
        tl = reprice_intraday_option(
            ticker='SPY', intraday_date=d, strike=100.0,
            expiration=date(2026, 5, 23), option_type='call',
            iv_t_minus_1=0.60, entry_price_per_share=2.0,
            intraday_bars=bars,
            risk_free=0.0, dividend_yield=0.0,
        )
        assert len(calls) == 1
        assert calls[0]['ticker'] == 'SPY'
        assert calls[0]['option_type'] == 'call'
        assert (tl['data_source'] == DATA_SOURCE_REALTIME).all()


class TestStructureDataSourcePropagation:
    """Structure-level data_source aggregates conservatively: realtime
    only if ALL legs were realtime; otherwise fallback."""

    def test_both_legs_realtime_yields_realtime_structure(self):
        d = date(2026, 5, 22)
        bars = _synthetic_bars(d, [100.0, 102.0, 105.0])
        rt = _realtime_snapshots(d, [0.30, 0.28, 0.25],
                                 snap_minutes=[9*60+30, 9*60+31, 9*60+32])
        # Pre-supply realtime to both legs by patching the loader
        import lib.options_intraday as oi
        original = oi.load_realtime_theta_curve
        oi.load_realtime_theta_curve = lambda **kw: rt
        try:
            tl = reprice_structure_intraday(
                structure='long_straddle', ticker='SPY',
                intraday_date=d, intraday_bars=bars,
                atm_strike=100.0, expiration=date(2026, 5, 23),
                call_entry=2.0, put_entry=2.0,
                call_iv=0.40, put_iv=0.40,
            )
        finally:
            oi.load_realtime_theta_curve = original
        assert (tl['data_source'] == DATA_SOURCE_REALTIME).all()

    def test_no_legs_realtime_yields_fallback_structure(self):
        d = date(2020, 7, 31)
        bars = _synthetic_bars(d, [100.0, 102.0, 105.0])
        import lib.options_intraday as oi
        original = oi.load_realtime_theta_curve
        oi.load_realtime_theta_curve = lambda **kw: None  # No data ever
        try:
            tl = reprice_structure_intraday(
                structure='long_straddle', ticker='SPY',
                intraday_date=d, intraday_bars=bars,
                atm_strike=100.0, expiration=date(2020, 8, 1),
                call_entry=2.0, put_entry=2.0,
                call_iv=0.40, put_iv=0.40,
            )
        finally:
            oi.load_realtime_theta_curve = original
        assert (tl['data_source'] == DATA_SOURCE_EMPIRICAL_FALLBACK).all()
