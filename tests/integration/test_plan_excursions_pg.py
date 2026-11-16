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
    with pytest.raises(sa.exc.IntegrityError):
        with clean.begin() as conn:
            _insert(conn, source='other')


def test_one_row_per_ticker_session_and_rule_version(clean):
    with clean.begin() as conn:
        _insert(conn)
    with pytest.raises(sa.exc.IntegrityError):
        with clean.begin() as conn:
            _insert(conn, side='calls')
