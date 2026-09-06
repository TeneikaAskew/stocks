"""A `cachetools` cache that survives threadpool dispatch.

Why this exists
---------------
Every API route handler used to be `async def`, so they all ran on the single
event loop and never overlapped. Module-level caches were therefore safe by
accident: no two requests could be inside one at the same time.

Converting the handlers to plain `def` moves them onto FastAPI's threadpool,
which is the point — a blocking query no longer stalls every other request.
It also means two requests really can be inside the same cache at once, and
`cachetools.TTLCache` is **not thread-safe**. Its own documentation says so.
The failure is not a stale read: `TTLCache.__setitem__` expires timed-out
entries and may `popitem` while another thread is walking the same internal
linked structure, which raises `KeyError` or `RuntimeError` and returns a 500
from a handler that was only trying to read a cache.

`cachetools` ships no locked variant, and its docs point users at exactly
this pattern.

Usage
-----
Identical to the cache it wraps::

    _DATES_CACHE = ThreadSafeCache(TTLCache(maxsize=64, ttl=43200))

    if key in _DATES_CACHE:          # locked
        return _DATES_CACHE[key]     # locked
    _DATES_CACHE[key] = value        # locked

The lock covers each individual operation, which is what makes the cache's
internals safe. It does NOT make a read-then-write sequence atomic — two
threads can still both miss and both compute. That is a duplicated
computation, not corruption, and where it matters (the on-demand grid fetch
spending AlphaVantage quota) the caller needs its own single-flight guard.
Stated here because a wrapper named "thread-safe" invites the stronger
assumption.

**Look up with `get`, never `in` then `[]`.** ::

    value = _CACHE.get(key, MISS)          # one locked operation
    if value is not MISS:
        return value

Those are two separate locked operations::

    if key in _CACHE:          # lock taken and released
        return _CACHE[key]     # lock taken again — the entry may be gone

and on a cache at capacity another thread can insert a different key and
evict the tested entry in between, so the second line raises `KeyError` out
of a handler that had just confirmed the key was present. Every call site in
`platform/api/` uses the `get` form; `MISS` exists so a cached `None` is
still a hit.
"""
from __future__ import annotations

import threading
from typing import Any, Iterator, MutableMapping

__all__ = ["ThreadSafeCache", "MISS"]


class _Miss:
    """Sentinel for `cache.get(key, MISS)`.

    A distinct object rather than `None`, so a cache legitimately holding
    `None` is still reported as a hit.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<cache MISS>"

    def __bool__(self) -> bool:
        return False


MISS = _Miss()


class ThreadSafeCache(MutableMapping):
    """Serialise every operation on a wrapped `cachetools` cache."""

    def __init__(self, cache: MutableMapping) -> None:
        self._cache = cache
        # Re-entrant: `__setitem__` on a full cache can trigger the wrapped
        # cache's own eviction callbacks, which may re-enter.
        self._lock = threading.RLock()

    # ── MutableMapping ──────────────────────────────────────────────────────
    def __getitem__(self, key: Any) -> Any:
        with self._lock:
            return self._cache[key]

    def __setitem__(self, key: Any, value: Any) -> None:
        with self._lock:
            self._cache[key] = value

    def __delitem__(self, key: Any) -> None:
        with self._lock:
            del self._cache[key]

    def __contains__(self, key: Any) -> bool:
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __iter__(self) -> Iterator:
        # Iterate a snapshot: yielding under the lock would hold it for as
        # long as the caller's loop body takes, and yielding without one
        # walks a structure another thread may be evicting from.
        with self._lock:
            return iter(list(self._cache))

    # ── convenience passthroughs used by the routers ────────────────────────
    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            return self._cache.get(key, default)

    def pop(self, key: Any, *args: Any) -> Any:
        with self._lock:
            return self._cache.pop(key, *args)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def maxsize(self) -> int:
        return self._cache.maxsize

    @property
    def lock(self) -> threading.RLock:
        """The wrapper's lock, for a caller that needs a compound operation.

        A check-then-set across two calls is not atomic on its own; hold this
        around the whole sequence when it must be.
        """
        return self._lock

    def __repr__(self) -> str:
        return f"ThreadSafeCache({self._cache!r})"
