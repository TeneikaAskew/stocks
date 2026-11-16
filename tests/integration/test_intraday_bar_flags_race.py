"""The bar flag pass and a month replace, interleaved on a real Postgres
(FEAT-DATA-001, issue #1982).

`flag_months` and `gcp.database.replace_rows_in_window` run on two connections
in two threads; a third connection reads `pg_locks`. The pass is held between
its read and its write by a stand-in for `lib.bar_prints.isolated_prints` that
waits on a `threading.Event`; the replace is held, under its locks and before
it swaps a bar, by a `verify` that waits on another. Every wait has a timeout
that fails the test.

Cases (a) and (b) show the shared advisory lock keeps the two apart in either
order. Cases (c) and (d) are negative controls: with the pass's lock removed,
or moved into the read's own statement, the same interleaving publishes a
coverage row computed from bars the table no longer holds. They pass by
showing the race, so the test is known to detect what it guards.

The rows are SPY's, in 2011, years before the first stored bar, as in
test_intraday_bar_flags_writes.py, whose seeding helpers these cases share.

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(decision 12, Design 3 step 1, Design 7).
"""
from __future__ import annotations

import threading
import time
from datetime import date

import pandas as pd
import pytest

import gcp.database as db
import gcp.fetchers.fetch_alphavantage_intraday as fai
import gcp.fetchers.intraday_bar_flags as ibf
from gcp import bar_recompute
from lib.eastern_time import intraday_month_window
from tests.integration import test_intraday_bar_flags_writes as writes
from tests.integration.test_intraday_bar_flags_writes import (
    SESSION_OF,
    SPY_KEY,
    T2,
    _coverage,
    _flags,
    _judged_four_months,
    _new_bars,
)

# That file's fixtures: its own rows wiped before and after, and a named run.
own_rows = writes.own_rows
execution = writes.execution

MARCH, APRIL, MAY, JUNE = (2011, 3), (2011, 4), (2011, 5), (2011, 6)
MAY_WINDOW = intraday_month_window(*MAY)
MAY_KEY = ibf.flag_lock_key("SPY", MAY)
# How long a thread or an event is waited for before the test fails.
WAIT = 20.0
# How long the third connection looks for a waiting lock.
SEEN_WITHIN = 10.0


class _Thread:
    """A function on its own thread, its result or its exception kept."""

    def __init__(self, target):
        self.result = None
        self.error: BaseException | None = None

        def run():
            try:
                self.result = target()
            except BaseException as exc:  # noqa: BLE001  (re-raised by finish)
                self.error = exc

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def alive(self) -> bool:
        return self._thread.is_alive()

    def finish(self, what: str):
        """Wait for the thread; fail when it does not end, re-raise what it raised."""
        self._thread.join(WAIT)
        assert not self._thread.is_alive(), f"{what} did not finish within {WAIT} s"
        if self.error is not None:
            raise self.error
        return self.result

    def abandon(self) -> None:
        self._thread.join(WAIT)


def _wait(event: threading.Event, what: str) -> None:
    assert event.wait(WAIT), f"{what} was not reached within {WAIT} s"


def _split(key: int) -> tuple[int, int]:
    """A 64-bit advisory key as pg_locks shows it: (classid, objid)."""
    unsigned = key % 2**64
    return unsigned >> 32, unsigned & 0xFFFFFFFF


def _waiting_on(key: int) -> list[int]:
    """The backends waiting, ungranted, for the advisory lock *key*."""
    import sqlalchemy

    high, low = _split(key)
    with db.get_engine().connect() as conn:
        rows = conn.execute(sqlalchemy.text(
            "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND objsubid = 1 "
            "AND NOT granted AND classid::bigint = :high AND objid::bigint = :low"),
            {"high": high, "low": low}).fetchall()
    return [int(row[0]) for row in rows]


