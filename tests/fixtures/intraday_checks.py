"""Row builders for the market_data_intraday checks (FEAT-DATA-001).

``market_data_intraday`` holds two timestamp conventions (CLAUDE.md 3.9): true
UTC instants, and legacy Eastern wall time stamped as UTC. These builders make
stored rows in either convention, or in both at once, from the naive Eastern
minutes a session holds, so a test states what a session IS and how it was
stored, and the check under test has to work out the rest.

Only what ``lib/eastern_time.py`` has on ``main`` is imported here, so a test
that uses this module can be run against ``main`` to show it is red there.
"""
from __future__ import annotations

import pandas as pd

from lib.eastern_time import eastern_index_to_utc

#: An insert time before the writers converted: proves nothing about a row.
OLD = pd.Timestamp("2026-02-23 02:40", tz="UTC")
#: An insert time after every writer converted: the row is a true instant.
NEW = pd.Timestamp("2026-11-20 12:00", tz="UTC")


def et_minutes(day: str, start: str, end: str) -> pd.DatetimeIndex:
    """Naive Eastern minutes of *day* from *start* to *end*, both included."""
    return pd.date_range(f"{day} {start}", f"{day} {end}", freq="min")


def store(naive_et: pd.DatetimeIndex, how: str) -> pd.DatetimeIndex:
    """The stored ``ts`` (aware UTC) of naive Eastern minutes.

    ``"true"`` converts them; ``"label"`` stamps the same clock reading as UTC,
    as the legacy writers did; ``"both"`` is the union of the two, one entry
    per key, as the table holds where both writers ran.
    """
    naive_et = pd.DatetimeIndex(naive_et)
    true = eastern_index_to_utc(naive_et)
    label = naive_et.tz_localize("UTC")
    if how == "true":
        return true
    if how == "label":
        return label
    if how == "both":
        return true.union(label)
    raise ValueError(f"unknown storage {how!r}")


def session_bars(day: str, *, start: str = "04:00", end: str = "20:00",
                 spike: bool = True, day_high: float = 600.0,
                 day_low: float = 590.0, f_high: float = 1.0,
                 f_low: float = 1.0) -> pd.DataFrame:
    """One session's 1-min bars: ``bar`` (naive Eastern minute), ``high``,
    ``low``, ``volume``.

    Every bar sits at the midpoint of *day_high* and *day_low*, except the
    10:17 bar, whose high is ``day_high * f_high``, and the 11:42 bar, whose
    low is ``day_low * f_low``: the session's extremes are two known minutes,
    so a reader that puts rows on the wrong minute loses them. Volume is 1000,
    and 20000 from 09:30 to 09:59 when *spike*, as a stored session's open is.
    """
    bar = et_minutes(day, start, end)
    mid = (day_high + day_low) / 2
    frame = pd.DataFrame({"bar": bar, "high": mid, "low": mid, "volume": 1000})
    clock = bar.strftime("%H:%M")
    frame.loc[clock == "10:17", "high"] = day_high * f_high
    frame.loc[clock == "11:42", "low"] = day_low * f_low
    if spike:
        frame.loc[(clock >= "09:30") & (clock <= "09:59"), "volume"] = 20000
    return frame


def stored(frame: pd.DataFrame, how: str = "true", *, shared: str = "true",
           inserted=OLD) -> pd.DataFrame:
    """*frame* (from :func:`session_bars`) as stored rows: adds ``ts`` and
    ``inserted_at``.

    For ``"both"`` the result holds one row per ``ts``, as the table does:
    where the two conventions meet on a key, the *shared* copy's values are
    kept (``"true"`` or ``"label"``).
    """
    if shared not in ("true", "label"):
        raise ValueError(f"unknown shared copy {shared!r}")
    if how in ("true", "label"):
        out = frame.assign(ts=store(frame["bar"], how))
    elif how == "both":
        first, second = ("true", "label") if shared == "true" else ("label", "true")
        out = pd.concat([frame.assign(ts=store(frame["bar"], first)),
                         frame.assign(ts=store(frame["bar"], second))],
                        ignore_index=True)
        out = out.drop_duplicates("ts", keep="first")
    else:
        raise ValueError(f"unknown storage {how!r}")
    out = out.sort_values("ts").reset_index(drop=True)
    out["inserted_at"] = inserted
    return out
