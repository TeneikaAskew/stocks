"""--replace-months: the re-framing migration for market_data_intraday.

The migration deletes a whole month and inserts its refetch in one
transaction. Two properties make that safe, and both are checked here rather
than reasoned about:

  1. The delete window for month M holds every row M can have in EITHER
     convention (true UTC, and Eastern wall time stamped as UTC), and no row of
     M-1 or M+1 in either convention. Checked exhaustively, every minute AV can
     return (04:00-20:00 ET: AV stores a bar AT 20:00), every day, every month 2016-2027, across DST.
  2. Nothing is deleted unless the refetch succeeded and covers the sessions
     already held; dry run never writes.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import gcp.fetchers.fetch_alphavantage_intraday as fai
from lib.eastern_time import ET

UTC = timezone.utc


def _month_days(y: int, m: int):
    d = date(y, m, 1)
    while d.month == m:
        yield d
        d += timedelta(days=1)


def _extremes(y: int, m: int) -> dict[str, tuple[datetime, datetime]]:
    """Earliest and latest stored instant of month (y, m) per convention.

    AV extended hours are 04:00-20:00 ET inclusive: production holds a bar at
    exactly 20:00 ET (01:00Z the next day in winter). True UTC stores the real instant;
    the legacy writers stored the Eastern wall clock labelled UTC.
    """
    first, last = min(_month_days(y, m)), max(_month_days(y, m))
    lo_wall, hi_wall = time(4, 0), time(20, 0)
    return {
        "true_utc": (datetime.combine(first, lo_wall, ET).astimezone(UTC),
                     datetime.combine(last, hi_wall, ET).astimezone(UTC)),
        "et_label": (datetime.combine(first, lo_wall, UTC),
                     datetime.combine(last, hi_wall, UTC)),
    }


MONTHS = [(y, m) for y in range(2016, 2028) for m in range(1, 13)]


@pytest.mark.parametrize("y,m", MONTHS)
def test_window_holds_the_month_in_both_conventions(y, m):
    start, end = fai.month_replace_window(y, m)
    for conv, (lo, hi) in _extremes(y, m).items():
        assert start <= lo and hi < end, (conv, lo, hi, start, end)


@pytest.mark.parametrize("y,m", MONTHS)
def test_window_holds_no_row_of_either_neighbour(y, m):
    start, end = fai.month_replace_window(y, m)
    prev = (y - 1, 12) if m == 1 else (y, m - 1)
    nxt = (y + 1, 1) if m == 12 else (y, m + 1)
    for conv, (_, hi) in _extremes(*prev).items():
        assert hi < start, ("previous month", conv, hi, start)
    for conv, (lo, _) in _extremes(*nxt).items():
        assert lo >= end, ("next month", conv, lo, end)


# ── replace_month: never delete on a bad or short refetch ────────────────────


def _vendor_month(days: list[str]) -> pd.DataFrame:
    """fetch_month's real shape: naive Eastern ts, one bar per listed day."""
    return pd.DataFrame({
        "ts": [pd.Timestamp(f"{d} 09:30") for d in days],
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })


def test_failed_fetch_deletes_nothing():
    with patch.object(fai, "fetch_month", return_value=(None, fai.FETCH_RATE_LIMIT)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 1}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.FETCH_RATE_LIMIT
    rep.assert_not_called()


def test_refetch_missing_a_held_session_deletes_nothing():
    """We hold 09-01 and 09-02; AV returned only 09-01. Leave the month alone."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates",
                      return_value={date(2026, 9, 1): 900, date(2026, 9, 2): 900}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2026-09-01 (1/900)", "2026-09-02 (0/900)"]
    rep.assert_not_called()


def test_only_held_sessions_are_reinserted():
    """Footprint-preserving: a month holding one day gets that day back, not
    the vendor's whole month."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01", "2026-09-02", "2026-09-24"]),
                                    fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 1}), \
         patch.object(fai, "replace_rows_in_window", return_value=(12, 1)) as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK
    df = rep.call_args.args[0]
    assert list(df["ts"]) == [pd.Timestamp("2026-09-24 13:30", tz="UTC")]


def test_dry_run_never_writes():
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 1): 1}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=False)
    assert r["status"] == fai.REPLACE_DRY
    rep.assert_not_called()


