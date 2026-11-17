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


@pytest.fixture(autouse=True)
def _stable_digest(monkeypatch):
    """The row digest is a live DB read; hold it constant unless a test is
    about a change in content."""
    monkeypatch.setattr(fai, "_held_digest", lambda *a, **k: "digest-0")

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


def _held_rows(counts: dict) -> pd.DataFrame:
    """Stored rows that place as *counts* ({Eastern date: bars}): per date that
    many true-UTC rows from 04:00 Eastern, with the opening spike a real day
    has. Prices are 2.0, so no row is a copy of a _vendor_month bar (1.0)."""
    frames = []
    for d, n in counts.items():
        wall = pd.date_range(f"{d} 04:00", periods=n, freq="1min")
        minute = wall.hour * 60 + wall.minute
        frames.append(pd.DataFrame({
            "ts": wall.tz_localize("America/New_York").tz_convert("UTC"),
            "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0,
            "volume": [5000 if 570 <= m < 600 else 100 for m in minute]}))
    if not frames:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    return pd.concat(frames).reset_index(drop=True)


def test_failed_fetch_deletes_nothing():
    with patch.object(fai, "fetch_month", return_value=(None, fai.FETCH_RATE_LIMIT)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 1})), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.FETCH_RATE_LIMIT
    rep.assert_not_called()


def test_refetch_missing_a_held_session_deletes_nothing():
    """We hold 09-01 and 09-02; AV returned only 09-01. Leave the month alone."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows",
                      return_value=_held_rows({date(2026, 9, 1): 900, date(2026, 9, 2): 900})), \
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
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 1})), \
         patch.object(fai, "replace_rows_in_window", return_value=(12, 1)) as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK
    df = rep.call_args.args[0]
    assert list(df["ts"]) == [pd.Timestamp("2026-09-24 13:30", tz="UTC")]


def test_dry_run_never_writes():
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 1): 1})), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=False)
    assert r["status"] == fai.REPLACE_DRY
    rep.assert_not_called()


def test_commit_swaps_utc_rows_over_the_month_window():
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01", "2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows",
                      return_value=_held_rows({date(2026, 9, 1): 1, date(2026, 9, 24): 1})), \
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
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 961})), \
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
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 961})), \
         patch.object(fai, "replace_rows_in_window", return_value=(961, 959)):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK


# ── code review H1/H2 on #1185 ────────────────────────────────────────────────


def test_a_month_holding_no_session_is_never_deleted():
    """held == {} used to leave `missing` empty and pass an empty frame to the
    replace, which deleted the whole window and inserted nothing."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({})), \
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
         patch.object(fai, "_stored_window_rows",
                      return_value=_held_rows({date(2026, 9, 1): 1, date(2026, 9, 2): held_bars})), \
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
         patch.object(fai, "_stored_window_rows",
                      side_effect=lambda *a, **k: _held_rows(next(snapshots))), \
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
    # Row locks on this key's window only (SELECT ... FOR UPDATE), never a
    # table lock that would serialise every migration task and stall writers.
    assert order[:4] == ["SET", "SELECT", "VERIFY", "DELETE"]
    assert not any(o == "LOCK" for o in order)


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
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): held_n})), \
         patch.object(fai, "replace_rows_in_window", return_value=(held_n, fetched_n)) as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert (r["status"] == fai.REPLACE_OK) is ok
    assert rep.called is ok


# ── Codex P1 on #1185 (f65789f): a writer landing DURING the refetch ──────────


def test_the_held_snapshot_is_taken_before_the_refetch():
    order = []
    with patch.object(fai, "_stored_window_rows",
                      side_effect=lambda *a, **k: order.append("SNAPSHOT")
                      or _held_rows({date(2026, 9, 24): 1})), \
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
         patch.object(fai, "_stored_window_rows",
                      side_effect=lambda *a, **k: _held_rows({date(2026, 9, 24): table["bars"]})), \
         patch.object(fai, "_held_session_dates",
                      side_effect=lambda *a, **k: {date(2026, 9, 24): table["bars"]}), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_CHANGED


def test_a_month_holding_nothing_spends_no_vendor_call():
    with patch.object(fai, "_stored_window_rows", return_value=_held_rows({})), \
         patch.object(fai, "fetch_month") as fetch:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_NOTHING_HELD
    fetch.assert_not_called()


# ── Codex P1 on #1185 (a1d6354): a same-count write between fetch and lock ────


def _full_session(day="2026-09-24", n=961) -> pd.DataFrame:
    return pd.DataFrame({
        "ts": pd.date_range(f"{day} 04:00", periods=n, freq="1min"),
        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1,
        "ticker": "SPY", "interval": "1min", "data_source": "alphavantage",
    })


def test_a_same_count_upsert_during_the_refetch_rolls_the_month_back():
    """The nightly writer upserts revised values at keys already held while AV
    is answering. Bar counts are unchanged, so only the row digest sees it."""
    table = {"digest": "before"}

    def fetch(*a, **k):
        table["digest"] = "after"                # same keys, new values
        return _full_session(), fai.FETCH_OK

    def fake_replace(df, table_name, key, ts_col, start, end, **kw):
        kw["verify"](object())
        return 961, len(df)

    with patch.object(fai, "fetch_month", side_effect=fetch), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 961})), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 961}), \
         patch.object(fai, "_held_digest", side_effect=lambda *a, **k: table["digest"]), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_CHANGED
    assert "content" in r["detail"]


def test_a_write_between_the_snapshot_and_the_digest_rolls_the_month_back():
    """Codex P1 on #1955 (472fd8ee): the rows classify_stored_rows reads and
    the digest the locked re-check compares with must describe the same
    table. A writer that commits between the two reads changes values the
    classification never saw; with the digest read second, the re-check
    matches the newer digest and the swap deletes on the old reading. The
    digest is read first, so the same write leaves the re-check differing."""
    start, end = fai.month_replace_window(2026, 9)
    table = {"digest": "before"}
    order = []

    def write():                                   # same keys, new values
        table["digest"] = "after"

    def snapshot(*a, **k):
        order.append("SNAPSHOT")
        rows = _held_rows({date(2026, 9, 24): 961})
        if order == ["SNAPSHOT"]:
            write()                                # lands right after this read
        return rows

    def digest(symbol, s, e, conn=None):
        if (s, e) != (start, end):
            return "tail"                          # the strip past the window
        order.append("DIGEST" if conn is None else "LOCKED")
        value = table["digest"]
        if order == ["DIGEST"]:
            write()                                # lands right after this read
        return value

    def fake_replace(df, table_name, key, ts_col, s, e, **kw):
        kw["verify"](object())
        return 961, len(df)

    with patch.object(fai, "fetch_month", return_value=(_full_session(), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", side_effect=snapshot), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 961}), \
         patch.object(fai, "_held_digest", side_effect=digest), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace) as swap:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_CHANGED
    assert "content" in r["detail"]
    swap.assert_called_once()                      # refused under the lock, nothing deleted
    assert order == ["DIGEST", "SNAPSHOT", "LOCKED"]


def test_an_unchanged_month_still_replaces_under_the_digest_check():
    with patch.object(fai, "fetch_month", return_value=(_full_session(), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 961})), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 961}), \
         patch.object(fai, "replace_rows_in_window",
                      side_effect=lambda df, *a, **kw: (kw["verify"](object()), (961, len(df)))[1]):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK


def test_a_dry_run_takes_no_digest():
    with patch.object(fai, "fetch_month", return_value=(_full_session(), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 961})), \
         patch.object(fai, "_held_digest") as dig:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=False)
    assert r["status"] == fai.REPLACE_DRY
    dig.assert_not_called()


# ── Codex P1 on #1185 (68ee4ea): an all-ticker verification pass ─────────────


def _stored_month_rows(conv: str, days=("2026-09-23", "2026-09-24")) -> pd.DataFrame:
    frames = []
    for d in days:
        wall = pd.date_range(f"{d} 04:00", f"{d} 20:00", freq="1min")
        minute = wall.hour * 60 + wall.minute
        vol = [5000 if 570 <= m < 600 else 100 for m in minute]
        c = conv if conv != "mixed" else ("utc" if d == days[0] else "et_label")
        ts = (wall.tz_localize("UTC") if c == "et_label"
              else wall.tz_localize("America/New_York").tz_convert("UTC"))
        frames.append(pd.DataFrame({"ts": ts, "volume": vol}))
    return pd.concat(frames).reset_index(drop=True)


@pytest.mark.parametrize("conv,status", [("utc", "clean"), ("et_label", "legacy"),
                                         ("mixed", "legacy")])
def test_verify_month_flags_any_legacy_rows(conv, status):
    with patch.object(fai, "query_to_dataframe_strict", return_value=_stored_month_rows(conv)):
        r = fai.verify_month("ZZZ", 2026, 9)
    assert r["status"] == status
    assert (r["label_rows"] == 0) == (status == "clean")


def test_verify_month_flags_a_collided_session():
    """Both writers touched one session: legacy premarket labels survive beside
    the true-UTC rows. The reader drops them, and the month is not clean."""
    true = _stored_month_rows("utc", days=("2026-09-22",))
    stale = true.head(0)
    wall = pd.date_range("2026-09-22 04:00", "2026-09-22 07:59", freq="1min")
    stale = pd.DataFrame({"ts": wall.tz_localize("UTC"), "volume": 100})
    with patch.object(fai, "query_to_dataframe_strict",
                      return_value=pd.concat([true, stale]).reset_index(drop=True)):
        r = fai.verify_month("SPY", 2026, 9)
    assert r["status"] == "legacy"
    assert r["dropped_rows"] == 240


def test_run_verify_months_fails_on_any_legacy_month(tmp_path, caplog):
    lst = tmp_path / "l.csv"
    lst.write_text("ticker,month\nAAA,2026-09\nBBB,2026-09\n")
    rows = {"AAA": _stored_month_rows("utc"), "BBB": _stored_month_rows("et_label")}
    with patch.object(fai, "query_to_dataframe_strict",
                      side_effect=lambda sql, params, **k: rows[params["t"]]):
        rc = fai.run_verify_months(str(lst), None)
    assert rc == 1
    assert "VERIFY-FAIL BBB,2026-09" in caplog.text
    assert "VERIFY-FAIL AAA" not in caplog.text


def test_run_verify_months_passes_when_all_clean(tmp_path):
    lst = tmp_path / "l.csv"
    lst.write_text("AAA,2026-09\n")
    with patch.object(fai, "query_to_dataframe_strict", return_value=_stored_month_rows("utc")):
        assert fai.run_verify_months(str(lst), None) == 0


def test_run_verify_months_fails_on_an_empty_listed_month(tmp_path, caplog):
    """Codex P1 on #1185 (4d466b6): a listed month with no rows is missing
    data, not a pass."""
    lst = tmp_path / "l.csv"
    lst.write_text("AAA,2026-09\n")
    with patch.object(fai, "query_to_dataframe_strict",
                      return_value=pd.DataFrame(columns=["ts", "volume"])):
        assert fai.run_verify_months(str(lst), None) == 1
    assert "VERIFY-FAIL AAA,2026-09 status=empty" in caplog.text


