"""Tests for the watched-ticker ingest job (fetch-watched-tickers).

Task 1 covers ``fetch_market_data._run_backfill`` learning a forced
``outputsize`` and a ``data_source`` label, and returning the number of
rows it passed to ``upsert_dataframe``. Later tasks extend this file.

The ``av_stub`` fixture replaces the Alpha Vantage call and the DB upsert
and records what each saw, so tests assert on I/O shape, not on the network.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from gcp.fetchers import fetch_market_data as fmd


def make_bars(n: int, ticker: str = 'X') -> pd.DataFrame:
    """n daily bars ending on a past date, safely inside the 10y cutoff."""
    dates = pd.bdate_range(end='2026-01-30', periods=n).date
    return pd.DataFrame({
        'ticker': ticker, 'date': list(dates),
        'open': 1.0, 'high': 1.0, 'low': 1.0, 'close': 1.0,
        'volume': 100, 'adjusted_close': 1.0,
    })


@pytest.fixture
def av_stub(monkeypatch):
    """Stub AV + upsert; returns a recorder.

    rec.av_calls: list of (ticker, outputsize); rec.frames: upserted frames.
    Set rec.bars_by_ticker[ticker] = n_bars to control returned data
    (default 3); 0 returns an empty frame ("no data returned").
    """
    rec = SimpleNamespace(av_calls=[], frames=[], bars_by_ticker={})

    def fake_av(ticker, api_key, outputsize):
        rec.av_calls.append((ticker, outputsize))
        n = rec.bars_by_ticker.get(ticker, 3)
        return make_bars(n, ticker) if n else pd.DataFrame()

    def fake_upsert(df, table, keys):
        rec.frames.append(df.copy())

    monkeypatch.setenv('ALPHA_VANTAGE_API_KEY', 'fake-key')
    monkeypatch.setenv('AV_BACKFILL_SLEEP_SECS', '0')
    monkeypatch.setattr(fmd, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(fmd, '_av_get_full_daily_series', fake_av)
    monkeypatch.setattr('gcp.database.upsert_dataframe', fake_upsert)
    return rec


def test_run_backfill_forced_outputsize_pulls_every_ticker_at_that_size(av_stub):
    fmd._run_backfill(['AAA', 'BBB'], outputsize='compact',
                      data_source='av_watched_backfill')
    assert av_stub.av_calls == [('AAA', 'compact'), ('BBB', 'compact')]
    assert len(av_stub.frames) == 2
    for frame in av_stub.frames:
        assert set(frame['data_source']) == {'av_watched_backfill'}


def test_run_backfill_without_keywords_keeps_full_and_default_source(av_stub):
    fmd._run_backfill(['AAA'])
    assert av_stub.av_calls == [('AAA', 'full')]
    assert set(av_stub.frames[0]['data_source']) == {'av_daily_backfill'}


def test_run_backfill_returns_the_rows_it_upserted(av_stub):
    av_stub.bars_by_ticker = {'AAA': 5, 'BBB': 7}
    assert fmd._run_backfill(['AAA', 'BBB']) == 12


def test_run_backfill_returns_zero_when_no_ticker_returns_data(av_stub):
    av_stub.bars_by_ticker = {'AAA': 0, 'BBB': 0}
    assert fmd._run_backfill(['AAA', 'BBB']) == 0
    assert av_stub.frames == []


# ---------------------------------------------------------------------------
# Task 3: config, the set read with its exact overflow, the second-guard dedup
# ---------------------------------------------------------------------------
import re
from pathlib import Path

from gcp.fetchers import fetch_watched_tickers as fwt

_MODULE_SRC = (Path(__file__).resolve().parents[2]
               / 'gcp' / 'fetchers' / 'fetch_watched_tickers.py')


def _set_frame(tickers, eligible_total):
    return pd.DataFrame({'ticker': tickers,
                         'eligible_total': [eligible_total] * len(tickers)})


class _Query:
    def __init__(self, frame=None, exc=None):
        self.frame, self.exc, self.calls = frame, exc, []

    def __call__(self, sql, params=None, timeout_s=None):
        self.calls.append((sql, params, timeout_s))
        if self.exc:
            raise self.exc
        return self.frame


def test_config_default_and_env_override():
    assert fwt.Config.from_env({}).max_tickers == 50
    assert fwt.Config.from_env({'WATCHED_TICKERS_MAX': '7'}).max_tickers == 7


def test_config_non_integer_raises():
    with pytest.raises(ValueError):
        fwt.Config.from_env({'WATCHED_TICKERS_MAX': 'x'})


def test_set_read_passes_sql_params_and_timeout():
    q = _Query(_set_frame(['AAA'], 1))
    fwt.read_watched_set(q, fmd.TICKERS, 50)
    assert q.calls == [(fwt.WATCHED_SET_SQL,
                        {'limit': 50, 'exclude': list(fmd.TICKERS)},
                        fwt._SET_QUERY_TIMEOUT_S)]


def test_set_read_overflow_is_exact():
    names = [f'T{i}' for i in range(50)]
    ws = fwt.read_watched_set(_Query(_set_frame(names, 60)), fmd.TICKERS, 50)
    assert ws.tickers == names
    assert ws.eligible_total == 60
    assert ws.overflow == 10
    ws = fwt.read_watched_set(_Query(_set_frame(names, 51)), fmd.TICKERS, 50)
    assert ws.overflow == 1


def test_set_read_normalises_tickers():
    ws = fwt.read_watched_set(_Query(_set_frame([' aapl '], 1)), [], 50)
    assert ws.tickers == ['AAPL']


def test_set_read_empty_frame_is_a_legitimate_zero():
    ws = fwt.read_watched_set(
        _Query(pd.DataFrame({'ticker': [], 'eligible_total': []})), [], 50)
    assert ws.tickers == [] and ws.eligible_total == 0 and ws.overflow == 0


def test_set_read_failure_is_set_read_error():
    with pytest.raises(fwt.SetReadError):
        fwt.read_watched_set(_Query(exc=RuntimeError('db down')), [], 50)


@pytest.mark.parametrize('frame', [
    pd.DataFrame({'ticker': [None], 'eligible_total': [1]}),
    pd.DataFrame({'ticker': [float('nan')], 'eligible_total': [1]}),
    pd.DataFrame({'ticker': [5], 'eligible_total': [1]}),
    pd.DataFrame({'ticker': ['AAA']}),
    pd.DataFrame({'ticker': ['AAA'], 'eligible_total': [None]}),
    pd.DataFrame({'ticker': ['AAA'], 'eligible_total': ['many']}),
    pd.DataFrame({'ticker': ['AAA'], 'eligible_total': [1.5]}),
])
def test_set_read_malformed_frame_is_set_read_error(frame):
    with pytest.raises(fwt.SetReadError):
        fwt.read_watched_set(_Query(frame), [], 50)


def test_dedup_second_guard_order_preserving():
    assert fwt.dedup(['aapl ', 'AAPL', 'SPY'], fmd.TICKERS) == ['AAPL']
    assert fwt.dedup(['B', 'A', 'B'], []) == ['B', 'A']


def test_set_sql_source_scan():
    sql = fwt.WATCHED_SET_SQL
    assert fwt.WATCHED_DATA_SOURCE == 'av_watched_backfill'
    assert sql.count('user_watchlists') == 1
    assert re.search(r'EXISTS \(SELECT 1 FROM user_watchlists[^)]*\)', sql)
    assert not re.search(r'owner|uid|email', sql, re.I)
    assert sql.index('<> ALL(:exclude)') < sql.index('LIMIT')
    assert not re.search(r'\bwatchlists\b', _MODULE_SRC.read_text())
