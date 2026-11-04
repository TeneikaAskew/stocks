"""Row builders for the EarningsWhispers retirement controls (FEAT-CATALYST-001).

Pure builders for ``earnings_calendar`` rows, one per source the table holds,
plus the alias controls of the retirement design (NULL, ``unknown``, both
EarningsWhispers spellings and the non-alias ``Earnings_Whispers``).

Values are chosen for string and numeric ordering, so that an EW row WINS a
reader's ``MIN``/``MAX``/``ORDER BY`` when the reader does not exclude it:
``'Zz Corp' > 'Acme'``, ``'premarket' > 'postmarket'``, ``9.0 > 5.0``,
``30000 > 20000``. EW rows carry what the retired writer emitted
(``market_cap`` None, ``sector`` ''), so ``MAX(market_cap)`` and
``MAX(sector)`` cannot pick an EW value: those columns are consistency
controls only.

``run_earnings_sql`` executes a reader's own SQL text against these rows in
an in-memory SQLite database. It rewrites only the handful of PostgreSQL
spellings the readers use (date arithmetic, ``CAST(... AS date)``,
``BOOL_OR``, ``= ANY(:list)``) and fails loudly on any it does not know, so a
query it cannot translate is never silently run as something else. SQLite
uses the same three-valued NULL logic as PostgreSQL for ``NOT IN``.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from typing import Optional

import pandas as pd

# The eight data_source values of RETIREMENT-DESIGN section 2.2.
ALIAS_CONTROL_VALUES = (
    None, 'unknown', 'earnings_whispers', 'EarningsWhispers',
    'Earnings_Whispers', 'alphavantage', 'unusual_whales', 'yahoo',
)

COLUMNS = (
    'ticker', 'earnings_date', 'earnings_time', 'company_name', 'market_cap',
    'sector', 'eps_estimate', 'has_options', 'expected_move', 'options_volume',
    'open_interest', 'stock_volume', 'score', 'strategy', 'strike',
    'data_source',
)


def _row(ticker: str, earnings_date: date, data_source: Optional[str],
         **values) -> dict:
    unknown = set(values) - set(COLUMNS)
    if unknown:
        raise KeyError(f"not an earnings_calendar column: {sorted(unknown)}")
    row = {c: None for c in COLUMNS}
    row.update(ticker=ticker, earnings_date=earnings_date,
               data_source=data_source, strategy='')
    row.update(values)
    return row


def ew_only(ticker: str, earnings_date: date, *,
            data_source: str = 'earnings_whispers', **values) -> dict:
    """An EarningsWhispers pick as the retired writer stored it."""
    base = dict(
        earnings_time='premarket', company_name='Zz Corp', market_cap=None,
        sector='', eps_estimate=None, has_options=True, expected_move=9.0,
        options_volume=None, open_interest=None, stock_volume=None,
        score=85.0, strategy='Long Calls', strike=100.0,
    )
    base.update(values)
    return _row(ticker, earnings_date, data_source, **base)


def av(ticker: str, earnings_date: date, **values) -> dict:
    base = dict(
        earnings_time='postmarket', company_name='Acme', market_cap=5e9,
        sector='Tech', eps_estimate=1.23, has_options=None, expected_move=None,
        options_volume=None, open_interest=None,
    )
    base.update(values)
    return _row(ticker, earnings_date, 'alphavantage', **base)


def uw(ticker: str, earnings_date: date, **values) -> dict:
    base = dict(
        earnings_time='postmarket', company_name='Acme', market_cap=5e9,
        sector='Tech', has_options=True, expected_move=5.0,
        options_volume=20000, open_interest=50000, stock_volume=1_000_000,
    )
    base.update(values)
    return _row(ticker, earnings_date, 'unusual_whales', **base)


def yahoo(ticker: str, earnings_date: date, **values) -> dict:
    """A Yahoo row as the per-ticker calendar path writes it.

    ``company_name`` '' and ``earnings_time`` 'unknown'
    (``scripts/fetch_earnings_calendar.py`` ``_fetch_yahoo_one``: the
    calendar carries no BMO/AMC), ``market_cap`` None. ``'unknown'`` sorts
    above ``'premarket'`` and ``'postmarket'``, so a real Yahoo row can win a
    reader's ``MAX(earnings_time)``; the mixed-ticker controls rely on that.
    """
    base = dict(earnings_time='unknown', company_name='', market_cap=None)
    base.update(values)
    return _row(ticker, earnings_date, 'yahoo', **base)


def yahoo_bulk(ticker: str, earnings_date: date, **values) -> dict:
    """A Yahoo row as the bulk Calendars path writes it: a company name and a
    time bucket from ``_yahoo_time_from_row`` (never NULL)."""
    base = dict(earnings_time='premarket', company_name='Yahoo Co')
    base.update(values)
    return _row(ticker, earnings_date, 'yahoo', **base)


def hydrated(row: dict, volume: int = 30000, oi: int = 90000) -> dict:
    """The row after ``enrich_with_av_options`` broadcast a chain sum onto it."""
    return {**row, 'options_volume': volume, 'open_interest': oi}


def stale(row: dict) -> dict:
    """A row persisted by an earlier run and never deleted by the keyed upsert.

    The values are unchanged; the builder names the provenance in the test.
    """
    return dict(row)


def null_source(ticker: str, earnings_date: date, **values) -> dict:
    """NULL ``data_source``: a design control, not producer-reachable (the
    column is NOT NULL in ``gcp/schema.sql``; fixture only)."""
    return _row(ticker, earnings_date, None, **values)


def unknown_source(ticker: str, earnings_date: date, **values) -> dict:
    """``'unknown'`` ``data_source``: a design control, not reached by
    ``main()``. Only ``persist_to_cloud_sql``'s branch for a frame with no
    ``source`` column writes it, and every frame ``main()`` persists has one."""
    return _row(ticker, earnings_date, 'unknown', **values)


def ew_raw_alias(ticker: str, earnings_date: date, **values) -> dict:
    """The raw ``'EarningsWhispers'`` spelling (an unmapped historical frame)."""
    return ew_only(ticker, earnings_date, data_source='EarningsWhispers', **values)


def legacy_dates(ticker: str = 'LGCY') -> list[dict]:
    """EW rows dated 2026-04-13 .. 2026-09-26, one per week."""
    out, d = [], date(2026, 4, 13)
    while d <= date(2026, 9, 26):
        out.append(ew_only(ticker, d))
        d += timedelta(days=7)
    return out


def alias_control_rows(ticker_prefix: str, earnings_date: date) -> list[dict]:
    """One row per alias-control value, ticker ``<prefix><index>``."""
    return [
        _row(f"{ticker_prefix}{i}", earnings_date, src, company_name='Acme')
        for i, src in enumerate(ALIAS_CONTROL_VALUES)
    ]


# ── SQLite execution of a reader's own SQL ─────────────────────────────────

_REWRITES = (
    (re.compile(r"CURRENT_DATE\s*\+\s*\(:(\w+)\)::int", re.I),
     r"date(:__today, '+' || :\1 || ' days')"),
    (re.compile(r"\bCURRENT_DATE\b", re.I), ":__today"),
    (re.compile(r"CAST\(\s*:(\w+)\s+AS\s+date\s*\)\s*\+\s*INTERVAL\s+'(\d+) days'", re.I),
     r"date(:\1, '+\2 days')"),
    (re.compile(r"CAST\(\s*:(\w+)\s+AS\s+date\s*\)", re.I), r":\1"),
    (re.compile(r"\bBOOL_OR\(", re.I), "MAX("),
)
_UNTRANSLATED = re.compile(r"::|\bINTERVAL\b|\bANY\(|\bSTRING_AGG\b", re.I)
_DATE_COLUMNS = ('earnings_date', 'date')


def _sqlite_value(v):
    if isinstance(v, date):
        return v.isoformat()
    return v


def make_db(rows: list[dict], market_data: Optional[list[dict]] = None):
    """In-memory DB with ``earnings_calendar`` (data_source nullable) and
    ``market_data_daily`` (ticker, date, close)."""
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE earnings_calendar ({', '.join(COLUMNS)})")
    conn.execute("CREATE TABLE market_data_daily (ticker, date, close)")
    conn.executemany(
        f"INSERT INTO earnings_calendar VALUES ({', '.join('?' * len(COLUMNS))})",
        [tuple(_sqlite_value(r[c]) for c in COLUMNS) for r in rows],
    )
    conn.executemany(
        "INSERT INTO market_data_daily VALUES (?, ?, ?)",
        [(m['ticker'], _sqlite_value(m['date']), m['close'])
         for m in (market_data or [])],
    )
    return conn


def run_earnings_sql(conn, sql: str, params: Optional[dict] = None,
                     today: Optional[date] = None) -> pd.DataFrame:
    """Run a reader's PostgreSQL text in SQLite; date columns come back as
    ``datetime.date`` (as pg8000 returns them)."""
    params = {k: _sqlite_value(v) for k, v in (params or {}).items()}
    if today is not None:
        params['__today'] = today.isoformat()
    for pattern, repl in _REWRITES:
        sql = pattern.sub(repl, sql)

    def _expand(m):
        name = m.group(1)
        values = params.pop(name)
        names = [f"{name}_{i}" for i in range(len(values))]
        params.update({n: _sqlite_value(v) for n, v in zip(names, values)})
        return f"IN ({', '.join(':' + n for n in names)})"
    sql = re.sub(r"=\s*ANY\(:(\w+)\)", _expand, sql)
    leftover = _UNTRANSLATED.search(sql)
    if leftover:
        raise AssertionError(f"untranslated PostgreSQL construct {leftover.group(0)!r} in:\n{sql}")
    df = pd.read_sql_query(sql, conn, params=params)
    for col in _DATE_COLUMNS:
        if col in df.columns:
            df[col] = [date.fromisoformat(v) if isinstance(v, str) else v
                       for v in df[col]]
    return df
