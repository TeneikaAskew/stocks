"""The bucket copy of the SPY, QQQ and IWM 1-min bars (FEAT-DATA-001, Design E).

The nightly fetch job writes one Parquet file per ticker-month and a manifest
that says how whole and on what basis each month is. Every test here runs
against an in-memory bucket (tests/fixtures/intraday_bars_bucket.py) and a
stubbed strict reader: nothing reaches the real bucket or a database.

Expected tables are written out from the bars a session IS (naive Eastern
minutes and their values), never through the code under test.
"""
from __future__ import annotations

import hashlib
import io
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gcp.fetchers import export_intraday_bars as xb
from gcp.fetchers import fetch_alphavantage_intraday as fai
from lib.eastern_time import (
    eastern_index_to_utc,
    intraday_month_window,
    place_stored_rows,
    sessions_between,
)
from tests.fixtures.intraday_bars_bucket import MemoryBucket
from tests.fixtures.intraday_checks import NEW, OLD, session_bars, stored

NOW = datetime(2026, 11, 13, 15, tzinfo=timezone.utc)

# B1 and B2, as the spec gives them. Written out here, not read from the module.
B1 = ("SELECT ts, open, high, low, close, volume, data_source, inserted_at "
      "FROM market_data_intraday WHERE ticker = :t AND interval = '1min' "
      "AND ts >= :start AND ts < :end ORDER BY ts")
B2 = ("SELECT date, high, low, data_source FROM market_data_daily "
      "WHERE ticker = :t AND date >= :first AND date <= :last")
BARS_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "data_source",
                "inserted_at"]
FILE_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "data_source"]
DAILY_COLUMNS = ["date", "high", "low", "data_source"]


def _last_day(year: int, month: int) -> date:
    first_of_next = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return first_of_next - timedelta(days=1)


def _sessions(year: int, month: int) -> list[date]:
    return sessions_between(date(year, month, 1), _last_day(year, month))


def _with_prices(frame: pd.DataFrame, kw: dict) -> pd.DataFrame:
    mid = (kw.get("day_high", 600.0) + kw.get("day_low", 590.0)) / 2
    return frame.assign(open=mid, close=mid, data_source="alphavantage")


def month_rows(year, month, how="true", shared="true", inserted=OLD, **kw) -> pd.DataFrame:
    """What B1 returns for a month whose every session is stored *how*: the
    eight columns, one row per stored key, ascending ``ts``."""
    parts = [stored(session_bars(d.isoformat(), **kw), how, shared=shared, inserted=inserted)
             for d in _sessions(year, month)]
    out = _with_prices(pd.concat(parts, ignore_index=True), kw)
    return out.sort_values("ts").reset_index(drop=True)[BARS_COLUMNS]


def expected_table(year, month, **kw) -> pd.DataFrame:
    """The month's bars, each on its own minute: built from the Eastern minute
    alone, never through place_stored_rows."""
    parts = []
    for d in _sessions(year, month):
        bars = session_bars(d.isoformat(), **kw)
        parts.append(_with_prices(bars.assign(ts=eastern_index_to_utc(bars["bar"])), kw))
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values("ts").reset_index(drop=True)[FILE_COLUMNS]


def read_file(data: bytes) -> pd.DataFrame:
    return pq.read_table(io.BytesIO(data)).to_pandas()


def assert_rows_equal(got: pd.DataFrame, want: pd.DataFrame) -> None:
    """Same columns in the same order, same instants, same values."""
    assert list(got.columns) == list(want.columns)
    assert len(got) == len(want)
    assert got["ts"].dt.tz is not None
    assert (pd.DatetimeIndex(got["ts"]).as_unit("ns").asi8
            == pd.DatetimeIndex(want["ts"]).as_unit("ns").asi8).all()
    for column in want.columns[1:]:
        pd.testing.assert_series_equal(
            got[column].reset_index(drop=True), want[column].reset_index(drop=True),
            check_dtype=False, check_exact=True, check_names=False)


