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
    assert "NO PATH YET" in adv["signal_alerts exits"]
    assert "#1190" in adv["signal_alerts exits"]
    premarket = next(v for k, v in adv.items() if k.startswith("market_data_daily"))
    assert "NO PATH YET" in premarket and "backfill_daily_indicators" not in premarket
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


def _replace(stored: pd.DataFrame, vendor: pd.DataFrame, sym: str, y: int, m: int,
             commit: bool, swap=None):
    """replace_month over written-out rows. *stored* is the table (any range);
    the snapshot and the re-read under the lock see its rows of the month's
    window. Returns (result, the swap mock). The default swap runs verify()
    as the real one does and reports every unspared window row deleted."""
    start, end = fai.month_replace_window(y, m)
    stored = stored.sort_values("ts").reset_index(drop=True)
    window = stored[(stored["ts"] >= start) & (stored["ts"] < end)].reset_index(drop=True)

    def default_swap(df, table, key, ts_col, w_start, w_end, **kw):
        if kw.get("verify"):
            kw["verify"](object())
        held_back = set(kw.get("spare_ts") or ())
        in_range = stored[(stored["ts"] >= w_start) & (stored["ts"] < w_end)]
        return int((~in_range["ts"].isin(held_back)).sum()), len(df)

    with patch.object(fai, "_stored_window_rows", return_value=window.copy()), \
         patch.object(fai, "_held_session_dates",
                      side_effect=lambda *a, **k: fai._placed_session_counts(window)), \
         patch.object(fai, "fetch_month", return_value=(vendor.copy(), fai.FETCH_OK)), \
         patch.object(fai, "replace_rows_in_window", side_effect=swap or default_swap) as rep:
        return fai.replace_month(sym, y, m, "k", commit=commit), rep


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
