"""The bar flag pass over the stored 1-minute bars of SPY, QQQ and IWM
(FEAT-DATA-001).

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 3).

``flag_months`` judges each (ticker, month) with ``lib.bar_prints``: one
transaction on one connection a ticker-month, one read of the month window
widened by seven days on each side, proof that every row read is a true
instant, the rule over the whole read, and the flags inside the month window
labelled regular or extended from the exchange's calendar.

With ``commit`` the transaction issues four statements, in this order: the
lock timeout with the isolation read back, the advisory lock of the
(ticker, month) in a statement of its own, the read, and one write that
replaces the month's flags and upserts its coverage row. The lock is held
from before the read until the write commits, and a month replace takes the
same key before it touches a bar (issue #1982), so a replace never commits
between the read and the write. A statement's snapshot is taken when it
starts, so the lock is never taken inside the read's own statement.

It reads ``market_data_intraday`` and never writes it: no bar is changed,
deleted or filled. It writes only ``intraday_bar_flags`` and
``intraday_bar_flag_coverage``. Nothing is caught here (CLAUDE.md 3.7): a
failed read or write raises with its own exception and never comes back as
an empty frame. A zone changes only through ``lib/eastern_time.py``
(CLAUDE.md 3.9).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, datetime, timedelta
from typing import Sequence

import numpy as np
import pandas as pd

from gcp import bar_recompute, database
from lib import bar_prints
from lib.eastern_time import (
    intraday_month_window,
    market_date,
    session_schedule,
    utc_now,
)

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

# How long the pass waits for a month's lock (spec Design 3, step 1).
LOCK_TIMEOUT = "120s"
CONFIG_SQL = (
    f"SELECT set_config('lock_timeout', '{LOCK_TIMEOUT}', true), "
    "current_setting('transaction_isolation')"
)
LOCK_SQL = "SELECT pg_advisory_xact_lock(:k)"

# The coverage rows of the rule version over a run's months, read once a
# ticker: what the last pass judged, to compare with what this pass reads.
COVERAGE_SQL = (
    "SELECT month, checked_at, session_sha256 FROM intraday_bar_flag_coverage "
    "WHERE ticker = :t AND interval = '1min' AND rule_version = :v "
    "AND ts >= :first AND ts <= :last"
)

_PARTS = ("regular", "extended")
_SIDES = ("high", "low")
_FLAG_VALUES = ("observed", "reference", "bound", "scale", "excess_bp")
_JSON_PARAMS = ("flags", "params", "bars_basis", "session_sha256", "code_version")

_WRITE_MONTH_SQL = """
WITH new_flags AS (
    SELECT f.ts, f.side, f.print_kind, f.session_part,
           f.observed, f.reference, f.bound, f.scale, f.excess_bp
    FROM jsonb_to_recordset(:flags) AS f(
        ts TIMESTAMPTZ, side TEXT, print_kind TEXT, session_part TEXT,
        observed DOUBLE PRECISION, reference DOUBLE PRECISION, bound DOUBLE PRECISION,
        scale DOUBLE PRECISION, excess_bp DOUBLE PRECISION)
),
stale AS (
    DELETE FROM intraday_bar_flags AS old
    WHERE old.ticker = :t AND old.interval = '1min' AND old.rule_version = :v
      AND old.ts >= :m_start AND old.ts < :m_end
      AND NOT EXISTS (
          SELECT 1 FROM new_flags AS n WHERE n.ts = old.ts AND n.side = old.side)
    RETURNING 1
),
upserted AS (
    INSERT INTO intraday_bar_flags (
        ticker, interval, ts, side, rule_version, print_kind, session_part,
        observed, reference, bound, scale, excess_bp,
        read_start, read_end, detected_at, checked_at, run_id)
    SELECT :t, '1min', n.ts, n.side, :v, n.print_kind, n.session_part,
           n.observed, n.reference, n.bound, n.scale, n.excess_bp,
           :read_start, :read_end, :now, :now, :run_id
    FROM new_flags AS n
    ON CONFLICT (ticker, interval, ts, side, rule_version) DO UPDATE SET
        print_kind = EXCLUDED.print_kind,
        session_part = EXCLUDED.session_part,
        observed = EXCLUDED.observed,
        reference = EXCLUDED.reference,
        bound = EXCLUDED.bound,
        scale = EXCLUDED.scale,
        excess_bp = EXCLUDED.excess_bp,
        read_start = EXCLUDED.read_start,
        read_end = EXCLUDED.read_end,
        checked_at = EXCLUDED.checked_at,
        run_id = EXCLUDED.run_id
    RETURNING (xmax = 0) AS inserted
),
covered AS (
    INSERT INTO intraday_bar_flag_coverage (
        ticker, interval, ts, rule_version, month, read_start, read_end, params,
        bars_in_month, bars_judged, first_judged_ts, last_judged_ts,
        flags_regular_high, flags_regular_low, flags_extended_high, flags_extended_low,
        bars_basis, session_sha256, code_version, run_id, checked_at)
    VALUES (
        :t, '1min', :m_start, :v, :month, :read_start, :read_end, :params,
        :bars_in_month, :bars_judged,
        CAST(:first_judged_ts AS TIMESTAMPTZ), CAST(:last_judged_ts AS TIMESTAMPTZ),
        :flags_regular_high, :flags_regular_low, :flags_extended_high, :flags_extended_low,
        :bars_basis, :session_sha256, :code_version, :run_id, :now)
    ON CONFLICT (ticker, interval, ts, rule_version) DO UPDATE SET
        month = EXCLUDED.month,
        read_start = EXCLUDED.read_start,
        read_end = EXCLUDED.read_end,
        params = EXCLUDED.params,
        bars_in_month = EXCLUDED.bars_in_month,
        bars_judged = EXCLUDED.bars_judged,
        first_judged_ts = EXCLUDED.first_judged_ts,
        last_judged_ts = EXCLUDED.last_judged_ts,
        flags_regular_high = EXCLUDED.flags_regular_high,
        flags_regular_low = EXCLUDED.flags_regular_low,
        flags_extended_high = EXCLUDED.flags_extended_high,
        flags_extended_low = EXCLUDED.flags_extended_low,
        bars_basis = EXCLUDED.bars_basis,
        session_sha256 = EXCLUDED.session_sha256,
        code_version = EXCLUDED.code_version,
        run_id = EXCLUDED.run_id,
        checked_at = EXCLUDED.checked_at
    RETURNING 1
)
SELECT (SELECT count(*) FROM stale) AS deleted,
       (SELECT count(*) FROM upserted WHERE inserted) AS inserted,
       (SELECT count(*) FROM upserted WHERE NOT inserted) AS updated
