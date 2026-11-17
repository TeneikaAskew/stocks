"""The premarket bars as each refresh run read them (FEAT-DATA-001).

docs/superpowers/specs/2026-11-16-feat-data-001-premarket-reads-as-read.md:
the vendor revises a session's one-minute bars after the close, so the
refresh job keeps, for SPY, QQQ and IWM, the bars it read, the request it
sent and the values it upserted, one object per ticker per run.

Hermetic: the vendor is a patched ``requests.get``; nothing here reaches a
network, a bucket or a database.
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from gcp.fetchers import fetch_market_data

SESSION = date(2026, 11, 16)
FETCHED_AT = datetime(2026, 11, 16, 13, 20, 1, 123456, tzinfo=timezone.utc)

# R1: the four bars of the spec's Design 2, as fetch_minute_data returns them
# (naive Eastern index, capitalised columns, the ticker column it adds).
R1_ROWS = [
    ('2026-11-16 04:00:00', 752.5, 752.6, 752.4, 752.5, 500),
    ('2026-11-16 04:01:00', 752.4, 752.5, 752.3, 752.4, 300),
    ('2026-11-16 04:02:00', 752.3, 752.4, 752.02, 752.3, 968),
    ('2026-11-16 04:03:00', 752.2, 752.3, 752.1, 752.2, 10),
]
R1_CSV = ('ts,open,high,low,close,volume\n'
          '2026-11-16 04:00:00,752.5,752.6,752.4,752.5,500\n'
          '2026-11-16 04:01:00,752.4,752.5,752.3,752.4,300\n'
          '2026-11-16 04:02:00,752.3,752.4,752.02,752.3,968\n'
          '2026-11-16 04:03:00,752.2,752.3,752.1,752.2,10\n')
R1_SHA256 = '538f5b83f2e52f65f93758d5e15b787eb939c7fcb42227e1794b03cdae660ee5'


def vendor_frame(rows, ticker='SPY') -> pd.DataFrame:
    """Bars in the shape fetch_minute_bars returns them."""
    df = pd.DataFrame([r[1:] for r in rows], columns=['Open', 'High', 'Low', 'Close', 'Volume'],
                      index=pd.DatetimeIndex([r[0] for r in rows], name='timestamp'))
    df['Volume'] = df['Volume'].astype('int64')
    df['ticker'] = ticker
    return df


def record_of(bars, **over) -> bytes:
    from gcp.fetchers import premarket_as_read as par

    kwargs = dict(ticker='SPY', session_date=SESSION, fetched_at=FETCHED_AT, bars=bars,
                  vendor_params=fetch_market_data.minute_bars_request('SPY', '2026-11'),
                  snapshot=None, execution=None, task_attempt=None)
    kwargs.update(over)
    return par.build_record(**kwargs)


def decode(data: bytes) -> dict:
    return json.loads(gzip.decompress(data))


class _Reply:
    """A vendor reply: ``json()`` returns the body given."""

    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_record_carries_the_request_as_sent(monkeypatch):
    """R2: the request the record stores is the request fetch_minute_bars
    sends, built by one function, without the key."""
    sent = []

    def fake_get(url, params=None, timeout=None):
        sent.append(dict(params))
        return _Reply({'Time Series (1min)': {
            '2026-11-16 04:00:00': {'1. open': '752.5', '2. high': '752.6',
                                    '3. low': '752.4', '4. close': '752.5',
                                    '5. volume': '500'}}})

    monkeypatch.setattr(fetch_market_data.requests, 'get', fake_get)
    bars, reason = fetch_market_data.fetch_minute_bars('SPY', '2026-11-16', 'TEST-KEY-not-real')
    assert reason == fetch_market_data.FETCH_OK and len(bars) == 1

    request = fetch_market_data.minute_bars_request('SPY', '2026-11')
    (params,) = sent
    assert params == {**request, 'apikey': 'TEST-KEY-not-real'}
    assert request['entitlement'] == 'realtime'
    assert request['adjusted'] == 'false'
    assert request['extended_hours'] == 'true'
    assert 'apikey' not in request

    # The record half: a refresh run stores that same request, and the key
    # appears nowhere in the object.
    from tests.fixtures.intraday_bars_bucket import MemoryBucket
    from tests.gcp.test_fetch_premarket_refresh import _as_read_name, _r1_bars, _run_refresh

    bucket = MemoryBucket()
    _run_refresh(monkeypatch, bars_for=_r1_bars, tickers=('SPY', 'QQQ', 'IWM'), bucket=bucket)
    text = gzip.decompress(bucket.objects[_as_read_name('SPY')]).decode()
    assert json.loads(text)['vendor_params'] == request
    assert 'TEST-KEY-not-real' not in text and 'apikey' not in text


def test_record_is_exact_and_deterministic():
    """R1: the record holds the bars as text whose sha256 is pinned, equal
    input gives equal bytes whatever the row order, and a record whose bars
    were changed after it was written is refused before any row is read."""
    from gcp.fetchers import premarket_as_read as par

    bars = vendor_frame(R1_ROWS)
    data = record_of(bars)
    doc = decode(data)
    assert doc['bars_csv'] == R1_CSV
    assert doc['bars_sha256'] == R1_SHA256
    assert doc['bar_count'] == 4
    assert doc['newest_bar'] == '2026-11-16 04:03:00'
    assert doc['version'] == 1 and doc['ticker'] == 'SPY'
    assert doc['session_date'] == '2026-11-16'
    assert doc['fetched_at'] == '2026-11-16T13:20:01.123456+00:00'
    assert doc['execution'] is None and doc['task_attempt'] is None and doc['snapshot'] is None
    assert set(doc) == {'version', 'ticker', 'session_date', 'fetched_at', 'execution',
                        'task_attempt', 'vendor_params', 'bar_count', 'newest_bar', 'bars_csv',
                        'bars_sha256', 'snapshot'}
    # JSON with sorted keys and no spaces, gzip with mtime 0
    assert gzip.decompress(data).decode() == json.dumps(doc, sort_keys=True, separators=(',', ':'))
    assert data[4:8] == b'\x00\x00\x00\x00'

    assert record_of(bars.iloc[::-1]) == data
    assert record_of(bars) == data

    header, got = par.read_record(data)
    assert set(header) == set(doc) - {'bars_csv'}
    want = pd.DataFrame({
        'ts': pd.to_datetime([r[0] for r in R1_ROWS]),
        'open': [r[1] for r in R1_ROWS], 'high': [r[2] for r in R1_ROWS],
        'low': [r[3] for r in R1_ROWS], 'close': [r[4] for r in R1_ROWS],
        'volume': pd.Series([r[5] for r in R1_ROWS], dtype='int64'),
    })
    pd.testing.assert_frame_equal(got, want)

    changed = dict(doc, bars_csv=doc['bars_csv'].replace('752.02', '752.03'))
    tampered = gzip.compress(json.dumps(changed, sort_keys=True, separators=(',', ':')).encode(),
                             mtime=0)
    with pytest.raises(ValueError, match=R1_SHA256):
        par.read_record(tampered)


@pytest.mark.parametrize('empty', [
    pd.DataFrame(),     # what fetch_minute_bars returns when the vendor has no bars for the day
    pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'],
                 index=pd.DatetimeIndex([], name='timestamp')),
], ids=['columnless', 'five_columns'])
def test_a_read_with_no_bars_is_recorded(empty):
    """R6: a read that returned no bars is on file: the header line alone."""
    from gcp.fetchers import premarket_as_read as par

    columns, shape = list(empty.columns), empty.shape
    data = record_of(empty)
    doc = decode(data)
    assert doc['bar_count'] == 0
    assert doc['newest_bar'] is None
    assert doc['bars_csv'] == 'ts,open,high,low,close,volume\n'
    assert doc['snapshot'] is None
    _, got = par.read_record(data)
    assert list(got.columns) == ['ts', 'open', 'high', 'low', 'close', 'volume'] and got.empty
    # the two shapes of "no bars" are the same record
    assert data == record_of(pd.DataFrame()) == record_of(
        pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume']))
    # the caller's frame is not touched
    assert list(empty.columns) == columns and empty.shape == shape


def test_object_size_is_bounded():
    """R8: a whole premarket of 330 bars with four-decimal prices, and a
    snapshot of every upserted key, is under 16 KiB."""
    from gcp.fetchers import fetch_premarket_refresh as fpr
    from gcp.fetchers import premarket_as_read as par

    start = pd.Timestamp('2026-11-16 04:00:00')
    rows = []
    for i in range(330):
        p = round(752.1234 + i / 10000, 4)
        rows.append(((start + pd.Timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S'),
                     p, round(p + 0.0517, 4), round(p - 0.0483, 4), round(p + 0.0121, 4),
                     1000 + 7 * i))
    row = {'ticker': 'SPY', 'date': SESSION, 'pre_high': 754.1234, 'pre_low': 751.0123,
           'pre_vwap': 752.7712, 'pre_volume': 1234567, 'gap_pct': 0.3456,
           'pre_range_atr': 0.4321, 'pre_fetched_at': FETCHED_AT,
           'pre_excluded_stale_prints': 0, 'pre_excluded_spikes': 1,
           'pre_filter_status': 'ok',
           'pre_filter_params': json.dumps({'pm_spike_atr': 0.5, 'pm_stale_print_atr': 0.25})}
    snapshot = par.snapshot_record(row, fpr._UPSERT_KEYS)
    assert set(snapshot) == set(fpr._UPSERT_KEYS) and len(snapshot) == 13
    data = record_of(vendor_frame(rows), snapshot=snapshot)
    assert decode(data)['bar_count'] == 330
    assert len(data) < 16384


def test_snapshot_record_is_the_bound_row_as_json():
    """Choice 2: the row as upsert_premarket binds it, on its keys, with the
    date, the fetch instant and the filter record made JSON; None stays None."""
    import numpy as np

    from gcp.fetchers import fetch_premarket_refresh as fpr
    from gcp.fetchers import premarket_as_read as par

    row = {'ticker': 'SPY', 'date': SESSION, 'pre_high': np.float64(752.6), 'pre_low': None,
           'pre_vwap': 752.4, 'pre_volume': np.int64(1778), 'gap_pct': None,
           'pre_range_atr': None, 'pre_fetched_at': FETCHED_AT,
           'pre_excluded_stale_prints': None, 'pre_excluded_spikes': None,
           'pre_filter_status': 'level_params_unavailable',
           'pre_filter_params': '{"b": 1, "a": [2]}', 'excluded_spike_prints': [1, 2]}
    got = par.snapshot_record(row, fpr._UPSERT_KEYS)
    assert list(got) == list(fpr._UPSERT_KEYS)          # the bound keys, nothing else
    assert got['date'] == '2026-11-16'
    assert got['pre_fetched_at'] == '2026-11-16T13:20:01.123456+00:00'
    assert got['pre_filter_params'] == {'a': [2], 'b': 1}
    assert got['pre_high'] == 752.6 and type(got['pre_high']) is float
    assert got['pre_volume'] == 1778 and type(got['pre_volume']) is int
    assert got['pre_low'] is None
    json.dumps(got)
    assert par.snapshot_record(None, fpr._UPSERT_KEYS) is None


def test_object_name():
    from gcp.fetchers import premarket_as_read as par

    assert par.object_name('SPY', SESSION, FETCHED_AT) == (
        'premarket-as-read/v1/2026-11-16/SPY/20261116T132001123456Z.json.gz')
    with pytest.raises(ValueError):
        par.object_name('SPY', SESSION, FETCHED_AT.replace(tzinfo=None))
