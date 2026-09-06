"""Tests for Phase 1 insight direction gate.

Two layers tested independently:

  1. InsightCache (lib/strategies/insight_cache.py) — pull-based cache
     with staleness check, graceful degradation on DB failures.
  2. evaluate_direction_gate — pure decision function from the v1
     conviction-unaware matrix in docs/replays/2026-05-10-corrected-baseline-v2.md §6.

Empirical justification per docs/audits/2026-05-10-risk-reviewer-validation.md:
  - 951 directional fires across 36 days SPY/IWM/QQQ
  - aligned-with-plan win rate: 55.7%
  - opposite-to-plan win rate:  35.4%
  - delta: -20.3pp — filtering opposing weak removes the loss-rich
    bucket while keeping medium+ as potential reversal signals.
"""
from __future__ import annotations

from datetime import date

import pytest

from lib.strategies.insight_cache import (
    InsightCache,
    InsightContext,
    NoInsight,
    GateDecision,
    evaluate_direction_gate,
)


# ── InsightCache ──────────────────────────────────────────────────


def test_cache_cold_miss_calls_fetcher():
    """First get(ticker) triggers a fetch."""
    cache = InsightCache(now_fn=lambda: 0.0)
    fetch_count = [0]
    def fetcher(t):
        fetch_count[0] += 1
        return InsightContext(ticker=t, direction='long', conviction='low', regime='normal')
    ctx = cache.get('SPY', fetcher)
    assert ctx is not None
    assert ctx.direction == 'long'
    assert fetch_count[0] == 1


def test_cache_serves_cached_value_within_refresh_window():
    """Second get(ticker) within refresh_after_seconds doesn't re-fetch."""
    fetch_count = [0]
    def fetcher(t):
        fetch_count[0] += 1
        return InsightContext(ticker=t, direction='long', conviction='low', regime='normal')

    now = [0.0]
    cache = InsightCache(refresh_after_seconds=60.0, now_fn=lambda: now[0])
    cache.get('SPY', fetcher)
    now[0] = 30.0  # 30s later
    cache.get('SPY', fetcher)
    assert fetch_count[0] == 1, "should serve from cache"


def test_cache_refetches_after_staleness():
    """get(ticker) past refresh_after_seconds re-fetches."""
    fetch_count = [0]
    def fetcher(t):
        fetch_count[0] += 1
        return InsightContext(ticker=t, direction='long', conviction='low', regime='normal')

    now = [0.0]
    cache = InsightCache(refresh_after_seconds=60.0, now_fn=lambda: now[0])
    cache.get('SPY', fetcher)
    now[0] = 70.0  # 70s later — past 60s window
    cache.get('SPY', fetcher)
    assert fetch_count[0] == 2


def test_cache_handles_no_insight_today():
    """Fetcher returning None caches NoInsight; subsequent gets return None."""
    fetch_count = [0]
    def fetcher(t):
        fetch_count[0] += 1
        return None

    cache = InsightCache(refresh_after_seconds=60.0, now_fn=lambda: 0.0)
    out1 = cache.get('SPY', fetcher)
    out2 = cache.get('SPY', fetcher)
    assert out1 is None
    assert out2 is None
    assert fetch_count[0] == 1, "NoInsight should also be cached"


def test_cache_degrades_safely_when_fetcher_raises():
    """Fetcher exception should NOT crash the cache; returns None."""
    def fetcher(t):
        raise RuntimeError("Cloud SQL down")

    cache = InsightCache(now_fn=lambda: 0.0)
    out = cache.get('SPY', fetcher)
    assert out is None


def test_cache_independent_per_ticker():
    """Caches per-ticker; fetcher called once per unique ticker."""
    fetch_log = []
    def fetcher(t):
        fetch_log.append(t)
        return InsightContext(ticker=t, direction='long', conviction='low', regime='normal')

    cache = InsightCache(now_fn=lambda: 0.0)
    cache.get('SPY', fetcher)
    cache.get('IWM', fetcher)
    cache.get('SPY', fetcher)  # cached
    cache.get('QQQ', fetcher)
    assert sorted(set(fetch_log)) == ['IWM', 'QQQ', 'SPY']
    assert len(fetch_log) == 3


# ── evaluate_direction_gate — the v1 matrix ──────────────────────


def _ctx(direction='long', conviction='low'):
    return InsightContext(
        ticker='SPY', direction=direction, conviction=conviction,
        regime='normal',
    )


def test_no_insight_yields_annotate():
    """Without an insight, gate is no-op."""
    d = evaluate_direction_gate('CALL', 'weak', insight=None)
    assert d.action == 'annotate'


def test_aligned_call_long_passes():
    d = evaluate_direction_gate('CALL', 'weak', _ctx('long'))
    assert d.action == 'pass'


def test_aligned_call_long_medium_passes():
    d = evaluate_direction_gate('CALL', 'medium', _ctx('long'))
    assert d.action == 'pass'


