"""Unit tests for gcp/bar_recompute.py, the module the two recompute tools
share (FEAT-DATA-001: --re-resolve on the end-of-day resolver and
--recompute-premarket on the daily fetcher).

No database and no bucket: every read and upload is patched.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from gcp import bar_recompute as br
from gcp import gcs_utils

UTC = timezone.utc

VALUE_COLUMNS = (
    "pre_high", "pre_low", "pre_vwap", "pre_volume", "gap_pct", "pre_range_atr",
    "pre_excluded_stale_prints", "pre_excluded_spikes", "pre_filter_status",
    "pre_filter_params",
)


# ── identity ──────────────────────────────────────────────────────────


def test_run_id_is_the_execution_or_a_local_stamp(monkeypatch):
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "fetch-market-data-abc12")
    assert br.run_id() == "fetch-market-data-abc12"
    monkeypatch.delenv("CLOUD_RUN_EXECUTION")
    assert re.fullmatch(r"local-\d{8}T\d{6}Z", br.run_id())


def test_code_version_reads_the_image_stamp(monkeypatch, tmp_path):
    stamp = tmp_path / "build_info.json"
    stamp.write_text(json.dumps(
        {"git_commit": "abc", "git_dirty": False, "built_at": "2026-11-14T00:00:00Z"}))
    monkeypatch.setattr(br, "BUILD_INFO_PATH", stamp)
    assert br.code_version() == {
        "git_commit": "abc", "git_dirty": False, "built_at": "2026-11-14T00:00:00Z"}
    monkeypatch.setattr(br, "BUILD_INFO_PATH", tmp_path / "absent.json")
    assert br.code_version() == {"git_commit": None, "git_dirty": None, "built_at": None}


# ── the window ────────────────────────────────────────────────────────


def test_parse_window():
    today = date(2026, 11, 14)
    three = ["SPY", "QQQ", "IWM"]
    assert br.parse_window(None, "2026-10-01", "2026-10-06", today) == (
        three, date(2026, 10, 1), date(2026, 10, 6))
    assert br.parse_window("ALL", "2026-10-01", "2026-10-06", today) == (
        three, date(2026, 10, 1), date(2026, 10, 6))
    assert br.parse_window("spy qqq", "2026-10-01", "2026-10-06", today)[0] == ["SPY", "QQQ"]

    refused = [
        ("AMD", "2026-10-01", "2026-10-06"),
        ("SPY,QQQ", "2026-10-01", "2026-10-06"),
        (None, None, "2026-10-06"),
        (None, "2026-10-01", None),
        (None, "2026-10-07", "2026-10-06"),
        (None, "2026-10-01", "2026-11-14"),
        (None, "2026-10-01", "2026-11-15"),
        (None, "2026-5-1x", "2026-10-06"),
    ]
    for tickers, first, last in refused:
        with pytest.raises(br.Refusal):
            br.parse_window(tickers, first, last, today)


def test_a_refusal_reads_as_one_line():
    with pytest.raises(br.Refusal) as caught:
        br.parse_window("AMD", "2026-10-01", "2026-10-06", date(2026, 11, 14))
    assert "\n" not in str(caught.value)
    assert "AMD" in str(caught.value)


# ── proof ─────────────────────────────────────────────────────────────


def test_require_proven():
    ts = pd.to_datetime(["2026-09-24 13:00:00+00:00", "2026-09-24 13:01:00+00:00"])
    late = pd.to_datetime(["2026-11-14 02:00:00+00:00", "2026-11-14 02:00:00+00:00"])
    br.require_proven(ts, late)

    one_old = pd.to_datetime(["2026-11-14 02:00:00+00:00", "2026-09-24 22:00:00+00:00"])
    with pytest.raises(br.UnprovenRows) as caught:
        br.require_proven(ts, one_old)
    assert caught.value.unproven == 1
    assert caught.value.rows == 2

    # A row on or after the first true-UTC session is proven by its date.
    br.require_proven(pd.to_datetime(["2026-10-06 13:00:00+00:00"]),
                      pd.to_datetime(["2026-05-01 00:00:00+00:00"]))


def test_bars_basis():
    bars = pd.DataFrame({
        "ts": pd.to_datetime(["2026-10-06 13:31:00+00:00", "2026-10-06 13:30:00+00:00"]),
        "open": [100.02, 100.0],
        "high": [100.5, 100.25],
        "low": [99.5, 99.75],
        "close": [100.02, 100.0],
        "volume": [1000.0, np.nan],
        "inserted_at": pd.to_datetime(
            ["2026-10-07 02:00:00+00:00", "2026-10-07 01:00:00+00:00"]),
    })
    lines = [
        "2026-10-06T13:30:00.000000+00:00|100.0|100.25|99.75|100.0|",
        "2026-10-06T13:31:00.000000+00:00|100.02|100.5|99.5|100.02|1000",
    ]
    basis = br.bars_basis(bars)
    assert basis["rows"] == 2
    assert basis["sha256"] == hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    assert basis["first_ts"] == "2026-10-06T13:30:00.000000+00:00"
    assert basis["last_ts"] == "2026-10-06T13:31:00.000000+00:00"
    assert basis["inserted_min"] == "2026-10-07T01:00:00.000000+00:00"
    assert basis["inserted_max"] == "2026-10-07T02:00:00.000000+00:00"


# ── values ────────────────────────────────────────────────────────────


def test_values_bound_to_a_statement():
    assert br.db_value(float("nan"), "double precision") is None
    assert br.db_value(pd.NaT, "timestamptz") is None
    assert br.db_value(None, "varchar") is None
    assert br.db_value(pd.NA, "integer") is None

    whole = br.db_value(np.float64(7654321.0), "bigint")
    assert whole == 7654321 and type(whole) is int

    bound = br.db_value(datetime(2026, 10, 6, 20, 0), "timestamptz")
    assert bound.tzinfo is not None
    assert bound == datetime(2026, 10, 6, 20, 0, tzinfo=UTC)
    aware = br.db_value(pd.Timestamp("2026-10-06 16:00:00", tz="America/New_York"), "timestamptz")
    assert aware == datetime(2026, 10, 6, 20, 0, tzinfo=UTC)

    assert br.db_value({"b": 1, "a": 2}, "jsonb") == '{"a": 2, "b": 1}'
    assert br.db_value('{"x": 1.0}', "jsonb") == '{"x": 1.0}'

    with pytest.raises(ValueError):
        br.db_value(1.5, "integer")
    with pytest.raises(ValueError):
        br.db_value(1.0, "interval")


def test_values_the_ledger_holds():
    assert br.json_value(0.1 + 0.2) == 0.30000000000000004
    assert json.loads(json.dumps(br.json_value(np.float64(0.1 + 0.2)))) == 0.1 + 0.2
    assert br.json_value(float("nan")) is None
    assert br.json_value(pd.NaT) is None
    assert br.json_value(np.int64(3)) == 3 and type(br.json_value(np.int64(3))) is int
    assert br.json_value(datetime(2026, 10, 6, 19, 50, 0, 250000)) == \
        "2026-10-06T19:50:00.250000+00:00"
    assert br.json_value(pd.Timestamp("2026-10-06 15:50:00.250000", tz="America/New_York")) == \
        "2026-10-06T19:50:00.250000+00:00"
    assert br.json_value(date(2026, 10, 6)) == "2026-10-06"
    assert br.json_value({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    assert br.json_value("ok") == "ok"


def test_same_is_exact_and_null_safe():
    assert br.same(None, float("nan"))
    assert br.same(pd.NaT, None)
    assert not br.same(None, 0.0)
    assert not br.same(0.30000000000000004, 0.3)
    assert br.same(7654321, 7654321.0)
    assert br.same(pd.Timestamp("2026-10-06 20:00:00", tz="UTC"), datetime(2026, 10, 6, 20, 0))
    assert br.same("2026-10-06T20:00:00.000000+00:00", "2026-10-06T20:00:00.000000+00:00")
    assert not br.same(datetime(2026, 10, 6, 20, 0), datetime(2026, 10, 6, 20, 1))
    assert br.same('{"a": 1.0, "b": 2}', {"b": 2, "a": 1.0})
    assert not br.same('{"a": 1.0}', {"a": 1.5})
    assert not br.same("ok", "params_unavailable")


def test_a_fresh_read_time_never_makes_a_write():
    old = {
        "pre_high": 100.5, "pre_low": 99.5, "pre_vwap": 100.0, "pre_volume": 330000,
        "gap_pct": 1.0101, "pre_range_atr": None, "pre_excluded_stale_prints": None,
        "pre_excluded_spikes": None, "pre_filter_status": "params_unavailable",
        "pre_filter_params": None,
        "pre_fetched_at": datetime(2026, 11, 14, 12, 0, tzinfo=UTC),
    }
    new = dict(old, pre_fetched_at=datetime(2026, 11, 14, 13, 0, tzinfo=UTC))

    assert br.decide(old, new, "run-1", VALUE_COLUMNS) == (False, False)
    assert br.decide(old, new, None, VALUE_COLUMNS) == (False, True)
    assert br.decide(old, dict(new, pre_high=100.75), "run-1", VALUE_COLUMNS) == (True, True)

    drift_old = dict(old, pre_vwap=0.30000000000000004)
    drift_new = dict(new, pre_vwap=0.3)
    assert br.decide(drift_old, drift_new, "run-1", VALUE_COLUMNS) == (True, True)

    # NULL against NULL is equal; NULL against zero is not.
    assert br.decide(old, dict(new, pre_range_atr=None), "run-1", VALUE_COLUMNS) == (False, False)
    assert br.decide(old, dict(new, pre_range_atr=0.0), "run-1", VALUE_COLUMNS) == (True, True)
    # A marker read back from pandas as NaN is a NULL marker.
    assert br.decide(old, new, float("nan"), VALUE_COLUMNS) == (False, True)


# ── the report ────────────────────────────────────────────────────────


def _rows():
    return [
        br.ReportRow(
            ticker="SPY", session_date=date(2026, 10, 6), row_key="2026-10-06",
            old={"pre_high": 100.25, "pre_fetched_at": None},
            new={"pre_high": 0.1 + 0.2,
                 "pre_fetched_at": datetime(2026, 11, 14, 13, 0, 0, 5, tzinfo=UTC)},
            changed=True, status="recomputed", bars_rows=330, bars_sha256="abc"),
        br.ReportRow(
            ticker="QQQ", session_date=date(2026, 10, 6), row_key="2026-10-06",
            old={"pre_high": 400.0, "pre_fetched_at": None},
            new=None, changed=None, status="no_bars", bars_rows=None, bars_sha256=None),
    ]


def test_rows_csv():
    text = br.rows_csv(_rows(), ("pre_high", "pre_fetched_at"))
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == [
        "ticker", "session_date", "row_key", "old_pre_high", "old_pre_fetched_at",
        "new_pre_high", "new_pre_fetched_at", "changed", "status", "bars_rows",
        "bars_sha256", "written"]
    assert parsed[1] == [
        "SPY", "2026-10-06", "2026-10-06", "100.25", "", "0.30000000000000004",
        "2026-11-14T13:00:00.000005+00:00", "true", "recomputed", "330", "abc", "false"]
    assert parsed[2] == [
        "QQQ", "2026-10-06", "2026-10-06", "400.0", "", "", "", "", "no_bars", "", "",
        "false"]


def test_exit_code():
    def row(status):
        return br.ReportRow(ticker="SPY", session_date=date(2026, 10, 6), row_key="k",
                            old={}, new=None, changed=None, status=status,
                            bars_rows=None, bars_sha256=None)

    fine = [row("recomputed"), row("already_current"), row("trade_missing")]
    assert br.exit_code(fine) == 0
    assert br.exit_code(fine + [row("no_bars")]) == 1
    for status in br.REFUSED_STATUSES:
        assert br.exit_code([row(status)]) == 1
    assert set(br.REFUSED_STATUSES) == {
        "unproven_rows", "no_bars", "bars_incomplete", "daily_incomplete",
        "changed_underneath", "trade_diverged"}


def test_save_report(monkeypatch, tmp_path):
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    summary = {"run_id": "run-1", "counts": {"recomputed": 1}}

    where = br.save_report(br.TARGET_PREMARKET, "run-1", "a,b\n1,2\n", summary, str(tmp_path))
    folder = tmp_path / "bar-recompute" / "v1" / "daily-premarket" / "run-1"
    assert (folder / "rows.csv").read_text() == "a,b\n1,2\n"
    assert json.loads((folder / "summary.json").read_text()) == summary
    assert str(folder) in where

    uploads = []

    def record(bucket, blob_path, text, content_type):
        uploads.append((bucket, blob_path, content_type))
        return f"gs://{bucket}/{blob_path}"

    monkeypatch.setenv("GCS_BUCKET", "b")
    monkeypatch.setattr(gcs_utils, "upload_text_to_gcs", record)
    br.save_report(br.TARGET_PREMARKET, "run-1", "a,b\n", summary, None)
    assert [(b, p) for b, p, _ in uploads] == [
        ("b", "bar-recompute/v1/daily-premarket/run-1/rows.csv"),
        ("b", "bar-recompute/v1/daily-premarket/run-1/summary.json"),
    ]

    # --report-dir wins over the bucket.
    uploads.clear()
    br.save_report(br.TARGET_EXITS, "run-2", "a\n", summary, str(tmp_path))
    assert uploads == []
    assert (tmp_path / "bar-recompute" / "v1" / "signal-alert-exits" / "run-2" / "rows.csv").exists()

    failure = ConnectionError("bucket unreachable")

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(gcs_utils, "upload_text_to_gcs", fail)
    with pytest.raises(ConnectionError) as caught:
        br.save_report(br.TARGET_PREMARKET, "run-1", "a,b\n", summary, None)
    assert caught.value is failure

    monkeypatch.delenv("GCS_BUCKET")
    with pytest.raises(br.Refusal):
        br.save_report(br.TARGET_PREMARKET, "run-1", "a,b\n", summary, None)
    with pytest.raises(br.Refusal):
        br.require_report_destination(None)
    br.require_report_destination(str(tmp_path))


def test_upload_text_raises(monkeypatch):
    failure = ConnectionError("bucket unreachable")

    class Blob:
        def upload_from_string(self, *_args, **_kwargs):
            raise failure

    class Bucket:
        def blob(self, _path):
            return Blob()

    class Client:
        def bucket(self, _name):
            return Bucket()

    monkeypatch.setattr(gcs_utils, "_storage_client", lambda: Client())
    with pytest.raises(ConnectionError) as caught:
        gcs_utils.upload_text_to_gcs("b", "p/rows.csv", "a,b\n", "text/csv")
    assert caught.value is failure


def test_upload_text_returns_the_url(monkeypatch):
    sent = {}

    class Blob:
        def upload_from_string(self, text, content_type=None):
            sent["text"], sent["content_type"] = text, content_type

    class Bucket:
        def blob(self, path):
            sent["path"] = path
            return Blob()

    class Client:
        def bucket(self, name):
            sent["bucket"] = name
            return Bucket()

    monkeypatch.setattr(gcs_utils, "_storage_client", lambda: Client())
    assert gcs_utils.upload_text_to_gcs("b", "p/rows.csv", "a,b\n", "text/csv") == "gs://b/p/rows.csv"
    assert sent == {"bucket": "b", "path": "p/rows.csv", "text": "a,b\n", "content_type": "text/csv"}
