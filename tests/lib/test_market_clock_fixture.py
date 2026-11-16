"""The frozen market clock (tests/fixtures/market_clock.py) does what its users rely on.

Every stage-one test freezes one instant through this seam and forbids the
host clock in the module under test (FEAT-DATA-001, stage 1 of the market-time
sweep). If the seam let a host read through, those tests would pass on the
test machine's clock and prove nothing about the evening.
"""
from __future__ import annotations

import types
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

import lib.eastern_time as eastern_time
from lib.eastern_time import ET, market_today
from tests.fixtures.market_clock import (
    DAYTIME,
    HOST_ENV,
    STANDARD_INSTANTS,
    HostClockRead,
    freeze_market_clock,
)

REPO = Path(__file__).resolve().parents[2]
WINTER_SUNDAY_EVENING = "2026-11-09T00:00:30Z"  # Sunday 2026-11-08 19:00:30 EST


def _module() -> types.ModuleType:
    mod = types.ModuleType("module_under_test")
    mod.date = date
    mod.datetime = datetime
    return mod


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch):
    """These tests state the mode they run in; the record runs set the variable."""
    monkeypatch.delenv(HOST_ENV, raising=False)


def test_the_seam_moves_market_today(monkeypatch):
    frozen = freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING)
    assert market_today() == date(2026, 11, 8)
    # The seam is the module attribute: a name imported before the freeze is the real clock.
    assert eastern_time.utc_now() == frozen
    assert eastern_time.eastern_now() == frozen
    assert frozen.utcoffset().total_seconds() == 0

    for instant, eastern in STANDARD_INSTANTS:
        freeze_market_clock(monkeypatch, instant)
        assert market_today() == eastern, instant
    assert STANDARD_INSTANTS[-1][0] == DAYTIME


def test_a_host_read_raises_and_an_aware_read_is_frozen(monkeypatch):
    mod = _module()
    freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING, mod)

    for read in (mod.date.today, mod.datetime.now, mod.datetime.utcnow, mod.datetime.today):
        with pytest.raises(HostClockRead):
            read()

    assert mod.datetime.now(ET).date() == date(2026, 11, 8)
    assert mod.datetime.strptime("2026-01-02", "%Y-%m-%d").date() == date(2026, 1, 2)
    assert mod.date.fromisoformat("2026-01-02") == date(2026, 1, 2)
    assert isinstance(datetime(2026, 1, 1), mod.datetime)
    assert isinstance(date(2026, 1, 1), mod.date)
    assert issubclass(datetime, mod.datetime)


def test_function_local_imports_and_pandas_are_guarded_on_request(monkeypatch):
    freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING, stdlib=True, pandas=True)

    def local_import_read():
        from datetime import date as _d

        return _d.today()

    with pytest.raises(HostClockRead):
        local_import_read()
    with pytest.raises(HostClockRead):
        pd.Timestamp.utcnow()
    with pytest.raises(HostClockRead):
        pd.Timestamp.now()
    assert pd.Timestamp.now(tz="America/New_York").date() == date(2026, 11, 8)
    assert pd.to_datetime("2026-01-02") == pd.Timestamp(2026, 1, 2)


def test_host_utc_mode_answers_as_a_utc_container(monkeypatch):
    monkeypatch.setenv(HOST_ENV, "utc")
    mod = _module()
    freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING, mod, pandas=True)

    assert mod.date.today() == date(2026, 11, 9)
    assert type(mod.date.today()) is date
    assert mod.datetime.now() == datetime(2026, 11, 9, 0, 0, 30)
    assert mod.datetime.utcnow().date() == date(2026, 11, 9)
    assert pd.Timestamp.utcnow().date() == date(2026, 11, 9)
    assert market_today() == date(2026, 11, 8)


def test_a_swallowing_block_cannot_hide_a_host_read(monkeypatch):
    mod = _module()
    freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING, mod)

    def swallow():
        try:
            return mod.datetime.now()
        except Exception:  # the shape of the handlers and fetchers under test
            return "swallowed"

    with pytest.raises(HostClockRead) as caught:
        swallow()
    assert Path(__file__).name in str(caught.value)
    assert "datetime.now()" in str(caught.value)


def test_an_allowed_instant_is_let_through(monkeypatch):
    mod = _module()
    freeze_market_clock(
        monkeypatch, WINTER_SUNDAY_EVENING, mod,
        allow_instants=("mod.datetime.now().isoformat()",),
    )

    stamp = mod.datetime.now().isoformat()
    assert stamp == "2026-11-09T00:00:30"
    with pytest.raises(HostClockRead):
        d = mod.datetime.now().date()  # noqa: F841 - a date read is never an allowed instant


def test_bad_input_is_refused(monkeypatch):
    with pytest.raises(ValueError):
        freeze_market_clock(monkeypatch, "2026-11-09T00:00:30")
    monkeypatch.setenv(HOST_ENV, "local")
    with pytest.raises(ValueError):
        freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING)


def test_a_module_that_holds_the_datetime_module_needs_stdlib(monkeypatch):
    import datetime as datetime_module

    mod = types.ModuleType("module_under_test")
    mod.dt = datetime_module
    with pytest.raises(ValueError, match="stdlib=True"):
        freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING, mod)
    freeze_market_clock(monkeypatch, WINTER_SUNDAY_EVENING, mod, stdlib=True)
    with pytest.raises(HostClockRead):
        mod.dt.date.today()


def test_no_committed_file_sets_the_host_mode():
    """The utc mode exists for the red-run record only; CI runs the raising mode."""
    assert HOST_ENV == "MARKET_CLOCK_HOST"
    candidates = [REPO / "Makefile", REPO / "tests" / "conftest.py", REPO / "pytest.ini", REPO / "pyproject.toml"]
    candidates += sorted((REPO / ".github" / "workflows").glob("*"))
    read = 0
    for path in candidates:
        if path.is_file():
            read += 1
            assert HOST_ENV not in path.read_text(encoding="utf-8", errors="replace"), path
    assert read > 2
