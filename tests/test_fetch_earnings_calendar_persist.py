"""Unit tests for `scripts/fetch_earnings_calendar.py::persist_to_cloud_sql`.

The earnings_calendar table has BIGINT columns (stock_volume,
options_volume, open_interest) that pandas widens to float64 when
mixing UW (int values) with Yahoo (NULL values) via concat. Float
values then serialize as "31193563.0" — Postgres rejects that for
BIGINT with 22P02 invalid input syntax. The persist layer must coerce
those columns to plain Python int (or None) before pg8000 sees them.

Tests stub `gcp.database.upsert_dataframe` so we can inspect the
DataFrame the persist function would have sent over the wire.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def captured_persist(monkeypatch):
    """Stub the SQL upsert and capture the DataFrame that would have
    been written. Returns a dict that gets populated when persist runs."""
    # Make scripts/ importable when the test runs in isolation.
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from gcp import database

    captured = {'df': None, 'table': None, 'conflict_cols': None, 'n': 0}

    def fake_upsert(df, table, conflict_cols=None, **kw):
        captured['df'] = df.copy()
        captured['table'] = table
        captured['conflict_cols'] = list(conflict_cols or [])
        return len(df)

    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'upsert_dataframe', fake_upsert)
    return captured


def _persist(df: pd.DataFrame) -> int:
    from scripts.fetch_earnings_calendar import persist_to_cloud_sql
    return persist_to_cloud_sql(df)


def test_bigint_columns_coerce_float_to_int(captured_persist):
    """UW row has stock_volume=31193563 as int; Yahoo row has it as
    NULL. After concat pandas reports the column as float64 and the
    UW value reads `31193563.0`. The coercion must turn it back into
    a plain Python int so pg8000 emits a BIGINT-compatible literal."""
    df = pd.DataFrame([
        {'date': '2026-04-30', 'ticker': 'AAPL', 'source': 'UnusualWhales',
         'strategy': '', 'stock_volume': 31193563.0,
         'options_volume': 1166736.0, 'open_interest': 421998.0},
        # NULL stock_volume forces float widening on the column.
        {'date': '2026-04-30', 'ticker': 'AAPL', 'source': 'Yahoo',
         'strategy': '', 'stock_volume': None,
         'options_volume': None, 'open_interest': None},
    ])
    n = _persist(df)
    assert n == 2
    out = captured_persist['df']

    aapl_uw = out[(out['ticker'] == 'AAPL') &
                  (out['data_source'] == 'unusual_whales')].iloc[0]
    aapl_yh = out[(out['ticker'] == 'AAPL') &
                  (out['data_source'] == 'yahoo')].iloc[0]

    # UW row: int, no float trailing
    for col in ('stock_volume', 'options_volume', 'open_interest'):
        v = aapl_uw[col]
        assert isinstance(v, int), (
            f"{col} must be Python int after coercion; got {type(v).__name__}={v!r}"
        )
        # And specifically NOT a float — that's the bug we're fixing.
        assert not isinstance(v, float)

    # Yahoo row: None (Postgres NULL), not NaN, not 0
    for col in ('stock_volume', 'options_volume', 'open_interest'):
        v = aapl_yh[col]
        assert v is None, (
            f"{col} must be None for null source; got {type(v).__name__}={v!r}"
        )


def test_bigint_coercion_preserves_value(captured_persist):
    """Coercion must not truncate or round — the int(31193563.0) round-
    trip should land at exactly 31193563."""
    df = pd.DataFrame([{
        'date': '2026-04-30', 'ticker': 'AAPL', 'source': 'UnusualWhales',
        'strategy': '', 'stock_volume': 31193563.0,
        'options_volume': 1166736.0, 'open_interest': 421998.0,
    }])
    _persist(df)
    out = captured_persist['df']
    assert out.iloc[0]['stock_volume'] == 31193563
    assert out.iloc[0]['options_volume'] == 1166736
    assert out.iloc[0]['open_interest'] == 421998


def test_no_bigint_columns_does_not_break(captured_persist):
    """Yahoo-only frame has no UW-specific columns — coercion must
    no-op for missing columns."""
    df = pd.DataFrame([{
        'date': '2026-04-30', 'ticker': 'AAPL', 'source': 'Yahoo',
        'strategy': '', 'eps_estimate': 1.62, 'eps_actual': 1.65,
    }])
    n = _persist(df)
    assert n == 1
    out = captured_persist['df']
    assert 'stock_volume' not in out.columns
    assert out.iloc[0]['ticker'] == 'AAPL'


def test_nan_in_bigint_column_becomes_none(captured_persist):
    """If pandas surfaces NaN (not None) for a missing UW value, the
    coercion must still produce None — not float('nan'), not 0."""
    df = pd.DataFrame([{
        'date': '2026-04-30', 'ticker': 'AAPL', 'source': 'UnusualWhales',
        'strategy': '', 'stock_volume': float('nan'),
        'options_volume': 1166736.0, 'open_interest': float('nan'),
    }])
    _persist(df)
    out = captured_persist['df']
    row = out.iloc[0]
    assert row['stock_volume'] is None
    assert row['options_volume'] == 1166736  # the only non-NaN
    assert row['open_interest'] is None
