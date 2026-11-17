"""FEAT-STRAT-001 target hit rates r2, done_when 'Reader' and 'Brief copy':
lib.target_reach reads every run ticker's past trades in one query, in the
policy's window, before the brief's own session, of the entry rule version
it is given, in the policy's measure; a NULL excursion reaches nothing and
still counts; and it formats the count text the quarter lines print
(docs/superpowers/specs/2026-11-17-feat-strat-001-target-hit-rates-r2.md)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa

from lib.strat_levels import LEVEL_RULE_VERSION, entry_rule_version, policy_wide_param
from lib.target_reach import (
    NO_STOP_TEXT, ReachTable, TargetReachUnavailable, load_target_reach, pct_half_up,
    unavailable_text,
)

DDL = ("CREATE TABLE plan_excursions (ticker TEXT, session_date DATE, rule_version TEXT, "
       "side TEXT, excursion_r REAL, excursion_held5_r REAL, excursion_atr REAL, "
       "excursion_held5_atr REAL)")
V = entry_rule_version(LEVEL_RULE_VERSION)


def _param(**over):
    row = {'param_key': 'target_reach_rate', 'method_id': 'plan_excursion_share',
           'effective_from': '2015-01-02', 'min_sample': 30, 'lookback_sessions': None,
           'extra': {'since': '2022-01-03', 'measure': 'touch_atr'}}
    row.update(over)
    return policy_wide_param('target_reach_rate', row, 'SPY', 'atr_14')


def _measure(m):
    return _param(extra={'since': '2022-01-03', 'measure': m})


class Db:
    def __init__(self, rows):
        self.engine = sa.create_engine('sqlite://')
        self.queries = []
        with self.engine.begin() as c:
            c.execute(sa.text(DDL))
            for r in rows:
                c.execute(sa.text(
                    "INSERT INTO plan_excursions VALUES (:t, :d, :v, 'calls', :x, :h, :xa, :ha)"),
                    {'v': V, 'h': None, 'xa': None, 'ha': None, **r})

    def query(self, sql, params):
        self.queries.append((sql, params))
        with self.engine.connect() as c:
            return pd.read_sql(sa.text(sql), c, params=params)


# x and h in stop distances, xa and ha in ATR (an ATR of twice the stop
# distance, so each ATR value is half the stop-distance one).
ROWS = [
    {'t': 'SPY', 'd': '2021-12-30', 'x': 5.0, 'xa': 2.5},                       # before since
    {'t': 'SPY', 'd': '2022-01-03', 'x': 0.5, 'h': 0.2, 'xa': 0.25, 'ha': 0.1},
    {'t': 'SPY', 'd': '2022-01-04', 'x': 1.2, 'h': 1.0, 'xa': 0.6, 'ha': 0.5},
    {'t': 'SPY', 'd': '2022-01-05', 'x': None, 'h': None},                      # fill bar to stop bar
    {'t': 'SPY', 'd': '2022-01-06', 'x': 2.0, 'h': 0.9, 'xa': 1.0, 'ha': 0.45},
    {'t': 'SPY', 'd': '2022-01-07', 'x': 9.0, 'xa': 4.5},                       # the brief's session
    {'t': 'QQQ', 'd': '2022-01-04', 'x': 0.3, 'xa': 0.15},
    {'t': 'SPY', 'd': '2022-01-04', 'x': 7.0, 'xa': 3.5, 'v': 'feat-strat-001.v2'},  # other version
]


def _db():
    return Db(ROWS)


def _load(db, tickers, session, param=None, version=V):
    return load_target_reach(db.query, tickers, session, param or _param(), version)


def test_one_query_for_three_tickers():
    db = _db()
    got = _load(db, ['spy', 'QQQ', 'IWM'], '2022-01-07')
    assert len(db.queries) == 1
    assert sorted(got) == ['IWM', 'QQQ', 'SPY']
    assert got['IWM'] == ReachTable('IWM', 0, None, None, ())
    assert got['IWM'].share_at_least(0.5) is None


def test_the_since_window_and_the_point_in_time_cut():
    got = _load(_db(), ['SPY'], '2022-01-07')['SPY']
    # 2021-12-30 is before since; 2022-01-07 is the brief's own session; the
    # v2 row is another entry version.
    assert (got.n, got.first, got.last) == (4, '2022-01-03', '2022-01-06')
    assert got.values == (0.25, 0.6, None, 1.0)
    got = _load(_db(), ['SPY'], '2022-01-06')['SPY']
    assert got.last == '2022-01-05' and got.n == 3


def test_the_version_filter_is_the_argument_never_a_constant():
    db = _db()
    got = _load(db, ['SPY'], '2022-01-07', version='feat-strat-001.v2')['SPY']
    assert got.values == (3.5,)
    assert db.queries[0][1]['rule_version'] == 'feat-strat-001.v2'
    with pytest.raises(TargetReachUnavailable, match='no entry rule version'):
        _load(_db(), ['SPY'], '2022-01-07', version=None)


@pytest.mark.parametrize('measure, values', [
    ('touch_atr', (0.25, 0.6, None, 1.0)),
    ('held_5m_atr', (0.1, 0.5, None, 0.45)),
    ('touch', (0.5, 1.2, None, 2.0)),
    ('held_5m', (0.2, 1.0, None, 0.9)),
])
def test_each_measure_reads_its_column(measure, values):
    got = _load(_db(), ['SPY'], '2022-01-07', _measure(measure))['SPY']
    assert got.values == values


def test_the_null_rule():
    got = _load(_db(), ['SPY'], '2022-01-07')['SPY']
    assert got.share_at_least(0.25) == pytest.approx(3 / 4)
    assert got.share_at_least(0.6) == pytest.approx(2 / 4)
    assert got.share_at_least(1.01) == 0.0
    assert got.share_at_least(-1.0) == pytest.approx(3 / 4)   # NULL never reaches


def test_the_lookback_window():
    db = _db()
    p = _param(lookback_sessions=2)
    got = _load(db, ['SPY', 'QQQ'], '2022-01-07', p)
    assert len(db.queries) == 1 and 'ROW_NUMBER()' in db.queries[0][0]
    assert got['SPY'].values == (None, 1.0)
    assert (got['SPY'].first, got['SPY'].last) == ('2022-01-05', '2022-01-06')
    assert got['QQQ'].n == 1
    # The lookback reads before since too: the ticker's last n trades.
    got = _load(db, ['SPY'], '2022-01-03', p)['SPY']
    assert got.values == (2.5,) and got.first == '2021-12-30'


def test_a_raising_query_or_an_unusable_param_raises():
    def boom(sql, params):
        raise RuntimeError('relation "plan_excursions" does not exist')
    with pytest.raises(TargetReachUnavailable, match='does not exist'):
        load_target_reach(boom, ['SPY'], '2022-01-07', _param(), V)
    with pytest.raises(TargetReachUnavailable):
        _load(_db(), ['SPY'], '2022-01-07', _param(min_sample=0))
    with pytest.raises(TargetReachUnavailable):
        load_target_reach(_db().query, ['SPY'], '2022-01-07', None, V)
    with pytest.raises(TargetReachUnavailable):
        load_target_reach(lambda s, p: None, ['SPY'], '2022-01-07', _param(), V)


# ── done_when 'Brief copy': the count text the quarter lines print ──────

def _table(n_reached, n, d=0.25):
    return ReachTable('IWM', n, '2022-01-03', '2025-10-21',
                      tuple([d] * n_reached + [None] * (n - n_reached)))


@pytest.mark.parametrize('k, n, want', [
    (1, 2, 50), (1, 3, 33), (2, 3, 67), (1, 8, 13), (3, 8, 38), (0, 5, 0), (5, 5, 100),
])
def test_the_percent_rounds_half_up(k, n, want):
    assert pct_half_up(k, n) == want


def test_the_count_text_at_below_and_with_no_trades():
    assert _table(16, 31).count_text(0.25, 30) == 'reached 16 of 31 (52%)'
    assert _table(16, 30).count_text(0.25, 30) == 'reached 16 of 30 (53%)'
    assert _table(12, 29).count_text(0.25, 30) == 'reached 12 of 29'
    assert ReachTable('IWM', 0, None, None, ()).count_text(0.25, 30) == 'no history yet'
    assert _table(0, 31).count_text(0.25, 30) == 'reached 0 of 31 (0%)'


def test_the_header_unavailable_and_no_stop_lines():
    assert _table(1, 906).header_text() == \
        'Reached before the stop: IWM trades 2022-01-03 to 2025-10-21 (906)'
    assert unavailable_text('input_unavailable') == \
        'Reached before the stop: unavailable (input_unavailable).'
    assert NO_STOP_TEXT == 'Reached before the stop: unavailable (no stop to measure from).'


def test_design_5_iwm_counts_in_atr():
    """The Experiment's 906 IWM trades before 2025-10-22, in ATR: Design 5's
    puts side (trigger 245.66, ATR 4.48) reads these counts."""
    r = json.loads((Path(__file__).resolve().parents[1] / 'fixtures'
                    / 'iwm_reach_atr_before_2025_10_22.json').read_text())
    t = ReachTable('IWM', r['n'], r['first'], r['last'], tuple(r['excursion_atr']))
    assert t.header_text() == 'Reached before the stop: IWM trades 2022-01-03 to 2025-10-21 (906)'
    assert t.count_text((245.66 - 245.50) / 4.48, 30) == 'reached 802 of 906 (89%)'
    assert [t.count_text(q, 30) for q in (0.25, 0.5, 0.75, 1.0)] == [
        'reached 475 of 906 (52%)', 'reached 247 of 906 (27%)',
        'reached 105 of 906 (12%)', 'reached 38 of 906 (4%)']
