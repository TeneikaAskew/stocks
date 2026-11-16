"""The bar flag pass over the stored 1-minute bars of SPY, QQQ and IWM
(FEAT-DATA-001).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 3).

``flag_months`` judges each (ticker, month) with ``lib.bar_prints``: one
transaction on one connection a ticker-month, one read of the month window
widened by seven days on each side, proof that every row read is a true
instant, the rule over the whole read, and the flags inside the month window
labelled regular or extended from the exchange's calendar.

It reads ``market_data_intraday`` and never writes it: no bar is changed,
deleted or filled. Nothing is caught here (CLAUDE.md 3.7): a failed read
raises with its own exception and never comes back as an empty frame.
A zone changes only through ``lib/eastern_time.py`` (CLAUDE.md 3.9).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Sequence

import numpy as np
import pandas as pd

from gcp import bar_recompute, database
from lib import bar_prints
from lib.eastern_time import intraday_month_window, market_date, session_schedule

log = logging.getLogger(__name__)

FLAG_TICKERS = ("SPY", "QQQ", "IWM")

# The read reaches this far past each end of the month window, so every bar of
# the month has its neighbours and its scale bars (spec Design 3, step 1).
READ_MARGIN = timedelta(days=7)

READ_COLUMNS = ("ts", "open", "high", "low", "close", "volume", "inserted_at")
READ_SQL = (
    "SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday "
    "WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts"
)

_PARTS = ("regular", "extended")
_SIDES = ("high", "low")


def read_window(month: tuple[int, int]) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` the pass reads for *month*: its month window
    widened by READ_MARGIN on each side."""
    start, end = intraday_month_window(*month)
    return start - READ_MARGIN, end + READ_MARGIN


def session_part(ts) -> np.ndarray:
    """``'regular'`` or ``'extended'`` for each aware instant of *ts*.

    Regular is ``[market_open, market_close)`` of a session of the exchange's
    calendar, so the open is inside and the close is not; half days close
    early, and a weekend or a holiday has no session. One calendar read for
    the whole of *ts*.
    """
    at = pd.DatetimeIndex(ts)
    parts = np.full(len(at), "extended", dtype=object)
    if len(at) == 0:
        return parts
    schedule = session_schedule(market_date(at.min()), market_date(at.max()))
    if schedule.empty:
        return parts
    opens = pd.DatetimeIndex(schedule["market_open"])
    closes = pd.DatetimeIndex(schedule["market_close"])
    # The last session that opened at or before each instant, if any.
    session = opens.searchsorted(at, side="right") - 1
    inside = (session >= 0) & np.asarray(at < closes[np.clip(session, 0, None)])
    parts[inside] = "regular"
    return parts


def judge_month(bars: pd.DataFrame, month: tuple[int, int]) -> tuple[pd.DataFrame, dict]:
    """The flags of *month* and its counts, from the rows read for it.

    *bars* is the whole read, margins included: the rule runs over all of it
    and only the flags whose ``ts`` lies in the month window are kept, each
    with its ``session_part``. The counts are of the month window alone:
    ``bars_in_month``, ``bars_judged``, ``first_judged_ts``,
    ``last_judged_ts`` (None when no bar was judged) and the four
    ``flags_<part>_<side>``.
    """
    start, end = intraday_month_window(*month)
    flags, judged = bar_prints.isolated_prints(bars)
    in_month = ((bars["ts"] >= start) & (bars["ts"] < end)).to_numpy(dtype=bool)
    judged_ts = bars["ts"][in_month & judged]

    kept = flags[(flags["ts"] >= start) & (flags["ts"] < end)].reset_index(drop=True)
    kept["session_part"] = session_part(kept["ts"])

    counts = {
        "bars_in_month": int(in_month.sum()),
        "bars_judged": int(len(judged_ts)),
        "first_judged_ts": judged_ts.iloc[0] if len(judged_ts) else None,
        "last_judged_ts": judged_ts.iloc[-1] if len(judged_ts) else None,
    }
    for part in _PARTS:
        for side in _SIDES:
            counts[f"flags_{part}_{side}"] = int(
                ((kept["session_part"] == part) & (kept["side"] == side)).sum())
    return kept, counts


def _read_bars(conn, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    """The stored rows of *ticker* in ``[start, end)``, on the transaction's
    own connection. Raises on any failure; an empty frame means the query ran
    and the window holds no row."""
    import sqlalchemy  # noqa: PLC0415

    rows = conn.execute(
        sqlalchemy.text(READ_SQL), {"t": ticker, "start": start, "end": end}).fetchall()
    bars = pd.DataFrame([tuple(row) for row in rows], columns=list(READ_COLUMNS))
    for name in ("ts", "inserted_at"):
        instants = pd.DatetimeIndex(bars[name])
        if instants.tz is None:
            if len(instants):
                raise ValueError(
                    f"market_data_intraday.{name} came back without a zone for {ticker}")
            instants = pd.DatetimeIndex([], tz="UTC")
        bars[name] = instants
    for name in ("open", "high", "low", "close"):
        bars[name] = bars[name].astype(float)
    return bars


def flag_months(tickers: Sequence[str], months: Sequence[tuple[int, int]], *,
                commit: bool, now_utc: datetime | None = None) -> dict:
    """Judge each (ticker, month); with commit, write its flags and coverage.
    Returns {'months', 'flags', 'changed', 'seconds'}.

    Each ticker-month runs in one transaction on one connection, the months
    of a ticker in ascending order. Without *commit* the transaction holds
    the read alone and is rolled back. A ticker outside FLAG_TICKERS raises
    ValueError before any query. Nothing is caught: a failure raises out of
    the month it happened in, and the months before it stay as they were
    left.
    """
    tickers = tuple(tickers)
    months = sorted(tuple(month) for month in months)
    other = [ticker for ticker in tickers if ticker not in FLAG_TICKERS]
    if other:
        raise ValueError(
            f"bar flags are for {', '.join(FLAG_TICKERS)} only, not {', '.join(other)}")

    began = time.monotonic()
    engine = database.get_engine()
    total = len(tickers) * len(months)
    done = flagged = changed = 0
    for ticker in tickers:
        for month in months:
            start, end = read_window(month)
            with engine.connect() as conn:
                with conn.begin() as transaction:
                    bars = _read_bars(conn, ticker, start, end)
                    bar_recompute.require_proven(bars["ts"], bars["inserted_at"])
                    flags, counts = judge_month(bars, month)
                    if not commit:
                        transaction.rollback()
            done += 1
            flagged += len(flags)
            log.info(
                "bar flags month: %s %04d-%02d judged=%d regular_high=%d regular_low=%d "
                "extended_high=%d extended_low=%d (%d/%d)",
                ticker, month[0], month[1], counts["bars_judged"],
                counts["flags_regular_high"], counts["flags_regular_low"],
                counts["flags_extended_high"], counts["flags_extended_low"], done, total)
    return {"months": done, "flags": flagged, "changed": changed,
            "seconds": time.monotonic() - began}
