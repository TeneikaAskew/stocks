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
COLS = (
    'ticker',
    'entry_time',
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


def latest_entry_time(ticker: str) -> Optional[datetime]:
    """Return MAX(entry_time) for a ticker, or None when no rows exist."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text('SELECT MAX(entry_time) AS t FROM historical_signals WHERE ticker = :t'),
            {'t': ticker.upper()},
        ).fetchone()
    return row.t if row and row.t else None


def delete_for_ticker(ticker: str) -> int:
    """Hard-delete every row for a ticker. Used by ``--force``."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text('DELETE FROM historical_signals WHERE ticker = :t'),
            {'t': ticker.upper()},
        )
    n = result.rowcount or 0
    logger.info('deleted %d rows for ticker=%s', n, ticker)
    return n


def bulk_insert(df: pd.DataFrame, chunk_size: int = 5000) -> tuple[int, int]:
    """Insert rows from ``df`` with ON CONFLICT DO NOTHING.

    Returns ``(attempted, inserted)``. The ``ticker`` and column names must
    already match the table schema. The ``extra`` column (JSONB) is expected
    to be a Python ``dict``; we serialize to JSON here.
    """
    if df.empty:
        return (0, 0)

    df = df[list(COLS)].copy()  # enforce column order, drop unknowns
    if 'extra' in df.columns:
        df['extra'] = df['extra'].apply(
            lambda x: json.dumps(_clean_for_json(x), default=_json_default) if x else None
        )

    placeholders = ', '.join(f':{c}' for c in COLS)
    sql = text(
        f'INSERT INTO historical_signals ({", ".join(COLS)}) '
        f'VALUES ({placeholders}) '
        'ON CONFLICT (ticker, entry_time) DO NOTHING'
    )

    engine = get_engine()
    attempted = 0
    inserted = 0
    with engine.begin() as conn:
        for start in range(0, len(df), chunk_size):
            chunk = df.iloc[start:start + chunk_size]
            params = chunk.to_dict(orient='records')
            for p in params:
                # NaN → None (psycopg2 / pg8000 don't auto-convert)
                for k, v in list(p.items()):
                    if isinstance(v, float) and pd.isna(v):
                        p[k] = None
            result = conn.execute(sql, params)
            attempted += len(params)
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
