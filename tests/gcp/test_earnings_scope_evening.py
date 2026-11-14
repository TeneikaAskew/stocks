"""The Sunday weekly scope of the history and reactions jobs (FEAT-DATA-001, stage 1).

`fetch-earnings-history` (19:15 ET) and `compute-earnings-reactions` (19:30 ET)
resolve ``weekly`` on Sundays from the weekday. Their containers' clock is UTC,
so in winter the host weekday at 19:15 EST is already Monday and both resolved
``daily``: the week-ahead fetch and recompute stopped when clocks changed on
2026-11-01. The weekday is the exchange's now.
"""
from __future__ import annotations

import pandas as pd
import pytest
import sqlalchemy

import gcp.database as database
import gcp.fetchers.compute_earnings_reactions as reactions
import gcp.fetchers.fetch_earnings_history as history
from lib.eastern_time import market_today_sql
from tests.fixtures.market_clock import DAYTIME, freeze_market_clock

SCOPES = [
    ("2026-11-09T00:00:30Z", "weekly"),  # Sunday 2026-11-08 19:00 EST
    ("2026-10-25T23:00:30Z", "weekly"),  # Sunday 2026-10-25 19:00 EDT
    ("2026-11-03T00:01:00Z", "daily"),   # Monday 2026-11-02 19:01 EST
    (DAYTIME, "daily"),
]


@pytest.mark.parametrize("module", [history, reactions], ids=["history", "reactions"])
@pytest.mark.parametrize("instant, want", SCOPES)
def test_the_history_and_reactions_scopes_read_the_exchange_weekday(monkeypatch, module, instant, want):
    monkeypatch.delenv("PIPELINE_SCOPE", raising=False)
    # stdlib=True: the unmodified functions import datetime inside themselves.
    freeze_market_clock(monkeypatch, instant, module, stdlib=True)
    assert module._resolve_scope(None) == want


def test_the_history_window_sql_reads_the_exchange_date(monkeypatch):
    issued: list[tuple[str, dict]] = []

    def recording(sql, params=None):
        issued.append((sql, params))
        return pd.DataFrame({"ticker": ["aaa"]})

    monkeypatch.setattr(database, "query_to_dataframe", recording)

    assert history._earnings_calendar_tickers(7) == ["AAA"]

    (sql, params), = issued
    assert sql.count(market_today_sql()) == 2
    assert "CURRENT_DATE" not in sql
    # The helper's text brings a :: cast; the statement keeps exactly the bind it had.
    assert set(sqlalchemy.text(sql)._bindparams) == {"days"}
    assert params == {"days": 7}
