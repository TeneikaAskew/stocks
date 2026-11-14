"""The freshness audit's 1-min session scan (FEAT-DATA-001, Design B).

The watchdog used to ask of ``market_data_intraday`` only whether a UTC day
held any row, through a reader that turns a database error into an empty
frame. These tests pin the scan that replaces it for this table: it counts each
settled session's regular-hours minutes, reports a session that is missing or
thin, and lets a failed read fail the run instead of reading as a gap.
"""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone

import pandas as pd
import pytest

import scripts.audit_data_freshness as mod
from lib.eastern_time import SessionReading, intraday_month_window, sessions_between
from tests.fixtures.intraday_checks import (
    OLD,
    et_minutes,
    install_audit_readers,
    rth_frame,
    store,
)

NOW = datetime(2026, 11, 13, 15, 0)
FIVE = ("2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11")
whole = {d: 390 for d in FIVE}

SESSIONS = "market_data_intraday [sessions]"
Q1 = ("SELECT ts, inserted_at FROM market_data_intraday WHERE ticker = :t "
      "AND interval = '1min' AND ts >= :start AND ts < :end")


@pytest.fixture(autouse=True)
def _restore_database_log_level():
    """main() raises the gcp.database logger's level; put it back."""
    logger = logging.getLogger("gcp.database")
    level = logger.level
    yield
    logger.setLevel(level)


def _check() -> dict:
    return next(c for c in mod.CHECKS if c["name"] == "market_data_intraday")


def _spy(counts: dict):
    """A scan reader: SPY holds *counts*, the other tickers are whole."""
    return lambda t: rth_frame(counts if t == "SPY" else whole)


def _audit(monkeypatch, scan, now=NOW):
    calls = install_audit_readers(monkeypatch, mod, scan)
    return mod.audit_all(now), calls


def _main(monkeypatch, argv, scan) -> int:
    install_audit_readers(monkeypatch, mod, scan)
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    real = mod.audit_all
    monkeypatch.setattr(mod, "audit_all", lambda: real(NOW))
    monkeypatch.setattr(sys, "argv", argv)
    try:
        mod.main()
    except SystemExit as exc:
        return 0 if exc.code is None else exc.code
    return 0


def _session_rows(report) -> list:
    return [r for r in report.rows if r.table == SESSIONS]


def test_scan_reads_five_settled_sessions_with_one_strict_query_per_ticker(monkeypatch):
    report, calls = _audit(monkeypatch, lambda t: rth_frame(whole))

    scans = [c for c in calls if "inserted_at" in c["sql"]]
    assert [c["params"]["t"] for c in scans] == ["IWM", "SPY", "QQQ"]
    for call in scans:
        assert " ".join(call["sql"].split()) == Q1
        assert "interval = '1min'" in call["sql"]
        assert "DATE(" not in call["sql"] and "::date" not in call["sql"]
        assert call["params"] == {
            "t": call["params"]["t"],
            "start": datetime(2026, 11, 5, 2, tzinfo=timezone.utc),
            "end": datetime(2026, 11, 12, 2, tzinfo=timezone.utc),
        }
        assert call["timeout_s"] == 120

    assert not [r for r in report.rows if "[sessions]" in r.table]
    # The stubbed day-presence reader holds no day for this table (see
    # install_audit_readers), so the old gap scan, if it still ran here,
    # would add a [gap] row for each ticker.
    assert not [r for r in report.rows if "market_data_intraday [gap]" in r.table]
    assert report.overall_status == "ok"

    check = _check()
    assert check["session_gap_days"] == 5
    assert "gap_scan_days" not in check
    assert check["settle_hour_et"] == 21
    assert check["settle_lag_days"] == 1
    assert check["min_rows_per_day"] == 350


