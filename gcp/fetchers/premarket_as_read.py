"""The SPY, QQQ and IWM premarket bars as each refresh run read them.

FEAT-DATA-001, docs/superpowers/specs/2026-11-16-feat-data-001-premarket-reads-as-read.md:
AlphaVantage revises a session's one-minute bars after the close (#2027), so
every bar in ``market_data_intraday`` is a later, revised read and a replay of
a morning cannot reproduce what the brief was built from. The refresh job
(``fetch_premarket_refresh``) therefore keeps, after its upsert, one immutable
gzip object per ticker per run in the existing bucket:

    gs://<GCS_BUCKET>/premarket-as-read/v1/<YYYY-MM-DD>/<TICKER>/<fetched_at>.json.gz

holding the session's bars as parsed, the request as sent (without the key)
and the values the run upserted for the ticker.

This module owns the record's format and its reader. Its top level imports
the standard library, pandas and ``lib.eastern_time`` only; it never imports
``gcp.database`` or ``requests`` (R7), so the reader runs where neither can.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime
from typing import Optional, Sequence

import pandas as pd

from lib.eastern_time import as_utc_instant, require_aware

PREFIX = 'premarket-as-read/v1'
RECORD_VERSION = 1
AS_READ_TICKERS = ('SPY', 'QQQ', 'IWM')
# The whole record step's budget, in seconds (spec Design 3).
AS_READ_DEADLINE_S = 10
CSV_HEADER = 'ts,open,high,low,close,volume'

# The columns of a frame as fetch_market_data.fetch_minute_bars returns it.
_VENDOR_COLUMNS = ('Open', 'High', 'Low', 'Close', 'Volume')
# The vendor's own key: naive Eastern wall time.
_TS_FORMAT = '%Y-%m-%d %H:%M:%S'
_RECORD_KEYS = frozenset({
    'version', 'ticker', 'session_date', 'fetched_at', 'execution', 'task_attempt',
    'vendor_params', 'bar_count', 'newest_bar', 'bars_csv', 'bars_sha256', 'snapshot'})


def _utc_text(value: datetime, name: str) -> str:
    """An aware instant as ISO 8601 in UTC with microseconds."""
    return as_utc_instant(require_aware(value, name=name)).isoformat(timespec='microseconds')


def object_name(ticker: str, session_date: date, fetched_at: datetime) -> str:
    """The object one run's read of *ticker* is stored under. *fetched_at*
    must be aware; it is named in UTC, so the 08:20 and the 09:20 reads of a
    date are two objects."""
    instant = as_utc_instant(require_aware(fetched_at, name='fetched_at'))
    return (f"{PREFIX}/{session_date.isoformat()}/{ticker}/"
            f"{instant.strftime('%Y%m%dT%H%M%S%fZ')}.json.gz")


def _csv_lines(bars: pd.DataFrame) -> list[str]:
    """One line per bar, in time order. An empty read, the columnless
    ``pd.DataFrame()`` fetch_minute_bars returns when the vendor has no bars
    for the day included, has none. A non-empty frame without the vendor's
    five columns raises: it is not a read."""
    if len(bars.index) == 0:
        return []
    frame = bars.loc[:, list(_VENDOR_COLUMNS)].sort_index(kind='mergesort')
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        raise ValueError('the bars must be keyed by the vendor\'s naive Eastern wall time; '
                         f'got an index in {index.tz}')
    return [f"{ts.strftime(_TS_FORMAT)},{float(o)!r},{float(h)!r},{float(lo)!r},"
            f"{float(c)!r},{int(v)}"
            for ts, o, h, lo, c, v in zip(index, frame['Open'], frame['High'], frame['Low'],
                                          frame['Close'], frame['Volume'])]


def bars_csv(bars: pd.DataFrame) -> str:
    """The bars as the record's text: ``CSV_HEADER`` and one line a bar in
    time order, every line ending in a newline. ``ts`` as the vendor keys it,
    each price as Python's ``repr`` of the parsed float, volume as an
    integer. The caller's frame is not modified."""
    return '\n'.join([CSV_HEADER, *_csv_lines(bars)]) + '\n'


def _json_value(key: str, value):
    """One bound value as JSON: a date as ``YYYY-MM-DD``, an instant as ISO
    8601 with its offset and microseconds, the filter record parsed from its
    JSON text, a numpy scalar as the Python value it holds."""
    if value is None:
        return None
    if key == 'pre_filter_params' and isinstance(value, str):
        return json.loads(value)
    if isinstance(value, datetime):
        return require_aware(value, name=key).isoformat(timespec='microseconds')
    if isinstance(value, date):
        return value.isoformat()
    item = getattr(value, 'item', None)
    if callable(item) and type(value).__module__ == 'numpy':
        return item()
    return value


