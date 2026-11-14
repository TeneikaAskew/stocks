"""The bucket copy of the SPY, QQQ and IWM 1-min bars (FEAT-DATA-001, Design E).

The nightly fetch job writes one Parquet file per ticker-month and a manifest
that says how whole and on what basis each month is. Every test here runs
against an in-memory bucket (tests/fixtures/intraday_bars_bucket.py) and a
stubbed strict reader: nothing reaches the real bucket or a database.

Expected tables are written out from the bars a session IS (naive Eastern
minutes and their values), never through the code under test.
"""
from __future__ import annotations

import ast
import gc
import hashlib
import io
import json
import logging
import subprocess
import sys
import textwrap
import weakref
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from gcp.fetchers import export_intraday_bars as xb
from gcp.fetchers import fetch_alphavantage_intraday as fai
from lib.eastern_time import (
    ET,
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


def month_rows(year, month, how="true", shared="true", inserted=OLD, days=None,
               **kw) -> pd.DataFrame:
    """What B1 returns for a month whose every session is stored *how*: the
    eight columns, one row per stored key, ascending ``ts``. *days* maps an
    ISO session date to session_bars arguments for that session alone."""
    days = days or {}
    parts = [stored(session_bars(d.isoformat(), **{**kw, **days.get(d.isoformat(), {})}),
                    how, shared=shared, inserted=inserted)
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

    SQL that names market_data_daily answers ``daily[ticker]`` (no daily row
    at all for a ticker that is not in it); any other SQL
    answers ``bars[(ticker, year, month)]`` from the window's start. An
    exception in place of a frame is raised.
    """
    import gcp.database as database

    daily = daily or {}
    calls: list[dict] = []

    def strict(sql, params=None, timeout_s=None):
        calls.append({"sql": sql, "params": params, "timeout_s": timeout_s})
        if "market_data_daily" in sql:
            answer = daily.get(params["t"], EMPTY_DAILY)
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


# -- Task 3: the manifest entry -------------------------------------------------

ENTRY_KEYS = {"file", "rows", "stored_rows", "dropped_rows", "inferred_rows",
              "first_ts", "last_ts", "sha256", "exported_at", "sessions", "basis"}


def daily_rows(year, month, src="alphavantage_daily", skip=(), stamp=None) -> pd.DataFrame:
    """One market_data_daily row of 600.0 and 590.0 per session of the month.
    *skip* leaves dates out; *stamp* maps a date to another ``data_source``."""
    stamp = stamp or {}
    rows = [{"date": d, "high": 600.0, "low": 590.0,
             "data_source": stamp.get(d.isoformat(), src)}
            for d in _sessions(year, month) if d.isoformat() not in skip]
    return pd.DataFrame(rows, columns=DAILY_COLUMNS).astype(
        {"date": object, "data_source": object})


def entry(rows, daily, y=2025, m=5, now=NOW) -> dict:
    return xb.build_month(rows, daily, "SPY", y, m, now)[1]


def test_entry_keys_and_counts():
    rows = month_rows(2025, 5, inserted=NEW)
    data, got = xb.build_month(rows, daily_rows(2025, 5), "SPY", 2025, 5, NOW)

    assert set(got) == ENTRY_KEYS and len(got) == 11
    assert got["rows"] + got["dropped_rows"] == got["stored_rows"] == 20181
    assert got["file"] == "intraday-bars/v1/1min/SPY/2025-05.parquet"
    assert got["sha256"] == hashlib.sha256(data).hexdigest()
    assert got["first_ts"] == "2025-05-01T08:00:00+00:00"
    assert got["last_ts"] == "2025-05-31T00:00:00+00:00"
    assert got["exported_at"] == NOW.isoformat() == "2026-11-13T15:00:00+00:00"
    assert got["sessions"] == {
        "expected": 21, "ok": 21, "thin": 0, "missing": 0, "undetermined": 0}
    assert got["basis"] == {
        "state": "as_traded", "factor_min": 1.0, "factor_max": 1.0, "as_traded": 21,
        "inferred": 0, "adjusted": 0, "odd": 0, "not_measured": {}}
    # The entry is what the manifest stores: it must survive JSON unchanged.
    assert json.loads(json.dumps(got)) == got


def test_one_unproven_row_makes_the_month_inferred():
    rows = month_rows(2025, 5, inserted=NEW)
    one = rows["ts"] == pd.Timestamp("2025-05-16 14:00", tz="UTC")     # 10:00 ET
    assert one.sum() == 1
    rows.loc[one, "inserted_at"] = OLD

    got = entry(rows, daily_rows(2025, 5))
    assert got["basis"]["state"] == "inferred"
    assert got["basis"]["as_traded"] == 20
    assert got["basis"]["inferred"] == 1
    assert got["inferred_rows"] == 1
    assert got["basis"]["not_measured"] == {}


def test_not_measured_reasons_and_partial():
    rows = month_rows(2025, 5, inserted=NEW, days={
        "2025-05-12": {"start": "09:30", "end": "13:29"},
        "2025-05-13": {"f_low": 0.99}})
    daily = daily_rows(2025, 5, skip=("2025-05-14",), stamp={
        "2025-05-15": "alphavantage_1min", "2025-05-19": "yahoo"})

    got = entry(rows, daily)
    assert got["basis"]["not_measured"] == {
        "2025-05-12": "incomplete", "2025-05-13": "odd", "2025-05-14": "no_daily_row",
        "2025-05-15": "daily_from_intraday", "2025-05-19": "daily_source_unknown"}
    assert got["basis"]["state"] == "partial"
    assert got["basis"]["as_traded"] == 16
    assert got["basis"]["odd"] == 1
    assert got["basis"]["inferred"] == 0 and got["basis"]["adjusted"] == 0
    assert (got["basis"]["factor_min"], got["basis"]["factor_max"]) == (1.0, 1.0)
    assert got["sessions"] == {
        "expected": 21, "ok": 20, "thin": 1, "missing": 0, "undetermined": 0}


def _one_reason(reason: str):
    """A whole proven as-traded May 2025 with one session that is not measured
    for *reason*: (rows, daily, the session)."""
    day = "2025-05-14"
    days, skip, stamp = {}, (), {}
    if reason == "incomplete":
        days = {day: {"start": "09:30", "end": "13:29"}}
    elif reason == "odd":
        days = {day: {"f_low": 0.99}}
    elif reason == "no_daily_row":
        skip = (day,)
    elif reason == "daily_from_intraday":
        stamp = {day: "alphavantage_1min"}
    elif reason == "daily_source_unknown":
        stamp = {day: "yahoo"}
    rows = month_rows(2025, 5, inserted=NEW, days=days)
    daily = daily_rows(2025, 5, skip=skip, stamp=stamp)
    if reason == "daily_not_positive":
        daily.loc[daily["date"] == date(2025, 5, 14), "low"] = 0.0
    elif reason == "no_rth_high_low":
        on_day = ((rows["ts"] >= pd.Timestamp("2025-05-14 04:00", tz="UTC"))
                  & (rows["ts"] < pd.Timestamp("2025-05-15 04:00", tz="UTC")))
        rows.loc[on_day, "high"] = np.nan
    return rows, daily, day


@pytest.mark.parametrize("reason", [
    "incomplete", "odd", "no_daily_row", "daily_from_intraday",
    "daily_source_unknown", "daily_not_positive", "no_rth_high_low"])
def test_a_month_with_a_session_not_measured_is_never_as_traded(reason):
    rows, daily, day = _one_reason(reason)
    got = entry(rows, daily)
    assert got["basis"]["not_measured"] == {day: reason}
    assert got["basis"]["state"] == "partial"
    assert got["basis"]["state"] != "as_traded"
    assert got["basis"]["as_traded"] == 20
    assert got["basis"]["odd"] == (1 if reason == "odd" else 0)


def test_adjusted_wins_and_carries_the_range():
    rows = month_rows(2025, 5, inserted=NEW, days={
        "2025-05-07": {"f_high": 0.99430, "f_low": 0.99430}})
    one = rows["ts"] == pd.Timestamp("2025-05-16 14:00", tz="UTC")
    rows.loc[one, "inserted_at"] = OLD

    got = entry(rows, daily_rows(2025, 5))
    assert got["basis"]["state"] == "adjusted"
    assert got["basis"]["adjusted"] == 1
    assert got["basis"]["inferred"] == 1
    assert got["basis"]["as_traded"] == 19
    assert got["basis"]["factor_min"] == 0.9943
    assert got["basis"]["factor_max"] == 1.0


def test_an_odd_session_is_outside_the_factor_range():
    # An ODD session's mean factor is 0.995; it is under not_measured and the
    # range is of the counted sessions only.
    rows = month_rows(2025, 5, inserted=NEW, days={"2025-05-13": {"f_low": 0.99}})
    got = entry(rows, daily_rows(2025, 5))
    assert (got["basis"]["factor_min"], got["basis"]["factor_max"]) == (1.0, 1.0)


def test_unmeasured_has_null_factors():
    got = entry(month_rows(2025, 5, inserted=NEW),
                daily_rows(2025, 5, src="alphavantage_1min"))
    assert got["basis"]["state"] == "unmeasured"
    assert got["basis"]["factor_min"] is None
    assert got["basis"]["factor_max"] is None
    assert len(got["basis"]["not_measured"]) == 21
    assert set(got["basis"]["not_measured"].values()) == {"daily_from_intraday"}
    assert got["basis"]["as_traded"] == 0


def test_a_month_with_no_row():
    data, got = xb.build_month(pd.DataFrame(columns=BARS_COLUMNS), daily_rows(2025, 5),
                               "SPY", 2025, 5, NOW)
    assert data is None
    assert got["rows"] == got["stored_rows"] == got["dropped_rows"] == 0
    assert got["inferred_rows"] == 0
    assert got["file"] is None and got["sha256"] is None
    assert got["first_ts"] is None and got["last_ts"] is None
    assert got["exported_at"] == NOW.isoformat()
    assert got["sessions"] == {
        "expected": 21, "ok": 0, "thin": 0, "missing": 21, "undetermined": 0}
    assert got["basis"]["state"] == "unmeasured"
    assert set(got) == ENTRY_KEYS


def test_the_newest_session_has_no_daily_row_yet():
    # 21:00 ET on 2026-11-12: the nightly export runs two hours before the
    # daily fetch, so that evening's session has no daily row yet.
    now = datetime(2026, 11, 13, 2, tzinfo=timezone.utc)
    rows = month_rows(2026, 11, inserted=NEW)
    rows = rows[rows["ts"] <= pd.Timestamp("2026-11-13 01:00", tz="UTC")]   # 20:00 ET
    daily = daily_rows(2026, 11)
    daily = daily[daily["date"] <= date(2026, 11, 11)]

    got = entry(rows, daily, 2026, 11, now)
    assert got["sessions"]["expected"] == 9
    assert got["sessions"]["ok"] == 9
    assert got["basis"]["not_measured"] == {"2026-11-12": "no_daily_row"}
    assert got["basis"]["state"] == "partial"
    assert got["basis"]["as_traded"] == 8
    assert got["inferred_rows"] == 0


# -- Task 4: the manifest protocol and export_window ---------------------------

SPY_MANIFEST = "intraday-bars/v1/1min/SPY/manifest.json"
MAY = "intraday-bars/v1/1min/SPY/2025-05.parquet"
JUNE = "intraday-bars/v1/1min/SPY/2025-06.parquet"


def first_session_rows(year, month, inserted=NEW, **kw) -> pd.DataFrame:
    """A small month: its first session only, stored as true UTC."""
    day = _sessions(year, month)[0].isoformat()
    return _with_prices(stored(session_bars(day, **kw), inserted=inserted), kw)[BARS_COLUMNS]


def small_bars(tickers, months, **kw) -> dict:
    return {(t, y, m): first_session_rows(y, m, **kw) for t in tickers for y, m in months}


def run(monkeypatch, tickers, months, bars, bucket, daily=None, now=NOW):
    """export_window against the stubbed reader: (its result, the reader's calls)."""
    calls = fake_query(monkeypatch, bars, daily)
    result = xb.export_window(tickers, months, bucket=bucket, now_utc=now)
    return result, calls


def manifest_doc(bucket, name=SPY_MANIFEST) -> dict:
    return json.loads(bucket.objects[name])


def manifest_with(*months: str) -> bytes:
    """A manifest another run wrote: an entry (no file) for each month key."""
    return json.dumps({"version": 1, "ticker": "SPY", "months": {
        key: {"file": None, "rows": 0, "written_by": "another run"} for key in months}}).encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_first_export_creates_the_manifest(monkeypatch):
    bucket = MemoryBucket()
    rows = first_session_rows(2025, 5)
    run(monkeypatch, ["SPY"], [(2025, 5)], {("SPY", 2025, 5): rows}, bucket)

    assert bucket.preconditions == [(MAY, None), (SPY_MANIFEST, 0)]
    _, want = xb.build_month(rows, EMPTY_DAILY, "SPY", 2025, 5, NOW)
    assert manifest_doc(bucket) == {"version": 1, "ticker": "SPY", "months": {"2025-05": want}}
    assert bucket.generations[SPY_MANIFEST] == 1
    assert want["sha256"] == sha(bucket.objects[MAY])


def test_a_manifest_another_run_created_in_between_is_kept(monkeypatch):
    bucket = MemoryBucket()
    seen = []

    def another_run_creates_it(name):
        if name == SPY_MANIFEST and not seen:
            seen.append(name)
            bucket.put(SPY_MANIFEST, manifest_with("2024-01"))

    bucket.before_write = another_run_creates_it
    run(monkeypatch, ["SPY"], [(2025, 5)], small_bars(["SPY"], [(2025, 5)]), bucket)

    doc = manifest_doc(bucket)
    assert set(doc["months"]) == {"2024-01", "2025-05"}
    assert doc["months"]["2024-01"]["written_by"] == "another run"
    assert bucket.writes.count(SPY_MANIFEST) == 2
    # The first attempt said "only if absent"; the retry named what it read.
    assert [g for n, g in bucket.preconditions if n == SPY_MANIFEST] == [0, 1]


def test_an_entry_another_run_wrote_in_between_is_kept(monkeypatch):
    bucket = MemoryBucket()
    bucket.put(SPY_MANIFEST, manifest_with("2025-04"))
    seen = []

    def another_run_adds_march(name):
        if name == SPY_MANIFEST and not seen:
            seen.append(name)
            bucket.put(SPY_MANIFEST, manifest_with("2025-03", "2025-04"))

    bucket.before_write = another_run_adds_march
    run(monkeypatch, ["SPY"], [(2025, 5)], small_bars(["SPY"], [(2025, 5)]), bucket)

    doc = manifest_doc(bucket)
    assert set(doc["months"]) == {"2025-03", "2025-04", "2025-05"}
    assert doc["months"]["2025-03"]["written_by"] == "another run"
    assert doc["months"]["2025-05"]["rows"] == 961


def test_six_mismatches_raise(monkeypatch):
    bucket = MemoryBucket()
    bucket.put(SPY_MANIFEST, manifest_with("2025-04"))

    def always_rewritten(name):
        if name == SPY_MANIFEST:
            bucket.put(SPY_MANIFEST, manifest_with("2025-04"))

    bucket.before_write = always_rewritten
    with pytest.raises(xb.GenerationMismatch):
        run(monkeypatch, ["SPY"], [(2025, 5)], small_bars(["SPY"], [(2025, 5)]), bucket)

    assert xb.MANIFEST_RETRIES == 5
    assert bucket.writes.count(SPY_MANIFEST) == 6
    assert set(manifest_doc(bucket)["months"]) == {"2025-04"}


def test_a_failed_manifest_read_writes_nothing(monkeypatch):
    bucket = MemoryBucket()
    bucket.put(SPY_MANIFEST, manifest_with("2025-04"))
    real_read = bucket.read

    def read(name):
        if name == SPY_MANIFEST:
            raise PermissionError("403 on the manifest")
        return real_read(name)

    monkeypatch.setattr(bucket, "read", read)
    with pytest.raises(PermissionError):
        run(monkeypatch, ["SPY"], [(2025, 5)], small_bars(["SPY"], [(2025, 5)]), bucket)
    assert bucket.writes == []
    assert set(manifest_doc(bucket)["months"]) == {"2025-04"}


@pytest.mark.parametrize("stored_bytes", [
    b"{",
    b'{"version": 2, "ticker": "SPY", "months": {}}',
    b'{"version": 1, "ticker": "QQQ", "months": {}}',
    b'[1]',
])
def test_a_bad_manifest_is_never_replaced(monkeypatch, stored_bytes):
    bucket = MemoryBucket()
    bucket.put(SPY_MANIFEST, stored_bytes)
    with pytest.raises(ValueError):
        run(monkeypatch, ["SPY"], [(2025, 5)], small_bars(["SPY"], [(2025, 5)]), bucket)
    assert bucket.objects[SPY_MANIFEST] == stored_bytes
    assert bucket.writes == []


def _exported_may_and_june(monkeypatch) -> MemoryBucket:
    bucket = MemoryBucket()
    months = [(2025, 5), (2025, 6)]
    run(monkeypatch, ["SPY"], months, small_bars(["SPY"], months), bucket,
        now=NOW - timedelta(days=1))
    bucket.reads.clear(), bucket.writes.clear(), bucket.preconditions.clear()
    return bucket


def test_second_month_upload_failure_leaves_the_first_month_whole(monkeypatch):
    bucket = _exported_may_and_june(monkeypatch)
    may_before, june_before = bucket.objects[MAY], bucket.objects[JUNE]
    june_entry_before = manifest_doc(bucket)["months"]["2025-06"]
    bucket.fail_write = lambda name: ConnectionError("reset") if name == JUNE else None

    months = [(2025, 5), (2025, 6)]
    with pytest.raises(ConnectionError):
        run(monkeypatch, ["SPY"], months,
            small_bars(["SPY"], months, day_high=700.0, day_low=690.0), bucket)

    doc = manifest_doc(bucket)
    assert bucket.objects[MAY] != may_before                       # the new file
    assert doc["months"]["2025-05"]["sha256"] == sha(bucket.objects[MAY])
    assert doc["months"]["2025-05"]["exported_at"] == NOW.isoformat()
    assert bucket.objects[JUNE] == june_before
    assert doc["months"]["2025-06"] == june_entry_before
    assert june_entry_before["sha256"] == sha(june_before)


@pytest.mark.parametrize("where,failure", [
    ("bars", ConnectionError("connection refused")),
    ("daily", KeyError("high")),
    ("upload", ConnectionError("reset")),
    ("upload", PermissionError("403")),
])
def test_failures_leave_the_manifest_as_it_was(monkeypatch, where, failure):
    bucket = _exported_may_and_june(monkeypatch)
    manifest_before = bucket.objects[SPY_MANIFEST]
    bars = small_bars(["SPY"], [(2025, 5)], day_high=700.0, day_low=690.0)
    daily = None
    if where == "bars":
        bars[("SPY", 2025, 5)] = failure
    elif where == "daily":
        daily = {"SPY": failure}
    else:
        bucket.fail_write = lambda name: failure if name == MAY else None

    with pytest.raises(type(failure)) as raised:
        run(monkeypatch, ["SPY"], [(2025, 5)], bars, bucket, daily=daily)
    assert raised.value is failure
    assert bucket.objects[SPY_MANIFEST] == manifest_before
    assert SPY_MANIFEST not in bucket.writes


def test_manifest_write_failure_after_an_upload(monkeypatch):
    bucket = _exported_may_and_june(monkeypatch)
    may_before = bucket.objects[MAY]
    bucket.fail_write = (
        lambda name: ConnectionError("reset") if name == SPY_MANIFEST else None)

    with pytest.raises(ConnectionError):
        run(monkeypatch, ["SPY"], [(2025, 5)],
            small_bars(["SPY"], [(2025, 5)], day_high=700.0, day_low=690.0), bucket)

    assert bucket.objects[MAY] != may_before
    recorded = manifest_doc(bucket)["months"]["2025-05"]["sha256"]
    assert recorded == sha(may_before)
    assert recorded != sha(bucket.objects[MAY])


def test_io_shape(monkeypatch):
    # Rule 0: the round-trips of a run, pinned. Nightly: 6 bars reads, 3 daily
    # reads, 3 manifest reads, 6 uploads, 6 manifest writes.
    months = [(2026, 9), (2026, 10)]
    bucket = MemoryBucket()
    result, calls = run(monkeypatch, xb.EXPORT_TICKERS, months,
                        small_bars(xb.EXPORT_TICKERS, months), bucket)

    b1 = [c for c in calls if "market_data_intraday" in c["sql"]]
    b2 = [c for c in calls if "market_data_daily" in c["sql"]]
    assert (len(b1), len(b2), len(calls)) == (6, 3, 9)
    assert all(c["timeout_s"] == 120 for c in calls)
    assert all(squash(c["sql"]) == B1 for c in b1)
    assert all(squash(c["sql"]) == B2 for c in b2)
    manifests = [xb.manifest_name(t) for t in xb.EXPORT_TICKERS]
    assert sorted(bucket.reads) == sorted(manifests)
    assert bucket.writes == [
        name for t in xb.EXPORT_TICKERS for y, m in months
        for name in (xb.object_name(t, y, m), xb.manifest_name(t))]
    assert result["months"] == 6
    assert result["rows"] == 6 * 961 == sum(
        e["rows"] for n in manifests for e in manifest_doc(bucket, n)["months"].values())
    assert isinstance(result["seconds"], float) and result["seconds"] >= 0
    # Per ticker: the daily read, then the manifest read, then the months.
    assert [c["params"]["t"] for c in calls] == [
        "SPY", "SPY", "SPY", "QQQ", "QQQ", "QQQ", "IWM", "IWM", "IWM"]
    assert "market_data_daily" in calls[0]["sql"]
    assert calls[0]["params"] == {
        "t": "SPY", "first": date(2026, 9, 1), "last": date(2026, 10, 31)}

    # The history: 12 bars reads, 1 daily read, 1 manifest read, 12 and 12 writes.
    year = xb.months_between((2025, 1), (2025, 12))
    bucket = MemoryBucket()
    result, calls = run(monkeypatch, ["SPY"], year, small_bars(["SPY"], year), bucket)
    b1 = [c for c in calls if "market_data_intraday" in c["sql"]]
    b2 = [c for c in calls if "market_data_daily" in c["sql"]]
    assert (len(b1), len(b2)) == (12, 1)
    assert b2[0]["params"] == {
        "t": "SPY", "first": date(2025, 1, 1), "last": date(2025, 12, 31)}
    assert bucket.reads == [SPY_MANIFEST]
    assert len(bucket.writes) == 24
    assert bucket.writes[0::2] == [xb.object_name("SPY", y, m) for y, m in year]
    assert bucket.writes[1::2] == [SPY_MANIFEST] * 12
    # Each write carries the generation the one before it returned: no re-read.
    assert [g for n, g in bucket.preconditions if n == SPY_MANIFEST] == list(range(12))
    assert result["months"] == 12
    assert result["rows"] == 12 * 961


def test_one_month_in_memory_at_a_time(monkeypatch):
    # Rule 0: memory is bounded to one ticker-month. Every frame the reader
    # handed out is dead by the time the next one is asked for.
    import gcp.database as database

    months = xb.months_between((2025, 1), (2025, 4))
    source = small_bars(["SPY"], months)
    handed_out: list = []
    live_at_each_read: list = []

    def strict(sql, params=None, timeout_s=None):
        if "market_data_daily" in sql:
            return EMPTY_DAILY
        gc.collect()
        live_at_each_read.append(sum(1 for ref in handed_out if ref() is not None))
        frame = source[(params["t"], params["start"].year, params["start"].month)].copy()
        handed_out.append(weakref.ref(frame))
        return frame

    monkeypatch.setattr(database, "query_to_dataframe_strict", strict)
    xb.export_window(["SPY"], months, bucket=MemoryBucket(), now_utc=NOW)

    assert len(handed_out) == 4
    assert live_at_each_read == [0, 0, 0, 0]


def test_a_rerun_converges(monkeypatch):
    months = [(2025, 5), (2025, 6)]
    bars = small_bars(["SPY"], months)
    bucket = MemoryBucket()
    run(monkeypatch, ["SPY"], months, bars, bucket, now=NOW)
    objects_first = {n: bucket.objects[n] for n in (MAY, JUNE)}
    doc_first = manifest_doc(bucket)

    later = NOW + timedelta(hours=24)
    run(monkeypatch, ["SPY"], months, bars, bucket, now=later)
    doc_second = manifest_doc(bucket)

    assert {n: bucket.objects[n] for n in (MAY, JUNE)} == objects_first
    assert sorted(doc_second["months"]) == ["2025-05", "2025-06"] == sorted(doc_first["months"])
    for key in ("2025-05", "2025-06"):
        first, second = dict(doc_first["months"][key]), dict(doc_second["months"][key])
        assert first.pop("exported_at") == NOW.isoformat()
        assert second.pop("exported_at") == later.isoformat()
        assert first == second
    assert sorted(bucket.objects) == sorted([MAY, JUNE, SPY_MANIFEST])


def test_each_month_logs_its_progress(monkeypatch, caplog):
    months = [(2026, 9), (2026, 10)]
    with caplog.at_level(logging.INFO):
        run(monkeypatch, xb.EXPORT_TICKERS, months,
            small_bars(xb.EXPORT_TICKERS, months), MemoryBucket())

    lines = [r.getMessage() for r in caplog.records
             if r.getMessage().startswith("bars month: ")]
    assert len(lines) == 6
    assert lines[0] == ("bars month: SPY 2026-09 rows=961 stored=961 dropped=0 "
                        "inferred=0 state=unmeasured (1/6)")
    assert "IWM 2026-10" in lines[-1] and lines[-1].endswith("(6/6)")
    assert not [r for r in caplog.records if r.getMessage().startswith("bars export:")]


def test_months_between_and_nightly_months():
    assert xb.months_between((2025, 11), (2026, 2)) == [
        (2025, 11), (2025, 12), (2026, 1), (2026, 2)]
    assert xb.months_between((2026, 2), (2026, 2)) == [(2026, 2)]
    assert xb.months_between((2026, 2), (2026, 1)) == []
    assert xb.nightly_months(date(2026, 10, 31)) == [(2026, 9), (2026, 10)]
    assert xb.nightly_months(date(2026, 1, 5)) == [(2025, 12), (2026, 1)]
    assert len(xb.months_between((2015, 1), (2026, 11))) == 143


# -- Task 5: read_bars, and nothing else reads the copy -------------------------

REPO = Path(__file__).resolve().parents[2]


def to_disk(bucket: MemoryBucket, root: Path) -> Path:
    """Every object of *bucket* under *root*, as ``gcloud storage cp -r
    .../intraday-bars/v1/1min/SPY ./bars/`` leaves a ticker's folder."""
    for name, data in bucket.objects.items():
        assert name.startswith(xb.PREFIX + "/")
        target = root / name[len(xb.PREFIX) + 1:]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def test_read_bars_returns_the_exported_rows_and_entries(monkeypatch, tmp_path):
    bucket = MemoryBucket()
    months = [(2025, 5), (2025, 6)]
    bars = {("SPY", y, m): month_rows(y, m, inserted=NEW) for y, m in months}
    run(monkeypatch, ["SPY"], months, bars, bucket, daily={"SPY": pd.concat(
        [daily_rows(2025, 5), daily_rows(2025, 6)], ignore_index=True)})
    root = to_disk(bucket, tmp_path)

    got, entries = xb.read_bars(root, "SPY", "2025-05", "2025-06")

    want = pd.concat([expected_table(2025, 5), expected_table(2025, 6)], ignore_index=True)
    assert_rows_equal(got, want)
    assert str(got["ts"].dt.tz) == "UTC"
    assert got["ts"].is_monotonic_increasing and got["ts"].is_unique
    assert list(got.index) == list(range(len(want)))
    assert str(got["volume"].dtype) == "Int64"
    doc = manifest_doc(bucket)
    assert [e["month"] for e in entries] == ["2025-05", "2025-06"]
    assert entries == [{**doc["months"][key], "month": key} for key in ("2025-05", "2025-06")]
    assert entries[0]["basis"]["state"] == "as_traded"
    assert entries[0]["sha256"] == sha(bucket.objects[MAY])

    june, june_entries = xb.read_bars(str(root), "SPY", "2025-06", "2025-06")
    assert_rows_equal(june, expected_table(2025, 6))
    assert list(june.index) == list(range(len(june)))
    assert [e["month"] for e in june_entries] == ["2025-06"]


def _exported_on_disk(monkeypatch, tmp_path) -> Path:
    return to_disk(_exported_may_and_june(monkeypatch), tmp_path)


@pytest.mark.parametrize("case,error,match", [
    ("no_manifest", FileNotFoundError, "manifest.json"),
    ("file_deleted", FileNotFoundError, "2025-05"),
    ("no_entry", KeyError, "2025-07"),
    ("file_replaced", ValueError, "2025-05"),
    ("version_2", ValueError, "version"),
    ("first_after_last", ValueError, "2025-06"),
    ("not_a_month", ValueError, "2025-5"),
])
def test_read_bars_errors(monkeypatch, tmp_path, case, error, match):
    root = _exported_on_disk(monkeypatch, tmp_path)
    first, last = "2025-05", "2025-06"
    if case == "no_manifest":
        (root / "SPY" / "manifest.json").unlink()
    elif case == "file_deleted":
        (root / "SPY" / "2025-05.parquet").unlink()
    elif case == "no_entry":
        last = "2025-07"
    elif case == "file_replaced":
        # Another valid Parquet file under the month's name: June's.
        (root / "SPY" / "2025-05.parquet").write_bytes(
            (root / "SPY" / "2025-06.parquet").read_bytes())
    elif case == "version_2":
        path = root / "SPY" / "manifest.json"
        doc = json.loads(path.read_text())
        doc["version"] = 2
        path.write_text(json.dumps(doc))
    elif case == "first_after_last":
        first, last = "2025-06", "2025-05"
    elif case == "not_a_month":
        first = "2025-5"

    with pytest.raises(error, match=match):
        xb.read_bars(root, "SPY", first, last)


def _state_month(state: str):
    """Task 3's inputs for a month in *state*: (rows, daily)."""
    if state == "inferred":
        rows = month_rows(2025, 5, inserted=NEW)
        rows.loc[rows["ts"] == pd.Timestamp("2025-05-16 14:00", tz="UTC"), "inserted_at"] = OLD
        return rows, daily_rows(2025, 5)
    if state == "adjusted":
        return (month_rows(2025, 5, inserted=NEW,
                           days={"2025-05-07": {"f_high": 0.99430, "f_low": 0.99430}}),
                daily_rows(2025, 5))
    if state == "partial":
        return month_rows(2025, 5, inserted=NEW), daily_rows(2025, 5, skip=("2025-05-14",))
    if state == "unmeasured":
        return month_rows(2025, 5, inserted=NEW), daily_rows(2025, 5, src="alphavantage_1min")
    raise AssertionError(state)


@pytest.mark.parametrize("state", ["inferred", "adjusted", "partial", "unmeasured"])
def test_read_bars_does_not_refuse_a_month_for_its_state(monkeypatch, tmp_path, state):
    rows, daily = _state_month(state)
    bucket = MemoryBucket()
    run(monkeypatch, ["SPY"], [(2025, 5)], {("SPY", 2025, 5): rows}, bucket,
        daily={"SPY": daily})

    got, entries = xb.read_bars(to_disk(bucket, tmp_path), "SPY", "2025-05", "2025-05")
    assert len(got) == 20181
    assert entries[0]["basis"]["state"] == state


def test_a_month_with_rows_0_returns_no_row(monkeypatch, tmp_path):
    empty = pd.DataFrame(columns=BARS_COLUMNS)
    bucket = MemoryBucket()
    run(monkeypatch, ["SPY"], [(2025, 5)], {("SPY", 2025, 5): empty}, bucket)
    assert sorted(bucket.objects) == [SPY_MANIFEST]            # no file for the month

    got, entries = xb.read_bars(to_disk(bucket, tmp_path / "a"), "SPY", "2025-05", "2025-05")
    assert len(got) == 0 and list(got.columns) == FILE_COLUMNS
    assert entries[0]["rows"] == 0 and entries[0]["file"] is None

    # Review Focus: an earlier export wrote the month, and it holds no row now.
    # The old object is still beside the manifest; it is not read.
    bucket = _exported_may_and_june(monkeypatch)
    run(monkeypatch, ["SPY"], [(2025, 5)], {("SPY", 2025, 5): empty}, bucket)
    assert MAY in bucket.objects
    assert manifest_doc(bucket)["months"]["2025-05"]["file"] is None
    root = to_disk(bucket, tmp_path / "b")
    assert (root / "SPY" / "2025-05.parquet").exists()

    got, entries = xb.read_bars(root, "SPY", "2025-05", "2025-05")
    assert len(got) == 0
    assert entries[0]["rows"] == 0
    both, _ = xb.read_bars(root, "SPY", "2025-05", "2025-06")
    assert len(both) == 961                                    # June's rows only


def test_after_a_failed_run_read_bars_tells_the_months_apart(monkeypatch, tmp_path):
    newer = dict(day_high=700.0, day_low=690.0)
    months = [(2025, 5), (2025, 6)]

    # The second month's upload failed: May is whole and readable.
    bucket = _exported_may_and_june(monkeypatch)
    bucket.fail_write = lambda name: ConnectionError("reset") if name == JUNE else None
    with pytest.raises(ConnectionError):
        run(monkeypatch, ["SPY"], months, small_bars(["SPY"], months, **newer), bucket)
    may, _ = xb.read_bars(to_disk(bucket, tmp_path / "a"), "SPY", "2025-05", "2025-05")
    assert len(may) == 961 and may["high"].max() == 700.0

    # A month's upload succeeded and its manifest write failed, with an older
    # entry: the entry describes the old file, and the month is refused by name.
    bucket = _exported_may_and_june(monkeypatch)
    bucket.fail_write = (
        lambda name: ConnectionError("reset") if name == SPY_MANIFEST else None)
    with pytest.raises(ConnectionError):
        run(monkeypatch, ["SPY"], [(2025, 5)],
            small_bars(["SPY"], [(2025, 5)], **newer), bucket)
    root = to_disk(bucket, tmp_path / "b")
    with pytest.raises(ValueError, match="2025-05"):
        xb.read_bars(root, "SPY", "2025-05", "2025-05")
    june, _ = xb.read_bars(root, "SPY", "2025-06", "2025-06")       # June is untouched
    assert len(june) == 961

    # Review Focus: the same failure on the month's first export, with an
    # older manifest that has no entry for it.
    bucket = _exported_may_and_june(monkeypatch)
    bucket.fail_write = (
        lambda name: ConnectionError("reset") if name == SPY_MANIFEST else None)
    with pytest.raises(ConnectionError):
        run(monkeypatch, ["SPY"], [(2025, 7)], small_bars(["SPY"], [(2025, 7)]), bucket)
    with pytest.raises(KeyError, match="2025-07"):
        xb.read_bars(to_disk(bucket, tmp_path / "c"), "SPY", "2025-07", "2025-07")

    # And on the ticker's first export ever: no manifest at all.
    bucket = MemoryBucket()
    bucket.fail_write = (
        lambda name: ConnectionError("reset") if name == SPY_MANIFEST else None)
    with pytest.raises(ConnectionError):
        run(monkeypatch, ["SPY"], [(2025, 5)], small_bars(["SPY"], [(2025, 5)]), bucket)
    with pytest.raises(FileNotFoundError):
        xb.read_bars(to_disk(bucket, tmp_path / "d"), "SPY", "2025-05", "2025-05")


_ISOLATED = """
import importlib.abc, sys

BLOCKED = ("gcp.database", "lib", "sqlalchemy", "google", "requests",
           "pandas_market_calendars")


class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if any(name == b or name.startswith(b + ".") for b in BLOCKED):
            raise ImportError("blocked for this test: " + name)
        return None


sys.meta_path.insert(0, Refuse())
for name in BLOCKED:
    try:
        __import__(name)
    except ImportError:
        continue
    raise SystemExit("the block does not hold for " + name)

from gcp.fetchers.export_intraday_bars import read_bars

bars, months = read_bars(sys.argv[1], "SPY", "2025-05", "2025-06")
loaded = sorted(m for m in sys.modules if any(m == b or m.startswith(b + ".") for b in BLOCKED))
print(len(bars), [m["month"] for m in months], loaded)
"""


def test_read_bars_needs_only_pandas_and_pyarrow(monkeypatch, tmp_path):
    root = _exported_on_disk(monkeypatch, tmp_path)
    done = subprocess.run(
        [sys.executable, "-c", _ISOLATED, str(root)], cwd=REPO, capture_output=True,
        text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "1922 ['2025-05', '2025-06'] []"


# What marks a file as reading the copy. A docstring may name the module or the
# prefix; code may not.
MODULE = "export_intraday_bars"
EXPORT_MODULE = "gcp/fetchers/export_intraday_bars.py"
FETCH_MODULE = "gcp/fetchers/fetch_alphavantage_intraday.py"
TREE_ROOTS = ("gcp", "lib", "scripts", "platform")
TREE_SKIP = {"__pycache__", "node_modules", ".venv", "venv"}


def copy_uses(source: str) -> set[str]:
    """How *source* reaches the bucket copy: any of ``imports-module`` (an
    import of the export module, or a string that holds its name),
    ``names-read_bars`` and ``names-prefix`` (a string holding the prefix).

    It cannot see a module name built at run time
    (``"export_" + "intraday_bars"``), nor a name reached through a variable
    another file assigned.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    found = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names] + [a.asname or "" for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = ([node.module or ""] + [a.name for a in node.names]
                     + [a.asname or "" for a in node.names])
        elif isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.keyword):
            names = [node.arg or ""]
        for name in names:
            if MODULE in name.split("."):
                found.add("imports-module")
            if "read_bars" in name.split("."):
                found.add("names-read_bars")
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings):
            if MODULE in node.value:
                found.add("imports-module")
            if "read_bars" in node.value:
                found.add("names-read_bars")
            if "intraday-bars/" in node.value:
                found.add("names-prefix")
    return found


@pytest.mark.parametrize("snippet,want", [
    ("from gcp.fetchers.export_intraday_bars import read_bars",
     {"imports-module", "names-read_bars"}),
    ("from gcp.fetchers import export_intraday_bars as xb", {"imports-module"}),
    ("import gcp.fetchers.export_intraday_bars", {"imports-module"}),
    ('import importlib\nm = importlib.import_module("gcp.fetchers.export_intraday_bars")',
     {"imports-module"}),
    ('def f(b, t):\n    return f"gs://{b}/intraday-bars/v1/1min/{t}"', {"names-prefix"}),
    ("def f(m):\n    return m.read_bars('.', 'SPY', '2025-01', '2025-02')",
     {"names-read_bars"}),
    ('def f(m):\n    return getattr(m, "read_bars")', {"names-read_bars"}),
    ('def f():\n    """Bars come from gcp.fetchers.export_intraday_bars (read_bars),\n'
     '    under intraday-bars/v1/1min/."""\n    return 1', set()),
    ('"""The export module is gcp/fetchers/export_intraday_bars.py."""\nX = 1', set()),
    ("import pandas as pd\nX = pd.DataFrame()", set()),
])
def test_the_copy_check_catches_each_way_in(snippet, want):
    assert copy_uses(snippet) == want


def test_nothing_in_the_tree_reads_the_copy():
    # CLAUDE.md 3.7.1: the bucket copy is never a source for the tree. No job,
    # replay, backtest or route imports the export module or names its prefix,
    # so nothing can fall back to it when Cloud SQL fails. The one caller is
    # the fetch job, which only writes the copy.
    uses = {}
    for root in TREE_ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            rel = path.relative_to(REPO)
            if TREE_SKIP.isdisjoint(rel.parts):
                found = copy_uses(path.read_text(encoding="utf-8"))
                if found:
                    uses[rel.as_posix()] = found
    assert uses.pop(EXPORT_MODULE) >= {"names-prefix", "names-read_bars"}   # the module itself
    fetch = uses.pop(FETCH_MODULE, set())
    assert fetch <= {"imports-module"}, fetch         # it writes; it never reads back
    assert uses == {}


# -- Task 6: the nightly run exports after its fetch ----------------------------


def _refuse_queries(monkeypatch):
    """Any strict read fails the test: the path under test must ask nothing."""
    import gcp.database as database

    def refuse(*_args, **_kwargs):
        raise AssertionError("a query was issued")

    monkeypatch.setattr(database, "query_to_dataframe_strict", refuse)
    monkeypatch.setattr(fai, "query_to_dataframe_strict", refuse)


def nightly(monkeypatch, argv, *, configured=True, export=None, process=None, env=None,
            real_export=False):
    """Run fai.main() as the job would, with the fetch stubbed: returns
    (exit code, the export_window calls as (tickers, months) pairs)."""
    calls: list = []

    def recorder(tickers, months, **kwargs):
        assert kwargs == {}                   # the bucket and the clock are the defaults
        calls.append((tickers, months))
        if isinstance(export, BaseException):
            raise export
        return export or {"months": 6, "rows": 123456, "seconds": 4.2}

    fetched: list = []

    def fake_process(symbol, start, end, keys, force):
        fetched.append(symbol)
        return process(symbol) if process is not None else fai.OUTCOME_OK

    monkeypatch.setattr(fai, "get_api_keys", lambda: ["k"])
    monkeypatch.setattr(fai, "resolve_all_symbols", lambda: ["SPY", "QQQ", "IWM"])
    monkeypatch.setattr(fai, "process_symbol", fake_process)
    monkeypatch.setattr(fai, "is_cloud_sql_configured", lambda: configured)
    monkeypatch.setattr(fai, "market_today", lambda: date(2026, 10, 31))
    if not real_export:
        monkeypatch.setattr(xb, "export_window", recorder)
    for name in ("CLOUD_RUN_TASK_COUNT", "CLOUD_RUN_TASK_INDEX", "INTRADAY_BARS_EXPORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday", *argv])
    try:
        fai.main()
        code = 0
    except SystemExit as stop:
        code = stop.code
    nightly.fetched = fetched
    return code, calls