def test_commit_swaps_utc_rows_over_the_month_window():
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01", "2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates",
                      return_value={date(2026, 9, 1): 1, date(2026, 9, 24): 1}), \
         patch.object(fai, "replace_rows_in_window", return_value=(900, 2)) as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK and r["deleted"] == 900
    df, table, key, ts_col, start, end = rep.call_args.args
    assert table == "market_data_intraday" and key == {"ticker": "SPY", "interval": "1min"}
    assert (start, end) == fai.month_replace_window(2026, 9)
    assert list(df["ts"]) == [pd.Timestamp("2026-09-01 13:30", tz="UTC"),
                              pd.Timestamp("2026-09-24 13:30", tz="UTC")]


def test_replace_list_parsing(tmp_path):
    p = tmp_path / "list.csv"
    p.write_text("ticker,month\n# comment\nspy,2026-09\n\nIWM, 2024-11  # winter\n")
    assert fai._read_replace_list(str(p)) == [("SPY", 2026, 9), ("IWM", 2024, 11)]


def test_replace_list_reads_from_gcs():
    blob = MagicMock()
    blob.download_as_text.return_value = "ticker,month\nQQQ,2026-09\n"
    client = MagicMock()
    client.bucket.return_value.blob.return_value = blob
    with patch("google.cloud.storage.Client", return_value=client):
        assert fai._read_replace_list("gs://b/lists/x.csv") == [("QQQ", 2026, 9)]
    client.bucket.assert_called_once_with("b")
    client.bucket.return_value.blob.assert_called_once_with("lists/x.csv")


# ── gcp.database.replace_rows_in_window: refuse before opening a transaction ─


