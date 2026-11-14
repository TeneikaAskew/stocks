#!/usr/bin/env python3
"""Local measurements for the bar export and the feature loader
(FEAT-DATA-001, the spec's Capacity section and its PR-body figures).

    python3 -m tests.gcp.measure_export_intraday_bars nightly
    python3 -m tests.gcp.measure_export_intraday_bars history
    python3 -m tests.gcp.measure_export_intraday_bars loader

Each mode runs in its own process, on synthetic rows, against the strict
reader stubbed and an in-memory bucket: no database, no bucket, no network.
It prints one line,

    mode=<m> seconds=<N.N> peak_rss_mb=<N>

and exits 1 when its bound is passed.

* ``nightly``: ``export_window`` over 6 ticker-months of 25,000 rows each
  (SPY, QQQ and IWM, 2026-09 and 2026-10). No bound; the figures are reported.
* ``history``: ``export_window`` over one ticker's 143 months (2015-01 to
  2026-11) of 50,000 rows each. Bound: peak under 512 MB. The export holds one
  ticker-month at a time, so a breach is a defect in the export, not a number
  to raise.
* ``loader``: ``strat_data_builder._load_1m_bars`` over 3,000,000 proven rows
  in one frame, the full rebuild's read. Bound: peak under 2,048 MB.

What the figures are, and are not:

* ``seconds`` is the time inside the code under measurement. The time the
  stub spends building each synthetic frame is taken out, since the real
  reader spends it in the database instead (which is NOT measured here).
* ``peak_rss_mb`` is the process's peak resident set (``ru_maxrss``), the
  interpreter, pandas and the synthetic rows included. In the two export
  modes the in-memory bucket also keeps every file written, which the real
  bucket does not.
* Synthetic rows are true UTC instants from 04:00 ET of each session, with
  ``inserted_at`` 2026-11-20 (proven), flat prices, and a daily row per
  session, so the placement, the session readings and the basis verdicts all
  run. A session holds as many rows as the month's count needs. Where that is
  more than the minutes between 04:00 and midnight ET, the rows are spaced
  under a minute apart: 50,000 rows do not fit in a month's minutes at one a
  minute, and the figure wanted is the cost of that many rows.

Not collected by pytest: the name does not start with ``test_``.
"""
from __future__ import annotations

import resource
import sys
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
INSERTED = pd.Timestamp("2026-11-20 03:00", tz="UTC")
HIGH, LOW = 600.0, 590.0
MID = (HIGH + LOW) / 2
# Rows of one session start at 04:00 ET and stay inside the same Eastern day.
SESSION_SPAN_S = 20 * 3600 - 60

BOUNDS_MB = {"nightly": None, "history": 512, "loader": 2048}


def _last_day(year: int, month: int) -> date:
    first_of_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first_of_next - timedelta(days=1)


def _session_starts_ns(days) -> np.ndarray:
    """04:00 Eastern of each session, as UTC nanoseconds."""
    from lib.eastern_time import eastern_index_to_utc

    starts = pd.DatetimeIndex([pd.Timestamp(d) + pd.Timedelta(hours=4) for d in days])
    return eastern_index_to_utc(starts).as_unit("ns").asi8


def _frame(ts_ns: np.ndarray, with_source: bool) -> pd.DataFrame:
    n = len(ts_ns)
    frame = {
        "ts": pd.DatetimeIndex(ts_ns, tz="UTC"),
        "open": np.full(n, MID), "high": np.full(n, HIGH), "low": np.full(n, LOW),
        "close": np.full(n, MID), "volume": np.full(n, 1000, dtype="int64"),
    }
    if with_source:
        frame["data_source"] = "alphavantage"
    frame["inserted_at"] = INSERTED
    return pd.DataFrame(frame)


