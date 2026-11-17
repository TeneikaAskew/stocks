"""The plan excursions history job (FEAT-STRAT-001 target hit rates spec,
docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md,
Design 4 "History, once"): resume, reprocess, delete only its own rows,
never replace a resolver row, one bar read per ticker-month, writes only to
plan_excursions, and the replay never reaches the model client.

The scoring runs on SQLite (plan_excursions as gcp/schema.sql creates it,
NOW() supplied); the month bar read, whose SQL is Postgres-only, is
replaced by the same rows in memory and its count is checked here, its SQL
in tests/integration/test_plan_excursions_pg.py."""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from gcp import backfill_plan_excursions as job
from lib.strat_levels import LEVEL_RULE_VERSION

REPO = Path(__file__).resolve().parents[2]
SESSIONS = [date(2026, 10, 29), date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3)]


# pandas Timestamps (the fill and stop times) bind as ISO text in SQLite, as
# a datetime does; Postgres takes them as they are.
sqlite3.register_adapter(pd.Timestamp, lambda t: t.isoformat())


def _engine():
    ddl = re.search(r"CREATE TABLE IF NOT EXISTS plan_excursions \(.*?\n\);",
                    (REPO / 'gcp/schema.sql').read_text(), re.S).group(0)
    engine = sa.create_engine('sqlite://', poolclass=sa.pool.StaticPool,
                              connect_args={'check_same_thread': False})

    @sa.event.listens_for(engine, 'connect')
    def _now(dbapi_conn, _rec):
        dbapi_conn.create_function('NOW', 0, lambda: '2026-11-16T22:00:00Z')

    statements = []

    @sa.event.listens_for(engine, 'before_cursor_execute')
    def _record(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    with engine.begin() as conn:
        conn.execute(sa.text(ddl.replace('DEFAULT NOW()', 'DEFAULT CURRENT_TIMESTAMP')))
    statements.clear()
    return engine, statements


def _basis(trigger=100.0, stop=99.0):
    """A current-rule basis whose calls side triggers at `trigger` with
    `stop`, and whose puts side has no trigger."""
    return {'rule_version': LEVEL_RULE_VERSION, '_calls': (trigger, stop)}


def _bars(session: date, path):
    """One-minute RTH bars from 09:30 ET with closes on `path`; each bar's
    high and low are its close +- 0.01."""
    t0 = pd.Timestamp(f'{session} 09:30', tz='America/New_York').tz_convert('UTC')
    rows = [dict(time=t0 + pd.Timedelta(minutes=i), open=c, high=c + 0.01, low=c - 0.01,
                 close=c) for i, c in enumerate(path)]
    return pd.DataFrame(rows)


@pytest.fixture
def patched(monkeypatch):
    """plan_inputs reads the test basis's calls side; the month bar read
    serves `bars` (a dict session -> path) and records each call."""
    from gcp.premarket_playbook_resolver import PLAN_OK, PlanInputs

    def plan_inputs(side, row, basis, policy_fn):
        if side == 'calls' and basis.get('_calls'):
            trig, stop = basis['_calls']
            return PlanInputs(trigger_price=trig, stop_price=stop, targets=(trig + 2,),
                              legs=3, cutoff_minutes=16 * 60, target_status=PLAN_OK)
        return PlanInputs(trigger_price=None, stop_price=None, target_status='not_entered')

    state = {'bars': {}, 'reads': []}

    def read_month_bars(engine, ticker, sessions):
        state['reads'].append((ticker, sessions[0].year, sessions[0].month))
        frames = [_bars(s, state['bars'][s]) for s in sessions if s in state['bars']]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
            columns=['time', 'open', 'high', 'low', 'close'])

    monkeypatch.setattr(job, 'plan_inputs', plan_inputs)
    monkeypatch.setattr(job, 'read_month_bars', read_month_bars)
    return state


UP = [99.5, 100.2, 101.0, 102.5, 101.5, 101.0, 100.8]     # fills, runs 2.5 past
FLAT = [99.5, 99.6, 99.7, 99.6, 99.5, 99.6, 99.7]         # never fills


