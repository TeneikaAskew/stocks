"""FEAT-STRAT-001 target hit rates, done_when 'Reader': lib.target_reach
reads every run ticker's past trades in one query, in the policy's window,
before the brief's own session, of the current rule version, with the
policy's measure; a NULL excursion reaches nothing and still counts
(docs/superpowers/specs/2026-11-16-feat-strat-001-target-hit-rates.md)."""
from __future__ import annotations

import pandas as pd
import pytest
import sqlalchemy as sa

from lib.strat_levels import LEVEL_RULE_VERSION, policy_wide_param
from lib.target_reach import ReachTable, TargetReachUnavailable, load_target_reach

DDL = ("CREATE TABLE plan_excursions (ticker TEXT, session_date DATE, rule_version TEXT, "
       "side TEXT, excursion_r REAL, excursion_held5_r REAL)")


def _param(**over):
    row = {'param_key': 'target_reach_rate', 'method_id': 'plan_excursion_share',
           'effective_from': '2015-01-02', 'min_sample': 30, 'lookback_sessions': None,
           'extra': {'since': '2022-01-03', 'measure': 'touch'}}
    row.update(over)
    return policy_wide_param('target_reach_rate', row, 'SPY', 'atr_14')


class Db:
    def __init__(self, rows):
        self.engine = sa.create_engine('sqlite://')
        self.queries = []
        with self.engine.begin() as c:
            c.execute(sa.text(DDL))
            for r in rows:
                c.execute(sa.text(
                    "INSERT INTO plan_excursions VALUES (:t, :d, :v, 'calls', :x, :h)"),
                    {'v': LEVEL_RULE_VERSION, 'h': None, **r})

    def query(self, sql, params):
        self.queries.append((sql, params))
        with self.engine.connect() as c:
            return pd.read_sql(sa.text(sql), c, params=params)


ROWS = [
    {'t': 'SPY', 'd': '2021-12-30', 'x': 5.0},               # before since
    {'t': 'SPY', 'd': '2022-01-03', 'x': 0.5, 'h': 0.2},
    {'t': 'SPY', 'd': '2022-01-04', 'x': 1.2, 'h': 1.0},
    {'t': 'SPY', 'd': '2022-01-05', 'x': None, 'h': None},  # nothing between fill and stop
    {'t': 'SPY', 'd': '2022-01-06', 'x': 2.0, 'h': 0.9},
    {'t': 'SPY', 'd': '2022-01-07', 'x': 9.0},               # the brief's own session
    {'t': 'QQQ', 'd': '2022-01-04', 'x': 0.3},
    {'t': 'SPY', 'd': '2022-01-02', 'x': 7.0, 'v': 'feat-strat-001.v2'},  # another rule
]


def _db():
    return Db(ROWS)


def test_one_query_for_three_tickers():
    db = _db()
    got = load_target_reach(db.query, ['spy', 'QQQ', 'IWM'], '2022-01-07', _param())
    assert len(db.queries) == 1
    assert sorted(got) == ['IWM', 'QQQ', 'SPY']
    assert got['IWM'] == ReachTable('IWM', 0, None, None, ())
    assert got['IWM'].share_at_least(0.5) is None


def test_the_since_window_and_the_point_in_time_cut():
    got = load_target_reach(_db().query, ['SPY'], '2022-01-07', _param())['SPY']
    # 2021-12-30 is before since; 2022-01-07 is the brief's own session; the
    # v2 row is another rule version.
    assert (got.n, got.first, got.last) == (4, '2022-01-03', '2022-01-06')
    assert got.values == (0.5, 1.2, None, 2.0)
    got = load_target_reach(_db().query, ['SPY'], '2022-01-06', _param())['SPY']
    assert got.last == '2022-01-05' and got.n == 3


def test_the_null_rule():
    got = load_target_reach(_db().query, ['SPY'], '2022-01-07', _param())['SPY']
    assert got.share_at_least(0.5) == pytest.approx(3 / 4)
    assert got.share_at_least(1.2) == pytest.approx(2 / 4)
    assert got.share_at_least(2.01) == 0.0
    assert got.share_at_least(-1.0) == pytest.approx(3 / 4)   # NULL never reaches


def test_the_measure_switch():
    p = _param(extra={'since': '2022-01-03', 'measure': 'held_5m'})
    got = load_target_reach(_db().query, ['SPY'], '2022-01-07', p)['SPY']
    assert got.values == (0.2, 1.0, None, 0.9)
    assert got.share_at_least(1.0) == pytest.approx(1 / 4)


def test_the_lookback_window():
    db = _db()
    p = _param(lookback_sessions=2)
    got = load_target_reach(db.query, ['SPY', 'QQQ'], '2022-01-07', p)
    assert len(db.queries) == 1 and 'ROW_NUMBER()' in db.queries[0][0]
    assert got['SPY'].values == (None, 2.0)
    assert (got['SPY'].first, got['SPY'].last) == ('2022-01-05', '2022-01-06')
    assert got['QQQ'].n == 1
    # The lookback reads before since too: the ticker's last n trades.
    got = load_target_reach(db.query, ['SPY'], '2022-01-03', p)['SPY']
    assert got.values == (5.0,) and got.first == '2021-12-30'


def test_a_raising_query_or_an_unusable_param_raises():
    def boom(sql, params):
        raise RuntimeError('relation "plan_excursions" does not exist')
    with pytest.raises(TargetReachUnavailable, match='does not exist'):
        load_target_reach(boom, ['SPY'], '2022-01-07', _param())
    with pytest.raises(TargetReachUnavailable):
        load_target_reach(_db().query, ['SPY'], '2022-01-07', _param(min_sample=0))
    with pytest.raises(TargetReachUnavailable):
        load_target_reach(_db().query, ['SPY'], '2022-01-07', None)
    with pytest.raises(TargetReachUnavailable):
        load_target_reach(lambda s, p: None, ['SPY'], '2022-01-07', _param())
