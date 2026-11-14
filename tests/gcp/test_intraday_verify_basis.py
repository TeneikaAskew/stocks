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

import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from gcp.fetchers import fetch_alphavantage_intraday as fai
from lib.eastern_time import intraday_month_window, session_schedule, sessions_between
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


# -- --verify-basis ------------------------------------------------------------

Q3 = ("SELECT ts, high, low, volume, inserted_at FROM market_data_intraday "
      "WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end")
Q4 = ("SELECT date, high, low, data_source FROM market_data_daily "
      "WHERE ticker = :t AND date >= :first AND date <= :last")
BARS_COLUMNS = ["ts", "high", "low", "volume", "inserted_at"]
SUMMARY = "verify-basis summary:"
AT_NOW = datetime(2026, 11, 13, 15, tzinfo=timezone.utc)
AS_TRADED = ({}, NEW)


def _run(monkeypatch, tmp_path, list_text, bars, daily_frames, now=AT_NOW):
    """run_verify_basis over a recording strict reader.

    *bars* maps (ticker, year, month) to that month window's frame and
    *daily_frames* maps a ticker to its daily frame; an exception in place of
    a frame is raised by the reader.
    """
    path = tmp_path / "l.csv"
    path.write_text(list_text)
    calls: list[dict] = []

    def strict(sql, params=None, timeout_s=None):
        calls.append({"sql": sql, "params": params, "timeout_s": timeout_s})
        if "market_data_daily" in sql:
            answer = daily_frames[params["t"]]
        else:
            answer = bars.get(
                (params["t"], params["start"].year, params["start"].month),
                pd.DataFrame(columns=BARS_COLUMNS))
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(fai, "query_to_dataframe_strict", strict)
    return fai.run_verify_basis(str(path), now), calls


def month(year, mon, per_day, how="true", shared="true"):
    """(bars, daily) for every session of a month. ``per_day(d)`` gives
    ``(session_bars keywords, inserted_at)`` for the ISO session date *d*;
    the daily frame holds one alphavantage_daily row of 600.0 / 590.0 each."""
    last = (date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)) - timedelta(days=1)
    days = [d.isoformat() for d in sessions_between(date(year, mon, 1), last)]
    parts = []
    for d in days:
        kw, inserted = per_day(d)
        parts.append(stored(session_bars(d, **kw), how, shared=shared, inserted=inserted))
    bars = pd.concat(parts, ignore_index=True)
    daily_frame = pd.concat([daily(d) for d in days], ignore_index=True)
    return bars, daily_frame


def _lines(capsys) -> list[str]:
    return capsys.readouterr().out.splitlines()


def test_reads_one_bars_query_per_month_and_one_daily_query_per_ticker(
        monkeypatch, tmp_path, capsys):
    april, daily_april = month(2025, 4, lambda d: AS_TRADED)
    may, daily_may = month(2025, 5, lambda d: AS_TRADED)
    code, calls = _run(
        monkeypatch, tmp_path, "SPY,2025-04\nSPY,2025-05\n",
        {("SPY", 2025, 4): april, ("SPY", 2025, 5): may},
        {"SPY": pd.concat([daily_april, daily_may], ignore_index=True)})
    assert code == 0
    assert len(calls) == 3

    (daily_call,) = [c for c in calls if "market_data_daily" in c["sql"]]
    assert " ".join(daily_call["sql"].split()) == Q4
    assert daily_call["params"] == {
        "t": "SPY", "first": date(2025, 4, 1), "last": date(2025, 5, 31)}

    bar_calls = [c for c in calls if "market_data_daily" not in c["sql"]]
    assert [(c["params"]["start"], c["params"]["end"]) for c in bar_calls] == [
        intraday_month_window(2025, 4), intraday_month_window(2025, 5)]
    for call in bar_calls:
        assert " ".join(call["sql"].split()) == Q3
        assert "interval = '1min'" in call["sql"]
        assert call["params"]["t"] == "SPY"
    assert all(c["timeout_s"] == 120 for c in calls)

    lines = _lines(capsys)
    assert lines == [f"{SUMMARY} months=2 as_traded=42 inferred=0 adjusted=0 odd=0 "
                     "unmeasured=0 incomplete=0 empty=0"]


