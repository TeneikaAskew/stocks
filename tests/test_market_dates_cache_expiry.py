"""/api/market/dates caches against the DATA, not a model of the schedule.

The list query is a Parallel Seq Scan of the whole per-ticker partition
(measured 2026-09-06: 2,003,580 rows scanned to return 3,278 dates, 1,716 ms),
so it has to be cached. Deciding WHEN to invalidate went wrong three times,
each in a different way, and none of them failed visibly — the endpoint kept
returning plausible dates, just stale ones:

  1. a fixed 12h TTL from request time, which spanned the ingestion entirely
  2. a 23:00 UTC boundary, when the scheduler runs in America/New_York, so it
     expired hours BEFORE the job and then held the pre-ingestion answer
  3. an Eastern boundary for the 23:00 writer, which missed a second writer

There are at least three writers to this table, read from GCP rather than any
doc:

    av-intraday-nightly      0 21 * * 1-6   America/New_York   (Mon-SAT)
    fetch-market-data-daily  0 23 * * 1-5   America/New_York
    av-intraday-monthly      0 21 1 * *     America/New_York

So the cache no longer models the schedule at all. It probes MAX(ts) — one
index descent, 10.8 ms against the 1,716 ms scan — and rebuilds only when the
newest bar has advanced. That is correct for any number of writers on any
schedule, including ad-hoc backfills no schedule describes.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "platform"))

pytest.importorskip("fastapi")

from starlette.testclient import TestClient  # noqa: E402

import api.main as main_module  # noqa: E402


@pytest.fixture
def client():
    return TestClient(main_module.app)


@pytest.fixture
def probe_backed(monkeypatch):
    """Serve the probe and the list from a controllable fake, counting scans."""
    state = {"max_ts": pd.Timestamp("2026-09-04 20:00:00"), "scans": 0,
             "dates": [pd.Timestamp("2026-09-04").date(),
                       pd.Timestamp("2026-09-03").date()]}

    def fake_query(sql, params=None):
        if "MAX(ts)" in sql:
            return pd.DataFrame({"max_ts": [state["max_ts"]]})
        state["scans"] += 1
        return pd.DataFrame({"trade_date": list(state["dates"])})

    monkeypatch.setattr(main_module, "_CLOUD_SQL", True)
    monkeypatch.setattr(main_module, "_dates_query", fake_query)
    monkeypatch.setattr(main_module, "_MARKET_DATES_CACHE",
                        type(main_module._MARKET_DATES_CACHE)())
    return state


def test_repeat_requests_do_not_rerun_the_scan(client, probe_backed):
    for _ in range(5):
        assert client.get("/api/market/dates/IWM").status_code == 200
    assert probe_backed["scans"] == 1, (
        "the expensive list query ran more than once for unchanged data")


def test_a_new_bar_invalidates_immediately(client, probe_backed):
    client.get("/api/market/dates/IWM")
    assert probe_backed["scans"] == 1

    # A writer lands a new session — any writer, any schedule.
    probe_backed["max_ts"] = pd.Timestamp("2026-09-07 20:00:00")
    probe_backed["dates"] = [pd.Timestamp("2026-09-07").date()] + probe_backed["dates"]

    body = client.get("/api/market/dates/IWM").json()
    assert probe_backed["scans"] == 2, "new data did not invalidate the cache"
    assert body["dates"][0] == "20260907", "stale list served after ingestion"


def test_no_schedule_assumption_survives_in_the_module():
    """The schedule model is gone, not merely bypassed."""
    src = (Path(main_module.__file__)).read_text()
    for gone in ("_next_ingest_boundary", "_INGEST_HOUR_ET", "_INGEST_HOUR_UTC"):
        assert gone not in src, (
            f"{gone} is back — freshness must follow the data, since three "
            f"separate attempts to model the ingest schedule were each wrong")


def test_eviction_drops_one_entry_not_the_whole_cache(client, probe_backed):
    """A working set just over the cap must not flush every valid entry.

    Clearing meant the 65th miss discarded 64 still-valid entries, so nearly
    every request paid the full scan and the cache defeated itself.
    """
    cap = main_module._MARKET_DATES_CACHE_MAX
    for i in range(cap + 1):
        client.get(f"/api/market/dates/T{i}")

    cache = main_module._MARKET_DATES_CACHE
    assert len(cache) == cap, f"expected {cap} entries, found {len(cache)}"
    assert "T0" not in cache, "the least-recently-used entry should be evicted"
    assert f"T{cap}" in cache, "the newest entry should be resident"
