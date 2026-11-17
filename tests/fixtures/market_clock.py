"""One frozen instant for a test, and a host clock that refuses to answer.

FEAT-DATA-001, stage 1 of the market-time sweep. Deployed code runs in
containers whose clock is UTC, so ``date.today()`` there is tomorrow from
19:00 Eastern in winter (20:00 in summer) until midnight Eastern. A test of
"this code takes today from the exchange's clock" therefore needs two things
at once:

* the instant is frozen at the one seam every helper reads,
  ``lib.eastern_time.eastern_now`` / ``utc_now``, so ``market_today()`` and
  everything built on it answers for that instant; and
* the host clock is forbidden in the module under test, so a site that still
  reads it fails the test instead of passing on the test machine's clock.

Usage::

    from tests.fixtures.market_clock import DAYTIME, freeze_market_clock

    def test_x(monkeypatch):
        freeze_market_clock(monkeypatch, "2026-11-09T00:00:30Z", module_under_test)
        ...

``MARKET_CLOCK_HOST=utc`` is for the record run on unmodified code only: a
guarded name then answers as a UTC container does, which shows the value the
old code gives in the evening. No committed file sets it; CI runs the default,
which raises (``tests/lib/test_market_clock_fixture.py`` pins that).
"""
from __future__ import annotations

import datetime as _datetime_module
import linecache
import os
import sys
from datetime import date as _RealDate
from datetime import datetime as _RealDatetime
from datetime import timezone
from types import ModuleType

HOST_ENV = "MARKET_CLOCK_HOST"

#: Thursday 2026-11-12 10:00 EST: the host's UTC date and the exchange's agree.
DAYTIME = "2026-11-12T15:00:00Z"

#: Each instant with the Eastern date at it.
STANDARD_INSTANTS: tuple[tuple[str, _RealDate], ...] = (
    ("2026-11-14T01:30:00Z", _RealDate(2026, 11, 13)),  # Friday 20:30 EST: UTC is already Saturday
    ("2026-07-10T23:30:00Z", _RealDate(2026, 7, 10)),   # Friday 19:30 EDT: the host date agrees
    ("2026-07-11T00:30:00Z", _RealDate(2026, 7, 10)),   # Friday 20:30 EDT: UTC is already Saturday
    (DAYTIME, _RealDate(2026, 11, 12)),
)


class HostClockRead(BaseException):
    """The code under test read the container's clock for a date or a time.

    A ``BaseException`` on purpose: several functions under test wrap their
    body in ``except Exception`` (fetchers, API handlers), which would swallow
    an ordinary exception and let the test pass on unmodified code.
    """


class _AnswersAsTheRealClass(type):
    """``isinstance`` / ``issubclass`` against a guard answer as the real class does.

    Code under test checks ``isinstance(value, datetime)`` on values made
    elsewhere (pandas, a driver, another module); replacing the module's name
    with a subclass must not change those answers.
    """

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls.__mro__[1])

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls.__mro__[1])


def _parse(instant: str) -> _RealDatetime:
    frozen = _RealDatetime.fromisoformat(instant.replace("Z", "+00:00"))
    if frozen.tzinfo is None:
        raise ValueError(f"{instant!r} names no zone; write the instant in UTC with a Z")
    return frozen.astimezone(timezone.utc)


def freeze_market_clock(
    monkeypatch,
    instant: str,
    *modules: ModuleType,
    stdlib: bool = False,
    pandas: bool = False,
    allow_instants: tuple[str, ...] = (),
) -> _RealDatetime:
    """Freeze the market clock at *instant* and forbid the host clock in *modules*.

    Returns the frozen instant, aware, in UTC.

    * ``lib.eastern_time.eastern_now`` and ``utc_now`` return the instant.
    * In each module passed, every module-level name bound to the real
      ``datetime.datetime`` or ``datetime.date`` becomes a guard subclass:
      ``today()``, ``utcnow()`` and ``now()`` with no zone are host reads and
      raise :class:`HostClockRead`; ``now(tz)`` returns the frozen instant in
      that zone; everything else is inherited.
    * ``stdlib=True`` also guards the two classes on the ``datetime`` module,
      for code that imports them inside a function.
    * ``pandas=True`` guards ``pd.Timestamp.now`` / ``utcnow`` / ``today``.
    * ``allow_instants`` holds call texts (``"datetime.now().isoformat()"``).
      A host read whose calling source line contains one returns the frozen
      instant as naive UTC. It is for an instant that shares a function with a
      date read under test, and nothing else.
    """
    frozen = _parse(instant)
    host = os.environ.get(HOST_ENV, "raise")
    if host not in ("raise", "utc"):
        raise ValueError(f"{HOST_ENV}={host!r}: the only value it takes is 'utc'")
    naive_utc = frozen.replace(tzinfo=None)
    allowed = tuple(allow_instants)

    def host_read(what: str, depth: int) -> _RealDatetime:
        """What a zone-less read returns: the UTC container's answer, or a refusal."""
        if host == "utc":
            return naive_utc
        caller = sys._getframe(depth)
        where = f"{caller.f_code.co_filename}:{caller.f_lineno}"
        line = linecache.getline(caller.f_code.co_filename, caller.f_lineno)
        if any(text in line for text in allowed):
            return naive_utc
        raise HostClockRead(
            f"{what} reads the container's clock at {where}; "
            "take the date or the instant from lib.eastern_time"
        )

    class GuardDatetime(_RealDatetime, metaclass=_AnswersAsTheRealClass):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return frozen.astimezone(tz)
            return host_read("datetime.now()", 2)

        @classmethod
        def utcnow(cls):
            return host_read("datetime.utcnow()", 2)

        @classmethod
        def today(cls):
            return host_read("datetime.today()", 2)

    class GuardDate(_RealDate, metaclass=_AnswersAsTheRealClass):
        @classmethod
        def today(cls):
            got = host_read("date.today()", 2)
            return _RealDate(got.year, got.month, got.day)

    import lib.eastern_time as eastern_time

    monkeypatch.setattr(eastern_time, "eastern_now", lambda: frozen.astimezone(eastern_time.ET))
    monkeypatch.setattr(eastern_time, "utc_now", lambda: frozen)

    for module in modules:
        for name, value in list(vars(module).items()):
            if value is _RealDatetime:
                monkeypatch.setattr(module, name, GuardDatetime)
            elif value is _RealDate:
                monkeypatch.setattr(module, name, GuardDate)
            elif value is _datetime_module and not stdlib:
                raise ValueError(
                    f"{module.__name__}.{name} is the datetime module itself; pass stdlib=True"
                )

    if stdlib:
        monkeypatch.setattr(_datetime_module, "datetime", GuardDatetime)
        monkeypatch.setattr(_datetime_module, "date", GuardDate)

    if pandas:
        import pandas as pd

        def _timestamp_now(tz=None):
            if tz is not None:
                return pd.Timestamp(frozen).tz_convert(tz)
            return pd.Timestamp(host_read("pd.Timestamp.now()", 2))

        def _timestamp_today(tz=None):
            if tz is not None:
                return pd.Timestamp(frozen).tz_convert(tz)
            return pd.Timestamp(host_read("pd.Timestamp.today()", 2))

        def _timestamp_utcnow():
            return pd.Timestamp(host_read("pd.Timestamp.utcnow()", 2), tz="UTC")

        monkeypatch.setattr(pd.Timestamp, "now", staticmethod(_timestamp_now))
        monkeypatch.setattr(pd.Timestamp, "today", staticmethod(_timestamp_today))
        monkeypatch.setattr(pd.Timestamp, "utcnow", staticmethod(_timestamp_utcnow))

    return frozen