# ── Codex P1 on #1185 (7d4d6d0): lock the window's rows, not the table ───────


def test_the_lock_is_a_row_lock_on_this_key_and_window():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=1)
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=lambda c: None)
    sqls = [" ".join(str(c.args[0]).split()) for c in conn.execute.call_args_list]
    lock = [q for q in sqls if "FOR UPDATE" in q]
    assert len(lock) == 1
    assert "ticker = :k_ticker" in lock[0] and "ts >= :w_start AND ts < :w_end" in lock[0]
    assert not any(q.startswith("LOCK TABLE") for q in sqls)


def test_a_row_inserted_after_the_lock_rolls_the_month_back():
    """A new key committed between the row lock and the DELETE is not a locked
    row; the DELETE then removes more rows than were locked and verified."""
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=0)

    def execute(stmt, *a, **k):
        q = str(stmt)
        r = MagicMock()
        r.scalar_one.return_value = 961          # rows locked and verified
        r.rowcount = 962 if q.startswith("DELETE") else 0   # one more at DELETE time
        return r
    conn.execute.side_effect = execute
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}), \
         pytest.raises(db.WindowChanged, match="962 rows, 961 were locked"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=lambda c: None)
    sqls = [str(c.args[0]) for c in conn.execute.call_args_list]
    assert not any("INSERT" in q for q in sqls)


def test_replace_month_reports_a_window_change_as_changed():
    def fake_replace(*a, **k):
        import gcp.database as db
        raise db.WindowChanged("a writer added rows")
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 1})), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_CHANGED


# ── Codex P1 on #1185 (3dd141d): derived rows keyed by the moved timestamps ──


def test_replace_clears_derived_rows_for_the_window_in_the_same_transaction():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=1)
    seen = []

    def execute(stmt, *a, **k):
        q = " ".join(str(stmt).split())
        seen.append(q)
        r = MagicMock()
        r.rowcount = 7 if q.startswith("DELETE FROM intraday_flow_15m") else 1
        r.scalar.return_value = None if "'realtime_gex_15m'" in str(a) else "exists"
        r.scalar_one.return_value = 1
        return r
    conn.execute.side_effect = execute
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    cleared = {}
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=lambda c: None,
                                  clear_tables=("intraday_flow_15m", "realtime_gex_15m"),
                                  cleared=cleared)
    flow = [q for q in seen if q.startswith("DELETE FROM intraday_flow_15m")]
    assert flow == ["DELETE FROM intraday_flow_15m WHERE ticker = :k_ticker "
                    "AND ts >= :w_start AND ts < :w_end"]
    assert not any(q.startswith("DELETE FROM realtime_gex_15m") for q in seen)  # absent table
    assert cleared == {"intraday_flow_15m": 7}
    # After the source DELETE and INSERT, inside the one engine.begin().
    assert seen.index(flow[0]) > max(i for i, q in enumerate(seen) if q.startswith("INSERT"))


def test_replace_month_clears_every_ts_keyed_derived_table():
    captured = {}

    def fake_replace(df, table, key, ts_col, start, end, **kw):
        captured.update(kw)
        kw["cleared"].update({"strat_features_1m": 390})
        return 961, len(df)
    with patch.object(fai, "fetch_month", return_value=(_vendor_month(["2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({date(2026, 9, 24): 1})), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK
    assert set(captured["clear_tables"]) >= {"intraday_flow_15m", "intraday_gex_15m",
                                            "realtime_gex_15m", "strat_features_1m",
                                            "strat_features_60m"}
    assert r["derived_cleared"] == {"strat_features_1m": 390}


def test_a_bad_derived_table_name_is_refused():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=1)
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}), \
         pytest.raises(ValueError, match="bad derived table"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  clear_tables=("x; DROP TABLE y",))


# ── Codex P1 x2 on #1185 (65bdc4f) ───────────────────────────────────────────


@pytest.mark.parametrize("body", ["", "ticker,month\n", "# only a comment\n"])
def test_an_empty_verification_list_fails(tmp_path, caplog, body):
    lst = tmp_path / "l.csv"
    lst.write_text(body)
    with patch.object(fai, "query_to_dataframe_strict") as q:
        assert fai.run_verify_months(str(lst), None) == 1
    q.assert_not_called()
    assert "nothing was verified" in caplog.text


def test_a_short_list_leaves_a_task_empty_without_failing(tmp_path, monkeypatch):
    """Two tasks, one item: task 1 gets nothing, which is not the failure."""
    lst = tmp_path / "l.csv"
    lst.write_text("AAA,2026-09\n")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "1")
    monkeypatch.setenv("CLOUD_RUN_TASK_COUNT", "2")
    assert fai.run_verify_months(str(lst), None) == 0


def test_an_empty_replace_list_fails(tmp_path):
    lst = tmp_path / "l.csv"
    lst.write_text("ticker,month\n")
    with patch.object(fai, "replace_month") as rm:
        assert fai.run_replace_months(str(lst), commit=True, limit=None) == 1
    rm.assert_not_called()


def test_a_committed_run_lists_replaced_windows_and_every_result_to_recompute(tmp_path, caplog):
    lst = tmp_path / "l.csv"
    lst.write_text("SPY,2026-09\n")
    ok = {"symbol": "SPY", "month": "2026-09", "status": fai.REPLACE_OK,
          "held_sessions": 1, "missing_sessions": 0, "deleted": 1, "inserted": 1}
    with patch.object(fai, "get_api_keys", return_value=["k"]), \
         patch.object(fai, "replace_month", return_value=ok), \
         patch.object(fai.time, "sleep"):
        assert fai.run_replace_months(str(lst), commit=True, limit=None) == 0
    assert "REPLACED SPY,2026-09" in caplog.text
    for table in ("historical_signals", "premarket_analysis", "signal_alerts",
                  "market_data_daily"):
        assert f"RECOMPUTE {table}" in caplog.text



def test_the_recompute_advice_never_names_a_destructive_or_no_op_command():
    """Codex P1 x2 on #1185 (ee9912e): the EOD resolver never re-selects
    resolved alerts and backfill_daily_indicators never reads bars, so naming
    them was a no-op; and --force --start-date <window> would have deleted
    every earlier historical_signals row for the ticker."""
    adv = fai.BAR_DERIVED_RESULTS
    assert "python -m gcp.signal_monitor_eod_resolver --re-resolve" in adv["signal_alerts exits"] and "--from" in adv["signal_alerts exits"] and "--to" in adv["signal_alerts exits"]
    assert "NO PATH YET" not in adv["signal_alerts exits"] and "#1190" not in adv["signal_alerts exits"]
    premarket = next(v for k, v in adv.items() if k.startswith("market_data_daily"))
    assert "python -m gcp.fetchers.fetch_market_data --recompute-premarket" in premarket and "--from" in premarket and "--to" in premarket and not any(old in premarket for old in ("NO PATH YET", "#1190", "backfill_daily_indicators"))
    hs = adv["historical_signals / signal_metrics"]
    assert "FULL regeneration" in hs and "earliest" in hs


# ── FEAT-DATA-001, replace-months: label copies and late vendor bars ─────────
#
# Spec: docs/superpowers/specs/2026-11-14-feat-data-001-replace-held-session-window.md


def _swap_engine(deleted: int):
    """_engine_with, with a lock count that equals the DELETE's row count (the
    swap rolls back when they differ) and every executed statement recorded."""
    engine, conn, tbl = _engine_with(rowcount=deleted)
    calls = []

    def execute(stmt, *a, **k):
        q = " ".join(str(stmt).split())
        calls.append((q, a[0] if a else None))
        r = MagicMock()
        r.scalar_one.return_value = deleted
        r.scalar.return_value = "exists"
        r.rowcount = deleted if q.startswith("DELETE FROM market_data_intraday") else 1
        return r
    conn.execute.side_effect = execute
    return engine, tbl, calls


def test_the_swap_spares_the_listed_keys():
    """Design 4: the lock statement and the DELETE leave the spared keys alone,
    the derived-table clears keep the whole window, and the delete-ratio check
    counts the rows deleted, not the rows of the window."""
    import gcp.database as db
    start, end = fai.month_replace_window(2018, 3)
    spare = [pd.Timestamp("2018-03-01 02:04", tz="UTC"), pd.Timestamp("2018-03-01 03:10", tz="UTC")]
    df = _rows(pd.DatetimeIndex(["2018-03-01 14:30", "2018-03-01 14:31"], tz="UTC"))
    key = {"ticker": "SPY", "interval": "1min"}

    def swap(deleted, frame=df, spare_ts=spare):
        engine, tbl, calls = _swap_engine(deleted)
        with patch.object(db, "get_engine", return_value=engine), \
             patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
            out = db.replace_rows_in_window(
                frame, "market_data_intraday", key, "ts", start, end,
                max_delete_ratio=3.0, verify=lambda c: None,
                clear_tables=("intraday_flow_15m",), spare_ts=spare_ts)
        return out, calls

    out, calls = swap(deleted=6)
    # 6 deleted for 2 inserted is exactly the ratio. Counting the 2 spared rows
    # as deleted would make it 8 and roll the swap back.
    assert out == (6, 2)
    lock = [(q, p) for q, p in calls if "FOR UPDATE" in q]
    delete = [(q, p) for q, p in calls if q.startswith("DELETE FROM market_data_intraday")]
    assert len(lock) == 1 and len(delete) == 1
    for q, p in lock + delete:
        assert "AND ts NOT IN" in q, q
        assert list(p["w_spare"]) == spare
    derived = [(q, p) for q, p in calls if q.startswith("DELETE FROM intraday_flow_15m")]
    assert [q for q, _ in derived] == ["DELETE FROM intraday_flow_15m WHERE ticker = :k_ticker "
                                       "AND ts >= :w_start AND ts < :w_end"]
    assert "w_spare" not in derived[0][1]

    with pytest.raises(ValueError, match="rolled back"):
        swap(deleted=7)

    # Refused before the transaction opens: nothing may reach the database.
    with patch.object(db, "get_engine", side_effect=AssertionError("no DB call expected")):
        with pytest.raises(ValueError, match="spared"):
            db.replace_rows_in_window(
                _rows(pd.DatetimeIndex(["2018-03-01 02:04", "2018-03-01 14:30"], tz="UTC")),
                "market_data_intraday", key, "ts", start, end, spare_ts=spare)
        with pytest.raises(ValueError, match="outside"):
            db.replace_rows_in_window(df, "market_data_intraday", key, "ts", start, end,
                                      spare_ts=[pd.Timestamp("2018-04-01 02:00", tz="UTC")])
        with pytest.raises(ValueError, match="tz-aware"):
            db.replace_rows_in_window(df, "market_data_intraday", key, "ts", start, end,
                                      spare_ts=[pd.Timestamp("2018-03-01 02:04")])

    # With nothing to spare the two statements are the ones of before.
    out, calls = swap(deleted=6, spare_ts=())
    assert out == (6, 2)
    lock_q, lock_p = next((q, p) for q, p in calls if "FOR UPDATE" in q)
    del_q, del_p = next((q, p) for q, p in calls if q.startswith("DELETE FROM market_data_intraday"))
    assert lock_q == ("SELECT count(*) FROM (SELECT 1 FROM market_data_intraday WHERE ticker = :k_ticker "
                      "AND interval = :k_interval AND ts >= :w_start AND ts < :w_end FOR UPDATE) locked")
    assert del_q == ("DELETE FROM market_data_intraday WHERE ticker = :k_ticker "
                     "AND interval = :k_interval AND ts >= :w_start AND ts < :w_end")
    assert "w_spare" not in lock_p and "w_spare" not in del_p


