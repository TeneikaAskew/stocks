"""--replace-months: the re-framing migration for market_data_intraday.

The migration deletes a whole month and inserts its refetch in one
transaction. Two properties make that safe, and both are checked here rather
than reasoned about:

  1. The delete window for month M holds every row M can have in EITHER
     convention (true UTC, and Eastern wall time stamped as UTC), and no row of
     M-1 or M+1 in either convention. Checked exhaustively, every minute AV can
     return (04:00-19:59 ET), every day, every month 2016-2027, across DST.
  2. Nothing is deleted unless the refetch succeeded and covers the sessions
     already held; dry run never writes.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
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

    AV extended hours are 04:00-19:59 ET. True UTC stores the real instant;
    the legacy writers stored the Eastern wall clock labelled UTC.
    """
    first, last = min(_month_days(y, m)), max(_month_days(y, m))
    lo_wall, hi_wall = time(4, 0), time(19, 59)
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
    assert r["missing"] == ["2026-09-02"]
    rep.assert_not_called()


def test_only_held_sessions_are_reinserted():
    """Footprint-preserving: a month holding one day gets that day back, not
    the vendor's whole month."""
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01", "2026-09-02", "2026-09-24"]),
                                    fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 24): 12}), \
         patch.object(fai, "replace_rows_in_window", return_value=(12, 1)) as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=True)
    assert r["status"] == fai.REPLACE_OK
    df = rep.call_args.args[0]
    assert list(df["ts"]) == [pd.Timestamp("2026-09-24 13:30", tz="UTC")]


def test_dry_run_never_writes():
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates", return_value={date(2026, 9, 1): 5}), \
         patch.object(fai, "replace_rows_in_window") as rep:
        r = fai.replace_month("SPY", 2026, 9, "k", commit=False)
    assert r["status"] == fai.REPLACE_DRY
    rep.assert_not_called()


def test_commit_swaps_utc_rows_over_the_month_window():
    with patch.object(fai, "fetch_month",
                      return_value=(_vendor_month(["2026-09-01", "2026-09-24"]), fai.FETCH_OK)), \
         patch.object(fai, "_held_session_dates",
                      return_value={date(2026, 9, 1): 5, date(2026, 9, 24): 5}), \
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
