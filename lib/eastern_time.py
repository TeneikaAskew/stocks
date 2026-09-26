"""The one place the trading platform's Eastern timezone is defined.

Eastern time is **America/New_York** -- a named, DST-correct IANA zone. It is
never a fixed offset (``EST`` / ``-05:00`` freezes the clock at winter time
through the summer) and never the backward-compatibility link ``US/Eastern``
(which is absent from slim tzdata images). Import :data:`ET` (a
``zoneinfo.ZoneInfo``) or :data:`ET_NAME` (the string, for the pandas and pytz
APIs that take a name) from here rather than constructing the zone locally, so
there is a single source of truth and the startup check below vouches for every
use of it at once.

This replaces the repository-wide source scanner that previously enforced the
same invariant by grepping every file: a single canonical helper plus a boot
assertion is a fixed target that cannot drift, where the scanner had to chase
every new way to spell a fixed offset.

It is also the one place a market timestamp changes zone. Storage is UTC
instants (``market_data_intraday.ts`` and every other TIMESTAMPTZ); vendor
bars arrive as naive Eastern wall time; display is naive Eastern. Convert at
those boundaries with the functions below, never with a hand-rolled
``tz_localize(None)`` or ``utc=True``: those relabel a clock reading instead
of converting it, which is how ``market_data_intraday`` came to hold Eastern
wall time stamped as UTC (CLAUDE.md 3.9).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import TypeAlias
from zoneinfo import ZoneInfo

#: The canonical Eastern zone name. Use it for the pandas / pytz string APIs
#: (``tz_convert(ET_NAME)``, ``pytz.timezone(ET_NAME)``).
ET_NAME = "America/New_York"

#: The canonical Eastern zone object. Use it wherever a ``tzinfo`` is wanted
#: (``datetime.now(ET)``, ``dt.astimezone(ET)``).
ET = ZoneInfo(ET_NAME)
UTC = timezone.utc

DateLike: TypeAlias = date | datetime


def require_aware(value: datetime, *, name: str = "timestamp") -> datetime:
    """Return *value* when it denotes an instant; reject ambiguous wall time."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def localize_assuming_utc(value: datetime) -> datetime:
    """Attach UTC to a deliberately naive UTC value.

    This function's explicit name is the required documentation at boundaries
    that emit naive UTC.  Already-aware values are rejected so callers cannot
    accidentally relabel an instant instead of converting it.
    """
    if value.tzinfo is not None:
        raise ValueError("value is already timezone-aware; use as_utc_instant")
    return value.replace(tzinfo=UTC)


def localize_assuming_eastern(
    value: datetime,
    *,
    fold: int | None = None,
) -> datetime:
    """Attach the market zone to an unambiguous naive Eastern wall time.

    Eastern clocks skip an hour each spring and repeat an hour each autumn.
    ``datetime.replace(tzinfo=...)`` accepts both impossible and ambiguous wall
    times without warning, so this boundary validates a UTC round trip.  A
    repeated wall time requires the caller to choose ``fold=0`` (the first
    occurrence) or ``fold=1`` (the second); ordinary times require no choice.
    """
    if value.tzinfo is not None:
        raise ValueError("value is already timezone-aware; use as_eastern_time")
    if fold not in (None, 0, 1):
        raise ValueError("fold must be 0, 1, or None")

    candidates = [value.replace(tzinfo=ET, fold=candidate) for candidate in (0, 1)]
    valid = [
        candidate
        for candidate in candidates
        if candidate.astimezone(UTC).astimezone(ET).replace(tzinfo=None) == value
    ]
    if not valid:
        raise ValueError(f"Eastern wall time does not exist: {value.isoformat()}")

    ambiguous = valid[0].utcoffset() != valid[-1].utcoffset()
    if ambiguous and fold is None:
        raise ValueError(
            f"Eastern wall time is ambiguous; specify fold=0 or fold=1: "
            f"{value.isoformat()}"
        )
    return candidates[0 if fold is None else fold]


