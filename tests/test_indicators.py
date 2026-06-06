"""Tests for lib/indicators.py — consolidated indicator functions."""

import pandas as pd
import numpy as np
import pytest
from lib.indicators import (
    wilder_moving_average,
    calculate_rsi,
    calculate_atr,
    calculate_ema,
    calculate_vwap,
    calculate_rvol,
    calculate_obv,
    calculate_stoch_rsi,
    calculate_bollinger_bands,
    calculate_macd,
    calculate_consecutive_moves,
    calculate_historical_levels,
    add_all_indicators,
    add_signal_indicators,
    add_brief_indicators,
    select_features,
    FEATURE_GROUPS,
)


# Pinned snapshot of the 83 indicator columns add_all_indicators emits (beyond
# the 6 OHLCV/Time source columns) under the default IndicatorConfig. This is
# the byte-identical contract ~25 callers + an in-flight backfill depend on; if
# this list changes, the change to add_all_indicators was NOT a pure refactor.
_PINNED_ADD_ALL_COLUMNS = {
    'ATR14', 'ATR20', 'ATR_Expansion', 'BB_Lower', 'BB_Middle', 'BB_Pct',
    'BB_Squeeze', 'BB_Upper', 'BB_Width', 'Close_vs_Range', 'Consecutive_Down',
    'Consecutive_Down_5', 'Consecutive_Up', 'Consecutive_Up_5', 'Daily_Range',
    'Daily_Range_Pct', 'EMA20', 'EMA50', 'EMA9', 'EMA9_Slope', 'EMA_Spread_ATR',
    'MACD', 'MACD_Histogram', 'MACD_Signal', 'Mins_Since_Open', 'OBV',
    'ORB_15m_Broke_High', 'ORB_15m_Broke_Low', 'ORB_15m_Distance', 'ORB_15m_High',
    'ORB_15m_High_Pct', 'ORB_15m_Low', 'ORB_15m_Low_Pct', 'ORB_15m_Mid',
    'ORB_15m_Mid_Pct', 'ORB_15m_Range', 'ORB_15m_Trend', 'ORB_15m_Within_Range',
    'ORB_30m_Broke_High', 'ORB_30m_Broke_Low', 'ORB_30m_Distance', 'ORB_30m_High',
    'ORB_30m_High_Pct', 'ORB_30m_Low', 'ORB_30m_Low_Pct', 'ORB_30m_Mid',
    'ORB_30m_Mid_Pct', 'ORB_30m_Range', 'ORB_30m_Trend', 'ORB_30m_Within_Range',
    'ORB_5m_Broke_High', 'ORB_5m_Broke_Low', 'ORB_5m_Distance', 'ORB_5m_High',
    'ORB_5m_High_Pct', 'ORB_5m_Low', 'ORB_5m_Low_Pct', 'ORB_5m_Mid',
    'ORB_5m_Mid_Pct', 'ORB_5m_Range', 'ORB_5m_Trend', 'ORB_5m_Within_Range',
    'Price_Change', 'Price_vs_EMA20', 'Price_vs_EMA20_ATR', 'Price_vs_EMA9',
    'Price_vs_EMA9_ATR', 'Price_vs_VWAP', 'Price_vs_VWAP_ATR', 'RSI14', 'RSI30',
    'RSI9', 'RSI_Divergence', 'RSI_Thrust_3', 'RVOL', 'RVol_Recent_20',
    'Realized_Vol_Short', 'SMA10', 'SMA20', 'SMA200', 'SMA5', 'SMA50',
    'StochRSI_D', 'StochRSI_K', 'VWAP',
    # Added on main (merged 2026-05-31): snake_case SQL-writer aliases +
    # annualised historical volatility periods.
    'high_low_spread', 'high_low_spread_pct', 'volatility_5d', 'volatility_20d',
    # Magnitude-engine volatility-expansion block (migrated 2026-06-01 from the
    # inline mag_dataset._add_phase1_features). Intraday-only / Time-gated.
    'BB20_Bandwidth', 'Realized_Vol_Z', 'Range_Expansion_Ratio',
    'Intraday_Range_vs_PrevDay',
}
_SOURCE_COLUMNS = {'Time', 'Open', 'High', 'Low', 'Close', 'Volume'}


