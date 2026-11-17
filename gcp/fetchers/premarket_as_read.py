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
import logging
import os
import time
from datetime import date, datetime, time as dt_time
from typing import Any, Callable, Mapping, NamedTuple, Optional, Sequence

import pandas as pd

from lib.eastern_time import (
    TRUE_UTC_FROM,
    as_utc_instant,
    eastern_bounds_utc,
    eastern_index_to_utc,
    market_date,
    require_aware,
)

log = logging.getLogger(__name__)

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


class AsRead(NamedTuple):
    """One run's read of one ticker: the frame fetch_minute_data returned,
    the instant it was fetched (the job's ``pre_fetched_at``) and the request
    it sent, without the key (``fetch_market_data.minute_bars_request``)."""
    bars: pd.DataFrame
    fetched_at: datetime
    vendor_params: dict


def _ordered(tickers) -> list[str]:
    rank = {ticker: i for i, ticker in enumerate(AS_READ_TICKERS)}
    return sorted(tickers, key=lambda t: (rank.get(t, len(rank)), t))


def write_records(bucket_factory: Callable[[], Any], session_date: date,
                  reads: dict[str, AsRead], snapshots: dict[str, Optional[dict]], *,
                  clock: Optional[Callable[[], float]] = None,
                  deadline_s: float = AS_READ_DEADLINE_S,
                  env: Mapping[str, str] = os.environ
                  ) -> tuple[list[str], list[tuple[str, str]]]:
    """Write one record per read, each once, within one deadline (spec
    Design 3). Returns the object names written and the ``(ticker, reason)``
    failures; the caller exits non-zero when there is a failure (R4).

    The clock (``time.monotonic`` when None, looked up per call) is read once
    before the bucket is built and once before each ticker's write. Each
    write is one attempt: ``retry=None`` and a ``timeout`` of what is left of
    *deadline_s*, so a transient error is a failed record and the step cannot
    run past its deadline. A ticker reached with nothing left fails with
    reason ``deadline`` and is not written. A write that raises (an object
    already at the name included: ``if_generation_match=0``, never
    overwritten) fails that ticker and the next one continues; a bucket that
    cannot be built fails every ticker. With no reads nothing is built.
    """
    now = clock if clock is not None else time.monotonic
    execution = env.get('CLOUD_RUN_EXECUTION')
    task_attempt = env.get('CLOUD_RUN_TASK_ATTEMPT')
    tickers = _ordered(reads)
    written: list[str] = []
    failed: list[tuple[str, str]] = []
    if not tickers:
        log.info('as_read_records written=0 failed=0 session=%s', session_date.isoformat())
        return written, failed

    def fail(ticker: str, reason: str) -> None:
        failed.append((ticker, reason))
        log.error('as_read_failed ticker=%s reason=%s', ticker, reason)

    start = now()
    try:
        bucket = bucket_factory()
    except Exception as exc:  # noqa: BLE001 every record fails, by name, and the run exits 1
        for ticker in tickers:
            fail(ticker, f'{type(exc).__name__}: {exc}')
        return written, failed

    for ticker in tickers:
        read = reads[ticker]
        try:
            name = object_name(ticker, session_date, read.fetched_at)
            record = _record(ticker=ticker, session_date=session_date,
                             fetched_at=read.fetched_at, bars=read.bars,
                             vendor_params=read.vendor_params, snapshot=snapshots.get(ticker),
                             execution=execution, task_attempt=task_attempt)
            data = _encode(record)
        except Exception as exc:  # noqa: BLE001 a record that cannot be built is a failed record
            fail(ticker, f'{type(exc).__name__}: {exc}')
            continue
        left = deadline_s - (now() - start)
        if left <= 0:
            fail(ticker, 'deadline')
            continue
        try:
            bucket.write(name, data, if_generation_match=0, timeout=left, retry=None)
        except Exception as exc:  # noqa: BLE001 counted, logged and exits 1 (R4)
            fail(ticker, f'{type(exc).__name__}: {exc}')
            continue
        written.append(name)
        log.info('as_read_written object=%s bar_count=%d newest_bar=%s bars_sha256=%s',
                 name, record['bar_count'], record['newest_bar'], record['bars_sha256'])
    log.info('as_read_records written=%d failed=%d session=%s',
             len(written), len(failed), session_date.isoformat())
    return written, failed


# ── The comparison (read-only, spec Design 5) ──────────────────────────────

