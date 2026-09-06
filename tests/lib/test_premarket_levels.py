"""Tests for `compute_premarket_levels` (PR followup to #381).

Pre-fix the trade_planner had to synthesize a blue-sky trigger above
pre_high via ATR projection (5/6 QQQ: $695.52 = pre_high+0.20×ATR),
which on tight days like 5/6 was never reached during RTH. With
PMK_H/PMK_L persisted to `strat_levels`:

  1. The live signal_monitor sees them as triggerable crossings during
     RTH (PR #381 added the read-side; this PR adds the write-side).
  2. The trade_planner can use them as candidate triggers in
     `select_trigger_and_regime` blue-sky branch.
  3. Insight `key_levels` and downstream analytics can include them.
"""
from __future__ import annotations

import pytest
from lib.strat_levels import compute_premarket_levels, StratLevel


def test_compute_premarket_levels_both_present():
    out = compute_premarket_levels(pre_high=692.86, pre_low=685.20)
    assert set(out.keys()) == {'PMK_H', 'PMK_L'}
    assert out['PMK_H'].price == 692.86
    assert out['PMK_H'].timeframe == 'intraday'
    assert out['PMK_H'].level_type == 'high'
    assert out['PMK_H'].is_current is True
    assert out['PMK_H'].period_label == 'premarket'
    assert out['PMK_L'].price == 685.20
    assert out['PMK_L'].level_type == 'low'


def test_compute_premarket_levels_high_only():
    """When pre_low is missing (rare, but happens early in premarket),
    we still persist pre_high so the live monitor has SOMETHING to
    trigger off."""
    out = compute_premarket_levels(pre_high=692.86, pre_low=None)
    assert set(out.keys()) == {'PMK_H'}
    assert out['PMK_H'].price == 692.86


def test_compute_premarket_levels_low_only():
    out = compute_premarket_levels(pre_high=None, pre_low=685.20)
    assert set(out.keys()) == {'PMK_L'}


def test_compute_premarket_levels_both_none_returns_empty():
    """Safe back-compat: no premarket data → no rows. Caller (brief)
    logs and proceeds without these levels."""
    out = compute_premarket_levels(pre_high=None, pre_low=None)
    assert out == {}


def test_compute_premarket_levels_zero_or_negative_inputs_skipped():
    """A bug or fixture anomaly should not write garbage rows."""
    out = compute_premarket_levels(pre_high=0.0, pre_low=-1.5)
    assert out == {}


def test_compute_premarket_levels_returns_StratLevel_instances():
    """Caller appends to LevelMap.levels (List[StratLevel]) so the type
    has to match."""
    out = compute_premarket_levels(692.86, 685.20)
    for level in out.values():
        assert isinstance(level, StratLevel)