def _two_session_ohlcv(seed=42, n_per=120):
    """Two RTH sessions of 1-min bars WITH a Time column (so VWAP/ORB fire)."""
    rng = np.random.default_rng(seed)
    frames = []
    for i, day in enumerate(['2024-01-02', '2024-01-03']):
        steps = rng.normal(0, 0.0008, n_per)
        close = 200.0 * np.exp(np.cumsum(steps))
        high = close * (1 + np.abs(rng.normal(0, 0.0005, n_per)))
        low = close * (1 - np.abs(rng.normal(0, 0.0005, n_per)))
        open_ = close * (1 + rng.normal(0, 0.0003, n_per))
        vol = rng.integers(1_000, 50_000, n_per).astype(float)
        times = pd.date_range(f'{day} 09:30', periods=n_per, freq='1min')
        frames.append(pd.DataFrame(
            {'Time': times, 'Open': open_, 'High': high, 'Low': low,
             'Close': close, 'Volume': vol}, index=times))
    return pd.concat(frames)


class TestFeatureTiering:
    """Pure-refactor parity + leanness contract for the capability tiers."""

    def test_add_all_indicators_column_set_unchanged(self):
        df = _two_session_ohlcv()
        out = add_all_indicators(df)
        new = set(out.columns) - _SOURCE_COLUMNS
        assert new == _PINNED_ADD_ALL_COLUMNS, (
            "add_all_indicators output changed — refactor was not byte-identical.\n"
            f"  added: {sorted(new - _PINNED_ADD_ALL_COLUMNS)}\n"
            f"  removed: {sorted(_PINNED_ADD_ALL_COLUMNS - new)}"
        )
        # 6 source + 93 indicators = 99 total. +4 over the post-merge 95 from
        # the 2026-06-01 magnitude block (BB20_Bandwidth, Realized_Vol_Z,
        # Range_Expansion_Ratio, Intraday_Range_vs_PrevDay).
        assert len(out.columns) == len(_SOURCE_COLUMNS) + len(_PINNED_ADD_ALL_COLUMNS) == 99

    def test_feature_groups_keys_and_membership(self):
        assert set(FEATURE_GROUPS) == {'signal', 'brief', 'regime', 'strat', 'magnitude'}
        # Every signal/brief/magnitude column is a real add_all_indicators output.
        for cap in ('signal', 'brief', 'magnitude'):
            for col in FEATURE_GROUPS[cap]:
                assert col in _PINNED_ADD_ALL_COLUMNS, f"{cap} col {col} not produced"

    def test_magnitude_block_matches_inline_reference(self):
        """The 4 migrated magnitude features must equal the old inline
        mag_dataset._add_phase1_features math at 0.0 max-abs-diff. This pins the
        migration as a pure move (no silent behaviour change for the magnitude
        engine), the same parity contract the signal/brief tiers carry."""
        df = _two_session_ohlcv(seed=5)
        out = add_all_indicators(df)
        d = out.copy()
        sess = pd.to_datetime(d['Time']).dt.date
        h, l, c = d['High'], d['Low'], d['Close']
        prev_c = c.groupby(sess).shift(1)
        # BB20 bandwidth
        bb_ref = np.where(c.notna() & (c != 0),
                          (d['BB_Upper'] - d['BB_Lower']) / c, np.nan)
        # Realized-vol z (15/60, session-grouped)
        logret = np.log(c / prev_c)
        rv15 = logret.groupby(sess).rolling(15).std().reset_index(level=0, drop=True)
        rv_mu = rv15.groupby(sess).rolling(60).mean().reset_index(level=0, drop=True)
        rv_sd = rv15.groupby(sess).rolling(60).std().reset_index(level=0, drop=True)
        rvz_ref = np.where(rv_sd.notna() & (rv_sd > 0), (rv15 - rv_mu) / rv_sd, np.nan)
        # Range expansion (prior-5 mean, session-grouped)
        rng = h - l
        avg5 = (rng.groupby(sess).shift(1).groupby(sess).rolling(5).mean()
                   .reset_index(level=0, drop=True))
        rer_ref = np.where(avg5.notna() & (avg5 > 0), rng / avg5, np.nan)
        for col, ref in [('BB20_Bandwidth', bb_ref),
                         ('Realized_Vol_Z', rvz_ref),
                         ('Range_Expansion_Ratio', rer_ref)]:
            np.testing.assert_allclose(
                out[col].to_numpy(dtype=float), np.asarray(ref, dtype=float),
                equal_nan=True, atol=0.0, err_msg=f"magnitude parity broke on {col}")

    def test_magnitude_features_time_gated(self):
        """Magnitude block is intraday-only — absent without a Time column."""
        n = 60
        close = pd.Series(np.linspace(100, 105, n))
        df = pd.DataFrame({'Open': close * 0.999, 'High': close * 1.001,
                           'Low': close * 0.998, 'Close': close,
                           'Volume': np.full(n, 1e4)})
        out = add_all_indicators(df)
        for col in ('BB20_Bandwidth', 'Realized_Vol_Z', 'Range_Expansion_Ratio',
                    'Intraday_Range_vs_PrevDay'):
            assert col not in out.columns, f"{col} should be Time-gated out"

    def test_signal_tier_parity_zero_diff(self):
        df = _two_session_ohlcv(seed=7)
        full = add_all_indicators(df)
        lean = add_signal_indicators(df)
        for col in FEATURE_GROUPS['signal']:
            assert col in lean.columns, f"signal tier missing {col}"
            np.testing.assert_allclose(
                lean[col].to_numpy(dtype=float),
                full[col].to_numpy(dtype=float),
                equal_nan=True, atol=0.0,
                err_msg=f"signal-tier parity broke on {col}")

    def test_brief_tier_parity_zero_diff(self):
        df = _two_session_ohlcv(seed=9)
        full = add_all_indicators(df)
        lean = add_brief_indicators(df)
        for col in FEATURE_GROUPS['brief']:
            assert col in lean.columns, f"brief tier missing {col}"
            np.testing.assert_allclose(
                lean[col].to_numpy(dtype=float),
                full[col].to_numpy(dtype=float),
                equal_nan=True, atol=0.0,
                err_msg=f"brief-tier parity broke on {col}")

    def test_signal_tier_is_lean(self):
        """Proves the lean path skips the heavy ORB / SMA blocks."""
        df = _two_session_ohlcv()
        lean = add_signal_indicators(df)
        assert not any(c.startswith('ORB_') for c in lean.columns)
        assert not any(c.startswith('SMA') for c in lean.columns)
        # promoted-regime + bollinger blocks skipped too
        assert 'BB_Upper' not in lean.columns
        assert 'Realized_Vol_Short' not in lean.columns

    def test_brief_tier_is_lean(self):
        df = _two_session_ohlcv()
        lean = add_brief_indicators(df)
        # Skips the heavy ORB / promoted-regime blocks and the unread RVOL/OBV.
        assert not any(c.startswith('ORB_') for c in lean.columns)
        assert 'Realized_Vol_Short' not in lean.columns
        assert 'RVOL' not in lean.columns
        assert 'OBV' not in lean.columns
        # But VWAP + Price_vs_VWAP MUST be produced: check_call/put_conditions
        # score on Price_vs_VWAP, so dropping these silently changes the brief's
        # published signal_status (regression caught in review 2026-05-31).
        assert 'VWAP' in lean.columns
        assert 'Price_vs_VWAP' in lean.columns

    def test_brief_tier_matches_full_on_daily_sql_passthrough(self):
        """Daily Cloud-SQL frames arrive WITH a pre-existing intraday
        ``Price_vs_VWAP`` column AND a Time column. The brief must treat that
        frame byte-identically to add_all_indicators: because Time is present,
        both recompute a degenerate daily VWAP and OVERWRITE the inbound
        price_vs_vwap. If add_brief_indicators skipped the VWAP/price-levels
        blocks, the stale SQL value would survive and flip the brief's
        below_vwap/above_vwap scoring. This is the case the intraday parity
        fixture did not cover."""
        n = 40
        rng = np.random.RandomState(3)
        close = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, n)))
        df = pd.DataFrame({
            'Time': pd.date_range('2026-04-01', periods=n, freq='D'),
            'Open': close.shift(1).fillna(close.iloc[0]),
            'High': close + 0.5, 'Low': close - 0.5, 'Close': close,
            'Volume': rng.randint(1e6, 5e6, n).astype(float),
            # Pre-existing intraday-session value from SQL (alias of price_vs_vwap).
            'Price_vs_VWAP': rng.normal(-1.0, 0.5, n),
        })
        full = add_all_indicators(df.copy(), close_col='Close')
        brief = add_brief_indicators(df.copy(), close_col='Close')
        # Both must overwrite the inbound Price_vs_VWAP with the daily recompute,
        # to the exact same values — no stale-SQL passthrough divergence.
        np.testing.assert_allclose(
            pd.to_numeric(brief['Price_vs_VWAP'], errors='coerce').to_numpy(),
            pd.to_numeric(full['Price_vs_VWAP'], errors='coerce').to_numpy(),
            equal_nan=True, atol=0.0,
            err_msg='brief diverged from full engine on daily-SQL Price_vs_VWAP',
        )

    def test_select_features_tolerates_time_gated_absence(self):
        """No Time → VWAP absent; select_features must not KeyError."""
        n = 60
        close = pd.Series(np.linspace(100, 105, n))
        df = pd.DataFrame({
            'Open': close * 0.999, 'High': close * 1.001, 'Low': close * 0.998,
            'Close': close,
            'Volume': np.random.RandomState(0).randint(1e3, 1e4, n).astype(float),
        })
        lean = add_signal_indicators(df)
        sel = select_features(lean, 'signal')
        assert 'VWAP' not in sel.columns       # Time-gated, legitimately absent
        assert 'RSI14' in sel.columns
        with pytest.raises(KeyError):
            select_features(lean, 'nonsense')


