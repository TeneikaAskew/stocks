"""InsightCache unit tests."""
from __future__ import annotations


def test_evict_drops_one_ticker_and_forces_a_refetch():
    """Codex on #1022: the cache is keyed by ticker with a wall-clock
    staleness window, so a replay crossing into the next session within
    that window kept serving the previous session's insight. The session
    reset evicts the ticker; other tickers stay cached."""
    from lib.strategies.insight_cache import InsightCache
    clock = [1000.0]
    cache = InsightCache(refresh_after_seconds=60.0, now_fn=lambda: clock[0])
    calls: list[str] = []

    def fetcher(ticker):
        calls.append(ticker)
        return None                     # NoInsight sentinel path is enough

    cache.get("spy", fetcher)
    cache.get("iwm", fetcher)
    assert calls == ["SPY", "IWM"]
    cache.get("spy", fetcher)
    assert calls == ["SPY", "IWM"], "fresh entry served from cache"
    cache.evict("spy")
    cache.get("spy", fetcher)
    cache.get("iwm", fetcher)
    assert calls == ["SPY", "IWM", "SPY"], "evicted ticker refetched, the other still cached"
    cache.evict("never-cached")         # no-op, never raises
