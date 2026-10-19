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
import threading
from bisect import bisect_left, bisect_right
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, NamedTuple, TypeAlias
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    import pandas as pd

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


# First raw date written only by the true-UTC writers (#1185 deployed
# 2026-09-26, before the next session). From here on a row's convention is
# known, not inferred: the heuristics below would otherwise have to read a
# live partial session (premarket only, or flat before the day fills), whose
# shape a legacy one can share (Codex P2 x2 on #1185). Must never be earlier
# than the first session after the writer deploy.
TRUE_UTC_FROM = date(2026, 9, 28)


def stored_intraday_to_eastern(ts, volume):
    """Naive-Eastern index for market_data_intraday rows, safe across the
    timestamp-convention migration (CLAUDE.md 3.9). Returns (naive-Eastern
    DatetimeIndex, boolean keep mask), one entry per input row.

    Used by the Charts API (platform/api/main.py) to read the table, and by the
    re-framing migration to count the distinct bars a month holds, so both
    agree on what the table contains.

    Raw dates from TRUE_UTC_FROM on are true UTC by construction and read as
    such. Until the re-framing migration finishes, an earlier raw date's rows
    are either
    Eastern wall time stamped as UTC (the legacy writers) or true UTC (every
    writer from #1185 on). Converting all rows shifts the legacy ones 4-5 h;
    converting none shifts the new ones.

    AV bars span 04:00-20:00 Eastern (there is a bar AT 20:00), so some raw
    clock times belong to one convention only, in both seasons:
      raw 04:00 up to the date's true-UTC start
                              only Eastern labels (true UTC starts at 04:00 ET:
                              08:00Z under EDT, 09:00Z under EST, so raw 08:xx
                              is a label on a winter date, Codex #1185)
      raw 20:01-01:00         only true UTC (the last label is raw 20:00)
    Such a row is read in its own convention wherever it sits. Every other row
    follows its raw date's verdict, decided by, in order:
      1. which exclusive region the date has rows in, if only one;
      2. the 09:30 ET open: the day's volume spike at raw label 09:30 and not
         at the converted 09:30 means labels, and the reverse means true UTC
         (the test that matched live prices in
         gcp/queries/classify_intraday_ts_convention.sql);
      3. regular-session coverage: each reading predicts the 390 minutes of
         09:30-16:00 ET at different raw times; labels win if their reading
         finds at least half of them and half again as many as the true-UTC
         reading (a flat-volume legacy day, with or without after-hours bars,
         Codex #1185);
         A date whose true reading lies wholly in 04:00-09:29 ET is a
         premarket snapshot and skips this test (step 4);
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
    # Where true UTC begins on each raw date: 04:00 ET in UTC minutes, 480
    # under EDT and 540 under EST. Taken from the date's own offset (at noon,
    # clear of the 02:00 Sunday transitions, and markets are shut on Sundays).
    first_true = {d: 240 - int(pd.Timestamp(d).replace(hour=12).tz_localize(ET_NAME)
                               .utcoffset().total_seconds() // 60)
                  for d in raw_date.unique()}
    label_only = (raw_min >= 240) & (raw_min < raw_date.map(first_true))
    true_only = (raw_min > 1200) | (raw_min <= 60)
    as_label = pd.Series(False, index=pos)
    follows_verdict = pd.Series(True, index=pos)

    def spike(window: pd.Series, day: pd.Series) -> float:
        """Mean volume of an opening window over the day's median minute."""
        med = day.median()
        return float(window.mean() / med) if len(window) and med and med > 0 else 0.0

    for d, rows in raw_date.groupby(raw_date).groups.items():
        rows = pd.Index(rows)
        if d >= TRUE_UTC_FROM:
            # Written after every legacy writer was retired: true UTC by
            # construction, whatever its shape. A live session (premarket
            # only, or partway through the day) needs no inference.
            continue
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
                # Regular-session coverage: each reading predicts the 390
                # minutes of 09:30-16:00 ET at different raw times. The reading
                # that finds the fuller regular session is the one the date was
                # written in. A premarket-only day fills neither, and stays on
                # the default (Codex #1185: RTH plus sparse post-market reads
                # as labels, which a clock envelope alone could not tell).
                cm = conv_min[rows]
                # A true-UTC premarket snapshot (today's session before the
                # open, or a retained 04:00-09:29 ET slice) sits at raw
                # 08:00-13:29 EDT / 09:00-14:29 EST, where the labels reading
                # sees most of a regular session. When the true reading lies
                # wholly in premarket, keep the convert default: from #1185
                # on every writer produces exactly this shape each morning
                # (Codex P2 on #1185). Legacy premarket from 04:00 is settled
                # by the label-only region above.
                in_premarket = (conv_date[rows] == d) & (cm >= 240) & (cm < 570)
                if bool(in_premarket.all()):
                    verdict_label = False
                else:
                    label_rth = int(((rm >= 570) & (rm < 960)).sum()) / 390
                    true_rth = int(((conv_date[rows] == d) & (cm >= 570) & (cm < 960)).sum()) / 390
                    verdict_label = label_rth >= 0.5 and label_rth >= 1.5 * true_rth
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