def test_missing_thin_and_whole_sessions(monkeypatch):
    absent = {d: 390 for d in FIVE if d != "2026-11-09"}
    report, _ = _audit(monkeypatch, _spy(absent))
    (row,) = _session_rows(report)
    assert row.table == "market_data_intraday [sessions]"
    assert row.ticker == "SPY"
    assert row.status == "stale"
    assert row.expected_latest == "2026-11-09"
    assert row.row_count_recent == 0
    assert row.detail == "MISSING: 0 of 390 regular-hours minutes"
    assert row.writer_job == "fetch-alphavantage-intraday"
    assert row.expected_max_hours == 30
    assert row.last_row_at is None and row.lag_hours is None

    report, _ = _audit(monkeypatch, _spy({**whole, "2026-11-09": 240}))
    (row,) = _session_rows(report)
    assert row.detail == "THIN: 240 of 390 regular-hours minutes"
    assert row.row_count_recent == 240
    assert (row.ticker, row.expected_latest) == ("SPY", "2026-11-09")

    report, _ = _audit(monkeypatch, _spy({**whole, "2026-11-09": 30}))
    (row,) = _session_rows(report)
    assert row.detail == "THIN: 30 of 390 regular-hours minutes"

    report, _ = _audit(monkeypatch, _spy({**whole, "2026-11-09": 351}))
    assert _session_rows(report) == []

    report, _ = _audit(monkeypatch, _spy({d: 240 for d in FIVE}))
    rows = _session_rows(report)
    assert [r.ticker for r in rows] == ["SPY"] * 5
    assert sorted(r.expected_latest for r in rows) == sorted(FIVE)

    # The query ran and returned no row: five MISSING sessions, which is true.
    report, _ = _audit(monkeypatch, _spy({}))
    rows = _session_rows(report)
    assert len(rows) == 5
    assert {r.detail for r in rows} == {"MISSING: 0 of 390 regular-hours minutes"}
    assert {r.ticker for r in rows} == {"SPY"}


def test_reader_errors_propagate_out_of_audit_all(monkeypatch):
    with pytest.raises(ConnectionError, match="connection refused"):
        _audit(monkeypatch, ConnectionError("connection refused"))
    with pytest.raises(KeyError, match="inserted_at"):
        _audit(monkeypatch, KeyError("inserted_at"))


def test_a_defect_in_the_readings_is_not_a_calendar_failure(monkeypatch):
    def broken(*_a, **_k):
        raise KeyError("inserted_at")

    monkeypatch.setattr(mod, "session_minute_readings", broken)
    with pytest.raises(KeyError, match="inserted_at"):
        _audit(monkeypatch, lambda t: rth_frame(whole))


def _schedule_failing_for_the_scan(monkeypatch) -> list[tuple]:
    """Make the session scan's own schedule read fail, and no other.

    The audit reads ``session_schedule`` in two places: the scan asks for the
    range from its oldest session to its newest, and ``_session_rth_fraction``
    asks for one day at a time. A stub that raised for both would let the
    second produce the calendar row with the scan removed. This one raises
    only for a range, answers a single day for real, and returns the list its
    calls are recorded in.
    """
    real = mod.session_schedule
    asked: list[tuple] = []

    def schedule(first, last):
        asked.append((first, last))
        if first != last:
            raise RuntimeError("boom")
        return real(first, last)

    monkeypatch.setattr(mod, "session_schedule", schedule)
    return asked


def test_a_calendar_error_from_the_schedule_is_the_one_calendar_row(monkeypatch):
    asked = _schedule_failing_for_the_scan(monkeypatch)
    report, calls = _audit(monkeypatch, lambda t: rth_frame(whole))

    # The scan asked the calendar for its five sessions, through _calendar ...
    assert (date(2026, 11, 5), date(2026, 11, 11)) in asked
    # ... and that failure, which no other check met, is the one calendar row.
    calendar_rows = [r for r in report.rows if r.table == "nyse_calendar"]
    assert len(calendar_rows) == 1
    assert calendar_rows[0].status == "unknown"
    assert "RuntimeError: boom" in calendar_rows[0].detail
    assert _session_rows(report) == []
    # It failed before any read of the bars.
    assert not [c for c in calls if "inserted_at" in c["sql"]]

    asked.clear()
    assert _main(monkeypatch, ["audit_data_freshness.py", "--strict"],
                 lambda t: rth_frame(whole)) == 2
    assert (date(2026, 11, 5), date(2026, 11, 11)) in asked