def _seen_waiting_on(key: int, waiter: _Thread, what: str) -> None:
    """Fail unless a backend is seen waiting on *key* within SEEN_WITHIN."""
    pause = threading.Event()
    deadline = time.monotonic() + SEEN_WITHIN
    while time.monotonic() < deadline:
        if _waiting_on(key):
            return
        assert waiter.alive(), f"{what} ended without waiting: {waiter.error!r}"
        pause.wait(0.05)
    raise AssertionError(
        f"{what} was not seen waiting on an ungranted advisory lock within {SEEN_WITHIN} s")


def _stored(month: tuple[int, int] = MAY) -> pd.DataFrame:
    """What a pass of *month* reads now: the stored rows of its read window."""
    with db.get_engine().connect() as conn:
        return ibf._read_bars(conn, "SPY", *ibf.read_window(month))


def _basis(bars: pd.DataFrame) -> tuple[str, dict]:
    return bar_recompute.bars_basis(bars)["sha256"], ibf.session_digests(bars)


def _may_opens(run_sql) -> list[float]:
    frame = run_sql("SELECT DISTINCT open FROM market_data_intraday WHERE ticker = 'SPY' "
                    "AND ts >= :s AND ts < :e ORDER BY open",
                    {"s": MAY_WINDOW[0], "e": MAY_WINDOW[1]})
    return list(frame.open)


def _coverage_months(run_sql) -> list[date]:
    return list(_coverage(run_sql).month)


def _may_coverage(run_sql) -> pd.Series:
    coverage = _coverage(run_sql)
    rows = coverage[coverage.month == date(2011, 5, 1)]
    assert len(rows) == 1, "May has no coverage row"
    return rows.iloc[0]


def _replace_may(*, verify=None, locks: bool = True):
    """The window swap of a replace of May, as replace_month hands it over:
    the refetched bars, the span tables and the locks of the months whose
    read window overlaps May's."""
    start, end = MAY_WINDOW
    months = ibf.flag_months_overlapping(start, end)
    assert months == [APRIL, MAY, JUNE]
    return db.replace_rows_in_window(
        _new_bars(SESSION_OF[MAY]), "market_data_intraday", SPY_KEY, "ts", start, end,
        verify=verify if verify is not None else (lambda conn: None),
        clear_span_tables=fai.DERIVED_SPAN_TABLES,
        advisory_locks=[ibf.flag_lock_key("SPY", m) for m in months] if locks else ())


def _pass_of_may(execution) -> dict:
    execution("exec-race")
    return ibf.flag_months(("SPY",), [MAY], commit=True, now_utc=T2)


class _HeldPass:
    """A stand-in for lib.bar_prints.isolated_prints: it runs after the pass's
    read, says so, and waits to be released before it judges."""

    def __init__(self, monkeypatch):
        self.has_read = threading.Event()
        self.release = threading.Event()
        real = ibf.bar_prints.isolated_prints

        def stand_in(bars):
            self.has_read.set()
            assert self.release.wait(WAIT), "the held pass was never released"
            return real(bars)

        monkeypatch.setattr(ibf.bar_prints, "isolated_prints", stand_in)


class _HeldReplace:
    """A verify for the swap: it runs under the swap's locks and before its
    DELETE, says so, and waits to be released."""

    def __init__(self):
        self.holding = threading.Event()
        self.release = threading.Event()

    def verify(self, conn) -> None:
        self.holding.set()
        assert self.release.wait(WAIT), "the held replace was never released"


def _read_first(seed, run_sql, execution, monkeypatch, *, replace_waits: bool,
                replace_locks: bool = True):
    """The pass reads May and is held before its write; a replace of May is
    started; the pass is released. *replace_waits*: whether the replace must
    be seen waiting for the pass (case a) or must commit while the pass is
    still held (the negative control). Returns (the basis of the old bars,
    the basis of the new bars)."""
    _judged_four_months(seed, execution)
    old = _basis(_stored())
    held = _HeldPass(monkeypatch)
    flag_pass = replace = None
    try:
        flag_pass = _Thread(lambda: _pass_of_may(execution))
        _wait(held.has_read, "the pass's read")
        replace = _Thread(lambda: _replace_may(locks=replace_locks))
        if replace_waits:
            # A third connection sees the replace waiting, and its bars unchanged.
            _seen_waiting_on(MAY_KEY, replace, "the replace")
            assert replace.alive() and flag_pass.alive()
            assert _may_opens(run_sql) == [100.0]
            assert _basis(_stored()) == old
        else:
            # Nothing holds the replace back: it commits while the pass is held.
            assert replace.finish("the replace") == (60, 60)
            assert flag_pass.alive()
            assert _may_opens(run_sql) == [200.0]
        held.release.set()
        out = flag_pass.finish("the pass")
        assert out["months"] == 1 and out["flags"] == 1
        assert replace.finish("the replace") == (60, 60)
    finally:
        held.release.set()
        for thread in (flag_pass, replace):
            if thread is not None:
                thread.abandon()
    assert _may_opens(run_sql) == [200.0]
    new = _basis(_stored())
    assert new != old
    return old, new


