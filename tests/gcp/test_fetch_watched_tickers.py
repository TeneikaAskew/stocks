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