class TestWilderMA:
    def test_basic_smoothing(self):
        values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = wilder_moving_average(values, 3)
        assert len(result) == 5
        assert not result.isna().all()

    def test_constant_input(self):
        values = pd.Series([5.0] * 20)
        result = wilder_moving_average(values, 14)
        # Constant input should converge to the constant
        assert abs(result.iloc[-1] - 5.0) < 0.01


class TestRSI:
    def test_output_range(self, sample_ohlcv):
        rsi = calculate_rsi(sample_ohlcv['Close'], 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_overbought_on_up_trend(self):
        prices = pd.Series(range(100, 150))  # Steady uptrend
        rsi = calculate_rsi(prices.astype(float), 14)
        assert rsi.iloc[-1] > 70  # Should be overbought

    def test_oversold_on_down_trend(self):
        prices = pd.Series(range(150, 100, -1))  # Steady downtrend
        rsi = calculate_rsi(prices.astype(float), 14)
        assert rsi.iloc[-1] < 30  # Should be oversold


class TestATR:
    def test_non_negative(self, sample_ohlcv):
        atr = calculate_atr(
            sample_ohlcv['High'], sample_ohlcv['Low'], sample_ohlcv['Close'], 14,
        )
        assert (atr.dropna() >= 0).all()

    def test_zero_range(self):
        n = 20
        flat = pd.Series([100.0] * n)
        atr = calculate_atr(flat, flat, flat, 14)
        assert atr.iloc[-1] == pytest.approx(0.0, abs=0.01)


class TestEMA:
    def test_basic(self):
        prices = pd.Series([1, 2, 3, 4, 5], dtype=float)
        ema = calculate_ema(prices, 3)
        assert len(ema) == 5
        # EMA should be between min and max
        assert ema.iloc[-1] >= 1 and ema.iloc[-1] <= 5


class TestVWAP:
    def test_single_day(self, sample_ohlcv):
        dates = pd.to_datetime(sample_ohlcv['Time']).dt.date
        vwap = calculate_vwap(
            sample_ohlcv['High'], sample_ohlcv['Low'],
            sample_ohlcv['Close'], sample_ohlcv['Volume'], dates,
        )
        assert len(vwap) == len(sample_ohlcv)
        # VWAP should be between high and low
        assert vwap.iloc[-1] >= sample_ohlcv['Low'].min()
        assert vwap.iloc[-1] <= sample_ohlcv['High'].max()


class TestRVOL:
    def test_basic(self, sample_ohlcv):
        rvol = calculate_rvol(sample_ohlcv['Volume'], 20)
        assert len(rvol) == len(sample_ohlcv)
        valid = rvol.dropna()
        assert (valid > 0).all()


class TestOBV:
    def test_basic(self, sample_ohlcv):
        obv = calculate_obv(sample_ohlcv['Close'], sample_ohlcv['Volume'])
        assert len(obv) == len(sample_ohlcv)

    def test_rising_prices_positive_obv(self):
        close = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])
        volume = pd.Series([1000.0] * 5)
        obv = calculate_obv(close, volume)
        assert obv.iloc[-1] > 0