NIGHTLY_ARGS = ["--symbol=ALL", "--force"]


def _messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def test_the_nightly_arguments_export_two_eastern_months(monkeypatch):
    code, calls = nightly(monkeypatch, NIGHTLY_ARGS)
    assert code == 0
    assert len(calls) == 1
    tickers, months = calls[0]
    assert tickers == ("SPY", "QQQ", "IWM")
    assert months == [(2026, 9), (2026, 10)]
    assert nightly.fetched == ["SPY", "QQQ", "IWM"]

    # The clock the spec names: 21:00 ET on 2026-10-31 is already 2026-11-01
    # in a UTC container, whose date would give the wrong two months.
    at = datetime(2026, 11, 1, 1, tzinfo=timezone.utc)
    assert at.astimezone(ET).date() == date(2026, 10, 31)
    assert xb.nightly_months(at.date()) == [(2026, 10), (2026, 11)]


@pytest.mark.parametrize("argv,env", [
    (["--symbol=ALL"], None),
    (["--symbol=ALL", "--force", "--start-date", "2026-10-01"], None),
    (["--symbol=ALL", "--force", "--end-date", "2026-10-31"], None),
    (["--symbols-file", "<file>", "--force"], None),
    (["--symbol", "SPY", "--force"], None),
    (["--force"], {"CLOUD_RUN_TASK_COUNT": "4"}),
    (NIGHTLY_ARGS, {"CLOUD_RUN_TASK_COUNT": "4"}),
])
def test_other_argument_shapes_export_nothing(monkeypatch, tmp_path, caplog, argv, env):
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("SPY\n")
    argv = [str(symbols) if a == "<file>" else a for a in argv]
    with caplog.at_level(logging.INFO):
        code, calls = nightly(monkeypatch, argv, env=env)
    assert calls == []
    assert code == 0
    assert nightly.fetched                         # the fetch itself ran
    assert not [m for m in _messages(caplog) if m.startswith("bars export")]


