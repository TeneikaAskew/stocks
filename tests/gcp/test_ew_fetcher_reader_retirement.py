"""Offline P-F actual-reader qualification; shared builders remain unchanged."""
import importlib
import re
from datetime import date, timedelta

import pytest

from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL
from tests.fixtures.earnings_calendar_sources import (
    alias_control_rows, ew_only, ew_raw_alias, hydrated, make_db,
    run_earnings_sql, uw, av,
)

DAY = date(2026, 11, 11)
SITES = (
    'timing', 'reaction_window', 'market_universe', 'market_eligible',
    'history_universe', 'history_window', 'news', 'insider', 'sec',
    'refresh_today', 'refresh_amc',
)
MODULES = {
    'timing': 'compute_earnings_reactions', 'reaction_window': 'compute_earnings_reactions',
    'market_universe': 'fetch_market_data', 'market_eligible': 'fetch_market_data',
    'history_universe': 'fetch_earnings_history', 'history_window': 'fetch_earnings_history',
    'news': 'fetch_news_sentiment', 'insider': 'fetch_insider_transactions',
    'sec': 'fetch_sec_filings', 'refresh_today': 'fetch_premarket_refresh',
    'refresh_amc': 'fetch_premarket_refresh',
}


@pytest.fixture(autouse=True)
def forbid_external_io(monkeypatch):
    import socket
    import subprocess
    import requests

    def forbidden(*args, **kwargs):
        pytest.fail('actual-reader qualification attempted external I/O')

    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)


def execute(monkeypatch, site, rows, *, remove_predicate=False, limit=50):
    """Only query I/O is replaced; run the real reader and its aggregate SQL."""
    import gcp.database as db
    import gcp.fetchers._watchlist as watchlist
    module = importlib.import_module('gcp.fetchers.' + MODULES[site])
    conn = make_db(rows)
    conn.execute('ALTER TABLE earnings_calendar ADD COLUMN is_s_p_500')
    conn.execute('CREATE TABLE watchlists (ticker, in_brief, in_insight)')
    conn.execute('CREATE TABLE earnings_history (ticker)')
    conn.executemany('INSERT INTO earnings_history VALUES (?)', [(r['ticker'],) for r in rows])
    seen = []

    def query(sql, params=None):
        seen.append(sql)
        if remove_predicate:
            sql = sql.replace(EARNINGS_NOT_RETIRED_SQL, '1=1')
        # Syntax adapters only: the immutable shared fixture rejects intervals.
        sql = sql.replace("(NOW() AT TIME ZONE 'America/New_York')::date", 'CURRENT_DATE')
        sql = re.sub(r"CURRENT_DATE\s*([+-])\s*\(:(\w+) \|\| ' days'\)::interval",
                     lambda m: f"date(:__today, '{m[1]}' || :{m[2]} || ' days')", sql)
        return run_earnings_sql(conn, sql, params, today=DAY)

    monkeypatch.setattr(db, 'query_to_dataframe', query)
    monkeypatch.setattr(db, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(module, 'query_to_dataframe', query, raising=False)
    monkeypatch.setattr(module, 'is_cloud_sql_configured', lambda: True, raising=False)
    monkeypatch.setattr(watchlist, 'load_watchlist', lambda: [])
    monkeypatch.delenv('BACKFILL_ALL_HISTORY', raising=False)
    try:
        if site == 'timing':
            result = module.fetch_calendar_timing_map(sorted({r['ticker'] for r in rows}))
        elif site in ('reaction_window', 'history_window'):
            result = module._tickers_reporting_in_window(7)
        elif site == 'market_universe':
            result = module._earnings_tickers_in_window(7, 7, top_n=limit, require_options=True)
        elif site == 'market_eligible':
            result = module._backfill_targets()
        elif site == 'history_universe':
            result = module._earnings_calendar_tickers(7, require_options=False)
        elif site.startswith('refresh_'):
            result = module.resolve_universe(DAY, max_tickers=limit)
        else:
            result = module._earnings_calendar_tickers(7)
        return result, seen
    finally:
        conn.close()


@pytest.mark.parametrize('site', SITES)
def test_actual_reader_retains_controls_and_removes_both_aliases(monkeypatch, site):
    day = DAY - timedelta(days=1) if site == 'refresh_amc' else DAY
    rows = alias_control_rows('C', day)
    for row in rows:
        row.update(earnings_time='postmarket', has_options=True, options_volume=20000,
                   stock_volume=1_000_000)
    # Eligible CTE consistency: retired writer never emitted qualifying stock volume.
    if site == 'market_eligible':
        for row in rows:
            if row['data_source'] in ('earnings_whispers', 'EarningsWhispers'):
                row['stock_volume'] = None
    retained = [r for r in rows if r['data_source'] not in ('earnings_whispers', 'EarningsWhispers')]
    expected, _ = execute(monkeypatch, site, retained)
    actual, queries = execute(monkeypatch, site, rows)
    original, _ = execute(monkeypatch, site, rows, remove_predicate=True)
    original_retained, _ = execute(monkeypatch, site, retained, remove_predicate=True)
    assert repr(expected).encode() == repr(original_retained).encode()
    assert actual == expected
    assert actual, 'a swallowed SQL error must not satisfy exclusion'
    target_queries = [q for q in queries if 'FROM earnings_calendar' in q]
    assert target_queries and all(EARNINGS_NOT_RETIRED_SQL in q for q in target_queries)
    if site == 'market_eligible':
        assert original == expected
    else:
        assert original != expected
    tickers = {k[0] for k in actual} if site in ('timing', 'market_eligible') else set(actual)
    assert tickers == {'C0', 'C1', 'C4', 'C5', 'C6', 'C7'}


def test_event_specific_majority_and_tie_are_preserved(monkeypatch):
    prior = DAY - timedelta(days=90)
    rows = [av('MIX', DAY), ew_only('MIX', DAY), ew_raw_alias('MIX', DAY),
            av('MIX', prior, earnings_time='premarket'),
            av('TIE', DAY), uw('TIE', DAY, earnings_time='premarket')]
    actual, _ = execute(monkeypatch, 'timing', rows)
    original, _ = execute(monkeypatch, 'timing', rows, remove_predicate=True)
    assert actual == {('MIX', DAY): 'postmarket', ('MIX', prior): 'premarket', ('TIE', DAY): None}
    assert original[('MIX', DAY)] == 'premarket'


def test_refresh_hydrated_ew_changes_limit_winner_without_predicate(monkeypatch):
    rows = [uw('MIX', DAY, market_cap=1e9), hydrated(ew_only('MIX', DAY)),
            uw('PEER', DAY, options_volume=25000, market_cap=1e9)]
    actual, _ = execute(monkeypatch, 'refresh_today', rows, limit=1)
    original, _ = execute(monkeypatch, 'refresh_today', rows, remove_predicate=True, limit=1)
    assert actual == ['PEER']
    assert original == ['MIX']


def test_amc_uses_hydrated_writer_rows(monkeypatch):
    prior = DAY - timedelta(days=1)
    rows = [hydrated(ew_only('EW', prior, earnings_time='postmarket')),
            hydrated(ew_raw_alias('RAW', prior, earnings_time='postmarket')),
            uw('UW', prior)]
    actual, _ = execute(monkeypatch, 'refresh_amc', rows)
    original, _ = execute(monkeypatch, 'refresh_amc', rows, remove_predicate=True)
    assert actual == ['UW']
    assert original == ['EW', 'RAW', 'UW']
