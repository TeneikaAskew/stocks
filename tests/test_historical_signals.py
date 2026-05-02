"""Unit tests for `gcp/historical_signals.py`.

These tests exercise the bulk_insert multi-row VALUES rewrite that
turned ~6 rows/sec into ~600 rows/sec. Specifically:
    - bind-param uniqueness (`p0_*..pN_*` per row)
    - chunk boundary at the configured chunk_size
    - NaN/Inf scrubbing (Postgres rejects these)
    - ON CONFLICT (ticker, entry_time) DO NOTHING idempotence
    - empty df short-circuits to (0, 0)
    - _clean_for_json + _json_default handle numpy NaN

No live DB. We patch `gcp.database.get_engine` with a fake engine that
captures every `execute(sql, params)` for assertion.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────
# Test fixtures — fake engine that records execute(sql, params) calls
# ──────────────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, rowcount=None):
        self.rowcount = rowcount


class FakeConnection:
    """Captures every execute() so tests can inspect SQL + params."""

    def __init__(self, rowcount_per_call=None):
        self.calls: list[tuple[str, dict]] = []
        # Default: every batch claims to have inserted exactly its row count
        self._rowcount_per_call = rowcount_per_call

    def execute(self, sql, params=None):
        # SQLAlchemy text() objects expose .text
        sql_str = getattr(sql, "text", str(sql))
        self.calls.append((sql_str, dict(params or {})))
        if self._rowcount_per_call is None:
            # Infer from "VALUES (...)" tuple count
            n_tuples = sql_str.count("(:p")
            return FakeResult(rowcount=n_tuples)
        return FakeResult(rowcount=self._rowcount_per_call)


class FakeEngine:
    def __init__(self, conn: FakeConnection):
        self.conn = conn

    @contextmanager
    def begin(self):
        yield self.conn

    @contextmanager
    def connect(self):
        yield self.conn


def _make_row(entry_time, **overrides):
    """Build one valid `historical_signals` row dict matching COLS.

    Includes every column in `gcp.historical_signals.COLS` so the
    bulk_insert column-projection (`df = df[list(COLS)]`) doesn't
    raise KeyError. New columns must be added here whenever COLS
    changes (Phase 0.7 added 'strategy', Phase 1 added
    'timeframe_tag' and 'expected_hold_min').
    """
    base = {
        "ticker": "IWM",
        "entry_time": entry_time,
        "strategy": "momentum",                # Phase 0.7
        "trade_type": "CALL",
        "entry_price": 220.5,
        "signal_strength": 4,
        "conditions_met": 3,
        "duration_minutes": 20,
        "return_pct": 1.25,
        "best_return": 1.25,
        "best_window_min": 20,
        "return_5min": 0.4,
        "return_10min": 0.7,
        "return_15min": 1.0,
        "return_20min": 1.25,
        "return_30min": 1.0,
        "return_45min": 0.6,
        "return_60min": 0.3,
        "entry_rsi": 56.0,
        "entry_ema9": 220.0,
        "entry_ema20": 219.5,
        "entry_vwap": 219.8,
        "entry_volume": 250_000,
        "extra": {"setup": "2D-1-2U"},
        "timeframe_tag": "30m",                # Phase 1
        "expected_hold_min": 30,               # Phase 1
    }
    base.update(overrides)
    return base


@pytest.fixture
def fake_engine_factory(monkeypatch):
    """Returns a function that installs a FakeEngine and returns its
    captured FakeConnection so tests can inspect calls."""
    from gcp import historical_signals as hs_module

    def install(rowcount=None):
        conn = FakeConnection(rowcount_per_call=rowcount)
        monkeypatch.setattr(hs_module, "get_engine", lambda: FakeEngine(conn))
        return conn

    return install


# ──────────────────────────────────────────────────────────────────────
# bulk_insert — empty short-circuit
# ──────────────────────────────────────────────────────────────────────


def test_bulk_insert_empty_df_returns_zero_zero(fake_engine_factory):
    """Empty df: no engine call, return (0, 0). Without this guard the
    SQL becomes `INSERT ... VALUES ` with no tuples — a syntax error."""
    from gcp.historical_signals import bulk_insert

    conn = fake_engine_factory()
    result = bulk_insert(pd.DataFrame())
    assert result == (0, 0)
    assert conn.calls == [], "engine should not be touched on empty df"


# ──────────────────────────────────────────────────────────────────────
# bulk_insert — multi-row VALUES form
# ──────────────────────────────────────────────────────────────────────


def test_bulk_insert_emits_one_statement_per_chunk(fake_engine_factory):
    """3 rows + chunk_size=10 → exactly one INSERT statement, with
    three (...) value tuples concatenated by ', '."""
    from gcp.historical_signals import bulk_insert

    conn = fake_engine_factory(rowcount=3)
    rows = [
        _make_row(datetime(2026, 4, 25, 10, 0)),
        _make_row(datetime(2026, 4, 25, 10, 5)),
        _make_row(datetime(2026, 4, 25, 10, 10)),
    ]
    df = pd.DataFrame(rows)
    attempted, inserted = bulk_insert(df, chunk_size=10)

    assert attempted == 3
    assert inserted == 3
    assert len(conn.calls) == 1, "all rows fit in one chunk → one execute"
    sql, params = conn.calls[0]
    assert sql.startswith("INSERT INTO historical_signals")
    # Phase 0.7 extended the conflict key to include strategy so
    # parallel-strategy rows coexist on the same (ticker, entry_time).
    assert "ON CONFLICT (ticker, entry_time, strategy) DO NOTHING" in sql
    # 3 value tuples
    assert sql.count("(:p") == 3


def test_bulk_insert_chunks_at_boundary(fake_engine_factory):
    """7 rows + chunk_size=3 → 3 inserts (3 + 3 + 1)."""
    from gcp.historical_signals import bulk_insert

    conn = fake_engine_factory()
    rows = [
        _make_row(datetime(2026, 4, 25, 10, i))
        for i in range(7)
    ]
    df = pd.DataFrame(rows)
    bulk_insert(df, chunk_size=3)

    assert len(conn.calls) == 3
    # Per-chunk row count
    chunk_sizes = [c[0].count("(:p") for c in conn.calls]
    assert chunk_sizes == [3, 3, 1]


def test_bulk_insert_unique_params_per_row(fake_engine_factory):
    """Each row gets prefixed `p{i}_*` keys so no two rows collide on
    the same bind name. With 23 columns × 2 rows we expect 46 keys."""
    from gcp.historical_signals import bulk_insert, COLS

    conn = fake_engine_factory()
    rows = [
        _make_row(datetime(2026, 4, 25, 10, 0)),
        _make_row(datetime(2026, 4, 25, 10, 5)),
    ]
    df = pd.DataFrame(rows)
    bulk_insert(df, chunk_size=10)

    sql, params = conn.calls[0]
    assert len(params) == 2 * len(COLS)
    # Row 0 + row 1 both have a `*_ticker` key, prefixed differently
    assert "p0_ticker" in params
    assert "p1_ticker" in params


# ──────────────────────────────────────────────────────────────────────
# bulk_insert — NaN/Inf scrubbing
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_value", [float("nan"), float("inf"), float("-inf"), np.nan]
)
def test_bulk_insert_scrubs_nan_and_inf_to_none(fake_engine_factory, bad_value):
    """Postgres rejects NaN/±Inf in numeric columns. The sender must
    convert them to NULL (None) before binding."""
    from gcp.historical_signals import bulk_insert

    conn = fake_engine_factory()
    row = _make_row(datetime(2026, 4, 25, 10, 0), entry_rsi=bad_value)
    bulk_insert(pd.DataFrame([row]), chunk_size=10)

    _, params = conn.calls[0]
    assert params["p0_entry_rsi"] is None


def test_bulk_insert_clean_for_json_handles_nan_in_extra(fake_engine_factory):
    """The `extra` JSONB column gets json.dumps'd. NaN must be scrubbed
    BEFORE serialization (not just at the json.default fallback) since
    a raw Python float('nan') would slip through."""
    from gcp.historical_signals import bulk_insert
    import json

    conn = fake_engine_factory()
    row = _make_row(
        datetime(2026, 4, 25, 10, 0),
        extra={"setup": "2U", "pct_to_target": float("nan")},
    )
    bulk_insert(pd.DataFrame([row]), chunk_size=10)

    _, params = conn.calls[0]
    extra_json = params["p0_extra"]
    assert extra_json is not None
    # The json string should not contain "NaN" — Postgres rejects it
    assert "NaN" not in extra_json
    decoded = json.loads(extra_json)
    assert decoded["pct_to_target"] is None


# ──────────────────────────────────────────────────────────────────────
# _clean_for_json + _json_default helpers
# ──────────────────────────────────────────────────────────────────────


def test_clean_for_json_replaces_nan_inf_with_none():
    from gcp.historical_signals import _clean_for_json

    cleaned = _clean_for_json({
        "a": 1.5,
        "b": float("nan"),
        "c": float("inf"),
        "d": float("-inf"),
        "e": None,
        "f": "ok",
    })
    assert cleaned == {"a": 1.5, "b": None, "c": None, "d": None,
                       "e": None, "f": "ok"}


def test_json_default_unwraps_numpy_nan_to_none():
    """numpy.float64('nan').item() returns Python float('nan') which
    json.dumps would write as 'NaN' — invalid for Postgres JSONB."""
    from gcp.historical_signals import _json_default

    assert _json_default(np.float64("nan")) is None
    # Non-NaN numpy scalars still unwrap to plain Python types
    assert _json_default(np.int64(42)) == 42
    assert _json_default(np.float64(1.5)) == 1.5


def test_json_default_handles_pandas_timestamp():
    from gcp.historical_signals import _json_default

    ts = pd.Timestamp("2026-04-25 10:30:00")
    result = _json_default(ts)
    assert isinstance(result, str)
    assert result.startswith("2026-04-25T10:30:00")


# ──────────────────────────────────────────────────────────────────────
# bulk_insert — column order + extra serialization
# ──────────────────────────────────────────────────────────────────────


def test_bulk_insert_extra_dict_is_serialized_to_json(fake_engine_factory):
    """`extra` arrives as a Python dict and goes out as a JSON string."""
    from gcp.historical_signals import bulk_insert

    conn = fake_engine_factory()
    row = _make_row(datetime(2026, 4, 25, 10, 0), extra={"a": 1, "b": "x"})
    bulk_insert(pd.DataFrame([row]), chunk_size=10)

    _, params = conn.calls[0]
    extra = params["p0_extra"]
    assert isinstance(extra, str)
    assert '"a": 1' in extra and '"b": "x"' in extra


def test_bulk_insert_falsy_extra_becomes_null(fake_engine_factory):
    """Empty dicts / None for `extra` skip serialization → None binding
    so the JSONB column accepts NULL rather than the string 'null'."""
    from gcp.historical_signals import bulk_insert

    conn = fake_engine_factory()
    row = _make_row(datetime(2026, 4, 25, 10, 0), extra={})
    bulk_insert(pd.DataFrame([row]), chunk_size=10)
    _, params = conn.calls[0]
    assert params["p0_extra"] is None


def test_bulk_insert_drops_unknown_columns(fake_engine_factory):
    """The DataFrame is reduced to COLS before the rows are dict-ified
    so callers can pass extra columns (e.g. internal scratchpads)
    without breaking the bind shape."""
    from gcp.historical_signals import bulk_insert, COLS

    conn = fake_engine_factory()
    row = _make_row(datetime(2026, 4, 25, 10, 0))
    row["debug_scratch"] = "ignore me"
    bulk_insert(pd.DataFrame([row]), chunk_size=10)

    _, params = conn.calls[0]
    expected_keys = {f"p0_{c}" for c in COLS}
    assert set(params.keys()) == expected_keys


# ──────────────────────────────────────────────────────────────────────
# latest_entry_time + delete_for_ticker — sanity smoke
# ──────────────────────────────────────────────────────────────────────


def test_latest_entry_time_returns_none_when_no_rows(monkeypatch):
    """Phase 0.7's latest_entry_time uses row[0] (positional) rather
    than row.t (attribute) — pg8000's Row implementation wraps aliased
    aggregates and breaks attribute access. The fake row must support
    __getitem__(0) → None to model the no-rows case."""
    from gcp import historical_signals as hs_module

    # Tuple is the simplest "indexable" thing that mirrors a real
    # Postgres row of (None,) — what fetchone() returns when MAX() over
    # an empty table.
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (None,)
    eng = MagicMock()
    eng.connect.return_value.__enter__.return_value = conn
    monkeypatch.setattr(hs_module, "get_engine", lambda: eng)

    assert hs_module.latest_entry_time("IWM") is None


def test_delete_for_ticker_returns_rowcount(monkeypatch):
    from gcp import historical_signals as hs_module

    conn = MagicMock()
    conn.execute.return_value.rowcount = 42
    eng = MagicMock()
    eng.begin.return_value.__enter__.return_value = conn
    monkeypatch.setattr(hs_module, "get_engine", lambda: eng)

    assert hs_module.delete_for_ticker("iwm") == 42
    # Ticker is upper-cased in the bind params
    call_args = conn.execute.call_args
    assert call_args[0][1] == {"t": "IWM"}
