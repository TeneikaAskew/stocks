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
    add_all_indicators,
)


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
