"""The bar flag pass's one write statement on a real Postgres (FEAT-DATA-001).

The hermetic cases in tests/gcp/test_intraday_bar_flags.py read the
statements off a recording engine. These run them: the configuration, the
advisory lock, the read and the data-modifying write, against the real
`market_data_intraday`, `intraday_bar_flags` and `intraday_bar_flag_coverage`
DDL.

The pass refuses every ticker but SPY, QQQ and IWM, so these rows are SPY's
and QQQ's, in 2011, years before the first stored bar; only that year of
those two tickers is wiped.

Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
(Design 2, Design 3).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

import gcp.fetchers.intraday_bar_flags as ibf

UTC = timezone.utc
YEAR = (datetime(2011, 1, 1, tzinfo=UTC), datetime(2012, 1, 1, tzinfo=UTC))
TABLES = ("market_data_intraday", "intraday_bar_flags", "intraday_bar_flag_coverage")
FLAG_COLUMNS = (
    "ticker, interval, ts, side, rule_version, print_kind, session_part, observed, "
    "reference, bound, scale, excess_bp, read_start, read_end, detected_at, checked_at, run_id"
)
T1 = datetime(2026, 11, 12, 2, 0, 5, tzinfo=UTC)
T2 = datetime(2026, 11, 13, 2, 0, 7, tzinfo=UTC)
T3 = datetime(2026, 11, 14, 2, 0, 9, tzinfo=UTC)
APRIL = (2011, 4)
APRIL_START = datetime(2011, 4, 1, 2, tzinfo=UTC)
READ_START = datetime(2011, 3, 25, 2, tzinfo=UTC)
READ_END = datetime(2011, 5, 8, 2, tzinfo=UTC)
# Tuesday to Thursday; 14:30Z is 10:30 ET, inside the regular session.
A = datetime(2011, 4, 5, 14, 30, tzinfo=UTC)
B = datetime(2011, 4, 6, 14, 30, tzinfo=UTC)
C = datetime(2011, 4, 7, 14, 30, tzinfo=UTC)


@pytest.fixture
def own_rows(db_engine):
    """This file's rows only: SPY and QQQ in 2011, in the three tables."""
    import sqlalchemy

    def wipe():
        with db_engine.begin() as conn:
            for table in TABLES:
                conn.execute(sqlalchemy.text(
                    f"DELETE FROM {table} WHERE ticker IN ('SPY', 'QQQ') "
                    "AND ts >= :s AND ts < :e"), {"s": YEAR[0], "e": YEAR[1]})
    wipe()
    yield
    wipe()


@pytest.fixture
def execution(monkeypatch):
    """Name the Cloud Run execution, so each pass has its own run id."""
    def name(value: str) -> None:
        monkeypatch.setenv("CLOUD_RUN_EXECUTION", value)
    return name


def _bars(ticker: str, day: str, n: int = 60) -> list[dict]:
    """n one-minute bars from 14:00Z: open, close and low 100.00, high 100.05.
    inserted_at takes its default, NOW(), which proves each row."""
    first = datetime.fromisoformat(f"{day}T14:00:00+00:00")
    return [{"ticker": ticker, "interval": "1min", "ts": first + timedelta(minutes=k),
             "open": 100.0, "high": 100.05, "low": 100.0, "close": 100.0, "volume": 1000,
             "data_source": "alphavantage"} for k in range(n)]


def _seed_april(seed) -> None:
    """Three April sessions of SPY: a 60 bp low wick at A and at B, and at C
    a bar 60 bp out on both sides."""
    rows = _bars("SPY", "2011-04-05") + _bars("SPY", "2011-04-06") + _bars("SPY", "2011-04-07")
    for row in rows:
        if row["ts"] in (A, B, C):
            row["low"] = 99.40
        if row["ts"] == C:
            row["high"] = 100.60
    seed("market_data_intraday", rows)


def _set_bar(db_engine, ts: datetime, **values) -> None:
    import sqlalchemy

    assignments = ", ".join(f"{name} = :{name}" for name in values)
    with db_engine.begin() as conn:
        changed = conn.execute(sqlalchemy.text(
            f"UPDATE market_data_intraday SET {assignments} "
            "WHERE ticker = 'SPY' AND interval = '1min' AND ts = :ts"),
            {"ts": ts, **values}).rowcount
    assert changed == 1


def _flags(run_sql, ticker: str = "SPY", version: str = "isolated-print-v1") -> pd.DataFrame:
    return run_sql(
        f"SELECT {FLAG_COLUMNS} FROM intraday_bar_flags WHERE ticker = :t "
        "AND rule_version = :v AND ts >= :s AND ts < :e ORDER BY ts, side",
        {"t": ticker, "v": version, "s": YEAR[0], "e": YEAR[1]})


def _coverage(run_sql, ticker: str = "SPY") -> pd.DataFrame:
    return run_sql(
        "SELECT * FROM intraday_bar_flag_coverage WHERE ticker = :t "
        "AND ts >= :s AND ts < :e ORDER BY ts", {"t": ticker, "s": YEAR[0], "e": YEAR[1]})


