"""FEAT-STRAT-001 target hit rates, done_when 'Table', on a real Postgres.

The apply-schema build runs gcp/schema.sql on every push to main that
touches it, so the plan_excursions table and the target_reach_rate policy row
must apply a second time without error and change nothing; the source CHECK
refuses any writer but the resolver and the history job
(docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md)."""
from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

REPO = Path(__file__).resolve().parents[2]

ROW = dict(ticker='ZZPX', session_date='2025-10-22', rule_version='feat-strat-001.v3',
           side='puts', trigger_price=245.66, stop_price=246.99, fill_price=245.66,
           fill_ts='2025-10-22T13:31:00+00:00', stop_ts=None, excursion_r=2.9,
           excursion_held5_r=None, source='history', resolver_version='2026-11-16.v5')


def _insert(conn, **over):
    row = {**ROW, **over}
    cols = ', '.join(row)
    conn.execute(sa.text(f"INSERT INTO plan_excursions ({cols}) VALUES "
                         f"({', '.join(':' + c for c in row)})"), row)


@pytest.fixture
def clean(db_engine):
    with db_engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM plan_excursions WHERE ticker = 'ZZPX'"))
    yield db_engine
    with db_engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM plan_excursions WHERE ticker = 'ZZPX'"))


def test_schema_applies_a_second_time_and_keeps_one_policy_row(clean, monkeypatch):
    from gcp import apply_schema
    engine = clean

    def execute(sql):
        with engine.begin() as c:
            c.execute(sa.text(sql))

    monkeypatch.setattr(apply_schema, 'execute_sql', execute)
    with engine.begin() as conn:
        _insert(conn)
    for unit in apply_schema.split_statement_groups((REPO / 'gcp/schema.sql').read_text()):
        apply_schema.run_unit(unit)
    with engine.connect() as conn:
        n = conn.execute(sa.text(
            "SELECT COUNT(*) FROM level_param_policy WHERE param_key = 'target_reach_rate'")).scalar()
        kept = conn.execute(sa.text(
            "SELECT excursion_r FROM plan_excursions WHERE ticker = 'ZZPX'")).scalar()
    assert n == 1
    assert kept == pytest.approx(2.9)


def test_the_source_check_refuses_another_writer(clean):
    with pytest.raises(sa.exc.DBAPIError, match="plan_excursions_"):
        with clean.begin() as conn:
            _insert(conn, source='other')


def test_one_row_per_ticker_session_and_rule_version(clean):
    with clean.begin() as conn:
        _insert(conn)
    with pytest.raises(sa.exc.DBAPIError, match="plan_excursions_"):
        with clean.begin() as conn:
            _insert(conn, side='calls')


def test_history_job_reads_one_month_per_query_and_writes_only_its_rows(clean, monkeypatch):
    """gcp.backfill_plan_excursions on Postgres: its month bar read (the
    as-traded market_data_intraday 1-minute bars, 09:30 ET to the close)
    runs once per ticker-month, a half day is cut at 13:00 ET, the resume
    read finds its own last row, and every write is to plan_excursions."""
    from datetime import date

    import pandas as pd

    from gcp import backfill_plan_excursions as job
    from gcp.premarket_playbook_resolver import PLAN_OK, PlanInputs
    from lib.strat_levels import LEVEL_RULE_VERSION

    engine = clean
    sessions = [date(2025, 11, 26), date(2025, 11, 28), date(2025, 12, 1)]  # 11-28 closes 13:00
    rows = []
    for s in sessions:
        t0 = pd.Timestamp(f'{s} 09:25', tz='America/New_York')
        for i in range(400):                 # 09:25 to 16:04 ET
            # 09:25 to 09:29 ET is premarket and runs well past the trigger
            # (103.0); the read keeps the regular session only, so these bars
            # change neither the fill nor the excursion.
            px = 103.0 if i < 5 else 100.0 if i < 10 else 101.0 + i / 1000
            rows.append(dict(ticker='ZZPX', interval='1min', ts=(t0 + pd.Timedelta(minutes=i)
                             ).tz_convert('UTC').to_pydatetime(),
                             open=px, high=px + 0.01, low=px - 0.01, close=px))
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM market_data_intraday WHERE ticker = 'ZZPX'"))
        conn.execute(sa.text(
            "INSERT INTO market_data_intraday (ticker, interval, ts, open, high, low, close) "
            "VALUES (:ticker, :interval, :ts, :open, :high, :low, :close)"), rows)

    def plan_inputs(side, row, basis, policy_fn):
        if side == 'calls':
            return PlanInputs(trigger_price=100.5, stop_price=99.5, targets=(102.5,), legs=3,
                              cutoff_minutes=16 * 60, target_status=PLAN_OK)
        return PlanInputs(trigger_price=None, stop_price=None, target_status='not_entered')

    monkeypatch.setattr(job, 'plan_inputs', plan_inputs)
    statements = []

    def record(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    sa.event.listen(engine, 'before_cursor_execute', record)
    try:
        (stats,) = job.run(engine, ['ZZPX'], sessions[0], sessions[-1], resume=False,
                           basis_fn=lambda t, s: {'rule_version': LEVEL_RULE_VERSION},
                           log=lambda _l: None)
        assert job.last_written(engine, 'ZZPX', LEVEL_RULE_VERSION) == sessions[-1]
    finally:
        sa.event.remove(engine, 'before_cursor_execute', record)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM market_data_intraday WHERE ticker = 'ZZPX'"))
        got = conn.execute(sa.text(
            "SELECT session_date, excursion_r FROM plan_excursions WHERE ticker = 'ZZPX' "
            "ORDER BY session_date")).fetchall()
    bar_reads = [s for s in statements if 'FROM market_data_intraday' in s]
    writes = [s for s in statements if s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
    assert len(bar_reads) == 2                                   # November, December
    assert stats.written == 3 and all('plan_excursions' in s for s in writes)
    # Highs run 101.01 + i/1000 from 09:35 ET; the furthest bar before the
    # close is 15:59 ET (i 394) on a full day and 12:59 ET (i 214) on 11-28.
    assert [(str(d), round(x, 3)) for d, x in got] == [
        ('2025-11-26', round(101.01 + 394 / 1000 - 100.5, 3)),
        ('2025-11-28', round(101.01 + 214 / 1000 - 100.5, 3)),
        ('2025-12-01', round(101.01 + 394 / 1000 - 100.5, 3))]
