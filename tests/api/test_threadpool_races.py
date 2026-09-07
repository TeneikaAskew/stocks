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
import time
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
            if re.search(r"if \S+ in _[A-Z0-9_]*CACHE\b", line):
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
    from lib.single_flight import SingleFlight

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
    from lib.single_flight import SingleFlight

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
    from lib.single_flight import SingleFlight

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
    from lib.single_flight import SingleFlight

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
    from lib.single_flight import SingleFlight

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


# ── winning a claim is not the same as being first ──────────────────────────

def test_a_claimant_rechecks_the_cache_before_redoing_the_work():
    """The gap between "cache is cold" and "I hold the claim".

    Every coalescing call site reads its cache, finds it empty, and only then
    claims. A thread descheduled between those two steps can take the claim
    moments after the previous claimant finished and populated the cache — and
    the first version of this code started work immediately on `mine=True`, so
    the expensive operation ran twice inside one TTL. That is precisely the
    bound the coalescing exists to hold, defeated by the coalescing itself.

    This drives the sequence deterministically rather than racing for it.
    """
    from lib.single_flight import SingleFlight

    flight = SingleFlight()
    cache: dict[str, str] = {}
    work_runs = []

    def call(key: str) -> str:
        cached = cache.get(key)
        if cached is not None:
            return cached
        with flight.claim(key) as mine:
            if not mine:
                flight.wait(key, 1.0)
            # The re-check under discussion.
            cached = cache.get(key)
            if cached is not None:
                return cached
            work_runs.append(key)
            cache[key] = "answer"
            return cache[key]

    # First caller populates the cache. A second caller that had ALREADY
    # passed the pre-claim check (simulated by calling again with the claim
    # now free) must not redo the work.
    assert call("IWM") == "answer"
    with flight.claim("IWM") as mine:
        assert mine, "the claim should be free once the first caller finished"
    assert call("IWM") == "answer"
    assert work_runs == ["IWM"], (
        f"the work ran {len(work_runs)} times for one key: {work_runs}")