def fake_query(monkeypatch, bars: dict, daily: dict | None = None) -> list[dict]:
    """Stand in for the strict reader; returns the list its calls land in.

    SQL that names market_data_daily answers ``daily[ticker]``; any other SQL
    answers ``bars[(ticker, year, month)]`` from the window's start. An
    exception in place of a frame is raised.
    """
    import gcp.database as database

    daily = daily or {}
    calls: list[dict] = []

    def strict(sql, params=None, timeout_s=None):
        calls.append({"sql": sql, "params": params, "timeout_s": timeout_s})
        if "market_data_daily" in sql:
            answer = daily[params["t"]]
        else:
            answer = bars[(params["t"], params["start"].year, params["start"].month)]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(database, "query_to_dataframe_strict", strict)
    return calls


def squash(sql: str) -> str:
    return " ".join(sql.split())


EMPTY_DAILY = pd.DataFrame(columns=DAILY_COLUMNS)


# -- Task 2: the month file -----------------------------------------------------


@pytest.mark.parametrize("how,shared", [("true", "true"), ("label", "true")])
def test_month_file_holds_each_bar_on_its_own_minute(how, shared):
    rows = month_rows(2025, 5, how, shared)
    data, entry = xb.build_month(rows, EMPTY_DAILY, "SPY", 2025, 5, NOW)

    schema = pq.read_schema(io.BytesIO(data))
    assert schema.names == FILE_COLUMNS
    assert schema.field("ts").type == pa.timestamp("us", tz="UTC")
    got = read_file(data)
    assert len(got) == 20181                      # 21 sessions of 961 bars
    assert got["ts"].is_monotonic_increasing
    assert_rows_equal(got, expected_table(2025, 5))
    assert entry["rows"] == entry["stored_rows"] == 20181
    assert entry["dropped_rows"] == 0
    assert entry["inferred_rows"] == 20181

    # The same keys inserted after every writer converted: no instant rests on
    # the resolver.
    _, proven = xb.build_month(month_rows(2025, 5, how, shared, inserted=NEW),
                               EMPTY_DAILY, "SPY", 2025, 5, NOW)
    assert proven["inferred_rows"] == 0
    assert proven["rows"] == 20181


def test_a_month_stored_both_ways_with_different_prices():
    true_copy = month_rows(2025, 5)
    label_copy = month_rows(2025, 5, "label", day_high=610.0, day_low=600.0)
    # The table's key allows one row per ts: where the two meet, the true copy
    # is the one stored.
    label_only = label_copy[~label_copy["ts"].isin(true_copy["ts"])]
    rows = (pd.concat([true_copy, label_only], ignore_index=True)
            .sort_values("ts").reset_index(drop=True))
    per_session = rows.groupby(rows["ts"].dt.date).size()
    assert len(label_only) == 21 * 240 and len(rows) == 25221

    data, entry = xb.build_month(rows, EMPTY_DAILY, "SPY", 2025, 5, NOW)
    got = read_file(data)
    assert_rows_equal(got, expected_table(2025, 5))
    assert got["high"].max() == 600.0
    assert entry["stored_rows"] == 25221
    assert entry["rows"] == 21 * 961
    assert entry["dropped_rows"] == 21 * 240
    assert entry["rows"] + entry["dropped_rows"] == entry["stored_rows"]
    assert per_session.sum() == 25221

    # One session alone: 961 kept and 240 dropped.
    one_true = _with_prices(stored(session_bars("2025-05-01")), {})
    one_label = _with_prices(
        stored(session_bars("2025-05-01", day_high=610.0, day_low=600.0), "label"),
        {"day_high": 610.0, "day_low": 600.0})
    one = pd.concat([one_true, one_label[~one_label["ts"].isin(one_true["ts"])]],
                    ignore_index=True).sort_values("ts").reset_index(drop=True)
    assert len(one) == 1201
    _, single = xb.build_month(one[BARS_COLUMNS], EMPTY_DAILY, "SPY", 2025, 5, NOW)
    assert (single["rows"], single["dropped_rows"]) == (961, 240)