class TestStochRSI:
    def test_output_range(self, sample_ohlcv):
        rsi = calculate_rsi(sample_ohlcv['Close'], 14)
        k, d = calculate_stoch_rsi(rsi)
        valid_k = k.dropna()
        valid_d = d.dropna()
        assert (valid_k >= 0).all() and (valid_k <= 100).all()
        assert (valid_d >= 0).all() and (valid_d <= 100).all()


class TestBollingerBands:
    def test_ordering(self, sample_ohlcv):
        upper, middle, lower = calculate_bollinger_bands(sample_ohlcv['Close'])
        valid = ~(upper.isna() | middle.isna() | lower.isna())
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()


class TestMACD:
    def test_histogram_is_difference(self, sample_ohlcv):
        macd, signal, hist = calculate_macd(sample_ohlcv['Close'])
        diff = macd - signal
        np.testing.assert_array_almost_equal(hist.values, diff.values, decimal=10)


class TestConsecutiveMoves:
    def test_basic(self):
        changes = pd.Series([1.0, 1.0, 1.0, -1.0, -1.0, -1.0])
        up, down = calculate_consecutive_moves(changes, 3)
        assert up.iloc[2] == 3  # 3 consecutive up
        assert down.iloc[5] == 3  # 3 consecutive down


class TestAddAllIndicators:
    def test_adds_columns(self, sample_ohlcv):
        result = add_all_indicators(sample_ohlcv)
        assert 'RSI14' in result.columns
        assert 'EMA9' in result.columns
        assert 'ATR14' in result.columns
        assert 'VWAP' in result.columns
        assert 'RVOL' in result.columns
        assert 'OBV' in result.columns
        assert 'StochRSI_K' in result.columns
        assert 'BB_Upper' in result.columns
        assert 'MACD' in result.columns
        assert 'Consecutive_Up' in result.columns

    def test_emits_secondary_atr_rsi_volatility_and_spread(self, sample_ohlcv):
        """Regression guard for the 2026-05-27 silent-NaN fix:
        ATR20, RSI30, volatility_5d, volatility_20d, high_low_spread,
        and high_low_spread_pct must be produced by default. Pre-fix,
        each was declared in market_data_daily but never computed —
        every row shipped NaN in those columns.
        """
        result = add_all_indicators(sample_ohlcv)
        for col in (
            'ATR20', 'RSI30',
            'volatility_5d', 'volatility_20d',
            'high_low_spread', 'high_low_spread_pct',
        ):
            assert col in result.columns, f"{col} missing from add_all_indicators output"
            # At least one non-NaN value must exist on a >20-bar sample.
            assert result[col].notna().any(), f"{col} is all-NaN — computation never ran"

    def test_daily_indicator_to_sql_column_covers_new_cols(self, sample_ohlcv):
        """Every key in DAILY_INDICATOR_TO_SQL_COLUMN must resolve to a
        real column in add_all_indicators output. Pre-fix, ATR20/RSI30/
        volatility_5d/high_low_spread{,_pct} keys were missing, so the
        SQL columns shipped NaN. This test pins the mapping ↔ producer
        contract so a future rename can't silently break it.
        """
        from gcp.database import DAILY_INDICATOR_TO_SQL_COLUMN
        result = add_all_indicators(sample_ohlcv)
        missing = [src for src in DAILY_INDICATOR_TO_SQL_COLUMN
                   if src not in result.columns]
        assert not missing, (
            f"DAILY_INDICATOR_TO_SQL_COLUMN references columns not produced "
            f"by add_all_indicators: {missing}"
        )

    def test_orb_columns_present_when_time_exists(self, sample_ohlcv):
        """add_all_indicators should produce ORB columns when Time column exists."""
        result = add_all_indicators(sample_ohlcv)
        # Default orb_windows are 5m, 15m, 30m
        for label in ['5m', '15m', '30m']:
            assert f'ORB_{label}_High' in result.columns, f"Missing ORB_{label}_High"
            assert f'ORB_{label}_Low' in result.columns, f"Missing ORB_{label}_Low"
            assert f'ORB_{label}_Trend' in result.columns, f"Missing ORB_{label}_Trend"
            assert f'ORB_{label}_Range' in result.columns, f"Missing ORB_{label}_Range"
            assert f'ORB_{label}_Mid' in result.columns, f"Missing ORB_{label}_Mid"

    def test_orb_columns_absent_without_time(self):
        """If the DataFrame has no Time column, ORB columns should not appear."""
        np.random.seed(42)
        n = 50
        close = pd.Series(np.linspace(100, 105, n))
        df = pd.DataFrame({
            'Open': close * 0.999,
            'High': close * 1.001,
            'Low': close * 0.998,
            'Close': close,
            'Volume': np.random.randint(1000, 10000, n).astype(float),
        })
        result = add_all_indicators(df)
        assert 'ORB_5m_High' not in result.columns
        assert 'ORB_5m_Trend' not in result.columns

    def test_orb_trend_values_valid(self, sample_ohlcv):
        """ORB Trend column should contain only -1, 0, or 1."""
        result = add_all_indicators(sample_ohlcv)
        trend_col = 'ORB_5m_Trend'
        assert trend_col in result.columns
        valid_values = {-1, 0, 1}
        actual_values = set(result[trend_col].dropna().unique().astype(int))
        assert actual_values.issubset(valid_values), (
            f"ORB_5m_Trend contains unexpected values: {actual_values - valid_values}"
        )

    # ── Promoted volatility-regime / momentum-velocity features (2026-05-31) ──
    def test_promoted_features_present(self, sample_ohlcv):
        result = add_all_indicators(sample_ohlcv)
        for col in ['Realized_Vol_Short', 'Mins_Since_Open', 'Price_vs_EMA9_ATR',
                    'Price_vs_EMA20_ATR', 'Price_vs_VWAP_ATR', 'EMA_Spread_ATR',
                    'EMA9_Slope', 'BB_Squeeze', 'RSI_Divergence']:
            assert col in result.columns, f"promoted feature missing: {col}"

    def test_mins_since_open_first_rth_bar_is_zero(self, sample_ohlcv):
        result = add_all_indicators(sample_ohlcv)
        # sample_ohlcv starts at the 09:30 open per the fixture.
        first = pd.to_datetime(result['Time']).iloc[0]
        if first.hour == 9 and first.minute == 30:
            assert result['Mins_Since_Open'].iloc[0] == 0.0

    def test_promoted_features_absent_pieces_without_time(self):
        """No Time → no Mins_Since_Open (parity with ORB guard)."""
        n = 60
        close = pd.Series(np.linspace(100, 105, n))
        df = pd.DataFrame({
            'Open': close * 0.999, 'High': close * 1.001, 'Low': close * 0.998,
            'Close': close, 'Volume': np.random.RandomState(0).randint(1e3, 1e4, n).astype(float),
        })
        result = add_all_indicators(df)
        assert 'Mins_Since_Open' not in result.columns
        # ATR-based ones still computed (no Time needed)
        assert 'Realized_Vol_Short' in result.columns

    def test_rsi_divergence_equals_fast_minus_slow(self, sample_ohlcv):
        result = add_all_indicators(sample_ohlcv)
        expected = result['RSI9'] - result['RSI14']
        pd.testing.assert_series_equal(
            result['RSI_Divergence'], expected, check_names=False)

    def test_atr_normalised_distance_matches_formula(self, sample_ohlcv):
        result = add_all_indicators(sample_ohlcv)
        atr = result['ATR14']
        expected = (result['Close'] - result['VWAP']) / atr.where(atr.abs() > 0, np.nan)
        pd.testing.assert_series_equal(
            result['Price_vs_VWAP_ATR'], expected, check_names=False)

    def test_orb_custom_windows(self):
        """add_all_indicators with custom orb_windows should produce matching columns."""
        from lib.config import IndicatorConfig
        np.random.seed(42)
        n = 50
        times = pd.date_range('2024-01-02 09:30', periods=n, freq='1min')
        close = pd.Series(np.linspace(200, 201, n))
        df = pd.DataFrame({
            'Time': times,
            'Open': close * 0.999,
            'High': close * 1.001,
            'Low': close * 0.998,
            'Close': close,
            'Volume': np.random.randint(1000, 10000, n).astype(float),
        }, index=times)

        custom_ind = IndicatorConfig(orb_windows=[{'minutes': 10, 'label': '10m'}])
        result = add_all_indicators(df, indicator_config=custom_ind)
        assert 'ORB_10m_High' in result.columns
        assert 'ORB_10m_Low' in result.columns
        assert 'ORB_10m_Trend' in result.columns
        # Default labels should NOT be present
        assert 'ORB_5m_High' not in result.columns