def test_strict_run_prints_the_thin_session(monkeypatch, capsys):
    code = _main(monkeypatch, ["audit_data_freshness.py", "--strict"],
                 _spy({**whole, "2026-11-09": 240}))
    assert code == 1
    lines = capsys.readouterr().out.splitlines()

    session_lines = [ln for ln in lines if "market_data_intraday [sessions]" in ln]
    assert len(session_lines) == 1
    assert "SPY" in session_lines[0] and "stale" in session_lines[0]
    assert any("writer-job: fetch-alphavantage-intraday" in ln for ln in lines)
    assert any("detail: THIN: 240 of 390 regular-hours minutes" in ln for ln in lines)
    assert any("details:" in ln and '"expected_latest": "2026-11-09"' in ln
               and '"row_count_recent": 240' in ln for ln in lines)
    assert any("Overall:" in ln and "STALE" in ln for ln in lines)


def test_whole_run_prints_nothing_of_its_own(monkeypatch, capsys, caplog):
    # main() calls logging.basicConfig(level=logging.WARNING), which does
    # nothing under pytest because the root logger already has pytest's
    # handlers. Setting the level here stands for it, and keeps this test
    # independent of what an earlier test left on the root logger.
    caplog.set_level(logging.WARNING)
    code = _main(monkeypatch, ["audit_data_freshness.py", "--strict"],
                 lambda t: rth_frame(whole))
    assert code == 0
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert not [ln for ln in lines if "[sessions]" in ln]
    assert any("Overall:" in ln for ln in lines)
    for text in (captured.out, captured.err, caplog.text):
        assert "check=intraday_session_gaps" not in text


def test_failed_read_logs_the_check_and_prints_no_report(monkeypatch, capsys, caplog):
    caplog.set_level(logging.WARNING)
    with pytest.raises(ConnectionError, match="connection refused"):
        _main(monkeypatch, ["audit_data_freshness.py", "--strict"],
              ConnectionError("connection refused"))
    assert "check=intraday_session_gaps FAILED after" in caplog.text
    assert "Overall:" not in capsys.readouterr().out


def test_half_day_and_undetermined_details(monkeypatch):
    # 2026-11-26 is Thanksgiving and 2026-11-27 closes at 13:00 ET: 210 minutes.
    december = datetime(2026, 12, 1, 15, 0)
    four = {d: 390 for d in ("2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25")}

    report, calls = _audit(monkeypatch, _spy_of(four, {"2026-11-27": 188}), now=december)
    scan = next(c for c in calls if "inserted_at" in c["sql"])
    assert scan["params"]["start"] == datetime(2026, 11, 20, 2, tzinfo=timezone.utc)
    assert scan["params"]["end"] == datetime(2026, 11, 28, 2, tzinfo=timezone.utc)
    (row,) = _session_rows(report)
    assert row.expected_latest == "2026-11-27"
    assert row.detail == "THIN: 188 of 210 regular-hours minutes"
    assert row.row_count_recent == 188

    report, _ = _audit(monkeypatch, _spy_of(four, {"2026-11-27": 189}), now=december)
    assert _session_rows(report) == []

    row = mod._session_gap_row(
        _check(), "SPY",
        SessionReading(date(2025, 5, 1), 390, 240, 390, 240, False, "UNDETERMINED"))
    assert row.detail == ("UNDETERMINED: 240 as true UTC, 390 as Eastern labels, "
                          "240 as both, of 390")
    assert row.row_count_recent == 240
    assert row.expected_latest == "2025-05-01"
    assert row.status == "stale"


def _spy_of(full_days: dict, half_day: dict):
    """A scan reader for the Thanksgiving week: every ticker holds
    *full_days*; SPY holds *half_day* and the others a whole half day."""
    def scan(t):
        last = half_day if t == "SPY" else {d: 210 for d in half_day}
        return rth_frame({**full_days, **last})
    return scan


# -- --intraday-gap-since ------------------------------------------------------

Q2 = ("SELECT min(ts) AS first_ts FROM market_data_intraday WHERE ticker = :t "
      "AND interval = '1min'")
FIRST = datetime(2022, 2, 24, 9, 0, tzinfo=timezone.utc)
SUMMARY = "intraday-gap-since summary:"