def _rows(engine):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(sa.text(
            "SELECT ticker, session_date, side, excursion_r, source FROM plan_excursions "
            "ORDER BY ticker, session_date"))]


def _run(engine, *, resume, start=SESSIONS[0], end=SESSIONS[-1], tickers=('IWM',)):
    lines = []
    stats = job.run(engine, tickers, start, end, resume=resume,
                    basis_fn=lambda t, s: _basis(), log=lines.append)
    return stats, lines


def test_writes_one_history_row_per_traded_session(patched):
    engine, _ = _engine()
    patched['bars'] = {s: UP for s in SESSIONS}
    (stats,), lines = _run(engine, resume=False)
    rows = _rows(engine)
    assert [r[1] for r in rows] == [s.isoformat() for s in SESSIONS]
    assert all(r[2] == 'calls' and r[4] == 'history' for r in rows)
    assert rows[0][3] == pytest.approx(2.51)
    assert (stats.sessions, stats.written, stats.deleted) == (4, 4, 0)
    assert lines[0].startswith('IWM: 4 sessions read, 4 rows written, 0 rows deleted')


def test_with_no_range_it_resumes_after_the_last_written_session(patched):
    engine, _ = _engine()
    patched['bars'] = {s: UP for s in SESSIONS}
    job.run(engine, ['IWM'], SESSIONS[0], SESSIONS[1], resume=False,
            basis_fn=lambda t, s: _basis(), log=lambda _l: None)
    seen = []
    job.run(engine, ['IWM'], SESSIONS[0], SESSIONS[-1], resume=True,
            basis_fn=lambda t, s: seen.append(s) or _basis(), log=lambda _l: None)
    assert seen == SESSIONS[2:]
    assert len(_rows(engine)) == 4


def test_an_explicit_range_reprocesses_and_deletes_a_session_that_now_gives_no_trade(patched):
    engine, _ = _engine()
    patched['bars'] = {s: UP for s in SESSIONS}
    _run(engine, resume=False)
    patched['bars'][SESSIONS[1]] = FLAT                     # corrected bars: no fill
    (stats,), _ = _run(engine, resume=False)
    assert [r[1] for r in _rows(engine)] == [
        s.isoformat() for s in SESSIONS if s != SESSIONS[1]]
    assert (stats.written, stats.deleted, stats.no_trade) == (3, 1, 1)


def test_a_no_trade_session_deletes_only_a_history_row(patched):
    engine, _ = _engine()
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO plan_excursions (ticker, session_date, rule_version, side, "
            "trigger_price, stop_price, fill_price, fill_ts, excursion_r, source, "
            "resolver_version) VALUES ('IWM', :d, :v, 'puts', 1, 2, 1, '2026-10-29T13:31Z', "
            "0.7, 'resolver', 'r')"), {'d': SESSIONS[0].isoformat(), 'v': LEVEL_RULE_VERSION})
    patched['bars'] = {SESSIONS[0]: FLAT}
    (stats,), _ = _run(engine, resume=False, end=SESSIONS[0])
    assert _rows(engine) == [('IWM', SESSIONS[0].isoformat(), 'puts', 0.7, 'resolver')]
    assert stats.deleted == 0


def test_a_resolver_row_is_never_replaced(patched):
    engine, _ = _engine()
    with engine.begin() as conn:
        conn.execute(sa.text(
            "INSERT INTO plan_excursions (ticker, session_date, rule_version, side, "
            "trigger_price, stop_price, fill_price, fill_ts, excursion_r, source, "
            "resolver_version) VALUES ('IWM', :d, :v, 'puts', 1, 2, 1, '2026-10-29T13:31Z', "
            "0.7, 'resolver', 'r')"), {'d': SESSIONS[0].isoformat(), 'v': LEVEL_RULE_VERSION})
    patched['bars'] = {s: UP for s in SESSIONS}
    (stats,), _ = _run(engine, resume=False)
    rows = _rows(engine)
    assert rows[0] == ('IWM', SESSIONS[0].isoformat(), 'puts', 0.7, 'resolver')
    assert stats.written == 3


