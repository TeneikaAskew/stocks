"""Regression tests for SEC EDGAR throttling in fetch_sec_filings.

Written against a real production failure: execution fetch-sec-filings-smmmr
(2026-08-31 11:00 UTC) died with

    WARNING  SEC GET failed for .../company_tickers.json: 429 Too Many Requests
    ERROR    Failed to load SEC ticker→CIK map; cannot proceed

The 429 landed on the run's FIRST request, before the per-ticker loop began,
so it was not caused by our own pacing. EDGAR throttles per egress IP and
Cloud Run shares that IP across tenants, so a 429 can arrive through no fault
of ours. Pre-fix, _http_get had no 429 handling at all: one transient throttle
killed the whole run.

test_429_then_success_is_retried is the regression test — it FAILS against the
pre-fix implementation and passes after.

Nothing here touches the network, GCS, or Cloud SQL.
"""

from __future__ import annotations

import sys
import types
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def _resp(status: int, payload=None, retry_after: str | None = None):
    """A requests.Response double with just the surface _http_get uses."""
    import requests

    r = MagicMock()
    r.status_code = status
    r.headers = {} if retry_after is None else {"Retry-After": retry_after}
    r.json.return_value = payload if payload is not None else {}
    if status >= 400:
        r.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status} Client Error", response=r
        )
    else:
        r.raise_for_status.return_value = None
    return r


OK_BODY = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}


@pytest.fixture(autouse=True)
def _isolate_retry_budget():
    """The backoff budget is module state; without this it leaks between tests.

    A test that burns budget would otherwise silently disarm retries in
    whichever test happened to run next — an order-dependent false pass.
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    fsf._reset_retry_budget()
    yield
    fsf._reset_retry_budget()


# ── _http_get retry behaviour ────────────────────────────────────────


def test_429_then_success_is_retried():
    """REGRESSION: a transient 429 must not kill the request.

    This is the production failure. Pre-fix _http_get made one attempt and
    returned None, so the job aborted. Post-fix it backs off and succeeds.
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    responses = [_resp(429), _resp(200, OK_BODY)]
    with patch.object(fsf.requests, "get", side_effect=responses) as g, \
         patch.object(fsf.time_module, "sleep") as slept:
        out = fsf._http_get("https://sec.example/x", "ua")

    assert out == OK_BODY, "a 429 followed by 200 must return the 200 body"
    assert g.call_count == 2
    assert slept.call_count == 1, "must wait before retrying a 429"


def test_persistent_429_gives_up_and_returns_none():
    """Exhausted retries return None — never a fabricated result (Rule 3.7)."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get", return_value=_resp(429)) as g, \
         patch.object(fsf.time_module, "sleep"):
        out = fsf._http_get("https://sec.example/x", "ua")

    assert out is None
    assert g.call_count == fsf.SEC_MAX_ATTEMPTS


def test_retry_after_header_is_honoured():
    """SEC's Retry-After wins over our exponential backoff."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get",
                      side_effect=[_resp(429, retry_after="7"), _resp(200, OK_BODY)]), \
         patch.object(fsf.time_module, "sleep") as slept:
        fsf._http_get("https://sec.example/x", "ua")

    assert slept.call_args[0][0] == pytest.approx(7.0)


def test_retry_after_is_capped():
    """A hostile Retry-After must not park the job past its task-timeout."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get",
                      side_effect=[_resp(429, retry_after="99999"), _resp(200, OK_BODY)]), \
         patch.object(fsf.time_module, "sleep") as slept:
        fsf._http_get("https://sec.example/x", "ua")

    assert slept.call_args[0][0] == fsf.SEC_BACKOFF_MAX_S


def test_http_date_retry_after_falls_back_to_backoff():
    """Retry-After may be an HTTP-date; unparseable values use backoff, not crash."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get",
                      side_effect=[_resp(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"),
                                   _resp(200, OK_BODY)]), \
         patch.object(fsf.time_module, "sleep") as slept:
        out = fsf._http_get("https://sec.example/x", "ua")

    assert out == OK_BODY
    assert slept.call_args[0][0] == pytest.approx(fsf.SEC_BACKOFF_BASE_S)