_PRICES = ('open', 'high', 'low', 'close')
# A price differs when the two values are this far apart or more:
# market_data_intraday prices are DOUBLE PRECISION and the vendor's carry at
# most four decimals.
PRICE_TOLERANCE = 0.00005


def _price_differs(a, b) -> bool:
    if pd.isna(a) or pd.isna(b):
        return not (pd.isna(a) and pd.isna(b))
    # Rounded to 9 decimals so two prices 0.00005 apart in decimal are not
    # read as 0.0000499999 apart in binary.
    return round(abs(float(a) - float(b)), 9) >= PRICE_TOLERANCE


def _volume_differs(a, b) -> bool:
    if pd.isna(a) or pd.isna(b):
        return not (pd.isna(a) and pd.isna(b))
    return int(a) != int(b)


def _counts(read: pd.DataFrame, stored: pd.DataFrame) -> dict:
    a, b = read.set_index('ts'), stored.set_index('ts')
    both = a.index.intersection(b.index).sort_values()
    per_field = {
        name: [(_volume_differs if name == 'volume' else _price_differs)(
            a.at[ts, name], b.at[ts, name]) for ts in both]
        for name in (*_PRICES, 'volume')}
    return {
        'as_read_bars': len(a),
        'stored_bars': len(b),
        'matched': len(both),
        'only_as_read': len(a.index.difference(b.index)),
        'only_stored': len(b.index.difference(a.index)),
        'differing': sum(any(flags) for flags in zip(*per_field.values())),
        **{f'differ_{name}': sum(flags) for name, flags in per_field.items()},
    }


def compare_bars(as_read: pd.DataFrame, stored: pd.DataFrame, session_date: date) -> dict:
    """Count how the bars a run read differ from the stored bars of its
    session.

    *as_read* is ``read_record``'s frame (``ts`` naive Eastern, as the vendor
    keyed it); *stored* has ``ts`` as aware instants and the five value
    columns, as ``./scripts/db_query_cr.sh`` or ``read_bars`` give them.
    Stored bars are kept when their Eastern date is *session_date* and they
    are at or before the newest bar read, so bars the vendor had not yet
    published are not counted (a read with no bars keeps none). A price
    differs at ``PRICE_TOLERANCE`` or more, a volume when the integers
    differ, and a missing value beside a present one is a difference.

    Returns ``as_read_bars``, ``stored_bars``, ``matched``, ``only_as_read``,
    ``only_stored``, ``differing`` (a matched bar with any field different),
    ``differ_open`` ... ``differ_volume``, and the same eleven under
    ``premarket`` for the bars from 04:00 to 09:29 Eastern.

    Raises ValueError for a session before ``lib.eastern_time.TRUE_UTC_FROM``
    (its stored instants are not known to be UTC), for a stored ``ts``
    without a zone, and for a ``ts`` that appears twice on either side.
    """
    if session_date < TRUE_UTC_FROM:
        raise ValueError(
            f"session {session_date.isoformat()} is before TRUE_UTC_FROM "
            f"({TRUE_UTC_FROM.isoformat()}): its stored instants are not known to be UTC")
    read = as_read.loc[:, ['ts', *_PRICES, 'volume']].copy()
    read['ts'] = eastern_index_to_utc(pd.DatetimeIndex(read['ts']))
    stored_ts = pd.DatetimeIndex(stored['ts'])
    if stored_ts.tz is None:
        raise ValueError('stored ts has no zone: which instant it names cannot be known')
    kept = stored.loc[:, ['ts', *_PRICES, 'volume']].copy()
    kept['ts'] = stored_ts.tz_convert('UTC')
    for side, frame in (('as-read', read), ('stored', kept)):
        if frame['ts'].duplicated().any():
            raise ValueError(f'the {side} bars hold a ts twice')

    in_session = [market_date(ts) == session_date for ts in kept['ts']]
    if len(read):
        newest = read['ts'].max()
        kept = kept.loc[pd.Series(in_session, index=kept.index) & (kept['ts'] <= newest)]
    else:
        kept = kept.iloc[0:0]

    start, end = eastern_bounds_utc(session_date, dt_time(4, 0), dt_time(9, 30))

    def premarket(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.loc[(frame['ts'] >= start) & (frame['ts'] < end)]

    return {**_counts(read, kept), 'premarket': _counts(premarket(read), premarket(kept))}
