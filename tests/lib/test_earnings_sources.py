"""The retired-source predicate (FEAT-CATALYST-001, EarningsWhispers retirement).

Executes ``EARNINGS_NOT_RETIRED_SQL`` over the eight alias-control values of
RETIREMENT-DESIGN section 2.2 in SQLite (same three-valued NULL logic as
PostgreSQL for ``NOT IN``). The per-reader controls live in the per-site
tests.
"""
import sqlite3

import pytest

from lib.earnings_reactions import (
    EARNINGS_NOT_RETIRED_SQL,
    RETIRED_EARNINGS_SOURCES,
    earnings_not_retired_sql,
)
from tests.fixtures.earnings_calendar_sources import ALIAS_CONTROL_VALUES


def _kept(predicate: str) -> list:
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE earnings_calendar (id INTEGER, data_source TEXT)")
    conn.executemany("INSERT INTO earnings_calendar VALUES (?, ?)",
                     list(enumerate(ALIAS_CONTROL_VALUES)))
    rows = conn.execute(
        f"SELECT data_source FROM earnings_calendar WHERE 1 = 1 AND {predicate} ORDER BY id"
    ).fetchall()
    return [r[0] for r in rows]


def test_constants():
    assert RETIRED_EARNINGS_SOURCES == ('earnings_whispers', 'EarningsWhispers')
    assert EARNINGS_NOT_RETIRED_SQL == (
        "(data_source IS NULL OR data_source NOT IN "
        "('earnings_whispers', 'EarningsWhispers'))"
    )
    assert earnings_not_retired_sql() == EARNINGS_NOT_RETIRED_SQL
    # The alias form differs only by the qualifying prefix.
    assert earnings_not_retired_sql('ec') == EARNINGS_NOT_RETIRED_SQL.replace(
        'data_source', 'ec.data_source')


@pytest.mark.parametrize('alias', ['', 'ec.', 'ec; DROP', '1ec', 'e c'])
def test_alias_must_be_an_identifier(alias):
    with pytest.raises(ValueError):
        earnings_not_retired_sql(alias)


def test_predicate_keeps_null_and_unknown_rows():
    kept = _kept(EARNINGS_NOT_RETIRED_SQL)
    assert None in kept
    assert 'unknown' in kept
    # Negative control: the plain NOT IN drops the NULL row.
    plain = _kept("data_source NOT IN ('earnings_whispers', 'EarningsWhispers')")
    assert None not in plain
    assert 'unknown' in plain


def test_predicate_excludes_exactly_the_two_aliases():
    kept = _kept(EARNINGS_NOT_RETIRED_SQL)
    assert kept == [None, 'unknown', 'Earnings_Whispers',
                    'alphavantage', 'unusual_whales', 'yahoo']
    dropped = [v for v in ALIAS_CONTROL_VALUES if v not in kept]
    assert dropped == ['earnings_whispers', 'EarningsWhispers']


def test_alias_form_executes_the_same_over_a_qualified_table():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE earnings_calendar (id INTEGER, data_source TEXT)")
    conn.executemany("INSERT INTO earnings_calendar VALUES (?, ?)",
                     list(enumerate(ALIAS_CONTROL_VALUES)))
    rows = conn.execute(
        "SELECT ec.data_source FROM earnings_calendar ec "
        f"WHERE 1 = 1 AND {earnings_not_retired_sql('ec')} ORDER BY ec.id"
    ).fetchall()
    assert [r[0] for r in rows] == _kept(EARNINGS_NOT_RETIRED_SQL)
