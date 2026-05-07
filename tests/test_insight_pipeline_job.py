"""Unit tests for gcp.insight_pipeline_job batch-guard helpers.

Covers parse_tickers (CSV + JSON-array), classify_trigger
(scheduled vs manual_batch), and the _run_scheduled cap/override
behaviour. The ticker run path itself is mocked — these tests
specifically protect the gates, not the LLM pipeline.
"""

from __future__ import annotations

import asyncio
import os
import pytest

from gcp import insight_pipeline_job as job


def _run(coro):
    """Run an async coroutine synchronously, robust to plugin interference.

    `asyncio.run()` raises ``RuntimeError("cannot be called from a running
    event loop")`` whenever the current thread already has a *running*
    loop registered — which has been observed on CI under
    pytest-asyncio 1.x + anyio 4.x (anyio's pytest plugin is pulled in
    transitively via httpx in requirements.txt and can leave a loop
    reference attached to the main thread).

    Build a brand-new loop and drive it with ``run_until_complete``,
    which bypasses ``asyncio.run``'s ``_get_running_loop()`` check.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
    code = asyncio.run(job._run_on_demand())
    assert code == 0
    assert len(captured_as_of) == 1
    ticker, as_of = captured_as_of[0]
    assert ticker == "AVGO"
    assert isinstance(as_of, datetime)
    assert as_of == datetime(2026, 4, 27, 13, 15, tzinfo=timezone.utc)


def test_run_on_demand_invalid_as_of_returns_one(captured_as_of, monkeypatch):
    _set_env(monkeypatch, INSIGHT_RUN_ID="rid-1", INSIGHT_TICKER="AVGO",
             INSIGHT_AS_OF="2099-01-01")  # future
    code = asyncio.run(job._run_on_demand())
    assert code == 1
    assert captured_as_of == []
