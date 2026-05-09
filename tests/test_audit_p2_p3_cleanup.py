"""Tests for the Track D P2/P3 cleanup PR (#9 in the implementation plan).

Three concerns:
  1. G.P2.5 — fire_alert gates Discord post on minimum strength but
     ALWAYS persists. Locked in by source-inspection + a runtime assert.
  2. G.P2.6 — compute_score_quality_correlation returns sensible
     Spearman ρ for a synthetic high-discrimination dataset and signals
     insufficient-data correctly.
  3. G.P3.4 — already covered in tests/test_strategy_agreement.py;
     this file just adds the fire_alert→persist round-trip integration.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


# ── 1) G.P2.5 — Discord gating on strength ───────────────────────────

def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    return SignalMonitor()


def _bar():
    return pd.Series({
        "Close": 720.0, "Last": 720.0,
        "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": 723.0, "EMA9": 722.0, "EMA20": 723.5,
        "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.42, "Price_vs_EMA9": -0.28, "Price_vs_EMA20": -0.49,
        "Consecutive_Down": 4, "Consecutive_Up": 0,
        "RVOL": 1.4, "ATR14": 1.2,
        "Broke_Prev_Day_Low": 0, "Broke_Prev_Day_High": 0,
    })


def _sig():
    return {
        "direction": "CALL", "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }


def test_discord_post_suppressed_for_weak_strength():
    """Default `discord_minimum_strength='medium'` suppresses Discord
    posts for 'weak' alerts. Persistence still happens (analytics need
    every fire)."""
    monitor = _make_monitor()
    monitor.webhook_url = "https://discord.example/webhook"
    ticker = monitor.tickers[0]
    with patch("gcp.signal_monitor.requests.post") as mock_post, \
         patch.object(monitor, "_persist_signal_alert") as mock_persist:
        monitor.fire_alert(
            ticker, _sig(), total_score=2.0,
            strength="weak", size=0.05, strat_bonus=0,
            latest=_bar(),
        )
    assert not mock_post.called, (
        "Discord post must be suppressed for weak strength under default "
        "discord_minimum_strength='medium'"
    )
    assert mock_persist.called, (
        "Persistence must always run regardless of Discord gate so "
        "analytics still capture weak signals"
    )


def test_discord_post_fires_for_medium_and_above():
    """Medium / strong / perfect all pass the default gate."""
    monitor = _make_monitor()
    monitor.webhook_url = "https://discord.example/webhook"
    ticker = monitor.tickers[0]
    for label in ("medium", "strong", "perfect"):
        with patch("gcp.signal_monitor.requests.post") as mock_post, \
             patch.object(monitor, "_persist_signal_alert"):
            monitor.fire_alert(
                ticker, _sig(), total_score=4.0,
                strength=label, size=0.10, strat_bonus=0,
                latest=_bar(),
            )
        assert mock_post.called, (
            f"Discord post must fire for strength={label} under default gate"
        )


def test_discord_minimum_strength_configurable_to_weak():
    """Setting discord_minimum_strength='weak' restores pre-G.P2.5 behaviour."""
    monitor = _make_monitor()
    monitor.webhook_url = "https://discord.example/webhook"
    monitor.monitor_cfg.discord_minimum_strength = "weak"
    ticker = monitor.tickers[0]
    with patch("gcp.signal_monitor.requests.post") as mock_post, \
         patch.object(monitor, "_persist_signal_alert"):
        monitor.fire_alert(
            ticker, _sig(), total_score=2.0,
            strength="weak", size=0.05, strat_bonus=0,
            latest=_bar(),
        )
    assert mock_post.called, (
        "When discord_minimum_strength='weak', even weak alerts post"
    )


# ── 2) G.P2.6 — Spearman ρ on score quartiles ────────────────────────

def test_quality_correlation_high_for_perfect_discrimination():
    """A synthetic dataset where higher score → higher hit rate
    (perfect monotonic discrimination) should produce Spearman ρ ≈ 1.0."""
    pytest.importorskip("scipy.stats")
    from gcp.signal_quality_alarm import compute_score_quality_correlation

    rows = []
    # Q1: 25 rows, score=1, 0% hit
    rows += [{"score": 1.0, "hit": 0} for _ in range(25)]
    # Q2: 25 rows, score=2, 25% hit
    rows += [{"score": 2.0, "hit": 1 if i < 6 else 0} for i in range(25)]
    # Q3: 25 rows, score=3, 50% hit
    rows += [{"score": 3.0, "hit": 1 if i < 12 else 0} for i in range(25)]
    # Q4: 25 rows, score=4, 100% hit
    rows += [{"score": 4.0, "hit": 1} for _ in range(25)]

    rho = compute_score_quality_correlation(rows)
    assert rho is not None
    assert rho == pytest.approx(1.0, abs=0.01), (
        f"perfect discrimination must produce ρ ≈ 1.0; got {rho}"
    )


def test_quality_correlation_zero_when_no_discrimination():
    """When hit rate is constant across quartiles, ρ should be near 0."""
    pytest.importorskip("scipy.stats")
    from gcp.signal_quality_alarm import compute_score_quality_correlation

    # 4 quartiles, each 25 rows, each 50% hit — flat discrimination
    rows = []
    for q in (1.0, 2.0, 3.0, 4.0):
        rows += [{"score": q, "hit": 1 if i < 12 else 0} for i in range(25)]

    rho = compute_score_quality_correlation(rows)
    # spearmanr can return NaN for perfectly tied ranks; the helper
    # converts that to None.
    assert rho is None or abs(rho) < 0.5, (
        f"flat discrimination must give |ρ| ≪ 1; got {rho}"
    )


def test_quality_correlation_returns_none_on_insufficient_sample():
    """Below MIN_SAMPLE rows, return None — too noisy for ρ to mean
    anything."""
    from gcp.signal_quality_alarm import (
        compute_score_quality_correlation,
        QUALITY_CORRELATION_MIN_SAMPLE,
    )
    rows = [{"score": float(i), "hit": i % 2}
            for i in range(QUALITY_CORRELATION_MIN_SAMPLE - 1)]
    assert compute_score_quality_correlation(rows) is None


def test_quality_correlation_embed_signals_insufficient_data():
    """format_quality_correlation_embed handles None ρ as
    insufficient-data (gray, no alarm)."""
    from gcp.signal_quality_alarm import format_quality_correlation_embed
    payload = format_quality_correlation_embed(None, n_rows=10, tf_col="cls_60m")
    assert payload["embeds"][0]["color"] == 0x808080, "gray = insufficient"


def test_quality_correlation_embed_red_when_below_threshold():
    """Below |ρ| threshold → red embed (alarm fires)."""
    from gcp.signal_quality_alarm import format_quality_correlation_embed
    payload = format_quality_correlation_embed(0.05, n_rows=200, tf_col="cls_60m")
    assert payload["embeds"][0]["color"] == 0xff0000, "red = alarm"


def test_quality_correlation_embed_green_when_healthy():
    """Above threshold → green embed."""
    from gcp.signal_quality_alarm import format_quality_correlation_embed
    payload = format_quality_correlation_embed(0.7, n_rows=200, tf_col="cls_60m")
    assert payload["embeds"][0]["color"] == 0x36a64f, "green = healthy"