# -- written-out rows: a vendor month, and how the table holds it ------------

FIELDS = ["open", "high", "low", "close", "volume"]


def _bars(day: str, minutes, sym: str = "IWM") -> pd.DataFrame:
    """fetch_month's shape for the listed Eastern minutes of *day* (minutes
    since midnight; past 1439 is not used). Every bar's five fields differ from
    every other bar's, and 09:30-09:59 carries the opening volume."""
    minutes = list(minutes)
    o = [200 + m / 100.0 for m in minutes]
    return pd.DataFrame({
        "ts": [pd.Timestamp(day) + pd.Timedelta(minutes=m) for m in minutes],
        "open": o, "high": [x + 0.05 for x in o], "low": [x - 0.05 for x in o],
        "close": [x + 0.01 for x in o],
        "volume": [50000 + (m * 7919) % 9000 if 570 <= m < 600 else 100 + (m * 7919) % 900
                   for m in minutes],
        "ticker": sym, "interval": "1min", "data_source": "alphavantage",
    })


def _true_rows(v: pd.DataFrame) -> pd.DataFrame:
    """The bars as a converting writer stores them: at their UTC instants."""
    return v.assign(ts=v["ts"].dt.tz_localize("America/New_York").dt.tz_convert("UTC"))[["ts"] + FIELDS]


def _label_rows(v: pd.DataFrame, lo_hour: int = 0, hi_hour: int = 24) -> pd.DataFrame:
    """The bars of Eastern hours [lo, hi) as the legacy writers stored them:
    the Eastern clock stamped as UTC."""
    hour = v["ts"].dt.hour
    w = v[(hour >= lo_hour) & (hour < hi_hour)]
    return w.assign(ts=w["ts"].dt.tz_localize("UTC"))[["ts"] + FIELDS]


def _refetch(v: pd.DataFrame) -> pd.DataFrame:
    """The refetch as replace_month hands it to classify_stored_rows: the
    vendor's naive Eastern stamp kept as ``ts_et`` beside the UTC key."""
    return v.assign(ts_et=v["ts"], ts=fai.eastern_index_to_utc(v["ts"]))


def _iwm_session() -> pd.DataFrame:
    """One vendor session shaped like IWM 2026-04-10 (spec, Problem 1): 842
    bars, a thin premarket (57, 43, 46 and 60 bars in the hours 04 to 07),
    every minute from 08:00 to 16:00, then 16:01 to 18:35."""
    minutes = (list(range(240, 240 + 57)) + list(range(300, 300 + 43))
               + list(range(360, 360 + 46)) + list(range(420, 480))
               + list(range(480, 961)) + list(range(961, 961 + 155)))
    assert len(minutes) == 842
    return _bars("2026-04-10", minutes)


def _iwm_stored(v: pd.DataFrame, copies: bool = True) -> pd.DataFrame:
    """How the table holds that session after both writers: the 842 bars at
    their true keys; the 206 premarket bars again under the Eastern label, at
    UTC 04:00-07:59; and, with *copies*, the Eastern-labelled rows of the
    08:00-10:59 bars that the true-UTC rewrite never overwrote, because no
    true bar uses their key (34 of them)."""
    true = _true_rows(v)
    parts = [true, _label_rows(v, 4, 8)]
    if copies:
        later = _label_rows(v, 8, 11)
        parts.append(later[~later["ts"].isin(true["ts"])])
    out = pd.concat(parts)
    assert not out["ts"].duplicated().any()
    return out.sort_values("ts").reset_index(drop=True)


IWM_DAY = date(2026, 4, 10)


class _World:
    """The table and the vendor, as replace_month sees them, held in memory.

    ``rows[symbol][key]`` is ``(open, high, low, close, volume, inserted_at)``.
    The swap does what replace_rows_in_window does, in its order: verify()
    first, then delete the range's unspared keys and write the frame with a
    new inserted_at. ``events`` records every read, fetch and swap in order.
    """

    def __init__(self):
        self.rows: dict = {}
        self.vendor: dict = {}
        self.events: list = []
        self.during_fetch = None       # called as f(world) while the vendor answers
        self.after_swap: dict = {}     # {swap number: f(world)}, after that swap commits
        self.fail_swap: dict = {}      # {swap number: exception raised in place of it}
        self.fail_keys = None          # exception raised by the key read
        self.swap = MagicMock(side_effect=self._swap)

    def store(self, sym: str, frame: pd.DataFrame, inserted_at: str = "2026-04-13") -> "_World":
        table = self.rows.setdefault(sym, {})
        for r in frame.itertuples(index=False):
            table[r.ts] = (r.open, r.high, r.low, r.close, r.volume, inserted_at)
        return self

    def serve(self, sym: str, y: int, m: int, frame: pd.DataFrame) -> "_World":
        self.vendor[(sym, y, m)] = frame
        return self

    def _range(self, sym, start, end) -> list:
        return sorted((k, v) for k, v in self.rows.get(sym, {}).items() if start <= k < end)

    def frame(self, sym, start, end) -> pd.DataFrame:
        items = self._range(sym, start, end)
        out = pd.DataFrame([v[:5] for _, v in items], columns=FIELDS)
        out.insert(0, "ts", pd.DatetimeIndex([k for k, _ in items], tz="UTC"))
        return out

    def _snapshot(self, sym, start, end):
        self.events.append(("rows", start, end))
        return self.frame(sym, start, end)

    def _keys(self, sym, start, end):
        self.events.append(("keys", start, end))
        if self.fail_keys is not None:
            raise self.fail_keys
        return [k for k, _ in self._range(sym, start, end)]

    def _digest(self, sym, start, end, conn=None):
        self.events.append(("digest", start, end, conn is not None))
        return repr(self._range(sym, start, end))

    def _fetch(self, sym, y, m, api_key):
        self.events.append(("fetch",))
        if self.during_fetch is not None:
            self.during_fetch(self)
        answer = self.vendor[(sym, y, m)]
        if isinstance(answer, str):            # a FETCH_* failure reason
            return None, answer
        return answer.copy(), fai.FETCH_OK

    def _swap(self, df, table, key, ts_col, start, end, **kw):
        n = self.swap.call_count
        self.events.append(("swap", n))
        if n in self.fail_swap:
            raise self.fail_swap[n]
        if kw.get("verify"):
            kw["verify"](object())
        stored = self.rows[key["ticker"]]
        spare = set(kw.get("spare_ts") or ())
        assert not spare & set(df[ts_col]), "the real swap refuses a frame at a spared key"
        gone = [k for k in stored if start <= k < end and k not in spare]
        for k in gone:
            del stored[k]
        for r in df.itertuples(index=False):
            stored[r.ts] = (r.open, r.high, r.low, r.close, r.volume, "this run")
        if n in self.after_swap:
            self.after_swap[n](self)
        return len(gone), len(df)

    def running(self):
        from contextlib import ExitStack
        stack = ExitStack()
        for name, fake in (
                ("_stored_window_rows", self._snapshot),
                ("_held_session_dates",
                 lambda sym, a, b, conn=None: fai._placed_session_counts(self.frame(sym, a, b))),
                ("_stored_keys", self._keys),
                ("_held_digest", self._digest),
                ("fetch_month", self._fetch)):
            stack.enter_context(patch.object(fai, name, side_effect=fake))
        stack.enter_context(patch.object(fai, "replace_rows_in_window", self.swap))
        return stack


def _replace(stored: pd.DataFrame, vendor: pd.DataFrame, sym: str, y: int, m: int,
             commit: bool, world: _World | None = None):
    """replace_month over written-out rows: *stored* is the table (any range),
    *vendor* the month the vendor returns. Returns (result, the swap mock)."""
    world = (world or _World()).store(sym, stored).serve(sym, y, m, vendor)
    with world.running():
        return fai.replace_month(sym, y, m, "k", commit=commit), world.swap


# -- Design 2: the snapshot is one strict read of the window's rows ----------


def test_the_snapshot_reads_the_five_fields_once_and_strictly():
    """One read before the refetch, with the fields the label-copy test needs.
    A database error is raised: it never reads as "nothing held", and no vendor
    call is spent after it."""
    reads = []

    def read(sql, params, **kw):
        reads.append((" ".join(sql.split()), params, kw))
        return _held_rows({date(2026, 9, 24): 1})

    with patch.object(fai, "query_to_dataframe_strict", side_effect=read), \
         patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-24"]), fai.FETCH_OK)):
        r = fai.replace_month("SPY", 2026, 9, "k", commit=False)
    assert r["status"] == fai.REPLACE_DRY
    assert len(reads) == 1
    sql, params, kw = reads[0]
    assert sql.startswith("SELECT ts, open, high, low, close, volume FROM market_data_intraday")
    start, end = fai.month_replace_window(2026, 9)
    assert params == {"t": "SPY", "s": start, "e": end}
    assert kw == {"timeout_s": 120}

    with patch.object(fai, "query_to_dataframe_strict", side_effect=RuntimeError("db down")), \
         patch.object(fai, "fetch_month") as fetch, \
         pytest.raises(RuntimeError, match="db down"):
        fai.replace_month("SPY", 2026, 9, "k", commit=True)
    fetch.assert_not_called()


def test_held_session_dates_is_unchanged():
    """_held_session_dates keeps its read (ts, volume) and its result."""
    rows = pd.concat([_stored("2026-09-22", stored="utc"),
                      _stored("2026-09-22", stored="et_label", start="04:00", end="07:59")])
    rows = rows.drop_duplicates("ts", keep="first").sort_values("ts")
    start, end = fai.month_replace_window(2026, 9)
    reads = []

    def read(sql, params, **kw):
        reads.append(" ".join(sql.split()))
        return rows.reset_index(drop=True)

    with patch.object(fai, "query_to_dataframe_strict", side_effect=read):
        assert fai._held_session_dates("SPY", start, end) == {date(2026, 9, 22): 961}
    assert len(reads) == 1 and reads[0].startswith("SELECT ts, volume FROM market_data_intraday")


