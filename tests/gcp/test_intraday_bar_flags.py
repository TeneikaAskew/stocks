"""The bar flag pass: what it reads, proves, judges and labels (FEAT-DATA-001).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 3, Design 4, Design 9). Hermetic: the engine is a recording stand-in
that answers the pass's read from a frame the test gives and records every
statement's text and parameters. Expected rows are literals written here.
"""

from __future__ import annotations

import logging
import re
import sys
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

import gcp.database as database
import gcp.fetchers.export_intraday_bars as xb
import gcp.fetchers.fetch_alphavantage_intraday as fai
import gcp.fetchers.intraday_bar_flags as ibf
from gcp.bar_recompute import UnprovenRows, bars_basis
from lib.bar_prints import isolated_prints
from lib.eastern_time import intraday_month_window, utc_to_eastern_naive
from tests.lib.test_bar_prints import load_session

UTC = timezone.utc
READ_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "inserted_at"]
READ_SQL = (
    "SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday "
    "WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts"
)
# Every writer has stored true instants since 2026-09-28, so a row inserted on
# this date is proven whatever its ts.
PROVEN = pd.Timestamp("2026-11-14 20:54:41", tz="UTC")
UNPROVEN = pd.Timestamp("2024-01-05 12:00:00", tz="UTC")


# The stand-in engine


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def one(self):
        assert len(self._rows) == 1
        return self._rows[0]


class _Transaction:
    def __init__(self, engine):
        self._engine = engine
        self._open = True

    def __enter__(self):
        return self

    def rollback(self):
        if self._open:
            self._open = False
            self._engine.events.append("rollback")

    def __exit__(self, kind, value, traceback):
        if self._open:
            self._open = False
            self._engine.events.append("rollback" if kind else "commit")
        return False


class _Connection:
    def __init__(self, engine):
        self._engine = engine

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self._engine.events.append("close")
        return False

    def begin(self):
        self._engine.events.append("begin")
        return _Transaction(self._engine)

    def execute(self, statement, params=None):
        return self._engine.answer(str(statement), dict(params or {}))


class RecordingEngine:
    """Answers the pass's statements and records them.

    statements: (text, params) for everything issued on a connection, in
    order. events: "begin", "commit", "rollback" and "close", in order.
    bars: the stored rows of one ticker; the read is answered from them by
    its own start and end. read_errors: one entry per read, an exception to
    raise or None. coverage: the frame the strict coverage read returns;
    coverage_reads: its (sql, params, kwargs) calls. order: "coverage" and
    "statement", one per round trip, in the order they were made.
    """

    def __init__(self, bars=None, *, isolation="read committed", read_errors=(),
                 write_result=(0, 0, 0), coverage=None):
        self.bars = bars if bars is not None else pd.DataFrame(columns=READ_COLUMNS)
        self.isolation = isolation
        self.read_errors = list(read_errors)
        self.write_result = write_result
        self.coverage = coverage if coverage is not None else coverage_rows()
        self.statements: list[tuple[str, dict]] = []
        self.events: list[str] = []
        self.coverage_reads: list[tuple[str, dict, dict]] = []
        self.order: list[str] = []

    def query_to_dataframe_strict(self, sql, params=None, **kwargs):
        self.order.append("coverage")
        self.coverage_reads.append((sql, dict(params or {}), kwargs))
        return self.coverage.copy()

    def connect(self):
        return _Connection(self)

    def answer(self, text, params):
        self.order.append("statement")
        self.statements.append((text, params))
        if text.startswith("SELECT set_config"):
            return _Result([("120s", self.isolation)])
        if "pg_advisory_xact_lock" in text:
            return _Result([("",)])
        if "FROM market_data_intraday" in text:
            if self.read_errors:
                error = self.read_errors.pop(0)
                if error is not None:
                    raise error
            rows = self.bars[(self.bars.ts >= params["start"]) & (self.bars.ts < params["end"])]
            return _Result(rows[READ_COLUMNS].itertuples(index=False, name=None))
        if "intraday_bar_flags" in text:
            return _Result([self.write_result])
        raise AssertionError(f"a statement the stand-in does not know: {text}")

    def texts(self):
        return [text for text, _ in self.statements]

    def reads(self):
        return [(t, p) for t, p in self.statements if "FROM market_data_intraday" in t]

    def writes(self):
        return [p for t, p in self.statements if "INSERT INTO intraday_bar_flags" in t]


def coverage_rows(*rows) -> pd.DataFrame:
    """What the pass's coverage read returns: one (month, checked_at,
    session_sha256) per coverage row."""
    return pd.DataFrame(list(rows), columns=["month", "checked_at", "session_sha256"])


@pytest.fixture
def engine_for(monkeypatch):
    """Install a RecordingEngine as gcp.database's engine and strict read, and
    return it."""

    def install(bars=None, **kwargs):
        engine = RecordingEngine(bars, **kwargs)
        monkeypatch.setattr(database, "get_engine", lambda: engine)
        monkeypatch.setattr(database, "query_to_dataframe_strict",
                            engine.query_to_dataframe_strict)
        return engine

    return install


# Bars written out in the tests


def minutes(start: str, n: int, *, base: float = 100.0, bar_range: float = 0.05,
            inserted_at=PROVEN) -> pd.DataFrame:
    """n one-minute bars from start (UTC): open, close and low at base, high
    at base + bar_range, in the columns of the pass's read."""
    return pd.DataFrame({
        "ts": pd.date_range(start, periods=n, freq="1min", tz="UTC"),
        "open": base,
        "high": base + bar_range,
        "low": base,
        "close": base,
        "volume": 1000,
        "inserted_at": inserted_at,
    })


def stack(*frames: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(frames, ignore_index=True)


def low_wick(bars: pd.DataFrame, at: str, low: float = 99.40) -> pd.DataFrame:
    """The bar at the UTC instant `at` gets a low 60 bp under its body."""
    hit = bars.ts == pd.Timestamp(at, tz="UTC")
    assert hit.sum() == 1, at
    bars.loc[hit, "low"] = low
    return bars


def eastern_minute(ts) -> list[str]:
    return list(utc_to_eastern_naive(pd.Series(list(ts))).dt.strftime("%H:%M"))


def month_messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith("bar flags month:")]


# Task 5: the pass reads, proves, judges and labels


