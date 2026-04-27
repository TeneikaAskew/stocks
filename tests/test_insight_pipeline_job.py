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

    async def fake_run_one(run_id: str, ticker: str) -> bool:
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

    async def fake_run_one(run_id: str, ticker: str) -> bool:
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


def test_run_scheduled_default_runs_three_tickers(stub_run_pipeline, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["SPY", "IWM", "QQQ"]


def test_run_scheduled_refuses_when_over_cap(stub_run_pipeline, monkeypatch):
    big = ",".join(f"T{i:03d}" for i in range(15))
    _set_env(monkeypatch, INSIGHT_TICKERS=big, INSIGHT_MAX_BATCH="10",
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 1
    assert stub_run_pipeline == [], "no tickers should have been processed"


def test_run_scheduled_override_bypasses_cap(stub_run_pipeline, monkeypatch):
    big = ",".join(f"T{i:03d}" for i in range(15))
    _set_env(monkeypatch, INSIGHT_TICKERS=big, INSIGHT_MAX_BATCH="10",
             INSIGHT_BATCH_OVERRIDE="1", INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 0
    assert len(stub_run_pipeline) == 15


def test_run_scheduled_at_cap_runs(stub_run_pipeline, monkeypatch):
    """Exactly at the cap is allowed (boundary test)."""
    csv = ",".join(f"T{i:03d}" for i in range(10))
    _set_env(monkeypatch, INSIGHT_TICKERS=csv, INSIGHT_MAX_BATCH="10",
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 0
    assert len(stub_run_pipeline) == 10


def test_run_scheduled_empty_input_refuses(stub_run_pipeline, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS="", INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 1
    assert stub_run_pipeline == []


def test_run_scheduled_json_array_input(stub_run_pipeline, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS='["SPY","IWM","QQQ","AVGO"]',
             INSIGHT_MAX_BATCH="10", INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["SPY", "IWM", "QQQ", "AVGO"]


def test_run_scheduled_tags_default_as_scheduled(captured_triggers, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS=None, INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    asyncio.run(job._run_scheduled())
    assert all(trig == "scheduled" for _, trig in captured_triggers)


def test_run_scheduled_tags_custom_list_as_manual_batch(captured_triggers, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ,AVGO", INSIGHT_MAX_BATCH=None,
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    asyncio.run(job._run_scheduled())
    assert all(trig == "manual_batch" for _, trig in captured_triggers)


def test_run_scheduled_invalid_max_batch_falls_back_to_default(stub_run_pipeline, monkeypatch):
    _set_env(monkeypatch, INSIGHT_TICKERS="SPY,IWM,QQQ", INSIGHT_MAX_BATCH="not-an-int",
             INSIGHT_BATCH_OVERRIDE=None, INSIGHT_RUN_ID=None)
    code = asyncio.run(job._run_scheduled())
    assert code == 0
    assert stub_run_pipeline == ["SPY", "IWM", "QQQ"]
