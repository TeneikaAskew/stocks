"""Pins `gcp.database.execute_sql`'s rowcount-forwarding contract.

`execute_sql` (gcp/database.py:711) returns `conn.execute(...).rowcount`
so callers can distinguish "statement ran but matched 0 rows" from
"statement matched N rows" instead of getting a fire-and-forget None.
This was landed in commit 1b6b2067; `gcp/premarket_brief.py`'s
`_delete_null_close_rows` was updated in #702 to actually use the real
count instead of a hardcoded "1 = attempted" sentinel (see
tests/test_premarket_brief.py::TestDeleteNullCloseRows).

Hermetic — fakes the SQLAlchemy engine/connection so no live DB is hit,
following the `_FakeEngine`/`_FakeConn`/context-manager pattern in
tests/test_options_retention_job.py.
"""
from __future__ import annotations

import gcp.database as database


class _FakeResult:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _FakeConn:
    def __init__(self, rowcount: int):
        self._rowcount = rowcount
        self.executed = []

    def execute(self, stmt, params=None):
        self.executed.append((str(stmt), params))
        return _FakeResult(self._rowcount)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self, rowcount: int):
        self.conn = _FakeConn(rowcount)

    def begin(self):
        return _Ctx(self.conn)


def test_execute_sql_returns_driver_rowcount(monkeypatch):
    """`conn.execute(...).rowcount == 3` must flow straight through as
    execute_sql's return value."""
    fake_engine = _FakeEngine(rowcount=3)
    monkeypatch.setattr(database, "get_engine", lambda: fake_engine)

    result = database.execute_sql(
        "DELETE FROM market_data_daily WHERE ticker = :t AND close IS NULL",
        {"t": "SPY"},
    )

    assert result == 3
    assert fake_engine.conn.executed[0][1] == {"t": "SPY"}


def test_execute_sql_returns_zero_when_no_rows_matched(monkeypatch):
    fake_engine = _FakeEngine(rowcount=0)
    monkeypatch.setattr(database, "get_engine", lambda: fake_engine)

    result = database.execute_sql("DELETE FROM t WHERE 1=0")

    assert result == 0