def test_404_is_not_retried():
    """Permanent errors must not burn the rate budget on pointless retries."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get", return_value=_resp(404)) as g, \
         patch.object(fsf.time_module, "sleep") as slept:
        out = fsf._http_get("https://sec.example/x", "ua")

    assert out is None
    assert g.call_count == 1, "a 404 is permanent — one attempt only"
    assert slept.call_count == 0


def test_connection_error_is_retried():
    """Timeouts and connection resets are transient."""
    import requests
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get",
                      side_effect=[requests.exceptions.ConnectionError("reset"),
                                   _resp(200, OK_BODY)]) as g, \
         patch.object(fsf.time_module, "sleep"):
        out = fsf._http_get("https://sec.example/x", "ua")

    assert out == OK_BODY
    assert g.call_count == 2


def test_5xx_is_retried():
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get",
                      side_effect=[_resp(503), _resp(200, OK_BODY)]) as g, \
         patch.object(fsf.time_module, "sleep"):
        assert fsf._http_get("https://sec.example/x", "ua") == OK_BODY
    assert g.call_count == 2


# ── CIK-map cache fallback ───────────────────────────────────────────


def _cache(age_hours: float, mapping=None):
    ts = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return ({"AAPL": "0000320193"} if mapping is None else mapping), ts


def test_fresh_cache_is_used_when_sec_is_down(caplog):
    """A throttled run proceeds on cache — and says so at ERROR level."""
    from gcp.fetchers import fetch_sec_filings as fsf

    mapping, _ = _cache(2.0)
    with patch.object(fsf, "_http_get", return_value=None), \
         patch.object(fsf, "_read_cik_cache", return_value=(mapping, 2.0)):
        with caplog.at_level("ERROR"):
            out = fsf.load_ticker_to_cik("ua")

    assert out == mapping
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "CACHED MAP" in joined, "degradation must be loud, not silent (Rule 3.7)"
    assert "2.0h old" in joined, "the log must state the measured staleness"


def test_stale_cache_is_refused():
    """Past the age limit, failing beats guessing."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf, "_http_get", return_value=None), \
         patch.object(fsf, "_read_cik_cache",
                      return_value=({"AAPL": "0000320193"},
                                    fsf.CIK_CACHE_MAX_AGE_H + 1)):
        assert fsf.load_ticker_to_cik("ua") == {}


def test_no_cache_returns_empty_so_caller_aborts():
    """With no cache the job must still fail loudly, exactly as before."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf, "_http_get", return_value=None), \
         patch.object(fsf, "_read_cik_cache", return_value=({}, None)):
        assert fsf.load_ticker_to_cik("ua") == {}


def test_successful_fetch_writes_the_cache():
    """A good run refreshes the fallback for the next throttled one."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf, "_http_get", return_value=OK_BODY), \
         patch.object(fsf, "_write_cik_cache") as w:
        out = fsf.load_ticker_to_cik("ua")

    assert out == {"AAPL": "0000320193"}
    w.assert_called_once()
    assert w.call_args[0][0] == {"AAPL": "0000320193"}


def test_cache_write_failure_does_not_fail_the_run(monkeypatch, caplog):
    """The live fetch already succeeded; a cache-write error must not abort.

    This drives the REAL _write_cik_cache and makes GCS blow up underneath it,
    so the try/except inside that function is what is under test. Patching
    _write_cik_cache itself with a side_effect would jump over that guard and
    prove nothing.
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")

    fake_storage = _fake_gcs(monkeypatch, RuntimeError("gcs down"))

    with patch.object(fsf, "_http_get", return_value=OK_BODY):
        with caplog.at_level("WARNING"):
            out = fsf.load_ticker_to_cik("ua")

    # The run survives and still returns the freshly fetched map.
    assert out == {"AAPL": "0000320193"}
    assert fake_storage.Client.called, "the real _write_cik_cache never ran"
    assert any("Could not write CIK cache" in r.getMessage()
               for r in caplog.records)


def test_cache_read_failure_is_not_mistaken_for_a_fresh_map(monkeypatch, caplog):
    """A broken GCS read yields no fallback, so the caller aborts loudly."""
    from gcp.fetchers import fetch_sec_filings as fsf

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")

    _fake_gcs(monkeypatch, RuntimeError("gcs down"))

    with patch.object(fsf, "_http_get", return_value=None):
        with caplog.at_level("WARNING"):
            out = fsf.load_ticker_to_cik("ua")

    assert out == {}
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "CIK cache read FAILED" in joined
    assert "does not fix itself" in joined
    assert "no usable cache exists" in joined


# ── run-wide backoff budget ──────────────────────────────────────────


def test_budget_exhaustion_stops_retrying(caplog):
    """Once the run-wide budget is spent, a 429 fails fast instead of sleeping.

    Without this, sustained throttling multiplies per-request backoff across
    ~500 tickers and the Cloud Run task is killed mid-loop, losing every row
    accumulated so far (CLAUDE.md Rule 0).
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    fsf._claim_retry_budget(fsf.SEC_RETRY_BUDGET_S)  # spend it all

    with patch.object(fsf.requests, "get", return_value=_resp(429)) as g, \
         patch.object(fsf.time_module, "sleep") as slept:
        with caplog.at_level("ERROR"):
            out = fsf._http_get("https://sec.example/x", "ua")

    assert out is None
    assert slept.call_count == 0, "must not sleep on an exhausted budget"
    assert g.call_count == 1, "must not keep re-requesting either"
    assert any("retry budget is exhausted" in r.getMessage()
               for r in caplog.records)


