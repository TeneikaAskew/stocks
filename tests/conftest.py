"""Shared test fixtures for the trading system test suite.

Two data-source modes for tests that need real OHLCV / level data:

  pytest --mode=live   (default)  Cloud SQL `market_data_daily` for any
                                  watchlist ticker, as_of = last
                                  business day with data.
  pytest --mode=mock              Frozen JSON fixture
                                  tests/fixtures/iwm_market_data.json
                                  (IWM only). Same shape as the DB
                                  rows, deterministic across runs.

Tests opt in by depending on the `market_data` fixture. Tests that
don't need real data (synthetic OHLCV unit tests) ignore --mode and
keep using the existing sample_* fixtures below.
"""

import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ───── --mode=live|mock flag ──────────────────────────────────────────


def pytest_addoption(parser):
    parser.addoption(
        "--mode", action="store", default="live",
        choices=["live", "mock"],
        help="Data source for the market_data fixture: live (Cloud SQL) "
             "or mock (frozen JSON fixture).",
    )


@pytest.fixture(scope="session")
def data_mode(request) -> str:
    return request.config.getoption("--mode")


# ───── Cloud SQL connection (live mode) ───────────────────────────────


_GCLOUD = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
_PROJECT = "adept-mountain-474619-d4"
_DB_HOST = "34.24.66.12"
_DB_NAME = "trading"


def _gcloud_secret(name: str) -> str:
    return subprocess.check_output(
        [_GCLOUD, "secrets", "versions", "access", "latest",
         f"--secret={name}", f"--project={_PROJECT}"],
        text=True, timeout=15,
    ).rstrip("\n")


def _connect_cloud_sql():
    """Connect to Cloud SQL. Prefers env vars; falls back to gcloud
    secrets so the user's local machine works without setting env vars.
    """
    import psycopg2
    if os.environ.get("CLOUD_SQL_URL"):
        return psycopg2.connect(os.environ["CLOUD_SQL_URL"], connect_timeout=10)
    if os.environ.get("DB_HOST") and os.environ.get("DB_USER"):
        return psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ.get("DB_NAME", "trading"),
            user=os.environ["DB_USER"],
            password=os.environ.get("DB_PASS",
                                    os.environ.get("DB_PASSWORD", "")),
            sslmode=os.environ.get("DB_SSLMODE", "prefer"),
            connect_timeout=10,
        )
    return psycopg2.connect(
        host=_DB_HOST,
        user=_gcloud_secret("db-trading-user"),
        password=_gcloud_secret("db-trading-pass"),
        dbname=_DB_NAME, sslmode="require", connect_timeout=10,
    )


@pytest.fixture(scope="session")
def db_conn(data_mode):
    if data_mode != "live":
        pytest.skip("db_conn only available in --mode=live")
    try:
        conn = _connect_cloud_sql()
    except Exception as e:
        pytest.skip(f"Cloud SQL unreachable: {type(e).__name__}: {e}")
    yield conn
    conn.close()


# ───── Mock fixture loader ────────────────────────────────────────────


_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_mock_fixture(ticker: str) -> dict:
    path = _FIXTURE_DIR / f"{ticker.lower()}_market_data.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No mock fixture for {ticker} at {path}. "
            f"Available: {sorted(p.name for p in _FIXTURE_DIR.glob('*.json'))}"
        )
    with open(path) as f:
        return json.load(f)


# ───── market_data fixture (live | mock) ──────────────────────────────


def _last_business_day_with_data(conn, ticker: str) -> date:
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(date) FROM market_data_daily "
        "WHERE ticker=%s AND close IS NOT NULL", (ticker,))
    (d,) = cur.fetchone()
    cur.close()
    if d is None:
        pytest.skip(f"No market_data_daily rows for {ticker}")
    return d


