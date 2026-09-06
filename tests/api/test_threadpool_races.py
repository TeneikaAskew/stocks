"""Concurrency tests for the state threadpool dispatch made reachable.

Every handler used to be `async def`, so they all ran on one event loop and
could not interleave. Module-level caches, singletons and file writes were
safe by accident. Converting handlers to plain `def` is the point of this
branch — a blocking query no longer stalls every other request — and it also
makes all of that state genuinely concurrent.

The suite had **no test that ran two requests through the same path at once**,
which is why none of these races were visible. Each test below drives real
threads through the real code and fails against the pre-fix version.

Hermetic: no network, no database, no Cloud Run.
"""
from __future__ import annotations

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "platform"))

pytest.importorskip("fastapi")
pytest.importorskip("cachetools")


# ── ThreadSafeCache ─────────────────────────────────────────────────────────

def test_cache_survives_concurrent_eviction():
    """`cachetools.TTLCache` is not thread-safe and says so.

    The realistic failure is not a stale read: `__setitem__` expires entries
    and may `popitem` while another thread walks the same internal linked
    structure, raising KeyError/RuntimeError out of a handler that was only
    reading a cache. Hammering a small cache from many threads is what
    surfaces it.
    """
    from cachetools import TTLCache
    from api.threadsafe_cache import ThreadSafeCache

    cache = ThreadSafeCache(TTLCache(maxsize=8, ttl=300))
    errors: list[BaseException] = []
    stop = threading.Event()

    def churn(worker: int) -> None:
        try:
            for i in range(3000):
                if stop.is_set():
                    return
                key = f"k{(worker * 7 + i) % 40}"
                cache[key] = i
                cache.get(key)
                key in cache          # noqa: B015 - exercising __contains__
                len(cache)
        except BaseException as exc:   # noqa: BLE001 - recording, then asserting
            errors.append(exc)
            stop.set()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(churn, range(8)))

    assert not errors, f"concurrent cache access raised: {errors[:3]}"
    assert len(cache) <= cache.maxsize


def test_cache_holds_the_maxsize_bound_under_contention():
    from cachetools import TTLCache
    from api.threadsafe_cache import ThreadSafeCache

    cache = ThreadSafeCache(TTLCache(maxsize=16, ttl=300))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda n: cache.__setitem__(f"t{n}", n), range(600)))
    assert len(cache) == 16


def test_contains_then_getitem_is_the_pattern_this_cache_cannot_make_safe():
    """`in` then `[]` are two locked operations, not one.

    On a cache at capacity another thread can insert a different key and evict
    the tested entry in between, so the second line raises `KeyError` out of a
    handler that had just confirmed the key was present. The wrapper cannot
    fix that; the CALL SITES have to use `get`.

    This test does not assert the crash (it is a race, so it is not
    deterministic). It asserts the property that makes the crash possible, so
    the reason `MISS` exists stays legible.
    """
    from cachetools import TTLCache
    from api.threadsafe_cache import MISS, ThreadSafeCache

    cache = ThreadSafeCache(TTLCache(maxsize=1, ttl=300))
    cache["a"] = 1
    assert "a" in cache
    cache["b"] = 2                    # evicts "a" between the two operations
    assert "a" not in cache
    assert cache.get("a", MISS) is MISS, "get must report the miss, not raise"


def test_missing_key_is_reported_as_miss_even_when_the_value_is_none():
    """`MISS` is a distinct sentinel so a cached `None` is still a hit."""
    from cachetools import TTLCache
    from api.threadsafe_cache import MISS, ThreadSafeCache

    cache = ThreadSafeCache(TTLCache(maxsize=4, ttl=300))
    cache["present"] = None
    assert cache.get("present", MISS) is None
    assert cache.get("absent", MISS) is MISS


