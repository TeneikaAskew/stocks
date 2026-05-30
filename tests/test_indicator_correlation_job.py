"""Hermetic tests for gcp.indicator_correlation_job.

No Cloud SQL, no network. The DataLoader and the persist step are
monkeypatched, so these exercise the real indicator + correlation code path
against synthetic bars. Per CLAUDE.md Rule 0.3, the integration test asserts
the I/O SHAPE (N tickers → exactly N load calls, one upsert, expected row
count) rather than just pure-helper correctness.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from gcp import indicator_correlation_job as job  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------

def _synthetic_session(day: str, n_bars: int = 390, seed: int = 0) -> pd.DataFrame:
    """One RTH session of 1-min bars (09:30..16:00) with a Time column."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{day} 09:30", periods=n_bars, freq="1min")
    # Geometric random walk so Close is strictly positive (log returns defined).
    steps = rng.normal(0, 0.0004, n_bars)
    close = 100.0 * np.exp(np.cumsum(steps))
    high = close * (1 + np.abs(rng.normal(0, 0.0003, n_bars)))
    low = close * (1 - np.abs(rng.normal(0, 0.0003, n_bars)))
    open_ = close * (1 + rng.normal(0, 0.0002, n_bars))
    vol = rng.integers(1_000, 50_000, n_bars)
    df = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )
    df.index.name = "Time"
    df["Time"] = df.index
    return df


def _multi_session(days: list[str], seed: int = 0) -> pd.DataFrame:
    return pd.concat([_synthetic_session(d, seed=seed + i) for i, d in enumerate(days)])


# ---------------------------------------------------------------------------
# Pure-function tests (I/O-free)
# ---------------------------------------------------------------------------

def test_filter_rth_drops_extended_hours():
    idx = pd.to_datetime([
        "2026-05-01 08:00", "2026-05-01 09:30", "2026-05-01 12:00",
        "2026-05-01 16:00", "2026-05-01 18:30",
    ])
    df = pd.DataFrame({"Close": [1, 2, 3, 4, 5], "Time": idx}, index=idx)
    out = job.filter_rth(df)
    # 09:30 and 16:00 inclusive; 12:00 in; 08:00 and 18:30 out.
    assert list(out["Close"]) == [2, 3, 4]


def test_add_forward_returns_is_causal_and_per_session():
    # Two sessions; the last h bars of EACH must be NaN (no cross-day leak).
    df = _multi_session(["2026-05-01", "2026-05-02"], seed=1)
    out = job.add_forward_returns(df, [5])
    col = "fwd_ret_5"
    assert col in out.columns
    per_day_nan = out.groupby("Date")[col].apply(lambda s: s.tail(5).isna().all())
    assert per_day_nan.all(), "last h bars of each session must be NaN"
    # And the value matches ln(Close[t+5]/Close[t]) within a session.
    day1 = out[out["Date"] == date(2026, 5, 1)].reset_index(drop=True)
    expected = np.log(day1["Close"].iloc[5]) - np.log(day1["Close"].iloc[0])
    assert day1[col].iloc[0] == pytest.approx(expected, rel=1e-9)


def test_forward_return_perfectly_predicts_a_synthetic_indicator():
    """A column equal to the forward return must show rank_ic ≈ 1.0 — proves
    the correlation wiring and sign are correct (no lookahead inversion)."""
    df = _synthetic_session("2026-05-01", seed=2)
    df = job.add_forward_returns(df, [5])
    df["cheater"] = df["fwd_ret_5"]  # leak the future on purpose
    df = df.dropna(subset=["fwd_ret_5"])
    out = job.correlate(df, ["cheater"], [5])
    row = out.iloc[0]
    assert row["rank_ic"] == pytest.approx(1.0, abs=1e-6)
    assert row["pearson"] == pytest.approx(1.0, abs=1e-6)


def test_indicator_columns_excludes_ohlcv_and_returns_and_constants():
    df = pd.DataFrame({
        "Open": [1.0, 2], "High": [1.0, 2], "Low": [1.0, 2],
        "Close": [1.0, 2], "Volume": [1, 2], "Time": [0, 1], "Date": [0, 1],
        "fwd_ret_5": [0.1, 0.2],
        "constant_col": [3.0, 3.0],          # constant → excluded
        "RSI14": np.random.default_rng(0).normal(size=2),  # too few valid → excluded
    })
    cols = job.indicator_columns(df)
    assert "Close" not in cols and "Volume" not in cols
    assert "fwd_ret_5" not in cols
    assert "constant_col" not in cols


