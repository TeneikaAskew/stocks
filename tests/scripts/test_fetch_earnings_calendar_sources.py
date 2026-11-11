"""EarningsWhispers retirement in scripts/fetch_earnings_calendar.py.

The calendar job no longer has an EarningsWhispers route: ``--source`` is
exactly all/uw/av/yh, ``--source all`` calls only the AlphaVantage, Unusual
Whales and Yahoo fetchers, and the DB hydration of options volume ignores
stored EarningsWhispers rows (RETIREMENT-DESIGN section 4.1 site 6).
Every provider, network and database boundary is faked.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from gcp import database
from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL
from scripts import fetch_earnings_calendar as fec
from tests.fixtures.earnings_calendar_sources import (
    av, ew_only, ew_raw_alias, hydrated, make_db, null_source,
    run_earnings_sql, stale, unknown_source, uw,
)

SCRIPT = Path(fec.__file__)


@pytest.fixture(autouse=True)
def no_external_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Provider/database calls forbidden")

    import requests
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(database, "get_engine", forbidden)


def _source_choices(monkeypatch) -> list:
    class _Parsed(Exception):
        pass

    seen = {}

    def capture(self, *a, **k):
        seen['parser'] = self
        raise _Parsed

    monkeypatch.setattr(argparse.ArgumentParser, 'parse_args', capture)
    with pytest.raises(_Parsed):
        fec.main()
    action = next(a for a in seen['parser']._actions if '--source' in a.option_strings)
    return list(action.choices)


def test_source_choices_are_exactly_all_uw_av_yh(monkeypatch):
    assert _source_choices(monkeypatch) == ['all', 'uw', 'av', 'yh']


def test_no_earnings_whispers_route():
    text = SCRIPT.read_text(encoding='utf-8')
    for needle in ('earningswhispers', 'EW_USER', 'EW_PASS', 'EarningsWhispers'):
        assert needle not in text, needle
    for name in ('fetch_earnings_whispers', 'ew_login', 'ew_fetch_strategy',
                 '_ew_extract_csrf', 'EW_BASE', 'EW_STRATEGY_ENDPOINTS'):
        assert not hasattr(fec, name), name


def test_normalize_earnings_time_is_unchanged():
    """Byte-identical to main e9a06998 (sha256 of its source)."""
    import hashlib
    import inspect
    src = inspect.getsource(fec.normalize_earnings_time)
    assert hashlib.sha256(src.encode()).hexdigest() == (
        '4f07f355a12198c8d0f4cb5a8ddf9d1361768c6c329e89702599393b1ec8d4d8')


def test_source_all_calls_only_av_uw_and_yahoo(monkeypatch):
    day = (datetime.now().date() + timedelta(days=1)).strftime('%Y-%m-%d')
    calls: list[str] = []

    def frame(ticker, source):
        return pd.DataFrame([{
            'date': day, 'ticker': ticker, 'company_name': 'Acme',
            'time': 'postmarket', 'eps_estimate': 1.0, 'source': source,
            'strategy': '', 'fetched_at': datetime.now().isoformat(),
        }])

    def fake_av(horizon='3month'):
        calls.append('av')
        return frame('AAA', 'AlphaVantage')

    def fake_uw(self, days_ahead=90):
        calls.append('uw')
        return frame('AAA', 'UnusualWhales')

    def fake_yh(start, end):
        calls.append('yh')
        return frame('BBB', 'Yahoo')

    def fake_ew(*a, **k):
        calls.append('ew')
        return frame('CCC', 'Earnings' + 'Whispers')

    monkeypatch.setattr(fec, 'fetch_alphavantage_earnings', fake_av)
    monkeypatch.setattr(fec.EarningsCalendarFetcher,
                        'fetch_unusual_whales_earnings', fake_uw)
    monkeypatch.setattr(fec, 'fetch_yahoo_earnings', fake_yh)
    # Present only on a tree that still has the EW route (negative control).
    monkeypatch.setattr(fec, 'fetch_earnings_whispers', fake_ew, raising=False)
    monkeypatch.setenv('EW_' + 'USER', 'fixture')
    monkeypatch.setenv('EW_' + 'PASS', 'fixture')

    persisted = {}

    def fake_upsert(df, table, conflict_cols=None, **kw):
        persisted['df'] = df.copy()
        return len(df)

    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'upsert_dataframe', fake_upsert)
    monkeypatch.setattr(sys, 'argv', ['fetch_earnings_calendar.py',
                                      '--source', 'all', '--no-av-options-enrich'])
    fec.main()

    assert calls == ['av', 'uw', 'yh']
    assert sorted(persisted['df']['data_source'].unique()) == [
        'alphavantage', 'unusual_whales', 'yahoo']


def test_persist_rejects_or_passes_unknown_source_unchanged(monkeypatch):
    """No source_map entry relabels the raw EarningsWhispers literal: a frame
    carrying it passes through unchanged (as any unmapped source does), so it
    stays recognisable to the readers' retired-source predicate."""
    captured = {}

    def fake_upsert(df, table, conflict_cols=None, **kw):
        captured['df'] = df.copy()
        return len(df)

    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'upsert_dataframe', fake_upsert)
    raw = 'Earnings' + 'Whispers'
    df = pd.DataFrame([
        {'date': '2026-11-03', 'ticker': t, 'source': s, 'strategy': ''}
        for t, s in (('A', 'AlphaVantage'), ('U', 'UnusualWhales'),
                     ('Y', 'Yahoo'), ('E', raw), ('Z', 'SomeNewVendor'))
    ])
    assert fec.persist_to_cloud_sql(df) == 5
    got = dict(zip(captured['df']['ticker'], captured['df']['data_source']))
    assert got == {'A': 'alphavantage', 'U': 'unusual_whales', 'Y': 'yahoo',
                   'E': raw, 'Z': 'SomeNewVendor'}