@pytest.mark.parametrize("value", ["off", "OFF", "Off"])
def test_the_variable_turns_it_off(monkeypatch, caplog, value):
    with caplog.at_level(logging.INFO):
        code, calls = nightly(monkeypatch, NIGHTLY_ARGS, env={"INTRADAY_BARS_EXPORT": value})
    assert calls == [] and code == 0
    assert len([m for m in _messages(caplog) if "INTRADAY_BARS_EXPORT" in m]) == 1


def test_any_other_value_of_the_variable_exports(monkeypatch):
    _, calls = nightly(monkeypatch, NIGHTLY_ARGS, env={"INTRADAY_BARS_EXPORT": "on"})
    assert len(calls) == 1


def test_database_not_configured_exports_nothing_and_asks_nothing(monkeypatch, caplog):
    _refuse_queries(monkeypatch)
    with caplog.at_level(logging.INFO):
        code, calls = nightly(monkeypatch, NIGHTLY_ARGS, configured=False)
    assert calls == [] and code == 0
    said = [m for m in _messages(caplog) if m.startswith("bars export skipped")]
    assert len(said) == 1 and "not configured" in said[0]


def test_gcs_bucket_unset_is_a_failed_export(monkeypatch, caplog):
    _refuse_queries(monkeypatch)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with caplog.at_level(logging.INFO):
        code, _ = nightly(monkeypatch, NIGHTLY_ARGS, real_export=True)
    assert code == 1
    failed = [m for m in _messages(caplog) if m.startswith("bars export failed")]
    assert len(failed) == 1
    assert failed[0].startswith("bars export failed (defect)")
    assert "GCS_BUCKET" in failed[0]


