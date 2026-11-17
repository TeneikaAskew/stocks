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


# R7's stored bars (Design 5), as UTC instants: 08:59Z only in the store,
# 09:00Z equal to the 04:00 read, 09:02Z the measured SPY 04:02 pair (low
# 749.74, volume 7,151), 09:03Z a revised close, 09:04Z after the newest read.
STORED_ROWS = [
    ('2026-11-16 08:59:00+00:00', 752.6, 752.7, 752.5, 752.6, 400),
    ('2026-11-16 09:00:00+00:00', 752.5, 752.6, 752.4, 752.5, 500),
    ('2026-11-16 09:02:00+00:00', 752.3, 752.4, 749.74, 752.3, 7151),
    ('2026-11-16 09:03:00+00:00', 752.2, 752.3, 752.1, 752.25, 10),
    ('2026-11-16 09:04:00+00:00', 752.1, 752.2, 752.0, 752.1, 20),
]
R7_COUNTS = {'as_read_bars': 4, 'stored_bars': 4, 'matched': 3, 'only_as_read': 1,
             'only_stored': 1, 'differing': 2, 'differ_open': 0, 'differ_high': 0,
             'differ_low': 1, 'differ_close': 1, 'differ_volume': 1}
# The premarket block: 08:59Z is 03:59 Eastern, outside 04:00 to 09:29.
R7_PREMARKET = {**R7_COUNTS, 'stored_bars': 3, 'only_stored': 0}


def stored_frame(rows=STORED_ROWS) -> pd.DataFrame:
    """Stored bars as the comparison takes them: ts as aware UTC instants."""
    return pd.DataFrame({
        'ts': pd.to_datetime([r[0] for r in rows]),
        'open': [r[1] for r in rows], 'high': [r[2] for r in rows],
        'low': [r[3] for r in rows], 'close': [r[4] for r in rows],
        'volume': [r[5] for r in rows],
    })


def as_read_frame() -> pd.DataFrame:
    from gcp.fetchers import premarket_as_read as par
    return par.read_record(record_of(vendor_frame(R1_ROWS)))[1]


def test_compare_counts_differing_bars():
    """R7: the as-read bars of R1 against five stored bars: matched,
    one-sided and differing bars counted, with the premarket block."""
    from gcp.fetchers import premarket_as_read as par

    got = par.compare_bars(as_read_frame(), stored_frame(), SESSION)
    assert {k: v for k, v in got.items() if k != 'premarket'} == R7_COUNTS
    assert got['premarket'] == R7_PREMARKET
    assert list(got) == [*R7_COUNTS, 'premarket']

    # a price 0.00004 apart is the same price; 0.00005 apart is not
    for delta, differ_open in ((0.00004, 0), (0.00005, 1)):
        rows = [STORED_ROWS[0], (STORED_ROWS[1][0], 752.5 + delta, *STORED_ROWS[1][2:]),
                *STORED_ROWS[2:]]
        got = par.compare_bars(as_read_frame(), stored_frame(rows), SESSION)
        assert got['differ_open'] == differ_open
        assert got['differing'] == 2 + differ_open


def test_compare_counts_a_missing_stored_value_as_different():
    """A stored NULL beside a value read is a difference, never a match."""
    from gcp.fetchers import premarket_as_read as par

    rows = [STORED_ROWS[0], (STORED_ROWS[1][0], float('nan'), *STORED_ROWS[1][2:]),
            *STORED_ROWS[2:]]
    stored = stored_frame(rows)
    stored['volume'] = pd.array([400, None, 7151, 10, 20], dtype='Int64')
    got = par.compare_bars(as_read_frame(), stored, SESSION)
    assert got['differ_open'] == 1 and got['differ_volume'] == 2 and got['differing'] == 3


def test_compare_refuses_a_session_before_true_utc():
    from gcp.fetchers import premarket_as_read as par

    with pytest.raises(ValueError, match='TRUE_UTC_FROM'):
        par.compare_bars(as_read_frame(), stored_frame(), date(2026, 9, 25))


