"""Unit tests for gcp.insight_pipeline_job batch-guard helpers.

Covers parse_tickers (CSV + JSON-array), classify_trigger
(scheduled vs manual_batch), and the _run_scheduled cap/override
behaviour. The ticker run path itself is mocked — these tests
specifically protect the gates, not the LLM pipeline.
"""

from __future__ import annotations

import asyncio
import os
import threading
import pytest

from gcp import insight_pipeline_job as job


def _run(coro):
    """Run an async coroutine synchronously in a fresh thread.

    Bypasses Python 3.12's stricter ``_get_running_loop()`` check (issue
    #282): if any prior test in the suite leaks a running-loop reference
    into the pytest main thread (observed under pytest-asyncio 1.x +
    transitive anyio 4.x via httpx), ``asyncio.run`` and same-thread
    ``loop.run_until_complete`` both refuse to start with
    ``RuntimeError: cannot be called from a running event loop`` /
    ``Cannot run the event loop while another loop is running``.

    A fresh thread has its own thread-local asyncio state, so
    ``asyncio.run`` inside the worker is unaffected by whatever the
    main thread inherited from earlier tests.
    """
    box: dict = {}

    def _runner():
        try:
            box["result"] = asyncio.run(coro)
        except BaseException as exc:  # re-raise on the caller thread
            box["error"] = exc

    t = threading.Thread(target=_runner, name="insight-pipeline-job-test")
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["result"]


# ---------------------------------------------------------------------------
# parse_tickers
# ---------------------------------------------------------------------------


def test_parse_tickers_csv_basic():
    assert job.parse_tickers("SPY,IWM,QQQ") == ["SPY", "IWM", "QQQ"]


def test_parse_tickers_csv_strips_and_uppercases():
    assert job.parse_tickers(" spy , iwm , qqq ") == ["SPY", "IWM", "QQQ"]


def test_parse_tickers_csv_dedupes_preserving_order():
    assert job.parse_tickers("SPY,IWM,SPY,QQQ,iwm") == ["SPY", "IWM", "QQQ"]


def test_parse_tickers_drops_empty_segments():
    assert job.parse_tickers("SPY,,IWM, ,QQQ,") == ["SPY", "IWM", "QQQ"]


def test_parse_tickers_empty_string_returns_empty_list():
    assert job.parse_tickers("") == []
    assert job.parse_tickers("   ") == []


def test_parse_tickers_json_array():
    assert job.parse_tickers('["SPY","IWM","QQQ"]') == ["SPY", "IWM", "QQQ"]


def test_parse_tickers_json_array_lowercase_normalised():
    assert job.parse_tickers('["spy","iwm","qqq"]') == ["SPY", "IWM", "QQQ"]


def test_parse_tickers_json_array_dedupes():
    assert job.parse_tickers('["SPY","IWM","SPY"]') == ["SPY", "IWM"]


def test_parse_tickers_malformed_json_falls_back_to_csv():
    # Looks like JSON but isn't valid — fall through to CSV split so
    # we don't lose data on a typo.
    assert job.parse_tickers("[SPY,IWM]") == ["[SPY", "IWM]"]


def test_parse_tickers_json_non_array_returns_empty():
    # A JSON object isn't a ticker list; safer to return [] than to
    # fabricate semantics. _run_scheduled then refuses with exit 1.
    assert job.parse_tickers('{"watchlist":["SPY"]}') == []


# ---------------------------------------------------------------------------
# classify_trigger
# ---------------------------------------------------------------------------


def test_classify_trigger_default_is_scheduled():
    assert job.classify_trigger(["SPY", "IWM", "QQQ"]) == "scheduled"


def test_classify_trigger_default_order_independent():
    assert job.classify_trigger(["IWM", "QQQ", "SPY"]) == "scheduled"


def test_classify_trigger_extra_ticker_is_manual():
    assert job.classify_trigger(["SPY", "IWM", "QQQ", "AVGO"]) == "manual_batch"