def _replace_first(seed, run_sql, execution):
    """A replace of May takes its locks and is held before it swaps; the pass
    of May is started and waits; the replace is released. Returns (the basis
    of the old bars, the basis of the new bars)."""
    _judged_four_months(seed, execution)
    old = _basis(_stored())
    held = _HeldReplace()
    flag_pass = replace = None
    try:
        replace = _Thread(lambda: _replace_may(verify=held.verify))
        _wait(held.holding, "the replace's verify")
        assert _may_opens(run_sql) == [100.0]
        flag_pass = _Thread(lambda: _pass_of_may(execution))
        _seen_waiting_on(MAY_KEY, flag_pass, "the pass")
        assert flag_pass.alive() and replace.alive()
        assert _may_opens(run_sql) == [100.0]
        held.release.set()
        assert replace.finish("the replace") == (60, 60)
        out = flag_pass.finish("the pass")
        assert out["months"] == 1
    finally:
        held.release.set()
        for thread in (replace, flag_pass):
            if thread is not None:
                thread.abandon()
    assert _may_opens(run_sql) == [200.0]
    new = _basis(_stored())
    assert new != old
    return old, new


def test_read_first(own_rows, seed, run_sql, execution, monkeypatch):
    """(a) The pass holds May's lock and has read. The replace waits before
    it locks a bar; once the pass commits it swaps and clears what the pass
    wrote. No row computed from the old bars is published."""
    _read_first(seed, run_sql, execution, monkeypatch, replace_waits=True)

    assert _coverage_months(run_sql) == [date(2011, 3, 1)]
    assert [ts.month for ts in _flags(run_sql).ts] == [3]
    print("\n(a) read first: the replace waited for the pass; coverage left for "
          f"{[d.isoformat() for d in _coverage_months(run_sql)]}, "
          f"flags left in months {[ts.month for ts in _flags(run_sql).ts]}")


def test_replace_first(own_rows, seed, run_sql, execution):
    """(b) The replace holds its locks and has not swapped yet. The pass
    waits in its lock statement; its read is a later statement, so it reads
    the replaced bars."""
    old, new = _replace_first(seed, run_sql, execution)

    row = _may_coverage(run_sql)
    assert (row.bars_basis["sha256"], row.session_sha256) == new
    assert (row.bars_basis["sha256"], row.session_sha256) != old
    assert row.bars_basis == bar_recompute.bars_basis(_stored())
    assert row.run_id == "exec-race" and row.checked_at == pd.Timestamp(T2)
    # The new bars hold no wick; April and June stay cleared until the rebuild.
    assert (row.flags_regular_low, row.bars_in_month) == (0, 60)
    assert _coverage_months(run_sql) == [date(2011, 3, 1), date(2011, 5, 1)]
    assert [ts.month for ts in _flags(run_sql).ts] == [3]
    print("\n(b) replace first: the pass waited for the replace; May's coverage row "
          f"holds the new bars' basis {row.bars_basis['sha256'][:12]}, "
          f"not the old {old[0][:12]}")