# ── Site 6: _load_existing_options_from_db ─────────────────────────────────

D = date(2026, 12, 15)


def _fake_db(monkeypatch, rows, *, strip_predicate=False):
    conn = make_db(rows)
    seen = []

    def query(sql, params=None):
        seen.append(sql)
        if strip_predicate:
            assert sql.count('AND ' + EARNINGS_NOT_RETIRED_SQL) == 1
            sql = sql.replace('AND ' + EARNINGS_NOT_RETIRED_SQL, '')
        return run_earnings_sql(conn, sql, params)

    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'query_to_dataframe', query)
    return seen


def _site6_rows():
    return [
        # T on D: current AV/UW rows plus a stale hydrated EW row.
        uw('T', D, options_volume=20000, open_interest=50000),
        av('T', D),
        stale(hydrated(ew_only('T', D), volume=30000, oi=90000)),
        # E: only an EW row for the pair (both spellings).
        hydrated(ew_only('E', D)),
        hydrated(ew_raw_alias('R', D)),
        # Controls kept: NULL and unknown sources.
        null_source('N', D, options_volume=7000, open_interest=8000),
        unknown_source('K', D, options_volume=6000, open_interest=9000),
    ]


def _keys():
    return {(t, D) for t in ('T', 'E', 'R', 'N', 'K')}


def test_db_hydration_ignores_stale_ew_rows(monkeypatch):
    seen = _fake_db(monkeypatch, _site6_rows())
    out = fec._load_existing_options_from_db(_keys())
    assert len(seen) == 1 and EARNINGS_NOT_RETIRED_SQL in seen[0]
    assert out == {
        ('T', D): (20000, 50000),
        ('N', D): (7000, 8000),
        ('K', D): (6000, 9000),
    }


def test_main_shaped_hydration_query_returns_the_stale_ew_value(monkeypatch):
    """Negative control: the same SQL without the predicate (main's text)."""
    _fake_db(monkeypatch, _site6_rows(), strip_predicate=True)
    out = fec._load_existing_options_from_db(_keys())
    assert out[('T', D)] == (30000, 90000)
    assert ('E', D) in out and ('R', D) in out


def test_hydration_step_writes_the_uw_value_onto_current_rows(monkeypatch):
    """enrich_with_av_options step 1 hydrates every row of the pair from the
    DB value; with the predicate that value is UW's, not the stale EW one.
    The target window excludes D, so no AV call is made."""
    _fake_db(monkeypatch, _site6_rows())
    frame = pd.DataFrame([
        {'date': D.isoformat(), 'ticker': 'T', 'source': 'AlphaVantage',
         'options_volume': None, 'open_interest': None},
        {'date': D.isoformat(), 'ticker': 'T', 'source': 'UnusualWhales',
         'options_volume': 1, 'open_interest': 2},
    ])
    out = fec.enrich_with_av_options(
        frame, '2026-12-14', 'key', target_dates_override=[date(2000, 1, 3)])
    assert list(out['options_volume']) == [20000, 20000]
    assert list(out['open_interest']) == [50000, 50000]