def test_a_rerun_over_the_same_span_writes_the_same_rows(patched):
    engine, _ = _engine()
    patched['bars'] = {s: UP for s in SESSIONS}
    _run(engine, resume=False)
    first = _rows(engine)
    _run(engine, resume=False)
    assert _rows(engine) == first


def test_one_bar_read_per_ticker_month(patched):
    engine, _ = _engine()
    patched['bars'] = {s: UP for s in SESSIONS}
    _run(engine, resume=False, tickers=('SPY', 'IWM'))
    assert patched['reads'] == [('SPY', 2026, 10), ('SPY', 2026, 11),
                                ('IWM', 2026, 10), ('IWM', 2026, 11)]


def test_nothing_is_written_outside_plan_excursions(patched):
    engine, statements = _engine()
    patched['bars'] = {s: UP for s in SESSIONS}
    patched['bars'][SESSIONS[2]] = FLAT
    _run(engine, resume=False)
    _run(engine, resume=True)
    writes = [s for s in statements if re.match(r'\s*(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)',
                                                s, re.I)]
    assert writes and all(re.search(r'\b(INTO|FROM)\s+plan_excursions\b', s) for s in writes)


def test_a_session_with_no_bars_or_no_basis_is_reported_and_left_alone(patched):
    engine, _ = _engine()
    patched['bars'] = {s: UP for s in SESSIONS if s != SESSIONS[0]}
    lines = []
    (stats,) = job.run(engine, ['IWM'], SESSIONS[0], SESSIONS[-1], resume=False,
                       basis_fn=lambda t, s: None if s == SESSIONS[1] else _basis(),
                       log=lines.append)
    assert stats.no_bars == [SESSIONS[0].isoformat()]
    assert stats.no_basis == [SESSIONS[1].isoformat()]
    assert [r[1] for r in _rows(engine)] == [s.isoformat() for s in SESSIONS[2:]]
    assert any(ln.startswith('IWM: no bars on 2026-10-29') for ln in lines)


def test_the_brief_replay_writes_nothing_and_never_reaches_the_model(monkeypatch):
    """brief_basis on the committed 2026-11-06 fixture: the brief's own path
    with no_persist=True; persist_level_map and the null-close cleanup
    fail the test if reached, and the model client must be called zero
    times. The basis equals the one
    the live brief path builds for the same session."""
    import lib.agents.llm_client as llm_client
    import lib.strat_levels as sl
    from gcp import premarket_brief as pb
    from tests.lib import strat_2026_11_06 as fx

    from tests.lib.level_params_fixtures import legacy_db

    db = legacy_db('IWM')
    live = fx.run_brief(monkeypatch, 'IWM', fx.loader_frame('IWM'), params_db=db)['level_basis']
    cfg, _ = fx.offline_brief_env(monkeypatch, {'IWM': fx.loader_frame('IWM')}, params_db=db)

    def forbidden(*_a, **_k):
        pytest.fail('the history replay wrote or reached the model client')

    model_calls = []

    def model_client(*a, **k):
        # The brief swallows a failing explanation, so a raise here could go
        # unseen; the call is recorded and counted instead.
        model_calls.append((a, k))
        raise RuntimeError('model client reached')

    monkeypatch.setattr(sl, 'persist_level_map', forbidden)
    monkeypatch.setattr(pb, '_delete_null_close_rows', forbidden)
    monkeypatch.setattr(llm_client, 'get_adapter', model_client)
    basis = job.brief_basis('IWM', date(2026, 11, 6), cfg)
    assert model_calls == []
    assert basis['rule_version'] == LEVEL_RULE_VERSION
    strip = lambda b: {k: v for k, v in b.items() if k not in ('built_at',)}  # noqa: E731
    assert strip(basis) == strip(live)