def test_a_flat_session_stored_both_ways_is_written_as_placed():
    # The named limit of Design F: nothing but inferred_rows flags this month.
    rows = _with_prices(
        stored(session_bars("2025-05-01", spike=False), "both", shared="label"), {})
    rows = rows[BARS_COLUMNS]
    instants, keep, proven = place_stored_rows(
        rows["ts"], rows["volume"], rows["inserted_at"])
    want = rows.loc[keep, FILE_COLUMNS[1:]].reset_index(drop=True)
    want.insert(0, "ts", instants[keep])
    want = want.sort_values("ts").reset_index(drop=True)

    data, entry = xb.build_month(rows, EMPTY_DAILY, "SPY", 2025, 5, NOW)
    assert_rows_equal(read_file(data), want)
    assert entry["rows"] == 961
    assert entry["inferred_rows"] == 961
    assert not proven.any()


def test_the_last_bar_of_a_month_is_in_that_months_file(monkeypatch):
    june, july = month_rows(2025, 6), month_rows(2025, 7)
    last_bar = pd.Timestamp("2025-07-01 00:00", tz="UTC")   # 20:00 ET on 2025-06-30
    assert june["ts"].iloc[-1] == last_bar                  # handed to the June window
    assert not (july["ts"] == last_bar).any()
    calls = fake_query(monkeypatch, {("SPY", 2025, 6): june, ("SPY", 2025, 7): july})
    bucket = MemoryBucket()

    xb.export_month(bucket, "SPY", 2025, 6, EMPTY_DAILY, NOW)
    xb.export_month(bucket, "SPY", 2025, 7, EMPTY_DAILY, NOW)

    june_file = read_file(bucket.objects["intraday-bars/v1/1min/SPY/2025-06.parquet"])
    july_file = read_file(bucket.objects["intraday-bars/v1/1min/SPY/2025-07.parquet"])
    assert june_file["ts"].iloc[-1] == last_bar
    assert july_file["ts"].iloc[0] == pd.Timestamp("2025-07-01 08:00", tz="UTC")
    assert not (july_file["ts"] == last_bar).any()
    assert [(c["params"]["start"], c["params"]["end"]) for c in calls] == [
        intraday_month_window(2025, 6), intraday_month_window(2025, 7)]


def test_export_month_reads_one_strict_query_and_overwrites(monkeypatch):
    rows = month_rows(2025, 5)
    calls = fake_query(monkeypatch, {("SPY", 2025, 5): rows})
    bucket = MemoryBucket()
    name = "intraday-bars/v1/1min/SPY/2025-05.parquet"

    entry = xb.export_month(bucket, "SPY", 2025, 5, EMPTY_DAILY, NOW)

    assert len(calls) == 1
    assert squash(calls[0]["sql"]) == B1
    assert "interval = '1min'" in calls[0]["sql"]
    assert calls[0]["params"] == {
        "t": "SPY",
        "start": datetime(2025, 5, 1, 2, tzinfo=timezone.utc),
        "end": datetime(2025, 6, 1, 2, tzinfo=timezone.utc)}
    assert calls[0]["timeout_s"] == 120
    assert bucket.writes == [name]
    assert bucket.preconditions == [(name, None)]
    assert entry["sha256"] == hashlib.sha256(bucket.objects[name]).hexdigest()
    first = bucket.objects[name]

    changed = rows.copy()
    changed.loc[100, "close"] = 123.45
    fake_query(monkeypatch, {("SPY", 2025, 5): changed})
    xb.export_month(bucket, "SPY", 2025, 5, EMPTY_DAILY, NOW)

    assert bucket.writes == [name, name]
    assert bucket.objects[name] != first
    assert read_file(bucket.objects[name])["close"].iloc[100] == 123.45


def test_null_price_and_volume_stay_null():
    rows = _with_prices(stored(session_bars("2025-05-01")), {})[BARS_COLUMNS]
    rows["volume"] = rows["volume"].astype("Int64")
    rows.loc[5, "open"] = np.nan
    rows.loc[7, "volume"] = pd.NA

    data, _ = xb.build_month(rows, EMPTY_DAILY, "SPY", 2025, 5, NOW)
    table = pq.read_table(io.BytesIO(data))
    assert table.column("open").null_count == 1
    assert table.column("volume").null_count == 1
    assert table.schema.field("volume").type == pa.int64()
    assert table.column("high").null_count == 0
    for name in ("open", "high", "low", "close"):
        assert table.schema.field(name).type == pa.float64()
    assert table.schema.field("data_source").type == pa.string()
    # The null sits on the row it was stored on, and nothing was filled in.
    got = read_file(data)
    assert pd.isna(got["open"].iloc[5]) and pd.isna(got["volume"].iloc[7])
    assert got["volume"].iloc[6] == 1000