HALF_DAY_FLAGS = {
    ("SPY", "2025-07-03"): [
        ("13:01", "low", "wick"), ("13:06", "low", "wick"),
        ("13:58", "low", "wick"), ("13:59", "low", "wick"),
    ],
    ("SPY", "2025-12-24"): [("14:21", "low", "close")],
    ("IWM", "2018-12-24"): [],
    ("IWM", "2025-11-28"): [("13:17", "low", "close"), ("14:50", "low", "open")],
}
HALF_DAY_OBSERVED = {
    ("SPY", "2025-12-24", "14:21"): 670.292,
    ("IWM", "2025-11-28", "14:50"): 233.4998,
}


@pytest.mark.parametrize("ticker,day", list(HALF_DAY_FLAGS))
def test_half_days(ticker, day):
    bars = load_session(ticker, day)
    month = (int(day[:4]), int(day[5:7]))
    eastern = utc_to_eastern_naive(bars.ts)
    on_the_day = eastern.dt.strftime("%Y-%m-%d") == day
    assert on_the_day.sum() > 300

    # Every bar from the 13:00 close to 20:00 ET is extended.
    clock = eastern.dt.strftime("%H:%M")
    afternoon = on_the_day & (clock >= "13:00") & (clock <= "20:00")
    assert afternoon.sum() > 50
    parts = ibf.session_part(bars.ts)
    assert set(parts[afternoon.to_numpy()]) == {"extended"}
    # The morning of a half day is still the regular session.
    morning = on_the_day & (clock >= "09:30") & (clock < "13:00")
    assert set(parts[morning.to_numpy()]) == {"regular"}

    flags, _counts = ibf.judge_month(bars, month)
    flag_eastern = utc_to_eastern_naive(flags.ts)
    flags = flags.assign(day=flag_eastern.dt.strftime("%Y-%m-%d").to_numpy(),
                         clock=flag_eastern.dt.strftime("%H:%M").to_numpy())
    flags = flags[flags.day == day]
    assert not (flags.session_part == "regular").any()

    after_close = flags[(flags.clock >= "13:00") & (flags.clock < "16:00")]
    assert list(zip(after_close.clock, after_close.side, after_close.print_kind)) \
        == HALF_DAY_FLAGS[(ticker, day)]
    assert set(after_close.session_part) <= {"extended"}
    for (t, d, clock_at), observed in HALF_DAY_OBSERVED.items():
        if (t, d) == (ticker, day):
            assert after_close[after_close.clock == clock_at].observed.item() == observed


def test_dry_run_issues_only_the_read(engine_for):
    engine = engine_for(load_session("SPY", "2023-05-25"))
    out = ibf.flag_months(("SPY",), [(2023, 5)], commit=False)

    assert len(engine.statements) == 1
    text, params = engine.statements[0]
    assert text == READ_SQL
    assert "interval = '1min'" in text
    assert text.startswith("SELECT ts, open, high, low, close, volume, inserted_at FROM")
    start, end = intraday_month_window(2023, 5)
    assert params == {
        "t": "SPY",
        "start": start - timedelta(days=7),
        "end": end + timedelta(days=7),
    }
    assert params["start"] == datetime(2023, 4, 24, 2, tzinfo=UTC)
    assert params["end"] == datetime(2023, 6, 8, 2, tzinfo=UTC)
    for word in ("set_config", "pg_advisory", "INSERT", "DELETE"):
        assert word not in text
    assert engine.events == ["begin", "rollback", "close"]
    assert set(out) == {"months", "flags", "changed", "seconds"}
    assert out["months"] == 1 and out["changed"] == 0
    assert out["flags"] >= 16          # the session's 16 regular-hours flags, and extended ones
    assert out["seconds"] >= 0


def _two_months() -> pd.DataFrame:
    """May and June 2023: sixty bars from 14:00Z on each of twelve days, with
    a 60 bp low wick in each month, one on May's last bar but two, one on
    June's third bar, and two that only a wider read could judge."""
    days = ["2023-05-02", "2023-05-10", "2023-05-18", "2023-05-25", "2023-05-30",
            "2023-05-31", "2023-06-01", "2023-06-02", "2023-06-09", "2023-06-16",
            "2023-06-23", "2023-06-29"]
    bars = stack(*[minutes(f"{day} 14:00", 60) for day in days])
    for at in ("2023-05-10 14:30", "2023-05-31 14:57", "2023-06-01 14:02",
               "2023-06-16 14:10"):
        low_wick(bars, f"{at}:00")
    return bars


TWO_MONTH_FLAGS = [
    pd.Timestamp("2023-05-10 14:30", tz="UTC"), pd.Timestamp("2023-05-31 14:57", tz="UTC"),
    pd.Timestamp("2023-06-01 14:02", tz="UTC"), pd.Timestamp("2023-06-16 14:10", tz="UTC"),
]


def test_flags_outside_the_month_window_are_not_kept():
    bars = _two_months()
    may, may_counts = ibf.judge_month(bars, (2023, 5))
    june, june_counts = ibf.judge_month(bars, (2023, 6))

    assert list(may.ts) == TWO_MONTH_FLAGS[:2]
    assert list(june.ts) == TWO_MONTH_FLAGS[2:]
    assert may_counts["bars_in_month"] == 360 and june_counts["bars_in_month"] == 360
    assert may_counts["flags_extended_low"] + may_counts["flags_regular_low"] == 2
    assert june_counts["flags_extended_low"] + june_counts["flags_regular_low"] == 2


def test_two_months_equal_one_read(engine_for, monkeypatch):
    bars = _two_months()
    engine_for(bars)
    kept: list[pd.DataFrame] = []
    judge = ibf.judge_month

    def keeping(read, month):
        flags, counts = judge(read, month)
        kept.append(flags)
        return flags, counts

    monkeypatch.setattr(ibf, "judge_month", keeping)
    out = ibf.flag_months(("SPY",), [(2023, 5), (2023, 6)], commit=False)

    whole, _judged = isolated_prints(bars)
    assert list(whole.ts) == TWO_MONTH_FLAGS
    union = pd.concat(kept, ignore_index=True)
    columns = list(whole.columns)
    pd.testing.assert_frame_equal(union[columns], whole)
    assert out["months"] == 2 and out["flags"] == 4


def test_unproven_rows(engine_for):
    bars = minutes("2023-05-10 14:00", 60)
    bars.loc[17, "inserted_at"] = UNPROVEN
    engine = engine_for(bars)

    with pytest.raises(UnprovenRows) as raised:
        ibf.flag_months(("SPY",), [(2023, 5)], commit=False)
    assert (raised.value.unproven, raised.value.rows) == (1, 60)
    assert engine.events == ["begin", "rollback", "close"]


