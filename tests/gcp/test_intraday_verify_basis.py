"""The basis check for stored 1-min bars (FEAT-DATA-001, Design C).

Until 2026-11-13 the 1-min requests returned prices adjusted as of the call,
so stored months sit on whatever basis their last fetch had. The check compares
a session's regular-hours high and low with the daily table's, which are as
traded, and says which sessions are not.

It never passes a session it could not measure: a session that is thin or
whose count depends on the timestamp convention is INCOMPLETE, a daily row the
bars themselves produced is UNMEASURED, and an as-traded reading that rests on
a row not proven a true instant is INFERRED.
"""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from gcp.fetchers import fetch_alphavantage_intraday as fai
from lib.eastern_time import session_schedule
from tests.fixtures.intraday_checks import NEW, OLD, session_bars, stored

DAY = "2025-05-01"
SCHEDULE = session_schedule(DAY, DAY)
DAILY_COLUMNS = ["date", "high", "low", "data_source"]


def daily(day, src="alphavantage_daily", high=600.0, low=590.0) -> pd.DataFrame:
    """A one-row market_data_daily frame for *day* (an ISO string, or the
    value the ``date`` column should hold)."""
    value = date.fromisoformat(day) if isinstance(day, str) else day
    return pd.DataFrame(
        [{"date": value, "high": high, "low": low, "data_source": src}],
        columns=DAILY_COLUMNS).astype({"date": object, "data_source": object})


def one(rows=None, daily_frame=None, *, inserted=NEW, **bars) -> dict:
    """The one record for DAY: whole proven bars against an as-traded daily
    row, unless a piece is given."""
    if rows is None:
        rows = stored(session_bars(DAY, **bars), inserted=inserted)
    if daily_frame is None:
        daily_frame = daily(DAY)
    (record,) = fai.session_basis_verdicts(rows, daily_frame, SCHEDULE)
    return record


def test_true_daily_sources():
    assert fai.TRUE_DAILY_SOURCES == (
        "alphavantage_daily", "av_daily_backfill", "av_watched_backfill")


@pytest.mark.parametrize("f_high,f_low,verdict,factor", [
    (0.99430, 0.99430, "ADJUSTED", 0.99430),
    (0.99969, 0.99969, "ADJUSTED", 0.99969),
    (0.99970, 0.99970, "AS-TRADED", 0.99970),
    (1.00030, 1.00030, "AS-TRADED", 1.00030),
    (1.00031, 1.00031, "ADJUSTED", 1.00031),
    (1.0, 0.99, "ODD", 0.99500),
    (0.99900, 1.00100, "ODD", 1.00000),
])
def test_the_measure(f_high, f_low, verdict, factor):
    record = one(f_high=f_high, f_low=f_low)
    assert record["session"] == date(2025, 5, 1)
    assert record["status"] == "OK"
    assert record["exact"] is True
    assert record["verdict"] == verdict
    assert record["reason"] is None
    assert record["f_high"] == f_high
    assert record["f_low"] == f_low
    assert record["factor"] == factor
    assert set(record) == {"session", "status", "exact", "verdict", "reason",
                           "f_high", "f_low", "factor"}


def test_a_daily_row_built_from_the_bars_is_not_a_measure():
    # The bars sit at 0.99430 of the traded price. The daily endpoint gave
    # nothing that night, so the daily row was built from these same bars:
    # against it they read exactly 1.0, whatever basis they are on.
    rows = stored(session_bars(DAY, f_high=0.99430, f_low=0.99430), inserted=NEW)
    rth = rows[(rows["bar"] >= f"{DAY} 09:30") & (rows["bar"] < f"{DAY} 16:00")]
    own = daily(DAY, src="alphavantage_1min",
                high=float(rth["high"].max()), low=float(rth["low"].min()))
    record = one(rows, own)
    assert record["verdict"] == "UNMEASURED"
    assert record["reason"] == "daily_from_intraday"
    assert record["f_high"] is None and record["f_low"] is None
    assert record["factor"] is None
    assert record["status"] == "OK"


@pytest.mark.parametrize("case,reason", [
    ("source-null", "daily_source_unknown"),
    ("source-yahoo", "daily_source_unknown"),
    ("no-daily-row", "no_daily_row"),
    ("high-null", "daily_not_positive"),
    ("low-zero", "daily_not_positive"),
    ("high-negative", "daily_not_positive"),
    ("bars-without-high-low", "no_rth_high_low"),
])
def test_unmeasured_reasons(case, reason):
    rows = stored(session_bars(DAY), inserted=NEW)
    daily_frame = {
        "source-null": lambda: daily(DAY, src=None),
        "source-yahoo": lambda: daily(DAY, src="yahoo"),
        "no-daily-row": lambda: pd.DataFrame(columns=DAILY_COLUMNS),
        "high-null": lambda: daily(DAY, high=None),
        "low-zero": lambda: daily(DAY, low=0.0),
        "high-negative": lambda: daily(DAY, high=-1.0),
        "bars-without-high-low": lambda: daily(DAY),
    }[case]()
    if case == "bars-without-high-low":
        rows = rows.assign(high=np.nan, low=np.nan)
    record = one(rows, daily_frame)
    assert record["verdict"] == "UNMEASURED"
    assert record["reason"] == reason
    assert record["f_high"] is None and record["f_low"] is None
    assert record["factor"] is None


def test_av_watched_backfill_is_measured():
    record = one(daily_frame=daily(DAY, src="av_watched_backfill"))
    assert record["verdict"] == "AS-TRADED"
    assert (record["f_high"], record["f_low"], record["factor"]) == (1.0, 1.0, 1.0)


def test_an_as_traded_session_on_rows_that_are_not_proven_is_inferred():
    record = one(inserted=OLD)
    assert record["verdict"] == "INFERRED"
    assert record["exact"] is False
    assert record["status"] == "OK"
    assert (record["f_high"], record["f_low"]) == (1.0, 1.0)


def test_a_session_that_is_not_ok_is_not_measured():
    record = one(start="09:30", end="13:29")
    assert record["verdict"] == "INCOMPLETE"
    assert record["status"] == "THIN"
    assert record["reason"] is None
    assert record["f_high"] is None and record["f_low"] is None
    assert record["factor"] is None
    # Whatever the daily row says: an unusable one does not change the answer.
    assert one(start="09:30", end="13:29",
               daily_frame=pd.DataFrame(columns=DAILY_COLUMNS))["verdict"] == "INCOMPLETE"


@pytest.mark.parametrize("value", [pd.Timestamp("2025-05-01"), datetime(2025, 5, 1)],
                         ids=["timestamp", "datetime"])
def test_daily_date_as_a_timestamp_still_matches(value):
    # pandas hands a DATE column back as Timestamps; the session must still
    # find its daily row.
    record = one(daily_frame=daily(value))
    assert record["verdict"] == "AS-TRADED"
    assert record["reason"] is None

    as_column = pd.DataFrame({"date": pd.to_datetime([value]), "high": [600.0],
                              "low": [590.0], "data_source": ["alphavantage_daily"]})
    assert one(daily_frame=as_column)["verdict"] == "AS-TRADED"
