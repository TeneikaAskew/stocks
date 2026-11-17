"""Reading a stored 1-min session without trusting an inferred convention.

``lib.eastern_time.session_minute_readings`` counts a session's regular-hours
minutes three ways (every row a true instant; unproven rows as Eastern labels;
unproven rows only where both readings agree) and gives one status only when
the three agree. A row is proven a true instant by its date or by its insert
time, never by the shape of its date's rows (FEAT-DATA-001, Design F).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

import lib.eastern_time as et
from gcp.fetchers import fetch_alphavantage_intraday as fai
from lib.eastern_time import (
    TRUE_UTC_INSERTED_FROM,
    SessionReading,
    intraday_month_window,
    place_stored_rows,
    proven_true_utc,
    session_minute_readings,
    session_schedule,
    stored_intraday_to_eastern,
    utc_to_eastern_naive,
)
from tests.fixtures.intraday_checks import (
    NEW,
    OLD,
    et_minutes,
    session_bars,
    store,
    stored,
)


def read(ts, day, inserted=OLD) -> SessionReading:
    return session_minute_readings(
        ts, pd.Series([inserted] * len(ts)), session_schedule(day, day))[0]


def _from_open(day: str, minutes: int) -> pd.DatetimeIndex:
    """*minutes* naive Eastern minutes of *day*, starting at 09:30."""
    return pd.date_range(f"{day} 09:30", periods=minutes, freq="min")


_MAY = "2025-05-01"
_TABLE = [
    # rows, storage, inserted, (true_utc, eastern_label, both, expected), status, exact
    (et_minutes(_MAY, "09:30", "13:29"), "true", OLD, (240, 150, 0, 390), "UNDETERMINED", False),
    (et_minutes(_MAY, "09:30", "13:29"), "label", OLD, (0, 240, 0, 390), "UNDETERMINED", False),
    (et_minutes(_MAY, "09:30", "13:29"), "both", OLD, (240, 390, 240, 390), "UNDETERMINED", False),
    (et_minutes(_MAY, "09:30", "13:29"), "true", NEW, (240, 240, 240, 390), "THIN", True),
    (et_minutes(_MAY, "04:00", "13:29"), "true", OLD, (240, 390, 240, 390), "UNDETERMINED", False),
    (et_minutes(_MAY, "04:00", "20:00"), "true", OLD, (390, 390, 390, 390), "OK", False),
    (et_minutes(_MAY, "04:00", "20:00"), "label", OLD, (390, 390, 390, 390), "OK", False),
    (et_minutes(_MAY, "04:00", "20:00"), "both", OLD, (390, 390, 390, 390), "OK", False),
    (et_minutes("2025-01-15", "04:00", "20:00"), "label", OLD,
     (331, 390, 331, 390), "UNDETERMINED", False),
    (pd.DatetimeIndex([]), "true", OLD, (0, 0, 0, 390), "MISSING", True),
    (_from_open("2026-10-01", 351), "true", OLD, (351, 351, 351, 390), "OK", True),
    (_from_open("2026-10-01", 350), "true", OLD, (350, 350, 350, 390), "THIN", True),
    (_from_open("2025-11-28", 189), "true", NEW, (189, 189, 189, 210), "OK", True),
    (_from_open("2025-11-28", 188), "true", NEW, (188, 188, 188, 210), "THIN", True),
]
_DAYS = [_MAY] * 8 + ["2025-01-15", _MAY, "2026-10-01", "2026-10-01",
                      "2025-11-28", "2025-11-28"]
_IDS = [
    "240-true", "240-label", "240-both", "240-true-proven", "cut-at-1330-true",
    "whole-true", "whole-label", "whole-both", "winter-whole-label", "no-row",
    "351-of-390", "350-of-390", "189-of-210", "188-of-210",
]


@pytest.mark.parametrize(
    "day,rows,how,inserted,counts,status,exact",
    [(d, *row) for d, row in zip(_DAYS, _TABLE)], ids=_IDS)
def test_session_minute_readings_table(day, rows, how, inserted, counts, status, exact):
    r = read(store(rows, how), day, inserted)
    assert r.session == date.fromisoformat(day)
    assert (r.true_utc, r.eastern_label, r.both, r.expected) == counts
    assert r.status == status
    assert r.exact is exact


def test_session_minute_readings_reads_no_calendar(monkeypatch):
    def no_calendar(*a, **k):
        raise AssertionError("session_minute_readings must not read the calendar")

    monkeypatch.setattr(et, "_sessions_covering", no_calendar)
    schedule = pd.DataFrame(
        {"market_open": [pd.Timestamp("2025-05-01 13:30+00:00")],
         "market_close": [pd.Timestamp("2025-05-01 20:00+00:00")]},
        index=pd.DatetimeIndex([pd.Timestamp("2025-05-01")]))
    ts = store(et_minutes(_MAY, "09:30", "13:29"), "true")
    readings = session_minute_readings(ts, pd.Series([OLD] * len(ts)), schedule)
    assert len(readings) == 1
    r = readings[0]
    assert (r.true_utc, r.eastern_label, r.both, r.expected) == (240, 150, 0, 390)
    assert r.session == date(2025, 5, 1)

    # Two sessions, handed over newest first: the readings keep that order.
    two = pd.DataFrame(
        {"market_open": [pd.Timestamp("2025-05-02 13:30+00:00"),
                         pd.Timestamp("2025-05-01 13:30+00:00")],
         "market_close": [pd.Timestamp("2025-05-02 20:00+00:00"),
                          pd.Timestamp("2025-05-01 20:00+00:00")]},
        index=pd.DatetimeIndex([pd.Timestamp("2025-05-02"), pd.Timestamp("2025-05-01")]))
    readings = session_minute_readings(ts, pd.Series([NEW] * len(ts)), two)
    assert [r.session for r in readings] == [date(2025, 5, 2), date(2025, 5, 1)]
    assert [r.status for r in readings] == ["MISSING", "THIN"]
    assert [r.true_utc for r in readings] == [0, 240]


def test_proven_rule():
    assert TRUE_UTC_INSERTED_FROM == datetime(2026, 9, 28, tzinfo=timezone.utc)
    ts = pd.DatetimeIndex([
        pd.Timestamp("2025-05-01 13:30", tz="UTC"),
        pd.Timestamp("2025-05-01 13:31", tz="UTC"),
        pd.Timestamp("2026-09-28 00:00", tz="UTC"),
        pd.Timestamp("2026-09-27 23:59", tz="UTC"),
    ])
    inserted = pd.Series([
        pd.NaT,
        pd.Timestamp("2026-09-28 00:00:00", tz="UTC"),
        OLD,
        pd.Timestamp("2026-09-27 23:59:59", tz="UTC"),
    ])
    assert proven_true_utc(ts, inserted).tolist() == [False, True, True, False]

    # A naive value is UTC, as stored_intraday_to_eastern reads ts.
    naive = proven_true_utc(
        pd.Series([pd.Timestamp("2025-05-01 13:30")]),
        pd.Series([pd.Timestamp("2026-11-20 12:00")]))
    assert naive.tolist() == [True]


def test_two_rows_in_one_minute_count_once():
    ts = pd.DatetimeIndex([
        pd.Timestamp("2025-05-01 13:30:00", tz="UTC"),
        pd.Timestamp("2025-05-01 13:30:30", tz="UTC"),
    ])
    assert read(ts, _MAY).true_utc == 1


def test_intraday_month_window():
    assert intraday_month_window(2025, 12) == (
        datetime(2025, 12, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 2, tzinfo=timezone.utc))
    assert fai.month_replace_window(2025, 12) == intraday_month_window(2025, 12)
    assert fai.month_replace_window(2026, 3) == intraday_month_window(2026, 3)
    assert intraday_month_window(2026, 3) == (
        datetime(2026, 3, 1, 2, tzinfo=timezone.utc),
        datetime(2026, 4, 1, 2, tzinfo=timezone.utc))


# -- place_stored_rows ---------------------------------------------------------

_OPEN = pd.Timestamp("2025-05-01 13:30", tz="UTC")
_CLOSE = pd.Timestamp("2025-05-01 20:00", tz="UTC")


def _place(rows: pd.DataFrame):
    return place_stored_rows(rows["ts"], rows["volume"], rows["inserted_at"])


def _rth(instants, keep):
    return keep & np.asarray((instants >= _OPEN) & (instants < _CLOSE))


def _with_row(rows: pd.DataFrame, ts: str, inserted) -> pd.DataFrame:
    """*rows* plus one flat-volume row stored at *ts* (UTC), appended last."""
    extra = pd.DataFrame({
        "bar": [pd.NaT], "high": [595.0], "low": [595.0], "volume": [1000],
        "ts": [pd.Timestamp(ts, tz="UTC")], "inserted_at": [inserted]})
    return pd.concat([rows, extra], ignore_index=True)


_PLACE_CASES = [
    "proven-keeps-its-stored-instant",
    "not-proven-follows-the-resolver",
    "one-minute-neither-proven",
    "one-minute-one-proven",
    "spiked-true", "spiked-label", "spiked-both-true-shared", "spiked-both-label-shared",
    "the-named-limit",
]


@pytest.mark.parametrize("case", _PLACE_CASES)
def test_place_stored_rows(case):
    labels_old = stored(session_bars(_MAY), "label", inserted=OLD)
    sixteen_thirty = pd.Timestamp("2025-05-01 16:30", tz="UTC")
    twenty_thirty = pd.Timestamp("2025-05-01 20:30", tz="UTC")

    if case == "proven-keeps-its-stored-instant":
        rows = stored(session_bars(_MAY), "label", inserted=NEW)
        assert len(rows) == 961
        wall, _ = stored_intraday_to_eastern(rows["ts"], rows["volume"])
        # The resolver reads every one of these rows as a label ...
        assert (wall == pd.DatetimeIndex(rows["bar"])).all()
        instants, keep, proven = _place(rows)
        # ... and a proven row is not moved by it.
        assert instants.equals(pd.DatetimeIndex(rows["ts"]))
        assert str(instants.tz) == "UTC"
        assert keep.all() and proven.all()

    elif case == "not-proven-follows-the-resolver":
        wall, resolver_keep = stored_intraday_to_eastern(
            labels_old["ts"], labels_old["volume"])
        instants, keep, proven = _place(labels_old)
        assert utc_to_eastern_naive(instants).equals(wall)
        assert (keep == resolver_keep).all()
        assert not proven.any()

    elif case == "one-minute-neither-proven":
        rows = _with_row(labels_old, "2025-05-01 20:30", OLD)
        _, resolver_keep = stored_intraday_to_eastern(rows["ts"], rows["volume"])
        instants, keep, proven = _place(rows)
        label_row = int(np.flatnonzero(rows["ts"] == sixteen_thirty)[0])
        added = len(rows) - 1
        assert instants[label_row] == twenty_thirty
        assert instants[added] == twenty_thirty
        assert np.flatnonzero(~keep).tolist() == [added]
        assert np.flatnonzero(~resolver_keep).tolist() == [added]

    elif case == "one-minute-one-proven":
        rows = _with_row(labels_old, "2025-05-01 20:30", NEW)
        instants, keep, proven = _place(rows)
        label_row = int(np.flatnonzero(rows["ts"] == sixteen_thirty)[0])
        added = len(rows) - 1
        assert instants[label_row] == twenty_thirty
        assert instants[added] == twenty_thirty
        assert proven[added] and not proven[label_row]
        assert np.flatnonzero(~keep).tolist() == [label_row]

    elif case.startswith("spiked-"):
        how, shared = {
            "spiked-true": ("true", "true"),
            "spiked-label": ("label", "true"),
            "spiked-both-true-shared": ("both", "true"),
            "spiked-both-label-shared": ("both", "label"),
        }[case]
        rows = stored(session_bars(_MAY), how, shared=shared, inserted=OLD)
        instants, keep, proven = _place(rows)
        rth = _rth(instants, keep)
        assert int(rth.sum()) == 390
        assert utc_to_eastern_naive(instants[rth]).equals(
            pd.DatetimeIndex(rows["bar"][rth]))
        assert rows["high"][rth].max() == 600.0
        assert rows["low"][rth].min() == 590.0

    else:
        # Design F's named limit: a whole session with flat volume, stored both
        # ways with the label copy on the shared keys, and no row proven. The
        # count is right and every regular-hours row is on the wrong minute.
        rows = stored(session_bars(_MAY, spike=False), "both", shared="label",
                      inserted=OLD)
        instants, keep, proven = _place(rows)
        rth = _rth(instants, keep)
        assert int(rth.sum()) == 390
        own = utc_to_eastern_naive(instants[rth]) == pd.DatetimeIndex(rows["bar"][rth])
        assert not own.any()
        assert not proven[rth].any()
        assert 600.0 not in set(rows["high"][rth])
        assert 590.0 not in set(rows["low"][rth])