def test_total_backoff_is_bounded_across_many_calls():
    """The capacity guarantee: total sleep stays under the budget, not per-call.

    Simulates a sustained throttle across a full 500-ticker run and asserts the
    summed backoff fits the budget, so worst-case wall-clock stays inside the
    1800s task-timeout.
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf.requests, "get", return_value=_resp(429, retry_after="30")), \
         patch.object(fsf.time_module, "sleep") as slept:
        for _ in range(500):
            fsf._http_get("https://sec.example/x", "ua")

    total = sum(c[0][0] for c in slept.call_args_list)
    assert total <= fsf.SEC_RETRY_BUDGET_S, (
        f"total backoff {total}s exceeds the {fsf.SEC_RETRY_BUDGET_S}s budget"
    )


def test_budget_resets_per_run():
    """A fresh run gets a fresh budget — otherwise run 2 in a warm process
    would start with retries already disabled."""
    from gcp.fetchers import fetch_sec_filings as fsf

    fsf._claim_retry_budget(fsf.SEC_RETRY_BUDGET_S)
    assert not fsf._claim_retry_budget(1.0)

    fsf._reset_retry_budget()
    assert fsf._claim_retry_budget(1.0)


# ── cache read: "not there yet" vs "path is broken" ──────────────────


class NotFound(Exception):
    """Stands in for google.api_core.exceptions.NotFound (lib absent here).

    The class is really named NotFound: _is_missing_blob falls back to
    type(exc).__name__, and a class-body __name__ = "NotFound" would NOT
    change that (the metaclass descriptor wins over the class __dict__).
    """


def _install_fake_gcs(monkeypatch, client):
    """Install a google.cloud.storage whose Client is `client`.

    Patches BOTH sys.modules and the attribute on the `google.cloud` parent
    package. `from google.cloud import storage` resolves via the parent's
    attribute when the real library is installed (as it is in CI) and via
    sys.modules when it is not (as in the sandbox) — so patching only
    sys.modules passes locally while silently mocking nothing in CI.
    """
    mod = types.ModuleType("google.cloud.storage")
    mod.Client = client
    monkeypatch.setitem(sys.modules, "google.cloud.storage", mod)
    import google.cloud as _gc
    monkeypatch.setattr(_gc, "storage", mod, raising=False)
    return mod


def _fake_gcs(monkeypatch, exc):
    """Install a google.cloud.storage whose Client() raises `exc`."""
    return _install_fake_gcs(monkeypatch, MagicMock(side_effect=exc))


def test_absent_cache_is_not_reported_as_broken(monkeypatch, caplog):
    """A missing blob is the expected first-run state — not an ERROR.

    Conflating it with a broken read sends an operator chasing IAM during an
    incident whose real fix is "wait for one good run".
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    _fake_gcs(monkeypatch, NotFound("no such object"))

    with caplog.at_level("INFO"):
        mapping, age = fsf._read_cik_cache()

    assert (mapping, age) == ({}, None)
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "yet" in joined
    assert not [r for r in caplog.records if r.levelname == "ERROR"], (
        "a missing cache must not be logged as a failure"
    )


def test_broken_cache_read_is_reported_as_broken(monkeypatch, caplog):
    """An operational read failure is permanent and must be loud."""
    from gcp.fetchers import fetch_sec_filings as fsf

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    _fake_gcs(monkeypatch, PermissionError("403 caller lacks storage.objects.get"))

    with caplog.at_level("INFO"):
        mapping, age = fsf._read_cik_cache()

    assert (mapping, age) == ({}, None)
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert errors, "a broken cache read must be an ERROR"
    assert "PermissionError" in errors[0], "name the exception type for triage"


