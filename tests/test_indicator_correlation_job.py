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
                      as_of=date(2026, 5, 8), dry_run=False,
                      targets=["forward_return"])

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
    # forward_return target tag + class sentinel on every row.
    assert (results["target_name"] == "forward_return").all()
    assert (results["target_class"] == "").all()
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
                  as_of=date(2026, 5, 6), dry_run=True, targets=["forward_return"])
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
                as_of=date(2026, 5, 6), dry_run=False, targets=["forward_return"])


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
                      as_of=date(2026, 5, 6), dry_run=True, targets=["forward_return"])
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
                   "--lookback-days", "5", "--as-of", "2026-05-06",
                   "--targets", "forward_return", "--dry-run"])
    assert rc == 0


def test_main_returns_one_on_failure(monkeypatch):
    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            return pd.DataFrame()  # all empty → run() raises → main() returns 1

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    rc = job.main(["--tickers", "SPY", "--horizons", "5",
                   "--lookback-days", "5", "--as-of", "2026-05-06",
                   "--targets", "forward_return"])
    assert rc == 1


# ---------------------------------------------------------------------------
# Target-modular tests (regime / strat / signal classification targets)
# ---------------------------------------------------------------------------

def _enriched_fixture(days, seed=21):
    """A multi-session enriched frame (full indicators + fwd returns)."""
    raw = _multi_session(days, seed=seed)
    raw = raw.reset_index(drop=True)
    return job.enrich(raw, job.IndicatorConfig(), [job._REGIME_HORIZON])


def test_resolve_targets_validates_and_orders():
    ns = job.parse_args(["--targets", "strat,forward_return"])
    assert job._resolve_targets(ns) == ["forward_return", "strat"]
    ns2 = job.parse_args(["--target", "regime"])
    assert job._resolve_targets(ns2) == ["regime"]
    with pytest.raises(ValueError, match="unknown target"):
        job._resolve_targets(job.parse_args(["--targets", "bogus"]))


def test_regime_target_emits_per_class_metrics():
    days = [f"2026-05-{d:02d}" for d in range(4, 16)]  # 12 sessions
    enr = _enriched_fixture(days)
    ind_cols = job.indicator_columns(enr)
    rows = job.compute_target_rows(enr, ind_cols, [job._REGIME_HORIZON], "regime")
    assert not rows.empty
    assert (rows["target_name"] == "regime").all()
    # Multiple regime classes scored.
    assert set(rows["target_class"].unique()).issubset({"BIG", "UP", "DOWN", "FLAT"})
    assert len(set(rows["target_class"].unique())) >= 2
    # Each row carries the classification metric trio (at least one non-null).
    for _, r in rows.iterrows():
        assert (r["mutual_info"] is not None) or (r["class_lift"] is not None) \
            or (r["rank_ic"] is not None)
    # rank_ic bounded; pearson left NULL for class targets.
    fic = rows["rank_ic"].dropna()
    assert ((fic >= -1.0001) & (fic <= 1.0001)).all()
    assert rows["pearson"].isna().all()


def test_strat_target_emits_valid_classes():
    days = [f"2026-05-{d:02d}" for d in range(4, 16)]
    enr = _enriched_fixture(days)
    ind_cols = job.indicator_columns(enr)
    rows = job.compute_target_rows(enr, ind_cols, [job._REGIME_HORIZON], "strat")
    assert not rows.empty
    assert (rows["target_name"] == "strat").all()
    assert set(rows["target_class"].unique()).issubset({"1", "2U", "2D", "3"})


def test_class_lift_shuffled_label_is_near_one_and_mi_near_zero():
    """Control: a randomly-shuffled label must show no edge — lift≈1, MI≈0."""
    rng = np.random.default_rng(0)
    n = 4000
    x = pd.Series(rng.normal(size=n))
    y = rng.integers(0, 2, n)  # independent of x
    lift = job._class_lift(x, y)
    mi = job._class_mutual_info(x, y)
    rank_ic = job._class_rank_ic(x, y)
    assert lift == pytest.approx(1.0, abs=0.15)
    assert mi == pytest.approx(0.0, abs=0.02)
    assert abs(rank_ic) < 0.1


def test_class_metrics_detect_a_real_signal():
    """A label that IS the indicator's high-half must show lift>1, MI>0."""
    rng = np.random.default_rng(1)
    n = 4000
    x = pd.Series(rng.normal(size=n))
    y = (x > x.median()).astype(int).to_numpy()  # perfectly aligned
    assert job._class_lift(x, y) > 1.5
    assert job._class_mutual_info(x, y) > 0.1
    assert job._class_rank_ic(x, y) > 0.5


def test_class_metrics_return_none_on_insufficient_rows():
    """Rule 3.7: too-few rows → None, never a fabricated 0 / 1."""
    x = pd.Series([1.0, 2.0, 3.0])
    y = np.array([0, 1, 0])
    assert job._class_lift(x, y) is None
    assert job._class_mutual_info(x, y) is None
    assert job._class_rank_ic(x, y) is None


def test_signal_target_skips_when_no_outcomes(monkeypatch):
    """Sparse / empty signal_alerts → skip with warning, no fabricated rows."""
    monkeypatch.setattr(job, "_load_signal_outcomes", lambda *a, **k: pd.DataFrame())
    enr = _enriched_fixture(["2026-05-04", "2026-05-05", "2026-05-06"])
    out = job.compute_signal_target({"SPY": enr}, ["SPY"], "2026-05-01", "2026-05-06")
    assert out.empty


def test_signal_target_scores_matched_alerts(monkeypatch):
    """Alerts joined to fire-bar indicators produce signal-target rows."""
    enr = _enriched_fixture(["2026-05-04", "2026-05-05", "2026-05-06"])
    # Build 60 synthetic alerts pinned to real bar timestamps, alternating win/loss.
    fire_bars = enr.iloc[20:200:3]
    alerts = pd.DataFrame({
        "ticker": "SPY",
        "alert_ts": pd.to_datetime(fire_bars["Time"]).values,
        "exit_return_pct": [0.5 if i % 2 == 0 else -0.5 for i in range(len(fire_bars))],
    })
    monkeypatch.setattr(job, "_load_signal_outcomes", lambda *a, **k: alerts)
    out = job.compute_signal_target({"SPY": enr}, ["SPY"], "2026-05-01", "2026-05-06")
    assert not out.empty
    assert (out["target_name"] == "signal").all()
    assert (out["target_class"] == "WIN").all()


def test_run_default_targets_includes_all_four(monkeypatch):
    """Default-all run emits forward_return + regime + strat rows (signal skipped
    here since the DB is unavailable in the hermetic test)."""
    days = [f"2026-05-{d:02d}" for d in range(4, 16)]

    class FakeLoader:
        def __init__(self, *a, **k):
            pass

        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            return _multi_session(days, seed=33)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    # No signal_alerts → signal target skips cleanly.
    monkeypatch.setattr(job, "_load_signal_outcomes", lambda *a, **k: pd.DataFrame())
    captured = {}
    monkeypatch.setattr(job, "_persist", lambda r: captured.__setitem__("r", r) or len(r))

    results = job.run(["SPY", "QQQ"], [job._REGIME_HORIZON], lookback_days=20,
                      as_of=date(2026, 5, 15), dry_run=False)
    tnames = set(results["target_name"].unique())
    assert {"forward_return", "regime", "strat"}.issubset(tnames)
    # forward_return rows still carry the empty-string class sentinel.
    fr = results[results["target_name"] == "forward_return"]
    assert (fr["target_class"] == "").all()