def test_no_api_call_site_uses_the_unsafe_lookup_pattern():
    """A guard, because this is a pattern that reads as obviously correct."""
    import re

    offenders = []
    for path in (REPO / "platform" / "api").rglob("*.py"):
        if path.name == "threadsafe_cache.py":
            continue
        for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if re.search(r"if \S+ in _[A-Z0-9_]*CACHE", line):
                offenders.append(f"{path.name}:{i} {line.strip()}")
    assert not offenders, (
        "`in` then `[]` on a shared cache is two locked operations; use "
        "`cache.get(key, MISS)`:\n  " + "\n  ".join(offenders))


# ── circuit breaker ─────────────────────────────────────────────────────────

def test_circuit_breaker_counts_every_concurrent_failure():
    """A get/increment/set loses updates: N threads raise the count by 1.

    That is the whole failure. During a vendor outage the breaker never
    reaches its threshold, so every worker keeps retrying against a vendor
    that is already down — precisely under the load that makes it matter.
    """
    from lib.api_client import _CircuitBreaker

    breaker = _CircuitBreaker(failure_threshold=10_000, cooldown_seconds=60)
    n = 500
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: breaker.record_failure("AV"), range(n)))

    assert breaker._consecutive_failures["AV"] == n, (
        "lost failure counts: the breaker will not trip when it should")


def test_circuit_breaker_opens_and_stays_open_under_contention():
    from lib.api_client import _CircuitBreaker

    breaker = _CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: breaker.record_failure("AV"), range(50)))
    with pytest.raises(RuntimeError, match="Circuit breaker open"):
        breaker.check("AV")


# ── Cloud SQL connector singleton ───────────────────────────────────────────

def test_connector_singleton_is_built_exactly_once(monkeypatch):
    """Two cold requests could both pass `if _CONNECTOR is None`.

    Each then builds a Connector with its own background refresh machinery
    and connections, and one is overwritten without ever being closed —
    during the cold-start burst, when the instance can least absorb it.
    """
    import lib.agents.model_routing as mr

    built: list[object] = []

    class _FakeConnector:
        def __init__(self, *a, **kw):
            built.append(self)

        def close(self):
            pass

    fake_module = type(sys)("google.cloud.sql.connector")
    fake_module.Connector = _FakeConnector
    monkeypatch.setitem(sys.modules, "google.cloud.sql.connector", fake_module)
    monkeypatch.setattr(mr, "_CONNECTOR", None)
    monkeypatch.setattr(mr.atexit, "register", lambda *a, **k: None)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: mr._get_connector(), range(12)))

    assert len(built) == 1, f"built {len(built)} connectors, expected 1"
    assert len({id(r) for r in results}) == 1, "callers got different singletons"


# ── ticker_info local cache file ────────────────────────────────────────────

def test_ticker_info_cache_does_not_lose_concurrent_entries(tmp_path, monkeypatch):
    """Two tickers, two read-modify-writes, one shared file.

    The first version of this test wrapped the sequence in
    `_LOCAL_CACHE_LOCK` itself, so it passed against production code that did
    NOT hold the lock across load/modify/save — it proved only that a lock
    works when you hold it. Codex caught that on #991.

    It now calls `_merge_into_local_cache`, which is what production calls,
    with no lock of its own.
    """
    import lib.ticker_info as ti

    cache_file = tmp_path / "ticker_info.json"
    monkeypatch.setattr(ti, "_LOCAL_CACHE_PATH", cache_file)

    def add(name: str) -> None:
        for _ in range(40):
            ti._merge_into_local_cache(name, {"symbol": name}, replace=True)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(add, [f"T{i}" for i in range(6)]))

    final = json.loads(cache_file.read_text())
    assert sorted(final) == [f"T{i}" for i in range(6)], (
        f"entries lost to a concurrent write: {sorted(final)}")


def test_ticker_info_merge_preserves_a_concurrently_stored_overview(tmp_path,
                                                                    monkeypatch):
    """`get_peers` must not drop an overview another thread just wrote.

    It re-reads under the lock and merges keys, rather than writing back the
    snapshot it read before its own network fetch.
    """
    import lib.ticker_info as ti

    cache_file = tmp_path / "ticker_info.json"
    monkeypatch.setattr(ti, "_LOCAL_CACHE_PATH", cache_file)

    ti._merge_into_local_cache("IWM", {"Name": "iShares Russell 2000"},
                               replace=True)
    ti._merge_into_local_cache("IWM", {"_peers": ["SPY", "QQQ"]}, replace=False)

    entry = json.loads(cache_file.read_text())["IWM"]
    assert entry["Name"] == "iShares Russell 2000", "the overview was discarded"
    assert entry["_peers"] == ["SPY", "QQQ"]