def _stamp(value: datetime) -> pd.Timestamp:
    return pd.Timestamp(value)


def test_first_pass_inserts_the_flags_and_the_coverage_row(own_rows, seed, run_sql, execution):
    _seed_april(seed)
    execution("exec-1")
    out = ibf.flag_months(("SPY",), [APRIL], commit=True, now_utc=T1)

    assert out["months"] == 1 and out["flags"] == 4 and out["changed"] == 0
    flags = _flags(run_sql)
    # A bar flagged on both sides is two rows.
    assert list(zip(flags.ts, flags.side)) == [
        (_stamp(A), "low"), (_stamp(B), "low"), (_stamp(C), "high"), (_stamp(C), "low")]
    assert list(flags.observed) == [99.40, 99.40, 100.60, 99.40]
    assert list(flags.reference) == [100.0, 100.0, 100.0, 100.0]
    assert list(flags.bound) == [99.50, 99.50, 100.50, 99.50]
    assert list(flags.scale) == pytest.approx([0.05] * 4)
    assert list(flags.excess_bp) == pytest.approx([60.0] * 4)
    assert set(flags.print_kind) == {"wick"} and set(flags.session_part) == {"regular"}
    assert set(flags.interval) == {"1min"} and set(flags.run_id) == {"exec-1"}
    assert (flags.detected_at == _stamp(T1)).all() and (flags.checked_at == _stamp(T1)).all()
    assert (flags.read_start == _stamp(READ_START)).all()
    assert (flags.read_end == _stamp(READ_END)).all()

    coverage = _coverage(run_sql)
    assert len(coverage) == 1
    row = coverage.iloc[0]
    assert row.ts == _stamp(APRIL_START) and row.month == date(2011, 4, 1)
    assert row.rule_version == "isolated-print-v1" and row.interval == "1min"
    assert row.read_start == _stamp(READ_START) and row.read_end == _stamp(READ_END)
    assert row.params == {"neighbours": 2, "scale_bars": 61, "scale_multiple": 6.0,
                          "floor_bp": 50.0}
    assert (row.bars_in_month, row.bars_judged) == (180, 176)
    assert row.first_judged_ts == _stamp(datetime(2011, 4, 5, 14, 2, tzinfo=UTC))
    assert row.last_judged_ts == _stamp(datetime(2011, 4, 7, 14, 57, tzinfo=UTC))
    assert (row.flags_regular_high, row.flags_regular_low,
            row.flags_extended_high, row.flags_extended_low) == (1, 3, 0, 0)
    assert row.bars_basis["rows"] == 180 and len(row.bars_basis["sha256"]) == 64
    assert sorted(row.session_sha256) == ["2011-04-05", "2011-04-06", "2011-04-07"]
    assert set(row.code_version) == {"git_commit", "git_dirty", "built_at"}
    assert row.run_id == "exec-1" and row.checked_at == _stamp(T1)


def test_a_dry_run_writes_nothing(own_rows, seed, run_sql):
    _seed_april(seed)
    out = ibf.flag_months(("SPY",), [APRIL], commit=False, now_utc=T1)

    assert out["flags"] == 4
    assert len(_flags(run_sql)) == 0 and len(_coverage(run_sql)) == 0


def test_a_second_pass_over_unchanged_bars_moves_only_checked_at_and_run_id(
        own_rows, seed, run_sql, execution, caplog):
    _seed_april(seed)
    execution("exec-1")
    ibf.flag_months(("SPY",), [APRIL], commit=True, now_utc=T1)
    first_flags, first_coverage = _flags(run_sql), _coverage(run_sql)

    execution("exec-2")
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [APRIL], commit=True, now_utc=T2)
    second_flags, second_coverage = _flags(run_sql), _coverage(run_sql)

    assert out["changed"] == 0
    assert not [r for r in caplog.records if r.getMessage().startswith("BARS-CHANGED")]
    moved = ["checked_at", "run_id"]
    pd.testing.assert_frame_equal(second_flags.drop(columns=moved),
                                  first_flags.drop(columns=moved))
    assert (second_flags.detected_at == _stamp(T1)).all()
    assert (second_flags.checked_at == _stamp(T2)).all()
    assert set(second_flags.run_id) == {"exec-2"}
    pd.testing.assert_frame_equal(second_coverage.drop(columns=moved),
                                  first_coverage.drop(columns=moved))
    assert list(second_coverage.checked_at) == [_stamp(T2)]
    assert list(second_coverage.run_id) == ["exec-2"]


