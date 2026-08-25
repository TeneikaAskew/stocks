"""Tests for the RVOL entry gate (audit 2026-08-25 §10).

The pure verdict function carries the semantics; the integration tests
pin the two behavioral contracts: shadow mode tags the persisted row
without changing fire behavior, enforce mode suppresses the fire before
Discord, persist, and the daily-trades counter.
"""
from __future__ import annotations

import math
from unittest.mock import patch

import pandas as pd

from gcp.signal_monitor import rvol_gate_verdict


# ── pure verdict semantics ──────────────────────────────────────────

def test_verdict_off_mode_returns_none():
    assert rvol_gate_verdict(0.4, 1.0, 'off') is None
    assert rvol_gate_verdict(2.0, 1.0, 'off') is None


def test_verdict_pass_at_and_above_threshold():
    assert rvol_gate_verdict(1.0, 1.0, 'shadow') == 'pass'
    assert rvol_gate_verdict(2.5, 1.0, 'enforce') == 'pass'


def test_verdict_below_threshold():
    assert rvol_gate_verdict(0.99, 1.0, 'shadow') == 'below'


def test_verdict_missing_rvol_is_below_not_pass():
    # CLAUDE.md §3.7 — an unknown RVOL must never silently pass a gate.
    assert rvol_gate_verdict(None, 1.0, 'shadow') == 'below'
    assert rvol_gate_verdict(float('nan'), 1.0, 'shadow') == 'below'
    assert rvol_gate_verdict(0.0, 1.0, 'shadow') == 'below'


# ── integration: enforce suppresses, shadow tags ────────────────────

def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""
    return monitor


def _bar(rvol):
    return pd.Series({
        "Close": 680.0, "Last": 680.0, "RSI14": 40.0, "RVOL": rvol,
        "VWAP": 681.0, "EMA9": 680.5, "EMA20": 681.0, "ATR14": 1.0,
        "StochRSI_K": 25.0, "Consecutive_Down": 3,
    })


def _sig():
    return {"direction": "CALL", "base_score": 4.0,
            "conditions_met": ["rsi_in_range", "below_vwap"]}


def test_enforce_mode_suppresses_fire_before_persist_and_counter():
    monitor = _make_monitor()
    monitor.signal_cfg.rvol_gate_mode = 'enforce'
    monitor.signal_cfg.rvol_gate_min = 1.0
    before = dict(monitor.daily_trades)
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar(0.4))
    assert not mock_persist.called, "enforce+below must not persist"
    assert monitor.daily_trades.get('QQQ', 0) == before.get('QQQ', 0), \
        "suppressed fire must not consume the daily-trades cap"


def test_enforce_mode_passes_fire_at_threshold():
    monitor = _make_monitor()
    monitor.signal_cfg.rvol_gate_mode = 'enforce'
    monitor.signal_cfg.rvol_gate_min = 1.0
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar(1.2))
    assert mock_persist.called, "enforce+pass must fire normally"
    assert monitor._latest_rvol_gate == 'pass'


def test_shadow_mode_fires_and_stashes_verdict():
    monitor = _make_monitor()
    monitor.signal_cfg.rvol_gate_mode = 'shadow'
    monitor.signal_cfg.rvol_gate_min = 1.0
    with patch.object(monitor, '_persist_signal_alert') as mock_persist:
        monitor.fire_alert('QQQ', _sig(), 4.0, 'medium', 0.5, 0, _bar(0.4))
    assert mock_persist.called, "shadow mode must never suppress a fire"
    assert monitor._latest_rvol_gate == 'below'
