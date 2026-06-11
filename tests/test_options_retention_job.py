"""Hermetic tests for the etf-options-retention Cloud Run Job control flow.

The DB is faked (no Cloud SQL) so the per-ticker batching / dry-run / floor-guard
logic is exercised directly. Asserts the I/O shape required by CLAUDE.md Rule 0:
work is driven per ticker (so the partial index is always seekable), a day's
purge issues batched DELETEs until nothing is eligible, and the job never
touches data when the window is unsafe or dry-run is set.
"""
from __future__ import annotations

import pytest

import gcp.options_retention_job as job


class _FakeResult:
    def __init__(self, rowcount=0, scalar_val=0, rows=None):
        self.rowcount = rowcount
        self._scalar = scalar_val
        self._rows = rows if rows is not None else []

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, tickers, delete_rowcounts, count_val):
        self.tickers = tickers
        self.delete_rowcounts = list(delete_rowcounts)
        self.count_val = count_val
        self.delete_calls = 0
        self.count_calls = 0
        self.set_timeout_calls = 0

    def execute(self, stmt, params=None):
        sql = str(stmt).strip().upper()
        if sql.startswith("SET LOCAL"):
            self.set_timeout_calls += 1
            return _FakeResult()
        if sql.startswith("WITH RECURSIVE"):
            return _FakeResult(rows=[(t,) for t in self.tickers])
        if sql.startswith("SELECT COUNT"):
            self.count_calls += 1
            return _FakeResult(scalar_val=self.count_val)
        self.delete_calls += 1
        rc = self.delete_rowcounts.pop(0) if self.delete_rowcounts else 0
        return _FakeResult(rowcount=rc)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self, tickers=("SPY",), delete_rowcounts=(), count_val=0):
        self.conn = _FakeConn(list(tickers), delete_rowcounts, count_val)

    def connect(self):
        return _Ctx(self.conn)

    def begin(self):
        return _Ctx(self.conn)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("RETENTION_DAYS", raising=False)
    monkeypatch.delenv("RETENTION_DRY_RUN", raising=False)


def _patch_engine(monkeypatch, engine):
    called = {"n": 0}

    def _fake_get_engine():
        called["n"] += 1
        return engine

    monkeypatch.setattr(job, "get_engine", _fake_get_engine)
    return called


def test_floor_guard_refuses_short_window_without_touching_db(monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "10")        # below the 14-day floor
    called = _patch_engine(monkeypatch, _FakeEngine())
    assert job.main() == 2
    assert called["n"] == 0                            # get_engine never called


def test_nothing_eligible_is_a_noop_per_ticker(monkeypatch):
    # No up-front count: a quiet day is one empty DELETE probe per ticker.
    eng = _FakeEngine(tickers=("SPY", "IWM", "QQQ"), delete_rowcounts=[0, 0, 0])
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.count_calls == 0                   # no count in normal mode
    assert eng.conn.delete_calls == 3                  # one empty probe / ticker
    assert eng.conn.set_timeout_calls == 3             # guard set on every batch


def test_no_realtime_tickers_is_a_clean_noop(monkeypatch):
    eng = _FakeEngine(tickers=())
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 0                  # nothing to iterate


def test_dry_run_counts_per_ticker_but_never_deletes(monkeypatch):
    monkeypatch.setenv("RETENTION_DRY_RUN", "1")
    eng = _FakeEngine(tickers=("SPY", "IWM", "QQQ"), count_val=1_000_000)
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.count_calls == 3                   # one count per ticker
    assert eng.conn.delete_calls == 0                  # dry-run deletes nothing


def test_batched_delete_loops_until_drained(monkeypatch):
    # One ticker, 120k eligible -> 50k + 50k + 20k + 0 -> 4 DELETE round-trips.
    eng = _FakeEngine(tickers=("SPY",),
                      delete_rowcounts=[50_000, 50_000, 20_000, 0])
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 4


def test_iterates_every_ticker(monkeypatch):
    # SPY drains in 1 real batch, IWM in 1 real batch; each then sees a 0.
    eng = _FakeEngine(tickers=("SPY", "IWM"),
                      delete_rowcounts=[40_000, 0, 30_000, 0])
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 4                  # 2 per ticker


def test_default_window_is_thirty_days(monkeypatch):
    # No RETENTION_DAYS -> default 30 (above floor) -> runs normally.
    eng = _FakeEngine(tickers=("SPY",), delete_rowcounts=[0])
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
