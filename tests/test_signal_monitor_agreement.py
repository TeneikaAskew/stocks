"""Phase 1.6 — integration tests for signal_monitor's agreement wiring.

Coverage:
  1. _evaluate_strategies_for_bar — mr=None short-circuit (no momentum eval)
  2. _evaluate_strategies_for_bar — solo mr fires, momentum returns None
  3. _evaluate_strategies_for_bar — stacked: both fire CALL → payload set
  4. _evaluate_strategies_for_bar — disagreement: mr CALL + mom PUT → no payload
  5. _persist_signal_alert — strategy_agreement IS the JSON payload when stacked
  6. _persist_signal_alert — strategy_agreement IS None when solo
  7. fire_alert embed — STACKED prefix + agreement_block when stacked
  8. fire_alert embed — no STACKED prefix when solo

Hermetic — mocks the momentum strategy evaluator so we don't depend on
constructing a synthetic bar that satisfies both opposing strategies.
The agreement helper itself is exhaustively tested in
tests/test_strategy_agreement.py; this file verifies the WIRING.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.strategies.base import Signal  # noqa: E402


# Same fixture pattern as tests/test_signal_monitor_persist.py
def _make_monitor():
    from gcp.signal_monitor import SignalMonitor
    monitor = SignalMonitor()
    monitor.webhook_url = ""    # disable Discord side-effect
    return monitor


def _mr_call_bar() -> pd.Series:
    """Bar that satisfies mean-reversion CALL: oversold pullback."""
    return pd.Series({
        "Close": 720.0, "Last": 720.0,
        "RSI14": 35.0, "RSI14_W": 35.0,
        "VWAP": 723.0,
        "EMA9": 722.0, "EMA20": 723.5,
        "StochRSI_K": 25.0,
        "Price_vs_VWAP": -0.42,
        "Price_vs_EMA9": -0.28,
        "Price_vs_EMA20": -0.49,
        "Consecutive_Down": 4,
        "Consecutive_Up": 0,
        "RVOL": 1.4, "ATR14": 1.2,
        "Broke_Prev_Day_Low": 0,
        "Broke_Prev_Day_High": 0,
    })


def _no_signal_bar() -> pd.Series:
    """Mid-range bar that satisfies neither strategy."""
    return pd.Series({
        "Close": 720.0, "Last": 720.0,
        "RSI14": 50.0, "RSI14_W": 50.0,
        "VWAP": 720.0,
        "EMA9": 720.0, "EMA20": 720.0,
        "StochRSI_K": 50.0,
        "Price_vs_VWAP": 0.0,
        "Price_vs_EMA9": 0.0, "Price_vs_EMA20": 0.0,
        "Consecutive_Up": 0, "Consecutive_Down": 0,
        "RVOL": 1.0, "ATR14": 1.0,
    })


def _mom_call_signal() -> Signal:
    return Signal(
        strategy="momentum",
        direction="CALL",
        timestamp=pd.Timestamp("2026-05-01 14:30", tz="UTC"),
        entry_price=720.0,
        base_score=4.0,
        weighted_score=4.0,
        conditions_met=["consecutive_up", "above_vwap", "above_ema9", "rsi_bullish_recovery"],
    )


def _mom_put_signal() -> Signal:
    return Signal(
        strategy="momentum",
        direction="PUT",
        timestamp=pd.Timestamp("2026-05-01 14:30", tz="UTC"),
        entry_price=720.0,
        base_score=3.0,
        weighted_score=3.0,
        conditions_met=["consecutive_down", "below_vwap"],
    )


# ── 1) mr returns None → helper short-circuits, momentum NOT evaluated ─

def test_helper_no_mr_signal_returns_none_pair_and_skips_momentum():
    monitor = _make_monitor()
    bar = _no_signal_bar()
    with patch("gcp.signal_monitor.MOMENTUM.evaluate") as mock_mom:
        sig, agreement = monitor._evaluate_strategies_for_bar(bar, 720.0, "SPY")
    assert sig is None
    assert agreement is None
    # Momentum should NOT be evaluated when mean-reversion didn't fire —
    # saves the cycles on the dominant no-signal path.
    mock_mom.assert_not_called()


# ── 2) Solo mr (momentum returns None) → no agreement ─────────────────

def test_helper_solo_mr_no_agreement():
    monitor = _make_monitor()
    bar = _mr_call_bar()
    with patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=None):
        sig, agreement = monitor._evaluate_strategies_for_bar(bar, 720.0, "SPY")
    assert sig is not None and sig["direction"] == "CALL"
    assert agreement is None


# ── 3) Stacked: both fire CALL → agreement payload set ────────────────

def test_helper_stacked_returns_agreement_payload():
    monitor = _make_monitor()
    bar = _mr_call_bar()
    with patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=_mom_call_signal()):
        sig, agreement = monitor._evaluate_strategies_for_bar(bar, 720.0, "SPY")
    assert sig is not None and sig["direction"] == "CALL"
    assert agreement is not None
    assert agreement["agree"] is True
    assert agreement["directions"] == ["CALL", "CALL"]
    # Composite score: max(base_scores) + AGREEMENT_BONUS (1.0)
    assert agreement["composite_score"] == pytest.approx(5.0)


# ── 4) Disagreement: mr CALL + mom PUT → no agreement ─────────────────

def test_helper_disagreement_no_agreement_payload():
    monitor = _make_monitor()
    bar = _mr_call_bar()
    with patch("gcp.signal_monitor.MOMENTUM.evaluate", return_value=_mom_put_signal()):
        sig, agreement = monitor._evaluate_strategies_for_bar(bar, 720.0, "SPY")
    assert sig is not None and sig["direction"] == "CALL"
    # mr fired CALL, mom fired PUT → opposite → no stacked bonus
    assert agreement is None


# ── 5) Persist: strategy_agreement carries the JSON when stacked ──────

def test_persist_writes_strategy_agreement_json_when_stacked():
    monitor = _make_monitor()
    monitor._latest_agreement = {
        "agree": True,
        "strategies": ["mean_reversion", "momentum"],
        "directions": ["CALL", "CALL"],
        "base_scores": [4.0, 4.0],
        "composite_score": 5.0,
    }
    sig = {
        "direction": "CALL",
        "base_score": 4,
        "conditions_met": ["consecutive_down", "rsi_oversold_zone", "below_vwap"],
    }
    latest = _mr_call_bar()

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker="SPY", sig=sig, total_score=5.0,
            strength="STRONG", size=0.10, strat_bonus=0,
            latest=latest, target=722.5, time_stop=30,
        )

    df = mock_upsert.call_args[0][0]
    assert "strategy_agreement" in df.columns
    payload = df.iloc[0]["strategy_agreement"]
    assert isinstance(payload, str), \
        "strategy_agreement must be JSON-serialized for the JSONB column"
    parsed = json.loads(payload)
    assert parsed["agree"] is True
    assert parsed["composite_score"] == 5.0


# ── 6) Persist: strategy_agreement is None on solo fires ──────────────

def test_persist_strategy_agreement_none_when_solo():
    monitor = _make_monitor()
    monitor._latest_agreement = None     # solo (the common case)
    sig = {
        "direction": "PUT",
        "base_score": 3,
        "conditions_met": ["consecutive_up", "rsi_overbought_zone", "above_vwap"],
    }
    latest = _mr_call_bar()      # bar shape doesn't matter here

    with patch("gcp.database.upsert_dataframe") as mock_upsert, \
         patch("gcp.database.is_cloud_sql_configured", return_value=True):
        mock_upsert.return_value = 1
        monitor._persist_signal_alert(
            ticker="QQQ", sig=sig, total_score=3.0,
            strength="MODERATE", size=0.05, strat_bonus=0,
            latest=latest, target=712.0, time_stop=20,
        )

    df = mock_upsert.call_args[0][0]
    assert "strategy_agreement" in df.columns
    assert df.iloc[0]["strategy_agreement"] is None


# ── 7) Embed prefix on stacked fires ──────────────────────────────────

def _capture_printed_embed(monitor, sig, latest, target=722.0, time_stop=30):
    """fire_alert prints the embed JSON to stdout. Capture the embed dict."""
    import io, contextlib
    buf = io.StringIO()
    with patch("gcp.database.upsert_dataframe", return_value=1), \
         patch("gcp.database.is_cloud_sql_configured", return_value=True), \
         contextlib.redirect_stdout(buf):
        monitor.fire_alert(
            ticker="SPY", sig=sig, total_score=5.0,
            strength="STRONG", size=0.10, strat_bonus=0,
            latest=latest,
        )
    text = buf.getvalue()
    # The embed JSON is wrapped in '=' separators; pull the JSON block.
    start = text.find("{")
    end = text.rfind("}")
    return json.loads(text[start: end + 1])


def test_fire_alert_embed_has_stacked_prefix_when_agreement():
    monitor = _make_monitor()
    monitor._latest_agreement = {
        "agree": True,
        "strategies": ["mean_reversion", "momentum"],
        "directions": ["CALL", "CALL"],
        "base_scores": [4.0, 4.0],
        "composite_score": 5.0,
    }
    sig = {
        "direction": "CALL",
        "base_score": 4,
        "conditions_met": ["consecutive_down", "below_vwap"],
    }
    latest = _mr_call_bar()
    embed = _capture_printed_embed(monitor, sig, latest)
    # Visual prefix on the title (🎯 = U+1F3AF)
    assert "STACKED" in embed["title"]
    assert "STACKED" in embed["description"]
    assert "Composite score: 5.0" in embed["description"]


def test_fire_alert_embed_no_stacked_prefix_when_solo():
    monitor = _make_monitor()
    monitor._latest_agreement = None    # solo fire
    sig = {
        "direction": "CALL",
        "base_score": 4,
        "conditions_met": ["consecutive_down", "below_vwap"],
    }
    latest = _mr_call_bar()
    embed = _capture_printed_embed(monitor, sig, latest)
    assert "STACKED" not in embed["title"]
    assert "STACKED" not in embed["description"]