def test_success_logs_one_line(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        nightly(monkeypatch, NIGHTLY_ARGS)
    lines = [m for m in _messages(caplog) if m.startswith("bars export:")]
    assert lines == ["bars export: 6 months, 123456 rows, 4.2 s"]


@pytest.mark.parametrize("failure,kind", [
    (ConnectionError("connection refused"), "outage"),
    (KeyError("high"), "defect"),
])
def test_a_failed_export_logs_its_kind_after_the_fetch_summary_and_exits_1(
        monkeypatch, caplog, failure, kind):
    with caplog.at_level(logging.INFO):
        code, calls = nightly(monkeypatch, NIGHTLY_ARGS, export=failure)
    assert code == 1 and len(calls) == 1
    messages = _messages(caplog)
    failed = [i for i, m in enumerate(messages) if m.startswith("bars export failed")]
    summary = [i for i, m in enumerate(messages) if m.startswith("Run summary:")]
    assert len(failed) == 1 and len(summary) == 1
    assert messages[failed[0]].startswith(f"bars export failed ({kind})")
    assert failed[0] > summary[0]
    assert not [m for m in messages if m.startswith("bars export:")]
    # The traceback is in the log: a defect is not reduced to its message.
    record = [r for r in caplog.records if r.getMessage().startswith("bars export failed")][0]
    assert record.exc_info is not None and record.exc_info[1] is failure
    assert record.levelno == logging.ERROR


def test_the_export_runs_when_a_ticker_failed(monkeypatch, caplog):
    def process(symbol):
        if symbol == "QQQ":
            raise RuntimeError("write failed")
        return fai.OUTCOME_OK

    with caplog.at_level(logging.INFO):
        code, calls = nightly(monkeypatch, NIGHTLY_ARGS, process=process)
    assert len(calls) == 1
    assert code == 1
    assert [m for m in _messages(caplog) if m.startswith("bars export:")]


# -- Task 7: --export-bars-from -------------------------------------------------


def history(monkeypatch, argv, *, configured=True, bucket="b", export=None, env=None):
    """Run fai.main() with --export-bars-from arguments: (exit code, the
    export_window calls). Asking for an API key or fetching fails the test."""
    def no_fetch(*_args, **_kwargs):
        pytest.fail("--export-bars-from fetches nothing")

    code, calls = None, None
    monkeypatch.setattr(fai, "get_api_keys", no_fetch)
    if bucket is None:
        monkeypatch.delenv("GCS_BUCKET", raising=False)
    else:
        monkeypatch.setenv("GCS_BUCKET", bucket)

    recorded: list = []

    def recorder(tickers, months, **kwargs):
        assert kwargs == {}
        recorded.append((tickers, months))
        if isinstance(export, BaseException):
            raise export
        return {"months": len(tickers) * len(months), "rows": 1000, "seconds": 1.5}

    monkeypatch.setattr(fai, "resolve_all_symbols", no_fetch)
    monkeypatch.setattr(fai, "process_symbol", no_fetch)
    monkeypatch.setattr(fai, "is_cloud_sql_configured", lambda: configured)
    monkeypatch.setattr(fai, "market_today", lambda: date(2026, 10, 31))
    monkeypatch.setattr(xb, "export_window", recorder)
    for name in ("CLOUD_RUN_TASK_COUNT", "CLOUD_RUN_TASK_INDEX", "INTRADAY_BARS_EXPORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (env or {}).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["fetch_alphavantage_intraday", *argv])
    with pytest.raises(SystemExit) as stop:      # every list mode ends in sys.exit
        fai.main()
    return stop.value.code, recorded


@pytest.mark.parametrize("extra,tickers", [
    ([], ("SPY", "QQQ", "IWM")),
    (["--symbol=ALL"], ("SPY", "QQQ", "IWM")),
    (["--symbol", "SPY"], ("SPY",)),
    (["--symbol", "spy"], ("SPY",)),
    (["--symbol", " iwm "], ("IWM",)),
])
def test_export_bars_from_writes_every_month_to_the_current_one(
        monkeypatch, caplog, extra, tickers):
    with caplog.at_level(logging.INFO):
        code, calls = history(monkeypatch, ["--export-bars-from", "2026-08", *extra])
    assert code == 0
    assert len(calls) == 1
    assert tuple(calls[0][0]) == tickers
    assert calls[0][1] == [(2026, 8), (2026, 9), (2026, 10)]
    assert len([m for m in _messages(caplog) if m.startswith("bars export:")]) == 1


def test_export_bars_from_the_current_month_alone(monkeypatch):
    code, calls = history(monkeypatch, ["--export-bars-from=2026-10", "--symbol=SPY"])
    assert code == 0 and calls == [(("SPY",), [(2026, 10)])]


@pytest.mark.parametrize("symbol", ["AMD", "SPY,QQQ", "SPY QQQ"])
def test_another_ticker_exits_1_before_any_query(monkeypatch, symbol):
    _refuse_queries(monkeypatch)
    code, calls = history(monkeypatch, ["--export-bars-from", "2026-08", "--symbol", symbol])
    assert code == 1 and calls == []


@pytest.mark.parametrize("kwargs", [
    {"configured": False}, {"bucket": None}, {"bucket": ""}, {"bucket": "  "}])
def test_not_configured_exits_1(monkeypatch, kwargs):
    _refuse_queries(monkeypatch)
    code, calls = history(monkeypatch, ["--export-bars-from", "2026-08"], **kwargs)
    assert code == 1 and calls == []


def test_more_than_one_task_exits_1(monkeypatch):
    # N tasks would each export the same months at once.
    _refuse_queries(monkeypatch)
    code, calls = history(monkeypatch, ["--export-bars-from", "2026-08"],
                          env={"CLOUD_RUN_TASK_COUNT": "4"})
    assert code == 1 and calls == []


@pytest.mark.parametrize("argv", [
    ["--export-bars-from", "2026-08", "--replace-months", "x"],
    ["--export-bars-from", "2026-08", "--verify-months", "x"],
    ["--export-bars-from", "2026-08", "--verify-basis", "x"],
    ["--export-bars-from", "2026-08", "--symbols-file", "f"],
    ["--export-bars-from", "2026-08", "--start-date", "2026-10-01"],
    ["--export-bars-from", "2026-08", "--end-date", "2026-10-31"],
    ["--export-bars-from", "2026-13"],
    ["--export-bars-from", "2026-00"],
    ["--export-bars-from", "2026-1"],
    ["--export-bars-from", "202601"],
    ["--export-bars-from", "2026-10-01"],
    ["--export-bars-from", "2026-11"],            # after the current Eastern month
    ["--export-bars-from", "2027-01"],
])
def test_export_bars_from_usage_errors(monkeypatch, capsys, argv):
    _refuse_queries(monkeypatch)
    monkeypatch.setattr(fai, "run_replace_months", lambda *a: pytest.fail("ran a list mode"))
    monkeypatch.setattr(fai, "run_verify_months", lambda *a: pytest.fail("ran a list mode"))
    monkeypatch.setattr(fai, "run_verify_basis", lambda *a: pytest.fail("ran a list mode"))
    code, calls = history(monkeypatch, argv)
    assert code == 2 and calls == []
    assert "--export-bars-from" in capsys.readouterr().err


def test_a_failed_history_export_exits_1(monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        code, calls = history(monkeypatch, ["--export-bars-from", "2026-08"],
                              export=ConnectionError("connection refused"))
    assert code == 1 and len(calls) == 1
    assert [m for m in _messages(caplog) if m.startswith("bars export failed (outage)")]


def test_run_export_bars_from_refuses_a_month_after_the_current_one(monkeypatch):
    # main() refuses it as a usage error; called directly it still does not
    # end quietly having written nothing.
    monkeypatch.setenv("GCS_BUCKET", "b")
    monkeypatch.delenv("CLOUD_RUN_TASK_COUNT", raising=False)
    monkeypatch.setattr(fai, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(fai, "market_today", lambda: date(2026, 10, 31))
    monkeypatch.setattr(xb, "export_window", lambda *a, **k: pytest.fail("exported"))
    assert fai.run_export_bars_from((2026, 11), "SPY") == 1


_AS_MAIN = """
import runpy, sys
from datetime import date

import pandas as pd

import gcp.database as database
import lib.eastern_time as eastern_time
from gcp.fetchers import export_intraday_bars
from tests.fixtures.intraday_bars_bucket import MemoryBucket
from tests.fixtures.intraday_checks import NEW, session_bars, stored

bars = stored(session_bars("2026-10-01"), inserted=NEW).assign(
    open=595.0, close=595.0, data_source="alphavantage")
daily = pd.DataFrame([{"date": date(2026, 10, 1), "high": 600.0, "low": 590.0,
                       "data_source": "alphavantage_daily"}])
asked = []


def strict(sql, params=None, timeout_s=None):
    asked.append("daily" if "market_data_daily" in sql else "bars")
    return daily if "market_data_daily" in sql else bars


bucket = MemoryBucket()
database.is_cloud_sql_configured = lambda: True
database.query_to_dataframe_strict = strict
export_intraday_bars.bucket_from_env = lambda: bucket
eastern_time.market_today = lambda: date(2026, 10, 31)
sys.argv = ["fetch_alphavantage_intraday", "--export-bars-from=2026-10", "--symbol=SPY"]
try:
    runpy.run_module("gcp.fetchers.fetch_alphavantage_intraday", run_name="__main__")
    code = "returned"
except SystemExit as stop:
    code = stop.code
print("RESULT", code, sorted(bucket.objects), asked)
"""


def test_the_module_run_as_main_exports_end_to_end(tmp_path):
    # The job starts as `python -m gcp.fetchers.fetch_alphavantage_intraday`, so
    # the export's own import of the fetch module loads it a second time under
    # its package name. One file and the manifest are written, exit 0.
    import os

    env = {k: v for k, v in os.environ.items()
           if k not in ("CLOUD_RUN_TASK_COUNT", "CLOUD_RUN_TASK_INDEX", "INTRADAY_BARS_EXPORT")}
    env["GCS_BUCKET"] = "b"
    done = subprocess.run([sys.executable, "-c", _AS_MAIN], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr
    result = [line for line in done.stdout.splitlines() if line.startswith("RESULT")]
    assert result == [
        "RESULT 0 ['intraday-bars/v1/1min/SPY/2026-10.parquet', "
        "'intraday-bars/v1/1min/SPY/manifest.json'] ['daily', 'bars']"]
    assert "bars export: 1 months, 961 rows" in done.stdout + done.stderr