def _gap_since(monkeypatch, argv, *, first_ts, months, now=NOW, configured=True):
    """Run main() with the on-demand flags over a recording strict reader.

    *first_ts* maps a ticker to its first stored instant (None for no row);
    *months* maps (ticker, year, month) to that month window's frame. An
    exception in place of either is raised by the reader.
    """
    import gcp.database as database

    def no_audit(*_a, **_k):
        raise AssertionError("audit_all must not run")

    calls: list[dict] = []

    def strict(sql, params=None, timeout_s=None):
        calls.append({"sql": sql, "params": params, "timeout_s": timeout_s})
        if "min(ts)" in sql:
            answer = first_ts.get(params["t"])
            if isinstance(answer, BaseException):
                raise answer
            return pd.DataFrame({"first_ts": [answer]})
        answer = months.get(
            (params["t"], params["start"].year, params["start"].month), rth_frame({}))
        if isinstance(answer, BaseException):
            raise answer
        return answer

    # A test may call this helper twice: reach past an earlier wrapper to the
    # real function instead of wrapping the wrapper.
    real = getattr(mod.run_intraday_gap_since, "real", mod.run_intraday_gap_since)

    def at_now(since, tickers, strict_flag):
        return real(since, tickers, strict_flag, now_utc=now)

    at_now.real = real
    monkeypatch.setattr(mod, "audit_all", no_audit)
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: configured)
    monkeypatch.setattr(mod, "run_intraday_gap_since", at_now)
    monkeypatch.setattr(database, "query_to_dataframe_strict", strict)
    monkeypatch.setattr(sys, "argv", ["audit_data_freshness.py", *argv])
    try:
        mod.main()
    except SystemExit as exc:
        return (0 if exc.code is None else exc.code), calls
    return 0, calls


def _sessions_in(first: str, last: str) -> list[str]:
    return [d.isoformat() for d in sessions_between(first, last)]


def _autumn_months(ticker: str = "SPY", *, thin: bool = True) -> dict:
    """September to 2026-11-11 for *ticker*. With *thin*: a 240-minute session
    on rows that are not proven (09-22), one on proven rows (10-05) and a
    session with no row (11-09). Without it every session is whole."""
    whole_old = [store(et_minutes(d, "04:00", "20:00"), "true")
                 for d in ("2026-09-21", "2026-09-23", "2026-09-24", "2026-09-25")]
    # Rows that are not proven read whole only with their extended hours
    # (Design F), so the whole form of 09-22 is 04:00 to 20:00 like the rest.
    cut = (pd.date_range("2026-09-22 09:30", periods=240, freq="min") if thin
           else et_minutes("2026-09-22", "04:00", "20:00"))
    unproven = pd.DatetimeIndex([], tz="UTC")
    for part in [*whole_old, store(cut, "true")]:
        unproven = unproven.append(part)
    september = pd.concat([
        pd.DataFrame({"ts": unproven,
                      "inserted_at": pd.DatetimeIndex([OLD] * len(unproven))}),
        rth_frame({d: 390 for d in ("2026-09-28", "2026-09-29", "2026-09-30")}),
    ], ignore_index=True)
    october = rth_frame({
        d: (240 if thin and d == "2026-10-05" else 390)
        for d in _sessions_in("2026-10-01", "2026-10-31")})
    november = rth_frame({
        d: 390 for d in _sessions_in("2026-11-01", "2026-11-11")
        if not (thin and d == "2026-11-09")})
    return {(ticker, 2026, 9): september, (ticker, 2026, 10): october,
            (ticker, 2026, 11): november}


