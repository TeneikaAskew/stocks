"""Pins the per-statement timeout bound on query_to_dataframe_strict.

Issue #765: freshness-watchdog has a 3600s Cloud Run task-timeout. One
unindexed query (PR #759's whole-universe enrichment check, against a
market_data_daily that carried only ticker-leading indexes) consumed the
entire budget. The container was killed mid-run, so the job reported
NOTHING — not even the checks that had already passed — and the logs
could not attribute the hour to any particular check.

`timeout_s` bounds a single statement server-side so that failure mode
becomes one loud, attributable error instead of a silent whole-job kill.
It must be applied via SET LOCAL inside an explicit transaction: a
session-level SET would ride the pooled connection back into the pool
and silently cap unrelated queries later.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pandas as pd
import pytest


def _mock_engine(monkeypatch):
    """Wire gcp.database.get_engine to a recording mock connection."""
    from gcp import database

    executed: list[str] = []
    began: list[str] = []

    conn = MagicMock()
    conn.execute.side_effect = lambda stmt, *a, **k: executed.append(str(stmt))

    class _Txn:
        def __enter__(self_):
            began.append("begin")
            return self_
        def __exit__(self_, *exc):
            return False

    conn.begin.side_effect = lambda: _Txn()

    class _Engine:
        def connect(self_):
            class _Ctx:
                def __enter__(s): return conn
                def __exit__(s, *e): return False
            return _Ctx()

    monkeypatch.setattr(database, "get_engine", lambda: _Engine())
    monkeypatch.setattr(database.pd, "read_sql",
                        lambda *a, **k: pd.DataFrame([{"ok": 1}]))
    return executed, began


def test_no_timeout_opens_no_transaction(monkeypatch):
    """Default path is unchanged — no SET, no explicit transaction."""
    from gcp.database import query_to_dataframe_strict
    executed, began = _mock_engine(monkeypatch)
    out = query_to_dataframe_strict("SELECT 1", {})
    assert not executed, "no SET should be issued when timeout_s is None"
    assert not began, "no transaction should be opened when timeout_s is None"
    assert out.iloc[0]["ok"] == 1


def test_timeout_is_set_local_inside_a_transaction(monkeypatch):
    """SET LOCAL, not a bare SET — the bound must not leak to the pool."""
    from gcp.database import query_to_dataframe_strict
    executed, began = _mock_engine(monkeypatch)
    query_to_dataframe_strict("SELECT 1", {}, timeout_s=120.0)
    assert began == ["begin"], "SET LOCAL requires an explicit transaction"
    assert len(executed) == 1
    stmt = executed[0]
    assert "SET LOCAL statement_timeout" in stmt, (
        f"expected a transaction-scoped SET LOCAL, got: {stmt}")
    assert "120000" in stmt, "timeout_s is seconds; Postgres wants ms"


def test_timeout_is_integer_coerced(monkeypatch):
    """The value is interpolated, so int() coercion is what keeps it safe."""
    from gcp.database import query_to_dataframe_strict
    executed, _ = _mock_engine(monkeypatch)
    query_to_dataframe_strict("SELECT 1", {}, timeout_s=1.7)
    assert executed[0].endswith("1700"), executed[0]
    assert "." not in executed[0].split("=")[-1], (
        "a float would be invalid Postgres syntax")
