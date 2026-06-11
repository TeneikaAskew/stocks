"""Hermetic tests for the etf-options-retention Cloud Run Job control flow.

The DB is faked (no Cloud SQL) so the per-ticker timestamp-window logic is
exercised directly. Asserts the I/O shape required by CLAUDE.md Rule 0: work is
driven per ticker in fixed ts windows (so the partial index is always a seekable
range), a ticker already inside the window is skipped after one ``min`` probe,
and nothing is deleted when the window is unsafe or dry-run is set.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import gcp.options_retention_job as job

_CUTOFF = datetime(2026, 6, 11, 2, 0, tzinfo=timezone.utc)


class _FakeResult:
    def __init__(self, rowcount=0, scalar_val=None, rows=None):
        self.rowcount = rowcount
        self._scalar = scalar_val
        self._rows = rows if rows is not None else []

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, tickers, cutoff, oldest_by_ticker, count_val, del_rows):
        self.tickers = tickers
        self.cutoff = cutoff
        self.oldest_by_ticker = oldest_by_ticker
        self.count_val = count_val
        self.del_rows = del_rows
        self.delete_calls = 0
        self.count_calls = 0
        self.set_timeout_calls = 0

    def execute(self, stmt, params=None):
        sql = str(stmt).strip().upper()
        params = params or {}
        if "SET LOCAL" in sql:
            self.set_timeout_calls += 1
            return _FakeResult()
        if "WITH RECURSIVE" in sql:
            return _FakeResult(rows=[(t,) for t in self.tickers])
        if "MIN(SNAPSHOT_TS)" in sql:
            return _FakeResult(scalar_val=self.oldest_by_ticker.get(params.get("tkr")))
        if "COUNT(*)" in sql:
            self.count_calls += 1
            return _FakeResult(scalar_val=self.count_val)
        if "NOW()" in sql:
            return _FakeResult(scalar_val=self.cutoff)
        self.delete_calls += 1            # DELETE
        return _FakeResult(rowcount=self.del_rows)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self, tickers=("SPY",), cutoff=_CUTOFF,
                 oldest_by_ticker=None, count_val=0, del_rows=100):
        self.conn = _FakeConn(list(tickers), cutoff, oldest_by_ticker or {},
                              count_val, del_rows)

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
    monkeypatch.setenv("RETENTION_DAYS", "10")          # below the 14-day floor
    called = _patch_engine(monkeypatch, _FakeEngine())
    assert job.main() == 2
    assert called["n"] == 0                              # get_engine never called


def test_all_tickers_current_is_a_noop(monkeypatch):
    # Every ticker's oldest row is newer than the cutoff -> skipped, no deletes.
    newer = _CUTOFF + timedelta(hours=1)
    eng = _FakeEngine(tickers=("SPY", "IWM", "QQQ"),
                      oldest_by_ticker={"SPY": newer, "IWM": newer, "QQQ": newer})
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 0


def test_ticker_with_no_realtime_rows_is_skipped(monkeypatch):
    eng = _FakeEngine(tickers=("SPY",), oldest_by_ticker={"SPY": None})
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 0


def test_active_ticker_walks_one_window_per_hour(monkeypatch):
    # oldest is exactly 2h before cutoff -> two 1-hour windows -> two deletes.
    eng = _FakeEngine(tickers=("SPY",),
                      oldest_by_ticker={"SPY": _CUTOFF - timedelta(hours=2)})
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 2
    assert eng.conn.set_timeout_calls == 2              # guard set on every window


def test_iterates_every_ticker(monkeypatch):
    # Two tickers, each one window behind -> one delete each.
    one_hour_back = _CUTOFF - timedelta(hours=1)
    eng = _FakeEngine(tickers=("SPY", "IWM"),
                      oldest_by_ticker={"SPY": one_hour_back, "IWM": one_hour_back})
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 2


def test_dry_run_counts_per_ticker_but_never_deletes(monkeypatch):
    monkeypatch.setenv("RETENTION_DRY_RUN", "1")
    eng = _FakeEngine(tickers=("SPY", "IWM", "QQQ"), count_val=1_000_000,
                      oldest_by_ticker={"SPY": _CUTOFF - timedelta(days=1)})
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.count_calls == 3                    # one count per ticker
    assert eng.conn.delete_calls == 0                   # dry-run deletes nothing


def test_no_tickers_is_a_clean_noop(monkeypatch):
    eng = _FakeEngine(tickers=())
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
    assert eng.conn.delete_calls == 0


def test_default_window_is_thirty_days(monkeypatch):
    # No RETENTION_DAYS -> default 30 (above floor); all current -> no-op.
    eng = _FakeEngine(tickers=("SPY",),
                      oldest_by_ticker={"SPY": _CUTOFF + timedelta(hours=1)})
    _patch_engine(monkeypatch, eng)
    assert job.main() == 0