def test_gap_since_reads_month_by_month_and_prints_the_lines(monkeypatch, capsys):
    argv = ["--intraday-gap-since", "2026-09-21", "--intraday-gap-tickers", "SPY"]
    code, calls = _gap_since(monkeypatch, argv, first_ts={"SPY": FIRST},
                             months=_autumn_months())
    assert code == 0

    assert len(calls) == 4
    probe, *reads = calls
    assert " ".join(probe["sql"].split()) == Q2
    assert probe["params"] == {"t": "SPY"}
    assert probe["timeout_s"] == 120
    assert [(c["params"]["start"], c["params"]["end"]) for c in reads] == [
        intraday_month_window(2026, 9), intraday_month_window(2026, 10),
        intraday_month_window(2026, 11)]
    for call in calls:
        assert "interval = '1min'" in call["sql"]
    for call in reads:
        assert " ".join(call["sql"].split()) == Q1
        assert call["params"]["t"] == "SPY"
        assert call["timeout_s"] == 120

    lines = capsys.readouterr().out.splitlines()
    assert lines[:-1] == [
        "MONTH SPY,2026-09 rows=5254 unproven_rows=4084",
        "SESSION-GAP SPY 2026-09-22 UNDETERMINED true_utc=240 eastern_label=150 "
        "both=0 expected=390 exact=no",
        "MONTH SPY,2026-10 rows=8430 unproven_rows=0",
        "SESSION-GAP SPY 2026-10-05 THIN true_utc=240 eastern_label=240 "
        "both=240 expected=390 exact=yes",
        "MONTH SPY,2026-11 rows=2730 unproven_rows=0",
        "SESSION-GAP SPY 2026-11-09 MISSING true_utc=0 eastern_label=0 "
        "both=0 expected=390 exact=yes",
    ]
    assert lines[-1].startswith(SUMMARY)
    assert ("SPY first=2022-02-24 sessions=38 ok=35 missing=1 thin=1 undetermined=1"
            in lines[-1])
    assert "seconds=" in lines[-1]

    code, _ = _gap_since(monkeypatch, [*argv, "--strict"], first_ts={"SPY": FIRST},
                         months=_autumn_months())
    assert code == 1
    capsys.readouterr()

    code, _ = _gap_since(monkeypatch, [*argv, "--strict"], first_ts={"SPY": FIRST},
                         months=_autumn_months(thin=False))
    assert code == 0
    out = capsys.readouterr().out
    assert "SESSION-GAP" not in out
    assert out.splitlines()[-1].startswith(SUMMARY)
    assert "SPY first=2022-02-24 sessions=38 ok=38 missing=0 thin=0 undetermined=0" in out


def test_sessions_before_the_first_stored_row_print_nothing(monkeypatch, capsys):
    months = _autumn_months()
    # The table's first row is the open of 2026-10-05: nothing before it is a gap.
    months[("SPY", 2026, 10)] = rth_frame({
        d: 390 for d in _sessions_in("2026-10-05", "2026-10-31")})
    code, calls = _gap_since(
        monkeypatch, ["--intraday-gap-since", "2026-09-21", "--intraday-gap-tickers", "SPY"],
        first_ts={"SPY": datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc)},
        months=months)
    assert code == 0
    reads = calls[1:]
    assert [(c["params"]["start"], c["params"]["end"]) for c in reads] == [
        intraday_month_window(2026, 10), intraday_month_window(2026, 11)]
    out = capsys.readouterr().out
    assert "MONTH SPY,2026-09" not in out
    gap_dates = [ln.split()[2] for ln in out.splitlines() if ln.startswith("SESSION-GAP")]
    assert gap_dates == ["2026-11-09"]
    assert "SPY first=2026-10-05 sessions=28 ok=27 missing=1 thin=0 undetermined=0" in out


def test_a_ticker_with_no_stored_row(monkeypatch, capsys):
    argv = ["--intraday-gap-since", "2026-11-05", "--intraday-gap-tickers", "QQQ"]
    code, calls = _gap_since(monkeypatch, argv, first_ts={"QQQ": None}, months={})
    assert code == 0
    assert len(calls) == 1 and "min(ts)" in calls[0]["sql"]
    lines = capsys.readouterr().out.splitlines()
    assert "NO-ROWS QQQ" in lines
    assert lines[-1].startswith(SUMMARY)
    assert "QQQ first=none sessions=0" in lines[-1]

    code, _ = _gap_since(monkeypatch, [*argv, "--strict"], first_ts={"QQQ": None},
                         months={})
    assert code == 1


def test_default_is_the_three_tickers(monkeypatch, capsys):
    code, calls = _gap_since(
        monkeypatch, ["--intraday-gap-since", "2026-11-05"],
        first_ts={"IWM": None, "SPY": None, "QQQ": None}, months={})
    assert code == 0
    assert [c["params"] for c in calls] == [{"t": t} for t in _check()["tickers"]]
    assert all("min(ts)" in c["sql"] for c in calls)