def as_utc_instant(value: datetime) -> datetime:
    """Convert an aware timestamp to the canonical UTC representation."""
    return require_aware(value).astimezone(UTC)


def as_eastern_time(value: datetime) -> datetime:
    """Convert an aware instant to the exchange's Eastern wall clock."""
    return require_aware(value).astimezone(ET)


def market_date(value: DateLike) -> date:
    """Return a market date, converting instants to Eastern before truncation.

    A plain ``date`` is already a business-date value and is returned as-is.
    A ``datetime`` must be aware: silently guessing what a naive datetime means
    is the defect class this boundary exists to prevent.
    """
    if isinstance(value, datetime):
        return as_eastern_time(value).date()
    return value


def utc_now() -> datetime:
    """Return the current instant as an aware UTC datetime."""
    return datetime.now(UTC)


def eastern_now() -> datetime:
    """Return the current instant in the exchange's Eastern timezone."""
    return datetime.now(ET)


# -- pandas boundaries -------------------------------------------------------
#
# pandas is imported inside these functions so the many modules that only need
# ET / ET_NAME do not pay for it at import.


def eastern_index_to_utc(values):
    """Convert naive Eastern wall-clock stamps to aware UTC instants.

    For vendor bar timestamps (AlphaVantage intraday keys are naive Eastern
    wall time). Accepts a ``DatetimeIndex`` or a datetime ``Series`` and returns
    the same kind, tz-aware in UTC.

    Already-aware input is rejected rather than relabelled: an aware value is an
    instant, and dropping its zone would silently move it. A wall time that does
    not exist (spring-forward gap) or occurs twice (autumn repeat) raises too.
    Market bars never fall in 01:00-03:00 Eastern, so meeting one is a data
    error to surface, not something to guess about.
    """
    import pandas as pd

    if isinstance(values, pd.Series):
        idx = pd.DatetimeIndex(values)
        return pd.Series(eastern_index_to_utc(idx), index=values.index, name=values.name)
    idx = pd.DatetimeIndex(values)
    if idx.tz is not None:
        raise ValueError(
            "eastern_index_to_utc expects naive Eastern wall time; got an aware "
            f"index ({idx.tz}). Use .tz_convert('UTC') to convert an instant."
        )
    return idx.tz_localize(ET_NAME, ambiguous="raise", nonexistent="raise").tz_convert("UTC")


def utc_to_eastern_naive(values):
    """Convert aware instants to naive Eastern wall time, for display only.

    The inverse of :func:`eastern_index_to_utc`, for output boundaries whose
    contract is naive Eastern (the Charts API). Naive input is rejected: which
    zone it is in cannot be known here.
    """
    import pandas as pd

    if isinstance(values, pd.Series):
        idx = pd.DatetimeIndex(values)
        return pd.Series(utc_to_eastern_naive(idx), index=values.index, name=values.name)
    idx = pd.DatetimeIndex(values)
    if idx.tz is None:
        raise ValueError("utc_to_eastern_naive expects tz-aware instants; got a naive index")
    return idx.tz_convert(ET_NAME).tz_localize(None)  # tz-ok: converted first; this IS the display helper


# -- reading market_data_intraday across the convention migration ------------


