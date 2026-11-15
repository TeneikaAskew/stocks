"""FEAT-PLAYBOOK-001: the late slot's write reaches the movement statement.

Spec: docs/superpowers/specs/2026-11-14-feat-playbook-001-brief-late-slot.md
(Site traceability; Consumers, the movement statement row).

No route and no response shape changes with the late slot. What changes is
when the session's canonical premarket_analysis row changes, and a signed-in
user sees that: from the next request after the late write,
GET /api/movement-statement returns a different ladder. These tests follow one
in-memory premarket_analysis table through the whole chain:

  gcp.premarket_brief.main([]) at 08:30:50 America/New_York (the early run)
  -> the table (the real row builder; only the database calls are in memory)
  -> GET /api/movement-statement for SPY through TestClient (the real router
     and lib.strat_levels.read_live_level_basis, reading that table through
     the route's own query function)
  gcp.premarket_brief.main([]) with BRIEF_RUN_SLOT=late at 09:21:30, on a
  premarket snapshot stamped 09:20:40 whose high is 30 cents above the early one
  -> the same table -> the same request.

On origin/main BRIEF_RUN_SLOT is not read: the 09:21:30 run rewrites no
canonical row and the route still answers with the early trigger.

No network and no database: the harness refuses sockets and answers every
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

# The module, not its classes: a Test* name at this module's top level would
# be collected here a second time.
import tests.gcp.test_premarket_brief_late_slot as late_tests  # noqa: E402

SESSION = late_tests.SESSION
KEY = (SESSION, 'SPY')


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


_RESEARCH_MODULES = ("lightgbm", "sklearn", "sklearn.calibration",
                     "sklearn.metrics", "joblib", "scipy")


def _stub_research_modules(monkeypatch):
    """Scoped stand-ins for the research stack when it is not installed.

    `monkeypatch.setitem`, not a module-level stub, so nothing leaks into
    another module's `pytest.importorskip("lightgbm")`; reverted at teardown.
    """
    from unittest.mock import MagicMock
    for name in _RESEARCH_MODULES:
        try:
            __import__(name)
        except Exception:
            parts = name.split(".")
            for i in range(1, len(parts) + 1):
                key = ".".join(parts[:i])
                if key not in sys.modules:
                    monkeypatch.setitem(sys.modules, key, MagicMock())


def _serve(monkeypatch, harness):
    """Answer the route's reads of premarket_analysis from the table the
    brief wrote, with each query's own filter. Every other read is empty.
    The session date is the frozen one: the route takes it from
    lib.movement_statement.market_today, which reads the host clock in
    America/New_York and is not frozen by lib.eastern_time.eastern_now."""
    import lib.movement_statement as ms
    from api.routers import dashboard as dash_module

    monkeypatch.setenv('MOVEMENT_STATEMENT_ENABLED', 'true')
    monkeypatch.setattr(dash_module, '_CLOUD_SQL', True)
    monkeypatch.setattr(ms, 'market_today', lambda: date.fromisoformat(SESSION))

    def fake_query(sql, params=None):
        params = params or {}
        if 'FROM premarket_analysis' not in sql:
            return pd.DataFrame()
        assert "run_kind = 'live'" in sql
        rows = [r for r in harness.tables['premarket_analysis'].values()
                if r['ticker'] == params['ticker'] and r['run_kind'] == 'live']
        if 'analysis_date = :d' in sql:              # the session's level_basis
            rows = [r for r in rows if str(r['analysis_date']) == str(params['d'])
                    and r.get('level_basis') is not None]
        elif 'date' in params:                       # the brief, as of a date
            rows = [r for r in rows if str(r['analysis_date']) <= str(params['date'])]
        rows.sort(key=lambda r: str(r['analysis_date']), reverse=True)
        return pd.DataFrame(rows[:1])

    monkeypatch.setattr(dash_module, '_query_fn', fake_query)

    # The assembler's other pieces reach the network: the continuation model
    # is muted, the reach-rate query answers no rows and gamma has no chain.
    # The levels block is the real one.
    real_assemble = ms.assemble_movement_statement

    def assemble(ticker, timeframe='15m', **kw):
        kw.setdefault('query_fn', lambda _sql, _params=None: pd.DataFrame())
        kw.setdefault('gamma_fn', lambda _ticker, as_of=None: {
            'available': False, 'reason': 'no chain in test'})
        kw.setdefault('engine', object())
        return real_assemble(ticker, timeframe, **kw)

    monkeypatch.setattr(ms, 'assemble_movement_statement', assemble)
    # The serving module imports the training module, which imports
    # lightgbm (requirements-research.txt only). Stub it for this test only,
    # and only when the real one cannot be imported, the way
    # tests/api/test_route_coverage.py::_reach_predict_backend does.
    _stub_research_modules(monkeypatch)
    import gcp.research.strat_engine.strat_pred_serve as serve
    monkeypatch.setattr(serve, 'predict_one',
                        lambda *a, **k: {'available': False, 'note': 'muted'})


def _get(client):
    return client.get('/api/movement-statement', params={'ticker': 'SPY', 'timeframe': '15m'})


def _cents(value) -> int:
    from lib.strat_levels import price_cents
    return price_cents(value)


def _rungs(side) -> list:
    return [(r['name'], _cents(r['price'])) for r in side]


def _early_run_and_first_request(client, monkeypatch):
    """The early run at 08:30:50 on the 08:20 snapshot, and the request
    after it. Returns (harness, the early row, the response)."""
    h = late_tests.Harness(monkeypatch)
    h.snapshot(stamp=late_tests.EARLY_STAMP, up=0.6)
    assert h.run('2026-11-13 08:30:50') is None
    _serve(monkeypatch, h)
    early = dict(h.tables['premarket_analysis'][KEY])
    first = _get(client)
    assert first.status_code == 200, first.text
    levels = first.json()['levels']
    assert levels['status'] == 'OK'
    # The early row's trigger is rung one, and its side lists are the ladder.
    assert (levels['calls'][0]['name'], _cents(levels['calls'][0]['price'])) == (
        early['calls_trigger_name'], _cents(early['calls_trigger_price']))
    assert _rungs(levels['calls']) == _rungs(early['level_basis']['long']['ladder'])
    assert _rungs(levels['puts']) == _rungs(early['level_basis']['short']['ladder'])
    return h, early, first


def test_the_ladder_follows_the_late_write(client, monkeypatch):
    h, early, first = _early_run_and_first_request(client, monkeypatch)

    h.snapshot(stamp=late_tests.LATE_STAMP, up=0.9)
    assert h.run('2026-11-13 09:21:30', late=True) == 0
    late = h.tables['premarket_analysis'][KEY]
    assert late['level_basis']['premarket']['fetched_at'] == late_tests.LATE_STAMP_ISO

    second = _get(client)
    assert second.status_code == 200, second.text
    levels = second.json()['levels']
    assert levels['status'] == 'OK'
    assert levels['calls'][0]['name'] == late['calls_trigger_name'] == 'PMK_H'
    assert _cents(levels['calls'][0]['price']) == _cents(late['calls_trigger_price']) \
        == _cents(early['calls_trigger_price']) + 30
    assert _rungs(levels['calls']) == _rungs(late['level_basis']['long']['ladder'])
    assert _rungs(levels['puts']) == _rungs(late['level_basis']['short']['ladder'])
    # The early trigger is no longer served.
    assert _cents(early['calls_trigger_price']) not in {c for _, c in _rungs(levels['calls'])}
    assert second.json() != first.json()


def test_a_late_run_that_does_not_apply_leaves_the_ladder(client, monkeypatch):
    h, early, first = _early_run_and_first_request(client, monkeypatch)

    h.snapshot(stamp=late_tests.LATE_STAMP, up=0.9)
    assert h.run('2026-11-13 09:35:00', late=True) == 1          # past the write cutoff
    assert h.tables['premarket_analysis'][KEY] == early
    assert _get(client).json() == first.json()
