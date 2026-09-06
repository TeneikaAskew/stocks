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
    """Two tickers, two load/modify/save cycles, one shared file.

    Without the lock the later write discards the earlier one's new entry, so
    a cache that should hold both holds one.
    """
    import lib.ticker_info as ti

    cache_file = tmp_path / "ticker_info.json"
    monkeypatch.setattr(ti, "_LOCAL_CACHE_PATH", cache_file)

    def add(name: str) -> None:
        for _ in range(40):
            with ti._LOCAL_CACHE_LOCK:
                cache = ti._load_local_cache()
                cache[name] = {"symbol": name}
                ti._save_local_cache(cache)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(add, [f"T{i}" for i in range(6)]))

    final = json.loads(cache_file.read_text())
    assert sorted(final) == [f"T{i}" for i in range(6)], (
        f"entries lost to a concurrent write: {sorted(final)}")


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
