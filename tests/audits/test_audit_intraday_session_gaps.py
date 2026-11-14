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

import pytest

import scripts.audit_data_freshness as mod
from lib.eastern_time import SessionReading
from tests.fixtures.intraday_checks import install_audit_readers, rth_frame

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


def test_a_calendar_error_from_the_schedule_is_the_one_calendar_row(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "session_schedule", boom)
    report, _ = _audit(monkeypatch, lambda t: rth_frame(whole))
    calendar_rows = [r for r in report.rows if r.table == "nyse_calendar"]
    assert len(calendar_rows) == 1
    assert "boom" in calendar_rows[0].detail
    assert _session_rows(report) == []

    assert _main(monkeypatch, ["audit_data_freshness.py", "--strict"],
                 lambda t: rth_frame(whole)) == 2


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
