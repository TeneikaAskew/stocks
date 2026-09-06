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

REPO = Path(__file__).resolve().parent.parent
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

def test_concurrent_on_demand_grid_requests_hit_the_vendor_once(monkeypatch):
    """The rate limiter bounds DISTINCT tickers and deliberately lets a repeat
    of the same one through, so it cannot stop two concurrent requests for the
    SAME off-list ticker from both calling AlphaVantage.

    The claim/decline single-flight lets exactly one caller fetch.
    """
    from api.routers import grid

    av_calls: list[str] = []
    holding = threading.Event()
    barrier = threading.Barrier(2, timeout=5)

    def one_request(_n):
        barrier.wait()
        with grid._claim_on_demand_fetch("ZZZZ") as mine:
            if mine:
                av_calls.append("ZZZZ")
                holding.set()
                # stay claimed long enough that the other thread must decline
                threading.Event().wait(0.15)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one_request, range(2)))

    assert av_calls == ["ZZZZ"], (
        f"AlphaVantage was called {len(av_calls)} times for one ticker")


def test_a_declined_claimant_does_not_block(monkeypatch):
    """The waiter must NOT park a worker thread.

    A per-ticker `threading.Lock` with the loser blocking on it would occupy a
    FastAPI worker for the whole fetch, so a burst on one ticker could starve
    `/api/health` — trading one starvation for another. The decline path
    returns immediately.
    """
    import time
    from api.routers import grid

    claimed = threading.Event()
    released = threading.Event()

    def holder():
        with grid._claim_on_demand_fetch("SLOW") as mine:
            assert mine
            claimed.set()
            released.wait(timeout=5)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert claimed.wait(timeout=5)

    started = time.monotonic()
    with grid._claim_on_demand_fetch("SLOW") as mine:
        assert mine is False, "a second caller wrongly claimed the fetch"
    elapsed = time.monotonic() - started

    released.set()
    t.join(timeout=5)
    assert elapsed < 0.5, f"the decline path blocked for {elapsed:.2f}s"


def test_claims_are_released_even_when_the_fetch_raises():
    """A raising fetch must not strand a ticker as permanently in-flight.

    The registry is a self-emptying set rather than a dict of locks that is
    never pruned, so a client rotating through fresh ticker strings cannot
    grow it without bound.
    """
    from api.routers import grid

    with pytest.raises(RuntimeError):
        with grid._claim_on_demand_fetch("BOOM") as mine:
            assert mine
            raise RuntimeError("vendor exploded")

    assert "BOOM" not in grid._INFLIGHT_CLAIMS
    with grid._claim_on_demand_fetch("BOOM") as mine:
        assert mine, "the ticker stayed claimed after a failure"


def test_claim_registry_is_empty_once_the_work_finishes():
    from api.routers import grid

    for i in range(200):
        with grid._claim_on_demand_fetch(f"T{i}"):
            pass
    assert not grid._INFLIGHT_CLAIMS, (
        f"registry retained {len(grid._INFLIGHT_CLAIMS)} entries")


# ── journal local file ──────────────────────────────────────────────────────

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