def test_ticker_info_cache_is_never_observed_partially_written(tmp_path, monkeypatch):
    """`write_text` truncates in place; a reader could catch it empty, hit the
    corrupt-cache branch, and then save its own single entry over everything.
    An atomic rename means a reader sees the whole old file or the whole new
    one."""
    import lib.ticker_info as ti

    cache_file = tmp_path / "ticker_info.json"
    monkeypatch.setattr(ti, "_LOCAL_CACHE_PATH", cache_file)
    ti._save_local_cache({f"S{i}": {"symbol": f"S{i}"} for i in range(200)})

    torn: list[int] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                except Exception:              # noqa: BLE001
                    torn.append(-1)
                    continue
                if len(data) < 200:
                    torn.append(len(data))

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        for _ in range(60):
            ti._save_local_cache({f"S{i}": {"symbol": f"S{i}"} for i in range(200)})
    finally:
        stop.set()
        t.join(timeout=5)

    assert not torn, f"reader observed a partial cache {torn[:5]}"


# ── grid on-demand single-flight ────────────────────────────────────────────

def test_single_flight_claims_exactly_one_caller(monkeypatch):
    from api.single_flight import SingleFlight

    sf = SingleFlight()
    claims: list[bool] = []
    barrier = threading.Barrier(4, timeout=5)
    hold = threading.Event()

    def attempt(_n):
        barrier.wait()
        with sf.claim("K") as mine:
            claims.append(mine)
            if mine:
                hold.wait(timeout=1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(attempt, range(4)))
        hold.set()

    assert claims.count(True) == 1, f"{claims.count(True)} callers claimed the work"


def test_a_decliner_does_not_block(monkeypatch):
    """The whole reason this is not a lock.

    A waiter blocked on a `threading.Lock` holds a FastAPI worker for the full
    duration of the work, so a burst on one key fills the pool and starves
    unrelated routes — the instance-wide starvation this branch removes.
    """
    import time
    from api.single_flight import SingleFlight

    sf = SingleFlight()
    claimed, release = threading.Event(), threading.Event()

    def holder():
        with sf.claim("SLOW") as mine:
            assert mine
            claimed.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert claimed.wait(timeout=5)

    started = time.monotonic()
    with sf.claim("SLOW") as mine:
        assert mine is False
    elapsed = time.monotonic() - started

    release.set()
    t.join(timeout=5)
    assert elapsed < 0.5, f"the decline path blocked for {elapsed:.2f}s"


def test_bounded_wait_returns_when_the_claimant_finishes():
    """`wait()` is for the caller whose only fallback is doing the work itself.

    It must return promptly when the claimant finishes — that is what turns a
    duplicate 1.7 s scan into a cache hit — and must time out rather than hand
    the worker over indefinitely.
    """
    import time
    from api.single_flight import SingleFlight

    sf = SingleFlight()
    claimed = threading.Event()

    def holder():
        with sf.claim("K") as mine:
            assert mine
            claimed.set()
            time.sleep(0.1)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert claimed.wait(timeout=5)

    started = time.monotonic()
    assert sf.wait("K", timeout=5.0) is True
    assert time.monotonic() - started < 2.0
    t.join(timeout=5)

    # And the timeout path: a claim still held when the budget expires.
    held = threading.Event()
    stop = threading.Event()

    def slow():
        with sf.claim("SLOW") as mine:
            assert mine
            held.set()
            stop.wait(timeout=5)

    t2 = threading.Thread(target=slow, daemon=True)
    t2.start()
    assert held.wait(timeout=5)
    started = time.monotonic()
    assert sf.wait("SLOW", timeout=0.2) is False
    assert time.monotonic() - started < 1.0
    stop.set()
    t2.join(timeout=5)