def test_a_changed_bar_deletes_one_flag_and_updates_another(
        own_rows, seed, run_sql, db_engine, execution, caplog):
    _seed_april(seed)
    execution("exec-1")
    ibf.flag_months(("SPY",), [APRIL], commit=True, now_utc=T1)

    _set_bar(db_engine, A, low=100.0)       # no longer flagged
    _set_bar(db_engine, B, low=99.30)       # still flagged, its observed moved
    execution("exec-3")
    with caplog.at_level(logging.INFO, logger=ibf.__name__):
        out = ibf.flag_months(("SPY",), [APRIL], commit=True, now_utc=T3)

    flags = _flags(run_sql)
    assert list(zip(flags.ts, flags.side)) == [
        (_stamp(B), "low"), (_stamp(C), "high"), (_stamp(C), "low")]
    moved = flags.iloc[0]
    assert (moved.observed, moved.reference, moved.bound) == (99.30, 100.0, 99.50)
    assert moved.scale == pytest.approx(0.05) and moved.excess_bp == pytest.approx(70.0)
    assert moved.checked_at == _stamp(T3) and moved.run_id == "exec-3"
    assert moved.detected_at == _stamp(T1)
    assert (flags.detected_at == _stamp(T1)).all() and (flags.checked_at == _stamp(T3)).all()

    # The two sessions that changed are named, with the write's own counts.
    changed = [r.getMessage() for r in caplog.records
               if r.getMessage().startswith("BARS-CHANGED")]
    assert changed == [
        "BARS-CHANGED SPY 2011-04 sessions=2011-04-05,2011-04-06 "
        "since=2026-11-12T02:00:05+00:00 inserted=0 deleted=1"]
    assert out["changed"] == 1 and out["flags"] == 3
    row = _coverage(run_sql).iloc[0]
    assert (row.flags_regular_high, row.flags_regular_low) == (1, 2)
    assert row.checked_at == _stamp(T3)


def _seeded_flag(ticker: str, ts: datetime, version: str) -> dict:
    return {"ticker": ticker, "interval": "1min", "ts": ts, "side": "low",
            "rule_version": version, "print_kind": "wick", "session_part": "regular",
            "observed": 90.0, "reference": 100.0, "bound": 99.5, "scale": 0.05,
            "excess_bp": 1000.0, "read_start": READ_START, "read_end": READ_END,
            "detected_at": T1 - timedelta(days=30), "checked_at": T1 - timedelta(days=30),
            "run_id": "seeded"}


def test_other_versions_tickers_and_months_are_untouched(own_rows, seed, run_sql, execution):
    """None of these four is in the pass's new set, so only the write's own
    scope (ticker, rule version, month window) keeps them."""
    _seed_april(seed)
    stale = datetime(2011, 4, 5, 14, 10, tzinfo=UTC)
    seed("intraday_bar_flags", [
        _seeded_flag("SPY", stale, "isolated-print-v0"),                 # another version
        _seeded_flag("QQQ", stale, "isolated-print-v1"),                 # another ticker
        _seeded_flag("SPY", APRIL_START - timedelta(minutes=1), "isolated-print-v1"),  # March
        _seeded_flag("SPY", datetime(2011, 5, 1, 2, tzinfo=UTC), "isolated-print-v1"),  # May
        _seeded_flag("SPY", stale, "isolated-print-v1"),                 # stale: this one goes
    ])
    everything = (f"SELECT {FLAG_COLUMNS} FROM intraday_bar_flags "
                  "WHERE run_id = 'seeded' ORDER BY ticker, rule_version, ts")
    before = run_sql(everything, {})
    assert len(before) == 5

    execution("exec-1")
    ibf.flag_months(("SPY",), [APRIL], commit=True, now_utc=T1)

    after = run_sql(everything, {})
    kept = before[~((before.ticker == "SPY") & (before.rule_version == "isolated-print-v1")
                    & (before.ts == _stamp(stale)))].reset_index(drop=True)
    assert len(kept) == 4
    pd.testing.assert_frame_equal(after, kept)
    assert len(_flags(run_sql, "SPY", "isolated-print-v0")) == 1
    assert len(_flags(run_sql, "QQQ")) == 1
    # April's own four flags, and the two seeded in March and May.
    assert len(_flags(run_sql)) == 6


def test_a_month_with_no_flag_still_writes_its_coverage_row(own_rows, seed, run_sql, execution):
    seed("market_data_intraday", _bars("QQQ", "2011-04-05"))
    execution("exec-1")
    out = ibf.flag_months(("QQQ",), [APRIL], commit=True, now_utc=T1)

    assert out["flags"] == 0
    assert len(_flags(run_sql, "QQQ")) == 0
    row = _coverage(run_sql, "QQQ").iloc[0]
    assert (row.flags_regular_high, row.flags_regular_low,
            row.flags_extended_high, row.flags_extended_low) == (0, 0, 0, 0)
    assert row.bars_judged == 56 and row.bars_judged > 0


def test_a_month_with_no_bar_writes_an_empty_coverage_row(own_rows, run_sql, execution):
    execution("exec-1")
    out = ibf.flag_months(("SPY",), [(2011, 8)], commit=True, now_utc=T1)

    assert out == {"months": 1, "flags": 0, "changed": 0, "seconds": out["seconds"]}
    coverage = _coverage(run_sql)
    assert len(coverage) == 1
    row = coverage.iloc[0]
    assert row.month == date(2011, 8, 1)
    assert row.bars_in_month == 0 and row.bars_judged == 0
    assert pd.isna(row.first_judged_ts) and pd.isna(row.last_judged_ts)
    assert row.session_sha256 == {} and row.bars_basis["rows"] == 0
    assert len(_flags(run_sql)) == 0