class TestHistoricalLevels:
    """calculate_historical_levels output, including Quarter (added v2)."""

    def _frame(self):
        # 12 months of weekly bars covering Q1 + Q2 of 2024.
        dates = pd.date_range('2024-01-05', '2024-06-28', freq='W-FRI')
        n = len(dates)
        np.random.seed(7)
        close = 200 + np.cumsum(np.random.normal(0, 0.5, n))
        high = close + 1
        low = close - 1
        open_ = close
        return pd.Series(dates), pd.Series(high), pd.Series(low), pd.Series(open_), pd.Series(close)

    def test_emits_quarter_columns(self):
        times, high, low, open_, close = self._frame()
        result = calculate_historical_levels(times, high, low, open_, close)
        for col in [
            'Prev_Quarter_High', 'Prev_Quarter_Low',
            'Prev_Quarter_Open', 'Prev_Quarter_Close',
            'Prev_Quarter_HL_Mid', 'Prev_Quarter_OC_Mid',
            'Broke_Prev_Quarter_High', 'Broke_Prev_Quarter_Low',
        ]:
            assert col in result.columns, f'{col} missing from historical levels'

    def test_quarter_high_matches_prior_quarter_max(self):
        """Q2 rows should have Prev_Quarter_High equal to max(High) over Q1."""
        times, high, low, open_, close = self._frame()
        result = calculate_historical_levels(times, high, low, open_, close)

        ts = pd.to_datetime(times)
        is_q1 = ts.dt.to_period('Q') == ts.dt.to_period('Q').iloc[0]
        is_q2 = ts.dt.to_period('Q') > ts.dt.to_period('Q').iloc[0]

        expected_q1_high = high[is_q1].max()
        q2_prev_quarter_high = result.loc[is_q2.values, 'Prev_Quarter_High'].dropna()
        assert (q2_prev_quarter_high == expected_q1_high).all()

    def test_first_quarter_has_nan(self):
        """Q1 has no prior quarter, so Prev_Quarter_* must be NaN there."""
        times, high, low, open_, close = self._frame()
        result = calculate_historical_levels(times, high, low, open_, close)

        ts = pd.to_datetime(times)
        is_q1 = ts.dt.to_period('Q') == ts.dt.to_period('Q').iloc[0]
        assert result.loc[is_q1.values, 'Prev_Quarter_High'].isna().all()
