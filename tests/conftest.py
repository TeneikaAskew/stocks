"""Shared test fixtures for the trading system test suite."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@pytest.fixture
def sample_ohlcv():
    """50-bar OHLCV DataFrame with realistic prices for testing indicators."""
    np.random.seed(42)
    n = 50
    base_price = 200.0
    # Random walk for close prices
    returns = np.random.normal(0, 0.005, n)
    close = base_price * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.003, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.003, n)))
    open_ = close * (1 + np.random.normal(0, 0.002, n))
    volume = np.random.randint(100000, 500000, n).astype(float)

    times = pd.date_range('2024-01-02 09:30', periods=n, freq='1min')

    return pd.DataFrame({
        'Time': times,
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    }).set_index(times)


@pytest.fixture
def sample_daily():
    """100-bar daily OHLCV data for backtesting."""
    np.random.seed(123)
    n = 100
    base = 200.0
    returns = np.random.normal(0.0003, 0.012, n)
    close = base * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, n)))
    open_ = np.roll(close, 1) * (1 + np.random.normal(0, 0.002, n))
    open_[0] = base
    volume = np.random.randint(500000, 2000000, n).astype(float)

    dates = pd.bdate_range('2024-01-02', periods=n)

    return pd.DataFrame({
        'Time': dates,
        'Open': open_,
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume,
    }).set_index(dates)


@pytest.fixture
def known_strat_sequence():
    """OHLCV data with known Strat labels for testing classification.

    Bar 0: reference bar
    Bar 1: Inside bar (1) — H < prev H, L > prev L
    Bar 2: Up bar (2U) — H > prev H, L >= prev L
    Bar 3: Down bar (2D) — H <= prev H, L < prev L
    Bar 4: Outside bar (3) — H > prev H, L < prev L
    """
    data = {
        'High':  [100, 99, 101, 100, 102],
        'Low':   [95,  96, 96.5, 94,  93],
        'Open':  [97,  97, 97,  98,  97],
        'Close': [98,  98, 100, 95,  99],
        'Volume': [1000, 1000, 1000, 1000, 1000],
    }
    dates = pd.date_range('2024-01-02', periods=5, freq='D')
    df = pd.DataFrame(data, index=dates)
    df['Time'] = dates
    # Expected labels: X, 1, 2U, 2D, 3
    return df


@pytest.fixture
def strat_combo_sequence():
    """OHLCV data with a 2D-1-2U reversal combo at bar 4.

    Bar 0: reference
    Bar 1: reference
    Bar 2: 2D (down bar)
    Bar 3: 1 (inside bar)
    Bar 4: 2U that breaks above bar 3's high (reversal trigger)
    """
    data = {
        'High':  [100, 100, 99,  98,  99.5],
        'Low':   [95,  95,  93,  94,  94.5],
        'Open':  [97,  97,  96,  95,  95],
        'Close': [98,  98,  94,  97,  99],
        'Volume': [1000] * 5,
    }
    dates = pd.date_range('2024-01-02', periods=5, freq='D')
    df = pd.DataFrame(data, index=dates)
    df['Time'] = dates
    return df


@pytest.fixture
def risk_config():
    from lib.config import RiskConfig
    return RiskConfig()


@pytest.fixture
def exit_config():
    from lib.config import ExitConfig
    return ExitConfig()