def test_classify_trigger_subset_is_manual():
    assert job.classify_trigger(["SPY"]) == "manual_batch"
    assert job.classify_trigger(["AVGO"]) == "manual_batch"


def test_classify_trigger_empty_is_manual():
    # Empty isn't a "default" run; treat as manual to flag in audit.
    assert job.classify_trigger([]) == "manual_batch"


# ---------------------------------------------------------------------------
# _run_scheduled cap + override
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_run_pipeline(monkeypatch):
    """Stub out the actual ticker pipeline so tests stay hermetic.

    Returns a list that records every ticker the scheduler attempted,
    in order, so the test can assert which tickers ran (or didn't).
    """
    calls: list[str] = []

    async def fake_run_one(run_id: str, ticker: str, as_of=None, allow_update: bool = False, run_kind: str = "scheduled", triggered_by=None) -> bool:
        calls.append(ticker)
        return True

    def fake_insert_run(ticker: str, trigger: str) -> str:
        # Return a synthetic id; trigger is captured below via a separate fixture
        return f"run-{ticker}"

    monkeypatch.setattr(job, "_run_one", fake_run_one)
    monkeypatch.setattr(job, "_insert_run", fake_insert_run)
    # These tests assert which tickers RAN in-process, which only has
    # meaning on the sequential path. Pin it explicitly: without this the
    # suite's result depends on whether google-cloud-tasks happens to be
    # importable in the environment (absent -> enqueue fails -> in-process
    # fallback -> green for the wrong reason).
    monkeypatch.setenv("INSIGHT_FANOUT", "0")
    return calls


@pytest.fixture
def captured_triggers(monkeypatch):
    """Capture the trigger value passed to every _insert_run call."""
    triggers: list[tuple[str, str]] = []

    def fake_insert_run(ticker: str, trigger: str) -> str:
        triggers.append((ticker, trigger))
        return f"run-{ticker}"

    monkeypatch.setattr(job, "_insert_run", fake_insert_run)

    async def fake_run_one(run_id: str, ticker: str, as_of=None, allow_update: bool = False, run_kind: str = "scheduled", triggered_by=None) -> bool:
        return True

    monkeypatch.setattr(job, "_run_one", fake_run_one)
    monkeypatch.setenv("INSIGHT_FANOUT", "0")  # see stub_run_pipeline
    return triggers


def _set_env(monkeypatch, **kwargs):
    """Set/unset env vars for one test, leaving others untouched."""
    for key, value in kwargs.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_run_scheduled_explicit_env_overrides_watchlist(stub_run_pipeline, monkeypatch):
    """INSIGHT_TICKERS env wins over the watchlist for ad-hoc runs."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", lambda **kw: ["FROM_DB", "ALSO_DB"])
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["SPY", "IWM", "QQQ"]


def test_run_scheduled_falls_back_to_watchlist_when_env_unset(stub_run_pipeline, monkeypatch):
    """Empty INSIGHT_TICKERS → query the Cloud SQL watchlists table."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", lambda **kw: ["AVGO", "MSFT", "IWM"])
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["AVGO", "MSFT", "IWM"]


def test_run_scheduled_falls_back_to_default_when_watchlist_empty(stub_run_pipeline, monkeypatch):
    """Both env and watchlist empty → DEFAULT_TICKERS so cron never no-ops."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", lambda **kw: [])
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == list(job.DEFAULT_TICKERS)


def test_run_scheduled_falls_back_to_default_when_watchlist_raises(stub_run_pipeline, monkeypatch):
    """Cloud SQL outage shouldn't block the daily cron — we fall to defaults."""
    import gcp.fetchers._watchlist as wl_mod

    def explode(**kw):
        raise RuntimeError("Cloud SQL down")
    monkeypatch.setattr(wl_mod, "load_watchlist", explode)
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == list(job.DEFAULT_TICKERS)