def test_enrich_produces_known_production_indicator_columns():
    df = _multi_session(["2026-05-01", "2026-05-02", "2026-05-03"], seed=3)
    out = job.enrich(df, job.IndicatorConfig(), [5, 15])
    # A representative slice of the add_all_indicators contract.
    for col in ["ATR14", "RSI14", "VWAP", "BB_Width", "MACD", "ORB_15m_Range"]:
        assert col in out.columns, f"expected production indicator {col}"
    # RTH filter applied + forward-return columns present.
    assert "fwd_ret_5" in out.columns and "fwd_ret_15" in out.columns


# ---------------------------------------------------------------------------
# Integration test — I/O shape (Rule 0.3), DB + loader mocked
# ---------------------------------------------------------------------------

def test_run_io_shape_and_pooled_row(monkeypatch):
    days = ["2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08"]
    calls = {"load": [], "persist": []}

    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            calls["load"].append(ticker)
            return _multi_session(days, seed=hash(ticker) % 1000)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)

    def fake_persist(results):
        calls["persist"].append(results.copy())
        return len(results)

    monkeypatch.setattr(job, "_persist", fake_persist)

    tickers = ["SPY", "IWM", "QQQ"]
    horizons = [5, 15]
    results = job.run(tickers, horizons, lookback_days=10,
                      as_of=date(2026, 5, 8), dry_run=False)

    # Exactly one SELECT per ticker — NOT per bar (the Rule 0 N+1 guard).
    assert calls["load"] == tickers
    # Exactly one upsert.
    assert len(calls["persist"]) == 1
    # POOLED rows exist in addition to the three real tickers.
    assert set(results["ticker"].unique()) == {"SPY", "IWM", "QQQ", "POOLED"}
    # Window provenance stamped on every row.
    assert (results["computed_date"] == date(2026, 5, 8)).all()
    assert (results["window_end"] == date(2026, 5, 8)).all()
    assert (results["lookback_days"] == 10).all()
    # Both horizons present, correlations bounded.
    assert set(results["horizon_min"].unique()) == {5, 15}
    finite_ic = results["rank_ic"].dropna()
    assert ((finite_ic >= -1.0001) & (finite_ic <= 1.0001)).all()


def test_run_dry_run_does_not_persist(monkeypatch):
    days = ["2026-05-04", "2026-05-05", "2026-05-06"]

    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            return _multi_session(days, seed=7)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    called = {"n": 0}
    monkeypatch.setattr(job, "_persist", lambda r: called.__setitem__("n", called["n"] + 1))

    out = job.run(["SPY"], [5], lookback_days=5,
                  as_of=date(2026, 5, 6), dry_run=True)
    assert called["n"] == 0
    assert not out.empty


def test_run_raises_when_all_tickers_empty(monkeypatch):
    """Rule 3.7: all-empty must fail loud, not silently write nothing."""
    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            return pd.DataFrame()

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    monkeypatch.setattr(job, "_persist", lambda r: 0)

    with pytest.raises(RuntimeError, match="No intraday data for ANY"):
        job.run(["SPY", "IWM"], [5], lookback_days=5,
                as_of=date(2026, 5, 6), dry_run=False)


def test_run_skips_empty_ticker_but_continues(monkeypatch):
    days = ["2026-05-04", "2026-05-05", "2026-05-06"]

    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            if ticker == "IWM":
                return pd.DataFrame()  # one empty ticker
            return _multi_session(days, seed=11)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    monkeypatch.setattr(job, "_persist", lambda r: len(r))

    results = job.run(["SPY", "IWM", "QQQ"], [5], lookback_days=5,
                      as_of=date(2026, 5, 6), dry_run=True)
    # IWM dropped; SPY/QQQ present (+ POOLED since ≥2 real tickers loaded).
    assert "IWM" not in set(results["ticker"].unique())
    assert {"SPY", "QQQ", "POOLED"}.issubset(set(results["ticker"].unique()))


def test_main_returns_zero_on_success(monkeypatch):
    days = ["2026-05-04", "2026-05-05", "2026-05-06"]

    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            return _multi_session(days, seed=5)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    monkeypatch.setattr(job, "_persist", lambda r: len(r))
    rc = job.main(["--tickers", "SPY,QQQ", "--horizons", "5",
                   "--lookback-days", "5", "--as-of", "2026-05-06", "--dry-run"])
    assert rc == 0


def test_main_returns_one_on_failure(monkeypatch):
    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            return pd.DataFrame()  # all empty → run() raises → main() returns 1

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    rc = job.main(["--tickers", "SPY", "--horizons", "5",
                   "--lookback-days", "5", "--as-of", "2026-05-06"])
    assert rc == 1