@pytest.mark.parametrize("argv", [
    ["--intraday-gap-since", "2026-11-05", "--intraday-gap-tickers", "AMD"],
    ["--intraday-gap-since", "2026-13-01"],
    ["--intraday-gap-since", "2026-11-12"],
    ["--intraday-gap-since", "2026-11-05", "--json"],
    ["--intraday-gap-tickers", "SPY"],
], ids=["another-ticker", "unparseable-date", "after-the-last-settled-session",
        "json", "tickers-without-since"])
def test_usage_errors_exit_2_before_any_query(monkeypatch, capsys, argv):
    code, calls = _gap_since(monkeypatch, argv, first_ts={}, months={})
    assert code == 2
    assert calls == []
    assert SUMMARY not in capsys.readouterr().out


def test_cloud_sql_not_configured_exits_2_before_any_query(monkeypatch, capsys):
    """As the audit does today: no query without a configured database."""
    code, calls = _gap_since(monkeypatch, ["--intraday-gap-since", "2026-11-05"],
                             first_ts={"SPY": FIRST}, months={}, configured=False)
    assert code == 2
    assert calls == []
    assert SUMMARY not in capsys.readouterr().out


@pytest.mark.parametrize("strict_flag", [[], ["--strict"]], ids=["listing", "strict"])
def test_a_calendar_error_exits_2_with_and_without_strict(monkeypatch, capsys, strict_flag):
    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "session_schedule", boom)
    code, _ = _gap_since(
        monkeypatch,
        ["--intraday-gap-since", "2026-09-21", "--intraday-gap-tickers", "SPY", *strict_flag],
        first_ts={"SPY": FIRST}, months=_autumn_months())
    assert code == 2
    captured = capsys.readouterr()
    assert not [ln for ln in captured.out.splitlines() if ln.startswith(SUMMARY)]
    assert "boom" in captured.err


@pytest.mark.parametrize("case", ["probe", "month-read", "readings"])
def test_reader_and_reading_errors_propagate(monkeypatch, capsys, case):
    argv = ["--intraday-gap-since", "2026-09-21", "--intraday-gap-tickers", "SPY"]
    first_ts, months, expected = {"SPY": FIRST}, _autumn_months(), KeyError
    if case == "probe":
        first_ts, expected = {"SPY": ConnectionError("connection refused")}, ConnectionError
    elif case == "month-read":
        months[("SPY", 2026, 10)] = KeyError("inserted_at")
    else:
        def broken(*_a, **_k):
            raise KeyError("inserted_at")
        monkeypatch.setattr(mod, "session_minute_readings", broken)

    with pytest.raises(expected):
        _gap_since(monkeypatch, argv, first_ts=first_ts, months=months)
    assert SUMMARY not in capsys.readouterr().out


def test_since_on_a_closed_day_and_ticker_spelling(monkeypatch, capsys):
    # 2026-10-31 is a Saturday: the scan starts at the next session.
    months = {**_autumn_months("SPY", thin=False), **_autumn_months("QQQ", thin=False)}
    code, calls = _gap_since(
        monkeypatch,
        ["--intraday-gap-since", "2026-10-31", "--intraday-gap-tickers", " spy, qqq "],
        first_ts={"SPY": FIRST, "QQQ": FIRST}, months=months)
    assert code == 0
    assert len(calls) == 6
    assert [c["params"]["t"] for c in calls] == ["SPY"] * 3 + ["QQQ"] * 3
    for probe, october, november in (calls[:3], calls[3:]):
        assert "min(ts)" in probe["sql"]
        assert (october["params"]["start"], october["params"]["end"]) == (
            intraday_month_window(2026, 10))
        assert (november["params"]["start"], november["params"]["end"]) == (
            intraday_month_window(2026, 11))
    summary = capsys.readouterr().out.splitlines()[-1]
    assert summary.startswith(SUMMARY)
    assert "SPY first=2022-02-24 sessions=8 ok=8 missing=0 thin=0 undetermined=0" in summary
    assert "QQQ first=2022-02-24 sessions=8 ok=8 missing=0 thin=0 undetermined=0" in summary