@pytest.mark.parametrize("error", [ConnectionError("connection refused"), KeyError("high")])
def test_read_failures_propagate(engine_for, error):
    engine = engine_for(minutes("2023-05-10 14:00", 60), read_errors=[error])

    with pytest.raises(type(error)) as raised:
        ibf.flag_months(("SPY",), [(2023, 5)], commit=False)
    assert raised.value is error
    assert engine.events == ["begin", "rollback", "close"]


def test_refuses_other_tickers(monkeypatch):
    def refuse():
        raise AssertionError("an engine was asked for")

    monkeypatch.setattr(database, "get_engine", refuse)
    with pytest.raises(ValueError, match="AAPL"):
        ibf.flag_months(("AAPL",), [(2023, 5)], commit=False)
    with pytest.raises(ValueError, match="AAPL"):
        ibf.flag_months(("SPY", "AAPL"), [(2023, 5)], commit=True)
    assert ibf.FLAG_TICKERS == ("SPY", "QQQ", "IWM")


def test_month_log_line(engine_for, caplog):
    engine_for(load_session("SPY", "2023-05-25"))
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        ibf.flag_months(("SPY", "QQQ"), [(2023, 5), (2023, 6)], commit=False)

    lines = month_messages(caplog)
    assert len(lines) == 4
    form = re.compile(
        r"bar flags month: (SPY|QQQ) \d{4}-\d{2} judged=\d+ regular_high=\d+ "
        r"regular_low=\d+ extended_high=\d+ extended_low=\d+ \(\d/4\)")
    assert all(form.fullmatch(line) for line in lines), lines
    # SPY 2023-05-25: 16 regular-hours flags, all low (the spec's count).
    assert lines[0].startswith("bar flags month: SPY 2023-05 judged=")
    assert " regular_high=0 regular_low=16 " in lines[0]
    assert lines[0].endswith("(1/4)")
    # June holds no bar of the file: nothing judged, nothing flagged.
    assert lines[1] == ("bar flags month: SPY 2023-06 judged=0 regular_high=0 "
                        "regular_low=0 extended_high=0 extended_low=0 (2/4)")
    assert [line.split()[3:5] for line in lines] == [
        ["SPY", "2023-05"], ["SPY", "2023-06"], ["QQQ", "2023-05"], ["QQQ", "2023-06"]]
    assert [line[-5:] for line in lines] == ["(1/4)", "(2/4)", "(3/4)", "(4/4)"]


# Review Focus: the edges of a session and of a month


@pytest.mark.parametrize("at,part", [
    ("2025-06-03 13:30:00", "regular"),    # 09:30:00 ET, a Tuesday: the open is inside
    ("2025-06-03 13:29:00", "extended"),   # 09:29:00 ET
    ("2025-06-03 19:59:00", "regular"),    # 15:59:00 ET
    ("2025-06-03 20:00:00", "extended"),   # 16:00:00 ET: the close is outside
    ("2025-06-07 15:00:00", "extended"),   # a Saturday
    ("2025-12-25 15:00:00", "extended"),   # Christmas, a Thursday
])
def test_session_edges(at, part):
    instant = pd.Timestamp(at, tz="UTC")
    bars = low_wick(minutes(str(instant - pd.Timedelta(minutes=30))[:19], 61), at)
    flags, counts = ibf.judge_month(bars, (instant.year, instant.month))

    assert list(flags.ts) == [instant]
    assert list(flags.side) == ["low"]
    assert list(flags.session_part) == [part]
    assert counts[f"flags_{part}_low"] == 1
    other = "extended" if part == "regular" else "regular"
    assert counts[f"flags_{other}_low"] == 0
    assert counts["flags_regular_high"] == 0 and counts["flags_extended_high"] == 0


def test_month_edge_bar_belongs_to_one_month():
    # June's window opens at 2023-06-01 02:00Z; the bar stamped then is June's.
    edge = "2023-06-01 02:00:00"
    bars = low_wick(minutes("2023-06-01 01:30:00", 61), edge)
    may, may_counts = ibf.judge_month(bars, (2023, 5))
    june, june_counts = ibf.judge_month(bars, (2023, 6))

    assert list(june.ts) == [pd.Timestamp(edge, tz="UTC")]
    assert len(may) == 0
    assert may_counts["bars_in_month"] == 30 and june_counts["bars_in_month"] == 31
    assert may_counts["bars_judged"] == 28 and june_counts["bars_judged"] == 29
    assert may_counts["last_judged_ts"] == pd.Timestamp("2023-06-01 01:59:00", tz="UTC")
    assert june_counts["first_judged_ts"] == pd.Timestamp(edge, tz="UTC")


# Task 6: the pass locks, writes and compares


CONFIG_SQL = ("SELECT set_config('lock_timeout', '120s', true), "
              "current_setting('transaction_isolation')")
LOCK_SQL = "SELECT pg_advisory_xact_lock(:k)"
NIGHT_ONE = datetime(2026, 11, 12, 2, 0, 5, tzinfo=UTC)
NIGHT_TWO = datetime(2026, 11, 13, 2, 0, 7, tzinfo=UTC)


def changed_messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith("BARS-CHANGED")]


def day_sha(bars: pd.DataFrame, utc_day: str) -> str:
    """The digest of the rows stamped on one UTC day. Every bar these tests
    write sits at 14:00Z to 15:00Z, where the UTC and the Eastern date agree."""
    return bars_basis(bars[bars.ts.dt.strftime("%Y-%m-%d") == utc_day])["sha256"]


def test_lock_key():
    assert ibf.flag_lock_key("SPY", (2023, 5)) == 2323874143540971683
    assert ibf.LOCK_TIMEOUT == "120s"

    months = [(year, month) for year in range(2015, 2027) for month in range(1, 13)]
    months = [m for m in months if m <= (2026, 11)]
    assert len(months) == 143
    keys = [ibf.flag_lock_key(ticker, m) for ticker in ("SPY", "QQQ", "IWM") for m in months]
    assert len(set(keys)) == 429
    assert all(type(k) is int and -2**63 <= k < 2**63 for k in keys)


