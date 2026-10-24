"""Offline schema-only diagnostics for #1562; provider contents never logged."""
import json
import logging
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from gcp.fetchers import fetch_av_realtime_options as mod

NOW = datetime(2026, 10, 22, 19, 30, tzinfo=timezone.utc)
SECRET = "FAKE-secret-bearing-value-apikey=malicious"

@pytest.fixture(autouse=True)
def boundaries(monkeypatch):
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)


def attempt(caplog):
    events = [json.loads(r.getMessage()) for r in caplog.records
              if r.getMessage().startswith('{"event":"av_realtime_options_attempt"')]
    assert len(events) == 1
    assert len(json.dumps(events[0]).encode()) <= 2048
    return events[0]

@pytest.mark.parametrize("payload,endpoint,message,records,keys", [
    ({}, "missing", "missing", "missing", []),
    ({"Note": SECRET}, "missing", "missing", "missing", ["Note"]),
    ({"endpoint": None, "message": None, "data": None}, "null", "null", "null", ["data", "endpoint", "message"]),
    ({"endpoint": SECRET, "message": SECRET, "data": SECRET}, "other", "other", "string", ["data", "endpoint", "message"]),
    ({"Error Message": "Invalid API call. Please retry or visit the documentation at https://www.alphavantage.co/documentation/#realtime-options"}, "missing", "missing", "missing", ["Error Message"]),
    ({"Information": SECRET}, "missing", "missing", "missing", ["Information"]),
    ({"endpoint": "Realtime Options", "message": "failure", "data": []}, "expected", "other", "array_empty", ["data", "endpoint", "message"]),
])
def test_untrusted_schema_is_projected_without_retry_or_write(monkeypatch, caplog, payload, endpoint, message, records, keys):
    request = Mock(return_value=Mock(status_code=200, headers={}, json=Mock(return_value=payload)))
    write = Mock(side_effect=AssertionError("must not write"))
    monkeypatch.setattr(mod.requests, "get", request)
    monkeypatch.setattr(mod, "upsert_dataframe", write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsUnavailable):
        mod.process_ticker("SPY", SECRET, NOW)
    assert request.call_count == 1
    write.assert_not_called()
    schema = attempt(caplog)["response_schema"]
    assert schema == {"body": "object", "present": keys,
                      "endpoint": endpoint, "message": message, "records": records}
    assert SECRET not in caplog.text

@pytest.mark.parametrize("value,shape", [(None,"null"), ([],"array_empty"), ([{}],"array_nonempty"), ({},"object"), (SECRET,"string"), (42,"number"), (True,"boolean")])
def test_records_shape_only(value, shape):
    result = mod._response_schema({"data": value, SECRET: SECRET})
    assert result["records"] == shape
    assert result["present"] == ["data"]
    assert SECRET not in json.dumps(result)

@pytest.mark.parametrize("payload", [None, [], [SECRET], SECRET, 12, True])
def test_nonobject_response_schema(payload):
    assert mod._response_schema(payload) == {"body": "nonobject"}


def test_failed_decode_retains_no_body(monkeypatch, caplog):
    response = Mock(status_code=200, headers={}, json=Mock(side_effect=ValueError(SECRET)))
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsUnavailable):
        mod.fetch_av_realtime_options("QQQ", SECRET, NOW)
    event = attempt(caplog)
    assert event["response_schema"] == {"body": "unavailable"}
    assert event["error_class"] == "json_error"
    assert SECRET not in caplog.text


def test_huge_unknown_body_keys_and_values_are_not_reflected():
    payload = {SECRET * 1000: SECRET * 1000, "endpoint": SECRET * 1000,
               "message": SECRET * 1000, "data": [SECRET * 1000], "Error Message": SECRET * 1000}
    result = mod._response_schema(payload)
    assert result == {"body": "object", "present": ["data", "endpoint", "message", "Error Message"],
                      "endpoint": "other", "message": "other", "records": "array_nonempty"}
    assert len(json.dumps(result).encode()) < 200
    assert SECRET not in json.dumps(result)
