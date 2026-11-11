"""Site 1 of the EarningsWhispers retirement: ``refresh_daily``'s upcoming_sql.

The reader's own SQL runs in SQLite over a fixture whose EW row is chosen to
win every aggregate of the per-ticker subquery on main (earlier date,
'premarket' > 'postmarket', 'Zz Corp' > 'Acme', larger expected_move and
volumes, score and strategy). ``MAX(market_cap)`` and ``MAX(sector)`` are
consistency controls only: the retired writer stored None and '' there, so
an EW row cannot win them on main either.

The negative control is main's upcoming_sql (e9a06998) verbatim.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from gcp import refresh_earnings_views as rev
from lib.earnings_reactions import EARNINGS_NOT_RETIRED_SQL
from tests.fixtures.earnings_calendar_sources import (
    av, ew_only, ew_raw_alias, hydrated, make_db, null_source, run_earnings_sql,
    unknown_source, uw, yahoo, yahoo_bulk,
)

TODAY = date.today()
D = TODAY + timedelta(days=3)

# gcp/refresh_earnings_views.py upcoming_sql at main e9a06998, verbatim.
MAIN_UPCOMING_SQL = """
        SELECT u.ticker, u.earnings_date, u.earnings_time, u.company_name,
               u.market_cap, u.sector, u.eps_estimate, u.expected_move,
               u.options_volume, u.open_interest, u.score, u.strategy,
               (SELECT close FROM market_data_daily md
                 WHERE md.ticker = u.ticker
                   AND md.date < u.earnings_date
                 ORDER BY md.date DESC LIMIT 1) AS prev_close
        FROM (
            SELECT ticker,
                   MIN(earnings_date) AS earnings_date,
                   MAX(earnings_time) AS earnings_time,
                   MAX(company_name)  AS company_name,
                   MAX(market_cap)    AS market_cap,
                   MAX(sector)        AS sector,
                   MAX(eps_estimate)  AS eps_estimate,
                   MAX(expected_move) AS expected_move,
                   MAX(options_volume) AS options_volume,
                   MAX(open_interest) AS open_interest,
                   MAX(score)         AS score,
                   MAX(strategy)      AS strategy
            FROM earnings_calendar
            WHERE earnings_date BETWEEN CURRENT_DATE
                                    AND CURRENT_DATE + (:days)::int
            GROUP BY ticker
        ) u
        ORDER BY u.earnings_date, u.ticker
    """


def fixture_rows() -> list[dict]:
    return [
        # T: mixed ticker; the hydrated EW row is dated D-1.
        av('T', D, earnings_time='postmarket'),
        uw('T', D),
        hydrated(ew_only('T', D - timedelta(days=1), earnings_time='premarket')),
        # E / R: EW-only tickers, both spellings.
        ew_only('E', D),
        ew_raw_alias('R', D),
        # Non-EW controls. Y is a Yahoo row as the calendar path writes it;
        # M mixes AV with such a Yahoo row, whose 'unknown' time wins
        # MAX(earnings_time) on main and on this branch alike.
        yahoo('Y', D),
        yahoo_bulk('B', D),
        av('M', D, earnings_time='postmarket'),
        yahoo('M', D),
        av('A', D, company_name='Beta'),
        null_source('N', D, company_name='NullCo'),
        unknown_source('K', D, company_name='UnknownCo'),
    ]


MARKET = [{'ticker': t, 'date': TODAY - timedelta(days=1), 'close': 100.0}
          for t in ('T', 'Y', 'B', 'M', 'A', 'N', 'K', 'E', 'R')]


@pytest.fixture
def refresh(monkeypatch):
    """Run refresh_daily with every database boundary faked; the upcoming
    query runs in SQLite over the fixture rows."""
    conn = make_db(fixture_rows(), MARKET)
    state = {'sql': [], 'upserted': None}

    def query(sql, params=None):
        if 'FROM earnings_calendar' in sql:
            state['sql'].append(sql)
            return run_earnings_sql(conn, sql, params, today=TODAY)
        if 'FROM earnings_ticker_lean' in sql or 'FROM earnings_event_outcomes' in sql:
            return pd.DataFrame()
        if 'FROM earnings_calibration' in sql:
            return pd.DataFrame()
        raise AssertionError(f"unexpected SQL: {sql[:80]}")

    def replace(df, refresh_date):
        assert refresh_date == TODAY
        state['upserted'] = df.copy()
        return len(df)

    from gcp import database
    monkeypatch.setattr(database, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(database, 'query_to_dataframe', query)
    monkeypatch.setattr(rev, 'query_to_dataframe', query)
    monkeypatch.setattr(rev, 'execute_sql', lambda *a, **k: None)
    monkeypatch.setattr(rev, '_replace_upcoming_rows', replace)
    state['conn'] = conn
    return state


def _by_ticker(df) -> dict:
    """Records keyed by ticker, NaN read back as None for comparison."""
    return {r['ticker']: {k: (None if isinstance(v, float) and v != v else v)
                          for k, v in r.items()}
            for r in df.to_dict('records')}


def test_upcoming_sql_carries_the_predicate_and_drops_score_and_strategy(refresh):
    rev.refresh_daily(14)
    (sql,) = refresh['sql']
    assert EARNINGS_NOT_RETIRED_SQL in sql
    # Inside the aggregating subquery, before its GROUP BY.
    inner = sql[sql.index('FROM earnings_calendar'):sql.index('GROUP BY ticker')]
    assert 'AND ' + EARNINGS_NOT_RETIRED_SQL in inner
    for gone in ('u.score', 'u.strategy', 'MAX(score)', 'MAX(strategy)'):
        assert gone not in sql


def test_main_shaped_query_returns_the_ew_values(refresh):
    """Negative control: main's text lets the EW row win every aggregate."""
    got = _by_ticker(run_earnings_sql(refresh['conn'], MAIN_UPCOMING_SQL,
                                      {'days': 14}, today=TODAY))
    t = got['T']
    assert t['earnings_date'] == D - timedelta(days=1)
    assert t['earnings_time'] == 'premarket'
    assert t['company_name'] == 'Zz Corp'
    assert t['expected_move'] == 9.0
    assert (t['options_volume'], t['open_interest']) == (30000, 90000)
    assert (t['score'], t['strategy']) == (85.0, 'Long Calls')
    # Consistency controls: already the AV/UW values on main.
    assert (t['market_cap'], t['sector']) == (5e9, 'Tech')
    assert {'E', 'R'} <= set(got)