def month_rows(year: int, month: int, rows: int) -> pd.DataFrame:
    """What the bars read returns for a synthetic month of *rows* rows."""
    from lib.eastern_time import sessions_between

    days = sessions_between(date(year, month, 1), _last_day(year, month))
    per_session = -(-rows // len(days))
    step_s = min(60, SESSION_SPAN_S // per_session)
    if step_s < 1:
        raise ValueError(f"{rows} rows do not fit in {year}-{month:02d}")
    offsets = np.arange(per_session, dtype="int64") * step_s * 1_000_000_000
    ts = (_session_starts_ns(days)[:, None] + offsets[None, :]).ravel()[:rows]
    return _frame(ts, with_source=True)


def daily_rows(first: date, last: date) -> pd.DataFrame:
    from lib.eastern_time import sessions_between

    days = sessions_between(first, last)
    return pd.DataFrame({"date": days, "high": HIGH, "low": LOW,
                         "data_source": "alphavantage_daily"})


def _export(tickers, months, rows_per_month: int) -> tuple[float, dict]:
    """export_window over synthetic months: (seconds in the export, its result)."""
    import gcp.database as database
    from gcp.fetchers import export_intraday_bars
    from tests.fixtures.intraday_bars_bucket import MemoryBucket

    in_stub = [0.0]

    def strict(sql, params=None, timeout_s=None):
        began = time.perf_counter()
        try:
            if "market_data_daily" in sql:
                return daily_rows(params["first"], params["last"])
            start = params["start"]
            return month_rows(start.year, start.month, rows_per_month)
        finally:
            in_stub[0] += time.perf_counter() - began

    database.query_to_dataframe_strict = strict
    began = time.perf_counter()
    result = export_intraday_bars.export_window(
        tickers, months, bucket=MemoryBucket(), now_utc=NOW)
    seconds = time.perf_counter() - began - in_stub[0]
    expected = len(tickers) * len(months)
    if result["months"] != expected or result["rows"] != expected * rows_per_month:
        raise SystemExit(f"the export wrote {result}, expected {expected} months of "
                         f"{rows_per_month} rows")
    return seconds, result


def nightly() -> float:
    from gcp.fetchers.export_intraday_bars import EXPORT_TICKERS

    seconds, _ = _export(EXPORT_TICKERS, [(2026, 9), (2026, 10)], 25_000)
    return seconds


def history() -> float:
    from gcp.fetchers.export_intraday_bars import months_between

    months = months_between((2015, 1), (2026, 11))
    if len(months) != 143:
        raise SystemExit(f"{len(months)} months, expected 143")
    seconds, _ = _export(["SPY"], months, 50_000)
    return seconds


def loader() -> float:
    from gcp.research.strat_engine import strat_data_builder as sdb
    from lib.eastern_time import sessions_between

    rows, per_session = 3_000_000, 961            # 04:00 to 20:00 ET, one a minute
    # Every date is before 2026-09-28, so each row is proven by its
    # inserted_at alone: the path Design H adds.
    count = -(-rows // per_session)
    days = sessions_between(date(2012, 1, 1), date(2026, 9, 25))[-count:]
    offsets = np.arange(per_session, dtype="int64") * 60 * 1_000_000_000
    ts = (_session_starts_ns(days)[:, None] + offsets[None, :]).ravel()[:rows]
    frame = _frame(ts, with_source=False)
    if len(frame) != rows:
        raise SystemExit(f"{len(frame)} synthetic rows, expected {rows}")
    del ts

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    handed = [frame]
    del frame
    sdb.pd.read_sql = lambda sql, conn, params=None: handed.pop()
    began = time.perf_counter()
    out = sdb._load_1m_bars(_Engine(), "SPY", days[0].isoformat())
    seconds = time.perf_counter() - began
    # 390 regular-hours minutes (09:30 to 15:59) of each whole session, and
    # those of the last session's rows, which stop where the row count does.
    last_rows = rows - (count - 1) * per_session
    last_minute = 4 * 60 + last_rows - 1
    expected = (count - 1) * 390 + max(0, min(959, last_minute) - 570 + 1)
    if len(out) != expected:
        raise SystemExit(f"the loader returned {len(out)} rows, expected {expected}")
    return seconds


def main(argv: list[str]) -> int:
    modes = {"nightly": nightly, "history": history, "loader": loader}
    if len(argv) != 1 or argv[0] not in modes:
        print("usage: python3 -m tests.gcp.measure_export_intraday_bars "
              "{nightly|history|loader}", file=sys.stderr)
        return 2
    mode = argv[0]
    seconds = modes[mode]()
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024   # Linux: KiB
    print(f"mode={mode} seconds={seconds:.1f} peak_rss_mb={peak_mb:.0f}")
    bound = BOUNDS_MB[mode]
    if bound is not None and peak_mb >= bound:
        print(f"peak_rss_mb {peak_mb:.0f} is not under the {bound} MB bound", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