def test_run_scheduled_explicit_env_blank_string_treated_as_unset(stub_run_pipeline, monkeypatch):
    """An empty/whitespace INSIGHT_TICKERS shouldn't bypass the watchlist."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", lambda **kw: ["AVGO"])
    _set_env(monkeypatch, INSIGHT_TICKERS="   ", INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["AVGO"]


def test_run_scheduled_refuses_when_over_cap(stub_run_pipeline, monkeypatch):
    big = ",".join(f"T{i:03d}" for i in range(15))
    _set_env(monkeypatch, INSIGHT_TICKERS=big, INSIGHT_MAX_BATCH="10",
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 1
    assert stub_run_pipeline == [], "no tickers should have been processed"


def test_run_scheduled_override_bypasses_cap(stub_run_pipeline, monkeypatch):
    big = ",".join(f"T{i:03d}" for i in range(15))
    _set_env(monkeypatch, INSIGHT_TICKERS=big, INSIGHT_MAX_BATCH="10",
             INSIGHT_BATCH_OVERRIDE="1", INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert len(stub_run_pipeline) == 15


def test_run_scheduled_at_cap_runs(stub_run_pipeline, monkeypatch):
    """Exactly at the cap is allowed (boundary test)."""
    csv = ",".join(f"T{i:03d}" for i in range(10))
    _set_env(monkeypatch, INSIGHT_TICKERS=csv, INSIGHT_MAX_BATCH="10",
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert len(stub_run_pipeline) == 10


def test_run_scheduled_empty_env_falls_through_to_watchlist_then_default(
    stub_run_pipeline, monkeypatch
):
    """Empty INSIGHT_TICKERS no longer refuses — it falls through the chain.
    With watchlist also empty, the cron uses DEFAULT_TICKERS so the daily
    job never silently no-ops."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", lambda **kw: [])
    _set_env(monkeypatch, INSIGHT_TICKERS="", INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == list(job.DEFAULT_TICKERS)


def test_run_scheduled_json_array_input(stub_run_pipeline, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS='["SPY","IWM","QQQ","AVGO"]',
             INSIGHT_MAX_BATCH="10", INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["SPY", "IWM", "QQQ", "AVGO"]


def test_run_scheduled_tags_default_as_scheduled(captured_triggers, monkeypatch):
    """When the watchlist returns the canonical default set, trigger
    stays 'scheduled' (not 'manual_batch')."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(wl_mod, "load_watchlist", lambda **kw: list(job.DEFAULT_TICKERS))
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    _run(job._run_scheduled())
    assert all(trig == "scheduled" for _, trig in captured_triggers)


def test_run_scheduled_tags_extended_watchlist_as_manual_batch(captured_triggers, monkeypatch):
    """When the watchlist has extra tickers beyond defaults (the real
    state today: SPY/IWM/QQQ/AVGO/MSFT/SPX), the run gets tagged
    'manual_batch' for audit purposes."""
    import gcp.fetchers._watchlist as wl_mod
    monkeypatch.setattr(
        wl_mod, "load_watchlist",
        lambda **kw: ["SPY", "IWM", "QQQ", "AVGO", "MSFT"],
    )
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    _run(job._run_scheduled())
    assert all(trig == "manual_batch" for _, trig in captured_triggers)


def test_run_scheduled_tags_custom_list_as_manual_batch(captured_triggers, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ,AVGO", INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    _run(job._run_scheduled())
    assert all(trig == "manual_batch" for _, trig in captured_triggers)


def test_run_scheduled_invalid_max_batch_falls_back_to_default(stub_run_pipeline, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_MAX_BATCH="not-an-int",
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["SPY", "IWM", "QQQ"]


# ---------------------------------------------------------------------------
# parse_as_of — point-in-time replay cutoff parsing
# ---------------------------------------------------------------------------


from datetime import date, datetime, timedelta, timezone  # noqa: E402


def test_parse_as_of_none_returns_none():
    assert job.parse_as_of(None) is None
    assert job.parse_as_of("") is None
    assert job.parse_as_of("   ") is None


def test_parse_as_of_iso_date():
    assert job.parse_as_of("2026-04-26") == date(2026, 4, 26)


def test_parse_as_of_iso_datetime_naive_treated_as_utc():
    parsed = job.parse_as_of("2026-04-27T13:15:00")
    assert isinstance(parsed, datetime)
    assert parsed == datetime(2026, 4, 27, 13, 15, tzinfo=timezone.utc)


def test_parse_as_of_iso_datetime_with_z_suffix():
    parsed = job.parse_as_of("2026-04-27T13:15:00Z")
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(0)


def test_parse_as_of_iso_datetime_with_offset():
    parsed = job.parse_as_of("2026-04-27T09:15:00-04:00")
    assert isinstance(parsed, datetime)
    # 09:15 ET == 13:15 UTC
    assert parsed.astimezone(timezone.utc) == datetime(2026, 4, 27, 13, 15, tzinfo=timezone.utc)


def test_parse_as_of_rejects_future_date():
    # Use UTC's tomorrow because parse_as_of compares against UTC `now`.
    # `date.today()` returns *local* date which can be a day behind UTC
    # near midnight, making the assertion flaky.
    tomorrow_utc = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="future"):
        job.parse_as_of(tomorrow_utc)


def test_parse_as_of_rejects_future_datetime():
    far_future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="future"):
        job.parse_as_of(far_future)


def test_parse_as_of_rejects_malformed():
    with pytest.raises(ValueError):
        job.parse_as_of("not a date")


# ---------------------------------------------------------------------------
# INSIGHT_AS_OF threading through _run_scheduled and _run_on_demand
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_as_of(monkeypatch):
    """Capture the as_of value passed to _run_one for every ticker."""
    received: list[tuple[str, object]] = []

    async def fake_run_one(run_id: str, ticker: str, as_of=None, allow_update: bool = False, run_kind: str = "scheduled", triggered_by=None) -> bool:
        received.append((ticker, as_of))
        return True

    def fake_insert_run(ticker: str, trigger: str) -> str:
        return f"run-{ticker}"

    monkeypatch.setattr(job, "_run_one", fake_run_one)
    monkeypatch.setattr(job, "_insert_run", fake_insert_run)
    return received


def test_run_scheduled_threads_as_of_to_each_run(captured_as_of, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None,
             INSIGHT_AS_OF="2026-04-26")
    code = _run(job._run_scheduled())
    assert code == 0
    assert all(as_of == date(2026, 4, 26) for _, as_of in captured_as_of)


def test_run_scheduled_no_as_of_passes_none(captured_as_of, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None,
             INSIGHT_AS_OF=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert all(as_of is None for _, as_of in captured_as_of)


def test_run_scheduled_invalid_as_of_returns_one(captured_as_of, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None,
             INSIGHT_AS_OF="not-a-date")
    code = _run(job._run_scheduled())
    assert code == 1
    assert captured_as_of == [], "no tickers should have run"


def test_run_on_demand_threads_as_of(captured_as_of, monkeypatch):
    _set_env(monkeypatch, INSIGHT_RUN_ID="rid-1", INSIGHT_TICKER="AVGO",
             INSIGHT_AS_OF="2026-04-27T13:15:00Z")
    code = _run(job._run_on_demand())
    assert code == 0
    assert len(captured_as_of) == 1
    ticker, as_of = captured_as_of[0]
    assert ticker == "AVGO"
    assert isinstance(as_of, datetime)
    assert as_of == datetime(2026, 4, 27, 13, 15, tzinfo=timezone.utc)


def test_run_on_demand_invalid_as_of_returns_one(captured_as_of, monkeypatch):
    _set_env(monkeypatch, INSIGHT_RUN_ID="rid-1", INSIGHT_TICKER="AVGO",
             INSIGHT_AS_OF="2099-01-01")  # future
    code = _run(job._run_on_demand())
    assert code == 1
    assert captured_as_of == []


# ---------------------------------------------------------------------------
# Fan-out dispatch
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_fanout(monkeypatch):
    """Hermetic fan-out: record enqueues, record in-process runs.

    Returns (enqueued, ran). `enqueued` holds the kwargs of every
    enqueue_insight_task call; `ran` holds (run_id, ticker) for every
    ticker that fell through to in-process execution.
    """
    enqueued: list[dict] = []
    ran: list[tuple[str, str]] = []

    def fake_enqueue(run_id, ticker, **kwargs):
        enqueued.append({"run_id": run_id, "ticker": ticker, **kwargs})
        return job.EnqueueOutcome.ENQUEUED

    async def fake_run_one(run_id: str, ticker: str, as_of=None,
                           allow_update: bool = False,
                           run_kind: str = "scheduled", triggered_by=None) -> bool:
        ran.append((run_id, ticker))
        return True

    monkeypatch.setattr(job, "enqueue_insight_task", fake_enqueue)
    monkeypatch.setattr(job, "_run_one", fake_run_one)
    monkeypatch.setattr(job, "_insert_run", lambda ticker, trigger: f"run-{ticker}")
    monkeypatch.delenv("INSIGHT_FANOUT", raising=False)
    return enqueued, ran


def test_fanout_enqueues_each_ticker_and_runs_none_in_process(
    stub_fanout, monkeypatch
):
    enqueued, ran = stub_fanout
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_AS_OF=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert [e["ticker"] for e in enqueued] == ["SPY", "IWM", "QQQ"]
    assert ran == []


def test_fanout_forwards_triggered_by_so_run_kind_stays_scheduled(
    stub_fanout, monkeypatch
):
    """The daily scheduler passes INSIGHT_TRIGGERED_BY as a container
    override. If the dispatcher drops it, children record manual_replay
    and the audit trail is wrong while everything still looks green."""
    enqueued, _ = stub_fanout
    _set_env(
        monkeypatch,
        INSIGHT_TICKERS="SPY,IWM",
        INSIGHT_AS_OF=None,
        INSIGHT_TRIGGERED_BY="cloud-scheduler:insight-pipeline-daily",
    )
    _run(job._run_scheduled())
    assert all(
        e["triggered_by"] == "cloud-scheduler:insight-pipeline-daily"
        for e in enqueued
    )


def test_fanout_forwards_as_of_cutoff(stub_fanout, monkeypatch):
    enqueued, _ = stub_fanout
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM", INSIGHT_AS_OF="2026-09-04")
    _run(job._run_scheduled())
    assert all(e["as_of_iso"] == "2026-09-04" for e in enqueued)


def test_replay_child_is_not_forced_to_manual_update(stub_fanout, monkeypatch):
    """INSIGHT_AS_OF resolves allow_update=True, but the child must
    re-derive that from the cutoff. Forwarding force_update would
    relabel the run manual_update."""
    enqueued, _ = stub_fanout
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM", INSIGHT_AS_OF="2026-09-04")
    _run(job._run_scheduled())
    assert all(e["force_update"] is False for e in enqueued)


def test_explicit_update_is_forwarded(stub_fanout, monkeypatch):
    enqueued, _ = stub_fanout
    _set_env(
        monkeypatch, INSIGHT_TICKERS="SPY,IWM",
        INSIGHT_AS_OF=None, INSIGHT_UPDATE="true",
    )
    _run(job._run_scheduled())
    assert all(e["force_update"] is True for e in enqueued)


def test_enqueue_failure_falls_back_in_process_for_that_ticker_only(
    stub_fanout, monkeypatch
):
    enqueued, ran = stub_fanout

    def flaky(run_id, ticker, **kwargs):
        if ticker == "IWM":
            return job.EnqueueOutcome.NOT_ENQUEUED
        enqueued.append({"run_id": run_id, "ticker": ticker, **kwargs})
        return job.EnqueueOutcome.ENQUEUED

    monkeypatch.setattr(job, "enqueue_insight_task", flaky)
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_AS_OF=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert [e["ticker"] for e in enqueued] == ["SPY", "QQQ"]
    # Only the failed one runs in-process, and it reuses its existing
    # run row rather than inserting a second.
    assert ran == [("run-IWM", "IWM")]


def test_fanout_disabled_runs_sequentially(stub_fanout, monkeypatch):
    enqueued, ran = stub_fanout
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM", INSIGHT_AS_OF=None,
             INSIGHT_FANOUT="0")
    _run(job._run_scheduled())
    assert enqueued == []
    assert [t for _, t in ran] == ["SPY", "IWM"]


def test_single_ticker_does_not_pay_a_container_start(stub_fanout, monkeypatch):
    enqueued, ran = stub_fanout
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY", INSIGHT_AS_OF=None)
    _run(job._run_scheduled())
    assert enqueued == []
    assert [t for _, t in ran] == ["SPY"]


def test_a_batch_too_large_to_throttle_does_not_fan_out(stub_fanout, monkeypatch):
    """max-concurrent-dispatches bounds in-flight dispatch requests, not
    running executions: jobs.run returns as soon as the execution exists,
    so the slot frees immediately and N tickers would become N concurrent
    executions against the same LLM provider. Above the cap we stay
    in-process, where concurrency is one ticker at a time."""
    enqueued, ran = stub_fanout
    over = ",".join(f"T{i}" for i in range(job.FANOUT_MAX_TICKERS + 1))
    _set_env(monkeypatch, INSIGHT_TICKERS=over, INSIGHT_AS_OF=None,
             INSIGHT_BATCH_OVERRIDE="1")
    code = _run(job._run_scheduled())
    assert code == 0
    assert enqueued == [], "a batch this size must not launch that many executions"
    assert len(ran) == job.FANOUT_MAX_TICKERS + 1


def test_a_batch_at_the_cap_still_fans_out(stub_fanout, monkeypatch):
    enqueued, ran = stub_fanout
    at_cap = ",".join(f"T{i}" for i in range(job.FANOUT_MAX_TICKERS))
    _set_env(monkeypatch, INSIGHT_TICKERS=at_cap, INSIGHT_AS_OF=None)
    _run(job._run_scheduled())
    assert len(enqueued) == job.FANOUT_MAX_TICKERS
    assert ran == []


def test_an_unknown_enqueue_is_not_run_in_process(stub_fanout, monkeypatch):
    """UNKNOWN means a child may already be running this run_id. Running it
    here too would put two pipelines on one run, racing its status
    transitions and doubling its history rows -- strictly worse than the
    missing report that skipping costs."""
    enqueued, ran = stub_fanout

    def ambiguous(run_id, ticker, **kwargs):
        if ticker == "IWM":
            return job.EnqueueOutcome.UNKNOWN
        enqueued.append({"run_id": run_id, "ticker": ticker, **kwargs})
        return job.EnqueueOutcome.ENQUEUED

    monkeypatch.setattr(job, "enqueue_insight_task", ambiguous)
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_AS_OF=None)
    code = _run(job._run_scheduled())
    assert code == 0
    assert [e["ticker"] for e in enqueued] == ["SPY", "QQQ"]
    assert ran == [], "an unknown outcome must not be resolved by running it again"


def test_a_definitive_refusal_still_runs_in_process(stub_fanout, monkeypatch):
    """The contrast case: NOT_ENQUEUED is the server saying nothing was
    accepted, so the fallback is safe and must still happen."""
    enqueued, ran = stub_fanout

    def refused(run_id, ticker, **kwargs):
        if ticker == "IWM":
            return job.EnqueueOutcome.NOT_ENQUEUED
        enqueued.append({"run_id": run_id, "ticker": ticker, **kwargs})
        return job.EnqueueOutcome.ENQUEUED

    monkeypatch.setattr(job, "enqueue_insight_task", refused)
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_AS_OF=None)
    _run(job._run_scheduled())
    assert ran == [("run-IWM", "IWM")]


def test_auto_refresh_children_are_classified_as_auto_refresh(monkeypatch):
    """docs/plans/MORNING_RUN_PROTECTION_PLAN.md defines run_kind
    'auto_refresh' for auto_refresh_top_n, reached via triggered_by
    'cron:auto-refresh-top-n'. Without this branch the pre-warm's children
    record 'manual_replay' and are indistinguishable from a hand-run replay
    -- and insight_runs.trigger can no longer tell them apart either, since
    the check constraint forces it to 'on_demand'."""
    from gcp import auto_refresh_top_n as ar

    for key in ("INSIGHT_UPDATE", "INSIGHT_AS_OF", "INSIGHT_TRIGGERED_BY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("INSIGHT_TRIGGERED_BY", ar.AUTO_REFRESH_TRIGGERED_BY)
    assert job._resolve_run_kind_and_update(False) == (False, "auto_refresh")


def test_auto_refresh_classification_does_not_shadow_scheduled_or_replay(monkeypatch):
    """The new branch sits below update and as_of, and beside
    cloud-scheduler — it must not capture those."""
    for key in ("INSIGHT_UPDATE", "INSIGHT_AS_OF", "INSIGHT_TRIGGERED_BY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("INSIGHT_TRIGGERED_BY", "cloud-scheduler:insight-pipeline-daily")
    assert job._resolve_run_kind_and_update(False) == (False, "scheduled")
    monkeypatch.setenv("INSIGHT_TRIGGERED_BY", "cron:auto-refresh-top-n")
    monkeypatch.setenv("INSIGHT_AS_OF", "2026-09-04")
    assert job._resolve_run_kind_and_update(False) == (True, "replay_refresh")


def test_run_kind_fits_the_column():
    """run_kind is VARCHAR(20) with no check constraint, so a new value
    needs no migration but must still fit."""
    assert len("auto_refresh") <= 20


# ---------------------------------------------------------------------------
# Redelivered-launch claim (Codex, PR #1094)
# ---------------------------------------------------------------------------
#
# Two things can start a SECOND execution carrying the SAME run_id, and the
# deterministic Cloud Tasks name stops neither because it only deduplicates
# create_task: Cloud Tasks retries the HTTP target POST (queue is
# --max-attempts 2, and jobs.run creates the execution before returning an
# Operation, so a lost response is indistinguishable from a failed launch),
# and Cloud Run retries the task (job is --max-retries 1). Unclaimed, both
# run the paid pipeline, both append history, and they race the final status.


def test_the_loser_of_a_redelivery_race_does_not_run_the_pipeline(monkeypatch):
    """Second execution finds the row already 'running' and stands down
    WITHOUT invoking the pipeline."""
    ran: list = []

    async def fake_pipeline(ticker, **kwargs):
        ran.append(ticker)
        raise AssertionError("pipeline must not run for an unclaimed run")

    monkeypatch.setattr(job, "_transition", lambda *a, **k: False)
    monkeypatch.setattr(job, "run_insight_pipeline", fake_pipeline)
    ok = _run(job._run_one("run-1", "SPY"))
    # True, not False: nothing failed. Returning False would make Cloud Run
    # retry the loser of the race indefinitely.
    assert ok is True
    assert ran == [], "the losing execution ran the pipeline anyway"


def test_the_winner_of_the_claim_proceeds(monkeypatch):
    """Contrast case: a successful claim must still run normally."""
    ran: list = []

    async def fake_pipeline(ticker, **kwargs):
        ran.append(ticker)
        raise RuntimeError("stop after the claim")

    monkeypatch.setattr(job, "_transition", lambda *a, **k: True)
    monkeypatch.setattr(job, "run_insight_pipeline", fake_pipeline)
    monkeypatch.setattr(job, "load_routes_snapshot", lambda *a, **k: {})
    _run(job._run_one("run-1", "SPY"))
    assert ran == ["SPY"], "the claiming execution must run the pipeline"


def test_the_claim_is_a_compare_and_swap_on_claimable_states():
    """The SQL must be conditional, and must still admit 'failed' so Cloud
    Run's own retry-after-failure keeps working. 'running' is deliberately
    excluded: a crashed execution leaves a visibly stuck row, which beats a
    second one duplicating work we cannot prove has stopped."""
    import inspect

    src = inspect.getsource(job._transition)
    assert "status IN ('queued', 'failed')" in src, (
        "the running transition must be a conditional claim, not a bare UPDATE"
    )
    assert "rowcount" in src, "the claim must be decided by rows affected"