def stored_intraday_to_eastern(ts, volume):
    """Naive-Eastern index for market_data_intraday rows, safe across the
    timestamp-convention migration (CLAUDE.md 3.9). Returns (naive-Eastern
    DatetimeIndex, boolean keep mask), one entry per input row.

    Used by the Charts API (platform/api/main.py) to read the table, and by the
    re-framing migration to count the distinct bars a month holds, so both
    agree on what the table contains.

    Until the re-framing migration finishes, a raw date's rows are either
    Eastern wall time stamped as UTC (the legacy writers) or true UTC (every
    writer from #1185 on). Converting all rows shifts the legacy ones 4-5 h;
    converting none shifts the new ones.

    AV bars span 04:00-20:00 Eastern (there is a bar AT 20:00), so some raw
    clock times belong to one convention only, in both seasons:
      raw 04:00-07:59         only Eastern labels (true UTC starts at 08:00Z)
      raw 20:01-01:00         only true UTC (the last label is raw 20:00)
    Such a row is read in its own convention wherever it sits. Every other row
    follows its raw date's verdict, decided by, in order:
      1. which exclusive region the date has rows in, if only one;
      2. the 09:30 ET open: the day's volume spike at raw label 09:30 and not
         at the converted 09:30 means labels, and the reverse means true UTC
         (the test that matched live prices in
         gcp/queries/classify_intraday_ts_convention.sql);
      3. the regular-session envelope: a legacy regular-session-only day sits
         at raw 09:30-16:00 and nowhere else, which true UTC never does (its
         RTH reaches past raw 16:00, its premarket starts at 08:00Z); a
         flat-volume legacy day (Codex #1185);
      4. otherwise convert: every writer's convention from now on.

    A row is dropped only when another row lands on the same Eastern minute:
    the one following its date's verdict wins over a straggler of the other
    convention, and then the one stored on its own date (raw date == Eastern
    date) wins. So stale duplicates left where both writers collided go, but
    the only copy of a bar, such as a true-UTC 20:00 ET spill in front of a
    legacy date, is kept (Codex #1185). After the migration this reduces to
    utc_to_eastern_naive with nothing dropped.
    """
    import numpy as np
    import pandas as pd

    inst = pd.DatetimeIndex(pd.to_datetime(ts))
    if inst.tz is None:
        inst = inst.tz_localize("UTC")  # tz-ok: pg8000 TIMESTAMPTZ in a UTC session
    inst = inst.tz_convert("UTC")
    raw = inst.tz_localize(None)  # tz-ok: the raw clock label, read per date below
    converted = utc_to_eastern_naive(inst)
    pos = range(len(inst))
    vol = pd.Series(pd.to_numeric(volume, errors="coerce").to_numpy(), index=pos)
    raw_min = pd.Series(raw.hour * 60 + raw.minute, index=pos)
    conv_min = pd.Series(converted.hour * 60 + converted.minute, index=pos)
    raw_date = pd.Series(raw.date, index=pos)
    conv_date = pd.Series(converted.date, index=pos)
    label_only = (raw_min >= 240) & (raw_min < 480)
    true_only = (raw_min > 1200) | (raw_min <= 60)
    as_label = pd.Series(False, index=pos)
    follows_verdict = pd.Series(True, index=pos)

    def spike(window: pd.Series, day: pd.Series) -> float:
        """Mean volume of an opening window over the day's median minute."""
        med = day.median()
        return float(window.mean() / med) if len(window) and med and med > 0 else 0.0

    for d, rows in raw_date.groupby(raw_date).groups.items():
        rows = pd.Index(rows)
        rm, v = raw_min[rows], vol[rows]
        lo, to = label_only[rows], true_only[rows]
        if lo.any() != to.any():
            verdict_label = bool(lo.any())
        else:
            label_spike = spike(v[(rm >= 570) & (rm < 600)], v)
            true_win = (conv_date[rows] == d) & (conv_min[rows] >= 570) & (conv_min[rows] < 600)
            true_spike = spike(v[true_win], v)
            if label_spike > 2 and label_spike > 1.5 * max(true_spike, 1.0):
                verdict_label = True
            elif true_spike > 2 and true_spike > 1.5 * max(label_spike, 1.0):
                verdict_label = False
            else:
                # A legacy regular-session-only day is raw 09:30-16:00 and
                # nothing else; true UTC would reach past raw 16:00 (RTH) or
                # start before 09:30 (premarket from 08:00Z).
                early = bool(((rm >= 570) & (rm < 810)).any())    # raw 09:30-13:29
                before = bool((rm < 570).any())                   # raw < 09:30
                late = bool(((rm > 960) & (rm <= 1260)).any())    # raw 16:01-21:00
                verdict_label = early and not before and not late
        row_label = lo | (~to & verdict_label)
        as_label[rows] = row_label
        follows_verdict[rows] = (row_label == verdict_label)

    out_idx = pd.DatetimeIndex(np.where(as_label.to_numpy(), raw.to_numpy(), converted.to_numpy()))
    own_date = pd.Series(raw_date.to_numpy() == out_idx.date, index=pos)
    # One row per Eastern minute: verdict-followers first, then own-date rows.
    rank = pd.DataFrame({"t": out_idx, "f": ~follows_verdict, "o": ~own_date}, index=pos)
    keep = ~rank.sort_values(["t", "f", "o"], kind="stable").duplicated("t").reindex(pos)
    return out_idx, keep.to_numpy()


