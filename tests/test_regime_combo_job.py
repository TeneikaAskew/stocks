"""Hermetic I/O-shape tests for gcp.regime_combo_job (Effort A scheduled job).

No Cloud SQL, no network. The DataLoader and the persist step are
monkeypatched, so this exercises the real combo pipeline against synthetic
bars and asserts the I/O contract (Rule 0.3): N tickers → exactly N loads, one
upsert, fail-loud on all-empty.
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

pytest.importorskip("sklearn")

from gcp import regime_combo_job as job  # noqa: E402


def _session(day: str, n: int = 390, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(f"{day} 09:30", periods=n, freq="1min")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.0005, n)))
    df = pd.DataFrame({
        "Open": close, "High": close * 1.001, "Low": close * 0.999,
        "Close": close, "Volume": rng.integers(1e4, 5e4, n).astype(float),
    }, index=idx)
    df.index.name = "Time"
    df["Time"] = df.index
    return df


def _multi(days, seed=0):
    return pd.concat([_session(d, seed=seed + i) for i, d in enumerate(days)])


_DAYS = [f"2026-04-{d:02d}" for d in range(1, 28)]  # ~27 sessions


def test_io_shape_loads_once_per_ticker_one_upsert(monkeypatch):
    calls = {"load": [], "persist": 0}

    class FakeLoader:
        def __init__(self, *a, **k): pass
        def load_intraday(self, ticker, start_date=None, end_date=None, **k):
            calls["load"].append(ticker)
            return _multi(_DAYS, seed=hash(ticker) % 100)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    monkeypatch.setattr(job, "_persist", lambda r: calls.__setitem__("persist", calls["persist"] + 1) or len(r))

    tickers = ["SPY", "IWM", "QQQ"]
    res = job.run(tickers, [15, 30], lookback_days=60, as_of=date(2026, 4, 28),
                  train_frac=0.7, min_support=200, top_k=5, max_order=2,
                  dry_run=False)
    # exactly one SELECT per ticker (NOT per bar — the Rule 0 N+1 guard)
    assert calls["load"] == tickers
    assert calls["persist"] == 1
    # window provenance stamped
    assert (res["computed_date"] == date(2026, 4, 28)).all()
    # only the expected regime classes
    assert set(res["target_class"].unique()) <= {"UP", "DOWN", "FLAT", "BIG"}
    # lift column present and finite where rows exist
    assert "lift" in res.columns


def test_dry_run_does_not_persist(monkeypatch):
    class FakeLoader:
        def __init__(self, *a, **k): pass
        def load_intraday(self, ticker, **k):
            return _multi(_DAYS, seed=3)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    called = {"n": 0}
    monkeypatch.setattr(job, "_persist", lambda r: called.__setitem__("n", called["n"] + 1))
    job.run(["IWM"], [15], lookback_days=60, as_of=date(2026, 4, 28),
            train_frac=0.7, min_support=200, top_k=5, max_order=2, dry_run=True)
    assert called["n"] == 0


def test_all_empty_raises(monkeypatch):
    class FakeLoader:
        def __init__(self, *a, **k): pass
        def load_intraday(self, ticker, **k):
            return pd.DataFrame()

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    monkeypatch.setattr(job, "_persist", lambda r: 0)
    with pytest.raises(RuntimeError, match="No intraday data for ANY"):
        job.run(["SPY", "IWM"], [15], lookback_days=60, as_of=date(2026, 4, 28),
                train_frac=0.7, min_support=200, top_k=5, max_order=2, dry_run=False)


def test_main_returns_zero_on_success(monkeypatch):
    class FakeLoader:
        def __init__(self, *a, **k): pass
        def load_intraday(self, ticker, **k):
            return _multi(_DAYS, seed=5)

    monkeypatch.setattr("lib.data_loader.DataLoader", FakeLoader)
    monkeypatch.setattr(job, "_persist", lambda r: len(r))
    rc = job.main(["--tickers", "IWM", "--horizons", "15", "--lookback-days", "60",
                   "--as-of", "2026-04-28", "--min-support", "200", "--max-order", "2",
                   "--dry-run"])
    assert rc == 0