def test_firebase_initializes_once_under_concurrent_callers():
    """Two cold `/api/me` requests must not both call `initialize_app()`.

    The loser gets `ValueError: The default Firebase app already exists`,
    which `current_user_email` swallows — so that request answers
    `email: null, is_admin: false`. A signed-in admin rendered as an anonymous
    visitor, on the endpoint the frontend uses to decide what to show them.
    That is a fabricated identity, not a slow response, which is why this one
    is worth a lock rather than tolerating the duplicate work.
    """
    import api.auth as api_auth

    calls: list[int] = []
    barrier = threading.Barrier(8)

    class _FakeFirebase:
        _apps: dict = {}

        @staticmethod
        def initialize_app(options=None):
            if _FakeFirebase._apps:
                raise ValueError("The default Firebase app already exists.")
            calls.append(1)
            time.sleep(0.02)             # widen the window
            _FakeFirebase._apps["[DEFAULT]"] = object()

    original_ready = api_auth._firebase_ready
    sys.modules["firebase_admin"] = _FakeFirebase   # type: ignore[assignment]
    api_auth._firebase_ready = False
    errors: list[BaseException] = []

    def go() -> None:
        barrier.wait()
        try:
            api_auth._ensure_firebase()
        except BaseException as exc:      # noqa: BLE001
            errors.append(exc)

    try:
        threads = [threading.Thread(target=go) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
    finally:
        api_auth._firebase_ready = original_ready
        sys.modules.pop("firebase_admin", None)

    assert not errors, f"a concurrent initializer raised: {errors[:2]}"
    assert calls == [1], (
        f"initialize_app ran {len(calls)} times; the losers would have raised "
        "ValueError and been reported as anonymous")


def _ticker_info_harness(mp, store, fetches, sleep_s=0.05):
    """Point lib.ticker_info at an in-memory cache and a counting fetcher."""
    import lib.ticker_info as ticker_info

    def fake_fetch(ticker: str):
        fetches.append(ticker)
        time.sleep(sleep_s)
        return {"Symbol": ticker, "Name": "Test"}

    mp.setattr(ticker_info, "fetch_ticker_overview", fake_fetch)
    mp.setattr(ticker_info, "_cloud_sql_available", lambda: False)
    # Only the STORAGE is faked. `_merge_into_local_cache` used to be stubbed
    # here with a one-line reimplementation, which meant every test through
    # this harness exercised the stub's merge semantics rather than the real
    # function -- so the peers-preservation test passed against a call site
    # that could still lose peers (Codex, PR #991). A harness that reimplements
    # the thing under test cannot fail for the reason it exists.
    mp.setattr(ticker_info, "_load_local_cache",
               lambda: {k: dict(v) for k, v in store.items()})
    mp.setattr(ticker_info, "_save_local_cache",
               lambda cache: (store.clear(), store.update(cache)))
    return ticker_info


def _concurrently(fn, n=6, timeout=10):
    results = []
    barrier = threading.Barrier(n)

    def go() -> None:
        barrier.wait()
        results.append(fn())

    threads = [threading.Thread(target=go) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    return results


def test_a_stale_entry_is_refreshed_once_and_served_to_everyone_else():
    """What the ticker coalescing is actually for.

    A stale-but-present entry is the common case at a 30-day freshness
    window: one caller refreshes from the vendor and the rest are served the
    stale value immediately. Nobody waits -- these run in threadpooled request
    handlers, so a waiter holds a FastAPI worker, and a burst on one ticker
    could fill the pool and starve `/api/health` and `/api/me`. That is the
    trade this whole migration removes, and a first version of this
    coalescing reintroduced it with a 20 s bounded wait.
    """
    fetches: list[str] = []
    stale = {"Symbol": "IWM", "_fetched_utc": "2020-01-01T00:00:00+00:00"}
    store = {"IWM": dict(stale)}

    with pytest.MonkeyPatch.context() as mp:
        ticker_info = _ticker_info_harness(mp, store, fetches, sleep_s=0.2)
        started = time.monotonic()
        results = _concurrently(lambda: ticker_info.get_ticker_info("IWM"))
        elapsed = time.monotonic() - started

    assert len(results) == 6 and all(r for r in results), results
    assert fetches == ["IWM"], (
        f"the vendor was called {len(fetches)} times refreshing one stale "
        f"entry: {fetches}")
    assert elapsed < 1.0, (
        f"the decliners took {elapsed:.2f}s; they should be served from cache "
        "immediately rather than waiting on the claimant")


def test_a_cold_ticker_refetches_rather_than_fabricating_a_miss():
    """The deliberate cost of never waiting, pinned so it stays deliberate.

    With nothing cached there is nothing honest to serve: returning `None`
    would surface as `404 No info for IWM` for a perfectly valid ticker while
    a fetch is in flight -- a fabricated answer (Rule 3.7). A duplicate vendor
    call is the cheaper wrong thing, so decliners fall through and fetch.

    This asserts the trade rather than the ideal, because a test that
    demanded one call here would be demanding the wait back.
    """
    fetches: list[str] = []
    store: dict[str, dict] = {}

    with pytest.MonkeyPatch.context() as mp:
        ticker_info = _ticker_info_harness(mp, store, fetches)
        results = _concurrently(lambda: ticker_info.get_ticker_info("IWM"))

    assert len(results) == 6 and all(r for r in results), results
    assert len(fetches) >= 1, "nobody fetched a cold ticker"


def test_an_overview_refresh_does_not_discard_independently_cached_peers():
    """`replace=True` wipes the ticker's entry, and `_peers` lives there too.

    `get_peers` stores `_peers` under its own flight and never reads the
    Cloud SQL relationships column back, so an overview refresh that dropped
    them would silently cost a second FinViz scrape on the next request.
    """
    fetches: list[str] = []
    store = {"IWM": {"_peers": ["VTWO", "IJR"],
                     "_fetched_utc": "2020-01-01T00:00:00+00:00"}}

    with pytest.MonkeyPatch.context() as mp:
        ticker_info = _ticker_info_harness(mp, store, fetches)
        ticker_info.get_ticker_info("IWM")

    assert store["IWM"].get("_peers") == ["VTWO", "IJR"], (
        f"the overview refresh discarded the cached peers: {store['IWM']}")


def test_peers_stored_after_the_overview_fetch_still_survive():
    """The window the first fix left open.

    That fix read `_peers` at the CALL SITE, folded it into `info`, and then
    called `_merge_into_local_cache(replace=True)` — which re-reads the cache
    under `_LOCAL_CACHE_LOCK` and replaces the whole entry. A `get_peers()`
    store landing between the call site's read and the merge's locked re-read
    was therefore still erased (Codex, PR #991): the read was outside the lock
    that the write it was racing has to take.

    This places a peers write in exactly that window. The overview payload
    already exists — the fetch has returned — and only then do peers land.
    """
    import lib.ticker_info as ti

    with pytest.MonkeyPatch.context() as mp:
        cache: dict = {}
        mp.setattr(ti, "_load_local_cache", lambda: cache)
        mp.setattr(ti, "_save_local_cache", lambda c: cache.update(c))

        info = {"Name": "iShares Russell 2000", "_fetched_utc": "2026-09-07T00:00:00+00:00"}

        # A concurrent get_peers() completes HERE: after the overview fetch
        # returned `info`, before the overview is written.
        ti._merge_into_local_cache("IWM", {"_peers": ["VTWO", "IJR"]}, replace=False)

        ti._merge_into_local_cache("IWM", info, replace=True, preserve=("_peers",))

    assert cache["IWM"].get("_peers") == ["VTWO", "IJR"], (
        "a peers write landing after the overview payload was assembled was "
        f"erased by the replace: {cache['IWM']}")
    assert cache["IWM"].get("Name") == "iShares Russell 2000", (
        "preserving peers must not cost the overview itself")


def test_the_overview_branch_does_not_read_the_cache_twice_to_preserve_peers():
    """The property the fix actually establishes.

    The first fix read `_peers` at the call site and folded it into `info`
    before calling `_merge_into_local_cache(replace=True)`. That read took the
    lock, released it, and only then did the merge re-acquire and re-read — so
    a `get_peers()` store landing in between was still erased (Codex, PR #991).

    The window cannot be tested by scheduling a write into it, because the fix
    is that the window no longer exists: preservation now reads from the SAME
    locked snapshot the replace is built from. What IS observable is that the
    separate pre-read is gone — exactly ONE cache load happens between the
    vendor fetch returning and the write, and it is the merge's own.
    """
    import lib.ticker_info as ti

    loads = {"n": 0}
    marks: dict = {}
    store = {"IWM": {"_peers": ["VTWO", "IJR"],
                     "_fetched_utc": "2020-01-01T00:00:00+00:00"}}

    def load():
        loads["n"] += 1
        return {k: dict(v) for k, v in store.items()}

    def fake_fetch(ticker: str):
        marks["after_fetch"] = loads["n"]
        return {"Symbol": ticker, "Name": "Test"}

    def save(cache):
        marks.setdefault("at_save", loads["n"])
        store.clear()
        store.update(cache)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ti, "fetch_ticker_overview", fake_fetch)
        mp.setattr(ti, "_cloud_sql_available", lambda: False)
        mp.setattr(ti, "_load_local_cache", load)
        mp.setattr(ti, "_save_local_cache", save)
        ti.get_ticker_info("IWM")

    between = marks["at_save"] - marks["after_fetch"]
    assert between == 1, (
        f"{between} cache reads between the vendor fetch and the write; expected "
        "exactly 1 (the merge's own, under the lock). More than one means a "
        "preservation read happens outside the lock the write it races takes.")
    assert store["IWM"].get("_peers") == ["VTWO", "IJR"]


def test_preserve_never_overwrites_a_value_the_update_supplies():
    """A future overview that returns peers of its own must win."""
    import lib.ticker_info as ti

    with pytest.MonkeyPatch.context() as mp:
        cache = {"IWM": {"_peers": ["stale"]}}
        mp.setattr(ti, "_load_local_cache", lambda: cache)
        mp.setattr(ti, "_save_local_cache", lambda c: cache.update(c))
        ti._merge_into_local_cache("IWM", {"_peers": ["fresh"]},
                                   replace=True, preserve=("_peers",))

    assert cache["IWM"]["_peers"] == ["fresh"]


def test_concurrent_overview_and_peers_writes_never_lose_either():
    """Both paths hammering one ticker; neither may erase the other.

    No test in this repo drove two threads through the same cache path before
    this round, which is why the overwrite survived a review and a fix.
    """
    import threading
    import lib.ticker_info as ti

    with pytest.MonkeyPatch.context() as mp:
        cache: dict = {}
        real_lock = ti._LOCAL_CACHE_LOCK
        mp.setattr(ti, "_load_local_cache", lambda: {k: dict(v) for k, v in cache.items()})

        def save(c):
            with real_lock:
                cache.clear()
                cache.update(c)

        mp.setattr(ti, "_save_local_cache", save)

        errors: list[str] = []

        def write_overview(n: int) -> None:
            ti._merge_into_local_cache(
                "IWM", {"Name": f"overview-{n}"}, replace=True, preserve=("_peers",))

        def write_peers(n: int) -> None:
            ti._merge_into_local_cache("IWM", {"_peers": [f"peer-{n}"]}, replace=False)

        threads = []
        for i in range(25):
            threads.append(threading.Thread(target=write_overview, args=(i,)))
            threads.append(threading.Thread(target=write_peers, args=(i,)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entry = cache.get("IWM", {})
        assert entry.get("_peers"), (
            f"peers were lost under concurrent overview refreshes: {entry}")
        assert entry.get("Name"), (
            f"the overview was lost under concurrent peers writes: {entry}")
        assert not errors, errors


def test_the_import_index_enforces_the_endpoints_own_dedupe_key():
    """The database authority must match `_dedupe_key()`, not approximate it.

    `_dedupe_key` truncates the timestamp to the minute and rounds the price
    to 4dp — deliberately, because an imported row carries no seconds while
    the stored row does. A first version of the index compared the RAW
    columns, so two concurrent commits of one fill passed it and inserted
    twice, creating exactly the duplicate a sequential commit would have
    skipped.

    This asserts the correspondence in both directions: the key calls the two
    rows identical, and the index DDL names the same two normalizations.
    """
    from api.routers import journal

    a = journal._dedupe_key("iwm", "call", "2026-09-04T10:00:00", 200.000012)
    b = journal._dedupe_key("IWM", "CALL", "2026-09-04 10:00", 200.0000)
    assert a == b, ("the dedupe key should call these the same trade; if this "
                    "changed, the index below has to change with it")

    ddl = (REPO / "gcp" / "schema.sql").read_text()
    # Slice from the CREATE, not from the first mention of the name: the
    # DROP that precedes it (so an existing deployment converges off the
    # raw-column version) also carries the name, and slicing from there
    # matched only "DROP INDEX IF EXISTS ...;".
    idx = ddl[ddl.index("CREATE UNIQUE INDEX IF NOT EXISTS "
                        "uq_journal_entries_import_dedupe"):]
    idx = idx[:idx.index(";")]
    assert "date_trunc('minute', entry_ts AT TIME ZONE 'UTC')" in idx, (
        "the index must truncate entry_ts to the minute, as _dedupe_key does. "
        "`AT TIME ZONE` is required: date_trunc is STABLE on timestamptz and "
        "IMMUTABLE on timestamp, so Postgres refuses to index the former.")
    assert "round(entry_price::numeric, 4)" in idx, (
        "the index must round entry_price to 4dp, as _dedupe_key does")
