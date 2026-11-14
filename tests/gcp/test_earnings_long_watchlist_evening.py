"""The Sunday watchlist is dated by the exchange (FEAT-DATA-001, stage 1).

`earnings-long-watchlist-sunday` runs at 19:45 America/New_York in a container
whose clock is UTC. In winter that is 00:45 UTC on Monday, so the post was
dated Monday, the source-age check counted from Monday, and the SQL window
(`CURRENT_DATE`, also UTC) ran Monday to Monday+7. The Python date and the SQL
date move together here so the two cannot disagree.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
import sqlalchemy

import gcp.earnings_long_watchlist as wl
from lib.eastern_time import market_today_sql
from tests.fixtures.market_clock import DAYTIME, freeze_market_clock


@pytest.mark.parametrize("instant, source, as_of", [
    # Sunday 2026-11-08 19:45 EST. The source is 14 days old from the exchange's
    # Sunday (fresh) and 15 from the host's Monday (stale: main() returned 1).
    ("2026-11-09T00:45:00Z", date(2026, 10, 25), date(2026, 11, 8)),
    # Sunday 2026-10-25 19:45 EDT: the host date agrees.
    ("2026-10-25T23:45:00Z", date(2026, 10, 11), date(2026, 10, 25)),
    (DAYTIME, date(2026, 10, 29), date(2026, 11, 12)),
])
def test_main_dates_the_post_and_the_source_age_from_the_exchange_date(monkeypatch, instant, source, as_of):
    freeze_market_clock(monkeypatch, instant, wl)
    built: list[date] = []

    def recording_message(df, as_of, days_ahead):
        built.append(as_of)
        return {}

    monkeypatch.setattr(wl, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(wl, "_latest_source_date", lambda: source)
    monkeypatch.setattr(wl, "_query_watchlist", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(wl, "build_discord_message", recording_message)

    assert wl.main(["--dry-run"]) == 0
    assert built == [as_of]


def test_the_watchlist_sql_reads_the_exchange_date(monkeypatch):
    issued: list[tuple[str, dict]] = []

    def recording(sql, params=None):
        issued.append((sql, params))
        return pd.DataFrame()

    monkeypatch.setattr(wl, "query_to_dataframe_strict", recording)

    wl._query_watchlist(7, 2)

    (sql, params), = issued
    assert sql.count(market_today_sql()) == 2
    assert "CURRENT_DATE" not in sql
    # The helper's text brings a :: cast; the statement keeps exactly the binds it had.
    assert set(sqlalchemy.text(sql)._bindparams) == {"days_ahead", "min_wins"}
    assert set(params) == {"days_ahead", "min_wins"}