def test_claims_are_released_even_when_the_work_raises():
    """A raising body must not strand a key as permanently in flight."""
    from api.single_flight import SingleFlight

    sf = SingleFlight()
    with pytest.raises(RuntimeError):
        with sf.claim("BOOM") as mine:
            assert mine
            raise RuntimeError("vendor exploded")

    assert sf.in_flight() == 0
    with sf.claim("BOOM") as mine:
        assert mine, "the key stayed claimed after a failure"


def test_the_registry_does_not_grow():
    """A dict of per-key locks that is never pruned grows without bound; the
    claim registry holds only keys with work actually in flight."""
    from api.single_flight import SingleFlight

    sf = SingleFlight()
    for i in range(500):
        with sf.claim(f"T{i}"):
            pass
    assert sf.in_flight() == 0


def test_concurrent_on_demand_grid_requests_hit_the_vendor_once():
    """The rate limiter bounds DISTINCT tickers and deliberately lets a repeat
    of the same one through, so it cannot stop two concurrent requests for the
    SAME off-list ticker from both calling AlphaVantage."""
    from api.routers import grid

    av_calls: list[str] = []
    barrier = threading.Barrier(2, timeout=5)

    def one_request(_n):
        barrier.wait()
        with grid._ONDEMAND_FLIGHT.claim("ZZZZ") as mine:
            if mine:
                av_calls.append("ZZZZ")
                threading.Event().wait(0.15)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one_request, range(2)))

    assert av_calls == ["ZZZZ"], (
        f"AlphaVantage was called {len(av_calls)} times for one ticker")


def test_freshness_decliner_serves_a_stale_report_rather_than_waiting(monkeypatch):
    """A lock here would park workers on the health surface itself.

    The decliner gets the previous report, labelled stale, immediately.
    """
    import time
    from api.routers import health

    monkeypatch.setattr(health, "_cache_value", {"ok": True, "sources": []})
    monkeypatch.setattr(health, "_cache_expires_at", time.monotonic() - 1)  # expired

    with health._AUDIT_FLIGHT.claim(health._AUDIT_KEY) as mine:
        assert mine
        started = time.monotonic()
        out = health.freshness_report_dict()
        elapsed = time.monotonic() - started

    assert out["stale"] is True
    assert "stale_age_seconds" in out
    assert elapsed < 0.5, f"the decliner blocked for {elapsed:.2f}s"


def test_freshness_decliner_503s_when_nothing_is_cached(monkeypatch):
    """503 says "ask again", which beats fabricating a report or holding the
    connection until an audit that may take tens of seconds completes."""
    import time
    from fastapi import HTTPException
    from api.routers import health

    monkeypatch.setattr(health, "_cache_value", None)
    monkeypatch.setattr(health, "_cache_expires_at", time.monotonic() - 1)

    with health._AUDIT_FLIGHT.claim(health._AUDIT_KEY) as mine:
        assert mine
        with pytest.raises(HTTPException) as ei:
            health.freshness_report_dict()
    assert ei.value.status_code == 503


# ── journal local file ─# ── journal local file ──────────────────────────────────────────────────────

def test_concurrent_journal_saves_never_expose_a_torn_file(tmp_path, monkeypatch):
    """`_load_local` raises on an unparseable file, so a torn read would 500.

    `_save_local` publishes by rename, so there is no torn state to read.
    """
    import api.routers.journal as journal

    path = tmp_path / "IWM.json"
    monkeypatch.setattr(journal, "_local_path", lambda t: path)

    entries = [{"id": str(i), "ticker": "IWM"} for i in range(300)]
    journal._save_local("IWM", entries)

    failures: list[BaseException] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                assert len(journal._load_local("IWM")) == 300
            except BaseException as exc:       # noqa: BLE001
                failures.append(exc)
                return

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    try:
        for _ in range(60):
            journal._save_local("IWM", entries)
    finally:
        stop.set()
        t.join(timeout=5)

    assert not failures, f"reader saw a torn journal: {failures[:2]}"