# -- NYSE sessions -------------------------------------------------------------
#
# The one NYSE calendar every job, script and the API reads (FEAT-DATA-001).
# Backed by pandas_market_calendars, imported inside the first calendar call so
# the importers that only need the zone helpers above do not pay for it.
#
# Fails loud (CLAUDE.md 3.7, REQ-DATA-001): an import error and any error from
# get_calendar or schedule propagate, and a build that returns no sessions
# raises and is never cached -- an empty schedule would report every date
# closed and every weekday a holiday. There is no weekday-only fallback.
#
# One schedule per process over a padded range (2000 through the current year
# plus 2), extended on demand. Before answering, the cache must cover the asked
# date(s) plus _SESSION_PAD on each side, so a date at either edge still finds
# its true neighbour. Building and extending happen under one lock with the
# coverage re-checked inside it: concurrent cold calls make one build, and an
# extension is taken over the union with whatever the cache already holds, so
# two extensions in opposite directions are both kept.

_NYSE = "NYSE"
_SESSION_CACHE_FIRST_DAY = date(2000, 1, 1)
_SESSION_CACHE_YEARS_AHEAD = 2
_SESSION_PAD = timedelta(days=10)
# A neighbour search widens its window by this factor while it finds nothing
# (only a closure longer than _SESSION_PAD needs it, e.g. 1914), up to the cap.
_NEIGHBOUR_WIDEN = 4
_NEIGHBOUR_MAX_PAD = timedelta(days=3660)


class _SessionCache(NamedTuple):
    """An immutable snapshot of the schedule over ``[first, last]``.

    ``days`` is the session dates, ascending, parallel to ``frame``'s rows.
    Readers take the module-level reference once and never see it change.
    """

    first: date
    last: date
    days: list[date]
    frame: pd.DataFrame


_session_cache: _SessionCache | None = None
_session_cache_lock = threading.Lock()


def _reset_session_cache() -> None:
    """Drop the cached schedule (tests only)."""
    global _session_cache
    with _session_cache_lock:
        _session_cache = None


def _build_session_cache(first: date, last: date) -> _SessionCache:
    """Read the NYSE schedule for ``[first, last]`` from the library.

    No ``except`` here or in any caller: every library error propagates.
    """
    import pandas_market_calendars as mcal

    schedule = mcal.get_calendar(_NYSE).schedule(
        start_date=first.isoformat(), end_date=last.isoformat()
    )
    if len(schedule) == 0:
        raise RuntimeError(
            f"NYSE schedule for {first} to {last} has no sessions; refusing to "
            "cache it (it would report every weekday as a holiday)"
        )
    frame = schedule[["market_open", "market_close"]]
    return _SessionCache(first, last, list(frame.index.date), frame)


def _sessions_covering(first: date, last: date) -> _SessionCache:
    """The cached schedule, built or extended so it covers ``[first, last]``."""
    global _session_cache
    cache = _session_cache
    if cache is not None and cache.first <= first and last <= cache.last:
        return cache
    with _session_cache_lock:
        cache = _session_cache  # another thread may have built it meanwhile
        if cache is not None and cache.first <= first and last <= cache.last:
            return cache
        if cache is None:
            lo = _SESSION_CACHE_FIRST_DAY
            hi = date(market_today().year + _SESSION_CACHE_YEARS_AHEAD, 12, 31)
        else:
            lo, hi = cache.first, cache.last
        built = _build_session_cache(min(lo, first), max(hi, last))
        _session_cache = built
        return built


def _session_day(value: DateLike | str) -> date:
    """Normalise a calendar argument to an Eastern market date.

    An ISO ``YYYY-MM-DD`` string is a date; anything else goes through
    :func:`market_date`, so an aware datetime is read as its Eastern date and a
    naive one is refused.
    """
    if isinstance(value, str):
        return date.fromisoformat(value)
    day = market_date(value)
    if not isinstance(day, date):
        raise TypeError(f"expected a date, datetime or ISO date string, got {value!r}")
    return day