def test_negative_control_no_lock(own_rows, seed, run_sql, execution, monkeypatch):
    """(c) Case (a) with the pass's lock statement replaced by SELECT 1: the
    replace commits between the pass's read and its write, and the pass then
    publishes May's coverage row and flag, computed from the old bars."""
    monkeypatch.setattr(ibf, "LOCK_SQL", "SELECT 1")
    old, new = _read_first(seed, run_sql, execution, monkeypatch, replace_waits=False)

    row = _may_coverage(run_sql)
    # The stale row exists: it describes bars the table no longer holds.
    assert (row.bars_basis["sha256"], row.session_sha256) == old
    assert (row.bars_basis["sha256"], row.session_sha256) != new
    assert row.run_id == "exec-race" and row.flags_regular_low == 1
    assert _coverage_months(run_sql) == [date(2011, 3, 1), date(2011, 5, 1)]
    # And so does its flag, of a wick the new bars do not hold.
    assert [ts.month for ts in _flags(run_sql).ts] == [3, 5]
    assert _flags(run_sql).iloc[1].observed == 99.40 and _may_opens(run_sql) == [200.0]
    print("\n(c) no lock: the replace committed while the pass was held; May's coverage "
          f"row holds the OLD bars' basis {row.bars_basis['sha256'][:12]} "
          f"(the table now holds {new[0][:12]}), with 1 stale flag at {row.month}")


def test_negative_control_lock_inside_the_read(own_rows, seed, run_sql, execution,
                                               monkeypatch):
    """(d) Case (b) with the lock moved into the read as a CTE: the read's
    snapshot is taken before the lock it waits on is granted, so the pass
    reads the old bars after the replace committed."""
    monkeypatch.setattr(ibf, "LOCK_SQL", "SELECT 1")
    monkeypatch.setattr(ibf, "READ_SQL", (
        f"WITH locked AS MATERIALIZED (SELECT pg_advisory_xact_lock({MAY_KEY})) "
        "SELECT b.ts, b.open, b.high, b.low, b.close, b.volume, b.inserted_at "
        "FROM locked CROSS JOIN market_data_intraday AS b "
        "WHERE b.ticker = :t AND b.interval = '1min' AND b.ts >= :start AND b.ts < :end "
        "ORDER BY b.ts"))
    old, new = _replace_first(seed, run_sql, execution)

    row = _may_coverage(run_sql)
    assert (row.bars_basis["sha256"], row.session_sha256) == old
    assert (row.bars_basis["sha256"], row.session_sha256) != new
    assert row.run_id == "exec-race" and row.flags_regular_low == 1
    print("\n(d) lock inside the read: the pass waited, then read its old snapshot; May's "
          f"coverage row holds the OLD bars' basis {row.bars_basis['sha256'][:12]} "
          f"(the table now holds {new[0][:12]})")


def test_replace_lock_timeout(own_rows, seed, run_sql, execution):
    """A replace that waits longer than its 30 s lock_timeout raises and
    commits nothing."""
    import sqlalchemy

    _judged_four_months(seed, execution)
    flags_before, coverage_before = _flags(run_sql), _coverage(run_sql)
    basis_before = _basis(_stored())
    swapped: list = []

    with db.get_engine().connect() as holder:
        with holder.begin():
            holder.execute(sqlalchemy.text("SELECT pg_advisory_xact_lock(:k)"),
                           {"k": MAY_KEY}).fetchall()
            began = time.monotonic()
            with pytest.raises(sqlalchemy.exc.DBAPIError) as stop:
                _replace_may(verify=swapped.append)
            waited = time.monotonic() - began

    # LockNotAvailable, from the swap's own lock statement, after its 30 s.
    assert "55P03" in str(stop.value) and "lock timeout" in str(stop.value)
    assert "pg_advisory_xact_lock" in str(stop.value)
    assert 29.0 <= waited < 45.0
    assert swapped == []                      # never reached its row lock
    assert _may_opens(run_sql) == [100.0]
    assert _basis(_stored()) == basis_before
    pd.testing.assert_frame_equal(_flags(run_sql), flags_before)
    pd.testing.assert_frame_equal(_coverage(run_sql), coverage_before)
    print(f"\nlock timeout: the replace raised after {waited:.1f} s and committed nothing")