def test_a_month_on_two_bases_is_one_line(monkeypatch, tmp_path, capsys):
    def june(d):
        f = 0.99430 if d < "2025-06-20" else 0.99725
        return {"f_high": f, "f_low": f}, OLD

    bars, daily_frame = month(2025, 6, june)
    code, _ = _run(monkeypatch, tmp_path, "SPY,2025-06\n",
                   {("SPY", 2025, 6): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert ("BASIS-FAIL SPY 2025-06 sessions=20 2025-06-02..2025-06-30 "
            "factor=0.99430..0.99725 inferred=20") in lines
    assert len([ln for ln in lines if ln.startswith("BASIS-FAIL")]) == 1
    assert lines[-1].startswith(SUMMARY)
    assert code == 1


def test_one_adjusted_session_fails_its_month(monkeypatch, tmp_path, capsys):
    def straddle(d):
        f = 0.99430 if d in ("2025-04-30", "2025-05-01") else 1.0
        return {"f_high": f, "f_low": f}, NEW

    april, daily_april = month(2025, 4, straddle)
    may, daily_may = month(2025, 5, straddle)
    code, _ = _run(
        monkeypatch, tmp_path, "SPY,2025-04\nSPY,2025-05\n",
        {("SPY", 2025, 4): april, ("SPY", 2025, 5): may},
        {"SPY": pd.concat([daily_april, daily_may], ignore_index=True)})
    lines = _lines(capsys)
    assert ("BASIS-FAIL SPY 2025-04 sessions=1 2025-04-30..2025-04-30 "
            "factor=0.99430..0.99430 inferred=0") in lines
    assert ("BASIS-FAIL SPY 2025-05 sessions=1 2025-05-01..2025-05-01 "
            "factor=0.99430..0.99430 inferred=0") in lines
    assert code == 1


def _mixed_may():
    """May 2025, every row proven: as traded, except a THIN session (05-12),
    an ODD one (05-13), one with no daily row (05-14) and one whose daily row
    was built from the 1-min bars (05-15)."""
    def per_day(d):
        if d == "2025-05-12":
            return {"start": "09:30", "end": "13:29"}, NEW
        if d == "2025-05-13":
            return {"f_low": 0.99}, NEW
        return AS_TRADED

    bars, daily_frame = month(2025, 5, per_day)
    daily_frame = daily_frame[daily_frame["date"] != date(2025, 5, 14)].reset_index(drop=True)
    daily_frame.loc[daily_frame["date"] == date(2025, 5, 15), "data_source"] = "alphavantage_1min"
    return bars, daily_frame


_MIXED_LINES = [
    "UNMEASURED SPY 2025-05 sessions=2 2025-05-14..2025-05-15 no_daily_row=1 "
    "daily_from_intraday=1 daily_source_unknown=0 daily_not_positive=0 no_rth_high_low=0",
    "INCOMPLETE SPY 2025-05 sessions=1 2025-05-12..2025-05-12 inexact=0",
    "ODD SPY 2025-05-13 high=1.00000 low=0.99000 exact=yes",
]


def test_a_proven_month_with_unmeasured_incomplete_and_odd_sessions_exits_0(
        monkeypatch, tmp_path, capsys):
    bars, daily_frame = _mixed_may()
    code, _ = _run(monkeypatch, tmp_path, "SPY,2025-05\n",
                   {("SPY", 2025, 5): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert lines[:-1] == _MIXED_LINES
    assert not [ln for ln in lines if ln.startswith(("BASIS-FAIL", "INFERRED"))]
    assert lines[-1] == (f"{SUMMARY} months=1 as_traded=17 inferred=0 adjusted=0 odd=1 "
                         "unmeasured=2 incomplete=1 empty=0")
    assert code == 0


def test_one_row_that_is_not_proven_makes_it_inferred_and_exit_3(
        monkeypatch, tmp_path, capsys):
    bars, daily_frame = _mixed_may()
    one_bar = bars["bar"] == pd.Timestamp("2025-05-16 10:00")
    assert int(one_bar.sum()) == 1
    bars.loc[one_bar, "inserted_at"] = OLD
    code, _ = _run(monkeypatch, tmp_path, "SPY,2025-05\n",
                   {("SPY", 2025, 5): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    for line in _MIXED_LINES:
        assert line in lines
    assert "INFERRED SPY 2025-05 sessions=1 2025-05-16..2025-05-16" in lines
    assert not [ln for ln in lines if ln.startswith("BASIS-FAIL")]
    assert lines[-1].startswith(SUMMARY)
    assert code == 3


def test_thin_sessions_that_are_not_proven_are_incomplete_not_a_basis(
        monkeypatch, tmp_path, capsys):
    # The first twelve sessions hold 12:00 to 15:59 only: they lack 10:17 and
    # 11:42, the minutes that hold the daily high and low.
    def per_day(d):
        return ({"start": "12:00", "end": "15:59"} if d <= "2025-05-16" else {}), OLD

    bars, daily_frame = month(2025, 5, per_day)
    code, _ = _run(monkeypatch, tmp_path, "SPY,2025-05\n",
                   {("SPY", 2025, 5): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert "INCOMPLETE SPY 2025-05 sessions=12 2025-05-01..2025-05-16 inexact=12" in lines
    assert "INFERRED SPY 2025-05 sessions=9 2025-05-19..2025-05-30" in lines
    assert not [ln for ln in lines if ln.startswith("BASIS-FAIL")]
    assert code == 3


@pytest.mark.parametrize("how,shared", [
    ("true", "true"), ("label", "true"), ("both", "true"), ("both", "label")])
def test_the_three_storages_print_the_same_lines(monkeypatch, tmp_path, capsys, how, shared):
    bars, daily_frame = month(2025, 5, lambda d: ({}, OLD), how, shared)
    code, _ = _run(monkeypatch, tmp_path, "SPY,2025-05\n",
                   {("SPY", 2025, 5): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert lines[:-1] == ["INFERRED SPY 2025-05 sessions=21 2025-05-01..2025-05-30"]
    assert lines[-1].startswith(SUMMARY)
    assert code == 3

    bars, daily_frame = month(
        2025, 5, lambda d: ({"f_high": 0.99430, "f_low": 0.99430}, OLD), how, shared)
    code, _ = _run(monkeypatch, tmp_path, "SPY,2025-05\n",
                   {("SPY", 2025, 5): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert lines[:-1] == ["BASIS-FAIL SPY 2025-05 sessions=21 2025-05-01..2025-05-30 "
                          "factor=0.99430..0.99430 inferred=21"]
    assert code == 1


def test_an_empty_month_and_an_empty_list(monkeypatch, tmp_path, capsys):
    _, daily_frame = month(2025, 5, lambda d: AS_TRADED)
    code, calls = _run(monkeypatch, tmp_path, "SPY,2025-05\n", {}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert lines[:-1] == ["EMPTY SPY 2025-05"]
    assert lines[-1] == (f"{SUMMARY} months=1 as_traded=0 inferred=0 adjusted=0 odd=0 "
                         "unmeasured=0 incomplete=0 empty=1")
    assert code == 1

    for text in ("", "ticker,month\n", "# only a comment\n"):
        code, calls = _run(monkeypatch, tmp_path, text, {}, {})
        assert code == 1
        assert calls == []
        assert SUMMARY not in capsys.readouterr().out


def test_another_ticker_exits_1_before_any_query(monkeypatch, tmp_path, capsys):
    code, calls = _run(monkeypatch, tmp_path, "SPY,2025-05\nAMD,2025-05\n", {}, {})
    assert code == 1
    assert calls == []
    assert SUMMARY not in capsys.readouterr().out


def test_reader_errors_propagate(monkeypatch, tmp_path, capsys):
    bars, daily_frame = month(2025, 5, lambda d: AS_TRADED)
    with pytest.raises(ConnectionError, match="connection refused"):
        _run(monkeypatch, tmp_path, "SPY,2025-05\n",
             {("SPY", 2025, 5): ConnectionError("connection refused")},
             {"SPY": daily_frame})
    assert SUMMARY not in capsys.readouterr().out

    with pytest.raises(KeyError, match="high"):
        _run(monkeypatch, tmp_path, "SPY,2025-05\n",
             {("SPY", 2025, 5): bars}, {"SPY": KeyError("high")})
    assert SUMMARY not in capsys.readouterr().out


@pytest.mark.parametrize("other", ["--verify-months", "--replace-months"])
def test_verify_basis_with_another_list_mode_is_a_usage_error(monkeypatch, capsys, other):
    calls: list = []
    monkeypatch.setattr(fai, "query_to_dataframe_strict",
                        lambda *a, **k: calls.append(a))
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday.py",
                                      "--verify-basis", "x", other, "y"])
    with pytest.raises(SystemExit) as exc:
        fai.main()
    assert exc.value.code == 2
    assert calls == []


def test_main_dispatches_verify_basis(monkeypatch):
    seen: list = []

    def fake(path):
        seen.append(path)
        return 3

    monkeypatch.setattr(fai, "run_verify_basis", fake)
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday.py",
                                      "--verify-basis", "gs://bucket/list.csv"])
    with pytest.raises(SystemExit) as exc:
        fai.main()
    assert exc.value.code == 3
    assert seen == ["gs://bucket/list.csv"]


def test_sessions_whose_close_has_not_passed_are_not_read(monkeypatch, tmp_path, capsys):
    # 2026-11-13 15:00 UTC: that day's session is open. Rows stop at 11-12
    # (proven by their date); the daily frame covers the whole month.
    settled = [d.isoformat() for d in sessions_between("2026-11-01", "2026-11-12")]
    bars = pd.concat([stored(session_bars(d), inserted=OLD) for d in settled],
                     ignore_index=True)
    all_days = [d.isoformat() for d in sessions_between("2026-11-01", "2026-11-30")]
    daily_frame = pd.concat([daily(d) for d in all_days], ignore_index=True)
    code, _ = _run(monkeypatch, tmp_path, "SPY,2026-11\n",
                   {("SPY", 2026, 11): bars}, {"SPY": daily_frame})
    lines = _lines(capsys)
    assert lines == [f"{SUMMARY} months=1 as_traded=9 inferred=0 adjusted=0 odd=0 "
                     "unmeasured=0 incomplete=0 empty=0"]
    assert code == 0