def snapshot_record(row: Optional[dict], keys: Sequence[str]) -> Optional[dict]:
    """The values the run bound for one ticker in ``upsert_premarket``,
    projected on *keys* (the job's ``_UPSERT_KEYS``) and made JSON; None when
    the run computed no row for the ticker."""
    if row is None:
        return None
    return {key: _json_value(key, row.get(key)) for key in keys}


def _record(*, ticker: str, session_date: date, fetched_at: datetime, bars: pd.DataFrame,
            vendor_params: dict, snapshot: Optional[dict], execution: Optional[str],
            task_attempt: Optional[str]) -> dict:
    lines = _csv_lines(bars)
    text = '\n'.join([CSV_HEADER, *lines]) + '\n'
    return {
        'version': RECORD_VERSION,
        'ticker': ticker,
        'session_date': session_date.isoformat(),
        'fetched_at': _utc_text(fetched_at, 'fetched_at'),
        'execution': execution,
        'task_attempt': task_attempt,
        'vendor_params': dict(vendor_params),
        'bar_count': len(lines),
        'newest_bar': lines[-1].split(',', 1)[0] if lines else None,
        'bars_csv': text,
        'bars_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'snapshot': snapshot,
    }


def _encode(record: dict) -> bytes:
    """JSON with sorted keys and no spaces, gzipped with mtime 0: equal
    input gives equal bytes."""
    text = json.dumps(record, sort_keys=True, separators=(',', ':'))
    return gzip.compress(text.encode('utf-8'), mtime=0)


def build_record(*, ticker: str, session_date: date, fetched_at: datetime, bars: pd.DataFrame,
                 vendor_params: dict, snapshot: Optional[dict], execution: Optional[str],
                 task_attempt: Optional[str]) -> bytes:
    """The object's bytes for one run's read of *ticker* (spec Design 2)."""
    return _encode(_record(ticker=ticker, session_date=session_date, fetched_at=fetched_at,
                           bars=bars, vendor_params=vendor_params, snapshot=snapshot,
                           execution=execution, task_attempt=task_attempt))


def read_record(data: bytes) -> tuple[dict, pd.DataFrame]:
    """The record's header (every key but ``bars_csv``) and its bars, with
    columns ``ts`` (naive Eastern ``Timestamp``), ``open``, ``high``, ``low``,
    ``close`` (float) and ``volume`` (int64).

    Raises ValueError, naming the expected and the found sha256, when
    ``bars_csv`` is not the text the record hashed, before any row is parsed;
    and ValueError when the record is not a version 1 record or its bars do
    not parse."""
    doc = json.loads(gzip.decompress(data))
    if not isinstance(doc, dict) or set(doc) != _RECORD_KEYS:
        raise ValueError('not a premarket as-read record: its keys are not the version 1 keys')
    if doc['version'] != RECORD_VERSION:
        raise ValueError(f"record version {doc['version']!r}; this reader reads {RECORD_VERSION}")
    text = doc['bars_csv']
    found = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if found != doc['bars_sha256']:
        raise ValueError(f"bars_csv has sha256 {found}; the record says {doc['bars_sha256']}")
    header = {key: value for key, value in doc.items() if key != 'bars_csv'}

    lines = text.split('\n')
    if lines[0] != CSV_HEADER or lines[-1] != '':
        raise ValueError('bars_csv does not start with the header line and end with a newline')
    rows = [line.split(',') for line in lines[1:-1]]
    if any(len(row) != 6 for row in rows):
        raise ValueError('bars_csv has a line without six fields')
    if len(rows) != doc['bar_count']:
        raise ValueError(f"bars_csv has {len(rows)} bars; the record says {doc['bar_count']}")
    bars = pd.DataFrame({
        'ts': pd.Series(pd.to_datetime([row[0] for row in rows], format=_TS_FORMAT),
                        dtype='datetime64[ns]'),
        **{name: pd.Series([float(row[i]) for row in rows], dtype='float64')
           for i, name in enumerate(('open', 'high', 'low', 'close'), start=1)},
        'volume': pd.Series([int(row[5]) for row in rows], dtype='int64'),
    })
    return header, bars