def test_commit_issues_four_statements_in_order(engine_for):
    engine = engine_for(low_wick(minutes("2023-05-10 14:00", 60), "2023-05-10 14:30:00"))
    out = ibf.flag_months(("SPY",), [(2023, 5)], commit=True, now_utc=NIGHT_ONE)

    texts = engine.texts()
    assert len(texts) == 4
    assert texts[0] == CONFIG_SQL
    assert texts[1] == LOCK_SQL
    assert engine.statements[1][1] == {"k": 2323874143540971683}
    assert engine.statements[1][1] == {"k": ibf.flag_lock_key("SPY", (2023, 5))}
    assert texts[2] == READ_SQL
    assert "pg_advisory" not in texts[2] and "pg_advisory" not in texts[3]
    assert texts[3] == ibf.write_month_sql()
    for clause in ("DELETE FROM intraday_bar_flags", "INSERT INTO intraday_bar_flags (",
                   "INSERT INTO intraday_bar_flag_coverage (",
                   "ON CONFLICT (ticker, interval, ts, side, rule_version) DO UPDATE",
                   "ON CONFLICT (ticker, interval, ts, rule_version) DO UPDATE"):
        assert texts[3].count(clause) == 1, clause
    assert "market_data_intraday" not in texts[3]
    assert "detected_at = " not in texts[3]          # an update keeps the first pass's time
    assert engine.events == ["begin", "commit", "close"]
    assert out["months"] == 1 and out["flags"] == 1 and out["changed"] == 0

    # One strict coverage read for the ticker, before its first month.
    assert engine.order == ["coverage"] + ["statement"] * 4
    (sql, params, kwargs), = engine.coverage_reads
    assert "FROM intraday_bar_flag_coverage" in sql and "interval = '1min'" in sql
    assert params == {"t": "SPY", "v": "isolated-print-v1",
                      "first": datetime(2023, 5, 1, 2, tzinfo=UTC),
                      "last": datetime(2023, 5, 1, 2, tzinfo=UTC)}
    assert kwargs == {}


def test_commit_statements_of_two_tickers_and_two_months(engine_for):
    engine = engine_for(minutes("2023-05-10 14:00", 60))
    ibf.flag_months(("SPY", "QQQ"), [(2023, 5), (2023, 6)], commit=True, now_utc=NIGHT_ONE)

    assert engine.order == (["coverage"] + ["statement"] * 8) * 2
    assert engine.texts() == [CONFIG_SQL, LOCK_SQL, READ_SQL, ibf.write_month_sql()] * 4
    locks = [p["k"] for t, p in engine.statements if t == LOCK_SQL]
    assert locks == [ibf.flag_lock_key(ticker, month) for ticker in ("SPY", "QQQ")
                     for month in ((2023, 5), (2023, 6))]
    assert [p["t"] for _, p, _ in engine.coverage_reads] == ["SPY", "QQQ"]
    assert all(p["first"] == datetime(2023, 5, 1, 2, tzinfo=UTC)
               and p["last"] == datetime(2023, 6, 1, 2, tzinfo=UTC)
               for _, p, _ in engine.coverage_reads)
    assert engine.events == ["begin", "commit", "close"] * 4


def test_dry_run_reads_the_coverage_once_a_ticker(engine_for):
    engine = engine_for(minutes("2023-05-10 14:00", 60))
    ibf.flag_months(("SPY",), [(2023, 5), (2023, 6)], commit=False)

    assert engine.order == ["coverage", "statement", "statement"]
    assert engine.texts() == [READ_SQL, READ_SQL]
    assert engine.events == ["begin", "rollback", "close"] * 2


def test_other_isolation_raises_before_the_lock(engine_for):
    engine = engine_for(minutes("2023-05-10 14:00", 60), isolation="repeatable read")

    with pytest.raises(RuntimeError, match="repeatable read"):
        ibf.flag_months(("SPY",), [(2023, 5)], commit=True, now_utc=NIGHT_ONE)
    assert engine.texts() == [CONFIG_SQL]
    assert engine.events == ["begin", "rollback", "close"]


def test_a_failing_month_leaves_earlier_months_written(engine_for):
    error = ConnectionError("connection refused")
    engine = engine_for(minutes("2023-05-10 14:00", 60), read_errors=[None, error, None])

    with pytest.raises(ConnectionError) as raised:
        ibf.flag_months(("SPY",), [(2023, 5), (2023, 6), (2023, 7)], commit=True,
                        now_utc=NIGHT_ONE)
    assert raised.value is error
    # May committed; June stopped at its read; July was not started.
    assert engine.events == ["begin", "commit", "close", "begin", "rollback", "close"]
    assert engine.texts() == [CONFIG_SQL, LOCK_SQL, READ_SQL, ibf.write_month_sql(),
                              CONFIG_SQL, LOCK_SQL, READ_SQL]
    assert [w["month"] for w in engine.writes()] == [date(2023, 5, 1)]


def test_coverage_row_holds_the_read_window_and_the_session_digests(engine_for, monkeypatch):
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "fetch-alphavantage-intraday-abc12")
    # The third group crosses midnight UTC inside one Eastern evening
    # (19:30 to 20:29 ET on 2023-05-18), and the last sits in June, inside
    # May's read and outside its window.
    bars = stack(minutes("2023-05-10 14:00", 60), minutes("2023-05-11 14:00", 60),
                 minutes("2023-05-18 23:30", 60), minutes("2023-06-02 14:00", 60))
    low_wick(bars, "2023-05-11 14:30:00")
    engine = engine_for(bars)
    ibf.flag_months(("SPY",), [(2023, 5)], commit=True, now_utc=NIGHT_ONE)

    (written,) = engine.writes()
    assert written["read_start"] == datetime(2023, 4, 24, 2, tzinfo=UTC)
    assert written["read_end"] == datetime(2023, 6, 8, 2, tzinfo=UTC)
    assert written["m_start"] == datetime(2023, 5, 1, 2, tzinfo=UTC)
    assert written["m_end"] == datetime(2023, 6, 1, 2, tzinfo=UTC)
    assert written["month"] == date(2023, 5, 1)
    assert written["t"] == "SPY" and written["v"] == "isolated-print-v1"
    assert written["params"] == {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0,
                                 "floor_bp": 50.0}
    assert written["now"] == NIGHT_ONE
    assert written["run_id"] == "fetch-alphavantage-intraday-abc12"
    assert written["code_version"] == {"git_commit": None, "git_dirty": None, "built_at": None}

    assert written["bars_basis"] == bars_basis(bars)
    assert written["bars_basis"]["rows"] == 240
    assert list(written["session_sha256"]) == ["2023-05-10", "2023-05-11", "2023-05-18",
                                               "2023-06-02"]
    for n, day in enumerate(written["session_sha256"]):
        rows = bars.iloc[60 * n:60 * (n + 1)]
        assert written["session_sha256"][day] == bars_basis(rows)["sha256"], day
    assert len(set(written["session_sha256"].values())) == 4

    # The first two bars of the read have no two bars before them.
    assert written["bars_in_month"] == 180 and written["bars_judged"] == 178
    assert written["first_judged_ts"] == datetime(2023, 5, 10, 14, 2, tzinfo=UTC)
    assert written["last_judged_ts"] == datetime(2023, 5, 19, 0, 29, tzinfo=UTC)
    assert (written["flags_regular_high"], written["flags_regular_low"],
            written["flags_extended_high"], written["flags_extended_low"]) == (0, 1, 0, 0)
    (flag,) = written["flags"]
    assert flag == {
        "ts": "2023-05-11T14:30:00+00:00", "side": "low", "print_kind": "wick",
        "session_part": "regular", "observed": 99.40, "reference": 100.0,
        "bound": 99.50, "scale": pytest.approx(0.05), "excess_bp": pytest.approx(60.0),
    }


