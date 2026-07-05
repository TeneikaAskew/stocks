"""Unit tests for gcp/research/magnitude_engine/mag_inference.py lookback logic.

Pins the fix for the recurring Monday ZERO-OUTPUT bug (gcp-job-failure
incidents 2026-06-22 and 2026-06-29): a fixed 24h lookback window can't
reach back across a weekend to Friday's close, so the job finds zero
scorable bars every Monday and every Friday's session permanently never
gets scored (verified against magnitude_per_bar_predictions: 06-19 and
06-26 both missing while every other weekday in the window is present).

Originally fixed with a day-of-week check (widen on Monday only), but
Codex flagged on PR #668 that a civil-Monday check still ZERO-OUTPUTs
(and false-pages) the Tuesday after a Monday market holiday, since
weekday()==1 falls through to the plain 24h window which starts on the
empty holiday session. Replaced with a session-gap escalation ladder
that widens based on whether bars were actually found, not the weekday —
covers weekends, holidays, holiday-adjacent weekends, and missed-run
catch-up uniformly.
"""
from __future__ import annotations

import pandas as pd

from gcp.research.magnitude_engine.mag_inference import (
    INFERENCE_LOOKBACK_HOURS,
    LOOKBACK_ESCALATION_HOURS,
    _load_recent_features_with_escalation,
    _resolve_explicit_lookback_hours,
)


def test_escalation_ladder_starts_at_the_normal_default():
    """The first rung must be the cheap, ordinary-weekday window so a
    normal Tue-Fri run never pays for a wider query."""
    assert LOOKBACK_ESCALATION_HOURS[0] == INFERENCE_LOOKBACK_HOURS


def test_escalation_ladder_is_strictly_increasing():
    assert list(LOOKBACK_ESCALATION_HOURS) == sorted(set(LOOKBACK_ESCALATION_HOURS))


def test_escalation_ladder_final_rung_spans_a_full_week():
    """168h (7 days) must be reachable so even a rare multi-day closure
    (e.g. a holiday-adjacent weekend, or a missed prior run) still finds
    the most recent real session before the ZERO-OUTPUT check fires."""
    assert max(LOOKBACK_ESCALATION_HOURS) >= 168


def test_explicit_cli_value_returned_verbatim():
    assert _resolve_explicit_lookback_hours(48, None) == 48


def test_explicit_env_value_returned_when_no_cli_value():
    assert _resolve_explicit_lookback_hours(None, "12") == 12


def test_cli_value_takes_priority_over_env_value():
    assert _resolve_explicit_lookback_hours(10, "20") == 10


def test_no_override_returns_none_signalling_auto_escalation():
    assert _resolve_explicit_lookback_hours(None, None) is None


def test_explicit_lookback_skips_escalation_entirely(monkeypatch):
    """An operator-supplied --lookback-hours must be used as-is, with no
    escalation attempted, even if it returns zero rows."""
    calls = []

    def fake_load(ticker, tf, lookback_hours):
        calls.append(lookback_hours)
        return pd.DataFrame()

    monkeypatch.setattr(
        "gcp.research.magnitude_engine.mag_inference._load_recent_features",
        fake_load,
    )
    df = _load_recent_features_with_escalation("SPY", "5m", 7)
    assert df.empty
    assert calls == [7], "explicit lookback must not escalate to other rungs"


def test_auto_mode_stops_at_first_rung_with_bars(monkeypatch):
    calls = []

    def fake_load(ticker, tf, lookback_hours):
        calls.append(lookback_hours)
        return pd.DataFrame({"x": [1]}) if lookback_hours == 96 else pd.DataFrame()

    monkeypatch.setattr(
        "gcp.research.magnitude_engine.mag_inference._load_recent_features",
        fake_load,
    )
    df = _load_recent_features_with_escalation("SPY", "5m", None)
    assert not df.empty
    assert calls == [h for h in LOOKBACK_ESCALATION_HOURS if h <= 96], (
        "must stop escalating as soon as a rung finds bars, not query every rung"
    )


def test_auto_mode_exhausts_ladder_and_returns_empty_on_real_outage(monkeypatch):
    calls = []

    def fake_load(ticker, tf, lookback_hours):
        calls.append(lookback_hours)
        return pd.DataFrame()

    monkeypatch.setattr(
        "gcp.research.magnitude_engine.mag_inference._load_recent_features",
        fake_load,
    )
    df = _load_recent_features_with_escalation("SPY", "5m", None)
    assert df.empty
    assert calls == list(LOOKBACK_ESCALATION_HOURS), (
        "a genuine outage must try every rung before giving up, so the "
        "ZERO-OUTPUT check only fires after a full week of no bars"
    )