def test_malformed_cache_is_reported_as_broken(monkeypatch, caplog):
    """Readable-but-garbage JSON is a broken fallback, not an absent one."""
    from gcp.fetchers import fetch_sec_filings as fsf

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    blob = MagicMock()
    blob.download_as_text.return_value = '{"mapping": {}, "fetched_at": null}'
    _install_fake_gcs(monkeypatch, MagicMock(return_value=MagicMock(
        **{"bucket.return_value.blob.return_value": blob})))

    with caplog.at_level("INFO"):
        mapping, age = fsf._read_cik_cache()

    assert (mapping, age) == ({}, None)
    assert any("malformed" in r.getMessage()
               for r in caplog.records if r.levelname == "ERROR")


def test_cache_write_failure_is_logged_at_error(monkeypatch, caplog):
    """A failed write silently disarms the fallback — WARNING buries that."""
    from gcp.fetchers import fetch_sec_filings as fsf

    monkeypatch.setenv("GCS_BUCKET", "test-bucket")
    _fake_gcs(monkeypatch, RuntimeError("gcs down"))

    with caplog.at_level("WARNING"):
        fsf._write_cik_cache({"AAPL": "0000320193"})

    assert any(r.levelname == "ERROR" and "Could not write CIK cache" in r.getMessage()
               for r in caplog.records)


# ── outage must not masquerade as an empty day (Codex P1, #947) ──────


def test_failed_submissions_fetch_raises_rather_than_returning_empty():
    """A failed fetch must be distinguishable from "this ticker filed nothing".

    Returning [] for both is what let a total outage look like a quiet day.
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf, "_http_get", return_value=None):
        with pytest.raises(fsf.SECFetchError):
            fsf.fetch_submissions("AAPL", "0000320193", "ua")


def test_genuinely_empty_filings_still_returns_empty_list():
    """A 200 with no `recent` block is a real empty result, not a failure."""
    from gcp.fetchers import fetch_sec_filings as fsf

    with patch.object(fsf, "_http_get", return_value={"filings": {"recent": {}}}):
        assert fsf.fetch_submissions("AAPL", "0000320193", "ua") == []

    with patch.object(fsf, "_http_get", return_value={}):
        assert fsf.fetch_submissions("AAPL", "0000320193", "ua") == []


def test_total_outage_on_cached_map_exits_nonzero(monkeypatch, caplog):
    """REGRESSION (Codex P1): a sustained SEC outage must fail the run.

    With the CIK cache in play the map request no longer aborts the job, so
    every submissions fetch failing would leave all_filings empty and reach
    "No filings fetched" -> exit 0. That reports SUCCESS through a total
    outage and suppresses the Cloud Run failure signal that surfaced this
    incident in the first place.
    """
    from gcp.fetchers import fetch_sec_filings as fsf

    mapping = {"AAPL": "0000320193", "MSFT": "0000789019"}
    monkeypatch.setattr(sys, "argv", ["fetch_sec_filings", "--tickers", "AAPL,MSFT"])

    with patch.object(fsf, "_http_get", return_value=None), \
         patch.object(fsf, "_read_cik_cache", return_value=(mapping, 2.0)), \
         patch.object(fsf.time_module, "sleep"):
        with caplog.at_level("ERROR"):
            with pytest.raises(SystemExit) as exc:
                fsf.main()

    assert exc.value.code == 1, "a total outage must exit nonzero"
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "2" in joined and "fail" in joined.lower()


def test_partial_failure_with_real_filings_still_succeeds():
    """One bad ticker among many must not fail a run that got real data."""
    from gcp.fetchers import fetch_sec_filings as fsf

    good = {"filings": {"recent": {
        "accessionNumber": ["acc-1"], "form": ["8-K"],
        "filingDate": [date.today().isoformat()], "reportDate": [None],
        "items": [""], "primaryDocument": ["d1.htm"],
    }}}

    tickers_payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft"},
    }

    def _side_effect(url, *a, **k):
        if url == fsf.TICKERS_URL:
            return tickers_payload
        return None if "0000789019" in url else good   # MSFT fails, AAPL works

    with patch.object(fsf, "_http_get", side_effect=_side_effect), \
         patch.object(fsf, "_write_cik_cache"), \
         patch.object(fsf.time_module, "sleep"), \
         patch.object(fsf, "is_cloud_sql_configured", return_value=False):
        with patch.object(sys, "argv",
                          ["fetch_sec_filings", "--tickers", "AAPL,MSFT"]):
            fsf.main()  # must not raise SystemExit
