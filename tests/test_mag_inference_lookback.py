"""Unit tests for gcp/research/magnitude_engine/mag_inference.py lookback logic.

Pins the fix for the recurring Monday ZERO-OUTPUT bug (gcp-job-failure
incidents 2026-06-22 and 2026-06-29): a fixed 24h lookback window can't
reach back across a weekend to Friday's close, so the job finds zero
scorable bars every Monday and every Friday's session permanently never
gets scored (verified against magnitude_per_bar_predictions: 06-19 and
06-26 both missing while every other weekday in the window is present).
"""
from __future__ import annotations

from datetime import datetime, timezone

from gcp.research.magnitude_engine.mag_inference import (
    INFERENCE_LOOKBACK_HOURS,
    _MONDAY_LOOKBACK_HOURS,
    _resolve_lookback_hours,
)

# 2026-06-29 is a Monday, 2026-06-30 is a Tuesday (confirmed against the
# actual incident dates).
_MONDAY = datetime(2026, 6, 29, 13, 25, tzinfo=timezone.utc)
_TUESDAY = datetime(2026, 6, 30, 13, 25, tzinfo=timezone.utc)
_FRIDAY = datetime(2026, 6, 26, 13, 25, tzinfo=timezone.utc)


def test_monday_default_widens_lookback():
    assert _resolve_lookback_hours(None, None, _MONDAY) == _MONDAY_LOOKBACK_HOURS


def test_monday_window_spans_prior_fridays_close():
    """The whole point: Monday's cutoff must reach back before Friday's
    ~20:00 UTC close, or Friday's session is permanently skipped."""
    cutoff = _MONDAY.timestamp() - _resolve_lookback_hours(None, None, _MONDAY) * 3600
    friday_close = datetime(2026, 6, 26, 20, 0, tzinfo=timezone.utc).timestamp()
    assert cutoff < friday_close


def test_non_monday_default_keeps_normal_window():
    assert _resolve_lookback_hours(None, None, _TUESDAY) == INFERENCE_LOOKBACK_HOURS
    assert _resolve_lookback_hours(None, None, _FRIDAY) == INFERENCE_LOOKBACK_HOURS


def test_explicit_cli_value_overrides_monday_default():
    assert _resolve_lookback_hours(48, None, _MONDAY) == 48


def test_explicit_env_value_overrides_monday_default():
    assert _resolve_lookback_hours(None, "12", _MONDAY) == 12


def test_cli_value_takes_priority_over_env_value():
    assert _resolve_lookback_hours(10, "20", _MONDAY) == 10