# -- Design 3: both sides are counted over the window and nothing else -------


@pytest.mark.parametrize("commit", [False, True])
def test_a_returned_late_bar_does_not_stand_in_for_a_missing_window_bar(commit):
    """2018-02-28 holds 09:30, 20:59 and 21:04 Eastern. The first two lie in
    February's window; 21:04 is 2018-03-01 02:04Z, past its end. A refetch with
    20:59 and 21:04 but no 09:30 holds one bar of the window's two. Counting
    the late bar for the session read two against two, and the swap deleted
    09:30."""
    v = _bars("2018-02-28", [570, 20 * 60 + 59, 21 * 60 + 4], "SPY")
    stored = _true_rows(v)
    start, end = fai.month_replace_window(2018, 2)
    assert list(stored["ts"] < end) == [True, True, False]
    r, swap = _replace(stored, v[v["ts"].dt.hour >= 20], "SPY", 2018, 2, commit)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2018-02-28 (1/2)"]
    swap.assert_not_called()


# -- Design 1 and 3: which stored rows count, decided from the refetch -------


def test_classify_counts_the_measured_iwm_shape():
    v = _iwm_session()
    stored = _iwm_stored(v)
    assert len(stored) == 842 + 206 + 34
    c = fai.classify_stored_rows(stored, _refetch(v), 2026, 4)
    assert c.held == {IWM_DAY: 842}
    assert c.rows == 1082
    assert c.label_dropped == 206
    assert c.label_copies == 34
    assert c.by_utc_hour == {4: 57, 5: 43, 6: 46, 7: 60, 8: 3, 9: 17, 10: 14}
    assert c.carry_in_keys == []


def _one_copy(stored: pd.DataFrame, v: pd.DataFrame) -> pd.Timestamp:
    """The key of one of the 34 label copies: the first stored row of UTC
    08:00-10:59 that is not at a refetched bar's true key."""
    true_keys = set(_true_rows(v)["ts"])
    hour = stored["ts"].dt.hour
    return next(k for k in stored["ts"][(hour >= 8) & (hour < 11)] if k not in true_keys)


@pytest.mark.parametrize("field", FIELDS)
def test_a_row_equal_in_four_fields_of_five_is_counted(field):
    """The comparison is exact and takes all five fields: the smallest change
    to any one of them makes the row a bar of its own, which the refetch must
    then return."""
    v = _iwm_session()
    stored = _iwm_stored(v)
    at = stored["ts"] == _one_copy(stored, v)
    stored.loc[at, field] = stored.loc[at, field] + (1 if field == "volume" else 0.0001)
    c = fai.classify_stored_rows(stored, _refetch(v), 2026, 4)
    assert c.label_copies == 33
    assert c.held == {IWM_DAY: 843}


@pytest.mark.parametrize("field", FIELDS)
def test_a_null_field_never_equals(field):
    """NULL in the stored row and in the refetched bar is not a match."""
    v = _iwm_session()
    stored = _iwm_stored(v).astype({f: "float64" for f in FIELDS})
    key = _one_copy(stored, v)
    stored.loc[stored["ts"] == key, field] = float("nan")
    ref = _refetch(v).astype({f: "float64" for f in FIELDS})
    ref.loc[ref["ts_et"] == key.tz_localize(None), field] = float("nan")
    assert ref[field].isna().sum() == 1
    c = fai.classify_stored_rows(stored, ref, 2026, 4)
    assert c.label_copies == 33
    assert c.held == {IWM_DAY: 843}


def test_fields_stored_as_decimal_compare_as_numbers():
    """A driver that hands the prices over as Decimal must not turn every
    copy into a bar of its own (Decimal('205.1') != 205.1 in Python)."""
    from decimal import Decimal
    v = _iwm_session()
    stored = _iwm_stored(v).astype({f: "object" for f in FIELDS})
    for f in ("open", "high", "low", "close"):
        stored[f] = [Decimal(repr(float(x))) for x in stored[f]]
    stored["volume"] = [None if x is None else int(x) for x in stored["volume"]]
    c = fai.classify_stored_rows(stored, _refetch(v), 2026, 4)
    assert (c.label_copies, c.label_dropped, c.held) == (34, 206, {IWM_DAY: 842})


def test_a_naive_stored_frame_classifies_like_an_aware_one():
    """pg8000 can hand TIMESTAMPTZ back without a zone in a UTC session; the
    resolver reads that as UTC and so does the classifier."""
    v = _iwm_session()
    stored = _iwm_stored(v)
    naive = stored.assign(ts=stored["ts"].dt.tz_localize(None))
    assert (fai.classify_stored_rows(naive, _refetch(v), 2026, 4)
            == fai.classify_stored_rows(stored, _refetch(v), 2026, 4))


def test_a_copy_at_a_key_the_refetch_returns_is_counted():
    """The label row of the 08:00 bar sits at 08:00Z, the true key of the
    04:00 bar, which the refetch returns. It is a label copy, but its key gets
    a bar from the swap, so it stays counted: the minute is held and fetched."""
    v = _iwm_session()
    stored = _iwm_stored(v)
    key = pd.Timestamp("2026-04-10 08:00", tz="UTC")
    eight = _label_rows(v, 8, 9).iloc[0]
    assert eight["ts"] == key and key in set(_true_rows(v)["ts"])
    for f in FIELDS:
        stored.loc[stored["ts"] == key, f] = eight[f]
    # Without the 04:00Z label row no other stored row shares its Eastern minute.
    stored = stored[stored["ts"] != pd.Timestamp("2026-04-10 04:00", tz="UTC")]
    c = fai.classify_stored_rows(stored, _refetch(v), 2026, 4)
    assert c.label_copies == 34
    assert c.label_dropped == 205
    assert c.held == {IWM_DAY: 842}


def test_label_read_rows_count_as_today():
    """A month held only under the Eastern label: every row is, by the
    definition, a label copy, and every one counts (Design 3, Problem 3)."""
    v = _bars("2026-04-10", range(240, 1201))
    c = fai.classify_stored_rows(_label_rows(v), _refetch(v), 2026, 4)
    assert c.held == {IWM_DAY: 961}
    assert (c.rows, c.label_copies, c.label_dropped, c.by_utc_hour, c.carry_in_keys) == (961, 0, 0, {}, [])


FEB_LATE = [pd.Timestamp("2018-03-01 02:04", tz="UTC"), pd.Timestamp("2018-03-01 03:10", tz="UTC"),
            pd.Timestamp("2018-03-01 04:37", tz="UTC")]