def _october() -> pd.DataFrame:
    return stack(*[minutes(f"2026-10-{day} 14:00", 60) for day in (13, 14, 15, 16)])


def _earlier_row(bars: pd.DataFrame, **overrides) -> pd.DataFrame:
    """The coverage row of an earlier pass over the 13th to the 15th."""
    shas = {f"2026-10-{day}": day_sha(bars, f"2026-10-{day}") for day in (13, 14, 15)}
    shas.update(overrides)
    return coverage_rows(
        (date(2026, 10, 1), pd.Timestamp("2026-10-16 01:00:05", tz="UTC"), shas))


def test_bars_changed(engine_for, caplog):
    bars = _october()

    # One date both hold differs.
    engine_for(bars, coverage=_earlier_row(bars, **{"2026-10-14": "0" * 64}))
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [(2026, 10)], commit=False)
    assert changed_messages(caplog) == [
        "BARS-CHANGED SPY 2026-10 sessions=2026-10-14 since=2026-10-16T01:00:05+00:00"]
    assert out["changed"] == 1

    # With commit, the write's own counts: 3 inserted and 2 deleted (1 updated).
    caplog.clear()
    engine = engine_for(bars, coverage=_earlier_row(bars, **{"2026-10-14": "0" * 64}),
                        write_result=(2, 3, 1))
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [(2026, 10)], commit=True, now_utc=NIGHT_ONE)
    assert changed_messages(caplog) == [
        "BARS-CHANGED SPY 2026-10 sessions=2026-10-14 since=2026-10-16T01:00:05+00:00 "
        "inserted=3 deleted=2"]
    assert out["changed"] == 1
    assert len(engine.writes()) == 1

    # A date the earlier row holds and the read does not is named too.
    caplog.clear()
    engine_for(bars, coverage=_earlier_row(
        bars, **{"2026-10-09": "f" * 64, "2026-10-14": "0" * 64}))
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        ibf.flag_months(("SPY",), [(2026, 10)], commit=False)
    assert changed_messages(caplog) == [
        "BARS-CHANGED SPY 2026-10 sessions=2026-10-09,2026-10-14 "
        "since=2026-10-16T01:00:05+00:00"]

    # A date only the read holds (the 16th) was appended: nothing is logged.
    caplog.clear()
    engine_for(bars, coverage=_earlier_row(bars))
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [(2026, 10)], commit=False)
    assert changed_messages(caplog) == []
    assert out["changed"] == 0

    # No earlier row for the month, or one for another month: nothing to compare.
    caplog.clear()
    other_month = _earlier_row(bars, **{"2026-10-14": "0" * 64})
    other_month["month"] = [date(2026, 9, 1)]
    engine_for(bars, coverage=other_month)
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [(2026, 10)], commit=False)
    assert changed_messages(caplog) == [] and out["changed"] == 0


# Review Focus: the live edge, an empty month and a short read


def test_live_edge_night_over_night(engine_for, caplog):
    # Night one: the month ends at bar N, 2026-11-11 14:59Z. Bar N-1 is a
    # 60 bp wick with one bar after it, so it cannot be judged yet.
    stored = stack(minutes("2026-11-10 14:00", 60), minutes("2026-11-11 14:00", 60))
    low_wick(stored, "2026-11-11 14:58:00")
    first = engine_for(stored)
    ibf.flag_months(("SPY",), [(2026, 11)], commit=True, now_utc=NIGHT_ONE)
    (one,) = first.writes()
    assert one["flags"] == []
    assert one["last_judged_ts"] == datetime(2026, 11, 11, 14, 57, tzinfo=UTC)
    assert list(one["session_sha256"]) == ["2026-11-10", "2026-11-11"]

    # Night two: the same bars and one more session.
    grown = stack(stored, minutes("2026-11-12 14:00", 60))
    second = engine_for(grown, coverage=coverage_rows(
        (one["month"], pd.Timestamp(one["now"]), one["session_sha256"])),
        write_result=(0, 1, 0))
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [(2026, 11)], commit=True, now_utc=NIGHT_TWO)
    (two,) = second.writes()

    assert changed_messages(caplog) == [] and out["changed"] == 0
    assert two["last_judged_ts"] == datetime(2026, 11, 12, 14, 57, tzinfo=UTC)
    assert two["last_judged_ts"] > one["last_judged_ts"]
    assert [(f["ts"], f["side"]) for f in two["flags"]] == [
        ("2026-11-11T14:58:00+00:00", "low")]
    assert list(two["session_sha256"]) == ["2026-11-10", "2026-11-11", "2026-11-12"]
    assert two["session_sha256"]["2026-11-11"] == one["session_sha256"]["2026-11-11"]


def test_month_with_no_bar(engine_for):
    engine = engine_for()
    out = ibf.flag_months(("IWM",), [(2023, 5)], commit=True, now_utc=NIGHT_ONE)

    (written,) = engine.writes()
    assert written["flags"] == []
    assert written["bars_in_month"] == 0 and written["bars_judged"] == 0
    assert written["first_judged_ts"] is None and written["last_judged_ts"] is None
    assert written["session_sha256"] == {}
    assert written["bars_basis"]["rows"] == 0
    assert out == {"months": 1, "flags": 0, "changed": 0, "seconds": out["seconds"]}


def test_short_read_judges_nothing(engine_for):
    engine = engine_for(low_wick(minutes("2023-05-10 14:00", 4), "2023-05-10 14:01:00"))
    out = ibf.flag_months(("SPY",), [(2023, 5)], commit=True, now_utc=NIGHT_ONE)

    (written,) = engine.writes()
    assert written["flags"] == []
    assert written["bars_in_month"] == 4 and written["bars_judged"] == 0
    assert written["first_judged_ts"] is None and written["last_judged_ts"] is None
    assert out["flags"] == 0


# Task 7: the nightly pass


NIGHTLY_ARGS = ["--symbol=ALL", "--force"]
PASS_RESULT = {"months": 6, "flags": 41, "changed": 2, "seconds": 9.8}