def test_predicated_query_returns_the_av_uw_values(refresh):
    rev.refresh_daily(14)
    (sql,) = refresh['sql']
    got = _by_ticker(run_earnings_sql(refresh['conn'], sql, {'days': 14}, today=TODAY))
    t = got['T']
    assert t['earnings_date'] == D
    assert t['earnings_time'] == 'postmarket'
    assert t['company_name'] == 'Acme'
    assert t['expected_move'] == 5.0
    assert (t['options_volume'], t['open_interest']) == (20000, 50000)
    assert (t['market_cap'], t['sector']) == (5e9, 'Tech')
    assert 'score' not in t and 'strategy' not in t
    # EW-only tickers absent; NULL and unknown sources kept.
    assert set(got) == {'T', 'Y', 'B', 'M', 'A', 'N', 'K'}


def test_non_ew_output_equals_main(refresh):
    """AV/UW/Yahoo/NULL/unknown tickers with no EW row read the same as main."""
    rev.refresh_daily(14)
    (sql,) = refresh['sql']
    new = _by_ticker(run_earnings_sql(refresh['conn'], sql, {'days': 14}, today=TODAY))
    old = _by_ticker(run_earnings_sql(refresh['conn'], MAIN_UPCOMING_SQL,
                                      {'days': 14}, today=TODAY))
    for tk in ('Y', 'B', 'M', 'A', 'N', 'K'):
        assert new[tk] == {k: v for k, v in old[tk].items()
                           if k not in ('score', 'strategy')}
    # Positive control: the producer-shaped Yahoo row is really aggregated.
    assert new['M']['earnings_time'] == 'unknown'
    assert new['M']['company_name'] == 'Acme'


def test_refreshed_rows_carry_no_ew_value(refresh):
    rev.refresh_daily(14)
    rows = _by_ticker(refresh['upserted'])
    assert set(rows) == {'T', 'Y', 'B', 'M', 'A', 'N', 'K'}
    t = rows['T']
    assert t['earnings_date'] == D
    assert t['earnings_time'] == 'postmarket'
    assert t['company_name'] == 'Acme'
    assert t['expected_move'] == 5.0
    assert t['implied_move_pct'] == pytest.approx(5.0)
    assert (t['options_volume'], t['open_interest']) == (20000, 50000)