def _cache_around(day: date) -> _SessionCache:
    return _sessions_covering(day - _SESSION_PAD, day + _SESSION_PAD)


def is_session(day: DateLike | str) -> bool:
    """True when NYSE trades on *day*, half days included."""
    d = _session_day(day)
    days = _cache_around(d).days
    i = bisect_left(days, d)
    return i < len(days) and days[i] == d


def previous_session(day: DateLike | str) -> date:
    """The last NYSE session strictly before *day*."""
    d = _session_day(day)
    pad = _SESSION_PAD
    while True:
        cache = _sessions_covering(d - pad, d + _SESSION_PAD)
        i = bisect_left(cache.days, d)
        if i > 0:
            return cache.days[i - 1]
        if pad >= _NEIGHBOUR_MAX_PAD:
            raise RuntimeError(f"no NYSE session within {pad.days} days before {d}")
        pad *= _NEIGHBOUR_WIDEN


def next_session(day: DateLike | str) -> date:
    """The first NYSE session strictly after *day*."""
    d = _session_day(day)
    pad = _SESSION_PAD
    while True:
        cache = _sessions_covering(d - _SESSION_PAD, d + pad)
        i = bisect_right(cache.days, d)
        if i < len(cache.days):
            return cache.days[i]
        if pad >= _NEIGHBOUR_MAX_PAD:
            raise RuntimeError(f"no NYSE session within {pad.days} days after {d}")
        pad *= _NEIGHBOUR_WIDEN


def latest_session_on_or_before(day: DateLike | str) -> date:
    """*day* when it is a session, else :func:`previous_session` of it."""
    d = _session_day(day)
    return d if is_session(d) else previous_session(d)


def sessions_between(start: DateLike | str, end: DateLike | str) -> list[date]:
    """NYSE sessions in ``[start, end]``, ascending; empty when ``end < start``."""
    s, e = _session_day(start), _session_day(end)
    days = _sessions_covering(min(s, e) - _SESSION_PAD, max(s, e) + _SESSION_PAD).days
    return days[bisect_left(days, s):bisect_right(days, e)]


def session_count(start: DateLike | str, end: DateLike | str) -> int:
    """Number of NYSE sessions in ``(start, end]``; 0 when ``end <= start``."""
    s, e = _session_day(start), _session_day(end)
    days = _sessions_covering(min(s, e) - _SESSION_PAD, max(s, e) + _SESSION_PAD).days
    return max(0, bisect_right(days, e) - bisect_right(days, s))


def session_close(day: DateLike | str) -> datetime:
    """The close of session *day* as an aware UTC datetime.

    13:00 ET on half days. Raises ``ValueError`` when *day* is not a session:
    a closed day has no close, and inventing 16:00 for it is the fallback this
    module exists to prevent.
    """
    d = _session_day(day)
    cache = _cache_around(d)
    i = bisect_left(cache.days, d)
    if i == len(cache.days) or cache.days[i] != d:
        raise ValueError(f"{d} is not an NYSE session")
    return cache.frame["market_close"].iloc[i].to_pydatetime().astimezone(UTC)


def holidays_in(year: int) -> list[date]:
    """Weekdays in *year* on which NYSE does not trade, ascending."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    days = _sessions_covering(first - _SESSION_PAD, last + _SESSION_PAD).days
    sessions = set(days[bisect_left(days, first):bisect_right(days, last)])
    every_day = (first + timedelta(days=n) for n in range((last - first).days + 1))
    return [d for d in every_day if d.weekday() < 5 and d not in sessions]


def session_schedule(start: DateLike | str, end: DateLike | str) -> pd.DataFrame:
    """The NYSE schedule for sessions in ``[start, end]``.

    Indexed by session date (naive ``Timestamp``), with the library's actual
    ``market_open`` and ``market_close`` as UTC timestamps: early closes and
    delayed opens included (2002-09-11 opened at 12:00 ET). The primitive the
    other calendar functions are built on; returns a copy.
    """
    s, e = _session_day(start), _session_day(end)
    cache = _sessions_covering(min(s, e) - _SESSION_PAD, max(s, e) + _SESSION_PAD)
    lo, hi = bisect_left(cache.days, s), bisect_right(cache.days, e)
    return cache.frame.iloc[lo:max(lo, hi)].copy()


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