def _feb_late_and_march() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(stored, March's vendor month): February's bars of 21:04, 22:10 and
    23:37 Eastern on the 28th, stored at their true keys, which lie in March's
    window; and a full first session of March."""
    late = _bars("2018-02-28", [21 * 60 + 4, 22 * 60 + 10, 23 * 60 + 37], "SPY")
    march = _bars("2018-03-01", range(240, 1201), "SPY")
    stored = pd.concat([_true_rows(late), _true_rows(march)]).reset_index(drop=True)
    assert list(stored["ts"][:3]) == FEB_LATE
    return stored, march


def test_rows_before_the_months_eastern_midnight_are_carry_ins():
    """March's carry strip is [03-01 02:00Z, 03-01 05:00Z). February's late
    bars in it are not counted for March and are not uncounted either: the
    04:37Z one loses its Eastern minute as a label of March 1 (how the dry run
    came to print 0/2 and not 0/3) and is still a carry-in."""
    stored, march = _feb_late_and_march()
    c = fai.classify_stored_rows(stored, _refetch(march), 2018, 3)
    assert c.carry_in_keys == FEB_LATE
    assert c.held == {date(2018, 3, 1): 961}
    assert (c.rows, c.label_dropped, c.label_copies, c.by_utc_hour) == (964, 0, 0, {})


def test_a_true_read_row_that_lost_its_minute_is_not_uncounted():
    """A label-verdict session plus the true-UTC 20:00 bar at 00:00Z the next
    day: the label row keeps the minute. The true row is re-inserted at its
    own key by the swap, so it is neither counted twice nor reported as a row
    written back nowhere."""
    v = _bars("2026-04-10", range(240, 1201))
    spill = _true_rows(v[v["ts"] == pd.Timestamp("2026-04-10 20:00")])
    assert list(spill["ts"]) == [pd.Timestamp("2026-04-11 00:00", tz="UTC")]
    c = fai.classify_stored_rows(pd.concat([_label_rows(v), spill]), _refetch(v), 2026, 4)
    assert c.held == {IWM_DAY: 961}
    assert (c.rows, c.label_dropped, c.label_copies, c.by_utc_hour) == (962, 0, 0, {})


def test_an_empty_window_classifies_as_nothing():
    v = _iwm_session()
    c = fai.classify_stored_rows(_true_rows(v).head(0), _refetch(v), 2026, 4)
    assert c == fai.StoredClassification({}, 0, 0, 0, {}, [])


# -- Design 3 in replace_month: label copies are not bars to return ----------


def test_label_copies_at_true_keys_do_not_make_a_refetch_short():
    """done_when[0]. On main these rows are incomplete_refetch with missing
    ['2026-04-10 (842/876)']: the 34 copies read as 34 more bars of the day."""
    v = _iwm_session()
    stored = _iwm_stored(v)

    r, swap = _replace(stored, v, "IWM", 2026, 4, commit=False)
    assert r["status"] == fai.REPLACE_DRY
    assert r["inserted"] == 842
    swap.assert_not_called()

    r2, swap = _replace(stored, v, "IWM", 2026, 4, commit=True)
    assert r2["status"] == fai.REPLACE_OK
    assert swap.call_count == 1
    frame = swap.call_args.args[0]
    assert sorted(frame["ts"]) == sorted(_true_rows(v)["ts"]) and len(frame) == 842
    assert "ts_et" not in frame.columns
    assert swap.call_args.kwargs["max_delete_ratio"] == fai.REPLACE_MAX_DELETE_RATIO == 3.0
    assert (r2["deleted"], r2["inserted"]) == (1082, 842)

    for out in (r, r2):
        assert (out["label_copies"], out["label_dropped"]) == (34, 206)
        assert (out["rows"], out["uncounted"]) == (1082, 240)
        assert out["by_utc_hour"] == {4: 57, 5: 43, 6: 46, 7: 60, 8: 3, 9: 17, 10: 14}
        assert (out["held_sessions"], out["missing_sessions"]) == (1, 0)


def test_label_region_rows_alone_never_made_a_refetch_short():
    """The 206 label rows of UTC 04:00-07:59 each lose their Eastern minute to
    the true row four hours later, before and after this change: dry_run."""
    v = _iwm_session()
    r, swap = _replace(_iwm_stored(v, copies=False), v, "IWM", 2026, 4, commit=False)
    assert r["status"] == fai.REPLACE_DRY
    assert (r["label_copies"], r["label_dropped"], r["rows"]) == (0, 206, 1048)
    swap.assert_not_called()


def _without_five_and_six(v: pd.DataFrame) -> pd.DataFrame:
    """The vendor month without its bars of 05:00 to 06:59 Eastern (89 of 842)."""
    hour = v["ts"].dt.hour
    short = v[(hour < 5) | (hour >= 7)]
    assert len(v) - len(short) == 43 + 46
    return short


@pytest.mark.parametrize("commit", [False, True])
def test_a_short_refetch_is_still_refused_on_a_clean_month(commit):
    """done_when[2]: a real bar the refetch lacks is not a label copy. Each of
    the 89 true rows is judged alone against the refetched bar four hours
    later, and none equals it."""
    v = _iwm_session()
    r, swap = _replace(_true_rows(v), _without_five_and_six(v), "IWM", 2026, 4, commit)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2026-04-10 (753/842)"]
    assert (r["label_copies"], r["label_dropped"]) == (0, 0)
    swap.assert_not_called()


@pytest.mark.parametrize("commit", [False, True])
def test_a_short_refetch_is_still_refused_beside_label_copies(commit):
    """The same refetch against the measured shape: the 34 copies are
    discounted and the 89 bars the refetch lacks still refuse the month."""
    v = _iwm_session()
    r, swap = _replace(_iwm_stored(v), _without_five_and_six(v), "IWM", 2026, 4, commit)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2026-04-10 (753/842)"]
    assert r["label_copies"] == 34
    swap.assert_not_called()


def test_a_month_held_only_under_the_eastern_label_keeps_todays_floor():
    """961 Eastern-labelled rows and no true-UTC row. Read as true instants
    only 721 of them fall inside 04:00-20:00 Eastern; the placed count, 961,
    is the floor, as today (Problem 3)."""
    v = _bars("2026-04-10", range(240, 1201))
    stored = _label_rows(v)
    assert len(stored) == 961

    r, swap = _replace(stored, v, "IWM", 2026, 4, commit=True)
    assert r["status"] == fai.REPLACE_OK
    assert (r["label_copies"], r["label_dropped"], r["uncounted"]) == (0, 0, 0)
    assert len(swap.call_args.args[0]) == 961

    for commit in (False, True):
        r, swap = _replace(stored, v[v["ts"].dt.hour >= 8], "IWM", 2026, 4, commit)
        assert r["status"] == fai.REPLACE_INCOMPLETE
        assert r["missing"] == ["2026-04-10 (721/961)"]
        swap.assert_not_called()


def test_a_window_holding_only_the_previous_months_late_bars_is_left_alone():
    """March's window holds February's three late bars and nothing of March.
    Nothing is held once the refetch is read, so nothing is handed to the swap
    and nothing is deleted (code review H2 on #1185)."""
    stored, march = _feb_late_and_march()
    r, swap = _replace(stored[stored["ts"].isin(FEB_LATE)], march, "SPY", 2018, 3, commit=True)
    assert r["status"] == fai.REPLACE_NOTHING_HELD
    assert (r["carry_in"], r["held_sessions"], r["rows"]) == (3, 0, 3)
    swap.assert_not_called()


# -- Design 4: the previous month's late bars are spared ---------------------


def test_previous_months_late_bars_are_spared_and_not_asked_of_this_month():
    """done_when[1]. On main: incomplete_refetch, missing ['2018-02-28 (0/2)'],
    because March's vendor month cannot return February's bars."""
    stored, march = _feb_late_and_march()

    r, swap = _replace(stored, march, "SPY", 2018, 3, commit=False)
    assert r["status"] == fai.REPLACE_DRY
    assert (r["carry_in"], r["missing_sessions"], r["held_sessions"]) == (3, 0, 1)
    swap.assert_not_called()

    r, swap = _replace(stored, march, "SPY", 2018, 3, commit=True)
    assert r["status"] == fai.REPLACE_OK
    assert (r["carry_in"], r["missing_sessions"]) == (3, 0)
    assert swap.call_count == 1
    frame = swap.call_args.args[0]
    assert list(swap.call_args.kwargs["spare_ts"]) == FEB_LATE
    assert not frame["ts"].isin(FEB_LATE).any()
    assert len(frame) == 961
    # The window's 964 rows less the three spared: what the swap deletes.
    assert (r["deleted"], r["inserted"]) == (961, 961)


def test_a_winter_label_row_the_refetch_lacks_is_spared_not_deleted():
    """Under EST the carry strip runs to 05:00Z, so the Eastern-label rows of
    the 1st's 04:00-04:59 bars lie in it. Copies of refetched bars count as
    today. One the refetch lacks cannot be told from a late bar of the previous
    month by this month's evidence, so it is spared: never counted, and never
    deleted."""
    v = _bars("2018-03-01", range(240, 1201), "SPY")
    stored = _label_rows(v)
    strip = [pd.Timestamp("2018-03-01 04:00", tz="UTC") + pd.Timedelta(minutes=n) for n in range(60)]

    r, swap = _replace(stored, v, "SPY", 2018, 3, commit=True)
    assert r["status"] == fai.REPLACE_OK
    assert (r["carry_in"], r["label_copies"], r["held_sessions"]) == (0, 0, 1)
    assert list(swap.call_args.kwargs["spare_ts"]) == []
    assert len(swap.call_args.args[0]) == 961

    r, swap = _replace(stored, v[v["ts"].dt.hour >= 5], "SPY", 2018, 3, commit=True)
    assert r["status"] == fai.REPLACE_OK
    assert r["carry_in"] == 60
    assert list(swap.call_args.kwargs["spare_ts"]) == strip
    frame = swap.call_args.args[0]
    assert len(frame) == 901 and not frame["ts"].isin(strip).any()
    assert r["deleted"] == 901          # the 60 are not among the rows deleted


# -- Design 2 and 5: a month writes its own late bars ------------------------

FEB_END = datetime(2018, 3, 1, 2, 0, tzinfo=UTC)             # February's window end
MARCH_MIDNIGHT = datetime(2018, 3, 1, 5, 0, tzinfo=UTC)      # 2018-03-01 00:00 Eastern (EST)
OTHER_STRIP_KEYS = [pd.Timestamp("2018-03-01 03:00", tz="UTC"), pd.Timestamp("2018-03-01 04:10", tz="UTC")]


def _february() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(stored, February's vendor month): the last session, 04:00-20:00, with
    its late bars of 21:04, 22:10 and 23:37 at their true keys past the window
    end; and two more rows in that strip which the vendor does not return."""
    feb = _bars("2018-02-28", list(range(240, 1201)) + [21 * 60 + 4, 22 * 60 + 10, 23 * 60 + 37], "SPY")
    others = _true_rows(_bars("2018-02-28", [22 * 60, 23 * 60 + 10], "SPY"))
    assert list(others["ts"]) == OTHER_STRIP_KEYS
    return pd.concat([_true_rows(feb), others]).reset_index(drop=True), feb


def test_split_tail_refuses_a_row_past_the_next_eastern_midnight():
    frame = _rows(pd.DatetimeIndex(["2018-03-01 01:59", "2018-03-01 02:00", "2018-03-01 04:59"], tz="UTC"))
    main, tail = fai.split_tail(frame, FEB_END, MARCH_MIDNIGHT)
    assert list(main["ts"]) == [pd.Timestamp("2018-03-01 01:59", tz="UTC")]
    assert list(tail["ts"]) == [pd.Timestamp("2018-03-01 02:00", tz="UTC"),
                                pd.Timestamp("2018-03-01 04:59", tz="UTC")]
    at_midnight = _rows(pd.DatetimeIndex(["2018-03-01 01:59", "2018-03-01 05:00"], tz="UTC"))
    with pytest.raises(ValueError, match="not a bar of"):
        fai.split_tail(at_midnight, FEB_END, MARCH_MIDNIGHT)


def test_a_months_own_late_bars_past_the_window_are_written():
    """done_when[1]. On main the dry run of February passes and the committed
    run raises ValueError: 3 row(s) fall outside the window."""
    stored, feb = _february()
    world = _World()
    r, swap = _replace(stored, feb, "SPY", 2018, 2, commit=True, world=world)
    assert r["status"] == fai.REPLACE_OK
    assert r["tail"] == 3
    assert (r["deleted"], r["inserted"]) == (961 + 3, 961 + 3)
    assert swap.call_count == 2

    first, second = swap.call_args_list
    assert first.args[4:6] == fai.month_replace_window(2018, 2)
    assert len(first.args[0]) == 961 and list(first.kwargs["spare_ts"]) == []
    frame, table, key, ts_col, start, end = second.args
    assert (table, key, ts_col) == ("market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts")
    assert start == FEB_END and end == datetime(2018, 3, 1, 4, 38, tzinfo=UTC)
    assert list(frame["ts"]) == FEB_LATE
    assert list(second.kwargs["spare_ts"]) == OTHER_STRIP_KEYS
    assert second.kwargs["clear_tables"] == fai.DERIVED_TS_TABLES
    assert second.kwargs["max_delete_ratio"] == fai.REPLACE_MAX_DELETE_RATIO
    assert callable(second.kwargs["verify"])

    # Both baselines are taken before the vendor is asked, the window's before
    # its rows are read; the strip's digest is taken again under the second
    # swap's lock.
    feb_window = fai.month_replace_window(2018, 2)
    assert world.events == [
        ("digest", *feb_window, False), ("rows", *feb_window),
        ("digest", FEB_END, MARCH_MIDNIGHT, False),
        ("fetch",),
        ("keys", FEB_END, end),
        ("swap", 1), ("digest", *feb_window, True),
        ("swap", 2), ("digest", FEB_END, MARCH_MIDNIGHT, True),
    ]
    held = world.rows["SPY"]
    assert [held[k][5] for k in FEB_LATE] == ["this run"] * 3
    assert [held[k][5] for k in OTHER_STRIP_KEYS] == ["2026-04-13"] * 2
    assert len(held) == 961 + 3 + 2


def test_a_dry_run_reports_the_tail_and_reads_nothing_more():
    stored, feb = _february()
    world = _World()
    r, swap = _replace(stored, feb, "SPY", 2018, 2, commit=False, world=world)
    assert r["status"] == fai.REPLACE_DRY
    assert (r["tail"], r["inserted"]) == (3, 964)
    swap.assert_not_called()
    assert world.events == [("rows", *fai.month_replace_window(2018, 2)), ("fetch",)]


def test_a_committed_month_without_late_bars_makes_one_swap_and_no_key_read():
    stored, feb = _february()
    world = _World()
    in_session = feb[feb["ts"].dt.hour * 60 + feb["ts"].dt.minute <= 1200]
    r, swap = _replace(stored, in_session, "SPY", 2018, 2, commit=True, world=world)
    assert r["status"] == fai.REPLACE_OK and r["tail"] == 0
    assert swap.call_count == 1
    assert [e[0] for e in world.events] == ["digest", "rows", "digest", "fetch", "swap", "digest"]
    # Late bars the vendor no longer returns stay as they are.
    assert [world.rows["SPY"][k][5] for k in FEB_LATE] == ["2026-04-13"] * 3


def test_a_refetched_row_past_the_next_eastern_midnight_is_never_written():
    """A row the vendor stamps in the next month is not of a held session and
    reaches neither swap, as today. Were a session of the next month held, the
    month would be refused before any swap: no bar of that session can lie
    inside this month's window, so the refetch holds none of it there. The
    ValueError of split_tail (the case above) stands behind both."""
    stored, feb = _february()
    with_next = pd.concat([feb, _bars("2018-03-01", [30], "SPY")])
    past = pd.Timestamp("2018-03-01 05:30", tz="UTC")           # 00:30 Eastern on March 1

    r, swap = _replace(stored, with_next, "SPY", 2018, 2, commit=True)
    assert r["status"] == fai.REPLACE_OK and r["tail"] == 3
    assert swap.call_count == 2
    assert all(past not in set(call.args[0]["ts"]) for call in swap.call_args_list)

    real = fai.classify_stored_rows

    def holding_march_too(*a, **k):
        c = real(*a, **k)
        return c._replace(held={**c.held, date(2018, 3, 1): 1})

    world = _World()
    with patch.object(fai, "classify_stored_rows", side_effect=holding_march_too):
        r, swap = _replace(stored, with_next, "SPY", 2018, 2, commit=True, world=world)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2018-03-01 (0/1)"]
    swap.assert_not_called()


def _run_world(tmp_path, monkeypatch, world: _World, items: list, commit: bool) -> int:
    lst = tmp_path / "l.csv"
    lst.write_text("".join(f"{sym},{y}-{m:02d}\n" for sym, y, m in items))
    monkeypatch.setattr(fai, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(fai, "_av_cfg", SimpleNamespace(delay_between_calls=0))
    with world.running():
        return fai.run_replace_months(str(lst), commit, None)


NEWER = (1.0, 2.0, 0.5, 1.5, 4242, "the nightly writer")


@pytest.mark.parametrize("when", ["while the vendor answers", "after the main swap"])
def test_a_tail_key_rewritten_during_the_run_is_not_overwritten(tmp_path, monkeypatch, caplog, when):
    """done_when[4]. Another writer upserts new values at a key the tail also
    holds: no key is added or removed, so only the strip's digest sees it. The
    second swap rolls back and the newer row stays."""
    import logging
    caplog.set_level(logging.INFO)
    stored, feb = _february()
    world = _World().store("SPY", stored).serve("SPY", 2018, 2, feb)
    keys_before = sorted(world.rows["SPY"])

    def rewrite(w):
        w.rows["SPY"][FEB_LATE[0]] = NEWER
    if when == "while the vendor answers":
        world.during_fetch = rewrite
    else:
        world.after_swap[1] = rewrite

    assert _run_world(tmp_path, monkeypatch, world, [("SPY", 2018, 2)], commit=True) == 1
    assert "SPY 2018-02 status=tail_not_written" in caplog.text
    assert "RETRY SPY,2018-02" in caplog.text
    held = world.rows["SPY"]
    assert held[FEB_LATE[0]] == NEWER                       # the newer values are kept
    assert sorted(held) == keys_before                      # no key added or removed
    assert [held[k][5] for k in FEB_LATE[1:]] == ["2026-04-13"] * 2   # the tail swap wrote nothing
    assert world.swap.call_count == 2
    start, end = fai.month_replace_window(2018, 2)
    assert {v[5] for k, v in held.items() if k < end} == {"this run"}   # the main swap committed

    # A second run, with nothing changing under it, converges.
    caplog.clear()
    world.during_fetch, world.after_swap = None, {}
    assert _run_world(tmp_path, monkeypatch, world, [("SPY", 2018, 2)], commit=True) == 0
    assert "SPY 2018-02 status=replaced" in caplog.text and "RETRY" not in caplog.text
    assert [world.rows["SPY"][k][5] for k in FEB_LATE] == ["this run"] * 3
    assert world.rows["SPY"][FEB_LATE[0]][:5] != NEWER[:5]


def test_with_the_strip_unchanged_the_month_is_replaced_and_its_tail_written(tmp_path, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO)
    stored, feb = _february()
    world = _World().store("SPY", stored).serve("SPY", 2018, 2, feb)
    assert _run_world(tmp_path, monkeypatch, world, [("SPY", 2018, 2)], commit=True) == 0
    assert "SPY 2018-02 status=replaced" in caplog.text and "RETRY" not in caplog.text
    tail = {r.ts: r for r in _true_rows(feb).itertuples(index=False) if r.ts in FEB_LATE}
    for k in FEB_LATE:
        assert world.rows["SPY"][k] == (*tail[k][1:], "this run")


def test_a_failed_tail_swap_reports_tail_not_written():
    """The main swap has committed, so the month cannot read as untouched or
    as replaced: the status says the late bars are as they were."""
    stored, feb = _february()
    world = _World()
    world.fail_swap[2] = RuntimeError("db down")
    r, swap = _replace(stored, feb, "SPY", 2018, 2, commit=True, world=world)
    assert r["status"] == fai.REPLACE_TAIL_NOT_WRITTEN == "tail_not_written"
    assert "db down" in r["detail"]
    assert (r["deleted"], r["inserted"], r["tail"]) == (961, 961, 3)
    assert [world.rows["SPY"][k][5] for k in FEB_LATE] == ["2026-04-13"] * 3


def test_the_key_read_is_strict_and_returns_utc_keys():
    """The spared keys of the tail swap come from this read. It goes through
    the strict query, so a database error is raised and never reads as "no
    keys stored" (which would spare nothing); a zone-less result is UTC."""
    reads = []

    def read(sql, params, **kw):
        reads.append((" ".join(sql.split()), params, kw))
        return pd.DataFrame({"ts": pd.to_datetime(["2018-03-01 02:04", "2018-03-01 03:00"])})

    with patch.object(fai, "query_to_dataframe_strict", side_effect=read):
        keys = fai._stored_keys("SPY", FEB_END, MARCH_MIDNIGHT)
    assert keys == [pd.Timestamp("2018-03-01 02:04", tz="UTC"), pd.Timestamp("2018-03-01 03:00", tz="UTC")]
    sql, params, kw = reads[0]
    assert len(reads) == 1 and sql.startswith("SELECT ts FROM market_data_intraday") and sql.endswith("ORDER BY ts")
    assert params == {"t": "SPY", "s": FEB_END, "e": MARCH_MIDNIGHT} and kw == {"timeout_s": 120}

    with patch.object(fai, "query_to_dataframe_strict", side_effect=RuntimeError("db down")), \
         pytest.raises(RuntimeError, match="db down"):
        fai._stored_keys("SPY", FEB_END, MARCH_MIDNIGHT)


def test_a_failed_strip_read_raises_before_any_swap():
    """Design 8: a database error on any read is raised. The key read comes
    before the main swap, so nothing has been written when it fails."""
    stored, feb = _february()
    world = _World()
    world.fail_keys = RuntimeError("db down")
    with pytest.raises(RuntimeError, match="db down"):
        _replace(stored, feb, "SPY", 2018, 2, commit=True, world=world)
    world.swap.assert_not_called()


# -- Design 6: the bound on what a month may leave uncounted ------------------


def _doubly_stored(labelled: int, extra_true: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(stored, vendor month): 74 + *extra_true* bars at their true keys, and
    the first *labelled* of the 04:00 bars again under the Eastern label. Each
    label row loses its Eastern minute to the true row four hours later."""
    minutes = list(range(240, 266)) + list(range(570, 600)) + list(range(961, 979 + extra_true))
    v = _bars("2026-04-10", minutes)
    labels = _label_rows(v[v["ts"].dt.hour == 4]).head(labelled)
    return pd.concat([_true_rows(v), labels]).reset_index(drop=True), v


def test_a_month_over_the_uncounted_bound_is_refused(tmp_path, monkeypatch, caplog):
    """done_when[6]: more than a quarter of the window's rows deleted and
    written back nowhere is not a month to replace unattended."""
    assert fai.REPLACE_MAX_UNCOUNTED_SHARE == 0.25

    stored, v = _doubly_stored(labelled=26)
    assert len(stored) == 100
    for commit in (False, True):
        r, swap = _replace(stored, v, "IWM", 2026, 4, commit)
        assert r["status"] == fai.REPLACE_UNCOUNTED_OVER == "uncounted_over_bound"
        assert (r["uncounted"], r["rows"], r["label_dropped"], r["missing_sessions"]) == (26, 100, 26, 0)
        swap.assert_not_called()
        caplog.clear()
        world = _World().store("IWM", stored).serve("IWM", 2026, 4, v)
        assert _run_world(tmp_path, monkeypatch, world, [("IWM", 2026, 4)], commit) == 1
        assert "RETRY IWM,2026-04" in caplog.text
        world.swap.assert_not_called()

    # Exactly a quarter is inside the bound.
    stored, v = _doubly_stored(labelled=25, extra_true=1)
    assert len(stored) == 100
    r, swap = _replace(stored, v, "IWM", 2026, 4, commit=False)
    assert (r["status"], r["uncounted"], r["rows"]) == (fai.REPLACE_DRY, 25, 100)
    r, swap = _replace(stored, v, "IWM", 2026, 4, commit=True)
    assert (r["status"], r["uncounted"], r["rows"]) == (fai.REPLACE_OK, 25, 100)
    assert len(swap.call_args.args[0]) == 75


# -- Design 6: what every run prints -----------------------------------------


def _four_months() -> tuple[_World, list]:
    """One of each: label rows and copies (IWM 2026-04), carry-ins (SPY
    2018-03), a tail (SPY 2018-02), and a month with none of them."""
    v = _iwm_session()
    late = _bars("2018-02-28", list(range(240, 1201)) + [21 * 60 + 4, 22 * 60 + 10, 23 * 60 + 37], "SPY")
    march = _bars("2018-03-01", range(240, 1201), "SPY")
    clean = _bars("2026-09-24", range(240, 1201), "SPY")
    world = _World().store("IWM", _iwm_stored(v)).serve("IWM", 2026, 4, v)
    for frame in (late, march, clean):
        world.store("SPY", _true_rows(frame))
    world.serve("SPY", 2018, 3, march).serve("SPY", 2018, 2, late).serve("SPY", 2026, 9, clean)
    return world, [("IWM", 2026, 4), ("SPY", 2018, 3), ("SPY", 2018, 2), ("SPY", 2026, 9)]


UNCOUNTED_LINES = [
    "UNCOUNTED IWM,2026-04 rows=1082 uncounted=240 share=22.18% label_dropped=206 label_copies=34 "
    "by_utc_hour=04:57,05:43,06:46,07:60,08:3,09:17,10:14 carry_in=0 tail=0",
    "UNCOUNTED SPY,2018-03 rows=964 uncounted=0 share=0.00% label_dropped=0 label_copies=0 "
    "by_utc_hour=- carry_in=3 tail=0",
    "UNCOUNTED SPY,2018-02 rows=961 uncounted=0 share=0.00% label_dropped=0 label_copies=0 "
    "by_utc_hour=- carry_in=0 tail=3",
    "UNCOUNTED SPY,2026-09 rows=961 uncounted=0 share=0.00% label_dropped=0 label_copies=0 "
    "by_utc_hour=- carry_in=0 tail=0",
]


@pytest.mark.parametrize("commit", [False, True])
def test_every_month_prints_an_uncounted_line(tmp_path, monkeypatch, caplog, commit):
    """done_when[5]. The numbers are the fixtures': 206 label rows by hour 57,
    43, 46, 60 and 34 copies by hour 3, 17, 14 of 1,082 rows (22.18%); three
    late bars carried into March; three written past February's window."""
    import logging
    caplog.set_level(logging.INFO)
    world, items = _four_months()
    assert _run_world(tmp_path, monkeypatch, world, items, commit) == 0
    messages = [rec.getMessage() for rec in caplog.records]
    assert [m for m in messages if m.startswith("UNCOUNTED")] == UNCOUNTED_LINES
    expected = fai.REPLACE_OK if commit else fai.REPLACE_DRY
    for line, (sym, y, m) in zip(UNCOUNTED_LINES, items):
        before = messages[messages.index(line) - 1]
        assert f"{sym} {y}-{m:02d} status={expected} " in before, before


def test_an_unclassified_month_prints_n_a_not_zeros(tmp_path, monkeypatch, caplog):
    """Label copies, carry-ins and the tail are decided from the refetch. With
    no refetch they are unknown, and a zero would read as "none"."""
    import logging
    caplog.set_level(logging.INFO)
    world = _World().store("SPY", _true_rows(_bars("2026-09-24", range(240, 1201), "SPY")))
    world.serve("SPY", 2026, 9, fai.FETCH_RATE_LIMIT)
    assert _run_world(tmp_path, monkeypatch, world, [("SPY", 2026, 9)], commit=True) == 1
    assert ("UNCOUNTED SPY,2026-09 rows=961 uncounted=n/a share=n/a label_dropped=n/a "
            "label_copies=n/a by_utc_hour=n/a carry_in=n/a tail=n/a") in caplog.text
    assert "RETRY SPY,2026-09" in caplog.text


def test_a_month_refused_as_short_still_prints_what_it_would_leave_uncounted(tmp_path, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO)
    v = _iwm_session()
    world = _World().store("IWM", _iwm_stored(v)).serve("IWM", 2026, 4, _without_five_and_six(v))
    assert _run_world(tmp_path, monkeypatch, world, [("IWM", 2026, 4)], commit=False) == 1
    assert "status=incomplete_refetch" in caplog.text
    assert ("UNCOUNTED IWM,2026-04 rows=1082 uncounted=240 share=22.18% label_dropped=206 "
            "label_copies=34 by_utc_hour=04:57,05:43,06:46,07:60,08:3,09:17,10:14 "
            "carry_in=0 tail=n/a") in caplog.text


def test_a_month_whose_tail_was_not_written_is_listed_as_replaced(tmp_path, monkeypatch, caplog):
    """Its window was deleted and re-inserted, so the results computed from
    the old bars are stale for it too; and it is not done, so it is a RETRY."""
    import logging
    caplog.set_level(logging.INFO)
    stored, feb = _february()
    world = _World().store("SPY", stored).serve("SPY", 2018, 2, feb)
    world.fail_swap[2] = RuntimeError("db down")
    assert _run_world(tmp_path, monkeypatch, world, [("SPY", 2018, 2)], commit=True) == 1
    assert "REPLACED SPY,2018-02" in caplog.text
    assert "RETRY SPY,2018-02" in caplog.text
    assert "tail not written (3 late bars past the window end): db down" in caplog.text


# -- a label copy that displaced a stored label row (plan, Review Focus 1) ---
#
# The spec's rule discounts a label copy read as a true instant at a key the
# refetch does not return. Where the vendor returned a bar when the labels were
# written and has not returned it since, that copy sits on the Eastern minute
# of the dropped bar's own label row, and the resolver keeps the copy. The
# label row is then the only stored copy of a real bar the refetch lacks. Its
# minute stays counted, as it is on main.


def test_a_copy_that_took_a_label_rows_minute_stays_counted():
    v = _iwm_session()
    now = v[v["ts"] != pd.Timestamp("2026-04-10 04:30")]      # the vendor no longer returns 04:30
    true = _true_rows(now)
    later = _label_rows(v, 8, 11)
    stored = pd.concat([true, _label_rows(v, 4, 8), later[~later["ts"].isin(true["ts"])]])
    assert len(stored) == 841 + 206 + 35
    displaced = pd.Timestamp("2026-04-10 04:30", tz="UTC")    # the 04:30 bar, under its label
    displacer = pd.Timestamp("2026-04-10 08:30", tz="UTC")    # the 08:30 bar's label row
    assert displaced in set(stored["ts"]) and displacer in set(stored["ts"])
    assert displacer not in set(true["ts"])

    c = fai.classify_stored_rows(stored, _refetch(now), 2026, 4)
    assert c.label_copies == 34            # not 35: the row at 08:30Z holds 04:30's minute
    assert c.held == {IWM_DAY: 842}        # 841 returned bars and the one only its label holds
    assert c.label_dropped == 206


@pytest.mark.parametrize("commit", [False, True])
def test_bars_held_only_as_displaced_labels_still_make_a_refetch_short(commit):
    """The labels were written when the vendor returned 04:00 to 04:29; the
    true-UTC rewrite and this refetch have no bar before 04:30. Thirty real
    bars are stored only under the label, each displaced by the label row of
    the bar four hours later. The month is refused, as on main (931/961)."""
    v = _bars("2026-04-10", range(240, 1201))
    now = v[v["ts"] >= pd.Timestamp("2026-04-10 04:30")]
    stored = pd.concat([_true_rows(now), _label_rows(v[v["ts"] < pd.Timestamp("2026-04-10 04:30")]),
                        _label_rows(v[(v["ts"] >= pd.Timestamp("2026-04-10 08:00"))
                                      & (v["ts"] < pd.Timestamp("2026-04-10 08:30"))])])
    assert len(stored) == 931 + 30 + 30 and not stored["ts"].duplicated().any()
    r, swap = _replace(stored, now, "IWM", 2026, 4, commit)
    assert r["status"] == fai.REPLACE_INCOMPLETE
    assert r["missing"] == ["2026-04-10 (931/961)"]
    assert (r["label_copies"], r["label_dropped"]) == (0, 30)
    swap.assert_not_called()


# -- FEAT-DATA-001, bar flags: a replace clears the flags by read span --------
#
# Spec: docs/superpowers/specs/2026-11-16-feat-data-001-bar-misprint-flags-r2.md
# (Design 7)

SPAN_TABLES = ("intraday_bar_flags", "intraday_bar_flag_coverage")


def test_the_two_derived_tuples():
    assert fai.DERIVED_TS_TABLES == (
        "intraday_flow_15m", "intraday_gex_15m", "realtime_gex_15m",
        "strat_features_1m", "strat_features_5m", "strat_features_15m",
        "strat_features_30m", "strat_features_60m", "strat_features_4h",
        "strat_features_levels_1m", "strat_features_levels_5m",
        "strat_features_levels_15m", "strat_features_levels_30m",
        "strat_features_levels_60m", "strat_features_levels_4h",
    )
    assert len(fai.DERIVED_TS_TABLES) == 15
    assert fai.DERIVED_SPAN_TABLES == SPAN_TABLES
    assert not set(fai.DERIVED_SPAN_TABLES) & set(fai.DERIVED_TS_TABLES)


def test_both_swaps_receive_the_span_tables():
    stored, feb = _february()
    r, swap = _replace(stored, feb, "SPY", 2018, 2, commit=True)
    assert r["status"] == fai.REPLACE_OK and swap.call_count == 2
    window, tail = swap.call_args_list
    assert window.kwargs["clear_span_tables"] == fai.DERIVED_SPAN_TABLES == SPAN_TABLES
    assert tail.kwargs["clear_span_tables"] == fai.DERIVED_SPAN_TABLES
    assert window.kwargs["clear_tables"] == fai.DERIVED_TS_TABLES
    assert tail.kwargs["clear_tables"] == fai.DERIVED_TS_TABLES


@pytest.mark.parametrize("name", ["bad name;", "x; DROP TABLE y", "Intraday_Bar_Flags", ""])
def test_a_bad_span_table_name_is_refused_before_the_transaction_opens(name):
    import gcp.database as db
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", side_effect=AssertionError("no DB call expected")), \
         pytest.raises(ValueError, match="bad derived table"):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  clear_span_tables=(name,))


def test_span_tables_need_their_clear_key_in_the_key():
    import gcp.database as db
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", side_effect=AssertionError("no DB call expected")), \
         pytest.raises(ValueError, match="clear_key must be a subset of key"):
        db.replace_rows_in_window(df, "market_data_intraday", {"interval": "1min"}, "ts",
                                  start, end, clear_span_tables=SPAN_TABLES)


def test_the_span_clear_runs_after_the_ts_clears_in_the_same_transaction():
    import gcp.database as db
    engine, conn, tbl = _engine_with(rowcount=1)
    seen = []

    def execute(stmt, *a, **k):
        q = " ".join(str(stmt).split())
        seen.append((q, a[0] if a else None))
        r = MagicMock()
        r.rowcount = {"DELETE FROM intraday_flow_15m": 7,
                      "DELETE FROM intraday_bar_flags": 41}.get(" ".join(q.split()[:3]), 1)
        r.scalar.return_value = (
            None if "'intraday_bar_flag_coverage'" in str(a) else "exists")
        r.scalar_one.return_value = 1
        return r
    conn.execute.side_effect = execute
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    cleared = {}
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=lambda c: None,
                                  clear_tables=("intraday_flow_15m",),
                                  clear_span_tables=SPAN_TABLES, cleared=cleared)
    texts = [q for q, _ in seen]
    span = [(q, p) for q, p in seen if q.startswith("DELETE FROM intraday_bar_flags")]
    # By read span, not by ts: every row whose [read_start, read_end) overlaps
    # the swapped window, for the key's clear_key columns.
    assert [q for q, _ in span] == [
        "DELETE FROM intraday_bar_flags WHERE ticker = :k_ticker "
        "AND read_start < :w_end AND read_end > :w_start"]
    assert span[0][1]["w_start"] == start and span[0][1]["w_end"] == end
    assert span[0][1]["k_ticker"] == "SPY"
    # A table that does not exist is skipped.
    assert not any(q.startswith("DELETE FROM intraday_bar_flag_coverage") for q in texts)
    assert cleared == {"intraday_flow_15m": 7, "intraday_bar_flags": 41}
    # After the source DELETE, the INSERT and the ts clears; one transaction.
    assert texts.index(span[0][0]) > texts.index(
        "DELETE FROM intraday_flow_15m WHERE ticker = :k_ticker "
        "AND ts >= :w_start AND ts < :w_end")
    assert texts.index(span[0][0]) > max(i for i, q in enumerate(texts) if q.startswith("INSERT"))
    assert engine.begin.call_count == 1


def test_without_span_tables_the_swap_issues_no_span_clear():
    import gcp.database as db
    engine, tbl, calls = _swap_engine(1)
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(df, "market_data_intraday",
                                  {"ticker": "SPY", "interval": "1min"}, "ts", start, end,
                                  verify=lambda c: None, clear_tables=("intraday_flow_15m",))
    assert not any("read_start" in q or "read_end" in q for q, _ in calls)


def _committed_run_clearing(tmp_path, caplog, span_counts: dict) -> int:
    """run_replace_months over SPY 2026-09, committed, the swap stubbed to
    report *span_counts* rows cleared from the span tables it was handed."""
    import logging

    def fake_replace(df, table, key, ts_col, start, end, **kw):
        kw["cleared"].update({"strat_features_1m": 390})
        kw["cleared"].update({t: span_counts[t] for t in kw["clear_span_tables"]})
        return 961, len(df)

    lst = tmp_path / "l.csv"
    lst.write_text("SPY,2026-09\n")
    caplog.set_level(logging.INFO)
    with patch.object(fai, "get_api_keys", return_value=["k"]), \
         patch.object(fai.time, "sleep"), \
         patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows",
                      return_value=_held_rows({date(2026, 9, 24): 1})), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        return fai.run_replace_months(str(lst), commit=True, limit=None)


def _rebuild_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("REBUILD ")]


def test_a_committed_replace_prints_rebuild_lines_for_the_span_tables(tmp_path, caplog):
    code = _committed_run_clearing(
        tmp_path, caplog, {"intraday_bar_flags": 41, "intraday_bar_flag_coverage": 3})
    assert code == 0
    assert _rebuild_lines(caplog) == [
        "REBUILD intraday_bar_flag_coverage rows_cleared=3",
        "REBUILD intraday_bar_flags rows_cleared=41",
        "REBUILD strat_features_1m rows_cleared=390",
    ]


def test_a_span_table_with_no_row_cleared_prints_no_rebuild_line(tmp_path, caplog):
    code = _committed_run_clearing(
        tmp_path, caplog, {"intraday_bar_flags": 0, "intraday_bar_flag_coverage": 3})
    assert code == 0
    assert _rebuild_lines(caplog) == [
        "REBUILD intraday_bar_flag_coverage rows_cleared=3",
        "REBUILD strat_features_1m rows_cleared=390",
    ]


# -- FEAT-DATA-001, bar flags: the replace takes the pass's locks (#1982) ------


def _keys_of(symbol: str, months: list) -> list[int]:
    from gcp.fetchers.intraday_bar_flags import flag_lock_key
    return [flag_lock_key(symbol, m) for m in months]


def test_the_swaps_receive_their_locks():
    from gcp.fetchers.intraday_bar_flags import flag_months_overlapping

    stored, feb = _february()
    r, swap = _replace(stored, feb, "SPY", 2018, 2, commit=True)
    assert r["status"] == fai.REPLACE_OK and swap.call_count == 2
    window, tail = swap.call_args_list
    # The window's swap of month M: M-1, M and M+1. The tail's: M and M+1.
    assert window.kwargs["advisory_locks"] == _keys_of(
        "SPY", [(2018, 1), (2018, 2), (2018, 3)])
    assert tail.kwargs["advisory_locks"] == _keys_of("SPY", [(2018, 2), (2018, 3)])
    start, end = fai.month_replace_window(2018, 2)
    assert window.kwargs["advisory_locks"] == _keys_of(
        "SPY", flag_months_overlapping(start, end))
    tail_start, tail_end = tail.args[4:6]
    assert tail_start == end
    assert tail.kwargs["advisory_locks"] == _keys_of(
        "SPY", flag_months_overlapping(end, tail_end))
    assert _keys_of("SPY", [(2018, 2)]) == [-4104793531149027913]


@pytest.mark.parametrize("symbol,year,month,months", [
    ("SPY", 2026, 1, [(2025, 12), (2026, 1), (2026, 2)]),
    ("QQQ", 2025, 12, [(2025, 11), (2025, 12), (2026, 1)]),
    # Every ticker, not only the three that have flags.
    ("AMD", 2026, 9, [(2026, 8), (2026, 9), (2026, 10)]),
])
def test_the_window_swap_locks_the_month_and_both_neighbours(symbol, year, month, months):
    captured = {}

    def fake_replace(df, table, key, ts_col, start, end, **kw):
        captured.update(kw, key=key)
        return 961, len(df)

    day = date(year, month, 15)
    vendor = _vendor_month([day.isoformat()]).assign(ticker=symbol)
    with patch.object(fai, "fetch_month", return_value=(vendor, fai.FETCH_OK)), \
         patch.object(fai, "_stored_window_rows", return_value=_held_rows({day: 1})), \
         patch.object(fai, "replace_rows_in_window", side_effect=fake_replace):
        r = fai.replace_month(symbol, year, month, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK
    assert captured["key"]["ticker"] == symbol
    assert captured["advisory_locks"] == _keys_of(symbol, months)
    assert all(type(k) is int and -2**63 <= k < 2**63 for k in captured["advisory_locks"])


def _lock_engine(isolation: str = "read committed", deleted: int = 1):
    """_swap_engine, whose lock statement answers *isolation*."""
    engine, conn, tbl = _engine_with(rowcount=deleted)
    calls = []

    def execute(stmt, *a, **k):
        q = " ".join(str(stmt).split())
        calls.append((q, a[0] if a else None))
        r = MagicMock()
        r.scalar_one.return_value = deleted
        r.scalar.return_value = "exists"
        r.one.return_value = (isolation, "", "", "")
        r.rowcount = deleted if q.startswith("DELETE FROM market_data_intraday") else 1
        return r
    conn.execute.side_effect = execute
    return engine, tbl, calls


LOCK_KEYS = [2323874143540971683, -2**63, 2**63 - 1, -7, 0]
LOCK_SELECT = ("SELECT current_setting('transaction_isolation'), pg_advisory_xact_lock(:k0), "
               "pg_advisory_xact_lock(:k1), pg_advisory_xact_lock(:k2), "
               "pg_advisory_xact_lock(:k3), pg_advisory_xact_lock(:k4)")


@pytest.mark.parametrize("with_verify", [True, False])
def test_lock_statement_precedes_the_row_lock(with_verify):
    import gcp.database as db
    engine, tbl, calls = _lock_engine()
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(
            df, "market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts",
            start, end, verify=(lambda c: calls.append(("VERIFY", None))) if with_verify else None,
            clear_tables=("intraday_flow_15m",),
            clear_span_tables=("intraday_bar_flags",), advisory_locks=LOCK_KEYS)
    texts = [q for q, _ in calls]
    assert texts[0] == "SET LOCAL lock_timeout = '30s'"
    assert texts[1] == LOCK_SELECT
    # One statement, each key once, ascending.
    assert calls[1][1] == {"k0": -2**63, "k1": -7, "k2": 0, "k3": 2323874143540971683,
                           "k4": 2**63 - 1}
    assert texts.count("SET LOCAL lock_timeout = '30s'") == 1
    assert sum("pg_advisory_xact_lock" in q for q in texts) == 1
    row_lock = ("SELECT count(*) FROM (SELECT 1 FROM market_data_intraday WHERE ticker = :k_ticker "
                "AND interval = :k_interval AND ts >= :w_start AND ts < :w_end FOR UPDATE) locked")
    delete = ("DELETE FROM market_data_intraday WHERE ticker = :k_ticker "
              "AND interval = :k_interval AND ts >= :w_start AND ts < :w_end")
    if with_verify:
        assert texts[2:5] == [row_lock, "VERIFY", delete]
    else:
        # Without verify the swap takes no row lock, as before.
        assert texts[2] == delete and not any("FOR UPDATE" in q for q in texts)
    first_delete = min(i for i, q in enumerate(texts) if q.startswith("DELETE"))
    assert first_delete > 1


def test_a_key_given_twice_is_locked_once():
    import gcp.database as db
    engine, tbl, calls = _lock_engine()
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(
            df, "market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts",
            start, end, advisory_locks=[5, 3, 5])
    assert calls[1] == (
        "SELECT current_setting('transaction_isolation'), pg_advisory_xact_lock(:k0), "
        "pg_advisory_xact_lock(:k1)", {"k0": 3, "k1": 5})


@pytest.mark.parametrize("with_verify", [True, False])
def test_with_no_advisory_locks_no_lock_statement_is_issued(with_verify):
    import gcp.database as db
    engine, tbl, calls = _lock_engine()
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}):
        db.replace_rows_in_window(
            df, "market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts",
            start, end, verify=(lambda c: None) if with_verify else None, advisory_locks=())
    texts = [q for q, _ in calls]
    assert not any("pg_advisory" in q or "transaction_isolation" in q for q in texts)
    # The lock timeout is set only for the row lock, as before.
    assert texts.count("SET LOCAL lock_timeout = '30s'") == (1 if with_verify else 0)