def run_main(monkeypatch, argv, *, flags=None, env=None, configured=True, fetch=None,
             real_pass=False):
    """Run fai.main() as the job would, with the fetch and the export stubbed.

    Returns (exit code, calls): the calls are ("fetch", symbol),
    ("flags", tickers, months, kwargs) and ("export", tickers, months), in
    the order main() made them. flags: what the pass returns, or an exception
    it raises. fetch: called with each symbol in place of the vendor fetch.
    real_pass: leave flag_months as it is (the test installs an engine).
    """
    calls: list = []

    def fake_process(symbol, start, end, keys, force):
        calls.append(("fetch", symbol))
        if fetch is not None:
            fetch(symbol)
        return fai.OUTCOME_OK

    def fake_flags(tickers, months, **kwargs):
        calls.append(("flags", tickers, months, kwargs))
        if isinstance(flags, BaseException):
            raise flags
        return dict(flags or PASS_RESULT)

    def fake_export(tickers, months, **kwargs):
        calls.append(("export", tickers, months))
        return {"months": 6, "rows": 123456, "seconds": 4.2}

    monkeypatch.setattr(fai, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(fai, "resolve_all_symbols", lambda: ["SPY", "QQQ", "IWM", "AMD"])
    monkeypatch.setattr(fai, "process_symbol", fake_process)
    monkeypatch.setattr(fai, "is_cloud_sql_configured", lambda: configured)
    monkeypatch.setattr(fai, "market_today", lambda: date(2026, 10, 31))
    monkeypatch.setattr(xb, "export_window", fake_export)
    if not real_pass:
        monkeypatch.setattr(ibf, "flag_months", fake_flags)
    for name in ("CLOUD_RUN_TASK_COUNT", "CLOUD_RUN_TASK_INDEX", "INTRADAY_BARS_EXPORT",
                 "INTRADAY_BAR_FLAGS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday", *argv])
    try:
        fai.main()
        code = 0
    except SystemExit as stop:
        code = stop.code
    return code, calls


def flag_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("bar flags")]


def kinds(calls) -> list[str]:
    return [call[0] for call in calls]


def test_nightly_runs_the_pass_after_the_fetch_and_before_the_export(monkeypatch):
    code, calls = run_main(monkeypatch, NIGHTLY_ARGS)

    assert code == 0
    assert calls == [
        ("fetch", "SPY"), ("fetch", "QQQ"), ("fetch", "IWM"), ("fetch", "AMD"),
        ("flags", ("SPY", "QQQ", "IWM"), [(2026, 9), (2026, 10)], {"commit": True}),
        ("export", ("SPY", "QQQ", "IWM"), [(2026, 9), (2026, 10)]),
    ]
    assert calls[4][2] == xb.nightly_months(date(2026, 10, 31))


def test_run_bar_flags_is_true_only_when_the_pass_returned(monkeypatch):
    monkeypatch.setattr(ibf, "flag_months", lambda *a, **k: dict(PASS_RESULT))
    assert fai._run_bar_flags(("SPY",), [(2026, 10)]) is True

    def refuse(*_args, **_kwargs):
        raise ValueError("ts is not strictly increasing at 2026-10-14 14:03:00+00:00")

    monkeypatch.setattr(ibf, "flag_months", refuse)
    assert fai._run_bar_flags(("SPY",), [(2026, 10)]) is False


def test_switch_off(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, NIGHTLY_ARGS, env={"INTRADAY_BAR_FLAGS": "off"})

    assert code == 0
    assert kinds(calls) == ["fetch"] * 4 + ["export"]
    assert flag_lines(caplog) == ["bar flags skipped: INTRADAY_BAR_FLAGS is off"]


@pytest.mark.parametrize("value", ["OFF", " Off "])
def test_switch_letter_case(monkeypatch, caplog, value):
    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, NIGHTLY_ARGS, env={"INTRADAY_BAR_FLAGS": value})

    assert code == 0
    assert kinds(calls) == ["fetch"] * 4 + ["export"]
    assert flag_lines(caplog) == ["bar flags skipped: INTRADAY_BAR_FLAGS is off"]


def test_any_other_value_of_the_switch_runs_the_pass(monkeypatch):
    code, calls = run_main(monkeypatch, NIGHTLY_ARGS, env={"INTRADAY_BAR_FLAGS": "on"})
    assert code == 0 and kinds(calls) == ["fetch"] * 4 + ["flags", "export"]


def test_database_not_configured_skips_the_pass(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, NIGHTLY_ARGS, configured=False)

    assert code == 0
    assert kinds(calls) == ["fetch"] * 4
    assert flag_lines(caplog) == ["bar flags skipped: the database is not configured"]


@pytest.mark.parametrize("argv,env", [
    (["--symbol=ALL"], None),                                             # no --force
    (["--symbol=ALL", "--force", "--start-date", "2026-10-01"], None),
    (["--symbol=ALL", "--force", "--end-date", "2026-10-31"], None),
    (["--symbols-file", "<file>", "--force"], None),
    (["--symbol", "SPY", "--force"], None),
    (NIGHTLY_ARGS, {"CLOUD_RUN_TASK_COUNT": "2"}),                        # two tasks
])
def test_other_shapes_flag_nothing(monkeypatch, tmp_path, caplog, argv, env):
    listed = tmp_path / "symbols.txt"
    listed.write_text("SPY\nQQQ\n")
    argv = [str(listed) if arg == "<file>" else arg for arg in argv]
    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, argv, env=env)

    assert code == 0
    assert "fetch" in kinds(calls)
    assert "flags" not in kinds(calls)
    assert flag_lines(caplog) == []


@pytest.mark.parametrize("error,kind", [
    (ConnectionError("connection refused"), "outage"),
    (KeyError("high"), "defect"),
])
def test_outage_and_defect(monkeypatch, caplog, error, kind):
    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, NIGHTLY_ARGS, flags=error)

    assert code == 1
    assert kinds(calls) == ["fetch"] * 4 + ["flags", "export"]
    (line,) = flag_lines(caplog)
    assert line.startswith(f"bar flags failed ({kind})")
    (record,) = [r for r in caplog.records if r.getMessage() == line]
    assert record.levelno == logging.ERROR and record.exc_info[1] is error


def test_flag_tables_absent(monkeypatch, caplog):
    # What a nightly that runs before apply-schema meets on its first read.
    import sqlalchemy.exc

    absent = sqlalchemy.exc.ProgrammingError(
        "SELECT month, checked_at, session_sha256 FROM intraday_bar_flag_coverage", {},
        Exception({"S": "ERROR", "C": "42P01",
                   "M": 'relation "intraday_bar_flag_coverage" does not exist'}))
    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, NIGHTLY_ARGS, flags=absent)

    assert code == 1
    assert kinds(calls) == ["fetch"] * 4 + ["flags", "export"]
    (line,) = flag_lines(caplog)
    assert line.startswith("bar flags failed (defect)")


