"""The bar flag pass: what it reads, proves, judges and labels (FEAT-DATA-001).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 3, Design 4, Design 9). Hermetic: the engine is a recording stand-in
that answers the pass's read from a frame the test gives and records every
statement's text and parameters. Expected rows are literals written here.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import gcp.database as database
import gcp.fetchers.intraday_bar_flags as ibf
from gcp.bar_recompute import UnprovenRows
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
    raise or None.
    """

    def __init__(self, bars=None, *, isolation="read committed", read_errors=(),
                 write_result=(0, 0, 0)):
        self.bars = bars if bars is not None else pd.DataFrame(columns=READ_COLUMNS)
        self.isolation = isolation
        self.read_errors = list(read_errors)
        self.write_result = write_result
        self.statements: list[tuple[str, dict]] = []
        self.events: list[str] = []

    def connect(self):
        return _Connection(self)

    def answer(self, text, params):
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


@pytest.fixture
def engine_for(monkeypatch):
    """Install a RecordingEngine as gcp.database.get_engine and return it."""

    def install(bars=None, **kwargs):
        engine = RecordingEngine(bars, **kwargs)
        monkeypatch.setattr(database, "get_engine", lambda: engine)
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