def _df_from_db(conn, ticker: str, as_of: date,
                lookback_days: int = 400) -> pd.DataFrame:
    start = as_of - timedelta(days=lookback_days)
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume, atr_14, "
        "       strat_candle, strat_combo, ftfc_score, ftfc_direction "
        "FROM market_data_daily "
        "WHERE ticker=%s AND date BETWEEN %s AND %s "
        "  AND close IS NOT NULL "
        "ORDER BY date",
        conn, params=(ticker, start, as_of))
    return _normalize_df(df)


def _df_from_mock(ticker: str) -> pd.DataFrame:
    rec = _load_mock_fixture(ticker)
    df = pd.DataFrame(rec["rows"])
    return _normalize_df(df)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Rename DB lowercase columns to OHLCV pascal-case and set DatetimeIndex.

    build_level_map / strat code expects Open/High/Low/Close columns and
    a DatetimeIndex. DB returns lowercase + a `date` column.
    """
    rename = {"open": "Open", "high": "High", "low": "Low",
              "close": "Close", "volume": "Volume"}
    df = df.rename(columns=rename)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    return df


@pytest.fixture
def market_data_factory(data_mode, request):
    """Returns a callable: (ticker, as_of=None) -> (df, current_price, atr).

    Live mode: hits Cloud SQL via session-scoped db_conn.
    Mock mode: loads tests/fixtures/<ticker>_market_data.json.

    Tests that want a single ticker use `market_data` instead.
    """
    if data_mode == "mock":
        def _load(ticker: str, as_of=None):
            df = _df_from_mock(ticker)
            if as_of is not None:
                df = df[df.index.date <= as_of]
            last = df.iloc[-1]
            return df, float(last["Close"]), float(last.get("atr_14") or 0.0)
        return _load

    # live
    conn = request.getfixturevalue("db_conn")
    def _load(ticker: str, as_of=None):
        if as_of is None:
            as_of = _last_business_day_with_data(conn, ticker)
        df = _df_from_db(conn, ticker, as_of)
        if df.empty:
            pytest.skip(f"No data for {ticker} at as_of={as_of}")
        last = df.iloc[-1]
        return df, float(last["Close"]), float(last.get("atr_14") or 0.0)
    return _load


@pytest.fixture
def market_data(market_data_factory):
    """Default fixture: returns IWM market data for the test's mode.

    Use `market_data_factory` directly when a test parametrizes ticker.
    Returns (DataFrame, current_price, atr_14).
    """
    return market_data_factory("IWM")


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
    """OHLCV data with a 212_bull_reversal combo at bar 4.

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


# ───────────────────────────────────────────────────────────────────
# Default load_watchlist stub for unit tests
# ───────────────────────────────────────────────────────────────────
# After the alert_config.json watchlist removal, SignalMonitor()
# requires Cloud SQL access at construction time (it queries
# watchlists for signals=TRUE rows). Unit tests that don't care
# about the watchlist source still need the constructor to succeed.
# This fixture stubs load_watchlist to return a default 3-ticker
# list for EVERY test, automatically. Tests that DO care can patch
# `gcp.fetchers._watchlist.load_watchlist` themselves inside their
# own with-block to override.
@pytest.fixture(autouse=True)
def _default_load_watchlist_stub(monkeypatch, request):
    """Patch the centralized watchlist loader with a 3-ticker default
    so unit tests don't need to touch Cloud SQL. Override in-test by
    re-patching with a context manager when a specific list is needed.

    Skipped for tests that intentionally exercise the real
    load_watchlist resolution chain (test_watchlist_helper.py).
    """
    # The watchlist-helper tests are testing the loader itself; they
    # need the real function. Same for any other test file that opts
    # out by name.
    if "test_watchlist_helper.py" in str(request.fspath):
        return
    try:
        from gcp.fetchers import _watchlist as wl_module
    except ImportError:
        # _watchlist module unavailable in this test environment
        # (e.g. minimal install without psycopg2) — nothing to patch.
        return
    monkeypatch.setattr(
        wl_module, "load_watchlist",
        lambda *a, **kw: ["IWM", "QQQ", "SPY"],
    )
