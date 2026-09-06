"""Coalesce concurrent work on the same key without parking worker threads.

The problem this solves appears once per expensive cached operation, and it
appeared three times in this PR before it got a name.

While every route handler was `async def`, they all ran on one event loop and
could not overlap, so a cold cache was refilled exactly once no matter how
many requests arrived. Threadpool dispatch removes that accident: N concurrent
misses on the same key run N copies of the same expensive work.

The obvious fix is a lock per key, and it is wrong here. A waiter blocked on a
`threading.Lock` occupies a FastAPI worker for the full duration of the work,
so a burst on one key can fill the pool and starve unrelated routes —
`/api/health` and `/api/me` included, which is the exact instance-wide
starvation this migration exists to remove. Trading one starvation for another
is not a fix, and it is a trap worth naming because a lock genuinely is the
right answer in most other places.

So: **claim or decline, never block**. What a decliner does is a policy
decision that belongs to the caller, because the honest answer differs:

    grid on-demand fetch   -> return the typed `unavailable` envelope; the UI
                              already renders it and polls again
    freshness audit        -> serve the stale report if one exists, else 503;
                              a monitoring surface tolerates staleness better
                              than it tolerates a starved worker pool
    market dates           -> `wait()` a bounded moment, then re-read; the
                              claimant usually finishes first, and the fallback
                              is doing the work rather than failing

`wait()` exists for that last shape and is deliberately bounded: it caps how
long a worker may be held rather than removing the bound entirely.
"""
from __future__ import annotations

import contextlib
import threading
from typing import Iterator

__all__ = ["SingleFlight"]


class SingleFlight:
    """Per-key "am I the one doing this?" coordination."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key -> Event, set when the claimant finishes. Present only while a
        # claim is in flight, so the mapping cannot grow without bound: every
        # entry is removed in a `finally`, whatever the claimant does.
        self._inflight: dict[str, threading.Event] = {}

    @contextlib.contextmanager
    def claim(self, key: str) -> Iterator[bool]:
        """Yield True if this caller owns the work for `key`, else False.

        Never blocks. The claim is released however the body exits, so a
        raising body cannot strand a key as permanently in flight.
        """
        with self._lock:
            done = self._inflight.get(key)
            mine = done is None
            if mine:
                done = threading.Event()
                self._inflight[key] = done
        try:
            yield mine
        finally:
            if mine:
                with self._lock:
                    self._inflight.pop(key, None)
                done.set()          # type: ignore[union-attr]

    def wait(self, key: str, timeout: float) -> bool:
        """Wait up to `timeout` for an in-flight claim on `key` to finish.

        Returns True if it finished (or was never in flight), False on
        timeout. For the caller whose fallback is doing the work itself: a
        short wait usually turns a duplicate query into a cache hit, and the
        timeout is what keeps a slow claimant from holding a worker
        indefinitely.
        """
        with self._lock:
            done = self._inflight.get(key)
        if done is None:
            return True
        return done.wait(timeout)

    def in_flight(self) -> int:
        """How many claims are outstanding. For tests and diagnostics."""
        with self._lock:
            return len(self._inflight)
