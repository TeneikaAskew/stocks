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