def test_summary_line(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        code, _calls = run_main(monkeypatch, NIGHTLY_ARGS, flags=PASS_RESULT)

    assert code == 0
    assert flag_lines(caplog) == ["bar flags: 6 months, 41 flags, 2 changed, 9.8 s"]


def _session(close: float) -> pd.DataFrame:
    """The session of 2026-10-14, its 14:20Z close as given."""
    bars = minutes("2026-10-14 14:00", 60)
    bars.loc[20, "close"] = close
    return bars


@pytest.mark.parametrize("refetched,changed", [(100.0, False), (100.02, True)])
def test_the_pass_reads_what_the_refetch_left(engine_for, monkeypatch, caplog,
                                              refetched, changed):
    values_a = _session(100.0)       # what the last pass judged
    values_b = _session(100.01)      # what the 23:00 writer left
    engine = engine_for(values_b, coverage=coverage_rows((
        date(2026, 10, 1), pd.Timestamp("2026-10-15 01:00:05", tz="UTC"),
        {"2026-10-14": bars_basis(values_a)["sha256"]})))
    assert bars_basis(values_b)["sha256"] != bars_basis(values_a)["sha256"]

    def upsert(symbol):
        # The night's fetch: every bar the vendor returns, written unconditionally.
        engine.bars = _session(refetched)

    with caplog.at_level(logging.INFO):
        code, calls = run_main(monkeypatch, NIGHTLY_ARGS, fetch=upsert, real_pass=True)

    assert code == 0
    assert kinds(calls) == ["fetch"] * 4 + ["export"]
    # Every read came after the last fetch, and found what it wrote.
    assert len(engine.reads()) == 6
    assert [w["bars_basis"] for w in engine.writes() if w["month"] == date(2026, 10, 1)] \
        == [bars_basis(_session(refetched))] * 3
    lines = changed_messages(caplog)
    if changed:
        assert lines == [
            f"BARS-CHANGED {ticker} 2026-10 sessions=2026-10-14 "
            "since=2026-10-15T01:00:05+00:00 inserted=0 deleted=0"
            for ticker in ("SPY", "QQQ", "IWM")]
        assert flag_lines(caplog)[-1].startswith("bar flags: 6 months, 0 flags, 3 changed, ")
    else:
        assert lines == []
        assert flag_lines(caplog)[-1].startswith("bar flags: 6 months, 0 flags, 0 changed, ")


# Task 8: the history run


HISTORY_TODAY = date(2026, 11, 16)


def run_history(monkeypatch, argv, *, env=None, configured=True):
    """Run fai.main() for a --flag-bars-from run, the Eastern date stubbed to
    2026-11-16. Returns (exit code, calls): each call is the
    (tickers, months, kwargs) flag_months was given. Reading an API key or
    fetching anything fails the test."""
    calls: list = []

    def fake_flags(tickers, months, **kwargs):
        calls.append((tickers, months, kwargs))
        return dict(PASS_RESULT)

    def no_fetch(*_args, **_kwargs):
        raise AssertionError("the history run fetches nothing and reads no API key")

    monkeypatch.setattr(fai, "get_api_keys", no_fetch)
    monkeypatch.setattr(fai, "resolve_all_symbols", no_fetch)
    monkeypatch.setattr(fai, "process_symbol", no_fetch)
    monkeypatch.setattr(fai, "fetch_month", no_fetch)
    monkeypatch.setattr(fai, "is_cloud_sql_configured", lambda: configured)
    monkeypatch.setattr(fai, "market_today", lambda: HISTORY_TODAY)
    monkeypatch.setattr(xb, "export_window", no_fetch)
    monkeypatch.setattr(ibf, "flag_months", fake_flags)
    for name in ("CLOUD_RUN_TASK_COUNT", "CLOUD_RUN_TASK_INDEX", "INTRADAY_BARS_EXPORT",
                 "INTRADAY_BAR_FLAGS", "ALPHA_VANTAGE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday", *argv])
    try:
        fai.main()
        code = 0
    except SystemExit as stop:
        code = stop.code
    return code, calls