# -- market dates and session windows ----------------------------------------


def market_today() -> date:
    """Today's date on the exchange's clock.

    ``date.today()`` and ``CURRENT_DATE`` are the container's / database's
    date, which is UTC here: from 20:00 Eastern (19:00 in winter) onward they
    are already tomorrow.
    """
    return eastern_now().date()


def eastern_bounds_utc(day: date, start: time, end: time) -> tuple[datetime, datetime]:
    """UTC instants for ``[start, end)`` Eastern wall time on market date *day*.

    DST-aware: 09:30 Eastern is 13:30Z in summer and 14:30Z in winter. Use it to
    query UTC-stamped bars by an Eastern session window, e.g. premarket
    ``(time(4), time(9, 30))`` or the regular session ``(time(9, 30), time(16))``.
    """
    return (
        as_utc_instant(localize_assuming_eastern(datetime.combine(day, start))),
        as_utc_instant(localize_assuming_eastern(datetime.combine(day, end))),
    )


# -- SQL fragments -------------------------------------------------------------
#
# Postgres here runs with TimeZone=UTC, so DATE(ts), ts::date and CURRENT_DATE
# are UTC dates. These return the Eastern equivalents as SQL text so the
# framing lives in one place too.

_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def market_date_sql(column: str) -> str:
    """SQL for the Eastern market date of a TIMESTAMPTZ *column*.

    ``market_date_sql("ts")`` -> ``(ts AT TIME ZONE 'America/New_York')::date``.
    *column* must be a plain (optionally table-qualified) identifier; this is
    interpolated into SQL, so anything else is refused.
    """
    if not _SQL_IDENT.match(column):
        raise ValueError(f"not a plain SQL column identifier: {column!r}")
    return f"({column} AT TIME ZONE '{ET_NAME}')::date"


def market_today_sql() -> str:
    """SQL for today's Eastern date (the ``CURRENT_DATE`` replacement)."""
    return f"(now() AT TIME ZONE '{ET_NAME}')::date"


def verify_eastern_is_dst_correct() -> None:
    """Raise if the loaded ``America/New_York`` is not DST-correct.

    ``America/New_York`` is UTC-05:00 in January and UTC-04:00 in July. A slim
    container image with incomplete tzdata, or a zone frozen at a fixed offset,
    fails one of those and would silently shift every Eastern time the app
    computes. Checking it once at import is the cheap boot assertion that keeps
    that failure loud instead of silent.
    """
    jan = datetime(2026, 1, 15, 12, tzinfo=ET).utcoffset()
    jul = datetime(2026, 7, 15, 12, tzinfo=ET).utcoffset()
    if jan != timedelta(hours=-5) or jul != timedelta(hours=-4):
        raise RuntimeError(
            "America/New_York is not DST-correct -- tzdata is missing or the "
            f"zone is frozen (January offset {jan}, July offset {jul}; "
            "expected -05:00 and -04:00). Install the `tzdata` package or the "
            "system zoneinfo database."
        )


verify_eastern_is_dst_correct()