def _rows(ts):
    return pd.DataFrame({"ticker": "SPY", "interval": "1min", "ts": ts,
                         "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1})


def test_replace_refuses_rows_outside_the_window():
    import gcp.database as db
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-10-01 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", side_effect=AssertionError("no DB call expected")), \
         pytest.raises(ValueError, match="outside"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end)


def test_replace_refuses_naive_rows_and_naive_bounds():
    import gcp.database as db
    start, end = fai.month_replace_window(2026, 9)
    with patch.object(db, "get_engine", side_effect=AssertionError("no DB call expected")):
        with pytest.raises(ValueError, match="naive"):
            db.replace_rows_in_window(_rows(pd.to_datetime(["2026-09-24 09:30"])),
                                      "market_data_intraday",
                                      {"ticker": "SPY", "interval": "1min"}, "ts", start, end)
        with pytest.raises(ValueError, match="tz-aware"):
            db.replace_rows_in_window(_rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC")),
                                      "market_data_intraday",
                                      {"ticker": "SPY", "interval": "1min"}, "ts",
                                      start.replace(tzinfo=None), end)


def test_replace_deletes_then_inserts_in_one_transaction():
    import sqlalchemy
    import gcp.database as db

    meta = sqlalchemy.MetaData()
    tbl = sqlalchemy.Table(
        "market_data_intraday", meta,
        sqlalchemy.Column("ticker", sqlalchemy.Text), sqlalchemy.Column("interval", sqlalchemy.Text),
        sqlalchemy.Column("ts", sqlalchemy.DateTime(timezone=True)),
        *[sqlalchemy.Column(c, sqlalchemy.Float) for c in ("open", "high", "low", "close")],
        sqlalchemy.Column("volume", sqlalchemy.BigInteger),
    )
    conn = MagicMock()
    conn.execute.return_value.rowcount = 7
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30", "2026-09-24 13:31"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        deleted, inserted = db.replace_rows_in_window(
            df, "market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts", start, end)
    assert (deleted, inserted) == (7, 2)
    assert engine.begin.call_count == 1, "delete and insert must share one transaction"
    first_sql = str(conn.execute.call_args_list[0].args[0])
    assert first_sql.startswith("DELETE FROM market_data_intraday")
    assert "INSERT" in str(conn.execute.call_args_list[1].args[0])


# ── run_replace_months: a green run means every month was replaced ──────────


def _run(tmp_path, monkeypatch, statuses, commit=True):
    lst = tmp_path / "l.csv"
    lst.write_text("".join(f"T{i},2026-09\n" for i in range(len(statuses))))
    monkeypatch.setattr(fai, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(fai, "_av_cfg", SimpleNamespace(delay_between_calls=0))
    results = iter(statuses)

    def fake(sym, y, m, key, commit):
        st = next(results)
        if isinstance(st, Exception):
            raise st
        return {"symbol": sym, "month": f"{y}-{m:02d}", "status": st, "deleted": 0,
                "inserted": 0, "held_sessions": 1, "missing_sessions": 0}
    monkeypatch.setattr(fai, "replace_month", fake)
    return fai.run_replace_months(str(lst), commit, None)


def test_commit_run_succeeds_only_when_every_month_is_replaced(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, [fai.REPLACE_OK, fai.REPLACE_OK]) == 0


@pytest.mark.parametrize("bad", [fai.FETCH_RATE_LIMIT, fai.REPLACE_INCOMPLETE,
                                 fai.FETCH_NO_TIMESERIES, fai.REPLACE_DRY])
def test_commit_run_fails_and_lists_retries_when_any_month_is_skipped(tmp_path, monkeypatch, caplog, bad):
    """Codex P1 on #1185: skipped months were only counted and the job still
    exited 0, so a run that left the table untouched looked complete."""
    import logging
    caplog.set_level(logging.ERROR)
    assert _run(tmp_path, monkeypatch, [fai.REPLACE_OK, bad]) == 1
    assert "RETRY T1,2026-09" in caplog.text
    assert "RETRY T0" not in caplog.text


def test_commit_run_fails_on_a_raised_month(tmp_path, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.ERROR)
    assert _run(tmp_path, monkeypatch, [RuntimeError("db down")]) == 1
    assert "RETRY T0,2026-09" in caplog.text


def test_dry_run_expects_dry_run_status(tmp_path, monkeypatch):
    assert _run(tmp_path, monkeypatch, [fai.REPLACE_DRY], commit=False) == 0
    assert _run(tmp_path, monkeypatch, [fai.REPLACE_INCOMPLETE], commit=False) == 1


# ── the 20:00 ET bar (code review C1 on #1185) ────────────────────────────────


def test_a_winter_month_end_2000_bar_is_inside_its_own_window():
    """2025-02-28 20:00 ET = 2025-03-01 01:00Z: it must belong to February's
    window, not fall on its end (which refused every winter month) nor into
    March's (which deleted it without re-inserting)."""
    bar = datetime(2025, 2, 28, 20, 0, tzinfo=ET).astimezone(UTC)
    feb, mar = fai.month_replace_window(2025, 2), fai.month_replace_window(2025, 3)
    assert feb[0] <= bar < feb[1]
    assert not (mar[0] <= bar < mar[1])


def _stored(day: str, *, stored: str, start="04:00", end="20:00") -> pd.DataFrame:
    wall = pd.date_range(f"{day} {start}", f"{day} {end}", freq="1min")
    minute = wall.hour * 60 + wall.minute
    ts = (wall.tz_localize("UTC") if stored == "et_label"
          else wall.tz_localize("America/New_York").tz_convert("UTC"))
    return pd.DataFrame({"ts": ts, "volume": [5000 if 570 <= m < 600 else 100 for m in minute]})


def _held_from(rows: pd.DataFrame, y: int, m: int) -> dict:
    start, end = fai.month_replace_window(y, m)
    win = rows[(rows["ts"] >= start) & (rows["ts"] < end)].reset_index(drop=True)
    with patch.object(fai, "query_to_dataframe_strict", return_value=win):
        return fai._held_session_dates("SPY", start, end)


def test_the_2000_bar_before_a_holiday_does_not_make_the_holiday_a_session():
    """Thanksgiving eve 2024-11-27 20:00 ET sits at raw 2024-11-28 01:00Z; it
    counts toward 11-27, and 11-28 is not a session."""
    held = _held_from(_stored("2024-11-27", stored="utc"), 2024, 11)
    assert held == {date(2024, 11, 27): 961}


def test_held_bars_count_a_collided_session_once():
    """Both writers touched 09-22: true UTC everywhere plus the legacy labels
    at raw 04:00-07:59 that the refetch never overwrote. Rows: 961 + 240;
    distinct bars: 961."""
    rows = pd.concat([_stored("2026-09-22", stored="utc"),
                      _stored("2026-09-22", stored="et_label", start="04:00", end="07:59")])
    rows = rows.drop_duplicates("ts", keep="first").sort_values("ts")
    assert len(rows) == 961 + 240
    assert _held_from(rows, 2026, 9) == {date(2026, 9, 22): 961}


def test_a_partial_refetch_touching_every_day_is_refused():
    """Codex P1 on #1185: AV returned half of each held day. Every session is
    present, so the old check passed and the month was cut in half."""
    half = pd.DataFrame({
        "ts": pd.date_range("2026-09-24 04:00", periods=480, freq="1min"),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })
    with patch.object(fai, "fetch_month", return_value=(half, fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 961}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2026-09-24 (480/961)"]
    rep.assert_not_called()


def test_a_session_a_couple_of_bars_short_is_within_tolerance():
    full = pd.DataFrame({
        "ts": pd.date_range("2026-09-24 04:00", periods=959, freq="1min"),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })
    with patch.object(fai, "fetch_month", return_value=(full, fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 961}), \
         patch.object(fai, "replace_rows_in_window", return_value=(961, 959)):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK


# ── code review H1/H2 on #1185 ────────────────────────────────────────────────


def test_a_month_holding_no_session_is_never_deleted():
    """held == {} used to leave `missing` empty and pass an empty frame to the
    replace, which deleted the whole window and inserted nothing."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_NOTHING_HELD
    rep.assert_not_called()


def _engine_with(rowcount):
    import sqlalchemy
    meta = sqlalchemy.MetaData()
    tbl = sqlalchemy.Table(
        "market_data_intraday", meta,
        sqlalchemy.Column("ticker", sqlalchemy.Text), sqlalchemy.Column("interval", sqlalchemy.Text),
        sqlalchemy.Column("ts", sqlalchemy.DateTime(timezone=True)),
        *[sqlalchemy.Column(c, sqlalchemy.Float) for c in ("open", "high", "low", "close")],
        sqlalchemy.Column("volume", sqlalchemy.BigInteger),
    )
    conn = MagicMock()
    conn.execute.return_value.rowcount = rowcount
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    return engine, conn, tbl


def test_an_oversized_delete_raises_inside_the_transaction():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=100)
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30", "2026-09-24 13:31"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}), \
         pytest.raises(ValueError, match="rolled back"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  max_delete_ratio=3.0)
    # Raised after the DELETE and before any INSERT; engine.begin() rolls back.
    assert conn.execute.call_count == 1


def test_replace_refuses_identifiers_that_are_not_table_columns():
    import gcp.database as db
    engine, _, tbl = _engine_with(rowcount=0)
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}), \
         pytest.raises(ValueError, match="not columns"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "Interval1": "1min"}, "ts", start, end)


def test_pacing_scales_with_the_task_count(tmp_path, monkeypatch):
    """N striped tasks share one AV key; each must wait delay x N between calls."""
    lst = tmp_path / "l.csv"
    lst.write_text("".join(f"T{i},2026-09\n" for i in range(8)))   # task 0 of 4 gets T0, T4
    monkeypatch.setenv("CLOUD_RUN_TASK_COUNT", "4")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "0")
    monkeypatch.setattr(fai, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(fai, "_av_cfg", SimpleNamespace(delay_between_calls=0.4))
    monkeypatch.setattr(fai, "replace_month", lambda sym, y, m, key, commit: {
        "symbol": sym, "month": f"{y}-{m:02d}", "status": fai.REPLACE_OK, "deleted": 0,
        "inserted": 0, "held_sessions": 1, "missing_sessions": 0})
    waits = []
    monkeypatch.setattr(fai.time, "sleep", waits.append)
    monkeypatch.setattr(fai.time, "time", lambda: 100.0)   # frozen clock
    assert fai.run_replace_months(str(lst), True, None) == 0
    assert waits == [pytest.approx(1.6)]   # 0.4 s x 4 tasks, before the 2nd call



@pytest.mark.parametrize("held_bars", [1, 2])
def test_a_sparse_held_session_with_no_refetched_bars_is_refused(held_bars):
    """Codex P1 on #1185: for a 1-2 bar session the shortfall tolerance let a
    refetch with zero bars for that day pass, deleting it for good."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates",
                      return_value={date(2026, 9, 1): 1, date(2026, 9, 2): held_bars}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == [f"2026-09-02 (0/{held_bars})"]
    rep.assert_not_called()


# ── Codex P1 on #1185 (8c1154a): a writer landing mid-replace ─────────────────


def test_a_session_added_after_the_precheck_rolls_the_month_back():
    """The nightly writer adds 09-25 after the held snapshot. Under the replace
    lock the re-read sees it, so nothing is deleted and the month is retried."""
    snapshots = iter([{date(2026, 9, 24): 1},                         # pre-check
                      {date(2026, 9, 24): 1, date(2026, 9, 25): 960}])  # under the lock

    def fake_replace(df, table, key, ts_col, start, end, **kw):
        kw["verify"](object())            # the real one calls this before DELETE
        raise AssertionError("verify should have raised")

    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", side_effect=lambda *a, **k: next(snapshots)), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_CHANGED


def test_replace_locks_then_verifies_before_deleting():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=1)
    order = []
    conn.execute.side_effect = lambda stmt, *a, **k: (
        order.append(str(stmt).split()[0]), MagicMock(rowcount=1))[1]
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=lambda c: order.append("VERIFY"))
    assert order[:4] == ["SET", "LOCK", "VERIFY", "DELETE"]


def test_a_failed_verify_never_reaches_the_delete():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=1)
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))

    def boom(c):
        raise RuntimeError("changed")
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}), \
         pytest.raises(RuntimeError, match="changed"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=boom)
    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert not any(q.startswith("DELETE") for q in sqls)