def test_history_months(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        code, calls = run_history(monkeypatch, ["--flag-bars-from", "2015-01", "--symbol", "SPY"])
    assert code == 0
    ((tickers, months, kwargs),) = calls
    assert tickers == ("SPY",)
    assert len(months) == 143
    assert months[0] == (2015, 1) and months[-1] == (2026, 11)
    assert months == xb.months_between((2015, 1), (2026, 11))
    assert kwargs == {"commit": False}
    assert flag_lines(caplog)[-1] == "bar flags: 6 months, 41 flags, 2 changed, 9.8 s"

    code, calls = run_history(
        monkeypatch, ["--flag-bars-from", "2015-01", "--flag-bars-to", "2020-12",
                      "--symbol", "SPY"])
    assert code == 0
    ((tickers, months, kwargs),) = calls
    assert len(months) == 72
    assert months[0] == (2015, 1) and months[-1] == (2020, 12)
    assert kwargs == {"commit": False}

    code, calls = run_history(monkeypatch, ["--flag-bars-from", "2015-01", "--symbol", "ALL"])
    assert code == 0
    assert calls[0][0] == ("SPY", "QQQ", "IWM") and len(calls[0][1]) == 143

    # --symbol defaults to ALL.
    code, calls = run_history(monkeypatch, ["--flag-bars-from=2026-10"])
    assert code == 0
    assert calls == [(("SPY", "QQQ", "IWM"), [(2026, 10), (2026, 11)], {"commit": False})]

    code, calls = run_history(
        monkeypatch, ["--flag-bars-from", "2021-01", "--symbol", "QQQ", "--commit"])
    assert code == 0
    ((tickers, months, kwargs),) = calls
    assert tickers == ("QQQ",)
    assert len(months) == 71 and months[0] == (2021, 1) and months[-1] == (2026, 11)
    assert kwargs == {"commit": True}


def test_history_of_one_month(monkeypatch):
    code, calls = run_history(
        monkeypatch, ["--flag-bars-from", "2023-05", "--flag-bars-to", "2023-05",
                      "--symbol", "IWM"])
    assert code == 0
    assert calls == [(("IWM",), [(2023, 5)], {"commit": False})]


@pytest.mark.parametrize("argv,env,configured", [
    (["--flag-bars-from", "2015-01", "--symbol", "AAPL"], None, True),
    (["--flag-bars-from", "2015-01", "--symbol", "SPY,QQQ"], None, True),
    (["--flag-bars-from", "2015-01", "--symbol", "SPY"], {"CLOUD_RUN_TASK_COUNT": "2"}, True),
    (["--flag-bars-from", "2015-01", "--symbol", "SPY"], None, False),
    (["--flag-bars-from", "2026-12", "--symbol", "SPY"], None, True),
    (["--flag-bars-from", "2021-01", "--flag-bars-to", "2020-12", "--symbol", "SPY"],
     None, True),
    (["--flag-bars-from", "2021-01", "--flag-bars-to", "2026-12", "--symbol", "SPY"],
     None, True),
    (["--flag-bars-to", "2020-12", "--symbol", "SPY"], None, True),
    (["--flag-bars-to", "2020-12", "--symbol", "SPY", "--commit"], None, True),
])
def test_refusals_exit_1_before_any_query(monkeypatch, caplog, argv, env, configured):
    def no_query(*_args, **_kwargs):
        raise AssertionError("a refused history run issues no query")

    monkeypatch.setattr(database, "get_engine", no_query)
    monkeypatch.setattr(database, "query_to_dataframe_strict", no_query)
    with caplog.at_level(logging.INFO):
        code, calls = run_history(monkeypatch, argv, env=env, configured=configured)

    assert code == 1
    assert calls == []
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and errors[0].startswith("flag-bars-from: ")
    assert errors[0].endswith("Nothing was read.")


@pytest.mark.parametrize("other", [
    ["--replace-months", "list.csv"],
    ["--verify-months", "list.csv"],
    ["--verify-basis", "list.csv"],
    ["--export-bars-from", "2015-01"],
])
def test_usage_errors(monkeypatch, other):
    code, calls = run_history(
        monkeypatch, ["--flag-bars-from", "2015-01", "--symbol", "SPY", *other])
    assert code == 2 and calls == []


@pytest.mark.parametrize("argv", [
    ["--flag-bars-from", "2026-13"],
    ["--flag-bars-from", "2026-1"],
    ["--flag-bars-from", "202601"],
    ["--flag-bars-from", "2015-01", "--flag-bars-to", "2026-13"],
    ["--flag-bars-from", "2015-01", "--flag-bars-to", "2026-1"],
    ["--flag-bars-from", "2015-01", "--flag-bars-to", "202601"],
    ["--flag-bars-from", "2015-01", "--symbols-file", "symbols.txt"],
    ["--flag-bars-from", "2015-01", "--start-date", "2026-10-01"],
    ["--flag-bars-from", "2015-01", "--end-date", "2026-10-31"],
])
def test_history_month_format_is_a_usage_error(monkeypatch, argv):
    code, calls = run_history(monkeypatch, [*argv, "--symbol", "SPY"])
    assert code == 2 and calls == []


def test_history_symbol_letter_case(monkeypatch):
    code, calls = run_history(monkeypatch, ["--flag-bars-from", "2026-10", "--symbol", "spy"])
    assert code == 0
    assert calls == [(("SPY",), [(2026, 10), (2026, 11)], {"commit": False})]


def test_history_pass_that_raises_exits_1(monkeypatch, caplog):
    def refuse(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    with caplog.at_level(logging.INFO):
        code, _calls = run_history(monkeypatch, ["--flag-bars-from", "2026-10", "--symbol", "SPY"])
        assert code == 0
        monkeypatch.setattr(ibf, "flag_months", refuse)
        monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday",
                                          "--flag-bars-from", "2026-10", "--symbol", "SPY"])
        with pytest.raises(SystemExit) as stop:
            fai.main()
    assert stop.value.code == 1
    assert flag_lines(caplog)[-1].startswith("bar flags failed (outage)")


# Task 10: the months a replace must lock


def test_months_overlapping():
    start, end = intraday_month_window(2023, 5)
    assert ibf.flag_months_overlapping(start, end) == [(2023, 4), (2023, 5), (2023, 6)]
    # A tail strip past May's window end.
    assert ibf.flag_months_overlapping(end, end + timedelta(days=1)) == [(2023, 5), (2023, 6)]
    # An empty span, and one that runs backwards.
    assert ibf.flag_months_overlapping(start, start) == []
    assert ibf.flag_months_overlapping(end, start) == []
    # Across a year end.
    assert ibf.flag_months_overlapping(*intraday_month_window(2025, 12)) == [
        (2025, 11), (2025, 12), (2026, 1)]
    assert ibf.flag_months_overlapping(*intraday_month_window(2026, 1)) == [
        (2025, 12), (2026, 1), (2026, 2)]


def test_months_overlapping_is_the_span_clears_predicate():
    # read_start < end AND read_end > start, as the replace's DELETE has it,
    # over every month a span of the history could touch.
    every = xb.months_between((2014, 1), (2027, 12))
    spans = [
        intraday_month_window(2023, 5),
        (datetime(2023, 5, 8, 2, tzinfo=UTC), datetime(2023, 5, 8, 2, 1, tzinfo=UTC)),
        (datetime(2023, 5, 8, 1, 59, tzinfo=UTC), datetime(2023, 5, 8, 2, tzinfo=UTC)),
        (datetime(2023, 5, 25, 1, 59, tzinfo=UTC), datetime(2023, 5, 25, 2, tzinfo=UTC)),
        (datetime(2023, 5, 25, 2, tzinfo=UTC), datetime(2023, 5, 25, 2, 1, tzinfo=UTC)),
        (datetime(2015, 1, 2, tzinfo=UTC), datetime(2026, 11, 14, tzinfo=UTC)),
    ]
    expected = [
        [(2023, 4), (2023, 5), (2023, 6)],
        [(2023, 5)],               # past April's margin: May's own days only
        [(2023, 4), (2023, 5)],    # the last minute April's read holds
        [(2023, 5)],               # the minute before June's read starts
        [(2023, 5), (2023, 6)],    # the first minute June's read holds
        xb.months_between((2014, 12), (2026, 11)),
    ]
    for (start, end), months in zip(spans, expected):
        by_predicate = [m for m in every
                        if ibf.read_window(m)[0] < end and ibf.read_window(m)[1] > start]
        assert ibf.flag_months_overlapping(start, end) == by_predicate == months


def test_months_overlapping_refuses_a_naive_bound():
    start, end = intraday_month_window(2023, 5)
    with pytest.raises(ValueError, match="tz-aware"):
        ibf.flag_months_overlapping(start.replace(tzinfo=None), end)
    with pytest.raises(ValueError, match="tz-aware"):
        ibf.flag_months_overlapping(start, end.replace(tzinfo=None))