def test_aligned_put_short_passes():
    d = evaluate_direction_gate('PUT', 'weak', _ctx('short'))
    assert d.action == 'pass'


def test_opposite_weak_long_suppressed():
    """The headline behavior — opposing weak gets dropped."""
    d = evaluate_direction_gate('PUT', 'weak', _ctx('long'))
    assert d.action == 'suppress'
    assert 'opposing_weak' in d.reason


def test_opposite_weak_short_suppressed():
    d = evaluate_direction_gate('CALL', 'weak', _ctx('short'))
    assert d.action == 'suppress'


def test_opposite_medium_long_downgraded():
    """Opposing medium gets one-tier downgrade."""
    d = evaluate_direction_gate('PUT', 'medium', _ctx('long'))
    assert d.action == 'downgrade'
    assert d.new_strength == 'weak'


def test_opposite_strong_long_kept_with_tag():
    """Opposing strong is kept — could be the actual reversal signal."""
    d = evaluate_direction_gate('PUT', 'strong', _ctx('long'))
    assert d.action == 'tag'
    assert 'opposing_strong' in d.reason


def test_flat_day_weak_annotated_not_suppressed():
    """Flat-day v1: weak passes through with annotation (not suppressed)."""
    d = evaluate_direction_gate('CALL', 'weak', _ctx('flat'))
    assert d.action == 'annotate'
    assert 'flat_day' in d.reason


def test_flat_day_medium_downgraded():
    d = evaluate_direction_gate('CALL', 'medium', _ctx('flat'))
    assert d.action == 'downgrade'
    assert d.new_strength == 'weak'


def test_flat_day_strong_kept():
    d = evaluate_direction_gate('CALL', 'strong', _ctx('flat'))
    assert d.action == 'tag'


# ── Invalidation tripwire ────────────────────────────────────────


def test_invalidated_thesis_disables_suppression():
    """When invalidated, opposing weak passes (gate effectively off)."""
    d = evaluate_direction_gate('PUT', 'weak', _ctx('long'),
                               insight_invalidated=True)
    assert d.action == 'annotate'
    assert 'invalidated' in d.reason


def test_invalidated_thesis_aligned_still_annotates():
    """Aligned fires also pass through with annotate when invalidated
    (no special boost — neutral state)."""
    d = evaluate_direction_gate('CALL', 'weak', _ctx('long'),
                               insight_invalidated=True)
    assert d.action == 'annotate'


# ── Consistency check ───────────────────────────────────────────


def test_gate_decision_returns_dataclass():
    """All paths return a GateDecision (no raw strings or dicts)."""
    for fire_dir in ('CALL', 'PUT'):
        for strength in ('weak', 'medium', 'strong'):
            for plan_dir in ('long', 'short', 'flat'):
                d = evaluate_direction_gate(fire_dir, strength, _ctx(plan_dir))
                assert isinstance(d, GateDecision)
                assert d.action in ('pass', 'suppress', 'downgrade', 'tag', 'annotate')
                assert d.reason  # non-empty


# ── Empirical-justification regression ───────────────────────────


def test_v1_matrix_implements_audit_recommendation():
    """The matrix from docs/replays/2026-05-10-corrected-baseline-v2.md §6.

    Conviction-UNAWARE in v1: each combination of (insight direction, fire
    direction, fire strength) maps to exactly one action. Lock the
    contract here so future changes can't silently regress."""
    expected = {
        # (plan_dir, fire_dir, strength) → action
        ('long', 'CALL', 'weak'):    'pass',
        ('long', 'CALL', 'medium'):  'pass',
        ('long', 'CALL', 'strong'):  'pass',
        ('long', 'PUT', 'weak'):     'suppress',
        ('long', 'PUT', 'medium'):   'downgrade',
        ('long', 'PUT', 'strong'):   'tag',
        ('short', 'PUT', 'weak'):    'pass',
        ('short', 'PUT', 'medium'):  'pass',
        ('short', 'PUT', 'strong'):  'pass',
        ('short', 'CALL', 'weak'):   'suppress',
        ('short', 'CALL', 'medium'): 'downgrade',
        ('short', 'CALL', 'strong'): 'tag',
        ('flat', 'CALL', 'weak'):    'annotate',
        ('flat', 'CALL', 'medium'):  'downgrade',
        ('flat', 'CALL', 'strong'):  'tag',
        ('flat', 'PUT', 'weak'):     'annotate',
        ('flat', 'PUT', 'medium'):   'downgrade',
        ('flat', 'PUT', 'strong'):   'tag',
    }
    for (plan_dir, fire_dir, strength), expected_action in expected.items():
        d = evaluate_direction_gate(fire_dir, strength, _ctx(plan_dir))
        assert d.action == expected_action, \
            f"plan={plan_dir} fire={fire_dir} {strength}: " \
            f"expected {expected_action}, got {d.action}"
