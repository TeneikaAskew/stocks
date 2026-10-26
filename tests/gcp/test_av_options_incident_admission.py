"""Offline regressions for real collector admission and write acknowledgements.

Each case catches a provider call outside a proven session, quota consumed
without persistence, or a fetched row incorrectly reported as acknowledged.
"""
from datetime import datetime, timezone
import builtins
import logging

import pandas as pd
import pytest

from gcp.fetchers import fetch_av_realtime_options as mod
from gcp.fetchers import evaluate_ew_strikes as calendar


@pytest.fixture(autouse=True)
def boundaries(monkeypatch):
    import socket
    import subprocess
    import requests
    from gcp import database

    def forbidden(*args, **kwargs):
        raise AssertionError("unmocked external boundary")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(database, "get_engine", forbidden)
    monkeypatch.setattr(mod.requests, "get", forbidden)
    monkeypatch.setattr(mod, "upsert_dataframe", forbidden)
    monkeypatch.setattr(mod.time, "sleep", lambda _: None)
    monkeypatch.setenv("AV_API_KEY", "FAKE-key")
    monkeypatch.setattr(mod.sys, "argv", ["fetch", "--tickers", "SPY"])


def clock(monkeypatch, value):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return value
    monkeypatch.setattr(mod, "datetime", FrozenDatetime)


def run_main():
    try:
        result = mod.main()
    except SystemExit as error:
        return error.code
    return 0 if result is None else result


def source(monkeypatch, *, two=False):
    calls, writes = [], []
    class Response:
        status_code = 200
        headers = {}
        def raise_for_status(self):
            pass
        def json(self):
            rows = [{"contractID": "SPY1", "type": "call", "expiration": "2026-12-18", "strike": "500"}]
            if two:
                rows.append({"contractID": "SPY2", "type": "put", "expiration": "2026-12-18", "strike": "501"})
            return {"endpoint": "Realtime Options", "message": "success", "data": rows}
        @property
        def raw(self):
            import io
            import json as json_module
            from urllib3.response import HTTPResponse
            if not hasattr(self, '_raw'):
                self._raw = HTTPResponse(body=io.BytesIO(json_module.dumps(self.json()).encode()), preload_content=False)
            return self._raw
        def close(self):
            if hasattr(self, '_raw'):
                self._raw.close()
    def get(*args, **kwargs):
        calls.append(kwargs["params"]["symbol"])
        return Response()
    def write(df, table, conflict_cols):
        writes.append((len(df), table, list(conflict_cols)))
        return len(df)
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr(mod, "upsert_dataframe", write)
    return calls, writes


# Literal UTC boundaries independently checked against NYSE normal/half-day
# sessions, both DST offsets, holiday and weekend dates.
@pytest.mark.parametrize("instant,due", [
    *[(f"2026-10-20T13:{minute:02}:00+00:00", False) for minute in range(0, 30, 5)],
    ("2026-10-20T13:29:59.999999+00:00", False),
    ("2026-10-20T13:30:00+00:00", True),
    ("2026-10-20T19:59:59.999999+00:00", True),
    ("2026-10-20T20:00:00+00:00", False),
    ("2026-10-20T21:00:00+00:00", False),
    ("2026-11-27T17:59:59.999999+00:00", True),
    ("2026-11-27T18:00:00+00:00", False),
    ("2026-11-27T19:00:00+00:00", False),
    ("2026-07-03T15:00:00+00:00", False),
    ("2026-10-24T15:00:00+00:00", False),
    ("2026-03-06T14:29:59+00:00", False),
    ("2026-03-06T14:30:00+00:00", True),
    ("2026-03-09T13:29:59+00:00", False),
    ("2026-03-09T13:30:00+00:00", True),
    ("2026-11-02T14:29:59+00:00", False),
    ("2026-11-02T14:30:00+00:00", True),
])
def test_actual_main_uses_real_nyse_session_before_external_work(monkeypatch, caplog, instant, due):
    clock(monkeypatch, datetime.fromisoformat(instant))
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    calls, writes = source(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert run_main() == 0
    assert calls == (["SPY"] if due else [])
    assert len(writes) == int(due)
    if not due:
        assert "not_due" in caplog.text


def test_closed_slot_skips_even_without_sql_or_api_key(monkeypatch, caplog):
    clock(monkeypatch, datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc))
    monkeypatch.delenv("AV_API_KEY")
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: (_ for _ in ()).throw(AssertionError("SQL preflight before admission")))
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert run_main() == 0
    assert "not_due" in caplog.text


