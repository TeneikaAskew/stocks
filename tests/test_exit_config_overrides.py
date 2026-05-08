"""Unit tests for lib.strategies.exit_config_overrides (Tier-A resolver).

Mirrors test_strategies_calibration.py — same monkeypatch-the-row
strategy, no DB required. Covers:

  - Tier-A hit (DB row present + usable values)
  - Tier-A miss → Tier-B fallback (no row, NaN, None, infinity, stale)
  - Per-knob resolution (call_target / put_target / call_stop / put_stop /
    call_time_stop / put_time_stop)
  - lru_cache cleared between tests so monkeypatches take effect
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from lib.strategies import exit_config_overrides as eco
from lib.config import ExitConfig

DEFAULTS = ExitConfig()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear lru_cache between tests."""
    eco._latest_overrides.cache_clear()
    yield
    eco._latest_overrides.cache_clear()


# ── Tier-A miss: empty row ────────────────────────────────────────────


def test_no_row_returns_tier_b_call_target():
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_call_target("UNKNOWN") == DEFAULTS.call_target


def test_no_row_returns_tier_b_for_every_knob():
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_call_target("X") == DEFAULTS.call_target
        assert eco.get_put_target("X") == DEFAULTS.put_target
        assert eco.get_call_stop("X") == DEFAULTS.call_stop
        assert eco.get_put_stop("X") == DEFAULTS.put_stop
        assert eco.get_call_time_stop("X") == DEFAULTS.call_time_stop
        assert eco.get_put_time_stop("X") == DEFAULTS.put_time_stop


# ── Tier-A hit ────────────────────────────────────────────────────────


def _row(**overrides) -> dict:
    base = {
        "calibration_date": date.today(),
        "call_target": 0.00301, "put_target": 0.00238,
        "call_stop": 0.00075, "put_stop": 0.00075,
        "call_time_stop": 20, "put_time_stop": 25,
        "disabled_conditions": None,
        "notes": "test",
    }
    base.update(overrides)
    return base


def test_tier_a_hit_call_target():
    with patch.object(eco, "_latest_overrides", return_value=_row()):
        assert eco.get_call_target("QQQ") == 0.00301


def test_tier_a_hit_all_knobs():
    with patch.object(eco, "_latest_overrides", return_value=_row()):
        assert eco.get_call_target("QQQ") == 0.00301
        assert eco.get_put_target("QQQ") == 0.00238
        assert eco.get_call_stop("QQQ") == 0.00075
        assert eco.get_put_stop("QQQ") == 0.00075
        assert eco.get_call_time_stop("QQQ") == 20
        assert eco.get_put_time_stop("QQQ") == 25


# ── NaN / None / infinity in row → Tier-B for that knob only ─────────


def test_nan_call_target_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=float('nan'))):
        # NaN call_target → Tier-B; other knobs still Tier-A
        assert eco.get_call_target("QQQ") == DEFAULTS.call_target
        assert eco.get_put_target("QQQ") == 0.00238


def test_none_call_target_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=None)):
        assert eco.get_call_target("QQQ") == DEFAULTS.call_target


def test_infinity_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=float('inf'))):
        assert eco.get_call_target("QQQ") == DEFAULTS.call_target


def test_zero_time_stop_falls_back():
    """0 minute time-stop is nonsense; treat as missing."""
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_time_stop=0)):
        assert eco.get_call_time_stop("QQQ") == DEFAULTS.call_time_stop


def test_negative_time_stop_falls_back():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(put_time_stop=-5)):
        assert eco.get_put_time_stop("QQQ") == DEFAULTS.put_time_stop


# ── Stale row → Tier-B (handled inside _latest_overrides) ────────────


def test_get_resolution_tier_returns_b_when_no_row():
    with patch.object(eco, "_latest_overrides", return_value=None):
        assert eco.get_resolution_tier("UNK", "call_target") == "B"


def test_get_resolution_tier_returns_a_when_present():
    with patch.object(eco, "_latest_overrides", return_value=_row()):
        assert eco.get_resolution_tier("QQQ", "call_target") == "A"
        assert eco.get_resolution_tier("QQQ", "put_target") == "A"
        assert eco.get_resolution_tier("QQQ", "call_time_stop") == "A"


def test_get_resolution_tier_returns_b_when_value_nan():
    with patch.object(eco, "_latest_overrides",
                      return_value=_row(call_target=float('nan'))):
        assert eco.get_resolution_tier("QQQ", "call_target") == "B"
        # Other knobs still A
        assert eco.get_resolution_tier("QQQ", "put_target") == "A"


# ── Helper purity ─────────────────────────────────────────────────────


def test_is_usable_number():
    assert eco._is_usable_number(0.00301)
    assert not eco._is_usable_number(None)
    assert not eco._is_usable_number(float('nan'))
    assert not eco._is_usable_number(float('inf'))
    assert not eco._is_usable_number(float('-inf'))
    assert eco._is_usable_number(0.0)  # zero is a valid value


def test_is_usable_int():
    assert eco._is_usable_int(20)
    assert eco._is_usable_int(20.0)
    assert not eco._is_usable_int(None)
    assert not eco._is_usable_int(float('nan'))
    assert not eco._is_usable_int(0)
    assert not eco._is_usable_int(-5)