def _write_cli_inputs(tmp_path, *, offsets=True, tamper=False):
    """R1's record and R7's stored bars as files, the CSV as
    ./scripts/db_query_cr.sh writes a TIMESTAMPTZ (with its offset)."""
    data = record_of(vendor_frame(R1_ROWS))
    if tamper:
        doc = decode(data)
        doc['bars_csv'] = doc['bars_csv'].replace('752.02', '752.03')
        data = gzip.compress(json.dumps(doc, sort_keys=True, separators=(',', ':')).encode(),
                             mtime=0)
    record = tmp_path / 'record.json.gz'
    record.write_bytes(data)
    lines = ['ts,open,high,low,close,volume']
    for ts, *values in STORED_ROWS:
        lines.append(','.join([ts if offsets else ts[:19], *map(str, values)]))
    stored = tmp_path / 'stored.csv'
    stored.write_text('\n'.join(lines) + '\n')
    return str(record), str(stored)


def _cli(*args):
    import subprocess
    import sys
    from pathlib import Path

    return subprocess.run([sys.executable, '-m', 'gcp.fetchers.premarket_as_read', *args],
                          cwd=Path(__file__).resolve().parents[2], capture_output=True,
                          text=True, timeout=300)


def test_compare_cli_is_read_only(tmp_path):
    """R7: the command prints the counts as one JSON line, exits 2 on a
    record whose sha256 does not match, and the module imports neither the
    database layer nor requests."""
    import subprocess
    import sys
    from pathlib import Path

    record, stored = _write_cli_inputs(tmp_path)
    done = _cli('compare', '--as-read', record, '--stored-csv', stored)
    assert done.returncode == 0, done.stderr
    (line,) = done.stdout.splitlines()
    assert json.loads(line) == {**R7_COUNTS, 'premarket': R7_PREMARKET}

    record, stored = _write_cli_inputs(tmp_path, tamper=True)
    done = _cli('compare', '--as-read', record, '--stored-csv', stored)
    assert done.returncode == 2 and done.stdout == ''
    assert R1_SHA256 in done.stderr

    probe = subprocess.run(
        [sys.executable, '-c', "import sys, gcp.fetchers.premarket_as_read as m; m.compare_bars; "
                               "print('requests' in sys.modules, 'gcp.database' in sys.modules)"],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=300)
    assert probe.stdout.strip() == 'False False', probe.stderr


def test_compare_cli_refuses_a_naive_stored_ts(tmp_path):
    """A stored ts without an offset names no instant: exit 2, nothing on
    stdout, the reason on stderr."""
    record, stored = _write_cli_inputs(tmp_path, offsets=False)
    done = _cli('compare', '--as-read', record, '--stored-csv', stored)
    assert done.returncode == 2 and done.stdout == ''
    assert 'ts' in done.stderr and len(done.stderr.strip().splitlines()) == 1


def test_compare_cli_reads_the_bucket_copy(tmp_path, monkeypatch, capsys):
    """--bars-root reads the record's ticker and month through
    export_intraday_bars.read_bars (stood in here; its own tests cover the
    folder) and compares the same way."""
    from gcp.fetchers import export_intraday_bars as xb
    from gcp.fetchers import premarket_as_read as par

    asked = []
    stored = stored_frame()
    stored['volume'] = stored['volume'].astype('Int64')
    stored['data_source'] = 'alphavantage'

    def read_bars(root, ticker, first, last):
        asked.append((root, ticker, first, last))
        return stored, [{'month': first}]

    monkeypatch.setattr(xb, 'read_bars', read_bars)
    record, _ = _write_cli_inputs(tmp_path)
    assert par.main(['compare', '--as-read', record, '--bars-root', str(tmp_path)]) == 0
    assert asked == [(str(tmp_path), 'SPY', '2026-11', '2026-11')]
    assert json.loads(capsys.readouterr().out) == {**R7_COUNTS, 'premarket': R7_PREMARKET}