@pytest.mark.parametrize("held_n,fetched_n,ok", [
    (3, 1, False),      # Codex P1 on #1185 (ef85a85): 1 of 3 passed a fixed 2-bar allowance
    (3, 2, False),
    (49, 48, False),    # under 50 bars: must be whole
    (50, 49, True),     # 2% of 50 = 1
    (961, 942, True),   # 2% of 961 = 19
    (961, 941, False),
])
def test_the_shortfall_tolerance_scales_with_the_session(held_n, fetched_n, ok):
    bars = pd.DataFrame({
        "ts": pd.date_range("2026-09-24 04:00", periods=fetched_n, freq="1min"),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })
    with patch.object(fai, "fetch_month", return_value=(bars, fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): held_n}), \
         patch.object(fai, "replace_rows_in_window", return_value=(held_n, fetched_n)) as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert (r["status"] == fai.REPLACE_OK) is ok
    assert rep.called is ok


# ── Codex P1 on #1185 (f65789f): a writer landing DURING the refetch ──────────


def test_the_held_snapshot_is_taken_before_the_refetch():
    order = []
    with patch.object(fai, "_held_session_dates",
                      side_effect=lambda *a, **k: order.append("SNAPSHOT") or {date(2026, 9, 24): 1}), \
         patch.object(fai, "fetch_month",
                      side_effect=lambda *a, **k: order.append("FETCH")
                      or (_vendor_month(["2026-09-24"]), fai.FETCH_OK)):
        fai.replace_month("SPY", 2026, 9, "k", commit=False)
    assert order == ["SNAPSHOT", "FETCH"]


def test_bars_written_while_the_refetch_is_in_flight_roll_the_month_back():
    """956 bars held when the migration starts; the nightly writer adds 5 while
    AV is answering. The refetch is within tolerance of either count, so only
    a snapshot taken BEFORE the fetch lets the locked re-check see the write."""
    table = {"bars": 956}
    full = pd.DataFrame({
        "ts": pd.date_range("2026-09-24 04:00", periods=961, freq="1min"),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })

    def fetch(*a, **k):
        table["bars"] = 961                      # the writer commits mid-request
        return full.copy(), fai.FETCH_OK

    def fake_replace(df, table_name, key, ts_col, start, end, **kw):
        kw["verify"](object())                   # the real one: under the lock
        return 961, len(df)

    with patch.object(fai, "fetch_month", side_effect=fetch), \
         patch.object(fai, "_held_session_dates",
                      side_effect=lambda *a, **k: {date(2026, 9, 24): table["bars"]}), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_CHANGED


def test_a_month_holding_nothing_spends_no_vendor_call():
    with patch.object(fai, "_held_session_dates", return_value={}), \
         patch.object(fai, "fetch_month") as fetch:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_NOTHING_HELD
    fetch.assert_not_called()
