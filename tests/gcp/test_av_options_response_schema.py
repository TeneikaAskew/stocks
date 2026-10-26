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


@pytest.mark.parametrize('fields,classification', [
    ({}, 'data_missing'),
    ({'data': None}, 'data_null'),
    ({'data': False}, 'data_type'),
    ({'data': 0}, 'data_type'),
    ({'data': ''}, 'data_type'),
    ({'data': {}}, 'data_type'),
    ({'data': {'unsafe': SECRET}}, 'data_type'),
    ({'data': SECRET}, 'data_type'),
])
def test_strict_success_requires_literal_data_array(monkeypatch, caplog, fields, classification):
    payload = {'endpoint': 'Realtime Options', 'message': 'success', **fields}
    request = Mock(return_value=Mock(status_code=200, headers={}, json=Mock(return_value=payload)))
    write = Mock(side_effect=AssertionError('must not write'))
    monkeypatch.setattr(mod.requests, 'get', request)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsUnavailable) as error:
        mod.process_ticker('QQQ', SECRET, NOW)
    assert not isinstance(error.value, mod.RealtimeOptionsEmpty)
    assert request.call_count == 1
    write.assert_not_called()
    assert attempt(caplog)['error_class'] == classification
    assert SECRET not in caplog.text


def test_strict_literal_empty_keeps_existing_three_attempt_limit(monkeypatch, caplog):
    payload = {'endpoint': 'Realtime Options', 'message': 'success', 'data': []}
    request = Mock(return_value=Mock(status_code=200, headers={}, json=Mock(return_value=payload)))
    write = Mock(side_effect=AssertionError('must not write'))
    monkeypatch.setattr(mod.requests, 'get', request)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsEmpty):
        mod.process_ticker('QQQ', SECRET, NOW)
    assert mod.EMPTY_RETRY_ATTEMPTS == 2
    assert request.call_count == 3
    write.assert_not_called()
    events = [json.loads(r.getMessage()) for r in caplog.records
              if r.getMessage().startswith('{"event":"av_realtime_options_attempt"')]
    assert [event['attempt'] for event in events] == [1, 2, 3]
    assert all(event['error_class'] == 'empty' for event in events)
    assert SECRET not in caplog.text


def test_strict_main_keeps_successful_siblings_without_retrying_unknown(monkeypatch, caplog):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(mod, 'datetime', FrozenDatetime)
    monkeypatch.setattr(mod, '_regular_session_due', lambda _: True)
    monkeypatch.setenv('AV_API_KEY', SECRET)
    monkeypatch.setattr(mod.sys, 'argv', ['collector', '--tickers', 'SPY QQQ IWM'])
    calls, writes = [], []
    def get(*args, **kwargs):
        ticker = kwargs['params']['symbol']
        calls.append(ticker)
        fields = {} if ticker == 'QQQ' else {'data': [{
            'contractID': ticker + '-FAKE', 'type': 'call',
            'expiration': '2026-12-18', 'strike': '500',
        }]}
        payload = {'endpoint': 'Realtime Options', 'message': 'success', **fields}
        import io
        from urllib3.response import HTTPResponse
        raw = HTTPResponse(body=io.BytesIO(json.dumps(payload).encode()), preload_content=False)
        return Mock(status_code=200, headers={}, json=Mock(return_value=payload), raw=raw)
    def write(df, table, keys):
        writes.append((df['ticker'].iat[0], len(df), table))
        return len(df)
    monkeypatch.setattr(mod.requests, 'get', get)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(SystemExit) as error:
        mod.main()
    assert error.value.code == 1
    assert calls == ['SPY', 'QQQ', 'IWM']
    assert writes == [('SPY', 1, 'etf_options_snapshots'), ('IWM', 1, 'etf_options_snapshots')]
    assert SECRET not in caplog.text


@pytest.mark.parametrize('kind', ['read_timeout', 'protocol'])
def test_source_body_network_failures_keep_transport_category(monkeypatch, caplog, kind):
    from gcp.fetchers import _av_realtime_transport as transport
    from urllib3.exceptions import ProtocolError, ReadTimeoutError
    failure = ReadTimeoutError(None, 'https://example.invalid/?apikey=' + SECRET, SECRET) if kind == 'read_timeout' else ProtocolError(SECRET)
    class Raw:
        headers = {}
        def read(self, *args, **kwargs):
            raise failure
    response = Mock(status_code=200, headers={}, raw=Raw())
    request = Mock(return_value=response)
    write = Mock(side_effect=AssertionError('must not write'))
    monkeypatch.setattr(mod.requests, 'get', request)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsUnavailable):
        mod.process_ticker('QQQ', SECRET, NOW, _source_deadline=transport.deadline())
    assert request.call_count == 1
    write.assert_not_called()
    event = attempt(caplog)
    assert event['http_status'] == 200
    assert event['error_class'] == 'transport_error'
    assert event['response_schema'] == {'body': 'unavailable'}
    assert SECRET not in caplog.text


@pytest.mark.parametrize('admitted,kind,classification', [
    (False, 'timeout', 'transport_error'),
    (True, 'timeout', 'transport_error'),
    (True, 'http', 'http_error'),
])
def test_source_requests_failures_before_and_after_response(monkeypatch, caplog, admitted, kind, classification):
    from gcp.fetchers import _av_realtime_transport as transport
    error_type = mod.requests.HTTPError if kind == 'http' else mod.requests.Timeout
    response = Mock(status_code=200, headers={})
    def decode(params, deadline, observed):
        if admitted:
            observed(response)
        raise error_type(SECRET)
    source = Mock(side_effect=decode)
    write = Mock(side_effect=AssertionError('must not write'))
    monkeypatch.setattr(transport, 'decoded_json', source)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(error_type):
        mod.process_ticker('QQQ', SECRET, NOW, _source_deadline=transport.deadline())
    assert source.call_count == 1
    write.assert_not_called()
    event = attempt(caplog)
    assert event['error_class'] == classification
    assert event['http_status'] == (200 if admitted else None)
    assert SECRET not in caplog.text
