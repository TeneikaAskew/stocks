"""FEAT-PLAYBOOK-001: the brief's exchange date reaches the site's API.

The frozen-clock tests in tests/gcp/test_premarket_brief.py stop at the
in-memory premarket_analysis tables. These follow the same two scheduled runs
to what a signed-in user is served:

  gcp.premarket_brief.main([]) at Sunday 21:00 America/New_York
  -> the in-memory premarket_analysis table (the real row builder; only the
     database calls are answered in memory)
  -> GET /api/dashboard/brief/{ticker} (the real router, reading that table
     through a fake _query_fn that applies the router's own filter)
  gcp.premarket_brief.main([]) at Monday 08:30 America/New_York
  -> the same table -> the same route, and GET /api/movement-statement, which
     reads the session's live level_basis.

On origin/main the Sunday run is dated Monday, so the first response carries
Monday's date on Sunday evening, and Monday's run writes no canonical row, so
the movement statement is served from a row built with no premarket snapshot.

No network and no database: the run helper refuses sockets and answers every
gcp.database call from the table.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# The module, not the class: a Test* name at this module's top level would be
# collected here a second time.
import tests.gcp.test_premarket_brief as brief_tests  # noqa: E402

SUNDAY = '2026-11-15'
MONDAY = '2026-11-16'
FRIDAY = '2026-11-13'


@pytest.fixture(scope="module")
def client():
    import os
    original_cwd = os.getcwd()
    platform_dir = str(PROJECT_ROOT / "platform")
    if platform_dir not in sys.path:
        sys.path.insert(0, platform_dir)
    os.chdir(platform_dir)
    from starlette.testclient import TestClient
    from api.main import app
    with TestClient(app) as c:
        yield c
    os.chdir(original_cwd)


def _serve(monkeypatch, tables):
    """Answer the routes' reads of premarket_analysis from the table the
    brief wrote, with each query's own filter. Every other read is empty."""
    from api.routers import dashboard as dash_module
    monkeypatch.setattr(dash_module, '_CLOUD_SQL', True)

    def fake_query(sql, params=None):
        params = params or {}
        if 'FROM premarket_analysis' not in sql:
            return pd.DataFrame()
        assert "run_kind = 'live'" in sql
        rows = [r for r in tables['premarket_analysis'].values()
                if r['ticker'] == params['ticker'] and r['run_kind'] == 'live']
        if 'analysis_date = :d' in sql:              # the session's level_basis
            rows = [r for r in rows if str(r['analysis_date']) == str(params['d'])
                    and r.get('level_basis') is not None]
        elif 'date' in params:                       # the brief, as of a date
            rows = [r for r in rows if str(r['analysis_date']) <= str(params['date'])]
        rows.sort(key=lambda r: str(r['analysis_date']), reverse=True)
        return pd.DataFrame(rows[:1])

    monkeypatch.setattr(dash_module, '_query_fn', fake_query)


def _sunday_then(monkeypatch, tables, *, monday):
    """The Sunday 21:00 run, and with `monday` the Monday 08:30 run after it."""
    runs = brief_tests.TestLiveDateIsTheExchangeDate()
    runs._run(monkeypatch, tables, runs._eastern(f'{SUNDAY} 21:00'),
              'premarket-brief-sunday', FRIDAY)
    if monday:
        runs._run(monkeypatch, tables, runs._eastern(f'{MONDAY} 08:30'),
                  'premarket-brief-daily', FRIDAY, premarket_day=MONDAY)
    return runs


@pytest.mark.parametrize('ticker', ['SPY', 'IWM'])
def test_the_brief_route_is_dated_sunday_after_the_sunday_run(client, monkeypatch, ticker):
    tables = brief_tests.TestLiveDateIsTheExchangeDate._tables()
    _sunday_then(monkeypatch, tables, monday=False)
    _serve(monkeypatch, tables)

    latest = client.get(f'/api/dashboard/brief/{ticker}')
    as_of_sunday = client.get(f'/api/dashboard/brief/{ticker}', params={'date': SUNDAY})
    assert latest.status_code == as_of_sunday.status_code == 200
    for body in (latest.json(), as_of_sunday.json()):
        assert body['source'] == 'cloud_sql'
        assert body['has_premarket'] is True
        # origin/main: 2026-11-16, a Monday brief served on Sunday evening,
        # and nothing at all for the request as of Sunday.
        assert str(body['analysis_date']).startswith(SUNDAY)


@pytest.mark.parametrize('ticker', ['SPY', 'IWM'])
def test_the_brief_route_serves_mondays_own_row_after_the_monday_run(client, monkeypatch, ticker):
    tables = brief_tests.TestLiveDateIsTheExchangeDate._tables()
    runs = _sunday_then(monkeypatch, tables, monday=True)
    _serve(monkeypatch, tables)

    latest = client.get(f'/api/dashboard/brief/{ticker}')
    as_of_sunday = client.get(f'/api/dashboard/brief/{ticker}', params={'date': SUNDAY})
    assert latest.status_code == as_of_sunday.status_code == 200
    assert str(latest.json().get('analysis_date')).startswith(MONDAY)
    # The Sunday row is kept beside it and is still what Sunday's date returns.
    # origin/main has no row dated Sunday, so that request has no premarket.
    assert str(as_of_sunday.json().get('analysis_date')).startswith(SUNDAY)

    # The row behind Monday's answer is the one the 08:30 run wrote, on the
    # 08:20 premarket snapshot. origin/main serves the row the Sunday run
    # wrote under Monday's date: no premarket, written the evening before.
    served = tables['premarket_analysis'][(MONDAY, ticker)]
    assert served['analysis_ts'] == runs._eastern(f'{MONDAY} 08:30')
    assert served['level_basis']['premarket_status'] == 'ok'


@pytest.mark.parametrize('ticker', ['SPY', 'IWM'])
def test_the_movement_ladder_is_built_on_mondays_premarket(client, monkeypatch, ticker):
    """GET /api/movement-statement reads the session's live level_basis. After
    both runs it is the Monday run's, so the premarket high and low are rungs
    of the ladder and the triggers. On origin/main the session's row is the
    one the Sunday run wrote, which has no premarket levels at all."""
    import gcp.database as database
    from api.routers import dashboard as dash_module
    from tests.lib.level_params_fixtures import legacy_db

    tables = brief_tests.TestLiveDateIsTheExchangeDate._tables()
    _sunday_then(monkeypatch, tables, monday=True)
    _serve(monkeypatch, tables)
    # The route rebuilds a basis that did not record its parameters through
    # the strict reader; the run helper leaves that reader refusing.
    monkeypatch.setattr(database, 'query_to_dataframe_strict',
                        legacy_db(['SPY', 'IWM']).query)

    # The session is named, as the endpoint names it, so the read does not
    # depend on the day the suite runs.
    level_map = dash_module._build_movement_level_map(ticker, analysis_date=date(2026, 11, 16))
    assert level_map is not None, 'the session has no live level basis to serve'
    names = {level.name for level in level_map.levels}
    assert {'PMK_H', 'PMK_L'} <= names
    assert level_map.calls_trigger['trigger_name'] == 'PMK_H'
    assert level_map.puts_trigger['trigger_name'] == 'PMK_L'
    stored = tables['premarket_analysis'][(MONDAY, ticker)]['level_basis']
    assert stored['premarket_status'] == 'ok'
