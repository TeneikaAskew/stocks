"""
Cloud SQL helpers for the ``historical_signals`` table.

Single-purpose module — read/write the table that holds the output of
``trading_analysis.py``. Idempotent inserts via ``ON CONFLICT (ticker,
entry_time) DO NOTHING``.

Use cases:
    >>> latest = latest_entry_time('IWM')
    >>> bulk_insert(signal_rows)             # doctest: +SKIP
    >>> delete_for_ticker('IWM')             # --force backfill mode
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Iterable, Optional

import pandas as pd
from sqlalchemy import text

from gcp.database import get_engine

logger = logging.getLogger(__name__)

# Columns the table accepts for INSERT, in the order our DataFrame should
# present them. ``inserted_at`` defaults to NOW() so we don't pass it.
# ``strategy`` was added in Phase 0.7 — defaults to 'momentum' on the
# server-side via the column DEFAULT, but we always send it explicitly
# from the application layer so the value is auditable in CI logs.
COLS = (
    'ticker',
    'entry_time',
    'strategy',
    'trade_type',
    'entry_price',
    'signal_strength',
    'conditions_met',
    'duration_minutes',
    'return_pct',
    'best_return',
    'best_window_min',
    'return_5min',
    'return_10min',
    'return_15min',
    'return_20min',
    'return_30min',
    'return_45min',
    'return_60min',
    'entry_rsi',
    'entry_ema9',
    'entry_ema20',
    'entry_vwap',
    'entry_volume',
    'extra',
)


def latest_entry_time(ticker: str, strategy: Optional[str] = None) -> Optional[datetime]:
    """Return MAX(entry_time) for a ticker, or None when no rows exist.

    When ``strategy`` is given, scopes to that strategy's rows only —
    used by the resume-from-MAX(entry_time) path on the per-strategy
    backfill so 'momentum' resumes from the momentum cursor and
    'mean_reversion' resumes from its own cursor.

    Index by position (row[0]) instead of attribute (row.t) - pg8000's
    Row implementation returns a wrapped Row when an aliased aggregate
    is accessed by attribute name, which propagates back to callers as
    a Row instead of a datetime and breaks downstream arithmetic
    (TypeError: unsupported operand type(s) for +: 'Row' and
    'datetime.timedelta' in scripts/run_historical_signals.py).
    Positional indexing returns the scalar value reliably.
    """
    engine = get_engine()
    if strategy:
        sql = 'SELECT MAX(entry_time) FROM historical_signals WHERE ticker = :t AND strategy = :s'
        params = {'t': ticker.upper(), 's': strategy}
    else:
        sql = 'SELECT MAX(entry_time) FROM historical_signals WHERE ticker = :t'
        params = {'t': ticker.upper()}
    with engine.connect() as conn:
        row = conn.execute(text(sql), params).fetchone()
    return row[0] if row and row[0] else None


def delete_for_ticker(ticker: str, strategy: Optional[str] = None) -> int:
    """Hard-delete every row for a ticker. Used by ``--force``.

    When ``strategy`` is given, scopes the delete to that strategy's
    rows only — so `--force --strategy=mean_reversion` doesn't wipe
    the existing 'momentum' rows from prior backfills.
    """
    engine = get_engine()
    if strategy:
        sql = 'DELETE FROM historical_signals WHERE ticker = :t AND strategy = :s'
        params = {'t': ticker.upper(), 's': strategy}
    else:
        sql = 'DELETE FROM historical_signals WHERE ticker = :t'
        params = {'t': ticker.upper()}
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
    n = result.rowcount or 0
    logger.info('deleted %d rows for ticker=%s strategy=%s', n, ticker, strategy or 'ALL')
    return n


def bulk_insert(df: pd.DataFrame, chunk_size: int = 1000) -> tuple[int, int]:
    """Insert rows from ``df`` with ON CONFLICT DO NOTHING.

    Returns ``(attempted, inserted)``. Column names must match the table
    schema; ``extra`` is expected to be a Python ``dict``.

    Performance: builds one multi-row ``VALUES (...), (...), ...`` per
    chunk so each chunk is a single network round-trip. The previous
    ``execute(stmt, [list_of_dicts])`` path used pg8000 executemany which
    serialises one statement per row over the wire — ~6 rows/sec vs
    ~600 rows/sec with this multi-row form.

    Postgres's bind-parameter limit is 65535. With 23 columns the safe
    cap is ~2800; we default to 1000 for headroom.
    """
    if df.empty:
        return (0, 0)

    df = df[list(COLS)].copy()  # enforce column order, drop unknowns
    if 'extra' in df.columns:
        df['extra'] = df['extra'].apply(
            lambda x: json.dumps(_clean_for_json(x), default=_json_default) if x else None
        )

    engine = get_engine()
    attempted = 0
    inserted = 0
    col_list = ', '.join(COLS)

    with engine.begin() as conn:
        for chunk_start in range(0, len(df), chunk_size):
            chunk = df.iloc[chunk_start:chunk_start + chunk_size]
            records = chunk.to_dict(orient='records')

            # Build one VALUES tuple per row, with unique parameter names.
            value_tuples: list[str] = []
            params: dict = {}
            for i, row in enumerate(records):
                row_keys = []
                for c in COLS:
                    key = f'p{i}_{c}'
                    val = row[c]
                    # NaN/Inf scalars from pandas → None
                    if isinstance(val, float) and (pd.isna(val) or val in (float('inf'), float('-inf'))):
                        val = None
                    params[key] = val
                    row_keys.append(f':{key}')
                value_tuples.append(f'({", ".join(row_keys)})')

            sql = text(
                f'INSERT INTO historical_signals ({col_list}) VALUES '
                + ', '.join(value_tuples)
                + ' ON CONFLICT (ticker, entry_time, strategy) DO NOTHING'
            )
            result = conn.execute(sql, params)
            attempted += len(records)
            inserted += result.rowcount or 0

    logger.info('bulk_insert: attempted=%d inserted=%d (skipped=%d)',
                attempted, inserted, attempted - inserted)
    return (attempted, inserted)


def _json_default(o):
    """JSON encoder fallback for numpy / pandas scalars."""
    if hasattr(o, 'item'):  # numpy scalars
        v = o.item()
        # numpy NaN unwraps to Python float('nan') — replace with None
        # so the resulting JSON is Postgres-valid (Postgres rejects NaN).
        if isinstance(v, float) and pd.isna(v):
            return None
        return v
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


def _clean_for_json(d: dict) -> dict:
    """Replace NaN/Inf values in a dict with None — Postgres JSONB rejects
    them. Numpy NaN survives the json.dumps default-fallback path but a
    raw Python float('nan') in the dict slips through, so scrub here."""
    out = {}
    for k, v in d.items():
        if isinstance(v, float) and (pd.isna(v) or v in (float('inf'), float('-inf'))):
            out[k] = None
        else:
            out[k] = v
    return out


def load_intraday_bars(
    ticker: str,
    start: datetime,
    end: Optional[datetime] = None,
) -> pd.DataFrame:
    """Load 1-min bars from market_data_intraday into the column shape
    that MarketAnalyzer expects: Time / Open / High / Low / Last / Volume.

    ``end`` defaults to NOW(). ``start`` is inclusive, ``end`` exclusive.
    """
    engine = get_engine()
    params = {'t': ticker.upper(), 'start': start}
    where = 'ticker = :t AND ts >= :start'
    if end is not None:
        where += ' AND ts < :end'
        params['end'] = end

    sql = text(f"""
        SELECT ts AS "Time",
               open AS "Open",
               high AS "High",
               low AS "Low",
               close AS "Last",
               volume AS "Volume"
        FROM market_data_intraday
        WHERE {where}
        ORDER BY ts
    """)
    df = pd.read_sql(sql, engine, params=params)
    df['Time'] = pd.to_datetime(df['Time'])
    return df