@pytest.mark.parametrize("with_verify", [True, False])
def test_other_isolation_raises_before_any_row_lock(with_verify):
    import gcp.database as db
    engine, tbl, calls = _lock_engine(isolation="repeatable read")
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    verified = []
    with patch.object(db, "get_engine", return_value=engine), \
         patch.dict(db._REFLECTED_TABLES, {"market_data_intraday": tbl}), \
         pytest.raises(RuntimeError, match="repeatable read"):
        db.replace_rows_in_window(
            df, "market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts",
            start, end, verify=verified.append if with_verify else None,
            clear_span_tables=("intraday_bar_flags",), advisory_locks=[1, 2, 3])
    texts = [q for q, _ in calls]
    assert len(texts) == 2 and texts[0] == "SET LOCAL lock_timeout = '30s'"
    assert "pg_advisory_xact_lock" in texts[1]
    assert verified == []
    assert not any("FOR UPDATE" in q or q.startswith(("DELETE", "INSERT")) for q in texts)


@pytest.mark.parametrize("key", ["1", 1.0, True, 2**63, -2**63 - 1, None])
def test_bad_keys_are_refused(key):
    import gcp.database as db
    start, end = fai.month_replace_window(2026, 9)
    df = _rows(pd.DatetimeIndex(["2026-09-24 13:30"], tz="UTC"))
    with patch.object(db, "get_engine", side_effect=AssertionError("no DB call expected")), \
         pytest.raises(ValueError, match="advisory_locks"):
        db.replace_rows_in_window(
            df, "market_data_intraday", {"ticker": "SPY", "interval": "1min"}, "ts",
            start, end, advisory_locks=[7, key])