@pytest.mark.parametrize("fault", ["import", "lookup", "not_frame", "columns", "empty_bad_index", "duplicate", "wrong_date", "naive", "nat", "reversed", "cross_date"])
def test_calendar_failure_is_safe_nonzero_without_external_work(monkeypatch, caplog, fault):
    clock(monkeypatch, datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc))
    schedule = calendar.nyse_sessions(datetime(2026, 10, 20).date(), datetime(2026, 10, 20).date())
    if fault == "import":
        original = builtins.__import__
        def fail_import(name, *args, **kwargs):
            if name == "gcp.fetchers.evaluate_ew_strikes":
                raise ImportError("FAKE-SECRET")
            return original(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", fail_import)
    else:
        if fault == "not_frame":
            schedule = None
        elif fault == "columns":
            schedule = schedule.drop(columns="market_close")
        elif fault == "empty_bad_index":
            schedule = pd.DataFrame(columns=["market_open", "market_close"])
        elif fault == "duplicate":
            schedule = pd.concat([schedule, schedule])
        elif fault == "wrong_date":
            schedule.index = pd.DatetimeIndex(["2026-10-19"])
        elif fault == "naive":
            schedule["market_open"] = schedule.market_open.dt.tz_localize(None)
        elif fault == "nat":
            schedule.loc[:, "market_open"] = pd.NaT
        elif fault == "reversed":
            schedule["market_close"] = schedule.market_open
        elif fault == "cross_date":
            schedule["market_close"] = schedule.market_close + pd.Timedelta(days=1)
        def lookup(*args):
            if fault == "lookup":
                raise RuntimeError("FAKE-SECRET")
            return schedule
        monkeypatch.setattr(calendar, "nyse_sessions", lookup)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert run_main() == 1
    assert "NYSE calendar unavailable" in caplog.text
    assert "FAKE-SECRET" not in caplog.text
    assert "not_due" not in caplog.text


@pytest.mark.parametrize("value", [datetime(2026, 10, 20, 15), pd.NaT, None, "2026-10-20T15:00:00+00:00"])
def test_invalid_clock_fails_closed(monkeypatch, caplog, value):
    clock(monkeypatch, value)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert run_main() == 1
    assert "NYSE calendar unavailable" in caplog.text


def test_calendar_looks_up_eastern_date_at_utc_day_boundary(monkeypatch, caplog):
    clock(monkeypatch, datetime(2026, 10, 21, 0, 30, tzinfo=timezone.utc))
    actual = calendar.nyse_sessions
    seen = []
    def lookup(start, end):
        seen.append((start.isoformat(), end.isoformat()))
        return actual(start, end)
    monkeypatch.setattr(calendar, "nyse_sessions", lookup)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert run_main() == 0
    assert seen == [("2026-10-20", "2026-10-20")]
    assert "not_due" in caplog.text


@pytest.mark.parametrize("entry", ["main", "direct"])
def test_missing_persistence_refuses_before_provider_quota(monkeypatch, caplog, entry):
    now = datetime(2026, 10, 20, 15, tzinfo=timezone.utc)
    clock(monkeypatch, now)
    # Real pure config check, with env-i plus explicit removal of both backends.
    for name in ("DB_HOST", "CLOUD_SQL_CONNECTION_NAME", "DB_USER", "DB_PASS", "DB_NAME"):
        monkeypatch.delenv(name, raising=False)
    calls, writes = source(monkeypatch)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    if entry == "main":
        assert run_main() == 1
        assert "persistence unavailable" in caplog.text
    else:
        with pytest.raises(mod.RealtimeOptionsUnavailable, match="persistence unavailable"):
            mod.process_ticker("SPY", "FAKE-key", now)
    assert calls == [] and writes == []


def test_empty_scope_is_not_healthy_zero(monkeypatch):
    clock(monkeypatch, datetime(2026, 10, 20, 15, tzinfo=timezone.utc))
    monkeypatch.setattr(mod.sys, "argv", ["fetch", "--tickers", " "])
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    assert run_main() == 1


class UntrustedCount:
    def __str__(self):
        raise AssertionError("untrusted acknowledgement stringified")
    __repr__ = __str__


@pytest.mark.parametrize("count", [0, -1, 1, 3, True, False, None, "2", 2.0, float("nan"), UntrustedCount()], ids=["zero", "negative", "partial", "excess", "true", "false", "none", "string", "float", "nan", "untrusted"])
def test_invalid_or_incomplete_write_ack_is_unavailable(monkeypatch, caplog, count):
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    source(monkeypatch, two=True)
    monkeypatch.setattr(mod, "upsert_dataframe", lambda *args: count)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    with pytest.raises(mod.RealtimeOptionsUnavailable, match="write acknowledgement unavailable"):
        mod.process_ticker("SPY", "FAKE-key", datetime(2026, 10, 20, 15, tzinfo=timezone.utc))
    assert "✓ upserted" not in caplog.text


def test_main_counts_acknowledged_sibling_and_preserves_partial_write_uncertainty(monkeypatch, caplog):
    clock(monkeypatch, datetime(2026, 10, 20, 15, tzinfo=timezone.utc))
    monkeypatch.setattr(mod.sys, "argv", ["fetch", "--tickers", "SPY IWM QQQ"])
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    calls, _ = source(monkeypatch, two=True)
    writes = []
    error = RuntimeError("FAKE-SECRET partial chunk")
    def write(df, *args):
        ticker = df.ticker.iloc[0]
        writes.append(ticker)
        if ticker == "IWM":
            raise error
        return len(df)
    monkeypatch.setattr(mod, "upsert_dataframe", write)
    caplog.set_level(logging.INFO, logger=mod.__name__)
    assert run_main() == 1
    assert calls == writes == ["SPY", "IWM", "QQQ"]
    assert "4 acknowledged contracts written" in caplog.text
    assert "uncertain" in caplog.text
    assert "FAKE-SECRET" not in caplog.text


def test_direct_write_exception_preserves_original_exception(monkeypatch):
    monkeypatch.setattr(mod, "is_cloud_sql_configured", lambda: True)
    source(monkeypatch)
    error = RuntimeError("partial chunk")
    def write(*args):
        raise error
    monkeypatch.setattr(mod, "upsert_dataframe", write)
    with pytest.raises(RuntimeError) as caught:
        mod.process_ticker("SPY", "FAKE-key", datetime(2026, 10, 20, 15, tzinfo=timezone.utc))
    assert caught.value is error


def _transport_fixture_response(ticker, *, empty=False):
    import io
    import json as json_module
    from urllib3.response import HTTPResponse
    payload = {'endpoint': 'Realtime Options', 'message': 'success', 'data': [] if empty else [{
        'contractID': ticker + '-FIXTURE', 'type': 'call', 'expiration': '2026-12-18', 'strike': '500',
    }]}
    class Response:
        status_code = 200
        headers = {}
        raw = HTTPResponse(body=io.BytesIO(json_module.dumps(payload).encode()), preload_content=False)
        def raise_for_status(self):
            pass
        def json(self):
            return payload
        def close(self):
            self.raw.close()
    return Response()


def test_default_cli_transport_stops_late_source_after_sibling_ack(monkeypatch):
    from gcp.fetchers import _av_realtime_transport as transport
    from types import SimpleNamespace
    clock(monkeypatch, datetime(2026, 10, 22, 19, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(mod.sys, 'argv', ['collector', '--tickers', 'SPY QQQ IWM'])
    monkeypatch.setattr(mod, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(mod, '_av_cfg', SimpleNamespace(delay_between_calls=0))
    now = [100.0]
    monkeypatch.setattr(transport, '_source_clock', lambda: now[0])
    calls, writes = [], []
    def get(*args, **kwargs):
        calls.append((kwargs['params']['symbol'], kwargs['timeout']))
        return _transport_fixture_response(kwargs['params']['symbol'])
    def write(df, table, keys):
        writes.append(df['ticker'].iat[0])
        now[0] += 20  # Prior SQL may finish; it must not grant more source time.
        return len(df)
    monkeypatch.setattr(mod.requests, 'get', get)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    assert run_main() == 1
    assert [t for t, _ in calls] == ['SPY']
    assert 0 < calls[0][1] <= 15
    assert writes == ['SPY']


def test_default_cli_transport_retries_share_one_deadline(monkeypatch):
    from gcp.fetchers import _av_realtime_transport as transport
    from types import SimpleNamespace
    clock(monkeypatch, datetime(2026, 10, 22, 19, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(mod.sys, 'argv', ['collector', '--tickers', 'SPY QQQ IWM'])
    monkeypatch.setattr(mod, 'is_cloud_sql_configured', lambda: True)
    monkeypatch.setattr(mod, '_av_cfg', SimpleNamespace(delay_between_calls=0))
    now = [100.0]
    monkeypatch.setattr(transport, '_source_clock', lambda: now[0])
    calls, writes = [], []
    def get(*args, **kwargs):
        ticker = kwargs['params']['symbol']
        calls.append((ticker, kwargs['timeout']))
        now[0] += 4 if ticker == 'SPY' else 2
        return _transport_fixture_response(ticker, empty=ticker == 'SPY')
    def write(df, table, keys):
        writes.append(df['ticker'].iat[0])
        now[0] += 5
        return len(df)
    monkeypatch.setattr(mod.requests, 'get', get)
    monkeypatch.setattr(mod, 'upsert_dataframe', write)
    assert run_main() == 1
    assert [t for t, _ in calls] == ['SPY', 'SPY', 'SPY', 'QQQ']
    assert all(0 < timeout <= 15 for _, timeout in calls)
    assert all(a > b for (_, a), (_, b) in zip(calls, calls[1:]))
    assert writes == ['QQQ']


def test_direct_worker_fetch_keeps_legacy_path_without_cli_signal(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from gcp.fetchers import _av_realtime_transport as transport
    monkeypatch.setattr(transport, 'deadline', lambda: (_ for _ in ()).throw(AssertionError('CLI budget used by API worker')))
    calls = []
    def get(*args, **kwargs):
        calls.append(kwargs)
        return _transport_fixture_response('SPY')
    monkeypatch.setattr(mod.requests, 'get', get)
    with ThreadPoolExecutor(max_workers=1) as pool:
        frame = pool.submit(mod.fetch_av_realtime_options, 'SPY', 'FAKE-key', datetime(2026, 10, 22, 19, 30, tzinfo=timezone.utc)).result(timeout=2)
    assert len(frame) == 1
    assert len(calls) == 1
    assert calls[0]['timeout'] == 60
    assert 'stream' not in calls[0]
