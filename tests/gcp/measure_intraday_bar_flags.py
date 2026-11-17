#!/usr/bin/env python3
"""Local measurement of the bar flag pass (FEAT-DATA-001, the spec's Capacity
section and its PR-body figures).

    python3 tests/gcp/measure_intraday_bar_flags.py

``flag_months`` with ``commit=True`` over one ticker's 72 months (SPY,
2015-01 to 2020-12), each read answered with 31,711 synthetic rows, against a
stand-in engine and a stubbed strict reader: no database, no bucket, no
network. It prints one line,

    seconds=<N.N> statements=<N> peak_rss_mb=<N> months=<N> rows_read=<N> flags=<N>

and exits 1 unless the statement count is 289 (one coverage read, and for
each month the configuration statement, the lock, the read and the write)
and the peak resident memory is under 512 MB. The pass holds one ticker-month
at a time, so a breach of either is a defect in the pass, not a number to
raise.

What the figures are, and are not:

* ``seconds`` is the time inside ``flag_months``. The time the stand-in
  spends building each synthetic read is taken out, since the real read
  spends it in the database instead, which is NOT measured here: no round
  trip to Cloud SQL is in this figure.
* ``statements`` counts every round trip the pass makes: the strict coverage
  read and each statement executed on a connection.
* ``peak_rss_mb`` is the process's peak resident set (``ru_maxrss``), the
  interpreter, pandas, the exchange calendar and the synthetic rows included.
* Each read's 31,711 rows are spread evenly over its window (the month
  window with its 7-day margins), a whole number of seconds apart, with
  ``inserted_at`` 2026-11-20 so every row is proven a true instant. Prices
  are a seeded random walk; every 2,000th row of a read carries a low 1%
  under its open and close, so the rule flags rows and the write carries a
  set that is not empty. The proof, the rule, the session labels, the
  per-session digests and the month's basis all run on them.
* The write statement is built and bound as in production and answered
  (0, 0, 0) by the stand-in: Postgres does not run it here.

Not collected by pytest: the name does not start with ``test_``.
"""
from __future__ import annotations

import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
INSERTED = pd.Timestamp("2026-11-20 03:00", tz="UTC")
TICKER = "SPY"
FIRST_MONTH, LAST_MONTH = (2015, 1), (2020, 12)
MONTHS = 72
ROWS_PER_READ = 31_711
MISPRINT_EVERY = 2_000
EXPECTED_STATEMENTS = 1 + 4 * MONTHS
BOUND_MB = 512


def read_rows(start: datetime, end: datetime) -> list[tuple]:
    """What the pass's read returns for ``[start, end)``: ROWS_PER_READ rows
    in the read's column order, ts ascending."""
    span_s = int((end - start).total_seconds())
    step_s = span_s // ROWS_PER_READ
    if step_s < 1:
        raise ValueError(f"{ROWS_PER_READ} rows do not fit in [{start}, {end})")
    ts = pd.Timestamp(start) + pd.to_timedelta(
        np.arange(ROWS_PER_READ, dtype="int64") * step_s, unit="s")
    rng = np.random.default_rng(int(pd.Timestamp(start).timestamp()))
    close = np.round(400.0 + np.cumsum(rng.normal(0.0, 0.02, ROWS_PER_READ)), 4)
    open_ = np.concatenate([[400.0], close[:-1]])
    high = np.maximum(open_, close) + 0.01
    low = np.minimum(open_, close) - 0.01
    misprint = np.arange(ROWS_PER_READ) % MISPRINT_EVERY == MISPRINT_EVERY // 2
    low[misprint] = np.round(low[misprint] * 0.99, 4)
    volume = np.full(ROWS_PER_READ, 1000, dtype="int64")
    return list(zip(ts.to_pydatetime(), open_.tolist(), high.tolist(), low.tolist(),
                    close.tolist(), volume.tolist(), [INSERTED] * ROWS_PER_READ))


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def one(self):
        (row,) = self._rows
        return row


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def rollback(self):
        raise AssertionError("a committed pass does not roll back")


class _Connection:
    def __init__(self, engine):
        self._engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def begin(self):
        return _Transaction()

    def execute(self, statement, params=None):
        return self._engine.answer(str(statement), params or {})


class StandInEngine:
    """Answers the pass's four statements and counts every round trip."""

    def __init__(self):
        self.statements = 0
        self.rows_read = 0
        self.flags_written = 0
        self.seconds_in_stub = 0.0

    def query_to_dataframe_strict(self, sql, params=None, **_kwargs):
        if "intraday_bar_flag_coverage" not in sql:
            raise AssertionError(f"a strict read the stand-in does not know: {sql}")
        self.statements += 1
        # No month judged before: nothing to compare, no BARS-CHANGED line.
        return pd.DataFrame(columns=["month", "checked_at", "session_sha256"])

    def connect(self):
        return _Connection(self)

    def answer(self, text, params):
        self.statements += 1
        if text.startswith("SELECT set_config"):
            return _Result([("120s", "read committed")])
        if "pg_advisory_xact_lock" in text:
            return _Result([("",)])
        if "FROM market_data_intraday" in text:
            began = time.perf_counter()
            rows = read_rows(params["start"], params["end"])
            self.seconds_in_stub += time.perf_counter() - began
            self.rows_read += len(rows)
            return _Result(rows)
        if "INSERT INTO intraday_bar_flags" in text:
            self.flags_written += len(params["flags"])
            return _Result([(0, 0, 0)])
        raise AssertionError(f"a statement the stand-in does not know: {text}")


def main() -> int:
    import gcp.database as database
    from gcp.fetchers import intraday_bar_flags
    from gcp.fetchers.export_intraday_bars import months_between

    months = months_between(FIRST_MONTH, LAST_MONTH)
    if len(months) != MONTHS:
        raise SystemExit(f"{len(months)} months, expected {MONTHS}")

    engine = StandInEngine()
    database.get_engine = lambda: engine
    database.query_to_dataframe_strict = engine.query_to_dataframe_strict

    began = time.perf_counter()
    result = intraday_bar_flags.flag_months([TICKER], months, commit=True, now_utc=NOW)
    seconds = time.perf_counter() - began - engine.seconds_in_stub
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024   # Linux: KiB

    print(f"seconds={seconds:.1f} statements={engine.statements} "
          f"peak_rss_mb={peak_mb:.0f} months={result['months']} "
          f"rows_read={engine.rows_read} flags={engine.flags_written}")

    failed = False
    if result["months"] != MONTHS or engine.rows_read != MONTHS * ROWS_PER_READ:
        print(f"the pass judged {result['months']} months over {engine.rows_read} rows, "
              f"expected {MONTHS} months of {ROWS_PER_READ} rows", file=sys.stderr)
        failed = True
    if engine.statements != EXPECTED_STATEMENTS:
        print(f"statements {engine.statements} is not {EXPECTED_STATEMENTS}",
              file=sys.stderr)
        failed = True
    if peak_mb >= BOUND_MB:
        print(f"peak_rss_mb {peak_mb:.0f} is not under the {BOUND_MB} MB bound",
              file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
