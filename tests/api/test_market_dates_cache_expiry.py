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

So the cache no longer models the schedule at all. Freshness is TWO
mechanisms, and the tests below cover both because neither is sufficient
alone:

  * the probe — MAX(ts), one index descent, 10.8 ms against the 1,716 ms
    scan — rebuilds the list the moment the newest bar advances, for any
    number of writers on any schedule.
  * a 1h TTL — the backstop for every write the probe CANNOT see. MAX(ts)
    only moves forward, so a backfill that fills a gap OLDER than the newest
    bar leaves it unchanged, and the probe reports fresh. That is a supported
    production path: av-intraday-nightly refetches the previous month as well
    as the current one. Without the TTL a Saturday repair would stay hidden
    until Monday's session landed, and for a ticker receiving no newer bars,
    indefinitely.

MAX(inserted_at) would catch both in one probe, but there is no index on it
(measured: Parallel Seq Scan, 977 ms), so it cannot go on the request path.
"""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "platform"))

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


def test_a_backfilled_older_date_is_caught_by_the_TTL(client, probe_backed,
                                                      monkeypatch):
    """The probe's blind spot, and the backstop that covers it.

    A backfill that fills a gap OLDER than the newest bar does not move
    MAX(ts), so the probe reports fresh and the stale list keeps being served.
    Only the TTL rescues it. Delete `_MARKET_DATES_TTL` or drop `within_ttl`
    from the freshness test and this fails; every other test in this file
    stays green, which is why it exists.
    """
    assert client.get("/api/market/dates/IWM").json()["dates"] == [
        "20260904", "20260903"]
    assert probe_backed["scans"] == 1

    # av-intraday-nightly refetches the previous month and repairs a gap.
    # The newest bar is untouched, so MAX(ts) does not move.
    probe_backed["dates"] = probe_backed["dates"] + [pd.Timestamp("2026-08-29").date()]

    body = client.get("/api/market/dates/IWM").json()
    assert probe_backed["scans"] == 1, (
        "the probe should still report fresh — MAX(ts) did not advance")
    assert "20260829" not in body["dates"], (
        "documenting the blind spot: the probe cannot see a historical insert")

    # Age the entry past the TTL. Backdating `cached_at` exercises the exact
    # comparison the request path makes, without a clock shim that would also
    # have to fool the write side.
    cached_ts, cached_at, payload = main_module._MARKET_DATES_CACHE["IWM"]
    main_module._MARKET_DATES_CACHE["IWM"] = (
        cached_ts,
        cached_at - main_module._MARKET_DATES_TTL - timedelta(seconds=1),
        payload,
    )

    body = client.get("/api/market/dates/IWM").json()
    assert probe_backed["scans"] == 2, (
        "the TTL backstop did not expire the entry, so a historical repair "
        "stays invisible indefinitely for a ticker receiving no newer bars")
    assert "20260829" in body["dates"], "backfilled date still missing after expiry"


def test_a_fresh_entry_inside_the_TTL_is_not_rescanned(client, probe_backed):
    """The other half of the contract: the TTL must not be so short that it
    defeats the probe. One second under the limit is still a cache hit."""
    client.get("/api/market/dates/IWM")
    cached_ts, cached_at, payload = main_module._MARKET_DATES_CACHE["IWM"]
    main_module._MARKET_DATES_CACHE["IWM"] = (
        cached_ts,
        cached_at - main_module._MARKET_DATES_TTL + timedelta(seconds=1),
        payload,
    )
    client.get("/api/market/dates/IWM")
    assert probe_backed["scans"] == 1, "expired one second early"


def test_configured_but_empty_never_falls_through_to_GCS(client, probe_backed,
                                                         monkeypatch):
    """A successful empty result is an answer, not a failure.

    The `except` below the Cloud SQL query raises 503 rather than serving the
    GCS staging parquets, because those are a different and possibly staler
    dataset. But a query that SUCCEEDS with zero rows raises nothing: the
    `if not df.empty` block was skipped, the try/except fell off its end, and
    execution continued into the GCS branch — reaching the same cross-source
    fallback by the one path that never raises.

    The GCS stub here returns blobs, so the two paths are distinguishable by
    their output rather than by inspection.
    """
    from api import gcs_reader

    def fake_blobs(prefix, pattern):
        if "/minute/" in prefix:
            return ["data/zzzz/minute/zzzz_minute_20190102.parquet"]
        return ["data/zzzz/intraday/zzzz_av_1min_201901.parquet"]

    monkeypatch.setattr(gcs_reader, "list_matching_blobs", fake_blobs)
    probe_backed["max_ts"] = None
    probe_backed["dates"] = []

    body = client.get("/api/market/dates/ZZZZ").json()
    assert body["source"] == "cloud_sql", (
        f"empty Cloud SQL result fell through to {body['source']}: a ticker "
        f"absent from the system of record was answered from staging files")
    assert body["dates"] == [], f"GCS dates leaked into the response: {body['dates']}"
    assert body["months"] == [], f"GCS months leaked into the response: {body['months']}"
    assert "ZZZZ" not in main_module._MARKET_DATES_CACHE, (
        "an empty result must not be cached — MAX(ts) is NULL over zero rows, "
        "so the entry could never be judged fresh and would be re-deleted "
        "every request")
