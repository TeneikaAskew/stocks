"""Site 4 of the EarningsWhispers retirement: the watchlist's ``upcoming`` CTE.

The CTE text the job actually sends runs in SQLite over a fixture whose EW
row is dated earlier and timed 'premarket' (> 'postmarket'), so on main it
wins ``MIN(earnings_date)`` and ``MAX(earnings_time)``. ``MAX(market_cap)``
and ``MAX(sector)`` are consistency controls only: the retired writer stored
None and '' there. The rest of the query (the join to the strategy winners)
is unchanged and PostgreSQL-only, so it is not executed here.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd
import pytest

from gcp import earnings_long_watchlist as gwl
from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL
from tests.fixtures.earnings_calendar_sources import (
    av, ew_only, ew_raw_alias, make_db, null_source, run_earnings_sql,
    unknown_source, yahoo,
)

TODAY = date.today()
D = TODAY


def _rows():
    return [
        av('T', D + timedelta(days=3), earnings_time='postmarket'),
        ew_only('T', D + timedelta(days=1), earnings_time='premarket'),
        ew_only('E', D + timedelta(days=2)),
        ew_raw_alias('R', D + timedelta(days=2)),
        yahoo('Y', D + timedelta(days=4)),
        null_source('N', D + timedelta(days=4)),
        unknown_source('K', D + timedelta(days=4)),
    ]


@pytest.fixture
def upcoming_cte(monkeypatch):
    seen = []

    def strict(sql, params=None):
        seen.append((sql, dict(params or {})))
        return pd.DataFrame()

    monkeypatch.setattr(gwl, 'query_to_dataframe_strict', strict)
    gwl._query_watchlist(7)
    ((sql, params),) = seen
    m = re.search(r"upcoming AS \((.*?)\n\s*\)\s*\n\s*SELECT u\.ticker", sql, re.S)
    assert m, "upcoming CTE not found"
    return m.group(1), params


def _run(cte, params, *, strip=False):
    if strip:
        assert cte.count('AND ' + EARNINGS_NOT_RETIRED_SQL) == 1
        cte = cte.replace('AND ' + EARNINGS_NOT_RETIRED_SQL, '')
    df = run_earnings_sql(make_db(_rows()), cte, params, today=TODAY)
    return {r['ticker']: r for r in df.to_dict('records')}


def test_upcoming_cte_carries_the_predicate(upcoming_cte):
    cte, _ = upcoming_cte
    where = cte[cte.index('FROM earnings_calendar'):cte.index('GROUP BY ticker')]
    assert 'AND ' + EARNINGS_NOT_RETIRED_SQL in where


def test_main_shaped_cte_takes_the_ew_date_and_time(upcoming_cte):
    got = _run(*upcoming_cte, strip=True)
    t = got['T']
    assert t['earnings_date'] == D + timedelta(days=1)
    assert t['earnings_time'] == 'premarket'
    assert (t['market_cap'], t['sector']) == (5e9, 'Tech')   # consistency
    assert {'E', 'R'} <= set(got)


def test_predicated_cte_takes_the_av_date_and_time(upcoming_cte):
    got = _run(*upcoming_cte)
    t = got['T']
    assert t['earnings_date'] == D + timedelta(days=3)
    assert t['earnings_time'] == 'postmarket'
    assert (t['market_cap'], t['sector']) == (5e9, 'Tech')   # consistency
    assert set(got) == {'T', 'Y', 'N', 'K'}


def test_non_ew_rows_equal_main(upcoming_cte):
    new = _run(*upcoming_cte)
    old = _run(*upcoming_cte, strip=True)
    clean = lambda r: {k: (None if isinstance(v, float) and v != v else v)  # noqa: E731
                       for k, v in r.items()}
    for tk in ('Y', 'N', 'K'):
        assert clean(new[tk]) == clean(old[tk])