def test_object_names():
    assert xb.object_name("SPY", 2025, 5) == "intraday-bars/v1/1min/SPY/2025-05.parquet"
    assert xb.manifest_name("SPY") == "intraday-bars/v1/1min/SPY/manifest.json"
    assert xb.PREFIX == "intraday-bars/v1/1min"
    assert xb.COLUMNS == tuple(FILE_COLUMNS)
    assert xb.EXPORT_TICKERS == fai.BASIS_TICKERS
    assert squash(xb.BARS_SQL) == B1
    assert squash(xb.DAILY_SQL) == B2
    assert squash(xb.DAILY_SQL) == squash(fai._BASIS_DAILY_SQL)


class _FakeBlob:
    def __init__(self, store: dict, name: str):
        self._store, self.name, self.generation = store, name, None

    def download_as_bytes(self):
        failure = self._store.get("download_raises")
        if failure is not None:
            raise failure
        self.generation = "1731500000000001"      # the client reports a string
        return b"payload"

    def upload_from_string(self, data, **kwargs):
        self._store.setdefault("uploads", []).append((self.name, data, kwargs))
        failure = self._store.get("upload_raises")
        if failure is not None:
            raise failure
        self.generation = 1731500000000002


class _FakeClient:
    store: dict = {}

    def bucket(self, name):
        self.store["bucket"] = name
        store = self.store

        class _Bucket:
            def blob(self, blob_name):
                return _FakeBlob(store, blob_name)

        return _Bucket()


@pytest.fixture
def gcs(monkeypatch):
    import google.cloud.storage as storage

    _FakeClient.store = {}
    monkeypatch.setattr(storage, "Client", _FakeClient)
    return _FakeClient.store


@pytest.mark.parametrize("value", ["gs://b", "b"])
def test_bucket_from_env(monkeypatch, gcs, value):
    monkeypatch.setenv("GCS_BUCKET", value)
    bucket = xb.bucket_from_env()
    assert isinstance(bucket, xb.GcsBucket)
    assert bucket.name == "b"
    assert gcs["bucket"] == "b"


@pytest.mark.parametrize("value", [None, "", "gs://"])
def test_bucket_from_env_refuses_an_unset_bucket(monkeypatch, gcs, value):
    if value is None:
        monkeypatch.delenv("GCS_BUCKET", raising=False)
    else:
        monkeypatch.setenv("GCS_BUCKET", value)
    with pytest.raises(RuntimeError, match="GCS_BUCKET"):
        xb.bucket_from_env()
    assert "bucket" not in gcs                    # no bucket was guessed


def test_gcs_bucket_absent_is_an_answer_and_any_other_failure_raises(gcs):
    from google.api_core.exceptions import Forbidden, NotFound, PreconditionFailed

    bucket = xb.GcsBucket("b")
    assert bucket.read("x/manifest.json") == (b"payload", 1731500000000001)

    gcs["download_raises"] = NotFound("no such object")
    assert bucket.read("x/manifest.json") is None

    gcs["download_raises"] = Forbidden("denied")
    with pytest.raises(Forbidden):
        bucket.read("x/manifest.json")

    assert bucket.write("x/manifest.json", b"{}", if_generation_match=0) == 1731500000000002
    name, data, kwargs = gcs["uploads"][-1]
    assert (name, data) == ("x/manifest.json", b"{}")
    assert kwargs["if_generation_match"] == 0

    assert bucket.write("x/2025-05.parquet", b"PAR1") == 1731500000000002
    assert gcs["uploads"][-1][2]["if_generation_match"] is None

    gcs["upload_raises"] = PreconditionFailed("generation mismatch")
    with pytest.raises(xb.GenerationMismatch):
        bucket.write("x/manifest.json", b"{}", if_generation_match=7)

    # Any other failed upload is itself, never a mismatch.
    gcs["upload_raises"] = Forbidden("denied")
    with pytest.raises(Forbidden):
        bucket.write("x/manifest.json", b"{}", if_generation_match=7)