""".strip()


def flag_lock_key(ticker: str, month: tuple[int, int]) -> int:
    """The advisory lock key of (ticker, month): the first 8 bytes of the
    sha256 of ``intraday_bar_flags:<ticker>:1min:<YYYY-MM>`` as a signed
    big-endian 64-bit integer. Stable across processes and releases; the
    pass and a replace of the month both take it."""
    name = f"intraday_bar_flags:{ticker}:1min:{month[0]:04d}-{month[1]:02d}"
    return int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big", signed=True)


def write_month_sql() -> str:
    """The one write statement of a ticker-month.

    Data-modifying CTEs over one snapshot: delete the flags of the ticker,
    month window and rule version that are not in the new set; upsert the new
    set, an update keeping ``detected_at``; upsert the coverage row. It
    returns the flags deleted, inserted and updated. The new set is one JSONB
    parameter, so the statement count does not grow with the flags, and an
    empty set runs the same statement.
    """
    return _WRITE_MONTH_SQL


def read_window(month: tuple[int, int]) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` the pass reads for *month*: its month window
    widened by READ_MARGIN on each side."""
    start, end = intraday_month_window(*month)
    return start - READ_MARGIN, end + READ_MARGIN


def flag_months_overlapping(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """The months whose read window overlaps ``[start, end)``, ascending.

    A month's flags and coverage rest on every bar of its read window
    (``read_window``), so these are the months a swap of ``[start, end)``
    invalidates: the predicate is the one of the replace's span clear,
    ``read_start < end AND read_end > start``. A replace takes the lock of
    each before it touches a bar (issue #1982). An empty span overlaps
    nothing.
    """
    for bound in (start, end):
        if getattr(bound, "tzinfo", None) is None:
            raise ValueError("flag_months_overlapping: start and end must be tz-aware")
    if start >= end:
        return []
    # A read window reaches READ_MARGIN past its month window, and a month
    # window starts within hours of the first of its month: one calendar
    # month of slack on each side holds every month that can overlap.
    low = start - READ_MARGIN
    high = end + READ_MARGIN
    year, month = (low.year - 1, 12) if low.month == 1 else (low.year, low.month - 1)
    last = (high.year + 1, 1) if high.month == 12 else (high.year, high.month + 1)
    months = []
    while (year, month) <= last:
        read_start, read_end = read_window((year, month))
        if read_start < end and read_end > start:
            months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


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


def session_digests(bars: pd.DataFrame) -> dict[str, str]:
    """Eastern date (ISO) to the ``bars_basis`` sha256 of that date's rows,
    over every row read, in date order."""
    if len(bars) == 0:
        return {}
    # Eastern is a whole number of hours from UTC, so every instant of one
    # UTC hour falls on one Eastern date: one calendar conversion an hour
    # read, not one a bar.
    hours = bars["ts"].dt.floor("h")
    day_of = {hour: market_date(hour).isoformat() for hour in hours.unique()}
    days = hours.map(day_of).to_numpy()
    return {
        day: bar_recompute.bars_basis(rows)["sha256"]
        for day, rows in bars.groupby(days, sort=True)
    }


def _earlier_coverage(ticker: str, months: Sequence[tuple[int, int]]) -> dict:
    """(year, month) to (checked_at, session_sha256) of the coverage rows the
    rule version holds for *months* of *ticker*. One strict read: a failure
    raises, and an empty answer means no month was judged before."""
    import json  # noqa: PLC0415

    frame = database.query_to_dataframe_strict(COVERAGE_SQL, {
        "t": ticker,
        "v": bar_prints.RULE_VERSION,
        "first": intraday_month_window(*months[0])[0],
        "last": intraday_month_window(*months[-1])[0],
    })
    earlier = {}
    for row in frame.itertuples(index=False):
        digests = row.session_sha256
        if isinstance(digests, str):
            digests = json.loads(digests)
        earlier[(row.month.year, row.month.month)] = (row.checked_at, digests)
    return earlier


def _changed_sessions(earlier: dict[str, str], read: dict[str, str]) -> list[str]:
    """The dates the earlier pass judged whose rows this read holds
    differently or not at all. A date only the read holds was appended since
    and is not a change."""
    return sorted(day for day, sha in earlier.items() if read.get(day) != sha)


def _instant_or_none(value):
    return None if value is None else value.to_pydatetime()


def _write_month(conn, values: dict) -> tuple[int, int, int]:
    """Run the one write statement; (deleted, inserted, updated)."""
    import sqlalchemy  # noqa: PLC0415
    from sqlalchemy.dialects.postgresql import JSONB  # noqa: PLC0415

    statement = sqlalchemy.text(write_month_sql()).bindparams(
        *[sqlalchemy.bindparam(name, type_=JSONB) for name in _JSON_PARAMS])
    deleted, inserted, updated = conn.execute(statement, values).one()
    return int(deleted), int(inserted), int(updated)


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
    of a ticker in ascending order. With *commit* it issues four statements:
    the configuration, the lock, the read and the write. Without it the
    transaction holds the read alone and is rolled back. Once a ticker,
    before its first month, one strict read of the coverage rows of the run's
    months; a session whose rows differ from those the earlier pass judged is
    logged as ``BARS-CHANGED``. A ticker outside FLAG_TICKERS raises
    ValueError before any query. Nothing is caught: a failure raises out of
    the month it happened in, and the months already written stay written.
    """
    import sqlalchemy  # noqa: PLC0415

    tickers = tuple(tickers)
    months = sorted(tuple(month) for month in months)
    other = [ticker for ticker in tickers if ticker not in FLAG_TICKERS]
    if other:
        raise ValueError(
            f"bar flags are for {', '.join(FLAG_TICKERS)} only, not {', '.join(other)}")

    began = time.monotonic()
    now = now_utc if now_utc is not None else utc_now()
    run = bar_recompute.run_id()
    code = bar_recompute.code_version()
    engine = database.get_engine()
    total = len(tickers) * len(months)
    done = flagged = changed = 0
    for ticker in tickers:
        earlier = _earlier_coverage(ticker, months) if months else {}
        for month in months:
            start, end = read_window(month)
            m_start, m_end = intraday_month_window(*month)
            written = None
            with engine.connect() as conn:
                with conn.begin() as transaction:
                    if commit:
                        _timeout, isolation = conn.execute(sqlalchemy.text(CONFIG_SQL)).one()
                        if isolation != "read committed":
                            raise RuntimeError(
                                f"bar flags: the transaction isolation is {isolation!r}, "
                                "not 'read committed'; nothing was locked or written")
                        conn.execute(
                            sqlalchemy.text(LOCK_SQL),
                            {"k": flag_lock_key(ticker, month)}).fetchall()
                    bars = _read_bars(conn, ticker, start, end)
                    bar_recompute.require_proven(bars["ts"], bars["inserted_at"])
                    flags, counts = judge_month(bars, month)
                    digests = session_digests(bars)
                    if commit:
                        written = _write_month(conn, {
                            "t": ticker,
                            "v": bar_prints.RULE_VERSION,
                            "m_start": m_start,
                            "m_end": m_end,
                            "month": date(month[0], month[1], 1),
                            "read_start": start,
                            "read_end": end,
                            "now": now,
                            "run_id": run,
                            "flags": [
                                {"ts": row.ts.isoformat(), "side": row.side,
                                 "print_kind": row.print_kind,
                                 "session_part": row.session_part,
                                 **{name: float(getattr(row, name)) for name in _FLAG_VALUES}}
                                for row in flags.itertuples(index=False)
                            ],
                            "params": dict(bar_prints.PARAMS),
                            "bars_in_month": counts["bars_in_month"],
                            "bars_judged": counts["bars_judged"],
                            "first_judged_ts": _instant_or_none(counts["first_judged_ts"]),
                            "last_judged_ts": _instant_or_none(counts["last_judged_ts"]),
                            **{name: counts[name] for name in counts
                               if name.startswith("flags_")},
                            "bars_basis": bar_recompute.bars_basis(bars),
                            "session_sha256": digests,
                            "code_version": code,
                        })
                    else:
                        transaction.rollback()
            done += 1
            flagged += len(flags)
            if month in earlier:
                checked_at, judged_digests = earlier[month]
                sessions = _changed_sessions(judged_digests, digests)
                if sessions:
                    changed += 1
                    line = (f"BARS-CHANGED {ticker} {month[0]:04d}-{month[1]:02d} "
                            f"sessions={','.join(sessions)} since={checked_at.isoformat()}")
                    if written is not None:
                        line += f" inserted={written[1]} deleted={written[0]}"
                    log.warning("%s", line)
            log.info(
                "bar flags month: %s %04d-%02d judged=%d regular_high=%d regular_low=%d "
                "extended_high=%d extended_low=%d (%d/%d)",
                ticker, month[0], month[1], counts["bars_judged"],
                counts["flags_regular_high"], counts["flags_regular_low"],
                counts["flags_extended_high"], counts["flags_extended_low"], done, total)
    return {"months": done, "flags": flagged, "changed": changed,
            "seconds": time.monotonic() - began}
