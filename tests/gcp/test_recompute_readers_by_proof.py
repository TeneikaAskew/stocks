"""The three readers the recompute runs place a stored 1-min row by proof
(FEAT-DATA-001, Design H).

``market_data_intraday`` holds two timestamp conventions (CLAUDE.md 3.9). A
row is PROVEN a true UTC instant when its UTC date is 2026-09-28 or later, or
its ``inserted_at`` is: every writer has converted since then. The readers
here select ``inserted_at`` and place rows with
``lib.eastern_time.place_stored_rows``: a proven row is read where it is
stored, and a row that is not proven is placed by the resolver, as before.

The fixture is the session the resolver gets wrong. SPY 2025-05-05, a Monday
the vendor served thin: stored as true UTC from 04:00 to 13:29 ET, flat
volume. The truth is 240 regular-hours bars, 09:30 to 13:29 ET. Read as
Eastern labels the same rows look like a whole regular session, 390 of 390
minutes, so the resolver takes that reading and every bar lands four hours
from its own minute.

Each reader has a twin over the same rows with an ``inserted_at`` that proves
nothing, which asserts what ``main`` returns: unproven rows are placed exactly
as before. Expected rows are written from the Eastern minute alone, never
through the code under test.
"""
from __future__ import annotations

import pandas as pd
import pytest

from gcp.research.strat_engine import strat_data_builder as sdb

DAY = "2025-05-05"
PROVEN = pd.Timestamp("2026-11-20 03:00", tz="UTC")
UNPROVEN = pd.Timestamp("2026-02-23 03:00", tz="UTC")
# 2025-05-05 is under EDT: an Eastern minute is four hours behind its UTC instant.
EDT = pd.Timedelta(hours=4)
VALUES = ["open", "high", "low", "close", "volume"]


def _bars(first: str, last: str) -> pd.DataFrame:
    """The session's bars for the Eastern minutes *first* to *last* (both
    included): ``ts`` their true UTC instant, ``open`` 1000 plus the bar's own
    Eastern minute of the day, ``high`` 0.5 above it, ``low`` 0.5 below it,
    ``close`` 0.25 above it, ``volume`` 1000."""
    wall = pd.date_range(f"{DAY} {first}", f"{DAY} {last}", freq="min")
    minute = (wall.hour * 60 + wall.minute).astype("float64")
    return pd.DataFrame({
        "ts": (wall + EDT).tz_localize("UTC"),
        "open": 1000.0 + minute,
        "high": 1000.5 + minute,
        "low": 999.5 + minute,
        "close": 1000.25 + minute,
        "volume": 1000,
    })


def thin_monday(inserted) -> pd.DataFrame:
    """The stored rows: 04:00 to 13:29 ET as true UTC (570 rows, 08:00 to
    17:29 UTC), with ``inserted_at`` as given."""
    rows = _bars("04:00", "13:29")
    assert len(rows) == 570
    assert rows["ts"].iloc[0] == pd.Timestamp(f"{DAY} 08:00", tz="UTC")
    assert rows["ts"].iloc[-1] == pd.Timestamp(f"{DAY} 17:29", tz="UTC")
    rows["inserted_at"] = inserted
    return rows


def expected_minutes(first: str, last: str) -> pd.DataFrame:
    """The bars a reader must return for those Eastern minutes, each on its
    own minute with its own values."""
    return _bars(first, last)


def assert_bars(instants, got: pd.DataFrame, want: pd.DataFrame, columns=VALUES) -> None:
    """*got*'s rows sit on *want*'s instants and hold *want*'s values."""
    assert len(got) == len(want)
    assert list(pd.DatetimeIndex(instants)) == list(want["ts"])
    for ours, theirs in zip(columns, VALUES):
        assert [float(v) for v in got[ours]] == [float(v) for v in want[theirs]], ours


# -- the feature loader: strat_data_builder._load_1m_bars -----------------------


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Engine:
    def connect(self):
        return _Conn()


def _stub_read_sql(monkeypatch, module, rows: pd.DataFrame, since="start_ts") -> list:
    """Answer the module's ``pd.read_sql`` with *rows* at or after the bound
    start; returns the list the SQL texts land in."""
    seen: list = []

    def read_sql(sql, conn, params=None):
        seen.append(str(sql))
        if rows.empty:
            return rows.copy()
        return rows[rows["ts"] >= params[since]].reset_index(drop=True).copy()

    monkeypatch.setattr(module.pd, "read_sql", read_sql)
    return seen


def test_strat_builder_load_1m_bars(monkeypatch):
    seen = _stub_read_sql(monkeypatch, sdb, thin_monday(PROVEN))

    out = sdb._load_1m_bars(_Engine(), "SPY", DAY)

    want = expected_minutes("09:30", "13:29")
    assert len(out) == 240
    assert out.index[0] == pd.Timestamp(f"{DAY} 13:30", tz="UTC")
    assert out.index[-1] == pd.Timestamp(f"{DAY} 17:29", tz="UTC")
    assert_bars(out.index, out, want)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert str(out.index.dtype) == "datetime64[ns, UTC]"
    assert out.index.name == "ts"
    assert len(seen) == 1 and "inserted_at" in seen[0]
    assert "interval = '1min'" in seen[0]


def test_strat_builder_load_1m_bars_unproven_twin(monkeypatch):
    # What main returns for both fixtures today: the resolver reads the date
    # as Eastern labels, so 390 apparent regular-hours bars where 240 exist.
    _stub_read_sql(monkeypatch, sdb, thin_monday(UNPROVEN))

    out = sdb._load_1m_bars(_Engine(), "SPY", DAY)

    assert len(out) == 390
    assert out.index[0] == pd.Timestamp(f"{DAY} 13:30", tz="UTC")      # 09:30 ET
    assert out.index[-1] == pd.Timestamp(f"{DAY} 19:59", tz="UTC")     # 15:59 ET
    assert out["open"].iloc[0] == 1330.0                               # the bar of 05:30 ET
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert str(out.index.dtype) == "datetime64[ns, UTC]"


def test_strat_builder_load_1m_bars_needs_inserted_at(monkeypatch):
    # No reader falls back to the resolver alone.
    _stub_read_sql(monkeypatch, sdb, thin_monday(PROVEN).drop(columns="inserted_at"))
    with pytest.raises(KeyError, match="inserted_at"):
        sdb._load_1m_bars(_Engine(), "SPY", DAY)


@pytest.mark.parametrize("columns", [
    ["ts", "open", "high", "low", "close", "volume"],
    ["ts", "open", "high", "low", "close", "volume", "inserted_at"],
])
def test_strat_builder_empty_read_returns_as_before(monkeypatch, columns):
    # An empty read returns before the column is touched, with the five
    # columns either way.
    _stub_read_sql(monkeypatch, sdb, pd.DataFrame(columns=columns))

    out = sdb._load_1m_bars(_Engine(), "SPY", DAY)

    assert out.empty
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index.name == "ts"
